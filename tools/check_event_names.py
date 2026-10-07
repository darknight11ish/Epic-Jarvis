#!/usr/bin/env python3
"""Every event name the desktop shell sends must be a name some surface reads,
and every name a surface reads must be a name something sends.

    python3 tools/check_event_names.py [-v]

Two roads carry the event stream out of Rust, and they are NOT the same road:

  * the Tauri events (`jarvis-event`, `jarvis-link`, `approvals-changed`,
    `jarvis-resync`), fanned out by `crate::emit_all` and consumed once, in
    `jarvis-link.js`, whose `onEvent` handlers read the FRAME'S OWN `kind`
    (`{ kind, id, data }`) - so there the event name is `jarvis-event` and the
    kind is data;
  * the HUD's `EventSource` shim in `src-tauri/src/hud_bootstrap.js`, which
    dispatches each frame with **the kind as the event type**
    (`es.dispatchEvent({ type: payload.kind, ... })`, `deliver()`), exactly as
    a real `EventSource` would for a named SSE event.

The second road is where the bug this script was written for lives, and it is
the reason the two cannot be checked the same way. `EventSource` delivers an
event ONLY to listeners registered for that exact type - `onmessage` is the
handler for type `message` and nothing else, which the shim's own comment says
it reproduces on purpose ("the page must behave the same here as it does in a
browser"). `jarvis_hud.html` reads `hello`, `approval`, `proposal`, `finding`
and `activity` inside its `onmessage` handler. Every one of those arrives with
its own kind as the type, so `onmessage` is never called for it and all five
branches are unreachable - the HUD's live event path has been dead since the
shim replaced its socket, and nothing anywhere says so: no error, no log line,
just a page that updates on its 30-second poll instead of on the event.

This script reports that, and does not fix it: `jarvis_hud.html` is vendored
from the backend folder, so the file and line are named instead. The five
branches are recorded in KNOWN_BREAKS below - printed loudly on every run, and
not counted against the exit code, because the file cannot be edited here.

A recorded break still fails when it MOVES or when a new one appears: the key
is the check, the file, the line, the kind the handler is registered for AND
the name read, so a branch added to the same handler, a branch renamed, a
second branch on the same line, or the whole handler re-registered at a new
line is a finding with no entry and the check goes red again.

What it reads - all from THIS checkout:

  jarvis-desktop/src-tauri/src/sse.rs           the wire grammar: the name a
                                                frame with no `event:` line gets
  jarvis-desktop/src-tauri/src/stream.rs        `dispatch`'s own match on
                                                `event.name` - the names the
                                                shell knows, plus the ones its
                                                `_ => {}` arm's comment leaves
                                                to a surface
  jarvis-desktop/src-tauri/src/hud_bootstrap.js the EventSource shim, the types
                                                it dispatches, and the two
                                                CustomEvents it fires
  jarvis-desktop/src/**                         the pages and modules that read
                                                them

Two things it cannot decide, both of which it says out loud rather than
guessing:

  * a kind a page reads whose producer is the BACKEND, not this repository
    (`wellbeing`, `sky`, `proposal`, ...). `stream.rs`'s `_ => {}` arm fans out
    every frame whatever its name, so these are not dead - but no line in this
    tree writes the name down. Each is listed in SENT_BY_THE_BACKEND with a
    one-line reason, so a new one has to be added deliberately.
  * a name the shell dispatches that no PAGE reads, because Rust consumes it
    itself (`hello` updates the link, `handoff` shows a toast). Each is listed
    in CONSUMED_WITHOUT_A_PAGE with a one-line reason.
"""
from __future__ import annotations

import re
import sys
from collections import namedtuple
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "jarvis-desktop" / "src"
RUST = REPO / "jarvis-desktop" / "src-tauri" / "src"
SSE = RUST / "sse.rs"
STREAM = RUST / "stream.rs"
BOOTSTRAP = RUST / "hud_bootstrap.js"

