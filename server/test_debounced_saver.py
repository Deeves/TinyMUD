import time
from debounced_saver import DebouncedSaver


def test_debounced_saver_coalesces_and_flushes():
    calls = []
    def _save():
        calls.append(time.time())

    # Use a tiny debounce interval to keep test fast
    s = DebouncedSaver(_save, interval_ms=50)

    # Burst of debounces should coalesce to a single save after the interval
    s.debounce()
    time.sleep(0.01)
    s.debounce()
    time.sleep(0.01)
    s.debounce()

    # Wait a bit longer than interval for background flush
    time.sleep(0.12)

    # Should have flushed once
    assert len(calls) == 1

    # A subsequent debounce should schedule again
    s.debounce()
    time.sleep(0.12)
    assert len(calls) == 2

    # Explicit flush should call immediately even if no debounce is armed
    s.flush()
    assert len(calls) == 3
