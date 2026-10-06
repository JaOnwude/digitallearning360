"""Write the API's OpenAPI document to a file for client generation.

Usage: python -m app.scripts.export_openapi <output-path>
"""

import json
import sys
from pathlib import Path

from app.main import app


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" keeps LF on Windows so CI's client-drift check is stable.
    body = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    out.write_text(body, encoding="utf-8", newline="\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
