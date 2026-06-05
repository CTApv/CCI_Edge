import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.schemas.device_schemas import DeviceResponse
from app.services.system_health_service import SystemHealthService


def _build_device() -> DeviceResponse:
    return DeviceResponse(
        device_id="device-1",
        name="Device 1",
        brand="Huawei",
        model="SUN2000",
        protocol="modbus_rtu",
        transport="serial",
        connection_settings={
            "port": "COM3",
            "slave_id": 1,
            "baud_rate": 9600,
            "parity": "N",
            "stop_bits": 1,
            "byte_size": 8,
            "timeout_seconds": 2.0,
            "retries": 1,
            "poll_interval_seconds": 15.0,
        },
        profile_overrides={},
        status="online",
        created_at="2026-04-10T00:00:00+00:00",
    )


class SystemHealthServiceTests(unittest.TestCase):
    def test_health_snapshot_merges_serial_scheduler_metrics_into_endpoint_runtimes(self) -> None:
        service = SystemHealthService()
        device = _build_device()

        with (
            patch("app.services.system_health_service.device_service.list_devices", return_value=[device]),
            patch(
                "app.services.system_health_service.endpoint_runtime_service.get_snapshots",
                return_value=[
                    {
                        "endpoint_type": "serial",
                        "endpoint_label": "COM3",
                        "device_count": 1,
                        "online_count": 1,
                        "pending_count": 0,
                        "offline_count": 0,
                        "shared": False,
                        "state": "healthy",
                        "consecutive_connect_failures": 0,
                        "remaining_backoff_seconds": 0.0,
                        "cooldown_until": None,
                        "last_attempt_at": None,
                        "last_success_at": None,
                        "last_error_at": None,
                        "last_error_stage": None,
                        "last_error": None,
                        "last_poll_status": None,
                        "last_outcome": "success",
                        "skipped_polls": 0,
                        "devices": ["Device 1 | Huawei | SUN2000"],
                    }
                ],
            ),
            patch(
                "app.services.system_health_service.polling_engine.get_serial_endpoint_snapshots",
                return_value=[
                    {
                        "endpoint_type": "serial",
                        "endpoint_label": "COM3",
                        "queued_full_due_count": 4,
                        "queued_heartbeat_due_count": 2,
                        "planned_full_count": 2,
                        "planned_heartbeat_count": 1,
                        "executed_full_count": 2,
                        "executed_heartbeat_count": 1,
                        "priority_deferral_count": 3,
                        "last_priority_at": "2026-04-10T10:00:00+00:00",
                        "last_cycle_started_at": "2026-04-10T10:00:01+00:00",
                        "last_cycle_completed_at": "2026-04-10T10:00:02+00:00",
                        "last_cycle_duration_ms": 850,
                        "average_cycle_duration_ms": 910.5,
                        "average_operation_duration_ms": 220.0,
                    }
                ],
            ),
            patch(
                "app.services.system_health_service.connection_manager.get_modbus_tcp_runtime_snapshots",
                return_value=[],
            ),
        ):
            snapshot = service.get_snapshot()

        runtime = snapshot["endpoint_runtimes"][0]
        self.assertEqual(runtime["endpoint_label"], "COM3")
        self.assertEqual(runtime["queued_full_due_count"], 4)
        self.assertEqual(runtime["priority_deferral_count"], 3)
        self.assertEqual(runtime["last_cycle_duration_ms"], 850)
        self.assertEqual(runtime["average_operation_duration_ms"], 220.0)

    def test_health_snapshot_merges_tcp_connection_metrics_into_endpoint_runtimes(self) -> None:
        service = SystemHealthService()
        device = DeviceResponse(
            device_id="device-tcp-1",
            name="Device TCP 1",
            brand="ZCS",
            model="Azzurro",
            protocol="modbus_tcp",
            transport="tcp",
            connection_settings={
                "host": "192.168.2.108",
                "port": 5020,
                "unit_id": 1,
                "timeout_seconds": 2.0,
                "retries": 1,
                "poll_interval_seconds": 15.0,
            },
            profile_overrides={},
            status="online",
            created_at="2026-04-10T00:00:00+00:00",
        )

        with (
            patch("app.services.system_health_service.device_service.list_devices", return_value=[device]),
            patch(
                "app.services.system_health_service.endpoint_runtime_service.get_snapshots",
                return_value=[
                    {
                        "endpoint_type": "tcp",
                        "endpoint_label": "192.168.2.108:5020",
                        "device_count": 1,
                        "online_count": 1,
                        "pending_count": 0,
                        "offline_count": 0,
                        "shared": False,
                        "state": "healthy",
                        "consecutive_connect_failures": 0,
                        "remaining_backoff_seconds": 0.0,
                        "cooldown_until": None,
                        "last_attempt_at": None,
                        "last_success_at": None,
                        "last_error_at": None,
                        "last_error_stage": None,
                        "last_error": None,
                        "last_poll_status": None,
                        "last_outcome": "success",
                        "skipped_polls": 0,
                        "devices": ["Device TCP 1 | ZCS | Azzurro"],
                    }
                ],
            ),
            patch(
                "app.services.system_health_service.polling_engine.get_serial_endpoint_snapshots",
                return_value=[],
            ),
            patch(
                "app.services.system_health_service.connection_manager.get_modbus_tcp_runtime_snapshots",
                return_value=[
                    {
                        "endpoint_type": "tcp",
                        "endpoint_label": "192.168.2.108:5020",
                        "last_lock_wait_ms": 12.5,
                        "average_lock_wait_ms": 8.25,
                        "last_operation_duration_ms": 21.0,
                        "average_operation_duration_ms": 19.75,
                        "last_round_trip_duration_ms": 33.5,
                        "average_round_trip_duration_ms": 28.0,
                        "tcp_sample_count": 14,
                    }
                ],
            ),
        ):
            snapshot = service.get_snapshot()

        runtime = snapshot["endpoint_runtimes"][0]
        self.assertEqual(runtime["endpoint_label"], "192.168.2.108:5020")
        self.assertEqual(runtime["last_lock_wait_ms"], 12.5)
        self.assertEqual(runtime["average_lock_wait_ms"], 8.25)
        self.assertEqual(runtime["last_round_trip_duration_ms"], 33.5)
        self.assertEqual(runtime["tcp_sample_count"], 14)

    def test_health_snapshot_reports_ready_modbus_tcp_broadcast_group(self) -> None:
        service = SystemHealthService()
        devices = [
            DeviceResponse(
                device_id="tcp-1",
                name="TCP 1",
                brand="Generic",
                model="Gateway",
                protocol="modbus_tcp",
                transport="tcp",
                connection_settings={
                    "host": "192.168.2.108",
                    "port": 5020,
                    "unit_id": 52,
                    "timeout_seconds": 2.0,
                    "retries": 1,
                },
                profile_overrides={},
                status="online",
                created_at="2026-04-10T00:00:00+00:00",
            ),
            DeviceResponse(
                device_id="tcp-2",
                name="TCP 2",
                brand="Generic",
                model="Gateway",
                protocol="modbus_tcp",
                transport="tcp",
                connection_settings={
                    "host": "192.168.2.108",
                    "port": 5020,
                    "unit_id": 53,
                    "timeout_seconds": 2.0,
                    "retries": 1,
                },
                profile_overrides={},
                status="online",
                created_at="2026-04-10T00:00:00+00:00",
            ),
        ]
        command_point = SimpleNamespace(key="active_power_limit")
        resolution = SimpleNamespace(command_point=command_point, requested_value=50.0)

        with (
            patch("app.services.system_health_service.device_service.list_devices", return_value=devices),
            patch(
                "app.services.system_health_service.endpoint_runtime_service.get_snapshots",
                return_value=[],
            ),
            patch(
                "app.services.system_health_service.polling_engine.get_serial_endpoint_snapshots",
                return_value=[],
            ),
            patch(
                "app.services.system_health_service.connection_manager.get_modbus_tcp_runtime_snapshots",
                return_value=[],
            ),
            patch(
                "app.services.system_health_service.inverter_profile_resolver.resolve_for_device",
                return_value=SimpleNamespace(command_points=[command_point]),
            ),
            patch(
                "app.services.system_health_service.active_power_limit_resolver.resolve_for_write",
                return_value=resolution,
            ),
            patch(
                "app.services.system_health_service.inverter_io_service.build_command_broadcast_signature",
                return_value=("generic_modbus", "holding", 0x1106, (500,), True),
            ),
        ):
            snapshot = service.get_snapshot()

        self.assertEqual(len(snapshot["broadcast_groups"]), 1)
        group = snapshot["broadcast_groups"][0]
        self.assertEqual(group["endpoint_type"], "modbus_tcp_gateway")
        self.assertEqual(group["endpoint_label"], "192.168.2.108:5020")
        self.assertEqual(group["broadcast_mode"], "modbus_tcp")
        self.assertEqual(group["state"], "ready")
        self.assertEqual(group["command_profile_count"], 1)
        self.assertEqual(group["duplicate_unit_ids"], [])


if __name__ == "__main__":
    unittest.main()
