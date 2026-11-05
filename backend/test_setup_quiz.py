#!/usr/bin/env python3
"""test_setup_quiz.py - Wave B, "Personalize Jarvis": the 25-question quiz,
its versioned setup.json, and the cardless progress route.

    python3 backend/test_setup_quiz.py

WHAT IS CHECKED, and why each check matters:

* the question set is 25 questions in the seven declared sections, every
  question carries a version, and the fourteen original ids are unchanged and
  still in their original order (the desktop fixture pins the same data);
* every new change kind resolves through the settings registry's OWN rows -
  `choice` keys in CHOICE_SETTINGS with a `to` the row really maps, `number`
  keys in NUMBER_SETTINGS inside the row's own low/high - so a question can
  never point at a setter that does not exist;
* the personality ids and the voice-speed words are the modules' own lists,
  not a second hand-typed copy, so a renamed preset fails here;
* `setup.json` schema 2: a partial retake MERGES the answers (the state-loss
  bug this wave fixes), `completed_version`/`runs`/`dismissed_at` behave, and
  an old three-key file still reads as version 1 with `completed_version` 1 -
  the truth that makes the first launch after deploy one correct offer.
  DEF-043 (2026-11-04): `completed_version` moves only when every question has
  an answer, so a partial apply leaves the offer, the HUD banner and the chat
  line running;
* `progress()` writes ONLY the quiz's own place: a non-object and an entry
  with neither `question` nor `dismiss` are refused, a bogus draft answer is
  cleaned away, an explicit empty draft clears it, and no other key moves;
* `progress()` is desktop-only (403 from another device, fail closed) and
  `POST /api/setup/progress` is wired behind the same origin/token gate as
  every other write, reading nothing before both pass;
* "Keep current settings" marks the question set complete and touches no
  setting and no answer - `apply()` is never called (monkeypatched to raise);
* the new code imports no model lane, no network and no subprocess, never
  calls `apply()` or a setter from `progress()`, never touches the taint
  latch, and `_run_setup_quiz`'s body holds no "confirm" (the pin that keeps
  the chat tool from ever applying);
* `setup_state_note()` is ONE line, appears only while the quiz is unfinished
  AND the "Personalize Jarvis" notification switch is on (DEF-044,
  2026-11-04), and the `setup_quiz` tool lists, explains from the real plan,
  and stages a draft while never applying.

No network, no model, no microphone, no owner's PC. Runs in repo mode; the
suite gives it a temporary settings folder.
"""
from __future__ import annotations

import ast
import inspect
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO, require_shipped  # noqa: E402

require_shipped("jarvis_setup.py", "jarvis_agent.py")

_TMP = tempfile.mkdtemp(prefix="jarvis-setup-quiz-")
os.environ["OPENJARVIS_CONFIG_DIR"] = _TMP

import jarvis_setup as S  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


SETUP = Path(_TMP) / "setup.json"


def _fresh(saved=None):
    """A known setup.json (or none at all)."""
    if saved is None:
        if SETUP.exists():
            SETUP.unlink()
        return
    SETUP.write_text(json.dumps(saved), encoding="utf-8")


def _read():
    return json.loads(SETUP.read_text(encoding="utf-8"))


def _legacy(answers, completed=True):
    doc = {"answers": dict(answers), "outcomes": []}
    if completed:
        doc["completed_at"] = 1700000000.25
    return doc


def a_reader(ch):
    """A current value that is NOT the change's target, so a plan shows it."""
    kind = str(ch.get("kind") or "")
    if kind == "bool":
        return not bool(ch.get("to"))
    if kind == "choice":
        setting = str(ch.get("setting"))
        if setting == "small_approvals":
            return ch.get("to") != "ask"
        if setting == "voice_speed":
            return "normal" if ch.get("to") != "normal" else "faster"
        if setting == "antislop_mode":
            return "after" if ch.get("to") != "after" else "during"
        if setting == "personality":
            return "warm_peer" if ch.get("to") != "warm_peer" else "classic_butler"
        return None
    if kind == "number":
        return 90 if int(ch.get("to")) != 90 else 60
    if kind == "asks_first":
        return {"tier": "auto", "asks": False}
    if kind == "reading_tool" or kind == "animal" or kind == "sky_show":
        return not bool(ch.get("to"))
    if kind == "manner":
        return "plain"
    if kind == "card_mode":
        return "always_full"
    if kind == "provider":
        return "duckduckgo"
    return None


def _ok(ch):
    return {"ok": True, "waiting": False, "message": "called"}


class FakeHandler:
    sent = None
    client_address = ("127.0.0.1", 5555)

    class _Conn:
        def getsockname(self):
            return ("127.0.0.1", 4719)

    connection = _Conn()

    def __init__(self, path, body=b"{}", token=True):
        self.path, self.body, self.token = path, body, token
        self.reads = 0
        FakeHandler.sent = None

    def _send(self, code, out, **k):
        FakeHandler.sent = (code, out)

    def do_GET(self):
        FakeHandler.sent = ("orig-get", None)

    def do_POST(self):
        FakeHandler.sent = ("orig-post", None)

    def read_body(self):
        self.reads += 1
        return self.body


# ---------------------------------------------------------------------------
#   1. 25 questions, 7 sections, versions, and the original 14 untouched
# ---------------------------------------------------------------------------

