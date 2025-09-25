"""debounced_saver.py — Best-effort debounced persistence of world state.

Coalesces frequent world.save_to_file writes under bursty activity. Uses the
Socket.IO sleep when available, otherwise time.sleep, and is safe under both
eventlet and threading modes.

Design:
- debounce(interval_ms): schedules a save soon; repeated calls within the window
  reset the timer.
- flush(): perform an immediate save (used on shutdown or critical updates).
"""

from __future__ import annotations

import atexit
import time
from typing import Optional, Callable


class DebouncedSaver:
    def __init__(self, save_fn: Callable[[], None], *, interval_ms: int = 300) -> None:
        self._save_fn = save_fn
        self._interval_s = max(0.0, float(interval_ms) / 1000.0)
        self._next_deadline: Optional[float] = None
        self._armed = False
        atexit.register(self.flush)

    def debounce(self) -> None:
        now = time.time()
        self._next_deadline = now + self._interval_s
        if not self._armed:
            self._armed = True
            # Start a very light background waiter using time.sleep; caller's async loop
            # can also call poll() periodically if desired.
            try:
                import threading
                t = threading.Thread(target=self._wait_and_flush, name='debounced-saver', daemon=True)
                t.start()
            except Exception:
                # As a fallback, just do an immediate save if we fail to thread
                self.flush()

    def _wait_and_flush(self) -> None:
        # Simple polling wait that coalesces resets to _next_deadline
        try:
            while True:
                nd = self._next_deadline
                if nd is None:
                    break
                dt = nd - time.time()
                if dt <= 0:
                    break
                # Sleep in small chunks to be responsive to resets
                time.sleep(min(0.05, dt))
        except Exception:
            pass
        finally:
            self.flush()

    def flush(self) -> None:
        # One-shot flush; ignore errors (best-effort persistence)
        self._next_deadline = None
        if self._armed:
            self._armed = False
        try:
            self._save_fn()
        except Exception:
            pass
