"""test_note_multihop_taint.py - Web-Gap 4: a note saved from outside text.

    python -B backend/run_suites.py test_note_multihop_taint.py

WHY THIS EXISTS (2026-10-23, Gemini's security work order, Web-Gap 4). A note
write is already carded when the turn was shaped by outside text
(`jarvis_agent.NOTE_WRITES`), but after a person approves it the note is
ordinary text: a later `notes_search` returns it, and nothing remembered WHERE
it came from. This suite proves the small PC-side registry built for it:

  * `jarvis_notes` stores only a REFERENCE (vault-relative path / Joplin note
    id) and a time - never a copy of any note - in the settings folder;
  * the registry is normalised, TTL-pruned and capped, and a missing/damaged
    one is safely empty;
  * a completed note write records its own returned reference (and only when
    the turn was outside-shaped);
  * a later search marks each matching result `source_taint: outside_web`
    and wraps its snippet in `<untrusted_web_derived_note>` exactly once,
    leaving every other result untouched;
  * the agent latches the same process-wide taint on that mark, and does not
    when a search is clean;
  * the owner's note store is never edited and no save is refused.

No real vault, Joplin server, model or socket is touched: every backend is
injected, and every registry lives in a temp folder.
"""
from __future__ import annotations

import ast
import json
import os
import sys
import tempfile
import time
import traceback
import types
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# `jarvis_gate.py` is one of the five patched base files, so it lives only in
# the published base (`JARVIS_BACKEND` on a real install, never this folder).
# Appended, not inserted: the shipped modules this suite imports keep coming
# from `backend/`, and this only lets the real gate be imported at all.
sys.path.append(str(HERE.parent / "jarvis-backend"))

# The gate's latch rows live in THIS suite's own temp database. The owner's
# `~/.openjarvis/approvals.db` is never opened, and no card is ever pushed: the
# approval worker a note write starts here is local to this process.
os.environ["JARVIS_APPROVALS_DB"] = str(
    Path(tempfile.mkdtemp(prefix="jarvis-note-taint-db-")) / "approvals.db")
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ["JARVIS_NTFY_SERVER"] = ""
os.environ.setdefault("JARVIS_APPROVAL_TIMEOUT", "2.0")

from _where import require_shipped  # noqa: E402

require_shipped("jarvis_notes.py", "jarvis_agent.py", "jarvis_note_capture.py",
                "jarvis_quick.py", "jarvis_notes_edit.py",
                "jarvis_tellme.py", "jarvis_email.py", "rebuilt/jarvis_router.py")

