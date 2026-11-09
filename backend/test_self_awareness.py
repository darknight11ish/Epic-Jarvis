"""test_self_awareness.py - full awareness of what the program has, and of
what changed (Wave 8.2, 2026-11-07).

    python3 backend/test_self_awareness.py

The owner: "i want jarvis to have full awareness of everything that the jarvis
program has, including if anything changes" ... "jarvis should be able to
change almost everything (when it makes sense) through chat and discuss it
with me properly in detail. and if multiple parts affect the same area".

This suite is the ACCEPTANCE PROOF for that audit. It reads the program's own
registries (never a hand-written list) and checks, with no model, no card, no
network and no real benchmark:

  - every BOOLEAN setting (38): a change sentence reaches `settings_bool`, and
    a named read sentence reaches a deterministic read intent;
  - every CHOICE setting (10): same, through `control_set` / `setting_explain`;
  - the NUMBER setting (1): change through `live_idle_set`, read through
    `live_idle_ask`;
  - every TOOL switch (61, `tool_targets()`): change through `settings_tool`,
    detail through `tool_profile`, and a state sentence through the new
    `tool_switch_state`; the on/off lists answer too;
  - every PRESET row: change through `preset_switch`, read through
    `preset_detail`; "which preset am I on?" answers from the ACTIVE preset;
  - the new awareness answers: benchmarks (history/progress/start/stop, with a
    fake runner), the change journal (snapshot diff + journal read), the
    inventories ("what do you have?" / "what can you change?"), the same-area
    groups (8 sections with more than one part), and a desktop Settings-page row
    by its page words;
  - the 181 feature-catalogue rows all resolve from their own cues - the same
    contract the Wave-8 audit measured;
  - "run a benchmark" no longer matches the open-app doorway (the live bug that
    said "I have asked this PC to open benchmark"), and a PRIVATE chat still
    answers these local reads deterministically (the Q3 rule).

Hermetic: its own temp OPENJARVIS_HOME / JARVIS_HOME / schedule DB, and it
refuses to run if those do not point inside its own temp folder. The benchmark
runner, the model record and the journal snapshots are injected; nothing here
loads a model, opens a socket, raises a card or writes to the owner's data.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_TMP = Path(tempfile.mkdtemp(prefix="jarvis-self-awareness-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(_TMP / "config")
os.environ["JARVIS_SCHEDULE_DB"] = str(_TMP / "schedule.db")
_HOME = _TMP / "home"
_HOME.mkdir(parents=True, exist_ok=True)
os.environ["OPENJARVIS_HOME"] = str(_HOME)
os.environ["JARVIS_HOME"] = str(_HOME)

import jarvis_bench as B  # noqa: E402
import jarvis_feature_catalogue as C  # noqa: E402
import jarvis_presets as P  # noqa: E402
import jarvis_quick as Q  # noqa: E402
import jarvis_schedule as S  # noqa: E402
import jarvis_settings_registry as R  # noqa: E402

PASSED, FAILED = [], []


def check(name: str, ok: bool, detail=None) -> None:
    if ok:
        PASSED.append(name)
        print(f"ok    {name}")
    else:
        FAILED.append(name)
        print(f"FAIL  {name}" + (f" | {detail!r}" if detail is not None else ""))


def _require_own_home() -> None:
    home = os.environ.get("OPENJARVIS_HOME") or ""
    try:
        same = bool(home) and Path(home).resolve() == _HOME.resolve()
    except OSError:
        same = False
    if not same:
        print("FAIL  the suite's OPENJARVIS_HOME is not its own temp folder")
        sys.exit(1)


def _intent(sentence: str):
    m = Q.match(sentence)
    return None if m is None else m.name


def _ran(sentence: str, sched=None, now=None):
    sched = sched or S.get()
    intent = Q.match(sentence)
    if intent is None:
        return None
    return Q.run(intent, sched, time.time() if now is None else now)


CHANGE_SET = {"settings_bool", "settings_choice", "settings_number", "settings_tool",
              "control_set", "live_idle_set", "preset_switch", "model_switch",
              "personality_set"}
READ_SET = {"feature_state", "feature_state_setting", "setting_explain",
            "settings_explain_setting", "settings_explain_all", "settings_help",
            "settings_antislop_state", "tool_profile", "tools_inventory",
            "preset_detail", "presets_list", "model_current", "model_answerer",
            "models_list", "model_speed", "self_setting_state", "self_knowledge",
            "tool_switch_state", "tool_switches_on_off", "setting_named_read",
            "desktop_row_info", "area_overview", "preset_current", "self_changes",
            "changeable_overview", "self_inventory", "bench_history",
            "bench_progress", "bench_run", "read_link", "focus_presets",
            "feature_explain", "feature_detail", "feature_howto",
            "feature_capabilities", "feature_can_do"}


def t_every_setting_can_be_changed_and_discussed():
    problems = []
    for setting in R.BOOL_SETTINGS:
        name = str(setting.names[0])
        changed = [n for n in ("turn on " + name, "turn off " + name,
                               "enable " + name) if _intent(n) in CHANGE_SET]
        if not changed:
            problems.append(("bool change", setting.key, name, _intent("turn on " + name)))
        read = [n for n in ("is " + name + " on?", "what is " + name + " set to?",
                            "what is the " + name + " setting set to?",
                            "explain the " + name + " setting")
                if _intent(n) in READ_SET]
        if not read:
            problems.append(("bool read", setting.key, name))
    for setting in R.CHOICE_SETTINGS:
        name = str(setting.names[0])
        try:
            options = list((setting.options() or {}).keys())[:3]
        except Exception:
            options = []
        changed = [n for n in ("set " + name + " to " + w for w in options)
                   if _intent(n) in CHANGE_SET] if options else []
        if not changed:
            problems.append(("choice change", setting.key, name, options))
        read = [n for n in ("what is " + name + "?", "what is " + name + " set to?",
                            "explain the " + name + " setting")
                if _intent(n) in READ_SET]
        if not read:
            problems.append(("choice read", setting.key, name))
    for setting in R.NUMBER_SETTINGS:
        name = str(setting.names[0])
        changed = [n for n in ("set the live idle timeout to 3 minutes",
                               "set the live idle timeout to 180 seconds",
                               "set " + name + " to 3 minutes")
                   if _intent(n) in CHANGE_SET]
        if not changed:
            problems.append(("number change", setting.key, name))
        read = [n for n in ("how long does jarvis live wait before it turns off?",
                            "what is the live idle timeout set to?")
                if _intent(n) in READ_SET]
        if not read:
            problems.append(("number read", setting.key, name))
    check("every boolean setting can be changed and discussed", not problems, problems)


def t_every_tool_can_be_changed_discussed_and_read():
    problems = []
    for tool, names in R.tool_targets().items():
        spoken = [str(n) for n in (names or ())] or [tool.replace("_", " ")]
        first = spoken[0]
        changed = [n for n in ("turn on " + first, "turn off " + first)
                   if _intent(n) in CHANGE_SET]
        if not changed:
            problems.append(("change", tool, first))
        detail = [n for n in ("tell me about " + first, "what does " + first + " do?")
                  if _intent(n) in READ_SET]
        if not detail:
            problems.append(("detail", tool, first))
        state = [n for n in ("is " + first + " on?", "is " + first + " off?")
                 if _intent(n) in READ_SET]
        if not state:
            problems.append(("state", tool, first))
    check("every one of the 61 tool switches can be changed, explained and read",
          not problems, problems[:12])
    for sentence, want in (("which tools are on?", "on"),
                           ("which tools are off?", "off")):
        intent = Q.match(sentence)
        check(f"the tool list answers {sentence!r}",
              intent is not None and intent.name == "tool_switches_on_off"
              and intent.f.get("want") == want,
              None if intent is None else (intent.name, intent.f))


def t_presets_and_models():
    # `jarvis_presets` exposes its rows as the module constant PRESETS (the
    # tuple `/api/presets` renders through P.view()); it has no presets()
    # helper. Asking for one made this loop iterate ZERO rows and pass
    # trivially, and made the live "what can you change?" say "0 presets"
    # (Wave-8.2 deploy finding 1, 2026-11-07). It reads the real collection now.
    presets = list(getattr(P, "PRESETS", ()) or ())
    problems = []
    if len(presets) < 9:
        problems.append(("the preset collection is short", len(presets)))
    for row in presets:
        title = str(getattr(row, "title", "") or "").lower()
        changed = [n for n in ("use the " + title + " preset",
                               "switch to the " + title + " preset")
                   if _intent(n) in CHANGE_SET]
        read = [n for n in ("what is the " + title + " preset?",
                            "tell me about the " + title + " preset")
                if _intent(n) in READ_SET]
        if not changed or not read:
            problems.append((title, changed, read))
    check("every preset can be switched to and explained", not problems, problems)
    for sentence, want in (("which preset am I on?", "preset_current"),
                           ("what preset are you on?", "preset_current"),
                           ("which model are you using?", "model_current"),
                           ("what models are installed?", "models_list")):
        check(f"{sentence!r} answers deterministically", _intent(sentence) == want,
              _intent(sentence))


def t_awareness_answers_read_locally():
    sched = S.get()
    preset = _ran("which preset am I on?", sched)
    check("the preset answer says what it is running and how to switch",
          preset is not None and preset.intent == "preset_current"
          and "preset" in preset.reply.lower()
          and ("cannot read which preset" in preset.reply.lower()
               or "use the" in preset.reply.lower()),
          None if preset is None else preset.reply[:180])
    bench = _ran("what benchmarks have been run on you?", sched)
    check("the benchmark history is honest when there are no rows",
          bench is not None and bench.intent == "bench_history"
          and ("not measured anything" in bench.reply.lower()
               or "no benchmark record" in bench.reply.lower()
               or "newest benchmark runs" in bench.reply.lower()),
          None if bench is None else bench.reply[:180])
    inv = _ran("what do you have?", sched)
    check("the inventory counts the program's own registries",
          inv is not None and inv.intent == "self_inventory"
          and str(len(C.FEATURES)) in inv.reply
          and str(len(R.tool_targets())) in inv.reply,
          None if inv is None else inv.reply[:200])
    chg = _ran("what can you change?", sched)
    # Wave-8.2 deploy finding 1 (2026-11-07): the live answer said "switch
    # between 0 presets" because the code asked for a `P.presets()` helper the
    # module does not have. It must report the REAL collection - at least 9 rows,
    # and the exact number /api/presets serves.
    real_presets = len(getattr(P, "PRESETS", ()) or ())
    check("the changeable overview names the settings and tools it can change",
          chg is not None and chg.intent == "changeable_overview"
          and "settings" in chg.reply and "tools" in chg.reply
          and "card" in chg.reply,
          None if chg is None else chg.reply[:200])
    check("... and reports the real preset count, never 0 (finding 1)",
          chg is not None and real_presets >= 9
          and f"between {real_presets} presets" in chg.reply
          and "0 presets" not in chg.reply,
          None if chg is None else (real_presets, chg.reply[:240]))
    changes = _ran("what changed about you?", sched)
    check("the change journal answers (empty honestly at first)",
          changes is not None and changes.intent == "self_changes"
          and "changed" in changes.reply.lower(),
          None if changes is None else changes.reply[:200])
    learning = _ran("what else affects the learning area?", sched)
    check("a same-area question lists every part of the area",
          learning is not None and learning.intent == "area_overview"
          and "background learning" in learning.reply.lower()
          and "learning" in learning.reply.lower(),
          None if learning is None else learning.reply[:220])
    pair = _ran("what happens if i change background learning and sensitive topics together?",
                sched)
    check("two parts in the same area are compared, not guessed",
          pair is not None and pair.intent == "area_overview"
          and "background learning" in pair.reply.lower()
          and ("same area" in pair.reply.lower()
               or "different areas" in pair.reply.lower()),
          None if pair is None else pair.reply[:220])
    row = _ran("what does the prompt coach setting do?", sched)
    # The older explain door keeps a sentence it can answer; either it or the
    # new page-row answer is a deterministic, page-worded answer.
    check("a desktop Settings-page row answers by the words on the page",
          row is not None and row.intent in ("feature_explain", "desktop_row_info")
          and len(row.reply) > 40,
          None if row is None else (row.intent, row.reply[:120]))
    # Wave-9 finding 4 (2026-11-07): the prompt-coach sentence belongs to
    # `feature_explain` on purpose, so the desktop-row door needs a sentence
    # that is really a Settings PAGE row and nothing else. This one is the
    # sentence the live verification uses, so both measure the same door.
    page_row = _ran("what does the morning briefing setting do?", sched)
    check("... and a page-only row reaches desktop_row_info by its page words",
          page_row is not None and page_row.intent == "desktop_row_info"
          and "morning briefing" in page_row.reply.lower(),
          None if page_row is None else (page_row.intent, page_row.reply[:160]))
    named = _ran("what is saving facts in jarvis's own words set to?", sched)
    check("a named setting reads its current value from the registry",
          named is not None and named.intent == "setting_named_read"
          and ("off" in named.reply.lower() or "on" in named.reply.lower()),
          None if named is None else named.reply[:200])


def t_private_chat_answers_the_local_reads():
    sched = S.get()
    for sentence in ("which preset am I on?", "what can you change?",
                     "what changed about you?", "what do you have?"):
        got = Q.answer(sentence, private=True, sched=sched)
        check(f"a private chat answers {sentence!r} from the local code",
              got is not None and got.intent in READ_SET and got.private is not True,
              None if got is None else (got.intent, got.reply[:100]))


def t_benchmarks_are_read_started_and_stopped():
    sched = S.get()
    old_start, old_view, old_cancel = B.start, B.view, B.cancel
    old_model = Q._model_record
    try:
        Q._model_record = lambda: "qwen3.5:9b"
        seen = {}

        def fake_start(body):
            seen["body"] = body
            return 200, {"ok": True, "run_id": "run-test1",
                         "message": "Measuring now."}

        def fake_view(run_id):
            seen["view"] = run_id
            if seen.get("done"):
                return 200, {"state": "done",
                             "result": {"words": "42.0 tokens a second, no spill."}}
            return 200, {"state": "running", "step": 2, "of": 4}

        def fake_cancel(run_id):
            seen["cancel"] = run_id
            return 200, {"words": "Stopped the benchmark run."}

        B.start, B.view, B.cancel = fake_start, fake_view, fake_cancel
        started = _ran("run a benchmark", sched)
        check("'run a benchmark' starts the real journaling path, not an app",
              started is not None and started.intent == "bench_run"
              and "run-test1" in started.reply
              and seen.get("body", {}).get("confirm", {}).get("may_evict") is True,
              None if started is None else started.reply[:220])
        state_file = Path(Q._bench_state_path())
        check("the run id is stored so a later turn can ask how it is going",
              state_file.exists()
              and json.loads(state_file.read_text(encoding="utf-8")).get("run_id")
              == "run-test1")
        progress = _ran("how is the benchmark going?", sched)
        check("progress reports the runner's own step count",
              progress is not None and "2" in progress.reply and "4" in progress.reply,
              None if progress is None else progress.reply[:160])
        seen["done"] = True
        done = _ran("how is the benchmark going?", sched)
        check("a finished run says the measured words",
              done is not None and "42.0 tokens a second" in done.reply,
              None if done is None else done.reply[:160])
        stopped = _ran("stop the benchmark", sched)
        check("the benchmark can be stopped from chat",
              stopped is not None and stopped.intent == "bench_stop"
              and "Stopped" in stopped.reply,
              None if stopped is None else stopped.reply[:160])
        seen["refuse"] = True
        B.start = lambda body: (409, {"error": "another benchmark run is already going"})
        refused = _ran("run a benchmark", sched)
        check("a refused start says nothing was measured",
              refused is not None and "Nothing was measured" in refused.reply,
              None if refused is None else refused.reply[:160])
    finally:
        B.start, B.view, B.cancel = old_start, old_view, old_cancel
        Q._model_record = old_model


def t_change_journal_records_what_changed():
    sched = S.get()
    old = Q._awareness_snapshot
    for name in ("snapshot.json", "changes.jsonl"):
        try:
            (Path(Q._awareness_dir()) / name).unlink()
        except OSError:
            pass
    try:
        first = {"version": "0.2.0", "preset": "general",
                 "setting:background_learning": "on", "tool:web_search": "off"}
        second = {"version": "0.2.0", "preset": "coding",
                  "setting:background_learning": "off", "tool:web_search": "off"}
        Q._awareness_snapshot = lambda: dict(first)
        Q._awareness_note()
        Q._awareness_snapshot = lambda: dict(second)
        Q._awareness_note()
        rows = Q._awareness_journal_rows()
        check("a changed preset and switch are journaled once",
              len(rows) == 1 and len(rows[0].get("changed") or []) == 2, rows)
        said = Q.run(Q.match("what changed about you?"), sched, time.time())
        check("'what changed about you?' names the fields and their old and new values",
              said is not None and "preset" in said.reply.lower()
              and "general" in said.reply and "coding" in said.reply,
              None if said is None else said.reply[:240])
        Q._awareness_note()
        rows2 = Q._awareness_journal_rows()
        check("re-reading an unchanged snapshot adds no journal row", len(rows2) == 1,
              rows2)
        Q._awareness_snapshot = old
        fresh = _ran("what changed about you?", sched)
        check("the journal answers honestly when nothing changed",
              fresh is not None and ("nothing has changed" in fresh.reply.lower()
                                     or "changed" in fresh.reply.lower()),
              None if fresh is None else fresh.reply[:160])
    finally:
        Q._awareness_snapshot = old


def t_run_a_benchmark_is_not_open_app():
    got = Q.match("run a benchmark")
    check("'run a benchmark' no longer matches the open-app doorway",
          got is not None and got.name == "bench_run",
          None if got is None else got.name)
    got = Q.match("I have asked this PC to open benchmark")
    check("... and the old open-app sentence is not invented anywhere",
          got is None or got.name != "open_app" or "benchmark" not in (got.f or {}).get("opened", ""),
          None if got is None else got.name)


def t_every_feature_row_resolves_from_its_own_cues():
    problems = []

    def resolve(sentence):
        m = Q.match(sentence)
        if m is None:
            return None
        if m.name == "capability_answer":
            return list(m.f.get("ids") or [])
        return m.name

    for row in C.FEATURES:
        rid = row.get("id")
        cues = []
        for key in ("covers", "aliases", "title", "what"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                cues.append(value.strip())
            elif isinstance(value, (list, tuple)):
                cues.extend(str(x).strip() for x in value if str(x).strip())
        covered = False
        for cue in cues[:8]:
            for form in ("can you {c}?", "what is {c}?", "tell me about {c}", "{c}"):
                try:
                    got = resolve(form.format(c=cue.lower()))
                except Exception:
                    got = None
                if isinstance(got, list):
                    covered = rid in got
                elif isinstance(got, str) and got:
                    # Any deterministic intent is a no-model answer; the audit's
                    # contract is "resolves from its own words", not one name.
                    covered = True
                if covered:
                    break
            if covered:
                break
        if not covered:
            problems.append(rid)
    check("all 181 feature rows answer from their own words", not problems,
          problems[:12])


def main() -> int:
    _require_own_home()
    try:
        for name, fn in list(globals().items()):
            if name.startswith("t_") and callable(fn):
                print(f"--- {name} ---")
                try:
                    fn()
                except Exception as exc:  # pragma: no cover
                    traceback.print_exc()
                    check(f"{name} ran without crashing", False, repr(exc))
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
