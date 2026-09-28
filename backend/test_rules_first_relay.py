"""The Jarvis rules stay first on a turn with no tools enabled, too.

    python3 test_rules_first_relay.py

Ollama puts the Modelfile's SYSTEM block (the Jarvis rules) in front only
when the first message is NOT a system message (ollama/server/routes.go).
Two things put a system message first on a conversation's first question:
memory-prefix.patch's recalled facts, and the desktop's attached clipboard
text. jarvis_agent.keep_rules_first() puts the rules back in front - but only
the tool loop called it. A turn with no tools enabled never reaches the tool
loop: jarvis_hud.py's relay sends `payload` straight to Ollama from _open()
(ollama-direct.patch), and on those turns the rules were still dropped.

rules-first-relay.patch makes _open() call the same function, for the local
model only. What this proves, with no file from the owner's PC:

  - the patch is last in apply-patches.ps1's list, after the patches whose
    lines it sits among, and its context is text chat-history.patch and
    cloud-one-turn.patch write - so it lands on the real file, not only on
    this stand-in;
  - it applies to the stand-in of jarvis_hud.py the whole stack before it
    leaves, and comes off again;
  - the lines it adds, run as they are: a first question with recalled facts
    gets the rules in front; a later question and a cloud lane are sent as
    they were; and if jarvis_agent cannot be loaded, nothing raises and the
    request goes as it did before.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import textwrap
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _stack  # noqa: E402
import jarvis_agent as AG  # noqa: E402

PATCH = "rules-first-relay.patch"
TARGET = "jarvis_hud.py"
FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def _patched():
    """(before, after) of jarvis_hud.py's stand-in around this patch, or
    (None, None) when it does not apply."""
    order = _stack.order()
    order = order[:order.index(PATCH)]
    text, log = _stack.stand_in(TARGET, order)
    if text is None:
        check(f"a stand-in of {TARGET} could be built", False, log)
        return None, None
    git = shutil.which("git")
    if not git:
        check("git is here to apply it", False)
        return None, None
    patch = (HERE / PATCH).read_text(encoding="utf-8")
    d = Path(tempfile.mkdtemp(prefix="jarvis-rules-first-relay-"))
    try:
        (d / TARGET).write_text(text, encoding="utf-8", newline="\n")
        one = "".join(h for h, _ in _stack.hunks(patch, TARGET))
        (d / "p.patch").write_text(f"--- a/{TARGET}\n+++ b/{TARGET}\n{one}",
                                   encoding="utf-8", newline="\n")
        r = subprocess.run([git, "apply", "p.patch"], cwd=d, capture_output=True, text=True)
        after = (d / TARGET).read_text(encoding="utf-8") if r.returncode == 0 else None
        r2 = subprocess.run([git, "apply", "-R", "p.patch"], cwd=d, capture_output=True,
                            text=True)
        back = (d / TARGET).read_text(encoding="utf-8") == text
        check(f"{TARGET}: applies to what the earlier patches wrote, and reverses",
              after is not None and r2.returncode == 0 and back, (r.stderr, r2.stderr))
        return text, after
    finally:
        shutil.rmtree(d, ignore_errors=True)


def t_its_place_in_the_stack():
    order = _stack.order()
    # Last when it was added; a patch added after it must leave its lines alone.
    check(f"{PATCH} is in apply-patches.ps1's list, and no later patch rewrites its lines",
          PATCH in order and not _stack.later_rewriting(PATCH, "keep_rules_first"), order[-3:])
    # brain-reads.patch (2026-09-28) and the projects -> support-chat chain
    # follow it. They patch other parts of jarvis_hud.py, so what matters is
    # that this comes after every patch whose lines it builds on (below),
    # that no later one touches _open(), and that the whole list applies,
    # which _stack proves.
    for later in order[order.index(PATCH) + 1:] if PATCH in order else []:
        text = (HERE / later).read_text(encoding="utf-8")
        check(f"{later}, after it, does not touch _open()",
              "def _open(" not in text and "_chat_client_fields_off" not in text)
    for earlier in ("ollama-direct.patch", "chat-history.patch", "cloud-one-turn.patch",
                    "memory-prefix.patch"):
        check(f"after {earlier}", earlier in order and order.index(earlier) < order.index(PATCH))
    patch = (HERE / PATCH).read_text(encoding="utf-8")
    check("it patches jarvis_hud.py and nothing else",
          sorted(l[6:].strip() for l in patch.splitlines() if l.startswith("+++ b/"))
          == [TARGET])
    # Its context must be text the stack itself writes, or it would apply
    # here (the stand-in adds any missing context) and fail on the PC.
    context = [l[1:] for l in patch.splitlines()
               if l.startswith(" ") and l.strip()]
    written = {l[1:] for name in ("chat-history.patch", "cloud-one-turn.patch")
               for l in (HERE / name).read_text(encoding="utf-8").splitlines()
               if l.startswith("+")}
    check("every context line is one chat-history.patch or cloud-one-turn.patch adds",
          context and all(c in written for c in context),
          [c for c in context if c not in written])


def _new_block(after: str) -> str:
    """The lines the patch adds, dedented so they run on their own."""
    patch = (HERE / PATCH).read_text(encoding="utf-8")
    added = [l[1:] for l in patch.splitlines()
             if l.startswith("+") and not l.startswith("+++")]
    block = "\n".join(added) + "\n"
    check("the added lines are in the patched file as one block", block in after)
    return textwrap.dedent(block)


def _run(block: str, lane: str, messages: list) -> dict:
    body = {"model": lane, "messages": [dict(m) for m in messages]}
    env = {"lane": lane, "local_model": "jarvis-primary", "body": body}
    exec(compile(block, PATCH, "exec"), env)
    return env["body"]


def t_what_it_does():
    before, after = _patched()
    if after is None:
        return
    check("CONTROL: before this patch, the relay never calls keep_rules_first",
          "keep_rules_first" not in before)
    block = _new_block(after)
    rules = {"role": "system", "content": AG.LANE_SYSTEM}
    recalled = {"role": "system", "content": "Things you know about the user ..."}
    q = {"role": "user", "content": "where does Mario live"}

    got = _run(block, "jarvis-primary", [recalled, q])["messages"]
    check("local model, first question with recalled facts: the rules go in front",
          got == [rules, recalled, q], [str(m["content"])[:30] for m in got])

    clip = {"role": "system", "content": "Context:\nsome copied text"}
    got = _run(block, "jarvis-primary", [clip, q])["messages"]
    check("local model, the desktop's clipboard message first: the rules go in front",
          got == [rules, clip, q], [str(m["content"])[:30] for m in got])

    later = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"},
             recalled, q]
    got = _run(block, "jarvis-primary", later)["messages"]
    check("local model, a later question: sent as it was (Ollama adds the rules)",
          got == later, [str(m["content"])[:30] for m in got])

    got = _run(block, "some-cloud-lane", [recalled, q])["messages"]
    check("a lane that is not the local model is not touched here",
          got == [recalled, q], [str(m["content"])[:30] for m in got])

    body = {"model": "jarvis-primary", "prompt": "no messages key"}
    env = {"lane": "jarvis-primary", "local_model": "jarvis-primary", "body": body}
    exec(compile(block, PATCH, "exec"), env)
    check("a body with no messages list is left alone", env["body"] == body)

    saved = sys.modules.get("jarvis_agent")
    sys.modules["jarvis_agent"] = None  # `import jarvis_agent` now raises
    try:
        got = _run(block, "jarvis-primary", [recalled, q])["messages"]
        check("jarvis_agent cannot be loaded: no error, the request goes as before",
              got == [recalled, q])
    except Exception as exc:
        check("jarvis_agent cannot be loaded: no error, the request goes as before",
              False, repr(exc))
    finally:
        sys.modules["jarvis_agent"] = saved


if __name__ == "__main__":
    for fn in (t_its_place_in_the_stack, t_what_it_does):
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
