"""jarvis_browser_control.py - lets Jarvis drive one browser tab, one step at
a time. Built for the case that started this: "control a chat for me" - a
customer-service widget, a support ticket form, anything on the open web that
has no API.

WHY THIS IS NOT JUST `browser-use` - AND WHICH PARTS OF IT WERE ADOPTED
`docs/ARCHITECTURE.md`'s "Decisions already taken" table rejected
`browser-use` as a framework by name: "dies at 8k context by step 2-3". That
framework hands the model the page - or a screenshot of it - fresh on every
step, and keeps clicking on its own judgment in a loop until the goal looks
done. Both of those are exactly what `docs/UFO-SAFETY-DESIGN.md` already
ruled out for `jarvis_ui_control.py`, for the same reason: a live
perceive-act loop is a standing grant for future, unnamed actions, which is
this project's one hard rule to never do. That rejection stands. This module
is `jarvis_ui_control.py`'s shape, not `browser-use`'s, aimed at a browser tab
instead of a native window:

    plan(goal, session, requests)   reads the CURRENT page of one browser
                                     session - no input is sent - and binds
                                     each requested step to exactly ONE
                                     concrete, named element actually on
                                     that page. Returns a Plan: a bounded,
                                     fully enumerated list of Steps decided
                                     now, not improvised later.
    run(plan, approved=True)        executes ONLY the enumerated steps, in
                                     order. Before each one (`navigate`
                                     excepted, which has nothing yet to
                                     re-check), re-reads the page and
                                     confirms the target is still there,
                                     still unique and still enabled. After
                                     each one, looks at what the step caused.
                                     The moment anything is off - the page
                                     navigated away, a dialog asked a
                                     question, a pop-up or download appeared,
                                     the tab crashed, the chat widget closed -
                                     run() STOPS and reports exactly which
                                     step and why, rather than guessing or
                                     clicking the nearest thing. Whatever
                                     changed needs a new plan() and a new
                                     decision, not a retry of the old one.

What WAS adopted from browser-use (MIT, v0.13.10), with the loop left out -
its parts that make a single, human-approved step safer and cheaper, not the
parts that decide what to do next. Code that is copied or closely adapted
carries an "Adapted from browser-use" comment naming the source file:

  * Page reading. `_elements_from_cdp` reads the page through the Chrome
    DevTools Protocol (`Accessibility.getFullAXTree` plus
    `DOMSnapshot.captureSnapshot`), the way `browser_use/dom/service.py`
    does. It keeps only elements that are actually visible
    (display/visibility/opacity, the idea in `is_element_visible_according_
    to_all_parents`) and not hidden behind something painted on top of them
    (`browser_use/dom/serializer/paint_order.py`'s rectangle-union test),
    and marks which of them are genuinely interactive
    (`browser_use/dom/serializer/clickable_elements.py`). What it hands
    back is the same compact (role, name) records as before - never raw
    HTML, never a screenshot.
  * The domain fence on every navigation, not only on `navigate` steps -
    `browser_use/browser/watchdogs/security_watchdog.py`'s idea of checking
    a URL before it loads AND after it lands (a redirect), and a new tab's
    URL too.
  * Watching for dialogs, pop-ups, downloads and crashes
    (`watchdogs/popups_watchdog.py`, `downloads_watchdog.py`,
    `crash_watchdog.py`) - but NOT their answers: browser-use clicks OK on
    a `confirm()` and lets downloads through. Here a question is never
    answered yes, and a download is always blocked. See `_wire_page`.
  * Waiting for the page to settle after a step (`watchdogs/
    dom_watchdog.py`'s pending-network wait), bounded by timeouts.
  * Page to clean text: `read_page`, after `browser_use/dom/
    markdown_extractor.py` - without its `markdownify` dependency.
  * Secrets the model never sees: `<secret>name</secret>` placeholders, as
    in `browser_use/tools/registry/service.py`, substituted only at the
    moment of typing, and redacted back out of anything that returns
    (`browser_use/utils.py`'s `redact_sensitive_string`).

Explicitly NOT adopted: the agent loop, LLM providers, cloud/sandbox,
telemetry, sync, skills, the MCP server, video recording, auto-accepting
confirm dialogs, and screenshots to the model.

THE CONTEXT-ECONOMY RULE THIS MODULE IS BUILT AROUND
"Dies at 8k context by step 2-3" is not a vague complaint - it is what
happens when every step's result feeds the whole page, or a growing
transcript, back into the model. Every read here is a short list of
(role, name) records, never raw HTML and never a screenshot; `_MAX_ELEMENTS`
bounds how many the model ever sees from one page, `_MAX_READ_VALUE_CHARS`
bounds any single value a `read` step hands back, and `_MAX_PAGE_TEXT_CHARS`
bounds one `read_page` - with a trailer naming what was left out and where to
continue, never a silent cut. All of them are enforced in this module, not
left to the 8000-character whole-result cutoff `jarvis_agent._tool_content()`
already has - that cutoff throws the whole result away once it is too big;
this keeps each step small enough that it never gets there.

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
purpose and is not where this belongs. The planned second, larger-context
lane is the RTX 2060 12 GB the owner is adding as a second graphics card.
Add `"browser_control"` to `[tools].enabled` only once that lane is actually
running AND has been measured with this tool's real page reads - not when
the card is merely installed, and not "to see if it fits".

Since 2026-09-24 the tool is offered only when BOTH are true: its name in
`[tools].enabled`, and the second graphics card's "Browser control" switch
on and working (jarvis_second_card.lane_for("browser_control"), which needs
"Longer conversations" on too). The model rounds after it runs continue on
that second-card lane (jarvis_agent.run_local_turn). Nothing in this module
changed: every check above still applies, and every step still needs its
own approval.

WHAT ACTUALLY HAPPENS, AND WHAT DOES NOT LEAVE THIS MACHINE
Unlike `jarvis_ui_control.py`, where only some steps reach the network,
every step here already involves a browser that is, by definition, talking
to some remote site. That does not make the machine's own trust rule
different - `LEAVES_MACHINE_HINT` still exists so the caller states plainly,
per step, that a click or a typed message is about to be sent to whoever is
on the other end of that page; the card shows it, the human decides. Same as
`jarvis_research.py`: the caller says what leaves the machine, this module
does not infer it (except that a step typing a saved secret is always marked
heavy - that one is not a judgement call).

`navigate` steps are restricted to `http://`/`https://` URLs - a
`javascript:`/`data:`/`file:` scheme becomes an unmatched request, not a
step. Callers may also pass `allowed_domains` to `plan()`: a plain list of
hostnames (subdomains of a listed one count as a match); a `navigate` request
to anything else is reported unmatched instead of becoming a step.

At run() time the fence covers EVERY way the tab can move, not just
`navigate` steps: a click that follows a link, a redirect, a script that
changes `location`, a new tab. With `allowed_domains` given, that list is
the fence. Without it, the fence is the sites the approved plan itself names
- the page it was planned on, plus each `navigate` target - because a card
that says "click Send on example.com" did not approve typing into whatever
site that click happens to lead to. A navigation outside the fence is
blocked before it loads where the browser allows it (`_make_guard`), and
detected after it lands where it does not (a server-side redirect); either
way the run stops and says where the page tried to go.

TESTING WITHOUT A REAL BROWSER
Real page reads and real input happen through small injectable functions -
`read`, `act`, `observe`, and `secrets` - exactly how `jarvis_ui_control.py`
injects `read`/`act` for `uiautomation`. Nothing in this file imports
Playwright at module load time; the default `read`/`act`/`observe` only try
to import it when actually called with nothing injected, and fail with a
clear message rather than a stack trace from deep inside a missing
dependency. The CDP-to-elements logic (`_elements_from_cdp`) and the
page-to-text logic (`html_to_text`) are pure functions, testable on plain
data with no browser at all.

WHY NOT `page.accessibility.snapshot()` ANY MORE
The first version of this module read the page with Playwright's
`page.accessibility.snapshot()`. That API is gone: on Playwright 1.63.0,
`'accessibility' in dir(playwright.sync_api.Page)` is False, and calling it
on a real page raises `AttributeError: 'Page' object has no attribute
'accessibility'`. The CDP reader below replaced it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict, replace
from html.parser import HTMLParser
from typing import Callable, Optional
from urllib.parse import urlparse, urlunparse

# The one thing a caller MUST tell this module, because it cannot infer it
# from the page on its own: whether a step sends something to whoever is on
# the other end. Mirrors jarvis_ui_control.IRREVERSIBLE_HINT/LEAVES_MACHINE_HINT.
IRREVERSIBLE_HINT = "irreversible"
LEAVES_MACHINE_HINT = "leaves_machine"

# Schemes a navigate step is allowed to target. Everything else - javascript:,
# data:, file:, chrome: - becomes an unmatched request rather than a step,
# the same treatment an unknown action already gets.
_ALLOWED_SCHEMES = {"http", "https"}

# Every action a request may name. Anything else is unmatched at plan() time
# rather than becoming a step that fails half-way through a run.
_ELEMENT_ACTIONS = ("click", "type", "select", "read", "read_new")
_ACTIONS = ("navigate", "read_page") + _ELEMENT_ACTIONS
# Actions that change the page - these need a genuinely interactive target.
_INPUT_ACTIONS = ("click", "type", "select")

# `<secret>name</secret>` - a stand-in for a value the model never sees.
# Names are short and plain on purpose: this is a key into a store, not a
# place to smuggle text.
_SECRET_RE = re.compile(r"<secret>([A-Za-z0-9_.\-]{1,64})</secret>")


# --------------------------------------------------------------------------
#   The plan - built locally from a live but read-only look at the page
# --------------------------------------------------------------------------

@dataclass
class Step:
    """One concrete action, bound to one concrete element (or, for
    `navigate`/`read_page`, to nothing - there is no element to bind).
    Nothing here is resolved again at run() time except to VERIFY it still
    matches - the identity was decided at plan() time, not guessed at run()
    time."""
    session: str
    url: str                 # the page this step was planned against
    role: str                # accessibility role: "button", "textbox", "link", ... ("" for navigate/read_page)
    name: str                # accessible name, as read from the page ("" for navigate/read_page)
    action: str               # one of _ACTIONS
    value: Optional[str] = None   # may hold <secret>name</secret> - NEVER the real secret
    why: str = ""
    heavy: bool = False
    # Only set when the request said which container the element is in -
    # see plan()'s "within". Re-verified by run() like the role and name.
    within_role: str = ""
    within_name: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Plan:
    goal: str
    session: str
    steps: list = field(default_factory=list)
    # Requests that named an element the page did not have (or had more
    # than one of), or a navigate target the scheme/domain check rejected.
    # Not steps; will not run - describe() must say so plainly, same reason
    # as jarvis_ui_control.py.
    unmatched: list = field(default_factory=list)
    if_refused: str = ""
    # The run-time fence. None means "only the sites this plan names" - see
    # the module docstring and _fence_for().
    allowed_domains: Optional[list] = None
    # Things the page did while plan() was looking (a dialog it showed, a
    # download it tried) - shown on the card, never acted on.
    notices: list = field(default_factory=list)

    @property
    def weight(self) -> str:
        return "heavy" if any(s.heavy for s in self.steps) else "normal"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["weight"] = self.weight
        return d


# How many elements one read() ever returns to the caller. A real page can
# have thousands of accessibility nodes; this caps the work plan() does and
# what a caller can ever be handed. When the cap bites, the read says how
# many were left out (see "omitted") and plan() puts that on the card.
_MAX_ELEMENTS = 300

# How far up the accessibility tree a read looks for the named container an
# element sits in ("within"). Generous but finite, same as
# jarvis_ui_control._READ_DEPTH.
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

# `read_page`'s cap - see _format_page_text. Bigger than one `read` value
# because it is a whole page's main text, still small enough that one call
# is a fraction of a 16K context. A longer page is read in pieces: the
# trailer names the offset to continue from.
_MAX_PAGE_TEXT_CHARS = 1500
# How much of the page's main-content HTML the browser hands back to be
# turned into text at all. Only bounds the local work - the model only ever
# sees the _MAX_PAGE_TEXT_CHARS window of the resulting text.
_MAX_PAGE_HTML_CHARS = 2_000_000

# Anything a page itself says (a dialog's message, a pop-up's address)
# reaches the caller capped at this.
_MAX_EVENT_TEXT = 300

# Timeouts for the real browser (milliseconds). Every wait is bounded: a
# page that never settles costs at most these, then the step is judged on
# what is there.
_ACT_TIMEOUT_MS = 8000
_NAV_TIMEOUT_MS = 20000
_SETTLE_LOAD_MS = 5000
_SETTLE_NETWORK_MS = 2000
_DOM_QUIET_MS = 250
_DOM_QUIET_MAX_MS = 1500
# How long a page gets to answer "are you alive" before it is reported as
# not responding (see _probe).
_PROBE_MS = 3000


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


def _format_page_text(text: str, offset: int) -> str:
    """Pure capping for a `read_page` step, same rule as
    _format_new_messages: a window of at most _MAX_PAGE_TEXT_CHARS starting
    at `offset`, and - only when something is left after it - a trailer
    saying how much and the offset to continue from. Never a silent cut."""
    offset = max(int(offset), 0)
    total = len(text)
    if total == 0:
        return "(the page has no readable text)"
    if offset >= total:
        return f"(no more page text; {total} characters total, offset was {offset})"
    chunk = text[offset:offset + _MAX_PAGE_TEXT_CHARS]
    remaining = total - (offset + len(chunk))
    if remaining > 0:
        next_offset = offset + len(chunk)
        chunk += (f"\n...({remaining} more characters not shown; call again "
                  f"with value={next_offset!r} to continue from there)")
    return chunk


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


def _norm(text) -> str:
    """Accessible names compared the way Playwright's exact match compares
    them: surrounding whitespace trimmed, inner runs collapsed."""
    return " ".join(str(text or "").split())


# --------------------------------------------------------------------------
#   Secrets - the model writes <secret>name</secret>, never the value
# --------------------------------------------------------------------------

def _secret_names(value) -> list:
    return _SECRET_RE.findall(value) if isinstance(value, str) else []


def _redact(text, used: dict) -> str:
    """Put every secret value used in this run back behind its placeholder,
    longest first so one secret that contains another cannot leak a piece.

    Adapted from browser-use (MIT, Copyright (c) 2024 Gregor Zunic)
    browser_use/utils.py redact_sensitive_string."""
    text = "" if text is None else str(text)
    values = {v: k for k, v in used.items() if v}
    if not values:
        return text
    ordered = sorted(values, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(v) for v in ordered))
    return pattern.sub(lambda m: f"<secret>{values[m.group(0)]}</secret>", text)


# --------------------------------------------------------------------------
#   Reading a page through CDP - pure, so it is testable on plain data
# --------------------------------------------------------------------------

# The computed styles DOMSnapshot.captureSnapshot is asked for, in order.
# Only what the checks below actually read (browser-use's
# enhanced_snapshot.py makes the same point: asking for more can crash
# Chrome on heavy pages).
_SNAPSHOT_STYLES = ["display", "visibility", "opacity", "cursor",
                    "background-color", "position"]

# CDP's own internal roles are CamelCase ("StaticText", "LabelText",
# "RootWebArea", "InlineTextBox"...) and not something Playwright's
# get_by_role can find; ARIA roles are lowercase. Only these few lowercase
# roles are skipped as well - they never name something a step can target.
_SKIP_ROLES = {"none", "presentation", "generic"}
# ...except that a "generic" element that says it is interactive (an
# onclick div with an aria-label) is kept - see _elements_from_cdp.

# Chrome's role name where it differs from the ARIA name Playwright uses.
_ROLE_TO_ARIA = {"image": "img"}

# Containers a step may name with "within" to tell two same-named elements
# apart ("the Reply button inside the order 2 row").
_CONTAINER_ROLES = {
    "dialog", "alertdialog", "form", "region", "log", "list", "listitem",
    "row", "article", "navigation", "main", "complementary", "group",
    "table", "grid", "feed", "menu", "menubar", "tabpanel", "toolbar",
    "search", "banner", "contentinfo", "listbox", "radiogroup", "tree",
    "treegrid", "tablist",
}

_TRANSPARENT = "rgba(0, 0, 0, 0)"


@dataclass(frozen=True)
class _Rect:
    """Closed axis-aligned rectangle.

    Adapted from browser-use (MIT, Copyright (c) 2024 Gregor Zunic)
    browser_use/dom/serializer/paint_order.py Rect."""
    x1: float
    y1: float
    x2: float
    y2: float

    def intersects(self, other: "_Rect") -> bool:
        return not (self.x2 <= other.x1 or other.x2 <= self.x1
                    or self.y2 <= other.y1 or other.y2 <= self.y1)

    def contains(self, other: "_Rect") -> bool:
        return (self.x1 <= other.x1 and self.y1 <= other.y1
                and self.x2 >= other.x2 and self.y2 >= other.y2)


class _RectUnion:
    """A disjoint set of rectangles: "is this rectangle entirely covered by
    the ones already added?"

    Adapted from browser-use (MIT, Copyright (c) 2024 Gregor Zunic)
    browser_use/dom/serializer/paint_order.py RectUnionPure - including its
    safety cap, past which contains() answers False (nothing hidden), which
    is the direction that fails safe here: an element wrongly thought
    visible is still re-checked by Playwright's own "is something covering
    it" test before any click."""
    _MAX_RECTS = 5000

    def __init__(self):
        self._rects: list = []

    @staticmethod
    def _split_diff(a: _Rect, b: _Rect) -> list:
        parts = []
        if a.y1 < b.y1:
            parts.append(_Rect(a.x1, a.y1, a.x2, b.y1))
        if b.y2 < a.y2:
            parts.append(_Rect(a.x1, b.y2, a.x2, a.y2))
        y_lo, y_hi = max(a.y1, b.y1), min(a.y2, b.y2)
        if a.x1 < b.x1:
            parts.append(_Rect(a.x1, y_lo, b.x1, y_hi))
        if b.x2 < a.x2:
            parts.append(_Rect(b.x2, y_lo, a.x2, y_hi))
        return parts

    def contains(self, r: _Rect) -> bool:
        if not self._rects:
            return False
        stack = [r]
        for s in self._rects:
            new_stack = []
            for piece in stack:
                if s.contains(piece):
                    continue
                if piece.intersects(s):
                    new_stack.extend(self._split_diff(piece, s))
                else:
                    new_stack.append(piece)
            if not new_stack:
                return True
            stack = new_stack
        return False

    def add(self, r: _Rect) -> bool:
        if len(self._rects) >= self._MAX_RECTS or self.contains(r):
            return False
        pending = [r]
        for s in self._rects:
            nxt = []
            for piece in pending:
                if piece.intersects(s):
                    nxt.extend(self._split_diff(piece, s))
                else:
                    nxt.append(piece)
            pending = nxt
        self._rects.extend(pending)
        return True


