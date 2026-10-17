"""test_gpu_memory.py - jarvis_hardware.gpu_memory_used(), the widget's GPU reader.

    python3 backend/test_gpu_memory.py

WHY THIS FILE EXISTS. `docs/CLAIMS.tsv` row A12 said "graphics memory is
offered as a fixed widget source", and the widget (`jarvis_widgets._gpu()`)
called `jarvis_hardware.gpu_memory_used()`. Until 2026-10-17 that function
existed in NO file: the tile fell through to (0.0, 0.0) on every PC and showed
"Could not read the graphics card just now." for ever - honest, but useless.
The function is now in jarvis_hardware.py, built from that module's own
nvidia-smi reader.

THE CONTRACT UNDER TEST is the one the existing caller already handles
(`jarvis_widgets.fill()`'s `gpu_memory` branch):

  * (used, total) in BYTES, summed over every card;
  * total == 0 means "could not read it" - the block shows NO value and the
    "could not read" note, never "0 GB used of 0 GB";
  * a real total with used == 0 IS a reading ("0.0 GB used of 8.0 GB"), and it
    must not be confused with the unknown value. That distinction is the point
    of this suite.

The nvidia-smi stub is `gen_hardware_cases.World`, whose rows are real-shaped
CSV in the CURRENT FIELDS_FULL shape - and the first check pins that column
count, because a fixture one field behind silently parses to no cards at all
(the #523 lesson: three hardware checks went red that way on main).
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _where import REPO  # noqa: E402

for p in (REPO / "tools", HERE / "rebuilt"):
    if str(p) not in sys.path:
        sys.path.append(str(p))

import gen_hardware_cases as G  # noqa: E402
import jarvis_compute as CP  # noqa: E402
import jarvis_hardware as H  # noqa: E402
import jarvis_widgets as W  # noqa: E402

FAILED, PASSED = [], []
SKIPPED = []

MiB = 1024.0 * 1024.0

#: An nvidia-smi row for a card with NOTHING on it: 8,192 MiB of memory, all
#: free. Same shape and column count as G.SMI_PAIR (see the first check).
SMI_EMPTY_CARD = (f"0, {G.U_2080S}, NVIDIA GeForce RTX 2080 SUPER, 8192, 8192, 7.5, "
                  f"Disabled, 00000000:07:00.0\n")


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def skip(why):
    """A check this machine cannot run: printed as `skip`, counted on its own,
    never as a pass."""
    SKIPPED.append(why)
    print(f"skip  {why}")


def gpu_block(reader) -> dict:
    """The widget's gpu_memory block for this reader - the caller under test."""
    return W.fill({"type": "progress", "source": "gpu_memory"}, W.Readers(gpu=reader))


def t_the_stub_rows_match_the_field_list():
    """A stub row with the wrong column count is SKIPPED by the parser, so it
    would empty the whole card list without saying so (#523 on main). Pin the
    shape before trusting any of the checks below."""
    want = len(CP.FIELDS_FULL.split(","))
    rows = [line for line in G.SMI_PAIR.strip().splitlines() if line.strip()]
    check(f"the nvidia-smi stub carries one column per FIELDS_FULL field ({want})",
          all(len(r.split(",")) == want for r in rows),
          [len(r.split(",")) for r in rows])
    cards = CP.parse_smi(G.SMI_PAIR, CP.FIELDS_FULL)
    check("... and the real parser reads both stub cards with their memory totals",
          [(c.total_mb, c.free_mb) for c in cards] == [(8192, 6980), (12288, 11650)],
          [(c.total_mb, c.free_mb) for c in cards])


def t_two_cards_are_both_reported():
    with G.World(smi=G.SMI_PAIR, log=G.ollama_log([G.LOG_2080S, G.LOG_2060]), reg=None):
        used, total = H.gpu_memory_used(fresh=True)
        block = gpu_block(lambda: H.gpu_memory_used())
    want_used = (8192 - 6980) + (12288 - 11650)
    check("two cards: (used, total) in bytes, both cards summed",
          used == want_used * MiB and total == (8192 + 12288) * MiB,
          (used / MiB, total / MiB))
    check("... and the total is both cards, not just the first one",
          total > 12288 * MiB, total / MiB)
    check("... so the tile shows the real numbers", block.get("value") == "1.8 GB used of 20 GB",
          block)
    check("... with the bar in the right place",
          abs(block.get("fraction") - round(want_used / (8192 + 12288), 3)) < 1e-9, block)


