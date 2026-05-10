from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))


def main() -> int:
    importlib.import_module("app.models")
    database = importlib.import_module("app.database")
    database_path = database.DATABASE_PATH
    if database_path.exists():
        database_path.unlink()
    database.init_db()
    print(f"Reset local database at {database_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
