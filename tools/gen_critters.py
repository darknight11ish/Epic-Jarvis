#!/usr/bin/env python3
"""Generate both apps' copies of the animal faces from one source.

Each animal (red panda, pygmy owl, sea otter) is drawn by one shader, built
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
disagrees, so the two cannot drift apart quietly.

    python3 tools/gen_critters.py          # write all three outputs
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
ANIMALS = [("redpanda", "RED_PANDA"), ("pygmyowl", "PYGMY_OWL"), ("seaotter", "SEA_OTTER")]
# The pose code, in load order: critter-pose.js holds the shared helpers and
# the panda; each other animal's file registers itself with it.
POSE_JS = [ROOT / "jarvis-desktop" / "src" / f
           for f in ("critter-pose.js", "critter-owl.js", "critter-otter.js")]
OUT_JS = ROOT / "jarvis-desktop" / "src" / "critters-gen.js"
OUT_KT = (ROOT / "jarvis-client" / "app" / "src" / "main" / "java" / "com" / "jarvis"
          / "client" / "face" / "CritterShaders.kt")
OUT_GOLDEN = (ROOT / "jarvis-client" / "app" / "src" / "test" / "resources"
              / "critter-pose-golden.json")

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
out vec4 oCol;
void main() {
    // gl_FragCoord counts y UP the screen, which is what critter() wants.
    vec2 p = (gl_FragCoord.xy - 0.5 * uRes) / min(uRes.x, uRes.y) * 2.0;
    vec4 c = critter(p);
    oCol = vec4(uBg * (1.0 - c.a) + c.rgb, 1.0);
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

# The moments the pose fixture samples: every state, blended and settled,
# with and without sound and a pointer, at clock values that land on a
# blink, a wave, a breath.
STATES = ["idle", "listening", "thinking", "speaking", "approval", "standby", "error", "banked"]


def golden_cases(species):
    cases = []
    for sp in species:
        for i, s in enumerate(STATES):
            for t in (0.0, 1.37, 4.43 + i * 0.11, 12.9):
                cases.append({"species": sp, "state": s, "prev": s, "since": 5.0, "t": t, "amp": 0.0,
                              "look": {}})
            cases.append({"species": sp, "state": s, "prev": STATES[(i + 3) % 8], "since": 0.21,
                          "t": 7.7, "amp": 0.6, "look": {"x": 0.4, "y": -0.3, "w": 0.8}})
        # The blink itself, caught closing, shut and opening. The first blink
        # lands at 0.975 s (critter-pose.js's hash of period 0) and lasts
        # 0.15 s; the second at 4.568 s. Every animal shares the blink.
        for t in (1.0, 1.05, 1.1, 4.6):
            cases.append({"species": sp, "state": "idle", "prev": "idle", "since": 9.0, "t": t,
                          "amp": 0.0, "look": {}})
        # Carrying on from what was on screen: leaving speaking mid-word (the
        # loudness at the change, not the new zero), and a second change 0.2 s
        # after the first (the previous state was itself still melting in).
        cases.append({"species": sp, "state": "idle", "prev": "speaking", "since": 0.1, "t": 3.3,
                      "amp": 0.0, "look": {}, "hist": {"prevAmp": 0.6}})
        cases.append({"species": sp, "state": "thinking", "prev": "listening", "since": 0.05, "t": 5.1,
                      "amp": 0.0, "look": {}, "hist": {"prev2": "idle", "gap": 0.2, "prevAmp": 0.28}})
        cases.append({"species": sp, "state": "approval", "prev": "error", "since": 0.3, "t": 8.4,
                      "amp": 0.28, "look": {"x": -0.5, "y": 0.2, "w": 0.4},
                      "hist": {"prev2": "standby", "gap": 0.4}})
        # A quick A -> B -> A: back to speaking 0.2 s after leaving it. The
        # speaking pose the idle one was melting from is drawn at the
        # loudness of the EARLIER change (prevAmp2), not the latest one.
        cases.append({"species": sp, "state": "speaking", "prev": "idle", "since": 0.1, "t": 6.2,
                      "amp": 0.3, "look": {},
                      "hist": {"prev2": "speaking", "gap": 0.2, "prevAmp": 0.05, "prevAmp2": 0.7}})
        # The mouth: the voice's own shape (open, wide, round), scaled by how
        # much the pose is speaking - fully while speaking, part way through
        # a melt in or out, not at all in any other state; values outside
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
    return cases


NODE = r"""
for (const f of process.argv.slice(1)) require(f);
const C = globalThis.CritterPose;
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = cases.map(c => {
  const api = C.species[c.species];
  return { ...c, uniforms: api.uniforms(api.pose(c.state, c.prev, c.since, c.t, c.amp, c.look, c.hist), c.mouth) };
});
// Six decimals: the Kotlin copies run in 32-bit floats and are checked to
// within a thousandth, so more digits would only be noise in the diff.
process.stdout.write(JSON.stringify(out, (k, v) =>
  typeof v === 'number' ? Math.round(v * 1e6) / 1e6 : v, 1) + '\n');
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
    return {OUT_JS: js, OUT_KT: kt, OUT_GOLDEN: res.stdout}


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
