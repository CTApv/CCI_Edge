import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.config import settings
from app.services.fleet_setpoint_service import (
    FleetDeviceControlState,
    FleetDeviceDispatchResult,
    FleetSetpointService,
)


class FleetSetpointServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._original_database_path = settings.database_path
        settings.database_path = Path(self._temp_dir.name) / "fleet-control-test.db"
        self._runtime_event_patcher = patch(
            "app.services.fleet_setpoint_service.runtime_event_service.record_event"
        )
        self._runtime_event_patcher.start()

    def tearDown(self) -> None:
        self._runtime_event_patcher.stop()
        settings.database_path = self._original_database_path
        self._temp_dir.cleanup()

    def test_modbus_slave_overrides_api_target(self) -> None:
        service = FleetSetpointService()

        initial_state = service.set_active_power_limit_percent(72.5, source="api")
        overridden_state = service.set_active_power_limit_percent(41.0, source="modbus_tcp_slave")

        self.assertEqual(initial_state.active_power_limit_percent, 72.5)
        self.assertEqual(overridden_state.active_power_limit_percent, 41.0)
        self.assertEqual(overridden_state.updated_source, "modbus_tcp_slave")
        self.assertEqual(overridden_state.effective_source_priority, 1000)
        self.assertIsNone(overridden_state.last_rejected_source)
        self.assertIsNone(overridden_state.last_rejected_reason)

    def test_rejects_api_target_when_modbus_slave_target_is_active(self) -> None:
        service = FleetSetpointService()

        initial_state = service.set_active_power_limit_percent(41.0, source="modbus_tcp_slave")
        rejected_state = service.set_active_power_limit_percent(72.5, source="api")

        self.assertEqual(initial_state.active_power_limit_percent, 41.0)
        self.assertEqual(rejected_state.active_power_limit_percent, 41.0)
        self.assertEqual(rejected_state.updated_source, "modbus_tcp_slave")
        self.assertEqual(rejected_state.effective_source_priority, 1000)
        self.assertEqual(rejected_state.last_rejected_source, "api")
        self.assertIsNotNone(rejected_state.last_rejected_reason)
        self.assertIn("priorita inferiore", rejected_state.last_rejected_reason or "")

    def test_api_target_can_override_modbus_target_when_cci_is_disabled(self) -> None:
        service = FleetSetpointService()

        with patch(
            "app.services.fleet_setpoint_service.modbus_tcp_slave_config_service.get_config",
            return_value=SimpleNamespace(
                enabled=True,
                cci_enabled=False,
                host="0.0.0.0",
                port=15020,
                unit_id=1,
                cci_readback_enabled=True,
                cci_readback_range_percent=1.0,
                cci_readback_stable_seconds=3.0,
                cci_readback_active_power_only=False,
            ),
        ):
            initial_state = service.set_active_power_limit_percent(41.0, source="modbus_tcp_slave")
            overridden_state = service.set_active_power_limit_percent(72.5, source="api")

        self.assertEqual(initial_state.active_power_limit_percent, 41.0)
        self.assertEqual(overridden_state.active_power_limit_percent, 72.5)
        self.assertEqual(overridden_state.updated_source, "api")
        self.assertIsNone(overridden_state.last_rejected_source)
        self.assertIsNone(overridden_state.last_rejected_reason)

    def test_same_source_same_target_does_not_refresh_timestamp(self) -> None:
        service = FleetSetpointService()

        initial_state = service.set_active_power_limit_percent(41.0, source="modbus_tcp_slave")
        repeated_state = service.set_active_power_limit_percent(41.0, source="modbus_tcp_slave")

        self.assertEqual(repeated_state.active_power_limit_percent, 41.0)
        self.assertEqual(repeated_state.updated_source, "modbus_tcp_slave")
        self.assertEqual(repeated_state.updated_at, initial_state.updated_at)

    def test_replace_device_control_states_updates_eligible_count(self) -> None:
        service = FleetSetpointService()
        service.replace_device_control_states(
            [
                FleetDeviceControlState(
                    device_id="a",
                    name="A",
                    brand="Brand",
                    model="Model A",
                    protocol="modbus_tcp",
                    transport="tcp",
                    device_status="online",
                    eligibility="eligible",
                    eligibility_reason=None,
                    control_state="aligned",
                    desired_percent=55.0,
                    desired_updated_at="2026-03-25T10:00:00+00:00",
                    desired_source="api",
                    desired_source_priority=300,
                    last_sent_percent=55.0,
                    last_applied_percent=55.0,
                    telemetry_confirmed=False,
                    last_command="active_power_limit",
                    last_resolved_value=55.0,
                    last_resolved_unit="%",
                    last_dispatch_outcome="ok",
                    last_dispatch_at="2026-03-25T10:00:05+00:00",
                    last_error=None,
                    note="Allineato.",
                ),
                FleetDeviceControlState(
                    device_id="b",
                    name="B",
                    brand="Brand",
                    model="Model B",
                    protocol="modbus_tcp",
                    transport="tcp",
                    device_status="online",
                    eligibility="ineligible",
                    eligibility_reason="Setpoint non supportato.",
                    control_state="blocked",
                    desired_percent=55.0,
                    desired_updated_at="2026-03-25T10:00:00+00:00",
                    desired_source="api",
                    desired_source_priority=300,
                    last_sent_percent=None,
                    last_applied_percent=None,
                    telemetry_confirmed=False,
                    last_command=None,
                    last_resolved_value=None,
                    last_resolved_unit=None,
                    last_dispatch_outcome="blocked",
                    last_dispatch_at=None,
                    last_error="Setpoint non supportato.",
                    note="Setpoint non supportato.",
                ),
            ],
            eligible_device_count=1,
        )

        state = service.get_state()
        stored_states = service.list_device_control_states()

        self.assertEqual(state.eligible_device_count, 1)
        self.assertEqual(len(stored_states), 2)
        self.assertEqual(stored_states[0].device_id, "b")
        self.assertEqual(stored_states[1].device_id, "a")

    def test_backoff_only_results_do_not_refresh_global_dispatch_timestamp(self) -> None:
        service = FleetSetpointService()
        service.set_active_power_limit_percent(50.0, source="api")
        first_state = service.record_dispatch_results(
            [
                FleetDeviceDispatchResult(
                    device_id="a",
                    name="A",
                    brand="Brand",
                    model="Model",
                    protocol="modbus_rtu",
                    transport="tcp",
                    outcome="error",
                    success=False,
                    message="Errore comando.",
                    command="active_power_limit",
                    diagnostics={"error": "errore"},
                    timestamp="2026-03-25T10:00:05+00:00",
                )
            ],
            eligible_device_count=1,
        )

        second_state = service.record_dispatch_results(
            [
                FleetDeviceDispatchResult(
                    device_id="a",
                    name="A",
                    brand="Brand",
                    model="Model",
                    protocol="modbus_rtu",
                    transport="tcp",
                    outcome="error",
                    success=False,
                    message="Backoff attivo.",
                    command="active_power_limit",
                    diagnostics={"backoff_active": True, "retry_after_seconds": 25},
                    timestamp="2026-03-25T10:00:30+00:00",
                )
            ],
            eligible_device_count=1,
        )

        self.assertEqual(first_state.last_dispatch_at, "2026-03-25T10:00:05+00:00")
        self.assertEqual(second_state.last_dispatch_at, "2026-03-25T10:00:05+00:00")


if __name__ == "__main__":
    unittest.main()
