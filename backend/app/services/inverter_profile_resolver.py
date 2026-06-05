from dataclasses import replace

from app.catalog.inverter_catalog import get_inverter_catalog
from app.models.inverter_model import InverterModel, InverterPoint
from app.schemas.device_schemas import DeviceResponse


class InverterProfileResolver:
    def find_catalog_model(
        self,
        *,
        brand: str,
        model: str,
        protocol: str,
        transport: str,
    ) -> InverterModel | None:
        for inverter_model in get_inverter_catalog():
            if (
                inverter_model.brand == brand
                and inverter_model.model == model
                and inverter_model.protocol == protocol
                and inverter_model.transport == transport
            ):
                return inverter_model
        if protocol == "modbus_rtu" and transport == "tcp":
            for inverter_model in get_inverter_catalog():
                if (
                    inverter_model.brand == brand
                    and inverter_model.model == model
                    and inverter_model.protocol == protocol
                    and inverter_model.transport == "serial"
                ):
                    return inverter_model
        return None

    def resolve_for_device(self, device: DeviceResponse) -> InverterModel | None:
        catalog_model = self.find_catalog_model(
            brand=device.brand,
            model=device.model,
            protocol=device.protocol,
            transport=device.transport,
        )
        if catalog_model is None:
            catalog_model = self.find_catalog_model(
                brand="Generic",
                model=self._generic_model_name(device.protocol, device.transport),
                protocol=device.protocol,
                transport=device.transport,
            )
            if catalog_model is None:
                return None

        resolved_model = self._resolve_inheritance(catalog_model)
        return self._apply_device_overrides(resolved_model, device.profile_overrides)

    def get_command_point(self, inverter_model: InverterModel, key: str) -> InverterPoint | None:
        for point in inverter_model.command_points:
            if point.key == key:
                return point
        return None

    def _resolve_inheritance(self, inverter_model: InverterModel) -> InverterModel:
        if not inverter_model.inherits_from:
            return inverter_model

        parent = self._find_model_by_key(inverter_model.inherits_from)
        if parent is None:
            return inverter_model

        resolved_parent = self._resolve_inheritance(parent)
        return InverterModel(
            brand=inverter_model.brand,
            model=inverter_model.model,
            protocol=inverter_model.protocol,
            transport=inverter_model.transport,
            defaults={**resolved_parent.defaults, **inverter_model.defaults},
            features=self._merge_features(resolved_parent.features, inverter_model.features),
            telemetry_points=self._merge_points(
                resolved_parent.telemetry_points,
                inverter_model.telemetry_points,
            ),
            command_points=self._merge_points(
                resolved_parent.command_points,
                inverter_model.command_points,
            ),
            alarm_points=self._merge_points(
                resolved_parent.alarm_points,
                inverter_model.alarm_points,
            ),
        )

    def _apply_device_overrides(
        self,
        inverter_model: InverterModel,
        profile_overrides: dict[str, object],
    ) -> InverterModel:
        if not profile_overrides:
            return inverter_model

        defaults_override = profile_overrides.get("defaults")
        telemetry_override = profile_overrides.get("telemetry_points")
        command_override = profile_overrides.get("command_points")
        alarm_override = profile_overrides.get("alarm_points")

        return InverterModel(
            brand=inverter_model.brand,
            model=inverter_model.model,
            protocol=inverter_model.protocol,
            transport=inverter_model.transport,
            defaults={
                **inverter_model.defaults,
                **(defaults_override if isinstance(defaults_override, dict) else {}),
            },
            features=list(inverter_model.features),
            telemetry_points=self._apply_point_overrides(
                inverter_model.telemetry_points,
                telemetry_override,
            ),
            command_points=self._apply_point_overrides(
                inverter_model.command_points,
                command_override,
            ),
            alarm_points=self._apply_point_overrides(
                inverter_model.alarm_points,
                alarm_override,
            ),
        )

    def _apply_point_overrides(
        self,
        points: list[InverterPoint],
        overrides: object,
    ) -> list[InverterPoint]:
        if not isinstance(overrides, dict):
            return list(points)

        resolved_points: list[InverterPoint] = []
        for point in points:
            point_override = overrides.get(point.key)
            if not isinstance(point_override, dict):
                resolved_points.append(point)
                continue

            allowed_fields = {
                "label",
                "register_type",
                "address",
                "length",
                "datatype",
                "scale",
                "unit",
                "writable",
                "visible",
                "scale_factor_key",
                "protocol_meta",
            }
            sanitized_override = {
                key: value
                for key, value in point_override.items()
                if key in allowed_fields
            }

            if "protocol_meta" in sanitized_override and not isinstance(
                sanitized_override["protocol_meta"],
                dict,
            ):
                sanitized_override.pop("protocol_meta")

            resolved_points.append(replace(point, **sanitized_override))

        return resolved_points

    def _find_model_by_key(self, key: str) -> InverterModel | None:
        for inverter_model in get_inverter_catalog():
            if self._model_key(inverter_model) == key:
                return inverter_model
        return None

    def _merge_features(self, parent_features: list[str], child_features: list[str]) -> list[str]:
        merged = list(parent_features)
        for feature in child_features:
            if feature not in merged:
                merged.append(feature)
        return merged

    def _merge_points(
        self,
        parent_points: list[InverterPoint],
        child_points: list[InverterPoint],
    ) -> list[InverterPoint]:
        merged: dict[str, InverterPoint] = {point.key: point for point in parent_points}
        parent_order = [point.key for point in parent_points]
        child_only_keys: list[str] = []
        for point in child_points:
            if point.key not in merged:
                child_only_keys.append(point.key)
            merged[point.key] = point

        ordered_keys = parent_order + [key for key in child_only_keys if key not in parent_order]
        return [merged[key] for key in ordered_keys]

    def _model_key(self, inverter_model: InverterModel) -> str:
        return (
            f"{inverter_model.brand}|{inverter_model.model}|"
            f"{inverter_model.protocol}|{inverter_model.transport}"
        )

    def _generic_model_name(self, protocol: str, transport: str) -> str:
        generic_models = {
            ("modbus_rtu", "serial"): "Modbus RTU Inverter",
            ("modbus_rtu", "tcp"): "Modbus RTU Inverter",
            ("modbus_tcp", "tcp"): "Modbus TCP Inverter",
            ("sunspec", "tcp"): "SunSpec Inverter",
            ("aurora", "serial"): "Aurora Inverter",
        }
        return generic_models.get((protocol, transport), "")


inverter_profile_resolver = InverterProfileResolver()
