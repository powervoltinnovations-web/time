"""Load the supplied college CSV, without generating or inventing academic data."""
from pathlib import Path
from .domain import parse_csv
OFFICIAL_CSV=Path(__file__).resolve().parents[1]/'sample_data'/'it_timetable_import_group_consistent.csv'
def presentation_config():
    return parse_csv(OFFICIAL_CSV.read_bytes())
