"""test_chatbot_sites.py - every chatbot WEBSITE adapter (the thin site files
jarvis_chatbot_<site>.py and their shared base, jarvis_chatbot_web.py)
against a REAL browser and a FAKE chat page served on 127.0.0.1. Nothing
here touches the internet, and nothing here ever opens a real chatbot site.

    python3 backend/test_chatbot_sites.py                 every site
    python3 backend/test_chatbot_sites.py chatgpt claude  just these

The owner's decisions (CLAUDE.md, 2026-09-28): Gemini, then "the chatbot
driver becomes versatile" - ChatGPT, Claude, Microsoft Copilot, Perplexity
and other commonly used chatbot websites, each in a visible window like
Gemini (a person's pace, no captcha solving), each with its own spare account
signed in once by hand. REVERSED 2026-09-29 (owner): the old "driven openly -
nothing that hides the automation" rule is gone (stealth is on for Jarvis's
browsers; the ban risk is accepted); what this file still tests is no proxy,
no captcha solving, and no spoofing code of Jarvis's own in the visible real
browser.

ONE GENERIC FAKE PAGE, BUILT FROM EACH SITE'S OWN SELECTORS TABLE. For each
site, the first selector of every role (the message box, the send and stop
buttons, a reply and its words, Jarvis's own message, the "Sign in" button,
a captcha, a notice, Perplexity's sources) is turned into a real element on
the page, so the site's adapter runs against the shape its table describes.
That proves the adapter and the table fit together; it does NOT prove the
table matches the real site - only each site's self-check on the owner's PC
can (`py -3 jarvis_chatbot_<site>.py check`).

Per site it proves:
  - a full turn: the exact words arrive (a line break is one message), the
    reply comes back complete - not while it grows, not while "stop" shows,
    not cut short by a pause mid-way - and only the NEWEST reply is read,
    never the sidebar; the first selector of every role is the one matched;
  - the site naming the new chat ("/c/<id>") is followed; another chat
    opened in the window is reported and never read;
  - a reply that TALKS about "unusual activity" is not a warning page;
  - every "needs the owner" page (a captcha, a sign-in page, a sign-in
    host, a sign-in address on the site, a "Sign in" button, an "unusual
    traffic" page, a "verify you are human" page, a notice over the page):
    status says so with the right reason, send() refuses, nothing is typed,
    sent or clicked;
  - another host is refused, a page that sends the window elsewhere is
    reported, and nothing is ever requested from another host;
  - close() works from another thread and twice; afterwards "gone";
  - the sign-in helper and the self-check work, in that site's words;
  - Perplexity: the listed sources come back as TEXT (each once, http(s)
    only) and no source link is ever opened; through the whole driver they
    reach the transcript as outside text.
And, without a browser, over the shared base and EVERY site file: no
proxy code, captcha-solving code, or spoofing code of Jarvis's own in the
visible real browser; one visible launch and one host-checked address, both in the base; no site file
drives the browser itself; every send selector names "send" or "submit"
(so a fallback can never click some other button); each site's own host,
profile folder, commands, registration and card note; shipped and
documented.

SKIPS the browser half (exit 0) when Playwright is not installed or no
Chromium can be started. Here, point Playwright at the downloaded browser:
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 backend/test_chatbot_sites.py
On Linux with no screen it starts Xvfb (a pretend screen): the adapters
never run headless, and neither does this test.
"""
from __future__ import annotations

import ast
import importlib
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
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, SHIPPED, require_shipped  # noqa: E402

SITE_FILES = ("gemini", "chatgpt", "claude", "copilot", "perplexity", "deepseek", "grok",
              "lechat", "metaai")
require_shipped("jarvis_chatbot.py", "jarvis_chatbot_web.py",
                *[f"jarvis_chatbot_{k}.py" for k in SITE_FILES],
                "jarvis_task_control.py", "jarvis_stop_all.py", "rebuilt/jarvis_router.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.insert(1, str(HERE / "rebuilt"))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-sites-"))
fw = types.ModuleType("jarvis_framework")
fw.CONFIG_DIR = _TMP
fw.LOG_DIR = _TMP
fw.load_framework = lambda: {}
fw.audit_log = lambda *a, **k: None
fw.action_tier = lambda action: "ask"
sys.modules["jarvis_framework"] = fw

import jarvis_chatbot as CB  # noqa: E402
import jarvis_chatbot_web as W  # noqa: E402

MODS = {k: importlib.import_module(f"jarvis_chatbot_{k}") for k in SITE_FILES}

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# ==========================================================================
#   Per-site test data (test-only: what a chat's own address looks like)
# ==========================================================================

#: Two addresses a NEW chat could be given by each site: the first is
#: followed, the second (a different chat) is reported.
CHAT_PATHS = {
    "gemini": ("/app/c_abc", "/app/c_other"),
    "chatgpt": ("/c/abc-123", "/c/other-456"),
    "claude": ("/chat/abc-123", "/chat/other-456"),
    "copilot": ("/chats/abc123", "/chats/other456"),
    "perplexity": ("/search/what-is-2-plus-2-abc", "/search/another-question"),
    "deepseek": ("/a/chat/s/abc-123", "/a/chat/s/other-456"),
    "grok": ("/c/abc-123", "/c/other-456"),
    "lechat": ("/chat/abc-123", "/chat/other-456"),
    "metaai": ("/c/abc-123", "/prompt/other-456"),
}
#: A sign-in address on the site's own host, for sites that have one.
LOGIN_PATHS = {
    "chatgpt": "/auth/login",
    "claude": "/login",
    "perplexity": "/login",
    "deepseek": "/sign_in",
    "grok": "/sign-in",
    "lechat": "/login",
}


# ==========================================================================
#   The code checks - these run even without a browser
# ==========================================================================

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


