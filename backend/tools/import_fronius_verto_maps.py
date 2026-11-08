"""Rebuild the checked-in factual map from the official Fronius ZIP.

Developer tool only: pip install openpyxl, then pass the downloaded ZIP path.
No network request, runtime dependency or extraction of arbitrary ZIP paths.
"""
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile

import openpyxl


def convert(archive: Path):
    raw = archive.read_bytes()
    maps = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as files:
        for name in files.namelist():
            if not name.startswith('Verto_') or not name.endswith('_ROW.xlsx'):
                continue
            variant = 'plus' if 'storage' in name else '4mppt' if '4MPPT' in name else '3mppt'
            fmt = 'float' if '_Float_' in name else 'int_sf'
            content = files.read(name)
            workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            models = {}
            for sheet in workbook:
                match = re.search(r'\((\d+)\)',sheet.title)
                if not match:
                    continue
                fields = {}
                rows = list(sheet.values)
                for row in rows:
                    if not isinstance(row[0],int):
                        continue
                    fields[row[5]] = {'offset':row[0]-1, 'length':row[2], 'type':row[7],
                        'unit':row[8] or '', 'sf':row[9], 'supported':'not supported' not in str(row[10]).lower()}
                models[match[1]] = {'length':int(rows[2][10]), 'fields':fields}
            maps[f'{variant}_{fmt}'] = {'file':name, 'sha256':hashlib.sha256(content).hexdigest(), 'models':models}
        version = files.read('_INFO.TXT').decode().strip().removeprefix('Version ')
    if len(maps) != 6:
        raise ValueError('Expected six Verto ROW workbooks; review the archive before updating.')
    return {'source':'https://www.fronius.com/QR-link/0024', 'version':version,
            'archive_sha256':hashlib.sha256(raw).hexdigest(), 'maps':maps}


if __name__ == '__main__':
    output = Path(__file__).resolve().parents[1]/'app/catalog/fronius_sunspec_maps.json'
    output.write_text(json.dumps(convert(Path(sys.argv[1])),indent=2),encoding='utf8')
    print(output)
