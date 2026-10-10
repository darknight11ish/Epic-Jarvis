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
5. **The rule every setting follows**: the SAFE direction is instant; the
   direction that LOOSENS something asks, and which direction that is comes
   from the entry's own `loosening` ("up", "down" or "none"). A denied card, a
   timed-out card, an unreachable gate and a PC that cannot ask all leave the
   value exactly as it was.
6. **A PC-only limit is refused from a phone**, in the owner's words.
7. **The voice check's bar** (the owner's decision of 2026-10-08) - the one row
   whose number is NOT in the settings file and whose loosening goes the OTHER
   way. It is offered to both apps and to the phone; it is read from the real
   encrypted print through `jarvis_voice`; the cosine the print stores and the
   whole percentage the owner reads convert exactly, floor and ceiling
   included; LOWERING it raises ONE card, under its own action name, and a
   RAISE raises none - proved by watching the card path, never by reading the
   flag; a number the voice module itself would refuse never reaches a card;
   and the print stays the only home of the number, with nothing about it
   logged.
8. **This PC's own notifications** (the owner's decision of 2026-10-08: they
   must be changeable from the phone too). Seven more rows - four toggles, the
   quiet-hours switch and the window's two times - owned by
   `jarvis_notify_prefs.py` in the owner's `[notifications]` table. They are
   offered to BOTH apps on the wire, every title says plainly that the setting
   is the PC's own, a change from a phone really lands in
   `jarvis-framework.toml`, a time of day is carried and stored as a clock time
   and never as a number of minutes, no direction of any of the seven raises a
   card (so an alarm is never left waiting on one), and `quiet_on` - the one
   additive field this view ever gained - follows the quiet-hours switch.
"""
from __future__ import annotations

import contextlib
import io
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
import _where  # noqa: E402
require_shipped("jarvis_limits.py", "jarvis_framework.py", "jarvis_owner_check.py",
                "jarvis_voice.py")
sys.path.append(str(HERE / "rebuilt"))

TMP = Path(tempfile.mkdtemp(prefix="jarvis-limits-"))
os.environ["JARVIS_FRAMEWORK_TOML"] = str(TMP / "jarvis-framework.toml")
os.environ["OPENJARVIS_CONFIG_DIR"] = str(TMP)
os.environ["JARVIS_CONFIG_DIR"] = str(TMP)
# The voice bar's own home for this suite. `jarvis_voice` reads this when it is
# FIRST imported, so it is set here with the other three - and never points at
# a print the owner has.
VOICE_PROFILE = TMP / "voice" / "owner.json"
os.environ["JARVIS_VOICE_PROFILE"] = str(VOICE_PROFILE)

import jarvis_limits as L  # noqa: E402
import jarvis_owner_check as OC  # noqa: E402

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


def _says_yes(cards=None):
    """A gate that approves, recording every card it was asked for."""
    def gate(action, detail, prompt):
        if cards is not None:
            cards.append((action, detail, prompt))
        return Verdict(True, "approved")
    return gate


def _voice():
    import jarvis_voice
    return jarvis_voice


def _make_print(threshold: float, embedder: str = "357a834f702b") -> None:
    """A real print file, written by jarvis_voice's OWN class and writer, so
    what is read back is what that module would load on the owner's PC."""
    v = _voice()
    VOICE_PROFILE.parent.mkdir(parents=True, exist_ok=True)
    v.VoiceProfile(name="owner", embedder=embedder, threshold=threshold,
                   centroid=[0.1, 0.2, 0.3, 0.4], samples=5).save(VOICE_PROFILE)


def _no_print() -> None:
    shutil.rmtree(VOICE_PROFILE.parent, ignore_errors=True)


def _tree(root: Path) -> dict:
    return {str(p): p.read_bytes() for p in sorted(Path(root).rglob("*")) if p.is_file()}


# --------------------------------------------------------------------------


