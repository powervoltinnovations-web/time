"""SQLite persistence: editable configuration plus immutable generation snapshots."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / 'data' / 'unisched.db'

@contextmanager
def connect():
    path = Path(os.environ.get('UNISCHED_DB', str(DEFAULT_DB)))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA journal_mode=WAL')
    try:
        with connection:
            yield connection
    finally:
        connection.close()

def initialize():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS configuration (
            id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        CREATE TABLE IF NOT EXISTS generations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            config_revision INTEGER NOT NULL, config TEXT NOT NULL,
            result TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS generation_workflow (
            generation_id INTEGER PRIMARY KEY REFERENCES generations(id),
            state TEXT NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','approved')),
            locked INTEGER NOT NULL DEFAULT 0 CHECK(locked IN (0,1)),
            revision INTEGER NOT NULL DEFAULT 0
        );
        ''')

def get_config():
    from .domain import Configuration
    with connect() as db:
        row = db.execute('SELECT * FROM configuration WHERE id=1').fetchone()
    if not row:
        return {'revision': 0, 'configuration': Configuration().model_dump()}
    # Add schema defaults in memory; never rewrite a user's old configuration on read.
    return {'revision': row['revision'], 'configuration': Configuration(**json.loads(row['body'])).model_dump()}

class RevisionConflict(Exception):
    pass

def save_config(config, expected_revision):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT revision FROM configuration WHERE id=1').fetchone()
        current = row['revision'] if row else 0
        if current != expected_revision:
            raise RevisionConflict('Academic data changed in another window. Reload before saving.')
        db.execute('''INSERT INTO configuration(id,body,revision) VALUES(1,?,?)
            ON CONFLICT(id) DO UPDATE SET body=excluded.body, revision=excluded.revision,
            updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')''', (json.dumps(config), current+1))
    return current+1

def save_generation(name, revision, config, result):
    with connect() as db:
        cursor = db.execute('INSERT INTO generations(name,config_revision,config,result) VALUES(?,?,?,?)',
                            (name, revision, json.dumps(config), json.dumps(result)))
        return cursor.lastrowid

def get_generation(identifier):
    from .domain import Configuration, COLLEGE
    with connect() as db:
        row = db.execute('SELECT * FROM generations WHERE id=?', (identifier,)).fetchone()
        workflow = _workflow(db,identifier)
    if not row:
        return None
    snapshot=json.loads(row['config'])
    snapshot.setdefault('settings',{}).setdefault('spread_lectures',False)
    config = Configuration(**snapshot)
    return {**dict(row), 'config': config.model_dump(), 'result': json.loads(row['result']),
            'workflow':workflow, 'meta': {'college':COLLEGE, **config.settings.meta()}}

def generations():
    with connect() as db:
        rows = db.execute('''SELECT id,name,created_at,config_revision,
            json_extract(result,'$.status') AS status,
            json_extract(result,'$.summary.teaching_hours') AS teaching_hours,
            COALESCE(json_extract(config,'$.settings.spread_lectures'),0) AS spread_lectures,
            COALESCE(json_extract(config,'$.settings.classroom_run_length'),1) AS classroom_run_length
            FROM generations ORDER BY id DESC LIMIT 100''').fetchall()
        output=[{**dict(row),'workflow':_workflow(db,row['id'])} for row in rows]
    return output


def delete_generation(identifier, expected_revision):
    """Delete one unlocked saved version and its controls atomically."""
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT id FROM generations WHERE id=?',(identifier,)).fetchone():
            return False
        workflow=_workflow(db,identifier)
        if workflow['revision'] != expected_revision:
            raise RevisionConflict('Timetable controls changed in another window. Reload before deleting.')
        if workflow['locked']:
            raise RevisionConflict('Unlock this timetable before deleting it.')
        db.execute('DELETE FROM generation_workflow WHERE generation_id=?',(identifier,))
        db.execute('DELETE FROM generations WHERE id=?',(identifier,))
        return True


def _workflow(db, identifier):
    row = db.execute('SELECT state,locked,revision FROM generation_workflow WHERE generation_id=?',(identifier,)).fetchone()
    return {'state':row['state'],'locked':bool(row['locked']),'revision':row['revision']} if row else {'state':'draft','locked':False,'revision':0}


def _write_workflow(db, identifier, workflow):
    db.execute('''INSERT INTO generation_workflow(generation_id,state,locked,revision) VALUES(?,?,?,?)
        ON CONFLICT(generation_id) DO UPDATE SET state=excluded.state,locked=excluded.locked,revision=excluded.revision''',
        (identifier,workflow['state'],int(workflow['locked']),workflow['revision']))


def change_workflow(identifier, expected_revision, action):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT id FROM generations WHERE id=?',(identifier,)).fetchone():
            raise RevisionConflict('This timetable no longer exists.')
        workflow=_workflow(db,identifier)
        if workflow['revision'] != expected_revision:
            raise RevisionConflict('Timetable controls changed in another window. Reload before continuing.')
        if workflow['locked'] and action != 'unlock':
            raise RevisionConflict('Unlock this timetable before changing its status.')
        if action in ('draft','approve'):
            workflow['state']='approved' if action=='approve' else 'draft'
        else:
            workflow['locked']=action=='lock'
        workflow['revision']+=1
        _write_workflow(db,identifier,workflow)


def save_manual_version(source, expected_revision, name, result):
    """Validate workflow and create the immutable edited snapshot in one transaction."""
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        workflow=_workflow(db,source['id'])
        if workflow['revision'] != expected_revision:
            raise RevisionConflict('This timetable changed in another window. Reload before saving your edit.')
        if workflow['locked'] or workflow['state']!='draft':
            raise RevisionConflict('Manual editing requires an unlocked Draft timetable.')
        cursor=db.execute('INSERT INTO generations(name,config_revision,config,result) VALUES(?,?,?,?)',
                          (name,source['config_revision'],json.dumps(source['config']),json.dumps(result)))
        workflow['revision']+=1
        _write_workflow(db,source['id'],workflow)
        return cursor.lastrowid
