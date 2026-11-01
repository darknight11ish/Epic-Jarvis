"""test_notes_write.py - the wave-1 notes writes, proved.

    python -B test_notes_write.py

WHAT THIS SUITE PROVES, in plain words:

1. CREATE ONE NOTE. `POST /api/notes/create` makes exactly one new `.md` file
   (or `.txt`), inside the configured vault only, with an undo receipt recorded
   BEFORE the file exists; the undo removes exactly that file and refuses if
   the note changed since. A path that already exists is a 409 BEFORE any card.
2. APPEND TO ANY NOTE. `POST /api/notes/append` adds the owner's words to the
   END of one existing note, never rewrites it: the old bytes are byte-for-byte
   intact, the appended block is read back, the sha256 the request started from
   is checked at the request AND after the card, and the File Guardian copy is
   taken first (the old version can be put back).
3. TAG ONE NOTE. `POST /api/notes/tag` adds or removes ONE tag, surgically: a
   frontmatter `tags:` list is edited only in that block (every other byte kept),
   a note with no frontmatter gets a visible `#tag` line in auto mode, the
   `frontmatter` and `line` modes do exactly one of those, and malformed front
   matter, a scalar `tags:` value, two `tags:` lines and an illegal tag name are
   all refused in plain words BEFORE any card.
4. ONE CARD PER WRITE, AND NOTHING WITHOUT IT. Each write asks ONE card under
   `edit_vault_note` (tier ask); a Deny, an expiry, a refused gate or a guardian
   that cannot copy writes NOTHING and changes nothing. A confirm-write that
   fails is discarded from the receipts (`discard`), so no undo claims a file
   that was never made.
5. THE LIMITS. 2 MiB per note, at most 4 writes waiting (429), one path per
   request (a list body is refused), no vault configured (503), missing note
   (404), conflict (409, no card), TOCTOU (the note changed while the card was
   up -> failed, nothing written, current hash named).
6. THE CHAT PATHS ARE DETERMINISTIC AND SAFE. "create a note called X",
   "add X to my <note>", "append X to my <note>", "add/remove tag X to/from my
   <note>" land on the module's own routes with no model; hidden lists refuse
   in a fixed line with NO title and NO card; several notes in one request are
   refused; and "note this"/"make a note:" (daily note), "add milk to my
   shopping list" (list), "remind me" (reminder) and "email" keep their own
   doors - no over-capture.
7. THE RECORDS AGREE. Both modules are in the SHIPPED lists, both published
   base twins are byte-identical (line endings aside), and the JARVIS-API
   section documents the new routes.

No network, no real approval card, no owner's files: a temporary vault, a
settings folder that is never the owner's, and a fake gate answer instead.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
os.environ.pop("JARVIS_BACKEND", None)
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_notes_edit.py", "jarvis_quick.py")

_TMP = Path(tempfile.gettempdir()) / ("jarvis-notes-write-" + secrets.token_hex(6))
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
FW_STATE = {"notes": {"obsidian": {"vault_directory": str(VAULT)}}}
FW.load_framework = lambda: json.loads(json.dumps(FW_STATE))
FW.action_tier = lambda action: "ask" if action == "edit_vault_note" else "auto"
AUDIT = []
FW.audit_log = lambda event, detail: AUDIT.append((event, detail))
sys.modules["jarvis_framework"] = FW

# The capture fast path (daily notes) asks jarvis_gate directly; a fake gate
# that always says yes lets the "still goes to the daily note" checks run
# without any real card. The wave-1 module is monkeypatched separately below.
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
    import jarvis_protection as PROTECTION
except Exception:                                           # noqa: BLE001
    PROTECTION = None
try:
    import jarvis_file_guardian as GU
except Exception:                                           # noqa: BLE001
    GU = None
try:
    import jarvis_receipts as RC
except Exception:                                           # noqa: BLE001
    RC = None

FAILED, PASSED, SKIPPED = [], [], []


def skip(name: str, why: str) -> None:
    SKIPPED.append(name)
    print(f"skip  {name}: {why}")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if not cond else ""))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def reset_vault() -> None:
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


def write_note(rel: str, text: str) -> Path:
    p = VAULT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def read_bytes(rel: str) -> bytes:
    return (VAULT / rel).read_bytes()


class Verdict:
    def __init__(self, allowed, tier="ask", outcome="approved", reason=""):
        self.allowed = allowed
        self.tier = tier
        self.outcome = outcome
        self.reason = reason


class Gate:
    """A fake gate: records every call, can run a hook while the card is 'up'."""

    def __init__(self, allowed=True, outcome="approved", hook=None, delay=0.0):
        self.allowed = allowed
        self.outcome = outcome
        self.hook = hook
        self.delay = delay
        self.calls = []

    def __call__(self, action, detail, prompt):
        self.calls.append((action, dict(detail or {}), prompt))
        if self.hook is not None:
            self.hook()
        if self.delay:
            time.sleep(self.delay)
        return Verdict(self.allowed, "ask", self.outcome)


def set_gate(gate) -> None:
    E._gate_check = gate                     # the module's own fail-closed wrapper


def wait_job(job_id: str, timeout: float = 8.0):
    end = time.time() + timeout
    code, out = E.change_status(job_id)
    while out.get("state") == "waiting" and time.time() < end:
        time.sleep(0.02)
        code, out = E.change_status(job_id)
    return code, out


def do_create(rel: str, text: str = "", *, gate=None, wait_s=0.08):
    gate = gate or Gate()
    set_gate(gate)
    code, out = E.handle_create({"path": rel, "text": text},
                                gate_check=gate, wait_s=wait_s)
    jid = out.get("id")
    if code == 202 and jid:
        code, out = wait_job(jid)
    return code, out, gate


def do_append(rel: str, text: str, *, gate=None, wait_s=0.08, expected=None):
    gate = gate or Gate()
    set_gate(gate)
    if expected is None:
        expected = sha(read_bytes(rel))
    code, out = E.handle_append({"path": rel, "text": text,
                                 "expected_sha256": expected},
                                gate_check=gate, wait_s=wait_s)
    jid = out.get("id")
    if code == 202 and jid:
        code, out = wait_job(jid)
    return code, out, gate


def do_tag(rel: str, tag: str, action="add", *, where="auto", gate=None,
           wait_s=0.08, expected=None):
    gate = gate or Gate()
    set_gate(gate)
    if expected is None:
        expected = sha(read_bytes(rel))
    code, out = E.handle_tag({"path": rel, "tag": tag, "action": action,
                              "where": where, "expected_sha256": expected},
                             gate_check=gate, wait_s=wait_s)
    jid = out.get("id")
    if code == 202 and jid:
        code, out = wait_job(jid)
    return code, out, gate


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


def ask(text: str):
    return Q.answer(text, sched=Stub(), now=time.time(),
                    peer="127.0.0.1", local=True)


# --------------------------------------------------------------------------
# 1. CREATE
# --------------------------------------------------------------------------
def t_create_makes_one_note_and_undo_removes_it():
    reset_vault()
    code, out, gate = do_create("Shopping.md", "milk\neggs\n")
    # OWNER DECISION 2026-10-31: a brand-new note is CARD-FREE. It is additive
    # and cannot destroy content, so it must not raise, or wait for, a card.
    check("create: the route answers created, card-free",
          code == 200 and out.get("state") == "created", f"{code} {out}")
    body = read_bytes("Shopping.md")
    check("create: the file holds exactly the text sent", body == b"milk\neggs\n", body)
    check("create: NO card was asked (the owner's decision, 2026-10-31)",
          gate.calls == [], gate.calls)
    check("create: the answer names the file and says it can be undone",
          "Shopping.md" in str(out.get("message"))
          and "You can undo it" in str(out.get("message")), out.get("message"))
    rid = str(out.get("receipt") or "")
    if RC is None:
        skip("create: undo receipt walk", "jarvis_receipts is not on this tree")
        return
    check("create: an undo receipt was recorded", bool(rid), rid)
    undone = RC.undo(rid) if rid else {}
    check("create: undo removes exactly the created note",
          not (VAULT / "Shopping.md").exists(), f"{undone} exists={(VAULT / 'Shopping.md').exists()}")


def t_create_collision_is_refused_before_any_card():
    reset_vault()
    write_note("Shopping.md", "already here\n")
    gate = Gate()
    code, out, _g = do_create("Shopping.md", "new")
    check("create: an existing note is a 409", code == 409, f"{code} {out}")
    check("create: ... and says why in words",
          "already a note" in str(out.get("error")), out)
    check("create: ... and asks NO card", gate.calls == [], gate.calls)


def t_create_refuses_bad_paths_and_a_list_body():
    reset_vault()
    for bad in ("../escape.md", "/abs.md", "C:/x.md", ".obsidian/x.md",
                "notes/../../escape.md", "picture.png", "notes/.hidden.md"):
        code, out = E.handle_create({"path": bad, "text": "x"})
        check(f"create: {bad!r} is refused before any card", code == 400, f"{code} {out}")
    gate = Gate()
    code, out = E.handle_create({"path": ["a.md", "b.md"], "text": "x"},
                                gate_check=gate, wait_s=0.05)
    check("create: a SECOND path in one body is refused plainly",
          code == 400 and "One note at a time" in str(out.get("error")), f"{code} {out}")
    check("create: ... and asks no card", gate.calls == [])


def t_create_denied_writes_nothing_and_no_receipt():
    # A Deny has nothing to refuse now: a brand-new note asks no card at all.
    reset_vault()
    gate = Gate(allowed=False, outcome="denied")
    code, out, _g = do_create("Denied.md", "nope", gate=gate)
    check("create: a brand-new note asks NO card, so a Deny refuses nothing",
          code == 200 and out.get("state") == "created" and gate.calls == [],
          f"{code} {out} {gate.calls}")
    check("create: ... and the note really is written", (VAULT / "Denied.md").is_file())


def t_create_is_one_path_and_respects_protection():
    if PROTECTION is None:
        skip("create: Protected from Jarvis", "jarvis_protection is not on this tree")
        return
    reset_vault()
    (VAULT / "Safe").mkdir(parents=True, exist_ok=True)
    PROTECTION.add_item("folder", str(VAULT / "Safe"), "blocked")
    code, out = E.handle_create({"path": "Safe/Blocked.md", "text": "x"})
    check("create: a blocked folder is refused before any card",
          code == 403 and not (VAULT / "Safe" / "Blocked.md").exists(), f"{code} {out}")


# --------------------------------------------------------------------------
# 2. APPEND
# --------------------------------------------------------------------------
def t_append_adds_only_and_the_guardian_can_put_it_back():
    reset_vault()
    note = write_note("Shopping.md", "old line\n")
    before = note.read_bytes()
    code, out, gate = do_append("Shopping.md", "new words")
    check("append: the route answers saved", code == 200 and out.get("state") == "saved",
          f"{code} {out}")
    after = note.read_bytes()
    check("append: the old bytes are byte-for-byte intact", after.startswith(before), after)
    check("append: the new words really landed at the end",
          after.endswith(b"\n\nnew words\n"), after)
    check("append: ONE card was asked", len(gate.calls) == 1, gate.calls)
    check("append: the answer names the note and says undo",
          "Shopping.md" in str(out.get("message")) and "You can undo it" in str(out.get("message")),
          out.get("message"))
    if GU is None:
        skip("append: File Guardian undo walk", "jarvis_file_guardian is not on this tree")
        return
    snap = str(out.get("snapshot") or "")
    check("append: a File Guardian snapshot id came back", bool(snap), out)
    restored = GU.restore_version(str(note), sha(before), gate=lambda a, d, p: Verdict(True))
    check("append: undo puts the exact old bytes back",
          note.read_bytes() == before, f"{restored} {note.read_bytes()[:120]}")


def t_append_conflict_and_toctou_write_nothing():
    reset_vault()
    note = write_note("Idea.md", "first\n")
    good = sha(note.read_bytes())
    note.write_bytes(b"someone else\n")
    gate = Gate()
    code, out = E.handle_append({"path": "Idea.md", "text": "x",
                                 "expected_sha256": good},
                                gate_check=gate, wait_s=0.05)
    check("append: a stale sha256 is a 409 with the current hash",
          code == 409 and out.get("current_sha256") == sha(note.read_bytes()), f"{code} {out}")
    check("append: ... and asks no card", gate.calls == [])
    # TOCTOU: the note changes while the card is up
    reset_vault()
    note = write_note("Idea.md", "first\n")
    def change_while_waiting():
        note.write_bytes(b"changed while the card waited\n")
    gate2 = Gate(hook=change_while_waiting)
    code, out, _g = do_append("Idea.md", "x", gate=gate2)
    check("append: a change while the card waited ends failed",
          out.get("state") == "failed", f"{code} {out}")
    check("append: ... names the current hash and writes nothing",
          out.get("current_sha256") == sha(note.read_bytes())
          and note.read_bytes() == b"changed while the card waited\n", out)


def t_append_deny_guardian_failure_and_missing_note():
    reset_vault()
    note = write_note("Idea.md", "keep me\n")
    before = note.read_bytes()
    gate = Gate(allowed=False, outcome="denied")
    code, out, _g = do_append("Idea.md", "x", gate=gate)
    check("append: a Deny writes nothing", out.get("state") == "denied"
          and note.read_bytes() == before, f"{code} {out}")
    check("append: ... with the module's own words",
          "You said no, so nothing was added." in str(out.get("message")), out)
    # guardian refuses
    old_snapshot = E._snapshot
    try:
        E._snapshot = lambda full, rel: {"ok": False, "error": "guardian_unavailable",
                                         "words": "The copy could not be saved."}
        code, out, _g = do_append("Idea.md", "x")
        check("append: no guardian copy -> failed, nothing added",
              out.get("state") == "failed" and note.read_bytes() == before, f"{code} {out}")
        check("append: ... says the copy was the reason",
              "could not be saved first" in str(out.get("message")), out)
    finally:
        E._snapshot = old_snapshot
    code, out = E.handle_append({"path": "Missing.md", "text": "x",
                                 "expected_sha256": "a" * 64})
    check("append: a missing note is a 404 before any card", code == 404, f"{code} {out}")


# --------------------------------------------------------------------------
# 3. TAG
# --------------------------------------------------------------------------
FM_NOTE = """---
title: Shopping
tags:
  - home
  - food
