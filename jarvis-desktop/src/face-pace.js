/**
 * How hard an animal face works, and how often it is drawn - the rules both
 * of the desktop's face loops use (the Faces window's `budget()` and
 * `dueFrame()`, and display mode's `govern()` and `tick()` in the widget,
 * the HUD and the floating face).
 *
 * The owner's ask (2026-09-28, "Sharp animals on capable hardware"): on a
 * capable graphics chip, with quality chosen over battery saving, the animals
 * draw at full resolution - and higher resolution and frame-rate choices on
 * both apps. The numbers live in `jarvis-visual-spec.json`
 * (`frame_rate.animals`, `frame_rate.pick_rule`), read here through
 * faces-spec.js; the phone's `FaceBudget.kt` carries the same numbers, held
 * to the same file by its SpecDriftTest.
 *
 * Pure: every clock and cost is passed in, so `tests/face-pace.mjs` runs it
 * under node. A classic script (like critter-pose.js), because faces.html's
 * own script is one and must have it before its first frame.
 */
(function (root) {
  "use strict";
  const FR = ((root.JARVIS_SPEC || {}).frame_rate) || {};
  const A = FR.animals || {};
  const AUTO = A.auto || {};
  const REST = A.rest_fps || {};
  const HEAD = A.headroom || {};

  /** Stored ids, low to max, and what each does to an animal. */
  const LEVELS = (A.levels || [
    { id: "low", label: "Lower", desktop_scale: 0.62, desktop_supersample: 1, phone_trace: 0.4 },
    { id: "medium", label: "Balanced", desktop_scale: 0.8, desktop_supersample: 1, phone_trace: 0.5 },
    { id: "high", label: "High", desktop_scale: 1.0, desktop_supersample: 1, phone_trace: 0.75 },
    { id: "max", label: "Maximum", desktop_scale: 1.0, desktop_supersample: 2, phone_trace: 1.0 },
  ]).map((l) => Object.freeze(Object.assign({}, l)));
  const ORDER = LEVELS.map((l) => l.id);

  /** The most pixels a side an animal is traced at on the desktop (2x2 on a big window). */
  const MAX_PX = A.desktop_max_px || 2400;
  /** Auto climbs to Maximum only while frames take under this share of their budget. */
  const CLIMB_TO_MAX_BELOW = AUTO.climb_to_max_below || 0.25;
  /** A frame-rate step back up needs this; a quality step back up needs RAISE_QUALITY_BELOW. */
  const RAISE_RATE_BELOW = AUTO.raise_rate_below || 0.33;
  const RAISE_QUALITY_BELOW = AUTO.raise_quality_below || 0.55;
  const DOWNGRADE_ABOVE = (FR.budget && FR.budget.downgrade_above) || 1.45;
  const MIN_FPS = (FR.pacing && FR.pacing.min_fps) || 30;
  /** The soft shadow is skipped below this many device pixels (and at Lower). */
  const NO_SHADOW_BELOW_PX = A.no_shadow_below_px || 200;
  const HOLD_FIRST_MS = 10000, HOLD_MAX_MS = 120000;

  const jsRound = Math.round;

  /**
   * The pick rule (spec `frame_rate.pick_rule`): the nearest whole share of
   * the screen's rate, but never more than a fifth faster than what was
   * picked. 90 on a 144 Hz screen is 72, on a 120 Hz one 60.
   */
  function strideNear(hz, want) {
    const rate = Number(hz) > 0 ? Number(hz) : 60;
    const w = Math.min(Number(want) > 0 ? Number(want) : rate, rate);
    let s = Math.max(1, jsRound(rate / w));
    if (rate / s > w * 1.2) s++;
    return s;
  }
  /** The largest stride that still draws at least `fps` a second (a ladder step). */
  function strideAtLeast(hz, fps) {
    return Math.max(1, Math.floor(hz / fps + 1e-3));
  }
  /** A Frame rate choice ("auto", "30", "60", "90", "120", "max") as a stride. */
  function strideFor(target, hz) {
    const n = Number(target);
    return strideNear(hz, Number.isFinite(n) && n > 0 ? n : hz);
  }

  /**
   * How many times a second an ANIMAL is drawn in `state`, before the
   * active frame rate's own stride; 0 means every frame that allows.
   * `target` is the Frame rate choice ("auto" while Auto adjust is on).
   * `headroom`: frames are cheap (see Headroom). `busy`: an idle happening
   * is playing (the pose file's busy()). The other faces keep state_fps.
   */
  function restFps(state, target, headroom, busy) {
    if (state === "standby") return REST.standby || 15;
    if (state === "banked") return REST.banked || 2;
    const states = REST.states || ["idle", "approval"];
    if (states.indexOf(state) < 0) return 0;
    const t = String(target || "auto");
    if (t === "max") return 0;
    const n = Number(t);
    if (Number.isFinite(n) && n > 0) return n;
    if (busy && state === "idle") return REST.auto_happening || 0;
    return headroom ? (REST.auto_headroom || 60) : (REST.auto_no_headroom || 30);
  }

  /**
   * Whether frames are cheap: the average cost under ON_BELOW of a 60 fps
   * frame, lost again above OFF_ABOVE of it. Not until MIN_FRAMES frames
   * have been seen, so the first, costliest frames of a face never count.
   */
  function makeHeadroom() {
    const budget = 1000 / (HEAD.budget_fps || 60);
    const on = (HEAD.on_below || 0.5) * budget, off = (HEAD.off_above || 0.8) * budget;
    const min = HEAD.min_frames || 10;
    let avg = 0, n = 0, yes = false;
    return {
      frame(costMs) {
        if (!Number.isFinite(costMs) || costMs < 0) return yes;
        avg = n === 0 ? costMs : avg * 0.9 + costMs * 0.1;
        n++;
        if (n >= min) yes = yes ? avg <= off : avg < on;
        return yes;
      },
      reset() { avg = 0; n = 0; yes = false; },
      get on() { return yes; },
      get avg() { return avg; },
    };
  }

  /**
   * Auto adjust's ladder for an animal (spec `frame_rate.animals.auto.step_down`):
   * Maximum -> High, then the frame rate down to 60, then Balanced, then 30,
   * then Lower. Each rung is {tier, stride}; a step that changes nothing on
   * this screen (60 on a 60 Hz one) is left out. `base` is the frame-rate
   * choice's own stride, which no rung goes under.
   */
  function ladder(hz, base = 1) {
    const b = Math.max(1, base | 0);
    const s60 = Math.max(b, strideAtLeast(hz, 60)), s30 = Math.max(b, strideAtLeast(hz, MIN_FPS));
    const raw = [["max", b], ["high", b], ["high", s60], ["medium", s60], ["medium", s30], ["low", s30]];
    const out = [];
    for (const [tier, stride] of raw) {
      const last = out[out.length - 1];
      if (!last || last.tier !== tier || last.stride !== stride) out.push({ tier, stride });
    }
    return out;
  }
  /** Where `tier` at `stride` sits on the ladder: exact, else the first rung no richer. */
  function rungOf(L, tier, stride) {
    const ti = ORDER.indexOf(tier);
    let i = L.findIndex((r) => r.tier === tier && r.stride === stride);
    if (i < 0) i = L.findIndex((r) => ORDER.indexOf(r.tier) <= ti && r.stride >= stride);
    return i < 0 ? L.length - 1 : i;
  }

  /**
   * One Auto adjust decision for an animal, made at most once per cooldown
   * by the caller. `load` is the average frame cost over the budget of the
   * rate being drawn. `top` is the highest tier allowed ("max", or "high"
   * where the caller will not climb that far). `holds` is makeHolds(): a
   * rung just stepped down from is not climbed back to for a while, longer
   * each time. Returns the new rung index, or `i` for no change.
   */
  function decide(L, i, load, top, holds, now) {
    if (load > DOWNGRADE_ABOVE) {
      if (i + 1 >= L.length) return i;
      holds.left(i, now);
      return i + 1;
    }
    if (i <= 0) return i;
    const up = L[i - 1];
    if (ORDER.indexOf(up.tier) > ORDER.indexOf(top)) return i;
    if (holds.held(i - 1, now)) return i;
    const need = up.tier === "max" ? CLIMB_TO_MAX_BELOW
               : up.stride < L[i].stride ? RAISE_RATE_BELOW : RAISE_QUALITY_BELOW;
    return load < need ? i - 1 : i;
  }
  function makeHolds() {
    const until = [], hold = [];
    return {
      left(i, now) {
        hold[i] = hold[i] ? Math.min(hold[i] * 2, HOLD_MAX_MS) : HOLD_FIRST_MS;
        until[i] = now + hold[i];
      },
      held(i, now) { return now < (until[i] || 0); },
      reset() { until.length = 0; hold.length = 0; },
    };
  }

  /** One level's numbers, by stored id (anything unknown is High). */
  function level(id) { return LEVELS.find((l) => l.id === id) || LEVELS[2]; }

  /**
   * How many pixels a side an animal is traced at: the level's share of the
   * `px` the face fills, times its supersample, and never more than MAX_PX.
   * `gpuPx` is what the page already works out for shader faces (device
   * pixels times the level's scale).
   */
  function tracePx(w, gpuPx, id) {
    const base = Math.max(96, Math.min(w, gpuPx));
    return Math.max(96, Math.min(MAX_PX, Math.round(base * (level(id).desktop_supersample || 1))));
  }
  /** Whether to skip the soft shadow: a face under NO_SHADOW_BELOW_PX, or Lower. */
  function noShadow(drawnPx, id) { return id === "low" || drawnPx < NO_SHADOW_BELOW_PX; }

  /** The readout under the full-size face: "60 fps · 4.2 ms per frame · animal resolution 1200 px (100%)". */
  function readout(fps, ms, animal) {
    let s = `${Math.round(fps)} fps · ${(Number(ms) || 0).toFixed(1)} ms per frame`;
    if (animal && animal.px > 0 && animal.of > 0) {
      s += ` · animal resolution ${Math.round(animal.px)} px (${Math.round((animal.px / animal.of) * 100)}%)`;
    }
    return s;
  }

  const api = Object.freeze({
    LEVELS, ORDER, MAX_PX, CLIMB_TO_MAX_BELOW, RAISE_RATE_BELOW, RAISE_QUALITY_BELOW, DOWNGRADE_ABOVE,
    MIN_FPS, NO_SHADOW_BELOW_PX, HOLD_FIRST_MS,
    strideNear, strideAtLeast, strideFor, restFps, makeHeadroom, ladder, rungOf, decide, makeHolds,
    level, tracePx, noShadow, readout,
  });
  root.FacePace = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
