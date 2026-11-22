"""The preset that loads when Atlas itself starts (2026-11-22).

    py -3 backend/test_startup_preset.py

THE OWNER'S ASK, VERBATIM: *"load the general local ai model preset. and have
that be the default that loads anytime jarvis is reset. it should be a larger
local ai model in that preset compared to qwen 9b. let me set the default
presets that load when atlas is restarted through chat or settings"*. He then
chose EAGER PRELOAD - the preset loads as the program starts, accepting about a
minute and about 15 GiB of card memory - rather than lazily on the first
message. The preset table needed nothing: `general` already exists, it is
`gemma4:26b-a4b-it-qat` on the pooled three-card lane, and it is larger than the
everyday `qwen3.5:9b`.

WHAT THIS SUITE PINS, and each one is a way the feature could be wrong:

  1. the SETTING is `~/.openjarvis/startup-preset.json` (`{"preset": "<id>"}`),
     absent means none, an unreadable file or an id this PC does not know reads
     as none AND SAYS WHY - never a silent no-op;
  2. setting it raises exactly ONE `change_own_config` card and writes NOTHING
     before the owner's yes; already set is a no-op with no second card;
     clearing is instant and removes the file; an unknown id, the Cloud row and
     a malformed body are 400s with NO card;
  3. the route `POST /api/work/startup-preset` and the chat sentence reach the
     SAME function (`jarvis_presets.set_startup_preset`), so both raise the same
     one card and write the same file;
  4. the START-UP step applies a configured preset through the ROUTE'S OWN road
     (`_apply_body(..., owner_ui=True)` -> `apply_preset`), with the lane start
     and the model switch really called, the lane persisted and the chosen
     preset written - and it runs NO reconcile on success, so the choice it just
     served is never deleted;
  5. when the configured preset CANNOT load, today's reconcile still runs
     (chat back on the default lane, the unservable choice forgotten) and BOTH
     sentences are kept in `restart_reconcile` - the old behaviour, with a word
     about it;
  6. with NO start-up preset, the start-up step IS today's reconcile, exactly
     (the two dicts are equal and the lanes/files end in the same state), so
     every existing reconcile test keeps its meaning;
  7. a start-up preset never blocks the HUD's first request: `install()` starts
     ONE daemon thread and returns while a blocked 26B load is still blocked;
  8. the chat sentences of the owner's own words match, and the ordinary "use
     the General preset now" does NOT become a start-up setting;
  9. `/api/work` carries the small read-only `startup_preset` block.

WHAT IS REAL AND WHAT IS INJECTED. The real `jarvis_presets` module, the real
`jarvis_quick` matcher and the real route wrapper (`install()`) are driven. The
lane start, the model switch, the lane read-back and the model rollback are
INJECTED, because this checkout has no GPU and must never start the owner's
lanes; the approval gate is a stand-in, because a suite must never post a card.
Every file lives under this suite's own `OPENJARVIS_CONFIG_DIR`, so the owner's
~/.openjarvis is never read or written.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _base  # noqa: E402
#: `jarvis_models.py` is one of the owner's own files; the published base carries
#: it and `jarvis_presets._active_url()` asks it for the one Ollama address.
_base.put_on_path(_base.folder("jarvis_models.py"))

SCRATCH = Path(tempfile.mkdtemp(prefix="startup-preset-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_RECEIPTS_DB"] = str(SCRATCH / "receipts.db")
#: This file IS a suite run, the same marker `test_pooled_lane.py` and
#: `test_cloud_escalate_setting.py` set: a bare `py -3 backend/test_startup_
#: preset.py` must still prove the live-file guards.
os.environ["JARVIS_SUITE_RUNNING"] = "1"
#: Hermetic: the default lane every reconcile sentence names, never the owner's.
os.environ["OLLAMA_URL"] = "http://127.0.0.1:11436"

import jarvis_presets as P      # noqa: E402
import jarvis_quick as Q        # noqa: E402

FAILED, PASSED = [], []
DEFAULT_LANE = "http://127.0.0.1:11436"
POOLED_LANE = "http://127.0.0.1:11450"


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok   " if cond else "FAIL ") + name
          + (f"\n        {detail}" if detail and not cond else ""))


class Verdict:
    def __init__(self, allowed=True, outcome=""):
        self.allowed = bool(allowed)
        self.outcome = outcome or ("approved" if allowed else "denied")
        self.reason = ""


class Gate:
    """A stand-in for jarvis_gate.check that records every question asked."""

    def __init__(self, allowed=True):
        self.calls = []
        self.allowed = allowed

    def __call__(self, action, detail=None, prompt="", **_kw):
        self.calls.append((action, dict(detail or {}), prompt))
        return Verdict(self.allowed)


def clean():
    """No start-up setting, no choice, no lane - each test starts here."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    for name in (P.STARTUP_FILE, P.CHOICE_FILE, P.LANE_FILE_NAME):
        try:
            (SCRATCH / name).unlink()
        except FileNotFoundError:
            pass


def _startup_file():
    return SCRATCH / P.STARTUP_FILE


