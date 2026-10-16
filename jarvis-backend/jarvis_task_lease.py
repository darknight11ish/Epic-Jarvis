"""jarvis_task_lease.py - one bounded, revocable lease over a run of steps.

WHAT IT IS FOR

Jarvis can already read a page (`jarvis_browser_control.py`), click a named
control inside another program (`jarvis_ui_control.py`) and drive the phone
(`jarvis_android_control.py`), but every one of those asks for a card per
plan, and the plan is decided afresh on every run. There is a middle shape
this project did not have: "for the next five minutes, on these sites, you
may take these steps - and nothing else". That is a LEASE, and this module is
the whole of it: what a lease is, who may open one, and the one deterministic
check that answers "is this step inside it?".

A LEASE IS NOT AN "APPROVE ALL"

An approval that says "yes, go" and then watches nothing is a standing grant
for future, unnamed actions - the exact thing `docs/ARCHITECTURE.md`'s one
permission model forbids, and the reason `jarvis_ui_control.py`'s docstring
turns UFO's perceive-act loop down. A lease is the opposite of that in every
part that matters, and each part is a check in `check_step()`:

  * it names ONE surface (`browser`, `desktop` or `android`) and is never
    widened to another;
  * a browser lease names the SITES it may touch. The target host must be one
    of them, exactly or as a subdomain. An outside host is a step-up, never a
    quiet navigation;
  * a desktop lease names the WINDOWS it may touch, as `(pid, hwnd)` pairs -
    the same identity `jarvis_front.py` and `jarvis_ui_control.py` work in.
    Jarvis's OWN windows are refused even when a caller puts one in the list,
    because a lease over Jarvis's own controls is a grant to widen itself;
  * it names the ACTIONS it may take, and anything outside that set is
    refused;
  * it expires. The default TTL is 300 seconds and the hard ceiling is 900 - a
    longer request is CLAMPED, not honoured, so no caller can open a lease
    that outlives the sitting;
  * it runs out of steps. `max_steps` defaults to 25, every ALLOWED step
    spends one, and a refusal spends nothing;
  * it can be revoked, and a revoked lease is dead at the next check.

THE FOUR CONSENT BOUNDARIES, IN ORDER

`check_step()` is deliberately dull: no model, no clock of its own beyond
`time.time()`, no network, and the same answer for the same input. A step is
refused the moment any of these trips, and the refusal says which:

  1. the lease exists, is unrevoked, is unexpired, and has steps left;
  2. the step is inside the lease's own scope - its action is one the lease
     names, its host or its window is one the lease names - and its target is
     not Jarvis's own window, page or package;
  3. the target is not a password field, a card or payment field, or a file
     upload/download control - read from the field's own type, from the
     caller's own flags (`password`, `sensitive`, `credit_card`, `file`,
     `download`) and from the control's words, because any one of the three is
     enough to refuse;
  4. the target's own words do not name a high-consequence action
     (`_STEP_UP_VERBS`: submit, pay, buy now, checkout, delete, publish, send
     email, ...). Those get their own card, every time.

Every refusal returns `verdict == "step_up_ask"` - never a bare "no", and
never an allow - so the caller's only way forward is to ask a person. That is
the design in one line: a lease can make the ordinary things quiet, and it can
never make an extraordinary thing quiet.

OPENING A LEASE NEEDS A PERSON

`create()` asks `jarvis_gate.check()` under `LEASE_GATE_NAME`, and reads the
answer the way `jarvis_vault._person_said_yes` reads one: `allowed` is NOT
enough, because the gate returns `allowed=True` on tier `notify` with nobody
asked. The tier must BE `"ask"` and the outcome must be `"approved"`.
Anything else - denied, timed out, notify, auto - opens nothing. If the gate
cannot be imported or cannot be asked, this module fails CLOSED with
`LeaseRefused`: a route that cannot ask a person must not open a lease.

`grant_task_lease` has no line in `[autonomy.tiers]` yet, so the gate resolves
it through its own `unknown_action_tier`, which is `"ask"` as shipped - the
safe direction, and the reason this module is safe to copy to the backend
before that line exists.

WHY IT IS DORMANT, AND WHAT IT DOES NOT DO

Nothing imports this module yet: it is the type, the check and the tests.
It opens no route, serves no page, starts no thread, holds no database and
writes no file. Every lease lives in the module-level dict below and dies
with the process; a lease that did not survive a restart is the safe failure.
It sends nothing, reads nothing, and touches no network. Copying the file to
the backend switches nothing on.

Standard library only, and `jarvis_gate` is imported INSIDE `_default_gate`
rather than at module level, so this module loads on a machine with no gate
at all - and then refuses to open anything.
"""
from __future__ import annotations

