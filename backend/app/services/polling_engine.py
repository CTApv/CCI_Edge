from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil
from threading import Event, Lock, Thread
from time import monotonic, perf_counter

from app.logger import get_logger
from app.models.inverter_model import InverterModel, InverterPoint
from app.schemas.device_overview_schemas import (
    DeviceTelemetryPoint,
    DeviceOverviewDiagnostics,
    DeviceOverviewMetrics,
)
from app.schemas.device_schemas import DeviceResponse
from app.services.device_runtime import (
    build_poll_endpoint_key,
    get_effective_full_poll_interval_seconds,
    get_effective_heartbeat_interval_seconds,
    get_effective_poll_interval_seconds,
    get_effective_retry_count,
    is_successful_full_poll,
    is_successful_real_poll,
    uses_serial_like_polling,
)
from app.services.connection_manager import connection_manager
from app.services.endpoint_runtime_service import endpoint_runtime_service
from app.services.device_service import device_service
from app.services.inverter_io_service import inverter_io_service
from app.services.inverter_profile_resolver import inverter_profile_resolver
from app.services.live_cache import LiveCacheEntry, live_cache
from app.services.power_history_service import power_history_service
from app.services.power_value_sanitizer import sanitize_device_power_kw
from app.services.telemetry_quality_service import telemetry_quality_service

SUPPORTED_POLL_PROTOCOLS = {"modbus_tcp", "modbus_rtu", "sunspec", "aurora", "delta_rs485"}
MAX_PARALLEL_POLL_WORKERS = 8
TCP_SHARED_MAX_ENDPOINT_OCCUPANCY_SECONDS = 4.0
TCP_SHARED_MAX_ACTIVE_POWER_BUDGET_PER_ENDPOINT_CYCLE = 32
TCP_SHARED_MAX_FULL_READ_BUDGET_PER_ENDPOINT_CYCLE = 1
TCP_SHARED_ACTIVE_POWER_BURST_BEFORE_FULL = 3
TCP_SHARED_FAST_ACTIVE_POWER_INTERVAL_SECONDS = 2.0
TCP_SHARED_MIN_FULL_POLL_INTERVAL_SECONDS = 60.0
TCP_SHARED_SLOW_OPERATION_THRESHOLD_MS = 750.0
TCP_SHARED_SLOW_FULL_READ_INTERVAL_SECONDS = 45.0
SERIAL_MAX_OPERATIONS_PER_ENDPOINT_CYCLE = 32
SERIAL_MAX_FULL_READ_BUDGET_PER_ENDPOINT_CYCLE = 10
SERIAL_MAX_HEARTBEAT_BUDGET_PER_ENDPOINT_CYCLE = 24
SERIAL_FAST_HEARTBEAT_INTERVAL_SECONDS = 2.0
SERIAL_INITIAL_FULL_POLL_FALLBACK_SECONDS = 300.0
SERIAL_MAX_ENDPOINT_OCCUPANCY_SECONDS = 9.0
POLLING_ENGINE_IDLE_WAIT_SECONDS = 0.2
POLLING_ENGINE_BUSY_WAIT_SECONDS = 0.01
POLLING_ENGINE_ERROR_WAIT_SECONDS = 1.0
_NO_DUE_AT = float("inf")

logger = get_logger("pv_edge_manager.polling")


@dataclass(slots=True, frozen=True)
class _EndpointPollResult:
    device: DeviceResponse
    entry: LiveCacheEntry | None
    poll_kind: str
    next_full_due_at: float | None = None
    next_heartbeat_due_at: float | None = None


@dataclass(slots=True, frozen=True)
class _SerialEndpointOperation:
    device: DeviceResponse
    poll_kind: str


@dataclass(slots=True, frozen=True)
class _SerialEndpointPlan:
    operations: list[_SerialEndpointOperation]
    queued_full_due_count: int
    queued_heartbeat_due_count: int
    planned_full_count: int
    planned_heartbeat_count: int


@dataclass(slots=True)
class _SerialEndpointRuntimeState:
    endpoint_type: str
    endpoint_label: str
    queued_full_due_count: int = 0
    queued_heartbeat_due_count: int = 0
    planned_full_count: int = 0
    planned_heartbeat_count: int = 0
    executed_full_count: int = 0
    executed_heartbeat_count: int = 0
    priority_deferral_count: int = 0
    last_priority_at: str | None = None
    last_cycle_started_at: str | None = None
    last_cycle_completed_at: str | None = None
    last_cycle_duration_ms: int | None = None
    average_cycle_duration_ms: float | None = None
    average_operation_duration_ms: float | None = None
    cycle_count: int = 0


def poll_device(
    device: DeviceResponse,
    *,
    poll_kind: str = "full",
) -> LiveCacheEntry | None:
    if device.protocol not in SUPPORTED_POLL_PROTOCOLS:
        return None

    inverter_model = inverter_profile_resolver.resolve_for_device(device)
    if inverter_model is None:
        return _build_fallback_entry(
            last_poll_status="stub_mode=false; stage=model_lookup",
            last_error="Catalog model not found for device.",
            poll_kind=poll_kind,
        )

    started_at = perf_counter()
    try:
        telemetry = (
            inverter_io_service.read_heartbeat(device, inverter_model)
            if poll_kind == "heartbeat"
            else inverter_io_service.read_active_power_only(device, inverter_model)
            if poll_kind == "active_power"
            else inverter_io_service.read_telemetry(
                device,
                inverter_model,
                essential_only=True,
            )
        )
        values = telemetry.values
        raw_power_kw = _metric_value(
            values=values,
            points=inverter_model.telemetry_points,
            canonical_key="active_power_kw",
            summary_metric="power_kw",
            default=0.0,
        )
        sanitized_power_kw = sanitize_device_power_kw(
            raw_power_kw,
            device=device,
            values=values,
            telemetry_points=inverter_model.telemetry_points,
        )
        return _build_cache_entry(
            metrics=DeviceOverviewMetrics(
                power_kw=sanitized_power_kw if sanitized_power_kw is not None else 0.0,
                daily_energy_kwh=_metric_value(
                    values=values,
                    points=inverter_model.telemetry_points,
                    canonical_key="daily_energy_kwh",
                    summary_metric="daily_energy_kwh",
                    default=0.0,
                    device=device,
                    validate_quality=True,
                ),
                total_energy_kwh=_metric_value(
                    values=values,
                    points=inverter_model.telemetry_points,
                    canonical_key="total_energy_kwh",
                    summary_metric="total_energy_kwh",
                    default=0.0,
                    device=device,
                    validate_quality=True,
                ),
                temperature_c=_metric_value(
                    values=values,
                    points=inverter_model.telemetry_points,
                    canonical_key="temperature_c",
                    summary_metric="temperature_c",
                    default=25.0,
                    device=device,
                    validate_quality=True,
                ),
            ),
            diagnostics=DeviceOverviewDiagnostics(
                last_poll_status=(
                    f"status={_status_value(values, inverter_model)}; stage=read_register; "
                    f"stub_mode=false; poll_kind={poll_kind}; "
                    f"unit_argument_style={telemetry.unit_argument_style}; "
                    f"protocol={device.protocol}"
                ),
                response_time_ms=int((perf_counter() - started_at) * 1000),
                retries=_get_retry_count(device),
                last_error=None,
                poll_kind=poll_kind,
            ),
            telemetry=_build_telemetry_points(inverter_model, values, device=device),
        )
    except ConnectionError:
        return _build_fallback_entry(
            response_time_ms=int((perf_counter() - started_at) * 1000),
            last_poll_status=(
                f"stub_mode=false; stage=connect; poll_kind={poll_kind}; protocol={device.protocol}"
            ),
            last_error=_connect_error_message(device.protocol),
            retries=_get_retry_count(device),
            poll_kind=poll_kind,
        )
    except NotImplementedError as exc:
        return _build_fallback_entry(
            response_time_ms=int((perf_counter() - started_at) * 1000),
            last_poll_status=(
                f"stub_mode=false; stage=driver; poll_kind={poll_kind}; protocol={device.protocol}"
            ),
            last_error=str(exc),
            retries=_get_retry_count(device),
            poll_kind=poll_kind,
        )
    except ValueError as exc:
        stage = _classify_poll_stage(str(exc))
        return _build_fallback_entry(
            response_time_ms=int((perf_counter() - started_at) * 1000),
            last_poll_status=(
                f"stub_mode=false; stage={stage}; poll_kind={poll_kind}; protocol={device.protocol}"
            ),
            last_error=str(exc),
            retries=_get_retry_count(device),
            poll_kind=poll_kind,
        )
    except Exception as exc:
        logger.warning("Polling exception for device %s: %s", device.device_id, str(exc))
        return _build_fallback_entry(
            response_time_ms=int((perf_counter() - started_at) * 1000),
            last_poll_status=(
                f"stub_mode=false; stage=exception; poll_kind={poll_kind}; protocol={device.protocol}"
            ),
            last_error=str(exc),
            retries=_get_retry_count(device),
            poll_kind=poll_kind,
        )


def poll_modbus_tcp_device(device: DeviceResponse) -> LiveCacheEntry | None:
    if device.protocol != "modbus_tcp":
        return None
    return poll_device_with_runtime(device)


def poll_modbus_rtu_device(device: DeviceResponse) -> LiveCacheEntry | None:
    if device.protocol != "modbus_rtu":
        return None
    return poll_device_with_runtime(device)


def poll_sunspec_device(device: DeviceResponse) -> LiveCacheEntry | None:
    if device.protocol != "sunspec":
        return None
    return poll_device_with_runtime(device)


def poll_aurora_device(device: DeviceResponse) -> LiveCacheEntry | None:
    if device.protocol != "aurora":
        return None
    return poll_device_with_runtime(device)


def poll_device_with_runtime(
    device: DeviceResponse,
    *,
    poll_kind: str = "full",
    now: float | None = None,
) -> LiveCacheEntry | None:
    current_time = monotonic() if now is None else now
    backoff_decision = endpoint_runtime_service.get_backoff_decision(device, now=current_time)
    if backoff_decision.active:
        endpoint_runtime_service.record_backoff_skip(device, now=current_time)
        return _build_endpoint_backoff_entry(device, backoff_decision, poll_kind=poll_kind)

    entry = poll_device(device, poll_kind=poll_kind)
    if entry is not None:
        endpoint_runtime_service.record_poll_result(device, entry, now=current_time)
    return entry


