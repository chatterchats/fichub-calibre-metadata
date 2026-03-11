# tests/stubs/calibre/utils/date.py
from datetime import datetime


def parse_date(val):
    # Calibre’s version is more complex; for tests a no‑op is fine
    return val


def utcnow():
    return datetime.utcnow()
