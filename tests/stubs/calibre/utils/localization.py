"""Minimal typed localization helper used by the plugin."""

from typing import Any


def canonicalize_lang(lang: Any) -> str | None:
    if not lang:
        return None
    return str(lang).lower()
