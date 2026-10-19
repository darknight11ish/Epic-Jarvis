"""jarvis_self_improve.py - Jarvis reads its own source, and drafts what it may not apply.

    import jarvis_self_improve as si

    d = si.diagnose("where is the taint latch written?")
    print(si.text(d))        # a quote with file:line, or "I could not establish this"

    p = si.draft("the jobs queue never runs its due jobs")
    print(si.proposal_text(p))   # a diff, a test diff and plain words, or a refusal

WHY THIS EXISTS

The most expensive recurring failure in this project is a WRONG PREMISE: a line
number reported as current, a feature described as missing when it is built, a
"confirmed" finding produced by grepping the wrong tree. Every one of those was
caught by reading the source. This module is the tool that reads the source and
answers with the line it read - and says plainly when it could not.

It is the read-only half of the self-improvement design
(`JARVIS-SELF-IMPROVEMENT-DESIGN-FOR-REVIEW.md`, sections 4 and 5.1-5.2 steps
1-3: phases 3 and 4). Phase 5 - applying a change with an approval card,
verification and a one-click undo - is deliberately NOT here and must not be
added to this file. Nothing in this module writes, applies, approves, cards or
reverts anything.

RETRIEVAL FIRST, MODEL SECOND

A 9B model reading this repository will hallucinate. So nothing here asks a model
to REMEMBER anything. It is two steps, and the first one is deterministic:

  1. `retrieve()` picks the lines that are really relevant, by matching the
     question's own words against the files it may read. Same question, same
     lines, no model involved - and that is the half the suite can prove.
  2. The model is asked to EXPLAIN those lines and nothing else. It answers by
     citing the NUMBER of a line it was shown, never by quoting one.

A citation this module reports is re-read from the file at that moment. The
model's own text is never presented as the evidence, so a paraphrase dressed as
a fact - or an invented quote - cannot be reported as one: the worst a bad answer
can do is cite a line that does not support it, and the quote beside it is still
the line that is really there.

EVERY ANSWER EITHER CITES A REAL LINE OR SAYS IT COULD NOT FIND ONE

That is a property of the shape, not a promise about the model. The reply
protocol has no third form:

    ANSWER: <what the lines show>
    CITE: 3
    CITE: 7
    ...
    CANNOT: <what is missing>

No valid `CITE` and no `CANNOT` is read as "could not establish" - never as an
answer. `text()` then prints either the explanation over its real quotes, or one
plain sentence saying this PC could not establish it.

WHAT IT MAY READ (the design's own table, section 4.3)

  * the program's own text files - this module's own folder (which is the
    backend folder on the owner's PC, `_jarvis-logs/` included), and, in a
    checkout of this repository, `backend/`, `jarvis-backend/`, `tools/`,
    `scripts/`, `docs/`, `features/features.json` and the four root documents
    that say what the program is (`README.md`, `CHANGELOG.md`, `CLAUDE.md`, the
    design document);
  * anything a caller names through `roots=` - the seam a later wiring uses for
    a log folder.

It does NOT read a database, and it does not open `~/.openjarvis` at all: section
4.3 allows the state databases only THROUGH THE EXISTING MODULES, which enforce
the taint and scrub rules. Reading one here would be exactly the raw handle that
rule forbids. The audit log lives under that folder too; a caller that has an
approved way to name it can pass it as a root, and this module treats it as text
like any other file. Until that wiring exists, the honest state is that this
module reads the PROGRAM, not the owner.

WHAT PROTECTS WHAT IS QUOTED

  * Every quote, every explanation and every drafted diff goes through
    `jarvis_scrub.scrub_text`. WITH NO SCRUBBER NOTHING IS QUOTED AT ALL - the
    answer becomes "the scrubber is not available, so nothing was read out".
    That is the fail-closed rule this project uses everywhere
    (`jarvis_voiceprint.py:632` is the same shape).
  * A question about private material, or a line read out of a module that HOLDS
    it, calls `jarvis_gate.latch_taint(why=...)` (`jarvis_gate.py:1772`), so the
    conversation cannot later be offered a cloud lane.
  * The only thing this module ever sends anywhere is the prompt to the LOCAL
    model, and `_loopback_url()` refuses a host that is not loopback. There is no
    other network call and no client of any kind.
  * There is no field anywhere in this file for a model's self-reported
    confidence. Section 4.4: it is not evidence.

THE TWO ROUTES, AND WHY THEY ARE THE ONLY ONES (added 2026-10-17)

The design's Phase 3 was written with "no route" so that nothing could apply
anything, and Phase 5 is still not here: this module applies nothing, writes
nothing, cards nothing and reverts nothing. What IS here now is the read-only
exposure the wiring queue asked for (2026-10-17): two
GET routes, behind the core's own origin and token checks, answered by
this PC's own requests only (another device is refused 403 before anything is
read), served by `install()` - the same shape every drop-in module's install()
has, called from
`plugins/ready/self-improve/`:

    GET /api/self-improve/diagnose?q=<question>   diagnose()'s answer, cited
    GET /api/self-improve/contract?model=<name>   jarvis_ollama_contract.probe()

Both only read. The diagnosis reads this program's own source and asks the
LOCAL model; the contract route asks the local Ollama for `POST /api/show`,
which reads the model's own metadata and loads nothing. Neither writes a file,
approves anything, starts a program, or leaves this PC. There is NO POST route
and no route for `draft()`: a drafted change still has no way out of the box.

WHAT PHASE 4 DRAFTS, AND WHAT IT REFUSES

`draft()` returns a `Proposal` whose `ok` is False - with a reason in plain words
- unless the model produced an explanation, a `code_diff`, and a separate
`test_diff`. Section 5.1 and section 5.2 step 3 pull against each other (a test is
required, and a test file may not be touched), and the reading taken here is the
one that satisfies both:

  * the `code_diff` may never touch `jarvis_gate.py`, a tier or risk table, a
    test file, or the three SHIPPED lists. Any of those is a refusal;
  * the `test_diff` must CREATE A NEW TEST FILE (`--- /dev/null`). It can
    therefore add a test but can never weaken, edit or delete one that exists;
  * no test diff at all is "no test, no proposal".

`refusal_reason()` is the one function that decides, and it reads the boundary
off the diff TEXT itself - nothing is checked by asking the model whether it
obeyed. The suite drives it with diffs that exist only in the test.

WHAT THIS DELIBERATELY DOES NOT DO

  * It applies nothing, writes nothing and cards nothing, and there is no route
    for `draft()`. Phase 5 - applying a change with an approval card and a
    one-click undo - is still not here.
  * It does not read the owner's memory, mail, calendar or documents.
  * No app calls the two read-only GET routes: this is a PC-side diagnostic for
    the owner, and this slice adds no desktop or Android face. The routes are
    answered to any client that passes the core's own checks, and that is all
    that is claimed.

Standard library only. No import of a shipped module happens at import time: the
scrubber and the gate are imported inside the functions that need them, each
wrapped, so a backend without either still runs with this feature quietly off.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
#   What may be read, and how much of it
# --------------------------------------------------------------------------

#: Suffixes worth reading. A `.patch` is deliberately NOT one: `backend/` holds
#: hundreds of them, they are history rather than program, and letting them into
#: the evidence set would bury the real answer under four copies of it.
READ_SUFFIXES: Tuple[str, ...] = (
    ".py", ".md", ".json", ".ps1", ".tsv", ".toml", ".txt", ".js", ".kt", ".rs", ".html",
)

#: Folders never walked: generated, vendored, or another agent's checkout.
SKIP_DIRS = frozenset({
    "__pycache__", ".git", "node_modules", "patch-history", "videos",
    "brag-output", ".dsh-scratch", ".venv", "venv", "dist", "build",
})

#: A file bigger than this is skipped rather than read into memory. Every real
#: source file here is far under it; the point is that one runaway log cannot
#: turn a question into a stall.
MAX_FILE_BYTES = 512 * 1024

#: How much evidence one question may carry, and how much of it is quoted or
#: shown to the model. A single line here can be long (the Project Mode gate line
#: in `jarvis_hud.py` is over 400 characters), so the prompt truncates each line
#: rather than dropping any: a dropped line would break the numbering the model
#: cites by.
MAX_EVIDENCE = 8
MAX_QUOTE = 300
PROMPT_LINE_CHARS = 500

#: Words that carry no signal in a question about source. Kept short on purpose:
#: a word wrongly dropped is a line never found, which is the failure this module
#: exists to avoid, so only words that are certainly noise are here.
_STOP = frozenset({
    "the", "and", "for", "are", "was", "were", "does", "did", "why", "how",
    "what", "where", "when", "which", "who", "that", "this", "these", "those",
    "with", "from", "into", "not", "but", "can", "cannot", "could", "should",
    "would", "has", "have", "had", "its", "it", "is", "be", "been", "being",
    "a", "an", "of", "to", "in", "on", "at", "by", "or", "as", "if", "then",
    "than", "there", "here", "my", "me", "i", "you", "your", "jarvis",
    "work", "works", "working", "get", "got", "doesn", "don", "isn", "why's",
    "thing", "things", "something", "anything", "nothing", "someone", "anyone",
    "tell", "show", "give", "make", "makes", "made", "want", "need", "needs",
    "know", "think", "see", "look", "looks", "really", "actually", "ever",
    "about", "over", "under", "again", "still", "even", "much", "many", "some",
    "any", "all", "more", "most", "other", "another", "same", "only", "just",
    "first", "last", "next", "new", "old", "right", "wrong", "always", "never",
})

#: The program's own code outranks prose about it, as a tie-breaker only.
CODE_SUFFIXES = frozenset({".py", ".ps1", ".js", ".kt", ".rs", ".toml"})
CODE_BONUS = 5

#: A line that DEFINES a symbol the question names outranks a line that only
#: MENTIONS it. "Where is the taint latch written?" must put
#: `def latch_taint(...)` in the evidence, and comments that merely say the
#: name (a registration note, a caller's own comment) otherwise score the same
#: and win the tie on path order - measured 2026-10-17 on Pillar 16's branch:
#: two new comments naming `jarvis_gate.latch_taint` pushed the definition out
#: of the top eight for that question, and the real-tree check caught it.
#: Large enough to beat any mention-only combination of the question's words,
#: and it only ever moves a DEFINITION up: nothing is dropped, so the mentions
#: are still evidence when the budget has room for them.
DEFINITION_BONUS = 60

#: What a definition line starts with, in the languages this module reads:
#: `def name(`, `async def name(`, `class Name`, Rust's `fn name(` /
#: `pub fn name(`, Kotlin's `fun name(`. The name is captured, not the whole
#: line, because the question's words have to appear in the NAME for this to be
#: a definition OF what was asked about - a `def save_history(` line is not the
#: "history" answer a question about a different word asked for.
_DEFINITION_LINE = re.compile(
    r"^(?:(?:async\s+)?def|class|fn|pub\s+fn|fun)\s+([A-Za-z_][A-Za-z0-9_]*)")

#: A long run of characters with no space or tab in it is a blob (a base64
#: payload in a word list, a hash), not a line of source that can answer
#: anything. Measured: an invented word matched inside `jarvis_stopword.py`'s
#: encoded table, which is how a "no answer exists" question came back with
#: eight confident hits.
BLOB_MIN_CHARS = 80


def module_dir() -> Path:
    """The folder this module really runs from - the backend folder, on his PC."""
    return Path(__file__).resolve().parent


def default_roots() -> Tuple[Path, ...]:
    """The folders `retrieve()` reads when a caller names none.

    This module's own folder always, because on the owner's PC that IS the
    program (and it is where `_jarvis-logs/` sits). Then, ONLY when this really
    is a checkout of this repository, the folders the design's table allows
    beside it.

    The marker for "a checkout" is `../scripts/apply-patches.ps1`, and it is
    deliberately narrow: the owner's backend folder has no such sibling, and a
    backend that happens to sit inside some OTHER git repository of his must not
    have unrelated folders walked because of it.

    `jarvis-backend/` is included last rather than first: it is the published
    twin of `backend/`, duplicates are dropped by `retrieve()`, and putting it
    last means a line that exists in both is cited from `backend/` - the tree an
    editor is working in. It is kept at all because the entry point,
    `jarvis_hud.py`, exists ONLY there.
    """
    roots: List[Path] = [module_dir()]
    repo = module_dir().parent
    if not (repo / "scripts" / "apply-patches.ps1").is_file():
        return tuple(roots)
    for name in ("tools", "scripts", "docs", "features"):
        candidate = repo / name
        if candidate.is_dir():
            roots.append(candidate)
    # The few root documents that say what this program is supposed to be. Named
    # one by one rather than walking the root, which would pull the whole
    # checkout - both apps, every worktree - into a scan of the backend.
    for name in ("README.md", "CHANGELOG.md", "CLAUDE.md",
                 "JARVIS-SELF-IMPROVEMENT-DESIGN-FOR-REVIEW.md"):
        candidate = repo / name
        if candidate.is_file():
            roots.append(candidate)
    twin = repo / "jarvis-backend"
    if twin.is_dir():
        roots.append(twin)
    return tuple(roots)


# --------------------------------------------------------------------------
#   Evidence, and what comes back
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Evidence:
    """One real line, read from one real file. The only thing a claim can rest on.

    `path` is what the owner would type: relative to the backend folder, or to
    the repository root for a file outside it.
    """

    path: str
    line: int
    text: str
    score: int = 0

    @property
    def where(self) -> str:
        return f"{self.path}:{self.line}"

    def quoted(self) -> str:
        body = self.text.strip()
        if len(body) > MAX_QUOTE:
            body = body[:MAX_QUOTE] + " ... (line truncated when shown)"
        return body


@dataclass(frozen=True)
class Citation:
    """An evidence line, re-read from disk at the moment it is reported."""

    path: str
    line: int
    text: str

    @property
    def where(self) -> str:
        return f"{self.path}:{self.line}"

    def quoted(self) -> str:
        body = self.text.strip()
        if len(body) > MAX_QUOTE:
            body = body[:MAX_QUOTE] + " ... (line truncated when shown)"
        return body


@dataclass
class Diagnosis:
    """What one question got back. Read `found` before `answer`.

    `found` False means exactly "this PC could not establish it" - never a softer
    way of saying the same thing, and never an answer with no citation.
    """

    question: str
    found: bool
    answer: str = ""
    citations: Tuple[Citation, ...] = ()
    why: str = ""
    evidence: Tuple[Evidence, ...] = ()
    tainted: bool = False
    latched: bool = False
    model: str = ""

    @property
    def where(self) -> str:
        return self.citations[0].where if self.citations else ""


@dataclass
class Proposal:
    """A drafted change. NOTHING HERE IS APPLIED, and nothing can be.

    `ok` False is the ordinary outcome when the model could not draft something
    the boundary allows; `refusal` then says which rule stopped it, in words the
    owner can read.
    """

    question: str
    ok: bool
    explanation: str = ""
    code_diff: str = ""
    test_diff: str = ""
    citations: Tuple[Citation, ...] = ()
    refusal: str = ""
    evidence: Tuple[Evidence, ...] = ()
    tainted: bool = False
    latched: bool = False
    model: str = ""


# --------------------------------------------------------------------------
#   The scrubber and the gate - both optional, both fail closed
# --------------------------------------------------------------------------

def _scrubber():
    """`jarvis_scrub`, or None. Nothing is quoted without it.

    The same shape `jarvis_voiceprint.py:632` uses for the same reason: a
    scrubber that is missing must not mean "carry on unscrubbed".
    """
    try:
        import jarvis_scrub                                    # noqa: PLC0415
        return jarvis_scrub
    except Exception:                                          # noqa: BLE001
        return None


def _scrubbed(text) -> Optional[str]:
    """`text` scrubbed, or None when there is no scrubber to scrub it with.

    None is a REFUSAL, not an empty answer: see the module docstring. The
    scrubber itself never raises and withholds the whole text if it fails
    (`jarvis_scrub.scrub_text`), so the two failure modes end in the same place -
    nothing is read out.
    """
    scrub = _scrubber()
    if scrub is None:
        return None
    try:
        return scrub.scrub_text(text if text is not None else "")
    except Exception:                                          # noqa: BLE001
        return None


def _gate():
    """`jarvis_gate`, or None. Never imported at module import time."""
    try:
        import jarvis_gate                                     # noqa: PLC0415
        return jarvis_gate
    except Exception:                                          # noqa: BLE001
        return None


def _latch(why: str) -> bool:
    """Set the conversation's taint latch, if the gate is here. Never raises.

    `jarvis_gate.latch_taint` (`jarvis_gate.py:1772`) already returns False
    rather than raising when it cannot work, and this only passes that through.
    """
    gate = _gate()
    if gate is None:
        return False
    try:
        return bool(gate.latch_taint(why=why))
    except Exception:                                          # noqa: BLE001
        return False


#: Phrases in a QUESTION that mean it is about private material. Deliberately
#: broad: setting the latch only ever REFUSES an escalation, so a false positive
#: costs the owner a cloud offer he did not ask for, while a false negative could
#: carry his memory or a credential into one.
#:
#: The words are phrases ("my mail", "chat history") rather than bare nouns
#: ("mail", "notes") because this repository is full of prose about mail and
#: notes, and "is there a self-improvement design document?" latched on the word
#: "document" - a latch that fires on everything says nothing.
SENSITIVE_QUESTION_MARKERS: Tuple[str, ...] = (
    "memory", "remember", "my facts", "about me", "chat history", "transcript",
    "credential", "password", "passphrase", "api key", "keychain", "secret",
    "voiceprint", "voice print", "private", "personal",
    "my documents", "my files", "my folders", "my mail", "my email", "my inbox",
    "my calendar", "my notes", "my journal", "my photos", "my pictures",
    "my screen", "my clipboard", "my spending", "my bank", "my receipts",
)

#: Modules whose SOURCE is the owner's own material rather than the program's
#: plumbing. Reading one of these is reading his memory, his mail or his
#: documents, which is what the latch is for (design section 4.5).
SENSITIVE_SOURCES: Tuple[str, ...] = (
    "jarvis_memory", "jarvis_recall", "jarvis_past", "jarvis_entities",
    "jarvis_auto_learn", "jarvis_chat_log", "jarvis_paste_guard",
    "jarvis_sensitive", "jarvis_voice", "jarvis_style", "jarvis_documents",
    "jarvis_email", "jarvis_mail_mask", "jarvis_calendar", "jarvis_note",
    "jarvis_spending", "jarvis_receipts", "jarvis_credentials",
    "jarvis_token_store", "jarvis_owned_tables", "jarvis_projects",
    "jarvis_picture", "jarvis_screen", "jarvis_ocr", "jarvis_watch",
)


def is_sensitive(question: str, evidence: Sequence[Evidence] = ()) -> bool:
    """Does this question, or the source it read, touch private material?

    Pure and deterministic, so the suite can drive it without a model and
    without a gate. Two ways to be sensitive, both narrow enough to mean
    something: the question asks about private material, or a line was read out
    of a module that HOLDS it.
    """
    haystack = (question or "").lower()
    if any(marker in haystack for marker in SENSITIVE_QUESTION_MARKERS):
        return True
    for item in evidence:
        stem = Path(item.path).stem.lower()
        if any(stem.startswith(name) for name in SENSITIVE_SOURCES):
            return True
    return False


# --------------------------------------------------------------------------
#   Retrieval - the deterministic half
# --------------------------------------------------------------------------

def _tokens(question: str) -> Tuple[str, ...]:
    """The question's own words, lowercased, deduped, noise removed."""
    words = re.findall(r"[a-z0-9_]+", (question or "").lower())
    keep = {w for w in words if len(w) >= 3 and w not in _STOP}
    return tuple(sorted(keep))


