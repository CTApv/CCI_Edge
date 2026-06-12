#!/usr/bin/env python3

"""Multi-slave Modbus TCP simulator for PV_GUARDIAN commissioning tests."""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import random
import time
from dataclasses import dataclass

from pymodbus.server import ModbusTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice


def encode_u16(value: float, *, scale: float = 1.0) -> int:
    return int(round(value / scale)) & 0xFFFF


def encode_i16(value: float, *, scale: float = 1.0) -> int:
    return int(round(value / scale)) & 0xFFFF


def encode_u32(value: float, *, scale: float = 1.0) -> tuple[int, int]:
    normalized = int(round(value / scale)) & 0xFFFFFFFF
    return (normalized >> 16) & 0xFFFF, normalized & 0xFFFF


def encode_i32(value: float, *, scale: float = 1.0) -> tuple[int, int]:
    return encode_u32(value, scale=scale)


def to_signed_word(value: int) -> int:
    normalized = int(value) & 0xFFFF
    return normalized - 0x10000 if normalized & 0x8000 else normalized


def build_realistic_snapshot(
    unit_id: int,
    *,
    now: float | None = None,
    nominal_power_kw: float = 100.0,
) -> dict[str, float]:
    timestamp = time.time() if now is None else now
    phase = ((timestamp / 90.0) + (unit_id * 0.07)) % (math.pi * 2)
    daylight = max(0.0, math.sin(phase))
    active_power_kw = nominal_power_kw * daylight * (0.72 + (unit_id % 7) * 0.035)
    return {
        "active_power_kw": round(active_power_kw, 2),
        "dc_power_kw": round(active_power_kw * 1.035, 2),
        "grid_power_kw": round(active_power_kw * 0.98, 2),
        "battery_power_kw": round(math.sin(phase * 1.7) * 8.0, 2),
        "load_power_kw": round(12.0 + (unit_id % 5) * 1.5, 2),
        "daily_energy_kwh": round(120.0 + unit_id * 2.5 + daylight * 15.0, 1),
        "total_energy_kwh": round(220_000.0 + unit_id * 1250.0 + timestamp / 3600.0, 1),
        "temperature_c": round(24.0 + daylight * 18.0 + (unit_id % 4), 1),
        "frequency_hz": round(50.0 + math.sin(phase * 0.5) * 0.04, 2),
        "voltage_v": round(400.0 + math.sin(phase * 0.8) * 3.0, 1),
        "current_a": round(active_power_kw * 1000.0 / (math.sqrt(3) * 400.0), 1),
        "power_factor": 0.998,
        "soc_percent": round(45.0 + math.sin(phase * 0.3) * 20.0, 1),
        "status": 2.0 if daylight > 0 else 3.0,
    }


@dataclass(slots=True)
class SimulatorOptions:
    host: str
    port: int
    units: int
    first_unit: int
    profile: str
    nominal_power_kw: float
    update_interval_seconds: float
    response_delay_ms: float
    drop_rate: float
    offline_units: set[int]


def build_profile_register_map(
    profile: str,
    unit_id: int,
    nominal_power_kw: float,
    *,
    now: float | None = None,
) -> dict[int, int]:
    values = build_realistic_snapshot(unit_id, now=now, nominal_power_kw=nominal_power_kw)
    if profile == "ems1000":
        encoded = {
            0x0049: encode_u32(values["daily_energy_kwh"], scale=0.1),
            0x004B: encode_u32(values["total_energy_kwh"], scale=0.1),
            0x005B: encode_i32(values["dc_power_kw"], scale=0.01),
            0x005D: encode_i32(values["grid_power_kw"], scale=0.01),
            0x005F: encode_i32(values["battery_power_kw"], scale=0.01),
            0x0061: encode_i32(values["load_power_kw"], scale=0.01),
            0x0063: encode_u16(values["soc_percent"], scale=0.1),
            0x006A: encode_i32(values["active_power_kw"], scale=0.01),
            0x006C: encode_u16(values["status"]),
            0x00CE: encode_i32(values["grid_power_kw"], scale=0.01),
            0x00D2: encode_i16(values["power_factor"], scale=0.001),
            0x00D9: encode_u16(values["voltage_v"], scale=0.1),
            0x00DB: encode_u16(values["voltage_v"] + 0.8, scale=0.1),
            0x00DC: encode_u16(values["voltage_v"] - 0.6, scale=0.1),
            0x00DD: encode_i16(values["current_a"], scale=0.1),
            0x00DE: encode_i16(values["current_a"] * 0.99, scale=0.1),
            0x00DF: encode_i16(values["current_a"] * 1.01, scale=0.1),
            0x00E0: encode_u16(values["frequency_hz"], scale=0.01),
        }
    elif profile == "datahub":
        encoded = {
            40440: encode_u16(values["voltage_v"], scale=0.1),
            40441: encode_u16(values["voltage_v"] + 0.8, scale=0.1),
            40442: encode_u16(values["voltage_v"] - 0.6, scale=0.1),
            40443: encode_i16(values["current_a"], scale=0.1),
            40444: encode_i16(values["current_a"] * 0.99, scale=0.1),
            40445: encode_i16(values["current_a"] * 1.01, scale=0.1),
            40446: encode_i32(values["grid_power_kw"], scale=0.001),
            40450: encode_i16(values["power_factor"], scale=0.001),
            40451: encode_u16(values["frequency_hz"], scale=0.01),
            40520: encode_i32(values["active_power_kw"], scale=0.001),
            40524: encode_u16(values["daily_energy_kwh"], scale=0.01),
            40526: encode_u32(values["total_energy_kwh"]),
            40528: encode_u32(nominal_power_kw, scale=0.01),
            40530: encode_i16(values["active_power_kw"], scale=0.01),
            40536: encode_i32(values["grid_power_kw"], scale=0.01),
            40538: encode_u16(values["soc_percent"]),
            45600: encode_u16(100.0, scale=0.1),
            45604: encode_u16(100.0, scale=0.1),
        }
    else:
        encoded = {
            0: encode_i16(values["active_power_kw"]),
            1: encode_u16(values["daily_energy_kwh"]),
            2: encode_u32(values["total_energy_kwh"]),
            4: encode_i16(values["temperature_c"]),
            5: encode_u16(values["status"]),
            10: encode_u16(100),
        }

    register_map: dict[int, int] = {}
    for register, raw_value in encoded.items():
        if isinstance(raw_value, tuple):
            for offset, word in enumerate(raw_value):
                register_map[register + offset] = word
        else:
            register_map[register] = raw_value
    return register_map


