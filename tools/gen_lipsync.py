#!/usr/bin/env python3
"""Write the lip-sync golden fixture both apps are checked against.

The mouth movement for the faces is worked out from each spoken reply by
`jarvis-desktop/src/lipsync.js` on the desktop and by a line-for-line Kotlin
copy on the phone (`jarvis-client/.../audio/LipSync.kt`). This runs the
JavaScript under node over the test clips in
`jarvis-client/app/src/test/resources/lipsync/` (Jarvis's own Kokoro voice:
the default voice and the animal voices - docs/LIPSYNC.md says how they were
made) and saves every frame of every track, plus some sample() reads, in
`lipsync-golden.json`. The phone's `LipSyncTest` fails if the Kotlin copy
disagrees by more than 1e-3, so the two cannot drift apart quietly.

    python3 tools/gen_lipsync.py          # rewrite the fixture
    python3 tools/gen_lipsync.py --check  # exit 1 if it is out of date

CI runs `--check`. Needs node on PATH.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIPSYNC_JS = ROOT / "jarvis-desktop" / "src" / "lipsync.js"
RESOURCES = ROOT / "jarvis-client" / "app" / "src" / "test" / "resources"
CLIPS = RESOURCES / "lipsync"
OUT = RESOURCES / "lipsync-golden.json"

# Runs in node: argv[1] = lipsync.js, stdin = list of WAV paths (relative
# names are what the fixture records). Values rounded to 6 decimals, which
# is far inside the test's 1e-3 and keeps the file small and stable.
NODE = r"""
const L = require(process.argv[1]);
const fs = require("fs");
const clips = JSON.parse(fs.readFileSync(0, "utf8"));
const r = (x) => Math.round(x * 1e6) / 1e6;
const out = { fps: L.FPS, lead_s: L.LEAD_S, clips: [] };
for (const c of clips) {
  const w = L.fromWav(fs.readFileSync(c.path));
  const t = L.analyse(w.samples, w.sampleRate);
  const reads = [];
  // Before the start, just inside the first frame, in between frames, just
  // inside the last frame, after the end - sample() adds LEAD_S itself.
  // Never exactly on an edge: the phone passes time as a Float, and 1e-4 s
  // keeps both apps on the same side of it.
  const last = (t.n - 1) / t.fps - L.LEAD_S;
  for (const s of [-1, -L.LEAD_S - 0.001, -L.LEAD_S + 0.0001, 0, 0.123, 0.5051, last / 2, last - 0.0001,
    last + 0.001, last + 5]) {
    const o = L.sample(t, s);
    reads.push({ t: s, inside: !(s < -L.LEAD_S || s > last), out: [r(o.level), r(o.open), r(o.wide), r(o.round)] });
  }
  out.clips.push({ file: c.name, sampleRate: w.sampleRate, samples: w.samples.length, n: t.n,
    level: Array.from(t.level, r), open: Array.from(t.open, r), wide: Array.from(t.wide, r),
    round: Array.from(t.round, r), reads });
}
process.stdout.write(JSON.stringify(out) + "\n");
"""


def build() -> str:
    clips = [{"name": p.name, "path": str(p)} for p in sorted(CLIPS.glob("*.wav"))]
    if not clips:
        raise SystemExit(f"no test clips in {CLIPS}")
    res = subprocess.run(["node", "-e", NODE, str(LIPSYNC_JS)], input=json.dumps(clips),
                         capture_output=True, text=True, check=True)
    return res.stdout


def main():
    check = "--check" in sys.argv
    text = build()
    old = OUT.read_text(encoding="utf-8") if OUT.exists() else None
    if old == text:
        print(f"{OUT.relative_to(ROOT)} is up to date")
        return 0
    if check:
        print(f"{OUT.relative_to(ROOT)} is out of date - run python3 tools/gen_lipsync.py "
              "(lipsync.js changed; change LipSync.kt the same way)", file=sys.stderr)
        return 1
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
