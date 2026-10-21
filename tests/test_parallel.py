import json,sqlite3
from copy import deepcopy
from types import SimpleNamespace
import pytest
from app.domain import Configuration
from app.resources import affected_units,eligible_rooms,booking_key
from app.parallel import elective_problems,audit_electives
from app.availability import free_resources
from app.analytics import analyze
from app.editing import edit_result

@pytest.fixture
def config():
    con=sqlite3.connect('file:data/unisched.db?mode=ro',uri=True)
    c=json.loads(con.execute('select body from configuration').fetchone()[0]);con.close()
    c['settings'].update(combined_elective_students={'IS':60,'STQA':60},prefer_parallel_batches=True,classroom_run_length=2)
    return Configuration(**c)

def test_option_student_sets_and_shared_teacher_booking(config):
    items={o.id:o for o in config.offerings}
    a,b,is_b=items['o149'],items['o155'],items['o150']
    assert not set(affected_units(config,a)) & set(affected_units(config,b))
    assert booking_key(config,a,'lecture')==booking_key(config,is_b,'lecture')
    ordinary=next(o for o in config.offerings if o.group_id==a.group_id and o.lectures and o.id not in ('o149','o155'))
    assert set(affected_units(config,a))|set(affected_units(config,b))==set(affected_units(config,ordinary))
    assert not elective_problems(config)

def test_capacity_and_enrollment(config):
    config.settings.combined_elective_students={'IS':80,'STQA':40}
    a=next(o for o in config.offerings if o.id=='o149')
    assert not eligible_rooms(config,a,'lecture')
    config.settings.combined_elective_students={'IS':60,'STQA':59}
    assert elective_problems(config)

def test_inconsistent_combined_teacher_rejected(config):
    next(o for o in config.offerings if o.id=='o150').teacher_id='t1'
    assert elective_problems(config)

def entry(config,oid,day=0,slot=0,room='cr1',kind='lecture',duration=1):
    o=next(o for o in config.offerings if o.id==oid)
    return dict(offering_id=o.id,group_id=o.group_id,subject_id=o.subject_id,teacher_id=o.teacher_id,batch_id=o.batch_id,kind=kind,day=day,slot=slot,duration=duration,room_id=room)

def test_combined_pair_audit(config):
    es=[entry(config,oid,room='cr1' if oid in ('o149','o150') else 'cr2') for oid in ('o149','o150','o155','o156')]
    assert not audit_electives(config,es)
    es[-1]['slot']=1
    assert audit_electives(config,es)

def test_availability_entire_interval_and_break(config):
    es=[entry(config,'o149',slot=1),entry(config,'o150',slot=1)]
    record={'config':config.model_dump(),'result':{'status':'feasible','entries':es}}
    first=free_resources(record,0,0,1)
    both=free_resources(record,0,0,2)
    assert 'cr1' in {r['id'] for r in first['classrooms']}
    assert 'cr1' not in {r['id'] for r in both['classrooms']}
    assert es[0]['teacher_id'] not in {t['id'] for t in both['teachers']}
    teacher=next(t for t in first['teachers'] if t['id']==es[0]['teacher_id'])
    actual=next(t for t in config.teachers if t.id==teacher['id'])
    assert teacher['remaining_daily_periods']==actual.max_daily_slots-1
    with pytest.raises(ValueError):free_resources(record,0,3,2)

def test_labs_stay_in_labs(config):
    for o in config.offerings:
        if o.labs:
            assert all(r.kind=='lab' for r in eligible_rooms(config,o,'lab'))
            assert config.settings.lab_slots==2

@pytest.fixture
def verified(config):
    from app.hints import reference_entries
    entries=reference_entries(config)
    assert entries, 'The shipped exact-data placement hint must exist.'
    return {'id':99,'name':'Verified full plan','config':config.model_dump(),'result':{'status':'feasible','entries':entries,'issues':[],'summary':{'classroom_optimization':{'minimum_run_enforced':True}}}}

def test_complete_official_dataset(config,verified):
    from app.scheduler import generate
    from app.parallel import batch_metrics
    r=generate(config,5,initial_entries=verified['result']['entries'])
    assert r['status']=='feasible'
    audit=analyze({'config':config.model_dump(),'result':r})
    assert audit['hard_conflicts']==0,audit['violations']
    assert len({e['group_id'] for e in r['entries']})==8
    assert batch_metrics(config,r['entries'])['partial_periods']<57
    assert all(e['duration']==2 for e in r['entries'] if e['kind']=='lab')
    assert r['summary']['classroom_optimization']['early_changes']==0

def test_audit_rejects_lab_in_classroom(verified):
    r=deepcopy(verified)
    next(e for e in r['result']['entries'] if e['kind']=='lab')['room_id']='cr1'
    assert any('ineligible room' in v for v in analyze(r)['violations'])

def test_manual_shared_room_edit_and_collision(verified):
    e=next(e for e in verified['result']['entries'] if e['offering_id']=='o149')
    i=verified['result']['entries'].index(e)
    free=free_resources(verified,e['day'],e['slot'])['classrooms']
    assert free
    changed,errors=edit_result(verified,[SimpleNamespace(entry_index=i,day=e['day'],slot=e['slot'],room_id=free[0]['id'])])
    assert not errors
    copies=[x for x in changed['entries'] if x['offering_id'] in ('o149','o150') and (x['day'],x['slot'])==(e['day'],e['slot'])]
    assert len(copies)==2 and all(x['room_id']==free[0]['id'] for x in copies)
    other=next(x for x in verified['result']['entries'] if x['offering_id']=='o155' and (x['day'],x['slot'])==(e['day'],e['slot']))
    bad,errors=edit_result(verified,[SimpleNamespace(entry_index=i,day=e['day'],slot=e['slot'],room_id=other['room_id'])])
    assert bad is None and any('room ' in v for v in errors)

def test_exports_combined_option_once_per_teacher(verified):
    from app.exports import views,excel,pdf
    from openpyxl import load_workbook
    from pypdf import PdfReader
    from io import BytesIO
    output=views(verified,'teacher','t24')
    text='\n'.join(cell for title,grid,hours in output for row in grid for cell in row)
    assert text.count('COMBINED A+B ELECTIVE')==3
    assert len(load_workbook(BytesIO(excel(verified))).worksheets)==8
    assert len(PdfReader(BytesIO(pdf(verified))).pages)>=8

def test_api_preserves_academic_data_and_expands_elective_scope(tmp_path,monkeypatch):
    import shutil
    from fastapi.testclient import TestClient
    from app.main import app
    db=tmp_path/'test.db';shutil.copyfile('data/unisched.db',db)
    monkeypatch.setenv('UNISCHED_DB',str(db))
    with TestClient(app) as client:
        original=client.get('/api/config').json()
        response=client.post('/api/generations',json={'name':'Verified regression','time_limit':5})
        assert response.status_code==200,response.text
        saved=response.json();assert saved['result']['status']=='feasible'
        assert client.get('/api/config').json()==original
        audit=client.get(f"/api/generations/{saved['id']}/analytics").json()
        assert audit['hard_conflicts']==0
        response=client.get(f"/api/generations/{saved['id']}/availability?day=0&slot=0&duration=2")
        assert response.status_code==200
        assert client.get(f"/api/generations/{saved['id']}/availability?day=0&slot=3&duration=2").status_code==422
        response=client.post('/api/generations',json={'name':'Combined scope','time_limit':5,'group_ids':['g7'],'continue_latest':False})
        assert response.status_code==200,response.text
        result=response.json()['result']
        assert result['status']=='feasible',result
        assert result['scope']['target_group_ids']==['g7','g8']
