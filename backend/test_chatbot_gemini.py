"""test_chatbot_gemini.py - the Gemini website adapter
(jarvis_chatbot_gemini.py) against a REAL browser and a FAKE Gemini page
served on 127.0.0.1. Nothing here touches the internet, and nothing here
ever opens gemini.google.com.

    python3 backend/test_chatbot_gemini.py

The owner's decisions (CLAUDE.md, 2026-09-28): Gemini through its website,
driven OPENLY - a visible window, a person's pace, nothing that hides the
automation or dodges Google's bot checks, no captcha solving; at a captcha,
a sign-in page or an "unusual activity" page it stops and asks the owner;
a spare Google account, signed in once by hand.

The fake page mimics Gemini's shape: a message box (a contenteditable
role="textbox"), a "Send message" button, a <model-response> that grows word
by word while a "Stop response" button shows, a sidebar of old chats, and on
request a captcha, a sign-in page, an "unusual traffic" page, a "verify it's
you" page, a notice over the page, a page that sends the window elsewhere,
and a reply with a link in it. Two host names reach the same server, as in
test_browser_control_live.py: 127.0.0.1 plays gemini.google.com, and
"localhost" plays Google's sign-in host (or a foreign site).

What it proves:
  - a full turn: the exact words arrive (line breaks included, Enter never
    sends half a message), and the reply comes back complete - not while
    it is still growing, and not while "Stop response" still shows; open()
    waits for a message box the page builds only after loading;
  - only the NEWEST reply to Jarvis's own message is read - never an older
    one, never the sidebar;
  - every "needs the owner" page: status says so with the right reason,
    send() refuses, and nothing on the page is clicked;
  - it never navigates away by itself (another host is refused), never
    follows the link in a reply, and a page that sends the window elsewhere
    is reported, not followed up;
  - close() works from another thread and twice; afterwards the page is
    "gone";
  - without Playwright, open() and ready() say so in plain words with the
    one-line install command; the registry lists Gemini as built, and
    plan() refuses before any card when it is not set up;
  - the whole driver (jarvis_chatbot.run) holds a one-message conversation
    through the real adapter, and pauses at a captcha with the window left
    open for the owner;
  - the sign-in helper waits while the owner signs in, types and clicks
    nothing, and stops when the window is closed;
  - the owner's self-check prints PASS for every step against the fake;
  - the module has no stealth, fingerprint, webdriver-hiding, proxy or
    captcha-solving code, launches a visible window, and clicks only the
    message box and the send button.

SKIPS (exit 0) when Playwright is not installed or no Chromium can be
started (it is an optional dependency). Here, with a browser already
downloaded somewhere, point Playwright at it:
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 backend/test_chatbot_gemini.py
On Linux with no screen, it starts Xvfb (a pretend screen) if there is one:
the adapter never runs headless, and neither does this test.
"""
from __future__ import annotations

import ast
import io
import json
import os
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
from _where import REPO, SHIPPED, require_shipped  # noqa: E402

