#!/usr/bin/env python3
"""Keyboard-shortcut honesty (2026-10-31): the fast path's list against the real source.

The owner asked "what keyboard shortcuts do you have?" and the model answered
"I don't have any keyboard shortcuts myself ... that's up to your OS settings".
That is false: Jarvis Desktop ships 11 bindable global hotkeys and the notes
editor has its own formatting keys. This suite pins the deterministic answers to
the SOURCE that owns each list, so a new shortcut cannot silently drift out of
the fast path:

  * `jarvis-desktop/src-tauri/src/hotkeys.rs` - the 11 bindable actions and
    their shipped default keys (including the two that ship unbound).
  * `jarvis-desktop/src/notes.js` - the notes editor's own SHORTCUTS map.
  * `backend/jarvis-primary.Modelfile` and `backend/jarvis_profiles.py` - the
    one honest system-prompt line (they must stay word for word equal).

The model is not called here: a stub scheduler is enough because every one of
these answers is read-only and deterministic ("stub-model": the questions are
answered before any model turn). No token, key or secret is read.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import jarvis_quick as Q  # noqa: E402

PASSED, FAILED = [], []


class Stub:
    """The scheduler stand-ins answer() uses for bookkeeping only."""

    def mark_command(self, text):
        pass

    def forget_set(self, conversation):
        pass

    def note_set(self, *a, **k):
        pass

    def last_set(self, *a, **k):
        return None


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def ask(text, surface="hud"):
    return Q.answer(text, sched=Stub(), now=time.time(), peer="127.0.0.1", local=True,
                    client_surface=surface)


def source_rust_actions():
    """(id, default key) from hotkeys.rs ACTIONS, in file order."""
    src = (ROOT / "jarvis-desktop" / "src-tauri" / "src" / "hotkeys.rs").read_text(encoding="utf-8")
    start = src.index("pub const ACTIONS")
    block = src[start:]
    block = block[: block.index("\n];")]
    out = []
    for chunk in re.split(r"Action\s*\{", block)[1:]:
        m_id = re.search(r'id:\s*"([^"]+)"', chunk)
        m_def = re.search(r'default:\s*"([^"]*)"', chunk)
        if m_id and m_def:
            out.append((m_id.group(1), m_def.group(1)))
    return out


def source_notes_shortcuts():
    """{lower key: action} from notes.js SHORTCUTS."""
    src = (ROOT / "jarvis-desktop" / "src" / "notes.js").read_text(encoding="utf-8")
    start = src.index("export const SHORTCUTS")
    block = src[start:]
    block = block[: block.index("});")] if "});" in block else block[:1200]
    return {k.lower(): v for k, v in re.findall(r'"(ctrl\+[^"]+)"\s*:\s*"([^"]+)"', block)}


def test_the_tables_are_the_real_source():
    rust = source_rust_actions()
    check("hotkeys.rs lists the 11 bindable actions we measured", len(rust) == 11, str(rust))
    ids = [a[0] for a in Q.SHORTCUT_ACTIONS]
    check("the fast path's action ids are hotkeys.rs's ids, in order", ids == [r[0] for r in rust],
          f"{ids} != {[r[0] for r in rust]}")
    keys = [a[1] for a in Q.SHORTCUT_ACTIONS]
    check("the fast path's default keys are hotkeys.rs's defaults",
          keys == [r[1] for r in rust], f"{keys} != {[r[1] for r in rust]}")
    check("exactly two actions ship unbound (Watch with me, Jarvis Live)",
          [a[0] for a in Q.SHORTCUT_ACTIONS if not a[1]] == ["toggle_watch", "toggle_live"])

    js = source_notes_shortcuts()
    check("notes.js binds 11 formatting keys", len(js) == 11, str(js))
    ours = {k.lower(): v for k, v in Q.SHORTCUT_NOTES_EDITOR}
    check("the notes-editor keys are notes.js's keys", set(ours) == set(js), f"{ours} != {js}")
    check("every notes-editor key has a real action", all(ours[k] for k in js), str(ours))


def test_list_answers_are_the_measured_truth():
    for prompt in ("what keyboard shortcuts do you have?",
                   "what are your keyboard shortcuts?",
                   "what keyboard shortcuts do you have"):
        r = ask(prompt)
        check(f"{prompt!r} is answered by the fast path", r is not None and r.intent == "shortcuts_list",
              r.intent if r else "model")
        reply = r.reply if r else ""
        check("... it says Jarvis Desktop has real shortcuts",
              "Jarvis Desktop" in reply and "real keyboard shortcuts" in reply, reply[:200])
        check("... it names every shipped key",
              all(key in reply for _id, key, _w, _where in Q.SHORTCUT_ACTIONS if key), reply)
        check("... it says where the global keys are changed",
              "Settings, Shortcuts" in reply, reply)
        check("... it names the notes editor's keys and scope",
              "notes editor" in reply and "Ctrl+B" in reply, reply)
        check("... it never repeats the old OS-settings lie",
              "OS settings" not in reply and "I don't have any keyboard shortcuts" not in reply,
              reply)
        check("... it does not claim the phone has shortcuts",
              "phone has no keyboard shortcuts" in reply, reply)


def test_open_and_quick_note():
    r = ask("how do I open you with the keyboard?")
    check("'how do I open you with the keyboard?' answers Alt+Space",
          r is not None and r.intent == "shortcuts_open" and "Alt+Space" in r.reply,
          r.reply if r else "model")
    r = ask("how can I open Jarvis with the keyboard?")
    check("'how can I open Jarvis with the keyboard?' is the same answer",
          r is not None and r.intent == "shortcuts_open", r.intent if r else "model")
    for prompt in ("what shortcut makes a quick note?",
                   "what is the shortcut for a quick note?",
                   "what is the quick note shortcut?"):
        r = ask(prompt)
        check(f"{prompt!r} answers Alt+Shift+N",
              r is not None and r.intent == "shortcuts_quick_note" and "Alt+Shift+N" in r.reply,
              r.reply if r else "model")
        check("... and says it is changeable in Settings, Shortcuts",
              r is not None and "Settings, Shortcuts" in r.reply, r.reply if r else "")


def test_change_answer():
    for prompt in ("can I change the shortcuts?", "how do I change my shortcuts?"):
        r = ask(prompt)
        check(f"{prompt!r} says yes and where",
              r is not None and r.intent == "shortcuts_change"
              and "Settings, Shortcuts" in r.reply and "can be changed" in r.reply,
              r.reply if r else "model")
        check("... it says the notes editor keys are fixed",
              r is not None and "notes editor" in r.reply and "not configurable" in r.reply,
              r.reply if r else "")


def test_named_shortcuts_and_unknown():
    r = ask("what is the shortcut for stop everything?")
    check("a named real key resolves (stop everything -> Alt+Shift+X)",
          r is not None and r.intent == "shortcuts_named" and "Alt+Shift+X" in r.reply,
          r.reply if r else "model")
    r = ask("what is the shortcut for bold?")
    check("a notes-editor key is named as inside the notes editor",
          r is not None and r.intent == "shortcuts_notes_named"
          and "Ctrl+B" in r.reply and "notes editor" in r.reply, r.reply if r else "model")
    r = ask("what is the shortcut for highlighting?")
    check("a shortcut that does not exist is refused plainly, with the nearest real ones",
          r is not None and r.intent == "shortcuts_unknown"
          and "isn't a Jarvis shortcut" in r.reply
          and "Alt+Shift+N" in r.reply and "Ctrl+B" in r.reply, r.reply if r else "model")
    r = ask("what shortcut makes a sandwich?")
    check("an imagined shortcut is also refused, not invented",
          r is not None and r.intent == "shortcuts_unknown", r.reply if r else "model")


def test_over_capture_stays_model():
    for prompt in ("what's the shortcut to close Chrome?",
                   "what is the keyboard shortcut to close Chrome",
                   "how do I close Windows with the keyboard?",
                   "what shortcut copies text in Word?"):
        r = ask(prompt)
        check(f"OS/other-program shortcut stays the model's: {prompt!r}", r is None,
              r.reply if r else "")


def test_phone_surface_is_pc_aware():
    r = ask("what keyboard shortcuts do you have?", surface="phone")
    check("the phone is told the shortcuts are on the PC",
          r is not None and r.intent == "shortcuts_list"
          and "on the PC" in r.reply and "phone has no keyboard shortcuts" in r.reply,
          r.reply if r else "model")
    r = ask("what shortcut makes a quick note?", surface="phone")
    check("the phone's quick-note answer names the PC",
          r is not None and "on the PC" in r.reply and "Alt+Shift+N" in r.reply,
          r.reply if r else "model")
    r = ask("can I change the shortcuts?", surface="phone")
    check("the phone's change answer points at the PC",
          r is not None and "on the PC" in r.reply, r.reply if r else "model")


def test_stub_model_never_gets_these():
    prompts = ("what keyboard shortcuts do you have?", "what are your keyboard shortcuts?",
               "how do I open you with the keyboard?", "what shortcut makes a quick note?",
               "can I change the shortcuts?", "what is the shortcut for stop everything?",
               "what is the shortcut for highlighting?")
    answers = [ask(p) for p in prompts]
    check("stub-model: every shortcut shape is answered before the model",
          all(a is not None for a in answers),
          str([p for p, a in zip(prompts, answers) if a is None]))
    check("stub-model: every answer is read-only fast path",
          all(a.intent in Q.READ_ONLY_INTENTS for a in answers if a is not None),
          str([a.intent for a in answers if a is not None]))


def test_system_prompt_line():
    mf = (ROOT / "backend" / "jarvis-primary.Modelfile").read_text(encoding="utf-8")
    m = re.search(r'SYSTEM """(.*?)"""', mf, re.S)
    check("the Modelfile carries the one honest shortcuts line",
          m is not None and "Jarvis Desktop ships real keyboard shortcuts" in m.group(1),
          "missing line")
    profiles = (ROOT / "backend" / "jarvis_profiles.py").read_text(encoding="utf-8")
    check("the tuned-model copy carries the same line",
          "Jarvis Desktop ships real keyboard shortcuts" in profiles, "missing line")
    line = next((ln for ln in (m.group(1).splitlines() if m else []) if "keyboard shortcuts" in ln and "Jarvis Desktop" in ln), "")
    check("the prompt line names the real keys and the place to change them",
          "Alt+Space" in line and "Alt+Shift+N" in line and "Settings, Shortcuts" in line, line)
    check("the prompt line points at the notes editor keys",
          "notes editor" in line and "Ctrl+B" in line, line)
    check("the prompt line carries no token, key or secret",
          not re.search(r"token|secret|api[ _-]?key|Bearer|sk-[A-Za-z0-9]", line, re.I), line)


def test_catalogue_rows_carry_the_truth():
    src = json.loads((ROOT / "features" / "features.json").read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in src}
    sc = by_id["shortcuts"]
    text = " ".join(str(sc.get(k) or "") for k in ("what", "where", "limit"))
    check("the Keyboard shortcuts row carries the measured list",
          "11" in text and "Alt+Space" in text and "notes" in text.lower(), text[:300])
    check("... it says the global keys are changeable and where",
          "Settings, Shortcuts" in text and "changed" in text, text[:300])
    check("... it says the notes-editor keys are fixed and the phone has none",
          "fixed" in text and "phone" in text, text[:300])
    nw = by_id["notes-write"]
    nw_text = " ".join(str(nw.get(k) or "") for k in ("where", "limit"))
    check("the quick-note row names Alt+Shift+N and where to change it",
          "Alt+Shift+N" in nw_text and "Settings, Shortcuts" in nw_text, nw_text[:300])
    three = [(ROOT / p).read_bytes() for p in (
        "features/features.json", "jarvis-desktop/src/features.json",
        "jarvis-client/app/src/main/assets/features.json")]
    check("the three features.json copies are byte-identical", three[0] == three[1] == three[2])
    catalogue = (ROOT / "backend" / "jarvis_feature_catalogue.py").read_text(encoding="utf-8")
    check("the generated feature catalogue carries the new row words",
          "measured list" in catalogue and "notes editor's Ctrl+B" in catalogue)


def main():
    tests = [test_the_tables_are_the_real_source, test_list_answers_are_the_measured_truth,
             test_open_and_quick_note, test_change_answer, test_named_shortcuts_and_unknown,
             test_over_capture_stays_model, test_phone_surface_is_pc_aware,
             test_stub_model_never_gets_these, test_system_prompt_line,
             test_catalogue_rows_carry_the_truth]
    for t in tests:
        print("\n-- " + t.__name__ + " " + "-" * 50)
        try:
            t()
        except Exception as exc:            # noqa: BLE001 - a crash is a failure, not a skip
            check(t.__name__ + " ran", False, repr(exc))
    print("\n" + "=" * 74)
    print(f"PASS {len(PASSED)}  FAIL {len(FAILED)}  SKIP 0")
    for name in FAILED:
        print("  FAIL:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