def t_the_table_matches_the_settings_file():
    """Every entry points at a home that really holds its value.

    A TOML-BACKED entry names a `[table].key` that really exists in the shipped
    jarvis-framework.toml - a hand-typed table that drifted from the settings it
    claims to change would write a key nothing reads, and this check is what
    stops that.

    A SOURCE-BACKED entry has no key to name at all: the voice check's bar lives
    in the owner's encrypted print, which `jarvis_voice.py` reads and writes. So
    the same check is kept meaningful a different way, and it is not weakened:
    the entry must (a) carry NO `[table].key`, (b) name a source this module
    knows, (c) point at the module it claims to (`owner` == `module` + ".py",
    the name the source itself declares), and (d) name a module this repository
    SHIPS WHOLE (`_where.SHIPPED`). A source pointing at a module the owner's
    backend need not even have would be a row whose value cannot be read or
    written at all - the same failure the key check exists to prevent."""
    cfg = tomllib.loads(SHIPPED.read_text(encoding="utf-8"))
    shipped = {n.rsplit("/", 1)[-1] for n in _where.SHIPPED}
    for limit in L.LIMITS:
        if limit.source:
            check(f"{limit.key}: names a source this module knows",
                  limit.source in L.SOURCES, limit.source)
            src = L.SOURCES.get(limit.source)
            if src is None:
                continue
            check(f"{limit.key}: its source carries no [table].key of its own",
                  limit.section == "" and limit.name == "",
                  (limit.section, limit.name))
            check(f"{limit.key}: {limit.source} points at the module it claims",
                  bool(src.module) and src.owner == f"{src.module}.py",
                  (src.module, src.owner))
            check(f"{limit.key}: {src.owner} is a module this repository ships whole",
                  src.owner in shipped, sorted(shipped))
            continue
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


def t_every_entry_says_which_direction_loosens():
    """The direction is explicit on every row, and it is the direction the row's
    behaviour already had - so converting `loosen_up` into `loosening` changed
    no existing row's behaviour. `undo_window` and `memory_people` go UP; every
    other row here has no loosening direction at all; and the voice check's bar
    is the one row that goes DOWN."""
    directions = {limit.key: limit.loosening for limit in L.LIMITS}
    check("every entry names a direction this module understands",
          bool(directions) and set(directions.values()) <= {"up", "down", "none"},
          directions)
    check("the two entries that always asked still go up",
          directions["undo_window"] == "up" and directions["memory_people"] == "up",
          directions)
    check("... and nothing else does",
          sorted(k for k, d in directions.items() if d == "up")
          == ["memory_people", "undo_window"], directions)
    check("the voice check's bar is the one that goes down",
          directions.get("voice_bar") == "down", directions)
    shown = {r["key"]: r["loosen_up"] for r in L.view()["limits"]}
    check("the view keeps `loosen_up`'s old meaning for both apps",
          shown["undo_window"] is True and shown["memory_people"] is True
          and shown["jobs_per_tick"] is False, shown)
    check("the voice bar's own row says false there, because its loosening is "
          "not an increase", shown["voice_bar"] is False, shown)
    check("a bool turned ON is its 'up', and OFF is not",
          L._is_loosening(L.find("memory_people"), False, True) is True
          and L._is_loosening(L.find("memory_people"), True, False) is False)
    check("a row with no loosening direction never asks, either way",
          L._is_loosening(L.find("jobs_per_tick"), 4, 12) is False
          and L._is_loosening(L.find("jobs_per_tick"), 12, 4) is False)
    check("a bigger number on an 'up' row is the loosening, a smaller one is not",
          L._is_loosening(L.find("undo_window"), 24, 168) is True
          and L._is_loosening(L.find("undo_window"), 168, 1) is False)


# --------------------------------------------------------------------------
#   The voice check's bar - the one row whose number is not in the file
# --------------------------------------------------------------------------


def t_the_voice_bar_is_offered_to_both_apps():
    """The owner's decision of 2026-10-08: on the PC AND on the phone. The row
    is a plain whole number, so the two screens that already draw every row of
    this table - filtering on the row's own `app` and `pc_only` - draw it with
    no change of their own."""
    _no_print()
    limit = L.find("voice_bar")
    check("the row is in the table", limit is not None)
    if limit is None:
        return
    check("... offered to both apps", limit.app == "both", limit.app)
    check("... and not a PC-only row", limit.pc_only is False, limit.pc_only)
    check("... a kind both screens already draw", limit.kind == "int", limit.kind)
    check("... shown as a whole percentage", limit.unit == "%", limit.unit)
    check("... with the choices the owner picks from",
          tuple(limit.choices) == (25, 35, 50, 65), limit.choices)
    check("... and the whole 5..100 range the voice clamp allows",
          limit.low == 5 and limit.high == 100, (limit.low, limit.high))
    every = {r["key"]: r for r in L.view()["limits"]}
    desk = {r["key"]: r for r in L.view(app="desktop")["limits"]}
    phone = {r["key"]: r for r in L.view(app="phone")["limits"]}
    check("the unfiltered view the route serves has it", "voice_bar" in every)
    check("the desktop's own view has it", "voice_bar" in desk, sorted(desk))
    check("the phone's own view has it too", "voice_bar" in phone, sorted(phone))
    row = phone.get("voice_bar") or {}
    check("its title is in the owner's words",
          "voice" in str(row.get("title", "")).lower()
          and "sure" in str(row.get("title", "")).lower(), row.get("title"))
    check("its note says a lower number lets more clips count, and that going "
          "lower asks on the PC first",
          "lower" in str(row.get("note", "")).lower()
          and "more clips" in str(row.get("note", ""))
          and "asks" in str(row.get("note", ""))
          and "PC" in str(row.get("note", "")), row.get("note"))
    check("with no print trained the row shows the default 35%",
          row.get("value") == 35 and row.get("words") == "35 %", row)


