"""test_support_widget.py - the customer-support WINDOW (jarvis_support_widget.py)
against a REAL browser and FAKE help pages served on 127.0.0.1, one per chat
maker the design names - Zendesk, Intercom, LivePerson, Gorgias, Freshchat,
Salesforce - and an unbranded one. Nothing here touches the internet, and
nothing here ever opens a real company's page.

    python3 backend/test_support_widget.py

HOW A CROSS-HOST CHAT FRAME IS TESTED. The fake help page is served as
http://127.0.0.1:<port>/help and a vendor's chat frame on it is served from
http://localhost:<port>/widget - a DIFFERENT host, as a real widget's frame
comes from the chat maker's own host. The test's vendor table lists
"localhost" as that maker's host; a second run lists another host instead,
and then the window must refuse the frame: "a chat window from localhost,
which Jarvis does not recognise", nothing read, nothing typed.

WHAT THIS PROVES, AND WHAT IT DOES NOT. The fake pages are built from the
vendor table's OWN first selectors (where each widget sits on the page), so
the window's frame-finding, host rule, reading, menu buttons and typing are
proved against the shape the table describes. Inside every fake chat the
markup is the same (a role="log" list, a textarea, a Send button, quick-reply
buttons), because nothing inside the real widgets could be seen from here.
It does NOT prove the table matches the real widgets - only the owner's
`py -3 jarvis_support_widget.py check groupon` on the PC can.

Per maker: the chat not open yet (NO_CHAT) and then open; the right maker
recognised; the frame's own host followed; the greeting read as the
company's; menu buttons listed and one pressed; the queue, a person
joining, the agent's question; a message typed exactly and sent; Jarvis's
own lines marked as its own. On one maker: a frame from an unknown host
refused, a captcha inside the chat, "unusual activity" words inside the chat
(not a warning page) and on the page (a warning page), a sign-in page, a
pre-chat email box inside the chat (not a sign-in page), the page sent
elsewhere, close() from another thread; a whole support chat through
jarvis_support.run() with the real window; the owner's read-only check
(nothing typed, sent or pressed). Without a browser: the openness checks
over this module (no stealth, no launch or address-opening of its own,
three click places, every send selector names send or submit).

SKIPS the browser half (exit 0) when Playwright or a browser is missing.
On Linux with no screen it starts Xvfb: the window is never headless.
"""
from __future__ import annotations

import ast
import dataclasses
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
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_support.py", "jarvis_support_widget.py", "jarvis_chatbot.py",
                "jarvis_chatbot_web.py", "jarvis_task_control.py", "jarvis_stop_all.py",
                "rebuilt/jarvis_router.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.insert(1, str(HERE / "rebuilt"))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-support-widget-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
fw.action_tier = lambda action: "ask"
sys.modules["jarvis_framework"] = fw

import jarvis_chatbot as CB  # noqa: E402
import jarvis_chatbot_web as W  # noqa: E402
import jarvis_support as S  # noqa: E402
import jarvis_support_widget as SW  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


ORDER = "4481" + "902217"
GREETING = "Hi! I'm the Groupon assistant. How can I help?"
ORDER_Q = "Hi, I'm Priya. Could I have your order number please?"
OFFER = "Thank you. I can offer you a full refund of $45. Would you like me to go ahead?"

# ==========================================================================
#   Openness, without a browser
# ==========================================================================

SRC = (HERE / "jarvis_support_widget.py").read_text(encoding="utf-8")


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


