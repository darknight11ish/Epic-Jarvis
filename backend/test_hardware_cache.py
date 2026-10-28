"""test_hardware_cache.py - the hardware detector's cache is not born expired.

WHY. `jarvis_hardware.detect()` is the one measurement every card-aware screen
reads (the Hardware page, the second-card panel, and now the model advisor's
GET /api/models/recommendations). Its `_detect()` probe can legitimately take
seconds on this PC - one registry read has a 10 s timeout - and the cache
timestamp was taken BEFORE the probe ran, so on a slow probe the cached value
was already older than `_CACHE_SECONDS` the moment it was stored: every later
call in the same second paid the whole probe again. Measured 2026-10-28 on the
owner's live backend: three consecutive `detect()` calls each took ~10.1 s.

The fix is one line (stamp the cache AFTER the probe returns); these checks
pin it and BITE on the old code: with the old stamping, the second call in
`t_a_slow_probe_is_cached_after_it_returns` probes again and the count check
fails.

    python3 test_hardware_cache.py
"""

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_hardware as H  # noqa: E402


def main():
    passed = failed = 0

    def check(what, ok, detail=""):
        nonlocal passed, failed
        print(("ok    " if ok else "FAIL  ") + what)
        if not ok:
            print("      " + str(detail))
            failed += 1
        else:
            passed += 1

    old_detect = H._detect
    old_cache = H._CACHE_SECONDS
    old_value = H._DET["value"]
    old_at = H._DET["at"]
    calls = {"n": 0}

    def slow(fresh=False):  # stands in for a probe that takes real time
        calls["n"] += 1
        time.sleep(0.06)
        return {"cards": [{"name": "a fake card", "total_gib": 4.0}],
                "planned": [], "log": None, "sources": {},
                "found": "one fake card"}

    try:
        H._detect = slow
        H._CACHE_SECONDS = 0.5
        H._DET.update(value=None, at=0.0)
        first = H.detect()
        second = H.detect()
        check("the slow probe runs exactly ONCE for two calls inside the TTL",
              calls["n"] == 1, calls)
        check("the warm call returns the same value", second is first)
        check("... and the value really carries the probe's cards",
              second["cards"][0]["name"] == "a fake card", second)
        time.sleep(0.6)
        third = H.detect()
        check("after the TTL it probes again", calls["n"] == 2, calls)
        check("... and the new probe's value is served", third["cards"][0]["name"] == "a fake card")
        check("a fresh=True read always probes", (H.detect(fresh=True), calls["n"] == 3)[1], calls)
    finally:
        H._detect = old_detect
        H._CACHE_SECONDS = old_cache
        H._DET.update(value=old_value, at=old_at)

    print(f"\n{passed} passed, {failed} failed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