require_shipped("jarvis_chatbot.py", "jarvis_chatbot_gemini.py", "jarvis_task_control.py",
                "jarvis_stop_all.py", "rebuilt/jarvis_router.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.insert(1, str(HERE / "rebuilt"))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-gemini-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
fw.action_tier = lambda action: "ask"
sys.modules["jarvis_framework"] = fw

import jarvis_chatbot as CB  # noqa: E402
import jarvis_chatbot_gemini as G  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# ==========================================================================
#   The code checks - these run even without a browser
# ==========================================================================

SRC = (HERE / "jarvis_chatbot_gemini.py").read_text(encoding="utf-8")


def _code_only(src: str) -> str:
    """The module with its comments and docstrings taken out: what it DOES,
    not what it says it never does. String literals that are code (the
    selectors, the words it shows) stay in."""
    tree = ast.parse(src)
    doc_lines = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            doc_lines.update(range(body[0].lineno, body[0].end_lineno + 1))
    out = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT or tok.start[0] in doc_lines:
            continue
        out.append(tok.string)
    return " ".join(out)


FORBIDDEN = (
    # stealth kits and patched drivers
    "stealth", "undetected", "puppeteer_extra", "selenium_stealth", "playwright_extra",
    # changing how the browser presents itself
    "user_agent", "useragent", "user-agent", "fingerprint", "extra_http_headers",
    "set_extra_http_headers", "locale", "timezone_id", "geolocation", "device_scale_factor",
    "--disable-blink-features", "automationcontrolled", "enable-automation",
    "ignore_default_args", "excludeswitches",
    # hiding that a program is driving
    "webdriver", "defineproperty", "add_init_script", "addinitscript",
    "__proto__", "navigator.",
    # going round limits or blocks
    "proxy", "rotate_", "socks5", "bypass",
    # solving captchas
    "2captcha", "twocaptcha", "anticaptcha", "anti-captcha", "capsolver", "capmonster",
    "deathbycaptcha", "solve_", "solve(", "solver", "recaptcha_token", "g-recaptcha-response",
)


def t_openly_no_stealth_code():
    code = _code_only(SRC).lower()
    found = [w for w in FORBIDDEN if w in code]
    check("the module has no stealth, fingerprint, webdriver-hiding, proxy or "
          "captcha-solving code", not found, found)
    check("... and its docstring still says what it never does (the check reads code, "
          "not words)", "No stealth plug-in" in SRC and "captcha solving" in SRC)
    tree = ast.parse(SRC)
    launches = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr in ("launch", "launch_persistent_context")]
    ok = bool(launches)
    for n in launches:
        kw = {k.arg: k.value for k in n.keywords}
        ok = ok and isinstance(kw.get("headless"), ast.Constant) \
            and kw["headless"].value is False
        ok = ok and set(kw) <= {"headless", "no_viewport", None}
    check("every browser launch is headless=False (a window you can see) with no other "
          "changes", ok, [ast.dump(n) for n in launches])
    check("nothing anywhere starts a headless browser", "headless=True" not in SRC
          and "headless = True" not in SRC)
    clickers = set()
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            for n in ast.walk(fn):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                        and n.func.attr in ("click", "dblclick", "tap", "check",
                                            "select_option", "dispatch_event", "set_checked"):
                    clickers.add(fn.name)
    check("it clicks in exactly two places: the message box and the send button",
          clickers == {"_type_message", "_press_send"}, clickers)
    gotos = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "goto"]
    check("one place opens an address, and it checks the host first",
          len(gotos) == 1 and "def _goto_here" in SRC
          and "if host not in self.chat_hosts" in SRC, len(gotos))
    check("the only address it opens by itself is Gemini's new chat",
          G.START_URL == "https://gemini.google.com/app" and G.GeminiWeb().chat_hosts
          == ("gemini.google.com",))
    check("a fixed typing pace, not a random one (the point is the site's load, not a "
          "disguise)", "random" not in _code_only(SRC).lower() and G.TYPE_DELAY_MS > 0)
    check("every selector is in the one table, with fallbacks",
          all(len(G.SELECTORS[r]) >= 2 for r in ("input", "send", "stop", "reply",
                                                 "reply_text", "captcha")))


