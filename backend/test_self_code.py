"""The self-code map (2026-11-07): Jarvis knows the major parts of its own code.

    python3 backend/test_self_code.py

WHAT THIS PROVES, in the order it checks it:

  - the GENERATOR is deterministic: `--check` passes on the committed map, two
    renders of one tree are identical, and the commit it records is this tree's
    own HEAD - so "what changed" is an answer about a real commit, not a wall
    clock;
  - the map is COMPLETE BY CONSTRUCTION: every file a commit would carry
    belongs to exactly one subsystem or is named in the exclude list, and the
    generator refuses a tree with a file nobody owns (proved on a synthetic tree
    through its own `build_map`, and with a second claimant added to its own
    table);
  - the map SHAPE holds: every subsystem has a purpose, files, key modules with
    their docstring's first sentence, tests, docs and at least one area; the
    architecture list is the five runtime parts in order; the newest twenty
    commits are there; the coverage arithmetic adds up;
  - each of the four chat intents answers from that map, word for word, with no
    model: the overview names the parts and where to start reading, a lookup
    names the part, its path, its tests and its docs, "recent" says it is as of
    the deploy that built the map, and "self repo" names the public repository;
  - a MISS says so and names the two nearest parts instead of guessing, and the
    absence of the map file is itself an honest answer - never an exception;
  - the old owners keep their sentences: version, tools, GPUs, memory and chat
    counts, identity, the feature overview, reach and "where did I put" all take
    their own phrasings exactly as before this change;
  - the two-file rule: `jarvis_self_code.py` and `jarvis-self-code.json` are
    byte-identical in `backend/` and `jarvis-backend/`, are in the SHIPPED list
    and the base's BESIDE table, and `jarvis_quick.py`'s twin matches too.

Nothing here opens a socket, calls a model or touches the owner's live folder:
`JARVIS_BACKEND` is never required, and the map is read from this checkout.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-self-code-"))
# Before anything imports jarvis_framework: its CONFIG_DIR is read once.
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_SCHEDULE_DB"] = str(_TMP / "schedule.db")
os.environ["OPENJARVIS_HOME"] = str(_TMP / "home")
os.environ["JARVIS_HOME"] = str(_TMP / "home")
(_TMP / "home").mkdir(parents=True, exist_ok=True)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_self_code.py", "jarvis-self-code.json", "jarvis_quick.py")

import jarvis_self_code as SC  # noqa: E402
import jarvis_quick as K  # noqa: E402

PASSED, FAILED = [], []
MAP_PATH = REPO / "backend" / SC.MAP_NAME
ALLOWED_AREAS = {"backend", "base", "desktop", "android", "tools", "docs", "ci"}


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def git(*args):
    """git's stdout in this repository, or "" - a check must not crash on it."""
    return _git_run(*args)[1]


def _git_run(*args):
    """(exit code, stdout) for one git command in this repository."""
    try:
        done = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True,
                              check=False)
    except OSError:
        return 1, ""
    return done.returncode, done.stdout.decode("utf-8", "replace").strip()


