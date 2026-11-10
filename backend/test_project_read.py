"""test_project_read.py - reading ONE file inside a folder the owner listed
(jarvis_project_read.py, and the `project_read` tool in jarvis_agent.py).

What this proves, in the order the design asked for it:

  1. A .py file INSIDE a listed folder is read: the words come back, the answer
     names the real path it opened and the path inside the folder, and it is
     marked `outside_text` like every other read.
  2. A folder that is not on "Folders Jarvis may look in" is refused in ONE
     plain sentence, and nothing is read from it - the same sentence the
     repository map uses, because it is the same boundary function.
  3. A path that climbs out with `..`, and a whole path (a drive letter, a
     leading slash, a UNC name), are refused before a single path is built.
  4. A link that leads OUT of the folder is refused, and the refusal names the
     boundary rather than the word "symlink" - checked on a real link made in
     the temp folder (SKIPPED, never "passed", on a PC that cannot make one).
  5. The per-file cap IS the repository map's own constant (not a second
     number), a file past it is cut and says `truncated`, and the cut length is
     the cap exactly.
  6. `.gitignore` is honoured by the SAME walk the map uses: an ignored file, an
     ignored folder, a build folder and a hidden folder are all refused, a
     negation puts a file back, and the map's own walk lists exactly the files
     this tool will read.
  7. A registered project's id reads that project's own folder, and a folder
     taken off the owner's list stops being readable even for a project that
     still names it.
  8. NO CARD is raised. The tool is driven through the REAL `_one_call` with the
     REAL `jarvis_gate.check` (the published base, with the SHIPPED
     [autonomy.tiers] read from backend/rebuilt/jarvis-framework.toml): it is
     decided under file_read's own action `read_files_readonly`, the verdict is
     tier "auto", nothing is left pending, and the step records "auto". The
     same action name is what file_read and my_files use, so no gate action,
     no tier line and no patch were added - and a second check proves the
     lookup name really is "file_read".
  9. The tool's schema says only what the tool does: one file, inside a folder
     the owner listed, read-only - and it makes no claim to search, list or
     reach anywhere else.
 10. It writes NOTHING: every file's size and mtime is unchanged, no file is
     added or removed, and a binary file is refused in words instead of
     returned as mojibake.
 11. A LINE RANGE. `start_line` and `lines` (optional whole numbers) return
     numbered lines carrying their REAL file line numbers, the window, the real
     total and the byte/line caps - and the ruling's one footer, word for word,
     in `more` when (and only when) more follows. The footer never goes into
     `content`, the slice is bounded at 96 KiB even for an absurd `lines`, a
     file too big to count says the total is unknown instead of guessing, and a
     bad value is refused in one plain sentence. With neither argument the read
     is the whole file, exactly as before.
 12. A CREDENTIAL FILE is refused by NAME with one plain sentence, even inside
     a folder the owner listed: `.env` and `.env.*`, a private key, the
     `.pem`/`.key`/`.pfx`/`.p12`/`.kdbx`/`.jks` extensions, a `.git` folder in
     the path - while ordinary source files that merely contain the word
     (`key.py`, `keys.py`, `env.py`, `credentials_migration.py`) still read.
     The refusal never reads the file first (a binary `.env` is still refused
     as a credential file, not as binary).
 13. It writes NOTHING, proved again with SHA-256 as well as size and mtime_ns
     across a whole-file read AND a line-range read, with no file added or
     removed.

No source-text pins except the two the brief asks for (the schema's own words
and the action's name, both read from the objects that hold them). Every other
check drives the real modules over a real tree on disk. No network, no model,
no owner's files, no real card.

Run it on its own:   py -3 -B backend/test_project_read.py
The suites' runner stages a backend and sets JARVIS_BACKEND; this file works
both ways, and says which gate it read.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    """A check that could NOT run. Never counted as a pass (the repo's rule)."""
    SKIPPED.append(name)
    print(f"SKIPPED  {name} - {why}. It did NOT run, and it did NOT pass.")


HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
#: This suite tests THIS repository's copy. `JARVIS_BACKEND` (set by the
#: suites' runner, and by the owner's shell on his PC) names the live install;
#: a run against that would measure his folder, not this tree.
os.environ.pop("JARVIS_BACKEND", None)


#: A disposable folder the real boundary accepts. The OS temp folder is NOT one
#: on Windows: it lives under AppData, and Jarvis refuses everything under
#: AppData (keys, browser data), so this asks the boundary and falls back to a
#: folder beside the user's home - the same shape test_repomap.py uses.
def _scratch(prefix="jarvis-project-read-"):
    return Path(tempfile.mkdtemp(prefix=prefix))


def _usable(root: Path) -> bool:
    try:
        import jarvis_documents as D
        D.check_folder(str(root))
        return True
    except Exception:                                        # noqa: BLE001
        return False


TMP = _scratch()
if not _usable(TMP):
    shutil.rmtree(TMP, ignore_errors=True)
    TMP = Path(tempfile.mkdtemp(prefix=".jarvis-project-read-tests-",
                                dir=str(Path.home())))
CONF = TMP / "config"
CONF.mkdir(exist_ok=True)
# The settings folder, the projects store, the approval queue and the push topic
# are all redirected BEFORE anything imports: the gate opens its queue at
# import time, and no test here may touch the owner's real one.
os.environ["JARVIS_CONFIG_DIR"] = str(CONF)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONF)
os.environ["JARVIS_PROJECTS_DB"] = str(CONF / "projects.db")
os.environ["JARVIS_APPROVALS_DB"] = str(CONF / "approvals.db")
os.environ["JARVIS_NTFY_TOPIC"] = ""

import jarvis_agent as AGENT                                # noqa: E402
import jarvis_documents as DOCS                             # noqa: E402
import jarvis_projects as PROJ                              # noqa: E402
import jarvis_project_read as PR                            # noqa: E402
import jarvis_repomap as RM                                 # noqa: E402

