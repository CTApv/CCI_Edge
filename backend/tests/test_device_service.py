import unittest
from unittest.mock import Mock, patch

from app.schemas.device_schemas import DeviceCreate, DeviceResponse, DeviceUpdate
from app.services.device_service import DeviceService


def _build_device(device_id: str, name: str) -> DeviceResponse:
    return DeviceResponse(
        device_id=device_id,
        name=name,
        brand="ZCS",
        model="ZUCCHETTI Azzurro 3PH 60KTL-V3",
        protocol="modbus_tcp",
        transport="tcp",
        connection_settings={"host": "192.168.2.108", "port": 5020, "unit_id": 1},
        profile_overrides={},
        status="online",
        created_at="2026-04-22T10:00:00+00:00",
    )


class DeviceServiceDeleteTests(unittest.TestCase):
    def _build_service(self, devices: list[DeviceResponse]) -> DeviceService:
        with (
            patch.object(DeviceService, "_initialize_storage"),
            patch.object(DeviceService, "_load_devices", return_value=list(devices)),
        ):
            return DeviceService()

    def test_delete_device_returns_success_when_cleanup_step_fails(self) -> None:
        device = _build_device("device-1", "Inverter 1")
        service = self._build_service([device])

        with (
            patch.object(service, "_delete_persisted_device") as delete_persisted,
            patch("app.services.device_service.live_cache.delete"),
            patch(
                "app.services.device_service.power_history_service.delete_device_history",
                side_effect=RuntimeError("history locked"),
            ),
            patch(
                "app.services.device_command_state_service.device_command_state_service.delete_device_states"
            ) as delete_states,
            patch(
                "app.services.fleet_dispatch_service.fleet_dispatch_service.request_dispatch"
            ) as request_dispatch,
        ):
            deleted = service.delete_device(device.device_id)

        self.assertTrue(deleted)
        delete_persisted.assert_called_once_with(device.device_id)
        delete_states.assert_called_once_with(device.device_id)
        request_dispatch.assert_called_once()
        self.assertEqual(service._devices, [])

    def test_delete_all_devices_returns_count_when_cleanup_step_fails(self) -> None:
        devices = [
            _build_device("device-1", "Inverter 1"),
            _build_device("device-2", "Inverter 2"),
        ]
        service = self._build_service(devices)

        def delete_history(device_id: str) -> None:
            if device_id == "device-1":
                raise RuntimeError("history locked")

        with (
            patch.object(service, "_delete_all_persisted_devices") as delete_all_persisted,
            patch("app.services.device_service.live_cache.delete"),
            patch(
                "app.services.device_service.power_history_service.delete_device_history",
                side_effect=delete_history,
            ),
            patch(
                "app.services.device_command_state_service.device_command_state_service.delete_device_states"
            ) as delete_states,
            patch(
                "app.services.fleet_dispatch_service.fleet_dispatch_service.request_dispatch"
            ) as request_dispatch,
        ):
            deleted_count = service.delete_all_devices()

        self.assertEqual(deleted_count, 2)
        delete_all_persisted.assert_called_once_with()
        self.assertEqual(delete_states.call_count, 2)
        delete_states.assert_any_call("device-1")
        delete_states.assert_any_call("device-2")
        request_dispatch.assert_called_once()
        self.assertEqual(service._devices, [])

    def test_create_device_rejects_duplicate_unit_on_same_tcp_endpoint(self) -> None:
        existing_device = _build_device("device-1", "Inverter 1")
        service = self._build_service([existing_device])
        payload = DeviceCreate(
            name="Inverter 2",
            brand="ZCS",
            model="ZUCCHETTI Azzurro 3PH 60KTL-V3",
            protocol="modbus_tcp",
            transport="tcp",
            connection_settings={"host": "192.168.2.108", "port": 5020, "unit_id": 1},
            profile_overrides={},
        )

        with (
            patch.object(service, "_ensure_catalog_profile_exists"),
            self.assertRaisesRegex(ValueError, "Unit ID 1 gia configurato"),
        ):
            service.create_device(payload)

    def test_update_device_allows_same_unit_for_current_device(self) -> None:
        existing_device = _build_device("device-1", "Inverter 1")
        service = self._build_service([existing_device])
        payload = DeviceUpdate(
            name="Inverter 1",
            brand="ZCS",
            model="ZUCCHETTI Azzurro 3PH 60KTL-V3",
            protocol="modbus_tcp",
            transport="tcp",
            connection_settings={"host": "192.168.2.108", "port": 5020, "unit_id": 1},
            profile_overrides={},
            status="online",
        )

        with (
            patch.object(service, "_ensure_catalog_profile_exists"),
            patch.object(service, "_persist_device"),
            patch("app.services.device_service.live_cache.delete"),
            patch("app.services.fleet_dispatch_service.fleet_dispatch_service.request_dispatch"),
        ):
            updated_device = service.update_device(existing_device.device_id, payload)

        self.assertIsNotNone(updated_device)
        self.assertEqual(updated_device.connection_settings["unit_id"], 1)
