"""test_notion_answer.py - the owner's Notion request gets the real steps, not
"I cannot access Notion".

    python3 backend/test_notion_answer.py

WHY THIS EXISTS. On 2026-10-27 at 20:57:32 the owner asked, in chat:

    "can you process all of my notion notes into obsidian?"

and Jarvis answered:

    "Sir, I cannot directly access or process files from Notion to transfer
     them to Obsidian without explicit file paths or content provided here. If
     you wish to proceed, please share the specific notes or details you would
     like transferred, and I shall assist accordingly."

Every sentence of that is wrong about this PC. `jarvis_documents.import_notion`
unzips a Notion export into a NEW folder in a folder the owner listed (PC only,
no card), and `jarvis_notion_obsidian.py` turns that export into an Obsidian
vault (`/api/notion/import`, PC only, ONE card). The model has no Notion tool
and the owner's feature list has no row for either one, so it answered the only
way it could. The fix is a fixed answer in `jarvis_quick.py`, and this suite is
what holds it to the truth:

  1. the owner's exact sentence, and close phrasings, are answered without the
     model, and a sentence with one more condition ("... tomorrow at 5") is not;
  2. near misses keep their own answer - "open Notion" still opens the app, a
     reminder that mentions Notion is still a reminder;
  3. every step it names is real: the export steps are `NOTION_DETAIL`'s, the
     import heading is `NOTION_TITLE`, the route is `jarvis_notion_obsidian`'s
     own `PATHS`, and the shipped TOML really asks on a card for it;
  4. the folder import really does write a NEW folder (driven end to end on a
     real zip in a temp folder - never the owner's list, never Notion);
  5. it promises nothing it cannot keep: no "I imported", no sync, no login,
     and it says out loud that nothing on Notion's side is changed and that the
     vault converter has no button in either app yet;
  6. it changes nothing itself: no card, no scheduler write, and the "cancel
     that" record is left alone (it is in READ_ONLY_INTENTS).

No network, no model.
"""
from __future__ import annotations

import inspect
import os
import sys
import tempfile
import tomllib
import traceback
import zipfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-notion-answer-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
(_TMP / "config").mkdir(parents=True, exist_ok=True)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py", "jarvis_documents.py", "jarvis_notion_obsidian.py")
if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_quick as Q  # noqa: E402
import jarvis_documents as D  # noqa: E402
import jarvis_notion_obsidian as JNO  # noqa: E402

PASSED, FAILED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


class _Sched:
    """The fast path asks the scheduler two things: note that a command was
    understood, and (for anything not read-only) forget what "cancel that"
    would take back. Both are spies here - nothing is written."""

    def __init__(self):
        self.commands = []
        self.forgotten = []

    def mark_command(self, text):
        self.commands.append(text)

    def note_set(self, *a, **k):
        pass

    def forget_set(self, conversation):
        self.forgotten.append(conversation)


OWNER_SAID = "can you process all of my notion notes into obsidian?"

#: The model's answer in the screenshot, which this fix exists to replace.
#: Only the claim is quoted - the word "cannot" has to appear in ANY honest
#: answer here, so the test looks for the promise of Notion ACCESS, not the word.
BAD_CLAIM = "cannot directly access or process files from Notion"

#: Steps the answer must name, each tied to the real thing below.
WANTED = (
    "I cannot log into Notion",
    "Export all workspace content",
    "Markdown & CSV",
    "NEW folder",
    "nothing in Notion is changed",
    "no app has a button for it yet",
)

#: What it must never say: this answer does not import anything, does not
#: change anything on Notion's side and cannot reach the owner's account.
FORBIDDEN = (
    "I have imported", "I imported", "I'll import", "I will import",
    "Done", "synced", "I can log into your Notion", "I accessed your Notion",
    "I am connected to Notion",
)


