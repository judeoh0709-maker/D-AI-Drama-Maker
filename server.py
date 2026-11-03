"""D AI Drama Maker: offline storyboard-to-MP4 developer starter.
Uses Python stdlib + Pillow + locally installed FFmpeg. No payments or API keys.
"""
from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
WEB = ROOT / 'web'
EXPORTS = ROOT / 'exports'
EXPORTS.mkdir(exist_ok=True)
FONT_CANDIDATES = [
    '/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf',
    '/usr/share/fonts/truetype/nanum/NanumSquareB.ttf',
    'C:/Windows/Fonts/malgun.ttf',
    '/System/Library/Fonts/AppleSDGothicNeo.ttc',
]

def font(size):
    custom = os.getenv('DRAMA_FONT')
    for path in ([custom] if custom else []) + FONT_CANDIDATES:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def wrap_pixels(draw, txt, text_font, maxwidth):
    lines=[]
    for para in txt.splitlines() or ['']:
        if not para.strip():
            lines.append(''); continue
        buf=''
        for c in para:
            if draw.textbbox((0,0),buf+c,font=text_font)[2] > maxwidth and buf:
                lines.append(buf); buf=c
            else: buf+=c
        lines.append(buf)
    return lines

def make_frame(path, scene, idx, total, title, country, actors):
    W,H = 1280,720
    base = Image.new('RGB',(W,H))
    px=base.load()
    colors=[((18,21,40),(71,39,78)),((12,32,44),(39,73,87)),((32,24,52),(76,48,65))]
    a,b=colors[idx%len(colors)]
    for y in range(H):
        t=y/H
        rgb=tuple(int(a[i]*(1-t)+b[i]*t) for i in range(3))
        for x in range(W):px[x,y]=rgb
    draw=ImageDraw.Draw(base)
    draw.ellipse((850,-180,1450,430), fill=(96,68,108),outline=(138,109,149),width=3)
    draw.ellipse((-170,400,410,970),fill=(29,44,64))
    draw.rounded_rectangle((82,95,1198,625),radius=24,fill=(16,20,37),outline=(150,130,195),width=2)
    draw.text((120,126),f'D · AI DRAMA MAKER    /    SCENE {idx+1:02d} OF {total:02d}',font=font(24),fill=(196,179,246))
    title_lines=wrap_pixels(draw,title,font(42),1040)[:2]
    y=195
    for line in title_lines:
        draw.text((120,y),line,font=font(42),fill=(246,239,255));y+=60
    draw.line((120,y+10,1150,y+10),fill=(92,90,121),width=2)
    y+=42
    for line in wrap_pixels(draw,scene,font(28),1020)[:7]:
        draw.text((120,y),line,font=font(28),fill=(223,225,239));y+=43
    draw.text((120,648),f'{country}   |   {actors}   |   STORYBOARD PREVIEW',font=font(19),fill=(192,192,209))
    base.save(path)

def render_video(data):
    if shutil.which('ffmpeg') is None:
        raise RuntimeError('FFmpeg를 찾을 수 없습니다. 설치하고 PATH에 추가하세요.')
    scenes=data.get('scenes')
    if not isinstance(scenes,list) or not (1 <= len(scenes) <= 12):
        raise ValueError('장면은 1~12개여야 합니다.')
    if any(not isinstance(x,str) or not x.strip() or len(x)>1600 for x in scenes):
        raise ValueError('각 장면은 1~1600자의 텍스트여야 합니다.')
    duration=data.get('duration',5)
    if type(duration) not in (int,float) or not 2 <= duration <= 12:
        raise ValueError('장면 길이는 2~12초로 지정하세요.')
    title=str(data.get('title','D AI Drama'))[:100]
    country=str(data.get('country','한국'))[:30]
    actors=str(data.get('actors','남자 주인공 183cm'))[:120]
    job=uuid.uuid4().hex[:12]
    output=EXPORTS/f'{job}.mp4'
    with tempfile.TemporaryDirectory(prefix='drama_') as temp:
        tmp=Path(temp)
        for i,scene in enumerate(scenes):
            make_frame(tmp/f'frame{i:03d}.png',scene,i,len(scenes),title,country,actors)
        concat=tmp/'concat.txt'
        lines=[]
        for i in range(len(scenes)):
            lines.extend([f"file '{(tmp/f'frame{i:03d}.png').as_posix()}'",f'duration {duration}'])
        lines.append(f"file '{(tmp/f'frame{len(scenes)-1:03d}.png').as_posix()}'")
        concat.write_text('\n'.join(lines)+'\n',encoding='utf-8')
        cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(concat),'-vf','fps=24,format=yuv420p','-c:v','libx264','-preset','veryfast','-crf','23','-movflags','+faststart','-an',str(output)]
        proc=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
        if proc.returncode:
            raise RuntimeError('영상 인코딩 실패: '+proc.stderr[-600:])
    return output.name

class Handler(BaseHTTPRequestHandler):
    def response(self, status, content, mime='application/json; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(content)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        self.wfile.write(content)
    def json_response(self,status,payload):
        self.response(status,json.dumps(payload,ensure_ascii=False).encode('utf-8'))
    def do_GET(self):
        path=unquote(urlparse(self.path).path)
        if path in ('/','/index.html'):
            file=WEB/'index.html';mime='text/html; charset=utf-8'
        elif re.fullmatch(r'/exports/[a-f0-9]{12}\.mp4',path):
            file=EXPORTS/Path(path).name;mime='video/mp4'
        else:
            self.json_response(404,{'error':'Not found'});return
        if not file.is_file():
            self.json_response(404,{'error':'File not found'});return
        self.response(200,file.read_bytes(),mime)
    def do_POST(self):
        if urlparse(self.path).path!='/api/render':
            self.json_response(404,{'error':'Not found'});return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not (0<size<=100_000):
                self.json_response(413,{'error':'요청 크기가 너무 큽니다.'});return
            data=json.loads(self.rfile.read(size))
            name=render_video(data)
            self.json_response(200,{'videoUrl':'/exports/'+name,'message':'스토리보드 MP4 생성 완료'})
        except (ValueError,RuntimeError,subprocess.TimeoutExpired) as err:
            self.json_response(400,{'error':str(err)})
        except Exception as err:
            self.json_response(500,{'error':f'서버 오류: {type(err).__name__}'})

if __name__=='__main__':
    host='127.0.0.1';port=int(os.getenv('DRAMA_PORT','8765'))
    print(f'D AI Drama Maker → http://{host}:{port}')
    ThreadingHTTPServer((host,port),Handler).serve_forever()