def _write_startup(preset_id, raw=None):
    _startup_file().write_text(
        raw if raw is not None else json.dumps({"preset": preset_id}),
        encoding="utf-8")


def _dead_pooled_state():
    """The restart state the reconcile exists for: pooled lane gone, choice kept."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (SCRATCH / P.LANE_FILE_NAME).write_text(
        json.dumps({"base_url": POOLED_LANE}), encoding="utf-8")
    (SCRATCH / P.CHOICE_FILE).write_text(
        json.dumps({"preset": "general"}), encoding="utf-8")


# ==========================================================================
#  1. the setting: absent, valid, and honestly unusable
# ==========================================================================

def t_the_setting_is_the_named_file_and_reads_honestly():
    check("the setting is startup-preset.json under the config folder",
          P.STARTUP_FILE == "startup-preset.json"
          and P._startup_path().name == "startup-preset.json"
          and P._startup_path().parent == SCRATCH,
          (P.STARTUP_FILE, P._startup_path()))
    check("its route is the one the task named",
          P.STARTUP_PATH == "/api/work/startup-preset", P.STARTUP_PATH)
    check("it reuses change_own_config, so no new gate row is owed",
          P.STARTUP_ACTION == P.CLOUD_ACTION == "change_own_config",
          (P.STARTUP_ACTION, P.CLOUD_ACTION))
    clean()
    check("absent reads as none, with nothing to explain",
          P.startup_view() == {"preset": "", "why": ""}, P.startup_view())
    _write_startup("general")
    check("a saved, known preset reads back by id",
          P.startup_view() == {"preset": "general", "why": ""}, P.startup_view())
    _write_startup("nope")
    view = P.startup_view()
    check("an id this PC does not know is NONE, and the why names it",
          view.get("preset") == "" and "no preset called 'nope'" in view.get("why", ""),
          view)
    _write_startup("", raw="{not json")
    view = P.startup_view()
    check("a corrupt file is none and says so, never an exception",
          view.get("preset") == "" and "not readable JSON" in view.get("why", ""),
          view)
    _write_startup("", raw='["general"]')
    view = P.startup_view()
    check("a wrong-shaped file is none and says so",
          view.get("preset") == "" and "does not hold a setting" in view.get("why", ""),
          view)
    clean()


# ==========================================================================
#  2. setting it: ONE card, nothing written before the yes
# ==========================================================================

def t_setting_raises_one_card_and_writes_nothing_before_the_yes():
    clean()
    denied = Gate(allowed=False)
    code, body = P.set_startup_preset(preset="general", gate_check=denied)
    check("a refused card answers 200 with the refusal, and says a card was raised",
          code == 200 and body.get("ok") is False
          and body.get("changed") is False and body.get("card") is True
          and body.get("outcome") == "denied", (code, body))
    check("... exactly ONE card, the change_own_config one",
          len(denied.calls) == 1
          and denied.calls[0][0] == "change_own_config", denied.calls)
    check("... and NOTHING was written before the yes",
          not _startup_file().exists() and P.startup_view()["preset"] == "",
          P.startup_view())
    check("... and it never claims the setting moved",
          "Not changed" in str(body.get("message") or ""), body.get("message"))
    yes = Gate()
    code, body = P.set_startup_preset(preset="general", gate_check=yes)
    check("an approved card writes the file and answers changed",
          code == 200 and body.get("ok") is True and body.get("changed") is True
          and body.get("card") is True, (code, body))
    check("... the file is the exact shape {\"preset\": \"<id>\"}",
          json.loads(_startup_file().read_text(encoding="utf-8"))
          == {"preset": "general"}, _startup_file().read_text(encoding="utf-8"))
    words = yes.calls[0][1].get("text") or ""
    check("the card says what happens at the NEXT start, in plain words",
          "every time Atlas starts" in words and "Nothing on this PC changes"
          in words, words)
    check("... and repeats the preset row's own measured cost rather than a guess",
          "11450" in words and "50 seconds" in words, words)
    check("... and the prompt is the short form of the same question",
          "load the General preset every time Atlas starts" in yes.calls[0][2],
          yes.calls[0][2])
    check("the success sentence names the next start too",
          "every time it starts" in str(body.get("message") or ""),
          body.get("message"))
    again = Gate()
    code, body = P.set_startup_preset(preset="general", gate_check=again)
    check("already set is a no-op with NO second card",
          code == 200 and body.get("changed") is False and again.calls == []
          and "already the preset" in str(body.get("message") or ""),
          (code, body, again.calls))
    clean()


def t_clearing_is_instant_and_removes_the_file():
    clean()
    _write_startup("general")

    class NoCards:
        def __call__(self, *_a, **_k):
            raise AssertionError("clearing raised a card for a tightening")

    code, body = P.set_startup_preset(preset="", gate_check=NoCards())
    check("clearing raises no card and removes the setting",
          code == 200 and body.get("ok") is True and body.get("changed") is True
          and body.get("card") is False and not _startup_file().exists(),
          (code, body))
    check("... and says what the next start will do",
          "No preset will be loaded" in str(body.get("message") or ""),
          body.get("message"))
    code, body = P.set_startup_preset(preset="", gate_check=NoCards())
    check("clearing again is a no-op that still asks nothing",
          code == 200 and body.get("changed") is False and body.get("card") is False,
          (code, body))
    _write_startup("general")
    code, body = P.startup_from_body({"clear": True})
    check("{\"clear\": true} is the same clear",
          code == 200 and not _startup_file().exists(), (code, body))
    _write_startup("general")
    code, body = P.startup_from_body({"preset": ""})
    check('{"preset": ""} is the same clear', code == 200 and not _startup_file().exists(),
          (code, body))
    clean()


def t_an_unknown_id_and_a_bad_body_are_400s_with_no_card():
    clean()
    gate = Gate()
    for label, body_in, expect in (
            ("an id this PC does not have", {"preset": "nonsense"},
             "no preset called"),
            ("the Cloud row", {"preset": "cloud"}, "not a local preset"),
            ("a non-text preset", {"preset": 3}, "must be text"),
            ("a body with no preset", {}, "expected"),
            ("a non-boolean clear", {"clear": "yes"}, "must be true or false"),
    ):
        code, body = P.startup_from_body(body_in)
        check(f"{label} is a 400 with a plain sentence",
              code == 400 and expect in str(body.get("error") or "")
              and not body.get("card"), (code, body))
    check("... and not one of them raised a card or wrote a file",
          gate.calls == [] and not _startup_file().exists(), gate.calls)
    code, body = P.startup_from_body(["general"])
    check("a body that is not an object is a 400 too",
          code == 400 and "JSON object" in str(body.get("error") or ""), (code, body))
    clean()


# ==========================================================================
#  3. one door: the route and the chat sentence reach the same function
# ==========================================================================

class Handler:
    """The HUD Handler's shape, with _send recording what the route answered."""
    do_GET = lambda self: None          # noqa: E731 - attribute, not a method
    do_POST = lambda self: None         # noqa: E731

    def __init__(self, path, body):
        self.path = path
        self._body = body
        self.sent = None

    def _send(self, code, out):
        self.sent = (code, out)


