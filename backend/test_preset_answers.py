"""test_preset_answers.py - what model a preset uses, answered from the preset
contract itself (the owner's 2026-11-02 wrong answer).

    python -B backend/test_preset_answers.py

THE OWNER'S BUG. Asked "what AI model will you use in the coding preset?" the
deployed chat answered `qwen3.5:9b` - the GENERAL preset's model - and denied
that any preset layers across the two cards. Both were false. The Coding row
in `backend/jarvis_presets.py` is `qwen3-coder-30b-a3b-ud-q3-k-xl`, heavy mode
across both cards, applied only after ONE approval card; PR #1106 is the
pooled both-card lane that makes it runnable, and on the tree this suite runs
against it is not deployed, so the honest answer says so.

WHAT THIS SUITE PROVES, on a fake PC state and the REAL preset contract:

  * every preset title answers with that row's own model, card and window;
  * the owner's exact phrasings are answered deterministically - the Coding
    model, both cards, ONE approval card, and "not live until that code is
    deployed" - and never `qwen3.5:9b` for Coding;
  * an unknown preset name says there is no such preset and lists the real
    ones instead of inventing a model;
  * a current-model question answers from the PC's own model record, and says
    "I do not know yet" when there is no record rather than quoting the
    chosen preset's model as if it were running;
  * "are you using both cards" answers from the preset contract and the lane
    reads, says "not right now" when no pooled lane is loaded, "yes" when one
    really is, and "I cannot read that" when the read fails;
  * `heavy_words` is used when the build has it, and the row's own `cost` is
    the fallback when it does not;
  * NO approval card is raised, no model switch or preset apply is asked, no
    cloud service is read, and no socket connection is attempted;
  * a near miss ("what model do you use", "what model of car do you drive",
    "which app can use the second card") keeps its old path.

Every fake is injected into `sys.modules`; the preset rows are the product's
own, so every sentence the answer quotes is the product's own words.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import traceback
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parent

WORK = Path(tempfile.mkdtemp(prefix="jarvis-preset-answers-"))
CONF = WORK / "config"
CONF.mkdir(parents=True, exist_ok=True)
(WORK / "home").mkdir(exist_ok=True)
os.environ["OPENJARVIS_HOME"] = str(WORK / "home")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CONF)
os.environ["JARVIS_SCHEDULE_DB"] = str(WORK / "schedule.db")
os.environ.pop("JARVIS_BACKEND", None)
# The owner last applied General, so "is it the chosen one?" has a real answer.
(CONF / "presets-choice.json").write_text(json.dumps({"preset": "general"}),
                                          encoding="utf-8")

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name
          + (("\n        " + str(detail)) if detail and not cond else ""))


def _fake_models(current="qwen3.5:9b", installed=None):
    mod = types.ModuleType("jarvis_models")
    mod.CURRENT = {"name": current}
    mod.CALLS = []
    mod.current_model = lambda: mod.CURRENT["name"]
    mod.installed_models = lambda: list(installed or [])

    def switch_to(ref, why=""):
        mod.CALLS.append({"ref": ref, "why": why})
        return {"ok": True, "waiting": True}

    mod.switch_to = switch_to
    return mod


def _fake_hardware():
    mod = types.ModuleType("jarvis_hardware")
    mod._current_model = lambda: ""
    mod._main_url = lambda: ""
    mod._tags = lambda url: set()
    return mod


def _fake_recommendations():
    mod = types.ModuleType("jarvis_model_recommendations")
    mod.load_store = lambda path=None: {}
    return mod


def _fake_second_card(state="off"):
    mod = types.ModuleType("jarvis_second_card")
    mod.STATE = {"state": state}
    mod.combined_lane_state = lambda: mod.STATE["state"]
    return mod


def _fake_lanes(pooled_key=True, running=False, raises=False):
    """The pooled lane's own read, in the shape PR #1106 adds."""
    mod = types.ModuleType("jarvis_model_lanes")
    if pooled_key:
        mod.POOLED_KEY = "pooled"
    mod.RUNNING = {"on": running}

    def pooled_running():
        if raises:
            raise RuntimeError("the lane read failed")
        return mod.RUNNING["on"]

    mod.pooled_running = pooled_running
    return mod


