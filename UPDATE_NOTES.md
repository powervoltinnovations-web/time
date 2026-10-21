> Current release: read [START_HERE.txt](START_HERE.txt) and [FINAL_CHANGES.md](FINAL_CHANGES.md). The included current official database is unchanged and the complete department timetable has passed validation. The material below is historical; do not import the older sample CSV or apply its old capacity warnings to this database.

# Room allocation and academic editing correction

Based only on the uploaded timetable-bef34540b6b7aa39e23352f209cbfe69092cce1f.zip.

- Removed the option that put laboratory subjects in classrooms and combined batches.
- Enforced correct room types in generation, audits, saved-placement reuse and manual room selection.
- Added an independent audit before saving generated timetables.
- Retained two-hour labs, two/three-period classroom continuity, teacher limits and all source CSV bytes.
- Added confirmed deletion of subjects with linked assignments, a shortcut to edit assignments, and clear explanations for incompatible semester/department edits.
- Fixed academic category navigation to retain the selected tab after refresh.
- Included backend and Chromium browser regressions in the ZIP.

The full-college input exceeds lab capacity and one teacher's daily workload capacity. The program reports these shortages rather than claiming a feasible full timetable. See FIX_REPORT.md.
