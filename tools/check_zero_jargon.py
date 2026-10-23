#!/usr/bin/env python3
"""Review #8 - the zero-jargon user-facing string scanner.

    python3 tools/check_zero_jargon.py                     # report mode (exit 0)
    python3 tools/check_zero_jargon.py --check             # baseline ratchet (0/1)
    python3 tools/check_zero_jargon.py --report PATH       # write JSON (machine-readable)

WHY THIS EXISTS. The owner is a beginner developer, and every refusal, warning
and status line in Jarvis is written for them - but the code that writes those
lines is developer code, and developer words leak into them: an exception class
name, ``HTTP 500``, a config key, a module name, ``null``/``None``/``NaN``, the
word ``taint`` or ``latch`` from an internal state machine. The 2026-10-23
10-Review Playbook (Review #8, "Zero-Jargon Beginner Readability & Error-
Recovery Scanner") asks for exactly this check, and the ruling makes it the
cheap first post-deploy fix. This is that check, built so it can be trusted
before it is used to judge anything:

  * it finds **candidate user-facing strings** on the three product surfaces and
    reports every developer word inside them, with the exact path:line, the
    word, and the string, in a machine-readable report;
  * it does **not** claim the tree is clean. The opening measurement is a real
    number recorded in ``docs/REVIEW-8-ZERO-JARGON-BASELINE-2026-10-23.json``
    and ``docs/REVIEW-8-ZERO-JARGON-2026-10-23.md``; cleaning the strings is a
    separate, follow-up piece of work (this tool's first job is to make the list
    visible);
  * ``--check`` is a **ratchet**: it fails only when the tree gains MORE jargon
    than the recorded baseline, so it can run in CI now, before the cleanup.
    When the cleanup lowers the count, regenerate the baseline downward.

WHAT IS SCANNED (the three product surfaces)

  backend   the shipped backend modules (``backend/_where.py``'s ``SHIPPED``
            list, ``rebuilt/`` entries included) - the strings the HUD, the
            phone and the desktop are shown in an answer, a refusal or a card.
            Only string LITERALS on user-facing context lines are read;
            docstrings and comments are developer text and are skipped.
  hud       ``jarvis-desktop/src/jarvis_hud.html`` (visible text nodes and the
            JS literals that reach ``textContent``/``innerHTML``/``title``/
            ``placeholder``/``say(``/``alert(``/an error key) and the page's
            ``hud-*.js`` modules.
  rust      user-facing error strings in ``jarvis-desktop/src-tauri/src`` -
            ``Err(format!(...))`` and ``words``/``title``/``message``/``refusal``
            values - not internal log lines.
  android   ``jarvis-client`` resource strings (``res/values*/strings.xml``,
            all of them - every resource string is user-facing by definition)
            and Compose literals on ``Text(``/``stringResource(``/``label =``/
            ``title =``/``message =``/``error =``/``placeholder =``/Toast/
            Snackbar/``contentDescription =`` lines.

WHAT IS A "DEVELOPER WORD". The rules live in ``TERM_RULES`` below: the internal
state vocabulary (``taint``, ``untainted``, ``latch``, ``digest_mismatch``,
``from_this_pc``), the search/ML stack (``FTS5``, ``BM25``, ``RRF``, ``ONNX``,
``WAL``, ``shard``, ``corpus``, ``daemon``, ``mutex``, ``semaphore``), module
names (``jarvis_*.py``), snake_case config keys, exception class names,
``traceback``, and the developer words the work order names (``null``, ``None``,
``NaN``, ``undefined``, ``API``, ``localhost``, ``loopback``, ``HTTP``,
``socket``, ``stdout``, ``stderr``, ``errno``, ``sqlite``, ``payload``,
``stack``), HTTP status codes written into user text (``HTTP 500``, ``status
422`` - a bare ``500`` is not flagged because ``$500`` is money), and raw JSON
fragments. Matching is whole-word and, where a word is also an ordinary English
word, case-sensitive on purpose (``None`` the Python value, not "none of").

THE ALLOWLIST (``tools/zero-jargon-allow.txt``) is for technical words the
owner has deliberately chosen to see and already understands: model names
(``Ollama``, ``qwen``, ``llama``, ...), ``HTTPS``, ``PIN``, ``Tailscale``,
``Meshnet``, ``VPN``, hardware names, ``API key``. A line with a space is a
whole phrase (case-insensitive substring, e.g. ``API key``) and removes that
phrase from the analysed text before matching, so the phrase passes while a
bare ``API`` elsewhere still fails; a single word allows that whole word
everywhere. Entries are one per line, ``#`` starts a comment.

REPORT #2 OF REVIEW 8 - THE ACTIONABLE-RECOVERY RULE. Every refusal should say
what happened AND what to click/do next; a bare ``"Failed"``/``"Invalid
request"`` is not a refusal a beginner can act on. This scanner reports those
separately as **bare refusals** (``bare_refusals`` in the JSON, shown in the
summary). It does not try to judge whether the advice is correct - that needs a
person - but it makes the bare ones countable.

EXIT CODES
    0  report mode finished; or ``--check``: the tree is at or below baseline
    1  ``--check``: the tree gained jargon or bare refusals over the baseline,
       or a surface file could not be read (never silent)
    2  the scanner itself cannot run: bad arguments, missing/invalid baseline,
       or a root that does not look like this repository

WHERE IT RUNS. Registered as an audit-job step in ``.github/workflows/ci.yml``
(``python3 ../../tools/check_zero_jargon.py --check``), so the ratchet is
visible in CI, and its own suite is named by a row in ``docs/CLAIMS.tsv``
(``test:backend/test_zero_jargon.py``), which the required ``backend`` job runs
through ``backend/run_suites.py``. It is NOT registered as a required "zero
jargon" gate: the tree is not clean yet, and a gate that must start red would
be ignored or switched off - the recorded baseline is what makes it real now.

The hermetic bite tests are ``backend/test_zero_jargon.py`` (a planted
``Traceback`` must be found; allowlisted words must pass; the real tree is
measured, never asserted to zero until the cleanup lands).
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
import warnings
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_ALLOWLIST = REPO / "tools" / "zero-jargon-allow.txt"
DEFAULT_BASELINE = REPO / "docs" / "REVIEW-8-ZERO-JARGON-BASELINE-2026-10-23.json"
BASELINE_VERSION = 1
TOOL_NAME = "check_zero_jargon.py"
REVIEW = "Review #8 - zero-jargon beginner readability"

# ---------------------------------------------------------------------------
#   The developer words
# ---------------------------------------------------------------------------
# (category, canonical word for the report, whole-word pattern). Order matters:
# the first rule whose span is used wins, so a specific compound
# (taint_latched) is checked before its parts (taint, latch). A pattern ending
# in a word boundary and starting with one is a whole word, not a substring -
# "API" does not match inside "CAPITAL", "null" does not match "nullify".
TERM_RULES = (
    ("internal_state", "taint_latched", re.compile(r"\btaint_latched\b")),
    ("internal_state", "rush_latched", re.compile(r"\brush_latched\b")),
    ("internal_state", "digest_mismatch", re.compile(r"\bdigest_mismatch\b")),
    ("internal_state", "from_this_pc", re.compile(r"\bfrom_this_pc\b")),
    ("internal_state", "untainted", re.compile(r"\buntainted\b", re.I)),
    ("internal_state", "taint", re.compile(r"\btaint(?:ed|s)?\b", re.I)),
    ("internal_state", "latch", re.compile(r"\blatch(?:es|ed)?\b", re.I)),
    ("search_and_ml", "FTS5", re.compile(r"\bfts5\b", re.I)),
    ("search_and_ml", "BM25", re.compile(r"\bbm25\b", re.I)),
    ("search_and_ml", "RRF", re.compile(r"\brrf\b", re.I)),
    ("search_and_ml", "ONNX", re.compile(r"\bonnx\b", re.I)),
    ("search_and_ml", "WAL", re.compile(r"\bwal\b", re.I)),
    ("search_and_ml", "shard", re.compile(r"\bshards?\b", re.I)),
    ("search_and_ml", "corpus", re.compile(r"\bcorpus\b|\bcorpora\b", re.I)),
    ("search_and_ml", "daemon", re.compile(r"\bdaemons?\b", re.I)),
    ("search_and_ml", "mutex", re.compile(r"\bmutex(?:es)?\b", re.I)),
    ("search_and_ml", "semaphore", re.compile(r"\bsemaphores?\b", re.I)),
    ("module_name", "jarvis module", re.compile(r"\bjarvis_[a-z0-9_]+(?:\.py)?\b")),
    ("config_key", "config key", re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")),
    ("exception", "exception class",
     re.compile(r"\b[A-Z][A-Za-z0-9]*(?:Error|Exception)\b")),
    ("traceback", "traceback", re.compile(r"\btraceback\b", re.I)),
    ("dev_word", "null", re.compile(r"\bnull\b", re.I)),
    ("dev_word", "None", re.compile(r"\bNone\b")),
    ("dev_word", "NaN", re.compile(r"\bNaN\b")),
    ("dev_word", "undefined", re.compile(r"\bundefined\b", re.I)),
    ("dev_word", "API", re.compile(r"\bAPI\b")),
    ("dev_word", "localhost", re.compile(r"\blocalhost\b", re.I)),
    ("dev_word", "loopback", re.compile(r"\bloopback\b", re.I)),
    ("dev_word", "HTTP", re.compile(r"\bHTTP\b")),
    ("dev_word", "socket", re.compile(r"\bsockets?\b", re.I)),
    ("dev_word", "stdout", re.compile(r"\bstdout\b", re.I)),
    ("dev_word", "stderr", re.compile(r"\bstderr\b", re.I)),
    ("dev_word", "errno", re.compile(r"\berrno\b", re.I)),
    ("dev_word", "sqlite", re.compile(r"\bsqlite3?\b", re.I)),
    ("dev_word", "payload", re.compile(r"\bpayloads?\b", re.I)),
    ("dev_word", "stack", re.compile(r"\bstack\b", re.I)),
    ("http_status", "HTTP status code",
     re.compile(r"\b(?:HTTP|status(?:\s+code)?|code|error)\s*[:#]?\s*[45]\d\d\b", re.I)),
)

#: Bare refusals Review 8's second half names: a message that says neither what
#: happened (in plain words) nor what to do next. Exact short forms only - a
#: sentence is not bare, even when it is unhelpful.
BARE_REFUSALS = frozenset({
    "failed", "error", "invalid", "invalid request", "invalid input",
    "bad request", "not found", "unavailable", "denied", "refused",
    "unknown error", "something went wrong", "operation failed",
    "request failed", "no", "none", "null",
})

#: A SQL statement is never read by a person - it is code text that can sit on
#: a marked line (a database helper next to an error dict). Not user-facing.
SQL_ISH = re.compile(
    r"^\s*(?:SELECT|UPDATE|INSERT|DELETE|CREATE|ALTER|DROP|PRAGMA|WITH|"
    r"WHERE|FROM|SET|AND|OR|ORDER|GROUP|LIMIT|JOIN|VALUES)\b", re.I)
SQL_FRAGMENT = re.compile(r"=\?|\bIS\s+(?:NOT\s+)?NULL\b", re.I)

#: Structural words that are dict/JSON KEYS rather than messages. A key named
#: "error" is not a sentence the owner reads; it is the label the message is
#: filed under. Scanning it as text produced one "bare refusal" per dict in the
#: first draft of this tool (1979 of them), which is a report nobody can use.
MARKER_WORDS = frozenset({
    "error", "note", "warning", "words", "message", "problem", "why", "reason",
    "title", "label", "hint", "prompt", "text", "detail", "refusal", "sentence",
    "notice", "answer", "body", "ok", "id", "action", "kind", "name", "value",
    "method", "path", "type", "status", "code", "data", "content", "result",
})

# ---------------------------------------------------------------------------
#   Which lines count as user-facing (the context markers)
# ---------------------------------------------------------------------------
# A string literal is a CANDIDATE when its own line, or one of the two lines
# before it, carries one of these markers. That window matters because a
# response is often written over several lines (a dict key on one line, its
# value on the next; an `Err(format!(` for a Rust command error). It is a
# heuristic and it says so: the report is a list of candidates for a person to
# read, not a compiler.
PY_MARKERS = re.compile(
    r'"(?:error|note|warning|words|message|problem|why|reason|title|label|hint|'
    r'prompt|text|detail|refusal|sentence|notice|answer|body)"\s*:'
    r"|_send\s*\(|refused\s*\(|refusal\s*\(|describe\s*\(|_WORDS\b|_SAID\b"
    r"|_MESSAGE\b|_NOTE\b|_WARNING\b|_HINT\b|_PROMPT\b|_TEXT\b|_REFUSAL\b"
    r"|words\s*=|message\s*=|problem\s*=|refusal\s*=|reason\s*=",
    re.I)
JS_MARKERS = re.compile(
    r"textContent\s*=|innerHTML\s*=|title\s*=|placeholder\s*=|setAttribute\(\s*"
    r"""["'](?:title|aria-label|alt)|say\s*\(|alert\s*\(|toast|snackbar|banner"""
    r"""|notice|["'](?:error|note|warning|words|message|label|title|hint|"""
    r"""detail|problem)["']\s*:|\.textContent\b|aria-label""",
    re.I)