def t_registry_and_ready():
    info = CB.ADAPTERS["gemini_web"]
    check("Gemini is registered as built, by this module",
          info.built and info.factory is G._factory and info.ready is G.ready)
    a = info.factory()
    check("the factory makes the adapter and opens nothing",
          isinstance(a, G.GeminiWeb) and a._worker is None and a._ctx is None)
    a.close()
    check("the card note says it is open about being a program and stops at captchas",
          "never hides that it is a program" in info.card_note
          and "captcha" in info.card_note and "spare account could be closed" in info.card_note)
    check("the profile is its own folder under the Jarvis settings folder",
          G.profile_dir() == _TMP / "chatbot" / "gemini-profile")
    saved = sys.modules.get("playwright.sync_api", "absent")
    sys.modules["playwright.sync_api"] = None  # an import of it now fails
    try:
        why = G.ready()
        check("without Playwright, ready() says so with the one-line install",
              why == G.NOT_INSTALLED and G.INSTALL_LINE in why, why)
        raised = None
        try:
            G.GeminiWeb(profile=_TMP / "p0").open()
        except G.GeminiUnavailable as exc:
            raised = exc
        check("... and open() raises the same plain words, opening nothing",
              raised is not None and G.INSTALL_LINE in raised.owner_words
              and not (_TMP / "p0").exists(), repr(raised))
        g = next(c for c in CB.choices() if c["id"] == "gemini_web")
        check("... and both apps' list says it is not ready, and why",
              g["built"] is True and g["ready"] is False and G.INSTALL_LINE in g["note"], g)
        s = CB.plan("gemini_web", "What is 2 plus 2?", deps=_deps(None))
        check("... and plan() refuses before any card",
              s.state == "refused" and G.INSTALL_LINE in s.problem, s.problem)
    finally:
        if saved == "absent":
            sys.modules.pop("playwright.sync_api", None)
        else:
            sys.modules["playwright.sync_api"] = saved
    check("the install line and the how-to name the same commands as requirements.txt",
          G.INSTALL_LINE in (HERE / "README.md").read_text(encoding="utf-8")
          and "playwright install chromium" in (HERE / "requirements.txt").read_text("utf-8"))