def build_sim_devices(options: SimulatorOptions) -> list[SimDevice]:
    ranges = (
        ((0x0000, 0x00E4),)
        if options.profile == "ems1000"
        else ((40440, 40610), (45600, 45610))
        if options.profile == "datahub"
        else ((0, 2048),)
    )
    devices: list[SimDevice] = []
    for unit_id in range(options.first_unit, options.first_unit + options.units):
        if unit_id in options.offline_units:
            continue

        initial_map = build_profile_register_map(
            options.profile,
            unit_id,
            options.nominal_power_kw,
        )
        simdata = [
            SimData(
                address=start,
                values=[
                    to_signed_word(initial_map.get(address, 0))
                    for address in range(start, end + 1)
                ],
                datatype=DataType.REGISTERS,
            )
            for start, end in ranges
        ]

        async def action(
            _function_code: int,
            start_address: int,
            current_registers: list[int],
            new_registers: list[int] | None,
            *,
            action_unit_id: int = unit_id,
        ) -> list[int] | None:
            if new_registers is not None:
                return new_registers
            interval = max(0.1, options.update_interval_seconds)
            quantized_now = math.floor(time.time() / interval) * interval
            current_map = build_profile_register_map(
                options.profile,
                action_unit_id,
                options.nominal_power_kw,
                now=quantized_now,
            )
            return [
                to_signed_word(current_map.get(start_address + offset, current_value))
                for offset, current_value in enumerate(current_registers)
            ]

        devices.append(SimDevice(id=unit_id, simdata=simdata, action=action))
    return devices


def parse_unit_set(raw_value: str) -> set[int]:
    if not raw_value.strip():
        return set()
    return {int(item.strip()) for item in raw_value.split(",") if item.strip()}


def parse_args() -> SimulatorOptions:
    parser = argparse.ArgumentParser(description="PV_GUARDIAN multi-slave Modbus TCP simulator")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5020)
    parser.add_argument("--units", type=int, default=50)
    parser.add_argument("--first-unit", type=int, default=1)
    parser.add_argument("--profile", choices=("ems1000", "datahub", "generic"), default="ems1000")
    parser.add_argument("--nominal-power-kw", type=float, default=100.0)
    parser.add_argument("--update-interval-seconds", type=float, default=2.0)
    parser.add_argument("--response-delay-ms", type=float, default=0.0)
    parser.add_argument("--drop-rate", type=float, default=0.0)
    parser.add_argument("--offline-units", default="")
    args = parser.parse_args()
    return SimulatorOptions(
        host=args.host,
        port=args.port,
        units=max(1, args.units),
        first_unit=max(1, args.first_unit),
        profile=args.profile,
        nominal_power_kw=max(1.0, args.nominal_power_kw),
        update_interval_seconds=max(0.1, args.update_interval_seconds),
        response_delay_ms=max(0.0, args.response_delay_ms),
        drop_rate=min(max(0.0, args.drop_rate), 1.0),
        offline_units=parse_unit_set(args.offline_units),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    options = parse_args()
    devices = build_sim_devices(options)

    def trace_packet(sending: bool, data: bytes) -> bytes:
        if not sending:
            return data
        if options.response_delay_ms > 0:
            time.sleep(options.response_delay_ms / 1000.0)
        if options.drop_rate > 0 and random.random() < options.drop_rate:
            logging.warning("Dropping simulated response")
            return b""
        return data

    logging.info(
        "Starting %s simulator on %s:%s with %s active units (%s offline)",
        options.profile,
        options.host,
        options.port,
        len(devices),
        len(options.offline_units),
    )

    async def serve() -> None:
        server = ModbusTcpServer(
            devices,
            address=(options.host, options.port),
            trace_packet=trace_packet,
        )
        await server.serve_forever()

    asyncio.run(serve())


if __name__ == "__main__":
    main()
