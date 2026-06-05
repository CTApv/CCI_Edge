import unittest

from app.catalog.inverter_catalog import get_inverter_catalog
from app.catalog.santerno_catalog import (
    SANTERNO_BRAND,
    SANTERNO_MODELS,
    build_santerno_models,
)
from app.services.active_power_limit_readback_resolver import (
    active_power_limit_readback_resolver,
)
from app.services.active_power_limit_resolver import active_power_limit_resolver
from app.services.inverter_io_service import inverter_io_service
from app.services.inverter_profile_resolver import inverter_profile_resolver


class SanternoCatalogTests(unittest.TestCase):
    def test_register_map_matches_sunway_tg_manual_for_dashboard_points(self) -> None:
        model = build_santerno_models("modbus_rtu", "serial")[0]
        telemetry_points = {point.key: point for point in model.telemetry_points}

        self.assertEqual(telemetry_points["product_id"].address, 476)
        self.assertEqual(telemetry_points["product_id"].datatype, "ascii_string")

        self.assertEqual(telemetry_points["mains_frequency_hz"].address, 1651)
        self.assertEqual(telemetry_points["mains_frequency_hz"].scale, 0.01)
        self.assertEqual(telemetry_points["mains_frequency_hz"].unit, "Hz")

        self.assertEqual(telemetry_points["power_factor"].address, 1652)
        self.assertEqual(telemetry_points["power_factor"].scale, 0.01)

        self.assertEqual(telemetry_points["active_power_kw"].address, 1653)
        self.assertEqual(telemetry_points["active_power_kw"].scale, 0.1)
        self.assertEqual(telemetry_points["active_power_kw"].unit, "kW")
        self.assertEqual(telemetry_points["active_power_kw"].protocol_meta["summary_metric"], "power_kw")

        self.assertEqual(telemetry_points["mains_voltage_v"].address, 1657)
        self.assertEqual(telemetry_points["mains_voltage_v"].scale, 0.1)

        self.assertEqual(telemetry_points["ac_current_a"].address, 1659)
        self.assertEqual(telemetry_points["ac_current_a"].scale, 0.1)

        self.assertEqual(telemetry_points["dc_voltage_v"].address, 1660)
        self.assertEqual(telemetry_points["dc_voltage_v"].scale, 0.1)

        self.assertEqual(telemetry_points["dc_current_a"].address, 1661)
        self.assertEqual(telemetry_points["dc_current_a"].scale, 0.1)

        self.assertEqual(telemetry_points["dc_power_kw"].address, 1662)
        self.assertEqual(telemetry_points["dc_power_kw"].scale, 0.1)

        self.assertEqual(telemetry_points["total_energy_kwh"].address, 1663)
        self.assertEqual(telemetry_points["total_energy_kwh"].datatype, "int32_swapped")
        self.assertEqual(telemetry_points["total_energy_kwh"].scale, 0.1)

        self.assertEqual(telemetry_points["status"].address, 1739)
        self.assertEqual(telemetry_points["status"].protocol_meta["summary_metric"], "status")

        self.assertEqual(telemetry_points["temperature_cpu_c"].address, 1712)
        self.assertEqual(telemetry_points["temperature_cpu_c"].scale, 0.1)
        self.assertEqual(telemetry_points["temperature_cpu_c"].protocol_meta["summary_metric"], "temperature_c")

    def test_grid_power_control_commands_use_manual_addresses_and_multiple_write(self) -> None:
        model = build_santerno_models("modbus_rtu", "serial")[0]
        command_points = {point.key: point for point in model.command_points}

        self.assertEqual(command_points["grid_power_control_mode"].address, 900)
        self.assertEqual(command_points["active_power_limit"].address, 918)
        self.assertEqual(command_points["active_power_limit"].scale, 0.01)
        self.assertEqual(command_points["active_power_limit"].unit, "%")
        self.assertTrue(command_points["active_power_limit"].protocol_meta["force_multi_write"])
        self.assertEqual(command_points["active_power_limit"].protocol_meta["modbus_write_function"], "0x10")

        self.assertEqual(
            inverter_io_service._encode_command_value(55.25, command_points["active_power_limit"]),
            [5525],
        )

    def test_active_power_limit_resolution_and_readback_are_available(self) -> None:
        model = build_santerno_models("modbus_rtu", "serial")[0]

        write_resolution = active_power_limit_resolver.resolve_for_write(model, 47.5)
        self.assertIsNotNone(write_resolution)
        assert write_resolution is not None
        self.assertEqual(write_resolution.command_point.key, "active_power_limit")
        self.assertEqual(write_resolution.requested_value, 47.5)

        readback_resolution = active_power_limit_readback_resolver.resolve_point(model)
        self.assertIsNotNone(readback_resolution)
        assert readback_resolution is not None
        self.assertEqual(readback_resolution.telemetry_point.key, "active_power_limit_pct")
        self.assertEqual(readback_resolution.telemetry_point.address, 3228)

    def test_catalog_exports_sunway_tg_family_and_rtu_over_tcp_can_resolve_it(self) -> None:
        catalog_models = {
            (model.brand, model.model, model.protocol, model.transport): model
            for model in get_inverter_catalog()
        }

        for model_name in SANTERNO_MODELS:
            key = (SANTERNO_BRAND, model_name, "modbus_rtu", "serial")
            self.assertIn(key, catalog_models)
            self.assertEqual(catalog_models[key].defaults["baud_rate"], 38400)
            self.assertEqual(catalog_models[key].defaults["stop_bits"], 2)
            self.assertEqual(catalog_models[key].defaults["test_register"], 476)

            resolved = inverter_profile_resolver.find_catalog_model(
                brand=SANTERNO_BRAND,
                model=model_name,
                protocol="modbus_rtu",
                transport="tcp",
            )
            self.assertIsNotNone(resolved)
            assert resolved is not None
            self.assertEqual(resolved.transport, "serial")


if __name__ == "__main__":
    unittest.main()