def _is_interactive(tag: str, attrs: dict, role: str, props: dict,
                    width: Optional[float], height: Optional[float],
                    cursor: str, chrome_clickable: bool,
                    has_form_control_descendant: Callable[[], bool]) -> bool:
    """Is this element something a person could click or type into?

    Adapted from browser-use (MIT, Copyright (c) 2024 Gregor Zunic)
    browser_use/dom/serializer/clickable_elements.py
    ClickableElementDetector.is_interactive - the same checks in the same
    order, over the data a CDP snapshot gives. Left out: its JS-listener
    detection (one extra CDP round trip per element); Chrome's own
    `isClickable` flag from the snapshot stands in for it."""
    tag = (tag or "").lower()
    if tag in ("html", "body"):
        return False
    if chrome_clickable:
        return True
    if tag in ("iframe", "frame") and (width or 0) > 100 and (height or 0) > 100:
        return True
    if tag == "label":
        if attrs.get("for"):
            return False
        if has_form_control_descendant():
            return True
    if tag == "span" and has_form_control_descendant():
        return True
    search_indicators = ("search", "magnify", "glass", "lookup", "find",
                         "query", "search-icon", "search-btn",
                         "search-button", "searchbox")
    classes = attrs.get("class", "").lower()
    if any(i in classes for i in search_indicators):
        return True
    if any(i in attrs.get("id", "").lower() for i in search_indicators):
        return True
    for k, v in attrs.items():
        if k.startswith("data-") and any(i in str(v).lower() for i in search_indicators):
            return True
    for name, value in props.items():
        if name == "disabled" and value:
            return False
        if name == "hidden" and value:
            return False
        if name in ("focusable", "editable", "settable") and value:
            return True
        if name in ("checked", "expanded", "pressed", "selected"):
            return True
        if name in ("required", "autocomplete") and value:
            return True
        if name == "keyshortcuts" and value:
            return True
    if tag in ("button", "input", "select", "textarea", "a", "details",
               "summary", "option", "optgroup"):
        return True
    if any(a in attrs for a in ("onclick", "onmousedown", "onmouseup",
                                "onkeydown", "onkeyup", "tabindex")):
        return True
    interactive_roles = {"button", "link", "menuitem", "option", "radio",
                         "checkbox", "tab", "textbox", "combobox", "slider",
                         "spinbutton", "search", "searchbox", "row", "cell",
                         "gridcell"}
    if attrs.get("role") in interactive_roles:
        return True
    if role in interactive_roles | {"listbox"}:
        return True
    if (width is not None and height is not None and 10 <= width <= 50
            and 10 <= height <= 50
            and any(a in attrs for a in ("class", "role", "onclick",
                                          "data-action", "aria-label"))):
        return True
    return cursor == "pointer"


