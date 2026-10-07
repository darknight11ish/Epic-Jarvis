"""import_history.py - feed an old ChatGPT, Claude, Gemini or DeepSeek export into the review queue.

    python backend\\import_history.py --chatgpt path\\to\\chatgpt-export.zip
    python backend\\import_history.py --claude path\\to\\claude-export.zip
    python backend\\import_history.py --gemini path\\to\\takeout.zip
    python backend\\import_history.py --deepseek path\\to\\deepseek_data.zip
    python backend\\import_history.py --auto path\\to\\any-of-the-four.zip
    python backend\\import_history.py --claude a.zip --gemini b.zip

Or, on the PC, the Brain's Memory page: "Bring in chats from ChatGPT, Claude,
Gemini or DeepSeek" (jarvis_history_import.py runs this same run() in the background;
docs/JARVIS-API.md section 85). The file is shipped beside jarvis_hud.py for
that, and still runs from this repository as before.

ONLY THE OWNER'S OWN WORDS ARE READ FOR FACTS (2026-09-28)
Every source now hands propose() the owner's own messages only - never the
other assistant's replies, never a tool's output, never a hidden or system
message - the same cut the live learner makes (extraction-wiring.patch,
"WHAT IT READS - user turns only"): the assistant turn is a carrier for
text the owner never wrote. Before this, the Claude and Gemini paths handed
propose() both sides of the chat. Also skipped, as the live learner skips
them (jarvis_intake.py): a chat the owner turned into a game or role-play,
a crisis message (never learned from, never counted), and a timer or
reminder command. The parsers below still read both sides - a chat with no
reply at all is still not offered - and `owner_words()` makes the cut in
run(), in one place, for all three.

WHAT THIS DOES, AND WHAT IT DELIBERATELY DOES NOT DO

This does not add anything to memory. It calls `jarvis_extract.propose()` -
the exact same function a live conversation triggers once it goes quiet -
once per historical conversation, exactly as if that history had happened
live. Everything propose() already guarantees keeps guaranteeing itself here,
for free, because nothing about propose() changes: the model call is
whatever `_local_llm` is (Ollama at OLLAMA_URL), a proposal still needs a
human to accept it before it becomes a fact, and the review queue's cap
still applies.

"On this machine" is CHECKED, not assumed. OLLAMA_URL is an environment
variable, and one pointing at another computer would have sent your whole
history there. So `run()` refuses to start unless it is this machine, and
memory-intake.patch makes propose() itself refuse as well, for every caller.

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

A SCRIPT, AND NOW A BUTTON TOO (2026-09-28)
A full history import can take from minutes to days, depending on how much
there is and how fast the local model answers - it is calling propose() once
per conversation, and propose() calls a local 8B-class model. That is squarely
"walk away and let it run", not "click and wait". It started as a command
line tool; the Brain's Memory page now starts the same run() in the
background on the PC, shows the counts as it goes, and can stop it
(jarvis_history_import.py). Both keep the same progress file, so a run
started from one carries on from the other.

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

WHAT ACTUALLY LEAVES THIS MACHINE: nothing. The export files are read from
disk. The only connection made is propose()'s own, to Ollama on this machine
(see above: refused otherwise).

FOUR FORMATS, AND HOW SURE THIS IS OF EACH (checked 2026-09-28)
  * Claude - checked against a real export (the one
    `scripts/recover_from_claude_export.py` was run on) and against open-
    source readers of current ones: `chat_messages`, `sender`, and the text
    from "text" content blocks only.
  * ChatGPT, DeepSeek and Gemini - written from the shapes that several
    open-source readers of REAL exports agree on (named beside each reader
    below), not from a file of the owner's own. Gemini's is the least
    certain: Google Takeout records what the owner typed more reliably than
    Gemini's answers, and has no conversation id, so prompts are put back
    into conversations by time (a new one after 30 minutes' silence).
If an export's field names do not match, its reader finds "0 conversations"
and says so, rather than raising or guessing. "I have not checked" beats a
confident guess.

READING A CHAT WELL (2026-09-28)
A long chat is handed to the model in pieces it can read whole (pieces()),
through the same door as live learning (jarvis_intake.propose: the date the
chat happened and the closest stored facts are in the prompt), on the chat's
own model. A model that does not answer pauses the run with that chat not
marked read, so nothing is lost. Pasted-in messages and code blocks are left
out. See "Reading a long chat whole", below.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import Iterator, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    # Run from this repository: the backend is wherever _where.py says.
    from _where import BACKEND, explain  # noqa: E402
except ImportError:
    # Shipped beside jarvis_hud.py (apply-patches.ps1, for the Brain's
    # button): the backend is this very folder.
    BACKEND = HERE

    def explain() -> str:
        return (f"import_history.py is in {HERE}, but jarvis_extract.py is not beside it. "
                f"Run apply-patches.ps1 on the PC.")

sys.path.insert(0, str(BACKEND))

#: Where the parsers' own notes go ("x.json: unreadable, skipped"). run()
#: points it at its `say` for the length of a run, so the Brain's button can
#: keep file names out of backend.log.
_say = print


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
    """The words of one Claude message. Built from its "text" content
    blocks when it has any - never a "thinking" block (the model's hidden
    reasoning), a "tool_use" (Claude's artifacts are one), a "tool_result"
    or any other kind -
    and otherwise from its plain `text` field. `attachments` (the text of
    a pasted or uploaded file, `extracted_content`) is never read: it is
    outside text, not the owner's words."""
    blocks = node.get("content")
    if isinstance(blocks, str) and blocks.strip():
        return blocks
    if isinstance(blocks, list):
        out = []
        for b in blocks:
            if isinstance(b, str):
                out.append(b)
            elif isinstance(b, dict) and b.get("type") in (None, "", "text") \
                    and isinstance(b.get("text"), str):
                out.append(b["text"])
        if any(o.strip() for o in out):
            return "\n".join(out)
    val = node.get("text")
    if isinstance(val, str) and val.strip():
        return val
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


#: conversation id -> when it happened (epoch seconds), for every conversation
#: the parsers below have yielded whose export said. A side table rather than
#: a third item in the tuple, so everything that already unpacks
#: `(conv_id, turns)` keeps working. run() reads it to date the conversation:
#: "yesterday" in a 2023 chat means a day in 2023, not yesterday
#: (jarvis_intake.conversation_at, memory-intake.patch).
WHEN: dict = {}


def _parse_time(raw) -> Optional[float]:
    """An export timestamp - ISO 8601 text, or epoch seconds - or None."""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        v = float(raw)
        return v / 1000.0 if v > 1e12 else v
    if not isinstance(raw, str) or not raw.strip():
        return None
    from datetime import datetime
    s = raw.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        pass
    # Python before 3.11 refuses fractional seconds that are not 3 or 6
    # digits; the exports are not consistent about it.
    try:
        head, _, tail = s.partition(".")
        zone = ""
        for mark in ("+", "-"):
            if mark in tail:
                zone = tail[tail.index(mark):]
        return datetime.fromisoformat(head + zone).timestamp()
    except ValueError:
        return None


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
                conv_id = _conv_id("claude", raw_id, turns)
                when = _parse_time(entry.get("created_at") or entry.get("updated_at"))
                if when is not None:
                    WHEN[conv_id] = when
                yield conv_id, turns


# --------------------------------------------------------------------------
#   Gemini / Google Takeout export
# --------------------------------------------------------------------------
#
# Google Takeout, "My Activity" -> "Gemini Apps", set to JSON (its default
# is HTML, which this cannot read): `Takeout/My Activity/Gemini Apps/
# MyActivity.json`, one list of activity RECORDS, newest first:
#
#     {"header": "Gemini Apps", "title": "Prompted <what the owner typed>",
#      "time": "2026-07-26T06:07:57.773Z", "products": ["Gemini Apps"],
#      "safeHtmlItem": [{"html": "<p>Gemini's answer</p>"}], ...}
#
# Checked 2026-09-28 against open-source readers written from real exports
# (420AI's gemini-export.ts, from a 1,452-record export; llm-aggregator's
# geminiTakeout.ts, 875 records); still not a file of the owner's own.
# What they found, and what this does about it:
#
#   * The owner's words are the `title`, after a verb: "Prompted ", and
#     less often "Asked ", "Said ", "Branched ", "Answered " (older ones:
#     "Prompted with: ", "Asked Gemini: ", "Asked Bard: "). The verb is cut
#     off. A title can end "Attached 2 files." - cut off too.
#   * Records that are not something the owner said - "Created" (Canvas),
#     "Used", "Added", "Gave" (feedback), "Selected", "Shared", "Deleted" -
#     are skipped, whatever follows the verb.
#   * Gemini's answer is `safeHtmlItem[].html` (HTML; only its words are
#     kept). It is often missing. Only the owner's words reach the model
#     anyway (owner_words, below).
#   * There is NO conversation id. So records are put back into
#     conversations the way the readers above do: in time order, and a
#     new conversation starts after 30 minutes with nothing said. That
#     gives the model "my sister is Anna ... she loves jazz" together,
#     instead of one line at a time with nothing around it.
#   * A Takeout with more than Gemini in it (Search, YouTube) has records of
#     the same shape; only those whose `header` or `products` say Gemini or
#     Bard are read. For an account in another language those words are
#     translated ("Gemini 앱", "App Gemini") - matched by the word "Gemini"
#     or "Bard" anywhere in them - and so are the verbs: a record with no
#     English verb is read only when it has an answer (so it was a prompt),
#     its whole title kept.

#: A conversation ends after this long with nothing said.
GEMINI_GAP = 30 * 60

_GEMINI_PROMPT = ("Prompted with: ", "Asked Gemini: ", "Asked Bard: ",
                  "Prompted ", "Asked ", "Said ", "Branched ", "Answered ")
_GEMINI_NOT_SAID = ("Created ", "Used ", "Added ", "Gave ", "Selected ", "Shared ",
                    "Deleted ", "Viewed ", "Visited ", "Searched ", "Edited ",
                    "Pinned ", "Renamed ", "Exported ", "Updated ")
_ATTACHED = re.compile(r"\s*Attached \d+ files?\.?\s*$", re.I)


def _gemini_is_gemini(rec: dict) -> bool:
    labels = [rec.get("header")]
    prods = rec.get("products")
    if isinstance(prods, list):
        labels += prods
    labels = [x.strip().lower() for x in labels if isinstance(x, str) and x.strip()]
    if not labels:
        return True   # no label at all: this file is the Gemini Apps one
    return any("gemini" in x or "bard" in x for x in labels)


def _gemini_prompt_text(title: str, has_answer: bool = True) -> str:
    """The owner's words in a record's title, or "" when the record is not
    something the owner said."""
    t = title.strip()
    for prefix in _GEMINI_NOT_SAID:
        if t.startswith(prefix):
            return ""
    for prefix in _GEMINI_PROMPT:
        if t.startswith(prefix):
            return _ATTACHED.sub("", t[len(prefix):]).strip()
    # No English verb: another language, or a shape not seen before. Kept
    # only when Gemini answered it - so it was a prompt - and kept whole.
    return _ATTACHED.sub("", t).strip() if has_answer else ""


def _html_words(html: str) -> str:
    from html.parser import HTMLParser

    class _Words(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.out = []

        def handle_data(self, data):
            self.out.append(data)

        def handle_starttag(self, tag, attrs):
            if tag in ("p", "br", "li", "div", "h1", "h2", "h3", "tr"):
                self.out.append(" ")

    w = _Words()
    try:
        w.feed(html)
        w.close()
    except Exception:
        return ""
    return " ".join("".join(w.out).split())


def _gemini_reply_text(record: dict) -> str:
    parts = []
    items = record.get("safeHtmlItem")
    if isinstance(items, list):
        for it in items:
            html = it.get("html") if isinstance(it, dict) else None
            if isinstance(html, str) and html.strip():
                parts.append(_html_words(html))
    if not any(parts):
        for key in ("subtitles", "details"):
            val = record.get(key)
            if isinstance(val, list):
                got = [v.get("name") if isinstance(v, dict) else v for v in val]
                parts += [g for g in got if isinstance(g, str) and g.strip()]
    return "\n".join(p for p in parts if p and p.strip())


def _gemini_records(path: Path) -> list:
    """Every Gemini prompt in this export as (time, prompt, reply), oldest
    first. Records with no readable time go last, in file order."""
    out = []
    for _label, doc in _walk_json_documents(path):
        records = doc if isinstance(doc, list) else doc.get("Gemini Apps") \
            if isinstance(doc, dict) else None
        if not isinstance(records, list):
            continue
        for rec in records:
            if not isinstance(rec, dict) or not _gemini_is_gemini(rec):
                continue
            title = rec.get("title")
            if not isinstance(title, str) or not title.strip():
                continue
            reply = " ".join(_gemini_reply_text(rec).split())
            prompt = " ".join(_gemini_prompt_text(title, bool(reply)).split())
            if not prompt:
                continue
            out.append((_parse_time(rec.get("time")), prompt, reply))
    far = float("inf")
    out.sort(key=lambda r: far if r[0] is None else r[0])
    return out


def gemini_conversations(path: Path) -> Iterator[tuple[str, list[dict]]]:
    """Yields (id, turns): the Gemini prompts put back into conversations -
    time order, a new one after GEMINI_GAP of silence. A prompt Gemini's
    answer was not captured for is kept, one-sided: "what car does Mario
    want" is worth reading without the answer, and no answer is invented."""
    group: list = []

    def finish(group):
        turns = []
        for _t, prompt, reply in group:
            turns.append({"role": "user", "content": prompt})
            if reply:
                turns.append({"role": "assistant", "content": reply})
        first, last = group[0], group[-1]
        # First and last record in the id: a later export where this
        # conversation grew is offered again (propose()'s own dedupe drops
        # what it already proposed), not skipped as "read before".
        raw = hashlib.sha256(f"{first[0]}|{first[1]}|{last[0]}|{last[1]}|{len(group)}"
                             .encode("utf-8", "replace")).hexdigest()[:20]
        conv_id = _conv_id("gemini", raw, turns)
        if first[0] is not None:
            WHEN[conv_id] = first[0]
        return conv_id, turns

    for rec in _gemini_records(path):
        if group and (rec[0] is None or group[-1][0] is None
                      or rec[0] - group[-1][0] > GEMINI_GAP):
            yield finish(group)
            group = []
        group.append(rec)
    if group:
        yield finish(group)


# --------------------------------------------------------------------------
#   ChatGPT export (added 2026-09-28, the owner's choice)
# --------------------------------------------------------------------------
#
# ChatGPT's "Export data" (Settings, Data controls) emails a link to a .zip
# holding `conversations.json`: ONE list of every conversation, each with
#
#     id / conversation_id, title, create_time (epoch seconds), current_node,
#     mapping: {node id: {"id", "parent", "children": [...],
#                         "message": null | {"author": {"role"},
#                                            "content": {"content_type", "parts"},
#                                            "create_time", "recipient", "weight",
#                                            "metadata": {...}}}}
#
# The mapping is a TREE, not a list: editing a message or asking for another
# answer starts a new branch, and every branch is kept. The conversation as
# the owner last saw it is the chain from `current_node` up through each
# node's `parent` - that chain is what is read here, and the abandoned
# branches are not (an edited-away message is words the owner took back).
#
# Read from each message on that chain, and only:
#   * role "user" or "assistant" - "system" and "tool" (code runs, web
#     pages, plug-in answers) are skipped;
#   * content_type "text" or "multimodal_text", and of its parts only the
#     plain strings - an image, a file or a voice clip is a dict and is
#     skipped, so a picture's own contents are never read;
#   * not hidden (metadata.is_visually_hidden_from_conversation, the
#     custom-instructions and memory messages ChatGPT keeps out of view), not
#     weight 0, and for the assistant only what it said to the owner
#     (recipient "all"), never a call it made to a tool.
# And then run() reads only the owner's turns (owner_words, above).
#
# WRITTEN FROM THE PUBLISHED SHAPE, NOT A REAL FILE: this project has not
# seen the owner's own export. The field names above are the ones ChatGPT's
# export has used for years and that open-source converters read; if a
# future export renames them, this finds 0 conversations and says so, rather
# than guessing.
#
# BIG EXPORTS: conversations.json can be hundreds of megabytes. It is read
# as a stream, one conversation at a time (`_json_items`), so memory holds
# one conversation, never the whole file. One single conversation over
# ONE_ITEM_MAX characters is skipped whole, and said so.

#: A single conversation bigger than this (in characters) is skipped: no
#: real chat is that long, and holding it would mean holding the file.
ONE_ITEM_MAX = 64 * 1024 * 1024
_CHUNK = 1024 * 1024
#: A JSON file that is NOT a list (so cannot be streamed) is read whole only
#: up to this size; bigger ones are skipped and said so.
WHOLE_FILE_MAX = 256 * 1024 * 1024


class TooBig(ValueError):
    pass


def _json_items(fh, size_hint: Optional[int] = None) -> Iterator[object]:
    """The items of a JSON file, one at a time.

    A file whose top level is a list is streamed: each element is decoded on
    its own, so a 500 MB conversations.json never sits in memory whole. Any
    other top level (an object) is yielded as one item, read whole, and
    refused over WHOLE_FILE_MAX. `fh` is a text stream."""
    dec = json.JSONDecoder()
    buf = fh.read(_CHUNK)
    pos = 0
    if buf.startswith("﻿"):
        pos = 1
    while True:
        while pos < len(buf) and buf[pos] in " \t\r\n":
            pos += 1
        if pos < len(buf):
            break
        more = fh.read(_CHUNK)
        if not more:
            return
        buf, pos = buf[pos:] + more, 0
    if buf[pos] != "[":
        if size_hint is not None and size_hint > WHOLE_FILE_MAX:
            raise TooBig("a JSON file too big to read whole")
        rest = fh.read(WHOLE_FILE_MAX + 1)
        text = buf[pos:] + rest
        if len(text) > WHOLE_FILE_MAX:
            raise TooBig("a JSON file too big to read whole")
        yield json.loads(text)
        return
    pos += 1
    want = _CHUNK
    while True:
        # Skip the commas and spaces between elements.
        while True:
            while pos < len(buf) and buf[pos] in " \t\r\n,":
                pos += 1
            if pos < len(buf):
                break
            more = fh.read(_CHUNK)
            if not more:
                return          # a list cut short: what was read is kept
            buf, pos = more, 0
        if buf[pos] == "]":
            return
        while True:
            try:
                item, end = dec.raw_decode(buf, pos)
                break
            except json.JSONDecodeError:
                if len(buf) - pos > ONE_ITEM_MAX:
                    raise TooBig("one conversation too big to read")
                # Double what is read each time, so one big conversation is
                # re-parsed a handful of times, not once per megabyte.
                more = fh.read(want)
                want = min(want * 2, ONE_ITEM_MAX)
                if not more:
                    raise
                buf, pos = buf[pos:] + more, 0
        want = _CHUNK
        if end - pos > ONE_ITEM_MAX:
            # It fitted in what was already read, but it is over the cap:
            # skipped the same as one that did not fit, and the rest read.
            _say("    skipped one conversation too big to read")
        else:
            yield item
        pos = end
        if pos > _CHUNK:
            buf, pos = buf[pos:], 0


def _json_entries(path: Path) -> Iterator[tuple[str, Iterator[object]]]:
    """(label, items) for every .json file in `path` (a .zip, a .json or a
    folder), each file's items streamed by _json_items. Unreadable files are
    skipped with a note, never an abort."""
    if path.is_dir():
        for f in sorted(f for f in path.rglob("*")
                        if f.is_file() and f.suffix.lower() in (".zip", ".json")):
            yield from _json_entries(f)
        return
    if zipfile.is_zipfile(path):
        try:
            with zipfile.ZipFile(path) as z:
                for info in z.infolist():
                    if info.is_dir() or not info.filename.lower().endswith(".json"):
                        continue
                    with z.open(info) as raw:
                        fh = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
                        yield info.filename, _json_items(fh, info.file_size)
        except (zipfile.BadZipFile, OSError) as exc:
            _say(f"  {path.name}: skipped - {type(exc).__name__}")
        return
    if path.suffix.lower() == ".json":
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                yield path.name, _json_items(fh, path.stat().st_size)
        except OSError as exc:
            _say(f"  {path.name}: skipped - {type(exc).__name__}")


def _safe_items(label: str, items: Iterator[object]) -> Iterator[object]:
    """`items`, stopping with a note (never an exception) at a bad file."""
    try:
        yield from items
    except TooBig as exc:
        _say(f"    {label}: skipped the rest - {exc}")
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, zipfile.BadZipFile,
            RuntimeError, EOFError) as exc:
        _say(f"    {label}: unreadable ({type(exc).__name__}), skipped")


_CHATGPT_TEXT = ("text", "multimodal_text")


def _chatgpt_message_text(msg: dict) -> str:
    content = msg.get("content")
    if not isinstance(content, dict):
        return ""
    if content.get("content_type") not in _CHATGPT_TEXT:
        return ""
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ""
    # Only plain strings: an image, a file or a voice clip is a dict.
    return "\n".join(p for p in parts if isinstance(p, str) and p.strip())


def _chatgpt_chain(mapping: dict, current) -> list:
    """The node ids from the root to `current`, oldest first: the branch
    the owner last saw. Without a usable `current_node`, the newest
    branch: from the root, always the last child."""
    chain, seen = [], set()
    node_id = current if isinstance(current, str) and current in mapping else None
    if node_id is not None:
        while isinstance(node_id, str) and node_id in mapping and node_id not in seen:
            seen.add(node_id)
            chain.append(node_id)
            node = mapping.get(node_id)
            node_id = node.get("parent") if isinstance(node, dict) else None
        chain.reverse()
        return chain
    roots = [k for k, v in mapping.items()
             if isinstance(v, dict) and v.get("parent") in (None, "")]
    node_id = roots[0] if roots else None
    while isinstance(node_id, str) and node_id in mapping and node_id not in seen:
        seen.add(node_id)
        chain.append(node_id)
        kids = mapping[node_id].get("children") if isinstance(mapping[node_id], dict) else None
        node_id = kids[-1] if isinstance(kids, list) and kids else None
    return chain


def _chatgpt_turns(convo: dict) -> list[dict]:
    mapping = convo.get("mapping")
    if not isinstance(mapping, dict):
        return []
    turns: list[dict] = []
    for node_id in _chatgpt_chain(mapping, convo.get("current_node")):
        node = mapping.get(node_id)
        msg = node.get("message") if isinstance(node, dict) else None
        if not isinstance(msg, dict):
            continue
        author = msg.get("author")
        role = author.get("role") if isinstance(author, dict) else None
        if role not in ("user", "assistant"):
            continue          # system, tool: never the owner's words
        meta = msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}
        if meta.get("is_visually_hidden_from_conversation") or \
                meta.get("is_user_system_message"):
            continue          # custom instructions, memory notes: kept out of view
        weight = msg.get("weight")
        if isinstance(weight, (int, float)) and not isinstance(weight, bool) and weight == 0:
            continue
        if role == "assistant" and msg.get("recipient") not in (None, "all"):
            continue          # a call to a tool, not words to the owner
        text = " ".join(_chatgpt_message_text(msg).split())
        if not text:
            continue
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"] += " " + text
        else:
            turns.append({"role": role, "content": text})
    return turns


