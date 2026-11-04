#!/usr/bin/env python3
"""test_self_knowledge.py - the self-awareness audit's phase-2 gaps, driven.

    python3 backend/test_self_knowledge.py

WHAT THIS PROVES (2026-11-04, the self-awareness audit's gaps 1, 9 and the
"knows partly" row):

  1. THE TEN UNREACHABLE SUBSYSTEMS REALLY ANSWER, without the model. All ten
     families the audit drove - "what are you running on", "which graphics
     cards do you have", "what is your context window", "how fast are you",
     "how much memory do you have", "how much storage is left", "what jobs can
     you schedule", "can you read my files", "can you see my screen", "do you
     have access to my calendar" - answered NOTHING and went to the language
     model. Every one is driven through the real matcher here and must come
     back with the owning module's own value.
  2. EACH ANSWER IS THE OWNER'S OWN READ, not a typed number: the preset row
     and hardware read, the speed record, the memory store, the disk reader,
     the two scheduler registries. A fixture is flipped at the reader's own
     seam and the answer must move with it.
  3. THE PAIR TABLE ANSWERS WHAT TWO THINGS DO TOGETHER. Ten hand-built rows,
     each one proven by a real interaction in a real module (the file:line is
     beside each row in `jarvis_quick.py`). Every row's phrase must be answered
     by the row - never the model - and the answer must be built from the live
     read at answer time, so flipping either value changes it.
  4. A COMBINATION NOBODY WROTE A RULE FOR FALLS THROUGH. "does web search
     work", "is the second card on" and "do two settings ever conflict" must
     NOT be answered by an invented rule.
  5. EVERY ONE OF THE 43 SWITCHABLE FEATURES REPORTS A LIVE ON/OFF, or says in
     words that it cannot read that switch - never "there is no switch" for a
     feature that really has a control.
  6. THE WIDER CAPABILITY ANSWERS: files, screen and the calendar each answer
     "can you..." from the real check - a true yes when the tool/setting is on,
     the honest refusal when it is off.
  7. A TWO-SETTING CHANGE says the interaction in one line and changes
     NOTHING - one card per change is the rule, and no approval behaviour is
     touched.

No network, no model, no live install: the config folder is a throwaway temp
directory, and every switch file the tests write is put back.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-self-knowledge-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_MEMORY_DB"] = str(_TMP / "config" / "memory.db")
os.environ["JARVIS_RECEIPTS_DB"] = str(_TMP / "config" / "receipts.db")
(_TMP / "config").mkdir(parents=True, exist_ok=True)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402

require_shipped("jarvis_quick.py", "jarvis_self_portrait.py",
                "jarvis_feature_guide.py", "jarvis_model_knowledge.py",
                "jarvis_second_card.py", "jarvis_search.py")
sys.path.append(str(HERE / "rebuilt"))

import jarvis_auto_learn as AL  # noqa: E402
import jarvis_feature_guide as FG  # noqa: E402
import jarvis_hardware as HW  # noqa: E402
import jarvis_jobs as JOBS  # noqa: E402
import jarvis_live as LIVE  # noqa: E402
import jarvis_model_knowledge as K  # noqa: E402
import jarvis_notify_prefs as NP  # noqa: E402
import jarvis_pc_facts as PC  # noqa: E402
import jarvis_phone_notifications as PN  # noqa: E402
import jarvis_presets as PR  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_schedule as SCH  # noqa: E402
import jarvis_search as SEARCH  # noqa: E402
import jarvis_second_card as SECOND  # noqa: E402
import jarvis_self_portrait as SP  # noqa: E402
import jarvis_settings_registry as REG  # noqa: E402

PASSED, FAILED = [], []


class _Sched:
    def mark_command(self, text):
        pass


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def answer(words):
    return Q.answer(words, sched=_Sched())


def said(words) -> str:
    got = answer(words)
    return str(getattr(got, "reply", "") or "")


# ---------------------------------------------------------------------------
#   1. The ten unreachable families, driven through the real matcher
# ---------------------------------------------------------------------------

#: (phrase, answer builder name) for every family the audit measured as going
#: to the model. "how much disk space" is the one bare form; the others are
#: the audit's own sentences plus the natural variants.
TEN = (
    ("what are you running on", "how_running"),
    ("what hardware do you have", "how_running"),
    ("which graphics cards do you have", "how_running"),
    ("which graphics card are you using", "how_running"),
    ("what graphics cards do you have", "how_running"),
    ("what are you running on right now", "how_running"),
    ("what is your context window", "how_context"),
    ("how much context do you have", "how_context"),
    ("how big is your context window", "how_context"),
    ("how fast are you", "how_fast"),
    ("how many tokens per second", "how_fast"),
    ("how fast do you run", "how_fast"),
    ("how much memory do you have", "how_memory"),
    ("how many things do you remember", "how_memory"),
    ("how many memories do you have", "how_memory"),
    ("what do you remember", "how_memory"),
    ("how much storage is left", "pc_facts"),
    ("how much disk space", "pc_facts"),
    ("how much disk space is left", "pc_facts"),
    ("how much storage do you have left", "pc_facts"),
    ("what jobs can you schedule", "how_jobs"),
    ("what can you schedule", "how_jobs"),
    ("what can you run on a schedule", "how_jobs"),
)


def every_family_answers_without_the_model():
    """THE AUDIT'S OWN SENTENCES. Before this change every one went to the model."""
    for words, want in TEN:
        got = Q.match(words)
        check(f"{words!r} is answered by {want}, not the model",
              got is not None and got.name == want,
              got.name if got else "went to the model")
        reply = said(words)
        check(f"... and it says something real", bool(reply.strip()), reply)
        check(f"... and it is not an apology for having no answer",
              "I don't have" not in reply and "I do not have access" not in reply,
              reply[:200])


