# D · AI Drama Maker

로컬 Python 서버와 웹 UI. 광고·결제·로그인·유료 API 연동 없음.

## 실행

Python 3.10 이상, FFmpeg 필요 (스토리보드 출력). 기본 앱은 PyTorch 없이 실행됩니다.

```sh
python -m venv .venv
# Linux/macOS
. .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python server.py
```

http://127.0.0.1:8765 에서 실행합니다. HTML 파일 직접 열기로는 생성 API가 동작하지 않습니다. 포트는 `DRAMA_PORT`, 한글 폰트는 `DRAMA_FONT`로 지정할 수 있습니다.

## 두 가지 영상 엔진

- **스토리보드 MP4**: CPU에서 Pillow + FFmpeg로 장면별 대본 카드를 영상화합니다. 실제 인물 움직임과 오디오는 없습니다.
- **Wan2.2 AI 영상**: 공식 TI2V-5B `generate.py`를 별도 Python 환경에서 실행합니다. 텍스트→영상과 참조 이미지→영상을 지원합니다. 한 번에 한 장면, 무음 출력입니다. UI에서 프롬프트·방향·프레임·시드를 지정합니다.

한국·일본·미국·영국·프랑스·이탈리아의 기존 가상 배우 캐스팅을 유지합니다. 서버가 국가별 주연을 결정하고 남자 주인공을 **183cm / 최소 180cm**로 고정합니다. API에서 다른 키를 제출하면 거부합니다. 이 정책은 프로필과 프롬프트에 적용되며, 생성 영상 속 실제 신체 비율을 보장하는 제어 모델은 아닙니다. 이미지→영상의 인물 외형은 참조 이미지 영향을 받습니다.

## Wan2.2 준비 (GPU가 있는 컴퓨터에서만)

**이 앱은 모델을 다운로드하지 않습니다.** 현재 Codex 환경에는 NVIDIA GPU와 PyTorch가 없어 모델 다운로드와 실제 AI 추론을 수행하지 않았습니다.

[공식 설치 및 체크포인트 안내](https://github.com/Wan-Video/Wan2.2#installation)를 따라 별도 환경에 소스·공식 의존성과 `Wan2.2-TI2V-5B` 체크포인트를 준비합니다. 공식 안내는 단일 GPU TI2V-5B에 최소 24GB VRAM과 CPU 오프로딩을 제시합니다. 실제 필요 메모리는 환경과 설정에 따라 달라집니다.

검토한 공식 버전: [`1ea34ff48f87168174e12956e200b1d908b1c5ff`](https://github.com/Wan-Video/Wan2.2/tree/1ea34ff48f87168174e12956e200b1d908b1c5ff). 해당 버전의 `README.md`, `generate.py`를 참고했습니다.

Linux/macOS 예시 (모두 본인의 실제 절대 경로로 변경):

```sh
export WAN22_REPO=/path/to/Wan2.2
export WAN22_CKPT_DIR=/path/to/Wan2.2-TI2V-5B
export WAN22_PYTHON=/path/to/wan-venv/bin/python
export WAN22_TIMEOUT=3600
python server.py
```

Windows PowerShell에서는 `$env:WAN22_REPO='C:\path\Wan2.2'`와 같은 방식으로 설정합니다. `WAN22_PYTHON`은 공식 의존성 및 CUDA PyTorch를 설치한 Python 실행 파일이어야 합니다. 미설정 시 현재 Python을 사용합니다.

UI의 환경 안내를 확인하고 엔진을 Wan2.2로 선택합니다. `ready`는 CUDA·소스·체크포인트 파일의 사전 확인 결과이며, 전체 모델 완전성·의존성 및 VRAM 적합성은 실제 추론 시 확인됩니다.

- 공식 task: `ti2v-5B`; 크기: `1280*704` 또는 `704*1280`.
- `--offload_model True --convert_model_dtype --t5_cpu` 사용.
- `frames`는 5~241의 `4n+1`, 기본 121 (24fps, 약 5초).
- 이미지: PNG/JPEG/WebP, UI 파일 6MB 이하, 디코딩된 이미지 1600만 화소 이하. I2V 출력 비율은 공식 엔진에 따라 참조 이미지 비율을 따릅니다.
- 모델 라이브러리에 `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` 적용. 프롬프트 확장·외부 API 호출 없음.

## API

| 경로 | 기능 |
| --- | --- |
| `GET /api/capabilities` | CUDA 및 로컬 Wan 준비 상태, FFmpeg 여부 |
| `POST /api/render` | 기존 스토리보드 MP4 생성 |
| `POST /api/generate` | AI 작업 제출, 성공 시 202 + `id`, `statusUrl` |
| `GET /api/jobs/{id}` | queued / running / succeeded / failed |
| `GET /exports/{id}.mp4` | 생성 파일 미리보기·다운로드 |

AI 요청 예시:

```json
{"mode":"t2v","prompt":"Two adult actors reunite at a cafe","country":"한국","maleLead":{"heightCm":183},"size":"1280*704","frames":121,"seed":42}
```

I2V는 `mode: "i2v"`, `imageBase64`에 data URL 접두사 없는 Base64 이미지 내용을 추가합니다. 준비되지 않은 엔진은 503, 진행 중 추가 작업은 409, 잘못된 입력은 400입니다. 작업 기록은 메모리에 최근 50건만 보관합니다. 재시작 시 기록과 진행 작업 상태는 복구되지 않으며, 출력 MP4는 유지됩니다. UI는 마지막 작업 주소를 로컬 저장하여 페이지 새로고침 후 조회합니다.

## 연기·음성·립싱크 확장

`drama/pipeline.py`의 `Performance`가 자연스러운 표정·호흡·여유 있는 연기 지시를 프롬프트에 추가합니다. `Dialogue`, `VoiceProvider`, `LipSyncProvider`, `PostProduction`은 향후 로컬 TTS와 립싱크 구현을 연결할 인터페이스입니다. 실제 공급자는 아직 연결되어 있지 않습니다. 브라우저 음성 미리듣기는 기존 OS TTS이며 MP4 오디오가 아닙니다.

아직 구현되지 않은 기능: 영상에 포함되는 음성, 립싱크 추론, 장면 간 얼굴 일관성 제어, 여러 AI 장면 자동 합성, AI 스토리 대본 생성. 기존 대본 생성은 템플릿이며 국가 선택만으로 전체 대사가 번역되지는 않습니다.

## 테스트

```sh
python -m unittest discover -s tests -v
```

실제 HTTP 서버와 FFmpeg를 포함한 11개 테스트. GPU 추론은 모의 호출로 명령·실패 정리를 확인하고, GPU가 없는 환경에서 실행을 거부하는지 확인합니다. 전체 GPU 모델 추론 테스트가 아닙니다.

선택적 UI 테스트: Node.js, Playwright, Chromium 설치 후:

```sh
DRAMA_TEST_PYTHON=/path/to/python CHROMIUM_PATH=/path/to/chromium node tests/browser.cjs
```

[전체 소스 분석과 검증 결과](docs/ANALYSIS.md)를 참고하세요. 기본 서버는 로컬 `127.0.0.1`에만 바인딩합니다.
