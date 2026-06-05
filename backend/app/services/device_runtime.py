from datetime import UTC, datetime

from app.core.connection_settings import (
    get_connection_retry_count,
    get_connection_timeout_seconds,
)
from app.schemas.device_schemas import DeviceResponse
from app.services.live_cache import ConnectionLifecycle, LiveCacheEntry

DEFAULT_POLL_INTERVAL_SECONDS = 15.0
MAX_POLL_INTERVAL_SECONDS = 300.0
DEFAULT_SERIAL_FULL_POLL_INTERVAL_MULTIPLIER = 4.0
MIN_SERIAL_FULL_POLL_INTERVAL_SECONDS = 60.0
MAX_FULL_POLL_INTERVAL_SECONDS = 900.0
MIN_CONTACT_GRACE_SECONDS = 180.0
MIN_SERIAL_CONTACT_GRACE_SECONDS = 600.0
MAX_CONTACT_GRACE_SECONDS = 1800.0
MAX_SERIAL_CONTACT_GRACE_SECONDS = 7200.0
TCP_CONTACT_GRACE_MULTIPLIER = 8.0
SERIAL_CONTACT_GRACE_MULTIPLIER = 24.0
TCP_ENDPOINT_CONTACT_GRACE_MULTIPLIER = 1.25
SERIAL_ENDPOINT_CONTACT_GRACE_MULTIPLIER = 2.0
MIN_FULL_DATA_GRACE_SECONDS = 120.0
MIN_SERIAL_FULL_DATA_GRACE_SECONDS = 300.0
MAX_FULL_DATA_GRACE_SECONDS = 1800.0
MAX_SERIAL_FULL_DATA_GRACE_SECONDS = 14400.0
FULL_DATA_GRACE_MULTIPLIER = 2.0
TCP_ENDPOINT_FULL_DATA_GRACE_MULTIPLIER = 1.0
SERIAL_ENDPOINT_FULL_DATA_GRACE_MULTIPLIER = 2.0
MIN_PARTIAL_GRACE_SECONDS = 180.0
MIN_SERIAL_PARTIAL_GRACE_SECONDS = 480.0
MAX_PARTIAL_GRACE_SECONDS = 1800.0
MAX_SERIAL_PARTIAL_GRACE_SECONDS = 14400.0
PARTIAL_GRACE_MULTIPLIER = 6.0
TCP_ENDPOINT_PARTIAL_GRACE_MULTIPLIER = 1.0
SERIAL_ENDPOINT_PARTIAL_GRACE_MULTIPLIER = 2.0
RUNTIME_POLL_PROTOCOLS = {"modbus_tcp", "modbus_rtu", "sunspec", "aurora", "delta_rs485"}
SERIAL_LIKE_POLL_PROTOCOLS = {"modbus_rtu", "aurora", "delta_rs485"}


def uses_serial_like_polling(device: object) -> bool:
    transport = getattr(device, "transport", None)
    if transport == "serial":
        return True
    return transport == "tcp" and getattr(device, "protocol", None) in SERIAL_LIKE_POLL_PROTOCOLS


def get_effective_poll_interval_seconds(device: DeviceResponse) -> float:
    try:
        poll_interval_seconds = float(
            device.connection_settings.get("poll_interval_seconds", DEFAULT_POLL_INTERVAL_SECONDS)
        )
    except (TypeError, ValueError):
        return DEFAULT_POLL_INTERVAL_SECONDS

    if poll_interval_seconds <= 0:
        return DEFAULT_POLL_INTERVAL_SECONDS

    return min(poll_interval_seconds, MAX_POLL_INTERVAL_SECONDS)


def get_effective_heartbeat_interval_seconds(device: DeviceResponse) -> float:
    try:
        heartbeat_interval_seconds = float(
            device.connection_settings.get(
                "heartbeat_interval_seconds",
                get_effective_poll_interval_seconds(device),
            )
        )
    except (TypeError, ValueError):
        return get_effective_poll_interval_seconds(device)

    if heartbeat_interval_seconds <= 0:
        return get_effective_poll_interval_seconds(device)

    return min(heartbeat_interval_seconds, MAX_POLL_INTERVAL_SECONDS)


def get_effective_full_poll_interval_seconds(device: DeviceResponse) -> float:
    try:
        explicit_interval = device.connection_settings.get("full_poll_interval_seconds")
        if explicit_interval not in {None, ""}:
            full_poll_interval_seconds = float(explicit_interval)
        elif uses_serial_like_polling(device):
            full_poll_interval_seconds = max(
                MIN_SERIAL_FULL_POLL_INTERVAL_SECONDS,
                get_effective_poll_interval_seconds(device)
                * DEFAULT_SERIAL_FULL_POLL_INTERVAL_MULTIPLIER,
            )
        else:
            full_poll_interval_seconds = get_effective_poll_interval_seconds(device)
    except (TypeError, ValueError):
        return (
            max(
                MIN_SERIAL_FULL_POLL_INTERVAL_SECONDS,
                get_effective_poll_interval_seconds(device)
                * DEFAULT_SERIAL_FULL_POLL_INTERVAL_MULTIPLIER,
            )
            if uses_serial_like_polling(device)
            else get_effective_poll_interval_seconds(device)
        )

    if full_poll_interval_seconds <= 0:
        return get_effective_poll_interval_seconds(device)

    return min(full_poll_interval_seconds, MAX_FULL_POLL_INTERVAL_SECONDS)