def t_openness():
    sites = (HERE / "test_chatbot_sites.py").read_text(encoding="utf-8")
    m = re.search(r"FORBIDDEN = \((.*?)\n\)", sites, re.S)
    forbidden = ast.literal_eval("(" + m.group(1) + "\n)") if m else ()
    check("the chatbot sites' forbidden list was read", len(forbidden) > 20)
    code = _code_only(SRC).lower()
    found = [w for w in forbidden if w in code]
    check("no stealth, fingerprint, webdriver-hiding, proxy or captcha-solving code",
          not found, found)
    check("no randomness, nothing headless", "random" not in code and "headless" not in code)
    tree = ast.parse(SRC)
    calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)}
    check("it never launches a browser or opens an address itself (the shared base does)",
          not calls & {"launch", "launch_persistent_context", "goto", "new_page",
                       "add_init_script", "route", "set_extra_http_headers"})
    clickers = set()
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            for n in ast.walk(fn):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                        and n.func.attr in ("click", "dblclick", "tap", "check",
                                            "select_option", "dispatch_event"):
                    clickers.add(fn.name)
    check("it clicks in two places of its own: a chat's menu button and its Send button "
          "(the message box is the base's _type_message)",
          clickers == {"_choose_here", "_send_here"}, clickers)
    risky = [s for v in SW.VENDORS for s in SW.vendor_roles(v, "send")
             if not re.search(r"send|submit", s, re.I)]
    check("every Send selector names send or submit", not risky, risky)
    check("its docstring says what it never does, and how a cross-host frame is handled",
          "No stealth plug-in" in SRC and "captcha solving" in SRC
          and "A CHAT IN A FRAME FROM ANOTHER HOST" in SRC and "NOT VERIFIED" in SRC)
    check("the six makers the design names, and an unbranded fallback",
          [v.id for v in SW.VENDORS] == ["zendesk", "intercom", "liveperson", "gorgias",
                                         "freshchat", "salesforce"]
          and SW.UNBRANDED.container == ('[role="log"]',))
    check("its own browser profile, apart from the chatbot sites'",
          SW.profile_dir() == _TMP / "chatbot" / "support-profile")
    check("the host rule: the maker's own hosts and their sub-hosts only",
          SW.host_allowed("wchat.freshchat.com", ("freshchat.com",))
          and not SW.host_allowed("freshchat.com.evil.example", ("freshchat.com",))
          and not SW.host_allowed("evilfreshchat.com", ("freshchat.com",)))


# ==========================================================================
#   The fake pages
# ==========================================================================

def element(selector: str, inner: str = "", extra: str = "") -> tuple:
    """(open tag, close tag) for a simple selector: tag#id.class[attr="v"]
    [attr*="v" i]. Enough for the vendor table's first selectors."""
    m = re.match(r"^([a-z]+)?", selector)
    tag = (m.group(1) if m and m.group(1) else "div")
    attrs = {}
    for idm in re.finditer(r"#([\w-]+)", selector):
        attrs["id"] = idm.group(1)
    classes = [c.group(1) for c in re.finditer(r"\.([\w-]+)", selector)]
    if classes:
        attrs["class"] = " ".join(classes)
    for a in re.finditer(r'\[([\w-]+)(\*?)="([^"]*)"(?: i)?\]', selector):
        attrs[a.group(1)] = a.group(3)
    body = " ".join(f'{k}="{v}"' for k, v in attrs.items())
    return f"<{tag} {body} {extra}>", f"</{tag}>"


def placement(v, src: str) -> str:
    """The vendor's chat, placed on the help page where its table says."""
    if v.frame:
        parts = v.frame[0].split()
        if len(parts) == 2:           # "#fc_frame iframe#fc_widget"
            o1, c1 = element(parts[0])
            o2, c2 = element(parts[1], extra=f'src="{src}" style="width:420px;height:560px"')
            return o1 + o2 + c2 + c1
        o, c = element(v.frame[0], extra=f'src="{src}" style="width:420px;height:560px"')
        return o + c
    o, c = element(v.container[0])
    return o + "%WIDGET%" + c


