"""jarvis_auto_router.py - estimate what a turn will COST on this PC, and ADVISE.

THIS MODULE ESTIMATES AND ADVISES. IT DOES NOT DECIDE, AND IT MUST NEVER DECIDE.

The one authority on which lane answers a turn - `local`, or a cloud lane such
as `jarvis-escalate` - is `jarvis_router.choose()`
(`backend/rebuilt/jarvis_router.py:590`, delivered to the owner's PC as
`rebuilt/jarvis_router.py`). Its nine gates run in a fixed order, and every one
of them can only move the answer DOWNWARD, toward local - its own docstring
says so at `jarvis_router.py:596-600` ("the order is the policy ... none of
them can escalate past a gate that already refused"). Nothing in this file may
move an answer back up.

So `evaluate_route()` is a second opinion about COST, never a second
permission. It answers one question: "would this turn make the owner wait a
long time on this machine, and would suggesting the cloud be lawful at this
moment?" It SENDS NOTHING, WRITES NOTHING, APPROVES NOTHING, LOGS NOTHING AND
REACHES NO NETWORK. It returns a plain dict whose `lane` is either

  * `"local"` - keep it here; `gate` and `reason` name the rule that said so; or
  * `"jarvis-escalate"` / `"jarvis-critic"` - a SUGGESTION, carrying
    `advisory: True`, reached ONLY when all four gates below pass AND the
    shipped `choose()` would also allow a cloud turn for this text.

THAT LAST CLAUSE IS ENFORCED BY DELEGATION, NOT BY COPYING. `_router_allows()`
calls the real `jarvis_router.choose()` with `owner_said_yes=True` - "if the
owner were to say yes to this one question, would the shipped authority allow
it at all?" - and whichever gate it refuses on becomes this module's answer
too. That is what makes a second entry point safe: it is STRICTLY WEAKER than
the first, so it can never open a gate `choose()` keeps shut. A parallel gate
stack here would be exactly the failure `jarvis_router.py:632-648` was written
about - a privacy decision with two sources of truth, and therefore a gate
nobody can see.

WHY IT EXISTS AT ALL. `choose()` decides from the SHAPE of the question (its
own 0-1 `complexity()` at `jarvis_router.py:504`, threshold `[routing]
complexity_threshold = 0.40`). It cannot tell the owner "this will take about
forty seconds here", because it holds no measurement. `jarvis_speed.py` holds
the measurement: the median tokens per second of the answers this PC really
gave, per model. This module turns that number, the size of the conversation
and the kind of work into seconds, so an app could offer the cloud before the
owner sits through the wait - and so the answer is still "no" unless four
separate things permit it.

WHAT IT DELIBERATELY IS NOT. It is not wired into any turn. It serves no route
of its own: `plugins/ready/auto-router/plugin.json` sets `install: "none"`, so
the loader imports this module and calls `install()` with no arguments, and
nothing about a live turn changes. That is on purpose - nothing new is
reachable, no new permission surface exists, and this module cannot be hooked
into a chat turn by accident. Adding a caller is a separate change with its
own review.

THE FOUR GATES, each proved able to fail in `backend/test_auto_router.py`.
They are inputs to the ADVICE; `choose()` remains the decision.

  1. mode/switch - OFF by default. On only when a caller enables it explicitly,
     or inside an active Project Mode workspace whose `auto_route_cloud` is
     true. A missing, unreadable or corrupt switch file reads as OFF.
  2. taint latch - a HARD BLOCK returning
     `reason="taint_latched_local_only"`. It reads the ONE latch that exists
     (`jarvis_gate.taint_active()`), plus a project whose `shareable` flag is
     not on. It cannot read the latch -> it blocks. See `taint_latched()`'s own
     note for the honest limitation: this project has ONE global latch, not one
     per topic.
  3. budget - the on-disk cloud budget (`jarvis_router.Budget`) AND the monthly
     money cap (`jarvis_chatbot_api.money_check()`). A cap that is exhausted OR
     unconfigured is a "no". Neither module readable -> a "no".
  4. scrubber - the outbound text must pass `jarvis_scrub.scrub_text()`, and the
     absence of the scrubber is itself a refusal. A recommendation always
     carries the exact `would_send` text the scrubber produced, so a caller can
     never send something this module did not scrub.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

# --------------------------------------------------------------------------
#   Names, thresholds and weights
# --------------------------------------------------------------------------

#: The two cloud lanes this module may SUGGEST. `jarvis-escalate` is the cheap
#: current model for an ordinary hard question; `jarvis-critic` is the stronger
#: one, whose own job in `jarvis_chatbot_api.CLOUD_LANES` is to check an answer
#: (jarvis_chatbot_api.py:1906-1908) - so it is what a review task is offered.
LANE_ESCALATE = "jarvis-escalate"
LANE_CRITIC = "jarvis-critic"

#: `local` is the only other answer this module ever gives.
LOCAL_LANE = "local"

#: A local turn predicted to run longer than this is worth mentioning.
SECONDS_THRESHOLD = 25.0

#: This module's own complexity score at which a turn is "hard enough".
COMPLEXITY_THRESHOLD = 0.75

#: A conversation this large counts toward complexity on its own.
CONTEXT_TOKENS_HEAVY = 3500

#: Tokens per second assumed when this PC has no measurement at all. A number,
#: not a measurement, and `measured_rate()` says which it used.
DEFAULT_TOKENS_PER_S = 25.0

#: Rough characters per token. Used only to size the typed prompt.
CHARS_PER_TOKEN = 4.0

#: Tokens expected in the ANSWER, which is the part the owner waits for.
ANSWER_TOKENS = 400
REVIEW_ANSWER_TOKENS = 900

#: The switch file, beside the framework config on a real install. Absent by
#: default, and anything unreadable or corrupt reads as OFF.
SWITCH_NAME = "auto-route.json"

#: Complexity weights. They add to 1.0, so a maximally complex turn scores 1.0
#: and `COMPLEXITY_THRESHOLD` can be reached by more than one honest route.
W_MULTI_FILE = 0.15
W_ARCHITECTURE = 0.15
W_INDICATORS_CAP = 0.45
W_HEAVY_CONTEXT = 0.25
W_PRIOR_BAD_TURN = 0.30

#: Words that mean the question spans more than one file, or is about design
#: rather than about one answer. Deliberately narrow: a false positive here
#: only makes the module suggest help sooner, and the four gates still decide.
_MULTI_FILE = re.compile(
    r"\b(?:multi[-\s]?file|several files|many files|all the files|across files|"
    r"every file|each (?:file|module)|all modules|the whole (?:repo|repository|"
    r"codebase|project)|refactor\w*|rename (?:it |them )?across|sweep|"
    r"throughout the (?:repo|codebase|project))\b",
    re.I,
)
_ARCHITECTURE = re.compile(
    r"\b(?:architect\w*|design (?:a|the) (?:system|schema|api|pipeline|database)|"
    r"migrat\w*|schema|database (?:schema|migration)|concurren\w*|race condition|"
    r"deadlock|dependency graph|trade[-\s]?offs?|end[-\s]to[-\s]end|protocol|"
    r"distributed|backward compat\w*|scal\w*)\b",
    re.I,
)

#: Words that ask for a REVIEW of something, which is `jarvis-critic`'s job
#: rather than `jarvis-escalate`'s.
_REVIEW = re.compile(
    r"\b(?:re-?view|critique|critic\w*|audit|proof[-\s]?read|second opinion|"
    r"pull (?:this|it|that) apart|find (?:the )?(?:bugs|problems|faults|flaws)|"
    r"what(?:'s| is) wrong with|check (?:this|my|the) "
    r"(?:code|answer|plan|work|design))\b",
    re.I,
)


# --------------------------------------------------------------------------
#   The optional modules, each resolved lazily and never at import time
# --------------------------------------------------------------------------
#
# Each of these is a separate module the owner's PC may or may not have. They
# are resolved on every call rather than at import time for two reasons: this
# module must import cleanly in a clone that holds none of them, and a suite
# must be able to stand one in by name. A missing module is never an exception
# out of `evaluate_route` - it is a refusal, which is the safe direction.

def _router_module():
    """`jarvis_router` - the decision authority. None when it is not here."""
    try:
        import jarvis_router
        return jarvis_router
    except Exception:
        return None


def _gate_module():
    """`jarvis_gate` - the taint latch and the approval model."""
    try:
        import jarvis_gate
        return jarvis_gate
    except Exception:
        return None


def _scrub_module():
    """`jarvis_scrub` - what makes outbound text safe to look at."""
    try:
        import jarvis_scrub
        return jarvis_scrub
    except Exception:
        return None


def _money_module():
    """`jarvis_chatbot_api` - the monthly money cap per service."""
    try:
        import jarvis_chatbot_api
        return jarvis_chatbot_api
    except Exception:
        return None


def _work_module():
    """`jarvis_work` - which work setup the owner's own words ask for."""
    try:
        import jarvis_work
        return jarvis_work
    except Exception:
        return None


