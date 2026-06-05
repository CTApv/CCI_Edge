import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.schemas.device_overview_schemas import (
    DeviceOverviewDiagnostics,
    DeviceOverviewMetrics,
    DeviceTelemetryPoint,
)
from app.models.inverter_model import InverterPoint
from app.services.fleet_dispatch_service import FleetDispatchService
from app.services.fleet_setpoint_service import FleetControlState
from app.services.inverter_io_service import CommandWriteResult


class _FakeFleetSetpointService:
    def __init__(self, state: FleetControlState) -> None:
        self.state = state
        self.control_states = []
        self.results = []
        self.eligible_device_count = 0

    def get_state(self) -> FleetControlState:
        return self.state

    def list_device_control_states(self):  # noqa: ANN001
        return list(self.control_states)

    def replace_device_control_states(self, states, *, eligible_device_count: int) -> None:  # noqa: ANN001
        self.control_states = list(states)
        self.eligible_device_count = eligible_device_count

    def record_dispatch_results(self, results, *, eligible_device_count: int):  # noqa: ANN001
        self.results = list(results)
        self.eligible_device_count = eligible_device_count
        return self.state

    def clear_device_results(self) -> None:
        self.results = []


class _FakeModbusTcpSlaveService:
    def __init__(self) -> None:
        self.refresh_calls = 0

    def refresh_registers(self) -> None:
        self.refresh_calls += 1


