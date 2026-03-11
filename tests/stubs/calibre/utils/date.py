"""Minimal typed date helpers used by the plugin."""

from datetime import datetime
from typing import Any


def parse_date(
    date_string: Any,
    assume_utc: bool = False,
    as_utc: bool = True,
    default: datetime | None = None,
) -> datetime:
    del assume_utc, as_utc
    if isinstance(date_string, datetime):
        return date_string
    return default or datetime.utcnow()


def utcnow() -> datetime:
    return datetime.utcnow()
