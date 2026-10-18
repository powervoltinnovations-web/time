"""Constraint scheduling, real capacity checks, and explainable scoped generation."""
import math
import secrets
import time
from collections import defaultdict
from ortools.sat.python import cp_model
from .domain import Configuration, minutes
from .classrooms import classroom_metrics, optimize_classrooms
from .resources import student_units, affected_units, session_specs, teaching_slots, eligible_rooms


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
    for item in config.offerings:
        total = teaching_slots(config, item)
        teacher_slots[item.teacher_id] += total
        for unit in affected_units(config,item):
            unit_slots[unit] += total
        group, subject = groups[item.group_id], subjects[item.subject_id]
        if subject.elective:
            elective_slots[group.department_id, group.semester] += total
        if (item.labs or item.projects) and not teachers[item.teacher_id].lab_eligible:
            problems.append(issue('LAB_ELIGIBILITY', f'{teachers[item.teacher_id].name} is not marked eligible for labs/projects.',
                                  'Assign an eligible teacher or update their eligibility after checking qualifications.'))
        for kind,count,duration in session_specs(config,item):
            if not count:
                continue
            rooms = eligible_rooms(config,item,kind)
            if not rooms:
                room_type = 'classroom' if kind == 'lecture' else 'lab'
                problems.append(issue('ROOM_ELIGIBILITY',f'{subject.code}, semester {group.semester} {group.division}: no eligible {room_type} fits the student strength, department, year, and selected room.',
                    'Add or select a room with sufficient capacity and matching department/year eligibility, or use smaller practical batches.'))
            if len(rooms) == 1:
                room_slots[rooms[0].id] += count*duration
            if rooms:
                room_demands[tuple(sorted(r.id for r in rooms))] += count*duration
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
            problems.append(issue('ROOM_POOL_CAPACITY',f'{demand} periods compete for a pool of {len(pool)} rooms with {len(pool)*weekly_slots} available periods.',
                                  'Add eligible rooms, enlarge the shared pool, or reduce contact hours.'))
    for (department,semester),slots in elective_slots.items():
        if slots > weekly_slots:
            problems.append(issue('ELECTIVE_CAPACITY',f'Semester {semester} in {department} needs {slots} separate elective periods; only {weekly_slots} exist.',
                                  'Reduce elective requirements or extend the calendar. Elective sets retain separate slots.'))
    return problems


