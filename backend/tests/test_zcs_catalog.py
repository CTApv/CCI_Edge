import unittest

from app.catalog.inverter_catalog import get_inverter_catalog
from app.catalog.zcs_catalog import ZCS_BRAND, ZCS_MODEL, build_zcs_models
from app.services.active_power_limit_readback_resolver import (
    active_power_limit_readback_resolver,
)
from app.services.active_power_limit_resolver import active_power_limit_resolver


class ZcsCatalogTests(unittest.TestCase):
    def test_v3_register_map_matches_manual_for_key_points(self) -> None:
        model = build_zcs_models("modbus_rtu", "serial")[0]
        telemetry_points = {point.key: point for point in model.telemetry_points}
        command_points = {point.key: point for point in model.command_points}

        self.assertEqual(telemetry_points["status"].address, 0x0404)
        self.assertEqual(telemetry_points["status"].register_type, "holding")
        self.assertEqual(telemetry_points["status"].protocol_meta["summary_metric"], "status")

        self.assertEqual(telemetry_points["active_power_kw"].address, 0x0485)
        self.assertEqual(telemetry_points["active_power_kw"].scale, 0.01)
        self.assertEqual(telemetry_points["active_power_kw"].unit, "kW")
        self.assertEqual(telemetry_points["active_power_kw"].protocol_meta["summary_metric"], "power_kw")

        self.assertEqual(telemetry_points["reactive_power_kvar"].address, 0x0486)
        self.assertEqual(telemetry_points["reactive_power_kvar"].scale, 0.01)

        self.assertEqual(telemetry_points["power_control_register"].address, 0x1105)
        self.assertEqual(telemetry_points["active_power_limit_pct"].address, 0x1106)
        self.assertEqual(telemetry_points["active_power_limit_pct"].protocol_meta["command"], "active_power_limit")
        self.assertEqual(telemetry_points["reactive_power_setpoint_percent"].address, 0x1108)

        self.assertEqual(command_points["active_power_limit"].address, 0x1106)
        self.assertEqual(command_points["active_power_limit"].scale, 0.1)
        self.assertEqual(command_points["active_power_limit"].unit, "%")
        self.assertTrue(command_points["active_power_limit"].protocol_meta["force_multi_write"])
        self.assertEqual(command_points["active_power_limit"].protocol_meta["modbus_write_function"], "0x10")
        self.assertEqual(command_points["reactive_power_target_percent"].address, 0x1108)
        self.assertTrue(command_points["reactive_power_target_percent"].protocol_meta["force_multi_write"])

    def test_active_power_limit_resolution_and_readback_are_available(self) -> None:
        model = build_zcs_models("modbus_tcp", "tcp")[0]

        write_resolution = active_power_limit_resolver.resolve_for_write(model, 54.3)
        self.assertIsNotNone(write_resolution)
        assert write_resolution is not None
        self.assertEqual(write_resolution.command_point.key, "active_power_limit")
        self.assertEqual(write_resolution.command_point.address, 0x1106)
        self.assertEqual(write_resolution.requested_value, 54.3)

        readback_resolution = active_power_limit_readback_resolver.resolve_point(model)
        self.assertIsNotNone(readback_resolution)
        assert readback_resolution is not None
        self.assertEqual(readback_resolution.telemetry_point.key, "active_power_limit_pct")
        self.assertEqual(readback_resolution.telemetry_point.address, 0x1106)

    def test_catalog_exports_both_rtu_and_tcp_profiles(self) -> None:
        catalog_models = {
            (model.brand, model.model, model.protocol, model.transport): model
            for model in get_inverter_catalog()
        }

        rtu_key = (ZCS_BRAND, ZCS_MODEL, "modbus_rtu", "serial")
        tcp_key = (ZCS_BRAND, ZCS_MODEL, "modbus_tcp", "tcp")

        self.assertIn(rtu_key, catalog_models)
        self.assertIn(tcp_key, catalog_models)
        self.assertEqual(catalog_models[rtu_key].defaults["test_register"], 0x0404)
        self.assertEqual(catalog_models[tcp_key].defaults["test_function"], "holding")


if __name__ == "__main__":
    unittest.main()
