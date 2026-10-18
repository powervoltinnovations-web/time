from copy import deepcopy
from io import BytesIO
import json
from urllib.error import HTTPError
import pytest
from fastapi.testclient import TestClient
from app import assistant,storage
from app.analytics import analyze
from app.domain import Configuration
from app.main import app
from app.scheduler import generate
from test_scheduler import small_config


@pytest.fixture
def config():
    data=small_config().model_dump()
    data['groups'][0]['room_id']=None
    data['rooms'] += [{**data['rooms'][0],'id':'r2','name':'Room 2'},
                      {**data['rooms'][0],'id':'r3','name':'Room 3'},
                      {**data['rooms'][0],'id':'tiny','name':'Small room','capacity':20}]
    data['offerings'][0].update(lectures=4,labs=0)
    for i in (2,3):
        data['subjects'].append({**data['subjects'][0],'id':f's{i}','code':f'S{i}','name':f'Subject {i}'})
        data['offerings'].append({**data['offerings'][0],'id':f'o{i}','subject_id':f's{i}'})
    return Configuration(**data)


def solved(config):
    result=generate(config,20,random_seed=42)
    assert result['status']=='feasible',result
    record={'id':1,'name':'Classroom plan','config':config.model_dump(),'result':result}
    assert analyze(record)['hard_conflicts']==0
    return record


@pytest.mark.parametrize('preference',[2,3])
def test_classroom_runs_are_optimized_and_all_hard_constraints_remain(config,preference):
    config.settings.classroom_run_length=preference
    record=solved(config)
    quality=record['result']['summary']['classroom_optimization']
    assert quality['preferred_periods']==preference
    assert quality['classroom_changes']==quality['early_changes']==0
    assert quality['optimal'] is True
    assert analyze(record)['internal_gaps']==0


def test_unavoidable_room_switches_reported_without_relaxing_locks(config):
    data=config.model_dump();data['settings'].update(days=['Monday','Tuesday'],classroom_run_length=3)
    data['rooms']=[r for r in data['rooms'] if r['id'] in ('r','r2')]
    data['subjects']=data['subjects'][:1]
    data['offerings']=data['offerings'][:1];data['offerings'][0]['lectures']=6;data['offerings'][0]['lab_room_id']=None
    data['teachers'].append({**data['teachers'][0],'id':'t2','name':'Teacher 2'})
    data['groups'].append({**data['groups'][0],'id':'g2','division':'B'})
    data['offerings'].append({**data['offerings'][0],'id':'o2','group_id':'g2','teacher_id':'t2'})
    c=Configuration(**data)
    locked=[{'offering_id':'o2','group_id':'g2','subject_id':'s','teacher_id':'t2','kind':'lecture','batch_id':None,
             'day':d,'slot':p,'duration':1,'room_id':'r' if p%2==0 else 'r2'} for d in (0,1) for p in range(3)]
    r=generate(c,20,target_group_ids=['g'],locked_entries=locked,random_seed=42)
    assert r['status']=='feasible',r
    assert [e for e in r['entries'] if e['group_id']=='g2']==locked
    assert r['summary']['classroom_optimization']['early_changes']>0
    assert analyze({'config':c.model_dump(),'result':r})['hard_conflicts']==0


@pytest.fixture
def client(config,tmp_path,monkeypatch):
    monkeypatch.setenv('UNISCHED_DB',str(tmp_path/'assistant.db'))
    monkeypatch.delenv('UNISCHED_OPENAI_API_KEY',raising=False)
    storage.initialize();storage.save_config(config.model_dump(),0)
    with TestClient(app) as client: yield client


def test_generation_preference_is_saved_per_version_and_base_must_match(client):
    a=client.post('/api/generations',json={'classroom_run_length':3}).json()
    assert a['result']['status']=='feasible'
    assert a['config']['settings']['classroom_run_length']==3
    assert client.get('/api/config').json()['configuration']['settings']['classroom_run_length']==1
    b=client.post('/api/generations',json={'classroom_run_length':2}).json()
    assert b['result']['scope']['base_generation_id'] is None
    c=client.post('/api/generations',json={'classroom_run_length':2}).json()
    assert c['result']['scope']['base_generation_id']==b['id']
    assert client.post('/api/generations',json={'classroom_run_length':2,'base_generation_id':a['id']}).status_code==409


