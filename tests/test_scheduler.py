from collections import Counter, defaultdict
from pathlib import Path
import pytest
from app.domain import Configuration, PERIODS, minutes, parse_csv
from app.scheduler import generate

SAMPLE = Path(__file__).resolve().parents[1] / 'sample_data' / 'unisched_semesters_3_5_7.csv'

@pytest.fixture(scope='module')
def sample():
    return parse_csv(SAMPLE.read_bytes())

@pytest.fixture(scope='module')
def scheduled(sample):
    result = generate(sample, 20)
    assert result['status'] == 'feasible', result
    return result

def verify_timetable(config, entries):
    """Independent verifier: reconstruct occupancy rather than trusting solver status."""
    teachers = {t.id: t for t in config.teachers}
    groups = {g.id: g for g in config.groups}
    subjects = {s.id: s for s in config.subjects}
    offerings = {o.id: o for o in config.offerings}
    occupied = set()
    days = defaultdict(set)
    hours = Counter()
    counts = Counter()
    for entry in entries:
        teacher = teachers[entry['teacher_id']]
        group = groups[entry['group_id']]
        subject = subjects[entry['subject_id']]
        offering = offerings[entry['offering_id']]
        assert entry['teacher_id'] == offering.teacher_id
        assert entry['subject_id'] == offering.subject_id
        assert entry['group_id'] == offering.group_id
        assert entry['duration'] == (2 if entry['kind'] == 'lab' else 1)
        assert entry['room_id'] == (offering.lab_room_id if entry['kind'] == 'lab' else group.room_id)
        assert 0 <= entry['day'] <= 4
        assert 0 <= entry['slot'] < 8
        assert entry['slot'] + entry['duration'] <= 8
        if entry['kind'] == 'lab':
            assert entry['slot'] in (0, 1, 2, 4, 5, 6)
        assert minutes(PERIODS[entry['slot']][0]) >= minutes(teacher.arrival)
        assert minutes(PERIODS[entry['slot']+entry['duration']-1][1]) <= minutes(teacher.departure)
        counts[offering.id, entry['kind']] += 1
        hours[teacher.id] += entry['duration']
        for slot in range(entry['slot'], entry['slot']+entry['duration']):
            resources = [('teacher', teacher.id), ('group', group.id), ('room', entry['room_id'])]
            if subject.elective:
                resources.append(('elective', subject.semester))
            for kind, identifier in resources:
                key = (kind, identifier, entry['day'], slot)
                assert key not in occupied, f'Collision: {key}'
                occupied.add(key)
            days[group.id, entry['day']].add(slot)
    for offering in config.offerings:
        assert counts[offering.id, 'lecture'] == offering.lectures
        assert counts[offering.id, 'lab'] == offering.labs
    for teacher in config.teachers:
        assert hours[teacher.id] <= teacher.max_hours
    for group in config.groups:
        load = sum(o.lectures+2*o.labs for o in config.offerings if o.group_id == group.id)
        for day in range(5):
            slots = days[group.id, day]
            if load >= 5:
                assert slots
            if slots:
                assert slots == set(range(max(slots)+1)), 'Noncontiguous division day'

def test_all_nine_divisions_are_valid(sample, scheduled):
    verify_timetable(sample, scheduled['entries'])
    assert scheduled['summary']['teaching_hours'] == 198
    assert scheduled['summary']['sessions'] == 171
    assert scheduled['summary']['divisions'] == 9
    assert scheduled['summary']['max_daily_hours'] == 5
    assert scheduled['summary']['balance_optimal']

def small_config():
    return Configuration(**{
        'teachers': [{'id':'t','name':'Professor Test','max_hours':20,'arrival':'09:00','departure':'17:45'}],
        'subjects': [{'id':'s','name':'Algorithms','code':'CS3','semester':3,'elective':False}],
        'rooms': [{'id':'r','name':'301','kind':'classroom'},{'id':'l','name':'Lab 1','kind':'lab'}],
        'groups': [{'id':'g','semester':3,'division':'A','room_id':'r'}],
        'offerings': [{'id':'o','group_id':'g','subject_id':'s','teacher_id':'t','lectures':5,'labs':2,'lab_room_id':'l'}]
    })

def test_teacher_weekly_limit():
    config = small_config()
    config.teachers[0].max_hours = 6
    result = generate(config)
    assert result['status'] == 'infeasible'
    assert result['entries'] == []
    assert 'TEACHER_LOAD' in {x['code'] for x in result['issues']}
    assert '9 assigned hours' in result['issues'][0]['problem']

def test_teacher_partial_period_availability():
    config = small_config()
    config.teachers[0].arrival = '09:30'
    config.teachers[0].departure = '10:45'
    result = generate(config)
    assert result['status'] == 'infeasible'
    assert {'TEACHER_AVAILABILITY','LAB_AVAILABILITY'} <= {x['code'] for x in result['issues']}

def test_real_infeasible_search_explains_no_gap_conflict():
    config = small_config()
    config.teachers[0].arrival = '10:00'
    # Total hours and two-hour lab windows fit, but no teacher is available at 09:00.
    result = generate(config, 10)
    assert result['status'] == 'infeasible'
    assert result['entries'] == []
    assert any(x['code'] == 'CONTIGUOUS_DAY' for x in result['issues'])
    assert 'sufficient conflict set' in result['explanation']

def test_true_timeout_is_not_reported_as_impossible():
    result = generate(small_config(), 0.000001)
    assert result['status'] == 'timeout'
    assert result['issues'][0]['code'] == 'SEARCH_LIMIT'
    assert 'does not prove' in result['issues'][0]['problem']

def test_early_departure_is_respected():
    config = small_config()
    config.teachers[0].departure = '12:00'
    result = generate(config, 10)
    assert result['status'] == 'feasible'
    verify_timetable(config, result['entries'])
    assert all(e['slot']+e['duration'] <= 3 for e in result['entries'])

def test_labs_never_cross_lunch_or_end_of_day():
    config = small_config()
    config.teachers[0].max_hours = 40
    config.offerings[0].lectures = 20
    config.offerings[0].labs = 10
    result = generate(config, 10)
    assert result['status'] == 'feasible'
    verify_timetable(config, result['entries'])
    assert {e['slot'] for e in result['entries']} & {6,7}

def test_empty_configuration_is_actionable():
    result = generate(Configuration())
    assert result['status'] == 'infeasible'
    assert result['issues'][0]['code'] == 'EMPTY_DATA'

def test_room_and_elective_capacity(sample):
    data = sample.model_dump()
    for item in data['offerings']:
        item['lectures'] = 4
        item['labs'] = 0
    for group in data['groups']:
        group['room_id'] = data['groups'][0]['room_id']
    config = Configuration(**data)
    result = generate(config)
    assert result['status'] == 'infeasible'
    assert 'ROOM_CAPACITY' in {x['code'] for x in result['issues']}
