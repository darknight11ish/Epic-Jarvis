#!/usr/bin/env python3
"""
Generates pattern-golden.json from shell.html's `_resolveRaw`.

The point is that the expected values come from the OTHER client. Every
Android face test before this compared Kotlin constants to other Kotlin
constants, which is why two transcription drifts survived a green suite. This
file is a faithful port of the reference switch — 640 samples across all twelve
patterns and all eight shipped state bindings — and PatternGoldenTest replays
it against resolveRaw().

Re-run only when shell.html's algorithm genuinely changes, and say so in the
commit. Regenerating it to make a failing test pass is the one thing that turns
this file back into what it replaced.

    python3 tools/gen_golden.py
"""
import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = ROOT / "jarvis-client/app/src/test/resources/jarvis-visual-spec.json"
OUT = ROOT / "jarvis-client/app/src/test/resources/pattern-golden.json"

spec = json.loads(SPEC.read_text())
PAL = {c["id"]: c["hex"] for c in spec["palette"]["colors"]}
FLASH = spec["limits"]["flash"]
PATTERNS = {p["id"]: p for p in spec["patterns"]}


def hx(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def hexOf(x):
    return hx(PAL.get(x, x)) if isinstance(x, str) else x


def lift(c, k):
    f = lambda v: max(0, min(255, round(v + (255 - v) * k if k >= 0 else v * (1 + k))))
    return tuple(f(v) for v in c)


def mix(a, b, k):
    k = max(0, min(1, k))
    return tuple(round(a[i] + (b[i] - a[i]) * k) for i in range(3))


def hsl2(h, s, l):
    h = ((h % 360) + 360) % 360
    s = max(0, min(1, s))
    l = max(0, min(1, l))
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l - c / 2
    if h < 60: r, g, b = c, x, 0
    elif h < 120: r, g, b = x, c, 0
    elif h < 180: r, g, b = 0, c, x
    elif h < 240: r, g, b = 0, x, c
    elif h < 300: r, g, b = x, 0, c
    else: r, g, b = c, 0, x
    return tuple(round((v + m) * 255) for v in (r, g, b))


def famRamp(f):
    return [hx(c["hex"]) for c in spec["palette"]["colors"] if c["family"] == f]


def hash01(n):
    s = math.sin(n * 127.1) * 43758.5453
    return s - math.floor(s)


FLOOR = {"period_s": 6, "sat": .7, "light": .6, "span_deg": 90, "offset_deg": 0,
         "depth": .25, "sharpness": 9, "gain": 1, "hold_s": 2, "blend_s": .45, "rate_hz": 0}


def pnum(q, k):
    v = q.get(k)
    if isinstance(v, (int, float)):
        return v
    return FLASH["flicker_rate_hz_max"] if k == "rate_hz" else FLOOR[k]


def REF(pid, bind, t, amp, seed=0):
    P = PATTERNS[pid]
    q = dict(P.get("params", {}))
    q.update(bind.get("params", {}) or {})
    bc = bind.get("color")
    pick = lambda i: hexOf(bc or i)
    k = P["kind"]
    if k == "solid":
        a = pick(q.get("color")); return a, lift(a, -0.55)
    if k == "hue_sweep":
        span = pnum(q, "span_deg"); off = pnum(q, "offset_deg")
        ph = (t / pnum(q, "period_s")) % 1
        h = off + (ph * 360 if span == 360 else math.sin(ph * math.pi * 2) * span * 0.5)
        sat = pnum(q, "sat"); light = pnum(q, "light")
        return hsl2(h, sat, light), hsl2(h + 28, sat * .9, light * .55)
    if k == "step_cycle":
        lst = [hexOf(c) for c in (q.get("colors") or [])]
        hold = pnum(q, "hold_s"); blend = pnum(q, "blend_s"); unit = hold + blend
        tot = t % (unit * len(lst)); i = int(tot // unit); into = tot - i * unit
        j = (i + 1) % len(lst)
        kk = 0 if into <= hold else (into - hold) / blend
        a = lst[i] if kk <= 0 else mix(lst[i], lst[j], kk)
        return a, lift(a, -0.55)
    if k == "breathe":
        base = pick(q.get("color")); d = pnum(q, "depth")
        e = (math.sin(t / pnum(q, "period_s") * math.pi * 2) * .5 + .5) * d
        return lift(base, e * .8 - d * .25), lift(base, -0.6 + e * .3)
    if k == "pulse":
        base = pick(q.get("color"))
        ph = max(0, math.sin(t / pnum(q, "period_s") * math.pi * 2))
        e = ph ** pnum(q, "sharpness")
        return lift(base, e * .75), lift(base, -0.7 + e * .4)
    if k == "gradient":
        A = hexOf(bc or q.get("from"))
        B = hexOf(bind["to"]) if bind.get("to") else (lift(A, -0.38) if bc else hexOf(q.get("to")))
        kk = math.sin(t / pnum(q, "period_s") * math.pi * 2) * .5 + .5
        return mix(A, B, kk), mix(B, A, kk)
    if k == "comet":
        head = hexOf(bc or q.get("color")); tail = hexOf(q.get("tail"))
        kk = (t / pnum(q, "period_s")) % 1
        e = (1 - abs(kk * 2 - 1)) ** 3
        return mix(tail, head, e), tail
    if k == "flicker":
        ramp = famRamp(q.get("family") or "ember")
        r = min(pnum(q, "rate_hz"), FLASH["flicker_rate_hz_max"]); d = pnum(q, "depth")
        n = hash01(math.floor(t * r) + seed * 17) * .6 + hash01(math.floor(t * r * 2.3) + seed * 31) * .4
        idx = min(len(ramp) - 1, max(0, round(1 + n * d * (len(ramp) - 1))))
        return ramp[idx], ramp[max(0, idx - 2)]
    if k == "reactive":
        A = hexOf(bc or q.get("quiet")); B = hexOf(q.get("loud"))
        kk = max(0, min(1, amp * pnum(q, "gain")))
        a = mix(A, B, kk); return a, lift(a, -0.55)
    if k == "temperature":
        kk = math.sin(t / pnum(q, "period_s") * math.pi * 2) * .5 + .5
        a = mix(hexOf(q["cold"]), hexOf(q["warm"]), kk * 2) if kk < .5 \
            else mix(hexOf(q["warm"]), hexOf(q["hot"]), (kk - .5) * 2)
        return a, lift(a, -0.5)
    if k == "strobe":
        minP = 2 / FLASH["max_transitions_per_s"]
        on = ((t / max(pnum(q, "period_s"), minP)) % 1) < .5
        a = hexOf(bc or q["a"]) if on else hexOf(q["b"])
        return a, lift(a, -0.5)
    raise SystemExit(f"unhandled kind {k}")


def h(c):
    return "#%02x%02x%02x" % c


cases = []
for pid in PATTERNS:
    for i in range(40):
        t = round(i * 0.37, 4); amp = round((i % 11) / 10, 3); seed = i % 5
        a, b = REF(pid, {}, t, amp, seed)
        cases.append({"pattern": pid, "t": t, "amp": amp, "seed": seed, "a": h(a), "b": h(b)})

for s in spec["states"]:
    d = s["default"]
    for i in range(20):
        t = round(i * 0.53, 4); amp = round((i % 7) / 6, 3)
        bind = {"color": d.get("color"), "params": d.get("params", {})}
        a, b = REF(d["pattern"], bind, t, amp, 0)
        cases.append({"state": s["id"], "pattern": d["pattern"], "color": d.get("color"),
                      "params": d.get("params", {}) or {}, "t": t, "amp": amp, "seed": 0,
                      "a": h(a), "b": h(b)})

OUT.write_text(json.dumps(
    {"note": "Generated from shell.html's _resolveRaw by tools/gen_golden.py. "
             "Do not hand-edit: the point is that these came from the OTHER client.",
     "cases": cases}, indent=1))
print(f"wrote {OUT} ({len(cases)} cases)")
