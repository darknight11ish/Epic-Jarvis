"""test_tool_profiles_chat.py - Jarvis can hold a conversation about its own tools.

    py -3 -B backend/test_tool_profiles_chat.py

WHAT THIS SUITE IS. `backend/jarvis_tool_profiles.py` holds the dossier (the
other lane's module). This suite proves the WIRING that turns it into an answer:
the deterministic fast path in `jarvis_quick` and the bounded system note in
`jarvis_agent`. No server, no model, no network, no owner file: every answer
here reads a fixed module and a made-up scheduler.

WHAT FAILS BEFORE THE WIRING, MEASURED ON THIS TREE (the merge of
`feat/self-awareness-phase3` and `feat/tool-profiles`, commit c587b3daa, in a
second worktree with this suite absent and the wiring reverted):

  * "tell me about the github tool"        -> match() = None (the model).
  * "what does browser_control do"         -> match() = feature_explain, i.e.
    the feature guide's prose for a *different* thing: the catalogue does not
    use the tool's name, so the guide found a near row.
  * "how does the reminder work"           -> None.
  * tool_profile_note([..."hi"])           -> None (already, and it must STAY
    None: the note is the one new way a prompt could change its bytes).

AFTER: the first two are `tool_profile` and answer with the dossier's own words
in `lane: "no AI model"`; the third still reaches the model, which now gets the
reminder tool's page as a note; the fourth is still None.

TWO GATES THIS SUITE EXISTS TO PIN, and both were found by running the older
suites rather than by reading the design:

  1. THE FEATURE LAYER MUST KEEP ITS ANSWERS. 42 of the catalogue's 175 feature
     titles open with words that also name a tool ("Web search", "Goals", "Read
     your own calendar", "Spending summaries", "Jarvis reads your email"), and
     `test_feature_answers` requires every one of them to resolve through the
     feature guide. So the fast path asks for the word "tool" or for the tool's
     code name typed with its underscore, and `t_no_feature_row_is_hijacked`
     re-checks all 175 rows both ways.
  2. THE WARM-UP AND A REAL TURN MUST SEND THE SAME BYTES before the question
     (`test_warm_prefix`). "what is on my calendar tomorrow" is that suite's
     real question, and it mentions the calendar by nickname - so the note may
     not fire on a nickname. `t_a_turn_that_names_nothing_is_byte_identical`
     pins the other side of it.

WHAT THIS SUITE DOES NOT CLAIM.
  * It does not re-check the dossier's facts against the modules; that is
    `backend/test_tool_profiles.py`, the module's own suite.
  * It cannot prove what the owner's PC will answer: `n_ctx` comes from Ollama
    at run time, so the token figures below are arithmetic at this repo's own
    `estimate_tokens` (3 characters a token), not a reading from the machine.
  * Two dossier sentences trip `jarvis_claims.unbacked_claim` as FALSE
    POSITIVES (`set_reminder`'s title line and one `set_timer` "gives" line are
    imperative: "Set a reminder or an alarm (set_reminder)."). They cannot
    affect a chat answer - that checker is applied to the MODEL's answer text
    in `jarvis_agent._nothing_done_line`, never to a `tool_profile` result,
    which is deterministic and has no model - but they are real and they belong
    to the module's wording, not to this wiring, so `t_no_answer_reads_as_a_
    done_claim` names them and fails if a THIRD one appears.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "rebuilt"))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-tool-profiles-chat-"))
for _name in ("OPENJARVIS_CONFIG_DIR", "OPENJARVIS_HOME", "JARVIS_HOME"):
    os.environ.setdefault(_name, str(_TMP / _name.lower()))

import jarvis_agent as AN  # noqa: E402
import jarvis_claims as CL  # noqa: E402
import jarvis_feature_catalogue as CAT  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_tool_profiles as TP  # noqa: E402

FAILED, PASSED = [], []
NOW = time.mktime(time.strptime("2026-11-04 09:05:00", "%Y-%m-%d %H:%M:%S"))


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class Sched:
    """A made-up scheduler: no answer here reads the owner's real jobs."""

    def listed(self):
        return []

    def mark_command(self, text):
        pass

    def note_set(self, *a, **k):
        pass

    def forget_set(self, conversation):
        pass


#: The question shapes this path owns: the owner says "tool", or types the
#: tool's own code name. Both forms are checked for EVERY name below.
def _by_tool_word(name):
    return "tell me about the " + name.replace("_", " ").replace("-", " ") + " tool"


def _by_code_name(name):
    return "what does " + name + " do"