def _elements_from_cdp(ax_nodes: list, snapshot: dict) -> tuple:
    """Turn one page's CDP accessibility tree and DOM snapshot into the
    compact records plan() and run() match against.

    `ax_nodes` is `Accessibility.getFullAXTree()["nodes"]`; `snapshot` is
    `DOMSnapshot.captureSnapshot()` asked for `_SNAPSHOT_STYLES`, with
    `includePaintOrder` and `includeDOMRects`. Only the main document is
    read - elements inside iframes are not (see backend/README.md).

    Returns (elements, omitted): elements in page order, each
        {"role", "name", "text", "enabled", "interactive", "sensitive",
         "password", "within_role", "within_name"}
    and how many were left out by the _MAX_ELEMENTS cap. An element is left
    out entirely (not just flagged) when it is not visible, or when
    something painted after it covers it completely - an element behind a
    modal overlay cannot be clicked by a person, so it is not offered as a
    target either."""
    docs = (snapshot or {}).get("documents") or []
    if not docs:
        return [], 0
    strings = snapshot.get("strings") or []
    doc = docs[0]
    nodes = doc.get("nodes") or {}
    layout = doc.get("layout") or {}

    def s(i) -> str:
        return strings[i] if isinstance(i, int) and 0 <= i < len(strings) else ""

    backend_ids = nodes.get("backendNodeId") or []
    parents = nodes.get("parentIndex") or []
    node_types = nodes.get("nodeType") or []
    node_names = nodes.get("nodeName") or []
    attr_lists = nodes.get("attributes") or []
    clickable = set((nodes.get("isClickable") or {}).get("index") or [])
    by_backend = {b: i for i, b in enumerate(backend_ids)}

    children: dict = {}
    for i, p in enumerate(parents):
        if p is not None and p >= 0:
            children.setdefault(p, []).append(i)

    lay_of: dict = {}
    for li, ni in enumerate(layout.get("nodeIndex") or []):
        lay_of.setdefault(ni, li)
    bounds = layout.get("bounds") or []
    styles = layout.get("styles") or []
    paints = layout.get("paintOrders") or []

    style_memo: dict = {}

    def style(i: int) -> dict:
        if i in style_memo:
            return style_memo[i]
        li = lay_of.get(i)
        out = ({} if li is None or li >= len(styles)
               else {k: s(v) for k, v in zip(_SNAPSHOT_STYLES, styles[li])})
        style_memo[i] = out
        return out

    def rect(i: int) -> Optional[_Rect]:
        li = lay_of.get(i)
        if li is None or li >= len(bounds) or len(bounds[li]) < 4:
            return None
        x, y, w, h = bounds[li][:4]
        return _Rect(x, y, x + w, y + h)

    def paint(i: int) -> Optional[int]:
        li = lay_of.get(i)
        return paints[li] if li is not None and li < len(paints) else None

    def attrs(i: int) -> dict:
        flat = attr_lists[i] if i < len(attr_lists) else []
        return {s(flat[k]).lower(): s(flat[k + 1]) for k in range(0, len(flat) - 1, 2)}

    def tag(i: int) -> str:
        return s(node_names[i]).lower() if i < len(node_names) else ""

    ancestor_memo: dict = {}

    def ancestors(i: int) -> frozenset:
        if i in ancestor_memo:
            return ancestor_memo[i]
        chain, j = [], parents[i] if i < len(parents) else -1
        while j is not None and j >= 0 and len(chain) < 512:
            chain.append(j)
            j = parents[j] if j < len(parents) else -1
        ancestor_memo[i] = frozenset(chain)
        return ancestor_memo[i]

    def visible(i: int) -> bool:
        """The idea of browser-use's is_element_visible_according_to_all_
        parents, for the main document: laid out, not display:none, not
        visibility:hidden, not fully transparent - itself or any
        ancestor (opacity is not inherited, so an opacity:0 wrapper hides
        a child whose own opacity still reads 1)."""
        if i not in lay_of:
            return False
        st = style(i)
        if st.get("display") == "none" or st.get("visibility") in ("hidden", "collapse"):
            return False
        for j in [i, *ancestors(i)]:
            try:
                if float(style(j).get("opacity") or 1) <= 0:
                    return False
            except ValueError:
                pass
        return rect(i) is not None

    def has_form_control_descendant(i: int, depth: int = 2) -> bool:
        if depth <= 0:
            return False
        for c in children.get(i, []):
            if c < len(node_types) and node_types[c] != 1:
                continue
            if tag(c) in ("input", "select", "textarea"):
                return True
            if has_form_control_descendant(c, depth - 1):
                return True
        return False

    # The viewport, as the snapshot measures it: the document node's own
    # layout box. Used for one rule browser-use does not have - see below.
    viewport = None
    for i in lay_of:
        if i < len(node_types) and node_types[i] == 9:   # the #document node
            viewport = rect(i)
            break

    # Things that could cover another element: laid-out elements with a
    # real background, mostly opaque. Same filter as browser-use's
    # PaintOrderRemover (transparent backgrounds and opacity < 0.8 do not
    # hide what is under them).
    #
    # Added here: a position:fixed layer that covers the whole viewport (a
    # modal's backdrop) stays over everything as the page scrolls, so it
    # covers elements far below the fold too - their document position is
    # outside its box, but a person could never reach them without closing
    # it first.
    everywhere = _Rect(float("-inf"), float("-inf"), float("inf"), float("inf"))
    occluders = []
    for i in lay_of:
        if i >= len(node_types) or node_types[i] != 1:
            continue
        st = style(i)
        if st.get("background-color", _TRANSPARENT) in ("", _TRANSPARENT):
            continue
        try:
            if float(st.get("opacity") or 1) < 0.8:
                continue
        except ValueError:
            continue
        if st.get("display") == "none" or st.get("visibility") in ("hidden", "collapse"):
            continue
        r, po = rect(i), paint(i)
        if r is None or po is None or r.x2 <= r.x1 or r.y2 <= r.y1:
            continue
        # Sizes, not positions: a scrolled page may report the fixed box at
        # its scroll offset. 20px of slack is a scrollbar's width.
        if (st.get("position") == "fixed" and viewport is not None
                and viewport.x2 > viewport.x1 and viewport.y2 > viewport.y1
                and (r.x2 - r.x1) >= (viewport.x2 - viewport.x1) - 20
                and (r.y2 - r.y1) >= (viewport.y2 - viewport.y1) - 20):
            r = everywhere
        occluders.append((i, r, po))
    occluders.sort(key=lambda o: -o[2])

    def covered(i: int) -> bool:
        """browser-use's paint-order idea, per element: is this element's
        box entirely covered by boxes painted AFTER it (a higher paint
        order)? Its own descendants and ancestors never count - a button's
        label does not hide the button."""
        r, po = rect(i), paint(i)
        if r is None or po is None:
            return False
        mine = ancestors(i)
        union = _RectUnion()
        for j, rj, pj in occluders:          # highest paint order first
            if pj <= po:
                break                         # nothing after this is on top
            if j == i or j in mine or i in ancestors(j):
                continue
            if rj.intersects(r) or (r.x1 == r.x2 or r.y1 == r.y2) and rj.contains(r):
                union.add(rj)
        return union.contains(r)

    # The accessibility tree, as parent links, so "within" can be found.
    ax_by_id = {n.get("nodeId"): n for n in ax_nodes or []}
    ax_parent: dict = {}
    for n in ax_nodes or []:
        for c in n.get("childIds") or []:
            ax_parent[c] = n.get("nodeId")

    def ax_value(n: dict, key: str):
        v = n.get(key)
        return v.get("value") if isinstance(v, dict) else None

    def props_of(n: dict) -> dict:
        out = {}
        for p in n.get("properties") or []:
            v = p.get("value")
            out[p.get("name")] = v.get("value") if isinstance(v, dict) else v
        return out

    def within_of(n: dict) -> tuple:
        pid, depth = ax_parent.get(n.get("nodeId")), 0
        while pid is not None and depth < _READ_DEPTH:
            p = ax_by_id.get(pid)
            if p is None:
                break
            if not p.get("ignored"):
                prole = str(ax_value(p, "role") or "")
                pname = _norm(ax_value(p, "name"))
                if prole in _CONTAINER_ROLES and pname:
                    return prole, pname
            pid, depth = ax_parent.get(pid), depth + 1
        return "", ""

    found = []
    for n in ax_nodes or []:
        if n.get("ignored"):
            continue
        role = str(ax_value(n, "role") or "")
        name = _norm(ax_value(n, "name"))
        if not role or not name or role != role.lower():
            continue
        bid = n.get("backendDOMNodeId")
        i = by_backend.get(bid)
        if i is None:
            continue
        t = tag(i)
        if t in ("option", "optgroup"):
            continue   # a native <select>'s options: `select` names them by label
        props = props_of(n)
        a = attrs(i)
        r = rect(i)
        interactive = _is_interactive(
            t, a, role, props,
            (r.x2 - r.x1) if r else None, (r.y2 - r.y1) if r else None,
            style(i).get("cursor", ""), i in clickable,
            lambda i=i: has_form_control_descendant(i))
        if role in _SKIP_ROLES and not interactive:
            continue
        if not visible(i) or covered(i):
            continue
        input_type = a.get("type", "").lower() if t == "input" else ""
        autocomplete = a.get("autocomplete", "").lower()
        sensitive = (input_type in ("password", "hidden", "file")
                     or autocomplete.startswith(("cc-", "one-time-code")))
        value = ax_value(n, "value")
        text = name if (sensitive or value in (None, "")) else str(value)
        within_role, within_name = within_of(n)
        found.append((i, {
            "role": _ROLE_TO_ARIA.get(role, role), "name": name,
            "text": text[:200],
            "enabled": not bool(props.get("disabled")),
            "interactive": bool(interactive),
            "sensitive": bool(sensitive),
            "password": input_type == "password",
            "within_role": within_role, "within_name": within_name,
        }))

    found.sort(key=lambda pair: pair[0])
    if len(found) <= _MAX_ELEMENTS:
        return [e for _, e in found], 0
    # Over the cap: interactive elements first (they are what steps target),
    # then containers and headings, each in page order; the count left out
    # is returned so the card can say so rather than dropping it silently.
    keep = [p for p in found if p[1]["interactive"]][:_MAX_ELEMENTS]
    room = _MAX_ELEMENTS - len(keep)
    if room > 0:
        keep += [p for p in found if not p[1]["interactive"]][:room]
    keep.sort(key=lambda pair: pair[0])
    return [e for _, e in keep], len(found) - len(keep)


