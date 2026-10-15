"""test_cloud_lane_precondition.py - the memory-injection switch gates the lanes.

    python3 backend/test_cloud_lane_precondition.py

WHY THIS EXISTS. `jarvis_hud.py` does not pass its configured cloud lanes to
`jarvis_router.choose()` while Jarvis is injecting the owner's facts itself:

    lanes=[] if jarvis_side_memory else lanes

with `jarvis_side_memory = jarvis_injects_memory()`, which reads
`[agent] context_from_memory` (`jarvis_hud.py:1835`). So that one setting is a
HARD switch on the whole cloud lane, and the comments say why
(`backend/cloud-say-yes.patch:10-12`): *"While Jarvis injects memory itself we
cannot escalate safely: it would attach your facts to a free-tier cloud
request."*

WHY IT IS NOT ALREADY COVERED. `test_cloud_say_yes.py` tests that the patch wires
`cloud_yes` through to `choose()`'s `owner_said_yes` gate; `test_rebuilt.py` and
`test_chat_stream_contract.py` test that gate itself. **None of them tests that
an empty lane list is what keeps the offer from ever being made** - which is the
single fact that decides whether cloud escalation is reachable at all. Read off
the owner's PC on 2026-10-13: every route in his log said
`gate: "privacy"`, `reason: "escalation off while Jarvis injects memory itself"`,
and the distinct set of gates in a whole day was exactly `{privacy}`.

WHAT IT PROVES, and what it would catch:
  1. A question that is complex and clean is OFFERED a lane when lanes are
     passed - so the lanes below really do qualify, and the test is not passing
     because escalation is broken for some other reason.
  2. The SAME question with `lanes=[]` - what the HUD passes while memory is
     injected server-side - is answered locally and offers NOTHING.
  Together those two are the bite: if `lanes=[]` ever stopped suppressing the
  offer (or the offer stopped appearing when lanes are passed), one of the two
  controls goes red.

No model, no network, no port: `choose()` is pure.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "rebuilt"))

import jarvis_router as R  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"{'ok   ' if cond else 'FAIL '} {name}" + (f"\n        {detail}" if detail and not cond else ""))


#: The three lanes the owner's own ~/.openjarvis/litellm-proxy.yaml defines.
LANES = ["jarvis-escalate", "jarvis-critic", "jarvis-bulk"]
LOCAL = "qwen3.5:9b"
#: Plainly non-private, and long enough that the complexity gate passes it.
HARD = ("Explain in detail how the three-body problem differs from the two-body "
        "problem, and why the difference matters for predicting orbits.")


print("--- the lane really does qualify ---")
d_with = R.choose(HARD, local_model=LOCAL, lanes=LANES,
                  conversation_tainted=False, has_image=False)
check("with the lanes passed, this question is OFFERED one (gate 'offer')",
      d_with.gate == "offer", f"gate={d_with.gate!r} reason={d_with.reason!r}")
check("... and the offer names a real lane",
      getattr(d_with, "offer", "") in LANES,
      f"offer={getattr(d_with, 'offer', None)!r}")
check("... and it still answers LOCALLY for now - an offer is not an escalation",
      d_with.lane == LOCAL, f"lane={d_with.lane!r}")
check("... and it does NOT carry memory to a cloud lane",
      d_with.inject_memory is not False or d_with.lane == LOCAL,
      f"inject_memory={d_with.inject_memory}")

print()
print("--- lanes=[] is what suppresses the offer entirely ---")
d_without = R.choose(HARD, local_model=LOCAL, lanes=[],
                     conversation_tainted=False, has_image=False)
check("with lanes=[], the SAME question is answered locally",
      d_without.lane == LOCAL, f"lane={d_without.lane!r}")
check("with lanes=[], NO offer is made at all (the cloud switch)",
      not getattr(d_without, "offer", None),
      f"offer={getattr(d_without, 'offer', None)!r} gate={d_without.gate!r}")
check("with lanes=[], the gate is not 'offer'",
      d_without.gate != "offer", f"gate={d_without.gate!r}")

print()
print("--- the two controls differ, which is the whole point ---")
check("the same question behaves differently with and without its lanes",
      (d_with.gate == "offer") and (d_without.gate != "offer"),
      f"with={d_with.gate!r} without={d_without.gate!r}")

print()
print("--- the caller's own switch still exists (this is the real guard) ---")
# The check above proves choose() BEHAVES correctly when handed no lanes. It
# cannot catch the actual regression, which is the CALLER: if jarvis_hud.py
# stopped passing `lanes=[]` while Jarvis injects memory itself, the offer would
# come back and this file's first checks would still pass. So the switch itself
# is read from the source. jarvis_hud.py is not in this repository, so this is
# skipped where it is absent and says so rather than passing quietly.
# jarvis_hud.py is not beside this suite: the tracked copy lives in
# `jarvis-backend/`, which is the published base folder.
HUD = HERE.parent / "jarvis-backend" / "jarvis_hud.py"
if not HUD.is_file():
    HUD = HERE / "jarvis_hud.py"
if not HUD.is_file():
    print("skip  jarvis_hud.py was not found (neither jarvis-backend/ nor beside "
          "this suite), so the caller's switch could not be read here")
else:
    print(f"     (reading {HUD.name} from {HUD.parent.name}/)")
    src = HUD.read_text(encoding="utf-8", errors="replace")
    check("jarvis_hud.py still empties the lane list while memory is injected",
          "lanes=[] if jarvis_side_memory else lanes" in src,
          "the line `lanes=[] if jarvis_side_memory else lanes` is gone from "
          "jarvis_hud.py - the switch that keeps a memory-carrying turn off the "
          "cloud lanes may have been removed or weakened")
    check("... and jarvis_side_memory still comes from the memory setting",
          "jarvis_side_memory = jarvis_injects_memory()" in src
          and "context_from_memory" in src,
          "jarvis_side_memory no longer tracks jarvis_injects_memory() / "
          "context_from_memory, so the two could drift apart")

print()
print(f"PASS {len(PASSED)}   FAIL {len(FAILED)}")
if FAILED:
    print()
    for name in FAILED:
        print(f"FAILED: {name}")
sys.exit(1 if FAILED else 0)
