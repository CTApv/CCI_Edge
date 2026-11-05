import unittest

from modbus_tcp_multi_slave_sim import (
    SimulatorOptions,
    build_profile_register_map,
    build_realistic_snapshot,
    build_sim_devices,
    encode_i16,
    encode_i32,
    encode_u16,
    encode_u32,
    parse_unit_set,
)


class ModbusTcpMultiSlaveSimulatorTests(unittest.TestCase):
    def test_snapshot_is_plausible_and_deterministic_for_fixed_time(self) -> None:
        first = build_realistic_snapshot(7, now=1000.0, nominal_power_kw=120.0)
        second = build_realistic_snapshot(7, now=1000.0, nominal_power_kw=120.0)

        self.assertEqual(first, second)
        self.assertGreaterEqual(first["active_power_kw"], 0)
        self.assertLessEqual(first["active_power_kw"], 120)
        self.assertGreater(first["frequency_hz"], 49)
        self.assertLess(first["frequency_hz"], 51)
        self.assertGreaterEqual(first["soc_percent"], 0)
        self.assertLessEqual(first["soc_percent"], 100)

    def test_register_encoders_preserve_signed_and_scaled_values(self) -> None:
        self.assertEqual(encode_u16(50.0, scale=0.01), 5000)
        self.assertEqual(encode_i16(-1.0), 0xFFFF)
        self.assertEqual(encode_u32(65536), (1, 0))
        self.assertEqual(encode_i32(-1), (0xFFFF, 0xFFFF))

    def test_offline_unit_parser(self) -> None:
        self.assertEqual(parse_unit_set("7, 18,32"), {7, 18, 32})
        self.assertEqual(parse_unit_set(""), set())

    def test_multi_slave_profile_omits_offline_units_and_has_plausible_registers(self) -> None:
        options = SimulatorOptions(
            host="127.0.0.1",
            port=15020,
            units=3,
            first_unit=1,
            profile="ems1000",
            nominal_power_kw=100.0,
            update_interval_seconds=2.0,
            response_delay_ms=0.0,
            drop_rate=0.0,
            offline_units={2},
        )
        devices = build_sim_devices(options)
        register_map = build_profile_register_map("ems1000", 1, 100.0, now=1000.0)

        self.assertEqual([device.id for device in devices], [1, 3])
        self.assertGreater(register_map[0x00E0], 4900)
        self.assertLess(register_map[0x00E0], 5100)


if __name__ == "__main__":
    unittest.main()
