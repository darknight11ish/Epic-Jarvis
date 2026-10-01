"""test_topics_leaks.py - the guard for topic controls: no module reads saved
facts unless it is on this list, and each says what it does about topics.

    python3 backend/test_topics_leaks.py

docs/TOPIC-CONTROLS-DESIGN.md section 4.4 lists every code path that reads
facts and says, for each, whether a topic that may not be USED must be left out
("use"), or whether it only protects the owner and must see everything ("all").
That table was a promise. This makes it a checked list: the test WALKS the
backend's source (every module a suite is not, and the rebuilt ones) and finds
every module that

  * imports jarvis_memory (or names it in sys.modules.get), or
  * holds SQL that reads the facts table (FROM facts / JOIN facts);

each such module must be in READERS below with a role, or the build FAILS and
names the module. A new reader added next year cannot leak by being forgotten:
it is caught here first.

The roles, and what is checked for each:
  core     the memory module and the topic module themselves.
  default  reads through MemoryStore.search() and takes its default,
           topics="use" (jarvis_past.recall, the memory_search tool): every
           .search( call in it states no topics= at all - so it cannot have
           been switched to "all" by accident.
  use      reads facts that can reach a model, a screen or a voice, and
           filters: every .search( call states topics= "use" or "visible" (or
           relies on a helper that does), and a module with its OWN SQL must
           call topic_blocked / blocked_ids.
  all      only PROTECTS the owner (duplicate checks, the chatbot leak check,
           "said again"): every .search( call states topics="all".
  owner    the owner's own view or act on a fact by id (lists, Forget, Erase,
           history): it reads by id or asks for topics="visible"/"all" on
           purpose.
  mentions imports or names jarvis_memory but reads no fact text (a version
           check, a folder lookup, a comment).

No pytest, no network.
"""
import ast
import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
PASSED, FAILED = [], []

# module file (relative to backend/) -> (role, why)
READERS = {
    "rebuilt/jarvis_memory.py": ("core", "the memory module: search(topics=), topic_blocked()"),
    "jarvis_topics.py": ("core", "the topic module: reads facts to sort and count them"),
    "jarvis_past.py": ("default", "chat recall and past recall: store.search with the default "
                                  "(use)"),
    "jarvis_agent.py": ("default", "the memory_search tool goes through jarvis_past.recall"),
    "jarvis_places.py": ("use", "own SQL for 'where is my passport': topic_blocked('use')"),
    "jarvis_tidy.py": ("use", "own SQL, a local model reads the facts: topic_blocked('use')"),
    "jarvis_briefing.py": ("use", "list_auto(topics='use')"),
    "jarvis_quick.py": ("use", "answers from jarvis_places.lookup; topic names for the door"),
    "jarvis_entities.py": ("use", "the entity model pass shows fact text to the local model: "
                                  "Off topics excluded"),
    "jarvis_intake.py": ("use", "candidates(): topics='visible' (Off excluded); the duplicate "
                                "checks: topics='all'; its one SQL only compares words, "
                                "never shown to a model", "protective_sql"),
    "jarvis_auto_learn.py": ("use", "list_auto(topics=), and the contradiction check "
                                    "(topics='all')"),
    "jarvis_sensitive.py": ("all", "saved_topic(): the topic a saved fact was saved with - "
                                   "only makes an answer MORE careful"),
    "jarvis_chatbot.py": ("all", "the leak check reads saved facts to keep them OUT of a web "
                                 "chat"),
    "jarvis_search.py": ("all", "'would this search repeat a saved fact?': entities_view(all)"),
    "jarvis_feedback.py": ("owner", "reads one fact by id to see if it is still current"),
    "jarvis_forget_range.py": ("owner", "the owner's Forget a time frame sees every fact"),
    "jarvis_brain_reads.py": ("owner", "one fact's history, by id"),
    "jarvis_sources.py": ("owner", "'Where this came from': ids of an answer's facts"),
    "jarvis_backup.py": ("mentions", "copies memory.db whole; modes ride along in the file"),
    "jarvis_data_health.py": ("mentions", "checks the file exists"),
    "jarvis_owned_tables.py": ("mentions", "which tables Epic-Jarvis made in memory.db"),
    "jarvis_chat_log.py": ("mentions", "a docstring names jarvis_memory.erase()"),
    "jarvis_goals.py": ("mentions", "goals.db sits beside memory.db; reads no fact"),
    "jarvis_projects.py": ("mentions", "projects.db; reads no fact"),
    "jarvis_schedule.py": ("mentions", "schedule.db; reads no fact"),
    "jarvis_settings_registry.py": ("mentions", "calls jarvis_topics.set_mode"),
    "import_history.py": ("mentions", "writes proposals through jarvis_extract"),
    "rebuilt/jarvis_events.py": ("mentions", "names memory events"),
    "rebuilt/jarvis_framework.py": ("mentions", "the audit log and settings"),
    "rebuilt/jarvis_recall.py": ("mentions", "orders the facts it is given; reads none"),
    "rebuilt/jarvis_voice.py": ("mentions", "names memory.db in a comment"),
    "rebuilt/jarvis_initiative.py": ("mentions", "no fact reads (checked 2026-09-30)"),
    "selftest.py": ("mentions", "the owner-run self test"),
    "jarvis_second_card.py": ("mentions", "names memory in a docstring"),
}

