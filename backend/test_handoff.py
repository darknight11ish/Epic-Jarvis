"""Tests for jarvis_handoff.py - "Solve it here": a captcha or sign-in page
handed to the owner's phone (the owner's decision of 2026-09-28).

    python3 backend/test_handoff.py

THE RULES CHECK (the brief: "no picture or input path exists outside a
paused-at-owner-page state"), in code and in behaviour:
  * in code: the ONLY page calls in the module are one screenshot (in
    frame()) and the owner's own tap / typing / key / scroll (in _relay());
    both run only through _on_window(), which frame() and send_input() reach
    only AFTER _mine() - the check that the session is still paused at that
    page with that window. No goto, no evaluate, no launch, no page script,
    no proxy, spoofing or captcha-solving words (the chatbot sites' own
    FORBIDDEN list; the owner reversed "driven openly" on 2026-09-29, and the
    list now says what still holds).
  * in behaviour, with a stand-in window that records every call: nothing is
    offered, pictured or passed on while a session runs, is paused for any
    other reason (a card, an "are you a bot?" question, Pause), is part of
    a comparison, or has no window (an API service); a Resume, a Stop, Stop
    everything, the window going to another site, closing, going unlooked-at
    for IDLE_S or passing MOST_S ends it at once, and the page sees nothing
    after that.
  * with a REAL browser (Playwright's Chromium in a visible window, on Xvfb
    when there is no screen - skipped when neither is here): a real JPEG of
    the one page, the owner's tap reaching a checkbox, typing reaching a box,
    and a tap that takes the page to another host ending the hand-off.
"""
from __future__ import annotations

import ast
import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tokenize
import traceback
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import SHIPPED, require_shipped  # noqa: E402

require_shipped("jarvis_handoff.py", "jarvis_chatbot.py", "jarvis_chatbot_routes.py",
                "jarvis_chatbot_web.py", "jarvis_support.py", "jarvis_stop_all.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.insert(1, str(HERE / "rebuilt"))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-handoff-"))
AUDIT: list = []
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda kind, detail=None, *a, **k: AUDIT.append((kind, detail))
fw.action_tier = lambda action: "ask"
sys.modules["jarvis_framework"] = fw

import jarvis_stop_all as SA  # noqa: E402
import jarvis_chatbot as CB  # noqa: E402
import jarvis_chatbot_routes as R  # noqa: E402
import jarvis_chatbot_web as W  # noqa: E402
import jarvis_handoff as HO  # noqa: E402
import jarvis_support as SUP  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


SRC = (HERE / "jarvis_handoff.py").read_text(encoding="utf-8")


def _code_only(src: str) -> str:
    tree = ast.parse(src)
    doc = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            doc.update(range(body[0].lineno, body[0].end_lineno + 1))
    return " ".join(t.string for t in tokenize.generate_tokens(io.StringIO(src).readline)
                    if t.type != tokenize.COMMENT and t.start[0] not in doc)


# ==========================================================================
#   A stand-in window that records every call
# ==========================================================================

def tiny_jpeg(w: int, h: int) -> bytes:
    """Just enough of a JPEG for its size to be read (SOF0)."""
    sof = b"\xff\xc0\x00\x11\x08" + h.to_bytes(2, "big") + w.to_bytes(2, "big") \
        + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    app0 = b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    return b"\xff\xd8" + app0 + sof + b"\xff\xd9"


class FakeMouse:
    def __init__(self, page):
        self.page = page

    def click(self, x, y):
        self.page.calls.append(("click", x, y))
        if self.page.on_click:
            self.page.on_click(x, y)

    def wheel(self, dx, dy):
        self.page.calls.append(("wheel", dx, dy))


class FakeKeyboard:
    def __init__(self, page):
        self.page = page

    def type(self, text):
        self.page.calls.append(("type", text))

    def press(self, key):
        self.page.calls.append(("press", key))


class FakePage:
    def __init__(self, url):
        self.url = url
        self.calls = []
        self.closed = False
        self.on_click = None
        self.mouse = FakeMouse(self)
        self.keyboard = FakeKeyboard(self)

    def screenshot(self, **kw):
        self.calls.append(("screenshot", kw))
        return tiny_jpeg(800, 600)


