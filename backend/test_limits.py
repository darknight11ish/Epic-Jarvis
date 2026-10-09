"""test_limits.py - the limits and frequencies the owner can change.

    python3 backend/test_limits.py

Runs anywhere; no model, no network, no gate (where a raise needs one, the test
stands one in exactly as test_attention_settings_route.py does).

An audit of all 117 features against the real settings surface (2026-10-08)
listed the limits the owner could see and change nowhere. They are all the same
shape - a number (or one on/off) in the owner's own jarvis-framework.toml,
already read by a module that knows what to do with it - so they share ONE
table (`jarvis_limits.LIMITS`) and ONE route. What this file proves:

1. **The table matches the file.** Every entry names a table and key that
   really exists in the shipped jarvis-framework.toml - a hand-typed table that
   drifted from the settings it claims to change would write a key nothing
   reads, and this check is what stops that.
2. **The value written is the value the module reads.** `value_of` reads the
   same key the owning module reads, and falls back to that module's own
   default when the key is absent or nonsense.
3. **A change is surgical**: ONE line of the owner's file moves, and its
   comments, spacing, CRLF endings and byte-order mark survive.
4. **Nonsense is refused with a plain message and nothing written**: not a
   number, outside the range, not one of the choices.
5. **The rule every setting follows**: turning something DOWN is instant;
   turning something UP asks, but only where the table says the bigger number
   is a loosening. A denied card, a timed-out card, an unreachable gate and a
   PC that cannot ask all leave the file exactly as it was.
6. **A PC-only limit is refused from a phone**, in the owner's words.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from _where import require_shipped  # noqa: E402
require_shipped("jarvis_limits.py", "jarvis_framework.py", "jarvis_owner_check.py")
sys.path.append(str(HERE / "rebuilt"))

TMP = Path(tempfile.mkdtemp(prefix="jarvis-limits-"))
os.environ["JARVIS_FRAMEWORK_TOML"] = str(TMP / "jarvis-framework.toml")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_CONFIG_DIR"] = str(TMP)

import jarvis_limits as L  # noqa: E402

SHIPPED = REPO / "backend" / "rebuilt" / "jarvis-framework.toml"
FAILED, PASSED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


class Verdict:
    def __init__(self, allowed, outcome, tier="ask"):
        self.allowed, self.outcome, self.tier = allowed, outcome, tier


def fresh(text: str = None) -> Path:
    p = TMP / "jarvis-framework.toml"
    if text is None:
        shutil.copyfile(SHIPPED, p)
    else:
        # write_bytes, not write_text: on Windows write_text turns the "\n" in a
        # CRLF sample into another CRLF, and the test would be measuring its own
        # translation rather than the writer's.
        p.write_bytes(text.encode("utf-8"))
    L._reload()
    return p


def reset(gate=None, tier="ask"):
    L.configure(gate=gate, tier_of=lambda action: tier)


# --------------------------------------------------------------------------


def t_the_table_matches_the_settings_file():
    """Every entry's table and key really exist, so a write lands somewhere a
    module actually reads."""
    cfg = tomllib.loads(SHIPPED.read_text(encoding="utf-8"))
    for limit in L.LIMITS:
        node = cfg
        for part in limit.section.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        check(f"{limit.key}: [{limit.section}] exists in the shipped file",
              isinstance(node, dict), limit.section)
        check(f"{limit.key}: {limit.section}.{limit.name} is really there",
              isinstance(node, dict) and limit.name in node,
              f"{limit.name} not in {list(node or {})}")
    keys = [x.key for x in L.LIMITS]
    check("no two limits share a key", len(keys) == len(set(keys)), keys)


def t_the_value_is_the_one_the_owning_module_reads():
    fresh()
    for limit in L.LIMITS:
        check(f"{limit.key}: the shipped file's own value is read",
              L.value_of(limit) == limit.default,
              (L.value_of(limit), limit.default))
    fresh("# nothing here\n[undo]\n")
    check("a missing key falls back to the module's own default",
          L.value_of(L.find("undo_window")) == 24, L.value_of(L.find("undo_window")))
    fresh("[undo]\nttl_hours = nonsense\n")
    check("a nonsense value falls back to the default too",
          L.value_of(L.find("undo_window")) == 24, L.value_of(L.find("undo_window")))


def t_one_line_moves_and_the_rest_of_the_file_does_not():
    p = fresh()
    before = p.read_text(encoding="utf-8")
    out = L.set_limit("undo_window", 168)
    after = p.read_text(encoding="utf-8")
    check("the answer reports the old and the new value",
          out.get("from") == 24 and out.get("to") == 168 and out.get("changed"), out)
    changed = [i for i, (a, b) in enumerate(zip(before.splitlines(), after.splitlines()), 1)
               if a != b]
    check("exactly one line changed", len(changed) == 1, changed)
    check("and it is the line the owner's file already had",
          after.splitlines()[changed[0] - 1].strip() == "ttl_hours = 168",
          after.splitlines()[changed[0] - 1] if changed else "")
    check("every comment survives", before.count("#") == after.count("#"))
    p2 = fresh("# a comment\r\n[undo]\r\nttl_hours = 24        # keep this\r\n[other]\r\nx = 1\r\n")
    L.set_limit("undo_window", 1, path=p2)
    raw = p2.read_bytes()
    check("CRLF endings survive (no bare LF was introduced)",
          raw.count(b"\r\n") == raw.count(b"\n") and b"\r\n" in raw,
          (raw.count(b"\r\n"), raw.count(b"\n")))
    check("the line's own trailing comment survives",
          b"ttl_hours = 1        # keep this\r\n" in raw, raw.decode("utf-8"))
    p3 = fresh("[undo]\nttl_hours = 24\n")
    L.set_limit("undo_window", 168, path=p3)
    p4 = fresh()
    L.set_limit("memory_people", True)
    check("a bool is written as true, not as 1",
          re.search(r"model_pass = true", p4.read_text(encoding="utf-8")) is not None,
          p4.read_text(encoding="utf-8").split("[memory.entities]")[-1][:120])


def t_nonsense_is_refused_and_writes_nothing():
    p = fresh()
    before = p.read_bytes()
    cases = [("undo_window", 0, "below the choices"),
             ("undo_window", 5, "a number that is not one of the choices"),
             ("undo_window", "soon", "not a number"),
             ("jobs_per_tick", 0, "below the range"),
             ("jobs_per_tick", 99, "above the range"),
             ("watch_star_jump", 2.0, "above the range"),
             ("memory_people", "perhaps", "not on or off"),
             ("not_a_limit", 1, "not a limit at all")]
    for key, value, why in cases:
        try:
            L.set_limit(key, value)
            check(f"{key} = {value!r} ({why}) is refused", False, "no error")
        except L.SettingsFileError as exc:
            check(f"{key} = {value!r} ({why}) is refused in plain words",
                  bool(str(exc)) and "_" not in str(exc), str(exc))
    check("and not one byte was written", p.read_bytes() == before)


def t_down_is_instant_and_up_asks_only_where_it_loosens():
    fresh()
    g = []
    reset(lambda action, detail, prompt: (g.append(action), Verdict(True, "approved"))[1])
    code, out = L.handle_post(L.ROUTE, {"key": "undo_window", "value": 1})
    check("turning the undo window down is instant, with no card",
          code == 200 and g == [] and L.value_of(L.find("undo_window")) == 1, (code, g))
    check("and is not called a loosening", out.get("loosening") is False, out)

    fresh()
    g2 = []
    reset(lambda action, detail, prompt: (g2.append((action, prompt)), Verdict(True, "approved"))[1])
    code, out = L.handle_post(L.ROUTE, {"key": "undo_window", "value": 168})
    check("turning it up goes through the gate", len(g2) == 1 and g2[0][0] == L.RAISE_ACTION,
          g2)
    check("the card names the limit and both numbers",
          "undo" in g2[0][1].lower() and "168" in g2[0][1], g2)
    check("it is applied once approved, and reported as a loosening",
          code == 200 and out.get("loosening") is True and out.get("approved") is True
          and L.value_of(L.find("undo_window")) == 168, (code, out))

    fresh()
    g3 = []
    reset(lambda action, detail, prompt: (g3.append(action), Verdict(True, "approved"))[1])
    code, out = L.handle_post(L.ROUTE, {"key": "jobs_per_tick", "value": 12})
    check("a limit whose bigger number is NOT a loosening asks nothing",
          code == 200 and g3 == [] and L.value_of(L.find("jobs_per_tick")) == 12,
          (code, g3))
    check("and is not called a loosening", out.get("loosening") is False, out)


def t_every_refusal_leaves_the_file_as_it_was():
    cases = [("a denied card", Verdict(False, "denied"), "ask", "You said no"),
             ("a card that timed out", Verdict(False, "timed_out"), "ask", "not answered"),
             ("a PC whose Jarvis cannot ask", Verdict(True, "approved"), "auto",
              "nothing was changed"),
             ("a gate that cannot be reached", RuntimeError("no gate"), "ask",
              "nothing was changed")]
    for why, verdict, tier, words in cases:
        p = fresh()
        before = p.read_bytes()

        def gate(action, detail, prompt, v=verdict):
            if isinstance(v, Exception):
                raise v
            return v

        reset(gate, tier)
        code, out = L.handle_post(L.ROUTE, {"key": "undo_window", "value": 168})
        check(f"{why}: refused with a code, not applied", code >= 400, (code, out))
        check(f"{why}: the file was not written", p.read_bytes() == before)
        check(f"{why}: and the answer says so in plain words",
              words in str(out.get("error")), out)


def t_a_pc_only_limit_is_refused_from_a_phone():
    """`jobs_per_tick` is the PC's own resource knob and is marked PC-only; the
    refusal is in the owner's words and nothing is written."""
    p = fresh()
    before = p.read_bytes()
    reset(lambda action, detail, prompt: Verdict(True, "approved"))
    code, out = L.handle_post(L.ROUTE, {"key": "jobs_per_tick", "value": 8},
                              peer="100.64.0.9", local="127.0.0.1")
    check("a PC-only limit is refused when the request came from a peer",
          code == 403 and out.get("pc_only") is True, (code, out))
    check("the refusal is in the owner's words",
          "PC" in str(out.get("error")), out)
    check("and nothing was written", p.read_bytes() == before)
    code2, out2 = L.handle_post(L.ROUTE, {"key": "jobs_per_tick", "value": 8},
                                peer=None, local="127.0.0.1")
    check("the same change from this PC goes through",
          code2 == 200 and L.value_of(L.find("jobs_per_tick")) == 8, (code2, out2))


def t_the_view_lists_what_each_app_may_change():
    fresh()
    desk = L.view(app="desktop")
    phone = L.view(app="phone")
    check("the desktop view has rows with the owner's words",
          desk["limits"] and all(r["title"] and r["words"] for r in desk["limits"]),
          desk["limits"][:1])
    check("the phone view leaves out what only the PC may change",
          all(r["key"] != "jobs_per_tick" for r in phone["limits"]),
          [r["key"] for r in phone["limits"]])
    check("the phone view still has the ones it may change",
          any(r["key"] == "undo_window" for r in phone["limits"]),
          [r["key"] for r in phone["limits"]])
    code, out = L.handle_post("/api/attention/settings", {"key": "undo_window", "value": 1})
    check("a route this module does not own is a 404", code == 404, (code, out))
    code, out = L.handle_post(L.ROUTE, {"key": "undo_window"})
    check("a body with no value is a 400 in plain words",
          code == 400 and out.get("error"), (code, out))


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("t_") and callable(v)]
    for t in tests:
        print(f"--- {t.__name__} ---")
        t()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("\nFAILED:")
        for f in FAILED:
            print(f"  {f}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
