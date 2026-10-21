"""Measured timetable analytics and an independent constraint audit."""
from collections import defaultdict, Counter
import math
from .domain import Configuration, minutes
from .classrooms import classroom_metrics
from .resources import affected_units, eligible_rooms, student_units, session_specs, booking_key, booking_members, unreserved_project, elective_code


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
    seen_sessions=set()
    for index,e in enumerate(entries):
        identity=(e['offering_id'],e['kind'],e['day'],e['slot'])
        if identity in seen_sessions: violations.append(f"{e['offering_id']}: duplicate overlapping session.")
        seen_sessions.add(identity)
        o = m['offerings'][e['offering_id']]
        t,g,s = m['teachers'].get(e['teacher_id']),m['groups'][e['group_id']],m['subjects'][e['subject_id']]
        if (e['teacher_id'],e['group_id'],e['subject_id'],e.get('batch_id')) != (o.teacher_id,o.group_id,o.subject_id,o.batch_id):
            violations.append(f'{o.id}: session does not match its teaching assignment.')
        expected_duration = dict((kind,duration) for kind,count,duration in session_specs(config,o)).get(e['kind'])
        if e['duration'] != expected_duration:
            violations.append(f'{o.id}: incorrect session duration.')
        counts[o.id,e['kind']] += 1
        independent=unreserved_project(o,e['kind'])
        if (independent and e['room_id'] is not None) or (not independent and e['room_id'] not in {r.id for r in eligible_rooms(config,o,e['kind'])}):
            violations.append(f'{s.code}: ineligible room or insufficient seats.')
        if not settings.fits(e['day'],e['slot'],e['duration']):
            violations.append(f'{s.code}: session crosses a break, blocked period, or end of day.')
        if t and (minutes(periods[e['slot']][0]) < minutes(t.arrival) or minutes(periods[e['slot']+e['duration']-1][1]) > minutes(t.departure)):
            violations.append(f'{t.name}: session is outside working hours.')
        if t and e['kind'] in ('lab','project') and not t.lab_eligible:
            violations.append(f'{t.name}: not eligible for a lab/project.')
        booking=(booking_key(config,o,e['kind']),e['day'],e['slot'],e['duration'],e['room_id'])
        for slot in range(e['slot'],e['slot']+e['duration']):
            resources = ([('teacher',t.id)] if t else [])+([('room',e['room_id'])] if e['room_id'] else [])
            if s.elective and not elective_code(config,o):
                resources.append(('elective',g.department_id+'_'+str(g.semester)))
            resources += [('student',u) for u in affected_units(config,o)]
            for resource,identifier in resources:
                occupancy[resource,identifier,e['day'],slot].append(booking)
                slots[resource,identifier,e['day']].add(slot)
    for (resource,identifier,day,slot),items in occupancy.items():
        if len(set(items))>1:
            violations.append(f'{resource} {identifier}: {settings.days[day]}, period {slot+1} has {len(items)} overlapping sessions.')
    if settings.spread_lectures:
        lectures=Counter((e['offering_id'],e['kind'],e['day']) for e in entries if e['kind'] in ('lecture','tutorial'))
        for (offering_id,kind,day),count in lectures.items():
            required=m['offerings'][offering_id].lectures if kind=='lecture' else m['offerings'][offering_id].tutorials
            if count>math.ceil(required/len(settings.days)):
                violations.append(f'{m["subjects"][m["offerings"][offering_id].subject_id].code}: too many lectures on {settings.days[day]}; spread them across different days.')
    scheduled = {e['group_id'] for e in entries}
    for o in config.offerings:
        if o.group_id in scheduled:
            for kind,count,duration in session_specs(config,o):
                if counts[o.id,kind] != count:
                    violations.append(f'{o.id}: {kind} count does not match its requirement.')
    from .parallel import audit_electives
    violations.extend(audit_electives(config,entries))
    checked=set()
    for o in config.offerings:
        key=booking_key(config,o,'lab')
        if key[0]!='joint' or key in checked or o.group_id not in scheduled: continue
        checked.add(key)
        placements=[]
        for member in booking_members(config,o,'lab'):
            placements.append(sorted((e['day'],e['slot'],e['duration'],e['room_id']) for e in entries if e['offering_id']==member.id and e['kind']=='lab'))
        if any(p!=placements[0] for p in placements):
            violations.append(f'{o.id}: combined practical batches must share the same complete session and room.')
    for t in config.teachers:
        teacher_load[t.id]=sum(len(slots['teacher',t.id,d]) for d in range(len(settings.days)))
    for r in config.rooms:
        room_load[r.id]=sum(len(slots['room',r.id,d]) for d in range(len(settings.days)))
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
                    'semester':group.semester,'batch':m['batches'][unit.split('::')[0]].name+(' / '+unit.split('::')[1] if '::' in unit else '') if unit.split('::')[0] in m['batches'] else 'Whole / remaining division',
                    'day':settings.days[day],'periods':len(used),'start':periods[min(used)][0],
                    'end':periods[max(used)][1],'gaps':holes,'idle_minutes':holes*settings.period_minutes})
    room_quality=classroom_metrics(config,entries)
    enforced=result.get('summary',{}).get('classroom_optimization',{})
    if enforced.get('minimum_run_enforced'):
        enforced_groups=set(enforced.get('enforced_group_ids',scheduled))
        for change in room_quality['changes']:
            if change['group_id'] in enforced_groups and change['shortfall']:
                violations.append(f"Division {m['groups'][change['group_id']].division}, {settings.days[change['day']]}: classroom changes before the required {settings.classroom_run_length} consecutive lecture periods.")
    available=sum(len(settings.available(d)) for d in range(len(settings.days)))
    room_rows=[{'id':r.id,'name':r.name,'kind':r.kind,'capacity':r.capacity,'used_periods':room_load[r.id],
                'available_periods':available,'utilization':round(100*room_load[r.id]/available,1) if available else 0} for r in config.rooms]
    return {'available':True,'classroom_optimization':room_quality,'hard_conflicts':len(violations),'violations':violations,
        'health_score':100 if not violations else max(0,100-len(violations)*5),
        'student_quality':round(100*filled/(filled+gaps),1) if filled+gaps else 0,
        'internal_gaps':gaps,'idle_minutes':gaps*settings.period_minutes,'compact_days':sum(r['gaps']==0 for r in student_rows),
        'active_student_days':len(student_rows),'long_gap_days':sum(r['gaps']>=2 for r in student_rows),
        'room_utilization':round(100*sum(room_load.values())/(available*len(config.rooms)),1) if available and config.rooms else 0,
        'student_days':student_rows,'teachers':teacher_rows,'rooms':room_rows,
        'method':'Health: 100 minus 5 per audited violation (minimum 0). Student quality: teaching periods / (teaching periods + internal gaps). Room utilization: occupied room-periods / all available room-periods. Recess and blocked periods are excluded.'}
