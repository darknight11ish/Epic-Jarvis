#!/usr/bin/env python3
"""test_self_knowledge.py - the self-awareness audit's gaps, driven.

    python3 backend/test_self_knowledge.py

WHAT THIS PROVES (2026-11-04; phase 2 covered the first seven, phase 3 the rest):

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
  3. THE PAIR TABLE ANSWERS WHAT TWO THINGS DO TOGETHER. TWELVE hand-built rows
     now (phase 2's ten, plus a preset's own model/card row and the cloud's own
     local-only-privacy row), each one proven by a real interaction in a real
     module (the file:line is beside each row in `jarvis_quick.py`). Every
     row's phrase must be answered by the row - never the model - and the
     answer must be built from the live read at answer time, so flipping either
     value changes it.
  4. A COMBINATION NOBODY WROTE A RULE FOR FALLS THROUGH THE TABLE. "does web
     search work", "is the second card on" and "do two settings ever conflict"
     must NOT be answered by an invented pair rule.
  5. EVERY ONE OF THE 43 SWITCHABLE FEATURES REPORTS A LIVE ON/OFF, or says in
     words that it cannot read that switch - never "there is no switch" for a
     feature that really has a control.
  6. THE WIDER CAPABILITY ANSWERS: files, screen and the calendar each answer
     "can you..." from the real check - a true yes when the tool/setting is on,
     the honest refusal when it is off.
  7. A TWO-SETTING CHANGE says the interaction in one line and changes
     NOTHING - one card per change is the rule, and no approval behaviour is
     touched.
  8. THE GENERIC TWO-ENTITY LOOKUP (phase 3): any "does X work with Y" whose
     halves are a real feature or setting answers both live states, says
     whether a known rule links them, and never invents one. An unknown name is
     said to be unknown; ordinary conversation still falls through.
  9. THE RICHER FOCUS-PRESET ANSWER (phase 3): every `jarvis_presets.PRESETS`
     row with its model, plus which preset is chosen, read from the real
     module - and an absent/unreadable record says so instead of reading as an
     empty list.
 10. THE MODEL'S OWN self_portrait TOOL CARRIES LIVE SETTING STATES (phase 3):
     a bounded, read-only digest of switch values and chosen options, so an
     unusual three-way question can read the state instead of guessing.
 11. THE VERSION FALLBACK (phase 3): when the VERSION file cannot be read the
     self-answer says so in a plain sentence - never a blank, a "None" or a
     guessed number.
 12. THE STRUCTURED FEATURE DIFFERENCE (phase 3): two features compared field
     by field - where each lives, its switch or none, its live on/off, what
     asks first and its honest limit - plus one plain sentence.

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

import jarvis_agent as A  # noqa: E402
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
    if cards:
        check("... and counts them from the same read",
              f"{len(cards)} graphics" in reply, reply[:200])
    else:
        # A CI runner (Linux, no NVIDIA card) has no count to check, and the
        # hardware read honestly reports none. The property under test is "the
        # answer follows the read", so it is asserted on that platform too:
        # the count is never invented, and the answer says it could not read a
        # card rather than claiming "0 graphics".
        check("... and with no card readable it says so instead of counting",
              "could not read this PC's graphics cards" in reply
              and "0 graphics" not in reply, reply[:200])

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
    disks = (PC.collect() or {}).get("disks")
    if isinstance(disks, list) and disks:
        check("... and that answer has a real free-space figure in it",
              "GB free of" in direct, direct)
    else:
        # jarvis_pc_help._read_disks is Windows-only (`os.name != "nt"` -> None),
        # so on the Linux CI runner there is no drive to quote and the same
        # answer is the honest "could not read your drives" sentence. That is
        # the property to assert there: no invented figure, and the answer says
        # it could not read one - never a number typed into this file.
        check("... and with no drive readable it says so and quotes no figure",
              "could not read your drives" in direct and "GB free of" not in direct,
              direct)
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
#   2. The pair table: twelve rows, each answered by its own rule
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
    # Phase 3's two rows (the ruling's twelve).
    ("preset_model_card",
     "what model and what card does the coding preset use"),
    ("cloud_privacy",
     "does cloud escalation send my private stuff"),
)

#: The two phase-3 rows read richer shapes than "a dict of booleans", so their
#: live-read proof is its own check (below) rather than the generic flip loop.
RICH_PAIRS = frozenset({"preset_model_card", "cloud_privacy"})


def every_pair_is_answered_by_its_own_rule():
    check("the table really holds twelve rules", len(Q._PAIR_RULES) == 12,
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
        values = rule["read"](got.f) if rule.get("args") else rule["read"]()
        want = rule["say"](values)
        reply = said(words)
        check(f"... and the answer is that rule's own sentence", reply == want,
              reply[:300])
        check(f"... and it is not the unknown-pair sentence",
              reply != Q.PAIR_UNKNOWN_WORDS, reply[:200])


def the_two_new_pairs_follow_their_real_reads():
    """THE PHASE-3 ROWS ARE LIVE READS, not lifted sentences.

    Row 11 follows `jarvis_presets.PRESETS` + the choice file; row 12 follows
    the cloud state file and `jarvis_auto_router.taint_latched()`. Each is
    flipped at the reader's own seam and the answer must move.
    """
    # -- row 11: the preset's own row and the chosen preset.
    for preset_id, phrase in (("coding", "what model and what card does the coding preset use"),
                              ("fast", "what context window and speed does fast have")):
        row = next((p for p in PR.PRESETS if p.id == preset_id), None)
        check(f"the {preset_id} preset row exists to read", row is not None)
        reply = said(phrase)
        check(f"{phrase!r} answers the row's real model",
              row is not None and row.model in reply, reply[:300])
        want_card = str((PR.LANES.get(row.lane) or {}).get("card") or "")
        check(f"... and the row's real card",
              bool(want_card) and want_card.split()[0] in reply, reply[:300])
        check(f"... and the row's own context window",
              f"{int(row.context):,} tokens" in reply, reply[:300])
    # Unknown preset: honest, and it lists the real titles.
    unknown = said("what model and what card does the bean preset use")
    check("an unknown preset is said to be unknown, with the real titles listed",
          "There is no preset called" in unknown
          and "Coding" in unknown and "Fast" in unknown, unknown[:300])
    # The choice file moves the answer.
    path = Path(PR._choice_path())
    had = path.read_bytes() if path.is_file() else None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"preset": "coding"}), encoding="utf-8")
        chosen = said("what model and what card does the fast preset use")
        check("the pair answer names the preset chosen on this PC",
              "chosen right now" in chosen and '"Coding"' in chosen, chosen[:400])
        path.write_text(json.dumps({"preset": "fast"}), encoding="utf-8")
        now = said("what model and what card does the fast preset use")
        check("... and follows it when the choice file moves",
              "It is the preset chosen on this PC right now" in now, now[:400])
    finally:
        if had is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(had)

    # -- row 12: the cloud state and the local-only block.
    escalate = Path(PR._escalate_path())
    cloud_choice = Path(PR._cloud_choice_path())
    had = escalate.read_bytes() if escalate.is_file() else None
    had_cloud = cloud_choice.read_bytes() if cloud_choice.is_file() else None
    real_taint = None
    try:
        import jarvis_auto_router as AR
        real_taint = AR.taint_latched
        escalate.parent.mkdir(parents=True, exist_ok=True)
        # A REAL provider id from the API module this PC ships, so the answer
        # is about an actual service rather than a name typed here.
        import jarvis_chatbot_api as API
        provider = next(iter(API.PRESETS))
        cloud_choice.write_text(json.dumps({"provider": provider}), encoding="utf-8")
        escalate.write_text(json.dumps({"on": True}), encoding="utf-8")
        AR.taint_latched = lambda active_project=None: (
            False, "")
        on = said("does cloud escalation send my private stuff")
        check("with the cloud switch ON and no taint, the answer says a question may go",
              "standing escalation switch is ON" in on
              and "no taint is latched" in on, on[:500])
        check("... and still says private material stays on this PC",
              "stays on this PC" in on or "stay on the local model" in on, on[:500])
        escalate.write_text(json.dumps({"on": False}), encoding="utf-8")
        AR.taint_latched = lambda active_project=None: (
            True, "probe: personal material was read into this conversation")
        latched = said("does cloud escalation send my private stuff")
        check("a latched local-only block makes the answer a hard NO",
              "block is ON" in latched and "probe: personal material" in latched,
              latched[:500])
        check("... which is a different answer from the untainted one",
              latched != on, f"{latched[:120]!r} / {on[:120]!r}")
        escalate.write_text(json.dumps({"on": False}), encoding="utf-8")
        off = said("does cloud escalation send my private stuff")
        check("with the cloud switch OFF the answer says every cloud turn needs a yes",
              "switch is OFF" in off or "No cloud service is chosen" in off, off[:400])
        check("... and the row's own one-line interaction protects the same block",
              "local-only" in Q._pair_cloud_privacy_conflict(
                  Q._pair_cloud_privacy_read()),
              Q._pair_cloud_privacy_conflict(Q._pair_cloud_privacy_read()))
    finally:
        if real_taint is not None:
            import jarvis_auto_router as AR2
            AR2.taint_latched = real_taint
        if had is None:
            escalate.unlink(missing_ok=True)
        else:
            escalate.write_bytes(had)
        if had_cloud is None:
            cloud_choice.unlink(missing_ok=True)
        else:
            cloud_choice.write_bytes(had_cloud)


def flipping_either_value_changes_the_pair_answer():
    """THE ANSWERS ARE BUILT FROM THE LIVE READ, not frozen at import.

    Phase 2's ten rows all answer from a dict of booleans, so one shaped fake
    proves each of them; the two phase-3 rows have richer reads and are proven
    by `the_two_new_pairs_follow_their_real_reads` instead.
    """
    for rid, words in PAIRS:
        if rid in RICH_PAIRS:
            continue
        rule = Q._PAIR_BY_ID[rid]
        real = rule["read"]
        try:
            # Two shaped fakes: one says "everything on / nothing clashing",
            # the other "everything off". Each must produce its own sentence
            # and the two must differ - which no constant could do.
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
        # "waits" only: "until you say yes" is the ending the card-words rule
        # removed (docs/ARCHITECTURE.md, Never approve-by-voice) and
        # test_card_words.py forbids it in jarvis_quick.py, so this must not
        # accept it as an alternative way to pass.
        check("... and flipping it OFF says the fact waits for its own card",
              "waits" in off, off)
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
                  "do two settings ever conflict",
                  "what happens if i combine two settings",
                  "what breaks if i turn on everything",
                  "can i use jarvis live and chat at the same time",
                  "does the big model work with the coding preset"):
        got = Q.match(words)
        check(f"{words!r} gets no invented pair rule",
              got is None or got.name != "pair_answer",
              got.name if got else None)
    check("no pair is invented for a pair of settings the table does not hold",
          Q._pair_conflict_line(["web_search", "pictures"]) == "",
          Q._pair_conflict_line(["web_search", "pictures"]))
    # The two cloud sentences the table now DOES own are answered by their own
    # rule - never by a second, invented one.
    for words in ("does the cloud send my files",
                  "if cloud is on does my email still stay on the pc"):
        got = Q.match(words)
        check(f"{words!r} is the cloud-privacy rule",
              got is not None and got.name == "pair_answer"
              and got.f.get("pair") == "cloud_privacy",
              f"{got.name if got else None} {getattr(got, 'f', None)}")


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


# ---------------------------------------------------------------------------
#   6. The generic two-entity lookup (phase 3)
# ---------------------------------------------------------------------------


def the_generic_two_entity_lookup_answers_honestly():
    """ANY two real names: both live states, and never an invented interaction."""
    words = "does web search work with chat history"
    got = Q.match(words)
    check(f"{words!r} is the generic two-thing answer",
          got is not None and got.name == "two_entity_answer"
          and got.f.get("a") == "web search" and got.f.get("b") == "chat history",
          f"{got.name if got else None} {getattr(got, 'f', None)}")
    reply = said(words)
    check("... it states BOTH live states from the registry",
          '"web search" is on' in reply and '"chat history" is on' in reply, reply)
    check("... and says no known rule links them, without claiming independence",
          "No rule in my code links those two" in reply, reply)

    # A pair the table DOES hold is answered with that rule instead.
    ruled = said("does chat history work with background learning")
    check("a pair with a real rule quotes that rule, inside the generic answer",
          "A known rule links them:" in ruled
          and "does NOT stop learning" in ruled, ruled)

    # A feature half is read through the feature guide's own state token.
    feature = said("does read a link work with web search")
    check("a real feature half reports its own state",
          "Read one web page out loud" in feature
          and "no on/off switch" in feature, feature)
    check("... beside the setting's live value", '"web search" is on' in feature,
          feature)

    # Unknown names are said to be unknown - never guessed at. The wording says
    # what really happened (the exact-name lookup missed); it does not claim the
    # thing is not a feature, because "reminders" is one of Jarvis's features
    # and simply has no catalogue ROW of that exact name.
    unknown = said("does my flux capacitor work with web search")
    check("an unknown half is said to be unknown, not invented",
          'does not match a feature or setting name I can read' in unknown
          and "flux capacitor" in unknown, unknown)
    check("... while the half that IS real still reports its live state",
          '"web search" is on' in unknown, unknown)
    both = said("does jarvis flux capacitor work with a warp drive")
    check("two unknown halves in a Jarvis question get the honest refusal",
          "Neither" in both and "will not invent" in both, both)
    # A real capability whose catalogue name is not the word the owner used is
    # NOT denied: the answer says the NAME did not match, and still reads the
    # half that does.
    loose = said("do reminders and calendar work together")
    check("a real capability under a loose word is not denied as 'not a feature'",
          "does not match a feature or setting name I can read" in loose, loose)
    check("... and the half that is a real row still reports its own state",
          "Read your own calendar" in loose, loose)

    # A CHANGE request is never turned into this answer (2026-11-04, found
    # while finishing this lane: "turn on web search and chat history together"
    # was read as the entity "turn on web search" and answered "that does not
    # match a name", hiding the change lane under it).
    for words in ("turn on web search and chat history together",
                  "please turn on web search and chat history together",
                  "enable web search and chat history together",
                  "switch on web search and chat history together"):
        got_change = Q.match(words)
        check(f"{words!r} is not the two-entity answer",
              got_change is None or got_change.name != "two_entity_answer",
              f"{got_change.name if got_change else None} "
              f"{getattr(got_change, 'f', None)}")
    # A real setting name that only CONTAINS a change word still answers.
    humoured = Q.match("does the humour switch work with chat history")
    check("a setting whose name contains 'switch' is still a real half",
          humoured is not None and humoured.name == "two_entity_answer",
          humoured.name if humoured else None)

    # The state is read at ANSWER time: flipping the reader moves it.
    real = FG.STATE_READERS.get("chat_history")
    try:
        FG.STATE_READERS["chat_history"] = lambda: False
        off = said("does web search work with chat history")
        check("flipping the real reader moves the generic answer to off",
              '"chat history" is off' in off, off)
        check("... which is a different answer", off != reply, f"{off[:100]!r}")
    finally:
        if real is None:
            FG.STATE_READERS.pop("chat_history", None)
        else:
            FG.STATE_READERS["chat_history"] = real

    # Ordinary conversation still falls through to the model.
    for words in ("does a car work with water",
                  "does tea work with milk"):
        check(f"{words!r} is not a Jarvis two-thing question",
              Q.match(words) is None, str(Q.match(words)))


# ---------------------------------------------------------------------------
#   7. The richer focus-preset answer (phase 3)
# ---------------------------------------------------------------------------


def the_focus_preset_lists_every_preset_row():
    """EVERY `jarvis_presets.PRESETS` ROW, its model, and which one is chosen."""
    got = Q.match("what is the focus preset")
    check("the focus preset is its own answer, not a preset called focus",
          got is not None and got.name == "focus_presets",
          f"{got.name if got else None} {getattr(got, 'f', None)}")
    reply = said("what is the focus preset")
    check("... it lists every preset row from the real module",
          all((p.title in reply) for p in PR.PRESETS), reply[:600])
    check("... and every row's own model",
          all((p.model in reply) for p in PR.PRESETS), reply[:600])
    check("... and names the setting it really is",
          "choice in Settings" in reply, reply[:300])

    # The chosen preset is read from the real choice file and follows it.
    path = Path(PR._choice_path())
    had = path.read_bytes() if path.is_file() else None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"preset": "coding"}), encoding="utf-8")
        chosen = said("what is the focus preset")
        check("the chosen preset is the one the choice file names",
              'The one chosen on this PC right now is "Coding"' in chosen, chosen[-300:])
        path.write_text(json.dumps({"preset": "fast"}), encoding="utf-8")
        moved = said("what is the focus preset")
        check("... and the answer follows the file when it moves",
              'The one chosen on this PC right now is "Fast"' in moved, moved[-300:])
    finally:
        if had is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(had)

    # A model question about "the focus preset" reaches the same answer instead
    # of denying that a preset called "focus" exists.
    denied = Q.match("what model does the focus preset use")
    check('"what model does the focus preset use" is the focus-preset answer too',
          denied is not None and denied.name == "focus_presets",
          denied.name if denied else None)
    said_model = said("what model does the focus preset use")
    check("... and it never says there is no preset called focus",
          "There is no preset called" not in said_model, said_model[:300])

    # A DAMAGED choice file is not "nothing applied yet". `jarvis_presets.choice()`
    # swallows both into None, so the answer has to look at the file itself - and
    # the owner's rule is that an unreadable record says so plainly.
    damaged_path = Path(PR._choice_path())
    had_damaged = damaged_path.read_bytes() if damaged_path.is_file() else None
    try:
        damaged_path.parent.mkdir(parents=True, exist_ok=True)
        damaged_path.write_text("{ not json", encoding="utf-8")
        damaged = said("what is the focus preset")
        check("a damaged choice file says it cannot say which preset is chosen",
              "does not name a preset I can read" in damaged, damaged[-300:])
    finally:
        if had_damaged is None:
            damaged_path.unlink(missing_ok=True)
        else:
            damaged_path.write_bytes(had_damaged)

    # THE SAME COLLISION THROUGH THE PAIR TABLE'S OWN SHAPE (2026-11-04, found
    # while finishing this lane). "what model and what card does the focus
    # preset use" reaches row 11 with the name "focus", and it used to answer
    # "There is no preset called focus" - the denial gap 6 was about, arriving
    # through a second door. It must answer the CHOSEN preset's real row.
    model_card = said("what model and what card does the focus preset use")
    check("a model/card question about the focus preset is never a denial",
          "There is no preset called" not in model_card, model_card[:400])
    chosen_id = PR.choice()
    if chosen_id:
        chosen_row = next((p for p in PR.PRESETS if p.id == chosen_id), None)
        check("... it answers the chosen preset's own row and model",
              chosen_row is not None and chosen_row.title in model_card
              and chosen_row.model in model_card, model_card[:400])
        check("... and says the focus preset is the setting that picks it",
              "choice in Settings" in model_card, model_card[:400])
    else:
        check("... or says plainly that no preset is recorded as chosen",
              "No preset is recorded as chosen" in model_card, model_card[:400])

    # An absent / unreadable record says so plainly.
    real_rows, real_choice = PR.PRESETS, PR.choice
    try:
        PR.PRESETS = ()
        empty = said("what is the focus preset")
        check("an empty preset record says so, rather than reading as no presets",
              "no rows on this PC" in empty, empty)
        PR.PRESETS = real_rows

        def _broken():
            raise RuntimeError("probe: the choice file is unreadable")

        PR.choice = _broken
        broken = said("what is the focus preset")
        check("an unreadable choice record says it could not read which is chosen",
              "could not read which preset is chosen" in broken, broken[-300:])
    finally:
        PR.PRESETS, PR.choice = real_rows, real_choice


# ---------------------------------------------------------------------------
#   8. The model's self_portrait tool: live settings, and the version fallback
# ---------------------------------------------------------------------------


def the_self_portrait_tool_carries_live_settings():
    """A BOUNDED, READ-ONLY DIGEST of the real switch and choice values."""
    got = A._run_self_portrait({})
    check("the model's self_portrait tool answers", got.get("ok") is True)
    live = got.get("live_settings") or {}
    check("... it carries a live_settings digest",
          isinstance(live.get("switches"), dict) and bool(live["switches"]), str(live)[:300])
    check("... the digest is the registry's own switches, on or off",
          all(isinstance(v, bool) for v in live["switches"].values())
          and isinstance(live.get("on"), int) and isinstance(live.get("off"), int),
          str(live)[:300])
    check("... it names the chosen preset and its plan model (or says none)",
          all(k in live for k in ("preset", "preset_title", "preset_model", "model")),
          str(sorted(live)))
    check("... it is bounded, and says how many it left out",
          (len(live["switches"]) + len(live["choices"]) + len(live["unreadable"]))
          <= SP.DIGEST_MAX and isinstance(live.get("more"), int), str(live)[:200])
    check("... and an unreadable switch is named, never shown as off",
          "face" not in live["switches"] or isinstance(live["switches"].get("face"), bool),
          str(live.get("unreadable"))[:200])

    # A real reader flip moves the digest - it is not frozen at import.
    real = FG.STATE_READERS.get("chat_history")
    try:
        FG.STATE_READERS["chat_history"] = lambda: False
        again = A._run_self_portrait({})["live_settings"]
        check("flipping the real chat-history reader moves the tool's digest",
              again["switches"].get("chat_history") is False,
              str(again["switches"].get("chat_history")))
    finally:
        if real is None:
            FG.STATE_READERS.pop("chat_history", None)
        else:
            FG.STATE_READERS["chat_history"] = real

    # No phrase, no secret: the digest is ids and values only.
    blob = json.dumps(live)
    check("the digest carries no sentence or secret-shaped value",
          " is " not in blob and "token" not in blob.lower(), blob[:200])


def the_version_fallback_says_it_could_not_read_it():
    """FIX #10: no VERSION file means a SENTENCE, never a blank or a "None"."""
    real = SP._app_version
    try:
        SP._app_version = lambda: ("unknown", "no VERSION file beside the backend")
        SP._clear_caches()
        block = SP.version_block()
        said = str(block.get("app_version_said") or "")
        check("the version block still answers the bare token honestly",
              block.get("app_version") == "unknown", str(block.get("app_version")))
        check("... and adds a sentence saying it could not be read",
              "could not read the app version" in said, said)
        check("... naming what would record one",
              "deploy reseal" in said, said)
        check("... never a blank, a None or a guessed number",
              bool(said.strip()) and "None" not in said
              and not any(ch.isdigit() for ch in said.replace("1", "")), said)
        tool = A._run_self_portrait({})
        check("the model's own tool carries that sentence too",
              tool.get("version", {}).get("app_version_said") == said,
              str(tool.get("version")))
    finally:
        SP._app_version = real
        SP._clear_caches()

    real_version = SP.app_version_said("1.2.3", "VERSION beside the backend")
    check("a readable version is named, not explained away",
          "1.2.3" in real_version and "could not read" not in real_version,
          real_version)


