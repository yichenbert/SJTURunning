"""Local named WGS84 routes. Atomic writes; malformed libraries are never overwritten."""
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from src import config
from src.route import validate_route
from utils.auxiliary_util import SportsUploaderError


class RouteLibrary:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(config.get_config_path()).parent / 'routes.json'

    def load(self):
        if not self.path.exists():
            return []
        try:
            if self.path.stat().st_size > 30 * 1024 * 1024:
                raise ValueError('路线库文件过大')
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('version') != 1 or not isinstance(data.get('routes'), list):
                raise ValueError('路线库格式不受支持')
            ids = set()
            for route in data['routes']:
                if route.get('coordinate_system') != 'WGS84' or not isinstance(route.get('name'), str):
                    raise ValueError('路线信息无效')
                if not isinstance(route.get('id'), str) or route['id'] in ids:
                    raise ValueError('路线编号无效')
                ids.add(route['id'])
                validate_route(route['points'])
            return data['routes']
        except (OSError, ValueError, KeyError, TypeError, AttributeError, SportsUploaderError) as e:
            raise SportsUploaderError('无法读取路线库，原文件已保留。' + str(e)) from e

    def _write(self, routes):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.routes-', suffix='.tmp', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump({'version':1, 'routes':routes}, stream, ensure_ascii=False, indent=2)
                stream.flush();os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)

    def save(self, name, points):
        points, _ = validate_route(points)
        name = str(name).strip()[:80] or '我的路线'
        routes = self.load()
        for route in routes:
            if route['name'] == name and route['points'] == points:
                return route
        used = {r['name'] for r in routes}
        base, index = name, 2
        while name in used:
            name = f'{base}（{index}）';index += 1
        record = {'id':uuid.uuid4().hex, 'name':name, 'coordinate_system':'WGS84',
                  'points':points, 'saved_at':datetime.now(timezone.utc).isoformat()}
        self._write([record] + routes)
        return record

    def rename(self, route_id, name):
        name = name.strip()[:80]
        if not name:raise SportsUploaderError('路线名称不能为空。')
        routes = self.load()
        if any(r['name'] == name and r['id'] != route_id for r in routes):
            raise SportsUploaderError('这个名称已存在，请换一个名称。')
        record = next((r for r in routes if r['id'] == route_id), None)
        if record is None:raise SportsUploaderError('路线不存在，请重新打开路线库。')
        record['name'] = name
        self._write(routes)

    def import_file(self, filename):
        path = Path(filename)
        if path.stat().st_size > 2 * 1024 * 1024:
            raise SportsUploaderError('路线文件过大。')
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('coordinate_system', 'WGS84') != 'WGS84':
            raise SportsUploaderError('仅支持 WGS84 路线文件。')
        return self.save(data.get('name', path.stem), data['points'])

    def seed_current(self, name, points):
        if not self.path.exists() and points:
            self.save(name, points)
