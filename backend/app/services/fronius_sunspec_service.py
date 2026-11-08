"""Fronius Verto SunSpec transport, telemetry and verified control writes.

Uses the existing SunSpec transport primitives, but owns discovery, decoding
and command sequencing. No unit-zero broadcasts or grid/battery settings.
"""
import math
import re
import struct
from time import monotonic

from pymodbus import FramerType
from app.core.connection_settings import get_poll_timeout_seconds, get_write_timeout_seconds
from app.services.connection_manager import connection_manager
from app.services.kaco_sunspec_service import KacoSunSpecService

FRONIUS_DRIVER = "fronius_verto_sunspec"


class FroniusSunSpecService(KacoSunSpecService):
    def __init__(self):
        super().__init__()
        self._maps = {}

    def _execute_with_client(self, device, *, operation_kind, operation):
        settings = device.connection_settings
        command = operation_kind == 'command'
        timeout = get_write_timeout_seconds(settings) if command else get_poll_timeout_seconds(settings, transport=device.transport)
        # No automatic retransmission of an uncertain command.
        retries = 0 if command else int(settings.get('retries', 0))
        tcp = device.protocol in {'modbus_tcp', 'sunspec'} or device.transport == 'tcp'
        unit = int(settings.get('unit_id' if tcp else 'slave_id', 1))
        if not 1 <= unit <= 247:
            raise ValueError('Indirizzo inverter Fronius fuori intervallo 1–247.')
        if tcp:
            host = str(settings.get('host', ''))
            if not host:
                raise ValueError('Indirizzo IP Fronius mancante.')
            return connection_manager.execute_modbus_tcp(host=host, port=int(settings.get('port',502)),
                framer=FramerType.RTU if device.protocol=='modbus_rtu' else FramerType.SOCKET,
                timeout=timeout, retries=retries, operation_kind=operation_kind,
                operation=lambda client: operation(client,unit))
        if device.protocol != 'modbus_rtu' or not settings.get('port'):
            raise ValueError('Porta seriale Modbus RTU Fronius mancante.')
        return connection_manager.execute_modbus_rtu(port=str(settings['port']),
            baudrate=int(settings.get('baud_rate',19200)), bytesize=int(settings.get('byte_size',8)),
            parity=str(settings.get('parity','N')), stopbits=int(settings.get('stop_bits',1)),
            timeout=timeout, retries=retries, advanced_options=settings, operation_kind=operation_kind,
            operation=lambda client: operation(client,unit))

    def _read(self, client, unit, address, count):
        response = self._read_registers(client=client, register_type="holding",
            unit_value=unit, address=address, count=count)
        words = list(getattr(response, "registers", []))
        if response.isError() or len(words) != count:
            raise RuntimeError(f"Fronius: lettura Modbus incompleta o rifiutata a {address} ({count} registri).")
        return words

    def _discover_model_map(self, *, client, unit_value):
        # Strict bounded discovery: reject short frames, duplicate/invalid headers.
        from app.services.kaco_sunspec_service import DiscoveredSunSpecModel
        if not 1 <= unit_value <= 247:
            raise ValueError("Fronius richiede un indirizzo inverter tra 1 e 247; broadcast disabilitato.")
        if self._read(client, unit_value, 40000, 2) != [0x5375, 0x6e53]:
            raise ValueError("Firma SunSpec assente a 40000; verificare porta e Unit ID inverter.")
        models, address = {}, 40002
        for _ in range(64):
            did, length = self._read(client, unit_value, address, 2)
            if did == 0xffff:
                if not ({103, 113} & models.keys()) or 1 not in models:
                    raise ValueError("Mappa SunSpec inverter trifase non trovata.")
                return models
            if did == 0 or did in models or not 0 < length <= 512 or address+length+2 > 65535:
                raise ValueError("Intestazione SunSpec non valida o duplicata.")
            models[did] = [DiscoveredSunSpecModel(did, address, length)]
            address += length+2
        raise ValueError("Terminatore SunSpec non trovato entro 64 modelli.")

    def _identity(self, client, unit, models, *, variant=None):
        common = models[1][0]
        if common.length < 65:
            raise ValueError("Modello SunSpec Common incompleto.")
        words = self._read(client, unit, common.start_address+2, 32)
        def text(data):
            return struct.pack('>'+str(len(data))+'H', *data).decode('ascii', errors='replace').rstrip('\0 ')
        manufacturer, name = text(words[:16]), text(words[16:])
        if manufacturer.lower() != "fronius" or not name.lower().startswith("verto "):
            raise ValueError(f"Dispositivo diverso da Fronius Verto: {manufacturer} {name}.")
        if variant and ((variant == "plus") != (124 in models)):
            raise ValueError("Serie Verto/Plus diversa dal profilo scelto: verificare modello e presenza accumulo.")
        return name

    def _read_points_with_client(self, *, client, device, unit_value, points):
        key = self._build_cache_key(device, unit_value)
        with self._cache_lock:
            cached = self._maps.get(key)
        if cached and monotonic()-cached[0] < 30:
            models = cached[1]
        else:
            models = self._discover_model_map(client=client, unit_value=unit_value)
            self._identity(client, unit_value, models)
            with self._cache_lock:
                self._maps[key] = (monotonic(), models)
        values, blocks = {}, {}
        # One bounded read per required model, including its scale factors.
        for point in points:
            resolved = self._resolve_point(point=point, model_map=models)
            if resolved is None:
                values[point.key] = None
                continue
            model = resolved.model
            if model.did not in blocks:
                words = []
                for offset in range(0, model.length+2, 120):
                    words += self._read(client, unit_value, model.start_address+offset,
                                        min(120, model.length+2-offset))
                if words[:2] != [model.did,model.length]:
                    with self._cache_lock:
                        self._maps.pop(key,None)
                    raise ValueError('Mappa SunSpec cambiata: nuova identificazione al prossimo polling.')
                blocks[model.did] = words
            words = blocks[model.did]
            offset = resolved.absolute_address-model.start_address
            value = self._decode(words[offset:offset+resolved.length], resolved.datatype)
            if value is not None and resolved.scale_factor_offset is not None:
                sf = self._decode(words[resolved.scale_factor_offset:resolved.scale_factor_offset+1], "sunssf")
                value = None if sf is None or not -10 <= sf <= 10 else value*10**sf
            values[point.key] = value
        return values

    @staticmethod
    def _decode(words, datatype):
        if not words:
            return None
        if datatype == "string":
            return struct.pack('>'+str(len(words))+'H', *words).decode('ascii', errors='replace').rstrip('\0 ')
        if datatype == "float32":
            if len(words) != 2:
                return None
            value = struct.unpack('>f', struct.pack('>HH', *words))[0]
            return value if math.isfinite(value) else None
        signed = datatype in {"int16", "int32", "sunssf"}
        width = 16*len(words)
        raw = 0
        for word in words:
            raw = (raw << 16) | word
        # SunSpec unavailable values differ for integers, accumulators and bits.
        unavailable = 1 << (width-1) if signed else 0 if datatype.startswith('acc') else (1 << width)-1
        if raw == unavailable:
            return None
        return raw-(1 << width) if signed and raw >= 1 << (width-1) else raw

    def _write_point_with_client(self, *, client, device, unit_value, point, value):
        if not math.isfinite(value):
            raise ValueError("Il comando richiede un valore finito.")
        low, high = point.protocol_meta.get('min_value'), point.protocol_meta.get('max_value')
        if low is None or high is None or not low <= value <= high:
            raise ValueError("Valore comando Fronius fuori intervallo.")
        # Fresh discovery and identity before every write: no stale cached offsets.
        models = self._discover_model_map(client=client, unit_value=unit_value)
        name = self._identity(client, unit_value, models, variant=point.protocol_meta.get('variant'))
        rating = re.match(r'Verto\s+(\d+(?:\.\d+)?)', name, re.IGNORECASE)
        expected = point.protocol_meta.get('expected_power_kw')
        if rating is None or expected is None or float(rating[1]) != expected:
            raise ValueError('Taglia inverter diversa dal modello scelto nel catalogo; verificare il profilo.')
        if 123 not in models or models[123][0].length != 24:
            raise ValueError("Modello SunSpec Controls 123 assente o non compatibile.")
        base = models[123][0].start_address
        before = self._read(client, unit_value, base, 26)
        action = point.protocol_meta.get('action')
        if action == 'power_limit':
            sf = self._decode(before[23:24], 'sunssf')
            if sf is None or not -4 <= sf <= 0:
                raise ValueError("Fattore di scala percentuale SunSpec non valido.")
            encoded = round(value / 10**sf)
            if not 0 <= encoded <= 65534:
                raise ValueError("Riferimento non rappresentabile nel registro SunSpec.")
            offset, words = 5, [encoded, 0, before[7], before[8], 1]
        elif action == 'connection':
            offset, words = 2, [0, before[3], int(value)]
        elif action == 'disable_limit':
            offset, words = 9, [0]
        else:
            raise ValueError("Comando Fronius non riconosciuto.")
        if any(word == 0xffff for word in words):
            raise ValueError("Parametri temporali SunSpec non disponibili; nessuna scrittura.")
        # A single FC16 includes setpoint and enable; preserve configured timeout/ramp.
        # Do not retry an uncertain write. Readback is register acceptance, not production.
        try:
            response = client.write_registers(base+offset, words, device_id=unit_value)
        except TypeError:
            response = client.write_registers(base+offset, words, slave=unit_value)
        if response.isError():
            raise RuntimeError("Scrittura Fronius rifiutata: verificare Allow Control e priorità dei controlli.")
        after = self._read(client, unit_value, base+offset, len(words))
        if after != words:
            raise RuntimeError("Scrittura inviata ma rilettura diversa: esito incerto, verificare inverter.")
        return {'stub_mode': False, 'driver': FRONIUS_DRIVER, 'model_did': 123,
                'detected_model': name, 'absolute_register': base+offset,
                'requested_value': value, 'write_accepted': True, 'readback_confirmed': True,
                'physical_execution_confirmed': False, 'broadcast': False}


fronius_sunspec_service = FroniusSunSpecService()