import re
import threading
import time
import urllib.parse
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable, Optional

# --------------------------------------------------------------------------
#   The vocabulary
# --------------------------------------------------------------------------

#: The three surfaces a lease can be opened over. One lease is one surface.
SURFACES = ("browser", "desktop", "android")

#: The actions a lease may name. The default set is what an ordinary errand
#: needs: look, click, scroll, type, press a key, go to a site the lease
#: already allows. Anything a caller adds must be named here too - an action
#: name this module has never heard of is refused at `create()` rather than
#: carried on a lease, so a typo cannot widen one.
DEFAULT_ACTIONS = frozenset({
    "snapshot",
    "click_element",
    "scroll",
    "type_text",
    "key_nav",
    "navigate_allowed",
})
KNOWN_ACTIONS = DEFAULT_ACTIONS

BACKGROUND = "background"
FOREGROUND = "foreground"
DELIVERY_MODES = (BACKGROUND, FOREGROUND)

DEFAULT_TTL_SECONDS = 300.0
MAX_TTL_SECONDS = 900.0
MIN_TTL_SECONDS = 1.0
DEFAULT_MAX_STEPS = 25

#: What `check_step()` answers with.
ALLOW = "allow_under_lease"
STEP_UP = "step_up_ask"

#: The name the approval gate is asked under when a lease is opened.
#:
#: Deliberately NOT spelled `..._ACTION`. `backend/test_card_words.py:70`,
#: `backend/test_gate_names.py:402` and
#: `backend/test_gate_denial_rule.py:295` each scan every `backend/jarvis_*.py`
#: for a module-level constant whose NAME contains ACTION, and each then
#: demands that the name resolve against the LIVE gate: a plain phrase in
#: `jarvis_card_words.TITLES`, a line in the live `[autonomy.tiers]`, or a
#: member of one of `jarvis_gate`'s own tables. This name has none of those
#: yet - the tier line belongs in `rebuilt/jarvis-framework.toml`, which this
#: slice does not touch - so calling it `..._ACTION` would fail three suites
#: for a reason that is not about this module. The honest state is written
#: down: the gate answers this name through `unknown_action_tier` ("ask" as
#: shipped), and a later slice gives it a line and a plain card title.
LEASE_GATE_NAME = "grant_task_lease"

# --------------------------------------------------------------------------
#   Jarvis's own surfaces - never a target, whoever asks
# --------------------------------------------------------------------------

#: Substrings that mean "this is Jarvis itself". Every one is somebody else's
#: own constant, quoted so the reason is checkable:
#:   jarvis_front.JARVIS_EXES            ("jarvis-desktop.exe", ...)
#:   jarvis-desktop/src-tauri/tauri.conf.json  "label": "quickbar" / "widget"
#:   jarvis_hud.py                       the HUD page it serves (hud.html)
#:   jarvis_android_control.JARVIS_PACKAGE_PREFIX  ("com.jarvis.")
_OWN_WINDOW_MARKERS = (
    "jarvis-desktop", "jarvis desktop", "jarvis_desktop",
    "quickbar", "quick bar",
    "jarvis_hud", "hud.html",
    "com.jarvis.",
)