DOCS._config_dir = lambda: CONF


def listed(*paths):
    """Put exactly these folders on "Folders Jarvis may look in"."""
    DOCS._save([{"path": os.path.realpath(str(p)), "added": 1.0} for p in paths])


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def build(root: Path) -> Path:
    """A small project: one Python package, a config file, a doc, an ignored
    folder, an ignored glob with one `!` exception, a build folder, a hidden
    folder, and a .gitignore that says all of it. Deterministic."""
    _write(root / "app" / "server.py", (
        '"""A tiny server."""\n'
        "import os\n"
        "\n"
        "def parse_route(text):\n"
        "    return text.split('/')\n"))
    _write(root / "app" / "router.py", (
        "from app.server import parse_route\n"
        "\n"
        "def install(handler):\n"
        "    return handler\n"))
    _write(root / "pyproject.toml", "[project]\nname = \"demo\"\n")
    _write(root / "README.md", "# Demo\n\nA tiny project.\n")
    _write(root / ".gitignore", "secret/\n*.gen.py\n!keep.gen.py\n")
    _write(root / "secret" / "hidden.py", "def secret_route():\n    return 1\n")
    _write(root / "gen" / "gone.gen.py", "def gone_thing():\n    return 1\n")
    _write(root / "gen" / "keep.gen.py", "def kept_thing():\n    return 2\n")
    _write(root / "build" / "out.py", "def built_thing():\n    return 3\n")
    _write(root / ".hidden" / "ghost.py", "def ghost_route():\n    return 0\n")
    return root


# ==========================================================================
#   1. inside a listed folder
# ==========================================================================

def t_1_one_file_inside_a_listed_folder_is_read():
    root = build(TMP / "tree-a")
    listed(root)
    out = PR.run_tool({"path": str(root), "file": "app/server.py"})
    check("1. a listed folder's .py file is read", out.get("ok") is True,
          json.dumps(out)[:400])
    text = str(out.get("content") or "")
    check("1. the words are the file's own, exactly",
          text == (root / "app" / "server.py").read_bytes().decode("utf-8"),
          text[:200])
    check("1. the answer names the path inside the folder",
          out.get("file") == "app/server.py", out.get("file"))
    check("1. ... and the REAL path it opened, for 'where this came from'",
          os.path.realpath(str(out.get("path") or ""))
          == os.path.realpath(str(root / "app" / "server.py")), out.get("path"))
    check("1. it is marked as outside text, like every other read",
          out.get("outside_text") is True, json.dumps(out)[:200])
    check("1. it says what kind of answer it is, for the model",
          "read only" in str(out.get("what") or ""), out.get("what"))
    check("1. back slashes are accepted for the same path, and it is reported "
          "with forward ones",
          PR.run_tool({"path": str(root), "file": "app\\router.py"}).get("file")
          == "app/router.py",
          PR.run_tool({"path": str(root), "file": "app\\router.py"}).get("file"))
    check("1. a config file and a document read the same way (any text kind)",
          PR.run_tool({"path": str(root), "file": "pyproject.toml"}).get("ok") is True
          and PR.run_tool({"path": str(root), "file": "README.md"}).get("ok") is True,
          "")
    check("1. the tool's own runner in jarvis_agent answers the same way",
          AGENT._run_project_read({"path": str(root), "file": "app/server.py"},
                                  None).get("ok") is True, "")
    check("1. nothing is written by a read",
          not (root / "app" / "server.py").with_suffix(".py.tmp").exists(), "")


# ==========================================================================
#   2. the boundary - outside the list
# ==========================================================================

def t_2_a_folder_off_the_list_is_refused_in_one_sentence():
    root = build(TMP / "tree-b")
    other = build(TMP / "tree-b-other")
    listed(root)                                   # a DIFFERENT folder is listed
    out = PR.run_tool({"path": str(other), "file": "app/server.py"})
    check("2. a folder that is not on the list is refused", out.get("ok") is False,
          json.dumps(out)[:300])
    said = str(out.get("error") or "")
    check("2. the refusal is the map's ONE plain sentence, word for word",
          said == RM.REFUSED, said)
    check("2. ... and it is one sentence that names what to do about it",
          said.count(".") == 1 and "\n" not in said
          and "Folders Jarvis may look in" in said and "Settings" in said, said)
    check("2. nothing was read from it: no text in the answer at all",
          "content" not in out, json.dumps(out)[:300])

    # A file INSIDE a listed folder whose own path names another folder's file
    # by climbing out is section 3; here: a file inside a SUBfolder is fine.
    sub = PR.run_tool({"path": str(root / "app"), "file": "router.py"})
    check("2. a subfolder of a listed folder can be its own starting point",
          sub.get("ok") is True and sub.get("file") == "router.py",
          json.dumps(sub)[:300])

    # No folders listed at all: the same sentence, not a crash.
    listed()
    out = PR.run_tool({"path": str(root), "file": "app/server.py"})
    check("2. with no folders listed at all, the answer is the same one sentence",
          out.get("ok") is False and out.get("error") == RM.REFUSED, str(out)[:300])
    listed(root)
    out = PR.run_tool({"path": str(TMP / "not-there-at-all"), "file": "x.py"})
    check("2. a folder that is not on this PC is refused in words, never a crash",
          out.get("ok") is False and isinstance(out.get("error"), str), str(out)[:300])


# ==========================================================================
#   3. the path is refused before anything is built
# ==========================================================================