WIDGET = r"""
<div id="w" style="display:%DISPLAY%">
<div role="log" id="log"></div>
<div class="quick-replies" id="menu"></div>
%CAPTCHA%
<textarea id="box" name="message" class="lpview_form_textarea" placeholder="Type a message"></textarea>
<button id="send" class="lp_send_button" aria-label="Send">Send</button>
</div>
<script>
const MODE = "%MODE%";
const log = document.getElementById('log'), box = document.getElementById('box'),
      menu = document.getElementById('menu'), w = document.getElementById('w');
const post = (p, b) => fetch(p, {method: 'POST', body: b});
function add(who, text) {
  const d = document.createElement('div');
  if (who === 'own') { d.className = 'user-comment consumer customer user-message outbound';
                       d.setAttribute('data-testid', 'primary-message');
                       d.setAttribute('data-author', 'me'); }
  else d.className = 'agent-msg';
  d.textContent = text; log.appendChild(d);
}
function buttons(labels) {
  menu.innerHTML = '';
  for (const l of labels) { const b = document.createElement('button'); b.textContent = l;
    b.onclick = () => { post('/clicked', l); add('own', l); menu.innerHTML = ''; react(l); };
    menu.appendChild(b); }
}
function later(ms, who, text) { setTimeout(() => add(who, text), ms); }
function react(t) {
  if (MODE === 'bot_q') { later(300, 'agent', 'Quick check - am I talking to a bot?'); return; }
  if (MODE === 'unusual_in_chat') { later(300, 'agent', 'We noticed unusual activity on your account, so I will check.'); return; }
  if (t === 'Talk to an agent') {
    later(300, 'agent', 'You are number 2 in the queue.');
    later(700, 'agent', 'Priya joined the chat.');
    later(1100, 'agent', %ORDER_Q%);
  } else if (/\d{10}/.test(t)) { later(400, 'agent', %OFFER%);
  } else if (t.startsWith('Yes, I accept')) {
    later(400, 'agent', 'Done! Is there anything else I can help you with today?');
  } else if (t.startsWith("No, that's everything")) {
    later(400, 'agent', 'Your reference number is GRP48213.');
    later(800, 'agent', 'This chat has ended.');
  }
}
document.getElementById('send').onclick = () => {
  const t = box.value; if (!t) return; post('/sent', t); add('own', t); box.value = ''; react(t); };
function start() { add('agent', %GREETING%); buttons(['Refund', 'Talk to an agent']); }
if (MODE === 'late_open') setTimeout(() => { w.style.display = 'block'; start(); }, 1500);
else start();
</script>"""

TOP = """<!doctype html><html><head><title>Help</title></head><body>
<h1>Help centre</h1>%TOPEXTRA%
<p>Find answers, or chat with us.</p>
%PLACE%
</body></html>"""


class Fake:
    """One server; the help page on 127.0.0.1, the chat frames on localhost."""

    def __init__(self):
        self.state = {"sent": [], "clicked": [], "requests": []}
        fake = self

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
                fake.state["requests"].append((host, self.path))
                path, _, q = self.path.partition("?")
                args = dict(p.split("=", 1) for p in q.split("&") if "=" in p)
                if path == "/help":
                    return self._send(200, fake.page(args.get("v", ""), args.get("mode", "")))
                if path == "/widget":
                    return self._send(200, "<!doctype html><html><body>"
                                      + fake.widget(args.get("mode", "")) + "</body></html>")
                if path == "/elsewhere":
                    return self._send(200, "<!doctype html><title>x</title><p>Else</p>")
                if path == "/go-away":
                    return self._send(302, "", extra={
                        "Location": f"http://localhost:{fake.port}/elsewhere"})
                return self._send(404, "<!doctype html><title>no</title>")

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n).decode("utf-8")
                if self.path == "/sent":
                    fake.state["sent"].append(body)
                elif self.path == "/clicked":
                    fake.state["clicked"].append(body)
                self._send(200, "ok", "text/plain")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def widget(self, mode: str) -> str:
        captcha = ('<iframe title="reCAPTCHA" src="/elsewhere" width="200" height="60">'
                   '</iframe>' if mode == "captcha_in_chat" else "")
        return (WIDGET.replace("%MODE%", mode).replace("%CAPTCHA%", captcha)
                .replace("%DISPLAY%", "none" if mode == "late_open" else "block")
                .replace("%GREETING%", json.dumps(GREETING))
                .replace("%ORDER_Q%", json.dumps(ORDER_Q))
                .replace("%OFFER%", json.dumps(OFFER)))

    def page(self, vid: str, mode: str) -> str:
        v = next((x for x in SW.VENDORS if x.id == vid), SW.UNBRANDED)
        src = f"http://localhost:{self.port}/widget?mode={mode}"
        if v is SW.UNBRANDED:
            place = self.widget(mode)
        else:
            place = placement(v, src).replace("%WIDGET%", self.widget(mode))
        extra = {"unusual_page": "<h2>Our systems have detected unusual traffic from your "
                                 "computer network</h2>",
                 "sign_in": '<form><input type="email" aria-label="Email"><input '
                            'type="password"></form>',
                 "leave": f'<script>setTimeout(()=>location.href="http://localhost:'
                          f'{self.port}/elsewhere",800)</script>'}.get(mode, "")
        return TOP.replace("%PLACE%", place).replace("%TOPEXTRA%", extra)

    def reset(self):
        for k in self.state:
            self.state[k].clear()

    def url(self, vid: str, mode: str = "") -> str:
        return f"http://127.0.0.1:{self.port}/help?v={vid}&mode={mode}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


