from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

ConnectionPrimitive = str | int | float | bool
ProtocolKey = Literal["modbus_rtu", "modbus_tcp", "sunspec", "aurora", "delta_rs485"]
TransportKey = Literal["serial", "tcp"]

DEFAULT_TIMEOUT_SECONDS = 3.0
DEFAULT_RETRIES = 0
DEFAULT_SERIAL_POLL_TIMEOUT_CAP_SECONDS = 1.0
DEFAULT_SERIAL_POLL_RETRY_CAP = 0
DEFAULT_SERIAL_GATEWAY_POLL_TIMEOUT_CAP_SECONDS = 2.0
DEFAULT_SERIAL_GATEWAY_POLL_RETRY_CAP = 0

PROTOCOL_TRANSPORTS: dict[ProtocolKey, TransportKey] = {
    "modbus_tcp": "tcp",
    "modbus_rtu": "serial",
    "aurora": "serial",
    "delta_rs485": "serial",
    "sunspec": "tcp",
}

PROTOCOL_ALLOWED_TRANSPORTS: dict[ProtocolKey, tuple[TransportKey, ...]] = {
    "modbus_tcp": ("tcp",),
    "modbus_rtu": ("serial", "tcp"),
    "aurora": ("serial",),
    "delta_rs485": ("serial",),
    "sunspec": ("tcp",),
}

PROTOCOL_REQUIRED_CONNECTION_SETTINGS: dict[ProtocolKey, tuple[str, ...]] = {
    "modbus_rtu": (
        "port",
        "slave_id",
        "baud_rate",
        "parity",
        "stop_bits",
        "byte_size",
        "timeout_seconds",
        "retries",
    ),
    "modbus_tcp": ("host", "port", "unit_id", "timeout_seconds", "retries"),
    "sunspec": ("host", "port", "unit_id", "timeout_seconds", "retries"),
    "aurora": (
        "port",
        "address",
        "baud_rate",
        "parity",
        "stop_bits",
        "byte_size",
        "timeout_seconds",
        "retries",
    ),
    "delta_rs485": (
        "port",
        "address",
        "baud_rate",
        "parity",
        "stop_bits",
        "byte_size",
        "timeout_seconds",
        "retries",
    ),
}

PROTOCOL_REQUIRED_CONNECTION_SETTINGS_BY_TRANSPORT: dict[
    tuple[ProtocolKey, TransportKey],
    tuple[str, ...],
] = {
    ("modbus_rtu", "tcp"): ("host", "port", "unit_id", "timeout_seconds", "retries"),
}

PROTOCOL_DEFAULT_CONNECTION_SETTINGS: dict[ProtocolKey, dict[str, ConnectionPrimitive]] = {
    "modbus_tcp": {
        "port": 502,
        "unit_id": 1,
        "timeout_seconds": 5.0,
        "retries": 3,
        "poll_interval_seconds": 15.0,
    },
    "modbus_rtu": {
        "baud_rate": 9600,
        "parity": "N",
        "stop_bits": 1,
        "byte_size": 8,
        "timeout_seconds": 5.0,
        "retries": 3,
        "poll_interval_seconds": 15.0,
    },
    "aurora": {
        "baud_rate": 19200,
        "parity": "N",
        "stop_bits": 1,
        "byte_size": 8,
        "timeout_seconds": 0.5,
        "retries": 1,
        "poll_interval_seconds": 15.0,
        "inter_request_delay_ms": 20,
        "retry_delay_ms": 40,
        "float_endian": ">",
    },
    "delta_rs485": {
        "baud_rate": 19200,
        "parity": "N",
        "stop_bits": 1,
        "byte_size": 8,
        "timeout_seconds": 1.0,
        "retries": 1,
        "poll_interval_seconds": 15.0,
        "inter_request_delay_ms": 10,
        "retry_delay_ms": 50,
        "delta_variant": 1,
    },
    "sunspec": {
        "port": 502,
        "unit_id": 126,
        "timeout_seconds": 5.0,
        "retries": 3,
        "poll_interval_seconds": 15.0,
    },
}