def t_3_climbing_out_and_whole_paths_are_refused():
    root = build(TMP / "tree-c")
    listed(root)
    cases = [
        ("../tree-c/app/server.py", "it climbs out with .."),
        ("app/../../tree-c/app/server.py", "a .. in the middle is refused too"),
        ("..", "a bare .. is refused"),
    ]
    for rel, why in cases:
        out = PR.run_tool({"path": str(root), "file": rel})
        check(f"3. {why}", out.get("ok") is False
              and out.get("error") == PR.CLIMBS_OUT, f"{rel}: {out}")
    whole = ["C:\\Windows\\win.ini", "C:/Windows/win.ini", "/etc/passwd",
             "\\\\server\\share\\x.py"]
    for rel in whole:
        out = PR.run_tool({"path": str(root), "file": rel})
        check(f"3. a whole path is refused, not joined: {rel}", out.get("ok") is False
              and out.get("error") == PR.WHOLE_PATH, str(out)[:200])
    check("3. an empty file name says which file to name",
          PR.run_tool({"path": str(root), "file": "  "}).get("error") == PR.NEED_FILE, "")
    check("3. no folder at all says which folder to name",
          PR.run_tool({"file": "app/server.py"}).get("error") == PR.NEED_FOLDER, "")
    check("3. a NUL byte in the name is refused, not opened",
          PR.run_tool({"path": str(root),
                       "file": "app/serve\x00r.py"}).get("error") == PR.NEED_FILE, "")
    check("3. not one of those refusals raised", True, "")


# ==========================================================================
#   4. a link that leads outside
# ==========================================================================

def t_4_a_link_that_leads_outside_is_refused():
    root = build(TMP / "tree-d")
    listed(root)
    outside = TMP / "tree-d-outside-secret.py"
    outside.write_text("TOKEN = 'not-for-jarvis'\n", encoding="utf-8")
    link = root / "app" / "outside_link.py"
    try:
        os.symlink(str(outside), str(link))
    except (OSError, NotImplementedError) as exc:
        return skip("4. a link out of the folder is refused",
                    f"this PC would not make a symbolic link ({type(exc).__name__})")
    # `commonpath`, not a string prefix: tree-d-outside-secret.py STARTS with
    # "tree-d", and a prefix test would call the escape "inside".
    real = os.path.realpath(str(link))
    root_real = os.path.realpath(str(root))
    check("4. the link really exists and really points outside the folder",
          os.path.islink(str(link))
          and os.path.commonpath([real, root_real]) != root_real, real)
    out = PR.run_tool({"path": str(root), "file": "app/outside_link.py"})
    check("4. a link that leads outside is REFUSED", out.get("ok") is False,
          json.dumps(out)[:300])
    check("4. ... and not one word of the file it points at comes back",
          "TOKEN" not in json.dumps(out) and "not-for-jarvis" not in json.dumps(out),
          json.dumps(out)[:300])
    check("4. the refusal is the boundary's own sentence, not a stack trace",
          out.get("error") == PR.NOT_ALLOWED, str(out.get("error"))[:200])
    check("4. the map's own walk does not list that link either",
          all(shown != "app/outside_link.py"
              for _full, shown in RM._walk(str(root), clock=time.monotonic)[0]), "")


# ==========================================================================
#   5. the per-file cap is the map's own constant
# ==========================================================================