def _speed_module():
    """`jarvis_speed` - the measured speed of the answers this PC gave."""
    try:
        import jarvis_speed
        return jarvis_speed
    except Exception:
        return None


# --------------------------------------------------------------------------
#   Small, total helpers. Nothing here raises.
# --------------------------------------------------------------------------

def _number(value) -> Optional[float]:
    """A finite number, or None. A bool is not a number here, and neither is
    a string that merely looks like one - `context_tokens=True` is a caller
    bug, not one token."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _tokens(text) -> float:
    """A rough token count for typed text. Only ever sizes the wait."""
    if not isinstance(text, str) or not text:
        return 0.0
    return len(text) / CHARS_PER_TOKEN


def _positive(value) -> Optional[float]:
    n = _number(value)
    if n is None or n <= 0:
        return None
    return n


# --------------------------------------------------------------------------
#   Gate 1 - the mode switch. OFF unless something turns it on.
# --------------------------------------------------------------------------

def switch_path() -> Path:
    """Where the mode switch lives. Beside the framework config when that is
    readable, and under the user's home otherwise - never created by this
    module, which writes nothing."""
    try:
        import jarvis_framework as fw
        base = Path(fw.CONFIG_DIR)
    except Exception:
        base = Path.home() / ".openjarvis"
    return base / SWITCH_NAME


def switch_state() -> tuple:
    """(is the mode switched on, why) from the switch file alone.

    OFF for a missing file, an unreadable one, a corrupt one, one that is not
    an object, or one whose `enabled` is not exactly `true`. Every one of those
    is the same answer, and it is the safe one: a switch nobody can read has
    not been turned on by anybody.
    """
    try:
        raw = json.loads(switch_path().read_text(encoding="utf-8"))
    except Exception:
        return False, "off in general chat"
    if isinstance(raw, dict) and raw.get("enabled") is True:
        return True, "switched on in settings"
    return False, "off in general chat"


def mode_on(active_project=None, enabled=None) -> tuple:
    """(may this module suggest anything at all, why).

    `enabled=True` / `False` is the caller's own explicit answer for this call.
    Otherwise the switch file is read, and a Project Mode workspace whose
    `auto_route_cloud` is exactly `true` also turns it on. A truthy-but-not-
    True value (`1`, `"yes"`, `[]` is false...) does NOT - the same rule the
    rest of this project applies to a flag that lets more leave the PC.
    """
    if enabled is True:
        return True, "enabled for this call"
    if enabled is False:
        return False, "off in general chat"
    on, why = switch_state()
    if on:
        return True, why
    if isinstance(active_project, dict) and active_project.get("auto_route_cloud") is True:
        return True, "this Project Mode workspace has auto_route_cloud on"
    return False, "off in general chat"


# --------------------------------------------------------------------------
#   Gate 2 - the taint latch. A HARD BLOCK.
# --------------------------------------------------------------------------

def taint_latched(active_project=None) -> tuple:
    """(is any local-only taint latched, why). A hard block on the cloud.

    THE HONEST LIMITATION, MEASURED 2026-10-14 AND NOT ROUNDED OFF. This
    project has exactly ONE taint latch, not one per topic:
    `jarvis_gate.latch_taint()` (jarvis-backend/jarvis_gate.py:1772) writes a
    single row keyed `'conversation'`, and its `why` argument is a LABEL, not a
    key - `jarvis_style.py:179` passes `why="style_exemplars"`, the gate passes
    the action name (jarvis_gate.py:1543), and `jarvis_hud.py:4726` passes
    `why="memory_injected"`. Nothing reads `why` back, so there is no way to
    ask "is a SPENDING taint latched". This function therefore does not pretend
    to: ANY active taint blocks, whatever latched it, and the caller is told
    only that personal material was read into this conversation.

    `taint_active()` (jarvis_gate.py:1791) already returns True when it cannot
    read its own database. This function adds the two cases that one cannot
    see: the gate module not being on this PC at all, and a project that is not
    marked shareable - the owner's own flag (`jarvis_projects.py:447`,
    `shareable INTEGER NOT NULL DEFAULT 0`), which is OFF until they approve a
    card that turns it on. A project that has not been approved for sharing is
    local-only, so it blocks here.
    """
    if isinstance(active_project, dict):
        shareable = active_project.get("shareable")
        # Not "if not shareable": the field is 0/1 in SQLite and False/True in
        # the JSON a caller passes, and anything ELSE (None, "", a missing key)
        # means "not known to be shareable", which is also a no.
        if shareable is not True and shareable != 1:
            return True, "this project is not marked shareable"
    gate = _gate_module()
    if gate is None:
        return True, "the taint latch is not on this PC, so nothing is known to be safe"
    try:
        if bool(gate.taint_active()):
            return True, ("personal material was read into this conversation, "
                          "so it stays on this machine")
    except Exception:
        return True, "the taint latch could not be read"
    return False, ""


# --------------------------------------------------------------------------
#   Gate 3 - the cloud budget and the monthly money cap
# --------------------------------------------------------------------------

def budget_allows(lane: str, next_chars: int = 0) -> tuple:
    """(may a cloud turn be afforded at all, why not in plain words).

    Two separate caps, because this project has two and they answer different
    questions. `jarvis_router.Budget` is the on-disk per-minute and per-day
    request cap (jarvis_router.py:323) - a rate limit. `jarvis_chatbot_api`
    `money_check()` (jarvis_chatbot_api.py:1094) is the owner's monthly MONEY
    cap - a spending limit - and it returns `("", cap)` only when the limit
    allows. Everything else it returns is non-empty plain words, including for
    a limit that is UNCONFIGURED (`no_limit_words`) or a service whose price is
    unknown, which is why this function treats any non-empty first element as
    "no" rather than only a `reached` flag: an unconfigured cap is not
    permission to spend.
    """
    router = _router_module()
    if router is None:
        return False, "the cloud budget is not on this PC, so nothing can be priced"
    try:
        budget = router.Budget.load()
        if not budget.allows_cloud():
            which = "per-minute" if budget.minute_exceeded() else "daily"
            return False, f"the {which} cloud budget is spent"
    except Exception:
        return False, "the cloud budget could not be read"

    api = _money_module()
    if api is None:
        return False, "the monthly money limit is not on this PC, so nothing can be priced"
    try:
        pid, model = api.lane_service(lane)
    except Exception:
        return False, f"no service is configured for {lane}"
    if not pid or not model:
        return False, f"no service is configured for {lane}"
    try:
        why, _cap = api.money_check(pid, model, next_chars=int(max(0, next_chars)),
                                    next_messages=1)
    except Exception:
        return False, "the monthly money limit could not be read"
    if why:
        return False, str(why)
    return True, ""


# --------------------------------------------------------------------------
#   Gate 4 - the scrubber, and the text it produces
# --------------------------------------------------------------------------

def scrub_outbound(text) -> tuple:
    """(the text that WOULD leave, why nothing may leave).

    ("", why) is a refusal; a non-empty first element is the scrubbed text.
    The scrubber being absent, raising, returning no text, or leaving a secret
    behind are all refusals - there is no path through this function that
    returns text the scrubber did not produce and then confirm clean.
    """
    scrub = _scrub_module()
    if scrub is None:
        return "", "the scrubber is not on this PC, so nothing may leave"
    try:
        clean = scrub.scrub_text(text, identifiers=True)
    except Exception:
        return "", "the scrubber failed, so nothing may leave"
    if not isinstance(clean, str) or not clean:
        return "", "the scrubber produced no text, so nothing may leave"
    try:
        left = scrub.find_secret(clean)
    except Exception:
        return "", "the scrubber could not confirm the text is clean"
    if left:
        return "", "the scrubber left something behind, so nothing may leave"
    return clean, ""


# --------------------------------------------------------------------------
#   The delegation - the shipped authority gets the last word
# --------------------------------------------------------------------------

def _router_allows(text: str, lane: str, budget=None, tainted: bool = False) -> tuple:
    """(allowed, gate, why) from `jarvis_router.choose()` itself.

    The question asked is deliberately the STRONGEST one available: `choose()`
    is called with `owner_said_yes=True`, so its own gate 6 - "the owner has
    not said yes for this question", which is what normally keeps `choose()`
    from ever escalating on its own (jarvis_router.py:746) - does not mask the
    gates underneath it. What is left is exactly the set of hard refusals:
    cloud_model, lockdown, taint, image, screen, private, secret, complexity
    and budget. Any of those, and this module refuses too.

    Passing `owner_said_yes=True` here does NOT approve anything. This function
    never sends a turn and never touches the approval model; it only asks the
    authority what it would permit, so that the advice below can never be
    broader than the permission.
    """
    router = _router_module()
    if router is None:
        return False, "router_unavailable", (
            "the router is not on this PC, so nothing may be suggested")
    try:
        decision = router.choose(
            text, local_model="", lanes=[lane], conversation_tainted=bool(tainted),
            budget=budget, owner_said_yes=True)
    except Exception:
        return False, "router_error", "the router would not answer, so nothing is suggested"
    gate = str(getattr(decision, "gate", "") or "")
    chosen = str(getattr(decision, "lane", "") or "")
    if gate == "escalate" and chosen == lane:
        return True, gate, ""
    # Every other gate name is a refusal, including the ones that name the
    # local lane itself ("private", "secret", "taint", "image", "screen",
    # "lockdown", "cloud_model", "complexity", "budget", "unavailable").
    why = str(getattr(decision, "reason", "") or "").strip()
    return False, f"router_refused:{gate or 'unknown'}", (
        why or "the router keeps this one on this machine")


# --------------------------------------------------------------------------
#   The measurement
# --------------------------------------------------------------------------

def _from_stats(speed_stats) -> Optional[float]:
    """A rate from the caller's own numbers, or None."""
    direct = _positive(speed_stats)
    if direct is not None:
        return direct
    if isinstance(speed_stats, str):
        try:
            return _positive(float(speed_stats.strip()))
        except Exception:
            return None
    if isinstance(speed_stats, dict):
        direct = _positive(speed_stats.get("tokens_per_s"))
        if direct is not None:
            return direct
        by = speed_stats.get("by_model")
        if isinstance(by, dict):
            best = None
            for stats in by.values():
                if not isinstance(stats, dict):
                    continue
                v = _positive(stats.get("median_tokens_per_s"))
                if v is not None and (best is None or v > best):
                    best = v
            return best
        return None
    if isinstance(speed_stats, (list, tuple)):
        module = _speed_module()
        if module is None:
            return None
        return _best_from_summary(module, speed_stats)
    return None


