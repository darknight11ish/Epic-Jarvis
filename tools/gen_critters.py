#!/usr/bin/env python3
"""Generate both apps' copies of the animal faces from one source.

Each face (red panda, pygmy owl, sea otter, monkey, robot) is drawn by one shader, built
from three parts in `jarvis-desktop/critters/`: `common_head.sksl` (shared
uniforms and helpers) + `<animal>.sksl` (its shapes and colours) +
`common_tail.sksl` (the shared march, lighting, orb and soft outline). The
desktop draws with WebGL2 (GLSL) and the phone with
android.graphics.RuntimeShader (AGSL); the two languages agree on almost
everything except the names of their vector types, so the source is written
with AGSL's names and the desktop copy gets a handful of `#define`s on top.
Each app then adds its own few-line `main`, because the two differ in how a
pixel's position arrives.

It also writes the POSE fixture. Each animal's body language is worked out
once a frame by JavaScript on the desktop (`critter-pose.js`,
`critter-owl.js`, `critter-otter.js`) and by line-for-line Kotlin copies on
the phone. This runs the JavaScript under node at fixed moments and saves
what it returns; the phone's `CritterPoseTest` fails if a Kotlin copy
disagrees, so the two cannot drift apart quietly. And the same for the
sleeping Zs drawn over an animal on standby (`zs` in `critter-pose.js`,
`CritterPose.zs` on the phone): their numbers and their answers go into
`critter-zs-golden.json`, which the same test reads. And whether an idle
happening is playing (`busy` in each pose file), which both apps' frame pacers
read, and whether one of its own talking gestures is (`gesturing`), which both
hosts read before handing the pose Jarvis's phrase ends:
`critter-busy-golden.json`. And the slow wander that replaces the shared sines
(`noise`, `breathWave`) and the host's look-ahead for phrase ends (`aheadStep`):
`critter-drift-golden.json`.

    python3 tools/gen_critters.py          # write all the outputs
    python3 tools/gen_critters.py --check  # exit 1 if any is out of date

CI and `jarvis-desktop/tests/faces.mjs` run `--check`.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CRITTERS = ROOT / "jarvis-desktop" / "critters"
# Each animal: its face id (also its .sksl file name), and the name of its
# shader constant on the phone. The desktop's copy is keyed by the face id.
ANIMALS = [("redpanda", "RED_PANDA"), ("pygmyowl", "PYGMY_OWL"), ("seaotter", "SEA_OTTER"), ("monkey", "MONKEY"),
           ("robot", "ROBOT")]
# The pose code, in load order: critter-pose.js holds the shared helpers and
# the panda; each other animal's file registers itself with it.
POSE_JS = [ROOT / "jarvis-desktop" / "src" / f
           for f in ("critter-pose.js", "critter-owl.js", "critter-otter.js", "critter-monkey.js", "critter-robot.js")]
OUT_JS = ROOT / "jarvis-desktop" / "src" / "critters-gen.js"
OUT_KT = (ROOT / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis"
          / "client" / "face" / "CritterShaders.kt")
OUT_GOLDEN = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources"
              / "critter-pose-golden.json")
# The sleeping Zs (critter-pose.js `zs`): its numbers and its answers at
# fixed moments, which the phone's CritterPoseTest checks its copy against.
OUT_ZS = OUT_GOLDEN.with_name("critter-zs-golden.json")
# Whether an idle happening is playing (each pose file's `busy`), which the
# frame pacer on both apps reads: one line of 0s and 1s per animal, four
# samples a second over the first 320 seconds and around a day-long clock.
OUT_BUSY = OUT_GOLDEN.with_name("critter-busy-golden.json")

GLSL_HEAD = """#version 300 es
precision highp float;
#define float2 vec2
#define float3 vec3
#define float4 vec4
#define half3 vec3
#define half4 vec4
"""

GLSL_MAIN = """
uniform vec2 uRes;
uniform vec3 uBg;
// 1 while a picture is drawn BEHIND the animal (the sun, moon and weather,
// sky.js): the uncovered part is left see-through (premultiplied, as the
// phone's AGSL main always returns it). 0: laid over uBg, as before.
uniform float uSeeThrough;
out vec4 oCol;
void main() {
    // gl_FragCoord counts y UP the screen, which is what critter() wants.
    vec2 p = (gl_FragCoord.xy - 0.5 * uRes) / min(uRes.x, uRes.y) * 2.0;
    vec4 c = critter(p);
    oCol = uSeeThrough > 0.5 ? c : vec4(uBg * (1.0 - c.a) + c.rgb, 1.0);
}
"""

AGSL_MAIN = """
uniform float2 uCenter;
uniform float uR;
half4 main(float2 fragCoord) {
    // fragCoord counts y DOWN the screen; critter() wants it up.
    float2 p = (fragCoord - uCenter) / uR;
    p.y = -p.y;
    return half4(critter(p));
}
"""

# The moments the pose fixture samples: every state, settled and part way
# through a change, with and without sound and a pointer, at clock values
# that land on a blink, a wave, a breath - and on the animals' own
# happenings (a stretch, a ruffle, a face wash...), their gestures while
# speaking, and clocks days long, where a 32-bit float and a 64-bit double
# are most likely to part company.
STATES = ["idle", "listening", "thinking", "speaking", "approval", "standby", "error", "banked"]

# Moments found by scanning the pose code (critter-*.js) - if its timings are
# changed these stop landing on the moment named, and the test still passes
# but covers less, so find new ones the same way.
MOMENTS = {
    # A blink starting (each animal blinks on its own clock), and one of the
    # double blinks.
    "blink": {"redpanda": 4.0, "pygmyowl": 7.285, "seaotter": 5.45, "monkey": 3.465, "robot": 2.595},
    "double": {"redpanda": 54.9, "pygmyowl": 18.32, "seaotter": 24.26, "monkey": 6.71, "robot": 15.72},
    # The middle of each idle happening, in the order of its kinds.
    "happen": {
        "redpanda": [117.15, 81.4, 70.3, 150.1, 132.51],              # stretch, tail flick, scratch, hears L, R
        "pygmyowl": [85.13, 342.55, 306.45, 101.58, 133.49, 65.74],  # ruffle, wing L, R, tilt L, R, slow blink
        "seaotter": [101.83, 56.48, 23.65, 39.48, 163.71],           # face wash, roll L, R, kick, pebble rub
        "monkey": [5.26, 83.68, 101.51, 70.01, 17.96, 214.61],      # scratch, banana, kick, swing, look round, tail
        "robot": [20.94, 69.74, 244.65, 52.35, 162.97, 101.947],     # fin flick, curious look, dip, mitten, squint, zip
    },
    # Half a second into each speaking gesture: a nod, a paw (wing) lifted, a tilt.
    "gesture": {"redpanda": [44.78, 52.85, 12.84], "pygmyowl": [64.77, 12.88, 16.7],
                "seaotter": [18.64, 55.01, 65.06], "monkey": [3.09, 32.78, 127.06],
                # (the robot's five: a nod, the right mitten, the left, both, a tilt)
                "robot": [2.97, 6.81, 8.53, 104.89, 102.9]},
}
# Clock values exactly representable as 32-bit floats (the phone's clock is
# one): a day, and three. (Much past a week the phone's own clock only
# ticks in sixteenths of a second, and nothing drawn from it can match a
# 64-bit clock to a thousandth.)
LONG_T = (86400.25, 259200.375)


def golden_cases(species):
    cases = []
    for sp in species:
        for i, s in enumerate(STATES):
            for t in (0.0, 1.37, 4.43 + i * 0.11, 12.9):
                cases.append({"species": sp, "state": s, "prev": s, "since": 5.0, "t": t, "amp": 0.0,
                              "look": {}})
            cases.append({"species": sp, "state": s, "prev": STATES[(i + 3) % 8], "since": 0.21,
                          "t": 7.7, "amp": 0.6, "look": {"x": 0.4, "y": -0.3, "w": 0.8}})
            for t in LONG_T:
                cases.append({"species": sp, "state": s, "prev": s, "since": 5.0, "t": t, "amp": 0.3,
                              "look": {}})
        # The blink itself, caught closing, shut and opening, and a double.
        b = MOMENTS["blink"][sp]
        for t in (b + 0.03, b + 0.1, b + 0.2, MOMENTS["double"][sp] + 0.35):
            cases.append({"species": sp, "state": "idle", "prev": "idle", "since": 9.0, "t": t,
                          "amp": 0.0, "look": {}})
        # Each idle happening, and each speaking gesture.
        for t in MOMENTS["happen"][sp]:
            cases.append({"species": sp, "state": "idle", "prev": "idle", "since": 99.0, "t": t,
                          "amp": 0.0, "look": {}})
        for t in MOMENTS["gesture"][sp]:
            cases.append({"species": sp, "state": "speaking", "prev": "speaking", "since": 99.0, "t": t,
                          "amp": 0.4, "look": {}})
        # Settling into a new state, part by part: the eyes are there first,
        # the tail last.
        for since in (0.0, 0.05, 0.15, 0.3, 0.6, 1.1, 1.9):
            cases.append({"species": sp, "state": "approval", "prev": "idle", "since": since,
                          "t": 40.0 + since, "amp": 0.2, "look": {}, "hist": {"prevAmp": 0.0}})
        cases.append({"species": sp, "state": "standby", "prev": "speaking", "since": 0.4, "t": 61.3,
                      "amp": 0.0, "look": {}, "hist": {"prevAmp": 0.5, "prev2": "thinking", "gap": 0.3}})
        # Carrying on from what was on screen: leaving speaking mid-word (the
        # loudness at the change, not the new zero), and a second change 0.2 s
        # after the first (the previous state was itself still settling in).
        cases.append({"species": sp, "state": "idle", "prev": "speaking", "since": 0.1, "t": 3.3,
                      "amp": 0.0, "look": {}, "hist": {"prevAmp": 0.6}})
        cases.append({"species": sp, "state": "thinking", "prev": "listening", "since": 0.05, "t": 5.1,
                      "amp": 0.0, "look": {}, "hist": {"prev2": "idle", "gap": 0.2, "prevAmp": 0.28}})
        cases.append({"species": sp, "state": "approval", "prev": "error", "since": 0.3, "t": 8.4,
                      "amp": 0.28, "look": {"x": -0.5, "y": 0.2, "w": 0.4},
                      "hist": {"prev2": "standby", "gap": 0.4}})
        # A quick A -> B -> A: back to speaking 0.2 s after leaving it. The
        # speaking pose the idle one was settling from is drawn at the
        # loudness of the EARLIER change (prevAmp2), not the latest one.
        cases.append({"species": sp, "state": "speaking", "prev": "idle", "since": 0.1, "t": 6.2,
                      "amp": 0.3, "look": {},
                      "hist": {"prev2": "speaking", "gap": 0.2, "prevAmp": 0.05, "prevAmp2": 0.7}})
        # The mouth: the voice's own shape (open, wide, round), scaled by how
        # much the pose is speaking - fully while speaking, part way through
        # a change in or out, not at all in any other state; values outside
        # 0..1 are clamped.
        for mouth in ({"open": 0.6, "wide": 0.3, "round": 0.1}, {"open": 1.4, "wide": -0.2, "round": 0.9}):
            cases.append({"species": sp, "state": "speaking", "prev": "speaking", "since": 5.0, "t": 2.5,
                          "amp": 0.3, "look": {}, "mouth": mouth})
        mouth = {"open": 0.8, "wide": 0.5, "round": 0.2}
        cases.append({"species": sp, "state": "speaking", "prev": "thinking", "since": 0.2, "t": 3.1,
                      "amp": 0.4, "look": {}, "mouth": mouth})
        cases.append({"species": sp, "state": "idle", "prev": "speaking", "since": 0.3, "t": 3.7,
                      "amp": 0.0, "look": {}, "hist": {"prevAmp": 0.5}, "mouth": mouth})
        cases.append({"species": sp, "state": "listening", "prev": "listening", "since": 5.0, "t": 1.9,
                      "amp": 0.5, "look": {}, "mouth": mouth})
        # The options (calm, serious, still - each a weight the host eases),
        # in every state, fully on and part way; and at a happening and a
        # gesture, which they take away.
        for i, s in enumerate(STATES):
            for opts in ({"calm": 1}, {"serious": 1}, {"still": 1}, {"calm": 0.4, "serious": 0.6}):
                cases.append({"species": sp, "state": s, "prev": s, "since": 5.0, "t": 12.9 + i * 0.37, "amp": 0.3,
                              "look": {"x": 0.3, "y": 0.2, "w": 0.5}, "opts": opts})
        for opts in ({"calm": 1}, {"serious": 0.5}, {"still": 1}):
            cases.append({"species": sp, "state": "idle", "prev": "idle", "since": 99.0,
                          "t": MOMENTS["happen"][sp][0], "amp": 0.0, "look": {}, "opts": opts})
            cases.append({"species": sp, "state": "speaking", "prev": "speaking", "since": 99.0,
                          "t": MOMENTS["gesture"][sp][1], "amp": 0.4, "look": {}, "opts": opts})
        # Nodding off (slow) and waking (less slow), and rousing from a doze.
        for since in (0.3, 1.0, 2.0, 4.0):
            cases.append({"species": sp, "state": "standby", "prev": "idle", "since": since, "t": 50.0 + since,
                          "amp": 0.0, "look": {}, "hist": {"prevAmp": 0.0}})
        for since in (0.2, 0.6):
            cases.append({"species": sp, "state": "idle", "prev": "standby", "since": since, "t": 70.0 + since,
                          "amp": 0.0, "look": {}, "hist": {"prevAmp": 0.0}})
        cases.append({"species": sp, "state": "approval", "prev": "banked", "since": 0.1, "t": 80.1,
                      "amp": 0.28, "look": {}, "hist": {"prevAmp": 0.0}})
        # The wake-up (about 2 s) and the nodding off (about 3 s), each played
        # from end to end, with the host's list of past changes: an animal
        # asleep for 9 s waking into idle, and one awake for 20 s nodding off.
        asleep9 = [{"state": "standby", "gap": 9.0, "amp": 0.0}, {"state": "idle", "gap": 20.0, "amp": 0.0}]
        awake20 = [{"state": "idle", "gap": 20.0, "amp": 0.0}, {"state": "standby", "gap": 9.0, "amp": 0.0}]
        for x in (0.05, 0.3, 0.6, 0.9, 1.2, 1.5, 1.8, 2.1, 2.3):
            cases.append({"species": sp, "state": "idle", "prev": "standby", "since": x, "t": 120.0 + x,
                          "amp": 0.0, "look": {}, "hist": {"past": asleep9}})
        for x in (0.1, 0.5, 0.9, 1.3, 1.7, 2.1, 2.5, 2.9, 3.2):
            cases.append({"species": sp, "state": "standby", "prev": "idle", "since": x, "t": 140.0 + x,
                          "amp": 0.0, "look": {}, "hist": {"past": awake20}})
        # Waking straight into waiting on you (only the eyes open), into
        # speaking (the mouth untouched, the gestures waiting), and into
        # listening then thinking (the wake-up carries on across both).
        for x in (0.3, 0.9, 1.6):
            cases.append({"species": sp, "state": "approval", "prev": "standby", "since": x, "t": 160.0 + x,
                          "amp": 0.28, "look": {}, "hist": {"past": asleep9}})
            cases.append({"species": sp, "state": "speaking", "prev": "standby", "since": x, "t": 170.0 + x,
                          "amp": 0.4, "look": {}, "hist": {"past": asleep9},
                          "mouth": {"open": 0.7, "wide": 0.3, "round": 0.2}})
        cases.append({"species": sp, "state": "thinking", "prev": "listening", "since": 0.4, "t": 181.4,
                      "amp": 0.0, "look": {}, "hist": {"past": [{"state": "listening", "gap": 0.7, "amp": 0.3}] + asleep9}})
        # Calm, serious and still: only the eyes open, or close.
        for opts in ({"calm": 1}, {"serious": 1}, {"still": 1}, {"calm": 0.5}):
            for x in (0.5, 1.2):
                cases.append({"species": sp, "state": "idle", "prev": "standby", "since": x, "t": 190.0 + x,
                              "amp": 0.0, "look": {}, "hist": {"past": asleep9}, "opts": opts})
            cases.append({"species": sp, "state": "standby", "prev": "idle", "since": 1.6, "t": 195.6,
                          "amp": 0.0, "look": {}, "hist": {"past": awake20}, "opts": opts})
        # Quick flips: asleep a third of a second and awake again, and the
        # other way round (each carries on from how far the one before got);
        # and the older, shorter form of the history a host may pass.
        cases.append({"species": sp, "state": "idle", "prev": "standby", "since": 0.25, "t": 200.25, "amp": 0.0,
                      "look": {}, "hist": {"past": [{"state": "standby", "gap": 0.3, "amp": 0.0}] + awake20[:1]}})
        cases.append({"species": sp, "state": "standby", "prev": "idle", "since": 0.4, "t": 210.4, "amp": 0.0,
                      "look": {}, "hist": {"past": [{"state": "idle", "gap": 0.3, "amp": 0.0}] + asleep9[:1]}})
        cases.append({"species": sp, "state": "listening", "prev": "standby", "since": 0.7, "t": 220.7,
                      "amp": 0.3, "look": {}, "hist": {"prevAmp": 0.0, "gap": 6.0}})
        # Three changes inside a second: each still settling when the next came
        # (the host's list of past changes, newest first).
        for since in (0.05, 0.3):
            cases.append({"species": sp, "state": "listening", "prev": "thinking", "since": since, "t": 90.0 + since,
                          "amp": 0.3, "look": {}, "hist": {"past": [
                              {"state": "thinking", "gap": 0.3, "amp": 0.0},
                              {"state": "speaking", "gap": 0.4, "amp": 0.6},
                              {"state": "idle", "gap": 7.0, "amp": 0.0}]},
                          "opts": {"calm": 0.5}})
        # Where the sleeping Zs rise from, with the host's own camera turn and zoom.
        cases.append({"species": sp, "state": "standby", "prev": "standby", "since": 9.0, "t": 33.3, "amp": 0.0,
                      "look": {}, "view": {"yaw": 0.4, "pitch": -0.15, "zoom": 1.3}})
    # The new behaviours (critter-pose.js "New behaviours"): each input the
    # host may pass, in the states it acts in, fully on and part way, under
    # the options that switch it off or make it smaller.
    for sp in species:
        cases.extend(behaviour_cases(sp))
    if "robot" in species:
        cases.extend(robot_cases())
    # The owl's orb kept clear of its head while the pointer turns the head
    # toward it (the push in critter-owl.js's clearOfHead is working here),
    # and coming up its side into the thinking circle.
    if "pygmyowl" in species:
        for t in (263.45, 82.2):
            cases.append({"species": "pygmyowl", "state": "thinking", "prev": "thinking", "since": 99.0, "t": t,
                          "amp": 0.0, "look": {"x": 1, "y": 1, "w": 1}})
        for since in (0.1, 0.5, 1.5, 3.0):
            cases.append({"species": "pygmyowl", "state": "thinking", "prev": "idle", "since": since,
                          "t": 44.0 + since, "amp": 0.0, "look": {}, "hist": {"prevAmp": 0.0}})
    return cases


# Where each animal's two cute idle moments start (clock, seconds): found by
# scanning the pose code, like MOMENTS - if the timings change these stop
# landing on a moment, so find new ones the same way (cuteAt, since 1e6).
CUTE = {"redpanda": (102.082, 408.591), "pygmyowl": (173.461, 313.491),
        "seaotter": (101.685, 403.501), "monkey": (87.92, 426.323), "robot": (130.566, 452.031)}


def behaviour_cases(sp):
    """The new behaviours' moments for one animal (see golden_cases)."""
    cases = []
    base = {"species": sp, "amp": 0.3, "look": {}}

    def add(state, t, opts, since=20.0, prev=None, hist=None, amp=None):
        c = dict(base, state=state, prev=prev or state, since=since, t=t, opts=opts)
        if hist is not None:
            c["hist"] = hist
        if amp is not None:
            c["amp"] = amp
        cases.append(c)

    # Listening nods in the owner's pauses, all three kinds, and under calm
    # (smaller) and serious (none).
    for n, ago in enumerate((0.35, 0.4, 0.5, 0.9)):
        add("listening", 10.4 + n, {"heard": ago, "heardN": n})
    add("listening", 10.4, {"heard": 0.4, "heardN": 0, "calm": 1})
    add("listening", 10.4, {"heard": 0.4, "heardN": 0, "serious": 1})
    # Gestures at Jarvis's phrase ends (in place of the random ones), and the
    # host tracking phrases before the first one ends (no gesture).
    for n, t in enumerate((20.0, 31.3, 44.6, 57.1, 63.9)):
        add("speaking", t, {"phraseEnd": 0.3 + 0.2 * n, "phraseN": n + 1})
    add("speaking", 20.0, {"phraseN": 0})
    # A fact saved (a nod), a long answer ready (the orb swells), in idle and
    # while speaking; none while waiting on you or asleep.
    for st in ("idle", "speaking", "approval", "standby"):
        add(st, 30.0, {"ackNod": 0.4, "ackGlow": 0.9})
    # A focus session, fully and part way, and the stretch as it ends.
    add("idle", 30.0, {"focus": 1})
    add("idle", 77.3, {"focus": 0.5})
    add("idle", 30.0, {"focusEnd": 1.2})
    # Petting, in idle and listening, and switched off by still.
    add("idle", 30.0, {"pet": 1, "petX": 0.5, "petDir": 1})
    add("listening", 30.0, {"pet": 0.6, "petX": -0.8, "petDir": -0.5})
    add("idle", 30.0, {"pet": 1, "petX": 0.5, "still": 1})
    # Each owner's switch (jarvis_animal.SWITCHES) off, and part way.
    add("listening", 10.4, {"heard": 0.4, "heardN": 0, "nods": 0})
    add("idle", 30.0, {"ackNod": 0.4, "ackGlow": 0.9, "acks": 0.5})
    add("idle", 30.0, {"focus": 1, "focus_buddy": 0})
    add("idle", 30.0, {"focusEnd": 1.2, "focus_buddy": 0})
    add("idle", 30.0, {"pet": 1, "petX": 0.5, "petting": 0})
    # Goodbye and hello, part way; none of it while waiting on you (the
    # host's cross-fade, as in a serious moment); nothing but the move out of
    # view asleep; only a cross-fade under calm.
    for g in (0.3, 0.7):
        add("idle", 30.0, {"goodbye": g})
    for h in (0.2, 0.6):
        add("idle", 30.0, {"hello": h})
    add("approval", 30.0, {"goodbye": 0.3})
    add("standby", 30.0, {"goodbye": 0.5}, since=9.0)
    add("idle", 30.0, {"goodbye": 0.5, "calm": 1})
    # Variety: listening's and thinking's variants now and then, and the
    # small reaction as waiting on you or something wrong arrives - the
    # second arrival in a row never repeating the first's.
    for i in range(8):
        add("listening", 2000.3 + 7.7 * i, {"variety": 1})
        add("thinking", 2000.3 + 7.7 * i, {"variety": 1})
    for since in (0.3, 0.6):
        add("approval", 40.0 + since, {"variety": 1}, since=since, prev="idle", hist={"prevAmp": 0.0}, amp=0.28)
        add("error", 50.0 + since, {"variety": 1}, since=since, prev="idle", hist={"prevAmp": 0.0}, amp=0.0)
        add("approval", 60.0 + since, {"variety": 1}, since=since, prev="idle", amp=0.28,
            hist={"past": [{"state": "idle", "gap": 3.0, "amp": 0.0}, {"state": "approval", "gap": 2.0, "amp": 0.28},
                           {"state": "idle", "gap": 9.0, "amp": 0.0}]})
    # The two cute idle moments, part way through each (idle long enough),
    # and switched off by the owner's switch, smaller under calm, and none
    # when it has not been idle long.
    for start in CUTE[sp]:
        for x in (1.5, 2.6, 3.8):
            add("idle", start + x, {}, since=1e6, amp=0.0)
    add("idle", CUTE[sp][0] + 2.6, {"cute_moments": 0}, since=1e6, amp=0.0)
    add("idle", CUTE[sp][1] + 2.6, {"cute_moments": 0.5}, since=1e6, amp=0.0)
    add("idle", CUTE[sp][0] + 2.6, {"calm": 1}, since=1e6, amp=0.0)
    add("idle", CUTE[sp][0] + 2.6, {}, since=100.0, amp=0.0)
    # Added 2026-09-29 (the skeptical review): fewer idle happenings while
    # Jarvis is not being used - each of the animal's happenings with
    # `attention` 0 (thinned away or one of the quarter that stay, by its
    # slot) and part way - and its gestures landing ON a phrase end handed
    # over ahead of time (`phraseDue`: seconds until it, negative once past).
    for t in MOMENTS["happen"][sp]:
        add("idle", t, {"attention": 0}, since=99.0, amp=0.0)
        add("idle", t, {"attention": 0.5}, since=99.0, amp=0.0)
    for n, (t, due) in enumerate(((20.0, 0.35), (31.3, 0.0), (44.6, -0.2), (57.1, -0.5), (63.9, 0.5), (20.0, -1.4))):
        add("speaking", t, {"phraseDue": due, "phraseN": n + 1})
    add("speaking", 31.3, {"phraseDue": 0.0, "phraseN": 2, "calm": 1})
    add("speaking", 31.3, {"phraseDue": 0.0, "phraseN": 2, "serious": 1})
    # Added 2026-09-28 (the audit's fixes): a focus session under calm (its
    # pose smaller), and a hello and a goodbye at an error (none of it).
    add("idle", 30.0, {"focus": 1, "calm": 1})
    add("idle", 77.3, {"focus": 1, "calm": 0.5})
    add("error", 30.0, {"hello": 0.6})
    add("error", 30.0, {"goodbye": 0.7})
    return cases


