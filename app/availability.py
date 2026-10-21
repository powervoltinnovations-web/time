"""Free resources for an entire requested interval in a saved timetable."""
from .domain import Configuration, minutes


def free_resources(record,day,slot,duration=1):
    config=Configuration(**record['config']);settings=config.settings
    if record['result']['status']!='feasible': raise ValueError('Choose a successful saved timetable.')
    if day<0 or day>=len(settings.days) or slot<0 or not settings.fits(day,slot,duration):
        raise ValueError('This interval crosses a break, blocked period, or the end of the day.')
    entries=record['result']['entries'];periods=settings.periods()
    busy=[e for e in entries if e['day']==day and e['slot']<slot+duration and slot<e['slot']+e['duration']]
    teachers=[]
    for t in config.teachers:
        if any(e['teacher_id']==t.id for e in busy): continue
        if minutes(t.arrival)>minutes(periods[slot][0]) or minutes(t.departure)<minutes(periods[slot+duration-1][1]):continue
        occupied={(e['day'],p) for e in entries if e['teacher_id']==t.id for p in range(e['slot'],e['slot']+e['duration'])}
        daily=sum(d==day for d,p in occupied)
        teachers.append({'id':t.id,'name':t.name,'lab_eligible':t.lab_eligible,
            'remaining_daily_periods':max(0,t.max_daily_slots-daily),
            'remaining_weekly_hours':max(0,t.max_hours-len(occupied)*settings.period_minutes/60)})
    rooms=[r.model_dump() for r in config.rooms if not any(e['room_id']==r.id for e in busy)]
    return {'day':settings.days[day],'start':periods[slot][0],'end':periods[slot+duration-1][1],
        'teachers':teachers,'classrooms':[r for r in rooms if r['kind']=='classroom'],'labs':[r for r in rooms if r['kind']=='lab'],
        'note':'Available across this complete interval in this saved timetable only. Faculty limits and room eligibility still apply; all manual changes are audited. Unscheduled divisions and external duties are not included.'}