def t_the_voice_bar_percent_and_cosine_convert_exactly():
    """The print stores a cosine similarity and the owner reads a whole
    percentage. The two meet in exactly two functions, and they are exact the
    whole way up - the floor (5%, jarvis_voice's own MIN_THRESHOLD) and the
    ceiling (100%) included."""
    for percent, cosine in ((5, 0.05), (25, 0.25), (35, 0.35), (50, 0.5),
                            (65, 0.65), (100, 1.0)):
        check(f"{percent}% is the cosine {cosine}",
              L._percent_to_cosine(percent) == cosine,
              L._percent_to_cosine(percent))
        check(f"... and {cosine} reads back as exactly {percent}%",
              L._cosine_to_percent(cosine) == percent,
              L._cosine_to_percent(cosine))
    check("the floor and the ceiling are the ones jarvis_voice itself clamps to",
          L._percent_to_cosine(5) == _voice().MIN_THRESHOLD
          and L._percent_to_cosine(100) == 1.0,
          (L._percent_to_cosine(5), _voice().MIN_THRESHOLD))
    check("every offered choice survives the round trip",
          all(L._cosine_to_percent(L._percent_to_cosine(p)) == p
              for p in L.find("voice_bar").choices))


def t_the_voice_bar_reads_the_print_and_the_clamp_holds():
    """The row's value comes from the REAL print, through jarvis_voice's own
    reader (`find_profile`, whose first step is `load_profile`) - including the
    clamp, so a hand-edited print can never show the owner a bar the check
    itself would never use."""
    _no_print()
    v = _voice()
    _make_print(0.5)
    check("a print whose bar is 0.5 shows 50%",
          L.value_of(L.find("voice_bar")) == 50, L.value_of(L.find("voice_bar")))
    check("... and it is the print's own number that was read",
          v.load_profile(VOICE_PROFILE).threshold == 0.5)
    _make_print(1.5)
    check("a bar above the ceiling is shown clamped, as 100%",
          L.value_of(L.find("voice_bar")) == 100, L.value_of(L.find("voice_bar")))
    check("... which is what jarvis_voice's own reader would use",
          v.load_profile(VOICE_PROFILE).threshold == 1.0)
    _make_print(-1.0)
    check("a bar below the floor is shown clamped, as 5%",
          L.value_of(L.find("voice_bar")) == 5, L.value_of(L.find("voice_bar")))
    check("... which is what jarvis_voice's own reader would use",
          v.load_profile(VOICE_PROFILE).threshold == v.MIN_THRESHOLD)
    _no_print()
    check("with no print at all the row falls back to its default, 35%",
          L.value_of(L.find("voice_bar")) == 35, L.value_of(L.find("voice_bar")))


