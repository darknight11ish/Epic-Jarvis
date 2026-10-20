"""The live contract endpoint must answer inside the apps' request timeouts.

`jarvis_hardware.detect()` measured ~10 s on the owner PC, and the contract
build used it twice, so `GET /api/work` took ~20.6 s and both apps' 20 s read
timed out ("Jarvis took too long..."). Cards do not change between requests,
so the module caches the detection for a short window. These checks pin the
cache, its copy isolation, the expiry path, and that a broken detector still
reads as "0 cards" rather than raising on every read.
"""
import sys
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


def main() -> int:
    t_a_second_read_reuses_the_detection_and_copies_its_result()
    t_live_status_uses_the_same_cache_and_keeps_the_contract_shape()
    t_a_broken_detector_is_reported_as_zero_cards_and_cached()
    P._clear_detect_cache()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