FAKE: list = []
N = [0]


def vendors_on(host: str) -> tuple:
    """The vendor table as shipped, each maker's host list replaced by
    `host` (the fake frames' host)."""
    return tuple(dataclasses.replace(v, hosts=(host,)) for v in SW.VENDORS)


def widget(vid: str, mode: str = "", *, host: str = "localhost"):
    N[0] += 1
    f = FAKE[0]
    return SW.SupportWidget("Groupon", f.url(vid, mode), ("127.0.0.1",),
                            vendors=vendors_on(host), profile=_TMP / f"profile{N[0]}",
                            type_delay_ms=5, open_wait=10)


def settle(a, most=8.0, until=None):
    """Read the chat until `until(lines)` or `most` seconds."""
    got = []
    end = time.monotonic() + most
    while time.monotonic() < end:
        got += a.read_new()
        if until and until(got):
            break
        time.sleep(0.2)
    return got


# ==========================================================================
#   Against a real browser
# ==========================================================================

def t_each_vendor():
    f = FAKE[0]
    for vid in [v.id for v in SW.VENDORS] + ["unbranded"]:
        f.reset()
        a = widget(vid, "late_open")
        try:
            a.open()
            st = a.status()
            check(f"{vid}: the chat not open yet reads as 'no chat open' (Jarvis waits; it "
                  "never clicks the page's launcher)", st.state == "needs_owner"
                  and st.reason == S.NO_CHAT, st)
            end = time.monotonic() + 8
            while time.monotonic() < end and a.status().state != "ok":
                time.sleep(0.2)
            st = a.status()
            check(f"{vid}: the chat, once open, is one Jarvis can work in", st.state == "ok", st)
            want = vid if vid != "unbranded" else "unbranded"
            check(f"{vid}: the right chat maker recognised",
                  a.vendor is not None and a.vendor.id == want,
                  getattr(a.vendor, "id", None))
            is_frame = vid in ("zendesk", "intercom", "gorgias", "freshchat", "salesforce")
            check(f"{vid}: " + ("its chat frame's own host (another host than the page) is "
                                "followed" if is_frame else "its chat is part of the page"),
                  a.frame_host == ("localhost" if is_frame else ""), a.frame_host)
            got = settle(a, 4, lambda g: g)
            check(f"{vid}: the greeting is read as the company's",
                  got[:1] == [{"who": "company", "text": GREETING}], got)
            check(f"{vid}: the chat's menu buttons are listed",
                  a.menu() == ["Refund", "Talk to an agent"], a.menu())
            a.choose("Talk to an agent")
            got = settle(a, 6, lambda g: any(x["text"] == ORDER_Q for x in g))
            texts = [(x["who"], x["text"]) for x in got]
            check(f"{vid}: pressing a button, then the queue, a person joining, the question",
                  f.state["clicked"] == ["Talk to an agent"]
                  and texts[:1] == [("own", "Talk to an agent")]
                  and ("company", "Priya joined the chat.") in texts
                  and ("company", ORDER_Q) in texts, texts)
            a.send(f"My order number is {ORDER}.\nThanks!")
            got = settle(a, 6, lambda g: any(x["text"] == OFFER for x in g))
            check(f"{vid}: a message typed exactly as checked (a line break stays one "
                  "message) and marked as Jarvis's own",
                  f.state["sent"] == [f"My order number is {ORDER}.\nThanks!"]
                  and got and got[0]["who"] == "own"
                  and any(x["who"] == "company" and x["text"] == OFFER for x in got),
                  (f.state["sent"], got))
            try:
                a.choose("Cancel everything")
                pressed = True
            except RuntimeError:
                pressed = False
            check(f"{vid}: a button that is not in the chat is never pressed",
                  not pressed and f.state["clicked"] == ["Talk to an agent"])
        finally:
            a.close()
        check(f"{vid}: nothing was asked of any host but the page's and its chat frame's",
              {h for h, _ in f.state["requests"]} <= {"127.0.0.1", "localhost"})


