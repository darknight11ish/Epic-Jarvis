"""The drop-in plugins, switched ON and OFF by talking (2026-11-26).

    python -B backend/test_plugin_chat.py

THE OWNER'S ASK: "full manipulation of every tool and plug in". Listing a
plugin (`plugin_list`) and adding one (`plugin_install`) were already answered
by the fast path in `backend/jarvis_quick.py`. Turning ONE on or off was not:
the switch guard inside `_plugins_question` handed every "turn on/off ... plugin"
sentence to the local model, and "which plugins are switched off" came back as
the whole list. This suite proves the six sentences that answer now, and - just
as importantly - that they still go through the AGENT'S OWN card pipeline rather
than a second switch invented here.

WHAT IS PROVED HERE, and each one is a different way the feature could lie:

  1. EVERY PHRASING REACHES ITS OWN INTENT, by intent (never "an answer came
     back"): the four switch shapes reach `plugin_on`/`plugin_off` naming the
     plugin, "which plugins are switched off" reaches `plugin_off_list`, and
     "is plugin <name> on" reaches `plugin_on_state`.

  2. THE OTHER LANES KEEP THEIR SENTENCES, in both directions: "turn on the
     timer tool" is still `settings_tool`, "how do I install a plugin" is still
     `plugin_install`, "what plugins do you have" and "list my plugins" are
     still `plugin_list`, "is docker plugin installed?" is still `plugin_state`
     - and the six new sentences are NOT those intents.

  3. THE NAME IS THE REAL REGISTRY'S. An unknown plugin is refused before any
     card, and the answer names both the words it looked for and the plugins
     that really exist. A space for a hyphen ("notes edit" for the folder
     "notes-edit") is the one alias the catalogue answers already use.

  4. ENABLING RAISES THE EXISTING CARD. ONE call to the agent's own gate, under
     the existing `modify_own_code` action, whose text is byte-for-byte what
     `jarvis_agent._prepare_plugin_switch` produced (so no second card wording
     exists), naming the plugin and the marker file. Approving it runs the
     agent's own `_execute_plugin_switch`, and the marker goes.

  5. DISABLING IS IMMEDIATE AND CARDLESS, the project's own on/off rule for
     every switch (docs/DECISIONS.md, 2026-11-02), and its answer says plainly
     that the plugin will not load until it is switched back on and names the
     sentence that undoes it. No gate call, one marker file, no other file
     touched.

  6. DENY CHANGES NOTHING. A denied card and a timed-out card leave the disk
     byte-for-byte what it was, and the state read back from the registry is
     still off.

  7. THE TWO READS ANSWER FROM THE LIVE REGISTRY, with no card and no write:
     the complement with its count, and the true state of one named plugin
     (on, off with the loader's own reason, and off inside its own
     plugin.json). A full folder snapshot before and after proves both are
     reads.

  8. THE SWITCH IS THE AGENT'S OWN CODE, pinned structurally: `jarvis_quick`
     calls `jarvis_agent._prepare_plugin_switch`, `_execute_plugin_switch`,
     `_plugin_apply` and `_gate_check`, and its own plugin functions contain no
     file write at all - so a later "quick" rewrite of the marker fails here.

  9. THE CHAT REQUEST IS NOT HELD OPEN. A slow card answers "one approval card
     is waiting" in about the wait budget, and the approved write still lands
     afterwards through the same plan.

TWO ROWS MUST BITE WHEN REVERTED, and they are named:

  * BITE 1 - `t_each_phrasing_reaches_its_own_intent`: on the tree before this
    change every switch sentence matched NOTHING (it went to the model) and
    "which plugins are switched off" matched `plugin_list`.
  * BITE 2 - `t_enabling_raises_the_existing_modify_own_code_card`: on the tree
    before this change no chat sentence raised any card at all.

No model runs, no network, no real approval card, and the owner's own plugin
folder is never read or written: `JARVIS_PLUGINS_DIR` points at a throwaway
folder for the whole run, and the config, home and log folders are throwaway
too.
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Hermetic before any shipped module reads a config or a home folder.
TMP = Path(tempfile.mkdtemp(prefix="jarvis-plugin-chat-"))
CFG = TMP / "config"
CFG.mkdir(parents=True, exist_ok=True)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CFG)
os.environ["JARVIS_CONFIG_DIR"] = str(CFG)
os.environ["OPENJARVIS_HOME"] = str(TMP / "home")
os.environ["JARVIS_HOME"] = str(TMP / "home")
os.environ["JARVIS_LOG_DIR"] = str(TMP / "logs")
os.environ["JARVIS_SCHEDULE_DB"] = str(TMP / "schedule.db")
os.environ.pop("JARVIS_FRAMEWORK_TOML", None)

sys.path.insert(0, str(HERE))
sys.path.append(str(HERE / "rebuilt"))
sys.path.append(str(HERE.parent / "jarvis-backend"))

import jarvis_agent as AG  # noqa: E402
import jarvis_plugins  # noqa: E402
import jarvis_quick as Q  # noqa: E402

MARKER = AG.PLUGIN_MARKER
FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name
          + (("\n      " + str(detail)) if (detail and not cond) else ""))


class NoSched:
    """What `Q.answer` needs from a scheduler; the plugin answers touch none."""

    def mark_command(self, text):
        pass

    def note_set(self, *a, **k):
        pass

    def forget_set(self, *a, **k):
        pass

    def last_set(self, *a, **k):
        return None


# --------------------------------------------------------------------------
#   The sandbox: a throwaway plugin folder, run through the REAL loader
# --------------------------------------------------------------------------

class Box:
    """A throwaway `jarvis_plugins/` the real loader reads.

    `JARVIS_PLUGINS_DIR` is an absolute path that exists, which is the only
    override `jarvis_plugins.plugins_dir()` honours - so every answer here is
    read from this folder and none from the owner's own.
    """

    def __init__(self, name):
        self.root = TMP / name
        self.folder = self.root / "jarvis_plugins"
        self.folder.mkdir(parents=True, exist_ok=True)
        sys.path.insert(0, str(self.root))

    def __enter__(self):
        self.saved = os.environ.get("JARVIS_PLUGINS_DIR")
        os.environ["JARVIS_PLUGINS_DIR"] = str(self.folder)
        jarvis_plugins._reset_for_tests()
        return self

    def __exit__(self, *exc):
        if self.saved is None:
            os.environ.pop("JARVIS_PLUGINS_DIR", None)
        else:
            os.environ["JARVIS_PLUGINS_DIR"] = self.saved
        try:
            sys.path.remove(str(self.root))
        except ValueError:
            pass
        jarvis_plugins._reset_for_tests()
        return False

    def plugin(self, name, *, summary=None, enabled=None, disabled=False):
        d = self.folder / name
        d.mkdir(parents=True, exist_ok=True)
        data = {"name": name, "module": "_pc_" + name.replace("-", "_"),
                "install": "handler", "stack_order": 1,
                "summary": summary or f"the {name} module"}
        if enabled is not None:
            data["enabled"] = enabled
        (d / "plugin.json").write_text(json.dumps(data), encoding="utf-8")
        if disabled:
            (d / MARKER).write_text("", encoding="utf-8")
        (self.root / ("_pc_" + name.replace("-", "_") + ".py")).write_text(
            "def install(handler_cls, *, origin_ok, token_ok, read_body):\n"
            "    return 'on'\n", encoding="utf-8")
        return d

    def start(self):
        """Run the REAL loader, so the registry's state is the truth it is on
        the PC (an `armed` loader with `loaded` names)."""

        class Handler:
            pass

        return jarvis_plugins.install(Handler, origin_ok=lambda r: True,
                                      token_ok=lambda r: True,
                                      read_body=lambda r: b"{}")


def snapshot(root: Path) -> dict:
    """Every file under `root`, its bytes and its mtime."""
    out = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            stat = path.stat()
            out[str(path.relative_to(root))] = (path.read_bytes(), stat.st_mtime_ns)
    return out


def rows_states(box) -> dict:
    """{name: state} read back from the registry the answers use."""
    answer = AG._plugin_rows()
    return {str(p.get("name")): str(p.get("state"))
            for p in (answer.get("plugins") or [])}


# --------------------------------------------------------------------------
#   The card, stood in for exactly as the agent's own suites stand in for it
# --------------------------------------------------------------------------

class Verdict:
    """The fields `jarvis_agent._one_call` and `_a_person_said_yes` read."""

    def __init__(self, allowed=True, tier="ask", outcome="approved"):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome
        self.action = AG.PLUGIN_TOGGLE_ACTION
        self.reason = f"tier is {tier}"
        self.request_id = "req-1"


class Gate:
    """Records every card it is asked for and answers as told."""

    def __init__(self, allowed=True, tier="ask", outcome="approved"):
        self.verdict = Verdict(allowed, tier, outcome)
        self.calls = []

    def __call__(self, action, detail, prompt):
        self.calls.append({"action": action,
                           "text": str((detail or {}).get("text") or ""),
                           "prompt": prompt})
        return self.verdict

    @property
    def last(self):
        return self.calls[-1] if self.calls else {}


class NoCard(Gate):
    """A gate that must not be asked; a call is recorded and would fail a
    check that says so."""


def with_gate(gate):
    """Point the fast path's ONE gate seam at `gate`; returns a restore fn."""
    saved = Q._plugin_gate
    Q._plugin_gate = lambda: gate

    def restore():
        Q._plugin_gate = saved

    return restore


