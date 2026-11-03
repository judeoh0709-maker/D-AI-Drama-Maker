"""Adapter to official Wan-Video/Wan2.2 generate.py (TI2V-5B).

The user provisions source, Python dependencies and local checkpoints separately.
No hub client, remote API, shell command, or automatic download is used.
"""
from __future__ import annotations
import base64
import binascii
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from PIL import Image, ImageOps
from .pipeline import Performance, casting


class Unavailable(RuntimeError):
    pass


class Wan22:
    def __init__(self):
        self.repo = Path(os.environ['WAN22_REPO']).expanduser().resolve() if os.getenv('WAN22_REPO') else None
        self.checkpoints = Path(os.environ['WAN22_CKPT_DIR']).expanduser().resolve() if os.getenv('WAN22_CKPT_DIR') else None
        self.python = os.getenv('WAN22_PYTHON', sys.executable)
        self.timeout = int(os.getenv('WAN22_TIMEOUT', '3600'))

    def status(self):
        probe = 'import json,torch; print(json.dumps({"cuda":torch.cuda.is_available(),"devices":torch.cuda.device_count()}))'
        try:
            p = subprocess.run([self.python, '-c', probe], capture_output=True, text=True, timeout=20)
            gpu = json.loads(p.stdout) if p.returncode == 0 else {'cuda': False, 'devices': 0}
        except (OSError, ValueError, subprocess.TimeoutExpired):
            gpu = {'cuda': False, 'devices': 0}
        reasons = []
        if not gpu.get('cuda'):
            reasons.append('CUDA GPU 또는 Wan Python 환경의 PyTorch를 사용할 수 없습니다.')
        if not self.repo or not (self.repo / 'generate.py').is_file():
            reasons.append('WAN22_REPO에 공식 Wan2.2 소스 경로를 설정하세요.')
        if not self.checkpoints or not self.checkpoints.is_dir() or not any(self.checkpoints.rglob('*.safetensors')):
            reasons.append('WAN22_CKPT_DIR에 로컬 TI2V-5B 체크포인트를 준비하세요.')
        return dict(ready=not reasons, gpu=gpu, reasons=reasons, task='ti2v-5B',
                    autoDownload=False, audio=False, lipSync=False)

    def validate(self, data):
        if not isinstance(data, dict):
            raise ValueError('JSON 객체가 필요합니다.')
        cast = casting(data)
        mode = data.get('mode', 't2v')
        if mode not in ('t2v', 'i2v'):
            raise ValueError('mode는 t2v 또는 i2v여야 합니다.')
        prompt = data.get('prompt')
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 4000:
            raise ValueError('영상 프롬프트는 1~4000자여야 합니다.')
        size = data.get('size', '1280*704')
        if size not in ('1280*704', '704*1280'):
            raise ValueError('TI2V-5B 크기는 1280*704 또는 704*1280입니다.')
        frames, seed = data.get('frames', 121), data.get('seed', 42)
        if type(frames) is not int or not 5 <= frames <= 241 or (frames - 1) % 4:
            raise ValueError('frames는 5~241 범위의 4n+1이어야 합니다.')
        if type(seed) is not int or not 0 <= seed <= 2147483647:
            raise ValueError('seed는 0~2147483647 정수여야 합니다.')
        image = None
        if mode == 'i2v':
            encoded = data.get('imageBase64')
            if not isinstance(encoded, str) or len(encoded) > 8_000_000:
                raise ValueError('8MB 이하 Base64 이미지가 필요합니다.')
            try:
                raw = base64.b64decode(encoded, validate=True)
                with Image.open(io.BytesIO(raw)) as im:
                    if im.format not in ('PNG', 'JPEG', 'WEBP') or im.width * im.height > 16_000_000:
                        raise ValueError('PNG/JPEG/WebP, 1600만 화소 이하 이미지를 사용하세요.')
                    im.load()
                    image = ImageOps.exif_transpose(im).convert('RGB')
            except (binascii.Error, OSError, Image.DecompressionBombError) as exc:
                raise ValueError('올바른 이미지를 선택하세요.') from exc
        elif data.get('imageBase64'):
            raise ValueError('이미지 입력에는 i2v 모드를 사용하세요.')
        if data.get('audio') or data.get('lipSync'):
            raise ValueError('음성·립싱크 공급자는 아직 연결되지 않았습니다.')
        perf = Performance()
        full_prompt = (f'{prompt.strip()}. Cast: {cast["nationality"]} fictional adult actors, '
                       f'{cast["maleLead"]["name"]}, male lead, 183 cm tall; '
                       f'{cast["femaleLead"]["name"]}, female lead. '
                       f'{perf.expression}. {perf.acting}. {perf.identity}.')
        return dict(mode=mode, prompt=full_prompt, size=size, frames=frames, seed=seed, cast=cast), image

    def command(self, spec, output, image=None):
        cmd = [self.python, str(self.repo / 'generate.py'), '--task', 'ti2v-5B',
               '--size', spec['size'], '--ckpt_dir', str(self.checkpoints),
               '--offload_model', 'True', '--convert_model_dtype', '--t5_cpu',
               '--frame_num', str(spec['frames']), '--base_seed', str(spec['seed']),
               '--prompt', spec['prompt'], '--save_file', str(output)]
        if image is not None:
            cmd += ['--image', str(image)]
        return cmd

    def generate(self, spec, image, output):
        status = self.status()
        if not status['ready']:
            raise Unavailable(' '.join(status['reasons']))
        with tempfile.TemporaryDirectory(prefix='wan22_') as temp:
            image_path = None
            if image is not None:
                image_path = Path(temp) / 'reference.png'
                image.save(image_path)
            # Keep model libraries offline, including accidental hub resolution.
            env = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
            log = Path(temp) / 'inference.log'
            try:
                with log.open('w') as stream:
                    p = subprocess.run(self.command(spec, output, image_path), cwd=self.repo,
                                       stdout=stream, stderr=subprocess.STDOUT, env=env,
                                       timeout=self.timeout)
                if p.returncode or not output.is_file() or output.stat().st_size == 0:
                    raise RuntimeError('Wan2.2 추론 실패. 로컬 체크포인트와 공식 의존성을 확인하세요.')
            except BaseException:
                output.unlink(missing_ok=True)
                raise
