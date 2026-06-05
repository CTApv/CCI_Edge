from dataclasses import dataclass

from app.models.inverter_model import InverterModel, InverterPoint
from app.schemas.device_overview_schemas import DeviceTelemetryPoint

PREFERRED_PERCENT_TELEMETRY_KEYS = (
    "active_power_limit",
    "active_power_limit_pct",
    "active_power_management_percentage",
    "output_power_derating_percent",
    "output_power_derating_percent_set",
    "maximum_feed_grid_power_pct",
    "maximum_feed_in_grid_power_pct",
)

PREFERRED_ABSOLUTE_TELEMETRY_KEYS = (
    "ac_active_power_set_w",
    "output_power_derating_modbus_w",
    "maximum_feed_in_grid_power_w",
    "maximum_feed_grid_power_kw",
)

POWER_UNIT_SCALE = {
    "w": 1.0,
    "kw": 1000.0,
}


@dataclass(slots=True, frozen=True)
class ActivePowerLimitReadbackPoint:
    telemetry_point: InverterPoint


@dataclass(slots=True, frozen=True)
class ActivePowerLimitReadbackEvaluation:
    supported: bool
    telemetry_key: str | None
    telemetry_label: str | None
    observed_percent: float | None
    observed_value: float | None
    observed_unit: str | None
    confirmed: bool


