"""Constraint scheduling, real capacity checks, and explainable scoped generation."""
import math
import secrets
import time
from collections import defaultdict
from ortools.sat.python import cp_model
from .domain import Configuration, minutes
from .classrooms import (classroom_metrics, optimize_classrooms, require_classroom_runs,
                         interchangeable_classrooms, allocate_classroom_blocks, interchangeable_labs, allocate_lab_intervals, instructional_room_pool, allocate_instruction_intervals)
from .resources import student_units, affected_units, session_specs, teaching_slots, eligible_rooms, booking_key, unreserved_project


def issue(code, problem, suggestion):
    return {'code': code, 'problem': problem, 'suggestion': suggestion}


def preflight(config: Configuration):
    if not config.offerings or not config.groups:
        return [issue('EMPTY_DATA', 'There are no teaching assignments to schedule.',
                      'Import reference data or add divisions, teachers, subjects, and assignments.')]
    settings = config.settings
    periods = settings.periods()
    weekly_slots = sum(len(settings.available(day)) for day in range(len(settings.days)))
    hour = settings.period_minutes/60
    problems = []
    teacher_slots, unit_slots, room_slots, elective_slots = (defaultdict(int) for _ in range(4))
    subjects = {s.id:s for s in config.subjects}
    groups = {g.id:g for g in config.groups}
    teachers = {t.id:t for t in config.teachers}
    room_demands = defaultdict(int)
    counted=set()
    for item in config.offerings:
        total = teaching_slots(config, item)

        for unit in affected_units(config,item):
            unit_slots[unit] += total
        group, subject = groups[item.group_id], subjects[item.subject_id]
        if subject.elective:
            elective_slots[group.department_id, group.semester] += total
        if item.teacher_id is not None and (item.labs or item.projects) and not teachers[item.teacher_id].lab_eligible:
            problems.append(issue('LAB_ELIGIBILITY', f'{teachers[item.teacher_id].name} is not marked eligible for labs/projects.',
                                  'Assign an eligible teacher or update their eligibility after checking qualifications.'))
        for kind,count,duration in session_specs(config,item):
            if not count:
                continue
            key=booking_key(config,item,kind)
            if key in counted: continue
            counted.add(key)
            if unreserved_project(item,kind): continue
            teacher_slots[item.teacher_id] += count*duration
            rooms = eligible_rooms(config,item,kind)
            if not rooms:
                room_type = 'classroom' if kind in ('lecture','tutorial') else 'lab'
                problems.append(issue('ROOM_ELIGIBILITY',f'{subject.code}, semester {group.semester} {group.division}: no eligible {room_type} fits the student strength, department, year, and selected room.',
                    'Add or select a room with sufficient capacity and matching department/year eligibility, or use smaller practical batches.'))
            if len(rooms) == 1:
                room_slots[rooms[0].id] += count*duration
            if rooms:
                room_demands[tuple(sorted(r.id for r in rooms))] += count*duration
            if item.teacher_id is None:
                continue
            teacher = teachers[item.teacher_id]
            possible = any(settings.fits(day,slot,duration) and minutes(periods[slot][0]) >= minutes(teacher.arrival)
                           and minutes(periods[slot+duration-1][1]) <= minutes(teacher.departure)
                           for day in range(len(settings.days)) for slot in range(len(periods)))
            if not possible:
                problems.append(issue('LAB_AVAILABILITY' if kind != 'lecture' else 'TEACHER_AVAILABILITY',
                    f'{teacher.name} has no {duration*settings.period_minutes}-minute unbroken window for {subject.code} ({kind}).',
                    'Extend teacher availability, change the session duration in College timings, or reassign the session. Breaks cannot be crossed.'))
    for teacher in config.teachers:
        slots = teacher_slots[teacher.id]
        available = sum(min(teacher.max_daily_slots, sum(minutes(periods[p][0]) >= minutes(teacher.arrival)
            and minutes(periods[p][1]) <= minutes(teacher.departure) for p in settings.available(day))) for day in range(len(settings.days)))
        if slots*hour > teacher.max_hours:
            problems.append(issue('TEACHER_LOAD',f'{teacher.name} has {slots*hour:g} assigned hours, above the {teacher.max_hours}-hour weekly limit.',
                f'Reassign at least {slots*hour-teacher.max_hours:g} hours to another teacher, reduce requirements, or raise the limit if policy permits.'))
        if slots > available:
            problems.append(issue('TEACHER_AVAILABILITY',f'{teacher.name} needs {slots} periods but availability and the daily cap allow only {available} periods per week.',
                                  'Extend availability, adjust the daily cap, or reassign subjects.'))
    for group in config.groups:
        for unit in student_units(config,group):
            if unit_slots[unit] > weekly_slots:
                problems.append(issue('DIVISION_LOAD',f'Semester {group.semester}, Division {group.division} ({unit}) needs {unit_slots[unit]} periods; only {weekly_slots} are available.',
                                      'Reduce requirements or extend the college calendar.'))
        if not any(o.group_id == group.id for o in config.offerings):
            problems.append(issue('NO_ASSIGNMENTS',f'Semester {group.semester}, Division {group.division} has no teaching assignments.',
                                  'Add subject assignments or exclude this division from generation.'))
    for room in config.rooms:
        if room_slots[room.id] > weekly_slots:
            problems.append(issue('ROOM_CAPACITY',f'{room.name} needs {room_slots[room.id]} periods; it has only {weekly_slots}.',
                                  'Use automatic room allocation or reassign some sessions to another eligible room.'))
    for pool,demand in room_demands.items():
        if demand > len(pool)*weekly_slots:
            pool_rooms = [r for r in config.rooms if r.id in pool]
            label = 'laboratories' if all(r.kind == 'lab' for r in pool_rooms) else 'rooms'
            capacity = len(pool)*weekly_slots
            problems.append(issue('ROOM_POOL_CAPACITY',
                f'{demand*hour:g} required room-hours exceed {capacity*hour:g} available room-hours '
                f'in {len(pool)} {label} ({", ".join(r.name for r in pool_rooms)}) '
                f'by {(demand-capacity)*hour:g} hours per week.',
                'Review assignment counts against the source timetable, add eligible laboratory capacity, '
                'or extend the approved calendar. Labs stay in laboratories for their full configured duration; '
                'the scheduler will not silently move them to classrooms or shorten them.'))
    for (department,semester),slots in elective_slots.items():
        if slots > weekly_slots:
            problems.append(issue('ELECTIVE_CAPACITY',f'Semester {semester} in {department} needs {slots} separate elective periods; only {weekly_slots} exist.',
                                  'Reduce elective requirements or extend the calendar. Elective sets retain separate slots.'))
    return problems


