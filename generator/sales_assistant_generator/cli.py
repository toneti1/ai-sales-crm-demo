"""Command-line entry point for generating a personalization package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .generator import generate_personalized_package


def _read_input(path: str | None) -> dict:
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return json.loads(sys.stdin.read())


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate audit, email, and website concept for one lead.")
    parser.add_argument("lead_json", nargs="?", help="Path to a lead JSON file. Reads stdin when omitted.")
    parser.add_argument("--html-out", help="Optional path to save the generated HTML website concept.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    try:
        result = generate_personalized_package(_read_input(args.lead_json))
    except Exception as exc:  # pragma: no cover - CLI boundary
        print(f"Generation failed: {exc}", file=sys.stderr)
        return 1

    if args.html_out:
        Path(args.html_out).write_text(result["generatedWebsiteHtml"], encoding="utf-8")

    indent = 2 if args.pretty else None
    print(json.dumps(result, ensure_ascii=False, indent=indent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