import jarvis_agent as A  # noqa: E402
import jarvis_notes as NOTES  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class Registry:
    """One temp registry folder, patched in for the duration of a test."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jarvis-note-taint-")
        self.folder = Path(self.tmp.name) / "config"
        self.saved = NOTES._registry_dir
        NOTES._registry_dir = lambda: self.folder

    def close(self):
        NOTES._registry_dir = self.saved
        self.tmp.cleanup()


def t_registry_marks_and_normalises_a_reference():
    reg = Registry()
    try:
        check("a fresh registry has nothing marked",
              NOTES.is_derived_from_outside("daily/note.md") is False)
        check("marking a reference succeeds",
              NOTES.mark_derived_from_outside("Daily\\Note.MD", target="obsidian") is True)
        check("... and it is found through case and slash differences",
              NOTES.is_derived_from_outside("./daily/note.md") is True)
        check("... while a different note is still unmarked",
              NOTES.is_derived_from_outside("daily/other.md") is False)
        check("an empty reference is never marked",
              NOTES.mark_derived_from_outside("") is False)
        check("the registry file holds the normalised reference and a time, "
              "never a copy of the note",
              (lambda text: "daily/note.md" in text and '"at"' in text
               and "cents" not in text)(
                  (reg.folder / NOTES.NOTE_TAINT_FILE).read_text(encoding="utf-8")))
    finally:
        reg.close()


def t_registry_is_pruned_and_bounded():
    reg = Registry()
    try:
        now = 1_800_000_000.0
        NOTES.mark_derived_from_outside("old/note.md", now=now)
        check("a reference inside the TTL is remembered",
              NOTES.is_derived_from_outside("old/note.md",
                                            now=now + NOTES.NOTE_TAINT_TTL_SECONDS - 1))
        check("a reference older than the TTL is dropped",
              NOTES.is_derived_from_outside("old/note.md",
                                            now=now + NOTES.NOTE_TAINT_TTL_SECONDS + 1)
              is False)
        for i in range(NOTES.MAX_TAINTED_NOTES + 5):
            NOTES.mark_derived_from_outside(f"bulk/{i}.md", now=now + 100 + i)
        kept = NOTES._load_taint(now=now + 200)
        check("the registry never grows past its cap",
              len(kept) <= NOTES.MAX_TAINTED_NOTES, len(kept))
        check("... and the oldest reference went first",
              "bulk/0.md" not in kept and f"bulk/{NOTES.MAX_TAINTED_NOTES + 4}.md" in kept,
              sorted(kept)[:2])
    finally:
        reg.close()


def t_registry_survives_a_damaged_file():
    reg = Registry()
    try:
        reg.folder.mkdir(parents=True, exist_ok=True)
        (reg.folder / NOTES.NOTE_TAINT_FILE).write_text("not json at all", encoding="utf-8")
        check("a damaged registry reads as empty instead of raising",
              NOTES._load_taint() == {})
        check("... and a new mark repairs it",
              NOTES.mark_derived_from_outside("fresh/note.md") is True
              and NOTES.is_derived_from_outside("fresh/note.md") is True)
    finally:
        reg.close()


def t_a_completed_note_write_records_its_reference():
    reg = Registry()
    try:
        check("an Obsidian daily write records its file",
              NOTES.mark_from_tool("append_obsidian_daily",
                                   {"ok": True, "target": "obsidian",
                                    "file": "daily/2026-10-23.md"}) is True
              and NOTES.is_derived_from_outside("daily/2026-10-23.md"))
        check("a Logseq journal write records its file",
              NOTES.mark_from_tool("append_logseq_journal",
                                   {"ok": True, "target": "logseq",
                                    "file": "journals/2026_10_23.md"}) is True
              and NOTES.is_derived_from_outside("journals/2026_10_23.md"))
        check("a Joplin create records its note id",
              NOTES.mark_from_tool("create_joplin_note",
                                   {"ok": True, "target": "joplin",
                                    "note_id": "a1b2c3"}) is True
              and NOTES.is_derived_from_outside("a1b2c3"))
        check("a FAILED write records nothing",
              NOTES.mark_from_tool("append_obsidian_daily",
                                   {"ok": False, "target": "obsidian",
                                    "file": "daily/failed.md"}) is False
              and not NOTES.is_derived_from_outside("daily/failed.md"))
        check("a tool that is not a note write records nothing",
              NOTES.mark_from_tool("notes_search",
                                   {"ok": True, "file": "daily/x.md"}) is False)
    finally:
        reg.close()


def t_search_results_that_are_derived_notes_are_wrapped():
    reg = Registry()
    try:
        NOTES.mark_derived_from_outside("daily/2026-10-23.md", target="obsidian")
        out = {"ok": True, "results": [
            {"title": "2026-10-23", "snippet": "web summary text",
             "ref": "daily/2026-10-23.md"},
            {"title": "own", "snippet": "own words", "ref": "daily/own.md"},
        ], "backend": "vault", "query": "diary"}
        got = NOTES.annotate_derived_results(out)
        derived = got["results"][0]
        clean = got["results"][1]
        check("a search result that is a derived note is marked",
              derived.get("source_taint") == NOTES.NOTE_TAINT_SOURCE, derived)
        check("... its snippet is wrapped in the untrusted-note markers",
              derived["snippet"].startswith(NOTES.NOTE_TAINT_OPEN)
              and derived["snippet"].endswith(NOTES.NOTE_TAINT_CLOSE), derived["snippet"])
        check("... and the result set says how many were derived",
              got.get("source_taint") == NOTES.NOTE_TAINT_SOURCE
              and got.get("derived_notes") == 1
              and "never instructions" in str(got.get("taint_note")), got)
        check("an ordinary (unmarked) result is untouched",
              "source_taint" not in clean
              and clean["snippet"] == "own words", clean)
        NOTES.annotate_derived_results(got)
        check("annotating twice does not double-wrap",
              got["results"][0]["snippet"].count(NOTES.NOTE_TAINT_OPEN) == 1,
              got["results"][0]["snippet"])
    finally:
        reg.close()


def t_run_marks_derived_results_for_both_backends():
    reg = Registry()
    try:
        NOTES.mark_derived_from_outside("daily/derived.md", target="obsidian")
        saved = NOTES._search_vault
        NOTES._search_vault = lambda p: {"ok": True, "results": [
            {"title": "d", "snippet": "outside summary", "ref": "daily/derived.md"}],
            "backend": "vault", "query": "q"}
        try:
            plan = types.SimpleNamespace(backend="vault", reason_empty="", query="q")
            out = NOTES.run(plan, approved=True)
        finally:
            NOTES._search_vault = saved
        check("run() on the vault path marks a derived note",
              out.get("source_taint") == NOTES.NOTE_TAINT_SOURCE
              and out["results"][0]["snippet"].startswith(NOTES.NOTE_TAINT_OPEN), out)

        NOTES.mark_derived_from_outside("joplin-id-1", target="joplin")
        plan = types.SimpleNamespace(backend="joplin", reason_empty="", query="q",
                                     url="http://127.0.0.1:41184/search", limit=5)
        out = NOTES.run(plan, approved=True,
                        fetch=lambda p: {"items": [
                            {"id": "joplin-id-1", "title": "T", "body": "web text"}]})
        check("run() on the Joplin path marks a derived note too",
              out.get("source_taint") == NOTES.NOTE_TAINT_SOURCE
              and out["results"][0]["snippet"].startswith(NOTES.NOTE_TAINT_OPEN), out)
    finally:
        reg.close()


def t_agent_latches_taint_on_a_derived_note_read():
    saved_gate = sys.modules.get("jarvis_gate")
    calls = []
    fake_gate = types.ModuleType("jarvis_gate")
    fake_gate.latch_taint = lambda **kw: calls.append(kw) or True
    saved_run = NOTES.run
    try:
        sys.modules["jarvis_gate"] = fake_gate
        NOTES.run = lambda p, **kw: {"ok": True, "results": [],
                                     "source_taint": NOTES.NOTE_TAINT_SOURCE}
        got = A._run_notes_search({}, object())
        check("the agent latches the process-wide taint on a derived-note search",
              calls == [{"why": "tainted_saved_note"}], calls)
        check("... and the result still reaches the tool path", got.get("source_taint"))
        NOTES.run = lambda p, **kw: {"ok": True, "results": []}
        calls.clear()
        A._run_notes_search({}, object())
        check("a clean notes search latches nothing", calls == [], calls)
    finally:
        NOTES.run = saved_run
        if saved_gate is None:
            sys.modules.pop("jarvis_gate", None)
        else:
            sys.modules["jarvis_gate"] = saved_gate


def t_agent_records_only_an_outside_shaped_note_write():
    reg = Registry()
    saved_mark = NOTES.mark_from_tool
    calls = []
    NOTES.mark_from_tool = lambda name, result, **kw: calls.append((name, result)) or True
    try:
        shaped = types.SimpleNamespace(note_needs_a_person=lambda: "after outside text")
        clean = types.SimpleNamespace(note_needs_a_person=lambda: "")
        A._mark_note_provenance("append_obsidian_daily",
                                {"ok": True, "target": "obsidian", "file": "d/x.md"},
                                shaped)
        check("an outside-shaped note write is recorded", len(calls) == 1, calls)
        A._mark_note_provenance("append_obsidian_daily",
                                {"ok": True, "target": "obsidian", "file": "d/y.md"},
                                clean)
        A._mark_note_provenance("append_obsidian_daily",
                                {"ok": False, "target": "obsidian", "file": "d/z.md"},
                                shaped)
        A._mark_note_provenance("notes_search", {"ok": True}, shaped)
        check("a clean turn, a failed write and a non-note tool record nothing",
              len(calls) == 1, calls)
    finally:
        NOTES.mark_from_tool = saved_mark
        reg.close()


def t_the_four_note_writers_are_the_covered_set():
    check("every note writer is in NOTE_WRITES",
          {"append_obsidian_daily", "append_logseq_journal", "create_joplin_note",
           "create_logseq_page"} <= set(A.NOTE_WRITES), sorted(A.NOTE_WRITES))


# --------------------------------------------------------------------------
#   2026-11-16: the owner's own remembered facts are NOT outside text
# --------------------------------------------------------------------------
# Measured defect: a memory-injected turn called
# `jarvis_gate.latch_taint(why="memory_injected")`, and because the latch is ONE
# boolean with a label no consumer reads, every later note write asked for a
# card ("Waiting for your approval card") and a setting change was refused as
# "shaped by something outside of your direct input". The two directions are
# proved here: memory no longer latches, and every real outside-text reader
# still does, with the 30-minute sliding window.

def _hud_tree():
    """The published base HUD, parsed. `tools/check_no_source_pins.py` forbids
    a source-text pin; an AST node is the sanctioned shape for "this call is
    gone" and "this guarded call is still here"."""
    return ast.parse((HERE.parent / "jarvis-backend" / "jarvis_hud.py")
                     .read_text(encoding="utf-8"))


