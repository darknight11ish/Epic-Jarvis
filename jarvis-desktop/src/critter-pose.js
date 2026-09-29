/**
 * The red panda's body language: where its head, ears, eyes, paws, tail and
 * orb are on any frame, for any of Jarvis's eight states.
 *
 * Why this is separate from the shader. The shader (`critters/redpanda.sksl`,
 * generated into `critters-gen.js`) only knows how to DRAW a panda in a given
 * pose. Working the pose out - a head tilt, a blink, a wave - is a few dozen
 * sums, and doing them here once a frame costs nothing, where doing them in
 * the shader would repeat them for every pixel on every step of the march.
 *
 * The phone runs a line-for-line Kotlin copy of this file
 * (`jarvis-client/.../face/CritterPose.kt`). They cannot share code - one is
 * JavaScript, one is Kotlin - so they share ANSWERS instead:
 * `tools/gen_critters.py` runs this file under node at fixed moments and
 * writes what it returns into a test fixture, and `CritterPoseTest` on the
 * phone fails if the Kotlin copy disagrees. A drift between the two is a red
 * build, not a panda that waves differently on the phone.
 *
 * Everything here is a pure function of (state, previous state, seconds
 * since the change, clock, loudness, where the pointer is, and the mouth
 * shape being heard). Nothing carries over from the last frame, so the same
 * inputs always draw the same panda. What looks random - where it glances,
 * when it blinks, when it stretches - is a hash of the clock, not a dice
 * roll, so both apps draw the same "random" panda.
 *
 * The motion follows a few people's published work, each credited where it
 * is used (and in THIRD-PARTY-NOTICES.txt): Daniel Holden's "Spring-It-On"
 * for how one pose settles into the next, Mika Suominen's TalkingHead for
 * holding still and then easing, for the blinks and for eyes that lead the
 * head, moeru-ai's airi for the pauses between glances, and pixiv's ChatVRM
 * for how much of a look the head takes.
 *
 * Coordinates: x to the viewer's right, y up, the panda faces -z (toward the
 * camera). Angles in radians.
 */
