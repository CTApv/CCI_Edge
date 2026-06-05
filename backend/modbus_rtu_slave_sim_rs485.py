#!/usr/bin/env python3

import argparse
import logging
import random
import signal
import sys
import threading
import time

import serial
from serial.rs485 import RS485Settings

REGISTER_COUNT = 2000
MAX_REGISTER_VALUE = 0xFFFF
STOP_EVENT = threading.Event()


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def append_crc(payload: bytes) -> bytes:
    crc = crc16_modbus(payload)
    return payload + bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def split_u32(value: int) -> tuple[int, int]:
    normalized = value & 0xFFFFFFFF
    return (normalized >> 16) & 0xFFFF, normalized & 0xFFFF


def is_valid_range(address: int, count: int) -> bool:
    return address >= 0 and count > 0 and address + count <= REGISTER_COUNT


def build_exception(slave_id: int, function: int, code: int) -> bytes:
    return append_crc(bytes((slave_id, function | 0x80, code)))


def get_inter_frame_gap_seconds(baudrate: int) -> float:
    char_time = 11.0 / max(baudrate, 1)
    return max(0.01, char_time * 4.5)


def expected_request_length(buffer: bytes, offset: int) -> int | None:
    if offset + 2 > len(buffer):
        return None

    function = buffer[offset + 1]
    if function in {3, 4, 6}:
        return 8
    if function == 16:
        if offset + 7 > len(buffer):
            return None
        byte_count = buffer[offset + 6]
        return 9 + byte_count
    return None


def extract_request_frame(buffer: bytearray, slave_id: int) -> bytes | None:
    index = 0
    while index < len(buffer):
        if buffer[index] != slave_id:
            index += 1
            continue

        frame_length = expected_request_length(buffer, index)
        if frame_length is None:
            if index > 0:
                del buffer[:index]
            return None

        if index + frame_length > len(buffer):
            if index > 0:
                del buffer[:index]
            return None

        frame = bytes(buffer[index : index + frame_length])
        payload = frame[:-2]
        received_crc = int.from_bytes(frame[-2:], byteorder="little")
        expected_crc = crc16_modbus(payload)
        if received_crc == expected_crc:
            del buffer[: index + frame_length]
            return frame

        index += 1

    if len(buffer) > 16:
        del buffer[:-8]
    return None


def read_frame(serial_port: serial.Serial, gap_seconds: float, slave_id: int) -> bytes | None:
    buffer = bytearray()
    last_data_at: float | None = None

    while not STOP_EVENT.is_set():
        try:
            chunk = serial_port.read(serial_port.in_waiting or 1)
        except serial.SerialException as exc:
            raise RuntimeError(f"Serial read failed: {exc}") from exc

        now = time.monotonic()
        if chunk:
            buffer.extend(chunk)
            last_data_at = now
            frame = extract_request_frame(buffer, slave_id)
            if frame is not None:
                return frame
            continue

        frame = extract_request_frame(buffer, slave_id)
        if frame is not None:
            return frame

        if buffer and last_data_at is not None and now - last_data_at >= gap_seconds:
            logging.warning("Discarding undecodable buffer after gap: %s", bytes(buffer).hex())
            buffer.clear()
            last_data_at = None

    return None


