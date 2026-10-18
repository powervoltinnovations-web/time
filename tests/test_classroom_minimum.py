"""Minimum room stay: independent fixtures for early, permitted, and reset changes."""
import pytest
from ortools.sat.python import cp_model
from app.classrooms import require_classroom_runs
from test_scheduler import small_config


@pytest.mark.parametrize('minimum,placements,feasible',[
    (2,[(0,'r'),(1,'r2')],False),
    (2,[(0,'r'),(1,'r'),(2,'r2'),(3,'r')],False),
    (2,[(0,'r'),(1,'r'),(2,'r2'),(3,'r2')],True),
    (2,[(0,'r'),(1,'r'),(2,'r2')],True),
    (2,[(3,'r'),(4,'r2')],True),  # Recess resets the minimum.
    (2,[(0,'r'),(2,'r2')],True),  # A non-lecture period resets it.
    (3,[(0,'r'),(1,'r2'),(2,'r')],False),
    (3,[(0,'r'),(1,'r'),(2,'r2'),(3,'r2')],False),
    (3,[(0,'r'),(1,'r'),(2,'r'),(3,'r2')],True),
    (3,[(0,'r'),(1,'r'),(2,'r'),(3,'r')],True),
    (3,[(0,'r'),(1,'r')],True),  # A shorter final block does not invent lectures.
    (3,[(2,'r'),(3,'r'),(4,'r2'),(5,'r2')],True),  # Recess.
    (3,[(0,'r'),(1,'r'),(4,'r2')],True),  # Non-lecture periods reset the run.
])
def test_minimum_room_run_at_generation_time(minimum,placements,feasible):
    config=small_config();config.settings.classroom_run_length=minimum
    config.rooms.append(config.rooms[0].model_copy(update={'id':'r2'}))
    model=cp_model.CpModel();enabled=model.NewBoolVar('enabled');model.Add(enabled==1)
    candidates=[]
    for slot,room in placements:
        var=model.NewBoolVar('chosen');model.Add(var==1)
        candidates.append((var,{'group_id':'g','day':0,'slot':slot,'duration':1,'room_id':room,'kind':'lecture'}))
    require_classroom_runs(model,config,candidates,{'g'},enabled)
    status=cp_model.CpSolver().Solve(model)
    assert (status in (cp_model.OPTIMAL,cp_model.FEASIBLE))==feasible


@pytest.mark.parametrize('minimum',[2,3])
def test_joint_rescheduling_repairs_a_room_only_seed(monkeypatch,minimum):
    from app import scheduler
    from app.classrooms import classroom_metrics
    from app.analytics import analyze
    config=small_config();config.settings.classroom_run_length=minimum
    config.groups[0].room_id=None
    config.offerings[0].lectures=12;config.offerings[0].labs=0
    config.rooms.append(config.rooms[0].model_copy(update={'id':'r2','name':'302'}))
    original_optimizer=scheduler.optimize_classrooms
    calls=[]
    def room_phase(c,entries,locked,budget):
        calls.append(True)
        if len(calls)==1:
            # Simulate a room-only phase unable to resolve an early change.
            from copy import deepcopy
            seed=deepcopy(entries)
            pair=next((a,b) for a,b in zip(seed,seed[1:]) if a['day']==b['day'] and a['slot']+1==b['slot'] and b['slot']!=4)
            pair[0]['room_id']='r';pair[1]['room_id']='r2'
            return seed,False
        return original_optimizer(c,entries,locked,budget)
    monkeypatch.setattr(scheduler,'interchangeable_classrooms',lambda *_:None)
    monkeypatch.setattr(scheduler,'optimize_classrooms',room_phase)
    result=scheduler.generate(config,20,random_seed=42)
    assert result['status']=='feasible',result
    assert len(calls)==2  # The joint time/room fallback actually ran.
    assert classroom_metrics(config,result['entries'])['early_changes']==0
    assert analyze({'config':config.model_dump(),'result':result})['hard_conflicts']==0


def test_two_lecture_minimum_repairs_reused_placements():
    from app.scheduler import generate
    from app.analytics import analyze
    from app.classrooms import classroom_metrics
    config=small_config();config.settings.classroom_run_length=2
    config.groups[0].room_id=None
    config.offerings[0].lectures=12;config.offerings[0].labs=0
    config.rooms.append(config.rooms[0].model_copy(update={'id':'r2','name':'302'}))
    original=generate(config,20,random_seed=42)
    assert original['status']=='feasible',original
    seed=[dict(e) for e in original['entries']]
    pair=next((a,b) for a,b in zip(seed,seed[1:]) if a['day']==b['day'] and a['slot']+1==b['slot'] and b['slot']!=4)
    pair[0]['room_id']='r';pair[1]['room_id']='r2'
    assert classroom_metrics(config,seed)['early_changes']>0
    result=generate(config,20,random_seed=42,initial_entries=seed)
    assert result['status']=='feasible',result
    assert result['summary']['reused_placements']
    assert result['summary']['classroom_optimization']['minimum_run_enforced']
    assert classroom_metrics(config,result['entries'])['early_changes']==0
    assert analyze({'config':config.model_dump(),'result':result})['hard_conflicts']==0