def t_the_hud_never_latches_the_owners_memory_as_outside_text():
    tree = _hud_tree()
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "latch_taint"]
    labels = [k.value.value for c in calls for k in c.keywords
              if k.arg == "why" and isinstance(k.value, ast.Constant)]
    check("the base HUD no longer latches recalled memory as outside text",
          "memory_injected" not in labels, labels)
    check("... and the only latch it still writes is the every-turn refresh",
          labels == ["refresh"], labels)
    refresh = calls[0] if calls else None
    guarded = refresh is not None and any(
        isinstance(n, ast.If) and isinstance(n.test, ast.Call)
        and isinstance(n.test.func, ast.Attribute)
        and n.test.func.attr == "taint_active"
        and any(c is refresh for c in ast.walk(n))
        for n in ast.walk(tree))
    check("... guarded by taint_active(), so it can only EXTEND a real "
          "outside-text latch and never create one", guarded)
    runs = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr == "run_local_turn"]
    wants = [k.value for c in runs for k in c.keywords if k.arg == "request"]
    check("the agent's request is filtered of Jarvis's own system turn",
          len(wants) == 1 and isinstance(wants[0], ast.Call)
          and getattr(wants[0].func, "id", "") == "_request_for_agent"
          and len(wants[0].args) == 2, wants)