def generate(config: Configuration, time_limit=20, target_group_ids=None, locked_entries=None, random_seed=None):
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
    model = cp_model.CpModel()
    teachers = {x.id:x for x in selected.teachers}
    subjects = {x.id:x for x in selected.subjects}
    groups = {x.id:x for x in selected.groups}
    coverage = defaultdict(list)
    candidates, assumptions = [], {}
    choice_by_key = {}

    def assumption(name, diagnostic):
        literal = model.NewBoolVar(name)
        model.AddAssumption(literal)
        assumptions[literal.Index()] = diagnostic
        return literal

    for item in selected.offerings:
        teacher, subject, group = teachers[item.teacher_id], subjects[item.subject_id], groups[item.group_id]
        required = assumption('required_'+item.id,issue('ASSIGNMENT_CONFLICT',
            f'{subject.code}, semester {group.semester} {group.division}, {teacher.name}: {item.lectures} lectures, {item.labs} labs, {item.projects} projects are part of the conflicting requirements.',
            'Review the listed assignments together. Adjust teacher availability, eligible rooms, session counts, or locked divisions.'))
        units = affected_units(selected,item)
        for kind,count,duration in session_specs(selected,item):
            if not count:
                continue
            choices = []
            daily_choices = defaultdict(list)
            rooms = eligible_rooms(selected,item,kind)
            for day in range(len(days)):
                for slot in range(len(periods)):
                    if not settings.fits(day,slot,duration):
                        continue
                    if minutes(periods[slot][0]) < minutes(teacher.arrival) or minutes(periods[slot+duration-1][1]) > minutes(teacher.departure):
                        continue
                    for room in rooms:
                        var = model.NewBoolVar(f'{item.id}_{kind}_{day}_{slot}_{room.id}')
                        choices.append(var)
                        daily_choices[day].append(var)
                        entry = {'offering_id':item.id,'group_id':group.id,'subject_id':subject.id,'teacher_id':teacher.id,
                                 'room_id':room.id,'day':day,'slot':slot,'duration':duration,'kind':kind,'batch_id':item.batch_id}
                        candidates.append((var,entry))
                        choice_by_key[item.id,kind,day,slot,room.id] = var
                        for offset in range(duration):
                            for resource,key in [('teacher',teacher.id),('room',room.id), *[('student',u) for u in units]]:
                                coverage[resource,key,day,slot+offset].append(var)
                            if subject.elective:
                                coverage['elective',(group.department_id,group.semester),day,slot+offset].append(var)
            model.Add(sum(choices) == count).OnlyEnforceIf(required)
            if kind=='lecture' and settings.spread_lectures:
                spread=assumption('spread_'+item.id,issue('LECTURE_SPREAD',
                    f'{subject.code}, semester {group.semester} {group.division}: {count} lectures must be spread across working days.',
                    'Provide teacher availability on more days, adjust locked sessions, or review lecture requirements.'))
                for variables in daily_choices.values():
                    model.Add(sum(variables)<=math.ceil(count/len(days))).OnlyEnforceIf(spread)

    for entry in locked:
        key = (entry['offering_id'],entry['kind'],entry['day'],entry['slot'],entry['room_id'])
        if key not in choice_by_key:
            return failed('infeasible',[issue('LOCKED_CONFLICT','A session in the base timetable no longer fits the current academic data.',
                                            'Generate all affected divisions together with a fresh plan.')])
        model.Add(choice_by_key[key] == 1)

    for (resource,key,day,slot),variables in coverage.items():
        if resource != 'elective':
            model.Add(sum(variables) <= 1)
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
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.000001,time_limit*(.8 if settings.classroom_run_length>1 else 1)-(time.monotonic()-started))
    solver.parameters.num_search_workers = 4
    solver.parameters.random_seed = random_seed if random_seed is not None else secrets.randbelow(2**30)
    result = solver.Solve(model)
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
    entries = sorted([entry for var,entry in candidates if solver.BooleanValue(var)],key=lambda e:(e['group_id'],e['day'],e['slot'],e['room_id']))
    entries,room_optimal=optimize_classrooms(selected,entries,locked,max(.01,time_limit-(time.monotonic()-started)))
    room_quality=classroom_metrics(selected,entries)
    hours = sum(e['duration']*settings.period_minutes/60 for e in entries)
    return {'status':'feasible','entries':entries,'issues':[],'scope':scope,'elapsed_seconds':round(time.monotonic()-started,3),
            'solutions':[
                'Placed every requested lecture, lab, and project in the selected plan without teacher, student, or room collisions.',
                f'Kept student days consecutive from {settings.start}, excluding configured breaks and blocked periods. Days may finish early.',
                'Assigned only rooms with sufficient seats and matching department/year eligibility. Shared rooms are allocated dynamically when Auto is selected.',
                'Reserved separate elective periods within each department and semester, including across divisions.',
                'Respected teacher coming/leaving times, daily and weekly limits, and lab/project eligibility. Sessions never cross breaks.',
                f'Preserved {len(locked)} sessions outside the selected divisions from the base timetable.' if locked else 'Created a fresh plan for the selected scope.',
                'Spread each subject’s lectures across working days; subjects with up to one lecture per working day never repeat on the same day.' if settings.spread_lectures else 'Used the saved lecture-distribution policy.',
                f'Classroom preference: {settings.classroom_run_length} consecutive lecture periods; {room_quality["classroom_changes"]} changes, including {room_quality["early_changes"]} before the preferred run length. Mandatory constraints remain enforced.' if settings.classroom_run_length>1 else 'Classroom continuity optimization was not requested.',
                f'Limited the longest student day to {solver.Value(peak)} teaching periods.'
            ],'summary':{'sessions':len(entries),'teaching_hours':hours,'divisions':len(selected.groups),
                          'teachers':len({e['teacher_id'] for e in entries}),'max_daily_hours':solver.Value(peak)*settings.period_minutes/60,
                          'max_daily_periods':solver.Value(peak),'balance_optimal':result == cp_model.OPTIMAL or solver.Value(peak)==lower_bound,
                          'classroom_optimization':{**room_quality,'optimal':room_optimal},'algorithm':'Google OR-Tools CP-SAT'}}
