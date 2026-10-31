"""test_reseal_live_install.py - proves the reseal tool behaves safely, on synthetic PCs.

    python3 test_reseal_live_install.py

WHAT THIS SUITE HOLDS

`tools/reseal_live_install.py` writes into the owner's LIVE backend folder and into
the installer's own record (`_jarvis-state.json`), so every refusal matters more than
the happy path. Gemini's Q3 ruling (2026-10-30) asked for it to be proved on
synthetic live folders, and this is that proof:

  1. a DRY RUN reports every shipped file as byte-equal / differs / absent, names the
     record rows it would re-hash, and writes NOTHING - not to the live folder, not a
     backup, not the record;
  2. `--apply` copies the repository's bytes EXACTLY, keeps the old bytes in a
     `<name>.before-reseal-<stamp>` sibling, purges stale `__pycache__` bytecode,
     compiles the file that is now in the folder, and re-hashes ONLY the record row of
     the file it replaced - the installer's own fields (`written`, `patches`,
     `patchList`) and every row it did not touch stay exactly as they were;
  3. a stale record row is corrected only for a file the tool owns. A row for a file
     this repository does not ship (the five patched base files) is never rewritten:
     it is listed with both hashes, the run exits 1, and the preflight projection says
     which rows therefore stay red;
  4. a shipped entry that flattens onto a name already taken, a record row that names
     a path outside the folder, and a target that is a directory are all REFUSED with
     nothing written; a record row for a file that is absent and not shipped is
     reported, not invented, and no file is created for it;
  5. a file this repository does not ship is never touched - not copied, not backed
     up, not named in the plan;
  6. a second `--apply` is a no-op: the tree is byte-identical, no backup is made, the
     record is not rewritten;
  7. a deliberately corrupted live file (invalid Python) is still replaced by the
     repository's bytes and the result compiles; and a repository copy that does NOT
     compile stops the run before anything is written, with the live folder unchanged;
  8. THE PREFLIGHT ROW SET IMPROVES, measured two ways: the patch projection (through
     `backend/selftest.py`'s own `patch_states`, with its own `read` seam) counts the
     rows that flip and names the ones that cannot; and on a synthetic install holding
     every shipped file, `backend/selftest.py`'s real `pf_modules` goes from three
     FAIL rows to one - the one file the repository does not ship - with the tool's own
     mirror of that check agreeing with the real number on both ends;
  9. the CLI: `--apply --dry-run` is refused, an empty `--ref` is refused, a folder
     with no `jarvis_hud.py` is refused, and a real two-commit git repository drives
     the whole thing through `git show` with no seam at all - dry run, apply, and an
     apply that changes nothing.

A check that could not run is SAID OUT LOUD as a skip and is never counted as a pass
(the project's BLOCKED-is-never-a-pass rule). Nothing here reads the real live
folder: every path is a temporary one. The only real repository files read are
`scripts/apply-patches.ps1`, `backend/<shipped entry>` and the published files they
describe, used as fixtures - never as a reference any live folder is compared to.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TOOL = REPO / "tools" / "reseal_live_install.py"

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check that could not run here. Counted on its own line, never as a pass."""
    SKIPPED.append(why)
    print(f"skip     {why}")


