from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import monotonic

from app.schemas.device_schemas import DeviceResponse
from app.services.device_runtime import build_poll_endpoint_key, is_successful_real_poll
from app.services.live_cache import LiveCacheEntry

ENDPOINT_BACKOFF_BASE_SECONDS = 5.0
ENDPOINT_BACKOFF_MAX_SECONDS = 60.0
ENDPOINT_CONNECT_BACKOFF_PROTOCOLS = {"modbus_tcp", "sunspec", "modbus_rtu", "aurora"}


@dataclass(slots=True, frozen=True)
class EndpointBackoffDecision:
    active: bool
    endpoint_type: str | None
    endpoint_label: str | None
    consecutive_connect_failures: int
    remaining_backoff_seconds: float
    cooldown_until: str | None


@dataclass(slots=True)
class EndpointRuntimeState:
    endpoint_type: str
    endpoint_label: str
    consecutive_connect_failures: int = 0
    cooldown_until_monotonic: float = 0.0
    cooldown_until: str | None = None
    last_attempt_at: str | None = None
    last_success_at: str | None = None
    last_error_at: str | None = None
    last_error_stage: str | None = None
    last_error: str | None = None
    last_poll_status: str | None = None
    last_outcome: str = "idle"
    skipped_polls: int = 0


class EndpointRuntimeService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._states: dict[tuple[str, str], EndpointRuntimeState] = {}

    def get_backoff_decision(
        self,
        device: DeviceResponse,
        *,
        now: float | None = None,
    ) -> EndpointBackoffDecision:
        endpoint = build_poll_endpoint_key(device)
        if endpoint is None:
            return EndpointBackoffDecision(
                active=False,
                endpoint_type=None,
                endpoint_label=None,
                consecutive_connect_failures=0,
                remaining_backoff_seconds=0.0,
                cooldown_until=None,
            )

        endpoint_type, endpoint_label = endpoint
        current_time = monotonic() if now is None else now
        with self._lock:
            state = self._states.get(endpoint)
            if state is None:
                return EndpointBackoffDecision(
                    active=False,
                    endpoint_type=endpoint_type,
                    endpoint_label=endpoint_label,
                    consecutive_connect_failures=0,
                    remaining_backoff_seconds=0.0,
                    cooldown_until=None,
                )

            remaining_seconds = max(0.0, state.cooldown_until_monotonic - current_time)
            return EndpointBackoffDecision(
                active=remaining_seconds > 0.0,
                endpoint_type=endpoint_type,
                endpoint_label=endpoint_label,
                consecutive_connect_failures=state.consecutive_connect_failures,
                remaining_backoff_seconds=remaining_seconds,
                cooldown_until=state.cooldown_until,
            )

    def record_poll_result(
        self,
        device: DeviceResponse,
        entry: LiveCacheEntry,
        *,
        now: float | None = None,
    ) -> None:
        endpoint = build_poll_endpoint_key(device)
        if endpoint is None:
            return

        current_time = monotonic() if now is None else now
        state = self._get_or_create_state(endpoint)
        stage = self._extract_stage(entry.diagnostics.last_poll_status)

        with self._lock:
            state.last_attempt_at = entry.timestamp
            state.last_poll_status = entry.diagnostics.last_poll_status

            if is_successful_real_poll(entry):
                state.consecutive_connect_failures = 0
                state.cooldown_until_monotonic = 0.0
                state.cooldown_until = None
                state.last_success_at = entry.timestamp
                state.last_error_at = None
                state.last_error_stage = None
                state.last_error = None
                state.last_outcome = "success"
                return

            state.last_error_at = entry.timestamp
            state.last_error_stage = stage
            state.last_error = entry.diagnostics.last_error

            if self._should_apply_connect_backoff(device, stage):
                state.consecutive_connect_failures += 1
                cooldown_seconds = min(
                    ENDPOINT_BACKOFF_MAX_SECONDS,
                    ENDPOINT_BACKOFF_BASE_SECONDS
                    * (2 ** max(0, state.consecutive_connect_failures - 1)),
                )
                state.cooldown_until_monotonic = current_time + cooldown_seconds
                state.cooldown_until = self._utc_future_iso(cooldown_seconds)
                state.last_outcome = "connect_error"
                return

            state.consecutive_connect_failures = 0
            state.cooldown_until_monotonic = 0.0
            state.cooldown_until = None
            state.last_outcome = "device_error"

    def record_backoff_skip(
        self,
        device: DeviceResponse,
        *,
        now: float | None = None,
    ) -> None:
        endpoint = build_poll_endpoint_key(device)
        if endpoint is None:
            return

        state = self._get_or_create_state(endpoint)
        with self._lock:
            state.last_attempt_at = self._utc_now_iso()
            state.last_outcome = "cooldown_skip"
            state.skipped_polls += 1

            current_time = monotonic() if now is None else now
            remaining_seconds = max(0.0, state.cooldown_until_monotonic - current_time)
            if remaining_seconds <= 0.0:
                state.cooldown_until_monotonic = 0.0
                state.cooldown_until = None

    def prune(self, active_devices: list[DeviceResponse]) -> None:
        active_endpoints = {
            endpoint
            for device in active_devices
            if (endpoint := build_poll_endpoint_key(device)) is not None
        }
        with self._lock:
            stale_endpoints = [
                endpoint for endpoint in self._states if endpoint not in active_endpoints
            ]
            for endpoint in stale_endpoints:
                del self._states[endpoint]

    def get_snapshots(self, devices: list[DeviceResponse]) -> list[dict[str, object]]:
        grouped: dict[tuple[str, str], list[DeviceResponse]] = defaultdict(list)
        for device in devices:
            endpoint = build_poll_endpoint_key(device)
            if endpoint is None:
                continue
            grouped[endpoint].append(device)

        current_time = monotonic()
        snapshots: list[dict[str, object]] = []
        with self._lock:
            for endpoint, endpoint_devices in grouped.items():
                endpoint_type, endpoint_label = endpoint
                state = self._states.get(endpoint)
                if state is None:
                    state = EndpointRuntimeState(
                        endpoint_type=endpoint_type,
                        endpoint_label=endpoint_label,
                    )

                remaining_seconds = max(0.0, state.cooldown_until_monotonic - current_time)
                online_count = sum(
                    1 for device in endpoint_devices if str(device.status).lower() == "online"
                )
                pending_count = sum(
                    1 for device in endpoint_devices if str(device.status).lower() == "pending"
                )
                offline_count = sum(
                    1 for device in endpoint_devices if str(device.status).lower() == "offline"
                )
                snapshots.append(
                    {
                        "endpoint_type": endpoint_type,
                        "endpoint_label": endpoint_label,
                        "device_count": len(endpoint_devices),
                        "online_count": online_count,
                        "pending_count": pending_count,
                        "offline_count": offline_count,
                        "shared": len(endpoint_devices) > 1,
                        "state": self._resolve_endpoint_state(
                            state=state,
                            remaining_backoff_seconds=remaining_seconds,
                        ),
                        "consecutive_connect_failures": state.consecutive_connect_failures,
                        "remaining_backoff_seconds": round(remaining_seconds, 3),
                        "cooldown_until": state.cooldown_until,
                        "last_attempt_at": state.last_attempt_at,
                        "last_success_at": state.last_success_at,
                        "last_error_at": state.last_error_at,
                        "last_error_stage": state.last_error_stage,
                        "last_error": state.last_error,
                        "last_poll_status": state.last_poll_status,
                        "last_outcome": state.last_outcome,
                        "skipped_polls": state.skipped_polls,
                        "devices": [
                            f"{device.name} | {device.brand} | {device.model}"
                            for device in sorted(endpoint_devices, key=lambda item: item.name.lower())
                        ],
                    }
                )

        snapshots.sort(
            key=lambda item: (
                item["state"] != "cooldown",
                -int(item["offline_count"]),
                -int(item["pending_count"]),
                -int(item["consecutive_connect_failures"]),
                -int(item["device_count"]),
                str(item["endpoint_label"]).lower(),
            )
        )
        return snapshots

    def _get_or_create_state(self, endpoint: tuple[str, str]) -> EndpointRuntimeState:
        with self._lock:
            state = self._states.get(endpoint)
            if state is None:
                endpoint_type, endpoint_label = endpoint
                state = EndpointRuntimeState(
                    endpoint_type=endpoint_type,
                    endpoint_label=endpoint_label,
                )
                self._states[endpoint] = state
            return state

    def _should_apply_connect_backoff(self, device: DeviceResponse, stage: str | None) -> bool:
        return (
            device.protocol in ENDPOINT_CONNECT_BACKOFF_PROTOCOLS
            and stage == "connect"
        )

    def _resolve_endpoint_state(
        self,
        *,
        state: EndpointRuntimeState,
        remaining_backoff_seconds: float,
    ) -> str:
        if remaining_backoff_seconds > 0.0:
            return "cooldown"
        if state.last_outcome == "success":
            return "healthy"
        if state.last_error is not None:
            return "degraded"
        return "idle"

    def _extract_stage(self, last_poll_status: str) -> str | None:
        for segment in last_poll_status.split(";"):
            normalized = segment.strip()
            if normalized.startswith("stage="):
                return normalized.split("=", 1)[1].strip() or None
        return None

    def _utc_now_iso(self) -> str:
        return datetime.now(UTC).isoformat()

    def _utc_future_iso(self, delta_seconds: float) -> str:
        return (datetime.now(UTC) + timedelta(seconds=delta_seconds)).isoformat()


endpoint_runtime_service = EndpointRuntimeService()