# ---------------------------------------------------------------------------
#   Kinds whose producer is the backend, not this repository
# ---------------------------------------------------------------------------
# stream.rs's `_ => {}` arm re-emits every frame whatever its name, so a page
# reading one of these is not waiting for nothing - but no line in this tree
# writes the name down, which is exactly how a name could be renamed on one
# side only. One line each; add a new one deliberately.
SENT_BY_THE_BACKEND = {
    "proposal": "published when the learner fills the memory review queue (brain.js reads it to re-read that pane).",
    "job": "published when a job changes; brain.js's own `refreshes` table re-reads the job list on it.",
    "wellbeing": "one boolean, `{\"serious\": bool}` - a crisis turn started or ended (jarvis-link.js `noteWellbeing`, and the HUD's own listener).",
    "sky": "the sun, moon and weather document changed (sky-feed.js and sky-settings.js read it).",
    "devices": "a device was paired or removed (devices.js re-reads the list on it).",
    "step": "one chat turn's own progress line, fanned out on this same bus (main.js `toolWatch`).",
    "live": "Jarvis Live started or ended on the phone (main.js takes the phone's session from it).",
    "voices": "the voice list or a custom-voice card changed (voice-panel.js re-reads it).",
}

# ---------------------------------------------------------------------------
#   Names stream.rs dispatches that no page reads, and why that is right
# ---------------------------------------------------------------------------
# Rust consumes these itself before the fan-out: the tray, the link state, the
# toast, the look badge. `persona` is the one with no reader anywhere - it is
# fanned out because the backend publishes it, and the HUD's own graph is the
# surface that draws one (its stream handler is this script's first finding).
CONSUMED_WITHOUT_A_PAGE = {
    "hello": "stream.rs itself: clears `stale`, re-reads everything and fires jarvis-resync.",
    "attention": "stream.rs itself: `link.attention.apply_event`, carried on jarvis-link to every window.",
    "approval": "stream.rs itself: re-reads /api/pending and emits approvals-changed, which the pages do listen for.",
    "appearance": "stream.rs itself: appearance.rs re-reads the document and emits appearance-changed.",
    "screen_watch": "look.rs's `on_event`, which emits screen-status to the badges and the bar.",
    "handoff": "stream.rs itself: shows a Windows toast naming the site that needs the owner.",
    "persona": "no reader in this tree; fanned out because the backend publishes it. The HUD's galaxy draws a `persona` node, and its stream handler is this script's first finding.",
}

# ---------------------------------------------------------------------------
#   The known breaks a guard is still allowed to guard around
# ---------------------------------------------------------------------------
# A guard with a list of known breaks is still a guard, because the list is
# keyed rather than wildcarded: a violation NOT in it takes the exit code to 1
# exactly as before, and a violation that IS in it is printed in full on every
# single run. That is the difference between a recorded break and a silenced
# one - the recorded one cannot be forgotten, and it cannot spread. What it
# must never become is a place a NEW violation hides, so an entry only covers
# the one finding it names (check, file, line, name), and an entry that stops
# being reported is itself printed as stale.
#
# Entries exist only where the fix is genuinely impossible IN THIS REPOSITORY.
# Everything below is one finding: five unreachable `if` branches inside one
# handler in `jarvis_hud.html`.
_KnownBreak = namedtuple("_KnownBreak", "reason fix")

