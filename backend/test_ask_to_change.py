"""test_ask_to_change.py - a setting changed by ASKING, and the receipt proved.

    python backend/test_ask_to_change.py

THE SLICE THIS PINS (2026-10-27). "Do anything by asking Jarvis", first
vertical slice: a VERIFIED setting change through chat. The owner says a
sentence that states the state they want ("make the prompt coach off", "set web
search to off", "I want the prompt coach off", "the prompt coach should be
off"), Jarvis resolves it against the real registry, asks ONE question back
when no state was said, and then either

  * raises ONE card through the setting's OWN writer and says a card is
    waiting (never "done"), or
  * (when the writer applies at once) RE-READS the value and answers with a
    receipt naming the old and the new value.

WHAT MAKES THESE CHECKS HAVE TEETH
    * The writer is a RECORDER here: the happy path asserts it was called
      exactly once with the wanted bool AND the request's own peer/local, and
      the "already" path asserts it was called ZERO times.
    * Every receipt assertion is on a RE-READ the test itself controls: the
      reader returns False then True, or True then False, and the answer must
      say the truth in both directions.
    * Source pins (not prose pins): the apply runner calls the registry writer
      and contains no direct config write and no gate decision at all.
    * The allow-list is DERIVED and compared with the real BOOL_SETTINGS table,
      so a switch added later cannot join this lane silently - it fails here
      until a person decides.
    * #884's read-only explanation is compared WORD FOR WORD with
      `jarvis_feature_guide.change()` for a target that is not on the list, so
      the guide's wording cannot drift while this lane is added beside it.

No model, no network, no port, and nothing here writes a setting for real.
"""
from __future__ import annotations

import dataclasses
import inspect
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_feature_guide as FG  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def setting_of(key):
    return next((b for b in R.BOOL_SETTINGS if b.key == key), None)


def name_of(key):
    setting = setting_of(key)
    return (setting.names[0] if setting is not None and setting.names else key)


class FakeSetting:
    """One BoolSetting swapped for the length of a block, with a recorded
    writer and a scripted reader. Nothing real is written."""

    def __init__(self, key, *, outcome=None, reads=(), raises=None):
        self.key = key
        self.outcome = outcome
        self.reads = list(reads)
        self.raises = raises
        self.calls = []
        self.read_calls = 0
        self._old_settings = None
        self._old_reader = None

    # -- the writer the production code must be the only caller of ----------
    def set(self, on, *, peer=None, local=None):
        self.calls.append({"on": bool(on), "peer": peer, "local": local})
        if self.raises is not None:
            raise self.raises
        return self.outcome

    # -- the reader the receipt must come from -----------------------------
    def read(self):
        self.read_calls += 1
        if not self.reads:
            return None
        return self.reads.pop(0)

    def __enter__(self):
        old = setting_of(self.key)
        self._old_settings = R.BOOL_SETTINGS
        R.BOOL_SETTINGS = tuple(
            dataclasses.replace(b, set=self.set) if b.key == self.key else b
            for b in R.BOOL_SETTINGS)
        self._old_reader = FG.STATE_READERS.get(self.key)
        FG.STATE_READERS[self.key] = self.read
        return self

    def __exit__(self, *exc):
        R.BOOL_SETTINGS = self._old_settings
        if self._old_reader is None:
            FG.STATE_READERS.pop(self.key, None)
        else:
            FG.STATE_READERS[self.key] = self._old_reader
        return False


def say(text, **kw):
    """One sentence through the real grammar and the real dispatcher."""
    intent = Q.match(text)
    if intent is None:
        return None, None
    return intent, Q.run(intent, None, 0.0, **kw)


def outcome(ok=True, said="", waiting=False, refused_pc_only=False):
    return R.Outcome(ok=ok, said=said, waiting=waiting, refused_pc_only=refused_pc_only)


# --------------------------------------------------------------------------
# 1. The allow-list IS the rule, and it is derived rather than typed twice
# --------------------------------------------------------------------------

print("--- the allow-list ---")

ALLOWED = set(Q.CHANGE_BY_ASKING)
REAL = {b.key for b in R.BOOL_SETTINGS}

check("every allow-listed key is a real BoolSetting", not (ALLOWED - REAL),
      sorted(ALLOWED - REAL))