def _best_from_summary(module, rows: list) -> Optional[float]:
    """The everyday model's measured rate out of `jarvis_speed.summary()`.

    "Everyday" is the model with the most answers, which is the one the owner
    actually talks to; a tie goes to the faster of the two. This is the rate
    for a model that HAS answers, so it is a measurement and not a guess. Falls
    back to the fastest measured model when no row carries an answer count.
    """
    try:
        by = module.summary([r for r in rows if isinstance(r, dict)])
    except Exception:
        return None
    if not isinstance(by, dict) or not by:
        return None
    best = None                      # (answers, rate) - most answers wins
    fastest = None
    for stats in by.values():
        if not isinstance(stats, dict):
            continue
        rate = _positive(stats.get("median_tokens_per_s"))
        if rate is None:
            continue
        if fastest is None or rate > fastest:
            fastest = rate
        count = _number(stats.get("answers")) or 0.0
        if best is None or count > best[0] or (count == best[0] and rate > best[1]):
            best = (count, rate)
    if best is not None:
        return best[1]
    return fastest


def measured_rate(speed_stats=None) -> tuple:
    """(tokens per second, where that number came from).

    In order: the caller's own `speed_stats`; then the measured speed log this
    PC keeps (`jarvis_speed.py`); then `DEFAULT_TOKENS_PER_S`. The third is a
    number and not a measurement, and the second element says which of the
    three was used, so a caller can tell the owner.
    """
    from_caller = _from_stats(speed_stats)
    if from_caller is not None:
        return from_caller, "the caller's own speed numbers"

    module = _speed_module()
    if module is not None:
        try:
            rows = module.SpeedLog().tail(500)
            measured = _best_from_summary(module, rows if isinstance(rows, list) else [])
        except Exception:
            measured = None
        if measured is not None:
            return measured, "measured on this PC (jarvis_speed.py)"

    return DEFAULT_TOKENS_PER_S, "no measurement on this PC - a cautious default"