PROTOCOL_DEFAULT_CONNECTION_SETTINGS_BY_TRANSPORT: dict[
    tuple[ProtocolKey, TransportKey],
    dict[str, ConnectionPrimitive],
] = {
    (
        "modbus_rtu",
        "tcp",
    ): {
        "port": 502,
        "unit_id": 1,
        "timeout_seconds": 5.0,
        "retries": 3,
        "poll_interval_seconds": 15.0,
    },
}

MODEL_DEFAULT_CONNECTION_SETTINGS: dict[
    tuple[str, str, ProtocolKey, TransportKey], dict[str, ConnectionPrimitive]
] = {
    (
        "bonfiglioli",
        "",
        "modbus_rtu",
        "serial",
    ): {
        "baud_rate": 19200,
        "parity": "E",
        "stop_bits": 2,
    },
}

_BOOLEAN_KEYS = {
    "handle_local_echo",
    "use_rs485_mode",
    "rs485_rts_level_for_tx",
    "rs485_rts_level_for_rx",
    "rs485_loopback",
    "retry_on_device_busy",
}

_INT_RANGES: dict[str, tuple[int, int | None]] = {
    "port": (1, 65535),
    "unit_id": (0, 247),
    "slave_id": (0, 247),
    "address": (0, 247),
    "baud_rate": (1, None),
    "stop_bits": (1, 2),
    "byte_size": (5, 8),
    "retries": (0, 10),
    "poll_retries": (0, 10),
    "write_retries": (0, 10),
    "device_busy_retry_count": (0, 10),
    "max_registers_per_request": (1, 125),
}

_FLOAT_RANGES: dict[str, tuple[float, float | None]] = {
    "timeout_seconds": (0.05, 60.0),
    "poll_timeout_seconds": (0.05, 60.0),
    "write_timeout_seconds": (0.05, 60.0),
    "poll_interval_seconds": (1.0, 300.0),
    "inter_request_delay_ms": (0.0, 60000.0),
    "inter_request_delay_seconds": (0.0, 60.0),
    "retry_delay_ms": (0.0, 60000.0),
    "device_busy_retry_delay_ms": (0.0, 60000.0),
    "rs485_delay_before_tx_ms": (0.0, 60000.0),
    "rs485_delay_before_rx_ms": (0.0, 60000.0),
}

_PROTOCOL_ALIASES: dict[ProtocolKey, dict[str, str]] = {
    "modbus_tcp": {"slave_id": "unit_id"},
    "sunspec": {"slave_id": "unit_id"},
    "modbus_rtu": {"unit_id": "slave_id", "address": "slave_id"},
    "aurora": {"unit_id": "address", "slave_id": "address"},
    "delta_rs485": {"unit_id": "address", "slave_id": "address"},
}

_TRANSPORT_PROTOCOL_ALIASES: dict[tuple[ProtocolKey, TransportKey], dict[str, str]] = {
    ("modbus_rtu", "tcp"): {"slave_id": "unit_id", "address": "unit_id"},
}


def normalize_connection_settings(
    *,
    protocol: str,
    transport: str,
    settings: Mapping[str, object],
    require_required_settings: bool,
    enforce_transport_match: bool = True,
) -> dict[str, ConnectionPrimitive]:
    protocol_key = _require_protocol_key(protocol)
    allowed_transports = PROTOCOL_ALLOWED_TRANSPORTS[protocol_key]
    if enforce_transport_match and transport not in allowed_transports:
        raise ValueError("Il trasporto selezionato non corrisponde al protocollo scelto.")

    normalized_input = _normalize_raw_settings(settings)
    canonical_settings = _apply_protocol_aliases(protocol_key, transport, normalized_input)
    normalized: dict[str, ConnectionPrimitive] = {
        **_default_connection_settings_for_transport(protocol_key, transport),
        **canonical_settings,
    }

    _validate_transport_specific_settings(transport=transport, settings=normalized)
    _validate_common_settings(protocol=protocol_key, transport=transport, settings=normalized)

    if require_required_settings:
        missing = [
            key
            for key in _required_connection_settings_for_transport(protocol_key, transport)
            if _is_missing_value(normalized.get(key))
        ]
        if missing:
            translated = ", ".join(_translate_setting_key(key) for key in missing)
            raise ValueError(f"Parametri di connessione mancanti: {translated}.")

    return normalized


