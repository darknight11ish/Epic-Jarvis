#!/usr/bin/env python3
"""Writes web search's contract file for both apps, and checks it.

    python3 tools/gen_web_search_cases.py            # write both copies
    python3 tools/gen_web_search_cases.py --check    # compare only

What GET /api/search, POST /api/search/settings and POST /api/search/test
really answer (backend/jarvis_search.py), in named situations, made by the
real code - nothing is written by hand:

    jarvis-desktop/tests/fixtures/web-search-cases.json
    jarvis-client/app/src/test/resources/contract/web-search-cases.json

(byte-identical). Both apps build against it: the desktop's Rust and
JavaScript tests, and the phone's WebSearchTest.

The keys are fakes in memory (no Credential Manager), the search answers
come from a stand-in (no network), and whether `ddgs` is installed is fixed
to "no", so the file is the same on every machine.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
_TMP = tempfile.mkdtemp(prefix="jarvis-ws-cases-")
import os  # noqa: E402
os.environ["OPENJARVIS_CONFIG_DIR"] = _TMP
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import jarvis_search as WS  # noqa: E402

DESKTOP = ROOT / "jarvis-desktop" / "tests" / "fixtures" / "web-search-cases.json"
PHONE = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
         / "web-search-cases.json")
COPIES = (DESKTOP, PHONE)

# A fake key, built by concatenation; it never appears in the output.
_FAKE = "tv" + "ly-" + "cases" + "0123456789"


class _Store:
    DATA: dict = {}

    def __init__(self, target):
        self.target = target

    def read(self):
        return _Store.DATA.get(self.target)

    def write(self, v):
        _Store.DATA[self.target] = v

    def delete(self):
        _Store.DATA.pop(self.target, None)


def _fresh(**settings):
    WS._reset_for_tests()
    _Store.DATA.clear()
    p = WS.settings_path()
    if p.exists():
        p.unlink()
    if settings:
        p.parent.mkdir(parents=True, exist_ok=True)
        base = {"provider": "searxng", "searxng_url": WS.DEFAULT_SEARXNG_URL,
                "ask_every_time": False}
        base.update(settings)
        p.write_text(json.dumps(base), encoding="utf-8")


def _answer(status, body):
    def fake(req, *, local):
        return status, body
    return fake


def cases() -> dict:
    WS._STORE_FACTORY = _Store
    WS._ddgs_installed = lambda: False
    out = {}
    _fresh()
    out["default"] = WS.view()
    _fresh(provider="tavily")
    _Store.DATA[WS.KEY_TARGETS["tavily"]] = _FAKE
    out["tavily_key_saved"] = WS.view()
    _fresh(provider="exa", ask_every_time=True)
    out["exa_no_key_ask_every_time"] = WS.view()
    # A settings file from before Brave was removed (2026-09-25).
    _fresh(provider="brave")
    out["brave_saved_no_longer_offered"] = WS.view()
    out["test_brave_no_longer_offered"] = WS.handle_test({})
    _fresh(provider="duckduckgo")
    out["duckduckgo_not_installed"] = WS.view()
    _fresh()
    WS.settings_path().write_text("{damaged", encoding="utf-8")
    out["damaged"] = WS.view()
    _fresh()
    out["post_provider"] = WS.handle_settings({"provider": "duckduckgo"})
    _fresh()
    out["post_bad_address"] = WS.handle_settings({"searxng_url": "https://searx.example.com"})
    _fresh()
    out["post_address"] = WS.handle_settings({"searxng_url": "http://192.168.1.20:8888"})
    _fresh()
    out["post_ask_on"] = WS.handle_settings({"ask_every_time": True})
    WS._reset_for_tests()
    saved_spawn = WS._spawn
    WS._spawn = lambda fn: None
    out["post_ask_off"] = WS.handle_settings({"ask_every_time": False})
    WS._spawn = saved_spawn
    _fresh()
    WS._HTTP = _answer(200, json.dumps({"results": [
        {"url": "https://example.org/1", "title": "One", "content": "a"},
        {"url": "https://example.org/2", "title": "Two", "content": "b"}]}).encode())
    out["test_works"] = WS.handle_test({})
    WS._HTTP = _answer(403, b"Forbidden")
    out["test_json_off"] = WS.handle_test({})

    def refused(req, *, local):
        raise ConnectionRefusedError(111, "Connection refused")
    WS._HTTP = refused
    out["test_not_running"] = WS.handle_test({})
    WS._HTTP = None
    _fresh(provider="tavily")
    out["test_key_missing"] = WS.handle_test({})
    _fresh()
    # Timestamps would differ from run to run; none of these carry one
    # except `last`, which no case here sets.
    return {"cases": {k: {"status": v[0], "body": v[1]} if isinstance(v, tuple) else v
                      for k, v in out.items()},
            "why": dict(WS.WHY), "labels": dict(WS.LABEL), "left_out": WS.LEFT_OUT,
            "providers": list(WS.PROVIDERS), "default": WS.DEFAULT_PROVIDER}


def render() -> str:
    text = json.dumps(cases(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    assert _FAKE not in text, "a key reached the contract file"
    return text


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        stale = []
        for path in COPIES:
            have = path.read_text(encoding="utf-8") if path.is_file() else ""
            if have.replace("\r\n", "\n") != text:
                stale.append(path)
        for path in stale:
            print(f"{path.relative_to(ROOT)} is out of date: run "
                  f"python3 tools/gen_web_search_cases.py")
        if stale:
            return 1
        print("web-search-cases.json matches the producer (desktop and phone copies).")
        return 0
    for path in COPIES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