def t_the_voice_bar_lowering_asks_and_raising_does_not():
    """LOWERING the bar is the loosening - a lower bar means MORE clips count as
    the owner's voice - and RAISING it is the safe direction. Proved by WATCHING
    the card path: the gate records every card it is asked for, and the print is
    read back through jarvis_voice."""
    _no_print()
    _make_print(0.5)
    cards = []
    reset(_says_yes(cards))
    check("the row starts at the print's own 50%",
          L.value_of(L.find("voice_bar")) == 50, L.value_of(L.find("voice_bar")))

    fresh()
    code, out = L.handle_post(L.ROUTE, {"key": "voice_bar", "value": 65})
    check("making the bar STRICTER applies at once and asks nobody",
          code == 200 and cards == [] and L.value_of(L.find("voice_bar")) == 65,
          (code, cards, L.value_of(L.find("voice_bar"))))
    check("... and is not called a loosening", out.get("loosening") is False, out)
    check("... and the print itself holds the new bar",
          _voice().load_profile(VOICE_PROFILE).threshold == 0.65)

    cards.clear()
    code, out = L.handle_post(L.ROUTE, {"key": "voice_bar", "value": 35})
    check("lowering it raises exactly ONE card", len(cards) == 1, cards)
    check("... under the lowering's OWN action name",
          bool(cards) and cards[0][0] == L.LOWER_ACTION, cards)
    check("... and never under the name that says 'raise'",
          all(action != L.RAISE_ACTION for action, _d, _p in cards), cards)
    check("the card names the bar and both percentages",
          bool(cards) and "from 65 to 35" in cards[0][2] and "35 %" in cards[0][2],
          cards[0][2] if cards else "")
    check("... and says what a LOWER bar lets through, not that Jarvis does more",
          bool(cards) and "more clips count as your voice" in cards[0][2]
          and "lets Jarvis do more" not in cards[0][2],
          cards[0][2] if cards else "")
    check("it is applied once approved, and reported as a loosening",
          code == 200 and out.get("loosening") is True and out.get("approved") is True
          and L.value_of(L.find("voice_bar")) == 35, (code, out))
    check("... and the PRINT is what now holds 0.35",
          _voice().load_profile(VOICE_PROFILE).threshold == 0.35)
    _no_print()


def t_the_voice_bar_lowering_refused_changes_nothing():
    """A denied card, a card that timed out and a PC that cannot ask all leave
    the print exactly as it was - and say so in the owner's words."""
    _no_print()
    for why, verdict, tier, words in (
            ("a denied card", Verdict(False, "denied"), "ask", "You said no"),
            ("a card that timed out", Verdict(False, "timed_out"), "ask", "not answered"),
            ("a PC whose Jarvis cannot ask", Verdict(True, "approved"), "auto",
             "nothing was changed")):
        _make_print(0.65)
        reset(lambda action, detail, prompt, v=verdict: v, tier)
        code, out = L.handle_post(L.ROUTE, {"key": "voice_bar", "value": 50})
        check(f"{why}: the lowering is refused with a code, not applied",
              code >= 400, (code, out))
        check(f"{why}: the print still holds 0.65",
              _voice().load_profile(VOICE_PROFILE).threshold == 0.65,
              _voice().load_profile(VOICE_PROFILE).threshold)
        check(f"{why}: and the answer says so in plain words",
              words in str(out.get("error")), out)
    _no_print()


def t_the_voice_bar_never_goes_below_the_models_own_floor():
    """"No bar below the model's own floor - not by enrolment, and not by a card
    either" is jarvis_voice's rule, and it is READ FROM jarvis_voice rather than
    restated here. So a lowering past the floor is refused BEFORE the owner is
    asked: no card is raised for a change that could not happen, and the print
    is untouched."""
    _no_print()
    _make_print(0.5)
    cards = []
    reset(_says_yes(cards))
    code, out = L.handle_post(L.ROUTE, {"key": "voice_bar", "value": 25})
    check("25% is refused below the small model's own 35% floor",
          code == 400, (code, out))
    check("... in the voice check's own words, as a percentage",
          "35%" in str(out.get("error")), out)
    check("... and NO card was raised for it", cards == [], cards)
    check("... and the print is untouched at 0.50",
          _voice().load_profile(VOICE_PROFILE).threshold == 0.5)

    cards.clear()
    _make_print(0.6, embedder="d51abcf31717")
    code, out = L.handle_post(L.ROUTE, {"key": "voice_bar", "value": 35})
    check("with the stronger model deciding, 35% is below its own 40% floor too",
          code == 400 and "40%" in str(out.get("error")), (code, out))
    check("... and still no card", cards == [], cards)
    code, out = L.handle_post(L.ROUTE, {"key": "voice_bar", "value": 50})
    check("but a lowering to 50%, above that floor, asks once and applies",
          code == 200 and [c[0] for c in cards] == [L.LOWER_ACTION]
          and _voice().load_profile(VOICE_PROFILE).threshold == 0.5, (code, cards))
    check("a number outside the row's own choices is refused as well",
          L.handle_post(L.ROUTE, {"key": "voice_bar", "value": 40})[0] == 400)
    _no_print()