def robot_cases():
    """The robot's own moments (critter-robot.js): its zip part way (it
    needs 10 s of rest, and none under calm), the gleam across its visor as
    a polish ends, its hello and goodbye at their ends (out of view), the
    eyes' pulse with a voice and none without, woken straight into waiting on
    you (no reaction, only the eyes), and its phrase-end gestures mapped onto
    its five kinds."""
    cases = []
    base = {"species": "robot", "amp": 0.3, "look": {}}

    def add(state, t, opts, since=999.0, prev=None, hist=None, mouth=None):
        c = dict(base, state=state, prev=prev or state, since=since, t=t, opts=opts)
        if hist is not None:
            c["hist"] = hist
        if mouth is not None:
            c["mouth"] = mouth
        cases.append(c)

    zip0 = MOMENTS["happen"]["robot"][5] - 1.2
    for x in (0.2, 0.7, 1.2, 1.9, 2.5):
        add("idle", zip0 + x, {})
    add("idle", zip0 + 1.2, {}, since=5.0)
    add("idle", zip0 + 1.2, {"calm": 1})
    add("idle", zip0 + 1.2, {"calm": 0.4})
    add("idle", zip0 + 1.2, {"attention": 0})
    add("idle", zip0 + 1.2, {"attention": 0.5})
    for x in (2.5, 2.8, 3.1):
        add("idle", CUTE["robot"][1] + x, {}, since=1e6)
    for o in ({"goodbye": 1}, {"hello": 0}, {"goodbye": 0.9, "still": 1}, {"hello": 0.1, "serious": 1}):
        add("idle", 30.0, o)
    voice = {"open": 0.9, "wide": 0.4, "round": 0.1}
    add("speaking", 12.0, {}, mouth=voice)
    add("speaking", 12.0, {})
    add("idle", 12.0, {}, mouth=voice)
    for x in (0.3, 0.9):
        add("approval", 160.0 + x, {"variety": 1}, since=x, prev="standby",
            hist={"past": [{"state": "standby", "gap": 9.0, "amp": 0.0}, {"state": "idle", "gap": 20.0, "amp": 0.0}]})
    for n in range(6):
        add("speaking", 20.0 + 3 * n, {"phraseEnd": 0.5, "phraseN": n})
    # Added 2026-09-28: its hello's fin flick, awake, asleep and dozing (none
    # but awake), and waiting on you (none of the hello at all).
    for st in ("idle", "standby", "banked", "approval"):
        add(st, 30.0, {"hello": 0.6})
    return cases


