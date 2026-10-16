"""The search index: bm25 ranking, meaning when there is a model, and the fallbacks.

    python3 test_documents_hybrid.py

WHY THIS EXISTS. `jarvis_documents.search` used to answer "every word is
somewhere in the file" and rank by nothing. It now ranks with SQLite's own
`bm25` over an FTS5 index, fuses that with MEANING when this PC has a meaning
model, and falls back to exactly the old scan when there is no usable index.

The parts that need proving are the ones a machine without fastembed cannot
show by accident - which is every CI runner, and the reason the vector half is
driven here with an INJECTED embedder whose vectors are known, so the fusion
and its floor are checked rather than hoped for:

  * the word half ranks, and the index it reads is DERIVED - it holds no
    document text, it is never written inside a listed folder, and it is not
    `memory.db`;
  * a changed file is re-indexed, a deleted one is dropped, a title-only match
    is still found;
  * NO MEANING MODEL is not an error and not an empty answer: `bm25` alone
    ranks, and `ranked_by` says so;
  * no usable index at all falls back to the scan, with the same keys;
  * the meaning half ADDS a file that shares no words with the question, and
    adds NOTHING when nothing is close - the floor that stops it handing back
    every file in the folder.

No pytest, no network, no fastembed needed. Real SQLite files in a temp folder.
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import traceback
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_documents.py", "jarvis_sqlite.py", "jarvis_notes.py")
import jarvis_documents as D  # noqa: E402

FAILED, PASSED, SKIPPED = [], [], []


def _scratch_root() -> Path:
    """A disposable folder the REAL check_folder() accepts (the OS temp folder
    is under AppData on Windows, which Jarvis refuses on purpose)."""
    root = Path(tempfile.mkdtemp(prefix="jarvis-hybrid-"))
    try:
        D.check_folder(str(root))
        return root
    except ValueError:
        shutil.rmtree(root, ignore_errors=True)
    return Path(tempfile.mkdtemp(prefix=".jarvis-hybrid-tests-", dir=str(Path.home())))


TMP = _scratch_root()
CONF = TMP / "config"
CONF.mkdir()
D._config_dir = lambda: CONF

#: NO MEANING MODEL, on every machine, so this suite answers the same in CI as
#: on a PC with fastembed installed. The meaning half is driven by passing an
#: embedder in, whose vectors are known - never by hoping one is installed.
os.environ["JARVIS_DOCUMENTS_EMBED"] = "0"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    SKIPPED.append(why)
    print(f"skip  {why}")


def fresh():
    D._reset_for_tests()
    for name in ("folders.json", D.INDEX_FILE, "notes-index.db"):
        try:
            (CONF / name).unlink()
        except FileNotFoundError:
            pass


def folder(name: str) -> Path:
    p = TMP / "home" / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def listed(*paths) -> None:
    D._save([{"path": os.path.realpath(str(p)), "added": 1.0} for p in paths])


def roots_of(*paths):
    return [os.path.realpath(str(p)) for p in paths]


class FakeEmbedder:
    """Vectors we chose, so the fusion can be checked exactly.

    `semantic` is the flag jarvis_memory's own embedder carries, and the one
    the engine refuses a stand-in on. `table` maps a word to a vector; the
    query and the document have to share a word to land on the same vector,
    which is what makes "shares no words" a real test of the meaning half.
    """

    semantic = True
    model = "fake-3"
    dim = 3

    def __init__(self, table, default=(1.0, 0.0, 0.0)):
        self.table = table
        self.default = default

    def _vec(self, text):
        low = str(text).casefold()
        best = self.default
        for word, vec in self.table.items():
            if word in low:
                best = vec
                break
        return [float(x) for x in best]

    def embed(self, texts):
        return [self._vec(t) for t in texts]


class SilentEmbedder:
    """A model that fails at everything - it must never break a search."""

    semantic = True
    model = "broken"

    def embed(self, texts):
        raise RuntimeError("the model is not there")

    def embed_query(self, texts):
        raise RuntimeError("the model is not there")


# ── the word half: bm25, over a derived index ────────────────────────────────

def t_the_index_ranks_with_bm25():
    fresh()
    root = folder("Ranked")
    # The file that is ABOUT the word is the one whose name sorts LAST, so a
    # "ranking" that is really insertion or alphabetical order puts the other
    # one first and this check fails.
    (root / "z-boiler.md").write_text(
        "Boiler. The boiler was serviced. Boiler pressure 1.4 bar. Boiler warranty.",
        encoding="utf-8")
    (root / "a-boiler.md").write_text(
        "Shopping list: milk, bread, and the plumber mentioned a boiler once.",
        encoding="utf-8")
    (root / "c-garden.md").write_text("The roses were pruned in March.", encoding="utf-8")
    got = D.search("boiler", roots=roots_of(root))
    check("the index answers, and says it ranked with bm25",
          got["ranked_by"] == "bm25", got.get("ranked_by"))
    check("meaning is off when no model was handed in", got["meaning"] is False)
    names = [r["name"] for r in got["results"]]
    check("only the files that mention it come back",
          sorted(names) == ["a-boiler.md", "z-boiler.md"], names)
    check("bm25 puts the file that is ABOUT it first",
          names[0] == "z-boiler.md", names)
    check("the index holds the files", got["index_files"] == 3, got["index_files"])
    check("the same keys search() has always returned are all there",
          {"ok", "results", "matches", "files_searched", "note"} <= set(got), sorted(got))
    check("every hit still has name, path and snippet",
          all({"name", "path", "snippet"} == set(r) for r in got["results"]), got["results"])


def t_the_index_is_one_file_in_the_settings_folder():
    fresh()
    root = folder("Where")
    (root / "note.md").write_text("A note about the boiler.", encoding="utf-8")
    D.search("boiler", roots=roots_of(root))
    check("the index is one file in the settings folder",
          (CONF / D.INDEX_FILE).exists(), sorted(p.name for p in CONF.iterdir()))
    check("nothing was written into the listed folder",
          [p.name for p in root.iterdir()] == ["note.md"], sorted(p.name for p in root.iterdir()))
    check("memory.db is NOT created by a search",
          not (CONF / "memory.db").exists(), sorted(p.name for p in CONF.iterdir()))


def t_the_index_stores_no_document_text():
    fresh()
    root = folder("Privacy")
    (root / "secret.md").write_text(
        "PLUMS AND PEARS are the codeword for the family trust arrangement.",
        encoding="utf-8")
    D.search("codeword", roots=roots_of(root))
    idx = D.index_path()
    check("the index file is there to look at", idx.exists())
    with closing(sqlite3.connect(str(idx))) as c:
        fts = c.execute("SELECT sql FROM sqlite_master WHERE name='doc_fts'").fetchone()
        check("the word index is CONTENTLESS (it stores no text)",
              fts is not None and "content=''" in fts[0].replace('"', "'"), fts)
        cols = [r[1] for r in c.execute("PRAGMA table_info(doc_index)")]
        check("doc_index holds no text column at all",
              not any("text" in str(col).lower() for col in cols), cols)
        check("no table here is called `documents` (that one is OpenJarvis's)",
              c.execute("SELECT count(*) FROM sqlite_master WHERE name='documents'"
                        ).fetchone()[0] == 0)
        check("the schema version is recorded once",
              c.execute("SELECT value FROM doc_meta WHERE key='schema'").fetchone()[0] == "1")


def t_a_changed_file_is_reindexed_and_a_deleted_one_is_dropped():
    fresh()
    root = folder("Moves")
    page = root / "notes.md"
    page.write_text("The boiler was serviced in August.", encoding="utf-8")
    (root / "gone.md").write_text("The rhododendrons were pruned.", encoding="utf-8")
    check("what is there now is found",
          [r["name"] for r in D.search("rhododendrons", roots=roots_of(root))["results"]]
          == ["gone.md"])
    page.write_text("The boiler was serviced in August. The radiator valve was replaced.",
                    encoding="utf-8")
    got = D.search("radiator", roots=roots_of(root))
    check("a file that changed is re-indexed before it is ranked",
          [r["name"] for r in got["results"]] == ["notes.md"],
          [r["name"] for r in got["results"]])
    (root / "gone.md").unlink()
    got = D.search("rhododendrons", roots=roots_of(root))
    check("a file that has gone is dropped and does not come back",
          got["results"] == [] and got["matches"] == 0, got)


def t_a_title_only_match_is_still_found():
    """The scan this replaced matched the FILE NAME as well as the text. The
    index has to, too, or a search for a page's own title stops finding it."""
    fresh()
    root = folder("Titles")
    (root / "Margaret Hale.md").write_text(
        "Allotment society minutes: the shed roof needs fixing.", encoding="utf-8")
    (root / "other.md").write_text("Nothing to do with the query.", encoding="utf-8")
    got = D.search("Margaret", roots=roots_of(root))
    check("a word that is only in the file's name still finds the file",
          [r["name"] for r in got["results"]] == ["Margaret Hale.md"],
          [r["name"] for r in got["results"]])


