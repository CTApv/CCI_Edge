"""Identified PVS SunSpec telemetry and expiring active-power commands."""
from dataclasses import dataclass
import math
import re
import struct
from threading import Lock
from time import monotonic
from pymodbus import FramerType
from app.catalog.fimer_pvs_catalog import (
    PVS_DRIVER, PVS_MAP, PVS_MODELS, PVS_MODEL_IDENTITY_ALIASES, commands, telemetry_points,
)
from app.core.connection_settings import get_poll_timeout_seconds, get_write_timeout_seconds
from app.services.connection_manager import connection_manager

CANONICAL_POINTS = {p.key: p for p in telemetry_points()}
CANONICAL_COMMANDS = {p.key: p for p in commands()}


def is_pvs_device(device):
    return getattr(device, "brand", "") == "ABB/FIMER" and getattr(device, "model", "") in PVS_MODELS


def decode(words, datatype):
    if not words:
        return None
    if datatype == "string":
        return struct.pack(">" + "H" * len(words), *words).decode("ascii", errors="replace").rstrip("\0 ")
    raw, width = 0, 16 * len(words)
    for word in words:
        raw = (raw << 16) | word
    signed = datatype in {"int16", "int32", "sunssf"}
    missing = 1 << (width - 1) if signed else 0 if datatype.startswith("acc") else (1 << width) - 1
    if not words or raw == missing:
        return None
    return raw - (1 << width) if signed and raw >= (1 << (width - 1)) else raw


@dataclass(frozen=True)
class PvsWriteResult:
    success: bool
    diagnostics: dict
    error: str | None = None


