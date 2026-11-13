#!/usr/bin/env python3
"""test_obfuscation.py - the code-protection tool CHECK, and the honest refusal.

This is the salvaged half of PR #1228 (2026-11-12). The pull request claimed a
multi-language obfuscation engine with an Ask-First card; what it actually had
was a read-only "is this program installed?" probe, a chat reply that promised a
card nobody raised, and six fake toolchains that copied files and reported
success. The fake parts are gone. This suite pins what is left, and it is
written so the fake parts cannot come back quietly.

WHAT IS CHECKED

  1. The check knows the seven code-protection programs, reports a stack and a
     spoken label for each, and lists them in a stable order.
  2. A name it does not know starts NO program.
  3. The one version probe is given `jarvis_child_env.inherited()` - the
     allowlisted child environment - and NEVER the backend's own environment.
     When that safe environment cannot be built, no program is started at all
     (there is no fallback to the whole environment).
  4. No obfuscation, minification, hardening, plan, card or verification exists:
     the module has no `detect_project`, `create_plan`, `build_card`,
     `execute_plan`, `verify_obfuscated_output` or `PROFILES`, and no project
     file is read, copied or written by anything this suite calls.
  5. The chat answer says plainly what is real: the tools are checked, and
     nothing is run.
  6. "obfuscate project X" gets a fixed honest refusal - no plan, no card - and
     the tool answer is answered from local code, never from a model.
  7. The fake gate surface is gone: `project_obfuscate` is in no shadow
     registry, no card-word table and neither shipped tier table.
  8. The module is shipped, in both SHIPPED lists, and byte-equal to the
     published-base twin.

WHY THE ENVIRONMENT CHECK IS THE IMPORTANT ONE
`backend/jarvis_child_env.py` exists because Jarvis's own environment holds the
pairing token, the Joplin token, the Obsidian key and every `*_KEY` /
`*_PASSWORD` / `*_SECRET` the owner has set. The old probe handed that whole
environment to each third-party binary it found. CLAUDE.md rule 3 says a key is
sent only to the one service it authenticates against, so the probe now gets the
allowlist or does not run.
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import jarvis_asks_first as AF  # noqa: E402
import jarvis_card_words as CW  # noqa: E402
import jarvis_obfuscation as OBF  # noqa: E402
import jarvis_quick as Q  # noqa: E402

PASSED = []
FAILED = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASSED.append(name)
        print(f"ok    {name}")
    else:
        FAILED.append(name)
        print(f"FAIL  {name}" + (f"\n        {detail}" if detail else ""))


class MockSched:
    def mark_command(self, text):
        pass

    def note_set(self, *a, **k):
        pass

    def last_set(self, *a, **k):
        return None


def ask(text: str, surface: str = "hud"):
    return Q.answer(
        text,
        sched=MockSched(),
        now=1794500000.0,
        peer="127.0.0.1",
        local=True,
        client_surface=surface,
    )


# --------------------------------------------------------------------------
# 1. The inventory itself
# --------------------------------------------------------------------------

EXPECTED_TOOLS = {
    "javascript-obfuscator", "terser", "pyarmor", "python-minifier",
    "r8", "strip", "garble",
}


def t_tool_inventory():
    tools = OBF.list_available_tools()
    check("the check knows all seven code-protection programs",
          {t["name"] for t in tools} == EXPECTED_TOOLS,
          str(sorted(t["name"] for t in tools)))
    check("the list is in a stable (sorted) order",
          [t["name"] for t in tools] == sorted(t["name"] for t in tools))

    for t in tools:
        check(f"{t['name']} carries a status, path, hint and description",
              all(k in t for k in ("available", "path", "version",
                                   "install_hint", "description")))
        check(f"{t['name']} carries a spoken language label",
              bool(t["stack_label"]) and t["stack_label"] != t["stack"],
              f"{t['name']}: {t['stack']} -> {t['stack_label']}")

    guidance = OBF.format_tool_guidance()
    check("the tool answer opens with what is NOT done", OBF.NOT_RUN in guidance)
    check("the tool answer says it cannot obfuscate or harden",
          "cannot obfuscate" in guidance and "harden" in guidance)
    check("the tool answer names each program it checks",
          all(t["name"] in guidance for t in tools))
    check("the tool answer names the languages it can SEE, not run",
          "Languages this check covers" in guidance
          and "JavaScript and TypeScript" in guidance)
    check("the tool answer never claims a profile or a ready run",
          "profile" not in guidance.lower()
          and "ready" not in guidance.lower()
          and "approval card" in guidance)

    single = OBF.format_tool_guidance("pyarmor")
    check("one tool's answer is honest with and without the program",
          "pyarmor" in single.lower() and "in this build" in single
          and ("--version" in single or "does not install it" in single))
    unknown = OBF.format_tool_guidance("not-a-real-obfuscator")
    check("an unknown tool is named as unknown, not guessed",
          "does not know" in unknown and "Nothing was run" in unknown)


# --------------------------------------------------------------------------
# 2. No program is started when there is nothing to start
# --------------------------------------------------------------------------

def t_unknown_tool_starts_nothing():
    boom = AssertionError("an unknown tool must start no program")
    with mock.patch.object(OBF.shutil, "which", side_effect=boom) as which_mock, \
         mock.patch.object(OBF.subprocess, "run", side_effect=boom) as run_mock:
        info = OBF.check_tool("not-a-real-obfuscator")
    check("an unknown name reports unavailable", info["available"] is False)
    check("... with no path and no version",
          info["path"] is None and info["version"] is None)
    check("... and starts neither a lookup nor a program",
          which_mock.call_count == 0 and run_mock.call_count == 0)


# --------------------------------------------------------------------------
# 3. The environment boundary - the leak this module exists to not repeat
# --------------------------------------------------------------------------

def t_safe_child_env_is_an_allowlist():
    secret_name = "JARVIS_OBF_TEST_PAIRING_TOKEN"
    os.environ[secret_name] = "never-send-me-to-a-third-party-program"
    try:
        env = OBF._safe_child_env()
    finally:
        os.environ.pop(secret_name, None)

    check("the safe child environment can be built here", isinstance(env, dict))
    upper = {k.upper() for k in (env or {})}
    check("a secret-looking name from the backend environment is NOT inherited",
          secret_name not in upper, str(sorted(upper))[:200])
    check("the telemetry switches ride along on every child",
          (env or {}).get("DO_NOT_TRACK") == "1"
          and (env or {}).get("HF_HUB_DISABLE_TELEMETRY") == "1")


def t_probe_uses_the_safe_environment():
    sentinel = {"PATH": r"C:\Windows\System32", "DO_NOT_TRACK": "1"}
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["env"] = kwargs.get("env")
        return types.SimpleNamespace(returncode=0, stdout="1.2.3\n", stderr="")

    with mock.patch.object(OBF.shutil, "which", return_value=r"C:\fake\pyarmor.exe"), \
         mock.patch.object(OBF, "_safe_child_env", return_value=sentinel), \
         mock.patch.object(OBF.subprocess, "run", side_effect=fake_run):
        info = OBF.check_tool("pyarmor")

    check("a found program is reported installed", info["available"] is True)
    check("the probe is given the allowlisted environment, not os.environ",
          seen.get("env") is sentinel, repr(seen.get("env")))
    check("the probe passes argv, not a shell string",
          seen.get("argv") == [r"C:\fake\pyarmor.exe", "--version"],
          repr(seen.get("argv")))
    check("the program's own version line is what is reported",
          info["version"] == "1.2.3", repr(info.get("version")))


def t_no_safe_environment_means_no_program():
    calls = []

    def fake_run(*a, **k):
        calls.append(a)
        return types.SimpleNamespace(returncode=0, stdout="1.0\n", stderr="")

    with mock.patch.object(OBF.shutil, "which", return_value=r"C:\fake\pyarmor.exe"), \
         mock.patch.object(OBF, "_safe_child_env", return_value=None), \
         mock.patch.object(OBF.subprocess, "run", side_effect=fake_run):
        info = OBF.check_tool("pyarmor")

    check("a missing safe environment still reports the program as installed",
          info["available"] is True)
    check("... but does not start it, and does not fall back to os.environ",
          calls == [], repr(calls))
    check("... so no version is claimed", info["version"] is None)


def t_safe_environment_fails_closed_when_helper_is_missing():
    saved = sys.modules.get("jarvis_child_env", "absent")
    sys.modules["jarvis_child_env"] = None
    try:
        failed = OBF._safe_child_env()
    finally:
        if saved == "absent":
            sys.modules.pop("jarvis_child_env", None)
        else:
            sys.modules["jarvis_child_env"] = saved
    check("without jarvis_child_env the answer is None (start nothing), not os.environ",
          failed is None, repr(failed))


# --------------------------------------------------------------------------
# 4. The fake machinery is gone, not merely unregistered
# --------------------------------------------------------------------------

def t_no_obfuscation_machinery():
    for name in ("PROFILES", "detect_project", "create_plan", "build_card",
                 "execute_plan", "verify_obfuscated_output", "OBFUSCATE_ACTION"):
        check(f"{name} does not exist on the module", not hasattr(OBF, name))
    for name in ("check_tool", "list_available_tools", "format_tool_guidance"):
        check(f"{name} is the small real surface that remains", hasattr(OBF, name))


# --------------------------------------------------------------------------
# 5/6. The chat lane: fixed local words, no plan, no card, nothing run
# --------------------------------------------------------------------------

def t_chat_tool_answer():
    r1 = ask("what obfuscation tools do you support?")
    check("'what obfuscation tools do you support' is answered locally",
          r1 is not None and r1.intent == "obfuscate_tools_info",
          getattr(r1, "intent", None))
    check("the answer starts with what is NOT done",
          r1 is not None and OBF.NOT_RUN in r1.reply, r1.reply[:120] if r1 else "")
    check("the answer lists the real programs",
          r1 is not None and "javascript-obfuscator" in r1.reply
          and "pyarmor" in r1.reply)

    r2 = ask("list code obfuscation tools")
    check("'list code obfuscation tools' is the same local answer",
          r2 is not None and r2.intent == "obfuscate_tools_info")

    r3 = ask("which hardening tools are installed?")
    check("'which hardening tools are installed?' is the same local answer",
          r3 is not None and r3.intent == "obfuscate_tools_info",
          getattr(r3, "intent", None))


def t_chat_refusal_never_promises_a_card():
    for text in ("obfuscate project sample-dashboard",
                 "harden project analytics with pyarmor hardened",
                 "apply code obfuscation to my project",
                 "protect my app"):
        r = ask(text)
        check(f"'{text}' gets the honest refusal",
              r is not None and r.intent == "project_obfuscate_unavailable",
              getattr(r, "intent", None))
        check(f"'{text}' says nothing was run",
              r is not None and "nothing was run" in r.reply.lower())
        check(f"'{text}' says no card was raised",
              r is not None and "no approval card" in r.reply.lower())
        check(f"'{text}' never asks the owner to approve anything",
              r is not None and "approve the approval card" not in r.reply.lower()
              and "please review" not in r.reply.lower())

    r = ask("obfuscate project ..")
    check("a path-shaped name ('..') is answered, not resolved",
          r is not None and r.intent == "project_obfuscate_unavailable")


def t_privacy_question_is_not_hijacked():
    r = ask("what protection do I have?")
    check("a privacy question is not answered by the code-protection lane",
          getattr(r, "intent", None) not in
          ("obfuscate_tools_info", "project_obfuscate_unavailable"),
          getattr(r, "intent", None))


def t_the_lane_is_a_deterministic_read():
    check("the tool answer is a private-chat read",
          "obfuscate_tools_info" in Q._PRIVATE_DETERMINISTIC_READS)
    check("the refusal is a private-chat read too",
          "project_obfuscate_unavailable" in Q._PRIVATE_DETERMINISTIC_READS)
    check("neither answer may clear 'cancel that'",
          "obfuscate_tools_info" in Q.READ_ONLY_INTENTS
          and "project_obfuscate_unavailable" in Q.READ_ONLY_INTENTS)


# --------------------------------------------------------------------------
# 7. The fake gate surface is gone
# --------------------------------------------------------------------------

def t_no_fake_gate_surface():
    row_ids = [a for _group, rows in AF.GROUPS for a in rows]
    check("project_obfuscate is in no asks-first group",
          "project_obfuscate" not in row_ids)
    check("project_obfuscate is not a MUST_ASK action",
          "project_obfuscate" not in AF.MUST_ASK)
    check("project_obfuscate is not a HARD_LIMITS action",
          "project_obfuscate" not in AF.HARD_LIMITS)
    check("project_obfuscate has no card title",
          "project_obfuscate" not in CW.TITLES)
    check("project_obfuscate has no card summary",
          "project_obfuscate" not in CW.SUMMARY)

    tomls = [ROOT / "backend" / "rebuilt" / "jarvis-framework.toml",
             ROOT / "jarvis-backend" / "jarvis-framework.toml"]
    for path in tomls:
        text = path.read_text(encoding="utf-8")
        check(f"no {path.parent.parent.name} tier line for a non-existent action",
              "project_obfuscate" not in text, str(path))


# --------------------------------------------------------------------------
# 8. Shipped, and the twin is the same file
# --------------------------------------------------------------------------

def t_shipped_and_twin():
    import _where

    check("jarvis_obfuscation.py is in backend/_where.py SHIPPED",
          "jarvis_obfuscation.py" in _where.SHIPPED)
    ps_text = (ROOT / "scripts" / "apply-patches.ps1").read_text(encoding="utf-8")
    check("jarvis_obfuscation.py is in scripts/apply-patches.ps1 $SHIPPED",
          "'jarvis_obfuscation.py'" in ps_text)

    backend_obf = (HERE / "jarvis_obfuscation.py").read_text(encoding="utf-8")
    base_obf = (ROOT / "jarvis-backend" / "jarvis_obfuscation.py").read_text(encoding="utf-8")
    check("jarvis_obfuscation.py is byte-equal to its published-base twin",
          backend_obf == base_obf)


def main():
    tests = [
        t_tool_inventory,
        t_unknown_tool_starts_nothing,
        t_safe_child_env_is_an_allowlist,
        t_probe_uses_the_safe_environment,
        t_no_safe_environment_means_no_program,
        t_safe_environment_fails_closed_when_helper_is_missing,
        t_no_obfuscation_machinery,
        t_chat_tool_answer,
        t_chat_refusal_never_promises_a_card,
        t_privacy_question_is_not_hijacked,
        t_the_lane_is_a_deterministic_read,
        t_no_fake_gate_surface,
        t_shipped_and_twin,
    ]
    for t in tests:
        print(f"\n--- {t.__name__} " + "-" * max(1, 56 - len(t.__name__)))
        try:
            t()
        except Exception as exc:  # noqa: BLE001 - report, never hide a crash
            check(f"{t.__name__} threw exception", False, repr(exc))

    print("\n" + "=" * 60)
    print(f"Total: {len(PASSED) + len(FAILED)} | Passed: {len(PASSED)} | Failed: {len(FAILED)}")
    if FAILED:
        print("Failed tests:")
        for f in FAILED:
            print(f"  - {f}")
        sys.exit(1)
    print("ALL TESTS PASSED!")
    sys.exit(0)


if __name__ == "__main__":
    main()
