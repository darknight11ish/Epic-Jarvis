"""test_games_temp_chat.py - games and role-play run in a temporary chat
automatically.

    python3 backend/test_games_temp_chat.py

The owner's decision, 2026-09-27 (CLAUDE.md; docs/OWNER-QUESTIONS-2026-09-27.md
Q19): "Games and role-play run in a temporary chat automatically" - the
recommended option, chosen over leaving it to the owner to switch on
temporary chat by hand. The problem it solves: "Jarvis learns automatically
by default" (CLAUDE.md, 2026-09-24), so a game or role-play session -
invented characters, made-up scenarios - could get mistakenly learned as
real facts about the owner.

Built as two things, both proved here:

  1. `jarvis_intake.game_or_roleplay(messages)` - the one place that decides
     "is this conversation a game", matched on the owner's own words only
     (no model, no network), like `schedule_command()` next to it. Wired
     into `owner_turns()`, so the learner (and jarvis's own
     eval_learner.py, and any other direct caller) never reads a game's
     words - the same file test_memory_intake.py already tests
     `owner_turns()` and `schedule_command()` in.
  2. `games-temporary.patch` - `jarvis_hud.py`'s own `_temporary_chat(body)`
     (temporary-chat.patch, 2026-09-25) now ALSO returns true for a
     detected game, and the two places in the chat turn's `finally` block
     that used to read `body.get("temporary")` directly now go through
     that same function - so a detected game is put through the *exact*
     same gate a manually-started temporary chat already uses: no recall,
     no "Remember:", not kept in chat history, not learned from. No card,
     no setting - it just happens, the same way "From now on, ..." applies
     at once (CLAUDE.md).

Proved against the whole patch stack's stand-in for jarvis_hud.py
(backend/_stack.py) - its lines lifted and run - the same technique
test_temporary_chat.py and test_auto_learn.py already use. No pytest, no
network, no model. Every check here fails on the code before this change:
`game_or_roleplay()`, `games-temporary.patch` and the `owner_turns()` wiring
did not exist.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import textwrap
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_intake.py")
import jarvis_intake as I  # noqa: E402
import _stack  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def mk(*texts, role="user"):
    return [{"role": role, "content": t} for t in texts]


# ==========================================================================
#   1. game_or_roleplay() itself
# ==========================================================================

def t_true_cases():
    cases = [
        "let's play a game where you're a grumpy wizard",
        "let's roleplay, you are a pirate captain",
        "let's start a role-play",
        "pretend you're a medieval knight",
        "pretend to be my old chemistry teacher",
        "I want you to act as a customer support agent",
        "act as if you are a talking cat",
        "can we do a text adventure",
        "shall we play a text adventure",
        "be my dungeon master for a one-shot",
        "be my DM tonight",
        "run a D&D campaign for me",
        "run a dnd campaign",
        "you are now a character named Zorp",
        "in character as Sherlock Holmes, what do you see",
        "roleplaying as a space captain, what's our next move",
        "choose your own adventure please",
        "let's play dungeons and dragons",
    ]
    for text in cases:
        check(f"detected: {text!r}", I.game_or_roleplay(mk(text)))


def t_false_cases():
    cases = [
        "what is the weather today",
        "Remember: my sister is Dana",
        "I am playing a game of chess with my dad tonight",
        "my kid loves role-playing games at school",
        "set a timer for 10 minutes",
        "act normal please, I'm in a hurry",
        "I used to be a teacher",
        "",
    ]
    for text in cases:
        check(f"not a game: {text!r}", not I.game_or_roleplay(mk(text)))
    check("no messages at all", not I.game_or_roleplay([]))
    check("None instead of a list", not I.game_or_roleplay(None))


def t_only_the_owners_own_words_count():
    convo = mk("what's the weather", role="assistant")
    convo += [{"role": "assistant",
               "content": "let's roleplay, I'll be a wizard and you a knight"}]
    check("the model's own words never turn this on",
          not I.game_or_roleplay(convo))
    check("a non-string content is ignored, not an error",
          not I.game_or_roleplay([{"role": "user", "content": [{"type": "text"}]}]))
    check("a message that is not a dict is ignored, not an error",
          not I.game_or_roleplay(["not a dict"]))


def t_once_started_the_whole_conversation_counts():
    convo = (mk("what is the weather", "ok thanks")
             + [{"role": "assistant", "content": "sunny and mild"}]
             + mk("let's roleplay, you're a knight", "I attack the dragon",
                  "what happens next"))
    check("a game started three turns ago is still a game now",
          I.game_or_roleplay(convo))
    check("the two turns before the game started still read as a game, on "
          "purpose - a played conversation is not un-learned turn by turn",
          I.game_or_roleplay(convo[:1]) is False
          and I.game_or_roleplay(convo) is True)


# ==========================================================================
#   2. owner_turns() - the learner never reads a game's words
# ==========================================================================

def t_owner_turns_excludes_the_whole_conversation():
    convo = mk("what is the weather", "ok thanks",
               "let's roleplay, you're a knight", "I attack the dragon with my sword")
    got = I.owner_turns(convo, "owner")
    check("nothing from a game conversation reaches the learner",
          got == [], got)
    ordinary = mk("my sister lives in Porto", "I moved to Leeds last week")
    got2 = [m["content"] for m in I.owner_turns(ordinary, "owner")]
    check("an ordinary conversation is unaffected",
          got2 == ["my sister lives in Porto", "I moved to Leeds last week"], got2)


def t_still_needs_origin_owner():
    convo = mk("let's roleplay, you're a knight")
    for origin in ("unknown", "jarvis", None, "owner "):
        check(f"origin={origin!r}: nothing either way (not owner)",
              I.owner_turns(convo, origin) == [])
    check("origin='owner': the game check applies",
          I.owner_turns(convo, "owner") == [])


def t_combines_with_the_other_exclusions():
    """A schedule command and a "Remember:" inside an otherwise ordinary
    conversation are still skipped, game or not - the checks are additive,
    not a replacement for each other."""
    convo = mk("remind me to call Mum at 6", "Remember: I take my coffee black",
               "my sister lives in Porto")
    got = [m["content"] for m in I.owner_turns(convo, "owner")]
    check("without a game: schedule and Remember are still skipped",
          got == ["my sister lives in Porto"], got)
    convo2 = convo + ["let's roleplay, you're a knight"]
    convo2 = convo[:1] + [{"role": "user", "content": "let's roleplay, you're a knight"}] + convo[1:]
    check("with a game anywhere in it: nothing at all, not even the ordinary line",
          I.owner_turns(convo2, "owner") == [])


# ==========================================================================
#   3. games-temporary.patch - the request-level gate
# ==========================================================================

def _hud():
    src, log = _stack.stand_in("jarvis_hud.py")
    check("the whole jarvis_hud.py stack builds, games-temporary.patch included",
          src is not None and "def _temporary_chat(body)" in src
          and "jarvis_intake.game_or_roleplay" in src,
          "\n".join(log or [])[-600:])
    check("every games-temporary hunk found its context in the stack (none made up)",
          not any("games-temporary" in line for line in log or []), log)
    return src


def _temporary_chat_fn(src):
    ns: dict = {}
    exec(compile(_stack.function_text(src, "_temporary_chat"), "<_temporary_chat>", "exec"), ns)
    return ns["_temporary_chat"]


def t_temporary_chat_detects_a_game():
    src = _hud()
    if src is None:
        return
    fn = _temporary_chat_fn(src)
    check("the app's own temporary flag still works, as before",
          fn({"temporary": True}) is True)
    check("a plain question is not temporary",
          fn({"messages": mk("what is the weather")}) is False)
    check("a detected game is temporary too, with no flag set",
          fn({"messages": mk("let's roleplay, you're a knight")}) is True)
    check("not a dict: false, not an error", fn("nonsense") is False)
    check("no messages key at all: false, not an error", fn({}) is False)
    real = sys.modules.get("jarvis_intake")
    sys.modules["jarvis_intake"] = None                      # the import fails
    try:
        check("without jarvis_intake.py: not detected, exactly as before this patch",
              fn({"messages": mk("let's roleplay, you're a knight")}) is False)
    finally:
        if real is None:
            sys.modules.pop("jarvis_intake", None)
        else:
            sys.modules["jarvis_intake"] = real


def _finally_snippet(src):
    frag = _stack.fragment_with(src, "jarvis_chat_log.record_turn(")
    a = next(i for i, line in enumerate(frag) if line.strip() == '_activity("idle")')
    b = max(i for i, line in enumerate(frag) if line.strip() == "pass") + 1
    return textwrap.dedent("\n".join(frag[a:b]))


def _run_finally(snippet, body, temporary_chat_fn):
    offered, recorded = [], []
    stub = types.ModuleType("jarvis_chat_log")
    stub.record_turn = lambda b, **kw: recorded.append(b)
    real = sys.modules.get("jarvis_chat_log")
    sys.modules["jarvis_chat_log"] = stub
    try:
        env = {"_activity": lambda *a: None, "MEMORY": True, "jarvis_side_memory": False,
               "LEARNER": types.SimpleNamespace(
                   offer=lambda m, origin="unknown", **kw: offered.append(m)),
               "_temporary_chat": temporary_chat_fn,
               "body": body, "route_header": {"lane": "qwen3:8b"}, "lane": "qwen3:8b",
               "_history": {"turn": {"answer": "hi"}, "at": 1.0}}
        exec(snippet, env)
    finally:
        if real is None:
            sys.modules.pop("jarvis_chat_log", None)
        else:
            sys.modules["jarvis_chat_log"] = real
    return offered, recorded


def t_a_detected_game_is_never_kept_or_learned_from():
    src = _hud()
    if src is None:
        return
    fn = _temporary_chat_fn(src)
    snippet = _finally_snippet(src)
    msg = mk("let's roleplay, you're a knight", "I attack the dragon with my sword")
    body = {"messages": msg, "conversation_id": "conv-game-1"}
    offered, recorded = _run_finally(snippet, body, fn)
    check("a detected game is never offered to the learner",
          offered == [], offered)
    check("and never recorded in chat history either",
          recorded == [], recorded)
    ordinary = mk("what is the weather", "I moved to Leeds last week")
    body2 = {"messages": ordinary, "conversation_id": "conv-ordinary-2"}
    offered2, recorded2 = _run_finally(snippet, body2, fn)
    check("an ordinary chat is unaffected: recorded and offered as before",
          len(recorded2) == 1 and offered2 == [ordinary], (offered2, recorded2))


def t_listed_and_applies():
    import _where
    order = _stack.order()
    check("games-temporary.patch is in apply-patches.ps1's order, after temporary-chat.patch",
          "games-temporary.patch" in order
          and order.index("games-temporary.patch") > order.index("temporary-chat.patch"),
          order[-3:])
    check("the module that does the detection is shipped whole",
          "jarvis_intake.py" in _where.SHIPPED)
    git = shutil.which("git")
    if not git:
        return check("SKIP - git is not installed", True)
    at = order.index("games-temporary.patch")
    text, _ = _stack.stand_in("jarvis_hud.py", order[:at])
    check("jarvis_hud.py: the stack before games-temporary.patch builds", text is not None)
    if text is None:
        return
    d = Path(tempfile.mkdtemp(prefix="jarvis-games-temp-patch-"))
    try:
        (d / "jarvis_hud.py").write_text(text, encoding="utf-8", newline="\n")
        (d / "p.patch").write_bytes((HERE / "games-temporary.patch").read_bytes()
                                    .replace(b"\r\n", b"\n"))
        for extra in (["--check"], [], ["--check", "--reverse"], ["--reverse"], []):
            r = subprocess.run([git, "apply", *extra, "p.patch"], cwd=d, capture_output=True,
                               text=True)
            check(f"git apply {' '.join(extra) or '(forwards)'} games-temporary.patch",
                  r.returncode == 0, r.stderr.strip())
        full = _stack.stand_in("jarvis_hud.py", order[:at + 1])[0]
        check("forwards gives the stack's own text",
              (d / "jarvis_hud.py").read_text(encoding="utf-8") == full)
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