def chatgpt_conversations(path: Path) -> Iterator[tuple[str, list[dict]]]:
    """Yields (id, turns) for every ChatGPT conversation in this export."""
    for label, items in _json_entries(path):
        for item in _safe_items(label, items):
            entries = item if isinstance(item, list) else [item]
            if isinstance(item, dict) and isinstance(item.get("conversations"), list):
                entries = item["conversations"]
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("mapping"), dict) \
                        or _is_deepseek(entry):
                    continue
                turns = _chatgpt_turns(entry)
                # Same rule as the Claude side: a chat with no reply at all,
                # or with no word from the owner, is not offered.
                if len(turns) < 2 or not any(t["role"] == "user" for t in turns):
                    continue
                raw_id = entry.get("conversation_id") or entry.get("id")
                conv_id = _conv_id("chatgpt", raw_id if isinstance(raw_id, str) else None,
                                   turns)
                when = _parse_time(entry.get("create_time") or entry.get("update_time"))
                if when is not None:
                    WHEN[conv_id] = when
                yield conv_id, turns


# --------------------------------------------------------------------------
#   DeepSeek export (added 2026-09-28, the owner's choice)
# --------------------------------------------------------------------------
#
# DeepSeek's "Export data" (Settings, Data) gives a .zip holding
# `conversations.json` (every chat) and `user.json` (the account - never
# read). Each conversation:
#
#     id, title, inserted_at, updated_at,
#     mapping: {node id: {"id", "parent", "children": [...],
#                         "message": null | {"model", "inserted_at", "files",
#                                            "fragments": [{"type", "content"}]}}}
#
# Like ChatGPT's, the mapping is a TREE (an edited question or a retried
# answer starts a branch), with a synthetic "root" node. Unlike ChatGPT's
# there is no `current_node` and no role: WHO spoke is the fragment's type.
#   REQUEST   the owner's words                        - read
#   RESPONSE  DeepSeek's answer                        - kept as the reply
#   THINK     the model's reasoning ("DeepThink")      - skipped
#   SEARCH, TOOL_SEARCH, TOOL_OPEN, TOOL_FIND, FILE    - web results, tools,
#             files: outside text, skipped
# The branch read is the one ending at the newest message (latest
# `inserted_at`), walked back to the root - the conversation as the owner
# last left it. Messages are put in TREE order, never time order: a real
# export has an answer stamped a few milliseconds before its question.
# Times are ISO 8601 with an offset ("2024-12-04T14:51:13.334000+08:00").
#
# Written 2026-09-28 from six open-source readers that agree on this shape
# (llm-archive, Xe/x, owl-brain, pointer, AIArchive, a real sample file in
# GPT-Rewind); not checked against a file of the owner's own. If a future
# export renames these, this finds 0 conversations and says so.

