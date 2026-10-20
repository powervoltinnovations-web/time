"""Load reviewed academic data, with the supplied CSV as a fallback."""
from pathlib import Path
from .domain import Configuration, parse_csv
OFFICIAL_CSV=Path(__file__).resolve().parents[1]/'sample_data'/'it_timetable_import_group_consistent.csv'
def presentation_config():
    # JSON retains stable IDs and existing faculty left without assignments.
    reviewed = OFFICIAL_CSV.with_name('reviewed_academic_data.json')
    if reviewed.exists():
        return Configuration.model_validate_json(reviewed.read_bytes())
    return parse_csv(OFFICIAL_CSV.read_bytes())
