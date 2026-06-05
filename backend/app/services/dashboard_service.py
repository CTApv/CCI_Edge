import math
from datetime import datetime, timezone

from app.schemas.dashboard_schemas import DashboardActivePowerResponse, DashboardSummaryResponse
from app.schemas.device_overview_schemas import DeviceTelemetryPoint
from app.schemas.power_history_schemas import (
    DevicePowerHistoryResponse,
    FleetPowerHistoryResponse,
    PowerHistorySeries,
)
from app.services.device_service import device_service
from app.services.live_cache import PowerSample, live_cache
from app.services.power_value_sanitizer import (
    MAX_DEVICE_POWER_KW_WITHOUT_NOMINAL,
    MIN_REASONABLE_POWER_LIMIT_KW,
    NOMINAL_POWER_LIMIT_MARGIN_KW,
    NOMINAL_POWER_LIMIT_MULTIPLIER,
    resolve_nominal_power_kw,
    sanitize_device_power_kw,
)
from app.services.power_history_service import power_history_service


class DashboardService:
    _NOMINAL_POWER_KEY_PRIORITY = (
        "rated_active_power_kw",
        "rated_power_kw",
        "power_rating_kw",
        "rated_power_unity_pf_kw",
        "inverter_max_power_kw",
        "inverter_max_power_w",
    )
    _NOMINAL_POWER_HINTS = (
        "potenza nominale",
        "rated power",
        "power rating",
        "potenza attiva nominale",
        "nominal power",
        "max power",
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

    def get_summary(self) -> DashboardSummaryResponse:
        devices = device_service.list_devices()
        total_devices = len(devices)
        online_devices = 0
        offline_devices = 0
        total_power_kw = 0.0
        nominal_power_kw = 0.0
        nominal_power_device_count = 0
        daily_energy_kwh = 0.0
        total_energy_kwh = 0.0
        active_alarms = 0

        for device in devices:
            if device.protocol in {"modbus_tcp", "modbus_rtu", "sunspec", "aurora", "delta_rs485"}:
                cache_entry = live_cache.get(device.device_id)
                nominal_device_power_kw = resolve_nominal_power_kw(
                    device=device,
                    telemetry=cache_entry.telemetry if cache_entry is not None else None,
                )
                if nominal_device_power_kw is not None and nominal_device_power_kw > 0:
                    nominal_power_kw += nominal_device_power_kw
                    nominal_power_device_count += 1
                if cache_entry is not None and device.status == "online":
                    sanitized_power_kw = sanitize_device_power_kw(
                        cache_entry.metrics.power_kw,
                        device=device,
                        telemetry=cache_entry.telemetry,
                        nominal_power_kw=nominal_device_power_kw,
                    )
                    if sanitized_power_kw is not None:
                        total_power_kw += sanitized_power_kw
                    daily_energy_kwh += cache_entry.metrics.daily_energy_kwh
                    total_energy_kwh += cache_entry.metrics.total_energy_kwh

            if device.status == "online":
                online_devices += 1
            else:
                offline_devices += 1
                if device.status != "pending":
                    active_alarms += 1

        power_utilization_percent = (
            round((abs(total_power_kw) / nominal_power_kw) * 100, 1)
            if nominal_power_kw > 0
            else None
        )
        return DashboardSummaryResponse(
            total_devices=total_devices,
            online_devices=online_devices,
            offline_devices=offline_devices,
            active_alarms=active_alarms,
            total_power_kw=round(total_power_kw, 1),
            nominal_power_kw=round(nominal_power_kw, 1),
            nominal_power_device_count=nominal_power_device_count,
            power_utilization_percent=power_utilization_percent,
            daily_energy_kwh=round(daily_energy_kwh, 1),
            total_energy_kwh=round(total_energy_kwh, 1),
        )

    def get_active_power_sum(self) -> DashboardActivePowerResponse:
        summary = self.get_summary()
        active_power_kw = round(summary.total_power_kw, 3)
        return DashboardActivePowerResponse(
            active_power_kw=active_power_kw,
            active_power_w=round(active_power_kw * 1000.0, 1),
            online_devices=summary.online_devices,
            total_devices=summary.total_devices,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def _extract_nominal_power_kw(self, telemetry: list[DeviceTelemetryPoint]) -> float | None:
        for key in self._NOMINAL_POWER_KEY_PRIORITY:
            point = next((item for item in telemetry if item.key == key), None)
            if point is None:
                continue
            value_kw = self._point_to_kw(point)
            if value_kw is not None and value_kw > 0:
                return value_kw

        for point in telemetry:
            fingerprint = f"{point.key} {point.label} {point.section}".lower()
            if not any(hint in fingerprint for hint in self._NOMINAL_POWER_HINTS):
                continue
            if any(excluded in fingerprint for excluded in self._NOMINAL_POWER_EXCLUDES):
                continue
            value_kw = self._point_to_kw(point)
            if value_kw is not None and value_kw > 0:
                return value_kw
        return None

    def _point_to_kw(self, point: DeviceTelemetryPoint) -> float | None:
        numeric_value = self._coerce_float(point.value)
        if numeric_value is None:
            numeric_value = self._coerce_float(point.raw_value)
        if numeric_value is None:
            return None

        if point.key == "inverter_max_power_w":
            return numeric_value / 1000.0

        unit = point.unit.strip().lower()
        if unit == "w":
            return numeric_value / 1000.0
        if unit == "kw" or unit == "":
            return numeric_value
        if unit == "mw":
            return numeric_value * 1000.0
        return None

    @staticmethod
    def _coerce_float(value: object) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            normalized = value.strip()
            if "," in normalized:
                normalized = normalized.replace(".", "").replace(",", ".")
            try:
                return float(normalized)
            except ValueError:
                return None
        return None

    def get_fleet_power_history(
        self,
        *,
        start_timestamp: str | None = None,
        end_timestamp: str | None = None,
        max_points: int | None = None,
    ) -> FleetPowerHistoryResponse:
        devices = device_service.list_devices()
        labels, history_matrix = power_history_service.get_fleet_history_matrix(
            [device.device_id for device in devices],
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            max_points=max_points,
        )
        if labels:
            labels, history_matrix = self._append_live_fleet_history_tail(
                devices,
                labels,
                history_matrix,
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                max_points=max_points,
            )
        else:
            labels, history_matrix = self._get_live_fleet_history_matrix(
                devices,
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                max_points=max_points,
            )
        device_series: list[PowerHistorySeries] = []
        totals_by_timestamp = {timestamp: 0.0 for timestamp in labels}

        for device in devices:
            cache_entry = live_cache.get(device.device_id)
            nominal_device_power_kw = resolve_nominal_power_kw(
                device=device,
                telemetry=cache_entry.telemetry if cache_entry is not None else None,
            )
            aligned_values = history_matrix.get(device.device_id, [0.0] * len(labels))
            rounded_values = self._sanitize_history_values(
                aligned_values,
                nominal_power_kw=nominal_device_power_kw,
            )
            device_series.append(
                PowerHistorySeries(
                    device_id=device.device_id,
                    label=device.name,
                    timestamps=labels,
                    values=rounded_values,
                )
            )

            for timestamp, value in zip(labels, rounded_values, strict=False):
                totals_by_timestamp[timestamp] += value

        total_series = PowerHistorySeries(
            label="Potenza totale",
            timestamps=labels,
            values=[round(totals_by_timestamp[timestamp], 3) for timestamp in labels],
        )

        return FleetPowerHistoryResponse(
            labels=labels,
            device_series=device_series,
            total_series=total_series,
        )

    def get_device_power_history(
        self,
        device_id: str,
        *,
        start_timestamp: str | None = None,
        end_timestamp: str | None = None,
        max_points: int | None = None,
    ) -> DevicePowerHistoryResponse | None:
        device = device_service.get_device(device_id)
        if device is None:
            return None

        history = power_history_service.get_device_history(
            device_id,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            max_points=max_points,
        )
        if not history:
            history = self._filter_live_history_samples(
                live_cache.get_power_history(device_id),
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                max_points=max_points,
            )
        else:
            history = self._append_live_device_history_tail(
                history,
                self._filter_live_history_samples(
                    live_cache.get_power_history(device_id),
                    start_timestamp=start_timestamp,
                    end_timestamp=end_timestamp,
                    max_points=None,
                ),
                max_points=max_points,
            )
        cache_entry = live_cache.get(device_id)
        nominal_device_power_kw = resolve_nominal_power_kw(
            device=device,
            telemetry=cache_entry.telemetry if cache_entry is not None else None,
        )
        labels = [sample.timestamp for sample in history]
        raw_values = [sample.power_kw for sample in history]
        return DevicePowerHistoryResponse(
            device_id=device_id,
            labels=labels,
            timestamps=labels,
            values=self._sanitize_history_values(
                raw_values,
                nominal_power_kw=nominal_device_power_kw,
            ),
        )

    def _sanitize_history_values(
        self,
        values: list[float],
        *,
        nominal_power_kw: float | None,
    ) -> list[float]:
        limit_kw = self._resolve_history_power_limit_kw(nominal_power_kw)
        sanitized_values: list[float] = []
        for value in values:
            numeric_value = self._coerce_float(value)
            if numeric_value is None or not math.isfinite(numeric_value):
                sanitized_values.append(0.0)
                continue
            sanitized_values.append(
                0.0 if abs(numeric_value) > limit_kw else round(numeric_value, 3)
            )
        return sanitized_values

    def _resolve_history_power_limit_kw(self, nominal_power_kw: float | None) -> float:
        if nominal_power_kw is None:
            return MAX_DEVICE_POWER_KW_WITHOUT_NOMINAL
        return max(
            MIN_REASONABLE_POWER_LIMIT_KW,
            nominal_power_kw * NOMINAL_POWER_LIMIT_MULTIPLIER,
            nominal_power_kw + NOMINAL_POWER_LIMIT_MARGIN_KW,
        )

    def _get_live_fleet_history_matrix(
        self,
        devices: list[object],
        *,
        start_timestamp: str | None,
        end_timestamp: str | None,
        max_points: int | None,
    ) -> tuple[list[str], dict[str, list[float]]]:
        samples_by_device = {
            device.device_id: self._filter_live_history_samples(
                live_cache.get_power_history(device.device_id),
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                max_points=None,
            )
            for device in devices
        }
        labels = sorted(
            {
                sample.timestamp
                for samples in samples_by_device.values()
                for sample in samples
            }
        )
        if not labels:
            return [], {device.device_id: [] for device in devices}

        limit = self._normalize_history_max_points(max_points)
        if len(labels) > limit:
            labels = labels[-limit:]

        history_matrix: dict[str, list[float]] = {}
        for device in devices:
            samples = samples_by_device.get(device.device_id, [])
            sample_index = 0
            latest_value = 0.0
            aligned_values: list[float] = []
            for label in labels:
                while sample_index < len(samples) and samples[sample_index].timestamp <= label:
                    latest_value = float(samples[sample_index].power_kw)
                    sample_index += 1
                aligned_values.append(latest_value)
            history_matrix[device.device_id] = aligned_values
        return labels, history_matrix

    def _append_live_fleet_history_tail(
        self,
        devices: list[object],
        labels: list[str],
        history_matrix: dict[str, list[float]],
        *,
        start_timestamp: str | None,
        end_timestamp: str | None,
        max_points: int | None,
    ) -> tuple[list[str], dict[str, list[float]]]:
        if not labels:
            return labels, history_matrix

        latest_persistent_label = labels[-1]
        samples_by_device = {
            device.device_id: self._filter_live_history_samples(
                live_cache.get_power_history(device.device_id),
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                max_points=None,
            )
            for device in devices
        }
        appended_labels = sorted(
            {
                sample.timestamp
                for samples in samples_by_device.values()
                for sample in samples
                if sample.timestamp > latest_persistent_label
            }
        )
        if not appended_labels:
            return labels, history_matrix

        combined_labels = [*labels, *appended_labels]
        limit = self._normalize_history_max_points(max_points)
        keep_from_index = max(0, len(combined_labels) - limit)
        trimmed_labels = combined_labels[keep_from_index:]
        merged_matrix: dict[str, list[float]] = {}
        for device in devices:
            device_id = device.device_id
            persistent_values = list(history_matrix.get(device_id, []))
            if len(persistent_values) < len(labels):
                persistent_values.extend([0.0] * (len(labels) - len(persistent_values)))
            persistent_values = persistent_values[: len(labels)]
            latest_value = persistent_values[-1] if persistent_values else 0.0
            samples = [
                sample
                for sample in samples_by_device.get(device_id, [])
                if sample.timestamp > latest_persistent_label
            ]
            sample_index = 0
            appended_values: list[float] = []
            for label in appended_labels:
                while sample_index < len(samples) and samples[sample_index].timestamp <= label:
                    latest_value = float(samples[sample_index].power_kw)
                    sample_index += 1
                appended_values.append(latest_value)
            merged_matrix[device_id] = [*persistent_values, *appended_values][keep_from_index:]

        return trimmed_labels, merged_matrix

    def _append_live_device_history_tail(
        self,
        persistent_history: list[PowerSample],
        live_history: list[PowerSample],
        *,
        max_points: int | None,
    ) -> list[PowerSample]:
        if not persistent_history:
            return self._filter_live_history_samples(
                live_history,
                start_timestamp=None,
                end_timestamp=None,
                max_points=max_points,
            )

        latest_persistent_label = persistent_history[-1].timestamp
        appended_samples = [
            sample for sample in live_history if sample.timestamp > latest_persistent_label
        ]
        if not appended_samples:
            return persistent_history

        combined_history = [*persistent_history, *appended_samples]
        limit = self._normalize_history_max_points(max_points)
        if len(combined_history) > limit:
            return combined_history[-limit:]
        return combined_history

    def _filter_live_history_samples(
        self,
        samples: list[PowerSample],
        *,
        start_timestamp: str | None,
        end_timestamp: str | None,
        max_points: int | None,
    ) -> list[PowerSample]:
        filtered_samples = [
            sample
            for sample in samples
            if (start_timestamp is None or sample.timestamp >= start_timestamp)
            and (end_timestamp is None or sample.timestamp <= end_timestamp)
        ]
        filtered_samples.sort(key=lambda sample: sample.timestamp)
        limit = self._normalize_history_max_points(max_points)
        if len(filtered_samples) > limit:
            return filtered_samples[-limit:]
        return filtered_samples

    def _normalize_history_max_points(self, max_points: int | None) -> int:
        if max_points is None:
            return 900
        return max(32, min(int(max_points), 900))


dashboard_service = DashboardService()
