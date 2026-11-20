"""Copy to Control Room backend/app/services; called by its existing collector.

The authenticated Control Room metadata is authoritative. No admin tokens are
sent to the edge. Edge transport uses the same trusted tailnet API as health.
"""
import requests


def sync_plant_identity(base_url, identity, device, metadata, *, timeout=4):
    # Presence advertises edge support; old releases must not receive new writes.
    if 'plant_name' not in identity or not identity.get('edge_id'):
        return False
    if metadata.get('lifecycle_state') == 'commissioned':
        desired = str(metadata.get('custom_name') or '').strip()
        revision = int(metadata.get('revision') or 0)
    elif metadata.get('ever_commissioned'):
        desired, revision = '', int(metadata.get('revision') or 0)
    else:
        desired, revision = str(device.get('plant_name') or '').strip(), None
        if not desired:
            return False
    if desired == str(identity.get('plant_name') or '').strip():
        return False
    response = requests.put(base_url + '/api/system/plant-identity',
        json={'edge_id': identity['edge_id'], 'plant_name': desired, 'revision': revision},
        timeout=timeout, allow_redirects=False)
    if response.status_code not in (200, 204):
        response.raise_for_status()
        raise requests.RequestException('Il dispositivo non ha confermato il nome impianto.')
    return True
