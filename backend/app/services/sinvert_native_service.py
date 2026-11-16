"""Explicit, leased ISO-on-TCP power-reference owner. No automatic restart/reconnect.

The 64-byte command telegram is accepted only with neutral command fields. While
owned, conflicting app commands are refused; OFF first terminates this owner.
S7 remains the independent readback path, never the reference write transport.
"""
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, RLock, Thread
import json
import math
import select
import socket
import struct
import time

from app.catalog.sinvert_s7_catalog import COMMISSIONING_MODEL
from app.services.sinvert_s7_service import sinvert_s7_service


class NativeChannel:
    def __init__(self, host, port, socket_factory=socket.create_connection):
        self.sock = socket_factory((host, port), .6)
        self.sock.settimeout(.6)
        try:
            src, dst = b'PVGUARDIAN', b'SINVERT'
            body = b'\xe0\0\0\0\x01\0' + bytes([0xc1, len(src)]) + src + bytes([0xc2, len(dst)]) + dst + b'\xc0\x01\x0a'
            self.sock.sendall(b'\x03\0' + struct.pack('>H', len(body) + 5) + bytes([len(body)]) + body)
            cc = self.receive()
            if len(cc) < 7 or cc[1] != 0xd0 or cc[2:4] != b'\0\x01':
                raise ConnectionError('Connessione ISO-on-TCP non accettata dal CP.')
        except Exception:
            self.close()
            raise

    def exact(self, size):
        result = b''
        while len(result) < size:
            part = self.sock.recv(size - len(result))
            if not part:
                raise ConnectionError('Connessione nativa chiusa dal CP.')
            result += part
        return result

    def receive(self):
        header = self.exact(4)
        size = int.from_bytes(header[2:], 'big')
        if header[:2] != b'\x03\0' or not 7 <= size <= 65535:
            raise ConnectionError('Frame TPKT non valido.')
        return self.exact(size - 4)

    def send(self, payload):
        if len(payload) != 64:
            raise ValueError('Il telegramma SINVERT deve contenere 64 byte.')
        self.sock.sendall(b'\x03\0\x00\x47\x02\xf0\x80' + payload)
        # Bound draining: an uncooperative peer cannot starve the watchdog loop.
        for _ in range(4):
            if not select.select([self.sock], [], [], 0)[0]:
                break
            body = self.receive()
            if len(body) < 3 or body[:2] != b'\x02\xf0':
                raise ConnectionError('TPDU nativa inattesa: ' + body[:16].hex())

    def close(self):
        self.sock.close()


@dataclass
class NativeSession:
    device: object
    identity: tuple
    client: object
    channel: object
    template: bytes
    value: float
    bench: bool
    original_gates: int
    deadline: float
    lock: RLock = field(default_factory=RLock)
    stop: Event = field(default_factory=Event)
    thread: Thread | None = None
    state: str = 'starting'
    error: str | None = None
    last_sent: float = 0
    sent_count: int = 0
    feedback: dict = field(default_factory=dict)
    cleanup_error: str | None = None
    last_program_check: float = 0


