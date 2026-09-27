"""test_sources.py - "Where this came from", and the quote check.

    python3 backend/test_sources.py

Feasibility items I42 and I132 (`docs/FEASIBILITY-AUDIT-2026-09-26.md`
section 2), the exact spec being detail 1 of
`docs/CUTTING-EDGE-2026-09-26-round3-knowledge.md`. `jarvis_sources.py`,
`answer-sources.patch`, `docs/JARVIS-API.md` section 55.

What it proves:

  - `from_tool_result` reads each of the four reading tools' own REAL result
    shapes (notes_search's vault results, web_search's normalised results,
    my_files' find/search/read shapes, file_read) into references only -
    never the note's or file's full text, never a web page's body - and
    drops anything of an unknown kind or with no reference at all;
  - `record`/`sources_of`/`handle_get` behave like `jarvis_memory`'s
    `used_view`/`handle_used_get`: a bad turn_id is a 400 in words, an
    unknown or empty turn_id is 200 with empty lists (never a 404), and
    what is recorded is exactly what is read back;
  - `install()` wraps `do_GET` the same way `jarvis_news.install` does -
    this route only, everything else passed through;
  - `unverified_quotes` finds a quoted phrase that is not in what was read
    this turn (spacing and case ignored), leaves a phrase that IS there
    alone, ignores short quotes and quotes when nothing was read at all -
    and is a pure word check: no model, never changes the text it is given;
  - `jarvis_agent._TurnWatch.took_in` collects sources from a REAL tool
    result (via `_run_notes_search`) into `.sources`, deduplicated and
    capped, alongside its existing outside-text bookkeeping - and a real
    `run_local_turn` call, with a notes_search tool call against a real
    temporary vault, carries the note's ref (never its snippet) in its
    `tool_sources`, and flags a quote the model invented that is not in
    that note's own text, in `unverified_quotes`.
"""
from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_agent.py", "jarvis_sources.py", "jarvis_notes.py")
import jarvis_agent as AG  # noqa: E402
import jarvis_sources as SRC  # noqa: E402
import _ollama_wire as W  # noqa: E402

AG._manner_now = lambda *a, **k: None
AG._record_chain = lambda steps: None
AG._publish_step = lambda step: None

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


TID = "0123456789abcdef0123456789abcdef"
TID2 = "fedcba9876543210fedcba9876543210"


# --------------------------------------------------------------------------
#   from_tool_result: each reading tool's own real shape
# --------------------------------------------------------------------------

def t_notes_search_becomes_a_note_or_wiki_reference():
    # jarvis_notes._search_vault's real shape (a note).
    result = {"ok": True, "results": [
        {"title": "Soup ideas", "snippet": "Add nutmeg, always.", "ref": "Recipes/Soup.md"},
        {"title": "Recipes", "snippet": "A wiki page's own snippet.", "ref": "Jarvis Wiki/Recipes.md"},
    ], "backend": "vault", "query": "soup"}
    out = SRC.from_tool_result("notes_search", result)
    check("two sources, one per result", len(out) == 2, out)
    check("a plain vault note is kind 'note'", out[0] == {"kind": "note", "ref": "Recipes/Soup.md",
                                                            "title": "Soup ideas"})
    check("a page under Jarvis Wiki/ is kind 'wiki', not 'note'",
          out[1]["kind"] == "wiki" and out[1]["ref"] == "Jarvis Wiki/Recipes.md", out[1])
    check("never the snippet - only the reference and the title",
          all("snippet" not in s and "Add nutmeg" not in json.dumps(s) for s in out), out)
    check("a failed search gives nothing", SRC.from_tool_result("notes_search", {"ok": False}) == [])
    check("a result with no ref is dropped", SRC.from_tool_result(
        "notes_search", {"ok": True, "results": [{"title": "x"}]}) == [])


