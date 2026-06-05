import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.config import settings
from app.services.hsm_bridge_config_service import HsmBridgeConfigService
from app.services.hsm_bridge_service import HsmBridgeService


class HsmBridgeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._original_database_path = settings.database_path
        settings.database_path = Path(self._temp_dir.name) / "hsm-bridge-test.db"

    def tearDown(self) -> None:
        settings.database_path = self._original_database_path
        self._temp_dir.cleanup()

    def test_config_service_persists_updated_values(self) -> None:
        service = HsmBridgeConfigService()

        updated = service.update_config(
            enabled=True,
            hsm_port="COM5",
            inverter_port="COM7",
            hsm_baud_rate=19200,
            hsm_parity="E",
            hsm_stop_bits=2,
            hsm_byte_size=8,
            frame_gap_ms=45,
            forward_delay_ms=120,
            ack_timeout_ms=900,
        )

        self.assertTrue(updated.enabled)
        self.assertEqual(updated.hsm_port, "COM5")
        self.assertEqual(updated.inverter_port, "COM7")
        self.assertEqual(updated.hsm_baud_rate, 19200)
        self.assertEqual(updated.hsm_parity, "E")
        self.assertEqual(updated.hsm_stop_bits, 2)
        self.assertEqual(updated.frame_gap_ms, 45)
        self.assertEqual(updated.forward_delay_ms, 120)
        self.assertEqual(updated.ack_timeout_ms, 900)

    def test_resolve_inverter_line_accepts_uniform_modbus_rtu_devices(self) -> None:
        service = HsmBridgeService()
        config_service = HsmBridgeConfigService()
        config = config_service.update_config(
            enabled=True,
            hsm_port="COM5",
            inverter_port="COM7",
            hsm_baud_rate=9600,
            hsm_parity="N",
            hsm_stop_bits=1,
            hsm_byte_size=8,
            frame_gap_ms=30,
            forward_delay_ms=300,
            ack_timeout_ms=500,
        )
        devices = [
            SimpleNamespace(
                transport="serial",
                protocol="modbus_rtu",
                connection_settings={
                    "port": "COM7",
                    "baud_rate": 19200,
                    "parity": "E",
                    "stop_bits": 2,
                    "byte_size": 8,
                    "use_rs485_mode": True,
                },
            ),
            SimpleNamespace(
                transport="serial",
                protocol="modbus_rtu",
                connection_settings={
                    "port": "COM7",
                    "baud_rate": 19200,
                    "parity": "E",
                    "stop_bits": 2,
                    "byte_size": 8,
                    "use_rs485_mode": True,
                },
            ),
        ]

        with patch("app.services.hsm_bridge_service.device_service.list_devices", return_value=devices):
            resolution = service._resolve_inverter_line(config)

        self.assertTrue(resolution.ready)
        self.assertEqual(resolution.protocol, "modbus_rtu")
        self.assertEqual(resolution.baud_rate, 19200)
        self.assertEqual(resolution.parity, "E")
        self.assertEqual(resolution.stop_bits, 2)
        self.assertEqual(resolution.byte_size, 8)
        self.assertEqual(resolution.advanced_options, {"use_rs485_mode": True})

    def test_resolve_inverter_line_rejects_mixed_serial_settings(self) -> None:
        service = HsmBridgeService()
        config = HsmBridgeConfigService().update_config(
            enabled=True,
            hsm_port="COM5",
            inverter_port="COM7",
            hsm_baud_rate=9600,
            hsm_parity="N",
            hsm_stop_bits=1,
            hsm_byte_size=8,
            frame_gap_ms=30,
            forward_delay_ms=300,
            ack_timeout_ms=500,
        )
        devices = [
            SimpleNamespace(
                transport="serial",
                protocol="modbus_rtu",
                connection_settings={
                    "port": "COM7",
                    "baud_rate": 19200,
                    "parity": "E",
                    "stop_bits": 2,
                    "byte_size": 8,
                },
            ),
            SimpleNamespace(
                transport="serial",
                protocol="modbus_rtu",
                connection_settings={
                    "port": "COM7",
                    "baud_rate": 9600,
                    "parity": "N",
                    "stop_bits": 1,
                    "byte_size": 8,
                },
            ),
        ]

        with patch("app.services.hsm_bridge_service.device_service.list_devices", return_value=devices):
            resolution = service._resolve_inverter_line(config)

        self.assertFalse(resolution.ready)
        self.assertIn("parametri seriali differenti", resolution.note or "")


if __name__ == "__main__":
    unittest.main()
