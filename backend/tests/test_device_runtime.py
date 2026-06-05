import unittest
from datetime import UTC, datetime, timedelta

from app.schemas.device_overview_schemas import DeviceOverviewDiagnostics, DeviceOverviewMetrics
from app.schemas.device_schemas import DeviceResponse
from app.services.device_runtime import (
    get_effective_full_poll_interval_seconds,
    resolve_communication_state,
    resolve_data_freshness,
    resolve_runtime_status,
    uses_serial_like_polling,
)
from app.services.live_cache import ConnectionLifecycle, LiveCacheEntry


def _build_device() -> DeviceResponse:
    return DeviceResponse(
        device_id="device-1",
        name="Device 1",
        brand="Generic",
        model="Model 1",
        protocol="modbus_rtu",
        transport="serial",
        connection_settings={
            "port": "COM3",
            "slave_id": 1,
            "baud_rate": 9600,
            "parity": "N",
            "stop_bits": 1,
            "byte_size": 8,
            "timeout_seconds": 5.0,
            "retries": 1,
            "poll_interval_seconds": 15.0,
        },
        profile_overrides={},
        status="offline",
        created_at="2026-04-02T00:00:00+00:00",
    )


def _build_tcp_device() -> DeviceResponse:
    return DeviceResponse(
        device_id="device-tcp-1",
        name="Device TCP 1",
        brand="Generic",
        model="Model TCP 1",
        protocol="modbus_tcp",
        transport="tcp",
        connection_settings={
            "host": "192.168.1.10",
            "port": 502,
            "unit_id": 1,
            "timeout_seconds": 2.0,
            "retries": 1,
            "poll_interval_seconds": 15.0,
        },
        profile_overrides={},
        status="offline",
        created_at="2026-04-02T00:00:00+00:00",
    )


def _build_rtu_over_tcp_device() -> DeviceResponse:
    return DeviceResponse(
        device_id="device-rtu-tcp-1",
        name="Device RTU TCP 1",
        brand="Generic",
        model="Model RTU TCP 1",
        protocol="modbus_rtu",
        transport="tcp",
        connection_settings={
            "host": "192.168.1.20",
            "port": 4002,
            "unit_id": 10,
            "timeout_seconds": 5.0,
            "retries": 3,
            "poll_interval_seconds": 15.0,
        },
        profile_overrides={},
        status="offline",
        created_at="2026-04-02T00:00:00+00:00",
    )


def _build_failure_entry(*, age_seconds: float) -> LiveCacheEntry:
    timestamp = (datetime.now(UTC) - timedelta(seconds=age_seconds)).isoformat()
    return LiveCacheEntry(
        metrics=DeviceOverviewMetrics(
            power_kw=0.0,
            daily_energy_kwh=0.0,
            total_energy_kwh=0.0,
            temperature_c=25.0,
        ),
        diagnostics=DeviceOverviewDiagnostics(
            last_poll_status="stub_mode=false; stage=connect; protocol=modbus_rtu",
            response_time_ms=250,
            retries=1,
            last_error="Unable to connect to Modbus RTU device.",
            poll_kind="heartbeat",
        ),
        telemetry=[],
        timestamp=timestamp,
    )


