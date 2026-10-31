"""test_send_file_chat.py - the chat door for the built send-one-file feature.

    python -B backend/test_send_file_chat.py

THE OWNER'S ASK, measured live (2026-10-31): the feature is built and
`/api/files/send` answers, but `send_file_to_phone` is a MODEL tool and is not
in the shipped [tools].enabled - so typing "find the file send-me.txt in my
Documents and send it to my phone" reached no card and answered that Jarvis
could not send the file. This suite pins the deterministic chat path:

1. THE SHAPES. "send me the file X", "send X to my phone", "send the file X to
   my phone", "find the file X and send it to my phone" and "send me X from my
   Downloads/Documents/Desktop" all resolve to `send_file`, and the runner calls
   `jarvis_send_file.prepare()` - the module's own search, exactly once.
2. ONE MATCH -> THE MODULE'S OWN CARD. The card's prompt is the module's own
   `prepare()` sentence (exact name, folder, byte size, 10 MiB cap, ten
   minutes, once), raised under the module's own action; nothing is approved by
   this path - only an approved verdict reaches the module's own `approve()`.
3. REFUSALS ARE THE MODULE'S WORDS, WITH NO CARD. No match, several matches,
   over the cap and a file outside the listed folders return the module's own
   `ValueError` sentence unchanged, and no card and no approve happen.
4. OVER-CAPTURE. "send me a message", "send an email to Sam" and "send my
   regards" stay the model's; the to-do path still works; the private-chat
   refusal is unchanged.

No model, no network, no real folders: `jarvis_send_file._folders` is pointed
at a temp directory for the length of each test.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-send-file-chat-"))
for _name in ("OPENJARVIS_CONFIG_DIR", "OPENJARVIS_HOME", "JARVIS_HOME"):
    os.environ.setdefault(_name, str(_TMP / _name.lower()))

import jarvis_quick as Q  # noqa: E402
import jarvis_send_file as SEND  # noqa: E402

FAILED, PASSED = [], []
NOW = time.mktime(time.strptime("2026-10-31 14:05:00", "%Y-%m-%d %H:%M:%S"))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name
          + (f"\n        {detail}" if detail and not cond else ""))


class _Sched:
    """The few scheduler calls answer() makes, doing nothing."""

    def mark_command(self, text):
        return None

    def note_set(self, *a, **k):
        return None

    def forget_set(self, *a, **k):
        return None


class _Verdict:
    """A gate verdict; defaults fail-closed like jarvis_gate.Verdict."""

    def __init__(self, allowed=False):
        self.allowed = bool(allowed)
        self.tier = "ask"
        self.action = SEND.ACTION
        self.reason = "test"
        self.outcome = "approved" if self.allowed else "refused"


def _root():
    return Path(tempfile.mkdtemp(prefix="send-file-chat-"))


def _folders(root):
    old = SEND._folders
    SEND._folders = lambda: [root]
    return old


def _module_refusal(query, root):
    """The module's own sentence for a query that cannot produce one file."""
    old = _folders(root)
    try:
        SEND.prepare({"query": query})
    except ValueError as exc:
        return str(exc)
    finally:
        SEND._folders = old
    return None


def _call(intent, root, *, verdict=None, tier="ask", gate=None):
    """Run the runner on `intent` with the real module and a fake card."""
    old_folders = _folders(root)
    real_prepare = SEND.prepare
    prepares = []
    cards = []

    def spy(args):
        prepares.append(dict(args))
        out = real_prepare(args)
        cards.append(out[1])
        return out

    gate_calls = []

    def fake_gate(action, detail, prompt):
        gate_calls.append({"action": action, "detail": detail, "prompt": prompt})
        return _Verdict(True) if verdict is None else verdict

    approves = []
    old_approve = SEND.approve

    def spy_approve(state):
        approves.append(dict(state or {}))
        return {"ok": True}

    SEND.approve = spy_approve
    try:
        res = Q._run_send_file_chat(intent.f, prepare=spy, gate=gate or fake_gate,
                                    tier_of=lambda _a: tier, spawn=lambda fn: fn())
    finally:
        SEND.approve = old_approve
        SEND._folders = old_folders
    return res, prepares, cards, gate_calls, approves


