"""Minimal typed stubs for calibre root helpers used by the plugin."""

from typing import Any


def as_unicode(obj: Any, enc: str = 'utf-8') -> str:
    return str(obj)


def prepare_string_for_xml(raw: str, attribute: bool = False) -> str:
    # very small subset of the real implementation
    raw = raw.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    if attribute:
        raw = raw.replace('"', '&quot;').replace("'", '&apos;')
    return raw
