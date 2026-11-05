from fastapi import APIRouter

from app.catalog.inverter_catalog import get_inverter_catalog

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/models")
def list_catalog_models() -> list[dict[str, object]]:
    return sorted(
        [
            {
                "brand": model.brand,
                "model": model.model,
                "protocol": model.protocol,
                "transport": model.transport,
                "defaults": model.defaults,
                "features": model.features,
                "verification": {
                    "status": str(model.catalog_meta.get("verification_status", "unclassified")),
                    "source_document": str(model.catalog_meta.get("source_document", "")) or None,
                    "source_version": str(model.catalog_meta.get("source_version", "")) or None,
                    "last_reviewed_at": str(model.catalog_meta.get("last_reviewed_at", "")) or None,
                    "field_tested": bool(model.catalog_meta.get("field_tested", False)),
                    "notes": str(model.catalog_meta.get("notes", "")) or None,
                },
                "telemetry_count": len(model.telemetry_points),
                "visible_telemetry_count": len(
                    [point for point in model.telemetry_points if point.visible]
                ),
                "command_count": len(model.command_points),
                "writable_command_count": len(
                    [point for point in model.command_points if point.writable]
                ),
                "alarm_count": len(model.alarm_points),
                "discovery_signature": {
                    "register": model.defaults.get("test_register")
                    if isinstance(model.defaults.get("test_register"), int)
                    else None,
                    "function": str(model.defaults.get("test_function"))
                    if isinstance(model.defaults.get("test_function"), str)
                    else None,
                },
                "capabilities": {
                    "has_active_power_limit": any(
                        point.key == "active_power_limit" for point in model.command_points
                    ),
                    "has_reactive_power_control": any(
                        point.key
                        in {
                            "reactive_power_target_percent",
                            "tan_phi_target",
                            "cos_phi_target",
                            "disable_reactive_targets",
                            "power_factor_setting",
                            "reactive_power_cosphi_pct",
                            "remote_reactive_power_var",
                        }
                        for point in model.command_points
                    ),
                    "has_start_stop_control": any(
                        point.key
                        in {
                            "start_inverter",
                            "stop_inverter",
                            "standby_inverter",
                            "start_stop",
                            "remote_start_stop",
                            "system_power_on_off",
                        }
                        for point in model.command_points
                    ),
                    "supports_live_telemetry": any(
                        point.visible for point in model.telemetry_points
                    ),
                    "supports_power_history": any(
                        point.protocol_meta.get("summary_metric") == "power_kw"
                        for point in model.telemetry_points
                    ),
                },
            }
            for model in get_inverter_catalog()
        ],
        key=lambda model: (
            str(model["brand"]).lower(),
            str(model["model"]).lower(),
            str(model["protocol"]).lower(),
        ),
    )