def answers_are_the_owners_own_read():
    """A FIXTURE FLIP AT THE READER'S OWN SEAM MOVES THE ANSWER."""
    # -- context and speed: the preset CHOICE is the real file, so flip it.
    choice = Path(PR._choice_path())
    had = choice.read_bytes() if choice.is_file() else None
    try:
        choice.parent.mkdir(parents=True, exist_ok=True)
        choice.write_text(json.dumps({"preset": "coding"}), encoding="utf-8")
        ctx = said("what is your context window")
        coding = Q._preset_row("coding") or {}
        want_ctx = int(coding.get("context") or 0)
        check("the context answer is the chosen preset's own number",
              f"{want_ctx:,} tokens" in ctx, f"{ctx} / {want_ctx}")
        check("... and names the preset it came from", "Coding" in ctx, ctx)
        running = said("what are you running on")
        check("the running answer names the same preset's model",
              str(coding.get("model") or "") in running, running[:300])
        want_speed = K.bench_for(str(coding.get("model") or "")) or {}
        speed = said("how fast are you")
        if isinstance(want_speed.get("tok_s"), (int, float)):
            check("the speed answer quotes the chosen model's measured tokens a second",
                  f"{float(want_speed['tok_s']):.1f}" in speed, f"{speed} / {want_speed}")
            check("... and says where that figure came from",
                  str(want_speed.get("source") or "")[:20] in speed, speed)
    finally:
        if had is None:
            choice.unlink(missing_ok=True)
        else:
            choice.write_bytes(had)

    # -- context also follows a preset row the PC is handed, not a constant.
    real_row, real_model = Q._preset_row, Q._model_record
    try:
        Q._preset_row = lambda _pid: {"title": "Probe", "model": "probe:1b",
                                      "lane": {"card": "Probe card"},
                                      "context": 123456}
        Q._model_record = lambda: "probe:1b"
        ctx = said("what is your context window")
        check("a flipped preset row moves the context answer",
              "123,456 tokens" in ctx, ctx)
        running = said("what are you running on")
        check("... and the running answer too",
              "probe:1b" in running and "Probe card" in running, running[:300])
    finally:
        Q._preset_row, Q._model_record = real_row, real_model

    # -- hardware: the hardware read is the source, and it names every card.
    cards = [c for c in (HW.status().get("cards") or ()) if isinstance(c, dict)]
    reply = said("what hardware do you have")
    for card in cards:
        check(f"the hardware answer names the real card {card.get('name')!r}",
              str(card.get("name") or "") in reply, reply[:300])
    check("... and counts them from the same read",
          f"{len(cards)} graphics" in reply, reply[:200])

    # -- speed: jarvis_model_knowledge.bench_for is the record it quotes.
    real_model = Q._model_record
    probe_model = str(K.current_model() or "qwen3.5:9b")
    try:
        Q._model_record = lambda: probe_model
        bench = K.bench_for(probe_model)
        speed = said("how fast are you")
    finally:
        Q._model_record = real_model
    if bench and isinstance(bench.get("tok_s"), (int, float)):
        check("the speed answer quotes the measured tokens a second",
              f"{float(bench['tok_s']):.1f}" in speed, f"{speed} / {bench}")
        check("... and names the model it was measured for",
              probe_model in speed, speed)
    else:
        check("with no measurement the speed answer says so, in those words",
              "not measured" in speed.lower(), speed)
    check("the speed answer never invents a number when there is none",
          bool(bench) or "not measured" in speed.lower(), speed)

    # -- memory: the portrait's store read, with a fake store to move it.
    real_mem = sys.modules.get("jarvis_memory")

    class _Store:
        def status(self):
            return {"current": 7, "facts": 9, "retired": 2, "entities": 4}

    class _Mod:
        @staticmethod
        def store():
            return _Store()

    class _Broken:
        """A memory module that cannot answer - the honest unreadable case."""

        @staticmethod
        def store():
            raise RuntimeError("probe: the store is unreadable")

    sys.modules["jarvis_memory"] = _Mod()
    try:
        mem = said("how much memory do you have")
        check("the memory answer is the store's own count", "7" in mem, mem)
        check("... and its own fact and entity counts",
              "9" in mem and "4" in mem, mem)
        sys.modules["jarvis_memory"] = _Broken()
        without = said("how much memory do you have")
        check("an unreadable store says it cannot read it, and does not guess",
              "cannot read" in without and "7" not in without, without)
    finally:
        if real_mem is None:
            sys.modules.pop("jarvis_memory", None)
        else:
            sys.modules["jarvis_memory"] = real_mem

    # -- storage: the SAME pc_facts answer the other disk phrasings use.
    direct = PC.answer("space_all")
    check("the storage answer is the pc_facts disk answer, character for character",
          said("how much storage is left") == direct, said("how much storage is left"))
    check("... and that answer has a real free-space figure in it",
          "GB free of" in direct, direct)
    real_answer = PC.answer
    try:
        PC.answer = lambda shape, drive="", facts=None: f"SENTINEL {shape}"
        check("a flipped disk reader moves the chat answer",
              "SENTINEL space_all" in said("how much disk space"),
              said("how much disk space"))
    finally:
        PC.answer = real_answer

    # -- jobs: both scheduler registries, with a real handler registered.
    jobs = said("what jobs can you schedule")
    for name, kind in sorted((SCH.KINDS or {}).items()):
        noun = str(getattr(kind, "noun", "") or name)
        check(f"the jobs answer names the scheduler kind {noun!r}", noun in jobs, jobs)
    before = JOBS.handlers()
    JOBS.register("probe_reads_show_up", lambda ctx, params: {"ok": True})
    try:
        after = said("what jobs can you schedule")
        check("a newly registered job body appears in the answer",
              "probe_reads_show_up" in after and "probe_reads_show_up" not in jobs,
              after)
    finally:
        for name in ("probe_reads_show_up",):
            JOBS._HANDLERS.pop(name, None)
            JOBS._READONLY_HANDLERS.discard(name)
    check("the handler registry is back to what it was",
          JOBS.handlers() == before, f"{JOBS.handlers()} != {before}")


