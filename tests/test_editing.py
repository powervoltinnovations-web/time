from copy import deepcopy
from io import BytesIO
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from pypdf import PdfReader
import pytest
from app.main import app
from app import storage
from app.analytics import analyze
from app.scheduler import generate
from test_scheduler import small_config


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('UNISCHED_DB',str(tmp_path/'edits.db'))
    storage.initialize()
    storage.save_config(small_config().model_dump(),0)
    with TestClient(app) as client:yield client


@pytest.fixture
def record(client):
    response=client.post('/api/generations',json={'name':'Editable plan'})
    assert response.status_code==200
    record=response.json()
    assert record['result']['status']=='feasible'
    return record


def swap_days(record):
    return [{'entry_index':i,'day':1-e['day'],'slot':e['slot'],'room_id':e['room_id']}
            for i,e in enumerate(record['result']['entries']) if e['day'] in (0,1)]


def test_manual_edits_save_audited_draft_without_mutating_original(client,record):
    source=deepcopy(record)
    response=client.post(f"/api/generations/{record['id']}/edits",json={'revision':0,'changes':swap_days(record)})
    assert response.status_code==200,response.text
    edited=response.json()
    assert edited['id']!=record['id']
    assert edited['workflow']=={'state':'draft','locked':False,'revision':0}
    assert edited['result']['parent_generation_id']==record['id']
    assert edited['result']['summary']['balance_optimal'] is False
    assert edited['result']['source']=='manual'
    assert analyze(edited)['hard_conflicts']==0
    original=client.get(f"/api/generations/{record['id']}").json()
    assert original['result']==source['result'] and original['config']==source['config']
    assert original['workflow']['revision']==1
    assert len(client.get('/api/generations').json())==2
    assert len(client.get('/api/performance').json()['runs'])==1  # Edits are not solver benchmarks.
    # A second window holding the original workflow revision cannot silently branch a stale edit.
    assert client.post(f"/api/generations/{record['id']}/edits",json={'revision':0,'changes':swap_days(record)}).status_code==409


def test_lifecycle_locks_and_exports(client,record):
    url=f"/api/generations/{record['id']}/workflow"
    approved=client.patch(url,json={'revision':0,'action':'approve'}).json()
    assert approved['workflow']['state']=='approved'
    edits={'revision':1,'changes':swap_days(record)}
    assert client.post(f"/api/generations/{record['id']}/edits",json=edits).status_code==409
    locked=client.patch(url,json={'revision':1,'action':'lock'}).json()
    assert locked['workflow']=={'state':'approved','locked':True,'revision':2}
    assert client.patch(url,json={'revision':2,'action':'draft'}).status_code==409
    assert client.patch(url,json={'revision':0,'action':'unlock'}).status_code==409
    book=load_workbook(BytesIO(client.get(f"/api/generations/{record['id']}/export/xlsx").content))
    assert 'APPROVED' in book.active['A2'].value and 'LOCKED' in book.active['A2'].value
    text=''.join(p.extract_text() for p in PdfReader(BytesIO(client.get(f"/api/generations/{record['id']}/export/pdf").content)).pages)
    assert 'APPROVED' in text and 'LOCKED' in text
    assert client.patch(url,json={'revision':2,'action':'unlock'}).json()['workflow']['locked'] is False
    assert client.patch(url,json={'revision':3,'action':'draft'}).json()['workflow']['state']=='draft'
    assert client.post(f"/api/generations/{record['id']}/edits",json={'revision':4,'changes':swap_days(record)}).status_code==200


def test_invalid_manual_placements_leave_history_intact(client,record):
    entries=record['result']['entries']
    index=next(i for i,e in enumerate(entries) if e['kind']=='lab')
    lab=entries[index]
    cases=[{'entry_index':index,'day':6,'slot':0,'room_id':'l'},
           {'entry_index':index,'day':lab['day'],'slot':7,'room_id':'l'},
           {'entry_index':index,'day':lab['day'],'slot':3,'room_id':'l'},
           {'entry_index':index,'day':lab['day'],'slot':lab['slot'],'room_id':'r'},
           {'entry_index':index,'day':lab['day'],'slot':lab['slot'],'room_id':'missing'}]
    for change in cases:
        response=client.post(f"/api/generations/{record['id']}/edits",json={'revision':0,'changes':[change]})
        assert response.status_code==422,response.text
        assert len(client.get('/api/generations').json())==1
    index=next(i for i,e in enumerate(entries) if e['kind']=='lecture' and e['day']==0)
    e=entries[index]
    response=client.post(f"/api/generations/{record['id']}/edits",json={'revision':0,'changes':[{'entry_index':index,'day':1,'slot':e['slot'],'room_id':e['room_id']}]})
    assert response.status_code==422
    assert 'spread them across different days' in response.text
    assert client.get(f"/api/generations/{record['id']}").json()['result']==record['result']


def test_approval_rechecks_saved_plan(client,record):
    invalid=deepcopy(record['result']);invalid['entries'][0]['room_id']='l' if invalid['entries'][0]['kind']=='lecture' else 'r'
    identifier=storage.save_generation('Invalid plan',1,record['config'],invalid)
    response=client.patch(f'/api/generations/{identifier}/workflow',json={'revision':0,'action':'approve'})
    assert response.status_code==422
    assert 'Approval blocked' in response.text


def test_old_snapshot_retains_old_lecture_distribution(client):
    config=small_config().model_dump();config['settings']['spread_lectures']=False
    from app.domain import Configuration
    result=generate(Configuration(**config),10)
    config['settings'].pop('spread_lectures')
    identifier=storage.save_generation('Pre-upgrade timetable',1,config,result)
    old=client.get(f'/api/generations/{identifier}').json()
    assert old['workflow']=={'state':'draft','locked':False,'revision':0}
    assert old['config']['settings']['spread_lectures'] is False
    assert client.patch(f'/api/generations/{identifier}/workflow',json={'revision':0,'action':'approve'}).status_code==200