def t_the_owners_own_sentence_is_answered_without_the_model():
    i = Q.match(OWNER_SAID)
    check(f"{OWNER_SAID!r} is the fast path's own answer", i is not None and i.name == "notion_export", i)
    sched = _Sched()
    r = Q.answer(OWNER_SAID, sched=sched)
    check("... and it is answered here, not by the model", r is not None, r)
    if r is None:
        return
    check("... with the fixed answer, word for word", r.reply == Q.NOTION_WORDS, r.reply)
    check("... and the route says which answer it was", r.intent == "notion_export", r.intent)
    check("... it is one short answer, not a page", len(r.reply) <= 900, f"{len(r.reply)} characters")
    for want in WANTED:
        check(f"... it says {want!r}", want in r.reply)
    check("... it does not repeat the model's false claim", BAD_CLAIM not in r.reply)
    for bad in FORBIDDEN:
        check(f"... it does not say {bad!r}", bad not in r.reply)
    check("... and it is the same answer in the warm manner",
          Q.in_manner(r.reply, "warm") == r.reply, Q.in_manner(r.reply, "warm"))

    # The same words typed into a chat arrive through answer_turn.
    typed = {"messages": [{"role": "user", "content": OWNER_SAID, "provenance": "typed"}],
             "conversation_id": "c-notion"}
    check("... typed into a chat: answered here too",
          getattr(Q.answer_turn(typed, sched=_Sched()), "intent", None) == "notion_export")
    pasted = {"messages": [{"role": "user", "content": OWNER_SAID, "provenance": "pasted"}],
              "conversation_id": "c-notion"}
    check("... but pasted text is not the owner's own words, and goes to the model",
          Q.answer_turn(pasted, sched=_Sched()) is None)


def t_close_phrasings_and_the_follow_up():
    said = (
        "process all of my notion notes into obsidian",
        "convert my notion notes to obsidian",
        "import my notion export into obsidian",
        "move all my notion notes over to obsidian",
        "transfer all of my notion pages to obsidian",
        "copy everything from notion into obsidian",
        "migrate my notion workspace to obsidian",
        "bring my notion pages into obsidian",
        "export all my notion notes to obsidian",
        "how do I import my notion export into obsidian?",
        "what is the best way to convert my notion notes to obsidian",
        "I want to move all my notion notes into obsidian",
        "can you help me import my notion export into obsidian",
    )
    for s in said:
        i = Q.match(s)
        check(f"{s!r} is answered without the model", i is not None and i.name == "notion_export", i)

    # The follow-up on its own: the .zip is picked with the PC's own picker, so
    # the answer can only say where - and it must not re-run the export steps
    # as if nothing had been done yet.
    for s in ("import my notion export", "bring in my notion export"):
        i = Q.match(s)
        check(f"{s!r} is answered without the model",
              i is not None and i.name == "notion_export" and i.f.get("step") == "import", i)
    r = Q.answer("import my notion export", sched=_Sched())
    check("... with the picker's own steps", r is not None and r.reply == Q.NOTION_PICK_WORDS,
          r and r.reply)
    check("... which name the same real button and folder list",
          D.NOTION_TITLE in r.reply and "Settings, Folders Jarvis may look in" in r.reply, r.reply)


def t_near_misses_keep_their_own_answer():
    # (sentence, the intent it must not become, or None for "not ours")
    misses = (
        ("open notion", "notion_export"),
        ("open obsidian", "notion_export"),
        ("remind me to convert my notion notes to obsidian", "notion_export"),
        ("remind me to import my notion export at 5pm", "notion_export"),
        ("convert my notion notes into a pdf", "notion_export"),
        ("process all my notion notes into obsidian tomorrow", "notion_export"),
        ("convert my notes to obsidian", "notion_export"),
        ("what is notion", "notion_export"),
        ("what can you do", "notion_export"),
    )
    for s, not_this in misses:
        i = Q.match(s)
        check(f"{s!r} is not this answer", i is None or i.name != not_this, i)
    check("'open notion' still opens the app", getattr(Q.match("open notion"), "name", None) == "open_app")
    check("a reminder that mentions Notion is still a reminder",
          getattr(Q.match("remind me to import my notion export at 5pm"), "name", None) == "reminder_set")