#: The same list as test_chatbot_gemini.py's (checked below that it is).
# CHANGED 2026-09-29 (owner): the old rule "driven openly - nothing that hides
# it, nothing that dodges bot detection" was REVERSED (stealth is on for
# Jarvis's browsers; the ban risk is accepted). This list is NOT that old rule
# any more. It holds what is still true for THIS code (the chatbot driver's
# visible, real browser):
#   * never a proxy and never captcha solving (Jarvis hands a captcha to the
#     owner - PC or phone "Solve it here");
#   * a real browser that Jarvis writes no fingerprint-spoofing of its own
#     for (the headless engine's stealth lives in jarvis_browser_engine*.py,
#     not in the chatbot driver, which stays visible so the owner can take
#     over at a captcha or sign-in).
FORBIDDEN = (
    # no spoofing kits or patched drivers in the visible-browser code
    "stealth", "undetected", "puppeteer_extra", "selenium_stealth", "playwright_extra",
    # no changing how the visible, real browser presents itself
    "user_agent", "useragent", "user-agent", "fingerprint", "extra_http_headers",
    "set_extra_http_headers", "locale", "timezone_id", "geolocation", "device_scale_factor",
    "--disable-blink-features", "automationcontrolled", "enable-automation",
    "ignore_default_args", "excludeswitches",
    # no scripts injected into the page
    "webdriver", "defineproperty", "add_init_script", "addinitscript",
    "__proto__", "navigator.",
    # STILL TRUE: no proxy, no rotating addresses, no getting past a limit
    "proxy", "rotate_", "socks5", "bypass",
    # STILL TRUE: Jarvis never solves a captcha
    "2captcha", "twocaptcha", "anticaptcha", "anti-captcha", "capsolver", "capmonster",
    "deathbycaptcha", "solve_", "solve(", "solver", "recaptcha_token", "g-recaptcha-response",
)
PROXY_WORDS = ("proxy", "rotate_", "socks5", "bypass")
CAPTCHA_WORDS = ("2captcha", "twocaptcha", "anticaptcha", "anti-captcha", "capsolver",
                 "capmonster", "deathbycaptcha", "solve_", "solve(", "solver",
                 "recaptcha_token", "g-recaptcha-response")
SPOOF_WORDS = tuple(w for w in FORBIDDEN if w not in PROXY_WORDS + CAPTCHA_WORDS)
#: Browser calls no SITE file may make: all driving is the shared base's.
BROWSER_CALLS = {"launch", "launch_persistent_context", "goto", "click", "dblclick", "tap",
                 "check", "fill", "type", "press", "evaluate", "route", "add_init_script",
                 "set_extra_http_headers", "dispatch_event", "select_option", "set_checked",
                 "locator", "new_page", "expose_function", "expose_binding", "mouse",
                 "keyboard", "set_input_files", "hover", "focus"}
CLICKS = ("click", "dblclick", "tap", "check", "select_option", "dispatch_event",
          "set_checked")
#: Anything but plain CSS in a selector table.
NOT_CSS = re.compile(r":has-text|:text|text=|xpath=|internal:|>>|:nth-match|:visible")

BASE_SRC = (HERE / "jarvis_chatbot_web.py").read_text(encoding="utf-8")
SITE_SRC = {k: (HERE / f"jarvis_chatbot_{k}.py").read_text(encoding="utf-8")
            for k in SITE_FILES}


def t_still_true_no_proxy_no_captcha_solving():
    gem = (HERE / "test_chatbot_gemini.py").read_text(encoding="utf-8")
    gem_list = re.search(r"FORBIDDEN = \((.*?)\n\)", gem, re.S)
    mine = re.search(r"FORBIDDEN = \((.*?)\n\)", Path(__file__).read_text("utf-8"), re.S)
    check("this test forbids exactly what test_chatbot_gemini.py forbids",
          gem_list is not None and mine is not None
          and re.sub(r"\s+", "", gem_list.group(1)) == re.sub(r"\s+", "", mine.group(1)))
    for label, words in (("proxy", ("proxy", "socks5")), ("captcha solving", ("capsolver",
                         "2captcha", "solve_"))):
        check(f"the shared list still forbids {label} (Jarvis never solves a captcha, "
              "never uses a proxy)", all(w in FORBIDDEN for w in words))
    for name, src in [("jarvis_chatbot_web.py", BASE_SRC)] + \
            [(f"jarvis_chatbot_{k}.py", s) for k, s in SITE_SRC.items()]:
        code = _code_only(src).lower()
        check(f"{name}: no proxy code (still true after the 2026-09-29 reversal)",
              not [w for w in PROXY_WORDS if w in code], [w for w in PROXY_WORDS if w in code])
        check(f"{name}: no captcha-solving code (Jarvis never solves a captcha)",
              not [w for w in CAPTCHA_WORDS if w in code],
              [w for w in CAPTCHA_WORDS if w in code])
        check(f"{name}: no fingerprint-spoofing of Jarvis's own in the visible real browser "
              "(the headless engine's stealth is elsewhere)",
              not [w for w in SPOOF_WORDS if w in code], [w for w in SPOOF_WORDS if w in code])
        check(f"{name}: a fixed typing pace, nothing random", "random" not in code)
        check(f"{name}: the chatbot driver's window is the visible one (the owner may have "
              "to take over at a captcha)",
              "headless=True" not in src and "headless = True" not in src)
        flat = " ".join(src.split())
        check(f"{name}: its docstring records the 2026-09-29 reversal and what still holds",
              "2026-09-29" in flat and "captcha solving" in flat and "proxy" in flat)