class FleetDispatchServiceTests(unittest.TestCase):
    def test_post_dispatch_callbacks_run_after_cycle(self) -> None:
        service = FleetDispatchService()
        callback_log: list[str] = []

        service.request_dispatch(on_complete=lambda: callback_log.append("done"))
        service._run_post_dispatch_callbacks()

        self.assertEqual(callback_log, ["done"])
        self.assertEqual(service._post_dispatch_callbacks, [])

    def test_request_dispatch_reserves_serial_priority_window(self) -> None:
        service = FleetDispatchService()
        serial_device = self._build_rtu_device("rtu-1", "INV 1")
        tcp_device = SimpleNamespace(
            device_id="tcp-1",
            name="TCP 1",
            brand="Brand",
            model="Model",
            protocol="modbus_tcp",
            transport="tcp",
            status="online",
            connection_settings={"host": "192.168.1.10", "port": 502, "unit_id": 1},
        )

        with (
            patch(
                "app.services.fleet_dispatch_service.device_service.list_devices",
                return_value=[serial_device, tcp_device],
            ),
            patch(
                "app.services.fleet_dispatch_service.connection_manager.request_modbus_rtu_priority",
            ) as priority_mock,
        ):
            service.request_dispatch()

        priority_mock.assert_called_once()
        self.assertEqual(priority_mock.call_args.args[0], "COM3")
        self.assertTrue(service._wake_event.is_set())

    def test_request_dispatch_reserves_rtu_over_tcp_priority_window(self) -> None:
        service = FleetDispatchService()
        gateway_device = self._build_rtu_over_tcp_device(
            "rtu-tcp-1",
            "INV TCP",
            host="192.168.100.20",
            port=4002,
            unit_id=10,
        )

        with (
            patch(
                "app.services.fleet_dispatch_service.device_service.list_devices",
                return_value=[gateway_device],
            ),
            patch(
                "app.services.fleet_dispatch_service.connection_manager.request_modbus_rtu_priority",
            ) as priority_mock,
        ):
            service.request_dispatch()

        priority_mock.assert_called_once_with(
            "tcp:192.168.100.20:4002",
            hold_seconds=4.0,
        )
        self.assertTrue(service._wake_event.is_set())

    def test_request_dispatch_reserves_priority_once_per_serial_line(self) -> None:
        service = FleetDispatchService()
        devices = [
            self._build_rtu_device("rtu-1", "INV 1"),
            self._build_rtu_device("rtu-2", "INV 2"),
            self._build_rtu_device("rtu-3", "INV 3", port="COM5"),
        ]

        with (
            patch(
                "app.services.fleet_dispatch_service.device_service.list_devices",
                return_value=devices,
            ),
            patch(
                "app.services.fleet_dispatch_service.connection_manager.request_modbus_rtu_priority",
            ) as priority_mock,
        ):
            service.request_dispatch()

        self.assertEqual(priority_mock.call_count, 2)
        self.assertEqual(
            {call.args[0] for call in priority_mock.call_args_list},
            {"COM3", "COM5"},
        )

    def test_tcp_priority_window_is_reserved_once_per_direct_endpoint_when_target_active(self) -> None:
        service = FleetDispatchService()
        state = FleetControlState(
            active_power_limit_percent=50.0,
            updated_at="2026-03-25T10:00:00+00:00",
            updated_source="api",
            last_dispatch_at=None,
            last_dispatch_ok_count=0,
            last_dispatch_error_count=0,
            last_dispatch_skipped_count=0,
            eligible_device_count=0,
            effective_source_priority=300,
            last_rejected_source=None,
            last_rejected_reason=None,
            last_rejected_at=None,
        )
        devices = [
            SimpleNamespace(
                device_id="tcp-1",
                name="TCP 1",
                brand="Brand",
                model="Model",
                protocol="modbus_tcp",
                transport="tcp",
                status="online",
                connection_settings={"host": "192.168.1.10", "port": 502, "unit_id": 1},
            ),
            SimpleNamespace(
                device_id="tcp-2",
                name="TCP 2",
                brand="Brand",
                model="Model",
                protocol="modbus_tcp",
                transport="tcp",
                status="online",
                connection_settings={"host": "192.168.1.10", "port": 502, "unit_id": 2},
            ),
            SimpleNamespace(
                device_id="tcp-3",
                name="TCP 3",
                brand="Brand",
                model="Model",
                protocol="modbus_tcp",
                transport="tcp",
                status="online",
                connection_settings={"host": "192.168.1.11", "port": 502, "unit_id": 1},
            ),
        ]

        with (
            patch("app.services.fleet_dispatch_service.fleet_setpoint_service.get_state", return_value=state),
            patch(
                "app.services.fleet_dispatch_service.device_service.list_devices",
                return_value=devices,
            ),
            patch(
                "app.services.fleet_dispatch_service.connection_manager.request_modbus_tcp_priority",
            ) as priority_mock,
        ):
            service._request_tcp_command_priority_window()

        self.assertEqual(priority_mock.call_count, 2)
        self.assertEqual(
            {call.args for call in priority_mock.call_args_list},
            {("192.168.1.10", 502), ("192.168.1.11", 502)},
        )

    def test_uses_single_rtu_broadcast_for_homogeneous_command_profile(self) -> None:
        state = FleetControlState(
            active_power_limit_percent=50.0,
            updated_at="2026-03-25T10:00:00+00:00",
            updated_source="api",
            last_dispatch_at=None,
            last_dispatch_ok_count=0,
            last_dispatch_error_count=0,
            last_dispatch_skipped_count=0,
            eligible_device_count=0,
            effective_source_priority=300,
            last_rejected_source=None,
            last_rejected_reason=None,
            last_rejected_at=None,
        )
        fake_setpoint_service = _FakeFleetSetpointService(state)
        fake_slave_service = _FakeModbusTcpSlaveService()
        devices = [
            self._build_rtu_device("rtu-1", "INV 1"),
            self._build_rtu_device("rtu-2", "INV 2"),
        ]
        command_point = InverterPoint(
            key="active_power_limit",
            label="Active power limit",
            kind="command",
            register_type="holding",
            address=1000,
            length=1,
            datatype="uint16",
            unit="%",
            writable=True,
        )
        resolution = SimpleNamespace(command_point=command_point, requested_value=50.0)
        write_result = CommandWriteResult(
            success=True,
            diagnostics={
                "stub_mode": False,
                "broadcast": True,
                "port": "COM3",
                "slave_id": 0,
            },
        )
        service = FleetDispatchService()

        with (
            patch("app.services.fleet_dispatch_service.fleet_setpoint_service", fake_setpoint_service),
            patch("app.services.fleet_dispatch_service.modbus_tcp_slave_service", fake_slave_service),
            patch("app.services.fleet_dispatch_service.device_service.list_devices", return_value=devices),
            patch(
                "app.services.fleet_dispatch_service.inverter_profile_resolver.resolve_for_device",
                return_value=SimpleNamespace(telemetry_points=[]),
            ),
            patch(
                "app.services.fleet_dispatch_service.active_power_limit_resolver.resolve_for_write",
                return_value=resolution,
            ),
            patch(
                "app.services.fleet_dispatch_service.inverter_io_service.build_command_broadcast_signature",
                return_value=("generic_modbus", "holding", 1000, (50,), False),
            ),
            patch(
                "app.services.fleet_dispatch_service.inverter_io_service.write_command_broadcast",
                return_value=write_result,
            ) as broadcast_mock,
            patch(
                "app.services.fleet_dispatch_service.command_service.send_active_power_limit_value",
            ) as send_mock,
            patch(
                "app.services.fleet_dispatch_service.command_service.record_active_power_limit_broadcast_success",
            ) as record_mock,
            patch.object(service, "_utc_now", return_value="2026-03-25T10:00:05+00:00"),
        ):
            service._dispatch_active_power_limit_if_needed()

        self.assertEqual(broadcast_mock.call_count, 1)
        self.assertEqual(send_mock.call_count, 0)
        self.assertEqual(record_mock.call_count, 2)
        self.assertEqual([item.control_state for item in fake_setpoint_service.control_states], ["aligned", "aligned"])
        self.assertTrue(all(result.diagnostics["broadcast"] for result in fake_setpoint_service.results))
        self.assertEqual(fake_setpoint_service.results[0].diagnostics["broadcast_candidate_count"], 2)

    def test_uses_single_rtu_over_tcp_broadcast_for_homogeneous_gateway_profile(self) -> None:
        state = FleetControlState(
            active_power_limit_percent=50.0,
            updated_at="2026-03-25T10:00:00+00:00",
            updated_source="api",
            last_dispatch_at=None,
            last_dispatch_ok_count=0,
            last_dispatch_error_count=0,
            last_dispatch_skipped_count=0,
            eligible_device_count=0,
            effective_source_priority=300,
            last_rejected_source=None,
            last_rejected_reason=None,
            last_rejected_at=None,
        )
        fake_setpoint_service = _FakeFleetSetpointService(state)
        fake_slave_service = _FakeModbusTcpSlaveService()
        devices = [
            self._build_rtu_over_tcp_device("rtu-tcp-1", "Gateway INV 1", unit_id=1),
            self._build_rtu_over_tcp_device("rtu-tcp-2", "Gateway INV 2", unit_id=2),
        ]
        command_point = InverterPoint(
            key="active_power_limit",
            label="Active power limit",
            kind="command",
            register_type="holding",
            address=0x1106,
            length=1,
            datatype="uint16",
            scale=0.1,
            unit="%",
            writable=True,
            protocol_meta={"force_multi_write": True},
        )
        resolution = SimpleNamespace(command_point=command_point, requested_value=50.0)
        write_result = CommandWriteResult(
            success=True,
            diagnostics={
                "stub_mode": False,
                "broadcast": True,
                "host": "192.168.1.20",
                "port": 502,
                "unit_id": 0,
                "gateway_mode": "rtu_over_tcp",
            },
        )
        service = FleetDispatchService()

        with (
            patch("app.services.fleet_dispatch_service.fleet_setpoint_service", fake_setpoint_service),
            patch("app.services.fleet_dispatch_service.modbus_tcp_slave_service", fake_slave_service),
            patch("app.services.fleet_dispatch_service.device_service.list_devices", return_value=devices),
            patch(
                "app.services.fleet_dispatch_service.inverter_profile_resolver.resolve_for_device",
                return_value=SimpleNamespace(telemetry_points=[]),
            ),
            patch(
                "app.services.fleet_dispatch_service.active_power_limit_resolver.resolve_for_write",
                return_value=resolution,
            ),
            patch(
                "app.services.fleet_dispatch_service.inverter_io_service.build_command_broadcast_signature",
                return_value=("generic_modbus", "holding", 0x1106, (500,), True),
            ),
            patch(
                "app.services.fleet_dispatch_service.inverter_io_service.write_command_broadcast",
                return_value=write_result,
            ) as broadcast_mock,
            patch(
                "app.services.fleet_dispatch_service.command_service.send_active_power_limit_value",
            ) as send_mock,
            patch(
                "app.services.fleet_dispatch_service.command_service.record_active_power_limit_broadcast_success",
            ) as record_mock,
            patch.object(service, "_utc_now", return_value="2026-03-25T10:00:05+00:00"),
        ):
            service._dispatch_active_power_limit_if_needed()

        self.assertEqual(broadcast_mock.call_count, 1)
        self.assertEqual(send_mock.call_count, 0)
        self.assertEqual(record_mock.call_count, 2)
        self.assertEqual([item.control_state for item in fake_setpoint_service.control_states], ["aligned", "aligned"])
        self.assertTrue(all(result.diagnostics["broadcast"] for result in fake_setpoint_service.results))
        self.assertEqual(
            fake_setpoint_service.results[0].diagnostics["broadcast_endpoint"],
            "192.168.1.20:502",
        )
        self.assertEqual(
            fake_setpoint_service.results[0].diagnostics["broadcast_endpoint_type"],
            "rtu_over_tcp",
        )

    def test_uses_single_modbus_tcp_gateway_broadcast_for_homogeneous_profile(self) -> None:
        state = FleetControlState(
            active_power_limit_percent=50.0,
            updated_at="2026-03-25T10:00:00+00:00",
            updated_source="api",
            last_dispatch_at=None,
            last_dispatch_ok_count=0,
            last_dispatch_error_count=0,
            last_dispatch_skipped_count=0,
            eligible_device_count=0,
            effective_source_priority=300,
            last_rejected_source=None,
            last_rejected_reason=None,
            last_rejected_at=None,
        )
        fake_setpoint_service = _FakeFleetSetpointService(state)
        fake_slave_service = _FakeModbusTcpSlaveService()
        devices = [
            self._build_modbus_tcp_gateway_device("tcp-gw-1", "Gateway TCP INV 1", unit_id=1),
            self._build_modbus_tcp_gateway_device("tcp-gw-2", "Gateway TCP INV 2", unit_id=2),
        ]
        command_point = InverterPoint(
            key="active_power_limit",
            label="Active power limit",
            kind="command",
            register_type="holding",
            address=0x1106,
            length=1,
            datatype="uint16",
            scale=0.1,
            unit="%",
            writable=True,
            protocol_meta={"force_multi_write": True},
        )
        resolution = SimpleNamespace(command_point=command_point, requested_value=50.0)
        write_result = CommandWriteResult(
            success=True,
            diagnostics={
                "stub_mode": False,
                "broadcast": True,
                "host": "192.168.1.20",
                "port": 502,
                "unit_id": 0,
                "gateway_mode": "modbus_tcp",
            },
        )
        service = FleetDispatchService()

        with (
            patch("app.services.fleet_dispatch_service.fleet_setpoint_service", fake_setpoint_service),
            patch("app.services.fleet_dispatch_service.modbus_tcp_slave_service", fake_slave_service),
            patch("app.services.fleet_dispatch_service.device_service.list_devices", return_value=devices),
            patch(
                "app.services.fleet_dispatch_service.inverter_profile_resolver.resolve_for_device",
                return_value=SimpleNamespace(telemetry_points=[]),
            ),
            patch(
                "app.services.fleet_dispatch_service.active_power_limit_resolver.resolve_for_write",
                return_value=resolution,
            ),
            patch(
                "app.services.fleet_dispatch_service.inverter_io_service.build_command_broadcast_signature",
                return_value=("generic_modbus", "holding", 0x1106, (500,), True),
            ),
            patch(
                "app.services.fleet_dispatch_service.inverter_io_service.write_command_broadcast",
                return_value=write_result,
            ) as broadcast_mock,
            patch(
                "app.services.fleet_dispatch_service.command_service.send_active_power_limit_value",
            ) as send_mock,
            patch(
                "app.services.fleet_dispatch_service.command_service.record_active_power_limit_broadcast_success",
            ) as record_mock,
            patch.object(service, "_utc_now", return_value="2026-03-25T10:00:05+00:00"),
        ):
            service._dispatch_active_power_limit_if_needed()

        self.assertEqual(broadcast_mock.call_count, 1)
        self.assertEqual(send_mock.call_count, 0)
        self.assertEqual(record_mock.call_count, 2)
        self.assertEqual([item.control_state for item in fake_setpoint_service.control_states], ["aligned", "aligned"])
        self.assertTrue(all(result.diagnostics["broadcast"] for result in fake_setpoint_service.results))
        self.assertEqual(
            fake_setpoint_service.results[0].diagnostics["broadcast_endpoint"],
            "192.168.1.20:502",
        )
        self.assertEqual(
            fake_setpoint_service.results[0].diagnostics["broadcast_endpoint_type"],
            "modbus_tcp_gateway",
        )

    def test_disables_rtu_broadcast_when_command_profiles_differ(self) -> None:
        state = FleetControlState(
            active_power_limit_percent=50.0,
            updated_at="2026-03-25T10:00:00+00:00",
            updated_source="api",
            last_dispatch_at=None,
            last_dispatch_ok_count=0,
            last_dispatch_error_count=0,
            last_dispatch_skipped_count=0,
            eligible_device_count=0,
            effective_source_priority=300,
            last_rejected_source=None,
            last_rejected_reason=None,
            last_rejected_at=None,
        )
        fake_setpoint_service = _FakeFleetSetpointService(state)
        fake_slave_service = _FakeModbusTcpSlaveService()
        devices = [
            self._build_rtu_device("rtu-1", "INV 1"),
            self._build_rtu_device("rtu-2", "INV 2"),
        ]
        command_point = InverterPoint(
            key="active_power_limit",
            label="Active power limit",
            kind="command",
            register_type="holding",
            address=1000,
            length=1,
            datatype="uint16",
            unit="%",
            writable=True,
        )
        resolution = SimpleNamespace(command_point=command_point, requested_value=50.0)
        send_response = SimpleNamespace(
            success=True,
            message="Modbus RTU command sent.",
            command="active_power_limit",
            diagnostics={
                "resolved_value": 50.0,
                "resolved_unit": "%",
                "requested_percent": 50.0,
            },
        )
        service = FleetDispatchService()

        with (
            patch("app.services.fleet_dispatch_service.fleet_setpoint_service", fake_setpoint_service),
            patch("app.services.fleet_dispatch_service.modbus_tcp_slave_service", fake_slave_service),
            patch("app.services.fleet_dispatch_service.device_service.list_devices", return_value=devices),
            patch(
                "app.services.fleet_dispatch_service.inverter_profile_resolver.resolve_for_device",
                return_value=SimpleNamespace(telemetry_points=[]),
            ),
            patch(
                "app.services.fleet_dispatch_service.active_power_limit_resolver.resolve_for_write",
                return_value=resolution,
            ),
            patch(
                "app.services.fleet_dispatch_service.inverter_io_service.build_command_broadcast_signature",
                side_effect=[
                    ("generic_modbus", "holding", 1000, (50,), False),
                    ("generic_modbus", "holding", 2000, (50,), False),
                ],
            ),
            patch(
                "app.services.fleet_dispatch_service.inverter_io_service.write_command_broadcast",
            ) as broadcast_mock,
            patch(
                "app.services.fleet_dispatch_service.command_service.send_active_power_limit_value",
                return_value=send_response,
            ) as send_mock,
        ):
            service._dispatch_active_power_limit_if_needed()

        self.assertEqual(broadcast_mock.call_count, 0)
        self.assertEqual(send_mock.call_count, 2)
        self.assertEqual([item.control_state for item in fake_setpoint_service.control_states], ["aligned", "aligned"])

    def test_disables_rtu_over_tcp_broadcast_when_gateway_command_profiles_differ(self) -> None:
        state = FleetControlState(
            active_power_limit_percent=50.0,
            updated_at="2026-03-25T10:00:00+00:00",
            updated_source="api",
            last_dispatch_at=None,
            last_dispatch_ok_count=0,
            last_dispatch_error_count=0,
            last_dispatch_skipped_count=0,
            eligible_device_count=0,
            effective_source_priority=300,
            last_rejected_source=None,
            last_rejected_reason=None,
            last_rejected_at=None,
        )
        fake_setpoint_service = _FakeFleetSetpointService(state)
        fake_slave_service = _FakeModbusTcpSlaveService()
        devices = [
            self._build_rtu_over_tcp_device("rtu-tcp-1", "Gateway INV 1", unit_id=1),
            self._build_rtu_over_tcp_device("rtu-tcp-2", "Gateway INV 2", unit_id=2),
        ]
        command_point = InverterPoint(
            key="active_power_limit",
            label="Active power limit",
            kind="command",
            register_type="holding",
            address=1000,
            length=1,
            datatype="uint16",
            unit="%",
            writable=True,
        )
        resolution = SimpleNamespace(command_point=command_point, requested_value=50.0)
        send_response = SimpleNamespace(
            success=True,
            message="Modbus RTU command sent.",
            command="active_power_limit",
            diagnostics={
                "resolved_value": 50.0,
                "resolved_unit": "%",
                "requested_percent": 50.0,
            },
        )
        service = FleetDispatchService()

        with (
            patch("app.services.fleet_dispatch_service.fleet_setpoint_service", fake_setpoint_service),
            patch("app.services.fleet_dispatch_service.modbus_tcp_slave_service", fake_slave_service),
            patch("app.services.fleet_dispatch_service.device_service.list_devices", return_value=devices),
            patch(
                "app.services.fleet_dispatch_service.inverter_profile_resolver.resolve_for_device",
                return_value=SimpleNamespace(telemetry_points=[]),
            ),
            patch(
                "app.services.fleet_dispatch_service.active_power_limit_resolver.resolve_for_write",
                return_value=resolution,
            ),
            patch(
                "app.services.fleet_dispatch_service.inverter_io_service.build_command_broadcast_signature",
                side_effect=[
                    ("generic_modbus", "holding", 1000, (50,), False),
                    ("generic_modbus", "holding", 2000, (50,), False),
                ],
            ),
            patch(
                "app.services.fleet_dispatch_service.inverter_io_service.write_command_broadcast",
            ) as broadcast_mock,
            patch(
                "app.services.fleet_dispatch_service.command_service.send_active_power_limit_value",
                return_value=send_response,
            ) as send_mock,
        ):
            service._dispatch_active_power_limit_if_needed()

        self.assertEqual(broadcast_mock.call_count, 0)
        self.assertEqual(send_mock.call_count, 2)
        self.assertEqual([item.control_state for item in fake_setpoint_service.control_states], ["aligned", "aligned"])

    def test_runs_due_cci_read_cycle_and_requeues_dispatch_when_new_values_wait(self) -> None:
        state = FleetControlState(
            active_power_limit_percent=48.0,
            updated_at="2026-03-25T10:00:00+00:00",
            updated_source="modbus_tcp_slave",
            last_dispatch_at="2026-03-25T10:00:01+00:00",
            last_dispatch_ok_count=0,
            last_dispatch_error_count=0,
            last_dispatch_skipped_count=0,
            eligible_device_count=0,
            effective_source_priority=1000,
            last_rejected_source=None,
            last_rejected_reason=None,
            last_rejected_at=None,
        )
        fake_setpoint_service = _FakeFleetSetpointService(state)
        fake_slave_service = SimpleNamespace(
            claim_due_cci_read_cycle=Mock(
                return_value=SimpleNamespace(
                    generation=7,
                    active_power_only=True,
                    reference_percent=48.0,
                )
            ),
            complete_cci_read_cycle=Mock(return_value=True),
            refresh_registers=Mock(),
            get_next_cci_read_due_in_seconds=Mock(return_value=None),
        )
        service = FleetDispatchService()
        devices = [self._build_rtu_device("rtu-1", "INV 1")]

        with (
            patch("app.services.fleet_dispatch_service.fleet_setpoint_service", fake_setpoint_service),
            patch("app.services.fleet_dispatch_service.modbus_tcp_slave_service", fake_slave_service),
            patch("app.services.fleet_dispatch_service.device_service.list_devices", return_value=devices),
            patch(
                "app.services.fleet_dispatch_service.polling_engine.run_on_demand_read_cycle",
                return_value={
                    "polled_device_count": 1,
                    "success_count": 1,
                    "error_count": 0,
                    "skipped_device_count": 0,
                    "endpoint_group_count": 1,
                },
            ) as read_cycle_mock,
            patch.object(service, "request_dispatch") as request_dispatch_mock,
        ):
            service._run_due_cci_read_cycle_if_needed()

        fake_slave_service.claim_due_cci_read_cycle.assert_called_once()
        read_cycle_mock.assert_called_once_with(devices, poll_kind="active_power")
        fake_slave_service.complete_cci_read_cycle.assert_called_once_with(7)
        fake_slave_service.refresh_registers.assert_called_once()
        request_dispatch_mock.assert_called_once()

    def test_due_cci_read_cycle_includes_rtu_over_tcp_devices(self) -> None:
        state = FleetControlState(
            active_power_limit_percent=48.0,
            updated_at="2026-03-25T10:00:00+00:00",
            updated_source="modbus_tcp_slave",
            last_dispatch_at="2026-03-25T10:00:01+00:00",
            last_dispatch_ok_count=0,
            last_dispatch_error_count=0,
            last_dispatch_skipped_count=0,
            eligible_device_count=0,
            effective_source_priority=1000,
            last_rejected_source=None,
            last_rejected_reason=None,
            last_rejected_at=None,
        )
        fake_setpoint_service = _FakeFleetSetpointService(state)
        fake_slave_service = SimpleNamespace(
            claim_due_cci_read_cycle=Mock(
                return_value=SimpleNamespace(
                    generation=7,
                    active_power_only=True,
                    reference_percent=48.0,
                )
            ),
            complete_cci_read_cycle=Mock(return_value=False),
            refresh_registers=Mock(),
            get_next_cci_read_due_in_seconds=Mock(return_value=None),
        )
        service = FleetDispatchService()
        serial_device = self._build_rtu_device("rtu-1", "INV 1")
        gateway_device = self._build_rtu_over_tcp_device("rtu-tcp-1", "INV 2")
        modbus_tcp_device = self._build_modbus_tcp_gateway_device("tcp-1", "INV 3")
        devices = [serial_device, gateway_device, modbus_tcp_device]

        with (
            patch("app.services.fleet_dispatch_service.fleet_setpoint_service", fake_setpoint_service),
            patch("app.services.fleet_dispatch_service.modbus_tcp_slave_service", fake_slave_service),
            patch("app.services.fleet_dispatch_service.device_service.list_devices", return_value=devices),
            patch(
                "app.services.fleet_dispatch_service.polling_engine.run_on_demand_read_cycle",
                return_value={
                    "polled_device_count": 3,
                    "success_count": 3,
                    "error_count": 0,
                    "skipped_device_count": 0,
                    "endpoint_group_count": 2,
                },
            ) as read_cycle_mock,
            patch.object(service, "request_dispatch") as request_dispatch_mock,
        ):
            service._run_due_cci_read_cycle_if_needed()

        read_cycle_mock.assert_called_once_with(
            [serial_device, gateway_device, modbus_tcp_device],
            poll_kind="active_power",
        )
        request_dispatch_mock.assert_not_called()

    def _build_rtu_device(self, device_id: str, name: str, *, port: str = "COM3") -> SimpleNamespace:
        return SimpleNamespace(
            device_id=device_id,
            name=name,
            brand="Brand",
            model="Model",
            protocol="modbus_rtu",
            transport="serial",
            status="online",
            connection_settings={
                "port": port,
                "slave_id": 1,
                "baud_rate": 9600,
                "byte_size": 8,
                "parity": "N",
                "stop_bits": 1,
                "timeout_seconds": 3.0,
                "retries": 0,
            },
        )

    def _build_rtu_over_tcp_device(
        self,
        device_id: str,
        name: str,
        *,
        host: str = "192.168.1.20",
        port: int = 502,
        unit_id: int = 1,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            device_id=device_id,
            name=name,
            brand="Brand",
            model="Model",
            protocol="modbus_rtu",
            transport="tcp",
            status="online",
            connection_settings={
                "host": host,
                "port": port,
                "unit_id": unit_id,
                "timeout_seconds": 3.0,
                "retries": 0,
            },
        )

    def _build_modbus_tcp_gateway_device(
        self,
        device_id: str,
        name: str,
        *,
        host: str = "192.168.1.20",
        port: int = 502,
        unit_id: int = 1,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            device_id=device_id,
            name=name,
            brand="Brand",
            model="Model",
            protocol="modbus_tcp",
            transport="tcp",
            status="online",
            connection_settings={
                "host": host,
                "port": port,
                "unit_id": unit_id,
                "timeout_seconds": 3.0,
                "retries": 0,
            },
        )

    def test_applies_backoff_after_aurora_command_error(self) -> None:
        state = FleetControlState(
            active_power_limit_percent=50.0,
            updated_at="2026-03-25T10:00:00+00:00",
            updated_source="api",
            last_dispatch_at=None,
            last_dispatch_ok_count=0,
            last_dispatch_error_count=0,
            last_dispatch_skipped_count=0,
            eligible_device_count=0,
            effective_source_priority=300,
            last_rejected_source=None,
            last_rejected_reason=None,
            last_rejected_at=None,
        )
        fake_setpoint_service = _FakeFleetSetpointService(state)
        fake_slave_service = _FakeModbusTcpSlaveService()
        device = SimpleNamespace(
            device_id="aurora-1",
            name="Aurora INV",
            brand="PowerOne",
            model="Aurora",
            protocol="aurora",
            transport="serial",
            status="online",
        )
        inverter_model = SimpleNamespace(telemetry_points=[])
        resolution = SimpleNamespace(
            command_point=SimpleNamespace(key="active_power_limit", unit="%", protocol_meta={}),
            requested_value=50.0,
        )
        error_response = SimpleNamespace(
            success=False,
            message="Aurora command failed.",
            command="active_power_limit",
            diagnostics={
                "stage": "write",
                "error": "Aurora TxState=51",
                "resolved_value": 50.0,
                "resolved_unit": "%",
                "requested_percent": 50.0,
                "aurora_op": 151,
                "aurora_tx_frame": "02 97 01 01 40 00 00 03 AA BB",
                "aurora_reply_frame": "33 00 00 00 00 00 CC DD",
                "aurora_reply_tx_state": 51,
            },
        )
        success_response = SimpleNamespace(
            success=True,
            message="Aurora command sent.",
            command="active_power_limit",
            diagnostics={
                "resolved_value": 50.0,
                "resolved_unit": "%",
                "requested_percent": 50.0,
            },
        )
        service = FleetDispatchService()

        with (
            patch("app.services.fleet_dispatch_service.fleet_setpoint_service", fake_setpoint_service),
            patch("app.services.fleet_dispatch_service.modbus_tcp_slave_service", fake_slave_service),
            patch(
                "app.services.fleet_dispatch_service.device_service.list_devices",
                return_value=[device],
            ),
            patch(
                "app.services.fleet_dispatch_service.inverter_profile_resolver.resolve_for_device",
                return_value=inverter_model,
            ),
            patch(
                "app.services.fleet_dispatch_service.active_power_limit_resolver.resolve_for_write",
                return_value=resolution,
            ),
            patch(
                "app.services.fleet_dispatch_service.command_service.send_active_power_limit_value",
                side_effect=[error_response, success_response],
            ) as send_mock,
            patch.object(
                service,
                "_now_monotonic",
                side_effect=[0.0, 5.0, 31.0],
            ),
            patch.object(
                service,
                "_utc_now",
                side_effect=[
                    "2026-03-25T10:00:05+00:00",
                    "2026-03-25T10:00:35+00:00",
                ],
            ),
        ):
            service._dispatch_active_power_limit_if_needed()
            self.assertEqual(send_mock.call_count, 1)
            self.assertEqual(fake_setpoint_service.control_states[0].control_state, "error")
            self.assertIn("Nuovo tentativo tra circa 30 s.", fake_setpoint_service.control_states[0].note)
            self.assertEqual(fake_setpoint_service.results[0].diagnostics["aurora_reply_tx_state"], 51)

            service._dispatch_active_power_limit_if_needed()
            self.assertEqual(send_mock.call_count, 1)
            self.assertEqual(fake_setpoint_service.control_states[0].control_state, "error")
            self.assertIn("Nuovo tentativo tra circa 25 s.", fake_setpoint_service.control_states[0].note)
            self.assertEqual(fake_setpoint_service.results[0].diagnostics["aurora_reply_tx_state"], 51)
            self.assertIn("aurora_tx_frame", fake_setpoint_service.results[0].diagnostics)

            service._dispatch_active_power_limit_if_needed()

        self.assertEqual(send_mock.call_count, 2)
        self.assertEqual(fake_setpoint_service.control_states[0].control_state, "aligned")
        self.assertEqual(fake_setpoint_service.results[0].outcome, "ok")

    def test_marks_ineligible_device_as_blocked_without_sending_command(self) -> None:
        state = FleetControlState(
            active_power_limit_percent=60.0,
            updated_at="2026-03-25T10:00:00+00:00",
            updated_source="api",
            last_dispatch_at=None,
            last_dispatch_ok_count=0,
            last_dispatch_error_count=0,
            last_dispatch_skipped_count=0,
            eligible_device_count=0,
            effective_source_priority=300,
            last_rejected_source=None,
            last_rejected_reason=None,
            last_rejected_at=None,
        )
        fake_setpoint_service = _FakeFleetSetpointService(state)
        fake_slave_service = _FakeModbusTcpSlaveService()
        device = SimpleNamespace(
            device_id="d1",
            name="INV-01",
            brand="Brand",
            model="Unsupported",
            protocol="modbus_tcp",
            transport="tcp",
            status="online",
        )
        service = FleetDispatchService()

        with (
            patch("app.services.fleet_dispatch_service.device_service.list_devices", return_value=[device]),
            patch("app.services.fleet_dispatch_service.fleet_setpoint_service", fake_setpoint_service),
            patch("app.services.fleet_dispatch_service.modbus_tcp_slave_service", fake_slave_service),
            patch("app.services.fleet_dispatch_service.inverter_profile_resolver.resolve_for_device", return_value=None),
            patch("app.services.fleet_dispatch_service.command_service.send_active_power_limit_value") as send_mock,
        ):
            service._dispatch_active_power_limit_if_needed()

        self.assertEqual(send_mock.call_count, 0)
        self.assertEqual(fake_setpoint_service.eligible_device_count, 0)
        self.assertEqual(len(fake_setpoint_service.control_states), 1)
        self.assertEqual(fake_setpoint_service.control_states[0].eligibility, "ineligible")
        self.assertEqual(fake_setpoint_service.control_states[0].control_state, "blocked")
        self.assertEqual(fake_setpoint_service.results[0].outcome, "blocked")
        self.assertEqual(fake_slave_service.refresh_calls, 1)

    def test_retries_same_target_after_device_returns_online(self) -> None:
        state = FleetControlState(
            active_power_limit_percent=55.0,
            updated_at="2026-03-25T10:00:00+00:00",
            updated_source="api",
            last_dispatch_at=None,
            last_dispatch_ok_count=0,
            last_dispatch_error_count=0,
            last_dispatch_skipped_count=0,
            eligible_device_count=0,
            effective_source_priority=300,
            last_rejected_source=None,
            last_rejected_reason=None,
            last_rejected_at=None,
        )
        fake_setpoint_service = _FakeFleetSetpointService(state)
        fake_slave_service = _FakeModbusTcpSlaveService()
        device = SimpleNamespace(
            device_id="d1",
            name="INV-01",
            brand="Brand",
            model="Model",
            protocol="modbus_tcp",
            transport="tcp",
            status="online",
        )
        resolution = SimpleNamespace(
            command_point=SimpleNamespace(key="active_power_limit", unit="%", protocol_meta={}),
            requested_value=55.0,
        )
        response = SimpleNamespace(
            success=True,
            message="Modbus TCP command sent.",
            command="active_power_limit",
            diagnostics={
                "resolved_value": 55.0,
                "resolved_unit": "%",
                "requested_percent": 55.0,
            },
        )
        service = FleetDispatchService()

        with (
            patch("app.services.fleet_dispatch_service.fleet_setpoint_service", fake_setpoint_service),
            patch("app.services.fleet_dispatch_service.modbus_tcp_slave_service", fake_slave_service),
            patch(
                "app.services.fleet_dispatch_service.device_service.list_devices",
                return_value=[device],
            ),
            patch(
                "app.services.fleet_dispatch_service.inverter_profile_resolver.resolve_for_device",
                return_value=SimpleNamespace(telemetry_points=[]),
            ),
            patch(
                "app.services.fleet_dispatch_service.active_power_limit_resolver.resolve_for_write",
                return_value=resolution,
            ),
            patch(
                "app.services.fleet_dispatch_service.command_service.send_active_power_limit_value",
                return_value=response,
            ) as send_mock,
        ):
            service._dispatch_active_power_limit_if_needed()

            self.assertEqual(send_mock.call_count, 1)
            self.assertEqual(fake_setpoint_service.control_states[0].control_state, "aligned")

            device.status = "offline"
            service._dispatch_active_power_limit_if_needed()
            self.assertEqual(send_mock.call_count, 1)
            self.assertEqual(fake_setpoint_service.control_states[0].control_state, "blocked")

            device.status = "online"
            service._dispatch_active_power_limit_if_needed()

        self.assertEqual(send_mock.call_count, 2)
        self.assertEqual(fake_setpoint_service.control_states[0].control_state, "aligned")
        self.assertEqual(fake_setpoint_service.results[0].outcome, "ok")
        self.assertEqual(fake_setpoint_service.eligible_device_count, 1)
        self.assertGreaterEqual(fake_slave_service.refresh_calls, 3)

    def test_confirms_target_from_fresh_telemetry_readback_without_resending(self) -> None:
        state = FleetControlState(
            active_power_limit_percent=42.0,
            updated_at="2026-03-25T10:00:00+00:00",
            updated_source="api",
            last_dispatch_at=None,
            last_dispatch_ok_count=0,
            last_dispatch_error_count=0,
            last_dispatch_skipped_count=0,
            eligible_device_count=0,
            effective_source_priority=300,
            last_rejected_source=None,
            last_rejected_reason=None,
            last_rejected_at=None,
        )
        fake_setpoint_service = _FakeFleetSetpointService(state)
        fake_slave_service = _FakeModbusTcpSlaveService()
        device = SimpleNamespace(
            device_id="d1",
            name="INV-01",
            brand="Brand",
            model="Model",
            protocol="modbus_tcp",
            transport="tcp",
            status="online",
        )
        inverter_model = SimpleNamespace(
            telemetry_points=[
                SimpleNamespace(
                    key="active_power_limit_pct",
                    label="Limite potenza attiva",
                    unit="%",
                    protocol_meta={"section": "Controllo potenza"},
                )
            ]
        )
        resolution = SimpleNamespace(
            command_point=SimpleNamespace(key="active_power_limit", unit="%", protocol_meta={}),
            requested_value=42.0,
        )
        response = SimpleNamespace(
            success=True,
            message="Modbus TCP command sent.",
            command="active_power_limit",
            diagnostics={
                "resolved_value": 42.0,
                "resolved_unit": "%",
                "requested_percent": 42.0,
            },
        )
        stale_entry = SimpleNamespace(
            metrics=DeviceOverviewMetrics(
                power_kw=0.0,
                daily_energy_kwh=0.0,
                total_energy_kwh=0.0,
                temperature_c=25.0,
            ),
            diagnostics=DeviceOverviewDiagnostics(
                last_poll_status="stub_mode=false; stage=ok",
                response_time_ms=120,
                retries=0,
                last_error=None,
            ),
            telemetry=[
                DeviceTelemetryPoint(
                    key="active_power_limit_pct",
                    label="Limite potenza attiva",
                    value=15.0,
                    raw_value=15.0,
                    display_value="15",
                    unit="%",
                    section="Controllo potenza",
                )
            ],
            timestamp="2026-03-25T09:59:00+00:00",
        )
        fresh_entry = SimpleNamespace(
            metrics=DeviceOverviewMetrics(
                power_kw=0.0,
                daily_energy_kwh=0.0,
                total_energy_kwh=0.0,
                temperature_c=25.0,
            ),
            diagnostics=DeviceOverviewDiagnostics(
                last_poll_status="stub_mode=false; stage=ok",
                response_time_ms=110,
                retries=0,
                last_error=None,
            ),
            telemetry=[
                DeviceTelemetryPoint(
                    key="active_power_limit_pct",
                    label="Limite potenza attiva",
                    value=42.0,
                    raw_value=42.0,
                    display_value="42",
                    unit="%",
                    section="Controllo potenza",
                )
            ],
            timestamp="2026-03-25T10:00:10+00:00",
        )
        service = FleetDispatchService()

        with (
            patch("app.services.fleet_dispatch_service.fleet_setpoint_service", fake_setpoint_service),
            patch("app.services.fleet_dispatch_service.modbus_tcp_slave_service", fake_slave_service),
            patch(
                "app.services.fleet_dispatch_service.device_service.list_devices",
                return_value=[device],
            ),
            patch(
                "app.services.fleet_dispatch_service.inverter_profile_resolver.resolve_for_device",
                return_value=inverter_model,
            ),
            patch(
                "app.services.fleet_dispatch_service.active_power_limit_resolver.resolve_for_write",
                return_value=resolution,
            ),
            patch(
                "app.services.fleet_dispatch_service.command_service.send_active_power_limit_value",
                return_value=response,
            ) as send_mock,
            patch(
                "app.services.fleet_dispatch_service.live_cache.get",
                side_effect=[stale_entry, fresh_entry],
            ),
            patch.object(
                service,
                "_utc_now",
                return_value="2026-03-25T10:00:05+00:00",
            ),
        ):
            service._dispatch_active_power_limit_if_needed()
            self.assertEqual(send_mock.call_count, 1)
            self.assertEqual(fake_setpoint_service.control_states[0].control_state, "aligned")
            self.assertFalse(fake_setpoint_service.control_states[0].telemetry_confirmed)

            service._dispatch_active_power_limit_if_needed()

        self.assertEqual(send_mock.call_count, 1)
        self.assertEqual(fake_setpoint_service.control_states[0].control_state, "aligned")
        self.assertTrue(fake_setpoint_service.control_states[0].telemetry_confirmed)
        self.assertEqual(fake_setpoint_service.control_states[0].last_applied_percent, 42.0)
        self.assertEqual(fake_setpoint_service.results[0].outcome, "ok")


if __name__ == "__main__":
    unittest.main()