_DS_USER, _DS_REPLY = ("REQUEST",), ("RESPONSE",)


def _deepseek_chain(mapping: dict) -> list:
    """Node ids from the root to the newest leaf, oldest first."""
    leaves = []
    for k, v in mapping.items():
        if not isinstance(v, dict):
            continue
        kids = v.get("children")
        if isinstance(kids, list) and any(isinstance(c, str) and c in mapping for c in kids):
            continue
        msg = v.get("message") if isinstance(v.get("message"), dict) else {}
        leaves.append((_parse_time(msg.get("inserted_at")) or 0.0, k))
    if not leaves:
        return []
    # Newest leaf; on a tie, the one listed last (the later branch).
    node_id = max(enumerate(leaves), key=lambda e: (e[1][0], e[0]))[1][1]
    chain, seen = [], set()
    while isinstance(node_id, str) and node_id in mapping and node_id not in seen:
        seen.add(node_id)
        chain.append(node_id)
        node = mapping.get(node_id)
        node_id = node.get("parent") if isinstance(node, dict) else None
    chain.reverse()
    return chain


def _deepseek_turns(convo: dict) -> list[dict]:
    mapping = convo.get("mapping")
    if not isinstance(mapping, dict):
        return []
    turns: list[dict] = []
    for node_id in _deepseek_chain(mapping):
        node = mapping.get(node_id)
        msg = node.get("message") if isinstance(node, dict) else None
        frags = msg.get("fragments") if isinstance(msg, dict) else None
        if not isinstance(frags, list):
            continue
        for f in frags:
            if not isinstance(f, dict) or not isinstance(f.get("content"), str):
                continue
            kind = str(f.get("type") or "").upper()
            role = "user" if kind in _DS_USER else "assistant" if kind in _DS_REPLY else None
            if role is None:
                continue          # THINK, SEARCH, tools, files
            text = " ".join(f["content"].split())
            if not text:
                continue
            if turns and turns[-1]["role"] == role:
                turns[-1]["content"] += " " + text
            else:
                turns.append({"role": role, "content": text})
    return turns


