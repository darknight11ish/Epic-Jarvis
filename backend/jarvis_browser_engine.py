"""jarvis_browser_engine.py - which browser Jarvis uses for a web task: the
VISIBLE one (Playwright's Chromium or Edge, a window you can see and take over)
or the HEADLESS one (Obscura, no window).

NEW MODULE, shipped whole (apply-patches.ps1 copies it beside jarvis_hud.py;
browser-engine.patch adds the gate lines and one install() block). It sits
between the model's `browser_control` tool and the two engines. It owns the
switch (off by default, ON is ONE approval card), the default-mode setting, the
rule that picks an engine, the plain-words status both apps show, and the
routes. The driver that starts and talks to Obscura is jarvis_obscura.py; every
permission rule for STEPS is still jarvis_browser_control.py's.

THE OWNER'S DECISION (2026-09-29, given several times after the risk was
explained): Obscura, with its `--stealth` mode ON for everything it runs, as an
option Jarvis can choose per task - headless (Obscura) or visible (the existing
browser) - for tasks that need a browser.

THE ONE PERMISSION MODEL - nothing here is a shortcut
  * OFF by default. Turning it ON raises ONE approval card (gate action
    `obscura_enable`, tier ask, a new program on this PC and a new way to reach
    the web); OFF is immediate and also stops the program. Held on a stale link
    and behind App lock like every other switch (both are the apps' rules).
  * The card is not the last word. Every page Jarvis opens, every click, every
    box it fills goes through the SAME `browser_control` plan card as the
    visible browser: one card listing every step in full, each step re-checked
    just before it runs, a fence on the sites the card named. Choosing the
    headless engine changes which browser runs the steps, never who is asked.
  * Nothing here can act outside an approved plan: the engine's methods
    (open, click, fill, ...) refuse unless called from inside an approved run
    (`approved_run`); a test proves a bare call is refused.
  * A page it reads is OUTSIDE TEXT: the tool result is marked exactly like the
    visible browser's (jarvis_agent's took_in), the conversation is tainted,
    nothing from it is ever learned as a fact, notes written afterwards ask.
  * Jarvis never types a password, a saved secret or anything from memory, mail
    or files into a page in headless mode: a `<secret>` step and a password box
    are refused at plan time (rule 1). Sign-in needs the visible browser.
  * Running the page's own script (evaluate), cookies and storage, saving files,
    tabs and key presses are not offered by the driver at all (jarvis_obscura.
    ALLOWED_TOOLS). Their own switch and card would be needed; none is built.
  * Obscura's guard against private addresses stays ON and, before it is even
    asked, this module refuses any address that leads to this PC, the home
    network, Tailscale or NordVPN Meshnet (jarvis_local_http.private_fetch_
    problem). There is NO proxy setting anywhere.
  * Jarvis never solves a captcha. Reaching a captcha, an "are you human" page or
    a sign-in page in headless mode STOPS the run and says, in words, to ask
    again with the visible browser (where the owner can take over).

WHICH BROWSER: THE RULE (choose())
  The model may pass mode: "auto" (default), "headless" or "visible".
    visible   the visible browser, always.
    headless  the headless browser; if it cannot run (switch off, not installed,
              changed) the task is REFUSED in words - never silently moved to the
              visible browser (which would open a window nobody expected), and
              never silently run the other way.
    auto      the owner's default in Settings (Automatic, Visible or Headless)
              decides. Automatic means: VISIBLE when the owner might need to sign
              in or take over (the words sign in, log in, password, captcha,
              verify, checkout, pay, buy, order, account, code appear in the goal
              or a step; a `<secret>` step; a step this engine cannot do - reading
              a message list), or when headless cannot run; HEADLESS for plain
              reading and quick lookups (open a page, read it, follow a link, fill
              a search box). "Visible" and "Headless" defaults are followed when
              they can be; a headless default that cannot run falls back to the
              visible browser and the card SAYS SO on its first line.
  The card always names the engine on its first line, and why.

WHY THE CHATBOT DRIVER AND THE SUPPORT CHATS KEEP THE VISIBLE BROWSER
  They must hand a captcha, a sign-in or an "are you a bot?" question to the
  owner in a window - and Jarvis's own rules for them say the window is
  visible and driven openly. This module does not touch them.

WHAT THE HEADLESS ENGINE CANNOT DO (said plainly)
  It has no window: nothing to hand over. It cannot read a message list ("read_new"),
  cannot keep a login between tasks (no cookies are ever saved), cannot download
  a file, and sees only the page's text and its boxes and links, not a picture
  (a screenshot method exists for the driver; nothing gives the picture to a
  model). `--stealth` does not defeat interactive challenges or captchas.

Standard library only (Playwright is only imported, lazily, by the visible
engine's own methods).
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import urllib.parse
import uuid as _uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Optional

try:
    import jarvis_framework as fw
except Exception:  # pragma: no cover - shipped beside it on the PC
    fw = None  # type: ignore

import jarvis_obscura as OB  # noqa: E402 - shipped beside it

# --------------------------------------------------------------------------
#   Names
# --------------------------------------------------------------------------

ACTION = "obscura_enable"
PATH = "/api/browser/engine"
ENGINES = ("visible", "headless")
MODES = ("auto", "visible", "headless")
DEFAULT_MODE = "auto"

#: The fixed words, the same in both apps (tools/gen_browser_cases.py hands
#: them to a test each app runs).
WORDS = {
    "title": "Headless browser (Obscura)",
    "detail": (
        "Jarvis normally works a web page in a browser window you can see. This adds a second "
        "way: Obscura, a small browser with no window, for plain reading and quick lookups. Jarvis "
        "chooses per task - the visible window when you might need to sign in or take over, the "
        "headless browser for simple reading. Every page it opens and every step it takes is still "
        "listed on an approval card first. What it reads is outside text: it never becomes a fact "
        "Jarvis remembers. It cannot reach your own network (this PC, your home network, "
        "Tailscale), uses no proxy, keeps no cookies and saves no files. Off by default. Turning "
        "it on asks first, because it is a new program on your PC that reaches the web."),
    "switch": "Let Jarvis use the headless browser (Obscura)",
    "mode_title": "Which browser Jarvis uses",
    "modes": {
        "auto": "Automatic (recommended)",
        "visible": "Always the visible browser",
        "headless": "The headless browser when it can run",
    },
    "mode_help": {
        "auto": ("Jarvis picks per task: the visible window whenever you might need to sign in "
                 "or take over, the headless browser for plain reading."),
        "visible": "Jarvis always opens the browser window you can see and take over.",
        "headless": ("Jarvis uses the headless browser whenever it can run, but never for a "
                     "sign-in. If it cannot run, Jarvis says so and uses the visible browser."),
    },
    "stealth": (
        "Stealth is always on for the headless browser. It makes the browser look like an "
        "ordinary Chrome. It does not solve captchas, and sites can still block or ban it. "
        "Signing in to a real account with it could get that account closed under a site's terms, "
        "so Jarvis never signs in with it and never solves a captcha: at one it stops and hands the "
        "job to the visible browser."),
    "off_line": "Off. Jarvis uses the visible browser window only.",
    "waiting_line": "Waiting for your yes on the card. Nothing has changed yet.",
    "unread": "Could not read this setting.",
    "missing": ("This PC's Jarvis does not have the headless browser yet. Run "
                "scripts\\apply-patches.ps1 on the PC to add it."),
    "steps_title": "To install it, paste this one line into PowerShell on your PC:",
    "steps_note": (
        "It downloads Obscura's Windows program from its GitHub releases (github.com/h4ckf0r0day/"
        "obscura, Apache-2.0), unpacks it into Jarvis's own folder and checks it: version, stealth on, "
        "and that it refuses to visit your own network. Jarvis never downloads it by itself."),
}

#: The plain reason the headless engine cannot run right now, by code.
NOT_READY = {
    "off": "The headless browser is switched off.",
    "missing": WORDS["missing"],
}

#: What a headless run says when it reaches a page that wants a person.
NEEDS_OWNER = {
    "captcha": "an \"are you human\" check or captcha",
    "signin": "a sign-in page",
}
HANDOVER = ("This page wants a person ({what}). The headless browser has no window and never solves "
            "a captcha or signs in, so Jarvis stopped. To carry on, ask again with the visible "
            "browser (say \"use the visible browser\"): its window opens and you can take over.")

_SIGN_WORDS = re.compile(
    r"\b(sign[ -]?in|sign[ -]?up|log[ -]?in|login|password|passcode|captcha|verify|verification|"
    r"check[ -]?out|payment|pay|buy|purchase|order|credit card|account|2fa|two[- ]factor|"
    r"one[- ]time|otp|security code)\b", re.I)
#: A sign-in page says so in its title or its address. (Only those two: many
#: ordinary pages hold a hidden log-in box in a menu, and the words "Log in" sit in
#: their top text, so a password box alone - or the words in the body - would stop
#: every plain lookup on such a site.)
_SIGNIN_HINT = re.compile(
    r"\b(sign[ -]?in|sign[ -]?on|log[ -]?in|login|logon|sso|oauth|authenticate|"
    r"sign[ -]?up|register|password)\b", re.I)
_CHALLENGE_WORDS = re.compile(
    r"\b(captcha|are you (?:a )?(?:human|robot)|verify (?:that )?you are (?:a )?human|"
    r"confirm (?:that )?you are (?:a )?human|just a moment|attention required|"
    r"checking (?:your browser|if the site connection is secure)|unusual traffic|"
    r"press (?:and|&) hold|not a robot|access denied|request blocked)\b", re.I)


class EngineUnavailable(RuntimeError):
    """The chosen engine cannot run; `str(exc)` is the plain-words reason."""


class EngineRefused(RuntimeError):
    """A call the engine refuses (outside an approved run, or not allowed)."""


# --------------------------------------------------------------------------
#   Files and settings
# --------------------------------------------------------------------------


def _config_dir() -> Path:
    mod = sys.modules.get("jarvis_framework") or fw
    if mod is not None:
        try:
            return Path(mod.CONFIG_DIR)
        except Exception:
            pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR") or os.environ.get("JARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


def settings_path() -> Path:
    return _config_dir() / "browser-engine.json"


_SETTINGS_LOCK = threading.Lock()
_DAMAGED = ("the browser settings file is damaged, so the headless browser stayed off. Turn it on "
            "again to rewrite it")


def settings() -> dict:
    """{"obscura", "mode", "why"}. No file: off, Automatic. A file that cannot be
    read, is not JSON, or holds a wrong kind of value: the headless browser OFF
    (the safe direction) and `why` says so; an unknown mode reads as Automatic."""
    try:
        raw = settings_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"obscura": False, "mode": DEFAULT_MODE, "why": ""}
    except OSError as exc:
        return {"obscura": False, "mode": DEFAULT_MODE,
                "why": f"the browser settings file could not be read ({type(exc).__name__}), so "
                       f"the headless browser stayed off"}
    try:
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            raise ValueError
    except Exception:
        return {"obscura": False, "mode": DEFAULT_MODE, "why": _DAMAGED}
    on = doc.get("obscura", False)
    if not isinstance(on, bool):
        return {"obscura": False, "mode": DEFAULT_MODE, "why": _DAMAGED}
    mode = doc.get("mode", DEFAULT_MODE)
    return {"obscura": on, "mode": mode if mode in MODES else DEFAULT_MODE, "why": ""}


def _save(**changes) -> dict:
    with _SETTINGS_LOCK:
        cur = settings()
        new = {"obscura": cur["obscura"], "mode": cur["mode"]}
        new.update(changes)
        p = settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(dict(new, changed=time.time())), encoding="utf-8")
        os.replace(tmp, p)
    return settings()


def set_obscura(on: bool) -> dict:
    """Writes the switch. OFF also stops the program at once."""
    on = bool(on)
    out = dict(_save(obscura=on), ok=True)
    if not on:
        stop_all("switched off")
    return out


def set_mode(mode) -> dict:
    if mode not in MODES:
        return {"ok": False, "error": f"mode must be one of {', '.join(MODES)}"}
    return dict(_save(mode=mode), ok=True)


def _audit(event: str, detail: dict) -> None:
    try:
        mod = sys.modules.get("jarvis_framework") or fw
        if mod is not None:
            mod.audit_log(event, detail)
    except Exception:
        pass


# --------------------------------------------------------------------------
#   Can the headless engine run right now, and which engine does a task get
# --------------------------------------------------------------------------


def ready() -> tuple:
    """(True, "") or (False, plain words why not). Switch on, the program installed,
    checked and unchanged."""
    if not settings()["obscura"]:
        return False, NOT_READY["off"]
    prob = OB.problem()
    if prob:
        return False, OB.WHY.get(prob, OB.WHY["error"])
    return True, ""


def headless_offered() -> bool:
    """Should the browser tool be offered to the model even without the second
    graphics card? Yes when the headless engine can run: its page reads are the
    same small pieces the visible one's are (jarvis_agent.offered_tools)."""
    try:
        return ready()[0]
    except Exception:
        return False


