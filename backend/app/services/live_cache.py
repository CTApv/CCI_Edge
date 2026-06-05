from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from threading import Lock

from app.config import settings
from app.schemas.device_overview_schemas import (
    DeviceOverviewDiagnostics,
    DeviceOverviewMetrics,
    DeviceTelemetryPoint,
)


@dataclass(slots=True)
class LiveCacheEntry:
    metrics: DeviceOverviewMetrics
    diagnostics: DeviceOverviewDiagnostics
    telemetry: list[DeviceTelemetryPoint]
    timestamp: str


@dataclass(slots=True, frozen=True)
class ConnectionLifecycle:
    has_seen_success: bool
    last_success_timestamp: str | None
    last_attempt_timestamp: str | None
    has_seen_full_success: bool = False
    last_full_success_timestamp: str | None = None


@dataclass(slots=True, frozen=True)
class PowerSample:
    timestamp: str
    power_kw: float


class LiveCache:
    def __init__(self) -> None:
        self._entries: dict[str, LiveCacheEntry] = {}
        self._power_history: dict[str, deque[PowerSample]] = {}
        self._connection_state: dict[str, ConnectionLifecycle] = {}
        self._history_limit = max(settings.power_history_limit, 120)
        self._lock = Lock()

    def get(self, device_id: str) -> LiveCacheEntry | None:
        with self._lock:
            return self._entries.get(device_id)

    def set(self, device_id: str, entry: LiveCacheEntry) -> None:
        with self._lock:
            self._entries[device_id] = entry
            previous_state = self._connection_state.get(
                device_id,
                ConnectionLifecycle(
                    has_seen_success=False,
                    last_success_timestamp=None,
                    last_attempt_timestamp=None,
                    has_seen_full_success=False,
                    last_full_success_timestamp=None,
                ),
            )
            is_success = _is_successful_poll_entry(entry)
            is_full_success = _is_successful_full_poll_entry(entry)
            last_contact_at = entry.diagnostics.last_contact_at or (
                entry.timestamp if is_success else previous_state.last_success_timestamp
            )
            last_valid_data_at = entry.diagnostics.last_valid_data_at or (
                entry.timestamp if is_full_success else previous_state.last_full_success_timestamp
            )
            self._connection_state[device_id] = ConnectionLifecycle(
                has_seen_success=previous_state.has_seen_success or is_success,
                last_success_timestamp=last_contact_at,
                last_attempt_timestamp=entry.timestamp,
                has_seen_full_success=previous_state.has_seen_full_success or is_full_success,
                last_full_success_timestamp=last_valid_data_at,
            )

    def get_connection_lifecycle(self, device_id: str) -> ConnectionLifecycle:
        with self._lock:
            return self._connection_state.get(
                device_id,
                ConnectionLifecycle(
                    has_seen_success=False,
                    last_success_timestamp=None,
                    last_attempt_timestamp=None,
                    has_seen_full_success=False,
                    last_full_success_timestamp=None,
                ),
            )

    def delete(self, device_id: str) -> None:
        with self._lock:
            self._entries.pop(device_id, None)
            self._power_history.pop(device_id, None)
            self._connection_state.pop(device_id, None)

    def append_power_sample(self, device_id: str, timestamp: str, power_kw: float) -> None:
        with self._lock:
            history = self._power_history.get(device_id)
            if history is None:
                history = deque(maxlen=self._history_limit)
                self._power_history[device_id] = history
            history.append(PowerSample(timestamp=timestamp, power_kw=power_kw))

    def get_power_history(self, device_id: str) -> list[PowerSample]:
        with self._lock:
            history = self._power_history.get(device_id)
            if history is None:
                return []
            return list(history)

    def get_runtime_stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "entry_count": len(self._entries),
                "power_history_device_count": len(self._power_history),
                "power_history_sample_count": sum(
                    len(samples) for samples in self._power_history.values()
                ),
                "connection_lifecycle_count": len(self._connection_state),
            }

    def prune(self, active_device_ids: Iterable[str]) -> None:
        active_ids = set(active_device_ids)
        with self._lock:
            stale_ids = [device_id for device_id in self._entries if device_id not in active_ids]
            for device_id in stale_ids:
                del self._entries[device_id]
            stale_history_ids = [
                device_id for device_id in self._power_history if device_id not in active_ids
            ]
            for device_id in stale_history_ids:
                del self._power_history[device_id]
            stale_connection_ids = [
                device_id for device_id in self._connection_state if device_id not in active_ids
            ]
            for device_id in stale_connection_ids:
                del self._connection_state[device_id]


def _is_successful_poll_entry(entry: LiveCacheEntry) -> bool:
    return (
        entry.diagnostics.last_error is None
        and "stub_mode=false" in entry.diagnostics.last_poll_status
    )


def _is_successful_full_poll_entry(entry: LiveCacheEntry) -> bool:
    return _is_successful_poll_entry(entry) and entry.diagnostics.poll_kind == "full"


live_cache = LiveCache()