def t_the_base_launches_one_visible_real_browser():
    tree = ast.parse(BASE_SRC)
    launches = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr in ("launch", "launch_persistent_context")]
    ok = len(launches) == 1
    for n in launches:
        kw = {k.arg: k.value for k in n.keywords}
        ok = ok and isinstance(kw.get("headless"), ast.Constant) \
            and kw["headless"].value is False and set(kw) <= {"headless", "no_viewport", None}
    check("the base has ONE browser launch: headless=False, nothing else changed", ok,
          [ast.dump(n) for n in launches])
    clickers = set()
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            for n in ast.walk(fn):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                        and n.func.attr in CLICKS:
                    clickers.add(fn.name)
    check("the base clicks in exactly two places: the message box and the send button",
          clickers == {"_type_message", "_press_send"}, clickers)
    gotos = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "goto"]
    check("the base opens an address in one place, and checks the host first",
          len(gotos) == 1 and "if host not in self.chat_hosts" in BASE_SRC)
    reads = re.findall(r"\.get_attribute\(\"(\w+)\"", BASE_SRC)
    check("the only attribute it reads from a page is a source link's href (as text)",
          reads == ["href"], reads)


def t_site_files_are_thin():
    for k, src in SITE_SRC.items():
        tree = ast.parse(src)
        calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)} & BROWSER_CALLS
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} \
            & {"keyboard", "mouse", "_page", "_ctx"}
        check(f"{k}: the site file never drives the browser itself (the base does)",
              not calls and not attrs, (calls, attrs))
        defs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        methods = {f.name for c in classes for f in c.body if isinstance(f, ast.FunctionDef)}
        check(f"{k}: its adapter overrides nothing of the base's",
              not methods and len(classes) == 1, methods)
        check(f"{k}: it has its own sign-in and self-check commands",
              {"sign_in", "self_check", "main", "ready", "_factory"} <= defs, defs)
        check(f"{k}: it says its selectors are NOT VERIFIED and that the account may be "
              "blocked or closed", "NOT VERIFIED" in src
              and ("blocked or closed" in src or k == "gemini"))


def t_selector_tables():
    ids, profiles = set(), set()
    for k, m in MODS.items():
        sel = m.SELECTORS
        need = ("input", "send", "stop", "reply", "own", "signed_out", "sign_in_form",
                "captcha", "warning", "notice")
        check(f"{k}: every role is in its one table", all(r in sel for r in need),
              [r for r in need if r not in sel])
        check(f"{k}: fallbacks for the box, send, stop, reply, captcha and sign-in button",
              all(len(sel[r]) >= 2 for r in ("input", "send", "stop", "reply", "captcha",
                                             "signed_out")))
        allsel = [s for r in sel.values() for s in r]
        bad = [s for s in allsel if not isinstance(s, str) or NOT_CSS.search(s)]
        check(f"{k}: every selector is plain CSS (the reply ones go to the page's closest())",
              not bad, bad)
        broad = [s for r in ("reply", "own") for s in sel[r]
                 if re.fullmatch(r"\s*(?:\*|div|span|p|main|section|article|body|html)\s*", s)]
        check(f"{k}: no reply or own-message selector is a bare element name (the warning "
              "check skips everything inside a match)", not broad, broad)
        risky = [s for s in sel["send"] if not re.search(r"send|submit", s, re.I)]
        check(f"{k}: every send selector names 'send' or 'submit' - a fallback can never "
              "click some other button", not risky, risky)
        if k == "perplexity":
            check("perplexity: a 'sources' row, reading links only (a[href])",
                  len(sel.get("sources", ())) >= 2
                  and all(re.search(r"\ba[.\[]|\ba$", s) for s in sel["sources"]),
                  sel.get("sources"))
        else:
            check(f"{k}: no 'sources' row (only Perplexity lists them)", "sources" not in sel)
        site = m.SITE
        host, path = W.host_path(m.START_URL)
        check(f"{k}: it opens only its own host, over https",
              m.START_URL.startswith("https://") and host == m.HOST == site.host
              and m._factory().chat_hosts == (m.HOST,), (m.START_URL, m.HOST))
        check(f"{k}: sign-in hosts are other hosts, reached only by the owner",
              m.HOST not in site.sign_in_hosts
              and all("." in h and "/" not in h for h in site.sign_in_hosts))
        a, b = CHAT_PATHS[k]
        probe = m._factory()
        check(f"{k}: a new chat's own address is recognised ({a}), the start is not",
              probe._is_new_chat_address(a) and probe._is_new_chat_address(b)
              and not probe._is_new_chat_address(path), (a, b, path))
        if k in LOGIN_PATHS:
            check(f"{k}: its own sign-in address is recognised ({LOGIN_PATHS[k]})",
                  bool(site.sign_in_paths) and re.match(site.sign_in_paths, LOGIN_PATHS[k])
                  and not re.match(site.sign_in_paths, path))
        ids.add(site.id)
        profiles.add(site.profile_name)
        check(f"{k}: its own profile folder, <config>/chatbot/{k}-profile",
              m.profile_dir() == _TMP / "chatbot" / f"{k}-profile"
              and site.profile_name == k)
        check(f"{k}: its commands name its own file",
              m.SIGN_IN_LINE == f"py -3 jarvis_chatbot_{k}.py sign-in"
              and m.CHECK_LINE == f"py -3 jarvis_chatbot_{k}.py check"
              and site.module == f"jarvis_chatbot_{k}.py")
    check("no two sites share an id or a profile folder",
          len(ids) == len(SITE_FILES) and len(profiles) == len(SITE_FILES))


