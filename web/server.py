"""Optional single-owner backend. Run behind an HTTPS reverse proxy for public use."""
from __future__ import annotations
import argparse
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from src.route import validate_route
from src import login
from src.main import run_sports_upload
from utils.auxiliary_util import SportsUploaderError

VERSION = '1.0.0'
STATIC = Path(__file__).parent / 'static'
ALLOWED_FILES = {'index.html', 'style.css', 'app.mjs', 'core.mjs', 'icon.svg', 'manifest.webmanifest', 'sw.js', 'LICENSE.txt'}
MIME = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.svg': 'image/svg+xml', '.webmanifest': 'application/manifest+json'}


def validate_config(value):
    if not isinstance(value, dict):
        raise ValueError('参数配置必须为对象。')
    points, _ = validate_route(value.get('自定义路线', []))
    name = value.get('路线名称', '我的路线')
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise ValueError('路线名称必须为 1 至 80 个字符。')
    result = {'使用自定义路线': True, '自定义路线': points, '路线名称': name.strip()}
    ranges = {'跑步天数': (1, 31, 1), '配速_分钟每公里': (3, 9, 0),
              '配速最小_分钟每公里': (3, 9, 0), '配速最大_分钟每公里': (3, 9, 0),
              'GPS采样间隔_秒': (1, 60, 1), '固定跑步时间_时': (0, 23, 1), '固定跑步时间_分': (0, 59, 1)}
    defaults = {'跑步天数': 1, '配速_分钟每公里': 5, '配速最小_分钟每公里': 4.5,
                '配速最大_分钟每公里': 6, 'GPS采样间隔_秒': 3, '固定跑步时间_时': 8, '固定跑步时间_分': 0}
    for key, (low, high, integer) in ranges.items():
        n = value.get(key, defaults[key])
        if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or not low <= n <= high or integer and int(n) != n:
            raise ValueError(f'参数 {key} 不在有效范围内。')
        result[key] = int(n) if integer else float(n)
    if result['配速最小_分钟每公里'] > result['配速最大_分钟每公里']:
        raise ValueError('最小配速不能大于最大配速。')
    for key in ('指定日期模式', '参数随机'):
        flag = value.get(key, False)
        if not isinstance(flag, bool):
            raise ValueError(f'参数 {key} 必须为布尔值。')
        result[key] = flag
    dates = value.get('指定日期列表', [])
    if not isinstance(dates, list) or len(dates) > 31 or result['指定日期模式'] and not dates:
        raise ValueError('请指定 1 至 31 个日期。')
    clean_dates = []
    for item in dates:
        if not isinstance(item, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', item):
            raise ValueError('日期格式应为 YYYY-MM-DD。')
        parsed = date.fromisoformat(item)
        if parsed > datetime.now(ZoneInfo('Asia/Shanghai')).date():
            raise ValueError('不能选择未来日期。')
        if item not in clean_dates:
            clean_dates.append(item)
    result['指定日期列表'] = clean_dates
    result['跑步时间随机'] = False
    for key, point, axis in [('起点纬度', points[0], 'latitude'), ('起点经度', points[0], 'longitude'),
                              ('终点纬度', points[-1], 'latitude'), ('终点经度', points[-1], 'longitude')]:
        result[key] = point[axis]
    return result


@dataclass
class Job:
    id: str
    name: str
    created: float = field(default_factory=time.time)
    state: str = 'queued'
    progress: float = 0
    message: str = ''
    logs: list = field(default_factory=list)
    stop: threading.Event = field(default_factory=threading.Event)
    lock: threading.RLock = field(default_factory=threading.RLock)

    def public(self, detail=False):
        with self.lock:
            value = {key: getattr(self, key) for key in ('id', 'name', 'created', 'state', 'progress', 'message')}
            if detail:
                value['logs'] = deepcopy(self.logs)
            return value


class JobManager:
    def __init__(self, login_fn=None, run_fn=None):
        self.jobs = OrderedDict()
        self.lock = threading.RLock()
        self.login_fn = login_fn or login.login
        self.run_fn = run_fn or run_sports_upload

    def submit(self, body):
        if not isinstance(body, dict) or body.get('confirmed') is not True:
            raise ValueError('请先确认本次任务。')
        username, password = body.get('username'), body.get('password')
        if not isinstance(username, str) or not username.strip() or len(username) > 256 or not isinstance(password, str) or not password or len(password) > 1024:
            raise ValueError('请输入有效的用户名和密码。')
        config = validate_config(body.get('config'))
        with self.lock:
            if any(j.state in ('queued', 'running', 'stopping') for j in self.jobs.values()):
                raise RuntimeError('已有任务正在运行，请等待完成或停止后再试。')
            job = Job(secrets.token_urlsafe(18), config['路线名称'])
            self.jobs[job.id] = job
            while len(self.jobs) > 50:
                self.jobs.popitem(last=False)
            threading.Thread(target=self._work, args=(job, username.strip(), password, config), daemon=True).start()
        return job.public()

    def _work(self, job, username, password, app_config):
        session = None
        runtime = {}
        def clean(message):
            text = str(message)
            if re.search(r'authorization|cookie|JAAuthCookie|["\x27]?uid["\x27]?\s*[:=]|token\s*[:=]', text, re.I):
                return '服务认证信息已隐藏。'
            for secret in (password, username):
                if secret:
                    text = text.replace(secret, '[已隐藏]')
            return text[:2000]
        def log(message, level='info'):
            with job.lock:
                job.logs.append({'time': time.time(), 'level': level, 'message': clean(message)})
                job.logs[:] = job.logs[-500:]
        def progress(current, total, message):
            with job.lock:
                job.progress = max(0, min(100, current / max(1, total) * 100))
            log(message)
        try:
            with job.lock:
                job.state = 'running'
            if job.stop.is_set():
                raise SportsUploaderError('任务已停止。')
            log('正在登录…')
            session = self.login_fn(username, password)
            if session is None:
                raise SportsUploaderError('登录失败，请检查账号或服务权限。')
            if job.stop.is_set():
                raise SportsUploaderError('任务已停止。')
            runtime = {'TIMEZONE': 'Asia/Shanghai', 'USER_ID': username, 'PASSWORD': password, 'SESSION': session, 'APP_CONFIG': app_config,
                       'START_LATITUDE': app_config['起点纬度'], 'START_LONGITUDE': app_config['起点经度'],
                       'END_LATITUDE': app_config['终点纬度'], 'END_LONGITUDE': app_config['终点经度'],
                       'INTERVAL_SECONDS': app_config['GPS采样间隔_秒'], 'RUNNING_SPEED_MPS': 1000 / (app_config['配速_分钟每公里'] * 60),
                       'HOST': 'pe.sjtu.edu.cn', 'UID_URL': 'https://pe.sjtu.edu.cn/sports/my/uid',
                       'MY_DATA_URL': 'https://pe.sjtu.edu.cn/sports/my/data', 'POINT_RULE_URL': 'https://pe.sjtu.edu.cn/api/running/point-rule',
                       'UPLOAD_URL': 'https://pe.sjtu.edu.cn/api/running/result/upload'}
            ok, message = self.run_fn(runtime, progress_callback=progress, log_cb=log, stop_check_cb=job.stop.is_set)
            with job.lock:
                job.state = 'cancelled' if job.stop.is_set() else 'completed' if ok else 'failed'
                job.message = clean(message)
                if ok:
                    job.progress = 100
        except Exception as error:
            with job.lock:
                job.state = 'cancelled' if job.stop.is_set() else 'failed'
                job.message = clean(error) if isinstance(error, SportsUploaderError) else '服务执行失败，请检查网络与服务配置。'
            log(job.message, 'error')
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass
            runtime.clear()
            password = username = ''

    def cancel(self, job):
        with job.lock:
            if job.state in ('queued', 'running', 'stopping'):
                job.stop.set()
                job.state = 'stopping'
        return job.public()


class WebServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, token, origins, manager=None):
        self.access_token = token
        self.origins = set(origins)
        self.manager = manager or JobManager()
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = 'SJTUWeb/1.0'
    def log_message(self, *args):
        pass

    def send(self, status, value, mime='application/json; charset=utf-8'):
        data = json.dumps(value, ensure_ascii=False).encode() if not isinstance(value, bytes) else value
        self.send_response(status)
        origin = self.headers.get('Origin')
        if origin and self.allowed_origin(origin):
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store' if self.path.startswith('/api/') else 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def allowed_origin(self, origin):
        own = {'http://' + self.headers.get('Host', ''), 'https://' + self.headers.get('Host', '')}
        return origin in self.server.origins or origin in own

    def authorize(self):
        origin = self.headers.get('Origin')
        if origin and not self.allowed_origin(origin):
            self.send(403, {'error': '该网页来源未在服务端允许列表中。'})
            return False
        token = self.headers.get('Authorization', '')
        if not secrets.compare_digest(token.encode(), ('Bearer ' + self.server.access_token).encode()):
            self.send(401, {'error': '服务访问密钥无效。'})
            return False
        return True

    def do_OPTIONS(self):
        origin = self.headers.get('Origin')
        if origin and self.allowed_origin(origin):
            self.send(204, b'')
        else:
            self.send(403, {'error': '网页来源未获允许。'})

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.startswith('/api/'):
            if not self.authorize():
                return
            if path == '/api/status':
                self.send(200, {'version': VERSION, 'capabilities': ['jobs', 'cancel']})
            elif path == '/api/jobs':
                with self.server.manager.lock:
                    jobs = [j.public() for j in reversed(self.server.manager.jobs.values())]
                self.send(200, jobs)
            elif re.fullmatch(r'/api/jobs/[\w-]+', path):
                job = self.server.manager.jobs.get(path.rsplit('/', 1)[-1])
                self.send(200, job.public(True)) if job else self.send(404, {'error': '任务不存在。'})
            else:
                self.send(404, {'error': '接口不存在。'})
            return
        file = 'index.html' if path == '/' else path.lstrip('/')
        if file not in ALLOWED_FILES:
            self.send(404, {'error': '文件不存在。'})
            return
        self.send(200, (STATIC / file).read_bytes(), MIME.get(Path(file).suffix, 'application/octet-stream'))

    def do_POST(self):
        path = urlsplit(self.path).path
        if not self.authorize():
            return
        try:
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self.send(415, {'error': '请求必须为 JSON。'})
                return
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > 1024 * 1024:
                self.send(413, {'error': '请求内容为空或超过 1 MB。'})
                return
            self.connection.settimeout(15)
            body = json.loads(self.rfile.read(length))
            if path == '/api/jobs':
                self.send(202, self.server.manager.submit(body))
            elif re.fullmatch(r'/api/jobs/[\w-]+/cancel', path):
                job = self.server.manager.jobs.get(path.split('/')[-2])
                self.send(200, self.server.manager.cancel(job)) if job else self.send(404, {'error': '任务不存在。'})
            else:
                self.send(404, {'error': '接口不存在。'})
        except RuntimeError as error:
            self.send(409, {'error': str(error)})
        except (ValueError, TypeError, SportsUploaderError) as error:
            self.send(400, {'error': str(error)[:300]})
        except TimeoutError:
            self.send(408, {'error': '读取请求超时。'})
        except Exception:
            self.send(500, {'error': '服务内部错误。'})


def main():
    parser = argparse.ArgumentParser(description='SJTU RUN Web companion server')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--allow-origin', action='append', default=['https://yichenbert.github.io'])
    args = parser.parse_args()
    token = os.environ.get('SJTU_WEB_TOKEN', '')
    if len(token) < 24:
        parser.error('请设置至少 24 字符的 SJTU_WEB_TOKEN 环境变量。')
    server = WebServer((args.host, args.port), token, args.allow_origin)
    print(f'SJTU RUN Web {VERSION}: http://{args.host}:{server.server_port}', flush=True)
    print('服务访问密钥已从环境变量读取；公开部署请使用 HTTPS 反向代理。', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for job in server.manager.jobs.values():
            job.stop.set()
        server.server_close()

if __name__ == '__main__':
    main()