RUST_MARKERS = re.compile(
    r"Err\s*\(|backend_refusal|plain_error"
    r"|(?:words|title|message|error_text|refusal|note|warning|label|hint)\s*[:=]"
    r"|user_words|sentence|_say\(", re.I)
KT_MARKERS = re.compile(
    r"\bText\s*\(|stringResource\s*\(|R\.string\.|label\s*=|title\s*=|"
    r"message\s*=|error\s*=|placeholder\s*=|contentDescription\s*=|Toast|"
    r"Snackbar|semantics|words\s*=|button\s*=|hint\s*=", re.I)

#: The line prefix that makes a short string a message VALUE: `"error": "Failed"`,
#: `words: "refused"`, `title = "..."`. A bare "denied" in `"status": "denied"`
#: is an enum value, not a refusal message for the owner, and is not counted as
#: a bare refusal.
MSG_VALUE_BEFORE = re.compile(
    r'["\']?(?:error|message|words|note|warning|problem|refusal|hint|detail|'
    r'prompt|title|label|why|reason)["\']?\s*[:=]\s*$', re.I)


# ---------------------------------------------------------------------------
#   What the scanner found
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    surface: str
    path: str
    line: int
    column: int
    category: str
    term: str
    string: str


@dataclass(frozen=True)
class Candidate:
    surface: str
    path: str
    line: int
    text: str
    #: True when the literal sits where a MESSAGE VALUE goes (a message-ish key
    #: immediately before it, or an Android resource string). Only strict
    #: candidates can become "bare refusals": "status": "denied" is an enum.
    strict: bool = False


