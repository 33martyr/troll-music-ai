"""Run the backend for local development.

    python scripts/dev_backend.py            # uses .env
    python scripts/dev_backend.py --mock     # mock text provider, separate database

``--mock`` is for working on the UI without an AI provider. Its output is
placeholder text and is labelled as mock everywhere it appears.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mock", action="store_true", help="use the mock text provider")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    if args.mock:
        os.environ["TROLL_LLM_PROVIDER"] = "mock"
        os.environ["TROLL_DATABASE_URL"] = "sqlite:///./data/dev-mock.db"
        os.environ["TROLL_STORAGE_DIR"] = "./data/dev-mock-storage"

    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