NODE = r"""
for (const f of process.argv.slice(1)) require(f);
const C = globalThis.CritterPose;
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = cases.map(c => {
  const api = C.species[c.species];
  const P = api.pose(c.state, c.prev, c.since, c.t, c.amp, c.look, c.hist, c.opts);
  return { ...c, uniforms: api.uniforms(P, c.mouth), overlay: api.overlay(P, c.view) };
});
// Six decimals: the Kotlin copies run in 32-bit floats and are checked to
// within a thousandth, so more digits would only be noise in the diff.
process.stdout.write(JSON.stringify(out, (k, v) =>
  typeof v === 'number' ? Math.round(v * 1e6) / 1e6 : v, 1) + '\n');
"""


def zs_cases():
    """Moments for the Zs fixture: a z appearing, rising, fading; two at once;
    calm part way and fully on; half asleep; the head on either side (the
    otter's point is to its left, so its Zs drift left); a head high enough
    that the rise is cut short (the panda's); and clocks past PERIOD and a
    day long (the phone restarts its clock at multiples of PERIOD)."""
    cases = []
    heads = ({"asleep": 1, "x": 0.52, "y": 0.80}, {"asleep": 1, "x": 0.365, "y": 0.55},
             {"asleep": 1, "x": -0.64, "y": 0.36}, {"asleep": 0.4, "x": 0.3, "y": 0.5})
    for ov in heads:
        for t in (0.0, 0.45, 1.37, 2.9, 4.43, 7.7, 12.9, 33.3, 100.05, 4095.9, 4096.3, 86400.25):
            for calm in (0.0, 0.5, 1.0):
                cases.append({"t": t, "ov": ov, "calm": calm})
    return cases