def t_web_search_becomes_a_web_reference():
    # jarvis_search.normalise's real shape.
    result = {"ok": True, "provider": "searxng", "provider_label": "SearXNG", "query": "soup",
              "results": [{"title": "Example Soup Co", "url": "https://example.com/soup",
                           "snippet": "The best soup in town, they say."}]}
    out = SRC.from_tool_result("web_search", result)
    check("one web source", out == [{"kind": "web", "url": "https://example.com/soup",
                                     "title": "Example Soup Co"}], out)
    check("never the snippet", all("best soup" not in json.dumps(s) for s in out))
    check("WS.tool_result's failure shape gives nothing",
          SRC.from_tool_result("web_search", {"ok": False, "error": "x"}) == [])


def t_my_files_becomes_a_file_reference_for_find_search_and_read():
    # jarvis_documents.search()'s real shape.
    search_result = {"ok": True, "results": [
        {"name": "Notes", "path": "/home/owner/Documents/notes.md", "snippet": "private text here"}],
        "matches": 1, "files_searched": 3}
    out = SRC.from_tool_result("my_files", search_result)
    check("search(): one file reference, never the snippet", out == [
        {"kind": "file", "path": "/home/owner/Documents/notes.md", "title": "Notes"}], out)
    # jarvis_documents.find()'s real shape - a DIFFERENT key ("found").
    find_result = {"ok": True, "found": [
        {"name": "Invoice", "path": "/home/owner/Documents/invoice.pdf", "kind": "pdf",
         "size": 1024, "modified": "2026-09-01"}], "matches": 1}
    out2 = SRC.from_tool_result("my_files", find_result)
    check("find(): one file reference, from 'found' not 'results'", out2 == [
        {"kind": "file", "path": "/home/owner/Documents/invoice.pdf", "title": "Invoice"}], out2)
    # jarvis_documents.read()'s real shape - the file itself, no list at all.
    read_result = {"ok": True, "name": "Invoice", "path": "/home/owner/Documents/invoice.pdf",
                   "kind": "pdf", "part": 1, "parts": 1, "title": "Invoice",
                   "text": "the whole private body of the file"}
    out3 = SRC.from_tool_result("my_files", read_result)
    check("read(): one file reference, never the text", out3 == [
        {"kind": "file", "path": "/home/owner/Documents/invoice.pdf", "title": "Invoice"}], out3)
    check("never the file's text", all("private body" not in json.dumps(s) for s in out3))


def t_file_read_becomes_a_file_reference():
    result = {"ok": True, "content": "the whole private content of this file", "truncated": False,
              "path": "/home/owner/notes.txt"}
    out = SRC.from_tool_result("file_read", result)
    check("one file reference, never the content",
          out == [{"kind": "file", "path": "/home/owner/notes.txt"}], out)


def t_unknown_tools_and_bad_shapes_give_nothing():
    check("a write tool gives nothing", SRC.from_tool_result("send_email", {"ok": True}) == [])
    check("a non-dict result gives nothing", SRC.from_tool_result("notes_search", "not a dict") == [])
    check("None gives nothing", SRC.from_tool_result("notes_search", None) == [])
    check("an unknown tool name gives nothing",
          SRC.from_tool_result("some_other_tool", {"ok": True, "results": [{"ref": "x"}]}) == [])