def merge_model_connection_defaults(
    *,
    brand: str,
    model: str,
    protocol: str,
    transport: str,
    settings: Mapping[str, object],
) -> dict[str, ConnectionPrimitive]:
    protocol_key = _require_protocol_key(protocol)
    if transport not in {"serial", "tcp"}:
        return _normalize_raw_settings(settings)
    transport_key: TransportKey = transport
    normalized_brand = brand.strip().lower()
    normalized_model = model.strip().lower()
    defaults = MODEL_DEFAULT_CONNECTION_SETTINGS.get(
        (normalized_brand, normalized_model, protocol_key, transport_key),
    ) or MODEL_DEFAULT_CONNECTION_SETTINGS.get(
        (normalized_brand, "", protocol_key, transport_key),
    )
    normalized_input = _normalize_raw_settings(settings)
    if not defaults:
        return normalized_input
    return {
        **defaults,
        **normalized_input,
    }


def normalize_persisted_connection_settings(
    *,
    protocol: str,
    transport: str,
    settings: Mapping[str, object],
) -> dict[str, ConnectionPrimitive]:
    return normalize_connection_settings(
        protocol=protocol,
        transport=transport,
        settings=settings,
        require_required_settings=False,
        enforce_transport_match=True,
    )


def _require_protocol_key(protocol: str) -> ProtocolKey:
    if protocol not in PROTOCOL_TRANSPORTS:
        raise ValueError(f"Protocollo non supportato per la validazione: {protocol}.")
    return protocol  # type: ignore[return-value]


def _normalize_raw_settings(settings: Mapping[str, object]) -> dict[str, ConnectionPrimitive]:
    normalized: dict[str, ConnectionPrimitive] = {}
    for raw_key, raw_value in settings.items():
        key = str(raw_key).strip()
        if not key:
            raise ValueError("Le impostazioni di connessione contengono una chiave vuota.")
        normalized[key] = _normalize_primitive_value(key=key, value=raw_value)
    return normalized


def _normalize_primitive_value(*, key: str, value: object) -> ConnectionPrimitive:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        trimmed_value = value.strip()
        if key in _BOOLEAN_KEYS:
            return _parse_bool(key, trimmed_value)
        return trimmed_value
    raise ValueError(
        f"Il parametro di connessione '{_translate_setting_key(key)}' deve essere una stringa, un numero o un booleano."
    )


def _apply_protocol_aliases(
    protocol: ProtocolKey,
    transport: str,
    settings: dict[str, ConnectionPrimitive],
) -> dict[str, ConnectionPrimitive]:
    aliases = {
        **_PROTOCOL_ALIASES.get(protocol, {}),
        **_TRANSPORT_PROTOCOL_ALIASES.get((protocol, transport), {}),
    }
    normalized = dict(settings)
    for alias, canonical in aliases.items():
        if canonical in normalized:
            continue
        if alias not in normalized:
            continue
        normalized[canonical] = normalized.pop(alias)
    return normalized


def _required_connection_settings_for_transport(
    protocol: ProtocolKey,
    transport: str,
) -> tuple[str, ...]:
    if transport in {"serial", "tcp"}:
        typed_transport: TransportKey = transport
        return PROTOCOL_REQUIRED_CONNECTION_SETTINGS_BY_TRANSPORT.get(
            (protocol, typed_transport),
            PROTOCOL_REQUIRED_CONNECTION_SETTINGS[protocol],
        )
    return PROTOCOL_REQUIRED_CONNECTION_SETTINGS[protocol]


def _default_connection_settings_for_transport(
    protocol: ProtocolKey,
    transport: str,
) -> dict[str, ConnectionPrimitive]:
    if transport in {"serial", "tcp"}:
        typed_transport: TransportKey = transport
        defaults = PROTOCOL_DEFAULT_CONNECTION_SETTINGS_BY_TRANSPORT.get((protocol, typed_transport))
        if defaults is not None:
            return dict(defaults)
    return dict(PROTOCOL_DEFAULT_CONNECTION_SETTINGS.get(protocol, {}))