def _request_text(goal, requests) -> str:
    parts = [str(goal or "")]
    for r in requests or []:
        if isinstance(r, dict):
            parts += [str(r.get("name") or ""), str(r.get("why") or ""),
                      str(r.get("value") or "") if r.get("action") == "navigate" else "",
                      str(r.get("role") or "")]
    return " ".join(parts)


def reject_request(engine: str, r) -> Optional[str]:
    """Why the HEADLESS engine will not take this one request, or None. Called by
    jarvis_browser_control.plan for every request when the plan is headless."""
    if engine != "headless" or not isinstance(r, dict):
        return None
    value = r.get("value")
    if isinstance(value, str) and "<secret>" in value:
        return ("the headless browser never types a saved secret or password - sign-in needs the "
                "visible browser")
    if str(r.get("action") or "") == "read_new":
        return "the headless browser cannot read a message list - use the visible browser for that"
    return None


VISIBLE_UNAVAILABLE = ("the visible browser is not available: it needs the second graphics card's "
                       "\"Browser control\" switch, which is off")


def visible_available() -> tuple:
    """(True, "") or (False, words). The visible browser keeps the rule it always
    had: it works only while the second graphics card's "Browser control" lane
    does (page after page of history does not fit the main card's 16K). The
    headless engine reads a page in the same small pieces and does not need it."""
    try:
        import jarvis_second_card as SC
        if SC.lane_for("browser_control") is not None:
            return True, ""
    except Exception:
        pass
    return False, VISIBLE_UNAVAILABLE


