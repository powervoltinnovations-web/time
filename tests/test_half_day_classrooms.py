"""Every working day needs distinct consecutive lectures in each half."""
from collections import Counter
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from ortools.sat.python import cp_model

from app import storage
from app.analytics import analyze
from app.classrooms import require_half_day_pairs, missing_half_day_pairs
from app.main import app
from app.scheduler import generate
from test_scheduler import small_config


def half_day_config(pool=True):
    config=small_config()
    config.settings.classroom_run_length=2
    config.settings.classroom_pairs_each_half=True
    config.teachers[0].max_hours=40
    config.offerings[0].lectures=20
    config.offerings[0].labs=5
    if pool:
        config.groups[0].room_id=None
        config.rooms.append(config.rooms[0].model_copy(update={'id':'r2','name':'302'}))
    return config


def assert_daily_pairs(config,result):
    assert result['status']=='feasible',result
    entries=result['entries']
    # Independent check of all ten halves; a double-period session alone is not a pair.
    for day in range(5):
        for start,end in ((0,4),(4,8)):
            lectures=[e for e in entries if e['group_id']=='g' and e['day']==day
                      and e['kind']=='lecture' and start<=e['slot']<end
                      and e['slot']+e['duration']<=end]
            assert any(a['slot']+a['duration']==b['slot'] and a['room_id']==b['room_id']
                       for a in lectures for b in lectures if a is not b),(day,start,lectures)
    assert Counter(e['kind'] for e in entries if e['group_id']=='g')=={'lecture':20,'lab':5}
    assert analyze({'config':config.model_dump(),'result':result})['hard_conflicts']==0
    assert result['summary']['classroom_optimization']['pairs_each_half_enforced']


@pytest.mark.parametrize('pool',[False,True])
def test_five_days_both_halves_keep_pairs_and_exact_weekly_counts(pool):
    config=half_day_config(pool);before=config.model_dump()
    assert_daily_pairs(config,generate(config,20,random_seed=42))
    assert config.model_dump()==before


def test_reused_morning_only_lectures_are_rescheduled():
    config=half_day_config()
    base={'offering_id':'o','group_id':'g','subject_id':'s','teacher_id':'t','batch_id':None}
    seed=[]
    for day in range(5):
        seed.extend({**base,'day':day,'slot':slot,'duration':1,'room_id':'r','kind':'lecture'} for slot in range(4))
        seed.append({**base,'day':day,'slot':4,'duration':2,'room_id':'l','kind':'lab'})
    before=deepcopy(seed)
    assert analyze({'config':config.model_dump(),'result':{'status':'feasible','entries':seed}})['hard_conflicts']==0
    assert len(missing_half_day_pairs(config,seed,{'g'}))==5
    result=generate(config,20,random_seed=42,initial_entries=seed)
    assert_daily_pairs(config,result)
    assert not result['summary']['reused_placements']
    assert seed==before


def test_insufficient_lectures_are_explained_without_inventing_sessions():
    config=half_day_config();config.offerings[0].lectures=19
    result=generate(config,20)
    assert result['status']=='infeasible'
    assert result['entries']==[]
    assert result['issues'][0]['code']=='HALF_DAY_CLASSROOM_PAIRS'
    assert 'at least 20' in result['issues'][0]['problem']
    assert 'It has 19' in result['issues'][0]['problem']
    assert config.offerings[0].lectures==19


@pytest.mark.parametrize('afternoon,duration,feasible',[
    ([(4,'r'),(5,'r')],1,True),
    ([(4,'r'),(5,'r2')],1,False),
    ([(4,'r'),(6,'r')],1,False),
    ([(4,'r')],2,False),
    ([(4,'r'),(6,'r')],2,True),
])
def test_halves_require_distinct_adjacent_sessions_in_the_same_room(afternoon,duration,feasible):
    config=half_day_config();config.settings.lecture_slots=duration
    model=cp_model.CpModel();candidates=[]
    for day in range(5):
        for slot,room in [(0,'r'),(duration,'r')]+afternoon:
            var=model.NewBoolVar('chosen');model.Add(var==1)
            candidates.append((var,{'group_id':'g','day':day,'slot':slot,'duration':duration,'room_id':room,'kind':'lecture'}))
    require_half_day_pairs(model,config,candidates,{'g'})
    assert (cp_model.CpSolver().Solve(model) in (cp_model.OPTIMAL,cp_model.FEASIBLE))==feasible


@pytest.mark.parametrize('alternating',[False,True])
def test_room_can_change_at_recess_while_preserved_division_stays_fixed(alternating):
    config=half_day_config()
    config.teachers.append(config.teachers[0].model_copy(update={'id':'t2','name':'Teacher 2'}))
    config.groups.append(config.groups[0].model_copy(update={'id':'g2','division':'B'}))
    config.offerings.append(config.offerings[0].model_copy(update={
        'id':'o2','group_id':'g2','teacher_id':'t2','lectures':30,'labs':0}))
    locked=[{'offering_id':'o2','group_id':'g2','subject_id':'s','teacher_id':'t2','batch_id':None,
             'day':day,'slot':slot,'duration':1,'room_id':'r2' if slot<4 else 'r','kind':'lecture'}
            for day in range(5) for slot in range(6)]
    if alternating:
        for e in locked:
            e['room_id']='r' if e['slot']%2 else 'r2'
    result=generate(config,20,target_group_ids=['g'],locked_entries=locked,random_seed=42)
    if alternating:
        assert result['status']=='infeasible',result
        assert result['entries']==[]
        assert 'HALF_DAY_CLASSROOM_PAIRS' in {i['code'] for i in result['issues']}
        return
    assert_daily_pairs(config,result)
    assert [e for e in result['entries'] if e['group_id']=='g2']==locked
    assert all(e['room_id']==('r' if e['slot']<4 else 'r2')
               for e in result['entries'] if e['group_id']=='g' and e['kind']=='lecture')


def test_api_saves_and_reuses_the_each_half_requirement(tmp_path,monkeypatch):
    monkeypatch.setenv('UNISCHED_DB',str(tmp_path/'halves.db'))
    config=half_day_config();config.settings.classroom_pairs_each_half=False
    storage.initialize();storage.save_config(config.model_dump(),0)
    with TestClient(app) as client:
        payload={'classroom_run_length':2,'classroom_pairs_each_half':True,'time_limit':20}
        first=client.post('/api/generations',json=payload)
        assert first.status_code==200,first.text
        record=first.json()
        assert record['config']['settings']['classroom_pairs_each_half']
        assert_daily_pairs(config,record['result'])
        second=client.post('/api/generations',json=payload).json()
        assert_daily_pairs(config,second['result'])
        assert second['result']['summary']['reused_placements']
        assert not client.get('/api/config').json()['configuration']['settings']['classroom_pairs_each_half']


def test_missing_afternoon_availability_is_not_accepted():
    config=half_day_config()
    config.offerings[0].labs=0
    config.teachers[0].departure='13:00'
    result=generate(config,20,random_seed=42)
    assert result['status']=='infeasible',result
    assert result['entries']==[]
    assert 'HALF_DAY_CLASSROOM_PAIRS' in {i['code'] for i in result['issues']}


def test_each_half_requirement_also_works_with_flexible_rooms():
    config=half_day_config()
    config.settings.classroom_run_length=1
    assert_daily_pairs(config,generate(config,20,random_seed=42))
