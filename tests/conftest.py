import sys
from pathlib import Path

# Use absolute paths so test discovery works from any working directory.
TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
STUBS_DIR = TESTS_DIR / 'stubs'

# Keep stubs first so fake calibre/polyglot packages win over site-packages.
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(STUBS_DIR))
