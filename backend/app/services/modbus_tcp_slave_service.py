import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event, Lock, Thread, current_thread
from time import monotonic
from typing import Callable

from pymodbus.datastore import (
    ModbusDeviceContext,
    ModbusSequentialDataBlock,
    ModbusServerContext,
)
from pymodbus.server import ModbusTcpServer

from app.logger import get_logger
from app.services.device_service import device_service
from app.services.live_cache import live_cache
from app.services.modbus_tcp_slave_config_service import modbus_tcp_slave_config_service
from app.services.fleet_setpoint_service import fleet_setpoint_service
from app.services.power_value_sanitizer import sanitize_produced_power_kw
from app.services.runtime_event_service import runtime_event_service

logger = get_logger("pv_edge_manager.modbus_tcp_slave")

HOLDING_ACTIVE_POWER_LIMIT_PERCENT_X10 = 2
HOLDING_REACTIVE_POWER_SETPOINT_PERCENT_X10 = 3
HOLDING_REGISTER_BASE_ADDRESS = 1

MAX_EXPOSED_INVERTERS = 247

INPUT_PLANT_ACTIVE_POWER_KW = 0
INPUT_INVERTER_ACTIVE_POWER_START = 1
INPUT_INVERTER_ACTIVE_POWER_END = INPUT_INVERTER_ACTIVE_POWER_START + MAX_EXPOSED_INVERTERS - 1
INPUT_ACTIVE_POWER_LIMIT_PERCENT_X10 = INPUT_INVERTER_ACTIVE_POWER_END + 1
INPUT_REACTIVE_POWER_SETPOINT_PERCENT_X10 = INPUT_ACTIVE_POWER_LIMIT_PERCENT_X10 + 1
INPUT_LAST_DISPATCH_OK_COUNT = INPUT_REACTIVE_POWER_SETPOINT_PERCENT_X10 + 1
INPUT_LAST_DISPATCH_ERROR_COUNT = INPUT_LAST_DISPATCH_OK_COUNT + 1
INPUT_LAST_DISPATCH_SKIPPED_COUNT = INPUT_LAST_DISPATCH_ERROR_COUNT + 1
INPUT_ELIGIBLE_DEVICE_COUNT = INPUT_LAST_DISPATCH_SKIPPED_COUNT + 1
INPUT_STATUS_FLAGS = INPUT_ELIGIBLE_DEVICE_COUNT + 1
INPUT_UPDATED_AT_EPOCH_HIGH = INPUT_STATUS_FLAGS + 1
INPUT_UPDATED_AT_EPOCH_LOW = INPUT_UPDATED_AT_EPOCH_HIGH + 1
INPUT_LAST_DISPATCH_AT_EPOCH_HIGH = INPUT_UPDATED_AT_EPOCH_LOW + 1
INPUT_LAST_DISPATCH_AT_EPOCH_LOW = INPUT_LAST_DISPATCH_AT_EPOCH_HIGH + 1

DISCRETE_INPUT_ALARM_START = 0

HOLDING_REGISTER_COUNT = 16
INPUT_REGISTER_COUNT = INPUT_LAST_DISPATCH_AT_EPOCH_LOW + 1
DISCRETE_INPUT_COUNT = MAX_EXPOSED_INVERTERS

# Backwards-compatible constant name for older tests/imports.
INPUT_PLANT_ACTIVE_POWER_KW_X10 = INPUT_PLANT_ACTIVE_POWER_KW


@dataclass(slots=True, frozen=True)
class CciConnectionSnapshot:
    status: str
    active_connections: int
    last_connected_at: str | None
    last_disconnected_at: str | None
    last_activity_at: str | None


@dataclass(slots=True, frozen=True)
class CciReadCycleRequest:
    generation: int
    active_power_only: bool
    reference_percent: float


class ObservableSequentialDataBlock(ModbusSequentialDataBlock):
    def __init__(
        self,
        address: int,
        values: list[int],
        *,
        on_write: Callable[[int, list[int]], None] | None = None,
    ) -> None:
        super().__init__(address, values)
        self._on_write = on_write

    def setValues(self, address: int, values: list[int] | int) -> object:
        result = super().setValues(address, values)
        if result is None and self._on_write is not None:
            normalized_values = values if isinstance(values, list) else [values]
            self._on_write(address, list(normalized_values))
        return result


