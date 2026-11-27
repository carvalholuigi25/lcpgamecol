"""Write the API's OpenAPI document to a file, without starting the server.

The mobile client generates its TypeScript types from this file:

    python scripts/export_openapi.py                 # writes openapi.json
    python scripts/export_openapi.py -o other.json
    python scripts/export_openapi.py --check         # exit 1 if openapi.json is out of date
"""

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "openapi.json"


def render() -> str:
    sys.path.insert(0, str(ROOT))
    # Importing the app warns about missing secrets; that is irrelevant for the schema.
    logging.disable(logging.WARNING)
    from main import app

    return json.dumps(app.openapi(), indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check", action="store_true", help="fail instead of writing when the file differs"
    )
    args = parser.parse_args(argv)

    document = render()
    current = args.output.read_text(encoding="utf-8") if args.output.exists() else None
    if args.check:
        if current != document:
            print(f"{args.output} is out of date; run python scripts/export_openapi.py")
            return 1
        print(f"{args.output} is up to date.")
        return 0
    if current != document:
        args.output.write_text(document, encoding="utf-8", newline="\n")
        print(f"Wrote {args.output}")
    else:
        print(f"{args.output} is already up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
