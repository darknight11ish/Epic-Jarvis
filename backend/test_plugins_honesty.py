#!/usr/bin/env python3
"""Plug-in honesty (2026-10-31).

The owner asked "what plug-ins do you have integrated into you?" and the model
answered that it had no plug-ins, only built-in capabilities. False: the loader
(backend/jarvis_plugins.py) imports every folder in jarvis_plugins\ beside
jarvis_hud.py and calls its own install(); plugins/ready/ holds 45 drop-in
modules (plugins/loader/README.md documents the mechanism, scripts/add-plugin.ps1
is the door). This suite pins the catalogue to those folders and the answers to
a fake installed state, so a plug-in cannot silently vanish from the reply.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import jarvis_quick as Q  # noqa: E402

PASSED, FAILED = [], []
READY = sorted(p.name for p in (ROOT / "plugins" / "ready").iterdir() if p.is_dir())


class NoSched:
    def mark_command(self, text):
        pass

    def note_set(self, *a, **k):
        pass

    def last_set(self, *a, **k):
        return None


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def ask(text, surface="hud"):
    return Q.answer(text, sched=NoSched(), now=1793505565.0, peer="127.0.0.1",
                    local=True, client_surface=surface)


def test_catalogue_is_the_real_ready_list():
    check("there are 45 ready plug-in folders", len(READY) == 45, str(len(READY)))
    check("the fast path's names are plugins/ready's folders",
          sorted(Q._plugin_names()) == READY, str(Q._plugin_names()[:5]) + " vs " + str(READY[:5]))
    check("every catalogue name is a real folder (no invented plug-in)",
          all(n in READY for n in Q._plugin_names()))
    check("every catalogue entry has a one-line purpose",
          all(purpose and len(purpose) > 5 for _n, purpose in Q.PLUGIN_CATALOGUE))


def test_list_and_state_answers_from_a_fake_registry():
    Q._plugin_entries = lambda: [
        {"folder": "docker", "module": "jarvis_docker", "error": None},
        {"folder": "goals", "module": "jarvis_goals", "error": None},
        {"folder": "broken", "module": "nope", "error": "no such module"},
    ]
    try:
        r = ask("what plug-ins do you have integrated into you?")
        check("the integrated question is answered by the fast path",
              r is not None and r.intent == "plugin_list", r.intent if r else "model")
        reply = r.reply if r else ""
        check("... it says Jarvis has a real plug-in system", "real drop-in plug-in system" in reply,
              reply[:250])
        check("... it lists the installed folders", "docker" in reply and "goals" in reply,
              reply[:250])
        check("... it does NOT repeat the old denial",
              "no plug-ins" not in reply and "built-in capabilities rather than" not in reply,
              reply[:250])
        check("... it names the real door (add-plugin + restart + no loader card)",
              "add-plugin.ps1" in reply and "restart" in reply and "loader" in reply, reply[:350])

        r = ask("what plugins are installed?")
        check("installed state reads the fake registry",
              r is not None and "docker" in r.reply and "goals" in r.reply, r.reply if r else "model")
        r = ask("what plugins are available?")
        check("available state lists catalogue names",
              r is not None and "android-builder" in r.reply and "45" in r.reply,
              r.reply if r else "model")
        r = ask("is docker plugin installed?")
        check("a named installed plug-in says yes", r is not None and "Yes" in r.reply,
              r.reply if r else "model")
        r = ask("is android-builder plugin installed?")
        check("a catalogue plug-in that is not installed says no and names it",
              r is not None and "No" in r.reply and "not installed" in r.reply,
              r.reply if r else "model")
        r = ask("what does plugin docker do?")
        check("a named plug-in gets its real purpose",
              r is not None and r.intent == "plugin_about"
              and "docker" in r.reply and "containers" in r.reply.lower(), r.reply if r else "model")
        r = ask("what does plugin nonsense do?")
        check("an unknown plug-in is refused with nearest real ones",
              r is not None and "isn't a Jarvis plug-in" in r.reply, r.reply if r else "model")
    finally:
        Q._plugin_entries = lambda: None


def test_install_answer_and_surface():
    r = ask("can I install a plugin?")
    check("'can I install a plugin?' is answered", r is not None and r.intent == "plugin_install",
          r.intent if r else "model")
    reply = r.reply if r else ""
    check("... it names add-plugin.ps1, restart and the PC folder",
          "add-plugin.ps1" in reply and "restart" in reply and "jarvis_plugins" in reply, reply[:350])
    check("... it says the loader raises no card", "loader itself raises no card" in reply, reply[:350])
    r = ask("how do I add a plugin?")
    check("'how do I add a plugin?' is a plug-in question, not a reminder",
          r is not None and r.intent == "plugin_install", r.intent if r else "model")
    r = ask("what plug-ins do you have?", "phone")
    check("the phone answer says plug-ins live on the PC",
          r is not None and "on the PC" in r.reply and "phone" in r.reply, r.reply if r else "model")


def test_over_capture():
    for text in ("install obsidian plugin", "what plugins does my browser have",
                 "what plugins does Chrome have", "add a WordPress plugin"):
        r = Q.match(text)
        check(f"not a Jarvis plug-in question: {text!r}",
              r is None or not str(r.name).startswith("plugin_"), r.name if r else "model")
    r = Q.match("how do I add a plugin?")
    check("the real plug-in question is still ours", r is not None and r.name == "plugin_install",
          r.name if r else "model")


def test_read_only():
    for text in ("what plug-ins do you have integrated into you?", "what plugins are available?",
                 "can I install a plugin?", "is docker plugin installed?"):
        Q._plugin_entries = lambda: [{"folder": "docker", "error": None}]
        try:
            r = ask(text)
        finally:
            Q._plugin_entries = lambda: None
        check(f"{text!r} is read-only", r is not None and r.intent in Q.READ_ONLY_INTENTS,
              r.intent if r else "model")


def test_system_prompt_line():
    mf = (ROOT / "backend" / "jarvis-primary.Modelfile").read_text(encoding="utf-8")
    m = re.search(r'SYSTEM """(.*?)"""', mf, re.S)
    text = m.group(1) if m else ""
    check("the Modelfile says the plug-in system is real",
          "real drop-in plug-in system" in text, "missing line")
    profiles = (ROOT / "backend" / "jarvis_profiles.py").read_text(encoding="utf-8")
    check("the tuned-model copy carries the same line",
          "real drop-in plug-in system" in profiles, "missing line")
    line = next((ln for ln in text.splitlines() if "drop-in plug-in system" in ln), "")
    check("the prompt line names the folder, add-plugin.ps1 and the restart",
          "jarvis_plugins" in line and "add-plugin.ps1" in line and "restart" in line, line)
    check("the prompt line carries no token or secret",
          not re.search(r"token|secret|api[ _-]?key|Bearer", line, re.I), line)


def test_source_truth():
    readme = (ROOT / "plugins" / "README.md").read_text(encoding="utf-8")
    check("plugins/README.md says 45 drop-in modules", "**45 drop-in modules**" in readme)
    registry = json.loads((ROOT / "plugins" / "registry.json").read_text(encoding="utf-8"))
    check("the generated registry agrees on 45 ready modules",
          registry.get("ready_count") == 45, str(registry.get("ready_count")))


def main():
    tests = [test_catalogue_is_the_real_ready_list, test_list_and_state_answers_from_a_fake_registry,
             test_install_answer_and_surface, test_over_capture, test_read_only,
             test_system_prompt_line, test_source_truth]
    for t in tests:
        print("\n-- " + t.__name__ + " " + "-" * 50)
        try:
            t()
        except Exception as exc:            # noqa: BLE001
            check(t.__name__ + " ran", False, repr(exc))
    print("\n" + "=" * 74)
    print(f"PASS {len(PASSED)}  FAIL {len(FAILED)}  SKIP 0")
    for name in FAILED:
        print("  FAIL:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
