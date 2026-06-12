import unittest

from app.catalog.inverter_catalog import get_inverter_catalog
from app.catalog.solax_catalog import (
    SOLAX_AELIO_MODEL,
    SOLAX_BRAND,
    SOLAX_DATAHUB_MODEL,
    SOLAX_DIRECT_MODELS,
    SOLAX_EMS1000_MODEL,
    SOLAX_GRAND_MODEL,
    SOLAX_MEGA_FORTH_MODEL,
    SOLAX_MIC_PRO_MODEL,
    SOLAX_ULTRA_MODEL,
    build_solax_models,
)
from app.services.active_power_limit_readback_resolver import (
    active_power_limit_readback_resolver,
)
from app.services.active_power_limit_resolver import active_power_limit_resolver
from app.services.inverter_io_service import inverter_io_service
from app.services.inverter_profile_resolver import inverter_profile_resolver


class SolaxCatalogTests(unittest.TestCase):
    def test_mic_pro_dashboard_map_scaling_and_command(self) -> None:
        model = self._find_build_model(SOLAX_MIC_PRO_MODEL, "modbus_rtu", "serial")
        telemetry = {point.key: point for point in model.telemetry_points}
        commands = {point.key: point for point in model.command_points}

        self.assertEqual(telemetry["active_power_kw"].address, 0x40E)
        self.assertEqual(telemetry["active_power_kw"].scale, 0.001)
        self.assertEqual(telemetry["active_power_kw"].protocol_meta["summary_metric"], "power_kw")
        self.assertEqual(telemetry["mains_frequency_hz"].scale, 0.01)
        self.assertEqual(telemetry["total_energy_kwh"].address, 0x423)
        self.assertEqual(telemetry["total_energy_kwh"].datatype, "uint32_swapped")
        self.assertEqual(telemetry["daily_energy_kwh"].address, 0x425)
        self.assertEqual(model.defaults["inter_request_delay_ms"], 1000)

        self.assertEqual(commands["active_power_limit"].address, 0x60F)
        self.assertEqual(commands["active_power_limit"].unit, "%")
        self.assertEqual(
            inverter_io_service._encode_command_value(55, commands["active_power_limit"]),
            [55],
        )

    def test_mega_forth_and_grand_use_verified_power_scaling_and_readback(self) -> None:
        mega = self._find_build_model(SOLAX_MEGA_FORTH_MODEL, "modbus_tcp", "tcp")
        mega_telemetry = {point.key: point for point in mega.telemetry_points}
        mega_commands = {point.key: point for point in mega.command_points}

        self.assertEqual(mega_telemetry["active_power_kw"].address, 0x183)
        self.assertEqual(mega_telemetry["active_power_kw"].datatype, "int32")
        self.assertEqual(mega_telemetry["active_power_kw"].scale, 0.001)
        self.assertEqual(mega_commands["active_power_limit"].address, 0x2303)
        self.assertEqual(mega_commands["active_power_limit"].scale, 0.1)
        self.assertEqual(
            inverter_io_service._encode_command_value(55.5, mega_commands["active_power_limit"]),
            [555],
        )
        mega_readback = active_power_limit_readback_resolver.resolve_point(mega)
        self.assertIsNotNone(mega_readback)
        assert mega_readback is not None
        self.assertEqual(mega_readback.telemetry_point.address, 0x2303)

        grand = self._find_build_model(SOLAX_GRAND_MODEL, "modbus_rtu", "serial")
        grand_telemetry = {point.key: point for point in grand.telemetry_points}
        grand_commands = {point.key: point for point in grand.command_points}

        self.assertEqual(grand_telemetry["active_power_kw"].address, 0x00B4)
        self.assertEqual(grand_telemetry["active_power_kw"].scale, 0.1)
        self.assertEqual(grand_telemetry["pv6_power_kw"].address, 0x011C)
        self.assertEqual(grand_telemetry["pv6_power_kw"].scale, 0.0001)
        self.assertEqual(grand_commands["start_stop"].protocol_meta["enum_map"][0xFE], "Arresto rapido")
        self.assertIsNotNone(active_power_limit_resolver.resolve_for_write(grand, 48.5))

    def test_hybrid_profiles_preserve_swapped_words_without_claiming_total_power(self) -> None:
        for model_name in (SOLAX_AELIO_MODEL, SOLAX_ULTRA_MODEL):
            model = self._find_build_model(model_name, "modbus_rtu", "serial")
            telemetry = {point.key: point for point in model.telemetry_points}
            commands = {point.key: point for point in model.command_points}

            self.assertEqual(telemetry["total_energy_kwh"].address, 0x0052)
            self.assertEqual(telemetry["total_energy_kwh"].datatype, "uint32_swapped")
            self.assertNotIn("active_power_kw", telemetry)
            self.assertEqual(commands["remote_active_power_w"].address, 0x007E)
            self.assertEqual(commands["remote_active_power_w"].datatype, "int32_swapped")
            self.assertTrue(commands["remote_active_power_w"].protocol_meta["force_multi_write"])
            self.assertEqual(
                inverter_io_service._encode_command_value(-1000, commands["remote_active_power_w"]),
                [0xFC18, 0xFFFF],
            )
            self.assertIsNone(active_power_limit_resolver.resolve_for_write(model, 50))

        ultra = self._find_build_model(SOLAX_ULTRA_MODEL, "modbus_rtu", "serial")
        ultra_telemetry = {point.key: point for point in ultra.telemetry_points}
        self.assertEqual(ultra_telemetry["pv3_voltage_v"].address, 0x0122)
        self.assertEqual(ultra_telemetry["battery_2_power_kw"].address, 0x0129)

    def test_datahub_has_aggregated_power_limit_and_readback(self) -> None:
        model = self._find_build_model(SOLAX_DATAHUB_MODEL, "modbus_tcp", "tcp")
        telemetry = {point.key: point for point in model.telemetry_points}
        commands = {point.key: point for point in model.command_points}

        self.assertEqual(telemetry["active_power_kw"].address, 40520)
        self.assertEqual(telemetry["active_power_kw"].scale, 0.001)
        self.assertEqual(telemetry["active_power_limit_pct"].address, 45600)
        self.assertEqual(commands["active_power_limit"].address, 40600)
        self.assertNotIn("force_multi_write", commands["active_power_limit"].protocol_meta)
        self.assertEqual(
            inverter_io_service._encode_command_value(42.5, commands["active_power_limit"]),
            [425],
        )

        write_resolution = active_power_limit_resolver.resolve_for_write(model, 42.5)
        self.assertIsNotNone(write_resolution)
        readback_resolution = active_power_limit_readback_resolver.resolve_point(model)
        self.assertIsNotNone(readback_resolution)
        assert readback_resolution is not None
        self.assertEqual(readback_resolution.telemetry_point.key, "active_power_limit_pct")

    def test_ems1000_exposes_system_power_without_unsafe_generic_percent_command(self) -> None:
        model = self._find_build_model(SOLAX_EMS1000_MODEL, "modbus_tcp", "tcp")
        telemetry = {point.key: point for point in model.telemetry_points}
        commands = {point.key: point for point in model.command_points}

        self.assertEqual(telemetry["active_power_kw"].address, 0x006A)
        self.assertEqual(telemetry["active_power_kw"].scale, 0.01)
        self.assertEqual(telemetry["status"].address, 0x006C)
        self.assertEqual(commands["vpp_active_power_target_w"].address, 0x0033)
        self.assertTrue(commands["vpp_active_power_target_w"].protocol_meta["force_multi_write"])
        self.assertIsNone(active_power_limit_resolver.resolve_for_write(model, 50))

    def test_catalog_exports_solax_profiles_and_rtu_over_tcp_resolves_direct_models(self) -> None:
        catalog_models = {
            (model.brand, model.model, model.protocol, model.transport): model
            for model in get_inverter_catalog()
        }
        for model_name in SOLAX_DIRECT_MODELS:
            self.assertIn((SOLAX_BRAND, model_name, "modbus_rtu", "serial"), catalog_models)
            self.assertIn((SOLAX_BRAND, model_name, "modbus_tcp", "tcp"), catalog_models)

        self.assertIn((SOLAX_BRAND, SOLAX_DATAHUB_MODEL, "modbus_tcp", "tcp"), catalog_models)
        self.assertIn((SOLAX_BRAND, SOLAX_EMS1000_MODEL, "modbus_tcp", "tcp"), catalog_models)
        self.assertNotIn((SOLAX_BRAND, SOLAX_DATAHUB_MODEL, "modbus_rtu", "serial"), catalog_models)
        self.assertNotIn((SOLAX_BRAND, SOLAX_EMS1000_MODEL, "modbus_rtu", "serial"), catalog_models)

        resolved = inverter_profile_resolver.find_catalog_model(
            brand=SOLAX_BRAND,
            model=SOLAX_GRAND_MODEL,
            protocol="modbus_rtu",
            transport="tcp",
        )
        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.transport, "serial")

    def test_catalog_profiles_expose_manual_verification_metadata(self) -> None:
        model = self._find_build_model(SOLAX_DATAHUB_MODEL, "modbus_tcp", "tcp")

        self.assertEqual(model.catalog_meta["verification_status"], "manual_verified")
        self.assertEqual(model.catalog_meta["source_document"], "DATAHUB TCP_V1.3")
        self.assertFalse(model.catalog_meta["field_tested"])

    def _find_build_model(self, model_name: str, protocol: str, transport: str):
        matches = [
            model
            for model in build_solax_models(protocol, transport)
            if model.model == model_name
        ]
        self.assertEqual(len(matches), 1)
        return matches[0]


if __name__ == "__main__":
    unittest.main()
