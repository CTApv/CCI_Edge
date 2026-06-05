from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil
from threading import Event, Lock, Thread
from time import monotonic
from typing import Callable

from app.config import settings
from app.logger import get_logger
from app.models.inverter_model import InverterPoint
from app.services.active_power_limit_readback_resolver import (
    active_power_limit_readback_resolver,
)
from app.services.active_power_limit_resolver import active_power_limit_resolver
from app.services.command_service import command_service
from app.services.connection_manager import connection_manager
from app.services.device_runtime import uses_serial_like_polling
from app.services.device_service import device_service
from app.services.endpoint_runtime_service import endpoint_runtime_service
from app.services.fleet_setpoint_service import (
    FleetDeviceControlState,
    FleetDeviceDispatchResult,
    fleet_setpoint_service,
)
from app.services.inverter_io_service import CommandWriteResult, inverter_io_service
from app.services.inverter_profile_resolver import inverter_profile_resolver
from app.services.live_cache import live_cache
from app.services.modbus_tcp_slave_service import modbus_tcp_slave_service
from app.services.polling_engine import polling_engine
from app.services.runtime_event_service import runtime_event_service

logger = get_logger("pv_edge_manager.fleet_dispatch")
SERIAL_DISPATCH_PRIORITY_HOLD_SECONDS = 4.0
TCP_DISPATCH_PRIORITY_HOLD_SECONDS = 2.5
TCP_PARALLEL_DISPATCH_WORKERS = 8


@dataclass(slots=True, frozen=True)
class _ResolvedFleetTarget:
    eligibility: str
    eligibility_reason: str | None
    inverter_model: object | None
    command_point: InverterPoint | None
    command_key: str | None
    resolved_value: float | None
    resolved_unit: str | None
    resolved_max_value: float | None


@dataclass(slots=True, frozen=True)
class _TelemetryReadbackStatus:
    supported: bool
    fresh: bool
    confirmed: bool
    observed_percent: float | None
    observed_value: float | None
    observed_unit: str | None
    telemetry_label: str | None


@dataclass(slots=True, frozen=True)
class _CommandRetryBackoff:
    desired_percent: float
    desired_updated_at: str
    next_retry_monotonic: float
    consecutive_errors: int
    last_error: str | None
    diagnostics: dict[str, str | int | float | bool]


@dataclass(slots=True, frozen=True)
class _BroadcastCandidate:
    device: object
    previous_state: FleetDeviceControlState | None
    resolved_target: _ResolvedFleetTarget
    readback: _TelemetryReadbackStatus


@dataclass(slots=True, frozen=True)
class _BroadcastEndpoint:
    key: tuple[object, ...]
    label: str
    kind: str


