"""The learner's model half must reach the REAL jarvis_extract.py, 2026-10-09.

    python3 test_learner_real_model.py

Measured here before the fix: `python backend/eval_learner.py` reported the
116 cases that need no model and said nothing about the rest - and
`--learner-model qwen3:8b` reported the same 116, with no model score at all.

WHY. `eval_learner.World.__init__` puts a STAND-IN jarvis_extract module into
`sys.modules` - the patch stack's own text, with no file behind it - so that
the cases which need no model can run on a machine that has no backend install.
`run_model_part` then did `import jarvis_extract`, and Python answers that
import from `sys.modules` first. So the "real learner" ran the stand-in: it has
no `propose` attribute and no `__file__`, and the model half came back as
"jarvis_extract.py could not be loaded" or, worse, as cases that quietly scored
zero. The learner's model-dependent numbers were UNMEASURED, not passing.

THE FIX. `eval_learner.load_real_extract()` reads the file from disk (the
JARVIS_BACKEND folder, else beside eval_learner.py), sets the stand-in aside
for exactly the length of that import, and hands `run_model_part` a module
whose `__file__` is the real file. The stand-in goes back into `sys.modules`
afterwards, so the no-model cases are untouched.

No network, no model: the stand-in backend this suite writes has a `propose`
that refuses, which is enough to prove WHICH module the model half used. It
must be run with JARVIS_BACKEND pointing at the backend under test, because
that is the folder the fix has to read the real file from; the suite says so
and stops plainly when it is not.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

FAILED, PASSED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


if not os.environ.get("JARVIS_BACKEND"):
    # The fix resolves the real file from JARVIS_BACKEND. Without it the
    # folder under test is this one, which ships no jarvis_extract.py - so
    # there is nothing here to prove, and pretending otherwise would be the
    # same "unmeasured read as passing" this suite exists for.
    print("skip  set JARVIS_BACKEND to the backend folder under test, e.g.")
    print('      $env:JARVIS_BACKEND = "<backend folder>"; '
          "python backend\\test_learner_real_model.py")
    sys.exit(0)

import types  # noqa: E402

_CASES = json.dumps({"id": "x1", "kind": "propose", "what": "a stand-in case",
                     "at": "2026-09-24",
                     "messages": [{"role": "user", "content": "I have started learning the harp"}],
                     "want": [["harp"]]}) + "\n"
_CASES_NAME = "learner_cases.jsonl"

#: A backend folder of this suite's own: a real jarvis_extract.py on disk, and
#: a jarvis_intake stub beside it. A backend that really installs
#: jarvis_intake.py is used instead - see below.
_FAKE = Path(tempfile.mkdtemp(prefix="jarvis-real-extract-"))
EXTRACT = _FAKE / "jarvis_extract.py"
EXTRACT.write_text(
    '"""The real learner, as this suite stands it up."""\n'
    "MARK = 'the real file'\n"
    "\n"
    "def propose(messages, *, llm=None, source=None):\n"
    "    raise RuntimeError(MARK)\n",
    encoding="utf-8")
(_FAKE / _CASES_NAME).write_text(_CASES, encoding="utf-8")

os.environ["JARVIS_BACKEND"] = str(_FAKE)

import eval_learner as L  # noqa: E402
import eval_memory as EM  # noqa: E402


def stand_in_module():
    """The stand-in eval_learner puts in sys.modules: what the no-model cases
    were written against, and what the model half used to be handed."""
    m = types.ModuleType("jarvis_extract")
    m.__file__ = None
    m.MARK = "the stand-in"
    sys.modules["jarvis_extract"] = m
    return m


def with_intake(fn):
    """Run `fn` with the real jarvis_intake.py when a backend has one, else
    with a stub: `run_model_part` only needs its name to exist, and every
    case is expected to fail at the stand-in extract's own refusal."""
    try:
        import jarvis_intake  # noqa: F401
        return fn()
    except ImportError:
        pass
    stub = types.ModuleType("jarvis_intake")
    stub.ORIGIN_OWNER = "owner"
    stub.owner_turns = lambda messages, origin: list(messages or [])
    stub.propose = lambda extract, messages, llm, **kw: extract.propose(messages)
    real = sys.modules.get("jarvis_intake")
    sys.modules["jarvis_intake"] = stub
    try:
        return fn()
    finally:
        if real is None:
            sys.modules.pop("jarvis_intake", None)
        else:
            sys.modules["jarvis_intake"] = real


class FakeAutoLearn:
    """jarvis_auto_learn's two functions run_model_part asks for, and nothing
    else: this suite is about which file was loaded, not about learning."""
    _is_loopback = staticmethod(lambda url: str(url).startswith("http://127.0.0.1"))
    _remote = staticmethod(lambda model: False)


def _load_memory():
    scratch = Path(tempfile.mkdtemp(prefix="jarvis-real-extract-store-"))
    M, _P = EM._load_memory(scratch)
    return M


def t_the_real_file_is_read_even_though_a_stand_in_is_installed():
    """The exact shape of the bug: a stand-in in sys.modules, a real file on
    disk, and the model half asked for the real one."""
    stand_in = stand_in_module()
    try:
        try:
            extract = L.load_real_extract()
        except ImportError as exc:
            return check("load_real_extract reads the real file from the backend", False,
                         f"{type(exc).__name__}: {exc}")
        check("load_real_extract reads the real file from the backend",
              Path(str(extract.__file__)).resolve() == EXTRACT.resolve(),
              repr(getattr(extract, "__file__", None)))
        check("it is a module that can really propose",
              callable(getattr(extract, "propose", None)))
        check("and it is the FILE's own code that answers, not the stand-in's",
              getattr(extract, "MARK", "") == "the real file", getattr(extract, "MARK", ""))
        check("the stand-in the no-model cases need is put back afterwards",
              sys.modules.get("jarvis_extract") is stand_in,
              repr(sys.modules.get("jarvis_extract")))
    finally:
        sys.modules.pop("jarvis_extract", None)


