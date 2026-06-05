import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.api import routes_fleet_control
from app.schemas.fleet_control_schemas import FleetSetpointRequest


class RoutesFleetControlTests(unittest.TestCase):
    def test_manual_setpoint_temporarily_disables_cci_until_dispatch_cycle_completes(self) -> None:
        config_state = SimpleNamespace(
            enabled=True,
            cci_enabled=True,
            host="0.0.0.0",
            port=15020,
            unit_id=1,
            cci_readback_enabled=True,
            cci_readback_range_percent=1.0,
            cci_readback_stable_seconds=3.0,
            cci_readback_active_power_only=False,
        )
        update_calls: list[dict[str, object]] = []
        dispatch_callback = None

        def get_config() -> SimpleNamespace:
            return config_state

        def update_config(**kwargs: object) -> SimpleNamespace:
            nonlocal config_state
            update_calls.append(dict(kwargs))
            config_state = SimpleNamespace(**kwargs)
            return config_state

        def request_dispatch(on_complete=None) -> None:  # noqa: ANN001
            nonlocal dispatch_callback
            dispatch_callback = on_complete

        with (
            patch(
                "app.api.routes_fleet_control.modbus_tcp_slave_config_service.get_config",
                side_effect=get_config,
            ),
            patch(
                "app.api.routes_fleet_control.modbus_tcp_slave_config_service.update_config",
                side_effect=update_config,
            ),
            patch(
                "app.api.routes_fleet_control.fleet_setpoint_service.set_active_power_limit_percent",
            ),
            patch(
                "app.api.routes_fleet_control.fleet_dispatch_service.request_dispatch",
                side_effect=request_dispatch,
            ),
            patch("app.api.routes_fleet_control.modbus_tcp_slave_service.refresh_registers"),
            patch(
                "app.api.routes_fleet_control._build_status_response",
                return_value="status",
            ),
        ):
            response = routes_fleet_control.set_fleet_setpoint(
                FleetSetpointRequest(value=42.0)
            )

        self.assertEqual(response, "status")
        self.assertEqual(len(update_calls), 1)
        self.assertFalse(update_calls[0]["cci_enabled"])
        self.assertIsNotNone(dispatch_callback)

        with (
            patch(
                "app.api.routes_fleet_control.modbus_tcp_slave_config_service.get_config",
                side_effect=get_config,
            ),
            patch(
                "app.api.routes_fleet_control.modbus_tcp_slave_config_service.update_config",
                side_effect=update_config,
            ),
            patch("app.api.routes_fleet_control.modbus_tcp_slave_service.refresh_registers"),
        ):
            dispatch_callback()

        self.assertEqual(len(update_calls), 2)
        self.assertTrue(update_calls[1]["cci_enabled"])

    def test_manual_setpoint_does_not_force_cci_on_if_it_was_already_disabled(self) -> None:
        config_state = SimpleNamespace(
            enabled=True,
            cci_enabled=False,
            host="0.0.0.0",
            port=15020,
            unit_id=1,
            cci_readback_enabled=True,
            cci_readback_range_percent=1.0,
            cci_readback_stable_seconds=3.0,
            cci_readback_active_power_only=False,
        )
        update_calls: list[dict[str, object]] = []
        dispatch_callback = None

        def get_config() -> SimpleNamespace:
            return config_state

        def update_config(**kwargs: object) -> SimpleNamespace:
            nonlocal config_state
            update_calls.append(dict(kwargs))
            config_state = SimpleNamespace(**kwargs)
            return config_state

        def request_dispatch(on_complete=None) -> None:  # noqa: ANN001
            nonlocal dispatch_callback
            dispatch_callback = on_complete

        with (
            patch(
                "app.api.routes_fleet_control.modbus_tcp_slave_config_service.get_config",
                side_effect=get_config,
            ),
            patch(
                "app.api.routes_fleet_control.modbus_tcp_slave_config_service.update_config",
                side_effect=update_config,
            ),
            patch(
                "app.api.routes_fleet_control.fleet_setpoint_service.set_active_power_limit_percent",
            ),
            patch(
                "app.api.routes_fleet_control.fleet_dispatch_service.request_dispatch",
                side_effect=request_dispatch,
            ),
            patch("app.api.routes_fleet_control.modbus_tcp_slave_service.refresh_registers"),
            patch(
                "app.api.routes_fleet_control._build_status_response",
                return_value="status",
            ),
        ):
            routes_fleet_control.set_fleet_setpoint(FleetSetpointRequest(value=18.0))

        self.assertEqual(update_calls, [])
        self.assertIsNotNone(dispatch_callback)

        with (
            patch(
                "app.api.routes_fleet_control.modbus_tcp_slave_config_service.get_config",
                side_effect=get_config,
            ),
            patch(
                "app.api.routes_fleet_control.modbus_tcp_slave_config_service.update_config",
                side_effect=update_config,
            ),
            patch("app.api.routes_fleet_control.modbus_tcp_slave_service.refresh_registers"),
        ):
            dispatch_callback()

        self.assertEqual(update_calls, [])


if __name__ == "__main__":
    unittest.main()