#: Every window the desktop shell opens is TITLED "Jarvis ...". Measured in
#: the shell's own source: `src-tauri/src/lib.rs:707` (the HUD),
#: `windows.rs:686` ("Jarvis Desktop - Settings"), `:793` ("Jarvis - Brain"),
#: `:839` ("Jarvis - Faces"), `:886` ("Jarvis - Everything Jarvis can do"),
#: `:926` ("Jarvis - Welcome"), and `tauri.conf.json`'s "Jarvis Desktop
#: Widget". A prefix rather than five more strings, so a window added to the
#: shell later is refused without this list having to learn its name.
#:
#: Deliberately over-broad: a window the owner has titled "Jarvis - Wikipedia"
#: is refused too. A refusal costs one card; the other direction is a lease
#: over Jarvis's own controls.
_OWN_WINDOW_PREFIXES = ("jarvis",)

# --------------------------------------------------------------------------
#   The words a step is judged by
# --------------------------------------------------------------------------

#: A field is a password field if its type says so, if the caller flags it, or
#: if its own label does. "pin" is included and is deliberately blunt: a PIN
#: box is exactly what must never be typed into, and "Pin to Start" being
#: refused as well costs a card and nothing else.
_PASSWORD_RX = re.compile(r"(?i)\b(?:pass(?:word|phrase|code)|passwd|pin)\b")

#: Card, payment and bank fields. Named rather than guessed: a form control
#: that is any of these always gets its own card.
_CARD_RX = re.compile(
    r"(?i)\b(?:card\s*(?:number|no\.?|#)|credit\s*card|debit\s*card|cvv|cvc|csc|"
    r"security\s*code|expir(?:y|es|ation)|iban|routing\s*number|sort\s*code|"
    r"account\s*number)\b")

#: File upload and download triggers - the "choose a file" control, the
#: "Upload" button, the "Download" link. `jarvis_browser_control.py` cancels
#: every download and refuses every upload; a lease must not be the way round
#: that.
_FILE_RX = re.compile(
    r"(?i)\b(?:upload|download|attach(?:ment)?|choose\s+files?|browse\s+files?|"
    r"select\s+files?|save\s+(?:as|file|to)|export)\b")

#: The high-consequence verbs, in the shape the work order gives them. A
#: control whose own words are one of these is NEVER clicked under a lease: it
#: is a `step_up_ask`, every time, so the person sees the button's own words on
#: a card before anything happens.
_STEP_UP_VERBS = re.compile(
    r"(?i)\b(submit|pay|purchase|buy\s+now|checkout|place\s+order|send\s+money|"
    r"transfer|delete|erase|remove|uninstall|publish|post|send\s+email|merge|"
    r"confirm\s+payment|authorize|grant\s+access|allow)\b"
)

#: Where a control's own words are read from. `_SENSITIVE_LABEL_KEYS` is the
#: label half (what the control IS); `_STEP_UP_TEXT_KEYS` adds the address the
#: step goes to and the text it would type, because a checkout URL and the
#: words about to be typed are both high-consequence intent.
_SENSITIVE_LABEL_KEYS = ("label", "name", "text", "title", "placeholder", "aria_label")
_STEP_UP_TEXT_KEYS = _SENSITIVE_LABEL_KEYS + ("value", "url")

#: Where the TARGET's identity is read from, for the "is this Jarvis?" check.
#: Prose keys (`why`, `note`, `goal`, ...) are deliberately not here: a caller
#: writing "why: click the Jarvis settings button" is describing a step, not
#: aiming at Jarvis.
_TARGET_TEXT_KEYS = ("url", "address", "window", "window_title", "title", "exe",
                     "process", "package", "app", "name", "label", "text",
                     "placeholder", "aria_label", "path")


class LeaseRefused(RuntimeError):
    """No lease was opened. Raised for every way opening one can fail, so a
    caller has one thing to catch and cannot mistake a refusal for a lease."""