def t_registered_and_ready():
    check("every site file loaded (none recorded a load error)", not W.LOAD_ERRORS,
          W.LOAD_ERRORS)
    check("the base loads exactly the site files this test knows",
          W.SITE_MODULES == tuple(f"jarvis_chatbot_{k}" for k in SITE_FILES), W.SITE_MODULES)
    on_disk = sorted(p.stem for p in HERE.glob("jarvis_chatbot_*.py")
                     if "W.Site(" in p.read_text(encoding="utf-8"))
    check("every site file on disk is in the base's list",
          on_disk == sorted(W.SITE_MODULES), on_disk)
    listed = {c["id"]: c for c in CB.choices()}
    for k, m in MODS.items():
        info = CB.ADAPTERS.get(m.ID)
        check(f"{k}: registered as {m.ID}, built, by its own module",
              info is not None and info.built and info.factory is m._factory
              and info.ready is m.ready and info.host == m.HOST and m.ID in listed)
        a = info.factory()
        check(f"{k}: the factory opens nothing", a._worker is None and a._ctx is None)
        a.close()
        note = info.card_note
        if k == "gemini":
            ok = "never hides that it is a program" not in note and "captcha" in note \
                 and "spare account could be closed" in note
        else:
            ok = ("never hides that it is a program" not in note
                  and "never changes how the browser looks" not in note
                  and "captcha" in note and "terms" in note
                  and f"spare {m.SITE.account} used only by Jarvis" in note
                  and "blocked or closed" in note)
        check(f"{k}: the card note says: a window you can see, the captcha rule, the terms, a "
              "spare account, may be blocked or closed - and promises nothing about hiding",
              ok, note)
        check(f"{k}: the card's 'how' names the spare account",
              "spare" in info.how and "window you can see" in info.how, info.how)
    check("ChatGPT's note names what OpenAI's terms forbid (quoted in the design doc)",
          "OpenAI's terms forbid automatically extracting" in CB.ADAPTERS["chatgpt_web"].card_note)
    check("Perplexity's note says its sources are copied as text, never opened",
          "never opens them" in CB.ADAPTERS["perplexity_web"].card_note)
    saved = sys.modules.get("playwright.sync_api", "absent")
    sys.modules["playwright.sync_api"] = None
    try:
        for k, m in MODS.items():
            check(f"{k}: without Playwright, ready() gives the one-line install",
                  m.ready() == W.NOT_INSTALLED)
        raised = None
        try:
            MODS["chatgpt"].ChatGPTWeb(profile=_TMP / "p0").open()
        except W.WebUnavailable as exc:
            raised = exc
        check("... and open() raises the same plain words, opening nothing",
              raised is not None and W.INSTALL_LINE in raised.owner_words
              and not (_TMP / "p0").exists(), repr(raised))
        s = CB.plan("claude_web", "What is 2 plus 2?", deps=_deps(None))
        check("... and plan() refuses before any card",
              s.state == "refused" and W.INSTALL_LINE in s.problem, s.problem)
    finally:
        if saved == "absent":
            sys.modules.pop("playwright.sync_api", None)
        else:
            sys.modules["playwright.sync_api"] = saved
    if W.playwright_installed():
        m = MODS["grok"]
        check("with Playwright but never signed in, ready() says how to sign in, in that "
              "site's words", m.ready() == m.NOT_SIGNED_IN and "Grok window" in m.ready()
              and "spare Grok account" in m.ready() and m.SIGN_IN_LINE in m.ready())
        folder = m.profile_dir()
        folder.mkdir(parents=True)
        try:
            why = m.ready()
            check("a profile folder alone (the sign-in window was opened, but the sign-in "
                  "never finished) is NOT 'ready': it says to run sign-in again",
                  why == m.SITE.sign_in_unfinished and m.SIGN_IN_LINE in why
                  and "spare Grok account" in why, why)
            W.mark_signed_in(folder)
            check("... and once a finished sign-in is noted, it is ready", m.ready() == "")
        finally:
            shutil.rmtree(folder, ignore_errors=True)