def _intent(phrase):
    got = Q.match(phrase, NOW)
    check(f"{phrase!r} is the send-file fast path",
          got is not None and got.name == "send_file", got)
    return got


# --------------------------------------------------------------------------
#   1. the shapes: the module's own prepare() runs, once, with the name
# --------------------------------------------------------------------------
def t_every_shape_calls_the_modules_own_prepare():
    root = _root()
    (root / "send-me.txt").write_text("hello", encoding="utf-8")
    shapes = {
        "send me the file send-me.txt": "send-me.txt",
        "send send-me.txt to my phone": "send-me.txt",
        "send the file send-me.txt to my phone": "send-me.txt",
        "find the file send-me.txt and send it to my phone": "send-me.txt",
        "send me send-me.txt from my Downloads": "send-me.txt",
        "send me the file send-me.txt from my Documents": "send-me.txt",
        "send me the file send-me.txt from my Downloads to my phone": "send-me.txt",
    }
    for phrase, query in shapes.items():
        got = _intent(phrase)
        if got is None:
            continue
        res, prepares, cards, gate_calls, approves = _call(got, root)
        check(f"{phrase!r}: prepare() called once with the name",
              prepares == [{"query": query}], prepares)
        check(f"{phrase!r}: the module's own card sentence is the prompt",
              len(gate_calls) == 1 and gate_calls[0]["prompt"] == cards[0],
              gate_calls[:1])
        check(f"{phrase!r}: the card shows the exact name, cap and window",
              cards and cards[0].startswith('Send "send-me.txt" from ')
              and "10 MiB" in cards[0] and "10 minutes" in cards[0]
              and "works once" in cards[0], cards[:1])
        check(f"{phrase!r}: raised under the module's own action",
              len(gate_calls) == 1 and gate_calls[0]["action"] == SEND.ACTION
              and gate_calls[0]["detail"] == {"text": cards[0]}, gate_calls[:1])
        check(f"{phrase!r}: the answer is the card's sentence, plus one fact",
              res.reply == cards[0] + Q.SEND_FILE_SAID, res.reply[:240])
        check(f"{phrase!r}: the approved verdict reaches approve()",
              len(approves) == 1 and approves[0].get("name") == "send-me.txt", approves)


# --------------------------------------------------------------------------
#   2. one match -> one card, and only an approved verdict approves
# --------------------------------------------------------------------------
def t_a_denied_card_sends_nothing():
    root = _root()
    (root / "send-me.txt").write_text("hello", encoding="utf-8")
    got = _intent("send me the file send-me.txt")
    if got is None:
        return
    res, prepares, cards, gate_calls, approves = _call(
        got, root, verdict=_Verdict(allowed=False))
    check("a denied card raises one card", len(gate_calls) == 1, gate_calls)
    check("a denied card never calls approve()", approves == [], approves)
    check("a denied card's reply is the card's own sentence",
          res.reply == cards[0] + Q.SEND_FILE_SAID, res.reply[:240])
    check("nothing here approves by itself: the runner has no auto path",
          Q.SEND_FILE_SAID == " Nothing is sent until you approve the card.")


def t_a_loosened_tier_raises_no_card():
    root = _root()
    (root / "send-me.txt").write_text("hello", encoding="utf-8")
    got = _intent("send me the file send-me.txt")
    if got is None:
        return
    res, prepares, cards, gate_calls, approves = _call(got, root, tier="auto")
    check("a non-ask tier prepares nothing and raises no card",
          prepares == [] and gate_calls == [] and approves == [],
          (prepares, gate_calls, approves))
    check("... and says the card was not raised",
          "did not raise a card" in res.reply and "Nothing was sent" in res.reply,
          res.reply[:240])