# --------------------------------------------------------------------------
#   The lease
# --------------------------------------------------------------------------

@dataclass
class TaskLease:
    """One bounded run of steps, opened by a person and never widened.

    Every field is a ceiling. Nothing here is re-read from a model, a file or
    the network: `check_step()` reads these and nothing else, which is what
    makes the answer deterministic.
    """
    lease_id: str
    goal: str
    created_at: float
    expires_at: float
    surface: str
    allowed_domains: frozenset = frozenset()
    allowed_windows: frozenset = frozenset()
    allowed_actions: frozenset = DEFAULT_ACTIONS
    delivery_mode: str = BACKGROUND
    max_steps: int = DEFAULT_MAX_STEPS
    steps_used: int = 0
    revoked: bool = False

    # ---- the state `check_step()` reads --------------------------------
    def expired(self, now: Optional[float] = None) -> bool:
        return (time.time() if now is None else now) >= self.expires_at

    def remaining_steps(self) -> int:
        return max(self.max_steps - self.steps_used, 0)

    def as_dict(self) -> dict:
        """A copy for a route or a log. Frozensets become sorted lists, so the
        answer is JSON-serialisable and its order does not depend on hashing."""
        d = asdict(self)
        d["allowed_domains"] = sorted(self.allowed_domains)
        d["allowed_windows"] = [list(w) for w in sorted(self.allowed_windows)]
        d["allowed_actions"] = sorted(self.allowed_actions)
        d["remaining_steps"] = self.remaining_steps()
        return d


#: Every open lease: lease_id -> TaskLease. In memory on purpose - see the
#: module docstring. The lock is not decoration: `check_step()` reads the
#: counter and increments it, and a lease whose step budget can be raced is
#: not a ceiling. Nothing blocks while holding it.
_LEASES: dict = {}
_LOCK = threading.RLock()


def _reset_for_tests() -> None:
    """Drop every lease. A test hook, not a route: a suite can start from no
    leases at all without reaching into `_LEASES` by hand."""
    with _LOCK:
        _LEASES.clear()


# --------------------------------------------------------------------------
#   Reading a step (pure: no state, no I/O, testable on plain dicts)
# --------------------------------------------------------------------------

def _norm(text: Any) -> str:
    """The comparison shape used everywhere here: surrounding whitespace
    trimmed, inner runs collapsed - the same normalisation
    `jarvis_browser_control._norm` uses for accessible names."""
    return " ".join(str("" if text is None else text).split())


