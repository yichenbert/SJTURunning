import math
import unittest
from unittest.mock import patch

from src.route import normalize_route, route_distance, sample_route, validate_route
from src.data_generator import generate_running_data_payload, split_track_into_segments
from src.route_editor import project, unproject
from utils.auxiliary_util import SportsUploaderError

ROUTE = [{'latitude': 31.028, 'longitude': 121.44},
         {'latitude': 31.029, 'longitude': 121.44},
         {'latitude': 31.029, 'longitude': 121.443}]


class RouteTests(unittest.TestCase):
    def test_map_projection_round_trip(self):
        for point in ROUTE:
            for zoom in (3, 16, 19):
                result = unproject(project(point['latitude'], point['longitude'], zoom), zoom)
                self.assertAlmostEqual(result['latitude'], point['latitude'], places=10)
                self.assertAlmostEqual(result['longitude'], point['longitude'], places=10)

    def test_duplicate_points_removed_but_closed_route_retained(self):
        points = normalize_route([ROUTE[0], ROUTE[0], ROUTE[1], ROUTE[0]])
        self.assertEqual(len(points), 3)
        self.assertEqual(points[0], points[-1])

    def test_invalid_routes_rejected(self):
        for route in ([], [ROUTE[0]], [{'latitude': math.nan, 'longitude': 121}],
                      [{'latitude': 31, 'longitude': 200}], [ROUTE[0]] * 5001):
            with self.subTest(route_size=len(route)), self.assertRaises(SportsUploaderError):
                validate_route(route)

    def test_sampling_preserves_turns_endpoints_and_pace(self):
        points, distance, duration = sample_route(ROUTE, 5, 3, 123456000)
        self.assertEqual(points[0]['latLng'], ROUTE[0])
        self.assertEqual(points[-1]['latLng'], ROUTE[-1])
        self.assertIn(ROUTE[1], [point['latLng'] for point in points])
        self.assertTrue(all(a['locatetime'] <= b['locatetime'] for a, b in zip(points, points[1:])))
        self.assertAlmostEqual(duration, distance * 0.3, places=8)
        self.assertAlmostEqual((points[-1]['locatetime'] - points[0]['locatetime']) / 1000, duration, delta=0.001)
        # Every sample is on one of the two legs, never cutting the corner.
        self.assertTrue(all(p['latLng']['longitude'] == 121.44 or p['latLng']['latitude'] == 31.029 for p in points))

    def test_closed_route_starts_and_ends_at_same_point(self):
        points, _, _ = sample_route(ROUTE + [ROUTE[0]], 5, 3, 0)
        self.assertEqual(points[0]['latLng'], points[-1]['latLng'])
        self.assertGreater(points[-1]['locatetime'], points[0]['locatetime'])

    def test_segments_keep_boundary_distance_and_duration(self):
        route = [ROUTE[0], {'latitude': 31.04, 'longitude': 121.48}]
        points, distance, _ = sample_route(route, 5, 3, 100000)
        tracks = split_track_into_segments(points, 0)
        self.assertGreater(len(tracks), 1)
        for a, b in zip(tracks, tracks[1:]):
            self.assertEqual(a['points'][-1], b['points'][0])
        self.assertAlmostEqual(sum(t['distance'] for t in tracks), distance, delta=0.1)
        self.assertEqual(sum(t['duration'] for t in tracks), tracks[-1]['etime'] - tracks[0]['stime'])

    def test_payload_uses_snapshot_and_route_length_instead_of_fixed_distance(self):
        settings = {'使用自定义路线': True, '自定义路线': ROUTE, '路线名称': '转弯路线',
                    '参数随机': False, '每日距离_米': 5000, '配速_分钟每公里': 5,
                    'GPS采样间隔_秒': 3}
        with patch('src.data_generator.load_config', side_effect=AssertionError('must use snapshot')):
            body, distance, duration = generate_running_data_payload(
                {'APP_CONFIG': settings, 'USER_ID': 'offline', 'START_TIME_EPOCH_MS': 0}, [], {}, log_cb=lambda *a: None)
        tracks = body[0]['tracks']
        self.assertAlmostEqual(distance, route_distance(ROUTE), delta=0.1)
        self.assertNotAlmostEqual(distance, 5000, delta=100)
        self.assertEqual(tracks[0]['points'][0]['latLng'], ROUTE[0])
        self.assertEqual(tracks[-1]['points'][-1]['latLng'], ROUTE[-1])
        self.assertEqual(duration, sum(t['duration'] for t in tracks))

    def test_enabled_empty_route_never_falls_back_to_straight_line(self):
        with self.assertRaises(SportsUploaderError):
            generate_running_data_payload({'APP_CONFIG': {'使用自定义路线': True, '自定义路线': []},
                                           'USER_ID': 'offline'}, [], {})

    def test_cancel_sampling(self):
        with self.assertRaises(SportsUploaderError):
            sample_route(ROUTE, 5, 3, 0, stop_check_cb=lambda: True)


if __name__ == '__main__':
    unittest.main()