ZS_NODE = r"""
for (const f of process.argv.slice(1)) require(f);
const C = globalThis.CritterPose;
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = { spec: C.ZS, cases: cases.map(c => ({ ...c, zs: C.zs(c.t, c.ov, c.calm) })) };
process.stdout.write(JSON.stringify(out, (k, v) =>
  typeof v === 'number' ? Math.round(v * 1e6) / 1e6 : v, 1) + '\n');
"""


# The clocks the busy fixture samples. The 0.013 keeps every sample off the
# exact edge of a happening, where a 32-bit and a 64-bit clock may disagree.
BUSY_TIMES = [round(k * 0.25 + 0.013, 3) for k in range(1280)] + \
             [round(86400 + k * 0.25 + 0.013, 3) for k in range(160)]

# Whether a moment the host hands in is playing (critter-pose.js
# momentsBusy, the frame pacer's): a stroke, a fact's nod, the long answer's
# glow and the focus stretch, inside and just outside their lengths, in the
# states they play in and those they do not, and under still and serious.
MOMENT_CASES = [
    {"state": st, "opts": o}
    for st in ("idle", "speaking", "approval", "standby")
    for o in ({}, {"pet": 0.4}, {"pet": 1, "petting": 0}, {"ackNod": 0.5}, {"ackNod": 1.3}, {"ackNod": 0.5, "acks": 0},
              {"ackGlow": 1.7}, {"ackGlow": 1.9}, {"focusEnd": 3.1}, {"focusEnd": 3.3}, {"focusEnd": 1, "focus_buddy": 0},
              {"pet": 1, "still": 1}, {"ackNod": 0.5, "serious": 1}, {"ackNod": 0.5, "calm": 1})
]

