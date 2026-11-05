from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from math import ceil
from threading import Lock
from time import monotonic

from app.core.connection_settings import get_poll_retry_count, get_poll_timeout_seconds
from app.schemas.device_schemas import DeviceResponse
from app.services.device_runtime import build_poll_endpoint_key, uses_serial_like_polling
from app.services.live_cache import LiveCacheEntry

ADAPTIVE_MIN_SAMPLES = 8
ADAPTIVE_STRONG_MIN_SAMPLES = 24
ADAPTIVE_SAMPLE_WINDOW = 40
ADAPTIVE_RECALCULATE_EVERY = 4
ADAPTIVE_STABLE_SUCCESS_RATE = 0.98
ADAPTIVE_STRONG_SUCCESS_RATE = 0.995
DEVICE_BACKOFF_FAILURE_THRESHOLD = 2
DEVICE_BACKOFF_BASE_SECONDS = 10.0
DEVICE_BACKOFF_MAX_SECONDS = 120.0


@dataclass(slots=True, frozen=True)
class AdaptivePollPolicy:
    timeout_seconds: float
    retries: int
    inter_request_delay_ms: float
    mode: str
    sample_count: int
    recent_success_rate: float | None


@dataclass(slots=True, frozen=True)
class DeviceBackoffDecision:
    active: bool
    device_id: str
    device_name: str
    consecutive_failures: int
    remaining_backoff_seconds: float


@dataclass(slots=True)
class EndpointAdaptiveState:
    endpoint_type: str
    endpoint_label: str
    latency_samples_ms: deque[float] = field(
        default_factory=lambda: deque(maxlen=ADAPTIVE_SAMPLE_WINDOW)
    )
    outcome_samples: deque[bool] = field(
        default_factory=lambda: deque(maxlen=ADAPTIVE_SAMPLE_WINDOW)
    )
    request_outcome_samples: deque[bool] = field(
        default_factory=lambda: deque(maxlen=ADAPTIVE_SAMPLE_WINDOW)
    )
    effective_timeout_seconds: float | None = None
    effective_retries: int | None = None
    effective_inter_request_delay_ms: float | None = None
    configured_timeout_seconds: float = 0.0
    configured_retries: int = 0
    configured_inter_request_delay_ms: float = 0.0
    mode: str = "warming"
    samples_since_recalculation: int = 0


@dataclass(slots=True)
class DeviceAdaptiveState:
    device_id: str
    device_name: str
    endpoint_type: str
    endpoint_label: str
    consecutive_failures: int = 0
    cooldown_until_monotonic: float = 0.0
    skipped_polls: int = 0


