"""European PVGT gateway: one shared TCP session, bounded reads and FC16 writes."""
from dataclasses import dataclass
import math
from time import monotonic, sleep

from app.catalog.xantrex_gt500_catalog import (
    GT500_E_MODELS, GT500_GATEWAY_DRIVER, GT500_FIELD_FIRMWARE,
    build_gt500_gateway_points, build_gt500_gateway_commands,
)
from app.core.connection_settings import get_poll_timeout_seconds
from app.services.connection_manager import connection_manager

READBACK_TIMEOUT_SECONDS = 12.0
READBACK_INTERVAL_SECONDS = 0.5


@dataclass(frozen=True)
class Gt500WriteResult:
    success: bool
    diagnostics: dict
    error: str | None = None


class XantrexGt500Service:
    @staticmethod
    def _endpoint(device):
        if device.brand != "Xantrex" or device.model not in GT500_E_MODELS:
            raise ValueError("PVGT12542EDI richiede il profilo GT500 E/GI dedicato.")
        if device.protocol != "modbus_tcp" or device.transport != "tcp":
            raise ValueError("PVGT12542EDI richiede Modbus TCP, non RTU o Xanbus.")
        settings = device.connection_settings
        host, port = str(settings.get("host", "")).strip(), int(settings.get("port", 502))
        unit = int(settings.get("unit_id", 1))
        if not host or not 1 <= port <= 65535 or not 1 <= unit <= 247:
            raise ValueError("Endpoint PVGT o Unit ID non valido; broadcast escluso.")
        return host, port, unit

    @staticmethod
    def _validate_point(point, canonical):
        expected = canonical.get(point.key)
        fields = ("address", "length", "register_type", "datatype", "scale", "unit", "writable", "scale_factor_key")
        if (expected is None or any(getattr(point, key) != getattr(expected, key) for key in fields)
                or point.protocol_meta.get("driver") != GT500_GATEWAY_DRIVER):
            raise ValueError("Mappa PVGT diversa da quella documentata.")

    @staticmethod
    def _read(client, unit):
        response = client.read_holding_registers(0, count=34, device_id=unit)
        words = list(getattr(response, "registers", []))
        if response.isError() or len(words) != 34:
            raise RuntimeError("Risposta PVGT incompleta o non valida.")
        if any(type(word) is not int or not 0 <= word <= 65535 for word in words):
            raise RuntimeError("Parole PVGT non valide.")
        if words[0] != 0:
            raise RuntimeError(f"Gateway PVGT: dati inverter non validi (stato {words[0]}).")
        if (words[1] not in {2, 4, 5, 6} or words[2] not in range(8)
                or words[4] not in range(5) or words[5] not in range(5)
                or not words[6] or not words[7] or words[31] > 100):
            raise RuntimeError("Firma/stati PVGT incoerenti con la mappa GT500 E.")
        return words

    def read_points(self, device, points):
        host, port, unit = self._endpoint(device)
        canonical = {p.key: p for p in build_gt500_gateway_points()}
        for point in points:
            self._validate_point(point, canonical)

        def operation(client):
            words = self._read(client, unit)
            values = {}
            for point in points:
                value = words[point.address]
                if point.datatype == "int16" and value >= 0x8000:
                    value -= 0x10000
                values[point.key] = value
            return values

        return connection_manager.execute_modbus_tcp(host, port,
            timeout=get_poll_timeout_seconds(device.connection_settings, transport="tcp"),
            retries=0, operation_kind="poll", operation=operation)

    def write(self, device, point, value):
        diagnostics = {"stub_mode": False, "driver": GT500_GATEWAY_DRIVER, "broadcast": False,
            "write_attempted": False, "write_accepted": False, "readback_confirmed": False,
            "physical_execution_confirmed": False, "stage": "preflight"}
        try:
            host, port, unit = self._endpoint(device)
            self._validate_point(point, {p.key: p for p in build_gt500_gateway_commands()})
            if device.connection_settings.get("xantrex_pvgt_control_enabled") is not True:
                raise ValueError("Controllo PVGT non abilitato: confermare prima la mappa del gateway sul sito.")
            if not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError("Limite MPPT fuori intervallo 0-100%.")
            encoded = math.floor(value + 0.5)
            diagnostics.update(requested_value=value, effective_percent=encoded, unit_id=unit,
                absolute_register=31, manual_register=32, persistent_limit=True)

            def operation(client):
                # Convert network errors to RuntimeError so the connection manager
                # cannot replay a write whose acceptance is uncertain.
                try:
                    before = self._read(client, unit)
                    if tuple(before[6:8]) != GT500_FIELD_FIRMWARE:
                        raise ValueError("Firmware PVGT non collaudato per la scrittura MPPT.")
                    if before[3] or before[2] == 7:
                        raise ValueError(f"Inverter in guasto 0x{before[3]:04X}: comando sospeso.")
                    if before[1] != 4 or before[2] not in {2, 3, 4}:
                        raise ValueError("Limite MPPT disponibile solo con obiettivo inseguimento automatico.")
                    diagnostics["previous_percent"] = before[31]
                    if before[31] == encoded:
                        diagnostics.update(stage="readback", readback_confirmed=True,
                            observed_percent=encoded, unchanged=True)
                        return
                    diagnostics.update(stage="write", write_attempted=True)
                    response = client.write_registers(31, [encoded], device_id=unit)
                    if response.isError():
                        raise RuntimeError("Scrittura limite MPPT rifiutata dal gateway.")
                    if getattr(response, "address", None) != 31 or getattr(response, "count", None) != 1:
                        raise RuntimeError("Risposta FC16 PVGT non coerente con il singolo registro scritto.")
                    diagnostics.update(write_accepted=True, stage="readback")
                    deadline = monotonic() + READBACK_TIMEOUT_SECONDS
                    # Gateway telemetry is cached for several seconds. An ACK is
                    # not evidence of application, and an immediate old value is normal.
                    while monotonic() < deadline:
                        sleep(READBACK_INTERVAL_SECONDS)
                        after = self._read(client, unit)
                        diagnostics["observed_percent"] = after[31]
                        if after[3] or after[2] == 7:
                            raise RuntimeError(f"Guasto inverter durante conferma: 0x{after[3]:04X}.")
                        if tuple(after[6:8]) != GT500_FIELD_FIRMWARE:
                            raise RuntimeError("Identita firmware cambiata durante il comando.")
                        if after[31] == encoded:
                            diagnostics["readback_confirmed"] = True
                            return
                    raise RuntimeError("Limite inviato ma rilettura non confermata entro 12 s; esito incerto.")
                except Exception as exc:
                    raise RuntimeError(str(exc)) from exc

            # Match polling's timeout to retain its existing single-client TCP
            # session. A different write timeout would recreate that connection.
            connection_manager.execute_modbus_tcp(host, port,
                timeout=get_poll_timeout_seconds(device.connection_settings, transport="tcp"),
                retries=0, operation_kind="command", operation=operation)
            return Gt500WriteResult(True, diagnostics)
        except Exception as exc:
            return Gt500WriteResult(False, diagnostics, str(exc))


xantrex_gt500_service = XantrexGt500Service()