def ask(text, *, private=False):
    """One whole sentence down the public `answer()` door."""
    return Q.answer(text, sched=NoSched(), now=time.time(), private=private,
                    peer="127.0.0.1", local=True)


# --------------------------------------------------------------------------
#   1. every phrasing reaches its own intent (BITE 1)
# --------------------------------------------------------------------------

def t_each_phrasing_reaches_its_own_intent():
    want = [
        ("turn on plugin news", "plugin_on", "news"),
        ("turn on the news plugin", "plugin_on", "news"),
        ("enable the news plugin", "plugin_on", "news"),
        ("turn off plugin news", "plugin_off", "news"),
        ("turn off the news plugin", "plugin_off", "news"),
        ("disable the news plugin", "plugin_off", "news"),
        ("disable plugin notes-edit", "plugin_off", "notes-edit"),
        ("which plugins are switched off", "plugin_off_list", None),
        ("what plugins are switched off", "plugin_off_list", None),
        ("which plug-ins are switched off", "plugin_off_list", None),
        ("is plugin news on", "plugin_on_state", "news"),
        ("is the news plugin on", "plugin_on_state", "news"),
        ("is plug-in notes-edit on", "plugin_on_state", "notes-edit"),
    ]
    for text, intent, name in want:
        got = Q.match(text)
        check(f"{text!r} reaches {intent}", got is not None and got.name == intent,
              None if got is None else (got.name, got.f))
        if name is not None:
            check(f"... naming the plugin {name!r}",
                  got is not None and got.f.get("name") == name,
                  None if got is None else got.f)
    check("the two switch intents are dispatch names routed to the plugin runner",
          {"plugin_on", "plugin_off"} <= set(Q._PLUGIN_INTENTS))
    check("the two reads are dispatch names routed to the plugin runner",
          {"plugin_off_list", "plugin_on_state"} <= set(Q._PLUGIN_INTENTS))
    check("the two reads are READ-ONLY (they must not clear 'cancel that')",
          {"plugin_off_list", "plugin_on_state"} <= Q.READ_ONLY_INTENTS)
    check("the two CHANGES are deliberately NOT read-only",
          not ({"plugin_on", "plugin_off"} & Q.READ_ONLY_INTENTS))
    check("a private chat still gets the two reads from this PC",
          {"plugin_off_list", "plugin_on_state"} <= Q._PRIVATE_DETERMINISTIC_READS)
    check("... and the two changes are not answered there",
          not ({"plugin_on", "plugin_off"} & Q._PRIVATE_DETERMINISTIC_READS))