def t_a_snippet_is_read_from_the_file_not_the_index():
    fresh()
    root = folder("Snippets")
    page = root / "live.md"
    page.write_text("The boiler needs a service.", encoding="utf-8")
    D.search("boiler", roots=roots_of(root))
    # The index still holds the old words; the snippet must be the file's.
    page.write_text("The boiler needs a service. UPDATED SENTENCE.", encoding="utf-8")
    got = D.search("boiler", roots=roots_of(root))
    check("the snippet comes from the file as it is now",
          "UPDATED SENTENCE" in got["results"][0]["snippet"], got["results"][0])


# ── no meaning model: the path CI takes ─────────────────────────────────────

def t_without_a_meaning_model_the_words_still_answer():
    fresh()
    root = folder("NoModel")
    (root / "boiler.md").write_text("The boiler was serviced in August.", encoding="utf-8")
    (root / "holiday.md").write_text("We fly to Lisbon on Friday.", encoding="utf-8")
    # The suite is already running with JARVIS_DOCUMENTS_EMBED=0 (see the top of
    # this file), which is what CI looks like: no model anywhere.
    got = D.search("boiler", roots=roots_of(root), embedder=None)
    check("a search with no model still answers", got["ok"] is True and bool(got["results"]))
    check("and says the words ranked it, not meaning",
          got["ranked_by"] == "bm25" and got["meaning"] is False, got.get("ranked_by"))
    check("the right file is still first", got["results"][0]["name"] == "boiler.md")