def t_shipped_and_documented():
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    api = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    arch = (REPO / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    for f in ["jarvis_chatbot_web.py"] + [f"jarvis_chatbot_{k}.py" for k in SITE_FILES]:
        check(f"{f}: shipped (in _where.SHIPPED and apply-patches.ps1)",
              f in SHIPPED and f"'{f}'" in ps1)
    for k, m in MODS.items():
        check(f"{k}: JARVIS-API.md section 87 has its id, host and both commands, run from "
              "\"<your backend folder>\"",
              m.ID in api and m.HOST in api
              and f'cd "<your backend folder>"; {m.SIGN_IN_LINE}' in api
              and f'cd "<your backend folder>"; {m.CHECK_LINE}' in api)
        check(f"{k}: ARCHITECTURE names its host as a way out, and README its commands",
              m.HOST in arch and m.CHECK_LINE in readme and m.SIGN_IN_LINE in readme)
    check("no command in the docs uses the owner's own folder",
          "pcadmin" not in api[api.find("## 87."):api.find("## 88.")])


# ==========================================================================
#   The generic fake chat page, built from a site's own SELECTORS
# ==========================================================================

_ATTR = re.compile(r"""\[\s*([\w-]+)\s*(?:([*^$~|]?=)\s*(?:"([^"]*)"|'([^']*)'|([\w-]+))"""
                   r"""\s*(?:[iIsS])?\s*)?\]""")


def _split(sel: str) -> list:
    """A selector's compound parts, outermost first ('>' and ' ' alike)."""
    parts, cur, depth, quote = [], "", 0, ""
    for ch in sel.strip():
        if quote:
            cur += ch
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if depth == 0 and (ch.isspace() or ch == ">"):
            if cur:
                parts.append(cur)
            cur = ""
            continue
        cur += ch
    if cur:
        parts.append(cur)
    return parts


def _element(compound: str, *, role: str = "", editable: bool = False, text: str = "",
             extra: str = "", hidden: bool = False) -> tuple:
    """(open tag, close tag) for ONE compound selector, e.g.
    'div#prompt-textarea[contenteditable="true"]'."""
    m = re.match(r"^([a-zA-Z][\w-]*|\*)?", compound)
    tag = (m.group(1) or "div").replace("*", "div")
    rest = compound[m.end():]
    attrs: dict = {}
    classes: list = []
    while rest:
        if rest.startswith("#"):
            mm = re.match(r"#([\w-]+)", rest)
            attrs["id"] = mm.group(1)
        elif rest.startswith("."):
            mm = re.match(r"\.([\w-]+)", rest)
            classes.append(mm.group(1))
        elif rest.startswith("["):
            mm = _ATTR.match(rest)
            if mm is None:
                raise ValueError(f"cannot build {compound!r}")
            name, op = mm.group(1), mm.group(2) or ""
            val = next((g for g in mm.group(3, 4, 5) if g is not None), "")
            if op == "^=":
                val = val + "1"
            elif op == "$=":
                val = "x" + val
            if name == "class":
                classes.append(val)
            elif name in attrs and op == "*=":
                attrs[name] += " " + val
            else:
                attrs[name] = val
        else:
            raise ValueError(f"cannot build {compound!r} (only tags, #id, .class, [attr])")
        rest = rest[mm.end():]
    if tag == "iframe" and "src" in attrs:
        attrs["src"] = "/frame/" + urllib.parse.quote(attrs["src"])
    if editable and tag not in ("textarea", "input"):
        attrs.setdefault("contenteditable", "true")
    if role:
        attrs["data-fake"] = role
    if classes:
        attrs["class"] = " ".join(classes)
    if hidden:
        attrs["style"] = "display:none"
    html_attrs = "".join(f' {k}="{v}"' if v != "" else f" {k}" for k, v in attrs.items())
    void = tag in ("input",)
    return f"<{tag}{html_attrs}{extra}>{'' if void else text}", "" if void else f"</{tag}>"


def build(selector: str, role: str, *, inner: str = "", **kw) -> str:
    """HTML for `selector` (nested for a descendant selector) whose innermost
    element carries data-fake=<role> and holds `inner`."""
    parts = _split(selector)
    opens, closes = [], []
    for i, p in enumerate(parts):
        last = i == len(parts) - 1
        o, c = _element(p, role=role if last else "", **(kw if last else {}))
        opens.append(o)
        closes.append(c)
    return "".join(opens) + inner + "".join(reversed(closes))


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>%NAME% (fake)</title>
<style>body{font-family:sans-serif} [data-fake=send],[data-fake=stop],[data-fake=signed_out]
{display:inline-block;padding:4px;border:1px solid} [data-fake=input]{min-height:2em;border:1px solid}
</style></head><body>
<nav aria-label="Recent chats"><h2>Verify it's you - an old chat title</h2>
  <p>SIDEBAR-OLD-CHAT: private words from another conversation</p>
  %OLDREPLY%</nav>
<main>
%TOP%
<div id="chat"></div>
%INPUT%
%SEND%
%STOP%
%CAPTCHA%
</main>
<script>
const MODE = "%MODE%";
const PORT = location.port;
const PATHS = %PATHS%;
const REPLY = %REPLY%;
const OWN = %OWN%;
const SOURCES = %SOURCES%;
const input = document.querySelector('[data-fake=input]');
const chat = document.getElementById('chat');
let n = 0;
function post(path, body) { fetch(path, {method: 'POST', body: body}); }
function make(html) { const t = document.createElement('template'); t.innerHTML = html;
  return t.content.firstElementChild; }
function fake(root, role) { return root.matches('[data-fake=' + role + ']') ? root
  : root.querySelector('[data-fake=' + role + ']'); }
function val() { return input.tagName === 'TEXTAREA' ? input.value
  : input.innerText.replace(/\\n$/, ''); }
function clear() { if (input.tagName === 'TEXTAREA') input.value = ''; else input.innerHTML = ''; }
function doSend() {
  const text = val();
  if (!text.trim()) return;
  clear();
  post('/sent', text);
  n += 1;
  const own = make(OWN); fake(own, 'own').textContent = text; chat.appendChild(own);
  if (MODE === 'captcha_after_send') {
    document.querySelector('[data-fake=captcha]').style.display = 'block'; return; }
  if (MODE === 'leave_after_send') { location.href = 'http://localhost:' + PORT + '/elsewhere'; return; }
  const r = make(REPLY); chat.appendChild(r);
  const box = fake(r, 'reply');
  const md = fake(r, 'reply_text') || box;
  const stop = document.querySelector('[data-fake=stop]'); stop.style.display = 'inline-block';
  let words;
  if (/2 plus 2/.test(text)) words = ['2', 'plus', '2', 'is', '4.'];
  else if (/3 plus 3/.test(text)) words = ['3', 'plus', '3', 'is', '6.'];
  else words = ('Reply ' + n + ': here is a streamed answer that grows word by word.').split(' ');
  let i = 0;
  function tick() {
    if (i < words.length) {
      md.append((i ? ' ' : '') + words[i]); i++;
      // A pause mid-way, with "stop" still showing: the reply is not done.
      setTimeout(tick, (n === 2 && i === 2) ? 2500 : 120); return;
    }
    if (MODE === 'unusual_in_reply') md.insertAdjacentHTML('beforeend',
        '<h2>Unusual activity? Verify it\\'s you</h2>');
    if (SOURCES) {
      const links = [['Source one', 'http://localhost:' + PORT + '/source-1'],
                     ['Source one again', 'http://localhost:' + PORT + '/source-1'],
                     ['Another question', '/search/another'],
                     ['Source two', 'http://localhost:' + PORT + '/source-2']];
      for (const [label, href] of links) {
        const s = make(SOURCES); const a = fake(s, 'sources');
        a.setAttribute('href', href); a.textContent = label; box.appendChild(s);
      }
    }
    stop.style.display = 'none';
    // Like the real sites: a new chat gets its own address a little later...
    if ((MODE === 'normal' || MODE === 'check') && n === 1)
      setTimeout(() => history.pushState({}, '', PATHS[0]), 400);
    // ... and the owner switching to another chat in the window, once the
    // reply has been read.
    if (MODE === 'normal' && n === 2) setTimeout(() => history.pushState({}, '', PATHS[1]), 2500);
  }
  setTimeout(tick, 300);
}
if (input) {
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doSend(); } });
  document.querySelector('[data-fake=send]').addEventListener('click', doSend);
}
</script></body></html>"""

SIGNIN = ('<!doctype html><html><body><h1>Sign in</h1><p>Use your account</p>'
          '<input type="email" aria-label="Email or phone"></body></html>')
CAPTCHA_FRAME = ('<!doctype html><html><body><label><input type="checkbox" '
                 'onclick="fetch(\'/clicked\',{method:\'POST\',body:\'captcha\'})">'
                 " I'm not a robot</label></body></html>")


class FakeSite:
    """One fake site on its own port, built from a site module's SELECTORS."""

    def __init__(self, key: str):
        self.key = key
        self.m = MODS[key]
        self.state = {"mode": "normal", "sent": [], "clicked": [], "requests": []}
        sel = self.m.SELECTORS
        self.start_path = W.host_path(self.m.START_URL)[1]
        reply_inner = build(sel["reply_text"][0], "reply_text") if sel.get("reply_text") else ""
        self.parts = {
            "INPUT": build(sel["input"][0], "input", editable=True),
            "SEND": build(sel["send"][0], "send", text="send"),
            "STOP": build(sel["stop"][0], "stop", text="stop", hidden=True),
            "CAPTCHA": build(sel["captcha"][0], "captcha", hidden=True,
                             extra=' width="300" height="80"'),
            "REPLY": build(sel["reply"][0], "reply", inner=reply_inner),
            "OWN": build(sel["own"][0], "own"),
            "SOURCES": (build(sel["sources"][0], "sources") if sel.get("sources") else ""),
            "OLDREPLY": build(sel["reply"][0], "old", inner="OLD-REPLY-IN-SIDEBAR"),
            "SIGNED_OUT": build(sel["signed_out"][0], "signed_out", text="Sign in"),
            "NOTICE": build(sel["notice"][0], "notice",
                            inner="Welcome! It can make mistakes. <button>Got it</button>"),
        }
        site = self

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
                site.state["requests"].append((host, self.path))
                mode = site.state["mode"]
                path = self.path.split("?")[0]
                if path == site.start_path:
                    if mode == "login_redirect":
                        return self._send(302, "", extra={
                            "Location": f"http://localhost:{site.port}/signin"})
                    if mode == "login_path":
                        return self._send(302, "", extra={"Location": LOGIN_PATHS[site.key]})
                    if mode == "login_dom":
                        return self._send(200, SIGNIN)
                    return self._send(200, site.page(mode))
                if path == "/signin":
                    return self._send(200, SIGNIN)
                if path.startswith("/frame/"):
                    return self._send(200, CAPTCHA_FRAME)
                if path == LOGIN_PATHS.get(site.key):
                    return self._send(200, "<!doctype html><title>x</title><p>One moment</p>")
                return self._send(404, "<!doctype html><title>elsewhere</title>"
                                       "<h1>Somewhere else</h1>")

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n).decode("utf-8")
                site.state["requests"].append(
                    ((self.headers.get("Host") or "").split(":")[0], self.path))
                if self.path == "/sent":
                    site.state["sent"].append(body)
                elif self.path == "/clicked":
                    site.state["clicked"].append(body)
                self._send(200, "ok", "text/plain")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.profiles = 0
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def page(self, mode: str) -> str:
        p = self.parts
        top = {"captcha": '<script>addEventListener("load",()=>{document.querySelector('
                          '"[data-fake=captcha]").style.display="block"})</script>',
               "signed_out": p["SIGNED_OUT"],
               "signs_in_later": p["SIGNED_OUT"] + '<script>setTimeout(()=>document.'
                                 'querySelector("[data-fake=signed_out]").remove(),1500)'
                                 '</script>',
               "unusual": "<h1>Our systems have detected unusual traffic from your "
                          "computer network</h1>",
               "verify": "<h2>Verify you are human by completing the action below.</h2>",
               "notice": p["NOTICE"]}.get(mode, "")
        return (PAGE.replace("%NAME%", self.m.NAME).replace("%MODE%", mode)
                .replace("%TOP%", top).replace("%OLDREPLY%", p["OLDREPLY"])
                .replace("%INPUT%", p["INPUT"]).replace("%SEND%", p["SEND"])
                .replace("%STOP%", p["STOP"]).replace("%CAPTCHA%", p["CAPTCHA"])
                .replace("%PATHS%", json.dumps(list(CHAT_PATHS[self.key])))
                .replace("%REPLY%", json.dumps(p["REPLY"]))
                .replace("%OWN%", json.dumps(p["OWN"]))
                .replace("%SOURCES%", json.dumps(p["SOURCES"])))

    def reset(self, mode="normal"):
        self.state["mode"] = mode
        for k in ("sent", "clicked", "requests"):
            self.state[k].clear()

    def adapter(self, *, sign_in_hosts=("localhost",), settle=1.0):
        self.profiles += 1
        cls = type(self.m._factory())
        return cls(start_url=self.base + self.start_path, chat_hosts=("127.0.0.1",),
                   sign_in_hosts=sign_in_hosts,
                   profile=_TMP / f"{self.key}-profile{self.profiles}",
                   type_delay_ms=5, settle_seconds=settle, open_wait=10)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def wait_reply(a, most=30.0):
    end = time.monotonic() + most
    while time.monotonic() < end:
        r = a.read_reply(1.0)
        if r is not None:
            return r
    return None


