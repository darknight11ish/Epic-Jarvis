"""test_presets_cloud.py - the Cloud row in the Presets menu, and the ONE card
its apply raises (the owner's decision, 2026-10-27).

    python3 backend/test_presets_cloud.py

WHAT THIS PROVES, and why each check is here

  * the Cloud row is a SIXTH row in the same shape as the five presets and is
    NOT one of them: `PRESET_IDS` stays five, so both apps' five-row list is
    unchanged and the phone needs no code change at all;
  * `/api/presets` gains `cloud_preset` and `cloud` and nothing else - the five
    presets are byte-for-byte what they were (additive keys only);
  * `cloud.providers` has one row per connected service and NEVER carries a
    key, a fragment of one, or a message;
  * applying the cloud preset with no provider, or one this PC does not know,
    refuses with 400 and names the six, BEFORE any card;
  * a service with no key refuses with 409 and the PC's own sentence, also
    before any card (`ready_for`), so no approval is asked for something that
    cannot work;
  * with a gate that says NO, nothing is written - no `cloud-choice.json`, no
    `presets-choice.json`;
  * with a gate that says YES, both files are written and `cloud.provider`
    says which one;
  * THE BITE THAT MATTERS: a cloud apply starts NO lane and switches NO model.
    A cloud preset changes nothing local; starting a GPU lane for it would
    unload the model the owner is using. Both spies are asserted never called.
  * `cloud_lanes()` is the ONE lane when a provider is chosen and NONE when it
    is not - which is `jarvis_router.choose()`'s gate "unavailable", never a
    substituted name;
  * the two sources of truth agree: `cloud_view()["providers"][i]["ready"]` is
    the same answer `jarvis_chatbot_api.lane_status()` gives for that service.

WHAT IS REAL AND WHAT IS INJECTED. The real `jarvis_presets.py` and the real
`jarvis_chatbot_api.py` are driven. The monthly money file, Credential Manager
and the approval gate are stood in for: this suite must never read the owner's
real key store, must never spend, and must never post a card anywhere. A fresh
`OPENJARVIS_CONFIG_DIR` is used, so nothing on this PC is touched.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BASE = REPO / "jarvis-backend"
REBUILT = HERE / "rebuilt"

#: A scratch home BEFORE anything reads a settings file.
SCRATCH = Path(tempfile.mkdtemp(prefix="jarvis-presets-cloud-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_SUITE_RUNNING"] = "1"
# No push, said explicitly rather than relied on.
os.environ["JARVIS_NTFY_TOPIC"] = ""
os.environ["JARVIS_NTFY_SERVER"] = ""

sys.dont_write_bytecode = True
sys.path.insert(0, str(REBUILT))
sys.path.insert(0, str(HERE))

import jarvis_chatbot_api as API  # noqa: E402
import jarvis_presets as P  # noqa: E402

FAILED, PASSED = [], []

#: A key-shaped string that must never appear in any answer this suite reads.
KEY = "sk-test-cloud-preset-0123456789"
STORE: dict = {}
MONEY = {"deepseek_api": {"limit": 5.0, "spent": 0.5}}


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class _Verdict:
    def __init__(self, allowed: bool, outcome: str = "") -> None:
        self.allowed = bool(allowed)
        self.outcome = outcome or ("approved" if allowed else "denied")
        self.reason = ""


def gate_yes(action, detail, prompt=""):
    gate_yes.seen.append((action, dict(detail or {}), prompt))
    return _Verdict(True)


def gate_no(action, detail, prompt=""):
    gate_no.seen.append((action, dict(detail or {}), prompt))
    return _Verdict(False, "denied")


gate_yes.seen = []
gate_no.seen = []


def clean():
    """A fresh scratch home and a service this PC can really use."""
    import shutil
    for child in SCRATCH.iterdir():
        if child.is_file():
            child.unlink()
        else:
            shutil.rmtree(child, ignore_errors=True)
    API._reset_models_for_tests()
    STORE.clear()
    STORE[API.KEY_TARGETS["deepseek_api"]] = KEY
    _point_money()


def _point_money():
    """A limit and a price for DeepSeek, written where the module reads them."""
    doc = {"limits": {}, "spent": {}, "prices": {}}
    for pid, got in MONEY.items():
        doc["limits"][pid] = got["limit"]
        doc["spent"][pid] = got["spent"]
    path = SCRATCH / "chatbot" / "api-money.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


# ---- the store and the gate are stood in, BEFORE anything reads them -------

def _fake_read_key(pid):
    return STORE.get(API.KEY_TARGETS.get(pid, ""), "")


def _fake_key_saved(pid):
    return bool(_fake_read_key(pid))


def _fake_ready_for(pid):
    """The module's own money rule, on the stood-in store."""
    if not _fake_key_saved(pid):
        return API.no_key_words(API.PRESETS[pid])
    why, _cap = API.money_check(pid, API.model_for(pid)[0])
    return why