class AdaptiveCommunicationService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._endpoint_states: dict[tuple[str, str], EndpointAdaptiveState] = {}
        self._device_states: dict[str, DeviceAdaptiveState] = {}

    def resolve_poll_policy(
        self,
        device: DeviceResponse,
        *,
        configured_timeout_seconds: float,
        configured_retries: int,
    ) -> AdaptivePollPolicy:
        configured_delay_ms = self._configured_inter_request_delay_ms(device)
        if not self._is_enabled(device):
            return AdaptivePollPolicy(
                timeout_seconds=configured_timeout_seconds,
                retries=configured_retries,
                inter_request_delay_ms=configured_delay_ms,
                mode="manual",
                sample_count=0,
                recent_success_rate=None,
            )

        endpoint = build_poll_endpoint_key(device)
        if endpoint is None:
            return AdaptivePollPolicy(
                timeout_seconds=configured_timeout_seconds,
                retries=configured_retries,
                inter_request_delay_ms=configured_delay_ms,
                mode="manual",
                sample_count=0,
                recent_success_rate=None,
            )

        with self._lock:
            state = self._get_or_create_endpoint_state_locked(endpoint)
            self._update_configured_limits_locked(
                state,
                configured_timeout_seconds=configured_timeout_seconds,
                configured_retries=configured_retries,
                configured_delay_ms=configured_delay_ms,
            )
            return AdaptivePollPolicy(
                timeout_seconds=round(
                    state.effective_timeout_seconds or configured_timeout_seconds,
                    2,
                ),
                retries=(
                    state.effective_retries
                    if state.effective_retries is not None
                    else configured_retries
                ),
                inter_request_delay_ms=round(
                    state.effective_inter_request_delay_ms
                    if state.effective_inter_request_delay_ms is not None
                    else configured_delay_ms,
                    1,
                ),
                mode=state.mode,
                sample_count=len(state.outcome_samples),
                recent_success_rate=self._success_rate(state),
            )

    def get_device_backoff_decision(
        self,
        device: DeviceResponse,
        *,
        now: float | None = None,
    ) -> DeviceBackoffDecision:
        current_time = monotonic() if now is None else now
        with self._lock:
            state = self._device_states.get(device.device_id)
            if state is None:
                return DeviceBackoffDecision(
                    active=False,
                    device_id=device.device_id,
                    device_name=device.name,
                    consecutive_failures=0,
                    remaining_backoff_seconds=0.0,
                )
            remaining_seconds = max(0.0, state.cooldown_until_monotonic - current_time)
            return DeviceBackoffDecision(
                active=remaining_seconds > 0.0,
                device_id=device.device_id,
                device_name=device.name,
                consecutive_failures=state.consecutive_failures,
                remaining_backoff_seconds=remaining_seconds,
            )

    def record_poll_result(
        self,
        device: DeviceResponse,
        entry: LiveCacheEntry,
        *,
        now: float | None = None,
    ) -> None:
        if "stage=endpoint_backoff" in entry.diagnostics.last_poll_status:
            return
        if "stage=device_backoff" in entry.diagnostics.last_poll_status:
            return

        endpoint = build_poll_endpoint_key(device)
        if endpoint is None or not self._is_enabled(device):
            return

        current_time = monotonic() if now is None else now
        success = entry.diagnostics.last_error is None
        stage = self._extract_stage(entry.diagnostics.last_poll_status)
        configured_timeout = get_poll_timeout_seconds(
            device.connection_settings,
            transport=device.transport,
            serial_gateway=uses_serial_like_polling(device) and device.transport == "tcp",
        )
        configured_retries = get_poll_retry_count(
            device.connection_settings,
            transport=device.transport,
            serial_gateway=uses_serial_like_polling(device) and device.transport == "tcp",
        )
        configured_delay_ms = self._configured_inter_request_delay_ms(device)

        with self._lock:
            endpoint_state = self._get_or_create_endpoint_state_locked(endpoint)
            self._update_configured_limits_locked(
                endpoint_state,
                configured_timeout_seconds=configured_timeout,
                configured_retries=configured_retries,
                configured_delay_ms=configured_delay_ms,
            )
            endpoint_state.outcome_samples.append(success)
            endpoint_state.samples_since_recalculation += 1

            device_state = self._get_or_create_device_state_locked(device, endpoint)
            if success:
                device_state.consecutive_failures = 0
                device_state.cooldown_until_monotonic = 0.0
            elif stage != "connect":
                device_state.consecutive_failures += 1
                if device_state.consecutive_failures >= DEVICE_BACKOFF_FAILURE_THRESHOLD:
                    exponent = device_state.consecutive_failures - DEVICE_BACKOFF_FAILURE_THRESHOLD
                    cooldown_seconds = min(
                        DEVICE_BACKOFF_MAX_SECONDS,
                        DEVICE_BACKOFF_BASE_SECONDS * (2**exponent),
                    )
                    device_state.cooldown_until_monotonic = current_time + cooldown_seconds

            if not success:
                self._degrade_policy_locked(endpoint_state)
            elif (
                endpoint_state.samples_since_recalculation >= ADAPTIVE_RECALCULATE_EVERY
                or len(endpoint_state.outcome_samples) == ADAPTIVE_MIN_SAMPLES
            ):
                self._recalculate_policy_locked(endpoint_state, device)

    def record_request_result(
        self,
        device: DeviceResponse,
        *,
        duration_ms: float,
        success: bool,
    ) -> None:
        endpoint = build_poll_endpoint_key(device)
        if endpoint is None or not self._is_enabled(device):
            return

        configured_timeout = get_poll_timeout_seconds(
            device.connection_settings,
            transport=device.transport,
            serial_gateway=uses_serial_like_polling(device) and device.transport == "tcp",
        )
        configured_retries = get_poll_retry_count(
            device.connection_settings,
            transport=device.transport,
            serial_gateway=uses_serial_like_polling(device) and device.transport == "tcp",
        )
        with self._lock:
            state = self._get_or_create_endpoint_state_locked(endpoint)
            self._update_configured_limits_locked(
                state,
                configured_timeout_seconds=configured_timeout,
                configured_retries=configured_retries,
                configured_delay_ms=self._configured_inter_request_delay_ms(device),
            )
            state.request_outcome_samples.append(success)
            if success and duration_ms > 0:
                state.latency_samples_ms.append(float(duration_ms))
            elif not success:
                self._degrade_policy_locked(state)

    def record_device_backoff_skip(self, device: DeviceResponse) -> None:
        with self._lock:
            state = self._device_states.get(device.device_id)
            if state is not None:
                state.skipped_polls += 1

    def prune(self, active_devices: list[DeviceResponse]) -> None:
        active_device_ids = {device.device_id for device in active_devices}
        active_endpoints = {
            endpoint
            for device in active_devices
            if (endpoint := build_poll_endpoint_key(device)) is not None
        }
        with self._lock:
            for device_id in list(self._device_states):
                if device_id not in active_device_ids:
                    del self._device_states[device_id]
            for endpoint in list(self._endpoint_states):
                if endpoint not in active_endpoints:
                    del self._endpoint_states[endpoint]

    def get_endpoint_snapshots(self, devices: list[DeviceResponse]) -> list[dict[str, object]]:
        grouped: dict[tuple[str, str], list[DeviceResponse]] = defaultdict(list)
        for device in devices:
            endpoint = build_poll_endpoint_key(device)
            if endpoint is not None:
                grouped[endpoint].append(device)

        now = monotonic()
        snapshots: list[dict[str, object]] = []
        with self._lock:
            for endpoint, endpoint_devices in grouped.items():
                state = self._endpoint_states.get(endpoint)
                quarantined_count = sum(
                    1
                    for device in endpoint_devices
                    if (
                        device_state := self._device_states.get(device.device_id)
                    ) is not None
                    and device_state.cooldown_until_monotonic > now
                )
                snapshots.append(
                    {
                        "endpoint_type": endpoint[0],
                        "endpoint_label": endpoint[1],
                        "adaptive_policy_mode": state.mode if state else "warming",
                        "adaptive_timeout_seconds": (
                            round(state.effective_timeout_seconds, 2)
                            if state and state.effective_timeout_seconds is not None
                            else None
                        ),
                        "adaptive_poll_retries": (
                            state.effective_retries if state else None
                        ),
                        "adaptive_inter_request_delay_ms": (
                            round(state.effective_inter_request_delay_ms, 1)
                            if state and state.effective_inter_request_delay_ms is not None
                            else None
                        ),
                        "adaptive_sample_count": (
                            len(state.outcome_samples) if state else 0
                        ),
                        "recent_success_rate": (
                            self._success_rate(state) if state else None
                        ),
                        "adaptive_request_p95_ms": (
                            round(request_p95_ms, 1)
                            if (
                                state
                                and (
                                    request_p95_ms := self._percentile_95(
                                        state.latency_samples_ms
                                    )
                                )
                                is not None
                            )
                            else None
                        ),
                        "quarantined_device_count": quarantined_count,
                    }
                )
        return snapshots

    def _update_configured_limits_locked(
        self,
        state: EndpointAdaptiveState,
        *,
        configured_timeout_seconds: float,
        configured_retries: int,
        configured_delay_ms: float,
    ) -> None:
        state.configured_timeout_seconds = max(0.05, float(configured_timeout_seconds))
        state.configured_retries = max(0, int(configured_retries))
        state.configured_inter_request_delay_ms = max(0.0, float(configured_delay_ms))
        if state.effective_timeout_seconds is None:
            state.effective_timeout_seconds = state.configured_timeout_seconds
        else:
            state.effective_timeout_seconds = min(
                state.effective_timeout_seconds,
                state.configured_timeout_seconds,
            )
        if state.effective_retries is None:
            state.effective_retries = state.configured_retries
        else:
            state.effective_retries = min(
                state.effective_retries,
                state.configured_retries,
            )
        if state.effective_inter_request_delay_ms is None:
            state.effective_inter_request_delay_ms = state.configured_inter_request_delay_ms
        else:
            state.effective_inter_request_delay_ms = min(
                state.effective_inter_request_delay_ms,
                state.configured_inter_request_delay_ms,
            )

    def _recalculate_policy_locked(
        self,
        state: EndpointAdaptiveState,
        device: DeviceResponse,
    ) -> None:
        state.samples_since_recalculation = 0
        sample_count = len(state.outcome_samples)
        success_rate = self._success_rate(state)
        request_success_rate = self._request_success_rate(state)
        if sample_count < ADAPTIVE_MIN_SAMPLES or success_rate is None:
            state.mode = "warming"
            return

        if (
            success_rate < ADAPTIVE_STABLE_SUCCESS_RATE
            or request_success_rate is None
            or request_success_rate < ADAPTIVE_STABLE_SUCCESS_RATE
        ):
            self._degrade_policy_locked(state)
            return

        p95_latency_ms = self._percentile_95(state.latency_samples_ms)
        request_latency_ceiling_ms = max(
            100.0,
            state.configured_timeout_seconds * 1000.0 * 0.75,
        )
        if p95_latency_ms is None or p95_latency_ms > request_latency_ceiling_ms:
            self._degrade_policy_locked(state)
            return

        timeout_floor = self._timeout_floor_seconds(device)
        target_timeout = min(
            state.configured_timeout_seconds,
            max(timeout_floor, (p95_latency_ms / 1000.0) * 1.8 + 0.1),
        )
        current_timeout = state.effective_timeout_seconds or state.configured_timeout_seconds
        if target_timeout > current_timeout or current_timeout - target_timeout >= 0.2:
            state.effective_timeout_seconds = round(target_timeout, 2)

        strong_stability = (
            success_rate >= ADAPTIVE_STRONG_SUCCESS_RATE
            and request_success_rate >= ADAPTIVE_STRONG_SUCCESS_RATE
            and sample_count >= ADAPTIVE_STRONG_MIN_SAMPLES
        )
        state.effective_retries = 0
        state.effective_inter_request_delay_ms = self._adaptive_delay_ms(
            configured_delay_ms=state.configured_inter_request_delay_ms,
            device=device,
            strong_stability=strong_stability,
        )
        state.mode = "optimized" if strong_stability else "stable"

    def _degrade_policy_locked(self, state: EndpointAdaptiveState) -> None:
        state.effective_timeout_seconds = state.configured_timeout_seconds
        state.effective_retries = min(state.configured_retries, 1)
        state.effective_inter_request_delay_ms = state.configured_inter_request_delay_ms
        state.mode = "degraded"
        state.samples_since_recalculation = 0

    def _adaptive_delay_ms(
        self,
        *,
        configured_delay_ms: float,
        device: DeviceResponse,
        strong_stability: bool,
    ) -> float:
        if configured_delay_ms <= 0:
            return 0.0
        floor_ms = 20.0 if device.transport == "tcp" else 10.0
        factor = 0.1 if strong_stability else 0.25
        return round(min(configured_delay_ms, max(floor_ms, configured_delay_ms * factor)), 1)

    def _timeout_floor_seconds(self, device: DeviceResponse) -> float:
        if device.transport == "serial":
            return 0.3
        if uses_serial_like_polling(device):
            return 0.5
        return 0.25

    def _configured_inter_request_delay_ms(self, device: DeviceResponse) -> float:
        settings = device.connection_settings
        raw_delay_ms = settings.get("inter_request_delay_ms")
        if raw_delay_ms not in {None, ""}:
            try:
                return max(0.0, float(raw_delay_ms))
            except (TypeError, ValueError):
                return 0.0
        raw_delay_seconds = settings.get("inter_request_delay_seconds")
        if raw_delay_seconds not in {None, ""}:
            try:
                return max(0.0, float(raw_delay_seconds) * 1000.0)
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    def _is_enabled(self, device: DeviceResponse) -> bool:
        raw_value = device.connection_settings.get("adaptive_communication", True)
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, (int, float)):
            return bool(raw_value)
        if isinstance(raw_value, str):
            return raw_value.strip().lower() not in {"0", "false", "no", "off"}
        return True

    def _get_or_create_endpoint_state_locked(
        self,
        endpoint: tuple[str, str],
    ) -> EndpointAdaptiveState:
        state = self._endpoint_states.get(endpoint)
        if state is None:
            state = EndpointAdaptiveState(
                endpoint_type=endpoint[0],
                endpoint_label=endpoint[1],
            )
            self._endpoint_states[endpoint] = state
        return state

    def _get_or_create_device_state_locked(
        self,
        device: DeviceResponse,
        endpoint: tuple[str, str],
    ) -> DeviceAdaptiveState:
        state = self._device_states.get(device.device_id)
        if state is None or (state.endpoint_type, state.endpoint_label) != endpoint:
            state = DeviceAdaptiveState(
                device_id=device.device_id,
                device_name=device.name,
                endpoint_type=endpoint[0],
                endpoint_label=endpoint[1],
            )
            self._device_states[device.device_id] = state
        else:
            state.device_name = device.name
        return state

    def _success_rate(self, state: EndpointAdaptiveState) -> float | None:
        if not state.outcome_samples:
            return None
        return round(sum(1 for outcome in state.outcome_samples if outcome) / len(state.outcome_samples), 3)

    def _request_success_rate(self, state: EndpointAdaptiveState) -> float | None:
        if not state.request_outcome_samples:
            return None
        return round(
            sum(1 for outcome in state.request_outcome_samples if outcome)
            / len(state.request_outcome_samples),
            3,
        )

    def _percentile_95(self, values: deque[float]) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = max(0, min(len(ordered) - 1, ceil(len(ordered) * 0.95) - 1))
        return float(ordered[index])

    def _extract_stage(self, last_poll_status: str) -> str | None:
        for segment in last_poll_status.split(";"):
            normalized = segment.strip()
            if normalized.startswith("stage="):
                return normalized.split("=", 1)[1].strip() or None
        return None


adaptive_communication_service = AdaptiveCommunicationService()