def t_a_memory_turn_is_not_shaped_by_outside_text():
    tree = _hud_tree()
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef)
               and n.name == "_request_for_agent"), None)
    check("the base HUD carries the request helper the agent is handed", fn is not None)
    if fn is None:
        return
    ns = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "<hud-helper>", "exec"), ns)
    recalled = {"role": "system",
                "content": "Things you know about the user, recalled for this "
                           "question. ...\n---FACTS---\nMario lives at 42 Elm "
                           "Street\n---END FACTS---"}
    user = {"role": "user",
            "content": "can you escalate to the cloud when the local model "
                       "cannot do it",
            "provenance": "typed"}
    payload = {"model": "m", "messages": [user, recalled], "stream": True,
               "temperature": 0.7, "max_tokens": 2048}
    fixed = ns["_request_for_agent"](payload, recalled)
    check("the server's own recalled-facts turn is taken out of the agent's request",
          recalled not in fixed["messages"] and len(payload["messages"]) == 2,
          fixed.get("messages"))
    check("... and the app's own provenance still arrives",
          fixed["messages"][0].get("provenance") == "typed", fixed.get("messages"))
    before = A._TurnWatch(payload["messages"], request=payload, tainted=False)
    after = A._TurnWatch(payload["messages"], request=fixed, tainted=False)
    check("the control: the raw payload reads as text the APP sent",
          before.app_context is True)
    check("... the filtered request does not", after.app_context is False)
    check("... so a setting change is not refused as outside-shaped",
          A._settings_turn_is_shaped(after) is False)
    check("... while the model still receives the recalled facts",
          any(m.get("role") == "system" and "---FACTS---" in str(m.get("content"))
              for m in A.messages_for_model(payload["messages"], fixed["messages"])))