class FimerPvsService:
    def __init__(self):
        self._lock = Lock()
        self._maps = {}

    def _execute(self, device, command, operation):
        if not is_pvs_device(device):
            raise ValueError("Profilo ABB/FIMER PVS dedicato richiesto.")
        settings = device.connection_settings
        tcp = device.transport == "tcp"
        unit = int(settings.get("unit_id", settings.get("slave_id", 1)) if tcp else settings.get("slave_id", 1))
        if not 1 <= unit <= 247:
            raise ValueError("Unit ID PVS richiesto tra 1 e 247; broadcast escluso.")
        timeout = get_write_timeout_seconds(settings) if command else get_poll_timeout_seconds(settings, transport=device.transport)
        kwargs = dict(timeout=timeout, retries=0, operation_kind="command" if command else "poll",
            operation=lambda client: operation(client, unit))
        if tcp and device.protocol in {"modbus_tcp", "modbus_rtu"}:
            host, port = str(settings.get("host", "")), int(settings.get("port", 502))
            if not host or not 1 <= port <= 65535:
                raise ValueError("Endpoint PVS non valido.")
            return connection_manager.execute_modbus_tcp(host, port,
                framer=FramerType.RTU if device.protocol == "modbus_rtu" else FramerType.SOCKET, **kwargs)
        if device.protocol == "modbus_rtu" and device.transport == "serial" and settings.get("port"):
            return connection_manager.execute_modbus_rtu(str(settings["port"]), int(settings.get("baud_rate", 19200)),
                int(settings.get("byte_size", 8)), str(settings.get("parity", "N")), int(settings.get("stop_bits", 1)),
                advanced_options=settings, **kwargs)
        raise ValueError("Trasporto PVS non supportato.")

    @staticmethod
    def _read(client, unit, address, count):
        response = client.read_holding_registers(address, count=count, device_id=unit)
        words = list(getattr(response, "registers", []))
        if response.isError() or len(words) != count:
            raise RuntimeError(f"Lettura PVS rifiutata/incompleta a {address}.")
        return words

    def _discover(self, client, unit):
        if self._read(client, unit, 40000, 2) != [0x5375, 0x6E53]:
            raise ValueError("Firma SunSpec PVS assente a 40000.")
        models, address = {}, 40002
        for _ in range(64):
            did, length = self._read(client, unit, address, 2)
            if did == 0xFFFF:
                if length != 0 or not {1, 103}.issubset(models):
                    raise ValueError("Mappa SunSpec PVS incompleta.")
                return models
            if did == 0 or did in models or not 0 < length <= 1024 or address + length + 2 > 65535:
                raise ValueError("Intestazione SunSpec PVS non valida o duplicata.")
            models[did] = (address, length)
            address += length + 2
        raise ValueError("Mappa SunSpec PVS senza terminatore entro 64 modelli.")

    def _block(self, client, unit, models, did):
        address, length = models[did]
        words = []
        for offset in range(0, length + 2, 120):
            words += self._read(client, unit, address + offset, min(120, length + 2 - offset))
        if words[:2] != [did, length]:
            raise ValueError("Mappa PVS cambiata durante la lettura.")
        return words

    @staticmethod
    def _value(blocks, did, name):
        words = blocks.get(did)
        definition = PVS_MAP["models"][str(did)]["fields"][name]
        start, length = definition["offset"], definition["length"]
        if words is None or start + length > len(words):
            return None
        result = decode(words[start:start + length], definition["datatype"])
        if result is not None and "sf_offset" in definition:
            sf_offset = definition["sf_offset"]
            sf = decode(words[sf_offset:sf_offset+1], "sunssf")
            result = None if sf is None or not -10 <= sf <= 10 else result * 10 ** sf
        return result

    def _identity(self, client, unit, models, device):
        if models[1][1] != 66 or models[103][1] != 50:
            raise ValueError("Versione dei modelli Common/103 PVS non compatibile.")
        common = self._block(client, unit, models, 1)
        manufacturer = self._value({1: common}, 1, "Mn")
        name = self._value({1: common}, 1, "Md")
        code, _ = PVS_MODELS[device.model]
        if not re.match(r"^(ABB|FIMER|POWER[- ]ONE)(?:\b|$)", manufacturer, re.I):
            raise ValueError("Costruttore diverso da ABB/FIMER.")
        identifiers = (code, *PVS_MODEL_IDENTITY_ALIASES.get(device.model, ()))
        pattern = r"(?<![A-Z0-9])(?:" + "|".join(re.escape(item) for item in identifiers) + r")(?![A-Z0-9])"
        if not re.search(pattern, name, re.I):
            raise ValueError(f"Modello/taglia/versione PVS diversa dal profilo {device.model}: {name}.")
        return common, name

    @staticmethod
    def _canonical(point, definitions):
        expected = definitions.get(point.key)
        if expected is None or any(getattr(point, k) != getattr(expected, k) for k in
                ("address", "length", "datatype", "scale", "unit", "register_type")) or point.protocol_meta != expected.protocol_meta:
            raise ValueError("Mappa PVS modificata rispetto al profilo verificato.")

    def read_points(self, device, points):
        for point in points:
            self._canonical(point, CANONICAL_POINTS)
        def operation(client, unit):
            key = (device.model, device.protocol, device.transport, tuple(sorted(device.connection_settings.items())))
            # Settings can contain structured diagnostic options; key uses stable repr.
            key = repr(key)
            with self._lock:
                cached = self._maps.get(key)
            models = cached[1] if cached and monotonic() - cached[0] < 30 else self._discover(client, unit)
            try:
                common, _ = self._identity(client, unit, models, device)
                blocks = {1: common}
                for did in {int(p.protocol_meta["did"]) for p in points}:
                    if did in models and did not in blocks:
                        blocks[did] = self._block(client, unit, models, did)
                count = self._value(blocks, 160, "N") if 160 in blocks else None
                if count is not None and not 1 <= count <= 6:
                    raise ValueError("Numero canali MPPT PVS non compatibile.")
                values = {}
                for p in points:
                    channel = p.protocol_meta.get("channel")
                    values[p.key] = None if channel and (count is None or channel > count) else self._value(
                        blocks, int(p.protocol_meta["did"]), p.protocol_meta["field"])
                with self._lock:
                    self._maps[key] = (monotonic(), models)
                return values
            except Exception:
                with self._lock:
                    self._maps.pop(key, None)
                raise
        return self._execute(device, False, operation)

    def write(self, device, point, value):
        diag = {"stub_mode": False, "driver": PVS_DRIVER, "write_attempted": False,
            "write_accepted": False, "readback_confirmed": False, "physical_execution_confirmed": False}
        def failed(exc):
            diag["stage"] = "uncertain" if diag["write_attempted"] else "blocked"
            return PvsWriteResult(False, diag, str(exc))
        try:
            self._canonical(point, CANONICAL_COMMANDS)
            if isinstance(value, bool) or not math.isfinite(value) or not (0 <= value <= 100 if point.key == "active_power_limit" else value == 0):
                raise ValueError("Valore comando PVS non valido.")
            def operation(client, unit):
                try:
                    models = self._discover(client, unit)
                    _, name = self._identity(client, unit, models, device)
                    if 123 not in models or models[123][1] != 24 or not {120, 121}.issubset(models):
                        raise ValueError("Modelli PVS 120/121/123 assenti o incompatibili.")
                    rating = self._value({120: self._block(client, unit, models, 120)}, 120, "WRtg")
                    maximum = self._value({121: self._block(client, unit, models, 121)}, 121, "WMax")
                    if rating is None or abs(rating - PVS_MODELS[device.model][1] * 1000) > 500 or maximum is None or not 0 < maximum <= rating * 1.01:
                        raise ValueError("Potenza nominale/base WMax PVS non valida.")
                    before = self._block(client, unit, models, 123)
                    base = models[123][0]
                    if point.key == "active_power_limit":
                        sf = decode(before[23:24], "sunssf")
                        if sf is None or not -4 <= sf <= 0:
                            raise ValueError("Scala percentuale PVS non valida.")
                        raw = round(value / 10 ** sf)
                        if not 0 <= raw <= 65534:
                            raise ValueError("Riferimento PVS non rappresentabile.")
                        address, words = base + 5, [raw, 0, 120, 0, 1]
                        diag.update(reference_pct=raw * 10 ** sf, revert_seconds=120, refresh_interval_seconds=45)
                    else:
                        address, words = base + 9, [0]
                    diag.update(detected_model=name, requested_value=value, maximum_power_w=maximum, absolute_register=address)
                    diag["write_attempted"] = True
                    response = client.write_registers(address, words, device_id=unit)
                    if response.isError() or response.address != address or response.count != len(words):
                        raise RuntimeError("Scrittura PVS non confermata; verificare Modbus Power Control e priorita.")
                    diag["write_accepted"] = True
                    if self._read(client, unit, address, len(words)) != words:
                        raise RuntimeError("Rilettura PVS diversa dal comando; esito incerto.")
                    diag.update(readback_confirmed=True, stage="reference_confirmed")
                    return PvsWriteResult(True, diag)
                except Exception as exc:
                    # Return inside manager callback: a lost ACK must not trigger
                    # the manager's reconnect-and-repeat callback mechanism.
                    return failed(exc)
            return self._execute(device, True, operation)
        except Exception as exc:
            return failed(exc)


fimer_pvs_service = FimerPvsService()
