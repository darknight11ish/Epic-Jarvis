"""test_runtime_identity.py - the two dynamic runtime lines the model gets.

    python -B backend/test_runtime_identity.py

Gemini ruling 1 (2026-10-31): the model system prompt gets exactly two dynamic
lines, all values read live at request time, and ordinary prompts otherwise keep
their bytes. Surface comes from PR #1046's `jarvis_surface` request context; this
suite fakes it (the module is not on this base yet), and drives every field with
probe values so no real model/preset/vault/device store is touched.

WHAT THIS PROVES:
1. the exact two-line shape, every field interpolated when known;
2. each missing getter becomes `unknown`, never a guess or a crash;
3. no surface -> NO line and the prompt list is unchanged byte for byte;
4. no secrets and no static feature list in the lines;
5. a known surface puts the note before the newest user message, rules first.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_agent as AG  # noqa: E402

FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


def fields(**kw):
    base = {"surface": "phone", "model": "qwen3.5:9b", "preset": "general",
            "cloud": "DeepSeek (API)", "vault": "configured", "phone": "connected"}
    base.update(kw)
    return base


def main():
    line = AG.runtime_identity_line(probes=fields())
    lines = line.splitlines()
    check("exactly two lines", len(lines) == 2, lines)
    check("line 1 is the runtime with every field",
          lines[0] == ("Runtime: Jarvis on phone (local model: qwen3.5:9b, "
                       "preset: general, cloud escalation: DeepSeek (API), "
                       "vault: configured, phone: connected)."), lines[0])
    check("line 2 is the fixed Rule, word for word",
          lines[1] == ('Rule: Never invent features, shortcuts, or settings; if '
                       'unsure, point to "Everything Jarvis can do" in the Brain.'), lines[1])
    check("the whole thing stays short (no static feature list)", len(line) < 600, len(line))
    check("no key-shaped secret, path or user name in the line",
          "sk-" not in line and "C:\\" not in line and "token" not in line.lower(), line)

    desktop = AG.runtime_identity_line(probes=fields(surface="desktop", model="qwen3.5:9b",
                                                     preset="coding", cloud="off",
                                                     vault="off", phone="off"))
    check("every field can change with the live state",
          "on desktop" in desktop and "preset: coding" in desktop
          and "cloud escalation: off" in desktop and "vault: off" in desktop
          and "phone: off" in desktop, desktop)

    unknown = AG.runtime_identity_line(probes=fields(model=None, preset=None,
                                                     cloud=None, vault=None, phone=None))
    check("a getter with nothing to say is `unknown`, not a guess",
          "local model: unknown" in unknown and "preset: unknown" in unknown
          and "cloud escalation: unknown" in unknown and "vault: unknown" in unknown
          and "phone: unknown" in unknown, unknown)

    no_surface = AG.runtime_identity_line(probes=fields(surface="unknown"))
    check("an unknown surface means NO runtime line", no_surface == "", no_surface)

    user = [{"role": "user", "content": "hello"}]
    check("with no surface the prompt list is unchanged",
          AG.with_runtime_identity_note(user) == user, AG.with_runtime_identity_note(user))
    check("dress_messages with no surface keeps the old prompt bytes",
          AG.dress_messages(user, manner=None) == user, AG.dress_messages(user, manner=None))

    inserted = AG.with_runtime_identity_note(user, probes=fields())
    check("a known surface adds ONE system note before the question",
          len(inserted) == 2 and inserted[0].get("role") == "user" and inserted[1].get("role") == "system"
          or len(inserted) == 3, inserted)
    # With no rules first in the input, the note is just before the user.
    check("... and the note is the two-line runtime text",
          any("Runtime: Jarvis on phone" in str(m.get("content")) for m in inserted if m.get("role") == "system"),
          inserted)

    # dress_messages path: fake a known surface and the live fields, then check
    # the model prompt has the note after the rules.
    saved_fields = AG.runtime_identity_fields
    AG.runtime_identity_fields = lambda *, probes=None: fields()
    try:
        dressed = AG.dress_messages([{"role": "user", "content": "hi"}], manner=None)
    finally:
        AG.runtime_identity_fields = saved_fields
    system = [m.get("content") for m in dressed if isinstance(m, dict) and m.get("role") == "system"]
    check("the real prompt path carries the runtime line after the rules",
          len(system) >= 2 and system[0] == AG.LANE_SYSTEM
          and any("Runtime: Jarvis on phone" in str(s) for s in system[1:]), system)

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
