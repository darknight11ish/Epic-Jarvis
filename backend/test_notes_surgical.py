"""test_notes_surgical.py - wave-2 surgical notes edits, proved.

    python -B backend/test_notes_surgical.py

The owner's question (2026-10-31): "does Jarvis have the ability to ... add
something to a part of the note, or change the note in other specific ways -
very specific (add something before this part, or in bold)?"

What this proves, on a temporary vault and a fake gate (no network, no model,
no owner's file):

1. INSERT UNDER A HEADING. One exact `#`..`######` heading, case-insensitive;
   the new line goes at the END of that section (after its last non-empty line,
   before the next heading of the same or a higher level). First, last, middle,
   empty and nested sections; zero or several matching headings refuse with the
   count, no card. LF and CRLF notes are both preserved exactly.
2. INSERT AT AN ANCHOR. One literal anchor, before/after the LINE that holds it;
   zero or several occurrences refuse with the count; the anchor's own bytes
   are untouched.
3. FORMAT A SPAN. One exact occurrence wrapped in `**` (bold) or `*` (italic),
   without altering its bytes; unwrap removes exactly one matching pair; a span
   already wrapped is a no-op (no card); a match inside a fenced code block is
   refused; zero or several occurrences refuse.
4. REPLACE EXACTLY. One literal occurrence, whole-word edges checked (a match
   inside a longer word refuses and says so); zero or several refuse; no regex.
5. THE CARD SHOWS THE EXACT CHANGE. The gate's detail carries the before/after
   text (bounded) or, while the hidden lists hide the words, a counts-only
   preview; a Deny/expiry/guardian failure/TOCTOU writes nothing; the File
   Guardian copy is taken first and can put the exact bytes back.
6. THE CHAT PATHS. "add ... under the X heading in my workout log", "add ...
   before/after ... in my ...", "make ... bold/italic", "unbold ...", "replace
   ... with ..." - deterministic, no model, hidden lists refuse with no title
   and no card; "add milk to my workout log" still appends at the end (wave 1);
   an ordinary "make it bold" with no note stays the model's.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import sys
import tempfile
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
os.environ.pop("JARVIS_BACKEND", None)
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_notes_edit.py", "jarvis_quick.py")

_TMP = Path(tempfile.gettempdir()) / ("jarvis-notes-surgical-" + secrets.token_hex(6))
_TMP.mkdir(parents=True, exist_ok=True)
VAULT = _TMP / "vault"
(VAULT / ".obsidian").mkdir(parents=True, exist_ok=True)
CONF = _TMP / "config"
CONF.mkdir(exist_ok=True)
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONF)
os.environ["JARVIS_RECEIPTS_DB"] = str(_TMP / "receipts.db")
os.environ["JARVIS_OBSIDIAN_VAULT"] = str(VAULT)

FW = types.ModuleType("jarvis_framework")
FW.CONFIG_DIR = CONF
FW.LOG_DIR = _TMP / "log"
FW.load_framework = lambda: {"notes": {"obsidian": {"vault_directory": str(VAULT)}}}
FW.action_tier = lambda action: "ask" if action == "edit_vault_note" else "auto"
FW.audit_log = lambda event, detail: None
sys.modules["jarvis_framework"] = FW

_GATE_MODULE = types.ModuleType("jarvis_gate")


class _Approved:
    allowed = True
    outcome = "approved"
    tier = "auto"
    reason = ""


_GATE_MODULE.check = lambda *a, **k: _Approved()
_GATE_MODULE.taint_active = lambda: False
sys.modules["jarvis_gate"] = _GATE_MODULE

import jarvis_notes_edit as E  # noqa: E402
import jarvis_quick as Q  # noqa: E402

try:
    import jarvis_file_guardian as GU
except Exception:                                           # noqa: BLE001
    GU = None
try:
    import jarvis_protection as PROTECTION
except Exception:                                           # noqa: BLE001
    PROTECTION = None

FAILED, PASSED, SKIPPED = [], [], []


def skip(name, why):
    SKIPPED.append(name)
    print(f"skip  {name}: {why}")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if not cond else ""))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def reset_vault():
    for child in list(VAULT.iterdir()):
        if child.name == ".obsidian":
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
    E._reset_for_tests()
    if PROTECTION is not None:
        PROTECTION._reset_for_tests()


def write_note(rel, text):
    p = VAULT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
    return p


def read(rel):
    return (VAULT / rel).read_bytes()


class Verdict:
    def __init__(self, allowed=True, tier="ask", outcome="approved", reason=""):
        self.allowed = allowed
        self.tier = tier
        self.outcome = outcome
        self.reason = reason


class Gate:
    def __init__(self, allowed=True, outcome="approved", hook=None):
        self.allowed = allowed
        self.outcome = outcome
        self.hook = hook
        self.calls = []

    def __call__(self, action, detail, prompt):
        self.calls.append((action, dict(detail or {}), prompt))
        if self.hook is not None:
            self.hook()
        return Verdict(self.allowed, "ask", self.outcome)


def set_gate(g):
    E._gate_check = g


def wait_job(jid, timeout=8.0):
    end = time.time() + timeout
    code, out = E.change_status(jid)
    while out.get("state") == "waiting" and time.time() < end:
        time.sleep(0.02)
        code, out = E.change_status(jid)
    return code, out


def run_route(handler, body, *, gate=None, wait_s=0.08):
    gate = gate or Gate()
    set_gate(gate)
    code, out = handler(body, gate_check=gate, wait_s=wait_s)
    if code == 202 and out.get("id"):
        code, out = wait_job(out["id"])
    return code, out, gate


def body_for(rel, **kw):
    b = {"path": rel, "expected_sha256": sha(read(rel))}
    b.update(kw)
    return b


WORKOUT = """# Workout log