def near_misses_keep_their_own_answers():
    """A different question must not be hijacked by the new intents."""
    NEW = {"how_running", "how_context", "how_fast", "how_memory", "how_jobs"}
    for words in ("how much memory do i have",
                  "how much ram do i have",
                  "what do you remember about my sister",
                  "what are you running late for",
                  "how fast can you order a pizza",
                  "what jobs does a carpenter do",
                  "how much storage does google give me"):
        got = Q.match(words)
        check(f"{words!r} is not one of the ten", got is None or got.name not in NEW,
              got.name if got else None)
    got = Q.match("how much memory do i have")
    check("... and 'how much memory do I have' keeps the PC's RAM answer",
          got is not None and got.name == "pc_facts", got.name if got else None)


# ---------------------------------------------------------------------------
#   2. The pair table: ten rows, each answered by its own rule
# ---------------------------------------------------------------------------

#: One phrase per row, exactly as the table's own shape matches it.
PAIRS = (
    ("chat_history_learning",
     "if I turn off chat history does background learning still work"),
    ("web_search_ask",
     "does web search use ask before every search"),
    ("learning_sensitive",
     "does background learning save sensitive topics"),
    ("second_card_features",
     "does the second card work with pictures"),
    ("big_model_combined",
     "does the big model work with both cards"),
    ("voice_check_live",
     "does the voice check apply when I start Live by voice"),
    ("standby_lanes",
     "does the standby hours stop the second card"),
    ("quiet_hours_phone",
     "does quiet hours also silence my phone"),
    ("lights_home_tool",
     "does lights without a card need the home tool"),
    ("picture_cloud",
     "does picture mode use the cloud"),
)


