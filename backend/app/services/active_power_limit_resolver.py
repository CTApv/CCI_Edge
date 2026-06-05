from dataclasses import dataclass

from app.models.inverter_model import InverterModel, InverterPoint

ACTIVE_POWER_LIMIT_ALIAS_KEY = "active_power_limit"

PREFERRED_PERCENT_COMMAND_KEYS = (
    "active_power_limit",
    "active_power_limit_pct",
    "active_power_setpoint_pct",
    "power_limit_pct",
    "remote_power_limitation_pct",
    "output_power_derating_percent_set",
    "active_power_limit_battery_pv_percent",
    "active_power_limit_pv_only_percent",
    "pac_absorption_derating_pv_grid_percent",
    "pac_absorption_derating_grid_only_percent",
    "maximum_feed_grid_power_pct",
)

PREFERRED_ABSOLUTE_COMMAND_KEYS = (
    "active_power_limit_kw",
    "user_active_power_limit_kw",
    "user_active_power_reference_kw",
    "active_power_setpoint_kw",
    "set_ac_active_power_w",
    "output_power_derating_modbus_w",
    "max_feed_in_power_w_set",
    "maximum_feed_in_grid_power_w",
    "fixed_active_power_derated_kw",
    "fixed_active_power_derated_w",
)


@dataclass(slots=True, frozen=True)
class ActivePowerLimitResolution:
    command_point: InverterPoint
    requested_value: float
    conversion_mode: str


class ActivePowerLimitResolver:
    def resolve_for_write(
        self,
        inverter_model: InverterModel,
        requested_percent: float,
    ) -> ActivePowerLimitResolution | None:
        command_point = self._resolve_command_point(inverter_model)
        if command_point is None:
            return None

        if command_point.unit == "%":
            return ActivePowerLimitResolution(
                command_point=command_point,
                requested_value=requested_percent,
                conversion_mode="percent_passthrough",
            )

        if command_point.unit in {"kW", "W"}:
            max_value = command_point.protocol_meta.get("max_value")
            if isinstance(max_value, (int, float)) and max_value > 0:
                return ActivePowerLimitResolution(
                    command_point=command_point,
                    requested_value=(requested_percent / 100.0) * float(max_value),
                    conversion_mode="percent_to_absolute",
                )

        return None

    def build_overview_command_alias(
        self,
        inverter_model: InverterModel,
    ) -> tuple[InverterPoint | None, set[str]]:
        exact_point = self._find_by_key(inverter_model.command_points, ACTIVE_POWER_LIMIT_ALIAS_KEY)
        if exact_point is not None:
            return exact_point, {ACTIVE_POWER_LIMIT_ALIAS_KEY}

        resolved_point = self._resolve_command_point(inverter_model)
        if resolved_point is None:
            return None, set()

        synthetic_point = InverterPoint(
            key=ACTIVE_POWER_LIMIT_ALIAS_KEY,
            label="Setpoint potenza attiva",
            kind=resolved_point.kind,
            register_type=resolved_point.register_type,
            address=resolved_point.address,
            length=resolved_point.length,
            datatype=resolved_point.datatype,
            scale=1.0,
            unit="%",
            writable=resolved_point.writable,
            visible=resolved_point.visible,
            protocol_meta={
                **resolved_point.protocol_meta,
                "min_value": 0.0,
                "max_value": 100.0,
                "step": 0.1,
                "section": str(
                    resolved_point.protocol_meta.get("section", "Controllo potenza")
                ),
                "resolved_command_key": resolved_point.key,
                "resolved_command_unit": resolved_point.unit,
                "normalized_command": True,
            },
        )
        return synthetic_point, {resolved_point.key}

    def _resolve_command_point(self, inverter_model: InverterModel) -> InverterPoint | None:
        for key in PREFERRED_PERCENT_COMMAND_KEYS:
            point = self._find_by_key(inverter_model.command_points, key)
            if point is not None:
                return point

        percent_candidates = [
            point
            for point in inverter_model.command_points
            if point.unit == "%" and self._matches_active_power_semantics(point)
        ]
        if percent_candidates:
            return percent_candidates[0]

        for key in PREFERRED_ABSOLUTE_COMMAND_KEYS:
            point = self._find_by_key(inverter_model.command_points, key)
            if point is not None:
                return point

        absolute_candidates = [
            point
            for point in inverter_model.command_points
            if point.unit in {"kW", "W"}
            and self._matches_active_power_semantics(point)
            and isinstance(point.protocol_meta.get("max_value"), (int, float))
        ]
        if absolute_candidates:
            return absolute_candidates[0]

        return None

    def _find_by_key(self, points: list[InverterPoint], key: str) -> InverterPoint | None:
        for point in points:
            if point.key == key:
                return point
        return None

    def _matches_active_power_semantics(self, point: InverterPoint) -> bool:
        section = str(point.protocol_meta.get("section", ""))
        fingerprint = f"{point.key} {point.label} {section}".strip().lower()
        include_terms = (
            "active_power",
            "potenza attiva",
            "power limit",
            "limitazione potenza",
            "setpoint potenza",
            "power setpoint",
            "power reference",
            "riferimento potenza",
            "derating",
            "feed in power",
            "remote power limitation",
            "power_limit",
        )
        exclude_terms = (
            "reactive",
            "reattiva",
            "current",
            "corrente",
            "power factor",
            "cosphi",
            "cos phi",
            "apparent",
            "apparente",
            "phase current",
        )
        return any(term in fingerprint for term in include_terms) and not any(
            term in fingerprint for term in exclude_terms
        )


active_power_limit_resolver = ActivePowerLimitResolver()
