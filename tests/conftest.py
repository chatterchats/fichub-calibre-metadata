import sys
from pathlib import Path

# insert "tests/stubs" at front so our fake calibre/polyglot packages are found
sys.path.insert(0, str(Path(__file__).parent / 'stubs'))