API._read_key = _fake_read_key
API.key_saved = _fake_key_saved
API.ready_for = _fake_ready_for


# ==========================================================================
#  1. the row itself
# ==========================================================================

def t_the_cloud_row_is_a_sixth_row_and_not_one_of_the_five():
    clean()
    row = P.cloud_preset_view()
    check("the Cloud row has the SAME keys a Preset.view() has",
          set(row) == set(P.PRESETS[0].view()), (sorted(set(row)), sorted(set(P.PRESETS[0].view()))))
    check("... and its id is 'cloud', which is NOT one of the five",
          row["id"] == "cloud" and "cloud" not in P.PRESET_IDS, P.PRESET_IDS)
    check("... so both apps' five-row list is still exactly five rows",
          len(P.PRESET_IDS) == 5 and [p["id"] for p in P.view()["presets"]] == list(P.PRESET_IDS),
          P.PRESET_IDS)
    check("its apply block says it is a cloud row that needs a provider, and "
          "starts no lane and switches no model",
          row["apply"]["cloud"] is True and row["apply"]["needs_provider"] is True
          and row["apply"]["lane_start"] is False and row["apply"]["auto"] is False,
          row["apply"])
    check("... and it promises no model of its own",
          row["model"] == "" and row["context"] == 0 and row["measured"] is None,
          (row["model"], row["context"]))


def t_live_status_gains_two_keys_and_moves_nothing_else():
    clean()
    st = P.live_status()
    for key in ("cloud_preset", "cloud"):
        check(f"/api/presets carries `{key}`", key in st, sorted(st))
    check("the five presets are untouched by it, in the same order",
          [p["id"] for p in st["presets"]] == list(P.PRESET_IDS), st["presets"][:1])
    check("... and the rest of the answer still has every key it had",
          {"found", "presets", "old_ids_replaced", "hardware", "recommendations",
           "chosen", "chosen_preset", "chosen_model", "active_lane", "lane",
           "lane_status", "apply_path", "switch_path", "auto"} <= set(st), sorted(st))


# ==========================================================================
#  2. the providers - and no key, ever
# ==========================================================================

def t_the_providers_are_one_row_per_service_and_never_a_key():
    clean()
    cloud = P.cloud_view()
    rows = cloud["providers"]
    check("one row per connected service, in PRESETS' own order",
          [r["id"] for r in rows] == list(API.PRESETS), [r["id"] for r in rows])
    check("no service is chosen yet, so `provider` is empty and no row is chosen",
          cloud["provider"] == "" and not any(r["chosen"] for r in rows), cloud["provider"])
    check("a row carries the service's name, company, host and model",
          all(r["name"] and r["company"] and r["host"] and r["model"] for r in rows),
          rows[0])
    check("the key is only ever SAID to be saved - true here for DeepSeek, and the "
          "key itself is nowhere in the answer",
          any(r["id"] == "deepseek_api" and r["key_saved"] is True for r in rows)
          and KEY not in json.dumps(cloud), cloud)
    check("... and neither is any fragment of it",
          not any(KEY[:6] in json.dumps(cloud) or KEY[6:] in json.dumps(cloud) for _ in (0,)),
          "the answer carries a piece of the key")
    check("a service with no key says so, with the PC's own sentence",
          any(r["id"] == "openai_api" and r["key_saved"] is False and r["why"]
              and "key" in r["why"].lower() for r in rows),
          [r for r in rows if r["id"] == "openai_api"])
    check("every row carries the ONE honest connect action - the command line to run "
          "on this PC - and where to make the key",
          all(r["key_line"].startswith("py -3 jarvis_chatbot_api.py key ")
              and r["key_where"].startswith("https://") for r in rows), rows[0])


def t_one_source_of_truth_for_whether_a_service_can_be_used():
    clean()
    cloud = {r["id"]: r for r in P.cloud_view()["providers"]}
    status = {r["pid"]: r for r in API.lane_status()["lanes"]}
    check("cloud_view() and lane_status() agree about `ready` for every service",
          all(cloud[pid]["ready"] == status[pid]["ready"] for pid in status),
          {pid: (cloud[pid]["ready"], status[pid]["ready"]) for pid in status})
    check("... and they give the same sentence for why one cannot be used",
          all((cloud[pid]["why"] or "") == (status[pid]["why"] or "") for pid in status),
          {pid: (cloud[pid]["why"], status[pid]["why"]) for pid in status})
    check("the money line both apps already show is on the row too",
          cloud["deepseek_api"]["money"]
          and cloud["deepseek_api"]["money"]["company"] == "DeepSeek",
          cloud["deepseek_api"]["money"])