def t_file_read_now_reports_its_resolved_path():
    """jarvis_agent._run_file_read must hand back the REAL path it opened -
    the resolved one, not merely what the model asked for - so a source
    built from it is built from what was really read."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "notes.txt"
        p.write_text("hello", encoding="utf-8")
        out = AG._run_file_read({"path": str(p)})
    check("_run_file_read's own result now carries 'path'", out.get("ok") is True and out.get("path"),
          out)
    srcs = SRC.from_tool_result("file_read", out)
    check("...and from_tool_result reads it straight off that field",
          srcs and srcs[0]["path"] == out["path"], (srcs, out))


# --------------------------------------------------------------------------
#   record / sources_of / handle_get - the same shape as /api/memory/used
# --------------------------------------------------------------------------

def t_record_and_read_back():
    SRC._reset_for_tests()
    sources = [{"kind": "note", "ref": "Ideas.md", "title": "Ideas"}]
    quotes = ["a quote that was never read"]
    SRC.record(TID, sources, quotes)
    got = SRC.sources_of(TID)
    check("what is recorded is read back exactly", got == {"sources": sources,
                                                            "unverified_quotes": quotes}, got)
    check("an id this process never saw: empty, not an error",
          SRC.sources_of(TID2) == {"sources": [], "unverified_quotes": []})
    check("a malformed id: empty too, never raises", SRC.sources_of("not-hex") == {
        "sources": [], "unverified_quotes": []})
    check("recording under a bad id does nothing", SRC.record("not-hex", sources) is None
          and SRC.sources_of("not-hex")["sources"] == [])
    check("recording nothing does nothing (no empty row created)",
          SRC.record(TID2, [], []) is None and TID2 not in SRC._TURNS)


def t_caps_and_dedup():
    SRC._reset_for_tests()
    many = [{"kind": "file", "path": f"/f{i}.txt"} for i in range(SRC.MAX_PER_TURN + 10)]
    SRC.record(TID, many)
    check("capped at MAX_PER_TURN", len(SRC.sources_of(TID)["sources"]) == SRC.MAX_PER_TURN)


def t_handle_get_the_same_shape_as_memory_used():
    SRC._reset_for_tests()
    SRC.record(TID, [{"kind": "web", "url": "https://example.com"}])
    code, out = SRC.handle_get(f"turn_id={TID}")
    check("200 with the sources", code == 200 and out["sources"][0]["url"] == "https://example.com", out)
    code2, out2 = SRC.handle_get(f"turn_id={TID2}")
    check("an unseen turn: 200 with empty lists, never 404", code2 == 200 and out2 == {
        "sources": [], "unverified_quotes": []}, out2)
    code3, out3 = SRC.handle_get("turn_id=not-hex")
    check("a bad id: 400 in words", code3 == 400 and "turn_id" in out3.get("error", ""), out3)
    code4, out4 = SRC.handle_get("")
    check("no turn_id at all: 400", code4 == 400)


def t_install_wraps_do_get_only():
    hits = []

    class H:
        def __init__(self):
            self.sent = None
            self.path = ""

        def do_GET(self):
            hits.append("get0")

        def do_POST(self):
            hits.append("post0")

        def _send(self, code, out):
            self.sent = (code, out)
            return self.sent

    line = SRC.install(H, origin_ok=lambda self: True, token_ok=lambda self: True,
                       read_body=lambda self: b"{}")
    check("install returns a banner line naming the feature", "Where this came from" in line)
    line2 = SRC.install(H, origin_ok=lambda self: True, token_ok=lambda self: True, read_body=None)
    check("installing twice says already on, and does not re-wrap", "already on" in line2)

    SRC._reset_for_tests()
    SRC.record(TID, [{"kind": "note", "ref": "Ideas.md"}])
    h = H()
    h.path = f"{SRC.PATH}?turn_id={TID}"
    h.do_GET()
    check("GET /api/chat/sources is answered here",
          h.sent[0] == 200 and h.sent[1]["sources"][0]["ref"] == "Ideas.md", h.sent)

    h2 = H()
    h2.path = "/api/something/else"
    h2.do_GET()
    check("any other GET passes through to the original", "get0" in hits)

    # A fresh handler class, so origin_ok's refusal is exercised cleanly
    # (H above is already wrapped for a different origin_ok).

    class H2:
        def __init__(self):
            self.sent = None
            self.path = SRC.PATH

        def do_GET(self):
            hits.append("get0-h2")

        def _send(self, code, out):
            self.sent = (code, out)
            return self.sent
    SRC.install(H2, origin_ok=lambda self: False, token_ok=lambda self: True, read_body=None)
    h4 = H2()
    h4.do_GET()
    check("cross-origin: 403, refused before reading anything", h4.sent[0] == 403, h4.sent)


# --------------------------------------------------------------------------
#   The quote check
# --------------------------------------------------------------------------

def t_unverified_quotes():
    read_this_turn = ["The recipe says: add nutmeg and simmer for twenty minutes."]
    answer = 'The note says "add nutmeg and simmer for twenty minutes", so do that.'
    check("a quote that IS in what was read is not flagged",
          SRC.unverified_quotes(answer, read_this_turn) == [])
    bad_answer = 'The note says "always add three whole nutmegs", which is not there.'
    got = SRC.unverified_quotes(bad_answer, read_this_turn)
    check("a quote that is NOT there is flagged, word for word",
          got == ["always add three whole nutmegs"], got)
    check("spacing and case are ignored",
          SRC.unverified_quotes('it says "ADD   NUTMEG and simmer FOR twenty minutes"',
                                read_this_turn) == [])
    check("a short quote (under 3 words) is never checked",
          SRC.unverified_quotes('it says "nutmeg" apparently', read_this_turn) == [])
    check("nothing was read this turn: no quote is ever flagged, even a false one",
          SRC.unverified_quotes(bad_answer, []) == [])
    check("no quotes in the answer at all: nothing to report",
          SRC.unverified_quotes("Just an ordinary answer with no quotes.", read_this_turn) == [])
    check("not a string: []", SRC.unverified_quotes(None, read_this_turn) == [])
    check("curly quotes are read the same as straight ones",
          SRC.unverified_quotes("it says “add nutmeg and simmer for twenty minutes”",
                                read_this_turn) == [])
    check("a pure word check - never changes the text it is given",
          bad_answer == 'The note says "always add three whole nutmegs", which is not there.')


# --------------------------------------------------------------------------
#   _TurnWatch.took_in collects sources alongside its existing bookkeeping
# --------------------------------------------------------------------------

def t_took_in_collects_sources():
    watch = AG._TurnWatch()
    result = {"ok": True, "results": [{"title": "Soup", "ref": "Soup.md", "snippet": "n/a"}]}
    cleaned = watch.took_in("notes_search", result)
    check("the model's own copy is still cleaned/labelled as before",
          cleaned.get(AG.OUTSIDE_FIELD) == AG.OUTSIDE_LABEL, cleaned)
    check("the source was collected onto the watch",
          watch.sources == [{"kind": "note", "ref": "Soup.md", "title": "Soup"}], watch.sources)
    # A second, identical result must not duplicate the same source.
    watch.took_in("notes_search", result)
    check("the same source is not added twice", len(watch.sources) == 1, watch.sources)
    # A tool in _NOT_READING never contributes a source either.
    watch2 = AG._TurnWatch()
    watch2.took_in("calculator", {"ok": True, "value": 4})
    check("calculator (not a reading tool) contributes nothing", watch2.sources == [])


# --------------------------------------------------------------------------
#   End to end: run_local_turn, a real temporary vault
# --------------------------------------------------------------------------

class _Verdict:
    def __init__(self, allowed=True, tier="auto", outcome="approved"):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome
        self.reason, self.action, self.request_id = "", "", None


def scripted_stream(rounds):
    it = iter(rounds)

    def opener(url, payload):
        return W.FakeResponse(W.stream(next(it)))
    return opener


def _turn(vault_dir, messages, model_says, *, enabled_tools=("notes_search",)):
    import os
    old = os.environ.get("JARVIS_OBSIDIAN_VAULT")
    os.environ["JARVIS_OBSIDIAN_VAULT"] = str(vault_dir)
    streamed = []
    tool_call = [{"id": "n1", "name": "notes_search", "arguments": {"query": "soup"}}]
    rounds = [
        [("tool_calls", tool_call), ("done", "stop")],
        [("content", model_says), ("done", "stop")],
    ]
    try:
        result = AG.run_local_turn(
            messages, "jarvis-primary", ollama_url="http://127.0.0.1:11434",
            stream_out=streamed.append, open_stream=scripted_stream(rounds),
            gate_check=lambda *a, **k: _Verdict(), enabled_tools=set(enabled_tools),
            keepalive_seconds=60, status_delay=60, model_waking=lambda url, model: False)
    finally:
        if old is None:
            os.environ.pop("JARVIS_OBSIDIAN_VAULT", None)
        else:
            os.environ["JARVIS_OBSIDIAN_VAULT"] = old
    return result


def t_end_to_end_a_real_note_becomes_a_source():
    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / ".obsidian").mkdir()  # what jarvis_notes.vault_problem() requires
        (vault / "Soup.md").write_text("The recipe says: add nutmeg and simmer for twenty minutes.",
                                       encoding="utf-8")
        messages = [{"role": "user", "content": "what does my soup note say?",
                    "provenance": "typed"}]
        result = _turn(vault, messages, "Your note says the soup needs nutmeg.")
    check("the turn finished normally", result.get("finish_reason") == "stop", result)
    check("notes_search really ran", "notes_search" in result.get("tools_ran", []), result)
    sources = result.get("tool_sources") or []
    check("the real note became one source, by reference - never its text",
          sources == [{"kind": "note", "ref": "Soup.md", "title": "Soup"}], sources)
    check("no unverified quotes: the answer made no quoted claim",
          result.get("unverified_quotes") == [], result)


def t_end_to_end_a_fabricated_quote_is_flagged():
    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / ".obsidian").mkdir()
        (vault / "Soup.md").write_text("The recipe says: add nutmeg and simmer for twenty minutes.",
                                       encoding="utf-8")
        messages = [{"role": "user", "content": "what does my soup note say?",
                    "provenance": "typed"}]
        result = _turn(vault, messages,
                       'It literally says "boil the soup for three hours straight", apparently.')
    uq = result.get("unverified_quotes") or []
    check("the invented quote is flagged as not found in what was read",
          uq == ["boil the soup for three hours straight"], (uq, result.get("answer")))
    check("the streamed answer text itself is untouched by the check",
          result.get("answer") == 'It literally says "boil the soup for three hours straight", '
                                  'apparently.', result.get("answer"))


def t_end_to_end_nothing_read_means_no_quote_check_at_all():
    messages = [{"role": "user", "content": "how are you?", "provenance": "typed"}]
    streamed = []
    result = AG.run_local_turn(
        messages, "jarvis-primary", ollama_url="http://127.0.0.1:11434", stream_out=streamed.append,
        open_stream=scripted_stream([[("content", 'I said "I am doing fine today", thanks.'),
                                      ("done", "stop")]]),
        gate_check=lambda *a, **k: None, enabled_tools=set(),
        keepalive_seconds=60, status_delay=60, model_waking=lambda url, model: False)
    check("no tools ran, so nothing to read: unverified_quotes is empty regardless",
          result.get("unverified_quotes") == [], result)
    check("and no sources either", result.get("tool_sources") == [], result)


if __name__ == "__main__":
    for fn in (t_notes_search_becomes_a_note_or_wiki_reference,
               t_web_search_becomes_a_web_reference,
               t_my_files_becomes_a_file_reference_for_find_search_and_read,
               t_file_read_becomes_a_file_reference,
               t_unknown_tools_and_bad_shapes_give_nothing,
               t_file_read_now_reports_its_resolved_path,
               t_record_and_read_back,
               t_caps_and_dedup,
               t_handle_get_the_same_shape_as_memory_used,
               t_install_wraps_do_get_only,
               t_unverified_quotes,
               t_took_in_collects_sources,
               t_end_to_end_a_real_note_becomes_a_source,
               t_end_to_end_a_fabricated_quote_is_flagged,
               t_end_to_end_nothing_read_means_no_quote_check_at_all):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