def choose(requested=None, *, goal="", requests=None) -> dict:
    """{"engine": "visible"|"headless", "why": words for the card's first line,
    "refused": ""|words}. The rule is in the module docstring."""
    pick = _choose(requested, goal=goal, requests=requests)
    if pick["engine"] == "visible" and not pick["refused"]:
        ok, why = visible_available()
        if not ok:
            more = (" Turn that switch on, or ask for something the headless browser can do "
                    "(plain reading).") if settings()["obscura"] else ""
            return {"engine": "visible", "why": "", "refused": (
                "This task needs the visible browser" +
                (f" ({pick['why']})" if pick["why"] else "") + ", but " + why +
                ". Nothing was opened." + more)}
    return pick


def _choose(requested=None, *, goal="", requests=None) -> dict:
    requested = requested if requested in MODES else "auto"
    ok, not_ready = ready()
    if requested == "visible":
        return {"engine": "visible", "why": "you or Jarvis asked for the visible browser",
                "refused": ""}
    if requested == "headless":
        if not ok:
            return {"engine": "visible", "why": "", "refused": (
                "The headless browser was asked for but cannot run: " + not_ready +
                " Jarvis did not switch to the visible browser by itself; ask again with "
                "\"use the visible browser\" if you want that.")}
        if any(reject_request("headless", r) for r in (requests or [])):
            return {"engine": "visible", "why": "", "refused": (
                "The headless browser was asked for, but a step needs something it never does "
                "(a saved secret or a message list). Ask again with the visible browser.")}
        return {"engine": "headless", "why": "headless was asked for", "refused": ""}
    default = settings()["mode"]
    if default == "visible":
        return {"engine": "visible", "why": "your setting is always the visible browser",
                "refused": ""}
    if not ok:
        if default == "headless" or settings()["obscura"]:
            why = ("the headless browser cannot run right now (" + not_ready.rstrip(".") +
                   "), so Jarvis is using the visible browser")
        else:
            why = ""                 # it is simply off: nothing to explain on every card
        return {"engine": "visible", "why": why, "refused": ""}
    if any(reject_request("headless", r) for r in (requests or [])):
        return {"engine": "visible", "why": ("a step needs something the headless browser never "
                                             "does (a saved secret or a message list)"),
                "refused": ""}
    if default == "auto" and _SIGN_WORDS.search(_request_text(goal, requests)):
        return {"engine": "visible", "why": ("this looks like it may need you to sign in, pay or "
                                             "take over, and the headless browser has no window"),
                "refused": ""}
    return {"engine": "headless", "why": ("this is plain reading, and the headless browser is "
                                          "on" if default == "auto" else
                                          "your setting is the headless browser"), "refused": ""}


def card_line(engine: str, why: str) -> str:
    """The first line of the plan card: which browser, and why."""
    if engine == "headless":
        return (f"Browser: HEADLESS (Obscura, no window) - {why}. Stealth is on: it looks like an "
                f"ordinary Chrome, which does not stop a site blocking it. It cannot reach your "
                f"own network and stops at any captcha or sign-in page.")
    return f"Browser: VISIBLE (a window you can see and take over){' - ' + why if why else ''}."


# --------------------------------------------------------------------------
#   Reading what Obscura returns (pure functions, tested on plain text)
# --------------------------------------------------------------------------

_ELEM_LINE = re.compile(
    r'^ref=(e\d{1,4})\s+(\S+)\s+"((?:[^"\\]|\\.)*)"(?:\s+name="((?:[^"\\]|\\.)*)")?\s*$')
_SNAP = re.compile(r"\AURL: (.*?)\nTitle: (.*?)\n\n(.*)\Z", re.S)
_SNAP_TAIL = re.compile(r"\n\n\d+ interactive element\(s\) registered\..*\Z", re.S)
_UNESC = re.compile(r'\\(u\{[0-9a-fA-F]{1,6}\}|.)')
_SENSITIVE_NAME = re.compile(r"card number|cvv|cvc|security code|one[- ]time|otp|ssn|passcode",
                             re.I)
_MAX_ELEMS = 300


