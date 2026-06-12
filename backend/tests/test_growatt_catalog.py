import unittest

from app.catalog.growatt_catalog import (
    GROWATT_BRAND,
    GROWATT_MAX_1500_MODEL,
    GROWATT_MIN_MODEL,
    GROWATT_MIX_MODEL,
    GROWATT_MODELS,
    GROWATT_SPA_MODEL,
    GROWATT_TL3_MODEL,
    build_growatt_models,
)
from app.catalog.inverter_catalog import get_inverter_catalog
from app.services.active_power_limit_readback_resolver import (
    active_power_limit_readback_resolver,
)
from app.services.active_power_limit_resolver import active_power_limit_resolver
from app.services.inverter_io_service import inverter_io_service
from app.services.inverter_profile_resolver import inverter_profile_resolver


class GrowattCatalogTests(unittest.TestCase):
    def test_low_map_scaling_and_dashboard_points(self) -> None:
        model = self._find_model(GROWATT_TL3_MODEL, "modbus_rtu", "serial")
        telemetry = {point.key: point for point in model.telemetry_points}

        self.assertEqual(telemetry["status"].address, 0)
        self.assertTrue(telemetry["status"].protocol_meta["heartbeat"])
        self.assertEqual(telemetry["dc_power_kw"].address, 1)
        self.assertEqual(telemetry["dc_power_kw"].scale, 0.0001)
        self.assertEqual(telemetry["pv8_power_kw"].address, 33)
        self.assertEqual(telemetry["active_power_kw"].address, 35)
        self.assertEqual(telemetry["active_power_kw"].scale, 0.0001)
        self.assertEqual(telemetry["active_power_kw"].protocol_meta["summary_metric"], "power_kw")
        self.assertEqual(telemetry["mains_frequency_hz"].scale, 0.01)
        self.assertEqual(telemetry["daily_energy_kwh"].scale, 0.1)
        self.assertEqual(telemetry["temperature_c"].datatype, "int16")
        self.assertEqual(telemetry["temperature_c"].scale, 0.1)

    def test_high_map_uses_3000_register_family(self) -> None:
        model = self._find_model(GROWATT_MIN_MODEL, "modbus_tcp", "tcp")
        telemetry = {point.key: point for point in model.telemetry_points}

        self.assertEqual(model.defaults["test_register"], 3000)
        self.assertEqual(telemetry["status"].address, 3000)
        self.assertEqual(telemetry["dc_power_kw"].address, 3001)
        self.assertEqual(telemetry["active_power_kw"].address, 3023)
        self.assertEqual(telemetry["active_power_kw"].scale, 0.0001)
        self.assertEqual(telemetry["mains_frequency_hz"].address, 3025)
        self.assertEqual(telemetry["daily_energy_kwh"].address, 3049)
        self.assertEqual(telemetry["temperature_c"].address, 3093)

    def test_storage_and_spa_profiles_use_their_specific_blocks(self) -> None:
        mix = self._find_model(GROWATT_MIX_MODEL, "modbus_rtu", "serial")
        mix_telemetry = {point.key: point for point in mix.telemetry_points}
        self.assertEqual(mix_telemetry["battery_discharge_power_kw"].address, 1009)
        self.assertEqual(mix_telemetry["battery_discharge_power_kw"].scale, 0.0001)
        self.assertEqual(mix_telemetry["battery_soc_pct"].address, 1014)

        spa = self._find_model(GROWATT_SPA_MODEL, "modbus_rtu", "serial")
        spa_telemetry = {point.key: point for point in spa.telemetry_points}
        self.assertEqual(spa.defaults["test_register"], 2000)
        self.assertEqual(spa_telemetry["status"].address, 2000)
        self.assertEqual(spa_telemetry["active_power_kw"].address, 2035)
        self.assertEqual(spa_telemetry["temperature_c"].address, 2093)

    def test_active_power_command_is_safe_encoded_and_has_readback(self) -> None:
        model = self._find_model(GROWATT_MAX_1500_MODEL, "modbus_rtu", "serial")
        commands = {point.key: point for point in model.command_points}
        telemetry = {point.key: point for point in model.telemetry_points}

        command = commands["active_power_limit"]
        self.assertEqual(command.address, 3)
        self.assertEqual(command.register_type, "holding")
        self.assertEqual(command.unit, "%")
        self.assertEqual(command.protocol_meta["min_value"], 0)
        self.assertEqual(command.protocol_meta["max_value"], 100)
        self.assertTrue(command.protocol_meta["broadcast_supported"])
        self.assertEqual(inverter_io_service._encode_command_value(55, command), [55])
        self.assertEqual(telemetry["pv16_voltage_v"].address, 903)
        self.assertEqual(telemetry["pv16_power_kw"].address, 905)

        self.assertEqual(telemetry["active_power_limit_pct"].address, 3)
        self.assertEqual(telemetry["active_power_limit_pct"].protocol_meta["command"], "active_power_limit")
        self.assertIsNotNone(active_power_limit_resolver.resolve_for_write(model, 55))
        self.assertIsNotNone(active_power_limit_readback_resolver.resolve_point(model))

    def test_catalog_exports_all_families_and_rtu_over_tcp_can_resolve(self) -> None:
        catalog_models = {
            (model.brand, model.model, model.protocol, model.transport): model
            for model in get_inverter_catalog()
        }
        for model_name in GROWATT_MODELS:
            rtu_key = (GROWATT_BRAND, model_name, "modbus_rtu", "serial")
            tcp_key = (GROWATT_BRAND, model_name, "modbus_tcp", "tcp")
            self.assertIn(rtu_key, catalog_models)
            self.assertIn(tcp_key, catalog_models)
            self.assertEqual(catalog_models[rtu_key].defaults["inter_request_delay_ms"], 1000)
            self.assertFalse(catalog_models[rtu_key].defaults["adaptive_communication"])
            self.assertEqual(catalog_models[tcp_key].defaults["max_registers_per_request"], 125)
            self.assertEqual(catalog_models[rtu_key].catalog_meta["source_version"], "V1.24")
            self.assertFalse(catalog_models[rtu_key].catalog_meta["field_tested"])

        resolved = inverter_profile_resolver.find_catalog_model(
            brand=GROWATT_BRAND,
            model=GROWATT_MIN_MODEL,
            protocol="modbus_rtu",
            transport="tcp",
        )
        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.transport, "serial")

    def _find_model(self, model_name: str, protocol: str, transport: str):
        matches = [
            model
            for model in build_growatt_models(protocol, transport)
            if model.model == model_name
        ]
        self.assertEqual(len(matches), 1)
        return matches[0]


if __name__ == "__main__":
    unittest.main()
