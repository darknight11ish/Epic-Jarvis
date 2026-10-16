"""jarvis_compaction.py - what a long conversation keeps: exact lines, and words.

WHAT THIS IS FOR

Two things already happen to a long conversation before it reaches the model
(`jarvis_agent.py`):

  * `clear_old_tool_results` empties the OLDER tool results, once the whole is
    past half the room, because up to six rounds of tool output would otherwise
    crowd out everything else. What it left behind was one bare sentence -
    `"[an earlier tool result was cleared to make room]"` - so WHICH file or URL
    was read, WHETHER the call was denied, and every identifier it returned were
    all gone from the model's view.
  * `fit_messages` drops the oldest question-and-answer pairs together until the
    prompt fits, down to three quarters of the budget so the start of the prompt
    stays the same for a few turns (Ollama reuses the KV prefix it has already
    read). It is TRIMMING, not summarising: a port number, a path, a temporary
    constraint or an error string from thirty turns ago is simply gone, even
    though the conversation is still on disk.

This module keeps the small, exact facts and the owner's own rules instead of
the prose. It is the deterministic half of that work and it holds no model: the
optional condensation at the bottom is off by default and never touches the
exact lines.

THREE SURFACES, ONE RULE EACH

1. `tool_stub()` - what a cleared tool result becomes (<= `STUB_MAX` characters):
   the tool, its primary target, an explicit OUTCOME, and up to three anchors.
   The outcome is one of `ok`, `error`, `denied_by_owner`, and the third word is
   the point: a call the approval gate refused must never read as a call that
   completed (`jarvis_agent.py` writes every refusal as an error beginning
   `"refused:"` - see `OUTCOME_REFUSED`).

2. `digest_message()` - ONE bounded system message folding the evicted turns:
   the owner's own constraints VERBATIM, a table of exact anchors each labelled
   with the turn it came from, and one line per turn saying how it ended.

3. `recall_message()` - the one or two EVICTED turns most relevant to the
   question, bounded, meant to be placed AFTER the cached prefix.

THE RULE THAT DECIDES WHETHER THIS IS A FIX OR A REGRESSION

`fit_messages` trims to three quarters so that the START of the prompt does not
change between turns, and Ollama can reuse what it has already read. Everything
here is therefore a PURE FUNCTION of the evicted turns: same evicted turns, same
bytes, in the same order. No clock, no random, no counter that keeps climbing -
the digest says how many turns were folded, and that number IS its key
(`digest_key`). A turn that evicts nothing must come out of
`jarvis_agent.compact_messages` byte-for-byte as `fit_messages` returns it today.

SCRUBBED, AND FAILING CLOSED WITHOUT THE SCRUBBER

Every stub, every quoted constraint, every anchor and the recall text go through
`jarvis_scrub.scrub_text`. With NO scrubber nothing is emitted at all: the stub
falls back to the old bare placeholder, and no digest and no recall are built.
A conversation that might hold a credential is not worth a nicer prompt.

Standard library only. It reads nothing, writes nothing, opens no route and
reaches no network; it is a set of pure functions over the messages it is given.
"""
from __future__ import annotations

import re
import threading
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

#: Where a cleared tool result's stub must fit. Short enough that a round of six
#: tool calls still costs less than one tool result did.
STUB_MAX = 180

#: The one system message the evicted turns are folded into. Anything starting
#: with this (or with RECALL_HEADER) is this module's own earlier output and is
#: never treated as something the owner said.
DIGEST_HEADER = "[EARLIER IN THIS CONVERSATION]"
RECALL_HEADER = "[RECALLED FROM EARLIER]"
ANCHOR_HEADER = "exact lines kept (turn: line):"
CONSTRAINT_HEADER = "the owner's own rules, word for word:"
OUTCOME_HEADER = "how each ended:"

#: The three words a stub may use for how a call ended. `denied_by_owner` is the
#: one that matters: a gate refusal is NOT a completed call, and the agent writes
#: every refusal's error as a string starting with this prefix (three sites in
#: `jarvis_agent.py`, pinned by the suite).
OUTCOME_OK = "ok"
OUTCOME_ERROR = "error"
OUTCOME_DENIED = "denied_by_owner"
OUTCOME_REFUSED = "refused:"