class RegisterStore:
    def __init__(
        self,
        *,
        nominal_power_kw: int,
        active_power_kw: int,
        daily_energy_kwh: int,
        total_energy_kwh: int,
        temperature_c: int,
        status: int,
        active_power_limit_pct: int,
        random_update_interval: float,
    ) -> None:
        self._lock = threading.Lock()
        self.holding = [0] * REGISTER_COUNT
        self.input = [0] * REGISTER_COUNT
        self.nominal_power_kw = nominal_power_kw
        self.random_update_interval = random_update_interval
        self._base_active_power_kw = active_power_kw
        self._daily_energy_kwh = daily_energy_kwh
        self._total_energy_kwh = total_energy_kwh
        self._temperature_c = temperature_c
        self._status = status
        self._active_power_limit_pct = active_power_limit_pct
        self._refresh_snapshot()

    def _refresh_snapshot(self) -> None:
        total_hi, total_lo = split_u32(self._total_energy_kwh)
        max_allowed_kw = max(
            0,
            int(round(self.nominal_power_kw * self._active_power_limit_pct / 100.0)),
        )
        limited_power_kw = min(self._base_active_power_kw, max_allowed_kw)

        snapshot = {
            0: limited_power_kw,
            1: self._daily_energy_kwh,
            2: total_hi,
            3: total_lo,
            4: self._temperature_c,
            5: self._status,
            10: self._active_power_limit_pct,
        }
        for register, value in snapshot.items():
            normalized = value & MAX_REGISTER_VALUE
            self.holding[register] = normalized
            self.input[register] = normalized

    def set_snapshot(
        self,
        *,
        active_power_kw: int,
        daily_energy_kwh: int,
        total_energy_kwh: int,
        temperature_c: int,
        status: int,
    ) -> None:
        with self._lock:
            self._base_active_power_kw = active_power_kw
            self._daily_energy_kwh = daily_energy_kwh
            self._total_energy_kwh = total_energy_kwh
            self._temperature_c = temperature_c
            self._status = status
            self._refresh_snapshot()

    def random_update(self) -> None:
        self.set_snapshot(
            active_power_kw=random.randint(5, self.nominal_power_kw),
            daily_energy_kwh=random.randint(50, 500),
            total_energy_kwh=100000 + random.randint(0, 200000),
            temperature_c=random.randint(20, 45),
            status=1,
        )

    def set_active_power_limit(self, value: int) -> None:
        with self._lock:
            self._active_power_limit_pct = max(0, min(100, value))
            self._refresh_snapshot()

    def read(self, table: str, address: int, count: int) -> list[int]:
        with self._lock:
            source = self.holding if table == "holding" else self.input
            return source[address : address + count]

    def write_single(self, address: int, value: int) -> None:
        normalized = value & MAX_REGISTER_VALUE
        with self._lock:
            if address == 0:
                self._base_active_power_kw = normalized
                self._refresh_snapshot()
                return
            if address == 10:
                self._active_power_limit_pct = max(0, min(100, normalized))
                self._refresh_snapshot()
                return

            self.holding[address] = normalized
            self.input[address] = normalized

    def write_many(self, address: int, values: list[int]) -> None:
        normalized = [value & MAX_REGISTER_VALUE for value in values]
        with self._lock:
            self.holding[address : address + len(normalized)] = normalized
            self.input[address : address + len(normalized)] = normalized

            if address <= 0 < address + len(normalized):
                self._base_active_power_kw = normalized[0 - address]
            if address <= 10 < address + len(normalized):
                self._active_power_limit_pct = max(0, min(100, normalized[10 - address]))
            self._refresh_snapshot()


def handle_request(frame: bytes, slave_id: int, store: RegisterStore) -> bytes | None:
    if len(frame) < 4:
        logging.warning("Frame too short: %s", frame.hex())
        return None

    payload = frame[:-2]
    received_crc = int.from_bytes(frame[-2:], byteorder="little")
    expected_crc = crc16_modbus(payload)
    if received_crc != expected_crc:
        logging.warning(
            "CRC mismatch expected=%04x received=%04x frame=%s",
            expected_crc,
            received_crc,
            frame.hex(),
        )
        return None

    request_slave_id = payload[0]
    function = payload[1]
    body = payload[2:]

    if request_slave_id != slave_id:
        return None

    if function in (3, 4):
        if len(body) != 4:
            return build_exception(slave_id, function, 3)
        address = int.from_bytes(body[0:2], byteorder="big")
        count = int.from_bytes(body[2:4], byteorder="big")
        if count <= 0 or count > 125:
            return build_exception(slave_id, function, 3)
        if not is_valid_range(address, count):
            return build_exception(slave_id, function, 2)

        table = "holding" if function == 3 else "input"
        values = store.read(table, address, count)
        logging.info("READ fn=%s addr=%s count=%s values=%s", function, address, count, values[:10])
        response = bytes((slave_id, function, count * 2))
        response += b"".join(value.to_bytes(2, byteorder="big") for value in values)
        return append_crc(response)

    if function == 6:
        if len(body) != 4:
            return build_exception(slave_id, function, 3)
        address = int.from_bytes(body[0:2], byteorder="big")
        value = int.from_bytes(body[2:4], byteorder="big")
        if not is_valid_range(address, 1):
            return build_exception(slave_id, function, 2)
        store.write_single(address, value)
        logging.info("WRITE SINGLE addr=%s value=%s", address, value)
        return append_crc(payload)

    if function == 16:
        if len(body) < 5:
            return build_exception(slave_id, function, 3)
        address = int.from_bytes(body[0:2], byteorder="big")
        count = int.from_bytes(body[2:4], byteorder="big")
        byte_count = body[4]
        raw_values = body[5:]
        if count <= 0 or count > 123 or byte_count != count * 2 or len(raw_values) != byte_count:
            return build_exception(slave_id, function, 3)
        if not is_valid_range(address, count):
            return build_exception(slave_id, function, 2)

        values = [
            int.from_bytes(raw_values[index : index + 2], byteorder="big")
            for index in range(0, len(raw_values), 2)
        ]
        store.write_many(address, values)
        logging.info("WRITE MULTI addr=%s count=%s values=%s", address, count, values[:10])
        response = bytes((slave_id, function)) + body[0:4]
        return append_crc(response)

    logging.warning("Unsupported function=%s", function)
    return build_exception(slave_id, function, 1)


def random_loop(store: RegisterStore) -> None:
    if store.random_update_interval <= 0:
        return
    while not STOP_EVENT.is_set():
        store.random_update()
        STOP_EVENT.wait(store.random_update_interval)


