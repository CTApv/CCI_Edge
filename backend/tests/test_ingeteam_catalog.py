import unittest

from app.catalog.ingeteam_catalog import build_ingeteam_models, build_ingeteam_telemetry


class IngeteamCatalogTests(unittest.TestCase):
    def test_live_telemetry_uses_manual_register_map(self) -> None:
        points = {point.key: point for point in build_ingeteam_telemetry()}

        self.assertEqual(points["dc_voltage_v"].address, 8)
        self.assertEqual(points["dc_current_a"].address, 9)
        self.assertEqual(points["ac_voltage_v"].address, 10)
        self.assertEqual(points["ac_current_a"].address, 13)
        self.assertEqual(points["active_power_kw"].address, 18)
        self.assertEqual(points["grid_frequency_hz"].address, 19)
        self.assertEqual(points["temperature_c"].address, 71)
        self.assertEqual(points["status"].address, 73)
        self.assertEqual(points["power_rating_kw"].address, 76)

        self.assertEqual(points["active_power_kw"].scale, 0.01)
        self.assertEqual(points["grid_frequency_hz"].scale, 0.01)
        self.assertEqual(points["power_rating_kw"].scale, 0.01)

    def test_defaults_probe_grid_frequency_input_register(self) -> None:
        rtu_model = build_ingeteam_models("modbus_rtu", "serial")[0]
        tcp_model = build_ingeteam_models("modbus_tcp", "tcp")[0]

        self.assertEqual(rtu_model.defaults["test_register"], 19)
        self.assertEqual(rtu_model.defaults["test_function"], "input")
        self.assertEqual(tcp_model.defaults["test_register"], 19)
        self.assertEqual(tcp_model.defaults["test_function"], "input")


if __name__ == "__main__":
    unittest.main()