def t_unreadable_is_unknown_not_a_measurement():
    """The bug this replaces: a bare zero printed as a measurement. An
    unreachable nvidia-smi answers (0.0, 0.0) - total 0 is what the caller
    already reads as "could not read" - and the tile says so with no value."""
    with G.World(smi="", log=None, reg=None):
        got = H.gpu_memory_used(fresh=True)
        check("no nvidia-smi at all: exactly the unknown value (0.0, 0.0)",
              got == (0.0, 0.0), got)
        block = gpu_block(lambda: H.gpu_memory_used())
        check("... the tile shows NO value", block.get("value") == "", block)
        check("... and says it could not read the card", block.get("note") == W.NO_GPU, block)
        check("... and nothing prints a bare zero", "0 GB used of 0 GB" not in str(block), block)
    with G.World(smi="garbage\nnot, an, smi, row\n", log=None, reg=None):
        check("an nvidia-smi that answers junk is unknown too, not zero",
              H.gpu_memory_used(fresh=True) == (0.0, 0.0))
    with G.World(smi="", log=None, reg=None):
        check("the reader never raises: a broken world still answers the unknown value",
              H.gpu_memory_used(fresh=True) == (0.0, 0.0))


def t_an_empty_card_is_a_reading_not_an_unknown():
    """Control for the unknown: a card that IS readable and has nothing on it
    reports used 0 with its real total - a reading, printed as such, and never
    confused with "could not read"."""
    with G.World(smi=SMI_EMPTY_CARD, log=None, reg=None):
        got = H.gpu_memory_used(fresh=True)
        check("a card with nothing on it: used 0, but the real total",
              got == (0.0, 8192 * MiB), got)
        block = gpu_block(lambda: H.gpu_memory_used())
        check("... the tile prints the reading, not the could-not-read note",
              block.get("value") == "0.0 GB used of 8.0 GB", block)
        check("... and carries no note", not block.get("note"), block)
        unknown = gpu_block(lambda: (0.0, 0.0))
        check("... while the unknown value still shows no value",
              unknown.get("value") == "" and unknown.get("note") == W.NO_GPU, unknown)


def t_a_silly_free_reading_cannot_make_negative_use():
    """used = total - free per card; a driver claiming more free than total is
    clamped, so a silly row cannot report negative use or credit."""
    row = (f"0, {G.U_2080S}, NVIDIA GeForce RTX 2080 SUPER, 8192, 9000, 7.5, "
           f"Disabled, 00000000:07:00.0\n")
    with G.World(smi=row, log=None, reg=None):
        got = H.gpu_memory_used(fresh=True)
    check("free > total clamps to used 0, never a negative amount",
          got == (0.0, 8192 * MiB), got)


def t_a_poll_is_the_cached_arithmetic():
    """The tile polls. The reader must not spawn nvidia-smi on every poll: it
    reuses jarvis_compute.query_cards' 30 s cache, so one cold read asks
    nvidia-smi exactly once and warm polls are arithmetic only."""
    world = G.World(smi=G.SMI_PAIR, log=None, reg=None)
    calls = []
    real = world.run_smi

    def counting(args):
        calls.append(list(args))
        return real(args)

    world.run_smi = counting
    with world:
        cold = H.gpu_memory_used(fresh=True)
        asked_cold = len(calls)
        n = 500
        t0 = time.perf_counter()
        for _ in range(n):
            warm = H.gpu_memory_used()
        per_poll = (time.perf_counter() - t0) / n
        asked_after = len(calls)
    check("a cold read asks nvidia-smi exactly once", asked_cold == 1, calls)
    check("... and 500 warm polls ask it not at all (the read is cached)",
          asked_after == asked_cold, (asked_cold, asked_after))
    check("... and warm polls answer the same thing as the cold one", warm == cold, (warm, cold))
    check("... and a warm poll is well under a millisecond", per_poll < 0.001,
          f"{per_poll * 1e6:.2f} us")


def main():
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            print(f"--- {name} ---")
            try:
                fn()
            except Exception as exc:  # pragma: no cover - a crash is a failure
                traceback.print_exc()
                check(f"{name} ran without crashing", False, repr(exc))
    print(f"\n{len(PASSED)} passed, {len(SKIPPED)} skipped, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
