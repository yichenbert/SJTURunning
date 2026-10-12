import copy
import json
import unittest
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs
from src.coordinates import service_payload, wgs84_to_gcj02
from src.api_client import upload_running_data, get_authorization_token_and_rules
from src.data_generator import generate_running_data_payload
from src.route import route_distance

ROUTE=[{'latitude':31.0285,'longitude':121.4445},{'latitude':31.029,'longitude':121.448}]
SETTINGS={'使用自定义路线':True,'自定义路线':ROUTE,'配速_分钟每公里':5,'GPS采样间隔_秒':3}

class CoordinateBoundaryTests(unittest.TestCase):
    def config(self):
        return {'APP_CONFIG':SETTINGS,'USER_ID':'offline','HOST':'test.invalid','START_LATITUDE':ROUTE[0]['latitude'],
                'START_LONGITUDE':ROUTE[0]['longitude'],'UID_URL':'https://test.invalid/uid','MY_DATA_URL':'https://test.invalid/my',
                'POINT_RULE_URL':'https://test.invalid/rule','UPLOAD_URL':'https://test.invalid/upload','START_TIME_EPOCH_MS':0}

    def payload(self):
        return generate_running_data_payload(self.config(),[],{},log_cb=lambda *a:None)

    def test_upload_converts_both_coordinate_fields_once_without_mutating_route_or_payload(self):
        original,distance,duration=self.payload();before=copy.deepcopy(original)
        with patch('src.api_client.make_request',return_value={'code':0}) as request:
            upload_running_data(self.config(),'test-token',original)
        sent=json.loads(request.call_args.kwargs['data'])
        first=sent[0]['tracks'][0]['points'][0]
        lat,lon=wgs84_to_gcj02(**ROUTE[0])
        self.assertEqual(first['latLng'],{'latitude':round(lat,7),'longitude':round(lon,7)})
        self.assertEqual(first['location'],f'{lon:.7f},{lat:.7f}')
        self.assertEqual(original,before)
        self.assertEqual(service_payload(self.config(),original),sent)
        self.assertAlmostEqual(distance,route_distance(ROUTE),delta=.1)
        self.assertEqual(sent[0]['tracks'][0]['distance'],original[0]['tracks'][0]['distance'])
        self.assertEqual(sent[0]['tracks'][0]['points'][0]['locatetime'],original[0]['tracks'][0]['points'][0]['locatetime'])

    def test_rendering_on_amap_returns_same_physical_route_as_free_map(self):
        from src.coordinates import from_amap
        payload,_,_=self.payload();converted=service_payload(self.config(),payload)
        points=[p['latLng'] for p in converted[0]['tracks'][0]['points']]
        restored=from_amap([[p['longitude'],p['latitude']] for p in points])
        self.assertAlmostEqual(restored[0]['latitude'],ROUTE[0]['latitude'],places=6)
        self.assertAlmostEqual(restored[0]['longitude'],ROUTE[0]['longitude'],places=6)

    def test_rule_lookup_location_matches_upload_coordinate_system(self):
        responses=[{'code':0,'data':{'uid':'test-token'}},{},{'data':{'rules':{}}}]
        with patch('src.api_client.make_request',side_effect=responses) as request:
            get_authorization_token_and_rules(self.config())
        call=request.call_args_list[-1]
        location=parse_qs(urlparse(call.args[1]).query)['location'][0]
        lat,lon=wgs84_to_gcj02(**ROUTE[0])
        self.assertEqual(location,f'{lon:.14f},{lat:.14f}')
        self.assertIn('location=',call.args[2]['referer'])

    def test_legacy_non_map_payload_remains_unchanged(self):
        payload,_,_=self.payload()
        self.assertEqual(service_payload({'APP_CONFIG':{'使用自定义路线':False}},payload),payload)