def load_tool():
    spec = importlib.util.spec_from_file_location("reseal_tool", TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["reseal_tool"] = mod      # dataclasses looks the module up by name
    spec.loader.exec_module(mod)
    return mod


T = load_tool()
T.deploy.git_rev_parse = lambda repo, revision: "0" * 40   # fixtures have no git


# ---------------------------------------------------------------------------
#   Fixtures: a fixture repository whose backend/ holds the bytes, and a PC
# ---------------------------------------------------------------------------

def sha(data):
    return hashlib.sha256(bytes(data).replace(b"\r\n", b"\n")).hexdigest()


def make_repo(shipped, blobs):
    """(the fixture repository, its `show(repo, ref, path)` seam)."""
    root = Path(tempfile.mkdtemp(prefix="reseal-repo-"))
    (root / "scripts").mkdir(parents=True)
    lines = ["$SHIPPED = @("]
    for entry in shipped:
        lines.append(f"    '{entry}'")
    lines += [")", "", "$PATCHES = @(", "    'test.patch'", ")", ""]
    text = "\n".join(lines)
    (root / "scripts" / "apply-patches.ps1").write_text(text, encoding="utf-8")
    files = {"scripts/apply-patches.ps1": text.encode("utf-8")}
    for rel, data in blobs.items():
        path = root / "backend" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files[f"backend/{rel}"] = data

    def show(repo, ref, path):
        return files[path]

    return root, show


def make_live(files, record=None):
    root = Path(tempfile.mkdtemp(prefix="reseal-live-"))
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    if record is not None:
        write_record(root, record)
    return root


def write_record(live, doc):
    (Path(live) / "_jarvis-state.json").write_text(json.dumps(doc, indent=2),
                                                   encoding="utf-8")


def a_record(rows, written="2026-10-01T09:00:00"):
    return {"schema": "jarvis-updater-manifest/1", "written": written,
            "backend": "C:/a/PC/Desktop program", "run": "baseline",
            "patches": [{"Patch": "test.patch", "Sha256": "aa" * 32,
                         "Verdict": "applied"}],
            "patchList": ["test.patch"], "unmatched": [], "leftOut": [],
            "notInstalled": [], "summary": "", "files": rows}


def a_row(data, patch="", verified=False):
    return {"sha256": sha(data) if data is not None else "",
            "patch": patch, "verified": verified}


def tree(root):
    root = Path(root)
    return {str(p.relative_to(root)).replace("\\", "/"): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


def run_tool(repo, live, **kw):
    lines = []
    code = T.run_reseal(repo, live, out=lines.append, **kw)
    return code, "\n".join(lines)


HUD = b"# the live HUD, as this PC runs it\n"
OLD_COMPUTE = b"def compute():\n    return 0\n"
BLOBS = {
    "rebuilt/jarvis_compute.py": b"def compute():\n    return 1\n",
    "jarvis_wiki.py": b"def wiki():\n    return 2\n",
    "static/theme.css": b"body { color: red }\n",
}
SHIPPED = ["rebuilt/jarvis_compute.py", "jarvis_wiki.py", "static/theme.css"]


def a_small_pc(record=None):
    """A fixture PC: one shipped file out of date, one up to date, one absent."""
    repo, show = make_repo(SHIPPED, BLOBS)
    live = make_live({"jarvis_hud.py": HUD,
                      "jarvis_compute.py": OLD_COMPUTE,
                      "jarvis_wiki.py": BLOBS["jarvis_wiki.py"]},
                     record if record is not None else a_record({
                         "jarvis_compute.py": a_row(OLD_COMPUTE),
                         "jarvis_wiki.py": a_row(BLOBS["jarvis_wiki.py"]),
                     }))
    return repo, live, show


# ---------------------------------------------------------------------------
#   1. The dry run
# ---------------------------------------------------------------------------

def t_dry_run_reports_each_file_and_writes_nothing():
    repo, live, show = a_small_pc()
    before = tree(live)
    code, text = run_tool(repo, live, ref="HEAD", show=show)
    check("dry run: the out-of-date file is reported as differing, by name",
          "differs (the repository's bytes will replace them): 1: jarvis_compute.py"
          in text, text)
    check("dry run: the missing file is reported as absent, by name",
          "absent (the repository ships them; nothing is there): 1: theme.css" in text,
          text)
    check("dry run: the file that already matches is counted, not listed",
          "unchanged: 1" in text, text)
    check("dry run: the record row it would re-hash is named",
          "to re-hash (the repository proves those bytes): 1: jarvis_compute.py" in text,
          text)
    check("dry run: it says nothing was written", "DRY RUN - nothing was written" in text,
          text)
    check("dry run: it asks for --apply rather than doing it",
          "then add --apply" in text, text)
    check("dry run: the live folder is byte-identical afterwards", tree(live) == before,
          f"{sorted(set(tree(live)) ^ set(before))}")
    check("dry run: no backup was made",
          not any(".before-reseal-" in name for name in tree(live)), sorted(tree(live)))
    check("dry run: exits 0 when every row it needs is provable", code == 0, code)


# ---------------------------------------------------------------------------
#   2. Apply
# ---------------------------------------------------------------------------

def t_apply_copies_the_repository_bytes_and_keeps_a_backup():
    repo, live, show = a_small_pc()
    (live / "__pycache__").mkdir()
    (live / "__pycache__" / "jarvis_wiki.cpython-312.pyc").write_bytes(b"stale bytecode")
    old_record = (live / "_jarvis-state.json").read_bytes()
    code, text = run_tool(repo, live, ref="HEAD", show=show, apply=True, stamp="T1")
    check("apply: the out-of-date file now holds the repository's bytes, exactly",
          (live / "jarvis_compute.py").read_bytes() == BLOBS["rebuilt/jarvis_compute.py"],
          (live / "jarvis_compute.py").read_bytes())
    check("apply: the absent file is written with the repository's bytes",
          (live / "theme.css").read_bytes() == BLOBS["static/theme.css"])
    check("apply: the file that already matched is left byte-identical",
          (live / "jarvis_wiki.py").read_bytes() == BLOBS["jarvis_wiki.py"])
    check("apply: the replaced file's old bytes are kept in a .before-reseal-<stamp> "
          "sibling",
          (live / "jarvis_compute.py.before-reseal-T1").read_bytes() == OLD_COMPUTE)
    check("apply: a file that was not replaced gets no backup",
          not (live / "jarvis_wiki.py.before-reseal-T1").exists())
    doc = json.loads((live / "_jarvis-state.json").read_text(encoding="utf-8"))
    check("apply: the record row of the file it replaced holds the repository's hash",
          doc["files"]["jarvis_compute.py"]["sha256"]
          == sha(BLOBS["rebuilt/jarvis_compute.py"]), doc["files"]["jarvis_compute.py"])
    check("apply: the row of a file it did not touch keeps its hash",
          doc["files"]["jarvis_wiki.py"]["sha256"] == sha(BLOBS["jarvis_wiki.py"]))
    check("apply: the installer's own fields are kept exactly",
          doc["written"] == "2026-10-01T09:00:00" and doc["patchList"] == ["test.patch"]
          and doc["patches"][0]["Patch"] == "test.patch", doc.get("patches"))
    check("apply: the old record is kept beside the new one",
          (live / "_jarvis-state.json.before-reseal-T1").read_bytes() == old_record)
    check("apply: the record says which tool wrote the row and for which commit",
          doc["resealed"]["tool"] == "tools/reseal_live_install.py"
          and doc["resealed"]["rows"] == ["jarvis_compute.py"], doc.get("resealed"))
    check("apply: stale bytecode is purged",
          not (live / "__pycache__" / "jarvis_wiki.cpython-312.pyc").exists())
    check("apply: the file that is now in the folder compiles",
          "COMPILE : py_compile OK for every Python file written" in text, text)
    check("apply: it proves convergence with the same comparison it planned with",
          "VERIFY  : 0 of 3 shipped file(s) still differ" in text, text)
    check("apply: exits 0 when every row it needs was provable", code == 0, code)


# ---------------------------------------------------------------------------
#   3. What the record may and may not say
# ---------------------------------------------------------------------------

def t_a_stale_row_is_corrected_only_for_a_file_the_tool_owns():
    old_hud = b"# the live HUD, before the patch stack touched it\n"
    new_hud = b"# the live HUD, patched on the PC after the record was written\n"
    repo, show = make_repo(SHIPPED, BLOBS)
    live = make_live({"jarvis_hud.py": new_hud,
                      "jarvis_compute.py": OLD_COMPUTE,
                      "jarvis_wiki.py": BLOBS["jarvis_wiki.py"]},
                     a_record({"jarvis_hud.py": a_row(old_hud, patch="hud.patch",
                                                      verified=True),
                               "jarvis_compute.py": a_row(OLD_COMPUTE),
                               "jarvis_wiki.py": a_row(BLOBS["jarvis_wiki.py"])}))
    code, text = run_tool(repo, live, ref="HEAD", show=show, apply=True, stamp="T2")
    doc = json.loads((live / "_jarvis-state.json").read_text(encoding="utf-8"))
    check("own rows: the shipped file's row is re-hashed to the repository's bytes",
          doc["files"]["jarvis_compute.py"]["sha256"]
          == sha(BLOBS["rebuilt/jarvis_compute.py"]))
    check("own rows: the patched base file's row is NOT rewritten",
          doc["files"]["jarvis_hud.py"]["sha256"] == sha(old_hud),
          doc["files"]["jarvis_hud.py"])
    check("own rows: the patched base file keeps its patch name and verified flag",
          doc["files"]["jarvis_hud.py"]["patch"] == "hud.patch"
          and doc["files"]["jarvis_hud.py"]["verified"] is True)
    check("own rows: no row is invented for a file the record never named",
          sorted(doc["files"]) == ["jarvis_compute.py", "jarvis_hud.py",
                                   "jarvis_wiki.py"], sorted(doc["files"]))
    check("own rows: the unprovable row is printed with both hashes",
          f"jarvis_hud.py: record {sha(old_hud)[:12]}, folder {sha(new_hud)[:12]}" in text,
          text)
    check("own rows: the run says the patched files stay red and why",
          "the patch stack" in text and "unprovable" in text, text)
    check("own rows: the module projection counts one row fixed and one left",
          "modules : 2 failing row(s) now, 1 after the reseal" in text, text)
    check("own rows: exits 1 because a row it will not invent remains", code == 1, code)


def t_a_record_this_tool_does_not_understand_is_left_alone():
    repo, show = make_repo(SHIPPED, BLOBS)
    live = make_live({"jarvis_hud.py": HUD,
                      "jarvis_compute.py": OLD_COMPUTE,
                      "jarvis_wiki.py": BLOBS["jarvis_wiki.py"]})
    write_record(live, {"schema": "something-else/9", "files": {
        "jarvis_compute.py": a_row(OLD_COMPUTE)}})
    before = (live / "_jarvis-state.json").read_bytes()
    code, text = run_tool(repo, live, ref="HEAD", show=show, apply=True, stamp="T3")
    check("unknown record: it says the record was not changed",
          "no row in it was changed" in text, text)
    check("unknown record: the record is byte-identical afterwards",
          (live / "_jarvis-state.json").read_bytes() == before)
    check("unknown record: the file sync still happened, because that part is provable",
          (live / "jarvis_compute.py").read_bytes() == BLOBS["rebuilt/jarvis_compute.py"])
    check("unknown record: exits 0 - nothing is left that it refuses to prove", code == 0,
          code)

    live2 = make_live({"jarvis_hud.py": HUD, "jarvis_compute.py": OLD_COMPUTE,
                       "jarvis_wiki.py": BLOBS["jarvis_wiki.py"]})
    write_record(live2, {"schema": "jarvis-updater-manifest/1",
                         "files": {"jarvis_compute.py": "not-an-object"}})
    before2 = (live2 / "_jarvis-state.json").read_bytes()
    code2, text2 = run_tool(repo, live2, ref="HEAD", show=show, apply=True, stamp="T3b")
    check("a record row that is not an object: it is reported, not reinterpreted",
          "row(s) that are not objects" in text2, text2)
    check("a record row that is not an object: the record is byte-identical",
          (live2 / "_jarvis-state.json").read_bytes() == before2)


def t_rebaselining_the_unprovable_rows_is_off_until_asked_for():
    old_hud = b"# the live HUD, before the record was written\n"
    new_hud = b"# the live HUD, repaired on the PC afterwards\n"
    repo, show = make_repo(SHIPPED, BLOBS)
    live = make_live({"jarvis_hud.py": new_hud,
                      "jarvis_compute.py": OLD_COMPUTE,
                      "jarvis_wiki.py": BLOBS["jarvis_wiki.py"]},
                     a_record({"jarvis_hud.py": a_row(old_hud, patch="hud.patch",
                                                      verified=True)}))
    before = (live / "_jarvis-state.json").read_bytes()
    code, text = run_tool(repo, live, ref="HEAD", show=show)
    check("rebaseline: a dry run says the row is left as it is",
          "0 row(s) to re-baseline, 1 row(s) left as they are" in text, text)
    check("rebaseline: a dry run writes nothing at all", 
          (live / "_jarvis-state.json").read_bytes() == before)
    code, text = run_tool(repo, live, ref="HEAD", show=show, apply=True, stamp="TR")
    doc = json.loads((live / "_jarvis-state.json").read_text(encoding="utf-8"))
    check("rebaseline: without the flag the row is still not rewritten",
          doc["files"]["jarvis_hud.py"]["sha256"] == sha(old_hud), doc["files"])
    check("rebaseline: without the flag the run exits 1", code == 1, code)
    code, text = run_tool(repo, live, ref="HEAD", show=show, apply=True, stamp="TS",
                          rebaseline_unprovable=True)
    doc = json.loads((live / "_jarvis-state.json").read_text(encoding="utf-8"))
    check("rebaseline: with the flag the row holds the folder's own hash",
          doc["files"]["jarvis_hud.py"]["sha256"] == sha(new_hud), doc["files"])
    check("rebaseline: with the flag the row keeps its patch name and verified flag",
          doc["files"]["jarvis_hud.py"]["patch"] == "hud.patch"
          and doc["files"]["jarvis_hud.py"]["verified"] is True)
    check("rebaseline: with the flag the run exits 0",
          code == 0 and "RESULT: PASS" in text, text)


# ---------------------------------------------------------------------------
#   4. Refusals: ambiguity, absent files, unsafe rows
# ---------------------------------------------------------------------------

def t_an_ambiguous_or_absent_file_is_refused():
    repo, show = make_repo(["rebuilt/x.py", "x.py"],
                           {"rebuilt/x.py": b"a = 1\n", "x.py": b"a = 2\n"})
    live = make_live({"jarvis_hud.py": HUD})
    for apply in (False, True):
        refused = ""
        try:
            run_tool(repo, live, ref="HEAD", show=show, apply=apply)
        except T.Refused as exc:
            refused = str(exc)
        check(f"ambiguous shipped names: refused ({'apply' if apply else 'dry run'})",
              "twice" in refused, refused)
    check("ambiguous shipped names: the live folder is untouched",
          sorted(tree(live)) == ["jarvis_hud.py"], sorted(tree(live)))

    repo2, show2 = make_repo(SHIPPED, BLOBS)
    gone = b"# a module the record knows and the repository does not ship\n"
    live2 = make_live({"jarvis_hud.py": HUD,
                       "jarvis_compute.py": OLD_COMPUTE,
                       "jarvis_wiki.py": BLOBS["jarvis_wiki.py"]},
                      a_record({"jarvis_compute.py": a_row(OLD_COMPUTE),
                                "jarvis_gone.py": a_row(gone)}))
    before = (live2 / "_jarvis-state.json").read_bytes()
    code, text = run_tool(repo2, live2, ref="HEAD", show=show2, apply=True, stamp="T4")
    check("absent and unshipped: it is reported, with the folder said to be empty",
          f"jarvis_gone.py: record {sha(gone)[:12]}, folder (absent)" in text, text)
    check("absent and unshipped: no file is invented for it",
          not (live2 / "jarvis_gone.py").exists())
    check("absent and unshipped: its record row keeps the old hash",
          json.loads((live2 / "_jarvis-state.json").read_text())["files"]
          ["jarvis_gone.py"]["sha256"] == sha(gone))
    check("absent and unshipped: exits 1", code == 1, code)
    del before

    live3 = make_live({"jarvis_hud.py": HUD})
    (live3 / "jarvis_compute.py").mkdir()
    refused = ""
    try:
        run_tool(repo2, live3, ref="HEAD", show=show2, apply=True)
    except T.Refused as exc:
        refused = str(exc)
    check("a directory where a shipped file goes: refused",
          "not a regular file" in refused, refused)
    check("a directory where a shipped file goes: nothing was written elsewhere",
          sorted(name for name in tree(live3) if name != "jarvis_compute.py")
          == ["jarvis_hud.py"], sorted(tree(live3)))


def t_a_record_row_outside_the_folder_is_refused():
    repo, show = make_repo(SHIPPED, BLOBS)
    live = make_live({"jarvis_hud.py": HUD, "jarvis_compute.py": OLD_COMPUTE,
                      "jarvis_wiki.py": BLOBS["jarvis_wiki.py"]},
                     a_record({"../escape.py": a_row(b"# outside\n")}))
    refused = ""
    try:
        run_tool(repo, live, ref="HEAD", show=show, apply=True)
    except T.Refused as exc:
        refused = str(exc)
    check("a record row naming a path outside the folder: refused",
          "not a safe relative file name" in refused, refused)
    check("... and the record is byte-identical",
          json.loads((live / "_jarvis-state.json").read_text())["files"]
          == {"../escape.py": a_row(b"# outside\n")})


# ---------------------------------------------------------------------------
#   5. Files the repository does not ship
# ---------------------------------------------------------------------------

def t_a_file_the_repository_does_not_ship_is_never_touched():
    repo, show = make_repo(SHIPPED, BLOBS)
    extras = {"jarvis_hud.py": HUD,
              "jarvis_secrets.py": b"# a module only this PC has\n",
              "notes.txt": b"the owner's notes\n",
              "some.patch": b"--- a/jarvis_hud.py\n",
              "jarvis_plugins/thing/plugin.json": b'{"name": "thing"}\n'}
    live = make_live(extras, a_record({"jarvis_compute.py": a_row(OLD_COMPUTE)}))
    before = {name: data for name, data in tree(live).items() if name in extras}
    code, text = run_tool(repo, live, ref="HEAD", show=show, apply=True, stamp="T5")
    after = {name: data for name, data in tree(live).items() if name in extras}
    check("unshipped files: every one is byte-identical afterwards", after == before,
          sorted(set(after) ^ set(before)))
    check("unshipped files: none of them was backed up",
          not any(name.startswith(tuple(extras)) and ".before-reseal-" in name
                  for name in tree(live)), sorted(tree(live)))
    check("unshipped files: none of them is named in the plan",
          "notes.txt" not in text and "jarvis_secrets.py" not in text
          and "some.patch" not in text, text)
    check("unshipped files: the run still did its own job", code == 0
          and (live / "jarvis_compute.py").read_bytes()
          == BLOBS["rebuilt/jarvis_compute.py"], code)


# ---------------------------------------------------------------------------
#   6. Idempotence
# ---------------------------------------------------------------------------

def t_a_second_apply_changes_nothing():
    repo, live, show = a_small_pc()
    run_tool(repo, live, ref="HEAD", show=show, apply=True, stamp="T6")
    first = tree(live)
    code, text = run_tool(repo, live, ref="HEAD", show=show, apply=True, stamp="T7")
    check("second apply: it says there is nothing to do",
          "RESULT: PASS - nothing to do" in text, text)
    check("second apply: the tree is byte-identical", tree(live) == first,
          sorted(set(tree(live)) ^ set(first)))
    check("second apply: no new backup is made",
          not any("T7" in name for name in tree(live)), sorted(tree(live)))
    check("second apply: exits 0", code == 0, code)


# ---------------------------------------------------------------------------
#   7. A corrupted file, and a repository copy that cannot compile
# ---------------------------------------------------------------------------

def t_a_corrupted_live_file_is_replaced_and_the_result_compiles():
    repo, show = make_repo(SHIPPED, BLOBS)
    live = make_live({"jarvis_hud.py": HUD,
                      "jarvis_compute.py": b"def compute(:\n    this is not python\n",
                      "jarvis_wiki.py": BLOBS["jarvis_wiki.py"]},
                     a_record({"jarvis_compute.py": a_row(b"def compute(:\n")}))
    code, text = run_tool(repo, live, ref="HEAD", show=show, apply=True, stamp="T8")
    body = (live / "jarvis_compute.py").read_bytes()
    check("corrupted live file: it is replaced with the repository's bytes",
          body == BLOBS["rebuilt/jarvis_compute.py"], body)
    compiled = ""
    try:
        compile(body.decode("utf-8"), "jarvis_compute.py", "exec")
    except SyntaxError as exc:                              # pragma: no cover
        compiled = str(exc)
    check("corrupted live file: what is now in the folder really compiles",
          compiled == "", compiled)
    check("corrupted live file: the corrupt bytes are in the backup",
          (live / "jarvis_compute.py.before-reseal-T8").read_bytes()
          == b"def compute(:\n    this is not python\n")
    check("corrupted live file: the run says the compile check passed",
          "COMPILE : py_compile OK" in text, text)
    check("corrupted live file: no bytecode was left behind",
          not any(name.endswith(".pyc") for name in tree(live)), sorted(tree(live)))


def t_a_repository_copy_that_does_not_compile_writes_nothing():
    broken = dict(BLOBS)
    broken["rebuilt/jarvis_compute.py"] = b"def compute(:\n    return 1\n"
    repo, show = make_repo(SHIPPED, broken)
    live = make_live({"jarvis_hud.py": HUD,
                      "jarvis_compute.py": OLD_COMPUTE,
                      "jarvis_wiki.py": BLOBS["jarvis_wiki.py"]},
                     a_record({"jarvis_compute.py": a_row(OLD_COMPUTE)}))
    before = tree(live)
    refused = ""
    try:
        run_tool(repo, live, ref="HEAD", show=show, apply=True)
    except T.Refused as exc:
        refused = str(exc)
    check("a repository file that will not compile: the run is refused",
          "does not compile" in refused, refused)
    check("a repository file that will not compile: the live folder is byte-identical",
          tree(live) == before, sorted(set(tree(live)) ^ set(before)))


# ---------------------------------------------------------------------------
#   8. The preflight row set improves
# ---------------------------------------------------------------------------

def t_the_patch_projection_counts_and_names_the_rows_that_move():
    repo, live, show = a_small_pc()
    calls = {"read": []}

    def states(backend, read=None):
        if read is None:
            return [("p1.patch", "jarvis_compute.py", "not applied", 0, 2),
                    ("p2.patch", "jarvis_hud.py", "not applied", 0, 3)]
        calls["read"].append(read("jarvis_compute.py"))
        return [("p1.patch", "jarvis_compute.py", "applied", 2, 2),
                ("p2.patch", "jarvis_hud.py", "not applied", 0, 3)]

    code, text = run_tool(repo, live, ref="HEAD", show=show, states_fn=states)
    check("projection: it counts the patch rows now and after",
          "patches : 2 not applied/partly now, 1 after (of 2 patch/file row(s))" in text,
          text)
    check("projection: it names the patch that flips to applied",
          "p1.patch -> jarvis_compute.py" in text, text)
    check("projection: it names every patch it cannot fix, grouped by the file it writes",
          "still not applied/partly after the reseal (1, by the file each patch writes)"
          in text
          and "jarvis_hud.py (1): p2.patch (not applied 0/3)" in text, text)
    check("projection: the 'after' list is read from the repository's bytes, not the "
          "folder's",
          calls["read"] and calls["read"][0] == BLOBS["rebuilt/jarvis_compute.py"].decode(),
          calls["read"][:1])


def t_the_real_preflight_modules_check_improves_on_a_synthetic_install():
    sys.path.insert(0, str(HERE))
    try:
        import selftest as S                                    # noqa: PLC0415
    except Exception as exc:                                    # pragma: no cover
        skip(f"backend/selftest.py could not be imported here: {exc}")
        return
    sys.path.insert(0, str(REPO / "backend"))
    from _where import SHIPPED as REAL_SHIPPED                  # noqa: PLC0415

    live = Path(tempfile.mkdtemp(prefix="reseal-synthetic-pc-"))
    for entry in REAL_SHIPPED:
        source = REPO / "backend" / entry
        (live / entry.rsplit("/", 1)[-1]).write_bytes(source.read_bytes())
    # The five patched base files: this repository does not ship them whole, so the
    # fixture stands in for what the patch stack put on the PC.
    for name in ("jarvis_hud.py", "jarvis_gate.py", "jarvis_extract.py",
                 "jarvis_models.py", "jarvis_skills.py"):
        (live / name).write_bytes(b"# a base file the patch stack produced\n")
    rows = {path.name: a_row(path.read_bytes())
            for path in live.glob("*.py") if path.is_file()}
    write_record(live, a_record(rows))
    # Three files drift AFTER the record was written: one rebuilt module, one other
    # shipped module, and one file only the patch stack owns.
    for name, bad in (("jarvis_compute.py", b"# an older copy\n"),
                      ("jarvis_wiki.py", b"# an older copy\n"),
                      ("jarvis_gate.py", b"# the live gate, newer than the record\n")):
        (live / name).write_bytes(bad)

    def failing():
        return [row for row in S.pf_modules(S.Live(backend=live)) if row[0] == S.FAIL]

    before = failing()
    check("synthetic install: the real modules check starts with three FAIL rows",
          len(before) == 3, [row[1] for row in before])

    def show(repo, ref, path):
        return (REPO / path).read_bytes()

    code, text = run_tool(REPO, live, ref="HEAD", show=show, apply=True, stamp="T9",
                          states_fn=lambda backend, read=None: [])
    after = failing()
    check("synthetic install: the real modules check ends with one FAIL row",
          len(after) == 1, [row[1] for row in after])
    check("synthetic install: the row that is left is the patched base file",
          after and after[0][1].startswith("jarvis_gate.py"), after)
    check("synthetic install: the tool's own mirror agrees before (three)",
          "modules : 3 failing row(s) now" in text, text)
    check("synthetic install: the tool's own mirror agrees after (one)",
          "1 after the reseal" in text, text)
    check("synthetic install: the real check's own count is printed for comparison",
          "its own modules check reports 3 FAIL row(s)" in text, text)
    check("synthetic install: no disagreement is reported between the two counts",
          "the two disagree" not in text, text)
    check("synthetic install: it exits 1, because one row is not its to fix",
          code == 1, code)
    check("synthetic install: the shipped files really are the repository's bytes",
          (live / "jarvis_compute.py").read_bytes()
          == (REPO / "backend" / "rebuilt" / "jarvis_compute.py").read_bytes())


# ---------------------------------------------------------------------------
#   9. The CLI, on a real git repository with no seam
# ---------------------------------------------------------------------------

def a_git_repo():
    root = Path(tempfile.mkdtemp(prefix="reseal-git-"))
    (root / "scripts").mkdir()
    (root / "backend" / "rebuilt").mkdir(parents=True)
    text = ("$SHIPPED = @(\n    'rebuilt/jarvis_compute.py'\n    'jarvis_wiki.py'\n)\n"
            "\n$PATCHES = @(\n    'test.patch'\n)\n")
    (root / "scripts" / "apply-patches.ps1").write_text(text, encoding="utf-8")
    (root / "backend" / "rebuilt" / "jarvis_compute.py").write_bytes(
        BLOBS["rebuilt/jarvis_compute.py"])
    (root / "backend" / "jarvis_wiki.py").write_bytes(BLOBS["jarvis_wiki.py"])

    def git(*args):
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                              text=True, timeout=120)

    try:
        if git("init", "-q").returncode != 0:                    # pragma: no cover
            return None
        git("config", "user.email", "test@example.invalid")
        git("config", "user.name", "reseal test")
        git("add", "-A")
        if git("commit", "-q", "-m", "the fixture repository").returncode != 0:
            return None                                             # pragma: no cover
    except (OSError, subprocess.SubprocessError):                # pragma: no cover
        return None
    return root


def t_the_cli_drives_a_real_git_repository():
    repo = a_git_repo()
    if repo is None:                                            # pragma: no cover
        skip("git is not available here, so the real-blob path could not be driven")
        return
    live = make_live({"jarvis_hud.py": HUD,
                      "jarvis_compute.py": OLD_COMPUTE,
                      "jarvis_wiki.py": BLOBS["jarvis_wiki.py"]})
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = T.main(["--backend-path", str(live), "--repo", str(repo), "--ref", "HEAD"])
    check("CLI: a dry run on a real repository exits 0", code == 0, out.getvalue())
    check("CLI: it read the bytes from the commit, not from a working-tree copy",
          "jarvis_compute.py" in out.getvalue() and "bytes from HEAD = " in out.getvalue(),
          out.getvalue())
    check("CLI: the dry run wrote nothing",
          (live / "jarvis_compute.py").read_bytes() == OLD_COMPUTE)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = T.main(["--backend-path", str(live), "--repo", str(repo), "--ref", "HEAD",
                       "--apply", "--dry-run"])
    check("CLI: --apply with --dry-run is refused", code == 2, out.getvalue())
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = T.main(["--backend-path", str(live), "--repo", str(repo), "--ref", ""])
    check("CLI: an empty --ref is refused", code == 2
          and "--ref must not be empty" in out.getvalue(), out.getvalue())
    nowhere = Path(tempfile.mkdtemp(prefix="reseal-not-a-backend-"))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = T.main(["--backend-path", str(nowhere), "--repo", str(repo),
                       "--ref", "HEAD"])
    check("CLI: a folder with no jarvis_hud.py is refused", code == 2
          and "no jarvis_hud.py" in out.getvalue(), out.getvalue())
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        first = T.main(["--backend-path", str(live), "--repo", str(repo), "--ref", "HEAD",
                        "--apply"])
        second = T.main(["--backend-path", str(live), "--repo", str(repo), "--ref", "HEAD",
                         "--apply"])
    check("CLI: apply on a real repository exits 0", first == 0, out.getvalue())
    check("CLI: a second apply exits 0 and changes nothing",
          second == 0 and "nothing to do" in out.getvalue(), out.getvalue())
    check("CLI: the file really holds the committed bytes",
          (live / "jarvis_compute.py").read_bytes()
          == BLOBS["rebuilt/jarvis_compute.py"])


# ---------------------------------------------------------------------------

TESTS = [
    t_dry_run_reports_each_file_and_writes_nothing,
    t_apply_copies_the_repository_bytes_and_keeps_a_backup,
    t_a_stale_row_is_corrected_only_for_a_file_the_tool_owns,
    t_a_record_this_tool_does_not_understand_is_left_alone,
    t_rebaselining_the_unprovable_rows_is_off_until_asked_for,
    t_an_ambiguous_or_absent_file_is_refused,
    t_a_record_row_outside_the_folder_is_refused,
    t_a_file_the_repository_does_not_ship_is_never_touched,
    t_a_second_apply_changes_nothing,
    t_a_corrupted_live_file_is_replaced_and_the_result_compiles,
    t_a_repository_copy_that_does_not_compile_writes_nothing,
    t_the_patch_projection_counts_and_names_the_rows_that_move,
    t_the_real_preflight_modules_check_improves_on_a_synthetic_install,
    t_the_cli_drives_a_real_git_repository,
]


def main():
    for fn in TESTS:
        print(f"--- {fn.__name__} ---")
        try:
            fn()
        except Exception as exc:                                # pragma: no cover
            traceback.print_exc()
            check(f"{fn.__name__} ran without crashing", False, repr(exc))
    total = len(PASSED) + len(FAILED)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed, {len(SKIPPED)} skipped"
          f" ({total} check(s) ran)")
    if SKIPPED:
        for why in SKIPPED:
            print(f"NOT RUN  {why}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
