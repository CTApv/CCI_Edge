import unittest

from app.catalog.inverter_catalog import get_inverter_catalog
from app.catalog.sungrow_catalog import (
    SUNGROW_BRAND,
    SUNGROW_MODELS,
    build_sungrow_models,
    holding_addr,
    input_addr,
)
from app.services.active_power_limit_readback_resolver import (
    active_power_limit_readback_resolver,
)
from app.services.active_power_limit_resolver import active_power_limit_resolver
from app.services.inverter_io_service import inverter_io_service
from app.services.inverter_profile_resolver import inverter_profile_resolver


class SungrowCatalogTests(unittest.TestCase):
    def test_register_map_uses_manual_minus_one_modbus_addresses(self) -> None:
        model = build_sungrow_models("modbus_rtu", "serial")[0]
        telemetry_points = {point.key: point for point in model.telemetry_points}

        self.assertEqual(telemetry_points["device_type_code"].address, input_addr(5000))
        self.assertEqual(telemetry_points["device_type_code"].protocol_meta["manual_register"], 5000)
        self.assertEqual(telemetry_points["device_type_code"].datatype, "uint16")

        self.assertEqual(telemetry_points["daily_energy_kwh"].address, input_addr(5003))
        self.assertEqual(telemetry_points["daily_energy_kwh"].scale, 0.1)
        self.assertEqual(telemetry_points["daily_energy_kwh"].protocol_meta["summary_metric"], "daily_energy_kwh")

        self.assertEqual(telemetry_points["total_energy_kwh"].address, input_addr(5004))
        self.assertEqual(telemetry_points["total_energy_kwh"].length, 2)
        self.assertEqual(telemetry_points["total_energy_kwh"].datatype, "uint32")
        self.assertEqual(telemetry_points["total_energy_kwh"].unit, "kWh")

        self.assertEqual(telemetry_points["temperature_c"].address, input_addr(5008))
        self.assertEqual(telemetry_points["temperature_c"].scale, 0.1)
        self.assertEqual(telemetry_points["temperature_c"].protocol_meta["summary_metric"], "temperature_c")

        self.assertEqual(telemetry_points["dc_voltage_v"].address, input_addr(5011))
        self.assertEqual(telemetry_points["dc_voltage_v"].scale, 0.1)
        self.assertEqual(telemetry_points["dc_current_a"].address, input_addr(5012))
        self.assertEqual(telemetry_points["dc_current_a"].scale, 0.1)
        self.assertEqual(telemetry_points["dc_power_kw"].address, input_addr(5017))
        self.assertEqual(telemetry_points["dc_power_kw"].scale, 0.001)

        self.assertEqual(telemetry_points["mains_voltage_v"].address, input_addr(5019))
        self.assertEqual(telemetry_points["ac_current_a"].address, input_addr(5022))
        self.assertEqual(telemetry_points["active_power_kw"].address, input_addr(5031))
        self.assertEqual(telemetry_points["active_power_kw"].scale, 0.001)
        self.assertEqual(telemetry_points["active_power_kw"].protocol_meta["summary_metric"], "power_kw")
        self.assertEqual(telemetry_points["mains_frequency_hz"].address, input_addr(5036))
        self.assertEqual(telemetry_points["mains_frequency_hz"].scale, 0.1)
        self.assertEqual(telemetry_points["status"].address, input_addr(5038))
        self.assertEqual(telemetry_points["status"].protocol_meta["summary_metric"], "status")

    def test_power_limit_commands_use_holding_registers_and_scaling(self) -> None:
        model = build_sungrow_models("modbus_rtu", "serial")[0]
        telemetry_points = {point.key: point for point in model.telemetry_points}
        command_points = {point.key: point for point in model.command_points}

        self.assertEqual(telemetry_points["active_power_limit_switch"].register_type, "holding")
        self.assertEqual(telemetry_points["active_power_limit_switch"].address, holding_addr(5007))
        self.assertEqual(telemetry_points["active_power_limit_pct"].address, holding_addr(5008))
        self.assertEqual(telemetry_points["active_power_limit_pct"].scale, 0.1)
        self.assertEqual(telemetry_points["active_power_limit_pct"].protocol_meta["command"], "active_power_limit")

        self.assertEqual(command_points["active_power_limit_enable"].address, holding_addr(5007))
        self.assertEqual(command_points["active_power_limit"].address, holding_addr(5008))
        self.assertEqual(command_points["active_power_limit"].scale, 0.1)
        self.assertEqual(command_points["active_power_limit"].unit, "%")
        self.assertTrue(command_points["active_power_limit"].protocol_meta["force_multi_write"])
        self.assertEqual(command_points["active_power_limit"].protocol_meta["modbus_write_function"], "0x10")
        self.assertEqual(
            inverter_io_service._encode_command_value(55.5, command_points["active_power_limit"]),
            [555],
        )

        write_resolution = active_power_limit_resolver.resolve_for_write(model, 55.5)
        self.assertIsNotNone(write_resolution)
        assert write_resolution is not None
        self.assertEqual(write_resolution.command_point.key, "active_power_limit")

        readback_resolution = active_power_limit_readback_resolver.resolve_point(model)
        self.assertIsNotNone(readback_resolution)
        assert readback_resolution is not None
        self.assertEqual(readback_resolution.telemetry_point.key, "active_power_limit_pct")

    def test_string_currents_are_optional_combiner_block(self) -> None:
        model = build_sungrow_models("modbus_rtu", "serial")[0]
        telemetry_points = {point.key: point for point in model.telemetry_points}

        self.assertEqual(telemetry_points["string_01_current_a"].address, input_addr(7013))
        self.assertEqual(telemetry_points["string_01_current_a"].scale, 0.01)
        self.assertEqual(telemetry_points["string_18_current_a"].address, input_addr(7030))
        self.assertTrue(telemetry_points["string_18_current_a"].protocol_meta["optional_block"])

    def test_catalog_exports_sungrow_family_and_rtu_over_tcp_can_resolve_it(self) -> None:
        catalog_models = {
            (model.brand, model.model, model.protocol, model.transport): model
            for model in get_inverter_catalog()
        }

        for model_name in SUNGROW_MODELS:
            rtu_key = (SUNGROW_BRAND, model_name, "modbus_rtu", "serial")
            tcp_key = (SUNGROW_BRAND, model_name, "modbus_tcp", "tcp")
            self.assertIn(rtu_key, catalog_models)
            self.assertIn(tcp_key, catalog_models)
            self.assertEqual(catalog_models[rtu_key].defaults["test_register"], input_addr(5000))
            self.assertEqual(catalog_models[rtu_key].defaults["test_function"], "input")
            self.assertEqual(catalog_models[tcp_key].defaults["test_register"], input_addr(5000))
            self.assertEqual(catalog_models[tcp_key].defaults["test_function"], "input")
            self.assertEqual(catalog_models[tcp_key].defaults["port"], 502)

            resolved = inverter_profile_resolver.find_catalog_model(
                brand=SUNGROW_BRAND,
                model=model_name,
                protocol="modbus_rtu",
                transport="tcp",
            )
            self.assertIsNotNone(resolved)
            assert resolved is not None
            self.assertEqual(resolved.transport, "serial")


if __name__ == "__main__":
    unittest.main()
