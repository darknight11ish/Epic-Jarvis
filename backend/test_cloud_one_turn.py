"""A cloud lane gets the newest question alone, never the conversation before it.

    python3 test_cloud_one_turn.py

The phone and the quickbar now send the conversation so far with every
question, the way the HUD page always did, so follow-ups are understood.
The cloud cut in /api/chat keeps every `role == "user"` turn - so without
this patch, an earlier private question could ride along on a later one
that was routed to a cloud lane. cloud-one-turn.patch cuts, inside `_open`,
every request to a lane that is not the local model down to the newest user
turn.

Four parts:
  1. The patch's context against what earlier patches wrote - git.
  2. The lines the patch adds, run on real-shaped requests.
  3. apply-patches.ps1 lists it, after ollama-direct.patch.
  4. The patched jarvis_hud.py - only where it exists (the owner's PC).

No network: nothing here opens a socket.
"""
import ast
import sys
import textwrap
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, missing, explain  # noqa: E402
import _skeleton  # noqa: E402

PATCH = "cloud-one-turn.patch"
SRC = BACKEND / "jarvis_hud.py"
FAILED, PASSED = [], []
LOCAL = "qwen3:8b"
PRIVATE = "my salary is 91,000 and my bank is Nordea"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _added() -> str:
    """The lines the patch adds, as they would sit inside `_open`."""
    lines = [l[1:] for l in (HERE / PATCH).read_text(encoding="utf-8").splitlines()
             if l.startswith("+") and not l.startswith("+++")]
    return "\n".join(lines)


def _open_body():
    """`_open`'s first line, the patch's lines, and a return of what would
    be sent - so the test runs the patch's own text, not a copy of it."""
    src = ("def run(lane, local_model, payload):\n"
           "    body = dict(payload); body[\"model\"] = lane\n"
           + textwrap.indent(textwrap.dedent(_added()), "    ") + "\n"
           "    return body\n")
    ns = {}
    exec(compile(src, "<cloud-one-turn>", "exec"), {"isinstance": isinstance, "dict": dict}, ns)
    return ns["run"]


RUN = _open_body()

# What a client now sends: the conversation, then the new question. The
# second turn is what the degrade loop's local rebuild restores, with the
# recalled-facts block memory-prefix.patch puts before the last user turn.
CONVERSATION = [
    {"role": "user", "content": PRIVATE + " - can I afford a new car?"},
    {"role": "assistant", "content": "On 91,000, a modest one, yes."},
    {"role": "system", "content": "Things you know about the user:\n- banks with Nordea"},
    {"role": "user", "content": "explain in detail how electric and hybrid cars compare "
                                "on running costs, step by step"},
]


def t_the_patch_context():
    ok, out = _skeleton.rehearse(PATCH, "ollama-direct.patch", "tool-calling-wiring.patch",
                                 "speed-record.patch", "feedback.patch")
    if ok is None:
        return check("SKIP - " + out, True)
    check("cloud-one-turn.patch applies to what ollama-direct (and the patches after it) wrote",
          ok is True, out)
    if ok:
        check("and it lands inside _open, above the request",
              out.index("said[-1:]") < out.index("_completions_url(lane),"))


def t_a_cloud_lane_gets_the_newest_question_only():
    payload = {"model": LOCAL, "messages": list(CONVERSATION), "stream": True}
    body = RUN("jarvis-escalate", LOCAL, payload)
    msgs = body["messages"]
    check("one message, and it is the newest question",
          msgs == [CONVERSATION[-1]], repr(msgs))
    sent = repr(body)
    check("the earlier private question is not in the request", PRIVATE not in sent)
    check("nor the recalled facts, nor the assistant's restatement",
          "Nordea" not in sent and "91,000" not in sent)
    check("the lane is still the one asked for", body["model"] == "jarvis-escalate")
    check("the caller's payload is left alone (a later local hop still has it all)",
          payload["messages"] == CONVERSATION)


def t_the_local_lane_is_untouched():
    payload = {"model": LOCAL, "messages": list(CONVERSATION), "stream": True}
    body = RUN(LOCAL, LOCAL, payload)
    check("the local model gets the whole conversation", body["messages"] == CONVERSATION)
    check("and the very same list, not a copy", body["messages"] is payload["messages"])


def t_awkward_shapes():
    image_turn = {"role": "user", "content": [
        {"type": "text", "text": "what is this?"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]}
    body = RUN("jarvis-vision", LOCAL, {"messages": [
        {"role": "user", "content": PRIVATE}, {"role": "assistant", "content": "ok"}, image_turn]})
    check("a screenshot turn goes whole, image and all", body["messages"] == [image_turn])
    body = RUN("jarvis-escalate", LOCAL, {"messages": [{"role": "system", "content": "x"}]})
    check("no user turn at all sends none - never a system or assistant one instead",
          body["messages"] == [], repr(body["messages"]))
    body = RUN("jarvis-escalate", LOCAL, {"messages": None})
    check("a missing list does not raise", body["messages"] == [])
    body = RUN("jarvis-escalate", LOCAL, {"messages": ["junk", 3, {"role": "user", "content": "q"}]})
    check("junk entries are skipped", body["messages"] == [{"role": "user", "content": "q"}])


def t_the_script_lists_it():
    ps = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    listed = f"'{PATCH}'" in ps
    check("apply-patches.ps1 applies it", listed)
    if listed:
        check("after ollama-direct.patch, whose lines are its context",
              ps.index("'ollama-direct.patch'") < ps.index(f"'{PATCH}'"))


def t_the_real_file():
    if missing("jarvis_hud.py"):
        return check("SKIP - " + explain(), True)
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    fns = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_open"]
    if not fns:
        return check("jarvis_hud.py has an _open", False)
    text = ast.unparse(fns[0])
    if "said[-1:]" not in text:
        return check("cloud-one-turn.patch is applied to jarvis_hud.py", False,
                     "run scripts/apply-patches.ps1 first")
    check("_open cuts a non-local lane to the newest user turn",
          "lane != local_model" in text and "said[-1:]" in text)


if __name__ == "__main__":
    for fn in (t_the_patch_context, t_a_cloud_lane_gets_the_newest_question_only,
               t_the_local_lane_is_untouched, t_awkward_shapes, t_the_script_lists_it,
               t_the_real_file):
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