#: The fourteen questions that shipped before Wave B, in their original order.
#: This is the pin that says a retake of the old quiz keeps working: the ids
#: are what `setup.json` stores, so they may never be renamed or reordered.
EXISTING_14 = ("talk_style", "humour", "carefulness", "learning", "reading_tools",
               "web_search", "search_asking", "search_provider", "screen_pictures",
               "notifications", "card_size", "voice", "animal_faces", "main_use")

#: The eleven Wave B added, every one mapping to a setter that already exists.
NEW_11 = ("personality", "antislop", "lights_without_card", "reworded_memories",
          "chat_history", "media_index", "small_approvals", "voice_speed",
          "one_moment", "live_idle_seconds", "bigger_model_hints")

#: Question count per section, in the card's order.
SECTION_COUNTS = {"talking": 5, "reading": 6, "learning": 5, "notifications": 1,
                  "voice": 4, "models": 2, "screen": 2}


def t_the_question_set_is_25_in_7_sections():
    ids = [q["id"] for q in S.QUESTIONS]
    check("the quiz is exactly 25 questions with unique ids",
          len(ids) == 25 and len(set(ids)) == 25, ids)
    sections = [sid for sid, _title in S.SECTIONS]
    check("there are seven sections with unique ids and titles",
          len(S.SECTIONS) == 7 and len(set(sections)) == 7
          and all(isinstance(title, str) and title for _sid, title in S.SECTIONS),
          S.SECTIONS)
    counts = {}
    for q in S.QUESTIONS:
        counts[q["section"]] = counts.get(q["section"], 0) + 1
    check("every question's section is one of the seven, and the counts match",
          set(counts) == set(sections) and counts == SECTION_COUNTS, counts)
    check("every question has an int version, 1..QUIZ_VERSION",
          all(isinstance(q.get("version"), int) and 1 <= q["version"] <= S.QUIZ_VERSION
              for q in S.QUESTIONS),
          [(q["id"], q.get("version")) for q in S.QUESTIONS])
    check("the fourteen original ids are unchanged and in their original order",
          tuple(q["id"] for q in S.QUESTIONS if q["id"] in EXISTING_14) == EXISTING_14,
          [q["id"] for q in S.QUESTIONS if q["id"] in EXISTING_14])
    check("the eleven added ids are exactly the ones Wave B names",
          {q["id"] for q in S.QUESTIONS} - set(EXISTING_14) == set(NEW_11),
          sorted({q["id"] for q in S.QUESTIONS} - set(EXISTING_14)))
    check("the original fourteen are version 1 and the eleven new ones are 2",
          all(q["version"] == 1 for q in S.QUESTIONS if q["id"] in EXISTING_14)
          and all(q["version"] == 2 for q in S.QUESTIONS if q["id"] in NEW_11),
          [(q["id"], q["version"]) for q in S.QUESTIONS])
    fixture = json.loads((REPO / "backend" / "fixtures" / "setup_questions.json")
                         .read_text(encoding="utf-8"))
    check("the generated fixture's count equals len(QUESTIONS)",
          fixture.get("count") == len(S.QUESTIONS)
          and fixture.get("version") == S.QUIZ_VERSION, fixture.get("count"))
    check("...and its questions carry the same ids, sections and versions",
          [row.get("id") for row in fixture.get("questions") or ()] == ids
          and [(row.get("section"), row.get("version"))
               for row in fixture.get("questions") or ()]
          == [(q["section"], q["version"]) for q in S.QUESTIONS],
          fixture.get("questions")[:1])


# ---------------------------------------------------------------------------
#   2. every change in the set maps to a registry row that really exists
# ---------------------------------------------------------------------------


def t_every_new_change_maps_to_a_real_setter():
    R = __import__("jarvis_settings_registry")
    choice_rows = {c.key: c for c in R.CHOICE_SETTINGS}
    number_rows = {n.key: n for n in R.NUMBER_SETTINGS}
    bad, choice_keys, number_keys = [], set(), set()
    for q in S.QUESTIONS:
        for option in q["options"]:
            for ch in option["changes"]:
                kind = str(ch.get("kind") or "")
                if kind == "choice":
                    key = str(ch.get("setting"))
                    choice_keys.add(key)
                    row = choice_rows.get(key)
                    if row is None:
                        bad.append(f"{q['id']}/{option['id']}: no ChoiceSetting {key!r}")
                        continue
                    if not isinstance(ch.get("to"), str):
                        bad.append(f"{q['id']}/{option['id']}: choice to is not a word")
                    elif R.choice_from_words(row, ch["to"]) is None:
                        bad.append(f"{q['id']}/{option['id']}: {ch['to']!r} is not one "
                                   f"of {key!r}'s own choices")
                elif kind == "number":
                    key = str(ch.get("setting"))
                    number_keys.add(key)
                    row = number_rows.get(key)
                    if row is None:
                        bad.append(f"{q['id']}/{option['id']}: no NumberSetting {key!r}")
                        continue
                    try:
                        value = int(ch.get("to"))
                    except (TypeError, ValueError):
                        bad.append(f"{q['id']}/{option['id']}: number to is not an int")
                        continue
                    low, high = row.low(), row.high()
                    if low is None or high is None:
                        bad.append(f"{q['id']}/{option['id']}: {key!r} has no range "
                                   f"on this tree, so it could not be checked")
                    elif not low <= value <= high:
                        bad.append(f"{q['id']}/{option['id']}: {value} is outside "
                                   f"{key!r}'s {low}..{high}")
    check("every choice and number change resolves through its own registry row",
          not bad, "\n".join(bad))
    check("the choice changes are exactly the four named settings",
          choice_keys == {"personality", "antislop_mode", "voice_speed",
                          "small_approvals"}, sorted(choice_keys))
    check("the number change is the one number setting",
          number_keys == {"live_idle_seconds"}, sorted(number_keys))
    check("a choice/number change's key is its setting, so two questions cannot "
          "plan it twice",
          S.change_key({"kind": "choice", "setting": "voice_speed", "to": "faster"})
          == "choice:voice_speed"
          and S.change_key({"kind": "number", "setting": "live_idle_seconds", "to": 60})
          == "number:live_idle_seconds", (S.change_key(
              {"kind": "choice", "setting": "voice_speed", "to": "faster"})))