def _install_route_only():
    """install() wired with no start-up work, so the route is the only surface."""
    real = (P._warm_on_startup, P._refresh_detect_cache_async)
    P._warm_on_startup = lambda: False
    P._refresh_detect_cache_async = lambda: None
    try:
        line = P.install(Handler, origin_ok=lambda s: True,
                         token_ok=lambda s: True,
                         read_body=lambda s: json.dumps(s._body).encode())
    finally:
        P._warm_on_startup, P._refresh_detect_cache_async = real
    return line


def _post(path, body):
    h = Handler(path, body)
    h.do_POST()
    return h.sent


def t_the_route_sets_and_clears_through_the_one_door():
    clean()
    line = _install_route_only()
    check("install() still answers its banner line", line == "presets    ready", line)
    gate = Gate()
    real_gate = P._gate
    P._gate = gate
    try:
        code, body = _post(P.STARTUP_PATH, {"preset": "general"})
        check("POST /api/work/startup-preset sets it after ONE card",
              code == 200 and body.get("changed") is True
              and len(gate.calls) == 1 and _startup_file().exists(), (code, body))
        code, body = _post(P.STARTUP_PATH, {"clear": True})
        check("... and the same route clears it with no card",
              code == 200 and not _startup_file().exists()
              and len(gate.calls) == 1, (code, body, gate.calls))
        code, body = _post(P.STARTUP_PATH, {"preset": "nope"})
        check("... and refuses an unknown id without a card",
              code == 400 and len(gate.calls) == 1, (code, body))
        # THE SAME FUNCTION IS THE DOOR: both surfaces call it, by name.
        real = P.set_startup_preset
        seen = []
        P.set_startup_preset = lambda **kw: (seen.append(dict(kw))
                                             or (200, {"ok": True, "changed": True,
                                                       "card": True}))
        try:
            _post(P.STARTUP_PATH, {"preset": "coding"})
            P.startup_from_body({"preset": "coding"})
        finally:
            P.set_startup_preset = real
        check("the route and startup_from_body call the one function, with the id",
              seen == [{"preset": "coding"}, {"preset": "coding"}], seen)
    finally:
        P._gate = real_gate
        clean()


# ==========================================================================
#  4. the start-up step: the route's own road, and no reconcile on success
# ==========================================================================

def _spy_apply(calls, result=None):
    """`apply_preset` with the lane, the switch and the read-back injected.

    The real function is still the one that decides everything - the order, the
    owner_ui road, the writes - exactly what the route runs. Only the four
    hardware-facing seams are stand-ins, so no lane is started and no model is
    loaded.
    """
    real = P.apply_preset

    def fake_start(key, mode="", keep_alive=None):
        calls["start"].append((key, mode, keep_alive))
        return 200, {"ok": True, "changed": True}

    def fake_switch(ref):
        calls["switch"].append(ref)
        return {"ok": True, "ref": ref}

    def fake_set_lane(url):
        calls["lane"].append(url)
        return bool(P._set_active_url(url))

    def fake_verify(url, model, ctx=None, allow_spill=0):
        calls["verify"].append((url, model, ctx, allow_spill))
        return {"ok": True, "checked": True}

    def spy(pid, **kw):
        calls["apply"].append((pid, kw.get("owner_ui"), kw.get("provider"),
                               kw.get("keep_alive")))
        if result is not None:
            return result
        return real(pid, start_lane=fake_start, switch_model=fake_switch,
                    set_active_url=fake_set_lane, verify_lane=fake_verify,
                    stop_pooled=lambda: {"ok": True, "ran": False, "reason": ""},
                    **kw)

    return spy


