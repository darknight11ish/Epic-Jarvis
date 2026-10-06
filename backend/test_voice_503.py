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
SRC = BACKEND / "jarvis_hud.py"

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _lift():
    """The real _no_speech and _SAY_FALLBACK, executed in isolation."""
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
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
    src = SRC.read_text(encoding="utf-8")

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
    src = SRC.read_text(encoding="utf-8")
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
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
