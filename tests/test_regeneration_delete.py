from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from app import storage, scheduler
from app.main import app, generation_lock
from app.domain import Configuration
from app.analytics import analyze
from app.classrooms import interchangeable_classrooms
from test_scheduler import small_config


@pytest.fixture
def config():
    c=small_config();c.settings.classroom_run_length=3;c.groups[0].room_id=None
    c.rooms.append(c.rooms[0].model_copy(update={'id':'r2','name':'302'}))
    return c


@pytest.fixture
def client(config,tmp_path,monkeypatch):
    monkeypatch.setenv('UNISCHED_DB',str(tmp_path/'repeat-delete.db'))
    storage.initialize();storage.save_config(config.model_dump(),0)
    with TestClient(app) as c: yield c


def make(client):
    response=client.post('/api/generations',json={'classroom_run_length':3})
    assert response.status_code==200,response.text
    result=response.json();assert result['result']['status']=='feasible',result
    return result


def remove(client,record):
    return client.request('DELETE',f"/api/generations/{record['id']}",json={'revision':record['workflow']['revision']})


def test_regeneration_revalidates_existing_plan_without_another_search(client,monkeypatch):
    first=make(client);before=client.get('/api/config').json()
    def unexpected(*args,**kwargs):raise AssertionError('Compatible regeneration should not repeat CP-SAT search')
    monkeypatch.setattr(scheduler.cp_model.CpSolver,'Solve',unexpected)
    second=make(client)
    assert second['id']!=first['id']
    assert second['result']['summary']['reused_placements']
    assert second['result']['entries']==first['result']['entries']
    assert second['result']['scope']['seed_generation_id']==first['id']
    assert client.get(f"/api/generations/{first['id']}").json()==first
    assert client.get('/api/config').json()==before
    assert analyze(second)['hard_conflicts']==0


def test_fresh_request_and_changed_data_do_not_reuse(client):
    make(client)
    fresh=client.post('/api/generations',json={'classroom_run_length':3,'continue_latest':False}).json()
    assert fresh['result']['status']=='feasible'
    assert not fresh['result']['summary']['reused_placements']
    cfg=client.get('/api/config').json();cfg['configuration']['offerings'][0]['lectures']=6
    assert client.put('/api/config',json=cfg).status_code==200
    changed=make(client)
    assert not changed['result']['summary']['reused_placements']
    assert changed['result']['scope']['seed_generation_id'] is None
    assert sum(e['kind']=='lecture' for e in changed['result']['entries'])==6


def test_invalid_or_incomplete_seed_is_never_accepted(config):
    first=scheduler.generate(config,20)
    assert first['status']=='feasible'
    bad=deepcopy(first['entries']);bad.pop()
    repaired=scheduler.generate(config,20,initial_entries=bad)
    assert repaired['status']=='feasible'
    assert not repaired['summary']['reused_placements']
    assert analyze({'config':config.model_dump(),'result':repaired})['hard_conflicts']==0


def test_pool_is_used_only_for_interchangeable_unreserved_lecture_rooms(config):
    assert len(interchangeable_classrooms(config,[]))==2
    assert interchangeable_classrooms(config,[{'room_id':'r'}]) is None
    config.offerings[0].projects=1;config.offerings[0].project_room_id='r'
    assert interchangeable_classrooms(config,[]) is None
    config.offerings[0].projects=0;config.groups[0].room_id='r'
    assert interchangeable_classrooms(config,[]) is None


def test_delete_only_selected_version_and_workflow_preserving_data_and_descendants(client):
    first=make(client);second=make(client)
    # Parent references are provenance; each child contains its own full snapshot.
    second_before=deepcopy(second)
    second['result']['parent_generation_id']=first['id']
    child_id=storage.save_generation('Independent child',second['config_revision'],second['config'],second['result'])
    child=client.get(f'/api/generations/{child_id}').json()
    before=client.get('/api/config').json()
    assert client.patch(f"/api/generations/{first['id']}/workflow",json={'revision':0,'action':'lock'}).status_code==200
    locked=client.get(f"/api/generations/{first['id']}").json()
    assert remove(client,locked).status_code==409
    unlocked=client.patch(f"/api/generations/{first['id']}/workflow",json={'revision':1,'action':'unlock'}).json()
    assert remove(client,first).status_code==409  # stale revision
    assert remove(client,unlocked).status_code==200
    assert client.get(f"/api/generations/{first['id']}").status_code==404
    assert client.get(f"/api/generations/{first['id']}/export/pdf").status_code==404
    assert client.get(f"/api/generations/{second['id']}").json()==second_before
    # The real second version and descendant are not cascaded or rewritten.
    assert client.get(f"/api/generations/{second['id']}").status_code==200
    assert client.get(f'/api/generations/{child_id}').json()==child
    assert client.get('/api/config').json()==before
    with storage.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM generation_workflow WHERE generation_id=?',(first['id'],)).fetchone()[0]==0
    assert remove(client,unlocked).status_code==404


def test_approved_and_busy_generation_are_protected_but_failed_reports_can_delete(client):
    first=make(client)
    approved=client.patch(f"/api/generations/{first['id']}/workflow",json={'revision':0,'action':'approve'}).json()
    assert remove(client,approved).status_code==409
    draft=client.patch(f"/api/generations/{first['id']}/workflow",json={'revision':1,'action':'draft'}).json()
    generation_lock.acquire()
    try: assert remove(client,draft).status_code==409
    finally: generation_lock.release()
    assert remove(client,draft).status_code==200
    failed_id=storage.save_generation('Timeout report',1,first['config'],{'status':'timeout','entries':[],'issues':[],'summary':{}})
    failed=client.get(f'/api/generations/{failed_id}').json()
    assert remove(client,failed).status_code==200
    assert client.get('/api/generations').json()==[]
    assert client.get('/api/performance').status_code==200
    assert client.post('/api/assistant/ask',json={'question':'Which room?','generation_id':first['id']}).status_code==404


def test_full_nine_division_room_pool_is_complete_and_continuous():
    from app.demo import presentation_config
    c=presentation_config();c.settings.classroom_run_length=3
    result=scheduler.generate(c,20,random_seed=7)
    assert result['status']=='feasible',result
    assert {e['group_id'] for e in result['entries']}=={g.id for g in c.groups}
    audit=analyze({'config':c.model_dump(),'result':result})
    assert audit['hard_conflicts']==audit['internal_gaps']==0
    # Independently inspect each continuous lecture block, across subject changes.
    from collections import defaultdict
    blocks=defaultdict(list)
    for e in result['entries']:
        if e['kind']=='lecture': blocks[e['group_id'],e['day']].append(e)
    periods=c.settings.periods()
    for lectures in blocks.values():
        ordered=sorted(lectures,key=lambda e:e['slot'])
        for a,b in zip(ordered,ordered[1:]):
            if a['slot']+a['duration']==b['slot'] and periods[b['slot']-1][1]==periods[b['slot']][0]:
                assert a['room_id']==b['room_id']