# The slow wander (critter-pose.js noise(), breathWave()) and the host's side
# of gestures that land on phrase ends (aheadStep): their answers at fixed
# moments - inside one period, past it, and days on - which the phone's
# CritterPoseTest checks its copies against (critter-drift-golden.json).
OUT_DRIFT = OUT_GOLDEN.with_name("critter-drift-golden.json")
DRIFT_TIMES = [0.0, 0.7, 1.9, 3.3, 5.1, 12.34, 47.6, 133.05, 1023.5, 1024.25, 4095.5, 4096.25, 4100.0, 8191.75, 86400.25, 259200.375]
AHEAD_STEPS = [  # (dt, next): a clip's ends coming up, one too late, one too soon after the last, a gap of nothing
    (0.0, None), (0.016, 1.4), (0.016, 0.95), (0.016, 0.88), (0.016, 0.87), (0.016, 0.5), (0.5, 3.0), (0.5, 2.9),
    (0.016, 0.7), (0.016, 0.6), (0.3, 0.8), (1.2, 0.85), (0.016, 0.66), (0.016, None), (2.5, 0.9), (0.016, 0.64),
]
DRIFT_NODE = r"""
for (const f of process.argv.slice(1)) require(f);
const C = globalThis.CritterPose, U = C.util;
const inp = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = { noise: [], breath: [], ahead: [], ahead_limits: C.AHEAD, breath_var: null };
for (const seed of [8, 17, 26, 34, 42]) for (const scale of [4, 8, 16, 32]) for (const t of inp.times) {
  out.noise.push({ t, seed, scale, v: U.noise(t, seed, scale) });
}
for (const k of [171, 205, 256, 300]) for (const t of inp.times) out.breath.push({ t, k, seed: 10, v: U.breathWave(t, k, 10) });
let rec = null;
for (const [dt, next] of inp.ahead) { rec = C.aheadStep(rec, dt, next); out.ahead.push({ dt, next, n: rec.n, due: rec.due }); }
process.stdout.write(JSON.stringify(out, (k, v) => typeof v === 'number' ? Math.round(v * 1e6) / 1e6 : v, 1) + '\n');
"""