def _validate_transport_specific_settings(
    *,
    transport: str,
    settings: dict[str, ConnectionPrimitive],
) -> None:
    if transport == "tcp":
        host = settings.get("host")
        if _is_missing_value(host):
            return
        if not isinstance(host, str) or host.strip() == "":
            raise ValueError("Il parametro di connessione 'host' deve contenere un indirizzo valido.")
        settings["host"] = host.strip()
        _validate_int_setting(settings, "port")
        return

    port_name = settings.get("port")
    if _is_missing_value(port_name):
        return
    if not isinstance(port_name, str) or port_name.strip() == "":
        raise ValueError("Il parametro di connessione 'porta seriale' deve contenere un valore valido.")
    settings["port"] = port_name.strip()


def _validate_common_settings(
    *,
    protocol: ProtocolKey,
    transport: str,
    settings: dict[str, ConnectionPrimitive],
) -> None:
    if protocol in {"modbus_tcp", "sunspec"}:
        _validate_int_setting(settings, "unit_id")
    elif protocol == "modbus_rtu":
        if transport == "tcp":
            _validate_int_setting(settings, "unit_id")
        else:
            _validate_int_setting(settings, "slave_id")
    else:
        _validate_int_setting(settings, "address")

    if protocol in {"aurora", "delta_rs485"} or (protocol == "modbus_rtu" and transport == "serial"):
        _validate_int_setting(settings, "baud_rate")
        _validate_parity_setting(settings)
        _validate_int_setting(settings, "stop_bits")
        _validate_int_setting(settings, "byte_size")

    _validate_float_setting(settings, "timeout_seconds")
    _validate_int_setting(settings, "retries")
    _validate_float_setting(settings, "poll_timeout_seconds", optional=True)
    _validate_int_setting(settings, "poll_retries", optional=True)
    _validate_float_setting(settings, "write_timeout_seconds", optional=True)
    _validate_int_setting(settings, "write_retries", optional=True)
    _validate_float_setting(settings, "poll_interval_seconds")

    for key in (
        "inter_request_delay_ms",
        "inter_request_delay_seconds",
        "retry_delay_ms",
        "device_busy_retry_delay_ms",
        "rs485_delay_before_tx_ms",
        "rs485_delay_before_rx_ms",
    ):
        _validate_float_setting(settings, key, optional=True)

    _validate_int_setting(settings, "device_busy_retry_count", optional=True)
    _validate_int_setting(settings, "max_registers_per_request", optional=True)
    _validate_delta_variant(settings, protocol=protocol)


def _validate_int_setting(
    settings: dict[str, ConnectionPrimitive],
    key: str,
    *,
    optional: bool = False,
) -> None:
    raw_value = settings.get(key)
    if _is_missing_value(raw_value):
        if optional:
            settings.pop(key, None)
            return
        return
    value = _parse_int(key, raw_value)
    minimum, maximum = _INT_RANGES[key]
    if value < minimum or (maximum is not None and value > maximum):
        upper_bound = f" e {maximum}" if maximum is not None else ""
        raise ValueError(
            f"Il parametro di connessione '{_translate_setting_key(key)}' deve restare tra {minimum}{upper_bound}."
        )
    settings[key] = value


def _validate_float_setting(
    settings: dict[str, ConnectionPrimitive],
    key: str,
    *,
    optional: bool = False,
) -> None:
    raw_value = settings.get(key)
    if _is_missing_value(raw_value):
        if optional:
            settings.pop(key, None)
            return
        return
    value = _parse_float(key, raw_value)
    minimum, maximum = _FLOAT_RANGES[key]
    if value < minimum or (maximum is not None and value > maximum):
        if maximum is None:
            raise ValueError(
                f"Il parametro di connessione '{_translate_setting_key(key)}' deve essere almeno {minimum}."
            )
        raise ValueError(
            f"Il parametro di connessione '{_translate_setting_key(key)}' deve restare tra {minimum} e {maximum}."
        )
    settings[key] = int(value) if value.is_integer() else value


