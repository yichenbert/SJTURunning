import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from src.route_library import RouteLibrary
from utils.auxiliary_util import SportsUploaderError

ROUTE=[{'latitude':31.028,'longitude':121.44},{'latitude':31.029,'longitude':121.442}]
OTHER=[ROUTE[0],{'latitude':31.029,'longitude':121.443}]

class RouteLibraryTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.path=Path(self.folder.name)/'routes.json'
        self.library=RouteLibrary(self.path)
    def tearDown(self):self.folder.cleanup()

    def test_multiple_routes_survive_reopening_and_exact_duplicate_not_added(self):
        a=self.library.save('路线',ROUTE);b=self.library.save('路线',OTHER)
        self.assertEqual(b['name'],'路线（2）')
        self.assertEqual(self.library.save('路线',ROUTE)['id'],a['id'])
        restored=RouteLibrary(self.path).load()
        self.assertEqual(len(restored),2)
        self.assertEqual({r['id'] for r in restored},{a['id'],b['id']})
        self.assertEqual(next(r for r in restored if r['id']==a['id'])['points'],ROUTE)

    def test_rename_preserves_points_and_rejects_collision(self):
        a=self.library.save('环线',ROUTE);b=self.library.save('直线',OTHER)
        self.library.rename(a['id'],'校园环线')
        self.assertEqual(next(r for r in self.library.load() if r['id']==a['id'])['points'],ROUTE)
        with self.assertRaises(SportsUploaderError):self.library.rename(b['id'],'校园环线')

    def test_invalid_file_cannot_overwrite_existing_library(self):
        self.path.write_text('{broken')
        with self.assertRaises(SportsUploaderError):self.library.save('路线',ROUTE)
        self.assertEqual(self.path.read_text(),'{broken')

    def test_failed_atomic_replace_preserves_existing_file(self):
        self.library.save('路线',ROUTE);before=self.path.read_bytes()
        with patch('src.route_library.os.replace',side_effect=OSError('write blocked')):
            with self.assertRaises(OSError):self.library.save('新路线',OTHER)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(list(self.path.parent.glob('.routes-*.tmp')),[])

    def test_import_wgs84_and_reject_unlabelled_gcj_source(self):
        source=self.path.parent/'export.json'
        source.write_text(json.dumps({'name':'旧路线','coordinate_system':'WGS84','points':ROUTE}))
        record=self.library.import_file(source)
        self.assertEqual(record['points'],ROUTE)
        source.write_text(json.dumps({'name':'其他路线','coordinate_system':'GCJ02','points':OTHER}))
        with self.assertRaises(SportsUploaderError):self.library.import_file(source)
        self.assertEqual(len(self.library.load()),1)

    def test_current_route_seed_happens_only_once(self):
        self.library.seed_current('旧配置',ROUTE)
        self.library.seed_current('新配置',OTHER)
        self.assertEqual([r['name'] for r in self.library.load()],['旧配置'])
