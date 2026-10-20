"""jarvis_app_control.py - the backend half of "fuller automation inside other apps".

WHAT THIS IS, in one paragraph. The owner asked (2026-10-19) for fuller
automation inside other apps, then specified "enable accessibility service with
control by jarvis **as an option** in the android app". The architecture that
follows from this project's own rules is: **the PC is the brain and the gate;
the phone is the hands.** The phone may never decide or approve anything. An
Android AccessibilityService reads the screen and performs one atomic action;
this module (on the PC) validates the owner's allow-list and the one-step plan,
raises exactly ONE approval card through jarvis_gate.check(), and then hands
that ONE approved step back to the phone when it asks - never a step nobody
approved, never a second step, and it stops the run when the screen has changed.
The Android service and the screens are a later, separate slice; this file is
the half the PC owns, and it **ships OFF** (the `[app_control] enabled` flag in
jarvis-framework.toml defaults to false, and a missing section reads as false).

WHY A BACKEND MODULE AT ALL, when the phone does the acting. Because every
safety rule this project has lives behind the PC's gate: ONE card, tier "ask"
checked before and on the verdict, an audit line, the taint/rush latches, the
protected-file rule, and no auto-approval. A phone that could act without
asking the PC would be a second, weaker permission model - exactly what
docs/ARCHITECTURE.md section 3 forbids. The phone is not trusted to choose the
action either: the plan arrives here first, is checked here, is shown on a card
here, and the step the phone is given afterwards is the one card's own step,
built from the stored plan (never from the phone's next request).

THE OWNER'S TWO DECISIONS, 2026-10-19, both load-bearing:
  * the accessibility option ships with an EMPTY allow-list - nothing can be
    read for context or acted on until the owner adds apps to it, and an empty
    list refuses every request in plain words;
  * there is NO separate read-only phase - the service may read the UI tree and
    act in the same carded step, but every step is ONE approval card naming the
    app, what will be done and the exact target, and a changed screen stops the
    run. Banner + one-tap Stop are mandatory from the first slice (the phone
    shows them; the PC's /api/task/stop is the existing path both clients use).

WHAT IT REFUSES OUTRIGHT, before any card exists (so there is nothing to
approve): any app not on the owner's allow-list (and an empty list refuses
everything); password/credential fields and anything said to look like 2FA;
money, banking and payment apps; steps that send, post or share anything;
steps that delete or move anything; anything that names one of
jarvis_gate._PROTECTED's files; any action other than tap/swipe/type/back/home;
a run while jarvis_gate.taint_active() is true (outside text may be steering
the conversation - acting then is exactly what the latch exists to stop); a
second run while one is waiting; and everything at all while the feature flag
is off. Every one of those is a plain sentence, never a traceback.

WHAT IT NEVER DOES. It never runs a step itself (there is no desktop input
here); it never stores audio, screen text or typed text in the audit log (the
audit line is app + verb only - the card is the only place the exact step is
written down, and that row is local); it never writes a screen snapshot to
disk; it never approves anything; it never clears a taint or rush latch; it
never acts while taint is latched; it never lets the phone choose or widen the
plan. The wire in either direction carries the plan and the snapshots over the
owner's own private link (Tailscale/Meshnet) under the existing token - never a
cloud service, never a public tunnel.

CREDIT, AND WHAT WAS NOT COPIED. The phone-side patterns this contract is
shaped for are re-implemented from MIT-licensed prior art, with credit in
THIRD-PARTY-NOTICES.txt: GiggleWang/MobileAgent-Android (MIT) - the in-app
AccessibilityService action set (tap/swipe/type/system button) and its
plan -> act -> check loop; droidrun/mobilerun (MIT) - the accessibility
"portal" UI-tree contract; microsoft/UFO (MIT) - the UIA plan/verify/stop-on-
change discipline this project's own jarvis_ui_control.py already follows. No
code was copied; the GPL project (mimic) was read-only reference and is not
used.

TESTING WITHOUT A PHONE. Pure logic only in this file: the allow-list parser,
the plan validator, the card text, the step matcher, the audit detail and the
run state machine are plain functions a suite can drive with dicts. The two
things that touch the outside are injectable: `gate` (jarvis_gate.check) and
`spawn` (the thread that waits for the card); there is no network, no file and
no Android import here at all.

    POST /api/app-control/run    {"allowed": [...], "app": ..., "step": {...},
                                  "snapshot": {...}} -> 202 {"run": <id>, ...}
    POST /api/app-control/step   {"run": <id>, "snapshot": {...}} -> one step,
                                  or done/stopped/pending in plain words

The two routes are added by backend/app-control.patch (there is no new patch
route shape here); docs/JARVIS-API.md section 146 has the full contract. The
feature is OFF by default and this slice adds no way to switch it on.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from typing import Callable, Optional

#: The gate action. The same one enrolling a voice print uses, because this
#: changes what Jarvis may DO on the owner's own device - a change to who
#: Jarvis obeys, which is what "change_own_config" means in the tier table.
ACTION = "change_own_config"

#: The only actions the phone may be told to perform. `screenshot` is
#: deliberately absent: S1 acts on the UI tree, and a screenshot is a reading
#: this backend half does not need.
ACTIONS = ("tap", "swipe", "type", "back", "home")

#: A typed value is one field's worth of text, never a document.
MAX_TEXT = 200
#: How many apps the owner may allow at most (a sanity bound, not a policy).
MAX_ALLOWED = 64
#: How long a run stays usable before it expires - the same shape as the
#: gate's own approval timeout, but shorter: a stale plan on a phone screen
#: must not be executable an hour later.
RUN_SECONDS = 900.0

#: One Android package name: at least one dot, no spaces or slashes.
PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")

#: Refusal sentences. Fixed here so every refusal is one plain sentence and
#: the tests can hold each one; never a traceback, never a JSON dump.
OFF = ("App control is switched off on this PC. It is off by default, and this "
       "build has no switch yet - nothing was changed.")
EMPTY = ("No apps are allowed yet. Add the apps Jarvis may use in the Jarvis "
         "app's Settings first; an empty list means nothing is allowed.")
NOT_ALLOWED = ("{app} is not on the list of apps Jarvis may use on this phone. "
               "Add it in the Jarvis app's Settings first.")
BAD_ACTION = ('Only tap, swipe, type, back and home are allowed - "{action}" is not.')
PASSWORD_FIELD = ("That is a password or credential field, so Jarvis will not "
                  "read it or type in it.")
TWO_FACTOR = ("That looks like a two-step verification field or code, so Jarvis "
              "will not touch it.")
MONEY_APP = ("That looks like a bank, payment or money app, so Jarvis will not "
             "use it.")
SEND_STEP = ("That step would send, post or share something, so Jarvis will not "
             "do it from here.")
DELETE_STEP = ("That step would delete or move something, so Jarvis will not do "
               "it from here.")
PROTECTED_FILE = ("That names a file only you may change by hand, so Jarvis will "
                  "not do it.")
NOT_FOUND = ("That control is not on the screen now, so Jarvis stopped rather "
             "than guess.")
SCREEN_CHANGED = ("The screen changed after the card was approved, so Jarvis "
                  "stopped rather than guess.")
PENDING_MSG = ("The approval card has not been answered yet. Nothing has run.")
SECOND_RUN = ("A Jarvis action is already waiting for approval. Approve or deny "
              "that card first.")
FINISHED = "That run is finished; there is nothing left to do."
UNKNOWN_RUN = "That app-control run is not here on this PC any more."
TAINTED = ("Jarvis read something from outside that may be trying to take over, "
           "so it will not act now. Say it again in a fresh conversation.")
BAD_BODY = "Send a JSON object with an app, one step and the screen snapshot."
BAD_ALLOWED = "The allowed list must be a list of app package names."

#: Words that make a step/target one this module refuses outright. Matched
#: case-insensitively against the app label, the target's own text/id and the
#: step's `why` - never against the owner's typed text (that is what the card
#: shows the owner, and refusing prose would refuse ordinary requests).
_MONEY = ("bank", "banking", "payment", "paypal", "venmo", "cash app",
          "checkout", "wallet", "broker", "brokerage", "invest", "stripe",
          "money transfer", "card number", "credit card", "debit card")
_SEND = ("send", "post", "share", "publish", "submit", "reply", "message",
         "email", "sms", "dm ", "tweet")
_DELETE = ("delete", "remove", "erase", "uninstall", "wipe", "format ",
           "move to", "rename", "trash", "destroy")
_TWO_FACTOR = ("2fa", "two-factor", "two factor", "two-step", "two step",
               "verification code", "one-time code", "one time code", "otp",
               "authenticator")
_SECRET = ("password", "passcode", "pass code", " pin", "pin ", "credential",
           "secret", "private key", "api key", "access token", "cvv",
           "security code", "social security", "ssn")


def _fw():
    import jarvis_framework
    return jarvis_framework


def _audit(event: str, detail: dict) -> None:
    try:
        _fw().audit_log(event, detail)
    except Exception:
        pass


def _tier_of(action: str) -> str:
    return str(_fw().action_tier(action))


def _gate(action: str, detail: dict, prompt: str):
    import jarvis_gate
    return jarvis_gate.check(action, detail, prompt=prompt)


def _tainted() -> bool:
    try:
        import jarvis_gate
        return bool(jarvis_gate.taint_active())
    except Exception:
        # A missing gate is not permission to act: fail closed.
        return True


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="jarvis-app-control", daemon=True).start()


#: Tests set this to the gate's own list (the repository-only run has no
#: jarvis_gate.py); None means "ask the real gate". The suite puts it back.
PROTECTED_NAMES = None


def _protected() -> tuple:
    """The gate's protected file names, read from the gate it protects.

    Imported lazily and copied to a tuple, so this module cannot hold a second,
    stale list. A missing gate returns ("",) and the scan finds nothing - but
    `_gate` then refuses everything anyway; failing open here would be a hole.
    PROTECTED_NAMES lets the suite prove the refusal without the owner's gate.
    """
    if PROTECTED_NAMES is not None:
        return tuple(PROTECTED_NAMES)
    try:
        import jarvis_gate
        return tuple(getattr(jarvis_gate, "_PROTECTED", ()))
    except Exception:
        return ()


def _now() -> float:
    return time.time()


def enabled(framework: Optional[dict] = None) -> bool:
    """Is the app-control feature switched on in the owner's settings file?

    OFF unless the file says `enabled = true` under `[app_control]`. A missing
    section, an unreadable file or a broken value all read as OFF - this is the
    one answer that can never do harm, and this slice adds no way to switch it
    on (the owner's option is the NEXT slice; until then it is off, deliberately).
    """
    try:
        cfg = framework if isinstance(framework, dict) else _fw().load_framework()
        section = (cfg or {}).get("app_control") or {}
        return section.get("enabled") is True
    except Exception:
        return False


# --------------------------------------------------------------------------
#   The owner's allow-list - empty means nothing, always
# --------------------------------------------------------------------------

def parse_allowed(value) -> tuple:
    """(list, error) for the `allowed` list in a run request.

    The list is the OWNER'S list, carried here from the phone's Settings (it
    lives on the phone, where the owner edits it; the PC does not invent one
    and cannot add to it). This function only validates shape and order - it
    never widens the list, never adds a default, and returns [] for "no apps",
    which the caller refuses with EMPTY. `error` is a plain sentence or "".
    """
    if value is None:
        return [], ""
    if not isinstance(value, (list, tuple)):
        return [], BAD_ALLOWED
    out = []
    for item in value:
        pkg = str(item or "").strip()
        if not pkg or not PACKAGE_RE.match(pkg):
            return [], BAD_ALLOWED
        if pkg not in out:
            out.append(pkg)
    if len(out) > MAX_ALLOWED:
        return [], f"At most {MAX_ALLOWED} apps may be allowed."
    return out, ""


def _clean(value, limit: int) -> str:
    """One field of text: no control characters, capped, never a traceback."""
    text = "".join(ch for ch in str(value or "") if ch == "\n" or ch == "\t"
                   or 32 <= ord(ch) < 127 or ord(ch) > 159)
    text = " ".join(text.split())
    return text[:limit]


def _find_word(text: str, words) -> str:
    """The first refused word found in `text`'s lowercase form, or ""."""
    low = (text or "").lower()
    for word in words:
        if word in low:
            return word
    return ""


def _scan_words(*texts):
    """(refusal sentence, which) for refused words across these fields."""
    blob = " ".join(str(t or "") for t in texts)
    for words, sentence in ((_MONEY, MONEY_APP), (_TWO_FACTOR, TWO_FACTOR),
                            (_SECRET, PASSWORD_FIELD), (_DELETE, DELETE_STEP),
                            (_SEND, SEND_STEP)):
        hit = _find_word(blob, words)
        if hit:
            return sentence, hit
    return "", ""


def _names_protected(*texts) -> str:
    """The protected file name found in these fields, or "".

    Kept here as well as in the gate on purpose: the gate's rule reads the
    action's TARGET, and this module refuses BEFORE any card exists, so nothing
    can even be asked about a plan that names the policy or the gate.
    """
    blob = " ".join(str(t or "") for t in texts).lower()
    for name in _protected():
        if name and name.lower() in blob:
            return name
    return ""


# --------------------------------------------------------------------------
#   The plan - one app, ONE atomic step, and the exact card
# --------------------------------------------------------------------------

def _target_of(step: dict) -> dict:
    """The node descriptor a tap/type/swipe targets, normalised; {} if none."""
    target = step.get("target")
    if not isinstance(target, dict):
        return {}
    bounds = []
    if isinstance(target.get("bounds"), (list, tuple)):
        for value in list(target.get("bounds"))[:4]:
            try:
                bounds.append(int(value))
            except (TypeError, ValueError):
                bounds = []
                break
    return {
        "id": _clean(target.get("id"), 200),
        "text": _clean(target.get("text"), 200),
        "class": _clean(target.get("class"), 120),
        "bounds": bounds,
        "password": target.get("password") is True,
        "enabled": target.get("enabled") is not False,
    }


def _snapshot_controls(snapshot: dict) -> list:
    controls = snapshot.get("controls") if isinstance(snapshot, dict) else None
    if not isinstance(controls, list):
        return []
    return [c for c in controls if isinstance(c, dict)]


def _same_target(planned: dict, live: dict) -> bool:
    """Still the same control: same id (when it had one) and same own text."""
    if not planned or not live:
        return False
    if planned.get("password") or live.get("password"):
        return False
    if planned.get("id"):
        return (str(live.get("id") or "") == planned["id"]
                and str(live.get("text") or "") == planned.get("text", ""))
    return str(live.get("text") or "") == planned.get("text", "")


def _same_identity(planned: dict, live: dict) -> bool:
    """Same control by its OWN identity, ignoring password/enabled flags.

    Used when the phone asks for the approved step: a control that is still the
    same one but has BECOME a password field or gone disabled must be told apart
    from a control that vanished - the refusal sentence is different, and a
    password field is the more serious of the two.
    """
    if not planned or not live:
        return False
    if planned.get("id"):
        return (str(live.get("id") or "") == planned["id"]
                and str(live.get("text") or "") == planned.get("text", ""))
    return (str(live.get("text") or "") == planned.get("text", "")
            and str(live.get("class") or "") == planned.get("class", ""))


def _control_present(snapshot: dict, planned: dict) -> bool:
    for candidate in _snapshot_controls(snapshot):
        if _same_target(planned, _target_of({"target": candidate})):
            return candidate.get("enabled") is not False
    return False


def validate_plan(doc: dict, allowed: list) -> tuple:
    """(plan, code, error) - the whole pre-card validation, pure and ordered.

    `allowed` is the OWNER'S allow-list (parse_allowed's output). Everything
    before the card is decided here: the app must be on that list (an empty
    list allows nothing), the step must be one of the five actions, the screen
    snapshot must contain the target, and the refused categories above are
    checked. Returns a plain plan dict ready to store and print, or
    (None, 400/409, <plain sentence>).
    """
    if not isinstance(doc, dict):
        return None, 400, BAD_BODY
    app = _clean(doc.get("app"), 200)
    if not app or not PACKAGE_RE.match(app):
        return None, 400, "Send the app's own package name, like com.android.settings."
    if not allowed:
        return None, 409, EMPTY
    if app not in allowed:
        return None, 409, NOT_ALLOWED.format(app=app)
    label = _clean(doc.get("app_name"), 80) or app
    step = doc.get("step")
    if not isinstance(step, dict):
        return None, 400, "Send exactly one step: {action, target, text, why}."
    action = _clean(step.get("action"), 20).lower()
    if action not in ACTIONS:
        return None, 400, BAD_ACTION.format(action=action or "(empty)")
    why = _clean(step.get("why"), MAX_TEXT)
    target = _target_of(step)
    if target.get("password"):
        return None, 409, PASSWORD_FIELD
    if action == "type":
        text = step.get("text")
        if not isinstance(text, str) or not text.strip():
            return None, 400, "A type step needs the text to type."
        if len(text) > MAX_TEXT:
            return None, 400, f"The text to type is longer than {MAX_TEXT} characters."
        if not target.get("id") and not target.get("text"):
            return None, 400, "A type step needs the field to type into."
    else:
        text = None
    if action in ("tap", "type", "swipe"):
        if not target.get("id") and not target.get("text"):
            return None, 400, "That step needs the control it targets."
    if action == "swipe" and len(target.get("bounds") or []) != 4:
        return None, 400, "A swipe needs the four bounds of the area to swipe."
    refusal, _hit = _scan_words(label, target.get("text", ""), target.get("id", ""), why)
    if refusal:
        return None, 409, refusal
    protected = _names_protected(label, target.get("text", ""), target.get("id", ""),
                                 why, app)
    if protected:
        return None, 409, PROTECTED_FILE
    snapshot = doc.get("snapshot")
    if not isinstance(snapshot, dict):
        return None, 400, "Send the screen snapshot you just read."
    if _clean(snapshot.get("app"), 200) != app:
        return None, 409, SCREEN_CHANGED
    if action != "back" and action != "home":
        if not _control_present(snapshot, target):
            return None, 409, NOT_FOUND
    plan = {
        "app": app,
        "app_name": label,
        "step": {"action": action, "target": target, "text": text, "why": why},
    }
    return plan, 202, ""


_VERB_WORDS = {"tap": "tap", "swipe": "swipe", "type": "type into",
               "back": "press Back", "home": "go to the Home screen"}


def _target_words(plan: dict) -> str:
    step = plan["step"]
    target = step.get("target") or {}
    if step["action"] in ("back", "home"):
        return ""
    label = target.get("text") or target.get("id") or "(that control)"
    return f' "{label}"'


def plan_card(plan: dict) -> str:
    """The card text: the app, the ONE step, what it types, and what refusing costs."""
    step = plan["step"]
    action = step["action"]
    line = f"Step 1 of 1: {_VERB_WORDS.get(action, action)}{_target_words(plan)}"
    if action == "type":
        line += f' - the exact text: "{step.get("text")}"'
    why = step.get("why") or ""
    return (
        f"Let Jarvis act in {plan['app_name']} on your phone?\n\n"
        f"App: {plan['app_name']} ({plan['app']})\n"
        f"{line}\n"
        + (f"Why: {why}\n" if why else "")
        + "\nThis is ONE step, and one card approves it - nothing is touched "
          "until you say yes. The phone checks the screen again just before it "
          "acts; a screen that changed stops the run. Stop on the phone cancels "
          "it, and no second step runs without a new plan and a new card.\n\n"
          "If you say no: nothing is touched, and nothing runs."
    )


def card_detail(plan: dict) -> dict:
    """The gate's `detail`: the card, and counts/names - never the typed text
    as a separate field (the card itself carries it for the owner to read)."""
    return {"text": plan_card(plan),
            "app": plan["app"], "app_name": plan["app_name"],
            "verb": plan["step"]["action"],
            "what": "one action in one allow-listed app on your phone"}


def audit_detail(plan: dict, phase: str, outcome: str = "") -> dict:
    """The audit line's shape: app + verb only, caps, no text, no snapshot.

    The owner's typed text and the screen's words never go in the audit log -
    the card is the one place the exact step is written down. This function is
    the single place audit rows are built, and the suite holds it to that.
    """
    out = {"app": plan.get("app", ""), "verb": plan.get("step", {}).get("action", "")}
    if phase:
        out["phase"] = str(phase)[:40]
    if outcome:
        out["outcome"] = str(outcome)[:40]
    return out


# --------------------------------------------------------------------------
#   The run state machine - started / pending / approved / delivered / done /
#   stopped, and stop-on-change
# --------------------------------------------------------------------------

_LOCK = threading.Lock()
#: The one run this PC is handling. One at a time, like every other card this
#: project raises: a second run while one waits is refused rather than queued,
#: so "which card is the real one" is never a question.
_RUN: Optional[dict] = None
#: run id -> run, so `/step` can find the current one (one at a time, kept in
#: a dict only so a finished run's id answers "finished" instead of "unknown").
_RUNS: dict = {}


def _view(run: Optional[dict]) -> Optional[dict]:
    """Counts and words only - never the plan, the typed text or a snapshot."""
    if run is None:
        return None
    return {"id": run["id"], "state": run["state"], "app": run["plan"]["app"],
            "verb": run["plan"]["step"]["action"], "since": run["since"]}


def state() -> dict:
    """/api/app-control has no GET route; this is for the suite and for the
    banner: whether the feature is on, and the one run, counts only."""
    with _LOCK:
        run = _RUN
    return {"available": enabled(), "active": _view(run)}


def _age(run: dict, now: Optional[float] = None) -> float:
    return (now if now is not None else _now()) - run["since"]


def _expired(run: dict, now: Optional[float] = None) -> bool:
    return run["state"] in ("pending", "approved", "delivered") and _age(run, now) > RUN_SECONDS


def _stamp(run: dict, state: str, now: Optional[float] = None) -> None:
    run["state"] = state
    run["at"] = now if now is not None else _now()


def _finish(run: dict, state: str, reason: str = "", now: Optional[float] = None) -> None:
    _stamp(run, state, now)
    run["reason"] = str(reason or "")[:300]
    _audit(f"app_control.{state}", audit_detail(run["plan"], state))


def stage_run(doc, *, gate: Optional[Callable] = None, spawn: Optional[Callable] = None,
              tier_of: Optional[Callable[[str], str]] = None,
              taint: Optional[Callable[[], bool]] = None,
              framework: Optional[dict] = None,
              now: Optional[float] = None) -> tuple:
    """POST /api/app-control/run: validate, raise ONE card, return the run id.

    Runs NOTHING: the request thread returns at once and the card waits on its
    own thread (jarvis_gate.check blocks for a person, so it must not block the
    HTTP request). All the dependencies are injectable for the suite; the
    defaults are the real gate, the real framework and a daemon thread.
    """
    global _RUN
    gate = gate or _gate
    spawn = spawn or _spawn
    tier_of = tier_of or _tier_of
    taint = taint or _tainted
    if not enabled(framework):
        return 409, {"ok": False, "available": False, "error": OFF}
    if taint():
        return 409, {"ok": False, "available": False, "error": TAINTED}
    if not isinstance(doc, dict):
        return 400, {"ok": False, "error": BAD_BODY}
    allowed, why = parse_allowed(doc.get("allowed"))
    if why:
        return 400, {"ok": False, "error": why}
    plan, code, error = validate_plan(doc, allowed)
    if plan is None:
        return code, {"ok": False, "error": error, "allowed": len(allowed)}
    try:
        tier = tier_of(ACTION)
    except Exception as exc:
        tier = f"unreadable ({type(exc).__name__})"
    if tier != "ask":
        return 409, {"ok": False, "pending": False,
                     "error": (f"{ACTION} is tier {tier!r} in jarvis-framework.toml; "
                               f"letting Jarvis act in another app needs a person to "
                               f"say yes, so it must be 'ask'. Nothing was changed.")}
    with _LOCK:
        live = _RUN
        if live is not None and _expired(live, now):
            # A card nobody answered must not keep the next request out for
            # ever; the gate's own timeout ends the waiting thread, and this
            # ends the run the same way when that thread has not got there yet.
            _finish(live, "stopped", "the approval card expired", now)
            live = None
        if live is not None and live["state"] not in ("done", "stopped", "denied",
                                                      "timed_out", "refused", "failed"):
            left = max(0, int(RUN_SECONDS - _age(live, now)))
            return 409, {"ok": False, "pending": True, "rule": SECOND_RUN,
                         "expires_in": left}
        rid = uuid.uuid4().hex
        run = {"id": rid, "state": "pending", "plan": plan,
               "since": now if now is not None else _now(),
               "decision": "", "reason": "", "delivered": False,
               "card_requested": _now() if now is None else now}
        _RUN = run
        _RUNS[rid] = run
    _audit("app_control.requested", audit_detail(plan, "requested"))

    def work():
        try:
            _decide(rid, gate=gate)
        except Exception:
            with _LOCK:
                mine = _RUN if (_RUN and _RUN["id"] == rid) else None
                if mine is not None and mine["state"] == "pending":
                    _finish(mine, "failed", "unexpected error")

    try:
        spawn(work)
    except Exception as exc:
        with _LOCK:
            if _RUN is not None and _RUN["id"] == rid:
                _finish(_RUN, "failed", f"could not start ({type(exc).__name__})")
        return 500, {"ok": False, "error": "could not raise the approval card"}
    return 202, {"ok": True, "run": rid, "status": "pending",
                 "app": plan["app"], "verb": plan["step"]["action"],
                 "message": ("Approve the card on your PC or phone to allow "
                             "this ONE step. Nothing runs until you do.")}


def _verdict(v) -> tuple:
    """(outcome, request_id, why) from a jarvis_gate.check answer.

    The same reading every module in this project uses: only a person's "ask"
    tier can be a yes, and a verdict without an outcome (an older gate) is read
    as approved only when allowed AND at tier ask.
    """
    vtier = getattr(v, "tier", "unknown")
    allowed = getattr(v, "allowed", False) is True
    outcome = getattr(v, "outcome", None)
    if outcome is None:
        outcome = "approved" if (allowed and vtier == "ask") else "refused"
    rid = getattr(v, "request_id", None)
    if vtier != "ask":
        return "refused", rid, (f"the gate answered at tier {vtier!r}, which is "
                                f"not a person saying yes")
    if allowed and outcome == "approved":
        return "approved", rid, ""
    if outcome in ("denied", "timed_out"):
        return outcome, rid, ""
    return "refused", rid, str(getattr(v, "reason", "refused"))[:200]


def _decide(rid: str, *, gate: Callable) -> dict:
    """Raise the card for run `rid`, wait for the answer, record the outcome.

    Blocks - runs on the card's own thread (see stage_run). Nothing is handed
    to the phone before this returns approved: `/step` answers "pending" until
    then, and every other outcome ends the run with no step ever sent.
    """
    with _LOCK:
        run = _RUN if (_RUN and _RUN["id"] == rid) else None
        if run is None or run["state"] != "pending":
            return {"outcome": "gone"}
        plan = run["plan"]
    detail = card_detail(plan)
    prompt = detail["text"]
    try:
        v = gate(ACTION, detail, prompt)
    except Exception as exc:
        with _LOCK:
            mine = _RUN if (_RUN and _RUN["id"] == rid) else None
            if mine is not None and mine["state"] == "pending":
                _finish(mine, "refused", f"the approval gate failed ({type(exc).__name__})")
        return {"outcome": "refused"}
    outcome, request_id, why = _verdict(v)
    with _LOCK:
        mine = _RUN if (_RUN and _RUN["id"] == rid) else None
        if mine is None or mine["state"] != "pending":
            return {"outcome": "gone"}
        mine["decision"] = outcome
        mine["request_id"] = request_id
        if outcome == "approved":
            _stamp(mine, "approved")
        else:
            _finish(mine, outcome, why or "the card was not approved")
        return {"outcome": outcome}


def _matching_run(body: dict) -> tuple:
    rid = _clean(body.get("run"), 80)
    with _LOCK:
        run = _RUN if (_RUN and _RUN["id"] == rid) else _RUNS.get(rid)
    if run is None:
        return None, 404, UNKNOWN_RUN
    return run, 200, ""


def _stop(run: dict, why: str, now: Optional[float]) -> tuple:
    """Stop a run: the safe direction, so it needs no card and no hesitation."""
    with _LOCK:
        if run["state"] in ("done", "stopped", "denied", "timed_out", "refused", "failed"):
            return 200, {"ok": False, "status": run["state"], "error": FINISHED}
        _finish(run, "stopped", why, now)
    return 200, {"ok": False, "status": "stopped", "error": why}


def step(body, *, now: Optional[float] = None,
         taint: Optional[Callable[[], bool]] = None) -> tuple:
    """POST /api/app-control/step: the phone asks for the ONE approved step.

    States, in the order they are answered:
      -- `{"stop": true}` stops the run at once (stop is never gated);
      -- a run that is PENDING_APPROVAL answers "pending" and no step;
      -- denied/timed out/refused/finished runs answer their state, no step;
      -- an APPROVED run re-checks the phone's fresh snapshot: a wrong app, a
         changed control, a vanished control or a password field STOPS the run;
         otherwise it returns exactly the step the card approved, once;
      -- a DELIVERED run takes the phone's result ("done"/"failed") and ends.
    The returned step is always rebuilt from the stored plan - never from the
    request - so the phone cannot swap in a different action or target.
    """
    taint = taint or _tainted
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": BAD_BODY}
    run, code, error = _matching_run(body)
    if run is None:
        return code, {"ok": False, "error": error}
    if body.get("stop") is True:
        return _stop(run, "stopped by the owner", now)
    with _LOCK:
        if _expired(run, now):
            _finish(run, "stopped", "the plan expired; make a new one", now)
            return 200, {"ok": False, "status": "stopped",
                         "error": "That plan expired before it ran; ask Jarvis again."}
        current = run["state"]
    if current == "pending":
        return 202, {"ok": True, "status": "pending", "message": PENDING_MSG}
    if current in ("denied", "timed_out", "refused", "failed"):
        return 200, {"ok": False, "status": current,
                     "error": run.get("reason") or "the card was not approved"}
    if current in ("done", "stopped"):
        return 200, {"ok": False, "status": current, "error": FINISHED}
    if current == "delivered":
        result = _clean(body.get("result"), 20).lower()
        if result not in ("done", "failed"):
            return 409, {"ok": False, "status": "delivered",
                         "error": 'The step was sent; report "result": "done" or '
                                  '"failed" after it runs.'}
        with _LOCK:
            _finish(run, "done" if result == "done" else "failed",
                    "" if result == "done" else "the phone could not do the step", now)
        return 200, {"ok": result == "done", "status": run["state"]}
    if current == "approved":
        if taint():
            return _stop(run, TAINTED, now)
        snapshot = body.get("snapshot")
        if not isinstance(snapshot, dict):
            return _stop(run, SCREEN_CHANGED, now)
        plan = run["plan"]
        if _clean(snapshot.get("app"), 200) != plan["app"]:
            return _stop(run, SCREEN_CHANGED, now)
        action = plan["step"]["action"]
        if action not in ("back", "home"):
            live = None
            for candidate in _snapshot_controls(snapshot):
                if _same_identity(plan["step"]["target"], _target_of({"target": candidate})):
                    live = candidate
                    break
            if live is None:
                return _stop(run, NOT_FOUND, now)
            if live.get("password") is True:
                return _stop(run, PASSWORD_FIELD, now)
            if live.get("enabled") is False:
                return _stop(run, SCREEN_CHANGED, now)
        with _LOCK:
            if run["state"] != "approved":
                return 200, {"ok": False, "status": run["state"], "error": FINISHED}
            _stamp(run, "delivered", now)
            run["delivered"] = True
        _audit("app_control.step", audit_detail(plan, "step", "delivered"))
        step_out = {"action": action}
        if action in ("tap", "type", "swipe"):
            step_out["target"] = dict(plan["step"]["target"])
        if action == "type":
            step_out["text"] = plan["step"]["text"]
        return 200, {"ok": True, "status": "step", "run": run["id"],
                     "step": step_out,
                     "message": "Do this one step, then report done or failed."}
    return 409, {"ok": False, "status": current, "error": FINISHED}


def _reset_for_tests() -> None:
    global _RUN, _RUNS
    with _LOCK:
        _RUN = None
        _RUNS = {}


# The suite imports nothing below this line; keep the file importable without
# a phone, a gate or the owner's settings.