def every_pair_is_answered_by_its_own_rule():
    check("the table really holds ten rules", len(Q._PAIR_RULES) == 10,
          str(len(Q._PAIR_RULES)))
    check("every rule carries a proven one-line interaction",
          all(callable(r.get("conflict")) for r in Q._PAIR_RULES))
    for rid, words in PAIRS:
        got = Q.match(words)
        check(f"{words!r} is the {rid} rule, not the model",
              got is not None and got.name == "pair_answer"
              and got.f.get("pair") == rid,
              f"{got.name if got else None} {getattr(got, 'f', None)}")
        rule = Q._PAIR_BY_ID[rid]
        values = rule["read"]()
        want = rule["say"](values)
        reply = said(words)
        check(f"... and the answer is that rule's own sentence", reply == want,
              reply[:300])
        check(f"... and it is not the unknown-pair sentence",
              reply != Q.PAIR_UNKNOWN_WORDS, reply[:200])


def flipping_either_value_changes_the_pair_answer():
    """THE ANSWERS ARE BUILT FROM THE LIVE READ, not frozen at import."""
    for rid, words in PAIRS:
        rule = Q._PAIR_BY_ID[rid]
        real = rule["read"]
        try:
            # Two shaped fakes: one says "everything on / nothing clashing",
            # the other "everything off". Each must produce its own sentence
            # and the two must differ - which no constant could do.
            seen = []

            def fake(on=True):
                def _read():
                    values = {k: on for k in
                              ("history", "learning", "sensitive", "enabled", "ask",
                               "big_model", "combined", "setting", "quiet", "phone",
                               "picture")}
                    values.update({
                        "conflicts": ["Pictures"] if on is False else [],
                        "mode": "", "held": "" if on else "the big model holds it",
                        "mic": False, "live_locked": True, "live_unlocked": False,
                        "asleep": on, "lane": "running" if on else "off",
                        "combined_lane": "off", "third": "off", "job": None,
                        "quiet_from": "22:00", "quiet_to": "07:00",
                        "model": "probe:1b", "cloud": not on, "provider": "",
                        "home": on, "lights": on, "why": ""})
                    seen.append(dict(values))
                    return values
                return _read

            rule["read"] = fake(True)
            on_said = rule["say"](rule["read"]())
            rule["read"] = fake(False)
            off_said = rule["say"](rule["read"]())
            check(f"the {rid} rule says two different things for two states",
                  bool(on_said) and bool(off_said) and on_said != off_said,
                  f"{on_said[:80]!r} vs {off_said[:80]!r}")
            check(f"... and it never claims a value it did not read",
                  "None" not in on_said and "None" not in off_said,
                  f"{on_said[:120]!r}")
        finally:
            rule["read"] = real