# ---------------------------------------------------------------------------
#   3. the personality and voice-speed options are the modules' own lists
# ---------------------------------------------------------------------------


def t_personality_and_voice_speed_options_are_the_rows_own():
    M = __import__("jarvis_manner")
    R = __import__("jarvis_settings_registry")
    builtins = {p["id"]: p.get("title") for p in M.all_personalities()
                if p.get("builtin")}
    question = next(q for q in S.QUESTIONS if q["id"] == "personality")
    ids = [o["id"] for o in question["options"]]
    check("the personality options are exactly the ten built-in preset ids",
          set(ids) == set(builtins) and len(ids) == 10
          and len(set(ids)) == 10, (sorted(ids), sorted(builtins)))
    check("...and each label is that preset's own title",
          all(o["label"] == builtins.get(o["id"]) for o in question["options"]),
          [(o["id"], o["label"], builtins.get(o["id"]))
           for o in question["options"] if o["label"] != builtins.get(o["id"])])
    speed = next(q for q in S.QUESTIONS if q["id"] == "voice_speed")
    row = next(c for c in R.CHOICE_SETTINGS if c.key == "voice_speed")
    check("the voice-speed options are the row's own values",
          [o["id"] for o in speed["options"]] == ["slower", "normal", "faster"]
          and {o["id"] for o in speed["options"]} == set(row.options().values()),
          ([(o["id"], o["changes"]) for o in speed["options"]],
           sorted(set(row.options().values()))))
    mode = next(q for q in S.QUESTIONS if q["id"] == "antislop")
    antis = next(c for c in R.CHOICE_SETTINGS if c.key == "antislop_mode")
    offered = {ch["to"] for o in mode["options"] for ch in o["changes"]
               if ch.get("kind") == "choice"}
    check("the Anti-Slop modes offered are the row's own values",
          offered == set(antis.options().values()) == {"during", "after"}, offered)
    small = next(q for q in S.QUESTIONS if q["id"] == "small_approvals")
    row = next(c for c in R.CHOICE_SETTINGS if c.key == "small_approvals")
    values = {R.choice_from_words(row, o["id"]) for o in small["options"]}
    check("the small-approval options map onto the row's True/False values",
          values == {True, False}, values)


# ---------------------------------------------------------------------------
#   4. the merge-on-apply fix: a partial retake keeps every earlier answer
# ---------------------------------------------------------------------------


def t_a_partial_retake_keeps_every_earlier_answer():
    old = {"talk_style": "warm", "humour": "on", "carefulness": "strict",
           "card_size": "full", "voice": ["prompt_coach"]}
    _fresh(_legacy(old))
    code, _got = S.progress({"dismiss": True})
    dismissed = _read()["dismissed_at"]
    out = S.apply({"voice_speed": "faster"}, confirm=True, taint=lambda: False,
                  here=lambda: True, readers=a_reader,
                  appliers={"choice:voice_speed": _ok}, tier_of=lambda a: "ask")
    saved = S._read_saved()
    check("a partial retake keeps every answer it did not ask about",
          out["ok"] is True and all(saved["answers"].get(k) == v for k, v in old.items())
          and len(saved["answers"]) == 6 and saved["answers"]["voice_speed"] == "faster",
          (out, saved["answers"]))
    check("...records the run, and does NOT claim the question set is finished "
          "(DEF-043: only 6 of 25 are answered)",
          saved["version"] == S.SCHEMA_VERSION
          and saved["completed_version"] == 1
          and saved["completed_version"] < S.QUIZ_VERSION
          and saved["runs"] == 2 and saved["completed_at"] is not None, saved)
    check("...keeps the dismissal and clears the card's place",
          saved["dismissed_at"] == dismissed and saved["in_progress"] == {},
          (saved["dismissed_at"], dismissed, saved["in_progress"]))
    # A second apply of the SAME answer is still accepted - it is the owner
    # pressing Apply, not a change the plan found - so `runs` counts it too (3)
    # and no answer is lost. That is deliberate: `runs` is a run count.
    out = S.apply({"voice_speed": "faster"}, confirm=True, taint=lambda: False,
                  here=lambda: True, readers=lambda ch: "faster",
                  appliers={"choice:voice_speed": _ok}, tier_of=lambda a: "ask")
    saved = S._read_saved()
    check("a second apply of the same answer is accepted and counts another run",
          out["ok"] is True and saved["runs"] == 3
          and len(saved["answers"]) == 6, (out.get("error"), saved["runs"]))
    check("...and an unanswered question id is never invented",
          set(saved["answers"]) == set(old) | {"voice_speed"}, sorted(saved["answers"]))


