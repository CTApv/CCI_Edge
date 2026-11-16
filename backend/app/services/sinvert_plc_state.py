"""Real CPU operating state via SZL 0x0424, index 0.

python-snap7 3.3.1 get_cpu_state() builds a placeholder READ request and its
extractor unconditionally returns RUN. Do not use it for a write interlock.
The pinned client's read_szl Data contains the four-byte SZL record header;
operating mode is byte 7, as in native Snap7 opGetPlcStatus.
https://github.com/SCADACS/snap7/blob/master/src/core/s7_micro_client.cpp
"""
def cpu_state(client):
    szl = client.read_szl(0x0424, 0)
    size = int(szl.Header.LengthDR)
    raw = bytes(szl.Data[:size])
    if size < 8 or len(raw) != size:
        raise ValueError('Stato CPU: risposta SZL 0424 incompleta.')
    record_size = int.from_bytes(raw[:2], 'big')
    record_count = int.from_bytes(raw[2:4], 'big')
    if record_size < 4 or record_count < 1 or 4 + record_size * record_count != size:
        raise ValueError('Stato CPU: struttura SZL 0424 non valida.')
    return 'S7CpuStatusRun' if raw[7] == 8 else 'S7CpuStatusUnknown' if raw[7] == 0 else 'S7CpuStatusStop'


def require_cpu_run(client):
    if cpu_state(client) != 'S7CpuStatusRun':
        raise ValueError('CPU non in RUN (SZL 0424): nessuna trasmissione autorizzata.')