def t_5_the_cap_is_the_maps_and_a_long_file_says_so():
    check("5. the cap IS jarvis_repomap's own constant, not a second number",
          PR.MAX_FILE_BYTES == RM.MAX_FILE_BYTES and PR.MAX_FILE_BYTES > 0,
          f"{PR.MAX_FILE_BYTES} vs {RM.MAX_FILE_BYTES}")
    root = TMP / "tree-e"
    body = "#' a long line of notes\n" * ((RM.MAX_FILE_BYTES // 20) + 200)
    _write(root / "big.py", body)
    _write(root / "small.py", "def tiny_route():\n    return 1\n")
    listed(root)
    size = (root / "big.py").stat().st_size
    check("5. the test file really is over the cap", size > RM.MAX_FILE_BYTES,
          f"{size} bytes vs cap {RM.MAX_FILE_BYTES}")
    out = PR.run_tool({"path": str(root), "file": "big.py"})
    check("5. a file past the cap is still read, not refused", out.get("ok") is True,
          json.dumps(out)[:300])
    check("5. ... it is cut at the cap exactly",
          out.get("bytes") == RM.MAX_FILE_BYTES and out.get("cap") == RM.MAX_FILE_BYTES,
          f"bytes={out.get('bytes')} cap={out.get('cap')}")
    check("5. ... and it SAYS it was cut, so a cut file is never the whole file",
          out.get("truncated") is True, json.dumps({k: out.get(k) for k in
                                                    ("truncated", "bytes")}))
    small = PR.run_tool({"path": str(root), "file": "small.py"})
    check("5. a file under the cap says it is whole", small.get("truncated") is False, "")
    check("5. ... and a whole file that fits carries no footer at all",
          "more" not in small, json.dumps(small)[:300])
    check("5. the huge file is never loaded whole into the answer",
          len(str(out.get("content") or "")) <= RM.MAX_FILE_BYTES,
          len(str(out.get("content") or "")))
    # A cut WHOLE-FILE read also says which line range to ask for next, with
    # the real total counted from the file itself.
    complete = str(out.get("content") or "").count("\n")
    real_total = len((root / "big.py").read_text(encoding="utf-8").splitlines())
    check("5. a cut whole-file read carries the one line-range footer",
          out.get("more") == PR.MORE.format(first=1, last=complete, total=real_total),
          f"{out.get('more')!r} vs complete={complete} total={real_total}")
    check("5. ... counted from the real file, so the next range starts after the cut",
          complete > 0 and real_total > complete, f"{complete} of {real_total}")


# ==========================================================================
#   6. .gitignore and the build folders - the SAME walk the map uses
# ==========================================================================

def t_6_ignored_and_build_paths_are_refused_like_the_map():
    root = build(TMP / "tree-f")
    listed(root)
    for rel, why in [("secret/hidden.py", "an ignored FOLDER is refused"),
                     ("gen/gone.gen.py", "an ignored *.gen.py file is refused"),
                     ("gen/keep.gen.py", "a later ! rule puts a file back"),
                     ("build/out.py", "a build folder is refused even with no ignore rule"),
                     (".hidden/ghost.py", "a hidden folder is refused")]:
        out = PR.run_tool({"path": str(root), "file": rel})
        if rel == "gen/keep.gen.py":
            check(f"6. {why}", out.get("ok") is True, json.dumps(out)[:250])
        else:
            check(f"6. {why}", out.get("ok") is False, json.dumps(out)[:250])
    for rel in ("secret/hidden.py", "gen/gone.gen.py", "build/out.py"):
        out = PR.run_tool({"path": str(root), "file": rel})
        check(f"6. {rel} is refused with the one plain sentence about the rules",
              out.get("error") == PR.SKIPPED, str(out.get("error"))[:200])
    out = PR.run_tool({"path": str(root), "file": ".gitignore"})
    check("6. the .gitignore file itself is never offered as source",
          out.get("ok") is False, json.dumps(out)[:200])

    # THE SAME LIST THE MAP USES: every file the map's walk lists is readable
    # here, byte for byte, and nothing it does not list is.
    found, stopped = RM._walk(str(root), clock=time.monotonic)
    shown = sorted(s.replace("\\", "/") for _f, s in found)
    check("6. the map's own walk lists the files this test expects",
          "app/server.py" in shown and "gen/keep.gen.py" in shown
          and "gen/gone.gen.py" not in shown and "secret/hidden.py" not in shown
          and "build/out.py" not in shown, shown)
    bad = [(rel, PR.run_tool({"path": str(root), "file": rel}).get("ok"))
           for rel in shown]
    check("6. every file the map lists is readable, and every other path is not",
          all(ok is True for _rel, ok in bad)
          and PR.run_tool({"path": str(root), "file": "secret/hidden.py"}).get("ok")
          is False, str([b for b in bad if b[1] is not True])[:300])
    check("6. the walk did not stop early, so the list really is the whole folder",
          stopped == "", stopped)


# ==========================================================================
#   7. a project's own folder
# ==========================================================================

def t_7_a_project_id_reads_its_own_folder():
    root = build(TMP / "tree-g")
    listed(root)
    store = PROJ.Projects(path=CONF / "projects.db")
    made = store.create({"name": "Project read", "kind": "coding", "folder": str(root)},
                        here=True)
    out = PR.run_tool({"path": made["id"], "file": "app/router.py"})
    check("7. a project's id in `path` reads that project's folder",
          out.get("ok") is True and out.get("project", {}).get("id") == made["id"],
          json.dumps(out)[:300])
    out = PR.run_tool({"path": made["id"], "file": "app/router.py"})
    check("7. ... and the answer names the project it came from",
          out.get("project", {}).get("name") == "Project read", out.get("project"))
    ranged = PR.run_tool({"path": made["id"], "file": "app/server.py",
                          "start_line": 3, "lines": 2})
    check("7. a line range flows through a project id too (run_tool -> read_project "
          "-> read_folder)",
          ranged.get("ok") is True and ranged.get("start_line") == 3
          and ranged.get("end_line") == 4 and ranged.get("total_lines") == 5
          and ranged.get("project", {}).get("id") == made["id"],
          json.dumps({k: ranged.get(k) for k in
                      ("ok", "start_line", "end_line", "total_lines")}))
    check("7. an unknown project id answers its own plain sentence",
          PR.run_tool({"path": "0" * 32, "file": "app/router.py"}).get("error")
          == "There is no project with that id.", "")
    # A project whose folder was taken off the owner's list.
    listed(TMP / "tree-a")
    out = PR.run_tool({"path": made["id"], "file": "app/router.py"})
    check("7. a folder taken off the list stops being readable, even by project id",
          out.get("ok") is False and out.get("error") == RM.REFUSED, str(out)[:300])
    listed(root)
    store.create({"name": "Life one", "kind": "life"}, here=True)
    life = [p for p in store.list() if p.get("name") == "Life one"][0]
    out = PR.run_tool({"path": life["id"], "file": "app/router.py"})
    check("7. a project with no folder says so, in words",
          out.get("ok") is False and "no folder" in str(out.get("error")), str(out)[:250])


# ==========================================================================
#   8. NO CARD - the real gate, the real _one_call
# ==========================================================================

def _real_gate():
    """The REAL jarvis_gate from the published base, or (None, why-not).

    The gate is one of the files that live only on the owner's PC, so the
    repository keeps its state in `jarvis-backend/` (backend/_base.py). The
    tier table used is the SHIPPED one, read out of
    backend/rebuilt/jarvis-framework.toml - so the tier this proves is the tier
    an install gets, not a number typed here.
    """
    import _base
    base = _base.folder("jarvis_gate.py")
    if base is None:
        return None, "there is no jarvis-backend/jarvis_gate.py in this tree"
    try:
        import tomllib
    except Exception:                                        # noqa: BLE001
        return None, "this Python has no tomllib to read the shipped tier table"
    toml = REPO / "backend" / "rebuilt" / "jarvis-framework.toml"
    if not toml.is_file():
        return None, f"there is no {toml}"
    cfg = tomllib.loads(toml.read_text(encoding="utf-8"))
    tiers = dict((cfg.get("autonomy") or {}).get("tiers") or {})
    if not tiers:
        return None, "the shipped [autonomy.tiers] table could not be read"
    _base.put_on_path(base)
    import types
    fw = types.ModuleType("jarvis_framework")
    fw.CONFIG_DIR = CONF
    fw.LOG_DIR = CONF / "log"
    fw.audit_log = lambda *a, **k: None
    fw.load_framework = lambda: {
        "logging": {"redact_private_content_in_logs": True},
        "autonomy": {"unknown_action_tier": "ask", "tiers": tiers},
    }
    sys.modules["jarvis_framework"] = fw
    import jarvis_gate
    return jarvis_gate, ""


def one_call(args, checker):
    """Drive the REAL `_one_call` for this one tool and read what it returned."""
    call = {"id": "call-1", "function": {"name": "project_read",
                                        "arguments": json.dumps(args)}}
    convo, steps = [], []

    class Out:
        status = None
        gone = False

        def set_status(self, word):
            self.status = word

        def card_answered(self, verdict):
            pass

    AGENT._one_call(call, ["project_read"], convo, steps, checker,
                    lambda *_a, **_k: None, Out(), lambda *_a, **_k: None)
    result = json.loads(convo[-1]["content"]) if convo else {}
    return result, steps


def t_8_no_card_is_raised_and_no_gate_action_is_added():
    root = build(TMP / "tree-h")
    listed(root)
    tool = AGENT.TOOLS["project_read"]
    # The lookup name is file_read's, which is how this tool is decided under
    # read_files_readonly without adding a line anywhere in the gate.
    lookup = tool.gate_lookup_name({"path": str(root), "file": "app/server.py"})
    check("8. the tool is looked up under file_read's own name, not a new one",
          lookup == "file_read", lookup)
    check("8. file_read itself carries no gate_lookup_name (the action is its own)",
          AGENT.TOOLS["file_read"].gate_lookup_name is None, "")

    gate, why = _real_gate()
    if gate is None:
        return skip("8. no card is raised (the real gate, the real _one_call)", why)
    try:
        check("8. the real shipped tier for file_read's action is 'auto' (the tier "
              "an install gets)",
              gate.action_for_tool("file_read", {})[0] == "read_files_readonly"
              and gate.check("read_files_readonly", {}).tier == "auto", "")
    except Exception as exc:                                 # noqa: BLE001
        return skip("8. no card is raised (the real gate, the real _one_call)",
                    f"the real gate would not answer here ({type(exc).__name__})")
    before = gate.pending()
    result, steps = one_call({"path": str(root), "file": "app/server.py"},
                             AGENT._gate_check)
    check("8. the tool RAN under the real gate", result.get("ok") is True,
          json.dumps(result)[:300])
    check("8. the row it records is the gate's own 'auto' outcome - not 'approved'",
          steps and steps[-1].get("outcome") == "auto", str(steps[-1:]))
    check("8. NOTHING was left pending: no card was raised for it",
          gate.pending() == before == [], f"before={before} after={gate.pending()}")
    # ... and the same call with a checker that records the action proves WHICH
    # action a card would have been raised under, if the tier ever moved.
    seen = []

    def watching(action, detail, prompt):
        seen.append(action)
        return gate.check(action, detail, prompt=prompt)

    result, steps = one_call({"path": str(root), "file": "app/server.py"}, watching)
    check("8. exactly one gate call, under read_files_readonly - file_read's action",
          seen == ["read_files_readonly"], seen)
    check("8. ... and it still raised no card (that action ships 'auto')",
          gate.pending() == [], gate.pending())
    check("8. the plan the gate was handed names the file, and no file's words",
          result.get("ok") is True and "app/server.py" in
          str(AGENT._prepare_project_read({"path": str(root),
                                           "file": "app/server.py"})[1]), "")


# ==========================================================================
#   9. the schema says only what the tool does
# ==========================================================================

def t_9_the_schema_says_only_what_the_tool_does():
    tool = AGENT.TOOLS["project_read"]
    schema = tool.schema()["function"]
    desc = str(schema.get("description") or "")
    props = (schema.get("parameters") or {}).get("properties") or {}
    check("9. it says it reads ONE file", "one file" in desc.lower(), desc)
    check("9. it says where: a folder the owner listed, or one of their projects",
          "folder you listed" in desc and "project" in desc, desc)
    check("9. it says it is read-only, and that nothing is sent",
          "read-only" in desc.lower() and "nothing is sent" in desc.lower(), desc)
    check("9. the four fields: the folder (or id), the file, and the optional line "
          "range",
          sorted(props) == ["file", "lines", "path", "start_line"]
          and schema["parameters"].get("required") == ["path", "file"], sorted(props))
    check("9. start_line and lines are optional WHOLE numbers, and their defaults and "
          "the cap are said",
          props["start_line"].get("type") == "integer"
          and props["lines"].get("type") == "integer"
          and "default 1" in str(props["start_line"].get("description"))
          and "default 400" in str(props["lines"].get("description"))
          and "2000" in str(props["lines"].get("description")), props)
    check("9. the description says a line range exists and that 'more' answers it",
          "start_line" in desc and "more" in desc, desc)
    check("9. the `file` field says 'inside that folder', so it cannot be read as "
          "a whole path",
          "inside that folder" in str(props["file"].get("description")), props["file"])
    check("9. the `path` field says a project's id is allowed",
          "project's id" in str(props["path"].get("description")), props["path"])
    # It must make no claim it cannot keep. These are the false claims an
    # over-written description makes: that it searches, that it lists a folder,
    # that it reaches anywhere on the PC, that it changes anything.
    false_claims = ["search", "list the files", "anywhere on this pc",
                    "whole disk", "writes the file", "changes the file",
                    "deletes the file"]
    found = [w for w in false_claims if w in desc.lower()]
    check("9. it makes none of the claims it cannot keep", not found, found)
    check("9. the tool's own name is the one the schema advertises",
          schema.get("name") == "project_read", schema.get("name"))


# ==========================================================================
#   10. it writes nothing, and it refuses a binary
# ==========================================================================

def _snapshot(root: Path) -> dict:
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in sorted(filenames) + sorted(dirnames):
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full)
                out[os.path.relpath(full, root)] = (st.st_size, st.st_mtime_ns)
            except OSError:
                out[os.path.relpath(full, root)] = ("gone",)
    return out


def t_10_it_writes_nothing_and_refuses_a_binary():
    root = build(TMP / "tree-i")
    listed(root)
    before = _snapshot(root)
    PR.run_tool({"path": str(root), "file": "app/server.py"})
    PR.run_tool({"path": str(root), "file": "secret/hidden.py"})
    PR.run_tool({"path": str(root), "file": "../escape.py"})
    after = _snapshot(root)
    check("10. not one file changed size or mtime", before == after,
          str({k: (before.get(k), after.get(k)) for k in set(before) | set(after)
               if before.get(k) != after.get(k)})[:300])
    check("10. no file was added and none removed", sorted(before) == sorted(after), "")
    blob = root / "app" / "logo.bin"
    blob.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    out = PR.run_tool({"path": str(root), "file": "app/logo.bin"})
    check("10. a binary file is refused in words, not returned as mojibake",
          out.get("ok") is False and out.get("error") == PR.BINARY, str(out)[:250])
    out = PR.run_tool({"path": str(root), "file": "app/logo.bin",
                       "start_line": 1, "lines": 2})
    check("10. ... and a LINE RANGE is refused too, not numbered as if it were words",
          out.get("ok") is False and out.get("error") == PR.BINARY, str(out)[:250])
    check("10. a folder is refused as a folder, not as a missing file",
          PR.run_tool({"path": str(root), "file": "app"}).get("error") == PR.IS_FOLDER, "")
    out = PR.run_tool({"path": str(root), "file": "app/nothing-here.py"})
    check("10. a file that is really not there says exactly that",
          out.get("error") == PR.NO_FILE.format(file="app/nothing-here.py"), str(out)[:200])
    check("10. the module keeps nothing between calls (no cache to reset)",
          PR._reset_for_tests() is None, "")
    check("10. the two copies of the new module are byte-equal",
          (REPO / "backend" / "jarvis_project_read.py").read_bytes().replace(
              b"\r\n", b"\n")
          == (REPO / "jarvis-backend" / "jarvis_project_read.py").read_bytes().replace(
              b"\r\n", b"\n"), "")


# ==========================================================================
#   11. a line range - numbered lines, the real total, and ONE footer
# ==========================================================================

def t_11_a_line_range_returns_numbered_lines_and_one_footer():
    root = TMP / "tree-j"
    root.mkdir(exist_ok=True)
    short = "".join(f"value_{i} = {i}\n" for i in range(1, 61))
    _write(root / "lines.py", short)
    _write(root / "long.py", "".join(f"row_{i} = {i}\n" for i in range(1, 501)))
    _write(root / "huge.py", "".join(f"x{i}\n" for i in range(1, 2501)))
    _write(root / "fat.py", "".join("z" * 200 + "\n" for _ in range(600)))
    _write(root / "unknown.py", "".join(f"u{i} = {i}\n" for i in range(1, 150001)))
    listed(root)
    total = len(short.splitlines())
    check("11. the test file's own line count is the one the tool must report",
          total == 60, total)

    out = PR.run_tool({"path": str(root), "file": "lines.py",
                       "start_line": 11, "lines": 5})
    check("11. a line range is read", out.get("ok") is True, json.dumps(out)[:300])
    content = str(out.get("content") or "")
    check("11. the lines are numbered with their REAL file line numbers",
          content.split("\n") == [f"11: value_11 = 11", f"12: value_12 = 12",
                                  f"13: value_13 = 13", f"14: value_14 = 14",
                                  f"15: value_15 = 15"], content[:300])
    check("11. the answer names the window it showed and the real total",
          (out.get("start_line"), out.get("end_line"), out.get("total_lines"))
          == (11, 15, total),
          str((out.get("start_line"), out.get("end_line"), out.get("total_lines"))))
    check("11. `more` is the ruling's sentence, word for word",
          out.get("more") == PR.MORE.format(first=11, last=15, total=total),
          str(out.get("more")))
    check("11. ... and NOT one word of it is inside `content` (the model reads that "
          "as source code)",
          "Showing lines" not in content and "request the next" not in content,
          content[-120:])
    check("11. a cut range says `truncated: true`", out.get("truncated") is True,
          out.get("truncated"))
    check("11. the answer carries the byte cap and the line cap",
          out.get("cap") == PR.MAX_FILE_BYTES and out.get("line_cap") == PR.MAX_LINES,
          str((out.get("cap"), out.get("line_cap"))))

    # With NEITHER argument the read is the whole file, exactly as before a
    # range existed: no range keys, and no footer when the whole file fits.
    whole = PR.run_tool({"path": str(root), "file": "lines.py"})
    check("11. no range asked is still the whole-file read, with no range keys",
          whole.get("content") == (root / "lines.py").read_bytes().decode("utf-8")
          and not {"start_line", "end_line", "total_lines", "more"} & set(whole),
          json.dumps(sorted(whole))[:300])
    check("11. ... and it still says it was not cut", whole.get("truncated") is False, "")

    # A range that reaches the end has nothing more: no footer at all.
    last = PR.run_tool({"path": str(root), "file": "lines.py",
                        "start_line": 41, "lines": 400})
    body = str(last.get("content") or "").split("\n")
    check("11. a range that reaches the end of the file has NO footer",
          last.get("ok") is True and "more" not in last
          and last.get("truncated") is False, json.dumps(last)[:300])
    check("11. ... and it ends on the file's real last line, numbered",
          last.get("end_line") == total and body[-1] == "60: value_60 = 60",
          f"{last.get('end_line')} {body[-1:]}")

    # `lines` alone starts at line 1; `start_line` alone shows the default 400.
    only_count = PR.run_tool({"path": str(root), "file": "lines.py", "lines": 3})
    check("11. `lines` alone starts at line 1",
          only_count.get("start_line") == 1
          and str(only_count.get("content") or "").split("\n") ==
          ["1: value_1 = 1", "2: value_2 = 2", "3: value_3 = 3"],
          str(only_count.get("content"))[:200])
    check("11. ... and the footer counts from 1 too",
          only_count.get("more") == PR.MORE.format(first=1, last=3, total=total),
          str(only_count.get("more")))
    only_start = PR.run_tool({"path": str(root), "file": "long.py",
                              "start_line": 30})
    check("11. `start_line` alone shows the default 400 lines",
          only_start.get("ok") is True
          and len(str(only_start.get("content") or "").split("\n")) == PR.DEFAULT_LINES
          == 400 and only_start.get("end_line") == 429,
          f"{len(str(only_start.get('content') or '').split(chr(10)))} "
          f"{only_start.get('end_line')}")

    # The hard cap: asking for 100,000 lines cannot return more than 2,000.
    capped = PR.run_tool({"path": str(root), "file": "huge.py", "lines": 100000})
    check("11. an absurd `lines` is capped at the hard 2,000, not obeyed",
          capped.get("ok") is True and capped.get("line_cap") == 2000
          and len(str(capped.get("content") or "").split("\n")) == 2000
          and capped.get("end_line") == 2000
          and capped.get("total_lines") == 2500,
          f"{capped.get('end_line')} / {capped.get('total_lines')}")
    check("11. ... and it says which range is next",
          capped.get("more") == PR.MORE.format(first=1, last=2000, total=2500),
          str(capped.get("more")))

    # The byte cap bounds the answer even when the lines are enormous.
    fat = PR.run_tool({"path": str(root), "file": "fat.py", "lines": 2000})
    fat_text = str(fat.get("content") or "")
    check("11. the 96 KiB answer cap bounds an absurd `lines` before 2,000 lines",
          fat.get("ok") is True and len(fat_text) <= PR.MAX_SLICE_BYTES
          and fat.get("bytes") <= PR.MAX_SLICE_BYTES
          and fat.get("end_line") < fat.get("total_lines"),
          f"chars={len(fat_text)} bytes={fat.get('bytes')} "
          f"end={fat.get('end_line')} of {fat.get('total_lines')}")
    check("11. ... and the footer says WHY it stopped, in the same shape",
          fat.get("more") == PR.MORE_BYTES.format(first=1, last=fat.get("end_line"),
                                                  total=600, kib=96)
          and "96 KiB" in str(fat.get("more")), str(fat.get("more")))

    # A bad value is refused in ONE plain sentence - never an exception.
    bad_values = [{"start_line": 0}, {"start_line": -1}, {"lines": 0},
                  {"lines": -5}, {"start_line": "11"}, {"lines": "5"},
                  {"start_line": 1.5}, {"lines": 1.5}, {"start_line": True},
                  {"lines": True}, {"start_line": 1, "lines": 0}]
    for asked in bad_values:
        try:
            got = PR.run_tool({"path": str(root), "file": "lines.py", **asked})
        except Exception as exc:                             # noqa: BLE001
            got = {"raised": type(exc).__name__}
        check(f"11. a bad range value is refused in one sentence, not raised: {asked}",
              got.get("ok") is False and got.get("available") is True
              and got.get("error") == PR.BAD_RANGE.format(cap=PR.MAX_LINES),
              str(got)[:250])

    # A file too big to count: the exact total is unknown, and it says so.
    saved = PR.MAX_COUNT_BYTES
    PR.MAX_COUNT_BYTES = 1024 * 1024
    try:
        unknown = PR.run_tool({"path": str(root), "file": "unknown.py",
                               "start_line": 5, "lines": 2})
    finally:
        PR.MAX_COUNT_BYTES = saved
    check("11. a file too big to count says the exact total is unknown, and a range "
          "can still be asked for",
          unknown.get("ok") is True and unknown.get("total_lines") is None
          and unknown.get("truncated") is True
          and unknown.get("more") == PR.MORE_UNKNOWN.format(first=5, last=6, mib=1),
          str(unknown.get("more")))
    check("11. ... and the lines it did ask for are the real ones",
          str(unknown.get("content") or "").split("\n") ==
          ["5: u5 = 5", "6: u6 = 6"], str(unknown.get("content"))[:200])


# ==========================================================================
#   12. a credential file is refused by NAME - and ordinary source still reads
# ==========================================================================

def t_12_a_credential_file_is_refused_by_name():
    root = TMP / "tree-k"
    root.mkdir(exist_ok=True)
    refused = [".env", ".env.local", ".netrc", ".git-credentials", ".npmrc",
               "credentials", "credentials.json",
               "id_rsa", "id_rsa.pub", "id_ed25519", "id_ecdsa", "id_dsa",
               "secrets.pem", "server.key", "cert.pfx", "cert.p12",
               "vault.kdbx", "store.jks",
               "pkg/.git/config", "pkg/.git/HEAD",
               # The owner's 2026-11-10 00:05 PT ruling (Q3) extended the list:
               # these were NOT refused before this wave.
               "secrets.json", ".envrc", ".htpasswd", ".pypirc", "api_keys.py",
               "refresh.token", "aws_credentials.json",
               "gcp-credentials-old.json", "pkg/.git/credentials"]
    allowed = ["key.py", "keys.py", "env.py", "credentials_migration.py",
               "notes.txt", "app/server.py",
               # ... and the near misses the ruling must NOT swallow.
               "tokens.md", "notes.token.md", "credentials_notes.md"]
    for rel in refused + allowed:
        _write(root / rel, "SECRET = 'this must never come back'\n")
    _write(root / ".notes.txt", "ordinary words, hidden by its name only\n")
    listed(root)

    for rel in refused:
        out = PR.run_tool({"path": str(root), "file": rel})
        check(f"12. {rel} is refused as a credential file",
              out.get("ok") is False and out.get("available") is True
              and out.get("error") == PR.CREDENTIAL, str(out)[:250])
        check(f"12. ... and not one word of it comes back: {rel}",
              "must never come back" not in json.dumps(out), str(out)[:250])
    for rel in allowed:
        out = PR.run_tool({"path": str(root), "file": rel})
        check(f"12. {rel} still reads like any ordinary source file",
              out.get("ok") is True and "SECRET" in str(out.get("content") or ""),
              str(out)[:250])

    # THE PREDICATE ITSELF, pinned on both sides - this is what stops the rule
    # from drifting into "any name containing the word".
    yes = [".env", ".ENV", ".env.production", ".env.local", ".netrc",
           ".git-credentials", ".npmrc", "credentials", "credentials.json",
           "CREDENTIALS.JSON", "id_rsa", "id_rsa.pub", "id_ed25519", "id_ecdsa",
           "id_dsa", "id_dsa.pub", "secrets.pem", "x.key", "x.pfx", "x.p12",
           "x.kdbx", "x.jks", "pkg/.git/config", "a/b/.git/HEAD",
           # The 2026-11-10 Q3 additions, each in the shape the ruling names.
           "secrets.json", ".envrc", ".htpasswd", ".pypirc", "api_keys.py",
           "x.token", "X.TOKEN", "aws_credentials.json",
           "GCP-CREDENTIALS-OLD.JSON", "pkg/.git/credentials"]
    no = ["key.py", "keys.py", "env.py", "credentials_migration.py", "notes.txt",
          "my.env", "server.pem.txt", "credentials.md", "my.git/config",
          "key", "keys.json",
          # The near misses the extended list must leave readable.
          "tokens.md", "notes.token.md", "secrets.json.md", "api_keys.py.txt"]
    check("12. the checker's own predicate: every credential NAME is refused",
          all(PR._credential(n) for n in yes),
          [n for n in yes if not PR._credential(n)])
    check("12. ... and every ordinary source name is NOT refused",
          not any(PR._credential(n) for n in no),
          [n for n in no if PR._credential(n)])
    check("12. `.git` as a FOLDER is refused anywhere in the path, not as a name",
          PR._credential("a/.git/config") and PR._credential("a/b/.git/HEAD")
          and not PR._credential("a/.git"), "")
    # THE PUBLIC, ONE-ARGUMENT NAME (2026-11-10 Q3): every other module that
    # reads or hands on a file asks THIS, and it is the public form of the ONE
    # helper's list - one list, never a copy that can drift.
    check("12. `is_credential_path` is the PUBLIC one-argument form of the ONE helper",
          callable(getattr(PR, "is_credential_path", None))
          and getattr(PR, "credential_path", None) is PR._credential, None)
    check("12. ... it takes a path or a bare filename and answers True/False",
          all(PR.is_credential_path(n) is True for n in yes)
          and not any(PR.is_credential_path(n) is True for n in no), None)

    # It never reads the file first: a credential file full of NUL bytes is
    # refused as a CREDENTIAL FILE, not as a binary one.
    (root / ".env").write_bytes(b"BINARY\x00\x00SECRET")
    out = PR.run_tool({"path": str(root), "file": ".env"})
    check("12. a binary .env is refused as a credential file - it was never opened",
          out.get("ok") is False and out.get("error") == PR.CREDENTIAL, str(out)[:200])
    # ... and the same for a name the boundary's own list does not know, so the
    # NEW check is the one that refuses it, after the walk and before the open.
    (root / "id_dsa").write_bytes(b"BINARY\x00\x00SECRET")
    out = PR.run_tool({"path": str(root), "file": "id_dsa"})
    check("12. a binary id_dsa is refused as a credential file - the new check ran "
          "after the walk, before the open",
          out.get("ok") is False and out.get("error") == PR.CREDENTIAL, str(out)[:200])

    # The new sentence must not swallow the boundary's own refusals.
    out = PR.run_tool({"path": str(root), "file": ".notes.txt"})
    check("12. a hidden file that is NOT a credential file keeps the boundary's "
          "sentence, not the credential one",
          out.get("ok") is False and out.get("error") == PR.NOT_ALLOWED, str(out)[:200])
    out = PR.run_tool({"path": str(root), "file": "../tree-k/key.py"})
    check("12. climbing out is still the boundary's sentence, before any name check",
          out.get("ok") is False and out.get("error") == PR.CLIMBS_OUT, str(out)[:200])


# ==========================================================================
#   13. zero mutation - SHA-256 across a whole read AND a range read
# ==========================================================================

def _hash_snapshot(root: Path):
    """Every file's relative path, size, mtime_ns and SHA-256, and every folder
    - read straight off the disk, so 'nothing changed' is measured, not assumed."""
    files, dirs = {}, set()
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames:
            dirs.add(os.path.relpath(os.path.join(dirpath, name), root))
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            st = os.stat(full)
            with open(full, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
            files[rel] = (st.st_size, st.st_mtime_ns, digest)
    return files, dirs


def t_13_a_whole_read_and_a_range_read_change_nothing():
    root = build(TMP / "tree-l")
    _write(root / "app" / "many.py",
           "".join(f"line_{i} = {i}\n" for i in range(1, 301)))
    listed(root)
    before_files, before_dirs = _hash_snapshot(root)
    whole = PR.run_tool({"path": str(root), "file": "app/server.py"})
    ranged = PR.run_tool({"path": str(root), "file": "app/many.py",
                          "start_line": 51, "lines": 25})
    after_files, after_dirs = _hash_snapshot(root)
    check("13. the whole-file read and the line-range read both came back",
          whole.get("ok") is True and ranged.get("ok") is True
          and len(str(ranged.get("content") or "").split("\n")) == 25,
          f"{whole.get('ok')} {ranged.get('ok')}")
    changed = {k: (before_files.get(k), after_files.get(k))
               for k in set(before_files) | set(after_files)
               if before_files.get(k) != after_files.get(k)}
    check("13. every file's path, size, mtime_ns and SHA-256 is unchanged",
          before_files == after_files, str(changed)[:500])
    check("13. no file was added and none removed",
          sorted(before_files) == sorted(after_files),
          str(sorted(set(after_files) - set(before_files)))[:300])
    check("13. no folder was added and none removed",
          before_dirs == after_dirs, str(before_dirs ^ after_dirs)[:300])
    check("13. the range really was what was asked for (a check that can fail)",
          str(ranged.get("content") or "").split("\n")[0] == "51: line_51 = 51"
          and ranged.get("end_line") == 75, str(ranged.get("content"))[:120])


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
