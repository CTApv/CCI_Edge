"""Explicit, short-lived CPU-only bench declaration. Never alters PLC consents."""
from threading import Lock
from time import monotonic


class SinvertBenchService:
    def __init__(self):
        self._lock = Lock()
        self._sessions = {}

    @staticmethod
    def _identity(device):
        s = device.connection_settings
        return (device.device_id, s.get('host'), s.get('port', 102), s.get('rack', 0), s.get('slot', 2))

    def set_enabled(self, device, enabled):
        with self._lock:
            key = self._identity(device)
            if enabled:
                self._sessions[key] = monotonic() + 600
            else:
                self._sessions.pop(key, None)
        return self.status(device)

    def status(self, device):
        with self._lock:
            remaining = max(0, self._sessions.get(self._identity(device), 0) - monotonic())
        return {'active': remaining > 0, 'remaining_seconds': int(remaining),
                'scope': 'cpu_only', 'plc_consents_modified': False}


sinvert_bench_service = SinvertBenchService()
