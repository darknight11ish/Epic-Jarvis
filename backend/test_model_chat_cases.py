"""The "can this model chat?" table both apps' Brain › Model reads is current.

    python3 test_model_chat_cases.py

Play tester, 2026-09-27: Brain › Model offered "Use" on nomic-embed-text, a
model that only serves memory search. Both apps now leave "Use" off such a
row and say "for memory search only - it cannot chat", by one rule held to
one table that tools/gen_model_chat_cases.py writes twice:

    jarvis-desktop/tests/fixtures/model-chat-cases.json
    jarvis-client/app/src/test/resources/contract/model-chat-cases.json

WHAT THIS PINS
  1. Both copies are exactly what the generator makes today, so a case added
     to the generator and never written out fails here, in CI.
  2. The case the play tester found is in the table, with the right answer.

Runs anywhere: standard library only, nothing of the owner's read.
"""
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def t_both_copies_are_current():
    import gen_model_chat_cases as G
    doc = G.document()
    for p in G.COPIES:
        have = p.read_text(encoding="utf-8").replace("\r\n", "\n") if p.exists() else ""
        check(f"{p.relative_to(G.ROOT)} matches (python3 tools/gen_model_chat_cases.py)",
              have == doc)


def t_the_case_the_rule_exists_for():
    import gen_model_chat_cases as G
    bare = {c["ref"]: c["chats"] for c in G.CASES if set(c) == {"ref", "chats"}}
    check("nomic-embed-text, a bare name, cannot chat", bare.get("nomic-embed-text") is False)
    check("qwen3:8b, a bare name, can chat", bare.get("qwen3:8b") is True)
    check("the words are one plain phrase", G.CANNOT_CHAT == "for memory search only - it cannot chat")


def main():
    for t in (t_both_copies_are_current, t_the_case_the_rule_exists_for):
        try:
            t()
        except Exception:
            FAILED.append(t.__name__)
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