(function (root) {
  "use strict";

  const TAU = Math.PI * 2;

  /**
   * About how long the BODY takes to settle into a new state, in seconds.
   * Each part has its own time now - see the half-lives below.
   */
  const BLEND_S = 0.55;

  // Overlapping action: on a change of state the parts do not all arrive
  // together. The eyes get there first, then the mouth and the head, then
  // the paws and the body, and the loose parts (tail, ears, wings) last -
  // swinging a little past and settling back, the way a tail follows the
  // animal it is attached to. Each is a "half-life": the time in which what
  // is left of the change halves. Most of a change is done in about three
  // half-lives.
  const HL_EYES = 0.035, HL_MOUTH = 0.07, HL_HEAD = 0.13, HL_LIMB = 0.15, HL_BODY = 0.18, HL_TRAIL = 0.22;
  // The painted eyelid (uLid) arrives after the eyes' own squash and the head:
  // 0.25 s, so a lid is mostly down in under a second and never pops.
  const HL_LID = 0.25;

  // The pose is a flat list of numbers so two of them can be blended
  // element by element. These are the names, in order. (New names go on the
  // end, so the phone's index constants keep their meaning.)
  const KEYS = [
    "headYaw", "headPitch", "headRoll", "lean", "bob", "breath",
    "earL", "earR", "eyeL", "eyeR", "brow", "speak", "lookX", "lookY",
    "pawLx", "pawLy", "pawLz", "pawRx", "pawRy", "pawRz",
    "tailSwing", "tailCurl", "orbX", "orbY", "orbZ", "orbR", "orbGlow",
    "bodyRoll", "earTwL", "earTwR", "tail2", "tail3", "tail4", "tail5",
    "asleep",
    // The painted eyelid (uLid): how far down it is, and its slope.
    "lid", "lidSlope",
  ];

  // Where things rest, in the body's own frame (origin on the seat).
  const LAP = { orb: [0, 0.34, -0.44, 0.095], pawL: [-0.15, 0.30, -0.40], pawR: [0.15, 0.30, -0.40] };

  /**
   * A small integer hash. Not `fract(sin(n) * 43758)`: that trick depends on
   * the exact rounding of a sine of a large number, which a 32-bit Kotlin
   * float and a 64-bit JavaScript double do not share - the two apps would
   * blink at different moments. Integer multiply-and-shift is exact in both.
   */
  function hash01(n) {
    let x = (n | 0) ^ 0x5bd1e995;
    x = Math.imul(x ^ (x >>> 15), 0x2c1b3c6d);
    x = Math.imul(x ^ (x >>> 12), 0x297a2d39);
    x ^= x >>> 15;
    return (x >>> 0) / 4294967296;
  }

  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const smooth = (k) => k * k * (3 - 2 * k);

  /**
   * An ease in and out, 0..1 for x in 0..1, that starts AND ends at rest:
   * its speed and its change of speed are both zero at each end
   * ("smootherstep"). It takes the place of TalkingHead's sigmoidFactory(5)
   * (met4citizen/TalkingHead, MIT), whose logistic curve was not quite still
   * at its ends - a small step in speed as every weight shift and head turn
   * began and ended.
   */
  function ease(x) {
    const k = clamp(x, 0, 1);
    return k * k * k * (k * (6 * k - 15) + 10);
  }

  /* ------------------------------------------------------------------ *
   * The clock, kept small.
   *
   * The phone's clock is a 32-bit float and can run for days. The sine of
   * a large number is where a float and a double part company, so every
   * rhythm here is a whole number of cycles per LOOP seconds, worked out
   * from the time within the loop - exact in both - and never from the raw
   * clock. LOOP is a power of two, so dividing by it is exact too.
   * ------------------------------------------------------------------ */
  const LOOP = 1024;
  function loopT(t) { return t - LOOP * Math.floor(t / LOOP); }
  /**
   * Everything that looks random repeats every PERIOD seconds (68 minutes):
   * the number of each time slot is taken round PERIOD before it is hashed.
   * Nobody will notice a stretch returning after an hour, and it means an
   * app may restart its clock at any multiple of PERIOD (the phone keeps
   * its clock small that way) without the animal jumping. Every rhythm
   * here (LOOP, the 2-, 16- and 32-second slots) divides it.
   */
  const PERIOD = 4096;
  /** Slot number n of `span`-second slots, taken round PERIOD (exact, negatives too). */
  function slotId(n, span) { return n & (PERIOD / span - 1); }
  /** A sine making exactly k cycles per LOOP (so k / 1024 cycles a second). */
  function wave(t, k, ph) { return Math.sin(phaseOf(t, k) + ph); }
  /** Where a rhythm of k cycles per LOOP is at clock t: 0..2pi, exact in both apps. */
  function phaseOf(t, k) {
    const u = (loopT(t) / LOOP) * k;
    return TAU * (u - Math.floor(u));
  }
  /* ------------------------------------------------------------------ *
   * Smooth drift that does not repeat (2026-09-29, the skeptical review:
   * "all five heads sway almost identically" and "breathing is a
   * metronome"). A sine has one period, so every face that used the same
   * one swayed in step, and a breath was exactly as long as the last.
   * noise() is a slow, smooth wander instead, seeded per face and per use:
   *
   *  - it is a uniform cubic B-spline through random control values, one
   *    every `scale` seconds (a power of two). That curve is smooth (no
   *    corner, no sudden change of speed) and can never leave -1..1;
   *  - its speed is bounded by construction: at most 2 / scale a second (a
   *    spline's slope is a weighted average of the gaps between neighbouring
   *    control values, and no gap is more than 2), so "how fast can it move"
   *    is a number written here, not a hope;
   *  - the control values are picked with the same integer hash as
   *    everything else, taken round PERIOD, so it repeats only after the
   *    4096 seconds every other rhythm here repeats after, and the phone may
   *    restart its clock at any multiple of that. JavaScript and Kotlin
   *    agree (integer hash, a handful of sums).
   * ------------------------------------------------------------------ */
  function ctrl(seed, j) {
    const h = hash01((seed & 255) * 8192 + j * 2), s = hash01((seed & 255) * 8192 + j * 2 + 1);
    // 0.5..1 in size, either way up: a control value near 0 would make a dead
    // stretch, and the wander should keep moving a little.
    return (s < 0.5 ? -1 : 1) * (0.5 + 0.5 * h);
  }
  /** -1..1, smooth, changing by at most 2 / scale a second; `scale` a power of two (seconds), `seed` under 256. */
  function noise(t, seed, scale) {
    const n = PERIOD / scale;
    const tl = t - PERIOD * Math.floor(t / PERIOD);
    const u = tl / scale, i = Math.floor(u), f = u - i;
    const c0 = ctrl(seed, (i + n - 1) % n), c1 = ctrl(seed, i % n), c2 = ctrl(seed, (i + 1) % n), c3 = ctrl(seed, (i + 2) % n);
    const g = 1 - f;
    return (c0 * g * g * g + c1 * (3 * f * f * f - 6 * f * f + 4) + c2 * (-3 * f * f * f + 3 * f * f + 3 * f + 1) + c3 * f * f * f) / 6;
  }
  /**
   * A breath at clock t, -1..1 like the sine it replaces, but uneven: the
   * phase is the steady one (k cycles a LOOP) plus a slow wander, so the
   * breath's rate drifts by at most BREATH_VAR either way (each breath's
   * length varies by about that much) and its depth by up to a tenth (never deeper than the steady breath was). `seed` is
   * the face's own.
   */
  const BREATH_VAR = 0.20, BREATH_SPAN = 16;
  function breathWave(t, k, seed) {
    const w0 = TAU * k / LOOP;   // radians a second at the steady rate
    const ph = phaseOf(t, k) + BREATH_VAR * (BREATH_SPAN / 2) * w0 * noise(t, seed, BREATH_SPAN);
    return Math.sin(ph) * (0.95 + 0.05 * noise(t, seed + 1, 32));
  }

  /** 0 at both ends, 1 in the middle, with no sudden start or stop (x in 0..1). */
  function bump(x) {
    if (x <= 0 || x >= 1) return 0;
    const s = Math.sin(Math.PI * x);
    return s * s;
  }
  /** Eases up over `a` seconds, holds for `h`, eases down over `r`; 0 outside. */
  function envAHR(x, a, h, r) {
    if (x <= 0 || x >= a + h + r) return 0;
    if (x < a) return smooth(x / a);
    if (x < a + h) return 1;
    return smooth(1 - (x - a - h) / r);
  }

  /* ------------------------------------------------------------------ *
   * Things that happen now and then. All are worked out from the clock by
   * the hash above, so they are the same on both apps and on every replay,
   * and none of them repeats on a beat.
   *
   * Each has its own "salt" (under 256; ids are multiplied by 256, so two
   * never share a draw), so the glances, the stretches and the blinks do
   * not all roll the same dice. Each purpose uses a few salts from its own
   * (each function says which), and each animal has its own set, so three
   * animals side by side do not glance or blink together.
   * ------------------------------------------------------------------ */

  /**
   * A number between lo and hi, more often near the middle: the average of
   * five draws, bent toward lo by `skew` above 1. TalkingHead's
   * gaussianRandom (met4citizen/TalkingHead, MIT), with the hash in place of
   * Math.random. Uses salts salt..salt+4.
   */
  function gauss(id, salt, lo, hi, skew) {
    let r = 0;
    for (let i = 0; i < 5; i++) r += hash01(id * 256 + salt + i);
    return lo + Math.pow(r / 5, skew) * (hi - lo);
  }

  /**
   * The pause before the eyes' next small dart, 0.8 to 4.8 seconds: the
   * table of moeru-ai/airi's randomSaccadeInterval (packages/stage-ui-three/
   * .../vrm/utils/eye-motions.ts, MIT) - chances for each 400 ms step, most
   * often the longest. Uses salts salt, salt+1.
   */
  const SACCADE_P = [0.075, 0.185, 0.31, 0.45, 0.575, 0.625, 0.665, 0.695, 0.715, 1.0];
  function saccadeGap(id, salt) {
    const r = hash01(id * 256 + salt);
    let i = 0;
    while (i < 9 && r > SACCADE_P[i]) i++;
    return 0.8 + 0.4 * i + 0.4 * hash01(id * 256 + salt + 1);
  }

  /**
   * Things that happen one after another with random pauses between them:
   * glances, blinks, weight shifts. The pauses are gauss(lo, hi, skew).
   *
   * Pure, so it cannot remember when the last one was. Instead time is cut
   * into `span`-second stretches (a power of two, so the cut is exact on
   * both apps), and each stretch starts its own run of pauses from its
   * start - so finding the latest one never walks back further than one
   * stretch. A pause never runs past its stretch, and the first pause of a
   * stretch is a whole pause, so no two are ever closer than `lo`.
   *
   * Returns [id of the latest one at or before t, seconds since it, id of
   * the one before, seconds until the next, seconds between the one before
   * and this one]. Ids are unique, for hashing what each one IS.
   */
  // The index of the last one in stretch n at or before `limit` seconds
  // into it (-1: none yet), and its time.
  function lastIn(n, span, limit, salt, lo, hi, skew) {
    let k = -1, at = 0;
    for (let j = 0; j < 32; j++) {
      const next = at + gauss(slotId(n, span) * 32 + j, salt, lo, hi, skew);
      if (next > limit || next >= span) break;
      k = j; at = next;
    }
    return [k, at];
  }
  function chain(t, span, salt, lo, hi, skew) {
    const n = Math.floor(t / span), local = t - n * span;
    let a = lastIn(n, span, local, salt, lo, hi, skew);
    let cn = n, cLocal = local;
    if (a[0] < 0) { cn = n - 1; cLocal = local + span; a = lastIn(cn, span, span, salt, lo, hi, skew); }
    const id = slotId(cn, span) * 32 + a[0], since = cLocal - a[1];
    // The next one: in the same stretch, or the first of the next.
    const nx = a[1] + gauss(id + 1, salt, lo, hi, skew);
    const until = nx < span ? nx - cLocal : span + gauss(slotId(cn + 1, span) * 32, salt, lo, hi, skew) - cLocal;
    // The one before: in the same stretch, or the last of the one before.
    let prev, hold;
    if (a[0] > 0) {
      prev = id - 1;
      hold = gauss(id, salt, lo, hi, skew);
    } else {
      const b = lastIn(cn - 1, span, span, salt, lo, hi, skew);
      prev = slotId(cn - 1, span) * 32 + b[0];
      hold = span - b[1] + a[1];
    }
    return [id, since, prev, until, hold];
  }

  /**
   * 0 open .. 1 shut. TalkingHead's blink (animTemplateBlink, MIT): a pause
   * of `lo` to `hi` seconds, more often short (TalkingHead uses 1 to 8; a
   * calm animal on a desk blinks less, so these are longer); the lids close
   * in 60 ms, stay shut for a moment, open in 100 ms; about one blink in
   * seven is a double blink. `salt` gives each animal its own blinks, so no
   * two blink in unison; `slow` stretches the blink (a dozing animal's).
   * Salts salt..salt+6.
   */
  function blinkAt(t, salt, slow, lo, hi) {
    const c = chain(t, 32, salt, lo, hi, 1.6);
    const shut = (0.06 + 0.1 * hash01(c[0] * 256 + salt + 5)) * slow;
    const lid = (x) => {
      if (x <= 0) return 0;
      if (x < 0.06 * slow) return smooth(x / (0.06 * slow));
      if (x < 0.06 * slow + shut) return 1;
      return 1 - smooth(clamp((x - 0.06 * slow - shut) / (0.10 * slow), 0, 1));
    };
    const one = lid(c[1]);
    const two = hash01(c[0] * 256 + salt + 6) < 0.15 ? lid(c[1] - (0.06 * slow + shut + 0.10 * slow + 0.12)) : 0;
    return Math.max(one, two);
  }
  /** The panda's blinks (kept for anything that still asks for them). */
  function blink(t) { return blinkAt(t, S_BLINK, 1, 2, 10); }

  const NONE = [-1, 0, 0];
  /**
   * Something that happens now and then: time is cut into `slot`-second
   * slots, and with chance `chance` a slot has one happening, starting
   * `lead` to `lead + spread` seconds in. Returns [which kind, seconds since
   * it started (negative before), the clock it starts at], or [-1, 0, 0] for
   * none. A happening must be over before its slot ends, so two never
   * overlap. Salts salt..salt+2.
   *
   * `kinds` is how often each kind comes up, relative to the others (a
   * number n instead means n kinds, all as often). A kind is never the same
   * as the one in the slot just before - two stretches in a row read as a
   * loop, not as an animal. Pure, like everything here: it cannot remember
   * the slot before, so it works it out again. Each slot's kind is drawn
   * leaving out the kind of the slot before, which was drawn leaving out
   * the one before that, and so on back to the first slot of the run (the
   * one after a slot with nothing in it). The same walk gives the same
   * answer from every frame, so a slot's kind never changes under it.
   */
  const RUN_MAX = 32;
  function pickKind(r, kinds, avoid) {
    let total = 0;
    for (let i = 0; i < kinds.length; i++) if (i !== avoid) total += kinds[i];
    let x = r * total;
    for (let i = 0; i < kinds.length; i++) {
      if (i === avoid) continue;
      if (x < kinds[i]) return i;
      x -= kinds[i];
    }
    for (let i = kinds.length - 1; i >= 0; i--) if (i !== avoid) return i;
    return 0;
  }
  function kindAt(n, slot, salt, chance, kinds) {
    const has = (m) => hash01(slotId(m, slot) * 256 + salt) < chance;
    if (!has(n)) return -1;
    if (kinds.length < 2) return 0;
    let m = n;
    while (m > n - RUN_MAX && has(m - 1)) m--;
    let k = -1;
    for (let j = m; j <= n; j++) k = pickKind(hash01(slotId(j, slot) * 256 + salt + 1), kinds, k);
    return k;
  }
  const EVEN = [[1], [1, 1], [1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1, 1], [1, 1, 1, 1, 1, 1]];
  function happening(t, slot, lead, spread, salt, chance, kinds) {
    if (typeof kinds === "number") kinds = EVEN[kinds - 1];
    const n = Math.floor(t / slot);
    const kind = kindAt(n, slot, salt, chance, kinds);
    if (kind < 0) return NONE;
    const off = lead + spread * hash01(slotId(n, slot) * 256 + salt + 2);
    // (t - n * slot) first: exact on the phone's 32-bit clock, days long.
    return [kind, t - n * slot - off, n * slot + off];
  }

  /**
   * happening() for the idle happenings, with two more things (2026-09-29,
   * the skeptical review):
   *
   *  - Each one is a little different. A slot's hash also gives it a SIZE
   *    (0.75 to 1: never bigger than the tested clip) and a LENGTH (the same
   *    clip played 0.8 to 1.25 times as long: `x` comes back already divided
   *    by it, so a caller reads the clip's own time, and playing() still
   *    works). Before, the panda's tail flick was the very same clip 28
   *    times in 30 minutes.
   *  - Fewer of them when Jarvis is not being used. `att` (the host's
   *    `attention`, 0..1) is 1 while the owner has talked to Jarvis lately or
   *    is pointing at the face, else 0. At 0, about one slot in four still has
   *    its happening (the same clips, only rarer); the rest have none. Each
   *    slot has its own threshold, so as `att` eases over a couple of seconds
   *    the others fade in one by one and a clip already playing grows or
   *    shrinks smoothly - nothing snaps. At 1 (and when a host passes
   *    nothing) every slot keeps its happening exactly as before.
   *
   * Returns [kind, seconds since it started (negative before), the clock it
   * starts at, weight]: `weight` is size times the thinning, 0..1, for the
   * caller to scale the clip by. [-1, 0, 0, 1] for none. `vsalt` is the
   * first of three salts for the size, length and thinning (default salt + 3).
   */
  const NONE4 = [-1, 0, 0, 1];
  const EV_SIZE_LO = 0.75, EV_LONG = 1.25, THIN_KEEP = 0.25, THIN_RAMP = 0.5;
  function thinGate(n, slot, vsalt, att) {
    const r = hash01(slotId(n, slot) * 256 + vsalt);
    // The attention at which this slot's happening is fully back: below zero
    // (always kept) for the quarter that stay when Jarvis is not being used.
    const th = r < THIN_KEEP ? -1 : (r - THIN_KEEP) / (1 - THIN_KEEP) * (1 - THIN_RAMP);
    return smooth(clamp((att - th) / THIN_RAMP, 0, 1));
  }
  function happeningV(t, slot, lead, spread, salt, chance, kinds, att, vsalt) {
    const h = happening(t, slot, lead, spread, salt, chance, kinds);
    if (h[0] < 0) return NONE4;
    if (vsalt === undefined) vsalt = salt + 3;
    const n = Math.floor(t / slot), id = slotId(n, slot) * 256;
    const size = EV_SIZE_LO + (1 - EV_SIZE_LO) * hash01(id + vsalt + 1);
    const long = Math.pow(EV_LONG, 2 * hash01(id + vsalt + 2) - 1);
    return [h[0], h[1] / long, h[2], size * thinGate(n, slot, vsalt, att == null ? 1 : att)];
  }

  /**
   * A talking gesture (a nod, a paw or wing lifted, a tilt), in phrases: at
   * most one in each two-second slot, often none, never the same kind twice
   * running - and none at all when one of the eyes' looks (gazeSalt, lo, hi
   * and contact: the state's own gaze()) moves the eyes within LOOK_CLEAR
   * seconds either side of it, so a gesture never lands on top of the head
   * turning to look. (A look from you back to you moves nothing, and does
   * not count.) Returns happening()'s three numbers.
   */
  const BEAT_KINDS = [4, 3, 3];
  const LOOK_CLEAR = 1.5;
  function beat(t, salt, gazeSalt, lo, hi, contact) {
    const b = happening(t, 2, 0, 0.6, salt, 0.45, BEAT_KINDS);
    if (b[0] < 0) return b;
    return clearOfLooks(b[2], gazeSalt, lo, hi, contact) ? b : NONE;
  }
  /** Whether no look moves the eyes within LOOK_CLEAR seconds either side of clock `at` (see beat()). */
  function clearOfLooks(at, gazeSalt, lo, hi, contact) {
    // Whether the look that starts with look `id` moves the eyes at all.
    const atYou = (id) => hash01(id * 256 + gazeSalt + 5) < contact;
    const moves = (c) => !(atYou(c[0]) && atYou(c[2]));
    const c = chain(at, 32, gazeSalt, lo, hi, 1.3);
    if (c[1] < LOOK_CLEAR && moves(c)) return false;
    const n = chain(at + LOOK_CLEAR, 32, gazeSalt, lo, hi, 1.3);
    return !(n[0] !== c[0] && moves(n));
  }

  /**
   * A slow weight shift, -1..1. TalkingHead's idle body (animMoods.neutral,
   * MIT): hold a lean for a while (here 3 to 9 seconds), then ease over to a
   * new one (here in two seconds, starting and ending at rest - see ease()).
   * A step and a hold, not a sway, so it reads as settling rather than as
   * rocking. Salts salt..salt+5.
   */
  function shift(t, salt) {
    const c = chain(t, 32, salt, 3, 9, 1);
    const a = 2 * hash01(c[2] * 256 + salt + 5) - 1, b = 2 * hash01(c[0] * 256 + salt + 5) - 1;
    return a + (b - a) * ease(c[1] / 2.0);
  }

  /*
   * Where it is looking. Two layers, as TalkingHead and ChatVRM do it:
   *
   *  - LOOKS: it looks at something (you, or somewhere else) and holds that
   *    for lo..hi seconds (TalkingHead's animTemplateEyes). The eyes JUMP
   *    there in 70 ms - a saccade, not a drift - and the head follows them,
   *    later and slower, taking only part of the turn (ChatVRM's
   *    VRMLookAtSmoother gives the head 40% of a look).
   *  - DARTS: within a look, the eyes alone make small jumps, with airi's
   *    pauses between them (at least 0.8 s), and never in the last 0.6 s
   *    before the next look - so a look is always held at least 0.6 s.
   *
   * Returns [eyes x, eyes y, head x, head y, blink], x and y -1..1-ish. The
   * head numbers are the look the head is turning toward (the caller turns
   * it only part of the way); the eyes are where the eyes are pointing.
   * The blink is 1 as a big look starts: real eyes blink as they turn far.
   * Salts salt..salt+7 and salt+8..salt+11.
   */
  function lookX(id, salt, contact, sx) {
    return hash01(id * 256 + salt + 5) < contact ? 0 : sx * (2 * hash01(id * 256 + salt + 6) - 1);
  }
  function lookY(id, salt, contact, sy, yb) {
    return hash01(id * 256 + salt + 5) < contact ? 0 : yb + sy * (2 * hash01(id * 256 + salt + 7) - 1);
  }
  // The dart offset reached `since` seconds into look `id`, which is held
  // for `hold` seconds in all: [x, y, seconds since that dart].
  function dartAt(id, since, hold, salt, amp) {
    let at = 0, x = 0, y = 0, j = 0, age = since;
    for (; j < 8; j++) {
      const next = at + saccadeGap(id * 8 + j, salt + 8);
      if (next > since || next > hold - 0.6) break;
      at = next;
      x = amp * (2 * hash01((id * 8 + j) * 256 + salt + 10) - 1);
      y = 0.6 * amp * (2 * hash01((id * 8 + j) * 256 + salt + 11) - 1);
      age = since - at;
    }
    return [x, y, age];
  }
  function gaze(t, salt, lo, hi, contact, sx, sy, yb, dart, headS) {
    const c = chain(t, 32, salt, lo, hi, 1.3);
    const x1 = lookX(c[0], salt, contact, sx), y1 = lookY(c[0], salt, contact, sy, yb);
    const x0 = lookX(c[2], salt, contact, sx), y0 = lookY(c[2], salt, contact, sy, yb);
    // Where the eyes were as the look changed: the old look plus its last dart.
    const d0 = dartAt(c[2], c[4], c[4], salt, dart);
    const d1 = dartAt(c[0], c[1], c[1] + c[3], salt, dart);
    const e = smooth(clamp(c[1] / 0.07, 0, 1));
    const de = smooth(clamp(d1[2] / 0.05, 0, 1));
    const fx = x0 + d0[0], fy = y0 + d0[1];
    const ex = fx + (x1 - fx) * e + d1[0] * de, ey = fy + (y1 - fy) * e + d1[1] * de;
    const h = ease((c[1] - 0.12) / headS);
    const big = Math.abs(x1 - x0) > 0.9 ? bump(c[1] / 0.2) : 0;
    return [ex, ey, x0 + (x1 - x0) * h, y0 + (y1 - y0) * h, big];
  }

  /*
   * The three ways the owner (or the moment) can ask an animal to move less.
   * Each is a weight, 0 (off) to 1 (on) - the host eases it over about a
   * second when it is switched, so nothing snaps; true counts as 1.
   *
   *  - calm: the owner's reduced (desktop) or calm (phone) motion. The head
   *    takes less of each look, the idle happenings and the talking
   *    gestures stop, and the slow rhythmic movements (the head's wander,
   *    the weight shifts, the tail's swish, the otter's water, the owl's
   *    orb and tilt while it thinks) are smaller.
   *  - serious: a crisis moment (the owner's call: "calm and plain"). A
   *    calm, attentive listener - no happenings, no gestures, no playful
   *    poses and no tilts; slower, steadier looks; blinking and breathing.
   *  - still: the owner's "Still" option. It sits calmly and only breathes:
   *    no looks led by the head, no gestures, no happenings, its eyes resting
   *    on you with only tiny darts; blinking and breathing stay.
   *
   * None of them touches the mouth: it follows the voice whatever is set.
   *
   * A fourth weight, `quiet`, is never set by a host: the pose sets it
   * itself for the couple of seconds an animal is waking up (see "Waking up
   * and falling asleep" below). It takes the happenings, the talking
   * gestures and the ordinary blinks away (the looks stay the state's own),
   * so the wake-up never lands on top of a stretch or a nod.
   */
  function optsOf(o, now) {
    o = o || {};
    if (o._n) return o;   // already worked out (makePose hands the same one on)
    const w = (v) => (v === true ? 1 : clamp(+v || 0, 0, 1));
    const num = (v, d) => (typeof v === "number" && isFinite(v) ? v : d);
    const t0 = num(now, 0);
    // A moment the host gives as SECONDS SINCE it happened, turned into the
    // clock it happened at - so a pose worked out at an earlier clock (the
    // settling does that) sees it at the right distance. Left out, or
    // negative: none (NEVER seconds ago).
    const at = (v) => { const a = num(v, NEVER); return a >= 0 && a < NEVER ? t0 - a : -NEVER; };
    // An owner's switch (jarvis_animal.SWITCHES, by its id): on unless given.
    const sw = (v) => (v == null ? 1 : w(v));
    return {
      calm: w(o.calm), serious: w(o.serious), still: w(o.still), quiet: 0,
      // The new behaviours (see "New behaviours" below and docs/CRITTERS.md):
      // the owner's switches, eased by the host like the options...
      nods: sw(o.nods), focusBuddy: sw(o.focus_buddy), acks: sw(o.acks), petting: sw(o.petting),
      cute: sw(o.cute_moments != null ? o.cute_moments : o.cute),
      // ...and what is happening.
      variety: w(o.variety), focus: w(o.focus),
      pet: w(o.pet), petX: clamp(num(o.petX, 0), -1, 1), petDir: clamp(num(o.petDir, 0), -1, 1),
      hello: o.hello == null ? 1 : w(o.hello), goodbye: w(o.goodbye),
      heardAt: at(o.heard), heardN: Math.floor(num(o.heardN, -1)),
      // Jarvis's phrase ends: either one that has happened (`phraseEnd`, seconds
      // since), or - the host having read the whole clip before it plays - the
      // next one still ahead (`phraseDue`, seconds until it; negative once it
      // has passed). With `phraseDue` the gesture is timed to LAND on the end
      // (phraseBeat), not to start there.
      phraseAt: typeof o.phraseDue === "number" && isFinite(o.phraseDue) ? t0 + clamp(o.phraseDue, -30, 30) : at(o.phraseEnd),
      phraseAhead: typeof o.phraseDue === "number" && isFinite(o.phraseDue) ? 1 : 0,
      phraseN: Math.floor(num(o.phraseN, -1)),
      // How much the owner is using Jarvis (2026-09-29): 1 (the default: as it
      // always was) or fewer idle happenings when 0. See happeningV.
      attention: o.attention == null ? 1 : w(o.attention),
      nodAt: at(o.ackNod), glowAt: at(o.ackGlow), focusEndAt: at(o.focusEnd),
      arrive: -1,
      _n: 1,
    };
  }
  /**
   * How much of each kind of movement is left under the options:
   * [the idle happenings and talking gestures, the head's share of a look,
   *  the slow rhythmic movements, a playful or tilted pose].
   */
  function mods(o) {
    return [
      1 - Math.max(o.calm, o.serious, o.still, o.quiet || 0),
      (1 - 0.6 * Math.max(o.calm, o.serious)) * (1 - o.still),
      (1 - 0.5 * o.calm) * (1 - 0.7 * o.serious) * (1 - o.still),
      1 - o.serious,
    ];
  }
  /**
   * gaze(), with the options folded in. Serious: slower, steadier looks,
   * mostly at you. Still: the eyes rest on you, darting only a little (the
   * same look as waiting on you). The head's two numbers come back already
   * scaled by the head's share, so a state that turns its head by them
   * turns it less, and its eyes - which take the rest of each look - more.
   */
  function looks(t, salt, lo, hi, contact, sx, sy, yb, dart, headS, o) {
    let g = gaze(t, salt, lo, hi, contact, sx, sy, yb, dart, headS);
    if (o.serious > 0) {
      g = mix5(g, gaze(t, salt, 3, 9, Math.max(contact, 0.6), 0.6 * sx, 0.6 * sy, yb, 0.5 * dart, 1.5 * headS), o.serious);
    }
    if (o.still > 0) g = mix5(g, restingGaze(t, salt), o.still);
    const k = mods(o)[1];
    return [g[0], g[1], k * g[2], k * g[3], g[4]];
  }
  /** Eyes on you, with only tiny darts: waiting on you, something wrong, "Still". */
  function restingGaze(t, salt) { return gaze(t, salt, 2, 7, 1, 0, 0, 0, 0.03, 1.1); }
  function mix5(a, b, k) {
    const o = new Array(5);
    for (let i = 0; i < 5; i++) o[i] = a[i] + (b[i] - a[i]) * k;
    return o;
  }

  /* ------------------------------------------------------------------ *
   * New behaviours (the owner, 2026-09-28: "New animal behaviours, all four
   * chosen", "Two cute idle moments per face", "Goodbye and hello when
   * switching faces", "Variety, never over the top"). docs/CRITTERS.md,
   * "New behaviours", lists every input a host passes for them (all in
   * `opts`, all optional) and what each animal does.
   *
   * The rules every one keeps:
   *  - Left out, an input changes nothing: a host that passes none of them
   *    draws exactly what it drew before.
   *  - Still, serious and a wake-up's quiet switch every one off; calm
   *    makes them smaller (newOf). Eased, as the weights themselves are.
   *  - None while waiting on you (approval) or after something went wrong
   *    (error), except the small reaction as either arrives, and none
   *    asleep or dozing.
   *  - The mouth is never touched: it follows Jarvis's real voice only.
   *  - Each is eased in and out (bump, envAHR, ease), so nothing jumps or
   *    changes speed suddenly, and nothing but a blink moves faster than
   *    three times a second.
   *  - A moment (a pause heard, a phrase ending, a fact saved...) is given
   *    as seconds since it happened, and turned into the clock it happened
   *    at (optsOf) - so the settling, which works poses out at earlier
   *    clocks, sees each one where it was.
   * ------------------------------------------------------------------ */
  const NEVER = 1e9;
  const ZERO2 = [0, 0], ZERO4 = [0, 0, 0, 0], ZERO5 = [0, 0, 0, 0, 0];
  /** How much of a new behaviour the options leave: none under still, serious or a wake-up's quiet; calm makes it smaller. */
  function newOf(o) { return (1 - o.still) * (1 - o.serious) * (1 - o.quiet) * (1 - 0.6 * o.calm); }
  /** The variants of listening, thinking and the arrivals: the host's `variety` (it passes 1), with the options. */
  function varOf(o) { return o.variety * newOf(o); }
  /** Working beside you in a focus session: none under still or serious. */
  function focusOf(o) { return o.focus * o.focusBuddy * (1 - o.still) * (1 - o.serious); }
  /** Being stroked. */
  function petOf(o) { return o.pet * o.petting * newOf(o); }
  /** The two cute idle moments: the owner's switch, none in a focus session. */
  function cuteOf(o) { return o.cute * newOf(o) * (1 - o.focus); }
  // Where each can happen: awake and not in a serious look.
  const AWAKE = { idle: 1, listening: 1, thinking: 1, speaking: 1 };

  /**
   * The k-th of `n` things in a shuffled order that never gives the same
   * one twice running: the numbers are dealt in shuffled hands of k (a
   * "shuffle bag"), and a hand that would start with the one the last hand
   * ended with swaps its first two. Pure: hand b is a hash of b. For k of
   * 3 or more. n counts from 0.
   */
  function bagOrder(b, k, salt) {
    const a = [];
    for (let i = 0; i < k; i++) a.push(i);
    for (let i = k - 1; i > 0; i--) {
      const j = Math.min(i, Math.floor(hash01(((b & 4095) * 8 + i) * 256 + salt) * (i + 1)));
      const s = a[i]; a[i] = a[j]; a[j] = s;
    }
    return a;
  }
  function bagKind(n, k, salt) {
    const b = Math.floor(n / k), i = n - b * k;
    const cur = bagOrder(b, k, salt);
    if (i < 2 && b > 0 && cur[0] === bagOrder(b - 1, k, salt)[k - 1]) {
      const s = cur[0]; cur[0] = cur[1]; cur[1] = s;
    }
    return cur[i];
  }

  /**
   * A listening nod, in one of the owner's pauses (o.heardAt, counted by
   * o.heardN - see pauseStep). Three kinds, never the same twice running:
   * [0] a small nod, [1] a smaller one with a tilt and a flick of the ears
   * (the owl: a fluff), [2] two little nods with a slow blink ("mm-hm").
   * About 3 degrees at most. Returns [head pitch, head roll, eyes shut
   * 0..1, ears] to add, with the options folded in.
   */
  const NOD_S = 1.3;
  function listenNod(t, o, salt) {
    const x = t - o.heardAt;
    if (!(x > 0 && x < NOD_S) || o.heardN < 0) return ZERO4;
    const w = o.nods * newOf(o), k = bagKind(o.heardN, 3, salt);
    if (k === 0) return [-w * 0.05 * (bump(x / 0.7) - 0.3 * bump((x - 0.55) / 0.7)), 0, 0, 0];
    if (k === 1) {
      return [-w * 0.035 * bump(x / 0.8), w * 0.05 * bump(x / 1.2), 0,
              w * (bump(x / 0.5) - 0.3 * bump((x - 0.35) / 0.5))];
    }
    return [-w * 0.03 * (bump(x / 0.5) + 0.8 * bump((x - 0.5) / 0.5)), 0, 0.5 * w * bump((x - 0.1) / 0.8), 0];
  }

  /**
   * A talking gesture at the end of one of Jarvis's phrases (o.phraseAt,
   * counted by o.phraseN), in place of beat()'s: the same three kinds, in a
   * shuffle bag so never the same twice running, and - like beat() - none
   * when the eyes move to look somewhere within LOOK_CLEAR of it. Returns
   * happening()'s three numbers.
   */
  function phraseBeat(t, o, salt, gazeSalt, lo, hi, contact) {
    const k = bagKind(Math.max(0, o.phraseN), 3, salt);
    // With the end known in advance (phraseDue) the gesture starts early
    // enough for its strongest moment to land on it: a nod peaks 0.35 s in,
    // a lift is at its top from 0.4 to 0.7 s (0.5 taken), a tilt at 0.6 s.
    const x = t - o.phraseAt + (o.phraseAhead ? PHRASE_LEAD[k] : 0);
    if (!(x >= 0 && x < 2)) return NONE;
    if (!clearOfLooks(o.phraseAt, gazeSalt, lo, hi, contact)) return NONE;
    return [k, x, o.phraseAt];
  }
  const PHRASE_LEAD = [0.35, 0.5, 0.6];

  /** The nod when a fact is saved (o.nodAt): [head pitch, ears] to add. About 2.5 degrees. */
  const ACK_S = 1.2;
  function ackNodOf(t, o) {
    const x = t - o.nodAt;
    if (!(x > 0 && x < ACK_S)) return ZERO2;
    const w = o.acks * newOf(o);
    return [-w * 0.045 * (bump(x / 0.75) - 0.3 * bump((x - 0.6) / 0.6)),
            w * (bump((x - 0.05) / 0.45) - 0.3 * bump((x - 0.4) / 0.5))];
  }
  /** The orb swelling once as a long answer is ready (o.glowAt): 0..1. */
  const GLOW_S = 1.8;
  function ackGlowOf(t, o) {
    const x = t - o.glowAt;
    return x > 0 && x < GLOW_S ? o.acks * newOf(o) * bump(x / GLOW_S) : 0;
  }
  /** The small stretch as a focus session ends (o.focusEndAt): 0..1. */
  const FOCUS_END_S = 3.2;
  function focusEndOf(t, o) {
    const x = t - o.focusEndAt;
    return x > 0 && x < FOCUS_END_S ? o.focusBuddy * newOf(o) * envAHR(x - 0.3, 0.9, 0.6, 1.4) : 0;
  }

  /**
   * A variant of listening or thinking, now and then: an 8-second slot has
   * one with chance `chance`, never the same kind as the slot before
   * (happening's rule). Returns [kind, envelope 0..1] - the envelope eases
   * up over 1.2 s, holds 1.4 s and eases down over 1.2 s - or [-1, 0].
   */
  function variant(t, o, salt, chance) {
    const w = varOf(o);
    if (w <= 0) return [-1, 0];
    const h = happening(t, 8, 0.5, 3.0, salt, chance, 3);
    return h[0] < 0 ? [-1, 0] : [h[0], w * envAHR(h[1], 1.2, 1.4, 1.2)];
  }

  /**
   * The small reaction as waiting on you or something going wrong arrives,
   * `x` seconds in, variant o.arrive (see arriveKind), then still. Returns
   * [head pitch, head roll, lean, eyes shut 0..1, ears] to add.
   *  - waiting on you: [0] it perks up a little, ears up; [1] a double
   *    blink and a small lean in; [2] a small tilt of interest.
   *  - something wrong: [0] a small start back, with a blink; [1] the head
   *    dips and the ears go back a touch; [2] one slow blink and a small
   *    tilt.
   */
  const ARRIVE_S = 1.3;
  function arrivalOf(state, o, x) {
    const w = o.arrive >= 0 && x > 0 && x < ARRIVE_S ? varOf(o) : 0;
    if (w <= 0) return ZERO5;
    const k = o.arrive;
    if (state === "approval") {
      if (k === 0) return [w * 0.05 * bump(x / 1.1), 0, 0, 0, w * bump(x / 1.1)];
      if (k === 1) return [0, 0, w * 0.02 * bump(x / 1.2), w * 0.9 * (bump(x / 0.25) + bump((x - 0.35) / 0.25)), 0];
      return [0, w * 0.05 * bump(x / 1.2), 0, 0, 0];
    }
    if (k === 0) return [0.01 * w * bump(x / 0.9), 0, -w * 0.03 * bump(x / 0.9), w * 0.8 * bump(x / 0.3), 0];
    if (k === 1) return [-w * 0.04 * bump(x / 1.2), 0, 0, 0, -w * bump(x / 1.2)];
    return [0, -w * 0.035 * bump(x / 1.2), 0, w * 0.85 * bump(x / 0.9), 0];
  }
  /**
   * Which variant the reaction to arriving in `state` (approval or error)
   * plays, `since` seconds into it, its own change being past[i]: a hash of
   * the 8-second slot it arrived in, never the variant the same state played
   * when it last arrived - if that was within the host's last few changes
   * (ARRIVE_BACK of them), which is when a repeat would be seen. -1 for any
   * other state.
   */
  const ARRIVE_BACK = 4;
  function arriveKind(state, past, i, since, t, salt) {
    if (state !== "approval" && state !== "error") return -1;
    let c = t - since;
    const at = [c];
    for (let j = i; j < i + ARRIVE_BACK && j < HIST_MAX && j < past.length; j++) {
      const pv = past[j];
      if (!pv || !pv.state || !(pv.gap < 1e8)) break;
      c -= pv.gap;
      if (pv.state === state) at.push(c);
    }
    let k = -1;
    for (let q = at.length - 1; q >= 0; q--) k = pickKind(hash01((Math.floor(at[q] / 8) & 4095) * 256 + salt), EVEN[2], k);
    return k;
  }

  /**
   * The two cute idle moments. Time is cut into CUTE_SLOT-second slots
   * (about four minutes), each with one moment starting 30 to 200 s in -
   * the two kinds taking turns, slot by slot - that plays only if the
   * animal had then been idle at least CUTE_AFTER seconds (`since` is how
   * long it has been idle). `lens` is how long each kind lasts. Returns
   * [kind, seconds since it started, the clock it started at] or NONE.
   */
  const CUTE_SLOT = 256, CUTE_AFTER = 150;
  function cuteAt(t, since, salt, lens) {
    const n = Math.floor(t / CUTE_SLOT);
    const id = slotId(n, CUTE_SLOT);
    const kind = id & 1;
    const start = n * CUTE_SLOT + 30 + 170 * hash01(id * 256 + salt);
    const x = t - start;
    if (x < 0 || x >= lens[kind] || since - x < CUTE_AFTER) return NONE;
    return [kind, x, start];
  }
  /**
   * A whole turn (2 pi), played from `a` seconds into a cute moment over
   * `len` seconds, at the moment's weight w: the otter rolling over, the
   * monkey twirling its banana. A turn cannot be made smaller and still end
   * where it began, so it plays only near full weight (q, from w 0.8 to 1)
   * - under calm the moment keeps only its other, smaller parts. Should the
   * weight change part way through, what is left over is turned back the
   * short way over the last 0.8 s before `end`, so it never jumps: it ends
   * on a whole number of turns, which is where it began.
   */
  function fullTurn(x, a, len, end, w) {
    const q = smooth(clamp((w - 0.8) / 0.2, 0, 1));
    return TAU * q * ease((x - a) / len) + TAU * (Math.floor(q + 0.5) - q) * ease((x - end + 0.8) / 0.8);
  }
  /** How much of the idle happenings a cute moment x seconds into its `len` leaves: none while it plays. */
  function cuteQuiet(x, len) { return envAHR(x, 0.8, len - 1.6, 0.8); }

  /**
   * Finding the pauses in someone talking, from a loudness (0..1) - the
   * owner's (the microphone, for the listening nods) or Jarvis's (its
   * voice, for the gestures at the phrase ends). Pure: the host keeps the
   * record and hands it back each frame with the seconds since the last
   * one, and puts rec.ago and rec.n in opts (heard/heardN or
   * phraseEnd/phraseN). A pause counts when the loudness has stayed under
   * PAUSE.OFF for `quietMin` seconds after at least PAUSE.TALK_MIN seconds
   * over PAUSE.ON, and the last pause counted was at least `gapMin` seconds
   * before - so a nod or a gesture always finishes before the next starts.
   * rec: {talk, quiet, ago, n} (null to start).
   *
   * PHRASE_QUIET is 0.05 s, not the 0.15 s it was (the voice-speed check,
   * 2026-09-28, docs/LIPSYNC.md "At every pace"). The loudness it is handed
   * takes about 0.15-0.2 s to fall under OFF after the sound stops, and two
   * of Jarvis's sentences played back to back leave only 0.1-0.15 s of it
   * at the normal pace and faster: at 0.15 s the finder caught 10 of 36
   * sentence ends at 1.0x and 1 of 36 at 1.3225x (real Kokoro clips, six
   * voices). At 0.05 s: 34 and 25 of 36 (the misses are one-word sentences,
   * under TALK_MIN), and still never inside a sentence at any pace the apps
   * offer (0.7225x to 1.3225x) - only at the commas, which are phrase ends
   * too. The microphone's NOD_QUIET is unchanged.
   */
  const PAUSE = Object.freeze({
    ON: 0.10, OFF: 0.05, TALK_MIN: 0.6,
    NOD_QUIET: 0.3, NOD_GAP: 3.0,         // the owner's pauses: a nod at most every 3 s
    PHRASE_QUIET: 0.05, PHRASE_GAP: 2.0,  // Jarvis's phrase ends: a gesture at most every 2 s
  });
  function pauseStep(rec, dt, level, quietMin, gapMin) {
    const r = rec || { talk: 0, quiet: 0, ago: NEVER, n: 0 };
    let talk = r.talk, quiet = r.quiet, ago = Math.min(NEVER, r.ago + Math.max(0, dt)), n = r.n;
    if (level >= PAUSE.ON) { talk += dt; quiet = 0; }
    else if (level <= PAUSE.OFF) quiet += dt;
    if (quiet >= quietMin && talk > 0) {
      if (talk >= PAUSE.TALK_MIN && ago >= gapMin) { ago = 0; n += 1; }
      talk = 0;
    }
    return { talk, quiet, ago, n };
  }

  /**
   * The host's side of gestures that land ON Jarvis's sentence ends
   * (2026-09-29; the skeptical review found a nod peaked 0.45-0.55 s after
   * the sentence it marked, inside the next one, because pauseStep only
   * hears an end once it is over). A host that has the whole clip before
   * it plays (JarvisLipSync.phraseEnds on the desktop, the same on the
   * phone) knows where each end will be, so it hands the pose the next end
   * BEFORE it comes, and the pose starts the gesture early enough for its
   * strongest moment to land on it (opts.phraseDue, phraseBeat).
   *
   * rec: {n, due} (null to start): `n` counts the ends handed over so far,
   * `due` is when the latest one is, in seconds from now (negative once it
   * has passed; null before the first). Each frame, hand it the seconds
   * since the last frame and `next`: the seconds until the clip's next end
   * still to come (null: none known). Put rec.due into opts.phraseDue and
   * rec.n into opts.phraseN. An end is taken up only when it is between
   * AHEAD.MIN and AHEAD.MAX seconds away - early enough that no gesture
   * (the longest starts 0.6 s before its end) begins part way in, not so
   * early that the one before is still playing - and only PAUSE.PHRASE_GAP
   * after the last one taken, the same spacing as pauseStep. One found too
   * late (the host started listening for ends part way into a clip) is left
   * out, not played half way.
   */
  const AHEAD = Object.freeze({ MIN: 0.65, MAX: 0.9 });
  function aheadStep(rec, dt, next) {
    const n = rec ? rec.n : 0;
    const due = rec && typeof rec.due === "number" ? rec.due - Math.max(0, dt) : null;
    if (typeof next === "number" && next >= AHEAD.MIN && next <= AHEAD.MAX
        && (due === null || next - due >= PAUSE.PHRASE_GAP)) {
      return { n: n + 1, due: next };
    }
    return { n, due };
  }

  // The panda's own dice.
  const S_GAZE = 0, S_EVENT = 16, S_ROLL = 24, S_LEAN = 32, S_BEAT = 40, S_BLINK = 48;
  // ...and for the new behaviours: listening's and thinking's variants, the
  // focus looks (twelve), the listening nods, the phrase-end gestures, the
  // cute moments.
  const S_LISTEN = 56, S_THINK = 59, S_FOCUS = 62, S_NOD = 74, S_PHRASE = 75, S_CUTE = 76;
  // ...and the panda's own seeds for the slow wander (noise()): its talking
  // sway, and its breathing. Each face has its own, so no two sway together.
  const N_YAW = 8, N_ROLL = 9, N_BREATH = 10;
  // How long each cute moment lasts: hugging its tail, playing with its orb.
  const CUTE_LEN = [7.0, 5.0];
  // Its idle happenings, and how often each comes up: the small ones (a
  // tail flick, an ear turning to a sound) most; the big ones (a stretch, a
  // scratch) about one time in eight each.
  const EVENTS = [12, 30, 12, 23, 23];   // stretch, tail flick, scratch, hears left, hears right

  /**
   * The panda's tail swing at clock `t`, in one state: the tail is drawn by
   * asking this for each of its segments at a slightly EARLIER time, the
   * tip the earliest - so a swing starts at the root and travels out to the
   * tip (follow-through, with no memory of past frames). `m` is mods().
   */
  function tailAt(state, t, m) {
    const sw = m[2];
    if (state === "listening") return sw * 0.12 * wave(t, 123, 0);
    if (state === "thinking") return sw * 0.2 * wave(t, 205, 0);
    if (state === "speaking") return sw * 0.14 * wave(t, 111, 1.0);
    if (state === "approval") return sw * 0.04 * wave(t, 81, 0);
    if (state === "standby") return 0;   // asleep: wrapped round, still
    if (state === "error") return sw * 0.03 * wave(t, 81, 0);
    if (state === "banked") return sw * 0.03 * wave(t, 70, 0);
    // idle: a slow swish, pushed the other way when its weight shifts, and
    // now and then a flick (the happening "tail flick", kind 1).
    let s = sw * (0.16 * wave(t, 87, 0) + 0.08 * wave(t, 139, 1.7) - 0.065 * shift(t - 0.6, S_ROLL));
    const ev = happeningV(t, 16, 0.5, 5.5, S_EVENT, 0.7, EVENTS);
    if (ev[0] === 1) s += m[0] * 0.32 * (bump(ev[1] / 0.8) - 0.3 * bump((ev[1] - 0.6) / 0.9));
    return s;
  }
  const TAIL_LAG = 0.12;

  /**
   * Whether one of the idle happenings is playing: happening()'s answer
   * [kind, seconds since it started, ...] has started and is not over.
   * HAPPENING_S is the longest one (the otter's roll: 1.4 + 1.8 + 1.8 s)
   * and a little over - the spec's frame_rate.animals.happening_s. Only the
   * frame pacer asks (faces.html, FaceView on the phone): at rest an animal
   * may be drawn 30 or 60 times a second, and while a stretch or a scratch
   * plays it is drawn at the screen's full rate, so the big movement is
   * smooth. Nothing about the pose depends on it.
   */
  const HAPPENING_S = 5.5;
  function playing(ev) { return ev[0] >= 0 && ev[1] >= 0 && ev[1] < HAPPENING_S; }
  /** playing(), for happeningV's answer: one thinned away (weight 0) is not playing. */
  function playingV(ev) { return playing(ev) && ev[3] > 0; }
  /** The panda's: an idle happening (the same dice its idle pose rolls) is playing at clock t. */
  function busy(state, t, since, opts) {
    return state === "idle" && (playingV(happeningV(t, 16, 0.5, 5.5, S_EVENT, 0.7, EVENTS, opts ? optsOf(opts, t).attention : 1))
      || cuteBusy(t, since, opts, S_CUTE, CUTE_LEN));
  }
  /**
   * Whether one of its own talking gestures (beat(): the timing used until
   * the host hands it Jarvis's phrase ends) is playing at clock t - a nod, a
   * paw lift or a tilt, at most GESTURE_S long. The host asks before it
   * switches the gestures over to the phrase ends part way into an answer
   * (faces.html's phraseOn), so a gesture is never cut off half way.
   */
  const GESTURE_S = 2;
  function gesturing(t) {
    const b = beat(t, S_BEAT, S_GAZE, 1.8, 6, 0.65);
    return b[0] >= 0 && b[1] >= 0 && b[1] < GESTURE_S;
  }
  /**
   * Whether one of the moments the host hands in is playing, for the frame
   * pacer (it draws them at the full rate, as it does a happening): being
   * stroked, a fact's nod, the long answer's glow (awake) or the stretch as a
   * focus session ends (idle). `opts` as the host hands the pose; none under
   * still or a serious moment, which take them away. Every animal's are the
   * same length, so this is one function for all five.
   */
  function momentsBusy(state, opts) {
    const o = optsOf(opts, 0);
    if (o.still >= 0.99 || o.serious >= 0.99) return false;
    // (Worked out at clock 0, each moment's clock is minus its "seconds since".)
    const on = (at, len) => -at > 0 && -at < len;
    if (AWAKE[state] && ((o.pet > 0 && o.petting > 0)
        || (o.acks > 0 && (on(o.nodAt, ACK_S) || on(o.glowAt, GLOW_S))))) return true;
    return state === "idle" && o.focusBuddy > 0 && on(o.focusEndAt, FOCUS_END_S);
  }
  /**
   * Whether a cute moment is playing, for the frame pacer: only when the
   * host passes how long the animal has been idle (`since`) and its opts,
   * so a host that passes neither is told exactly what it was before.
   */
  function cuteBusy(t, since, opts, salt, lens) {
    if (typeof since !== "number") return false;
    return cuteAt(t, since, salt, lens)[0] >= 0 && cuteOf(optsOf(opts, t)) > 0;
  }

  /**
   * The pose for ONE state at clock `t`. `amp` is the microphone while
   * listening and Jarvis's own voice while speaking (0..1, already smoothed
   * by the shell). `look` is {x, y, w}: the pointer, -1..1 from the centre,
   * and how much to follow it (0 when there is no pointer). `since` is how
   * long this state has been showing (for a state that needs a wind-up -
   * none does at the moment); leave it out and the state is taken as long
   * settled. `o` is optsOf(): calm, serious and still.
   *
   * The loudness does NOT move the head or the body: it rises and falls
   * with every syllable, four times a second, and a head that followed it
   * would bob like a toy. It lights the orb and the eyebrows and lifts the
   * ears a little; the body moves in phrase-sized gestures instead (see
   * "speaking").
   */
  function stateTargets(state, t, amp, look, since, o) {
    if (typeof since !== "number") since = 1e9;
    o = optsOf(o, t);
    const m = mods(o);
    // Idle: a focus session takes the happenings away, and so does a cute
    // moment while it plays (m[0] is what tailAt's flick reads too).
    const cu = state === "idle" ? cuteAt(t, since, S_CUTE, CUTE_LEN) : NONE;
    const cw = cu[0] >= 0 ? cuteOf(o) : 0;
    const fw = state === "idle" ? focusOf(o) : 0;
    const fp = fw * (1 - 0.6 * o.calm);   // the focus pose itself: smaller under calm (the happenings still go by fw)
    // (and so do the stretch as a focus session ends, and being stroked)
    const fe = state === "idle" ? focusEndOf(t, o) : 0, pw = AWAKE[state] ? petOf(o) : 0;
    // The idle happening of this slot (one dice roll, read by the tail too),
    // and its weight: size, and thinned away when Jarvis is not being used.
    const evI = state === "idle" ? happeningV(t, 16, 0.5, 5.5, S_EVENT, 0.7, EVENTS, o.attention) : NONE4;
    m[0] *= (1 - fw) * (1 - cw * (cu[0] >= 0 ? cuteQuiet(cu[1], CUTE_LEN[cu[0]]) : 0)) * (1 - fe) * (1 - pw) * evI[3];
    const hap = m[0], sw = m[2], play = m[3];
    const P = {
      headYaw: 0, headPitch: 0, headRoll: 0, lean: 0, bob: 0, breath: 1,
      earL: 0.2, earR: 0.2, eyeL: 1, eyeR: 1, brow: 0, speak: 0, lookX: 0, lookY: 0,
      pawLx: LAP.pawL[0], pawLy: LAP.pawL[1], pawLz: LAP.pawL[2],
      pawRx: LAP.pawR[0], pawRy: LAP.pawR[1], pawRz: LAP.pawR[2],
      tailSwing: 0, tailCurl: 0.75,
      orbX: LAP.orb[0], orbY: LAP.orb[1], orbZ: LAP.orb[2], orbR: LAP.orb[3], orbGlow: 0.55,
      bodyRoll: 0, earTwL: 0, earTwR: 0, tail2: 0, tail3: 0, tail4: 0, tail5: 0,
      asleep: state === "standby" ? 1 : 0,
      lid: 0, lidSlope: 0,
    };
    // 256 cycles a loop is one breath every 4 seconds.
    let breathK = 256, breathDepth = 1, blinkSlow = 1, blinks = true, turnBlink = 0;
    let eyeK = 1, deepBreath = 0, scratch = 0, lift = 0, ackK = 1, hug = 0;

    if (state === "listening") {
      // Ears up and forward, head tilted about 15 degrees - the dog-hearing-
      // its-name tilt - leaning in. The eyes stay on you, with only small
      // glances; the ears lift a little with your voice. (Serious: no tilt,
      // eyes their usual size.)
      const g = looks(t, S_GAZE, 2, 7, 0.8, 0.2, 0.1, 0, 0.05, 1.1, o);
      P.headRoll = play * 0.26 + sw * 0.025 * wave(t, 205, 0);
      P.headPitch = 0.06;
      P.headYaw = 0.1 * g[2];
      P.lean = 0.10;
      P.earL = 1 + 0.12 * amp + sw * 0.04 * wave(t, 170, 0);
      P.earR = 1 + 0.12 * amp + sw * 0.04 * wave(t, 170, 1.9);
      P.eyeL = P.eyeR = 1 + 0.12 * play;
      P.brow = 0.3 + 0.4 * play;
      P.lookX = g[0] - 0.4 * g[2]; P.lookY = 0.1 + g[1] - 0.4 * g[3];
      P.orbGlow = 0.55 + 0.5 * amp;
      // Now and then (variety): it tilts its head the other way, leans in a
      // little closer, or turns an ear.
      const v = variant(t, o, S_LISTEN, 0.4);
      if (v[0] === 0) P.headRoll -= 0.39 * play * v[1];
      else if (v[0] === 1) { P.lean += 0.04 * v[1]; P.eyeL += 0.05 * v[1]; P.eyeR += 0.05 * v[1]; }
      else if (v[0] === 2) P.earTwR += 0.3 * v[1];
      // A small nod in your pauses.
      const nd = listenNod(t, o, S_NOD);
      P.headPitch += nd[0]; P.headRoll += play * nd[1]; eyeK *= 1 - nd[2];
      P.earL += 0.3 * nd[3]; P.earR += 0.3 * nd[3];
      turnBlink = g[4];
    } else if (state === "thinking") {
      // Holds the orb up in both paws and gazes into it - glancing up and
      // away now and then, the way people do while they think.
      const bob = sw * 0.02 * wave(t, 359, 0);
      const g = looks(t, S_GAZE, 1.8, 6, 0.55, 0.7, 0.2, 0.75, 0.05, 1.1, o);
      P.orbX = 0; P.orbY = 0.58 + bob; P.orbZ = -0.56; P.orbR = 0.125;
      P.pawLx = -0.12; P.pawLy = 0.50 + bob; P.pawLz = -0.52;
      P.pawRx = 0.12; P.pawRy = 0.50 + bob; P.pawRz = -0.52;
      P.headPitch = -0.34 + sw * 0.03 * wave(t, 147, 0) + 0.22 * g[3];
      P.headYaw = 0.15 * g[2];
      P.headRoll = sw * 0.08 * wave(t, 98, 0);
      P.lookX = g[0] - 0.4 * g[2];
      P.lookY = -0.7 + g[1] - 0.4 * g[3];
      P.earL = P.earR = 0.05;
      P.brow = 0.25;
      P.lean = 0.06;
      P.orbGlow = 0.95 + 0.2 * wave(t, 424, 0);
      // Now and then (variety): it turns the orb in its paws, brings it
      // closer and peers in, or tilts its head, thinking.
      const v = variant(t, o, S_THINK, 0.5);
      if (v[0] === 0) {
        const r = 0.03 * v[1] * wave(t, 300, 0);
        P.pawLy += r; P.pawRy -= r; P.pawLz -= 0.6 * r; P.pawRz += 0.6 * r;
      } else if (v[0] === 1) {
        P.orbY += 0.04 * v[1]; P.orbZ -= 0.03 * v[1];
        P.pawLy += 0.04 * v[1]; P.pawRy += 0.04 * v[1]; P.pawLz -= 0.03 * v[1]; P.pawRz -= 0.03 * v[1];
        P.headPitch -= 0.05 * v[1]; eyeK *= 1 - 0.15 * v[1];
      } else if (v[0] === 2) { P.headRoll += 0.12 * play * v[1]; P.brow += 0.1 * v[1]; }
      turnBlink = g[4];
    } else if (state === "speaking") {
      // Leans in and talks with its eyes, its head and one paw - in PHRASES:
      // at most one gesture every two seconds (a nod, a paw lifted and
      // dropped, a tilt), often none, never the same one twice running, and
      // never just as its eyes move to look somewhere (see beat()). The eyes
      // lead each look; the head follows only a little. The mouth itself
      // follows the mouth track of the words actually being heard
      // (uniforms' `mouth`); `speak` only says how much of it to show - 1
      // here, 0 in every other state, settling between them.
      const g = looks(t, S_GAZE, 1.8, 6, 0.65, 0.5, 0.18, 0, 0.06, 1.1, o);
      // (With the host's phrase ends, the gestures land on them instead.)
      const b = o.phraseN >= 0 ? phraseBeat(t, o, S_PHRASE, S_GAZE, 1.8, 6, 0.65) : beat(t, S_BEAT, S_GAZE, 1.8, 6, 0.65);
      const x = b[1];
      // A fact's nod waits while a gesture plays, so two never stack up.
      ackK = b[0] >= 0 ? 1 - bump(clamp(x / 1.6, 0, 1)) : 1;
      P.speak = 1;
      P.lean = 0.05;
      P.headPitch = 0.03;
      P.headYaw = sw * 0.05 * noise(t, N_YAW, 4) + 0.08 * g[2];
      P.headRoll = sw * 0.035 * noise(t, N_ROLL, 4);
      P.lookX = g[0] - 0.16 * g[2]; P.lookY = g[1] - 0.16 * g[3];
      P.brow = 0.3 + 0.1 * amp;
      P.earL = P.earR = 0.45;
      P.orbGlow = 0.6 + 0.45 * amp;
      if (b[0] === 0) {
        // A nod on the stressed word: down, and back a little past level.
        P.headPitch -= hap * 0.06 * (bump(x / 0.7) - 0.3 * bump((x - 0.55) / 0.7));
        P.brow += hap * 0.25 * bump(x / 0.7);
      } else if (b[0] === 1) {
        // The paw comes up off the orb, holds a moment, and goes back.
        const e = hap * envAHR(x, 0.4, 0.3, 0.6);
        P.pawRx += 0.10 * e; P.pawRy += 0.16 * e; P.pawRz -= 0.06 * e;
        P.headPitch -= hap * 0.025 * bump(x / 0.9);
      } else if (b[0] === 2) {
        P.headRoll += hap * play * 0.06 * bump(x / 1.2);
        P.brow += hap * 0.15 * bump(x / 1.2);
      }
      turnBlink = g[4];
    } else if (state === "approval") {
      // Waiting on you - and the question may be a serious one (sending an
      // email, say), so no wave and nothing cute (the owner's call,
      // 2026-09-28): it sits up, leans in and looks straight at you, ears
      // up, holding its orb up higher. Then it is still - only its breathing
      // moves, a slow blink now and then, and its eyes' tiny darts, so it
      // reads as alive and attentive rather than frozen.
      const g = restingGaze(t, S_GAZE);
      P.lean = 0.10;
      P.headPitch = 0.04;
      P.eyeL = P.eyeR = 1 + 0.12 * play;
      P.brow = 0.45;
      P.earL = P.earR = 1.0;
      P.tailCurl = 0.8;
      P.pawLy += 0.10; P.pawRy += 0.10; P.orbY += 0.10;
      P.lookX = g[0]; P.lookY = g[1];
      P.orbGlow = 0.9;
      lift = 0.015; blinkSlow = 1.4;
      // The small reaction as it arrives (variety), then still.
      const ar = arrivalOf(state, o, since);
      P.headPitch += ar[0]; P.headRoll += play * ar[1]; P.lean += ar[2]; eyeK *= 1 - ar[3];
      P.earL += 0.3 * ar[4]; P.earR += 0.3 * ar[4];
    } else if (state === "standby") {
      // Asleep: eyes shut, head drooped, ears down, the tail wrapped round,
      // breathing slow and deep. Once in a while a sigh - one deeper breath
      // and the head settling a little lower. Nothing else moves.
      const e = happening(t, 16, 0.5, 5.5, S_EVENT, 0.35, 1);
      const sigh = e[0] === 0 ? bump(e[1] / 4.5) : 0;
      P.eyeL = P.eyeR = 0;
      P.headPitch = -0.40 - 0.035 * sigh;
      P.headRoll = 0.22 * play;
      P.lean = 0.06;
      P.earL = P.earR = -0.7;
      P.tailCurl = 1;
      P.orbGlow = 0.15;
      deepBreath = sigh;
      // 171 cycles a loop: a breath every 6 seconds.
      breathK = 171; breathDepth = 1.8; blinks = false;
    } else if (state === "error") {
      // Something went wrong: a still, concerned look - head tipped a
      // little and lowered, eyes down, brows drawn, ears back a touch.
      // Nothing comic (it used to scratch its head; the owner's call,
      // 2026-09-28). Only its breathing moves, and its eyes' tiny darts.
      const g = restingGaze(t, S_GAZE);
      P.headRoll = -0.12 * play;
      P.headPitch = -0.08;
      P.earL = P.earR = -0.15;
      P.eyeL = P.eyeR = 0.8;
      P.brow = -0.25;
      P.lookX = g[0]; P.lookY = -0.3 + g[1];
      P.orbGlow = 0.35;
      blinkSlow = 1.4;
      const ar = arrivalOf(state, o, since);
      P.headPitch += ar[0]; P.headRoll += play * ar[1]; P.lean += ar[2]; eyeK *= 1 - ar[3];
      P.earL += 0.3 * ar[4]; P.earR += 0.3 * ar[4];
    } else if (state === "banked") {
      // Things are waiting, but it is keeping them to itself: dozing,
      // half-lidded, blinking slowly - and now and then nodding off, its
      // head sinking over three seconds before it catches itself.
      const e = happening(t, 16, 0.5, 5.5, S_EVENT, 0.55, 1);
      const x = e[1];
      const droop = e[0] === 0 ? (x < 3.2 ? smooth(clamp(x / 3.2, 0, 1)) : 1 - smooth(clamp((x - 3.2) / 0.8, 0, 1))) : 0;
      P.eyeL = P.eyeR = 0.35 * (1 - 0.7 * droop);
      P.headPitch = -0.15 - 0.12 * droop;
      P.earL = P.earR = -0.2 - 0.2 * droop;
      P.lookY = -0.2;
      P.orbGlow = 0.25;
      P.tailCurl = 0.9;
      // 205 cycles a loop: a breath every 5 seconds.
      breathK = 205; blinkSlow = 2.5;
    } else {
      // idle: sits with its orb in its lap. It looks at something, holds,
      // looks at something else - the eyes first, the head after; its
      // weight shifts every few seconds; its tail swishes slowly, the swing
      // running out to the tip. Every 10 to 30 seconds it does one small
      // thing - most often a flick of the tail or an ear turning to a sound
      // before the head does; now and then a stretch or a scratch.
      const g = looks(t, S_GAZE, 1.5, 6, 0.35, 0.8, 0.25, 0, 0.08, 1.1, o);
      const gLag = looks(t - 0.3, S_GAZE, 1.5, 6, 0.35, 0.8, 0.25, 0, 0.08, 1.1, o);
      const ev = evI;
      const x = ev[1];
      const roll = sw * 0.025 * shift(t, S_ROLL);
      let ex = g[0], ey = g[1], hx = g[2], hy = g[3];
      if (ev[0] >= 3) {
        // It hears something to one side: that ear turns first, then the
        // head and eyes turn that way together; it listens, and comes back.
        // (The eyes glide with the head here rather than jumping, so this
        // never lands a second jump right after one of the glances.)
        const s = ev[0] === 3 ? -1 : 1;
        const ear = hap * 0.35 * envAHR(x, 0.25, 2.4, 0.8);
        if (s < 0) P.earTwL += ear; else P.earTwR += ear;
        const wh = hap * envAHR(x - 0.4, 0.9, 1.4, 0.9);
        ex += (s * 0.9 - ex) * wh; ey += (0.1 - ey) * wh;
        hx += (s * 0.75 - hx) * wh; hy += (0.1 - hy) * wh;
      }
      P.bodyRoll = roll;
      P.lean = sw * 0.012 * shift(t, S_LEAN);
      P.headYaw = 0.25 * hx;
      P.headPitch = 0.10 * hy + sw * 0.02 * wave(t, 97, 1.1);
      P.headRoll = -0.5 * roll + sw * 0.035 * wave(t, 83, 0.2);
      P.lookX = ex - 0.4 * hx; P.lookY = ey - 0.4 * hy;
      // Follow-through: when the head turns, the ears lag and swing after.
      const lag = clamp(g[2] - gLag[2], -1, 1);
      P.earTwL -= 0.2 * lag; P.earTwR -= 0.2 * lag;
      P.earL = 0.2 + sw * 0.05 * wave(t, 131, 0);
      P.earR = 0.2 + sw * 0.05 * wave(t, 131, 2.3);
      P.tailCurl = 0.75 + sw * 0.04 * wave(t, 59, 0.3);
      P.pawLy += sw * 0.006 * wave(t, 113, 0); P.pawRy += sw * 0.006 * wave(t, 113, 2.1);
      if (ev[0] === 0) {
        // A stretch: leans well back, lifts its chin a little, squints,
        // ears back, paws out to the sides, one deep breath - and settles.
        // (Leaning back more than it looks up, so it reads as a stretch and
        // not as something above it catching its eye.)
        const e = hap * envAHR(x, 1.0, 0.7, 1.7);
        P.lean -= 0.05 * e; P.headPitch += 0.10 * e; eyeK = 1 - 0.55 * e;
        P.pawLx -= 0.06 * e; P.pawRx += 0.06 * e; P.pawLy += 0.03 * e; P.pawRy += 0.03 * e;
        P.earL -= 0.35 * e; P.earR -= 0.35 * e; P.tailCurl -= 0.12 * e;
        deepBreath = e;
      } else if (ev[0] === 1) {
        // The flick itself is in tailAt(); the tail uncurls a little with it.
        P.tailCurl -= hap * 0.12 * bump(x / 1.5);
      } else if (ev[0] === 2) {
        // A scratch at the side of its head (placed below, once the head
        // has turned), tipping its head into it with its eyes half shut.
        scratch = hap * envAHR(x, 0.6, 1.6, 0.7);
        P.headRoll += 0.10 * scratch;
        eyeK = 1 - 0.45 * scratch;
      }
      turnBlink = g[4];
      if (fw > 0) {
        // Working beside you (a focus session): it settles to gaze into the
        // orb in its lap, head a little down, looking up now and then - far
        // fewer looks, and no happenings (hap, above).
        const f = gaze(t, S_FOCUS, 4, 12, 0.75, 0.3, 0.12, 0, 0.03, 1.6);
        P.lookX += (f[0] - 0.4 * f[2] - P.lookX) * fp;
        P.lookY += (-0.6 + f[1] - 0.4 * f[3] - P.lookY) * fp;
        P.headYaw += (0.2 * f[2] - P.headYaw) * fp;
        P.headPitch += (-0.16 + 0.1 * f[3] - P.headPitch) * fp;
        P.lean += 0.02 * fp;
        turnBlink *= 1 - fp;
      }
      // The small stretch as a focus session ends (the idle stretch's).
      if (fe > 0) {
        P.lean -= 0.05 * fe; P.headPitch += 0.10 * fe; eyeK *= 1 - 0.55 * fe;
        P.pawLx -= 0.06 * fe; P.pawRx += 0.06 * fe; P.pawLy += 0.03 * fe; P.pawRy += 0.03 * fe;
        P.earL -= 0.35 * fe; P.earR -= 0.35 * fe; P.tailCurl -= 0.12 * fe;
        deepBreath = Math.max(deepBreath, fe);
      }
      if (cw > 0 && cu[0] === 0) {
        // Cute moment: it hugs its tail. The tail curls round across its
        // front (the orb moved aside in its lap), both paws hold it, its head
        // tips down onto it, eyes half shut and content, nuzzling a little.
        hug = cw * envAHR(cu[1], 1.4, 4.0, 1.6);
        P.tailCurl += (1 - P.tailCurl) * hug;
        P.orbX += (-0.17 - P.orbX) * hug; P.orbZ += (-0.40 - P.orbZ) * hug;
        P.pawRx += (0.30 - P.pawRx) * hug; P.pawRy += (0.38 - P.pawRy) * hug; P.pawRz += (-0.53 - P.pawRz) * hug;
        P.pawLx += (0.08 - P.pawLx) * hug; P.pawLy += (0.45 - P.pawLy) * hug; P.pawLz += (-0.53 - P.pawLz) * hug;
        P.lookX += (0.3 - P.lookX) * hug; P.lookY += (-0.55 - P.lookY) * hug;
        P.headYaw += (0.14 - P.headYaw) * hug;
        P.headPitch += (-0.14 - P.headPitch) * hug;
        P.headRoll += hug * play * (0.14 + 0.03 * wave(t, 205, 0));
        P.brow += 0.15 * hug; eyeK *= 1 - 0.55 * hug;
        turnBlink *= 1 - hug;
      } else if (cw > 0 && cu[0] === 1) {
        // Cute moment: it plays with its orb - tosses it up a little from
        // its paws, watching it, catches it, and a smaller toss again.
        const e = cw * envAHR(cu[1], 0.6, 3.6, 0.8);
        const h = cw * 0.2 * (bump((cu[1] - 0.9) / 1.0) + 0.6 * bump((cu[1] - 2.3) / 0.9));
        P.orbY += 0.06 * e + h; P.orbZ -= 0.04 * e;
        P.pawLy += 0.06 * e + 0.35 * h; P.pawRy += 0.06 * e + 0.35 * h;
        P.pawLz -= 0.04 * e; P.pawRz -= 0.04 * e;
        P.pawLx += 0.03 * e; P.pawRx -= 0.03 * e;
        P.lookX += (0 - P.lookX) * e; P.lookY += (-0.2 + 3.5 * h - P.lookY) * e;
        P.headYaw += (0 - P.headYaw) * e;
        P.headPitch += (-0.05 + 0.5 * h - P.headPitch) * e;
        P.brow += 0.2 * e;
        turnBlink *= 1 - e;
      }
    }

    // Stroked (petting): it leans into your hand, eyes soft and half shut,
    // ears back happily - and follows the stroke a little.
    if (pw > 0) {
      P.headRoll += pw * play * (0.10 * o.petX + 0.03 * o.petDir);
      P.headPitch += 0.04 * pw;
      P.bodyRoll += 0.02 * pw * o.petX;
      P.earL -= 0.25 * pw; P.earR -= 0.25 * pw;
      P.brow += 0.15 * pw;
      eyeK *= 1 - 0.45 * pw;
    }
    // A fact saved: one small nod, ears flicking. A long answer ready: the
    // orb swells once.
    const an = AWAKE[state] ? ackNodOf(t, o) : ZERO2;
    P.headPitch += ackK * an[0];
    P.earL += 0.4 * ackK * an[1]; P.earR += 0.4 * ackK * an[1];
    const gl = AWAKE[state] ? ackGlowOf(t, o) : 0;
    P.orbGlow += 0.4 * gl; P.orbR *= 1 + 0.2 * gl;

    P.tailSwing = tailAt(state, t, m);
    P.tail2 = tailAt(state, t - TAIL_LAG, m);
    P.tail3 = tailAt(state, t - 2 * TAIL_LAG, m);
    P.tail4 = tailAt(state, t - 3 * TAIL_LAG, m);
    P.tail5 = tailAt(state, t - 4 * TAIL_LAG, m);
    if (hug > 0) {
      // (Hugged, the tail keeps still, swung round across its front.)
      const sw0 = -0.45 * hug;
      P.tailSwing += (sw0 - P.tailSwing) * hug; P.tail2 += (sw0 - P.tail2) * hug; P.tail3 += (sw0 - P.tail3) * hug;
      P.tail4 += (sw0 - P.tail4) * hug; P.tail5 += (sw0 - P.tail5) * hug;
    }

    // Breathing: the chest swells and the whole body rises a little.
    const b = breathWave(t, breathK, N_BREATH) * (1 + 0.6 * deepBreath);
    P.breath = 1 + 0.018 * breathDepth * b;
    P.bob = 0.007 * breathDepth * b + lift;

    // Following the pointer: mostly with the eyes. Asleep, it does not.
    const w = state === "standby" ? 0 : clamp(look.w || 0, 0, 1);
    if (w > 0) {
      const lx = clamp(look.x || 0, -1, 1), ly = clamp(look.y || 0, -1, 1);
      P.lookX += (lx - P.lookX) * w;
      P.lookY += (ly - P.lookY) * w;
      P.headYaw += m[1] * 0.2 * lx * w;
      P.headPitch += m[1] * 0.2 * ly * w;
    }

    if (scratch > 0) {
      // The paw goes to a spot just outside the side of the head, wherever
      // the head has turned to, and scratches up and down twice a second.
      // On the way there and back it swings out round the cheek (an arc,
      // not a straight line through the face).
      const q = onHead(P, 0.58, 0.30 + 0.03 * wave(t, 2048, 0), -0.10);
      const arc = 4 * scratch * (1 - scratch);
      P.pawRx += (q[0] - P.pawRx) * scratch + 0.10 * arc;
      P.pawRy += (q[1] - P.pawRy) * scratch;
      P.pawRz += (q[2] - P.pawRz) * scratch - 0.10 * arc;
    }

    farewell(P, state, o);

    lidSet(P, state);
    const q = 1 - (o.quiet || 0);
    const k = eyeK * (1 - q * Math.max(blinks ? blinkAt(t, S_BLINK, blinkSlow, 2, 10) : 0, turnBlink));
    P.eyeL *= k; P.eyeR *= k;
    return P;
  }

  /* ------------------------------------------------------------------ *
   * The painted eyelids (owner, 2026-09-29): a lid of the surrounding fur
   * laid over the top of each eye by the shader (uLid, in the surface
   * colouring; docs/CRITTERS.md "Painted eyelids"). The four animals share
   * these amounts; the robot has no lids.
   *
   * A lid is a SETTLED LOOK, not a movement: it is a number the state sets
   * and the pose's ordinary settling eases in and out, so it never pops and
   * adds no idle motion. Idle, listening, thinking and speaking have none.
   * The ordinary blink still shuts the eye all the way (the eye's own
   * squash), lid or no lid: the lid only ever covers the top of an eye, so
   * the two cannot fight.
   *   - waiting on you: a level, attentive lid;
   *   - something went wrong: a lid sloped worried (inner end up);
   *   - dozing and asleep: a heavy, level lid.
   * A crisis-help moment (`serious`) takes them all away, applied where the
   * pose is finished (makePose), so a lid fades with the host's eased weight.
   * Still and calm change nothing about them: at an approval or an error the
   * lid is the plain look the owner asked for.
   * ------------------------------------------------------------------ */
  /** [how far down 0..1, slope -1..1 (+1: inner end up, worried)] by state. */
  const LID = { approval: [0.2, 0], error: [0.42, 1], banked: [0.55, 0], standby: [0.55, 0] };
  /** The heavy lid of sleep (also what a wake-up lifts, and a nodding off lowers). */
  const LID_SLEEP = 0.55;
  function lidSet(P, state) {
    const l = LID[state] || ZERO2;
    P.lid = l[0]; P.lidSlope = l[1];
  }
  /** Nodding off: from the lid the old state had (F) to the sleeping one, as the eyes close (close 0..1). */
  function lidNod(P, F, close) {
    P.lid = toward(F.lid, P.lid, close);
    P.lidSlope = toward(F.lidSlope, P.lidSlope, close);
  }
  /** Waking, x seconds in: the sleeping lid lifts a little after the eyes open (from 0.25 s, done by 1.15 s). */
  function lidUp(x) { return ease((x - 0.25) / 0.9); }
  /** A crisis-help moment (`serious`, a weight the host eases) leaves the animal neutral: no lid. Poses without lids pass through. */
  function lidCalm(P, o) {
    if (P.lid !== undefined) { const w = 1 - o.serious; P.lid *= w; P.lidSlope *= w; }
    return P;
  }
  /** Waking (k: how asleep it was, 1 fully): from the sleeping lid to the state's own. */
  function lidWake(P, x, k) {
    const s = k * (1 - lidUp(x));
    P.lid = toward(P.lid, LID_SLEEP, s);
    P.lidSlope = toward(P.lidSlope, 0, s);
  }

  /**
   * Hello and goodbye, when the owner switches faces (owner, 2026-09-28):
   * the HOST plays them, handing over how far each has got - `o.goodbye`
   * 0..1 on the face that is leaving, then `o.hello` 0..1 on the one coming
   * in (about HELLO_S and GOODBYE_S seconds each). Left out: none. Every
   * animal's is built the same way (see the owl's, the otter's and the
   * monkey's):
   *  - Goodbye: a little wave (nothing while asleep or dozing), looking at
   *    you, then out of view - the panda ducks down below the picture.
   *  - Hello: it comes back up into view, a small bounce past its place,
   *    and looks at you.
   * Under still, calm or a serious moment - and while waiting on you or
   * after something went wrong, which the owner's rules treat as serious
   * moments too (switchE) - the pose plays none of it and the host
   * cross-fades the faces instead: switchAlpha() says how much.
   */
  const HELLO_S = 1.0, GOODBYE_S = 1.0;
  const DROP = 2.1;   // how far down it goes to be out of view, ear tips and all
  // Waiting on you and something wrong: attentive and still, so a face
  // switch there is the quick gentle cross-fade, as under a serious moment.
  const STILL_SWITCH = { approval: 1, error: 1 };
  /** How much of its own hello and goodbye an animal plays: the extras, none while waiting on you or at an error. */
  function switchE(o, state) { return STILL_SWITCH[state] ? 0 : extras(o); }
  function farewell(P, state, o) {
    const g = o.goodbye, h = o.hello;
    if (g <= 0 && h >= 1) return;
    const E = switchE(o, state);
    const awake = AWAKE[state] ? 1 : 0;
    if (g > 0) {
      const a = E * bump(clamp(g / 0.6, 0, 1));
      const at = E * awake * ease(g / 0.2);
      P.lookX += (0 - P.lookX) * at; P.lookY += (0 - P.lookY) * at;
      P.headYaw += (0 - P.headYaw) * at;
      // The wave: its right paw up by its shoulder, waving side to side
      // about one and a half times a second (by how far the goodbye has got).
      const wv = a * awake;
      P.pawRx += 0.12 * wv + 0.06 * wv * Math.sin(TAU * 1.6 * g);
      P.pawRy += 0.36 * wv; P.pawRz -= 0.08 * wv;
      P.brow += 0.2 * wv;
      P.bob -= E * DROP * ease((g - 0.4) / 0.6);
    }
    if (h < 1) {
      P.bob -= E * DROP * (1 - ease(h / 0.45));
      P.bob += E * 0.045 * bump((h - 0.3) / 0.45);
      const at = E * awake * ease((h - 0.25) / 0.25) * (1 - ease((h - 0.8) / 0.2));
      P.lookX += (0 - P.lookX) * at; P.lookY += (0 - P.lookY) * at;
      P.headYaw += (0 - P.headYaw) * at; P.headPitch += (0.04 - P.headPitch) * at;
      P.brow += 0.2 * at;
    }
  }
  /**
   * How opaque the host draws an animal while it says hello or goodbye:
   * 1 while the pose plays the piece itself; under still, calm or a serious
   * moment, or while waiting on you or at an error (when it does not), the
   * host cross-fades instead - the leaving face fading out as its goodbye
   * goes 0 to 1, the new one in with its hello. `opts` is what the host
   * hands the pose; `state` the state it is drawn in (left out: no state
   * counts as serious, as before). A state that changes part way through a
   * switch changes this at once - rare, since a switch lasts a second.
   */
  function switchAlpha(opts, state) {
    const o = optsOf(opts, 0), E = switchE(o, state);
    return clamp(1 - (1 - E) * Math.max(o.goodbye, 1 - o.hello), 0, 1);
  }

  /* ------------------------------------------------------------------ *
   * Waking up and falling asleep (the owner, 2026-09-28: "If I wake up the
   * animal models from sleep, do they have a short wake up animation? If
   * not add one" - and then the same for nodding off).
   *
   * Each animal plays a short, calm piece when Jarvis leaves standby (about
   * two seconds) and when it goes to standby (about three) - by the
   * schedule, by hand, or (leaving) when the link comes back after "not
   * connected", which shows standby too. What each animal does is in its
   * own `wakeSleep` (the panda's is below). The rules every one keeps:
   *
   *  - The mouth never moves: it follows Jarvis's real voice and nothing
   *    else, so there is no yawn.
   *  - Waking straight into "waiting on you", "something went wrong" or a
   *    doze, only the eyes open, gently: those looks stay still.
   *  - Under calm, serious or still (weighted: `E` in wakeSleep), only the eyes
   *    open, or close, slowly.
   *  - While it wakes, its idle happenings, talking gestures and ordinary
   *    blinks wait (the `quiet` weight, see optsOf), so nothing doubles up;
   *    speaking straight away is fine - the mouth is untouched, only the
   *    gestures wait.
   *  - A quick flip (awake, asleep, awake inside a second) never snaps: each
   *    piece is scaled by how far the one before it got (`k`), and the
   *    settling (makePose) carries on from what was on screen as always.
   *  - The Zs fade out as it wakes, and only rise once it is asleep - near
   *    the end of nodding off, not at its start (zsOf).
   *
   * Like everything here it is a pure function of the state, the list of
   * past changes and the clock - no randomness, nothing remembered.
   * ------------------------------------------------------------------ */
  const WAKE_S = 2.2, SLEEP_S = 3.0;
  /**
   * The last change between asleep (standby) and awake (anything else), seen
   * from `since` seconds into `state`, whose own change is past[i]: [seconds
   * since that change, its index in past] - or null when there is none (or,
   * with `cut`, when it is long enough ago that the piece it started has
   * finished). Changes between two awake states in between (woken into
   * listening, then thinking) do not restart it.
   */
  function crossing(state, past, i, since, cut) {
    const asleep = state === "standby", len = asleep ? SLEEP_S : WAKE_S;
    let x = since;
    for (let j = i; j < HIST_MAX && j < past.length; j++) {
      if (cut && x >= len) return null;
      const pv = past[j];
      if (!pv || !pv.state) return null;
      if ((pv.state === "standby") !== asleep) return [x, j];
      x += pv.gap;
    }
    return null;
  }
  /**
   * How asleep it is, 0 (awake) to 1: rises over SLEEP_S as it nods off and
   * falls over WAKE_S as it wakes, each time carrying on from wherever the
   * change before left it (so a quick flip back and forth never jumps).
   */
  function depth(state, past, i, since) {
    const to = state === "standby" ? 1 : 0;
    const c = crossing(state, past, i, since, true);
    if (!c) return to;
    const pv = past[c[1]];
    const d0 = depth(pv.state, past, c[1] + 1, pv.gap);
    return d0 + (to - d0) * ease(c[0] / (to ? SLEEP_S : WAKE_S));
  }
  /** How much of the Zs to show for a depth: none until it is nearly asleep. */
  function zsOf(d) { return smooth(clamp((d - 0.8) / 0.2, 0, 1)); }
  /** The wake-up's `quiet` weight, x seconds in: all of it, then easing off by WAKE_S. */
  function quietOf(x) { return 1 - smooth(clamp((x - 1.5) / (WAKE_S - 1.5), 0, 1)); }
  /** How much of the extras (a stretch, a fluff, a rub) the options leave. */
  function extras(o) { return (1 - o.still) * (1 - o.calm) * (1 - o.serious); }
  function withQuiet(o, q) { return Object.assign({}, o, { quiet: q }); }
  /** a, moved toward b by w (0..1). */
  function toward(a, b, w) { return a + (b - a) * w; }
  // Waking into these, only the eyes open: the looks stay still.
  const PLAIN = { approval: 1, error: 1, banked: 1 };
  /** The plain wake-up's eyes, 0 shut .. 1 open, x seconds in: open over 0.1 to 0.7 s. */
  function eyesOpen(x) { return ease((x - 0.1) / 0.6); }
  /** The plain nodding-off's eyes: close slowly over 1.8 s. */
  function eyesClose(x) { return 1 - ease(x / 1.8); }

  /**
   * The panda's waking up and nodding off, on top of the state's own pose P.
   * `x`: seconds since the change; `k`: how far the change before it had got
   * (1: fully asleep when it woke, fully awake when it nodded off); `E`: how
   * much of the extras the options and the state allow (the extras play at
   * E times k); `F`: nodding off only - the pose of the state it was in, at the
   * change, which it holds a while before letting go.
   */
  function wakeSleep(P, state, x, k, E, t, F) {
    const e = E * k;
    if (state === "standby") {
      // Nodding off: heavy eyes and a slow blink; a nod as it drifts, it
      // catches itself (eyes open a little, ears up), another heavy blink -
      // then its head goes down for good and its tail curls round.
      const lids = (1 - 0.45 * ease(x / 0.6) - 0.30 * ease((x - 0.95) / 0.6) + 0.25 * ease((x - 1.55) / 0.3)
        - 0.50 * ease((x - 2.1) / 0.5)) * (1 - bump((x - 0.55) / 0.45)) * (1 - bump((x - 1.85) / 0.35));
      const lid = k * toward(eyesClose(x), lids, E);
      P.eyeL = F.eyeL * lid; P.eyeR = F.eyeR * lid;
      // The painted lid comes down with the eyes' drooping - not with the two
      // quick blinks laid on it (the eye's own squash does those).
      const droop = 1 - 0.45 * ease(x / 0.6) - 0.30 * ease((x - 0.95) / 0.6) + 0.25 * ease((x - 1.55) / 0.3)
        - 0.50 * ease((x - 2.1) / 0.5);
      lidNod(P, F, 1 - k * toward(eyesClose(x), droop, E));
      // How far down the head has gone: sags, nods, catches, and drops.
      const down = 0.2 * ease(x / 0.9) + 0.35 * ease((x - 0.95) / 0.6) - 0.2 * ease((x - 1.55) / 0.45)
        + 0.65 * ease((x - 2.0) / 1.0);
      const up = e * (1 - down);
      P.headPitch = toward(P.headPitch, F.headPitch, up);
      P.headRoll = toward(P.headRoll, F.headRoll, up);
      P.earL = toward(P.earL, F.earL, up) + 0.25 * e * bump((x - 1.5) / 0.6);
      P.earR = toward(P.earR, F.earR, up) + 0.25 * e * bump((x - 1.5) / 0.6);
      P.tailCurl = toward(P.tailCurl, F.tailCurl, e * (1 - ease((x - 1.9) / 1.0)));
      return;
    }
    // Waking: its eyes open with a slow double blink; its head lifts a
    // little past and settles; a small stretch (leans back, paws up and
    // out, chin up, a deeper breath); its ears perk with a flick.
    const lids = eyesOpen(x) * (1 - E * bump((x - 0.75) / 0.45)) * (1 - 0.85 * E * bump((x - 1.25) / 0.4));
    const f = 1 - k * (1 - lids);
    P.eyeL *= f; P.eyeR *= f;
    lidWake(P, x, k);   // ...and lifts a little after they open
    P.headPitch += 0.05 * e * bump((x - 0.2) / 1.2);
    const s = e * envAHR(x - 0.55, 0.5, 0.35, 0.6);
    P.lean -= 0.05 * s; P.headPitch += 0.08 * s; P.breath += 0.012 * s;
    if (state !== "thinking") {
      // (Thinking holds the orb up in both paws: they stay on it.)
      P.pawLx -= 0.05 * s; P.pawRx += 0.05 * s; P.pawLy += 0.06 * s; P.pawRy += 0.06 * s;
    }
    const flick = e * (bump((x - 0.95) / 0.5) - 0.3 * bump((x - 1.35) / 0.5));
    P.earL += 0.45 * flick; P.earR += 0.45 * flick;
  }

  /**
   * Makes an animal's pose() from its stateTargets(), the names of its pose
   * numbers, and each number's half-life ({name: [half-life, bouncy, cut,
   * own]}; a name left out takes HL_BODY; `cut` makes it an angle that
   * settles round the circle without passing through the angle `cut`;
   * `own` is not slowed while falling asleep or waking). Every animal settles into a new state the
   * same way, so the owl and the otter use this too.
   *
   * How a change of state settles: "inertialization", from Daniel Holden's
   * Spring-It-On (orangeduck/Spring-It-On, inertialization.c and common.h's
   * decay_spring_damper_exact, MIT). At the moment of the change the new
   * state's pose starts playing AT ONCE, plus an offset: the gap between it
   * and what was on screen, moving at the speed the screen was moving. The
   * offset then dies away like a critically damped spring - exactly, as a
   * formula of the time since the change, so nothing needs remembering
   * from frame to frame. The new state's own movement is never paused or
   * faded, nothing jumps, and nothing even changes speed suddenly. The
   * loose parts ("bouncy") use a slightly under-damped spring, so they
   * swing a few percent past and settle back.
   *
   * Falling asleep and waking are slower (slowBy()): nodding off takes
   * about two seconds, waking about one, and dozing off or rousing from a
   * doze about twice the usual time - an animal does not drop asleep in
   * half a second.
   *
   * What was on screen at the change is worked out again from `hist`:
   *   past   - the changes before this one, newest first: for each, the
   *            state that was LEFT, how long it had been showing (gap) and
   *            the loudness it was drawn with when it was left (amp). If
   *            the state being left was itself still settling in, what was
   *            on screen is THAT settling - and if the state before it was
   *            too, that one's, and so on: three or four changes inside a
   *            second or two all carry on smoothly. The walk stops at a
   *            state that had finished settling, or after HIST_MAX changes.
   *            A host keeps it by putting, at each change of state,
   *            {state: <the old state>, gap: now - changedAt, amp: <the
   *            loudness of the last frame>} on the front, and dropping
   *            entries older than about twenty seconds.
   * A host that keeps less may pass the older, shorter form instead:
   *   prevAmp - the loudness at the change;
   *   prev2, gap - the state before the previous one, and how long the
   *             previous state had been showing;
   *   prevAmp2 - the loudness at the change before that one.
   *
   * `opts` ({calm, serious, still}, see optsOf()) is handed to every state's
   * targets, the old ones included.
   *
   * `moves` (optional) is the animal's waking up and nodding off (see
   * "Waking up and falling asleep" above, and the panda's wakeSleep): laid
   * on each state's own pose for the first seconds after a change between
   * asleep and awake, inside the settling - so what was on screen at any
   * later change already includes it, and carries on from it. With it, the
   * pose's `asleep` (what the Zs fade with) comes from depth() rather than
   * settling like a body part.
   */
  const LN2 = 0.6931471805599453;
  const FD = 1 / 120;   // the step the screen's speed at the change is measured over
  const HIST_MAX = 6;   // the most changes a pose looks back through
  const S_ARRIVE = 255; // the dice for which reaction an arrival plays (every animal's)
  /** How much slower than usual a change from `prev` to `state` settles. */
  function slowBy(state, prev) {
    if (state === "standby") return 5;       // nodding off
    if (prev === "standby") return 2.5;      // waking
    if (state === "banked" || prev === "banked") return 2;
    return 1;
  }
  /** The changes before this one, newest first, from either form of `hist`. */
  function pastOf(prevState, hist, amp) {
    if (Array.isArray(hist.past)) return hist.past;
    const num = (v, d) => (typeof v === "number" ? v : d);
    if (!prevState) return [];
    const past = [{ state: prevState, gap: num(hist.gap, 1e9), amp: num(hist.prevAmp, amp) }];
    if (hist.prev2) past.push({ state: hist.prev2, gap: 1e9, amp: num(hist.prevAmp2, past[0].amp) });
    return past;
  }
  // An angle's difference taken the short way round, -pi..pi.
  const turn = (a) => a - TAU * Math.round(a / TAU);
  // The same angle, somewhere in (c - 2pi, c].
  const below = (a, c) => a - TAU * Math.ceil((a - c) / TAU);
  function makePose(targets, keys, halflives, moves) {
    const HL = keys.map((k) => (halflives[k] ? halflives[k][0] : HL_BODY));
    const B = keys.map((k) => (halflives[k] ? halflives[k][1] : 0));
    // An angle (a third entry, a number c): settles round the circle the way
    // that never passes through the angle c. A fourth entry of 1: not slowed
    // by slowBy() - the owl's floating orb does not doze off or wake with
    // the owl.
    const CUT = keys.map((k) => (halflives[k] && typeof halflives[k][2] === "number" ? halflives[k][2] : null));
    const OWN = keys.map((k) => (halflives[k] && halflives[k][3] ? 1 : 0));
    // Past eight half-lives what is left is under a five-thousandth.
    const longest = 8 * Math.max(...HL);
    // The pose `since` seconds after the change into `state` (past[i] is the
    // change it came from) - and, when `both`, the pose FD seconds earlier
    // as well, which is what the change after this one needs to know how
    // fast the screen was moving. The walk back is one call per change.
    function level(state, past, i, since, t, amp, look, o0, both) {
      // Arriving in waiting on you or something wrong: which small reaction
      // it plays (arriveKind), kept with the options this state is drawn with.
      const ak = arriveKind(state, past, i, since, t, S_ARRIVE);
      const o = ak >= 0 ? Object.assign({}, o0, { arrive: ak }) : o0;
      // Waking up or nodding off: how long ago, how far the change before it
      // had got (far), how much of the extras to play (ex), and - nodding off -
      // the pose it is letting go of (F: the old state's at the change, its
      // ordinary blinks and happenings left out). Found even once the piece
      // is over: the settling below measures what was on screen against this
      // state's pose AT the change, piece and all, for as long as it settles.
      const cr = moves ? crossing(state, past, i, since, false) : null;
      const len = state === "standby" ? SLEEP_S : WAKE_S;
      let far = 0, ex = 0, F = null;
      if (cr) {
        const pc = past[cr[1]], d0 = depth(pc.state, past, cr[1] + 1, pc.gap);
        const asleep = state === "standby";
        far = asleep ? 1 - d0 : d0;
        ex = asleep || !PLAIN[state] ? extras(o) : 0;
        if (asleep) F = targets(pc.state, t - cr[0], pc.amp, look, pc.gap, withQuiet(o, 1));
      }
      // The state's pose at clock tt, `sn` seconds into it, dx seconds after now.
      const at = (tt, sn, dx) => {
        const x = cr ? cr[0] + dx : len;
        if (x >= len) return lidCalm(targets(state, tt, amp, look, sn, o), o);
        const P = targets(state, tt, amp, look, sn, withQuiet(o, state === "standby" ? 0 : quietOf(x)));
        moves(P, state, x, far, ex, tt, F);
        return lidCalm(P, o);
      };
      const cur = at(t, since, 0);
      const curB = both ? at(t - FD, since - FD, -FD) : null;
      const pv = i < HIST_MAX ? past[i] : null;
      if (!pv || !pv.state || pv.state === state) return [cur, curB];
      const k = slowBy(state, pv.state);
      if (since >= longest * k) return [cur, curB];
      const s = Math.max(0, since), sB = Math.max(0, since - FD), tc = t - s;
      const on = level(pv.state, past, i + 1, pv.gap, tc, pv.amp, look, o0, true);
      const nwA = at(tc, 0, -s);
      const nwB = at(tc - FD, -FD, -s - FD);
      const outA = {}, outB = both ? {} : null;
      for (let j = 0; j < keys.length; j++) {
        const key = keys[j], hl = OWN[j] ? HL[j] : HL[j] * k;
        let x0 = on[0][key] - nwA[key];
        let v0 = ((on[0][key] - on[1][key]) - (nwA[key] - nwB[key])) / FD;
        if (CUT[j] !== null) {
          x0 = below(on[0][key], CUT[j]) - below(nwA[key], CUT[j]);
          v0 = (turn(on[0][key] - on[1][key]) - turn(nwA[key] - nwB[key])) / FD;
        }
        outA[key] = cur[key] + offset(x0, v0, hl, B[j], s);
        if (both) outB[key] = curB[key] + offset(x0, v0, hl, B[j], sB);
      }
      return [outA, outB];
    }
    return function pose(state, prevState, since, t, amp, look, hist, opts) {
      look = look || {};
      hist = hist || {};
      const past = pastOf(prevState, hist, amp);
      const P = level(state, past, 0, since, t, amp, look, optsOf(opts, t), false)[0];
      if (moves) P.asleep = zsOf(depth(state, past, 0, since));
      return P;
    };
  }
  // What is left, `s` seconds after a change, of an offset x0 moving at v0,
  // with half-life hl. Critically damped: x0 and the speed die away
  // together. Bouncy: the same, turning once through zero (damping ratio
  // 0.7).
  function offset(x0, v0, hl, bouncy, s) {
    if (s >= 8 * hl) return 0;
    const y = 2 * LN2 / hl, j1 = v0 + x0 * y, e = Math.exp(-y * s);
    return bouncy ? e * (x0 * Math.cos(y * s) + (j1 / y) * Math.sin(y * s)) : e * (x0 + j1 * s);
  }

  /** A half-life table from which part is which (eyes, mouth, head, limbs, loose parts). */
  function halfLives(eyes, mouth, head, limbs, trail) {
    const out = {};
    // The painted eyelid settles slowly (HL_LID): a look, not a movement.
    out.lid = [HL_LID, 0]; out.lidSlope = [HL_LID, 0];
    for (const k of eyes) out[k] = [HL_EYES, 0];
    for (const k of mouth) out[k] = [HL_MOUTH, 0];
    for (const k of head) out[k] = [HL_HEAD, 0];
    for (const k of limbs) out[k] = [HL_LIMB, 0];
    for (const k of trail) out[k] = [HL_TRAIL, 1];
    return out;
  }
  const HALF = halfLives(
    ["eyeL", "eyeR", "lookX", "lookY"], ["speak"], ["headYaw", "headPitch", "headRoll", "brow"],
    ["pawLx", "pawLy", "pawLz", "pawRx", "pawRy", "pawRz", "orbX", "orbY", "orbZ"],
    ["earL", "earR", "earTwL", "earTwR", "tailSwing", "tailCurl", "tail2", "tail3", "tail4", "tail5"]);
  const pose = makePose(stateTargets, KEYS, HALF, wakeSleep);

  /**
   * The mouth to draw: [open, wide, round], each 0..1.
   *
   * `mouth` is the mouth track sampled at what is being heard right now
   * ({open, wide, round}, or an array in that order), from the voice's own
   * sound - see docs/LIPSYNC.md. It is scaled by how much the pose is
   * speaking (`P.speak`: 1 in speaking, 0 elsewhere, settling with the
   * state), so when speaking ends the mouth eases shut in about a quarter of
   * a second rather than snapping.
   *
   * No mouth (null or undefined) means no real voice is playing - a typed
   * answer, Quiet mode, an answer kept on screen - and the mouth stays SHUT.
   * An animal never makes up mouth movements that match no sound.
   */
  function mouthOf(P, mouth) {
    const w = clamp(+P.speak || 0, 0, 1);
    if (!mouth || w <= 0) return [0, 0, 0];
    const arr = typeof mouth.length === "number";
    const ch = (v) => clamp(+v || 0, 0, 1) * w;
    return arr ? [ch(mouth[0]), ch(mouth[1]), ch(mouth[2])]
               : [ch(mouth.open), ch(mouth.wide), ch(mouth.round)];
  }

  /* ------------------------------------------------------------------ *
   * From a pose to the numbers the shader reads.
   * ------------------------------------------------------------------ */

  // 3x3 matrices as nine numbers, row by row.
  function rx(a) { const c = Math.cos(a), s = Math.sin(a); return [1, 0, 0, 0, c, -s, 0, s, c]; }
  function ry(a) { const c = Math.cos(a), s = Math.sin(a); return [c, 0, s, 0, 1, 0, -s, 0, c]; }
  function rz(a) { const c = Math.cos(a), s = Math.sin(a); return [c, -s, 0, s, c, 0, 0, 0, 1]; }
  function mul(A, B) {
    const o = new Array(9);
    for (let r = 0; r < 3; r++)
      for (let c = 0; c < 3; c++)
        o[r * 3 + c] = A[r * 3] * B[c] + A[r * 3 + 1] * B[3 + c] + A[r * 3 + 2] * B[6 + c];
    return o;
  }
  function apply(M, v) {
    return [
      M[0] * v[0] + M[1] * v[1] + M[2] * v[2],
      M[3] * v[0] + M[4] * v[1] + M[5] * v[2],
      M[6] * v[0] + M[7] * v[1] + M[8] * v[2],
    ];
  }
  const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];

  // The neck, in the body's frame, and how much bigger the head is drawn
  // than it is modelled (redpanda.sksl's HEAD_S).
  const NECK = [0, 0.60, -0.02], HEAD_S = 1.14;
  // The head's own turn (without the body's). Positive yaw looks to the
  // viewer's right; positive pitch looks up; positive roll tips the head
  // toward the viewer's right shoulder.
  function headTurn(P) { return mul(ry(-P.headYaw), mul(rx(P.headPitch), rz(-P.headRoll))); }
  /** A point given in the head's own (unscaled) frame, in the body's frame. */
  function onHead(P, x, y, z) { return add(NECK, apply(headTurn(P), [x * HEAD_S, y * HEAD_S, z * HEAD_S])); }
  // The shader wants each INVERSE matrix, row by row. A rotation's inverse
  // is its transpose, so row i of the inverse is column i of the matrix.
  const invRow = (M, i) => [M[i], M[3 + i], M[6 + i]];

  // The tail's resting line, wrapped round the panda's right side, and the
  // line it swings out to when relaxed. Body frame; the last number is the
  // radius at that point.
  const TAIL_WRAP = [
    [0.18, 0.08, 0.30, 0.10], [0.46, 0.10, 0.20, 0.15], [0.62, 0.14, -0.04, 0.17],
    [0.58, 0.22, -0.28, 0.16], [0.40, 0.30, -0.42, 0.13], [0.20, 0.38, -0.46, 0.08],
  ];
  const TAIL_OUT = [
    [0.18, 0.08, 0.30, 0.10], [0.46, 0.12, 0.32, 0.15], [0.70, 0.22, 0.26, 0.17],
    [0.84, 0.40, 0.12, 0.16], [0.88, 0.60, -0.04, 0.13], [0.82, 0.78, -0.16, 0.08],
  ];

  /** The body sits here; the camera looks at the origin. */
  const SEAT_Y = -0.90;

  /**
   * Everything the shader needs, as named float arrays: one per uniform,
   * so each app can hand them over with whatever call its GPU API uses.
   * `mouth` is optional - see mouthOf().
   */
  function uniforms(P, mouth) {
    const bodyPos = [0, SEAT_Y + P.bob, 0];
    // Leaning forward tips the top of the body toward the camera (-z);
    // rolling tips it toward the viewer's right.
    const B = mul(rz(-P.bodyRoll), rx(-P.lean));
    const toWorld = (v) => add(bodyPos, apply(B, v));

    const neck = toWorld(NECK);
    const H = mul(B, headTurn(P));

    // An ear stands at its base tilt, leans in and forward as it perks up,
    // and flops outward and back as it droops; `tw` swivels it round on
    // itself, toward a sound.
    const ear = (perk, side, tw) => {
      // Droops outward only below level: 0.35 * max(0, -perk), rounded off
      // near level (a hard corner there changed the ear's speed by a third
      // in one frame on every change into or out of sleep, a doze or an
      // error). The same at the ends: within a hundredth of a radian.
      const out = 0.38 - 0.22 * perk + 0.175 * (Math.sqrt(perk * perk + 0.0025) - perk);
      const fwd = 0.22 * perk;
      return mul(rz(-side * out), mul(rx(fwd), ry(side * tw)));
    };
    const EL = ear(P.earL, -1, P.earTwL), ER = ear(P.earR, 1, P.earTwR);

    const tail = {};
    const curl = clamp(P.tailCurl, 0, 1);
    // Each point's own swing: the ones further out swing as the root did a
    // moment ago (tailAt), so a swing runs down the tail to its tip.
    const sw = [P.tailSwing, P.tailSwing, P.tail2, P.tail3, P.tail4, P.tail5];
    const base = TAIL_WRAP[0];
    for (let i = 0; i < 6; i++) {
      const a = TAIL_WRAP[i], b = TAIL_OUT[i], s = sw[i];
      let x = b[0] + (a[0] - b[0]) * curl, y = b[1] + (a[1] - b[1]) * curl, z = b[2] + (a[2] - b[2]) * curl;
      // Swing round the base about the vertical, more at the tip.
      const k = i / 5;
      const ang = s * 0.45 * k;
      const dx = x - base[0], dz = z - base[2];
      x = base[0] + dx * Math.cos(ang) - dz * Math.sin(ang);
      z = base[2] + dx * Math.sin(ang) + dz * Math.cos(ang);
      // Lifts a little as it swings out either way. (A smooth |s|: a plain
      // one turned its speed round in one frame each time the swing crossed
      // the middle.)
      y += (Math.sqrt(s * s + 0.0016) - 0.04) * 0.05 * k;
      tail["uTail" + i] = [...toWorld([x, y, z]), a[3]];
    }

    return Object.assign({
      uBodyPos: bodyPos,
      uBodyR0: invRow(B, 0), uBodyR1: invRow(B, 1), uBodyR2: invRow(B, 2),
      uBreath: [P.breath],
      uNeck: neck,
      uHeadR0: invRow(H, 0), uHeadR1: invRow(H, 1), uHeadR2: invRow(H, 2),
      uEarL0: invRow(EL, 0), uEarL1: invRow(EL, 1), uEarL2: invRow(EL, 2),
      uEarR0: invRow(ER, 0), uEarR1: invRow(ER, 1), uEarR2: invRow(ER, 2),
      uFace: [clamp(P.eyeL, 0, 1.2), clamp(P.eyeR, 0, 1.2), P.brow],
      uLid: [clamp(P.lid, 0, 1), clamp(P.lidSlope, -1, 1)],
      uMouth: mouthOf(P, mouth),
      uLook: [clamp(P.lookX, -1, 1), clamp(P.lookY, -1, 1)],
      uShL: toWorld([-0.24, 0.48, -0.10]),
      uShR: toWorld([0.24, 0.48, -0.10]),
      uPawL: toWorld([P.pawLx, P.pawLy, P.pawLz]),
      uPawR: toWorld([P.pawRx, P.pawRy, P.pawRz]),
      uOrb: [...toWorld([P.orbX, P.orbY, P.orbZ]), P.orbR],
      uOrbGlow: [clamp(P.orbGlow, 0, 1.5)],
    }, tail);
  }

  /* ------------------------------------------------------------------ *
   * Where the "Zs" rise from while it sleeps.
   *
   * The Zs are drawn by the host, flat, over the picture (the shader is
   * already as big as the phone allows). overlay() tells it where: a point
   * a little above and to one side of the head, carried with the head and
   * the breathing so the Zs stay attached as it sighs, projected through
   * the same camera the shader uses. And how much: `asleep`, which settles
   * from 0 to 1 over a couple of seconds as it nods off (and back, faster,
   * as it wakes) - the host fades the Zs with it.
   * ------------------------------------------------------------------ */

  /**
   * A world point to the shader's screen: [x, y] with y UP, in the units
   * the shader's `p` uses - 0 at the middle of the picture and 1 at its
   * edge (the desktop: half the shorter side of the canvas; the phone: 2r,
   * half of the 4r square the animal is drawn over). `cam` is the animal's
   * camera (its .sksl's CAM_TARGET, CAM_DIST, CAM_PITCH); yaw, pitch and
   * zoom are the host's own uYaw, uPit and uZoom.
   */
  function project(X, cam, yaw, pitch, zoom) {
    const cp = Math.cos(pitch + cam[4]), sp = Math.sin(pitch + cam[4]);
    const cy = Math.cos(yaw), sy = Math.sin(yaw), d = cam[3];
    const rx0 = X[0] - (cam[0] - d * cp * sy), ry0 = X[1] - (cam[1] + d * sp), rz0 = X[2] - (cam[2] - d * cp * cy);
    // Undo the yaw, then the pitch (the shader's ray, turned back).
    const dx = rx0 * cy - rz0 * sy, rz1 = rx0 * sy + rz0 * cy;
    const dy = ry0 * cp + rz1 * sp, dz = -ry0 * sp + rz1 * cp;
    const f = 3.1 * zoom / Math.max(dz, 1e-3);
    return [dx * f, dy * f];
  }
  /** The overlay: {asleep: 0..1, x, y} - see the note above and project(). */
  function overlayAt(P, X, cam, view) {
    view = view || {};
    const q = project(X, cam, +view.yaw || 0, +view.pitch || 0, view.zoom > 0 ? +view.zoom : 1);
    return { asleep: clamp(+P.asleep || 0, 0, 1), x: q[0], y: q[1] };
  }
  // The panda's camera (redpanda.sksl): target x, y, z, distance, pitch.
  const CAM = [0, -0.08, 0, 3.35, 0];
  function overlay(P, view) {
    const B = mul(rz(-P.bodyRoll), rx(-P.lean));
    const bodyPos = [0, SEAT_Y + P.bob, 0];
    const at = add(bodyPos, apply(B, onHead(P, 0.3, 0.92, 0.0)));
    return overlayAt(P, at, CAM, view);
  }

  /* ------------------------------------------------------------------ *
   * The sleeping "Zs" themselves (owner, 2026-09-28): small letter z's
   * rising from overlay()'s point while an animal sleeps - standby only,
   * never when Jarvis is merely unreachable (the host decides that).
   *
   * One shared answer for both apps, so they look the same: where each z
   * is, how big, how see-through and how tilted, as a pure function of the
   * clock. Nothing random per frame - each z's small differences are a hash
   * of its number - so the phone's copy (CritterPose.kt `zs`) is checked
   * against this one by a fixture (critter-zs-golden.json), like the pose.
   *
   * What it looks like: a new z about every 1.4 to 1.8 seconds, each living
   * 3.2 to 4 seconds, so two or three at a time. Each rises up and a little
   * outward (away from the head), sways gently, grows a little and fades
   * out; it fades in over its first moments too, so nothing pops. Calm (the
   * desktop's reduced motion, the phone's calm motion) swaps them for ONE z
   * that stays beside the head and does not rise - still readable as
   * "asleep", with nothing drifting across the screen. The two cross-fade
   * as calm eases in or out.
   * ------------------------------------------------------------------ */
  const ZS = Object.freeze({
    EVERY: 1.6,        // seconds from one z to the next, on average (4096 / 1.6 = 2560, whole)
    JITTER: 0.1,       // each is born up to this much early or late: 1.4 to 1.8 s apart
    SLOTS: 2560,       // PERIOD / EVERY: the z numbers repeat with everything else
    LIFE: 3.2,         // how long each lives, at least...
    LIFE_VAR: 0.8,     // ...plus up to this
    RISE: 0.30,        // how far it rises over its life, in the shader's units (1 = edge)
    RISE_MIN: 0.12,    // never less than this...
    TOP: 0.80,         // ...but no higher than this where it can help it (the panda's head is high)
    OUT: 0.10,         // how far it drifts outward, away from the head...
    TRADE: 0.8,        // ...plus this much of any rise cut short by TOP, so a high head's Zs go
                       // up and out on a slant instead of into the top edge
    SWAY: 0.022,       // and a slow side-to-side sway
    SIZE0: 0.090,      // the letter's height when it appears...
    SIZE1: 0.160,      // ...and as it fades out
    ALPHA: 0.9,        // at its most opaque
    FADE_IN: 0.15,     // share of its life spent fading in
    FADE_OUT: 0.45,    // share of its life spent fading out
    TILT: 0.22,        // radians it leans away from the head
    CALM_DX: 0.02,     // calm: the one still z, this far out from the point...
    CALM_DY: 0.05,     // ...and this far up
    CALM_SIZE: 0.12,
    CALM_ALPHA: 0.75,
    WIDTH: 0.8,        // the letter's width, a share of its height
    STROKE: 0.18,      // its line, a share of its height (round ends)
    LIGHTEN: 0.60,     // its colour: the state's own bound colour, this much toward white,
                       // so it reads on the dark ground beside a dimmed, sleeping animal
    COUNT: 5,          // entries zs() returns: the calm z, then four rising ones
  });

  /**
   * The Zs for one frame: ZS.COUNT entries of [x, y, size, alpha, tilt] - the
   * letter's centre in the shader's units (y UP, like overlay()), its height
   * in the same units, 0..1, and its lean in radians (counter-clockwise, y
   * up). The first is calm's still z; the other four are the rising ones.
   * Entries not showing have alpha 0; the host skips those.
   *
   * `ov` is overlay()'s answer, its `asleep` already multiplied by anything
   * the host fades them with (the phone and the desktop fade them out while
   * Jarvis is unreachable). `calm` is the eased calm weight, 0..1. `t` is
   * the same clock the pose is given.
   */
  function zs(t, ov, calm) {
    const out = [];
    const asleep = clamp(+ov.asleep || 0, 0, 1), ax = +ov.x || 0, ay = +ov.y || 0;
    const c = clamp(+calm || 0, 0, 1);
    const side = ax >= 0 ? 1 : -1;
    out.push([ax + side * ZS.CALM_DX, ay + ZS.CALM_DY, ZS.CALM_SIZE,
              ZS.CALM_ALPHA * asleep * c, -side * ZS.TILT * 0.8]);
    const rise = clamp(ZS.TOP - ay, ZS.RISE_MIN, ZS.RISE);
    const outward = ZS.OUT + (ZS.RISE - rise) * ZS.TRADE;
    // The clock within PERIOD, so a restart at a multiple of it (the phone
    // does that) moves nothing, and a float and a double agree.
    const tl = t - PERIOD * Math.floor(t / PERIOD);
    const kHi = Math.floor((tl + ZS.JITTER) / ZS.EVERY);
    for (let k = kHi - 3; k <= kHi; k++) {
      const n = ((k % ZS.SLOTS) + ZS.SLOTS) % ZS.SLOTS;
      const h1 = hash01(n * 3 + 101), h2 = hash01(n * 3 + 102), h3 = hash01(n * 3 + 103);
      const born = k * ZS.EVERY + (h1 * 2 - 1) * ZS.JITTER;
      const life = ZS.LIFE + ZS.LIFE_VAR * h2;
      const u = (tl - born) / life;
      if (u <= 0 || u >= 1) { out.push([ax, ay, ZS.SIZE0, 0, 0]); continue; }
      const fade = smooth(clamp(u / ZS.FADE_IN, 0, 1)) * smooth(clamp((1 - u) / ZS.FADE_OUT, 0, 1));
      // Rises quickly at first and slows as it goes, like something light.
      const e = u * (1.4 - 0.4 * u);
      out.push([
        ax + side * outward * e + ZS.SWAY * Math.sin(TAU * (0.8 * u + h3)),
        ay + rise * e,
        ZS.SIZE0 + (ZS.SIZE1 - ZS.SIZE0) * u,
        ZS.ALPHA * fade * asleep * (1 - c),
        -side * ZS.TILT * (0.6 + 0.4 * h3),
      ]);
    }
    return out;
  }

  const api = {
    KEYS, BLEND_S, hash01, blink, blinkAt, stateTargets, pose, uniforms, mouthOf, overlay, ZS, zs, HAPPENING_S,
    // The new behaviours' helpers for a host: the pause finder and its
    // numbers, how opaque to draw a face while it says hello or goodbye, and
    // how long each of those takes.
    PAUSE, pauseStep, AHEAD, aheadStep, switchAlpha, HELLO_S, GOODBYE_S,
    // ...and whether a moment it hands in (a stroke, a nod, a glow, a stretch) is playing.
    momentsBusy,
    // Every animal, by face id. The owl and the otter add themselves. Each
    // has `mouth(P, mouth)` too (the same mouthOf), for a drawing that is not
    // the shader - the flat fallback - to open the same mouth, and
    // `overlay(P, view)` for where its sleeping Zs rise from, and
    // `busy(state, t)`: whether an idle happening is playing (the frame pacer's).
    species: { redpanda: { KEYS, stateTargets, pose, uniforms, mouth: mouthOf, overlay, busy, gesturing, HELLO_S, GOODBYE_S } },
    // Shared with the other animals' files, so all three do their sums alike.
    util: { makePose, halfLives, lidSet, lidNod, lidWake, LID, LID_SLEEP, mouthOf, clamp, smooth, ease, rx, ry, rz, mul, apply, add, invRow,
            wave, bump, envAHR, happening, beat, shift, gaze, looks, restingGaze, optsOf, mods, chain,
            gauss, blinkAt, overlayAt, phaseOf, LOOP, PERIOD, TAU, playing, playingV,
            // The slow wander, uneven breathing, and the idle happenings that
            // vary and thin out (2026-09-29).
            noise, breathWave, happeningV, thinGate, NONE4, PHRASE_LEAD,
            toward, eyesOpen, eyesClose, WAKE_S, SLEEP_S,
            // The new behaviours' shared parts (see "New behaviours").
            NEVER, NONE, ZERO2, ZERO4, ZERO5, AWAKE, newOf, varOf, focusOf, petOf, cuteOf, extras, switchE, bagKind,
            listenNod, phraseBeat, ackNodOf, ackGlowOf, focusEndOf, variant, arrivalOf, cuteAt, cuteQuiet, fullTurn,
            cuteBusy, GESTURE_S, HELLO_S, GOODBYE_S },
  };
  root.CritterPose = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
