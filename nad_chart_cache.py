"""Bounded, persistent chart snapshots. Display data only, never order quotes."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor


class ChartCache:
    def __init__(self, path, clock=time.time):
        self.path, self.clock = path, clock
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='nad-chart')
        self.values, self.active, self.failures, self.jobs = {}, set(), {}, {}
        self.loaded = False

    def _load(self):
        if self.loaded:
            return
        self.loaded = True
        try:
            if self.path.stat().st_size > 8 * 1024 * 1024:
                return
            values = json.loads(self.path.read_text())
            self.values = {key: value for key, value in list(values.items())[-128:]
                           if 0 <= self.clock() - value['fetchedAt'] <= 900}
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            self.values = {}

    def _refresh(self, key, fetch):
        try:
            value = fetch()
            with self.lock:
                self.values.pop(key, None)
                self.values[key] = value
                self.failures.pop(key, None)
                while len(self.values) > 128:
                    self.values.pop(next(iter(self.values)))
                try:
                    temporary = self.path.with_suffix('.tmp')
                    temporary.write_text(json.dumps(self.values, separators=(',', ':')))
                    temporary.replace(self.path)
                except OSError:
                    pass  # A read-only/full disk must not discard a valid chart.
        except Exception:
            with self.lock:
                self.failures[key] = self.clock()
                while len(self.failures) > 128:
                    self.failures.pop(next(iter(self.failures)))
        finally:
            with self.lock:
                self.active.discard(key)
                self.jobs.pop(key, None)

    def get(self, token, interval, fetch, wait=True):
        key = token + ':' + interval
        with self.lock:
            self._load()
            value = self.values.get(key)
            age = self.clock() - value['fetchedAt'] if value else float('inf')
            usable = value is not None and 0 <= age <= 900
            fresh = usable and age < 90
            retry = self.failures.get(key, 0) + 30 - self.clock()
            if not fresh and key not in self.active and retry <= 0 and len(self.active) < 8:
                self.active.add(key)
                self.jobs[key] = self.pool.submit(self._refresh, key, fetch)
            job = self.jobs.get(key)
            result = dict(value) if usable else dict(token=token, interval=interval,
                candles=[], source='nad.fun', fetchedAt=None)
            result.update(stale=usable and not fresh, refreshing=key in self.active)
            if not fresh:
                result['retryAfter'] = max(2, int(retry) + 1)
            if retry > 0:
                result['error'] = 'Chart update delayed. Try again shortly.'
        # Existing native clients expect candles on their first request. Only a
        # cold key joins its own fetch; no shared cache lock is held while waiting.
        if wait and not usable and job is not None:
            try:
                job.result(timeout=90)
            except Exception:
                pass
            return self.get(token, interval, fetch, wait=False)
        return result