# --------------------------------------------------------------------------
#   1. The fast path: an answer, in its own words, and no model
# --------------------------------------------------------------------------
def t_a_tool_question_answers_with_no_model():
    for name in ("browser_control", "github_search", "memory_search",
                 "calendar_read", "set_reminder"):
        text = "what does " + name + " do"
        got = Q.match(text)
        check(f"{text!r} is the tool path", getattr(got, "name", None) == "tool_profile",
              getattr(got, "name", None))
        res = Q.answer(text, sched=Sched(), now=NOW)
        check(f"... and answers in the dossier's own words",
              res is not None and res.reply == TP.answer_about(text),
              "" if res is None else res.reply[:120])
        check(f"... on the no-model lane",
              res is not None and Q.route_fields(res)["quick"] == "tool_profile"
              and Q.route_fields(res)["lane"] == "no AI model"
              and Q.route_fields(res)["where"] == "local",
              None if res is None else Q.route_fields(res))


def t_every_tool_and_family_can_be_asked_about():
    """Coverage, in both owned forms - the mirror of test_reach's every-tool row."""
    missing = [n for n in TP.names()
               if getattr(Q.match(_by_tool_word(n)), "name", None) != "tool_profile"]
    check("every tool and family answers 'tell me about the <name> tool'",
          not missing, missing)
    underscored = [n for n in TP.names() if "_" in n]
    missing = [n for n in underscored
               if getattr(Q.match(_by_code_name(n)), "name", None) != "tool_profile"]
    check("every code name typed with its underscore answers 'what does <id> do'",
          not missing, missing)
    check("the dossier covers exactly the tools jarvis_agent offers",
          set(TP.PROFILES) == set(AN.TOOLS), sorted(set(TP.PROFILES) ^ set(AN.TOOLS)))


def t_a_question_that_names_no_tool_still_reaches_the_model():
    """No tool named -> None -> the model, exactly as before this path existed."""
    for text in ("what do you have", "what is the weather", "hi",
                 "what are my goals", "set a timer for 5 minutes",
                 "remind me to call mum", "what do you know about me",
                 "how do I set a reminder", "what can you see on my screen",
                 "which tools ask first", "what is on my calendar tomorrow"):
        got = Q.match(text)
        check(f"{text!r} is not the tool path",
              getattr(got, "name", None) != "tool_profile",
              getattr(got, "name", None))


def t_no_feature_row_is_hijacked():
    """The 175-row guard: feature titles keep the feature guide's answer.

    Measured before the marker gate existed: 42 titles were taken by the tool
    path, which is why the gate is there.
    """
    titles = [r["title"] for r in CAT.FEATURES if isinstance(r, dict) and r.get("title")]
    check("the catalogue still has the rows this guard is about", len(titles) >= 170,
          len(titles))
    taken = [s for t in titles
             for s in ("tell me about " + t, "what does " + t + " do")
             if getattr(Q.match(s), "name", None) == "tool_profile"]
    check("no feature title is answered by the tool dossier", not taken, taken[:6])


def t_the_collision_probe_keeps_the_features_answer():
    """The design's own collision probe, plus the plug-in alias that met it."""
    for text in ("what is the prompt coach", "what is my calendar",
                 "tell me about Web search", "tell me about plugin list",
                 "what does Goals do"):
        got = Q.match(text)
        check(f"{text!r} keeps its feature answer",
              getattr(got, "name", None) in
              ("feature_explain", "feature_change", "feature_detail"),
              getattr(got, "name", None))


def t_the_fast_path_is_registered_read_only():
    """A private chat must not change state through it, and it must not undo."""
    check("tool_profile is in READ_ONLY_INTENTS", "tool_profile" in Q.READ_ONLY_INTENTS)
    res = Q.answer("what does browser_control do", private=True, sched=Sched(), now=NOW)
    check("a private chat never gets the fast path", res is None, res)
    check("... it hands the turn to the model", res is None)


def t_a_missing_module_falls_back_to_the_model():
    """The dossier is its own patch: a backend without it must not notice."""
    text = "what does browser_control do"
    saved = sys.modules.get("jarvis_tool_profiles")
    sys.modules["jarvis_tool_profiles"] = None
    try:
        check("no module -> the helper says so", Q._tool_profiles() is None)
        check("no module -> no intent", Q._tool_profile(Q.normalize_spoken_command(text)) is None)
        got = Q.match(text)
        check("no module -> the turn still routes somewhere sane",
              getattr(got, "name", None) != "tool_profile", getattr(got, "name", None))
        check("no module -> no note, so the prompt is unchanged",
              AN.tool_profile_note([{"role": "user", "content": text}]) is None)
        check("no module -> the runner returns None instead of raising",
              Q._run_tool_profile({"text": text}) is None)
    finally:
        if saved is None:
            sys.modules.pop("jarvis_tool_profiles", None)
        else:
            sys.modules["jarvis_tool_profiles"] = saved


