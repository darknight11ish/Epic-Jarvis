"""jarvis_browser_control.py - lets Jarvis drive one browser tab, one step at
a time. Built for the case that started this: "control a chat for me" - a
customer-service widget, a support ticket form, anything on the open web that
has no API.

WHY THIS IS NOT JUST `browser-use`
`docs/ARCHITECTURE.md`'s "Decisions already taken" table already rejected
`browser-use` by name: "dies at 8k context by step 2-3". That framework hands
the model the page - or a screenshot of it - fresh on every step, and keeps
clicking on its own judgment in a loop until the goal looks done. Both of
those are exactly what `docs/UFO-SAFETY-DESIGN.md` already ruled out for
`jarvis_ui_control.py`, for the same reason: a live perceive-act loop is a
standing grant for future, unnamed actions, which is this project's one hard
rule to never do. This module is `jarvis_ui_control.py`'s shape, not
`browser-use`'s, aimed at a browser tab instead of a native window:

    plan(goal, session, requests)   reads the CURRENT page of one browser
                                     session - no input is sent - and binds
                                     each requested step to a concrete,
                                     named element actually on that page.
                                     Returns a Plan: a bounded, fully
                                     enumerated list of Steps decided now,
                                     not improvised later.
    run(plan, approved=True)        executes ONLY the enumerated steps, in
                                     order. Before each one (`navigate`
                                     excepted, which has nothing yet to
                                     re-check), re-reads the page and
                                     confirms the target is still there and
                                     still enabled. The moment that is not
                                     true - the page navigated away, a
                                     dialog covered it, the chat widget
                                     closed - run() STOPS and reports
                                     exactly which step failed, rather than
                                     guessing or clicking the nearest thing.
                                     Whatever changed needs a new plan() and
                                     a new decision, not a retry of the old
                                     one.

Same reasoning as `jarvis_ui_control.py` for why one card can cover several
steps without being an "approve-all": one decision for one bounded, fully
printed set of steps is not a standing grant. A goal that needs to change
mid-way is a NEW plan and a new decision.

THE CONTEXT-ECONOMY RULE THIS MODULE IS BUILT AROUND
"Dies at 8k context by step 2-3" is not a vague complaint - it is what
happens when every step's result feeds the whole page, or a growing
transcript, back into the model. Every read here is a short list of
(role, name) pairs, never raw HTML and never a screenshot; `_MAX_ELEMENTS`
bounds how many the model ever sees from one page, and `_MAX_READ_VALUE_CHARS`
bounds any single value a `read` step hands back (a chat transcript is
read as one capped preview, not the page's entire text). Both are enforced
in `run()` itself, not left to the 8000-character whole-result cutoff
`jarvis_agent._tool_content()` already has - that cutoff throws the whole
result away once it is too big; this keeps each step small enough that it
never gets there, so a five-step conversation with a support widget does not
cost noticeably more context than one step did.

THE SAME RULE, APPLIED TO A CONVERSATION THAT NEVER STOPS
"Continue a conversation extremely long" is the same context-economy problem
at a different timescale: read the WHOLE transcript again on message 40 and
cost has grown with the conversation's length, no matter how tight any one
step's cap is. `read_new` is the fix - it takes a container (a chat log, a
message list) and a cursor (the index already seen) and returns only the
messages after that cursor, capped at `_MAX_NEW_MESSAGES` and
`_MAX_MESSAGE_CHARS` per call, with the cap saying so plainly (a "N more not
shown, call again with value=..." trailer) rather than silently dropping
anything. Turn 40 of a long-running chat costs the same as turn 2: the size
of what changed, not the size of the whole conversation so far.

SHIPS DISABLED, ON PURPOSE
Feature-complete, not switched on. See `backend/README.md`'s own section on
this. Two real reasons, not caution for its own sake: it needs Playwright
actually installed (a new dependency this project has not taken before), and
it needs a model with real context headroom to spend on several rounds of
page-plus-history - the primary lane `docs/MODEL-TOPOLOGY.md` describes
(8B, 16K context, already budgeted to 6.48 of 6.90 GiB) is sized tight on
purpose and is not where this belongs. Add `"browser_control"` to
`[tools].enabled` only once a second, larger-context lane is actually
running - not before, and not "to see if it fits".

WHAT ACTUALLY HAPPENS, AND WHAT DOES NOT LEAVE THIS MACHINE
Unlike `jarvis_ui_control.py`, where only some steps reach the network,
every step here already involves a browser that is, by definition, talking
to some remote site. That does not make the machine's own trust rule
different - `LEAVES_MACHINE_HINT` still exists so the caller states plainly,
per step, that a click or a typed message is about to be sent to whoever is
on the other end of that page; the card shows it, the human decides. Same as
`jarvis_research.py`: the caller says what leaves the machine, this module
does not infer it.

`navigate` steps are restricted to `http://`/`https://` URLs - a
`javascript:`/`data:`/`file:` scheme becomes an unmatched request, not a
step, the same way an unknown UI-control action would be. Callers may also
pass `allowed_domains` to `plan()`: a plain list of hostnames (subdomains of
a listed one count as a match); a `navigate` request to anything else is
reported unmatched instead of becoming a step. Omitted, there is no
restriction beyond the scheme check - the same "caller decides the fence"
posture as everything else in this module.

TESTING WITHOUT A REAL BROWSER
Real page reads and real input happen through two small functions, `read`
and `act`, both injectable - exactly how `jarvis_ui_control.py` injects
`read`/`act` for `uiautomation`. Nothing in this file imports Playwright at
module load time; the default `read`/`act` only try to import it when
actually called with nothing injected, and fail with a clear message rather
than a stack trace from deep inside a missing dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Callable, Optional
from urllib.parse import urlparse

# The one thing a caller MUST tell this module, because it cannot infer it
# from the page on its own: whether a step sends something to whoever is on
# the other end. Mirrors jarvis_ui_control.IRREVERSIBLE_HINT/LEAVES_MACHINE_HINT.
IRREVERSIBLE_HINT = "irreversible"
LEAVES_MACHINE_HINT = "leaves_machine"

# Schemes a navigate step is allowed to target. Everything else - javascript:,
# data:, file:, chrome: - becomes an unmatched request rather than a step,
# the same treatment an unknown action already gets.
_ALLOWED_SCHEMES = {"http", "https"}


# --------------------------------------------------------------------------
#   The plan - built locally from a live but read-only look at the page
# --------------------------------------------------------------------------

@dataclass
class Step:
    """One concrete action, bound to one concrete element (or, for
    `navigate`, to nothing - there is no element to bind yet). Nothing here
    is resolved again at run() time except to VERIFY it still matches - the
    identity was decided at plan() time, not guessed at run() time."""
    session: str
    url: str                 # the page this step was planned against
    role: str                # accessibility role: "button", "textbox", "link", ... ("" for navigate)
    name: str                # accessible name, as read from the page ("" for navigate)
    action: str               # "navigate" | "click" | "type" | "select" | "read" | "read_new"
    value: Optional[str] = None
    why: str = ""
    heavy: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Plan:
    goal: str
    session: str
    steps: list = field(default_factory=list)
    # Requests that named an element the page did not have, or a navigate
    # target the scheme/domain check rejected. Not steps; will not run -
    # describe() must say so plainly, same reason as jarvis_ui_control.py.
    unmatched: list = field(default_factory=list)
    if_refused: str = ""

    @property
    def weight(self) -> str:
        return "heavy" if any(s.heavy for s in self.steps) else "normal"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["weight"] = self.weight
        return d


# How many interactive elements one read() ever returns to the caller. A real
# page can have hundreds of accessibility nodes; describe()'s card size is
# already bounded by the (small, model-authored) request count, but the
# snapshot plan() searches against is not, so this caps the work plan() does
# and keeps a pathological page from turning one read into a slow, huge scan.
_MAX_ELEMENTS = 300

# Same reasoning as jarvis_ui_control._READ_DEPTH: an explicit, generous-but-
# finite tree-walk depth, not unbounded recursion into a deeply nested page.
_READ_DEPTH = 12

# The actual fix for "dies at 8k context by step 2-3": any value a `read`
# step hands back - a chat transcript, an input's current text - is capped
# here, in run(), so it stays small on every single step rather than only
# being caught once the *whole* tool result is already too big to send.
_MAX_READ_VALUE_CHARS = 700

# `read_new`'s own caps - see _format_new_messages. Deliberately smaller and
# separate from _MAX_READ_VALUE_CHARS: this is the piece built for "continue
# a conversation extremely long" - a chat that has been going for an hour
# must cost the same, small amount per turn as one that just started,
# because only the messages since the last cursor are ever read, never the
# whole transcript again.
_MAX_NEW_MESSAGES = 15
_MAX_MESSAGE_CHARS = 300


def _format_new_messages(children_text: list, since: int) -> str:
    """Pure formatting/capping for a `read_new` step - independent of
    Playwright on purpose, so the property that matters (only what's new is
    ever returned, and a cap that bites SAYS SO rather than silently
    dropping the rest) is provable directly, the same "no silent
    truncation" rule `jarvis_agent._tool_content()` already holds itself to.

    `children_text` is the container's children, in DOM order, as plain
    text - the whole transcript, not yet trimmed to what's new. `since` is
    the index the caller already saw up to; everything at or after it is
    "new". Returns a capped, indexed block, and - only when the cap
    actually bit - one more line naming how many are left out and the
    cursor value to ask for them with.
    """
    since = max(int(since), 0)
    new = list(enumerate(children_text))[since:]
    if not new:
        return f"(no new messages; {len(children_text)} total, cursor was {since})"
    shown = new[:_MAX_NEW_MESSAGES]
    lines = [f"[{i}] {text[:_MAX_MESSAGE_CHARS]}" for i, text in shown]
    remaining = len(new) - len(shown)
    if remaining > 0:
        next_cursor = shown[-1][0] + 1
        lines.append(f"...({remaining} more not shown; call again with "
                      f"value={next_cursor!r} to continue from there)")
    return "\n".join(lines)


def _host_matches(url: str, allowed_domains: Optional[list]) -> bool:
    if not allowed_domains:
        return True
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    for d in allowed_domains:
        d = str(d).lower().lstrip(".")
        if host == d or host.endswith("." + d):
            return True
    return False


def _default_read(session: str) -> dict:
    """The real page read. Lazily imports Playwright so this module loads
    fine with nothing installed, and fails clearly - not with an ImportError
    three frames down - when nobody injected a `read`."""
    try:
        page = _page_for(session, create=False)
    except ImportError as exc:
        raise RuntimeError(
            "no page reader was given and 'playwright' is not installed - "
            "this only works with Playwright's Chromium present, or with a "
            "`read` function supplied for testing"
        ) from exc
    if page is None:
        return {"url": "", "title": "", "elements": []}
    tree = page.accessibility.snapshot() or {}
    elements: list = []

    def walk(node: dict, depth: int) -> None:
        if depth <= 0 or len(elements) >= _MAX_ELEMENTS:
            return
        role = str(node.get("role") or "")
        name = str(node.get("name") or "")
        if role and name:
            elements.append({
                "role": role, "name": name,
                "text": str(node.get("value") or node.get("name") or "")[:200],
                "enabled": not bool(node.get("disabled")),
            })
        for child in (node.get("children") or []):
            if len(elements) >= _MAX_ELEMENTS:
                return
            walk(child, depth - 1)

    walk(tree, _READ_DEPTH)
    return {"url": page.url, "title": page.title(), "elements": elements}


def _default_act(step: Step) -> Optional[str]:
    """Returns the read-back text for a "read" step, None for every other
    action - run() folds a non-None return into that step's own `value`
    (capped) before it is reported as done."""
    try:
        page = _page_for(step.session, create=True)
    except ImportError as exc:
        raise RuntimeError(
            "no `act` function was given and 'playwright' is not installed "
            "- see _default_read"
        ) from exc
    if step.action == "navigate":
        page.goto(step.value or "", wait_until="domcontentloaded")
        return None
    locator = page.get_by_role(step.role, name=step.name, exact=True).first
    if step.action == "click":
        locator.click()
    elif step.action == "type":
        locator.fill(step.value or "")
    elif step.action == "select":
        locator.select_option(label=step.value or "")
    elif step.action == "read":
        try:
            return locator.input_value()
        except Exception:
            return locator.inner_text()
    elif step.action == "read_new":
        # step.role/step.name name the CONTAINER (a chat log, a message
        # list) - its direct children are the individual messages, in the
        # order the page renders them. Reading text off children rather
        # than matching by (role, name) is deliberate: a message bubble
        # rarely has a distinct accessible name of its own, so the
        # (role, name) matching every other action uses would not find it.
        count = locator.locator(":scope > *").count()
        texts = [locator.locator(":scope > *").nth(i).inner_text()
                 for i in range(min(count, _MAX_ELEMENTS))]
        return _format_new_messages(texts, int(step.value or 0))
    else:
        raise ValueError(f"unknown action {step.action!r}")
    return None


# One Chromium instance for the process's life, not relaunched per call -
# same "long-lived resource behind a lazy singleton" shape as this being a
# desktop backend already implies for Ollama's own model residency
# (OLLAMA_KEEP_ALIVE=-1 in jarvis-primary.Modelfile). Launched NOT headless
# on purpose: the owner should be able to see the tab Jarvis is driving, the
# same transparency jarvis_events.set_activity gives the rest of this
# project's actions.
_sessions: dict = {}
_browser = None
_playwright = None


def _page_for(session: str, *, create: bool):
    global _browser, _playwright
    if session in _sessions:
        return _sessions[session]
    if not create:
        return None
    if _browser is None:
        from playwright.sync_api import sync_playwright  # type: ignore
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(headless=False)
    page = _browser.new_page()
    _sessions[session] = page
    return page


def close(session: Optional[str] = None) -> None:
    """Close one session's tab, or every open tab and the browser itself if
    `session` is omitted. Not called automatically by anything here - a
    caller that opens sessions is the one that knows when it is done with
    them."""
    global _browser, _playwright
    if session is not None:
        page = _sessions.pop(session, None)
        if page is not None:
            page.close()
        return
    for page in _sessions.values():
        page.close()
    _sessions.clear()
    if _browser is not None:
        _browser.close()
        _browser = None
    if _playwright is not None:
        _playwright.stop()
        _playwright = None


def _find(elements: list, role: str, name: str) -> Optional[dict]:
    for e in elements:
        if e.get("role") == role and e.get("name") == name:
            return e
    return None


def plan(goal: str, session: str, requests: list, *,
         allowed_domains: Optional[list] = None,
         read: Optional[Callable[[str], dict]] = None) -> Plan:
    """Work out the concrete steps. Reads the current page; sends no input.

    `requests` is a list of dicts, each naming what the caller wants to
    happen - not yet bound to anything real:

        {"action": "navigate", "value": "https://example.com/support",
         "why": "...", "leaves_machine": True}
        {"role": "textbox", "name": "Message", "action": "type",
         "value": "my order hasn't arrived", "why": "...",
         "leaves_machine": True}
        {"role": "button", "name": "Send", "action": "click", "why": "...",
         "leaves_machine": True}
        {"role": "log", "name": "Conversation", "action": "read_new",
         "value": "12", "why": "check for a reply"}

    `read_new`'s `role`/`name` name a CONTAINER (a chat log, a message
    list), not one message - see `_format_new_messages` for why a message
    bubble is read by position, not by (role, name) matching. `value` is the
    index already seen; omitted or `"0"` reads from the start, bounded the
    same as everything else by `_MAX_NEW_MESSAGES`.

    A `navigate` request is checked against `_ALLOWED_SCHEMES` and
    `allowed_domains`, never against the current page - there may not be one
    yet. Every other request is checked against the CURRENT page right now;
    an element that is not there - or not enabled - is not guessed at, it is
    reported in `unmatched` and simply does not become a step.
    """
    getter = read or _default_read
    current = getter(session) or {"url": "", "title": "", "elements": []}
    elements = current.get("elements") or []
    url = str(current.get("url") or "")
    steps, unmatched = [], []
    for r in requests:
        action = str(r.get("action", "")).strip()
        heavy = bool(r.get(IRREVERSIBLE_HINT)) or bool(r.get(LEAVES_MACHINE_HINT))
        if action == "navigate":
            target = str(r.get("value", ""))
            scheme = urlparse(target).scheme.lower()
            if scheme not in _ALLOWED_SCHEMES:
                unmatched.append({**r, "reason": f"scheme {scheme!r} is not allowed"})
                continue
            if not _host_matches(target, allowed_domains):
                unmatched.append({**r, "reason": "domain is not in allowed_domains"})
                continue
            steps.append(Step(session=session, url=url, role="", name="",
                               action="navigate", value=target,
                               why=str(r.get("why", "")), heavy=heavy))
            continue
        role = str(r.get("role", "")).strip()
        name = str(r.get("name", "")).strip()
        found = _find(elements, role, name)
        if not found or not found.get("enabled", True):
            unmatched.append({**r, "reason": "not found" if not found
                               else "found but disabled"})
            continue
        steps.append(Step(
            session=session, url=url, role=role, name=name, action=action,
            value=r.get("value"), why=str(r.get("why", "")), heavy=heavy))
    return Plan(
        goal=str(goal), session=str(session), steps=steps, unmatched=unmatched,
        if_refused="nothing on this page changes; the goal is not attempted")


def describe(p: Plan) -> str:
    """The card text. Every step in full, in the order it would run."""
    lines = [f'Jarvis would like to do this in the browser session "{p.session}": {p.goal}',
             "", f"{len(p.steps)} step(s), weight: {p.weight}.", ""]
    if not p.steps:
        lines.append("No requested step could be matched, so nothing would happen.")
    for i, s in enumerate(p.steps, 1):
        heavy_note = "  [sends something to the other end]" if s.heavy else ""
        if s.action == "navigate":
            lines += [f"  {i}. navigate to {s.value!r}{heavy_note}", f"     why: {s.why}", ""]
        elif s.action == "read_new":
            lines += [f'  {i}. read new messages in {s.role} "{s.name}" '
                      f'since #{s.value or 0}{heavy_note}',
                      f"     why: {s.why}", ""]
        else:
            detail = f" = {s.value!r}" if s.value is not None else ""
            lines += [f'  {i}. {s.action} {s.role} "{s.name}"{detail}{heavy_note}',
                      f"     why: {s.why}", ""]
    if p.unmatched:
        lines.append(f"{len(p.unmatched)} requested step(s) could NOT be "
                      "matched and will NOT run:")
        for u in p.unmatched:
            label = u.get("value") if u.get("action") == "navigate" else u.get("name")
            lines.append(f"  - {label!r}: {u.get('reason')}")
        lines.append("")
    lines.append(f"If you say no: {p.if_refused}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   Execution - only the enumerated steps, re-verified just before each one
# --------------------------------------------------------------------------

def run(p: Plan, *, read: Optional[Callable[[str], dict]] = None,
        act: Optional[Callable[[Step], Optional[str]]] = None,
        announce: Optional[Callable[[str], None]] = None,
        checkpoint: Optional[Callable[[], Optional[str]]] = None,
        approved: bool = False) -> dict:
    """Execute an approved plan, one step at a time.

    `approved` has no default of True, same reason as jarvis_ui_control.py: a
    module that can act on the world must not be one call away from doing it
    by accident.

    Before every step except `navigate` (which has no prior element to
    re-check), the live page is re-read and the target must still exist and
    still be enabled. If it does not, execution STOPS at that step - steps
    already done are reported as done, the failing step and everything after
    it are reported as not run. That is a new plan() and a new decision.

    `announce(text)`, if given, is called just before each step - the same
    hook jarvis_ui_control.run() offers for jarvis_events.set_activity.

    `checkpoint()` is the same pause/stop hook as jarvis_ui_control.run -
    see that module's own docstring for the exact contract and why this one
    imports nothing to use it.
    """
    if not approved:
        return {"ok": False, "reason": "not approved; nothing was done",
                "plan": p.as_dict()}
    getter = read or _default_read
    actor = act or _default_act
    tell = announce or (lambda _text: None)
    check = checkpoint or (lambda: None)

    done = []
    for i, step in enumerate(p.steps, 1):
        label = step.value if step.action == "navigate" else f'{step.action} "{step.name}"'
        tell(f"Step {i}/{len(p.steps)}: {label} in session {step.session}")
        signal = check()
        if signal in ("stop", "pause"):
            remaining = p.steps[i - 1:]
            result = {"ok": False,
                      "reason": ("stopped by request" if signal == "stop"
                                 else "paused by request - resuming needs a new decision"),
                      "done": [s.as_dict() for s in done],
                      "not_run": [s.as_dict() for s in remaining]}
            if signal == "pause":
                result["paused"] = True
            return result
        if step.action != "navigate":
            current = getter(step.session) or {"elements": []}
            found = _find(current.get("elements") or [], step.role, step.name)
            if not found or not found.get("enabled", True):
                remaining = p.steps[i - 1:]
                return {"ok": False,
                        "reason": (f'step {i} ("{step.name}" in session '
                                   f"{step.session}) no longer matches what "
                                   "was planned - stopping rather than guessing"),
                        "done": [s.as_dict() for s in done],
                        "not_run": [s.as_dict() for s in remaining]}
        try:
            read_back = actor(step)
        except Exception as exc:
            remaining = p.steps[i - 1:]
            return {"ok": False,
                    "reason": f"step {i} failed: {type(exc).__name__}: {exc}",
                    "done": [s.as_dict() for s in done],
                    "not_run": [s.as_dict() for s in remaining]}
        if step.action == "read" and read_back is not None:
            step.value = str(read_back)[:_MAX_READ_VALUE_CHARS]
        elif step.action == "read_new" and read_back is not None:
            # Already capped and, if truncated, already says so - by
            # _format_new_messages itself (real path) or by the injected
            # `act` in a test. Re-slicing here with _MAX_READ_VALUE_CHARS
            # would risk cutting the "N more not shown" trailer off silently,
            # which is the exact failure this action exists to avoid.
            step.value = str(read_back)
        done.append(step)
    tell("Done.")
    return {"ok": True, "done": [s.as_dict() for s in done], "not_run": []}