def t_the_startup_apply_loads_the_preset_through_the_routes_road():
    clean()
    _write_startup("general")
    calls = {"start": [], "switch": [], "lane": [], "verify": [], "apply": []}
    real = P.apply_preset
    P.apply_preset = _spy_apply(calls)
    try:
        got = P.apply_startup_preset(
            reconcile=lambda: (_ for _ in ()).throw(
                AssertionError("the reconcile ran after a successful apply")))
    finally:
        P.apply_preset = real
    check("the start-up step applies through the route's own road, with no card",
          calls["apply"] == [("general", True, None, -1)], calls["apply"])
    check("... it really STARTS the preset's pooled lane, in its own mode",
          calls["start"] == [("pooled", "gemma4-26b-a4b", -1)], calls["start"])
    check("... and the start asks the lane to KEEP the model resident (-1), so "
          "Ollama's idle timer cannot throw an eager preload away",
          calls["start"] and calls["start"][0][2] == P.STARTUP_KEEP_ALIVE == -1,
          (calls["start"], P.STARTUP_KEEP_ALIVE))
    check("... it really SWITCHES the model to the preset's own",
          calls["switch"] == ["gemma4:26b-a4b-it-qat"], calls["switch"])
    check("... it reads the lane back before claiming anything",
          len(calls["verify"]) == 1
          and calls["verify"][0][1] == "gemma4:26b-a4b-it-qat"
          and calls["verify"][0][2] == 32768, calls["verify"])
    check("... it PERSISTS the lane chat now uses (the pooled one)",
          calls["lane"] == [POOLED_LANE]
          and P._persisted_lane_url() == POOLED_LANE,
          (calls["lane"], P._persisted_lane_url()))
    check("... and it saves the chosen preset, so both apps agree",
          P.choice() == "general", P.choice())
    check("the record says the preset loaded, names the lane, and says it is "
          "held resident",
          isinstance(got, dict) and got.get("changed") is True
          and got.get("startup_applied") is True
          and got.get("preset") == "general"
          and got.get("lane") == POOLED_LANE
          and got.get("keep_alive") == -1 and got.get("held_resident") is True
          and "loaded the General preset at start" in str(got.get("why") or "")
          and "stays resident" in str(got.get("why") or ""), got)
    check("... and NOTHING calls the reconcile that would forget the choice",
          P.choice() == "general", P.choice())
    clean()


# ==========================================================================
#  4b. keep-alive: the eager load outlives Ollama's idle timer, but never
#      the owner's rest hours
# ==========================================================================

def t_the_keep_alive_reaches_the_lanes_one_loader():
    """`-1` is Ollama's own "stay resident", and it travels the EXISTING loader.

    MEASURED 2026-11-22: the General model was applied at 02:41 and Ollama's
    default idle timer had unloaded it by 10:30 (`/api/ps` on 11450 empty while
    `/api/work` said `chosen: "general"`). The ask is one field on the lane's own
    load request - no second loader, no second load.
    """
    import jarvis_big_coder as BC
    seen = {}
    real_post = BC._post_json

    def fake_post(url, path, body, timeout):
        seen.update(url=url, path=path, body=body, timeout=timeout)
        return {}

    BC._post_json = fake_post
    try:
        ok = BC.load(POOLED_LANE, "gemma4:26b-a4b-it-qat", 32768, keep_alive=-1)
    finally:
        BC._post_json = real_post
    check("the lane's own load POST carries keep_alive -1",
          ok is True and seen.get("path") == "/api/generate"
          and seen.get("body", {}).get("keep_alive") == -1
          and seen.get("body", {}).get("options") == {"num_ctx": 32768},
          (ok, seen))
    # Every other caller sends exactly what it sent before: no field at all.
    seen.clear()
    BC._post_json = fake_post
    try:
        BC.load(POOLED_LANE, "gemma4:26b-a4b-it-qat", 32768)
    finally:
        BC._post_json = real_post
    check("... and a load that was not asked for residency sends no keep_alive",
          "keep_alive" not in seen.get("body", {}), seen.get("body"))
    # load_coder FORWARDS it, so the start's own load is the one that asks.
    real_load = BC.load
    forwarded = {}

    def fake_load(url, model, num_ctx, keep_alive=None):
        forwarded.update(url=url, model=model, num_ctx=num_ctx,
                         keep_alive=keep_alive)
        return True

    real_settle = BC._settle
    real_cards = BC.cards_in_pc
    BC.load = fake_load
    BC._settle = lambda url, model, gone=False, **_kw: [
        {"name": model, "context_length": 32768, "size": 15_000,
         "size_vram": 15_000}]
    BC.cards_in_pc = lambda: None
    try:
        got = BC.load_coder(port=11450, num_ctx=32768, allow_spill=0,
                            mode="gemma4-26b-a4b", keep_alive=-1)
    finally:
        BC.load = real_load
        BC._settle = real_settle
        BC.cards_in_pc = real_cards
    check("load_coder hands keep_alive to load, so the start-up load is the one "
          "that asks",
          got.get("ok") is True and forwarded.get("keep_alive") == -1
          and forwarded.get("num_ctx") == 32768, (got, forwarded))


