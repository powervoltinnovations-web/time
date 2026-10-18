# Changes to the supplied ZIP

Based on the exact source in `time.zip` (commit `130dd57af812b7f5e49eb2dc707ff2a433e3c9ac`).

| Requested change | Where to use it |
| --- | --- |
| Prefer 2 or 3 lectures in one classroom | Generate timetable → Classroom continuity preference |
| Separate optional Mini Projects page | Left sidebar → Mini projects |
| Visible chat icon from the starting page | Bottom-right → AI Chat |
| Repair overlapping batch/session text | Timetables → All batches |

The original `app/demo.py` and every file under `sample_data/` are byte-for-byte unchanged. The dataset still has 24 subjects, 33 teachers, 9 divisions, 27 batches, 7 classrooms, and 6 laboratories. No mini-project entries are seeded. The original lab assignments, lecture distribution, college timings, recess, and no-gap constraints are preserved.

Room optimization first obtains a valid schedule, then reallocates lecture rooms with days, times, faculty, and non-lecture sessions fixed. It minimizes changes before the requested 2/3-period run and then total changes. Recess, laboratories, projects, and gaps reset a run. The result reports whether the room allocation was proven optimal for those fixed session times; constraints may prevent every preference from being met.

Projects are created only through an explicit save. You choose their hours, supervisor, and an existing eligible room; the program does not enlarge rooms or create faculty automatically. Existing project assignments retain their original lab and duration behavior unless you edit them. Backups can retain the new project hours and room fields; earlier CSV files still import.

The assistant is read-only. Local checks inspect saved plans and audit proposed replacement rooms against capacity, eligibility, and bookings. Historical timetables are evaluated separately. Optional OpenAI mode explains those facts; setup and data-sharing details are in README.md.

See START_HERE.txt for Windows startup and carrying your existing data folder into this update.