BUSY_NODE = r"""
for (const f of process.argv.slice(1)) require(f);
const C = globalThis.CritterPose;
const inp = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const times = inp.times;
const out = { happening_s: C.HAPPENING_S, times, busy: {}, gesture_s: C.util.GESTURE_S, gesturing: {},
              moments: inp.moments.map(c => ({ ...c, busy: C.momentsBusy(c.state, c.opts) })) };
out.busy_att0 = {};
for (const sp of Object.keys(C.species)) {
  out.busy[sp] = times.map(t => C.species[sp].busy('idle', t) ? '1' : '0').join('');
  // ...and with the owner not using Jarvis (`attention` 0): about one in four.
  out.busy_att0[sp] = times.map(t => C.species[sp].busy('idle', t, undefined, { attention: 0 }) ? '1' : '0').join('');
  // Whether one of its own talking gestures plays (the host's check before
  // it hands the pose Jarvis's phrase ends part way into an answer).
  out.gesturing[sp] = times.map(t => C.species[sp].gesturing(t) ? '1' : '0').join('');
  // Never outside idle.
  for (const st of ['listening', 'thinking', 'speaking', 'approval', 'standby', 'error', 'banked'])
    if (times.some(t => C.species[sp].busy(st, t))) throw new Error(sp + ' is busy in ' + st);
}
process.stdout.write(JSON.stringify(out, null, 1) + '\n');
"""