class _AnyApplier(dict):
    """`appliers` that reports every planned change as made.

    The real setters are the settings registry's business; these checks are
    about WHICH answers count as a finished quiz, not about what each setter
    does once it is called."""

    def get(self, _key, _default=None):
        return _ok


def _all_answers() -> dict:
    """One valid answer for every one of the 25 questions."""
    return {q["id"]: (["all"] if q["multi"] else q["options"][0]["id"])
            for q in S.QUESTIONS}


def t_a_partial_apply_does_not_claim_the_quiz_is_finished():
    """DEF-043 (2026-11-04): a partial apply used to write
    `completed_version = QUIZ_VERSION`, so the launch offer, the HUD banner and
    the chat line all stopped while `answered_count()` still said 1 of 25."""
    import jarvis_agent as AG  # noqa: E402 - heavy, so only when needed
    _fresh()
    out = S.apply({"talk_style": "warm"}, confirm=True, taint=lambda: False,
                  readers=a_reader, appliers={"manner": _ok},
                  tier_of=lambda a: "ask")
    saved = S._read_saved()
    check("a partial apply saves the answer and counts the run, but claims no completion",
          out["ok"] is True and saved["answers"] == {"talk_style": "warm"}
          and saved["completed_version"] == 0 and saved["runs"] == 1, saved)
    st = S.state(readers=lambda ch: None)
    check("...so the first-open offer is still open (completed_version < version)",
          st["completed_version"] < S.QUIZ_VERSION and st["answered_count"] == 1, st)
    check("...and the chat line still says the quiz is unfinished",
          isinstance(AG.setup_state_note(), str)
          and "1 of 25 answered" in AG.setup_state_note(), AG.setup_state_note())
    # A partial retake of an OLDER completed file keeps what it did complete -
    # it is not dragged back to zero just because this run was partial.
    _fresh(_legacy({"talk_style": "warm", "humour": "on"}))
    out = S.apply({"card_size": "full"}, confirm=True, taint=lambda: False,
                  readers=a_reader, appliers={"card_mode": _ok},
                  tier_of=lambda a: "ask")
    saved = S._read_saved()
    check("...and a partial retake keeps the completed version the file already had",
          out["ok"] is True and saved["completed_version"] == 1
          and saved["completed_version"] < S.QUIZ_VERSION and saved["runs"] == 2,
          saved)


def t_a_complete_apply_still_marks_the_quiz_finished():
    """The other half of DEF-043: an apply with every question answered still
    marks the set complete, so a finished owner is never nagged."""
    import jarvis_agent as AG  # noqa: E402
    _fresh()
    out = S.apply(_all_answers(), confirm=True, taint=lambda: False,
                  readers=a_reader, appliers=_AnyApplier(),
                  tier_of=lambda a: "ask")
    saved = S._read_saved()
    check("answering every question marks the whole quiz finished",
          out["ok"] is True and S.answered_count(saved) == len(S.QUESTIONS)
          and saved["completed_version"] == S.QUIZ_VERSION, saved)
    st = S.state(readers=lambda ch: None)
    check("...so the offer and the banner stop, and the chat line costs no tokens",
          st["completed_version"] == S.QUIZ_VERSION
          and st["answered_count"] == len(S.QUESTIONS)
          and AG.setup_state_note() is None, st)


# ---------------------------------------------------------------------------
#   5. an old three-key file still reads as version 1
# ---------------------------------------------------------------------------


