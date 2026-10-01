import unittest

from app.catalog.cgs_sinvert_box_catalog import (
    CGS_SINVERT_BOX_BRAND,
    CGS_SINVERT_BOX_MODELS,
    build_cgs_sinvert_box_models,
)
from app.catalog.inverter_catalog import get_inverter_catalog
from app.services.inverter_io_service import inverter_io_service


class CgsSinvertBoxCatalogTests(unittest.TestCase):
    def test_all_one_to_five_unit_variants_are_exported(self) -> None:
        catalog_keys = {
            (model.brand, model.model, model.protocol, model.transport)
            for model in get_inverter_catalog()
        }
        self.assertEqual(len(CGS_SINVERT_BOX_MODELS), 5)
        for model_name in CGS_SINVERT_BOX_MODELS:
            self.assertIn(
                (CGS_SINVERT_BOX_BRAND, model_name, "modbus_tcp", "tcp"),
                catalog_keys,
            )

    def test_five_unit_profile_matches_manual_register_map(self) -> None:
        model = build_cgs_sinvert_box_models()[-1]
        telemetry = {point.key: point for point in model.telemetry_points}
        commands = {point.key: point for point in model.command_points}

        self.assertEqual(model.defaults["port"], 502)
        self.assertEqual(model.defaults["test_register"], 1)
        self.assertEqual(telemetry["system_status_bits"].protocol_meta["bitmask_labels"][0], "Sistema bloccato per manomissione")
        self.assertEqual(telemetry["regulation_availability_bits"].address, 165)
        self.assertEqual(telemetry["inverter_running_bits"].address, 80)
        self.assertEqual(telemetry["communication_error_bits"].address, 81)
        self.assertEqual(telemetry["active_power_inv_u_1"].address, 92)
        self.assertEqual(telemetry["active_power_inv_u_5"].address, 100)
        self.assertEqual(telemetry["active_power_limit_pct_inv_u_5"].address, 120)
        self.assertEqual(telemetry["setpoint_activation_bits"].address, 0)
        self.assertEqual(telemetry["setpoint_activation_bits"].protocol_meta["bitmask_labels"][3], "Setpoint limite attivi")
        self.assertEqual(commands["active_power_limit"].address, 112)
        self.assertEqual(commands["active_power_limit_inv_u_5"].address, 120)
        self.assertEqual(commands["setpoint_activation_mode"].address, 167)
        self.assertEqual(commands["setpoint_activation_mode"].protocol_meta["enum_map"][-1], "ON")

    def test_float32_commands_are_encoded_msw_first_big_endian(self) -> None:
        model = build_cgs_sinvert_box_models()[0]
        command = {point.key: point for point in model.command_points}["active_power_limit"]
        self.assertEqual(
            inverter_io_service._encode_command_value(50.0, command),
            [0x4248, 0x0000],
        )

    def test_profiles_only_include_configured_inverter_units(self) -> None:
        for unit_count, model in enumerate(build_cgs_sinvert_box_models(), start=1):
            power_points = [
                point for point in model.telemetry_points
                if point.key.startswith("active_power_inv_u_")
            ]
            limit_commands = [
                point for point in model.command_points
                if point.key.startswith("active_power_limit")
            ]
            self.assertEqual(len(power_points), unit_count)
            self.assertEqual(len(limit_commands), unit_count)


if __name__ == "__main__":
    unittest.main()