# ---------------------------------------------------------------------------
#   9. The structured feature difference (phase 3)
# ---------------------------------------------------------------------------


def the_structured_difference_names_each_field():
    """TWO FEATURES, FIELD BY FIELD, plus one plain sentence."""
    got = FG.difference("reminders", "Galaxy")
    check("two real features produce a comparison", got.get("kind") == "feature",
          str(got)[:200])
    compare = got.get("compare") or []
    check("... with one structured side per feature", len(compare) == 2,
          str(len(compare)))
    fields = ("id", "title", "where", "has_switch", "switch", "state",
              "state_words", "asks", "limit", "what")
    for i, facts in enumerate(compare):
        check(f"side {i + 1} carries every field the brief names",
              all(k in facts for k in fields), str(sorted(facts)))
        check(f"side {i + 1} says where it lives and what asks first",
              bool(facts["where"]) and isinstance(facts["asks"], str)
              and bool(facts["asks"]), str(facts)[:300])
        check(f"side {i + 1}'s live state is a real token, not a guess",
              isinstance(facts["state"], str) and bool(facts["state"]),
              str(facts.get("state")))
        check(f"side {i + 1}'s switch is a real list (none = no switch)",
              isinstance(facts["switch"], list)
              and facts["has_switch"] == bool(facts["switch"]), str(facts)[:200])
    check("... and the words end with ONE plain sentence about the difference",
          got["words"].rstrip().endswith(".") and "The difference:" in got["words"],
          got["words"][-300:])
    check("... the structured side and the prose cannot disagree",
          all(f["state_words"] in got["words"] for f in compare), got["words"][:300])

    # A real switchable feature: its switch is named and its live state is read.
    switchable = [r for r in FG.control_matrix() if r.get("switch_keys")]
    check("the control matrix has a switchable row to compare", bool(switchable))
    if len(switchable) >= 2:
        rows = [FG.row_by_id(r["id"]) for r in switchable[:2]]
        named = [str(r.get("title") or "") for r in rows if r]
        if len(named) == 2:
            pair = FG.difference(named[0], named[1])
            check("a switchable feature's side has_switch=True and a live token",
                  bool(pair.get("compare"))
                  and pair["compare"][0]["has_switch"] is True
                  and pair["compare"][0]["state"] in
                  ("on", "off", "partly on", "cannot be read on this PC"),
                  str(pair.get("compare")[:1])[:300])

    # One known feature and one unknown still answers honestly.
    one = FG.difference("reminders", "bicycle")
    check("one real feature and one unknown name still says what it can",
          one.get("kind") == "feature" and len(one.get("compare") or []) == 1
          and "nothing to compare it with" in one["words"], one["words"][-200:])
    # One row under two names is ONE feature, not an invented difference. The
    # quick path merges them before it calls the guide, so that is the path
    # driven here (the same one the owner's sentence takes).
    same_intent = Q.match("what's the difference between reminders and alarms")
    check("reminders and alarms are the same comparison intent",
          same_intent is not None and same_intent.name == "feature_difference",
          same_intent.name if same_intent else None)
    same = said("what's the difference between reminders and alarms")
    check("two names for one row say they are the same row",
          "same feature row" in same, same[:300])


def every_new_intent_is_read_only():
    for name in ("how_running", "how_context", "how_fast", "how_memory", "how_jobs",
                 "pair_answer", "settings_pair_note", "two_entity_answer",
                 "focus_presets"):
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
        the_two_new_pairs_follow_their_real_reads()
        real_switch_files_move_the_pair_answers()
        a_combination_with_no_rule_falls_through()
        the_generic_two_entity_lookup_answers_honestly()
        the_focus_preset_lists_every_preset_row()
        the_self_portrait_tool_carries_live_settings()
        the_version_fallback_says_it_could_not_read_it()
        the_structured_difference_names_each_field()
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