def _patterns(tokens: Sequence[str]) -> Dict[str, "re.Pattern[str]"]:
    """One compiled pattern per question word: it must START a word.

    `backup` matches `backups` and `backup.patch`; `thing` does not match
    `nothing`. An UNDERSCORE is a separator, not a letter: this is snake_case
    code, and the whole point of the example that found this was that `taint`
    did not match inside `def latch_taint(...)` - the one line that answers the
    question. Compiled once per call: a pattern built per line was measured at
    several seconds on a tree this size.
    """
    return {t: re.compile(r"(?<![a-z0-9])" + re.escape(t)) for t in tokens}


def _hits(low: str, tokens: Sequence[str], patterns) -> List[str]:
    """Which question words this line really contains.

    The plain `in` test runs first because it is the cheap one and it is false
    for almost every line; only a line that contains the letters at all pays for
    the pattern.
    """
    found = []
    for token in tokens:
        if token in low and patterns[token].search(low):
            found.append(token)
    return found


def _weight(df: int) -> int:
    """What one word is worth, from the number of lines carrying it.

    A word that appears on almost every line says almost nothing; the line
    carrying a RARE word of the question is the one worth reading. Buckets rather
    than a formula, so the ranking can be explained in one sentence and cannot
    drift with a float.
    """
    if df <= 2:
        return 40
    if df <= 10:
        return 20
    if df <= 50:
        return 10
    if df <= 300:
        return 4
    if df <= 2000:
        return 2
    return 1


