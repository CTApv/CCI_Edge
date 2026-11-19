"""Explicit RA1 commissioning. No PLC gate writes, fleet dispatch or reconnect."""
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Event, RLock, Thread
import json
import math
import os
import select
import socket
import struct
import time

from app.catalog.sinvert_ra1_catalog import is_ra1_device
from app.services.sinvert_ra1_service import SinvertRa1Service
from app.services.sinvert_s7_service import sinvert_s7_service
from app.services.sinvert_plc_state import require_cpu_run


def raw_float(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Riferimento numerico non valido.')
    return struct.unpack('>f', struct.pack('>f', value))[0]


class Ra1Channel:
    """COTP client with explicitly supplied, confirmed TSAPs (hexadecimal)."""
    def __init__(self, host, port, local_tsap, remote_tsap):
        src, dst = bytes.fromhex(local_tsap), bytes.fromhex(remote_tsap)
        if not 1 <= len(src) <= 32 or not 1 <= len(dst) <= 32:
            raise ValueError('TSAP richiesti: 1..32 byte esadecimali ciascuno.')
        self.sock = socket.create_connection((host, port), .6)
        self.sock.settimeout(.6)
        try:
            body = b'\xe0\0\0\0\x01\0' + bytes([0xc1, len(src)]) + src + bytes([0xc2, len(dst)]) + dst + b'\xc0\x01\x0a'
            self.sock.sendall(b'\x03\0' + struct.pack('>H', len(body) + 5) + bytes([len(body)]) + body)
            cc = self.receive()
            if len(cc) < 7 or cc[0] + 1 != len(cc) or cc[1] != 0xd0 or cc[2:4] != b'\0\x01':
                raise ConnectionError('Il CP non ha accettato la connessione ISO-on-TCP RA1.')
        except Exception:
            self.close()
            raise

    def exact(self, count):
        data = b''
        while len(data) < count:
            part = self.sock.recv(count - len(data))
            if not part:
                raise ConnectionError('Canale CP chiuso.')
            data += part
        return data

    def receive(self):
        header = self.exact(4)
        size = int.from_bytes(header[2:], 'big')
        if header[:2] != b'\x03\0' or not 7 <= size <= 65535:
            raise ConnectionError('TPKT RA1 non valido.')
        return self.exact(size - 4)

    def send(self, payload):
        if len(payload) != 64 or payload[:32] != bytes(32) or payload[36:] != bytes(28):
            raise ValueError('Ammesso solo il riferimento A; gli altri campi devono essere neutri.')
        self.sock.sendall(b'\x03\0\x00\x47\x02\xf0\x80' + payload)
        # Drain bounded COTP data fragments; never starve the transmit watchdog.
        for _ in range(4):
            if not select.select([self.sock], [], [], 0)[0]:
                break
            body = self.receive()
            if len(body) < 3 or body[:2] != b'\x02\xf0':
                raise ConnectionError('Risposta COTP RA1 inattesa.')

    def close(self):
        self.sock.close()


@dataclass
class Ra1Session:
    device: object
    endpoint: tuple
    options: dict
    value: float
    client: object = None
    channel: object = None
    state: str = 'starting'
    stop: Event = field(default_factory=Event)
    lock: RLock = field(default_factory=RLock)
    thread: Thread | None = None
    deadline: float = 0
    last_sent: float = 0
    last_program_check: float = 0
    sent_count: int = 0
    last_encoded: bytes = b''
    write_attempted: bool = False
    feedback: dict = field(default_factory=dict)
    error: str | None = None


class SinvertRa1LabService:
    interval = .8
    max_gap = 3.5
    lease_seconds = 60

    @staticmethod
    def verify(client):
        from snap7.type import Block
        SinvertRa1Service._verify(client)
        info = client.get_block_info(Block.FC, 500)
        if (int(info.MC7Size), int(info.CheckSum)) != (732, 40259):
            raise ValueError('Firma FC500 diversa: watchdog/canale RA1 non riconosciuto.')

    def __init__(self, client_factory=None, channel_factory=Ra1Channel, audit=None, device_getter=None):
        self.client_factory = client_factory
        self.channel_factory = channel_factory
        self.audit_callback = audit
        self.device_getter = device_getter
        self._lock = RLock()
        self._sessions = {}

    @staticmethod
    def endpoint(device):
        if not is_ra1_device(device) or device.protocol != 's7_tcp' or device.transport != 'tcp' or device.profile_overrides:
            raise ValueError('Richiesto il profilo RA1 canonico, senza override.')
        s = device.connection_settings
        endpoint = (str(s.get('host', '')).strip(), int(s.get('port', 102)), int(s.get('rack', 0)), int(s.get('slot', 2)))
        if not endpoint[0] or not 1 <= endpoint[1] <= 65535 or not 0 <= endpoint[2] <= 7 or not 0 <= endpoint[3] <= 31:
            raise ValueError('Endpoint RA1 non valido.')
        return endpoint

    def audit(self, device, phase, **fields):
        row = dict(utc=datetime.now(timezone.utc).isoformat(), device_id=device.device_id,
                   kind='sinvert_ra1_lab', phase=phase, physical_execution_confirmed=False, **fields)
        if self.audit_callback:
            self.audit_callback(row)
            return
        from app.config import settings
        path = settings.database_path.parent / 'sinvert_ra1_audit.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, allow_nan=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())

    @contextmanager
    def connection(self, device):
        endpoint = self.endpoint(device)
        lock = sinvert_s7_service.endpoint_lock(*endpoint)
        if not lock.acquire(timeout=5):
            raise TimeoutError('Endpoint RA1 occupato.')
        client = None
        try:
            from snap7.client import Client
            client = (self.client_factory or (lambda: Client(auto_reconnect=False)))()
            client.connect(endpoint[0], endpoint[2], endpoint[3], tcp_port=endpoint[1])
            connection = getattr(client, 'connection', None)
            if connection is not None:
                connection.timeout = .6
                if getattr(connection, 'socket', None) is not None:
                    connection.socket.settimeout(.6)
            # Never reuse the read driver's signature cache for a write.
            self.verify(client)
            require_cpu_run(client)
            yield client
        finally:
            try:
                if client is not None:
                    try:
                        client.disconnect()
                    finally:
                        client.destroy()
            finally:
                lock.release()

    @staticmethod
    def read(client, db, offset, count):
        data = bytes(client.db_read(db, offset, count))
        if len(data) != count:
            raise ValueError('Lettura RA1 incompleta.')
        return data

    def conditions(self, client, *, bench):
        from snap7.type import Areas
        read = lambda db, offset, count: self.read(client, db, offset, count)
        require_cpu_run(client)
        configured = bytes(client.read_area(Areas.MK, 0, 51, 1))[0]
        ready = bytes(client.read_area(Areas.MK, 0, 55, 1))[0]
        if not 1 <= int.from_bytes(read(100, 6, 2), 'big') <= 32:
            raise ValueError('Numero posizioni RA1 non valido.')
        gates = read(100, 135, 1)[0]
        cp_enabled = bool(read(400, 16, 1)[0] & 128)
        if bench:
            if cp_enabled or ready or any(client.read_area(Areas.MK, 0, 102, 4)):
                raise ValueError('Prova S7 riservata al banco isolato: CP, consensi e uscite devono essere inattivi.')
        else:
            if not cp_enabled or gates & 3 != 2:
                raise ValueError('Per CP diretto occorrono ramo CP attivo, selezione esterna attiva e copia HMI A disattiva. Nessun bit viene forzato.')
            if not configured & ready & 15 or ready & ~configured & 15 or not read(3, 0, 1)[0] & 128:
                raise ValueError('Consensi di gruppo o consenso esterno RA1 assenti/incoerenti.')
            expected = {0:1, 2:440, 4:504, 6:0, 8:1864, 16:1, 18:440, 20:944, 22:0, 28:64}
            params = read(600, 0, 30)
            if any(int.from_bytes(params[o:o+2], 'big') != value for o, value in expected.items()):
                raise ValueError('Parametri CP diversi dal progetto RA1.')
            for db in (511, 944):
                frame = read(db, 0, 64)
                if frame[:32] != bytes(32) or frame[36:] != bytes(28):
                    raise ValueError('Comandi/campi diversi dal riferimento A non neutri: trasmissione vietata.')
            if read(402, 0, 2) != bytes(2) or read(402, 10, 4) != bytes(4) or any(read(402, o, 1)[0] & 3 for o in (842, 1036, 1230, 1424)):
                raise ValueError('Comando o selettore HMI attivo.')

    @staticmethod
    def validate(value, maximum):
        value, maximum = raw_float(value), raw_float(maximum)
        if not 0 < maximum <= 1000000 or not 0 <= value <= maximum:
            raise ValueError('Impostare un limite grezzo positivo e un riferimento compreso nel limite.')
        return value

    def status(self, device):
        endpoint = self.endpoint(device)
        with self._lock:
            session = self._sessions.get(endpoint)
        if not session or session.device.device_id != device.device_id:
            return dict(active=False, state='stopped', write_attempted=False, physical_execution_confirmed=False)
        with session.lock:
            return dict(active=session.state == 'active' and not session.stop.is_set(), state=session.state,
                        remaining_seconds=max(0, int(session.deadline-time.monotonic())),
                        raw_value=session.value, maximum=session.options.get('maximum'), sent_count=session.sent_count,
                        write_attempted=session.write_attempted, error=session.error,
                        feedback=dict(session.feedback), physical_execution_confirmed=False)

    def available(self, device):
        with self._lock:
            session = self._sessions.get(self.endpoint(device))
            if session and session.state in ('starting', 'active', 'stopping', 'bench_probe'):
                raise ValueError('Endpoint RA1 gia impegnato: arrestare o attendere la prova in corso.')

    def preflight(self, device, *, bench):
        with self.connection(device) as client:
            try:
                self.conditions(client, bench=bench)
                error = None
            except ValueError as exc:
                error = str(exc)
            feedback = self.feedback(client, None)
        return dict(success=error is None, error=error, program_verified=True, write_attempted=False,
                    transport='s7_bench' if bench else 'iso_on_tcp', feedback=feedback,
                    physical_execution_confirmed=False)

    def feedback(self, client, encoded):
        received = self.read(client, 944, 32, 4)
        regulator = self.read(client, 570, 2, 4)
        processed = struct.unpack('>f', self.read(client, 570, 140, 4))[0]
        flags = self.read(client, 600, 24, 1)[0]
        finite = lambda data: (v if math.isfinite(v := struct.unpack('>f', data)[0]) else None)
        return dict(received_raw=finite(received), regulator_raw=finite(regulator),
                    processed_raw=processed if math.isfinite(processed) else None,
                    received_matches=encoded is not None and received == encoded,
                    regulator_input_confirmed=encoded is not None and regulator == encoded,
                    watchdog_fault=bool(flags & 16), receive_error=bool(flags & 2))

    def probe(self, device, value, maximum, *, cpu_only_confirmed):
        if cpu_only_confirmed is not True:
            raise ValueError('Confermare banco con sola CPU e CP, senza inverter o periferiche.')
        value = self.validate(value, maximum)
        endpoint = self.endpoint(device)
        with self._lock:
            self.available(device)
            reservation = Ra1Session(device, endpoint, {}, value, state='bench_probe')
            self._sessions[endpoint] = reservation
        result = dict(success=False, write_attempted=False, write_accepted=False, restored=False,
                      stage='blocked', transport='s7_bench', physical_execution_confirmed=False,
                      watchdog_tested=False, error=None)
        encoded = struct.pack('>f', value)
        try:
            with self.connection(device) as client:
                self.conditions(client, bench=True)
                original = self.read(client, 944, 32, 4)
                if original == encoded:
                    raise ValueError('Scegliere un valore diverso dal riferimento attuale per verificare una variazione.')
                self.audit(device, 'before_probe', raw_value=value, original_hex=original.hex())
                if reservation.stop.is_set():
                    raise ValueError('Prova annullata prima della scrittura.')
                try:
                    result.update(write_attempted=True, stage='uncertain')
                    client.db_write(944, 32, bytearray(encoded))
                    deadline = time.monotonic() + .8
                    while True:
                        result['feedback'] = self.feedback(client, encoded)
                        result['write_accepted'] = result['feedback']['received_matches']
                        if result['feedback']['received_matches'] and result['feedback']['regulator_input_confirmed']:
                            result.update(success=True, write_accepted=True, stage='regulator_confirmed')
                            break
                        if time.monotonic() >= deadline:
                            result.update(stage='readback_failed', error='Riferimento scritto; ingresso del regolatore non confermato.')
                            break
                        time.sleep(.04)
                finally:
                    # Restore only while isolation and ownership still hold. Never overwrite a third party.
                    self.conditions(client, bench=True)
                    current = self.read(client, 944, 32, 4)
                    if current == encoded:
                        client.db_write(944, 32, bytearray(original))
                        result['restored'] = self.read(client, 944, 32, 4) == original
                    elif current == original:
                        result['restored'] = True
                    if not result['restored']:
                        raise RuntimeError('Ripristino non confermato: verificare DB944.DBD32 sul PLC.')
        except Exception as exc:
            result.update(success=False, error=str(exc))
            if result['write_attempted']:
                result['stage'] = 'uncertain'
        finally:
            reservation.state = 'stopped'
            reservation.write_attempted = result['write_attempted']
        try:
            self.audit(device, 'probe_result', result=result)
        except Exception as exc:
            result.update(success=False, error='Registrazione esito fallita: '+str(exc))
        return result

    def start(self, device, value, maximum, local_tsap, remote_tsap, *, connection_confirmed, exclusive_confirmed):
        if connection_confirmed is not True or exclusive_confirmed is not True:
            raise ValueError('Confermare TSAP/partner CP e controllo esclusivo del riferimento grezzo.')
        for tsap in (local_tsap, remote_tsap):
            if not isinstance(tsap, str) or not 1 <= len(bytes.fromhex(tsap)) <= 32:
                raise ValueError('Specificare entrambi i TSAP in esadecimale.')
        value = self.validate(value, maximum)
        endpoint = self.endpoint(device)
        with self._lock:
            self.available(device)
            session = Ra1Session(device, endpoint, dict(maximum=maximum, local_tsap=local_tsap, remote_tsap=remote_tsap), value)
            self._sessions[endpoint] = session
        session.thread = Thread(target=self.run, args=(session,), daemon=True, name='sinvert-ra1')
        session.thread.start()
        return self.status(device)

    def send_confirm(self, session):
        now = time.monotonic()
        if session.stop.is_set() or now >= session.deadline or (session.last_sent and now-session.last_sent > self.max_gap):
            raise TimeoutError('Arresto, scadenza sessione o cadenza watchdog persa: nessun reinvio automatico.')
        payload = bytearray(64)
        encoded = struct.pack('>f', session.value)
        payload[32:36] = encoded
        session.write_attempted = True
        session.channel.send(bytes(payload))
        session.last_sent = time.monotonic()
        session.sent_count += 1
        deadline = time.monotonic() + .6
        while True:
            session.feedback = self.feedback(session.client, encoded)
            f = session.feedback
            if f['received_matches'] and f['regulator_input_confirmed'] and not f['watchdog_fault'] and not f['receive_error']:
                session.last_encoded = encoded
                return
            if time.monotonic() >= deadline:
                raise RuntimeError('Telegramma inviato, ma ricezione/ingresso regolatore/watchdog non confermati. Canale chiuso.')
            time.sleep(.03)

    def run(self, session):
        try:
            with self.connection(session.device) as client:
                session.client = client
                self.conditions(client, bench=False)
                if self.read(client, 944, 32, 4) == struct.pack('>f', session.value):
                    raise ValueError('Per avviare il collaudo scegliere un riferimento diverso da quello attuale: serve verificare una variazione.')
                self.audit(session.device, 'before_native_start', raw_value=session.value, options=session.options)
                if session.stop.is_set():
                    raise ValueError('Avvio annullato.')
                session.channel = self.channel_factory(*session.endpoint[:2], session.options['local_tsap'], session.options['remote_tsap'])
                session.deadline = time.monotonic() + self.lease_seconds
                session.last_program_check = time.monotonic()
                with session.lock:
                    self.send_confirm(session)
                    session.state = 'active'
                self.audit(session.device, 'native_started')
                # Release the shared endpoint during the steady-state loop.
                endpoint_lock = sinvert_s7_service.endpoint_lock(*session.endpoint)
                endpoint_lock.release()
                try:
                    while not session.stop.wait(.05):
                        now = time.monotonic()
                        if now >= session.deadline or now-session.last_sent > self.max_gap:
                            raise TimeoutError('Sessione scaduta o cadenza watchdog persa; riavvio manuale richiesto.')
                        if now-session.last_sent < self.interval:
                            continue
                        if not endpoint_lock.acquire(timeout=.05):
                            continue
                        try:
                            with session.lock:
                                from app.services.device_service import device_service
                                device = (self.device_getter or device_service.get_device)(session.device.device_id)
                                if device is None or self.endpoint(device) != session.endpoint:
                                    raise ValueError('Profilo o endpoint del dispositivo cambiato.')
                                if now-session.last_program_check >= 15:
                                    self.verify(client)
                                    session.last_program_check = time.monotonic()
                                self.conditions(client, bench=False)
                                if self.read(client, 944, 32, 4) != session.last_encoded:
                                    raise ValueError('Riferimento CP modificato da un altro produttore: canale chiuso.')
                                self.send_confirm(session)
                        finally:
                            endpoint_lock.release()
                finally:
                    try:
                        if session.channel is not None:
                            session.channel.close()
                    finally:
                        endpoint_lock.acquire()
        except Exception as exc:
            session.error = str(exc)
        finally:
            session.stop.set()
            if session.channel is not None:
                try:
                    session.channel.close()
                except Exception as exc:
                    session.error = session.error or str(exc)
            session.state = 'fault' if session.error else 'stopped'
            try:
                self.audit(session.device, 'native_stopped', error=session.error, sent_count=session.sent_count)
            except Exception as exc:
                session.error = str(exc)
                session.state = 'fault'

    def change(self, device, value, *, renew=False):
        with self._lock:
            session = self._sessions.get(self.endpoint(device))
        if not session or session.device.device_id != device.device_id:
            raise ValueError('Nessuna sessione RA1 del dispositivo.')
        with session.lock:
            if session.state != 'active' or session.stop.is_set() or time.monotonic() >= session.deadline:
                raise ValueError('Sessione non attiva: riavvio esplicito richiesto.')
            value = self.validate(value, session.options['maximum'])
            self.audit(device, 'reference_requested', raw_value=value, renew=renew)
            session.value = value
            session.feedback = {**session.feedback, 'received_matches': False, 'regulator_input_confirmed': False}
            if renew:
                session.deadline = time.monotonic() + self.lease_seconds
        return self.status(device)

    def stop(self, device):
        with self._lock:
            session = self._sessions.get(self.endpoint(device))
        if session and session.device.device_id == device.device_id:
            session.stop.set()
            if session.thread:
                session.thread.join(timeout=2)
        return self.status(device)

    def stop_all(self):
        with self._lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            session.stop.set()
        for session in sessions:
            if session.thread:
                session.thread.join(timeout=2)


sinvert_ra1_lab_service = SinvertRa1LabService()
