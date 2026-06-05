from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.schemas.device_overview_schemas import DeviceTelemetryPoint


MAX_DEVICE_POWER_KW_WITHOUT_NOMINAL = 10_000.0
MAX_TRUSTED_NOMINAL_POWER_KW = 20_000.0
MIN_REASONABLE_POWER_LIMIT_KW = 50.0
NOMINAL_POWER_LIMIT_MULTIPLIER = 1.5
NOMINAL_POWER_LIMIT_MARGIN_KW = 50.0

_NOMINAL_POWER_KEY_PRIORITY = (
    "rated_active_power_kw",
    "rated_power_kw",
    "power_rating_kw",
    "rated_power_unity_pf_kw",
    "inverter_max_power_kw",
    "inverter_max_power_w",
    "max_active_power_kw",
)
_NOMINAL_POWER_HINTS = (
    "potenza nominale",
    "rated power",
    "power rating",
    "potenza attiva nominale",
    "nominal power",
    "max active power",
)
_NOMINAL_POWER_EXCLUDES = (
    "charge",
    "discharge",
    "battery",
    "apparent",
    "reactive",
    "corrente",
    "current",
    "tensione",
    "voltage",
    "sf",
)
_MODEL_POWER_PATTERNS = (
    re.compile(r"\bRPS\s+(\d{2,5})(?:\b|\s|-)", re.IGNORECASE),
    re.compile(r"\bIngecon\s+SUN\s*(\d{2,5})(?:\s*HE|\s*TL|\b)", re.IGNORECASE),
    re.compile(r"\bSUN\s*(\d{2,5})\s*HE\b", re.IGNORECASE),
    re.compile(r"\bSUN2000[-\s]?(\d{1,4}(?:[.,]\d+)?)KTL\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,5}(?:[.,]\d+)?)\s*kW\b", re.IGNORECASE),
)


def sanitize_device_power_kw(
    value: object,
    *,
    device: object | None = None,
    telemetry: Sequence[DeviceTelemetryPoint] | None = None,
    values: Mapping[str, object] | None = None,
    telemetry_points: Sequence[object] | None = None,
    nominal_power_kw: float | None = None,
) -> float | None:
    numeric_value = _coerce_float(value)
    if numeric_value is None or not math.isfinite(numeric_value):
        return None

    effective_nominal_power_kw = _trusted_nominal_power_kw(
        nominal_power_kw
        or resolve_nominal_power_kw(
            device=device,
            telemetry=telemetry,
            values=values,
            telemetry_points=telemetry_points,
        )
    )
    limit_kw = _power_limit_kw(effective_nominal_power_kw)
    if abs(numeric_value) > limit_kw:
        return None
    return numeric_value


def sanitize_produced_power_kw(
    value: object,
    *,
    device: object | None = None,
    telemetry: Sequence[DeviceTelemetryPoint] | None = None,
    values: Mapping[str, object] | None = None,
    telemetry_points: Sequence[object] | None = None,
    nominal_power_kw: float | None = None,
    default: float = 0.0,
) -> float:
    sanitized_value = sanitize_device_power_kw(
        value,
        device=device,
        telemetry=telemetry,
        values=values,
        telemetry_points=telemetry_points,
        nominal_power_kw=nominal_power_kw,
    )
    if sanitized_value is None:
        return default
    return max(0.0, sanitized_value)


def resolve_nominal_power_kw(
    *,
    device: object | None = None,
    telemetry: Sequence[DeviceTelemetryPoint] | None = None,
    values: Mapping[str, object] | None = None,
    telemetry_points: Sequence[object] | None = None,
) -> float | None:
    for candidate in (
        _extract_nominal_power_kw_from_telemetry(telemetry or ()),
        _extract_nominal_power_kw_from_values(values or {}, telemetry_points or ()),
        _infer_nominal_power_kw_from_device(device),
    ):
        trusted_candidate = _trusted_nominal_power_kw(candidate)
        if trusted_candidate is not None:
            return trusted_candidate
    return None