def _is_blob(line: str) -> bool:
    """A long unbroken run of characters: encoded data, not source."""
    return len(line) > BLOB_MIN_CHARS and " " not in line and "\t" not in line


def _definition_name(text: str) -> str:
    """The symbol this line DEFINES, or "" for a line that defines nothing.

    Only a real definition line at the START of the (stripped) line counts:
    prose that says `def latch_taint(` in a sentence is a mention, which is
    exactly the shape the definition bonus must not reward.
    """
    match = _DEFINITION_LINE.match(text.strip())
    return match.group(1) if match else ""


def _iter_files(roots: Iterable[Path]) -> Iterable[Path]:
    """Every readable text file under `roots`, in a fixed order.

    Sorted, so two runs and two machines read the same files in the same order:
    the ranking breaks ties by path, and a walk that returned files in filesystem
    order would make the evidence set machine-dependent.

    `SKIP_DIRS` is matched against the path RELATIVE to the root being walked,
    never against the absolute path. That is not tidiness: a checkout under
    `.dsh-scratch/` is how this repository is worked in parallel, and matching
    the absolute path made every file in such a worktree invisible - measured,
    with every question coming back "no line mentions this". The root itself is
    never skipped, so a log folder the owner points at is read even when its own
    name would be skipped anywhere deeper.
    """
    for root in roots:
        root = Path(root)
        if root.is_file():
            if root.suffix.lower() in READ_SUFFIXES:
                yield root
            continue
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in READ_SUFFIXES:
                continue
            try:
                parts = path.relative_to(root).parts
            except ValueError:
                parts = path.parts
            if any(part in SKIP_DIRS for part in parts):
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield path


