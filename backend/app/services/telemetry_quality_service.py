from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from app.models.inverter_model import InverterPoint
from app.services.power_value_sanitizer import sanitize_device_power_kw


TelemetryQualityState = Literal["valid", "warning", "invalid", "unavailable"]


@dataclass(slots=True, frozen=True)
class TelemetryQualityEvaluation:
    state: TelemetryQualityState
    reason: str | None = None


class TelemetryQualityService:
    def evaluate(
        self,
        point: InverterPoint,
        value: object,
        *,
        device: object | None = None,
        values: dict[str, object] | None = None,
        telemetry_points: list[InverterPoint] | None = None,
    ) -> TelemetryQualityEvaluation:
        if value is None or (isinstance(value, str) and not value.strip()):
            return TelemetryQualityEvaluation("unavailable", "Valore non disponibile")

        if self._matches_invalid_sentinel(point, value):
            return TelemetryQualityEvaluation("invalid", "Valore sentinella dichiarato dal protocollo")

        numeric_value = self._coerce_float(value)
        if numeric_value is None:
            if self._expects_numeric(point):
                return TelemetryQualityEvaluation("invalid", "Valore numerico non interpretabile")
            return TelemetryQualityEvaluation("valid")
        if not math.isfinite(numeric_value):
            return TelemetryQualityEvaluation("invalid", "Valore non finito")

        explicit_evaluation = self._evaluate_explicit_limits(point, numeric_value)
        if explicit_evaluation is not None:
            return explicit_evaluation

        normalized_unit = point.unit.strip().lower()
        normalized_key = point.key.strip().lower()
        summary_metric = str(point.protocol_meta.get("summary_metric", "")).strip().lower()

        if summary_metric == "power_kw" or self._looks_like_power(normalized_key, normalized_unit):
            value_kw = self._to_kw(numeric_value, normalized_unit)
            if value_kw is not None and sanitize_device_power_kw(
                value_kw,
                device=device,
                values=values,
                telemetry_points=telemetry_points,
            ) is None:
                return TelemetryQualityEvaluation(
                    "invalid",
                    "Potenza oltre il limite plausibile per il dispositivo",
                )

        if normalized_unit in {"%", "percent", "pct"}:
            if numeric_value < -110 or numeric_value > 110:
                return TelemetryQualityEvaluation("invalid", "Percentuale fuori intervallo plausibile")

        if normalized_unit == "hz" or "frequency" in normalized_key or "frequenza" in normalized_key:
            if numeric_value < 0 or numeric_value > 70:
                return TelemetryQualityEvaluation("invalid", "Frequenza fuori intervallo plausibile")
            if numeric_value == 0 or numeric_value < 45 or numeric_value > 65:
                return TelemetryQualityEvaluation("warning", "Frequenza assente o fuori intervallo nominale")

        if normalized_unit in {"v", "volt"}:
            if numeric_value < 0 or numeric_value > 2500:
                return TelemetryQualityEvaluation("invalid", "Tensione fuori intervallo plausibile")
        elif normalized_unit == "kv":
            if numeric_value < 0 or numeric_value > 100:
                return TelemetryQualityEvaluation("invalid", "Tensione fuori intervallo plausibile")

        if normalized_unit in {"a", "ampere"} and abs(numeric_value) > 10_000:
            return TelemetryQualityEvaluation("invalid", "Corrente fuori intervallo plausibile")

        if normalized_unit in {"c", "degc"} or "temperature" in normalized_key:
            if numeric_value < -60 or numeric_value > 180:
                return TelemetryQualityEvaluation("invalid", "Temperatura fuori intervallo plausibile")

        if self._looks_like_power_factor(normalized_key, point.label):
            if numeric_value < -1.05 or numeric_value > 1.05:
                return TelemetryQualityEvaluation("invalid", "Fattore di potenza fuori intervallo plausibile")

        if self._looks_like_energy(normalized_key, normalized_unit):
            if numeric_value < 0:
                return TelemetryQualityEvaluation("invalid", "Energia negativa non plausibile")
            limit = 1_000_000.0 if "daily" in normalized_key or "giornal" in point.label.lower() else 100_000_000.0
            if numeric_value > limit:
                return TelemetryQualityEvaluation("invalid", "Energia oltre il limite plausibile")

        return TelemetryQualityEvaluation("valid")

    def is_usable_metric(
        self,
        point: InverterPoint,
        value: object,
        *,
        device: object | None = None,
        values: dict[str, object] | None = None,
        telemetry_points: list[InverterPoint] | None = None,
    ) -> bool:
        return self.evaluate(
            point,
            value,
            device=device,
            values=values,
            telemetry_points=telemetry_points,
        ).state in {"valid", "warning"}

    def _evaluate_explicit_limits(
        self,
        point: InverterPoint,
        numeric_value: float,
    ) -> TelemetryQualityEvaluation | None:
        valid_min = self._coerce_float(point.protocol_meta.get("valid_min"))
        valid_max = self._coerce_float(point.protocol_meta.get("valid_max"))
        warning_min = self._coerce_float(point.protocol_meta.get("warning_min"))
        warning_max = self._coerce_float(point.protocol_meta.get("warning_max"))

        if valid_min is not None and numeric_value < valid_min:
            return TelemetryQualityEvaluation("invalid", f"Valore inferiore al minimo valido ({valid_min:g})")
        if valid_max is not None and numeric_value > valid_max:
            return TelemetryQualityEvaluation("invalid", f"Valore superiore al massimo valido ({valid_max:g})")
        if warning_min is not None and numeric_value < warning_min:
            return TelemetryQualityEvaluation("warning", f"Valore inferiore alla soglia nominale ({warning_min:g})")
        if warning_max is not None and numeric_value > warning_max:
            return TelemetryQualityEvaluation("warning", f"Valore superiore alla soglia nominale ({warning_max:g})")
        return None

    def _matches_invalid_sentinel(self, point: InverterPoint, value: object) -> bool:
        invalid_values = point.protocol_meta.get("invalid_values")
        if not isinstance(invalid_values, (list, tuple, set)):
            return False
        return value in invalid_values

    def _expects_numeric(self, point: InverterPoint) -> bool:
        datatype = point.datatype.strip().lower()
        return not any(token in datatype for token in ("ascii", "string", "char", "bytes"))

    def _looks_like_power(self, key: str, unit: str) -> bool:
        return "power" in key and unit in {"w", "kw", "mw"}

    def _looks_like_energy(self, key: str, unit: str) -> bool:
        return "energy" in key or unit in {"wh", "kwh", "mwh"}

    def _looks_like_power_factor(self, key: str, label: str) -> bool:
        normalized_label = label.strip().lower()
        return "power_factor" in key or "cosphi" in key or "fattore di potenza" in normalized_label

    def _to_kw(self, value: float, unit: str) -> float | None:
        if unit == "w":
            return value / 1000.0
        if unit == "kw":
            return value
        if unit == "mw":
            return value * 1000.0
        return None

    def _coerce_float(self, value: object) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            normalized = value.strip().replace(",", ".")
            if not normalized:
                return None
            try:
                return float(normalized)
            except ValueError:
                return None
        return None


telemetry_quality_service = TelemetryQualityService()
