#!/usr/bin/env python3
"""Write the lip-sync golden fixture both apps are checked against.

The mouth movement for the faces is worked out from each spoken reply by
`jarvis-desktop/src/lipsync.js` on the desktop and by a line-for-line Kotlin
copy on the phone (`jarvis-client/.../audio/LipSync.kt`). This runs the
JavaScript under node over the test clips in
`jarvis-client/app/src/test/resources/lipsync/` (Jarvis's own Kokoro voice:
the default voice and the animal voices - docs/LIPSYNC.md says how they were
made; a few resampled to 8, 16, 22.05 and 44.1 kHz, and one cut off
mid-word, so both copies are also held to the same numbers at every window
size, at a frame hop that is not a whole number of samples, and at the end
fade) and saves every frame of every track, plus some sample() reads, in
`lipsync-golden.json`. The phone's `LipSyncTest` fails if the Kotlin copy
disagrees by more than 1e-3, so the two cannot drift apart quietly.

    python3 tools/gen_lipsync.py          # rewrite the fixture
    python3 tools/gen_lipsync.py --check  # exit 1 if it is out of date

CI runs `--check`. Needs node on PATH.

Mouth shapes inside the WAV. The PC may add a "jmth" RIFF chunk after
`data` (docs/LIPSYNC.md, "Mouths from Kokoro's own timing"): ASCII
"v1;src=kokoro;" + a lipsync.js pack() string. Both apps then take open,
wide and round from it and the loudness from their own analysis
(`JarvisLipSync.merge` / `LipSync.merge`). This tool also:

- builds the committed fixture `lipsync-mouth/kokoro-panda-lips-jmth.wav`:
  the panda test clip, byte for byte, with one "jmth" chunk appended (a
  made-up mouth track 2 frames shorter than the clip, so the merge's
  length slack is exercised; its payload has an odd length, so the RIFF pad
  byte is too) and the RIFF size fixed. It is made here, from the clip, by
  `mouth_fixture()` - never by hand - and `--check` fails if it differs;
- records, for a list of good and broken variants of that chunk (another
  version, bad base64, not whole frames, before `data`, a file cut short,
  ...), whether the desktop found a mouth and merged it - and a SHA-256 of
  each variant's bytes, so the phone's test proves it built the same file
  before comparing its answer.
"""
import base64
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIPSYNC_JS = ROOT / "jarvis-desktop" / "src" / "lipsync.js"
RESOURCES = ROOT / "jarvis-client" / "app" / "src" / "test" / "resources"
CLIPS = RESOURCES / "lipsync"
OUT = RESOURCES / "lipsync-golden.json"
MOUTH_SOURCE = CLIPS / "kokoro-panda-lips.wav"
MOUTH_FIXTURE = RESOURCES / "lipsync-mouth" / "kokoro-panda-lips-jmth.wav"

# Runs in node: argv[1] = lipsync.js, stdin = {clips: WAV paths (relative
# names are what the fixture records), mouth: the jmth fixture and variants}. Values rounded to 6 decimals, which
# is far inside the test's 1e-3 and keeps the file small and stable.
NODE = r"""
const L = require(process.argv[1]);
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const clips = input.clips;
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
  // 0.02 and 0.0301: inside the mouth's fade-in (ONSET_S).
  for (const s of [-1, -L.LEAD_S - 0.001, -L.LEAD_S + 0.0001, 0, 0.02, 0.0301, 0.123, 0.5051, last / 2, last - 0.0001,
    last + 0.001, last + 5]) {
    const o = L.sample(t, s);
    reads.push({ t: s, inside: !(s < -L.LEAD_S || s > last), out: [r(o.level), r(o.open), r(o.wide), r(o.round)] });
  }
  out.clips.push({ file: c.name, sampleRate: w.sampleRate, samples: w.samples.length, n: t.n,
    level: Array.from(t.level, r), open: Array.from(t.open, r), wide: Array.from(t.wide, r),
    round: Array.from(t.round, r), reads });
}
// Mouth shapes inside the WAV: the fixture's merged track and reads, then
// what the desktop made of each variant (a mouth? merged? the same sound?).
const m = input.mouth;
const src = L.fromWav(Buffer.from(m.source, "base64"));
const srcTrack = L.analyse(src.samples, src.sampleRate);
const same = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);
const fx = L.fromWav(fs.readFileSync(m.fixture));
const merged = L.merge(L.analyse(fx.samples, fx.sampleRate), fx.mouth);
const reads = [];
for (const s of [0, 0.02, 0.123, 0.5051, (merged.n - 3) / merged.fps - L.LEAD_S + 0.0001]) {
  const o = L.sample(merged, s);
  reads.push({ t: s, out: [r(o.level), r(o.open), r(o.wide), r(o.round)] });
}
out.mouth = { file: m.fixtureName, source: m.sourceName, n: merged.n,
  mouthN: fx.mouth ? fx.mouth.n : 0, sameSound: same(fx.samples, src.samples),
  level: Array.from(merged.level, r), open: Array.from(merged.open, r), wide: Array.from(merged.wide, r),
  round: Array.from(merged.round, r), reads, cases: [] };
for (const c of m.cases) {
  const w = L.fromWav(Buffer.from(c.bytes, "base64"));
  const a = L.analyse(w.samples, w.sampleRate);
  const t = L.merge(a, w.mouth);
  out.mouth.cases.push({ ...c.spec, sha256: c.sha256, mouth: !!w.mouth, merged: t !== a,
    sameSound: same(w.samples, src.samples) });
}
process.stdout.write(JSON.stringify(out) + "\n");
"""