def category_of(prompt) -> str:
    """The work setup the owner's own words ask for, or "general".

    `jarvis_work.match()` (jarvis_work.py:518) is the project's own reading of
    "what kind of work is this?" - it is pure, total and switches nothing. Its
    `name` is used as the category; no match, or no module, is "general".
    """
    module = _work_module()
    if module is None:
        return "general"
    try:
        matched = module.match(prompt)
    except Exception:
        return "general"
    if isinstance(matched, dict):
        name = str(matched.get("name") or "").strip()
        if name:
            return name
    return "general"


def _answer_tokens(category: str) -> float:
    """How long the ANSWER is expected to be, which is what the owner waits
    for. A review or a coding job is longer than an ordinary question; an
    unrecognised category is an ordinary question."""
    text = str(category or "").lower()
    if _REVIEW.search(text) or "review" in text or "critic" in text:
        return REVIEW_ANSWER_TOKENS
    if "cod" in text or "program" in text or "script" in text:
        return float(REVIEW_ANSWER_TOKENS)
    return float(ANSWER_TOKENS)


def is_review(prompt, last_turn=None) -> bool:
    """Is this a REVIEW task - the kind `jarvis-critic` exists for?

    True when the owner's words ask for one, or when the caller says the turn
    being reviewed is itself a review (`last_turn` with `kind: "review"`).
    """
    if isinstance(last_turn, dict):
        if str(last_turn.get("kind") or "").strip().lower() == "review":
            return True
    if not isinstance(prompt, str):
        return False
    return bool(_REVIEW.search(prompt))