KNOWN_BREAKS = {
    # --- 1. a kind read in a handler registered for another type -------------
    # The key is this script's own four coordinates for that finding: the check
    # that reports it, `file` (the page), `line` (the line the kind is READ at -
    # not the line the handler is registered at, which is printed beside it),
    # `kind` (the type the handler is registered for) and `name` (the kind being
    # read). All four, so that an added branch, a renamed one, a second branch on
    # the same line, or the whole handler moved down the page is a finding with
    # no entry - and an entry that stops matching is reported as stale.
    #
    # THE FIVE HUD LINES BELOW ARE +80 FROM WHAT THEY WERE (2447/2448/2455/2456/
    # 2457 -> the numbers here). That is this rule firing correctly, not a
    # workaround: the 2026-10-07 bug audit added 80 lines to `jarvis_hud.html`
    # (the prompt window that used to slide one exchange every turn), the whole
    # page below the insertion moved down, and these entries were moved with it.
    # A branch was fixed or removed? Then fix or delete its entry - the shift is
    # not a reason for any of them to stay.
    ("1 a read that can never arrive", "jarvis_hud.html", 2547, "message", "hello"):
        _KnownBreak(
            "the file is vendored byte for byte from the owner's backend folder, so a "
            "branch and a listener cannot be added here",
            "the backend's own copy of jarvis_hud.html: register a listener per kind "
            "the page reads - es.addEventListener(\"hello\", ...) - where that page lives"),
    ("1 a read that can never arrive", "jarvis_hud.html", 2548, "message", "approval"):
        _KnownBreak(
            "the file is vendored byte for byte from the owner's backend folder, so a "
            "branch and a listener cannot be added here",
            "the backend's own copy of jarvis_hud.html: register a listener per kind "
            "the page reads - es.addEventListener(\"approval\", ...) - where that page lives"),
    ("1 a read that can never arrive", "jarvis_hud.html", 2555, "message", "proposal"):
        _KnownBreak(
            "the file is vendored byte for byte from the owner's backend folder, so a "
            "branch and a listener cannot be added here",
            "the backend's own copy of jarvis_hud.html: register a listener per kind "
            "the page reads - es.addEventListener(\"proposal\", ...) - where that page lives"),
    ("1 a read that can never arrive", "jarvis_hud.html", 2556, "message", "finding"):
        _KnownBreak(
            "the file is vendored byte for byte from the owner's backend folder, so a "
            "branch and a listener cannot be added here",
            "the backend's own copy of jarvis_hud.html: register a listener per kind "
            "the page reads - es.addEventListener(\"finding\", ...) - where that page lives"),
    ("1 a read that can never arrive", "jarvis_hud.html", 2557, "message", "activity"):
        _KnownBreak(
            "the file is vendored byte for byte from the owner's backend folder, so a "
            "branch and a listener cannot be added here",
            "the backend's own copy of jarvis_hud.html: register a listener per kind "
            "the page reads - es.addEventListener(\"activity\", ...) - where that page lives"),
}


def known_break(check: str, page: str, line: int, kind: str, name: str):
    """The recorded entry for one finding, or None - which means NEW.

    All four coordinates and not one of them: the file and the line alone would
    let a second, different branch on the same line pass as the recorded one,
    the name alone would let an added branch hide behind a name already here,
    and the kind alone would cover every handler on the page.
    """
    return KNOWN_BREAKS.get((check, page, line, kind, name))


# ---------------------------------------------------------------------------
#   Reading the shell
# ---------------------------------------------------------------------------

def code_mask(src: str) -> list[bool]:
    """True at each offset that is real code, False inside a comment, a string,
    a template's text or a regex literal. Offsets are untouched, so a reported
    line number still points at the real line (the same trick as
    check-tokens.py and check_invoke_grants.py).

    Without it, `hud_bootstrap.js`'s own prose - "`event: approval` reaches
    addEventListener" - reads as a dispatched name, and `jarvis_hud.html`'s
    comment about `onmessage` reads as a listener.
    """
    mask = [True] * len(src)
    i, n = 0, len(src)
    prev = ""
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                mask[i] = False
                i += 1
        elif c == "/" and i + 1 < n and src[i + 1] == "*":
            end = src.find("*/", i + 2)
            end = n if end < 0 else end + 2
            for j in range(i, end):
                if src[j] != "\n":
                    mask[j] = False
            i = end
        elif c in "\"'`":
            quote = c
            i += 1
            while i < n:
                if src[i] == "\\":
                    mask[i] = False
                    i += 2
                    continue
                if src[i] == quote:
                    i += 1
                    break
                if quote == "`" and src[i] == "$" and i + 1 < n and src[i + 1] == "{":
                    depth = 1
                    i += 2
                    while i < n and depth:
                        if src[i] == "{":
                            depth += 1
                        elif src[i] == "}":
                            depth -= 1
                        i += 1
                    continue
                if src[i] != "\n":
                    mask[i] = False
                i += 1
        elif c == "/" and prev in "(,=:[!&|?{};+-*%~^<>" and not src.startswith("/=", i):
            i += 1
            while i < n and src[i] != "\n":
                if src[i] == "\\":
                    i += 1
                elif src[i] == "/":
                    i += 1
                    break
                i += 1
        else:
            if not c.isspace():
                prev = c
            i += 1
    return mask


