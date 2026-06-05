import unittest
from time import monotonic

from app.schemas.device_overview_schemas import (
    DeviceOverviewDiagnostics,
    DeviceOverviewMetrics,
)
from app.schemas.device_schemas import DeviceResponse
from app.services.endpoint_runtime_service import EndpointRuntimeService
from app.services.live_cache import LiveCacheEntry


def _build_device(
    *,
    device_id: str = "device-1",
    name: str = "Device 1",
    status: str = "offline",
) -> DeviceResponse:
    return DeviceResponse(
        device_id=device_id,
        name=name,
        brand="Huawei",
        model="SUN2000",
        protocol="modbus_tcp",
        transport="tcp",
        connection_settings={
            "host": "192.168.1.10",
            "port": 502,
            "unit_id": 1,
            "timeout_seconds": 3.0,
            "retries": 0,
        },
        profile_overrides={},
        status=status,
        created_at="2026-03-24T00:00:00+00:00",
    )


def _build_entry(
    *,
    stage: str,
    error: str | None,
    timestamp: str,
) -> LiveCacheEntry:
    return LiveCacheEntry(
        metrics=DeviceOverviewMetrics(
            power_kw=0.0,
            daily_energy_kwh=0.0,
            total_energy_kwh=0.0,
            temperature_c=25.0,
        ),
        diagnostics=DeviceOverviewDiagnostics(
            last_poll_status=f"stub_mode=false; stage={stage}; protocol=modbus_tcp",
            response_time_ms=25,
            retries=0,
            last_error=error,
        ),
        telemetry=[],
        timestamp=timestamp,
    )


class EndpointRuntimeServiceTests(unittest.TestCase):
    def test_connect_failure_starts_cooldown_and_reports_snapshot(self) -> None:
        service = EndpointRuntimeService()
        device = _build_device()
        start = monotonic()
        failure_entry = _build_entry(
            stage="connect",
            error="Unable to connect to Modbus TCP device.",
            timestamp="2026-03-24T10:00:00+00:00",
        )

        service.record_poll_result(device, failure_entry, now=start)

        decision = service.get_backoff_decision(device, now=start)
        snapshot = service.get_snapshots([device])[0]

        self.assertTrue(decision.active)
        self.assertEqual(decision.consecutive_connect_failures, 1)
        self.assertEqual(snapshot["state"], "cooldown")
        self.assertEqual(snapshot["last_error_stage"], "connect")
        self.assertEqual(snapshot["last_outcome"], "connect_error")
        self.assertEqual(snapshot["endpoint_label"], "192.168.1.10:502")

    def test_success_clears_existing_cooldown(self) -> None:
        service = EndpointRuntimeService()
        device = _build_device()
        start = monotonic()
        failure_entry = _build_entry(
            stage="connect",
            error="Unable to connect to Modbus TCP device.",
            timestamp="2026-03-24T10:00:00+00:00",
        )
        success_entry = _build_entry(
            stage="read_register",
            error=None,
            timestamp="2026-03-24T10:00:05+00:00",
        )

        service.record_poll_result(device, failure_entry, now=start)
        service.record_poll_result(
            _build_device(status="online"),
            success_entry,
            now=start + 10.0,
        )

        decision = service.get_backoff_decision(device, now=start + 10.0)
        snapshot = service.get_snapshots([_build_device(status="online")])[0]

        self.assertFalse(decision.active)
        self.assertEqual(snapshot["state"], "healthy")
        self.assertEqual(snapshot["consecutive_connect_failures"], 0)
        self.assertIsNone(snapshot["last_error"])
        self.assertEqual(snapshot["last_success_at"], "2026-03-24T10:00:05+00:00")


if __name__ == "__main__":
    unittest.main()
