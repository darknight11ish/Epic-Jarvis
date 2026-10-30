"""test_presets_consistency.py - every preset is ONE state, ONE list, on both
screens (the owner, 2026-10-28: "make sure the presets for jarvis personality
and other presets are consistent too").

    python3 backend/test_presets_consistency.py

WHAT THIS PROVES, and why each check is here

The owner's report that started this work was a VOICE that disagreed with
every screen showing it: the list said Bella, the sound was George. The class
of bug is "a screen names one thing, the behaviour is another", so the checks
below are written against BEHAVIOUR, not against the list alone:

  * the personality list is the contract's ten, in the contract's order, with
    the contract's titles - not a second hand-typed list;
  * the row `GET /api/manner` marks as in use is the preset the PROMPT block
    really uses (`<jarvis_persona id="...">`), and the one the saved state
    really holds. All ten are driven, not one;
  * the voice numbers the list publishes for a preset are the preset's own
    numbers (blend, fallback, speed) - so a list can never describe a voice the
    speech path does not use;
  * the legacy `{"manner": "plain"}` write really moves the ONE preset state
    (it maps to `tactical_ops`), which is why a client must send
    `{"personality": id}` instead: this records the flattening the phone's
    write path avoids, rather than leaving it to be discovered;
  * every row carries the fields the phone's parser needs from the same GET
    (`id`, `title`, `description`, `builtin`) - a cross-app contract, checked
    where the answer is made;
  * the `manner` event rings ONCE for a real change, with the new personality
    in the frame, and NOT for a refused body or a damaged settings file (a real
    change also writes the one PC-wide voice, so its own `voices` event may sit
    beside it - `test_voice_one_state.py` owns that half, and this suite counts
    only its own doorbell);
  * the generated fixture both apps render from (`fixtures/work_presets.json`,
    `tools/gen_work_presets.py`) carries exactly the preset rows the live
    module would send - the fixture's `hardware` block is host-specific and is
    deliberately not compared.

WHAT IS REAL AND WHAT IS INJECTED. The real `jarvis_manner.py`,
`jarvis_presets.py` and the real contract are driven. Only the event bus is a
stand-in (it records instead of broadcasting); a fresh `OPENJARVIS_CONFIG_DIR`
is used, so the owner's own `manner.json` is never read or written.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

#: A scratch home BEFORE anything reads a settings file.
SCRATCH = Path(tempfile.mkdtemp(prefix="jarvis-presets-consistency-"))
os.environ["OPENJARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_CONFIG_DIR"] = str(SCRATCH)
os.environ["JARVIS_SUITE_RUNNING"] = "1"

sys.path.insert(0, str(HERE))

import jarvis_manner as M  # noqa: E402
import jarvis_presets as P  # noqa: E402

CONTRACT = json.loads((REPO / "contract" / "personalities.json").read_text(encoding="utf-8"))
FIXTURE = json.loads((HERE / "fixtures" / "work_presets.json").read_text(encoding="utf-8"))

FAILED: list = []
PASSED: list = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}"
          + (f"\n        {detail}" if detail and not cond else ""))


# --------------------------------------------------------------------------
# A recording event bus. `jarvis_manner._publish` imports `jarvis_events` and
# calls `BUS.publish(kind, data)`; this replaces exactly that, so the check is
# about what the module really publishes rather than about a mock it never
# reaches.
# --------------------------------------------------------------------------
class _Recorder:
    def __init__(self):
        self.frames = []

    def publish(self, kind, data=None):
        self.frames.append((kind, data))
        return None

    def kinds(self):
        return [k for k, _ in self.frames]


def _with_bus():
    rec = _Recorder()
    fake = types.ModuleType("jarvis_events")
    fake.BUS = rec
    previous = sys.modules.get("jarvis_events")
    sys.modules["jarvis_events"] = fake
    return rec, previous


def _restore_bus(previous):
    if previous is None:
        sys.modules.pop("jarvis_events", None)
    else:
        sys.modules["jarvis_events"] = previous


# --------------------------------------------------------------------------
# 1. The list is the contract's, in the contract's order.
# --------------------------------------------------------------------------
def t_the_personality_list_is_the_contracts_ten():
    view = M.view()
    rows = view["personalities"]
    expected = CONTRACT["personalities"]
    check("the answer lists ten built-ins",
          len([r for r in rows if r.get("builtin")]) == len(expected),
          f"{len(rows)} rows, {len(expected)} in the contract")
    check("the ids are the contract's ids, in the contract's order",
          [r["id"] for r in rows if r.get("builtin")] == [p["id"] for p in expected],
          json.dumps([r["id"] for r in rows])[:300])
    check("the titles are the contract's titles, in the same order",
          [r["title"] for r in rows if r.get("builtin")] == [p["title"] for p in expected],
          json.dumps([r["title"] for r in rows])[:300])
    check("the default is the contract's default",
          view["personality_default"] == CONTRACT["default"], view["personality_default"])


# --------------------------------------------------------------------------
# 2. THE MARK IS THE BEHAVIOUR. All ten driven: the row marked in use is the
#    preset the prompt block really uses and the state really holds - the class
#    of bug behind "the screen says Bella, the sound is George".
# --------------------------------------------------------------------------
def t_the_marked_row_is_the_preset_the_prompt_really_uses():
    for preset in CONTRACT["personalities"]:
        pid = preset["id"]
        ok, said = M.set_personality(pid)
        if not ok:
            check(f"{pid}: switches", False, said)
            continue
        view = M.view()
        marked = [r["id"] for r in view["personalities"]
                  if r.get("builtin") and r["id"] == view["personality"]]
        block = M.prompt_block()
        check(f"{pid}: the marked row is the saved state",
              view["personality"] == pid and M.current_personality() == pid,
              f"marked {view['personality']}, state {M.current_personality()}")
        check(f"{pid}: the prompt block names the marked preset",
              f'<jarvis_persona id="{pid}"' in block,
              block[:160])
        check(f"{pid}: exactly one row can be in use",
              marked == [pid], json.dumps(marked))
        check(f"{pid}: the switch line is the preset's own",
              said == preset["switch_ack"], said)


# --------------------------------------------------------------------------
# 3. The voice a row publishes is the preset's own voice data - no second copy
#    for a screen to disagree with. This is the voice-override class of bug,
#    checked as "list vs the data the speech path reads".
# --------------------------------------------------------------------------
def t_a_rows_voice_is_its_own_voice_data():
    for preset in CONTRACT["personalities"]:
        pid = preset["id"]
        M.set_personality(pid)
        row = next(r for r in M.view()["personalities"] if r["id"] == pid)
        own = M.preset(pid)
        check(f"{pid}: the listed blend/fallback/speed are the preset's own",
              row["voice_blend"] == own["voice_blend"] == preset["voice_blend"]
              and row["voice"]["fallback"] == own["voice_fallback"] == preset["voice_fallback"]
              and float(row["voice_speed"]) == float(preset["voice_speed"])
              and M.preset(pid)["voice_speed"] == row["voice_speed"],
              json.dumps(row["voice"]) + " vs " + json.dumps(preset["voice_fallback"]))
        # The switch that decides whether a preset's voice is applied at all is
        # the SAME setting the view publishes - one switch, not two.
        check(f"{pid}: the view's voice_sync is the setting",
              row["voice_speed"] == preset["voice_speed"]
              and M.view()["voice_sync"] == M.sync_voice_enabled())


# --------------------------------------------------------------------------
# 4. The legacy word really moves the ONE state - recorded, because it is the
#    reason a client sends `personality` and never a manner word.
# --------------------------------------------------------------------------
def t_the_legacy_manner_word_moves_the_one_preset_state():
    M.set_personality("classic_butler")
    before = M.view()["personality"]
    code, body = M.handle_set({"manner": "plain"})
    check("the legacy write is accepted", code == 200 and body.get("ok") is True,
          f"{code} {body}")
    check("it really moves the preset (plain maps to tactical_ops)",
          before == "classic_butler" and M.view()["personality"] == "tactical_ops",
          f"{before} -> {M.view()['personality']}")
    check("and the prompt follows it, so no screen may mark the old one",
          '<jarvis_persona id="tactical_ops"' in M.prompt_block(),
          M.prompt_block()[:120])
    # Back to the default for the checks after this one.
    M.set_personality(CONTRACT["default"])


# --------------------------------------------------------------------------
# 5. The row shape the phone parses is the row shape the PC makes.
# --------------------------------------------------------------------------
def t_every_row_carries_what_a_client_parses():
    rows = M.view()["personalities"]
    bad = [r for r in rows
           if not (isinstance(r.get("id"), str) and r["id"]
                   and isinstance(r.get("title"), str) and r["title"]
                   and isinstance(r.get("description"), str) and r["description"]
                   and isinstance(r.get("builtin"), bool))]
    check("every row has id, title, a non-empty description and builtin", not bad,
          json.dumps(bad)[:400])
    check("the active id is one of the listed ids",
          M.view()["personality"] in {r["id"] for r in rows},
          M.view()["personality"])


# --------------------------------------------------------------------------
# 6. ONE doorbell per real change, and silence for a change that did not happen.
# --------------------------------------------------------------------------
def t_the_manner_event_rings_once_for_a_real_change():
    rec, previous = _with_bus()
    try:
        code, _body = M.handle_set({"personality": "dry_wit"})
        # 2026-10-30: a personality switch also gives the one PC-wide voice that
        # preset's voice (`jarvis_manner._apply_personality_voice`, the owner's
        # 2026-10-28 report), and that write publishes ONE `voices` event - by
        # design, the same event the Voices screen makes (see
        # test_voice_one_state.py, which owns that half). What this test is
        # about is the `manner` doorbell, so it counts THAT kind and lets the
        # voice event through. Asserting the whole event list here failed on
        # main after that change and proved nothing about this screen.
        manner = [data for kind, data in rec.frames if kind == "manner"]
        check("a personality switch rings `manner` once",
              code == 200 and len(manner) == 1, json.dumps(rec.kinds()))
        frame = manner[0] if manner else {}
        check("the frame carries the new preset and the one manner word",
              isinstance(frame, dict)
              and frame.get("personality") == "dry_wit"
              and frame.get("manner") in M.MANNERS
              and frame.get("manner") == M.current(),
              json.dumps(frame)[:300])
        rec.frames.clear()
        code, _body = M.handle_set({"personality": "not-a-personality"})
        check("a refused switch rings nothing",
              code == 400 and rec.frames == [], f"{code} {rec.kinds()}")
        rec.frames.clear()
        M.handle_set({"humor": True})
        check("humour rings it too - one doorbell for this whole screen",
              rec.kinds().count("manner") == 1, json.dumps(rec.kinds()))
    finally:
        _restore_bus(previous)


def t_a_damaged_file_rings_nothing_and_changes_nothing():
    path = M.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    rec, previous = _with_bus()
    try:
        code, body = M.handle_set({"personality": "dry_wit"})
        check("a damaged manner.json refuses the write",
              code in (400, 500) and body.get("ok") is False, f"{code} {body}")
        check("and rings nothing", rec.frames == [], json.dumps(rec.kinds()))
    finally:
        _restore_bus(previous)
        try:
            path.unlink()
        except OSError:
            pass
        for suffix in (".bak", ".tmp"):
            try:
                path.with_name(path.name + suffix).unlink()
            except OSError:
                pass


# --------------------------------------------------------------------------
# 7. The fixture both apps render from is the live module's own rows.
# --------------------------------------------------------------------------
def t_the_shared_fixture_is_the_live_preset_rows():
    live = [p.view() for p in P.PRESETS]
    check("the fixture's presets are the live module's rows",
          FIXTURE.get("presets") == live,
          f"{len(FIXTURE.get('presets') or [])} fixture rows, {len(live)} live")
    check("the fixture's replaced ids are the module's",
          FIXTURE.get("old_ids_replaced") == list(P.OLD_IDS),
          json.dumps(FIXTURE.get("old_ids_replaced")))
    check("the fixture names the generator that writes it",
          FIXTURE.get("generated_by") == "tools/gen_work_presets.py",
          str(FIXTURE.get("generated_by")))


TESTS = [
    t_the_personality_list_is_the_contracts_ten,
    t_the_marked_row_is_the_preset_the_prompt_really_uses,
    t_a_rows_voice_is_its_own_voice_data,
    t_the_legacy_manner_word_moves_the_one_preset_state,
    t_every_row_carries_what_a_client_parses,
    t_the_manner_event_rings_once_for_a_real_change,
    t_a_damaged_file_rings_nothing_and_changes_nothing,
    t_the_shared_fixture_is_the_live_preset_rows,
]


def main() -> int:
    for fn in TESTS:
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception:
            import traceback
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