# --------------------------------------------------------------------------
#   Page to clean text - pure, for read_page
# --------------------------------------------------------------------------

_TEXT_SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "canvas",
                   "iframe", "object", "embed", "head", "select", "option",
                   "datalist", "math"}
_TEXT_BLOCK_TAGS = {"p", "div", "section", "article", "main", "header",
                    "footer", "aside", "nav", "form", "fieldset", "table",
                    "ul", "ol", "dl", "blockquote", "pre", "figure",
                    "figcaption", "details", "summary", "dt", "dd",
                    "address", "legend", "caption", "tr", "li", "hr",
                    "h1", "h2", "h3", "h4", "h5", "h6", "body", "html"}


# Marks a nested list item's indentation until whitespace has been cleaned
# up - plain spaces would be collapsed away with everything else. A control
# character no page text contains.
_INDENT = "\x01"


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list = []
        self.skip = 0
        self.pre = 0
        self.lists: list = []     # stack of [ordered, counter]
        self.cells = 0

    def _newline(self):
        self.out.append("\n")

    def handle_starttag(self, tag, attrs):
        if tag in _TEXT_SKIP_TAGS:
            self.skip += 1
            return
        if self.skip:
            return
        a = dict(attrs)
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._newline()
            self.out.append("#" * int(tag[1]) + " ")
        elif tag in ("ul", "ol"):
            self.lists.append([tag == "ol", 0])
            self._newline()
        elif tag == "li":
            self._newline()
            depth = max(len(self.lists), 1)
            marker = "-"
            if self.lists and self.lists[-1][0]:
                self.lists[-1][1] += 1
                marker = f"{self.lists[-1][1]}."
            self.out.append(_INDENT * (depth - 1) + marker + " ")
        elif tag == "tr":
            self._newline()
            self.cells = 0
        elif tag in ("td", "th"):
            if self.cells:
                self.out.append(" | ")
            self.cells += 1
        elif tag == "br":
            self._newline()
        elif tag == "hr":
            self._newline()
            self.out.append("---")
            self._newline()
        elif tag == "pre":
            self.pre += 1
            self._newline()
        elif tag == "img":
            alt = _norm(a.get("alt"))
            if alt:
                self.out.append(f" {alt} ")
        elif tag in _TEXT_BLOCK_TAGS:
            self._newline()

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in _TEXT_SKIP_TAGS:
            self.skip = max(self.skip - 1, 0)

    def handle_endtag(self, tag):
        if tag in _TEXT_SKIP_TAGS:
            self.skip = max(self.skip - 1, 0)
            return
        if self.skip:
            return
        if tag in ("ul", "ol") and self.lists:
            self.lists.pop()
        if tag == "pre":
            self.pre = max(self.pre - 1, 0)
        if tag in _TEXT_BLOCK_TAGS or tag in ("td", "th"):
            if tag not in ("td", "th"):
                self._newline()

    def handle_data(self, data):
        if self.skip or not data:
            return
        if self.pre:
            self.out.append(data)
        else:
            self.out.append(re.sub(r"\s+", " ", data))


def _preprocess_markdown_content(content: str, max_newlines: int = 3) -> str:
    """Light clean-up of extracted text: drop SPA state blobs (big inline
    JSON), squeeze runs of blank lines, drop whitespace-only lines.

    Adapted from browser-use (MIT, Copyright (c) 2024 Gregor Zunic)
    browser_use/dom/markdown_extractor.py _preprocess_markdown_content."""
    content = re.sub(r'`\{["\w].*?\}`', "", content, flags=re.DOTALL)
    content = re.sub(r'\{"\$type":[^}]{100,}\}', "", content)
    content = re.sub(r'\{"[^"]{5,}":\{[^}]{100,}\}', "", content)
    content = re.sub(r"\n{4,}", "\n" * max_newlines, content)
    kept = []
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) > 100 and stripped[0] in "{[":
            try:
                json.loads(stripped)
                continue
            except ValueError:
                pass
        kept.append(line)
    return "\n".join(kept).strip()


def html_to_text(page_html: str) -> str:
    """The main content of a page, as compact markdown-ish text: headings
    as `#`, list items as `-`, table cells joined with ` | `, links and
    buttons as their plain text, images as their alt text. No URLs, no
    attributes, no scripts or styles, no form-field values - so a password
    typed into a field can never come back through this.

    The shape of browser-use's markdown_extractor (MIT, Copyright (c) 2024
    Gregor Zunic) - page HTML to markdown, then _preprocess_markdown_content
    - with a small standard-library converter in place of its `markdownify`
    dependency."""
    parser = _TextExtractor()
    try:
        parser.feed(page_html or "")
        parser.close()
    except Exception:
        pass
    raw = "".join(parser.out)
    lines = [re.sub(r"[ \t\u00a0]+", " ", ln).strip().replace(_INDENT, "  ")
             for ln in raw.split("\n")]
    return _preprocess_markdown_content("\n".join(lines))


