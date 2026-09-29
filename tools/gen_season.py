#!/usr/bin/env python3
"""Write the seasonal-touches golden fixture both apps are checked against.

The seasonal touches behind the character faces are worked out by
`jarvis-desktop/src/season.js` on the desktop and by a line-for-line Kotlin
copy on the phone (`jarvis-client/.../face/Season.kt`). This runs the
JavaScript under node at fixed moments - every season in both halves of the
world, the edges of each season and holiday (the hour they fade over), the
New Year sparkle, time zones either side of UTC (and a half-hour one) - with
and without calm motion, Still, an approval, weather and a wide or tall
frame, and saves what it returns in `season-golden.json`. The phone's
`SeasonTest` fails if the Kotlin copy disagrees (1e-6 on every number), so
the two cannot drift apart quietly.

    python3 tools/gen_season.py          # rewrite the fixture
    python3 tools/gen_season.py --check  # exit 1 if it is out of date

CI runs `--check`. Needs node on PATH.
"""
import calendar
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEASON_JS = ROOT / "jarvis-desktop" / "src" / "season.js"
OUT = ROOT / "jarvis-client" / "app" / "src" / "test" / "resources" / "season-golden.json"

# Runs in node: argv[1] = season.js, stdin = the cases. Numbers rounded to 9
# decimals, far inside the test's 1e-6, to keep the file stable.
NODE = r"""
const S = require(process.argv[1]);
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const r = (x) => (typeof x === "number" && !Number.isInteger(x) ? Math.round(x * 1e9) / 1e9 : x);
const deep = (v) => Array.isArray(v) ? v.map(deep)
  : (v && typeof v === "object") ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, deep(x)]))
  : r(v);
const out = {
  layout: S.LAYOUT, seasons: S.SEASONS, holidays: S.HOLIDAYS, snowman: S.SNOWMAN, sparkle_s: S.SPARKLE_S,
  leaf_rgb: S.LEAF_RGB, petal_rgb: S.PETAL_RGB, bulb_rgb: S.BULB_RGB,
  shapes: deep({ leaf: S.leafShape(), petal: S.petalShape(), glint: S.glintShape() }),
  civil: [], calendars: [], holds: [], scenes: [],
};
for (const d of input.civil) {
  out.civil.push({ days: d, ymd: S.civilFromDays(d), back: S.daysFromCivil(...S.civilFromDays(d)) });
}
for (const c of input.calendars) {
  const k = S.calendar(c.ms, c.tz, c.lat);
  out.calendars.push(deep({ ms: c.ms, tz: c.tz, lat: c.lat, south: k.south, local: k.local, season: k.season,
    seasons: k.seasons, day: k.day, items: k.items, sparkleSec: k.sparkleSec }));
}
for (const h of input.holds) out.holds.push(deep({ state: h[0], prev: h[1], since: h[2], w: S.holdWeight(h[0], h[1], h[2]) }));
for (const c of input.scenes) {
  const sc = S.scene(c.ms, c.tz, c.t, c.opts);
  out.scenes.push(deep({ ms: c.ms, tz: c.tz, t: c.t, opts: c.opts, season: sc.season, ax: sc.ax, ay: sc.ay,
    ops: sc.ops.map((o) => [o.k].concat(o.v)) }));
}
process.stdout.write(JSON.stringify(out, null, 1) + "\n");
"""


def utc(y, mo, d, h=0, mi=0, s=0):
    return calendar.timegm((y, mo, d, h, mi, s, 0, 0, 0)) * 1000


def local(y, mo, d, h, mi, s, tz):
    """UTC milliseconds of a local wall-clock moment at offset `tz` minutes."""
    return utc(y, mo, d, h, mi, s) - tz * 60000


