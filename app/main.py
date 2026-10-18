from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from collections import deque
import json
import time
import sys
import platform
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError
from typing import Literal
from fastapi import FastAPI, File, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError, field_validator
from . import storage
from .domain import Configuration, COLLEGE, DAYS, PERIODS, parse_csv, configuration_csv
from .scheduler import generate, preflight
from .exports import pdf, excel
from .exchange import configuration_csv_v2, configuration_excel, parse_upload
from .analytics import analyze
from .demo import presentation_config
from .calendar import Settings
from .editing import edit_result
from . import assistant

ROOT = Path(__file__).resolve().parent.parent
generation_lock = Lock()
process_started = time.monotonic()
request_times = deque(maxlen=500)

@asynccontextmanager
async def lifespan(app):
    storage.initialize()
    if storage.get_config()['revision'] == 0:
        sample = presentation_config()
        try:
            storage.save_config(sample.model_dump(), 0)
        except storage.RevisionConflict:
            pass
    yield

app = FastAPI(title='UniSched API', version='2.0.0', lifespan=lifespan)

@app.middleware('http')
async def measure_requests(request, call_next):
    started = time.monotonic()
    response = await call_next(request)
    request_times.append((time.monotonic()-started)*1000)
    return response

class ConfigUpdate(BaseModel):
    revision: int = Field(ge=0)
    configuration: Configuration

class GenerateRequest(BaseModel):
    name: str = Field(default='Odd semester timetable', min_length=1, max_length=80)
    time_limit: int = Field(default=20, ge=5, le=120)
    department_id: str | None = None
    semester: int | None = Field(default=None, ge=1, le=8)
    group_ids: list[str] | None = Field(default=None, max_length=30)
    base_generation_id: int | None = Field(default=None, ge=1)
    continue_latest: bool = True
    classroom_run_length: int | None = Field(default=None, ge=1, le=3, strict=True)

    @field_validator('name')
    @classmethod
    def printable_name(cls, value):
        if any(ord(char) < 32 for char in value):
            raise ValueError('Timetable names cannot contain control characters or line breaks.')
        return value

class AssistantRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1500)
    generation_id: int | None = Field(default=None, ge=1)
    entry_index: int | None = Field(default=None, ge=0)
    mode: Literal['local','openai'] = 'local'

@app.get('/api/assistant/status')
def assistant_status():
    return assistant.status()

@app.post('/api/assistant/ask')
def ask_assistant(payload: AssistantRequest):
    if not payload.question.strip():
        raise HTTPException(422,'Enter a timetable question.')
    if payload.entry_index is not None and payload.generation_id is None:
        raise HTTPException(422,'Select one timetable before selecting a session.')
    if payload.generation_id is not None:
        record=storage.get_generation(payload.generation_id)
        if record is None: raise HTTPException(404,'Timetable not found.')
        records=[record]
    else:
        records=[storage.get_generation(r['id']) for r in storage.generations()]
    if not records:
        raise HTTPException(422,'Generate or select a saved timetable first.')
    try:
        answer,facts=assistant.local_advice(records,payload.question,payload.entry_index)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    response={'answer':answer,'local_answer':answer,'facts':facts,'mode':'local','online_error':None}
    if payload.mode=='openai':
        try:
            response['answer']=assistant.explain_with_openai(payload.question,facts)
            response['mode']='openai'
        except ValueError as exc:
            response['online_error']=str(exc)
    return response

@app.get('/api/health')
def health():
    with storage.connect() as db:
        db.execute('SELECT 1').fetchone()
    return {'status': 'ok', 'database': 'sqlite'}

@app.get('/api/meta')
def meta():
    config = Configuration(**storage.get_config()['configuration'])
    return {'college': COLLEGE, **config.settings.meta(), 'recess': ['13:00','13:45']}

@app.get('/api/config')
def configuration():
    return storage.get_config()

@app.put('/api/config')
def save_configuration(payload: ConfigUpdate):
    try:
        revision = storage.save_config(payload.configuration.model_dump(), payload.revision)
    except storage.RevisionConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return {'revision': revision, 'configuration': payload.configuration.model_dump()}

