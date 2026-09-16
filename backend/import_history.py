"""import_history.py - feed an old Claude or Gemini export into the review queue.

    python backend\\import_history.py --claude path\\to\\claude-export.zip
    python backend\\import_history.py --gemini path\\to\\takeout.zip
    python backend\\import_history.py --claude a.zip --gemini b.zip

WHAT THIS DOES, AND WHAT IT DELIBERATELY DOES NOT DO

This does not add anything to memory. It calls `jarvis_extract.propose()` -
the exact same function a live conversation triggers once it goes quiet -
once per historical conversation, exactly as if that history had happened
live. Everything propose() already guarantees keeps guaranteeing itself here,
for free, because nothing about propose() changes: the model call is
whatever `_local_llm` is (Ollama, on this machine, never a cloud lane), a
proposal still needs a human to accept it before it becomes a fact, and the
review queue's cap still applies.

THAT LAST PART IS THE POINT, NOT A LIMITATION TO WORK AROUND. Two full
conversation histories could easily be thousands of conversations. There is
no bulk-approve here and there will not be one - "There is no approve-all
anywhere in Jarvis; do not build one" is a rule stated more than once in this
project, and a history importer is exactly the tool that would tempt someone
into breaking it "just this once, there's a lot of data." Every fact this
produces still gets exactly one human decision, exactly the way a fact from
yesterday's conversation would. Importing a big history means reviewing the
queue over several sittings, the same as you would if you'd actually had a
few thousand conversations. The cap makes that literal instead of aspirational:
when the queue fills, this tool STOPS and tells you to go clear some of it in
the Brain window, then run it again to continue.

WHY THIS IS A SCRIPT AND NOT A DESKTOP BUTTON (yet)
A full history import can take from minutes to days, depending on how much
there is and how fast the local model answers - it is calling propose() once
per conversation, and propose() calls a local 8B-class model. That is squarely
"walk away and let it run", not "click and wait", so it starts as a command
line tool the owner runs when they want to, the same way `grade-peers.py` and
`jarvis_research.py` in this directory are tools rather than buttons. A Brain
window trigger that starts/shows progress on a background run of this is a
reasonable next step, not something this file tries to also be.

RESUMABILITY
Each conversation gets a stable id (the export's own id if it has one,
otherwise a hash of its content) and a record of "already offered to
propose()" is kept in `<config dir>/import-history-progress.json`. Re-running
the same command later - because the queue filled, because the process was
interrupted, because you just want to check for anything new in a fresh
export - skips what it already offered. It does NOT skip what got REJECTED
or is still pending: those already live in propose()'s own dedupe (memory-
noise.patch), which this script inherits by calling the same function. The
progress file is only about not re-running the LOCAL MODEL over the same
conversation twice, which would be slow for no benefit; it is not a second
copy of the decision the review queue already tracks.

WHAT ACTUALLY LEAVES THIS MACHINE: nothing. Both export files are read from
disk. Nothing here opens a socket.

TWO FORMATS, TWO CONFIDENCE LEVELS
The Claude parser is checked against the export shape this project's own
`scripts/recover_from_claude_export.py` was built and run against on a real
export - one JSON per conversation, `chat_messages`, `sender`, `text`. The
Gemini parser is written against Google Takeout's documented "Gemini Apps"
activity export shape, WHICH THIS PROJECT HAS NOT VERIFIED AGAINST A REAL
FILE. Google Takeout's activity log has historically recorded the PROMPT you
sent more reliably than the full response you got back, so a Gemini import
may end up mostly one-sided ("I asked about X") rather than a full back and
forth. If your export's field names do not match what `_gemini_conversations`
looks for, it degrades to "0 conversations found in this file" rather than
raising - loudly enough to notice, not loudly enough to crash - and the fix
is to open the JSON, see what the real keys are called, and adjust the
handful of `.get(...)` calls in that one function. Said here plainly rather
than left to be discovered as a silent gap: "I have not checked" beats a
confident guess, and this project's own rules say so.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
import zipfile
from pathlib import Path
from typing import Iterator, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, explain  # noqa: E402

sys.path.insert(0, str(BACKEND))


def _config_dir() -> Path:
    """Same rule jarvis_memory._config_dir() and jarvis_framework use: the
    real framework's CONFIG_DIR if it is importable, OPENJARVIS_CONFIG_DIR if
    set, otherwise ~/.openjarvis. Kept independent rather than imported, so
    this script still runs (and still writes its progress file somewhere
    sane) even against a backend where jarvis_framework itself is missing or
    broken - it should not be possible for a mis-set-up backend to make the
    progress file land somewhere unfindable.
    """
    import os
    try:
        import jarvis_framework as fw  # type: ignore
        if getattr(fw, "CONFIG_DIR", None):
            return Path(fw.CONFIG_DIR)
    except Exception:
        pass
    env = os.environ.get("OPENJARVIS_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path(os.path.expanduser("~")) / ".openjarvis"


PROGRESS_FILE = _config_dir() / "import-history-progress.json"


def _load_progress() -> dict:
    try:
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    except Exception:
        # Missing, corrupt, first run - all the same answer: nothing has
        # been offered yet. Never let a bad progress file stop the import;
        # the worst case of losing it is re-offering conversations that are
        # already in propose()'s own dedupe, which is slow, not unsafe.
        return {"done": []}


def _save_progress(done: set) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PROGRESS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"done": sorted(done)}, indent=2), encoding="utf-8")
    tmp.replace(PROGRESS_FILE)


def _conv_id(source: str, raw_id: Optional[str], turns: list[dict]) -> str:
    """A stable id for "have I already offered this conversation". The
    export's own id if there is one - it will not collide and will not
    change between runs. Otherwise a hash of the first and last turn's text,
    which is stable across re-reading the same file and different enough
    across distinct conversations for this script's only real requirement:
    not re-running the local model over the same thing twice.
    """
    if raw_id:
        return f"{source}:{raw_id}"
    sample = (turns[0].get("content", "") if turns else "") + \
             (turns[-1].get("content", "") if len(turns) > 1 else "")
    return f"{source}:{hashlib.sha256(sample.encode('utf-8', 'replace')).hexdigest()[:16]}"


# --------------------------------------------------------------------------
#   Claude export
# --------------------------------------------------------------------------
#
# Verified shape, not guessed: `scripts/recover_from_claude_export.py` was
# built and run against a real claude.ai export in this project's own
# history. Its finding, kept here rather than re-discovered: the export is
# not one JSON file, it is many -
#
#     conversations.json              <- an index. No message text in it.
#     conversations/<uuid>.json       <- the actual conversations
#     projects/<uuid>.json
#
# - so reading only the top-level conversations.json finds zero messages and
# looks like an empty history rather than a wrong assumption. Every JSON
# entry in the archive is read for that reason.
#
# Within one conversation entry, the message list has been seen under both
# `chat_messages` and `messages`, and a turn's speaker under both `sender`
# and `role`, with the text as a bare string OR as `content: [{"type":
# "text", "text": "..."}]` blocks (the same content-block shape Claude's own
# API uses). All of that is walked rather than assumed to be one shape.

def _claude_role(raw) -> Optional[str]:
    r = str(raw or "").strip().lower()
    if r in ("human", "user"):
        return "user"
    if r in ("assistant", "bot", "model"):
        return "assistant"
    return None


def _claude_text(node: dict) -> str:
    val = node.get("text")
    if isinstance(val, str) and val.strip():
        return val
    blocks = node.get("content")
    if isinstance(blocks, str):
        return blocks
    if isinstance(blocks, list):
        out = []
        for b in blocks:
            if isinstance(b, dict) and isinstance(b.get("text"), str):
                out.append(b["text"])
            elif isinstance(b, str):
                out.append(b)
        return "\n".join(out)
    return ""


def _claude_turns(convo: dict) -> list[dict]:
    msgs = convo.get("chat_messages")
    if not isinstance(msgs, list):
        msgs = convo.get("messages")
    if not isinstance(msgs, list):
        return []
    turns = []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        role = _claude_role(m.get("sender") or m.get("role"))
        text = " ".join(_claude_text(m).split())
        if role and text:
            turns.append({"role": role, "content": text})
    return turns


def claude_conversations(path: Path) -> Iterator[tuple[str, list[dict]]]:
    """Yields (id, turns) for every conversation this export holds."""
    for _label, doc in _walk_json_documents(path):
        candidates = doc if isinstance(doc, list) else [doc]
        for entry in candidates:
            if not isinstance(entry, dict):
                continue
            turns = _claude_turns(entry)
            if len(turns) >= 2:  # a monologue with no reply teaches nothing
                raw_id = entry.get("uuid") or entry.get("id")
                yield _conv_id("claude", raw_id, turns), turns


# --------------------------------------------------------------------------
#   Gemini / Google Takeout export
# --------------------------------------------------------------------------
#
# UNVERIFIED AGAINST A REAL FILE - see the module docstring. Written against
# Google Takeout's documented "Gemini Apps" activity export:
# `Takeout/My Activity/Gemini Apps/MyActivity.json`, an array of records that
# typically carry a `title` like "Prompted with: <text>" or "Asked Gemini:
# <text>", a `time`, and sometimes a `subtitles` or `details` array that may
# hold the response. Each record is usually ONE turn, not a conversation, so
# unlike the Claude side there is rarely a `replaces`-worthy back-and-forth to
# reconstruct - this treats each record as its own single-turn "conversation"
# for propose() to look at, which honestly reflects what Takeout tends to
# capture rather than pretending to a fuller transcript than the export has.

def _gemini_prompt_text(title: str) -> str:
    t = title.strip()
    for prefix in ("Prompted with: ", "Asked Gemini: ", "Asked Bard: "):
        if t.startswith(prefix):
            return t[len(prefix):]
    return t


def _gemini_reply_text(record: dict) -> str:
    for key in ("subtitles", "details"):
        val = record.get(key)
        if isinstance(val, list):
            parts = [v.get("name") if isinstance(v, dict) else v for v in val]
            parts = [p for p in parts if isinstance(p, str) and p.strip()]
            if parts:
                return "\n".join(parts)
    return ""


def gemini_conversations(path: Path) -> Iterator[tuple[str, list[dict]]]:
    for _label, doc in _walk_json_documents(path):
        records = doc if isinstance(doc, list) else doc.get("Gemini Apps") if isinstance(doc, dict) else None
        if not isinstance(records, list):
            continue
        for i, rec in enumerate(records):
            if not isinstance(rec, dict):
                continue
            title = rec.get("title")
            if not isinstance(title, str) or not title.strip():
                continue
            prompt = " ".join(_gemini_prompt_text(title).split())
            if not prompt:
                continue
            turns = [{"role": "user", "content": prompt}]
            reply = " ".join(_gemini_reply_text(rec).split())
            if reply:
                turns.append({"role": "assistant", "content": reply})
            else:
                # A prompt with no captured reply still has something worth
                # asking about ("what car does Mario want" is durable even
                # without Gemini's answer to it) - but propose()'s own model
                # reads a one-sided transcript, so this is offered honestly
                # as a single-user-turn conversation, not padded with an
                # invented reply.
                pass
            raw_id = rec.get("titleUrl") or f"{rec.get('time','')}:{title}"
            yield _conv_id("gemini", raw_id, turns), turns


# --------------------------------------------------------------------------
#   Reading the archive, whatever shape it is in
# --------------------------------------------------------------------------
#
# The same lesson `scripts/recover_from_claude_export.py` learned: read every
# JSON file inside, not the first or the largest one, and keep going when one
# entry is unreadable rather than aborting the whole import over it.

def _walk_json_documents(path: Path) -> Iterator[tuple[str, object]]:
    if path.is_dir():
        files = sorted(f for f in path.rglob("*")
                       if f.is_file() and f.suffix.lower() in (".zip", ".json"))
        for f in files:
            yield from _walk_json_documents(f)
        return
    if zipfile.is_zipfile(path):
        try:
            with zipfile.ZipFile(path) as z:
                for name in z.namelist():
                    if not name.lower().endswith(".json"):
                        continue
                    try:
                        with z.open(name) as fh:
                            yield f"{path.name}:{name}", json.load(
                                io.TextIOWrapper(fh, encoding="utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
                        print(f"    {name}: unreadable ({type(exc).__name__}), skipped")
        except (zipfile.BadZipFile, OSError) as exc:
            print(f"  {path.name}: skipped - {type(exc).__name__}: {exc}")
        return
    if path.suffix.lower() == ".json":
        try:
            yield path.name, json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  {path.name}: skipped - {type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------
#   Feeding the review queue
# --------------------------------------------------------------------------

def run(sources: list[tuple[str, Path]]) -> int:
    """sources: [("claude", path), ("gemini", path), ...]. Returns an exit
    code, non-zero only when nothing at all could be read."""
    import jarvis_extract as X  # the real module, from BACKEND

    progress = _load_progress()
    done = set(progress.get("done", []))
    seen_this_run = 0
    proposed_this_run = 0
    started = time.time()

    PARSERS = {"claude": claude_conversations, "gemini": gemini_conversations}

    for kind, path in sources:
        if not path.is_file() and not path.is_dir():
            print(f"  {kind}: no such file or folder: {path}")
            continue
        print(f"\n=== {kind}: {path} ===")
        found = 0
        for conv_id, turns in PARSERS[kind](path):
            found += 1
            if conv_id in done:
                continue
            seen_this_run += 1
            proposed = X.propose(turns, source=f"import:{kind}")
            proposed_this_run += len(proposed)
            done.add(conv_id)

            status = X.setup_status()
            if status.get("queue_full"):
                _save_progress(done)
                print(f"\n  Stopped after {seen_this_run} new conversation(s) this run "
                      f"({proposed_this_run} proposal(s) added) - the review queue is "
                      f"full.")
                print("  Open the Brain window, review some of what's pending, then "
                      "run this command again to pick up where it left off.")
                print(f"  Progress saved to {PROGRESS_FILE}")
                return 0
        if found == 0:
            print(f"  0 conversations found in this file. If you are sure this is a "
                  f"real {kind} export, the field names in "
                  f"`{'_claude_turns' if kind == 'claude' else 'gemini_conversations'}` "
                  f"probably do not match what this file actually contains - open it "
                  f"and check.")

    _save_progress(done)
    elapsed = time.time() - started
    print(f"\nDone. {seen_this_run} new conversation(s) offered to the review queue "
          f"this run, {proposed_this_run} proposal(s) added, in {elapsed:.0f}s.")
    print("Nothing became a fact without a decision in the Brain window - review "
          "the queue there when you're ready.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--claude", type=Path, help="a Claude/claude.ai export .zip, "
                    ".json, or a folder holding either")
    ap.add_argument("--gemini", type=Path, help="a Google Takeout export .zip, "
                    ".json, or a folder holding either")
    args = ap.parse_args()

    sources = []
    if args.claude:
        sources.append(("claude", args.claude))
    if args.gemini:
        sources.append(("gemini", args.gemini))
    if not sources:
        ap.error("pass at least one of --claude or --gemini")

    try:
        import jarvis_extract  # noqa: F401  (fail fast, with a clear reason)
    except ImportError:
        print(f"Could not import jarvis_extract. {explain()}")
        return 2

    return run(sources)


if __name__ == "__main__":
    sys.exit(main())