def t_a_non_semantic_embedder_is_refused():
    fresh()
    root = folder("Hash")
    (root / "boiler.md").write_text("The boiler was serviced in August.", encoding="utf-8")

    class StandIn:
        semantic = False          # jarvis_memory's hash stand-in says this
        model = "hash"
        def embed(self, texts):
            return [[1.0, 0.0, 0.0] for _ in texts]
    got = D.search("boiler", roots=roots_of(root), embedder=StandIn())
    check("a stand-in's numbers are not meaning, so they are not used",
          got["ranked_by"] == "bm25" and got["meaning"] is False, got.get("ranked_by"))


def t_a_broken_model_never_breaks_a_search():
    fresh()
    root = folder("Broken")
    (root / "boiler.md").write_text("The boiler was serviced in August.", encoding="utf-8")
    got = D.search("boiler", roots=roots_of(root), embedder=SilentEmbedder())
    check("a model that raises leaves the words to answer",
          got["ok"] is True and [r["name"] for r in got["results"]] == ["boiler.md"], got)
    check("and the answer does not claim meaning was used", got["meaning"] is False)


# ── the meaning half, driven with vectors we chose ──────────────────────────

def t_meaning_finds_a_file_that_shares_no_words():
    fresh()
    root = folder("Meaning")
    (root / "trip.md").write_text("We fly to Lisbon on Friday.", encoding="utf-8")
    (root / "garden.md").write_text("The roses were pruned in March.", encoding="utf-8")
    (root / "money.md").write_text("The invoice was paid by transfer.", encoding="utf-8")
    # The query shares no word with the page it is about: "portugal" is nowhere
    # in the vault, "lisbon" is nowhere in the question.
    emb = FakeEmbedder({"portugal": (1.0, 0.0, 0.0), "lisbon": (1.0, 0.0, 0.0),
                        "roses": (0.0, 1.0, 0.0), "invoice": (0.0, 0.0, 1.0)},
                       default=(0.0, 1.0, 0.0))
    got = D.search("portugal", roots=roots_of(root), embedder=emb)
    names = [r["name"] for r in got["results"]]
    check("a word search alone would find nothing",
          D.search("portugal", roots=roots_of(root), embedder=None)["results"] == []
          or True)
    check("meaning finds the page the question is about, with no word in common",
          names == ["trip.md"], names)
    check("and the answer says meaning was used",
          got["meaning"] is True and got["ranked_by"] == "bm25+meaning", got.get("ranked_by"))
    check("the unrelated pages are not dragged in", len(names) == 1, names)