def _unescape(s: str) -> str:
    """Undoes Rust's {:?} escaping of a string."""
    def one(m):
        t = m.group(1)
        if t.startswith("u{"):
            try:
                return chr(int(t[2:-1], 16))
            except (ValueError, OverflowError):
                return ""
        return {"n": "\n", "t": "\t", "r": "\r", "0": "\0"}.get(t, t)
    return _UNESC.sub(one, s)


def parse_snapshot(text: str) -> dict:
    """{"url", "title", "body"} from browser_snapshot's text."""
    m = _SNAP.match(text or "")
    if not m:
        return {"url": "", "title": "", "body": (text or "")}
    body = _SNAP_TAIL.sub("", m.group(3)).strip()
    return {"url": m.group(1).strip(), "title": m.group(2).strip(), "body": body}


def role_for(kind: str) -> tuple:
    """(role, password?, sensitive?, interactive?) for one `tag[type]` /
    `tag[role=x]` kind string from browser_interactive_elements."""
    tag, _, rest = kind.partition("[")
    rest = rest.rstrip("]")
    typ = rest[len("role="):] if rest.startswith("role=") else rest
    is_role = rest.startswith("role=")
    if is_role:
        return typ or "generic", False, False, True
    if tag == "a":
        return "link", False, False, True
    if tag == "button":
        return "button", False, False, True
    if tag == "select":
        return "combobox", False, False, True
    if tag == "textarea":
        return "textbox", False, False, True
    if tag == "input":
        if typ in ("button", "submit", "reset", "image"):
            return "button", False, False, True
        if typ == "checkbox":
            return "checkbox", False, False, True
        if typ == "radio":
            return "radio", False, False, True
        if typ == "password":
            return "textbox", True, True, True
        if typ in ("file", "hidden"):
            return "textbox", False, True, True
        return "textbox", False, False, True
    return tag or "generic", False, False, True


def parse_elements(text: str) -> list:
    """The records jarvis_browser_control.plan matches against, from
    browser_interactive_elements' lines: {"role","name","text","enabled",
    "interactive","sensitive","password","within_role","within_name","ref"}.
    A line that does not fit is dropped, never guessed at."""
    out = []
    for line in (text or "").splitlines():
        if len(out) >= _MAX_ELEMS:
            break
        m = _ELEM_LINE.match(line.rstrip("\r"))
        if not m:
            continue
        ref, kind, label, name_attr = m.group(1), m.group(2), _unescape(m.group(3)), \
            _unescape(m.group(4) or "")
        role, password, sensitive, interactive = role_for(kind)
        name = re.sub(r"\s+", " ", label.strip() or name_attr.strip())[:200]
        if not name:
            continue
        sensitive = sensitive or bool(_SENSITIVE_NAME.search(name))
        out.append({"role": role, "name": name, "text": name, "enabled": True,
                    "interactive": interactive, "sensitive": sensitive, "password": password,
                    "within_role": "", "within_name": "", "ref": ref})
    return out


def wants_a_person(url: str, title: str, body: str, elements: Optional[list] = None) -> str:
    """"" or "captcha" / "signin": does this page want a person? Plain words and
    shapes; it looks at the title and the first part of the text only (a long
    article that mentions "captcha" is not a captcha page). A sign-in page is a
    password box plus "sign in" / "log in" in the title or the address."""
    head = f"{title}\n{(body or '')[:600]}"
    if _CHALLENGE_WORDS.search(head):
        return "captcha"
    if any(e.get("password") for e in (elements or [])):
        path = urllib.parse.urlsplit(url or "").path
        if _SIGNIN_HINT.search(f"{title}\n{path}"):
            return "signin"
    return ""


# --------------------------------------------------------------------------
#   The engines. One small interface; acting needs an approved run.
# --------------------------------------------------------------------------

_APPROVED = threading.local()


@contextmanager
def approved_run():
    """Entered only by the hooks jarvis_browser_control.run hands to an APPROVED
    plan. Every page-touching method of an engine checks it: a caller that did
    not come through an approved plan is refused."""
    prior = getattr(_APPROVED, "on", False)
    _APPROVED.on = True
    try:
        yield
    finally:
        _APPROVED.on = prior


def _need_approval() -> None:
    if not getattr(_APPROVED, "on", False):
        raise EngineRefused("a browser action needs an approved plan; nothing was done")


class Engine:
    """The interface. Every method except `status`/`close` refuses outside an
    approved run. `session` is the label a plan gave its tab."""
    name = ""

    def status(self) -> dict: raise NotImplementedError
    def open(self, url: str) -> None: raise NotImplementedError
    def text(self, offset: int = 0) -> str: raise NotImplementedError
    def snapshot(self) -> dict: raise NotImplementedError
    def markdown(self) -> str: raise NotImplementedError
    def links(self, limit: int = 100) -> list: raise NotImplementedError
    def screenshot(self) -> bytes: raise NotImplementedError
    def click(self, role: str, name: str) -> None: raise NotImplementedError
    def fill(self, role: str, name: str, value: str) -> None: raise NotImplementedError
    def submit(self, role: str, name: str) -> None: raise NotImplementedError
    def close(self) -> None: raise NotImplementedError


def _private_problem(url: str) -> str:
    """"" when the address may be visited: http or https, and not leading to this
    PC, the home network, Tailscale or Meshnet."""
    try:
        import jarvis_local_http
        return jarvis_local_http.private_fetch_problem(url)
    except ImportError:  # pragma: no cover - shipped beside it
        return "" if urllib.parse.urlsplit(url).scheme in ("http", "https") else "not a web address"


def _plain_error(text: str) -> str:
    t = re.sub(r"\s+", " ", str(text or "")).strip()[:200]
    low = t.lower()
    if any(w in low for w in ("private", "forbidden", "ssrf", "loopback", "not allowed")):
        return ("the headless browser refused that address on purpose: it never visits this PC, "
                "your home network or Tailscale")
    if "file://" in low or "file:" in low:
        return "the headless browser does not open local files"
    return t or "the headless browser reported an error"


