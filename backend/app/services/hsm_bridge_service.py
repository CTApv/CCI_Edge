from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event, Lock, Thread
from time import monotonic, sleep

import serial

from app.logger import get_logger
from app.schemas.device_schemas import DeviceResponse
from app.services.connection_manager import connection_manager
from app.services.device_service import device_service
from app.services.hsm_bridge_config_service import (
    HsmBridgeConfig,
    hsm_bridge_config_service,
)
from app.services.runtime_event_service import runtime_event_service

logger = get_logger("pv_edge_manager.hsm_bridge")

_ADVANCED_SERIAL_OPTION_KEYS = {
    "handle_local_echo",
    "use_rs485_mode",
    "rs485_rts_level_for_tx",
    "rs485_rts_level_for_rx",
    "rs485_loopback",
    "rs485_delay_before_tx_ms",
    "rs485_delay_before_rx_ms",
}


@dataclass(slots=True, frozen=True)
class HsmBridgeLineResolution:
    ready: bool
    note: str | None
    protocol: str | None
    baud_rate: int | None
    parity: str | None
    stop_bits: int | None
    byte_size: int | None
    advanced_options: dict[str, object]


@dataclass(slots=True, frozen=True)
class HsmBridgeRuntimeSnapshot:
    status: str
    running: bool
    startup_error: str | None
    queue_depth: int
    frames_received_count: int
    frames_forwarded_count: int
    frames_overwritten_count: int
    ack_ok_count: int
    timeout_count: int
    last_hsm_frame_at: str | None
    last_forward_at: str | None
    last_ack_at: str | None
    last_error_at: str | None
    last_error: str | None
    line_ready: bool
    line_note: str | None
    resolved_protocol: str | None
    resolved_baud_rate: int | None
    resolved_parity: str | None
    resolved_stop_bits: int | None
    resolved_byte_size: int | None