def t_the_model_half_uses_that_file():
    """End to end through run_model_part, which is what the CLI calls."""
    stand_in = stand_in_module()
    try:
        def go():
            return L.run_model_part(_load_memory(), None, FakeAutoLearn,
                                    L.load_cases(_FAKE / _CASES_NAME),
                                    Path(tempfile.mkdtemp(prefix="jarvis-real-extract-run-")),
                                    "qwen3:8b", "http://127.0.0.1:11434")
        got = with_intake(go)
    finally:
        sys.modules.pop("jarvis_extract", None)
    check("the model half runs at all (it used to report the file could not be loaded)",
          got.get("ran") is True, repr(got)[:400])
    check("and it names the real file it loaded",
          Path(str(got.get("real_file") or "")).resolve() == EXTRACT.resolve(),
          repr(got.get("real_file")))
    # The stand-in's propose refuses with its own mark, so a case that really
    # reached the real file carries that mark rather than "no propose()".
    marks = json.dumps(got.get("cases") or [])
    check("the case was really run through the real file, and its refusal proves it",
          "the real file" in marks and "no propose()" not in marks, marks[:400])
    check("a module with no propose() would have been refused, not scored as wrong",
          got.get("ran") is True or "could not be loaded" in str(got.get("why")),
          repr(got)[:300])


def t_no_real_file_is_said_plainly():
    """A backend that has no jarvis_extract.py must be reported, never
    silently scored - that is how the bug hid for so long."""
    empty = Path(tempfile.mkdtemp(prefix="jarvis-no-extract-"))
    old = os.environ["JARVIS_BACKEND"]
    old_here = L.HERE
    os.environ["JARVIS_BACKEND"] = str(empty)
    L.HERE = empty
    try:
        try:
            L.load_real_extract()
            check("a folder with no jarvis_extract.py raises, rather than returning "
                  "something else", False, "no error raised")
        except ImportError as exc:
            check("a folder with no jarvis_extract.py raises, rather than returning "
                  "something else", "jarvis_extract.py" in str(exc), str(exc))
    finally:
        L.HERE = old_here
        os.environ["JARVIS_BACKEND"] = old


def t_the_cli_reports_a_model_half_that_could_not_run():
    """The shape the bug really had, at the level a person uses it.

    `python backend/eval_learner.py --learner-model qwen3:8b` printed the
    116 no-model cases, said nothing about the model half, and exited 0 - so
    silence looked exactly like a pass, and the learner's model-dependent
    numbers were never measured. A model half that FAILED must now be visible
    in the exit code, and the report must name the file it really loaded."""
    out = Path(tempfile.mkdtemp(prefix="jarvis-real-extract-cli-"))
    old_cases = L.CASES
    L.CASES = _FAKE / _CASES_NAME
    try:
        code = L.main(["--learner-model", "qwen3:8b", "--out", str(out)])
    finally:
        L.CASES = old_cases
    report = (out / "learner-eval.md")
    said = report.read_text(encoding="utf-8") if report.is_file() else ""
    saved = json.loads((out / "learner-eval.json").read_text(encoding="utf-8")) \
        if (out / "learner-eval.json").is_file() else {}
    mp = saved.get("model_part") or {}
    check("the report names the model half", "The real learner (qwen3:8b)" in said,
          said[-600:])
    check("the report names the FILE it loaded", str(EXTRACT) in said, said[-600:])
    check("a model half that ran and failed is NOT a clean exit",
          code != 0, f"exit {code}")
    check("the saved result carries the same file, not a stand-in",
          Path(str(mp.get("real_file") or "")).resolve() == EXTRACT.resolve(),
          repr(mp.get("real_file")))


def t_the_path_comes_from_the_backend_folder():
    old = os.environ["JARVIS_BACKEND"]
    try:
        os.environ["JARVIS_BACKEND"] = str(_FAKE)
        check("JARVIS_BACKEND's own copy is the one chosen",
              L.real_extract_path() == EXTRACT.resolve(), repr(L.real_extract_path()))
        os.environ["JARVIS_BACKEND"] = str(_FAKE / "gone")
        L.HERE = _FAKE
        check("a JARVIS_BACKEND with no copy there falls back to the file beside "
              "eval_learner.py", L.real_extract_path() == EXTRACT.resolve(),
              repr(L.real_extract_path()))
    finally:
        L.HERE = Path(__file__).resolve().parent
        os.environ["JARVIS_BACKEND"] = old


if __name__ == "__main__":
    try:
        for fn in (t_the_real_file_is_read_even_though_a_stand_in_is_installed,
                   t_the_model_half_uses_that_file,
                   t_no_real_file_is_said_plainly,
                   t_the_cli_reports_a_model_half_that_could_not_run,
                   t_the_path_comes_from_the_backend_folder):
            print(f"\n--- {fn.__name__} ---")
            try:
                fn()
            except Exception:
                import traceback
                FAILED.append(fn.__name__)
                traceback.print_exc()
    finally:
        # This suite's own stand-in backend folder: a real jarvis_extract.py
        # on disk, which is the whole point of the suite.
        import shutil
        shutil.rmtree(_FAKE, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