# ==========================================================================
#  3. the apply - refusals BEFORE any card
# ==========================================================================

def t_cloud_apply_refuses_before_it_asks_anything():
    clean()
    gate_yes.seen.clear()
    code, out = P.apply_preset("cloud", cloud_gate=gate_yes)
    check("no provider named: 400, and the sentence lists the six services",
          code == 400 and out["changed"] is False
          and all(pid in out["error"] for pid in API.PRESETS), out)
    check("... and no card was raised for it", gate_yes.seen == [], gate_yes.seen)
    code, out = P.apply_preset("cloud", provider="nope_api", cloud_gate=gate_yes)
    check("a provider this PC does not know: 400 naming the six, no card",
          code == 400 and "nope_api" in out["error"] and gate_yes.seen == [], out)
    code, out = P.apply_preset("cloud", provider="openai_api", cloud_gate=gate_yes)
    check("a service with no key saved: 409 with the PC's own words, BEFORE a card",
          code == 409 and out["changed"] is False and out["error"]
          and gate_yes.seen == [], (code, out))
    check("... and nothing was written for any of the three refusals",
          not (SCRATCH / P.CLOUD_CHOICE_FILE).exists()
          and not (SCRATCH / P.CHOICE_FILE).exists(),
          sorted(p.name for p in SCRATCH.iterdir()))


# ==========================================================================
#  4. the apply - the card, and what is written only after it
# ==========================================================================

def t_a_refused_card_writes_nothing():
    clean()
    gate_no.seen.clear()
    code, out = P.apply_preset("cloud", provider="deepseek_api", cloud_gate=gate_no)
    check("the gate was asked ONCE, as change_own_config, with the provider's words",
          len(gate_no.seen) == 1 and gate_no.seen[0][0] == P.CLOUD_ACTION
          and "DeepSeek" in gate_no.seen[0][1]["text"]
          and "api.deepseek.com" in gate_no.seen[0][1]["text"], gate_no.seen)
    check("a NO changes nothing: 200, ok false, changed false",
          code == 200 and out["ok"] is False and out["changed"] is False, out)
    check("... and neither settings file was written",
          not (SCRATCH / P.CLOUD_CHOICE_FILE).exists()
          and not (SCRATCH / P.CHOICE_FILE).exists(),
          sorted(p.name for p in SCRATCH.iterdir()))
    check("... and no provider is in use", P.cloud_chosen() == "", P.cloud_chosen())


def t_an_approved_card_saves_the_choice_and_marks_it():
    clean()
    gate_yes.seen.clear()
    code, out = P.apply_preset("cloud", provider="deepseek_api", cloud_gate=gate_yes)
    check("a yes writes the choice: 200, ok true, changed true",
          code == 200 and out["ok"] is True and out["changed"] is True, out)
    check("cloud-choice.json names the service",
          json.loads((SCRATCH / P.CLOUD_CHOICE_FILE).read_text(encoding="utf-8"))
          == {"provider": "deepseek_api"},
          (SCRATCH / P.CLOUD_CHOICE_FILE).read_text(encoding="utf-8"))
    check("presets-choice.json says the preset is 'cloud'",
          json.loads((SCRATCH / P.CHOICE_FILE).read_text(encoding="utf-8"))["preset"]
          == "cloud", (SCRATCH / P.CHOICE_FILE).read_text(encoding="utf-8"))
    fresh = P.cloud_view()
    check("a refetch says which provider is in use, and marks exactly that row",
          fresh["provider"] == "deepseek_api"
          and [r["id"] for r in fresh["providers"] if r["chosen"]] == ["deepseek_api"],
          fresh["provider"])
    check("... and cloud_lanes() is the ONE lane",
          P.cloud_lanes() == ["jarvis-escalate"], P.cloud_lanes())


