"""One address resolver, and every shipped module asks it for the Ollama URL.

WHY THIS EXISTS

`OLLAMA_URL` names the lane the chat is on. On this PC it is
`http://127.0.0.1:11436` (the everyday lane), and the same machine runs other
lanes on other ports (`jarvis_presets.LANES`), so an address is not a constant
and not something to copy.

PR #1330 (merged 2026-11-16) made the address a *checked* value: one function,
`jarvis_models.ollama_url_on_this_pc()`, reads `OLLAMA_URL` and refuses a host
that is not this PC. But it routed only the three reads that commit touched
(`jarvis_models.OLLAMA`, `jarvis_extract.OLLAMA`, `jarvis_hud.OLLAMA_URL`), and
a review of that merge counted about fifteen shipped modules still reading the
variable - or Ollama's own `OLLAMA_HOST` - straight out of the environment.
This suite is the record of that sweep.

WHAT IT PROVES, AND WHY THAT IS NOT A GREP

  1. `t_the_published_base_has_one_resolver` reads EVERY Python file in
     `jarvis-backend/` - the published base - with `ast`, not by searching for
     a string, and lists every place an `os.environ` read of `OLLAMA_URL` or
     `OLLAMA_HOST` really happens. It requires exactly two, both NAMED: the
     helper's own read, and one deliberate exception
     (`jarvis_ollama_contract.py`, whose reason is written on EXCEPTIONS). A
     new direct read anywhere in the base fails this check.

  2. `t_every_changed_module_asks_the_helper` requires each changed module to
     have no direct read left AND to call `jarvis_models.ollama_url_on_this_pc()`
     inside the one function that resolves the address. Grepping for the name
     alone would pass on a module that calls it and ignores the answer; this
     walks the AST and names the function.

  3. `t_each_module_gets_the_lane_port_not_the_raw_environment` is the point.
     For every changed module it drives that module's own resolver four times:

       * `OLLAMA_URL=http://127.0.0.1:11436` -> 11436. The everyday lane's port,
         not Ollama's default. A module that hard-coded 11434 fails here.
       * the same with a trailing slash -> still 11436. The callers' own
         `.rstrip("/")` is kept; the bytes are today's.
       * `OLLAMA_URL=http://198.51.100.7:11434` (TEST-NET-2, not this PC) ->
         11434, with the helper's own refusal sentence on stderr. A module
         that still read the raw variable would return 198.51.100.7 here;
         returning this PC's loopback is what proves the helper is IN the path,
         not merely imported by it.
       * unset -> 11434, unchanged from before.

     The raw environment is read beside those answers, so the lane case and the
     refusal case cannot both pass by accident.

WHAT IT DOES NOT CLAIM

  * It starts no Ollama, opens no socket and asks no model: every resolver is
    called with its network seam blocked or with an early exit.
  * It does not re-check the helper's own rules - `test_gpu_offload.py` does
    that (unset, empty, loopback forms, the refusal line, one report per bad
    value); this suite would be a second copy of it.
  * It runs against `backend/` (or `JARVIS_BACKEND`), the copy a test exercises,
    and reads the published base for the whole-tree count. When `JARVIS_BACKEND`
    names an install, `require_shipped` refuses rather than testing a different
    copy.
"""
from __future__ import annotations

import ast
import contextlib
import io
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, require_shipped  # noqa: E402

#: The published base, which is the tree this repository asks about: the live
#: backend's own folder does not exist here, and the base is what an installer
#: starts from.
BASE_TREE = REPO / "jarvis-backend"

LANE = "http://127.0.0.1:11436"
REMOTE = "http://198.51.100.7:11434"
LOOPBACK = "http://127.0.0.1:11434"

