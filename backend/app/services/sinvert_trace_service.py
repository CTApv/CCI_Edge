"""Bounded persistent polling trace; recording never performs PLC operations."""
import io
import csv
import json
import zipfile
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
import logging
from threading import Lock


class SinvertTraceService:
    def __init__(self, directory=None):
        self.directory = directory
        self._lock = Lock()
        self._handler = None

    def _root(self):
        from app.config import settings
        return self.directory or settings.database_path.parent

    def append(self, device, entry):
        if device.brand != 'SINVERT' or device.protocol != 's7_tcp':
            return
        row = {'utc': datetime.now(timezone.utc).isoformat(), 'kind': 'poll',
               'device_id': device.device_id, 'host': device.connection_settings.get('host'),
               'sample_timestamp': entry.timestamp,
               'diagnostics': entry.diagnostics.model_dump(mode='json'),
               'telemetry': [p.model_dump(mode='json') for p in entry.telemetry]}
        with self._lock:
            if self._handler is None:
                self._root().mkdir(parents=True, exist_ok=True)
                self._handler = RotatingFileHandler(self._root()/'sinvert_samples.jsonl',
                    maxBytes=10*1024*1024, backupCount=3, encoding='utf8')
            record = logging.LogRecord('sinvert_trace', logging.INFO, '', 0,
                json.dumps(row, ensure_ascii=False, allow_nan=False), (), None)
            self._handler.emit(record)

    def export(self, device_id):
        """Only selected device rows; no credentials or complete DB exports."""
        result = io.BytesIO()
        with self._lock, zipfile.ZipFile(result, 'w', zipfile.ZIP_DEFLATED) as z:
            for path in sorted(self._root().glob('sinvert_samples.jsonl*')) + [self._root()/'sinvert_command_audit.jsonl']:
                if not path.is_file():
                    continue
                # Audit has its own historical file; cap retrieval and retain full file on disk.
                with path.open('rb') as f:
                    length = path.stat().st_size
                    offset = max(0, length-20*1024*1024)
                    f.seek(offset)
                    if offset: f.readline()
                    lines = []
                    for line in f:
                        try:
                            if json.loads(line).get('device_id') == device_id:
                                lines.append(line)
                        except (ValueError, UnicodeDecodeError):
                            continue
                z.writestr(path.name, b''.join(lines))
            with z.open('telemetry.csv', 'w') as binary:
                with io.TextIOWrapper(binary, encoding='utf-8-sig', newline='') as text:
                    writer = csv.writer(text)
                    writer.writerow(['utc', 'sample_timestamp', 'key', 'raw_value', 'value', 'quality'])
                    for path in sorted(self._root().glob('sinvert_samples.jsonl*')):
                        with path.open(encoding='utf8') as f:
                            for line in f:
                                try:
                                    row = json.loads(line)
                                    if row.get('device_id') != device_id: continue
                                    for point in row.get('telemetry', []):
                                        writer.writerow([row.get('utc'), row.get('sample_timestamp'),
                                            point.get('key'), point.get('raw_value'), point.get('value'), point.get('quality')])
                                except ValueError:
                                    continue
            z.writestr('manifest.json', json.dumps({'device_id': device_id,
                'export_utc': datetime.now(timezone.utc).isoformat(),
                'poll_trace_retention': '4 files, 10 MiB each; oldest samples rotate',
                'audit_export_tail_bytes': 20*1024*1024,
                'physical_execution_confirmed': False}))
        return result.getvalue()

    def close(self):
        with self._lock:
            if self._handler is not None:
                self._handler.close()
                self._handler = None


sinvert_trace_service = SinvertTraceService()