# --------------------------------------------------------------------------
#   3. refusals: the module's own words, no card, no approve
# --------------------------------------------------------------------------
def t_refusals_are_the_modules_words_and_raise_no_card():
    root = _root()
    (root / "report-jan.txt").write_text("one", encoding="utf-8")
    (root / "report-feb.txt").write_text("two", encoding="utf-8")
    big = root / "big.bin"
    with big.open("wb") as fh:
        fh.truncate(SEND.CAP_BYTES + 1)
    cases = (
        ("send me the file nope.txt", "nope.txt", "NO_SEARCH_WORDS"),
        ("send me the file report", "report", "several"),
        ("send me the file big.bin", "big.bin", "NO_CAP_WORDS"),
    )
    for phrase, query, kind in cases:
        got = _intent(phrase)
        if got is None:
            continue
        expected = _module_refusal(query, root)
        check(f"{kind}: the module itself refuses that query",
              expected is not None, query)
        res, prepares, cards, gate_calls, approves = _call(got, root)
        check(f"{kind}: the reply is the module's own sentence, unchanged",
              res.reply == expected, (res.reply[:240], str(expected)[:240]))
        check(f"{kind}: no card and no approve()",
              gate_calls == [] and approves == [], (gate_calls, approves))
    # A file the owner's listed folders do not contain: the same no-match
    # sentence, even though the file really exists on this PC.
    outside = _root()
    (outside / "secret.txt").write_text("not listed", encoding="utf-8")
    empty = _root()
    got = _intent("send me the file secret.txt")
    if got is not None:
        expected = _module_refusal("secret.txt", empty)
        res, prepares, cards, gate_calls, approves = _call(got, empty)
        check("outside the listed folders: the module's no-match sentence",
              expected is not None and res.reply == expected,
              (res.reply[:240], str(expected)[:240]))
        check("outside the listed folders: no card and no approve()",
              gate_calls == [] and approves == [], (gate_calls, approves))


# --------------------------------------------------------------------------
#   4. over-capture: ordinary conversation stays the model's
# --------------------------------------------------------------------------
def t_ordinary_conversation_does_not_become_a_file_send():
    for phrase in ("send me a message", "send an email to Sam", "send my regards",
                   "send a photo to my phone", "send the meeting notes to my phone",
                   "send me the file"):
        got = Q.match(phrase, NOW)
        check(f"{phrase!r} is not the file-send path",
              got is None or got.name != "send_file", got)
    todo = Q.match("add milk to my todo list", NOW)
    check("the to-do path still answers", todo is not None and todo.name == "todo_add",
          todo)
    email = Q.match("send an email to Sam", NOW)
    check("the email sentence is still the model's (no quick path steals it)",
          email is None, email)


# --------------------------------------------------------------------------
#   5. wiring: answer() reaches the runner; a private chat never does
# --------------------------------------------------------------------------
def t_answer_reaches_the_runner_and_a_private_chat_does_not():
    old = Q._run_send_file_chat
    calls = []

    def stub(f):
        calls.append(dict(f or {}))
        return Q.Result("stub answer", "send_file")

    Q._run_send_file_chat = stub
    try:
        res = Q.answer("send me the file send-me.txt", sched=_Sched(), now=NOW)
        check("answer() reaches the file-send runner",
              res is not None and res.intent == "send_file"
              and calls == [{"query": "send-me.txt"}], (res, calls))
        before = len(calls)
        private = Q.answer("send me the file send-me.txt", sched=_Sched(),
                           now=NOW, private=True)
        check("a private chat refuses before the runner, raising no card",
              len(calls) == before and private is not None and private.private,
              (calls, private))
    finally:
        Q._run_send_file_chat = old
    check("the send-file intent is not in READ_ONLY_INTENTS (it raises a card)",
          "send_file" not in Q.READ_ONLY_INTENTS)


def main() -> int:
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                print(f"FAIL  {name} raised")
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