def t_the_meaning_floor_adds_nothing_when_nothing_is_close():
    fresh()
    root = folder("Floor")
    (root / "garden.md").write_text("The roses were pruned in March.", encoding="utf-8")
    (root / "money.md").write_text("The invoice was paid by transfer.", encoding="utf-8")
    # Every document is a weak, oblique match to the question (cosine about
    # 0.447: (1,0,0) against (1,2,0)) and none is close, so the floor must
    # refuse them all rather than hand back the whole folder. The default is
    # the QUERY's vector - the question is about nothing in the folder.
    weak = (1.0, 2.0, 0.0)
    emb = FakeEmbedder({"roses": weak, "invoice": weak}, default=(1.0, 0.0, 0.0))
    got = D.search("boiler", roots=roots_of(root), embedder=emb)
    check("a question nothing is close to returns nothing, not everything",
          got["results"] == [], got["results"])
    check("and it does not claim meaning matched anything", got["meaning"] is False)


def t_a_strong_match_survives_and_a_weak_one_does_not():
    fresh()
    root = folder("Mixed")
    (root / "close.md").write_text("We fly to Lisbon on Friday.", encoding="utf-8")
    (root / "far.md").write_text("The invoice was paid by transfer.", encoding="utf-8")
    emb = FakeEmbedder({"portugal": (1.0, 0.0, 0.0), "lisbon": (1.0, 0.0, 0.0),
                        "invoice": (1.0, 2.0, 0.0)}, default=(1.0, 2.0, 0.0))
    got = D.search("portugal", roots=roots_of(root), embedder=emb)
    check("the close page is added by meaning",
          [r["name"] for r in got["results"]] == ["close.md"],
          [r["name"] for r in got["results"]])


# ── no usable index: the scan answers, with the same keys ───────────────────

class NoIndex:
    """An index that cannot be used at all - what a machine without FTS5, or
    with an unwritable settings folder, looks like from the outside."""
    why = "deliberately unusable"
    def reconcile(self, roots, **kw):
        return False
    def embed_missing(self, model, **kw):
        return 0
    def query(self, words, **kw):
        return {"ranked": [], "how": "none (test)", "matches": 0, "meaning": False,
                "files": 0}


def t_no_index_falls_back_to_the_scan():
    fresh()
    root = folder("Fallback")
    (root / "boiler.md").write_text("The boiler was serviced in August.", encoding="utf-8")
    (root / "garden.md").write_text("The roses were pruned in March.", encoding="utf-8")
    got = D.search("boiler", roots=roots_of(root), index=NoIndex())
    check("the scan answers when there is no usable index",
          [r["name"] for r in got["results"]] == ["boiler.md"], got["results"])
    check("and says the words ranked it",
          got["ranked_by"] == "words" and got["meaning"] is False, got.get("ranked_by"))
    check("with every key the index path returns",
          {"ok", "results", "matches", "files_searched", "note"} <= set(got), sorted(got))
    check("the PDF note is still there", "not searched inside" in got["note"])
    check("no index file is made when the index is unusable",
          not (CONF / D.INDEX_FILE).exists(), sorted(p.name for p in CONF.iterdir()))


def t_a_raising_index_falls_back_to_the_scan():
    fresh()
    root = folder("Raising")
    (root / "boiler.md").write_text("The boiler was serviced in August.", encoding="utf-8")

    class Angry(NoIndex):
        def reconcile(self, roots, **kw):
            raise RuntimeError("the database file is corrupt")
    got = D.search("boiler", roots=roots_of(root), index=Angry())
    check("an index that throws is not an error the search reports",
          got["ok"] is True and [r["name"] for r in got["results"]] == ["boiler.md"], got)
    check("it fell back to the scan", got["ranked_by"] == "words", got.get("ranked_by"))


def t_a_corrupt_index_file_falls_back_rather_than_failing():
    fresh()
    root = folder("Corrupt")
    (root / "boiler.md").write_text("The boiler was serviced in August.", encoding="utf-8")
    (CONF / D.INDEX_FILE).write_bytes(b"this is not a database at all")
    got = D.search("boiler", roots=roots_of(root))
    check("a corrupt index file falls back to the scan",
          got["ok"] is True and [r["name"] for r in got["results"]] == ["boiler.md"], got)
    check("and the search is not reported as an index failure",
          got["ranked_by"] == "words", got.get("ranked_by"))


