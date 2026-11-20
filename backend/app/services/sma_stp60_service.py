"""SMA TI en-15 fixed profile with identity, headers and shared 1 Hz pacing."""
import math
import struct
from threading import Lock
from time import monotonic, sleep

from app.catalog.sma_stp60_catalog import SMA_DRIVER, MANAGER_MODEL, INVERTER_MODEL
from app.core.connection_settings import get_poll_timeout_seconds, get_write_timeout_seconds
from app.services.connection_manager import connection_manager


class SmaStp60Service:
    def __init__(self):
        self._lock = Lock()
        self._last_request = {}
        self._identities = {}

    def _call(self, device, callback):
        # Guard all SMA requests across units on the same Manager. No lowerable delay setting.
        key = (device.connection_settings['host'], int(device.connection_settings.get('port', 502)))
        with self._lock:
            delay = self._last_request.get(key, float('-inf')) + 1.0 - monotonic()
            if delay > 0:
                sleep(delay)
            self._last_request[key] = monotonic()
            return callback()

    def _read(self, client, device, unit, address, count):
        def request():
            try:
                return client.read_holding_registers(address, count=count, device_id=unit)
            except TypeError:
                return client.read_holding_registers(address, count=count, slave=unit)
        response = self._call(device, request)
        words = list(getattr(response, 'registers', []))
        if response.isError() or len(words) != count:
            raise RuntimeError(f'SMA: lettura rifiutata o incompleta al registro {address}.')
        return words

    @staticmethod
    def _decode(words, datatype):
        if datatype == 'string':
            return struct.pack('>' + 'H'*len(words), *words).decode('ascii', errors='replace').rstrip('\0 ')
        raw = int.from_bytes(struct.pack('>' + 'H'*len(words), *words), 'big')
        bits = 16*len(words)
        signed = datatype in {'int16', 'sunssf'}
        unavailable = 1 << (bits-1) if signed else 0 if datatype.startswith('acc') else (1 << bits)-1
        if raw == unavailable:
            return None
        return raw - (1 << bits) if signed and raw >= 1 << (bits-1) else raw

    def _identity(self, client, device, unit, *, fresh=False):
        key = (device.connection_settings['host'], int(device.connection_settings.get('port', 502)), unit, device.model)
        with self._lock:
            cached = self._identities.get(key)
        if not fresh and cached and monotonic()-cached[0] < 60:
            return cached[1]
        words = self._read(client, device, unit, 40000, 70)
        if words[:4] != [0x5375, 0x6e53, 1, 66]:
            raise ValueError('SMA: firma o Common Model diverso dalla mappa documentata.')
        manufacturer = self._decode(words[4:20], 'string')
        model = self._decode(words[20:36], 'string')
        manager = device.model == MANAGER_MODEL
        if device.model not in {MANAGER_MODEL, INVERTER_MODEL}:
            raise ValueError('Profilo SMA sconosciuto.')
        firmware = self._decode(words[44:52], 'string')
        # Unit ID ranges are validated by role. Old addressing is explicit, never guessed.
        legacy = unit == 1 if manager else 2 <= unit <= 43
        allowed = unit in {1, 125} if manager else 2 <= unit <= 43 or 126 <= unit <= 167
        if not allowed or words[68] != unit:
            raise ValueError('SMA: Unit ID non coerente con ruolo o identità rilevata.')
        if manufacturer.upper() != 'SMA' or (model != 'SMA Inverter Manager' if manager else model.upper().replace(' ', '').replace('-', '') not in {'STP60', 'STP6010'}):
            raise ValueError(f'Profilo SMA non corrispondente al dispositivo: {manufacturer} {model}.')
        result = {'words': words, 'model': model, 'firmware': firmware, 'legacy_addressing': legacy}
        with self._lock:
            self._identities[key] = (monotonic(), result)
        return result

    def _execute(self, device, command, operation):
        if device.protocol != 'modbus_tcp' or device.transport != 'tcp':
            raise ValueError('SMA STP60 richiede Modbus TCP tramite Inverter Manager.')
        settings = device.connection_settings
        unit = int(settings.get('unit_id', 0))
        manager = device.model == MANAGER_MODEL
        if not (unit in {1, 125} if manager else 2 <= unit <= 43 or 126 <= unit <= 167):
            raise ValueError('Unit ID SMA non valido per il profilo selezionato.')
        if command and not manager:
            raise ValueError('I comandi SMA agiscono sul gruppo tramite il Manager, non sul singolo STP60.')
        def guarded(client):
            try:
                return operation(client, unit)
            except Exception as exc:
                # Prevent the connection manager from replaying an uncertain write operation.
                if command:
                    raise RuntimeError(str(exc)) from exc
                raise
        return connection_manager.execute_modbus_tcp(host=str(settings['host']), port=int(settings.get('port', 502)),
            timeout=get_write_timeout_seconds(settings) if command else get_poll_timeout_seconds(settings, transport='tcp'),
            retries=0, operation_kind='command' if command else 'poll', operation=guarded)

    def read_points(self, device, points):
        def operation(client, unit):
            identity = self._identity(client, device, unit)
            blocks = {40000: identity['words']}
            for base, count, header in [(40185, 52, [103, 50]), (40237, 28, [120, 26]),
                                        (40265, 32, [121, 30]), (40343, 26, [123, 24])]:
                if not any(base <= p.address < base+count for p in points):
                    continue
                words = self._read(client, device, unit, base, count)
                if words[:2] != header:
                    raise ValueError(f'SMA: mappa diversa da TI en-15 a {base}; nessuna interpretazione automatica.')
                blocks[base] = words
            def word_at(address, count):
                for base, words in blocks.items():
                    offset = address-base
                    if 0 <= offset and offset+count <= len(words):
                        return words[offset:offset+count]
                raise ValueError('Punto SMA fuori mappa documentata.')
            values = {}
            for point in points:
                value = self._decode(word_at(point.address, point.length), point.datatype)
                sf_addr = point.protocol_meta.get('sf_address')
                if value is not None and sf_addr is not None:
                    sf = self._decode(word_at(sf_addr, 1), 'sunssf')
                    value = None if sf is None or not -10 <= sf <= 10 else value * 10**sf
                values[point.key] = value
            return values
        return self._execute(device, False, operation)

    def write_point(self, device, point, value):
        if point.protocol_meta.get('driver') != SMA_DRIVER or not point.writable:
            raise ValueError('Comando SMA non autorizzato dal profilo.')
        bounds = {'active_power_limit': (0, 100), 'start_inverter': (1, 1), 'stop_inverter': (0, 0)}
        if point.key not in bounds or not math.isfinite(value) or not bounds[point.key][0] <= value <= bounds[point.key][1]:
            raise ValueError('Valore comando SMA fuori intervallo.')
        def operation(client, unit):
            identity = self._identity(client, device, unit, fresh=True)
            controls = self._read(client, device, unit, 40343, 26)
            if controls[:2] != [123, 24]:
                raise ValueError('SMA: IC123 diverso dalla mappa documentata.')
            if point.key == 'active_power_limit':
                sf = self._decode(controls[23:24], 'sunssf')
                if sf != -2:
                    raise ValueError('SMA: fattore di scala limite potenza inatteso.')
                address, encoded = 40348, round(value*100)
            else:
                address, encoded = 40347, int(value)
            # Single writable register. Enable/timing registers are read-only on SMA.
            def request():
                try:
                    return client.write_registers(address, [encoded], device_id=unit)
                except TypeError:
                    return client.write_registers(address, [encoded], slave=unit)
            response = self._call(device, request)
            if response.isError():
                raise RuntimeError('Comando SMA rifiutato dal Manager.')
            after = self._read(client, device, unit, 40343, 26)
            if after[:2] != [123, 24] or after[address-40343] != encoded:
                raise RuntimeError('Comando SMA inviato, rilettura non confermata; esito incerto.')
            return {'stub_mode': False, 'driver': SMA_DRIVER, 'write_accepted': True,
                'readback_confirmed': True, 'physical_execution_confirmed': False,
                'group_scope': True, 'unit_id': unit, 'absolute_register': address,
                'requested_value': value, 'limit_enabled': after[9] == 1,
                'detected_model': identity['model'], 'broadcast': False}
        return self._execute(device, True, operation)


sma_stp60_service = SmaStp60Service()