def get_effective_timeout_seconds(device: DeviceResponse) -> float:
    timeout_seconds = get_connection_timeout_seconds(device.connection_settings)
    return min(timeout_seconds, 120.0)


def get_effective_retry_count(device: DeviceResponse) -> int:
    return get_connection_retry_count(device.connection_settings)


def get_effective_write_timeout_seconds(device: DeviceResponse) -> float:
    timeout_seconds = get_connection_timeout_seconds(device.connection_settings)
    return min(timeout_seconds, 120.0)


def get_effective_write_retry_count(device: DeviceResponse) -> int:
    return get_connection_retry_count(device.connection_settings)


def estimate_serial_endpoint_sweep_seconds(
    device: DeviceResponse,
    endpoint_device_count: int,
) -> float:
    if not uses_serial_like_polling(device):
        return 0.0

    peer_count = max(1, int(endpoint_device_count))
    per_device_budget_seconds = max(
        0.5,
        get_effective_timeout_seconds(device) * (get_effective_retry_count(device) + 1),
    )
    return peer_count * per_device_budget_seconds


def estimate_shared_endpoint_sweep_seconds(
    device: DeviceResponse,
    endpoint_device_count: int,
) -> float:
    peer_count = max(1, int(endpoint_device_count))
    if peer_count <= 1:
        return 0.0

    if uses_serial_like_polling(device):
        return estimate_serial_endpoint_sweep_seconds(device, endpoint_device_count)

    per_device_budget_seconds = max(
        0.25,
        get_effective_timeout_seconds(device) * (get_effective_retry_count(device) + 1),
        get_effective_full_poll_interval_seconds(device),
    )
    return peer_count * per_device_budget_seconds


def is_successful_real_poll(entry: LiveCacheEntry) -> bool:
    return (
        entry.diagnostics.last_error is None
        and "stub_mode=false" in entry.diagnostics.last_poll_status
    )


def is_successful_full_poll(entry: LiveCacheEntry) -> bool:
    return is_successful_real_poll(entry) and entry.diagnostics.poll_kind == "full"


def is_recent_full_data(
    device: DeviceResponse,
    lifecycle: ConnectionLifecycle,
    *,
    endpoint_device_count: int = 1,
) -> bool:
    if lifecycle.last_full_success_timestamp is None:
        return False

    age_seconds = _entry_age_seconds(lifecycle.last_full_success_timestamp)
    if age_seconds is None:
        return False

    minimum_grace_seconds = (
        MIN_SERIAL_FULL_DATA_GRACE_SECONDS
        if uses_serial_like_polling(device)
        else MIN_FULL_DATA_GRACE_SECONDS
    )
    max_grace_seconds = (
        MAX_SERIAL_FULL_DATA_GRACE_SECONDS
        if uses_serial_like_polling(device)
        else MAX_FULL_DATA_GRACE_SECONDS
    )
    endpoint_grace_seconds = estimate_shared_endpoint_sweep_seconds(
        device,
        endpoint_device_count,
    ) * (
        SERIAL_ENDPOINT_FULL_DATA_GRACE_MULTIPLIER
        if uses_serial_like_polling(device)
        else TCP_ENDPOINT_FULL_DATA_GRACE_MULTIPLIER
    )
    freshness_window_seconds = min(
        max_grace_seconds,
        max(
            minimum_grace_seconds,
            get_effective_full_poll_interval_seconds(device) * FULL_DATA_GRACE_MULTIPLIER,
            endpoint_grace_seconds,
        ),
    )
    return age_seconds <= freshness_window_seconds


def is_recent_last_success(
    device: DeviceResponse,
    lifecycle: ConnectionLifecycle,
    *,
    endpoint_device_count: int = 1,
) -> bool:
    if lifecycle.last_success_timestamp is None:
        return False

    age_seconds = _entry_age_seconds(lifecycle.last_success_timestamp)
    if age_seconds is None:
        return False

    grace_multiplier = (
        SERIAL_CONTACT_GRACE_MULTIPLIER
        if uses_serial_like_polling(device)
        else TCP_CONTACT_GRACE_MULTIPLIER
    )
    minimum_grace_seconds = (
        MIN_SERIAL_CONTACT_GRACE_SECONDS
        if uses_serial_like_polling(device)
        else MIN_CONTACT_GRACE_SECONDS
    )
    max_grace_seconds = (
        MAX_SERIAL_CONTACT_GRACE_SECONDS
        if uses_serial_like_polling(device)
        else MAX_CONTACT_GRACE_SECONDS
    )
    endpoint_grace_seconds = estimate_shared_endpoint_sweep_seconds(
        device,
        endpoint_device_count,
    ) * (
        SERIAL_ENDPOINT_CONTACT_GRACE_MULTIPLIER
        if uses_serial_like_polling(device)
        else TCP_ENDPOINT_CONTACT_GRACE_MULTIPLIER
    )
    grace_window_seconds = min(
        max_grace_seconds,
        max(
            minimum_grace_seconds,
            get_effective_heartbeat_interval_seconds(device) * grace_multiplier,
            endpoint_grace_seconds,
        ),
    )
    return age_seconds <= grace_window_seconds


