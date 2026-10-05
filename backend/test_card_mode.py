"""The owner's choice between the two ways to use two graphics cards.

    python3 test_card_mode.py

WHAT THIS IS. On 2026-10-05 the owner asked to be given a choice between the
two ways his two cards can be used - "split" (one bigger model spread across
both cards) and "concurrent" (two different models at once, one per card) -
rather than working it out from the switches. Both ways already existed
(split is the "combined" switch, concurrent is every other switch here) and so
did the rule that they cannot both run. What was added is the CHOICE:
`status()["mode"]`, and one plain sentence per way saying what it costs.

WHAT THIS PROVES, all without a graphics card, a real Ollama or the owner's
PC (nvidia-smi's output is replayed in its real CSV format by
tools/gen_second_card_cases.World, and starting a process is recorded, never
really done - the same stand-in backend/test_second_card.py uses):

  - the choice is DERIVED from the switches and never stored: a "mode" written
    into second-card.json by hand is not read, and Jarvis never writes one, so
    the choice and the switches cannot disagree;
  - the invalid combination is impossible through the API - the second way is
    refused (409) while the first is set up, in both directions, and the
    refusal NAMES the switches to turn off instead of leaving the owner to
    find them;
  - it is impossible in reality too: a hand-edited file holding both is
    reported as no choice at all, in words, and starts NEITHER lane;
  - picking the split raises the SAME approval card the switch already raises
    (second_card_combined_enable, tier ask) - no new action, no new Ollama,
    no new port and nothing added to the gate tables;
  - picking the split really reaches the Ollama the backend launches, and only
    that one: OLLAMA_SCHED_SPREAD=1 is set for the process Jarvis starts, an
    inherited value is dropped first, and the everyday Ollama's own pinning is
    not touched;
  - the words on screen are plain, and each way says what it costs;
  - the desktop Settings page offers the choice, through the EXISTING
    set_second_card command, and hides it on a backend that has no mode.
"""
import json
import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import BACKEND, REPO, missing  # noqa: E402