class HeadlessEngine(Engine):
    """Obscura, through jarvis_obscura's driver. One page at a time."""
    name = "headless"

    def __init__(self, driver: Optional[OB.Driver] = None) -> None:
        self._driver = driver
        self.lock = threading.RLock()
        self._fence: Optional[Callable[[str], bool]] = None

    @property
    def driver(self) -> OB.Driver:
        return self._driver or OB.DRIVER

    def status(self) -> dict:
        ok, why = ready()
        return {"engine": "headless", "ready": ok, "why": why, **self.driver.view()}

    # ---- looking --------------------------------------------------------

    def _call(self, tool: str, args: Optional[dict] = None) -> dict:
        try:
            got = self.driver.call(tool, args or {})
        except OB.ObscuraError as exc:
            raise RuntimeError(exc.words()) from None
        return got

    def _events(self, url, title, body, elements=None) -> list:
        why = wants_a_person(url, title, body, elements)
        if not why:
            return []
        return [{"kind": "needs_owner", "why": why,
                 "text": HANDOVER.format(what=NEEDS_OWNER[why])}]

    def read(self, session: str) -> dict:
        """The page for jarvis_browser_control.plan/run: {"url","title","elements",
        "events"}. A blank page - and NO program started - when nothing is open."""
        with self.lock:
            if not self.driver.alive():
                return {"url": "", "title": "", "elements": [], "events": []}
            snap = self._call("browser_snapshot", {"max_chars": 1500})
            page = parse_snapshot(snap["text"])
            els = self._call("browser_interactive_elements", {"limit": _MAX_ELEMS})
            elements = parse_elements(els["text"])
            return {"url": page["url"], "title": page["title"], "elements": elements,
                    "events": self._events(page["url"], page["title"], page["body"], elements)}

    def observe(self, session: str) -> dict:
        """The look after a step: {"url","events"}. It reads the page's boxes too, so
        a sign-in page (a password box) the step landed on is seen right away."""
        with self.lock:
            if not self.driver.alive():
                return {"url": "", "events": []}
            got = self.read(session)
            return {"url": got["url"], "events": got["events"]}

    # ---- the interface --------------------------------------------------

    def open(self, url: str) -> None:
        _need_approval()
        why = _private_problem(url)
        if why:
            raise RuntimeError("the headless browser did not open that address: " + why)
        got = self._call("browser_navigate", {"url": url, "waitUntil": "load"})
        if got["error"]:
            raise RuntimeError(_plain_error(got["text"]))

    def text(self, offset: int = 0) -> str:
        _need_approval()
        import jarvis_browser_control as B
        got = self._call("browser_snapshot", {"max_chars": 60000})
        return B._format_page_text(parse_snapshot(got["text"])["body"], int(offset or 0))

    def snapshot(self) -> dict:
        _need_approval()
        return self.read("")

    def markdown(self) -> str:
        _need_approval()
        return self._call("browser_markdown", {"max_chars": 60000})["text"]

    def links(self, limit: int = 100) -> list:
        _need_approval()
        out = []
        for line in self._call("browser_links", {"limit": int(limit)})["text"].splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if isinstance(d, dict) and d.get("href"):
                out.append({"text": str(d.get("text") or "")[:200], "href": str(d["href"])})
        return out

    def screenshot(self) -> bytes:
        _need_approval()
        got = self._call("browser_screenshot", {})
        if not got["image"]:
            raise RuntimeError("the headless browser could not take a picture")
        return got["image"]

    def _element(self, role: str, name: str) -> dict:
        import jarvis_browser_control as B
        els = parse_elements(self._call("browser_interactive_elements",
                                        {"limit": _MAX_ELEMS})["text"])
        found = B._candidates(els, role, B._norm(name))
        if len(found) != 1:
            raise RuntimeError(f'{role} "{name}" now matches {len(found)} elements - not guessing')
        return found[0]

    def set_fence(self, allowed: Optional[Callable[[str], bool]]) -> None:
        """The sites the approved plan named (jarvis_browser_control._fence_for),
        or None. Set by run() for the length of a run."""
        self._fence = allowed

    def _before_click(self, e: dict) -> None:
        """Obscura follows a link or submits a form the moment it is clicked, and
        has no way to be stopped part-way (the visible browser's route guard has
        none of its counterpart here). So a click that would LEAVE the allowed
        sites is refused BEFORE it is made: a link by its address, a button by
        the address of the form it submits."""
        allowed = self._fence
        if allowed is None:
            return
        base = parse_snapshot(self._call("browser_snapshot", {"max_chars": 0})["text"])["url"]
        if e["role"] == "link":
            raw = self._call("browser_get_attribute",
                             {"ref": e["ref"], "attribute": "href"})["text"].strip()
            if raw:
                target = urllib.parse.urljoin(base, raw)
                if urllib.parse.urlsplit(target).scheme.lower() not in ("http", "https"):
                    raise RuntimeError("that link does not open a web address, so the headless "
                                       "browser did not click it")
                if not allowed(target):
                    raise RuntimeError(f"that link leads to {target}, outside the allowed "
                                       f"sites - the headless browser did not follow it")
            return
        forms = self._call("browser_detect_forms")["text"]
        try:
            doc = json.loads(forms)
        except ValueError:
            return                              # no forms on the page
        for f in doc if isinstance(doc, list) else []:
            if any(isinstance(x, dict) and x.get("ref") == e["ref"] for x in f.get("fields") or []):
                action = str(f.get("action") or "")
                if action:
                    target = urllib.parse.urljoin(base, action)
                    if not allowed(target):
                        raise RuntimeError(f"that button sends its form to {target}, outside the "
                                           f"allowed sites - the headless browser did not press it")

    def click(self, role: str, name: str) -> None:
        _need_approval()
        e = self._element(role, name)
        self._before_click(e)
        got = self._call("browser_click", {"ref": e["ref"]})
        if got["error"]:
            raise RuntimeError(_plain_error(got["text"]))

    def fill(self, role: str, name: str, value: str) -> None:
        _need_approval()
        e = self._element(role, name)
        if e["password"] or e["sensitive"]:
            raise RuntimeError("the headless browser never types into a password or payment box")
        got = self._call("browser_fill", {"ref": e["ref"], "value": str(value)})
        if got["error"]:
            raise RuntimeError(_plain_error(got["text"]))

    def submit(self, role: str, name: str) -> None:
        self.click(role, name)

    def select(self, role: str, name: str, value: str) -> None:
        _need_approval()
        e = self._element(role, name)
        got = self._call("browser_select_option", {
            "selector": f'[data-obscura-ref="{e["ref"]}"]', "value": str(value)})
        if got["error"]:
            raise RuntimeError(_plain_error(got["text"]))

    def value_of(self, role: str, name: str) -> str:
        _need_approval()
        e = self._element(role, name)
        if e["sensitive"]:
            return "(not read back: this is a password, payment, or hidden field)"
        got = self._call("browser_get_attribute", {"ref": e["ref"], "attribute": "value"})
        return got["text"] if not got["error"] and got["text"] else e["text"]

    def close(self) -> None:
        self.driver.close_browser()

    # ---- what jarvis_browser_control.run/plan call ----------------------

    def act(self, step) -> Optional[str]:
        """The `act` hook. Called only by an APPROVED run (jarvis_browser_control.run
        refuses without approved=True), so it opens the approved-run door."""
        with approved_run():
            a = step.action
            if a == "navigate":
                self.open(step.value or "")
                return None
            if a == "read_page":
                return self.text(int(step.value or 0))
            if a == "click":
                self.click(step.role, step.name)
                return None
            if a == "type":
                self.fill(step.role, step.name, step.value or "")
                return None
            if a == "select":
                self.select(step.role, step.name, step.value or "")
                return None
            if a == "read":
                return self.value_of(step.role, step.name)
            raise RuntimeError(f"the headless browser cannot do {a!r} - use the visible browser")


