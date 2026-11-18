"""Offline interpretation of Aurora captures, reconstructed from Manager TL.

This module has no serial/network access and is not called by the live driver.
It decodes observed settings; it cannot certify physical power or capture age.
"""
from __future__ import annotations

import math
from struct import unpack

CONTROL_READ_SELECTORS = {132: "timeout", 133: "enabled", 134: "limit", 135: "smooth"}
REFERENCE_SOFTWARE_SHA256 = "f6383335512b710d27c94ff17806b74e4ff130bba0d4b10f8e1a08187f4c67ed"


def _capture_crc(data: bytes) -> int:
    crc = 0xffff
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x8408 if crc & 1 else 0)
    return crc ^ 0xffff


def validate_reply(frame: bytes) -> bytes:
    if len(frame) != 8:
        raise ValueError("A capture must contain exactly one eight-byte Aurora reply.")
    if int.from_bytes(frame[6:], "little") != _capture_crc(frame[:6]):
        raise ValueError("Aurora capture CRC mismatch.")
    if frame[0] != 0:
        raise ValueError(f"Aurora device rejected the request: TxState={frame[0]}.")
    return frame


def decode_control_capture(selector: int, frame: bytes) -> dict[str, object]:
    """Caller must associate this reply to an observed opcode-83 request.

    Replies do not echo address/opcode/selector. A CRC-valid reply alone cannot
    establish which device, parameter or request it belongs to.
    """
    if selector not in CONTROL_READ_SELECTORS:
        raise ValueError("Unsupported Aurora control read selector.")
    frame = validate_reply(frame)
    result: dict[str, object] = {
        "selector": selector, "property": CONTROL_READ_SELECTORS[selector],
        "global_state": frame[1], "reply_hex": frame.hex(" "),
        "evidence": "manufacturer_software_static_analysis",
        "field_tested": False,
    }
    raw = int.from_bytes(frame[2:4], "big")
    if selector == 132:
        # Manager TL divides the 16-bit value by 60 before displaying minutes.
        # This does not establish firmware expiration/fallback behavior.
        minutes = raw // 60
        result.update(raw_timeout=raw, displayed_minutes=minutes,
                      displayed_forever=minutes == 255)
    elif selector == 133:
        result.update(raw_enabled=frame[2], enabled=frame[2] != 0)
    elif selector == 134:
        result.update(raw_limit=raw, stored_limit_percent=raw * 100.0 / 32768.0,
                      within_nominal_range=raw <= 32768)
    else:
        smooth = unpack(">f", frame[2:6])[0]
        if not math.isfinite(smooth) or smooth < 0:
            raise ValueError("Invalid Aurora smooth value in capture.")
        integer = int(smooth)
        result.update(raw_smooth=smooth, displayed_smooth=integer - integer % 4)
    return result


def decode_control_snapshot(replies: dict[int, bytes]) -> dict[str, object]:
    """Interpret an explicitly correlated set of four replies, offline only."""
    if set(replies) != set(CONTROL_READ_SELECTORS):
        raise ValueError("A snapshot requires exactly selectors 132, 133, 134 and 135.")
    settings = {CONTROL_READ_SELECTORS[key]: decode_control_capture(key, frame)
                for key, frame in replies.items()}
    enabled = settings["enabled"]["enabled"]
    stored = settings["limit"]["stored_limit_percent"]
    return {
        "settings": settings,
        # Manager TL displays 100% when PL-ON is zero, regardless of stored limit.
        "displayed_limit_percent": stored if enabled else 100.0,
        "capture_freshness_confirmed": False,
        "physical_execution_confirmed": False,
        "field_tested": False,
    }


def decode_control_exchanges(exchanges: list[dict[str, str]]) -> dict[str, object]:
    """Validate request/reply pairs supplied by a serial capture, never transmit.

    Pairing must come from the capture tool: replies have no address or selector.
    This checks frame integrity and one-address scope, not capture authenticity.
    """
    replies: dict[int, bytes] = {}
    addresses: set[int] = set()
    for exchange in exchanges:
        request = bytes.fromhex(exchange["request"])
        if len(request) != 10 or int.from_bytes(request[8:], "little") != _capture_crc(request[:8]):
            raise ValueError("Invalid Aurora request length or CRC in capture.")
        if request[1] != 83 or request[2] not in CONTROL_READ_SELECTORS or any(request[3:8]):
            raise ValueError("Capture must contain only the four supported opcode-83 read requests.")
        selector = request[2]
        if selector in replies:
            raise ValueError("Duplicate control read selector: select one coherent snapshot.")
        addresses.add(request[0])
        replies[selector] = bytes.fromhex(exchange["reply"])
    if len(addresses) != 1:
        raise ValueError("A control snapshot must refer to one device address.")
    return {
        **decode_control_snapshot(replies),
        "address": addresses.pop(),
        "request_frames_validated": True,
        "request_reply_pairing": "supplied_by_capture_not_echoed_by_protocol",
    }
