"""Measure classroom continuity without weakening mandatory scheduling rules."""
from collections import defaultdict


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
            'note':(f'{preferred}-period minimum is enforced for newly generated divisions. Preserved historical divisions keep their existing rooms. ' if preferred>=2 else 'Room continuity is a preference. ')+'The rule applies within consecutive lecture blocks; labs, projects, recess, and free periods reset the run. A shorter block may end without adding lectures. Capacity, collisions, and student continuity remain enforced.'}


def optimize_classrooms(config, entries, locked_entries, time_limit):
    """Reassign lecture rooms while holding every day/time/teacher/batch fixed."""
    from copy import deepcopy
    from ortools.sat.python import cp_model
    from .resources import eligible_rooms, booking_key
    if config.settings.classroom_run_length<=1:
        return entries,False
    model=cp_model.CpModel();rooms={r.id:i+1 for i,r in enumerate(config.rooms)}
    offerings={o.id:o for o in config.offerings};bookings=defaultdict(list);slots=defaultdict(dict)
    fixed={(e['offering_id'],e['kind'],e['day'],e['slot']):e['room_id'] for e in locked_entries}
    choices=[]
    joint_bookings=set()
    for i,e in enumerate(entries):
        if e['kind']!='lecture':
            for p in range(e['slot'],e['slot']+e['duration']):
                key=(e['room_id'],e['day'],p,booking_key(config,offerings[e['offering_id']],e['kind']))
                if e['room_id'] and key not in joint_bookings:
                    bookings[e['room_id'],e['day'],p].append(1);joint_bookings.add(key)
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
    locked_groups={e['group_id'] for e in locked_entries}
    for (group,day),lecture_slots in slots.items():
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
                if preferred>=2 and group not in locked_groups:
                    model.Add(shortfall==0)
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


def require_classroom_runs(model, config, candidates, target_groups, enabled):
    """Constrain room changes while choosing times, not only after times are fixed.

    A lecture segment can finish before the requested minimum (e.g. before a lab).
    Within a continuing segment, switching rooms requires a complete run.
    Preserved divisions are historical bookings and are never rewritten here.
    """
    preferred=config.settings.classroom_run_length
    if preferred<2:
        return
    room_codes={r.id:i+1 for i,r in enumerate(config.rooms)}
    slots=defaultdict(list)
    for var,entry in candidates:
        if entry['kind']=='lecture' and entry['group_id'] in target_groups:
            for p in range(entry['slot'],entry['slot']+entry['duration']):
                slots[entry['group_id'],entry['day'],p].append((var,room_codes[entry['room_id']]))
    periods=config.settings.periods()
    for group in target_groups:
        for day in range(len(config.settings.days)):
            previous_room=previous_run=previous_active=None
            for p in range(len(periods)):
                choices=slots[group,day,p]
                active=model.NewBoolVar(f'lecture_active_{group}_{day}_{p}')
                model.Add(active==sum(v for v,_ in choices))
                room=model.NewIntVar(0,len(room_codes),'lecture_room')
                model.Add(room==sum(v*code for v,code in choices))
                run=model.NewIntVar(0,preferred,'lecture_room_run')
                model.Add(run==0).OnlyEnforceIf(active.Not())
                if p==0 or periods[p-1][1]!=periods[p][0]:
                    model.Add(run==1).OnlyEnforceIf(active)
                else:
                    same=model.NewBoolVar('same_lecture_room')
                    model.Add(room==previous_room).OnlyEnforceIf(same)
                    model.Add(room!=previous_room).OnlyEnforceIf(same.Not())
                    extended=model.NewIntVar(1,preferred,'extended_lecture_room_run')
                    model.AddMinEquality(extended,[previous_run+1,preferred])
                    model.Add(run==extended).OnlyEnforceIf([active,same])
                    model.Add(run==1).OnlyEnforceIf([active,same.Not()])
                    model.Add(previous_run>=preferred).OnlyEnforceIf([enabled,active,previous_active,same.Not()])
                previous_room,previous_run,previous_active=room,run,active


def interchangeable_classrooms(config, locked_entries):
    """Pool only lecture rooms with exactly identical eligibility and no other use."""
    from .resources import eligible_rooms, booking_key, session_specs
    pool=None
    for offering in config.offerings:
        if offering.lectures:
            eligible=eligible_rooms(config,offering,'lecture')
            ids={r.id for r in eligible}
            if len(ids)<2 or pool is not None and ids!={r.id for r in pool}:
                return None
            pool=eligible
    if not pool:
        return None
    ids={r.id for r in pool}
    if any(e['room_id'] in ids for e in locked_entries):
        return None
    for offering in config.offerings:
        for kind,count,_ in session_specs(config,offering):
            if kind!='lecture' and count and ids.intersection(r.id for r in eligible_rooms(config,offering,kind)):
                return None
    return pool