def _power_stub(drop):
    """`jarvis_power` with `schedule_drop` answering `drop` (or raising)."""
    import jarvis_power as PW
    real = PW.schedule_drop

    def fake(now=None):
        if isinstance(drop, Exception):
            raise drop
        return drop
    PW.schedule_drop = fake
    return PW, real


def t_rest_hours_are_respected_and_no_energy_rest_setting_is_invented():
    """A rest window is the OWNER's own "let the cards go"; a keep-alive that
    ignored it would hold 15 GiB through the hours he set aside.

    The setting the product really has is `[power]`'s scheduled window
    (`schedule_enabled`, `quiet_start`, `quiet_end`), read by
    `jarvis_power.schedule_drop()` - the same reader the power rules use. There
    is NO `[energy]` rest-hours setting: that section is the measured-watts
    record, so nothing here invents one.
    """
    for drop, label in (("standby", "the cards are asked to unload"),
                        ("quiet", "the quiet window is on")):
        PW, real = _power_stub(drop)
        try:
            keep, why = P._startup_keep_alive()
        finally:
            PW.schedule_drop = real
        check(f"during rest hours ({label}) the model is NOT held resident",
              keep is None and drop in why, (keep, why))
    PW, real = _power_stub(None)
    try:
        keep, why = P._startup_keep_alive()
    finally:
        PW.schedule_drop = real
    check("outside them the start-up load asks to stay resident",
          keep == -1 and why == "", (keep, why))
    PW, real = _power_stub(RuntimeError("the clock could not be read"))
    try:
        keep, why = P._startup_keep_alive()
    finally:
        PW.schedule_drop = real
    check("rest hours that cannot be read are not ignored: no hold, and the "
          "reason says so",
          keep is None and "could not be read" in why, (keep, why))


def t_a_rest_window_changes_the_load_the_startup_apply_asks_for():
    clean()
    _write_startup("general")
    calls = {"start": [], "switch": [], "lane": [], "verify": [], "apply": []}
    real = P.apply_preset
    P.apply_preset = _spy_apply(calls)
    PW, real_drop = _power_stub("standby")
    try:
        got = P.apply_startup_preset(
            reconcile=lambda: (_ for _ in ()).throw(
                AssertionError("the reconcile ran after a successful apply")))
    finally:
        P.apply_preset = real
        PW.schedule_drop = real_drop
    check("with rest hours on, the same road is taken but the load asks for no "
          "hold",
          calls["start"] == [("pooled", "gemma4-26b-a4b", None)]
          and got.get("keep_alive") is None
          and got.get("held_resident") is False
          and "rest hours are on now" in str(got.get("why") or ""), (calls, got))
    clean()


def t_switching_preset_still_replaces_the_model_no_second_copy():
    """The keep-alive is bounded by the one-preset-at-a-time rule (2026-11-18).

    A preset that is not heavy ENDS the pooled lane before it touches anything -
    that is what unloads the model held with keep_alive -1 - so a later switch
    can never leave two models resident.
    """
    clean()
    orders = []
    stopped = {"n": 0}

    def stop_pooled():
        stopped["n"] += 1
        orders.append("stop")
        return {"ok": True, "ran": True, "reason": ""}

    def start_lane(key, mode="", keep_alive=None):
        orders.append(("start", keep_alive))
        return 200, {"ok": True, "changed": False}

    def verify(url, model, ctx=None, allow_spill=0):
        return {"ok": True, "checked": True}

    code, out = P.apply_preset(
        "fast", owner_ui=True, stop_pooled=stop_pooled, start_lane=start_lane,
        switch_model=lambda ref: {"ok": True, "ref": ref},
        set_active_url=lambda url: True, verify_lane=verify)
    check("applying another preset ends the held lane FIRST",
          stopped["n"] == 1 and orders and orders[0] == "stop",
          (stopped, orders))
    check("... and the new preset's own start asks for NO keep-alive, so only "
          "the start-up one holds",
          orders == ["stop", ("start", None)], orders)
    check("... and the switch itself answers ok, so the model really changed",
          code == 200 and out.get("ok") is True, (code, out))
    clean()