#: How much of a digest, and of a recall, is allowed. Tokens here are the same
#: pessimistic 3-characters-a-token the agent uses (`estimate_tokens`).
DIGEST_TOKENS = 700
RECALL_TOKENS = 400
RECALL_TURNS = 2

#: Up to this many anchors in a stub, and this many in one digest.
STUB_ANCHORS = 3
DIGEST_ANCHORS = 24

#: How long one verbatim constraint sentence may be before it is cut (with an
#: honest " ..."), so one long paragraph cannot spend the whole digest.
CONSTRAINT_MAX = 240

#: The owner's own constraint markers, in the words this owner really uses.
#: Deliberately a small, readable list: a sentence is quoted VERBATIM, so a
#: sentence wrongly included costs context, and one wrongly left out is the
#: failure this module exists to prevent.
CONSTRAINT_MARKERS: Tuple[str, ...] = (
    "never", "don't", "do not", "don't ever", "always", "must not", "must",
    "make sure", "be sure", "remember to", "remember that", "only", "keep it",
    "no more than", "at most", "at least", "without asking", "ask me first",
)

#: The exact things worth keeping. Each is narrow on purpose: a pattern that
#: matches every number would fill the table with noise and keep nothing.
ANCHORS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("url", re.compile(r"https?://[^\s\"'<>)\]},;]+")),
    ("path", re.compile(r"\b[A-Za-z]:\\(?:[^\\/:*?\"<>|\r\n ]+\\)*[^\\/:*?\"<>|\r\n ]*")),
    ("path", re.compile(r"(?<![\w.])/(?:[\w.\-]+/)+[\w.\-]+")),
    ("file", re.compile(r"\b[\w.\-]+\.(?:py|json|toml|md|txt|log|csv|xlsx|xls|db|ps1|kt|rs|js|mjs|html|yaml|yml|ini|cfg|lock)\b")),
    ("module", re.compile(r"\bjarvis_[a-z0-9_]+(?:\.py)?\b")),
    ("sha", re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")),
    ("date", re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?\b")),
    ("version", re.compile(r"\bv\d+(?:\.\d+)+\b|\b\d+\.\d+\.\d+\b")),
    ("hostport", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b")),
    ("port", re.compile(r"\bport\s*[:=]?\s*\d{2,5}\b", re.I)),
    ("amount", re.compile(r"(?:[$£€]\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s*(?:GB|MB|KB|GiB|MiB|tokens?|ms)\b)")),
    ("error", re.compile(r"\b[A-Z][A-Za-z0-9_]*(?:Error|Exception)\b")),
    ("code", re.compile(r"`([^`\n]{2,60})`")),
)
_ANCHOR_ORDER = {kind: i for i, (kind, _) in enumerate(ANCHORS)}
_CODE_ANCHOR = "code"


# --------------------------------------------------------------------------
#   The scrubber - optional, and nothing is emitted without it
# --------------------------------------------------------------------------

def scrubber():
    """`jarvis_scrub`, or None. The same fail-closed rule as everywhere else
    (`jarvis_voiceprint.py:632`): a missing scrubber must not mean "carry on
    unscrubbed"."""
    try:
        import jarvis_scrub                                     # noqa: PLC0415
        return jarvis_scrub
    except Exception:                                           # noqa: BLE001
        return None


def clean(text) -> Optional[str]:
    """`text` scrubbed, or None when there is no scrubber to scrub it with."""
    scrub = scrubber()
    if scrub is None:
        return None
    try:
        return scrub.scrub_text(text if text is not None else "")
    except Exception:                                           # noqa: BLE001
        return None


def tokens(text: str) -> int:
    """The agent's own pessimistic count (`jarvis_agent.estimate_tokens`)."""
    return 6 + len(text or "") // 3


# --------------------------------------------------------------------------
#   Anchors
# --------------------------------------------------------------------------

def extract_anchors(text: str, *, limit: Optional[int] = None) -> Tuple[str, ...]:
    """The exact things in `text`, in a fixed order, each appearing once.

    Order is by KIND (the order of `ANCHORS`) and then by first appearance, so
    two runs over the same text return the same tuple on any machine.

    AN ANCHOR INSIDE A LONGER ONE IS DROPPED. `C:\\Users\\me\\notes.txt` also
    matches the bare file name and the drive letter, and `127.0.0.1:11434` also
    matches the version-shaped `127.0.0`; keeping the small ones would fill the
    table with fragments of the lines that matter. Where one candidate contains
    another, the LONGER one is kept - and where they are the same length, the
    earlier one in the fixed kind order.
    """
    found: List[Tuple[int, int, str]] = []
    seen = set()
    for kind, pattern in ANCHORS:
        for match in pattern.finditer(text or ""):
            value = (match.group(1) if kind == _CODE_ANCHOR and match.groups()
                     else match.group(0)).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            found.append((_ANCHOR_ORDER[kind], match.start(), value))
    # Drop the ones that are really a fragment of another: longest first, and
    # for equal lengths the earlier in kind order.
    ordered = sorted(found, key=lambda item: (-len(item[2]), item[0], item[1]))
    keep: List[Tuple[int, int, str]] = []
    for item in ordered:
        if any(item[2] != other[2] and item[2] in other[2] for other in keep):
            continue
        keep.append(item)
    keep.sort(key=lambda item: (item[0], item[1]))
    values = tuple(item[2] for item in keep)
    return values[:limit] if limit else values


def _fit(parts: Sequence[str], limit: int) -> str:
    """Join `parts` with " | ", dropping the TAIL until it fits `limit`.

    Dropping from the end (and never from the middle) is what keeps the result
    deterministic and keeps the most important part - the tool, its target and
    its outcome - first.
    """
    out = " | ".join(p for p in parts if p)
    if len(out) <= limit:
        return out
    kept: List[str] = []
    for part in parts:
        if not part:
            continue
        trial = " | ".join(kept + [part])
        if len(trial) > limit:
            break
        kept.append(part)
    return " | ".join(kept)[:limit]


# --------------------------------------------------------------------------
#   1. The tool-result stub
# --------------------------------------------------------------------------

#: Argument keys that name a tool call's primary target, most specific first.
TARGET_KEYS: Tuple[str, ...] = (
    "path", "file", "filename", "url", "uri", "query", "q", "command", "cmd",
    "name", "ref", "id", "expr", "expression", "text", "model", "pattern",
)


def primary_target(args) -> str:
    """The one thing this call was aimed at, from its own arguments.

    A named key first (`TARGET_KEYS`), then the first short string value in
    sorted-key order - deterministic, and never a whole JSON blob.
    """
    if not isinstance(args, dict):
        return ""
    for key in TARGET_KEYS:
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:80]
    for key in sorted(args):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:80]
    return ""