def generate(config: Configuration, time_limit=20, target_group_ids=None, locked_entries=None, random_seed=None, initial_entries=None, pool_instruction_rooms=True):
    started = time.monotonic()
    all_groups = {g.id:g for g in config.groups}
    targets = set(target_group_ids if target_group_ids is not None else all_groups)
    locked = [e for e in (locked_entries or []) if e['group_id'] not in targets]
    active = targets | {e['group_id'] for e in locked}
    if (target_group_ids is not None and not targets) or not targets <= all_groups.keys():
        raise ValueError('Choose at least one existing division to generate.')
    data = config.model_dump()
    data['groups'] = [g for g in data['groups'] if g['id'] in active]
    data['batches'] = [b for b in data['batches'] if b['group_id'] in active]
    data['offerings'] = [o for o in data['offerings'] if o['group_id'] in active]
    selected = Configuration(**data)
    scope = {'target_group_ids':sorted(targets), 'scheduled_group_ids':sorted(active),
             'remaining_group_ids':sorted(all_groups.keys()-active), 'locked_sessions':len(locked)}
    def failed(status, issues, explanation=None):
        result = {'status':status,'entries':[],'issues':issues,'solutions':[],'summary':{},
                  'scope':scope,'elapsed_seconds':round(time.monotonic()-started,3)}
        if explanation:
            result['explanation'] = explanation
        return result
    problems = preflight(selected)
    if problems:
        return failed('infeasible',problems)
    settings = config.settings
    periods, days = settings.periods(), settings.days
    def success(entries,room_optimal,peak_value,balance_optimal,reused=False):
        room_quality=classroom_metrics(selected,entries)
        hours = sum(e['duration']*settings.period_minutes/60 for e in entries)
        return {'status':'feasible','entries':entries,'issues':[],'scope':scope,'elapsed_seconds':round(time.monotonic()-started,3),
                'solutions':[
                    'Revalidated compatible saved placements and saved them as a new draft.' if reused else 'Placed every requested lecture, lab, and project in the selected plan without teacher, student, or room collisions.',
                    f'Kept student days consecutive from {settings.start}, excluding configured breaks and blocked periods. Days may finish early.',
                    'Assigned only rooms with sufficient seats and matching department/year eligibility. Shared rooms are allocated dynamically when Auto is selected.',
                    'Reserved separate elective periods within each department and semester, including across divisions.',
                    'Respected teacher coming/leaving times, daily and weekly limits, and lab/project eligibility. Sessions never cross breaks.',
                    f'Preserved {len(locked)} sessions outside the selected divisions from the base timetable.' if locked else 'Created a fresh plan for the selected scope.',
                    'Spread each subject’s lectures across working days; subjects with up to one lecture per working day never repeat on the same day.' if settings.spread_lectures else 'Used the saved lecture-distribution policy.',
                    f'Classroom preference: {settings.classroom_run_length} consecutive lecture periods; {room_quality["classroom_changes"]} changes, including {room_quality["early_changes"]} before the preferred run length. Mandatory constraints remain enforced.' if settings.classroom_run_length>1 else 'Classroom continuity optimization was not requested.',
                    f'Limited the longest student day to {peak_value} teaching periods.'
                ],'summary':{'sessions':len(entries),'teaching_hours':hours,'divisions':len(selected.groups),
                              'teachers':len({e['teacher_id'] for e in entries if e['teacher_id']}),'reused_placements':reused,'max_daily_hours':peak_value*settings.period_minutes/60,
                              'max_daily_periods':peak_value,'balance_optimal':balance_optimal,
                              'classroom_optimization':{**room_quality,'optimal':room_optimal,'minimum_run_enforced':settings.classroom_run_length>=2,'enforced_group_ids':sorted(targets) if settings.classroom_run_length>=2 else []},'algorithm':'Google OR-Tools CP-SAT'}}

    # A compatible saved plan is a validated starting solution, not a reason to
    # repeat an expensive search. Old records and academic data are not edited.
    if initial_entries:
        from .analytics import analyze
        seed=[dict(e) for e in initial_entries if e['group_id'] in targets]+[dict(e) for e in locked]
        expected={o.group_id for o in selected.offerings}
        try:
            audit=analyze({'config':selected.model_dump(),'result':{'status':'feasible','entries':seed}})
            valid={e['group_id'] for e in seed}==expected and not audit['hard_conflicts']
        except (KeyError,IndexError,TypeError,ValueError):
            valid=False
        if valid:
            quality=classroom_metrics(selected,seed)
            if settings.classroom_run_length>=2 and any(c['group_id'] in targets and c['shortfall'] for c in quality['changes']):
                seed,_=optimize_classrooms(selected,seed,locked,min(3,max(.001,time_limit*.1)))
                quality=classroom_metrics(selected,seed)
            if settings.classroom_run_length<2 or not any(c['group_id'] in targets and c['shortfall'] for c in quality['changes']):
                peak_value=max((d['periods'] for d in audit['student_days']),default=0)
                loads=defaultdict(int)
                for d in audit['student_days']: loads[d['group_id'],d['batch']]+=d['periods']
                lower=max((math.ceil(n/len(days)) for n in loads.values()),default=0)
                return success(seed,quality['classroom_changes']==0,peak_value,peak_value==lower,True)
    shared_rooms=instructional_room_pool(selected,locked) if pool_instruction_rooms and settings.classroom_run_length>=2 else None
    lab_pool=interchangeable_labs(selected,locked)
    lab_ids={r.id for r in lab_pool} if lab_pool else set()
    model = cp_model.CpModel()
    teachers = {x.id:x for x in selected.teachers}
    subjects = {x.id:x for x in selected.subjects}
    groups = {x.id:x for x in selected.groups}
    coverage = defaultdict(list)
    candidates, assumptions = [], {}
    choice_by_key = {}
    joint_variables = {}

    def assumption(name, diagnostic):
        literal = model.NewBoolVar(name)
        model.AddAssumption(literal)
        assumptions[literal.Index()] = diagnostic
        return literal

    for item in selected.offerings:
        teacher, subject, group = teachers.get(item.teacher_id), subjects[item.subject_id], groups[item.group_id]
        required = assumption('required_'+item.id,issue('ASSIGNMENT_CONFLICT',
            f'{subject.code}, semester {group.semester} {group.division}, {teacher.name if teacher else "Independent project"}: {item.lectures} lectures, {item.labs} labs, {item.projects} projects are part of the conflicting requirements.',
            'Review the listed assignments together. Adjust teacher availability, eligible rooms, session counts, or locked divisions.'))
        units = affected_units(selected,item)
        for kind,count,duration in session_specs(selected,item):
            if not count:
                continue
            choices = []
            daily_choices = defaultdict(list)
            rooms = eligible_rooms(selected,item,kind)
            if shared_rooms and {r.id for r in shared_rooms}<={r.id for r in rooms}:rooms=shared_rooms[:1]
            if lab_pool and {r.id for r in rooms}==lab_ids: rooms=lab_pool[:1]
            if unreserved_project(item,kind):
                from types import SimpleNamespace
                rooms=[SimpleNamespace(id=None)]
            for day in range(len(days)):
                for slot in range(len(periods)):
                    if not settings.fits(day,slot,duration):
                        continue
                    if teacher and (minutes(periods[slot][0]) < minutes(teacher.arrival) or minutes(periods[slot+duration-1][1]) > minutes(teacher.departure)):
                        continue
                    for room in rooms:
                        joint_key=(booking_key(selected,item,kind),day,slot,room.id)
                        var=joint_variables.get(joint_key)
                        if var is None:
                            var = model.NewBoolVar(f'{item.id}_{kind}_{day}_{slot}_{room.id}')
                            joint_variables[joint_key]=var
                        choices.append(var)
                        daily_choices[day].append(var)
                        entry = {'offering_id':item.id,'group_id':group.id,'subject_id':subject.id,'teacher_id':item.teacher_id,
                                 'room_id':room.id,'day':day,'slot':slot,'duration':duration,'kind':kind,'batch_id':item.batch_id}
                        candidates.append((var,entry))
                        choice_by_key[item.id,kind,day,slot,room.id] = var
                        for offset in range(duration):
                            for resource,key in ([('teacher',teacher.id)] if teacher else [])+([('room',room.id)] if room.id else [])+[('student',u) for u in units]:
                                coverage[resource,key,day,slot+offset].append(var)
                            if subject.elective:
                                coverage['elective',(group.department_id,group.semester),day,slot+offset].append(var)
            model.Add(sum(choices) == count).OnlyEnforceIf(required)
            if kind in ('lecture','tutorial') and settings.spread_lectures:
                spread=assumption('spread_'+item.id,issue('LECTURE_SPREAD',
                    f'{subject.code}, semester {group.semester} {group.division}: {count} lectures must be spread across working days.',
                    'Provide teacher availability on more days, adjust locked sessions, or review lecture requirements.'))
                for variables in daily_choices.values():
                    model.Add(sum(variables)<=math.ceil(count/len(days))).OnlyEnforceIf(spread)

    # A combined session reserves teacher and room once, but each batch independently.
    coverage={key:list({v.Index():v for v in values}.values()) for key,values in coverage.items()}
    coverage=defaultdict(list,coverage)
    for entry in locked:
        key = (entry['offering_id'],entry['kind'],entry['day'],entry['slot'],entry['room_id'])
        if key not in choice_by_key:
            return failed('infeasible',[issue('LOCKED_CONFLICT','A session in the base timetable no longer fits the current academic data.',
                                            'Generate all affected divisions together with a fresh plan.')])
        model.Add(choice_by_key[key] == 1)

    for (resource,key,day,slot),variables in coverage.items():
        if resource != 'elective':
            capacity=len(shared_rooms) if shared_rooms and resource=='room' and key==shared_rooms[0].id else 1
            if lab_pool and resource=='room' and key==lab_pool[0].id: capacity=len(lab_pool)
            model.Add(sum(variables) <= capacity)
    for department,semester in {(s.department_id,s.semester) for s in selected.subjects if s.elective}:
        separate = assumption(f'elective_{department}_{semester}',issue('SEPARATE_ELECTIVES',
            f'{department}, semester {semester}: every elective session requires a separate slot across divisions.',
            'Adjust elective assignments or availability to create more distinct periods. Sets organize subjects without making them parallel.'))
        for day in range(len(days)):
            for slot in range(len(periods)):
                model.Add(sum(coverage['elective',(department,semester),day,slot]) <= 1).OnlyEnforceIf(separate)
    for teacher in selected.teachers:
        for day in range(len(days)):
            model.Add(sum(sum(coverage['teacher',teacher.id,day,p]) for p in range(len(periods))) <= teacher.max_daily_slots)

    peak = model.NewIntVar(0,len(periods),'largest_daily_load')
    lower_bound = 0
    for group in selected.groups:
        no_gaps = assumption('no_gaps_'+group.id,issue('CONTIGUOUS_DAY',
            f'Semester {group.semester} {group.division} must start at {settings.start} with no internal gaps except configured breaks/blocked periods.',
            'Make teachers and rooms available at the start of the day, or adjust assignments, the calendar, or locked divisions.'))
        for unit in student_units(selected,group):
            load = sum(teaching_slots(selected,o) for o in selected.offerings if unit in affected_units(selected,o))
            lower_bound = max(lower_bound,math.ceil(load/len(days)))
            for day in range(len(days)):
                busy = []
                for slot in settings.available(day):
                    value = model.NewBoolVar(f'busy_{unit}_{day}_{slot}')
                    model.Add(value == sum(coverage['student',unit,day,slot]))
                    busy.append(value)
                for a,b in zip(busy,busy[1:]):
                    model.Add(a >= b).OnlyEnforceIf(no_gaps)
                if load >= len(days) and busy:
                    model.Add(busy[0] == 1).OnlyEnforceIf(no_gaps)
                model.Add(sum(busy) <= peak)
    model.Minimize(peak)
    diagnostic_model = model.Clone()
    model.ClearAssumptions()
    for index in assumptions:
        model.Add(model.GetBoolVarFromProtoIndex(index) == 1)
    model.Add(peak >= lower_bound)
    if initial_entries:
        hinted=set()
        for entry in initial_entries:
            room=shared_rooms[0].id if shared_rooms and entry['room_id'] in {r.id for r in shared_rooms} else entry['room_id']
            if entry['room_id'] in lab_ids: room=lab_pool[0].id
            var=choice_by_key.get((entry['offering_id'],entry['kind'],entry['day'],entry['slot'],room))
            if var is not None and var.Index() not in hinted:
                model.AddHint(var,1);hinted.add(var.Index())
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.000001,time_limit*(.8 if settings.classroom_run_length>1 else 1)-(time.monotonic()-started))
    solver.parameters.num_search_workers = 4
    solver.parameters.random_seed = random_seed if random_seed is not None else secrets.randbelow(2**30)
    result = solver.Solve(model)
    if result == cp_model.INFEASIBLE and shared_rooms:
        # Reserving fixed tutorial rooms is a search optimization, not a new requirement.
        return generate(config,max(.01,time_limit-(time.monotonic()-started)),target_group_ids,locked_entries,random_seed,initial_entries,pool_instruction_rooms=False)
    if result == cp_model.INFEASIBLE:
        diagnostic_model.ClearObjective()
        diagnostic_solver = cp_model.CpSolver()
        diagnostic_solver.parameters.max_time_in_seconds = max(0.001,time_limit-(time.monotonic()-started))
        diagnostic_solver.parameters.num_search_workers = 1
        status = diagnostic_solver.Solve(diagnostic_model)
        core = diagnostic_solver.SufficientAssumptionsForInfeasibility() if status == cp_model.INFEASIBLE else []
        diagnostics = [assumptions[i] for i in core if i in assumptions]
        return failed('infeasible',diagnostics or [issue('CONSTRAINT_CONFLICT',
            'The combined teacher, student, room, elective, and calendar requirements cannot be satisfied.',
            'Review shared room capacity, teacher daily limits, unbroken lab windows, and any locked divisions. Try scheduling affected divisions together.')],
            'Proven infeasible. Where available, the listed constraints form a sufficient conflict set, which may not be minimal. Suggestions are not applied automatically.')
    if result not in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        return failed('timeout',[issue('SEARCH_LIMIT','The search limit was reached without a complete timetable. This does not prove generation is impossible.',
                                      'Use a longer search limit, schedule connected divisions together, or reduce contention for shared rooms.')])
    entries = sorted([entry for var,entry in candidates if solver.BooleanValue(var)],key=lambda e:(e['group_id'],e['day'],e['slot'],e['room_id'] or ''))
    if lab_pool: entries=allocate_lab_intervals(entries,lab_pool)
    room_budget=max(.01,time_limit-(time.monotonic()-started))
    if settings.classroom_run_length>=2:
        room_budget=min(room_budget,max(.01,time_limit*.1))
    if shared_rooms:
        entries=allocate_instruction_intervals(selected,entries,shared_rooms)
        room_optimal=True
    else:
        entries,room_optimal=optimize_classrooms(selected,entries,locked,room_budget)
    room_quality=classroom_metrics(selected,entries)
    early_target_changes=[c for c in room_quality['changes'] if c['group_id'] in targets and c['shortfall']>0]
    if settings.classroom_run_length>=2 and early_target_changes:
        # Try the inexpensive room-only repair first. If times prevent a full run,
        # jointly reschedule the selected divisions; never return the violating seed.
        continuity=model.NewBoolVar('require_minimum_lecture_room_stay')
        model.Add(continuity==1)
        require_classroom_runs(model,selected,candidates,targets,continuity)
        model.ClearHints()
        used={(e['offering_id'],e['kind'],e['day'],e['slot'],e['room_id']) for e in entries}
        hinted=set()
        for var,e in candidates:
            if var.Index() not in hinted:
                model.AddHint(var,int((e['offering_id'],e['kind'],e['day'],e['slot'],e['room_id']) in used));hinted.add(var.Index())
        solver.parameters.max_time_in_seconds=max(.001,time_limit-(time.monotonic()-started))
        result=solver.Solve(model)
        if result==cp_model.INFEASIBLE:
            return failed('infeasible',[issue('CLASSROOM_CONTINUITY',
                f'The selected divisions cannot keep one classroom for at least {settings.classroom_run_length} consecutive lecture periods with the current rooms, availability, and preserved divisions.',
                'Provide an eligible room for the complete lecture block, or generate connected divisions together without preserving their old room bookings. Labs, projects, recess, and the end of the day may end a shorter block.')])
        if result not in (cp_model.OPTIMAL,cp_model.FEASIBLE):
            return failed('timeout',[issue('CLASSROOM_SEARCH_LIMIT',
                f'A timetable was found, but it changed classrooms before {settings.classroom_run_length} consecutive lectures. It was not accepted. Search time expired while arranging a compliant timetable; this does not prove it is impossible.',
                'Increase the search limit or generate connected divisions together so their room bookings can move.')])
        entries=sorted([entry for var,entry in candidates if solver.BooleanValue(var)],key=lambda e:(e['group_id'],e['day'],e['slot'],e['room_id'] or ''))
        if lab_pool: entries=allocate_lab_intervals(entries,lab_pool)
        entries,room_optimal=optimize_classrooms(selected,entries,locked,max(.001,time_limit-(time.monotonic()-started)))
        room_quality=classroom_metrics(selected,entries)
    return success(entries,room_optimal,solver.Value(peak),result==cp_model.OPTIMAL or solver.Value(peak)==lower_bound)