check("the allow-list is a frozenset, so it cannot be edited at run time",
      isinstance(Q.CHANGE_BY_ASKING, frozenset), type(Q.CHANGE_BY_ASKING))

# The three exclusions, each for a reason the code states: no readable state
# (the second card's features are not measured yet) and a PC-only card.
NO_READBACK = {"second_card_combined", "second_card_suggest_struggle",
               "second_card_suggest_correction"}
PC_ONLY_CARD = {"lights_without_card"}
check("the three second-card switches are NOT in the list (their state cannot "
      "be read, so a receipt for them would be a guess)",
      not (NO_READBACK & ALLOWED), sorted(NO_READBACK & ALLOWED))
check("lights without asking is NOT in the list (its card is PC-only)",
      not (PC_ONLY_CARD & ALLOWED), sorted(PC_ONLY_CARD & ALLOWED))

# DERIVED, not typed: every other switch must be in, or a switch added later
# would silently be outside this lane (or worse, inside it without a decision).
EXPECTED = REAL - NO_READBACK - PC_ONLY_CARD
check(f"...and every other switch ({len(EXPECTED)}) IS in the list - a new "
      "switch therefore fails this line until a person decides",
      ALLOWED == EXPECTED, f"missing {sorted(EXPECTED - ALLOWED)}, "
                           f"extra {sorted(ALLOWED - EXPECTED)}")

# Every entry passes the three rules the list's comment states, read off the
# real tables rather than trusted.
bad_writer = [k for k in ALLOWED
              if not str(getattr(setting_of(k), "set", None).__name__).startswith("set_")]
check("every entry's writer is a registry setter function", not bad_writer, bad_writer)
missing_reader = [k for k in ALLOWED if k not in FG.STATE_READERS]
check("every entry has a state reader, so the receipt can be a read",
      not missing_reader, missing_reader)

print()

# --------------------------------------------------------------------------
# 2. Detection: a stated state is resolved; a missing state asks ONE question
# --------------------------------------------------------------------------

print("--- the sentences, and what each becomes ---")

STATES_THE_OWNER_SAYS = (
    ("make the prompt coach off", "prompt_coach", False),
    ("make the prompt coach on", "prompt_coach", True),
    ("set the prompt coach to on", "prompt_coach", True),
    ("set the prompt coach to off", "prompt_coach", False),
    ("put the prompt coach on", "prompt_coach", True),
    ("change the prompt coach to off", "prompt_coach", False),
    ("switch the prompt coach to on", "prompt_coach", True),
    ("turn the prompt coach to off", "prompt_coach", False),
    ("i want the prompt coach off", "prompt_coach", False),
    ("i'd like the prompt coach off", "prompt_coach", False),
    ("i want the prompt coach to be switched off", "prompt_coach", False),
    ("the prompt coach should be off", "prompt_coach", False),
    ("the prompt coach should be turned off", "prompt_coach", False),
    ("the prompt coach needs to be off", "prompt_coach", False),
    ("the prompt coach must be off", "prompt_coach", False),
    ("make sure the prompt coach is off", "prompt_coach", False),
    ("ensure web search is off", "web_search", False),
    ("make web search on", "web_search", True),
    ("set web search to off", "web_search", False),
    ("make the prompt coach enabled", "prompt_coach", True),
    ("make the prompt coach disabled", "prompt_coach", False),
    ("the prompt coach should be disabled", "prompt_coach", False),
    ("make chat history off", "chat_history", False),
    ("make learning in the background off", "background_learning", False),
    ("set background learning to off", "background_learning", False),
    ("make the sandbox on", "sandbox_exec", True),
    ("can you make the prompt coach off", "prompt_coach", False),
    ("make the prompt coach feature off", "prompt_coach", False),
    ("make the prompt coach on please", "prompt_coach", True),
)

wrong = []
for phrase, key, on in STATES_THE_OWNER_SAYS:
    got = Q.match(phrase)
    if got is None or got.name != "feature_change_apply":
        wrong.append((phrase, got.name if got else "the model"))
        continue
    if got.f.get("key") != key or got.f.get("on") is not on:
        wrong.append((phrase, got.f))
check(f"all {len(STATES_THE_OWNER_SAYS)} ways of saying the wanted state reach "
      "the change lane with the right key and bool", not wrong, wrong[:6])