def t_a_failed_startup_apply_falls_back_and_records_why():
    """FAIL-BEFORE: `apply_startup_preset` did not exist, so a start-up preset
    that could not load left the old reconcile's silent "preset forgotten" with
    no word about the setting that caused it."""
    clean()
    _write_startup("general")
    _dead_pooled_state()
    error = ("the pooled lane did not start: no card was free; nothing was "
             "changed")
    lane_calls, rolled = [], []

    def reconcile():
        return P.reconcile_after_restart(
            probe=lambda url: False,
            set_active_url=lambda url: (lane_calls.append(url)
                                        or bool(P._set_active_url(url))),
            rollback_model=lambda: (rolled.append(1) or {"ok": True}))

    got = P.apply_startup_preset(
        apply=lambda pid: (503, {"ok": False, "changed": False, "error": error}),
        reconcile=reconcile)
    check("a start-up preset that cannot load still repairs the lane, as today",
          lane_calls == [DEFAULT_LANE]
          and P._persisted_lane_url() == DEFAULT_LANE
          and rolled == [1], (lane_calls, P._persisted_lane_url(), rolled))
    check("... and the unservable choice is forgotten, exactly as today",
          not (SCRATCH / P.CHOICE_FILE).exists(),
          (SCRATCH / P.CHOICE_FILE).exists())
    check("the recorded outcome keeps the four keys the contract names",
          isinstance(got, dict)
          and {"changed", "why", "lane", "preset"} <= set(got), sorted(got or {}))
    check("... and the why names the FAILED start-up apply, in words",
          "could not be loaded" in str(got.get("why") or "")
          and "no card was free" in str(got.get("why") or ""), got.get("why"))
    check("... and it still says what today's reconcile did",
          "does not survive a restart" in str(got.get("why") or "")
          and "Apply the preset again" in str(got.get("why") or ""), got.get("why"))
    check("... the failed preset is named, and the remembered one is kept apart",
          got.get("preset") == "general"
          and got.get("startup_preset") == "general"
          and got.get("startup_applied") is False
          and got.get("remembered_preset") == "general",
          (got.get("preset"), got.get("startup_preset"),
           got.get("remembered_preset")))
    check("... and it is changed, because the lane really moved back",
          got.get("changed") is True and got.get("lane") == DEFAULT_LANE,
          (got.get("changed"), got.get("lane")))
    clean()


def t_an_apply_that_raises_is_said_and_the_fallback_still_runs():
    clean()
    _write_startup("general")
    _dead_pooled_state()

    def boom(_pid):
        raise RuntimeError("the lane module is not on this PC")

    got = P.apply_startup_preset(apply=boom,
                                 reconcile=lambda: P.reconcile_after_restart(
                                     probe=lambda u: False,
                                     set_active_url=lambda u: True,
                                     rollback_model=lambda: {"ok": True}))
    check("an apply that raises is a recorded failure, never a crash",
          isinstance(got, dict) and got.get("startup_applied") is False
          and "RuntimeError" in str(got.get("why") or ""), got)


# ==========================================================================
#  6. with no start-up preset, today's behaviour, exactly
# ==========================================================================

def t_with_no_startup_preset_the_step_is_todays_reconcile():
    clean()
    sentinel = {"changed": False, "why": "today, untouched", "lane": DEFAULT_LANE,
                "preset": "coding"}
    calls = []
    got = P.apply_startup_preset(
        apply=lambda pid: (_ for _ in ()).throw(
            AssertionError("an apply ran with no start-up preset")),
        reconcile=lambda: (calls.append(1) or dict(sentinel)))
    check("no start-up preset: the reconcile runs once and its dict is returned",
          calls == [1] and got == sentinel, (calls, got))
    # ... and with the REAL reconcile, the two answers and the end state agree.
    _dead_pooled_state()
    seam_calls = []
    from_startup = P.apply_startup_preset(
        reconcile=lambda: P.reconcile_after_restart(
            probe=lambda u: False,
            set_active_url=lambda u: (seam_calls.append(u)
                                      or bool(P._set_active_url(u))),
            rollback_model=lambda: {"ok": True}))
    _dead_pooled_state()
    direct_calls = []
    direct = P.reconcile_after_restart(
        probe=lambda u: False,
        set_active_url=lambda u: (direct_calls.append(u)
                                  or bool(P._set_active_url(u))),
        rollback_model=lambda: {"ok": True})
    check("... the answer IS the reconcile's own answer, key for key",
          from_startup == direct, (from_startup, direct))
    check("... and the state it leaves is the same state",
          seam_calls == direct_calls == [DEFAULT_LANE]
          and not (SCRATCH / P.CHOICE_FILE).exists()
          and P._persisted_lane_url() == DEFAULT_LANE,
          (seam_calls, direct_calls, P._persisted_lane_url()))
    clean()


# ==========================================================================
#  7. it must never block the HUD from serving
# ==========================================================================