def est_local_seconds(prompt, context_tokens=0, category: str = "general",
                      tokens_per_s=None) -> float:
    """How long this turn is expected to take on this PC, in seconds.

    The work the owner waits for is the ANSWER, plus the prompt the model must
    read, plus whatever conversation is already in front of it. All three are
    divided by the measured rate. This is an ESTIMATE and it is deliberately
    crude: a clever model of a machine nobody can predict would make the advice
    feel random, and the advice is not a decision anyway.
    """
    rate = _positive(tokens_per_s) or DEFAULT_TOKENS_PER_S
    context = _number(context_tokens) or 0.0
    context = max(0.0, context)
    total = context + _tokens(prompt) + _answer_tokens(category)
    return round(total / rate, 2)


def complexity_score(prompt, context_tokens=0, last_turn=None) -> float:
    """A 0.0-1.0 score for how hard this turn looks to this PC.

    Three things add up, and each one is separately provable in the suite:
    multi-file and architecture words in the question (up to 0.45), a
    conversation over `CONTEXT_TOKENS_HEAVY` (0.25), and a previous local turn
    that failed or came back empty (0.30). The score is clamped to 1.0.

    This is NOT `jarvis_router.complexity()` and is not a replacement for it.
    That one reads the SHAPE of the question alone and decides; this one reads
    the SIZE of the job and advises. The shipped threshold is 0.40 on that
    scale; this module's is `COMPLEXITY_THRESHOLD` on this one.
    """
    score = 0.0
    text = prompt if isinstance(prompt, str) else ""
    if text:
        hits = len(set(m.group(0).lower() for m in _MULTI_FILE.finditer(text)))
        score += min(hits * W_MULTI_FILE, W_INDICATORS_CAP)
        arch = len(set(m.group(0).lower() for m in _ARCHITECTURE.finditer(text)))
        score += min(arch * W_ARCHITECTURE, W_INDICATORS_CAP)
        # The cap is on the pair, not on each list, so a question that is both
        # sprawling and architectural still cannot score above 0.45 on words.
        score = min(score, W_INDICATORS_CAP)
    context = _number(context_tokens) or 0.0
    if context > CONTEXT_TOKENS_HEAVY:
        score += W_HEAVY_CONTEXT
    if _prior_bad_turn(last_turn)[0]:
        score += W_PRIOR_BAD_TURN
    return round(min(max(score, 0.0), 1.0), 3)