# ---- The "jmth" chunk: the fixture and its variants ------------------------
# LipSyncTest.kt's `variant()` builds the same bytes from the same spec; the
# SHA-256 in the fixture proves it did. Change both together.

def _le32(v: int) -> bytes:
    return struct.pack("<I", v & 0xFFFFFFFF)


def _packed(frames: int, extra_bytes: int = 0, fps: int = 100) -> str:
    """A pack() string of a made-up mouth track: level 0 (the apps take the
    level from their own analysis), open/wide/round in a fixed pattern."""
    raw = bytearray()
    for i in range(frames):
        raw += bytes((0, (i * 37) % 256, (i * 11 + 5) % 256, (250 - 3 * i) % 256))
    raw += bytes(extra_bytes)
    return f"{fps}:" + base64.b64encode(bytes(raw)).decode("ascii")


def _clip_frames(wav: bytes) -> int:
    """Mouth-track frames of a clip: 100 a second, rounded up (lipsync.js)."""
    rate = struct.unpack_from("<I", wav, 24)[0]
    samples = struct.unpack_from("<I", wav, 40)[0] // 2
    return (samples * 100 + rate - 1) // rate


def variant(src: bytes, spec: dict) -> bytes:
    """The source clip with one "jmth" chunk, placed and sized as `spec` says:
    payload (latin-1 text), where ("after" `data` | "before" it), sizeDelta
    (declared size minus the payload's), pad (a pad byte after an odd
    declared size), list ("padded" | "unpadded": a 3-byte LIST chunk between
    `data` and "jmth", with or without its pad byte), cut (bytes cut off the
    end, after the RIFF size is fixed)."""
    payload = spec["payload"].encode("latin-1")
    declared = len(payload) + spec.get("sizeDelta", 0)
    chunk = b"jmth" + _le32(declared) + payload
    if spec.get("pad", True) and declared % 2 == 1:
        chunk += b"\0"
    lst = spec.get("list")
    extra = b""
    if lst:
        extra = b"LIST" + _le32(3) + b"abc" + (b"\0" if lst == "padded" else b"")
    if spec.get("where", "after") == "after":
        out = bytearray(src + extra + chunk)
    else:
        at = src.index(b"data", 12)
        out = bytearray(src[:at] + chunk + src[at:])
    out[4:8] = _le32(len(out) - 8)
    cut = spec.get("cut", 0)
    return bytes(out[:len(out) - cut] if cut else out)