# --------------------------------------------------------------------------
#   2. The note: bounded, conditional, and never on a turn that names nothing
# --------------------------------------------------------------------------
def t_a_tool_turn_gets_a_bounded_note():
    msgs = [{"role": "user", "content": "what does browser_control do"}]
    note = AN.tool_profile_note(msgs)
    cap = AN.TOOL_PROFILE_CHARS + len(AN.TOOL_NOTE_PREFIX)
    check("a tool turn gets a note", note is not None)
    check("... inside the 1,200-character budget plus its one fixed line",
          note is not None and len(note) <= cap, None if note is None else len(note))
    check("... that says where the facts came from and to use only them",
          note is not None and note.startswith(AN.TOOL_NOTE_PREFIX))
    check("... and carries the dossier's own words",
          note is not None and "browser_control" in note and "What it is:" in note)
    longest = max((len(TP.context_for(_by_tool_word(n)) or "") for n in TP.names()))
    check("every dossier block is inside the module's own cap",
          longest <= TP.CONTEXT_LIMIT, longest)


def t_a_turn_that_names_nothing_is_byte_identical():
    """The whole point of the conditional note: 0 tokens, the same bytes."""
    for text in ("hi", "what is the weather", "what is on my calendar tomorrow"):
        check(f"{text!r} gets no note", AN.tool_profile_note([{"role": "user", "content": text}]) is None)
    base = [{"role": "system", "content": AN.LANE_SYSTEM},
            {"role": "user", "content": "hi"}]
    plain = AN.dress_messages(base, manner="auto")
    empty = AN.dress_messages(base, manner="auto", tool_note="")
    check("dress_messages sends the same prompt with no note", plain == empty)
    no_note = AN.tool_profile_note([{"role": "user", "content": "hi"}]) or ""
    check("... and run_local_turn's own path changes nothing",
          AN.dress_messages(base, manner="auto", tool_note=no_note) == plain)


def t_a_follow_up_keeps_the_tools_page():
    """This is what makes a DISCUSSION possible rather than one answer."""
    convo = [{"role": "user", "content": "what does browser_control do"},
             {"role": "assistant", "content": "It drives one browser tab."},
             {"role": "user", "content": "would that let you fill in a form?"}]
    note = AN.tool_profile_note(convo)
    check("a follow-up keeps the block", note is not None)
    check("... the same one as the turn before", note == AN.tool_profile_note(convo[:1]))
    deeper = convo + [{"role": "assistant", "content": "Yes."},
                      {"role": "user", "content": "how would that change what you can do?"}]
    check("... and it still looks two turns back", AN.tool_profile_note(deeper) is not None)
    far = [{"role": "user", "content": "what does browser_control do"},
           {"role": "assistant", "content": "a"}, {"role": "user", "content": "unrelated"},
           {"role": "assistant", "content": "b"}, {"role": "user", "content": "unrelated"},
           {"role": "assistant", "content": "c"},
           {"role": "user", "content": "would that let you fill in a form?"}]
    check("... but not further than two turns", AN.tool_profile_note(far) is None)
    check("a first message that only looks like a follow-up gets no note",
          AN.tool_profile_note([{"role": "user", "content": "would that work?"}]) is None)


def t_the_note_is_placed_like_the_other_notes():
    """Immediately before the question, and the rules still first."""
    note = AN.tool_profile_note([{"role": "user", "content": "what does browser_control do"}])
    msgs = [{"role": "user", "content": "first"},
            {"role": "assistant", "content": "x"},
            {"role": "user", "content": "what does browser_control do"}]
    out = AN.with_tool_profile_note(msgs, note)
    at = [i for i, m in enumerate(out) if m.get("content") == note]
    check("the note is in the list exactly once", len(at) == 1, at)
    check("... immediately before the newest user message",
          bool(at) and at[0] == len(out) - 2 and out[-1]["content"] == msgs[-1]["content"])
    check("... and msgs itself is not changed", msgs[1]["content"] == "x" and len(msgs) == 3)
    first = AN.with_tool_profile_note([{"role": "user", "content": "what does browser_control do"}], note)
    check("with no system message yet, the rules are still first",
          first[0]["content"] == AN.LANE_SYSTEM and first[1]["content"] == note)
    check("no note -> the bytes are untouched", AN.with_tool_profile_note(msgs, "") == msgs)