def _read_lines(path: Path) -> List[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").split("\n")
    except OSError:
        return []


def _label(path: Path) -> str:
    """The path as the owner would type it.

    Relative to this module's own folder first - so on his PC a citation reads
    `jarvis_gate.py:1772`, with no fragment of his own folder name in it - and
    then relative to the repository root, which is what makes `tools/check_x.py`
    and `backend/x.py` distinguishable here.
    """
    for base in (module_dir(), module_dir().parent):
        try:
            return path.resolve().relative_to(base.resolve()).as_posix()
        except (ValueError, OSError):
            continue
    return path.name


def _resolve(label: str, roots: Sequence[Path]) -> Optional[Path]:
    """The file a citation label names, found the way `_label` wrote it."""
    candidates: List[Path] = []
    for root in roots:
        candidates.append(root if root.is_dir() else root.parent)
    candidates.append(module_dir())
    candidates.append(module_dir().parent)
    for base in candidates:
        candidate = base / label
        if candidate.is_file():
            return candidate
    return None


def retrieve(question: str, *, roots: Optional[Sequence[Path]] = None,
             limit: int = MAX_EVIDENCE) -> Tuple[Evidence, ...]:
    """The lines that really answer `question`, best first. No model, no network.

    A line scores the sum of its words' weights (rare words weigh more), plus a
    bonus for a word in the FILE NAME - a question about backups is more likely
    to be answered by `jarvis_backup.py` than by a comment that happens to say
    "backup" - plus a small bonus for the program's own code over prose about it,
    plus a DEFINITION bonus when the line defines a symbol the question names
    (`def latch_taint(` for "where is the taint latch written"). Without that
    last term a mention of the name scores the same as the definition and wins
    the tie on path order: two comments naming the latch were enough to push
    the definition out of the top eight (Pillar 16, 2026-10-17).
    Ranking is `(-score, path, line)`, which is total and deterministic: the same
    question against the same tree returns the same lines in the same order.

    Duplicates are dropped by (file name, whole line): `backend/x.py` and
    `jarvis-backend/x.py` are the same program twice, and letting both in would
    spend the evidence budget on the twin instead of on the answer.

    THIS MODULE'S OWN FILE IS NOT EVIDENCE. Its docstring is full of example
    questions, and a line that quotes the question back outranks the line that
    answers it - measured: "where is the taint latch written?" returned this
    file's own usage example first and the `def latch_taint` line not at all.
    The cost is real and accepted: this module cannot be diagnosed by itself.
    """
    tokens = _tokens(question)
    if not tokens:
        return ()
    where = tuple(Path(r) for r in (roots if roots is not None else default_roots()))
    patterns = _patterns(tokens)
    mine = Path(__file__).resolve()

    df: Dict[str, int] = {t: 0 for t in tokens}
    seen: set = set()
    found: List[Tuple[str, int, str, Tuple[str, ...], str]] = []
    for path in _iter_files(where):
        try:
            if path.resolve() == mine:
                continue
        except OSError:
            pass
        label = _label(path)
        name = path.name.lower()
        for number, line in enumerate(_read_lines(path), start=1):
            stripped = line.strip()
            if not stripped or _is_blob(stripped):
                continue
            hits = _hits(stripped.lower(), tokens, patterns)
            if not hits:
                continue
            # Dropped here, in WALK order, not after ranking: the sort is by
            # path, and the twin's label sorts first, so deduping later would
            # cite `jarvis-backend/x.py` for a line that is also in `backend/`.
            key = (name, stripped)
            if key in seen:
                continue
            seen.add(key)
            for token in hits:
                df[token] += 1
            found.append((label, number, stripped, tuple(hits), name))

    scored: List[Evidence] = []
    for label, number, text, hits, name in found:
        score = sum(_weight(df[token]) for token in hits)
        score += 2 * len(_hits(name, hits, patterns))
        if Path(label).suffix.lower() in CODE_SUFFIXES:
            score += CODE_BONUS
        defined = _definition_name(text)
        if defined and _hits(defined.lower(), hits, patterns):
            score += DEFINITION_BONUS
        scored.append(Evidence(path=label, line=number, text=text, score=score))
    scored.sort(key=lambda e: (-e.score, e.path, e.line))
    return tuple(scored[:max(1, int(limit))])


# --------------------------------------------------------------------------
#   The model - one seam, and it is loopback or it is nothing
# --------------------------------------------------------------------------

#: Where the local model lives when nothing says otherwise. The same default
#: `jarvis_ollama_contract.py:145` and `jarvis_thinking.py:210` use.
DEFAULT_URL = "http://127.0.0.1:11434"

#: Hosts that mean "this PC". Anything else is not used: this module's whole
#: reason for existing is the LOCAL model, and a diagnosis carries the owner's
#: own source text.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "0.0.0.0"})

#: `options.num_ctx` is always named. A `POST /api/generate` that names a model
#: and no `num_ctx` loads that model at Ollama's OWN default (2,048 on the
#: owner's install) rather than the lane's - measured in this repository on
#: 2026-10-10/11 and written up at `jarvis_agent.py:6229`. The evidence is capped
#: well under this, so the number is a floor for the prompt, not a claim about
#: the model.
DEFAULT_NUM_CTX = 8192


def _loopback_url(url: Optional[str] = None) -> str:
    """`url`, or `OLLAMA_HOST`, or loopback - and loopback if the host is not.

    A remote host is not refused with an exception: it simply is not used, and
    the caller gets the loopback default. Nothing in this module can be pointed
    at another machine by an environment variable.
    """
    for candidate in (url, os.environ.get("OLLAMA_HOST"), DEFAULT_URL):
        text = (candidate or "").strip()
        if not text:
            continue
        host = text.split("://", 1)[-1].split("/", 1)[0]
        if host.startswith("["):
            host = host[1:].split("]", 1)[0]
        else:
            host = host.split(":", 1)[0]
        if host.lower() in LOOPBACK_HOSTS:
            return text.rstrip("/")
    return DEFAULT_URL


def _model_name(model: Optional[str] = None) -> str:
    return str(model or os.environ.get("JARVIS_MODEL") or "qwen3.5:9b").strip()


def _run(prompt: str, *, model: Optional[str] = None, url: Optional[str] = None,
         timeout: float = 120.0) -> str:
    """Ask the LOCAL model. The reply, or "" - never raises, never remote.

    THIS IS THE SEAM. The suite replaces it (`M._run = fake`, the shape
    `backend/test_model_lanes.py:290` uses) or passes `ask=` to `diagnose()`;
    nothing in CI needs an Ollama to test any of the behaviour above this line.
    """
    where = _loopback_url(url)
    body = json.dumps({
        "model": _model_name(model),
        "prompt": prompt,
        "stream": False,
        "options": {"num_ctx": DEFAULT_NUM_CTX},
    }).encode("utf-8")
    try:
        request = urllib.request.Request(
            f"{where}/api/generate", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            payload = json.loads(answer.read().decode("utf-8"))
    except Exception:                                          # noqa: BLE001
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("response") or "")


# --------------------------------------------------------------------------
#   The reply protocol - the shape that makes a citation structural
# --------------------------------------------------------------------------

ANSWER_ANCHOR = "ANSWER:"
CITE_ANCHOR = "CITE:"
CANNOT_ANCHOR = "CANNOT:"
EXPLAIN_ANCHOR = "EXPLAIN:"
CODE_ANCHOR = "CODE_DIFF:"
TEST_ANCHOR = "TEST_DIFF:"
END_CODE_ANCHOR = "END_CODE_DIFF"
END_TEST_ANCHOR = "END_TEST_DIFF"

#: The instruction both prompts carry, spelled once. It is quoted in the suite,
#: so the protocol and the test cannot drift apart.
PROTOCOL = (
    "Answer ONLY from the numbered lines. Never write a fact that is not in one "
    "of them. Reply in exactly this shape:\n"
    "ANSWER: <what those lines show, at most four short lines>\n"
    "CITE: <the number of a line you used>\n"
    "CITE: <another number, if you used another>\n"
    "If the numbered lines do not answer the question, reply with one line:\n"
    "CANNOT: <what is missing>\n"
)

DRAFT_PROTOCOL = (
    "Draft a change using ONLY the numbered lines. Reply in exactly this shape:\n"
    "EXPLAIN: <what you would change and why, in plain words, at most four lines>\n"
    "CODE_DIFF:\n<one unified diff, in git format>\nEND_CODE_DIFF\n"
    "TEST_DIFF:\n<a unified diff that CREATES a new test file, starting --- /dev/null>\n"
    "END_TEST_DIFF\n"
    "CITE: <the number of a line you used>\n"
    "If you cannot draft it, reply with one line:\n"
    "CANNOT: <why>\n"
)


def _prompt_lines(evidence: Sequence[Evidence]) -> str:
    """The numbered evidence block. Each line is truncated, never dropped.

    Dropping a line would break the numbering the model cites by, which is the
    one thing the whole protocol rests on.
    """
    out = []
    for number, item in enumerate(evidence, start=1):
        text = item.text
        if len(text) > PROMPT_LINE_CHARS:
            text = text[:PROMPT_LINE_CHARS] + " ..."
        out.append(f"{number}) {item.where}: {text}")
    return "\n".join(out)


def build_prompt(question: str, evidence: Sequence[Evidence]) -> str:
    """The diagnosis prompt. Public so the suite can read what the model is told."""
    return (
        "You are reading Jarvis's own source code on the owner's PC.\n"
        f"Question: {question}\n\n"
        f"{PROTOCOL}\n"
        "The numbered lines are the only evidence:\n"
        f"{_prompt_lines(evidence)}\n"
    )


def build_draft_prompt(question: str, evidence: Sequence[Evidence]) -> str:
    """The drafting prompt. Same evidence, a diff-shaped answer."""
    return (
        "You are drafting a change to Jarvis's own source, for the OWNER to apply "
        "by hand. You cannot apply it and nothing you write is applied.\n"
        f"Question: {question}\n\n"
        f"{DRAFT_PROTOCOL}\n"
        "The numbered lines are the only evidence:\n"
        f"{_prompt_lines(evidence)}\n"
    )


def _canonical(raw: str) -> str:
    """One model reply as lines: CRLF and lone CR tolerated."""
    return (raw or "").replace("\r\n", "\n").replace("\r", "\n")


def parse_reply(raw: str) -> Tuple[str, Tuple[int, ...], str]:
    """(explanation, cited numbers, cannot-reason) from one model reply.

    Forgiving about the things a model gets wrong harmlessly (indentation, the
    anchor's case, a number written as "3." or "#3"), and strict about the one
    thing that matters: an index that is not a plain number is not a citation.
    """
    answer: List[str] = []
    cites: List[int] = []
    cannot = ""
    for line in _canonical(raw).split("\n"):
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith(CANNOT_ANCHOR):
            cannot = stripped[len(CANNOT_ANCHOR):].strip()
            continue
        if upper.startswith(CITE_ANCHOR):
            value = stripped[len(CITE_ANCHOR):].strip().lstrip("#").rstrip(".")
            if re.fullmatch(r"\d+", value):
                cites.append(int(value))
            continue
        if upper.startswith(ANSWER_ANCHOR):
            answer.append(stripped[len(ANSWER_ANCHOR):].strip())
            continue
        if upper.startswith(EXPLAIN_ANCHOR):
            answer.append(stripped[len(EXPLAIN_ANCHOR):].strip())
            continue
    return " ".join(part for part in answer if part).strip(), tuple(cites), cannot


def _section(raw: str, start: str, end: str) -> str:
    """The lines between `start` and `end` anchors, or "".

    A model that forgets the closing anchor does not get the rest of its own
    reply swallowed into a diff: the section also stops at any anchor that
    belongs to a later section, and at a second `start`.
    """
    text = _canonical(raw)
    begin = text.find(start)
    if begin < 0:
        return ""
    begin += len(start)
    stops = [text.find(mark, begin) for mark in
             (end, ANSWER_ANCHOR, EXPLAIN_ANCHOR, CODE_ANCHOR, TEST_ANCHOR, CITE_ANCHOR)]
    stops = [spot for spot in stops if spot >= 0]
    body = text[begin:min(stops)] if stops else text[begin:]
    return body.strip("\n").strip()


# --------------------------------------------------------------------------
#   Phase 3 - diagnose
# --------------------------------------------------------------------------

def _cite(evidence: Sequence[Evidence], numbers: Iterable[int],
          roots: Sequence[Path]) -> Tuple[Citation, ...]:
    """Turn cited NUMBERS into real quotes, re-read from disk now.

    A number outside the evidence list is dropped. The text is re-read rather
    than taken from the prompt, so what is reported is the file as it is at the
    moment of the answer.
    """
    out: List[Citation] = []
    for number in numbers:
        if not (1 <= number <= len(evidence)):
            continue
        item = evidence[number - 1]
        real = None
        found = _resolve(item.path, roots)
        if found is not None:
            lines = _read_lines(found)
            if 0 < item.line <= len(lines) and lines[item.line - 1].strip():
                real = lines[item.line - 1].strip()
        text = real if real is not None else item.text
        out.append(Citation(path=item.path, line=item.line, text=text))
    return tuple(out)


def diagnose(question: str, *, roots: Optional[Sequence[Path]] = None,
             model: Optional[str] = None, ask: Optional[Callable[[str], str]] = None,
             limit: int = MAX_EVIDENCE) -> Diagnosis:
    """Read the source, ask the local model to explain it, cite what it used.

    Never raises: a question this module cannot answer - no evidence, no
    scrubber, no model - comes back as `found=False` with the reason in `why`.
    `ask` is the model seam; without it `_run` is used, and `_run` is
    loopback-only.
    """
    where = tuple(Path(r) for r in (roots if roots is not None else default_roots()))
    try:
        evidence = retrieve(question, roots=where, limit=limit)
    except Exception as exc:                                   # noqa: BLE001
        return Diagnosis(question=question, found=False,
                         why=f"the source could not be searched ({type(exc).__name__})")

    sensitive = is_sensitive(question, evidence)
    latched = _latch("self_improve_diagnosis") if sensitive else False
    common = dict(evidence=evidence, tainted=sensitive, latched=latched,
                  model=_model_name(model))

    if not evidence:
        return Diagnosis(question=question, found=False,
                         why="no line in the program's own files mentions this, so "
                             "there is nothing to read out",
                         **common)

    if _scrubber() is None:
        return Diagnosis(question=question, found=False,
                         why="the scrubber is not available, so nothing was read out",
                         **common)

    prompt = build_prompt(question, evidence)
    runner = ask or (lambda p: _run(p, model=model))
    try:
        raw = runner(prompt) or ""
    except Exception as exc:                                   # noqa: BLE001
        return Diagnosis(question=question, found=False,
                         why=f"the local model could not be asked ({type(exc).__name__})",
                         **common)

    if not raw.strip():
        return Diagnosis(question=question, found=False,
                         why="the local model did not answer, so nothing was established",
                         **common)

    answer, numbers, cannot = parse_reply(raw)
    citations = _cite(evidence, numbers, where)
    if not citations:
        return Diagnosis(question=question, found=False,
                         why=cannot or "the model named no line it had read",
                         **common)

    clean = _scrubbed(answer)
    if clean is None:
        return Diagnosis(question=question, found=False,
                         why="the scrubber is not available, so nothing was read out",
                         **common)
    return Diagnosis(question=question, found=True, answer=clean,
                     citations=citations, **common)


def text(diagnosis: Diagnosis) -> str:
    """The plain rendering: the explanation over the real lines, or the refusal.

    A "could not establish" carries NO file:line at all, on purpose: it must not
    read like an answer with a citation attached. `diagnosis.evidence` holds the
    lines it read, for a caller that wants to show what was searched.
    """
    lines: List[str] = []
    if not diagnosis.found:
        lines.append(f"Could not establish this: {diagnosis.why}")
        if diagnosis.tainted:
            lines.append("(This question touches private material, so this "
                         "conversation is marked local-only for a while.)")
        return "\n".join(lines)
    if diagnosis.answer:
        clean = _scrubbed(diagnosis.answer)
        lines.append(clean if clean is not None else
                     "Could not establish this: the scrubber is not available.")
    for quote in diagnosis.citations:
        clean = _scrubbed(quote.text)
        if clean is None:
            lines.append(f"  {quote.where}: (not shown - the scrubber is not available)")
            continue
        shown = clean.strip()
        if len(shown) > MAX_QUOTE:
            shown = shown[:MAX_QUOTE] + " ... (line truncated when shown)"
        lines.append(f"  {quote.where}: {shown}")
    if diagnosis.tainted:
        lines.append("(This question touches private material, so this "
                     "conversation is marked local-only for a while.)")
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   Phase 4 - draft, and the boundary that decides what may be drafted
# --------------------------------------------------------------------------

#: Files a drafted `code_diff` may never touch, by name. Every one is here for a
#: sentence in the design's section 5.1 table, and the suite proves each name
#: really is the thing it is listed as.
PROTECTED: Tuple[str, ...] = (
    "jarvis_gate.py",        # "Modify jarvis_gate.py, the approval path"
    "apply-patches.ps1",     # "Change $PATCHES, $SHIPPED, or the three lists"
    "_where.py",             # the other end of the same three lists
)

#: Files that hold a tier or risk table - "any tier/risk table" in section 5.1.
#: Each is the table's OWN definition site (`_RANK`/`_VALID_TIERS`), or the
#: settings file the tier values are read from. The suite pins these names
#: against the source, so a table that is renamed is caught rather than silently
#: unprotected.
TIER_TABLE_NAMES: Tuple[str, ...] = (
    "jarvis_gate.py",              # the action -> tier table, _RANK, _VALID_TIERS
    "jarvis_content_risk.py",      # _RANK
    "jarvis_preview.py",           # _RANK
    "jarvis_injection.py",         # _RANK
    "jarvis_browser_control.py",   # _INJECTION_RANK
    "jarvis_arbiter.py",           # _PRI_RANK
    "jarvis-framework.toml",       # [autonomy.tiers]
)

#: A test file by name anywhere in the tree. Section 5.1: the model may not
#: "Disable, weaken or delete a test".
TEST_FILE_RE = re.compile(r"(^|/)test_[^/]*\.py$")

#: A unified diff names its files in `--- a/...` and `+++ b/...` lines. The `+++`
#: side is the one `git apply` anchors on, and the one read here.
_DIFF_TARGET_RE = re.compile(r"^\+\+\+[ \t]+(?:[ab]/)?([^\t\n]+)", re.MULTILINE)
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@", re.MULTILINE)


def diff_targets(diff_text: str) -> Tuple[str, ...]:
    """The files a unified diff touches, `a/` and `b/` prefixes removed.

    Read from the `+++` lines. A `+++ /dev/null` line names nothing and is
    skipped: a diff that DELETES a file is then judged on the file it came from,
    which the `creates_new_file` rule handles for the test side.
    """
    seen: List[str] = []
    for match in _DIFF_TARGET_RE.finditer(_canonical(diff_text)):
        target = match.group(1).strip()
        if not target or target == "/dev/null":
            continue
        if target not in seen:
            seen.append(target)
    return tuple(seen)


def is_diff(diff_text: str) -> bool:
    """Does this really look like a unified diff? A hunk header must be present."""
    return bool(diff_text.strip()) and bool(diff_targets(diff_text)) \
        and bool(_HUNK_RE.search(_canonical(diff_text)))


def creates_new_file(diff_text: str) -> bool:
    """A diff that ADDS a file says so with `--- /dev/null`."""
    return bool(re.search(r"^---[ \t]+/dev/null", _canonical(diff_text), re.MULTILINE))


def refusal_reason(code_diff: str, test_diff: str) -> str:
    """Why this pair of diffs may not be offered, or "" when it may.

    The one function that decides, so the suite drives the boundary with diffs
    that exist only in the test. The rules, in the order they are checked:

      1. the code diff must be a real diff, naming at least one file;
      2. no diff at all may touch `PROTECTED` or a tier table - the boundary in
         the design's section 5.1;
      3. the code diff may not touch a test file: a model that edits tests can
         make a wrong change pass;
      4. the test diff must be a real diff that CREATES a new test file, so it
         can carry the test the change needs without weakening one that exists.

    Nothing is checked by asking the model whether it obeyed. These are read off
    the diff text itself.
    """
    if not is_diff(code_diff):
        return "no code diff was drafted"
    if not is_diff(test_diff):
        return "no test was drafted, and a change with no test is not offered"
    targets = diff_targets(code_diff) + diff_targets(test_diff)
    for target in targets:
        name = Path(target).name
        if name in PROTECTED:
            return (f"{name} is outside what may be changed by a draft: the gate, "
                    f"the approval path and the shipped lists are not the model's to edit")
        if name in TIER_TABLE_NAMES:
            return (f"{name} holds a tier or risk table, which decides what needs "
                    f"an approval card, so it is never part of a draft")
    for target in diff_targets(code_diff):
        if TEST_FILE_RE.search(target):
            return (f"{target} is a test file: a draft may add a test, never change "
                    f"one, or a wrong change could make itself pass")
    test_targets = diff_targets(test_diff)
    if not test_targets:
        return "the test diff names no file"
    for target in test_targets:
        if not TEST_FILE_RE.search(target):
            return f"{target} is not a test file, so that diff is not a test"
    if not creates_new_file(test_diff):
        return ("the test must be a NEW file (--- /dev/null); editing an existing "
                "test can weaken it, which is what this boundary forbids")
    return ""


def draft(question: str, *, roots: Optional[Sequence[Path]] = None,
          model: Optional[str] = None, ask: Optional[Callable[[str], str]] = None,
          limit: int = MAX_EVIDENCE) -> Proposal:
    """Draft a change and the test for it. IT IS NOT APPLIED - nothing here applies.

    A refusal is an ordinary result, not an error: `ok` is False and `refusal`
    says which rule stopped it. The ways to be refused are the boundary (a
    protected file, a tier table, an existing test), a missing test, and a model
    that could not draft at all.
    """
    where = tuple(Path(r) for r in (roots if roots is not None else default_roots()))
    try:
        evidence = retrieve(question, roots=where, limit=limit)
    except Exception as exc:                                   # noqa: BLE001
        return Proposal(question=question, ok=False,
                        refusal=f"the source could not be searched ({type(exc).__name__})")

    sensitive = is_sensitive(question, evidence)
    latched = _latch("self_improve_draft") if sensitive else False
    common = dict(evidence=evidence, tainted=sensitive, latched=latched,
                  model=_model_name(model))

    if not evidence:
        return Proposal(question=question, ok=False,
                        refusal="no line in the program's own files mentions this, "
                                "so there is nothing to draft from", **common)
    if _scrubber() is None:
        return Proposal(question=question, ok=False,
                        refusal="the scrubber is not available, so nothing was drafted",
                        **common)

    prompt = build_draft_prompt(question, evidence)
    runner = ask or (lambda p: _run(p, model=model))
    try:
        raw = runner(prompt) or ""
    except Exception as exc:                                   # noqa: BLE001
        return Proposal(question=question, ok=False,
                        refusal=f"the local model could not be asked ({type(exc).__name__})",
                        **common)
    if not raw.strip():
        return Proposal(question=question, ok=False,
                        refusal="the local model did not answer, so nothing was drafted",
                        **common)

    explanation, numbers, cannot = parse_reply(raw)
    if cannot:
        return Proposal(question=question, ok=False,
                        refusal=f"the model could not draft this: {cannot}", **common)

    code_diff = _section(raw, CODE_ANCHOR, END_CODE_ANCHOR)
    test_diff = _section(raw, TEST_ANCHOR, END_TEST_ANCHOR)
    if not explanation.strip():
        return Proposal(question=question, ok=False,
                        refusal="no explanation came back with the draft", **common)

    stop = refusal_reason(code_diff, test_diff)
    if stop:
        return Proposal(question=question, ok=False, refusal=stop,
                        citations=_cite(evidence, numbers, where), **common)

    clean_explanation = _scrubbed(explanation)
    clean_code = _scrubbed(code_diff)
    clean_test = _scrubbed(test_diff)
    if clean_explanation is None or clean_code is None or clean_test is None:
        return Proposal(question=question, ok=False,
                        refusal="the scrubber is not available, so nothing was drafted",
                        **common)
    return Proposal(question=question, ok=True, explanation=clean_explanation,
                    code_diff=clean_code, test_diff=clean_test,
                    citations=_cite(evidence, numbers, where), **common)


def proposal_text(proposal: Proposal) -> str:
    """The draft as the owner would read it: what it does, then the lines."""
    lines: List[str] = []
    if not proposal.ok:
        lines.append(f"Not drafted: {proposal.refusal}")
        if proposal.tainted:
            lines.append("(This question touches private material, so this "
                         "conversation is marked local-only for a while.)")
        return "\n".join(lines)
    lines.append(proposal.explanation)
    lines.append("")
    lines.append("The change it would make (nothing is applied):")
    lines.append(proposal.code_diff)
    lines.append("")
    lines.append("The test that would fail without it (a new file):")
    lines.append(proposal.test_diff)
    for quote in proposal.citations:
        clean = _scrubbed(quote.text)
        if clean is None:
            continue
        lines.append(f"  {quote.where}: {clean.strip()[:MAX_QUOTE]}")
    lines.append("")
    lines.append("Nothing was changed. This is a draft for you to apply by hand.")
    return "\n".join(lines)


# --------------------------------------------------------------------------
#   The route - two READ-ONLY GETs, added 2026-10-17
#
#   This is the wiring queue's own item (the master guide's Part III.1 item 3):
#   the merged self-diagnosis and Ollama-contract libraries had no caller an
#   owner could reach. `install()` below is the call the drop-in folder
#   `plugins/ready/self-improve/` makes - exactly the shape
#   jarvis_receipts.install and jarvis_vault.install use, and the reason this
#   feature needs no patch at all.
#
#   The boundary is the ABSENCE of things, and it is the point:
#
#     * GET only. `do_GET` is wrapped and `do_POST`, `do_PUT` and the rest are
#       never touched, so a caller cannot turn a read into a write. There is no
#       route for draft(): applying a change stays Phase 5 and is not here.
#     * The two routes read. `diagnose()` reads this program's own source and
#       asks the LOCAL model; `jarvis_ollama_contract.probe()` makes ONE
#       read-only POST to the local Ollama's `/api/show`. Nothing writes a file,
#       approves anything, starts a program or leaves this PC.
#     * No raw evidence line is returned. `diagnose()` scrubs its answer, and
#       the citations are scrubbed HERE before they are serialised: their
#       `text` field is the line as re-read from disk, and returning it raw
#       would be a second display path with one fewer guard than `text()` has.
# --------------------------------------------------------------------------

#: The two routes this module answers. Only these exact paths are handled;
#: every other path, including another feature's, goes straight to the core's
#: own do_GET untouched.
DIAGNOSE_PATH = "/api/self-improve/diagnose"
CONTRACT_PATH = "/api/self-improve/contract"
PATHS = frozenset((DIAGNOSE_PATH, CONTRACT_PATH))

#: How long a question may be, in characters. A question is a sentence and 500
#: characters is far more than one; a longer one is refused rather than read.
#: This is a limit, not a timing: nothing here is measured per answer.
MAX_QUESTION_CHARS = 500


def _quiet(line: str) -> None:
    """The probe's log seam for the route.

    `probe()` normally writes one line to the backend's own stderr the first
    time it sees a finding. Called from a route, that sentence is already in
    the answer, so it is not written a second time.
    """
    return None


def _query_values(query: str) -> dict:
    """The query string's values, the way every other route reads them."""
    from urllib.parse import parse_qs
    try:
        return parse_qs(str(query or ""), keep_blank_values=True)
    except Exception:                                          # noqa: BLE001
        return {}


def _one(values) -> str:
    """The first value of a repeated query key, trimmed; "" when there is none."""
    return str(values[0]).strip() if values else ""


def _asked(query: str):
    """(question, None), or ("", (400, refusal)) for a question that is refused.

    Empty and over-long are the two refusals, and both are decided BEFORE the
    source is searched or a model is asked: a bad request must cost nothing.
    """
    question = _one(_query_values(query).get("q"))
    if not question:
        return "", (400, {
            "ok": False,
            "error": "question is empty",
            "message": ("ask a question about the program's own source, for example "
                        "GET /api/self-improve/diagnose?q=where+is+the+taint+latch+written"),
        })
    if len(question) > MAX_QUESTION_CHARS:
        return "", (400, {
            "ok": False,
            "error": "question is too long",
            "message": (f"a question longer than {MAX_QUESTION_CHARS} characters is "
                        f"refused, and nothing was read; this route reads the "
                        f"program's own source, it is not a chat"),
        })
    return question, None


def _citation_view(citation: Citation) -> dict:
    """One citation as JSON: the scrubber's output, or a plain withholding note.

    The scrubber runs HERE because `Citation.text` is the line re-read from
    disk, not the explanation. `text()` scrubs at display time, and a route
    that serialised the raw field would be a second display path with one
    fewer guard.
    """
    clean = _scrubbed(citation.text)
    out = {"path": citation.path, "line": citation.line,
           "where": citation.where, "quote": ""}
    if clean is None:
        out["withheld"] = "the scrubber is not available, so the line was not read out"
        return out
    shown = clean.strip()
    if len(shown) > MAX_QUOTE:
        shown = shown[:MAX_QUOTE] + " ... (line truncated when shown)"
    out["quote"] = shown
    return out


def _diagnosis_view(question: str, diagnosis: Diagnosis) -> dict:
    """`Diagnosis` as JSON - the fields the dataclass gives, and no more.

    `evidence` is deliberately NOT here: those lines were never scrubbed, so
    serialising them would expose more than `text()` allows. `found` False is
    an ordinary answer ("this PC could not establish it"), not a route failure,
    so `ok` stays true and `why` says what happened in plain words.
    """
    return {
        "ok": True,
        "read_only": True,
        "route": "diagnose",
        "question": question,
        "found": bool(diagnosis.found),
        "answer": diagnosis.answer if diagnosis.found else "",
        "citations": ([_citation_view(c) for c in diagnosis.citations]
                      if diagnosis.found else []),
        "why": "" if diagnosis.found else diagnosis.why,
        "tainted": bool(diagnosis.tainted),
        "latched": bool(diagnosis.latched),
        "model": diagnosis.model,
        "words": text(diagnosis),
    }


def _answer_diagnose(query: str, *, ask=None) -> tuple:
    """(200, the diagnosis) for a question that may be asked; else the refusal."""
    question, refusal = _asked(query)
    if refusal is not None:
        return refusal
    return 200, _diagnosis_view(question, diagnose(question, ask=ask))


def _answer_contract(query: str, *, ask_ollama=None) -> tuple:
    """(200, the contract report) or (503, why it could not be read at all).

    A missing `model=` uses the module's own default - the same model a
    diagnosis would ask (`JARVIS_MODEL`, else `qwen3.5:9b`).
    """
    model = _one(_query_values(query).get("model")) or _model_name(None)
    try:
        import jarvis_ollama_contract as contract       # noqa: PLC0415
    except Exception:                                   # noqa: BLE001
        return 503, {
            "ok": False,
            "error": "the Ollama contract module is not installed",
            "message": ("jarvis_ollama_contract.py is not in this backend, so the "
                        "contract cannot be read; nothing was changed"),
        }
    # `_loopback_url()` with no argument checks OLLAMA_HOST and falls back to
    # loopback, so this route cannot be pointed at another machine either.
    report = contract.probe(model, url=_loopback_url(), ask=ask_ollama,
                            log=_quiet, when="self-improve route")
    return 200, {
        "ok": True,
        "read_only": True,
        "route": "contract",
        "model": report.model,
        "url": report.url,
        "verdict": report.verdict,
        "usable": bool(report.usable),
        "said": list(report.said) if report.said is not None else None,
        "unknown": list(report.unknown),
        "missing": list(report.missing),
        "note": report.note,
        "when": report.when,
        "words": contract.text(report),
    }


def handle_get(route: str, query: str = "", *, ask=None, ask_ollama=None) -> tuple:
    """(status, JSON object) for one route - the route's whole answer, no socket.

    Public so the suite drives every refusal and every outcome without a
    handler and without an Ollama; `install()` is the only caller in the
    backend. `ask` and `ask_ollama` are the same seams `diagnose()` and
    `probe()` already expose, not new behaviour.
    """
    if route == DIAGNOSE_PATH:
        return _answer_diagnose(query, ask=ask)
    if route == CONTRACT_PATH:
        return _answer_contract(query, ask_ollama=ask_ollama)
    return 404, {
        "ok": False,
        "error": "no such route",
        "message": (f"this module answers two read-only GET routes: "
                    f"{DIAGNOSE_PATH} and {CONTRACT_PATH}"),
    }


#: One plain sentence for a request that did not come from this PC. The
#: route is a diagnostic OF this PC's own source, so another device learns
#: nothing - not even whether a file exists.
NOT_THIS_PC = ("Reading Jarvis's own source is for this PC only, so nothing "
               "was read.")


def _from_this_pc(peer, local) -> bool:
    """Is this request from this PC? Fails CLOSED: no helper, no answer.

    The same rule `jarvis_brain_reads._from_this_pc` uses: the project's one
    answer (`jarvis_owner_check.from_this_pc`) treats loopback and this PC's
    own addresses as here, so a program on the PC can ask and a phone on the
    same private network cannot.
    """
    try:
        import jarvis_owner_check
        return bool(jarvis_owner_check.from_this_pc(peer, local))
    except Exception:
        return False


def install(handler_cls, *, origin_ok, token_ok, read_body) -> str:
    """Wrap `handler_cls.do_GET` so the two read-only diagnostic routes are
    answered here, after the server's own origin and token checks - and only
    for THIS PC's own requests, refused 403 before the module reads anything.

    Every other request goes straight to the original do_GET. `do_POST` is NOT
    wrapped, because both routes read and a read must not be reachable by POST.
    The same shape jarvis_receipts.install and jarvis_vault.install use - and
    the reason this feature needs no patch: `plugins/ready/self-improve/plugin.json`
    names this module and `jarvis_plugins.py` makes the call the patch would
    have made.

    `read_body` is accepted because every install() takes the core's three
    callbacks; a GET route has no body to read, and this one reads none.
    """
    from urllib.parse import urlsplit
    del read_body  # a GET route has no body; accepted for the loader's shape

    get0 = handler_cls.do_GET
    if getattr(get0, "_jarvis_self_improve", False):
        return "  self-improve   read-only diagnosis and Ollama contract (already on)"

    def _allowed(self) -> bool:
        try:
            if not origin_ok(self):
                self._send(403, {"error": "cross-origin request refused"})
                return False
            if not token_ok(self):
                self._send(401, {"error": "bad or missing X-Jarvis-Token"})
                return False
        except Exception:                                   # noqa: BLE001
            self._send(401, {"error": "bad or missing X-Jarvis-Token"})
            return False
        return True

    def do_GET(self):
        parts = urlsplit(str(getattr(self, "path", "") or ""))
        route = parts.path.rstrip("/")
        if route not in PATHS:
            return get0(self)
        if not _allowed(self):
            return None
        peer, local = _peer_local(self)
        # This PC only, BEFORE any file is read: another device is refused
        # with one sentence and learns nothing. The same owner rule the
        # guardian and selection routes use.
        if not _from_this_pc(peer, local):
            return self._send(403, {
                "ok": False,
                "read_only": True,
                "error": "not_this_pc",
                "message": NOT_THIS_PC,
            })
        try:
            code, out = handle_get(route, parts.query)
        except Exception as exc:                            # noqa: BLE001
            # The exception's NAME only. Nothing in the answer is a traceback,
            # and the owner is told plainly that nothing changed.
            code, out = 503, {
                "ok": False,
                "error": type(exc).__name__,
                "message": "the diagnostic could not be completed, and nothing was changed",
            }
        return self._send(code, out)

    def _peer_local(self) -> tuple:
        """(peer, local) for this request, best effort; the owner check fails
        CLOSED when they cannot be had (jarvis_owner_check's own rule)."""
        peer = local = None
        try:
            peer = self.client_address[0]
        except Exception:
            pass
        try:
            local = self.connection.getsockname()[0]
        except Exception:
            pass
        return peer, local

    do_GET._jarvis_self_improve = True
    handler_cls.do_GET = do_GET
    return "  self-improve   read-only diagnosis and Ollama contract: on"