def span(src: str, mask: list[bool], open_at: int) -> int:
    """The offset just past the bracket that closes the one at `open_at`,
    ignoring anything inside a string or a comment."""
    depth, i = 0, open_at
    while i < len(src):
        if mask[i]:
            if src[i] in "([{":
                depth += 1
            elif src[i] in ")]}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return len(src) - 1


def body_after(src: str, mask: list[bool], at: int) -> tuple[int, int]:
    """The `{ ... }` body of the handler written at or after `at`, by balanced
    braces - `onmessage = (m) => { ... }` and `addEventListener("x", (m) => {
    ... })` are both this shape."""
    brace = at
    while brace < len(src) and not (mask[brace] and src[brace] == "{"):
        brace += 1
    if brace >= len(src):
        return at, at
    return brace, span(src, mask, brace)


def line_of(src: str, at: int) -> int:
    return src[:at].count("\n") + 1


KIND_COMPARISON = re.compile(
    r'(?<![\w$.])(kind|[\w$]+\.(?:kind|type))\s*(?:===|!==|==|!=)\s*"([a-z][a-z0-9_]*)"')


def kind_reads(src: str, mask: list[bool], begin: int, end: int) -> list[tuple[str, int]]:
    """(name, line) for every event kind a handler branches on.

    The shape has to be one of the three this tree writes: a comparison against
    `kind` (a local bound from the frame), `<x>.kind` or `<x>.type` - one dot
    only, so `frame.data.kind === "briefing"` (a job's own kind, a different
    namespace) is not mistaken for an event name.
    """
    out = []

    def code(at: int) -> bool:
        return begin <= at <= end and mask[at]

    for m in KIND_COMPARISON.finditer(src):
        if code(m.start()):
            out.append((m.group(2), line_of(src, m.start())))
    for m in re.finditer(r"switch\s*\(\s*(kind|[\w$]+\.(?:kind|type))\s*\)", src):
        if not code(m.start()):
            continue
        open_at = src.index("(", m.start())
        close = span(src, mask, open_at)
        for case in re.finditer(r'case\s+"([a-z][a-z0-9_]*)"\s*:', src[close:end]):
            out.append((case.group(1), line_of(src, close + case.start())))
    # brain.js's `const refreshes = { model: [...], finding: [...] };` then
    # `refreshes[kind]` - a table keyed by the frame's kind, which is how the
    # Brain re-reads a pane on a doorbell.
    for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*\[\s*(?:kind|[\w$]+\.(?:kind|type))\s*\]", src):
        if not code(m.start()):
            continue
        table = m.group(1)
        decl = re.search(r"(?:const|let|var)\s+" + re.escape(table) + r"\s*=\s*\{", src[begin:end])
        if not decl:
            continue
        open_at = begin + decl.end() - 1
        close = span(src, mask, open_at)
        block = src[open_at + 1:close]
        for key in re.finditer(r'(?:^|[,{\s])(?:["\']?)([a-z][a-z0-9_]*)["\']?\s*:', block, re.M):
            out.append((key.group(1), line_of(src, open_at + 1 + key.start())))
    return out


# ---------------------------------------------------------------------------
#   The dispatched side
# ---------------------------------------------------------------------------

