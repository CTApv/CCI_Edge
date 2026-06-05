import unittest
from struct import pack
from types import SimpleNamespace
from unittest.mock import patch

from app.models.inverter_model import InverterPoint
from app.schemas.device_schemas import DeviceResponse
from app.services.aurora_service import (
    AuroraProtocolError,
    AuroraService,
    OP_GET_PART_NUMBER,
    OP_SET_PWR_LIMIT,
)


class _FakeSerialPort:
    def close(self) -> None:
        return None


class AuroraServiceTests(unittest.TestCase):
    def test_read_points_combines_state_and_dsp_values(self) -> None:
        service = AuroraService()
        device = DeviceResponse(
            device_id="aurora-1",
            name="Aurora 1",
            brand="PowerOne",
            model="Aurora Inverter",
            protocol="aurora",
            transport="serial",
            connection_settings={
                "port": "COM7",
                "address": 2,
                "baud_rate": 19200,
                "parity": "N",
                "stop_bits": 1,
                "byte_size": 8,
                "timeout_seconds": 0.5,
                "retries": 1,
            },
            profile_overrides={},
            status="online",
            created_at="2026-03-25T10:00:00+00:00",
        )
        points = [
            InverterPoint(
                key="status",
                label="Stato inverter",
                kind="telemetry",
                register_type="aurora",
                address=0,
                length=1,
                datatype="uint16",
                protocol_meta={"aurora_method": "state", "field": "InvState"},
            ),
            InverterPoint(
                key="active_power_kw",
                label="Potenza attiva",
                kind="telemetry",
                register_type="aurora",
                address=3,
                length=1,
                datatype="float32",
                protocol_meta={"aurora_method": "dsp", "tom": 3},
            ),
            InverterPoint(
                key="temperature_c",
                label="Temperatura inverter",
                kind="telemetry",
                register_type="aurora",
                address=21,
                length=1,
                datatype="float32",
                protocol_meta={"aurora_method": "dsp", "tom": 21},
            ),
        ]

        with (
            patch.object(service, "_open_serial_port", return_value=_FakeSerialPort()),
            patch.object(service, "_get_state", return_value={"InvState": 6}),
            patch.object(service, "_get_dsp", side_effect=[12.5, 44.0]),
        ):
            values = service.read_points(device, SimpleNamespace(), points)

        self.assertEqual(values["status"], 6)
        self.assertEqual(values["active_power_kw"], 12.5)
        self.assertEqual(values["temperature_c"], 44.0)

    def test_set_power_limit_scales_percent_to_aurora_payload(self) -> None:
        service = AuroraService()

        with patch.object(
            service,
            "_execute_request",
            return_value=(b"\x00" * 8, {"aurora_tx_frame": "02 97 01 01 40 00 00 03 00 00"}),
        ) as execute_mock:
            service._set_power_limit(
                serial_port=_FakeSerialPort(),
                address=2,
                percent=50,
                settings={"timeout_seconds": 0.5, "retries": 0},
            )

        request = execute_mock.call_args.kwargs["request"]
        self.assertEqual(request.op, OP_SET_PWR_LIMIT)
        self.assertEqual(request.params6, bytes([1, 1, 0x40, 0x00, 0, 3]))

    def test_write_point_returns_aurora_trace_diagnostics(self) -> None:
        service = AuroraService()
        device = DeviceResponse(
            device_id="aurora-1",
            name="Aurora 1",
            brand="PowerOne",
            model="Aurora Inverter",
            protocol="aurora",
            transport="serial",
            connection_settings={
                "port": "COM7",
                "address": 2,
                "baud_rate": 19200,
                "parity": "N",
                "stop_bits": 1,
                "byte_size": 8,
                "timeout_seconds": 0.5,
                "retries": 1,
            },
            profile_overrides={},
            status="online",
            created_at="2026-03-25T10:00:00+00:00",
        )
        point = InverterPoint(
            key="active_power_limit",
            label="Limite potenza attiva",
            kind="command",
            register_type="aurora",
            address=151,
            length=1,
            datatype="uint16",
            protocol_meta={},
            writable=True,
            unit="%",
        )

        with (
            patch.object(service, "_open_serial_port", return_value=_FakeSerialPort()),
            patch.object(
                service,
                "_set_power_limit",
                return_value={
                    "aurora_op": 151,
                    "aurora_operation": "set_power_limit",
                    "aurora_tx_frame": "02 97 01 01 40 00 00 03 AA BB",
                    "aurora_reply_frame": "00 00 00 00 00 00 CC DD",
                },
            ),
        ):
            diagnostics = service.write_point(device, point, 50.0)

        self.assertEqual(diagnostics["aurora_op"], 151)
        self.assertEqual(diagnostics["aurora_operation"], "set_power_limit")
        self.assertIn("aurora_tx_frame", diagnostics)
        self.assertIn("aurora_reply_frame", diagnostics)

    def test_probe_connection_returns_state_and_version_diagnostics(self) -> None:
        service = AuroraService()

        with (
            patch.object(service, "_open_serial_port", return_value=_FakeSerialPort()),
            patch.object(
                service,
                "_get_state",
                return_value={
                    "Global": 1,
                    "InvState": 2,
                    "DcDc1": 3,
                    "DcDc2": 4,
                    "Alarm": 5,
                },
            ),
            patch.object(
                service,
                "_probe_part_number",
                return_value={
                    "part_number": "3M04",
                    "part_number_raw": "-3M04-",
                    "part_number_source": "op_52",
                },
            ),
            patch.object(
                service,
                "_probe_version",
                return_value={"Model": "B", "Grid": "B", "Trafo": "F", "App": "7"},
            ),
        ):
            diagnostics = service.probe_connection(
                {
                    "port": "COM7",
                    "address": 2,
                    "baud_rate": 19200,
                    "parity": "N",
                    "stop_bits": 1,
                    "byte_size": 8,
                    "timeout_seconds": 0.5,
                    "retries": 1,
                }
            )

        self.assertEqual(diagnostics["global_state"], 1)
        self.assertEqual(diagnostics["inverter_state"], 2)
        self.assertEqual(diagnostics["alarm_code"], 5)
        self.assertEqual(diagnostics["part_number"], "3M04")
        self.assertEqual(diagnostics["model_code"], "B")
        self.assertEqual(diagnostics["application_code"], "7")

    def test_probe_part_number_uses_ascii_reply_and_normalizes_value(self) -> None:
        service = AuroraService()
        raw_reply = b"-3M04-"

        with patch.object(
            service,
            "_execute_request",
            return_value=(raw_reply + pack("<H", service._crc16_ccitt_reflected(raw_reply)), {}),
        ) as execute_mock:
            diagnostics = service._probe_part_number(
                serial_port=_FakeSerialPort(),
                address=2,
                settings={"timeout_seconds": 0.5, "retries": 0},
            )

        request = execute_mock.call_args.kwargs["request"]
        self.assertEqual(request.op, OP_GET_PART_NUMBER)
        self.assertEqual(diagnostics["part_number"], "3M04")
        self.assertEqual(diagnostics["part_number_raw"], "-3M04-")

    def test_parse_reply_adds_human_label_for_tx_state(self) -> None:
        service = AuroraService()
        payload = bytes.fromhex("33 00 00 00 00 00 22 3C")

        with self.assertRaises(AuroraProtocolError) as ctx:
            service._parse_reply(payload, reply_format="stateful")

        self.assertEqual(ctx.exception.diagnostics["aurora_reply_tx_state"], 51)
        self.assertEqual(
            ctx.exception.diagnostics["aurora_reply_tx_state_label"],
            "Command is not implemented",
        )


if __name__ == "__main__":
    unittest.main()
