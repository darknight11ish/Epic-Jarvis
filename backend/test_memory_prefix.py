"""The recalled-facts block used to be the first thing in the request.

`messages = [{"role": "system", ...recalled facts...}] + messages`

The facts are chosen per question, so that made token 0 of the request differ
on every turn. llama.cpp, and therefore Ollama, reuses a cached KV prefix only
up to the first token that differs - so a changing position 0 threw away the
cache for the entire conversation and re-prefilled all of it, every turn,
growing as the conversation grew.

The fix inserts the block just before the final user turn instead. These tests
execute the shipped ordering expression - lifted out of jarvis_hud.py with ast
rather than paraphrased here - and check the property that matters: everything
before the last turn is byte-identical across two turns that recall different
facts.

    python3 test_memory_prefix.py
"""
import ast, json, sys, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# BACKEND is where the modules under test actually live - this folder in
# the dev container, $JARVIS_BACKEND on a real install. REPO is this
# repository. They used to be the same path and are not on the machine
# that runs Jarvis.
from _where import BACKEND, REPO, missing, explain, require_shipped
SRC = BACKEND / "jarvis_hud.py"

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def _ordering():
    """The real `messages = ...` expression from the memory block.

    Found by shape, not by line number: the one assignment to `messages` whose
    right-hand side mentions `recalled`. Returns a function of
    (messages, recalled) that evaluates it.
    """
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "messages" for t in node.targets):
            continue
        names = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
        if "recalled" in names:
            found.append(node.value)
    if len(found) != 1:
        raise AssertionError(
            f"expected exactly one `messages = ...recalled...` assignment, found {len(found)}")
    code = compile(ast.Expression(found[0]), "<lifted>", "eval")
    return lambda messages, recalled: eval(code, {}, {"messages": messages, "recalled": recalled})


def _turn(n):
    return [{"role": "user", "content": f"question {i}"} for i in range(n)]


def t_the_prefix_survives_a_turn():
    place = _ordering()

    history = [{"role": "user", "content": "where does Mario live"},
               {"role": "assistant", "content": "at 42 Elm Street"},
               {"role": "user", "content": "and what is he allergic to"}]

    a = place(list(history), {"role": "system", "content": "recalled:\n- Mario lives at 42 Elm Street"})
    b = place(list(history), {"role": "system", "content": "recalled:\n- Mario is allergic to shellfish"})

    check("the block is in the request at all",
          any("recalled" in json.dumps(m) for m in a))

    # The property. Serialise each prefix the way a request would and compare.
    pa, pb = json.dumps(a[:-2]), json.dumps(b[:-2])
    check("two turns recalling different facts share an identical prefix",
          pa == pb and pa != "[]",
          f"prefix diverged:\n        {pa}\n        {pb}")

    check("everything from the original history is still there",
          all(m in a for m in history), "a turn was dropped")
    check("nothing was duplicated", len(a) == len(history) + 1, f"{len(a)} messages")

    # CONTROL. The old ordering fails the same property, so a test that passed
    # on both would be measuring nothing.
    oa = [{"role": "system", "content": "recalled:\n- A"}] + list(history)
    ob = [{"role": "system", "content": "recalled:\n- B"}] + list(history)
    check("CONTROL: the old prepend does NOT share a prefix",
          json.dumps(oa[:-2]) != json.dumps(ob[:-2]),
          "the control did not reproduce the bug - the property is not discriminating")


def t_the_facts_reach_the_question():
    place = _ordering()
    history = _turn(4)
    out = place(list(history), {"role": "system", "content": "recalled"})
    check("the last message is still the user's question",
          out[-1] == history[-1], f"last is {out[-1]}")
    check("the facts sit immediately before it", out[-2]["content"] == "recalled",
          "recalled facts should be adjacent to the question they were recalled for")


def t_edges():
    place = _ordering()
    r = {"role": "system", "content": "recalled"}
    out = place([], dict(r))
    check("an empty conversation does not raise and is not empty", out == [r], repr(out))
    one = [{"role": "user", "content": "hello"}]
    out = place(list(one), dict(r))
    check("a single-turn conversation keeps the turn and gains the block",
          out == [r, one[0]], repr(out))
    # That shape, [recalled, question], is this expression's output only. On
    # its own it would drop the Modelfile's SYSTEM block;
    # jarvis_agent.keep_rules_first() puts the rules back in front (see
    # t_the_first_question_keeps_the_rules).
    check("and the block comes first when there is nothing to prefix",
          out[0] is not one[0])


