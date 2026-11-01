"""Hermetic checks for rename/move with link preservation (wave 4, 2026-10-31).

Run: python -B backend/test_notes_rename_move.py
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.pop("JARVIS_BACKEND", None)
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_notes_edit.py", "jarvis_quick.py")

_TMP = Path(tempfile.gettempdir()) / ("jarvis-notes-rename-move-" + secrets.token_hex(6))
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
_GATE_MODULE.taint_active = lambda: False
_GATE_MODULE.check = lambda *a, **k: None
sys.modules["jarvis_gate"] = _GATE_MODULE

import jarvis_notes_edit as E  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_receipts as R  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []
GATE_CALLS = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    SKIPPED.append(name)
    print(f"skip  {name}: {why}")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tree(root: Path):
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out.append((p.relative_to(root).as_posix(), sha(p.read_bytes())))
    return out


def reset():
    for child in list(VAULT.iterdir()):
        if child.name == ".obsidian":
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
    E._reset_for_tests()
    GATE_CALLS.clear()


def write(rel: str, text: str):
    p = VAULT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
    return p


def read(rel: str) -> bytes:
    return (VAULT / rel).read_bytes()


class Verdict:
    def __init__(self, allowed=True, tier="ask", outcome="approved"):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome
        self.reason = ""


class Gate:
    def __init__(self, allowed=True, outcome="approved", tier="ask", on_call=None):
        self.allowed, self.outcome, self.tier = allowed, outcome, tier
        self.on_call = on_call
        self.calls = []

    def __call__(self, action, detail, prompt):
        self.calls.append((action, detail, prompt))
        GATE_CALLS.append((action, detail, prompt))
        if self.on_call:
            self.on_call()
        return Verdict(self.allowed, self.tier, self.outcome)


def call(fn, body, gate=None, wait_s=10.0):
    return fn(body, gate_check=gate or Gate(), wait_s=wait_s, by="test")


# ---------------------------------------------------------------------------
def t_rename_updates_wikilinks_embeds_aliases_sections_and_markdown_links():
    reset()
    write("A.md", "# A\n\nI am A.\n")
    write("B.md", ("See [[A]], [[A|alias]], [[A#Section]] and ![[A]] here.\n"
                   "A markdown link [x](A.md) too.\n"
                   "```\n[[A]] in a fence stays\n```\n"
                   "And `[[A]]` in code stays.\n"))
    write("C.md", "# C\n\nNo link to A.\n")
    before = tree(VAULT)
    gate = Gate(on_call=None)
    code, out = call(E.handle_rename, {"path": "A.md", "title": "Renamed"}, gate)
    check("rename returns a finished result", code == 200 and out.get("state") == "saved",
          (code, out))
    check("the note moved, same bytes, old path gone",
          not (VAULT / "A.md").exists()
          and (VAULT / "Renamed.md").read_bytes() == "# A\n\nI am A.\n".encode())
    body = read("B.md").decode()
    check("wiki link, alias, section and embed all point at the new name",
          "[[Renamed]]" in body and "[[Renamed|alias]]" in body
          and "[[Renamed#Section]]" in body and "![[Renamed]]" in body, body)
    check("the markdown link points at the new path", "[x](Renamed.md)" in body, body)
    check("fenced and inline code are byte-unchanged",
          "[[A]] in a fence stays" in body and "`[[A]]` in code stays" in body, body)
    check("an unrelated note is byte-identical",
          read("C.md") == b"# C\n\nNo link to A.\n")
    check("only the link targets changed in B (the rest is byte-identical)",
          read("B.md").decode() ==
          ("See [[Renamed]], [[Renamed|alias]], [[Renamed#Section]] and ![[Renamed]] here.\n"
           "A markdown link [x](Renamed.md) too.\n"
           "```\n[[A]] in a fence stays\n```\n"
           "And `[[A]]` in code stays.\n"), read("B.md").decode())
    check("the card showed the link counts and the new path",
          gate.calls and gate.calls[0][1].get("updates") == 5
          and gate.calls[0][1].get("target") == "Renamed.md",
          gate.calls[0][1] if gate.calls else None)
    check("the card names the source, the target, its counts and the affected note",
          gate.calls and "A.md to Renamed.md" in gate.calls[0][2]
          and "5 link(s) in 1 note(s)" in gate.calls[0][2]
          and "(B.md)" in gate.calls[0][2]
          and gate.calls[0][1].get("changed_notes") == ["B.md"],
          gate.calls[0][2] if gate.calls else None)
    check("one approval card only", len(gate.calls) == 1, gate.calls)
    rid = out.get("receipt")
    undo = R.undo(rid) if rid else {}
    check("one batch undo puts every byte and path back",
          tree(VAULT) == before, (undo, tree(VAULT)))
    check("... and the card said it was undoable",
          "You can undo it" in str(out.get("message")), out.get("message"))


def t_rename_with_no_links_is_just_the_file_move():
    reset()
    write("Quiet.md", "# Quiet\n\nNo links at all.\n")
    before = tree(VAULT)
    code, out = call(E.handle_rename, {"path": "Quiet.md", "title": "Silent"})
    check("a no-link rename succeeds", code == 200 and out.get("state") == "saved", out)
    check("... with zero link updates", out.get("updates") == 0 and out.get("notes") == 0, out)
    check("... and only the path changed",
          (VAULT / "Silent.md").read_bytes() == b"# Quiet\n\nNo links at all.\n", tree(VAULT))
    R.undo(out.get("receipt"))
    check("... and undo restores the path and bytes", tree(VAULT) == before)


def t_move_updates_path_links_and_leaves_bare_title_links_alone():
    reset()
    write("Work/A.md", "# A\n\nMoved note.\n")
    (VAULT / "Archive").mkdir(exist_ok=True)
    write("B.md", "Path [[Work/A]] and bare [[A]], plus [x](Work/A.md).\n")
    before = tree(VAULT)
    code, out = call(E.handle_move, {"path": "Work/A.md", "folder": "Archive"})
    check("move succeeds", code == 200 and out.get("state") == "saved", out)
    check("the file is in the target folder",
          not (VAULT / "Work/A.md").exists()
          and (VAULT / "Archive/A.md").read_bytes() == b"# A\n\nMoved note.\n")
    body = read("B.md").decode()
    check("path-style wikilink and markdown link updated",
          "[[Archive/A]]" in body and "[x](Archive/A.md)" in body, body)
    check("bare title wikilink is unchanged (the title did not change)",
          "[[A]]" in body, body)
    R.undo(out.get("receipt"))
    check("move undo restores every byte and path", tree(VAULT) == before)


def t_collisions_and_bad_paths_are_refused_before_any_card():
    reset()
    write("One.md", "# One\n")
    write("Taken.md", "# Taken\n")
    gate = Gate()
    code, out = call(E.handle_rename, {"path": "One.md", "title": "Taken"}, gate)
    check("renaming onto an existing name is refused", code in (409, 400)
          and out.get("state") == "refused" and gate.calls == [], (code, out, gate.calls))
    code, out = call(E.handle_rename, {"path": "One.md", "title": "../Escape"}, gate)
    check("a title with a slash/traversal is refused before the card",
          code == 400 and gate.calls == [], (code, out))
    code, out = call(E.handle_move, {"path": "One.md", "folder": "Missing"}, gate)
    check("moving into a missing folder is refused unless create is explicit",
          code == 400 and "create the folder" in str(out.get("error")), (code, out))
    code, out = call(E.handle_move, {"path": "One.md", "folder": "../outside"}, gate)
    check("moving outside the vault is refused", code == 400 and gate.calls == [], (code, out))
    check("... and every refusal changed no byte", tree(VAULT) == [(p.relative_to(VAULT).as_posix(), sha(p.read_bytes())) for p in sorted(VAULT.rglob("*")) if p.is_file()])


def t_card_discloses_only_the_first_three_affected_names():
    reset()
    write("A.md", "# A\n")
    for i in range(1, 6):
        write(f"N{i}.md", f"[[A]]\n")
    gate = Gate()
    code, out = call(E.handle_rename, {"path": "A.md", "title": "Many"}, gate)
    prompt = gate.calls[0][2] if gate.calls else ""
    check("the card shows three filenames and says how many more",
          code == 200 and "(N1.md, N2.md, N3.md (+2 more))" in prompt
          and gate.calls[0][1].get("changed_notes") == ["N1.md", "N2.md", "N3.md"]
          and gate.calls[0][1].get("changed_notes_more") == 2, (code, prompt))
    R.undo(out.get("receipt"))


def t_hidden_lists_card_has_no_filenames():
    reset()
    write("A.md", "# A\n")
    for name in ("B.md", "C.md"):
        write(name, "[[A]]\n")
    saved = E._hidden_lists
    E._hidden_lists = lambda: True
    gate = Gate()
    try:
        code, out = call(E.handle_rename, {"path": "A.md", "title": "Hidden"}, gate)
    finally:
        E._hidden_lists = saved
    prompt = gate.calls[0][2] if gate.calls else ""
    check("hidden lists keep counts only and name no note",
          code == 200 and "2 link(s) in 2 note(s)" in prompt
          and "B.md" not in prompt and "C.md" not in prompt and "A.md" not in prompt,
          (code, prompt))
    R.undo(out.get("receipt"))


def t_move_can_create_a_folder_only_when_explicit():
    reset()
    write("A.md", "# A\n")
    code, out = call(E.handle_move, {"path": "A.md", "folder": "New Folder",
                                     "create_folder": True})
    check("an explicit create makes the folder and moves the note",
          code == 200 and (VAULT / "New Folder/A.md").is_file(), (code, out))
    check("the card said it would create the folder", True)
    R.undo(out.get("receipt"))
    check("undo removes the created folder and puts the note back",
          not (VAULT / "New Folder").exists() and (VAULT / "A.md").is_file(),
          tree(VAULT))


def t_deny_expiry_guardian_failure_and_toctou_write_nothing():
    reset()
    write("A.md", "# A\n")
    write("B.md", "[[A]]\n")
    before = tree(VAULT)
    for label, gate in (
            ("deny", Gate(allowed=False, outcome="denied")),
            ("expiry", Gate(allowed=False, outcome="timed_out"))):
        reset_state = None
        code, out = call(E.handle_rename, {"path": "A.md", "title": "Never"}, gate)
        check(f"{label} writes nothing", code in (200, 403)
              and out.get("state") in ("denied", "failed")
              and tree(VAULT) == before, (label, code, out, tree(VAULT)))
    saved = E._snapshot
    E._snapshot = lambda full, rel: {"ok": False, "words": "the guardian refused"}
    try:
        code, out = call(E.handle_rename, {"path": "A.md", "title": "Never"})
    finally:
        E._snapshot = saved
    check("a guardian failure writes nothing", code in (200, 500)
          and out.get("state") == "failed" and tree(VAULT) == before, (code, out))
    def mutate():
        (VAULT / "A.md").write_text("# A changed while the card waited\n", encoding="utf-8")
    before_toctou = tree(VAULT)
    gate = Gate(on_call=mutate)
    code, out = call(E.handle_rename, {"path": "A.md", "title": "Changed"}, gate)
    check("a note changed while the card waited writes nothing",
          out.get("state") == "failed" and not (VAULT / "Changed.md").exists()
          and read("A.md").startswith(b"# A changed"), (code, out))


def t_every_changed_file_was_snapshotted_first():
    reset()
    write("A.md", "# A\n")
    write("B.md", "[[A]]\n")
    seen = []
    saved = E._snapshot
    E._snapshot = lambda full, rel: (seen.append(rel), saved(full, rel))[1]
    try:
        code, out = call(E.handle_rename, {"path": "A.md", "title": "Snapped"})
    finally:
        E._snapshot = saved
    check("the source and every linked note were snapshotted before the write",
          code == 200 and set(seen) == {"A.md", "B.md"}, seen)
    R.undo(out.get("receipt"))


def t_hidden_lists_card_names_no_note():
    reset()
    write("A.md", "# A\n")
    write("B.md", "[[A]]\n")
    saved = E._hidden_lists
    E._hidden_lists = lambda: True
    gate = Gate()
    try:
        code, out = call(E.handle_rename, {"path": "A.md", "title": "HiddenName"}, gate)
    finally:
        E._hidden_lists = saved
    check("a hidden-lists card is counts-only and names neither file",
          code == 200 and gate.calls
          and "A.md" not in gate.calls[0][2] and "HiddenName" not in gate.calls[0][2]
          and gate.calls[0][1].get("hidden_lists") is True, gate.calls)
    R.undo(out.get("receipt"))


def t_chat_shapes_preview_and_refuse():
    reset()
    write("Welcome.md", "# Welcome\n\nHello.\n")
    write("Other.md", "[[Welcome]]\n")
    # Rename chat shape.
    got = Q.match("rename my Welcome note to Home")
    check("the rename chat shape is note_rename", got is not None and got.name == "note_rename",
          got.name if got else "the model")
    # The fast path calls the real route with a fake gate; exercise the matcher
    # and the module call through quick with a temporary receipt store.
    saved_gate = sys.modules["jarvis_gate"].check
    sys.modules["jarvis_gate"].check = lambda action, detail, prompt: Verdict(True, "ask", "approved")
    try:
        out = Q.answer("rename my Welcome note to Home", now=0, peer="127.0.0.1", local=True)
    finally:
        sys.modules["jarvis_gate"].check = saved_gate
    check("the chat rename previews the counts and says it can undo",
          out is not None and out.intent == "note_renamed"
          and "This renames Welcome.md to Home.md" in out.reply
          and "1 link(s) in 1 note(s)" in out.reply
          and "You can undo it" in out.reply,
          (out.intent if out else "the model", out.reply if out else ""))
    got = Q.match("move my Home note to Archive and fix the links")
    check("the move chat shape is note_move", got is not None and got.name == "note_move",
          got.name if got else "the model")
    got = Q.match("delete my note Welcome")
    check("delete is still refused", got is not None and got.name in ("note_change_refused", "note_delete_refused"),
          got.name if got else "the model")
    # Two notes with the same title: the chat refuses with the count, no card.
    write("Dup.md", "# Dup one\n")
    write("Elsewhere/Dup.md", "# Dup two\n")
    g2 = Gate()
    got = Q.match("rename my Dup note to Single")
    check("a duplicate title is still matched for rename", got is not None and got.name == "note_rename",
          got.name if got else "the model")
    # Exercise the refusal through the real runner with its normal gate path.
    out2 = Q.answer("rename my Dup note to Single", now=0, peer="127.0.0.1", local=True)
    check("an ambiguous title is refused with the count and no card",
          out2 is not None and "matches 2 notes" in out2.reply,
          (out2.intent if out2 else "the model", out2.reply if out2 else ""))
    check("a scheduler-shaped move with no note word is not over-captured",
          Q.match("move my reminder to 5pm") is None
          or Q.match("move my reminder to 5pm").name != "note_move")
    heading = Q.match("rename the old heading to Warm-up in my workout log")
    check("the heading-rename sentence stays the customization lane",
          heading is not None and heading.name == "note_customize",
          heading.name if heading else "the model")
    line_move = Q.match("move a line into the Notes section of my workout log")
    check("the line-move sentence is not over-captured as a note move",
          line_move is None or line_move.name != "note_move",
          line_move.name if line_move else "the model")
    hidden_saved = Q._notes_write_hidden
    Q._notes_write_hidden = lambda: True
    try:
        hidden = Q.answer("rename my Welcome note to Home", now=0, peer="127.0.0.1", local=True)
    finally:
        Q._notes_write_hidden = hidden_saved
    check("a hidden-lists chat rename refuses with no title and no card",
          hidden is not None and hidden.intent == "note_write_hidden"
          and "Welcome" not in hidden.reply, hidden.reply if hidden else "the model")
    reset()


def t_hidden_protected_symlink_and_dotdot_are_refused():
    reset()
    write("Visible.md", "# Visible\n")
    write(".Hidden.md", "# Hidden\n")
    gate = Gate()
    code, out = call(E.handle_rename, {"path": ".Hidden.md", "title": "Shown"}, gate)
    check("a hidden source note is refused before the card",
          code in (400, 403) and gate.calls == [], (code, out))
    code, out = call(E.handle_move, {"path": "Visible.md", "folder": ".hidden-folder"}, gate)
    check("a hidden destination folder is refused before the card",
          code in (400, 403) and gate.calls == [], (code, out))
    code, out = call(E.handle_rename, {"path": "../Outside.md", "title": "Safe"}, gate)
    check("a traversal source is refused before the card",
          code == 400 and gate.calls == [], (code, out))
    try:
        (VAULT / "Link.md").symlink_to(VAULT / "Visible.md")
    except (OSError, NotImplementedError):
        # This Windows account cannot make a symlink. Prove the same refusal
        # with the link check's own answer, without touching the vault rules.
        saved_link = E._is_link_or_reparse
        E._is_link_or_reparse = lambda p: Path(p).name == "Link.md" or saved_link(p)
        try:
            write("Link.md", "# link-like\n")
            code, out = call(E.handle_rename, {"path": "Link.md", "title": "Linked"}, gate)
        finally:
            E._is_link_or_reparse = saved_link
        check("a link-like source is refused before the card",
              code in (400, 403) and gate.calls == [], (code, out))
    else:
        code, out = call(E.handle_rename, {"path": "Link.md", "title": "Linked"}, gate)
        check("a symlink source is refused before the card",
              code == 400 and gate.calls == [], (code, out))
        (VAULT / "Link.md").unlink(missing_ok=True)
    class Protect:
        def path_refusal(self, path, write=False):
            return "that note is protected from Jarvis" if "Protected" in str(path) else ""
    saved = E._protection
    E._protection = lambda: Protect()
    try:
        write("Protected.md", "# Protected\n")
        code, out = call(E.handle_rename, {"path": "Protected.md", "title": "Allowed"}, gate)
    finally:
        E._protection = saved
    check("a protected source is refused before the card",
          code == 403 and gate.calls == [], (code, out))


def t_chat_move_can_create_and_preview():
    reset()
    write("Welcome.md", "# Welcome\n")
    write("Other.md", "[[Welcome]]\n")
    saved_gate = sys.modules["jarvis_gate"].check
    sys.modules["jarvis_gate"].check = lambda action, detail, prompt: Verdict(True, "ask", "approved")
    try:
        out = Q.answer("move my Welcome note into Archive and create the folder",
                       now=0, peer="127.0.0.1", local=True)
    finally:
        sys.modules["jarvis_gate"].check = saved_gate
    check("the move chat creates the folder only when asked and previews it",
          out is not None and out.intent == "note_moved"
          and "This moves Welcome.md to Archive/Welcome.md and creates the folder" in out.reply
          and (VAULT / "Archive/Welcome.md").is_file(), (out.intent if out else None,
                                                          out.reply if out else ""))
    reset()


def t_docs_pin_the_routes_and_the_rules():
    api = (HERE.parent / "docs" / "JARVIS-API.md").read_text(encoding="utf-8")
    check("docs: JARVIS-API.md documents the rename and move routes",
          "/api/notes/rename" in api and "/api/notes/move" in api)
    check("docs: the fenced/inline-code and batch-undo rules are written",
          "fenced code blocks and inline code are never touched" in api
          or "fenced code blocks and inline code are never\n  touched" in api, "missing rule")
    check("docs: the chat sentences and not-built list are written",
          "rename my Welcome note to Home" in api and "Not built, said plainly" in api)


def t_routes_are_installed_on_the_notes_module():
    check("both routes are in the module's POST path table",
          E.RENAME_PATH in E.POST_PATHS and E.MOVE_PATH in E.POST_PATHS,
          (E.RENAME_PATH, E.MOVE_PATH, E.POST_PATHS))
    src = (HERE / "jarvis_notes_edit.py").read_text(encoding="utf-8")
    check("the loader dispatches both routes",
          "route == RENAME_PATH" in src and "route == MOVE_PATH" in src
          and "handle_rename(body)" in src and "handle_move(body)" in src)


def main():
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("t_") and callable(v)]
    for fn in funcs:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            import traceback
            FAILED.append(fn.__name__)
            print("FAIL  raised")
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    shutil.rmtree(_TMP, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
