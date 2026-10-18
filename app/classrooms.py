"""Measure classroom continuity without weakening mandatory scheduling rules."""
from collections import defaultdict
from .calendar import minutes


def classroom_metrics(config, entries):
    preferred=config.settings.classroom_run_length
    periods=config.settings.periods()
    lectures=defaultdict(dict)
    for e in entries:
        if e['kind']=='lecture':
            for p in range(e['slot'],e['slot']+e['duration']):
                lectures[e['group_id'],e['day']][p]=e['room_id']
    changes=[]
    for (group,day),slots in lectures.items():
        run=0;previous=None;previous_slot=None
        for p,room in sorted(slots.items()):
            adjacent=previous_slot is not None and p==previous_slot+1 and periods[previous_slot][1]==periods[p][0]
            if adjacent and previous!=room:
                changes.append({'group_id':group,'day':day,'slot':p,'from_room':previous,'to_room':room,
                                'preceding_periods':run,'shortfall':max(0,preferred-run)})
            run=run+1 if adjacent and previous==room else 1
            previous,previous_slot=room,p
    return {'preferred_periods':preferred,'classroom_changes':len(changes),
            'early_changes':sum(c['shortfall']>0 for c in changes) if preferred>1 else 0,
            'shortfall_periods':sum(c['shortfall'] for c in changes) if preferred>1 else 0,
            'changes':changes,
            'note':'Preference applies to consecutive lecture periods within each division. Labs, projects, recess, and free periods reset the run. Capacity, collisions, student continuity, and daily balance take priority.'}


def optimize_classrooms(config, entries, locked_entries, time_limit):
    """Reassign lecture rooms while holding every day/time/teacher/batch fixed."""
    from copy import deepcopy
    from ortools.sat.python import cp_model
    from .resources import eligible_rooms
    if config.settings.classroom_run_length<=1:
        return entries,False
    model=cp_model.CpModel();rooms={r.id:i+1 for i,r in enumerate(config.rooms)}
    offerings={o.id:o for o in config.offerings};bookings=defaultdict(list);slots=defaultdict(dict)
    fixed={(e['offering_id'],e['kind'],e['day'],e['slot']):e['room_id'] for e in locked_entries}
    choices=[]
    for i,e in enumerate(entries):
        if e['kind']!='lecture':
            for p in range(e['slot'],e['slot']+e['duration']): bookings[e['room_id'],e['day'],p].append(1)
            continue
        eligible=eligible_rooms(config,offerings[e['offering_id']],'lecture')
        fixed_room=fixed.get((e['offering_id'],e['kind'],e['day'],e['slot']))
        if fixed_room: eligible=[r for r in eligible if r.id==fixed_room]
        variables=[]
        for room in eligible:
            v=model.NewBoolVar(f'placement_{i}_{room.id}');variables.append((v,room.id));choices.append((i,v,room.id))
            model.AddHint(v, int(room.id==e['room_id']))
            for p in range(e['slot'],e['slot']+e['duration']): bookings[room.id,e['day'],p].append(v)
        model.Add(sum(v for v,r in variables)==1)
        code=model.NewIntVar(1,len(rooms),f'room_{i}')
        model.Add(code==sum(rooms[r]*v for v,r in variables))
        for p in range(e['slot'],e['slot']+e['duration']): slots[e['group_id'],e['day']][p]=code
    for variables in bookings.values(): model.Add(sum(variables)<=1)
    periods=config.settings.periods();preferred=config.settings.classroom_run_length
    changes=[];shortfalls=[]
    for lecture_slots in slots.values():
        last_slot=last_room=last_run=None
        for p,code in sorted(lecture_slots.items()):
            run=model.NewIntVar(1,preferred,'room_run')
            if last_slot is None or p!=last_slot+1 or periods[last_slot][1]!=periods[p][0]:
                model.Add(run==1)
            else:
                change=model.NewBoolVar('room_change')
                model.Add(code!=last_room).OnlyEnforceIf(change)
                model.Add(code==last_room).OnlyEnforceIf(change.Not())
                extended=model.NewIntVar(1,preferred,'extended_run')
                model.AddMinEquality(extended,[last_run+1,preferred])
                model.Add(run==1).OnlyEnforceIf(change)
                model.Add(run==extended).OnlyEnforceIf(change.Not())
                shortfall=model.NewIntVar(0,preferred-1,'shortfall')
                model.Add(shortfall==preferred-last_run).OnlyEnforceIf(change)
                model.Add(shortfall==0).OnlyEnforceIf(change.Not())
                changes.append(change);shortfalls.append(shortfall)
            last_slot,last_room,last_run=p,code,run
    model.Minimize(sum(shortfalls)*(len(changes)+1)+sum(changes))
    solver=cp_model.CpSolver();solver.parameters.max_time_in_seconds=max(.001,time_limit)
    solver.parameters.num_search_workers=4
    result=solver.Solve(model)
    if result not in (cp_model.FEASIBLE,cp_model.OPTIMAL): return entries,False
    updated=deepcopy(entries)
    for i,v,r in choices:
        if solver.BooleanValue(v): updated[i]['room_id']=r
    before=classroom_metrics(config,entries);after=classroom_metrics(config,updated)
    if (after['shortfall_periods'],after['classroom_changes'])>(before['shortfall_periods'],before['classroom_changes']):
        return entries,False
    return updated,result==cp_model.OPTIMAL