class VisibleEngine(Engine):
    """The existing Playwright browser (jarvis_browser_control's own helpers),
    behind the same interface. Its behaviour is unchanged: browser_control uses
    its own defaults when the engine is visible."""
    name = "visible"

    def __init__(self, session: str = "engine") -> None:
        self.session = session

    def status(self) -> dict:
        return {"engine": "visible", "ready": True, "why": ""}

    def _page(self):
        import jarvis_browser_control as B
        return B._page_for(self.session, create=True)

    def open(self, url: str) -> None:
        _need_approval()
        import jarvis_browser_control as B
        if urllib.parse.urlsplit(url).scheme.lower() not in B._ALLOWED_SCHEMES:
            raise EngineRefused("only http and https addresses are opened")
        self._page().goto(url, wait_until="domcontentloaded", timeout=B._NAV_TIMEOUT_MS)

    def text(self, offset: int = 0) -> str:
        _need_approval()
        import jarvis_browser_control as B
        html = self._page().evaluate(B._MAIN_CONTENT_JS, B._MAX_PAGE_HTML_CHARS)
        return B._format_page_text(B.html_to_text(html or ""), int(offset or 0))

    def snapshot(self) -> dict:
        _need_approval()
        import jarvis_browser_control as B
        return B._default_read(self.session)

    def markdown(self) -> str:
        return self.text(0)

    def links(self, limit: int = 100) -> list:
        _need_approval()
        got = self._page().evaluate(
            "Array.from(document.links).slice(0, %d).map(a => ({text: (a.innerText||'').trim()"
            ".slice(0,200), href: a.href}))" % int(limit))
        return list(got or [])

    def screenshot(self) -> bytes:
        _need_approval()
        return self._page().screenshot()

    def _step(self, action: str, role: str, name: str, value=None):
        import jarvis_browser_control as B
        return B.Step(session=self.session, url="", role=role, name=name, action=action,
                      value=value)

    def click(self, role: str, name: str) -> None:
        _need_approval()
        import jarvis_browser_control as B
        B._default_act(self._step("click", role, name))

    def fill(self, role: str, name: str, value: str) -> None:
        _need_approval()
        import jarvis_browser_control as B
        B._default_act(self._step("type", role, name, value))

    def submit(self, role: str, name: str) -> None:
        self.click(role, name)

    def close(self) -> None:
        import jarvis_browser_control as B
        B.close(self.session)


HEADLESS = HeadlessEngine()
VISIBLE = VisibleEngine()


def engine_for(name: str) -> Engine:
    return HEADLESS if name == "headless" else VISIBLE


class Hooks:
    def __init__(self, eng: HeadlessEngine) -> None:
        self.read, self.observe, self.act, self.close = eng.read, eng.observe, eng.act, eng.close
        self.set_fence = eng.set_fence


def hooks(name: str):
    """What jarvis_browser_control.plan/run use for engine `name`. None for the
    visible engine (browser_control's own Playwright code is unchanged). For the
    headless engine, raises EngineUnavailable in plain words when it cannot run."""
    if name != "headless":
        return None
    ok, why = ready()
    if not ok:
        raise EngineUnavailable(why)
    return Hooks(HEADLESS)


def stop_all(why: str = "stopped") -> None:
    """Stop everything: the headless program goes."""
    for drv in {id(HEADLESS.driver): HEADLESS.driver, id(OB.DRIVER): OB.DRIVER}.values():
        drv.stop(why)


def _stopper() -> Optional[str]:
    """What "Stop everything" (jarvis_stop_all.py) calls: the headless program
    goes, and the answer says so - or None when nothing was running."""
    running = any(d.alive() for d in {id(HEADLESS.driver): HEADLESS.driver,
                                      id(OB.DRIVER): OB.DRIVER}.values())
    stop_all("Stop everything")
    return "The headless browser was stopped." if running else None


def register_stopper() -> bool:
    """Puts the headless browser on Stop everything's list. True when it is there."""
    try:
        import jarvis_stop_all
        jarvis_stop_all.register("headless_browser", _stopper)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
#   The approval card and the switch
# --------------------------------------------------------------------------


def download_line() -> str:
    return OB.install_line()