def t_shipped_and_listed():
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("shipped: in _where.SHIPPED and apply-patches.ps1",
          "jarvis_chatbot_gemini.py" in SHIPPED and "'jarvis_chatbot_gemini.py'" in ps1)
    check("chatbot.patch is in the patch list", "'chatbot.patch'" in ps1)
    patch = (HERE / "chatbot.patch").read_text(encoding="utf-8")
    check("chatbot.patch gives the gate a _RISK line: outbound, cannot be undone",
          '+    "chatbot_session": ("no", "outbound",' in patch)
    import jarvis_reach as R
    check("'What Jarvis can reach' has a row for it", "chatbot" in dict(R.KINDS))
    api = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    check("JARVIS-API.md section 60 names the adapter and the self-check",
          "jarvis_chatbot_gemini.py" in api and G.CHECK_LINE in api)
    notices = (REPO / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8")
    check("THIRD-PARTY-NOTICES names Playwright (Apache-2.0)",
          "Playwright for Python" in notices and "Apache" in notices)


# ==========================================================================
#   The fake Gemini page
# ==========================================================================

STATE = {"mode": "normal", "sent": [], "clicked": [], "requests": []}

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Gemini (fake)</title>
<style>body{font-family:sans-serif} #stop,#cap{display:none} .dlg{border:2px solid}</style>
</head><body>
<nav aria-label="Recent chats"><h2>Verify it's you - an old chat title</h2>
  <p>SIDEBAR-OLD-CHAT: private words from another conversation</p>
  <model-response><message-content><div class="markdown">OLD-REPLY-IN-SIDEBAR</div>
  </message-content></model-response></nav>
<main>
%TOP%
<div id="chat"></div>
%BOX%
<button id="stop" aria-label="Stop response">stop</button>
<iframe id="cap" src="/recaptcha/api2/anchor" title="reCAPTCHA"></iframe>
</main>
<script>
const MODE = "%MODE%";
const PORT = location.port;
let ed = document.getElementById('ed');
const chat = document.getElementById('chat');
let n = 0;
function post(path, body) { fetch(path, {method: 'POST', body: body}); }
function doSend() {
  const text = ed.innerText.replace(/\\n$/, '');
  if (!text.trim()) return;
  ed.innerHTML = '';
  post('/sent', text);
  n += 1;
  const q = document.createElement('user-query'); q.textContent = text; chat.appendChild(q);
  if (MODE === 'captcha_after_send') { document.getElementById('cap').style.display = 'block'; return; }
  if (MODE === 'leave_after_send') { location.href = 'http://localhost:' + PORT + '/elsewhere'; return; }
  const r = document.createElement('model-response');
  r.innerHTML = '<message-content><div class="markdown"></div></message-content>';
  chat.appendChild(r);
  const md = r.querySelector('.markdown');
  const stop = document.getElementById('stop'); stop.style.display = 'inline-block';
  let words;
  if (/2 plus 2/.test(text)) words = ['2', 'plus', '2', 'is', '4.'];
  else words = ('Reply ' + n + ': here is a streamed answer that grows word by word.').split(' ');
  let i = 0;
  function tick() {
    if (i < words.length) {
      md.append((i ? ' ' : '') + words[i]); i++;
      setTimeout(tick, (MODE === 'think' && i === 2) ? 2500 : 150); return;
    }
    if (MODE === 'link_reply') md.insertAdjacentHTML('beforeend',
        ' <a id="lnk" href="http://localhost:' + PORT + '/followed">a link</a>');
    if (MODE === 'unusual_in_reply') md.insertAdjacentHTML('beforeend',
        '<h2>Unusual activity? Verify it\\'s you</h2>');
    stop.style.display = 'none';
    // Like the real page: a new chat gets its own address a little later.
    if (MODE === 'new_address' && n === 1) setTimeout(() => history.pushState({}, '', '/app/c_abc'), 500);
    // ... and the owner switching to another chat in the window.
    if (MODE === 'new_address' && n === 2) setTimeout(() => history.pushState({}, '', '/app/c_other'), 500);
  }
  setTimeout(tick, 400);
}
function wire() {
  ed = document.getElementById('ed');
  ed.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doSend(); } });
  document.getElementById('send').addEventListener('click', doSend);
}
if (MODE === 'slow_box') {
  // Like the real page: the message box is built a moment after loading.
  setTimeout(() => { document.getElementById('slot').innerHTML = %BOXJS%; wire(); }, 1500);
} else if (ed) {
  wire();
}
</script></body></html>"""

BOX = ('<rich-textarea><div id="ed" class="ql-editor" contenteditable="true" role="textbox" '
       'aria-label="Enter a prompt here"></div></rich-textarea>'
       '<button id="send" aria-label="Send message">send</button>')
TOPS = {
    "captcha": '<script>addEventListener("load",()=>{document.getElementById("cap")'
               '.style.display="block"})</script>',
    "signed_out": '<a aria-label="Sign in" href="/signin">Sign in</a>',
    # The owner signs in by hand: the "Sign in" button goes away by itself.
    "signs_in_later": '<a id="si" aria-label="Sign in" href="/signin">Sign in</a><script>'
                      'setTimeout(()=>document.getElementById("si").remove(),1500)</script>',
    "unusual": "<h1>Our systems have detected unusual traffic from your computer network</h1>",
    "verify": "<h1>Verify it's you</h1>",
    "notice": '<div role="dialog" class="dlg">Welcome! Gemini can make mistakes. '
              '<button>Got it</button></div>',
}
SIGNIN = ('<!doctype html><html><body><h1>Sign in</h1><p>Use your Google Account</p>'
          '<input type="email" aria-label="Email or phone"></body></html>')
CAPTCHA_FRAME = ('<!doctype html><html><body><label><input type="checkbox" '
                 'onclick="fetch(\'/clicked\',{method:\'POST\',body:\'captcha\'})">'
                 " I'm not a robot</label></body></html>")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        STATE["requests"].append((host, self.path))
        mode = STATE["mode"]
        if self.path.startswith("/app"):
            if mode == "login_redirect":
                return self._send(302, "", extra={"Location": f"http://localhost:{PORT}/signin"})
            if mode == "login_dom":
                return self._send(200, SIGNIN)
            page = (PAGE.replace("%MODE%", mode).replace("%TOP%", TOPS.get(mode, ""))
                    .replace("%BOX%", '<div id="slot"></div>' if mode == "slow_box" else BOX)
                    .replace("%BOXJS%", json.dumps(BOX)))
            return self._send(200, page)
        if self.path.startswith("/signin"):
            return self._send(200, SIGNIN)
        if self.path.startswith("/recaptcha"):
            return self._send(200, CAPTCHA_FRAME)
        return self._send(404, "<!doctype html><title>elsewhere</title><h1>Somewhere else</h1>")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode("utf-8")
        STATE["requests"].append(((self.headers.get("Host") or "").split(":")[0], self.path))
        if self.path == "/sent":
            STATE["sent"].append(body)
        elif self.path == "/clicked":
            STATE["clicked"].append(body)
        self._send(200, "ok", "text/plain")


SERVER = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
PORT = SERVER.server_address[1]
BASE = f"http://127.0.0.1:{PORT}"


def reset(mode="normal"):
    STATE["mode"] = mode
    STATE["sent"].clear()
    STATE["clicked"].clear()
    STATE["requests"].clear()


_PROFILES = [0]


def adapter(*, sign_in_hosts=("localhost",), settle=1.0) -> "G.GeminiWeb":
    _PROFILES[0] += 1
    return G.GeminiWeb(start_url=BASE + "/app", chat_hosts=("127.0.0.1",),
                       sign_in_hosts=sign_in_hosts, profile=_TMP / f"profile{_PROFILES[0]}",
                       type_delay_ms=5, settle_seconds=settle, open_wait=10)


def wait_reply(a, most=30.0):
    end = time.monotonic() + most
    while time.monotonic() < end:
        r = a.read_reply(1.0)
        if r is not None:
            return r
    return None


# ==========================================================================
#   Against a real browser
# ==========================================================================

def t_full_turn():
    reset()
    a = adapter()
    try:
        a.open()
        st = a.status()
        check("the fake chat page opens and is 'ok' (the sidebar's 'verify it's you' title "
              "is not read as a warning)", st == CB.OK, st)
        check("the message box was found by its role and aria-label",
              a.matched.get("input", (0,))[0] == 1, a.matched.get("input"))
        a.send("What is 2 plus 2?")
        check("the exact words arrived, once", STATE["sent"] == ["What is 2 plus 2?"],
              STATE["sent"])
        early = a.read_reply(0.3)
        check("while the reply is still being written, read_reply() answers None",
              early is None, early)
        reply = wait_reply(a)
        check("the complete reply comes back, and only it", reply == "2 plus 2 is 4.", reply)
        check("the stop button and the reply were found",
              "stop" in a.matched and "reply" in a.matched, a.matched)
        check("the page is still 'ok' afterwards", a.status() == CB.OK)
        check("a second read with nothing sent gives None, not the old reply",
              a.read_reply(0.2) is None)
        a.send("line one\nline two")
        check("a line break is typed as a line break: one message, not two",
              STATE["sent"][-1:] == ["line one\nline two"] and len(STATE["sent"]) == 2,
              STATE["sent"])
        r2 = wait_reply(a)
        check("the NEWEST reply is read, not the first one or the sidebar's",
              r2 == "Reply 2: here is a streamed answer that grows word by word.", r2)
        check("no old chat or sidebar words ever came back",
              "SIDEBAR" not in (reply or "") + (r2 or "") and "OLD-REPLY" not in (r2 or ""))
    finally:
        a.close()


def t_waits_for_the_message_box():
    reset("slow_box")
    a = adapter()
    try:
        a.open()
        st = a.status()
        check("open() waits for a message box the page builds after loading",
              st == CB.OK and "input" in a.matched, st)
        a.send("What is 2 plus 2?")
        check("... and the message then goes", STATE["sent"] == ["What is 2 plus 2?"],
              STATE["sent"])
        check("... and its reply comes back", wait_reply(a) == "2 plus 2 is 4.")
    finally:
        a.close()


def t_a_new_chat_gets_its_own_address():
    reset("new_address")
    a = adapter()
    try:
        a.open()
        a.send("Hello")
        wait_reply(a)
        time.sleep(1.0)
        check("Gemini giving the new chat its own address (/app/<id>) is not 'another chat'",
              a.status() == CB.OK, a.status())
        a.send("And again")
        r = wait_reply(a)
        check("... and the conversation carries on there", r is not None
              and r.startswith("Reply 2"), r)
        time.sleep(1.0)
        st = a.status()
        check("a DIFFERENT chat opened in the window: needs_owner, never read",
              st.state == "needs_owner" and st.reason == "a different chat is showing", st)
    finally:
        a.close()


def t_waits_for_stop_button():
    reset("think")
    a = adapter(settle=0.8)
    try:
        a.open()
        a.send("Tell me something")
        t0 = time.monotonic()
        reply = wait_reply(a)
        took = time.monotonic() - t0
        check("a reply that pauses mid-way (stop still showing) is not cut short",
              reply == "Reply 1: here is a streamed answer that grows word by word.", reply)
        check("... it waited for the stop button to go", took >= 2.5, round(took, 2))
    finally:
        a.close()


def t_needs_owner_pages():
    cases = [
        ("captcha", "captcha", ("localhost",)),
        ("login_dom", "login", ("localhost",)),
        ("login_redirect", "login", ("localhost",)),
        ("signed_out", "login", ("localhost",)),
        ("unusual", "unusual", ("localhost",)),
        ("verify", "unusual", ("localhost",)),
        ("notice", "a notice is open over the page", ("localhost",)),
    ]
    for mode, reason, hosts in cases:
        reset(mode)
        a = adapter(sign_in_hosts=hosts)
        try:
            a.open()
            st = a.status()
            check(f"{mode}: status is needs_owner, reason {reason!r}",
                  st.state == "needs_owner" and st.reason == reason, st)
            refused = False
            try:
                a.send("What is 2 plus 2?")
            except RuntimeError:
                refused = True
            check(f"{mode}: send() refuses and nothing is typed or sent",
                  refused and STATE["sent"] == [], STATE["sent"])
            check(f"{mode}: nothing on the page was clicked", STATE["clicked"] == [])
        finally:
            a.close()


def t_captcha_after_send():
    reset("captcha_after_send")
    a = adapter()
    try:
        a.open()
        a.send("What is 2 plus 2?")
        check("no reply while a captcha is showing", a.read_reply(1.0) is None)
        st = a.status()
        check("a captcha that appears after sending: needs_owner, captcha",
              st.state == "needs_owner" and st.reason == "captcha", st)
        time.sleep(0.5)
        check("the captcha's checkbox was never clicked", STATE["clicked"] == [])
    finally:
        a.close()


def t_never_goes_elsewhere():
    reset("link_reply")
    a = adapter()
    try:
        a.open()
        refused = False
        try:
            a._navigate(f"http://localhost:{PORT}/somewhere")
        except PermissionError:
            refused = True
        check("the adapter refuses to open another host", refused)
        a.send("Give me a link")
        reply = wait_reply(a)
        check("a reply with a link is read as text", reply is not None
              and reply.endswith("a link"), reply)
        time.sleep(0.5)
        hosts = {h for h, _ in STATE["requests"]}
        paths = [p for _, p in STATE["requests"]]
        check("nothing was ever requested from another host, and the link was not followed",
              hosts == {"127.0.0.1"} and "/followed" not in paths
              and "/somewhere" not in paths, STATE["requests"])
    finally:
        a.close()
    reset("unusual_in_reply")
    a = adapter()
    try:
        a.open()
        a.send("Tell me about account checks")
        reply = wait_reply(a)
        check("a reply that TALKS about 'unusual activity' is not a warning page",
              reply is not None and a.status() == CB.OK, a.status())
    finally:
        a.close()
    reset("leave_after_send")
    a = adapter(sign_in_hosts=())
    try:
        a.open()
        a.send("Hello")
        time.sleep(1.0)
        st = a.status()
        check("a page that sends the window to another host: needs_owner, and it says where",
              st.state == "needs_owner" and st.reason == "a page on localhost", st)
    finally:
        a.close()


def t_close():
    reset()
    a = adapter()
    a.open()
    t = threading.Thread(target=a.close)
    t.start()
    t.join(40)
    check("close() works from another thread", not t.is_alive() and a._ctx is None)
    a.close()
    check("close() twice does not raise, and the page is then 'gone'",
          a.status().state == "gone")
    raised = False
    try:
        a.send("hello")
    except RuntimeError:
        raised = True
    check("nothing can be sent after close()", raised)


def t_through_the_driver():
    CB._reset_for_tests()
    reset()
    a = adapter()
    d = _deps(a)
    s = CB.plan("gemini_web", "What is 2 plus 2?", max_turns=1, deps=d)
    check("the driver plans a Gemini conversation (no problem)", not s.problem, s.problem)
    code, _ = CB.start(s, deps=d, wait=True)
    check("one card, then the goal went to the page word for word",
          code == 202 and len(CARDS) == 1 and STATE["sent"] == ["What is 2 plus 2?"],
          (code, len(CARDS), STATE["sent"]))
    who = [(t["who"], t.get("outside_text")) for t in s.transcript]
    check("the transcript holds Jarvis's message and Gemini's reply, marked outside text",
          who == [("jarvis", False), ("chatbot", True)]
          and s.transcript[1]["text"] == "2 plus 2 is 4.", s.transcript)
    check("it ended at its one-message limit and closed the window",
          s.state == "done" and s.ended_code == "limit_turns" and a._ctx is None,
          (s.state, s.ended_code))
    CB._reset_for_tests()
    CARDS.clear()
    reset("captcha")
    a = adapter()
    d = _deps(a)
    s = CB.plan("gemini_web", "What is 2 plus 2?", max_turns=1, deps=d)
    CB.start(s, deps=d, wait=True)
    check("at a captcha the conversation PAUSES and asks, with nothing sent",
          s.state == "paused" and s.paused_code == "captcha" and STATE["sent"] == [],
          (s.state, s.paused_code))
    check("... and the window stays open for the owner to deal with it",
          a._ctx is not None and a.status().reason == "captcha")
    CB.stop(s.id, deps=d)
    check("Stop closes the window", s.state == "stopped" and a._ctx is None)
    CB._reset_for_tests()
    CARDS.clear()
    reset("captcha_after_send")
    a = adapter()
    d = _deps(a)
    s = CB.plan("gemini_web", "What is 2 plus 2?", max_turns=2, deps=d)
    t0 = time.monotonic()
    CB.start(s, deps=d, wait=True)
    took = time.monotonic() - t0
    check("a captcha that shows while waiting for the reply pauses at once, not after the "
          "reply timeout", s.state == "paused" and s.paused_code == "captcha"
          and took < 30 and STATE["sent"] == ["What is 2 plus 2?"],
          (s.state, s.paused_code, round(took, 1)))
    CB.stop(s.id, deps=d)
    check("... and Stop closes that window too", a._ctx is None)
    CB._reset_for_tests()


def t_sign_in_helper():
    reset("signs_in_later")
    a = adapter()
    lines = []

    def out(line):
        lines.append(line)
        if line.startswith("Signed in"):
            # The owner closes the window.
            threading.Thread(target=a.close).start()
    code = G.sign_in(out=out, adapter=a, wait=30)
    check("the sign-in helper waits while the owner signs in, says when it is done, and "
          "stops when the window is closed", code == 0 and any(l.startswith("Signed in")
                                                                for l in lines)
          and a._ctx is None, lines)
    check("... it tells the owner to use the SPARE account, and typed and clicked nothing",
          any("SPARE Google account" in l for l in lines) and STATE["sent"] == []
          and STATE["clicked"] == [])
    reset("signed_out")
    a = adapter()
    lines = []
    code = G.sign_in(out=lines.append, adapter=a, wait=2)
    check("never signed in within the wait: it says so plainly and how to finish",
          code == 1 and any(G.SIGN_IN_LINE in l for l in lines) and a._ctx is None, lines)


def t_self_check():
    reset()
    a = adapter()
    lines = []
    report = _TMP / "check.txt"
    code = G.self_check(out=lines.append, adapter=a, report=report, reply_wait=30)
    fails = [l for l in lines if l.startswith("FAIL")]
    check("the owner's self-check passes every step against the fake page",
          code == 0 and not fails and any("it says 4" in l for l in lines), lines)
    check("it sent only the fixed harmless question",
          STATE["sent"] == [G.CHECK_QUESTION], STATE["sent"])
    check("it says which selector matched, and saves the results where it says",
          any("selector 1 of" in l for l in lines) and report.is_file()
          and any(str(report) in l for l in lines))
    reset("captcha")
    lines = []
    code = G.self_check(out=lines.append, adapter=adapter(), report=report, reply_wait=5)
    check("at a captcha the self-check FAILs that step, says what to do, and sends nothing",
          code == 1 and any(l.startswith("FAIL") and "captcha" in l for l in lines)
          and STATE["sent"] == [], lines)
    check("... still closes the window, and the pass/fail count comes last",
          lines[-3] == "PASS  Closed the window" and lines[-2] == "3 pass, 1 fail", lines)


# ==========================================================================
#   Plumbing
# ==========================================================================

CARDS: list = []


class Verdict:
    def __init__(self, allowed, outcome, tier="ask"):
        self.allowed, self.outcome, self.tier = allowed, outcome, tier


def _approve(action, detail, prompt):
    CARDS.append((action, detail, prompt))
    return Verdict(True, "approved")


def _model(url, body):
    if body.get("format") == CB.SUMMARY_SCHEMA:
        return {"message": {"content": json.dumps({"answer": "It is 4.", "claims": [],
                                                   "open": []})}}
    return {"message": {"content": json.dumps({"move": "stop", "message": "",
                                               "reason": "answered", "notes": ""})}}


def _deps(a):
    return CB.Deps(model=_model, saved_facts=lambda m: [], names_for_facts=lambda f: {},
                   owner_busy=lambda: False, second_lane=lambda: None,
                   full_version_on=lambda: False,
                   main_lane=lambda: ("http://127.0.0.1:11434", "jarvis-primary"),
                   tier_of=lambda action: "ask", gate=_approve,
                   activity=lambda s, d="": None, audit=lambda e, d: None,
                   make_adapter=(lambda cid: a) if a is not None else None)


def _free_display():
    for n in range(90, 120):
        if not Path(f"/tmp/.X{n}-lock").exists() and not Path(f"/tmp/.X11-unix/X{n}").exists():
            return n
    return None


def _screen():
    """A screen for the VISIBLE window: the real one, or Xvfb on Linux."""
    if sys.platform != "linux" or os.environ.get("DISPLAY"):
        return None, ""
    xvfb = shutil.which("Xvfb")
    n = _free_display()
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


def main():
    code_only = [t_openly_no_stealth_code, t_registry_and_ready, t_shipped_and_listed]
    browser = [t_full_turn, t_waits_for_the_message_box, t_a_new_chat_gets_its_own_address,
               t_waits_for_stop_button, t_needs_owner_pages,
               t_captcha_after_send, t_never_goes_elsewhere, t_close, t_through_the_driver,
               t_sign_in_helper, t_self_check]
    xvfb = None
    served = [False]
    try:
        for fn in code_only:
            print(f"--- {fn.__name__} ---")
            try:
                fn()
            except Exception as exc:  # pragma: no cover
                traceback.print_exc()
                check(f"{fn.__name__} ran without crashing", False, repr(exc))
        skip = ""
        if not G.playwright_installed():
            skip = "playwright is not installed"
        else:
            xvfb, skip = _screen()
        if not skip:
            threading.Thread(target=SERVER.serve_forever, daemon=True).start()
            served[0] = True
            probe = adapter()
            try:
                probe.open()
            except G.GeminiUnavailable as exc:
                skip = exc.owner_words
            except Exception as exc:
                skip = f"no browser could be started ({type(exc).__name__}: {str(exc)[:200]})"
            finally:
                probe.close()
        if skip:
            print(f"SKIP the real-browser half: {skip}")
        else:
            for fn in browser:
                print(f"--- {fn.__name__} ---")
                try:
                    fn()
                except Exception as exc:  # pragma: no cover
                    traceback.print_exc()
                    check(f"{fn.__name__} ran without crashing", False, repr(exc))
    finally:
        if served[0]:
            SERVER.shutdown()
        SERVER.server_close()
        if xvfb is not None:
            xvfb.terminate()
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