def mouth_specs(src: bytes) -> tuple[dict, list[dict]]:
    n = _clip_frames(src)
    good = _packed(n - 2)
    fixture = {"payload": "v1;src=fixture;" + good}   # 15 + 4k: odd, so padded
    k = "v1;src=kokoro;"
    specs = [
        {"name": "the backend's own shape", "want": "merged", "payload": k + good},
        {"name": "no src field", "want": "merged", "payload": "v1;" + good},
        {"name": "an extra field", "want": "merged", "payload": k + "x=1;" + good},
        {"name": "NUL padding counted in the size", "want": "merged", "payload": k + good + "\0"},
        {"name": "the same length as the clip", "want": "merged", "payload": k + _packed(n)},
        {"name": "3 frames longer", "want": "merged", "payload": k + _packed(n + 3)},
        {"name": "a padded odd LIST before it", "want": "merged", "payload": k + good, "list": "padded"},
        {"name": "4 frames longer: not merged", "want": "kept apart", "payload": k + _packed(n + 4)},
        {"name": "4 frames shorter: not merged", "want": "kept apart", "payload": k + _packed(n - 4)},
        {"name": "version 2", "want": "ignored", "payload": "v2;src=kokoro;" + good},
        {"name": "no version", "want": "ignored", "payload": "src=kokoro;" + good},
        {"name": "a field that is not key=value", "want": "ignored", "payload": "v1;src kokoro;" + good},
        {"name": "bad base64", "want": "ignored", "payload": k + good[:40] + "*" + good[41:]},
        {"name": "padding in the middle", "want": "ignored", "payload": k + good[:40] + "=" + good[41:]},
        {"name": "not whole frames", "want": "ignored", "payload": k + _packed(n - 2, extra_bytes=1)},
        {"name": "another frame rate", "want": "ignored", "payload": k + _packed(n - 2, fps=50)},
        {"name": "no frames", "want": "ignored", "payload": k + "100:"},
        {"name": "before data", "want": "ignored", "payload": k + good, "where": "before"},
        {"name": "after an odd LIST missing its pad byte", "want": "ignored", "payload": k + good, "list": "unpadded"},
        {"name": "declared one byte short (odd)", "want": "ignored", "payload": k + good, "sizeDelta": -1},
        {"name": "declared past the end", "want": "ignored", "payload": k + good, "sizeDelta": 100},
        {"name": "the file cut short", "want": "ignored", "payload": k + good, "cut": 10},
    ]
    return fixture, specs


def mouth_fixture() -> bytes:
    src = MOUTH_SOURCE.read_bytes()
    fixture, _ = mouth_specs(src)
    return variant(src, fixture)


def build() -> str:
    clips = [{"name": p.name, "path": str(p)} for p in sorted(CLIPS.glob("*.wav"))]
    if not clips:
        raise SystemExit(f"no test clips in {CLIPS}")
    src = MOUTH_SOURCE.read_bytes()
    _, specs = mouth_specs(src)
    cases = []
    for spec in specs:
        b = variant(src, spec)
        cases.append({"spec": spec, "bytes": base64.b64encode(b).decode("ascii"),
                      "sha256": hashlib.sha256(b).hexdigest()})
    mouth = {"fixture": str(MOUTH_FIXTURE), "fixtureName": MOUTH_FIXTURE.name,
             "source": base64.b64encode(src).decode("ascii"), "sourceName": MOUTH_SOURCE.name,
             "cases": cases}
    res = subprocess.run(["node", "-e", NODE, str(LIPSYNC_JS)],
                         input=json.dumps({"clips": clips, "mouth": mouth}),
                         capture_output=True, text=True, check=True)
    # Each variant must be read as its spec says: "merged" (the shapes are
    # used), "kept apart" (read, but the lengths differ by more than 3
    # frames), "ignored" (as if the chunk were not there). Always the same
    # sound as the clip without it.
    got = json.loads(res.stdout)
    for c in got["mouth"]["cases"]:
        seen = "merged" if c["merged"] else "kept apart" if c["mouth"] else "ignored"
        if seen != c["want"] or not c["sameSound"]:
            raise SystemExit(f"lipsync.js reads the jmth variant {c['name']!r} as {seen!r} "
                             f"(same sound: {c['sameSound']}); it should be {c['want']!r}")
    if not got["mouth"]["sameSound"] or got["mouth"]["mouthN"] != got["mouth"]["n"] - 2:
        raise SystemExit("lipsync.js does not read the jmth fixture as made")
    return res.stdout


def main():
    check = "--check" in sys.argv
    want = mouth_fixture()
    have = MOUTH_FIXTURE.read_bytes() if MOUTH_FIXTURE.exists() else None
    if have != want:
        if check:
            print(f"{MOUTH_FIXTURE.relative_to(ROOT)} is out of date - run python3 tools/gen_lipsync.py",
                  file=sys.stderr)
            return 1
        MOUTH_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        MOUTH_FIXTURE.write_bytes(want)
        print(f"wrote {MOUTH_FIXTURE.relative_to(ROOT)}")
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
