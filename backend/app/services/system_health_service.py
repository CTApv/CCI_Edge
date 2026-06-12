from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime

from app.services.active_power_limit_resolver import active_power_limit_resolver
from app.services.adaptive_communication_service import adaptive_communication_service
from app.services.connection_manager import connection_manager
from app.services.device_runtime import build_poll_endpoint_key
from app.services.endpoint_runtime_service import endpoint_runtime_service
from app.services.device_service import device_service
from app.services.inverter_io_service import inverter_io_service
from app.services.inverter_profile_resolver import inverter_profile_resolver
from app.services.live_cache import live_cache
from app.services.modbus_tcp_slave_config_service import modbus_tcp_slave_config_service
from app.services.modbus_tcp_slave_service import modbus_tcp_slave_service
from app.services.polling_engine import SUPPORTED_POLL_PROTOCOLS, polling_engine
from app.services.power_history_service import power_history_service
from app.services.system_identity_service import system_identity_service


ACTIVE_POWER_SLO_TARGET_SECONDS = 30.0
FULL_TELEMETRY_SLO_TARGET_SECONDS = 300.0
COMMAND_SLO_TARGET_SECONDS = 2.0


class SystemHealthService:
    def get_snapshot(self) -> dict[str, object]:
        devices = device_service.list_devices()
        status_counts = self._build_status_counts(devices)
        endpoint_hotspots = self._build_endpoint_hotspots(devices)
        endpoint_runtimes = endpoint_runtime_service.get_snapshots(devices)
        serial_scheduler_snapshots = {
            (item["endpoint_type"], item["endpoint_label"]): item
            for item in polling_engine.get_serial_endpoint_snapshots(devices)
        }
        tcp_scheduler_snapshots = {
            (item["endpoint_type"], item["endpoint_label"]): item
            for item in polling_engine.get_shared_tcp_endpoint_snapshots(devices)
        }
        tcp_connection_snapshots = {
            (item["endpoint_type"], item["endpoint_label"]): item
            for item in connection_manager.get_modbus_tcp_runtime_snapshots()
        }
        adaptive_snapshots = {
            (item["endpoint_type"], item["endpoint_label"]): item
            for item in adaptive_communication_service.get_endpoint_snapshots(devices)
        }
        endpoint_runtimes = [
            self._enrich_endpoint_runtime(
                {
                    **runtime,
                    **serial_scheduler_snapshots.get(
                        (runtime["endpoint_type"], runtime["endpoint_label"]),
                        {},
                    ),
                    **tcp_scheduler_snapshots.get(
                        (runtime["endpoint_type"], runtime["endpoint_label"]),
                        {},
                    ),
                    **tcp_connection_snapshots.get(
                        (runtime["endpoint_type"], runtime["endpoint_label"]),
                        {},
                    ),
                    **adaptive_snapshots.get(
                        (runtime["endpoint_type"], runtime["endpoint_label"]),
                        {},
                    ),
                }
            )
            for runtime in endpoint_runtimes
        ]
        data_quality = self._build_data_quality_snapshot(devices)
        service_levels = self._build_service_levels_snapshot(devices, endpoint_runtimes)
        slave_config = modbus_tcp_slave_config_service.get_config()

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "identity": system_identity_service.get_snapshot(),
            "status_counts": status_counts,
            "polling": polling_engine.get_runtime_snapshot(),
            "live_cache": live_cache.get_runtime_stats(),
            "history_storage": power_history_service.get_storage_stats(),
            "modbus_tcp_slave": {
                "enabled": slave_config.enabled,
                "running": modbus_tcp_slave_service.is_running(),
                "host": slave_config.host,
                "port": slave_config.port,
                "unit_id": slave_config.unit_id,
                "startup_error": modbus_tcp_slave_service.get_startup_error(),
            },
            "broadcast_groups": self._build_broadcast_groups(devices),
            "endpoint_hotspots": endpoint_hotspots,
            "endpoint_runtimes": endpoint_runtimes,
            "data_quality": data_quality,
            "service_levels": service_levels,
        }

    def _build_status_counts(self, devices: list[object]) -> dict[str, int]:
        counts = {
            "total": len(devices),
            "online": 0,
            "pending": 0,
            "offline": 0,
            "warning": 0,
            "fault": 0,
        }
        for device in devices:
            normalized_status = str(device.status).strip().lower()
            if normalized_status in counts:
                counts[normalized_status] += 1
            else:
                counts["offline"] += 1
        return counts

    def _build_endpoint_hotspots(self, devices: list[object]) -> list[dict[str, object]]:
        grouped: dict[tuple[str, str], list[object]] = defaultdict(list)
        for device in devices:
            if device.protocol not in SUPPORTED_POLL_PROTOCOLS:
                continue
            endpoint = self._build_endpoint_key(device)
            if endpoint is None:
                continue
            grouped[endpoint].append(device)

        hotspots: list[dict[str, object]] = []
        for (endpoint_type, endpoint_label), endpoint_devices in grouped.items():
            if len(endpoint_devices) <= 1:
                continue

            online_count = sum(1 for device in endpoint_devices if str(device.status).lower() == "online")
            pending_count = sum(1 for device in endpoint_devices if str(device.status).lower() == "pending")
            offline_count = sum(1 for device in endpoint_devices if str(device.status).lower() == "offline")
            note = (
                "Endpoint condiviso: discovery, polling e scritture devono restare sequenziali."
                if endpoint_type == "tcp"
                else "Bus condiviso: attenzione a timeout, baud rate e concorrenza sul canale RS485."
            )
            hotspots.append(
                {
                    "endpoint_type": endpoint_type,
                    "endpoint_label": endpoint_label,
                    "device_count": len(endpoint_devices),
                    "online_count": online_count,
                    "pending_count": pending_count,
                    "offline_count": offline_count,
                    "note": note,
                    "devices": [
                        f"{device.name} | {device.brand} | {device.model}"
                        for device in sorted(endpoint_devices, key=lambda item: item.name.lower())
                    ],
                }
            )

        hotspots.sort(
            key=lambda item: (
                -int(item["offline_count"]),
                -int(item["pending_count"]),
                -int(item["device_count"]),
                str(item["endpoint_label"]).lower(),
            )
        )
        return hotspots

    def _build_endpoint_key(self, device: object) -> tuple[str, str] | None:
        return build_poll_endpoint_key(device)

    def _enrich_endpoint_runtime(
        self,
        runtime: dict[str, object],
    ) -> dict[str, object]:
        recommendations: list[str] = []
        endpoint_type = str(runtime.get("endpoint_type") or "")
        device_count = self._int_value(runtime.get("device_count"))
        shared = bool(runtime.get("shared"))
        average_operation_ms = self._float_value(runtime.get("average_operation_duration_ms"))
        average_round_trip_ms = self._float_value(runtime.get("average_round_trip_duration_ms"))
        priority_pending = bool(runtime.get("priority_pending", False))

        polling_profile = "standard"
        adaptive_mode = "standard"
        expected_active_power_cycle_seconds = None
        estimated_full_telemetry_cycle_seconds = None
        if endpoint_type == "tcp" and shared:
            polling_profile = "gateway_tcp_light"
            adaptive_mode = "fast_active_power"
            reference_ms = average_round_trip_ms or average_operation_ms
            if reference_ms is not None and device_count > 0:
                expected_active_power_cycle_seconds = round(
                    (reference_ms * device_count) / 1000.0,
                    1,
                )
                estimated_full_telemetry_cycle_seconds = round(
                    max(reference_ms / 1000.0, 1.0) * device_count,
                    1,
                )
            if average_operation_ms is not None and average_operation_ms >= 750.0:
                adaptive_mode = "slow_gateway"
                estimated_full_telemetry_cycle_seconds = round(45.0 * device_count, 1)
                recommendations.append(
                    "Gateway lento: la dashboard privilegia letture potenza attiva e diluisce la telemetria completa."
                )
            if priority_pending:
                recommendations.append(
                    "Comando in priorita: le letture su questo endpoint vengono sospese per lasciare libera la write."
                )
            if device_count > 16:
                recommendations.append(
                    "Molti slave sullo stesso gateway: appena possibile conviene dividerli su piu linee o gateway."
                )
        elif endpoint_type == "serial" and shared:
            polling_profile = "serial_scheduler"
            adaptive_mode = "heartbeat_plus_full"
            reference_ms = average_operation_ms or average_round_trip_ms
            if reference_ms is not None and device_count > 0:
                expected_active_power_cycle_seconds = round(
                    max(reference_ms / 1000.0, 0.05) * device_count,
                    1,
                )
                estimated_full_telemetry_cycle_seconds = expected_active_power_cycle_seconds

        reference_ms = average_round_trip_ms or average_operation_ms
        if reference_ms is not None and device_count > 0:
            if expected_active_power_cycle_seconds is None:
                expected_active_power_cycle_seconds = round(
                    max(reference_ms / 1000.0, 0.05) * device_count,
                    1,
                )
            if estimated_full_telemetry_cycle_seconds is None:
                estimated_full_telemetry_cycle_seconds = expected_active_power_cycle_seconds

        active_power_slo_state = self._classify_slo(
            expected_active_power_cycle_seconds,
            ACTIVE_POWER_SLO_TARGET_SECONDS,
        )
        full_telemetry_slo_state = self._classify_slo(
            estimated_full_telemetry_cycle_seconds,
            FULL_TELEMETRY_SLO_TARGET_SECONDS,
        )
        if active_power_slo_state == "fail":
            recommendations.append(
                "Il giro potenza stimato supera l'obiettivo operativo: verificare latenza o dividere l'endpoint."
            )
        if full_telemetry_slo_state == "fail":
            recommendations.append(
                "La telemetria completa stimata supera 5 minuti: ridurre slave per linea o ottimizzare il gateway."
            )

        if runtime.get("last_error"):
            recommendations.append(
                "Ultimo errore presente: controllare cablaggio, unit id e tempi di risposta dello slave indicato."
            )
        if self._int_value(runtime.get("quarantined_device_count")) > 0:
            recommendations.append(
                "Uno o piu slave sono isolati temporaneamente per non rallentare il resto della linea."
            )

        return {
            **runtime,
            "polling_profile": polling_profile,
            "adaptive_mode": adaptive_mode,
            "expected_active_power_cycle_seconds": expected_active_power_cycle_seconds,
            "active_power_slo_target_seconds": ACTIVE_POWER_SLO_TARGET_SECONDS,
            "active_power_slo_state": active_power_slo_state,
            "estimated_full_telemetry_cycle_seconds": estimated_full_telemetry_cycle_seconds,
            "full_telemetry_slo_target_seconds": FULL_TELEMETRY_SLO_TARGET_SECONDS,
            "full_telemetry_slo_state": full_telemetry_slo_state,
            "recommendations": recommendations[:4],
        }

    def _classify_slo(
        self,
        estimated_seconds: float | None,
        target_seconds: float,
    ) -> str:
        if estimated_seconds is None:
            return "unknown"
        if estimated_seconds <= target_seconds:
            return "pass"
        if estimated_seconds <= target_seconds * 1.5:
            return "warning"
        return "fail"

    def _build_data_quality_snapshot(self, devices: list[object]) -> dict[str, object]:
        counts = Counter({"valid": 0, "warning": 0, "invalid": 0, "unavailable": 0})
        issue_devices: list[dict[str, object]] = []
        for device in devices:
            entry = live_cache.get(str(device.device_id))
            if entry is None:
                continue

            device_counts = Counter(
                str(getattr(point, "quality", "valid"))
                for point in entry.telemetry
            )
            counts.update(device_counts)
            if not any(device_counts.get(state, 0) for state in ("warning", "invalid", "unavailable")):
                continue

            examples = [
                f"{point.label}: {point.quality_reason or point.quality}"
                for point in entry.telemetry
                if point.quality in {"warning", "invalid", "unavailable"}
            ][:4]
            issue_devices.append(
                {
                    "device_id": str(device.device_id),
                    "name": str(device.name),
                    "invalid_count": device_counts.get("invalid", 0),
                    "warning_count": device_counts.get("warning", 0),
                    "unavailable_count": device_counts.get("unavailable", 0),
                    "examples": examples,
                }
            )

        issue_devices.sort(
            key=lambda item: (
                -int(item["invalid_count"]),
                -int(item["warning_count"]),
                str(item["name"]).lower(),
            )
        )
        return {
            "total_points": sum(counts.values()),
            "valid_points": counts["valid"],
            "warning_points": counts["warning"],
            "invalid_points": counts["invalid"],
            "unavailable_points": counts["unavailable"],
            "devices_with_issues": len(issue_devices),
            "issue_devices": issue_devices[:20],
        }

    def _build_service_levels_snapshot(
        self,
        devices: list[object],
        endpoint_runtimes: list[dict[str, object]],
    ) -> dict[str, object]:
        active_power_within_target = 0
        active_power_over_target = 0
        active_power_unknown = 0
        full_telemetry_within_target = 0
        full_telemetry_over_target = 0
        full_telemetry_unknown = 0

        endpoint_device_counts = {
            (str(runtime.get("endpoint_type")), str(runtime.get("endpoint_label"))): self._int_value(
                runtime.get("device_count")
            )
            for runtime in endpoint_runtimes
        }
        for runtime in endpoint_runtimes:
            device_count = self._int_value(runtime.get("device_count"))
            active_state = str(runtime.get("active_power_slo_state", "unknown"))
            full_state = str(runtime.get("full_telemetry_slo_state", "unknown"))
            if active_state == "pass":
                active_power_within_target += device_count
            elif active_state in {"warning", "fail"}:
                active_power_over_target += device_count
            else:
                active_power_unknown += device_count

            if full_state == "pass":
                full_telemetry_within_target += device_count
            elif full_state in {"warning", "fail"}:
                full_telemetry_over_target += device_count
            else:
                full_telemetry_unknown += device_count

        covered_devices = sum(endpoint_device_counts.values())
        active_power_unknown += max(0, len(devices) - covered_devices)
        full_telemetry_unknown += max(0, len(devices) - covered_devices)
        return {
            "active_power_target_seconds": ACTIVE_POWER_SLO_TARGET_SECONDS,
            "full_telemetry_target_seconds": FULL_TELEMETRY_SLO_TARGET_SECONDS,
            "command_target_seconds": COMMAND_SLO_TARGET_SECONDS,
            "active_power_within_target": active_power_within_target,
            "active_power_over_target": active_power_over_target,
            "active_power_unknown": active_power_unknown,
            "full_telemetry_within_target": full_telemetry_within_target,
            "full_telemetry_over_target": full_telemetry_over_target,
            "full_telemetry_unknown": full_telemetry_unknown,
        }

    def _float_value(self, value: object) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _int_value(self, value: object) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _build_broadcast_groups(self, devices: list[object]) -> list[dict[str, object]]:
        grouped: dict[tuple[str, str], list[object]] = defaultdict(list)
        for device in devices:
            endpoint = self._build_broadcast_endpoint_key(device)
            if endpoint is None:
                continue
            grouped[endpoint].append(device)

        groups = [
            self._build_broadcast_group(endpoint_type, endpoint_label, endpoint_devices)
            for (endpoint_type, endpoint_label), endpoint_devices in grouped.items()
        ]
        state_priority = {"blocked": 0, "warning": 1, "ready": 2, "not_applicable": 3}
        groups.sort(
            key=lambda item: (
                state_priority.get(str(item["state"]), 9),
                -int(item["device_count"]),
                str(item["endpoint_label"]).lower(),
            )
        )
        return groups

    def _build_broadcast_endpoint_key(self, device: object) -> tuple[str, str] | None:
        protocol = getattr(device, "protocol", None)
        transport = getattr(device, "transport", None)
        connection_settings = getattr(device, "connection_settings", {})
        if not isinstance(connection_settings, dict):
            return None

        if protocol == "modbus_rtu" and transport == "serial":
            port = str(connection_settings.get("port", "")).strip()
            if not port:
                return None
            return "serial", port

        if transport == "tcp" and protocol in {"modbus_rtu", "modbus_tcp"}:
            host = str(connection_settings.get("host", "")).strip()
            port = connection_settings.get("port")
            if not host or port in {None, ""}:
                return None
            try:
                normalized_port = int(port)
            except (TypeError, ValueError):
                return None
            endpoint_type = "rtu_over_tcp" if protocol == "modbus_rtu" else "modbus_tcp_gateway"
            return endpoint_type, f"{host}:{normalized_port}"

        return None

    def _build_broadcast_group(
        self,
        endpoint_type: str,
        endpoint_label: str,
        devices: list[object],
    ) -> dict[str, object]:
        online_count = sum(1 for device in devices if str(device.status).lower() == "online")
        model_keys = {
            (
                str(getattr(device, "brand", "")),
                str(getattr(device, "model", "")),
                str(getattr(device, "protocol", "")),
                str(getattr(device, "transport", "")),
            )
            for device in devices
        }
        unit_ids = [
            unit_id
            for device in devices
            for unit_id in [self._device_unit_id(device)]
            if unit_id is not None
        ]
        duplicate_unit_ids = sorted(
            unit_id for unit_id, count in Counter(unit_ids).items() if count > 1
        )

        command_signatures: set[tuple[object, ...]] = set()
        issues: list[str] = []
        for device in devices:
            signature, issue = self._build_active_power_broadcast_signature(device)
            if issue is not None:
                issues.append(f"{device.name}: {issue}")
                continue
            if signature is not None:
                command_signatures.add(signature)

        if duplicate_unit_ids:
            issues.append(
                "Unit ID duplicati sullo stesso endpoint: "
                + ", ".join(str(unit_id) for unit_id in duplicate_unit_ids)
            )

        broadcast_mode = self._broadcast_mode(endpoint_type)
        state, summary, detail = self._classify_broadcast_group(
            endpoint_type=endpoint_type,
            device_count=len(devices),
            model_count=len(model_keys),
            command_profile_count=len(command_signatures),
            issues=issues,
        )

        return {
            "endpoint_type": endpoint_type,
            "endpoint_label": endpoint_label,
            "broadcast_mode": broadcast_mode,
            "state": state,
            "summary": summary,
            "detail": detail,
            "device_count": len(devices),
            "online_count": online_count,
            "model_count": len(model_keys),
            "command_profile_count": len(command_signatures),
            "duplicate_unit_ids": duplicate_unit_ids,
            "issues": issues[:6],
            "devices": [
                {
                    "device_id": str(device.device_id),
                    "name": str(device.name),
                    "brand": str(device.brand),
                    "model": str(device.model),
                    "protocol": str(device.protocol),
                    "transport": str(device.transport),
                    "status": str(device.status),
                    "unit_id": self._device_unit_id(device),
                }
                for device in sorted(devices, key=lambda item: str(item.name).lower())
            ],
        }

    def _broadcast_mode(self, endpoint_type: str) -> str:
        if endpoint_type == "serial":
            return "rtu_serial"
        if endpoint_type == "rtu_over_tcp":
            return "rtu_over_tcp"
        if endpoint_type == "modbus_tcp_gateway":
            return "modbus_tcp"
        return "none"

    def _classify_broadcast_group(
        self,
        *,
        endpoint_type: str,
        device_count: int,
        model_count: int,
        command_profile_count: int,
        issues: list[str],
    ) -> tuple[str, str, str]:
        if device_count < 2:
            return (
                "not_applicable",
                "Endpoint dedicato",
                "Un solo device su questo endpoint: il broadcast non porta vantaggi.",
            )

        if endpoint_type not in {"serial", "rtu_over_tcp", "modbus_tcp_gateway"}:
            return (
                "not_applicable",
                "Endpoint non broadcast",
                "Questo protocollo non ha una scrittura broadcast gestita dall'app.",
            )

        if issues or command_profile_count != 1:
            return (
                "blocked",
                "Broadcast disattivato",
                "La flotta su questo endpoint non ha un profilo comando unico o ha impostazioni da correggere.",
            )

        if model_count > 1:
            return (
                "warning",
                "Broadcast pronto con modelli misti",
                "Il comando risulta omogeneo, ma conviene verificare che la suddivisione per modello sia voluta.",
            )

        return (
            "ready",
            "Broadcast pronto",
            "I device condividono endpoint e profilo comando: l'app puo inviare una sola write broadcast.",
        )

    def _build_active_power_broadcast_signature(
        self,
        device: object,
    ) -> tuple[tuple[object, ...] | None, str | None]:
        try:
            inverter_model = inverter_profile_resolver.resolve_for_device(device)
            if inverter_model is None:
                return None, "profilo catalogo non trovato"

            resolution = active_power_limit_resolver.resolve_for_write(inverter_model, 50.0)
            if resolution is None:
                return None, "nessun comando potenza attiva risolvibile"

            signature = inverter_io_service.build_command_broadcast_signature(
                device,
                resolution.command_point,
                resolution.requested_value,
            )
            if signature is None:
                return None, "driver comando non compatibile con broadcast"
            return signature, None
        except Exception as exc:  # pragma: no cover - defensive diagnostics only
            return None, f"diagnostica profilo non riuscita: {exc}"

    def _device_unit_id(self, device: object) -> int | None:
        connection_settings = getattr(device, "connection_settings", {})
        if not isinstance(connection_settings, dict):
            return None
        for key in ("unit_id", "slave_id", "address"):
            value = connection_settings.get(key)
            if value in {None, ""}:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        return None


system_health_service = SystemHealthService()
