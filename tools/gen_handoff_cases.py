#!/usr/bin/env python3
"""Writes the "Solve it here" contract file for both apps, and checks it.

    python3 tools/gen_handoff_cases.py            # write both copies
    python3 tools/gen_handoff_cases.py --check    # compare only

What the routes of backend/jarvis_handoff.py (answered by
jarvis_chatbot_routes.py) really answer, in named situations, made by the
real code with a stand-in browser window (it records calls and hands back a
tiny made-up JPEG) and a clock moved by hand - nothing is written by hand:

    jarvis-desktop/tests/fixtures/handoff-cases.json
    jarvis-client/app/src/test/resources/contract/handoff-cases.json

(byte-identical). The phone's HandoffTest and the desktop's
tests/handoff.mjs build against it, and check their words against `words`
(jarvis_handoff.WORDS). Hand-off ids are numbered here, so the file is the
same on every run.
"""
import json
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
for p in (BACKEND, BACKEND / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
_TMP = Path(tempfile.mkdtemp(prefix="jarvis-handoff-cases-"))
_fw = types.ModuleType("jarvis_framework")
_fw.CONFIG_DIR = _TMP
_fw.LOG_DIR = _TMP
_fw.load_framework = lambda: {}
_fw.audit_log = lambda *a, **k: None
_fw.action_tier = lambda action: "ask"
sys.modules["jarvis_framework"] = _fw

import jarvis_chatbot as CB  # noqa: E402
import jarvis_chatbot_routes as R  # noqa: E402
import jarvis_handoff as HO  # noqa: E402
import jarvis_handoff_mode as HM  # noqa: E402
import jarvis_support as SUP  # noqa: E402

COPIES = (ROOT / "jarvis-desktop" / "tests" / "fixtures" / "handoff-cases.json",
          ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "contract"
          / "handoff-cases.json")

_N = [0]


def _hex(n: int) -> str:
    _N[0] += 1
    return f"{_N[0]:0{2 * n}x}"


HO.secrets = types.SimpleNamespace(token_hex=_hex)


def tiny_jpeg(w: int, h: int) -> bytes:
    sof = b"\xff\xc0\x00\x11\x08" + h.to_bytes(2, "big") + w.to_bytes(2, "big") \
        + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    return b"\xff\xd8" + sof + b"\xff\xd9"


class _Page:
    def __init__(self, url):
        self.url = url
        self.mouse = types.SimpleNamespace(click=lambda x, y: None, wheel=lambda x, y: None)
        self.keyboard = types.SimpleNamespace(type=lambda t: None, press=lambda k: None)

    def screenshot(self, **kw):
        return tiny_jpeg(390, 300)


class _Window:
    def __init__(self, url, hosts, sign_in=()):
        self._page = _Page(url)
        self.chat_hosts = hosts
        self.sign_in_hosts = sign_in

    def _page_alive(self):
        return True

    def _call(self, fn, timeout):
        return fn()


class _Clock:
    t = 1000.0

    def __call__(self):
        return self.t


CLOCK = _Clock()
TIER = CB.Tier("one_card", "http://127.0.0.1:11434", "m", 4096)


def fresh():
    with CB._LOCK:
        CB._SESSIONS.clear()
    SUP._reset_for_tests()
    CLOCK.t = 1000.0
    HO._reset_for_tests(clock=CLOCK)


def chatbot(code="captcha", state="paused"):
    s = CB.Session(id="chat_000000000001", chatbot="gemini_web", goal="g",
                   limits=CB.Limits(5, 10), tier=TIER, state=state, paused_code=code)
    s.adapter = _Window("https://gemini.google.com/app", ("gemini.google.com",),
                        ("accounts.google.com",))
    with CB._LOCK:
        CB._SESSIONS[s.id] = s
    return s


def support(code="login"):
    c = SUP.SupportChat(id="sup_000000000001", company="groupon", company_name="Groupon",
                        help_url="https://www.groupon.com/help", hosts=("www.groupon.com",),
                        goal="g", details=(), limits=SUP.Limits(5, 10, 10), tier=TIER,
                        state="paused", paused_code=code)
    c.widget = _Window("https://www.groupon.com/help", ("www.groupon.com",))
    with SUP._LOCK:
        SUP._CHATS[c.id] = c
    return c


def answer(pair):
    code, body = pair
    return {"code": code, "body": body}


def offer():
    return R.handle_get("")[1]["handoff"]


def cases() -> dict:
    out = {"words": dict(HO.WORDS), "ended_words": dict(HO.ENDED),
           "stuck_words": dict(HO.STUCK), "keys": list(HO.KEYS),
           "owner_codes": list(HO.OWNER_CODES),
           # The owner's setting of 2026-10-08 ("make this a setting for both
           # options with 1 as the default"): the two values, the default, and
           # every word both apps show for it. Read from the real module, so
           # neither app can carry a different pair of names or a different
           # default.
           "mode_words": dict(HM.WORDS), "modes": list(HM.MODES),
           "mode_default": HM.DEFAULT, "mode_patient": HM.KEEP_OFFERING,
           "limits": {"frames_per_s": HO.FRAMES_PER_S,
                      "idle_s": HO.idle_seconds(), "ceiling_s": HO.ceiling_seconds(),
                      "text_most": HO.TEXT_MOST, "scroll_most": HO.SCROLL_MOST},
           "routes": {"start": R.HANDOFF_START_ROUTE, "frame": R.HANDOFF_FRAME_ROUTE,
                      "input": R.HANDOFF_INPUT_ROUTE, "end": R.HANDOFF_END_ROUTE,
                      "mode": R.HANDOFF_MODE_ROUTE}}
    fresh()
    out["offer_none"] = offer()
    out["start_nothing"] = answer(R.handle_post(R.HANDOFF_START_ROUTE,
                                                {"kind": "chatbot", "id": "chat_0000000000ff"}))
    chatbot(code="blocked")
    out["offer_other_pause"] = offer()
    fresh()
    s = chatbot("captcha")
    out["offer_captcha"] = offer()
    started = R.handle_post(R.HANDOFF_START_ROUTE, {"kind": "chatbot", "id": s.id})
    out["start"] = answer(started)
    hid = started[1]["handoff"]
    out["offer_active"] = offer()
    out["frame"] = answer(R.handle_frame("h=" + hid))
    out["frame_too_soon"] = answer(R.handle_frame("h=" + hid))
    out["tap"] = answer(R.handle_post(R.HANDOFF_INPUT_ROUTE,
                                      {"h": hid, "type": "tap", "x": 0.5, "y": 0.25}))
    out["text"] = answer(R.handle_post(R.HANDOFF_INPUT_ROUTE,
                                       {"h": hid, "type": "text", "text": "abc"}))
    out["key_refused"] = answer(R.handle_post(R.HANDOFF_INPUT_ROUTE,
                                              {"h": hid, "type": "key", "key": "F5"}))
    s.state = "running"
    out["input_after_resume"] = answer(R.handle_post(R.HANDOFF_INPUT_ROUTE,
                                                     {"h": hid, "type": "key", "key": "Enter"}))
    out["offer_after_resume"] = offer()
    fresh()
    s = chatbot("login")
    hid = R.handle_post(R.HANDOFF_START_ROUTE, {"kind": "chatbot", "id": s.id})[1]["handoff"]
    s.adapter._page.url = "https://somewhere.example/"
    out["frame_left"] = answer(R.handle_frame("h=" + hid))
    fresh()
    s = chatbot("unusual")
    hid = R.handle_post(R.HANDOFF_START_ROUTE, {"kind": "chatbot", "id": s.id})[1]["handoff"]
    out["end"] = answer(R.handle_post(R.HANDOFF_END_ROUTE, {"h": hid}))
    out["frame_after_end"] = answer(R.handle_frame("h=" + hid))
    fresh()
    support("login")
    out["offer_support"] = offer()
    # ---- the owner's setting (2026-10-08) --------------------------------
    # "Stop early" is the default: nobody looking for about a minute ends the
    # hand-off AND the status carries the PC's own line naming the window
    # Jarvis is stuck on. Both apps show that line word for word, so it is
    # worked out here from the real code, not typed twice.
    fresh()
    s = chatbot("captcha")
    started = R.handle_post(R.HANDOFF_START_ROUTE, {"kind": "chatbot", "id": s.id})
    hid = started[1]["handoff"]
    out["mode_default_offer"] = offer()
    out["mode_default_start"] = answer(started)
    CLOCK.t += HM.idle_seconds() + 1
    out["mode_idle_frame"] = answer(R.handle_frame("h=" + hid))
    out["mode_idle_offer"] = offer()
    # The setting's own route, as both apps read it (GET /api/chatbot/handoff_mode).
    out["mode_route_get"] = {"route": R.HANDOFF_MODE_ROUTE, "body": HM.view()}
    fresh()
    return out


def render() -> str:
    _N[0] = 0
    return json.dumps(cases(), indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        bad = [str(p.relative_to(ROOT)) for p in COPIES
               if not p.is_file() or p.read_text(encoding="utf-8") != text]
        if bad:
            print("out of date (run python3 tools/gen_handoff_cases.py): " + ", ".join(bad))
            return 1
        print("handoff cases: both copies up to date")
        return 0
    for p in COPIES:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