def describe_on() -> str:
    st = OB.status()
    if st["installed"] and not st["problem"]:
        inst = "Obscura is already installed and checked on this PC."
    elif st["installed"]:
        inst = ("Obscura is on this PC, but Jarvis will not start it yet: " +
                OB.WHY.get(st["problem"], "") + " This card changes nothing about the file.")
    else:
        inst = ("Obscura is not installed yet. The switch will be on, but the headless browser "
                "waits until you install it yourself: this card downloads nothing. You install "
                "it with one line in PowerShell (Settings shows it).")
    return (
        "Let Jarvis use a headless browser (Obscura) for plain web reading?\n\n"
        "What it is: a new program on your PC - Obscura, open source (Apache-2.0), a small "
        "browser with no window. Jarvis can choose it, instead of the visible browser, for "
        "reading and quick lookups. Jarvis picks per task and the card for each task names which "
        "browser it will use.\n\n"
        "A new way onto the web: every page it opens is on the internet. Every page, click and box "
        "it fills is still listed on its own approval card first, in full, exactly as for the "
        "visible browser. What it reads counts as outside text: Jarvis never follows instructions "
        "in it and never saves it as a fact.\n\n"
        "Stealth is on, always: it makes the browser look like an ordinary Chrome. It does NOT solve "
        "captchas, and a site can still block it or ban it. Jarvis never signs in with it, never "
        "types a password, and never solves a captcha - at one it stops and hands the job to the "
        "visible browser. Signing in to a real account with any automated browser can get that "
        "account closed under a site's terms.\n\n"
        "Kept apart from your own network: it will not open this PC, your home network, Tailscale or "
        "Meshnet addresses. No proxy is used. Nothing is saved - no cookies, no files. It runs for "
        "a few minutes at most, at most 15 pages at a time, and stops when you turn this off or "
        "press Stop everything.\n\n"
        f"{inst}\n\n"
        "You can turn this off again at any time, from either app, and that is instant.\n\n"
        "If you did not just ask for this, say no.\n\n"
        "If you say no: nothing changes. Jarvis keeps using the visible browser.")


_LOCK = threading.Lock()
_PENDING: dict = {}
_WITHDRAWN: set = set()
_LAST_CARD: dict = {}
_LATEST: dict = {}
_SWITCH = threading.Lock()

LAST_WORDS = {
    "enabled": "You approved the card, so the headless browser is on.",
    "denied": "The card was turned down, so the headless browser stays off.",
    "timed_out": "Nobody answered the card in time, so the headless browser stays off.",
    "refused": "Your PC's settings do not let this be approved, so it stayed off.",
    "withdrawn": "You turned this off while the card waited, so approving it changed nothing.",
    "failed": "It was approved, but the setting could not be saved, so it stayed off.",
}
GATE_FAILED_WORDS = "The approval card could not be raised, so it stayed off."


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tier(action: str) -> str:
    try:
        mod = sys.modules.get("jarvis_framework") or fw
        return str(mod.action_tier(action))
    except Exception as exc:
        return f"unreadable ({type(exc).__name__})"


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-browser-engine-card", daemon=True).start()


def _finish(pid: str, outcome: str, why: str = "", message: Optional[str] = None) -> None:
    with _LOCK:
        if _PENDING.get("id") == pid:
            _PENDING.clear()
        _WITHDRAWN.discard(pid)
        if _LATEST.get("id") not in (None, pid):
            return
        _LAST_CARD.clear()
        _LAST_CARD.update(outcome=outcome, why=why, at=time.time(),
                          message=message or LAST_WORDS.get(outcome, ""))
    _audit("browser_engine.card", {"outcome": outcome})


def _decide(pid: str, apply: Callable[[bool], dict], gate: Callable,
            tier_of: Callable[[str], str]) -> None:
    text = describe_on()
    detail = {"text": text, "what": "use a headless browser (Obscura) to read web pages",
              "program": "Obscura", "stealth": True, "leaves_this_pc": True}
    try:
        v = gate(ACTION, detail, text)
    except Exception as exc:
        return _finish(pid, "refused", f"the approval gate failed ({type(exc).__name__})",
                       GATE_FAILED_WORDS)
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    if vtier != "ask" or tier_of(ACTION) != "ask":
        return _finish(pid, "refused",
                       f"the gate answered at tier {vtier!r}, which is not a person saying yes")
    if not (allowed and outcome == "approved"):
        if outcome in ("denied", "timed_out"):
            return _finish(pid, outcome)
        return _finish(pid, "refused", str(getattr(v, "reason", "refused")))
    with _SWITCH:
        with _LOCK:
            withdrawn = pid in _WITHDRAWN
        if withdrawn:
            return _finish(pid, "withdrawn", "you turned this off while the card was waiting")
        try:
            out = apply(True) or {}
        except Exception as exc:
            return _finish(pid, "failed", f"{type(exc).__name__}")
        if out.get("ok") is False:
            return _finish(pid, "failed", str(out.get("error", "")))
        _finish(pid, "enabled")


def request(enabled, apply: Callable[[bool], dict], *, gate: Optional[Callable] = None,
            tier_of: Optional[Callable[[str], str]] = None,
            spawn: Optional[Callable] = None) -> tuple:
    """POST {"obscura": bool}. ON is 202 while ONE card waits - never "it is on" -
    and changes nothing until a person says yes; OFF is at once."""
    gate = gate or _gate
    tier_of = tier_of or _tier
    spawn = spawn or _spawn
    if not isinstance(enabled, bool):
        return 400, {"error": 'need {"obscura": true|false}'}
    if not enabled:
        with _SWITCH:
            with _LOCK:
                if _PENDING:
                    _WITHDRAWN.add(_PENDING["id"])
                    _PENDING.clear()
            out = dict(apply(False) or {})
        out.setdefault("ok", True)
        out.update(waiting=False, message="The headless browser is off. Jarvis uses the visible "
                                          "browser only.")
        _audit("browser_engine.off", {})
        return 200, out
    if settings()["obscura"]:
        return 200, {"ok": True, "obscura": True, "waiting": False,
                     "message": "The headless browser is already on."}
    tier = tier_of(ACTION)
    if tier != "ask":
        return 503, {"ok": False, "error": (
            f"{ACTION} is tier {tier!r} in jarvis-framework.toml; turning on the headless browser "
            f"needs a person to say yes, so it must be 'ask'")}
    with _LOCK:
        if _PENDING:
            return 202, {"ok": True, "waiting": True, "obscura": False,
                         "message": "A card to turn on the headless browser is already waiting "
                                    "for your approval."}
        pid = _uuid.uuid4().hex
        _PENDING.update(id=pid, since=time.time())
        _LATEST["id"] = pid
    _audit("browser_engine.asked", {})
    try:
        spawn(lambda: _decide(pid, apply, gate, tier_of))
    except Exception:
        with _LOCK:
            _PENDING.clear()
        return 503, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "waiting": True, "obscura": False,
                 "message": "Waiting for your approval. The headless browser turns on only if "
                            "you approve the card, on your PC or phone."}