def t_a_frame_from_an_unknown_host():
    f = FAKE[0]
    f.reset()
    a = widget("freshchat", host="chat.vendor.example")
    try:
        a.open()
        st = a.status()
        check("a chat frame from a host not on its maker's list is refused, by name",
              st.state == "needs_owner" and "localhost" in st.reason
              and "does not recognise" in st.reason, st)
        check("...nothing is read from it", a.read_new() == [] and a.menu() == [])
        try:
            a.send("hello")
            sent = True
        except RuntimeError:
            sent = False
        check("...and nothing is typed into it", not sent and f.state["sent"] == [])
    finally:
        a.close()


def t_pages_that_need_the_owner():
    f = FAKE[0]
    cases = [("captcha_in_chat", "captcha"), ("unusual_page", "unusual"),
             ("sign_in", "login")]
    for mode, reason in cases:
        f.reset()
        a = widget("zendesk", mode)
        try:
            a.open()
            st = a.status()
            check(f"{mode}: needs the owner ({reason}); nothing is done about it",
                  st.state == "needs_owner" and st.reason == reason, st)
            try:
                a.send("hello")
                sent = True
            except RuntimeError:
                sent = False
            check(f"{mode}: send refuses", not sent and f.state["sent"] == [])
        finally:
            a.close()
    f.reset()
    a = widget("zendesk", "unusual_in_chat")
    try:
        a.open()
        settle(a, 2)
        a.send("Hello, I need help with an order.")
        got = settle(a, 4, lambda g: any("unusual activity" in x["text"] for x in g))
        check("an agent SAYING 'unusual activity' in the chat is not a warning page",
              a.status().state == "ok" and any("unusual" in x["text"] for x in got), got)
    finally:
        a.close()
    f.reset()
    a = widget("liveperson")
    try:
        a.open()
        a._call(lambda: a._page.evaluate(
            "document.getElementById('lpChat').insertAdjacentHTML('afterbegin', "
            "'<input type=\"email\" aria-label=\"Your email\">')"), 10)
        st = a.status()
        check("a pre-chat email box INSIDE the chat is not a sign-in page", st.state == "ok",
              st)
    finally:
        a.close()
    f.reset()
    a = widget("zendesk", "leave")
    try:
        a.open()
        end = time.monotonic() + 8
        st = a.status()
        while time.monotonic() < end and "localhost" not in st.reason:
            time.sleep(0.3)
            st = a.status()
        check("the page sent elsewhere pauses, naming the host",
              st.state == "needs_owner" and "localhost" in st.reason, st)
    finally:
        a.close()
    a = widget("zendesk")
    a.open()
    t = threading.Thread(target=a.close)
    t.start()
    t.join(30)
    a.close()
    check("close() works from another thread, and twice; then 'gone'",
          not t.is_alive() and a.status().state == "gone")


