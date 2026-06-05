from __future__ import annotations

from dataclasses import dataclass

from app.services.dashboard_service import dashboard_service
from app.services.device_service import device_service
from app.services.fleet_setpoint_service import FleetControlState, FleetDeviceControlState
from app.services.hsm_bridge_config_service import hsm_bridge_config_service
from app.services.hsm_bridge_service import hsm_bridge_service
from app.services.modbus_tcp_slave_config_service import modbus_tcp_slave_config_service
from app.services.modbus_tcp_slave_service import modbus_tcp_slave_service
from app.services.system_health_service import system_health_service


@dataclass(slots=True, frozen=True)
class FleetControlConfidenceSnapshot:
    state: str
    requested_percent: float | None
    written_percent: float | None
    confirmed_percent: float | None
    actual_power_kw: float | None
    nominal_power_kw: float | None
    utilization_percent: float | None
    eligible_devices: int
    aligned_devices: int
    pending_devices: int
    error_devices: int
    blocked_devices: int
    telemetry_confirmed_devices: int
    last_target_at: str | None
    last_write_at: str | None
    last_confirmation_at: str | None


@dataclass(slots=True, frozen=True)
class FleetReadinessCheck:
    key: str
    label: str
    state: str
    summary: str
    detail: str


@dataclass(slots=True, frozen=True)
class FleetReadinessSnapshot:
    overall_state: str
    ready_count: int
    warning_count: int
    fail_count: int
    checks: list[FleetReadinessCheck]