@app.get('/api/config.csv')
def export_configuration():
    body = configuration_csv_v2(Configuration(**storage.get_config()['configuration']))
    return Response('\ufeff'+body, media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="unisched-academic-data.csv"'})

@app.get('/api/sample.csv')
def sample_csv():
    return FileResponse(ROOT/'sample_data'/'unisched_semesters_3_5_7.csv', media_type='text/csv', filename='unisched_semesters_3_5_7.csv')

@app.post('/api/import/preview')
async def import_preview(file: UploadFile = File(...)):
    try:
        config = parse_upload(await file.read(1_000_001), file.filename or 'data.csv')
    except (ValueError, ValidationError, KeyError, TypeError, BadZipFile, ParseError, StopIteration) as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        await file.close()
    return {'configuration': config.model_dump(), 'counts': {k: len(v) for k,v in config.model_dump().items() if isinstance(v,list)},
            'issues': preflight(config)}

@app.get('/api/validate')
def validate_configuration():
    config = Configuration(**storage.get_config()['configuration'])
    return {'issues': preflight(config)}

@app.post('/api/calendar/preview')
def preview_calendar(settings: Settings):
    return settings.meta()

@app.get('/api/generations')
def generation_list():
    return storage.generations()

@app.post('/api/generations')
def generate_timetable(payload: GenerateRequest):
    if not generation_lock.acquire(blocking=False):
        raise HTTPException(409, 'A timetable is already being generated. Please wait for it to finish.')
    try:
        current = storage.get_config()
        config = Configuration(**current['configuration'])
        if payload.classroom_run_length is not None:
            config.settings.classroom_run_length = payload.classroom_run_length
        groups = [g for g in config.groups if (not payload.department_id or g.department_id == payload.department_id)
                  and (not payload.semester or g.semester == payload.semester)]
        if payload.group_ids is not None:
            if not set(payload.group_ids) <= {g.id for g in groups}:
                raise HTTPException(422,'Selected divisions must belong to the chosen department and semester.')
            groups = [g for g in groups if g.id in payload.group_ids]
        if not groups:
            raise HTTPException(422,'Choose at least one division with academic data.')
        base = None
        if payload.base_generation_id:
            base = storage.get_generation(payload.base_generation_id)
            if not base or base['result']['status'] != 'feasible' or base['config_revision'] != current['revision'] or base['config']['settings']!=config.settings.model_dump():
                raise HTTPException(409,'The base timetable must be successful and use the current academic data. Generate a fresh complete plan after editing data.')
        elif payload.continue_latest:
            for candidate in storage.generations():
                if candidate['status']=='feasible' and candidate['config_revision']==current['revision']:
                    saved=storage.get_generation(candidate['id'])
                    if saved['config']['settings']==config.settings.model_dump():
                        base=saved
                        break
        result = generate(config, payload.time_limit, [g.id for g in groups], base['result']['entries'] if base else [])
        result['scope']['base_generation_id'] = base['id'] if base else None
        identifier = storage.save_generation(payload.name.strip() or 'Timetable', current['revision'], config.model_dump(), result)
        return storage.get_generation(identifier)
    finally:
        generation_lock.release()

@app.get('/api/generations/{identifier}')
def generation_detail(identifier: int):
    result = storage.get_generation(identifier)
    if result is None:
        raise HTTPException(404, 'Timetable not found.')
    return result

@app.delete('/api/generations/{identifier}')
def delete_timetable(identifier: int, revision: int = Query(ge=0)):
    if not generation_lock.acquire(blocking=False):
        raise HTTPException(409,'A timetable is being generated. Wait for it to finish before deleting.')
    try:
        try:
            removed=storage.delete_generation(identifier,revision)
        except storage.RevisionConflict as exc:
            raise HTTPException(409,str(exc)) from exc
        if not removed:
            raise HTTPException(404,'Timetable not found.')
        return {'deleted':identifier}
    finally:
        generation_lock.release()

class WorkflowUpdate(BaseModel):
    revision: int = Field(ge=0)
    action: Literal['draft','approve','lock','unlock']


class PlacementChange(BaseModel):
    entry_index: int = Field(ge=0, strict=True)
    day: int = Field(ge=0, le=6, strict=True)
    slot: int = Field(ge=0, le=15, strict=True)
    room_id: str = Field(min_length=1,max_length=80)


class ManualEdit(BaseModel):
    revision: int = Field(ge=0)
    changes: list[PlacementChange] = Field(min_length=1,max_length=1200)


@app.patch('/api/generations/{identifier}/workflow')
def update_workflow(identifier: int, payload: WorkflowUpdate):
    record=generation_detail(identifier)
    if record['result']['status']!='feasible':
        raise HTTPException(409,'Only successful timetables have draft, approval, and lock controls.')
    if payload.action=='approve':
        audit=analyze(record)
        if audit['hard_conflicts']:
            raise HTTPException(422,'Approval blocked: '+'; '.join(audit['violations']))
    try:
        storage.change_workflow(identifier,payload.revision,payload.action)
    except storage.RevisionConflict as exc:
        raise HTTPException(409,str(exc)) from exc
    return generation_detail(identifier)


@app.post('/api/generations/{identifier}/edits')
def manually_edit(identifier: int, payload: ManualEdit):
    record=generation_detail(identifier)
    if record['result']['status']!='feasible':
        raise HTTPException(409,'Only successful timetables can be edited.')
    workflow=record['workflow']
    if workflow['locked'] or workflow['state']!='draft':
        raise HTTPException(409,'Unlock the timetable and mark it Draft before editing.')
    if workflow['revision']!=payload.revision:
        raise HTTPException(409,'Timetable controls changed in another window. Reload before saving.')
    try:
        result,violations=edit_result(record,payload.changes)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    if violations:
        raise HTTPException(422,'Edit not saved. Fix these conflicts or swap the affected sessions together: '+ '\n• '.join(violations))
    try:
        new_id=storage.save_manual_version(record,payload.revision,(record['name'][:57]+' · Manual draft'),result)
    except storage.RevisionConflict as exc:
        raise HTTPException(409,str(exc)) from exc
    return generation_detail(new_id)


@app.get('/api/generations/{identifier}/analytics')
def generation_analytics(identifier: int):
    return analyze(generation_detail(identifier))

@app.get('/api/config.json')
def export_json():
    return Response(json.dumps(storage.get_config()['configuration'],indent=2),media_type='application/json',
                    headers={'Content-Disposition':'attachment; filename="unisched-academic-backup.json"'})

@app.get('/api/config.xlsx')
def export_excel_data():
    config = Configuration(**storage.get_config()['configuration'])
    return Response(configuration_excel(config),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition':'attachment; filename="unisched-academic-data.xlsx"'})

@app.get('/api/demo/{format}')
def demo_data(format: Literal['json','csv','xlsx']):
    config = presentation_config()
    body = config.model_dump_json(indent=2) if format=='json' else configuration_csv_v2(config) if format=='csv' else configuration_excel(config)
    return Response(body,media_type={'json':'application/json','csv':'text/csv','xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}[format],
                    headers={'Content-Disposition':f'attachment; filename="it_presentation.{format}"'})

@app.get('/api/performance')
def performance():
    rows = storage.generations()
    durations=[]
    solver_rows=[]
    for row in rows:
        record = storage.get_generation(row['id'])
        if record['result'].get('source')=='manual':
            continue
        solver_rows.append(row)
        row['duration'] = record['result'].get('elapsed_seconds',0)
        row['sessions'] = len(record['result']['entries'])
        durations.append(row['duration'])
    rows=solver_rows
    latency = sorted(request_times)
    peak_mb = None
    try:
        import resource
        peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024*1024 if sys.platform=='darwin' else 1024)
    except ImportError:
        if sys.platform=='win32':
            import ctypes
            from ctypes import wintypes
            class Counters(ctypes.Structure):
                _fields_ = [('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in
                    ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
            counters=Counters()
            counters.cb=ctypes.sizeof(counters)
            ctypes.windll.kernel32.GetCurrentProcess.restype=wintypes.HANDLE
            ctypes.windll.psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
            if ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),ctypes.byref(counters),counters.cb):
                peak_mb=counters.PeakWorkingSetSize/(1024*1024)
    return {'python':platform.python_version(),'platform':platform.system(),'uptime_seconds':round(time.monotonic()-process_started),
            'peak_memory_mb':round(peak_mb,1) if peak_mb is not None else None,'active_generation':generation_lock.locked(),
            'average_api_ms':round(sum(latency)/len(latency),2) if latency else None,
            'p95_api_ms':round(latency[min(len(latency)-1,int(len(latency)*.95))],2) if latency else None,
            'request_samples':len(latency),'average_generation_seconds':round(sum(durations)/len(durations),3) if durations else None,
            'success_rate':round(100*sum(r['status']=='feasible' for r in rows)/len(rows),1) if rows else None,
            'fastest_seconds':min(durations) if durations else None,'slowest_seconds':max(durations) if durations else None,
            'runs':rows,'measurement_note':'API latency covers the latest 500 completed requests in this process. Generation metrics cover solver runs among the latest 100 saved versions, including failed and timed-out searches; manual edits are excluded. Memory is peak resident process memory when available.'}

@app.get('/api/generations/{identifier}/export/{format}')
def export_generation(identifier: int, format: Literal['pdf','xlsx'], view: Literal['group','teacher','classroom','lab']='group', target: str | None = Query(default=None, max_length=80), batch: str | None = Query(default=None,max_length=80)):
    record = generation_detail(identifier)
    if record['result']['status'] != 'feasible':
        raise HTTPException(409, 'Only a successfully generated timetable can be exported.')
    try:
        body = pdf(record, view, target,batch) if format == 'pdf' else excel(record, view, target,batch)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    mime = 'application/pdf' if format == 'pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return Response(body, media_type=mime, headers={'Content-Disposition': f'attachment; filename="UniSched-{view}-{identifier}.{format}"'})

app.mount('/static', StaticFiles(directory=ROOT/'static'), name='static')

@app.get('/', include_in_schema=False)
def index():
    return FileResponse(ROOT/'static'/'index.html')
