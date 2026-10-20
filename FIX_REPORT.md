# Validation and remaining source-data conflicts

## Changes

Lectures/tutorials require classrooms; laboratory sessions require laboratories. The older option that enabled classroom practicals and combined batches has been removed. Legacy settings cannot bypass the rule. Manual room lists, independent audits, and saved-placement reuse enforce the same rule.

Subject name/code/default-hour edits persist. Existing assignment counts can be edited through **Edit linked assignments**. Semester/department changes must remain compatible with linked divisions; an explanation is shown when they do not. Deleting a subject offers an unchecked confirmation to remove its linked teaching assignments atomically. Saved timetable snapshots remain intact. Academic category navigation now survives reload.

All work uses the uploaded ZIP. Its CSV is unchanged, as are dependencies, faculty/subject mappings, laboratory durations, room capacities, calendars, and classroom continuity constraints.

## Why the full input cannot fit as supplied

| Scope | Two-hour laboratory sessions | Required lab-room hours |
|---|---:|---:|
| Semester 3, A/B/C | 45 | 90 |
| Semester 5, A/B/C | 54 | 108 |
| Semester 7, A/B | 24 | 48 |
| Total | 123 | 246 |

The six laboratory rooms are 701, 702, 703, 807, 901, and 902. Each provides eight teaching hours per day, five days per week, so the absolute upper bound is **240 lab-room hours**. At least **six hours of laboratory capacity are missing**, even before considering teacher clashes, batch availability, or continuity. Starting at 10:00 reduces the upper bound further, to 210.

Faculty **Pallavi M. N.** has 32 assigned periods and a weekly limit of 32, but the daily cap is six across five days: at most **30**. That separate shortage is two periods.

No search algorithm can meet both bounds without changing an input. Review the source assignment counts first. If those are correct, additional approved laboratory capacity/calendar availability and a correction to faculty workload are necessary. Removing these two lower-bound conflicts alone does not prove that all other constraints will fit. No such changes were made automatically, and every laboratory retains its two-hour duration.

## Checks

Backend regressions cover strict room eligibility even with legacy flags; rejection of lab/classroom swaps; refusal to save a candidate that fails final audit; invalid hint rejection; subject edits/deletion, stale-revision protection and snapshot preservation; and readable PDF/Excel exports.

Actual data generation was validated for:

| Separate validation scope | Sessions | Audited conflicts | Early classroom changes |
|---|---:|---:|---:|
| Semester 3 A | 38 | 0 | 0 |
| Semester 3 A/B/C | 114 | 0 | 0 |
| Semester 5 A/B/C | 111 | 0 | 0 |
| Semester 7 A/B | 64 | 0 | 0 |

These runs enforce a minimum of three consecutive lecture periods before changing classrooms. Each is a **separate scope**, not a coordinated college-wide timetable; their results must not be combined without checking shared resources.

Chromium checks cover real UI generation, manual room options, academic tabs and reload, subject edits, an incompatible semester edit with a clear error, assignment-count editing, guarded subject deletion, persistence, snapshot preservation, mobile rendering and JavaScript errors.

To repeat: install `requirements-dev.txt`, run `python -m pytest -q`, then `python tests/browser_smoke.py` with Chromium installed. Tests use disposable databases and do not change your academic data.

## Using the corrected application

Extract into a new folder and run `start_windows.bat` (64-bit Python 3.11 or 3.12), or follow the Linux/macOS commands in `README.md`. Keep your prior project/data as a backup. A fresh database loads the supplied CSV automatically. To retain existing academic changes, stop both servers and copy your existing `data` folder into the new application before starting it.

Use a hard browser refresh after upgrading. Historical timetable snapshots remain historical; generate a new version to apply corrected room allocation. Old versions that placed labs in classrooms will fail the stricter audit if submitted for approval or editing.