def t_a_cloud_apply_starts_no_lane_and_switches_no_model():
    """THE BITE. A cloud preset changes nothing local, so neither spy may fire.

    A cloud apply that called `start_lane` would try to start a GPU lane for a
    service that answers over HTTPS - and on the owner's PC that unloads the
    model he is using. This is the check that keeps a future edit from
    "reusing" the local path.
    """
    clean()
    calls = []

    def start_lane(key):
        calls.append(("start_lane", key))
        return 200, {"ok": True}

    def switch_model(ref):
        calls.append(("switch_model", ref))
        return {"ok": True}

    def set_active_url(url):
        calls.append(("set_active_url", url))
        return True

    code, out = P.apply_preset("cloud", provider="deepseek_api", cloud_gate=gate_yes,
                              start_lane=start_lane, switch_model=switch_model,
                              set_active_url=set_active_url,
                              rollback_model=lambda: calls.append(("rollback", "")))
    check("the cloud preset applied", code == 200 and out["changed"] is True, out)
    check("... and it started NO lane", not [c for c in calls if c[0] == "start_lane"], calls)
    check("... switched NO model", not [c for c in calls if c[0] == "switch_model"], calls)
    check("... re-pointed no chat lane", not [c for c in calls if c[0] == "set_active_url"], calls)
    check("... and rolled nothing back", not [c for c in calls if c[0] == "rollback"], calls)


def t_apply_from_body_passes_the_provider_and_ignores_it_elsewhere():
    """The route's own entry point, not just apply_preset().

    `apply_from_body` is what `POST /api/work/apply` calls, and it deliberately
    takes no gate argument - it uses the module's own, which is the real
    jarvis_gate. So the module's `_gate` is stood in for the one call here and
    put back afterwards: that keeps this the SAME road the route takes while
    still never posting a card.
    """
    clean()
    gate_yes.seen.clear()
    real_gate = P._gate
    P._gate = gate_yes
    try:
        code, out = P.apply_from_body({"preset": "cloud", "provider": "deepseek_api"})
        check("POST /api/work/apply carries `provider` through to the cloud apply",
              code == 200 and out.get("changed") is True
              and out.get("provider") == "deepseek_api", (code, out))
        check("... and it raised exactly ONE change_own_config card on the way",
              len(gate_yes.seen) == 1 and gate_yes.seen[0][0] == P.CLOUD_ACTION,
              gate_yes.seen)
        code, out = P.apply_from_body({"preset": "fast", "provider": "deepseek_api"})
        check("a local preset's body is untouched by `provider` - it refuses for its "
              "own local reason (this machine has no such lane/model), and raises no "
              "card of its own",
              out.get("changed") is False
              and "provider" not in json.dumps(out)
              and len(gate_yes.seen) == 1, (code, out))
    finally:
        P._gate = real_gate
    code, out = P.apply_from_body({"preset": "cloud", "provider": 7})
    check("a non-text provider is a 400 rather than a crash", code == 400, (code, out))


# ==========================================================================
#  5. the lane list - one, or none
# ==========================================================================

def t_the_lane_list_is_one_or_none():
    clean()
    check("nothing chosen: no cloud lane at all (gate unavailable, not a substitute)",
          P.cloud_lanes() == [], P.cloud_lanes())
    P.apply_preset("cloud", provider="deepseek_api", cloud_gate=gate_yes)
    check("a provider chosen: exactly the ONE lane",
          P.cloud_lanes() == ["jarvis-escalate"], P.cloud_lanes())
    (SCRATCH / P.CLOUD_CHOICE_FILE).write_text("{not json", encoding="utf-8")
    check("a corrupt choice file reads as no provider, and so as no lane",
          P.cloud_chosen() == "" and P.cloud_lanes() == [], P.cloud_chosen())
    (SCRATCH / P.CLOUD_CHOICE_FILE).write_text(
        json.dumps({"provider": "gone_api"}) + "\n", encoding="utf-8")
    check("a provider this PC does not know is not a lane either",
          P.cloud_lanes() == [], P.cloud_lanes())


# ==========================================================================

TESTS = [
    t_the_cloud_row_is_a_sixth_row_and_not_one_of_the_five,
    t_live_status_gains_two_keys_and_moves_nothing_else,
    t_the_providers_are_one_row_per_service_and_never_a_key,
    t_one_source_of_truth_for_whether_a_service_can_be_used,
    t_cloud_apply_refuses_before_it_asks_anything,
    t_a_refused_card_writes_nothing,
    t_an_approved_card_saves_the_choice_and_marks_it,
    t_a_cloud_apply_starts_no_lane_and_switches_no_model,
    t_apply_from_body_passes_the_provider_and_ignores_it_elsewhere,
    t_the_lane_list_is_one_or_none,
]


def main() -> int:
    for fn in TESTS:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            FAILED.append(f"{fn.__name__} raised")
            print(f"FAIL  {fn.__name__} raised")
            traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  failed: {name}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