def _validate_parity_setting(settings: dict[str, ConnectionPrimitive]) -> None:
    raw_value = settings.get("parity")
    if _is_missing_value(raw_value):
        return
    if not isinstance(raw_value, str):
        raise ValueError("Il parametro di connessione 'parita' deve essere una stringa.")
    parity = raw_value.strip().upper()
    if parity not in {"N", "E", "O", "M", "S"}:
        raise ValueError("Il parametro di connessione 'parita' deve essere uno tra N, E, O, M, S.")
    settings["parity"] = parity


def _validate_delta_variant(
    settings: dict[str, ConnectionPrimitive],
    *,
    protocol: ProtocolKey,
) -> None:
    raw_value = settings.get("delta_variant")
    if _is_missing_value(raw_value):
        settings.pop("delta_variant", None)
        return
    if protocol != "delta_rs485":
        settings.pop("delta_variant", None)
        return
    variant = _parse_int("delta_variant", raw_value)
    if variant not in {1, 3, 4}:
        raise ValueError("Il parametro di connessione 'variante Delta' deve essere 1, 3 o 4.")
    settings["delta_variant"] = variant


def _parse_int(key: str, raw_value: ConnectionPrimitive) -> int:
    if isinstance(raw_value, bool):
        raise ValueError(
            f"Il parametro di connessione '{_translate_setting_key(key)}' deve essere numerico."
        )
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, float):
        if not raw_value.is_integer():
            raise ValueError(
                f"Il parametro di connessione '{_translate_setting_key(key)}' deve essere un intero."
            )
        return int(raw_value)
    if isinstance(raw_value, str):
        if raw_value == "":
            raise ValueError(
                f"Il parametro di connessione '{_translate_setting_key(key)}' non puo essere vuoto."
            )
        return int(raw_value)
    raise ValueError(
        f"Il parametro di connessione '{_translate_setting_key(key)}' deve essere numerico."
    )


def _parse_float(key: str, raw_value: ConnectionPrimitive) -> float:
    if isinstance(raw_value, bool):
        raise ValueError(
            f"Il parametro di connessione '{_translate_setting_key(key)}' deve essere numerico."
        )
    if isinstance(raw_value, (int, float)):
        return float(raw_value)
    if isinstance(raw_value, str):
        if raw_value == "":
            raise ValueError(
                f"Il parametro di connessione '{_translate_setting_key(key)}' non puo essere vuoto."
            )
        return float(raw_value)
    raise ValueError(
        f"Il parametro di connessione '{_translate_setting_key(key)}' deve essere numerico."
    )


def _parse_bool(key: str, raw_value: str) -> bool:
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(
        f"Il parametro di connessione '{_translate_setting_key(key)}' deve essere true o false."
    )


def _is_missing_value(value: ConnectionPrimitive | object | None) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _translate_setting_key(key: str) -> str:
    translations = {
        "host": "host",
        "port": "porta",
        "unit_id": "ID unita",
        "slave_id": "ID slave",
        "address": "indirizzo",
        "baud_rate": "baud rate",
        "parity": "parita",
        "stop_bits": "bit di stop",
        "byte_size": "dimensione byte",
        "timeout_seconds": "timeout",
        "retries": "tentativi",
        "poll_timeout_seconds": "timeout polling",
        "poll_retries": "tentativi polling",
        "write_timeout_seconds": "timeout scrittura",
        "write_retries": "tentativi scrittura",
        "poll_interval_seconds": "intervallo polling",
        "delta_variant": "variante Delta",
        "device_busy_retry_count": "tentativi device busy",
        "device_busy_retry_delay_ms": "attesa device busy",
        "inter_request_delay_ms": "attesa tra richieste",
        "inter_request_delay_seconds": "attesa tra richieste",
        "max_registers_per_request": "registri per richiesta",
        "handle_local_echo": "local echo",
        "use_rs485_mode": "modalita RS485",
        "rs485_rts_level_for_tx": "RTS TX",
        "rs485_rts_level_for_rx": "RTS RX",
        "rs485_loopback": "loopback RS485",
        "rs485_delay_before_tx_ms": "ritardo RS485 TX",
        "rs485_delay_before_rx_ms": "ritardo RS485 RX",
    }
    return translations.get(key, key.replace("_", " "))