def t_an_old_three_key_file_reads_as_version_one():
    _fresh(_legacy({"talk_style": "warm", "humour": "on"}))
    saved = S._read_saved()
    check("a three-key file reads as version 1, completed_version 1, runs 1",
          saved["version"] == 1 and saved["completed_version"] == 1
          and saved["runs"] == 1 and saved["dismissed_at"] is None
          and saved["in_progress"] == {}, saved)
    check("...and state() reports the QUESTION-SET version, not the file's",
          S.state(readers=lambda ch: None)["version"] == S.QUIZ_VERSION
          and S.state(readers=lambda ch: None)["completed_version"] == 1,
          S.state(readers=lambda ch: None)["completed_version"])
    _fresh(_legacy({"talk_style": "warm"}, completed=False))
    saved = S._read_saved()
    check("a file with no completed_at reads as completed_version 0, runs 0",
          saved["completed_version"] == 0 and saved["runs"] == 0
          and saved["completed_at"] is None, saved)
    SETUP.write_text("{not json at all", encoding="utf-8")
    saved = S._read_saved()
    check("a damaged file reads as the empty defaults and never raises",
          saved["answers"] == {} and saved["completed_at"] is None
          and saved["completed_version"] == 0 and saved["in_progress"] == {},
          saved)
    SETUP.write_text("[1, 2, 3]", encoding="utf-8")
    check("a file that is not an object reads as the empty defaults",
          S._read_saved()["answers"] == {}, S._read_saved())
    # Reading must never write: a GET on an old file leaves it byte-identical.
    raw = json.dumps(_legacy({"talk_style": "warm"}))
    SETUP.write_text(raw, encoding="utf-8")
    S.state(readers=lambda ch: None)
    check("reading an old file does not upgrade or rewrite it",
          SETUP.read_text(encoding="utf-8") == raw, SETUP.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
#   6. progress writes ONLY the quiz's own place
# ---------------------------------------------------------------------------


def t_progress_writes_only_progress():
    _fresh({"version": 2, "completed_version": 2, "runs": 4,
            "dismissed_at": 111.5, "in_progress": {},
            "answers": {"talk_style": "warm"}, "completed_at": 100.25,
            "outcomes": [{"setting": "manner", "state": "changed"}]})
    before = _read()
    code, got = S.progress({"section": "learning", "question": "reworded_memories",
                            "draft_answers": {"reworded_memories": "on"}})
    after = _read()
    check("progress records the place and the draft",
          code == 200 and got["in_progress"]["question"] == "reworded_memories"
          and got["in_progress"]["section"] == "learning"
          and got["in_progress"]["draft_answers"] == {"reworded_memories": "on"},
          got)
    check("progress changes nothing else in the file",
          all(after[k] == before[k] for k in
              ("version", "completed_version", "runs", "dismissed_at",
               "answers", "completed_at", "outcomes")),
          {k: (before[k], after[k]) for k in before if before[k] != after[k]})
    check("progress refuses a body that is not an object",
          S.progress("nope")[0] == 400, S.progress("nope"))
    check("progress refuses an entry with neither question nor dismiss",
          S.progress({"section": "learning"})[0] == 400,
          S.progress({"section": "learning"}))
    check("progress refuses a question that is not in the quiz",
          S.progress({"question": "not_a_question"})[0] == 400,
          S.progress({"question": "not_a_question"}))
    code, got = S.progress({"question": "talk_style",
                            "draft_answers": {"not_a_question": "x",
                                              "talk_style": "plain"}})
    check("a bogus draft answer is cleaned away, a real one is kept (and the "
          "staged one merged, not lost)",
          code == 200
          and "not_a_question" not in got["in_progress"]["draft_answers"]
          and got["in_progress"]["draft_answers"]
          == {"talk_style": "plain", "reworded_memories": "on"},
          got)
    code, got = S.progress({"question": "talk_style", "draft_answers": {}})
    check("an explicit empty draft clears it (\"take it again\")",
          code == 200 and got["in_progress"]["draft_answers"] == {}, got)
    code, got = S.progress({"dismiss": True})
    check("dismiss records dismissed_at and leaves the answers alone",
          code == 200 and isinstance(got["dismissed_at"], float)
          and _read()["answers"] == {"talk_style": "warm"}, got)
    # A corrupt file still gets a valid place: the reader defaults, the writer
    # upgrades, and nothing raises.
    SETUP.write_text("{broken", encoding="utf-8")
    code, got = S.progress({"question": "one_moment"})
    check("progress over a damaged file writes a clean schema-2 document",
          code == 200 and _read()["version"] == S.SCHEMA_VERSION
          and _read()["in_progress"]["question"] == "one_moment", code)


# ---------------------------------------------------------------------------
#   7. progress is desktop-only
# ---------------------------------------------------------------------------


def t_progress_is_desktop_only():
    _fresh(_legacy({"talk_style": "warm"}))
    raw = SETUP.read_text(encoding="utf-8")
    code, out = S.handle_post_progress({"question": "talk_style"},
                                       peer="100.64.0.9", local="100.64.0.1")
    check("a progress request from another device is 403 and writes nothing",
          code == 403 and out.get("pc_only") is True
          and SETUP.read_text(encoding="utf-8") == raw, (code, out))
    code, out = S.handle_post_progress({"question": "talk_style"},
                                       peer=None, local=None)
    check("...and the documented in-process call (this PC) is 200",
          code == 200 and out.get("in_progress", {}).get("question") == "talk_style",
          (code, out))

    class H(FakeHandler):
        pass
    S.install(H, origin_ok=lambda self: True, token_ok=lambda self: True,
              read_body=lambda self: b"{}")
    h = H("/api/setup/nope")
    h.do_POST()
    check("an unknown /api/setup path still reaches the server's own handler",
          FakeHandler.sent == ("orig-post", None), FakeHandler.sent)


# ---------------------------------------------------------------------------
#   8. the progress route is wired behind the same gate as every write
# ---------------------------------------------------------------------------


def t_the_progress_route_is_wired_and_guarded():
    class H(FakeHandler):
        pass
    reads = []

    def read_body(handler):
        reads.append(handler.path)
        return handler.body

    origin_ok = {"v": True}
    msg = S.install(H, origin_ok=lambda self: origin_ok["v"],
                    token_ok=lambda self: self.token, read_body=read_body)
    check("install() lists the questionnaire and names the progress route",
          "setup" in msg.lower() and "progress" in msg.lower(), msg)

    h = H("/api/setup/progress", body=json.dumps({"question": "talk_style"}).encode(),
          token=False)
    h.do_POST()
    check("no token: 401 before the body is read",
          FakeHandler.sent[0] == 401 and reads == [], (FakeHandler.sent, reads))

    h = H("/api/setup/progress", body=json.dumps({"question": "talk_style"}).encode())
    origin_ok["v"] = False
    try:
        h.do_POST()
    finally:
        origin_ok["v"] = True
    check("a cross-origin request: 403 before the body is read",
          FakeHandler.sent[0] == 403 and reads == [], (FakeHandler.sent, reads))

    h = H("/api/setup/progress", body=b"{not json")
    h.do_POST()
    check("a body that is not JSON: 400, not a crash", FakeHandler.sent[0] == 400,
          FakeHandler.sent)

    old_here, S._here = S._here, lambda peer, local: True
    try:
        h = H("/api/setup/progress",
              body=json.dumps({"question": "talk_style",
                               "draft_answers": {"talk_style": "plain"}}).encode())
        h.do_POST()
        sent = FakeHandler.sent
    finally:
        S._here = old_here
    check("a valid progress POST from the PC: 200 with the recorded place",
          sent[0] == 200 and sent[1].get("in_progress", {}).get("question")
          == "talk_style", sent)

    class H2(FakeHandler):
        pass
    S.install(H2, origin_ok=lambda self: True, token_ok=lambda self: True,
              read_body=lambda self: self.body)
    check("install() is idempotent (no second wrap of the handler)",
          "already on" in S.install(H2, origin_ok=lambda self: True,
                                    token_ok=lambda self: True,
                                    read_body=lambda self: self.body))


# ---------------------------------------------------------------------------
#   9. "Keep current settings" touches no setting and no answer
# ---------------------------------------------------------------------------


def t_keep_current_settings_touches_no_setting():
    _fresh({"version": 1, "answers": {"talk_style": "warm", "humour": "on"},
            "completed_at": 100.25, "outcomes": []})
    before = _read()
    old_apply = S.apply
    S.apply = lambda *a, **k: (_ for _ in ()).throw(AssertionError(
        "keep_current must never call apply()"))
    try:
        code, got = S.progress({"keep_current": True})
    finally:
        S.apply = old_apply
    after = _read()
    check("keep_current answers 200 and marks the question set complete",
          code == 200 and got.get("completed_version") == S.QUIZ_VERSION
          and after["completed_version"] == S.QUIZ_VERSION, (code, got))
    check("...and touches no answer, no outcome and no completion time",
          after["answers"] == before["answers"]
          and after["outcomes"] == before["outcomes"]
          and after["completed_at"] == before["completed_at"], after)
    check("...and the first-open offer is silenced (state says complete)",
          S.state(readers=lambda ch: None)["completed_version"] == S.QUIZ_VERSION,
          S.state(readers=lambda ch: None)["completed_version"])
    check("keep_current sets dismissed_at so a stale dismissal cannot nag later",
          isinstance(after["dismissed_at"], float), after["dismissed_at"])


# ---------------------------------------------------------------------------
#   10. what the new code must never do
# ---------------------------------------------------------------------------


def _functions(tree, name):
    return [n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]


def t_no_model_switch_no_network_no_gate_in_the_new_code():
    src = Path(S.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    imports, calls = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                calls.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                calls.add(fn.attr)
    check("jarvis_setup still imports no model lane, network or subprocess",
          not (imports & {"jarvis_models", "socket", "http", "urllib", "requests",
                          "subprocess", "jarvis_presets"}), imports)
    check("...and never sets or clears the gate's latch, switches a model or "
          "applies a preset",
          not (calls & {"latch_taint", "clear_taint", "switch_model",
                        "apply_preset", "approve_check"}),
          sorted(calls & {"latch_taint", "clear_taint", "switch_model",
                          "apply_preset", "approve_check"}))
    progress_fns = _functions(tree, "progress")
    check("progress() is one function whose body reads no taint latch and calls "
          "no apply()",
          len(progress_fns) == 1
          and not any(isinstance(n, ast.Call) and (
              (isinstance(n.func, ast.Name) and n.func.id in
               ("_tainted", "apply", "latch_taint"))
              or (isinstance(n.func, ast.Attribute) and n.func.attr in
                  ("apply", "taint_active", "latch_taint")))
              for n in ast.walk(progress_fns[0])),
          ast.dump(progress_fns[0])[:200] if progress_fns else "no progress()")
    # The chat tool can READ the quiz and STAGE a draft, and can never apply.
    import jarvis_agent as AG  # noqa: E402 - heavy, so only this test imports it
    run_src = inspect.getsource(AG._run_setup_quiz)
    check("_run_setup_quiz's body contains no \"confirm\" at all",
          "confirm" not in run_src, run_src[:200])
    run_tree = ast.parse(run_src)
    run_calls = {n.func.attr if isinstance(n.func, ast.Attribute) else
                 n.func.id for n in ast.walk(run_tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name,
                                                                   ast.Attribute))}
    check("...and it never calls apply() or a setter, only reads and progress",
          "apply" not in run_calls and "set" not in run_calls
          and "progress" in run_calls, sorted(run_calls))
    check("the setup tool is registered read-only under the gate's own skill_list "
          "action, in the settings group and the not-reading set",
          "setup_quiz" in AG.TOOLS
          and AG.TOOLS["setup_quiz"].gate_lookup_name({}) == "skill_list"
          and any("setup_quiz" in members for _g, _w, members in AG.TOOL_GROUPS)
          and "setup_quiz" in AG._NOT_READING,
          (AG.TOOLS.get("setup_quiz"), AG.TOOL_GROUPS))


# ---------------------------------------------------------------------------
#   11. the prompt line: one honest line, only while the quiz is unfinished
# ---------------------------------------------------------------------------


def t_the_setup_note_is_one_honest_line():
    import jarvis_agent as AG  # noqa: E402
    _fresh(_legacy({"talk_style": "warm"}))
    note = AG.setup_state_note()
    check("an unfinished quiz adds ONE line, and it says where the owner is",
          isinstance(note, str) and "\n" not in note
          and "Personalize Jarvis" in note and "of 25 answered" in note
          and "nothing in chat may apply" in note, note)
    S.progress({"question": "reworded_memories"})
    note = AG.setup_state_note()
    check("...and it names the question the card is open at",
          isinstance(note, str)
          and "reword it" in note, note)
    _fresh({"version": 2, "completed_version": S.QUIZ_VERSION, "runs": 1,
            "dismissed_at": None, "in_progress": {},
            "answers": {"talk_style": "warm"}, "completed_at": 100.25,
            "outcomes": []})
    check("a finished quiz costs no tokens at all", AG.setup_state_note() is None,
          AG.setup_state_note())
    msgs = [{"role": "user", "content": "hi"}]
    _fresh(_legacy({"talk_style": "warm"}))
    dressed = AG.with_setup_state_note(msgs)
    check("...the line sits just before the newest user message, never first",
          len(dressed) == 3 and dressed[0]["role"] == "system"
          and dressed[0]["content"] == AG.LANE_SYSTEM
          and "Personalize Jarvis" in dressed[1]["content"]
          and dressed[2] is msgs[0], dressed[-3:])
    check("...and a list with no user message is returned as a plain copy",
          AG.with_setup_state_note([{"role": "system", "content": "x"}])
          == [{"role": "system", "content": "x"}],
          AG.with_setup_state_note([]))


def t_the_setup_note_obeys_the_personalize_switch():
    """DEF-044 (2026-11-04): the eighth notification switch, "Personalize
    Jarvis", gated only the launch toast. The every-turn chat line read
    `setup.json` alone, so an owner who switched the reminder OFF was still
    told in chat that the quiz was unfinished. The switch is one value in
    `jarvis_notify_prefs`; the line must read it, both ways."""
    import jarvis_agent as AG  # noqa: E402
    import jarvis_framework as FW  # noqa: E402 - the reader the switch lives in
    _fresh(_legacy({"talk_style": "warm"}))
    cfg = Path(_TMP) / "jarvis-framework.toml"
    keep_explicit = os.environ.get("JARVIS_FRAMEWORK_TOML")

    def _write_switch(on: bool) -> None:
        cfg.write_text("[notifications]\nsetup = %s\n"
                       % ("true" if on else "false"), encoding="utf-8")
        # SAY WHICH CONFIG IS THE ONE. `run_suites.py` gives every suite a
        # `JARVIS_FRAMEWORK_TOML` pointing at the runner's own copy, and
        # `jarvis_framework.config_path()` prefers that explicit override over
        # `CONFIG_DIR/jarvis-framework.toml`. Without this line the switch is
        # written to a file the reader never opens, so this check passed when
        # the suite was run directly and failed under the runner (CI's
        # `backend` job) - the same code, two answers. The documented way for a
        # suite to choose its config is to set the variable itself
        # (`test_rebuilt.py` does the same).
        os.environ["JARVIS_FRAMEWORK_TOML"] = str(cfg)
        FW.reload_framework()

    try:
        # No settings file at all = the module's own default, which is ON.
        check("the switch's default (nothing written): an unfinished quiz still "
              "adds its one line",
              isinstance(AG.setup_state_note(), str)
              and "Personalize Jarvis" in AG.setup_state_note(),
              AG.setup_state_note())
        _write_switch(False)
        S.progress({"question": "reworded_memories",
                    "draft_answers": {"reworded_memories": "on"}})
        check("switch OFF: the chat line is not added, even while the quiz is "
              "unfinished and a draft is open",
              S._read_saved()["in_progress"].get("question") == "reworded_memories"
              and AG.setup_state_note() is None, AG.setup_state_note())
        msgs = [{"role": "system", "content": AG.LANE_SYSTEM},
                {"role": "user", "content": "what's left in my setup?"}]
        dressed = AG.with_setup_state_note(msgs)
        check("...and the turn gets the plain copy, with no such system message",
              dressed == msgs and dressed[0] is msgs[0]
              and not [m for m in dressed
                       if isinstance(m, dict)
                       and "Personalize Jarvis" in str(m.get("content") or "")],
              dressed)
        _write_switch(True)
        check("switch back ON: the line returns from the same reader",
              isinstance(AG.setup_state_note(), str)
              and "Personalize Jarvis" in AG.setup_state_note(),
              AG.setup_state_note())
    finally:
        if keep_explicit is None:
            os.environ.pop("JARVIS_FRAMEWORK_TOML", None)
        else:
            os.environ["JARVIS_FRAMEWORK_TOML"] = keep_explicit
        try:
            cfg.unlink()
        except OSError:
            pass
        FW.reload_framework()


# ---------------------------------------------------------------------------
#   12. the chat tool: list, explain from the real plan, stage, never apply
# ---------------------------------------------------------------------------


def t_the_setup_quiz_tool_reads_explains_and_stages():
    import jarvis_agent as AG  # noqa: E402
    _fresh(_legacy({"talk_style": "warm"}))
    listed = AG._run_setup_quiz({})
    check("the tool lists the sections and every question with its place",
          listed["ok"] is True and len(listed["questions"]) == 25
          and len(listed["sections"]) == 7
          and listed["answered_count"] == 1
          and listed["answers"] == {"talk_style": "warm"}, listed)
    explained = AG._run_setup_quiz({"question": "personality"})
    check("the tool explains one question's every option from the real plan",
          explained["ok"] is True and len(explained["options"]) == 10
          and all(isinstance(row.get("effects"), list)
                  for row in explained["options"])
          and explained["question"]["title"] == "Which personality should Jarvis have?",
          explained.get("question"))
    check("...and an option that is already set is reported as skipped, not planned",
          any("already" in reason for row in explained["options"]
              for reason in row["skipped"]), explained["options"][:1])
    staged = AG._run_setup_quiz({"question": "reworded_memories",
                                 "staged_answer": "on"})
    saved = S._read_saved()
    check("the tool stages a draft choice in setup.json",
          staged["ok"] is True and staged["staged"]["recorded"] is True
          and saved["in_progress"]["draft_answers"] == {"reworded_memories": "on"},
          (staged.get("staged"), saved["in_progress"]))
    check("...and the answers are still the owner's applied ones, untouched",
          saved["answers"] == {"talk_style": "warm"}, saved["answers"])
    bad = AG._run_setup_quiz({"question": "voice_speed", "staged_answer": "warp"})
    check("the tool refuses an option that is not that question's",
          bad["ok"] is False and "not one of this question's options" in bad["error"],
          bad)
    missing = AG._run_setup_quiz({"question": "not a real question"})
    check("the tool refuses a name that matches no single question, and lists them",
          missing["ok"] is False and len(missing["questions"]) == 25, missing)
    check("the tool's own words say the owner applies, never chat",
          "applies" in AG._setup_quiz_tool_text().lower()
          or "pressing apply" in AG._setup_quiz_tool_text().lower(),
          AG._setup_quiz_tool_text())


def t_dress_messages_carries_the_line_only_while_unfinished():
    """The WIRING, not only the helper (2026-11-04).

    `t_the_setup_note_is_one_honest_line` above proves the line's words and
    `with_setup_state_note`'s placement. Nothing proved that `dress_messages` -
    the one function that orders every note, and the one a real turn goes
    through - still calls it. That wiring is what a refactor drops silently, and
    it is the exact half that made five other suites' word-for-word prompt pins
    start failing on 2026-11-04: they now give themselves a FINISHED quiz, so
    those pins can only stay byte-exact while THIS check says the line really
    arrives when the quiz is unfinished.
    """
    import jarvis_agent as AG  # noqa: E402
    msgs = [{"role": "system", "content": AG.LANE_SYSTEM},
            {"role": "user", "content": "what does the Personalize quiz ask?"}]
    _fresh(_legacy({"talk_style": "warm"}))
    line = AG.setup_state_note()
    dressed = AG.dress_messages(msgs, manner=None)
    quiz = [m for m in dressed
            if isinstance(m, dict) and "Personalize Jarvis" in str(m.get("content") or "")]
    check("an unfinished quiz: dress_messages carries the line, once",
          isinstance(line, str) and len(quiz) == 1
          and quiz[0]["content"] == line and quiz[0]["role"] == "system",
          (line, quiz))
    if quiz:
        check("...and it sits after the rules and before the question it is about",
              dressed.index(quiz[0]) > dressed.index(msgs[0])
              and dressed.index(quiz[0]) < len(dressed) - 1
              and dressed[-1] == msgs[-1], dressed)
    else:
        check("...and it sits after the rules and before the question it is about",
              False, "there is no line to place")
    here = next(m for m in dressed if m is msgs[0])
    check("...never first, and the caller's own messages are not changed",
          dressed[0] is here and msgs[1] == {"role": "user",
                                             "content": "what does the Personalize quiz ask?"},
          dressed)
    _fresh({"version": 2, "completed_version": S.QUIZ_VERSION, "runs": 1,
            "dismissed_at": None, "in_progress": {}, "answers": {},
            "completed_at": 1.0, "outcomes": []})
    finished = AG.dress_messages(msgs, manner=None)
    check("a finished quiz: dress_messages adds no such line, and no extra message",
          not [m for m in finished
               if isinstance(m, dict) and "Personalize Jarvis" in str(m.get("content") or "")]
          and len(finished) == len(msgs), finished)


if __name__ == "__main__":
    for fn in (t_the_question_set_is_25_in_7_sections,
               t_every_new_change_maps_to_a_real_setter,
               t_personality_and_voice_speed_options_are_the_rows_own,
               t_a_partial_retake_keeps_every_earlier_answer,
               t_a_partial_apply_does_not_claim_the_quiz_is_finished,
               t_a_complete_apply_still_marks_the_quiz_finished,
               t_an_old_three_key_file_reads_as_version_one,
               t_progress_writes_only_progress,
               t_progress_is_desktop_only,
               t_the_progress_route_is_wired_and_guarded,
               t_keep_current_settings_touches_no_setting,
               t_no_model_switch_no_network_no_gate_in_the_new_code,
               t_the_setup_note_is_one_honest_line,
               t_the_setup_note_obeys_the_personalize_switch,
               t_dress_messages_carries_the_line_only_while_unfinished,
               t_the_setup_quiz_tool_reads_explains_and_stages):
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