# --------------------------------------------------------------------------
#   2. the other lanes keep their own sentences, in both directions
# --------------------------------------------------------------------------

def t_the_other_lanes_keep_their_sentences():
    lanes = [
        # the TOOL-switch lane (settings_tool) and the plug-in lanes must not
        # trade sentences: pinned by intent, both ways.
        ("turn on the timer tool", "settings_tool"),
        ("turn off the timer tool", "settings_tool"),
        ("how do I install a plugin", "plugin_install"),
        ("can I install a plugin?", "plugin_install"),
        ("what plugins do you have", "plugin_list"),
        ("list my plugins", "plugin_list"),
        ("what plugins are installed?", "plugin_list"),
        ("what plugins are available?", "plugin_list"),
        ("is docker plugin installed?", "plugin_state"),
        ("what does plugin docker do?", "plugin_about"),
    ]
    for text, intent in lanes:
        got = Q.match(text)
        check(f"{text!r} still reaches {intent}",
              got is not None and got.name == intent,
              None if got is None else (got.name, got.f))
        check(f"... and is NOT one of the six new intents ({text!r})",
              got is None or got.name not in {"plugin_on", "plugin_off",
                                              "plugin_off_list",
                                              "plugin_on_state"},
              None if got is None else got.name)
    # "enable the <name> plugin" is the switch, and must not be read as the
    # install how-to; "enable a plugin" with no name keeps the install answer.
    got = Q.match("enable the news plugin")
    check("'enable the news plugin' is the switch, not plugin_install",
          got is not None and got.name == "plugin_on",
          None if got is None else got.name)
    got = Q.match("can I enable a plugin?")
    check("'can I enable a plugin?' with no name is not the switch "
          "(it keeps its own lane / the model, as before)",
          got is None or got.name != "plugin_on",
          None if got is None else (got.name, got.f))
    check("a sentence that merely mentions a plugin stays the model's",
          Q.match("remind me to turn on the plugin later") is None,
          Q.match("remind me to turn on the plugin later"))
    check("no plug-in word, no claim: 'turn on the news' stays the model's",
          Q.match("turn on the news") is None, Q.match("turn on the news"))