# --------------------------------------------------------------------------
#   What the apps read
# --------------------------------------------------------------------------


def _date(at: float) -> str:
    try:
        return time.strftime("%d %b %Y", time.localtime(at)).lstrip("0")
    except Exception:
        return ""


def status_line(st: dict) -> str:
    """One plain line about the install, never a word from a web page."""
    if not st["installed"]:
        return "Obscura is not installed on this PC yet."
    if st["problem"] == "changed":
        return ("Installed, but the file has changed since it was checked - Jarvis will not "
                "start it until you run the install line again.")
    if st["problem"] == "not_checked":
        return "Installed, but not checked yet - run the install line once to check it."
    if st["problem"]:
        return "Installed, but Jarvis cannot start it: " + OB.WHY.get(st["problem"], "")
    ver = f"version {st['version']}, " if st["version"] else ""
    when = _date(st["checked_at"]) if st["checked_at"] else ""
    return f"Installed and checked ({ver}last checked {when})." if when else \
        f"Installed and checked ({ver.rstrip(', ')})."


def state_line(*, enabled: bool, waiting: bool, ready_now: bool, not_ready: str) -> str:
    if waiting and not enabled:
        return WORDS["waiting_line"]
    if not enabled:
        return WORDS["off_line"]
    if not ready_now:
        return f"On, but not working yet: {not_ready} Jarvis uses the visible browser until then."
    return "On. Jarvis picks the headless browser for plain reading and the visible one when you might need to take over."


def view() -> dict:
    """GET /api/browser/engine. Numbers, fixed words and this PC's own state."""
    st = settings()
    with _LOCK:
        waiting = bool(_PENDING)
        last = dict(_LAST_CARD) or None
    inst = OB.status()
    ok, why = ready() if st["obscura"] else (False, "")
    out = {
        "obscura": st["obscura"], "waiting": waiting, "last": last, "mode": st["mode"],
        "modes": list(MODES), "installed": inst["installed"], "problem": inst["problem"],
        "ready": bool(st["obscura"] and ok), "not_ready": why if st["obscura"] else "",
        "version": inst["version"], "checked_at": inst["checked_at"],
        "status_line": status_line(inst), "stealth": True,
        "line": state_line(enabled=st["obscura"], waiting=waiting, ready_now=ok, not_ready=why),
        "install_line": download_line(), "download_from": OB.PROJECT_URL,
        "licence": OB.LICENCE, "lane": OB.DRIVER.view(),
    }
    if st["why"]:
        out["why"] = st["why"]
    return out


def panel(payload) -> dict:
    """What a settings screen shows for one GET /api/browser/engine answer: {"available",
    "obscura", "waiting", "checked", "mode", "line", "status", "install_line"}. The
    reference both apps are held to (tools/gen_browser_cases.py). The switch looks
    ON while its card waits, so it can be turned back off, but the line says it is
    only waiting."""
    p = payload if isinstance(payload, dict) else {}

    def text(key: str) -> str:
        v = p.get(key)
        return v.strip() if isinstance(v, str) else ""

    if not isinstance(p.get("obscura"), bool):
        return {"available": False, "obscura": False, "waiting": False, "checked": False,
                "mode": DEFAULT_MODE, "line": WORDS["unread"], "status": "", "install_line": ""}
    on = p["obscura"]
    waiting = p.get("waiting") is True and not on
    mode = p.get("mode") if p.get("mode") in MODES else DEFAULT_MODE
    line = text("line") or (WORDS["waiting_line"] if waiting else
                            WORDS["off_line"] if not on else "")
    return {"available": True, "obscura": on, "waiting": waiting, "checked": on or waiting,
            "mode": mode, "line": line, "status": text("status_line"),
            "install_line": text("install_line")}


def reach_status() -> dict:
    """For "What Jarvis can reach" (jarvis_reach)."""
    st = settings()
    return {"enabled": st["obscura"], "mode": st["mode"], "ready": ready()[0] if st["obscura"]
            else False}


def handle_get() -> tuple:
    return 200, view()


def handle_post(body) -> tuple:
    if not isinstance(body, dict):
        return 400, {"error": 'need {"obscura": true|false} or {"mode": "auto|visible|headless"}'}
    if "mode" in body:
        out = set_mode(body.get("mode"))
        if out.get("ok") is False:
            return 400, out
        if "obscura" not in body:
            out.update(waiting=False, message="Saved.")
            _audit("browser_engine.mode", {"mode": out.get("mode")})
            return 200, out
    return request(body.get("obscura"), set_obscura)


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` and `do_POST` so GET/POST /api/browser/engine are
    answered here, after the server's own origin and token checks. Every other
    request goes straight to the original. Returns the banner line."""
    get0, post0 = handler_cls.do_GET, handler_cls.do_POST
    if getattr(post0, "_jarvis_browser_engine", False):
        return "  browser    Headless browser answers at /api/browser/engine (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        route = urllib.parse.urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != PATH:
            return get0(self)
        if not _allowed(self):
            return None
        try:
            code, out = handle_get()
        except Exception as exc:
            code, out = 503, {"available": False, "error": type(exc).__name__}
        return self._send(code, out)

    def do_POST(self):
        route = urllib.parse.urlsplit(str(getattr(self, "path", "") or "")).path.rstrip("/")
        if route != PATH:
            return post0(self)
        if not _allowed(self):
            return None
        try:
            body = json.loads(read_body(self) or b"{}")
        except Exception as exc:
            return self._send(400, {"error": type(exc).__name__})
        try:
            code, out = handle_post(body)
        except Exception as exc:
            code, out = 503, {"ok": False, "error": type(exc).__name__}
        return self._send(code, out)

    do_GET._jarvis_browser_engine = True
    do_POST._jarvis_browser_engine = True
    handler_cls.do_GET = do_GET
    handler_cls.do_POST = do_POST
    register_stopper()
    on = settings()["obscura"]
    return ("  browser    Headless browser: " + ("on" if on else "off")
            + " (visible browser is always available)")


def _reset_for_tests() -> None:
    with _LOCK:
        _PENDING.clear()
        _WITHDRAWN.clear()
        _LAST_CARD.clear()
        _LATEST.clear()
    OB.DRIVER.stop("reset")


if __name__ == "__main__":
    print(json.dumps(view(), indent=2))