class ActivePowerLimitReadbackResolver:
    def resolve_point(self, inverter_model: InverterModel) -> ActivePowerLimitReadbackPoint | None:
        for key in PREFERRED_PERCENT_TELEMETRY_KEYS:
            point = self._find_by_key(inverter_model.telemetry_points, key)
            if point is not None:
                return ActivePowerLimitReadbackPoint(telemetry_point=point)

        for point in inverter_model.telemetry_points:
            linked_command = point.protocol_meta.get("command")
            if isinstance(linked_command, str) and linked_command == "active_power_limit":
                return ActivePowerLimitReadbackPoint(telemetry_point=point)

        percent_candidates = [
            point
            for point in inverter_model.telemetry_points
            if self._normalize_unit(point.unit) == "%"
            and self._matches_readback_semantics(point)
        ]
        if percent_candidates:
            return ActivePowerLimitReadbackPoint(telemetry_point=percent_candidates[0])

        for key in PREFERRED_ABSOLUTE_TELEMETRY_KEYS:
            point = self._find_by_key(inverter_model.telemetry_points, key)
            if point is not None:
                return ActivePowerLimitReadbackPoint(telemetry_point=point)

        absolute_candidates = [
            point
            for point in inverter_model.telemetry_points
            if self._normalize_unit(point.unit) in {"w", "kw"}
            and self._matches_readback_semantics(point)
        ]
        if absolute_candidates:
            return ActivePowerLimitReadbackPoint(telemetry_point=absolute_candidates[0])

        return None

    def evaluate(
        self,
        *,
        inverter_model: InverterModel,
        telemetry: list[DeviceTelemetryPoint],
        desired_percent: float,
        resolved_value: float | None,
        resolved_unit: str | None,
        resolved_max_value: float | None,
    ) -> ActivePowerLimitReadbackEvaluation:
        resolution = self.resolve_point(inverter_model)
        if resolution is None:
            return ActivePowerLimitReadbackEvaluation(
                supported=False,
                telemetry_key=None,
                telemetry_label=None,
                observed_percent=None,
                observed_value=None,
                observed_unit=None,
                confirmed=False,
            )

        telemetry_by_key = {item.key: item for item in telemetry}
        observed_item = telemetry_by_key.get(resolution.telemetry_point.key)
        if observed_item is None or not isinstance(observed_item.value, (int, float)):
            return ActivePowerLimitReadbackEvaluation(
                supported=True,
                telemetry_key=resolution.telemetry_point.key,
                telemetry_label=resolution.telemetry_point.label,
                observed_percent=None,
                observed_value=None,
                observed_unit=resolution.telemetry_point.unit,
                confirmed=False,
            )

        observed_value = float(observed_item.value)
        observed_unit = observed_item.unit or resolution.telemetry_point.unit
        observed_percent = self._resolve_observed_percent(
            observed_value=observed_value,
            observed_unit=observed_unit,
            desired_percent=desired_percent,
            resolved_value=resolved_value,
            resolved_unit=resolved_unit,
            resolved_max_value=resolved_max_value,
        )
        confirmed = (
            observed_percent is not None
            and abs(observed_percent - desired_percent) <= 1.0
        )
        return ActivePowerLimitReadbackEvaluation(
            supported=True,
            telemetry_key=resolution.telemetry_point.key,
            telemetry_label=resolution.telemetry_point.label,
            observed_percent=observed_percent,
            observed_value=observed_value,
            observed_unit=observed_unit,
            confirmed=confirmed,
        )

    def _resolve_observed_percent(
        self,
        *,
        observed_value: float,
        observed_unit: str,
        desired_percent: float,
        resolved_value: float | None,
        resolved_unit: str | None,
        resolved_max_value: float | None,
    ) -> float | None:
        normalized_observed_unit = self._normalize_unit(observed_unit)
        if normalized_observed_unit == "%":
            return self._clamp_percent(observed_value)

        normalized_resolved_unit = self._normalize_unit(resolved_unit)
        if (
            normalized_observed_unit in POWER_UNIT_SCALE
            and normalized_resolved_unit in POWER_UNIT_SCALE
            and resolved_max_value is not None
            and resolved_max_value > 0
        ):
            observed_in_resolved_unit = self._convert_power_value(
                observed_value,
                from_unit=normalized_observed_unit,
                to_unit=normalized_resolved_unit,
            )
            if observed_in_resolved_unit is not None:
                return self._clamp_percent((observed_in_resolved_unit / resolved_max_value) * 100.0)

        if (
            normalized_observed_unit in POWER_UNIT_SCALE
            and normalized_resolved_unit in POWER_UNIT_SCALE
            and resolved_value is not None
        ):
            observed_in_resolved_unit = self._convert_power_value(
                observed_value,
                from_unit=normalized_observed_unit,
                to_unit=normalized_resolved_unit,
            )
            if observed_in_resolved_unit is not None:
                tolerance = max(0.1, abs(resolved_value) * 0.02)
                if abs(observed_in_resolved_unit - resolved_value) <= tolerance:
                    return self._clamp_percent(desired_percent)
        return None

    def _matches_readback_semantics(self, point: InverterPoint) -> bool:
        section = str(point.protocol_meta.get("section", ""))
        fingerprint = f"{point.key} {point.label} {section}".strip().lower()
        include_terms = (
            "active_power_limit",
            "power limit",
            "limitazione potenza",
            "setpoint potenza",
            "power setpoint",
            "derating",
            "management percentage",
            "gestione potenza",
            "feed in power",
            "remote power limitation",
        )
        exclude_terms = (
            "active_power_kw",
            "active_power_w",
            "active power phase",
            "summary",
            "misura",
            "measure",
            "output power",
            "max active power",
            "potenza massima",
        )
        return any(term in fingerprint for term in include_terms) and not any(
            term in fingerprint for term in exclude_terms
        )

    def _find_by_key(self, points: list[InverterPoint], key: str) -> InverterPoint | None:
        for point in points:
            if point.key == key:
                return point
        return None

    def _normalize_unit(self, unit: str | None) -> str:
        if unit is None:
            return ""
        normalized = str(unit).strip().lower()
        if normalized in {"percent", "%"}:
            return "%"
        return normalized

    def _convert_power_value(self, value: float, *, from_unit: str, to_unit: str) -> float | None:
        if from_unit not in POWER_UNIT_SCALE or to_unit not in POWER_UNIT_SCALE:
            return None
        value_in_watts = value * POWER_UNIT_SCALE[from_unit]
        return value_in_watts / POWER_UNIT_SCALE[to_unit]

    def _clamp_percent(self, value: float) -> float:
        return round(min(max(float(value), 0.0), 100.0), 1)


active_power_limit_readback_resolver = ActivePowerLimitReadbackResolver()
