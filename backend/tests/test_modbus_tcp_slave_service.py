import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.config import settings
from app.schemas.device_overview_schemas import (
    DeviceOverviewDiagnostics,
    DeviceOverviewMetrics,
)
from app.services.fleet_setpoint_service import FleetSetpointService
from app.services.live_cache import LiveCacheEntry
from app.services.modbus_tcp_slave_service import (
    HOLDING_ACTIVE_POWER_LIMIT_PERCENT_X10,
    HOLDING_REACTIVE_POWER_SETPOINT_PERCENT_X10,
    INPUT_ACTIVE_POWER_LIMIT_PERCENT_X10,
    INPUT_INVERTER_ACTIVE_POWER_END,
    INPUT_PLANT_ACTIVE_POWER_KW,
    INPUT_REACTIVE_POWER_SETPOINT_PERCENT_X10,
    MAX_EXPOSED_INVERTERS,
    ModbusTcpSlaveService,
)


class _FakeDeviceService:
    def __init__(self, devices: list[SimpleNamespace]) -> None:
        self._devices = devices

    def list_devices(self) -> list[SimpleNamespace]:
        return list(self._devices)


class _FakeLiveCache:
    def __init__(self, entries: dict[str, LiveCacheEntry]) -> None:
        self._entries = entries

    def get(self, device_id: str) -> LiveCacheEntry | None:
        return self._entries.get(device_id)


def _entry(power_kw: float) -> LiveCacheEntry:
    return LiveCacheEntry(
        metrics=DeviceOverviewMetrics(
            power_kw=power_kw,
            daily_energy_kwh=0.0,
            total_energy_kwh=0.0,
            temperature_c=25.0,
        ),
        diagnostics=DeviceOverviewDiagnostics(
            last_poll_status="stub_mode=false; stage=read_register",
            response_time_ms=20,
            retries=0,
            last_error=None,
        ),
        telemetry=[],
        timestamp="2026-03-27T10:00:00+00:00",
    )


class ModbusTcpSlaveServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._original_database_path = settings.database_path
        settings.database_path = Path(self._temp_dir.name) / "modbus-slave-test.db"

    def tearDown(self) -> None:
        settings.database_path = self._original_database_path
        self._temp_dir.cleanup()

    def test_holding_register_write_updates_active_and_reactive_setpoints(self) -> None:
        local_setpoint_service = FleetSetpointService()
        service = ModbusTcpSlaveService()
        fake_device_service = _FakeDeviceService([])
        fake_live_cache = _FakeLiveCache({})

        with (
            patch("app.services.modbus_tcp_slave_service.fleet_setpoint_service", local_setpoint_service),
            patch("app.services.modbus_tcp_slave_service.device_service", fake_device_service),
            patch("app.services.modbus_tcp_slave_service.live_cache", fake_live_cache),
            patch(
                "app.services.modbus_tcp_slave_service.modbus_tcp_slave_config_service.get_config",
                return_value=SimpleNamespace(
                    enabled=True,
                    cci_enabled=True,
                    host="0.0.0.0",
                    port=15020,
                    unit_id=1,
                    cci_readback_enabled=True,
                    cci_readback_range_percent=1.0,
                    cci_readback_stable_seconds=3.0,
                    cci_readback_active_power_only=False,
                ),
            ),
            patch("app.services.fleet_dispatch_service.fleet_dispatch_service.request_dispatch"),
        ):
            service._handle_holding_write(
                HOLDING_ACTIVE_POWER_LIMIT_PERCENT_X10,
                [250, service._encode_signed_int16(-125)],
            )

        state = local_setpoint_service.get_state()
        holding_values = service._holding_registers.getValues(1, 3)

        self.assertEqual(state.active_power_limit_percent, 25.0)
        self.assertEqual(service._cci_active_power_limit_percent, 25.0)
        self.assertEqual(service._reactive_power_setpoint_percent, -12.5)
        self.assertEqual(holding_values[1], 250)
        self.assertEqual(holding_values[2], service._encode_signed_int16(-125))

    def test_holding_register_addresses_start_at_one_and_two(self) -> None:
        self.assertEqual(HOLDING_ACTIVE_POWER_LIMIT_PERCENT_X10, 2)
        self.assertEqual(HOLDING_REACTIVE_POWER_SETPOINT_PERCENT_X10, 3)

    def test_holding_write_refreshes_only_control_registers(self) -> None:
        local_setpoint_service = FleetSetpointService()
        service = ModbusTcpSlaveService()
        fake_live_cache = _FakeLiveCache({})

        with (
            patch("app.services.modbus_tcp_slave_service.fleet_setpoint_service", local_setpoint_service),
            patch(
                "app.services.modbus_tcp_slave_service.device_service",
                SimpleNamespace(
                    list_devices=lambda: (_ for _ in ()).throw(
                        AssertionError("full device refresh not expected")
                    )
                ),
            ),
            patch("app.services.modbus_tcp_slave_service.live_cache", fake_live_cache),
            patch(
                "app.services.modbus_tcp_slave_service.modbus_tcp_slave_config_service.get_config",
                return_value=SimpleNamespace(
                    enabled=True,
                    cci_enabled=True,
                    host="0.0.0.0",
                    port=15020,
                    unit_id=1,
                    cci_readback_enabled=True,
                    cci_readback_range_percent=1.0,
                    cci_readback_stable_seconds=3.0,
                    cci_readback_active_power_only=False,
                ),
            ),
            patch("app.services.fleet_dispatch_service.fleet_dispatch_service.request_dispatch"),
        ):
            service._handle_holding_write(HOLDING_ACTIVE_POWER_LIMIT_PERCENT_X10, [250])

        holding_values = service._holding_registers.getValues(1, 3)
        input_values = service._input_registers.getValues(1, INPUT_ACTIVE_POWER_LIMIT_PERCENT_X10 + 1)

        self.assertEqual(holding_values[1], 250)
        self.assertEqual(input_values[INPUT_ACTIVE_POWER_LIMIT_PERCENT_X10], 250)

    def test_holding_writes_are_ignored_when_cci_is_disabled(self) -> None:
        local_setpoint_service = FleetSetpointService()
        service = ModbusTcpSlaveService()
        fake_device_service = _FakeDeviceService([])
        fake_live_cache = _FakeLiveCache({})

        with (
            patch("app.services.modbus_tcp_slave_service.fleet_setpoint_service", local_setpoint_service),
            patch("app.services.modbus_tcp_slave_service.device_service", fake_device_service),
            patch("app.services.modbus_tcp_slave_service.live_cache", fake_live_cache),
            patch(
                "app.services.modbus_tcp_slave_service.modbus_tcp_slave_config_service.get_config",
                return_value=SimpleNamespace(
                    enabled=True,
                    cci_enabled=False,
                    host="0.0.0.0",
                    port=15020,
                    unit_id=1,
                    cci_readback_enabled=True,
                    cci_readback_range_percent=1.0,
                    cci_readback_stable_seconds=3.0,
                    cci_readback_active_power_only=False,
                ),
            ),
            patch("app.services.fleet_dispatch_service.fleet_dispatch_service.request_dispatch"),
        ):
            service._handle_holding_write(
                HOLDING_ACTIVE_POWER_LIMIT_PERCENT_X10,
                [250, service._encode_signed_int16(-125)],
            )

        state = local_setpoint_service.get_state()

        self.assertIsNone(state.active_power_limit_percent)
        self.assertEqual(service._cci_active_power_limit_percent, 25.0)
        self.assertEqual(service._reactive_power_setpoint_percent, -12.5)

    def test_holding_write_is_buffered_when_cci_read_cycle_is_in_progress(self) -> None:
        local_setpoint_service = FleetSetpointService()
        service = ModbusTcpSlaveService()
        fake_device_service = _FakeDeviceService([])
        fake_live_cache = _FakeLiveCache({})
        service._cci_read_in_progress_generation = 5

        with (
            patch("app.services.modbus_tcp_slave_service.fleet_setpoint_service", local_setpoint_service),
            patch("app.services.modbus_tcp_slave_service.device_service", fake_device_service),
            patch("app.services.modbus_tcp_slave_service.live_cache", fake_live_cache),
            patch(
                "app.services.modbus_tcp_slave_service.modbus_tcp_slave_config_service.get_config",
                return_value=SimpleNamespace(
                    enabled=True,
                    cci_enabled=True,
                    host="0.0.0.0",
                    port=15020,
                    unit_id=1,
                    cci_readback_enabled=True,
                    cci_readback_range_percent=1.0,
                    cci_readback_stable_seconds=3.0,
                    cci_readback_active_power_only=False,
                ),
            ),
            patch("app.services.fleet_dispatch_service.fleet_dispatch_service.request_dispatch") as dispatch_mock,
        ):
            service._handle_holding_write(HOLDING_ACTIVE_POWER_LIMIT_PERCENT_X10, [250])

        dispatch_mock.assert_not_called()
        self.assertTrue(service.complete_cci_read_cycle(5))
        self.assertEqual(local_setpoint_service.get_state().active_power_limit_percent, 25.0)

    def test_manual_fleet_target_does_not_overwrite_cci_holding_registers(self) -> None:
        local_setpoint_service = FleetSetpointService()
        service = ModbusTcpSlaveService()
        fake_device_service = _FakeDeviceService([])
        fake_live_cache = _FakeLiveCache({})

        local_setpoint_service.set_active_power_limit_percent(55.0, source="api")
        service._cci_active_power_limit_percent = 25.0
        service._reactive_power_setpoint_percent = -12.5

        with (
            patch("app.services.modbus_tcp_slave_service.fleet_setpoint_service", local_setpoint_service),
            patch("app.services.modbus_tcp_slave_service.device_service", fake_device_service),
            patch("app.services.modbus_tcp_slave_service.live_cache", fake_live_cache),
        ):
            service._refresh_registers_locked()

        holding_values = service._holding_registers.getValues(1, 3)
        input_values = service._input_registers.getValues(1, INPUT_ACTIVE_POWER_LIMIT_PERCENT_X10 + 1)

        self.assertEqual(holding_values[1], 250)
        self.assertEqual(holding_values[2], service._encode_signed_int16(-125))
        self.assertEqual(input_values[INPUT_ACTIVE_POWER_LIMIT_PERCENT_X10], 550)

    def test_refresh_registers_exposes_plant_and_per_inverter_power_and_alarm_bits(self) -> None:
        local_setpoint_service = FleetSetpointService()
        local_setpoint_service.set_active_power_limit_percent(55.0, source="api")

        service = ModbusTcpSlaveService()
        service._reactive_power_setpoint_percent = -10.0
        fake_device_service = _FakeDeviceService(
            [
                SimpleNamespace(device_id="inv-1", status="online"),
                SimpleNamespace(device_id="inv-2", status="warning"),
                SimpleNamespace(device_id="inv-3", status="fault"),
            ]
        )
        fake_live_cache = _FakeLiveCache(
            {
                "inv-1": _entry(12.3),
                "inv-2": _entry(4.4),
            }
        )

        with (
            patch("app.services.modbus_tcp_slave_service.fleet_setpoint_service", local_setpoint_service),
            patch("app.services.modbus_tcp_slave_service.device_service", fake_device_service),
            patch("app.services.modbus_tcp_slave_service.live_cache", fake_live_cache),
        ):
            service._refresh_registers_locked()

        input_values = service._input_registers.getValues(1, INPUT_REACTIVE_POWER_SETPOINT_PERCENT_X10 + 1)
        discrete_values = service._discrete_inputs.getValues(1, 3)

        self.assertEqual(input_values[INPUT_PLANT_ACTIVE_POWER_KW], 17)
        self.assertEqual(input_values[1], 12)
        self.assertEqual(input_values[2], 4)
        self.assertEqual(input_values[3], 0)
        self.assertEqual(input_values[INPUT_ACTIVE_POWER_LIMIT_PERCENT_X10], 550)
        self.assertEqual(
            input_values[INPUT_REACTIVE_POWER_SETPOINT_PERCENT_X10],
            service._encode_signed_int16(-100),
        )
        self.assertEqual(discrete_values, [0, 1, 1])

    def test_refresh_registers_excludes_impossible_power_from_cci_inputs(self) -> None:
        local_setpoint_service = FleetSetpointService()
        service = ModbusTcpSlaveService()
        fake_device_service = _FakeDeviceService(
            [
                SimpleNamespace(
                    device_id="inv-good",
                    name="Inverter buono",
                    brand="Ingeteam",
                    model="Ingecon SUN 840HE TL",
                    status="online",
                ),
                SimpleNamespace(
                    device_id="inv-bad",
                    name="GT Series 192.168.2.108",
                    brand="Xantrex",
                    model="GT Series",
                    status="online",
                ),
            ]
        )
        fake_live_cache = _FakeLiveCache(
            {
                "inv-good": _entry(320.0),
                "inv-bad": _entry(4_271_701.66),
            }
        )

        with (
            patch("app.services.modbus_tcp_slave_service.fleet_setpoint_service", local_setpoint_service),
            patch("app.services.modbus_tcp_slave_service.device_service", fake_device_service),
            patch("app.services.modbus_tcp_slave_service.live_cache", fake_live_cache),
        ):
            service._refresh_registers_locked()

        input_values = service._input_registers.getValues(1, 3)

        self.assertEqual(input_values[INPUT_PLANT_ACTIVE_POWER_KW], 320)
        self.assertEqual(input_values[1], 320)
        self.assertEqual(input_values[2], 0)

    def test_refresh_registers_exposes_last_supported_inverter_slot(self) -> None:
        local_setpoint_service = FleetSetpointService()
        service = ModbusTcpSlaveService()
        devices = [
            SimpleNamespace(
                device_id=f"inv-{index}",
                name=f"Inverter {index}",
                brand="ZCS",
                model="ZUCCHETTI Azzurro 3PH 60KTL-V3",
                status="warning" if index == MAX_EXPOSED_INVERTERS else "online",
            )
            for index in range(1, MAX_EXPOSED_INVERTERS + 1)
        ]
        fake_device_service = _FakeDeviceService(devices)
        fake_live_cache = _FakeLiveCache(
            {
                f"inv-{MAX_EXPOSED_INVERTERS}": _entry(9.9),
            }
        )

        with (
            patch("app.services.modbus_tcp_slave_service.fleet_setpoint_service", local_setpoint_service),
            patch("app.services.modbus_tcp_slave_service.device_service", fake_device_service),
            patch("app.services.modbus_tcp_slave_service.live_cache", fake_live_cache),
        ):
            service._refresh_registers_locked()

        input_values = service._input_registers.getValues(1, INPUT_INVERTER_ACTIVE_POWER_END + 1)
        discrete_values = service._discrete_inputs.getValues(1, MAX_EXPOSED_INVERTERS)

        self.assertEqual(len(discrete_values), MAX_EXPOSED_INVERTERS)
        self.assertEqual(input_values[INPUT_INVERTER_ACTIVE_POWER_END], 10)
        self.assertEqual(discrete_values[MAX_EXPOSED_INVERTERS - 1], 1)


if __name__ == "__main__":
    unittest.main()