def is_within_partial_grace(
    device: DeviceResponse,
    lifecycle: ConnectionLifecycle,
    *,
    endpoint_device_count: int = 1,
) -> bool:
    reference_timestamp = (
        lifecycle.last_full_success_timestamp or lifecycle.last_success_timestamp
    )
    if reference_timestamp is None:
        return False

    age_seconds = _entry_age_seconds(reference_timestamp)
    if age_seconds is None:
        return False

    minimum_grace_seconds = (
        MIN_SERIAL_PARTIAL_GRACE_SECONDS
        if uses_serial_like_polling(device)
        else MIN_PARTIAL_GRACE_SECONDS
    )
    max_grace_seconds = (
        MAX_SERIAL_PARTIAL_GRACE_SECONDS
        if uses_serial_like_polling(device)
        else MAX_PARTIAL_GRACE_SECONDS
    )
    endpoint_grace_seconds = estimate_shared_endpoint_sweep_seconds(
        device,
        endpoint_device_count,
    ) * (
        SERIAL_ENDPOINT_PARTIAL_GRACE_MULTIPLIER
        if uses_serial_like_polling(device)
        else TCP_ENDPOINT_PARTIAL_GRACE_MULTIPLIER
    )
    grace_window_seconds = min(
        max_grace_seconds,
        max(
            minimum_grace_seconds,
            get_effective_full_poll_interval_seconds(device) * PARTIAL_GRACE_MULTIPLIER,
            endpoint_grace_seconds,
        ),
    )
    return age_seconds <= grace_window_seconds


def _entry_age_seconds(timestamp_value: str) -> float | None:
    try:
        timestamp = datetime.fromisoformat(timestamp_value)
    except ValueError:
        return None

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)

    return max(0.0, (datetime.now(UTC) - timestamp.astimezone(UTC)).total_seconds())


def get_last_contact_age_seconds(lifecycle: ConnectionLifecycle) -> float | None:
    if lifecycle.last_success_timestamp is None:
        return None
    return _entry_age_seconds(lifecycle.last_success_timestamp)


def get_last_full_data_age_seconds(lifecycle: ConnectionLifecycle) -> float | None:
    if lifecycle.last_full_success_timestamp is None:
        return None
    return _entry_age_seconds(lifecycle.last_full_success_timestamp)


def resolve_communication_state(
    device: DeviceResponse,
    lifecycle: ConnectionLifecycle,
    *,
    endpoint_device_count: int = 1,
) -> str:
    if lifecycle.has_seen_success and is_recent_last_success(
        device,
        lifecycle,
        endpoint_device_count=endpoint_device_count,
    ):
        return "online"
    if lifecycle.has_seen_success:
        return "offline"
    return "pending"


def resolve_data_freshness(
    device: DeviceResponse,
    lifecycle: ConnectionLifecycle,
    *,
    endpoint_device_count: int = 1,
) -> str:
    if not lifecycle.has_seen_full_success:
        return "missing"
    if is_recent_full_data(
        device,
        lifecycle,
        endpoint_device_count=endpoint_device_count,
    ):
        return "fresh"
    return "stale"


def resolve_runtime_status(
    device: DeviceResponse,
    cache_entry: LiveCacheEntry | None,
    lifecycle: ConnectionLifecycle,
    *,
    endpoint_device_count: int = 1,
) -> str:
    if device.protocol not in RUNTIME_POLL_PROTOCOLS:
        return device.status

    communication_state = resolve_communication_state(
        device,
        lifecycle,
        endpoint_device_count=endpoint_device_count,
    )
    data_freshness = resolve_data_freshness(
        device,
        lifecycle,
        endpoint_device_count=endpoint_device_count,
    )

    if communication_state != "online":
        return communication_state

    if cache_entry is not None and is_successful_full_poll(cache_entry) and is_recent_full_data(
        device,
        lifecycle,
        endpoint_device_count=endpoint_device_count,
    ):
        return "online"

    if uses_serial_like_polling(device):
        return "online"
    if data_freshness == "fresh":
        return "online"
    if is_within_partial_grace(
        device,
        lifecycle,
        endpoint_device_count=endpoint_device_count,
    ):
        return "degraded"
    return "online"


def build_poll_endpoint_key(device: DeviceResponse) -> tuple[str, str] | None:
    settings = device.connection_settings
    if device.transport == "tcp":
        host = str(settings.get("host", "")).strip()
        port = settings.get("port")
        if not host or port in {None, ""}:
            return None
        return "tcp", f"{host}:{port}"

    if device.transport == "serial":
        port_name = str(settings.get("port", "")).strip()
        if not port_name:
            return None
        return "serial", port_name

    return None