class SinvertNativeService:
    interval = .8
    lease_seconds = 600
    max_send_gap = 3.5  # PLC watchdog was measured at ~5.1 seconds.

    def __init__(self, *, client_factory=None, channel_factory=NativeChannel, device_getter=None, audit=None, reference=None):
        self.client_factory = client_factory
        self.channel_factory = channel_factory
        self.device_getter = device_getter
        self.audit_callback = audit
        self.reference = reference
        self._lock = RLock()
        self._sessions = {}

    @staticmethod
    def identity(device):
        s = device.connection_settings
        return (str(s.get('host', '')), int(s.get('port', 102)), int(s.get('rack', 0)), int(s.get('slot', 2)))

    def _audit(self, session, phase, **fields):
        row = {'kind': 'sinvert_native', 'device_id': session.device.device_id,
               'phase': phase, 'raw_value': session.value, 'bench_cpu_only': session.bench,
               'physical_execution_confirmed': False, **fields}
        if self.audit_callback:
            self.audit_callback(row)
        else:
            from app.services.sinvert_s7_command_service import sinvert_s7_command_service
            from datetime import datetime, timezone
            sinvert_s7_command_service._audit({'utc': datetime.now(timezone.utc).isoformat(), **row})

    def _get(self, device):
        with self._lock:
            return self._sessions.get(self.identity(device))

    def status(self, device):
        session = self._get(device)
        if not session:
            return {'active': False, 'state': 'stopped', 'remaining_seconds': 0,
                    'physical_execution_confirmed': False}
        with session.lock:
            return {'active': session.state == 'active' and not session.stop.is_set(),
                    'owner_device_id': session.device.device_id, 'state': session.state,
                    'remaining_seconds': max(0, int(session.deadline - time.monotonic())),
                    'raw_value': session.value, 'bench_cpu_only': session.bench,
                    'sent_count': session.sent_count,
                    'last_send_age_seconds': round(time.monotonic() - session.last_sent, 3) if session.last_sent else None,
                    'error': session.error, 'cleanup_error': session.cleanup_error,
                    'feedback': dict(session.feedback), 'physical_execution_confirmed': False}

    @staticmethod
    def _read(client, db, offset, size):
        return bytes(client.db_read(db, offset, size))

    def _verify_program(self, client):
        from snap7.type import Block
        reference = self.reference or json.loads((Path(__file__).parent.parent / 'catalog/sinvert_s7_command_reference.json').read_text())
        if client.get_cpu_state() != 'S7CpuStatusRun':
            raise ValueError('CPU non in RUN.')
        if client.get_cpu_info().ModuleTypeName.decode('latin1').strip('\0 ') != reference['cpu_module']:
            raise ValueError('Tipo CPU diverso dal profilo verificato.')
        for name, expected in reference['blocks'].items():
            kind = Block.FB if name.startswith('FB') else Block.FC if name.startswith('FC') else Block.OB
            actual = client.get_block_info(kind, int(name[2:]))
            if any(int(getattr(actual, k)) != v for k, v in expected.items()):
                raise ValueError(f'Programma PLC diverso dal profilo verificato ({name}).')
        for db, size in reference.get('db_sizes', {}).items():
            if client.get_block_info(Block.DB, int(db)).MC7Size != size:
                raise ValueError(f'Dimensione DB{db} diversa dal profilo verificato.')

    @staticmethod
    def _neutral(telegram):
        # A/B references only; no global pulses, numeric HMI commands, unit
        # selectors, trailing commands or unknown fields may be replayed.
        if len(telegram) != 64 or telegram[:2] != bytes(2) or telegram[10:32] != bytes(22) or telegram[40:] != bytes(24):
            raise ValueError('Telegramma con comandi o campi sconosciuti: canale nativo non avviato.')

    def _validate_device(self, device, value, bench):
        from app.services.sinvert_bench_service import sinvert_bench_service
        s = device.connection_settings
        maximum = float(s.get('sinvert_reference_max_raw', 0))
        if device.model != COMMISSIONING_MODEL or s.get('sinvert_write_mode') != 'commissioning':
            raise ValueError('Abilitare il profilo di collaudo SINVERT.')
        if isinstance(value, bool) or not math.isfinite(value) or not math.isfinite(maximum) or not 0 < maximum <= 1000000 or not 0 <= value <= maximum:
            raise ValueError('Riferimento fuori dal limite locale configurato.')
        if sinvert_bench_service.status(device)['active'] != bench:
            raise ValueError('Modo banco cambiato o scaduto: interrompere e riavviare la sessione corretta.')

    def _conditions(self, session, client, *, starting=False):
        from snap7.type import Areas
        read = lambda db, offset, n: self._read(client, db, offset, n)
        mk = lambda offset, n=1: bytes(client.read_area(Areas.MK, 0, offset, n))
        if client.get_cpu_state() != 'S7CpuStatusRun':
            raise ValueError('CPU non in RUN: trasmissione interrotta.')
        if not read(100, 3, 1)[0] & 16 or not 1 <= int.from_bytes(read(100, 6, 2), 'big') <= 32:
            raise ValueError('Configurazione M/TL non valida.')
        if mk(0)[0] & 16 or mk(23)[0] & 2:
            raise ValueError('Reinizializzazione PLC attiva.')
        if session.bench:
            if mk(55)[0] or any(mk(102, 4)):
                raise ValueError('Banco non piu isolato: consensi/uscite presenti.')
        elif not mk(55)[0] & 15 or not read(3, 0, 1)[0] & 128:
            raise ValueError('Consensi PLC assenti: trasmissione interrotta.')
        if not session.bench and (mk(34)[0] & 15 or read(64, 26, 1)[0] & 15):
            raise ValueError('Sequenza o richiesta PLC in corso: riferimento non inviato.')
        # Neutral telegram must not silently clear an HMI pulse or TEST mode.
        if read(402, 0, 2) != bytes(2) or read(402, 10, 4) != bytes(4) or any(read(402, o, 1)[0] & 3 for o in (842, 1036, 1230, 1424)):
            raise ValueError('Comando HMI o selettore TEST attivo: fermare il canale nativo prima di usarlo.')
        current = read(511, 0, 64)
        self._neutral(current)
        expected = bytearray(session.template)
        if not starting:
            expected[32:36] = struct.pack('>f', session.value)
        if current != bytes(expected):
            raise ValueError('Altro produttore ha modificato DB511: proprieta del canale persa.')
        if not starting and read(100, 135, 1)[0] & 3 != 3:
            raise ValueError('Abilitazioni di copia rimosse dal PLC o da altro operatore.')

    def _gates(self, session, client, enabled):
        from snap7.type import Areas, WordLen
        for bit in (0, 1):
            target = True if enabled else bool(session.original_gates & (1 << bit))
            client.write_area(Areas.DB, 100, 135 * 8 + bit, bytearray([int(target)]), WordLen.Bit)
        actual = self._read(client, 100, 135, 1)[0] & 3
        if actual != (3 if enabled else session.original_gates & 3):
            raise RuntimeError('Abilitazioni di copia: rilettura non corrispondente.')

    def _send_confirm(self, session, client, value):
        now = time.monotonic()
        if session.stop.is_set() or now >= session.deadline:
            raise TimeoutError('Sessione arrestata o scaduta prima dell\'invio.')
        if session.last_sent and now - session.last_sent > self.max_send_gap:
            raise TimeoutError('Cadenza watchdog persa: vietato riattivare automaticamente il canale.')
        payload = bytearray(session.template)
        encoded = struct.pack('>f', value)
        payload[32:36] = encoded
        session.channel.send(bytes(payload))
        session.last_sent = time.monotonic()
        session.sent_count += 1
        # Source, copied value and actual FB input are three separate S7 reads.
        deadline = time.monotonic() + .6
        while True:
            source = self._read(client, 511, 32, 4)
            copied = self._read(client, 944, 32, 4)
            actual = self._read(client, 570, 2, 4)
            flags = self._read(client, 600, 24, 1)[0]
            processed = struct.unpack('>f', self._read(client, 570, 140, 4))[0]
            session.feedback = {'source_matches': source == encoded, 'copied': copied == encoded,
                'regulator_input_confirmed': actual == encoded, 'watchdog_healthy': not bool(flags & 0x12),
                'processed_raw': processed if math.isfinite(processed) else None}
            if all(session.feedback[k] for k in ('source_matches', 'copied', 'regulator_input_confirmed', 'watchdog_healthy')):
                session.value = value
                return
            if time.monotonic() >= deadline:
                raise RuntimeError('Invio nativo effettuato, ma catena sorgente/copia/ingresso o watchdog non confermati. Sessione interrotta; verificare il PLC.')
            time.sleep(.03)

    def start(self, device, value, *, bench):
        self._validate_device(device, value, bench)
        identity = self.identity(device)
        if not identity[0] or not 1 <= identity[1] <= 65535 or not 0 <= identity[2] <= 7 or not 0 <= identity[3] <= 31:
            raise ValueError('Endpoint S7 non valido.')
        with self._lock:
            old = self._sessions.get(identity)
            if old and old.state in ('starting', 'active', 'stopping'):
                raise ValueError('Endpoint gia posseduto da una sessione nativa: arrestarla prima di riavviare.')
            if old and old.cleanup_error:
                raise ValueError('Ripristino precedente non confermato: verificare i bit di copia nel PLC prima di una nuova sessione.')
            import snap7
            client = (self.client_factory or (lambda: snap7.client.Client(auto_reconnect=False)))()
            session = NativeSession(device, identity, client, None, b'', value, bench, 0, time.monotonic() + self.lease_seconds)
            self._sessions[identity] = session
        endpoint = sinvert_s7_service.endpoint_lock(*identity)
        gates_touched = False
        try:
            if not endpoint.acquire(timeout=2):
                raise TimeoutError('Endpoint S7 occupato.')
            try:
                client.connect(*identity[:1], identity[2], identity[3], tcp_port=identity[1])
                connection = getattr(client, 'connection', None)
                if connection is not None:
                    connection.timeout = .6
                    if getattr(connection, 'socket', None) is not None:
                        connection.socket.settimeout(.6)
                self._verify_program(client)
                session.last_program_check = time.monotonic()
                session.template = self._read(client, 511, 0, 64)
                copied = self._read(client, 944, 0, 64)
                if session.template[:32] + session.template[36:] != copied[:32] + copied[36:]:
                    raise ValueError('Campi diversi dal riferimento A non allineati fra DB511 e DB944.')
                session.original_gates = self._read(client, 100, 135, 1)[0]
                self._conditions(session, client, starting=True)
                self._audit(session, 'before_start', original_gates=session.original_gates)
                session.channel = self.channel_factory(identity[0], identity[1])
                if session.stop.is_set():
                    raise ValueError('Avvio annullato da una richiesta di arresto.')
                gates_touched = True
                self._gates(session, client, True)
                self._send_confirm(session, client, value)
                session.state = 'active'
                self._audit(session, 'started', feedback=session.feedback)
            finally:
                endpoint.release()
            session.thread = Thread(target=self._run, args=(session,), name='sinvert-native', daemon=True)
            session.thread.start()
            return self.status(device)
        except Exception as exc:
            session.error = str(exc)
            session.state = 'stopping'
            self._cleanup(session, restore_gates=gates_touched)
            session.state = 'fault'
            raise

    def update(self, device, client, value):
        """Caller holds endpoint lock; never reacquire it here."""
        session = self._get(device)
        if not session or session.device.device_id != device.device_id:
            raise ValueError('Avviare la sessione nativa del dispositivo prima di inviare il riferimento.')
        with session.lock:
            if session.state != 'active' or session.stop.is_set() or time.monotonic() >= session.deadline:
                raise ValueError('Sessione nativa non attiva o scaduta.')
            try:
                self._validate_device(device, value, session.bench)
                self._conditions(session, client)
                self._audit(session, 'before_reference', requested_raw=value)
                self._send_confirm(session, client, value)
                self._audit(session, 'reference_confirmed', feedback=session.feedback)
                return self.status(device)
            except Exception as exc:
                session.error = str(exc)
                session.stop.set()
                raise

    def submit_reference(self, device, value, *, dry_run=False):
        session = self._get(device)
        if not session or session.device.device_id != device.device_id:
            raise ValueError('Il dispositivo non possiede il canale nativo.')
        endpoint = sinvert_s7_service.endpoint_lock(*session.identity)
        if not endpoint.acquire(timeout=.5):
            raise TimeoutError('Endpoint occupato: riferimento non inviato.')
        try:
            if dry_run:
                with session.lock:
                    if session.state != 'active' or session.stop.is_set():
                        raise ValueError('Sessione nativa non attiva.')
                    self._validate_device(device, value, session.bench)
                    self._conditions(session, session.client)
                    return self.status(device)
            return self.update(device, session.client, value)
        finally:
            endpoint.release()

    def _run(self, session):
        endpoint = sinvert_s7_service.endpoint_lock(*session.identity)
        try:
            while not session.stop.wait(.05):
                now = time.monotonic()
                if now >= session.deadline:
                    raise TimeoutError('Sessione di collaudo scaduta (10 minuti). Nessun rinnovo automatico.')
                if now - session.last_sent > self.max_send_gap:
                    raise TimeoutError('Cadenza watchdog non rispettata: nessun riavvio automatico.')
                if now - session.last_sent < self.interval:
                    continue
                if not endpoint.acquire(timeout=.1):
                    continue
                try:
                    with session.lock:
                        if session.stop.is_set():
                            break
                        if self.device_getter:
                            device = self.device_getter(session.device.device_id)
                        else:
                            from app.services.device_service import device_service
                            device = device_service.get_device(session.device.device_id)
                        if not device or self.identity(device) != session.identity:
                            raise ValueError('Dispositivo eliminato o endpoint cambiato.')
                        self._validate_device(device, session.value, session.bench)
                        if now - session.last_program_check > 15:
                            self._verify_program(session.client)
                            session.last_program_check = time.monotonic()
                        self._conditions(session, session.client)
                        self._send_confirm(session, session.client, session.value)
                finally:
                    endpoint.release()
        except Exception as exc:
            session.error = str(exc)
        finally:
            session.stop.set()
            session.state = 'stopping'
            self._cleanup(session)
            session.state = 'fault' if session.error or session.cleanup_error else 'stopped'

    def _cleanup(self, session, *, restore_gates=True):
        if session.channel:
            try:
                session.channel.close()
            except Exception:
                pass
        # Do not replay an old reference on stop. PLC watchdog/fallback owns loss
        # of transport; restore only copy-enable bits this session took over.
        if restore_gates:
            endpoint = sinvert_s7_service.endpoint_lock(*session.identity)
            acquired = endpoint.acquire(timeout=2)
            try:
                if not acquired:
                    raise TimeoutError('Endpoint occupato durante il ripristino delle copie.')
                self._gates(session, session.client, False)
            except Exception as exc:
                session.cleanup_error = str(exc)
            finally:
                if acquired:
                    endpoint.release()
        try:
            session.client.disconnect()
        except Exception:
            pass
        try:
            self._audit(session, 'stopped', error=session.error, cleanup_error=session.cleanup_error)
        except Exception as exc:
            session.cleanup_error = str(exc)

    def stop(self, device):
        session = self._get(device)
        if session:
            session.stop.set()
            if session.thread:
                session.thread.join(timeout=4)
            if session.state in ('starting', 'active', 'stopping'):
                raise RuntimeError('Arresto nativo non ancora confermato: verificare lo stato prima di proseguire.')
        return self.status(device)

    def stop_all(self):
        with self._lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            self.stop(session.device)


sinvert_native_service = SinvertNativeService()
