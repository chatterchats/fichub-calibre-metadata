# tests/stubs/calibre/ebooks/metadata/sources/base.py
class Source:
    def __init__(self):
        # the plugin looks at self.browser; tests can assign a fake later
        self.browser = None