class HsmBridgeService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._queue_lock = Lock()
        self._hsm_serial_lock = Lock()
        self._stop_event = Event()
        self._listener_thread: Thread | None = None
        self._worker_thread: Thread | None = None
        self._hsm_serial: serial.Serial | None = None
        self._startup_error: str | None = None
        self._pending_frames: deque[bytes] = deque(maxlen=1)
        self._frames_received_count = 0
        self._frames_forwarded_count = 0
        self._frames_overwritten_count = 0
        self._ack_ok_count = 0
        self._timeout_count = 0
        self._last_hsm_frame_at: str | None = None
        self._last_forward_at: str | None = None
        self._last_ack_at: str | None = None
        self._last_error_at: str | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        config = hsm_bridge_config_service.get_config()
        if not config.enabled:
            logger.info("HSM bridge is disabled by configuration.")
            return

        with self._lock:
            if self._is_running_locked():
                return
            self._stop_event.clear()
            self._startup_error = None
            self._reset_runtime_locked()
            try:
                self._hsm_serial = self._open_hsm_serial(config)
            except Exception as exc:
                self._hsm_serial = None
                self._startup_error = str(exc)
                logger.error("Unable to start HSM bridge: %s", exc)
                runtime_event_service.record_event(
                    category="hsm",
                    level="error",
                    title="Avvio bridge HSM fallito",
                    message="Il bridge HSM non e riuscito ad aprire la seriale configurata.",
                    details={
                        "hsm_port": config.hsm_port,
                        "inverter_port": config.inverter_port,
                        "error": str(exc),
                    },
                    dedupe_key="hsm-start-failed",
                    dedupe_window_seconds=5.0,
                )
                return

            self._listener_thread = Thread(
                target=self._listen_hsm_loop,
                name="pv-edge-hsm-listener",
                daemon=True,
            )
            self._worker_thread = Thread(
                target=self._forward_loop,
                name="pv-edge-hsm-forwarder",
                daemon=True,
            )
            self._listener_thread.start()
            self._worker_thread.start()
            logger.info(
                "HSM bridge started on HSM port %s toward inverter port %s.",
                config.hsm_port or "<unset>",
                config.inverter_port or "<unset>",
            )
            runtime_event_service.record_event(
                category="hsm",
                level="success",
                title="Bridge HSM avviato",
                message=(
                    "Il runtime HSM e partito ed e pronto a inoltrare i frame "
                    "verso la linea inverter selezionata."
                ),
                details={
                    "hsm_port": config.hsm_port,
                    "inverter_port": config.inverter_port,
                },
                dedupe_key="hsm-started",
                dedupe_window_seconds=5.0,
            )

    def stop(self) -> None:
        with self._lock:
            listener_thread = self._listener_thread
            worker_thread = self._worker_thread
            was_running = self._is_running_locked()
            self._listener_thread = None
            self._worker_thread = None
            self._stop_event.set()

        for thread in (listener_thread, worker_thread):
            if thread is not None:
                thread.join(timeout=2)

        with self._lock:
            serial_port = self._hsm_serial
            self._hsm_serial = None
        if serial_port is not None:
            try:
                serial_port.close()
            except Exception:
                pass
        if was_running:
            runtime_event_service.record_event(
                category="hsm",
                level="info",
                title="Bridge HSM fermato",
                message="Il runtime HSM e stato arrestato e non inoltra piu frame verso gli inverter.",
                dedupe_key="hsm-stopped",
                dedupe_window_seconds=3.0,
            )

    def reload_runtime_config(self) -> None:
        self.stop()
        if hsm_bridge_config_service.get_config().enabled:
            self.start()

    def is_running(self) -> bool:
        with self._lock:
            return self._is_running_locked()

    def get_runtime_snapshot(self) -> HsmBridgeRuntimeSnapshot:
        config = hsm_bridge_config_service.get_config()
        line_resolution = self._resolve_inverter_line(config)
        with self._lock, self._queue_lock:
            running = self._is_running_locked()
            if not config.enabled:
                status = "offline"
            elif running and line_resolution.ready:
                status = "online"
            elif running:
                status = "pending"
            else:
                status = "offline"

            return HsmBridgeRuntimeSnapshot(
                status=status,
                running=running,
                startup_error=self._startup_error,
                queue_depth=len(self._pending_frames),
                frames_received_count=self._frames_received_count,
                frames_forwarded_count=self._frames_forwarded_count,
                frames_overwritten_count=self._frames_overwritten_count,
                ack_ok_count=self._ack_ok_count,
                timeout_count=self._timeout_count,
                last_hsm_frame_at=self._last_hsm_frame_at,
                last_forward_at=self._last_forward_at,
                last_ack_at=self._last_ack_at,
                last_error_at=self._last_error_at,
                last_error=self._last_error,
                line_ready=line_resolution.ready,
                line_note=line_resolution.note,
                resolved_protocol=line_resolution.protocol,
                resolved_baud_rate=line_resolution.baud_rate,
                resolved_parity=line_resolution.parity,
                resolved_stop_bits=line_resolution.stop_bits,
                resolved_byte_size=line_resolution.byte_size,
            )

    def _listen_hsm_loop(self) -> None:
        config = hsm_bridge_config_service.get_config()
        buffer = bytearray()
        last_byte_at: float | None = None
        frame_gap_seconds = max(0.005, config.frame_gap_ms / 1000.0)

        while not self._stop_event.is_set():
            serial_port = self._get_hsm_serial()
            if serial_port is None:
                break

            try:
                with self._hsm_serial_lock:
                    waiting = self._safe_serial_in_waiting(serial_port)
                    chunk = serial_port.read(waiting or 1)
            except Exception as exc:
                self._record_error(f"Errore lettura HSM: {exc}")
                sleep(0.05)
                continue

            if chunk:
                buffer.extend(chunk)
                last_byte_at = monotonic()

            if buffer and last_byte_at is not None and monotonic() - last_byte_at >= frame_gap_seconds:
                self._enqueue_frame(bytes(buffer))
                buffer.clear()
                last_byte_at = None

            sleep(0.005)

    def _forward_loop(self) -> None:
        while not self._stop_event.is_set():
            frame = self._pop_frame()
            if frame is None:
                sleep(0.01)
                continue

            config = hsm_bridge_config_service.get_config()
            if not config.enabled:
                continue

            if config.forward_delay_ms > 0:
                delay_seconds = config.forward_delay_ms / 1000.0
                deadline = monotonic() + delay_seconds
                while not self._stop_event.is_set() and monotonic() < deadline:
                    sleep(0.005)
                if self._stop_event.is_set():
                    return

            line_resolution = self._resolve_inverter_line(config)
            if not line_resolution.ready:
                self._record_error(line_resolution.note or "Linea inverter non disponibile.")
                continue

            response_timeout = max(0.05, config.ack_timeout_ms / 1000.0)
            expect_response = not self._is_broadcast_frame(frame)
            try:
                response = connection_manager.execute_modbus_rtu_raw(
                    config.inverter_port,
                    line_resolution.baud_rate or 9600,
                    line_resolution.byte_size or 8,
                    line_resolution.parity or "N",
                    line_resolution.stop_bits or 1,
                    timeout=response_timeout,
                    retries=0,
                    raw_request=frame,
                    response_timeout=response_timeout,
                    expect_response=expect_response,
                    advanced_options=line_resolution.advanced_options,
                    operation_kind="command",
                    inter_frame_gap_seconds=max(0.01, config.frame_gap_ms / 1000.0),
                )
            except Exception as exc:
                self._record_error(f"Errore inoltro HSM: {exc}")
                continue

            with self._lock:
                self._frames_forwarded_count += 1
                self._last_forward_at = self._utcnow_iso()

            if not expect_response:
                continue

            if not response:
                with self._lock:
                    self._timeout_count += 1
                    self._last_error_at = self._utcnow_iso()
                    self._last_error = "Timeout ACK inverter."
                runtime_event_service.record_event(
                    category="hsm",
                    level="warning",
                    title="ACK inverter non ricevuto",
                    message="Il bridge HSM ha inoltrato un frame ma non ha ricevuto risposta dalla linea inverter.",
                    details={
                        "hsm_port": config.hsm_port,
                        "inverter_port": config.inverter_port,
                        "ack_timeout_ms": config.ack_timeout_ms,
                    },
                    dedupe_key="hsm-ack-timeout",
                    dedupe_window_seconds=4.0,
                )
                continue

            serial_port = self._get_hsm_serial()
            if serial_port is None:
                continue

            try:
                with self._hsm_serial_lock:
                    if hasattr(serial_port, "reset_output_buffer"):
                        serial_port.reset_output_buffer()
                    serial_port.write(response)
                    serial_port.flush()
                with self._lock:
                    self._ack_ok_count += 1
                    self._last_ack_at = self._utcnow_iso()
            except Exception as exc:
                self._record_error(f"Errore risposta HSM: {exc}")

    def _resolve_inverter_line(self, config: HsmBridgeConfig) -> HsmBridgeLineResolution:
        inverter_port = config.inverter_port.strip()
        if not inverter_port:
            return HsmBridgeLineResolution(
                ready=False,
                note="Seleziona la porta inverter per il bridge HSM.",
                protocol=None,
                baud_rate=None,
                parity=None,
                stop_bits=None,
                byte_size=None,
                advanced_options={},
            )

        serial_devices = [
            device
            for device in device_service.list_devices()
            if device.transport == "serial"
            and str(device.connection_settings.get("port", "")).strip() == inverter_port
        ]
        if not serial_devices:
            return HsmBridgeLineResolution(
                ready=False,
                note="Nessun dispositivo seriale configurato sulla porta inverter selezionata.",
                protocol=None,
                baud_rate=None,
                parity=None,
                stop_bits=None,
                byte_size=None,
                advanced_options={},
            )

        if any(device.protocol != "modbus_rtu" for device in serial_devices):
            return HsmBridgeLineResolution(
                ready=False,
                note="Il bridge HSM supporta solo linee con dispositivi Modbus RTU.",
                protocol=None,
                baud_rate=None,
                parity=None,
                stop_bits=None,
                byte_size=None,
                advanced_options={},
            )

        first_device = serial_devices[0]
        base_signature = self._build_serial_signature(first_device)
        if base_signature is None:
            return HsmBridgeLineResolution(
                ready=False,
                note="Impostazioni seriali inverter incomplete sulla porta selezionata.",
                protocol=None,
                baud_rate=None,
                parity=None,
                stop_bits=None,
                byte_size=None,
                advanced_options={},
            )

        for device in serial_devices[1:]:
            if self._build_serial_signature(device) != base_signature:
                return HsmBridgeLineResolution(
                    ready=False,
                    note="La porta inverter contiene dispositivi con parametri seriali differenti.",
                    protocol=None,
                    baud_rate=None,
                    parity=None,
                    stop_bits=None,
                    byte_size=None,
                    advanced_options={},
                )

        baud_rate, parity, stop_bits, byte_size, advanced_options = base_signature
        return HsmBridgeLineResolution(
            ready=True,
            note=f"{len(serial_devices)} dispositivi RTU allineati sulla porta inverter.",
            protocol="modbus_rtu",
            baud_rate=baud_rate,
            parity=parity,
            stop_bits=stop_bits,
            byte_size=byte_size,
            advanced_options=advanced_options,
        )

    def _build_serial_signature(
        self,
        device: DeviceResponse,
    ) -> tuple[int, str, int, int, dict[str, object]] | None:
        settings = device.connection_settings
        try:
            baud_rate = int(settings.get("baud_rate", 0))
            parity = str(settings.get("parity", "")).strip().upper()
            stop_bits = int(settings.get("stop_bits", 0))
            byte_size = int(settings.get("byte_size", 0))
        except Exception:
            return None

        if baud_rate <= 0 or parity not in {"N", "E", "O"} or stop_bits not in {1, 2} or not 5 <= byte_size <= 8:
            return None

        advanced_options = {
            key: settings[key]
            for key in _ADVANCED_SERIAL_OPTION_KEYS
            if key in settings
        }
        return baud_rate, parity, stop_bits, byte_size, advanced_options

    def _open_hsm_serial(self, config: HsmBridgeConfig) -> serial.Serial:
        hsm_port = config.hsm_port.strip()
        inverter_port = config.inverter_port.strip()
        if not hsm_port:
            raise RuntimeError("Seleziona la porta HSM.")
        if not inverter_port:
            raise RuntimeError("Seleziona la porta inverter.")
        if hsm_port == inverter_port:
            raise RuntimeError("La porta HSM e la porta inverter devono essere diverse.")
        return serial.Serial(
            port=hsm_port,
            baudrate=config.hsm_baud_rate,
            bytesize=config.hsm_byte_size,
            parity=config.hsm_parity,
            stopbits=config.hsm_stop_bits,
            timeout=0.01,
            write_timeout=0.2,
        )

    def _get_hsm_serial(self) -> serial.Serial | None:
        with self._lock:
            return self._hsm_serial

    def _enqueue_frame(self, frame: bytes) -> None:
        if not frame:
            return
        with self._queue_lock, self._lock:
            if len(self._pending_frames) == self._pending_frames.maxlen:
                self._frames_overwritten_count += 1
            self._pending_frames.append(frame)
            self._frames_received_count += 1
            self._last_hsm_frame_at = self._utcnow_iso()

    def _pop_frame(self) -> bytes | None:
        with self._queue_lock:
            if not self._pending_frames:
                return None
            return self._pending_frames.pop()

    def _record_error(self, message: str) -> None:
        with self._lock:
            self._last_error = message
            self._last_error_at = self._utcnow_iso()
        runtime_event_service.record_event(
            category="hsm",
            level="error",
            title="Errore bridge HSM",
            message=message,
            details={},
            dedupe_key=f"hsm-error:{message}",
            dedupe_window_seconds=5.0,
        )

    def _reset_runtime_locked(self) -> None:
        with self._queue_lock:
            self._pending_frames.clear()
        self._frames_received_count = 0
        self._frames_forwarded_count = 0
        self._frames_overwritten_count = 0
        self._ack_ok_count = 0
        self._timeout_count = 0
        self._last_hsm_frame_at = None
        self._last_forward_at = None
        self._last_ack_at = None
        self._last_error_at = None
        self._last_error = None

    def _is_running_locked(self) -> bool:
        return bool(
            self._hsm_serial is not None
            and self._listener_thread is not None
            and self._listener_thread.is_alive()
            and self._worker_thread is not None
            and self._worker_thread.is_alive()
        )

    def _safe_serial_in_waiting(self, serial_port: serial.Serial) -> int:
        try:
            return int(serial_port.in_waiting or 0)
        except Exception:
            return 0

    def _is_broadcast_frame(self, frame: bytes) -> bool:
        return len(frame) >= 1 and frame[0] == 0

    def _utcnow_iso(self) -> str:
        return datetime.now(UTC).isoformat()


hsm_bridge_service = HsmBridgeService()