# --------------------------------------------------------------------------
#   3. the name is the real registry's - never a guess
# --------------------------------------------------------------------------

def t_an_unknown_name_is_refused_and_names_both():
    with Box("unknown") as box:
        box.plugin("news")
        box.plugin("notes-edit")
        box.start()
        before = snapshot(box.folder)
        gate = Gate()
        restore = with_gate(gate)
        try:
            said = Q._run_plugin_switch("plugin_on", "weather").reply
            read = Q._run_plugin_on_state("weather").reply
        finally:
            restore()
        check("an unknown switch name is refused, not guessed",
              "'weather'" in said and "no plugin called" in said, said)
        check("... and it names the real plugins",
              "news" in said and "notes-edit" in said, said)
        check("... before any card exists", gate.calls == [], gate.calls)
        check("an unknown name in the read is refused the same way",
              "'weather'" in read and "news" in read and "notes-edit" in read, read)
        check("... and nothing on disk changed", snapshot(box.folder) == before,
              sorted(snapshot(box.folder)))
        check("a space for a hyphen is the one alias: 'notes edit' finds "
              "'notes-edit'", Q._plugin_lookup("notes edit", AG._plugin_rows())[0]
              == "notes-edit", Q._plugin_lookup("notes edit", AG._plugin_rows()))


# --------------------------------------------------------------------------
#   4. enabling raises the EXISTING card (BITE 2)
# --------------------------------------------------------------------------

