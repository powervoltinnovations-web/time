"""Apply only the reviewed teacher assignments to an existing local database."""
import argparse
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import sqlite3

from app.domain import Configuration
from app import storage

ROOT = Path(__file__).resolve().parent


def apply_corrections(configuration, corrections):
    result = deepcopy(configuration)
    for profile in corrections["new_teachers"]:
        matches = [t for t in result["teachers"]
                   if t["short_code"].casefold() == profile["short_code"].casefold()
                   or t["name"].casefold() == profile["name"].casefold()]
        if len(matches) > 1:
            raise ValueError(f'Ambiguous teacher: {profile["name"]}')
        if not matches:
            if any(t["id"] == profile["id"] for t in result["teachers"]):
                raise ValueError(f'Teacher identifier already exists: {profile["id"]}')
            result["teachers"].append(deepcopy(profile))
    changes = []
    groups = {g["id"]: g for g in result["groups"]}
    batches = {b["id"]: b for b in result["batches"]}
    subjects = {s["id"]: s for s in result["subjects"]}
    teachers = {t["id"]: t for t in result["teachers"]}
    for update in corrections["assignments"]:
        targets = [o for o in result["offerings"]
                   if groups[o["group_id"]]["semester"] == update["semester"]
                   and groups[o["group_id"]]["division"] == update["division"]
                   and subjects[o["subject_id"]]["code"] == update["subject_code"]
                   and subjects[o["subject_id"]]["department_id"] == "it"
                   and (batches[o["batch_id"]]["name"] if o["batch_id"] else "") == update["batch"]
                   and o["labs" if update["kind"] == "lab" else "lectures"] > 0]
        faculty = [t for t in result["teachers"] if t["short_code"] == update["teacher"]]
        if len(targets) != 1 or len(faculty) != 1:
            raise ValueError(f'Expected one assignment and teacher for {update}; '
                             f'found {len(targets)} assignment(s), {len(faculty)} teacher(s). No data saved.')
        offering, teacher = targets[0], faculty[0]
        previous = teachers.get(offering["teacher_id"], {}).get("short_code", "")
        offering["teacher_id"] = teacher["id"]
        changes.append({**update, "previous_teacher": previous, "changed": previous != update["teacher"]})
    Configuration(**result)
    return result, changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    # Honor the application's database override without displaying its value.
    import os
    database = Path(os.environ.get("UNISCHED_DB", str(storage.DEFAULT_DB)))
    if not database.exists():
        print("No existing database to update. Start the application to load the corrected seed data.")
        return
    current = storage.get_config()
    corrections = json.loads((ROOT / "sample_data" / "reviewed_corrections.json").read_text())
    updated, changes = apply_corrections(current["configuration"], corrections)
    for item in changes:
        print(f'Sem {item["semester"]} {item["division"]} {item["batch"] or "division"} '
              f'{item["subject_code"]}: {item["previous_teacher"]} -> {item["teacher"]}'
              + ("" if item["changed"] else " (already correct)"))
    if args.dry_run:
        print("Preview only; database unchanged.")
        return
    if updated == current["configuration"]:
        print("All reviewed corrections are already applied; no changes needed.")
        return
    backup = database.parent / "backups" / ("before-reviewed-update-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".db")
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as source, sqlite3.connect(backup) as target:
        source.backup(target)
    storage.save_config(updated, current["revision"])
    print("Reviewed assignments saved. Existing faculty settings, unrelated data and saved timetables preserved.")
    print("A database backup was saved under data/backups (or beside your custom database).")
    print("Restart the application and generate a new timetable.")


if __name__ == "__main__":
    main()
