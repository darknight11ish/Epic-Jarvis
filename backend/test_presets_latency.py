"""The live contract endpoint must answer inside the apps' request timeouts.

`jarvis_hardware.detect()` measured ~10 s on the owner PC, and the contract
build used it twice, so `GET /api/work` took ~20.6 s and both apps' 20 s read
timed out ("Jarvis took too long..."). Cards do not change between requests,
so the module caches the detection for a short window. These checks pin the
cache, its copy isolation, the expiry path, and that a broken detector still
reads as "0 cards" rather than raising on every read.

THE EXPIRY PATH IS STALE-WHILE-REVALIDATE (2026-10-20). The cache used to
rebuild synchronously on the request thread when the 60-second window ran out,
so every minute one `GET /api/work` would block for the whole detection. The
expired-cache checks below use a detector that SLEEPS: the call must come back
in well under that sleep with the old snapshot, one background refresh must run,
a second request during it must start no second detector, and the startup
warm-up must do the first detection off the request path. The timing is never
the evidence on its own - the call counters and the in-flight peak are.
"""
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jarvis_presets as P  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name
          + (f"\n        {detail}" if detail and not cond else ""))


class _FakeHardware:
    """Counts detects so the cache is proved, not inferred from timing."""

    calls = 0

    @classmethod
    def detect(cls):
        cls.calls += 1
        return {"cards": [{"name": "Fake RTX", "vram_gib": 8.0, "uuid": "gpu-0"}]}


#: How long the deliberately slow detector sleeps. A stale-cache read that did
#: the detection itself could not come back inside a third of this.
SLOW_DETECT_SECONDS = 1.0

#: The most a stale-cache answer may take. The slow detector is asleep for
#: 1.0 s, so this only passes when the request thread does NOT detect.
STALE_BUDGET_MS = 200.0


class _SlowHardware:
    """A detector slow enough that doing it on the caller's thread is visible.

    It counts its calls AND how many ran at once, so both halves of the
    stale-while-revalidate rule are proved without trusting a stopwatch: a
    stale answer arrives while the sleep is still running, and a second request
    during that sleep starts no second detector. The card it reports is named
    with its own call number, so "the old snapshot was served" is checkable.
    """

    calls = 0
    running = 0
    most_at_once = 0
    lock = threading.Lock()

    @classmethod
    def reset(cls):
        with cls.lock:
            cls.calls = 0
            cls.running = 0
            cls.most_at_once = 0

    @classmethod
    def detect(cls):
        with cls.lock:
            cls.calls += 1
            number = cls.calls
            cls.running += 1
            cls.most_at_once = max(cls.most_at_once, cls.running)
        try:
            time.sleep(SLOW_DETECT_SECONDS)
        finally:
            with cls.lock:
                cls.running -= 1
        return {"cards": [{"name": f"Fake RTX #{number}", "vram_gib": 8.0,
                           "uuid": f"gpu-{number}"}]}


def _swap_hardware(fake):
    """Put `fake` on sys.modules as jarvis_hardware; return what was there."""
    real = sys.modules.get("jarvis_hardware")
    sys.modules["jarvis_hardware"] = fake
    return real


def _restore_hardware(real):
    if real is None:
        sys.modules.pop("jarvis_hardware", None)
    else:
        sys.modules["jarvis_hardware"] = real


