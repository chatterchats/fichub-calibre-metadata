# tests/stubs/calibre/utils/localization.py
def canonicalize_lang(lang):
    if not lang:
        return None
    return lang.lower()