class FakeWindow:
    """What jarvis_handoff needs of a WebAdapter: _call, _page,
    _page_alive, chat_hosts, sign_in_hosts."""
    chat_hosts = ("gemini.google.com",)
    sign_in_hosts = ("accounts.google.com",)

    def __init__(self, url="https://gemini.google.com/app"):
        self._page = FakePage(url)

    def _page_alive(self):
        return not self._page.closed

    def _call(self, fn, timeout):
        return fn()


class NoWindow:
    """An API service: no browser window at all."""


TIER = CB.Tier("one_card", "http://127.0.0.1:11434", "m", 4096)
_n = [0]


def session(state="paused", code="captcha", adapter=None, compare=""):
    _n[0] += 1
    s = CB.Session(id=f"chat_{_n[0]:012x}", chatbot="gemini_web", goal="g",
                   limits=CB.Limits(5, 10), tier=TIER, state=state, paused_code=code,
                   compare=compare)
    s.adapter = adapter if adapter is not None else FakeWindow()
    with CB._LOCK:
        CB._SESSIONS[s.id] = s
    return s


def support_chat(state="paused", code="login", widget=None):
    _n[0] += 1
    c = SUP.SupportChat(id=f"sup_{_n[0]:012x}", company="groupon", company_name="Groupon",
                        help_url="https://www.groupon.com/help", hosts=("www.groupon.com",),
                        goal="g", details=(), limits=SUP.Limits(5, 10, 10), tier=TIER,
                        state=state, paused_code=code)
    w = widget if widget is not None else FakeWindow("https://www.groupon.com/help")
    if widget is None:
        w.chat_hosts = ("www.groupon.com",)
        w.sign_in_hosts = ()
    c.widget = w
    with SUP._LOCK:
        SUP._CHATS[c.id] = c
    return c


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


CLOCK = Clock()


def fresh():
    with CB._LOCK:
        CB._SESSIONS.clear()
    SUP._reset_for_tests()
    CLOCK.t = 1000.0
    HO._reset_for_tests(clock=CLOCK)
    AUDIT.clear()


def page_of(s):
    a = s.adapter if hasattr(s, "adapter") else s.widget
    return a._page


# ==========================================================================
#   The code checks
# ==========================================================================