def _wait_until(predicate, timeout=5.0):
    """Wait for a background refresh to reach a state. True when it did."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _settle():
    """Let any refresh this suite started finish, so the next check is clean."""
    _wait_until(lambda: not P._DETECT_CACHE.get("in_flight"), timeout=5.0)


def _expire_the_snapshot():
    """Age the cached snapshot past its window - exactly the 60-second expiry,
    without sleeping 60 seconds. This suite is the cache's own, so it reaches
    into the cache it is checking."""
    P._DETECT_CACHE["at"] = time.monotonic() - P.DETECT_CACHE_SECONDS - 1.0



def t_a_second_read_reuses_the_detection_and_copies_its_result():
    real = sys.modules.get("jarvis_hardware")
    sys.modules["jarvis_hardware"] = _FakeHardware
    P._clear_detect_cache()
    _FakeHardware.calls = 0
    try:
        first = P.hardware_block()
        second = P.hardware_block()
        check("two reads inside the window detect the cards once",
              _FakeHardware.calls == 1, _FakeHardware.calls)
        check("the cached block still says how many cards and where from",
              second["detected"]["count"] == 1
              and second["detected"]["cards"][0]["name"] == "Fake RTX"
              and second["detected"]["source"] == "jarvis_hardware.detect()",
              second["detected"])
        first["detected"]["cards"][0]["name"] = "mutated by a caller"
        third = P.hardware_block()
        check("a caller mutating the returned cards cannot corrupt the cache",
              third["detected"]["cards"][0]["name"] == "Fake RTX",
              third["detected"])
        P._clear_detect_cache()
        P.hardware_block()
        check("clearing the cache makes the next read detect again",
              _FakeHardware.calls == 2, _FakeHardware.calls)
    finally:
        if real is None:
            del sys.modules["jarvis_hardware"]
        else:
            sys.modules["jarvis_hardware"] = real
        P._clear_detect_cache()


def t_live_status_uses_the_same_cache_and_keeps_the_contract_shape():
    real = sys.modules.get("jarvis_hardware")
    sys.modules["jarvis_hardware"] = _FakeHardware
    P._clear_detect_cache()
    _FakeHardware.calls = 0
    try:
        first = P.live_status()
        second = P.live_status()
        check("one contract build detects once and the next build reuses it",
              _FakeHardware.calls == 1, _FakeHardware.calls)
        check("the cached live answer still has the nested hardware and lane",
              isinstance(first.get("hardware"), dict)
              and "detected" in first["hardware"]
              and "questionnaire" in first["hardware"]
              and "lane" in first and "lane_status" in first
              and "questionnaire" not in first,
              sorted(first))
        check("the two answers are the same contract",
              first["presets"] == second["presets"]
              and first["hardware"] == second["hardware"])
    finally:
        if real is None:
            del sys.modules["jarvis_hardware"]
        else:
            sys.modules["jarvis_hardware"] = real
        P._clear_detect_cache()


def t_a_broken_detector_is_reported_as_zero_cards_and_cached():
    real = sys.modules.get("jarvis_hardware")
    sys.modules["jarvis_hardware"] = SimpleNamespace(
        detect=lambda: (_ for _ in ()).throw(RuntimeError("no driver")))
    P._clear_detect_cache()
    try:
        first = P.hardware_block()["detected"]
        second = P.hardware_block()["detected"]
        check("a detector that raises reads as zero cards, not an error",
              first["count"] == 0 and first["cards"] == [], first)
        check("the zero-card answer is cached too",
              second == first, (first, second))
    finally:
        if real is None:
            del sys.modules["jarvis_hardware"]
        else:
            sys.modules["jarvis_hardware"] = real
        P._clear_detect_cache()


def t_an_expired_snapshot_answers_at_once_and_refreshes_in_the_background():
    """The 60-second expiry must not block the request that finds it expired.

    Before this was stale-while-revalidate, this check failed on both counts:
    the call waited for the whole detection and returned the NEW snapshot. With
    it, the call returns the OLD snapshot inside STALE_BUDGET_MS and the new one
    arrives from one background refresh afterwards.
    """
    real = _swap_hardware(_SlowHardware)
    _SlowHardware.reset()
    P._clear_detect_cache()
    _settle()
    try:
        # The startup warm-up fills the cache before the first request needs it.
        check("the startup warm-up starts the first detection in the background",
              P._refresh_detect_cache_async() is True)
        check("...and a second call while it runs starts no second detector",
              P._refresh_detect_cache_async() is False)
        warm = _wait_until(lambda: P._DETECT_CACHE.get("value") is not None)
        check("the startup detection completes and fills the cache",
              warm and _SlowHardware.calls == 1, _SlowHardware.calls)
        served_warm = P.hardware_block()["detected"]
        check("a warm cache is served without detecting again",
              _SlowHardware.calls == 1
              and served_warm["cards"][0]["name"] == "Fake RTX #1",
              (served_warm, _SlowHardware.calls))

        _expire_the_snapshot()
        started = time.monotonic()
        stale = P.hardware_block()["detected"]
        elapsed_ms = (time.monotonic() - started) * 1000.0
        check(f"an expired-cache read returns in under {STALE_BUDGET_MS:.0f} ms",
              elapsed_ms < STALE_BUDGET_MS, f"{elapsed_ms:.1f} ms")
        check("...with the OLD snapshot (the caller is not made to wait for a new one)",
              stale["cards"][0]["name"] == "Fake RTX #1", stale)
        check("...and exactly ONE background detection was started",
              _wait_until(lambda: _SlowHardware.calls == 2, timeout=0.5),
              _SlowHardware.calls)
        fresh = _wait_until(
            lambda: P._DETECT_CACHE.get("value", {}).get("cards", [{}])[0].get(
                "name") == "Fake RTX #2")
        check("the background refresh completes and replaces the snapshot", fresh,
              P._DETECT_CACHE.get("value"))
        check("the next read is the refreshed snapshot, still without detecting",
              P.hardware_block()["detected"]["cards"][0]["name"] == "Fake RTX #2"
              and _SlowHardware.calls == 2, _SlowHardware.calls)
    finally:
        _restore_hardware(real)
        _settle()
        P._clear_detect_cache()


def t_reads_during_a_refresh_start_no_second_refresh():
    """One refresh in flight, however many requests arrive while it runs."""
    real = _swap_hardware(_SlowHardware)
    _SlowHardware.reset()
    P._clear_detect_cache()
    _settle()
    try:
        P._refresh_detect_cache_async()
        _wait_until(lambda: P._DETECT_CACHE.get("value") is not None)
        _expire_the_snapshot()
        names = [P.hardware_block()["detected"]["cards"][0]["name"]
                 for _ in range(3)]
        check("three expired-cache reads all answer straight away with the old snapshot",
              names == ["Fake RTX #1"] * 3, names)
        check("...and they started exactly one refresh between them",
              _SlowHardware.calls == 2, _SlowHardware.calls)
        check("no two card detections ever ran at the same time",
              _wait_until(lambda: _SlowHardware.running == 0 and
                          _SlowHardware.calls == 2)
              and _SlowHardware.most_at_once == 1, _SlowHardware.most_at_once)
    finally:
        _restore_hardware(real)
        _settle()
        P._clear_detect_cache()


def t_install_warms_the_cache_once_when_the_real_hud_starts():
    """The startup refresh is wired into install(), and NOT into a test run."""
    real = _swap_hardware(_SlowHardware)
    _SlowHardware.reset()
    P._clear_detect_cache()
    _settle()
    real_warm = P._warm_on_startup
    P._warm_on_startup = lambda: True
    try:
        check("the startup warm-up is off in a test process",
              real_warm() is False, real_warm)

        class Handler:
            def _send(self, code, body):
                return {"code": code, "out": body}

            def do_GET(self):
                return None

            def do_POST(self):
                return None

        banner = P.install(Handler, origin_ok=lambda h: True,
                           token_ok=lambda h: True,
                           read_body=lambda h: "{}")
        check("installing the preset routes still answers with its banner",
              "presets" in banner, banner)
        check("...and starts exactly one card detection in the background",
              _wait_until(lambda: P._DETECT_CACHE.get("value") is not None)
              and _SlowHardware.calls == 1, _SlowHardware.calls)
        check("...whose result is the cached snapshot a request then gets",
              P.hardware_block()["detected"]["cards"][0]["name"] == "Fake RTX #1",
              P._DETECT_CACHE.get("value"))
    finally:
        P._warm_on_startup = real_warm
        _restore_hardware(real)
        _settle()
        P._clear_detect_cache()


def main() -> int:
    t_a_second_read_reuses_the_detection_and_copies_its_result()
    t_live_status_uses_the_same_cache_and_keeps_the_contract_shape()
    t_a_broken_detector_is_reported_as_zero_cards_and_cached()
    t_an_expired_snapshot_answers_at_once_and_refreshes_in_the_background()
    t_reads_during_a_refresh_start_no_second_refresh()
    t_install_warms_the_cache_once_when_the_real_hud_starts()
    P._clear_detect_cache()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
