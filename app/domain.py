"""Validated academic records with backwards-compatible CSV import."""
import csv
import io
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .calendar import Settings

COLLEGE = 'Datta Meghe College of Engineering, Airoli, Navi Mumbai'
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
PERIODS = [('09:00', '10:00'), ('10:00', '11:00'), ('11:00', '12:00'),
           ('12:00', '13:00'), ('13:45', '14:45'), ('14:45', '15:45'),
           ('15:45', '16:45'), ('16:45', '17:45')]
CSV_FIELDS = ['semester', 'division', 'teacher_name', 'teacher_hours_per_week',
              'teacher_arrival', 'teacher_departure', 'subject_name', 'subject_code',
              'elective', 'classroom', 'lab_room', 'lectures_per_week', 'labs_per_week']

def minutes(value):
    hour, minute = map(int, value.split(':'))
    return hour * 60 + minute

class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')

    @field_validator('*')
    @classmethod
    def printable_text(cls, value):
        if isinstance(value, str) and any(ord(char) < 32 for char in value):
            raise ValueError('Text fields cannot contain control characters or line breaks.')
        return value

class Teacher(Record):
    name: str = Field(min_length=1, max_length=100)
    max_hours: int = Field(ge=1, le=60, strict=True)
    department_id: str = 'general'
    email: str = Field(default='', max_length=120)
    short_code: str = Field(default='', max_length=20)
    max_daily_slots: int = Field(default=8, ge=1, le=16, strict=True)
    lab_eligible: bool = True
    arrival: str
    departure: str

    @field_validator('arrival', 'departure')
    @classmethod
    def valid_time(cls, value):
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
            raise ValueError('Use a 24-hour time such as 09:00 or 17:45.')
        return value

    @model_validator(mode='after')
    def time_order(self):
        if not 360 <= minutes(self.arrival) < minutes(self.departure) <= 1320:
            raise ValueError('Arrival and departure must be ordered within 06:00–22:00.')
        if self.email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', self.email):
            raise ValueError('Enter a valid email address or leave it blank.')
        return self

class Subject(Record):
    name: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=30)
    semester: int = Field(strict=True)
    elective: bool = False
    department_id: str = 'general'
    elective_set_id: str | None = None
    course_type: str = Field(default='theory', pattern=r'^(theory|lab|project|mixed)$')
    weekly_hours: int = Field(default=3, ge=1, le=40, strict=True)

    @field_validator('semester')
    @classmethod
    def semester_allowed(cls, value):
        if value not in range(1,9):
            raise ValueError('Semester must be between 1 and 8.')
        return value

class Room(Record):
    name: str = Field(min_length=1, max_length=50)
    kind: str = Field(pattern=r'^(classroom|lab)$')
    capacity: int = Field(default=80, ge=1, le=500, strict=True)
    department_id: str | None = None
    eligible_years: list[int] = Field(default_factory=list)

    @field_validator('eligible_years')
    @classmethod
    def valid_years(cls, value):
        if len(set(value)) != len(value) or any(year not in (1,2,3,4) for year in value):
            raise ValueError('Eligible years must be unique values from 1 to 4, or empty for all years.')
        return value

class Group(Record):
    semester: int = Field(strict=True)
    division: str = Field(min_length=1, max_length=12)
    room_id: str | None = None
    department_id: str = 'general'
    strength: int = Field(default=60, ge=1, le=500, strict=True)
    _semester = field_validator('semester')(Subject.semester_allowed.__func__)

class Offering(Record):
    group_id: str
    subject_id: str
    teacher_id: str
    lectures: int = Field(ge=0, le=40, strict=True)
    labs: int = Field(ge=0, le=20, strict=True)
    lab_room_id: str | None = None
    projects: int = Field(default=0, ge=0, le=20, strict=True)
    batch_id: str | None = None
    project_room_id: str | None = None
    project_hours: float | None = Field(default=None, ge=0.5, le=8, allow_inf_nan=False)

    @model_validator(mode='after')
    def nonempty(self):
        if self.lectures + self.labs + self.projects == 0:
            raise ValueError('An assignment needs at least one lecture, lab, or project per week.')
        if self.batch_id and self.lectures:
            raise ValueError('Batch assignments are for labs/projects; assign lectures to the whole division.')
        return self

class Department(Record):
    name: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=20)

