# tests/stubs/calibre/__init__.py
def as_unicode(obj, enc='utf-8'):
    return str(obj)


def prepare_string_for_xml(raw, attribute=False):
    # very small subset of the real implementation
    raw = raw.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    if attribute:
        raw = raw.replace('"', '&quot;').replace("'", '&apos;')
    return raw
