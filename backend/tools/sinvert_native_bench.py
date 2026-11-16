"""Explicit finite native-channel commissioning probe; never run on app startup."""

def main():
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Finite SINVERT ISO-on-TCP watchdog test on the confirmed CPU+CP bench.")
    parser.add_argument("--cpu-cp-only", action="store_true", help="Confirm that no inverter or peripheral is connected.")
    parser.add_argument("--output-dir", type=Path, default=Path.cwd() / "sinvert-native-probe-results")
    args = parser.parse_args()
    if not args.cpu_cp_only:
        parser.error("This finite write test requires --cpu-cp-only on the isolated CPU+CP bench.")
    if not __debug__:
        parser.error("Optimized Python is not supported: probe verification guards must remain enabled.")
    from datetime import datetime, timezone
    from pathlib import Path
    import json
    import math
    import select
    import socket
    import struct
    import time

    import snap7
    from snap7.type import Areas, Block, WordLen

    base = Path(__file__).resolve().parent
    out = args.output_dir / ('native_watchdog_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    out.mkdir(parents=True)
    j = {'scope': 'operator-authorized CPU+CP-only bench', 'writes': [], 'frames': [], 'samples': [], 'restoration': {}}
    c = snap7.client.Client()
    sock = None
    backup = {}
    changed = False

    def save():
        (out / 'journal.json').write_text(json.dumps(j, indent=2), encoding='utf8')

    def read(db, offset, size):
        return bytes(c.db_read(db, offset, size))

    def guard():
        assert bytes(c.read_area(Areas.MK, 0, 55, 1)) == bytes(1), 'M55 changed'
        assert bytes(c.read_area(Areas.MK, 0, 102, 4)) == bytes(4), 'Output requests changed'

    def exact(n):
        result = b''
        while len(result) < n:
            part = sock.recv(n - len(result))
            if not part:
                raise EOFError('Native peer closed connection')
            result += part
        return result

    def receive():
        header = exact(4)
        assert header[:2] == b'\x03\0', 'Invalid TPKT header'
        size = int.from_bytes(header[2:], 'big')
        assert 7 <= size <= 65535, 'Invalid TPKT size'
        return exact(size - 4)

    def send(payload, phase):
        # Class 0 data TPDU, EOT=1; one complete 64-byte telegram per TSDU.
        assert len(payload) == 64
        packet = b'\x03\0' + struct.pack('>H', len(payload) + 7) + b'\x02\xf0\x80' + payload
        row = {'utc': datetime.now(timezone.utc).isoformat(), 'phase': phase, 'payload': payload.hex()}
        j['frames'].append(row)
        save()  # Record intent before a send whose outcome could be uncertain.
        sock.sendall(packet)
        row['send_returned'] = True

    def gate(bit, value, cleanup=False):
        nonlocal changed
        if not cleanup:
            guard()
        changed = True
        row = {'db': 100, 'byte': 135, 'bit': bit, 'value': value, 'cleanup': cleanup}
        j['writes'].append(row)
        save()
        c.write_area(Areas.DB, 100, 135 * 8 + bit, bytearray([int(value)]), WordLen.Bit)
        row['readback'] = bool(read(100, 135, 1)[0] & (1 << bit))

    def sample(phase, elapsed):
        guard()
        flags = read(600, 24, 6)
        regulator = read(570, 0, 148)
        row = {
            'phase': phase, 'elapsed_s': round(elapsed, 3),
            'source': struct.unpack('>f', read(511, 32, 4))[0],
            'copy': struct.unpack('>f', read(944, 32, 4))[0],
            'input': struct.unpack('>f', regulator[2:6])[0],
            'processed': struct.unpack('>f', regulator[140:144])[0],
            'watchdog_failed': bool(flags[0] & 16), 'new_data': bool(flags[0] & 1),
            'receive_error': bool(flags[0] & 2), 'receive_status': flags[2:4].hex(),
            'regulator_communication_input': bool(regulator[0] & 1),
            'remote': bool(regulator[24] & 32),
        }
        j['samples'].append(row)
        save()
        return row

    def drain():
        # AG_SEND may share ID 1; consume application responses without interpreting
        # or executing their contents. Discard only within this temporary client.
        while select.select([sock], [], [], 0)[0]:
            body = receive()
            j.setdefault('received_frames', []).append(body.hex())

    try:
        for attempt in range(3):
            try:
                c.connect('192.168.0.245', 0, 2)
                j['state'] = c.get_cpu_state()
                break
            except Exception as exc:
                j.setdefault('preparation_read_errors', []).append(str(exc))
                c.disconnect()
                if attempt == 2:
                    raise
        assert j['state'] == 'S7CpuStatusRun'
        j['serial'] = c.get_cpu_info().SerialNumber.decode().strip('\0 ')
        assert j['serial'] == 'S C-FODC12442015'
        reference_path = base.parent / 'app/catalog/sinvert_s7_command_reference.json'
        if not reference_path.exists():
            reference_path = base / 'sinvert_s7_command_reference.json'
        reference = json.loads(reference_path.read_text())
        for name, expected in reference['blocks'].items():
            kind = Block.FB if name.startswith('FB') else Block.FC if name.startswith('FC') else Block.OB
            info = c.get_block_info(kind, int(name[2:]))
            assert all(int(getattr(info, key)) == value for key, value in expected.items()), name
        guard()
        spans = [(511, 0, 64), (944, 0, 64), (100, 135, 1), (402, 0, 14),
                 (402, 842, 2), (402, 1036, 2), (402, 1230, 2), (402, 1424, 2)]
        for span in spans:
            backup[span] = read(*span)
        telegram = backup[(511, 0, 64)]
        assert telegram[:2] == bytes(2), 'Pending global commands'
        assert telegram[14:32] == bytes(18), 'Pending unit commands or unknown data'
        assert telegram[40:] == bytes(24), 'Unknown trailing data'
        assert telegram[10:14] == bytes(4), 'Other numeric command active'
        assert backup[(100, 135, 1)][0] & 3 == 0, 'Copy gates already active'
        assert read(511, 36, 28) == read(944, 36, 28), 'Other copied fields differ'
        original = struct.unpack('>f', telegram[32:36])[0]
        assert math.isfinite(original) and 0 <= original <= 999998
        j['backup'] = {f'{n}:{o}:{length}': value.hex() for (n, o, length), value in backup.items()}
        save()
        for _ in range(3):
            time.sleep(.2)
            assert read(511, 0, 64) == telegram, 'Concurrent source writer detected'

        sock = socket.create_connection(('192.168.0.245', 102), 3)
        sock.settimeout(3)
        src, dst = b'PVGUARDIAN', b'SINVERT'
        body = b'\xe0\0\0\0\x01\0' + bytes([0xc1, len(src)]) + src + bytes([0xc2, len(dst)]) + dst + b'\xc0\x01\x0a'
        cr = bytes([len(body)]) + body
        sock.sendall(b'\x03\0' + struct.pack('>H', len(cr) + 4) + cr)
        cc = receive()
        assert cc[1] == 0xd0 and cc[2:4] == b'\0\x01', 'Native connection not accepted'
        j['connection_confirm'] = cc.hex()
        gate(0, True)
        gate(1, True)
        start = time.monotonic()
        next_frame = 0.0
        print('Native channel connected, copy enabled; bounded 9-second transmission.', flush=True)
        while (elapsed := time.monotonic() - start) < 9:
            if elapsed >= next_frame:
                value = original + 1 if elapsed < 3 else original + 2 if elapsed < 6 else original
                payload = bytearray(telegram)
                payload[32:36] = struct.pack('>f', value)
                send(payload, 'active')
                next_frame += .8
            drain()
            sample('active', elapsed)
            time.sleep(.12)
        send(telegram, 'restore_source_through_native_channel')
        loss_start = time.monotonic()
        print('Transmission stopped; observing watchdog for 8 seconds.', flush=True)
        while (elapsed := time.monotonic() - loss_start) < 8:
            drain()
            sample('silence', elapsed)
            time.sleep(.12)
        active = [s for s in j['samples'] if s['phase'] == 'active' and s['elapsed_s'] > 2]
        silent = [s for s in j['samples'] if s['phase'] == 'silence' and s['elapsed_s'] > 6]
        j['native_reference_variation_confirmed'] = all(any(s['source'] == value and s['copy'] == value and s['input'] == value for s in active) for value in [original + 1, original + 2, original])
        j['watchdog_healthy_during_transmission'] = bool(active) and all(not s['watchdog_failed'] for s in active)
        j['watchdog_failed_after_silence'] = bool(silent) and all(s['watchdog_failed'] for s in silent)
    except Exception as exc:
        j['error'] = str(exc)
    finally:
        if sock:
            sock.close()
        if changed:
            try:
                gate(0, False, True)
                gate(1, False, True)
                # Once reception is no longer called, restore only saved command/
                # copied buffer spans. Runtime watchdog flags are not overwritten.
                for n, offset, length in [s for s in backup if s != (100, 135, 1)]:
                    data = backup[(n, offset, length)]
                    j['writes'].append({'db': n, 'offset': offset, 'hex': data.hex(), 'cleanup': True})
                    save()
                    c.db_write(n, offset, bytearray(data))
                for bit in (0, 1):
                    gate(bit, bool(backup[(100, 135, 1)][0] & (1 << bit)), True)
                for span, data in backup.items():
                    j['restoration'][':'.join(map(str, span))] = read(*span) == data
                j['restored'] = all(j['restoration'].values())
            except Exception as exc:
                j['restore_error'] = str(exc)
        c.disconnect()
        save()
    print(json.dumps({k: v for k, v in j.items() if k not in ['backup', 'writes', 'frames', 'samples', 'received_frames']}, indent=2), flush=True)
    print(out, flush=True)
    if j.get('error') or j.get('restore_error') or not all(j.get(key, False) for key in [
        'native_reference_variation_confirmed', 'watchdog_healthy_during_transmission',
        'watchdog_failed_after_silence', 'restored',
    ]):
        raise SystemExit(1)

if __name__ == "__main__":
    main()