def t_a_startup_load_never_blocks_the_hud():
    clean()
    _write_startup("general")
    real = (P._warm_on_startup, P._refresh_detect_cache_async,
            P._STARTUP_CHECK_STARTED, P.apply_startup_preset, P._LAST_RECONCILE)
    import threading
    started, release = threading.Event(), threading.Event()
    ran = []

    def slow_apply():
        ran.append(1)
        started.set()
        release.wait(10)
        return {"changed": True, "why": "loaded at start (stub)", "lane": POOLED_LANE,
                "preset": "general", "startup_applied": True}

    P._warm_on_startup = lambda: True
    P._refresh_detect_cache_async = lambda: None
    P._STARTUP_CHECK_STARTED = False
    P.apply_startup_preset = slow_apply
    P._LAST_RECONCILE = {"changed": False, "why": "not run yet"}
    try:
        line = P.install(Handler, origin_ok=lambda s: True,
                         token_ok=lambda s: True,
                         read_body=lambda s: b"{}")
        quick = started.wait(5)
        check("install() returns while the 26B load is still loading",
              line == "presets    ready" and quick
              and release.is_set() is False and ran == [1],
              (line, quick, release.is_set(), ran))
        check("... and the record is not claimed before the load finishes",
              P._LAST_RECONCILE.get("why") == "not run yet", P._LAST_RECONCILE)
        release.set()
        for _ in range(400):
            if P._LAST_RECONCILE.get("startup_applied") is True:
                break
            time.sleep(0.01)
        check("... and the outcome lands in restart_reconcile when it does",
              P._LAST_RECONCILE.get("startup_applied") is True
              and P._LAST_RECONCILE.get("preset") == "general",
              P._LAST_RECONCILE)
        line = P.install(Handler, origin_ok=lambda s: True,
                         token_ok=lambda s: True, read_body=lambda s: b"{}")
        time.sleep(0.05)
        check("... a second install() starts no second load",
              len(ran) == 1 and line == "presets    ready", (ran, line))
    finally:
        release.set()
        (P._warm_on_startup, P._refresh_detect_cache_async,
         P._STARTUP_CHECK_STARTED, P.apply_startup_preset,
         P._LAST_RECONCILE) = real
        clean()


def t_with_no_startup_preset_install_still_reconciles_synchronously():
    clean()
    real = (P._warm_on_startup, P._refresh_detect_cache_async,
            P._STARTUP_CHECK_STARTED, P.reconcile_after_restart, P._LAST_RECONCILE)
    calls = []
    P._warm_on_startup = lambda: True
    P._refresh_detect_cache_async = lambda: None
    P._STARTUP_CHECK_STARTED = False
    P.reconcile_after_restart = lambda **kw: (calls.append(1)
                                              or {"changed": True, "why": "fixed",
                                                  "lane": DEFAULT_LANE,
                                                  "preset": "coding"})
    P._LAST_RECONCILE = {"changed": False, "why": "not run yet"}
    try:
        P.install(Handler, origin_ok=lambda s: True, token_ok=lambda s: True,
                  read_body=lambda s: b"{}")
        check("no start-up preset: the reconcile runs ONCE, in install(), as always",
              calls == [1] and P._STARTUP_CHECK_STARTED is False, (calls,))
        check("... and its dict is the payload's, at once",
              P._LAST_RECONCILE.get("why") == "fixed", P._LAST_RECONCILE)
    finally:
        (P._warm_on_startup, P._refresh_detect_cache_async,
         P._STARTUP_CHECK_STARTED, P.reconcile_after_restart,
         P._LAST_RECONCILE) = real
        clean()


# ==========================================================================
#  8. the payload block
# ==========================================================================

def t_live_status_carries_the_small_read_only_block():
    clean()
    real = (P.hardware_block, P.recommendations, P.cloud_view)
    P.hardware_block = lambda: {"detected": {"cards": []}, "questionnaire": {}}
    P.recommendations = lambda: {"one": {}, "two": {}, "three": {}}
    P.cloud_view = lambda: {"provider": "", "providers": [],
                            "escalate": {"on": False, "why": ""}}
    try:
        body = P.live_status()
        check("with nothing set, the block is the empty honest one",
              body.get("startup_preset") == {"preset": "", "why": ""},
              body.get("startup_preset"))
        _write_startup("general")
        body = P.live_status()
        check("a saved start-up preset is reported in /api/work",
              body.get("startup_preset") == {"preset": "general", "why": ""},
              body.get("startup_preset"))
        _write_startup("nope")
        body = P.live_status()
        block = body.get("startup_preset") or {}
        check("... and an unusable setting is reported as none WITH the reason",
              block.get("preset") == "" and "no preset called" in block.get("why", ""),
              block)
        check("... it is a read: the file it read is still exactly there",
              _startup_file().exists())
        check("... and restart_reconcile is still reported beside it",
              "restart_reconcile" in body, sorted(body))
    finally:
        (P.hardware_block, P.recommendations, P.cloud_view) = real
        clean()


# ==========================================================================
#  9. chat: the owner's own words, and the sentence it must not take
# ==========================================================================

def t_the_chat_sentences_are_the_owners_own_words():
    clean()
    cases = (
        ("load the general preset when you start", {"name": "general",
                                                    "clear": False}),
        ("load the General preset on startup", {"name": "General", "clear": False}),
        ("make general my default preset on startup",
         {"name": "general", "clear": False}),
        ("make the general preset my default when atlas starts",
         {"name": "general", "clear": False}),
        ("set the default preset to general", {"name": "general", "clear": False}),
        ("stop loading a preset when you start", {"clear": True}),
        ("don't load a preset when you start", {"clear": True}),
        ("clear the startup preset", {"clear": True}),
        ("no preset on startup", {"clear": True}),
    )
    for sentence, want in cases:
        got = Q.match(sentence)
        check(f"chat matches {sentence!r}",
              got is not None and got.name == "startup_preset"
              and dict(got.f) == want,
              (None if got is None else (got.name, dict(got.f)), want))