def t_the_voice_bar_lives_only_in_the_print_and_is_never_logged():
    """The number has ONE home: the encrypted print, written by jarvis_voice.
    No settings file gains a key for it, no other file moves, the value read
    back after a write is the value written - and nothing about it is printed
    or logged."""
    _no_print()
    _make_print(0.65)
    p = fresh()
    before = p.read_bytes()
    files_before = _tree(TMP)
    reset(_says_yes())
    out_buf, err_buf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        code, out = L.handle_post(L.ROUTE, {"key": "voice_bar", "value": 50})
    check("the lowering went through", code == 200, (code, out))
    check("no settings file gained a key for it", p.read_bytes() == before)
    check("the value read back after the write is the value written",
          L.value_of(L.find("voice_bar")) == 50, L.value_of(L.find("voice_bar")))
    check("... and jarvis_voice's own reader finds it in the print",
          _voice().load_profile(VOICE_PROFILE).threshold == 0.5)
    files_after = _tree(TMP)
    changed = sorted(k for k, v in files_after.items() if files_before.get(k) != v)
    added = sorted(k for k in files_after if k not in files_before)
    check("the print is the ONLY file that changed",
          changed == [str(VOICE_PROFILE)], (changed, str(VOICE_PROFILE)))
    check("... and no new file appeared beside it", added == [], added)
    check("nothing about the bar was printed or logged",
          out_buf.getvalue() == "" and err_buf.getvalue() == "",
          (out_buf.getvalue(), err_buf.getvalue()))
    src = (HERE / "jarvis_limits.py").read_text(encoding="utf-8")
    check("the module that holds the row has no logging in it at all",
          "print(" not in src and "import logging" not in src
          and "logger" not in src)
    _no_print()


def t_the_voice_bar_loosening_is_wired_like_the_other_ones():
    """The loosening card is wired the way every other one is, and this is what
    keeping it safe depends on: the action has its own plain words, it is on the
    "What asks first" page, and - like `raise_a_limit` - nothing in the gate
    stack gives it a `_RISK` line, so the gate reads it as UNCLASSIFIED, which
    is exactly what makes jarvis_owner_check require the owner's own check
    (Windows Hello on this PC) before the card can be approved."""
    import jarvis_asks_first as AF
    import jarvis_card_words as W
    check("the card has its own plain words, and they say LOWER",
          W.title_for(L.LOWER_ACTION)
          == "Jarvis wants to lower the bar for your voice check",
          W.title_for(L.LOWER_ACTION))
    page = [a for _title, rows in AF.GROUPS for a in rows]
    check("the action is on the What asks first page", L.LOWER_ACTION in page)
    check("... which the existing loosening is on too", L.RAISE_ACTION in page)
    check("... and the two are different names",
          L.LOWER_ACTION and L.LOWER_ACTION != L.RAISE_ACTION)
    stack = ((REPO / "jarvis-backend" / "jarvis_gate.py")
             .read_text(encoding="utf-8", errors="replace")
             + "\n".join(q.read_text(encoding="utf-8", errors="replace")
                         for q in sorted(HERE.glob("*.patch"))))
    check("nothing in the gate stack classifies the new action, so the gate "
          "reads it as unclassified",
          L.LOWER_ACTION not in stack and L.RAISE_ACTION not in stack)
    check("an unclassified card is what makes the owner's check required "
          "(Windows Hello on the PC)",
          OC.is_risky({"action": L.LOWER_ACTION,
                       "risk": {"classified": False}}) is True)
    tiers = tomllib.loads(SHIPPED.read_text(encoding="utf-8"))["autonomy"]["tiers"]
    # The gate reads an action with no tier line of its own as "ask", which is
    # what keeps the card live - and an explicit "ask" is the same promise. What
    # must never happen is a LOOSER line ("auto", "local"), because then the
    # loosening could go through with no card at all. This checks the promise
    # rather than the absence of a line: the other session's
    # fix/two-raises-get-their-tier-lines (2026-10-09, merged) added explicit
    # `raise_a_limit` and `raise_attention_budget` lines, both "ask", and CI runs
    # this suite on the MERGE of this branch with main - so "no line" is no
    # longer the shape the truth takes.
    for action in (L.RAISE_ACTION, L.LOWER_ACTION):
        check(f"{action} is never looser than 'ask', so its card cannot be skipped",
              str(tiers.get(action, "ask")).strip().lower() == "ask", tiers.get(action))
    check("the row names its own gate action, not the raise's name",
          L.find("voice_bar").action == L.LOWER_ACTION
          and L.find("undo_window").action == "", L.find("voice_bar").action)