# Runs in the page for read_page: the main content (a <main>, else an
# <article>, else the body minus nav/aside/footer), with everything the
# person cannot see removed, as HTML for html_to_text. Hidden-ness is taken
# from the live page's computed styles, since a detached copy has none.
_MAIN_CONTENT_JS = r"""
(maxChars) => {
  const root = document.querySelector('main, [role=main]')
            || document.querySelector('article') || document.body;
  if (!root) return '';
  const clone = root.cloneNode(true);
  const orig = [root, ...root.querySelectorAll('*')];
  const copy = [clone, ...clone.querySelectorAll('*')];
  const drop = [];
  for (let i = 0; i < orig.length && i < copy.length; i++) {
    const el = orig[i];
    let hidden = el.hidden || el.getAttribute('aria-hidden') === 'true';
    if (!hidden) {
      const cs = getComputedStyle(el);
      hidden = cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0';
    }
    if (hidden && i > 0) drop.push(copy[i]);
  }
  for (const el of drop) el.remove();
  if (root === document.body) {
    for (const el of clone.querySelectorAll('nav, aside, footer, [role=navigation], [role=contentinfo]')) el.remove();
  }
  const out = clone.outerHTML || '';
  return out.length > maxChars ? out.slice(0, maxChars) : out;
}
"""

# Runs in the page after a step: resolves once nothing in the DOM has
# changed for `quiet` ms, or after `max` ms whatever happens.
_DOM_QUIET_JS = r"""
([quiet, max]) => new Promise((resolve) => {
  let t = null, m = null;
  const obs = new MutationObserver(() => { clearTimeout(t); t = setTimeout(done, quiet); });
  function done() { obs.disconnect(); clearTimeout(t); clearTimeout(m); resolve(true); }
  obs.observe(document, {subtree: true, childList: true, attributes: true, characterData: true});
  t = setTimeout(done, quiet);
  m = setTimeout(done, max);
})
"""

_SENSITIVE_FIELD_JS = r"""
(el) => {
  const type = (el.getAttribute && (el.getAttribute('type') || '')).toLowerCase();
  const ac = (el.getAttribute && (el.getAttribute('autocomplete') || '')).toLowerCase();
  return ['password', 'hidden', 'file'].includes(type)
      || ac.startsWith('cc-') || ac.startsWith('one-time-code');
}
"""


# --------------------------------------------------------------------------
#   The real browser - lazily imported, one Chromium for the process
# --------------------------------------------------------------------------

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

# The one test-only override: test_browser_control_live.py flips this to run
# headless in a container with no display. Nothing in this project sets it,
# and the default stays a visible window.
_HEADLESS = False
# Extra Playwright launch options, for the same live test (pointing at a
# Chromium build that is not the one Playwright expects). Empty by default.
_LAUNCH_OPTIONS: dict = {}

# What the page did, per session, since the last read: dialogs, pop-ups,
# downloads, crashes, navigations. Filled by listeners (_wire_page), emptied
# by every read/observe. Bounded, so a page that fires thousands of events
# cannot grow it without limit.
_events: dict = {}
_MAX_QUEUED_EVENTS = 50
# session -> fence predicate (url -> allowed?), only while run() is running.
_fences: dict = {}
_guards: dict = {}


def _record(session: str, event: dict) -> None:
    q = _events.setdefault(session, [])
    if len(q) < _MAX_QUEUED_EVENTS:
        q.append(event)


def _drain(session: str) -> list:
    return _events.pop(session, [])


def _wire_page(session: str, page) -> None:
    """Listen for the things that must stop a run.

    The watchdog idea is browser-use's (browser_use/browser/watchdogs/
    popups_watchdog.py, downloads_watchdog.py, crash_watchdog.py); the
    answers are this project's:

      * A JavaScript dialog is closed the moment it opens, ALWAYS with
        dismiss() - never accept(). For an `alert` that is its only button.
        For `confirm`/`prompt`/`beforeunload` it is the Cancel answer, and
        the run then stops and reports the question. browser-use clicks OK
        on a confirm; that would be Jarvis approving something on the
        owner's behalf, which this project never does. Leaving the dialog
        open instead was tried and is not an option: with a listener
        attached, Playwright waits for it forever - the click that raised it
        times out, and even a fresh CDP read of the page hangs.
      * A download is cancelled (the browser context is also created with
        downloads refused) and reported.
      * A pop-up or new tab is reported; nothing drives it.
      * A crash or a closed tab is reported.
      * Every main-frame navigation is recorded, so run() can check each
        address the tab passed through against the fence, not only where it
        ended up."""

    def on_dialog(dialog):
        try:
            kind, message = dialog.type, dialog.message
        except Exception:
            kind, message = "dialog", ""
        try:
            dialog.dismiss()
        except Exception:
            pass
        _record(session, {"kind": "dialog", "type": str(kind),
                          "message": str(message)[:_MAX_EVENT_TEXT]})

    def on_download(download):
        try:
            url, filename = download.url, download.suggested_filename
        except Exception:
            url, filename = "", ""
        try:
            download.cancel()
        except Exception:
            pass
        _record(session, {"kind": "download", "url": str(url)[:_MAX_EVENT_TEXT],
                          "filename": str(filename)[:_MAX_EVENT_TEXT]})

    def on_popup(popup):
        try:
            url = popup.url
        except Exception:
            url = ""
        _record(session, {"kind": "popup", "url": str(url)[:_MAX_EVENT_TEXT]})
        try:
            popup.on("download", on_download)
            popup.on("dialog", on_dialog)
        except Exception:
            pass

    def on_nav(frame):
        try:
            if frame == page.main_frame:
                _record(session, {"kind": "navigation", "url": frame.url})
        except Exception:
            pass

    page.on("dialog", on_dialog)
    page.on("download", on_download)
    page.on("popup", on_popup)
    page.on("crash", lambda *_: _record(session, {"kind": "crash"}))
    page.on("close", lambda *_: _record(session, {"kind": "closed"}))
    page.on("framenavigated", on_nav)


def _make_guard(session: str):
    """A route handler that stops a top-level navigation outside the fence
    BEFORE it loads - browser-use's security_watchdog checks a URL before
    navigating too. It answers such a request with an empty 204, which
    leaves the tab on the page it was on (aborting it instead would strand
    the tab on Chrome's error page). Iframes are never blocked: a chat
    widget is very often an iframe from another domain.

    Two things it cannot catch, which is why run() ALSO checks every
    recorded navigation afterwards: a server-side redirect (Playwright does
    not route redirects) and a first request whose frame does not exist yet
    in a way the check below can see."""
    def guard(route, request):
        blocked = False
        try:
            allowed = _fences.get(session)
            if allowed is not None and request.is_navigation_request():
                try:
                    top = request.frame.parent_frame is None
                except Exception:
                    # A brand-new tab's first request has no frame yet. It
                    # is still a top-level document (a new iframe would say
                    # sec-fetch-dest: iframe).
                    dest = (request.headers or {}).get("sec-fetch-dest", "document")
                    top = dest == "document"
                blocked = top and not allowed(request.url)
        except Exception:
            blocked = False
        if blocked:
            _record(session, {"kind": "blocked_navigation",
                              "url": str(request.url)[:_MAX_EVENT_TEXT]})
            try:
                route.fulfill(status=204, body="")
                return
            except Exception:
                pass
        try:
            route.fallback()
        except Exception:
            pass
    return guard


def _arm_fence(session: str, allowed: Callable[[str], bool]) -> None:
    _fences[session] = allowed
    page = _sessions.get(session)
    if page is not None and session not in _guards:
        guard = _make_guard(session)
        try:
            page.context.route("**/*", guard)
            _guards[session] = guard
        except Exception:
            pass


def _disarm_fence(session: str) -> None:
    _fences.pop(session, None)
    guard = _guards.pop(session, None)
    page = _sessions.get(session)
    if guard is not None and page is not None:
        try:
            page.context.unroute("**/*", guard)
        except Exception:
            pass


def _page_for(session: str, *, create: bool):
    global _browser, _playwright
    if session in _sessions:
        return _sessions[session]
    if not create:
        return None
    if _browser is None:
        from playwright.sync_api import sync_playwright  # type: ignore
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(headless=_HEADLESS, **_LAUNCH_OPTIONS)
    # One browser context per session: its own cookies, and downloads
    # refused at the browser level, not only by our listener.
    context = _browser.new_context(accept_downloads=False)
    page = context.new_page()
    _wire_page(session, page)
    _sessions[session] = page
    if session in _fences:
        _arm_fence(session, _fences[session])
    return page


def close(session: Optional[str] = None) -> None:
    """Close one session's tab, or every open tab and the browser itself if
    `session` is omitted. Not called automatically by anything here - a
    caller that opens sessions is the one that knows when it is done with
    them."""
    global _browser, _playwright
    names = [session] if session is not None else list(_sessions)
    for name in names:
        page = _sessions.pop(name, None)
        _events.pop(name, None)
        _fences.pop(name, None)
        _guards.pop(name, None)
        if page is not None:
            try:
                page.context.close()
            except Exception:
                pass
    if session is not None:
        return
    if _browser is not None:
        _browser.close()
        _browser = None
    if _playwright is not None:
        _playwright.stop()
        _playwright = None