class ModbusTcpSlaveService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._thread: Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: ModbusTcpServer | None = None
        self._active_unit_id: int | None = None
        self._startup_error: str | None = None
        self._cci_active_power_limit_percent: float | None = None
        self._reactive_power_setpoint_percent: float | None = None
        self._active_connection_count = 0
        self._last_client_connected_at: str | None = None
        self._last_client_disconnected_at: str | None = None
        self._last_client_activity_at: str | None = None
        self._has_seen_client_connection = False
        self._cci_read_window_generation = 0
        self._cci_read_window_current_generation: int | None = None
        self._cci_read_window_anchor_percent: float | None = None
        self._cci_read_window_last_value_percent: float | None = None
        self._cci_read_window_started_monotonic: float | None = None
        self._cci_read_completed_generation: int | None = None
        self._cci_read_in_progress_generation: int | None = None
        self._cci_dispatch_pending_after_read = False
        self._last_cci_timeline_percent: float | None = None
        self._last_cci_timeline_at_monotonic: float | None = None
        self._holding_registers = ObservableSequentialDataBlock(
            1,
            [0] * HOLDING_REGISTER_COUNT,
            on_write=self._handle_holding_write,
        )
        self._input_registers = ModbusSequentialDataBlock(1, [0] * INPUT_REGISTER_COUNT)
        self._discrete_inputs = ModbusSequentialDataBlock(1, [0] * DISCRETE_INPUT_COUNT)
        self._context = self._build_context(unit_id=1)

    def start(self) -> None:
        config = modbus_tcp_slave_config_service.get_config()
        if not config.enabled:
            logger.info("Modbus TCP slave is disabled by configuration.")
            return

        started_event = Event()
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return

            self._context = self._build_context(unit_id=config.unit_id)
            self._active_unit_id = config.unit_id
            self._startup_error = None
            self._reset_cci_connection_state_locked()
            self._refresh_registers_locked()
            self._thread = Thread(
                target=self._run_server,
                args=(started_event,),
                name="pv-edge-modbus-tcp-slave",
                daemon=True,
            )
            self._thread.start()
        started_event.wait(timeout=3)

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            loop = self._loop
            server = self._server

        if server is not None and loop is not None:
            try:
                future = asyncio.run_coroutine_threadsafe(server.shutdown(), loop)
                future.result(timeout=3)
            except Exception as exc:
                logger.warning("Failed to stop Modbus TCP slave cleanly: %s", exc)

        if thread is not None:
            thread.join(timeout=4)
            if thread.is_alive():
                logger.warning("Timed out waiting for Modbus TCP slave thread to stop.")

        with self._lock:
            if self._thread is thread and (thread is None or not thread.is_alive()):
                self._thread = None
                self._loop = None
                self._server = None
                self._active_unit_id = None

    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive() and self._server is not None

    def reload_runtime_config(self) -> None:
        self.stop()
        if modbus_tcp_slave_config_service.get_config().enabled:
            self.start()

    def refresh_registers(self) -> None:
        with self._lock:
            self._refresh_registers_locked()

    def refresh_control_registers(self) -> None:
        with self._lock:
            self._refresh_control_registers_locked()

    def reset_cci_read_tracking(self) -> None:
        with self._lock:
            self._reset_cci_read_tracking_locked()

    def get_startup_error(self) -> str | None:
        with self._lock:
            return self._startup_error

    def get_next_cci_read_due_in_seconds(self) -> float | None:
        config = modbus_tcp_slave_config_service.get_config()
        if not config.cci_enabled or not config.cci_readback_enabled:
            return None

        with self._lock:
            current_generation = self._cci_read_window_current_generation
            if (
                current_generation is None
                or self._cci_read_window_started_monotonic is None
                or self._cci_read_completed_generation == current_generation
                or self._cci_read_in_progress_generation == current_generation
            ):
                return None

            due_at = (
                self._cci_read_window_started_monotonic
                + max(0.1, float(config.cci_readback_stable_seconds))
            )
            return max(0.0, due_at - monotonic())

    def claim_due_cci_read_cycle(self) -> CciReadCycleRequest | None:
        config = modbus_tcp_slave_config_service.get_config()
        if not config.cci_enabled or not config.cci_readback_enabled:
            return None

        with self._lock:
            current_generation = self._cci_read_window_current_generation
            if (
                current_generation is None
                or self._cci_read_window_started_monotonic is None
                or self._cci_read_completed_generation == current_generation
                or self._cci_read_in_progress_generation == current_generation
            ):
                return None

            due_at = (
                self._cci_read_window_started_monotonic
                + max(0.1, float(config.cci_readback_stable_seconds))
            )
            if monotonic() < due_at:
                return None

            self._cci_read_in_progress_generation = current_generation
            reference_percent = (
                self._cci_read_window_last_value_percent
                if self._cci_read_window_last_value_percent is not None
                else self._cci_read_window_anchor_percent
            )
            return CciReadCycleRequest(
                generation=current_generation,
                active_power_only=bool(config.cci_readback_active_power_only),
                reference_percent=0.0 if reference_percent is None else float(reference_percent),
            )

    def complete_cci_read_cycle(self, generation: int) -> bool:
        with self._lock:
            if self._cci_read_in_progress_generation == generation:
                self._cci_read_in_progress_generation = None
            dispatch_pending = self._cci_dispatch_pending_after_read
            self._cci_dispatch_pending_after_read = False
            if self._cci_read_window_current_generation == generation:
                self._cci_read_completed_generation = generation
            return dispatch_pending

    def get_cci_connection_snapshot(self) -> CciConnectionSnapshot:
        with self._lock:
            running = self._thread is not None and self._thread.is_alive() and self._server is not None
            if not running:
                status = "offline"
            elif self._active_connection_count > 0:
                status = "online"
            elif self._has_seen_client_connection:
                status = "offline"
            else:
                status = "pending"

            return CciConnectionSnapshot(
                status=status,
                active_connections=self._active_connection_count,
                last_connected_at=self._last_client_connected_at,
                last_disconnected_at=self._last_client_disconnected_at,
                last_activity_at=self._last_client_activity_at,
            )

    def _run_server(self, started_event: Event) -> None:
        try:
            asyncio.run(self._serve(started_event))
        except Exception as exc:
            with self._lock:
                self._startup_error = str(exc)
            started_event.set()
            logger.error("Modbus TCP slave stopped with error: %s", exc)
        finally:
            with self._lock:
                if self._thread is current_thread():
                    self._server = None
                    self._loop = None
                    self._active_unit_id = None
                    self._thread = None
            started_event.set()
            logger.info("Modbus TCP slave stopped.")

    async def _serve(self, started_event: Event) -> None:
        config = modbus_tcp_slave_config_service.get_config()
        loop = asyncio.get_running_loop()
        with self._lock:
            self._loop = loop

        server = ModbusTcpServer(
            context=self._context,
            address=(
                config.host,
                config.port,
            ),
            ignore_missing_devices=False,
            trace_connect=self._handle_trace_connect,
            trace_packet=self._handle_trace_packet,
        )
        with self._lock:
            self._server = server

        logger.info(
            "Starting Modbus TCP slave on %s:%s unit_id=%s",
            config.host,
            config.port,
            config.unit_id,
        )
        started_event.set()
        await server.serve_forever(background=False)

    def _handle_holding_write(self, address: int, values: list[int]) -> None:
        config = modbus_tcp_slave_config_service.get_config()
        dispatch_requested = False
        for index, register_value in enumerate(values):
            register_address = address + index
            if register_address == HOLDING_ACTIVE_POWER_LIMIT_PERCENT_X10:
                requested_percent = self._normalize_cci_active_percent(register_value / 10.0)
                self._cci_active_power_limit_percent = requested_percent
                if not config.cci_enabled:
                    logger.info(
                        "Ignored Modbus TCP slave active power write on holding %s because CCI control is disabled.",
                        register_address,
                    )
                    continue
                state = fleet_setpoint_service.set_active_power_limit_percent(
                    requested_percent,
                    source="modbus_tcp_slave",
                )
                if (
                    state.updated_source == "modbus_tcp_slave"
                    and state.active_power_limit_percent is not None
                    and abs(state.active_power_limit_percent - requested_percent) < 0.051
                ):
                    dispatch_requested = self._track_cci_active_power_write(
                        requested_percent,
                        config=config,
                    )
                    self._record_cci_setpoint_event(
                        requested_percent,
                        dispatch_requested=dispatch_requested,
                    )
                else:
                    logger.warning(
                        "Ignored Modbus TCP slave active power write %.1f%% on holding %s because the active source is %s.",
                        requested_percent,
                        register_address,
                        state.updated_source or "none",
                    )
                    runtime_event_service.record_event(
                        category="cci",
                        level="warning",
                        title="Setpoint CCI ignorato",
                        message=(
                            f"Scrittura CCI {requested_percent:.1f}% ignorata: "
                            f"sorgente attiva {state.updated_source or 'none'}."
                        ),
                        details={
                            "requested_percent": requested_percent,
                            "register": register_address,
                            "active_source": state.updated_source or "none",
                        },
                        dedupe_key="cci-setpoint-ignored",
                        dedupe_window_seconds=2.0,
                    )
            elif register_address == HOLDING_REACTIVE_POWER_SETPOINT_PERCENT_X10:
                decoded_value = self._decode_signed_int16(register_value) / 10.0
                self._reactive_power_setpoint_percent = self._normalize_reactive_percent(
                    decoded_value
                )
                if not config.cci_enabled:
                    logger.info(
                        "Ignored Modbus TCP slave reactive power write on holding %s because CCI control is disabled.",
                        register_address,
                    )
                    continue

        if dispatch_requested:
            from app.services.fleet_dispatch_service import fleet_dispatch_service

            fleet_dispatch_service.request_dispatch()
        self.refresh_control_registers()

    def _refresh_registers_locked(self) -> None:
        state = fleet_setpoint_service.get_state()
        holding_values, control_input_values = self._build_control_register_values(state)

        input_values = [0] * INPUT_REGISTER_COUNT
        discrete_values = [0] * DISCRETE_INPUT_COUNT

        plant_active_power_kw = 0.0
        for index, device in enumerate(device_service.list_devices()[:MAX_EXPOSED_INVERTERS], start=1):
            cache_entry = live_cache.get(device.device_id)
            produced_power_kw = 0.0
            if cache_entry is not None:
                produced_power_kw = sanitize_produced_power_kw(
                    cache_entry.metrics.power_kw,
                    device=device,
                    telemetry=cache_entry.telemetry,
                )
            plant_active_power_kw += produced_power_kw
            input_values[INPUT_INVERTER_ACTIVE_POWER_START + index - 1] = self._encode_power_kw(
                produced_power_kw
            )
            discrete_values[DISCRETE_INPUT_ALARM_START + index - 1] = (
                1 if str(device.status).lower() in {"warning", "fault"} else 0
            )

        input_values[INPUT_PLANT_ACTIVE_POWER_KW] = self._encode_power_kw(
            plant_active_power_kw
        )
        input_values[
            INPUT_ACTIVE_POWER_LIMIT_PERCENT_X10 : INPUT_LAST_DISPATCH_AT_EPOCH_LOW + 1
        ] = control_input_values

        ModbusSequentialDataBlock.setValues(self._holding_registers, 1, holding_values)
        ModbusSequentialDataBlock.setValues(self._input_registers, 1, input_values)
        ModbusSequentialDataBlock.setValues(self._discrete_inputs, 1, discrete_values)

    def _refresh_control_registers_locked(self) -> None:
        state = fleet_setpoint_service.get_state()
        holding_values, control_input_values = self._build_control_register_values(state)
        ModbusSequentialDataBlock.setValues(self._holding_registers, 1, holding_values)
        ModbusSequentialDataBlock.setValues(
            self._input_registers,
            INPUT_ACTIVE_POWER_LIMIT_PERCENT_X10 + 1,
            control_input_values,
        )

    def _build_control_register_values(self, state: object) -> tuple[list[int], list[int]]:
        cci_active_power_limit_percent_x10 = 0
        if self._cci_active_power_limit_percent is not None:
            cci_active_power_limit_percent_x10 = int(
                round(self._cci_active_power_limit_percent * 10.0)
            )
        cci_reactive_power_setpoint_percent_x10 = 0
        if self._reactive_power_setpoint_percent is not None:
            cci_reactive_power_setpoint_percent_x10 = int(
                round(self._reactive_power_setpoint_percent * 10.0)
            )
        active_power_limit_percent_x10 = 0
        if state.active_power_limit_percent is not None:
            active_power_limit_percent_x10 = int(round(state.active_power_limit_percent * 10.0))

        holding_values = [0] * HOLDING_REGISTER_COUNT
        holding_values[
            self._holding_register_index(HOLDING_ACTIVE_POWER_LIMIT_PERCENT_X10)
        ] = cci_active_power_limit_percent_x10
        holding_values[
            self._holding_register_index(HOLDING_REACTIVE_POWER_SETPOINT_PERCENT_X10)
        ] = self._encode_signed_int16(
            cci_reactive_power_setpoint_percent_x10
        )

        updated_epoch = self._iso_to_epoch_seconds(state.updated_at)
        last_dispatch_epoch = self._iso_to_epoch_seconds(state.last_dispatch_at)
        status_flags = 0
        if self._thread is not None and self._thread.is_alive():
            status_flags |= 0x0001
        if state.active_power_limit_percent is not None:
            status_flags |= 0x0002
        if self._reactive_power_setpoint_percent is not None:
            status_flags |= 0x0004

        return holding_values, [
            active_power_limit_percent_x10,
            self._encode_signed_int16(cci_reactive_power_setpoint_percent_x10),
            state.last_dispatch_ok_count & 0xFFFF,
            state.last_dispatch_error_count & 0xFFFF,
            state.last_dispatch_skipped_count & 0xFFFF,
            state.eligible_device_count & 0xFFFF,
            status_flags,
            (updated_epoch >> 16) & 0xFFFF,
            updated_epoch & 0xFFFF,
            (last_dispatch_epoch >> 16) & 0xFFFF,
            last_dispatch_epoch & 0xFFFF,
        ]

    def _handle_trace_connect(self, connected: bool) -> None:
        with self._lock:
            timestamp = self._utc_now()
            if connected:
                self._active_connection_count += 1
                self._last_client_connected_at = timestamp
                self._last_client_activity_at = timestamp
                self._has_seen_client_connection = True
            else:
                self._active_connection_count = max(0, self._active_connection_count - 1)
                self._last_client_disconnected_at = timestamp
        runtime_event_service.record_event(
            category="cci",
            level="success" if connected else "warning",
            title="CCI connesso" if connected else "CCI disconnesso",
            message=(
                "Un client CCI ha aperto una connessione verso il nostro slave Modbus TCP."
                if connected
                else "Il client CCI si e scollegato dal nostro slave Modbus TCP."
            ),
            dedupe_key="cci-connection-online" if connected else "cci-connection-offline",
            dedupe_window_seconds=2.0,
        )

    def _handle_trace_packet(self, sending: bool, data: bytes) -> bytes:
        if not sending and data:
            with self._lock:
                self._last_client_activity_at = self._utc_now()
        return data

    def _reset_cci_connection_state_locked(self) -> None:
        self._active_connection_count = 0
        self._last_client_connected_at = None
        self._last_client_disconnected_at = None
        self._last_client_activity_at = None
        self._has_seen_client_connection = False

    def _track_cci_active_power_write(self, requested_percent: float, *, config: object) -> bool:
        with self._lock:
            return self._track_cci_active_power_write_locked(
                requested_percent,
                config=config,
            )

    def _track_cci_active_power_write_locked(self, requested_percent: float, *, config: object) -> bool:
        if not bool(getattr(config, "cci_readback_enabled", False)):
            self._reset_cci_read_tracking_locked()
            return True

        now_monotonic = monotonic()
        if self._cci_read_in_progress_generation is not None:
            self._cci_dispatch_pending_after_read = True
            self._start_cci_read_window_locked(
                requested_percent,
                now_monotonic=now_monotonic,
            )
            return False

        current_generation = self._cci_read_window_current_generation
        read_completed_for_current_window = (
            current_generation is not None
            and self._cci_read_completed_generation == current_generation
        )
        if (
            self._cci_read_window_anchor_percent is None
            or self._cci_read_window_started_monotonic is None
            or read_completed_for_current_window
        ):
            self._start_cci_read_window_locked(
                requested_percent,
                now_monotonic=now_monotonic,
            )
            return True

        band_percent = max(0.0, float(getattr(config, "cci_readback_range_percent", 0.0)))
        if abs(requested_percent - self._cci_read_window_anchor_percent) > band_percent:
            self._start_cci_read_window_locked(
                requested_percent,
                now_monotonic=now_monotonic,
            )
        else:
            self._cci_read_window_last_value_percent = requested_percent
        return True

    def _start_cci_read_window_locked(
        self,
        requested_percent: float,
        *,
        now_monotonic: float,
    ) -> None:
        self._cci_read_window_generation += 1
        self._cci_read_window_current_generation = self._cci_read_window_generation
        self._cci_read_window_anchor_percent = requested_percent
        self._cci_read_window_last_value_percent = requested_percent
        self._cci_read_window_started_monotonic = now_monotonic

    def _reset_cci_read_tracking_locked(self) -> None:
        self._cci_read_window_current_generation = None
        self._cci_read_window_anchor_percent = None
        self._cci_read_window_last_value_percent = None
        self._cci_read_window_started_monotonic = None
        self._cci_read_completed_generation = None
        self._cci_read_in_progress_generation = None
        self._cci_dispatch_pending_after_read = False
        self._last_cci_timeline_percent = None
        self._last_cci_timeline_at_monotonic = None

    def _record_cci_setpoint_event(
        self,
        requested_percent: float,
        *,
        dispatch_requested: bool,
    ) -> None:
        now_monotonic = monotonic()
        with self._lock:
            should_emit = (
                self._last_cci_timeline_percent is None
                or abs(requested_percent - self._last_cci_timeline_percent) >= 1.0
                or self._last_cci_timeline_at_monotonic is None
                or (now_monotonic - self._last_cci_timeline_at_monotonic) >= 3.0
            )
            if not should_emit:
                return
            self._last_cci_timeline_percent = requested_percent
            self._last_cci_timeline_at_monotonic = now_monotonic

        runtime_event_service.record_event(
            category="setpoint",
            level="info",
            title="Setpoint ricevuto dal CCI",
            message=f"Il CCI ha aggiornato il target impianto a {requested_percent:.1f}%.",
            details={
                "source": "modbus_tcp_slave",
                "requested_percent": requested_percent,
                "dispatch_requested": dispatch_requested,
            },
            dedupe_key="cci-setpoint",
            dedupe_window_seconds=0.5,
        )

    def _iso_to_epoch_seconds(self, timestamp: str | None) -> int:
        if not timestamp:
            return 0
        return int(datetime.fromisoformat(timestamp).timestamp())

    def _build_context(self, *, unit_id: int) -> ModbusServerContext:
        return ModbusServerContext(
            devices={
                unit_id: ModbusDeviceContext(
                    hr=self._holding_registers,
                    ir=self._input_registers,
                    di=self._discrete_inputs,
                ),
            },
            single=False,
        )

    def _normalize_reactive_percent(self, value: float) -> float:
        return round(min(max(float(value), -100.0), 100.0), 1)

    def _normalize_cci_active_percent(self, value: float) -> float:
        return round(min(max(float(value), 0.0), 100.0), 1)

    def _encode_power_kw(self, value_kw: float) -> int:
        return max(0, min(0xFFFF, int(round(max(0.0, float(value_kw))))))

    def _encode_signed_int16(self, value: int) -> int:
        normalized = max(-0x8000, min(0x7FFF, int(value)))
        return normalized & 0xFFFF

    def _decode_signed_int16(self, value: int) -> int:
        normalized = int(value) & 0xFFFF
        if normalized & 0x8000:
            return normalized - 0x10000
        return normalized

    def _utc_now(self) -> str:
        return datetime.now(UTC).isoformat()

    def _holding_register_index(self, register_address: int) -> int:
        return register_address - HOLDING_REGISTER_BASE_ADDRESS


modbus_tcp_slave_service = ModbusTcpSlaveService()
