"""Tests run offline with the LLM disabled and a throwaway SQLite file."""
import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="kg-tests-")
os.environ["GEMINI_API_KEY"] = ""
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp) / 'test.db'}"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
