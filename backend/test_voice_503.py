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


def t_each_route_answers_for_itself():
    """CONTROL. Reading speech and speaking text are opposite directions."""
    src = SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)

    calls = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_no_speech":
            kw = {k.arg: k.value for k in n.keywords}
            ok = kw.get("fallback_ok")
            calls.append((n.lineno, getattr(ok, "value", None)))
    check("every voice route routes through _no_speech", len(calls) == 4,
          f"found {len(calls)} call sites: {calls}")
    check("three of the four refuse a client fallback",
          sum(1 for _, v in calls if v is False) == 3, repr(calls))
    check("exactly one allows it - saying text the client already holds",
          sum(1 for _, v in calls if v is True) == 1, repr(calls))

    # The utterance route is the one that must never say yes.
    i = src.index('route == "/api/voice/utterance"')
    j = src.index('route == "/api/voice/say"')
    utt = src[i:j]
    check("the utterance route refuses local speech-to-text in words",
          "do NOT recognise this yourself" in utt,
          "a client that guessed would move the privacy boundary")
    check("and it does not offer a fallback", "fallback_ok=True" not in utt)


def t_nothing_returns_500_for_a_missing_module():
    """CONTROL on the regression."""
    src = SRC.read_text(encoding="utf-8")
    for route in ("/api/voice/utterance", "/api/voice/say"):
        i = src.index(f'route == "{route}"')
        seg = src[i:i + 2000]
        head = seg[:seg.index("_no_speech")] if "_no_speech" in seg else seg
        check(f"{route} reaches _no_speech before any 500",
              "_no_speech" in seg and "500" not in head,
              "a missing module still surfaces as a server error")
    i = src.index('route == "/api/voice/wake"')
    seg = src[i:i + 900]
    check("/api/voice/wake no longer imports without a guard",
          "try:" in seg[:seg.index("import jarvis_speech")][-40:],
          "the bare import is back")


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