# --------------------------------------------------------------------------
#   This PC's own notifications - the seven the phone may change too
#   (the owner's decision of 2026-10-08)
# --------------------------------------------------------------------------
#: The seven values `jarvis_notify_prefs.py` owns, in the order the table
#: carries them, and the kind each row must have.
NOTIFY_ROWS = (
    ("notif_alarms", "bool"),
    ("notif_reminders", "bool"),
    ("notif_briefing", "bool"),
    ("notif_handoff", "bool"),
    ("notif_quiet_enabled", "bool"),
    ("notif_quiet_start", "time"),
    ("notif_quiet_end", "time"),
)


def t_the_notification_rows_are_on_the_table_and_say_whose_they_are():
    """Seven rows, one per value in the owner's `[notifications]` table, and the
    TWO things the owner's decision of 2026-10-08 demands of their words: every
    title says the setting is the PC's own ("on your PC"), and the quiet-hours
    switch keeps its own words for the state so a switch turned off is not a
    sentence pretending it is on."""
    check("all seven rows are on the table",
          [k for k, _ in NOTIFY_ROWS if L.find(k) is None] == [],
          [k for k, _ in NOTIFY_ROWS if L.find(k) is None])
    for key, kind in NOTIFY_ROWS:
        limit = L.find(key)
        if limit is None:
            continue
        check(f"{key}: carries the kind both screens draw for it",
              limit.kind == kind, (limit.kind, kind))
        check(f"{key}: says the setting is the PC's own",
              "(on your PC)" in limit.title, limit.title)
        check(f"{key}: names the value it owns in [notifications]",
              limit.section == "notifications"
              and limit.name == key[len("notif_"):], (limit.section, limit.name))
        check(f"{key}: carries no `[table].key` beyond its own",
              limit.source == "", limit.source)
        check(f"{key}: has the owner's own note", bool(limit.note), limit.note)
        check(f"{key}: is offered to BOTH apps", limit.app == "both", limit.app)
        check(f"{key}: and is not PC-only, so a phone may change it",
              limit.pc_only is False, limit.pc_only)
    # The defaults are `jarvis_notify_prefs.py`'s own, not typed twice.
    import jarvis_notify_prefs as NP
    for key, _kind in NOTIFY_ROWS:
        pref = key[len("notif_"):]
        check(f"{key}: defaults to the value the owning module uses",
              L.find(key).default == NP.DEFAULTS[pref],
              (L.find(key).default, NP.DEFAULTS[pref]))
    check("the quiet-hours switch is the row that decides whether the two "
          "times matter, and the table names it once",
          L.NOTIFY_QUIET_ON == "notif_quiet_enabled"
          and L.find(L.NOTIFY_QUIET_ON) is not None, L.NOTIFY_QUIET_ON)