def _extract_nominal_power_kw_from_telemetry(
    telemetry: Sequence[DeviceTelemetryPoint],
) -> float | None:
    for key in _NOMINAL_POWER_KEY_PRIORITY:
        point = next((item for item in telemetry if item.key == key), None)
        if point is None:
            continue
        value_kw = _point_to_kw(
            key=point.key,
            unit=point.unit,
            value=point.value,
            raw_value=point.raw_value,
        )
        if value_kw is not None and value_kw > 0:
            return value_kw

    for point in telemetry:
        fingerprint = f"{point.key} {point.label} {point.section}".lower()
        if not any(hint in fingerprint for hint in _NOMINAL_POWER_HINTS):
            continue
        if any(excluded in fingerprint for excluded in _NOMINAL_POWER_EXCLUDES):
            continue
        value_kw = _point_to_kw(
            key=point.key,
            unit=point.unit,
            value=point.value,
            raw_value=point.raw_value,
        )
        if value_kw is not None and value_kw > 0:
            return value_kw
    return None


def _extract_nominal_power_kw_from_values(
    values: Mapping[str, object],
    telemetry_points: Sequence[object],
) -> float | None:
    for key in _NOMINAL_POWER_KEY_PRIORITY:
        raw_value = values.get(key)
        if raw_value is None:
            continue
        point = next(
            (candidate for candidate in telemetry_points if getattr(candidate, "key", None) == key),
            None,
        )
        value_kw = _point_to_kw(
            key=key,
            unit=str(getattr(point, "unit", "")) if point is not None else "kW",
            value=raw_value,
        )
        if value_kw is not None and value_kw > 0:
            return value_kw

    for point in telemetry_points:
        key = str(getattr(point, "key", ""))
        if key not in values:
            continue
        section = _protocol_meta_section(point)
        fingerprint = f"{key} {getattr(point, 'label', '')} {section}".lower()
        if not any(hint in fingerprint for hint in _NOMINAL_POWER_HINTS):
            continue
        if any(excluded in fingerprint for excluded in _NOMINAL_POWER_EXCLUDES):
            continue
        value_kw = _point_to_kw(
            key=key,
            unit=str(getattr(point, "unit", "")),
            value=values.get(key),
        )
        if value_kw is not None and value_kw > 0:
            return value_kw
    return None


def _infer_nominal_power_kw_from_device(device: object | None) -> float | None:
    if device is None:
        return None

    text = " ".join(
        str(getattr(device, field_name, "") or "")
        for field_name in ("brand", "model", "name")
    )
    for pattern in _MODEL_POWER_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        numeric_value = _coerce_float(match.group(1))
        if numeric_value is not None and numeric_value > 0:
            return numeric_value
    return None


def _power_limit_kw(nominal_power_kw: float | None) -> float:
    if nominal_power_kw is None:
        return MAX_DEVICE_POWER_KW_WITHOUT_NOMINAL
    return max(
        MIN_REASONABLE_POWER_LIMIT_KW,
        nominal_power_kw * NOMINAL_POWER_LIMIT_MULTIPLIER,
        nominal_power_kw + NOMINAL_POWER_LIMIT_MARGIN_KW,
    )


def _trusted_nominal_power_kw(value: object) -> float | None:
    numeric_value = _coerce_float(value)
    if numeric_value is None or numeric_value <= 0 or not math.isfinite(numeric_value):
        return None
    if numeric_value > MAX_TRUSTED_NOMINAL_POWER_KW:
        return None
    return numeric_value


def _point_to_kw(
    *,
    key: str,
    unit: str,
    value: object,
    raw_value: object | None = None,
) -> float | None:
    numeric_value = _coerce_float(value)
    if numeric_value is None:
        numeric_value = _coerce_float(raw_value)
    if numeric_value is None:
        return None

    if key == "inverter_max_power_w":
        return numeric_value / 1000.0

    normalized_unit = unit.strip().lower()
    if normalized_unit == "w":
        return numeric_value / 1000.0
    if normalized_unit in {"kw", ""}:
        return numeric_value
    if normalized_unit == "mw":
        return numeric_value * 1000.0
    return None


def _coerce_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if "," in normalized:
            normalized = normalized.replace(".", "").replace(",", ".")
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def _protocol_meta_section(point: object) -> str:
    protocol_meta = getattr(point, "protocol_meta", None)
    if isinstance(protocol_meta, dict):
        section = protocol_meta.get("section")
        if isinstance(section, str):
            return section
    return ""