#: module -> the function(s) that resolve the address for it. The helper call
#: has to be INSIDE one of them; a call that exists only in a comment, a
#: docstring or some other function does not count.
CHANGED = {
    "jarvis_agent.py": ("warm_everyday",),
    "jarvis_chatbot.py": ("_default_main_lane",),
    "jarvis_decision_lab.py": ("_loopback_url", "_lane"),
    "jarvis_hardware.py": ("_main_url",),
    "jarvis_live_photo_test.py": ("run",),
    "jarvis_model_lanes.py": ("_hud_ollama_url",),
    "jarvis_model_resources.py": ("_active_lane",),
    "jarvis_personality_creator.py": ("_hud_lane_url",),
    "jarvis_power_switch.py": ("__init__",),
    "jarvis_presets.py": ("_active_url",),
    "jarvis_quiz.py": ("_lane",),
    "jarvis_screen_picture.py": ("main_url",),
    "jarvis_second_card.py": ("_main_ollama_url",),
    "jarvis_self_improve.py": ("_loopback_url",),
    "jarvis_sensitive.py": ("learner_model",),
    "jarvis_thinking.py": ("_ollama_url",),
    "jarvis_work.py": ("_main_url",),
}

#: The one deliberate exception, named with its reason, so a second one has to
#: be argued for here rather than appearing quietly.
#:
#: `jarvis_ollama_contract.py`'s `default_url()` still reads `OLLAMA_HOST`.
#: `backend/test_ollama_contract.py` pins that module to the standard library
#: and nothing else ("the probe needs nothing but the standard library"): it is
#: the read-only probe used when Jarvis's picture of a model is in doubt, and
#: it must import even where the rest of the backend will not. Its one live
#: caller (`jarvis_self_improve.py`'s `/api/self-improve/contract`) already
#: passes the lane this suite covers, so the fallback is not the read that
#: decides a turn.
EXCEPTIONS = {"OLLAMA_URL": {"jarvis_models.py"},
              "OLLAMA_HOST": {"jarvis_ollama_contract.py"}}

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


#: The modules are imported once, from the copy this run tests. This happens
#: AFTER the shipped-copy guard, so a run against a live install refuses before
#: it imports anything instead of testing a different copy.
require_shipped(*sorted(CHANGED))
import jarvis_agent as J_AGENT  # noqa: E402
import jarvis_chatbot as J_CHATBOT  # noqa: E402
import jarvis_decision_lab as J_DECISION_LAB  # noqa: E402
import jarvis_hardware as J_HARDWARE  # noqa: E402
import jarvis_live_photo_test as J_LIVE_PHOTO  # noqa: E402
import jarvis_model_lanes as J_MODEL_LANES  # noqa: E402
import jarvis_model_resources as J_MODEL_RESOURCES  # noqa: E402
import jarvis_models as J_MODELS  # noqa: E402
import jarvis_personality_creator as J_PERSONALITY  # noqa: E402
import jarvis_power_switch as J_POWER_SWITCH  # noqa: E402
import jarvis_presets as J_PRESETS  # noqa: E402
import jarvis_quiz as J_QUIZ  # noqa: E402
import jarvis_screen_picture as J_SCREEN_PICTURE  # noqa: E402
import jarvis_second_card as J_SECOND_CARD  # noqa: E402
import jarvis_self_improve as J_SELF_IMPROVE  # noqa: E402
import jarvis_sensitive as J_SENSITIVE  # noqa: E402
import jarvis_thinking as J_THINKING  # noqa: E402
import jarvis_work as J_WORK  # noqa: E402


# --------------------------------------------------------------------------
#   Reading source the way Python reads it
# --------------------------------------------------------------------------

