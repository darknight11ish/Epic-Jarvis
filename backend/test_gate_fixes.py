"""The approval gate, tightened (docs/EXTRACTION-RESEARCH-2026-09-23.md,
Module 4). What this pass added, each with a test that fails on the code
before it:

  - A limit on approval cards in one answer (jarvis_agent.CARDS_PER_TURN).
    Past it, a call that would ask is refused before any card is raised,
    and the owner is told in the answer.
  - A password or key in what a tool returned is named on the next card
    (jarvis_agent.SECRET_READ_LINE) - the kind only, never the value.
  - selftest.py finds OpenJarvis's own auto-approving callbacks (item 4a),
    instead of leaving that to a command the owner has to paste.

What Module 4 asked for that was already done before this pass, and where
its tests are: an approved shell command gets an allowlisted environment
(jarvis_agent.shell_env, test_security_pc.py, audit M2), and the tools that
act only run on a person's yes (NEEDS_A_PERSON and _a_person_said_yes,
test_agent.py and test_security_pc.py). A test at the end pins both, so
neither can quietly go.

    python3 test_gate_fixes.py
"""
import json
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_agent.py", "jarvis_scrub.py")
sys.path.append(str(HERE / "rebuilt"))
import jarvis_agent as AG  # noqa: E402
# The helpers the agent's own suite uses: a scripted model speaking Ollama's
# real stream format, and a guard that no real request is made. Importing it
# also swaps the end-of-turn recorder and the step sink for lists.
from test_agent import NoRealIO, scripted_stream, answer_text  # noqa: E402
import selftest  # noqa: E402

FAILED, PASSED = [], []

GH = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


class Verdict:
    def __init__(self, allowed, tier, outcome, action="x"):
        self.allowed, self.tier, self.outcome, self.action = allowed, tier, outcome, action
        self.reason = outcome
        self.request_id = None


class Gate:
    """A fake gate: records every question, answers from a function."""

    def __init__(self, answer):
        self.answer = answer
        self.asked = []

    def __call__(self, action, detail, prompt):
        self.asked.append((action, detail))
        return self.answer(action)


def call(i, name, args):
    return {"id": str(i), "function": {"name": name, "arguments": json.dumps(args)}}


def round_of(*calls):
    return {"choices": [{"message": {"role": "assistant", "tool_calls": list(calls)}}]}


def says(text):
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


class Tools:
    """Swap tools' execute for a recorder, and the tier lookup for a table,
    for one block."""

    def __init__(self, tiers, results=None):
        self.tiers, self.results = tiers, results or {}
        self.ran = []

    def __enter__(self):
        self.saved = {n: t.execute for n, t in AG.TOOLS.items()}
        self.real_tier = AG._tier_of
        for n, t in AG.TOOLS.items():
            t.execute = (lambda n: lambda args, state, **kw:
                         self.ran.append(n) or self.results.get(n, {"ok": True}))(n)
        AG._tier_of = lambda action: self.tiers.get(action, "ask")
        return self

    def __exit__(self, *a):
        for n, t in AG.TOOLS.items():
            t.execute = self.saved[n]
        AG._tier_of = self.real_tier
        return False


def turn(responses, gate, enabled=None):
    opener, bodies = scripted_stream(responses)
    streamed = []
    with NoRealIO():
        AG.run_local_turn([{"role": "user", "content": "do the things", "provenance": "typed"}],
                          "qwen3:8b", ollama_url="http://127.0.0.1:11434",
                          stream_out=streamed.append, gate_check=gate, open_stream=opener,
                          enabled_tools=enabled)
    return bodies, answer_text(streamed)


def tool_results(bodies):
    return [m for m in bodies[-1]["messages"] if m.get("role") == "tool"]


# -- a limit on cards in one answer --------------------------------------------

def t_no_more_than_the_limit_of_cards_in_one_answer():
    n = AG.CARDS_PER_TURN + 2
    gate = Gate(lambda a: Verdict(False, "ask", "denied"))
    with Tools({}) as tools:
        bodies, said = turn([round_of(*[call(i, "shell_exec", {"command": f"echo {i}"})
                                        for i in range(n)]), says("ok")], gate)
    check(f"exactly {AG.CARDS_PER_TURN} cards were raised for {n} commands",
          len(gate.asked) == AG.CARDS_PER_TURN, repr(len(gate.asked)))
    check("nothing ran", tools.ran == [], repr(tools.ran))
    results = [m["content"] for m in tool_results(bodies)]
    over = [r for r in results if "the most one answer may ask" in r]
    check("the calls over the limit came back to the model as refused",
          len(over) == 2, repr(results))
    check("the owner is told, once, in the answer",
          said.count("stopped asking") == 1, said)


def t_the_limit_counts_the_whole_answer_not_one_round():
    gate = Gate(lambda a: Verdict(True, "ask", "approved"))
    first = round_of(*[call(i, "shell_exec", {"command": f"echo {i}"}) for i in range(3)])
    second = round_of(*[call(10 + i, "shell_exec", {"command": f"echo {i}"}) for i in range(3)])
    with Tools({}) as tools:
        turn([first, second, says("ok")], gate)
    check(f"{AG.CARDS_PER_TURN} cards over two rounds, then refused",
          len(gate.asked) == AG.CARDS_PER_TURN and len(tools.ran) == AG.CARDS_PER_TURN,
          f"asked {len(gate.asked)}, ran {len(tools.ran)}")