def _outcome(result: dict, text: str) -> str:
    """How this call ended, in three words.

    `ok` when the result says it worked. A gate refusal - which the agent writes
    as an error beginning `refused:`, at every refusal site - is
    `denied_by_owner`, so it can never read as a completed call. Everything else
    that carries an error, or that does not say it worked, is `error`.

    A result with no `ok` at all is read from its `error` key: most reading
    tools answer without one, and calling every one of them an error would make
    the third word mean nothing.
    """
    if not isinstance(result, dict):
        return OUTCOME_DENIED if OUTCOME_REFUSED in (text or "")[:400] else OUTCOME_ERROR
    if result.get("ok") is False:
        if str(result.get("error") or "").startswith(OUTCOME_REFUSED):
            return OUTCOME_DENIED
        return OUTCOME_ERROR
    if result.get("ok") is True:
        return OUTCOME_OK
    return OUTCOME_ERROR if result.get("error") else OUTCOME_OK


def tool_stub(*, name: str = "", args=None, result_text: str = "",
              result: Optional[dict] = None, limit: int = STUB_MAX) -> Optional[str]:
    """What a cleared tool result becomes: `tool | target | outcome | anchors`.

    `None` when there is no scrubber - the caller must then fall back to the old
    bare placeholder rather than emit anything from the result. Never raises.
    """
    try:
        import json as _json
        parsed = result
        if parsed is None:
            parsed = {}
            try:
                body = _json.loads(result_text or "")
                if isinstance(body, dict):
                    parsed = body
            except Exception:                                   # noqa: BLE001
                parsed = {}
        outcome = _outcome(parsed if isinstance(parsed, dict) else {}, result_text or "")
        anchors = extract_anchors(result_text or "", limit=STUB_ANCHORS)
        target = primary_target(args)
        parts = [str(name or "tool"), target, outcome]
        parts.extend(anchors)
        raw = _fit(parts, limit)
        text = clean(raw)
        if text is None:
            return None
        return text[:limit].strip()
    except Exception:                                           # noqa: BLE001
        return None


