"""Contracts for future local voice and lip-sync providers.

Browser speech preview is intentionally separate from exported audio.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

COUNTRIES = {
    '한국': ('Korean', 'ko-KR', '서준', '하린'),
    '일본': ('Japanese', 'ja-JP', '렌', '아오이'),
    '미국': ('American', 'en-US', 'Ethan', 'Olivia'),
    '영국': ('British', 'en-GB', 'Oliver', 'Amelia'),
    '프랑스': ('French', 'fr-FR', 'Louis', 'Camille'),
    '이탈리아': ('Italian', 'it-IT', 'Luca', 'Giulia'),
}


def casting(data):
    country = data.get('country', '한국')
    if country not in COUNTRIES:
        raise ValueError('지원하지 않는 국가입니다.')
    nationality, language, male, female = COUNTRIES[country]
    lead = data.get('maleLead', {})
    if not isinstance(lead, dict):
        raise ValueError('maleLead는 객체여야 합니다.')
    # The server owns the casting policy, including JSON/API callers.
    if lead.get('heightCm', 183) != 183:
        raise ValueError('남자 주인공 키는 183cm로 고정됩니다 (최소 180cm).')
    return dict(country=country, nationality=nationality, language=language,
                maleLead=dict(name=male, heightCm=183, minHeightCm=180, locked=True),
                femaleLead=dict(name=female, heightCm=168))


@dataclass(frozen=True)
class Performance:
    expression: str = 'subtle micro-expressions, natural blinking and eye contact'
    acting: str = 'relaxed acting, natural pauses, unhurried breathing, continuous gestures'
    identity: str = 'consistent character appearance throughout the shot'


@dataclass(frozen=True)
class Dialogue:
    text: str
    language: str
    speaker: str
    pause_after_ms: int = 500


class VoiceProvider(Protocol):
    def synthesize(self, dialogue: Dialogue, output: Path) -> Path: ...


class LipSyncProvider(Protocol):
    def synchronize(self, video: Path, audio: Path, output: Path) -> Path: ...


class PostProduction:
    """Inject providers explicitly; never silently claim silent video is voiced."""
    def __init__(self, voice: VoiceProvider, lip_sync: LipSyncProvider):
        self.voice, self.lip_sync = voice, lip_sync

    def process(self, video: Path, dialogue: Dialogue, output: Path) -> Path:
        audio = self.voice.synthesize(dialogue, output.with_suffix('.wav'))
        return self.lip_sync.synchronize(video, audio, output)