def t_a_whole_support_chat_through_the_real_window():
    f = FAKE[0]
    f.reset()
    old = (S.POLL, S.PACE_SECONDS)
    S.POLL, S.PACE_SECONDS = 0.3, 0.2
    moves = [{"move": "menu", "option": "Talk to an agent"},
             {"move": "reply", "message": f"It's {ORDER}."}]

    def model(url, body):
        if body.get("format") == S.SUMMARY_SCHEMA:
            return {"message": {"content": json.dumps({"answer": "Refunded.", "agreed": [],
                                                       "open": []})}}
        mv = {"move": "wait", "message": "", "option": "", "reason": "", "notes": ""}
        # The model is asked only when the company has spoken: the greeting,
        # then the agent's question.
        if moves:
            mv.update(moves.pop(0))
        return {"message": {"content": json.dumps(mv)}}
    cards = []
    a = widget("zendesk")
    d = S.Deps(model=model, saved_facts=lambda m: [], names_for_facts=lambda x: {},
               owner_busy=lambda: False, second_lane=lambda: None,
               full_version_on=lambda: False,
               main_lane=lambda: ("http://127.0.0.1:11434", "jarvis-primary"),
               tier_of=lambda x: "ask",
               gate=lambda act, det, pr: cards.append(act) or types.SimpleNamespace(
                   allowed=True, outcome="approved", tier="ask"),
               activity=lambda s, dt="": None, audit=lambda e, dt: None,
               make_widget=lambda c: a, spawn=lambda fn: fn(), history=lambda rec: "",
               allow_test_address=True)
    try:
        c = S.plan("groupon", f"Refund order {ORDER}, the spa closed.",
                   details=[{"name": "Order number", "value": ORDER}], deps=d)
        S.start(c, deps=d, wait=True)
    finally:
        S.POLL, S.PACE_SECONDS = old
    check("the whole chat ran in the real window and finished",
          c.ended_code in ("chat_ended", "finished"), (c.state, c.ended_code, c.ended_words))
    check("the button pressed, then exactly these typed: the listed order number, the "
          "accepting line (after its card), the reference request",
          f.state["clicked"] == ["Talk to an agent"]
          and f.state["sent"] == [f"It's {ORDER}.", S.ACCEPT_LINE, S.CLOSING_ASK],
          (f.state["clicked"], f.state["sent"]))
    check("two cards: the details card and the offer card", cards == [S.ACTION,
                                                                     S.OFFER_ACTION], cards)
    check("the reference number was kept", c.reference == "GRP48213", c.reference)
    check("the window was closed at the end", a.status().state == "gone")


def t_the_owners_check_reads_only():
    f = FAKE[0]
    f.reset()
    lines = []
    a = widget("gorgias")
    rc = SW.check(["groupon", f.url("gorgias")], out=lines.append, widget=a, wait=10,
                  report=_TMP / "support-check.txt")
    text = "\n".join(lines)
    check("the check passes on a working chat, naming the maker and each selector",
          rc == 0 and "PASS  Recognised the chat's maker - Gorgias" in text
          and "PASS  Found the Send button - selector" in text, text)
    check("...and it typed, sent and pressed nothing",
          f.state["sent"] == [] and f.state["clicked"] == [])
    check("...and lists the menu buttons by label only",
          '"Refund", "Talk to an agent"' in text)
    check("...and wrote its report", (_TMP / "support-check.txt").is_file())


# ==========================================================================

def _free_display():
    for n in range(90, 120):
        if not Path(f"/tmp/.X{n}-lock").exists() and not Path(f"/tmp/.X11-unix/X{n}").exists():
            return n
    return None


def _screen():
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


def _run(fn):
    print(f"--- {fn.__name__} ---")
    try:
        fn()
    except Exception as exc:  # pragma: no cover
        traceback.print_exc()
        check(f"{fn.__name__} ran without crashing", False, repr(exc))


def main():
    xvfb = None
    try:
        _run(t_openness)
        skip = ""
        if not W.playwright_installed():
            skip = "playwright is not installed"
        else:
            xvfb, skip = _screen()
        if not skip:
            FAKE.append(Fake())
            probe = widget("zendesk")
            try:
                probe.open()
            except W.WebUnavailable as exc:
                skip = exc.owner_words
            except Exception as exc:
                skip = f"no browser could be started ({type(exc).__name__}: {str(exc)[:200]})"
            finally:
                probe.close()
        if skip:
            print(f"SKIP the real-browser half: {skip}")
        else:
            for fn in (t_each_vendor, t_a_frame_from_an_unknown_host,
                       t_pages_that_need_the_owner,
                       t_a_whole_support_chat_through_the_real_window,
                       t_the_owners_check_reads_only):
                _run(fn)
    finally:
        for f in FAKE:
            f.close()
        if xvfb is not None:
            xvfb.terminate()
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
