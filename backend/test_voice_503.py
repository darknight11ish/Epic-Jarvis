"""Four routes, four different ways of saying "there is no speech module".

jarvis_speech.py does not exist on this machine, so every /api/voice/* route
is on its failure path right now - and they disagreed:

    /api/voice/status      200  {"available": false, "error": "ModuleNotFound..."}
    /api/voice/utterance   500  {"error": "ModuleNotFoundError"}
    /api/voice/say         500  {"error": "ModuleNotFoundError"}
    /api/voice/wake        the ImportError was not caught at all

A client asking "is the voice path up?" had to recognise all four. Worse, the
two 500s are the wrong answer: a 500 says the server broke, and nothing broke -
the module was never installed. That is a 503, which is the code the say
route's own no-engine branch already used, carrying a field that tells the
client whether speaking it itself is acceptable.

That field, `client_fallback_ok`, is the load-bearing part, and it is NOT the
same answer on every route. These tests hold that line.

WHERE THE CODE COMES FROM. `jarvis_hud.py` is the owner's file and is not in
this repository, so in CI this suite used to be skipped BY NAME and every
check in it ran only on the owner's PC (`backend/run_suites.py`'s NEEDS_OWNER
list). Two of its checks execute the code rather than read it - `_no_speech()`
itself, and the sentence `_SAY_FALLBACK` - and both of those are written
entirely by patches, so the whole patch stack's text for that file HAS them:
`_lift()` below takes them from the real file when this machine has one and
from the stand-in built by `backend/_stack.py` when it does not, one function
at a time. The route checks still need the whole file - the stand-in carries
the routes' own lines but not the `if route == "..."` that owns them, and
`ast.parse` cannot read it - so those are named as skips here and run on the
owner's PC (2026-10-10).

    python3 test_voice_503.py
"""
import ast, sys, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# BACKEND is where the modules under test actually live - this folder in
# the dev container, $JARVIS_BACKEND on a real install. REPO is this
# repository. They used to be the same path and are not on the machine
# that runs Jarvis.
from _where import BACKEND, REPO, missing, explain
HUD = BACKEND / "jarvis_hud.py"

FAILED, PASSED, SKIPPED = [], [], []

#: Why a check that reads a statement out of the WHOLE file cannot run here.
_WHOLE_FILE = ("jarvis_hud.py is not on this machine and this check reads a statement out of "
               "the whole file with ast; the patch stack's stand-in (backend/_stack.py) is "
               "fragments and cannot be parsed, so it still needs the owner's file")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    """A check this machine cannot run. Printed as `skip`, counted on its own,
    never as a pass - and the summary line at the end carries the number into
    backend/run_suites.py, which reports whole-suite and inside-suite skips
    separately."""
    SKIPPED.append(name)
    print(f"skip  {name} - {why}")


_STAND_IN = None


def _stack_text() -> str:
    """The whole patch stack's text for jarvis_hud.py, built once ("" when it
    cannot be built at all)."""
    global _STAND_IN
    if _STAND_IN is None:
        import _stack
        _STAND_IN = _stack.stand_in("jarvis_hud.py")[0] or ""
    return _STAND_IN


def _assignment_text(source: str, name: str):
    """One module-level `name = ...` and every line it spans, cut by lines.

    `_stack.function_text()` cuts a `def` out of the stand-in; `_SAY_FALLBACK`
    is a constant, and the stand-in is fragments, so ast cannot find it either.
    Brackets are counted, so a value written across several lines comes out
    whole - which is the shape both of them are written in."""
    lines = source.splitlines()
    starts = [i for i, l in enumerate(lines)
              if l.startswith(f"{name} =") or l.startswith(f"{name}=")]
    if len(starts) != 1:
        return None
    out, depth = [], 0
    for line in lines[starts[0]:]:
        out.append(line)
        depth += sum(line.count(c) for c in "([{") - sum(line.count(c) for c in ")]}")
        if depth <= 0:
            break
    return "\n".join(out) + "\n"