def t_the_ordinary_preset_sentence_is_not_a_startup_setting():
    clean()
    for sentence in ("use the general preset now",
                     "switch to the general preset",
                     "apply the coding preset",
                     "use the general preset"):
        got = Q.match(sentence)
        check(f"the ordinary {sentence!r} is NOT the start-up setting",
              got is None or got.name != "startup_preset",
              None if got is None else (got.name, dict(got.f)))
    check("... and matching it wrote no setting",
          not _startup_file().exists(), P.startup_view())
    check('"load the general preset" (no start marker) is not the setting either',
          Q.match("load the general preset") is None
          or Q.match("load the general preset").name != "startup_preset",
          None if Q.match("load the general preset") is None
          else Q.match("load the general preset").name)
    clean()


def t_the_chat_sentence_sets_the_same_file_through_the_same_door():
    clean()
    gate = Gate()
    real_gate = P._gate
    P._gate = gate
    try:
        out = Q.run(Q.match("load the general preset when you start"), None,
                    time.time())
        check("chat setting it raises ONE change_own_config card",
              out is not None and len(gate.calls) == 1
              and gate.calls[0][0] == "change_own_config", gate.calls)
        check("... writes the SAME file the route writes",
              json.loads(_startup_file().read_text(encoding="utf-8"))
              == {"preset": "general"}, P.startup_view())
        check("... and answers in plain words naming the NEXT start",
              out is not None and "every time it starts" in out.reply
              and "Nothing on this PC changes until the next start" in out.reply,
              out.reply if out else None)
        out = Q.run(Q.match("stop loading a preset when you start"), None,
                    time.time())
        check("chat clearing it is instant and removes the same file",
              out is not None and not _startup_file().exists()
              and len(gate.calls) == 1
              and "No preset will be loaded" in out.reply,
              (out.reply if out else None, _startup_file().exists()))
        # THE SAME DOOR, BY NAME: the chat runner calls set_startup_preset.
        real = P.set_startup_preset
        seen = []
        P.set_startup_preset = lambda **kw: (seen.append(dict(kw))
                                             or (200, {"ok": True, "changed": True,
                                                       "card": True,
                                                       "message": "stub"}))
        try:
            Q.run(Q.match("load the general preset when you start"), None,
                  time.time())
        finally:
            P.set_startup_preset = real
        check("the chat runner calls the one function, with the resolved id",
              seen == [{"preset": "general"}], seen)
    finally:
        P._gate = real_gate
        clean()


def t_a_refused_chat_card_is_never_reported_as_set():
    clean()
    gate = Gate(allowed=False)
    real_gate = P._gate
    P._gate = gate
    try:
        out = Q.run(Q.match("make general my default preset on startup"), None,
                    time.time())
        check("a denied card says the setting did not change, and writes nothing",
              out is not None and "Not changed" in out.reply
              and not _startup_file().exists(), out.reply if out else None)
        check("... and it never claims the preset will load",
              out is not None and "will load" not in out.reply,
              out.reply if out else None)
    finally:
        P._gate = real_gate
        clean()


def t_an_unknown_preset_in_chat_says_so_without_a_card():
    clean()
    gate = Gate()
    real_gate = P._gate
    P._gate = gate
    try:
        out = Q.run(Q.match("load the nonsense preset when you start"), None,
                    time.time())
        check("an unknown preset is said plainly, with no card",
              out is not None and "I do not know a preset called" in out.reply
              and gate.calls == [], (out.reply if out else None, gate.calls))
    finally:
        P._gate = real_gate
        clean()


# ==========================================================================

TESTS = [
    t_the_setting_is_the_named_file_and_reads_honestly,
    t_setting_raises_one_card_and_writes_nothing_before_the_yes,
    t_clearing_is_instant_and_removes_the_file,
    t_an_unknown_id_and_a_bad_body_are_400s_with_no_card,
    t_the_route_sets_and_clears_through_the_one_door,
    t_the_startup_apply_loads_the_preset_through_the_routes_road,
    t_the_keep_alive_reaches_the_lanes_one_loader,
    t_rest_hours_are_respected_and_no_energy_rest_setting_is_invented,
    t_a_rest_window_changes_the_load_the_startup_apply_asks_for,
    t_switching_preset_still_replaces_the_model_no_second_copy,
    t_a_failed_startup_apply_falls_back_and_records_why,
    t_an_apply_that_raises_is_said_and_the_fallback_still_runs,
    t_with_no_startup_preset_the_step_is_todays_reconcile,
    t_a_startup_load_never_blocks_the_hud,
    t_with_no_startup_preset_install_still_reconciles_synchronously,
    t_live_status_carries_the_small_read_only_block,
    t_the_chat_sentences_are_the_owners_own_words,
    t_the_ordinary_preset_sentence_is_not_a_startup_setting,
    t_the_chat_sentence_sets_the_same_file_through_the_same_door,
    t_a_refused_chat_card_is_never_reported_as_set,
    t_an_unknown_preset_in_chat_says_so_without_a_card,
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
