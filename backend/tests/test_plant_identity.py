import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError
from app.services.plant_identity_service import PlantIdentityService
from app.services.system_identity_service import SystemIdentityService
from app.api import routes_system
from app.schemas.system_schemas import PlantIdentityUpdateRequest


class PlantIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'plant_identity.json'
        self.service = PlantIdentityService(self.path)
        self.edge = 'PV10D657D3B89E'
    def test_persistence_restart_rename_and_clear(self):
        self.assertEqual(self.service.get(self.edge),{})
        self.service.update(self.edge,'  Campo Fotovoltaico Nord  ',1)
        restarted=PlantIdentityService(self.path)
        self.assertEqual(restarted.get(self.edge)['plant_name'],'Campo Fotovoltaico Nord')
        restarted.update(self.edge,'Impianto Sud',2)
        self.assertEqual(self.service.get(self.edge)['plant_name'],'Impianto Sud')
        self.service.update(self.edge,'',3)
        self.assertIsNone(restarted.get(self.edge)['plant_name'])
    def test_stale_updates_idempotency_and_foreign_edge(self):
        first=self.service.update(self.edge,'Nome attuale',4)
        self.assertEqual(first,self.service.update(self.edge,'Nome attuale',4))
        for rev in [3,4]:
            with self.assertRaises(ValueError):self.service.update(self.edge,'Vecchio nome',rev)
        self.assertEqual(self.service.get('OTHER'),{})
    def test_atomic_failure_preserves_last_name(self):
        self.service.update(self.edge,'Confermato',1)
        with patch('app.services.plant_identity_service.os.replace',side_effect=OSError('disk error')):
            with self.assertRaises(OSError):self.service.update(self.edge,'Non salvato',2)
        self.assertEqual(self.service.get(self.edge)['plant_name'],'Confermato')
        self.assertEqual(list(self.path.parent.glob('*.tmp')),[])
    def test_validation_corrupt_file_and_empty_name(self):
        for value in ['a'*201,'Nome\nAlterato','A\x00B']:
            with self.assertRaises(ValueError):self.service.update(self.edge,value)
        self.path.write_text('not json',encoding='utf-8')
        self.assertEqual(self.service.get(self.edge),{})
        with self.assertRaises(ValidationError):PlantIdentityUpdateRequest(edge_id=self.edge,plant_name='a'*201)
        with self.assertRaises(ValidationError):PlantIdentityUpdateRequest(edge_id=self.edge,plant_name='X',hostname='Y')
    def test_health_name_changes_without_identity_cache_or_restart(self):
        identity=SystemIdentityService()
        identity._cached_identity={'edge_id':self.edge,'hostname':'docker-id'}
        with patch('app.services.system_identity_service.plant_identity_service',self.service):
            self.assertIsNone(identity.get_snapshot()['plant_name'])
            self.service.update(self.edge,'Nuovo impianto',1)
            current=identity.get_snapshot()
        self.assertEqual(current['plant_name'],'Nuovo impianto')
        self.assertEqual(current['hostname'],'docker-id')
        self.assertEqual(current['edge_id'],self.edge)
    def test_endpoint_rejects_wrong_device_and_storage_errors(self):
        identity=Mock();identity.get_snapshot.return_value={'edge_id':self.edge}
        with patch.object(routes_system,'plant_identity_service',self.service),patch.object(routes_system,'system_identity_service',identity):
            with self.assertRaises(HTTPException) as exc:
                routes_system.update_plant_identity(PlantIdentityUpdateRequest(edge_id='OTHER',plant_name='Wrong'))
            self.assertEqual(exc.exception.status_code,409)
            self.assertFalse(self.path.exists())
            result=routes_system.update_plant_identity(PlantIdentityUpdateRequest(edge_id=self.edge,plant_name='Impianto',revision=1))
            self.assertEqual(result['plant_name'],'Impianto')
            with patch.object(self.service,'update',side_effect=OSError('disk')):
                with self.assertRaises(HTTPException) as exc:
                    routes_system.update_plant_identity(PlantIdentityUpdateRequest(edge_id=self.edge,plant_name='X'))
                self.assertEqual(exc.exception.status_code,503)

    def test_control_room_contract_commission_rename_offline_retry_and_stock(self):
        # Run the distributed Control Room helper against the actual edge route.
        class RequestException(Exception):pass
        requests=SimpleNamespace(put=Mock(),RequestException=RequestException)
        source=Path(__file__).resolve().parents[2]/'deployment/control-room/plant_identity_sync.py'
        spec=importlib.util.spec_from_file_location('plant_sync_under_test',source)
        helper=importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules',{'requests':requests}):spec.loader.exec_module(helper)
        identity={'edge_id':self.edge,'plant_name':None}
        edge_identity=Mock();edge_identity.get_snapshot.return_value={'edge_id':self.edge}
        def put(url,**kwargs):
            self.assertEqual(url,'http://edge/api/system/plant-identity')
            self.assertFalse(kwargs['allow_redirects'])
            routes_system.update_plant_identity(PlantIdentityUpdateRequest(**kwargs['json']))
            return SimpleNamespace(status_code=200)
        requests.put.side_effect=put
        metadata={'custom_name':'Campo Nord','lifecycle_state':'commissioned','revision':1}
        with patch.object(routes_system,'system_identity_service',edge_identity),patch.object(routes_system,'plant_identity_service',self.service):
            self.assertTrue(helper.sync_plant_identity('http://edge',identity,{},metadata))
            identity['plant_name']='Campo Nord'
            self.assertFalse(helper.sync_plant_identity('http://edge',identity,{},metadata))
            metadata.update(custom_name='Campo Sud',revision=2)
            requests.put.side_effect=RequestException('offline')
            with self.assertRaises(RequestException):helper.sync_plant_identity('http://edge',identity,{},metadata)
            self.assertEqual(self.service.get(self.edge)['plant_name'],'Campo Nord')
            requests.put.side_effect=put
            self.assertTrue(helper.sync_plant_identity('http://edge',identity,{},metadata))
            self.assertEqual(self.service.get(self.edge)['plant_name'],'Campo Sud')
            identity['plant_name']='Campo Sud'
            self.assertTrue(helper.sync_plant_identity('http://edge',identity,{},dict(metadata,lifecycle_state='pending',ever_commissioned=True,revision=3)))
            self.assertIsNone(self.service.get(self.edge)['plant_name'])
        self.assertFalse(helper.sync_plant_identity('http://old',{'edge_id':self.edge},{},metadata))
        self.assertFalse(helper.sync_plant_identity('http://edge',identity,{},{}))


if __name__=='__main__':unittest.main()
