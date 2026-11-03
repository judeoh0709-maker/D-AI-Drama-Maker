import base64
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from PIL import Image
import server
from drama.jobs import Jobs, Busy
from drama.wan22 import Wan22, Unavailable
from drama.pipeline import COUNTRIES, casting, Dialogue, PostProduction


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = Wan22()
        self.data = dict(mode='t2v', prompt='A quiet cafe', country='한국')

    def test_casting_all_countries_and_height_policy(self):
        for country in COUNTRIES:
            c = casting({'country': country})
            self.assertEqual(c['maleLead']['heightCm'], 183)
            self.assertTrue(c['maleLead']['locked'])
        for height in (179, 180, '183', None):
            with self.assertRaises(ValueError):
                casting({'maleLead': {'heightCm': height}})
        with self.assertRaises(ValueError):
            casting({'country': 'unknown'})

    def test_t2v_official_command(self):
        self.engine.repo = Path('/wan')
        self.engine.checkpoints = Path('/models')
        spec, image = self.engine.validate(self.data)
        cmd = self.engine.command(spec, Path('/output.mp4'))
        self.assertIsNone(image)
        for token in ('ti2v-5B', '1280*704', '--frame_num', '121', '--t5_cpu', '--convert_model_dtype'):
            self.assertIn(token, cmd)
        self.assertNotIn('--image', cmd)
        self.assertIn('183 cm', spec['prompt'])
        self.assertIn('natural pauses', spec['prompt'])

    def test_i2v_verified_image_and_command(self):
        raw = io.BytesIO()
        Image.new('RGB', (32, 32)).save(raw, format='PNG')
        spec, image = self.engine.validate(dict(self.data, mode='i2v', imageBase64=base64.b64encode(raw.getvalue()).decode()))
        self.assertEqual(image.size, (32, 32))
        self.engine.repo = Path('/wan')
        self.assertIn('--image', self.engine.command(spec, Path('/out.mp4'), Path('/ref.png')))

    def test_invalid_input(self):
        for changes in ({'mode':'bad'}, {'prompt':''}, {'frames':120}, {'frames':True},
                        {'seed':-1}, {'size':'1280*720'}, {'mode':'i2v'},
                        {'mode':'i2v','imageBase64':'garbage'}, {'lipSync': True},
                        {'maleLead': []}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.engine.validate(dict(self.data, **changes))

    def test_no_gpu_no_inference(self):
        spec, image = self.engine.validate(self.data)
        with patch.object(self.engine, 'status', return_value={'ready':False,'reasons':['no GPU']}), patch('drama.wan22.subprocess.run') as run:
            with self.assertRaises(Unavailable):
                self.engine.generate(spec, image, Path('/tmp/no-gpu.mp4'))
            run.assert_not_called()

    def test_inference_invocation_offline_and_failure_cleanup(self):
        spec, image = self.engine.validate(self.data)
        self.engine.repo = Path('/wan')
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'out.mp4'
            def fake_run(cmd, **kwargs):
                self.assertEqual(kwargs['env']['HF_HUB_OFFLINE'], '1')
                self.assertNotIn('shell', kwargs)
                output.write_bytes(b'fake-output')
                return subprocess.CompletedProcess(cmd, 0)
            with patch.object(self.engine, 'status', return_value={'ready':True}), patch('drama.wan22.subprocess.run', side_effect=fake_run):
                self.engine.generate(spec, image, output)
                self.assertTrue(output.exists())
            with patch.object(self.engine, 'status', return_value={'ready':True}), patch('drama.wan22.subprocess.run', side_effect=subprocess.TimeoutExpired('wan',1)):
                with self.assertRaises(subprocess.TimeoutExpired):
                    self.engine.generate(spec, image, output)
                self.assertFalse(output.exists())

    def test_voice_lipsync_extension_chain(self):
        calls=[]
        class Voice:
            def synthesize(self, dialogue, output):
                calls.append(dialogue.language); return output
        class Lip:
            def synchronize(self, video, audio, output):
                calls.append(audio.suffix); return output
        result=PostProduction(Voice(), Lip()).process(Path('v.mp4'), Dialogue('안녕','ko-KR','서준'), Path('final.mp4'))
        self.assertEqual(result, Path('final.mp4'))
        self.assertEqual(calls, ['ko-KR','.wav'])


class JobTests(unittest.TestCase):
    def test_single_worker_success_failure(self):
        entered, release = threading.Event(), threading.Event()
        class Fake:
            def generate(self, spec, image, output):
                entered.set(); release.wait(3)
                if spec.get('fail'): raise RuntimeError('expected failure')
                output.write_bytes(b'test')
        with tempfile.TemporaryDirectory() as tmp:
            jobs = Jobs(Fake(), Path(tmp))
            job = jobs.submit({'cast':{}}, None)
            self.assertTrue(entered.wait(2))
            with self.assertRaises(Busy): jobs.submit({'cast':{}}, None)
            release.set()
            for _ in range(100):
                if not jobs.active: break
                time.sleep(.01)
            self.assertEqual(jobs.get(job)['status'],'succeeded')
            bad = jobs.submit({'cast':{}, 'fail':True}, None)
            for _ in range(100):
                if not jobs.active: break
                time.sleep(.01)
            self.assertEqual(jobs.get(bad)['status'],'failed')
            self.assertIsNone(jobs.get('not-found'))


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = ThreadingHTTPServer(('127.0.0.1',0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:'+str(cls.http.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join()

    def request(self, path, data=None, headers=None):
        req = Request(self.base+path, data=json.dumps(data).encode() if data is not None else None,
                      headers=headers or {})
        try: response=urlopen(req,timeout=30)
        except HTTPError as exc: response=exc
        with response: return response.status, response.read()

    def test_ui_health_errors(self):
        status, body = self.request('/')
        self.assertEqual(status,200)
        self.assertIn('텍스트 → 영상'.encode(),body)
        self.assertEqual(self.request('/api/capabilities')[0],200)
        self.assertEqual(self.request('/api/render',[])[0],400)
        self.assertEqual(self.request('/api/generate',{'prompt':''})[0],400)
        self.assertEqual(self.request('/api/jobs/aaaaaaaaaaaa')[0],404)
        self.assertEqual(self.request('/exports/../../server.py')[0],404)
        self.assertEqual(self.request('/api/render',{}, {'Origin':'https://other.example'})[0],403)
        with patch.object(server.ENGINE,'status',return_value={'ready':False,'reasons':['no GPU']}):
            self.assertEqual(self.request('/api/generate',{'prompt':'test'})[0],503)

    def test_generate_submission_and_poll(self):
        class Fake:
            def generate(self, spec, image, output): output.write_bytes(b'fake')
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(server.ENGINE,'status',return_value={'ready':True}), patch.object(server,'JOBS',Jobs(Fake(),Path(tmp))):
                status, body=self.request('/api/generate', {'prompt':'test'})
                self.assertEqual(status,202)
                url=json.loads(body)['statusUrl']
                for _ in range(100):
                    status, body=self.request(url)
                    if json.loads(body)['status']=='succeeded':break
                    time.sleep(.01)
                self.assertEqual(json.loads(body)['status'],'succeeded')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
    def test_real_storyboard_mp4(self):
        # Actual encoder and download route, not a mocked render.
        status, body=self.request('/api/render',{'country':'한국','title':'검증','scenes':['자연스러운 재회'], 'duration':2})
        self.assertEqual(status,200,body)
        url=json.loads(body)['videoUrl']; path=server.EXPORTS/Path(url).name
        try:
            self.assertEqual(self.request(url)[0],200)
            probe=subprocess.run(['ffprobe','-v','error','-show_streams','-of','json',str(path)],capture_output=True,text=True,check=True)
            streams=json.loads(probe.stdout)['streams']
            self.assertEqual(streams[0]['codec_name'],'h264')
            self.assertGreaterEqual(float(streams[0]['duration']),2)
        finally:path.unlink(missing_ok=True)


if __name__=='__main__': unittest.main()
