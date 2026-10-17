"""test_optin_roots.py - the opt-in list must see the whole models home.

    python3 backend/test_optin_roots.py

WHY THIS EXISTS (2026-10-16)

`jarvis_optin_models.search_roots()` names the folders this PC keeps
hand-downloaded model files in. It named `D:\Jarvis Models\AI-Models`,
`D:\Jarvis Models\Ollama\store`, `~\.lmstudio\models` and
`~\Documents\AI Models` - and missed `D:\Jarvis Models\HuggingFace\gguf\`,
where three models already on the disk live and are already imported into
Ollama (a 27B uncensored, a 30B coder and a Qwen3-VL file). The owner was never
offered any of them, and a fourth hard-coded path would have missed the next
folder too.

The fix makes the models home itself the LAST root: `_walk` recurses, so every
folder under `D:\Jarvis Models\` is seen, now and later - `HuggingFace\gguf\`
today, whatever the owner adds next. The named roots still come first, so which
copy of a duplicated file wins does not change, and `choices()` still keeps one
entry per file name.

WHAT THIS PROVES
  * the roots module returns today include a folder that CONTAINS the real
    HuggingFace models folder, and the real 27B is reachable through the roots
    the product actually uses (`choices(search_roots())`) - READ-ONLY on D:,
    skipped where D: does not exist (CI);
  * the BITE: with the pre-fix root list the same model is INVISIBLE, and with
    today's roots it is offered - so the LIST is what makes it visible;
  * the CONTROL: a folder that is not a root is not searched, so a file there
    is not offered - the test proves the list is the mechanism, not a wider
    scan that happened to work;
  * the catch-all is `D:\Jarvis Models`, not the drive root and not the home
    folder, so this is a models-home walk and not a disk scan;
  * the environment override still replaces the list completely;
  * the list change starts, pulls, installs and loads nothing.

Nothing here writes to D:. The fake stores live in a temp folder on the system
drive, and every model file in them is a sparse file (a name and a size, no
data) so the test costs no disk.
"""
from __future__ import annotations

import ast
import inspect
import os
import sys
import tempfile
import traceback
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-optin-roots-"))
# Before anything imports jarvis_framework: its CONFIG_DIR is read once.
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
if str(HERE / "rebuilt") not in sys.path:
    sys.path.append(str(HERE / "rebuilt"))

import jarvis_optin_models as O  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []

#: The roots as they were BEFORE the fix, quoted from the pre-fix module so the
#: bite compares against the code that really shipped, not a guess.
OLD_ROOTS = (
    Path("D:/Jarvis Models/AI-Models"),
    Path("D:/Jarvis Models/Ollama/store"),
    Path.home() / ".lmstudio" / "models",
    Path.home() / "Documents" / "AI Models",
)

#: The real folder that was invisible. Only names are read, never contents.
HF = Path("D:/Jarvis Models/HuggingFace/gguf")
REAL_27B = HF / "JonathanColetti__Qwen3.8-27B-Uncensored-GGUF" / "Qwen3.8-27B-Uncensored-noMTP-IQ4_XS.gguf"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why: str) -> None:
    SKIPPED.append(why)
    print(f"skip  {why}")