def expected_first(fs: FakeSite) -> str:
    if fs.key != "perplexity":
        return "2 plus 2 is 4."
    return ("2 plus 2 is 4.\n\nSources listed by Perplexity (links not opened):\n"
            f"1. Source one - http://localhost:{fs.port}/source-1\n"
            f"2. Source two - http://localhost:{fs.port}/source-2")


# ==========================================================================
#   Against a real browser, per site
# ==========================================================================

def t_full_turn(fs: FakeSite):
    k = fs.key
    fs.reset()
    a = fs.adapter()
    try:
        a.open()
        st = a.status()
        check(f"{k}: the fake chat page opens and is 'ok' (the sidebar's 'verify it's you' "
              "is not read as a warning)", st == CB.OK, st)
        a.send("What is 2 plus 2?")
        check(f"{k}: the exact words arrived, once",
              fs.state["sent"] == ["What is 2 plus 2?"], fs.state["sent"])
        early = a.read_reply(0.2)
        check(f"{k}: while the reply is still being written, read_reply() answers None",
              early is None, early)
        reply = wait_reply(a)
        check(f"{k}: the complete reply comes back, and only it", reply == expected_first(fs),
              reply)
        roles = ["input", "send", "stop", "reply"] + \
            [r for r in ("reply_text", "sources") if r in fs.m.SELECTORS]
        firsts = {r: a.matched.get(r, (None,))[0] for r in roles}
        check(f"{k}: the first selector of every role is the one that matched",
              all(v == 1 for v in firsts.values()), firsts)
        time.sleep(1.0)
        check(f"{k}: the site naming the new chat ({CHAT_PATHS[k][0]}) is not 'another chat'",
              a.status() == CB.OK, a.status())
        t0 = time.monotonic()
        a.send("line one\nline two")
        check(f"{k}: a line break is typed as a line break: one message, not two",
              fs.state["sent"] == ["What is 2 plus 2?", "line one\nline two"],
              fs.state["sent"])
        r2 = wait_reply(a)
        took = time.monotonic() - t0
        want = "Reply 2: here is a streamed answer that grows word by word."
        check(f"{k}: a reply that pauses mid-way is not cut short, and the NEWEST is read",
              r2 is not None and r2.split("\n\nSources")[0] == want and took >= 2.5,
              (r2, round(took, 2)))
        check(f"{k}: no old chat or sidebar words ever came back",
              "SIDEBAR" not in (reply or "") + (r2 or "") and "OLD-REPLY" not in (r2 or ""))
        # The fake opens the other chat 2.5 seconds after the reply ends.
        end = time.monotonic() + 8
        st = a.status()
        while st.state == "ok" and time.monotonic() < end:
            time.sleep(0.25)
            st = a.status()
        check(f"{k}: a DIFFERENT chat opened in the window: needs_owner, never read",
              st.state == "needs_owner" and st.reason == "a different chat is showing", st)
        refused = False
        try:
            a._navigate(f"http://localhost:{fs.port}/somewhere")
        except PermissionError:
            refused = True
        check(f"{k}: the adapter refuses to open another host", refused)
        time.sleep(0.3)
        hosts = {h for h, _ in fs.state["requests"]}
        paths = [p for _, p in fs.state["requests"]]
        check(f"{k}: nothing was requested from another host; no source link was opened",
              hosts == {"127.0.0.1"} and not any(p.startswith("/source") for p in paths)
              and "/somewhere" not in paths, fs.state["requests"])
    finally:
        t = threading.Thread(target=a.close)
        t.start()
        t.join(40)
    check(f"{k}: close() works from another thread", not t.is_alive() and a._ctx is None)
    a.close()
    check(f"{k}: close() twice does not raise, and the page is then 'gone'",
          a.status().state == "gone")
    raised = False
    try:
        a.send("hello")
    except RuntimeError:
        raised = True
    check(f"{k}: nothing can be sent after close()", raised)