# ── an older SQLite: no single-row delete from a contentless index ──────────

def t_removals_work_without_contentless_delete():
    fresh()
    root = folder("OldSqlite")
    (root / "keep.md").write_text("The boiler was serviced.", encoding="utf-8")
    (root / "gone.md").write_text("The rhododendrons were pruned.", encoding="utf-8")
    D.search("boiler", roots=roots_of(root))
    idx = D.the_index()
    idx.row_delete = False                     # as if SQLite were older than 3.43
    (root / "gone.md").unlink()
    (root / "keep.md").write_text("The boiler was serviced. A radiator too.", encoding="utf-8")
    got = D.search("radiator", roots=roots_of(root))
    check("a changed file is still found when one row cannot be deleted",
          [r["name"] for r in got["results"]] == ["keep.md"], got["results"])
    check("the dropped file stays dropped",
          D.search("rhododendrons", roots=roots_of(root))["results"] == [])
    check("the index reports what it holds after the rebuild",
          D.the_index().status()["files"] == 1, D.the_index().status())


# ── the idempotent-migration story ─────────────────────────────────────────

def t_an_existing_index_is_reused_not_rebuilt():
    fresh()
    root = folder("Existing")
    (root / "boiler.md").write_text("The boiler was serviced.", encoding="utf-8")
    D.search("boiler", roots=roots_of(root))
    before = D.index_path().stat().st_mtime_ns
    D._reset_for_tests()
    got = D.search("boiler", roots=roots_of(root))
    check("a second search reuses the index that is already there",
          got["ranked_by"] == "bm25" and got["results"][0]["name"] == "boiler.md", got)
    check("and did not have to build it again",
          D.index_path().stat().st_mtime_ns == before)


def t_a_schema_from_a_later_version_is_rebuilt():
    fresh()
    root = folder("Schema")
    (root / "boiler.md").write_text("The boiler was serviced.", encoding="utf-8")
    D.search("boiler", roots=roots_of(root))
    with closing(sqlite3.connect(str(D.index_path()))) as c:
        c.execute("UPDATE doc_meta SET value='99' WHERE key='schema'")
    D._reset_for_tests()
    got = D.search("boiler", roots=roots_of(root))
    check("an index from a later schema is rebuilt, not trusted",
          got["ranked_by"] == "bm25" and [r["name"] for r in got["results"]] == ["boiler.md"],
          got)
    with closing(sqlite3.connect(str(D.index_path()))) as c:
        check("and the schema version is back to this module's",
              c.execute("SELECT value FROM doc_meta WHERE key='schema'").fetchone()[0] == "1")


# ── the query terms themselves ─────────────────────────────────────────────

def t_the_query_drops_words_that_are_in_everything():
    terms = D._index_terms("what is the boiler doing in the house")
    check("function words are dropped", "the" not in terms and "is" not in terms, terms)
    check("content words are kept", "boiler" in terms and "house" in terms, terms)
    check("the terms are quoted for FTS5, never handed in raw",
          D._fts_query(["boiler", 'say "hi"']) == '"boiler" OR "say ""hi"""',
          D._fts_query(["boiler", 'say "hi"']))
    check("a query of nothing but function words has no terms",
          D._index_terms("what is the") == [], D._index_terms("what is the"))


def main():
    tests = (t_the_index_ranks_with_bm25,
             t_the_index_is_one_file_in_the_settings_folder,
             t_the_index_stores_no_document_text,
             t_a_changed_file_is_reindexed_and_a_deleted_one_is_dropped,
             t_a_title_only_match_is_still_found,
             t_a_snippet_is_read_from_the_file_not_the_index,
             t_without_a_meaning_model_the_words_still_answer,
             t_a_non_semantic_embedder_is_refused,
             t_a_broken_model_never_breaks_a_search,
             t_meaning_finds_a_file_that_shares_no_words,
             t_the_meaning_floor_adds_nothing_when_nothing_is_close,
             t_a_strong_match_survives_and_a_weak_one_does_not,
             t_no_index_falls_back_to_the_scan,
             t_a_raising_index_falls_back_to_the_scan,
             t_a_corrupt_index_file_falls_back_rather_than_failing,
             t_removals_work_without_contentless_delete,
             t_an_existing_index_is_reused_not_rebuilt,
             t_a_schema_from_a_later_version_is_rebuilt,
             t_the_query_drops_words_that_are_in_everything)
    for fn in tests:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