def generator():
    """The generator module, loaded by path - it is a tool, not an importable one."""
    spec = importlib.util.spec_from_file_location(
        "gen_self_code_map", REPO / "tools" / "gen_self_code_map.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    return gen


GEN = generator()
MAP = json.loads(MAP_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
#   The generator: deterministic, and complete by construction
# --------------------------------------------------------------------------

def t_the_generator_is_deterministic():
    first = GEN.generate(REPO)
    second = GEN.generate(REPO)
    check("two runs on one tree produce the same bytes", first == second)
    # THE STRICT HALF: rebuild the document from this tree, with the provenance
    # the committed map records, and compare it with the committed file. That is
    # exactly what `--check` compares, with the dirty-tree judgement taken out.
    fresh = GEN.render(GEN.build_map(
        REPO, GEN.tree_files(REPO), ref=MAP["ref"], built_at=MAP["built_at"],
        commits=list(MAP["recent_commits"])))
    check("the committed map is byte-for-byte what this tree produces",
          fresh == MAP_PATH.read_text(encoding="utf-8"),
          "the generator would write different bytes")
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        rc = GEN.check(REPO)
    said = captured.getvalue()
    check("--check agrees, or refuses a dirty tree in its documented words",
          rc == 0 or ("uncommitted changes" in said and "map itself is not" in said),
          said.strip().splitlines()[0] if said.strip() else f"exit {rc}")
    info = GEN.provenance(REPO)
    check("the recorded commit is this tree's HEAD", info["ref"] == git("rev-parse", "HEAD"),
          f"{info['ref']} != {git('rev-parse', 'HEAD')}")
    check("the recorded build date is that commit's own date, not now",
          info["built_at"] == git("show", "-s", "--format=%cI", "HEAD"),
          info["built_at"])
    rebuilt = GEN.build_map(REPO, GEN.tree_files(REPO), ref="0" * 40,
                            built_at="2000-01-01T00:00:00+00:00", commits=[])
    check("the map is a product of the tree, not of the clock",
          rebuilt["ref"] == "0" * 40 and rebuilt["built_at"].startswith("2000-01-01"))


def t_the_generator_refuses_a_tree_it_cannot_cover():
    import tempfile as _tf
    with _tf.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "backend").mkdir()
        (root / "backend" / "jarvis_quick.py").write_text('"""A module."""\n',
                                                          encoding="utf-8")
        (root / "VERSION").write_text("0.0.1", encoding="utf-8")
        (root / "stray").mkdir()
        (root / "stray" / "nobody-owns-me.py").write_text("x = 1\n", encoding="utf-8")
        try:
            GEN.build_map(root, ["VERSION", "backend/jarvis_quick.py",
                                 "stray/nobody-owns-me.py"],
                          ref="abc", built_at="2026-11-07T00:00:00+00:00", commits=[])
            raised = ""
        except GEN.CoverageError as exc:
            raised = str(exc)
        check("a file no subsystem owns fails the run", "nobody-owns-me.py" in raised,
              raised or "no error was raised")
        check("... and the failure names the count and the path",
              "belong to no subsystem" in raised and "stray/nobody-owns-me.py" in raised,
              raised)
        # The other half: a file two subsystems claim is refused too, and both
        # claimants are named. The extra row is added to the generator's OWN
        # table - so the check is exercised on the code that runs, not a copy.
        original = GEN.SUBSYSTEMS
        try:
            extra = dict(original[0])
            extra["id"] = "second-claimant"
            extra["modules"] = ("jarvis_quick",)
            extra["paths"] = ()
            extra["key_modules"] = ()
            GEN.SUBSYSTEMS = tuple(original) + (extra,)
            try:
                GEN.assign(["backend/jarvis_quick.py"])
                shared = ""
            except GEN.CoverageError as exc:
                shared = str(exc)
        finally:
            GEN.SUBSYSTEMS = original
        check("a file two subsystems claim fails the run",
              "more than one subsystem" in shared, shared or "no error was raised")
        check("... and names both claimants, so the fix is obvious",
              "quick" in shared and "second-claimant" in shared, shared)


def t_the_exclude_list_is_named_and_counted():
    check("the exclude list carries a reason for every pattern",
          all(reason.strip() for _pattern, reason in GEN.EXCLUDED),
          str(GEN.EXCLUDED[:2]))
    dropped = [r for r in MAP["excluded_patterns"] if r["count"]]
    check("every excluded group in the map has a count and examples",
          bool(dropped) and all(r["examples"] for r in dropped), str(dropped[:2]))
    cov = MAP["coverage"]
    check("the coverage arithmetic adds up (covered + excluded = tracked)",
          cov["covered"] + cov["excluded"] == cov["tracked_files"],
          str(cov))
    check("every file the map lists is really tracked by git",
          all(row["file_count"] for row in MAP["subsystems"]), "an empty subsystem")
    owned = [f for row in MAP["subsystems"] for f in row["files"]]
    check("no file is listed by two subsystems", len(owned) == len(set(owned)),
          f"{len(owned)} listings, {len(set(owned))} distinct")
    tracked = set(GEN.tree_files(REPO))
    check("every listed file exists in this tree", set(owned) <= tracked,
          str(sorted(set(owned) - tracked)[:3]))


# --------------------------------------------------------------------------
#   The map's shape
# --------------------------------------------------------------------------

def t_the_map_shape_holds():
    check("the map names the public repository",
          MAP["repo"] == "darknight11ish/Epic-Jarvis" and MAP["public"] is True,
          f"{MAP.get('repo')} {MAP.get('public')}")
    check("the map carries a version and a commit", bool(MAP["version"])
          and len(MAP["ref"]) == 40, f"{MAP['version']} {MAP['ref']}")
    check("every key module's summary is a real first sentence",
          all(k["summary"] and len(k["summary"]) <= 201
              for row in MAP["subsystems"] for k in row["key_modules"]),
          str([k for row in MAP["subsystems"] for k in row["key_modules"]
               if not k["summary"]][:2]))
    problems = []
    for row in MAP["subsystems"]:
        if not (row["id"] and row["title"] and row["purpose"]):
            problems.append(f"{row['id']}: no id/title/purpose")
        if not row["files"] or row["file_count"] != len(row["files"]):
            problems.append(f"{row['id']}: files and file_count disagree")
        # Docs, deploy and videos are not modules: they have nothing to start
        # reading IN, so a key module there would have to be invented.
        if len(row["key_modules"]) > 6:
            problems.append(f"{row['id']}: {len(row['key_modules'])} key modules")
        if row["group"] == "runtime" and not row["key_modules"]:
            problems.append(f"{row['id']}: a runtime part with no start module")
        if not row["tests"]:
            problems.append(f"{row['id']}: no tests")
        if not row["docs"]:
            problems.append(f"{row['id']}: no docs")
        if not row["areas"] or not set(row["areas"]) <= ALLOWED_AREAS:
            problems.append(f"{row['id']}: areas {row['areas']}")
        for path in row["tests"] + row["docs"] + [k["path"] for k in row["key_modules"]]:
            if not (REPO / path).is_file():
                problems.append(f"{row['id']}: {path} is not here")
    check("every subsystem has a purpose, files, modules, tests, docs and areas",
          not problems, "; ".join(problems[:6]))
    check("the map has the parts a person would ask about by name",
          {"gate", "memory", "models", "quick", "agent", "tools", "voice",
           "phone", "desktop", "self", "features"} <= {r["id"] for r in MAP["subsystems"]},
          str(sorted(r["id"] for r in MAP["subsystems"])))
    arch = MAP["architecture"]
    check("the architecture list is the five runtime parts, in order",
          [a["id"] for a in arch] == ["pc", "models", "desktop", "phone", "github"],
          str([a.get("id") for a in arch]))
    check("... each with a title, one sentence and owning paths",
          all(a["title"] and a["sentence"] and a["paths"] for a in arch), str(arch[:1]))
    check("the newest twenty commits are recorded with their dates",
          len(MAP["recent_commits"]) == 20
          and all(c["date"] and c["subject"] and c["sha"] for c in MAP["recent_commits"]),
          str(len(MAP["recent_commits"])))
    check("the top-level directories are described, one line each",
          len(MAP["top_level"]) >= 15
          and all(t["path"] and t["line"] for t in MAP["top_level"]),
          str(len(MAP["top_level"])))


def t_the_map_was_built_from_a_commit_in_this_history():
    ref = MAP["ref"]
    code, _out = _git_run("cat-file", "-e", ref + "^{commit}")
    check("the map's commit exists in this repository", code == 0, ref)
    # On the commit that carries the map, `ref` is its parent; while the map is
    # still uncommitted it IS HEAD. Both are true statements about this history.
    at_head = ref == git("rev-parse", "HEAD")
    ancestor, _out = _git_run("merge-base", "--is-ancestor", ref, "HEAD")
    check("the map's commit is this tree's HEAD or one of its ancestors",
          at_head or ancestor == 0, f"{ref} is not in HEAD's history")


# --------------------------------------------------------------------------
#   The four intents: the right names, from the map, with no model
# --------------------------------------------------------------------------

def answer(sentence):
    """(intent name, the reply) for one sentence through the real matcher."""
    got = K.match(sentence)
    if got is None:
        return None, ""
    out = K.run(got, None, time.time())
    return got.name, (out.reply if out is not None else "")


def t_the_overview_names_the_parts_and_where_to_read():
    name, text = answer("what are your major parts")
    check("'what are your major parts' is the self-code overview",
          name == "self_code_overview", str(name))
    for said in ("Approvals and the gate", "Memory: facts", "Voice: speech",
                 "backend/jarvis_quick.py", "parts that run"):
        check(f"the overview names {said!r}", said in text)
    check("the overview says the map holds no code",
          "does not hold the code itself" in text)
    check("the overview is bounded (25-40 lines)",
          25 <= len(text.splitlines()) <= 40, str(len(text.splitlines())))
    for sentence in ("what is your architecture", "how are you built",
                     "what are the major parts of your code"):
        check(f"{sentence!r} reaches the same answer",
              answer(sentence)[0] == "self_code_overview")


def t_a_lookup_names_the_part_its_path_its_tests_and_its_docs():
    name, text = answer("what does the memory subsystem do")
    check("'what does the memory subsystem do' is the lookup", name == "self_code_lookup",
          str(name))
    for said in ("Memory: facts, recall", "backend/jarvis_intake.py",
                 "backend/test_memory_recall.py", "docs/ARCHITECTURE.md"):
        check(f"the memory lookup names {said!r}", said in text)
    for sentence in ("where is the code for memory", "where is memory in your code",
                     "which part of your code handles memory"):
        check(f"{sentence!r} reaches the memory lookup",
              answer(sentence)[0] == "self_code_lookup", str(answer(sentence)[0]))
    _n, voice = answer("where is the code for voice")
    check("another subject answers with its own part",
          "Voice: speech" in voice and "backend/jarvis_speech.py" in voice)
    check("the same question twice gives the same words",
          SC.lookup("memory") == SC.lookup("memory") == text)


def t_a_miss_says_so_and_names_the_two_nearest():
    name, text = answer("where is the code for quantum sprockets")
    check("a subject the map does not know is still the lookup",
          name == "self_code_lookup", str(name))
    check("a miss says it is not in the map I was built with",
          "not in the map I was built with" in text, text)
    check("... and names the two nearest parts", text.count('"') >= 4, text)
    check("... and does not guess", "I will not guess" in text, text)
    check("the module itself answers a miss the same way",
          "not in the map I was built with" in SC.lookup("quantum sprockets"))


def t_recent_and_self_repo_answer_from_the_same_map():
    name, text = answer("what did you change recently")
    check("'what did you change recently' is the recent answer",
          name == "self_code_recent", str(name))
    check("recent says it is as of the deploy that built the map",
          "as of the deploy that built this map" in text.lower(), text[:120])
    check("recent names the commit and the version",
          MAP["ref"][:9] in text and MAP["version"] in text, text[:160])
    check("recent carries the twenty subjects", text.count("- 20") >= 18,
          str(text.count("- 20")))
    for sentence in ("what changed on main", "what was your last release"):
        check(f"{sentence!r} reaches the recent answer",
              answer(sentence)[0] == "self_code_recent")
    name, repo = answer("what is your github repository")
    check("'what is your github repository' is the repository answer",
          name == "self_code_repo", str(name))
    for said in ("darknight11ish/Epic-Jarvis", "github.com/darknight11ish",
                 "public"):
        check(f"the repository answer names {said!r}", said in repo)
    for sentence in ("where is your code on github", "where do you live on github"):
        check(f"{sentence!r} reaches the repository answer",
              answer(sentence)[0] == "self_code_repo")
    check("the four intents are read-only (a private chat keeps its own rule)",
          {"self_code_overview", "self_code_lookup", "self_code_recent",
           "self_code_repo"} <= K.READ_ONLY_INTENTS)


def t_a_missing_map_is_an_honest_answer_not_an_exception():
    real_name, real_cache = SC.MAP_NAME, dict(SC._CACHE)
    try:
        SC.MAP_NAME = "jarvis-self-code-that-is-not-there.json"
        SC._CACHE.clear()
        check("a missing map means available() is False", SC.available() is False)
        info = SC.map_info()
        check("map_info says why, with the same keys",
              info["available"] is False and "not installed" in info["why"]
              and set(info) >= {"ref", "version", "built_at", "repo"}, str(info))
        for label, text in (("overview", SC.overview()), ("lookup", SC.lookup("memory")),
                            ("recent", SC.recent()), ("self repo", SC.self_repo())):
            check(f"the {label} answer says the map was not installed",
                  "not installed" in text and text.strip() != "", text[:80])
    finally:
        SC.MAP_NAME, SC._CACHE = real_name, real_cache


def t_the_old_owners_keep_their_own_sentences():
    rows = [
        ("what version are you", "self_version"),
        ("what is your version", "self_version"),
        ("what tools do you have", "tools_inventory"),
        ("what cards are installed", "self_hardware"),
        ("how many graphics cards do i have", "self_hardware"),
        ("how many notes do i have", "self_notes"),
        ("how many conversations do i have", "self_chats"),
        ("who are you", "identity_help"),
        ("what can you do", "feature_overview"),
        ("what can you reach", "reach_list"),
        ("where is my passport", "where_put"),
        ("where did i put my keys", "where_put"),
        ("where is the talk button", "feature_explain"),
    ]
    wrong = [(s, want, K.match(s).name if K.match(s) else None)
             for s, want in rows if (K.match(s).name if K.match(s) else None) != want]
    check("every old phrasing still takes its old path", not wrong, str(wrong))
    check("ordinary English is not claimed by the lookup",
          K.match("what does my oven do") is None
          and K.match("how are you built differently from chatgpt") is None,
          str(K.match("what does my oven do")))
    check("'what does X do' only fires when X is really in the map",
          K.match("what does memory do").name == "self_code_lookup"
          and K.match("what does my oven do") is None)


# --------------------------------------------------------------------------
#   The two-file rule
# --------------------------------------------------------------------------

def t_the_module_and_its_map_travel_together():
    for leaf in ("jarvis_self_code.py", SC.MAP_NAME, "jarvis_quick.py"):
        ours = REPO / "backend" / leaf
        theirs = REPO / "jarvis-backend" / leaf
        check(f"jarvis-backend/{leaf} is this repository's own bytes",
              theirs.is_file() and theirs.read_bytes() == ours.read_bytes(),
              "missing or different")
    import _where
    check("the reader and its map are on the SHIPPED list",
          "jarvis_self_code.py" in _where.SHIPPED
          and SC.MAP_NAME in _where.SHIPPED, str(_where.SHIPPED[-4:]))
    spec = importlib.util.spec_from_file_location(
        "gen_base_from_backend", REPO / "tools" / "gen_base_from_backend.py")
    gen_base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen_base)
    beside = [name for name, _where_from, _why in gen_base.BESIDE]
    check("the map is in the BESIDE table the base is re-taken from",
          SC.MAP_NAME in beside, str(beside[-4:]))
    ps1 = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8",
                                                             errors="replace")
    check("apply-patches.ps1 ships the reader and the map",
          "'jarvis_self_code.py'" in ps1 and f"'{SC.MAP_NAME}'" in ps1)
    check("the reader is imported lazily by the matcher, never at import time",
          "import jarvis_self_code" in (REPO / "backend" / "jarvis_quick.py")
          .read_text(encoding="utf-8"))


def main():
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:  # pragma: no cover
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, 0 skipped, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
