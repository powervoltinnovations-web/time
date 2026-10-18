"""Upgrade, resource contention, scoped scheduling, and interchange regressions."""
from collections import Counter
from copy import deepcopy
import io
import json
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from pypdf import PdfReader
import pytest
from app import storage
from app.analytics import analyze
from app.calendar import Settings
from app.demo import presentation_config
from app.domain import Configuration, parse_csv
from app.exchange import configuration_csv_v2, configuration_excel, parse_upload
from app.exports import excel, pdf
from app.main import app
from app.scheduler import generate, preflight
from test_scheduler import small_config


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('UNISCHED_DB',str(tmp_path/'workspace.db'))
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope='module')
def demo_record():
    config=presentation_config()
    result=generate(config,60)
    assert result['status']=='feasible', result
    return {'id':1,'name':'IT presentation','config':config.model_dump(),'result':result}


def test_new_install_and_backups(client):
    current=client.get('/api/config').json()
    c=Configuration(**current['configuration'])
    assert current['revision']==1
    assert (len(c.subjects),len(c.teachers),len(c.groups),len(c.rooms),len(c.offerings))==(24,33,9,13,153)
    assert c.settings.start=='09:00'
    for suffix in ('json','xlsx','csv'):
        response=client.get('/api/config.'+suffix)
        assert response.status_code==200
        preview=client.post('/api/import/preview',files={'file':('data.'+suffix,response.content)})
        assert preview.status_code==200,preview.text
        assert preview.json()['issues']==[]
        if suffix!='csv':
            assert preview.json()['configuration']==c.model_dump()
    assert client.get('/api/config').json()==current


def test_full_demo_has_longer_days_and_real_contention(demo_record):
    r=demo_record['result'];a=analyze(demo_record)
    assert r['summary']['sessions']==315
    assert r['summary']['teaching_hours']==396
    assert a['hard_conflicts']==0,a['violations']
    assert a['internal_gaps']==0
    assert a['active_student_days']==135
    counts=Counter((e['offering_id'],e['day']) for e in r['entries'] if e['kind']=='lecture')
    assert max(counts.values())==1
    assert len(demo_record['config']['batches'])==27
    assert all(d['start']=='09:00' for d in a['student_days'])
    assert sum(d['end'] in ('15:45','16:45') for d in a['student_days'])>=30
    assert sum(d['periods'] for d in a['student_days'])==864
    assert a['room_utilization']==76.2  # 396 contact periods / (13 rooms * 40 periods)
    assert len(a['rooms'])==13
    assert all(r['utilization']<=100 for r in a['rooms'])
    book=load_workbook(io.BytesIO(excel(demo_record)))
    assert len(book.worksheets)==9
    batch_book=load_workbook(io.BytesIO(excel(demo_record,'group','it3A','it3A1')))
    assert 'Batch A1' in batch_book.active['A2'].value
    all_text=' '.join(str(cell.value) for row in batch_book.active for cell in row)
    assert 'A2' not in all_text and 'A3' not in all_text
    assert '32 scheduled teaching hours' in batch_book.active['A3'].value
    assert len(PdfReader(io.BytesIO(pdf(demo_record))).pages)>=9


def test_scoped_generation_keeps_other_divisions_and_checks_stale_base(client):
    first=client.post('/api/generations',json={'group_ids':['it3A'],'time_limit':20}).json()
    assert first['result']['status']=='feasible',first
    assert {e['group_id'] for e in first['result']['entries']}=={'it3A'}
    second=client.post('/api/generations',json={'group_ids':['it3B'],'time_limit':20}).json()
    assert second['result']['status']=='feasible',second
    assert second['result']['scope']['base_generation_id']==first['id']
    assert [e for e in second['result']['entries'] if e['group_id']=='it3A']==first['result']['entries']
    assert len(second['result']['scope']['remaining_group_ids'])==7
    assert analyze(second)['hard_conflicts']==0
    regenerated=client.post('/api/generations',json={'group_ids':['it3A'],'time_limit':20}).json()
    assert regenerated['result']['status']=='feasible',regenerated
    assert [e for e in regenerated['result']['entries'] if e['group_id']=='it3B']==[e for e in second['result']['entries'] if e['group_id']=='it3B']
    current=client.get('/api/config').json()
    current['configuration']['teachers'][0]['email']='updated@example.edu'
    assert client.put('/api/config',json=current).status_code==200
    assert client.post('/api/generations',json={'group_ids':['it3C'],'base_generation_id':first['id']}).status_code==409
    assert client.post('/api/generations',json={'department_id':'missing'}).status_code==422
    assert client.post('/api/generations',json={'semester':5,'group_ids':['it3A']}).status_code==422
    assert client.get(f"/api/generations/{first['id']}/analytics").json()['hard_conflicts']==0
    metrics=client.get('/api/performance').json()
    assert len(metrics['runs'])==3 and metrics['success_rate']==100
    assert metrics['average_generation_seconds']>0