def t_every_step_the_answer_names_is_real():
    # 1. The export steps are jarvis_documents' own words for the Notion side.
    check("jarvis_documents.NOTION_TITLE is the import's heading",
          D.NOTION_TITLE == "Bring in a Notion export", D.NOTION_TITLE)
    check("... and the answer names it", D.NOTION_TITLE in Q.NOTION_WORDS)
    for want in ("Export all workspace content", "Markdown & CSV"):
        check(f"NOTION_DETAIL really says {want!r}", want in D.NOTION_DETAIL, D.NOTION_DETAIL)
        check(f"... and so does the answer", want in Q.NOTION_WORDS)

    # 2. The import function exists, takes one local .zip and one listed folder,
    #    and nothing about an account.
    sig = inspect.signature(D.import_notion)
    check("jarvis_documents.import_notion takes the .zip and the folder",
          list(sig.parameters)[:2] == ["zip_path", "into"], str(sig))
    check("... and no Notion account, token or URL",
          not [p for p in sig.parameters if p.lower() in ("token", "url", "account", "email")], str(sig))

    # 3. The vault converter is real, and it is the route the answer names.
    check("jarvis_notion_obsidian really serves the route the answer names",
          JNO.PATHS[1] == "/api/notion/import" and JNO.PATHS[1] in Q.NOTION_WORDS, JNO.PATHS)
    check("... its gate action is its own", JNO.GATE_ACTION == "import_notion_export", JNO.GATE_ACTION)
    check("... and its card title is the one its module documents",
          "Notion export" in JNO.TITLE and "vault" in JNO.TITLE.lower(), JNO.TITLE)

    # 4. "One card" is the shipped tier, not a promise made up here.
    shipped = HERE / "rebuilt" / "jarvis-framework.toml"
    with open(shipped, "rb") as fh:
        tiers = tomllib.load(fh)["autonomy"]["tiers"]
    check("the shipped jarvis-framework.toml asks on a card for that action",
          tiers.get("import_notion_export") == "ask", tiers.get("import_notion_export"))
    check("... and the answer says so (one card)", "one card" in Q.NOTION_WORDS)


def t_the_import_really_writes_a_new_folder():
    """The answer's claim, driven: a real .zip in a temp folder, through the
    same function /api/folders/import calls. Nothing of the owner's is read."""
    root = _TMP / "listed"
    root.mkdir(parents=True, exist_ok=True)
    zp = _TMP / "Export.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("Notes/First page 1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d.md", "# First page\n\nHello.\n")
        zf.writestr("Notes/table.csv", "a,b\n1,2\n")
        zf.writestr("Notes/ignore.exe", "not a document")
    try:
        out = D.import_notion(str(zp), str(root), roots=[str(root)], today="2026-10-28")
    except Exception as exc:  # noqa: BLE001 - the failure IS the finding
        check("the folder import brings a Notion export in", False, f"{type(exc).__name__}: {exc}")
        return
    final = Path(out["folder"])
    check("the folder import brings a Notion export in", out.get("ok") is True, out)
    check("... into a NEW folder beside the listed one, never over it",
          final.parent == root and final.name == "Notion export 2026-10-28", str(final))
    check("... with the notes in it", (final / "Notes" / "First page 1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d.md").is_file())
    check("... and the things it will not read left out", out.get("skipped") == 1, out)
    check("... and it says so in its own words", "Brought in" in str(out.get("said")), out.get("said"))


def t_it_changes_nothing_and_keeps_cancel_that():
    check("the answer is in READ_ONLY_INTENTS", "notion_export" in Q.READ_ONLY_INTENTS)
    sched = _Sched()
    r = Q.answer(OWNER_SAID, sched=sched, conversation="c-notion")
    check("... answering it runs and says nothing to the model", r is not None)
    check("... it does not clear what 'cancel that' would take back", sched.forgotten == [], sched.forgotten)
    check("... and it opens no card (nothing to approve in a fixed answer)",
          r is not None and not r.made and not r.facts and r.open_settings is None)


def main():
    for fn in (t_the_owners_own_sentence_is_answered_without_the_model,
               t_close_phrasings_and_the_follow_up,
               t_near_misses_keep_their_own_answer,
               t_every_step_the_answer_names_is_real,
               t_the_import_really_writes_a_new_folder,
               t_it_changes_nothing_and_keeps_cancel_that):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