class Batch(Record):
    group_id: str
    name: str = Field(min_length=1, max_length=30)
    strength: int = Field(ge=1, le=500, strict=True)

class ElectiveSet(Record):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=30)
    department_id: str = 'general'
    semester: int
    _semester = field_validator('semester')(Subject.semester_allowed.__func__)

class Configuration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    teachers: list[Teacher] = Field(default_factory=list, max_length=100)
    subjects: list[Subject] = Field(default_factory=list, max_length=120)
    rooms: list[Room] = Field(default_factory=list, max_length=100)
    groups: list[Group] = Field(default_factory=list, max_length=30)
    offerings: list[Offering] = Field(default_factory=list, max_length=240)
    departments: list[Department] = Field(default_factory=lambda: [Department(id='general', name='General / existing academic data', code='GEN')], max_length=30)
    batches: list[Batch] = Field(default_factory=list, max_length=120)
    elective_sets: list[ElectiveSet] = Field(default_factory=list, max_length=80)
    settings: Settings = Field(default_factory=Settings)

    @model_validator(mode='after')
    def references(self):
        for field in ('teachers', 'subjects', 'rooms', 'groups', 'offerings', 'departments', 'batches', 'elective_sets'):
            items = getattr(self, field)
            if len({item.id for item in items}) != len(items):
                raise ValueError(f'Duplicate IDs in {field}.')
        for field, key in [('teachers', lambda x: x.name.casefold()),
                           ('subjects', lambda x: (x.department_id, x.code.casefold())),
                           ('rooms', lambda x: x.name.casefold()),
                           ('groups', lambda x: (x.department_id, x.semester, x.division.casefold())),
                           ('departments', lambda x: x.code.casefold()),
                           ('batches', lambda x: (x.group_id, x.name.casefold())),
                           ('elective_sets', lambda x: (x.department_id, x.semester, x.code.casefold()))]:
            items = getattr(self, field)
            if len({key(item) for item in items}) != len(items):
                raise ValueError(f'Duplicate names, codes, or divisions in {field}.')
        teachers = {x.id: x for x in self.teachers}
        subjects = {x.id: x for x in self.subjects}
        rooms = {x.id: x for x in self.rooms}
        groups = {x.id: x for x in self.groups}
        departments = {x.id for x in self.departments}
        batches = {x.id: x for x in self.batches}
        elective_sets = {x.id: x for x in self.elective_sets}
        for item in [*self.teachers, *self.subjects, *self.groups, *self.elective_sets, *self.rooms]:
            if item.department_id is not None and item.department_id not in departments:
                raise ValueError(f'{item.id} references a missing department.')
        for batch in self.batches:
            if batch.group_id not in groups:
                raise ValueError(f'Batch {batch.name} references a missing division.')
        for group in self.groups:
            if sum(b.strength for b in self.batches if b.group_id == group.id) > group.strength:
                raise ValueError(f'Batch strengths exceed the student count for Division {group.division}.')
        for subject in self.subjects:
            if subject.elective_set_id:
                item = elective_sets.get(subject.elective_set_id)
                if not item or not subject.elective or (item.department_id,item.semester) != (subject.department_id,subject.semester):
                    raise ValueError(f'{subject.code} needs an elective set from its own department and semester.')
        pairs = set()
        for group in self.groups:
            if group.room_id and (group.room_id not in rooms or rooms[group.room_id].kind != 'classroom'):
                raise ValueError(f'Division {group.division} needs a valid classroom.')
        for item in self.offerings:
            if item.projects and item.project_hours is not None and not (item.project_hours*60/self.settings.period_minutes).is_integer():
                raise ValueError('Mini-project hours must fit a whole number of teaching periods.')
            if item.group_id not in groups or item.subject_id not in subjects or item.teacher_id not in teachers:
                raise ValueError(f'Assignment {item.id} references a missing division, subject, or teacher.')
            if groups[item.group_id].semester != subjects[item.subject_id].semester:
                raise ValueError(f'Assignment {item.id}: subject and division semesters must match.')
            if groups[item.group_id].department_id != subjects[item.subject_id].department_id:
                raise ValueError(f'Assignment {item.id}: subject and division departments must match.')
            if item.batch_id and (item.batch_id not in batches or batches[item.batch_id].group_id != item.group_id):
                raise ValueError(f'Assignment {item.id} references an invalid lab batch.')
            if item.project_room_id and item.project_room_id not in rooms:
                raise ValueError(f'Assignment {item.id} references an invalid project room.')
            if item.lab_room_id and (item.lab_room_id not in rooms or rooms[item.lab_room_id].kind != 'lab'):
                raise ValueError(f'Assignment {item.id} references an invalid laboratory.')
            pair = (item.group_id, item.subject_id, item.batch_id)
            if pair in pairs:
                raise ValueError('Each division/subject pair must have exactly one teacher assignment.')
            pairs.add(pair)
        return self