def _raw_reads(path: Path) -> list:
    """[(line, "OLLAMA_URL"|"OLLAMA_HOST", function)] for direct env reads.

    `ast`, not a string search: a comment, a docstring or a message that names
    the variable is not a read, and a read spelled `os.getenv(...)` or
    `os.environ[...]` still is."""
    import warnings
    with warnings.catch_warnings():
        # A module's own docstring may hold an invalid escape (a Windows path);
        # that is its business and not this suite's output.
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    stack: list = []

    class Walk(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            fn = node.func
            call = ""
            if isinstance(fn, ast.Attribute):
                base = fn.value
                if (isinstance(base, ast.Attribute) and isinstance(base.value, ast.Name)
                        and base.value.id == "os" and base.attr == "environ"):
                    call = "os.environ." + fn.attr
                elif isinstance(base, ast.Name) and base.id in ("os", "environ"):
                    call = base.id + "." + fn.attr
            if call in ("os.environ.get", "os.getenv", "environ.get"):
                if (node.args and isinstance(node.args[0], ast.Constant)
                        and node.args[0].value in EXCEPTIONS):
                    found.append((node.lineno, node.args[0].value,
                                  ".".join(stack[-2:])))
            self.generic_visit(node)

        def visit_Subscript(self, node):
            if (isinstance(node.value, ast.Attribute) and node.value.attr == "environ"
                    and isinstance(node.slice, ast.Constant)
                    and node.slice.value in EXCEPTIONS):
                found.append((node.lineno, node.slice.value, ".".join(stack[-2:])))
            self.generic_visit(node)

    Walk().visit(tree)
    return found


def _helper_calls_in(path: Path) -> dict:
    """{function: [line, ...]} for calls to `jarvis_models.ollama_url_on_this_pc()`."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(path.read_text(encoding="utf-8"))
    out: dict = {}
    stack: list = []

    class Walk(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            fn = node.func
            if (isinstance(fn, ast.Attribute) and fn.attr == "ollama_url_on_this_pc"
                    and isinstance(fn.value, ast.Name) and fn.value.id == "jarvis_models"):
                out.setdefault(stack[-1] if stack else "<module>", []).append(node.lineno)
            self.generic_visit(node)

    Walk().visit(tree)
    return out


# --------------------------------------------------------------------------
#   Driving each module's own resolver, with its network seam closed
# --------------------------------------------------------------------------

@contextlib.contextmanager
def ollama_url(value):
    """`OLLAMA_URL` set for the block; unset when `value` is None."""
    saved = os.environ.get("OLLAMA_URL")
    if value is None:
        os.environ.pop("OLLAMA_URL", None)
    else:
        os.environ["OLLAMA_URL"] = value
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("OLLAMA_URL", None)
        else:
            os.environ["OLLAMA_URL"] = saved


@contextlib.contextmanager
def without(*names):
    """`import name` raises for the block, as on a backend without it."""
    saved = {name: sys.modules.get(name) for name in names}
    for name in names:
        sys.modules[name] = None
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def _resolvers():
    """{module: callable returning the address it will talk to} - each one the
    module's OWN resolver, with the seam that would open a socket closed."""

    def agent():
        seen = []
        real_machine = J_AGENT._is_this_machine
        real_lane = J_PRESETS._persisted_lane_url
        J_AGENT._is_this_machine = lambda url: (seen.append(url), False)[1]
        J_PRESETS._persisted_lane_url = lambda: ""
        try:
            J_AGENT.warm_everyday(model="jarvis-primary")
        finally:
            J_AGENT._is_this_machine = real_machine
            J_PRESETS._persisted_lane_url = real_lane
        if not seen:
            raise AssertionError("warm_everyday did not reach its address check")
        return seen[0]

    def live_photo():
        seen = []
        real = J_MODELS.ollama_url_on_this_pc

        def answer(*args):
            got = real(*args)
            seen.append(got)
            return got

        J_MODELS.ollama_url_on_this_pc = answer
        folder = Path(tempfile.mkdtemp(prefix="jarvis-url-routing-"))
        try:
            with without("jarvis_second_card"):
                J_LIVE_PHOTO.run(candidates=[], folder=folder)
        finally:
            J_MODELS.ollama_url_on_this_pc = real
        if not seen:
            raise AssertionError("live_photo_test.run did not ask the helper")
        return seen[0]

    def model_lanes():
        with without("jarvis_hud"):
            return J_MODEL_LANES._hud_ollama_url()

    def personality():
        with without("jarvis_model_lanes"):
            return J_PERSONALITY._hud_lane_url()

    def sensitive():
        with without("jarvis_second_card", "jarvis_extract"):
            return J_SENSITIVE.learner_model()[0]

    def work():
        with without("jarvis_hardware"):
            return J_WORK._main_url()

    def model_resources():
        with tempfile.TemporaryDirectory(prefix="jarvis-url-routing-") as tmp:
            return J_MODEL_RESOURCES._active_lane(Path(tmp))["url"]

    return {
        "jarvis_agent.py": agent,
        "jarvis_chatbot.py": lambda: J_CHATBOT._default_main_lane()[0],
        "jarvis_decision_lab.py": lambda: J_DECISION_LAB._lane()[0],
        "jarvis_hardware.py": lambda: J_HARDWARE._main_url(),
        "jarvis_live_photo_test.py": live_photo,
        "jarvis_model_lanes.py": model_lanes,
        "jarvis_model_resources.py": model_resources,
        "jarvis_personality_creator.py": personality,
        "jarvis_power_switch.py": lambda: J_POWER_SWITCH.EverydayOllama().url,
        "jarvis_presets.py": lambda: J_PRESETS._active_url(),
        "jarvis_quiz.py": lambda: J_QUIZ._lane()[0],
        "jarvis_screen_picture.py": lambda: J_SCREEN_PICTURE.main_url(),
        "jarvis_second_card.py": lambda: J_SECOND_CARD._main_ollama_url(),
        "jarvis_self_improve.py": lambda: J_SELF_IMPROVE._loopback_url(),
        "jarvis_sensitive.py": sensitive,
        "jarvis_thinking.py": lambda: J_THINKING._ollama_url(),
        "jarvis_work.py": work,
    }


# --------------------------------------------------------------------------
#   1. The published base has one resolver and one named exception
# --------------------------------------------------------------------------

def t_the_published_base_has_one_resolver():
    """Every Python file in `jarvis-backend/`, read with `ast`.

    The count is the point: it was 20 environment reads of these two names in
    the base when the sweep started (19 outside the helper, in 18 modules), and
    it is 2 now - the helper, and the stdlib-only probe whose reason is written
    on EXCEPTIONS. Each is NAMED, so this check fails if a new read appears or
    if one of the two moves.
    """
    if not BASE_TREE.is_dir():
        check("the published base is here to read", False, str(BASE_TREE))
        return
    reads = {}
    for path in sorted(BASE_TREE.glob("*.py")):
        found = _raw_reads(path)
        if found:
            reads[path.name] = found
    for name, where in sorted(EXCEPTIONS.items()):
        got = {mod for mod, hits in reads.items()
               if any(hit[1] == name for hit in hits)}
        check(f"the only reader of {name} in the base is {', '.join(sorted(where))}",
              got == where, f"{name}: {sorted(got)}")
    total = sum(len(hits) for hits in reads.values())
    check("nothing else in the published base reads an Ollama address directly",
          total == sum(len(where) for where in EXCEPTIONS.values()),
          f"{total} raw read(s) in {sorted(reads)}")
    helper = [hit for hit in reads.get("jarvis_models.py", [])
              if hit[1] == "OLLAMA_URL"]
    check("the helper's own read is inside ollama_url_on_this_pc()",
          len(helper) == 1 and helper[0][2].endswith("ollama_url_on_this_pc"),
          helper)


# --------------------------------------------------------------------------
#   2. Every changed module asks the helper, in the function that resolves it
# --------------------------------------------------------------------------

def t_every_changed_module_asks_the_helper():
    for name, functions in sorted(CHANGED.items()):
        path = BACKEND / name
        if not path.is_file():
            check(f"{name} is in {BACKEND}", False, "the file is missing")
            continue
        reads = _raw_reads(path)
        check(f"{name} has no direct read of an Ollama address left",
              reads == [], reads)
        calls = _helper_calls_in(path)
        check(f"{name} calls jarvis_models.ollama_url_on_this_pc() in "
              f"{' / '.join(functions)}",
              any(fn in calls for fn in functions), calls)


# --------------------------------------------------------------------------
#   3. Each module gets the lane's port - and the refusal, not the raw value
# --------------------------------------------------------------------------

def t_each_module_gets_the_lane_port_not_the_raw_environment():
    resolvers = _resolvers()
    names = sorted(CHANGED)

    lane_seen = {}
    with ollama_url(LANE):
        for name in names:
            lane_seen[name] = resolvers[name]()
    check(f"with OLLAMA_URL at the everyday lane, all {len(names)} modules ask "
          f"{LANE}", all(url == LANE for url in lane_seen.values()),
          {n: u for n, u in lane_seen.items() if u != LANE})

    slash_seen = {}
    with ollama_url(LANE + "/"):
        for name in names:
            slash_seen[name] = resolvers[name]()
    check("... and the same lane with a trailing slash resolves to the same "
          "address (the callers that trim still do)",
          all(url.rstrip("/") == LANE for url in slash_seen.values()),
          {n: u for n, u in slash_seen.items() if u.rstrip("/") != LANE})

    refused = {}
    capture = io.StringIO()
    with ollama_url(REMOTE):
        check("... while the raw environment really does say another machine",
              os.environ.get("OLLAMA_URL") == REMOTE,
              os.environ.get("OLLAMA_URL"))
        with contextlib.redirect_stderr(capture):
            for name in names:
                refused[name] = resolvers[name]()
        said = capture.getvalue()
    check("... and a raw OLLAMA_URL on another machine is not what any of them uses",
          all(url == LOOPBACK for url in refused.values()),
          {n: u for n, u in refused.items() if u != LOOPBACK})
    check("... because the helper refused it, in its own sentence, not silently",
          "OLLAMA_URL" in said and "refused" in said and REMOTE in said, said)

    unset_seen = {}
    with ollama_url(None):
        for name in names:
            unset_seen[name] = resolvers[name]()
    check("with nothing set, every module asks Ollama's own loopback default",
          all(url == LOOPBACK for url in unset_seen.values()),
          {n: u for n, u in unset_seen.items() if u != LOOPBACK})


# --------------------------------------------------------------------------
#   4. The instruments themselves bite (a pin that cannot fail is no pin)
# --------------------------------------------------------------------------

def t_the_pins_can_fail():
    """Three small sources whose answer is known before they are read.

    The sweep above is only worth its green lines if `_raw_reads` really finds
    a direct read and `_helper_calls_in` really ties the call to its function;
    a reader that quietly matched nothing would pass every check above."""
    with tempfile.TemporaryDirectory(prefix="jarvis-url-pin-") as tmp:
        raw = Path(tmp) / "raw.py"
        raw.write_text('import os\n\n\ndef _active_url():\n'
                       '    return os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")\n',
                       encoding="utf-8")
        found = _raw_reads(raw)
        check("a direct read like the ones this sweep removed is found",
              len(found) == 1 and found[0][1] == "OLLAMA_URL"
              and found[0][2].endswith("_active_url"), found)
        check("... and the call pin does not mistake it for a routed module",
              "jarvis_models" not in raw.read_text(encoding="utf-8"),
              raw.read_text(encoding="utf-8"))

        wrong = Path(tmp) / "wrong_function.py"
        wrong.write_text(
            'def _other():\n'
            '    import jarvis_models\n'
            '    return jarvis_models.ollama_url_on_this_pc()\n\n\n'
            'def _active_url():\n'
            '    return "http://127.0.0.1:11434"\n',
            encoding="utf-8")
        calls = _helper_calls_in(wrong)
        check("a helper call in the WRONG function is not evidence for this one",
              "_other" in calls and "_active_url" not in calls, calls)
        check("... so a module that calls it and ignores it would be caught",
              not any(fn in calls for fn in ("_active_url",)), calls)

        good = Path(tmp) / "good.py"
        good.write_text('def _active_url():\n'
                        '    import jarvis_models\n'
                        '    return jarvis_models.ollama_url_on_this_pc()\n',
                        encoding="utf-8")
        check("... and the shape every changed module has IS accepted",
              "_active_url" in _helper_calls_in(good) and _raw_reads(good) == [],
              (_helper_calls_in(good), _raw_reads(good)))


# --------------------------------------------------------------------------

def main():
    for fn in (t_the_published_base_has_one_resolver,
               t_every_changed_module_asks_the_helper,
               t_each_module_gets_the_lane_port_not_the_raw_environment,
               t_the_pins_can_fail):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