def test_advice_checks_full_plan_capacity_and_never_mutates(config):
    record=solved(config);original=deepcopy(record)
    first=assistant.room_options(record,0)
    assert len(first['alternatives'])==2
    assert any('seats' in ' '.join(r['reasons']) for r in first['rejected'] if r['room_id']=='tiny')
    used=first['alternatives'][0]['room_id']
    data=record['config'];data['teachers'].append({**data['teachers'][0],'id':'t2','name':'Teacher 2'})
    data['groups'].append({**data['groups'][0],'id':'g2','division':'B','room_id':used})
    data['offerings'].append({**data['offerings'][0],'id':'other','group_id':'g2','teacher_id':'t2','lectures':1})
    record['result']['entries'].append({**record['result']['entries'][0],'group_id':'g2','offering_id':'other','teacher_id':'t2','room_id':used})
    assert analyze(record)['hard_conflicts']==0
    snapshot=deepcopy(record)
    text,facts=assistant.local_advice([record],'Is there a replacement classroom?',0)
    assert 'Verified replacement rooms' in text
    assert used not in {r['room_id'] for r in facts['room_check']['alternatives']}
    assert any('occupied' in ' '.join(r['reasons']) for r in facts['room_check']['rejected'] if r['room_id']==used)
    assert record==snapshot
    assert original['result']['entries'][0]==record['result']['entries'][0]


def test_assistant_scope_validation_and_offline_fallback(client):
    assert client.post('/api/assistant/ask',json={'question':'Explain conflicts'}).status_code==422
    first=client.post('/api/generations',json={}).json()
    second=client.post('/api/generations',json={}).json()
    before=client.get('/api/generations').json()
    assert client.post('/api/assistant/ask',json={'question':'room','entry_index':0}).status_code==422
    assert client.post('/api/assistant/ask',json={'question':'room','generation_id':999}).status_code==404
    assert client.post('/api/assistant/ask',json={'question':'room','generation_id':first['id'],'entry_index':999}).status_code==422
    response=client.post('/api/assistant/ask',json={'question':'Explain conflicts and faculty workload'}).json()
    assert len(response['facts']['plans'])==2
    assert all(p['hard_conflicts']==0 for p in response['facts']['plans'])
    assert 'Highest teaching loads' in response['answer']
    response=client.post('/api/assistant/ask',json={'question':'replacement room','generation_id':first['id'],'entry_index':0,'mode':'openai'}).json()
    assert response['mode']=='local' and response['online_error']
    assert 'Verified replacement rooms' in response['answer']
    assert client.get('/api/generations').json()==before
    assert client.get(f"/api/generations/{first['id']}").json()==first
    assert client.get('/api/assistant/status').json()['online_available'] is False


def test_openai_adapter_sends_only_selected_facts_and_handles_service_errors(monkeypatch):
    monkeypatch.setenv('UNISCHED_OPENAI_API_KEY','test-key-not-real')
    facts={'plans':[{'id':3,'name':'Selected plan'}],'room_check':None}
    captured=[]
    def reply(request,timeout):
        captured.append(json.loads(request.data))
        assert timeout==30 and request.full_url=='https://api.openai.com/v1/responses'
        return BytesIO(json.dumps({'output':[{'content':[{'type':'output_text','text':'Verified explanation.'}]}]}).encode())
    monkeypatch.setattr(assistant,'urlopen',reply)
    assert assistant.explain_with_openai('Explain this plan',facts)=='Verified explanation.'
    assert captured[0]['store'] is False
    assert json.loads(captured[0]['input'])['verified_facts']==facts
    assert 'test-key' not in json.dumps(captured)
    def fail(*args,**kwargs):raise HTTPError('https://api.openai.com',401,'secret error body',{},None)
    monkeypatch.setattr(assistant,'urlopen',fail)
    with pytest.raises(ValueError,match='API key was rejected') as exc:
        assistant.explain_with_openai('Explain this plan',facts)
    assert 'secret error body' not in str(exc.value)