def animals():
    """The animals that exist so far, each with its full shader source."""
    head = (CRITTERS / "common_head.sksl").read_text(encoding="utf-8")
    tail = (CRITTERS / "common_tail.sksl").read_text(encoding="utf-8")
    out = []
    for face_id, const in ANIMALS:
        src = CRITTERS / f"{face_id}.sksl"
        if src.exists():
            out.append((face_id, const, head + "\n" + src.read_text(encoding="utf-8") + "\n" + tail))
    return out


def build():
    js_rows, kt_rows = [], []
    for face_id, const, body in animals():
        glsl = GLSL_HEAD + body + GLSL_MAIN
        agsl = body + AGSL_MAIN
        if '"""' in agsl or "$" in agsl:
            sys.exit(f"{face_id}: the shader must not contain a triple quote or a dollar sign: "
                     "both break a Kotlin raw string")
        js_rows.append(f"  {face_id}: {json.dumps(glsl)},\n")
        kt_rows.append(f'    const val {const} = """{agsl}"""\n')

    js = (
        "// GENERATED by tools/gen_critters.py from jarvis-desktop/critters/*.sksl.\n"
        "// Do not edit: edit the .sksl and re-run `python3 tools/gen_critters.py`.\n"
        "window.JARVIS_CRITTERS = Object.freeze({\n"
        + "".join(js_rows) +
        "});\n"
    )
    kt = (
        "// GENERATED by tools/gen_critters.py from jarvis-desktop/critters/*.sksl.\n"
        "// Do not edit: edit the .sksl and re-run `python3 tools/gen_critters.py`.\n"
        "package com.jarvis.client.face\n\n"
        "/** The animal faces' AGSL, one shared source with the desktop's GLSL. */\n"
        "internal object CritterShaders {\n"
        + "\n".join(kt_rows) +
        "}\n"
    )
    pose_files = [str(f) for f in POSE_JS if f.exists()]
    res = subprocess.run(["node", "-e", NODE, *pose_files],
                         input=json.dumps(golden_cases([a for a, _, _ in animals()])),
                         capture_output=True, text=True, check=True)
    zs = subprocess.run(["node", "-e", ZS_NODE, *pose_files], input=json.dumps(zs_cases()),
                        capture_output=True, text=True, check=True)
    busy = subprocess.run(["node", "-e", BUSY_NODE, *pose_files], input=json.dumps({"times": BUSY_TIMES, "moments": MOMENT_CASES}),
                          capture_output=True, text=True, check=True)
    drift = subprocess.run(["node", "-e", DRIFT_NODE, *pose_files],
                           input=json.dumps({"times": DRIFT_TIMES, "ahead": AHEAD_STEPS}),
                           capture_output=True, text=True, check=True)
    return {OUT_JS: js, OUT_KT: kt, OUT_GOLDEN: res.stdout, OUT_ZS: zs.stdout, OUT_BUSY: busy.stdout, OUT_DRIFT: drift.stdout}


def main():
    check = "--check" in sys.argv
    stale = []
    for path, text in build().items():
        old = path.read_text(encoding="utf-8") if path.exists() else None
        if old == text:
            continue
        if check:
            stale.append(str(path.relative_to(ROOT)))
        else:
            path.write_text(text, encoding="utf-8")
            print("wrote", path.relative_to(ROOT))
    if stale:
        print("out of date - run `python3 tools/gen_critters.py`:\n  " + "\n  ".join(stale))
        sys.exit(1)


if __name__ == "__main__":
    main()
