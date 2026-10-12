import json
import threading
import time
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo
from src.main import run_sports_upload
from web.server import JobManager, WebServer, validate_config

POINTS = [{'latitude':31.0285,'longitude':121.4445},{'latitude':31.029,'longitude':121.448}]
CONFIG = {'自定义路线':POINTS,'路线名称':'校园路线'}
TOKEN = 'test-only-token-not-a-real-credential'

class FakeSession:
    def __init__(self): self.closed = False
    def close(self): self.closed = True

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.session = FakeSession()
        self.gate = threading.Event()
        def run(config, progress_callback, log_cb, stop_check_cb):
            self.received = config.copy()
            log_cb('PASSWORD=demo-secret; uid: sensitive-token')
            progress_callback(1,2,'离线模拟任务')
            self.gate.wait(3)
            return True, '离线模拟完成'
        self.manager = JobManager(login_fn=lambda u,p:self.session, run_fn=run)
        self.server = WebServer(('127.0.0.1',0),TOKEN,['https://yichenbert.github.io'],self.manager)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.gate.set();self.server.shutdown();self.server.server_close();self.thread.join()

    def request(self, path, data=None, token=TOKEN, origin=None):
        headers = {'Authorization':'Bearer '+token}
        if origin: headers['Origin']=origin
        body = None
        if data is not None:
            headers['Content-Type']='application/json';body=json.dumps(data).encode()
        request=urllib.request.Request(self.url+path,data=body,headers=headers)
        try:
            with urllib.request.urlopen(request,timeout=3) as response:
                return response.status,json.loads(response.read()),response.headers
        except urllib.error.HTTPError as error:
            return error.code,json.loads(error.read()),error.headers

    def body(self): return {'username':'demo-account','password':'demo-secret','config':CONFIG,'confirmed':True}

    def wait_done(self, id):
        for _ in range(100):
            job=self.manager.jobs[id].public(True)
            if job['state'] not in ('running','queued','stopping'):return job
            time.sleep(.01)
        self.fail('job did not finish')

    def test_unauthorized_and_untrusted_origin_cannot_read_or_start(self):
        self.assertEqual(self.request('/api/jobs',self.body(),token='wrong')[0],401)
        self.assertEqual(self.request('/api/status',origin='https://untrusted.example')[0],403)
        self.assertEqual(len(self.manager.jobs),0)
        code,_,headers=self.request('/api/status',origin='https://yichenbert.github.io')
        self.assertEqual(code,200);self.assertEqual(headers['Access-Control-Allow-Origin'],'https://yichenbert.github.io')

    def test_jobs_snapshot_config_redact_credentials_and_close_session(self):
        code,job,_=self.request('/api/jobs',self.body());self.assertEqual(code,202)
        self.gate.set();detail=self.wait_done(job['id'])
        text=json.dumps(detail)
        self.assertNotIn('demo-secret',text);self.assertNotIn('sensitive-token',text);self.assertNotIn('demo-account',text)
        self.assertEqual(detail['state'],'completed');self.assertEqual(detail['progress'],100)
        self.assertEqual(self.received['APP_CONFIG']['自定义路线'],POINTS)
        self.assertEqual(self.received['HOST'],'pe.sjtu.edu.cn')
        self.assertTrue(self.session.closed)

    def test_confirmation_validation_and_concurrent_job_rejected(self):
        data=self.body();data['confirmed']=False
        self.assertEqual(self.request('/api/jobs',data)[0],400)
        data=self.body();data['config']={'自定义路线':POINTS,'跑步天数':32}
        self.assertEqual(self.request('/api/jobs',data)[0],400)
        self.assertEqual(self.request('/api/jobs',self.body())[0],202)
        self.assertEqual(self.request('/api/jobs',self.body())[0],409)

    def test_stop_is_reported_and_nonexistent_job_is_404(self):
        _,job,_=self.request('/api/jobs',self.body())
        self.assertEqual(self.request('/api/jobs/'+job['id']+'/cancel',{})[0],200)
        self.gate.set();self.assertEqual(self.wait_done(job['id'])['state'],'cancelled')
        self.assertEqual(self.request('/api/jobs/nonexistent')[0],404)

    def test_client_cannot_override_remote_hosts_or_pass_invalid_dates(self):
        config=validate_config({**CONFIG,'HOST':'attacker.example','PASSWORD':'never-save'})
        self.assertNotIn('HOST',config);self.assertNotIn('PASSWORD',config)
        for dates in (['2999-01-01'],['2026-02-30'],['not-a-date']):
            with self.assertRaises(ValueError):validate_config({**CONFIG,'指定日期模式':True,'指定日期列表':dates})

    def test_web_dates_use_shanghai_timezone_independent_of_server_timezone(self):
        app_config=validate_config({**CONFIG,'指定日期模式':True,'指定日期列表':['2026-01-02'],'固定跑步时间_时':8})
        runtime={'TIMEZONE':'Asia/Shanghai','APP_CONFIG':app_config}
        payload=[{'tracks':[]}]
        with patch('src.main.get_authorization_token_and_rules',return_value=('mock-token',{})), patch('src.main.generate_running_data_payload',return_value=(payload,100,30)), patch('src.main.upload_running_data',return_value={'code':0,'data':True}) as upload:
            run_sports_upload(runtime,log_cb=lambda *args:None)
        expected=int(datetime(2026,1,2,8,tzinfo=ZoneInfo('Asia/Shanghai')).timestamp()*1000)
        self.assertEqual(upload.call_args.args[0]['START_TIME_EPOCH_MS'],expected)

    def test_static_server_denies_path_traversal(self):
        request=urllib.request.Request(self.url+'/../config.json')
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
        self.assertEqual(error.exception.code,404)

if __name__=='__main__':unittest.main()