def allocate_classroom_blocks(config, entries, pool):
    """Color continuous lecture intervals; pool capacity guarantees enough rooms.

    Each complete lecture block keeps one room. Earliest-start interval coloring
    needs no more rooms than the maximum simultaneous lecture count.
    """
    from copy import deepcopy
    updated=deepcopy(entries);by_group=defaultdict(list);blocks=defaultdict(list)
    periods=config.settings.periods()
    for e in updated:
        if e['kind']=='lecture':
            by_group[e['group_id'],e['day']].append(e)
    for (group,day),lectures in by_group.items():
        current=[];end=None
        for e in sorted(lectures,key=lambda e:e['slot']):
            if current and (e['slot']!=end or periods[end-1][1]!=periods[e['slot']][0]):
                blocks[day].append(current);current=[]
            current.append(e);end=e['slot']+e['duration']
        if current: blocks[day].append(current)
    for day,items in blocks.items():
        free_at={r.id:0 for r in pool}
        for block in sorted(items,key=lambda b:(b[0]['slot'],b[0]['group_id'])):
            room=next((r.id for r in pool if free_at[r.id]<=block[0]['slot']),None)
            if room is None:
                raise ValueError('Lecture-room pool capacity was exceeded.')
            for e in block: e['room_id']=room
            free_at[room]=block[-1]['slot']+block[-1]['duration']
    return updated


def interchangeable_labs(config, locked_entries):
    """Collapse identical auto-assigned laboratories during time placement."""
    from .resources import eligible_rooms,session_specs
    pool=None
    for o in config.offerings:
        for kind,count,_ in session_specs(config,o):
            if not count: continue
            rooms=eligible_rooms(config,o,kind)
            labs=[r for r in rooms if r.kind=='lab']
            if not labs: continue
            if kind!='lab' or len(labs)<2: return None
            if pool is not None and {r.id for r in labs}!={r.id for r in pool}: return None
            pool=labs
    if not pool or any(e['room_id'] in {r.id for r in pool} for e in locked_entries): return None
    return pool


def allocate_lab_intervals(entries,pool):
    """Interval coloring of identical lab rooms; pooled capacity guarantees a fit."""
    ids={r.id for r in pool};result=[dict(e) for e in entries]
    for day in {e['day'] for e in result}:
        ends={r.id:0 for r in pool}
        sessions=sorted((e for e in result if e['day']==day and e['room_id'] in ids),key=lambda e:(e['slot'],e['offering_id']))
        for e in sessions:
            free=next((r.id for r in pool if ends[r.id]<=e['slot']),None)
            if free is None: raise ValueError('Lab interval coloring exceeded validated pooled capacity.')
            e['room_id']=free;ends[free]=e['slot']+e['duration']
    return result


def instructional_room_pool(config,locked_entries):
    """Reserve fixed tutorial rooms; pool identical flexible teaching rooms.

Pooling covers lectures and authorized classroom practicals. Fixed reservations
and differing eligibility disable pooling rather than weaken resource checks.
"""
    from .resources import eligible_rooms,session_specs
    base=None;reserved=set()
    for o in config.offerings:
        if o.lectures:
            ids={r.id for r in eligible_rooms(config,o,'lecture')}
            if len(ids)<2 or base is not None and ids!=base:return None
            base=ids
    if not base:return None
    for o in config.offerings:
        for kind,count,_ in session_specs(config,o):
            if not count or kind=='lecture':continue
            ids={r.id for r in eligible_rooms(config,o,kind)}
            if ids!=base:reserved|=ids&base
    ids=base-reserved
    if len(ids)<2 or any(e['room_id'] in ids for e in locked_entries):return None
    return [r for r in config.rooms if r.id in ids]


def allocate_instruction_intervals(config,entries,pool):
    """Color whole lecture blocks and joint practical intervals in pooled rooms."""
    from .resources import booking_key
    result=[dict(e) for e in entries];ids={r.id for r in pool}
    offerings={o.id:o for o in config.offerings};periods=config.settings.periods()
    for day in {e['day'] for e in result}:
        intervals=[];lectures=defaultdict(list);other=defaultdict(list)
        for e in result:
            if e['day']!=day or e['room_id'] not in ids:continue
            if e['kind']=='lecture':lectures[e['group_id']].append(e)
            else:other[booking_key(config,offerings[e['offering_id']],e['kind']),e['slot'],e['duration']].append(e)
        for sessions in lectures.values():
            block=[];end=None
            for e in sorted(sessions,key=lambda e:e['slot']):
                if block and (end!=e['slot'] or periods[end-1][1]!=periods[e['slot']][0]):
                    intervals.append((block[0]['slot'],end,block));block=[]
                block.append(e);end=e['slot']+e['duration']
            if block:intervals.append((block[0]['slot'],end,block))
        for (_,slot,duration),sessions in other.items():intervals.append((slot,slot+duration,sessions))
        ends={r.id:0 for r in pool}
        for start,end,sessions in sorted(intervals,key=lambda x:(x[0],x[1])):
            room=next((r.id for r in pool if ends[r.id]<=start),None)
            if room is None:raise ValueError('Instructional room coloring exceeded pooled capacity.')
            for e in sessions:e['room_id']=room
            ends[room]=end
    return result