# --------------------------------------------------------------------------
#   2. The rolling digest
# --------------------------------------------------------------------------

def _content(message) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(part.get("text") or "") for part in content
                        if isinstance(part, dict))
    return ""


def is_own_message(message) -> bool:
    """Is this message one of ours (a digest or a recall line)?

    A message is checked by its first line, so a digest that has been given back
    to us is never folded into the next one (which would double it) and never
    mistaken for something the owner said.
    """
    content = _content(message).lstrip()
    return content.startswith(DIGEST_HEADER) or content.startswith(RECALL_HEADER)


def _one_line(text: str, limit: int = 120) -> str:
    flat = " ".join(str(text or "").split())
    return flat[:limit].rstrip() + (" ..." if len(flat) > limit else "")


def user_constraints(evicted: Sequence[dict], *, limit: int = 6) -> Tuple[str, ...]:
    """The owner's own words, VERBATIM, where they set a rule.

    A sentence carrying one of `CONSTRAINT_MARKERS` is kept exactly as he wrote
    it - not summarised, because the words ("never", "only", "at most") are what
    carries the meaning. Sentence order is document order, so the same evicted
    turns give the same list.

    Each sentence is capped at `CONSTRAINT_MAX` characters with an honest " ...",
    because one long paragraph carrying a rule would otherwise spend the whole
    digest on itself; the rule is at the start of a sentence in every case this
    owner's own phrasing has produced.
    """
    out: List[str] = []
    for message in evicted:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        body = _content(message)
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", body):
            words = " ".join(sentence.split()).strip()
            if not words or len(words) < 6:
                continue
            low = words.lower()
            if any(marker in low for marker in CONSTRAINT_MARKERS):
                words = words[:CONSTRAINT_MAX].rstrip() + (
                    " ..." if len(words) > CONSTRAINT_MAX else "")
                if words not in out:
                    out.append(words)
            if len(out) >= limit:
                return tuple(out)
    return tuple(out)


def _turn_endings(evicted: Sequence[dict]) -> List[str]:
    """One line per evicted turn saying how it ENDED - never what was asked.

    The question is deliberately not quoted here. The anchor table above
    already says what each turn was about, in the exact lines it produced, and
    quoting the owner's question again would cost the context this module exists
    to save. It also matters for a check elsewhere: `test_lane_prompt.py`'s
    control proves trimming really happened by showing the evicted turn's own
    words are gone from the prompt, and a digest that quoted them back would
    make that control unreadable.
    """
    lines: List[str] = []
    turn = 0
    outcome = ""
    for message in evicted:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role == "user":
            if turn and outcome:
                lines.append(f"- turn {turn}: {outcome}")
            turn += 1
            outcome = ""
        elif role == "assistant":
            if not outcome:
                outcome = "answered"
        elif role == "tool":
            word = _outcome_for_tool(_content(message))
            if word:
                outcome = word
    if turn and outcome:
        lines.append(f"- turn {turn}: {outcome}")
    return lines


def _outcome_for_tool(text: str) -> str:
    try:
        import json as _json
        body = _json.loads(text or "")
    except Exception:                                           # noqa: BLE001
        return ""
    if not isinstance(body, dict):
        return ""
    return _outcome(body, text)


def digest_key(evicted: Sequence[dict]) -> str:
    """The digest's identity: the number of turns folded away.

    This is what makes "byte-for-byte identical between compactions" checkable.
    The digest says this number out loud, so a reader (and a test) can see that
    nothing was rewritten when nothing new was evicted.
    """
    return f"evicted-turns={_turn_count(evicted)}"


def _turn_count(evicted: Sequence[dict]) -> int:
    return sum(1 for m in evicted if isinstance(m, dict) and m.get("role") == "user")