def t_it_is_not_prepended_anywhere():
    """CONTROL on the source. Fails if the block goes back to position 0."""
    src = SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "messages" for t in node.targets):
            continue
        v = node.value
        # `[<something>] + messages` is the shape of the bug.
        if (isinstance(v, ast.BinOp) and isinstance(v.op, ast.Add)
                and isinstance(v.left, ast.List)
                and isinstance(v.right, ast.Name) and v.right.id == "messages"):
            check("nothing is prepended to messages", False,
                  f"line {node.lineno}: a list is prepended, which moves token 0")
            return
    check("nothing is prepended to messages", True)


def t_the_persona_invariants_come_back():
    """The more serious half, and it is not about speed at all.

    ollama/server/routes.go:

        msgs := append(m.Messages, req.Messages...)
        if req.Messages[0].Role != "system" && m.System != "" {
            msgs = append([]api.Message{{Role: "system", Content: m.System}}, msgs...)

    A system message at index 0 suppresses the Modelfile's own SYSTEM block.
    Prepending the recalled facts therefore dropped jarvis_persona's
    INVARIANT_PROMPT - "say what is a guess and what is verified", "never
    claim an action was taken that was not" - on every local turn where recall
    fired, and only those turns. The invariants went missing at exactly the
    moment the model was holding the user's private facts.
    """
    place = _ordering()
    history = [{"role": "user", "content": "where does Mario live"},
               {"role": "assistant", "content": "at 42 Elm Street"},
               {"role": "user", "content": "and what is he allergic to"}]
    out = place(list(history), {"role": "system", "content": "recalled"})
    check("index 0 is not a system message, so the Modelfile SYSTEM applies",
          out[0].get("role") != "system",
          f"messages[0] is {out[0].get('role')!r} - ollama will skip m.System")

    # A client that sends its own leading system message: this expression
    # leaves it where the client put it. It does not decide whether the
    # rules go in front of it - jarvis_agent.keep_rules_first() does, and
    # since 2026-09-25 (the owner's decision) it always does; see
    # t_the_first_question_keeps_the_rules below.
    theirs = [{"role": "system", "content": "you are a pirate"}] + history
    out = place(list(theirs), {"role": "system", "content": "recalled"})
    check("a client's own leading system message is left where it put it",
          out[0] is theirs[0], repr(out[0]))


def t_the_first_question_keeps_the_rules():
    """The case the test above does not cover: the FIRST question.

    With no earlier turn, "just before the question" is index 0, so this
    expression gives [recalled, question] - a system message first, and
    Ollama then skips the Modelfile's SYSTEM block. jarvis_agent's
    keep_rules_first() runs last on every request to the local model and puts
    that block (LANE_SYSTEM, the Modelfile's SYSTEM word for word) in front.
    Checked here on the real placement feeding the real function, so either
    side changing shape shows up.
    """
    require_shipped("jarvis_agent.py")
    import jarvis_agent as AG
    place = _ordering()
    rules = {"role": "system", "content": AG.LANE_SYSTEM}
    r = {"role": "system", "content": "recalled"}

    q = {"role": "user", "content": "where does Mario live"}
    out = AG.keep_rules_first(place([q], dict(r)))
    check("a first question that recalled facts starts with the Jarvis rules",
          out == [rules, r, q], [m.get("content", "")[:30] for m in out])

    history = [{"role": "user", "content": "where does Mario live"},
               {"role": "assistant", "content": "at 42 Elm Street"},
               {"role": "user", "content": "and what is he allergic to"}]
    out = AG.keep_rules_first(place(list(history), dict(r)))
    check("a later question is left alone (Ollama adds the rules itself)",
          out[0] == history[0] and rules not in out, repr(out[0]))

    theirs = [{"role": "system", "content": "Context:\nsome copied text"}, q]
    out = AG.keep_rules_first(place(list(theirs), dict(r)))
    check("an app's own leading system message gets the rules in front of it",
          out == [rules] + theirs[:1] + [r, q],
          [m.get("content", "")[:30] for m in out])


def t_k_is_not_a_magic_number():
    src = SRC.read_text(encoding="utf-8")
    check("the recall width is a named constant", "MEMORY_K" in src,
          "k=5 was a token budget written where nobody would find it")
    check("and search uses it", "search(query, k=MEMORY_K)" in src)
    check("it still defaults to 5", '_int_env("JARVIS_MEMORY_K", 5)' in src,
          "the default must not change behaviour")
    check("a typo in the variable does not stop the server booting",
          "def _int_env" in src and "except (TypeError, ValueError)" in src,
          "int(os.environ[...]) at module scope raises before the import finishes")


if __name__ == "__main__":
    for fn in (t_the_prefix_survives_a_turn, t_the_facts_reach_the_question, t_edges,
               t_it_is_not_prepended_anywhere, t_the_persona_invariants_come_back,
               t_the_first_question_keeps_the_rules, t_k_is_not_a_magic_number):
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
