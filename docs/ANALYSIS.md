# 전체 소스 분석 및 검증 결과

기준 저장소: `judeoh0709-maker/D-AI-Drama-Maker`, `master`, `cf45ba76c48d24f5f85e469bf269494a1563b678`.
검증일: 2026-11-03 (한국 시간).

## 기존 추적 파일 전수 분석

| 파일 | 분석 |
| --- | --- |
| `server.py` | Python 표준 HTTP 서버. `/api/render`에서 Pillow 카드 → FFmpeg H.264 MP4 출력. AI 모델 호출 없음. 로컬 바인딩 및 출력 파일명 제한 있음. 기존에는 국가·배우 입력이 자유 문자열이고 키 정책이 서버에서 검증되지 않았음. |
| `web/index.html` | CSS와 JavaScript가 내장된 한국어 UI. 6개국 각각 남녀 가상 배우 SVG 및 OS 음성 미리듣기. 3장면 대본은 고정 템플릿. 국가 언어는 음성 샘플에 적용되지만 전체 대본은 한국어. 작품 저장·TXT/JSON 내보내기와 스토리보드 API 연동 있음. |
| `index.html` | 위 웹 UI와 동일한 복사본. Python은 `web/index.html`을 제공함. 이번 변경에서도 두 파일을 동일하게 유지. |
| `requirements.txt` | `Pillow>=10,<13`만 필요. 실제 AI 추론 의존성은 없었음. 기본 앱의 가벼운 설치를 유지하고 Wan 의존성은 별도 Python 환경으로 분리. |
| `README.md` | 기존 기능·실행 및 스토리보드 한계를 설명. 실제 저장소에 없는 `.vscode/launch.json` 안내가 있었으므로 수정. |
| `exports/README.txt` | 생성 MP4 저장 경로 안내. |

기존 UI에서 183cm가 표시되었지만 API 정책은 아니었습니다. 서버에서 국가별 배우와 키를 결정하도록 수정했습니다. 프로필은 잠그지만 확산 모델이 생성한 영상에서 정확한 키·국적·배우 외형을 강제 검증하지는 않습니다.

## 구현 변경

- `drama/wan22.py`: 공식 TI2V-5B CLI의 텍스트 및 이미지 입력, 로컬 모델 경로·별도 Python, CUDA 확인, 입력 검증, 이미지 실디코딩, 시드·크기·프레임 제한, 오프라인 실행, 추론 제한 시간 및 실패 파일 정리.
- `drama/jobs.py`: 동시 GPU 작업 1개, 비동기 실행·진행/실패 조회, 메모리 작업 이력 최대 50개.
- `drama/pipeline.py`: 6개국 캐스팅, 서버 키 고정, 표정·연기 프롬프트 정책, TTS 및 립싱크 공급자 계약과 합성 연결 지점.
- `server.py`: AI 생성/작업 조회/준비 상태 API, JSON 객체 확인, 타 Origin의 POST 거부. 기존 스토리보드 유지.
- 두 HTML: 엔진 선택, 텍스트/I2V 업로드, 크기·프레임·시드, 상태 조회, 재접속 시 마지막 작업 조회, AI MP4 미리보기·다운로드, 한계 명시.
- `.gitignore`: 임시 작업, Python 캐시, 환경 설정 및 생성 MP4 제외.

공식 참고: [README](https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/README.md), [generate.py](https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/generate.py). A14B·S2V·Animate는 이번 실행 모듈의 대상이 아닙니다.

## 환경과 테스트 증거

- `/dev/nvidia*` 장치 없음, `nvidia-smi` 없음, PyTorch 미설치. CUDA 상태 `false`, 장치 수 0. **모델 다운로드 없음.**
- Python 3.12, Pillow 12.3.0, 로컬 FFmpeg/ffprobe 사용.
- `python -m unittest discover -s tests -v`: **11개 통과**. 6개국/키 정책, CLI 입력, 이미지 검증, GPU 부재 차단, 오프라인 추론 호출 계약, 실패 정리, 음성/립싱크 인터페이스 연결, 비동기 단일 작업 및 실패 처리, 실제 HTTP API, 실제 MP4 생성·다운로드·ffprobe 확인.
- Chromium + Playwright `tests/browser.cjs`: **통과**. 6개국 전환/캐스팅, 183cm 표시, 대본 3개 장면, AI 필드 전환, 이미지 미선택 오류, GPU 미준비 오류, 실제 3장면 스토리보드 생성과 9초 이상 MP4 브라우저 재생, JavaScript 예외 없음.
- Python compileall, `git diff --check`: 통과.

## 성공·미검증·미구현 구분

| 상태 | 항목 |
| --- | --- |
| 실제 실행 성공 | Python HTTP 서버, 웹 UI, 6개국 가상 배우 선택, 키 정책, 템플릿 대본, CPU 스토리보드 H.264 출력·브라우저 재생·다운로드 |
| 구현 및 계약 테스트 성공 / GPU 실증 미검증 | Wan2.2 텍스트→영상·이미지→영상 CLI 연결, 작업 상태 관리. 모의 추론은 실제 생성 품질이나 모델 호환성의 증거가 아님. |
| 구조 구현 / 실제 공급자 미구현 | 자연스러운 표정·여유 있는 연기 프롬프트, Dialogue·TTS·립싱크 확장 인터페이스 |
| 미구현 | TTS 음원의 MP4 포함, 립싱크 추론, 다장면 AI 자동 합성, 장면 간 얼굴 고정, AI 대본 작성·전체 대사 자동 번역 |

GPU 환경에서 남은 실증: 공식 의존성과 TI2V-5B 전체 체크포인트 준비 → `/api/capabilities` 확인 → T2V/I2V 각각 생성 → ffprobe와 재생 확인 → 인물 외형·표정·호흡 수동 평가. 24GB 이상 GPU를 공식 최소 안내로 참고하되 OOM 가능성은 실제 환경에서 검증해야 합니다. 본 보고서는 이 실증을 완료했다고 주장하지 않습니다.

작업 상태는 영구 저장하지 않습니다. 진행 중 서버 종료 시 복구·취소·자동 재시도는 지원하지 않습니다. 출력 파일은 사용자가 관리합니다. 음성 미리듣기는 기기에 해당 언어 음성이 있어야 하며 자동화 테스트는 실제 소리를 청취하지 않습니다.