# The state is what decides the DIRECTION, so a wrong direction is the worst
# possible bug here: assert both directions exist for the same setting.
both = [got.f.get("on") for got in (Q.match("make web search on"),
                                    Q.match("make web search off"))]
check("the two directions are two different values (on is True, off is False)",
      both == [True, False], both)

# Ambiguous: a real allow-listed setting named with NO state. ONE question,
# never a guess and never a card.
AMBIGUOUS = ("change the prompt coach", "toggle the prompt coach",
             "adjust the prompt coach", "switch the prompt coach",
             "set the prompt coach", "change web search")
wrong = []
for phrase in AMBIGUOUS:
    got = Q.match(phrase)
    if got is None or got.name != "feature_change_ask":
        wrong.append((phrase, got.name if got else "the model"))
        continue
    if not got.f.get("key"):
        wrong.append((phrase, "no key"))
check(f"all {len(AMBIGUOUS)} no-state phrasings ask ONE question back", not wrong, wrong)
ask_out, ask_res = say("change the prompt coach")
check("...and the question is a question, naming the setting and both words",
      ask_res is not None and ask_res.reply.count("?") == 1
      and "prompt coach" in ask_res.reply and "on or off" in ask_res.reply,
      ask_res.reply if ask_res else None)
check("...and the question itself changes nothing (it is read-only)",
      ask_res is not None and ask_res.intent == "feature_change_ask")

# NEAR MISSES. These must NOT become a setting change: a value that is not
# on/off, a general sentence, a sentence an older lane already owns, and a
# TWO-PART sentence (which would otherwise act on the last state word in it).
for phrase in ("make the prompt coach on and tell me",
               "make me a sandwich",
               "set the prompt coach to medium",
               "change the prompt coach to louder",
               "make it on",
               "make the second card on",
               # The bug this pair pins: without the guard, the FIRST clause's
               # name resolves through the tolerant matcher and the state word
               # taken is the LAST one - the opposite direction to what the
               # owner said about the prompt coach.
               "i want the prompt coach off and the lights on",
               "make web search off and the prompt coach on",
               "make sure the prompt coach is off and the timer is on"):
    got = Q.match(phrase)
    check(f"'{phrase}' is not read as a setting change",
          got is None or got.name != "feature_change_apply",
          got.name if got else "the model")
check("...while a setting whose own NAME contains 'on' still resolves exactly",
      (Q.match("make one bigger model on both cards off") or Q.Intent("")).name
      == "feature_change",
      Q.match("make one bigger model on both cards off"))

# The phrases that ALREADY work keep their own intent, byte for byte: this lane
# is additive and must not take a working sentence away.
for phrase, want in (("turn on the prompt coach", "settings_bool"),
                     ("turn off the prompt coach", "settings_bool"),
                     ("turn on lights without asking", "settings_bool"),
                     ("turn off the app lock", "settings_not_by_asking"),
                     ("turn on the wake word", "settings_wake_word"),
                     ("set the voice speed to faster", "control_set"),
                     ("how do I turn on web search", "feature_howto")):
    got = Q.match(phrase)
    check(f"'{phrase}' keeps its own intent ({want})",
          got is not None and got.name == want,
          got.name if got else "the model")

print()

# --------------------------------------------------------------------------
# 3. The writer is the setting's OWN setter, once, with the request's address
# --------------------------------------------------------------------------

print("--- the write goes through the setting's own writer ---")

fake = FakeSetting("prompt_coach", outcome=outcome(said="Prompt coach is on."),
                   reads=[False, True])
with fake:
    intent, res = say("make the prompt coach on", peer="10.0.0.5", local=False)
check("the sentence reaches the change lane", intent is not None
      and intent.name == "feature_change_apply", intent.name if intent else None)
check("the setter ran EXACTLY once", len(fake.calls) == 1, fake.calls)
check("...with the wanted bool", fake.calls and fake.calls[0]["on"] is True,
      fake.calls)
check("...and with the request's own peer/local, as the settings path passes them",
      fake.calls and fake.calls[0]["peer"] == "10.0.0.5"
      and fake.calls[0]["local"] is False, fake.calls)
check("the answer is the receipt: old value, then new value, read back",
      res is not None and "reads on now" in res.reply and "was off before" in res.reply,
      res.reply if res else None)