def stream_table() -> tuple[list[tuple[str, int]], list[str]]:
    """(name, line) for each `match event.name.as_str()` arm in stream.rs, and
    the names its `_ => {}` arm's own comment hands to a surface."""
    text = STREAM.read_text(encoding="utf-8", errors="replace")
    mask = code_mask(text)
    m = re.search(r"match\s+event\.name\.as_str\(\)\s*\{", text)
    if not m:
        raise SystemExit(f"::error::{STREAM.name}: no `match event.name.as_str()` - "
                         f"this check cannot read the shell's dispatch table")
    open_at = text.index("{", m.start())
    close = span(text, mask, open_at)
    block = text[open_at + 1:close]
    arms = []
    default_at = None
    # An arm is `"name" => {`, and four of them are guarded -
    # `"schedule" if event.data["state"].as_str() == Some("fired") => {` - so
    # the guard is skipped rather than required to be absent. The `==` inside
    # the guard is why the arrow cannot be found by "up to the first `=`".
    for arm in re.finditer(r'^\s*"([a-z][a-z0-9_]*)"(?:\s+if\b.*?)?\s*=>', block, re.M):
        arms.append((arm.group(1), line_of(text, open_at + 1 + arm.start())))
    for arm in re.finditer(r"^\s*_\s*=>", block, re.M):
        default_at = open_at + 1 + arm.start()
    extra: list[str] = []
    if default_at is not None:
        # The comment directly above `_ => {}` names the kinds it leaves to a
        # surface: "finding | persona | model | voice - nothing here consumes
        # them". Read from there rather than hard-coded, so the list cannot
        # drift from the code it describes. Read up to the first character that
        # cannot be part of a list of names, so the sentence after the dash
        # ("nothing here consumes them") is not read as six more names.
        before = text[:default_at].rstrip().splitlines()
        prose = []
        for line in reversed(before):
            if line.strip().startswith("//"):
                prose.append(line.strip().lstrip("/").strip())
            else:
                break
        if prose:
            head = re.split(r"[^A-Za-z0-9_ |]", prose[-1], maxsplit=1)[0]
            extra = [n.strip() for n in head.split("|")
                     if re.fullmatch(r"[a-z][a-z0-9_]*", n.strip() or "")]
    return arms, extra


def sse_default_name() -> str:
    """The name a frame with no `event:` line gets, from sse.rs's own
    `unwrap_or_else`. That is the ONE frame kind that could reach a handler
    registered for `message`."""
    text = SSE.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'unwrap_or_else\(\|\|\s*"([a-z][a-z0-9_]*)"\.to_string\(\)', text)
    if not m:
        raise SystemExit(f"::error::{SSE.name}: the parser's default event name is "
                         f"not where this check reads it - the frame grammar changed")
    return m.group(1)


def bootstrap_types() -> tuple[set[str], dict[str, int]]:
    """The types hud_bootstrap.js can dispatch, and where each is written.

    `payload.kind` (the frame's own name, from `deliver`), the shim's own
    lifecycle types (`open`, `error`), and the two `CustomEvent`s the bootstrap
    fires on `window` for the faces.
    """
    text = BOOTSTRAP.read_text(encoding="utf-8", errors="replace")
    mask = code_mask(text)
    out: dict[str, int] = {}
    for m in re.finditer(r"type:\s*payload\.kind", text):
        if mask[m.start()]:
            out["<payload.kind>"] = line_of(text, m.start())
    for m in re.finditer(r'type:\s*"([a-z]+)"', text):
        if mask[m.start()]:
            out[m.group(1)] = line_of(text, m.start())
    for m in re.finditer(r'new CustomEvent\(\s*"([a-z-]+)"', text):
        if mask[m.start()]:
            out[m.group(1)] = line_of(text, m.start())
    return set(out), out


# ---------------------------------------------------------------------------
#   The listening side
# ---------------------------------------------------------------------------

