# Final timetable update

This release uses the latest uploaded **New folder.rar**, including academic revision 40 and the original saved generation 7. The SQLite database and supplied CSV are unchanged, byte for byte. No faculty profile, assignment, subject, student strength, room capacity, calendar or required session count was edited.

## Scheduling

- Optimize batch occupancy together so A1/A2/A3 (and other divisions' batches) spend more time in parallel sessions. Faculty, room, student, duration and availability constraints remain mandatory.
- Keep laboratories exclusively for labs, classrooms for lectures, and every laboratory session two hours long.
- Combine final-year A+B IS into one 60-student class and STQA into another 60-student class. Both options run simultaneously, in separate classrooms, on three different days. These are generation settings; the official subject and offering records remain intact.
- Reserve each combined option's teacher and classroom once, retain both division records, and audit alternative student attendance separately.
- Preserve existing non-elective final-year times before optimizing batch occupancy; then preserve their rooms where possible. The search is bounded, so mathematical minimality is not claimed.
- Keep normal lecture classroom continuity. A parallel elective block ends the preceding whole-division lecture block.

## Free resources and manual editing

Every timetable slot has **Free faculty & rooms**. The display checks the whole selected interval across all entries in the saved plan, excludes occupied rooms and faculty outside working hours, and shows remaining faculty daily/weekly limits and room capacities. A free faculty member with no remaining hours can still be considered for moving an existing session, but cannot accept extra workload. All saves undergo the full audit. External duties and unscheduled divisions are not known to the application.

Moving a combined elective time moves both options and both division copies. A room change applies only to the chosen option's A+B copies. Conflicting edits are rejected. Teacher and room screens/exports show each physical combined class once.

## Verified result

- Eight divisions, 289 assignment-session records, zero audited violations.
- Partially occupied batch periods across second/third year: **57 → 17**.
- Missing batch-periods within active division slots: **84 → 21**.
- Final-year non-elective sessions: **43 of 52 retain their original time and room**; nine moved.
- Two-hour laboratory sessions, correct room types, all required counts, faculty caps, availability, no student gaps and classroom continuity pass validation.
- Three simultaneous IS/STQA sessions occur on separate days. Each option fits its 60 students in a 70-seat classroom.
- The bounded search found a valid improved plan; global optimality and fully packed batches in every slot are not claimed.

The verified placement hint is keyed to the complete data and policy fingerprint. It is independently audited before reuse. Changed academic data invalidate it and trigger normal constraint search. The original saved timetable is not rewritten: click Generate to create a new version. Compatible newer saved versions remain preferred when continuing the latest plan.

## Checks

Eleven regression/integration tests cover the full official dataset, combined student attendance and teacher booking, enrollment/capacity checks, incorrect lab rooms, manual edits, free resources over full intervals, PDF/Excel export, scoped generation and unchanged academic data. Browser checks passed for free-resource dialogs and combined elective display, with no JavaScript errors.

Use **START_HERE.txt**. The older FIX_REPORT and README sections describe historical versions and do not override this release's instructions. Do not import the sample CSV over your current official database.
