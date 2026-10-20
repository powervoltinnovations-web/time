"""Reviewed mappings and preservation of local edits during the data update."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app import storage
from app.demo import presentation_config
from update_reviewed_data import apply_corrections

ROOT = Path(__file__).resolve().parents[1]
PATCH = json.loads((ROOT / "sample_data" / "reviewed_corrections.json").read_text())


def assignment(config, semester, division, batch, code):
    groups = {g["id"]: g for g in config["groups"]}
    subjects = {s["id"]: s for s in config["subjects"]}
    batches = {b["id"]: b for b in config["batches"]}
    return next(o for o in config["offerings"]
                if groups[o["group_id"]]["semester"] == semester
                and groups[o["group_id"]]["division"] == division
                and (batches[o["batch_id"]]["name"] if o["batch_id"] else "") == batch
                and subjects[o["subject_id"]]["code"] == code)


def test_reviewed_mappings_and_ignored_vsk_entry():
    config = presentation_config().model_dump()
    faculty = {t["id"]: t["short_code"] for t in config["teachers"]}
    expected = [
        (3, "B", "", "2343114", "JSP"),
        (3, "C", "C2", "2343115", "PMN"), (3, "C", "C2", "2343611", "GMA"),
        (3, "C", "C3", "2993511", "NYM"), (3, "C", "C3", "2343115", "PMN"),
        (5, "A", "A2", "2345115", "PMN"),
        (5, "B", "B1", "23451181", "DPK"), (5, "B", "B2", "23451181", "ADM"),
        (5, "B", "B2", "2345115", "ARR"), (5, "B", "B2", "2345116", "VGK"),
        (5, "C", "C1", "2345116", "JRG"), (5, "C", "C2", "2345511", "HS"),
        (5, "C", "C2", "MDL501", "KNS"), (5, "C", "C3", "2345511", "HS"),
        (7, "A", "A1", "ROSP", "RZ"), (7, "A", "A2", "ROSP", "RZ"),
    ]
    for semester, division, batch, code, teacher in expected:
        assert faculty[assignment(config, semester, division, batch, code)["teacher_id"]] == teacher
    assert faculty[assignment(config, 5, "B", "B3", "23451181")["teacher_id"]] == "KNS"
    assert faculty[assignment(config, 7, "A", "A3", "ROSP")["teacher_id"]] == "JSP"
    # Reassigned MECH faculty remains available even without a current assignment.
    assert any(t["short_code"] == "MECH" for t in config["teachers"])
    for code in ("HS", "RZ"):
        teacher = next(t for t in config["teachers"] if t["short_code"] == code)
        assert (teacher["max_hours"], teacher["max_daily_slots"]) == (20, 6)
        assert (teacher["arrival"], teacher["departure"]) == ("09:00", "17:45")


def test_updater_preserves_local_sad_changes_limits_and_other_data():
    config = presentation_config().model_dump()
    teachers = {t["short_code"]: t for t in config["teachers"]}
    teachers["PMN"]["max_daily_slots"] = 7
    teachers["KAJ"]["max_hours"] = 18
    teachers["HS"]["max_hours"] = 12
    for batch in ("A1", "A2", "A3"):
        assignment(config, 7, "A", batch, "SAD")["teacher_id"] = teachers["KAJ"]["id"]
    target = assignment(config, 3, "B", "", "2343114")
    target["teacher_id"] = teachers["DPK"]["id"]
    before = deepcopy(config)
    updated, changes = apply_corrections(config, PATCH)
    assert config == before  # preparation cannot partially mutate the caller
    for key in config:
        if key != "offerings":
            assert updated[key] == before[key]
    expected = deepcopy(before)
    assignment(expected, 3, "B", "", "2343114")["teacher_id"] = teachers["JSP"]["id"]
    assert updated == expected
    assert sum(c["changed"] for c in changes) == 1
    assert apply_corrections(updated, PATCH)[0] == updated


def test_missing_assignment_aborts_without_partial_mutation():
    config = presentation_config().model_dump()
    target = assignment(config, 3, "B", "", "2343114")
    config["offerings"].remove(target)
    before = deepcopy(config)
    with pytest.raises(ValueError, match="No data saved"):
        apply_corrections(config, PATCH)
    assert config == before


def test_database_update_backup_and_repeatability(tmp_path, monkeypatch):
    database = tmp_path / "data" / "unisched.db"
    monkeypatch.setenv("UNISCHED_DB", str(database))
    storage.initialize()
    config = presentation_config().model_dump()
    teachers = {t["short_code"]: t for t in config["teachers"]}
    assignment(config, 3, "B", "", "2343114")["teacher_id"] = teachers["DPK"]["id"]
    teachers["PMN"]["max_daily_slots"] = 7
    storage.save_config(config, 0)
    identifier = storage.save_generation("Historical record", 1, config,
                                         {"status": "infeasible", "entries": [], "issues": []})
    snapshot = storage.get_generation(identifier)
    command = [sys.executable, str(ROOT / "update_reviewed_data.py")]
    subprocess.run(command + ["--dry-run"], cwd=ROOT, env=os.environ, check=True, capture_output=True)
    assert storage.get_config()["configuration"] == config
    subprocess.run(command, cwd=ROOT, env=os.environ, check=True, capture_output=True)
    updated = storage.get_config()
    assert updated["configuration"] == apply_corrections(config, PATCH)[0]
    assert len(list((database.parent / "backups").glob("*.db"))) == 1
    assert storage.get_generation(identifier) == snapshot
    subprocess.run(command, cwd=ROOT, env=os.environ, check=True, capture_output=True)
    assert storage.get_config() == updated
    assert len(list((database.parent / "backups").glob("*.db"))) == 1
