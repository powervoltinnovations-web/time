# Changes to the supplied ZIP

Based on the exact source in `time.zip` (commit `130dd57af812b7f5e49eb2dc707ff2a433e3c9ac`).

| Requested change | Where to use it |
| --- | --- |
| Prefer 2 or 3 lectures in one classroom | Generate timetable → Classroom continuity preference |
| Separate optional Mini Projects page | Left sidebar → Mini projects |
| Visible chat icon from the starting page | Bottom-right → AI Chat |
| Repair overlapping batch/session text | Timetables → All batches |

The original `app/demo.py` and every file under `sample_data/` are byte-for-byte unchanged. The dataset still has 24 subjects, 33 teachers, 9 divisions, 27 batches, 7 classrooms, and 6 laboratories. No mini-project entries are seeded. The original lab assignments, lecture distribution, college timings, recess, and no-gap constraints are preserved.

Classroom correction: the generation dialog now defaults to a minimum of three consecutive lecture periods in one room before allowing a room change within a lecture block. A room-only pass is tried first. If it cannot meet this minimum, the solver jointly arranges times and rooms for the selected divisions. A conflicting or unverified result is not returned as a successful timetable. The 2-period option remains a preference, and flexible allocation remains available.

Labs, projects, recess, and the end of the day may end a lecture block before three periods; the rule does not create extra lectures to fill a block. Preserved divisions and saved timetable versions keep their original rooms. Generate a fresh timetable (or include all affected divisions) to apply the rule to them. Capacity, collisions, faculty availability, and no-gap rules remain enforced.

Verification of the classroom correction: the original nine-division dataset generated with zero consecutive-lecture room changes, zero audited hard conflicts, and zero internal gaps. No academic records or unrelated project features were changed.

Projects are created only through an explicit save. You choose their hours, supervisor, and an existing eligible room; the program does not enlarge rooms or create faculty automatically. Existing project assignments retain their original lab and duration behavior unless you edit them. Backups can retain the new project hours and room fields; earlier CSV files still import.

The assistant is read-only. Local checks inspect saved plans and audit proposed replacement rooms against capacity, eligibility, and bookings. Historical timetables are evaluated separately. Optional OpenAI mode explains those facts; setup and data-sharing details are in README.md.

See START_HERE.txt for Windows startup and carrying your existing data folder into this update.


## Latest limited update: timeout and deletion

- Avoid repeating a full search when a saved timetable still satisfies the current configuration. Revalidate it and save a new Draft; keep the old version intact.
- Reduce interchangeable classroom choices in the time solver to a capacity pool, then assign real rooms to complete lecture blocks. Use this only when all lecture-room eligibility sets match and the pool has no other uses or preserved bookings. Keep the general solver for other configurations.
- Add Delete timetable controls on the timetable screen and version history. Require a confirmation, respect lock/approval states, and check the workflow revision to prevent deletion after a concurrent status change. Failed reports can also be deleted. Remove only the chosen version and its workflow, without cascading to later independent snapshots.

The original nine-division dataset completed three fresh test runs in approximately 6–10 seconds with no audited clashes, gaps, or early classroom changes. Revalidation of those saved placements took approximately 0.04 seconds in the test environment. Timings depend on the machine and configuration; the search still reports genuine constraint failures and distinguishes them from a timeout.

Academic data, mini projects, chatbot behavior, manual editing, batch layout, and export formatting are unchanged by this update.