def get_connection_timeout_seconds(
    settings: Mapping[str, object],
    *,
    default: float = DEFAULT_TIMEOUT_SECONDS,
) -> float:
    timeout_seconds = _coerce_float_setting(settings.get("timeout_seconds"), default=default)
    return max(0.05, min(timeout_seconds, 60.0))


def get_connection_retry_count(
    settings: Mapping[str, object],
    *,
    default: int = DEFAULT_RETRIES,
) -> int:
    retries = _coerce_int_setting(settings.get("retries"), default=default)
    return max(0, min(retries, 10))


def get_poll_timeout_seconds(
    settings: Mapping[str, object],
    *,
    transport: str,
    default: float = DEFAULT_TIMEOUT_SECONDS,
    serial_gateway: bool = False,
) -> float:
    explicit_timeout = settings.get("poll_timeout_seconds")
    if not _is_missing_value(explicit_timeout):
        timeout_seconds = _coerce_float_setting(explicit_timeout, default=default)
        return max(0.05, min(timeout_seconds, 60.0))

    timeout_seconds = get_connection_timeout_seconds(settings, default=default)
    if transport == "serial":
        return min(timeout_seconds, DEFAULT_SERIAL_POLL_TIMEOUT_CAP_SECONDS)
    if serial_gateway:
        return min(timeout_seconds, DEFAULT_SERIAL_GATEWAY_POLL_TIMEOUT_CAP_SECONDS)
    return timeout_seconds


def get_poll_retry_count(
    settings: Mapping[str, object],
    *,
    transport: str,
    default: int = DEFAULT_RETRIES,
    serial_gateway: bool = False,
) -> int:
    explicit_retries = settings.get("poll_retries")
    if not _is_missing_value(explicit_retries):
        retries = _coerce_int_setting(explicit_retries, default=default)
        return max(0, min(retries, 10))

    retries = get_connection_retry_count(settings, default=default)
    if transport == "serial":
        return min(retries, DEFAULT_SERIAL_POLL_RETRY_CAP)
    if serial_gateway:
        return min(retries, DEFAULT_SERIAL_GATEWAY_POLL_RETRY_CAP)
    return retries


def get_write_timeout_seconds(
    settings: Mapping[str, object],
    *,
    default: float = DEFAULT_TIMEOUT_SECONDS,
) -> float:
    explicit_timeout = settings.get("write_timeout_seconds")
    if not _is_missing_value(explicit_timeout):
        timeout_seconds = _coerce_float_setting(explicit_timeout, default=default)
        return max(0.05, min(timeout_seconds, 60.0))

    return get_connection_timeout_seconds(settings, default=default)


def get_write_retry_count(
    settings: Mapping[str, object],
    *,
    default: int = DEFAULT_RETRIES,
) -> int:
    explicit_retries = settings.get("write_retries")
    if not _is_missing_value(explicit_retries):
        retries = _coerce_int_setting(explicit_retries, default=default)
        return max(0, min(retries, 10))

    return get_connection_retry_count(settings, default=default)


def _coerce_float_setting(raw_value: object, *, default: float) -> float:
    if _is_missing_value(raw_value):
        return float(default)
    if isinstance(raw_value, bool):
        return float(default)
    if isinstance(raw_value, (int, float)):
        return float(raw_value)
    if isinstance(raw_value, str):
        try:
            return float(raw_value)
        except ValueError:
            return float(default)
    return float(default)


def _coerce_int_setting(raw_value: object, *, default: int) -> int:
    if _is_missing_value(raw_value):
        return int(default)
    if isinstance(raw_value, bool):
        return int(default)
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, float):
        return int(raw_value)
    if isinstance(raw_value, str):
        try:
            return int(raw_value)
        except ValueError:
            return int(default)
    return int(default)
