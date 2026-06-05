import unittest

from app.catalog.goodwe_catalog import (
    GOODWE_BMS_MODEL,
    GOODWE_BRAND,
    GOODWE_GRID_TIED_MT_MODEL,
    GOODWE_GRID_TIED_STANDARD_MODEL,
    GOODWE_HYBRID_ET_MODEL,
    build_goodwe_models,
)
from app.catalog.inverter_catalog import get_inverter_catalog
from app.services.active_power_limit_readback_resolver import (
    active_power_limit_readback_resolver,
)
from app.services.active_power_limit_resolver import active_power_limit_resolver
from app.services.inverter_io_service import inverter_io_service
from app.services.inverter_profile_resolver import inverter_profile_resolver


class GoodWeCatalogTests(unittest.TestCase):
    def test_bms_profile_uses_goodwe_brand_and_manual_scaling(self) -> None:
        model = self._find_build_model(GOODWE_BMS_MODEL, "modbus_rtu", "serial")
        telemetry_points = {point.key: point for point in model.telemetry_points}

        self.assertEqual(model.brand, GOODWE_BRAND)
        self.assertEqual(telemetry_points["battery_current_a"].address, 0)
        self.assertEqual(telemetry_points["battery_current_a"].datatype, "int16")
        self.assertEqual(telemetry_points["battery_current_a"].scale, 0.01)
        self.assertEqual(telemetry_points["battery_voltage_v"].address, 1)
        self.assertEqual(telemetry_points["battery_voltage_v"].scale, 0.01)
        self.assertEqual(telemetry_points["soc_percent"].address, 2)
        self.assertEqual(telemetry_points["soc_percent"].datatype, "uint8_low")
        self.assertEqual(telemetry_points["cell_16_voltage_v"].address, 30)
        self.assertEqual(telemetry_points["cell_16_voltage_v"].scale, 0.001)
        self.assertEqual(telemetry_points["cumulative_discharging_kwh"].address, 42)
        self.assertEqual(telemetry_points["cumulative_discharging_kwh"].scale, 0.001)
        self.assertEqual(model.command_points, [])

        raw_values = {
            point.key: inverter_io_service._decode_register_value(
                registers=[0xFF38, 0x1481, 0x0064],
                start_address=0,
                point=point,
            )
            for point in [
                telemetry_points["battery_current_a"],
                telemetry_points["battery_voltage_v"],
                telemetry_points["soc_percent"],
            ]
        }
        scaled_values = inverter_io_service._apply_point_scaling(
            [
                telemetry_points["battery_current_a"],
                telemetry_points["battery_voltage_v"],
                telemetry_points["soc_percent"],
            ],
            raw_values,
        )

        self.assertAlmostEqual(scaled_values["battery_current_a"], -2.0)
        self.assertAlmostEqual(scaled_values["battery_voltage_v"], 52.49)
        self.assertEqual(scaled_values["soc_percent"], 100.0)

    def test_grid_tied_standard_register_map_and_active_power_command(self) -> None:
        model = self._find_build_model(GOODWE_GRID_TIED_STANDARD_MODEL, "modbus_rtu", "serial")
        telemetry_points = {point.key: point for point in model.telemetry_points}
        command_points = {point.key: point for point in model.command_points}

        self.assertEqual(telemetry_points["device_serial_number"].address, 512)
        self.assertEqual(telemetry_points["total_energy_kwh"].address, 546)
        self.assertEqual(telemetry_points["total_energy_kwh"].datatype, "uint32")
        self.assertEqual(telemetry_points["total_energy_kwh"].scale, 0.1)
        self.assertEqual(telemetry_points["dc_voltage_v"].address, 550)
        self.assertEqual(telemetry_points["mains_voltage_v"].address, 554)
        self.assertEqual(telemetry_points["active_power_kw"].address, 563)
        self.assertEqual(telemetry_points["active_power_kw"].scale, 0.001)
        self.assertEqual(telemetry_points["active_power_kw"].protocol_meta["summary_metric"], "power_kw")
        self.assertEqual(telemetry_points["status"].address, 564)
        self.assertEqual(telemetry_points["temperature_c"].address, 565)
        self.assertEqual(telemetry_points["daily_energy_kwh"].address, 566)

        self.assertEqual(command_points["active_power_limit"].address, 256)
        self.assertEqual(command_points["active_power_limit"].unit, "%")
        self.assertTrue(command_points["active_power_limit"].protocol_meta["force_multi_write"])
        self.assertEqual(
            inverter_io_service._encode_command_value(47.0, command_points["active_power_limit"]),
            [47],
        )

        write_resolution = active_power_limit_resolver.resolve_for_write(model, 47.0)
        self.assertIsNotNone(write_resolution)
        readback_resolution = active_power_limit_readback_resolver.resolve_point(model)
        self.assertIsNotNone(readback_resolution)
        assert readback_resolution is not None
        self.assertEqual(readback_resolution.telemetry_point.key, "active_power_limit_pct")

    def test_grid_tied_mt_register_map_uses_high_low_power_registers(self) -> None:
        model = self._find_build_model(GOODWE_GRID_TIED_MT_MODEL, "modbus_rtu", "serial")
        telemetry_points = {point.key: point for point in model.telemetry_points}

        self.assertEqual(telemetry_points["dc_voltage_v"].address, 768)
        self.assertEqual(telemetry_points["mains_frequency_hz"].address, 778)
        self.assertEqual(telemetry_points["status"].address, 782)
        self.assertEqual(telemetry_points["temperature_c"].address, 783)
        self.assertEqual(telemetry_points["total_energy_kwh"].address, 786)
        self.assertEqual(telemetry_points["daily_energy_kwh"].address, 800)
        self.assertEqual(telemetry_points["active_power_kw"].address, 850)
        self.assertEqual(telemetry_points["active_power_kw"].length, 2)
        self.assertEqual(telemetry_points["active_power_kw"].datatype, "uint32")
        self.assertEqual(telemetry_points["active_power_kw"].scale, 0.001)
        self.assertEqual(telemetry_points["pv4_current_a"].address, 858)

    def test_hybrid_et_family_available_on_rtu_and_modbus_tcp(self) -> None:
        rtu_model = self._find_build_model(GOODWE_HYBRID_ET_MODEL, "modbus_rtu", "serial")
        tcp_model = self._find_build_model(GOODWE_HYBRID_ET_MODEL, "modbus_tcp", "tcp")
        telemetry_points = {point.key: point for point in rtu_model.telemetry_points}

        self.assertEqual(rtu_model.defaults["slave_id"], 247)
        self.assertEqual(tcp_model.defaults["port"], 502)
        self.assertEqual(tcp_model.defaults["unit_id"], 247)
        self.assertEqual(telemetry_points["device_serial_number"].address, 35003)
        self.assertEqual(telemetry_points["dc_voltage_v"].address, 35103)
        self.assertEqual(telemetry_points["active_power_kw"].address, 35138)
        self.assertEqual(telemetry_points["active_power_kw"].datatype, "int16")
        self.assertEqual(telemetry_points["active_power_kw"].scale, 0.001)
        self.assertEqual(telemetry_points["daily_energy_kwh"].address, 35165)
        self.assertEqual(telemetry_points["total_energy_kwh"].address, 35167)
        self.assertEqual(telemetry_points["battery_voltage_v"].address, 35180)
        self.assertEqual(telemetry_points["soc_percent"].address, 37007)
        self.assertEqual(telemetry_points["max_cell_voltage_v"].scale, 0.001)

    def test_grid_tied_families_are_available_on_modbus_tcp_for_tcp_gateways(self) -> None:
        for model_name in (GOODWE_GRID_TIED_STANDARD_MODEL, GOODWE_GRID_TIED_MT_MODEL):
            model = self._find_build_model(model_name, "modbus_tcp", "tcp")
            command_points = {point.key: point for point in model.command_points}

            self.assertEqual(model.defaults["port"], 502)
            self.assertEqual(model.defaults["unit_id"], 247)
            self.assertEqual(model.defaults["test_register"], 512)
            self.assertEqual(command_points["active_power_limit"].address, 256)
            self.assertEqual(command_points["active_power_limit"].unit, "%")

    def test_catalog_exports_goodwe_models_and_rtu_over_tcp_can_resolve_grid_tied(self) -> None:
        catalog_models = {
            (model.brand, model.model, model.protocol, model.transport): model
            for model in get_inverter_catalog()
        }

        expected = {
            (GOODWE_BRAND, GOODWE_BMS_MODEL, "modbus_rtu", "serial"),
            (GOODWE_BRAND, GOODWE_GRID_TIED_STANDARD_MODEL, "modbus_rtu", "serial"),
            (GOODWE_BRAND, GOODWE_GRID_TIED_MT_MODEL, "modbus_rtu", "serial"),
            (GOODWE_BRAND, GOODWE_HYBRID_ET_MODEL, "modbus_rtu", "serial"),
            (GOODWE_BRAND, GOODWE_GRID_TIED_STANDARD_MODEL, "modbus_tcp", "tcp"),
            (GOODWE_BRAND, GOODWE_GRID_TIED_MT_MODEL, "modbus_tcp", "tcp"),
            (GOODWE_BRAND, GOODWE_HYBRID_ET_MODEL, "modbus_tcp", "tcp"),
        }
        for key in expected:
            self.assertIn(key, catalog_models)

        resolved = inverter_profile_resolver.find_catalog_model(
            brand=GOODWE_BRAND,
            model=GOODWE_GRID_TIED_STANDARD_MODEL,
            protocol="modbus_rtu",
            transport="tcp",
        )
        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.transport, "serial")

    def _find_build_model(self, model_name: str, protocol: str, transport: str):
        matches = [
            model
            for model in build_goodwe_models(protocol, transport)
            if model.model == model_name
        ]
        self.assertEqual(len(matches), 1)
        return matches[0]


if __name__ == "__main__":
    unittest.main()