def real_switch_files_move_the_pair_answers():
    """FOUR PAIRS, FLIPPED THROUGH THE REAL FILE EACH SETTING WRITES."""
    # 1. web search x ask before every search - jarvis_search's own file.
    path = SEARCH.settings_path()
    had = path.read_bytes() if path.is_file() else None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"provider": "searxng", "enabled": True,
                                    "ask_every_time": True}), encoding="utf-8")
        on = said("does web search use ask before every search")
        check("ask-every-time ON says every search raises a card",
              "every search raises its own approval card" in on, on)
        path.write_text(json.dumps({"provider": "searxng", "enabled": True,
                                    "ask_every_time": False}), encoding="utf-8")
        off = said("does web search use ask before every search")
        check("... and flipping it OFF changes the answer", off != on, off)
        check("... to the one that says a search goes without asking",
              "goes without asking" in off, off)
        path.write_text(json.dumps({"provider": "searxng", "enabled": False,
                                    "ask_every_time": True}), encoding="utf-8")
        dead = said("does web search use ask before every search")
        check("with web search itself OFF the ask switch has nothing to ask about",
              "nothing to ask about" in dead, dead)
    finally:
        if had is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(had)

    # 2. background learning x sensitive facts - jarvis_auto_learn's own file.
    path = AL.settings_path()
    had = path.read_bytes() if path.is_file() else None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"auto": True, "auto_sensitive": True}),
                        encoding="utf-8")
        on = said("does background learning save sensitive topics")
        check("sensitive-auto ON says a sensitive fact is saved without a per-fact yes",
              "saved without a per-fact yes" in on, on)
        path.write_text(json.dumps({"auto": True, "auto_sensitive": False}),
                        encoding="utf-8")
        off = said("does background learning save sensitive topics")
        check("... and flipping it OFF says the fact waits for its own card",
              "waits" in off or "until you say yes" in off, off)
        check("... which is a different answer", off != on, off)
    finally:
        if had is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(had)

    # 3. the voice check x a Live start by voice - jarvis_live's own file.
    path = LIVE._voice_check_path()
    had = path.read_bytes() if path.is_file() else None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({LIVE.VOICE_CHECK_SETTING: True}),
                        encoding="utf-8")
        on = said("does the voice check apply when I start Live by voice")
        check("the voice check ON says the press itself is the act",
              "the press itself is the act" in on, on)
        path.write_text(json.dumps({LIVE.VOICE_CHECK_SETTING: False}),
                        encoding="utf-8")
        off = said("does the voice check apply when I start Live by voice")
        check("... and OFF says the checks get STRICTER, not weaker",
              "STRICTER" in off or "stricter" in off, off)
        check("... which is the opposite of what the switch sounds like", off != on, off)
    finally:
        if had is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(had)

    # 4. the PC's quiet hours x the phone's notifications - two real files.
    prefs = NP.read()
    check("the quiet-hours row reads jarvis_notify_prefs' own prefs",
          isinstance(prefs.get("quiet_enabled"), bool), str(prefs))
    phone = PN.settings()
    check("the phone row reads jarvis_phone_notifications' own settings",
          isinstance(phone.get("enabled"), bool), str(phone))
    quiet = said("does quiet hours also silence my phone")
    check("the answer names the PC's window and the phone's own switch",
          ("22:00" in quiet or "quiet hours" in quiet) and "phone" in quiet, quiet)


def a_combination_with_no_rule_falls_through():
    """NO INVENTED RULES. A sentence the table does not own stays the model's."""
    for words in ("does web search work",
                  "is the second card on",
                  "does the cloud send my files",
                  "do two settings ever conflict",
                  "what happens if i combine two settings",
                  "what breaks if i turn on everything",
                  "can i use jarvis live and chat at the same time",
                  "does the big model work with the coding preset",
                  "if cloud is on does my email still stay on the pc"):
        got = Q.match(words)
        check(f"{words!r} gets no invented pair rule",
              got is None or got.name != "pair_answer",
              got.name if got else None)
    check("no pair is invented for a pair of settings the table does not hold",
          Q._pair_conflict_line(["web_search", "pictures"]) == "",
          Q._pair_conflict_line(["web_search", "pictures"]))