def _lift():
    """The real _no_speech and _SAY_FALLBACK, executed in isolation.

    The owner's jarvis_hud.py when this machine has one - the way this suite
    has always read it. Otherwise the patch stack's stand-in, one piece at a
    time: `_stack.function_text("_no_speech")` and `_assignment_text(
    "_SAY_FALLBACK")`, compiled together. Both are code the patches write
    outright, so the stand-in has them verbatim, and a missing piece is a
    failure rather than a skip - it means the stack no longer writes the
    helper these routes are built on."""
    if HUD.is_file():
        tree = ast.parse(HUD.read_text(encoding="utf-8"))
        body = [n for n in tree.body
                if (isinstance(n, ast.FunctionDef) and n.name == "_no_speech")
                or (isinstance(n, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "_SAY_FALLBACK" for t in n.targets))]
        names = {getattr(n, "name", None) or n.targets[0].id for n in body}
        if {"_no_speech", "_SAY_FALLBACK"} - names:
            raise AssertionError(f"missing from jarvis_hud.py: {sorted({'_no_speech','_SAY_FALLBACK'} - names)}")
        ns = {}
        exec(compile(ast.Module(body=body, type_ignores=[]), "<lifted>", "exec"), ns)
        return ns
    import _stack
    src = _stack_text()
    if not src:
        raise AssertionError("jarvis_hud.py is not here and the patch stack's stand-in for it "
                             "could not be built")
    pieces = {"_no_speech": _stack.function_text(src, "_no_speech"),
              "_SAY_FALLBACK": _assignment_text(src, "_SAY_FALLBACK")}
    gone = sorted(n for n, p in pieces.items() if p is None)
    if gone:
        raise AssertionError(f"missing from the patch stack's jarvis_hud.py: {gone}")
    ns = {}
    for name in ("_SAY_FALLBACK", "_no_speech"):
        exec(compile(pieces[name], f"<{name}, lifted from the patch stack>", "exec"), ns)
    return ns


def _whole_file():
    """The whole file's text, or None when only the owner's PC has it."""
    return HUD.read_text(encoding="utf-8") if HUD.is_file() else None


def t_the_shape():
    ns = _lift()
    code, payload = ns["_no_speech"](ModuleNotFoundError("No module named 'jarvis_speech'"),
                                     fallback_ok=True, reason="because")
    check("a missing module is 503, not 500", code == 503, f"got {code}")
    check("it says the module is missing rather than naming an exception",
          "not installed" in payload.get("error", ""), repr(payload.get("error")))
    check("the exception is still there, as detail",
          "ModuleNotFoundError" in payload.get("detail", ""), repr(payload.get("detail")))
    check("available is explicitly false", payload.get("available") is False)
    check("client_fallback_ok is a real boolean, not absent",
          payload.get("client_fallback_ok") is True, repr(payload))
    check("and it carries the reason", payload.get("reason") == "because")

    _, refused = ns["_no_speech"](ImportError("x"), fallback_ok=False, reason="no")
    check("fallback_ok=False survives into the body",
          refused.get("client_fallback_ok") is False, repr(refused))


def t_the_say_fallback_is_conditional():
    """The one sentence that matters to the phone."""
    ns = _lift()
    txt = ns["_SAY_FALLBACK"].lower()
    check("it says on-device", "on-device" in txt or "on device" in txt, txt)
    check("it names network synthesis as egress", "egress" in txt, txt)
    check("it says this reply is NOT permission for that",
          "not permission" in txt, txt)
    check("it names the actual Android check",
          "isnetworkconnectionrequired" in txt.replace(" ", ""), txt)


def _route_node(src, marker):
    """The innermost statement of jarvis_hud.py that `marker` is part of.

    The route checks below used to be `i = src.index(marker); src[i:i + 2000]`.
    A window like that is a promise about how many characters away the next
    route is; every edit above it moves the code the window was written for
    out of view, and the check then reads whatever slid in. The AST node
    travels with the edit.
    """
    off = src.find(marker)
    if off < 0:
        return None
    line = src.count("\n", 0, off) + 1
    best = None
    for n in ast.walk(ast.parse(src)):
        if not isinstance(n, ast.stmt):
            continue
        end = n.end_lineno or n.lineno
        if not (n.lineno <= line <= end):
            continue
        if best is None or (n.lineno, -end) > (best.lineno,
                                               -(best.end_lineno or best.lineno)):
            best = n
    return best


def _route_block(src, marker):
    """That statement's own source - what a fixed window used to hold."""
    node = _route_node(src, marker)
    return ast.get_source_segment(src, node) if node is not None else ""


