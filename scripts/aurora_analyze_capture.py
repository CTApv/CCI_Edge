"""Analyze a correlated serial capture JSON without opening any connection.

Usage: python scripts/aurora_analyze_capture.py path/to/capture.json
Input: {"exchanges": [{"request": "02 53 ...", "reply": "00 ..."}, ...]}
The capture must pair each of the four opcode-83 reads with its own reply.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.aurora_capture_analysis import decode_control_exchanges


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    args = parser.parse_args()
    try:
        capture = json.loads(args.capture.read_text(encoding="utf-8"))
        result = decode_control_exchanges(capture["exchanges"])
    except (ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
        parser.exit(2, f"Invalid capture: {exc}\n")
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