# ---------------------------------------------------------------------------
#   3. Every switchable feature reports a live state - or says it cannot
# ---------------------------------------------------------------------------


def every_switchable_feature_says_its_real_state():
    switchable = [r for r in FG.control_matrix()
                  if r.get("label") == FG.LABEL_SWITCH_ADJUST]
    # 43 with the shipped contract in place (the audit's number); the staged
    # backend the CI runner builds carries no contract file, so the floor is
    # the real rows' own minimum rather than a typed 43.
    check("the feature list has a real set of switchable rows", len(switchable) >= 24,
          str(len(switchable)))
    readable = unreadable = no_control = 0
    for row in switchable:
        feature = FG.row_by_id(row["id"]) or {}
        words = FG.explain(row.get("name") or feature.get("title") or "")["words"]
        if row.get("switch_keys"):
            readable += 1
            check(f"{row['id']} reports its live on/off",
                  "Right now," in words and " is on" in words or " is off" in words,
                  words[-260:])
        elif str(row.get("status") or "") in ("planned", "not-a-setting"):
            no_control += 1
            check(f"{row['id']} really has no switch, and says so",
                  "no on/off switch" in words, words[-260:])
        else:
            unreadable += 1
            check(f"{row['id']} has a control this build cannot read, and says so",
                  "could not read a live on/off" in words, words[-300:])
    check("every switchable row is one of those three - none is silent",
          readable + unreadable + no_control == len(switchable),
          f"{readable}/{unreadable}/{no_control}")
    check("at least one switchable row really reports a read value", readable >= 20,
          str(readable))
    check("... and the rest say plainly that the switch cannot be read, "
          "never that there is no switch", unreadable >= 1, str(unreadable))


def a_flipped_switch_moves_the_feature_answer():
    """The state line is the reader's, so flipping the reader flips the words."""
    real = FG.STATE_READERS.get("chat_history")
    try:
        FG.STATE_READERS["chat_history"] = lambda: False
        off = FG.state("history")["words"]
        FG.STATE_READERS["chat_history"] = lambda: True
        on = FG.state("history")["words"]
        check("the feature answer says OFF when the reader says off",
              "off" in off.lower(), off)
        check("... and ON when the reader says on", "on" in on.lower(), on)
        check("... so the two answers really differ", off != on, f"{off} / {on}")
    finally:
        if real is None:
            FG.STATE_READERS.pop("chat_history", None)
        else:
            FG.STATE_READERS["chat_history"] = real


# ---------------------------------------------------------------------------
#   4. The wider capability answers (files, screen, calendar)
# ---------------------------------------------------------------------------


