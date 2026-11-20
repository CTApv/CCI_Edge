import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import requests
from app.services.plant_identity_sync import sync_plant_identity
from app.services.fleet_inventory import FleetCollector

class PlantSyncTests(unittest.TestCase):
    @patch('app.services.plant_identity_sync.requests.put')
    def test_new_edge_commissioned_name_rename_and_no_repeat(self,put):
        put.return_value.status_code=200
        identity={'edge_id':'PV123','plant_name':None}
        metadata={'lifecycle_state':'commissioned','custom_name':'Campo Nord','revision':2}
        self.assertTrue(sync_plant_identity('http://edge',identity,{},metadata))
        self.assertEqual(put.call_args.kwargs['json'],{'edge_id':'PV123','plant_name':'Campo Nord','revision':2})
        identity['plant_name']='Campo Nord';put.reset_mock()
        self.assertFalse(sync_plant_identity('http://edge',identity,{},metadata));put.assert_not_called()
    @patch('app.services.plant_identity_sync.requests.put')
    def test_old_edges_unconfigured_and_returned_stock(self,put):
        put.return_value.status_code=200
        self.assertFalse(sync_plant_identity('http://edge',{'edge_id':'PV123'},{},{}))
        identity={'edge_id':'PV123','plant_name':'Campo'}
        self.assertFalse(sync_plant_identity('http://edge',identity,{},{}))
        self.assertTrue(sync_plant_identity('http://edge',identity,{},dict(ever_commissioned=True,lifecycle_state='pending',revision=8)))
        self.assertEqual(put.call_args.kwargs['json']['plant_name'],'')
    @patch('app.services.plant_identity_sync.requests.put')
    def test_failures_are_retryable(self,put):
        identity={'edge_id':'PV123','plant_name':None};meta={'lifecycle_state':'commissioned','custom_name':'Campo','revision':1}
        put.side_effect=requests.Timeout('offline')
        with self.assertRaises(requests.Timeout):sync_plant_identity('http://edge',identity,{},meta)
        put.side_effect=None;put.return_value.status_code=200
        self.assertTrue(sync_plant_identity('http://edge',identity,{},meta))
    @patch('app.services.fleet_inventory.sync_plant_identity',side_effect=requests.Timeout('offline'))
    @patch('app.services.fleet_inventory.DeviceMetadataStore')
    @patch('app.services.fleet_inventory.requests.get')
    def test_optional_sync_failure_does_not_break_telemetry(self,get,metadata,sync):
        health=Mock();health.json.return_value={'identity':{'edge_id':'PV123','plant_name':None},'status_counts':{'total':1,'online':1}}
        power=Mock();power.json.return_value={'active_power_kw':12}
        get.side_effect=[health,power]
        with tempfile.TemporaryDirectory() as root:
            collector=FleetCollector(SimpleNamespace(fleet_request_timeout_seconds=2),SimpleNamespace(path=Path(root)/'inventory.json'))
            result=collector._collect_device({'id':'device','tailscale_ip':'100.64.0.1'})
        self.assertEqual(result['status'],'online');self.assertEqual(result['active_power_kw'],12)
        sync.assert_called_once()

if __name__=='__main__':unittest.main()