def t_the_notification_rows_reach_both_apps_and_the_pc_keeps_them():
    """What the ROUTE answers, not what the table says. Each screen filters the
    one answer on each row's own `app`, so "offered to both apps" has to be
    proved on the wire - and it has to be proved that NOTHING turns a change
    into an approval card, because the one thing these rows must never do is
    leave an alarm unanswered while a card about it waits."""
    fresh()
    every = {r["key"]: r for r in L.view()["limits"]}
    desk = {r["key"]: r for r in L.view(app="desktop")["limits"]}
    phone = {r["key"]: r for r in L.view(app="phone")["limits"]}
    for key, kind in NOTIFY_ROWS:
        check(f"{key}: the unfiltered view the route serves has it",
              key in every, sorted(every))
        check(f"{key}: the desktop's own view has it", key in desk, sorted(desk))
        check(f"{key}: the phone's own view has it", key in phone, sorted(phone))
        row = phone.get(key) or {}
        check(f"{key}: the wire carries the kind the phone's plate draws",
              row.get("kind") == kind, row.get("kind"))
        check(f"{key}: the wire carries the owner's words",
              bool(row.get("words")) and bool(row.get("note")), row)
        if kind == "bool":
            check(f"{key}: a switch row sends true/false, never a number",
                  isinstance(row.get("value"), bool), row.get("value"))
        else:
            check(f"{key}: a time row sends the clock time itself, never a "
                  f"number of minutes",
                  isinstance(row.get("value"), str) and ":" in str(row.get("value")),
                  row.get("value"))
    # `quiet_on` is the one additive field this view ever gained: the two time
    # rows are worth drawing only while quiet hours are on, and each screen asks
    # the answer rather than guessing.
    check("the view says whether quiet hours are on, for every row",
          all("quiet_on" in r for r in L.view()["limits"]),
          [r["key"] for r in L.view()["limits"] if "quiet_on" not in r])
    check("... and it is the quiet-hours switch's own value",
          all(r["quiet_on"] is False for r in L.view()["limits"]))
    L.handle_post(L.ROUTE, {"key": L.NOTIFY_QUIET_ON, "value": True})
    check("... and it follows that switch",
          all(r["quiet_on"] is True for r in L.view()["limits"]))
    # The direction rule: "none" on all seven, so neither direction asks.
    for key, _kind in NOTIFY_ROWS:
        check(f"{key}: no direction of this row is a loosening",
              L.find(key).loosening == "none", L.find(key).loosening)
        check(f"{key}: ... and the legacy wire flag says so too",
              L.find(key).loosen_up is False, L.find(key).loosen_up)


def t_a_notification_write_lands_in_the_owners_toml():
    """A change from EITHER app goes through the one route and ends up in the
    owner's own `jarvis-framework.toml`, which is the whole point: the phone
    cannot reach the desktop's localStorage, and this is what the phone can
    reach. Proved by reading the FILE, not by reading the module's answer."""
    import jarvis_notify_prefs as NP
    cards = []
    reset(lambda action, detail, prompt: (cards.append((action, prompt)),
                                         Verdict(True, "approved"))[1])
    p = fresh()
    before = p.read_text(encoding="utf-8")
    code, out = L.handle_post(L.ROUTE, {"key": "notif_alarms", "value": False})
    check("a phone-sized change is accepted", code == 200 and out["ok"], (code, out))
    check("... with NO approval card, so an alarm is never left waiting on one",
          cards == [], cards)
    check("... and the file really says so",
          "alarms = false" in p.read_text(encoding="utf-8")
          and NP.read()["alarms"] is False, p.read_text(encoding="utf-8")[-320:])
    check("... and the answer is a sentence the owner can read",
          out["said"] == "Speak up when an alarm rings (on your PC): off.",
          out["said"])
    changed = [i for i, (a, b) in enumerate(
        zip(before.splitlines(), p.read_text(encoding="utf-8").splitlines()), 1)
        if a != b]
    check("exactly one line moved", len(changed) == 1, changed)
    check("every comment in the owner's file survives",
          before.count("#") == p.read_text(encoding="utf-8").count("#"))

    code, out = L.handle_post(L.ROUTE, {"key": "notif_quiet_start",
                                        "value": "23:30"})
    check("a quiet-hours time is accepted and written as a QUOTED clock time",
          code == 200 and 'quiet_start = "23:30"' in p.read_text(encoding="utf-8"),
          p.read_text(encoding="utf-8")[-320:])
    check("... and it reads back exactly", NP.read()["quiet_start"] == "23:30",
          NP.read()["quiet_start"])
    check("... and it never asked either", cards == [], cards)

    before_bad = p.read_bytes()
    for bad in (1320, "1320", "25:00", "nonsense"):
        code, out = L.handle_post(L.ROUTE, {"key": "notif_quiet_start",
                                            "value": bad})
        check(f"a time of day given as {bad!r} is refused, not stored as a "
              f"bare number", code == 400 and out.get("error"), (code, out))
        check(f"... in plain words that name the shape wanted ({bad!r})",
              "22:00" in str(out.get("error")), out.get("error"))
    check("... and not one byte was written by any of them",
          p.read_bytes() == before_bad)
    code, out = L.handle_post(L.ROUTE, {"key": "notif_alarms", "value": "perhaps"})
    check("a switch given a word that is neither on nor off is refused",
          code == 400 and "on or off" in str(out.get("error")), (code, out))
    code, out = L.handle_post(L.ROUTE, {"key": "notif_nonsense", "value": True})
    check("a row that does not exist is refused", code == 400, (code, out))


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