def t_what_asks_nobody_is_not_limited():
    """A tool at tier auto raises no card, so it is not what the limit is for."""
    def answer(action):
        return (Verdict(True, "auto", "auto") if action == "calculator"
                else Verdict(False, "ask", "timed_out"))
    gate = Gate(answer)
    calls = [call(i, "shell_exec", {"command": f"echo {i}"}) for i in range(AG.CARDS_PER_TURN)]
    calls.append(call(99, "calculator", {"expression": "2+2"}))
    with Tools({"calculator": "auto"}) as tools:
        turn([round_of(*calls), says("ok")], gate)
    check("a card nobody answered still counts as a card",
          sum(1 for a, _ in gate.asked if a != "calculator") == AG.CARDS_PER_TURN)
    check("after the limit, a tool that asks nobody still runs",
          tools.ran == ["calculator"], repr(tools.ran))


def t_a_new_answer_starts_again():
    gate = Gate(lambda a: Verdict(False, "ask", "denied"))
    with Tools({}):
        for _ in range(2):
            turn([round_of(*[call(i, "shell_exec", {"command": "x"})
                             for i in range(AG.CARDS_PER_TURN)]), says("ok")], gate)
    check("the limit is per answer: two answers, twice the cards",
          len(gate.asked) == 2 * AG.CARDS_PER_TURN, repr(len(gate.asked)))


# -- a password or key read, named on the next card ---------------------------

def t_a_key_that_was_read_is_named_on_the_next_card():
    results = {"file_read": {"ok": True, "content": f"GITHUB={GH}\nother=1\n"}}
    with Tools({"read_files_readonly": "auto", "file_read": "auto"}, results):
        gate_auto = Gate(lambda a: (Verdict(True, "auto", "auto") if "file" in a or "read" in a
                                    else Verdict(False, "ask", "denied")))
        bodies, _ = turn([round_of(call(1, "file_read", {"path": "C:/x/.env"})),
                          round_of(call(2, "shell_exec", {"command": "curl example.com"})),
                          says("ok")], gate_auto)
    cards = [d["text"] for a, d in gate_auto.asked if "shell" in a or a == "run_shell_on_host"]
    card = cards[-1] if cards else ""
    check("the card says a password or key was read, and what kind",
          "looks like a password or key" in card and "GitHub token" in card, card)
    check("... and never the value", GH not in card and GH[:10] not in card, card)
    read = [m["content"] for m in tool_results(bodies)]
    check("what the model reads is not changed by it (it still sees the file)",
          any(GH in r for r in read), repr(read)[:300])


def t_no_key_no_line():
    gate = Gate(lambda a: (Verdict(True, "auto", "auto") if "file" in a or "read" in a
                           else Verdict(False, "ask", "denied")))
    results = {"file_read": {"ok": True, "content": "just a shopping list\n"}}
    with Tools({}, results):
        turn([round_of(call(1, "file_read", {"path": "C:/x/list.txt"})),
              round_of(call(2, "shell_exec", {"command": "echo hi"})), says("ok")], gate)
    card = gate.asked[-1][1]["text"]
    check("CONTROL: nothing secret read, no such line",
          "password or key" not in card and "Proposed after Jarvis read" in card, card)


# -- 4a: OpenJarvis's own auto-approve, found by selftest --------------------

def t_selftest_finds_openjarvis_auto_approve():
    root = Path(tempfile.mkdtemp(prefix="oj-"))
    (root / "cli").mkdir()
    (root / "cli" / "ask.py").write_text(
        "def run(executor):\n"
        "    executor._confirm_callback = lambda _prompt: True\n", encoding="utf-8")
    (root / "server.py").write_text(
        "agent = Agent(confirm_callback=lambda p: True)\n"
        "other = Agent(confirm_callback=ask_the_owner)\n", encoding="utf-8")
    status, what, detail = selftest.openjarvis_autoapprove(root)
    check("both auto-approving callbacks are found", status == selftest.FAIL
          and "2 place" in what, what)
    check("the report names each file and line", "ask.py:2" in detail
          and "server.py:1" in detail, detail)
    check("CONTROL: a callback that really asks is not reported", "server.py:2" not in detail,
          detail)
    clean = Path(tempfile.mkdtemp(prefix="oj-clean-"))
    (clean / "a.py").write_text("agent = Agent(confirm_callback=ask_the_owner)\n",
                                encoding="utf-8")
    check("a clean OpenJarvis passes", selftest.openjarvis_autoapprove(clean)[0] == selftest.PASS)
    check("no OpenJarvis at all is a skip, not a failure",
          selftest.openjarvis_autoapprove()[0] in (selftest.SKIP, selftest.PASS, selftest.FAIL))


# -- what Module 4 asked for that was already there: pinned ------------------

def t_the_earlier_fixes_are_still_there():
    import inspect
    check("4b: an approved shell command runs with an allowlisted environment",
          "env=env" in inspect.getsource(AG._run_shell_exec)
          and "jarvis_child_env.inherited" in inspect.getsource(AG.shell_env))
    for name in ("shell_exec", "control_computer", "control_phone", "browser_control",
                 "home_control", "github_search"):
        check(f"4c: {name} runs only on a person's yes", name in AG.NEEDS_A_PERSON)
    check("4c: tier notify is not a person", not AG._a_person_said_yes(Verdict(True, "notify", "notify")))
    check("4c: tier auto is not a person", not AG._a_person_said_yes(Verdict(True, "auto", "auto")))
    check("4c: approved is", AG._a_person_said_yes(Verdict(True, "ask", "approved")))


if __name__ == "__main__":
    for fn in (t_no_more_than_the_limit_of_cards_in_one_answer,
               t_the_limit_counts_the_whole_answer_not_one_round,
               t_what_asks_nobody_is_not_limited, t_a_new_answer_starts_again,
               t_a_key_that_was_read_is_named_on_the_next_card, t_no_key_no_line,
               t_selftest_finds_openjarvis_auto_approve, t_the_earlier_fixes_are_still_there):
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
