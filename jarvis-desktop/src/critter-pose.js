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
 * inputs always draw the same panda.
 *
 * Coordinates: x to the viewer's right, y up, the panda faces -z (toward the
 * camera). Angles in radians.
 */
(function (root) {
  "use strict";

  const TAU = Math.PI * 2;

  /** How long one pose takes to melt into the next, in seconds. */
  const BLEND_S = 0.55;

  // The pose is a flat list of numbers so two of them can be blended
  // element by element. These are the names, in order.
  const KEYS = [
    "headYaw", "headPitch", "headRoll", "lean", "bob", "breath",
    "earL", "earR", "eyeL", "eyeR", "brow", "speak", "lookX", "lookY",
    "pawLx", "pawLy", "pawLz", "pawRx", "pawRy", "pawRz",
    "tailSwing", "tailCurl", "orbX", "orbY", "orbZ", "orbR", "orbGlow",
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

  /** 0 open .. 1 shut. A blink roughly every four seconds, never on a beat. */
  function blink(t) {
    const period = 4.1;
    const n = Math.floor(t / period);
    const at = 0.4 + hash01(n) * 2.9;
    const x = t - n * period - at;
    const len = 0.15;
    if (x < 0 || x > len) return 0;
    return Math.sin((x / len) * Math.PI);
  }

  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const smooth = (k) => k * k * (3 - 2 * k);

  /**
   * The pose for ONE state at clock `t`. `amp` is the microphone while
   * listening and Jarvis's own voice while speaking (0..1, already smoothed
   * by the shell). `look` is {x, y, w}: the pointer, -1..1 from the centre,
   * and how much to follow it (0 when there is no pointer).
   */
  function stateTargets(state, t, amp, look) {
    const P = {
      headYaw: 0, headPitch: 0, headRoll: 0, lean: 0, bob: 0, breath: 1,
      earL: 0.2, earR: 0.2, eyeL: 1, eyeR: 1, brow: 0, speak: 0, lookX: 0, lookY: 0,
      pawLx: LAP.pawL[0], pawLy: LAP.pawL[1], pawLz: LAP.pawL[2],
      pawRx: LAP.pawR[0], pawRy: LAP.pawR[1], pawRz: LAP.pawR[2],
      tailSwing: 0, tailCurl: 0.75,
      orbX: LAP.orb[0], orbY: LAP.orb[1], orbZ: LAP.orb[2], orbR: LAP.orb[3], orbGlow: 0.55,
    };
    let breathPeriod = 4.0, breathDepth = 1, blinks = true;

    if (state === "listening") {
      // Ears up and forward, head tilted about 15 degrees - the dog-hearing-
      // its-name tilt - leaning in. The microphone twitches the ears.
      P.headRoll = 0.26 + 0.03 * Math.sin(t * 1.3);
      P.headPitch = 0.06;
      P.lean = 0.10;
      P.earL = 1 + 0.35 * amp * Math.sin(t * 23.0);
      P.earR = 1 + 0.35 * amp * Math.sin(t * 19.0 + 1.1);
      P.eyeL = P.eyeR = 1.12;
      P.brow = 0.7;
      P.lookY = 0.1;
      P.tailSwing = 0.18 * Math.sin(t * 1.6);
      P.orbGlow = 0.55 + 0.5 * amp;
    } else if (state === "thinking") {
      // Holds the orb up in both paws and gazes into it.
      const bob = 0.02 * Math.sin(t * 2.2);
      P.orbX = 0; P.orbY = 0.58 + bob; P.orbZ = -0.56; P.orbR = 0.125;
      P.pawLx = -0.12; P.pawLy = 0.50 + bob; P.pawLz = -0.52;
      P.pawRx = 0.12; P.pawRy = 0.50 + bob; P.pawRz = -0.52;
      P.headPitch = -0.34 + 0.04 * Math.sin(t * 0.9);
      P.headRoll = 0.10 * Math.sin(t * 0.6);
      P.lookX = 0.2 * Math.sin(t * 0.7);
      P.lookY = -0.7;
      P.earL = P.earR = 0.05;
      P.brow = 0.25;
      P.lean = 0.06;
      P.tailSwing = 0.35 * Math.sin(t * 1.7);
      P.orbGlow = 0.95 + 0.2 * Math.sin(t * 2.6);
    } else if (state === "speaking") {
      // A small nod rides Jarvis's own voice, and one paw talks too. The
      // mouth itself is NOT worked out from the loudness any more: it follows
      // the mouth track of the words actually being heard (uniforms' `mouth`),
      // and `speak` only says how much of it to show - 1 here, 0 in every
      // other state, melting between them with the rest of the pose.
      P.speak = 1;
      P.headPitch = 0.04 + 0.08 * amp;
      P.headYaw = 0.08 * Math.sin(t * 0.7);
      P.headRoll = 0.05 * Math.sin(t * 0.9);
      P.pawRx = 0.24; P.pawRy = 0.42 + 0.07 * amp; P.pawRz = -0.46;
      P.brow = 0.3 + 0.3 * amp;
      P.earL = P.earR = 0.45;
      P.tailSwing = 0.22 * Math.sin(t * 1.2);
      P.orbGlow = 0.6 + 0.45 * amp;
    } else if (state === "approval") {
      // Waiting on you: looks straight at you, eyebrows up, and waves.
      P.pawLx = -0.50 + 0.07 * Math.sin(t * 5.0);
      P.pawLy = 1.00 + 0.03 * Math.sin(t * 10.0);
      P.pawLz = -0.48;
      P.eyeL = P.eyeR = 1.1;
      P.brow = 0.85;
      P.earL = P.earR = 0.8;
      P.headRoll = -0.10;
      P.headPitch = 0.05;
      P.tailSwing = 0.3 * Math.sin(t * 2.0);
      P.orbGlow = 0.9;
    } else if (state === "standby") {
      // Asleep: eyes shut, head drooped, ears down, the tail wrapped round,
      // breathing slow and deep.
      P.eyeL = P.eyeR = 0;
      P.headPitch = -0.40;
      P.headRoll = 0.22;
      P.lean = 0.06;
      P.earL = P.earR = -0.7;
      P.tailCurl = 1;
      P.tailSwing = 0.04 * Math.sin(t * 0.5);
      P.orbGlow = 0.15;
      breathPeriod = 6.0; breathDepth = 1.8; blinks = false;
    } else if (state === "error") {
      // Puzzled: head tilted the other way, one ear down, squinting, and a
      // paw scratching its head.
      P.headRoll = -0.28;
      P.headPitch = 0.12;
      P.earL = -0.8; P.earR = 0.5;
      P.eyeL = 0.55; P.eyeR = 0.85;
      P.brow = -0.3;
      P.lookY = 0.35; P.lookX = -0.2;
      P.pawRx = 0.44 + 0.02 * Math.sin(t * 9.0);
      P.pawRy = 1.02 + 0.015 * Math.sin(t * 9.0 + 1.0);
      P.pawRz = -0.16;
      P.orbGlow = 0.35;
      P.tailSwing = 0.1 * Math.sin(t * 0.8);
    } else if (state === "banked") {
      // Things are waiting, but it is keeping them to itself: dozing,
      // half-lidded, still.
      P.eyeL = P.eyeR = 0.35;
      P.headPitch = -0.15;
      P.earL = P.earR = -0.2;
      P.lookY = -0.2;
      P.orbGlow = 0.25;
      P.tailCurl = 0.9;
      breathPeriod = 5.0;
    } else {
      // idle: looks around the room at its own pace.
      P.lookX = 0.55 * Math.sin(t * 0.31) + 0.25 * Math.sin(t * 0.83 + 1.3);
      P.lookY = 0.15 * Math.sin(t * 0.47);
      P.headYaw = 0.22 * P.lookX;
      P.headPitch = 0.08 * P.lookY;
      P.headRoll = 0.06 * Math.sin(t * 0.4);
      P.tailSwing = 0.25 * Math.sin(t * 0.9);
    }

    // Breathing: the chest swells and the whole body rises a little.
    const b = Math.sin((t * TAU) / breathPeriod);
    P.breath = 1 + 0.018 * breathDepth * b;
    P.bob = 0.010 * breathDepth * b;

    // Following the pointer. Asleep, it does not.
    const w = state === "standby" ? 0 : clamp(look.w || 0, 0, 1);
    if (w > 0) {
      const lx = clamp(look.x || 0, -1, 1), ly = clamp(look.y || 0, -1, 1);
      P.lookX += (lx - P.lookX) * w;
      P.lookY += (ly - P.lookY) * w;
      P.headYaw += 0.35 * lx * w;
      P.headPitch += 0.2 * ly * w;
    }

    if (blinks) {
      const k = 1 - blink(t);
      P.eyeL *= k; P.eyeR *= k;
    }
    return P;
  }

  /**
   * Makes an animal's pose() from its stateTargets() and the names of its
   * pose numbers. Every animal melts between states the same way, so the
   * owl and the otter use this too (critter-owl.js, critter-otter.js).
   *
   * The pose actually shown: the previous state's melting into the current
   * one over BLEND_S. Both keep moving while they blend, so a change of
   * state never freezes the panda for the length of the fade.
   *
   * `hist` is what the caller remembered at the moment of the change:
   *   prevAmp - the loudness then. The previous state's pose is drawn with
   *             it, not with the new state's: leaving `speaking`, the new
   *             loudness is 0, and the nod and the orb would drop in one frame.
   *   prev2, gap - the state before the previous one, and how long the
   *             previous state had been showing. If that was less than
   *             BLEND_S, the previous state was itself still melting in, so
   *             the "from" pose carries on that blend instead of jumping to
   *             where it would have settled. One level is enough: a third
   *             change inside the same half second is the only case left.
   *   prevAmp2 - the loudness at the change BEFORE that one, which is what
   *             the state before the previous one (prev2) was drawn with.
   *             Without it a quick A -> B -> A drew prev2 at the latest
   *             change's loudness, and the orb and nod jumped. Optional: a
   *             caller that does not keep it gets prevAmp, as before.
   *
   * A caller keeps these by doing, at each change of state, in this order:
   *   prev2 = prev; gap = now - changedAt; prevAmp2 = prevAmp;
   *   prevAmp = <the loudness of the last frame>; prev = state; ...
   */
  function makePose(targets, keys) {
    return function pose(state, prevState, since, t, amp, look, hist) {
      look = look || {};
      hist = hist || {};
      const cur = targets(state, t, amp, look);
      const k = clamp(since / BLEND_S, 0, 1);
      if (k >= 1 || !prevState || prevState === state) return cur;
      const prevAmp = typeof hist.prevAmp === "number" ? hist.prevAmp : amp;
      const prevAmp2 = typeof hist.prevAmp2 === "number" ? hist.prevAmp2 : prevAmp;
      const gap = typeof hist.gap === "number" ? hist.gap : 1e9;
      const prev = pose(prevState, hist.prev2 || prevState, since + gap, t, prevAmp, look,
                        { prevAmp: prevAmp2 });
      const e = smooth(k), out = {};
      for (const key of keys) out[key] = prev[key] + (cur[key] - prev[key]) * e;
      return out;
    };
  }
  const pose = makePose(stateTargets, KEYS);

  /**
   * The mouth to draw: [open, wide, round], each 0..1.
   *
   * `mouth` is the mouth track sampled at what is being heard right now
   * ({open, wide, round}, or an array in that order), from the voice's own
   * sound - see docs/LIPSYNC.md. It is scaled by how much the pose is
   * speaking (`P.speak`: 1 in speaking, 0 elsewhere, melting with the
   * state), so the mouth settles shut over the same half second as the rest
   * of the pose when speaking ends.
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
    // Leaning forward tips the top of the body toward the camera (-z).
    const B = rx(-P.lean);
    const toWorld = (v) => add(bodyPos, apply(B, v));

    const neck = toWorld([0, 0.60, -0.02]);
    // Positive yaw looks to the viewer's right; positive pitch looks up;
    // positive roll tips the head toward the viewer's right shoulder.
    const H = mul(B, mul(ry(-P.headYaw), mul(rx(P.headPitch), rz(-P.headRoll))));

    // An ear stands at its base tilt, leans in and forward as it perks up,
    // and flops outward and back as it droops.
    const ear = (perk, side) => {
      const out = 0.38 - 0.22 * perk + (perk < 0 ? -0.35 * perk : 0);
      const fwd = 0.22 * perk;
      return mul(rz(-side * out), rx(fwd));
    };
    const EL = ear(P.earL, -1), ER = ear(P.earR, 1);

    const tail = {};
    const s = P.tailSwing, curl = clamp(P.tailCurl, 0, 1);
    const base = TAIL_WRAP[0];
    for (let i = 0; i < 6; i++) {
      const a = TAIL_WRAP[i], b = TAIL_OUT[i];
      let x = b[0] + (a[0] - b[0]) * curl, y = b[1] + (a[1] - b[1]) * curl, z = b[2] + (a[2] - b[2]) * curl;
      // Swing round the base about the vertical, more at the tip.
      const k = i / 5;
      const ang = s * 0.45 * k;
      const dx = x - base[0], dz = z - base[2];
      x = base[0] + dx * Math.cos(ang) - dz * Math.sin(ang);
      z = base[2] + dx * Math.sin(ang) + dz * Math.cos(ang);
      y += Math.abs(s) * 0.05 * k;
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

  const api = {
    KEYS, BLEND_S, hash01, blink, stateTargets, pose, uniforms, mouthOf,
    // Every animal, by face id. The owl and the otter add themselves. Each
    // has `mouth(P, mouth)` too (the same mouthOf), for a drawing that is not
    // the shader - the flat fallback - to open the same mouth.
    species: { redpanda: { KEYS, stateTargets, pose, uniforms, mouth: mouthOf } },
    // Shared with the other animals' files, so all three do their sums alike.
    util: { makePose, mouthOf, clamp, smooth, rx, ry, rz, mul, apply, add, invRow },
  };
  root.CritterPose = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