class DeviceRuntimeTests(unittest.TestCase):
    def test_recent_contact_and_recent_full_data_keep_device_online(self) -> None:
        device = _build_device()
        failure_entry = _build_failure_entry(age_seconds=5)
        last_success_timestamp = (datetime.now(UTC) - timedelta(seconds=70)).isoformat()
        last_full_success_timestamp = (datetime.now(UTC) - timedelta(seconds=90)).isoformat()
        lifecycle = ConnectionLifecycle(
            has_seen_success=True,
            last_success_timestamp=last_success_timestamp,
            last_attempt_timestamp=failure_entry.timestamp,
            has_seen_full_success=True,
            last_full_success_timestamp=last_full_success_timestamp,
        )

        status = resolve_runtime_status(device, failure_entry, lifecycle)

        self.assertEqual(status, "online")

    def test_recent_serial_contact_without_recent_full_data_keeps_device_online(self) -> None:
        device = _build_device()
        failure_entry = _build_failure_entry(age_seconds=5)
        last_success_timestamp = (datetime.now(UTC) - timedelta(seconds=70)).isoformat()
        lifecycle = ConnectionLifecycle(
            has_seen_success=True,
            last_success_timestamp=last_success_timestamp,
            last_attempt_timestamp=failure_entry.timestamp,
            has_seen_full_success=False,
            last_full_success_timestamp=None,
        )

        status = resolve_runtime_status(device, failure_entry, lifecycle)

        self.assertEqual(status, "online")

    def test_large_serial_bus_recent_contact_keeps_device_online_while_full_sweep_is_pending(self) -> None:
        device = _build_device()
        failure_entry = _build_failure_entry(age_seconds=5)
        last_success_timestamp = (datetime.now(UTC) - timedelta(minutes=12)).isoformat()
        lifecycle = ConnectionLifecycle(
            has_seen_success=True,
            last_success_timestamp=last_success_timestamp,
            last_attempt_timestamp=failure_entry.timestamp,
            has_seen_full_success=False,
            last_full_success_timestamp=None,
        )

        status = resolve_runtime_status(
            device,
            failure_entry,
            lifecycle,
            endpoint_device_count=100,
        )

        self.assertEqual(status, "online")

    def test_large_serial_bus_stale_full_data_stays_online_when_contact_is_recent(self) -> None:
        device = _build_device()
        failure_entry = _build_failure_entry(age_seconds=5)
        lifecycle = ConnectionLifecycle(
            has_seen_success=True,
            last_success_timestamp=(datetime.now(UTC) - timedelta(minutes=12)).isoformat(),
            last_attempt_timestamp=failure_entry.timestamp,
            has_seen_full_success=True,
            last_full_success_timestamp=(datetime.now(UTC) - timedelta(minutes=45)).isoformat(),
        )

        status = resolve_runtime_status(
            device,
            failure_entry,
            lifecycle,
            endpoint_device_count=100,
        )

        self.assertEqual(status, "online")

    def test_rtu_over_tcp_uses_serial_like_runtime_windows(self) -> None:
        device = _build_rtu_over_tcp_device()

        self.assertTrue(uses_serial_like_polling(device))
        self.assertEqual(get_effective_full_poll_interval_seconds(device), 60.0)

    def test_rtu_over_tcp_recent_contact_keeps_device_online_while_full_data_waits(self) -> None:
        device = _build_rtu_over_tcp_device()
        failure_entry = _build_failure_entry(age_seconds=5)
        lifecycle = ConnectionLifecycle(
            has_seen_success=True,
            last_success_timestamp=(datetime.now(UTC) - timedelta(seconds=60)).isoformat(),
            last_attempt_timestamp=failure_entry.timestamp,
            has_seen_full_success=True,
            last_full_success_timestamp=(datetime.now(UTC) - timedelta(minutes=20)).isoformat(),
        )

        status = resolve_runtime_status(device, failure_entry, lifecycle)

        self.assertEqual(status, "online")

    def test_recent_serial_contact_with_stale_full_data_keeps_device_online(self) -> None:
        device = _build_device()
        failure_entry = _build_failure_entry(age_seconds=5)
        last_success_timestamp = (datetime.now(UTC) - timedelta(seconds=60)).isoformat()
        last_full_success_timestamp = (datetime.now(UTC) - timedelta(minutes=20)).isoformat()
        lifecycle = ConnectionLifecycle(
            has_seen_success=True,
            last_success_timestamp=last_success_timestamp,
            last_attempt_timestamp=failure_entry.timestamp,
            has_seen_full_success=True,
            last_full_success_timestamp=last_full_success_timestamp,
        )

        status = resolve_runtime_status(device, failure_entry, lifecycle)

        self.assertEqual(status, "online")

    def test_old_last_success_eventually_marks_device_offline(self) -> None:
        device = _build_device()
        failure_entry = _build_failure_entry(age_seconds=5)
        last_success_timestamp = (datetime.now(UTC) - timedelta(seconds=700)).isoformat()
        lifecycle = ConnectionLifecycle(
            has_seen_success=True,
            last_success_timestamp=last_success_timestamp,
            last_attempt_timestamp=failure_entry.timestamp,
            has_seen_full_success=True,
            last_full_success_timestamp=(datetime.now(UTC) - timedelta(seconds=700)).isoformat(),
        )

        status = resolve_runtime_status(device, failure_entry, lifecycle)

        self.assertEqual(status, "offline")

    def test_runtime_helpers_expose_communication_and_freshness_separately(self) -> None:
        device = _build_device()
        lifecycle = ConnectionLifecycle(
            has_seen_success=True,
            last_success_timestamp=(datetime.now(UTC) - timedelta(seconds=60)).isoformat(),
            last_attempt_timestamp=(datetime.now(UTC) - timedelta(seconds=5)).isoformat(),
            has_seen_full_success=True,
            last_full_success_timestamp=(datetime.now(UTC) - timedelta(minutes=20)).isoformat(),
        )

        communication_state = resolve_communication_state(device, lifecycle)
        data_freshness = resolve_data_freshness(device, lifecycle)

        self.assertEqual(communication_state, "online")
        self.assertEqual(data_freshness, "stale")

    def test_large_shared_tcp_endpoint_recent_contact_keeps_device_online(self) -> None:
        device = _build_tcp_device()
        failure_entry = _build_failure_entry(age_seconds=5)
        lifecycle = ConnectionLifecycle(
            has_seen_success=True,
            last_success_timestamp=(datetime.now(UTC) - timedelta(minutes=12)).isoformat(),
            last_attempt_timestamp=failure_entry.timestamp,
            has_seen_full_success=True,
            last_full_success_timestamp=(datetime.now(UTC) - timedelta(minutes=12)).isoformat(),
        )

        status = resolve_runtime_status(
            device,
            failure_entry,
            lifecycle,
            endpoint_device_count=40,
        )

        self.assertEqual(status, "online")

    def test_large_shared_tcp_endpoint_eventually_goes_offline_when_contact_is_too_old(self) -> None:
        device = _build_tcp_device()
        failure_entry = _build_failure_entry(age_seconds=5)
        lifecycle = ConnectionLifecycle(
            has_seen_success=True,
            last_success_timestamp=(datetime.now(UTC) - timedelta(minutes=20)).isoformat(),
            last_attempt_timestamp=failure_entry.timestamp,
            has_seen_full_success=True,
            last_full_success_timestamp=(datetime.now(UTC) - timedelta(minutes=20)).isoformat(),
        )

        status = resolve_runtime_status(
            device,
            failure_entry,
            lifecycle,
            endpoint_device_count=40,
        )

        self.assertEqual(status, "offline")


if __name__ == "__main__":
    unittest.main()