def _truthy(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    return False


def _element_of(step: dict) -> dict:
    """The control a step acts on. A step may describe it in its own
    `element` dict, or be its own element description (a label beside a url).
    Both are merged, with `element` winning - the fail-closed direction, since
    merging can only give the checks MORE words to look at."""
    el = step.get("element")
    if not isinstance(el, dict):
        return dict(step)
    merged = dict(step)
    merged.update(el)
    return merged


def _label_text(el: dict) -> str:
    return " ".join(_norm(el.get(k)) for k in _SENSITIVE_LABEL_KEYS
                    if isinstance(el.get(k), str))


def _stepup_text(el: dict) -> str:
    return " ".join(_norm(el.get(k)) for k in _STEP_UP_TEXT_KEYS
                    if isinstance(el.get(k), str))


def _target_texts(step: dict, el: dict) -> list:
    """Every word that describes the TARGET, for the "is this Jarvis?" check.
    Read from both the step and its element, so a window title beside the
    element is seen as well as one inside it."""
    out = []
    for source in (step, el):
        for key in _TARGET_TEXT_KEYS:
            value = source.get(key)
            if isinstance(value, (str, int)):
                text = _norm(value)
                if text and text not in out:
                    out.append(text)
    return out


def own_window_reason(*texts: Any) -> str:
    """The marker that says a piece of text is Jarvis itself, or "".

    Public because the check is worth reusing and worth testing on its own -
    a caller about to aim a step at a window should be able to ask first.
    """
    for text in texts:
        low = _norm(text).lower()
        if not low:
            continue
        for marker in _OWN_WINDOW_MARKERS:
            if marker in low:
                return marker
        for prefix in _OWN_WINDOW_PREFIXES:
            if low.startswith(prefix):
                return prefix
    return ""


def host_allowed(host: str, allowed_domains: Iterable[str]) -> bool:
    """Whether a host is inside a lease's sites: the exact host, or a
    subdomain of one. http/https is checked by the caller, not here.

    `jarvis_browser_control._host_matches` returns True for an EMPTY list
    ("no sites named means anywhere"), which is right for a plan the owner is
    reading on a card and wrong for a lease nobody is watching. Here an empty
    list matches nothing.
    """
    host = _norm(host).lower().rstrip(".")
    if not host:
        return False
    for d in allowed_domains or ():
        d = _norm(d).lower().lstrip(".").rstrip(".")
        if d and (host == d or host.endswith("." + d)):
            return True
    return False


def _sensitive_reason(el: dict) -> str:
    """Check 3: a password field, a card or payment field, or a file
    upload/download control. Read from the type, the caller's own flags, and
    the control's words - any one of the three is enough.

    `sensitive` is read as well as the three named flags, because a caller
    that already knows which fields are sensitive should not have to say it
    twice: `jarvis_browser_control._lease_payload` sends
    `element["sensitive"] = True` for exactly `input_type in ("password",
    "hidden", "file")` (its own snapshot record, jarvis_browser_control.py:910)
    and passes `input_type` through only for the password half. Without this
    line a file input whose label happens to be "Photo" would be allowed under
    a lease while its own reader had already called it sensitive. A caller's
    flag can only ADD a refusal here, never remove one."""
    input_type = _norm(el.get("input_type") or el.get("type")
                       or el.get("html_type")).lower()
    label = _label_text(el)
    if input_type == "password" or _truthy(el.get("password")) or _PASSWORD_RX.search(label):
        return "the target is a password field, which a lease never types into"
    if _truthy(el.get("sensitive")):
        return ("the target is a field its own reader flagged as sensitive (a "
                "password, hidden or file control), which always gets its own card")
    if _truthy(el.get("credit_card")) or _CARD_RX.search(label):
        return "the target is a card or payment field, which always gets its own card"
    if (input_type == "file" or _truthy(el.get("file")) or _truthy(el.get("file_upload"))
            or _truthy(el.get("upload")) or _truthy(el.get("download"))
            or _FILE_RX.search(label)):
        return "the target is a file upload or download control, which a lease never touches"
    return ""


def _stepup_reason(el: dict) -> str:
    """Check 4: the target's own words name a high-consequence action."""
    m = _STEP_UP_VERBS.search(_stepup_text(el))
    if not m:
        return ""
    return (f"the step's own words name a high-consequence action "
            f"({m.group(0).strip()!r}), which needs its own card")


def _window_of(step: dict) -> tuple:
    """The (pid, hwnd) a desktop step names, or (None, None). Accepts the
    three shapes a caller might use: `pid`/`hwnd` keys, a `window` pair, or a
    `window` dict."""
    pid, hwnd = step.get("pid"), step.get("hwnd")
    window = step.get("window")
    if isinstance(window, dict):
        pid = window.get("pid", pid)
        hwnd = window.get("hwnd", hwnd)
    elif isinstance(window, (list, tuple)) and len(window) == 2:
        pid, hwnd = window
    try:
        return int(pid), int(hwnd)
    except (TypeError, ValueError):
        return None, None


def _target_reason(lease: TaskLease, step: dict, el: dict) -> str:
    """Check 2: the step is inside this lease's scope, and its target is not
    Jarvis. The Jarvis check comes first, so a step aimed at Jarvis's own HUD
    is refused as that rather than as an unlisted host."""
    hit = own_window_reason(*_target_texts(step, el))
    if hit:
        return (f"this target is Jarvis's own (matched {hit!r}), and a lease "
                f"never covers Jarvis itself")

    if lease.surface == "browser":
        url = _norm(step.get("url") or el.get("url"))
        if not url:
            return "a browser step must carry the address it acts on"
        parsed = urllib.parse.urlparse(url)
        scheme = (parsed.scheme or "").lower()
        if scheme not in ("http", "https"):
            return (f"only http and https addresses are allowed "
                    f"({scheme or 'no scheme'} was given)")
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host:
            return "that address has no host"
        if not host_allowed(host, lease.allowed_domains):
            return f"{host} is not one of this lease's allowed sites"
        return ""

    if lease.surface == "desktop":
        pid, hwnd = _window_of(step)
        if pid is None or hwnd is None:
            return "a desktop step must name the window it acts on, as (pid, hwnd)"
        if (pid, hwnd) not in lease.allowed_windows:
            return f"the window ({pid}, {hwnd}) is not one this lease allows"
        return ""

    return (f"nothing in this lease binds an {lease.surface} step to a target, "
            f"so every {lease.surface} step is refused until something does")


def _ask(reason: str) -> dict:
    return {"verdict": STEP_UP, "reason": reason}


# --------------------------------------------------------------------------
#   The circuit-breaker
# --------------------------------------------------------------------------

def check_step(lease_id: str, step: Any) -> dict:
    """Is this one step inside that lease? A dict, and nothing else.

    Returns `{"verdict": "allow_under_lease", "remaining_steps": N}` when the
    step is inside the lease, or `{"verdict": "step_up_ask", "reason": ...}`
    for every other answer. There is no third verdict and no exception: a
    caller cannot mistake a refusal for a permission, and cannot miss one.

    An ALLOW spends a step (`steps_used` goes up), because a step budget
    nobody counts is not a ceiling. A refusal spends nothing - nothing
    happened, so nothing is used up.
    """
    lease = _LEASES.get(_norm(lease_id))
    if lease is None:
        return _ask("no lease is open under that id")
    if lease.revoked:
        return _ask("this lease was revoked")
    if lease.expired():
        return _ask("this lease has expired")
    if lease.steps_used >= lease.max_steps:
        return _ask(f"this lease's {lease.max_steps} steps are used up")

    step = step if isinstance(step, dict) else {}
    el = _element_of(step)

    action = _norm(step.get("action")).lower()
    if action not in lease.allowed_actions:
        return _ask(f"this lease does not name the action {action or '(none)'!r}")

    reason = _target_reason(lease, step, el)
    if reason:
        return _ask(reason)
    reason = _sensitive_reason(el)
    if reason:
        return _ask(reason)
    reason = _stepup_reason(el)
    if reason:
        return _ask(reason)

    with _LOCK:
        # Re-checked under the lock: two threads can both be past the check
        # above and only one of them may spend the last step.
        if lease.revoked or lease.expired() or lease.steps_used >= lease.max_steps:
            return _ask("this lease ran out between the check and the step")
        lease.steps_used += 1
        remaining = lease.remaining_steps()
    return {"verdict": ALLOW, "remaining_steps": remaining}


def revoke(lease_id: str) -> bool:
    """Kill one lease. True when a lease was there to kill, False when it was
    unknown or already revoked - so a caller can say which happened, and
    revoking twice is never an error."""
    lease = _LEASES.get(_norm(lease_id))
    if lease is None or lease.revoked:
        return False
    with _LOCK:
        if lease.revoked:
            return False
        lease.revoked = True
    return True


def get(lease_id: str) -> Optional[TaskLease]:
    """The lease itself, for a route that must show what is open. Read-only by
    convention: nothing outside this module writes to it."""
    return _LEASES.get(_norm(lease_id))


# --------------------------------------------------------------------------
#   Opening a lease - the one moment a person is asked
# --------------------------------------------------------------------------

def _default_gate(action: str, detail: dict, prompt: str):
    """`jarvis_gate.check()`, imported HERE rather than at module level.

    `jarvis_gate.py` is the owner's own module - it is patched, never shipped
    - so it may not be on the machine this file is loaded on. The import is
    left to raise: `create()` turns any failure into `LeaseRefused`, which is
    the fail-closed direction. Nothing opens without a person's yes, and a
    machine that cannot ask gets no lease.
    """
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _person_said_yes(verdict: Any) -> bool:
    """A person's yes, and nothing weaker.

    `allowed` alone is not that: `jarvis_gate.check()` returns `allowed=True`
    on tier `notify` with nobody asked. The tier must BE `"ask"` and the
    outcome must be `"approved"` - the same test `jarvis_vault.py`'s
    `_person_said_yes` and `jarvis_sky.py`'s before it make. This is
    deliberately STRICTER than the tier table: a config that listed
    `grant_task_lease` as `notify` or `auto` opens no lease here, which is the
    only direction a safety check is allowed to differ in.
    """
    if getattr(verdict, "allowed", False) is not True:
        return False
    if getattr(verdict, "tier", None) != "ask":
        return False
    return getattr(verdict, "outcome", None) == "approved"


def _refusal_note(verdict: Any) -> str:
    outcome = getattr(verdict, "outcome", None) or "refused"
    reason = _norm(getattr(verdict, "reason", "") or "")
    tier = getattr(verdict, "tier", None) or "?"
    return f"the approval gate answered {outcome!r} at tier {tier!r}" + (
        f" ({reason})" if reason else "")


def _clean_domains(allowed_domains: Iterable[str]) -> frozenset:
    out = set()
    for raw in allowed_domains or ():
        d = _norm(raw).lower().lstrip(".").rstrip(".")
        if not d:
            continue
        if any(ch in d for ch in ("/", ":", "@", "\\")):
            raise ValueError(
                f"a lease names a HOST, not an address: {raw!r} carries a "
                f"scheme, a port or a path. Name the host on its own, so what "
                f"the lease allows is what the lease says")
        out.add(d)
    return frozenset(out)


def _clean_windows(allowed_windows: Iterable) -> frozenset:
    out = set()
    for raw in allowed_windows or ():
        if isinstance(raw, dict):
            pid, hwnd = raw.get("pid"), raw.get("hwnd")
        elif isinstance(raw, (list, tuple)) and len(raw) == 2:
            pid, hwnd = raw
        else:
            raise ValueError(
                f"a window is named as a (pid, hwnd) pair; {raw!r} is not one")
        try:
            out.add((int(pid), int(hwnd)))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"a window is named as a (pid, hwnd) pair of whole numbers; "
                f"{raw!r} is not one") from exc
    return frozenset(out)


