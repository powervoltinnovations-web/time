# Reviewed teacher-assignment update

Only the requested assignments were changed. Existing faculty profiles, limits, availability, subjects, rooms, settings, durations and session counts are preserved. TE B3 Cyber Security remains KNS: the CS–VSK instruction was explicitly withdrawn.

## Changes

| Semester | Division / batch | Subject | Previous | Requested |
|---|---|---|---|---|
| 3 | B / whole division | Automata Theory | DPK | JSP |
| 3 | C / C2 | ADS Lab | HJ | PMN |
| 3 | C / C2 | Mini-Project - Full Stack Java Programming | PMN | GMA |
| 3 | C / C3 | Entrepreneurship Development | MECH | NYM |
| 3 | C / C3 | ADS Lab | HJ | PMN |
| 5 | A / A2 | DevOPs Lab | PMN | PMN (already correct) |
| 5 | B / B1 | Cyber Security Lab | KNS | DPK |
| 5 | B / B2 | Cyber Security Lab | KNS | ADM |
| 5 | B / B2 | DevOPs Lab | SUK | ARR |
| 5 | B / B2 | AI & ML Lab | RAJ | VGK |
| 5 | C / C1 | AI & ML Lab | VGK | JRG |
| 5 | C / C2 | India Knowledge System | PJ | HS |
| 5 | C / C2 | Multidisciplinary Minor Lab | BD | KNS |
| 5 | C / C3 | India Knowledge System | PJ | HS |
| 7 | A / A1 | Recent Open Source Project Lab | JSP | RZ |
| 7 | A / A2 | Recent Open Source Project Lab | JSP | RZ |

15 assignments changed; TE A2 DevOps was already PMN. Added **Mr. Honaji Salve (HS)** and **Prof. Reshma Zore (RZ)** with the approved initial defaults: IT, 09:00–17:45, 6 periods/day, 20 hours/week, laboratory eligible, email blank. Existing profiles are never overwritten by the updater.

## Preserve your existing local corrections

1. Stop the running application and keep a copy of your existing project.
2. Copy the files from this ZIP into your existing application folder. Keep its `data` and `.venv` folders; this ZIP does not contain replacements for them.
3. Double-click **update_reviewed_data.bat**. It previews each changed assignment in the terminal and saves a database backup before applying the reviewed list. The first pause asks you to ensure the server is stopped.
4. Run **start_windows.bat** and generate a new timetable. Saved timetable history is preserved.

This updater retains your local SAD–Krushna assignments, workload limits, rooms and other edits unless they are one of the specific assignments listed above. It refuses an ambiguous or missing target without saving a partial update. Repeating it is safe. On Linux/macOS run `.venv/bin/python update_reviewed_data.py`; add `--dry-run` to preview without saving.

## Fresh installation

Extract to a new folder and run `start_windows.bat`. New databases load `sample_data/reviewed_academic_data.json`. This full data file preserves all existing record IDs and teachers left without assignments. The updated CSV contains matching assignment rows; JSON is the complete representation, including unassigned faculty.

The fresh seed is based on the last supplied ZIP, not your unuploaded local database. Use the updater on your existing installation to preserve your later manual changes.

## Validation and limits

Checked the original and updated data field by field: only 15 offering `teacher_id` fields changed and two new teachers were appended. All existing teacher objects and other configuration fields are identical. Each untouched CSV row is byte-for-byte preserved.

Faculty caps were not increased. In the supplied baseline, the reviewed assignments now exceed some existing limits (GMA, NYM, PMN, ADM, ARR and JRG). The prior laboratory-capacity shortage also remains. These are reported by the scheduler; this data correction does not claim a feasible full-college plan.

The older `FIX_REPORT.md` describes the preceding code-fix build before this data update. Its workload figures and separate-semester success results are historical. Tests in this build check the corrected mappings, proper capacity failures, and preservation of local data.
