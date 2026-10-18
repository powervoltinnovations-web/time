"""Manual placements preserve assignments and validate the entire saved plan."""
from copy import deepcopy
from .domain import Configuration
from .analytics import analyze


def edit_result(record, changes):
    config=Configuration(**record['config'])
    result=deepcopy(record['result'])
    entries=result['entries']
    seen=set()
    for change in changes:
        index=change.entry_index
        if index in seen or not 0 <= index < len(entries):
            raise ValueError('Each edited session must refer to a distinct existing session.')
        seen.add(index)
        entry=entries[index]
        if change.day>=len(config.settings.days) or change.slot+entry['duration']>len(config.settings.periods()):
            raise ValueError('The session must fit within the saved timetable calendar. Multi-period sessions must fit in full.')
        if change.room_id not in {r.id for r in config.rooms}:
            raise ValueError('Choose a room from this saved timetable.')
        entry.update(day=change.day,slot=change.slot,room_id=change.room_id)
    if entries==record['result']['entries']:
        raise ValueError('No placements changed. Move a session, swap placements, or select another eligible room.')
    audit=analyze({**record,'result':result})
    if audit['hard_conflicts']:
        return None,audit['violations']
    result['source']='manual'
    result['parent_generation_id']=record['id']
    result['elapsed_seconds']=0
    result['summary']['balance_optimal']=False
    result['summary']['classroom_optimization']={**audit['classroom_optimization'],'optimal':False}
    peak=max((row['periods'] for row in audit['student_days']),default=0)
    result['summary']['max_daily_periods']=peak
    result['summary']['max_daily_hours']=peak*config.settings.period_minutes/60
    result['summary']['algorithm']='Manual placement with full constraint audit'
    result['solutions']=[
        f'Manually adjusted {len(changes)} sessions; saved as a new draft based on version #{record["id"]}.',
        'Validated the complete saved plan: no teacher, room, student, or elective collisions.',
        'Preserved exact session counts and durations; respected faculty availability, caps, room eligibility, breaks, and student continuity.',
        'Original timetable content remains available in Version history. Daily balance has not been optimized after manual editing.'
    ]
    if 'scope' in result:
        result['scope']['locked_sessions']=0
        result['scope']['base_generation_id']=None
    return result,[]