def capabilities_answer_from_the_real_check():
    # -- files: the live [tools].enabled decides, and it is flipped for real.
    on = said("can you read my files")
    tools = Q._enabled_tools_turn()
    if "my_files" in tools or "file_read" in tools:
        check("with a file tool offered, the files answer is an honest YES",
              on.startswith("Yes - reading your files"), on[:200])
        check("... naming the tool that really is on", "my_files" in on
              or "file_read" in on, on[:200])
    else:
        check("with no file tool offered, the files answer is the refusal",
              "switched off on this PC" in on, on[:200])
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-self-knowledge-toml-"))
    empty = tmp / "no-tools.toml"
    empty.write_text('[tools]\nenabled = []\n', encoding="utf-8")
    real = os.environ.get("JARVIS_FRAMEWORK_TOML")
    try:
        os.environ["JARVIS_FRAMEWORK_TOML"] = str(empty)
        off = said("can you read my files")
        check("a settings file with no tools turns the files answer into a refusal",
              "switched off on this PC" in off, off[:220])
        check("... and the yes is gone", not off.startswith("Yes -"), off[:120])
        cal = said("do you have access to my calendar")
        check("the calendar answer is the real refusal when calendar_read is off",
              "switched off on this PC" in cal and "calendar" in cal.lower(), cal[:220])
    finally:
        if real is None:
            os.environ.pop("JARVIS_FRAMEWORK_TOML", None)
        else:
            os.environ["JARVIS_FRAMEWORK_TOML"] = real
    back = said("can you read my files")
    check("putting the settings file back puts the honest yes back",
          back.startswith("Yes - reading your files"), back[:160])

    # -- screen: picture mode is the check, and its own words are the refusal.
    screen = said("can you see my screen")
    off = Q._switch_is_off("picture-mode")
    if off is True:
        check("with picture mode off, seeing the screen is refused in its own words",
              "switched off on this PC" in screen and "icture mode" in screen,
              screen[:240])
    elif off is False:
        check("with picture mode on, seeing the screen is an honest yes",
              screen.startswith("Yes - seeing your screen"), screen[:200])
    else:
        check("an unreadable picture-mode switch steps aside instead of guessing",
              screen != "" and "cannot read" not in screen[:20], screen[:200])
    check("'look at my screen' is still the Live read's, not this refusal",
          (Q.match("look at my screen") is None
           or Q.match("look at my screen").name != "honest_chat"),
          str(Q.match("look at my screen")))


def the_old_three_still_refuse():
    for words, needle in (("can you read my email", "email"),
                          ("can you control my phone", "phone")):
        reply = said(words)
        check(f"{words!r} still gets its honest refusal",
              "switched off on this PC" in reply and needle in reply.lower(),
              reply[:200])


# ---------------------------------------------------------------------------
#   5. A two-setting change says the interaction and changes nothing
# ---------------------------------------------------------------------------


def a_two_setting_change_says_the_conflict():
    got = Q.match("turn on web search and ask before every search")
    check("the two-setting change is answered by the pair note",
          got is not None and got.name == "settings_pair_note",
          got.name if got else "went to the model")
    result = answer("turn on web search and ask before every search")
    check("it says one setting per message",
          "one setting per message" in result.reply, result.reply[:200])
    check("... it states the interaction in one line",
          Q._pair_conflict_line(["web_search", "ask_before_every_search"])
          in result.reply, result.reply)
    check("... and it says nothing was changed",
          "Nothing was changed" in result.reply, result.reply)
    check("... and it raises NO card", not getattr(result, "waiting", False),
          str(getattr(result, "waiting", None)))
    check("... and it asks for one of them on its own",
          "on its own" in result.reply, result.reply)

    # A pair the table does NOT hold is not hijacked into a warning.
    other = Q.match("turn on web search and turn on pictures")
    check("two settings with no rule between them do not get a warning",
          other is None or other.name != "settings_pair_note",
          other.name if other else None)
    # A QUESTION that names two settings is not a change request.
    q = Q.match("does web search use ask before every search")
    check("a question naming two settings is the pair answer, not the change note",
          q is not None and q.name == "pair_answer", q.name if q else None)


def every_new_intent_is_read_only():
    for name in ("how_running", "how_context", "how_fast", "how_memory", "how_jobs",
                 "pair_answer", "settings_pair_note"):
        check(f"{name} is read-only, so 'cancel that' cannot undo a question",
              name in Q.READ_ONLY_INTENTS)


# ---------------------------------------------------------------------------

def main() -> int:
    try:
        every_family_answers_without_the_model()
        answers_are_the_owners_own_read()
        near_misses_keep_their_own_answers()
        every_pair_is_answered_by_its_own_rule()
        flipping_either_value_changes_the_pair_answer()
        real_switch_files_move_the_pair_answers()
        a_combination_with_no_rule_falls_through()
        every_switchable_feature_says_its_real_state()
        a_flipped_switch_moves_the_feature_answer()
        capabilities_answer_from_the_real_check()
        the_old_three_still_refuse()
        a_two_setting_change_says_the_conflict()
        every_new_intent_is_read_only()
    except Exception:
        traceback.print_exc()
        FAILED.append("the suite itself raised")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  FAILED  {name}")
        return 1
    print("PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
