#!/usr/bin/env python3
"""Write the sky golden fixture both apps are checked against.

The sun, the moon and the weather behind the animal faces are worked out by
`jarvis-desktop/src/sky.js` on the desktop and by a line-for-line Kotlin
copy on the phone (`jarvis-client/.../face/Sky.kt`). This runs the
JavaScript under node at fixed moments and places - the solstices and
equinoxes, both halves of the world, a polar day and a polar night, a new,
quarter and full moon - with and without weather, and saves what it
returns in `sky-golden.json`. The phone's `SkyTest` fails if the Kotlin copy
disagrees (1e-6 on every number, two seconds on a rising or setting), so the
two cannot drift apart quietly.

    python3 tools/gen_sky.py          # rewrite the fixture
    python3 tools/gen_sky.py --check  # exit 1 if it is out of date

CI runs `--check`. Needs node on PATH.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKY_JS = ROOT / "jarvis-desktop" / "src" / "sky.js"
OUT = ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "sky-golden.json"

# Runs in node: argv[1] = sky.js, stdin = the cases. Numbers rounded to 9
# decimals, far inside the test's 1e-6, to keep the file stable.
NODE = r"""
const S = require(process.argv[1]);
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const r = (x) => (typeof x === "number" && !Number.isInteger(x) ? Math.round(x * 1e9) / 1e9 : x);
const deep = (v) => Array.isArray(v) ? v.map(deep)
  : (v && typeof v === "object") ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, deep(x)]))
  : r(v);
