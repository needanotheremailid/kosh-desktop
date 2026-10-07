"""Read-only prerequisite probe. Does not import app code or open its data."""
import importlib.metadata
import json
import sys

EXPECTED = {"PyMuPDF": "1.28.2", "python-docx": "1.2.0", "lxml": "6.1.1", "typing_extensions": "4.15.0"}
problems = []
if sys.version_info[:2] != (3, 12):
    problems.append("Python 3.12 is required by this tested source release.")
versions = {}
for package, expected in EXPECTED.items():
    try:
        actual = importlib.metadata.version(package)
        versions[package] = actual
        if actual != expected:
            problems.append(f"{package} {expected} is required; found {actual}.")
    except importlib.metadata.PackageNotFoundError:
        problems.append(f"{package} {expected} is missing.")
if not problems:
    try:
        import pymupdf
        import docx
        import sqlite3
        with sqlite3.connect(":memory:") as database:
            if database.execute("SELECT 1").fetchone()[0] != 1:
                problems.append("SQLite in-memory check failed.")
    except Exception:
        problems.append("Installed document libraries could not load. Repair this Python environment.")
result = {"ok": not problems, "python": sys.executable, "python_version": sys.version.split()[0], "packages": versions, "errors": problems}
print(json.dumps(result))
sys.exit(0 if result["ok"] else 1)
