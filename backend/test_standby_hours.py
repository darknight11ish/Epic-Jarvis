"""jarvis_power.py's standby hours - the window the owner sets, and the unload.

    python3 test_standby_hours.py

No Ollama, no real graphics card, no network. A fake `jarvis_models` and a
fake everyday Ollama are what the unload path is driven against, so nothing in
this suite can free or load a real model.

WHAT IS PINNED, and why each one is here:

1. THE DECISION TABLE. `jarvis_power.current()` used to return a hard-coded
   "quiet" inside `[power]`'s window and never called `should_standby()` at all,
   so `schedule_mode` and `idle_mode` - both in the owner's file, both
   documented as what a window drops TO - were read by nothing. Every cell of
   the table is checked: inside and outside the window, a window that crosses
   midnight, quiet vs standby, the idle timer on and off, the feature off, and
   a mode the owner chose winning over a rule.
2. THE UNLOAD, WHICH IS THE POINT. A window that only makes `current()` say
   "standby" frees no graphics card. `enforce()` must actually ask
   `jarvis_power_switch` to unload, and the answer must say which models were
   freed - and a failed unload must never raise out of a clock tick.
3. NOTHING IS UNLOADED WHILE SOMETHING IS USING IT. A turn being answered, a
   Live conversation, an approval card on screen and a multi-step task all hold
   it off; the mode does not change and nothing is freed. This is the check
   that stops a blank answer at 23:00, so it is proved for each of the four.
4. `force` IN set_mode. Inside the window `current()` already READS "standby"
   while the stored mode is still "active"; without `force`, set_mode answers
   "Already standby." and frees nothing. That exact bug is pinned.
5. THE FOUR ROWS THE OWNER CHANGES. They exist in `jarvis_limits.LIMITS`, they
   default to today's behaviour (off, quiet, 23:00-07:00), they are `app="both"`
   so both apps draw them, their kinds are ones both clients already draw, and
   a change asks the owner under `change_own_config` - while saying no changes
   nothing and raises no card.
"""
import sys
import tempfile
import traceback
import types
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import missing, require_shipped  # noqa: E402

require_shipped("jarvis_power.py", "jarvis_power_switch.py", "jarvis_limits.py")

# ---------------------------------------------------------------------------
#   A settings file we own, so nothing here reads the owner's
# ---------------------------------------------------------------------------
CONFIG = {"power": {"enabled": True, "schedule_enabled": False, "quiet_start": "23:00",
                    "quiet_end": "07:00", "schedule_mode": "quiet",
                    "idle_enabled": False, "idle_minutes": 45, "idle_mode": "quiet"}}
TMP = Path(tempfile.mkdtemp(prefix="jarvis-hours-"))
TOML = TMP / "jarvis-framework.toml"
TOML.write_text("[power]\n"
                'enabled = true\nschedule_enabled = false\nquiet_start = "23:00"\n'
                'quiet_end = "07:00"\nschedule_mode = "quiet"\nidle_enabled = false\n'
                "idle_minutes = 45\nidle_mode = " '"quiet"\n', encoding="utf-8")

fw = types.ModuleType("jarvis_framework")


def _load_framework():
    # A deep-ish copy so a test can change one key and nothing else.
    return {k: dict(v) if isinstance(v, dict) else v for k, v in CONFIG.items()}


fw.load_framework = _load_framework
fw.reload_framework = lambda: None
fw.config_path = lambda: str(TOML)
fw.audit_log = lambda *a, **k: None
sys.modules["jarvis_framework"] = fw

if missing("jarvis_power.py"):
    sys.path.append(str(HERE / "rebuilt"))
import jarvis_power as P  # noqa: E402
import jarvis_power_switch as S  # noqa: E402
import jarvis_limits as L  # noqa: E402

#: No thread under the tests: every edge is driven by hand.
P._KEEPER_AUTOSTART = False

FAILED, PASSED = [], []


def check(label, ok, detail=""):
    (PASSED if ok else FAILED).append(label)
    print(("  ok   " if ok else "  FAIL ") + label + ("" if ok else f"  <- {detail}"))


def eq(label, got, want):
    check(label, got == want, f"got {got!r}, want {want!r}")


def hours(**kw):
    """Set keys in the fake `[power]` table, then put them back."""
    old = dict(CONFIG["power"])
    CONFIG["power"].update(kw)
    return old