def _page_gone_events(page, exc: Exception) -> list:
    text = str(exc).lower()
    try:
        closed = page.is_closed()
    except Exception:
        closed = False
    if "crash" in text:
        return [{"kind": "crash"}]
    if closed or "closed" in text:
        return [{"kind": "closed"}]
    return []


def _probe(page) -> list:
    """A bounded liveness check: [] if the page answers, otherwise the
    event that explains why not (crashed, closed, or not responding)."""
    try:
        page.wait_for_function("() => true", timeout=_PROBE_MS)
        return []
    except Exception as exc:
        gone = _page_gone_events(page, exc)
        return gone or [{"kind": "unresponsive"}]


def _default_read(session: str) -> dict:
    """The real page read, through CDP (see _elements_from_cdp). Lazily
    imports Playwright so this module loads fine with nothing installed,
    and fails clearly - not with an ImportError three frames down - when
    nobody injected a `read`."""
    try:
        page = _page_for(session, create=False)
    except ImportError as exc:
        raise RuntimeError(
            "no page reader was given and 'playwright' is not installed - "
            "this only works with Playwright's Chromium present, or with a "
            "`read` function supplied for testing"
        ) from exc
    if page is None:
        return {"url": "", "title": "", "elements": [], "events": _drain(session)}
    # A CDP call to a crashed or frozen tab never returns (Playwright's
    # CDPSession.send has no timeout) - so first a bounded "are you alive"
    # round trip, which also delivers any events Playwright is holding.
    gone = _probe(page)
    if gone or any(ev.get("kind") in ("crash", "closed") for ev in _events.get(session, [])):
        return {"url": "", "title": "", "elements": [],
                "events": _drain(session) + gone}
    try:
        cdp = page.context.new_cdp_session(page)
        try:
            ax = cdp.send("Accessibility.getFullAXTree")
            snap = cdp.send("DOMSnapshot.captureSnapshot", {
                "computedStyles": _SNAPSHOT_STYLES,
                "includePaintOrder": True, "includeDOMRects": True})
        finally:
            try:
                cdp.detach()
            except Exception:
                pass
        url, title = page.url, page.title()
    except Exception as exc:
        gone = _page_gone_events(page, exc)
        if not gone:
            raise
        return {"url": "", "title": "", "elements": [],
                "events": _drain(session) + gone}
    elements, omitted = _elements_from_cdp(ax.get("nodes") or [], snap)
    return {"url": url, "title": title, "elements": elements,
            "omitted": omitted, "events": _drain(session)}


def _default_observe(session: str) -> dict:
    """The cheap look run() takes after every step: where the tab is and
    what it did - no element scan. The short wait also gives Playwright's
    synchronous API a moment to deliver events (a pop-up, a download) it is
    holding; a plain time.sleep would not."""
    page = _sessions.get(session)
    if page is None:
        return {"url": "", "events": _drain(session)}
    try:
        page.wait_for_timeout(50)
    except Exception:
        pass
    gone = _probe(page)
    if gone:
        return {"url": "", "events": _drain(session) + gone}
    return {"url": page.url, "events": _drain(session)}


def _settle(page, action: str) -> None:
    """Wait for the page to settle after a step, every wait bounded: the
    load event, then (after a click or navigation) a quiet network, then a
    quiet DOM. The pending-network idea is browser-use's
    (browser_use/browser/watchdogs/dom_watchdog.py); Playwright's own
    "networkidle" and a MutationObserver do the work here. A page that
    never settles - a chat widget animating a typing indicator - costs at
    most the timeouts, and then run() judges it on what is there."""
    try:
        page.wait_for_timeout(100)
    except Exception:
        return
    try:
        page.wait_for_load_state("load", timeout=_SETTLE_LOAD_MS)
    except Exception:
        pass
    if action in ("click", "navigate"):
        try:
            page.wait_for_load_state("networkidle", timeout=_SETTLE_NETWORK_MS)
        except Exception:
            pass
    for _ in range(2):   # once more if a navigation replaced the document mid-wait
        try:
            page.evaluate(_DOM_QUIET_JS, [_DOM_QUIET_MS, _DOM_QUIET_MAX_MS])
            return
        except Exception:
            try:
                page.wait_for_load_state("domcontentloaded", timeout=_SETTLE_LOAD_MS)
            except Exception:
                return


def _locate(page, step: "Step"):
    """The one element a step names - strictly. No `.first`: if the browser
    sees more than one match, Playwright's strict mode refuses to act, a
    second, independent check on plan()'s own uniqueness rule."""
    scope = page
    if step.within_role and step.within_name:
        scope = page.get_by_role(step.within_role, name=step.within_name, exact=True)
    locator = scope.get_by_role(step.role, name=step.name, exact=True)
    count = locator.count()
    if count != 1:
        where = (f' inside {step.within_role} "{step.within_name}"'
                 if step.within_name else "")
        raise RuntimeError(f'the browser finds {count} {step.role} elements named '
                           f'"{step.name}"{where}, not exactly one - not guessing')
    return locator


def _default_act(step: Step) -> Optional[str]:
    """Returns the read-back text for a "read"/"read_new"/"read_page" step,
    None for every other action - run() folds a non-None return into that
    step's own `value` before it is reported as done."""
    try:
        page = _page_for(step.session, create=True)
    except ImportError as exc:
        raise RuntimeError(
            "no `act` function was given and 'playwright' is not installed "
            "- see _default_read"
        ) from exc
    if step.action == "navigate":
        page.goto(step.value or "", wait_until="domcontentloaded", timeout=_NAV_TIMEOUT_MS)
        _settle(page, "navigate")
        return None
    if step.action == "read_page":
        page_html = page.evaluate(_MAIN_CONTENT_JS, _MAX_PAGE_HTML_CHARS)
        return _format_page_text(html_to_text(page_html or ""), int(step.value or 0))
    locator = _locate(page, step)
    if step.action == "click":
        locator.click(timeout=_ACT_TIMEOUT_MS)
        _settle(page, "click")
    elif step.action == "type":
        locator.fill(step.value or "", timeout=_ACT_TIMEOUT_MS)
        _settle(page, "type")
    elif step.action == "select":
        locator.select_option(label=step.value or "", timeout=_ACT_TIMEOUT_MS)
        _settle(page, "select")
    elif step.action == "read":
        try:
            sensitive = bool(locator.evaluate(_SENSITIVE_FIELD_JS, timeout=_ACT_TIMEOUT_MS))
        except Exception:
            sensitive = True    # cannot tell - do not read it back
        if sensitive:
            return "(not read back: this is a password, payment, or hidden field)"
        try:
            return locator.input_value(timeout=_ACT_TIMEOUT_MS)
        except Exception:
            return locator.inner_text(timeout=_ACT_TIMEOUT_MS)
    elif step.action == "read_new":
        # step.role/step.name name the CONTAINER (a chat log, a message
        # list) - its direct children are the individual messages, in the
        # order the page renders them. Reading text off children rather
        # than matching by (role, name) is deliberate: a message bubble
        # rarely has a distinct accessible name of its own, so the
        # (role, name) matching every other action uses would not find it.
        kids = locator.locator(":scope > *")
        count = kids.count()
        texts = [kids.nth(i).inner_text(timeout=_ACT_TIMEOUT_MS)
                 for i in range(min(count, _MAX_ELEMENTS))]
        return _format_new_messages(texts, int(step.value or 0))
    else:
        raise ValueError(f"unknown action {step.action!r}")
    return None


# --------------------------------------------------------------------------
#   plan() / describe()
# --------------------------------------------------------------------------

def _candidates(elements: list, role: str, name: str, within: str = "") -> list:
    out = [e for e in elements
           if e.get("role") == role and _norm(e.get("name")) == name]
    if within:
        out = [e for e in out if _norm(e.get("within_name")) == within]
    return out


