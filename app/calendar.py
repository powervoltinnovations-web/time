"""Validated college calendar shared by the solver, screens, and exports."""
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

def minutes(value):
    hour, minute = map(int, value.split(':'))
    return hour * 60 + minute

def clock(value):
    return f'{value//60:02d}:{value%60:02d}'

def time_string(value):
    if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
        raise ValueError('Use a 24-hour time such as 09:00 or 17:45.')
    return value

class Break(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(default='Recess', min_length=1, max_length=40)
    start: str = '13:00'
    duration: int = Field(default=45, ge=5, le=120, strict=True)
    _time = field_validator('start')(time_string)

class Block(BaseModel):
    model_config = ConfigDict(extra='forbid')
    day: str
    slot: int = Field(ge=0, le=15, strict=True)
    reason: str = Field(default='College activity', min_length=1, max_length=60)

class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    start: str = '09:00'
    end: str = '17:45'
    period_minutes: int = Field(default=60, ge=30, le=90, strict=True)
    days: list[str] = Field(default_factory=lambda: WEEKDAYS[:5], min_length=1, max_length=7)
    breaks: list[Break] = Field(default_factory=lambda: [Break()], max_length=4)
    blocked: list[Block] = Field(default_factory=list, max_length=40)
    spread_lectures: bool = True
    classroom_run_length: int = Field(default=1, ge=1, le=3, strict=True)
    lecture_slots: int = Field(default=1, ge=1, le=2, strict=True)
    lab_slots: int = Field(default=2, ge=1, le=4, strict=True)
    project_slots: int = Field(default=4, ge=1, le=6, strict=True)
    _time = field_validator('start', 'end')(time_string)

    @model_validator(mode='after')
    def valid_calendar(self):
        if not 360 <= minutes(self.start) < minutes(self.end) <= 1320:
            raise ValueError('College operating hours must be ordered within 06:00–22:00.')
        if len(set(self.days)) != len(self.days) or any(day not in WEEKDAYS for day in self.days):
            raise ValueError('Select unique, valid working days.')
        self.days.sort(key=WEEKDAYS.index)
        previous = minutes(self.start)
        for pause in sorted(self.breaks, key=lambda b: b.start):
            begin = minutes(pause.start)
            if begin < previous or begin+pause.duration > minutes(self.end):
                raise ValueError('Breaks must be within college hours and must not overlap.')
            if (begin-previous) % self.period_minutes:
                raise ValueError('Every break must begin at a teaching-period boundary.')
            previous = begin+pause.duration
        if (minutes(self.end)-previous) % self.period_minutes:
            raise ValueError('Operating hours and breaks must fit complete teaching periods. Adjust the end time.')
        count = len(self.periods())
        if not 1 <= count <= 16:
            raise ValueError('The calendar must contain between 1 and 16 teaching periods per day.')
        keys = [(b.day,b.slot) for b in self.blocked]
        if len(set(keys)) != len(keys) or any(b.day not in self.days or b.slot >= count for b in self.blocked):
            raise ValueError('Blocked periods must be unique and refer to an active day and period.')
        return self

    def periods(self):
        pauses = {minutes(b.start): b.duration for b in self.breaks}
        result, current = [], minutes(self.start)
        while current < minutes(self.end):
            if current in pauses:
                current += pauses[current]
            else:
                result.append((clock(current), clock(current+self.period_minutes)))
                current += self.period_minutes
        return result

    def available(self, day):
        return [slot for slot in range(len(self.periods())) if not any(b.day == self.days[day] and b.slot == slot for b in self.blocked)]

    def fits(self, day, slot, duration):
        periods = self.periods()
        if slot+duration > len(periods):
            return False
        available = self.available(day)
        return all(p in available for p in range(slot,slot+duration)) and all(
            periods[p][1] == periods[p+1][0] for p in range(slot,slot+duration-1))

    def meta(self):
        return {'days': self.days, 'periods': self.periods(), 'breaks': [b.model_dump() for b in self.breaks],
                'blocked': [b.model_dump() for b in self.blocked], 'start': self.start, 'end': self.end,
                'period_minutes': self.period_minutes, 'lecture_slots': self.lecture_slots,
                'lab_slots': self.lab_slots, 'project_slots': self.project_slots, 'spread_lectures':self.spread_lectures,'classroom_run_length':self.classroom_run_length}