def t_talk_about_warnings(fs: FakeSite):
    k = fs.key
    fs.reset("unusual_in_reply")
    a = fs.adapter()
    try:
        a.open()
        a.send("Tell me about account checks")
        reply = wait_reply(a)
        check(f"{k}: a reply that TALKS about 'unusual activity' is not a warning page",
              reply is not None and a.status() == CB.OK, a.status())
    finally:
        a.close()


def t_needs_owner(fs: FakeSite):
    k = fs.key
    cases = [("captcha", "captcha"), ("login_dom", "login"), ("login_redirect", "login"),
             ("signed_out", "login"), ("unusual", "unusual"), ("verify", "unusual"),
             ("notice", "a notice is open over the page")]
    if k in LOGIN_PATHS:
        cases.append(("login_path", "login"))
    for mode, reason in cases:
        fs.reset(mode)
        a = fs.adapter()
        try:
            a.open()
            st = a.status()
            refused = False
            try:
                a.send("What is 2 plus 2?")
            except RuntimeError:
                refused = True
            time.sleep(0.2)
            check(f"{k} {mode}: needs_owner ({reason!r}); send() refuses; nothing typed, "
                  "sent or clicked",
                  st.state == "needs_owner" and st.reason == reason and refused
                  and fs.state["sent"] == [] and fs.state["clicked"] == [],
                  (st, refused, fs.state["sent"], fs.state["clicked"]))
        finally:
            a.close()
    fs.reset("captcha_after_send")
    a = fs.adapter()
    try:
        a.open()
        a.send("What is 2 plus 2?")
        early = a.read_reply(1.0)
        st = a.status()
        time.sleep(0.3)
        check(f"{k}: a captcha that appears after sending: no reply, needs_owner, never "
              "clicked", early is None and st.state == "needs_owner" and st.reason == "captcha"
              and fs.state["clicked"] == [], (early, st))
    finally:
        a.close()
    fs.reset("leave_after_send")
    a = fs.adapter(sign_in_hosts=())
    try:
        a.open()
        a.send("Hello")
        time.sleep(1.0)
        st = a.status()
        check(f"{k}: a page that sends the window to another host: needs_owner, says where",
              st.state == "needs_owner" and st.reason == "a page on localhost", st)
    finally:
        a.close()