@pytest.mark.parametrize('change,code',[
    ('seats','ROOM_ELIGIBILITY'),('year','ROOM_ELIGIBILITY'),('department','ROOM_ELIGIBILITY'),
    ('daily','TEACHER_AVAILABILITY'),('lab_eligibility','LAB_ELIGIBILITY')])
def test_hard_resource_restrictions(change,code):
    c=small_config()
    if change=='seats':c.rooms[0].capacity=10
    if change=='year':c.rooms[0].eligible_years=[4]
    if change=='department':
        c.departments.append(type(c.departments[0])(id='other',name='Other',code='OTH'))
        c.rooms[0].department_id='other'
    if change=='daily':c.teachers[0].max_daily_slots=1
    if change=='lab_eligibility':c.teachers[0].lab_eligible=False
    result=generate(c)
    assert result['status']=='infeasible'
    assert code in {i['code'] for i in result['issues']}


def test_batches_projects_calendar_and_exports():
    data=small_config().model_dump()
    data['settings']={'days':['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'],
                      'blocked':[{'day':'Monday','slot':0,'reason':'Assembly'}]}
    data['batches']=[{'id':'b1','group_id':'g','name':'A1','strength':30},{'id':'b2','group_id':'g','name':'A2','strength':30}]
    data['teachers'].append({**data['teachers'][0],'id':'t2','name':'Second Professor'})
    data['offerings'][0].update(lectures=6,labs=0)
    for i in (1,2):
        data['offerings'].append({'id':f'batch{i}','group_id':'g','subject_id':'s','teacher_id':'t' if i==1 else 't2',
                                 'batch_id':f'b{i}','lectures':0,'labs':1,'projects':1,'lab_room_id':'l'})
    data['settings']['spread_lectures']=False  # This separate calendar/project fixture tests legacy distribution.
    # Whole-division lectures use 80 seats; 30-seat laboratory fits only the practical batches.
    data['rooms'][1]['capacity']=30
    assert generate(Configuration(**data),10)['status']=='infeasible'
    data['rooms'].append({**data['rooms'][1],'id':'l2','name':'Second Lab'})
    data['offerings'][-1]['lab_room_id']='l2'
    c=Configuration(**data);r=generate(c,20)
    assert r['status']=='feasible',r
    record={'name':'Batches and projects','config':c.model_dump(),'result':r}
    audit=analyze(record)
    assert audit['hard_conflicts']==0,audit['violations']
    assert len({r['batch'] for r in audit['student_days']})==2
    assert all(e['duration']==4 for e in r['entries'] if e['kind']=='project')
    book=load_workbook(io.BytesIO(excel(record)))
    assert book.active['G5'].value=='Saturday'
    assert book.active['B6'].value=='BLOCKED\nAssembly'
    assert 'A1' in '\n'.join(str(cell.value) for row in book.active for cell in row)
    assert PdfReader(io.BytesIO(pdf(record))).pages
    invalid=deepcopy(data);invalid['batches'][1]['strength']=40
    with pytest.raises(ValueError,match='Batch strengths exceed'):
        Configuration(**invalid)


