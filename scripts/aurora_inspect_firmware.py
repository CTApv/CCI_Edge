"""Compare DSP+MCU identities against a local Central CVI table, offline only."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.aurora_firmware_analysis import classify_firmware


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", type=Path, required=True)
    parser.add_argument("--dsp-id", required=True)
    parser.add_argument("--dsp-revision", required=True, help="Two hex digits")
    parser.add_argument("--mcu-id", required=True)
    parser.add_argument("--mcu-revision", required=True, help="Two hex digits")
    args = parser.parse_args()
    try:
        result = classify_firmware(args.table.read_text(encoding="utf-8-sig"),
                                   dsp_id=args.dsp_id, dsp_revision=args.dsp_revision,
                                   mcu_id=args.mcu_id, mcu_revision=args.mcu_revision)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Invalid firmware evidence: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
