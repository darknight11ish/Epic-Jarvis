"""The drop-in plugins, by chat: list them, switch ONE on or off (2026-11-02).

    python -B backend/test_plugin_switch.py

THE OWNER'S DECISION: "Jarvis may list plugins and turn them on/off by chat, one
card per change."  This suite proves the two tools that do it, and - just as
importantly - what they may NOT do.

WHAT IS PROVED HERE, and each one is a different way the feature could lie:

  * THE LIST IS TRUE. Every folder in the plugin folder is named with its state
    and the reason it is off - on, switched off by the `disabled` marker,
    switched off in its own plugin.json, failed to load (the loader's own
    reason included), a broken plugin.json, added after Jarvis started - and a
    plugin that loaded and whose folder has gone since is reported instead of
    silently disappearing. A missing plugin folder says so.

  * THE LIST WRITES NOTHING. The whole sandbox is snapshotted (every file, its
    bytes and its mtime) before and after: a read that creates, changes or
    deletes one file fails here.

  * OFF IS IMMEDIATE AND CARDLESS. One named plugin, one marker file, no gate
    call at all - the project's own on/off rule ("turning it off is immediate").

  * ON IS ONE CARD. It goes through the real `_one_call` under the EXISTING
    `modify_own_code` action, the card names the plugin and the exact file it
    would remove, and a denied card changes nothing on disk.

  * IT IS HONEST ABOUT THE MOMENT. Both answers say the change lands the next
    time Jarvis starts and that Jarvis cannot restart itself. Nothing here
    restarts anything.

  * IT CANNOT GO BULK, AND IT CANNOT DELETE. The schema has no list, so a call
    naming two plugins is refused before anything is prepared; a call with an
    extra argument is refused; and after a full off/on cycle the plugin folder
    holds exactly the files it held before, plus or minus the one marker.

  * THE CATALOGUE IS ONE PLUGIN TOO. The two tools are in the tool contract,
    in exactly one short-list group, classified as a read and an action, in the
    shipped `[tools].enabled` default list, and each description is inside the
    300-token budget.

No model runs, no network, no real approval card, and the owner's own plugin
folder is never read or written: `JARVIS_PLUGINS_DIR` points at a throwaway
folder for the whole run, and it is removed on the way out.
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Hermetic before any shipped module reads a config, the same shape every other
# suite uses: a run on the owner's PC must not read or write the real state.
TMP = Path(tempfile.mkdtemp(prefix="jarvis-plugin-switch-"))
CFG = TMP / "config"
CFG.mkdir(parents=True, exist_ok=True)
os.environ["OPENJARVIS_CONFIG_DIR"] = str(CFG)
os.environ["JARVIS_CONFIG_DIR"] = str(CFG)
os.environ["JARVIS_LOG_DIR"] = str(TMP / "logs")
os.environ.pop("JARVIS_FRAMEWORK_TOML", None)

sys.path.insert(0, str(HERE))
sys.path.append(str(HERE / "rebuilt"))
sys.path.append(str(HERE.parent / "jarvis-backend"))

import jarvis_agent as AG  # noqa: E402
import jarvis_plugins  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(("ok    " if cond else "FAIL  ") + name
          + (("\n      " + str(detail)) if (detail and not cond) else ""))


# --------------------------------------------------------------------------
#   The sandbox: a throwaway plugin folder, and modules beside it on sys.path
# --------------------------------------------------------------------------

class Box:
    """A throwaway `jarvis_plugins/` plus the stand-in modules a plugin.json
    can name. `JARVIS_PLUGINS_DIR` points here for the whole run, so the real
    path `jarvis_plugins.plugins_dir()` returns is this one (an absolute path
    that exists is the only override the loader honours)."""

    def __init__(self, name):
        self.root = TMP / name
        self.folder = self.root / "jarvis_plugins"
        self.folder.mkdir(parents=True, exist_ok=True)
        sys.path.insert(0, str(self.root))

    def __enter__(self):
        self.saved_env = os.environ.get("JARVIS_PLUGINS_DIR")
        os.environ["JARVIS_PLUGINS_DIR"] = str(self.folder)
        jarvis_plugins._reset_for_tests()
        return self

    def __exit__(self, *exc):
        if self.saved_env is None:
            os.environ.pop("JARVIS_PLUGINS_DIR", None)
        else:
            os.environ["JARVIS_PLUGINS_DIR"] = self.saved_env
        try:
            sys.path.remove(str(self.root))
        except ValueError:
            pass
        jarvis_plugins._reset_for_tests()
        return False

    def plugin(self, name, *, order=1, summary=None, manifest=None,
               manifest_text=None, disabled=False, enabled=None, body=None):
        d = self.folder / name
        d.mkdir(parents=True, exist_ok=True)
        if manifest_text is not None:
            (d / "plugin.json").write_text(manifest_text, encoding="utf-8")
        else:
            data = {"name": name, "module": f"_sw_{name}", "install": "handler",
                    "stack_order": order, "summary": summary or f"the {name} module"}
            if enabled is not None:
                data["enabled"] = enabled
            if manifest:
                data.update(manifest)
            (d / "plugin.json").write_text(json.dumps(data), encoding="utf-8")
        if disabled:
            (d / PLUGIN_MARKER).write_text("", encoding="utf-8")
        if body is not None:
            (self.root / f"_sw_{name}.py").write_text(body, encoding="utf-8")
        return d

    def module(self, name, route="/api/anything"):
        (self.root / f"_sw_{name}.py").write_text(
            "def install(handler_cls, *, origin_ok, token_ok, read_body):\n"
            "    return 'on'\n", encoding="utf-8")

    def start(self):
        """Run the REAL loader, so `status()` is the truth it is on the PC."""

        class Handler:
            pass

        return jarvis_plugins.install(Handler, origin_ok=lambda r: True,
                                      token_ok=lambda r: True,
                                      read_body=lambda r: b"{}")


PLUGIN_MARKER = "disabled"


# --------------------------------------------------------------------------
#   Driving ONE tool call through the REAL _one_call
# --------------------------------------------------------------------------

class Out:
    """What `_one_call` needs from the app it is answering to."""

    gone = False

    def __init__(self):
        self.statuses = []

    def set_status(self, status):
        self.statuses.append(status)

    def card_answered(self, verdict):
        return None


class Verdict:
    def __init__(self, allowed=True, tier="ask", outcome="approved"):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome
        self.action = None
        self.reason = f"tier is {tier}"
        self.request_id = None


class Gate:
    """Records every question it is asked, and answers as told."""

    def __init__(self, allowed=True, tier="ask", outcome="approved"):
        self.allowed, self.tier, self.outcome = allowed, tier, outcome
        self.calls = []

    def __call__(self, action, detail, prompt):
        self.calls.append({"action": action, "text": (detail or {}).get("text", ""),
                           "prompt": prompt})
        return Verdict(self.allowed, self.tier, self.outcome)

    @property
    def last(self):
        return self.calls[-1] if self.calls else {}


def drive(name, args, *, gate=None, watch=None):
    """One tool call through the real `_one_call`. Returns (gate, convo, steps)."""
    gate = gate or Gate()
    convo, steps = [], []
    AG._one_call({"id": "1", "function": {"name": name,
                                          "arguments": json.dumps(args)}},
                 [name], convo, steps, gate, None, Out(),
                 lambda *a, **k: None, watch=watch or AG._TurnWatch())
    return gate, convo, steps


def result(convo):
    """The tool result the model reads, as a dict."""
    return json.loads(convo[-1]["content"]) if convo else {}


def snapshot(root: Path) -> dict:
    """Every file under `root`: its bytes and its mtime - so a read that
    writes, touches or deletes ONE file is visible."""
    out = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            stat = path.stat()
            out[str(path.relative_to(root))] = (path.read_bytes(), stat.st_mtime_ns)
    return out


# --------------------------------------------------------------------------
#   1. the tool contract
# --------------------------------------------------------------------------

def t_the_two_tools_are_in_the_contract():
    for name in (AG.PLUGIN_LIST_TOOL, AG.PLUGIN_SWITCH_TOOL):
        check(f"{name} is a real tool", name in AG.TOOLS)
    check("the list tool is plugin_list, the switch is plugin_switch",
          AG.PLUGIN_LIST_TOOL == "plugin_list" and AG.PLUGIN_SWITCH_TOOL == "plugin_switch")
    listed = AG.TOOLS[AG.PLUGIN_LIST_TOOL]
    switch = AG.TOOLS[AG.PLUGIN_SWITCH_TOOL]
    check("the list tool takes no arguments at all",
          listed.parameters.get("properties") == {} and not listed.parameters.get("required"))
    props = switch.parameters.get("properties") or {}
    check("the switch takes ONE plugin name and an on/off action",
          set(props) == {"plugin", "action"}
          and props["action"].get("enum") == ["on", "off"]
          and switch.parameters.get("required") == ["plugin", "action"], switch.parameters)
    check("no array anywhere in the switch's schema: there is no bulk shape",
          "array" not in json.dumps(switch.parameters))
    for name, tool in ((AG.PLUGIN_LIST_TOOL, listed), (AG.PLUGIN_SWITCH_TOOL, switch)):
        tokens = AG.estimate_tokens(tool.schema())
        check(f"{name}'s text is inside the per-tool budget (300; it is {tokens})",
              tokens <= 300, tokens)
        groups = [g for g, _w, members in AG.TOOL_GROUPS if name in members]
        check(f"{name} is in exactly one short-list group ({groups})",
              groups == ["settings"], groups)
    check("the switch only ever runs on a person's yes",
          AG.PLUGIN_SWITCH_TOOL in AG.NEEDS_A_PERSON)
    check("neither tool's result is marked as outside text",
          AG.PLUGIN_LIST_TOOL in AG._NOT_READING
          and AG.PLUGIN_SWITCH_TOOL in AG._NOT_READING)
    check("the switch is decided under the EXISTING modify_own_code action",
          AG.PLUGIN_TOGGLE_ACTION == "modify_own_code")
    check("the switch declares a gate lookup key the published table has",
          switch.gate_lookup_name({}) == "skill_manage")
    check("the tool-diet can find both (every tool has hints)",
          all(AG.TOOL_HINTS.get(n) for n in (AG.PLUGIN_LIST_TOOL, AG.PLUGIN_SWITCH_TOOL)))


def t_both_tools_ship_in_the_default_list():
    toml = (HERE / "rebuilt" / "jarvis-framework.toml").read_text(encoding="utf-8")
    line = next((ln for ln in toml.splitlines() if ln.startswith("enabled = [")), "")
    for name in (AG.PLUGIN_LIST_TOOL, AG.PLUGIN_SWITCH_TOOL):
        check(f"{name} is in the shipped [tools].enabled list", f'"{name}"' in line, line)
    check("... and therefore a fresh install offers it",
          AG.PLUGIN_LIST_TOOL in AG.offered_tools({AG.PLUGIN_LIST_TOOL, AG.PLUGIN_SWITCH_TOOL})
          and AG.PLUGIN_SWITCH_TOOL in AG.offered_tools({AG.PLUGIN_LIST_TOOL,
                                                         AG.PLUGIN_SWITCH_TOOL}))


# --------------------------------------------------------------------------
#   2. the list: true, complete, and read-only
# --------------------------------------------------------------------------

def t_the_list_names_every_plugin_and_says_why_it_is_off():
    with Box("all-states") as box:
        box.plugin("onone", body=None)
        box.module("onone")
        box.plugin("markeroff", disabled=True)
        box.plugin("manifestoff", enabled=False)
        box.plugin("broken", manifest_text="{not json")
        box.plugin("failedload")                      # module absent on purpose
        box.start()
        # ... and one added AFTER the loader ran.
        box.plugin("addedlater")
        rows = AG._plugin_rows()
        check("the list says it worked", rows.get("ok") is True, rows)
        check("the folder it read is named once", rows.get("folder") == str(box.folder),
              rows.get("folder"))
        by = {p["name"]: p for p in rows.get("plugins") or []}
        check("every folder is named", set(by) == {"onone", "markeroff", "manifestoff",
                                                   "broken", "failedload", "addedlater"},
              sorted(by))
        check("a loaded plugin is on", by.get("onone", {}).get("on") is True
              and by["onone"]["state"] == "on", by.get("onone"))
        check("a `disabled` marker is off, and the reason names the marker",
              by.get("markeroff", {}).get("on") is False
              and "disabled marker" in by["markeroff"]["why"], by.get("markeroff"))
        check("`enabled: false` is off, and the reason says it is a hand edit in "
              "its own plugin.json",
              by.get("manifestoff", {}).get("on") is False
              and "plugin.json" in by["manifestoff"]["why"]
              and "hand edit" in by["manifestoff"]["why"], by.get("manifestoff"))
        check("a broken plugin.json is reported, with its own reason",
              by.get("broken", {}).get("state") == "broken"
              and "plugin.json" in by["broken"]["why"], by.get("broken"))
        check("a failed load is reported, with the loader's own reason",
              by.get("failedload", {}).get("state") == "failed"
              and "did not load" in by["failedload"]["why"], by.get("failedload"))
        check("a folder added after start is named as not loaded yet",
              by.get("addedlater", {}).get("state") == "new"
              and "after Jarvis started" in by["addedlater"]["why"],
              by.get("addedlater"))
        check("the counts are the plugins' own", rows["counts"] == {"on": 1, "off": 5},
              rows["counts"])
        check("the answer says when a change would take effect",
              "next time Jarvis starts" in rows["note"]
              and "cannot restart" in rows["note"], rows["note"])


def t_the_list_touches_nothing_on_disk():
    with Box("readonly") as box:
        box.plugin("news", body=None)
        box.module("news")
        box.plugin("old", disabled=True)
        box.start()
        before = snapshot(box.folder)
        gate, convo, steps = drive(AG.PLUGIN_LIST_TOOL, {})
        after = snapshot(box.folder)
        check("the list answers", result(convo).get("ok") is True, convo)
        check("the list raised no card", gate.calls == [], gate.calls)
        check("the list wrote, touched or deleted nothing", before == after,
              sorted(set(before) ^ set(after)))
        check("the list is one step that ran, with no card needed",
              steps == [{"tool": AG.PLUGIN_LIST_TOOL, "ran": True, "ok": True,
                         "outcome": "no card needed"}], steps)


def t_a_missing_plugin_folder_reports_itself():
    with Box("no-folder") as box:
        shutil.rmtree(box.folder)
        rows = AG._plugin_rows()
        check("no folder: the answer is still a list, not an error",
              rows.get("ok") is True and rows.get("folder_exists") is False, rows)
        check("no folder: it says there is no plugin folder, and where",
              "no plugin folder" in rows.get("note", "")
              and str(box.folder) in rows.get("note", ""), rows.get("note"))
        check("no folder: no plugins are invented", rows.get("plugins") == [], rows)
        gate, convo, _steps = drive(AG.PLUGIN_LIST_TOOL, {})
        check("no folder: the tool still answers without a card",
              result(convo).get("ok") is True and gate.calls == [], convo)


def t_a_plugin_whose_folder_has_gone_is_still_reported():
    with Box("stale") as box:
        box.plugin("news")
        box.module("news")
        box.start()
        check("it starts on", AG._plugin_rows()["counts"]["on"] == 1)
        shutil.rmtree(box.folder / "news")
        rows = AG._plugin_rows()
        gone = [p for p in rows["plugins"] if p["name"] == "news"]
        check("a loaded plugin whose folder has gone is still listed",
              len(gone) == 1 and gone[0]["state"] == "gone", rows["plugins"])
        check("... and the reason says it keeps running until a restart",
              "keeps running until Jarvis restarts" in gone[0]["why"], gone[0])
        check("... and it is not counted as failed or off-and-forgotten",
              rows["counts"]["on"] == 1, rows["counts"])


# --------------------------------------------------------------------------
#   3. switching OFF: immediate, one file, never a card
# --------------------------------------------------------------------------

def t_off_is_immediate_and_needs_no_card():
    with Box("off") as box:
        box.plugin("news")
        box.module("news")
        box.start()
        before = snapshot(box.folder)
        gate, convo, steps = drive(AG.PLUGIN_SWITCH_TOOL,
                                   {"plugin": "news", "action": "off"})
        got = result(convo)
        check("off: it worked", got.get("ok") is True and got.get("changed") is True, got)
        check("off: NO card was raised", gate.calls == [], gate.calls)
        check("off: the loader's own marker is now in the folder",
              (box.folder / "news" / PLUGIN_MARKER).is_file())
        check("off: plugin.json and every other file are untouched",
              {k: v for k, v in snapshot(box.folder).items()
               if k != f"news{os.sep}{PLUGIN_MARKER}"} == before,
              sorted(snapshot(box.folder)))
        check("off: the answer says it lands at the next start, and that Jarvis "
              "cannot restart itself",
              "next time Jarvis starts" in got.get("message", "")
              and "cannot restart" in got.get("message", ""), got.get("message"))
        check("off: the loader would now skip it",
              [p for p in AG._plugin_rows()["plugins"] if p["name"] == "news"][0]["state"]
              == "off")
        check("off: it is one step that ran with no card",
              steps == [{"tool": AG.PLUGIN_SWITCH_TOOL, "ran": True, "ok": True,
                         "outcome": "no card needed"}], steps)


def t_off_again_is_a_plain_answer_with_no_write():
    with Box("off-twice") as box:
        box.plugin("news", disabled=True)
        box.start()
        before = snapshot(box.folder)
        gate, convo, _steps = drive(AG.PLUGIN_SWITCH_TOOL,
                                    {"plugin": "news", "action": "off"})
        got = result(convo)
        check("already off: no card, nothing changed", gate.calls == []
              and got.get("ok") is True and got.get("changed") is False, (gate.calls, got))
        check("already off: the disk is byte-for-byte what it was",
              snapshot(box.folder) == before)
        check("already off: it says so plainly",
              "already switched off" in got.get("message", ""), got.get("message"))


# --------------------------------------------------------------------------
#   4. switching ON: ONE modify_own_code card, and a denial changes nothing
# --------------------------------------------------------------------------

def t_on_is_one_card_under_the_existing_action():
    with Box("on-card") as box:
        box.plugin("news", disabled=True, summary="the news reader")
        box.start()
        gate = Gate(allowed=True, tier="ask", outcome="approved")
        convo, steps = [], []
        AG._one_call({"id": "1", "function": {
            "name": AG.PLUGIN_SWITCH_TOOL,
            "arguments": json.dumps({"plugin": "news", "action": "on"})}},
            [AG.PLUGIN_SWITCH_TOOL], convo, steps, gate, None, Out(),
            lambda *a, **k: None, watch=AG._TurnWatch())
        check("on: exactly ONE card was raised", len(gate.calls) == 1, gate.calls)
        check("on: it is the EXISTING modify_own_code action",
              gate.last.get("action") == "modify_own_code", gate.last.get("action"))
        card = gate.last.get("text", "")
        check("on: the card names the plugin", "'news'" in card, card[:200])
        check("on: the card names the exact file it would remove",
              str(box.folder / "news" / PLUGIN_MARKER) in card, card[:400])
        check("on: the card says the plugin is code that runs at start-up",
              "program folder" in card and "starts" in card, card[:400])
        check("on: the card says when it takes effect and that Jarvis cannot restart",
              "NEXT time Jarvis starts" in card and "cannot restart" in card, card)
        check("on: the card says what a no means",
              "If you say no: nothing changes" in card, card[-200:])
        got = result(convo)
        check("on, approved: the marker is gone", not (box.folder / "news"
                                                       / PLUGIN_MARKER).exists())
        check("on, approved: plugin.json is untouched",
              (box.folder / "news" / "plugin.json").is_file())
        check("on, approved: the answer says it is not running until the next start",
              got.get("ok") is True and "next time Jarvis starts" in got.get("message", "")
              and "not running yet" in got.get("message", ""), got)
        check("on: the step records the card's outcome",
              steps and steps[-1].get("outcome") == "approved", steps)


def t_a_denied_on_card_changes_nothing():
    with Box("on-denied") as box:
        box.plugin("news", disabled=True)
        box.start()
        before = snapshot(box.folder)
        gate = Gate(allowed=False, tier="ask", outcome="denied")
        convo, steps = [], []
        AG._one_call({"id": "1", "function": {
            "name": AG.PLUGIN_SWITCH_TOOL,
            "arguments": json.dumps({"plugin": "news", "action": "on"})}},
            [AG.PLUGIN_SWITCH_TOOL], convo, steps, gate, None, Out(),
            lambda *a, **k: None, watch=AG._TurnWatch())
        check("a denied card raises one card", len(gate.calls) == 1, gate.calls)
        check("a denied card changes nothing on disk", snapshot(box.folder) == before)
        check("a denied card says refused, and why",
              result(convo).get("ok") is False
              and "refused" in result(convo).get("error", ""), result(convo))
        check("... and the plugin is still off",
              [p for p in AG._plugin_rows()["plugins"] if p["name"] == "news"][0]["state"]
              == "off")


def t_a_timed_out_card_changes_nothing_either():
    with Box("on-timeout") as box:
        box.plugin("news", disabled=True)
        box.start()
        before = snapshot(box.folder)
        gate = Gate(allowed=False, tier="ask", outcome="timed_out")
        convo, _steps = [], []
        AG._one_call({"id": "1", "function": {
            "name": AG.PLUGIN_SWITCH_TOOL,
            "arguments": json.dumps({"plugin": "news", "action": "on"})}},
            [AG.PLUGIN_SWITCH_TOOL], convo, [], gate, None, Out(),
            lambda *a, **k: None, watch=AG._TurnWatch())
        check("a timed-out card changes nothing", snapshot(box.folder) == before)
        check("a timed-out card is not a yes", result(convo).get("ok") is False,
              result(convo))


def t_a_loosened_tier_still_cannot_switch_a_plugin_on():
    """The belt: `modify_own_code` is "ask" in the shipped file, and if someone
    ever loosens it, `NEEDS_A_PERSON` refuses an allowed verdict nobody said yes
    to. Nothing is written."""
    with Box("on-loosened") as box:
        box.plugin("news", disabled=True)
        box.start()
        before = snapshot(box.folder)
        gate = Gate(allowed=True, tier="auto", outcome="auto")
        convo, _steps = [], []
        AG._one_call({"id": "1", "function": {
            "name": AG.PLUGIN_SWITCH_TOOL,
            "arguments": json.dumps({"plugin": "news", "action": "on"})}},
            [AG.PLUGIN_SWITCH_TOOL], convo, [], gate, None, Out(),
            lambda *a, **k: None, watch=AG._TurnWatch())
        got = result(convo)
        check("allowed with nobody asked: refused", got.get("ok") is False, got)
        check("... and nothing was written", snapshot(box.folder) == before)
        check("... and the answer names the action and that nobody was asked",
              "modify_own_code" in got.get("error", "")
              and "nobody was asked" in got.get("error", ""), got.get("error"))


# --------------------------------------------------------------------------
#   5. names it cannot know: refused in plain words, before any card
# --------------------------------------------------------------------------

def t_an_unknown_name_is_refused_with_a_plain_sentence():
    with Box("unknown") as box:
        box.plugin("news", disabled=True)
        box.start()
        before = snapshot(box.folder)
        gate, convo, steps = drive(AG.PLUGIN_SWITCH_TOOL,
                                   {"plugin": "weather", "action": "on"})
        got = result(convo)
        check("unknown name: no card is raised", gate.calls == [], gate.calls)
        check("unknown name: it is refused, not guessed",
              got.get("ok") is False and "there is no plugin called 'weather'" in got.get(
                  "error", ""), got)
        check("unknown name: the real names are offered",
              "news" in got.get("error", ""), got.get("error"))
        check("unknown name: nothing on disk changed", snapshot(box.folder) == before)
        check("unknown name: the step is a refusal",
              steps and steps[-1].get("outcome") == "refused", steps)


def t_a_path_or_a_blank_is_not_a_plugin_name():
    with Box("badnames") as box:
        box.plugin("news", disabled=True)
        box.start()
        for bad in ("../news", "..\\news", "", "   ", ".", "..", "a" * 80):
            _state, problem = AG._plugin_check(bad, box.folder)
            check(f"{bad!r} is not a plugin name ({problem[:60]!r})", bool(problem), problem)


# --------------------------------------------------------------------------
#   6. no bulk, and nothing is ever deleted
# --------------------------------------------------------------------------

def t_there_is_no_bulk_path():
    with Box("bulk") as box:
        box.plugin("one", disabled=True)
        box.plugin("two", disabled=True)
        box.start()
        before = snapshot(box.folder)
        for args in ({"action": "on", "plugins": ["one", "two"]},
                     {"action": "on", "plugin": "one", "plugin2": "two"},
                     {"action": "on", "plugin": ["one", "two"]},
                     {"action": "on", "plugin": "one", "all": True}):
            gate, convo, _steps = drive(AG.PLUGIN_SWITCH_TOOL, args)
            got = result(convo)
            check(f"refused before anything is asked: {sorted(args)}",
                  got.get("ok") is False and gate.calls == [], (args, got, gate.calls))
        check("no bulk call wrote one byte", snapshot(box.folder) == before)
        check("... and both plugins are still off",
              all(p["on"] is False for p in AG._plugin_rows()["plugins"]))


def t_nothing_is_ever_deleted():
    """A full cycle - off, on, off - leaves the folder holding exactly the files
    it held before, plus or minus the ONE marker. And the code that does it has
    no delete, move or rename of a folder in it."""
    with Box("no-delete") as box:
        d = box.plugin("news", summary="the news reader")
        (d / "README.md").write_text("a plugin's own readme", encoding="utf-8")
        (d / "helper.py").write_text("# a helper the module imports\n", encoding="utf-8")
        box.module("news")
        box.start()
        before = snapshot(box.folder)
        for action in ("off", "on", "off"):
            gate, convo, _steps = drive(AG.PLUGIN_SWITCH_TOOL,
                                        {"plugin": "news", "action": action},
                                        gate=Gate())
            check(f"{action}: the switch worked", result(convo).get("ok") is True,
                  result(convo))
        after = snapshot(box.folder)
        check("every original file, byte for byte, is still there",
              {k: v for k, v in before.items()} ==
              {k: v for k, v in after.items() if k != f"news{os.sep}{PLUGIN_MARKER}"},
              sorted(set(before) ^ set(after)))
        check("the plugin folder itself is still there", d.is_dir())
        check("one cycle's difference is exactly the marker",
              set(after) - set(before) == {f"news{os.sep}{PLUGIN_MARKER}"},
              sorted(set(after) - set(before)))

    src = (HERE / "jarvis_agent.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    banned = {"rmtree", "rmdir", "renames", "move", "removedirs"}
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = getattr(f, "id", None) or getattr(f, "attr", None)
            if name in banned:
                used.add(name)
    check("jarvis_agent.py never removes, moves or renames a folder", not used, sorted(used))
    plugin_fns = {n.name: n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name.startswith("_plugin")}
    check("the plugin section is really there to check", len(plugin_fns) >= 6,
          sorted(plugin_fns))
    deletes = []
    for name, fn in plugin_fns.items():
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "unlink":
                deletes.append(name)
    check("the ONLY delete in the plugin code is the marker's removal",
          deletes == ["_plugin_apply"], deletes)


def t_a_plugin_off_in_its_own_manifest_is_not_rewritten():
    with Box("manifest-off") as box:
        d = box.plugin("quiet", enabled=False)
        box.start()
        before = snapshot(box.folder)
        for action in ("on", "off"):
            gate, convo, _steps = drive(AG.PLUGIN_SWITCH_TOOL,
                                        {"plugin": "quiet", "action": action})
            got = result(convo)
            check(f"manifest-off, {action}: no card", gate.calls == [], gate.calls)
            check(f"manifest-off, {action}: it says the plugin is off in its own "
                  f"plugin.json", "plugin.json" in (got.get("message") or ""), got)
        check("manifest-off: plugin.json was not rewritten", snapshot(box.folder) == before)
        check("... and no marker was added",
              not (d / PLUGIN_MARKER).exists())


def t_a_broken_plugin_cannot_be_switched():
    with Box("broken-switch") as box:
        box.plugin("bad", manifest_text="{not json")
        box.start()
        for action in ("on", "off"):
            gate, convo, _steps = drive(AG.PLUGIN_SWITCH_TOOL,
                                        {"plugin": "bad", "action": action})
            got = result(convo)
            check(f"broken manifest, {action}: refused with no card",
                  got.get("ok") is False and gate.calls == [], (got, gate.calls))
            check(f"broken manifest, {action}: the reason names plugin.json",
                  "plugin.json" in got.get("error", ""), got.get("error"))


# --------------------------------------------------------------------------
#   7. the loader is missing: every door says so, in words
# --------------------------------------------------------------------------

def t_without_the_loader_both_tools_say_so():
    saved = AG._plugin_loader
    AG._plugin_loader = lambda: None
    try:
        rows = AG._plugin_rows()
        check("no loader: the list is a plain error, not a crash",
              rows.get("ok") is False and "jarvis_plugins.py" in rows.get("error", ""),
              rows)
        gate, convo, _steps = drive(AG.PLUGIN_SWITCH_TOOL,
                                    {"plugin": "news", "action": "on"})
        check("no loader: the switch is refused with no card",
              gate.calls == [] and "jarvis_plugins.py" in result(convo).get("error", ""),
              (gate.calls, result(convo)))
    finally:
        AG._plugin_loader = saved


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