def digest_text(evicted: Sequence[dict], *, max_tokens: int = DIGEST_TOKENS) -> Optional[str]:
    """The folded turns as one block of text, or None when there is nothing to
    fold or no scrubber to scrub it with.

    Sections, in this order: the count (the key), the owner's rules word for
    word, the exact anchors with the turn each came from, and one line per turn.
    Everything is a pure function of `evicted`, so the same turns give the same
    bytes - which is the whole point.
    """
    turns = _turn_count(evicted)
    if turns <= 0:
        return None
    lines = [DIGEST_HEADER,
             f"{turns} earlier exchange{'s' if turns != 1 else ''} were folded away "
             f"to make room ({digest_key(evicted)})."]

    constraints = user_constraints(evicted)
    if constraints:
        lines.append(CONSTRAINT_HEADER)
        lines.extend(f"- {c}" for c in constraints)

    anchors: List[str] = []
    seen_anchors: set = set()
    turn = 0
    for message in evicted:
        if not isinstance(message, dict):
            continue
        if message.get("role") == "user":
            turn += 1
        if turn <= 0:
            continue
        for value in extract_anchors(_content(message)):
            # One line per DISTINCT exact thing, labelled with the FIRST turn it
            # came from: a path mentioned in four turns is one path, and the
            # turn it first appeared is the one worth naming.
            if value in seen_anchors:
                continue
            seen_anchors.add(value)
            anchors.append(f"- turn {turn}: {value}")
            if len(anchors) >= DIGEST_ANCHORS:
                break
        if len(anchors) >= DIGEST_ANCHORS:
            break
    if anchors:
        lines.append(ANCHOR_HEADER)
        lines.extend(anchors)

    endings = _turn_endings(evicted)
    if endings:
        lines.append(OUTCOME_HEADER)
        lines.extend(endings)

    body = "\n".join(lines)
    # Bounded, and bounded the same way every time: whole trailing lines are
    # dropped, never a character count, so the same turns always give the same
    # text back.
    while tokens(body) > max_tokens and len(lines) > 2:
        lines.pop()
        body = "\n".join(lines)
    text = clean(body)
    return text


def digest_message(evicted: Sequence[dict], *,
                   max_tokens: int = DIGEST_TOKENS) -> Optional[dict]:
    """The digest as the one system message it is sent as, or None."""
    body = digest_text(evicted, max_tokens=max_tokens)
    if not body:
        return None
    return {"role": "system", "content": body}


# --------------------------------------------------------------------------
#   3. Query-triggered recall of evicted turns
# --------------------------------------------------------------------------

#: Words that do not make a question about anything. Without this, a recall is
#: pulled in by "the new question" sharing the word "question" with an evicted
#: turn - measured: that fired on every turn of a long conversation, spending
#: 400 tokens to say what the prompt already said.
_RECALL_STOP = frozenset({
    "the", "and", "for", "with", "that", "this", "these", "those", "what",
    "when", "where", "which", "who", "why", "how", "question", "questions",
    "answer", "answers", "asked", "ask", "tell", "about", "please", "could",
    "would", "should", "again", "more", "some", "any", "you", "your", "have",
    "does", "did", "was", "were", "are", "is", "it", "its", "not", "but",
    "can", "will", "now", "then", "there", "here", "new", "next", "last",
})


def _score(question: str, message: dict) -> int:
    """How relevant one evicted message is to the question.

    Shared words only, lowercased, three characters or more and not one of the
    words that mean nothing (`_RECALL_STOP`) - the same shape
    `jarvis_self_improve.retrieve` uses, and never a model call: this runs on
    the hot path, so it is arithmetic and nothing else.
    """
    words = {w for w in re.findall(r"[a-z0-9_]+", (question or "").lower())
             if len(w) >= 3 and w not in _RECALL_STOP}
    if not words:
        return 0
    body = _content(message).lower()
    return sum(1 for w in words if w in body)


def recall_text(question: str, evicted: Sequence[dict], *,
                turns: int = RECALL_TURNS, max_tokens: int = RECALL_TOKENS) -> Optional[str]:
    """The most relevant EVICTED turns, bounded, or None.

    Whole turns are chosen (a question with its answer and its tool results),
    never a mid-turn slice, and each is quoted from the turn's own words. The
    caller places this AFTER the cached prefix, so a turn's prefix is never
    disturbed by what this turn happens to ask.
    """
    if not question or not evicted:
        return None
    blocks: List[List[dict]] = []
    current: List[dict] = []
    for message in evicted:
        if not isinstance(message, dict):
            continue
        if message.get("role") == "user" and current:
            blocks.append(current)
            current = []
        current.append(message)
    if current:
        blocks.append(current)
    if not blocks:
        return None

    scored = []
    for index, block in enumerate(blocks):
        best = max((_score(question, m) for m in block), default=0)
        total = sum(_score(question, m) for m in block)
        scored.append((best, total, index, block))
    # Most relevant first; the FIRST word of the question breaks a tie, and the
    # position breaks the rest, so this is a total order - the same question and
    # the same turns always pick the same blocks in the same order.
    scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
    picked = [item for item in scored[:max(1, turns)] if item[0] > 0]
    if not picked:
        return None
    picked.sort(key=lambda item: item[2])          # back into conversation order

    lines = [RECALL_HEADER, "from earlier in this conversation, before it was folded:"]
    for _best, _total, index, block in picked:
        for message in block:
            role = message.get("role")
            if role == "tool":
                continue                            # the digest already carries its anchors
            said = _one_line(_content(message), 200)
            if not said:
                continue
            lines.append(f"- {role}: {said}")
    body = "\n".join(lines)
    while tokens(body) > max_tokens and len(lines) > 2:
        lines.pop()
        body = "\n".join(lines)
    if len(lines) <= 2:
        return None
    return clean(body)


