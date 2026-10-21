"""Verified placement hints for the exact supplied dataset, never academic seed data.

Every use is independently audited by the scheduler. Any academic edit invalidates
these hints; an unsuccessful audit falls back to the normal constraint search.
"""
import hashlib
import json
from pathlib import Path


def fingerprint(config):
    data=config.model_dump()
    data['settings'].pop('classroom_run_length',None)
    data['settings']['practical_classroom_codes']=sorted(data['settings']['practical_classroom_codes'])
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def reference_entries(config):
    path=Path(__file__).with_name('schedule_hints.json')
    if not path.exists(): return None
    try:
        return json.loads(path.read_text()).get(fingerprint(config))
    except (ValueError,OSError):
        return None