class PollingEngine:
    def __init__(self) -> None:
        self._thread: Thread | None = None
        self._lock = Lock()
        self._stop_event = Event()
        self._should_run = False
        self._thread_start_count = 0
        self._last_thread_started_at: str | None = None
        self._last_loop_error: str | None = None
        self._last_loop_error_at: str | None = None
        self._consecutive_loop_error_count = 0
        self._next_poll_at: dict[str, float] = {}
        self._next_heartbeat_poll_at: dict[str, float] = {}
        self._tcp_full_cursor_by_endpoint: dict[str, int] = {}
        self._tcp_light_cursor_by_endpoint: dict[str, int] = {}
        self._shared_non_serial_endpoint_counts: dict[str, int] = {}
        self._shared_tcp_endpoint_runtime: dict[str, _SerialEndpointRuntimeState] = {}
        self._tcp_slow_full_due_by_endpoint: dict[str, float] = {}
        self._serial_full_cursor_by_endpoint: dict[str, int] = {}
        self._serial_heartbeat_cursor_by_endpoint: dict[str, int] = {}
        self._startup_priority_sweep_pending = True
        self._last_cycle_started_at: str | None = None
        self._last_cycle_completed_at: str | None = None
        self._last_cycle_duration_ms: int | None = None
        self._last_due_device_count = 0
        self._last_polled_device_count = 0
        self._last_success_count = 0
        self._last_error_count = 0
        self._last_pollable_device_count = 0
        self._last_endpoint_group_count = 0
        self._last_skipped_device_count = 0
        self._serial_endpoint_runtime: dict[str, _SerialEndpointRuntimeState] = {}
        self._next_loop_wait_seconds = POLLING_ENGINE_IDLE_WAIT_SECONDS

    def get_runtime_snapshot(self) -> dict[str, str | int | float | bool | None]:
        self.ensure_running()
        with self._lock:
            scheduled_device_ids = set(self._next_poll_at) | set(self._next_heartbeat_poll_at)
            current_time = monotonic()
            next_due_seconds = [
                max(0.0, due_at - current_time) for due_at in self._next_poll_at.values()
            ]
            return {
                "enabled": self._should_run,
                "running": self._thread is not None and self._thread.is_alive(),
                "thread_start_count": self._thread_start_count,
                "last_thread_started_at": self._last_thread_started_at,
                "last_loop_error": self._last_loop_error,
                "last_loop_error_at": self._last_loop_error_at,
                "consecutive_loop_error_count": self._consecutive_loop_error_count,
                "scheduled_device_count": len(scheduled_device_ids),
                "pollable_device_count": self._last_pollable_device_count,
                "last_cycle_started_at": self._last_cycle_started_at,
                "last_cycle_completed_at": self._last_cycle_completed_at,
                "last_cycle_duration_ms": self._last_cycle_duration_ms,
                "last_due_device_count": self._last_due_device_count,
                "last_polled_device_count": self._last_polled_device_count,
                "last_success_count": self._last_success_count,
                "last_error_count": self._last_error_count,
                "last_endpoint_group_count": self._last_endpoint_group_count,
                "last_skipped_device_count": self._last_skipped_device_count,
                "next_full_poll_due_in_seconds_min": (
                    round(min(next_due_seconds), 3) if next_due_seconds else None
                ),
                "next_full_poll_due_in_seconds_max": (
                    round(max(next_due_seconds), 3) if next_due_seconds else None
                ),
            }

    def request_device_full_poll(self, device_id: str, *, delay_seconds: float = 0.0) -> None:
        due_at = monotonic() + max(0.0, float(delay_seconds))
        with self._lock:
            current_due_at = self._next_poll_at.get(device_id)
            if current_due_at is None or due_at < current_due_at:
                self._next_poll_at[device_id] = due_at

    def run_on_demand_read_cycle(
        self,
        devices: list[DeviceResponse],
        *,
        poll_kind: str = "full",
    ) -> dict[str, int]:
        selected_devices = [
            device for device in devices if device.protocol in SUPPORTED_POLL_PROTOCOLS
        ]
        if not selected_devices:
            return {
                "polled_device_count": 0,
                "success_count": 0,
                "error_count": 0,
                "skipped_device_count": 0,
                "endpoint_group_count": 0,
            }

        endpoint_groups = self._group_due_devices_by_endpoint(selected_devices)
        polled_count = 0
        success_count = 0
        error_count = 0
        skipped_count = 0
        max_workers = min(MAX_PARALLEL_POLL_WORKERS, len(endpoint_groups))
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="pv-edge-readback") as executor:
            future_to_group = {
                executor.submit(
                    self._poll_on_demand_endpoint_group,
                    endpoint_devices,
                    poll_kind=poll_kind,
                ): endpoint_devices
                for endpoint_devices in endpoint_groups
            }
            for future in as_completed(future_to_group):
                for result in future.result():
                    polled_count += 1
                    success_delta, error_delta, skipped_delta = self._store_polled_entry(
                        result.device,
                        result.entry,
                        allow_active_power_history=(poll_kind == "active_power"),
                    )
                    success_count += success_delta
                    error_count += error_delta
                    skipped_count += skipped_delta

        return {
            "polled_device_count": polled_count,
            "success_count": success_count,
            "error_count": error_count,
            "skipped_device_count": skipped_count,
            "endpoint_group_count": len(endpoint_groups),
        }

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                self._should_run = True
                return
            self._should_run = True
            self._stop_event.clear()
            self._next_poll_at = {}
            self._next_heartbeat_poll_at = {}
            self._tcp_full_cursor_by_endpoint = {}
            self._tcp_light_cursor_by_endpoint = {}
            self._shared_non_serial_endpoint_counts = {}
            self._shared_tcp_endpoint_runtime = {}
            self._tcp_slow_full_due_by_endpoint = {}
            self._serial_full_cursor_by_endpoint = {}
            self._serial_heartbeat_cursor_by_endpoint = {}
            self._serial_endpoint_runtime = {}
            self._startup_priority_sweep_pending = True
            self._last_loop_error = None
            self._last_loop_error_at = None
            self._consecutive_loop_error_count = 0
            self._start_thread_locked()

    def ensure_running(self) -> bool:
        with self._lock:
            if not self._should_run:
                return False
            if self._thread is not None and self._thread.is_alive():
                return False
            logger.warning("Polling engine thread is not alive; restarting it")
            self._start_thread_locked()
            return True

    def _start_thread_locked(self) -> None:
        self._stop_event.clear()
        self._thread = Thread(target=self._run, name="pv-edge-polling", daemon=True)
        self._thread.start()
        self._thread_start_count += 1
        self._last_thread_started_at = self._utc_now()

    def stop(self) -> None:
        with self._lock:
            self._should_run = False
            thread = self._thread
            self._thread = None
            self._stop_event.set()

        if thread is not None:
            thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll_devices()
            except Exception as exc:
                self._record_loop_exception(exc)
                logger.exception("Polling engine cycle failed: %s", exc)
                self._next_loop_wait_seconds = POLLING_ENGINE_ERROR_WAIT_SECONDS
            else:
                self._record_loop_success()
            self._stop_event.wait(self._next_loop_wait_seconds)

    def _poll_devices(self) -> None:
        cycle_started_at = datetime.now(UTC).isoformat()
        cycle_started_perf = perf_counter()
        devices = device_service.list_devices()
        polled_devices = [device for device in devices if device.protocol in SUPPORTED_POLL_PROTOCOLS]
        serial_devices = [
            device for device in polled_devices if self._uses_serial_like_endpoint(device)
        ]
        non_serial_devices = [
            device for device in polled_devices if not self._uses_serial_like_endpoint(device)
        ]
        active_device_ids = {
            device.device_id for device in polled_devices
        }
        active_tcp_endpoint_keys = {
            self._shared_endpoint_key_for_device(device)
            for device in non_serial_devices
            if self._uses_shared_non_serial_endpoint(device)
        }
        shared_non_serial_endpoint_counts = self._build_shared_non_serial_endpoint_counts(
            non_serial_devices,
        )
        self._shared_non_serial_endpoint_counts = shared_non_serial_endpoint_counts
        live_cache.prune(active_device_ids)
        endpoint_runtime_service.prune(polled_devices)
        self._next_poll_at = {
            device_id: due_at
            for device_id, due_at in self._next_poll_at.items()
            if device_id in active_device_ids
        }
        self._next_heartbeat_poll_at = {
            device_id: due_at
            for device_id, due_at in self._next_heartbeat_poll_at.items()
            if device_id in active_device_ids
        }
        self._tcp_full_cursor_by_endpoint = {
            endpoint_key: cursor
            for endpoint_key, cursor in self._tcp_full_cursor_by_endpoint.items()
            if endpoint_key in active_tcp_endpoint_keys
        }
        self._tcp_light_cursor_by_endpoint = {
            endpoint_key: cursor
            for endpoint_key, cursor in self._tcp_light_cursor_by_endpoint.items()
            if endpoint_key in active_tcp_endpoint_keys
        }
        with self._lock:
            self._shared_tcp_endpoint_runtime = {
                endpoint_key: state
                for endpoint_key, state in self._shared_tcp_endpoint_runtime.items()
                if endpoint_key in active_tcp_endpoint_keys
            }
        self._tcp_slow_full_due_by_endpoint = {
            endpoint_key: due_at
            for endpoint_key, due_at in self._tcp_slow_full_due_by_endpoint.items()
            if endpoint_key in active_tcp_endpoint_keys
        }
        active_serial_endpoint_keys = {
            self._serial_endpoint_key_for_device(device) for device in serial_devices
        }
        self._serial_full_cursor_by_endpoint = {
            endpoint_key: cursor
            for endpoint_key, cursor in self._serial_full_cursor_by_endpoint.items()
            if endpoint_key in active_serial_endpoint_keys
        }
        self._serial_heartbeat_cursor_by_endpoint = {
            endpoint_key: cursor
            for endpoint_key, cursor in self._serial_heartbeat_cursor_by_endpoint.items()
            if endpoint_key in active_serial_endpoint_keys
        }
        with self._lock:
            self._serial_endpoint_runtime = {
                endpoint_key: state
                for endpoint_key, state in self._serial_endpoint_runtime.items()
                if endpoint_key in active_serial_endpoint_keys
            }

        now = monotonic()
        self._seed_initial_schedule(polled_devices, now)
        due_devices = [
            device
            for device in non_serial_devices
            if self._non_serial_device_has_due_work(device, now)
        ]
        serial_endpoint_groups = self._group_due_serial_devices_by_endpoint(serial_devices, now)
        polled_count = 0
        success_count = 0
        error_count = 0
        skipped_count = 0
        due_device_count = len(due_devices) + sum(
            self._count_due_serial_devices(endpoint_devices, now)
            for endpoint_devices in serial_endpoint_groups
        )
        if due_device_count == 0:
            self._next_loop_wait_seconds = POLLING_ENGINE_IDLE_WAIT_SECONDS
            self._update_runtime_snapshot(
                cycle_started_at=cycle_started_at,
                cycle_duration_ms=int(round((perf_counter() - cycle_started_perf) * 1000)),
                due_device_count=0,
                polled_device_count=0,
                success_count=0,
                error_count=0,
                pollable_device_count=len(polled_devices),
                endpoint_group_count=0,
                skipped_device_count=0,
            )
            return

        endpoint_groups = self._group_due_devices_by_endpoint(due_devices)
        all_endpoint_groups = endpoint_groups + serial_endpoint_groups
        max_workers = min(MAX_PARALLEL_POLL_WORKERS, len(all_endpoint_groups))
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="pv-edge-poll") as executor:
            future_to_group = {
                executor.submit(self._poll_endpoint_group, endpoint_devices, current_time=now): endpoint_devices
                for endpoint_devices in all_endpoint_groups
            }
            for future in as_completed(future_to_group):
                for result in future.result():
                    device = result.device
                    entry = result.entry
                    polled_count += 1
                    success_delta, error_delta, skipped_delta = self._store_polled_entry(
                        device,
                        entry,
                    )
                    success_count += success_delta
                    error_count += error_delta
                    skipped_count += skipped_delta

                    if result.next_full_due_at is not None:
                        self._next_poll_at[device.device_id] = result.next_full_due_at
                    if result.next_heartbeat_due_at is not None:
                        self._next_heartbeat_poll_at[device.device_id] = result.next_heartbeat_due_at

        post_cycle_now = monotonic()
        non_serial_due_work_remaining = any(
            self._non_serial_device_has_due_work(device, post_cycle_now)
            for device in non_serial_devices
        )
        serial_due_work_remaining = any(
            self._serial_device_has_due_work(device, post_cycle_now) for device in serial_devices
        )
        self._next_loop_wait_seconds = (
            POLLING_ENGINE_BUSY_WAIT_SECONDS
            if serial_due_work_remaining or non_serial_due_work_remaining
            else POLLING_ENGINE_IDLE_WAIT_SECONDS
        )
        self._update_runtime_snapshot(
            cycle_started_at=cycle_started_at,
            cycle_duration_ms=int(round((perf_counter() - cycle_started_perf) * 1000)),
            due_device_count=due_device_count,
            polled_device_count=polled_count,
            success_count=success_count,
            error_count=error_count,
            pollable_device_count=len(polled_devices),
            endpoint_group_count=len(all_endpoint_groups),
            skipped_device_count=skipped_count,
        )

    def _seed_initial_schedule(self, devices: list[DeviceResponse], now: float) -> None:
        device_count = len(devices)
        if device_count == 0:
            return

        priority_sweep = self._startup_priority_sweep_pending
        non_serial_endpoint_counts = self._build_shared_non_serial_endpoint_counts(
            [device for device in devices if not self._uses_serial_like_endpoint(device)]
        )
        for index, device in enumerate(devices):
            if self._uses_serial_like_endpoint(device):
                if device.device_id not in self._next_heartbeat_poll_at:
                    self._next_heartbeat_poll_at[device.device_id] = now
                if device.device_id not in self._next_poll_at:
                    self._next_poll_at[device.device_id] = (
                        now + SERIAL_INITIAL_FULL_POLL_FALLBACK_SECONDS
                    )
                continue

            if self._uses_shared_modbus_tcp_gateway_polling(
                device,
                endpoint_counts=non_serial_endpoint_counts,
            ):
                if device.device_id not in self._next_heartbeat_poll_at:
                    self._next_heartbeat_poll_at[device.device_id] = now
                if device.device_id not in self._next_poll_at:
                    if priority_sweep:
                        self._next_poll_at[device.device_id] = now
                    else:
                        full_interval_seconds = self._shared_gateway_full_poll_interval_seconds(
                            device
                        )
                        offset_seconds = (full_interval_seconds * index) / device_count
                        self._next_poll_at[device.device_id] = now + offset_seconds
                continue

            if device.device_id in self._next_poll_at:
                continue

            if priority_sweep:
                self._next_poll_at[device.device_id] = now
                continue

            poll_interval_seconds = get_effective_poll_interval_seconds(device)
            offset_seconds = (poll_interval_seconds * index) / device_count
            self._next_poll_at[device.device_id] = now + offset_seconds

        if priority_sweep:
            self._startup_priority_sweep_pending = False

    def _group_due_serial_devices_by_endpoint(
        self,
        serial_devices: list[DeviceResponse],
        now: float,
    ) -> list[list[DeviceResponse]]:
        grouped: dict[tuple[str, str], list[DeviceResponse]] = {}
        for device in serial_devices:
            endpoint = build_poll_endpoint_key(device)
            group_key = endpoint if endpoint is not None else ("device", device.device_id)
            grouped.setdefault(group_key, []).append(device)

        due_groups: list[list[DeviceResponse]] = []
        for endpoint_devices in grouped.values():
            if not any(self._serial_device_has_due_work(device, now) for device in endpoint_devices):
                continue
            endpoint_port = self._serial_endpoint_port(endpoint_devices)
            if endpoint_port is not None and connection_manager.is_modbus_rtu_priority_pending(
                endpoint_port
            ):
                self._record_serial_endpoint_priority_deferral(endpoint_devices)
                continue
            due_groups.append(endpoint_devices)
        return due_groups

    def _serial_device_has_due_work(self, device: DeviceResponse, now: float) -> bool:
        return (
            now >= self._next_heartbeat_poll_at.get(device.device_id, _NO_DUE_AT)
            or now >= self._next_poll_at.get(device.device_id, _NO_DUE_AT)
        )

    def _count_due_serial_devices(self, endpoint_devices: list[DeviceResponse], now: float) -> int:
        return sum(1 for device in endpoint_devices if self._serial_device_has_due_work(device, now))

    def _non_serial_device_has_due_work(self, device: DeviceResponse, now: float) -> bool:
        if self._is_tcp_command_priority_pending_for_device(device):
            return False
        if now >= self._next_poll_at.get(device.device_id, _NO_DUE_AT):
            return True
        if self._uses_shared_modbus_tcp_gateway_polling(device):
            return now >= self._next_heartbeat_poll_at.get(device.device_id, _NO_DUE_AT)
        return False

    def _group_due_devices_by_endpoint(
        self,
        due_devices: list[DeviceResponse],
    ) -> list[list[DeviceResponse]]:
        grouped: dict[tuple[str, str], list[DeviceResponse]] = {}
        for device in due_devices:
            endpoint = build_poll_endpoint_key(device)
            group_key = endpoint if endpoint is not None else ("device", device.device_id)
            grouped.setdefault(group_key, []).append(device)
        return list(grouped.values())

    def _poll_endpoint_group(
        self,
        endpoint_devices: list[DeviceResponse],
        *,
        current_time: float,
    ) -> list[_EndpointPollResult]:
        if endpoint_devices and self._uses_serial_like_endpoint(endpoint_devices[0]):
            return self._poll_serial_endpoint_group(endpoint_devices, current_time=current_time)

        if self._uses_shared_non_serial_endpoint_group(endpoint_devices):
            return self._poll_shared_non_serial_endpoint_group(
                endpoint_devices,
                current_time=current_time,
            )

        results: list[_EndpointPollResult] = []
        for device in endpoint_devices:
            started_at = monotonic()
            entry = poll_device_with_runtime(device, now=started_at, poll_kind="full")
            completed_at = monotonic()
            results.append(
                _EndpointPollResult(
                    device=device,
                    entry=entry,
                    poll_kind="full",
                    next_full_due_at=self._resolve_next_full_due_at(
                        device=device,
                        completed_at=completed_at,
                    ),
                )
            )
        return results

    def _poll_shared_non_serial_endpoint_group(
        self,
        endpoint_devices: list[DeviceResponse],
        *,
        current_time: float,
    ) -> list[_EndpointPollResult]:
        if not self._uses_shared_modbus_tcp_gateway_polling_group(endpoint_devices):
            return self._poll_legacy_shared_non_serial_endpoint_group(
                endpoint_devices,
                current_time=current_time,
            )
        if self._is_tcp_command_priority_pending_for_group(endpoint_devices):
            self._record_shared_tcp_endpoint_priority_deferral(endpoint_devices)
            return []

        endpoint_key = self._shared_endpoint_key_for_group(endpoint_devices)
        plan = self._build_shared_tcp_gateway_endpoint_plan(
            endpoint_devices,
            current_time=current_time,
        )
        operations = plan.operations
        results: list[_EndpointPollResult] = []
        processed_full_devices: list[DeviceResponse] = []
        processed_light_devices: list[DeviceResponse] = []
        group_started_at = monotonic()
        group_started_at_iso = self._utc_now()

        for operation in operations:
            device = operation.device
            started_at = monotonic()
            entry = poll_device_with_runtime(
                device,
                now=started_at,
                poll_kind=operation.poll_kind,
            )
            completed_at = monotonic()
            lifecycle = live_cache.get_connection_lifecycle(device.device_id)
            results.append(
                _EndpointPollResult(
                    device=device,
                    entry=entry,
                    poll_kind=operation.poll_kind,
                    next_full_due_at=self._resolve_next_full_due_at(
                        device=device,
                        completed_at=completed_at,
                        poll_kind=operation.poll_kind,
                        entry=entry,
                        lifecycle=lifecycle,
                        shared_non_serial_endpoint=True,
                    ),
                    next_heartbeat_due_at=self._resolve_next_heartbeat_due_at(
                        device=device,
                        completed_at=completed_at,
                        shared_non_serial_endpoint=True,
                    ),
                )
            )
            if operation.poll_kind == "full":
                processed_full_devices.append(device)
            else:
                processed_light_devices.append(device)
            if self._shared_endpoint_cycle_budget_exhausted(
                endpoint_devices=endpoint_devices,
                group_started_at=group_started_at,
            ):
                break

        self._advance_shared_cursor(
            cursor_map=self._tcp_full_cursor_by_endpoint,
            endpoint_key=endpoint_key,
            endpoint_devices=endpoint_devices,
            selected_devices=processed_full_devices,
        )
        self._advance_shared_cursor(
            cursor_map=self._tcp_light_cursor_by_endpoint,
            endpoint_key=endpoint_key,
            endpoint_devices=endpoint_devices,
            selected_devices=processed_light_devices,
        )
        self._record_shared_tcp_endpoint_cycle(
            endpoint_devices=endpoint_devices,
            plan=plan,
            results=results,
            cycle_started_at=group_started_at,
            cycle_started_at_iso=group_started_at_iso,
            preempted_by_priority=False,
        )
        return results

    def _poll_legacy_shared_non_serial_endpoint_group(
        self,
        endpoint_devices: list[DeviceResponse],
        *,
        current_time: float,
    ) -> list[_EndpointPollResult]:
        _ = current_time
        endpoint_key = self._shared_endpoint_key_for_group(endpoint_devices)
        cursor = self._tcp_full_cursor_by_endpoint.get(endpoint_key, 0)
        ordered_devices = self._rotate_shared_endpoint_devices(endpoint_devices, cursor)
        results: list[_EndpointPollResult] = []
        processed_devices: list[DeviceResponse] = []
        group_started_at = monotonic()

        for device in ordered_devices:
            started_at = monotonic()
            entry = poll_device_with_runtime(device, now=started_at, poll_kind="full")
            completed_at = monotonic()
            results.append(
                _EndpointPollResult(
                    device=device,
                    entry=entry,
                    poll_kind="full",
                    next_full_due_at=self._resolve_next_full_due_at(
                        device=device,
                        completed_at=completed_at,
                    ),
                )
            )
            processed_devices.append(device)
            if self._shared_endpoint_cycle_budget_exhausted(
                endpoint_devices=endpoint_devices,
                group_started_at=group_started_at,
            ):
                break

        self._advance_shared_cursor(
            cursor_map=self._tcp_full_cursor_by_endpoint,
            endpoint_key=endpoint_key,
            endpoint_devices=endpoint_devices,
            selected_devices=processed_devices,
        )
        return results

    def _build_shared_tcp_gateway_endpoint_operations(
        self,
        endpoint_devices: list[DeviceResponse],
        *,
        current_time: float,
    ) -> list[_SerialEndpointOperation]:
        return self._build_shared_tcp_gateway_endpoint_plan(
            endpoint_devices,
            current_time=current_time,
        ).operations

    def _build_shared_tcp_gateway_endpoint_plan(
        self,
        endpoint_devices: list[DeviceResponse],
        *,
        current_time: float,
    ) -> _SerialEndpointPlan:
        endpoint_key = self._shared_endpoint_key_for_group(endpoint_devices)
        light_candidates = self._ordered_shared_tcp_light_candidates(
            endpoint_key=endpoint_key,
            endpoint_devices=endpoint_devices,
            current_time=current_time,
        )
        full_candidates = self._ordered_shared_tcp_full_candidates(
            endpoint_key=endpoint_key,
            endpoint_devices=endpoint_devices,
            current_time=current_time,
        )
        light_budget = min(
            len(light_candidates),
            TCP_SHARED_MAX_ACTIVE_POWER_BUDGET_PER_ENDPOINT_CYCLE,
        )
        slow_gateway = self._is_slow_shared_tcp_gateway(endpoint_devices)
        if slow_gateway:
            light_budget = min(
                light_budget,
                max(
                    TCP_SHARED_ACTIVE_POWER_BURST_BEFORE_FULL + 1,
                    min(8, ceil(len(endpoint_devices) / 4)),
                ),
            )
        full_budget = (
            len(full_candidates)
            if not light_candidates
            else min(
                len(full_candidates),
                TCP_SHARED_MAX_FULL_READ_BUDGET_PER_ENDPOINT_CYCLE,
            )
        )
        if slow_gateway and light_candidates and full_budget > 0:
            next_full_due = self._tcp_slow_full_due_by_endpoint.get(endpoint_key, 0.0)
            if current_time < next_full_due:
                full_budget = 0
        selected_fulls = full_candidates[:full_budget]
        if slow_gateway and selected_fulls:
            self._tcp_slow_full_due_by_endpoint[endpoint_key] = (
                current_time + TCP_SHARED_SLOW_FULL_READ_INTERVAL_SECONDS
            )
        selected_full_ids = {device.device_id for device in selected_fulls}
        selected_lights = [
            device for device in light_candidates if device.device_id not in selected_full_ids
        ][:light_budget]

        operations = [
            _SerialEndpointOperation(device=device, poll_kind="active_power")
            for device in selected_lights[:TCP_SHARED_ACTIVE_POWER_BURST_BEFORE_FULL]
        ]
        operations.extend(
            _SerialEndpointOperation(device=device, poll_kind="full")
            for device in selected_fulls
        )
        operations.extend(
            _SerialEndpointOperation(device=device, poll_kind="active_power")
            for device in selected_lights[TCP_SHARED_ACTIVE_POWER_BURST_BEFORE_FULL:]
        )
        return _SerialEndpointPlan(
            operations=operations,
            queued_full_due_count=len(full_candidates),
            queued_heartbeat_due_count=len(light_candidates),
            planned_full_count=len(selected_fulls),
            planned_heartbeat_count=len(selected_lights),
        )

    def _ordered_shared_tcp_light_candidates(
        self,
        *,
        endpoint_key: str,
        endpoint_devices: list[DeviceResponse],
        current_time: float,
    ) -> list[DeviceResponse]:
        rotated_devices = self._rotate_shared_endpoint_devices(
            endpoint_devices,
            self._tcp_light_cursor_by_endpoint.get(endpoint_key, 0),
        )
        candidates: list[DeviceResponse] = []
        for device in rotated_devices:
            heartbeat_due_at = self._next_heartbeat_poll_at.get(device.device_id, _NO_DUE_AT)
            if current_time < heartbeat_due_at:
                continue
            candidates.append(device)
        return candidates

    def _ordered_shared_tcp_full_candidates(
        self,
        *,
        endpoint_key: str,
        endpoint_devices: list[DeviceResponse],
        current_time: float,
    ) -> list[DeviceResponse]:
        rotated_devices = self._rotate_shared_endpoint_devices(
            endpoint_devices,
            self._tcp_full_cursor_by_endpoint.get(endpoint_key, 0),
        )
        unseen_devices: list[DeviceResponse] = []
        seen_devices: list[DeviceResponse] = []
        for device in rotated_devices:
            full_due_at = self._next_poll_at.get(device.device_id, 0.0)
            if current_time < full_due_at:
                continue
            lifecycle = live_cache.get_connection_lifecycle(device.device_id)
            if lifecycle.has_seen_full_success:
                seen_devices.append(device)
            else:
                unseen_devices.append(device)
        return unseen_devices + seen_devices

    def _poll_serial_endpoint_group(
        self,
        endpoint_devices: list[DeviceResponse],
        *,
        current_time: float,
    ) -> list[_EndpointPollResult]:
        plan = self._build_serial_endpoint_plan(endpoint_devices, current_time=current_time)
        operations = plan.operations
        results: list[_EndpointPollResult] = []
        group_started_at = monotonic()
        group_started_at_iso = self._utc_now()
        preempted_by_priority = False
        for operation in operations:
            endpoint_port = self._serial_endpoint_port(endpoint_devices)
            if endpoint_port is not None and connection_manager.is_modbus_rtu_priority_pending(
                endpoint_port
            ):
                preempted_by_priority = True
                self._record_serial_endpoint_priority_deferral(endpoint_devices)
                break
            device = operation.device
            started_at = monotonic()
            entry = poll_device_with_runtime(device, now=started_at, poll_kind=operation.poll_kind)
            completed_at = monotonic()
            lifecycle = live_cache.get_connection_lifecycle(device.device_id)
            results.append(
                _EndpointPollResult(
                    device=device,
                    entry=entry,
                    poll_kind=operation.poll_kind,
                    next_full_due_at=self._resolve_next_full_due_at(
                        device=device,
                        completed_at=completed_at,
                        poll_kind=operation.poll_kind,
                        entry=entry,
                        lifecycle=lifecycle,
                    ),
                    next_heartbeat_due_at=self._resolve_next_heartbeat_due_at(
                        device=device,
                        completed_at=completed_at,
                    ),
                )
            )
            if self._serial_endpoint_cycle_budget_exhausted(
                endpoint_devices=endpoint_devices,
                group_started_at=group_started_at,
            ):
                break
        self._record_serial_endpoint_cycle(
            endpoint_devices=endpoint_devices,
            plan=plan,
            results=results,
            cycle_started_at=group_started_at,
            cycle_started_at_iso=group_started_at_iso,
            preempted_by_priority=preempted_by_priority,
        )
        return results

    def _poll_on_demand_endpoint_group(
        self,
        endpoint_devices: list[DeviceResponse],
        *,
        poll_kind: str,
    ) -> list[_EndpointPollResult]:
        results: list[_EndpointPollResult] = []
        for device in endpoint_devices:
            started_at = monotonic()
            entry = poll_device_with_runtime(device, now=started_at, poll_kind=poll_kind)
            results.append(
                _EndpointPollResult(
                    device=device,
                    entry=entry,
                    poll_kind=poll_kind,
                )
            )
        return results

    def _build_serial_endpoint_plan(
        self,
        endpoint_devices: list[DeviceResponse],
        *,
        current_time: float,
    ) -> _SerialEndpointPlan:
        endpoint_key = self._serial_endpoint_key_for_group(endpoint_devices)
        heartbeat_candidates = self._ordered_serial_heartbeat_candidates(
            endpoint_key=endpoint_key,
            endpoint_devices=endpoint_devices,
            current_time=current_time,
        )
        full_candidates = self._ordered_serial_full_candidates(
            endpoint_key=endpoint_key,
            endpoint_devices=endpoint_devices,
            current_time=current_time,
        )

        full_budget = self._resolve_serial_full_budget(endpoint_devices, full_candidates)
        heartbeat_budget = self._resolve_serial_heartbeat_budget(
            endpoint_devices=endpoint_devices,
            heartbeat_candidates=heartbeat_candidates,
            full_candidates=full_candidates,
            full_budget=full_budget,
        )

        selected_heartbeats = heartbeat_candidates[:heartbeat_budget]
        selected_fulls = full_candidates[:full_budget]
        self._advance_serial_cursor(
            cursor_map=self._serial_heartbeat_cursor_by_endpoint,
            endpoint_key=endpoint_key,
            endpoint_devices=endpoint_devices,
            selected_devices=selected_heartbeats,
        )
        self._advance_serial_cursor(
            cursor_map=self._serial_full_cursor_by_endpoint,
            endpoint_key=endpoint_key,
            endpoint_devices=endpoint_devices,
            selected_devices=selected_fulls,
        )
        return _SerialEndpointPlan(
            operations=self._interleave_serial_operations(selected_heartbeats, selected_fulls),
            queued_full_due_count=len(full_candidates),
            queued_heartbeat_due_count=len(heartbeat_candidates),
            planned_full_count=len(selected_fulls),
            planned_heartbeat_count=len(selected_heartbeats),
        )

    def _build_serial_endpoint_operations(
        self,
        endpoint_devices: list[DeviceResponse],
        *,
        current_time: float,
    ) -> list[_SerialEndpointOperation]:
        return self._build_serial_endpoint_plan(
            endpoint_devices,
            current_time=current_time,
        ).operations

    def _ordered_serial_heartbeat_candidates(
        self,
        *,
        endpoint_key: str,
        endpoint_devices: list[DeviceResponse],
        current_time: float,
    ) -> list[DeviceResponse]:
        rotated_devices = self._rotate_serial_endpoint_devices(
            endpoint_devices,
            self._serial_heartbeat_cursor_by_endpoint.get(endpoint_key, 0),
        )
        unseen_devices: list[DeviceResponse] = []
        seen_devices: list[DeviceResponse] = []
        for device in rotated_devices:
            full_due_at = self._next_poll_at.get(device.device_id, _NO_DUE_AT)
            heartbeat_due_at = self._next_heartbeat_poll_at.get(device.device_id, _NO_DUE_AT)
            if current_time >= full_due_at or current_time < heartbeat_due_at:
                continue
            lifecycle = live_cache.get_connection_lifecycle(device.device_id)
            if lifecycle.has_seen_success:
                seen_devices.append(device)
            else:
                unseen_devices.append(device)
        return unseen_devices + seen_devices

    def _ordered_serial_full_candidates(
        self,
        *,
        endpoint_key: str,
        endpoint_devices: list[DeviceResponse],
        current_time: float,
    ) -> list[DeviceResponse]:
        rotated_devices = self._rotate_serial_endpoint_devices(
            endpoint_devices,
            self._serial_full_cursor_by_endpoint.get(endpoint_key, 0),
        )
        unseen_devices: list[DeviceResponse] = []
        seen_devices: list[DeviceResponse] = []
        for device in rotated_devices:
            full_due_at = self._next_poll_at.get(device.device_id, _NO_DUE_AT)
            if current_time < full_due_at:
                continue
            lifecycle = live_cache.get_connection_lifecycle(device.device_id)
            if lifecycle.has_seen_full_success:
                seen_devices.append(device)
            else:
                unseen_devices.append(device)
        return unseen_devices + seen_devices

    def _resolve_serial_full_budget(
        self,
        endpoint_devices: list[DeviceResponse],
        full_candidates: list[DeviceResponse],
    ) -> int:
        if not full_candidates:
            return 0

        unseen_full_count = sum(
            1
            for device in full_candidates
            if not live_cache.get_connection_lifecycle(device.device_id).has_seen_full_success
        )
        if unseen_full_count > 0:
            bootstrap_budget = max(2, min(10, ceil(len(endpoint_devices) / 3)))
            return min(
                len(full_candidates),
                SERIAL_MAX_FULL_READ_BUDGET_PER_ENDPOINT_CYCLE,
                bootstrap_budget,
            )

        steady_budget = max(4, min(10, ceil(len(endpoint_devices) / 2)))
        return min(
            len(full_candidates),
            SERIAL_MAX_FULL_READ_BUDGET_PER_ENDPOINT_CYCLE,
            steady_budget,
        )

    def _resolve_serial_heartbeat_budget(
        self,
        *,
        endpoint_devices: list[DeviceResponse],
        heartbeat_candidates: list[DeviceResponse],
        full_candidates: list[DeviceResponse],
        full_budget: int,
    ) -> int:
        if not heartbeat_candidates:
            return 0

        unseen_contact_count = sum(
            1
            for device in heartbeat_candidates
            if not live_cache.get_connection_lifecycle(device.device_id).has_seen_success
        )
        if unseen_contact_count > 0:
            total_budget = min(
                SERIAL_MAX_OPERATIONS_PER_ENDPOINT_CYCLE,
                max(8, ceil(len(endpoint_devices) / 2)),
            )
            available_budget = max(1, total_budget - full_budget)
            heartbeat_budget = max(available_budget, unseen_contact_count)
            return min(
                len(heartbeat_candidates),
                SERIAL_MAX_HEARTBEAT_BUDGET_PER_ENDPOINT_CYCLE,
                heartbeat_budget,
                max(0, SERIAL_MAX_OPERATIONS_PER_ENDPOINT_CYCLE - full_budget),
            )

        # Once the line is stable, full telemetry should dominate and heartbeat becomes
        # a cheap background liveness check rather than the main consumer of bus time.
        if full_candidates:
            heartbeat_budget = min(
                len(heartbeat_candidates),
                max(1, min(2, ceil(len(endpoint_devices) / 40))),
            )
            return min(
                heartbeat_budget,
                SERIAL_MAX_HEARTBEAT_BUDGET_PER_ENDPOINT_CYCLE,
            )

        total_budget = min(
            SERIAL_MAX_OPERATIONS_PER_ENDPOINT_CYCLE,
            max(6, ceil(len(endpoint_devices) / 2)),
        )
        available_budget = max(1, total_budget - full_budget)
        heartbeat_budget = min(
            len(heartbeat_candidates),
            max(2, available_budget),
        )
        return min(
            heartbeat_budget,
            SERIAL_MAX_HEARTBEAT_BUDGET_PER_ENDPOINT_CYCLE,
        )

    def _interleave_serial_operations(
        self,
        heartbeat_devices: list[DeviceResponse],
        full_devices: list[DeviceResponse],
    ) -> list[_SerialEndpointOperation]:
        operations: list[_SerialEndpointOperation] = []
        heartbeat_index = 0
        full_index = 0
        while heartbeat_index < len(heartbeat_devices) or full_index < len(full_devices):
            if full_index < len(full_devices):
                operations.append(
                    _SerialEndpointOperation(device=full_devices[full_index], poll_kind="full")
                )
                full_index += 1
            if heartbeat_index < len(heartbeat_devices):
                heartbeat_device = heartbeat_devices[heartbeat_index]
                operations.append(
                    _SerialEndpointOperation(
                        device=heartbeat_device,
                        poll_kind=self._resolve_serial_light_poll_kind(heartbeat_device),
                    )
                )
                heartbeat_index += 1
        return operations

    def _resolve_serial_light_poll_kind(self, device: DeviceResponse) -> str:
        if device.protocol == "modbus_rtu" and device.transport == "tcp":
            return "active_power"
        return "heartbeat"

    def _serial_endpoint_key_for_device(self, device: DeviceResponse) -> str:
        endpoint = build_poll_endpoint_key(device)
        if endpoint is None:
            return f"device:{device.device_id}"
        return f"{endpoint[0]}:{endpoint[1]}"

    def _shared_endpoint_key_for_device(self, device: DeviceResponse) -> str:
        endpoint = build_poll_endpoint_key(device)
        if endpoint is None:
            return f"device:{device.device_id}"
        return f"{endpoint[0]}:{endpoint[1]}"

    def _shared_endpoint_key_for_group(self, endpoint_devices: list[DeviceResponse]) -> str:
        if not endpoint_devices:
            return "shared:empty"
        return self._shared_endpoint_key_for_device(endpoint_devices[0])

    def _serial_endpoint_key_for_group(self, endpoint_devices: list[DeviceResponse]) -> str:
        if not endpoint_devices:
            return "serial:empty"
        return self._serial_endpoint_key_for_device(endpoint_devices[0])

    def _serial_endpoint_port(self, endpoint_devices: list[DeviceResponse]) -> str | None:
        if not endpoint_devices:
            return None
        if endpoint_devices[0].transport != "serial":
            endpoint = build_poll_endpoint_key(endpoint_devices[0])
            if endpoint is None:
                return None
            return f"{endpoint[0]}:{endpoint[1]}"
        connection_settings = getattr(endpoint_devices[0], "connection_settings", {})
        if not isinstance(connection_settings, dict):
            return None
        port = connection_settings.get("port")
        return str(port).strip() if port not in {None, ""} else None

    def _rotate_serial_endpoint_devices(
        self,
        endpoint_devices: list[DeviceResponse],
        cursor: int,
    ) -> list[DeviceResponse]:
        if not endpoint_devices:
            return []
        if len(endpoint_devices) == 1:
            return list(endpoint_devices)

        start_index = cursor % len(endpoint_devices)
        return endpoint_devices[start_index:] + endpoint_devices[:start_index]

    def _rotate_shared_endpoint_devices(
        self,
        endpoint_devices: list[DeviceResponse],
        cursor: int,
    ) -> list[DeviceResponse]:
        if not endpoint_devices:
            return []
        if len(endpoint_devices) == 1:
            return list(endpoint_devices)

        start_index = cursor % len(endpoint_devices)
        return endpoint_devices[start_index:] + endpoint_devices[:start_index]

    def _advance_serial_cursor(
        self,
        *,
        cursor_map: dict[str, int],
        endpoint_key: str,
        endpoint_devices: list[DeviceResponse],
        selected_devices: list[DeviceResponse],
    ) -> None:
        if not endpoint_devices or not selected_devices:
            return

        device_index_map = {
            device.device_id: index for index, device in enumerate(endpoint_devices)
        }
        last_index = device_index_map.get(selected_devices[-1].device_id)
        if last_index is None:
            return
        cursor_map[endpoint_key] = (last_index + 1) % len(endpoint_devices)

    def _advance_shared_cursor(
        self,
        *,
        cursor_map: dict[str, int],
        endpoint_key: str,
        endpoint_devices: list[DeviceResponse],
        selected_devices: list[DeviceResponse],
    ) -> None:
        if not endpoint_devices or not selected_devices:
            return

        device_index_map = {
            device.device_id: index for index, device in enumerate(endpoint_devices)
        }
        last_index = device_index_map.get(selected_devices[-1].device_id)
        if last_index is None:
            return
        cursor_map[endpoint_key] = (last_index + 1) % len(endpoint_devices)

    def _serial_endpoint_cycle_budget_exhausted(
        self,
        *,
        endpoint_devices: list[DeviceResponse],
        group_started_at: float,
    ) -> bool:
        return monotonic() - group_started_at >= SERIAL_MAX_ENDPOINT_OCCUPANCY_SECONDS

    def _shared_endpoint_cycle_budget_exhausted(
        self,
        *,
        endpoint_devices: list[DeviceResponse],
        group_started_at: float,
    ) -> bool:
        _ = endpoint_devices
        return monotonic() - group_started_at >= TCP_SHARED_MAX_ENDPOINT_OCCUPANCY_SECONDS

    def _uses_serial_like_endpoint(self, device: DeviceResponse) -> bool:
        return uses_serial_like_polling(device)

    def _uses_shared_non_serial_endpoint(self, device: DeviceResponse) -> bool:
        return (
            not self._uses_serial_like_endpoint(device)
            and build_poll_endpoint_key(device) is not None
        )

    def _build_shared_non_serial_endpoint_counts(
        self,
        devices: list[DeviceResponse],
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for device in devices:
            if self._uses_serial_like_endpoint(device):
                continue
            endpoint = build_poll_endpoint_key(device)
            if endpoint is None:
                continue
            endpoint_key = f"{endpoint[0]}:{endpoint[1]}"
            counts[endpoint_key] = counts.get(endpoint_key, 0) + 1
        return counts

    def _uses_shared_modbus_tcp_gateway_polling(
        self,
        device: DeviceResponse,
        *,
        endpoint_counts: dict[str, int] | None = None,
    ) -> bool:
        if device.protocol != "modbus_tcp" or device.transport != "tcp":
            return False
        endpoint = build_poll_endpoint_key(device)
        if endpoint is None:
            return False
        endpoint_key = f"{endpoint[0]}:{endpoint[1]}"
        counts = endpoint_counts if endpoint_counts is not None else self._shared_non_serial_endpoint_counts
        return counts.get(endpoint_key, 0) > 1

    def _uses_shared_modbus_tcp_gateway_polling_group(
        self,
        endpoint_devices: list[DeviceResponse],
    ) -> bool:
        if not endpoint_devices:
            return False
        return self._uses_shared_modbus_tcp_gateway_polling(endpoint_devices[0]) or (
            len(endpoint_devices) > 1
            and endpoint_devices[0].protocol == "modbus_tcp"
            and endpoint_devices[0].transport == "tcp"
        )

    def _uses_shared_non_serial_endpoint_group(
        self,
        endpoint_devices: list[DeviceResponse],
    ) -> bool:
        if not endpoint_devices or self._uses_serial_like_endpoint(endpoint_devices[0]):
            return False
        endpoint_key = self._shared_endpoint_key_for_group(endpoint_devices)
        return (
            build_poll_endpoint_key(endpoint_devices[0]) is not None
            and (
                len(endpoint_devices) > 1
                or self._shared_non_serial_endpoint_counts.get(endpoint_key, 0) > 1
            )
        )

    def _tcp_priority_endpoint_for_device(self, device: DeviceResponse) -> tuple[str, int] | None:
        if device.transport != "tcp" or device.protocol not in {"modbus_tcp", "sunspec"}:
            return None
        settings = getattr(device, "connection_settings", {})
        if not isinstance(settings, dict):
            return None
        host = settings.get("host")
        port = settings.get("port")
        if host in {None, ""} or port in {None, ""}:
            return None
        try:
            normalized_host = str(host).strip()
            normalized_port = int(port)
        except (TypeError, ValueError):
            return None
        if not normalized_host:
            return None
        return normalized_host, normalized_port

    def _is_tcp_command_priority_pending_for_device(self, device: DeviceResponse) -> bool:
        endpoint = self._tcp_priority_endpoint_for_device(device)
        if endpoint is None:
            return False
        host, port = endpoint
        return connection_manager.is_modbus_tcp_priority_pending(host, port)

    def _is_tcp_command_priority_pending_for_group(
        self,
        endpoint_devices: list[DeviceResponse],
    ) -> bool:
        if not endpoint_devices:
            return False
        return self._is_tcp_command_priority_pending_for_device(endpoint_devices[0])

    def _shared_gateway_full_poll_interval_seconds(self, device: DeviceResponse) -> float:
        return max(
            TCP_SHARED_MIN_FULL_POLL_INTERVAL_SECONDS,
            get_effective_poll_interval_seconds(device) * 4.0,
        )

    def _is_slow_shared_tcp_gateway(self, endpoint_devices: list[DeviceResponse]) -> bool:
        if not endpoint_devices:
            return False
        endpoint = build_poll_endpoint_key(endpoint_devices[0])
        if endpoint is None:
            return False
        endpoint_type, endpoint_label = endpoint
        if endpoint_type != "tcp":
            return False
        for snapshot in connection_manager.get_modbus_tcp_runtime_snapshots():
            if snapshot.get("endpoint_type") != "tcp":
                continue
            if snapshot.get("endpoint_label") != endpoint_label:
                continue
            sample_count = int(snapshot.get("tcp_sample_count") or 0)
            if sample_count < 3:
                return False
            average_ms = snapshot.get("average_operation_duration_ms")
            if average_ms is None:
                average_ms = snapshot.get("last_operation_duration_ms")
            try:
                return float(average_ms or 0.0) >= TCP_SHARED_SLOW_OPERATION_THRESHOLD_MS
            except (TypeError, ValueError):
                return False
        return False

    def _resolve_shared_tcp_endpoint_identity(
        self,
        endpoint_devices: list[DeviceResponse],
    ) -> tuple[str, str]:
        if not endpoint_devices:
            return "tcp", "unknown"
        endpoint = build_poll_endpoint_key(endpoint_devices[0])
        if endpoint is None:
            return "tcp", self._shared_endpoint_key_for_group(endpoint_devices)
        return endpoint

    def _resolve_next_full_due_at(
        self,
        *,
        device: DeviceResponse,
        completed_at: float,
        poll_kind: str = "full",
        entry: LiveCacheEntry | None = None,
        lifecycle: object | None = None,
        shared_non_serial_endpoint: bool = False,
    ) -> float:
        backoff_decision = endpoint_runtime_service.get_backoff_decision(
            device,
            now=completed_at,
        )
        if backoff_decision.active:
            return completed_at + backoff_decision.remaining_backoff_seconds

        if shared_non_serial_endpoint:
            if poll_kind == "full":
                return completed_at + self._shared_gateway_full_poll_interval_seconds(device)
            shared_lifecycle = lifecycle or live_cache.get_connection_lifecycle(device.device_id)
            if (
                entry is not None
                and is_successful_real_poll(entry)
                and not shared_lifecycle.has_seen_full_success
            ):
                return completed_at
            return self._next_poll_at.get(device.device_id, _NO_DUE_AT)

        if not self._uses_serial_like_endpoint(device):
            return completed_at + get_effective_poll_interval_seconds(device)

        if poll_kind == "full":
            return completed_at + get_effective_full_poll_interval_seconds(device)

        serial_lifecycle = lifecycle or live_cache.get_connection_lifecycle(device.device_id)
        if (
            entry is not None
            and is_successful_real_poll(entry)
            and not serial_lifecycle.has_seen_full_success
        ):
            return completed_at
        return self._next_poll_at.get(device.device_id, _NO_DUE_AT)

    def _resolve_next_heartbeat_due_at(
        self,
        *,
        device: DeviceResponse,
        completed_at: float,
        shared_non_serial_endpoint: bool = False,
    ) -> float | None:
        if shared_non_serial_endpoint:
            heartbeat_interval_seconds = min(
                get_effective_heartbeat_interval_seconds(device),
                TCP_SHARED_FAST_ACTIVE_POWER_INTERVAL_SECONDS,
            )
            return completed_at + heartbeat_interval_seconds
        if not self._uses_serial_like_endpoint(device):
            return None
        heartbeat_interval_seconds = min(
            get_effective_heartbeat_interval_seconds(device),
            SERIAL_FAST_HEARTBEAT_INTERVAL_SECONDS,
        )
        return completed_at + heartbeat_interval_seconds

    def _update_runtime_snapshot(
        self,
        *,
        cycle_started_at: str,
        cycle_duration_ms: int,
        due_device_count: int,
        polled_device_count: int,
        success_count: int,
        error_count: int,
        pollable_device_count: int,
        endpoint_group_count: int,
        skipped_device_count: int,
    ) -> None:
        with self._lock:
            self._last_cycle_started_at = cycle_started_at
            self._last_cycle_completed_at = datetime.now(UTC).isoformat()
            self._last_cycle_duration_ms = cycle_duration_ms
            self._last_due_device_count = due_device_count
            self._last_polled_device_count = polled_device_count
            self._last_success_count = success_count
            self._last_error_count = error_count
            self._last_pollable_device_count = pollable_device_count
            self._last_endpoint_group_count = endpoint_group_count
            self._last_skipped_device_count = skipped_device_count

    def _record_loop_exception(self, exc: Exception) -> None:
        error_at = self._utc_now()
        with self._lock:
            self._last_loop_error = f"{exc.__class__.__name__}: {exc}"
            self._last_loop_error_at = error_at
            self._consecutive_loop_error_count += 1
            self._last_cycle_completed_at = error_at

    def _record_loop_success(self) -> None:
        with self._lock:
            self._consecutive_loop_error_count = 0

    def _record_serial_endpoint_priority_deferral(
        self,
        endpoint_devices: list[DeviceResponse],
    ) -> None:
        with self._lock:
            state = self._get_or_create_serial_endpoint_runtime_state_locked(endpoint_devices)
            state.priority_deferral_count += 1
            state.last_priority_at = self._utc_now()

    def _record_shared_tcp_endpoint_priority_deferral(
        self,
        endpoint_devices: list[DeviceResponse],
    ) -> None:
        with self._lock:
            state = self._get_or_create_shared_tcp_endpoint_runtime_state_locked(
                endpoint_devices
            )
            state.priority_deferral_count += 1
            state.last_priority_at = self._utc_now()

    def _record_serial_endpoint_cycle(
        self,
        *,
        endpoint_devices: list[DeviceResponse],
        plan: _SerialEndpointPlan,
        results: list[_EndpointPollResult],
        cycle_started_at: float,
        cycle_started_at_iso: str,
        preempted_by_priority: bool,
    ) -> None:
        completed_at_iso = self._utc_now()
        executed_full_count = sum(1 for result in results if result.poll_kind == "full")
        executed_heartbeat_count = sum(
            1 for result in results if result.poll_kind in {"heartbeat", "active_power"}
        )
        operation_durations = [
            float(result.entry.diagnostics.response_time_ms)
            for result in results
            if result.entry is not None
        ]
        cycle_duration_ms = int(round((monotonic() - cycle_started_at) * 1000))
        with self._lock:
            state = self._get_or_create_serial_endpoint_runtime_state_locked(endpoint_devices)
            state.queued_full_due_count = plan.queued_full_due_count
            state.queued_heartbeat_due_count = plan.queued_heartbeat_due_count
            state.planned_full_count = plan.planned_full_count
            state.planned_heartbeat_count = plan.planned_heartbeat_count
            state.executed_full_count = executed_full_count
            state.executed_heartbeat_count = executed_heartbeat_count
            state.last_cycle_started_at = cycle_started_at_iso
            state.last_cycle_completed_at = completed_at_iso
            state.last_cycle_duration_ms = cycle_duration_ms
            state.cycle_count += 1
            state.average_cycle_duration_ms = self._blend_average(
                state.average_cycle_duration_ms,
                cycle_duration_ms,
                state.cycle_count,
            )
            if operation_durations:
                state.average_operation_duration_ms = self._blend_average(
                    state.average_operation_duration_ms,
                    sum(operation_durations) / len(operation_durations),
                    state.cycle_count,
                )
            if preempted_by_priority:
                state.last_priority_at = completed_at_iso

    def _record_shared_tcp_endpoint_cycle(
        self,
        *,
        endpoint_devices: list[DeviceResponse],
        plan: _SerialEndpointPlan,
        results: list[_EndpointPollResult],
        cycle_started_at: float,
        cycle_started_at_iso: str,
        preempted_by_priority: bool,
    ) -> None:
        completed_at_iso = self._utc_now()
        executed_full_count = sum(1 for result in results if result.poll_kind == "full")
        executed_heartbeat_count = sum(
            1 for result in results if result.poll_kind == "active_power"
        )
        operation_durations = [
            float(result.entry.diagnostics.response_time_ms)
            for result in results
            if result.entry is not None
        ]
        cycle_duration_ms = int(round((monotonic() - cycle_started_at) * 1000))
        with self._lock:
            state = self._get_or_create_shared_tcp_endpoint_runtime_state_locked(
                endpoint_devices
            )
            state.queued_full_due_count = plan.queued_full_due_count
            state.queued_heartbeat_due_count = plan.queued_heartbeat_due_count
            state.planned_full_count = plan.planned_full_count
            state.planned_heartbeat_count = plan.planned_heartbeat_count
            state.executed_full_count = executed_full_count
            state.executed_heartbeat_count = executed_heartbeat_count
            state.last_cycle_started_at = cycle_started_at_iso
            state.last_cycle_completed_at = completed_at_iso
            state.last_cycle_duration_ms = cycle_duration_ms
            state.cycle_count += 1
            state.average_cycle_duration_ms = self._blend_average(
                state.average_cycle_duration_ms,
                cycle_duration_ms,
                state.cycle_count,
            )
            if operation_durations:
                state.average_operation_duration_ms = self._blend_average(
                    state.average_operation_duration_ms,
                    sum(operation_durations) / len(operation_durations),
                    state.cycle_count,
                )
            if preempted_by_priority:
                state.last_priority_at = completed_at_iso

    def get_serial_endpoint_snapshots(
        self,
        devices: list[DeviceResponse],
    ) -> list[dict[str, object]]:
        grouped: dict[str, list[DeviceResponse]] = {}
        for device in devices:
            if not self._uses_serial_like_endpoint(device):
                continue
            endpoint_key = self._serial_endpoint_key_for_device(device)
            grouped.setdefault(endpoint_key, []).append(device)

        snapshots: list[dict[str, object]] = []
        for endpoint_key, endpoint_devices in grouped.items():
            endpoint_type, endpoint_label = self._resolve_serial_endpoint_identity(endpoint_devices)
            with self._lock:
                state = self._serial_endpoint_runtime.get(endpoint_key)
                snapshots.append(
                    {
                        "endpoint_type": endpoint_type,
                        "endpoint_label": endpoint_label,
                        "queued_full_due_count": state.queued_full_due_count if state else 0,
                        "queued_heartbeat_due_count": (
                            state.queued_heartbeat_due_count if state else 0
                        ),
                        "planned_full_count": state.planned_full_count if state else 0,
                        "planned_heartbeat_count": state.planned_heartbeat_count if state else 0,
                        "executed_full_count": state.executed_full_count if state else 0,
                        "executed_heartbeat_count": (
                            state.executed_heartbeat_count if state else 0
                        ),
                        "priority_deferral_count": state.priority_deferral_count if state else 0,
                        "last_priority_at": state.last_priority_at if state else None,
                        "last_cycle_started_at": state.last_cycle_started_at if state else None,
                        "last_cycle_completed_at": state.last_cycle_completed_at if state else None,
                        "last_cycle_duration_ms": state.last_cycle_duration_ms if state else None,
                        "average_cycle_duration_ms": (
                            state.average_cycle_duration_ms if state else None
                        ),
                        "average_operation_duration_ms": (
                            state.average_operation_duration_ms if state else None
                        ),
                    }
                )

        snapshots.sort(
            key=lambda item: (
                -int(item["priority_deferral_count"]),
                -(int(item["queued_full_due_count"]) + int(item["queued_heartbeat_due_count"])),
                str(item["endpoint_label"]).lower(),
            )
        )
        return snapshots

    def get_shared_tcp_endpoint_snapshots(
        self,
        devices: list[DeviceResponse],
    ) -> list[dict[str, object]]:
        grouped: dict[str, list[DeviceResponse]] = {}
        endpoint_counts = self._build_shared_non_serial_endpoint_counts(
            [device for device in devices if not self._uses_serial_like_endpoint(device)]
        )
        for device in devices:
            if not self._uses_shared_modbus_tcp_gateway_polling(
                device,
                endpoint_counts=endpoint_counts,
            ):
                continue
            endpoint_key = self._shared_endpoint_key_for_device(device)
            grouped.setdefault(endpoint_key, []).append(device)

        snapshots: list[dict[str, object]] = []
        for endpoint_key, endpoint_devices in grouped.items():
            endpoint_type, endpoint_label = self._resolve_shared_tcp_endpoint_identity(
                endpoint_devices
            )
            with self._lock:
                state = self._shared_tcp_endpoint_runtime.get(endpoint_key)
                snapshots.append(
                    {
                        "endpoint_type": endpoint_type,
                        "endpoint_label": endpoint_label,
                        "queued_full_due_count": state.queued_full_due_count if state else 0,
                        "queued_heartbeat_due_count": (
                            state.queued_heartbeat_due_count if state else 0
                        ),
                        "planned_full_count": state.planned_full_count if state else 0,
                        "planned_heartbeat_count": state.planned_heartbeat_count if state else 0,
                        "executed_full_count": state.executed_full_count if state else 0,
                        "executed_heartbeat_count": (
                            state.executed_heartbeat_count if state else 0
                        ),
                        "priority_deferral_count": state.priority_deferral_count if state else 0,
                        "last_priority_at": state.last_priority_at if state else None,
                        "last_cycle_started_at": state.last_cycle_started_at if state else None,
                        "last_cycle_completed_at": state.last_cycle_completed_at if state else None,
                        "last_cycle_duration_ms": state.last_cycle_duration_ms if state else None,
                        "average_cycle_duration_ms": (
                            state.average_cycle_duration_ms if state else None
                        ),
                        "average_operation_duration_ms": (
                            state.average_operation_duration_ms if state else None
                        ),
                    }
                )

        snapshots.sort(
            key=lambda item: (
                -int(item["priority_deferral_count"]),
                -(int(item["queued_full_due_count"]) + int(item["queued_heartbeat_due_count"])),
                str(item["endpoint_label"]).lower(),
            )
        )
        return snapshots

    def _get_or_create_serial_endpoint_runtime_state(
        self,
        endpoint_devices: list[DeviceResponse],
    ) -> _SerialEndpointRuntimeState:
        with self._lock:
            return self._get_or_create_serial_endpoint_runtime_state_locked(endpoint_devices)

    def _get_or_create_serial_endpoint_runtime_state_locked(
        self,
        endpoint_devices: list[DeviceResponse],
    ) -> _SerialEndpointRuntimeState:
        endpoint_key = self._serial_endpoint_key_for_group(endpoint_devices)
        state = self._serial_endpoint_runtime.get(endpoint_key)
        if state is None:
            endpoint_type, endpoint_label = self._resolve_serial_endpoint_identity(endpoint_devices)
            state = _SerialEndpointRuntimeState(
                endpoint_type=endpoint_type,
                endpoint_label=endpoint_label,
            )
            self._serial_endpoint_runtime[endpoint_key] = state
        return state

    def _get_or_create_shared_tcp_endpoint_runtime_state_locked(
        self,
        endpoint_devices: list[DeviceResponse],
    ) -> _SerialEndpointRuntimeState:
        endpoint_key = self._shared_endpoint_key_for_group(endpoint_devices)
        state = self._shared_tcp_endpoint_runtime.get(endpoint_key)
        if state is None:
            endpoint_type, endpoint_label = self._resolve_shared_tcp_endpoint_identity(
                endpoint_devices
            )
            state = _SerialEndpointRuntimeState(
                endpoint_type=endpoint_type,
                endpoint_label=endpoint_label,
            )
            self._shared_tcp_endpoint_runtime[endpoint_key] = state
        return state

    def _store_polled_entry(
        self,
        device: DeviceResponse,
        entry: LiveCacheEntry | None,
        *,
        allow_active_power_history: bool = False,
    ) -> tuple[int, int, int]:
        if entry is None:
            return 0, 1, 0

        previous_entry = live_cache.get(device.device_id)
        cached_entry = _merge_poll_entry(previous_entry, entry)
        live_cache.set(device.device_id, cached_entry)

        if _is_endpoint_backoff_entry(entry):
            return 0, 1, 1

        if not is_successful_real_poll(cached_entry):
            return 0, 1, 0

        is_full_history_sample = is_successful_full_poll(cached_entry)
        is_active_power_history_sample = _is_successful_active_power_poll(cached_entry)
        should_append_live_power_history = is_full_history_sample or is_active_power_history_sample
        should_append_persistent_power_history = is_full_history_sample or (
            allow_active_power_history and is_active_power_history_sample
        )
        if should_append_live_power_history or should_append_persistent_power_history:
            history_power_kw = sanitize_device_power_kw(
                cached_entry.metrics.power_kw,
                device=device,
                telemetry=cached_entry.telemetry,
            )
            if history_power_kw is not None:
                if should_append_live_power_history:
                    live_cache.append_power_sample(
                        device_id=device.device_id,
                        timestamp=cached_entry.timestamp,
                        power_kw=history_power_kw,
                    )
                if should_append_persistent_power_history:
                    power_history_service.append_sample(
                        device_id=device.device_id,
                        timestamp=cached_entry.timestamp,
                        power_kw=history_power_kw,
                    )

        return 1, 0, 0

    def _resolve_serial_endpoint_identity(
        self,
        endpoint_devices: list[DeviceResponse],
    ) -> tuple[str, str]:
        if not endpoint_devices:
            return "serial", "serial:empty"
        endpoint = build_poll_endpoint_key(endpoint_devices[0])
        if endpoint is None:
            return "serial", endpoint_devices[0].device_id
        return endpoint

    def _blend_average(
        self,
        current_average: float | None,
        new_value: float,
        sample_count: int,
    ) -> float:
        if current_average is None or sample_count <= 1:
            return round(float(new_value), 2)
        return round(
            ((current_average * (sample_count - 1)) + float(new_value)) / sample_count,
            2,
        )

    def _utc_now(self) -> str:
        return datetime.now(UTC).isoformat()


def _build_cache_entry(
    metrics: DeviceOverviewMetrics,
    diagnostics: DeviceOverviewDiagnostics,
    telemetry: list[DeviceTelemetryPoint] | None = None,
    *,
    timestamp: str | None = None,
) -> LiveCacheEntry:
    entry_timestamp = timestamp or datetime.now(UTC).isoformat()
    last_contact_at = diagnostics.last_contact_at or (
        entry_timestamp if diagnostics.last_error is None and "stub_mode=false" in diagnostics.last_poll_status else None
    )
    last_valid_data_at = diagnostics.last_valid_data_at or (
        entry_timestamp if diagnostics.last_error is None and diagnostics.poll_kind == "full" else None
    )
    return LiveCacheEntry(
        metrics=metrics,
        diagnostics=diagnostics.model_copy(
            update={
                "last_contact_at": last_contact_at,
                "last_valid_data_at": last_valid_data_at,
            }
        ),
        telemetry=list(telemetry or []),
        timestamp=entry_timestamp,
    )


def _build_fallback_entry(
    response_time_ms: int = 0,
    last_poll_status: str = "stub_mode=true; stage=idle",
    last_error: str | None = None,
    retries: int = 0,
    poll_kind: str = "full",
) -> LiveCacheEntry:
    return _build_cache_entry(
        metrics=DeviceOverviewMetrics(
            power_kw=0.0,
            daily_energy_kwh=0.0,
            total_energy_kwh=0.0,
            temperature_c=25.0,
        ),
        diagnostics=DeviceOverviewDiagnostics(
            last_poll_status=last_poll_status,
            response_time_ms=response_time_ms,
            retries=retries,
            last_error=last_error,
            poll_kind=poll_kind,
        ),
        telemetry=[],
    )


def _build_endpoint_backoff_entry(
    device: DeviceResponse,
    backoff_decision: object,
    *,
    poll_kind: str,
) -> LiveCacheEntry:
    endpoint_label = getattr(backoff_decision, "endpoint_label", None) or "shared endpoint"
    remaining_seconds = max(
        1,
        int(round(float(getattr(backoff_decision, "remaining_backoff_seconds", 0.0)))),
    )
    consecutive_failures = int(
        getattr(backoff_decision, "consecutive_connect_failures", 0),
    )
    return _build_fallback_entry(
        response_time_ms=0,
        last_poll_status=(
            f"stub_mode=false; stage=endpoint_backoff; poll_kind={poll_kind}; protocol={device.protocol}; "
            f"endpoint={endpoint_label}"
        ),
        last_error=(
            f"Polling paused for shared endpoint {endpoint_label} after "
            f"{consecutive_failures} connection failure(s). Retrying in {remaining_seconds}s."
        ),
        retries=_get_retry_count(device),
        poll_kind=poll_kind,
    )


def _is_endpoint_backoff_entry(entry: LiveCacheEntry) -> bool:
    return "stage=endpoint_backoff" in entry.diagnostics.last_poll_status


def _merge_poll_entry(
    previous_entry: LiveCacheEntry | None,
    next_entry: LiveCacheEntry,
) -> LiveCacheEntry:
    last_contact_at = next_entry.diagnostics.last_contact_at
    last_valid_data_at = next_entry.diagnostics.last_valid_data_at
    merged_metrics = next_entry.metrics.model_copy(deep=True)
    merged_telemetry = [item.model_copy(deep=True) for item in next_entry.telemetry]

    if previous_entry is not None:
        if last_contact_at is None:
            last_contact_at = previous_entry.diagnostics.last_contact_at
        if last_valid_data_at is None:
            last_valid_data_at = (
                previous_entry.diagnostics.last_valid_data_at
                or (previous_entry.timestamp if is_successful_full_poll(previous_entry) else None)
            )

        should_preserve_previous_data = (
            not is_successful_full_poll(next_entry)
            and (
                previous_entry.diagnostics.last_valid_data_at is not None
                or is_successful_full_poll(previous_entry)
            )
        )
        if _is_successful_active_power_poll(next_entry):
            merged_metrics = previous_entry.metrics.model_copy(
                deep=True,
                update={"power_kw": next_entry.metrics.power_kw},
            )
            merged_telemetry = _merge_telemetry_points(
                previous_entry.telemetry,
                next_entry.telemetry,
            )
        elif should_preserve_previous_data:
            merged_metrics = previous_entry.metrics.model_copy(deep=True)
            merged_telemetry = [item.model_copy(deep=True) for item in previous_entry.telemetry]

    return LiveCacheEntry(
        metrics=merged_metrics,
        diagnostics=next_entry.diagnostics.model_copy(
            deep=True,
            update={
                "last_contact_at": last_contact_at,
                "last_valid_data_at": last_valid_data_at,
            },
        ),
        telemetry=merged_telemetry,
        timestamp=next_entry.timestamp,
    )


def _get_retry_count(device: DeviceResponse) -> int:
    return get_effective_retry_count(device)


def _is_successful_active_power_poll(entry: LiveCacheEntry) -> bool:
    return is_successful_real_poll(entry) and entry.diagnostics.poll_kind == "active_power"


def _merge_telemetry_points(
    previous_telemetry: list[DeviceTelemetryPoint],
    next_telemetry: list[DeviceTelemetryPoint],
) -> list[DeviceTelemetryPoint]:
    merged_by_key = {
        item.key: item.model_copy(deep=True) for item in previous_telemetry
    }
    merged_order = [item.key for item in previous_telemetry]

    for item in next_telemetry:
        if item.key not in merged_by_key:
            merged_order.append(item.key)
        merged_by_key[item.key] = item.model_copy(deep=True)

    return [merged_by_key[key] for key in merged_order if key in merged_by_key]


def _connect_error_message(protocol: str) -> str:
    if protocol == "modbus_rtu":
        return "Unable to connect to Modbus RTU device."
    if protocol in {"modbus_tcp", "sunspec"}:
        return "Unable to connect to Modbus TCP device."
    if protocol == "aurora":
        return "Unable to connect to Aurora RTU device."
    if protocol == "delta_rs485":
        return "Unable to connect to Delta RS485 device."
    return "Unable to connect to device."


def _classify_poll_stage(message: str) -> str:
    if "Missing" in message:
        return "settings"
    if "Telemetry profile" in message:
        return "profile"
    return "read_register"


def _metric_value(
    *,
    values: dict[str, float | int],
    points: list[InverterPoint],
    canonical_key: str,
    summary_metric: str,
    default: float,
    device: object | None = None,
    validate_quality: bool = False,
) -> float:
    raw_value = values.get(canonical_key)
    if isinstance(raw_value, (int, float)):
        point = next((item for item in points if item.key == canonical_key), None)
        if not validate_quality or point is None or telemetry_quality_service.is_usable_metric(
            point,
            raw_value,
            device=device,
            values=values,
            telemetry_points=points,
        ):
            return float(raw_value)

    for point in points:
        if point.protocol_meta.get("summary_metric") != summary_metric:
            continue
        candidate = values.get(point.key)
        if isinstance(candidate, (int, float)):
            if not validate_quality or telemetry_quality_service.is_usable_metric(
                point,
                candidate,
                device=device,
                values=values,
                telemetry_points=points,
            ):
                return float(candidate)

    return default


def _status_value(values: dict[str, float | int], inverter_model: InverterModel) -> str:
    raw_value = values.get("status")
    if isinstance(raw_value, (int, float)):
        return str(int(raw_value))

    for point in inverter_model.telemetry_points:
        if point.protocol_meta.get("summary_metric") != "status":
            continue
        candidate = values.get(point.key)
        if isinstance(candidate, (int, float)):
            return str(int(candidate))

    return "0"


def _build_telemetry_points(
    inverter_model: InverterModel,
    values: dict[str, float | int],
    *,
    device: object | None = None,
) -> list[DeviceTelemetryPoint]:
    telemetry_items: list[DeviceTelemetryPoint] = []
    for point in inverter_model.telemetry_points:
        if not point.visible or point.key not in values:
            continue

        value = values[point.key]
        quality = telemetry_quality_service.evaluate(
            point,
            value,
            device=device,
            values=values,
            telemetry_points=inverter_model.telemetry_points,
        )
        telemetry_items.append(
            DeviceTelemetryPoint(
                key=point.key,
                label=point.label,
                value=value,
                raw_value=value,
                display_value=_format_point_value(point, value),
                unit=point.unit,
                section=str(point.protocol_meta.get("section", "General")),
                visible=point.visible,
                writable=point.writable,
                quality=quality.state,
                quality_reason=quality.reason,
            )
        )
    return telemetry_items


def _format_point_value(point: InverterPoint, value: float | int) -> str:
    enum_map = point.protocol_meta.get("enum_map")
    if isinstance(enum_map, dict) and isinstance(value, (int, float)):
        code = int(value)
        mapped = enum_map.get(code)
        if isinstance(mapped, str):
            return mapped
        return f"{code} - Sconosciuto"

    bitmask_labels = point.protocol_meta.get("bitmask_labels")
    if isinstance(bitmask_labels, dict) and isinstance(value, (int, float)):
        bitmask = int(value)
        active_labels = [
            str(label)
            for bit_index, label in sorted(bitmask_labels.items(), key=lambda item: int(item[0]))
            if bitmask & (1 << int(bit_index))
        ]
        if active_labels:
            return " | ".join(active_labels)
        return "Nessun derating attivo"

    display_format = str(point.protocol_meta.get("display_format", "number"))
    if display_format == "hex":
        width = int(point.protocol_meta.get("display_width", 4))
        prefix = str(point.protocol_meta.get("display_prefix", "0x"))
        return f"{prefix}{int(value) & ((1 << (width * 4)) - 1):0{width}X}"

    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.3f}".rstrip("0").rstrip(".")

    return str(value)


polling_engine = PollingEngine()