SEARCH_RECEIVER = re.compile(r"(?:^|\.)(?:store|st|_store)(?:\(\))?$|store\(\)$")
SQL_FACTS = re.compile(r"\b(?:FROM|JOIN)\s+facts\b", re.I)
NON_SOURCE = re.compile(r"^(?:test_|eval_|_)")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def sources() -> list:
    out = []
    for folder in (HERE, HERE / "rebuilt"):
        for p in sorted(folder.glob("*.py")):
            if NON_SOURCE.match(p.name) and p.name not in ("_where.py",):
                continue
            if p.name in ("_where.py", "run_suites.py", "recover_from_claude_export.py"):
                continue
            rel = p.relative_to(HERE).as_posix()
            out.append((rel, p.read_text(encoding="utf-8")))
    return out


def analyse(text: str) -> dict:
    """What a module does with memory: {"touches", "sql", "searches": [call
    source, ...]}."""
    tree = ast.parse(text)
    touches = False
    sql = False
    searches = []
    # A call inside `except TypeError:` is the fallback for a store from before
    # the argument existed (a stand-in in a test): it cannot have topics at all.
    fallback = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ExceptHandler) and n.type is not None \
                and ast.unparse(n.type) == "TypeError":
            for m in ast.walk(n):
                fallback.add(id(m))
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            touches |= any(a.name == "jarvis_memory" for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            touches |= n.module == "jarvis_memory"
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            if n.value == "jarvis_memory":
                touches = True
            if SQL_FACTS.search(n.value) and len(n.value) < 600:
                sql = True
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "search":
            try:
                recv = ast.unparse(n.func.value)
            except Exception:
                recv = ""
            if SEARCH_RECEIVER.search(recv) and id(n) not in fallback:
                searches.append(ast.unparse(n))
    return {"touches": touches, "sql": sql, "searches": searches}


def t_every_module_that_reads_facts_is_listed():
    unlisted, stale = [], []
    found = {}
    for rel, text in sources():
        a = analyse(text)
        found[rel] = a
        if (a["touches"] or a["sql"]) and rel not in READERS:
            unlisted.append(rel)
    for rel in READERS:
        if rel not in found:
            stale.append(rel)
    check("no module reads facts without being on the list in test_topics_leaks.py",
          not unlisted,
          "unlisted (add it to READERS with a role, after deciding use / all): "
          + ", ".join(unlisted))
    check("every listed module still exists", not stale, ", ".join(stale))
    return found


def t_each_role_does_what_it_says(found):
    for rel, entry in READERS.items():
        role, why = entry[0], entry[1]
        a = found.get(rel)
        if a is None:
            continue
        calls = a["searches"]
        if role == "default":
            bad = [c for c in calls if "topics=" in c]
            check(f"{rel} (default): its .search() calls take the default (use)", not bad,
                  "; ".join(bad))
        elif role == "all":
            bad = [c for c in calls if 'topics="all"' not in c and "topics='all'" not in c]
            check(f'{rel} (all): every .search() call says topics="all"', not bad,
                  "; ".join(bad))
        elif role == "use":
            bad = [c for c in calls if "topics=" not in c]
            check(f"{rel} (use): every .search() call says which topics", not bad,
                  "; ".join(bad))
            if a["sql"] and "protective_sql" not in entry:
                text = dict(sources())[rel]
                check(f"{rel} (use): its own SQL is filtered (topic_blocked / blocked_ids)",
                      "topic_blocked(" in text or "blocked_ids(" in text or "_topic_hidden(" in text)
        elif role == "owner":
            bad = [c for c in calls if "topics=" not in c]
            check(f"{rel} (owner): any .search() call says which topics", not bad,
                  "; ".join(bad))
        elif role == "mentions":
            check(f"{rel} (mentions): reads no .search() of the store", not calls,
                  "; ".join(calls))


def t_the_guard_can_fail():
    """A module that reads facts and is not listed IS caught."""
    a = analyse('import jarvis_memory\nrows = jarvis_memory.store().search("x", k=3)\n')
    check("a new module that imports jarvis_memory is seen", a["touches"])
    b = analyse('c.execute("SELECT text FROM facts WHERE id=?", (1,))\n')
    check("a new module with SQL on the facts table is seen", b["sql"])
    c = analyse('hits = store.search("x", k=5)\n')
    check("a store.search() call is seen", len(c["searches"]) == 1)
    d = analyse('m = _RX.search("x")\n')
    check("a regex .search() is not mistaken for one", not d["searches"])


def main() -> int:
    found = None
    for fn in (t_every_module_that_reads_facts_is_listed,):
        print(f"\n--- {fn.__name__} ---")
        try:
            found = fn()
        except Exception:
            traceback.print_exc()
            FAILED.append(fn.__name__)
    for fn in (t_each_role_does_what_it_says,):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn(found or {})
        except Exception:
            traceback.print_exc()
            FAILED.append(fn.__name__)
    for fn in (t_the_guard_can_fail,):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            traceback.print_exc()
            FAILED.append(fn.__name__)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + "; ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
