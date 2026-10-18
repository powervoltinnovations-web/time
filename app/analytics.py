"""Measured timetable analytics and an independent constraint audit."""
from collections import defaultdict, Counter
import math
from .domain import Configuration, minutes
from .classrooms import classroom_metrics
from .resources import affected_units, eligible_rooms, student_units, session_specs


def analyze(record):
    config = Configuration(**record['config'])
    result = record['result']
    if result['status'] != 'feasible':
        return {'available':False,'issues':result['issues']}
    entries = result['entries']
    settings = config.settings
    periods = settings.periods()
    m = {key:{x.id:x for x in getattr(config,key)} for key in ('groups','teachers','subjects','rooms','offerings','batches','departments')}
    occupancy = defaultdict(list)
    slots = defaultdict(set)
    counts, teacher_load, room_load = Counter(),Counter(),Counter()
    violations = []
    for index,e in enumerate(entries):
        o = m['offerings'][e['offering_id']]
        t,g,s = m['teachers'][e['teacher_id']],m['groups'][e['group_id']],m['subjects'][e['subject_id']]
        if (e['teacher_id'],e['group_id'],e['subject_id'],e.get('batch_id')) != (o.teacher_id,o.group_id,o.subject_id,o.batch_id):
            violations.append(f'{o.id}: session does not match its teaching assignment.')
        expected_duration = dict((kind,duration) for kind,count,duration in session_specs(config,o)).get(e['kind'])
        if e['duration'] != expected_duration:
            violations.append(f'{o.id}: incorrect session duration.')
        counts[o.id,e['kind']] += 1
        if e['room_id'] not in {r.id for r in eligible_rooms(config,o,e['kind'])}:
            violations.append(f'{s.code}: ineligible room or insufficient seats.')
        if not settings.fits(e['day'],e['slot'],e['duration']):
            violations.append(f'{s.code}: session crosses a break, blocked period, or end of day.')
        if minutes(periods[e['slot']][0]) < minutes(t.arrival) or minutes(periods[e['slot']+e['duration']-1][1]) > minutes(t.departure):
            violations.append(f'{t.name}: session is outside working hours.')
        if e['kind'] != 'lecture' and not t.lab_eligible:
            violations.append(f'{t.name}: not eligible for a lab/project.')
        teacher_load[t.id] += e['duration']
        room_load[e['room_id']] += e['duration']
        for slot in range(e['slot'],e['slot']+e['duration']):
            resources = [('teacher',t.id),('room',e['room_id'])]
            if s.elective:
                resources.append(('elective',g.department_id+'_'+str(g.semester)))
            resources += [('student',u) for u in affected_units(config,o)]
            for resource,identifier in resources:
                occupancy[resource,identifier,e['day'],slot].append(index)
                slots[resource,identifier,e['day']].add(slot)
    for (resource,identifier,day,slot),items in occupancy.items():
        if len(items)>1:
            violations.append(f'{resource} {identifier}: {settings.days[day]}, period {slot+1} has {len(items)} overlapping sessions.')
    if settings.spread_lectures:
        lectures=Counter((e['offering_id'],e['day']) for e in entries if e['kind']=='lecture')
        for (offering_id,day),count in lectures.items():
            if count>math.ceil(m['offerings'][offering_id].lectures/len(settings.days)):
                violations.append(f'{m["subjects"][m["offerings"][offering_id].subject_id].code}: too many lectures on {settings.days[day]}; spread them across different days.')
    scheduled = {e['group_id'] for e in entries}
    for o in config.offerings:
        if o.group_id in scheduled:
            for kind,count,duration in session_specs(config,o):
                if counts[o.id,kind] != count:
                    violations.append(f'{o.id}: {kind} count does not match its requirement.')
    teacher_rows=[]
    for t in config.teachers:
        daily=[len(slots['teacher',t.id,d]) for d in range(len(settings.days))]
        hours=teacher_load[t.id]*settings.period_minutes/60
        if hours>t.max_hours or max(daily,default=0)>t.max_daily_slots:
            violations.append(f'{t.name}: daily or weekly limit exceeded.')
        teacher_rows.append({'id':t.id,'name':t.name,'hours':hours,'weekly_limit':t.max_hours,'daily':daily,'daily_limit':t.max_daily_slots})
    student_rows=[]
    gaps=0
    filled=0
    for group in config.groups:
        if group.id not in scheduled:
            continue
        for unit in student_units(config,group):
            for day in range(len(settings.days)):
                used=slots['student',unit,day]
                if not used:
                    load=sum(count*duration for o in config.offerings if unit in affected_units(config,o) for kind,count,duration in session_specs(config,o))
                    if load>=len(settings.days) and settings.available(day):
                        violations.append(f'Division {group.division}, {settings.days[day]}: required teaching day is empty.')
                    continue
                if min(used) != settings.available(day)[0]:
                    violations.append(f'Division {group.division}, {settings.days[day]}: starts after the first available period.')
                holes=sum(p not in used for p in settings.available(day) if min(used)<=p<=max(used))
                gaps+=holes
                filled+=len(used)
                if holes:
                    violations.append(f'Division {group.division}, {settings.days[day]}: {holes} internal gaps.')
                student_rows.append({'group_id':group.id,'division':group.division,'department':m['departments'][group.department_id].code,
                    'semester':group.semester,'batch':m['batches'][unit].name if unit in m['batches'] else 'Whole / remaining division',
                    'day':settings.days[day],'periods':len(used),'start':periods[min(used)][0],
                    'end':periods[max(used)][1],'gaps':holes,'idle_minutes':holes*settings.period_minutes})
    available=sum(len(settings.available(d)) for d in range(len(settings.days)))
    room_rows=[{'id':r.id,'name':r.name,'kind':r.kind,'capacity':r.capacity,'used_periods':room_load[r.id],
                'available_periods':available,'utilization':round(100*room_load[r.id]/available,1) if available else 0} for r in config.rooms]
    return {'available':True,'classroom_optimization':classroom_metrics(config,entries),'hard_conflicts':len(violations),'violations':violations,
        'health_score':100 if not violations else max(0,100-len(violations)*5),
        'student_quality':round(100*filled/(filled+gaps),1) if filled+gaps else 0,
        'internal_gaps':gaps,'idle_minutes':gaps*settings.period_minutes,'compact_days':sum(r['gaps']==0 for r in student_rows),
        'active_student_days':len(student_rows),'long_gap_days':sum(r['gaps']>=2 for r in student_rows),
        'room_utilization':round(100*sum(room_load.values())/(available*len(config.rooms)),1) if available and config.rooms else 0,
        'student_days':student_rows,'teachers':teacher_rows,'rooms':room_rows,
        'method':'Health: 100 minus 5 per audited violation (minimum 0). Student quality: teaching periods / (teaching periods + internal gaps). Room utilization: occupied room-periods / all available room-periods. Recess and blocked periods are excluded.'}
