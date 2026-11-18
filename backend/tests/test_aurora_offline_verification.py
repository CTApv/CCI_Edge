"""Wire-level regression of the approved 151 and offline readback decoding.

No physical serial ports or network connections are opened by these tests.
Golden frames describe the existing PV Guardian behavior, not vendor rounding.
"""
import binascii
import unittest
from struct import pack
from types import SimpleNamespace
from unittest.mock import patch

from app.services.aurora_service import AuroraProtocolError, AuroraService
from app.services.aurora_capture_analysis import (
    decode_control_capture, decode_control_snapshot, decode_control_exchanges,
)


def independent_crc_frame(payload):
    """CRC via the stdlib forward CCITT algorithm and reflected input/output."""
    reflected = bytes(int(f"{byte:08b}"[::-1], 2) for byte in payload)
    crc = binascii.crc_hqx(reflected, 0xffff)
    crc = int(f"{crc:016b}"[::-1], 2) ^ 0xffff
    return payload + crc.to_bytes(2, "little")


class EmulatedSerial:
    def __init__(self, expected, reply, chunk_size=1):
        self.expected = expected
        self.reply = reply
        self.chunk_size = chunk_size
        self.pending = b""
        self.writes = []
        self.closed = False

    @property
    def in_waiting(self):
        return min(self.chunk_size, len(self.pending))

    def reset_input_buffer(self):
        self.pending = b""

    def reset_output_buffer(self):
        pass

    def write(self, frame):
        if frame != self.expected:
            raise AssertionError(f"Approved 151 frame changed: {frame.hex(' ')}")
        self.writes.append(frame)
        self.pending = self.reply
        return len(frame)

    def flush(self):
        pass

    def read(self, size):
        result = self.pending[:size]
        self.pending = self.pending[size:]
        return result

    def close(self):
        self.closed = True


class Approved151WireTests(unittest.TestCase):
    GOLDEN = {
        0: "02 97 01 01 00 00 00 03 24 41",
        1: "02 97 01 01 01 48 00 03 2b 9d",
        25: "02 97 01 01 20 00 00 03 77 ce",
        50: "02 97 01 01 40 00 00 03 93 57",
        75: "02 97 01 01 5f ff 00 03 38 e0",
        99: "02 97 01 01 7e b7 00 03 64 b3",
        100: "02 97 01 01 7f ff 00 03 6b 6f",
    }
    ACK = bytes.fromhex("00 06 00 00 00 00 17 cc")

    def exchange(self, percent, reply, retries=0):
        service = AuroraService()
        port = EmulatedSerial(bytes.fromhex(self.GOLDEN[percent]), reply)
        device = SimpleNamespace(protocol="aurora", connection_settings={
            "port": "OFFLINE-EMULATOR", "address": 2, "retries": retries,
            "timeout_seconds": 0.05, "inter_request_delay_ms": 0, "retry_delay_ms": 0,
        })
        with patch.object(service, "_open_serial_port", return_value=port):
            result = service.write_point(device, SimpleNamespace(key="active_power_limit"), percent)
        self.assertTrue(port.closed)
        return result, port

    def test_approved_frames_are_preserved_through_public_write_path(self):
        for percent, golden in self.GOLDEN.items():
            with self.subTest(percent=percent):
                result, port = self.exchange(percent, self.ACK)
                self.assertEqual(port.writes, [bytes.fromhex(golden)])
                self.assertEqual(result["aurora_op"], 151)
                self.assertEqual(result["applied_value"], percent)

    def test_fragmented_reply_with_leading_noise_is_recognized(self):
        result, _ = self.exchange(50, b"\xaa\x55" + self.ACK)
        self.assertEqual(result["aurora_reply_frame"].lower(), self.ACK.hex(" "))

    def test_rejected_command_is_not_reported_as_success(self):
        with self.assertRaises(AuroraProtocolError) as ctx:
            self.exchange(50, bytes.fromhex("33 00 00 00 00 00 22 3c"))
        self.assertEqual(ctx.exception.diagnostics["aurora_reply_tx_state"], 51)

    def test_corrupted_reply_is_rejected(self):
        with self.assertRaises(AuroraProtocolError):
            self.exchange(50, self.ACK[:-1] + b"\x00")

    def test_silence_is_a_timeout(self):
        with self.assertRaises(AuroraProtocolError) as ctx:
            self.exchange(50, b"")
        self.assertIn("timeout", str(ctx.exception).lower())

    def test_out_of_range_never_opens_serial_port(self):
        service = AuroraService()
        with patch.object(service, "_open_serial_port") as open_port:
            for value in (-1, 101):
                with self.assertRaises(ValueError):
                    service.write_point(SimpleNamespace(), SimpleNamespace(key="active_power_limit"), value)
            open_port.assert_not_called()