def t_the_two_files_use_the_same_tool_marker():
    """`_TOOL_SAID` decides what counts as naming a tool, in both files.

    Two copies of one expression is a drift risk, so the copy is checked rather
    than trusted: if one side gains "plug-in" or loses the underscore, this
    fails here instead of in a field test where the fast path and the note
    disagree about the same sentence.
    """
    check("jarvis_quick._TOOL_SAID and jarvis_agent._TOOL_SAID are the same expression",
          Q._TOOL_SAID.pattern == AN._TOOL_SAID.pattern,
          (Q._TOOL_SAID.pattern, AN._TOOL_SAID.pattern))
    for text in ("what does browser_control do", "tell me about the github tool",
                 "what is on my calendar tomorrow", "tell me about Web search"):
        low = text.lower()
        check(f"... and they agree about {text!r}",
              bool(Q._TOOL_SAID.search(low)) == bool(AN._TOOL_SAID.search(low)))


# --------------------------------------------------------------------------
#   3. What the answers must never look like
# --------------------------------------------------------------------------
def t_no_answer_reads_as_a_done_claim():
    """A dossier sentence must not read as "I did it" (the claims guard).

    Two do, and they are named here rather than hidden: they are imperative
    wording in the module ("Set a reminder or an alarm (set_reminder)."), not a
    claim this wiring makes, and the checker that flags them never sees a
    deterministic answer - `jarvis_agent._nothing_done_line` runs it on the
    MODEL's text. A third one fails this test, which is the ratchet.
    """
    known = {"set_reminder", "set_timer"}
    fired = set()
    for name in TP.names():
        said = TP.answer_about(_by_tool_word(name))
        if said and CL.unbacked_claim(said, []):
            fired.add(name)
    check("no NEW dossier answer reads as an action already taken",
          fired <= known, sorted(fired - known))
    check("... and every answer the tool path really returns is deterministic",
          all((Q.answer(_by_tool_word(n), sched=Sched(), now=NOW) or Q.Result("", "")).intent
              == "tool_profile"
              for n in ("browser_control", "calculator", "memory_search", "files")))


GENERIC = re.compile(r"^(?:x|y|z|todo|foo|bar)$")


def t_no_answer_leaks_a_path_or_a_count():
    """The note is safe in a private chat: fixed dossier data, nothing live."""
    leaks = []
    for name in TP.names():
        block = TP.context_for(_by_tool_word(name)) or ""
        if re.search(r"[A-Za-z]:\\|/Users/|AppData|pcadmin", block):
            leaks.append(name)
    check("no dossier block contains an absolute path or a user name", not leaks, leaks)
    check("the fixed line claims no live state",
          not re.search(r"\d{4}-\d\d-\d\d|right now|connected", AN.TOOL_NOTE_PREFIX.lower()),
          AN.TOOL_NOTE_PREFIX)


def main() -> int:
    groups = (
        ("the fast path", (t_a_tool_question_answers_with_no_model,
                           t_every_tool_and_family_can_be_asked_about,
                           t_a_question_that_names_no_tool_still_reaches_the_model,
                           t_the_fast_path_is_registered_read_only,
                           t_a_missing_module_falls_back_to_the_model)),
        ("the feature layer keeps its answers", (t_no_feature_row_is_hijacked,
                                                 t_the_collision_probe_keeps_the_features_answer)),
        ("the bounded note", (t_a_tool_turn_gets_a_bounded_note,
                              t_a_turn_that_names_nothing_is_byte_identical,
                              t_a_follow_up_keeps_the_tools_page,
                              t_the_note_is_placed_like_the_other_notes)),
        ("one vocabulary, two files", (t_the_two_files_use_the_same_tool_marker,)),
        ("what the answers must never be", (t_no_answer_reads_as_a_done_claim,
                                            t_no_answer_leaks_a_path_or_a_count)),
    )
    for title, tests in groups:
        print(f"\n--- {title} ---")
        for fn in tests:
            try:
                fn()
            except Exception:
                FAILED.append(fn.__name__)
                traceback.print_exc()
    print(f"\nPASS {len(PASSED)}   FAIL {len(FAILED)}")
    print(f"tools: {len(TP.PROFILES)}   families: {len(TP.FAMILIES)}   "
          f"checks: {len(PASSED) + len(FAILED)}")
    if FAILED:
        print("FAILED:")
        for name in FAILED:
            print(f"  {name}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