check("...and the route says the change lane, not the explanation lane",
      res is not None and res.intent == "feature_change_apply")

# Already there: zero calls, zero cards, and words that say "already".
fake = FakeSetting("prompt_coach", outcome=outcome(said="never used"),
                   reads=[True])
with fake:
    intent, res = say("make the prompt coach on")
check("a setting already in the wanted state calls the setter ZERO times",
      fake.calls == [], fake.calls)
check("...and the answer says it is already on, and that nothing changed",
      res is not None and "already on" in res.reply
      and "Nothing was changed" in res.reply, res.reply if res else None)

# The card path: the setter's own waiting sentence, never "done".
fake = FakeSetting("screen_picture",
                   outcome=outcome(said="Waiting for your approval. Picture mode "
                                        "turns on only if you approve the card, "
                                        "on your PC or phone.", waiting=True),
                   reads=[False, True])
with fake:
    res = Q.run(Q.Intent("feature_change_apply",
                         {"key": "screen_picture", "on": True}), None, 0.0)
check("a carded setting answers with the setter's own waiting sentence",
      res is not None and "Waiting for your approval" in res.reply,
      res.reply if res else None)
check("...and claims nothing: no 'checked', no success sentence",
      res is not None and "I checked:" not in res.reply
      and "reads on now" not in res.reply, res.reply if res else None)
check("...and does NOT read the value back, because nothing was written",
      fake.read_calls == 1, fake.read_calls)   # the pre-read only

# A setter whose waiting words do not mention approval gets the fact added.
fake = FakeSetting("web_search", outcome=outcome(said="Queued.", waiting=True),
                   reads=[False])
with fake:
    res = Q.run(Q.Intent("feature_change_apply",
                         {"key": "web_search", "on": True}), None, 0.0)
check("a waiting answer that never says 'card' still tells the owner one is up",
      res is not None and "card is waiting" in res.reply
      and "Nothing has changed yet" in res.reply, res.reply if res else None)

print()

# --------------------------------------------------------------------------
# 4. The receipt is honest in both failure directions
# --------------------------------------------------------------------------

print("--- when the read disagrees, it says so ---")

fake = FakeSetting("prompt_coach", outcome=outcome(said="Prompt coach is on."),
                   reads=[False, False])          # wrote, but the value did not move
with fake:
    res = Q.run(Q.Intent("feature_change_apply",
                         {"key": "prompt_coach", "on": True}), None, 0.0)
check("a setter that reports success but a value that did not move is NOT "
      "reported as done",
      res is not None and "still reads off" in res.reply
      and "Nothing was changed" in res.reply and "I checked:" not in res.reply,
      res.reply if res else None)

fake = FakeSetting("prompt_coach", outcome=outcome(said="Prompt coach is on."),
                   reads=[False, None])           # wrote, value unreadable after
with fake:
    res = Q.run(Q.Intent("feature_change_apply",
                         {"key": "prompt_coach", "on": True}), None, 0.0)
check("a value that cannot be read back is not claimed either",
      res is not None and "could not read it back" in res.reply
      and "I checked:" not in res.reply, res.reply if res else None)

fake = FakeSetting("prompt_coach", outcome=outcome(said="never used"),
                   reads=[None])
with fake:
    res = Q.run(Q.Intent("feature_change_apply",
                         {"key": "prompt_coach", "on": True}), None, 0.0)
check("a value that cannot be read BEFORE the write is not written at all",
      fake.calls == [] and res is not None and "will not change it" in res.reply,
      (fake.calls, res.reply if res else None))

fake = FakeSetting("web_search",
                   outcome=outcome(ok=False, said="That can only be changed on "
                                                  "the PC."),
                   reads=[False])
with fake:
    res = Q.run(Q.Intent("feature_change_apply",
                         {"key": "web_search", "on": True}), None, 0.0)
check("the setter's own refusal is the answer, unchanged",
      res is not None and res.reply == "That can only be changed on the PC.",
      res.reply if res else None)

fake = FakeSetting("web_search", outcome=None, raises=RuntimeError("boom"),
                   reads=[False])
with fake:
    res = Q.run(Q.Intent("feature_change_apply",
                         {"key": "web_search", "on": True}), None, 0.0)
