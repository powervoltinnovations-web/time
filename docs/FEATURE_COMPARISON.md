# Screenshot comparison

The existing UniSched purple website and SQLite data are retained. The supplied blue-interface screenshots were used as a feature reference.

| Reference feature | Updated UniSched location and behavior |
| --- | --- |
| Department selector and new departments | Header selector and Departments CRUD; department appears on timetables and exports. |
| Generate scope: department, semester, all/A/B/C | Generate by division; buttons are built from actual divisions; preserves compatible prior divisions by default. |
| Mini projects | Subject course type and project session count in assignments; configurable consecutive duration. |
| Divisions, student strength, practical groups | Academic setup → Divisions / Lab batches; batch headcounts and student overlap enforced; Create three batches helper and a 27-batch demo with assigned practical teachers and labs. |
| Subject name/code, weekly hours, type, semester | Subjects & courses; explicit First/Second/Third/Final Year selection plus semester. |
| Elective sets | Academic setup → Elective sets; subjects link to a set in the same department/semester. The user's separate-slot requirement takes precedence over the screenshot's parallel alternatives. |
| Faculty name, email, daily/weekly limits, lab eligibility | Teachers and Faculty workload; every restriction is enforced in generation. |
| Faculty workload matrix | Faculty workload shows assigned hours; Analytics shows the actual daily distribution. |
| Classrooms/labs, seats, department, year eligibility | Rooms & Labs; fixed allocation or Auto shared pools. |
| Conflict inspector | Check requirements, generation failure reports, and independent Analytics audit. |
| Excel import | Import data accepts the supplied Excel template, CSV, and full JSON backups; preview before replacement. |
| Manual editing / Draft / Approved / Lock | Timetables controls; multi-session placement changes are audited and saved as new drafts. Approval and lock are enforced by the backend and shown in exports. |
| Lecture distribution | Three/four weekly lectures use different days; fresh solver seeds vary valid placement. |
| Version history | Immutable snapshots with the original academic data and calendar. |
| Timetable health/student quality/room usage | Analytics & conflicts; transparent measured formulas, daily breakdown, faculty loads, room usage. |
| College operating hours, period length, working days | College timings with period preview and validation. |
| Lunch/additional breaks, blocked periods | College timings; excluded from teaching, gap calculations, and session windows. |
| Lecture/lab/project session durations | College timings; shared by generation, display, analytics, and exports. |
| Performance panel | Real Python process uptime/memory, API latency, generation timing/success, and recent runs. Refresh button updates measurements. |
| AI Assistant label in screenshot header | No external AI integration. Existing solver reports and rule-based suggestions explain actual conflicts; no simulated chatbot or fabricated metrics. |
| Professor-specific blank grid | Timetables → By professor; all unassigned teaching cells stay blank. |
| PDF/Excel with college name | Current division/professor and complete-plan exports; snapshot calendar retained. |

The updated templates are illustrative IT data for presentation, not an official college curriculum. Separate practical batches can run in parallel; elective options still require separate slots.