def t_sign_in_and_self_check(fs: FakeSite):
    k, m = fs.key, fs.m
    fs.reset("signs_in_later")
    a = fs.adapter()
    lines = []

    def out(line):
        lines.append(line)
        if line.startswith("Signed in"):
            threading.Thread(target=a.close).start()   # the owner closes the window
    code = m.sign_in(out=out, adapter=a, wait=30)
    check(f"{k}: the sign-in helper waits, says when it is done, in {m.NAME}'s words, and "
          f"asks for the SPARE {m.SITE.account}; typed and clicked nothing",
          code == 0 and any(line.startswith(f"Signed in: {m.NAME}'s message box") for line in lines)
          and any(f"SPARE {m.SITE.account}" in line for line in lines)
          and fs.state["sent"] == [] and fs.state["clicked"] == [] and a._ctx is None, lines)
    check(f"{k}: a finished sign-in is noted in that window's profile folder",
          W.signed_in_marker(a.profile).is_file())
    fs.reset("check")
    lines = []
    report = _TMP / f"{k}-check.txt"
    code = m.self_check(out=lines.append, adapter=fs.adapter(), report=report, reply_wait=30)
    fails = [line for line in lines if line.startswith("FAIL")]
    check(f"{k}: the owner's self-check passes every step against the fake page (the site "
          f"naming the chat {CHAT_PATHS[k][0]} included), sending only the two fixed "
          "questions in that one chat, and saves its results",
          code == 0 and not fails and any("it says 4" in line for line in lines)
          and any("it says 6" in line for line in lines)
          and fs.state["sent"] == [W.CHECK_QUESTION, W.CHECK_QUESTION_2] and report.is_file()
          and any(f"{m.NAME}'s chat page is showing" in line for line in lines), lines)
    if k == "perplexity":
        check("perplexity: the self-check notes which selector read the sources, without "
              "counting it as a pass or a fail",
              any(line.startswith("NOTE  Sources read as text: selector 1") for line in lines)
              and "14 pass, 0 fail" in lines, lines)
    # A wrong guess at the site's new-chat address is caught HERE, not on the
    # second message of a real conversation (audit, 2026-09-28).
    fs.reset("check")
    lines = []
    wrong = fs.adapter()
    wrong._chat_re = re.compile(r"^/not-this-site/")
    code = m.self_check(out=lines.append, adapter=wrong, report=report, reply_wait=8)
    fails = [line for line in lines if line.startswith("FAIL")]
    check(f"{k}: a wrong chat_address FAILs the self-check and names the line to update",
          code == 1 and len(fails) == 1
          and f"chat_address line in {m.SITE.module}" in fails[0], lines)


def t_through_the_driver():
    """Perplexity through the whole driver: its sources reach the transcript
    as outside text."""
    fs = FAKES["perplexity"]
    CB._reset_for_tests()
    CARDS.clear()
    fs.reset()
    a = fs.adapter()
    d = _deps(a)
    s = CB.plan("perplexity_web", "What is 2 plus 2?", max_turns=1, deps=d)
    check("perplexity via the driver: planned with no problem", not s.problem, s.problem)
    code, _ = CB.start(s, deps=d, wait=True)
    turns = s.transcript
    check("perplexity via the driver: one card, the goal sent word for word, and the "
          "reply WITH its sources in the transcript as outside text",
          code == 202 and len(CARDS) == 1 and fs.state["sent"] == ["What is 2 plus 2?"]
          and len(turns) == 2 and turns[1]["outside_text"] is True
          and turns[1]["text"] == expected_first(fs), (code, len(CARDS), turns))
    check("perplexity via the driver: it ended at its limit and closed the window",
          s.state == "done" and a._ctx is None, s.state)
    CB._reset_for_tests()


# ==========================================================================
#   Plumbing
# ==========================================================================

CARDS: list = []
FAKES: dict = {}


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


def _run(fn, *args):
    label = fn.__name__ + (f"[{args[0].key}]" if args else "")
    print(f"--- {label} ---")
    try:
        fn(*args)
    except Exception as exc:  # pragma: no cover
        traceback.print_exc()
        check(f"{label} ran without crashing", False, repr(exc))


def main(argv):
    only = [k for k in argv if k in SITE_FILES] or list(SITE_FILES)
    xvfb = None
    try:
        for fn in (t_still_true_no_proxy_no_captcha_solving, t_the_base_launches_one_visible_real_browser, t_site_files_are_thin,
                   t_selector_tables, t_registered_and_ready, t_shipped_and_documented):
            _run(fn)
        skip = ""
        if not W.playwright_installed():
            skip = "playwright is not installed"
        else:
            xvfb, skip = _screen()
        if not skip:
            for k in SITE_FILES:
                FAKES[k] = FakeSite(k)
            probe = FAKES["gemini"].adapter()
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
            for k in only:
                for fn in (t_full_turn, t_talk_about_warnings, t_needs_owner,
                           t_sign_in_and_self_check):
                    _run(fn, FAKES[k])
            if "perplexity" in only:
                _run(t_through_the_driver)
    finally:
        for fs in FAKES.values():
            fs.close()
        if xvfb is not None:
            xvfb.terminate()
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
