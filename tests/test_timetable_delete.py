"""Deleting a saved timetable must not delete academic data or other versions."""
import pytest
from fastapi.testclient import TestClient
from app import storage
from app.main import app, generation_lock
from test_scheduler import small_config


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('UNISCHED_DB',str(tmp_path/'delete.db'))
    storage.initialize();storage.save_config(small_config().model_dump(),0)
    with TestClient(app) as client: yield client


def saved(client):
    response=client.post('/api/generations',json={'name':'Delete test'})
    assert response.status_code==200,response.text
    assert response.json()['result']['status']=='feasible'
    return response.json()


def test_deletes_only_selected_version_and_workflow(client):
    first=saved(client);second=saved(client)
    config=client.get('/api/config').json()
    # Exercise workflow row cleanup and allow an explicitly confirmed approved version.
    response=client.patch(f"/api/generations/{first['id']}/workflow",json={'revision':0,'action':'approve'})
    assert response.status_code==200
    response=client.delete(f"/api/generations/{first['id']}?revision=1")
    assert response.status_code==200,response.text
    assert response.json()=={'deleted':first['id']}
    assert client.get(f"/api/generations/{first['id']}").status_code==404
    assert client.get(f"/api/generations/{first['id']}/export/pdf").status_code==404
    assert client.get(f"/api/generations/{second['id']}").json()==second
    assert client.get('/api/config').json()==config
    assert [g['id'] for g in client.get('/api/generations').json()]==[second['id']]
    with storage.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM generation_workflow WHERE generation_id=?',(first['id'],)).fetchone()[0]==0


def test_locked_and_stale_versions_are_protected_until_unlocked(client):
    record=saved(client);url=f"/api/generations/{record['id']}"
    assert client.patch(url+'/workflow',json={'revision':0,'action':'lock'}).status_code==200
    assert client.delete(url+'?revision=0').status_code==409
    response=client.delete(url+'?revision=1')
    assert response.status_code==409 and 'Unlock' in response.json()['detail']
    assert client.get(url).status_code==200
    assert client.patch(url+'/workflow',json={'revision':1,'action':'unlock'}).status_code==200
    assert client.delete(url+'?revision=1').status_code==409
    assert client.delete(url+'?revision=2').status_code==200
    assert client.delete(url+'?revision=2').status_code==404


def test_failed_generation_can_be_deleted_and_missing_ids_are_reported(client):
    config=storage.get_config()
    identifier=storage.save_generation('Failed attempt',config['revision'],config['configuration'],
                                       {'status':'infeasible','entries':[],'issues':[],'summary':{}})
    assert client.delete(f'/api/generations/{identifier}?revision=0').status_code==200
    assert client.get('/api/generations').json()==[]
    assert client.delete('/api/generations/99999?revision=0').status_code==404


def test_generation_in_progress_and_invalid_revisions_do_not_delete(client):
    record=saved(client);url=f"/api/generations/{record['id']}"
    assert client.delete(url).status_code==422
    assert client.delete(url+'?revision=-1').status_code==422
    with generation_lock:
        assert client.delete(url+'?revision=0').status_code==409
    assert client.get(url).status_code==200
    assert client.delete(url+'?revision=0').status_code==200
