"""test_storage.py - what this machine can hold, and the rule that keeps it working.

    python backend/test_storage.py

WHY (the owner, 2026-10-10)
    "I have a lot of space on my D drive ssd that has 4tb ... this may not be
    the case for everyone that installs epic jarvis on their desktop." So the
    model chooser must read the machine in front of it, and two things must
    never happen: a disk filled up, and a download nobody agreed to. The night
    this was written, C: hit 5.7 GB free and every build on the machine failed;
    a stalled 12.85 GB download is what did it.

Every check here fails on the code before jarvis_storage.py existed: there was
no storage awareness anywhere, so every tier was offered on every machine and
nothing checked free space before a download.

No model, no network, no Ollama: the machine is a dictionary handed in, so the
tests do not depend on the PC they run on.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jarvis_storage as S  # noqa: E402

PASSED, FAILED = [], []

GB = 1024 ** 3


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


def profile(free_gb, cards=((8, 6),), installed=()):
    """A made-up PC, so the tests do not depend on the one they run on."""
    return {
        "models_drive": "D:\\Jarvis Models",
        "free_bytes": int(free_gb * GB),
        "cards": [{"name": f"card {i}", "vram_total": int(t * GB), "vram_free": int(f * GB)}
                  for i, (t, f) in enumerate(cards)],
        "card_count": len(cards),
        "total_vram": int(sum(t for t, _ in cards) * GB),
        "biggest_card_vram": int(max((t for t, _ in cards), default=0) * GB),
        "installed": sorted(installed),
    }


def tier(offered, name):
    for t in offered["tiers"]:
        if t["id"] == name:
            return t
    return None


# --------------------------------------------------------------------------
# 1. The owner's own machine gets everything
# --------------------------------------------------------------------------

print("--- the owner's machine (3.6 TB free, one 8 GB card) ---")
owner = profile(3600, cards=((8, 7), (12, 11)))
offered = S.offer(owner)
check("a big drive offers the top tier", tier(offered, "generous")["fits"])
check("and suggests the biggest tier that fits, not the smallest",
      offered["recommended"] == "generous",
      f"recommended {offered['recommended']!r}")
for name in ("lean", "comfortable", "generous"):
    t = tier(offered, name)
    check(f"{name} is offered on a big drive", bool(t and t["fits"]), t and t["why_not"])
print()

# --------------------------------------------------------------------------
# 2. A small laptop SSD gets the small set, said plainly
# --------------------------------------------------------------------------

print("--- a small SSD with 20 GB free ---")
# Note the arithmetic the rule implies: Lean costs 15 GB and the safe margin is
# 25 GB, so a machine needs 40 GB free to be offered Lean at all. 20 GB free is
# a machine that should be told to free some space, not one to download onto -
# which is why the first check below is a refusal, and why the drive-name check
# uses the refusal's own words rather than an escape sequence.
small = profile(20, cards=())
tiny = S.offer(small)
check("Lean is refused when 20 GB free cannot cover its 15 GB and the 25 GB margin",
      not tier(tiny, "lean")["fits"], tier(tiny, "lean")["why_not"])
check("Comfortable is refused on a small SSD", not tier(tiny, "comfortable")["fits"])
check("Generous is refused on a small SSD", not tier(tiny, "generous")["fits"])
check("the refusal explains the free-space rule in plain words",
      "keeps at least" in tier(tiny, "comfortable")["why_not"],
      tier(tiny, "comfortable")["why_not"])
check("the refusal names the drive it is talking about",
      "D:\\Jarvis Models" in tier(tiny, "comfortable")["why_not"],
      tier(tiny, "comfortable")["why_not"])
# Nothing fits here, so there is nothing to recommend - and that must be said,
# never papered over by suggesting a tier that does not fit.
check("no tier is recommended when none fits", tiny["recommended"] is None,
      f"recommended {tiny['recommended']!r}")
yes, why = S.may_download("qwen3:8b", 4.9, small, agreed=True)
check("and a download onto that machine is refused too", yes is False, why)

# A machine with a real SSD and room: Lean is exactly what it should be offered.
roomy_small = S.offer(profile(60, cards=()))
check("Lean fits a small SSD with 60 GB free", tier(roomy_small, "lean")["fits"],
      tier(roomy_small, "lean")["why_not"])
check("and Lean is what is recommended there", roomy_small["recommended"] == "lean",
      f"recommended {roomy_small['recommended']!r}")
print()

# --------------------------------------------------------------------------
# 2b. No graphics card, but plenty of disk: refused for the CARD, not the size
# --------------------------------------------------------------------------

print("--- plenty of disk, no graphics card ---")
big_no_card = S.offer(profile(2000, cards=()))
check("with 2 TB free and no card, Comfortable is refused for the card",
      "graphics card" in tier(big_no_card, "comfortable")["why_not"],
      tier(big_no_card, "comfortable")["why_not"])
check("and it is NOT refused for disk space",
      "free" not in tier(big_no_card, "comfortable")["why_not"],
      tier(big_no_card, "comfortable")["why_not"])
print()

# --------------------------------------------------------------------------
# 3. THE ONE THAT MATTERS: the night C: hit 5.7 GB free
# --------------------------------------------------------------------------

print("--- the night C: fell to 5.7 GB free ---")
about_to_break = profile(30, cards=((8, 6),))
yes, why = S.may_download("gpt-oss:20b", 12.85, about_to_break, agreed=True)
check("a 12.85 GB download that would leave 17 GB free is refused",
      yes is False, why)
check("and the refusal says how much free space is kept",
      "25 GB" in why, why)
check("and it says what to do instead",
      ("Free some space" in why or "another drive" in why), why)
check("and it names the 5.7 GB night, so the rule has evidence",
      "5.7 GB" in why, why)

plenty = profile(500, cards=((8, 6),))
yes2, why2 = S.may_download("gpt-oss:20b", 12.85, plenty, agreed=True)
check("the same download IS allowed when there is room", yes2 is True, why2)
print()

# --------------------------------------------------------------------------
# 4. Never a silent download
# --------------------------------------------------------------------------

print("--- never a silent download ---")
yes, why = S.may_download("qwen3.5:9b", 6.1, profile(500), agreed=False)
check("a download without a yes is refused", yes is False, why)
check("and the refusal asks for the yes rather than doing it",
      "without you saying yes" in why, why)
check("and it says how big the download is", "6.1 GB" in why, why)
print()

# --------------------------------------------------------------------------
# 5. A model already on disk is not downloaded again
# --------------------------------------------------------------------------

print("--- a model already on disk ---")
yes, why = S.may_download("qwen3:8b", 4.9, profile(500, installed=["qwen3:8b"]), agreed=True)
check("a model already here is not downloaded again", yes is True, why)
check("and it says so, rather than pretending to download", "already here" in why, why)
print()

# --------------------------------------------------------------------------
# 6. No card: say so once, and do not claim the model will be fast
# --------------------------------------------------------------------------

print("--- a PC with no graphics card ---")
noc = profile(500, cards=())
off = S.offer(noc)
check("Lean is still offered without a card", tier(off, "lean")["fits"])
check("Comfortable needs a card and says so",
      not tier(off, "comfortable")["fits"] and "graphics card" in tier(off, "comfortable")["why_not"],
      tier(off, "comfortable")["why_not"])
print()

# --------------------------------------------------------------------------
# 6b. Reading the REAL hardware shape (the bug this test exists for)
# --------------------------------------------------------------------------

print("--- reading what jarvis_hardware.detect() actually returns ---")
# detect() names its fields `total_gib` and `free_gib`, in GiB - not bytes, and
# not `memory_total`. The first version of cards_from() read the wrong names,
# so every card came out as 0 GB and the chooser told a two-card, 20 GB PC that
# Comfortable would not fit. This pins the real shape.
real_shape = {"cards": [
    {"name": "NVIDIA GeForce RTX 2060", "total_gib": 12.0, "free_gib": 11.0},
    {"name": "NVIDIA GeForce RTX 2080 Super", "total_gib": 8.0, "free_gib": 7.5},
]}
cards = S.cards_from(real_shape)
check("two cards are read from the real detect() shape", len(cards) == 2, str(cards))
check("the first card's total video memory comes out as 12 GB",
      cards[0]["vram_total"] == 12 * GB, str(cards[0]))
check("its free video memory comes out as 11 GB",
      cards[0]["vram_free"] == 11 * GB, str(cards[0]))
check("the largest card is recognised as 12 GB, not 0",
      max(c["vram_total"] for c in cards) == 12 * GB)
real_profile = S.machine_profile("D:\\Jarvis Models", hardware=real_shape)
check("so a two-card PC gets a real card count",
      real_profile["card_count"] == 2, str(real_profile["card_count"]))
check("and its largest card is 12 GB",
      real_profile["biggest_card_vram"] == 12 * GB,
      str(real_profile["biggest_card_vram"]))
check("a card with no memory reported is 0, never assumed",
      S.cards_from({"cards": [{"name": "mystery"}]})[0]["vram_total"] == 0)
check("a junk card list yields no cards rather than a guess",
      S.cards_from({"cards": "nonsense"}) == [])
check("no hardware at all yields no cards", S.cards_from(None) == [])
print()

# --------------------------------------------------------------------------
# 7. Every tier says what the owner asked to see, before anything is chosen
# --------------------------------------------------------------------------

print("--- what every tier must say (the owner's own list) ---")
for t in S.TIERS:
    check(f"{t['id']}: has a plain name", bool(t.get("name")))
    check(f"{t['id']}: says what it is for", bool(t.get("for")))
    check(f"{t['id']}: says what it costs on disk", t.get("needs_disk", 0) > 0)
    check(f"{t['id']}: has at least one model", len(t.get("models", ())) > 0)
    for m in t.get("models", ()):
        check(f"{t['id']}/{m['id']}: says what the model is for", bool(m.get("plain")))
        check(f"{t['id']}/{m['id']}: says its size on disk", m.get("gb", 0) > 0)
        check(f"{t['id']}/{m['id']}: says which card it uses", bool(m.get("card")))
        check(f"{t['id']}/{m['id']}: says the video memory it wants", m.get("needs_vram", 0) > 0)
print()

# --------------------------------------------------------------------------
# 8. The opt-in fiction model: labelled, costed, and never the everyday one
# --------------------------------------------------------------------------

print("--- the opt-in fiction model (owner, 2026-10-10) ---")
gen = tier(S.offer(owner), "generous")
opt = gen.get("opt_in") or []
check("Generous carries the opt-in choices", len(opt) >= 1)
check("the opt-in is marked opt-in, not a normal model",
      all("opt-in" in S.words_for(gen).lower() for _ in [0]))
check("the opt-in label carries the measured cost",
      all(m.get("cost") for m in opt), [m.get("id") for m in opt])
check("the cost names TruthfulQA and the point drop",
      any("TruthfulQA" in m.get("cost", "") and "5.8" in m.get("cost", "") for m in opt))
check("no everyday tier's NORMAL model list contains the abliterated file",
      all("abliterated" not in m["id"] for t in S.TIERS for m in t.get("models", ())))
check("the opt-in model is not the default recommendation",
      all(m["id"] not in [x["id"] for x in tier(S.offer(owner), t)["models"]]
          for m in opt for t in ("lean", "comfortable", "generous")))
print()

# --------------------------------------------------------------------------
# 9. The words the owner reads
# --------------------------------------------------------------------------

print("--- one tier as the owner reads it ---")
words = S.words_for(tier(S.offer(owner), "generous"))
check("the words name the tier", "Generous" in words)
check("the words say what it is for", "big drive" in words)
check("the words give the size on disk", "GB on disk" in words)
check("the words say how much stays free", "free" in words)
check("the words name a card", "card" in words)
check("the words carry the opt-in cost", "TruthfulQA" in words)
refused_words = S.words_for(tier(S.offer(profile(20, cards=())), "generous"))
check("a refused tier says why in the same words", "Not offered on this PC" in refused_words,
      refused_words)
print()

# --------------------------------------------------------------------------
# 10. A drive that cannot be measured is treated as having nothing
# --------------------------------------------------------------------------

print("--- when the drive cannot be asked about ---")
# Why this asks the CONTRACT rather than handing over a made-up path:
# `shutil.disk_usage("Q:\\no\\such\\drive")` and a POSIX path behave
# differently. On POSIX a plain string is a relative path, so it resolves
# against the working directory and happily reports the free space of the
# drive the tests run from - which made this check pass on Windows and fail
# in CI. What matters is not which nonsense path is refused, it is that a
# drive which CANNOT be measured reads as zero, never as plenty, so
# `disk_usage` raising is what is pinned here.
import shutil as _shutil  # noqa: E402
import tempfile as _tempfile  # noqa: E402


def _raise(*_a, **_k):
    raise OSError("no such drive")


_orig = _shutil.disk_usage
_shutil.disk_usage = _raise
try:
    got = S.free_bytes(_tempfile.gettempdir())
finally:
    _shutil.disk_usage = _orig
check("a drive that cannot be measured reads as zero free, never as plenty", got == 0, str(got))
check("and the real call still reads a real number for a real folder",
      S.free_bytes(_tempfile.gettempdir()) > 0)
yes, why = S.may_download("qwen3:8b", 4.9, {"installed": [], "free_bytes": 0,
                                           "models_drive": "Q:\\gone"}, agreed=True)
check("so a download onto an unmeasurable drive is refused", yes is False, why)
print()

# --------------------------------------------------------------------------
# 11. This PC, for the record (never a failure - the owner's machine may differ)
# --------------------------------------------------------------------------

print("--- this PC, read live (for the report; not a pass or a fail) ---")
try:
    import jarvis_hardware as H
    hw = None
    try:
        hw = H.detect(fresh=False)
    except Exception as exc:  # a machine with no nvidia-smi is not a failure
        print(f"      hardware detection said: {exc}")
    live = S.machine_profile("D:\\Jarvis Models", hardware=hw, installed=[])
    print(f"      drive           : {live['models_drive']}")
    print(f"      free            : {live['free_bytes'] / GB:.1f} GB")
    print(f"      cards           : {live['card_count']} ({live['total_vram'] / GB:.0f} GB total, "
          f"{live['biggest_card_vram'] / GB:.0f} GB largest)")
    live_offer = S.offer(live)
    print(f"      suggested tier  : {live_offer['recommended']}")
    for t in live_offer["tiers"]:
        print(f"      {t['name']:<12} fits={t['fits']}  {('' if t['fits'] else t['why_not'])}")
except Exception as exc:
    print(f"      could not read this PC: {exc}")
print()

print(f"PASS {len(PASSED)}   FAIL {len(FAILED)}")
if FAILED:
    print()
    for name in FAILED:
        print(f"FAILED: {name}")
sys.exit(1 if FAILED else 0)