# ---------------------------------------------------------------------------
#   The allowlist
# ---------------------------------------------------------------------------


def load_allowlist(path: Path) -> tuple[frozenset, tuple]:
    """(single words to skip, phrases to remove before matching). Never raises:
    a missing allowlist is no allowlist, and the caller is told so."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return frozenset(), ()
    words, phrases = set(), []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if " " in line:
            phrases.append(line.casefold())
        else:
            words.add(line.casefold())
    return frozenset(words), tuple(phrases)


def _analyse(text: str, allowed_words: frozenset, allowed_phrases: tuple):
    """(findings of (column, category, term), bare refusal or None) for one
    candidate string. Allowlisted phrases are blanked out first, so "API key"
    passes while a bare "API" in the same sentence still fails."""
    work = text
    for phrase in allowed_phrases:
        if phrase in work.casefold():
            work = re.sub(re.escape(phrase), lambda m: " " * len(m.group(0)),
                          work, flags=re.I)
    taken, findings = [], []
    bare_token = not re.search(r"\s", text.strip())
    for category, term, pattern in TERM_RULES:
        if term.casefold() in allowed_words:
            continue
        # A lone config key ("content_type") is a data field, not a sentence
        # shown to a person; in prose it is caught by the same rule below.
        if bare_token and category == "config_key":
            continue
        for m in pattern.finditer(work):
            start, end = m.span()
            if any(start < t_end and end > t_start for t_start, t_end in taken):
                continue          # a compound already claimed this span
            taken.append((start, end))
            findings.append((m.start(), category, term))
    normalised = re.sub(r"[\s.!?:;,]+", " ", text).strip().casefold()
    bare = normalised if normalised in BARE_REFUSALS else None
    return findings, bare


# ---------------------------------------------------------------------------
#   Candidate extraction, by surface
# ---------------------------------------------------------------------------


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _quoted_at(line: str) -> list[tuple[str, int, bool]]:
    """[(body, start column, is_a_key)] for the quoted literals in one line.

    Scanned by hand rather than with one regex: a regex with a backreference
    happily pairs the CLOSING quote of one literal with the OPENING quote of
    the next (measured: `getElementById("x") ... = "HTTP 500"` produced the
    fake body `).textContent = `), which is exactly the kind of wrong report
    this tool exists not to make."""
    out: list[tuple[str, int, bool]] = []
    index, size = 0, len(line)
    while index < size:
        if line[index] not in "\"'":
            index += 1
            continue
        quote = line[index]
        cursor, body = index + 1, []
        while cursor < size:
            char = line[cursor]
            if char == "\\" and cursor + 1 < size:
                body.append(char)
                body.append(line[cursor + 1])
                cursor += 2
                continue
            if char == quote:
                break
            body.append(char)
            cursor += 1
        if cursor >= size:          # an unterminated quote on this line
            index += 1
            continue
        text = "".join(body)
        is_key = bool(re.match(r"\s*:", line[cursor + 1:]))
        out.append((text, index, is_key))
        index = cursor + 1
    return out


def _strict_before(line: str, column: int) -> bool:
    return bool(MSG_VALUE_BEFORE.search(line[:column]))


def _iter_numbered(text: str):
    """(line number, line) with no trailing newline."""
    for number, line in enumerate(text.splitlines(), 1):
        yield number, line


def _context(lines: list[str], index: int, window: int = 2) -> str:
    """The line plus the two before it, joined - where a marker may sit."""
    return "\n".join(lines[max(0, index - window):index + 1])


#: Docstrings are developer text, not user-facing words. Collected by AST so a
#: string that is a module/class/function docstring is skipped, whatever its
#: quotes or position; a literal that merely starts a line is not skipped.
def docstring_lines(tree: ast.Module) -> set:
    spans = set()

    def visit(node):
        body = getattr(node, "body", None)
        if body and isinstance(body[0], ast.Expr) and isinstance(
                getattr(body[0], "value", None), ast.Constant) and isinstance(
                body[0].value.value, str):
            for line in range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1):
                spans.add(line)
        for child in ast.walk(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                inner = child.body
                if inner and isinstance(inner[0], ast.Expr) and isinstance(
                        getattr(inner[0], "value", None), ast.Constant) and isinstance(
                        inner[0].value.value, str):
                    for line in range(inner[0].lineno,
                                      (inner[0].end_lineno or inner[0].lineno) + 1):
                        spans.add(line)

    visit(tree)
    return spans


def backend_candidates(path: Path, rel: str) -> tuple[list, list]:
    """(candidates, unreadable) for one Python module."""
    text = _read(path)
    lines = text.splitlines()
    with warnings.catch_warnings():
        # Some backend modules carry text with `\p`/`\z` in it; the parser warns
        # about the escape. That is the module's business, not this scan's, and
        # a warning on stderr is not a finding.
        warnings.simplefilter("ignore")
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            return [], [f"{rel}: cannot parse ({exc.msg})"]
        skip = docstring_lines(tree)
        out: list[Candidate] = []
        seen: set = set()
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
        except (tokenize.TokenError, IndentationError) as exc:
            return [], [f"{rel}: cannot tokenize ({exc})"]
        for tok in tokens:
            # Python 3.12 tokenizes an f-string into FSTRING_START/MIDDLE/END;
            # the literal words are the FSTRING_MIDDLE value, already unescaped.
            is_middle = tok.type == getattr(tokenize, "FSTRING_MIDDLE", -1)
            if tok.type != tokenize.STRING and not is_middle:
                continue
            if tok.start[0] in skip:
                continue
            try:
                value = tok.string if is_middle else ast.literal_eval(tok.string)
            except (ValueError, SyntaxError, RecursionError):
                continue
            if not isinstance(value, str):
                continue
            # an f-string's braces and its expressions are not words; only the
            # literal parts of it are candidate text.
            if is_middle:
                value = value.replace("{{", "{").replace("}}", "}")
            if len(value.strip()) < 3:
                continue
            # '' and "" docstring-looking literals are already skipped above; a
            # value that is only whitespace has no words and cannot leak anything.
            if not PY_MARKERS.search(_context(lines, tok.start[0] - 1)):
                continue
            key = (tok.start[0], value)
            if key in seen:
                continue
            seen.add(key)
            strict = _strict_before(lines[tok.start[0] - 1], max(0, tok.start[1] - 1))
            out.append(Candidate("backend", rel, tok.start[0], value, strict))
    return out, []


def hud_candidates(path: Path, rel: str) -> tuple[list, list]:
    text = _read(path)
    lines = text.splitlines()
    out: list[Candidate] = []
    in_raw = False
    in_style = False
    in_comment = False
    for number, line in _iter_numbered(text):
        stripped = line.strip()
        if "<!--" in line:
            in_comment = True
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue              # an HTML comment is developer text
        if re.search(r"<script\b", line, re.I):
            in_raw = True
        if re.search(r"<style\b", line, re.I):
            in_style = True
        # HTML visible text (the page itself and its labels): strip tags and
        # read what a person would see. Only the .html page has visible text;
        # a .js file's lines are code, and the marker pass below reads its
        # string literals. Comments, script and style blocks are not text.
        if (path.suffix.lower() == ".html" and not in_raw and not in_style
                and stripped and not stripped.startswith("<!--")):
            visible = re.sub(r"<[^>]+>", " ", line)
            visible = re.sub(r"&[a-z#0-9]+;", " ", visible, flags=re.I).strip()
            if re.search(r"[A-Za-z]{3,}", visible):
                out.append(Candidate("hud", rel, number, visible))
        if re.search(r"</script\s*>", line, re.I):
            in_raw = False
        if re.search(r"</style\s*>", line, re.I):
            in_style = False
        if stripped.startswith(("//", "/*", "*", "<!--")):
            continue              # comments are developer text, not user words
        if JS_MARKERS.search(_context(lines, number - 1)):
            for piece, start, is_key in _quoted_at(line):
                if is_key or len(piece.strip()) < 3:
                    continue
                out.append(Candidate("hud", rel, number, piece,
                                     _strict_before(line, start)))
    return out, []


def rust_candidates(path: Path, rel: str) -> tuple[list, list]:
    text = _read(path)
    lines = text.splitlines()
    out: list[Candidate] = []
    for number, line in _iter_numbered(text):
        if line.strip().startswith("//"):
            continue
        if not RUST_MARKERS.search(_context(lines, number - 1)):
            continue
        for piece, start, is_key in _quoted_at(line):
            if is_key or len(piece.strip()) < 3:
                continue
            out.append(Candidate("rust", rel, number, piece,
                                 _strict_before(line, start)))
    return out, []


def kotlin_candidates(path: Path, rel: str) -> tuple[list, list]:
    text = _read(path)
    lines = text.splitlines()
    out: list[Candidate] = []
    for number, line in _iter_numbered(text):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        if not KT_MARKERS.search(_context(lines, number - 1)):
            continue
        for piece, start, is_key in _quoted_at(line):
            if is_key or len(piece.strip()) < 3:
                continue
            out.append(Candidate("android", rel, number, piece,
                                 _strict_before(line, start)))
    return out, []


XML_STRING = re.compile(r"<(?:string|item)[^>]*>(.*?)</(?:string|item)>", re.S)


def xml_candidates(path: Path, rel: str) -> tuple[list, list]:
    """Every resource string is user-facing by definition, so this surface
    needs no marker: the value itself is read, and it is a message value."""
    text = _read(path)
    out: list[Candidate] = []
    for match in XML_STRING.finditer(text):
        value = re.sub(r"<[^>]+>", " ", match.group(1))
        value = re.sub(r"\\(.)", r"\1", value).strip()
        if len(value) >= 3:
            line = text.count("\n", 0, match.start()) + 1
            out.append(Candidate("android", rel, line, value, True))
    return out, []


# ---------------------------------------------------------------------------
#   Walking the tree
# ---------------------------------------------------------------------------


def shipped_backend_names(root: Path) -> list[str]:
    """The SHIPPED tuple from backend/_where.py, as bare file names.

    Falls back to `backend/jarvis_*.py` when the file is not there (a minimal
    test root), so a hermetic fixture is scanned the same way as the real tree.
    """
    where = root / "backend" / "_where.py"
    names: list[str] = []
    if where.is_file():
        text = _read(where)
        start = text.find("SHIPPED = (")
        if start != -1:
            block = text[start:text.find("\n)", start) + 2]
            for line in block.splitlines()[1:]:
                m = re.match(r'\s*"([^"]+\.py)",', line)
                if m:
                    names.append(m.group(1))
    if not names:
        backend = root / "backend"
        names = [p.name for p in sorted(backend.glob("jarvis_*.py"))]
        names += [f"rebuilt/{p.name}" for p in sorted((backend / "rebuilt").glob("*.py"))]
    return names


def surface_files(root: Path):
    """(surface, files, unreadable-sources) for the four surfaces."""
    backend: list[tuple[Path, str]] = []
    for name in shipped_backend_names(root):
        path = root / "backend" / name
        if path.is_file():
            backend.append((path, f"backend/{name}"))
    hud: list[tuple[Path, str]] = []
    page = root / "jarvis-desktop" / "src" / "jarvis_hud.html"
    if page.is_file():
        hud.append((page, "jarvis-desktop/src/jarvis_hud.html"))
    for path in sorted((root / "jarvis-desktop" / "src").glob("hud-*.js")):
        hud.append((path, f"jarvis-desktop/src/{path.name}"))
    rust: list[tuple[Path, str]] = []
    rust_root = root / "jarvis-desktop" / "src-tauri" / "src"
    if rust_root.is_dir():
        for path in sorted(rust_root.rglob("*.rs")):
            rust.append((path, path.relative_to(root).as_posix()))
    android: list[tuple[Path, str]] = []
    client = root / "jarvis-client" / "app" / "src"
    if client.is_dir():
        for path in sorted(client.rglob("strings.xml")):
            android.append((path, path.relative_to(root).as_posix()))
        for path in sorted(client.rglob("*.kt")):
            rel = path.relative_to(root).as_posix()
            if "/test/" in rel or "/androidTest/" in rel:
                continue          # test code speaks to a developer, not the owner
            android.append((path, rel))
    return {"backend": backend, "hud": hud, "rust": rust, "android": android}


EXTRACTORS = {
    "backend": backend_candidates,
    "hud": hud_candidates,
    "rust": rust_candidates,
    "android": kotlin_candidates,
}


def scan(root: Path, allowlist: Path) -> dict:
    """The whole report, including the opening counts. Reads only."""
    allowed_words, allowed_phrases = load_allowlist(allowlist)
    files = surface_files(root)
    findings: list[Finding] = []
    seen_findings: set = set()
    bare: list[dict] = []
    seen_bare: set = set()
    unreadable: list[str] = []
    files_scanned = Counter()
    for surface, pairs in files.items():
        for path, rel in pairs:
            if path.name == "strings.xml":
                candidates, errors = xml_candidates(path, rel)
                surface_of = "android"
            else:
                candidates, errors = EXTRACTORS[surface](path, rel)
                surface_of = surface
                if surface == "android":
                    surface_of = "android"
            files_scanned[surface] += 1
            unreadable.extend(errors)
            for candidate in candidates:
                if candidate.text.strip().casefold() in MARKER_WORDS:
                    continue          # a dict/JSON key, not a message
                if SQL_ISH.search(candidate.text) or SQL_FRAGMENT.search(candidate.text):
                    continue          # SQL is code, never words on a screen
                matched, bare_hit = _analyse(candidate.text, allowed_words,
                                             allowed_phrases)
                for column, category, term in matched:
                    finding = Finding(surface_of, candidate.path,
                                      candidate.line, column, category,
                                      term, candidate.text)
                    # ONE finding per (file, line, word, string): two copies of
                    # the same literal on one line are one wording problem.
                    key = (finding.path, finding.line, finding.term,
                           finding.string)
                    if key in seen_findings:
                        continue
                    seen_findings.add(key)
                    findings.append(finding)
                if bare_hit and candidate.strict:
                    bare_key = (surface_of, candidate.path, candidate.line,
                                candidate.text)
                    if bare_key in seen_bare:
                        continue
                    seen_bare.add(bare_key)
                    bare.append({"surface": surface_of, "file": candidate.path,
                                 "line": candidate.line, "string": candidate.text,
                                 "normalised": bare_hit})
    findings.sort(key=lambda f: (f.path, f.line, f.column, f.term))
    bare.sort(key=lambda b: (b["file"], b["line"]))
    by_term = Counter(f.term for f in findings)
    by_category = Counter(f.category for f in findings)
    by_surface = Counter(f.surface for f in findings)
    return {
        "tool": TOOL_NAME,
        "review": REVIEW,
        "version": BASELINE_VERSION,
        "generated": date.today().isoformat(),
        "root": ".",
        "files_scanned": dict(sorted(files_scanned.items())),
        "files_scanned_total": sum(files_scanned.values()),
        "allowlist": {
            "words": sorted(allowed_words),
            "phrases": sorted(allowed_phrases),
        },
        "counts": {
            "total": len(findings),
            "bare_refusals": len(bare),
            "by_category": dict(sorted(by_category.items())),
            "by_term": dict(sorted(by_term.items())),
            "by_surface": dict(sorted(by_surface.items())),
        },
        "findings": [f.__dict__ for f in findings],
        "bare_refusals": bare,
        "unreadable": unreadable,
    }


# ---------------------------------------------------------------------------
#   Printing and the ratchet
# ---------------------------------------------------------------------------


def _short(text: str, limit: int = 92) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def print_report(report: dict, *, top: int = 12, show_samples: bool = True) -> None:
    counts = report["counts"]
    print(f"{REVIEW} - report mode")
    print(f"  files scanned: {report['files_scanned_total']}  "
          + " ".join(f"{k}={v}" for k, v in report["files_scanned"].items()))
    print(f"  user-facing developer words: {counts['total']}")
    print(f"  bare refusals (no what/next): {counts['bare_refusals']}")
    if report["unreadable"]:
        print(f"  unreadable files: {len(report['unreadable'])}")
        for line in report["unreadable"][:5]:
            print(f"    ! {line}")
    terms = list(counts["by_term"].items())
    if terms:
        print("  top terms: " + ", ".join(f"{t} x{n}" for t, n in terms[:top]))
    surfaces = counts["by_surface"]
    if surfaces:
        print("  by surface: " + ", ".join(f"{s}={n}" for s, n in surfaces.items()))
    if show_samples and report["findings"]:
        print("  sample findings (path:line - word - string):")
        for f in report["findings"][:top]:
            print(f"    {f['path']}:{f['line']} - {f['term']} - "
                  f"\"{_short(f['string'], 78)}\"")
    if report["bare_refusals"]:
        print("  sample bare refusals:")
        for b in report["bare_refusals"][:min(top, 5)]:
            print(f"    {b['file']}:{b['line']} - \"{_short(b['string'], 78)}\"")


def load_baseline(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise SystemExit(f"REFUSED: no baseline at {path}. Generate one with "
                         f"--report {path.relative_to(REPO) if path.is_relative_to(REPO) else path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"REFUSED: baseline {path} is not JSON ({exc})")
    counts = data.get("counts")
    if not isinstance(counts, dict) or not isinstance(counts.get("total"), int):
        raise SystemExit(f"REFUSED: baseline {path} has no counts.total")
    return data


def check(report: dict, baseline: dict) -> int:
    """The ratchet: fail only when the tree gets WORSE than the record."""
    had_total = baseline["counts"]["total"]
    had_bare = baseline["counts"].get("bare_refusals", 0)
    total = report["counts"]["total"]
    bare = report["counts"]["bare_refusals"]
    ok = True
    print(f"  baseline: {had_total} developer word(s), {had_bare} bare refusal(s)")
    print(f"  current:  {total} developer word(s), {bare} bare refusal(s)")
    if total > had_total:
        ok = False
        print(f"FAIL  the tree has {total - had_total} MORE user-facing developer "
              f"word(s) than the recorded baseline")
        for f in report["findings"][:12]:
            print(f"      {f['path']}:{f['line']} - {f['term']} - "
                  f"\"{_short(f['string'], 70)}\"")
        print("      Fix the wording, or if a deliberate technical word is now "
              "allowed, add it to tools/zero-jargon-allow.txt; only lower the "
              "baseline after a cleanup.")
    if bare > had_bare:
        ok = False
        print(f"FAIL  the tree has {bare - had_bare} MORE bare refusal(s) than the "
              f"recorded baseline")
        for b in report["bare_refusals"][:8]:
            print(f"      {b['file']}:{b['line']} - \"{_short(b['string'], 70)}\"")
    if report["unreadable"]:
        ok = False
        print(f"FAIL  {len(report['unreadable'])} file(s) could not be read: a "
              f"scanner that silently skips a surface is not a check")
        for line in report["unreadable"][:8]:
            print(f"      {line}")
    print("ok    no new user-facing developer words over the baseline"
          if ok else "FAIL  zero-jargon ratchet")
    return 0 if ok else 1


def main(argv=None) -> int:
    # A findings string can carry an em dash or a curly quote; a Windows pipe
    # defaults to cp1252 and would raise inside the tool. Same fix as _where.py
    # gives the suites: read and write UTF-8, replace what cannot be drawn.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass
    parser = argparse.ArgumentParser(
        description="Review #8: scan user-facing strings for developer jargon.")
    parser.add_argument("--root", default="", help="repository root (default: this checkout)")
    parser.add_argument("--allowlist", default="", help="allowlist file")
    parser.add_argument("--report", default="", help="write the machine-readable JSON here")
    parser.add_argument("--check", action="store_true",
                        help="ratchet against the recorded baseline (exit 1 if worse)")
    parser.add_argument("--baseline", default="", help="baseline JSON (default: the docs baseline)")
    parser.add_argument("--quiet", action="store_true", help="summary only")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else REPO
    if not (root / "backend").is_dir():
        raise SystemExit(f"REFUSED: {root} has no backend/ folder - not this repository")
    allowlist = Path(args.allowlist) if args.allowlist else root / "tools" / "zero-jargon-allow.txt"
    report = scan(root, allowlist)
    if args.report:
        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        print(f"  report written: {out}")
    if args.quiet:
        print(json.dumps(report["counts"], ensure_ascii=False))
    else:
        print_report(report)
    if args.check:
        baseline_path = Path(args.baseline) if args.baseline else \
            root / "docs" / "REVIEW-8-ZERO-JARGON-BASELINE-2026-10-23.json"
        return check(report, load_baseline(baseline_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