def event_source_handlers(text: str, mask: list[bool]):
    """(type, begin, end, line) for every handler registered on the page's own
    `EventSource`.

    Only a page that calls `new EventSource(...)` is on this road - today that
    is `jarvis_hud.html` alone, and the shim is injected into that webview only.
    """
    made = re.search(r"(\w+)\s*=\s*new\s+EventSource\s*\(", text)
    if not made:
        return []
    var = made.group(1)
    out = []
    for m in re.finditer(re.escape(var) + r"\s*\.\s*(onmessage|onopen|onerror)\s*=", text):
        if not mask[m.start()]:
            continue
        begin, end = body_after(text, mask, m.end())
        out.append((m.group(1)[2:], begin, end, line_of(text, m.start())))
    for m in re.finditer(re.escape(var) + r'\.addEventListener\(\s*"([a-z0-9_-]+)"', text):
        if not mask[m.start()]:
            continue
        begin, end = body_after(text, mask, m.end())
        out.append((m.group(1), begin, end, line_of(text, m.start())))
    return out


def on_event_handlers(text: str, mask: list[bool]):
    """(begin, end, line) for every `onEvent(...)` handler in a file."""
    out = []
    for m in re.finditer(r"(?<![\w$.])onEvent\s*\(", text):
        if not mask[m.start()]:
            continue
        begin, end = body_after(text, mask, m.end())
        out.append((begin, end, line_of(text, m.start())))
    return out


