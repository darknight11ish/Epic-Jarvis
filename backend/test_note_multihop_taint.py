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

import json
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_notes.py", "jarvis_agent.py", "jarvis_note_capture.py")

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