def _until() -> float:
    import jarvis_gate as G
    with closing(G._connect()) as c:
        row = c.execute("SELECT until FROM taint WHERE key='conversation'").fetchone()
    return float(row["until"]) if row else 0.0


def t_memory_latches_nothing_and_real_outside_text_still_latches():
    import jarvis_gate as G
    import jarvis_quick as Q
    import jarvis_tellme as T
    import jarvis_email as E
    try:
        G.clear_taint()
        check("memory in a conversation hands the note writer the owner's own write",
              Q._note_write_tainted() == "typed", Q._note_write_tainted())
        G.latch_taint(why="page_watch")
        check("a page read still latches", G.taint_active() is True)
        check("... and a note write after it still asks",
              Q._note_write_tainted() == "after_outside_text")
        until = _until()
        left = until - time.time()
        check("... for the same 30-minute window", 29 * 60 <= left <= 31 * 60, left)
        G.latch_taint(why="refresh")
        check("... and the every-turn re-latch pushes it out, never shortens it",
              _until() > until, (until, _until()))
        held = _until()
        G.latch_taint(minutes=1)
        check("... a shorter request can never cut a latch already held",
              _until() == held)
        G.clear_taint()
        check("the page-watch reader still latches",
              T._latch_page_watch() is True and G.taint_active())
        G.clear_taint()
        check("the document/file reader still latches",
              A._latch_sandbox_tool_read() is True and G.taint_active())
        G.clear_taint()
        now = time.time()
        rows = E.find_quiet_threads(
            [{"direction": "out", "at": now - 4 * 86400, "thread": "t1",
              "who": "Alex", "text": "Can you send the file?"}],
            now=now, latch=True)
        check("the email-body read still latches",
              bool(rows) and G.taint_active(), rows)
    finally:
        G.clear_taint()


def t_a_pasted_file_is_still_kept_on_this_pc():
    """The pasted file's own boundary, unchanged by the memory fix.

    A file ridden in on a question has never set the 30-minute process-wide
    latch: `jarvis_attached_file.py:36-41` records the 2026-10-30 decision that
    it marks the CONVERSATION private and the router's own `file` gate refuses
    the cloud lane - "so one attachment cannot keep every other chat off the
    cloud lane". That is what must still hold."""
    import jarvis_router as RT
    d = RT.choose("How do I compare two large documents?", local_model="local-model",
                  lanes=[RT.CLOUD_LANE], has_file=True)
    check("a pasted-file turn is still refused a cloud lane by its own gate",
          d.lane == "local-model" and d.gate == "file", (d.lane, d.gate))


def t_the_note_card_follows_outside_text_not_memory():
    import jarvis_gate as G
    import jarvis_quick as Q
    import jarvis_notes_edit as E
    vault = Path(tempfile.mkdtemp(prefix="jarvis-note-card-")) / "vault"
    vault.mkdir(parents=True)
    (vault / ".obsidian").mkdir()
    saved = os.environ.get("JARVIS_OBSIDIAN_VAULT")
    os.environ["JARVIS_OBSIDIAN_VAULT"] = str(vault)
    try:
        G.clear_taint()
        code, body = E.handle_create(
            {"path": "Field Test Groceries.md", "text": "milk"},
            provenance=Q._note_write_tainted(), client="hud", wait_s=0.2)
        check("a direct owner note write is card-free",
              code == 200 and body.get("state") == "created", (code, body))
        G.latch_taint(why="page_watch")
        code2, body2 = E.handle_create(
            {"path": "Field Test Groceries 2.md", "text": "eggs"},
            provenance=Q._note_write_tainted(), client="hud", wait_s=0.5)
        check("... a write after outside text still raises the one card",
              code2 == 202 and body2.get("state") == "waiting", (code2, body2))
    finally:
        G.clear_taint()
        if saved is None:
            os.environ.pop("JARVIS_OBSIDIAN_VAULT", None)
        else:
            os.environ["JARVIS_OBSIDIAN_VAULT"] = saved


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("t_") and callable(fn):
            try:
                fn()
            except Exception:
                FAILED.append(name)
                print(f"FAIL {name} raised")
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