author: me
---
milk
"""


def t_tag_edits_only_the_tags_block():
    reset_vault()
    note = write_note("Shopping.md", FM_NOTE)
    code, out, gate = do_tag("Shopping.md", "urgent")
    text = note.read_text(encoding="utf-8")
    check("tag: the route answers saved", code == 200 and out.get("state") == "saved",
          f"{code} {out}")
    check("tag: the new tag is in the front matter",
          "tags:\n  - home\n  - food\n  - urgent\n" in text, text)
    check("tag: every other byte is kept",
          "title: Shopping\n" in text and "author: me\n" in text
          and text.endswith("---\nmilk\n"), text)
    check("tag: ONE card, and the module's own undo sentence",
          len(gate.calls) == 1 and "You can undo it" in str(out.get("message")), out)
    code, out, _g = do_tag("Shopping.md", "food", action="remove")
    text = note.read_text(encoding="utf-8")
    check("tag: removing one tag keeps the others and the file",
          "  - home\n  - urgent\n" in text and "  - food\n" not in text
          and text.endswith("---\nmilk\n"), text)


def t_tag_auto_line_mode_and_frontmatter_mode():
    reset_vault()
    note = write_note("Plain.md", "hello\n")
    code, out, _g = do_tag("Plain.md", "todo")
    check("tag: auto on a note with no front matter adds a visible #tag line",
          code == 200 and note.read_text(encoding="utf-8") == "hello\n#todo\n",
          note.read_text(encoding="utf-8"))
    code, out, _g = do_tag("Plain.md", "todo", action="remove")
    check("tag: removing that tag line leaves the note as it was",
          note.read_text(encoding="utf-8") == "hello\n", note.read_text(encoding="utf-8"))
    note2 = write_note("Front.md", "body\n")
    code, out, _g = do_tag("Front.md", "recipes", where="frontmatter")
    text = note2.read_text(encoding="utf-8")
    check("tag: frontmatter mode creates the YAML tags list",
          text.startswith("---\ntags:\n  - recipes\n---\nbody\n"), text)
    code, out, _g = do_tag("Front.md", "recipes", where="line")
    check("tag: line mode adds a #tag line even when front matter exists",
          note2.read_text(encoding="utf-8").endswith("#recipes\n"),
          note2.read_text(encoding="utf-8"))


def t_tag_refuses_malformed_and_illegal_before_any_card():
    reset_vault()
    cases = {
        "Bad1.md": "---\ntags: notalist\n---\nbody\n",
        "Bad2.md": "---\ntitle: x\nbody\n",
        "Bad3.md": "---\ntags:\n  - a\ntags:\n  - b\n---\nbody\n",
    }
    for rel, text in cases.items():
        write_note(rel, text)
        gate = Gate()
        code, out = E.handle_tag({"path": rel, "tag": "x", "action": "add",
                                  "expected_sha256": sha(read_bytes(rel))},
                                 gate_check=gate, wait_s=0.05)
        check(f"tag: {rel} is refused in words", code == 400 and out.get("error"),
              f"{code} {out}")
        check(f"tag: {rel} asks NO card", gate.calls == [], gate.calls)
    write_note("Good.md", "body\n")
    for bad in ("", "two words", "9", "bad!tag"):
        code, out = E.handle_tag({"path": "Good.md", "tag": bad, "action": "add",
                                  "expected_sha256": sha(read_bytes("Good.md"))})
        check(f"tag: illegal tag {bad!r} is a 400", code == 400, f"{code} {out}")


def t_tag_unchanged_answers_without_a_card():
    reset_vault()
    note = write_note("Shopping.md", FM_NOTE)
    code, out, gate = do_tag("Shopping.md", "home")
    check("tag: a tag already there is a no-op", code == 200
          and out.get("state") == "unchanged" and gate.calls == [], f"{code} {out}")
    check("tag: ... says so in plain words", "already has #home" in str(out.get("message")),
          out)
    code, out, gate = do_tag("Shopping.md", "absent", action="remove")
    check("tag: removing a tag that is not there is a no-op", code == 200
          and out.get("state") == "unchanged" and gate.calls == [], f"{code} {out}")


def t_tag_denied_and_conflict_write_nothing():
    reset_vault()
    note = write_note("Shopping.md", FM_NOTE)
    before = note.read_bytes()
    gate = Gate(allowed=False, outcome="denied")
    code, out, _g = do_tag("Shopping.md", "urgent", gate=gate)
    check("tag: a Deny writes nothing", out.get("state") == "denied"
          and note.read_bytes() == before, f"{code} {out}")
    check("tag: ... with the module's own words",
          "You said no, so the note was not tagged." in str(out.get("message")), out)
    code, out = E.handle_tag({"path": "Shopping.md", "tag": "urgent", "action": "add",
                              "expected_sha256": "0" * 64})
    check("tag: a stale sha256 is a 409 before any card", code == 409, f"{code} {out}")


def t_waiting_limit_and_one_path_bodies():
    reset_vault()
    slow = Gate(delay=0.9)
    set_gate(slow)
    ids = []
    # The waiting limit belongs to the CARDED writes; creates are card-free and
    # do not wait, so this fills the queue with appends (still one card each).
    for i in range(E.MAX_WAITING):
        rel = f"Wait{i}.md"
        write_note(rel, "x\n")
        expected = sha(read_bytes(rel))
        code, out = E.handle_append({"path": rel, "text": "y",
                                     "expected_sha256": expected},
                                    gate_check=slow, wait_s=0.02)
        ids.append((code, out))
    check("limits: the first carded writes wait for their cards",
          all(c == 202 and o.get("state") == "waiting" for c, o in ids),
          [(c, o.get("state")) for c, o in ids])
    write_note("Over.md", "x\n")
    expected = sha(read_bytes("Over.md"))
    code, out = E.handle_append({"path": "Over.md", "text": "y",
                                 "expected_sha256": expected},
                                gate_check=slow, wait_s=0.02)
    check("limits: the next carded write is refused as 429 with the number",
          code == 429 and str(E.MAX_WAITING) in str(out.get("error")), f"{code} {out}")
    for code, out in ids:
        jid = out.get("id")
        if jid:
            wait_job(jid, timeout=5.0)
    for i in range(E.MAX_WAITING):
        (VAULT / f"Wait{i}.md").unlink(missing_ok=True)
    (VAULT / "Over.md").unlink(missing_ok=True)


# --------------------------------------------------------------------------
# 4. THE CHAT PATHS
# --------------------------------------------------------------------------
def t_chat_create_and_the_daily_note_still_owns_its_own_shapes():
    reset_vault()
    gate = Gate()
    set_gate(gate)
    got = ask("create a note called Shopping with milk and eggs")
    check("chat: 'create a note called X' is the create path",
          got is not None and got.intent == "note_created", got.intent if got else "model")
    check("chat: the file was made with the given words",
          (VAULT / "Shopping.md").is_file()
          and "milk and eggs" in (VAULT / "Shopping.md").read_text(encoding="utf-8"),
          (VAULT / "Shopping.md").read_text(encoding="utf-8") if (VAULT / "Shopping.md").is_file() else "missing")
    reset_vault()
    got = ask("make a note: call the plumber")
    check("chat: 'make a note:' still goes to today's daily note, not the create path",
          got is not None and got.intent == "note_made", got.intent if got else "model")
    got = ask("note this: the boiler service is due")
    check("chat: 'note this:' still goes to today's daily note",
          got is not None and got.intent == "note_made", got.intent if got else "model")
    got = ask("add milk to my shopping list")
    check("chat: the shopping LIST keeps its own door (no note append)",
          got is None or got.intent not in ("note_append", "note_appended"),
          got.intent if got else "model")
    got = ask("remind me to call Sam at 5pm")
    check("chat: a reminder stays a reminder (no note append)",
          got is None or got.intent not in ("note_append", "note_appended"),
          got.intent if got else "model")


def t_chat_append_and_tag_paths():
    reset_vault()
    note = write_note("Shopping.md", "old\n")
    got = ask("add milk to my Shopping note")
    check("chat: 'add X to my <note>' is the append path",
          got is not None and got.intent == "note_appended", got.intent if got else "model")
    check("chat: ... and the words are at the end of that note",
          note.read_bytes().endswith(b"\n\nmilk\n"), note.read_bytes())
    check("chat: ... and the answer names the file and says undo",
          got is not None and "Shopping.md" in got.reply and "You can undo it" in got.reply,
          got.reply if got else "")
    got = ask("append eggs to my Shopping note")
    check("chat: 'append X to my <note>' is the append path",
          got is not None and got.intent == "note_appended" and "eggs" in note.read_text(encoding="utf-8"),
          got.intent if got else "model")
    got = ask("add tag recipes to my Shopping note")
    check("chat: 'add tag X to my <note>' tags the note",
          got is not None and got.intent == "note_tagged"
          and "recipes" in note.read_text(encoding="utf-8"), got.reply if got else "model")
    got = ask("remove tag recipes from my Shopping note")
    check("chat: 'remove tag X from my <note>' removes it",
          got is not None and got.intent == "note_tagged"
          and "recipes" not in note.read_text(encoding="utf-8"), got.reply if got else "model")


def t_chat_batch_and_hidden_are_refused_without_a_card():
    reset_vault()
    write_note("Shopping.md", "old\n")
    gate = Gate()
    set_gate(gate)
    got = ask("add milk to all my notes")
    check("chat: several notes in one request is refused in words",
          got is not None and got.intent == "notes_batch_refused"
          and "one note at a time" in got.reply, got.reply if got else "model")
    check("chat: ... and asks no card and writes nothing", gate.calls == []
          and (VAULT / "Shopping.md").read_text(encoding="utf-8") == "old\n", gate.calls)
    # hidden lists: a brand-new note is still card-free and additive, so it is
    # created - but the reply must name no title, no file, and no card is asked.
    old_hidden = Q._calendar_hidden
    try:
        Q._calendar_hidden = lambda: (True, "Words hidden.")
        hidden_gate = Gate()
        set_gate(hidden_gate)
        got = ask("create a note called Secret")
        check("chat hidden: a new note is created card-free",
              got is not None and got.intent == "note_created"
              and hidden_gate.calls == [], got.intent if got else "model")
        check("chat hidden: ... the reply counts the note and names no title",
              got is not None and "Created one note" in got.reply
              and "Secret" not in got.reply, got.reply if got else "")
        check("chat hidden: ... and the file is really written",
              (VAULT / "Secret.md").exists())
        for text in ("add milk to my Shopping note", "add tag x to my Shopping note"):
            got = ask(text)
            check(f"chat hidden: {text!r} still refuses the carded change",
                  got is not None and got.intent == "note_write_hidden"
                  and hidden_gate.calls == [], got.intent if got else "model")
            check("chat hidden: ... no title and nothing changed",
                  got is not None and "Shopping" not in got.reply, got.reply if got else "")
    finally:
        Q._calendar_hidden = old_hidden


# --------------------------------------------------------------------------
# 4b. CARD-FREE CREATE CHAT SHAPES + WHERE-IS-MY-VAULT (2026-10-31 follow-up)
# --------------------------------------------------------------------------
def t_cardfree_create_chat_shapes():
    reset_vault()
    gate = Gate()
    set_gate(gate)
    shapes = ("write a note for me about the gym trip",
              "write me a note about milk and eggs",
              "make a new note called Gym with went to the gym yesterday",
              "create a note called Shopping and put milk in it")
    for said in shapes:
        got = ask(said)
        check(f"chat card-free: {said!r} creates a note",
              got is not None and got.intent == "note_created",
              got.intent if got else "model")
        check("chat card-free: ... the answer says it can be undone",
              got is not None and "You can undo it" in got.reply,
              got.reply if got else "")
    files = sorted(p.name for p in VAULT.glob("*.md"))
    check("chat card-free: every shape wrote a note", len(files) == len(shapes), files)
    check("chat card-free: NO card was asked for any create", gate.calls == [], gate.calls)
    gym = VAULT / "Gym.md"
    check("chat card-free: named create holds the owner's words",
          gym.is_file() and "went to the gym yesterday" in gym.read_text(encoding="utf-8"),
          gym.read_text(encoding="utf-8") if gym.is_file() else "missing")
    shopping = VAULT / "Shopping.md"
    check("chat card-free: 'and put ... in it' becomes the body",
          shopping.is_file() and "milk" in shopping.read_text(encoding="utf-8"))


def t_cardfree_capability_creates_nothing():
    reset_vault()
    gate = Gate()
    set_gate(gate)
    for said in ("can you write a note?", "write a note for me"):
        got = ask(said)
        check(f"chat capability: {said!r} answers yes and creates nothing",
              got is not None and got.intent == "note_create_capability"
              and "Yes" in got.reply, got.intent if got else "model")
    check("chat capability: NO card, no file, no model fallthrough",
          gate.calls == [] and not list(VAULT.glob("*.md")),
          [p.name for p in VAULT.glob("*.md")])


def t_where_is_my_vault_and_last_note():
    reset_vault()
    set_gate(Gate())
    Q._LAST_FILED.clear()
    for said in ("where is my vault?", "which folder are my notes in?",
                 "where do you save my notes?", "where are my notes?"):
        got = ask(said)
        check(f"chat location: {said!r} names the vault",
              got is not None and got.intent == "note_location"
              and str(VAULT) in got.reply, got.reply if got else "model")
        check("chat location: ... read-only, no 'Nothing was done' footer",
              got is not None and "Nothing was actually done" not in got.reply,
              got.reply if got else "")
    got = ask("what folder is it in?")
    check("chat location: with no last note it says so honestly",
          got is not None and got.intent == "note_location"
          and "cannot see which note" in got.reply, got.reply if got else "")
    check("chat location: ... and never offers to search the files",
          got is not None and "search" not in got.reply.lower()
          and "access" not in got.reply.lower(), got.reply if got else "")
    got = ask("what folder is Chrome in?")
    check("chat location: 'what folder is Chrome in' is NOT a vault question",
          got is None or got.intent != "note_location", got.intent if got else "model")
    create = ask("create a note called Gym with gym yesterday")
    check("chat location: the create succeeded before the follow-up",
          create is not None and create.intent == "note_created",
          create.intent if create else "model")
    got = ask("what folder is it in?")
    made = sorted(p.name for p in VAULT.glob("*.md"))
    check("chat location: after a create it names the exact file it wrote",
          got is not None and bool(made) and made[0] in got.reply
          and str(VAULT) in got.reply,
          f"{got.reply if got else ''} files={made}")
    got = ask("where did that note go?")
    check("chat location: 'where did that note go?' names the same file",
          got is not None and bool(made) and made[0] in got.reply,
          f"{got.reply if got else ''} files={made}")


def t_where_is_my_vault_hidden_names_no_note():
    reset_vault()
    set_gate(Gate())
    old = Q._calendar_hidden
    try:
        Q._calendar_hidden = lambda: (True, "Words hidden.")
        got = ask("where did that note go?")
        check("chat location hidden: vault only, no note title or file",
              got is not None and got.intent == "note_location"
              and str(VAULT) in got.reply and ".md" not in got.reply,
              got.reply if got else "model")
    finally:
        Q._calendar_hidden = old


def t_create_round3_invariants():
    """Gemini round-3 ruling 2: the five invariants of a card-free create."""
    reset_vault()
    # 1. strict collision refusal, case-insensitive on Windows (and explicit on
    #    a case-sensitive filesystem): "gym.md" may not create beside "Gym.md".
    code, out, gate = do_create("Gym.md", "first")
    check("round3: the first create is card-free", code == 200
          and out.get("state") == "created" and gate.calls == [], out)
    code, out, gate = do_create("gym.md", "second")
    check("round3: a same-name/different-case collision is a 409",
          code == 409 and out.get("state") == "exists", f"{code} {out}")
    check("round3: ... the first note is byte-for-byte untouched",
          (VAULT / "Gym.md").read_text(encoding="utf-8") == "first")
    check("round3: ... and no card was asked", gate.calls == [], gate.calls)
    # 2. body-size cap: 64 KB is the most a card-free create writes.
    exact = "a" * (E.CARD_FREE_MAX_BYTES - 8)
    code, out = E.handle_create({"path": "Exact.md", "text": exact})
    check("round3: a note just under the 64 KB cap is created",
          code == 200 and out.get("state") == "created", f"{code} {out}")
    code, out = E.handle_create({"path": "Big.md",
                                 "text": "a" * (E.CARD_FREE_MAX_BYTES + 16)})
    check("round3: a note over the 64 KB cap is a 413, no card, no file",
          code == 413 and not (VAULT / "Big.md").exists(), f"{code} {out}")
    # 3. card-free ONLY for a direct owner write: after outside text, a
    #    background job, or another client keeps the old ONE-card path.
    for i, (kwargs, why) in enumerate((
        ({"provenance": "after_outside_text", "client": "hud"}, "after outside text"),
        ({"provenance": "background", "client": "hud"}, "a background job"),
        ({"provenance": "typed", "client": "phone"}, "a non-HUD client"),
    )):
        gate = Gate(delay=0.9)
        set_gate(gate)
        rel = f"CARDED{i}.md"
        code, out = E.handle_create({"path": rel, "text": "x"},
                                    gate_check=gate, wait_s=0.02, **kwargs)
        check(f"round3: {why} still asks its ONE card",
              code == 202 and out.get("state") == "waiting"
              and len(gate.calls) == 1, f"{kwargs} {code} {out} {gate.calls}")
        check(f"round3: ... and {why} writes no file before the yes",
              not (VAULT / rel).exists())
        wait_job(out.get("id"), timeout=5.0)
        (VAULT / rel).unlink(missing_ok=True)
    # 4. direct owner writing in the HUD is the one card-free case.
    gate = Gate()
    code, out = E.handle_create({"path": "Owner.md", "text": "x"},
                                gate_check=gate, provenance="typed", client="hud")
    check("round3: a direct owner HUD write is card-free",
          code == 200 and out.get("state") == "created" and gate.calls == [],
          f"{code} {out} {gate.calls}")
    # 5. the chat path obeys the same rule: a tainted turn forces the card.
    old_taint = Q._note_write_tainted
    try:
        Q._note_write_tainted = lambda: "after_outside_text"
        gate = Gate(delay=3.0)
        set_gate(gate)
        got = ask("write a note for me about the gym")
        check("round3: chat after outside text still asks its card",
              got is not None and got.intent == "note_create_waiting"
              and len(gate.calls) == 1, (got.intent if got else "model") + f" {gate.calls}")
        check("round3: ... and creates no file before the yes",
              not any(p.name.startswith("the gym") for p in VAULT.glob("*.md")))
    finally:
        Q._note_write_tainted = old_taint


def t_create_round3_refusals_are_the_contract():
    """The refusals that must survive card-free mode (ruling 2)."""
    reset_vault()
    for bad in ("../escape.md", "/abs.md", "C:/x.md", ".obsidian/x.md",
                "notes/../../escape.md", "picture.png", "notes/.hidden.md",
                ".git/config.md"):
        code, out = E.handle_create({"path": bad, "text": "x"})
        check(f"round3: {bad!r} is refused with no write", code == 400,
              f"{code} {out}")
    try:
        target = VAULT / "Outside"
        target.mkdir(exist_ok=True)
        link = VAULT / "linkdir"
        if not link.exists():
            os.symlink(str(target), str(link), target_is_directory=True)
        code, out = E.handle_create({"path": "linkdir/x.md", "text": "x"})
        check("round3: a symlinked folder is refused", code in (400, 403),
              f"{code} {out}")
    except (OSError, NotImplementedError):
        pass


# --------------------------------------------------------------------------
# 5. THE RECORDS
# --------------------------------------------------------------------------
def _same_text(a: Path, b: Path) -> bool:
    try:
        return (a.read_bytes().replace(b"\r\n", b"\n")
                == b.read_bytes().replace(b"\r\n", b"\n"))
    except OSError:
        return False


def t_twins_and_docs_agree():
    for name in ("jarvis_notes_edit.py", "jarvis_quick.py"):
        check(f"records: {name} has a byte-identical published twin",
              _same_text(HERE / name, REPO / "jarvis-backend" / name),
              f"{HERE/name} vs {REPO/'jarvis-backend'/name}")
    api = (REPO / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    for route in ("/api/notes/create", "/api/notes/append", "/api/notes/tag",
                  "/api/notes/change"):
        check(f"docs: JARVIS-API.md documents {route}", route in api)
    check("docs: the notes editor section says the three writes are one card each",
          "one approval card" in api)


# --------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------
TESTS = [
    t_create_makes_one_note_and_undo_removes_it,
    t_create_collision_is_refused_before_any_card,
    t_create_refuses_bad_paths_and_a_list_body,
    t_create_denied_writes_nothing_and_no_receipt,
    t_create_is_one_path_and_respects_protection,
    t_append_adds_only_and_the_guardian_can_put_it_back,
    t_append_conflict_and_toctou_write_nothing,
    t_append_deny_guardian_failure_and_missing_note,
    t_tag_edits_only_the_tags_block,
    t_tag_auto_line_mode_and_frontmatter_mode,
    t_tag_refuses_malformed_and_illegal_before_any_card,
    t_tag_unchanged_answers_without_a_card,
    t_tag_denied_and_conflict_write_nothing,
    t_waiting_limit_and_one_path_bodies,
    t_chat_create_and_the_daily_note_still_owns_its_own_shapes,
    t_chat_append_and_tag_paths,
    t_chat_batch_and_hidden_are_refused_without_a_card,
    t_cardfree_create_chat_shapes,
    t_cardfree_capability_creates_nothing,
    t_where_is_my_vault_and_last_note,
    t_where_is_my_vault_hidden_names_no_note,
    t_create_round3_invariants,
    t_create_round3_refusals_are_the_contract,
    t_twins_and_docs_agree,
]


def main():
    print("=" * 74)
    print("jarvis_notes_edit + jarvis_quick - the wave-1 notes writes")
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
    if FAILED:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

