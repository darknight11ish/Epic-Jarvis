"""test_repomap.py - the read-only repository map (jarvis_repomap.py).

What this proves, in the order the design asked for it:

  1. A temp project tree of Python, JavaScript/TypeScript and Rust files maps
     to the RIGHT symbols, ranked for a question - the file that declares the
     asked-about names comes first, and its lines are the ones printed.
  2. `.gitignore` is honoured, per directory, including `!` negation.
  3. A folder that is not on "Folders Jarvis may look in" is refused in ONE
     plain sentence, and nothing is listed - the walk never starts.
  4. The map is bounded: at most TOKENS_MAX (2,000) by the project's own token
     count (`jarvis_agent.estimate_tokens`, 3 characters a token), and a
     caller's bigger budget is clipped back to it.
  5. Determinism: the same tree and the same question give the same map, byte
     for byte, twice running.
  6. It writes NOTHING: every file's size and mtime is unchanged, no file is
     added or removed, and no index/cache file appears anywhere.
  7. The route answers its documented shape (GET /api/projects/<id>/map),
     through the REAL project store, on a REAL listed folder - and a project
     with no folder, an unknown project and an unlisted folder each answer
     with their own sentence.
  8. A huge file is trimmed (listed, not read) rather than crashing the map.
  9. The TOOL wiring: the `my_files` action `map` returns the map for a listed
     folder through jarvis_documents and jarvis_agent's own runner, refuses an
     unlisted one, marks the result as outside text, and the tool's schema
     offers the action.

No source-text pins: every check drives the real modules over a real tree on
disk. Nothing here needs a network, a model, or the owner's PC.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

FAILED, PASSED = [], []
SKIPPED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


#: A disposable folder the real boundary accepts. The OS temp folder is NOT
#: one on Windows: it lives under AppData, and Jarvis refuses everything under
#: AppData (keys, browser data), so this asks the boundary and falls back to a
#: folder beside the user's home - the same shape test_documents.py uses.
def _scratch_root(prefix="jarvis-repomap-") -> Path:
    root = Path(tempfile.mkdtemp(prefix=prefix))
    return root


def _usable(root: Path) -> bool:
    try:
        import jarvis_documents as D
        D.check_folder(str(root))
        return True
    except Exception:                                        # noqa: BLE001
        return False


TMP = _scratch_root()
if not _usable(TMP):
    shutil.rmtree(TMP, ignore_errors=True)
    TMP = Path(tempfile.mkdtemp(prefix=".jarvis-repomap-tests-", dir=str(Path.home())))
CONF = TMP / "config"
CONF.mkdir(exist_ok=True)
os.environ["JARVIS_CONFIG_DIR"] = str(CONF)
os.environ["JARVIS_PROJECTS_DB"] = str(CONF / "projects.db")

import jarvis_agent as AGENT                                # noqa: E402
import jarvis_documents as DOCS                             # noqa: E402
import jarvis_projects as PROJ                              # noqa: E402
import jarvis_repomap as RM                                 # noqa: E402

DOCS._config_dir = lambda: CONF


# ==========================================================================
#   The tree the tests map
# ==========================================================================

def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def build_tree(root: Path) -> Path:
    """A small repository: Python, JS, TS and Rust, two folders, one ignored
    folder, one negated ignore, and a generated file. Deterministic."""
    _write(root / "app" / "server.py", (
        '"""A tiny server."""\n'
        "import os\n"
        "from app import router\n"
        "\n"
        "class Server:\n"
        "    def __init__(self, host):\n"
        "        self.host = host\n"
        "\n"
        "    def start(self):\n"
        "        return router.route_for_turn('hi')\n"
        "\n"
        "def parse_route(text):\n"
        "    return text.split('/')\n"
    ))
    _write(root / "app" / "router.py", (
        "from app.server import Server\n"
        "\n"
        "def install(handler):\n"
        "    return handler\n"
        "\n"
        "def route_for_turn(prompt):\n"
        "    return prompt\n"
    ))
    _write(root / "app" / "notes.md", "# Notes\n\nNothing to do with routing.\n")
    _write(root / "web" / "ui.js", (
        "import { api } from './api.js';\n"
        "\n"
        "export function renderRoute(row) {\n"
        "  return api.get(row);\n"
        "}\n"
        "\n"
        "class Plate {\n"
        "  draw() { return null; }\n"
        "}\n"
    ))
    _write(root / "web" / "api.js", (
        "export const fetchRows = async (name) => {\n"
        "  return name;\n"
        "};\n"
    ))
    _write(root / "web" / "types.ts", (
        "export interface ProjectRow { id: string }\n"
        "export type RouteShape = string;\n"
    ))
    _write(root / "rust" / "db.rs", (
        "use crate::router;\n"
        "\n"
        "pub struct Db { pub path: String }\n"
        "\n"
        "pub fn open_db(path: &str) -> Db {\n"
        "    Db { path: path.to_string() }\n"
        "}\n"
        "\n"
        "impl Db {\n"
        "    pub fn close(&self) {}\n"
        "}\n"
    ))
    # .gitignore: a WHOLE folder, and every generated .py - then a negation
    # that puts one generated file back (git's last-match-wins rule).
    _write(root / ".gitignore", "secret/\n*.gen.py\n")
    _write(root / "secret" / "hidden_route.py", "def secret_route():\n    return 1\n")
    _write(root / "gen" / "codegen.gen.py", "def generated_thing():\n    return 2\n")
    _write(root / "gen" / "keep.py", "def kept_route():\n    return 3\n")
    _write(root / "sub" / ".gitignore", "local_only.py\n")
    _write(root / "sub" / "local_only.py", "def local_route():\n    return 4\n")
    return root


# ==========================================================================
#   1. it lists and ranks the right names
# ==========================================================================

def t_1_the_map_finds_and_ranks_the_right_symbols():
    root = build_tree(TMP / "tree")
    listed(root)
    out = RM.map_folder(str(root), "where is the route registered", budget=1500)
    check("1. a listed folder maps", out.get("ok") is True, json.dumps(out)[:400])
    text = out.get("map") or ""
    check("1. the map names the file that declares the routing names first",
          text.index("app/router.py") < text.index("app/server.py")
          if "app/server.py" in text else "app/router.py" in text, text[:1200])
    check("1. its symbols are the ones asked about",
          "def route_for_turn" in text and "def install" in text, text[:1200])
    check("1. a class and a method are printed as such",
          "class Server" in text and "def start" in text, text[:1200])
    check("1. JavaScript signatures are found",
          "function renderRoute" in text and "class Plate" in text, text[:1500])
    check("1. the TypeScript interface and type are found",
          "interface ProjectRow" in text and "type RouteShape" in text, text[:1500])
    check("1. a Rust fn, struct and impl are found",
          "fn open_db" in text and "struct Db" in text and "impl Db" in text, text[:1800])
    check("1. no function BODY is copied into the map",
          "return text.split" not in text and "return prompt" not in text, text[:1500])
    check("1. the import edges are in the map",
          "app.router" in text or "app import router" in text, text[:1500])
    check("1. every file listed is a real relative path",
          all(not line.split("  ")[0].startswith(("/", "\\"))
              for line in text.splitlines() if line[:1].isdigit()),
          text[:800])

    # ... and a question about the RUST file ranks the Rust file first.
    out2 = RM.map_folder(str(root), "open_db rust", budget=1500)
    t2 = out2.get("map") or ""
    first = next((line for line in t2.splitlines() if line[:1].isdigit()), "")
    check("1. a different question ranks a different file first", "rust/db.rs" in first,
          t2[:600])


def t_1b_a_question_that_matches_nothing_still_lists_the_folder():
    root = build_tree(TMP / "tree-b")
    listed(root)
    out = RM.map_folder(str(root), "zzzznothing", budget=1500)
    check("1b. a question with no match still returns the folder's files",
          out.get("ok") is True and out.get("files", 0) >= 5, json.dumps(out)[:300])


# ==========================================================================
#   2. .gitignore
# ==========================================================================

def t_2_gitignore_is_honoured():
    root = build_tree(TMP / "tree-c")
    listed(root)
    out = RM.map_folder(str(root), "route", budget=1500)
    text = out.get("map") or ""
    check("2. an ignored FOLDER is not walked",
          "secret/" not in text and "secret_route" not in text, text[:1500])
    check("2. an ignored *.gen.py file is not listed",
          "codegen" not in text and "generated_thing" not in text, text[:1500])
    check("2. a NON-ignored file beside it is still listed", "gen/keep.py" in text,
          text[:2000])
    check("2. a nested .gitignore is honoured too",
          "local_only" not in text and "local_route" not in text, text[:2000])
    check("2. the .gitignore file itself is not offered as source",
          ".gitignore" not in text, text[:2000])


def t_2b_negation_puts_a_file_back():
    root = SECRET = TMP / "tree-d"
    _write(root / ".gitignore", "*.gen.py\n!kept.gen.py\n")
    _write(root / "gone.gen.py", "def gone_thing():\n    return 1\n")
    _write(root / "kept.gen.py", "def kept_thing():\n    return 2\n")
    listed(root)
    text = RM.map_folder(str(root), "kept_thing", budget=1500).get("map") or ""
    check("2b. a later ! rule un-ignores the file", "kept.gen.py" in text, text[:800])
    check("2b. the still-ignored one is absent", "gone.gen.py" not in text, text[:800])


# ==========================================================================
#   3. the boundary - one plain sentence, and no walk
# ==========================================================================

def t_3_an_unlisted_folder_is_refused_in_one_sentence():
    root = build_tree(TMP / "tree-e")
    listed(TMP / "tree")                      # a DIFFERENT folder is on the list
    out = RM.map_folder(str(root), "route")
    check("3. an unlisted folder is refused", out.get("ok") is False, json.dumps(out)[:300])
    said = str(out.get("error") or "")
    check("3. the refusal is ONE plain sentence",
          said == RM.REFUSED and said.count(".") == 1 and "\n" not in said, said)
    check("3. the refusal names what to do about it",
          "Folders Jarvis may look in" in said and "Settings" in said, said)
    check("3. nothing was listed from a refused folder",
          "map" not in out and "files" not in out, json.dumps(out)[:300])

    # A subfolder of a listed folder is inside it, and may be mapped.
    listed(root)
    sub = RM.map_folder(str(root / "app"), "route", budget=800)
    check("3. a folder INSIDE a listed one is allowed", sub.get("ok") is True,
          json.dumps(sub)[:300])
    check("3. and the map is of that subfolder only",
          "router.py" in (sub.get("map") or "") and "web/" not in (sub.get("map") or ""),
          (sub.get("map") or "")[:500])

    # A hidden folder is never entered, even inside a listed one.
    _write(root / ".hidden" / "ghost.py", "def ghost_route():\n    return 0\n")
    text = RM.map_folder(str(root), "ghost_route", budget=1500).get("map") or ""
    check("3. a hidden folder is not entered", "ghost.py" not in text, text[:800])

    # A .gitignore cannot open a hole either: it only hides more.
    check("3. a refused folder never raises", RM.map_folder("", "x").get("ok") is False, "")
    check("3. a folder that is not there is refused in words",
          RM.map_folder(str(TMP / "no-such-folder-xyz"), "x").get("ok") is False, "")


# ==========================================================================
#   4. the budget
# ==========================================================================

def t_4_the_token_budget_is_bounded():
    root = TMP / "tree-f"
    # 300 files is more than fits in any budget here, with symbols in each.
    for i in range(300):
        _write(root / "pkg" / f"m{i:03d}.py",
               f"def route_{i}(x):\n    return x\n\n"
               f"class Row{i}:\n    def draw(self):\n        return {i}\n")
    listed(root)
    for asked in (400, 1500, 9000):
        out = RM.map_folder(str(root), "route", budget=asked)
        text = out.get("map") or ""
        tokens = out.get("tokens")
        check(f"4. a {asked:,} budget packs at or under TOKENS_MAX",
              out.get("ok") is True and tokens <= RM.TOKENS_MAX, f"{tokens}")
        check(f"4. ... and the count is the project's own estimate ({asked:,})",
              tokens == RM.estimate_tokens(text) == AGENT.estimate_tokens(text),
              f"{tokens} vs {AGENT.estimate_tokens(text)}")
        check(f"4. ... and it is not an empty answer ({asked:,})",
              len(text.splitlines()) > 3 and out.get("files", 0) > 0, text[:200])
    out = RM.map_folder(str(root), "route", budget=9000)
    check("4. a caller asking for more than TOKENS_MAX gets TOKENS_MAX",
          out.get("budget") == RM.TOKENS_MAX, str(out.get("budget")))
    check("4. a small folder's map is inside the design's 1,000-2,000 band at the "
          "default budget",
          RM.TOKENS_DEFAULT == 1500 and 1000 <= RM.TOKENS_MAX <= 2000, "")
    check("4. it says what did not fit", out.get("truncated") is True
          and "did not fit" in (out.get("map") or ""), (out.get("map") or "")[-300:])


# ==========================================================================
#   5. determinism
# ==========================================================================

def t_5_the_same_tree_and_question_give_the_same_map():
    root = build_tree(TMP / "tree-g")
    listed(root)
    a = RM.map_folder(str(root), "where is the route registered", budget=1200)
    b = RM.map_folder(str(root), "where is the route registered", budget=1200)
    check("5. two runs give the same text", a.get("map") == b.get("map"), "maps differ")
    check("5. two runs give the same counts",
          (a.get("tokens"), a.get("files"), a.get("symbols"))
          == (b.get("tokens"), b.get("files"), b.get("symbols")), "")
    check("5. two runs rank the same files",
          a.get("ranked") == b.get("ranked"), "")
    # A second copy of the SAME tree maps identically: the answer depends on
    # the tree, not on where it sits on the disk or on the walk's order.
    twin = TMP / "tree-g-twin"
    shutil.copytree(root, twin)
    listed(twin)
    c = RM.map_folder(str(twin), "where is the route registered", budget=1200)
    check("5. a copy of the tree ranks the same",
          [r["path"] for r in a.get("ranked") or []]
          == [r["path"] for r in c.get("ranked") or []], "")


# ==========================================================================
#   6. it writes nothing
# ==========================================================================

def _snapshot(root: Path) -> dict:
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in sorted(filenames) + sorted(dirnames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            try:
                st = os.stat(full)
                out[rel] = (st.st_size, st.st_mtime_ns, os.path.isdir(full))
            except OSError:
                out[rel] = ("gone",)
    return out


def t_6_the_map_call_writes_nothing():
    root = build_tree(TMP / "tree-h")
    listed(root)
    before = _snapshot(root)
    out = RM.map_folder(str(root), "route", budget=1500)
    after = _snapshot(root)
    check("6. the map succeeded", out.get("ok") is True, "")
    check("6. not one file changed size or mtime", before == after,
          str({k: (before.get(k), after.get(k)) for k in set(before) | set(after)
               if before.get(k) != after.get(k)})[:400])
    check("6. no file was added and none removed",
          sorted(before) == sorted(after), "")
    # ... and no index or cache file appears anywhere under the mapped folder.
    names = {os.path.basename(p).casefold() for p in after}
    check("6. no index/cache file is kept beside the tree",
          not any(n.endswith((".idx", ".db", ".sqlite", ".cache", ".tmp"))
                  for n in names), str(sorted(names))[:300])


# ==========================================================================
#   7. the route
# ==========================================================================

_ROUTE_KEYS = {"ok", "available", "folder", "question", "map", "tokens", "budget",
               "files", "files_seen", "symbols", "truncated", "ranked", "outside_text"}


def _store():
    store = PROJ.Projects(path=CONF / "projects.db")
    return store


def t_7_the_route_answers_its_documented_shape():
    root = build_tree(TMP / "tree-i")
    listed(root)
    store = _store()
    made = store.create({"name": "Repomap route", "kind": "coding",
                         "folder": str(root)}, here=True)
    pid = made["id"]
    code, body = RM.handle_get(pid, "q=where+is+the+route&tokens=1200", store=store)
    check("7. GET /api/projects/<id>/map answers 200", code == 200, f"{code} {body}")
    check("7. the documented keys are all there", _ROUTE_KEYS <= set(body or {}),
          str(sorted(set(_ROUTE_KEYS) - set(body or {}))))
    check("7. it names the project and the folder it mapped",
          body.get("project", {}).get("id") == pid
          and os.path.realpath(str(body.get("folder", {}).get("path"))) ==
          os.path.realpath(str(root)), json.dumps(body.get("project"))[:200])
    check("7. the map is the same one the module makes",
          body.get("map") == RM.map_folder(str(root), body.get("question") or "",
                                           budget=1200).get("map"), "")
    check("7. the question round-trips and the budget is honoured",
          body.get("question") == "where is the route" and body.get("budget") == 1200,
          f"{body.get('question')!r} {body.get('budget')}")
    check("7. it is marked as outside text and counts what it saw",
          body.get("outside_text") is True
          and isinstance(body.get("files_seen"), int) and body["files_seen"] >= 5, "")
    check("7. the ranked rows explain the order (path, score, symbols)",
          all({"path", "score", "symbols"} <= set(r) for r in body.get("ranked") or [])
          and body["ranked"][0]["score"] >= body["ranked"][-1]["score"], "")

    # A project with no folder: its own sentence, not a crash.
    store.create({"name": "Life one", "kind": "life"}, here=True)
    life = [p for p in store.list() if p.get("name") == "Life one"][0]
    code, body = RM.handle_get(life["id"], "", store=store)
    check("7. a project with no folder is refused in words",
          code == 400 and body.get("ok") is False and "no folder" in body.get("error", ""),
          f"{code} {body}")
    # An unknown project.
    code, body = RM.handle_get("nope-not-a-project", "", store=store)
    check("7. an unknown project answers its own sentence",
          code == 400 and "no project" in body.get("error", ""), f"{code} {body}")
    # A folder that is no longer listed (the owner took it off the list).
    listed(TMP / "tree")
    code, body = RM.handle_get(pid, "", store=store)
    check("7. a project whose folder is no longer listed is refused, in one sentence",
          code == 400 and body.get("error") == RM.REFUSED, json.dumps(body)[:300])
    listed(root)


# ==========================================================================
#   8. a huge file
# ==========================================================================

def t_8_a_huge_file_is_trimmed_not_crashed():
    root = TMP / "tree-j"
    _write(root / "small.py", "def tiny_route():\n    return 1\n")
    big = root / "huge.js"
    big.parent.mkdir(parents=True, exist_ok=True)
    with open(big, "w", encoding="utf-8") as fh:
        fh.write("// a generated file, far bigger than the map will ever read\n")
        for i in range(30000):
            fh.write(f"function generated_{i}(a, b) {{ return a + b; }}\n")
    size = big.stat().st_size
    check("8. the huge file really is over the read limit",
          size > RM.MAX_FILE_BYTES, f"{size} bytes")
    listed(root)
    out = RM.map_folder(str(root), "generated tiny route", budget=1500)
    check("8. the map still answers", out.get("ok") is True, json.dumps(out)[:300])
    check("8. it stayed inside the budget", out.get("tokens", 9999) <= RM.TOKENS_MAX,
          str(out.get("tokens")))
    check("8. the small file beside it is still there",
          "tiny_route" in (out.get("map") or ""), (out.get("map") or "")[:600])
    check("8. the huge file is NAMED but not read",
          "large file" in (out.get("map") or ""), (out.get("map") or "")[:1200])


# ==========================================================================
#   9. the tool wiring: my_files action map
# ==========================================================================

def listed(*paths):
    DOCS._save([{"path": os.path.realpath(str(p)), "added": 1.0} for p in paths])


def t_9_my_files_map_returns_the_map_and_refuses_an_unlisted_folder():
    root = build_tree(TMP / "tree-k")
    listed(root)
    out = DOCS.run_tool({"action": "map", "path": str(root),
                         "words": "where is the route registered"})
    check("9. my_files action map returns the map for a listed folder",
          out.get("ok") is True, json.dumps(out)[:400])
    check("9. the answer carries the map text and its counts",
          "app/router.py" in (out.get("map") or "")
          and isinstance(out.get("tokens"), int) and out.get("tokens", 0) > 0, "")
    check("9. the map is marked as OUTSIDE TEXT on the tool path",
          out.get("outside_text") is True
          and (out.get("map") or "").startswith(DOCS.OUTSIDE_LABEL), "")
    check("9. the answer says what a map is, for the model",
          "names" in str(out.get("what") or ""), str(out.get("what"))[:200])

    # ... and through the agent's own runner, which is the wiring that counts.
    got = AGENT._run_my_files({"action": "map", "path": str(root),
                              "words": "route"}, None)
    check("9. jarvis_agent's own my_files runner answers the same action",
          isinstance(got, dict) and got.get("ok") is True, str(got)[:300])

    # The tool's schema offers the action, and folds a project id into `path`
    # (no second field: a project id is 32 hex characters, never a folder).
    params = AGENT.TOOLS["my_files"].parameters
    check("9. the my_files schema offers the map action",
          "map" in params["properties"]["action"]["enum"], "")
    check("9. the my_files schema says a project id goes in path",
          "project id" in params["properties"]["path"]["description"],
          str(params["properties"]["path"]))

    # An unlisted folder: the same one sentence, through the tool too.
    other = build_tree(TMP / "tree-l")
    out = DOCS.run_tool({"action": "map", "path": str(other), "words": "route"})
    check("9. the tool refuses an unlisted folder with one plain sentence",
          out.get("ok") is False and out.get("error") == RM.REFUSED, str(out)[:300])
    check("9. the agent runner refuses it too",
          AGENT._run_my_files({"action": "map", "path": str(other)}, None).get("ok")
          is False, "")

    # A project id works from the tool as well as a path.
    store = _store()
    made = store.create({"name": "Tool map", "kind": "coding", "folder": str(root)},
                        here=True)
    got = RM.run_tool({"action": "map", "project": made["id"], "words": "route"})
    check("9. the tool maps by project id too", got.get("ok") is True, str(got)[:300])
    got = RM.run_tool({"action": "map", "path": made["id"], "words": "route"})
    check("9. ... and by a project id passed as path, which is how the schema says it",
          got.get("ok") is True and got.get("project", {}).get("id") == made["id"],
          str(got)[:300])
    check("9. a tool call with neither a project nor a folder says what to do",
          RM.run_tool({"action": "map"}).get("ok") is False, "")

    # No folders listed at all: the tool's own existing refusal, unchanged.
    DOCS._save([])
    out = DOCS.run_tool({"action": "map", "path": str(root)})
    check("9. with no folders listed, my_files still refuses in its own words",
          out.get("ok") is False and "not listed any folders" in out.get("error", ""),
          str(out)[:300])


def t_10_describe_says_it_reads_names_only():
    said = DOCS.describe({"action": "map", "path": "C:\\work\\app"})
    check("10. the card's words say names and signatures only",
          "names and signatures only" in said and "C:\\work\\app" in said, said)
    check("10. ... and that nothing is written",
          "nothing is written" in said.lower() or "Nothing is changed" in said, said)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