def cases():
    civil = [-719468, -1, 0, 59, 11016, 19782, 20452, 20819, 20820, 2932896]
    cals = []
    # The 15th of every month at noon, New York, both halves of the world.
    for mo in range(1, 13):
        for lat in (40.7, -33.9, None):
            cals.append({"ms": local(2026, mo, 15, 12, 0, 0, -300), "tz": -300, "lat": lat})
    # The edges: midnight crossings and the hour they fade over.
    edges = [(2026, 12, 1, 0, 30), (2026, 11, 30, 23, 59), (2027, 3, 1, 0, 10), (2026, 10, 24, 0, 20),
             (2026, 11, 1, 0, 45), (2026, 12, 18, 0, 5), (2027, 1, 2, 0, 30), (2027, 1, 2, 1, 30),
             (2026, 12, 15, 0, 40), (2027, 2, 1, 0, 15), (2026, 6, 15, 0, 30), (2024, 2, 29, 12, 0)]
    for (y, mo, d, h, mi) in edges:
        for tz in (-300, 0, 330, 600, -210):
            cals.append({"ms": local(y, mo, d, h, mi, 0, tz), "tz": tz, "lat": 51.5 if tz >= 0 else -12.0})
    # New Year's first minute.
    for s in (0, 2, 20, 45, 57, 61):
        cals.append({"ms": local(2027, 1, 1, 0, 0, s, -300), "tz": -300, "lat": 40.7})
    holds = [[a, b, s] for a in ("idle", "approval", "error") for b in ("idle", "approval", "error", "speaking")
             for s in (0, 0.2, 0.4, 0.79, 2.0)]
    ny = -300
    scenes = []

    def sc(ms, tz, t, **opts):
        scenes.append({"ms": ms, "tz": tz, "t": t, "opts": opts})

    m = local(2026, 11, 20, 15, 0, 0, ny)

    sc(m, ny, m / 1000, lat=40.7)
    sc(m, ny, 1234.5, lat=40.7, calm=True)
    sc(m, ny, 1234.5, lat=40.7, hold=0.5)
    sc(m, ny, 1234.5, lat=40.7, ax=1.5, ay=1)
    m = local(2026, 10, 28, 15, 0, 0, -240)
    sc(m, -240, m / 1000, lat=40.7)
    sc(m, -240, m / 1000, lat=40.7, hold=1)
    m = local(2026, 12, 24, 20, 0, 0, ny)
    sc(m, ny, m / 1000, lat=40.7)
    sc(m, ny, m / 1000, lat=40.7, calm=True, ax=1, ay=1.8)
    sc(m, ny, m / 1000, lat=40.7, snow=0.6)
    sc(m, ny, m / 1000, lat=40.7, hide=0.3, hold=0.2)
    sc(m, ny, m / 1000, lat=40.7, hide=1)
    m = local(2027, 2, 10, 9, 0, 0, ny)
    sc(m, ny, m / 1000, lat=None)
    for s in (5, 25, 44):
        m = local(2027, 1, 1, 0, 0, s, ny)
        sc(m, ny, m / 1000, lat=40.7)
    m = local(2027, 1, 1, 0, 0, 30, ny)
    sc(m, ny, m / 1000, lat=40.7, calm=True)
    m = local(2027, 4, 20, 15, 0, 0, -240)
    sc(m, -240, m / 1000, lat=40.7)
    sc(m, -240, 77.25, lat=40.7, calm=True, ax=1.3, ay=1)
    m = local(2027, 7, 10, 14, 0, 0, -240)
    sc(m, -240, m / 1000, lat=40.7, sunAlt=62.0)
    sc(m, -240, m / 1000, lat=40.7)
    sc(m, -240, m / 1000, lat=40.7, sunAlt=62.0, rain=0.8)
    m = local(2027, 7, 10, 22, 30, 0, -240)
    sc(m, -240, m / 1000, lat=40.7, sunAlt=-14.0)
    sc(m, -240, m / 1000, lat=40.7)
    sc(m, -240, 99.5, lat=40.7, calm=True)
    sc(m, -240, m / 1000, lat=40.7, sunAlt=-2.0, rain=0.25)
    # The southern half of the world: late November is summer, July winter.
    m = local(2026, 11, 20, 23, 0, 0, 660)
    sc(m, 660, m / 1000, lat=-33.9, sunAlt=-20.0)
    m = local(2027, 7, 1, 12, 0, 0, 600)
    sc(m, 600, m / 1000, lat=-33.9)
    # A season changing over, New York, 00:30 on 1 December.
    m = local(2026, 12, 1, 0, 30, 0, ny)
    sc(m, ny, m / 1000, lat=40.7)
    # The owl's scenery covers the snowman's corner: none for it.
    m = local(2026, 12, 24, 20, 0, 0, ny)
    sc(m, ny, m / 1000, lat=40.7, snowman=False)
    # The tropics: no autumn leaves and no winter snow; the holidays stay.
    # Singapore in December (the lights), Mumbai in late October (the
    # pumpkin), and just outside the line (Hong Kong, 22.3 - inside; Taipei,
    # 25.0 - outside) and south of it (Darwin, -12.5, in July's "winter").
    for lat in (1.3, 22.3, 25.0):
        m = local(2026, 12, 24, 20, 0, 0, 480)
        sc(m, 480, m / 1000, lat=lat)
    m = local(2026, 10, 28, 15, 0, 0, 330)
    sc(m, 330, m / 1000, lat=19.1)
    m = local(2027, 7, 1, 12, 0, 0, 570)
    sc(m, 570, m / 1000, lat=-12.5)
    return {"civil": civil, "calendars": cals, "holds": holds, "scenes": scenes}


def render() -> str:
    res = subprocess.run(["node", "-e", NODE, str(SEASON_JS)], input=json.dumps(cases()),
                         capture_output=True, text=True, check=True)
    return res.stdout


def main(argv) -> int:
    text = render()
    if "--check" in argv:
        have = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if have != text:
            print(f"{OUT.relative_to(ROOT)} is out of date - run python3 tools/gen_season.py")
            return 1
        print("season golden: up to date")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
