"""jarvis_router.py - which lane answers, and what it is allowed to see.

REBUILT. The original is gone. Five call sites pin the interface:

    Budget.load().status()                              jarvis_hud:1475
    budget = Budget.load()                              jarvis_hud:1705
    choose(query, local_model=, lanes=, has_image=, ...) jarvis_hud:1707
    degrade(lane, lanes, local_model)                   jarvis_hud:1846
    Decision(chosen, "you chose this lane", "manual", 0.0, inject_memory=...)
                                                        jarvis_hud:2115
    _PRIVATE.search(joined)                             jarvis_hud:2024

and `decision.lane / .reason / .gate / .inject_memory / .as_dict` are all
read. `[budget]` and `[routing]` in the config supply the numbers.

THE RULE THIS MODULE EXISTS TO ENFORCE, from JARVIS-FRAMEWORK.md section 1:

    "cloud turns get your raw question and nothing else. Local turns get your
     question plus whatever stored facts are actually relevant to it. There is
     no third option where a cloud model quietly receives your memory."

So `inject_memory` is FALSE on every cloud lane, computed from the lane rather
than passed in - a caller cannot ask for memory on a cloud turn, because the
bug that started all this (`context_from_memory = true` injecting memory into
every request, before routing even ran) was exactly a caller being trusted.

AND THE ONE THAT WAS BROKEN THE LONGEST: degrade() "has always described that
chain; nothing ever called it, so the documented behaviour did not exist"
(jarvis_hud:1820). It is called now. It walks DOWNWARD only and never returns
the lane it was given, because a degrade that can return its input is an
infinite retry loop against a service that is already refusing.
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

try:
    import jarvis_framework as fw
except Exception:
    fw = None  # type: ignore


def _cfg(section: str, key: str, default=None):
    if fw is None:
        return default
    try:
        return fw.load_framework().get(section, {}).get(key, default)
    except Exception:
        return default


# --------------------------------------------------------------------------
#   What must never go to a cloud lane
# --------------------------------------------------------------------------
#
# jarvis_hud:2024 uses this as `jarvis_router._PRIVATE.search(joined)`, so it
# is a compiled regex with .search, matched against joined message text.
#
# It is a BACKSTOP, not the mechanism. JARVIS-FRAMEWORK.md is explicit: "It's a
# backstop, not the primary mechanism - the primary mechanism is that cloud
# lanes are never handed memory in the first place, so even a topic missing
# from this list can't leak your stored facts, only your literal typed words."
# Anything that relies on this list being complete is designed wrong.
_PRIVATE_TERMS = [
    r"\bpassword\b", r"\bpassphrase\b", r"\bapi[ _-]?key\b", r"\bsecret\b",
    r"\btoken\b", r"\bcredential\b", r"\bprivate key\b", r"\bseed phrase\b",
    r"\bssn\b", r"\bsocial security\b", r"\bpassport\b",
    # Both spellings. The list otherwise uses American terms (ssn,
    # social security) and only had the British "licence" - so "what's
    # my driver's license number" typed in the owner's own words missed
    # the one backstop meant to catch literal private phrases.
    r"\bdriver'?s licen[cs]e\b",
    r"\biban\b", r"\bsort code\b", r"\brouting number\b", r"\baccount number\b",
    r"\bcredit card\b", r"\bcvv\b",
    r"\bdiagnos\w*\b", r"\bprescription\b", r"\bbiopsy\b", r"\bmedical record\b",
    r"\bsalary\b", r"\bbank statement\b", r"\btax return\b",
    # The topics `[privacy] never_leaves_device` names, which this list did
    # not - rule 1 of the project is that email, files and money stay local,
    # and "summarise my inbox" or "what's on my calendar" matched nothing
    # here. Broad on purpose: a false match sends a question to the local
    # model (costs quality), a miss sends it to a cloud one (costs privacy).
    r"\be-?mails?\b", r"\binbox\w*\b", r"\bcalendars?\b",
    r"\bbank\w*\b", r"\binvoic\w*\b", r"\btax(?:es)?\b", r"\bfinanc\w*\b",
    r"\bmedical\b", r"\bfiles?\b",
    # The two private note stores. jarvis-framework.toml's [notes.joplin]
    # said this list matched "joplin"; it did not until 2026-09-24. A
    # question about them is answered where the notes search can run, and
    # that is only ever the local lane.
    r"\bjoplin\b", r"\bobsidian\b", r"\blogseq\b",
    # The same stores asked about WITHOUT naming the app: "search my vault",
    # "what does my wiki say", "what did I write in my notes", "my journal
    # from monday". Those four words are everyday English too - release
    # notes, the Wall Street Journal, a pole vault, a game's wiki - so they
    # count only as the owner's own: "my" or "our", with at most one word
    # between ("my Obsidian vault", "my meeting notes", "my bullet journal").
    r"\b(?:my|our)\s+(?:[\w'-]+\s+)?(?:vaults?|wikis?|notes?|journals?)\b",
]


def _term_pattern(term: str) -> str:
    """One `never_leaves_device` entry as a pattern for typed text:
    "files_on_disk" matches "files on disk", "files-on-disk" and itself, and a
    plural. Empty for an entry with no words in it."""
    words = [re.escape(w) for w in re.split(r"[\s_\-]+", str(term or "").strip()) if w]
    if not words:
        return ""
    return r"\b" + r"[\s_\-]?".join(words) + r"s?\b"


def _config_terms() -> tuple:
    raw = _cfg("privacy", "never_leaves_device", []) or []
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(str(t) for t in raw if isinstance(t, str) and t.strip())


class _PrivateMatcher:
    """The backstop: the words above AND the owner's own `[privacy]
    never_leaves_device` list in jarvis-framework.toml.

    That list said it was "kept in sync with the _PRIVATE regex in
    jarvis_router.py by hand", and it was not - nothing read it at all, so
    adding a word there changed nothing. Now it is read, on every check, so
    an edit to the config applies without a restart (the parse is cached by
    jarvis_framework and only redone when the file changes; the pattern is
    recompiled here only when the list does).

    Looks like a compiled regex to its callers - jarvis_hud calls
    `jarvis_router._PRIVATE.search(joined)` - so it has `.search`, and that
    is all it needs."""

    def __init__(self):
        self._terms: Optional[tuple] = None
        self._rx = re.compile("|".join(_PRIVATE_TERMS), re.I)

    def _current(self):
        terms = _config_terms()
        if terms != self._terms:
            extra = [p for p in (_term_pattern(t) for t in terms) if p]
            self._rx = re.compile("|".join(_PRIVATE_TERMS + extra), re.I)
            self._terms = terms
        return self._rx

    def search(self, text):
        return self._current().search(str(text or ""))

    @property
    def pattern(self) -> str:
        return self._current().pattern


_PRIVATE = _PrivateMatcher()


def is_private(text: str) -> bool:
    return bool(_PRIVATE.search(str(text or "")))


# --------------------------------------------------------------------------
#   What must never go to a cloud lane, part two: the literal secret itself
# --------------------------------------------------------------------------
#
# `is_private()` above matches the WORD for a secret ("what's my api key").
# It says nothing about a message that pastes the secret itself with no
# matching word nearby - a stack trace, a .env line, a curl command copied
# out of a terminal. That gap is real: nothing in this codebase scanned
# outbound content for a secret-SHAPED value before this, only for the
# topic words naming one.
#
# Shape-based and intentionally narrow. A false negative here still has
# is_private()'s keyword list and the taint/complexity/budget gates behind
# it; a false positive sends a genuinely safe question to the local model
# instead of the cloud, which costs quality, not privacy. That asymmetry is
# why this leans toward well-known, low-ambiguity SHAPES (a private key
# block, a provider's own documented token prefix, a JWT's three-dot
# structure) rather than a generic high-entropy-string heuristic, which
# flags far more and explains far less.
_SECRET_PATTERNS = [
    ("a private key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("an AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("a GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("a Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    # Anthropic (sk-ant-api03-...) and today's OpenAI keys (sk-proj-...,
    # sk-svcacct-...) have dashes and underscores inside. The old pattern
    # allowed only letters and digits after "sk-", so it caught the 2023
    # OpenAI shape and missed both of those - the very keys the 2026-09-17
    # API-key rule made likely to be pasted here.
    ("an OpenAI or Anthropic API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("a Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("a Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{30,}\b")),
    ("a JSON web token", re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("a bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}={0,2}", re.I)),
    # A labelled assignment, not a bare high-entropy string: `token = <blob>`
    # is specific enough to act on; an unlabelled 20-character string is not
    # - it is also a hash, an id, a filename.
    ("a labelled secret value", re.compile(
        r"\b(?:api[_-]?key|secret|token|password|passwd)\s*[:=]\s*"
        r"['\"]?([A-Za-z0-9_\-/+]{16,})['\"]?", re.I)),
]


def _mask(excerpt: str) -> str:
    """First four characters and a length, never the excerpt itself. Enough
    for the owner to recognise WHICH secret this was without this function
    becoming a second place the secret is readable in full."""
    excerpt = str(excerpt)
    head = excerpt[:4]
    return f"{head}{'…' if len(excerpt) > 4 else ''} ({len(excerpt)} characters)"


def looks_like_a_secret(text: str) -> Optional[str]:
    """The kind of secret found (masked, human-readable), or None.

    Shape, not topic - see the module note above. Checked in declaration
    order and returns on the first match, so a message tripping several
    patterns is still reported once, with the earliest and most specific
    match winning.
    """
    s = str(text or "")
    for kind, pattern in _SECRET_PATTERNS:
        m = pattern.search(s)
        if m:
            return f"{kind} ({_mask(m.group(0))})"
    return None


# --------------------------------------------------------------------------
#   The budget
# --------------------------------------------------------------------------

@dataclass
class Budget:
    """Cloud requests per minute and per day, counted on disk.

    On disk rather than in memory because the limit is meant to survive a
    restart. A per-process counter resets every time the backend is restarted,
    which on a desktop is several times a day - and a daily cap you can clear
    by restarting is not a cap.
    """

    per_minute: int = 15
    per_day: int = 800
    minute_hits: list = field(default_factory=list)
    day_hits: list = field(default_factory=list)
    path: Optional[Path] = None

    _lock = threading.RLock()

    @classmethod
    def _store_path(cls) -> Path:
        base = Path(fw.CONFIG_DIR) if fw is not None else Path.home() / ".openjarvis"
        return base / "budget.json"

    @classmethod
    def load(cls) -> "Budget":
        b = cls(per_minute=int(_cfg("budget", "requests_per_minute", 15) or 15),
                per_day=int(_cfg("budget", "requests_per_day", 800) or 800),
                path=cls._store_path())
        try:
            raw = json.loads(b.path.read_text(encoding="utf-8"))
            # Each list separately: one corrupt element in `minute` used to
            # discard a perfectly good `day` array, and `day` is the cap that
            # matters.
            for key, dest in (("minute", "minute_hits"), ("day", "day_hits")):
                try:
                    setattr(b, dest, [float(x) for x in (raw.get(key) or [])])
                except (TypeError, ValueError):
                    continue
        except Exception:
            # A missing or corrupt budget file means "no cloud calls recorded",
            # which is the permissive direction - but the alternative is
            # refusing every cloud turn because a JSON file has a stray comma,
            # and the cap is a cost control, not a safety control.
            pass
        b._prune()
        return b

    def _prune(self) -> None:
        now = time.time()
        self.minute_hits = [t for t in self.minute_hits if now - t < 60]
        self.day_hits = [t for t in self.day_hits if now - t < 86400]

    def save(self) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"minute": self.minute_hits,
                                       "day": self.day_hits}), encoding="utf-8")
            tmp.replace(self.path)          # atomic; a torn file reads as empty
        except Exception:
            pass

    def spend(self, n: int = 1) -> None:
        """Record cloud requests, re-reading the file first.

        jarvis_hud calls Budget.load() PER REQUEST on a threading server, so
        several Budget objects exist at once, each holding a snapshot. Without
        the re-read, two of them each spending five wrote five to disk instead
        of ten - half the day's usage lost, and a cap that does not cap.
        """
        with self._lock:
            now = time.time()
            fresh = {"minute": [], "day": []}
            if self.path is not None:
                try:
                    fresh = json.loads(self.path.read_text(encoding="utf-8"))
                except Exception:
                    fresh = {"minute": list(self.minute_hits),
                             "day": list(self.day_hits)}
            try:
                self.minute_hits = [float(x) for x in fresh.get("minute", [])]
                self.day_hits = [float(x) for x in fresh.get("day", [])]
            except (TypeError, ValueError):
                pass
            for _ in range(max(1, n)):
                self.minute_hits.append(now)
                self.day_hits.append(now)
            self._prune()
            self.save()

    def minute_exceeded(self) -> bool:
        self._prune()
        return len(self.minute_hits) >= self.per_minute

    def day_exceeded(self) -> bool:
        self._prune()
        return len(self.day_hits) >= self.per_day

    def allows_cloud(self) -> bool:
        return not (self.minute_exceeded() or self.day_exceeded())

    def status(self) -> dict:
        self._prune()
        return {
            "per_minute": self.per_minute,
            "per_day": self.per_day,
            "used_this_minute": len(self.minute_hits),
            "used_today": len(self.day_hits),
            "minute_exceeded": self.minute_exceeded(),
            "day_exceeded": self.day_exceeded(),
            "cloud_allowed": self.allows_cloud(),
        }


# --------------------------------------------------------------------------
#   The decision
# --------------------------------------------------------------------------

@dataclass
class Decision:
    lane: str
    reason: str
    gate: str
    complexity: float = 0.0
    inject_memory: bool = False
    tainted: bool = False
    #: A cloud lane that COULD answer this turn, offered - never taken - when
    #: the owner has not said yes for this one question (gate "offer").
    #: Empty whenever a privacy gate kept the turn local: those are never
    #: offered to the cloud at all.
    offer: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def is_local_lane(lane: str, local_model: str = "") -> bool:
    """Is this lane running on this machine?

    Name-based, and that is a weakness worth stating: a lane called
    "jarvis-local" that someone pointed at a remote Ollama would read as local
    here. backend/README.md already records the same hazard for OLLAMA_URL -
    "the local model is ALSO egress if OLLAMA_URL does not point at this
    machine" - and the loopback assertion for that lives with the caller that
    opens the socket, which is the only place it can be checked honestly.
    """
    lane = str(lane or "")
    # Ollama's own cloud models ("gpt-oss:120b-cloud", "glm-4.6:cloud") are
    # run THROUGH the local Ollama but answered on ollama.com. The address is
    # 127.0.0.1 and the name can be the configured local model, so neither
    # check below can see it - only the name's "cloud" tag can. Such a lane
    # is never local, whatever else it matches, so memory is never injected
    # into it. Found by the memory-safety red team, 2026-09-24.
    if is_remote_model(lane):
        return False
    if local_model and lane == local_model:
        return True
    return bool(re.search(r"local|jarvis-primary|ollama", lane, re.I))


# The tag Ollama gives a model it runs on its own servers: ":cloud" or a
# size followed by "-cloud" ("120b-cloud"). Matched on the tag only, so a
# local model whose NAME merely contains "cloud" is not caught by accident.
_REMOTE_TAG = re.compile(r":(?:[^:/]*-)?cloud$", re.I)


def is_remote_model(name: str) -> bool:
    """Is this an Ollama model that is answered off this machine?"""
    return bool(_REMOTE_TAG.search(str(name or "").strip()))


#: choose()'s reason when the configured local model is a cloud one.
CLOUD_MODEL_AS_LOCAL = (
    "refused: the everyday model {model} is one of Ollama's cloud models, answered "
    "on ollama.com, not on this PC, so nothing is sent to it. Switch the everyday "
    "model to one that runs on this PC; a cloud model belongs in a cloud lane, "
    "where Jarvis asks you before each question")


def complexity(query: str) -> float:
    """A rough 0-1 score. Longer, more clause-heavy questions score higher.

    INFERRED - only the threshold survived (`[routing] complexity_threshold =
    0.40`, "enforced today by choose() gate 2"). The scale is therefore known
    to be 0-1 with 0.40 meaning "hard enough to consider escalating", and the
    formula below is this file's, not the original's. It is deliberately dull:
    a clever scorer that nobody can predict makes routing feel random.
    """
    q = " ".join(str(query or "").split())
    if not q:
        return 0.0
    words = len(q.split())
    score = min(words / 120.0, 0.6)
    score += 0.1 * min(q.count(",") + q.count(";"), 2)
    if re.search(r"\b(why|how|compare|explain|design|prove|trade-?off)\b", q, re.I):
        score += 0.15
    if re.search(r"\b(step by step|in detail|thoroughly)\b", q, re.I):
        score += 0.1
    return round(min(score, 1.0), 3)


def choose(query: str, local_model: str = "", lanes: Optional[list] = None,
           has_image: bool = False, conversation_tainted: bool = False,
           budget: Optional[Budget] = None, tainted: Optional[bool] = None,
           owner_said_yes: bool = False, **_extra) -> Decision:
    """Which lane answers this turn.

    Eight gates, in this order, and the order is the policy. Each one can only
    send the answer DOWNWARD toward local - none of them can escalate past a
    gate that already refused.

     -1. the local model is itself  -> gate "cloud_model": refused, and
         one of Ollama's cloud models    run_local_turn sends it nothing
      0. no cloud lanes offered      -> local
      1. the conversation is tainted -> local, unconditionally
     1b. the turn carries a picture  -> local, unconditionally
      2. private content matched     -> local
      3. a real secret was found     -> local, unconditionally
      4. not complex enough          -> local
      5. budget spent                -> local
      6. the owner has not said yes  -> local, with the cloud lane OFFERED
         for THIS question
      otherwise                      -> the first cloud lane

    GATE 6, AND WHY THE DEFAULT IS "NO" (the owner's decision, 2026-09-24).
    docs/ARCHITECTURE.md says cloud use is "per use, with permission ...
    and asks. No standing grant." This function used to decide on its own:
    any long, non-private question went to the first cloud lane, and the
    owner saw a Cloud badge afterwards. Now a turn reaches a cloud lane only
    when the caller passes `owner_said_yes=True` - the owner's own yes for
    this one question - and even then gates 0-5 still apply, so a yes can
    never carry a private or tainted turn out. Without it, the turn is
    answered here and `offer` names the lane that could have answered, so an
    app can ask. Nothing learned, remembered or configured sets the yes.

    Gate 2 (`is_private`) catches the WORD for a secret ("what's my api
    key"); gate 3 (`looks_like_a_secret`) catches the secret ITSELF pasted
    with no matching word nearby - a stack trace, a .env line, a token
    copied out of a terminal. Neither replaces the other.

    THE PARAMETER IS `conversation_tainted`, AND THAT IS NOT A DETAIL.

    This was called `tainted`, with `**_extra` to absorb anything unexpected.
    jarvis_hud.py:1714 passes `conversation_tainted=tainted`, so `**_extra`
    silently ate it and gate 1 - the one described here as "local,
    unconditionally" - NEVER FIRED from the only production caller. A
    conversation that had read outside text went to a cloud lane, with
    `decision.tainted` reported False so the route header agreed. No
    exception, no log line.

    That is the whole argument against a permissive `**kwargs` on a function
    that makes a privacy decision: it converts a TypeError at startup, which
    someone fixes in a minute, into an open gate nobody can see. `**_extra`
    is still here so an unknown argument cannot take down every chat turn -
    but anything it catches is now RECORDED, because a silently ignored
    argument to this function is exactly the bug above.
    """
    if tainted is not None:
        # The older spelling, kept working rather than broken.
        conversation_tainted = bool(conversation_tainted) or bool(tainted)
    if _extra:
        try:
            if fw is not None:
                fw.audit_log("router.unknown_argument",
                             {"names": sorted(_extra.keys())})
        except Exception:
            pass
    lanes = list(lanes or [])
    c = complexity(query)
    local = local_model or "local"
    # Whether the "local" lane IS local, rather than assuming it. `local_model`
    # comes from a state file (jarvis_models.current_model()), not a constant,
    # so a caller can hand this function a CLOUD model as its "local" lane.
    # Computing inject_memory from the gate meant every safe-looking gate then
    # returned that cloud lane WITH memory attached - the exact thing the
    # module docstring promises cannot happen. Computed from the lane now.
    local_is_local = is_local_lane(local, local_model)

    def local_decision(gate: str, why: str) -> Decision:
        return Decision(local, why, gate, c,
                        inject_memory=local_is_local,
                        tainted=conversation_tainted)

    # Gate -1, before every other (security audit H1, 2026-09-25): the
    # "local" lane is one of Ollama's cloud models. Every gate below would
    # hand it back as the lane that "stays on this machine" - a tainted
    # turn, a picture, a private question - so none of them may run. The
    # lane is still named (the caller has no other that is local), with
    # gate "cloud_model", no memory and no offer; jarvis_agent.run_local_turn,
    # which answers every local turn, refuses to send it anything and says
    # why in the same words. Where a cloud model belongs is a cloud lane,
    # which asks the owner each time (gate 6).
    if is_remote_model(local):
        return Decision(local, CLOUD_MODEL_AS_LOCAL.format(model=local), "cloud_model", c,
                        inject_memory=False, tainted=conversation_tainted)

    if not lanes:
        # "unavailable", not "no-lanes": jarvis_hud.py:1717 tests for exactly
        # this string to rewrite the reason when Jarvis is injecting memory
        # itself. A different name left that branch dead.
        return local_decision("unavailable", "no cloud lane was offered")
    if conversation_tainted:
        return local_decision(
            "taint",
            "this conversation has read outside text, so it stays on this machine")
    # A PICTURE NEVER LEAVES. A screen capture can show anything that was on
    # screen - an email, a document, a password manager, a bank statement -
    # and none of the text checks below can read it. This used to escalate a
    # picture like any other long question, and even went looking for a cloud
    # lane with "vision" in its name. Rule 1: files, email and credentials
    # stay on the local model. If the local model cannot see pictures, the
    # desktop says so before sending (jarvis-desktop's vision.rs), rather
    # than this routing around it.
    if has_image:
        return local_decision(
            "image",
            "the message carries a picture, which can show anything that was "
            "on screen, so it stays on this machine")
    if is_private(query):
        return local_decision("private", "the question matches the private-topic backstop")
    secret = looks_like_a_secret(query)
    if secret:
        return local_decision(
            "secret", f"the message contains what looks like {secret}, not "
                      f"just a word for one, so it stayed on this machine")
    if c < float(_cfg("routing", "complexity_threshold", 0.40) or 0.40):
        return local_decision("complexity", f"complexity {c} is under the threshold")

    b = budget or Budget.load()
    if not b.allows_cloud():
        which = "daily" if b.day_exceeded() else "per-minute"
        return local_decision("budget", f"the {which} cloud budget is spent")

    lane = lanes[0]
    if owner_said_yes is not True:
        d = local_decision(
            "offer", f"complexity {c}: {lane} could answer this, but the cloud is used "
                     f"only when you say yes for this question")
        d.offer = lane
        return d
    return Decision(lane, f"complexity {c}, budget available, and you said yes for this "
                          f"question", "escalate", c,
                    inject_memory=False, tainted=conversation_tainted)


def degrade(lane: str, lanes: Optional[list] = None,
            local_model: str = "") -> Optional[str]:
    """One step down from `lane`, or None if there is nowhere lower.

    NEVER returns `lane`. jarvis_hud calls this after a lane refused and
    retries with the result; returning the input would retry the refusing lane
    for ever. The caller checks `if not nxt or nxt == lane: break` as a second
    guard, and that guard should never fire.

    The chain is `[budget].degrade_chain` when the current lane is in it,
    otherwise the caller's own `lanes` list, and local is always the floor -
    checked FIRST, unconditionally, before `chain` or `lanes` is even read.

    THAT ORDERING IS THE FIX. It used to be checked last: `order` was built
    from `chain` or `lanes`, and if `lane` (already equal to `local`) happened
    to appear inside that list with something after it, the walk returned
    THAT NEXT ENTRY instead of ever reaching the floor. `jarvis_hud:1738`
    documents that a `lanes` list containing `local_model` is a real state -
    it exists specifically so degrading FROM a cloud lane can land ON local -
    but the same list read the other way, starting the walk AT local, handed
    back a CLOUD lane. Reproduced: `degrade("local", ["local","a","b"],
    "local")` returned `"a"`. `choose()` pins a conversation to `local`
    unconditionally on taint or the private backstop - this was the one path
    that could still walk it back out to the cloud, the moment the local
    model refused or timed out and jarvis_hud asked what to try next.
    """
    lane = str(lane or "")
    local = local_model or "local"
    if lane == local:
        return None
    chain = list(_cfg("budget", "degrade_chain", []) or [])
    order = chain if lane in chain else list(lanes or [])

    # Seen lanes are skipped, so a chain that lists a lane twice - or a
    # `lanes` list that CONTAINS local_model, which jarvis_hud:1738 shows is a
    # real state - cannot produce a 2-cycle. It could before: degrade("a",
    # ["a","b"], "a") gave "b" and degrade("b", ["a","b"], "a") gave "a",
    # which never returns its own input and so slipped past the caller's
    # `nxt == lane` guard while re-opening a lane that had just refused.
    if lane in order:
        seen = {lane}
        for nxt in order[order.index(lane) + 1:]:
            if nxt and nxt not in seen:
                return nxt
            seen.add(nxt)
    # Bottom of the chain, or a lane nobody listed. Local is always the floor.
    return local


def status() -> dict:
    return {"budget": Budget.load().status(),
            "complexity_threshold": _cfg("routing", "complexity_threshold", 0.40),
            "degrade_chain": _cfg("budget", "degrade_chain", []),
            "private_terms": len(_PRIVATE_TERMS) + len(_config_terms()),
            "secret_patterns": len(_SECRET_PATTERNS)}


if __name__ == "__main__":
    for k, v in status().items():
        print(f"  {k:<22} {v}")