def parse_csv(raw: bytes) -> Configuration:
    if len(raw) > 1_000_000:
        raise ValueError('CSV must be smaller than 1 MB.')
    try:
        content = raw.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('Save the CSV with UTF-8 encoding.') from exc
    reader = csv.DictReader(io.StringIO(content))
    if reader.fieldnames != CSV_FIELDS:
        from .exchange import parse_extended_csv
        return parse_extended_csv(content)
    maps = {key: {} for key in ('teachers', 'subjects', 'rooms', 'groups')}
    offerings = []

    def add(category, key, values):
        existing = maps[category].get(key)
        if existing:
            if {k: v for k, v in existing.items() if k != 'id'} != values:
                raise ValueError(f'Conflicting repeated {category} details for {key}.')
            return existing['id']
        identifier = category[0] + str(len(maps[category]) + 1)
        maps[category][key] = {'id': identifier, **values}
        return identifier

    for row_number, row in enumerate(reader, 2):
        try:
            if len(offerings) >= 240:
                raise ValueError('At most 240 teaching assignments are supported.')
            if None in row or any(v is None for v in row.values()):
                raise ValueError('Incorrect number of CSV columns.')
            row = {k: v.strip() for k, v in row.items()}
            if row['elective'].lower() not in ('true', 'false', 'yes', 'no', '1', '0'):
                raise ValueError('Elective must be true/false, yes/no, or 1/0.')
            semester = int(row['semester'])
            teacher = add('teachers', row['teacher_name'].casefold(), {
                'name': row['teacher_name'], 'max_hours': int(row['teacher_hours_per_week']),
                'arrival': row['teacher_arrival'], 'departure': row['teacher_departure']})
            subject = add('subjects', row['subject_code'].casefold(), {
                'name': row['subject_name'], 'code': row['subject_code'], 'semester': semester,
                'elective': row['elective'].lower() in ('true', 'yes', '1')})
            room = add('rooms', row['classroom'].casefold(), {'name': row['classroom'], 'kind': 'classroom'})
            lab = None
            if row['lab_room']:
                lab = add('rooms', row['lab_room'].casefold(), {'name': row['lab_room'], 'kind': 'lab'})
            group = add('groups', (semester, row['division'].casefold()), {
                'semester': semester, 'division': row['division'].upper(), 'room_id': room})
            offerings.append({'id': f'o{len(offerings)+1}', 'group_id': group, 'subject_id': subject,
                              'teacher_id': teacher, 'lectures': int(row['lectures_per_week']),
                              'labs': int(row['labs_per_week']), 'lab_room_id': lab})
        except (ValueError, KeyError) as exc:
            raise ValueError(f'CSV row {row_number}: {exc}') from exc
    if not offerings:
        raise ValueError('The CSV has no teaching assignments.')
    return Configuration(**{k: list(v.values()) for k, v in maps.items()}, offerings=offerings)

def configuration_csv(config: Configuration):
    maps = {key: {x.id: x for x in getattr(config, key)} for key in ('teachers', 'subjects', 'rooms', 'groups')}
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for item in config.offerings:
        teacher, subject, group = maps['teachers'][item.teacher_id], maps['subjects'][item.subject_id], maps['groups'][item.group_id]
        row = dict(zip(CSV_FIELDS, [group.semester, group.division, teacher.name, teacher.max_hours,
            teacher.arrival, teacher.departure, subject.name, subject.code, str(subject.elective).lower(),
            maps['rooms'][group.room_id].name if group.room_id else 'AUTO', maps['rooms'][item.lab_room_id].name if item.lab_room_id else '',
            item.lectures, item.labs]))
        # Protect spreadsheet users from formula interpretation of arbitrary names.
        writer.writerow({k: "'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r')) else v for k, v in row.items()})
    return output.getvalue()