check("a writer that raises is said plainly and changes nothing",
      res is not None and "could not be changed" in res.reply
      and "nothing was changed" in res.reply, res.reply if res else None)

# An intent with no state in it at all is a coding mistake, and it must never
# be read as "off" (which is what bool(None) would do).
fake = FakeSetting("web_search", outcome=outcome(said="Web search is off."),
                   reads=[True])
with fake:
    res = Q.run(Q.Intent("feature_change_apply", {"key": "web_search"}), None, 0.0)
check("an apply intent with no state fails closed: no write, and it says so",
      fake.calls == [] and res is not None
      and "did not catch whether you want" in res.reply,
      (fake.calls, res.reply if res else None))

print()

# --------------------------------------------------------------------------
# 5. A target that is NOT on the list keeps #884's exact read-only answer
# --------------------------------------------------------------------------

print("--- everything else keeps its own answer ---")

for key in sorted(NO_READBACK | PC_ONLY_CARD):
    phrase = f"make {name_of(key)} off"
    # No scripted reads here: the fake reader answers None both inside the
    # block and after it, so the guide's own "It is off right now" clause is
    # absent from BOTH sides and the comparison is about the guide's words.
    fake = FakeSetting(key, outcome=outcome(said="never used"), reads=[])
    with fake:
        intent, res = say(phrase)
        want = FG.change(name_of(key))["words"]
    check(f"'{phrase}' is the explanation lane, not the change lane",
          intent is not None and intent.name == "feature_change",
          intent.name if intent else None)
    check(f"...and it writes NOTHING for {key}", fake.calls == [], fake.calls)
    check(f"...and its words are #884's own, word for word ({key})",
          res is not None and res.reply == want,
          (res.reply[-200:] if res else None, want[-200:]))

# A feature's own change answer is untouched as well.
for phrase in ("can I change the prompt coach", "is the prompt coach adjustable",
               "can i change lights without asking"):
    intent, res = say(phrase)
    check(f"'{phrase}' still reaches the read-only change answer",
          intent is not None and intent.name == "feature_change"
          and res is not None and res.intent == "feature_change",
          intent.name if intent else None)

print()

# --------------------------------------------------------------------------
# 6. END TO END, with the REAL setter and the REAL reader: the value moves
# --------------------------------------------------------------------------

print("--- the real writer and the real reader, in a throwaway folder ---")

import tempfile  # noqa: E402

import jarvis_prompt_coach as PC  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="jarvis-ask-to-change-"))
_old_cfg = PC._config_dir
PC._config_dir = lambda: TMP          # never the owner's own folder
try:
    started = FG.read_state("prompt_coach")
    intent, res = say("make the prompt coach on")
    moved = FG.read_state("prompt_coach")
    check("the real sentence reaches the change lane", intent is not None
          and intent.name == "feature_change_apply", intent.name if intent else None)
    check("the REAL setter wrote the value (the reader sees True now)",
          moved is True and started is not True, (started, moved))
    check("...and the answer is a receipt naming both values",
          res is not None and "reads on now" in res.reply
          and "was off before" in res.reply, res.reply if res else None)
    check("...and 'Done.' is not the whole answer, because a read is better",
          res is not None and res.reply != "Done.", res.reply if res else None)
    # The same sentence again: no card, no write, and the words say already.
    before_second = TMP.joinpath(PC.SETTINGS_NAME).read_bytes()
    intent2, res2 = say("make the prompt coach on")
    after_second = TMP.joinpath(PC.SETTINGS_NAME).read_bytes()
    check("asking for the value it already has writes NOTHING to the file",
          before_second == after_second, (before_second, after_second))
    check("...and says it is already on", res2 is not None
          and "already on" in res2.reply, res2.reply if res2 else None)
    # And the other direction really moves it back: this is the reversibility
    # the allow-list's comment claims, measured rather than asserted.
    intent3, res3 = say("set the prompt coach to off")
    check("the other direction really moves it back",
          FG.read_state("prompt_coach") is False and intent3 is not None
          and intent3.name == "feature_change_apply",
          (FG.read_state("prompt_coach"), intent3.name if intent3 else None))
    check("...with its own receipt", res3 is not None
          and "reads off now" in res3.reply and "was on before" in res3.reply,
          res3.reply if res3 else None)
