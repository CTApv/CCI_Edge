"""Persistent Control Room plant label, independent from Docker hostname."""
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from app.config import settings


class PlantIdentityService:
    def __init__(self, path=None):
        self._path = Path(path) if path else None
        self._lock = RLock()

    @property
    def path(self):
        return self._path or settings.database_path.with_name('plant_identity.json')

    def get(self, edge_id):
        with self._lock:
            try:
                data = json.loads(self.path.read_text(encoding='utf-8'))
                if not isinstance(data, dict) or data.get('edge_id') != edge_id:
                    return {}
                name = data.get('plant_name')
                if name is not None and (not isinstance(name, str) or len(name) > 200):
                    return {}
                return data
            except (OSError, ValueError):
                return {}

    def update(self, edge_id, plant_name, revision=None):
        name = plant_name.strip() or None
        if name and (len(name) > 200 or any(ord(c) < 32 for c in name)):
            raise ValueError('Nome impianto non valido: massimo 200 caratteri, senza caratteri di controllo.')
        with self._lock:
            before = self.get(edge_id)
            previous_revision = before.get('revision')
            if revision is not None and previous_revision is not None:
                if revision < previous_revision or (revision == previous_revision and name != before.get('plant_name')):
                    raise ValueError('Configurazione impianto superata da una revisione più recente.')
            if before and name == before.get('plant_name') and revision == previous_revision:
                return before
            data = {'edge_id': edge_id, 'plant_name': name, 'revision': revision,
                    'updated_at': datetime.now(UTC).isoformat(), 'source': 'control_room'}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                                  prefix='.plant-', suffix='.tmp', delete=False) as f:
                    tmp = f.name
                    json.dump(data, f, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self.path)
            finally:
                if tmp and os.path.exists(tmp):
                    os.unlink(tmp)
            return data


plant_identity_service = PlantIdentityService()
