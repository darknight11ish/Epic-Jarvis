"""The owner's 2026-11-24 sentence: ONE note, one action, plus what a name means.

MEASURED BEFORE THIS SUITE EXISTED, on a throwaway vault, driving the real
`jarvis_quick.answer_turn`:

  "Make a note called mood log and favorite. And every time I refer to mood
   log, I'm referring to this particular note."
  -> notes_batch_refused, "I change one note at a time, so nothing was written"

Two separate faults, and both are pinned below.

1. THE REFERRAL SENTENCE WAS READ AS A BATCH. `_NOTE_WRITE_BATCH`'s `.*`
   reaches across a full stop, so the words "every" and "note" in the SECOND
   sentence made the whole turn read as "write to every note". A sentence about
   what a NAME means is not a request to write to every note: it is taken out
   before the batch test, and the command in front of it is judged on its own.

2. "AND FAVORITE" WAS WRITTEN AS THE NOTE'S BODY. `_FAVOURITE_CLAUSE` requires
   an OBJECT ("favourite it"), so a bare "and favorite" fell through to
   `_note_body_clause` and the vault got `mood log.md` holding the single word
   "favorite" (8 bytes) - a note the owner asked to be favourited, silently
   holding the word instead of the property. The bare word is now a flag, and
   only when it is the WHOLE remaining clause, so body text is not eaten.

Nothing here depends on the owner's vault: every check runs on a temporary one.
"""
import json
import os
import secrets
import sys
import tempfile
import time
import types
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND.parent / "tools"))

from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py")

_TMP = Path(tempfile.gettempdir()) / ("jarvis-note-referral-" + secrets.token_hex(6))
_TMP.mkdir(parents=True, exist_ok=True)
VAULT = _TMP / "vault"
(VAULT / ".obsidian").mkdir(parents=True, exist_ok=True)
CONF = _TMP / "config"
CONF.mkdir(exist_ok=True)
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONF)
os.environ["JARVIS_RECEIPTS_DB"] = str(_TMP / "receipts.db")
os.environ["JARVIS_OBSIDIAN_VAULT"] = str(VAULT)
os.environ.setdefault("HF_HUB_OFFLINE", "1")

FW = types.ModuleType("jarvis_framework")
FW.CONFIG_DIR = CONF
FW.LOG_DIR = _TMP / "log"
FW_STATE = {"notes": {"obsidian": {"vault_directory": str(VAULT)}}}
FW.load_framework = lambda: json.loads(json.dumps(FW_STATE))
FW.action_tier = lambda action: "ask" if action == "edit_vault_note" else "auto"
FW.audit_log = lambda event, detail: None
sys.modules["jarvis_framework"] = FW

GATE = types.ModuleType("jarvis_gate")


class _Approved:
    allowed = True
    outcome = "approved"
    tier = "auto"
    reason = ""


GATE.check = lambda *a, **k: _Approved()
GATE.taint_active = lambda: False
sys.modules["jarvis_gate"] = GATE

import jarvis_quick as Q  # noqa: E402

NOW = time.mktime(time.strptime("2026-11-24 21:30:00", "%Y-%m-%d %H:%M:%S"))

#: The owner's sentence, word for word.
OWNER_SENTENCE = ("Make a note called mood log and favorite. And every time I "
                  "refer to mood log, I'm referring to this particular note.")

CHECKS = []


def check(name, got, want=True):
    ok = got == want
    CHECKS.append(ok)
    print(("ok    " if ok else "FAIL  ") + name + ("" if ok else f"  (got {got!r})"))


def ask(sentence):
    body = {"messages": [{"role": "user", "content": sentence,
                          "provenance": "typed"}]}
    return Q.answer_turn(body, now=NOW)


def reset_vault():
    for child in list(VAULT.iterdir()):
        if child.name == ".obsidian":
            continue
        if child.is_dir():
            for sub in sorted(child.rglob("*"), reverse=True):
                sub.unlink() if sub.is_file() else sub.rmdir()
            child.rmdir()
        else:
            child.unlink()


def vault_notes():
    return [p for p in VAULT.rglob("*.md")]


# 1. THE OWNER'S OWN SENTENCE: one note, created, and favourited.
reset_vault()
res = ask(OWNER_SENTENCE)
check("the owner's sentence is a note CREATE, not a batch refusal",
      res is not None and res.intent == "note_created", True)
check("it never says 'one note at a time'",
      res is not None and "one note at a time" in (res.reply or ""), False)
notes = vault_notes()
check("exactly one note was written", len(notes), 1)
check("the note is called mood log", notes[0].name if notes else "", "mood log.md")
text = notes[0].read_text(encoding="utf-8") if notes else ""
check("the note carries favorite: true", "favorite: true" in text, True)
check("'favorite' was NOT written as the note's body", text.strip().endswith("---"),
      True)
check("the reply says it is favourited", "favourited" in (res.reply or ""), True)

# 2. THE REFERRAL ON ITS OWN: answered, and it promises a lookup only.
reset_vault()
res = ask("Every time I refer to mood log, I'm referring to this particular note.")
check("the referral alone is understood", res is not None
      and res.intent == "note_referral", True)
check("it repeats the name the owner used", "mood log" in (res.reply or ""), True)
check("it never claims to have written an alias line",
      "aliases" in (res.reply or ""), False)
check("the referral alone writes nothing", len(vault_notes()), 0)

# 3. A REAL BATCH STILL REFUSES. The fix must not open the door it guards.
res = ask("add a line about milk to all my notes")
check("a real batch is still refused", res is not None
      and res.intent == "notes_batch_refused", True)

# 4. THE SAME BARE FORM FOR PIN, and its negative.
reset_vault()
res = ask("Make a note called reading list and pin.")
notes = vault_notes()
text = notes[0].read_text(encoding="utf-8") if notes else ""
check("a bare 'and pin' sets pinned: true", "pinned: true" in text, True)
check("a bare pin is not written as the body", text.strip().endswith("---"), True)

# 5. THE BARE FLAG IS ONLY THE WHOLE CLAUSE: body text is not eaten.
#    Asked of the clause reader itself, because the TITLE grammar is greedy
#    ("a note called recipes and my favorite things" makes the whole tail the
#    name), so a sentence-level check here would test the wrong grammar.
body, pinned, favourite, _date = Q._note_create_clauses("favorite", NOW)
check("a bare 'favorite' is a FLAG, with no body", (list(body), favourite),
      ([], True))
body, pinned, favourite, _date = Q._note_create_clauses("my favorite things", NOW)
check("'my favorite things' stays BODY text, not a flag",
      ("favorite things" in " ".join(body), favourite), (True, None))
body, pinned, favourite, _date = Q._note_create_clauses("pin", NOW)
check("a bare 'pin' is a FLAG, with no body", (list(body), pinned), ([], True))

print()
print(f"{sum(CHECKS)} passed, {len(CHECKS) - sum(CHECKS)} failed")
sys.exit(0 if all(CHECKS) else 1)