finally:
    PC._config_dir = _old_cfg

print()

# --------------------------------------------------------------------------
# 7. Source pins: the writer, no direct config write, and no approval at all
# --------------------------------------------------------------------------

print("--- source pins (they fail if anyone rewrites the path) ---")

apply_src = inspect.getsource(Q._run_feature_change_apply)
check("the apply runner calls the registry's own setter",
      ".set(" in apply_src and "setting.set(" in apply_src, apply_src[:200])
direct_writes = [word for word in ("save_settings(", "write_text(", "json.dump",
                                   "_save(", "open(", "Path(")
                  if word in apply_src]
check("...and contains NO direct config write", not direct_writes, direct_writes)
approval = [word for word in ("jarvis_gate", "decide(", ".approve", "approve(",
                              "gate.check", "check(")
            if word in apply_src]
check("...and approves nothing: no gate call, no decide, no approve",
      not approval, approval)

run_src = inspect.getsource(Q.run)
check("the dispatcher hands the request's peer/local to the apply runner",
      "_run_feature_change_apply(f, peer, local)" in run_src, run_src[:200])

check("feature_change is still read-only, so 'can I change X' never writes",
      "feature_change" in Q.READ_ONLY_INTENTS)
check("the ONE question back changes nothing and is read-only too",
      "feature_change_ask" in Q.READ_ONLY_INTENTS)
check("the refusal changes nothing and is read-only",
      "feature_change_refused" in Q.READ_ONLY_INTENTS)
check("the apply intent is NOT read-only, so 'cancel that' knows something "
      "happened",
      "feature_change_apply" not in Q.READ_ONLY_INTENTS)

# The whole module has exactly ONE gate door - the update lane's own nested
# `_gate` helper - and the change lane is not it. A second `import jarvis_gate`
# appearing is the failure this pins.
quick_src = (HERE / "jarvis_quick.py").read_text(encoding="utf-8")
check("the module has exactly one gate import, and it is the update lane's",
      quick_src.count("import jarvis_gate") == 1
      and "jarvis_gate" not in apply_src,
      quick_src.count("import jarvis_gate"))
check("the change lane never reaches that gate door",
      "_gate(" not in apply_src, [ln for ln in apply_src.splitlines()
                                  if "_gate(" in ln])

# A private chat refuses the change before any writer can run.
fake = FakeSetting("prompt_coach", outcome=outcome(said="never used"),
                   reads=[False, True])
with fake:
    private = Q.answer_turn(
        {"messages": [{"role": "user", "content": "make the prompt coach off",
                       "provenance": "typed"}]},
        private=True)
check("a private chat refuses the change and the setter never runs",
      fake.calls == [] and private is not None
      and private.intent == "feature_change_apply"
      and "private" in private.reply.lower(), private.reply if private else None)

print()

# --------------------------------------------------------------------------
# 7. What this slice must never claim
# --------------------------------------------------------------------------

print("--- the refusals, each ONE plain sentence ---")

REFUSALS = (
    ("set my password to something new", "password"),
    ("make the pairing token on", "token"),
    ("change the approval tiers to auto", "configuration"),
    ("change the config file", "configuration"),
    ("change my memory to forget everything", "cannot be undone"),
)
for phrase, marker in REFUSALS:
    intent, res = say(phrase)
    check(f"'{phrase}' is refused in words",
          intent is not None and intent.name == "feature_change_refused"
          and res is not None and marker in res.reply
          and res.reply.count(".") == 1,
          (intent.name if intent else None, res.reply if res else None))

# The refusals are for names NOTHING resolves to. A real setting's name must
# never be swallowed by one of those words.
check("a real setting whose name contains none of those words is unaffected",
      Q.match("make the better voice off") is not None
      and Q.match("make the better voice off").name == "feature_change_apply",
      Q.match("make the better voice off"))
check("...and 'change the timer' is still nobody's setting change",
      (Q.match("change the timer") or Q.Intent("")).name != "feature_change_apply",
      Q.match("change the timer"))

print()

print(f"PASS {len(PASSED)}   FAIL {len(FAILED)}")
if FAILED:
    print()
    for name in FAILED:
        print(f"FAILED: {name}")
sys.exit(1 if FAILED else 0)