def _event_text(ev: dict) -> str:
    """One plain sentence for something the page did."""
    kind = ev.get("kind")
    if kind == "dialog":
        if ev.get("type") == "alert":
            return (f'the page showed a message: "{ev.get("message", "")}" - '
                    "Jarvis closed it with its only button, OK")
        return (f'the page asked a {ev.get("type")} question: "{ev.get("message", "")}" - '
                "Jarvis answered Cancel (it never answers yes)")
    if kind == "popup":
        return f"the page opened a new tab or pop-up (at {ev.get('url') or 'an unknown address'})"
    if kind == "download":
        return (f'the page tried to download a file ("{ev.get("filename", "")}" from '
                f"{ev.get('url', '')}) - downloads are blocked; nothing was saved")
    if kind == "crash":
        return "the browser tab crashed"
    if kind == "closed":
        return "the browser tab was closed"
    if kind == "unresponsive":
        return "the page stopped responding"
    if kind == "blocked_navigation":
        return (f"the page tried to go to {ev.get('url')}, outside the allowed sites - "
                "Jarvis blocked it before it loaded")
    if kind == "navigation":
        return f"the page went to {ev.get('url')}"
    return f"the page did something unexpected ({kind})"


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
        {"role": "textbox", "name": "Password", "action": "type",
         "value": "<secret>shop_password</secret>", "why": "log in"}
        {"role": "button", "name": "Reply", "within": "Order 2",
         "action": "click", "why": "...", "leaves_machine": True}
        {"role": "log", "name": "Conversation", "action": "read_new",
         "value": "12", "why": "check for a reply"}
        {"action": "read_page", "value": "0", "why": "see what the page says"}

    Each element request must match EXACTLY ONE visible element. Two
    elements with the same role and name are not resolved by picking the
    first - the request is reported unmatched as ambiguous, naming the
    containers they sit in, and the caller can add `"within": "<container
    name>"` to say which. That is safer than binding "the second Send
    button" by position: a position can silently point at a different
    element after the page re-renders, and a card saying `click button
    "Send"` would not tell the owner which one was meant. With `within`,
    the card says it, and run() re-checks it.

    `read_new`'s `role`/`name` name a CONTAINER (a chat log, a message
    list), not one message - see `_format_new_messages`. `value` is the
    index already seen. `read_page` names no element: it reads the page's
    main text, `_MAX_PAGE_TEXT_CHARS` at a time from the offset in `value`.

    A `type` step's value may contain `<secret>name</secret>`: the real
    value is looked up only inside run(), at the moment of typing, and
    never appears in the plan, the card, or the result. A password field
    only accepts such a placeholder - a literal password in a request would
    already have passed through the model and would be printed on the card.

    A `navigate` request is checked against `_ALLOWED_SCHEMES` and
    `allowed_domains`, never against the current page - there may not be one
    yet. Every other request is checked against the CURRENT page right now;
    an element that is not there, not unique, not enabled, or not something
    that can be clicked or typed into is not guessed at - it is reported in
    `unmatched` and simply does not become a step.
    """
    getter = read or _default_read
    current = getter(session) or {"url": "", "title": "", "elements": []}
    elements = current.get("elements") or []
    url = str(current.get("url") or "")
    notices = [_event_text(ev) for ev in (current.get("events") or [])
               if ev.get("kind") != "navigation"]
    omitted = int(current.get("omitted") or 0)
    if omitted:
        notices.append(f"this page has {omitted} more element(s) than Jarvis reads at once "
                       f"(the limit is {_MAX_ELEMENTS}); those cannot be steps")
    steps, unmatched = [], []
    for r in requests:
        action = str(r.get("action", "")).strip()
        heavy = bool(r.get(IRREVERSIBLE_HINT)) or bool(r.get(LEAVES_MACHINE_HINT))
        value = r.get("value")
        secret_names = _secret_names(value)
        if action not in _ACTIONS:
            unmatched.append({**r, "reason": f"unknown action {action!r}"})
            continue
        if isinstance(value, str) and "<secret>" in value and action != "type":
            unmatched.append({**r, "reason": "a <secret> placeholder can only be typed "
                                              "(a type step), never sent any other way"})
            continue
        if isinstance(value, str) and value.count("<secret>") != len(secret_names):
            unmatched.append({**r, "value": "(withheld)",
                              "reason": "a <secret> placeholder is malformed - it must be "
                                        "<secret>name</secret> with a plain name"})
            continue
        if action == "navigate":
            target = str(value or "")
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
        if action == "read_page":
            try:
                offset = max(int(value or 0), 0)
            except (TypeError, ValueError):
                unmatched.append({**r, "reason": "value must be a character offset (a number)"})
                continue
            steps.append(Step(session=session, url=url, role="", name="",
                               action="read_page", value=str(offset),
                               why=str(r.get("why", "")), heavy=heavy))
            continue
        role = str(r.get("role", "")).strip()
        name = _norm(r.get("name", ""))
        within = _norm(r.get("within", ""))
        found = _candidates(elements, role, name, within)
        if not found:
            unmatched.append({**r, "reason": "not found" if not within
                               else f"not found inside {within!r}"})
            continue
        if len(found) > 1:
            places = sorted({_norm(e.get("within_name")) for e in found} - {""})
            if len(places) > 1 and not within:
                hint = (" - they are inside " + ", ".join(repr(p) for p in places[:5])
                        + '; add "within" with one of those names to say which')
            else:
                hint = " and nothing on the page tells them apart"
            unmatched.append({**r, "reason": f"ambiguous: {len(found)} elements match "
                                              f"{role} {name!r}{hint} - not guessing"})
            continue
        e = found[0]
        if not e.get("enabled", True):
            unmatched.append({**r, "reason": "found but disabled"})
            continue
        if action in _INPUT_ACTIONS and e.get("interactive", True) is False:
            unmatched.append({**r, "reason": "found, but it is not something that "
                                              "can be clicked or typed into"})
            continue
        if action == "read" and e.get("sensitive"):
            unmatched.append({**r, "reason": "a password, payment, or hidden field - "
                                              "its contents are never read back"})
            continue
        if action == "type" and e.get("password") and not secret_names:
            unmatched.append({**r, "value": "(withheld)",
                              "reason": "a password field only takes a <secret>name</secret> "
                                        "placeholder, so the real value never passes through "
                                        "the model or this card"})
            continue
        if action == "type" and secret_names:
            heavy = True
        steps.append(Step(
            session=session, url=url, role=role, name=name, action=action,
            value=value, why=str(r.get("why", "")), heavy=heavy,
            within_role=str(e.get("within_role", "")) if within else "",
            within_name=within))
    return Plan(
        goal=str(goal), session=str(session), steps=steps, unmatched=unmatched,
        if_refused="nothing on this page changes; the goal is not attempted",
        allowed_domains=list(allowed_domains) if allowed_domains else None,
        notices=notices)


def _plan_hosts(p: Plan) -> list:
    hosts = []
    for s in p.steps:
        for u in (s.url, s.value if s.action == "navigate" else ""):
            h = (urlparse(u or "").hostname or "").lower()
            if h and h not in hosts:
                hosts.append(h)
    return hosts


# The weight the CARD prints is the heavier of two: the steps the model
# flagged, and the gate's own risk table - which classifies this whole
# action as one that cannot be undone and leaves the machine (by its worst
# case: every browser step either sends something or lands on an unread
# page). The card used to print only the model's flags, so a plan whose Send
# click the model left unflagged read "weight: normal" while the notice and
# the risk line said the opposite. `Plan.weight` stays the model's own
# marking; this is what a person is shown.
CARD_WEIGHT_LINE = (
    "weight: heavy - any step in a web page can send something or be impossible to undo, "
    "so the whole plan is treated that way. The steps marked below are the "
    "ones Jarvis flagged itself; an unmarked step is not a promise that it "
    "is safe.")


def describe(p: Plan) -> str:
    """The card text. Every step in full, in the order it would run."""
    lines = [f'Jarvis would like to do this in the browser session "{p.session}": {p.goal}',
             "", f"{len(p.steps)} step(s), {CARD_WEIGHT_LINE}"]
    if p.steps:
        if p.allowed_domains:
            lines.append("Allowed sites: " + ", ".join(p.allowed_domains)
                         + " - if the page goes anywhere else, it stops.")
        else:
            hosts = _plan_hosts(p)
            lines.append("Allowed sites: only the ones this plan names ("
                         + (", ".join(hosts) or "none") + ") - if the page goes "
                         "anywhere else, it stops.")
    lines.append("")
    if not p.steps:
        lines.append("No requested step could be matched, so nothing would happen.")
    uses_secret = False
    for i, s in enumerate(p.steps, 1):
        heavy_note = "  [Jarvis flagged: sends something to the other end]" if s.heavy else ""
        inside = (f' (inside {s.within_role or "container"} "{s.within_name}")'
                  if s.within_name else "")
        if s.action == "navigate":
            lines += [f"  {i}. navigate to {s.value!r}{heavy_note}", f"     why: {s.why}", ""]
        elif s.action == "read_new":
            lines += [f'  {i}. read new messages in {s.role} "{s.name}"{inside} '
                      f'since #{s.value or 0}{heavy_note}',
                      f"     why: {s.why}", ""]
        elif s.action == "read_page":
            lines += [f"  {i}. read the page's text from character #{s.value or 0}"
                      f"{heavy_note}", f"     why: {s.why}", ""]
        else:
            detail = f" = {s.value!r}" if s.value is not None else ""
            lines += [f'  {i}. {s.action} {s.role} "{s.name}"{inside}{detail}{heavy_note}',
                      f"     why: {s.why}"]
            if _secret_names(s.value):
                uses_secret = True
                lines.append("     (the <secret> part is filled in from your saved secrets "
                             "at the moment of typing - its real value is never shown here, "
                             "logged, or given to the model)")
            lines.append("")
    if p.unmatched:
        lines.append(f"{len(p.unmatched)} requested step(s) could NOT be "
                      "matched and will NOT run:")
        for u in p.unmatched:
            if u.get("action") == "navigate":
                label = u.get("value")
            else:
                label = u.get("name") or u.get("action")
            lines.append(f"  - {label!r}: {u.get('reason')}")
        lines.append("")
    if p.notices:
        lines.append("While reading the page:")
        lines += [f"  - {n}" for n in p.notices]
        lines.append("")
    if uses_secret:
        lines.append("A secret is only typed if the page is on an allowed site at that moment.")
    lines.append(f"If you say no: {p.if_refused}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   Execution - only the enumerated steps, re-verified just before each one
# --------------------------------------------------------------------------

def _fence_for(p: Plan) -> Callable[[str], bool]:
    """The run-time fence: `allowed_domains` if the plan has it, otherwise
    the sites the plan itself names. `about:blank` (a fresh tab) is always
    fine; any other non-http(s) address - `chrome-error://`, `file:`,
    `data:` - is outside it."""
    domains = p.allowed_domains or _plan_hosts(p)

    def allowed(url: str) -> bool:
        if not url or url == "about:blank":
            return True
        if urlparse(url).scheme.lower() not in _ALLOWED_SCHEMES:
            return False
        return _host_matches(url, domains) if domains else False
    return allowed


def _without_fragment(url: str) -> str:
    try:
        return urlunparse(urlparse(url)._replace(fragment=""))
    except Exception:
        return url


def _page_problem(look: dict, allowed: Callable[[str], bool],
                  expected_url: str, notes: list) -> Optional[str]:
    """What, if anything, about this look at the page means the run must
    stop. An `alert` is noted and is not a reason to stop - it has no
    choice to make. Everything else the page did on its own is."""
    for ev in look.get("events") or []:
        kind = ev.get("kind")
        if kind == "dialog" and ev.get("type") == "alert":
            notes.append(_event_text(ev))
            continue
        if kind == "navigation":
            if not allowed(str(ev.get("url") or "")):
                return f"the page went to {ev.get('url')}, which is outside the allowed sites"
            continue
        return _event_text(ev)
    url = str(look.get("url") or "")
    if url:
        if not allowed(url):
            return f"the page is now at {url}, which is outside the allowed sites"
        if expected_url and _without_fragment(url) != _without_fragment(expected_url):
            return f"the page address changed from {expected_url} to {url}"
    return None


def run(p: Plan, *, read: Optional[Callable[[str], dict]] = None,
        act: Optional[Callable[[Step], Optional[str]]] = None,
        announce: Optional[Callable[[str], None]] = None,
        checkpoint: Optional[Callable[[], Optional[str]]] = None,
        observe: Optional[Callable[[str], dict]] = None,
        secrets: Optional[Callable[[str, str], Optional[str]]] = None,
        approved: bool = False) -> dict:
    """Execute an approved plan, one step at a time.

    `approved` has no default of True, same reason as jarvis_ui_control.py: a
    module that can act on the world must not be one call away from doing it
    by accident.

    Before every step except `navigate` (which has no prior element to
    re-check), the live page is re-read: it must still be on an allowed site,
    at the address the previous step left it on (a page that moved on its
    own in between is a stop), and the target must still exist, be the only
    match, and be enabled. After every step, run() looks again: a dialog
    that asked a question, a pop-up, a download, a crash, or any navigation
    outside the fence stops the run there. Steps already done are reported
    as done; everything after the stop is reported as not run. That is a new
    plan() and a new decision.

    `observe(session)`, if given, is that after-step look - `{"url",
    "events"}`, no elements. Omitted, an injected `read` is used for it;
    with neither injected, the real browser's.

    `secrets(name, host)` looks up a `<secret>name</secret>` value at the
    moment a `type` step runs, for the host the page is on right then. There
    is no default store in this project yet, so with nothing injected a step
    that needs a secret stops the run (fails closed) and types nothing. The
    real value goes only to `act`; it is redacted back out of every reason,
    read-back and note this function returns, and nothing here logs it.

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
    looker = observe or read or _default_observe
    allowed = _fence_for(p)
    real_browser = act is None
    sessions = sorted({s.session for s in p.steps})
    if real_browser:
        for name in sessions:
            _arm_fence(name, allowed)
    try:
        return _run_steps(p, getter, actor, looker, allowed, announce, checkpoint, secrets)
    finally:
        if real_browser:
            for name in sessions:
                _disarm_fence(name)