def recall_message(question: str, evicted: Sequence[dict], *,
                   turns: int = RECALL_TURNS,
                   max_tokens: int = RECALL_TOKENS) -> Optional[dict]:
    """The recall as the system message it is sent as, or None."""
    body = recall_text(question, evicted, turns=turns, max_tokens=max_tokens)
    if not body:
        return None
    return {"role": "system", "content": body}


# --------------------------------------------------------------------------
#   4. Optional condensation of the PROSE only, off the hot path
# --------------------------------------------------------------------------

class Condenser:
    """Optional: a model shortening the digest's WORDS, never its exact lines.

    OFF by default (`enabled=False`), and nothing here ever runs on the hot
    path: `submit()` starts a daemon thread and returns at once, and the result
    is only ever used for the NEXT compaction, never for this one - so the bytes
    sent this turn cannot depend on when a thread finished.

    THE CIRCUIT BREAKER. A condenser that fails (or is missing) is retried no
    more than `max_failures` times in a row; after that this stops calling it
    at all until `reset()`. An optional nicety must never become a turn that
    waits, or a log filled with the same failure.

    THE ANCHOR TABLE IS NEVER GIVEN TO IT. `submit()` takes prose only; the
    caller passes `digest_prose()`, which is the digest with its exact-line
    section removed. A model may not rewrite a path, a port or a SHA.
    """

    def __init__(self, condense: Optional[Callable[[str], str]] = None, *,
                 enabled: bool = False, max_failures: int = 3) -> None:
        self.condense = condense
        self.enabled = bool(enabled) and condense is not None
        self.max_failures = max(1, int(max_failures))
        self.failures = 0
        self.tripped = False
        self.calls = 0
        self.results: dict = {}
        self._lock = threading.RLock()

    def available(self) -> bool:
        return bool(self.enabled and not self.tripped and self.condense is not None)

    def _run(self, key: str, prose: str) -> None:
        try:
            short = self.condense(prose)
        except Exception:                                       # noqa: BLE001
            short = None
        with self._lock:
            self.calls += 1
            if isinstance(short, str) and short.strip():
                self.failures = 0
                self.results[key] = short.strip()
                return
            self.failures += 1
            if self.failures >= self.max_failures:
                self.tripped = True

    def submit(self, key: str, prose: str) -> bool:
        """Ask for `prose` to be shortened later. True when a thread was started.

        Never blocks, never raises, and does nothing at all unless it is enabled
        and the breaker is closed.
        """
        if not self.available() or not prose or key in self.results:
            return False
        thread = threading.Thread(target=self._run, args=(key, prose),
                                  name="jarvis-condense", daemon=True)
        thread.start()
        return True

    def take(self, key: str) -> Optional[str]:
        with self._lock:
            return self.results.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self.failures = 0
            self.tripped = False
            self.results.clear()


def digest_prose(text: str) -> str:
    """`text` with its exact-line section removed - what a condenser may see.

    Everything from `ANCHOR_HEADER` to the next section is dropped, so the
    paths, ports, versions, dates and error names are not in the string at all.
    """
    lines = (text or "").split("\n")
    out: List[str] = []
    skipping = False
    for line in lines:
        if line.strip() == ANCHOR_HEADER:
            skipping = True
            continue
        if skipping:
            if line.strip() in (OUTCOME_HEADER, CONSTRAINT_HEADER) or line.startswith("["):
                skipping = False
            else:
                continue
        out.append(line)
    return "\n".join(out).strip()