def _prior_bad_turn(last_turn) -> tuple:
    """(did the last local turn fail or come back empty, in plain words).

    A local model that just failed or answered nothing is the strongest signal
    there is that the next try may want help, and it is the one signal no
    reading of the question alone can produce. Reads strict values only, so a
    caller passing something odd gets no credit for it.
    """
    if last_turn is None:
        return False, ""
    if isinstance(last_turn, str):
        word = last_turn.strip().lower()
        if word in ("failed", "failure", "empty", "error", "timeout", "refused"):
            return True, f"the last local turn was {word}"
        return False, ""
    if isinstance(last_turn, dict):
        if last_turn.get("ok") is False:
            return True, "the last local turn failed"
        if last_turn.get("empty") is True:
            return True, "the last local turn came back empty"
        status = str(last_turn.get("status") or last_turn.get("outcome") or "").strip().lower()
        if status in ("failed", "failure", "empty", "error", "timeout", "refused"):
            return True, f"the last local turn was {status}"
    return False, ""


# --------------------------------------------------------------------------
#   The advice
# --------------------------------------------------------------------------

def _local(out: dict, gate: str, why: str, reason: str = "") -> dict:
    """Every refusal leaves through here, so no return path can accidentally
    keep a cloud lane set."""
    out["lane"] = LOCAL_LANE
    out["recommended"] = False
    out["gate"] = gate
    out["reason"] = reason or gate
    out["why"] = why
    return out