def restore(old):
    CONFIG["power"].clear()
    CONFIG["power"].update(old)


def reset_power():
    """A fresh process-like state between tests."""
    with P._LOCK:
        P._state.update({"mode": "active", "why": "startup", "manual": False,
                         "rule_seen": None})
    # A power card left in flight by the previous test would make the next
    # set_mode answer 409 ("already waiting") - a real guard, and not what the
    # next test is asking about.
    S._PENDING.clear()
    CONFIG["power"].clear()
    CONFIG["power"].update({"enabled": True, "schedule_enabled": False,
                            "quiet_start": "23:00", "quiet_end": "07:00",
                            "schedule_mode": "quiet", "idle_enabled": False,
                            "idle_minutes": 45, "idle_mode": "quiet"})


def at(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M")


def cover_now(**kw):
    """A window that contains the REAL clock, for the tests that must go
    through `current()` (which always reads the real clock and takes no
    argument, on purpose - that is the design being kept)."""
    from datetime import timedelta
    n = datetime.now()
    CONFIG["power"].update({"schedule_enabled": True,
                            "quiet_start": (n - timedelta(minutes=2)).strftime("%H:%M"),
                            "quiet_end": (n + timedelta(minutes=2)).strftime("%H:%M")})
    CONFIG["power"].update(kw)


# ---------------------------------------------------------------------------
#   1. The decision table
# ---------------------------------------------------------------------------
def t_the_window_is_still_the_window():
    reset_power()
    check("schedule_enabled false: no window at all", not P.in_quiet_hours(at("2026-11-03 23:30")))
    hours(schedule_enabled=True)
    check("inside 23:00-07:00", P.in_quiet_hours(at("2026-11-03 23:30")))
    check("just before it starts", not P.in_quiet_hours(at("2026-11-03 22:59")))
    check("at the start minute", P.in_quiet_hours(at("2026-11-03 23:00")))
    # A window that crosses midnight is the normal case and the one a naive
    # `start <= t <= end` gets silently wrong.
    check("after midnight, still inside", P.in_quiet_hours(at("2026-11-04 03:00")))
    check("at the end minute it is over", not P.in_quiet_hours(at("2026-11-04 07:00")))
    check("midday is outside", not P.in_quiet_hours(at("2026-11-04 12:00")))
    restore({"enabled": True, "schedule_enabled": False, "quiet_start": "23:00",
             "quiet_end": "07:00", "schedule_mode": "quiet", "idle_enabled": False,
             "idle_minutes": 45, "idle_mode": "quiet"})


def t_a_window_that_does_not_cross_midnight():
    reset_power()
    hours(schedule_enabled=True, quiet_start="09:00", quiet_end="17:00")
    check("inside a plain same-day window", P.in_quiet_hours(at("2026-11-03 12:00")))
    check("outside it", not P.in_quiet_hours(at("2026-11-03 19:00")))


def t_what_the_window_drops_to():
    reset_power()
    # `rule()`/`schedule_drop()` take a time, so the fixed 23:00-07:00 window
    # is used for every assertion about them.
    hours(schedule_enabled=True, schedule_mode="quiet")
    eq("schedule_mode quiet: rule() says quiet", P.rule(at("2026-11-03 23:30")),
       ("quiet", P.WHY))
    eq("schedule_mode quiet: schedule_drop() says quiet",
       P.schedule_drop(at("2026-11-03 23:30")), "quiet")
    hours(schedule_mode="standby")
    eq("schedule_mode standby: rule() says standby",
       P.rule(at("2026-11-03 23:30"))[0], "standby")
    eq("schedule_drop() alone", P.schedule_drop(at("2026-11-03 23:30")), "standby")
    # A word the file cannot mean must not become "free the cards".
    for bad in ("active", "sleep", "", "QUIET!", "standbyy"):
        hours(schedule_mode=bad)
        eq(f"schedule_mode {bad!r} falls back to quiet, never standby",
           P.schedule_drop(at("2026-11-03 23:30")), "quiet")
    hours(schedule_mode="STANDBY")
    eq("the word is not case sensitive", P.schedule_drop(at("2026-11-03 23:30")), "standby")
    # current() always reads the real clock, on purpose - so it is driven by a
    # window that contains the real clock.
    reset_power()
    cover_now(schedule_mode="quiet")
    eq("current() with schedule_mode quiet reads quiet", P.current(), "quiet")
    cover_now(schedule_mode="standby")
    eq("current() with schedule_mode standby reads standby", P.current(), "standby")


def t_outside_the_window_nothing_changes():
    reset_power()
    hours(schedule_enabled=True, schedule_mode="standby")
    eq("outside the window the mode is active", P.current(), "active")
    eq("rule() finds nothing", P.rule(at("2026-11-04 12:00")), (None, ""))
    out = P.enforce(at("2026-11-04 12:00"))
    check("enforce() outside the window does nothing", out.get("changed") is False, out)


def t_the_feature_off_is_todays_behaviour():
    reset_power()
    hours(enabled=False, schedule_enabled=True, schedule_mode="standby")
    eq("[power] enabled false: no rule, even inside the hours", P.current(), "active")
    eq("rule() is empty", P.rule(at("2026-11-03 23:30")), (None, ""))
    eq("schedule_drop() is empty", P.schedule_drop(at("2026-11-03 23:30")), None)


def t_the_idle_timer():
    reset_power()
    hours(idle_enabled=True, idle_minutes=45, idle_mode="standby")
    with P._LOCK:
        P._state["last_seen"] = 0.0            # idle for a very long time
    check("idle_enabled: the timer has run out", P.should_standby())
    eq("idle_mode standby: it reads standby", P.idle_drop(), "standby")
    eq("and current() is standby", P.current(), "standby")
    hours(idle_mode="quiet")
    eq("idle_mode quiet: it reads quiet", P.current(), "quiet")
    hours(idle_enabled=False)
    with P._LOCK:
        P._state["last_seen"] = 0.0
    check("idle_enabled false: the timer never fires", not P.should_standby())
    eq("current() is active again", P.current(), "active")
    hours(idle_enabled=True, idle_minutes=0)
    check("idle_minutes 0 means no timer", not P.should_standby())


def t_a_chosen_mode_wins_over_a_rule():
    reset_power()
    hours(schedule_enabled=True, schedule_mode="standby")
    P.set_mode("quiet", why="the owner, from the desktop")
    eq("Quiet chosen by hand is not deepened to Standby", P.current(), "quiet")
    check("and the stored mode is what the owner asked for", P._state["mode"] == "quiet")
    P.set_mode("active", why="the owner, from the desktop")
    eq("active chosen by hand does not free the cards", P.current(), "active")
    P.set_mode("standby", why="the owner, from the desktop")
    eq("Standby chosen by hand stays Standby", P.current(), "standby")
    reset_power()
    hours(schedule_enabled=False)
    P.set_mode("standby", why="the standby schedule")
    eq("the standby schedule's Standby survives outside any window", P.current(), "standby")


# ---------------------------------------------------------------------------
#   2. The unload, with a fake models module and a fake Ollama
# ---------------------------------------------------------------------------
class FakeModels:
    """What `jarvis_models` looks like to the unload path."""

    def __init__(self, names, fail=()):
        self.names = list(names)
        self.fail = set(fail)
        self.unloaded = []

    def resident_models(self):
        return list(self.names)

    def unload(self, name):
        if name in self.fail:
            raise RuntimeError("no")
        self.unloaded.append(name)


class FakeEveryday:
    """`jarvis_power_switch.EverydayOllama`: what `/api/ps` says, and unloads."""

    def __init__(self, loaded, url="http://127.0.0.1:11434"):
        self.loaded = list(loaded)
        self.url = url
        self.unloaded = []

    def ps(self):
        return list(self.loaded)

    def unload(self, name):
        self.unloaded.append(name)
        self.loaded = [n for n in self.loaded if n != name]


def _with_unload(names=("jarvis-primary:latest",), loaded=("qwen3.5:9b",),
                 fail=(), gate_ok=True):
    """Put the fakes where the real code looks, and return them.

    `jarvis_models` is a MODULE in sys.modules, never the real file: this
    suite must not be able to unload a model on the PC it runs on.
    """
    models = FakeModels(names, fail=fail)
    everyday = FakeEveryday(loaded)
    fake = types.ModuleType("jarvis_models")
    fake.resident_models = models.resident_models
    fake.unload = models.unload
    sys.modules["jarvis_models"] = fake
    S.everyday_ollama = lambda: everyday
    verdict = types.SimpleNamespace(allowed=gate_ok, outcome="approved" if gate_ok else "denied",
                                    tier="ask")
    S._gate_check = lambda action, detail, prompt: verdict
    return models, everyday


def t_standby_really_unloads_and_says_what():
    reset_power()
    models, everyday = _with_unload()
    hours(schedule_enabled=True, schedule_mode="standby")
    out = P.enforce(at("2026-11-03 23:30"), wait_s=5.0)
    check("enforce() changed the mode", out.get("changed") is True, out)
    eq("the stored mode is standby", P._state["mode"], "standby")
    eq("what it recorded as freed", sorted(out.get("unloaded") or []),
       sorted(["jarvis-primary:latest", "qwen3.5:9b"]))
    check("the everyday model really was asked to unload", "qwen3.5:9b" in everyday.unloaded,
          everyday.unloaded)
    check("and jarvis_models' name too", "jarvis-primary:latest" in models.unloaded,
          models.unloaded)
    eq("status() keeps what was freed", sorted((P.status().get("last_unload") or {})
                                               .get("unloaded") or []),
       sorted(["jarvis-primary:latest", "qwen3.5:9b"]))
    check("the answer says something in plain words", bool(str(out.get("said") or "").strip()), out)


def t_force_is_what_makes_the_unload_happen():
    # THE BUG THIS FEATURE WOULD HAVE SHIPPED WITHOUT: inside the window
    # current() already reads "standby", so set_mode's own "Already standby."
    # answer would skip the unload entirely.
    reset_power()
    cover_now(schedule_mode="standby")
    eq("current() already reads standby before anything was unloaded",
       P.current(), "standby")
    eq("the stored mode is still active", P._state["mode"], "active")
    code, out = S.set_mode("standby", why=P.WHY, wait_s=5.0, ollama=FakeEveryday([]))
    eq("without force: 'already standby', nothing changed", (code, out.get("changed")),
       (200, False))
    eq("and the stored mode is still active", P._state["mode"], "active")
    reset_power()
    cover_now(schedule_mode="standby")
    _with_unload()
    code, out = S.set_mode("standby", why=P.WHY, wait_s=5.0, force=True)
    eq("with force: 200 and changed", (code, out.get("changed")), (200, True))


def t_a_failed_unload_never_raises():
    reset_power()
    models, everyday = _with_unload(fail=("jarvis-primary:latest",))
    hours(schedule_enabled=True, schedule_mode="standby")
    out = P.enforce(at("2026-11-03 23:30"), wait_s=5.0)
    check("a model that refuses to unload does not crash the tick", isinstance(out, dict), out)
    check("the one that did work is still reported", "qwen3.5:9b" in
          (out.get("unloaded") or []), out)
    # A broken jarvis_models module entirely.
    reset_power()
    hours(schedule_enabled=True, schedule_mode="standby")
    broken = types.ModuleType("jarvis_models")
    broken.resident_models = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    real = sys.modules.get("jarvis_models")
    sys.modules["jarvis_models"] = broken
    try:
        S.everyday_ollama = lambda: FakeEveryday([])
        out = P.enforce(at("2026-11-03 23:30"), wait_s=5.0)
        check("jarvis_models raising does not crash the tick", isinstance(out, dict), out)
    finally:
        if real is not None:
            sys.modules["jarvis_models"] = real
        else:
            sys.modules.pop("jarvis_models", None)


def t_the_window_ending_wakes_what_it_put_to_sleep():
    reset_power()
    _with_unload()
    hours(schedule_enabled=True, schedule_mode="standby")
    P.enforce(at("2026-11-03 23:30"), wait_s=5.0)
    eq("on standby after the window opened", P._state["mode"], "standby")
    eq("and it was this module's own doing", P._state["why"], P.WHY)
    out = P.enforce(at("2026-11-04 07:30"), wait_s=5.0)
    eq("the end of the window wakes it", P._state["mode"], "active")
    check("the answer says it changed", out.get("changed") is True, out)


def t_the_window_leaves_alone_what_it_did_not_put_to_sleep():
    reset_power()
    _with_unload()
    hours(schedule_enabled=True, schedule_mode="standby")
    P.set_mode("standby", why="the owner, from the phone")
    out = P.enforce(at("2026-11-04 07:30"), wait_s=5.0)
    eq("Standby chosen by hand stays on after the window ends", P._state["mode"], "standby")
    check("and nothing was changed", out.get("changed") is False, out)


def t_a_tap_inside_the_window_is_not_overruled():
    reset_power()
    _with_unload()
    hours(schedule_enabled=True, schedule_mode="standby")
    P.enforce(at("2026-11-03 23:30"), wait_s=5.0)
    eq("on standby at the start of the window", P._state["mode"], "standby")
    # The owner is up at 02:00 and asks for Active.
    P.set_mode("active", why="the owner, from the desktop")
    eq("his Active is honoured", P.current(), "active")
    out = P.enforce(at("2026-11-04 02:10"), wait_s=5.0)
    eq("the keeper does not put him back on standby", P._state["mode"], "active")
    check("and says why it did nothing", out.get("changed") is False, out)
    _with_unload()
    out = P.enforce(at("2026-11-04 07:05"), wait_s=5.0)
    check("at the window's end the manual choice is forgotten, nothing to do",
          out.get("changed") is False, out)


# ---------------------------------------------------------------------------
#   3. Nothing is unloaded while something is using it
# ---------------------------------------------------------------------------
def _fake_modules(**patches):
    """Replace modules `in_flight()` asks, and put them back."""
    saved = {name: sys.modules.get(name) for name in patches}
    for name, mod in patches.items():
        sys.modules[name] = mod
    return saved


def _restore(saved):
    for name, mod in saved.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod


def t_nothing_is_unloaded_while_a_turn_or_card_is_in_flight():
    reset_power()
    hours(schedule_enabled=True, schedule_mode="standby")
    _with_unload()

    def none_running():
        return types.SimpleNamespace(running=lambda: [])

    events_quiet = types.ModuleType("jarvis_events")
    events_quiet.activity = lambda: {"state": "idle", "detail": ""}
    gate_clear = types.ModuleType("jarvis_gate")
    gate_clear.pending = lambda: []

    saved = _fake_modules(jarvis_task_control=none_running(), jarvis_events=events_quiet,
                          jarvis_gate=gate_clear)
    try:
        eq("nothing in flight: no reason to wait", P.in_flight(), None)

        # A turn being answered.
        events_quiet.activity = lambda: {"state": "thinking", "detail": ""}
        eq("a turn being answered holds it off", P.in_flight(),
           "Jarvis is thinking right now")
        before = dict(P._state)
        out = P.enforce(at("2026-11-03 23:30"), wait_s=5.0)
        check("nothing was unloaded while a turn was in flight", out.get("changed") is False, out)
        eq("and the mode did not change", P._state["mode"], before["mode"])
        check("the hold is recorded honestly", "thinking" in
              str((P.status().get("last_hold") or {}).get("held") or ""),
              P.status().get("last_hold"))

        # Speaking counts too, and so does a tool working.
        for state in ("speaking", "working"):
            events_quiet.activity = lambda s=state: {"state": s, "detail": ""}
            check(f"{state} also holds it off", P.in_flight() is not None)

        # A card on screen.
        events_quiet.activity = lambda: {"state": "idle", "detail": ""}
        gate_clear.pending = lambda: [{"id": "a1", "action": "x", "tier": "ask"}]
        eq("a waiting approval card holds it off", P.in_flight(),
           "an approval card is waiting")
        out = P.enforce(at("2026-11-03 23:30"), wait_s=5.0)
        check("nothing unloaded while a card waits", out.get("changed") is False, out)

        # A multi-step task.
        gate_clear.pending = lambda: []
        saved2 = _fake_modules(jarvis_task_control=types.SimpleNamespace(
            running=lambda: [{"id": "t1"}]))
        try:
            eq("a running task holds it off", P.in_flight(), "a task is running")
            eq("but jarvis_power_switch keeps its own task branch",
               P.in_flight(include_tasks=False), None)
        finally:
            _restore(saved2)
    finally:
        _restore(saved)


def t_a_live_conversation_holds_it_off():
    reset_power()
    hours(schedule_enabled=True, schedule_mode="standby")
    _with_unload()
    events_quiet = types.ModuleType("jarvis_events")
    events_quiet.activity = lambda: {"state": "idle", "detail": ""}
    gate_clear = types.ModuleType("jarvis_gate")
    gate_clear.pending = lambda: []
    chatbot = types.ModuleType("jarvis_chatbot")
    chatbot.view = lambda _x="": {"session": {"id": "s1", "state": "running"}}
    saved = _fake_modules(jarvis_task_control=types.SimpleNamespace(running=lambda: []),
                          jarvis_events=events_quiet, jarvis_gate=gate_clear,
                          jarvis_chatbot=chatbot,
                          jarvis_chatbot_compare=types.SimpleNamespace(live=lambda: False),
                          jarvis_support=types.SimpleNamespace(live=lambda: False))
    try:
        eq("a Live conversation holds it off", P.in_flight(),
           "a Live conversation is running")
        out = P.enforce(at("2026-11-03 23:30"), wait_s=5.0)
        check("nothing unloaded under a Live conversation", out.get("changed") is False, out)
        chatbot.view = lambda _x="": {"session": {"id": "s1", "state": "done"}}
        eq("a finished session does not", P.in_flight(), None)
    finally:
        _restore(saved)


def t_set_mode_refuses_while_a_turn_runs():
    # The guard is in the module that unloads, not only in the clock's path, so
    # a tap on Standby in either app is refused too.
    reset_power()
    _with_unload()
    events = types.ModuleType("jarvis_events")
    events.activity = lambda: {"state": "speaking", "detail": ""}
    saved = _fake_modules(jarvis_task_control=types.SimpleNamespace(running=lambda: []),
                          jarvis_events=events,
                          jarvis_gate=types.SimpleNamespace(pending=lambda: []))
    try:
        code, out = S.set_mode("standby", by="desktop", wait_s=1.0)
        eq("a tap on Standby while Jarvis is speaking: 409", code, 409)
        check("the words say why, and that nothing was unloaded",
              "speaking" in str(out.get("error") or ""), out)
        check("no model was unloaded", not out.get("unloaded"), out)
        eq("and the mode did not change", P._state["mode"], "active")
    finally:
        _restore(saved)


# ---------------------------------------------------------------------------
#   4. The four rows the owner changes
# ---------------------------------------------------------------------------
def t_the_four_rows_exist_and_default_to_today():
    keys = ("standby_hours_on", "standby_hours_unload", "standby_hours_start",
            "standby_hours_end")
    for key in keys:
        row = L.find(key)
        check(f"{key} is in the one table both apps draw", row is not None)
        if row is None:
            continue
        eq(f"{key} is on both apps", row.app, "both")
        check(f"{key} is a kind both clients already draw ({row.kind})",
              row.kind in ("bool", "time"))
        check(f"{key} asks the owner", row.always_asks is True)
        check(f"{key} says what the card is really about",
              bool(row.card_more) and "more" not in row.card_more.lower())
        eq(f"{key} writes the key jarvis_power reads", (row.section, row.name),
           ("power", {"standby_hours_on": "schedule_enabled",
                      "standby_hours_unload": "schedule_mode",
                      "standby_hours_start": "quiet_start",
                      "standby_hours_end": "quiet_end"}[key]))
    eq("the switch is off by default", L.value_of(L.find("standby_hours_on")), False)
    eq("what it drops to is quiet by default",
       L.value_of(L.find("standby_hours_unload")), False)
    eq("the window starts at the shipped 23:00",
       L.value_of(L.find("standby_hours_start")), "23:00")
    eq("and ends at the shipped 07:00", L.value_of(L.find("standby_hours_end")), "07:00")


def t_the_unload_row_reads_the_word_in_the_file():
    row = L.find("standby_hours_unload")
    eq("the word for on is standby", row.on_text, "standby")
    eq("the word for off is quiet", row.off_text, "quiet")
    eq("the literal written when it is on", L._literal(row, True), '"standby"')
    eq("the literal written when it is off", L._literal(row, False), '"quiet"')
    old = dict(CONFIG["power"])
    CONFIG["power"]["schedule_mode"] = "standby"
    try:
        eq("a file saying standby reads as on", L.value_of(row), True)
        CONFIG["power"]["schedule_mode"] = "quiet"
        eq("a file saying quiet reads as off", L.value_of(row), False)
        CONFIG["power"]["schedule_mode"] = "nonsense"
        eq("a word nobody can mean reads as off, not as free the cards",
           L.value_of(row), False)
    finally:
        restore(old)


def t_a_change_asks_the_owner_and_a_refusal_changes_nothing():
    asked = []

    def gate(action, detail, prompt):
        asked.append((action, detail.get("was"), detail.get("now")))
        return types.SimpleNamespace(allowed=True, outcome="approved", tier="ask")

    L.configure(gate=gate, tier_of=lambda a: "ask")
    try:
        code, out = L.change({"key": "standby_hours_on", "value": True})
        eq("turning the hours on: 200", code, 200)
        eq("asked exactly once", len(asked), 1)
        eq("under change_own_config, the config card", asked[0][0], "change_own_config")
        eq("from off to on", (asked[0][1], asked[0][2]), (False, True))
        check("and says plainly that it is now on",
              str(out.get("said") or "") == "Keep Jarvis quiet during my hours: on.",
              out)

        asked.clear()
        code, out = L.change({"key": "standby_hours_start", "value": "23:30"})
        eq("moving a time also asks", len(asked), 1)
        eq("and the card names both times", (asked[0][1], asked[0][2]), ("23:00", "23:30"))

        asked.clear()
        code, out = L.change({"key": "standby_hours_end", "value": "07:00"})
        check("setting it to what it already is asks nothing and says so",
              not asked and code == 200, (asked, code, out))

        # A denial: the value is not written.
        asked.clear()

        def no(action, detail, prompt):
            return types.SimpleNamespace(allowed=False, outcome="denied", tier="ask")

        L.configure(gate=no, tier_of=lambda a: "ask")
        before = TOML.read_text(encoding="utf-8")
        code, out = L.change({"key": "standby_hours_unload", "value": True})
        eq("a denied card is 409", code, 409)
        eq("and the file is untouched", TOML.read_text(encoding="utf-8"), before)
        eq("nor did the value move", L.value_of(L.find("standby_hours_unload")), False)
    finally:
        L.configure(gate=None, tier_of=None)


def t_the_rows_are_drawn_from_the_one_table():
    body = L.view(app="phone")
    keys = [r["key"] for r in body["limits"]]
    for key in ("standby_hours_on", "standby_hours_unload", "standby_hours_start",
                "standby_hours_end"):
        check(f"the phone's view carries {key}", key in keys)
    for row in body["limits"]:
        if row["key"].startswith("standby_hours"):
            check(f"{row['key']} reaches the screen with a value it can draw",
                  row["kind"] in ("bool", "time") and row["value"] is not None, row)
            check(f"{row['key']} is not PC-only, so the phone may change it",
                  row["pc_only"] is False, row)
    desktop = [r["key"] for r in L.view(app="desktop")["limits"]]
    for key in ("standby_hours_on", "standby_hours_unload", "standby_hours_start",
                "standby_hours_end"):
        check(f"the desktop's view carries {key}", key in desktop)


def t_the_switch_is_off_on_a_pc_that_never_touches_it():
    # The shipped [power] section, as both copies of jarvis-framework.toml have
    # it: schedule_enabled false, schedule_mode "quiet", 23:00-07:00.
    import re
    root = HERE.parent
    seen = 0
    for rel in ("jarvis-backend/jarvis-framework.toml", "backend/rebuilt/jarvis-framework.toml"):
        p = root / rel
        if not p.is_file():
            continue
        seen += 1
        text = p.read_text(encoding="utf-8")
        block = text.split("[power]", 1)[1].split("\n[", 1)[0]
        check(f"{rel}: schedule_enabled is false in the shipped file",
              re.search(r"(?m)^\s*schedule_enabled\s*=\s*false\s*$", block) is not None,
              block[:400])
        check(f"{rel}: schedule_mode is quiet in the shipped file",
              re.search(r'(?m)^\s*schedule_mode\s*=\s*"quiet"\s*$', block) is not None,
              block[:400])
        check(f"{rel}: the file no longer claims these keys are unread",
              "not read" not in block, block[:400])
    check("both copies of the settings file were checked", seen == 2, seen)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("t_") and callable(v)]
    for fn in tests:
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
