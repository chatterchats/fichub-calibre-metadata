"""Minimal typed Source class used by tests and type checking."""

from typing import Any


class Source:
    def __init__(self) -> None:
        # The plugin calls self.browser.open_novisit(...); tests inject a fake object.
        self.browser: Any = None

    def clean_downloaded_metadata(self, mi: Any) -> None:
        del mi