Notes for the week.

## Warm-up
- 5 min bike

## Strength
- squats 3x5
- bench 3x5

## Cardio
- run 20 min
"""


def fresh(rel="workout log.md", text=WORKOUT):
    reset_vault()
    write_note(rel, text)
    return rel


# --------------------------------------------------------------------------
# 1. Insert under a heading
# --------------------------------------------------------------------------
def t_insert_under_middle_last_first_and_empty_sections():
    rel = fresh()
    code, out, gate = run_route(E.handle_insert,
                                body_for(rel, text="plank 3x30", mode="under_heading",
                                         target="Strength"))
    text = read(rel).decode()
    check("heading insert: route answers saved", code == 200 and out.get("state") == "saved",
          f"{code} {out}")
    check("heading insert: the new line is the last line of the Strength section",
          "- bench 3x5\nplank 3x30\n\n## Cardio" in text, text)
    check("heading insert: ONE card", len(gate.calls) == 1, gate.calls)
    preview = gate.calls[0][1].get("preview") or {}
    check("heading insert: the card shows the exact before/after",
          "bench 3x5" in str(preview.get("before")) and "plank 3x30" in str(preview.get("after")),
          preview)
    check("heading insert: the prompt names the file and the heading",
          "workout log.md" in gate.calls[0][2] and "Strength" in gate.calls[0][2],
          gate.calls[0][2])
    # last section
    code, out, _g = run_route(E.handle_insert,
                              body_for(rel, text="cool down", mode="under_heading",
                                       target="Cardio"))
    text = read(rel).decode()
    check("heading insert: the last section grows at the end of the file",
          text.rstrip().endswith("cool down"), text[-80:])
    # first section
    code, out, _g = run_route(E.handle_insert,
                              body_for(rel, text="jumping jacks", mode="under_heading",
                                       target="Warm-up"))
    text = read(rel).decode()
    check("heading insert: the first section grows before the second heading",
          "- 5 min bike\njumping jacks\n\n## Strength" in text, text)
    # empty section, then nested headings
    rel2 = fresh("empty.md", "## Empty\n\n## Next\nx\n")
    code, out, _g = run_route(E.handle_insert,
                              body_for(rel2, text="first line", mode="under_heading",
                                       target="Empty"))
    text2 = read(rel2).decode()
    check("heading insert: an empty section gets the line right after its heading",
          "## Empty\nfirst line\n" in text2, text2)
    rel3 = fresh("nested.md", "## A\n### B\ntext under B\n## C\nend\n")
    code, out, _g = run_route(E.handle_insert,
                              body_for(rel3, text="after B", mode="under_heading",
                                       target="A"))
    text3 = read(rel3).decode()
    check("heading insert: a nested heading stays inside the outer section",
          "text under B\nafter B\n## C" in text3, text3)


def t_insert_under_heading_zero_and_several_refuse():
    rel = fresh("two.md", "## Warm-up\na\n## Warm-up\nb\n")
    code, out, gate = run_route(E.handle_insert,
                                body_for(rel, text="x", mode="under_heading",
                                         target="Warm-up"))
    check("heading insert: two matching headings refuse with the count",
          code == 400 and "2" in str(out.get("error")) and "Warm-up" in str(out.get("error")),
          f"{code} {out}")
    check("heading insert: ... and ask no card", gate.calls == [], gate.calls)
    code, out, gate = run_route(E.handle_insert,
                                body_for(rel, text="x", mode="under_heading",
                                         target="Missing"))
    check("heading insert: no matching heading refuses with the count",
          code == 400 and "no" in str(out.get("error")).lower(), f"{code} {out}")
    check("heading insert: ... and asks no card", gate.calls == [])


def t_insert_preserves_crlf():
    rel = fresh("crlf.md", "# T\r\n\r\n## A\r\nold\r\n\r\n## B\r\nlast\r\n")
    code, out, _g = run_route(E.handle_insert,
                              body_for(rel, text="new", mode="under_heading", target="A"))
    data = read(rel).decode()
    check("heading insert: CRLF notes stay CRLF",
          "\r\nnew\r\n\r\n## B" in data
          and "\n" not in data.replace("\r\n", ""),
          repr(data[-60:]))
    rel2 = fresh("lf.md", "# T\n\n## A\nold\n\n## B\nlast\n")
    code, out, _g = run_route(E.handle_insert,
                              body_for(rel2, text="new", mode="under_heading", target="A"))
    check("heading insert: LF notes stay LF", "\r" not in read(rel2).decode())


# --------------------------------------------------------------------------
# 2. Insert at an anchor
# --------------------------------------------------------------------------
def t_insert_before_and_after_an_anchor():
    rel = fresh()
    before = read(rel)
    code, out, gate = run_route(E.handle_insert,
                                body_for(rel, text="mobility", mode="before",
                                         target="squats 3x5"))
    text = read(rel).decode()
    check("anchor insert: before puts its own line above the anchor's line",
          "mobility\n- squats 3x5\n" in text, text)
    check("anchor insert: the anchor's bytes are untouched", "- squats 3x5" in text)
    preview = gate.calls[0][1].get("preview") or {}
    check("anchor insert: the card shows the anchor line and the new line",
          "squats 3x5" in str(preview.get("before"))
          and "mobility" in str(preview.get("after")), preview)
    code, out, _g = run_route(E.handle_insert,
                              body_for(rel, text="stretch", mode="after",
                                       target="squats 3x5"))
    text = read(rel).decode()
    check("anchor insert: after puts its own line below the anchor's line",
          "- squats 3x5\nstretch\n" in text, text)
    check("anchor insert: no bytes were changed except the new lines",
          read(rel).decode().replace("mobility\n", "").replace("stretch\n", "") == before.decode(),
          read(rel).decode())


def t_insert_anchor_zero_and_several_refuse():
    rel = fresh("a.md", "one two one\n")
    code, out, gate = run_route(E.handle_insert,
                                body_for(rel, text="x", mode="before", target="one"))
    check("anchor insert: several occurrences refuse with the count",
          code == 400 and "2" in str(out.get("error")), f"{code} {out}")
    check("anchor insert: ... and ask no card", gate.calls == [])
    code, out, gate = run_route(E.handle_insert,
                                body_for(rel, text="x", mode="after", target="absent"))
    check("anchor insert: zero occurrences refuses",
          code == 400 and "could not find" in str(out.get("error")).lower(), f"{code} {out}")
    check("anchor insert: ... and asks no card", gate.calls == [])


def t_insert_after_the_last_line_with_no_final_newline():
    rel = fresh("tail.md", "head\nanchor words")
    code, out, _g = run_route(E.handle_insert,
                              body_for(rel, text="after it", mode="after",
                                       target="anchor words"))
    text = read(rel).decode()
    check("anchor insert: an anchor on the last line gets the new line after it",
          text.replace("\r\n", "\n") == "head\nanchor words\nafter it\n", repr(text))


# --------------------------------------------------------------------------
# 3. Format a span
# --------------------------------------------------------------------------
def t_bold_italic_and_unwrap():
    rel = fresh()
    code, out, gate = run_route(E.handle_format,
                                body_for(rel, target="squats 3x5", style="bold",
                                         action="add"))
    text = read(rel).decode()
    check("format: bold wraps the one exact span", "**squats 3x5**" in text, text)
    preview = gate.calls[0][1].get("preview") or {}
    check("format: the card shows the wrapped span",
          "**squats 3x5**" in str(preview.get("after")), preview)
    check("format: ONE card", len(gate.calls) == 1)
    code, out, gate = run_route(E.handle_format,
                                body_for(rel, target="bench 3x5", style="italic",
                                         action="add"))
    text = read(rel).decode()
    check("format: italic wraps the one exact span", "*bench 3x5*" in text, text)
    code, out, gate = run_route(E.handle_format,
                                body_for(rel, target="squats 3x5", style="bold",
                                         action="remove"))
    text = read(rel).decode()
    check("format: unbold removes exactly the one pair", "squats 3x5" in text
          and "**squats 3x5**" not in text, text)
    check("format: the italic span next to it is untouched", "*bench 3x5*" in text)


def t_format_refusals_and_noops():
    rel = fresh("f.md", "**done** and done again\n")
    code, out, gate = run_route(E.handle_format,
                                body_for(rel, target="done", style="bold", action="add"))
    check("format: text that appears twice refuses with the count",
          code == 400 and "2" in str(out.get("error")), f"{code} {out}")
    check("format: ... and asks no card", gate.calls == [])
    code, out, gate = run_route(E.handle_format,
                                body_for(rel, target="done", style="bold", action="remove"))
    check("format: remove on a twice-occurring target refuses too",
          code == 400 and "2" in str(out.get("error")), f"{code} {out}")
    rel2 = fresh("g.md", "**already** plain\n")
    code, out, gate = run_route(E.handle_format,
                                body_for(rel2, target="already", style="bold",
                                         action="add"))
    check("format: already-bold is a no-op with no card",
          code == 200 and out.get("state") == "unchanged" and gate.calls == [],
          f"{code} {out}")
    code, out, gate = run_route(E.handle_format,
                                body_for(rel2, target="already", style="italic",
                                         action="add"))
    check("format: italic may wrap bold text (standard Markdown)",
          code == 200 and "***already***" in read(rel2).decode(), f"{code} {out}")
    rel3 = fresh("fence.md", "text\n```\ncode here\n```\nend\n")
    code, out, gate = run_route(E.handle_format,
                                body_for(rel3, target="code here", style="bold",
                                         action="add"))
    check("format: a match inside a code fence refuses",
          code == 400 and "code block" in str(out.get("error")).lower(), f"{code} {out}")
    check("format: ... and asks no card", gate.calls == [])


# --------------------------------------------------------------------------
# 4. Replace exactly
# --------------------------------------------------------------------------
def t_replace_one_exact_occurrence():
    rel = fresh()
    before = read(rel)
    code, out, gate = run_route(E.handle_replace,
                                body_for(rel, old="squats 3x5", new="lunges 3x8"))
    text = read(rel).decode()
    check("replace: route answers saved", code == 200 and out.get("state") == "saved",
          f"{code} {out}")
    check("replace: the exact words are gone and the new ones are there",
          "squats 3x5" not in text and "lunges 3x8" in text, text)
    preview = gate.calls[0][1].get("preview") or {}
    check("replace: the card shows old and new lines",
          "squats 3x5" in str(preview.get("before"))
          and "lunges 3x8" in str(preview.get("after")), preview)
    if GU is None:
        skip("replace: undo walk", "jarvis_file_guardian is not on this tree")
        return
    restored = GU.restore_version(str(VAULT / rel), sha(before),
                                  gate=lambda a, d, p: Verdict(True))
    check("replace: undo puts the exact bytes back", read(rel) == before, restored)


def t_replace_refusals():
    rel = fresh("r.md", "one two two three\n")
    code, out, gate = run_route(E.handle_replace,
                                body_for(rel, old="two", new="four"))
    check("replace: several occurrences refuse with the count",
          code == 400 and "2" in str(out.get("error")), f"{code} {out}")
    check("replace: ... and ask no card", gate.calls == [])
    code, out, gate = run_route(E.handle_replace,
                                body_for(rel, old="four", new="five"))
    check("replace: zero occurrences refuse",
          code == 400 and "could not find" in str(out.get("error")).lower(), f"{code} {out}")
    rel2 = fresh("w.md", "squats only\n")
    code, out, gate = run_route(E.handle_replace,
                                body_for(rel2, old="squat", new="press"))
    check("replace: part of a longer word refuses and says so",
          code == 400 and "longer word" in str(out.get("error")).lower(), f"{code} {out}")
    code, out = E.handle_replace({"path": rel2, "old": "x", "new": "x",
                                        "expected_sha256": sha(read(rel2))})
    check("replace: old and new the same refuses", code == 400, f"{code} {out}")


# --------------------------------------------------------------------------
# 5. Nothing writes without the card; previews stay bounded
# --------------------------------------------------------------------------
def t_deny_expiry_guardian_toctou_and_preview_bounds():
    rel = fresh()
    before = read(rel)
    gate = Gate(allowed=False, outcome="denied")
    code, out, _g = run_route(E.handle_insert,
                              body_for(rel, text="x", mode="under_heading",
                                       target="Strength"), gate=gate)
    check("guard: a Deny writes nothing", read(rel) == before and out.get("state") == "denied",
          f"{code} {out}")
    check("guard: ... with the module's own words",
          "You said no, so nothing was changed." in str(out.get("message")), out)
    gate = Gate(allowed=False, outcome="timed_out")
    code, out, _g = run_route(E.handle_format,
                              body_for(rel, target="squats 3x5", style="bold",
                                       action="add"), gate=gate)
    check("guard: an expiry writes nothing", read(rel) == before)
    old_snap = E._snapshot
    try:
        E._snapshot = lambda full, relpath: {"ok": False, "error": "no copy",
                                             "words": "The copy could not be saved."}
        code, out, _g = run_route(E.handle_replace,
                                  body_for(rel, old="squats 3x5", new="x"))
        check("guard: no guardian copy -> failed, unchanged",
              out.get("state") == "failed" and read(rel) == before, f"{code} {out}")
    finally:
        E._snapshot = old_snap
    # TOCTOU: change the note while the card is up
    changed = Gate(hook=lambda: (VAULT / rel).write_bytes(
        (VAULT / rel).read_bytes() + b"\nchanged while waiting\n"))
    code, out, _g = run_route(E.handle_insert,
                              body_for(rel, text="x", mode="before",
                                       target="squats 3x5"), gate=changed)
    check("guard: a change while the card waited ends failed",
          out.get("state") == "failed", f"{code} {out}")


def t_preview_is_bounded_and_counts_only_when_hidden():
    rel = fresh()
    gate = Gate()
    code, out, _g = run_route(E.handle_replace,
                              body_for(rel, old="squats 3x5", new="lunges 3x8"),
                              gate=gate)
    preview = gate.calls[0][1].get("preview") or {}
    check("preview: before/after are bounded strings",
          isinstance(preview.get("before"), str) and len(preview["before"]) <= 300
          and isinstance(preview.get("after"), str), preview)
    old_hidden = E._hidden_lists
    try:
        E._hidden_lists = lambda: True
        gate = Gate()
        code, out, _g = run_route(E.handle_format,
                                  body_for(rel, target="bench 3x5", style="bold",
                                           action="add"), gate=gate)
        preview = gate.calls[0][1].get("preview") or {}
        check("preview: hidden lists show counts only, no words",
              preview.get("counts_only") is True
              and "bench 3x5" not in json.dumps(preview), preview)
    finally:
        E._hidden_lists = old_hidden


# --------------------------------------------------------------------------
# 6. The chat paths
# --------------------------------------------------------------------------
class Stub:
    def mark_command(self, text):
        pass

    def forget_set(self, conversation):
        pass

    def note_set(self, *a, **k):
        pass

    def last_set(self, *a, **k):
        return None

    def add_at(self, kind, at, text, source="quick"):
        return {"id": "stub-" + kind, "text": text, "due": at, "kind": kind}

    def add_todo(self, text, *a, **k):
        return {"id": "stub-todo", "text": text}

    def add_note(self, text, *a, **k):
        return {"id": "stub-note", "text": text}


def ask(text):
    return Q.answer(text, sched=Stub(), now=time.time(),
                    peer="127.0.0.1", local=True)


def t_chat_surgical_sentences():
    rel = fresh()
    got = ask("add plank under the Strength heading in my workout log")
    text = read(rel).decode()
    check("chat: 'add ... under the X heading in my workout log' is the heading insert",
          got is not None and got.intent == "note_inserted", got.intent if got else "model")
    check("chat: ... and the line is at the end of that section",
          "- bench 3x5\nplank\n" in text, text)
    got = ask("add mobility before squats 3x5 in my workout log")
    text = read(rel).decode()
    check("chat: 'add ... before ... in my ...' is the anchor insert",
          got is not None and got.intent == "note_inserted"
          and "mobility\n- squats 3x5" in text, got.intent if got else "model")
    got = ask("make bench 3x5 bold in my workout log")
    check("chat: 'make ... bold in my ...' formats the span",
          got is not None and got.intent == "note_formatted"
          and "**bench 3x5**" in read(rel).decode(), got.reply if got else "model")
    got = ask("put bench 3x5 in italic in my workout log")
    check("chat: 'put ... in italic' formats the span",
          got is not None and got.intent == "note_formatted", got.reply if got else "model")
    got = ask("unbold bench 3x5 in my workout log")
    check("chat: 'unbold ...' removes the bold",
          got is not None and got.intent == "note_formatted"
          and "**bench 3x5**" not in read(rel).decode(), got.reply if got else "model")
    got = ask("replace bench 3x5 with press 3x5 in my workout log")
    check("chat: 'replace ... with ...' replaces exactly",
          got is not None and got.intent == "note_replaced"
          and "press 3x5" in read(rel).decode(), got.intent if got else "model")
    # wave-1 append still wins for a plain add
    got = ask("add milk to my workout log")
    check("chat: 'add milk to my workout log' is still the wave-1 append-at-end",
          got is not None and got.intent == "note_appended", got.intent if got else "model")
    check("chat: ... and the words are at the very end",
          read(rel).decode().rstrip().endswith("milk"), read(rel).decode()[-80:])
    # no note named -> not ours
    got = ask("make it bold")
    check("chat: an ordinary 'make it bold' with no note is not a note edit",
          got is None or got.intent not in
          ("note_formatted", "note_inserted", "note_replaced"),
          got.intent if got else "model")


def t_chat_hidden_refuses_without_a_card():
    rel = fresh()
    old_hidden = Q._calendar_hidden
    gate = Gate()
    set_gate(gate)
    try:
        Q._calendar_hidden = lambda: (True, "Words hidden.")
        for sentence in ("add plank under the Strength heading in my workout log",
                         "add mobility before squats 3x5 in my workout log",
                         "make bench 3x5 bold in my workout log",
                         "replace bench 3x5 with press in my workout log"):
            got = ask(sentence)
            check(f"chat hidden: {sentence!r} refuses with no card",
                  got is not None and got.intent == "note_write_hidden"
                  and gate.calls == [], got.intent if got else "model")
            check("chat hidden: ... no title and no words leak",
                  got is not None and "workout log" not in got.reply
                  and "Strength" not in got.reply, got.reply if got else "")
    finally:
        Q._calendar_hidden = old_hidden


# --------------------------------------------------------------------------
# 7. Records
# --------------------------------------------------------------------------
def _same_text(a, b):
    try:
        return (a.read_bytes().replace(b"\r\n", b"\n")
                == b.read_bytes().replace(b"\r\n", b"\n"))
    except OSError:
        return False


def t_twins_and_docs_agree():
    for name in ("jarvis_notes_edit.py", "jarvis_quick.py"):
        check(f"records: {name} has a byte-identical published twin",
              _same_text(HERE / name, REPO / "jarvis-backend" / name))
    api = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    for route in ("/api/notes/insert", "/api/notes/format", "/api/notes/replace"):
        check(f"docs: JARVIS-API.md documents {route}", route in api)


# --------------------------------------------------------------------------
# 8. Wave 3 - more formatting, line shapes, headings, properties, links,
#    templates. Same route, same card, same undo.
# --------------------------------------------------------------------------
def t_wave3_more_formatting_strike_and_code():
    rel = fresh("fmt.md", "alpha beta gamma\n")
    code, out, gate = run_route(E.handle_customize,
                                body_for(rel, action="format", style="strike",
                                         target="beta", format_action="add"))
    text = read(rel).decode()
    check("wave3: strike wraps the span", code == 200 and "~~beta~~" in text, f"{code} {out}")
    code, out, _g = run_route(E.handle_customize,
                              body_for(rel, action="format", style="strike",
                                       target="beta", format_action="remove"))
    check("wave3: removing strike unwraps exactly", "~~beta~~" not in read(rel).decode())
    code, out, _g = run_route(E.handle_customize,
                              body_for(rel, action="format", style="code",
                                       target="gamma", format_action="add"))
    check("wave3: inline code wraps the span", "`gamma`" in read(rel).decode(), read(rel).decode())
    code, out, _g = run_route(E.handle_customize,
                              body_for(rel, action="format", style="code",
                                       target="gamma", format_action="remove"))
    check("wave3: removing inline code unwraps it", "`gamma`" not in read(rel).decode())


def t_wave3_lines_checklists_and_headings():
    rel = fresh("lines.md", "milk\neggs\n- [ ] bread\n")
    code, out, _g = run_route(E.handle_customize,
                              body_for(rel, action="line", line_action="checklist",
                                       target="milk"))
    check("wave3: a line becomes a checklist item", "- [ ] milk" in read(rel).decode(),
          read(rel).decode())
    code, out, _g = run_route(E.handle_customize,
                              body_for(rel, action="line", line_action="tick",
                                       target="- [ ] bread"))
    check("wave3: a checklist item can be ticked",
          "- [x] bread" in read(rel).decode(), read(rel).decode())
    code, out, _g = run_route(E.handle_customize,
                              body_for(rel, action="line", line_action="untick",
                                       target="- [x] bread"))
    check("wave3: a ticked item can be unticked",
          code == 200 and "- [x] bread" not in read(rel).decode(), f"{code} {out}")
    code, out, _g = run_route(E.handle_customize,
                              body_for(rel, action="line", line_action="untick",
                                       target="- [ ] bread"))
    check("wave3: untick refuses when it is not ticked",
          code == 400 and "not ticked" in str(out.get("error")), f"{code} {out}")
    code, out, _g = run_route(E.handle_customize,
                              body_for(rel, action="line", line_action="bullet",
                                       target="eggs"))
    check("wave3: a line becomes a bullet", "- eggs" in read(rel).decode())
    code, out, _g = run_route(E.handle_customize,
                              body_for(rel, action="line", line_action="heading",
                                       target="- eggs", level=2))
    check("wave3: a line becomes a heading", "## eggs" in read(rel).decode(),
          f"{code} {out} {read(rel).decode()!r}")
    code, out, _g = run_route(E.handle_customize,
                              body_for(rel, action="line", line_action="plain",
                                       target="## eggs"))
    check("wave3: a heading goes back to plain text", "## eggs" not in read(rel).decode())
    # a line that is not unique refuses
    rel2 = fresh("dupe.md", "same\nsame\n")
    code, out, gate = run_route(E.handle_customize,
                                body_for(rel2, action="line", line_action="bullet",
                                         target="same"))
    check("wave3: two identical lines refuse with the count, no card",
          code == 400 and "2" in str(out.get("error")) and gate.calls == [], f"{code} {out}")


def t_wave3_heading_rename_and_new_section():
    rel = fresh("sections.md", "# Log\n\n## Warm-up\n- a\n\n## Cardio\n- b\n")
    code, out, _g = run_route(E.handle_customize,
                              body_for(rel, action="rename_heading", old="Cardio",
                                       new="Conditioning"))
    text = read(rel).decode()
    check("wave3: renaming one heading keeps its level",
          "## Conditioning" in text and "## Cardio" not in text, text)
    code, out, _g = run_route(E.handle_customize,
                              body_for(rel, action="new_section", heading="Notes",
                                       text="- [ ] check form"))
    text = read(rel).decode()
    check("wave3: a new section is appended with its heading and body",
          "## Notes\n\n- [ ] check form" in text, text)
    code, out, gate = run_route(E.handle_customize,
                                body_for(rel, action="new_section", heading="Notes"))
    check("wave3: a duplicate section heading refuses",
          code == 400 and "already" in str(out.get("error")).lower(), f"{code} {out}")


def t_wave3_properties():
    rel = fresh("props.md", "---\ntitle: Log\n---\nbody\n")
    code, out, _g = run_route(E.handle_customize,
                              body_for(rel, action="set_property", key="status",
                                       value="active"))
    text = read(rel).decode()
    check("wave3: a property is set in the front matter",
          "status: \"active\"" in text and "title: Log" in text and "body" in text,
          text)
    code, out, _g = run_route(E.handle_customize,
                              body_for(rel, action="set_property", key="done",
                                       value="true"))
    check("wave3: a boolean value is written unquoted", "done: true" in read(rel).decode())
    code, out, _g = run_route(E.handle_customize,
                              body_for(rel, action="remove_property", key="status"))
    check("wave3: one property is removed and the rest kept",
          "status:" not in read(rel).decode() and "title: Log" in read(rel).decode())
    rel2 = fresh("bad.md", "---\ntitle: x\nbody\n")
    code, out, gate = run_route(E.handle_customize,
                                body_for(rel2, action="set_property", key="k", value="v"))
    check("wave3: malformed front matter refuses before any card",
          code == 400 and gate.calls == [], f"{code} {out}")


def t_wave3_wikilinks():
    rel = fresh("link.md", "# Index\n")
    code, out, gate = run_route(E.handle_customize,
                                body_for(rel, action="link", note="Workout log"))
    text = read(rel).decode()
    check("wave3: a wikilink line is appended", "[[Workout log]]" in text, text)
    code, out, _g = run_route(E.handle_customize,
                              body_for(rel, action="link", note="Workout log"))
    check("wave3: the same link twice is a no-op with no card",
          code == 200 and out.get("state") == "unchanged", f"{code} {out}")


def t_wave3_templates():
    reset_vault()
    # built-in templates create ONE note from a defined body
    got = ask("create a workout log")
    check("wave3: 'create a workout log' creates the note",
          got is not None and got.intent == "template_created", got.intent if got else "model")
    body = (VAULT / "workout log.md").read_text(encoding="utf-8")
    check("wave3: ... with warm-up/session/cool-down/notes checkboxes",
          "## Warm-up" in body and "## Session" in body
          and "## Cool-down" in body and "## Notes" in body, body)
    check("wave3: ... and a second one is refused at the same name",
          (ask("create a workout log").intent if ask("create a workout log") else "") in
          ("template_create_refused",), "")
    got = ask("save my workout log as a template called My workout")
    check("wave3: 'save ... as a template' writes into the template folder",
          got is not None and got.intent == "template_saved", got.reply if got else "model")
    template_file = VAULT / "Templates" / "My workout.md"
    check("wave3: ... and the template file exists with the note's words",
          template_file.is_file()
          and "## Warm-up" in template_file.read_text(encoding="utf-8"),
          str(template_file))
    got = ask("list my templates")
    check("wave3: 'list my templates' lists names only",
          got is not None and got.intent == "template_listed"
          and "my workout" in got.reply.lower(), got.reply if got else "model")
    # the module's read route lists names, never text
    code, listed = E.handle_templates_list()
    check("wave3: GET templates lists names and no text",
          code == 200 and any("my workout" == str(n).lower()
                              for n in listed.get("templates", []))
          and "text" not in json.dumps(listed), listed)


def t_wave3_chat_sentences_hidden_and_create_workout_note():
    rel = fresh("chat.md", "alpha\nbeta\n")
    got = ask("turn alpha into a checklist item in my chat")
    check("wave3 chat: a line becomes a checklist item",
          got is not None and got.intent == "note_customized"
          and "- [ ] alpha" in read(rel).decode(), got.reply if got else "model")
    got = ask("set status to active in my chat")
    check("wave3 chat: a property is set",
          got is not None and got.intent == "note_customized"
          and "status:" in read(rel).decode(), got.reply if got else "model")
    got = ask("add a link to Workout log in my chat")
    check("wave3 chat: a wikilink is added",
          got is not None and got.intent == "note_customized"
          and "[[workout log]]" in read(rel).decode().lower(), got.reply if got else "model")
    # hidden lists: every wave-3 sentence refuses with no title and no card
    old_hidden = Q._calendar_hidden
    try:
        Q._calendar_hidden = lambda: (True, "Words hidden.")
        gate = Gate()
        set_gate(gate)
        for sentence in ("create a workout log", "list my templates",
                         "turn alpha into a checklist item in my chat",
                         "set status to active in my chat"):
            got = ask(sentence)
            check(f"wave3 hidden: {sentence!r} refuses with no card",
                  got is not None and got.intent == "note_write_hidden"
                  and gate.calls == [], got.intent if got else "model")
            check("wave3 hidden: ... no title or template name leaks",
                  got is not None and "workout" not in got.reply.lower()
                  and "chat" not in got.reply.lower(), got.reply if got else "")
    finally:
        Q._calendar_hidden = old_hidden

TESTS = [
    t_insert_under_middle_last_first_and_empty_sections,
    t_insert_under_heading_zero_and_several_refuse,
    t_insert_preserves_crlf,
    t_insert_before_and_after_an_anchor,
    t_insert_anchor_zero_and_several_refuse,
    t_insert_after_the_last_line_with_no_final_newline,
    t_bold_italic_and_unwrap,
    t_format_refusals_and_noops,
    t_replace_one_exact_occurrence,
    t_replace_refusals,
    t_deny_expiry_guardian_toctou_and_preview_bounds,
    t_preview_is_bounded_and_counts_only_when_hidden,
    t_chat_surgical_sentences,
    t_chat_hidden_refuses_without_a_card,
    t_wave3_more_formatting_strike_and_code,
    t_wave3_lines_checklists_and_headings,
    t_wave3_heading_rename_and_new_section,
    t_wave3_properties,
    t_wave3_wikilinks,
    t_wave3_templates,
    t_wave3_chat_sentences_hidden_and_create_workout_note,
    t_twins_and_docs_agree,
]


def main():
    print("=" * 74)
    print("jarvis_notes_edit + jarvis_quick - wave-2 surgical notes edits")
    print("=" * 74)
    for test in TESTS:
        print()
        print("--", test.__name__, "-" * max(0, 60 - len(test.__name__)))
        try:
            test()
        except Exception:                                   # noqa: BLE001
            FAILED.append(test.__name__ + " (exception)")
            import traceback
            traceback.print_exc()
    print()
    print("=" * 74)
    print(f"PASS {len(PASSED)}  FAIL {len(FAILED)}  SKIP {len(SKIPPED)}")
    for name in FAILED:
        print("  FAIL:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