class FleetDispatchService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._stop_event = Event()
        self._wake_event = Event()
        self._thread: Thread | None = None
        self._command_retry_backoffs: dict[str, _CommandRetryBackoff] = {}
        self._command_retry_backoff_lock = Lock()
        self._post_dispatch_callbacks: list[Callable[[], None]] = []
        self._dispatch_request_generation = 0

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return

            self._stop_event.clear()
            self._wake_event.clear()
            self._thread = Thread(
                target=self._run,
                name="pv-edge-fleet-dispatch",
                daemon=True,
            )
            self._thread.start()
        self.request_dispatch()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._thread = None
            self._stop_event.set()
            self._wake_event.set()

        if thread is not None:
            thread.join(timeout=2)

    def request_dispatch(
        self,
        on_complete: Callable[[], None] | None = None,
    ) -> None:
        with self._lock:
            if on_complete is not None:
                self._post_dispatch_callbacks.append(on_complete)
            self._dispatch_request_generation += 1
        self._request_serial_command_priority_window()
        self._request_tcp_command_priority_window()
        self._wake_event.set()

    def _run(self) -> None:
        handled_generation = -1
        run_cycle = True
        while not self._stop_event.is_set():
            with self._lock:
                current_generation = self._dispatch_request_generation
            if run_cycle or current_generation != handled_generation:
                handled_generation = current_generation
                self._dispatch_active_power_limit_if_needed()
                self._run_due_cci_read_cycle_if_needed()
                self._run_post_dispatch_callbacks()
                run_cycle = False
                continue
            signaled = self._wake_event.wait(self._resolve_wait_seconds())
            self._wake_event.clear()
            run_cycle = not signaled

    def _run_post_dispatch_callbacks(self) -> None:
        with self._lock:
            callbacks = self._post_dispatch_callbacks
            self._post_dispatch_callbacks = []

        for callback in callbacks:
            try:
                callback()
            except Exception as exc:
                logger.warning("Fleet dispatch post-cycle callback failed: %s", exc)

    def _resolve_wait_seconds(self) -> float:
        wait_seconds = max(0.1, float(settings.fleet_dispatch_interval_seconds))
        next_cci_read_due_seconds = modbus_tcp_slave_service.get_next_cci_read_due_in_seconds()
        if next_cci_read_due_seconds is None:
            return wait_seconds
        return max(0.1, min(wait_seconds, next_cci_read_due_seconds))

    def _run_due_cci_read_cycle_if_needed(self) -> None:
        state = fleet_setpoint_service.get_state()
        if (
            state.updated_source != "modbus_tcp_slave"
            or state.active_power_limit_percent is None
        ):
            return

        request = modbus_tcp_slave_service.claim_due_cci_read_cycle()
        if request is None:
            return

        poll_kind = "active_power" if request.active_power_only else "full"
        devices = [
            device
            for device in device_service.list_devices()
            if self._uses_post_dispatch_read_cycle(device)
        ]
        try:
            summary = polling_engine.run_on_demand_read_cycle(
                devices,
                poll_kind=poll_kind,
            )
            logger.info(
                "CCI read cycle completed around %.1f%% using %s mode: polled=%s success=%s error=%s skipped=%s",
                request.reference_percent,
                "active_power" if request.active_power_only else "full",
                summary["polled_device_count"],
                summary["success_count"],
                summary["error_count"],
                summary["skipped_device_count"],
            )
            runtime_event_service.record_event(
                category="polling",
                level="success" if int(summary["error_count"]) <= 0 else "warning",
                title="Lettura inverter avviata dal CCI",
                message=(
                    f"Completato un ciclo di lettura {poll_kind} attorno a "
                    f"{request.reference_percent:.1f}%."
                ),
                details={
                    "generation": request.generation,
                    "reference_percent": request.reference_percent,
                    "poll_kind": poll_kind,
                    "polled_count": int(summary["polled_device_count"]),
                    "success_count": int(summary["success_count"]),
                    "error_count": int(summary["error_count"]),
                    "skipped_count": int(summary["skipped_device_count"]),
                },
            )
        except Exception as exc:
            logger.warning(
                "CCI read cycle failed around %.1f%%: %s",
                request.reference_percent,
                exc,
            )
            runtime_event_service.record_event(
                category="polling",
                level="error",
                title="Lettura inverter CCI fallita",
                message=(
                    f"Il ciclo di lettura richiesto attorno a "
                    f"{request.reference_percent:.1f}% non e andato a buon fine."
                ),
                details={
                    "generation": request.generation,
                    "reference_percent": request.reference_percent,
                    "poll_kind": poll_kind,
                    "error": str(exc),
                },
                dedupe_key="cci-read-cycle-failed",
                dedupe_window_seconds=4.0,
            )
        finally:
            dispatch_pending = modbus_tcp_slave_service.complete_cci_read_cycle(
                request.generation
            )
            modbus_tcp_slave_service.refresh_registers()

        if dispatch_pending:
            self.request_dispatch()

    def _dispatch_active_power_limit_if_needed(self) -> None:
        devices = device_service.list_devices()
        state = fleet_setpoint_service.get_state()
        previous_states = {
            item.device_id: item for item in fleet_setpoint_service.list_device_control_states()
        }

        if state.active_power_limit_percent is None or state.updated_at is None:
            with self._command_retry_backoff_lock:
                self._command_retry_backoffs = {}
            control_states = [
                self._build_idle_control_state(device)
                for device in devices
            ]
            eligible_device_count = sum(
                1 for device_state in control_states if device_state.eligibility == "eligible"
            )
            fleet_setpoint_service.replace_device_control_states(
                control_states,
                eligible_device_count=eligible_device_count,
            )
            fleet_setpoint_service.clear_device_results()
            modbus_tcp_slave_service.refresh_registers()
            return

        desired_percent = state.active_power_limit_percent
        desired_updated_at = state.updated_at
        desired_source = state.updated_source
        desired_source_priority = state.effective_source_priority
        self._prune_command_retry_backoffs(
            active_device_ids={device.device_id for device in devices},
            desired_percent=desired_percent,
            desired_updated_at=desired_updated_at,
        )

        logger.info(
            "Reconciling fleet target %.1f%% from %s across %s configured devices.",
            desired_percent,
            desired_source or "unknown",
            len(devices),
        )

        control_states: list[FleetDeviceControlState] = []
        dispatch_results: list[FleetDeviceDispatchResult] = []
        eligible_device_count = 0
        resolved_targets: dict[str, _ResolvedFleetTarget] = {}

        for device in devices:
            resolved_target = self._resolve_target(device, desired_percent)
            resolved_targets[device.device_id] = resolved_target
            if resolved_target.eligibility == "eligible":
                eligible_device_count += 1

        broadcast_dispatches = self._dispatch_rtu_broadcast_groups(
            devices=devices,
            previous_states=previous_states,
            resolved_targets=resolved_targets,
            desired_percent=desired_percent,
            desired_updated_at=desired_updated_at,
            desired_source=desired_source,
            desired_source_priority=desired_source_priority,
        )
        parallel_dispatches = self._dispatch_parallel_tcp_devices(
            devices=devices,
            previous_states=previous_states,
            resolved_targets=resolved_targets,
            broadcast_dispatches=broadcast_dispatches,
            desired_percent=desired_percent,
            desired_updated_at=desired_updated_at,
            desired_source=desired_source,
            desired_source_priority=desired_source_priority,
        )

        for device in devices:
            broadcast_dispatch = broadcast_dispatches.get(device.device_id)
            if broadcast_dispatch is not None:
                control_state, dispatch_result = broadcast_dispatch
                control_states.append(control_state)
                dispatch_results.append(dispatch_result)
                continue
            parallel_dispatch = parallel_dispatches.get(device.device_id)
            if parallel_dispatch is not None:
                control_state, dispatch_result = parallel_dispatch
                control_states.append(control_state)
                dispatch_results.append(dispatch_result)
                continue

            previous_state = previous_states.get(device.device_id)
            resolved_target = resolved_targets[device.device_id]
            control_state, dispatch_result = self._reconcile_device(
                device=device,
                previous_state=previous_state,
                resolved_target=resolved_target,
                desired_percent=desired_percent,
                desired_updated_at=desired_updated_at,
                desired_source=desired_source,
                desired_source_priority=desired_source_priority,
            )
            control_states.append(control_state)
            dispatch_results.append(dispatch_result)

        fleet_setpoint_service.replace_device_control_states(
            control_states,
            eligible_device_count=eligible_device_count,
        )
        fleet_setpoint_service.record_dispatch_results(
            dispatch_results,
            eligible_device_count=eligible_device_count,
        )
        logger.info(
            "Fleet target reconciliation: aligned=%s pending=%s blocked=%s error=%s eligible=%s total=%s",
            sum(1 for item in control_states if item.control_state == "aligned"),
            sum(1 for item in control_states if item.control_state == "pending"),
            sum(1 for item in control_states if item.control_state == "blocked"),
            sum(1 for item in control_states if item.control_state == "error"),
            eligible_device_count,
            len(control_states),
        )
        aligned_count = sum(1 for item in control_states if item.control_state == "aligned")
        pending_count = sum(1 for item in control_states if item.control_state == "pending")
        blocked_count = sum(1 for item in control_states if item.control_state == "blocked")
        error_count = sum(1 for item in control_states if item.control_state == "error")
        if eligible_device_count <= 0:
            level = "warning"
            title = "Dispatch target senza device compatibili"
            message = (
                f"Il target {desired_percent:.1f}% da {desired_source or 'sorgente sconosciuta'} "
                "non ha trovato inverter compatibili."
            )
        elif error_count > 0:
            level = "warning"
            title = "Dispatch target con errori"
            message = (
                f"Il target {desired_percent:.1f}% e stato inviato, ma almeno un inverter "
                "ha restituito errore."
            )
        elif aligned_count > 0 or pending_count > 0:
            level = "success"
            title = "Dispatch target inviato"
            message = (
                f"Il target {desired_percent:.1f}% e stato inviato agli inverter "
                "compatibili nel ciclo corrente."
            )
        else:
            level = "info"
            title = "Dispatch target in attesa"
            message = (
                f"Il target {desired_percent:.1f}% e presente, ma non risulta ancora un invio utile "
                "verso gli inverter compatibili."
            )
        runtime_event_service.record_event(
            category="dispatch",
            level=level,
            title=title,
            message=message,
            details={
                "requested_percent": desired_percent,
                "source": desired_source or "unknown",
                "aligned_count": aligned_count,
                "pending_count": pending_count,
                "blocked_count": blocked_count,
                "error_count": error_count,
                "eligible_count": eligible_device_count,
                "device_count": len(control_states),
            },
            dedupe_key=f"dispatch-summary:{desired_updated_at}",
            dedupe_window_seconds=30.0,
        )
        modbus_tcp_slave_service.refresh_registers()

    def _request_serial_command_priority_window(self) -> None:
        reserved_priority_keys: set[str] = set()
        for device in device_service.list_devices():
            priority_key = self._serial_like_priority_key(device)
            if priority_key is None or priority_key in reserved_priority_keys:
                continue
            reserved_priority_keys.add(priority_key)
            connection_manager.request_modbus_rtu_priority(
                priority_key,
                hold_seconds=SERIAL_DISPATCH_PRIORITY_HOLD_SECONDS,
            )

    def _request_tcp_command_priority_window(self) -> None:
        state = fleet_setpoint_service.get_state()
        if state.active_power_limit_percent is None:
            return
        reserved_endpoints: set[tuple[str, int]] = set()
        for device in device_service.list_devices():
            endpoint = self._tcp_command_priority_endpoint(device)
            if endpoint is None or endpoint in reserved_endpoints:
                continue
            reserved_endpoints.add(endpoint)
            host, port = endpoint
            connection_manager.request_modbus_tcp_priority(
                host,
                port,
                hold_seconds=TCP_DISPATCH_PRIORITY_HOLD_SECONDS,
            )

    def _dispatch_rtu_broadcast_groups(
        self,
        *,
        devices: list[object],
        previous_states: dict[str, FleetDeviceControlState],
        resolved_targets: dict[str, _ResolvedFleetTarget],
        desired_percent: float,
        desired_updated_at: str,
        desired_source: str | None,
        desired_source_priority: int,
    ) -> dict[str, tuple[FleetDeviceControlState, FleetDeviceDispatchResult]]:
        line_groups: dict[_BroadcastEndpoint, list[object]] = {}
        for device in devices:
            endpoint = self._broadcast_endpoint(device)
            if endpoint is None:
                continue
            line_groups.setdefault(endpoint, []).append(device)

        broadcast_dispatches: dict[str, tuple[FleetDeviceControlState, FleetDeviceDispatchResult]] = {}
        for endpoint, line_devices in line_groups.items():
            if len(line_devices) < 2:
                continue
            if any(
                not self._device_matches_broadcast_endpoint(device, endpoint)
                for device in line_devices
            ):
                logger.debug(
                    "Modbus broadcast disabled on %s: endpoint contains incompatible devices.",
                    endpoint.label,
                )
                continue

            if any(self._has_active_endpoint_backoff(device) for device in line_devices):
                logger.info(
                    "Modbus broadcast skipped on %s: endpoint communication is in cooldown.",
                    endpoint.label,
                )
                continue

            line_signatures = {
                signature
                for device in line_devices
                for signature in [self._broadcast_endpoint_signature(device)]
                if signature is not None
            }
            if len(line_signatures) != 1 or len(line_signatures) != len(
                {self._broadcast_endpoint_signature(device) for device in line_devices}
            ):
                logger.debug(
                    "Modbus broadcast disabled on %s: endpoint settings are incomplete or mixed.",
                    endpoint.label,
                )
                continue

            configured_command_signatures: set[tuple[object, ...]] = set()
            broadcast_supported = True
            for device in line_devices:
                resolved_target = resolved_targets[device.device_id]
                if (
                    resolved_target.eligibility != "eligible"
                    or resolved_target.command_point is None
                    or resolved_target.resolved_value is None
                ):
                    broadcast_supported = False
                    break

                command_signature = inverter_io_service.build_command_broadcast_signature(
                    device,
                    resolved_target.command_point,
                    resolved_target.resolved_value,
                )
                if command_signature is None:
                    broadcast_supported = False
                    break
                configured_command_signatures.add(command_signature)

            if not broadcast_supported or len(configured_command_signatures) != 1:
                logger.debug(
                    "Modbus broadcast disabled on %s: active power command profiles are not homogeneous.",
                    endpoint.label,
                )
                continue

            candidates = [
                candidate
                for device in line_devices
                for candidate in [
                    self._build_broadcast_candidate(
                        device=device,
                        previous_state=previous_states.get(device.device_id),
                        resolved_target=resolved_targets[device.device_id],
                        desired_percent=desired_percent,
                        desired_updated_at=desired_updated_at,
                    )
                ]
                if candidate is not None
            ]
            if not candidates:
                continue

            reference_candidate = candidates[0]
            assert reference_candidate.resolved_target.command_point is not None
            assert reference_candidate.resolved_target.resolved_value is not None
            write_result = inverter_io_service.write_command_broadcast(
                reference_candidate.device,
                reference_candidate.resolved_target.command_point,
                reference_candidate.resolved_target.resolved_value,
            )
            if not write_result.success:
                logger.warning(
                    "Modbus broadcast write failed on %s, falling back to per-device dispatch: %s",
                    endpoint.label,
                    write_result.error,
                )
                continue

            dispatch_at = self._utc_now()
            diagnostics = {
                **write_result.diagnostics,
                "broadcast": True,
                "broadcast_endpoint": endpoint.label,
                "broadcast_endpoint_type": endpoint.kind,
                "broadcast_candidate_count": len(candidates),
                "broadcast_configured_count": len(line_devices),
            }
            if endpoint.kind == "serial":
                diagnostics["broadcast_port"] = endpoint.label
            logger.info(
                "Modbus broadcast write sent on %s for %s/%s configured devices.",
                endpoint.label,
                len(candidates),
                len(line_devices),
            )
            for candidate in candidates:
                command_service.record_active_power_limit_broadcast_success(
                    candidate.device.device_id,
                    desired_percent,
                )
                broadcast_dispatches[candidate.device.device_id] = (
                    self._build_broadcast_success_control_state(
                        candidate=candidate,
                        desired_percent=desired_percent,
                        desired_updated_at=desired_updated_at,
                        desired_source=desired_source,
                        desired_source_priority=desired_source_priority,
                        dispatch_at=dispatch_at,
                        diagnostics=diagnostics,
                    )
                )

        return broadcast_dispatches

    def _dispatch_parallel_tcp_devices(
        self,
        *,
        devices: list[object],
        previous_states: dict[str, FleetDeviceControlState],
        resolved_targets: dict[str, _ResolvedFleetTarget],
        broadcast_dispatches: dict[str, tuple[FleetDeviceControlState, FleetDeviceDispatchResult]],
        desired_percent: float,
        desired_updated_at: str,
        desired_source: str | None,
        desired_source_priority: int,
    ) -> dict[str, tuple[FleetDeviceControlState, FleetDeviceDispatchResult]]:
        endpoint_counts: dict[tuple[str, int], int] = {}
        for device in devices:
            endpoint = self._tcp_command_priority_endpoint(device)
            if endpoint is None:
                continue
            endpoint_counts[endpoint] = endpoint_counts.get(endpoint, 0) + 1

        parallel_devices = [
            device
            for device in devices
            if device.device_id not in broadcast_dispatches
            and resolved_targets[device.device_id].eligibility == "eligible"
            and self._tcp_command_priority_endpoint(device) is not None
            and endpoint_counts.get(self._tcp_command_priority_endpoint(device), 0) == 1
        ]
        if len(parallel_devices) < 2:
            return {}

        results: dict[str, tuple[FleetDeviceControlState, FleetDeviceDispatchResult]] = {}
        max_workers = min(TCP_PARALLEL_DISPATCH_WORKERS, len(parallel_devices))
        with ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="pv-edge-dispatch-tcp",
        ) as executor:
            future_to_device = {
                executor.submit(
                    self._reconcile_device,
                    device=device,
                    previous_state=previous_states.get(device.device_id),
                    resolved_target=resolved_targets[device.device_id],
                    desired_percent=desired_percent,
                    desired_updated_at=desired_updated_at,
                    desired_source=desired_source,
                    desired_source_priority=desired_source_priority,
                ): device
                for device in parallel_devices
            }
            for future in as_completed(future_to_device):
                device = future_to_device[future]
                try:
                    results[device.device_id] = future.result()
                except Exception as exc:
                    logger.warning(
                        "Parallel TCP dispatch failed for %s, retrying sequentially: %s",
                        getattr(device, "device_id", "unknown"),
                        exc,
                    )
                    results[device.device_id] = self._reconcile_device(
                        device=device,
                        previous_state=previous_states.get(device.device_id),
                        resolved_target=resolved_targets[device.device_id],
                        desired_percent=desired_percent,
                        desired_updated_at=desired_updated_at,
                        desired_source=desired_source,
                        desired_source_priority=desired_source_priority,
                    )
        return results

    def _build_broadcast_candidate(
        self,
        *,
        device: object,
        previous_state: FleetDeviceControlState | None,
        resolved_target: _ResolvedFleetTarget,
        desired_percent: float,
        desired_updated_at: str,
    ) -> _BroadcastCandidate | None:
        if resolved_target.eligibility != "eligible":
            return None
        if resolved_target.command_point is None or resolved_target.resolved_value is None:
            return None
        if device.status in {"offline", "fault"}:
            return None

        preserved_fields = self._preserve_previous_command_fields(
            previous_state=previous_state,
            desired_percent=desired_percent,
            desired_updated_at=desired_updated_at,
        )
        readback_reference_timestamp = (
            self._string_or_none(preserved_fields["last_dispatch_at"]) or desired_updated_at
        )
        readback = self._evaluate_readback(
            device=device,
            resolved_target=resolved_target,
            desired_percent=desired_percent,
            reference_timestamp=readback_reference_timestamp,
        )

        if (
            preserved_fields["last_dispatch_at"] is not None
            and preserved_fields["last_sent_percent"] == desired_percent
            and readback.supported
        ):
            return None

        retry_after_seconds = self._remaining_command_retry_backoff(
            device_id=device.device_id,
            desired_percent=desired_percent,
            desired_updated_at=desired_updated_at,
        )
        if previous_state is not None and retry_after_seconds is not None:
            return None

        if not self._should_attempt_dispatch(previous_state, desired_percent, desired_updated_at):
            return None

        return _BroadcastCandidate(
            device=device,
            previous_state=previous_state,
            resolved_target=resolved_target,
            readback=readback,
        )

    def _build_broadcast_success_control_state(
        self,
        *,
        candidate: _BroadcastCandidate,
        desired_percent: float,
        desired_updated_at: str,
        desired_source: str | None,
        desired_source_priority: int,
        dispatch_at: str,
        diagnostics: dict[str, str | int | float | bool],
    ) -> tuple[FleetDeviceControlState, FleetDeviceDispatchResult]:
        device = candidate.device
        resolved_target = candidate.resolved_target
        readback = candidate.readback
        self._clear_command_retry_backoff(device.device_id)
        broadcast_note_prefix = self._broadcast_success_note_prefix(diagnostics)

        if readback.supported:
            note = (
                f"{broadcast_note_prefix} "
                + self._build_post_dispatch_pending_note(readback)
            )
            control_state = FleetDeviceControlState(
                device_id=device.device_id,
                name=device.name,
                brand=device.brand,
                model=device.model,
                protocol=device.protocol,
                transport=device.transport,
                device_status=device.status,
                eligibility="eligible",
                eligibility_reason=None,
                control_state="aligned",
                desired_percent=desired_percent,
                desired_updated_at=desired_updated_at,
                desired_source=desired_source,
                desired_source_priority=desired_source_priority,
                last_sent_percent=desired_percent,
                last_applied_percent=None,
                telemetry_confirmed=False,
                last_command=resolved_target.command_key,
                last_resolved_value=resolved_target.resolved_value,
                last_resolved_unit=resolved_target.resolved_unit,
                last_dispatch_outcome="ok",
                last_dispatch_at=dispatch_at,
                last_error=None,
                note=note,
            )
        else:
            control_state = FleetDeviceControlState(
                device_id=device.device_id,
                name=device.name,
                brand=device.brand,
                model=device.model,
                protocol=device.protocol,
                transport=device.transport,
                device_status=device.status,
                eligibility="eligible",
                eligibility_reason=None,
                control_state="aligned",
                desired_percent=desired_percent,
                desired_updated_at=desired_updated_at,
                desired_source=desired_source,
                desired_source_priority=desired_source_priority,
                last_sent_percent=desired_percent,
                last_applied_percent=desired_percent,
                telemetry_confirmed=False,
                last_command=resolved_target.command_key,
                last_resolved_value=resolved_target.resolved_value,
                last_resolved_unit=resolved_target.resolved_unit,
                last_dispatch_outcome="ok",
                last_dispatch_at=dispatch_at,
                last_error=None,
                note=(
                    f"{broadcast_note_prefix} "
                    "Il modello non espone un readback telemetrico del setpoint."
                ),
            )

        return self._finalize_control_state(
            device_id=device.device_id,
            control_state=control_state,
            diagnostics=diagnostics,
        )

    def _broadcast_success_note_prefix(
        self,
        diagnostics: dict[str, str | int | float | bool],
    ) -> str:
        if diagnostics.get("broadcast_endpoint_type") == "rtu_over_tcp":
            return "Broadcast RTU-over-TCP inviato sul gateway."
        if diagnostics.get("broadcast_endpoint_type") == "modbus_tcp_gateway":
            return "Broadcast Modbus TCP inviato sul gateway."
        return "Broadcast RTU inviato sulla linea seriale."

    def _broadcast_endpoint(self, device: object) -> _BroadcastEndpoint | None:
        protocol = getattr(device, "protocol", None)
        transport = getattr(device, "transport", None)
        connection_settings = getattr(device, "connection_settings", {})
        if not isinstance(connection_settings, dict):
            return None

        if protocol == "modbus_rtu" and transport == "serial":
            port = self._serial_port(device)
            if port is None:
                return None
            return _BroadcastEndpoint(
                key=("serial", port),
                label=port,
                kind="serial",
            )

        if transport == "tcp" and protocol in {"modbus_rtu", "modbus_tcp"}:
            host = connection_settings.get("host")
            port = connection_settings.get("port")
            if host in {None, ""} or port is None:
                return None
            try:
                normalized_host = str(host).strip()
                normalized_port = int(port)
            except (TypeError, ValueError):
                return None
            if not normalized_host:
                return None
            endpoint_kind = (
                "rtu_over_tcp" if protocol == "modbus_rtu" else "modbus_tcp_gateway"
            )
            return _BroadcastEndpoint(
                key=(endpoint_kind, normalized_host, normalized_port),
                label=f"{normalized_host}:{normalized_port}",
                kind=endpoint_kind,
            )

        return None

    def _device_matches_broadcast_endpoint(
        self,
        device: object,
        endpoint: _BroadcastEndpoint,
    ) -> bool:
        protocol = getattr(device, "protocol", None)
        if endpoint.kind == "serial":
            return protocol == "modbus_rtu"
        if endpoint.kind == "rtu_over_tcp":
            return protocol == "modbus_rtu"
        if endpoint.kind == "modbus_tcp_gateway":
            return protocol == "modbus_tcp"
        return False

    def _broadcast_endpoint_signature(self, device: object) -> tuple[object, ...] | None:
        protocol = getattr(device, "protocol", None)
        transport = getattr(device, "transport", None)
        if protocol == "modbus_rtu" and transport == "serial":
            return self._rtu_line_signature(device)
        if protocol == "modbus_rtu" and transport == "tcp":
            return self._tcp_gateway_signature(device, "rtu_over_tcp")
        if protocol == "modbus_tcp" and transport == "tcp":
            return self._tcp_gateway_signature(device, "modbus_tcp_gateway")
        return None

    def _tcp_gateway_signature(
        self,
        device: object,
        gateway_mode: str,
    ) -> tuple[object, ...] | None:
        connection_settings = getattr(device, "connection_settings", {})
        if not isinstance(connection_settings, dict):
            return None
        host = connection_settings.get("host")
        port = connection_settings.get("port")
        if host in {None, ""} or port is None:
            return None
        try:
            normalized_host = str(host).strip()
            normalized_port = int(port)
        except (TypeError, ValueError):
            return None
        if not normalized_host:
            return None
        return (gateway_mode, normalized_host, normalized_port)

    def _serial_port(self, device: object) -> str | None:
        if getattr(device, "transport", None) != "serial":
            return None
        connection_settings = getattr(device, "connection_settings", {})
        port = connection_settings.get("port") if isinstance(connection_settings, dict) else None
        if port in {None, ""}:
            return None
        return str(port)

    def _serial_like_priority_key(self, device: object) -> str | None:
        serial_port = self._serial_port(device)
        if serial_port is not None:
            return serial_port
        if getattr(device, "protocol", None) != "modbus_rtu" or getattr(device, "transport", None) != "tcp":
            return None
        connection_settings = getattr(device, "connection_settings", {})
        if not isinstance(connection_settings, dict):
            return None
        host = connection_settings.get("host")
        port = connection_settings.get("port")
        if host in {None, ""} or port in {None, ""}:
            return None
        try:
            normalized_host = str(host).strip()
            normalized_port = int(port)
        except (TypeError, ValueError):
            return None
        if not normalized_host:
            return None
        return f"tcp:{normalized_host}:{normalized_port}"

    def _tcp_command_priority_endpoint(self, device: object) -> tuple[str, int] | None:
        if getattr(device, "transport", None) != "tcp":
            return None
        if getattr(device, "protocol", None) not in {"modbus_tcp", "sunspec"}:
            return None
        connection_settings = getattr(device, "connection_settings", {})
        if not isinstance(connection_settings, dict):
            return None
        host = connection_settings.get("host")
        port = connection_settings.get("port")
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

    def _uses_post_dispatch_read_cycle(self, device: object) -> bool:
        if uses_serial_like_polling(device):
            return True
        return (
            getattr(device, "protocol", None) == "modbus_tcp"
            and getattr(device, "transport", None) == "tcp"
        )

    def _rtu_line_signature(self, device: object) -> tuple[object, ...] | None:
        connection_settings = getattr(device, "connection_settings", {})
        if not isinstance(connection_settings, dict):
            return None
        port = connection_settings.get("port")
        baud_rate = connection_settings.get("baud_rate")
        byte_size = connection_settings.get("byte_size")
        parity = connection_settings.get("parity")
        stop_bits = connection_settings.get("stop_bits")
        if (
            port in {None, ""}
            or baud_rate is None
            or byte_size is None
            or parity in {None, ""}
            or stop_bits is None
        ):
            return None
        try:
            return (
                str(port),
                int(baud_rate),
                int(byte_size),
                str(parity).upper(),
                int(stop_bits),
            )
        except (TypeError, ValueError):
            return None

    def _build_idle_control_state(self, device: object) -> FleetDeviceControlState:
        resolved_target = self._resolve_target(device, 100.0)
        if resolved_target.eligibility == "eligible":
            note = "Nessun setpoint globale attivo."
        else:
            note = resolved_target.eligibility_reason or "Setpoint globale non supportato."
        return FleetDeviceControlState(
            device_id=device.device_id,
            name=device.name,
            brand=device.brand,
            model=device.model,
            protocol=device.protocol,
            transport=device.transport,
            device_status=device.status,
            eligibility=resolved_target.eligibility,
            eligibility_reason=resolved_target.eligibility_reason,
            control_state="idle",
            desired_percent=None,
            desired_updated_at=None,
            desired_source=None,
            desired_source_priority=0,
            last_sent_percent=None,
            last_applied_percent=None,
            telemetry_confirmed=False,
            last_command=resolved_target.command_key,
            last_resolved_value=None,
            last_resolved_unit=resolved_target.resolved_unit,
            last_dispatch_outcome=None,
            last_dispatch_at=None,
            last_error=None,
            note=note,
        )

    def _resolve_target(self, device: object, desired_percent: float) -> _ResolvedFleetTarget:
        inverter_model = inverter_profile_resolver.resolve_for_device(device)
        if inverter_model is None:
            return _ResolvedFleetTarget(
                eligibility="ineligible",
                eligibility_reason="Profilo catalogo non risolto.",
                inverter_model=None,
                command_point=None,
                command_key=None,
                resolved_value=None,
                resolved_unit=None,
                resolved_max_value=None,
            )

        resolution = active_power_limit_resolver.resolve_for_write(inverter_model, desired_percent)
        if resolution is None:
            return _ResolvedFleetTarget(
                eligibility="ineligible",
                eligibility_reason="Setpoint potenza attiva non supportato dal modello.",
                inverter_model=inverter_model,
                command_point=None,
                command_key=None,
                resolved_value=None,
                resolved_unit=None,
                resolved_max_value=None,
            )

        return _ResolvedFleetTarget(
            eligibility="eligible",
            eligibility_reason=None,
            inverter_model=inverter_model,
            command_point=resolution.command_point,
            command_key=resolution.command_point.key,
            resolved_value=resolution.requested_value,
            resolved_unit=resolution.command_point.unit,
            resolved_max_value=self._float_or_none(
                resolution.command_point.protocol_meta.get("max_value")
            ),
        )

    def _reconcile_device(
        self,
        *,
        device: object,
        previous_state: FleetDeviceControlState | None,
        resolved_target: _ResolvedFleetTarget,
        desired_percent: float,
        desired_updated_at: str,
        desired_source: str | None,
        desired_source_priority: int,
    ) -> tuple[FleetDeviceControlState, FleetDeviceDispatchResult]:
        preserved_fields = self._preserve_previous_command_fields(
            previous_state=previous_state,
            desired_percent=desired_percent,
            desired_updated_at=desired_updated_at,
        )
        readback_reference_timestamp = (
            self._string_or_none(preserved_fields["last_dispatch_at"]) or desired_updated_at
        )
        readback = self._evaluate_readback(
            device=device,
            resolved_target=resolved_target,
            desired_percent=desired_percent,
            reference_timestamp=readback_reference_timestamp,
        )

        if resolved_target.eligibility != "eligible":
            control_state = FleetDeviceControlState(
                device_id=device.device_id,
                name=device.name,
                brand=device.brand,
                model=device.model,
                protocol=device.protocol,
                transport=device.transport,
                device_status=device.status,
                eligibility=resolved_target.eligibility,
                eligibility_reason=resolved_target.eligibility_reason,
                control_state="blocked",
                desired_percent=desired_percent,
                desired_updated_at=desired_updated_at,
                desired_source=desired_source,
                desired_source_priority=desired_source_priority,
                last_sent_percent=None,
                last_applied_percent=None,
                telemetry_confirmed=False,
                last_command=None,
                last_resolved_value=None,
                last_resolved_unit=None,
                last_dispatch_outcome="blocked",
                last_dispatch_at=None,
                last_error=resolved_target.eligibility_reason,
                note=resolved_target.eligibility_reason
                or "Il device non partecipa al controllo flotta.",
            )
            return control_state, self._build_dispatch_result(control_state)

        endpoint_backoff_note = self._endpoint_backoff_note(device)
        if endpoint_backoff_note is not None:
            control_state = FleetDeviceControlState(
                device_id=device.device_id,
                name=device.name,
                brand=device.brand,
                model=device.model,
                protocol=device.protocol,
                transport=device.transport,
                device_status=device.status,
                eligibility="eligible",
                eligibility_reason=None,
                control_state="blocked",
                desired_percent=desired_percent,
                desired_updated_at=desired_updated_at,
                desired_source=desired_source,
                desired_source_priority=desired_source_priority,
                last_sent_percent=preserved_fields["last_sent_percent"],
                last_applied_percent=preserved_fields["last_applied_percent"],
                telemetry_confirmed=False,
                last_command=resolved_target.command_key,
                last_resolved_value=resolved_target.resolved_value,
                last_resolved_unit=resolved_target.resolved_unit,
                last_dispatch_outcome="blocked",
                last_dispatch_at=preserved_fields["last_dispatch_at"],
                last_error=endpoint_backoff_note,
                note=endpoint_backoff_note,
            )
            decision = endpoint_runtime_service.get_backoff_decision(device)
            return control_state, self._build_dispatch_result(
                control_state,
                diagnostics={
                    "endpoint_backoff_active": True,
                    "endpoint_label": decision.endpoint_label or "",
                    "remaining_backoff_seconds": round(
                        max(0.0, decision.remaining_backoff_seconds),
                        3,
                    ),
                    "consecutive_connect_failures": decision.consecutive_connect_failures,
                },
            )

        if device.status in {"offline", "fault"}:
            note = (
                "Device offline: il target verra riallineato quando torna raggiungibile."
                if device.status == "offline"
                else "Device in fault: il target resta sospeso finche il guasto non rientra."
            )
            control_state = FleetDeviceControlState(
                device_id=device.device_id,
                name=device.name,
                brand=device.brand,
                model=device.model,
                protocol=device.protocol,
                transport=device.transport,
                device_status=device.status,
                eligibility="eligible",
                eligibility_reason=None,
                control_state="blocked",
                desired_percent=desired_percent,
                desired_updated_at=desired_updated_at,
                desired_source=desired_source,
                desired_source_priority=desired_source_priority,
                last_sent_percent=preserved_fields["last_sent_percent"],
                last_applied_percent=preserved_fields["last_applied_percent"],
                telemetry_confirmed=False,
                last_command=resolved_target.command_key,
                last_resolved_value=resolved_target.resolved_value,
                last_resolved_unit=resolved_target.resolved_unit,
                last_dispatch_outcome="blocked",
                last_dispatch_at=preserved_fields["last_dispatch_at"],
                last_error=note,
                note=note,
            )
            return control_state, self._build_dispatch_result(control_state)

        if (
            preserved_fields["last_dispatch_at"] is not None
            and preserved_fields["last_sent_percent"] == desired_percent
            and readback.supported
        ):
            if readback.fresh and readback.confirmed:
                control_state = FleetDeviceControlState(
                    device_id=device.device_id,
                    name=device.name,
                    brand=device.brand,
                    model=device.model,
                    protocol=device.protocol,
                    transport=device.transport,
                    device_status=device.status,
                    eligibility="eligible",
                    eligibility_reason=None,
                    control_state="aligned",
                    desired_percent=desired_percent,
                    desired_updated_at=desired_updated_at,
                    desired_source=desired_source,
                    desired_source_priority=desired_source_priority,
                    last_sent_percent=desired_percent,
                    last_applied_percent=readback.observed_percent,
                    telemetry_confirmed=True,
                    last_command=resolved_target.command_key,
                    last_resolved_value=resolved_target.resolved_value,
                    last_resolved_unit=resolved_target.resolved_unit,
                    last_dispatch_outcome="ok",
                    last_dispatch_at=self._string_or_none(preserved_fields["last_dispatch_at"]),
                    last_error=None,
                    note=self._build_readback_confirmed_note(readback),
                )
                return control_state, self._build_dispatch_result(control_state)

            control_state = FleetDeviceControlState(
                device_id=device.device_id,
                name=device.name,
                brand=device.brand,
                model=device.model,
                protocol=device.protocol,
                transport=device.transport,
                device_status=device.status,
                eligibility="eligible",
                eligibility_reason=None,
                control_state="aligned",
                desired_percent=desired_percent,
                desired_updated_at=desired_updated_at,
                desired_source=desired_source,
                desired_source_priority=desired_source_priority,
                last_sent_percent=desired_percent,
                last_applied_percent=readback.observed_percent,
                telemetry_confirmed=False,
                last_command=resolved_target.command_key,
                last_resolved_value=resolved_target.resolved_value,
                last_resolved_unit=resolved_target.resolved_unit,
                last_dispatch_outcome="ok",
                last_dispatch_at=self._string_or_none(preserved_fields["last_dispatch_at"]),
                last_error=None,
                note=self._build_readback_pending_note(readback),
                )
            return control_state, self._build_dispatch_result(control_state)

        retry_after_seconds = self._remaining_command_retry_backoff(
            device_id=device.device_id,
            desired_percent=desired_percent,
            desired_updated_at=desired_updated_at,
        )
        if previous_state is not None and retry_after_seconds is not None:
            retry_backoff = self._get_command_retry_backoff(device.device_id)
            note = self._build_retry_backoff_note(
                previous_state.last_error,
                retry_after_seconds,
            )
            control_state = FleetDeviceControlState(
                device_id=device.device_id,
                name=device.name,
                brand=device.brand,
                model=device.model,
                protocol=device.protocol,
                transport=device.transport,
                device_status=device.status,
                eligibility="eligible",
                eligibility_reason=None,
                control_state="error",
                desired_percent=desired_percent,
                desired_updated_at=desired_updated_at,
                desired_source=desired_source,
                desired_source_priority=desired_source_priority,
                last_sent_percent=preserved_fields["last_sent_percent"] or desired_percent,
                last_applied_percent=preserved_fields["last_applied_percent"],
                telemetry_confirmed=False,
                last_command=resolved_target.command_key,
                last_resolved_value=resolved_target.resolved_value,
                last_resolved_unit=resolved_target.resolved_unit,
                last_dispatch_outcome="error",
                last_dispatch_at=self._string_or_none(preserved_fields["last_dispatch_at"]),
                last_error=previous_state.last_error,
                note=note,
            )
            return control_state, self._build_dispatch_result(
                control_state,
                diagnostics={
                    "backoff_active": True,
                    "retry_after_seconds": retry_after_seconds,
                    **({} if retry_backoff is None else retry_backoff.diagnostics),
                },
            )

        if not self._should_attempt_dispatch(previous_state, desired_percent, desired_updated_at):
            control_state = FleetDeviceControlState(
                device_id=device.device_id,
                name=device.name,
                brand=device.brand,
                model=device.model,
                protocol=device.protocol,
                transport=device.transport,
                device_status=device.status,
                eligibility="eligible",
                eligibility_reason=None,
                control_state="aligned",
                desired_percent=desired_percent,
                desired_updated_at=desired_updated_at,
                desired_source=desired_source,
                desired_source_priority=desired_source_priority,
                last_sent_percent=preserved_fields["last_sent_percent"] or desired_percent,
                last_applied_percent=preserved_fields["last_applied_percent"] or desired_percent,
                telemetry_confirmed=False,
                last_command=resolved_target.command_key,
                last_resolved_value=resolved_target.resolved_value,
                last_resolved_unit=resolved_target.resolved_unit,
                last_dispatch_outcome="ok",
                last_dispatch_at=preserved_fields["last_dispatch_at"],
                last_error=None,
                note="Target gia allineato con l'ultimo invio utile. Conferma telemetrica non disponibile.",
            )
            return control_state, self._build_dispatch_result(control_state)

        response = command_service.send_active_power_limit_value(device.device_id, desired_percent)
        dispatch_at = self._utc_now()
        if response is None:
            retry_delay_seconds = self._record_command_retry_backoff(
                device_id=device.device_id,
                protocol=device.protocol,
                desired_percent=desired_percent,
                desired_updated_at=desired_updated_at,
                error_message="Device non trovato.",
                diagnostics=None,
            )
            control_state = FleetDeviceControlState(
                device_id=device.device_id,
                name=device.name,
                brand=device.brand,
                model=device.model,
                protocol=device.protocol,
                transport=device.transport,
                device_status=device.status,
                eligibility="eligible",
                eligibility_reason=None,
                control_state="error",
                desired_percent=desired_percent,
                desired_updated_at=desired_updated_at,
                desired_source=desired_source,
                desired_source_priority=desired_source_priority,
                last_sent_percent=desired_percent,
                last_applied_percent=None,
                telemetry_confirmed=False,
                last_command=resolved_target.command_key,
                last_resolved_value=resolved_target.resolved_value,
                last_resolved_unit=resolved_target.resolved_unit,
                last_dispatch_outcome="error",
                last_dispatch_at=dispatch_at,
                last_error="Device non trovato.",
                note=self._build_error_retry_note(
                    "Il device non e piu disponibile nel backend.",
                    retry_delay_seconds,
                ),
            )
            return control_state, self._build_dispatch_result(
                control_state,
                diagnostics={"retry_after_seconds": retry_delay_seconds},
            )

        diagnostics = dict(response.diagnostics)
        response_error = diagnostics.get("error")
        response_error_text = str(response_error) if response_error else None
        if response.success:
            self._clear_command_retry_backoff(device.device_id)
            command_resolved_value = self._float_or_none(diagnostics.get("resolved_value"))
            command_resolved_unit = self._string_or_none(diagnostics.get("resolved_unit"))
            if readback.supported:
                control_state = FleetDeviceControlState(
                    device_id=device.device_id,
                    name=device.name,
                    brand=device.brand,
                    model=device.model,
                    protocol=device.protocol,
                    transport=device.transport,
                    device_status=device.status,
                    eligibility="eligible",
                    eligibility_reason=None,
                    control_state="aligned",
                    desired_percent=desired_percent,
                    desired_updated_at=desired_updated_at,
                    desired_source=desired_source,
                    desired_source_priority=desired_source_priority,
                    last_sent_percent=desired_percent,
                    last_applied_percent=None,
                    telemetry_confirmed=False,
                    last_command=response.command,
                    last_resolved_value=command_resolved_value,
                    last_resolved_unit=command_resolved_unit,
                    last_dispatch_outcome="ok",
                    last_dispatch_at=dispatch_at,
                    last_error=None,
                    note=self._build_post_dispatch_pending_note(readback),
                )
            else:
                control_state = FleetDeviceControlState(
                    device_id=device.device_id,
                    name=device.name,
                    brand=device.brand,
                    model=device.model,
                    protocol=device.protocol,
                    transport=device.transport,
                    device_status=device.status,
                    eligibility="eligible",
                    eligibility_reason=None,
                    control_state="aligned",
                    desired_percent=desired_percent,
                    desired_updated_at=desired_updated_at,
                    desired_source=desired_source,
                    desired_source_priority=desired_source_priority,
                    last_sent_percent=desired_percent,
                    last_applied_percent=desired_percent,
                    telemetry_confirmed=False,
                    last_command=response.command,
                    last_resolved_value=command_resolved_value,
                    last_resolved_unit=command_resolved_unit,
                    last_dispatch_outcome="ok",
                    last_dispatch_at=dispatch_at,
                    last_error=None,
                    note="Comando accettato dal driver. Il modello non espone un readback telemetrico del setpoint.",
                )
        else:
            error_stage = self._string_or_none(diagnostics.get("stage"))
            retry_delay_seconds = self._record_command_retry_backoff(
                device_id=device.device_id,
                protocol=device.protocol,
                desired_percent=desired_percent,
                desired_updated_at=desired_updated_at,
                error_message=response_error_text or response.message,
                diagnostics=diagnostics,
            )
            control_state = FleetDeviceControlState(
                device_id=device.device_id,
                name=device.name,
                brand=device.brand,
                model=device.model,
                protocol=device.protocol,
                transport=device.transport,
                device_status=device.status,
                eligibility="eligible",
                eligibility_reason=None,
                control_state="error",
                desired_percent=desired_percent,
                desired_updated_at=desired_updated_at,
                desired_source=desired_source,
                desired_source_priority=desired_source_priority,
                last_sent_percent=desired_percent,
                last_applied_percent=None,
                telemetry_confirmed=False,
                last_command=response.command,
                last_resolved_value=self._float_or_none(diagnostics.get("resolved_value")),
                last_resolved_unit=self._string_or_none(diagnostics.get("resolved_unit")),
                last_dispatch_outcome="error",
                last_dispatch_at=dispatch_at,
                last_error=response_error_text or response.message,
                note=self._build_error_retry_note(
                    self._build_error_note(error_stage, response_error_text or response.message),
                    retry_delay_seconds,
                ),
            )
            diagnostics["retry_after_seconds"] = retry_delay_seconds
        return self._finalize_control_state(
            device_id=device.device_id,
            control_state=control_state,
            diagnostics=diagnostics,
        )

    def _should_attempt_dispatch(
        self,
        previous_state: FleetDeviceControlState | None,
        desired_percent: float,
        desired_updated_at: str,
    ) -> bool:
        if previous_state is None:
            return True
        if previous_state.desired_updated_at != desired_updated_at:
            return True
        if previous_state.desired_percent != desired_percent:
            return True
        if previous_state.control_state in {"blocked", "error", "idle"}:
            return True
        if previous_state.last_dispatch_at is None:
            return True
        if previous_state.last_sent_percent != desired_percent:
            return True
        return False

    def _has_active_endpoint_backoff(self, device: object) -> bool:
        if not hasattr(device, "connection_settings"):
            return False
        return endpoint_runtime_service.get_backoff_decision(device).active

    def _endpoint_backoff_note(self, device: object) -> str | None:
        if not hasattr(device, "connection_settings"):
            return None
        decision = endpoint_runtime_service.get_backoff_decision(device)
        if not decision.active:
            return None
        endpoint_label = decision.endpoint_label or "endpoint condiviso"
        retry_seconds = int(ceil(max(0.0, decision.remaining_backoff_seconds)))
        return (
            f"Endpoint {endpoint_label} in cooldown comunicazione: invio sospeso "
            f"per circa {retry_seconds} s."
        )

    def _prune_command_retry_backoffs(
        self,
        *,
        active_device_ids: set[str],
        desired_percent: float,
        desired_updated_at: str,
    ) -> None:
        with self._command_retry_backoff_lock:
            self._command_retry_backoffs = {
                device_id: backoff
                for device_id, backoff in self._command_retry_backoffs.items()
                if device_id in active_device_ids
                and backoff.desired_percent == desired_percent
                and backoff.desired_updated_at == desired_updated_at
            }

    def _remaining_command_retry_backoff(
        self,
        *,
        device_id: str,
        desired_percent: float,
        desired_updated_at: str,
    ) -> int | None:
        with self._command_retry_backoff_lock:
            backoff = self._command_retry_backoffs.get(device_id)
            if backoff is None:
                return None
            if (
                backoff.desired_percent != desired_percent
                or backoff.desired_updated_at != desired_updated_at
            ):
                self._command_retry_backoffs.pop(device_id, None)
                return None
            remaining_seconds = backoff.next_retry_monotonic - self._now_monotonic()
            if remaining_seconds <= 0:
                return None
            return ceil(remaining_seconds)

    def _record_command_retry_backoff(
        self,
        *,
        device_id: str,
        protocol: str,
        desired_percent: float,
        desired_updated_at: str,
        error_message: str,
        diagnostics: dict[str, str | int | float | bool] | None,
    ) -> int:
        with self._command_retry_backoff_lock:
            previous = self._command_retry_backoffs.get(device_id)
            if (
                previous is not None
                and previous.desired_percent == desired_percent
                and previous.desired_updated_at == desired_updated_at
            ):
                consecutive_errors = previous.consecutive_errors + 1
            else:
                consecutive_errors = 1

            retry_delay_seconds = self._compute_command_retry_delay_seconds(
                protocol=protocol,
                consecutive_errors=consecutive_errors,
            )
            self._command_retry_backoffs[device_id] = _CommandRetryBackoff(
                desired_percent=desired_percent,
                desired_updated_at=desired_updated_at,
                next_retry_monotonic=self._now_monotonic() + retry_delay_seconds,
                consecutive_errors=consecutive_errors,
                last_error=error_message,
                diagnostics={} if diagnostics is None else dict(diagnostics),
            )
        return retry_delay_seconds

    def _clear_command_retry_backoff(self, device_id: str) -> None:
        with self._command_retry_backoff_lock:
            self._command_retry_backoffs.pop(device_id, None)

    def _get_command_retry_backoff(self, device_id: str) -> _CommandRetryBackoff | None:
        with self._command_retry_backoff_lock:
            return self._command_retry_backoffs.get(device_id)

    def _compute_command_retry_delay_seconds(
        self,
        *,
        protocol: str,
        consecutive_errors: int,
    ) -> int:
        base_delay_seconds = 30 if protocol == "aurora" else 15
        return min(300, base_delay_seconds * (2 ** max(0, consecutive_errors - 1)))

    def _build_retry_backoff_note(
        self,
        last_error: str | None,
        retry_after_seconds: int,
    ) -> str:
        prefix = (
            f"Ultimo invio non riuscito: {last_error}"
            if last_error
            else "Ultimo invio non riuscito."
        )
        return f"{prefix} Nuovo tentativo tra circa {retry_after_seconds} s."

    def _build_error_retry_note(self, base_note: str, retry_after_seconds: int) -> str:
        return f"{base_note} Nuovo tentativo tra circa {retry_after_seconds} s."

    def _finalize_control_state(
        self,
        *,
        device_id: str,
        control_state: FleetDeviceControlState,
        diagnostics: dict[str, str | int | float | bool] | None = None,
    ) -> tuple[FleetDeviceControlState, FleetDeviceDispatchResult]:
        if control_state.control_state != "error":
            self._clear_command_retry_backoff(device_id)
        return control_state, self._build_dispatch_result(
            control_state,
            diagnostics=diagnostics,
        )

    def _evaluate_readback(
        self,
        *,
        device: object,
        resolved_target: _ResolvedFleetTarget,
        desired_percent: float,
        reference_timestamp: str,
    ) -> _TelemetryReadbackStatus:
        inverter_model = resolved_target.inverter_model
        if inverter_model is None:
            return _TelemetryReadbackStatus(
                supported=False,
                fresh=False,
                confirmed=False,
                observed_percent=None,
                observed_value=None,
                observed_unit=None,
                telemetry_label=None,
            )

        cache_entry = live_cache.get(device.device_id)
        evaluation = active_power_limit_readback_resolver.evaluate(
            inverter_model=inverter_model,
            telemetry=[] if cache_entry is None else cache_entry.telemetry,
            desired_percent=desired_percent,
            resolved_value=resolved_target.resolved_value,
            resolved_unit=resolved_target.resolved_unit,
            resolved_max_value=resolved_target.resolved_max_value,
        )
        cache_timestamp = None if cache_entry is None else cache_entry.timestamp
        is_fresh = self._is_timestamp_not_older(cache_timestamp, reference_timestamp)
        return _TelemetryReadbackStatus(
            supported=evaluation.supported,
            fresh=is_fresh,
            confirmed=evaluation.confirmed and is_fresh,
            observed_percent=evaluation.observed_percent,
            observed_value=evaluation.observed_value,
            observed_unit=evaluation.observed_unit,
            telemetry_label=evaluation.telemetry_label,
        )

    def _preserve_previous_command_fields(
        self,
        *,
        previous_state: FleetDeviceControlState | None,
        desired_percent: float,
        desired_updated_at: str,
    ) -> dict[str, object]:
        if previous_state is None:
            return {
                "last_sent_percent": None,
                "last_applied_percent": None,
                "last_dispatch_at": None,
            }
        if (
            previous_state.desired_updated_at != desired_updated_at
            or previous_state.desired_percent != desired_percent
        ):
            return {
                "last_sent_percent": None,
                "last_applied_percent": None,
                "last_dispatch_at": None,
            }
        return {
            "last_sent_percent": previous_state.last_sent_percent,
            "last_applied_percent": previous_state.last_applied_percent,
            "last_dispatch_at": previous_state.last_dispatch_at,
        }

    def _build_post_dispatch_pending_note(self, readback: _TelemetryReadbackStatus) -> str:
        label = readback.telemetry_label or "telemetria di readback"
        return f"Comando inviato all'inverter. Feedback telemetrico disponibile su {label} quando il polling lo aggiorna."

    def _build_readback_pending_note(self, readback: _TelemetryReadbackStatus) -> str:
        label = readback.telemetry_label or "telemetria di readback"
        if not readback.fresh:
            return f"Comando gia inviato. Il feedback telemetrico su {label} non e ancora aggiornato."
        if readback.observed_percent is None:
            return f"Feedback telemetrico disponibile su {label}, ma il valore non e ancora confrontabile col target."
        return (
            f"Feedback telemetrico da {label}: {readback.observed_percent:.1f}% osservato dopo l'invio del comando."
        )

    def _build_readback_confirmed_note(self, readback: _TelemetryReadbackStatus) -> str:
        label = readback.telemetry_label or "telemetria di readback"
        if readback.observed_percent is not None:
            return f"Setpoint confermato da {label}: {readback.observed_percent:.1f}%."
        return f"Setpoint confermato da {label}."

    def _build_dispatch_result(
        self,
        control_state: FleetDeviceControlState,
        *,
        diagnostics: dict[str, str | int | float | bool] | None = None,
    ) -> FleetDeviceDispatchResult:
        result_diagnostics: dict[str, str | int | float | bool] = {
            "device_status": control_state.device_status,
            "control_state": control_state.control_state,
            "eligibility": control_state.eligibility,
            "desired_source_priority": control_state.desired_source_priority,
            "telemetry_confirmed": control_state.telemetry_confirmed,
        }
        if control_state.desired_percent is not None:
            result_diagnostics["desired_percent"] = control_state.desired_percent
        if control_state.desired_source is not None:
            result_diagnostics["desired_source"] = control_state.desired_source
        if control_state.last_resolved_value is not None:
            result_diagnostics["resolved_value"] = control_state.last_resolved_value
        if control_state.last_resolved_unit is not None:
            result_diagnostics["resolved_unit"] = control_state.last_resolved_unit
        if control_state.last_error is not None:
            result_diagnostics["error"] = control_state.last_error
        dispatch_latency_ms = self._dispatch_latency_ms(
            control_state.desired_updated_at,
            control_state.last_dispatch_at,
        )
        if dispatch_latency_ms is not None:
            result_diagnostics["dispatch_latency_ms"] = dispatch_latency_ms
        if diagnostics:
            result_diagnostics.update(diagnostics)

        outcome = "pending"
        success = False
        if control_state.control_state == "aligned":
            outcome = "ok"
            success = True
        elif control_state.control_state == "error":
            outcome = "error"
        elif control_state.control_state == "blocked":
            outcome = "blocked"

        return FleetDeviceDispatchResult(
            device_id=control_state.device_id,
            name=control_state.name,
            brand=control_state.brand,
            model=control_state.model,
            protocol=control_state.protocol,
            transport=control_state.transport,
            outcome=outcome,
            success=success,
            message=control_state.note,
            command=control_state.last_command,
            diagnostics=result_diagnostics,
            timestamp=control_state.last_dispatch_at or self._utc_now(),
        )

    def _is_timestamp_not_older(
        self,
        candidate_timestamp: str | None,
        reference_timestamp: str | None,
    ) -> bool:
        if candidate_timestamp is None:
            return False
        if reference_timestamp is None:
            return True
        try:
            candidate = datetime.fromisoformat(candidate_timestamp)
            reference = datetime.fromisoformat(reference_timestamp)
        except ValueError:
            return False
        return candidate >= reference

    def _dispatch_latency_ms(
        self,
        desired_updated_at: str | None,
        dispatch_at: str | None,
    ) -> int | None:
        if desired_updated_at is None or dispatch_at is None:
            return None
        try:
            desired_timestamp = datetime.fromisoformat(desired_updated_at)
            dispatch_timestamp = datetime.fromisoformat(dispatch_at)
        except ValueError:
            return None
        latency_seconds = (dispatch_timestamp - desired_timestamp).total_seconds()
        return max(0, int(round(latency_seconds * 1000)))

    def _build_error_note(self, stage: str | None, message: str) -> str:
        if stage == "connect":
            return f"Connessione non riuscita: {message}"
        if stage == "profile":
            return f"Profilo non compatibile con il target richiesto: {message}"
        if stage == "configuration":
            return f"Configurazione incompleta per il comando flotta: {message}"
        if stage == "driver":
            return f"Driver non pronto al comando richiesto: {message}"
        return f"Ultimo invio non riuscito: {message}"

    def _float_or_none(self, value: object) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return None

    def _string_or_none(self, value: object) -> str | None:
        if value is None:
            return None
        return str(value)

    def _utc_now(self) -> str:
        return datetime.now(UTC).isoformat()

    def _now_monotonic(self) -> float:
        return monotonic()


fleet_dispatch_service = FleetDispatchService()