class OfflineControlCaptureTests(unittest.TestCase):
    def snapshot(self, enabled=True, limit=16384, timeout=60, smooth=12.0):
        return {
            132: independent_crc_frame(bytes((0, 6)) + timeout.to_bytes(2, "big") + b"\0\0"),
            133: independent_crc_frame(bytes((0, 6, int(enabled), 0, 0, 0))),
            134: independent_crc_frame(bytes((0, 6)) + limit.to_bytes(2, "big") + b"\0\0"),
            135: independent_crc_frame(bytes((0, 6)) + pack(">f", smooth)),
        }

    def test_decodes_manufacturer_readback_formats(self):
        result = decode_control_snapshot(self.snapshot())
        self.assertEqual(result["displayed_limit_percent"], 50.0)
        self.assertEqual(result["settings"]["timeout"]["displayed_minutes"], 1)
        self.assertEqual(result["settings"]["smooth"]["displayed_smooth"], 12)
        self.assertFalse(result["physical_execution_confirmed"])
        self.assertFalse(result["capture_freshness_confirmed"])

    def test_disabled_limit_keeps_stored_setting_separate(self):
        result = decode_control_snapshot(self.snapshot(enabled=False, limit=8192))
        self.assertEqual(result["displayed_limit_percent"], 100)
        self.assertEqual(result["settings"]["limit"]["stored_limit_percent"], 25)

    def test_forever_label_and_smooth_quantization_match_software(self):
        result = decode_control_snapshot(self.snapshot(timeout=15300, smooth=15.9))
        self.assertTrue(result["settings"]["timeout"]["displayed_forever"])
        self.assertEqual(result["settings"]["smooth"]["displayed_smooth"], 12)

    def test_invalid_selector_crc_length_or_missing_setting_is_rejected(self):
        with self.assertRaises(ValueError):
            decode_control_capture(151, Approved151WireTests.ACK)
        with self.assertRaises(ValueError):
            decode_control_capture(132, b"\x00" * 8)
        with self.assertRaises(ValueError):
            decode_control_capture(132, b"\x00" * 7)
        with self.assertRaises(ValueError):
            decode_control_snapshot({132: Approved151WireTests.ACK})

    def test_nack_and_nonfinite_smooth_are_not_valid_settings(self):
        with self.assertRaises(ValueError):
            decode_control_capture(132, bytes.fromhex("33 00 00 00 00 00 22 3c"))
        for value in (float("nan"), float("inf"), -1.0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                decode_control_snapshot(self.snapshot(smooth=value))

    def test_invalid_raw_limit_is_preserved_and_flagged(self):
        result = decode_control_snapshot(self.snapshot(limit=65535))
        self.assertFalse(result["settings"]["limit"]["within_nominal_range"])
        self.assertEqual(result["settings"]["limit"]["raw_limit"], 65535)

    def exchanges(self):
        return [{"request": independent_crc_frame(bytes((2, 83, selector, 0, 0, 0, 0, 0))).hex(),
                 "reply": reply.hex()}
                for selector, reply in self.snapshot().items()]

    def test_correlated_capture_checks_read_request_frames(self):
        result = decode_control_exchanges(self.exchanges())
        self.assertEqual(result["address"], 2)
        self.assertTrue(result["request_frames_validated"])
        self.assertEqual(result["displayed_limit_percent"], 50)

    def test_write_or_mixed_device_or_duplicate_captures_are_rejected(self):
        write = self.exchanges()
        write[0]["request"] = Approved151WireTests.GOLDEN[50]
        mixed = self.exchanges()
        mixed[0]["request"] = independent_crc_frame(bytes((3, 83, 132, 0, 0, 0, 0, 0))).hex()
        duplicate = self.exchanges() + [self.exchanges()[0]]
        bad_crc = self.exchanges()
        bad_crc[0]["request"] = bad_crc[0]["request"][:-4] + "0000"
        for exchanges in (write, mixed, duplicate, bad_crc, []):
            with self.subTest(exchanges=exchanges), self.assertRaises(ValueError):
                decode_control_exchanges(exchanges)


if __name__ == "__main__":
    unittest.main()