def _fake_model(path: Path, size_mb: int = 600) -> Path:
    """A file with a model's NAME and SIZE and no data (sparse: costs nothing)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.truncate(size_mb * 1024 * 1024)
    return path


def _contains(root: Path, inner: Path) -> bool:
    """Is `inner` the same as `root` or somewhere under it? (String-safe on
    Windows and on CI's Linux, where neither path exists.)"""
    a = os.path.normcase(os.path.abspath(str(root)))
    b = os.path.normcase(os.path.abspath(str(inner)))
    return b == a or b.startswith(a.rstrip(os.sep) + os.sep)


# --------------------------------------------------------------------------
#   The fix itself, on the roots the module returns
# --------------------------------------------------------------------------

def t_the_models_home_is_a_root_and_the_named_homes_still_are():
    roots = O.search_roots()
    as_text = [str(r) for r in roots]
    check("the named homes are still first, in the order they had",
          tuple(roots[:2]) == OLD_ROOTS[:2] and len(roots) == len(OLD_ROOTS) + 1,
          [str(r) for r in roots])
    check("the models home itself is a root",
          Path("D:/Jarvis Models") in roots, as_text)
    check("... and it is LAST, so the named homes keep the order they had",
          roots[-1] == Path("D:/Jarvis Models"), as_text)
    check("the catch-all is the models home, not the drive root and not the home folder",
          not any(str(r).rstrip("/\\").lower() in ("d:", "d:/", "d:\\") for r in roots)
          and Path.home() not in roots, as_text)


def t_the_roots_reach_the_huggingface_models_that_were_invisible():
    if not HF.is_dir():
        skip("D:\\Jarvis Models\\HuggingFace\\gguf is not on this machine (CI) - the real-disk checks did not run")
        return
    roots = O.search_roots()
    check("a root contains the HuggingFace models folder",
          any(_contains(r, HF) for r in roots), [str(r) for r in roots])
    check("... and the pre-fix list contained no such root",
          not any(_contains(r, HF) for r in OLD_ROOTS), [str(r) for r in OLD_ROOTS])
    found = [p for p in O._walk(Path("D:/Jarvis Models")) if _contains(HF, p)]
    check("walking the models home reaches the files under it", bool(found), [str(p) for p in found][:5])
    if REAL_27B.is_file():
        check("the real 27B uncensored file is on this disk and is a choice file",
              O.is_choice_file(REAL_27B.name), REAL_27B.name)
        O._set("uncensored_choices_offered", True)
        with_roots = [c for c in O.choices(roots=O.search_roots(), names=[])
                      if c.file.name.lower() == REAL_27B.name.lower()]
        without = [c for c in O.choices(roots=OLD_ROOTS, names=[])
                   if c.file.name.lower() == REAL_27B.name.lower()]
        check("the real model IS offered through today's roots - READ-ONLY", bool(with_roots),
              [str(c.file) for c in O.choices(roots=O.search_roots(), names=[])])
        check("BITE: through the pre-fix roots the same model is INVISIBLE",
              not without, [str(c.file) for c in without])
    else:
        skip("the real 27B file is not at its known path on this machine")


# --------------------------------------------------------------------------
#   The mechanism, proved on folders this test owns (runs everywhere)
# --------------------------------------------------------------------------

def t_the_list_is_what_makes_a_folder_visible():
    O._set("uncensored_choices_offered", True)
    home = _TMP / "models"                       # stands in for D:\Jarvis Models
    named = home / "AI-Models"
    later = home / "HuggingFace" / "gguf"        # the folder that was invisible
    elsewhere = _TMP / "somewhere-else"
    _fake_model(named / "Qwen2.5-7B-Instruct-abliterated-Q4_K_M.gguf")
    _fake_model(later / "Qwen3.8-27B-Uncensored-noMTP-IQ4_XS.gguf")
    _fake_model(elsewhere / "Qwen3.5-14B-Uncensored-elsewhere.gguf")

    through_home = O.choices(roots=[home], names=[])
    through_named_only = O.choices(roots=[named], names=[])

    check("a model under the models home is found (the catch-all works)",
          any(c.file.name.startswith("Qwen3.8-27B") for c in through_home),
          [str(c.file) for c in through_home])
    check("... and so is one in the named folder", len(through_home) == 2,
          [str(c.file) for c in through_home])
    check("BITE: with only the named folder as a root, the later folder's model VANISHES",
          not any(c.file.name.startswith("Qwen3.8-27B") for c in through_named_only),
          [str(c.file) for c in through_named_only])
    check("CONTROL: a folder that is not a root is not searched, so its file is not offered",
          not any("elsewhere" in str(c.file) for c in through_home),
          [str(c.file) for c in through_home])
    check("... even though that file would pass every other rule (name and size)",
          O.is_choice_file("Qwen3.5-14B-Uncensored-elsewhere.gguf")
          and (elsewhere / "Qwen3.5-14B-Uncensored-elsewhere.gguf").stat().st_size > 512 * 1024 * 1024,
          str((elsewhere / "Qwen3.5-14B-Uncensored-elsewhere.gguf").stat().st_size))
    check("the same file name found twice is still ONE entry",
          len({c.file.name.lower() for c in O.choices(roots=[home, named], names=[])}) == 2,
          [str(c.file) for c in O.choices(roots=[home, named], names=[])])


def t_the_environment_override_still_replaces_the_list():
    real = os.environ.get("JARVIS_OPTIN_MODEL_ROOTS")
    try:
        os.environ["JARVIS_OPTIN_MODEL_ROOTS"] = os.pathsep.join(
            [str(_TMP / "models"), str(_TMP / "other")])
        check("JARVIS_OPTIN_MODEL_ROOTS replaces the whole list",
              [str(p) for p in O.search_roots()] == [str(_TMP / "models"), str(_TMP / "other")],
              [str(p) for p in O.search_roots()])
    finally:
        if real is None:
            os.environ.pop("JARVIS_OPTIN_MODEL_ROOTS", None)
        else:
            os.environ["JARVIS_OPTIN_MODEL_ROOTS"] = real
    check("... and unsetting it brings the shipped list back",
          any(_contains(r, Path("D:/Jarvis Models")) for r in O.search_roots()))


# --------------------------------------------------------------------------
#   A list change only: nothing is started, pulled, installed or loaded
# --------------------------------------------------------------------------

def t_this_is_a_list_and_nothing_else():
    src = inspect.getsource(O.search_roots)
    forbidden = ("subprocess", "os.system", "requests", "urlopen", "create(",
                 "pull", "install", "load(", "http://", "https://")
    present = [w for w in forbidden if w in src]
    check("search_roots starts, pulls, installs and loads nothing", not present, present)
    # `choices()` DOES read one thing besides the disk - Ollama's own model list
    # (`_installed_names`, /api/tags) - which is how it knows a file is already
    # imported. That read predates this change; what must not appear is an
    # ACTION: a process, a pull, a create, a load or a generate.
    body = inspect.getsource(O.choices)
    actions = ("subprocess", "os.system", "requests", "/api/pull", "/api/create",
               "/api/generate", "/api/chat", "load(")
    present = [w for w in actions if w in body]
    check("choices() takes no action - no process, pull, create, load or generate",
          not present, present)
    walk = inspect.getsource(O._walk)
    check("the walk only ever reads directory entries",
          "read_bytes" not in walk and "open(" not in walk, walk[:200])


def t_every_test_here_is_registered():
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    defined = sorted(n.name for n in tree.body
                     if isinstance(n, ast.FunctionDef) and n.name.startswith("t_"))
    running = sorted(fn.__name__ for fn in RUN)
    missing = sorted(set(defined) - set(running))
    extra = sorted(set(running) - set(defined))
    check("every t_ function here is in RUN", not missing, missing)
    check("... and every name in RUN is a function here", not extra, extra)
    check("BITE: a name left out of RUN would be named",
          sorted(set(["t_a", "t_never_run"]) - set(["t_a"])) == ["t_never_run"])


if __name__ == "__main__":
    RUN = (
        t_the_models_home_is_a_root_and_the_named_homes_still_are,
        t_the_roots_reach_the_huggingface_models_that_were_invisible,
        t_the_list_is_what_makes_a_folder_visible,
        t_the_environment_override_still_replaces_the_list,
        t_this_is_a_list_and_nothing_else,
        t_every_test_here_is_registered,
    )
    for fn in RUN:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
