# tests/stubs/calibre/ebooks/metadata/book/base.py
class Metadata:
    def __init__(self, title=None, authors=None):
        self.title = title
        self.authors = authors or []
        self.tags = []
        self.series = None
        self.series_index = None
        self.publisher = None
        self.pubdate = None
        self.comments = None
        self.language = None
        self.source_relevance = 0
        self._identifiers = {}

    def set_identifier(self, key, value):
        self._identifiers[key] = value

    # plugin uses mi.set('language', …) and mi.set('tags', …)
    def set(self, field, value):
        setattr(self, field, value)
