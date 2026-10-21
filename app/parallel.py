"""Generation-only elective policy and measurable batch utilization."""
from collections import defaultdict
from .resources import elective_code, booking_key, student_units, affected_units, group_options


def elective_problems(config):
    problems=[]
    buckets=defaultdict(list)
    for o in config.offerings:
        if elective_code(config,o):
            g=next(g for g in config.groups if g.id==o.group_id)
            buckets[g.department_id,g.semester].append(o)
    for key,items in buckets.items():
        groups=[g for g in config.groups if (g.department_id,g.semester)==key and g.division.upper() in ('A','B')]
        if len(groups)!=2: problems.append('Combined IS/STQA requires both final-year A and B in this scope.')
        sizes=config.settings.combined_elective_students
        if any(type(n)!=int or n<=0 for n in sizes.values()) or sum(sizes.values())!=sum(g.strength for g in groups):
            problems.append('Combined option enrollment must be positive and total the A+B student count.')
        counts=set()
        for code in sizes:
            members=[o for o in items if elective_code(config,o)==code]
            if len(members)!=2 or len({o.group_id for o in members})!=2:
                problems.append(f'{code}: both divisions need a lecture assignment.')
            if len({(o.teacher_id,o.lectures) for o in members})!=1 or any(o.labs or o.tutorials or o.projects or not o.lectures for o in members):
                problems.append(f'{code}: combined assignments must have the same teacher and lecture count, with no practical components.')
            counts.update(o.lectures for o in members)
        if len(counts)!=1: problems.append('Combined options must have matching weekly session counts.')
    return problems


def audit_electives(config,entries):
    errors=elective_problems(config)
    placements=defaultdict(list);families=defaultdict(dict)
    scheduled={e['group_id'] for e in entries}
    for o in config.offerings:
        if o.group_id not in scheduled or not elective_code(config,o): continue
        key=booking_key(config,o,'lecture')
        times=sorted((e['day'],e['slot'],e['duration'],e['room_id']) for e in entries if e['offering_id']==o.id and e['kind']=='lecture')
        placements[key].append(times)
        families[key[1:3]][key[3]]=times
    for key,copies in placements.items():
        if len(copies)!=2 or any(c!=copies[0] for c in copies[1:]):
            errors.append(f'{key[3]}: combined A+B copies must share every time and room.')
    for options in families.values():
        times=[[(d,s,n) for d,s,n,r in p] for p in options.values()]
        if any(t!=times[0] for t in times[1:]): errors.append('IS and STQA must run at the same times.')
    return errors


def batch_metrics(config,entries):
    occupied=defaultdict(set)
    offerings={o.id:o for o in config.offerings}
    for e in entries:
        for p in range(e['slot'],e['slot']+e['duration']):
            occupied[e['group_id'],e['day'],p].update(affected_units(config,offerings[e['offering_id']]))
    missing=partial=full=0
    for g in config.groups:
        units=student_units(config,g)
        if len(units)<2 or group_options(config,g): continue
        for d in range(len(config.settings.days)):
            for p in config.settings.available(d):
                count=len(occupied[g.id,d,p])
                if count:
                    missing+=len(units)-count
                    partial+=count<len(units)
                    full+=count==len(units)
    return {'missing_batch_periods':missing,'partial_periods':partial,'full_periods':full,
            'note':'Parallel batches are optimized while exact hours, teachers, rooms and two-hour labs stay mandatory. Shared tutorial teachers may require partial batch periods.'}