for p in (REPO / "tools", HERE / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.append(str(p))

import jarvis_second_card as SC  # noqa: E402
import gen_second_card_cases as G  # noqa: E402

PASSED, FAILED, SKIPPED = [], [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(name, why):
    """Said plainly, never faked: a `check(name, True)` would claim this was
    proved when it was not."""
    SKIPPED.append(name)
    print(f"skip  {name} - {why}")


class Verdict:
    """A person's answer at the approval gate, the same shape the real
    jarvis_gate returns and the same one test_second_card.py uses."""

    def __init__(self, allowed, tier="ask", outcome=None, request_id="r1", reason=""):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome
        self.request_id, self.reason = request_id, reason


def approving():
    return lambda a, d, p: Verdict(True, "ask", "approved")


SW_OFF = {"master": False, "combined": False,
          "features": {f: False for f in SC.FEATURE_IDS}}


def switches(**kw) -> dict:
    """A whole switch reading, the way _read_switches returns one."""
    feats = kw.pop("features", ())
    out = {"master": bool(kw.get("master")), "combined": bool(kw.get("combined")),
           "features": {f: (f in feats) for f in SC.FEATURE_IDS}}
    return out


# --------------------------------------------------------------- the guard --


def t_the_choice_is_derived_and_never_stored():
    # The whole guard: there is no stored "mode", so no saved setting can say
    # one thing while the switches say another.
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(master=True, learning=True)
        p = w.dir / "second-card.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["mode"] = SC.MODE_SPLIT     # a lie: "combined" is off, so this is not the split
        p.write_text(json.dumps(data), encoding="utf-8")
        sw = SC._read_switches()
        check("a hand-written \"mode\" in the file is not part of the switches",
              "mode" not in sw, sorted(sw))
        check("the choice is read from the switches, never from that field",
              SC.current_mode(sw, SC.detect(fresh=True)) == SC.MODE_CONCURRENT,
              SC.current_mode(sw, SC.detect(fresh=True)))
        # ... and Jarvis never writes one, whichever switch moves.
        SC.request_change("combined", False)
        SC.request_change("learning", False)
        SC._write_switch("master", True)
        written = json.loads(p.read_text(encoding="utf-8"))
        check("nothing Jarvis writes ever saves a \"mode\"", "mode" not in written, sorted(written))
        check("the file still holds the switches themselves",
              set(written) >= {"master", "combined", "features"}, sorted(written))


def t_mode_reads_the_switches():
    det = {"capable": True}
    check("nothing on: no way is chosen yet, and that is not \"concurrent\"",
          SC.current_mode(SW_OFF) == "")
    check("the main switch alone: still nothing chosen (no feature, so no second model)",
          SC.current_mode(switches(master=True)) == "")
    check("a feature on without the main switch: nothing chosen either (it cannot run)",
          SC.current_mode(switches(features=("learning",))) == "")
    check("main switch and a feature: concurrent",
          SC.current_mode(switches(master=True, features=("learning",))) == SC.MODE_CONCURRENT)
    check("\"combined\" on: split",
          SC.current_mode(switches(combined=True)) == SC.MODE_SPLIT)
    check("both saved on: neither, not a made-up winner",
          SC.current_mode(switches(master=True, combined=True, features=("learning",))) == "")
    check("Referee loads no model, so on its own it is not \"two models\"",
          SC.current_mode(switches(master=True, features=("referee",))) == "")
    check("a chosen hardware preset runs the extra features on ONE card, so it is neither way",
          SC.current_mode(switches(master=True, features=("learning",)), {"capable": True,
                                                                         "_main": True}) == "")
    check("but \"combined\" is asked first: a preset does not stop it starting its own Ollama",
          SC.current_mode(switches(combined=True), {"capable": True, "_main": True})
          == SC.MODE_SPLIT)


def t_one_definition_of_the_clash():
    # conflict_ids and _combined_conflict are the same test, so a refusal can
    # name the switches and the guard cannot drift from the words.
    bad = []
    for master in (False, True):
        for combined in (False, True):
            for feats in ((), ("learning",), ("vision", "wiki"), ("referee",)):
                sw = switches(master=master, combined=combined, features=feats)
                if bool(SC.conflict_ids(sw)) != SC._combined_conflict(sw):
                    bad.append((master, combined, feats))
    check("conflict_ids and _combined_conflict agree for every combination", not bad, bad)
    check("conflict_ids is in the apps' own order (FEATURE_IDS), not alphabetical",
          SC.conflict_ids(switches(master=True, features=("wiki", "vision", "long_context")))
          == ["long_context", "vision", "wiki"],
          SC.conflict_ids(switches(master=True, features=("wiki", "vision", "long_context"))))
    check("a model-free switch never counts as a clash",
          SC.conflict_ids(switches(master=True, features=("referee",))) == [])
    check("the main switch off means nothing clashes (no feature runs without it)",
          SC.conflict_ids(switches(features=("learning",))) == [])


def t_the_two_ways_cannot_both_be_on():
    with G.World(G.SMI["2080s_2060"]):
        # split asked for while concurrent is set up: refused, and it says which switch.
        with G.World(G.SMI["2080s_2060"]) as w:
            w.switches(master=True, learning=True)
            code, out = SC.request_change("combined", True, gate=lambda *a: None)
            check("picking split while a switch is on: refused (409), no card raised",
                  code == 409 and "both cards to itself" in out["error"], out)
            check("the refusal NAMES the switch to turn off, instead of saying \"the features\"",
                  "\"Learning in the background\"" in out["error"]
                  and "Turn it off first" in out["error"], out["error"])
            check("nothing was turned on by the refusal",
                  SC._read_switches()["combined"] is False)
        with G.World(G.SMI["2080s_2060"]) as w:
            w.switches(master=True, vision=True, wiki=True)
            code, out = SC.request_change("combined", True, gate=lambda *a: None)
            check("two switches on: both are named, in the apps' order",
                  code == 409 and "\"Pictures\" and \"Wiki builder\"" in out["error"]
                  and "Turn them off first" in out["error"], out["error"])
        # the other direction: concurrent asked for while split is set up.
        with G.World(G.SMI["2080s_2060"]) as w:
            w.switches(combined=True)
            for feature in ("learning", "master"):
                code, out = SC.request_change(feature, True, gate=lambda *a: None)
                check(f"picking {feature} while split is set up: refused (409)",
                      code == 409 and "Turn that off first" in out["error"], out)
            st = SC.status()
            check("and the choice still reads as split - the two never both look chosen",
                  st["mode"]["mode"] == SC.MODE_SPLIT and st["mode"]["conflict"] is False,
                  st["mode"])


def t_a_damaged_file_runs_neither_way():
    # A hand-edited file, or a machine that died between two writes. The
    # backend refuses this through the API, so it should not be reachable -
    # but "should not" is not "cannot", and the cards must not be fought over.
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(master=True, combined=True, learning=True)
        st = SC.status()
        m = st["mode"]
        check("both saved on: the choice is reported as none, not as a winner",
              m["mode"] == "" and m["chosen"] is False, m)
        check("and it is called a contradiction in words",
              m["conflict"] is True and "cannot both run" in m["conflict_why"], m)
        check("the contradiction names both sides",
              "\"One bigger model on both cards\"" in m["conflict_why"]
              and "\"Learning in the background\"" in m["conflict_why"], m["conflict_why"])
        check("NEITHER lane is running, so the cards are not fought over",
              st["lane"]["state"] == "off" and SC._COMBINED_LANE.state == "off"
              and not w.running(), (st["lane"], SC._COMBINED_LANE.state))
        check("the split option can still be picked once the clash is gone",
              m["options"][0]["available"] is False
              and "Turn" in m["options"][0]["blocked"], m["options"][0])


# ------------------------------------------------------ picking one, really --


def t_picking_split_is_the_existing_card_and_it_takes_effect():
    with G.World(G.SMI["2080s_2060"]) as w:
        before = SC.status()
        check("a fresh PC: neither way chosen, and split is offered with nothing in its way",
              before["mode"]["mode"] == "" and before["mode"]["options"][0]["available"] is True
              and before["mode"]["options"][0]["blocked"] == "", before["mode"])
        check("the heading and the note come from the backend, in plain words",
              before["mode"]["title"] == SC.MODE_TITLE and before["mode"]["note"] == SC.MODE_NOTE
              and before["mode"]["title"].endswith("?"), before["mode"]["title"])
        seen = []
        gate = lambda a, d, p: seen.append((a, d, p)) or Verdict(True, "ask", "approved")
        code, out = SC.request_change("combined", True, gate=gate)
        check("picking split raises exactly ONE card, the action the switch already used",
              code == 200 and out["pending"] is True and len(seen) == 1
              and seen[0][0] == SC.COMBINED_ACTION == "second_card_combined_enable",
              (code, out, seen))
        check("the card is the split's own words: both cards, the model, the pace, unmeasured",
              all(w in seen[0][2] for w in ("RTX 2080 SUPER", "RTX 2060", "qwen3:14b",
                                            "bigger, slower card", "not measured yet")),
              seen[0][2])
        check("it is raised at tier ask, and says nothing leaves this PC",
              seen[0][1]["leaves_this_pc"] is False, seen[0][1])
        st = SC.status()
        check("the choice reads back off the switch once approved: split",
              SC._read_switches()["combined"] is True and st["mode"]["mode"] == SC.MODE_SPLIT
              and st["mode"]["chosen"] is True, st["mode"])
        check("the chosen way's own name and words are shown",
              st["mode"]["name"] == SC.MODE_NAME[SC.MODE_SPLIT]
              and st["mode"]["detail"] == SC.MODE_DETAIL[SC.MODE_SPLIT], st["mode"])
        check("the other way says why it cannot be picked: name the switch that clashes",
              st["mode"]["options"][1]["selected"] is False)
        check("the split option shows as selected, and the concurrent one does not",
              st["mode"]["options"][0]["selected"] is True
              and st["mode"]["options"][1]["selected"] is False, st["mode"]["options"])
        check("after approval the second-card lane is off and only the combined one runs",
              st["lane"]["state"] == "off" and SC._COMBINED_LANE.state == "running",
              (st["lane"], SC._COMBINED_LANE.state))


def t_picking_concurrent_stops_splitting_at_once():
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(combined=True)
        SC.status()          # really starts the combined Ollama, as a page visit would
        seen = []
        gate = lambda a, d, p: seen.append(a) or Verdict(True, "ask", "approved")
        code, out = SC.request_change("combined", False, gate=gate)
        check("picking the other way is at once, and raises no card at all",
              code == 200 and not seen and out.get("pending") is False, (code, out, seen))
        check("it really stopped: the combined Ollama is stopped",
              SC._read_switches()["combined"] is False and bool(w.killed), w.killed)
        check("and the choice now reads as none, because nothing else is set up",
              SC.status()["mode"]["mode"] == "", SC.status()["mode"])
        check("the option says plainly what is still missing before two models run",
              "Nothing is set up on the second card yet" in
              SC.status()["mode"]["options"][1]["hint"],
              SC.status()["mode"]["options"][1])
    # ... and once the switches below are on, the other way is the one chosen.
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(master=True, learning=True)
        st = SC.status()
        check("main switch plus a feature: the choice reads as concurrent",
              st["mode"]["mode"] == SC.MODE_CONCURRENT
              and st["mode"]["options"][1]["selected"] is True, st["mode"])
        check("the per-card lane really is the one running",
              st["lane"]["state"] == "running" and SC._COMBINED_LANE.state == "off",
              (st["lane"], SC._COMBINED_LANE.state))
        check("the split option then says which switch to turn off",
              st["mode"]["options"][0]["available"] is False
              and "\"Learning in the background\"" in st["mode"]["options"][0]["blocked"],
              st["mode"]["options"][0])


def t_split_reaches_the_ollama_it_launches():
    # The claim the whole feature rests on, and the one the owner was told was
    # "one environment variable": OLLAMA_SCHED_SPREAD really is set, really on
    # the process Jarvis starts, and really does not depend on his own
    # environment or on his everyday Ollama.
    spread = SC.lane_env((G.U_2080S, G.U_2060), port=11435, num_ctx=32768, base={}, spread=True)
    check("the split's Ollama is given every card it may use, and the spread setting",
          spread["CUDA_VISIBLE_DEVICES"] == f"{G.U_2080S},{G.U_2060}"
          and spread["OLLAMA_SCHED_SPREAD"] == "1", spread)
    check("... with no pin to a single card, which is the whole point of the split",
          "," in spread["CUDA_VISIBLE_DEVICES"] and spread["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID",
          spread)
    inherited = SC.lane_env((G.U_2080S, G.U_2060), port=11435, num_ctx=32768,
                            base={"OLLAMA_SCHED_SPREAD": "0"}, spread=True)
    check("a value inherited from the owner's own environment is dropped, then set for this "
          "instance only", inherited["OLLAMA_SCHED_SPREAD"] == "1", inherited)
    per_card = SC.lane_env(G.U_2060, port=11435, num_ctx=32768, base={})
    check("the per-card lane (concurrent) never sets it: one card cannot spread a model",
          "OLLAMA_SCHED_SPREAD" not in per_card, per_card)
    check("and a per-card lane stays pinned to its one card, by id",
          per_card["CUDA_VISIBLE_DEVICES"] == G.U_2060
          and G.U_2080S not in per_card["CUDA_VISIBLE_DEVICES"], per_card)
    # The everyday Ollama is a different program the owner pinned himself.
    cmd = SC.pin_command(G.U_2080S) or ""
    check("the everyday Ollama's own pinning is unchanged, and never told to spread",
          "OLLAMA_SCHED_SPREAD" not in cmd and "CUDA_VISIBLE_DEVICES" in cmd, cmd)
    with G.World(G.SMI["2080s_2060"]) as w:
        w.switches(combined=True)
        SC.status()
        env = next((p.kwargs["env"] for p in w.started
                    if p.kwargs["env"].get("OLLAMA_SCHED_SPREAD") == "1"), None)
        check("a split that is really on starts an Ollama carrying the spread setting",
              env is not None and env["CUDA_VISIBLE_DEVICES"] == f"{G.U_2080S},{G.U_2060}",
              [p.kwargs["env"] for p in w.started])


# ------------------------------------------------------------ the words -----


def t_the_words_are_plain_and_say_the_tradeoff():
    strings = [SC.MODE_TITLE, SC.MODE_NOTE] + list(SC.MODE_NAME.values()) \
        + list(SC.MODE_DETAIL.values())
    bad = [s for s in strings if re.search(r"[{}]|HTTP \d|\bNone\b|\bnull\b|_|\[object", s)]
    check("every word is plain: no JSON, no code, no field names", not bad, bad)
    split, conc = SC.MODE_DETAIL[SC.MODE_SPLIT], SC.MODE_DETAIL[SC.MODE_CONCURRENT]
    check("the split says what it buys: a model bigger than either card holds alone",
          "bigger model" in split and "neither card could hold on its own" in split, split)
    check("the split says what it costs: every word crosses between the cards, so it is slower",
          "cross" in split and "slower card's pace" in split, split)
    check("the split says it needs both cards, so the switches below cannot be on",
          "BOTH cards to itself" in split, split)
    check("the split warns about the everyday model still holding memory on a card",
          "everyday model" in split and "free" in split, split)
    check("the concurrent way says what it buys: full speed each, at the same time",
          "full speed" in conc and "at the same time" in conc, conc)
    check("the concurrent way says what it costs: each model must fit its own card",
          "fit on its own card" in conc, conc)
    check("the note says plainly that the two cannot both run",
          "cannot both run at once" in SC.MODE_NOTE, SC.MODE_NOTE)
    check("the heading asks the question in the owner's own terms",
          "graphics cards" in SC.MODE_TITLE, SC.MODE_TITLE)
    with G.World(G.SMI["2080s_2060"]) as w:
        for label, st in (("nothing on", {}),
                          ("split on", {"combined": True}),
                          ("concurrent on", {"master": True, "learning": True})):
            w.switches(**st)
            m = SC.status()["mode"]
            every = [m["note"], m["title"], m["conflict_why"]] + \
                [o[k] for o in m["options"] for k in ("name", "detail", "blocked", "hint")]
            raw = [s for s in every if re.search(r"[{}]|HTTP \d|\bNone\b|\bnull\b|_", s)]
            check(f"status()'s mode block is plain too ({label})", not raw, raw)
            check(f"every option has a name and its own tradeoff words ({label})",
                  all(o["name"] and o["detail"] for o in m["options"]), m["options"])


def t_no_new_approval_action_was_added():
    # Reusing the "combined" card means the gate tables, the toml and both
    # apps' "what asks first" pages are untouched by this feature. If a new
    # action ever appears, this fails and whoever added it has to say why.
    import jarvis_asks_first as AF
    for action in ("second_card_mode", "second_card_split", "second_card_card_mode"):
        check(f"no gate action called {action} exists",
              action not in AF.HARD_LIMITS and action not in AF.MUST_ASK)
    toml = (BACKEND / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    actions = sorted(set(re.findall(r"^(second_card_[a-z_]+)\s*=", toml, re.M)))
    check("the toml still has exactly the four second-card approval actions",
          actions == ["second_card_browser_enable", "second_card_combined_enable",
                      "second_card_enable", "second_card_third_assign"], actions)
    check("picking the split is still tier ask (a person must say yes)",
          SC.COMBINED_ACTION in AF.MUST_ASK)
    check("the module's own action list is unchanged",
          (SC.ACTION, SC.BROWSER_ACTION, SC.THIRD_ACTION, SC.COMBINED_ACTION)
          == ("second_card_enable", "second_card_browser_enable", "second_card_third_assign",
              "second_card_combined_enable"))


# ------------------------------------------------- the two apps' screens ----


def t_the_desktop_offers_the_choice():
    html = (REPO / "jarvis-desktop" / "src" / "settings.html").read_text(encoding="utf-8")
    js = (REPO / "jarvis-desktop" / "src" / "settings.js").read_text(encoding="utf-8")
    check("settings.html has the choice's own block inside the graphics-cards card",
          all(f'id="{i}"' in html for i in ("sc-mode-section", "sc-mode-title", "sc-mode-note",
                                            "sc-mode-conflict", "sc-mode-options",
                                            "sc-mode-status")))
    check("it sits in the second-card section, above the switches it is the front door to",
          html.index('id="second-card"') < html.index('id="sc-mode-options"')
          < html.index('id="sc-switches"'))
    # Only the mode block's own source, so "no new command" is a real check.
    start = js.index("function scModeWanted(")
    block = js[start:js.index("function scPaint(status)")]
    check("the page draws the choice from the backend's own options, never a list of its own",
          "status.mode" in block and "mode.options" in block, "")
    check("picking a way posts through the EXISTING set_second_card command, and no other",
          set(re.findall(r'invoke\("([a-z_]+)"', block)) == {"set_second_card"},
          set(re.findall(r'invoke\("([a-z_]+)"', block)))
    check("and what it sends is the same switch the \"combined\" row already drives",
          re.search(r'invoke\("set_second_card", \{ feature: "combined", enabled: wanted \}\)',
                    block) is not None
          and re.search(r'function scModeWanted\(id\) \{\s*return id === "split";',
                        block) is not None, "")
    check("an older backend with no mode hides the whole block instead of drawing blanks",
          "modeSection.hidden = true" in block and "!mode.options.length" in block)
    check("the plain words come from the backend, not typed twice in JavaScript",
          "mode.detail" not in block and "MODE_DETAIL" not in block
          and "mode.title" in block and "mode.note" in block)
    check("the choice is drawn by scPaint, before the one-shot focus marker is cleared",
          js.index("scModePaint(status);") < js.index("scRestoreFocusId = null;",
                                                     js.index("scModePaint(status);")))
    # The page reads fields by name; the backend sends them by name. Checked
    # against the fixture, so a rename on one side cannot pass silently.
    case = json.loads((REPO / "jarvis-desktop" / "tests" / "fixtures"
                       / "second-card-cases.json").read_text(encoding="utf-8"))["cases"]
    mode = case["capable_off"]["mode"]
    block = mode["options"][0]
    check("the page reads each option field the backend really sends",
          all(f"option.{k}" in js or f"mode.{k}" in js
              for k in ("id", "name", "detail", "selected", "available", "blocked", "hint",
                        "pending"))
          and all(k in block for k in ("id", "name", "detail", "selected", "available",
                                       "blocked", "hint", "pending")), sorted(block))
    check("and the block fields too",
          all(f"mode.{k}" in js for k in ("title", "note", "conflict_why", "options"))
          and all(k in mode for k in ("title", "note", "conflict_why", "options")), sorted(mode))
    # The existing "One bigger model on both cards" switch must say it is the
    # same setting, or the page shows one thing twice with no explanation.
    check("the older combined switch's own note says it is the same setting as the choice",
          "This is the same setting as" in html)


def t_the_phone_already_has_the_same_decision():
    # The phone's own plate already shows the "combined" switch, which IS the
    # split. Since the choice is derived on the PC, the phone needs no change
    # to be correct - said plainly rather than claimed as a second build.
    plate = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis"
             / "client" / "ui" / "screens" / "SecondCardPlate.kt")
    if not plate.is_file():
        skip("the phone's second-card plate", "the Android app is not in this checkout")
        return
    text = plate.read_text(encoding="utf-8")
    check("the phone already offers the split as its own switch",
          "combinedSwitch" in text and "One bigger model on both cards" in text)
    second = (REPO / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis"
              / "client" / "net" / "SecondCard.kt")
    net = second.read_text(encoding="utf-8")
    check("and the phone's reader is hand-written per field, so the PC's new key cannot break it",
          'obj["features"]' in net and 'obj["combined"]' in net)
    check("the phone was NOT given a copy of the choice's words: one source, on the PC",
          "One model across both cards" not in net and "Two models at once" not in net)


def t_real_two_card_hardware():
    # The one thing no stand-in can prove: how Ollama really places a split
    # model on real cards. It needs two cards, and this suite deliberately
    # never starts or stops a real Ollama (the owner's machine is not ours to
    # change), so where there are not two cards it says so rather than faking
    # a pass.
    cards = SC._cards(fresh=True)
    if len(cards) < 2:
        skip("a split on two real graphics cards",
             f"this machine reports {len(cards)} NVIDIA card(s); the split's placement and its "
             f"speed are recorded as unmeasured (docs/MODEL-TOPOLOGY.md)")
        return
    ok, why = SC._combined_capable(SC.detect(fresh=True))
    check("two real cards: the split is offered, with no reason to refuse it", ok, why)
    check("and the choice's own answer agrees with the switch's",
          SC.status()["mode"]["options"][0]["available"] is ok)


if __name__ == "__main__":
    if missing("jarvis_second_card.py"):
        print("jarvis_second_card.py is not here: " + str(BACKEND))
        sys.exit(1)
    tests = [v for k, v in list(globals().items()) if k.startswith("t_") and callable(v)]
    for fn in tests:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(fn.__name__)
            traceback.print_exc()
    tail = f"\n{len(PASSED)} passed, {len(FAILED)} failed"
    if SKIPPED:
        tail += f", {len(SKIPPED)} skipped"
    print(tail)
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    sys.exit(1 if FAILED else 0)
