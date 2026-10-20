# UniSched

University timetable planning for **Datta Meghe College of Engineering, Airoli, Navi Mumbai**. Website, FastAPI, SQLite, and OR-Tools CP-SAT. No frontend build is required.

## Run on Windows

Extract into a **new folder** and double-click `start_windows.bat`. Install 64-bit Python 3.11 or 3.12 first. Keep the terminal open, then visit `http://127.0.0.1:8000`. Press Ctrl+F5 after upgrading.

Manual commands from the folder containing `run.py`:

```bat
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.lock
.venv\Scripts\python.exe run.py
```

On Linux/macOS, use `python3.12 -m venv .venv`, then `.venv/bin/python -m pip install -r requirements.lock` and `.venv/bin/python run.py`. Python 3.11 also works.

## This update

- **Strict rooms:** lectures/tutorials use classrooms; every lab uses a laboratory. Classroom-practical exceptions are removed, including for old API requests and manual editing. A final independent audit runs before saving.
- **Academic editing:** subject deletion offers explicit removal of linked assignments. Subject editing links directly to those assignments and explains incompatible semester/department changes. Academic tabs survive page reloads.

- **Generate by division → Generate:** choose a 9:00 or 10:00 a.m. start. The saved timetable and exports use that choice. It does not rewrite the imported source calendar.
- **Classroom continuity:** default minimum two consecutive lecture periods before changing rooms; three is optional. Enforced separately in each uninterrupted morning/afternoon lecture block. Recess, tutorials, labs, projects, and free periods end a block. A short block may end without inventing extra lectures. If reservations make the rule impossible, generation reports it instead of relaxing it.
- **Tutorials:** dedicated sidebar section with subject, division, batch, teacher, sessions, duration, and classroom. The nine supplied tutorial assignments use **room 710**.
- **Practicals remain two hours**, Monday–Friday. Existing lecture counts are preserved exactly; new lecture assignments default to three per week.
- Manual editing, Draft/Approved/Lock, deletion of generated versions, AI chat, separate batch cards, professor/classroom/lab views, and PDF/Excel export remain available.

## Supplied official data

The only application seed file is [`sample_data/it_timetable_import_group_consistent.csv`](sample_data/it_timetable_import_group_consistent.csv). Its bytes are unchanged from the uploaded file. A fresh database imports it automatically. Previous illustrative seed files are removed.

It contains 191 assignments, 34 subjects, 24 named faculty, eight divisions, 24 batches, seven classrooms and six laboratories. Semesters 3 and 5 have A/B/C; semester 7 has A/B. Teacher–subject mappings, names, session counts and room capacities are retained. The source's `MECH` faculty department code is represented as a department named `MECH`; no faculty is invented. Subjects appearing as both theory and practical are represented as mixed courses. Tutorial rows are recognized as tutorials, retaining their batch and room 710.

### Lab-only scheduling and source-data limits

All laboratory assignments require laboratories and reserve their own batch, teacher and room time. Two-hour laboratories and the existing two/three-period lecture continuity rule remain intact. The CSV is the sole academic input; no subjects, faculty, rooms, counts or availability limits were invented or changed.

The full eight-division input has **123 two-hour lab sessions = 246 lab-room hours**, but **6 labs × 5 days × 8 hours = 240 hours** at 9:00 (210 at 10:00). Pallavi M. N. has 32 assigned periods with a six-period daily cap, permitting only 30 across five days. These mathematical shortages cannot be resolved by a longer search. The application reports both without moving labs to classrooms, shortening sessions or changing faculty limits.

A complete college timetable therefore needs source-data corrections or explicitly approved changes to capacity/calendar and faculty workload. Six more lab-room hours and a correction to the two-period faculty shortage are necessary lower bounds, not a guarantee of a complete solution. See `FIX_REPORT.md`.

Each semester's divisions were successfully generated together in separate validation runs, with no audited conflicts and three-period lecture continuity. These separate results must not be combined into a college plan without coordinating shared resources. Previous hints and saved placements are only reused after validation against current room rules.

Major Project remains reserved student time without a teacher or room booking. Its supplied two sessions of four hours remain intact.

A start-time choice only selects the calendar for the new timetable. Teacher availability remains enforced; if it prevents that start, the result explains the conflict. Source CSV downloads are exact; current-data CSV/Excel/JSON exports include normalized tutorial fields. JSON and Excel preserve all identifiers and independent project records.

## Existing databases

For the requested replacement data, use a freshly extracted folder **without copying the old `data` folder**. Keep your original project as a backup. Existing databases are never silently overwritten on startup. If you choose to retain an old database, use **Import data → Preview supplied college data → Replace academic data** after downloading a backup. Historical timetable snapshots remain unchanged and can be deleted separately.

## AI chat

The floating purple **AI chat** button is on the starting page and the sidebar. Local checks work without a key. Select a timetable/session to ask about eligible replacement classrooms and conflicts. Optional OpenAI explanations require `UNISCHED_OPENAI_API_KEY` in the server environment; never put keys in website code. Local checks remain authoritative and suggested changes are not automatically applied.

## Development checks

This ZIP includes tests using the supplied CSV and disposable databases. Install `requirements-dev.txt`, run `python -m pytest -q`, then `python tests/browser_smoke.py` with Chromium installed (`python -m playwright install chromium` if needed). Linux automatically uses system `chromium`; `CHROMIUM_PATH` can select another installed executable. Browser artifacts go in ignored `artifacts/`.