def _run_steps(p, getter, actor, looker, allowed, announce, checkpoint, secrets) -> dict:
    tell = announce or (lambda _text: None)
    check = checkpoint or (lambda: None)
    used: dict = {}        # secret name -> value, for redaction only
    notes: list = []
    done: list = []
    expected_url: Optional[str] = None

    def stopped(reason: str, first_not_run: int, **extra) -> dict:
        out = {"ok": False, "reason": _redact(reason, used),
               "done": [s.as_dict() for s in done],
               "not_run": [s.as_dict() for s in p.steps[first_not_run:]]}
        if notes:
            out["notes"] = [_redact(n, used) for n in notes]
        out.update(extra)
        return out

    for i, step in enumerate(p.steps, 1):
        # The checkpoint comes FIRST, before the announcement. It used to
        # come second, and `announce` is wired to a sticky
        # `jarvis_events.set_activity("working", text)` - so a pause left
        # the Brain window claiming a step that never ran, and kept saying
        # it.
        signal = check()
        if signal in ("stop", "pause"):
            extra = {"paused": True} if signal == "pause" else {}
            return stopped("stopped by request" if signal == "stop"
                           else "paused by request - resuming needs a new decision",
                           i - 1, **extra)
        if step.action == "navigate":
            label = step.value
        elif step.action == "read_page":
            label = "read the page's text"
        else:
            label = f'{step.action} "{step.name}"'
        tell(f"Step {i}/{len(p.steps)}: {label} in session {step.session}")

        current: dict = {}
        if step.action != "navigate":
            try:
                current = (looker if step.action == "read_page" else getter)(step.session) or {}
            except Exception as exc:
                return stopped(f"before step {i} ({label}): the page could not be read "
                               f"({type(exc).__name__}: {exc}) - stopping", i - 1)
            problem = _page_problem(current, allowed,
                                    expected_url if expected_url is not None else step.url,
                                    notes)
            if problem:
                return stopped(f"before step {i} ({label}): {problem} - stopping rather "
                               "than acting on a page that is not the one planned", i - 1)
            if step.action != "read_page":
                found = _candidates(current.get("elements") or [], step.role,
                                    _norm(step.name), _norm(step.within_name))
                if len(found) != 1 or not found[0].get("enabled", True):
                    extra = (f" (it now matches {len(found)} elements)"
                             if len(found) > 1 else "")
                    return stopped(f'step {i} ("{step.name}" in session '
                                   f"{step.session}) no longer matches what "
                                   f"was planned{extra} - stopping rather than guessing",
                                   i - 1)

        to_act = step
        names = _secret_names(step.value) if step.action == "type" else []
        if names:
            if secrets is None:
                return stopped(f"step {i} ({label}) types a saved secret, but no secret "
                               "store was given to this run - nothing was typed", i - 1)
            host = (urlparse(str(current.get("url") or "")).hostname or "").lower()
            real = step.value
            for secret_name in names:
                try:
                    secret_value = secrets(secret_name, host)
                except Exception as exc:
                    return stopped(f"step {i} ({label}): looking up secret {secret_name!r} "
                                   f"failed ({type(exc).__name__}) - nothing was typed", i - 1)
                if not secret_value:
                    return stopped(f"step {i} ({label}): secret {secret_name!r} is not "
                                   f"available for {host or 'this page'} - nothing was typed",
                                   i - 1)
                used[secret_name] = str(secret_value)
                real = real.replace(f"<secret>{secret_name}</secret>", str(secret_value))
            to_act = replace(step, value=real)

        try:
            read_back = actor(to_act)
        except Exception as exc:
            return stopped(f"step {i} failed: {type(exc).__name__}: {exc}", i - 1)
        finally:
            to_act = None   # the only object holding a real secret; not kept

        if step.action == "read" and read_back is not None:
            step.value = _redact(str(read_back)[:_MAX_READ_VALUE_CHARS], used)
        elif step.action in ("read_new", "read_page") and read_back is not None:
            # Already capped and, if truncated, already says so - by
            # _format_new_messages/_format_page_text (real path) or by the
            # injected `act` in a test. Re-slicing here would risk cutting
            # the "N more not shown" trailer off silently, which is the
            # exact failure these actions exist to avoid.
            step.value = _redact(str(read_back), used)
        done.append(step)

        try:
            after = looker(step.session) or {}
        except Exception as exc:
            return stopped(f"step {i} ({label}) ran, but the page could not be checked "
                           f"afterwards ({type(exc).__name__}: {exc}) - stopping", i)
        problem = _page_problem(after, allowed, "", notes)
        if problem:
            return stopped(f"after step {i} ({label}): {problem} - stopping", i)
        if after.get("url"):
            expected_url = str(after["url"])

    # One last read, so a Stop that arrived while the final step was running
    # is not thrown away. Every step ran, so `ok` stays True - but the owner
    # pressed Stop and is told it was seen and was too late. The read also
    # SPENDS the signal (jarvis_task_control.checkpoint), which is what keeps
    # a stop that missed its run from stopping the next one instead.
    late = check()
    out = {"ok": True, "done": [s.as_dict() for s in done], "not_run": []}
    if notes:
        out["notes"] = [_redact(n, used) for n in notes]
    if late in ("stop", "pause"):
        out["late_signal"] = late
        out["note"] = (f"a {late} arrived after the last step had already run - "
                       "the plan finished, and nothing was left undone")
        tell(f"Done. (A {late} arrived too late to change anything.)")
    else:
        tell("Done.")
    return out