def _voice_guards(src):
    """Every `/api/voice/...` route that answers "there is no speech module",
    with the `fallback_ok` it passes - read off the tree.

    The old check counted `_no_speech` calls in the file: exactly five, three
    with fallback_ok=False and two with True. A count says nothing about WHICH
    route got which answer - a sixth route added, or two routes swapping their
    flags, both had to be caught by hand (2026-10-03). This names them.
    """
    out = {}
    for n in ast.walk(ast.parse(src)):
        if not isinstance(n, ast.If):
            continue
        named = [c.value for c in ast.walk(n.test)
                 if isinstance(c, ast.Constant) and isinstance(c.value, str)
                 and c.value.startswith("/api/voice/")]
        if not named:
            continue
        for call in ast.walk(n):
            if isinstance(call, ast.Call) and getattr(call.func, "id", "") == "_no_speech":
                kw = {k.arg: k.value for k in call.keywords}
                if "fallback_ok" in kw:
                    out[named[0]] = getattr(kw["fallback_ok"], "value", None)
    return out


def _imports_of(src, name):
    """Every `import <name>` in the file, and whether a `try:` wraps it.

    The wake route's check used to read `src[i:i + 900]` for `try:` in the 40
    characters before the import. This asks the tree, so the guard is found
    wherever it sits and however the import is spelled.
    """
    found = []

    def walk(node, in_try):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Try):
                walk(child, True)
                continue
            if isinstance(child, ast.Import) and any(a.name == name
                                                     for a in child.names):
                found.append((child.lineno, in_try))
            walk(child, in_try)

    walk(ast.parse(src), False)
    return found


def t_each_route_answers_for_itself():
    """CONTROL. Reading speech and speaking text are opposite directions."""
    src = _whole_file()
    if src is None:
        for name in ("every voice route that can find no speech module says so through "
                     "_no_speech, with the right answer for its direction",
                     "the utterance route is still there to check",
                     "the utterance route refuses local speech-to-text in words",
                     "and it does not offer a fallback"):
            skip(name, _WHOLE_FILE)
        return

    # Which route may offer the client's own fallback is the whole point of
    # the field, so it is pinned per route rather than counted.
    want = {
        "/api/voice/wake": False,       # it listens
        "/api/voice/status": False,     # the read that says the path is down
        "/api/voice/utterance": False,  # it listens
        "/api/voice/say": True,         # it speaks text the client already holds
        "/api/voice/moment": True,      # same, the "One moment." clip
    }
    have = _voice_guards(src)
    check("every voice route that can find no speech module says so through "
          "_no_speech, with the right answer for its direction",
          have == want,
          f"missing {sorted(set(want) - set(have))}, "
          f"extra {sorted(set(have) - set(want))}, "
          f"wrong {[k for k in want if k in have and have[k] != want[k]]}")

    # The utterance route is the one that must never say yes.
    utt = _route_block(src, 'route == "/api/voice/utterance"')
    check("the utterance route is still there to check", bool(utt))
    check("the utterance route refuses local speech-to-text in words",
          "do NOT recognise this yourself" in utt,
          "a client that guessed would move the privacy boundary")
    check("and it does not offer a fallback", "fallback_ok=True" not in utt)


def t_nothing_returns_500_for_a_missing_module():
    """CONTROL on the regression."""
    src = _whole_file()
    if src is None:
        for route in ("/api/voice/utterance", "/api/voice/say"):
            skip(f"{route} is still there to check", _WHOLE_FILE)
            skip(f"{route} reaches _no_speech before any 500", _WHOLE_FILE)
        skip("/api/voice/wake no longer imports without a guard", _WHOLE_FILE)
        return
    for route in ("/api/voice/utterance", "/api/voice/say"):
        seg = _route_block(src, f'route == "{route}"')
        check(f"{route} is still there to check", bool(seg))
        head = seg[:seg.index("_no_speech")] if "_no_speech" in seg else seg
        check(f"{route} reaches _no_speech before any 500",
              "_no_speech" in seg and "500" not in head,
              "a missing module still surfaces as a server error")
    # Every import of jarvis_speech in the file must sit inside a try:, not
    # just the one the old 900-character window happened to reach.
    imports = _imports_of(src, "jarvis_speech")
    check("/api/voice/wake no longer imports without a guard",
          bool(imports) and all(guarded for _, guarded in imports),
          f"a bare `import jarvis_speech` is back, at "
          f"{[ln for ln, guarded in imports if not guarded]}")


if __name__ == "__main__":
    for fn in (t_the_shape, t_the_say_fallback_is_conditional,
               t_each_route_answers_for_itself, t_nothing_returns_500_for_a_missing_module):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    if SKIPPED:
        print(f"      ({len(SKIPPED)} check(s) read the whole of jarvis_hud.py, which only the "
              f"owner's PC has; they run there)")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
