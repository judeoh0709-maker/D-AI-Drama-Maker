"""One inference at a time, bounded in-memory history. Restart clears job status."""
import threading
import uuid
from datetime import datetime, timezone


class Busy(RuntimeError):
    pass


class Jobs:
    def __init__(self, engine, exports):
        self.engine, self.exports = engine, exports
        self.lock = threading.Lock()
        self.history = {}
        self.active = False

    def submit(self, spec, image):
        with self.lock:
            if self.active:
                raise Busy('이미 영상 생성 중입니다. 완료 후 다시 시도하세요.')
            self.active = True
            job = uuid.uuid4().hex[:12]
            while len(self.history) >= 50:
                del self.history[next(iter(self.history))]
            self.history[job] = dict(id=job, status='queued', cast=spec['cast'],
                                     createdAt=datetime.now(timezone.utc).isoformat(),
                                     audio=False, lipSync=False)
        threading.Thread(target=self._run, args=(job, spec, image), daemon=True).start()
        return job

    def get(self, job):
        with self.lock:
            return dict(self.history[job]) if job in self.history else None

    def _run(self, job, spec, image):
        output = self.exports / f'{job}.mp4'
        try:
            with self.lock:
                self.history[job]['status'] = 'running'
            self.engine.generate(spec, image, output)
            with self.lock:
                self.history[job].update(status='succeeded', videoUrl=f'/exports/{job}.mp4')
        except Exception as exc:
            output.unlink(missing_ok=True)
            with self.lock:
                self.history[job].update(status='failed', error=str(exc)[:500])
        finally:
            with self.lock:
                self.active = False