def _fake_cloud():
    mod = types.ModuleType("jarvis_chatbot_api")
    mod.CALLS = []
    mod.PRESETS = {}

    def key_saved(pid):
        mod.CALLS.append(("key_saved", pid))
        return None

    def ready_for(pid):
        mod.CALLS.append(("ready_for", pid))
        return ""

    def model_for(pid):
        mod.CALLS.append(("model_for", pid))
        return "", ""

    def money_view(pid):
        mod.CALLS.append(("money_view", pid))
        return None

    mod.key_saved = key_saved
    mod.ready_for = ready_for
    mod.model_for = model_for
    mod.money_view = money_view
    return mod


def _fake_gate():
    mod = types.ModuleType("jarvis_gate")
    mod.CALLS = []

    def check_gate(action, detail, prompt=""):
        mod.CALLS.append((action, detail))
        raise AssertionError("the preset answer must never reach the approval gate")

    mod.check = check_gate
    return mod


def main():
    import jarvis_schedule as SCH
    import jarvis_presets as P
    import jarvis_quick as Q

    models = _fake_models(installed=["qwen3.5:9b", "qwen3.5:4b",
                                     "qwen3-coder-30b-a3b-ud-q3-k-xl"])
    hardware = _fake_hardware()
    second_card = _fake_second_card("off")
    # main's shape: the pooled both-card lane does not exist in this build.
    lanes = _fake_lanes(pooled_key=False, running=False)
    cloud = _fake_cloud()
    gate = _fake_gate()
    sys.modules["jarvis_models"] = models
    sys.modules["jarvis_hardware"] = hardware
    sys.modules["jarvis_model_recommendations"] = _fake_recommendations()
    sys.modules["jarvis_second_card"] = second_card
    sys.modules["jarvis_model_lanes"] = lanes
    sys.modules["jarvis_chatbot_api"] = cloud
    sys.modules["jarvis_gate"] = gate

    card_calls = []
    real_apply = P.apply_from_body
    P.apply_from_body = lambda body: (card_calls.append(dict(body)),
                                      (500, {"ok": False}))[1]

    sched = SCH.Scheduler(WORK / "schedule.db")
    ask = lambda text: Q.answer_turn(
        {"messages": [{"role": "user", "content": text, "provenance": "typed"}],
         "conversation_id": "abcdefgh-preset"}, sched=sched)

    # ------------------------------------------------------------------
    #  1. The owner's exact wrong answer
    # ------------------------------------------------------------------
    owner = ask("what AI model will you use in the coding preset?")
    reply = getattr(owner, "reply", "") or ""
    check("owner phrase: it is the deterministic preset answer, not the model",
          owner is not None and owner.intent == "preset_model", owner)
    check("owner phrase: the Coding model is named",
          "qwen3-coder-30b-a3b-ud-q3-k-xl" in reply, reply)
    check("owner phrase: it does NOT answer qwen3.5:9b (the wrong answer)",
          "qwen3.5:9b" not in reply, reply)
    check("owner phrase: it says both cards",
          "both cards" in reply.lower(), reply)
    check("owner phrase: it says the pooled both-card lane is the plan",
          "one pooled lane" in reply and "RTX 2060" in reply
          and "RTX 2080 SUPER" in reply, reply)
    check("owner phrase: it says ONE approval card is needed",
          "ONE approval card" in reply and "nothing switches" in reply, reply)
    check("owner phrase: it says it is not live until the code is deployed",
          "not live until that code is deployed" in reply, reply)
    check("owner phrase: it does not claim the preset is the chosen one",
          "not the preset chosen" in reply and 'General' in reply, reply)

    for text in ("what model does the coding preset use?",
                 "which model will you use in the coding preset?",
                 "which model does the coding preset load?",
                 "what is the coding preset's model?",
                 "what model is used in the coding preset?"):
        got = ask(text)
        said = getattr(got, "reply", "") or ""
        check(f"shape: {text!r} answers the preset lane",
              got is not None and got.intent == "preset_model", got)
        check(f"shape: {text!r} names the Coding model",
              "qwen3-coder-30b-a3b-ud-q3-k-xl" in said, said)

    # ------------------------------------------------------------------
    #  2. Every preset title, from the real rows
    # ------------------------------------------------------------------
    for preset in P.PRESETS:
        title = str(preset.title)
        got = ask(f"what model does the {title.lower()} preset use?")
        said = getattr(got, "reply", "") or ""
        check(f"preset {title}: answered deterministically",
              got is not None and got.intent == "preset_model", got)
        check(f"preset {title}: the row's own model is named",
              str(preset.model) in said, said)
        if preset.heavy_mode:
            check(f"preset {title}: says both cards, not one card",
                  "both cards" in said.lower(), said)
            check(f"preset {title}: says ONE approval card",
                  "ONE approval card" in said, said)
            check(f"preset {title}: says the pooled lane is not in this build",
                  "not in this build yet" in said
                  and "not live until that code is deployed" in said, said)
        else:
            card = str((preset.lane_info or {}).get("card") or "")
            check(f"preset {title}: names its card",
                  card and card in said, said)
            check(f"preset {title}: names its window",
                  f"{int(preset.context):,} tokens" in said, said)
            check(f"preset {title}: does not claim both cards",
                  "both cards at once" not in said, said)
        if str(preset.id) == "general":
            check(f"preset {title}: is the one chosen on this PC",
                  "It is the preset chosen" in said, said)
        else:
            check(f"preset {title}: is not claimed as the chosen one",
                  "not the preset chosen" in said, said)

    cloud_row = ask("what model does the cloud preset use?")
    cloud_reply = getattr(cloud_row, "reply", "") or ""
    check("cloud row: says it is a service, not a local model",
          cloud_row is not None and cloud_row.intent == "preset_model"
          and "does not run one of the local models" in cloud_reply
          and "service you connect" in cloud_reply, cloud_reply)

    # ------------------------------------------------------------------
    #  3. An unknown preset invents nothing
    # ------------------------------------------------------------------
    unknown = ask("what model does the quantum preset use?")
    said = getattr(unknown, "reply", "") or ""
    check("unknown name: says there is no such preset",
          unknown is not None and unknown.intent == "preset_model"
          and 'There is no preset called "quantum"' in said, said)
    check("unknown name: lists every real title",
          all(str(p.title) in said for p in P.PRESETS), said)
    check("unknown name: invents no model", "qwen" not in said, said)

    # ------------------------------------------------------------------
    #  4. "are you using both cards" - the model's denial
    # ------------------------------------------------------------------
    both = ask("are you using both cards?")
    said = getattr(both, "reply", "") or ""
    check("both cards: answered deterministically",
          both is not None and both.intent == "both_cards", both)
    check("both cards: names the Coding model",
          "qwen3-coder-30b-a3b-ud-q3-k-xl" in said, said)
    check("both cards: says Coding is the both-card preset",
          "Coding is the one that uses both cards" in said, said)
    check("both cards: says ONE approval card",
          "ONE approval card" in said, said)
    check("both cards: on this build says it is not live yet",
          "not in this build yet" in said
          and "not live until that code is deployed" in said, said)
    check("both cards: every other preset is one card",
          "Every other preset runs on one card" in said, said)
    # The same fact asked round the other way.
    for text in ("does the coding preset use both cards?",
                 "do you layer the model across both cards?",
                 "are both cards in use?",
                 "are you layering models?"):
        got = ask(text)
        check(f"both cards shape: {text!r}",
              got is not None and got.intent == "both_cards", got)

    # A real pooled lane that IS running says yes; a stopped one says no.
    sys.modules["jarvis_model_lanes"] = _fake_lanes(pooled_key=True, running=True)
    got = ask("are you using both cards?")
    said = getattr(got, "reply", "") or ""
    check("both cards: a running pooled lane answers YES and names it",
          "Yes - the Coding preset is running one model across both cards" in said,
          said)
    check("both cards: a running pooled lane quotes the row's window",
          f"{int(P.by_id('coding').context):,} tokens" in said, said)
    sys.modules["jarvis_model_lanes"].RUNNING["on"] = False
    got = ask("are you using both cards?")
    said = getattr(got, "reply", "") or ""
    check("both cards: a stopped pooled lane says NOT right now",
          "Not right now: no pooled both-card lane is loaded" in said, said)
    sys.modules["jarvis_model_lanes"] = _fake_lanes(pooled_key=True, raises=True)
    got = ask("are you using both cards?")
    said = getattr(got, "reply", "") or ""
    check("both cards: a read that fails says I cannot tell you",
          "I cannot read the model lanes on this PC" in said
          and "cannot tell" in said, said)
    # The separate "One bigger model on both cards" mode is its own fact.
    sys.modules["jarvis_model_lanes"] = _fake_lanes(pooled_key=False, running=False)
    second_card.STATE["state"] = "running"
    got = ask("are you using both cards?")
    said = getattr(got, "reply", "") or ""
    check("both cards: the combined mode is named as a mode of its own",
          "One bigger model on both cards" in said
          and "mode of its own" in said, said)
    second_card.STATE["state"] = "off"

    # ------------------------------------------------------------------
    #  5. A current-model question reads the real record, or says so
    # ------------------------------------------------------------------
    got = ask("what model are you using now?")
    said = getattr(got, "reply", "") or ""
    check("current model: names the recorded model and the chosen preset",
          got is not None and got.intent == "model_current"
          and "You are running qwen3.5:9b" in said and "General" in said, said)
    saved = models.CURRENT["name"]
    models.CURRENT["name"] = None
    got = ask("what model are you using now?")
    said = getattr(got, "reply", "") or ""
    check("current model: no record says I do not know yet",
          "does not record which model is actually running" in said
          and "I do not know yet" in said, said)
    check("current model: ... and never claims the preset's model is running",
          "You are running" not in said, said)
    models.CURRENT["name"] = saved

    # ------------------------------------------------------------------
    #  6. heavy_words wins when present; the row's cost is the fallback
    # ------------------------------------------------------------------
    heavy = dict(P.by_id("coding").view())
    heavy["heavy_words"] = "HEAVY-WORDS-SENTINEL: both cards, the other models pause."
    heavy["lane"] = {"key": "pooled", "card": "both cards", "port": 11450,
                     "words": "one model across both cards"}
    words = Q._preset_answer(heavy)
    check("heavy_words: used when this build has the field",
          "HEAVY-WORDS-SENTINEL" in words, words)
    check("heavy_words: the row's cost text is replaced, not repeated",
          str(P.by_id("coding").cost) not in words, words)
    check("heavy_words: a pooled row is described as live, not 'arriving later'",
          "one pooled lane" in words and "not live until" not in words, words)
    plain = dict(P.by_id("coding").view())
    plain.pop("heavy_words", None)
    words = Q._preset_answer(plain)
    check("heavy_words: absent means the row's own cost is the fallback",
          str(P.by_id("coding").cost) in words, words)
    check("heavy_words: without the pooled lane it says it is not live yet",
          "not in this build yet" in words
          and "not live until that code is deployed" in words, words)

    # ------------------------------------------------------------------
    #  7. Near misses keep their old path (no hijack)
    # ------------------------------------------------------------------
    got = Q.match("what model do you use")
    check("near miss: 'what model do you use' is still identity_help",
          got is not None and got.name == "identity_help", got)
    check("near miss: 'what model of car do you drive' is still the model's",
          Q.match("what model of car do you drive") is None,
          Q.match("what model of car do you drive"))
    got = Q.match("which app can use the second card")
    check("near miss: the second-card feature question is not both_cards",
          got is None or got.name != "both_cards", got)
    got = Q.match("what model are you running")
    check("near miss: 'what model are you running' is still model_current",
          got is not None and got.name == "model_current", got)

    # ------------------------------------------------------------------
    #  8. No card, no switch, no cloud call, no socket
    # ------------------------------------------------------------------
    check("no card: jarvis_presets.apply_from_body was never called",
          card_calls == [], card_calls)
    check("no switch: jarvis_models.switch_to was never called",
          models.CALLS == [], models.CALLS)
    check("no card: the approval gate was never reached", gate.CALLS == [], gate.CALLS)
    check("no cloud: no cloud service was read", cloud.CALLS == [], cloud.CALLS)
    connects = []

    def counted_connect(self, address):
        connects.append(address)
        raise OSError("network blocked by test_preset_answers")

    real_connect = socket.socket.connect
    socket.socket.connect = counted_connect
    try:
        for text in ("what AI model will you use in the coding preset?",
                     "what model does the fast preset use?",
                     "are you using both cards?",
                     "what model are you using now?"):
            ask(text)
    finally:
        socket.socket.connect = real_connect
    check("no cloud: no network connection was attempted", connects == [], connects)

    # ------------------------------------------------------------------
    #  9. The twin is identical, so the deployed copy is the tested one
    # ------------------------------------------------------------------
    a = (REPO / "backend" / "jarvis_quick.py").read_bytes()
    b = (REPO / "jarvis-backend" / "jarvis_quick.py").read_bytes()
    check("twin: jarvis_quick.py is identical in both copies", a == b)

    P.apply_from_body = real_apply


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
