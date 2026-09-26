"""The local chat lane talks to Ollama now, not to a program that was never running.

`/api/chat`'s completion request always went to `{JARVIS_URL}/v1/chat/completions`
- OpenJarvis's own port and API shape - whatever lane was chosen, local or
not. OpenJarvis was never actually installed as part of this setup, so every
local turn was one `_open()` call away from a 503 it could never recover
from. `ollama-direct.patch` adds `_completions_url(lane)`, which sends the
local lane to Ollama's own OpenAI-compatible endpoint instead, and leaves a
non-local lane going to JARVIS_URL exactly as before - unimplemented in
practice (there is no other cloud-lane transport in this codebase yet), but
that gap is not this patch's to invent an answer for.

This test executes the real `_completions_url`, lifted from the source with
ast - the same technique test_degrade_filter.py already uses on this exact
file, for this exact reason. It cannot start a real HTTP server or reach a
real Ollama; that part only the owner's own machine can prove.

    python3 test_ollama_direct.py
"""
import ast
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, missing, explain
SRC = BACKEND / "jarvis_hud.py"

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _completions_url_fn(source: str):
    """Lifts the real `_completions_url` function out of the source and
    returns it, callable, with OLLAMA_URL/JARVIS_URL bound to test values and
    `local_model` - a free variable, closed over from do_POST in the real
    code - bound the same way test_degrade_filter.py binds the loop's own
    free variables."""
    tree = ast.parse(source)
    found = [n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "_completions_url"]
    if len(found) != 1:
        raise AssertionError(f"expected exactly one _completions_url, found {len(found)}")
    ns = {"OLLAMA_URL": "http://127.0.0.1:11434",
          "JARVIS_URL": "http://127.0.0.1:8000",
          "local_model": "qwen3:8b"}
    exec(compile(ast.Module(body=[found[0]], type_ignores=[]), "<lifted>", "exec"), ns)
    return ns["_completions_url"]


def t_local_lane_goes_to_ollama():
    if missing("jarvis_hud.py"):
        return check("SKIP - " + explain(), True)
    fn = _completions_url_fn(SRC.read_text(encoding="utf-8"))
    check("the local lane resolves to Ollama's own endpoint",
          fn("qwen3:8b") == "http://127.0.0.1:11434/v1/chat/completions",
          fn("qwen3:8b"))


def t_a_non_local_lane_is_left_alone():
    if missing("jarvis_hud.py"):
        return check("SKIP - " + explain(), True)
    fn = _completions_url_fn(SRC.read_text(encoding="utf-8"))
    check("a cloud lane still resolves to JARVIS_URL - unimplemented, not silently redirected",
          fn("jarvis-escalate") == "http://127.0.0.1:8000/v1/chat/completions",
          fn("jarvis-escalate"))


def t_open_calls_the_new_function_not_the_old_literal():
    """The bug was `_open` hardcoding the URL inline. Confirm the fix is
    that `_open` now calls `_completions_url(lane)` - a literal string
    substitution done wrong (e.g. only in the function definition, not at
    the call site) would leave the original bug live with a decoy function
    sitting unused beside it."""
    if missing("jarvis_hud.py"):
        return check("SKIP - " + explain(), True)
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    opens = [n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "_open"]
    check("found the real _open", len(opens) == 1, f"found {len(opens)}")
    if len(opens) != 1:
        return
    body = ast.unparse(opens[0])
    check("_open calls _completions_url(lane)", "_completions_url(lane)" in body, body)
    check("_open no longer builds the URL from JARVIS_URL directly",
          "JARVIS_URL}/v1/chat/completions" not in body, body)


def t_the_error_message_names_the_right_service():
    """A local-lane failure has to say Ollama and how to start it, not blame
    a program that was never supposed to be running - that string is what a
    confused owner would actually go act on."""
    if missing("jarvis_hud.py"):
        return check("SKIP - " + explain(), True)
    src = SRC.read_text(encoding="utf-8")
    check("mentions Ollama's own start command for the local-lane failure",
          "ollama serve" in src, "expected the literal `ollama serve` advice somewhere")
    # The non-local branch keeps a message of its own, naming where it looked.
    # (It used to tell the owner to run `uv run jarvis serve`, a program this
    # setup never installs; chat-stream.patch replaced that sentence.)
    check("the non-local branch has its own message, naming JARVIS_URL",
          "{JARVIS_URL}" in src)
    check("the local-lane message is conditioned on lane == local_model, not unconditional",
          "if lane == local_model else" in src or "if lane == local_model\n" in src,
          "expected the ternary picking the message by lane")


if __name__ == "__main__":
    for fn in (t_local_lane_goes_to_ollama, t_a_non_local_lane_is_left_alone,
               t_open_calls_the_new_function_not_the_old_literal,
               t_the_error_message_names_the_right_service):
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