def t_enabling_raises_the_existing_modify_own_code_card():
    with Box("on-card") as box:
        d = box.plugin("news", summary="the news reader", disabled=True)
        box.start()
        # The plan the card must show, produced by the agent's own prepare.
        _state, plan = AG._prepare_plugin_switch({"plugin": "news", "action": "on"})
        gate = Gate()
        restore = with_gate(gate)
        try:
            got = ask("turn on plugin news")
        finally:
            restore()
        check("enabling really answered", got is not None and got.intent == "plugin_on",
              None if got is None else got.intent)
        check("enabling raised exactly ONE card", len(gate.calls) == 1, gate.calls)
        check("it is the EXISTING modify_own_code action",
              gate.last.get("action") == "modify_own_code", gate.last.get("action"))
        card = gate.last.get("text", "")
        check("the card is the agent's own words, byte for byte", card == plan,
              card[:300])
        check("the card names the plugin", "'news'" in card, card[:200])
        check("the card names the exact marker file it would remove",
              str(d / MARKER) in card, card[:400])
        check("the card says it is code that runs at start-up",
              "small program folder" in card and "starts" in card, card[:400])
        check("the card says when it lands and that Jarvis cannot restart",
              "NEXT time Jarvis starts" in card and "cannot restart" in card, card)
        check("the card says what a no means",
              "If you say no: nothing changes" in card, card[-200:])
        check("approving removed the marker", not (d / MARKER).exists())
        check("approving says it is switched back on, not running yet",
              got is not None and "switched back on" in got.reply
              and "not running yet" in got.reply,
              None if got is None else got.reply)
        check("... and the registry now reads it as not off by marker",
              (d / MARKER).exists() is False, rows_states(box))


# --------------------------------------------------------------------------
#   5. disabling is immediate, cardless, and says what it means
# --------------------------------------------------------------------------

def t_disabling_is_immediate_cardless_and_says_so():
    with Box("off-now") as box:
        d = box.plugin("news")
        box.start()
        check("the plugin starts on", rows_states(box).get("news") == "on",
              rows_states(box))
        before = snapshot(box.folder)
        gate = NoCard()
        restore = with_gate(gate)
        try:
            got = ask("turn off plugin news")
        finally:
            restore()
        said = got.reply if got is not None else ""
        check("disabling answered", got is not None and got.intent == "plugin_off",
              None if got is None else got.intent)
        check("disabling raised NO card at all", gate.calls == [], gate.calls)
        check("the loader's own marker is now in the folder", (d / MARKER).is_file())
        check("plugin.json and every other file are untouched",
              {k: v for k, v in snapshot(box.folder).items()
               if k != f"news{os.sep}{MARKER}"} == before,
              sorted(snapshot(box.folder)))
        check("the answer names the plugin", "'news'" in said, said)
        check("the answer says it will not load until it is switched back on",
              "will not load the next time Jarvis starts" in said, said)
        check("... and names the sentence that undoes it",
              '"turn the news plugin on"' in said, said)
        check("the registry reads it as switched off",
              rows_states(box).get("news") == "off", rows_states(box))
        again = Q._run_plugin_switch("plugin_off", "news").reply
        check("disabling it again changes nothing and says so",
              "already switched off" in again, again)


# --------------------------------------------------------------------------
#   6. deny changes nothing (state read back)
# --------------------------------------------------------------------------