def _is_deepseek(entry) -> bool:
    """A DeepSeek conversation: a mapping whose messages have fragments."""
    mapping = entry.get("mapping") if isinstance(entry, dict) else None
    if not isinstance(mapping, dict) or "current_node" in entry:
        return False
    for v in mapping.values():
        msg = v.get("message") if isinstance(v, dict) else None
        if isinstance(msg, dict):
            return isinstance(msg.get("fragments"), list)
    return "inserted_at" in entry


def deepseek_conversations(path: Path) -> Iterator[tuple[str, list[dict]]]:
    """Yields (id, turns) for every DeepSeek conversation in this export."""
    for label, items in _json_entries(path):
        for item in _safe_items(label, items):
            entries = item if isinstance(item, list) else [item]
            for entry in entries:
                if not _is_deepseek(entry):
                    continue
                turns = _deepseek_turns(entry)
                if len(turns) < 2 or not any(t["role"] == "user" for t in turns):
                    continue
                raw_id = entry.get("id")
                conv_id = _conv_id("deepseek", raw_id if isinstance(raw_id, str) else None,
                                   turns)
                when = _parse_time(entry.get("inserted_at") or entry.get("updated_at"))
                if when is not None:
                    WHEN[conv_id] = when
                yield conv_id, turns


# --------------------------------------------------------------------------
#   Which export is this? (the Brain's one button takes any of the four)
# --------------------------------------------------------------------------