const out = { phases: S.PHASES, tint: S.TINT, layout: S.LAYOUT, bodies: [], scenes: [], outlines: [], hashes: [] };
for (const c of input.bodies) {
  const s = S.sun(c.ms, c.lat, c.lon), m = S.moon(c.ms, c.lat, c.lon);
  out.bodies.push(deep({ ms: c.ms, lat: c.lat, lon: c.lon,
    gmst: S.gmst(c.ms),
    sun: { alt: s.alt, az: s.az, H: s.H, ra: s.ra, dec: s.dec, lambda: s.lambda },
    moon: { alt: m.alt, altGeo: m.altGeo, az: m.az, H: m.H, ra: m.ra, dec: m.dec, parallax: m.parallax,
            elong: m.elong, fraction: m.fraction, waxing: m.waxing, phase: m.phase, chi: m.chi, tilt: m.tilt },
    summary: S.summary(c.ms, c.lat, c.lon),
    // The settings line, with times as UTC "HH:MM" so the file is the same
    // everywhere (each app uses its own clock).
    today: S.todayWords(S.summary(c.ms, c.lat, c.lon), (t) => new Date(t).toISOString().slice(11, 16)) }));
}
for (const c of input.scenes) {
  const sc = S.scene(c.ms, c.t, c.place, c.weather, c.opts);
  out.scenes.push(deep({ ms: c.ms, t: c.t, place: c.place, weather: c.weather, opts: c.opts, scene: sc }));
}
for (const c of input.outlines) {
  out.outlines.push(deep({ fraction: c[0], bx: c[1], by: c[2], n: c[3], pts: S.moonOutline(c[0], c[1], c[2], c[3]) }));
}
for (let i = -3; i < 40; i += 7) out.hashes.push([i, r(S.hash01(i))]);
out.tints = [-30, -18, -12, -5, -2, 0, 3, 6, 12, 20, 45].map((a) => [a, S.tintAt(a).map(r)]);
process.stdout.write(JSON.stringify(out, null, 1) + "\n");
"""


def utc(y, mo, d, h=0, mi=0):
    import calendar
    return calendar.timegm((y, mo, d, h, mi, 0, 0, 0, 0)) * 1000


PLACES = {
    "london": (51.48, 0.0),
    "new_york": (40.7, -74.0),
    "denver": (39.7, -105.0),
    "sydney": (-33.9, 151.2),
    "singapore": (1.3, 103.8),
    "reykjavik": (64.1, -21.9),
    "longyearbyen": (78.2, 15.6),
    "ushuaia": (-54.8, -68.3),
}


def cases():
    bodies = []
    moments = [utc(2024, 6, 21, 3, 43), utc(2024, 6, 21, 12), utc(2024, 12, 21, 21, 32),
               utc(2025, 3, 20, 13, 2), utc(2024, 1, 25, 17, 54), utc(2024, 4, 8, 18, 21),
               utc(2024, 1, 18, 3, 52), utc(2026, 9, 28, 6, 30)]
    for i, (name, (lat, lon)) in enumerate(sorted(PLACES.items())):
        for j, ms in enumerate(moments):
            if (i + j) % 2 == 0 or name in ("london", "sydney", "longyearbyen"):
                bodies.append({"ms": ms, "lat": lat, "lon": lon})
    rain = {"rain": 0.7, "snow": 0, "wind": 0.4, "cloud": 0.8, "fog": 0, "dir": -1}
    snow = {"rain": 0, "snow": 0.8, "wind": 0.3, "cloud": 0.6, "fog": 0.1, "dir": 1}
    wind = {"rain": 0, "snow": 0, "wind": 0.9, "cloud": 0.2, "fog": 0, "dir": 1}
    fog = {"rain": 0.1, "snow": 0.1, "wind": 0.0, "cloud": 1.0, "fog": 1.0, "dir": 1}
    ny = {"lat": 40.7, "lon": -74.0}
    syd = {"lat": -33.9, "lon": 151.2}
    polar = {"lat": 78.2, "lon": 15.6}
    scenes = [
        {"ms": utc(2024, 6, 21, 9, 50), "t": 1000.25, "place": ny, "weather": None, "opts": {}},    # dawn
        {"ms": utc(2024, 6, 21, 16, 55), "t": 1000.25, "place": ny, "weather": None, "opts": {}},   # noon
        {"ms": utc(2024, 6, 22, 0, 25), "t": 1000.25, "place": ny, "weather": None, "opts": {}},    # dusk
        {"ms": utc(2024, 1, 26, 5, 0), "t": 1000.25, "place": ny, "weather": None, "opts": {}},     # full moon
        {"ms": utc(2024, 1, 14, 23, 0), "t": 1000.25, "place": ny, "weather": None, "opts": {}},    # crescent
        {"ms": utc(2024, 1, 14, 9, 30), "t": 1000.25, "place": syd, "weather": None, "opts": {}},
        {"ms": utc(2024, 6, 21, 23, 0), "t": 1000.25, "place": polar, "weather": None, "opts": {}},  # midnight sun
        {"ms": utc(2024, 12, 21, 12, 0), "t": 1000.25, "place": polar, "weather": None, "opts": {}},
        {"ms": utc(2025, 1, 1, 15, 0), "t": 1234.5, "place": ny, "weather": rain, "opts": {}},
        {"ms": utc(2025, 1, 1, 15, 0), "t": 1234.5, "place": ny, "weather": rain, "opts": {"calm": True}},
        {"ms": utc(2025, 1, 1, 3, 0), "t": 1759000000.125, "place": ny, "weather": snow, "opts": {}},
        {"ms": utc(2025, 1, 1, 3, 0), "t": 77.75, "place": None, "weather": wind, "opts": {"ax": 1.5, "ay": 1}},
        {"ms": utc(2025, 1, 1, 3, 0), "t": 77.75, "place": syd, "weather": fog, "opts": {"ax": 1, "ay": 1.4}},
    ]
    outlines = [[0.0, 1, 0, 8], [0.25, 0.6, -0.8, 12], [0.5, 0, 1, 8], [0.93, -0.28, 0.96, 10], [1.0, 1, 0, 6]]
    return {"bodies": bodies, "scenes": scenes, "outlines": outlines}


def render() -> str:
    res = subprocess.run(["node", "-e", NODE, str(SKY_JS)], input=json.dumps(cases()),
                         capture_output=True, text=True, check=True)
    return res.stdout


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        have = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if have != text:
            print(f"{OUT.relative_to(ROOT)} is out of date - run python3 tools/gen_sky.py")
            return 1
        print("sky golden: up to date")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
