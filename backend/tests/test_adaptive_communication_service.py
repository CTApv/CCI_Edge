import unittest
from time import monotonic

from app.schemas.device_overview_schemas import DeviceOverviewDiagnostics, DeviceOverviewMetrics
from app.schemas.device_schemas import DeviceResponse
from app.services.adaptive_communication_service import AdaptiveCommunicationService
from app.services.live_cache import LiveCacheEntry


def _build_device(*, device_id: str = "device-1") -> DeviceResponse:
    return DeviceResponse(
        device_id=device_id,
        name=f"Device {device_id}",
        brand="SOLAX POWER",
        model="X3-ULTRA",
        protocol="modbus_tcp",
        transport="tcp",
        connection_settings={
            "host": "192.168.2.108",
            "port": 5020,
            "unit_id": 1,
            "timeout_seconds": 2.0,
            "retries": 1,
            "inter_request_delay_ms": 1000,
        },
        profile_overrides={},
        status="online",
        created_at="2026-06-12T00:00:00+00:00",
    )


def _build_entry(
    *,
    success: bool,
    response_time_ms: int = 100,
    poll_kind: str = "heartbeat",
) -> LiveCacheEntry:
    return LiveCacheEntry(
        metrics=DeviceOverviewMetrics(
            power_kw=0.0,
            daily_energy_kwh=0.0,
            total_energy_kwh=0.0,
            temperature_c=25.0,
        ),
        diagnostics=DeviceOverviewDiagnostics(
            last_poll_status=(
                f"stub_mode=false; stage={'read_register' if success else 'exception'}; "
                f"poll_kind={poll_kind}; protocol=modbus_tcp"
            ),
            response_time_ms=response_time_ms,
            retries=1,
            last_error=None if success else "No response received",
            poll_kind=poll_kind,
        ),
        telemetry=[],
        timestamp="2026-06-12T10:00:00+00:00",
    )


class AdaptiveCommunicationServiceTests(unittest.TestCase):
    def test_stable_endpoint_reduces_delay_timeout_and_retries(self) -> None:
        service = AdaptiveCommunicationService()
        device = _build_device()

        for index in range(28):
            service.record_request_result(
                device,
                duration_ms=100 + (index % 3),
                success=True,
            )
            service.record_poll_result(
                device,
                _build_entry(success=True, response_time_ms=100 + (index % 3)),
            )

        policy = service.resolve_poll_policy(
            device,
            configured_timeout_seconds=2.0,
            configured_retries=1,
        )

        self.assertEqual(policy.mode, "optimized")
        self.assertEqual(policy.retries, 0)
        self.assertEqual(policy.timeout_seconds, 0.28)
        self.assertEqual(policy.inter_request_delay_ms, 100.0)

    def test_tcp_adaptive_timeout_never_drops_below_floor(self) -> None:
        service = AdaptiveCommunicationService()
        device = _build_device()
        for _ in range(28):
            service.record_request_result(device, duration_ms=10, success=True)
            service.record_poll_result(device, _build_entry(success=True))

        policy = service.resolve_poll_policy(
            device,
            configured_timeout_seconds=2.0,
            configured_retries=1,
        )

        self.assertEqual(policy.timeout_seconds, 0.25)

    def test_failed_device_is_quarantined_without_quarantining_endpoint(self) -> None:
        service = AdaptiveCommunicationService()
        failed_device = _build_device(device_id="failed")
        healthy_device = _build_device(device_id="healthy")
        start = monotonic()

        service.record_poll_result(failed_device, _build_entry(success=False), now=start)
        service.record_poll_result(failed_device, _build_entry(success=False), now=start + 1)

        failed_decision = service.get_device_backoff_decision(
            failed_device,
            now=start + 1,
        )
        healthy_decision = service.get_device_backoff_decision(
            healthy_device,
            now=start + 1,
        )
        snapshot = service.get_endpoint_snapshots([failed_device, healthy_device])[0]

        self.assertTrue(failed_decision.active)
        self.assertFalse(healthy_decision.active)
        self.assertEqual(snapshot["quarantined_device_count"], 1)

    def test_error_restores_conservative_policy(self) -> None:
        service = AdaptiveCommunicationService()
        device = _build_device()
        for _ in range(28):
            service.record_request_result(device, duration_ms=100, success=True)
            service.record_poll_result(device, _build_entry(success=True))

        service.record_poll_result(device, _build_entry(success=False))
        policy = service.resolve_poll_policy(
            device,
            configured_timeout_seconds=2.0,
            configured_retries=1,
        )

        self.assertEqual(policy.mode, "degraded")
        self.assertEqual(policy.timeout_seconds, 2.0)
        self.assertEqual(policy.retries, 1)
        self.assertEqual(policy.inter_request_delay_ms, 1000.0)

    def test_endpoint_with_marginal_reliability_stays_conservative(self) -> None:
        service = AdaptiveCommunicationService()
        device = _build_device()
        for index in range(40):
            service.record_request_result(device, duration_ms=100, success=True)
            service.record_poll_result(
                device,
                _build_entry(success=index != 10),
            )

        policy = service.resolve_poll_policy(
            device,
            configured_timeout_seconds=2.0,
            configured_retries=1,
        )

        self.assertEqual(policy.mode, "degraded")
        self.assertEqual(policy.timeout_seconds, 2.0)
        self.assertEqual(policy.retries, 1)
        self.assertEqual(policy.inter_request_delay_ms, 1000.0)

    def test_slow_successful_requests_keep_endpoint_conservative(self) -> None:
        service = AdaptiveCommunicationService()
        device = _build_device()
        for _ in range(28):
            service.record_request_result(device, duration_ms=1800, success=True)
            service.record_poll_result(device, _build_entry(success=True))

        policy = service.resolve_poll_policy(
            device,
            configured_timeout_seconds=2.0,
            configured_retries=1,
        )

        self.assertEqual(policy.mode, "degraded")
        self.assertEqual(policy.timeout_seconds, 2.0)
        self.assertEqual(policy.retries, 1)
        self.assertEqual(policy.inter_request_delay_ms, 1000.0)

    def test_request_error_keeps_successful_poll_endpoint_conservative(self) -> None:
        service = AdaptiveCommunicationService()
        device = _build_device()
        for index in range(40):
            service.record_request_result(
                device,
                duration_ms=100,
                success=index != 10,
            )
            service.record_poll_result(device, _build_entry(success=True))

        policy = service.resolve_poll_policy(
            device,
            configured_timeout_seconds=2.0,
            configured_retries=1,
        )

        self.assertEqual(policy.mode, "degraded")
        self.assertEqual(policy.inter_request_delay_ms, 1000.0)

    def test_device_backoff_is_reset_when_endpoint_changes(self) -> None:
        service = AdaptiveCommunicationService()
        device = _build_device()
        start = monotonic()
        service.record_poll_result(device, _build_entry(success=False), now=start)
        service.record_poll_result(device, _build_entry(success=False), now=start + 1)

        moved_device = device.model_copy(
            update={
                "connection_settings": {
                    **device.connection_settings,
                    "host": "192.168.2.109",
                }
            }
        )
        service.record_poll_result(
            moved_device,
            _build_entry(success=True),
            now=start + 2,
        )

        decision = service.get_device_backoff_decision(moved_device, now=start + 2)
        self.assertFalse(decision.active)
        self.assertEqual(decision.consecutive_failures, 0)


if __name__ == "__main__":
    unittest.main()