KINDS = ("chatgpt", "claude", "gemini", "deepseek")
LABELS = {"chatgpt": "ChatGPT", "claude": "Claude", "gemini": "Gemini",
          "deepseek": "DeepSeek"}


def _kind_of_item(item) -> Optional[str]:
    first = item[0] if isinstance(item, list) and item else item
    if isinstance(item, dict) and isinstance(item.get("conversations"), list) \
            and item["conversations"]:
        first = item["conversations"][0]
    if not isinstance(first, dict):
        return None
    if isinstance(first.get("mapping"), dict):
        return "deepseek" if _is_deepseek(first) else "chatgpt"
    if isinstance(first.get("chat_messages"), list):
        return "claude"
    if "title" in first and "time" in first and ("header" in first or "products" in first):
        return "gemini"
    return None


def detect_kind(path: Path) -> Optional[str]:
    """"chatgpt", "claude", "gemini", "deepseek", or None when this is none.

    A Google Takeout Gemini export is known by its folder name. Otherwise
    the first item of each JSON file decides: a `mapping` tree is ChatGPT,
    or DeepSeek when its messages are made of `fragments`; a
    `chat_messages` list is Claude. Only the first item of a file is read.
    """
    names = []
    if path.is_dir():
        names = [str(f.relative_to(path)) for f in path.rglob("*") if f.is_file()]
    elif zipfile.is_zipfile(path):
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
        except (zipfile.BadZipFile, OSError):
            return None
    else:
        names = [path.name]
    low = [n.replace("\\", "/").lower() for n in names]
    if any("gemini apps/" in n or "/bard/" in n for n in low):
        return "gemini"
    claude_hint = False
    for label, items in _json_entries(path):
        for item in _safe_items(label, items):
            kind = _kind_of_item(item)
            if kind:
                return kind
            first = item[0] if isinstance(item, list) and item else item
            if isinstance(first, dict) and first.get("uuid"):
                claude_hint = True   # Claude's index file: ids only
            break
    return "claude" if claude_hint else None


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
                        _say(f"    {name}: unreadable ({type(exc).__name__}), skipped")
        except (zipfile.BadZipFile, OSError) as exc:
            _say(f"  {path.name}: skipped - {type(exc).__name__}: {exc}")
        return
    if path.suffix.lower() == ".json":
        try:
            yield path.name, json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            _say(f"  {path.name}: skipped - {type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------
#   Feeding the review queue
# --------------------------------------------------------------------------

def _dated(when):
    """jarvis_intake.conversation_at(when), or a do-nothing block without it."""
    try:
        import jarvis_intake
        return jarvis_intake.conversation_at(when)
    except Exception:
        import contextlib
        return contextlib.nullcontext()


def local_model_ok(X) -> bool:
    """Is jarvis_extract's model on this machine?

    jarvis_extract.local_model_ok() when memory-intake.patch is applied (the
    same check propose() itself now makes), and otherwise the same test done
    here on X.OLLAMA - so this script refuses even on a backend that does
    not have that patch yet. Anything unparseable or missing is a no.
    """
    check = getattr(X, "local_model_ok", None)
    if callable(check):
        try:
            return bool(check())
        except Exception:
            return False
    try:
        import urllib.parse
        host = (urllib.parse.urlparse(str(getattr(X, "OLLAMA", "") or "")).hostname
                or "").lower()
    except Exception:
        return False
    return host in ("127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1")


def owner_words(turns: list[dict]) -> list[dict]:
    """The turns of one imported chat that propose() may read: the owner's
    own words, and only those - the same cut the live learner makes
    (jarvis_intake.owner_turns, extraction-wiring.patch). Never the other
    assistant's replies. Also left out, as the live learner leaves them out:
    the whole chat when the owner made it a game or role-play, a crisis
    message, and a timer or reminder command. Without jarvis_intake.py, the
    owner's turns as they are."""
    mine = [{"role": "user", "content": t["content"]} for t in turns or []
            if isinstance(t, dict) and t.get("role") == "user"
            and isinstance(t.get("content"), str) and t["content"].strip()]
    try:
        import jarvis_intake as J
    except Exception:
        return mine
    try:
        game = getattr(J, "game_or_roleplay", None)
        if callable(game) and game(mine):
            return []
    except Exception:
        return []
    out = []
    for t in mine:
        text = t["content"]
        try:
            skip = getattr(J, "wellbeing_skip", None)
            if callable(skip) and skip(text):
                continue
            sched = getattr(J, "schedule_command", None)
            if callable(sched) and sched(text):
                continue
        except Exception:
            continue      # cannot tell: leave it out (fail closed)
        out.append(t)
    return out


# --------------------------------------------------------------------------
#   Reading a long chat whole (2026-09-28)
# --------------------------------------------------------------------------
#
# A chat can be hundreds of messages long. Handed to the model in one go it
# does not fit in what the model can read at once, and the start of it is
# lost without a word - which is where people usually say who they are. So
# the owner's words are handed over in PIECES of at most PIECE_CHARS
# characters, each one read whole, each one its own propose() call, all
# dated to the chat. A piece starts with the last message of the one
# before when that is short, so "my sister is Anna" and "she loves jazz"
# are not split from each other. (propose()'s own dedupe drops a fact the
# overlap makes it find twice.)
#
# Left out, because they are very rarely the owner's own words about
# themselves: a single message over PASTED_CHARS characters (a pasted
# email, document or web page), and ``` code blocks. The same reason the
# live learner leaves pasted text out (jarvis_intake.owner_turns).

#: At most this many characters of the owner's words per model call.
PIECE_CHARS = 6000
#: A message longer than this is treated as pasted in, and not read.
PASTED_CHARS = 4000
#: The last message of a piece is repeated at the start of the next one
#: when it is at most this long.
OVERLAP_CHARS = 600

_FENCE = re.compile(r"```.*?(?:```|$)", re.S)


def pieces(mine: list[dict]) -> list[list[dict]]:
    """The owner's turns of one chat (owner_words' result), as the pieces
    the model reads: code blocks and pasted-in messages left out, then
    grouped, in order, to at most PIECE_CHARS characters each. A message
    between OVERLAP_CHARS and PIECE_CHARS long is a piece on its own."""
    kept = []
    for t in mine or []:
        text = " ".join(_FENCE.sub(" ", str(t.get("content") or "")).split())
        if not text or len(text) > PASTED_CHARS:
            continue
        kept.append({"role": "user", "content": text})
    out: list[list[dict]] = []
    cur: list[dict] = []
    size = 0
    for t in kept:
        n = len(t["content"])
        if cur and size + n > PIECE_CHARS:
            out.append(cur)
            last = cur[-1]
            cur = [last] if len(last["content"]) <= OVERLAP_CHARS and \
                len(last["content"]) + n <= PIECE_CHARS else []
            size = sum(len(x["content"]) for x in cur)
        cur.append(t)
        size += n
    if cur:
        out.append(cur)
    return out


def _chat_model() -> Optional[str]:
    """The model the chat uses, so an import does not load a second copy
    of a model onto the graphics card beside it - with a smaller window -
    or ask for one that is not there. The same order the live learner
    uses (jarvis_hud._extract_model): JARVIS_LOCAL_MODEL, then
    jarvis_models.current_model(). None: jarvis_extract's own default."""
    import os
    name = os.environ.get("JARVIS_LOCAL_MODEL", "").strip()
    if name:
        return name
    try:
        import jarvis_models
        name = str(jarvis_models.current_model() or "").strip()
    except Exception:
        name = ""
    return name or None


class _Asker:
    """jarvis_extract's own model call (_local_llm), on the chat's model,
    counting the calls that got no answer at all - the model was not
    running, or timed out. A chat whose reading got no answer is NOT
    marked as read: propose() returns [] then, which would otherwise look
    exactly like "nothing to learn here" and skip the chat for ever."""

    def __init__(self, ask, model):
        self.ask, self.model, self.missed = ask, model, 0

    def __call__(self, prompt, *a, **kw):
        if self.model and not a and "model" not in kw:
            kw["model"] = self.model
        out = self.ask(prompt, *a, **kw)
        if out is None:
            self.missed += 1
        return out


def _asker(X) -> Optional[_Asker]:
    ask = getattr(X, "_local_llm", None)
    return _Asker(ask, _chat_model()) if callable(ask) else None


def _propose(X, piece: list[dict], kind: str, when, asker) -> list:
    """One piece through the same door the live learner uses:
    jarvis_intake.propose, which tells the model the day the chat
    happened (so "last week" becomes a real date) and shows it the stored
    facts closest to what was said (so a correction names the fact it
    replaces). Without jarvis_intake.py or a model call to hand it, the
    plain propose(), dated, as before."""
    source = f"import:{kind}"
    if asker is not None:
        try:
            import jarvis_intake
        except ImportError:
            jarvis_intake = None
        if jarvis_intake is not None and callable(getattr(jarvis_intake, "propose", None)):
            return jarvis_intake.propose(X, piece, asker, source=source, when=when)
    with _dated(when):
        if asker is not None:
            return X.propose(piece, llm=asker, source=source)
        return X.propose(piece, source=source)


#: What the last run() did, for the Brain's button (jarvis_history_import.py)
#: and for the tests. Counts only - never a file name, never a word of a chat.
#:   kinds     the sources read, in order ("chatgpt", ...)
#:   read      conversations found in the export(s)
#:   before    of those, already offered by an earlier run (skipped)
#:   offered   conversations looked at this run
#:   nothing   of those, how many had no words of the owner's left to read
#:             (a game, only a timer command, ...) - the model is not asked
#:   waiting   possible facts propose() added to the review queue this run
#:   pieces    model calls made (a long chat is read in several pieces)
#:   stopped   "done", "queue_full", "cancelled", "refused", "empty" or
#:             "no_model" (the model gave no answer: the chat being read is
#:             not marked read, so the next run reads it)
SUMMARY: dict = {}


def _no_steps(_info: dict) -> None:
    return None


def run(sources: list[tuple[str, Path]], *, say=print, on_step=None,
        cancelled=None) -> int:
    """sources: [("claude", path), ("gemini", path), ("chatgpt", path),
    ("auto", path), ...]. Returns an exit code: 2 when it refused to start.

    `say` takes every line this prints (the Brain's button passes one that
    keeps nothing). `on_step(SUMMARY)` is called after each conversation;
    `cancelled()` is asked before each one, and a True stops the run with
    what was done saved. SUMMARY holds the counts afterwards."""
    global _say
    import jarvis_extract as X  # the real module, from BACKEND

    step = on_step or _no_steps
    SUMMARY.clear()
    SUMMARY.update({"kinds": [], "read": 0, "before": 0, "offered": 0, "nothing": 0,
                    "waiting": 0, "pieces": 0, "stopped": "done"})

    # Before anything is read or marked done: a refusal inside propose()
    # would return [] for every conversation, and each one would then be
    # recorded as "already offered" and skipped for ever after.
    if not local_model_ok(X):
        SUMMARY["stopped"] = "refused"
        say(f"  Refusing to start: OLLAMA_URL is {getattr(X, 'OLLAMA', None)!r}, "
            f"which is not this computer. Your history would have been sent "
            f"there. Point OLLAMA_URL at this machine (for example "
            f"http://127.0.0.1:11434), or remove it, and run this again.")
        return 2

    progress = _load_progress()
    done = set(progress.get("done", []))
    asker = _asker(X)
    seen_this_run = 0
    proposed_this_run = 0
    started = time.time()

    PARSERS = {"claude": claude_conversations, "gemini": gemini_conversations,
               "chatgpt": chatgpt_conversations, "deepseek": deepseek_conversations}
    said_before, _say = _say, say
    try:
        for kind, path in sources:
            if not path.is_file() and not path.is_dir():
                say(f"  {kind}: no such file or folder: {path}")
                continue
            if kind == "auto":
                kind = detect_kind(path) or ""
                if not kind:
                    say(f"  {path.name}: not a ChatGPT, Claude, Gemini or DeepSeek export that "
                        f"this can read - 0 conversations found.")
                    continue
            SUMMARY["kinds"].append(kind)
            say(f"\n=== {kind}: {path} ===")
            found = 0
            for conv_id, turns in PARSERS[kind](path):
                if cancelled is not None and cancelled():
                    SUMMARY["stopped"] = "cancelled"
                    _save_progress(done)
                    say(f"\n  Stopped when asked, after {seen_this_run} new "
                        f"conversation(s) ({proposed_this_run} proposal(s) added). "
                        f"Run it again to carry on.")
                    return 0
                found += 1
                SUMMARY["read"] += 1
                if conv_id in done:
                    SUMMARY["before"] += 1
                    step(SUMMARY)
                    continue
                seen_this_run += 1
                SUMMARY["offered"] = seen_this_run
                parts = pieces(owner_words(turns))
                if not parts:
                    # Nothing of the owner's to read: the model is not asked.
                    SUMMARY["nothing"] += 1
                    done.add(conv_id)
                    step(SUMMARY)
                    continue
                # Dated to when the conversation happened, if the export says.
                # Same propose(), same model, same review queue; a long chat
                # in pieces (see pieces()).
                missed = asker.missed if asker is not None else 0
                for part in parts:
                    proposed = _propose(X, part, kind, WHEN.get(conv_id), asker)
                    SUMMARY["pieces"] += 1
                    proposed_this_run += len(proposed or [])
                    SUMMARY["waiting"] = proposed_this_run
                    if asker is not None and asker.missed > missed:
                        break
                if asker is not None and asker.missed > missed:
                    SUMMARY["stopped"] = "no_model"
                    _save_progress(done)
                    step(SUMMARY)
                    say(f"\n  Stopped: the AI model on this PC did not answer, so this "
                        f"chat was not read. Nothing is lost - start Jarvis's model "
                        f"(Ollama), then run this again to carry on from here.")
                    return 0
                done.add(conv_id)
                step(SUMMARY)

                status = X.setup_status()
                if status.get("queue_full"):
                    SUMMARY["stopped"] = "queue_full"
                    _save_progress(done)
                    say(f"\n  Stopped after {seen_this_run} new conversation(s) this run "
                        f"({proposed_this_run} proposal(s) added) - the review queue is "
                        f"full.")
                    say("  Open the Brain window, review some of what's pending, then "
                        "run this command again to pick up where it left off.")
                    say(f"  Progress saved to {PROGRESS_FILE}")
                    return 0
            if found == 0:
                where = {"claude": "_claude_turns", "gemini": "gemini_conversations",
                         "chatgpt": "_chatgpt_turns", "deepseek": "_deepseek_turns"}[kind]
                say(f"  0 conversations found in this file. If you are sure this is a "
                    f"real {kind} export, the field names in `{where}` probably do not "
                    f"match what this file actually contains - open it and check.")
    finally:
        _say = said_before

    if SUMMARY["read"] == 0:
        SUMMARY["stopped"] = "empty"
    _save_progress(done)
    elapsed = time.time() - started
    say(f"\nDone. {seen_this_run} new conversation(s) offered to the review queue "
        f"this run, {proposed_this_run} proposal(s) added, in {elapsed:.0f}s.")
    say("Nothing became a fact without a decision in the Brain window - review "
        "the queue there when you're ready.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--claude", type=Path, help="a Claude/claude.ai export .zip, "
                    ".json, or a folder holding either")
    ap.add_argument("--gemini", type=Path, help="a Google Takeout export .zip, "
                    ".json, or a folder holding either")
    ap.add_argument("--chatgpt", type=Path, help="a ChatGPT data export .zip, its "
                    "conversations.json, or a folder holding either")
    ap.add_argument("--deepseek", type=Path, help="a DeepSeek data export .zip, its "
                    "conversations.json, or a folder holding either")
    ap.add_argument("--auto", type=Path, help="any of the four: which one it is is "
                    "worked out from the file")
    args = ap.parse_args()

    sources = []
    if args.claude:
        sources.append(("claude", args.claude))
    if args.gemini:
        sources.append(("gemini", args.gemini))
    if args.chatgpt:
        sources.append(("chatgpt", args.chatgpt))
    if args.deepseek:
        sources.append(("deepseek", args.deepseek))
    if args.auto:
        sources.append(("auto", args.auto))
    if not sources:
        ap.error("pass at least one of --chatgpt, --claude, --gemini, --deepseek or --auto")

    try:
        import jarvis_extract  # noqa: F401  (fail fast, with a clear reason)
    except ImportError:
        print(f"Could not import jarvis_extract. {explain()}")
        return 2

    return run(sources)


if __name__ == "__main__":
    sys.exit(main())