def evaluate_route(prompt, context_tokens=0, active_project=None,
                   speed_stats=None, *, last_turn=None, enabled=None) -> dict:
    """Estimate the cost of this turn locally, and ADVISES a lane - or not.

    THE DECISION IS NOT MADE HERE. `jarvis_router.choose()` decides, and this
    function can only ever return a lane `choose()` would also permit, because
    `_router_allows()` asks it directly.

    Returns a plain dict. The keys a caller may act on:

        lane                  "local", "jarvis-escalate" or "jarvis-critic"
        recommended           True only when `lane` is a cloud lane
        advisory              always True - this is advice, never a permission
        gate / reason         which rule decided; "cost" when advice was given
        why                   the same thing in plain words, ready to show
        est_local_seconds     the estimated wait on this PC
        complexity_score      this module's own 0.0-1.0 score
        category              the work setup `jarvis_work.match()` found
        tokens_per_s          the rate used, and where it came from
        would_send            the SCRUBBED text - empty unless gate 4 passed
        lane_if_allowed       the lane that was under consideration

    A `recommended: True` result always carries a non-empty `would_send`, and
    that is the ONLY text the advice covers. `prompt` itself is never returned
    as something to send: a caller that sends unscrubbed text has ignored this
    function, not been misled by it.

    Never raises. Any input, including None, gives a dict.
    """
    text = prompt if isinstance(prompt, str) else ""
    context = _number(context_tokens)
    context = 0.0 if context is None else max(0.0, context)
    category = category_of(text)
    rate, rate_why = measured_rate(speed_stats)
    seconds = est_local_seconds(text, context, category, rate)
    score = complexity_score(text, context, last_turn)
    lane = LANE_CRITIC if is_review(text, last_turn) else LANE_ESCALATE

    out = {
        "lane": LOCAL_LANE,
        "recommended": False,
        "advisory": True,
        "gate": "",
        "reason": "",
        "why": "",
        "est_local_seconds": seconds,
        "complexity_score": score,
        "category": category,
        "tokens_per_s": rate,
        "tokens_per_s_why": rate_why,
        "would_send": "",
        "lane_if_allowed": lane,
        "thresholds": {"seconds": SECONDS_THRESHOLD,
                       "complexity": COMPLEXITY_THRESHOLD},
        "gates": {},
    }

    # --- gate 1: the mode switch, OFF by default --------------------------
    on, why1 = mode_on(active_project, enabled)
    out["gates"]["mode"] = on
    if not on:
        return _local(out, "auto_route_off", why1)

    # --- gate 2: the taint latch, a HARD BLOCK ---------------------------
    tainted, why2 = taint_latched(active_project)
    out["gates"]["taint"] = not tainted
    if tainted:
        return _local(out, "taint_latched_local_only", why2,
                      reason="taint_latched_local_only")

    # --- gate 3: the budget and the monthly money cap --------------------
    allowed3, why3 = budget_allows(lane, next_chars=len(text))
    out["gates"]["budget"] = allowed3
    if not allowed3:
        return _local(out, "budget", why3)

    # --- gate 4: the scrubber, and the text it produced ------------------
    clean, why4 = scrub_outbound(text)
    out["gates"]["scrubber"] = bool(clean)
    if not clean:
        return _local(out, "scrubber_unavailable", why4)
    out["would_send"] = clean

    # --- the shipped authority gets the last word ------------------------
    budget = None
    router = _router_module()
    if router is not None:
        try:
            budget = router.Budget.load()
        except Exception:
            budget = None
    allowed5, gate5, why5 = _router_allows(clean, lane, budget=budget, tainted=tainted)
    out["gates"]["router"] = allowed5
    if not allowed5:
        return _local(out, gate5, why5)

    # --- is the local wait even worth mentioning? ------------------------
    worth_seconds = seconds > SECONDS_THRESHOLD
    worth_complexity = score >= COMPLEXITY_THRESHOLD
    if not (worth_seconds or worth_complexity):
        kept = ("this looks quick enough here (about "
                f"{seconds:.0f}s, complexity {score:.2f})")
        return _local(out, "not_worth_it", kept)

    pieces = []
    if worth_seconds:
        pieces.append(f"about {seconds:.0f} seconds on this PC")
    if worth_complexity:
        bad, bad_why = _prior_bad_turn(last_turn)
        pieces.append(f"complexity {score:.2f}"
                      + (f", and {bad_why}" if bad else ""))
    out["lane"] = lane
    out["recommended"] = True
    out["gate"] = "cost"
    out["reason"] = "cost"
    out["why"] = (f"{lane} could answer this: " + "; ".join(pieces)
                  + ". You would still be asked before anything is sent.")
    return out


# --------------------------------------------------------------------------
#   The plug-in loader's entry point
# --------------------------------------------------------------------------

def install() -> str:
    """Called by `jarvis_plugins.py` when the folder is loaded.

    `plugins/ready/auto-router/plugin.json` says `install: "none"`, so the
    loader imports this module, calls this with NO arguments, and prints the
    line it returns. Nothing is installed, no route is added, and no core file
    is touched - which is the point: this module advises, `jarvis_router
    .choose()` decides, and nothing about a live turn changes until a caller is
    added deliberately.
    """
    return ("  auto-router  advises on cost only; jarvis_router.choose() "
            "still decides (no route)")


if __name__ == "__main__":
    demo = evaluate_route("Explain, step by step, how the scheduler decides.")
    for key in sorted(demo):
        print(f"  {key:<20} {demo[key]}")
