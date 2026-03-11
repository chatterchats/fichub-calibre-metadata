"""Minimal typed Metadata class used by tests and type checking."""

from datetime import datetime
from typing import Any


class Metadata:
    def __init__(self, title: str | None = None, authors: list[str] | None = None) -> None:
        self.title: str | None = title
        self.authors: list[str] = authors or []
        self.tags: list[str] = []
        self.series: str | None = None
        self.series_index: float | None = None
        self.publisher: str | None = None
        self.pubdate: datetime | None = None
        self.comments: str | None = None
        self.language: str | None = None
        self.source_relevance: int = 0
        self._identifiers: dict[str, str] = {}

    def set_identifier(self, key: str, value: str) -> None:
        self._identifiers[key] = value

    # plugin uses mi.set('language', …), mi.set('tags', …), and others
    def set(self, field: str, value: Any) -> None:
        setattr(self, field, value)
