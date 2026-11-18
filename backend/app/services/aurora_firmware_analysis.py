"""Offline interpretation of the Central CVI AN101 compatibility evidence.

The result reports the manufacturer's SOFTWARE table only. It is not an allow
list for sending commands and is deliberately disconnected from the live driver.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re


@dataclass(frozen=True)
class FirmwareRule:
    dsp_id: str
    dsp_min: int
    dsp_max: int
    mcu_id: str
    mcu_min: int
    mcu_max: int
    description: str


def _revision(text: str) -> int:
    if not re.fullmatch(r"[0-9A-Fa-f]{2}", text):
        raise ValueError("Firmware revision must be exactly two hexadecimal characters.")
    return int(text, 16)


def parse_compatibility_table(text: str) -> list[FirmwareRule]:
    rules = []
    inside = False
    complete = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "[START]":
            if inside or complete:
                raise ValueError("Duplicate firmware table section.")
            inside = True
            continue
        if stripped == "[EOF]":
            complete = inside
            break
        if not inside or not stripped or stripped.startswith("//"):
            continue
        data, _, description = stripped.partition("//")
        fields = [value.strip() for value in data.split(";")]
        if fields[-1] == "":
            fields.pop()
        if len(fields) != 6 or not all(re.fullmatch(r"[A-Za-z0-9]{2}", fields[n]) for n in (0, 3)):
            raise ValueError("Malformed Central firmware rule.")
        low_dsp, high_dsp = _revision(fields[1]), _revision(fields[2])
        low_mcu, high_mcu = _revision(fields[4]), _revision(fields[5])
        if low_dsp > high_dsp or low_mcu > high_mcu:
            raise ValueError("Reversed Central firmware revision range.")
        rules.append(FirmwareRule(fields[0], low_dsp, high_dsp,
                                  fields[3], low_mcu, high_mcu, description.strip()))
    if not complete or not rules:
        raise ValueError("Incomplete or empty Central firmware table.")
    return rules


def classify_firmware(text: str, *, dsp_id: str, dsp_revision: str,
                      mcu_id: str, mcu_revision: str) -> dict[str, object]:
    if not all(re.fullmatch(r"[A-Za-z0-9]{2}", value) for value in (dsp_id, mcu_id)):
        raise ValueError("DSP and MCU IDs must each contain exactly two characters.")
    dsp, mcu = _revision(dsp_revision), _revision(mcu_revision)
    rules = parse_compatibility_table(text)
    matches = [rule.description for rule in rules
               if rule.dsp_id == dsp_id and rule.mcu_id == mcu_id
               and rule.dsp_min <= dsp <= rule.dsp_max
               and rule.mcu_min <= mcu <= rule.mcu_max]
    return {
        "dsp_id": dsp_id, "dsp_revision": dsp_revision,
        "mcu_id": mcu_id, "mcu_revision": mcu_revision,
        "an101_listed_by_vendor_software": bool(matches),
        "matching_descriptions": matches,
        "table_sha256_utf8": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "table_rule_count": len(rules),
        "command_compatibility_confirmed": False,
        "field_tested": False,
    }
