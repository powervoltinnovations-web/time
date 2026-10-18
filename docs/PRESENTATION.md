# UniSched presentation walkthrough

1. Start with `start_windows.bat`, then open http://127.0.0.1:8000.
2. For an existing database, export **Import data → Back up current data**, then **Preview IT reference data → Replace academic data**. A new database already contains this dataset.
3. Select **IT · Information Technology** in the header. In Academic setup, show 24 subjects, 33 teachers, nine divisions, 27 batches, and seven classrooms plus six laboratories. Divisions use Auto classroom allocation; classrooms have 70 seats and labs 20 seats. Each division has 60 students.
4. Open Generate by division. Leave All years / semesters selected, choose Generate all selected divisions, and use a 60-second limit. It must place 315 sessions / 396 faculty contact hours without collisions or student gaps. Runtime depends on the computer; use 120 seconds if the search reaches its limit.
5. Show a division timetable: 09:00 start, 13:00–13:45 recess, 32 teaching hours per student/week, mostly 15:45–16:45 finishes. Each subject’s three/four weekly lectures must appear on different days. Select a practical batch to see its 32-hour schedule; the all-batches view includes parallel sessions and therefore totals 44 contact hours per division. A shorter day is legitimate. Show the solved-constraints report below the grid.
6. Open Analytics & conflicts: inspect actual student gaps, teacher caps, and room occupancy. The complete reference plan uses 76.2% of the available room-period capacity. Partial plans naturally have lower utilization.
7. Switch to By professor. Only that faculty member's lectures/labs appear. Export PDF and Excel; both include the college name.
8. Demonstrate separate generation by selecting Semester 3 and generating A, then B. If you already have a full plan, other divisions remain locked; to demonstrate starting from A only, uncheck Preserve other divisions for the first run. B's generation then preserves A automatically. The banner shows exactly which divisions remain unscheduled.
9. Add a department, then a subject with Second/Third/Final Year selection. Add a division and teaching assignments before generating that new department. A new subject alone does not create teaching assignments.
10. Demonstrate a real failure on a copy of the reference data: set one assigned teacher's weekly limit to 1 hour, then generate. UniSched explains the excess assigned hours and proposes reassigning/reducing requirements or changing the limit. Restore the limit to 20 and regenerate. No restriction is silently ignored.

## Manual edits and workflow

Open Edit entire plan. Exchange days/starting periods in two lecture rows, then Validate & save new Draft. If other divisions clash, the form explains the conflicts and leaves the old version intact. Whole-day exchanges across the complete plan are a useful demonstration when all faculty have the same daily availability. Show the earlier version in history, approve the new one, then lock it. The editing button becomes unavailable. Unlock it and Mark Draft to edit again.

## Lab-batch example

A 60-student division can contain A1/A2/A3 with 20 students each. Assign lectures to the whole division. Create separate lab/project assignments for each batch, selecting teachers and suitable laboratories. If one batch works while another cannot start any teaching, the no-gap rule can make the plan impossible. Add sufficient simultaneous lab/teacher capacity or revise assignments; creating batch names alone does not create their teaching sessions.

## Backup and migration

Stop the server before copying a complete `data` folder. To update, keep the old installation as a backup, extract the new ZIP to a new folder, copy `data`, then run the new Windows launcher. Do not transfer `.venv`. For editable academic data only, use JSON/Excel export and import. Historical timetables remain in SQLite and are not included in academic-data exports.