def stop_handler(signum: int, _frame: object) -> None:
    logging.info("Signal received: %s", signum)
    STOP_EVENT.set()
    sys.exit(0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Standalone Modbus RTU slave simulator with RS485 support")
    parser.add_argument("--port", required=True)
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument("--bytesize", type=int, choices=[5, 6, 7, 8], default=8)
    parser.add_argument("--parity", choices=["N", "E", "O"], default="N")
    parser.add_argument("--stopbits", type=int, choices=[1, 2], default=1)
    parser.add_argument("--slave-id", type=int, default=1)
    parser.add_argument("--nominal-power-kw", type=int, default=30)
    parser.add_argument("--active-power-kw", type=int, default=15)
    parser.add_argument("--daily-energy-kwh", type=int, default=120)
    parser.add_argument("--total-energy-kwh", type=int, default=123456)
    parser.add_argument("--temperature-c", type=int, default=28)
    parser.add_argument("--status", type=int, default=1)
    parser.add_argument("--active-power-limit-pct", type=int, default=100)
    parser.add_argument("--random-update-interval", type=float, default=1.0)
    parser.add_argument("--use-rs485-mode", action="store_true")
    parser.add_argument("--rs485-rts-level-for-tx", type=parse_bool, default=True)
    parser.add_argument("--rs485-rts-level-for-rx", type=parse_bool, default=False)
    parser.add_argument("--rs485-loopback", type=parse_bool, default=False)
    parser.add_argument("--rs485-delay-before-tx-ms", type=float, default=None)
    parser.add_argument("--rs485-delay-before-rx-ms", type=float, default=None)
    return parser


def open_serial_port(args: argparse.Namespace) -> serial.Serial:
    serial_port = serial.Serial(
        port=args.port,
        baudrate=args.baudrate,
        bytesize=args.bytesize,
        parity=args.parity,
        stopbits=args.stopbits,
        timeout=0.05,
        write_timeout=1,
    )

    if args.use_rs485_mode:
        serial_port.rs485_mode = RS485Settings(
            rts_level_for_tx=args.rs485_rts_level_for_tx,
            rts_level_for_rx=args.rs485_rts_level_for_rx,
            loopback=args.rs485_loopback,
            delay_before_tx=milliseconds_to_seconds(args.rs485_delay_before_tx_ms),
            delay_before_rx=milliseconds_to_seconds(args.rs485_delay_before_rx_ms),
        )

    return serial_port


def wait_for_serial_port(args: argparse.Namespace) -> serial.Serial:
    while not STOP_EVENT.is_set():
        try:
            return open_serial_port(args)
        except serial.SerialException as exc:
            logging.warning("Unable to open serial port %s: %s", args.port, exc)
            STOP_EVENT.wait(1.0)
    raise RuntimeError("Stop requested before serial port became available.")


def milliseconds_to_seconds(value_ms: float | None) -> float | None:
    if value_ms is None:
        return None
    return value_ms / 1000.0


def main() -> int:
    args = build_parser().parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)

    store = RegisterStore(
        nominal_power_kw=args.nominal_power_kw,
        active_power_kw=args.active_power_kw,
        daily_energy_kwh=args.daily_energy_kwh,
        total_energy_kwh=args.total_energy_kwh,
        temperature_c=args.temperature_c,
        status=args.status,
        active_power_limit_pct=args.active_power_limit_pct,
        random_update_interval=args.random_update_interval,
    )

    thread = threading.Thread(target=random_loop, args=(store,), daemon=True)
    thread.start()

    gap_seconds = get_inter_frame_gap_seconds(args.baudrate)
    serial_port = wait_for_serial_port(args)

    logging.info(
        "Slave started port=%s serial=%s %s%s%s slave_id=%s rs485=%s",
        args.port,
        args.baudrate,
        args.bytesize,
        args.parity,
        args.stopbits,
        args.slave_id,
        args.use_rs485_mode,
    )
    logging.info("Registers: 0=power, 1=daily, 2-3=total, 4=temp, 5=status, 10=active_power_limit_pct")

    try:
        while not STOP_EVENT.is_set():
            try:
                frame = read_frame(serial_port, gap_seconds, args.slave_id)
                if not frame:
                    continue

                logging.info("RX frame=%s", frame.hex())
                response = handle_request(frame, args.slave_id, store)
                if response is None:
                    continue

                serial_port.write(response)
                serial_port.flush()
                logging.info("TX frame=%s", response.hex())
            except RuntimeError as exc:
                logging.warning("%s", exc)
                try:
                    serial_port.close()
                except Exception:
                    pass
                if STOP_EVENT.is_set():
                    break
                STOP_EVENT.wait(1.0)
                serial_port = wait_for_serial_port(args)
    finally:
        try:
            serial_port.close()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