def t_a_denied_card_changes_nothing():
    for verdict in (Verdict(allowed=False, tier="ask", outcome="denied"),
                    Verdict(allowed=False, tier="ask", outcome="timed_out")):
        with Box("denied") as box:
            d = box.plugin("news", disabled=True)
            box.start()
            before = snapshot(box.folder)
            gate = Gate()
            gate.verdict = verdict
            restore = with_gate(gate)
            try:
                got = ask("enable the news plugin")
            finally:
                restore()
            said = got.reply if got is not None else ""
            check(f"a {verdict.outcome} card is still ONE card",
                  len(gate.calls) == 1, gate.calls)
            check(f"a {verdict.outcome} card changes nothing on disk",
                  snapshot(box.folder) == before, sorted(snapshot(box.folder)))
            check(f"a {verdict.outcome} card says nothing was changed",
                  "Nothing was changed" in said, said)
            check(f"a {verdict.outcome} card says the plugin stays off",
                  "stays off" in said, said)
            check(f"the plugin is still off by the registry ({verdict.outcome})",
                  rows_states(box).get("news") == "off", rows_states(box))
            check(f"the marker is still there ({verdict.outcome})",
                  (d / MARKER).is_file())


def t_a_loosened_tier_still_cannot_switch_a_plugin_on():
    """The belt: `modify_own_code` is "ask" in the shipped file. If a settings
    file ever loosened it, an allowed verdict with nobody asked must not write."""
    with Box("loosened") as box:
        d = box.plugin("news", disabled=True)
        box.start()
        before = snapshot(box.folder)
        gate = Gate(allowed=True, tier="auto", outcome="auto")
        restore = with_gate(gate)
        try:
            got = ask("turn on plugin news")
        finally:
            restore()
        said = got.reply if got is not None else ""
        check("allowed with nobody asked: the plugin stays off",
              (d / MARKER).is_file() and snapshot(box.folder) == before,
              sorted(snapshot(box.folder)))
        check("... and the answer names modify_own_code and that nobody was asked",
              "modify_own_code" in said and "nobody was asked" in said, said)


# --------------------------------------------------------------------------
#   7. the two reads answer from the live registry, and write nothing
# --------------------------------------------------------------------------

def t_the_reads_answer_from_the_live_registry():
    with Box("reads") as box:
        box.plugin("news")
        box.plugin("quiet", disabled=True)
        box.plugin("handoff", enabled=False)
        box.start()
        before = snapshot(box.folder)
        gate = NoCard()
        restore = with_gate(gate)
        try:
            off_list = ask("which plugins are switched off")
            news = ask("is plugin news on")
            quiet = ask("is plugin quiet on")
            handoff = ask("is the handoff plugin on")
        finally:
            restore()
        check("the complement answered", off_list is not None
              and off_list.intent == "plugin_off_list",
              None if off_list is None else off_list.intent)
        text = off_list.reply if off_list is not None else ""
        check("the complement has its COUNT", "2 of the 3 plug-ins" in text, text)
        check("... and names the two that are off, and only those",
              "quiet" in text and "handoff" in text and "news" not in text, text)
        check("... and says how to switch one back on",
              'turn on plugin <name>' in text, text)
        check("the state read says YES for a loaded plugin",
              news is not None and "Yes" in news.reply and "'news'" in news.reply,
              None if news is None else news.reply)
        check("... and read-only, from the live registry",
              news is not None and news.intent == "plugin_on_state")
        check("a marker-off plugin says no, with the loader's own reason",
              quiet is not None and "No" in quiet.reply
              and "disabled marker" in quiet.reply, None if quiet is None else quiet.reply)
        check("a plugin off in its own plugin.json says so",
              handoff is not None and "No" in handoff.reply
              and "plugin.json" in handoff.reply and "hand edit" in handoff.reply,
              None if handoff is None else handoff.reply)
        check("NO card was raised by either read", gate.calls == [], gate.calls)
        check("neither read wrote, touched or deleted one file",
              snapshot(box.folder) == before, sorted(snapshot(box.folder)))
        check("both reads answer deterministically in a private chat",
              ask("which plugins are switched off", private=True) is not None
              and ask("is plugin news on", private=True) is not None)
        priv = ask("turn on plugin news", private=True)
        check("a CHANGE is refused in a private chat, not carded",
              priv is not None and priv.intent == "plugin_on"
              and "private" in priv.reply.lower(),
              None if priv is None else priv.reply)