def test_calendar_validation_and_preview(client):
    response=client.post('/api/calendar/preview',json={'start':'09:00','end':'16:45','period_minutes':60})
    assert response.status_code==200 and len(response.json()['periods'])==7
    for value in ({'end':'16:30'},{'breaks':[{'start':'12:30','duration':45}]},{'days':['Monday','Monday']},
                  {'blocked':[{'day':'Sunday','slot':0}]},{'lab_slots':0}):
        assert client.post('/api/calendar/preview',json=value).status_code==422


def test_csv_preserves_custom_department_room_and_cross_department_teacher():
    data=presentation_config().model_dump()
    data['departments'][0]['id']='d_custom'
    for key in ('groups','teachers','subjects','rooms','elective_sets'):
        for row in data[key]:row['department_id']='d_custom'
    data['departments'].append({'id':'math_department','name':'Applied Mathematics','code':'MATH'})
    data['teachers'][0]['department_id']='math_department'
    c=Configuration(**data)
    parsed=parse_upload(configuration_csv_v2(c).encode(),'data.csv')
    assert parsed.rooms==c.rooms
    assert parsed.departments==c.departments
    assert parsed.teachers[0].department_id=='math_department'
    assert len(parsed.offerings)==153 and preflight(parsed)==[]
    assert parsed.elective_sets[0].code==c.elective_sets[0].code


@pytest.mark.parametrize('filename,content', [('bad.xlsx',b'not a zip'),('bad.json',b'[]'),('bad.json',b'{')])
def test_bad_imports_are_explained(client,filename,content):
    before=client.get('/api/config').json()
    response=client.post('/api/import/preview',files={'file':(filename,content)})
    assert response.status_code==422,response.text
    assert client.get('/api/config').json()==before


def test_excel_rejects_formulas(client):
    book=load_workbook(io.BytesIO(configuration_excel(presentation_config())))
    book['teachers']['B2']='=1+1'
    out=io.BytesIO();book.save(out)
    response=client.post('/api/import/preview',files={'file':('formula.xlsx',out.getvalue())})
    assert response.status_code==422 and 'formulas' in response.text


def test_legacy_database_is_normalized_without_rewriting(tmp_path,monkeypatch):
    monkeypatch.setenv('UNISCHED_DB',str(tmp_path/'legacy.db'))
    c=small_config()
    fields={'teachers':['id','name','max_hours','arrival','departure'],'subjects':['id','name','code','semester','elective'],
            'rooms':['id','name','kind'],'groups':['id','semester','division','room_id'],
            'offerings':['id','group_id','subject_id','teacher_id','lectures','labs','lab_room_id']}
    old={key:[{field:row[field] for field in fields[key]} for row in c.model_dump()[key]] for key in fields}
    result=generate(c,10)
    for e in result['entries']:e.pop('batch_id',None)
    result.pop('scope',None)
    storage.initialize();storage.save_config(old,0)
    identifier=storage.save_generation('Original version',1,old,result)
    with storage.connect() as db:
        body=db.execute('SELECT body FROM configuration').fetchone()[0]
        snapshot=db.execute('SELECT config FROM generations').fetchone()[0]
    with TestClient(app) as client:
        config=client.get('/api/config').json()
        assert config['revision']==1 and len(config['configuration']['offerings'])==1
        assert config['configuration']['departments'][0]['id']=='general'
        config['configuration']['settings']['end']='16:45'
        assert client.put('/api/config',json=config).status_code==200
        saved=client.get(f'/api/generations/{identifier}').json()
        assert saved['meta']['end']=='17:45'
        assert saved['config']['settings']['end']=='17:45'
        assert client.get(f'/api/generations/{identifier}/export/pdf').status_code==200
        assert client.get(f'/api/generations/{identifier}/analytics').json()['hard_conflicts']==0
    with storage.connect() as db:
        assert db.execute('SELECT config FROM generations').fetchone()[0]==snapshot
    # Reading defaults itself did not write the legacy configuration; only the explicit PUT did.
    assert json.loads(body)==old


def test_generated_student_unit_ids_cannot_collide_with_batch_ids():
    from app.resources import student_units
    from app.domain import Batch
    config=small_config()
    config.batches=[Batch(id='division_g',group_id='g',name='A1',strength=30)]
    units=student_units(config,config.groups[0])
    assert len(units)==len(set(units))==2
