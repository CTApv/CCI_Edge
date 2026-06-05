import unittest

from app.catalog.bonfiglioli_catalog import BONFIGLIOLI_RPS_MODELS
from app.core.connection_settings import normalize_persisted_connection_settings
from app.schemas.device_schemas import DeviceCreate, DeviceUpdate
from app.schemas.protocol_schemas import ProtocolTestRequest
from app.services.device_service import device_service


class ConnectionSettingsValidationTests(unittest.TestCase):
    def test_device_create_normalizes_tcp_aliases_and_defaults(self) -> None:
        payload = DeviceCreate(
            name="  Inverter 1  ",
            brand=" Huawei ",
            model=" SUN2000 ",
            protocol="modbus_tcp",
            transport="tcp",
            connection_settings={
                "host": " 192.168.1.10 ",
                "port": "502",
                "slave_id": "7",
            },
            profile_overrides={},
        )

        self.assertEqual(payload.name, "Inverter 1")
        self.assertEqual(payload.brand, "Huawei")
        self.assertEqual(payload.model, "SUN2000")
        self.assertEqual(payload.connection_settings["host"], "192.168.1.10")
        self.assertEqual(payload.connection_settings["port"], 502)
        self.assertEqual(payload.connection_settings["unit_id"], 7)
        self.assertEqual(payload.connection_settings["timeout_seconds"], 5)
        self.assertEqual(payload.connection_settings["retries"], 3)
        self.assertEqual(payload.connection_settings["poll_interval_seconds"], 15)

    def test_device_update_rejects_invalid_transport_for_protocol(self) -> None:
        with self.assertRaisesRegex(ValueError, "trasporto selezionato non corrisponde"):
            DeviceUpdate(
                name="Inverter 1",
                brand="Huawei",
                model="SUN2000",
                protocol="modbus_tcp",
                transport="serial",
                connection_settings={"host": "192.168.1.10", "unit_id": 1},
                profile_overrides={},
                status="pending",
            )

    def test_protocol_test_request_preserves_transport_mismatch_for_service_diagnostics(self) -> None:
        payload = ProtocolTestRequest(
            protocol="modbus_tcp",
            transport="serial",
            connection_settings={"host": "192.168.1.10", "port": "502", "unit_id": "1"},
        )

        self.assertEqual(payload.transport, "serial")
        self.assertEqual(payload.connection_settings["host"], "192.168.1.10")
        self.assertEqual(payload.connection_settings["port"], "502")
        self.assertEqual(payload.connection_settings["unit_id"], 1)

    def test_persisted_settings_can_be_normalized_without_required_fields(self) -> None:
        normalized = normalize_persisted_connection_settings(
            protocol="modbus_rtu",
            transport="serial",
            settings={"port": "COM4", "unit_id": "12"},
        )

        self.assertEqual(normalized["port"], "COM4")
        self.assertEqual(normalized["slave_id"], 12)
        self.assertEqual(normalized["baud_rate"], 9600)
        self.assertEqual(normalized["parity"], "N")

    def test_device_create_normalizes_modbus_rtu_over_tcp_settings(self) -> None:
        payload = DeviceCreate(
            name="Gateway RTU",
            brand="Huawei",
            model="SUN2000",
            protocol="modbus_rtu",
            transport="tcp",
            connection_settings={
                "host": " 192.168.2.15 ",
                "port": "502",
                "slave_id": "9",
            },
            profile_overrides={},
        )

        self.assertEqual(payload.connection_settings["host"], "192.168.2.15")
        self.assertEqual(payload.connection_settings["port"], 502)
        self.assertEqual(payload.connection_settings["unit_id"], 9)
        self.assertEqual(payload.connection_settings["timeout_seconds"], 5)
        self.assertEqual(payload.connection_settings["retries"], 3)
        self.assertEqual(payload.connection_settings["poll_interval_seconds"], 15)

    def test_optional_poll_and_write_settings_are_accepted(self) -> None:
        payload = DeviceCreate(
            name="RTU tuned",
            brand="Huawei",
            model="SUN2000",
            protocol="modbus_rtu",
            transport="serial",
            connection_settings={
                "port": "COM5",
                "slave_id": 8,
                "poll_timeout_seconds": "0.8",
                "poll_retries": "0",
                "write_timeout_seconds": "3.5",
                "write_retries": "1",
            },
            profile_overrides={},
        )

        self.assertEqual(payload.connection_settings["poll_timeout_seconds"], 0.8)
        self.assertEqual(payload.connection_settings["poll_retries"], 0)
        self.assertEqual(payload.connection_settings["write_timeout_seconds"], 3.5)
        self.assertEqual(payload.connection_settings["write_retries"], 1)

    def test_delta_variant_is_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "variante Delta"):
            DeviceCreate(
                name="Delta",
                brand="Delta",
                model="SI",
                protocol="delta_rs485",
                transport="serial",
                connection_settings={
                    "port": "COM3",
                    "address": 1,
                    "delta_variant": 2,
                },
                profile_overrides={},
            )

    def test_bonfiglioli_catalog_defaults_are_applied_on_device_create(self) -> None:
        payload = DeviceCreate(
            name="Bonfiglioli 1",
            brand="Bonfiglioli",
            model=BONFIGLIOLI_RPS_MODELS[0],
            protocol="modbus_rtu",
            transport="serial",
            connection_settings={
                "port": "COM7",
                "slave_id": 5,
            },
            profile_overrides={},
        )

        self.assertEqual(payload.connection_settings["port"], "COM7")
        self.assertEqual(payload.connection_settings["slave_id"], 5)
        self.assertEqual(payload.connection_settings["baud_rate"], 19200)
        self.assertEqual(payload.connection_settings["parity"], "E")
        self.assertEqual(payload.connection_settings["stop_bits"], 2)
        self.assertEqual(payload.connection_settings["byte_size"], 8)

    def test_ingeteam_exact_catalog_profile_is_required_and_preserved(self) -> None:
        payload = DeviceCreate(
            name="Ingeteam 630",
            brand="Ingeteam",
            model="Ingecon SUN 630HE TL",
            protocol="modbus_rtu",
            transport="serial",
            connection_settings={
                "port": "COM9",
                "slave_id": 7,
            },
            profile_overrides={},
        )

        self.assertEqual(payload.brand, "Ingeteam")
        self.assertEqual(payload.model, "Ingecon SUN 630HE TL")
        self.assertEqual(payload.protocol, "modbus_rtu")
        self.assertEqual(payload.transport, "serial")
        self.assertEqual(payload.connection_settings["port"], "COM9")
        self.assertEqual(payload.connection_settings["slave_id"], 7)
        self.assertEqual(payload.connection_settings["baud_rate"], 9600)
        self.assertEqual(payload.connection_settings["parity"], "N")
        self.assertEqual(payload.connection_settings["stop_bits"], 1)

    def test_device_service_rejects_unknown_model_for_selected_brand_protocol_and_transport(self) -> None:
        payload = DeviceCreate(
            name="Ingeteam custom",
            brand="Ingeteam",
            model="Ingecon SUN 999HE TL",
            protocol="modbus_rtu",
            transport="serial",
            connection_settings={
                "port": "COM9",
                "slave_id": 7,
            },
            profile_overrides={},
        )

        with self.assertRaisesRegex(ValueError, "profilo selezionato non e disponibile nel catalogo inverter"):
            device_service.create_device(payload)


if __name__ == "__main__":
    unittest.main()