def t_the_complement_is_honest_when_nothing_is_installed():
    with Box("empty") as box:
        box.start()
        said = Q._run_plugin_off_list().reply
        check("an empty plugin folder says there are no plug-ins, not '0 of 0'",
              "There are no plug-ins" in said, said)
        check("... and says none is switched off", "none is switched off" in said,
              said)
        shutil.rmtree(box.folder)
        gone = Q._run_plugin_off_list().reply
        check("a missing plugin folder names the folder, not an empty list",
              "There is no plug-in folder" in gone
              and str(box.folder) in gone, gone)


# --------------------------------------------------------------------------
#   8. the switch is the agent's own code, pinned structurally
# --------------------------------------------------------------------------

def t_the_switch_is_the_agents_own_code():
    src = (HERE / "jarvis_quick.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    mine = [name for name in fns if name.startswith("_plugin_")
            or name in ("_run_plugin_switch", "_run_plugin_off_list",
                        "_run_plugin_on_state", "_plugin_switch_ask")]
    check("the plugin fast-path functions are really there", len(mine) >= 8,
          sorted(mine))
    called = set()
    for name in mine:
        for node in ast.walk(fns[name]):
            if isinstance(node, ast.Call):
                f = node.func
                called.add(getattr(f, "id", None) or getattr(f, "attr", None))
    for wanted in ("_prepare_plugin_switch", "_execute_plugin_switch",
                   "_plugin_apply"):
        check(f"the fast path calls jarvis_agent.{wanted}", wanted in called,
              sorted(c for c in called if c))
    check("the fast path's gate IS the agent's own fail-closed wrapper",
          Q._plugin_gate() is AG._gate_check)
    writes = []
    for name in mine:
        for node in ast.walk(fns[name]):
            if isinstance(node, ast.Call):
                f = node.func
                attr = getattr(f, "attr", None)
                func = getattr(f, "id", None)
                if attr in ("unlink", "rmtree", "rmdir", "removedirs", "renames",
                            "move", "mkdir", "makedirs") or func == "open":
                    writes.append((name, attr or func))
    check("no plugin fast-path function writes, deletes or moves a file itself",
          writes == [], writes)
    check("... and the quick lane defines no marker name of its own",
          not hasattr(Q, "PLUGIN_MARKER"))


# --------------------------------------------------------------------------
#   9. the chat request is not held open, and the approved write still lands
# --------------------------------------------------------------------------

def t_a_waiting_card_does_not_hold_the_request_open():
    with Box("slow-card") as box:
        d = box.plugin("news", disabled=True)
        box.start()
        started = time.time()

        class Slow(Gate):
            def __call__(self, action, detail, prompt):
                time.sleep(2.5)
                return super().__call__(action, detail, prompt)

        gate = Slow()
        restore = with_gate(gate)
        try:
            # The RUNNER, not nswer(): nswer() also records the change
            # journal for any non-read-only intent, and that is not the thing
            # this row is about.
            got = Q._run_plugin_switch("plugin_on", "news")
        finally:
            restore()
        took = time.time() - started
        check("a card that has not been answered answers 'waiting' at once",
              got is not None and "One approval card is waiting" in got.reply,
              None if got is None else got.reply)
        check(f"... without holding the chat request open ({took:.2f}s)",
              took < 2.2, took)
        check("... and nothing has been written while the card waits",
              (d / MARKER).is_file())
        deadline = time.time() + 10
        while time.time() < deadline and not gate.calls:
            time.sleep(0.05)
        deadline = time.time() + 10
        while time.time() < deadline and (d / MARKER).exists():
            time.sleep(0.05)
        check("the approved card still switches the plugin on afterwards",
              not (d / MARKER).exists(), sorted(snapshot(box.folder)))


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"\n--- {name} ---")
            try:
                fn()
            except Exception:
                FAILED.append(name)
                print(f"FAIL {name} raised")
                traceback.print_exc()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