def main() -> int:
    verbose = "-v" in sys.argv

    arms, left_to_a_surface = stream_table()
    message = sse_default_name()
    dispatched = {name for name, _line in arms} | set(left_to_a_surface) | {message}
    if not dispatched:
        print("::error::read no dispatched event names at all - this check would "
              "pass having checked nothing")
        return 1
    bootstrap, bootstrap_at = bootstrap_types()

    # ---- the listening side -------------------------------------------------
    # Only two shapes count as a read of a BUS kind, and both are deliberately
    # narrow: a branch inside an `onEvent(...)` handler (where the frame is the
    # argument), and a comparison against a variable actually called `frame`
    # (jarvis-link.js's own `noteWellbeing`, registered inside its EV_EVENT
    # listener). Anything wider sweeps in the chat, job, retirement and memory
    # kinds, which are different namespaces with the same word "kind".
    unreachable: list[tuple[str, str, int, str, int]] = []
    hud_types: dict[str, tuple[str, int]] = {}
    bus_reads: set[tuple[str, str, int]] = set()        # (file, kind, line)
    pages = [p for p in sorted(SRC.rglob("*")) if p.suffix in (".js", ".html")]
    for path in pages:
        text = path.read_text(encoding="utf-8", errors="replace")
        mask = code_mask(text)
        for kind, begin, end, line in event_source_handlers(text, mask):
            hud_types[kind] = (path.name, line)
            for name, name_line in kind_reads(text, mask, begin, end):
                if name != kind:
                    unreachable.append((path.name, kind, line, name, name_line))
        for begin, end, _line in on_event_handlers(text, mask):
            bus_reads |= {(path.name, name, name_line)
                          for name, name_line in kind_reads(text, mask, begin, end)}
        for m in re.finditer(r'frame\s*\.\s*kind\s*[!=]==?\s*"([a-z][a-z0-9_]*)"', text):
            if mask[m.start()]:
                bus_reads.add((path.name, m.group(1), line_of(text, m.start())))

    readers: dict[str, list[str]] = {}
    for page, name, line in sorted(bus_reads):
        readers.setdefault(name, []).append(f"{page}:{line}")
    for kind, (page, line) in hud_types.items():
        readers.setdefault(kind, []).append(f"a listener at {page}:{line}")

    problems = False
    # Every recorded break this run actually reports, and every unrecorded
    # finding. The first list is printed, loudly, whether or not the run is
    # otherwise green; the second one is what sets the exit code.
    recorded: dict[tuple, tuple[str, str, int, str, str]] = {}
    unrecorded: list[tuple[str, str, str]] = []
    stale: list[tuple] = []

    # Each check is reported under its own heading, so each keeps its own list
    # of what it could not record. An entry that is found and recorded goes in
    # `recorded` and is printed at the end, whatever else the run found.
    def entry_for(check: str, where: str, why: str) -> None:
        unrecorded.append((
            check,
            f"  {where}",
            f"add a recording for {why}",
        ))

    # 1. The headline: a kind read in a handler registered for another type.
    new_unreachable: list[str] = []
    if unreachable:
        for page, kind, handler_line, name, name_line in sorted(unreachable, key=lambda r: r[4]):
            found = known_break("1 a read that can never arrive", page, name_line, kind, name)
            detail = (f"{page}:{name_line}  reads `{name}` in the `{kind}` handler "
                      f"registered at {page}:{handler_line} - the frame arrives as "
                      f"type `{name}`, so this branch never runs")
            if found is None:
                new_unreachable.append(detail)
                entry_for("a read that can never arrive", detail,
                          f"check 1, {page}:{name_line}, the `{kind}` handler, name `{name}`")
            else:
                recorded[("1 a read that can never arrive", page, name_line, kind, name)] = \
                    (page, kind, handler_line, name, name_line)
    if new_unreachable:
        problems = True
        print("::error::the HUD's stream handler reads event kinds that can never "
              "reach it - hud_bootstrap.js dispatches each frame with its KIND as "
              "the event type (`deliver`, hud_bootstrap.js:%d), and an EventSource "
              "delivers an event only to listeners registered for that exact type "
              "(`onmessage` is type `message` and nothing else). NOTHING BELOW IS "
              "RECORDED IN KNOWN_BREAKS, so it is either new or the recorded entry "
              "no longer matches line for line:"
              % bootstrap_at.get("<payload.kind>", 0))
        for detail in new_unreachable:
            print("  " + detail)
        print("  A recorded break is not a licence to add another: either fix this "
              "one, or add its own entry to KNOWN_BREAKS, with the reason it cannot "
              "be fixed in this repository and where the real fix belongs. An entry "
              "is keyed on check + file + line + the kind the handler is registered "
              "for + the name read, so it cannot cover a different branch.")

    # 2. A listener or a read with no producer anywhere in this tree.
    unknown = sorted(
        {(name, f"{page}:{line}") for page, name, line in bus_reads
         if name not in dispatched and name not in SENT_BY_THE_BACKEND}
        | {(kind, f"{page}:{line}") for kind, (page, line) in hud_types.items()
           if kind not in dispatched and kind not in SENT_BY_THE_BACKEND
           and kind not in ("open", "error")})
    new_unknown: list[str] = []
    if unknown:
        for name, where in unknown:
            page, _colon, at = where.rpartition(":")
            found = known_break("2 a name no producer here writes down", page, int(at), "", name)
            if found is None:
                new_unknown.append(f"{name}  (read at {where})")
                entry_for("a name no producer here writes down", f"{name}  (read at {where})",
                          f"check 2, {where}, name `{name}`")
            else:
                recorded[("2 a name no producer here writes down", page, int(at), "", name)] = \
                    (page, "", int(at), name, int(at))
        if new_unknown:
            problems = True
            print("::error::a page reads an event name no producer in this tree writes "
                  "down - add it to SENT_BY_THE_BACKEND in this script with a one-line "
                  "reason, or fix the name. Any name listed below is NOT recorded in "
                  "KNOWN_BREAKS:")
            for name_where in new_unknown:
                print("  " + name_where)

    # 3. A name the shell dispatches that nothing reads.
    # An entry here would have no file, line or handler kind to name - a
    # dispatched name comes from a Rust arm, and the finding is the name
    # itself - so it is keyed on the name alone. Nothing is recorded today:
    # this is the check that found `persona`.
    unread = sorted(n for n in dispatched
                    if n not in readers and n not in CONSUMED_WITHOUT_A_PAGE)
    new_unread: list[str] = []
    if unread:
        for name in unread:
            found = known_break("3 a name nothing reads", f"<{name}>", 0, "", name)
            if found is None:
                new_unread.append(name)
                entry_for("a name nothing reads", name, f"check 3, name `{name}`")
            else:
                recorded[("3 a name nothing reads", f"<{name}>", 0, "", name)] = \
                    (f"<{name}>", "", 0, name, 0)
        if new_unread:
            problems = True
            print("::error::the shell dispatches an event name no page and no Rust arm "
                  "reads - either a dead sender, or add it to CONSUMED_WITHOUT_A_PAGE "
                  "with a one-line reason. Any name listed below is NOT recorded in "
                  "KNOWN_BREAKS:")
            for name in new_unread:
                print("  " + name)

    # An entry that is no longer reported is printed rather than ignored: the
    # branch may have been fixed (good - delete the entry, so the check is
    # whole again), or the handler may have moved (the finding is still real,
    # and it is now failing above as an unrecorded one).
    for key in KNOWN_BREAKS:
        if key not in recorded:
            stale.append(key)
    if stale:
        print("::error::a break recorded in KNOWN_BREAKS was NOT reported by this run "
              "- delete the entry if the branch is fixed, or move it to where the "
              "branch is now, because a stale entry is the one way this list could "
              "quietly absorb a real finding:")
        for check, page, line, kind, name in sorted(stale, key=lambda k: (k[1], k[2], k[4])):
            where = f"{page}:{line}" if line else f"{page} (no read line)"
            handler = f" in the `{kind}` handler" if kind else ""
            print(f"  check {check}: {where}{handler} reads `{name}` - recorded, not reported")
        problems = True

    if recorded:
        # Printed whether or not the rest of the run is green, because the whole
        # point of a recorded break is that it stays visible. A break that is
        # recorded and never printed is an ignore list with extra steps.
        print()
        print("the HUD's live event path is broken where it lives outside this "
              "repository; these are recorded in KNOWN_BREAKS, so they do not fail "
              "this check, and they are printed on every run so they cannot be "
              "forgotten:")
        for key in sorted(recorded, key=lambda k: (k[0], k[1], k[2], k[4])):
            _check, page, at, kind, name = key
            if kind:
                print(f"  {page}:{at}  reads `{name}` in the `{kind}` handler - an "
                      f"EventSource never calls that handler for type `{name}`")
            else:
                print(f"  {page}:{at}  `{name}` is read here and no line in this "
                      f"tree writes the name down")
            print(f"      cannot be fixed in this repository: {KNOWN_BREAKS[key].reason}")
            print(f"      the real fix belongs: {KNOWN_BREAKS[key].fix}")

    if verbose:
        for name in sorted(dispatched):
            where = ", ".join(sorted(set(readers.get(name, [])))) \
                or "nothing (CONSUMED_WITHOUT_A_PAGE)"
            print(f"  {name:<14} {where}")
        for name in sorted(SENT_BY_THE_BACKEND):
            print(f"  {name:<14} backend, not written down here: "
                  f"{SENT_BY_THE_BACKEND[name]}")

    if problems:
        return 1

    print(f"{len(dispatched)} event name(s) dispatched across the two roads; every "
          f"one is read, or listed in this script as consumed in Rust.")
    print(f"The HUD's EventSource shim dispatches "
          f"{sorted(t for t in bootstrap if t != '<payload.kind>')} plus the frame's "
          f"own kind as the type; the page registers listeners for {sorted(hud_types)} "
          f"- and only for those.")
    print(f"{len(SENT_BY_THE_BACKEND)} name(s) are published by the backend rather "
          f"than written down here, each listed with its reason.")
    if recorded:
        print(f"{len(recorded)} known break(s) reported, each recorded in "
              f"KNOWN_BREAKS - the HUD's stream handler reads kinds that arrive as "
              f"their own event type, and the real fix belongs in the BACKEND's copy "
              f"of jarvis_hud.html, which this repository holds as a byte-for-byte "
              f"vendored copy it must not edit. A finding NOT recorded there still "
              f"exits 1.")
    else:
        print("No known break was reported by this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