class FleetRuntimeInsightsService:
    def build_control_confidence(
        self,
        *,
        state: FleetControlState,
        device_control_states: list[FleetDeviceControlState],
    ) -> FleetControlConfidenceSnapshot:
        summary = dashboard_service.get_summary()
        eligible_states = [
            item for item in device_control_states if item.eligibility == "eligible"
        ]
        requested_percent = state.active_power_limit_percent
        aligned_devices = sum(1 for item in eligible_states if item.control_state == "aligned")
        pending_devices = sum(1 for item in eligible_states if item.control_state == "pending")
        error_devices = sum(1 for item in eligible_states if item.control_state == "error")
        blocked_devices = sum(1 for item in eligible_states if item.control_state == "blocked")
        telemetry_confirmed_devices = sum(
            1 for item in eligible_states if item.telemetry_confirmed
        )
        written_percent = self._mean_percent(
            [
                item.last_sent_percent
                for item in eligible_states
                if item.last_sent_percent is not None
            ]
        )
        confirmed_percent = self._mean_percent(
            [
                item.last_applied_percent
                for item in eligible_states
                if item.last_applied_percent is not None
            ]
        )
        if requested_percent is None:
            confidence_state = "idle"
        elif len(eligible_states) <= 0:
            confidence_state = "warning"
        elif error_devices > 0 or blocked_devices > 0:
            confidence_state = "warning"
        elif pending_devices > 0:
            confidence_state = "tracking"
        elif (
            aligned_devices >= max(1, len(eligible_states))
            and telemetry_confirmed_devices > 0
            and telemetry_confirmed_devices >= max(1, len(eligible_states))
        ):
            confidence_state = "confirmed"
        elif aligned_devices > 0:
            confidence_state = "stable"
        else:
            confidence_state = "tracking"

        return FleetControlConfidenceSnapshot(
            state=confidence_state,
            requested_percent=requested_percent,
            written_percent=written_percent,
            confirmed_percent=confirmed_percent,
            actual_power_kw=summary.total_power_kw,
            nominal_power_kw=summary.nominal_power_kw,
            utilization_percent=summary.power_utilization_percent,
            eligible_devices=len(eligible_states),
            aligned_devices=aligned_devices,
            pending_devices=pending_devices,
            error_devices=error_devices,
            blocked_devices=blocked_devices,
            telemetry_confirmed_devices=telemetry_confirmed_devices,
            last_target_at=state.updated_at,
            last_write_at=self._max_timestamp(
                [
                    item.last_dispatch_at
                    for item in eligible_states
                    if item.last_sent_percent is not None
                ]
            ),
            last_confirmation_at=self._max_timestamp(
                [
                    item.last_dispatch_at
                    for item in eligible_states
                    if item.telemetry_confirmed and item.last_dispatch_at
                ]
            ),
        )

    def build_readiness(
        self,
        *,
        device_control_states: list[FleetDeviceControlState],
    ) -> FleetReadinessSnapshot:
        devices = device_service.list_devices()
        health_snapshot = system_health_service.get_snapshot()
        modbus_config = modbus_tcp_slave_config_service.get_config()
        cci_connection = modbus_tcp_slave_service.get_cci_connection_snapshot()
        hsm_config = hsm_bridge_config_service.get_config()
        hsm_runtime = hsm_bridge_service.get_runtime_snapshot()

        total_devices = len(devices)
        eligible_devices = sum(
            1 for item in device_control_states if item.eligibility == "eligible"
        )
        ineligible_devices = sum(
            1 for item in device_control_states if item.eligibility == "ineligible"
        )
        offline_devices = sum(
            1 for item in device_control_states if str(item.device_status).lower() == "offline"
        )
        warning_devices = sum(
            1
            for item in device_control_states
            if str(item.device_status).lower() in {"warning", "fault"}
        )

        checks: list[FleetReadinessCheck] = []
        if total_devices == 0:
            checks.append(
                FleetReadinessCheck(
                    key="devices",
                    label="Flotta inverter",
                    state="fail",
                    summary="Nessun dispositivo configurato",
                    detail="Aggiungi almeno un inverter prima del commissioning della dashboard operatore.",
                )
            )
        elif eligible_devices <= 0:
            checks.append(
                FleetReadinessCheck(
                    key="devices",
                    label="Flotta inverter",
                    state="fail",
                    summary="Nessun dispositivo compatibile col controllo potenza",
                    detail="I device presenti non espongono un comando valido per il target globale.",
                )
            )
        elif ineligible_devices > 0 or offline_devices > 0 or warning_devices > 0:
            checks.append(
                FleetReadinessCheck(
                    key="devices",
                    label="Flotta inverter",
                    state="warn",
                    summary=(
                        f"{eligible_devices}/{total_devices} pronti, "
                        f"{ineligible_devices} non compatibili, {offline_devices} offline"
                    ),
                    detail=(
                        "Controlla i profili dei device non compatibili e verifica quelli offline "
                        "prima della messa in servizio."
                    ),
                )
            )
        else:
            checks.append(
                FleetReadinessCheck(
                    key="devices",
                    label="Flotta inverter",
                    state="pass",
                    summary=f"{eligible_devices}/{total_devices} device pronti al target globale",
                    detail="I dispositivi configurati risultano compatibili e raggiungibili dal runtime.",
                )
            )

        slave_startup_error = modbus_tcp_slave_service.get_startup_error()
        if not modbus_config.enabled:
            checks.append(
                FleetReadinessCheck(
                    key="cci_runtime",
                    label="Slave CCI",
                    state="warn",
                    summary="Slave Modbus TCP disabilitato",
                    detail="Abilita il servizio se il commissioning richiede il collegamento del CCI sulla nostra porta Modbus TCP.",
                )
            )
        elif slave_startup_error is not None or not modbus_tcp_slave_service.is_running():
            checks.append(
                FleetReadinessCheck(
                    key="cci_runtime",
                    label="Slave CCI",
                    state="fail",
                    summary="Slave Modbus TCP non operativo",
                    detail=slave_startup_error
                    or "Il runtime del nostro slave Modbus TCP non e in esecuzione.",
                )
            )
        else:
            checks.append(
                FleetReadinessCheck(
                    key="cci_runtime",
                    label="Slave CCI",
                    state="pass",
                    summary=f"Online su {modbus_config.host}:{modbus_config.port} | ID {modbus_config.unit_id}",
                    detail="Lo slave Modbus TCP e attivo e pronto a ricevere il setpoint dal CCI.",
                )
            )

        if not modbus_config.cci_enabled:
            checks.append(
                FleetReadinessCheck(
                    key="cci_link",
                    label="Collegamento CCI",
                    state="warn",
                    summary="Controllo CCI disabilitato",
                    detail="Il runtime del CCI e spento lato applicazione: il target verra accettato solo da sorgenti manuali o API.",
                )
            )
        elif not modbus_config.enabled or not modbus_tcp_slave_service.is_running():
            checks.append(
                FleetReadinessCheck(
                    key="cci_link",
                    label="Collegamento CCI",
                    state="fail",
                    summary="Canale CCI non raggiungibile",
                    detail="Lo slave Modbus TCP non e online, quindi il CCI non puo collegarsi alla dashboard.",
                )
            )
        elif cci_connection.status == "online":
            checks.append(
                FleetReadinessCheck(
                    key="cci_link",
                    label="Collegamento CCI",
                    state="pass",
                    summary="CCI connesso al nostro slave",
                    detail="La linea di comando del CCI e viva e sta dialogando con il backend.",
                )
            )
        elif cci_connection.status == "offline":
            checks.append(
                FleetReadinessCheck(
                    key="cci_link",
                    label="Collegamento CCI",
                    state="warn",
                    summary="Nessuna connessione CCI attiva",
                    detail="Il servizio e pronto ma al momento non vede alcun client CCI collegato.",
                )
            )
        else:
            checks.append(
                FleetReadinessCheck(
                    key="cci_link",
                    label="Collegamento CCI",
                    state="warn",
                    summary="In attesa della prima connessione CCI",
                    detail="Il runtime e pronto: collega il CCI o completa il test di commissioning sul canale Modbus TCP.",
                )
            )

        if not hsm_config.enabled:
            checks.append(
                FleetReadinessCheck(
                    key="hsm_bridge",
                    label="Bridge HSM",
                    state="pass",
                    summary="Bridge non abilitato",
                    detail="Va bene cosi se questo impianto non richiede l'inoltro HSM verso la linea inverter.",
                )
            )
        elif hsm_runtime.startup_error is not None or not hsm_runtime.running:
            checks.append(
                FleetReadinessCheck(
                    key="hsm_bridge",
                    label="Bridge HSM",
                    state="fail",
                    summary="Bridge HSM non operativo",
                    detail=hsm_runtime.startup_error
                    or "Il servizio HSM e abilitato ma non risulta in esecuzione.",
                )
            )
        elif not hsm_runtime.line_ready:
            checks.append(
                FleetReadinessCheck(
                    key="hsm_bridge",
                    label="Bridge HSM",
                    state="fail",
                    summary="Linea inverter non pronta per il bridge",
                    detail=hsm_runtime.line_note
                    or "La porta inverter selezionata non risolve una linea Modbus RTU valida.",
                )
            )
        else:
            checks.append(
                FleetReadinessCheck(
                    key="hsm_bridge",
                    label="Bridge HSM",
                    state="pass",
                    summary="Runtime attivo e linea pronta",
                    detail=hsm_runtime.line_note
                    or "Il bridge HSM e allineato con la linea inverter configurata.",
                )
            )

        serial_runtime_items = [
            runtime
            for runtime in health_snapshot["endpoint_runtimes"]
            if runtime.get("endpoint_type") == "serial"
        ]
        serial_attention_items = [
            runtime
            for runtime in serial_runtime_items
            if runtime.get("state") in {"degraded", "cooldown"}
            or int(runtime.get("offline_count", 0) or 0) > 0
        ]
        if not serial_runtime_items:
            checks.append(
                FleetReadinessCheck(
                    key="serial_lines",
                    label="Linee seriali",
                    state="pass",
                    summary="Nessuna linea seriale condivisa",
                    detail="L'assetto attuale non espone bus RS485 da presidiare in commissioning.",
                )
            )
        elif serial_attention_items:
            checks.append(
                FleetReadinessCheck(
                    key="serial_lines",
                    label="Linee seriali",
                    state="warn",
                    summary=f"{len(serial_attention_items)} endpoint seriali da verificare",
                    detail="Controlla timeout, baud rate e condivisione del bus prima di chiudere il commissioning.",
                )
            )
        else:
            checks.append(
                FleetReadinessCheck(
                    key="serial_lines",
                    label="Linee seriali",
                    state="pass",
                    summary=f"{len(serial_runtime_items)} endpoint seriali stabili",
                    detail="Le linee RS485 attive risultano stabili dal punto di vista del runtime.",
                )
            )

        polling_snapshot = health_snapshot["polling"]
        status_counts = health_snapshot["status_counts"]
        if not bool(polling_snapshot.get("running", False)):
            checks.append(
                FleetReadinessCheck(
                    key="polling",
                    label="Feedback inverter",
                    state="fail",
                    summary="Polling engine fermo",
                    detail="La dashboard non sta leggendo i device, quindi non puo confermare i target applicati.",
                )
            )
        elif int(polling_snapshot.get("pollable_device_count", 0) or 0) <= 0:
            checks.append(
                FleetReadinessCheck(
                    key="polling",
                    label="Feedback inverter",
                    state="warn",
                    summary="Nessun device ancora in polling",
                    detail="Completa il provisioning o verifica i profili per attivare il feedback telemetrico.",
                )
            )
        elif int(polling_snapshot.get("last_error_count", 0) or 0) > 0:
            checks.append(
                FleetReadinessCheck(
                    key="polling",
                    label="Feedback inverter",
                    state="warn",
                    summary=(
                        f"{polling_snapshot.get('last_error_count', 0)} errori "
                        "nell'ultimo ciclo di lettura"
                    ),
                    detail="La dashboard sta leggendo gli inverter ma l'ultimo ciclo non e stato completamente pulito.",
                )
            )
        elif int(status_counts.get("offline", 0) or 0) > 0:
            checks.append(
                FleetReadinessCheck(
                    key="polling",
                    label="Feedback inverter",
                    state="warn",
                    summary=f"{status_counts.get('offline', 0)} device offline nel runtime",
                    detail="Il polling e vivo ma alcuni inverter non stanno ancora restituendo telemetria utile.",
                )
            )
        else:
            checks.append(
                FleetReadinessCheck(
                    key="polling",
                    label="Feedback inverter",
                    state="pass",
                    summary=(
                        f"{status_counts.get('online', 0)}/{status_counts.get('total', 0)} "
                        "device online con feedback attivo"
                    ),
                    detail="La dashboard riceve telemetria utile per confermare setpoint e produzione reale.",
                )
            )

        fail_count = sum(1 for item in checks if item.state == "fail")
        warning_count = sum(1 for item in checks if item.state == "warn")
        ready_count = sum(1 for item in checks if item.state == "pass")
        if fail_count > 0:
            overall_state = "fail"
        elif warning_count > 0:
            overall_state = "warn"
        else:
            overall_state = "pass"

        return FleetReadinessSnapshot(
            overall_state=overall_state,
            ready_count=ready_count,
            warning_count=warning_count,
            fail_count=fail_count,
            checks=checks,
        )

    def _mean_percent(self, values: list[float | None]) -> float | None:
        numeric_values = [float(value) for value in values if value is not None]
        if not numeric_values:
            return None
        return round(sum(numeric_values) / len(numeric_values), 1)

    def _max_timestamp(self, values: list[str | None]) -> str | None:
        timestamps = [value for value in values if isinstance(value, str) and value.strip()]
        if not timestamps:
            return None
        return max(timestamps)


fleet_runtime_insights_service = FleetRuntimeInsightsService()