def t_code():
    sites = (HERE / "test_chatbot_sites.py").read_text(encoding="utf-8")
    m = re.search(r"FORBIDDEN = \((.*?)\n\)", sites, re.S)
    forbidden = ast.literal_eval("(" + m.group(1) + "\n)") if m else ()
    check("the chatbot sites' forbidden list was read", len(forbidden) > 20)
    code = _code_only(SRC).lower()
    found = [w for w in forbidden if w in code]
    check("no proxy, no captcha-solving code, no spoofing code of its own (the owner "
          "reversed 'driven openly' on 2026-09-29; these three still hold)", not found, found)
    check("its docstring records the reversal and what still holds",
          "2026-09-29" in SRC and "captcha solving" in " ".join(SRC.split())
          and "never saved" in SRC)
    tree = ast.parse(SRC)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)]
    attrs = {n.func.attr for n in calls}
    check("it never opens, launches, runs page scripts or clicks elements",
          not attrs & {"goto", "launch", "launch_persistent_context", "new_page", "evaluate",
                       "evaluate_handle", "add_init_script", "route", "locator", "fill",
                       "dispatch_event", "select_option", "set_checked", "expose_function",
                       "expose_binding", "set_input_files", "query_selector"},
          sorted(attrs))

    def where(attr_names):
        out = set()
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef):
                for n in ast.walk(fn):
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                            and n.func.attr in attr_names:
                        out.add(fn.name)
        return out
    check("ONE picture call, in frame() only", where({"screenshot"}) == {"frame"},
          where({"screenshot"}))
    check("the owner's own input reaches the page in _relay() only",
          where({"click", "type", "press", "wheel"}) == {"_relay"},
          where({"click", "type", "press", "wheel"}))
    uses = {}
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            names = [n.id for n in ast.walk(fn) if isinstance(n, ast.Name)]
            for name in ("_on_window", "_relay", "_mine"):
                if name in names:
                    uses.setdefault(name, set()).add(fn.name)
    check("_on_window is called from frame() and send_input() only",
          uses.get("_on_window") == {"frame", "send_input"}, uses.get("_on_window"))
    check("_relay is reached only through send_input()", uses.get("_relay") == {"send_input"},
          uses.get("_relay"))
    for name in ("frame", "send_input"):
        fn = next(f for f in tree.body if isinstance(f, ast.FunctionDef) and f.name == name)
        order = [n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id in ("_mine", "_on_window")]
        first_mine = min((n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call)
                          and isinstance(n.func, ast.Name) and n.func.id == "_mine"),
                         default=10 ** 9)
        first_window = min((n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call)
                            and isinstance(n.func, ast.Name) and n.func.id == "_on_window"),
                           default=0)
        check(f"{name}(): the paused-there check (_mine) comes before the window is touched",
              "_mine" in order and first_mine < first_window, order)
    check("only the three owner pages can start one", HO.OWNER_CODES == ("captcha", "login",
                                                                          "unusual"))
    check("keys: no function keys, no shortcuts",
          all(not k.startswith("F") and "+" not in k for k in HO.KEYS))
    # Nothing else in the chatbot family pictures a page or moves a mouse.
    for f in ("jarvis_chatbot.py", "jarvis_chatbot_web.py", "jarvis_support.py",
              "jarvis_support_widget.py", "jarvis_chatbot_routes.py", "jarvis_chatbot_compare.py"):
        src = (HERE / f).read_text(encoding="utf-8")
        t = ast.parse(src)
        bad = {n.func.attr for n in ast.walk(t) if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Attribute)
               and n.func.attr in ("screenshot", "wheel")}
        mouse = [n for n in ast.walk(t) if isinstance(n, ast.Attribute) and n.attr == "mouse"]
        check(f"{f}: no picture and no mouse of its own", not bad and not mouse, bad)
    check("shipped", "jarvis_handoff.py" in SHIPPED)
    ps1 = (HERE.parent / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("apply-patches.ps1 ships it", "'jarvis_handoff.py'" in ps1)


# ==========================================================================
#   Behaviour with the stand-in window
# ==========================================================================

def t_nothing_offered_unless_paused_at_an_owner_page():
    fresh()
    check("nothing running: not offered", HO.offer()["available"] is False)
    code, out = HO.start("chatbot", "chat_000000000999")
    check("... and a start is refused with a plain reason", code == 409 and "Nothing" in
          out["error"], (code, out))
    running = session(state="running", code="")
    card = session(state="paused", code="blocked")
    mine = session(state="paused", code="paused")
    cmp_ = session(state="paused", code="captcha", compare="cmp_000000000001")
    api = session(state="paused", code="captcha", adapter=NoWindow())
    bot = support_chat(state="paused", code="bot_question")
    ident = support_chat(state="paused", code="identity")
    check("running, blocked, Pause, a comparison, an API service, 'are you a bot?' and an "
          "identity check are never offered", HO.offer()["available"] is False, HO.offer())
    for kind, x in (("chatbot", running), ("chatbot", card), ("chatbot", mine),
                    ("chatbot", cmp_), ("chatbot", api), ("support", bot),
                    ("support", ident)):
        code, _ = HO.start(kind, x.id)
        check(f"start refused for {kind} {x.state}/{x.paused_code}"
              + (" (compare)" if getattr(x, "compare", "") else ""), code == 409)
    touched = [page_of(x).calls for x in (running, card, mine, cmp_, bot, ident)]
    check("... and no page was pictured or touched", all(c == [] for c in touched), touched)


def t_a_whole_hand_off():
    fresh()
    s = session(code="captcha")
    off = HO.offer()
    check("paused at a captcha: offered, naming the site and the reason only",
          off["available"] and off["kind"] == "chatbot" and off["id"] == s.id
          and off["site"] == "Gemini" and off["reason"] == "captcha"
          and off["title"] == "Gemini needs you" and "captcha" in off["text"]
          and off["active"] == "", off)
    check("the offer carries no picture", "jpeg" not in json.dumps(off))
    code, out = HO.start("support", s.id)
    check("the wrong kind is refused", code == 409)
    code, out = HO.start("chatbot", s.id)
    check("start: no card, a hand-off id", code == 200 and out["handoff"].startswith("ho_"),
          (code, out))
    hid = out["handoff"]
    check("... offer() now names it as active", HO.offer()["active"] == hid)
    code, out = HO.send_input(hid, {"type": "tap", "x": 0.5, "y": 0.5})
    check("a tap before any picture is refused (nothing to aim at)", code == 400, out)
    code, out = HO.frame(hid)
    page = page_of(s)
    check("one picture: a JPEG of that page, its size from its own header",
          code == 200 and base64.b64decode(out["jpeg"])[:2] == b"\xff\xd8"
          and (out["width"], out["height"]) == (800, 600) and out["seq"] == 1, (code, out))
    check("... Playwright's own screenshot of that ONE page, as a JPEG in page pixels",
          page.calls[-1][0] == "screenshot" and page.calls[-1][1].get("type") == "jpeg"
          and page.calls[-1][1].get("scale") == "css", page.calls)
    code, out = HO.frame(hid)
    check("at most two pictures a second", code == 429 and out["retry_ms"] > 0, (code, out))
    CLOCK.t += 0.6
    check("... then another", HO.frame(hid)[0] == 200)
    code, out = HO.send_input(hid, {"type": "tap", "x": 0.25, "y": 1.0})
    check("a tap lands where the owner tapped, in page pixels",
          code == 200 and page.calls[-1] == ("click", 199.8, 599.0), page.calls[-1])
    check("typing is passed on as typed",
          HO.send_input(hid, {"type": "text", "text": "hunter two"})[0] == 200
          and page.calls[-1] == ("type", "hunter two"))
    check("Enter, Backspace and Space are keys", all(
        HO.send_input(hid, {"type": "key", "key": k})[0] == 200
        for k in ("Enter", "Backspace", "Space")) and page.calls[-1] == ("press", " "))
    check("a scroll is capped", HO.send_input(hid, {"type": "scroll", "dy": 99999})[0] == 200
          and page.calls[-1] == ("wheel", 0, HO.SCROLL_MOST))
    before = len(page.calls)
    bad = [HO.send_input(hid, b)[0] for b in (
        {"type": "key", "key": "F5"}, {"type": "key", "key": "Control+L"},
        {"type": "text", "text": "a\nb"}, {"type": "text", "text": "x" * 201},
        {"type": "tap", "x": 1.5, "y": 0.1}, {"type": "tap", "x": "a", "y": 1},
        {"type": "drag"}, {"type": "text", "text": ""})]
    check("refused: other keys, control characters, too long, outside the picture, unknown",
          all(c == 400 for c in bad) and len(page.calls) == before, bad)
    typed = json.dumps(AUDIT)
    check("the audit carries counts and key names, never typed text",
          "hunter" not in typed and any(d and d.get("event") == "input" for _, d in AUDIT))
    code, out = HO.send_input("ho_nottheone", {"type": "key", "key": "Enter"})
    check("another hand-off id is refused", code == 410)
    # The owner pressed Resume: the session runs again.
    s.state = "running"
    before = len(page.calls)
    code, out = HO.send_input(hid, {"type": "key", "key": "Enter"})
    check("after Resume, input is refused: the hand-off ended ('resumed')",
          code == 410 and out["ended"] == "resumed", (code, out))
    check("... picture refused too, and the page saw nothing more",
          HO.frame(hid)[0] == 410 and len(page.calls) == before)
    check("... and it is no longer offered", HO.offer()["available"] is False)


def t_ends():
    fresh()
    s = session(code="login")
    hid = HO.start("chatbot", s.id)[1]["handoff"]
    HO.frame(hid)
    page = page_of(s)
    page.url = "https://evil.example/phish"
    CLOCK.t += 1
    code, out = HO.frame(hid)
    check("the window on another host: the picture is refused and it ends ('left')",
          code == 410 and out["ended"] == "left", (code, out))
    check("... nothing was pictured on that host",
          [c for c in page.calls if c[0] == "screenshot"].__len__() == 1)
    page.url = "https://gemini.google.com/app"
    check("coming back does not revive it", HO.send_input(hid, {"type": "key",
                                                               "key": "Enter"})[0] == 410)

    fresh()
    s = session(code="login")
    s.adapter._page.url = "https://accounts.google.com/signin"
    hid = HO.start("chatbot", s.id)[1]["handoff"]
    check("a sign-in page on the site's own sign-in host is allowed",
          HO.frame(hid)[0] == 200)
    page = page_of(s)
    page.on_click = lambda x, y: setattr(page, "url", "https://elsewhere.example/")
    code, out = HO.send_input(hid, {"type": "tap", "x": 0.1, "y": 0.1})
    check("a tap that takes the page to another site ends it at once",
          code == 410 and out["ended"] == "left", (code, out))

    fresh()
    s = session(code="unusual")
    hid = HO.start("chatbot", s.id)[1]["handoff"]
    HO.frame(hid)
    CLOCK.t += HO.IDLE_S + 1
    code, out = HO.send_input(hid, {"type": "key", "key": "Enter"})
    check("nobody looking for IDLE_S: it ends ('idle')", code == 410 and out["ended"] == "idle")

    fresh()
    s = session(code="captcha")
    hid = HO.start("chatbot", s.id)[1]["handoff"]
    for _ in range(int(HO.MOST_S // 30) + 2):
        CLOCK.t += 30
        code, out = HO.frame(hid)
        if code != 200:
            break
    check("however it goes, it ends after MOST_S ('time')", code == 410
          and out["ended"] == "time", (code, out))

    fresh()
    s = session(code="captcha")
    hid = HO.start("chatbot", s.id)[1]["handoff"]
    s.adapter._page.closed = True
    check("the window closed: it ends", HO.frame(hid)[1].get("ended") in ("closed",))

    fresh()
    s = session(code="captcha")
    hid = HO.start("chatbot", s.id)[1]["handoff"]
    SA.stop_all("test")
    check("Stop everything ends it", HO.frame(hid)[1].get("ended") == "stop_all")

    fresh()
    s = session(code="captcha")
    hid = HO.start("chatbot", s.id)[1]["handoff"]
    check("End is never refused, and twice is fine",
          HO.end(hid)[0] == 200 and HO.end(hid)[0] == 200 and HO.frame(hid)[0] == 410)
    s.state = "stopped"
    fresh()
    s = session(code="captcha")
    hid = HO.start("chatbot", s.id)[1]["handoff"]
    s.state = "stopped"
    check("Stop on the conversation ends it ('stopped')",
          HO.frame(hid)[1].get("ended") == "stopped")

    fresh()
    a = session(code="captcha")
    b = session(code="captcha")
    h1 = HO.start("chatbot", a.id)[1]["handoff"]
    h2 = HO.start("chatbot", b.id)[1]["handoff"]
    check("one hand-off at a time: a new one ends the old",
          HO.frame(h1)[0] == 410 and HO.frame(h2)[0] == 200)
    check("... and the picture came from the new session's window only",
          not [c for c in page_of(a).calls if c[0] == "screenshot"])


def t_support_chat():
    fresh()
    c = support_chat(code="login")
    off = HO.offer()
    check("a support chat at a sign-in page is offered", off["available"]
          and off["kind"] == "support" and off["site"] == "Groupon", off)
    code, out = HO.start("support", c.id)
    check("... and can be handed on", code == 200, out)
    hid = out["handoff"]
    check("... its picture", HO.frame(hid)[0] == 200)
    c.state = "running"
    check("... and a Resume ends it", HO.frame(hid)[1].get("ended") == "resumed")


def t_routes():
    fresh()
    s = session(code="captcha")
    code, out = R.handle_get("")
    check("GET /api/chatbot/status carries `handoff`", code == 200
          and out["handoff"]["available"] and out["handoff"]["id"] == s.id, out.get("handoff"))
    code, out = R.handle_post(R.HANDOFF_START_ROUTE, {"kind": "chatbot", "id": s.id})
    check("POST /api/chatbot/handoff/start", code == 200, out)
    hid = out["handoff"]
    code, out = R.handle_frame("h=" + hid)
    check("GET /api/chatbot/handoff/frame", code == 200 and out["jpeg"], code)
    code, out = R.handle_post(R.HANDOFF_INPUT_ROUTE, {"h": hid, "type": "key", "key": "Tab"})
    check("POST /api/chatbot/handoff/input", code == 200, out)
    code, out = R.handle_post(R.HANDOFF_END_ROUTE, {"h": hid})
    check("POST /api/chatbot/handoff/end", code == 200)
    check("... then the picture route says it ended", R.handle_frame("h=" + hid)[0] == 410)
    check("the routes are on the server's lists", R.HANDOFF_FRAME_ROUTE in R.GET_ROUTES
          and all(r in R.POST_ROUTES for r in R.HANDOFF_POST_ROUTES))


def t_words():
    need = ("title", "alert_title", "alert_locked", "alert_text", "here_button", "pc_button",
            "may_refuse", "held_stale", "locked", "detail")
    check("every sentence the apps need", all(HO.WORDS.get(k) for k in need))
    check("the app says plainly that some captchas may refuse taps passed on this way",
          "refuse taps" in HO.WORDS["may_refuse"])
    check("the locked alert names nothing", "{" not in HO.WORDS["alert_locked"])
    check("ASCII only (both apps' fixtures)", all(v.isascii() for v in HO.WORDS.values()))
    gen = HERE.parent / "tools" / "gen_handoff_cases.py"
    r = subprocess.run([sys.executable, str(gen), "--check"], capture_output=True, text=True)
    check("both apps' contract file is up to date (tools/gen_handoff_cases.py --check)",
          r.returncode == 0, r.stdout + r.stderr)


def t_event():
    fresh()
    events = []
    fake = types.ModuleType("jarvis_events")

    class _FakeBus:
        def publish(self, kind, data):
            events.append((kind, data))

    fake.BUS = _FakeBus()
    saved = sys.modules.get("jarvis_events")
    sys.modules["jarvis_events"] = fake
    try:
        s = session(code="captcha")
        off = HO.offer()
        check("offer() publishes a handoff event", len(events) == 1 and events[0][0] == "handoff", events)
        if events:
            check("event carries the offer data", events[0][1].get("available") is True
                  and events[0][1].get("site") == "Gemini"
                  and events[0][1].get("reason") == "captcha", events[0][1])
        HO.offer()
        check("duplicate offer does not republish", len(events) == 1, len(events))
    finally:
        if saved is not None:
            sys.modules["jarvis_events"] = saved
        else:
            sys.modules.pop("jarvis_events", None)



# ==========================================================================
#   With a real browser
# ==========================================================================

PAGE = """<!doctype html><html><body style="margin:0">
<div style="position:absolute;left:0;top:0;width:200px;height:100px">
  <input id="box" style="position:absolute;left:10px;top:10px;width:150px" aria-label="Code">
</div>
<label style="position:absolute;left:300px;top:300px">
  <input type="checkbox" id="tick" style="width:40px;height:40px;margin:0"
   onclick="fetch('/clicked',{method:'POST',body:'tick'})"> I'm not a robot</label>
<a id="away" href="http://localhost:%PORT%/elsewhere"
   style="position:absolute;left:600px;top:500px;display:block;width:100px;height:40px">away</a>
<button id="send" style="position:absolute;left:10px;top:60px"
   onclick="fetch('/typed',{method:'POST',body:document.getElementById('box').value})">send</button>
</body></html>"""
HITS = {"clicked": [], "typed": []}


class _H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = PAGE.replace("%PORT%", str(SERVER.server_address[1])).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        HITS.setdefault(self.path.strip("/"), []).append(self.rfile.read(n).decode())
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


SERVER = ThreadingHTTPServer(("127.0.0.1", 0), _H)


class _Site(W.WebAdapter):
    SITE = W.Site(id="handoff_test", name="Test site", host="127.0.0.1",
                  start_url="http://127.0.0.1/app", module="test_handoff.py",
                  profile_name="handoff-test", account="a spare account", company="Nobody",
                  selectors={"input": ("#box",), "send": ("#send",), "reply": (".reply",),
                             "own": (".own",), "captcha": ("#tick",)})


def _screen():
    if sys.platform != "linux" or os.environ.get("DISPLAY"):
        return None, ""
    xvfb = shutil.which("Xvfb")
    n = next((i for i in range(120, 150) if not Path(f"/tmp/.X{i}-lock").exists()), None)
    if not xvfb or n is None:
        return None, "no screen and no Xvfb"
    p = subprocess.Popen([xvfb, f":{n}", "-screen", "0", "1280x1024x24", "-nolisten", "tcp"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if Path(f"/tmp/.X11-unix/X{n}").exists():
            break
        time.sleep(0.1)
    os.environ["DISPLAY"] = f":{n}"
    return p, ""


def t_real_browser(a):
    fresh()
    HO._reset_for_tests()   # the real clock: the page takes real time
    s = session(code="captcha", adapter=a)
    hid = HO.start("chatbot", s.id)[1]["handoff"]
    code, out = HO.frame(hid)
    data = base64.b64decode(out.get("jpeg", "")) if code == 200 else b""
    check("real: a JPEG of the one page, in page pixels", code == 200
          and data[:2] == b"\xff\xd8" and out["width"] > 600 and out["height"] > 500,
          (code, {k: v for k, v in out.items() if k != "jpeg"}))
    w, h = out.get("width", 1), out.get("height", 1)

    def tap(px, py):
        return HO.send_input(hid, {"type": "tap", "x": px / (w - 1), "y": py / (h - 1)})
    code, _ = tap(320, 320)
    time.sleep(0.8)
    check("real: the owner's tap reached the checkbox", code == 200
          and HITS.get("clicked") == ["tick"], (code, HITS))
    tap(60, 20)
    HO.send_input(hid, {"type": "text", "text": "4 7 x"})
    tap(25, 70)
    time.sleep(0.8)
    check("real: typing reached the box", HITS.get("typed") == ["4 7 x"], HITS)
    code, out = tap(650, 520)
    if code == 200:
        time.sleep(1.0)
        code, out = HO.frame(hid)
    check("real: a tap that took the page to another host ended it ('left')",
          code == 410 and out.get("ended") == "left", (code, out))


def main():
    xvfb = None
    served = False
    a = None
    try:
        for fn in (t_code, t_nothing_offered_unless_paused_at_an_owner_page, t_a_whole_hand_off,
                   t_ends, t_support_chat, t_routes, t_words, t_event):
            print(f"--- {fn.__name__} ---")
            try:
                fn()
            except Exception as exc:  # pragma: no cover
                traceback.print_exc()
                check(f"{fn.__name__} ran without crashing", False, repr(exc))
        skip = ""
        if not W.playwright_installed():
            skip = "playwright is not installed"
        else:
            xvfb, skip = _screen()
        if not skip:
            threading.Thread(target=SERVER.serve_forever, daemon=True).start()
            served = True
            port = SERVER.server_address[1]
            a = _Site(start_url=f"http://127.0.0.1:{port}/app", chat_hosts=("127.0.0.1",),
                      sign_in_hosts=(), profile=_TMP / "profile", open_wait=5)
            try:
                a.open()
            except Exception as exc:
                skip = f"no browser could be started ({type(exc).__name__}: {str(exc)[:200]})"
        if skip:
            print(f"SKIP the real-browser half: {skip}")
        else:
            print("--- t_real_browser ---")
            try:
                t_real_browser(a)
            except Exception as exc:  # pragma: no cover
                traceback.print_exc()
                check("t_real_browser ran without crashing", False, repr(exc))
    finally:
        if a is not None:
            a.close()
        if served:
            SERVER.shutdown()
        SERVER.server_close()
        if xvfb is not None:
            xvfb.terminate()
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
