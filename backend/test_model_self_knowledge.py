"""test_model_self_knowledge.py - does Jarvis know what model it is running?

    python3 backend/test_model_self_knowledge.py

THE OWNER'S BUG (2026-10-31). Asked "what ai model do you have?", Jarvis said it
did not know which model it was running on, while the HUD telemetry beside it
said "ANSWERED BY qwen3.5:9b". This suite proves the fix on a FAKE PC state:

  * the current model and preset are named from the PC's own state;
  * the installed list, the presets and what each preset changes are answered
    from the shared preset contract;
  * a measured benchmark is quoted with its unit, context, VRAM and the fact
    that it was measured on this PC; a missing benchmark says so;
  * release dates say "not recorded" (they are not in this tree);
  * a preset change and a model switch ask the EXISTING cards - through
    `jarvis_presets.apply_from_body` and `jarvis_models.switch_to` - and the
    answers say the card is waiting; they never approve anything and never
    claim a switch happened before the card;
  * ordinary chat ("what model is best for coding", "use the dark theme") is
    not turned into a switch;
  * the model's system prompt gains one honest model+preset line, and nothing
    when nothing is recorded.

Every fake is injected into `sys.modules`; the real preset contract is used, so
the sentences are the product's own words, not test copies.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parent

WORK = Path(tempfile.mkdtemp(prefix="jarvis-model-knowledge-"))
CONF = WORK / "config"
CONF.mkdir(parents=True, exist_ok=True)
(WORK / "home").mkdir(exist_ok=True)
os.environ["OPENJARVIS_HOME"] = str(WORK / "home")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONF)
os.environ["JARVIS_SCHEDULE_DB"] = str(WORK / "schedule.db")
os.environ.pop("JARVIS_BACKEND", None)
# The owner last applied General: the current preset comes from the real file.
(CONF / "presets-choice.json").write_text(json.dumps({"preset": "general"}), encoding="utf-8")

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name
          + (("\n        " + detail) if detail and not cond else ""))


def _fake_models(current="qwen3.5:9b", installed=None, switch=None):
    mod = types.ModuleType("jarvis_models")
    mod.CALLS = []
    mod.current_model = lambda: current
    mod.installed_models = lambda: list(installed or [])
    def switch_to(ref, why=""):
        mod.CALLS.append({"ref": ref, "why": why})
        return dict(switch or {"ok": True, "waiting": True})
    mod.switch_to = switch_to
    return mod


def _fake_hardware():
    mod = types.ModuleType("jarvis_hardware")
    mod._current_model = lambda: ""
    mod._main_url = lambda: ""
    mod._tags = lambda url: set()
    return mod


def _fake_recommendations(benchmarked=None):
    mod = types.ModuleType("jarvis_model_recommendations")
    store = {"benchmarked": dict(benchmarked or {})}
    mod.load_store = lambda path=None: dict(store)
    return mod


def main():
    import jarvis_schedule as SCH
    import jarvis_presets as P
    import jarvis_model_knowledge as K
    import jarvis_quick as Q
    import jarvis_agent as A

    sys.modules["jarvis_models"] = _fake_models(installed=["qwen3.5:9b", "qwen3.5:4b",
                                                           "qwen2.5vl:7b"])
    sys.modules["jarvis_hardware"] = _fake_hardware()
    sys.modules["jarvis_model_recommendations"] = _fake_recommendations({
        "qwen3.5:9b": {"tokens_per_s": 44.9, "context_tokens": 196608,
                       "vram_gb": 9.17, "measured_at": 1761000000.0},
    })
    sched = SCH.Scheduler(WORK / "schedule.db")
    ask = lambda text: Q.answer_turn(
        {"messages": [{"role": "user", "content": text, "provenance": "typed"}],
         "conversation_id": "abcdefgh-model"}, sched=sched)

    # --- 1. what is it running? ---------------------------------------------
    r = ask("what ai model do you have?")
    check("current: names the running model and the preset",
          r is not None and "qwen3.5:9b" in r.reply and "General" in r.reply
          and "You are running" in r.reply, getattr(r, "reply", None))
    r = ask("which model are you using?")
    check("current: the other shape answers the same fact",
          r is not None and "qwen3.5:9b" in r.reply)
    r = ask("which model answered that?")
    check("answerer: names the chat model and says no separate per-answer line",
          r is not None and "qwen3.5:9b" in r.reply and "per-answer" in r.reply,
          getattr(r, "reply", None))

    # --- 2. installed models and presets ------------------------------------
    r = ask("what local models are installed?")
    check("models: lists the installed tags and the one in use",
          r is not None and "qwen3.5:9b" in r.reply and "qwen3.5:4b" in r.reply
          and "qwen2.5vl:7b" in r.reply and "Chat is using qwen3.5:9b" in r.reply,
          getattr(r, "reply", None))
    r = ask("what presets do you have?")
    check("presets: lists the preset titles and the current one",
          r is not None and "General (current)" in r.reply and "Coding" in r.reply,
          getattr(r, "reply", None))
    check("presets: the real contract has the expected rows",
          len(P.PRESETS) >= 5 and P.by_id("general") is not None)
    r = ask("what does the coding preset change?")
    check("preset detail: its model, window and honest cost",
          r is not None and "Coding" in r.reply and "qwen3-coder" in r.reply.lower()
          and "HEAVY MODE" in r.reply, getattr(r, "reply", None))
    r = ask("which model would the general preset load?")
    check("preset detail: the model question shape",
          r is not None and "qwen3.5:9b" in r.reply, getattr(r, "reply", None))

    # --- 3. measured speed, pros/cons, releases -----------------------------
    r = ask("how fast is qwen3.5:9b?")
    check("speed: the measured row with its unit, context and provenance",
          r is not None and "44.9 tokens a second" in r.reply
          and "196,608 tokens" in r.reply and "measured on this PC" in r.reply,
          getattr(r, "reply", None))
    r = ask("how fast is qwen9:1b?")
    check("speed: a model with no benchmark says so, with where to measure",
          r is not None and "No benchmark is recorded on this PC" in r.reply
          and "Brain, Models" in r.reply, getattr(r, "reply", None))
    r = ask("what are the pros and cons of qwen3.5:9b?")
    check("pros/cons: the preset's own what/cost/worse words",
          r is not None and "Pros:" in r.reply and "Cons:" in r.reply
          and "Speed:" in r.reply and "Release date: not recorded" in r.reply,
          getattr(r, "reply", None))
    r = ask("when was qwen3.5:9b released?")
    check("release: 'not recorded', never an invented date",
          r is not None and "not recorded" in r.reply and "guess" in r.reply,
          getattr(r, "reply", None))

    # --- 4. advice, not a switch -------------------------------------------
    r = ask("which model should I use for coding?")
    check("recommend: names a preset, says it is advice and nothing switched",
          r is not None and "Coding" in r.reply and "This is advice" in r.reply
          and "nothing was switched" in r.reply, getattr(r, "reply", None))
    for text in ("use the dark theme", "what is the weather", "read my email"):
        got = ask(text)
        reply = getattr(got, "reply", "") or ""
        check(f"over-capture: {text!r} is not turned into a model switch",
              "approval card is up" not in reply and "Switching to" not in reply,
              reply[:200])

    # --- 5. switching uses the EXISTING cards, and never approves ----------
    import jarvis_models as fake_m
    import jarvis_presets as real_p
    seen = []
    real_apply = real_p.apply_from_body
    def fake_apply(body):
        seen.append(dict(body))
        return 202, {"ok": True, "state": "waiting", "waiting": True,
                      "said": "This starts the main lane, then ONE card switches the model."}
    real_p.apply_from_body = fake_apply
    try:
        r = ask("switch to the coding preset")
        check("preset switch: the one card is asked with the existing body",
              seen == [{"preset": "coding"}], seen)
        check("preset switch: the answer says the card is waiting, not that it switched",
              r is not None and "approval card is up" in r.reply
              and "Nothing switches" in r.reply and "ONE card" in r.reply,
              getattr(r, "reply", None))
        check("preset switch: the answer carries the PC's own preview",
              r is not None and "main lane" in r.reply)
    finally:
        real_p.apply_from_body = real_apply
    fake_m.switch_to = lambda ref, why="": (seen.append({"switch": ref}),
                                            {"ok": True, "waiting": True})[1]
    try:
        r = ask("switch to qwen3.5:4b")
        check("model switch: calls the existing switch_to with the ref",
              {"switch": "qwen3.5:4b"} in seen, seen)
        check("model switch: says the switch_model card is waiting",
              r is not None and "Switching to qwen3.5:4b" in r.reply
              and "approval card is up" in r.reply,
              getattr(r, "reply", None))
    finally:
        pass
    fake_m.switch_to = lambda ref, why="": {"ok": False, "reason": "you said no"}
    r = ask("switch to qwen3.5:4b")
    check("model switch: a refused card is reported as no change, not as done",
          r is not None and "nothing was changed" in r.reply
          and "you said no" in r.reply, getattr(r, "reply", None))

    # --- 6. the system prompt line -----------------------------------------
    line = K.prompt_line()
    check("prompt: one honest model+preset line",
          line == 'You are running as qwen3.5:9b on this PC, under the "General" preset.',
          line)
    msgs = A.with_rules_first([{"role": "user", "content": "hi"}])
    check("prompt: it is the second system message, rules still first",
          len(msgs) == 3 and msgs[0]["content"] == A.LANE_SYSTEM
          and msgs[1]["content"] == line, [m.get("content", "")[:40] for m in msgs])
    saved = K.prompt_line
    K.prompt_line = lambda: ""
    try:
        plain = A.with_rules_first([{"role": "user", "content": "hi"}])
        check("prompt: nothing recorded means exactly the old message list",
              len(plain) == 2 and plain[0]["content"] == A.LANE_SYSTEM)
    finally:
        K.prompt_line = saved

    # --- 7. no approval path, and the twin is identical ---------------------
    src = (HERE / "jarvis_model_knowledge.py").read_text(encoding="utf-8")
    for banned in ("import jarvis_gate", "gate_check", ".decide(", "approve_pending"):
        check(f"no approval path: the module never reaches {banned!r}",
              banned not in src)
    for name in ("jarvis_model_knowledge.py", "jarvis_quick.py", "jarvis_agent.py"):
        a = (REPO / "backend" / name).read_bytes()
        b = (REPO / "jarvis-backend" / name).read_bytes()
        check(f"twin: {name} is identical in both copies", a == b)
    where = (REPO / "backend" / "_where.py").read_text(encoding="utf-8")
    script = (REPO / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("shipped: named in both SHIPPED lists",
          '"jarvis_model_knowledge.py"' in where and "'jarvis_model_knowledge.py'" in script)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        FAILED.append("the suite itself raised")
    print()
    if FAILED:
        print(f"{len(PASSED)} passed, {len(FAILED)} FAILED")
        for name in FAILED:
            print(f"  FAIL {name}")
        sys.exit(1)
    print(f"{len(PASSED)} passed, 0 failed")