def create(goal: str,
           surface: str,
           ttl_seconds: float = DEFAULT_TTL_SECONDS,
           allowed_domains: Iterable[str] = (),
           allowed_windows: Iterable = (),
           allowed_actions: Iterable[str] = DEFAULT_ACTIONS,
           delivery_mode: str = BACKGROUND,
           foreground_opt_in: bool = False,
           max_steps: int = DEFAULT_MAX_STEPS,
           gate: Optional[Callable[[str, dict, str], Any]] = None) -> TaskLease:
    """Ask a person, and only then open one lease.

    `gate` is the injection point `jarvis_ui_control.py` and
    `jarvis_browser_control.py` use for their real `read`/`act`: the default
    is the real `jarvis_gate.check()`, and a suite passes a stand-in so no
    card is raised and nothing waits. The real call BLOCKS until a person
    answers or the gate gives up, exactly as every other route that waits for
    a person does.

    `delivery_mode="foreground"` needs `foreground_opt_in=True`. Without it
    the request is refused rather than quietly downgraded to background: a
    caller who asked for a visible run and got an invisible one would believe
    the owner had watched it happen.
    """
    goal = _norm(goal)
    if not goal:
        raise ValueError("a lease needs a goal, in the owner's own words - it is "
                         "what the card says the lease is for")

    surface = _norm(surface).lower()
    if surface not in SURFACES:
        raise ValueError(f"a lease is over one of {SURFACES}; {surface!r} is not one")

    try:
        ttl = float(ttl_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"a lease's TTL is a number of seconds, not {ttl_seconds!r}") from exc
    # CLAMPED, not honoured: a longer request is shortened and cannot be
    # otherwise, so no caller can hold a lease past the ceiling.
    ttl = min(max(ttl, MIN_TTL_SECONDS), MAX_TTL_SECONDS)

    try:
        max_steps = int(max_steps)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"a lease's step budget is a whole number, not {max_steps!r}") from exc
    if max_steps < 1:
        raise ValueError("a lease needs at least one step; 0 steps is not a lease")

    actions = frozenset(_norm(a).lower() for a in (allowed_actions or ()) if _norm(a))
    if not actions:
        raise ValueError("a lease that names no actions allows nothing - name the "
                         "actions it may take, or leave the default alone")
    unknown = sorted(a for a in actions if a not in KNOWN_ACTIONS)
    if unknown:
        raise ValueError(
            f"these are not actions this module knows: {unknown}. A lease may "
            f"only name {sorted(KNOWN_ACTIONS)}, so a typo cannot widen one")

    delivery_mode = _norm(delivery_mode).lower()
    if delivery_mode not in DELIVERY_MODES:
        raise ValueError(f"delivery is one of {DELIVERY_MODES}; {delivery_mode!r} is not one")
    if delivery_mode == FOREGROUND and not foreground_opt_in:
        raise ValueError(
            "foreground delivery puts the run in front of the owner, so it "
            "needs foreground_opt_in=True - the explicit opt-in, not a default")

    domains = _clean_domains(allowed_domains)
    windows = _clean_windows(allowed_windows)

    # ---- the person is asked BEFORE anything is recorded ----
    detail = {
        "what": ("open a task lease: a bounded set of steps Jarvis may take "
                 "without a card for each one"),
        "goal": goal[:300],
        "surface": surface,
        "sites": sorted(domains)[:12],
        "windows": [list(w) for w in sorted(windows)][:12],
        "actions": sorted(actions),
        "steps": max_steps,
        "delivery": delivery_mode,
        "for_seconds": ttl,
    }
    if surface == "browser":
        where = f"{len(domains)} site(s)"
    elif surface == "desktop":
        where = f"{len(windows)} window(s)"
    else:
        where = "no target bound yet, so every step will ask"
    prompt = (f"a {surface} lease for up to {int(ttl)} seconds and {max_steps} "
              f"step(s) ({where}), to: {goal[:200]}")

    ask = gate if gate is not None else _default_gate
    try:
        verdict = ask(LEASE_GATE_NAME, detail, prompt)
    except Exception as exc:
        # Fail CLOSED. Every failure here - no jarvis_gate, no approval queue,
        # a broken stand-in - has the same safe answer, and it is "no lease".
        raise LeaseRefused(
            f"no lease was opened: the approval gate could not be asked "
            f"({exc})") from exc
    if not _person_said_yes(verdict):
        raise LeaseRefused(f"no lease was opened: {_refusal_note(verdict)}")

    now = time.time()
    lease = TaskLease(
        lease_id=uuid.uuid4().hex[:12],
        goal=goal[:300],
        created_at=now,
        expires_at=now + ttl,
        surface=surface,
        allowed_domains=domains,
        allowed_windows=windows,
        allowed_actions=actions,
        delivery_mode=delivery_mode,
        max_steps=max_steps,
    )
    with _LOCK:
        _LEASES[lease.lease_id] = lease
    return lease
