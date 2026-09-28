/**
 * The sea otter's body language, for each of Jarvis's eight states.
 *
 * Loaded after critter-pose.js, like the owl's; adds the otter to
 * CritterPose.species. The phone runs a line-for-line Kotlin copy
 * (OtterPose.kt), held to the same answers by tools/gen_critters.py's
 * fixture and CritterPoseTest.
 *
 * It floats on its back, so its body is not upright like the others': in
 * the body's frame x runs along its spine (head at -x, the viewer's left),
 * y points out of its belly and z is its side. The head keeps the frame
 * every animal's head has - face down -z - and is turned up toward the
 * camera, which looks down on the pool.
 */
(function (root) {
  "use strict";
  const C = root.CritterPose;
  const { makePose, halfLives, mouthOf, clamp, smooth, rx, ry, rz, mul, apply, add, invRow,
          wave, bump, envAHR, happening, beat, shift, looks, restingGaze, optsOf, mods, blinkAt,
          overlayAt, ease, toward, eyesOpen, eyesClose, TAU } = C.util;

  const KEYS = [
    "headYaw", "headPitch", "headRoll", "bob", "rock", "tilt", "breath",
    "eyeL", "eyeR", "paddle", "speak", "lookX", "lookY",
    "pawLx", "pawLy", "pawLz", "pawRx", "pawRy", "pawRz",
    "orbX", "orbY", "orbZ", "orbR", "orbGlow", "ripple", "wave", "asleep",
  ];

  const NECK = [-0.60, 0.14, 0.0];
  // The head at rest is turned up toward the camera and a little toward the
  // middle of the picture; the state's own turn adds to this.
  const HEAD_BASE_YAW = 0.30, HEAD_BASE_PITCH = 0.62;
  // The pebble on its chest, and the paws that hold it (body frame).
  const PEBBLE = [-0.12, 0.34, 0.0, 0.075];
  // Where the pebble lies when the paws have let go of it: down on the chest.
  const PEBBLE_DOWN = PEBBLE[1] - 0.08;

  // The otter's own dice (see critter-pose.js's note on salts).
  const S_GAZE = 160, S_EVENT = 176, S_ROLL = 184, S_LEAN = 192, S_BEAT = 200, S_BLINK = 208;
  // Its idle happenings, and how often each comes up: rubbing its pebble,
  // kicking and rolling most; washing its face (the biggest) less.
  const EVENTS = [14, 20, 20, 20, 26];   // wash, roll left, roll right, kick, rub

  // The head's own turn, as a matrix (without the body's).
  function headTurn(P) {
    return mul(ry(-(HEAD_BASE_YAW + P.headYaw)), mul(rx(HEAD_BASE_PITCH + P.headPitch), rz(-P.headRoll)));
  }
  // A point given in the head's frame, in the body's frame: so a paw can be
  // sent to a cheek or over an eye wherever the head happens to be.
  function onHead(P, v) { return add(NECK, apply(headTurn(P), v)); }

  function stateTargets(state, t, amp, look, since, o) {
    if (typeof since !== "number") since = 1e9;
    o = o || optsOf();
    const m = mods(o), hap = m[0], sw = m[2], play = m[3];
    const P = {
      headYaw: 0, headPitch: 0, headRoll: 0, bob: 0, rock: 0, tilt: 0.10, breath: 1,
      eyeL: 1, eyeR: 1, paddle: 0, speak: 0, lookX: 0, lookY: 0,
      pawLx: -0.14, pawLy: 0.33, pawLz: -0.09, pawRx: -0.14, pawRy: 0.33, pawRz: 0.09,
      orbX: PEBBLE[0], orbY: PEBBLE[1], orbZ: PEBBLE[2], orbR: PEBBLE[3], orbGlow: 0.55, ripple: 0.010,
      // Where the rings on the water have spread to: every state shares it.
      // (391 cycles a loop: 2.4 radians a second, kept small for the GPU.)
      wave: 6.283185307179586 * (((t - 1024 * Math.floor(t / 1024)) / 1024 * 391) % 1),
      asleep: state === "standby" ? 1 : 0,
    };
    // 244 cycles a loop: a breath every 4.2 seconds.
    let breathK = 244, breathDepth = 1, blinkSlow = 1, blinks = true, turnBlink = 0, calm = 1;
    let eyeK = 1, deepBreath = 0, paws = null, wash = 0;

    if (state === "listening") {
      // Head up and tilted, eyes on you, its pebble held on its chest.
      const g = looks(t, S_GAZE, 2, 7, 0.8, 0.2, 0.1, 0, 0.05, 1.1, o);
      P.tilt = 0.24;
      P.headPitch = 0.12;
      P.headYaw = 0.1 * g[2];
      P.headRoll = play * 0.28 + sw * 0.025 * wave(t, 212, 0);
      P.eyeL = P.eyeR = 1 + 0.12 * play;
      P.lookX = g[0] - 0.4 * g[2]; P.lookY = g[1] - 0.4 * g[3];
      P.orbGlow = 0.55 + 0.5 * amp;
      turnBlink = g[4];
    } else if (state === "thinking") {
      // Taps the pebble on its belly, watching it - a few taps, then a
      // pause to think, then a few more; glancing up now and then.
      const gate = smooth(clamp(0.5 + 1.5 * wave(t, 184, 0), 0, 1));
      const tap = sw * Math.pow(0.5 - 0.5 * wave(t, 1141, Math.PI / 2), 2) * gate;
      const g = looks(t, S_GAZE, 1.8, 6, 0.6, 0.5, 0.2, 0.8, 0.05, 1.1, o);
      P.orbY = PEBBLE[1] + 0.07 * tap;
      P.pawLy = P.pawRy = 0.33 + 0.07 * tap;
      P.headPitch = -0.30 + 0.2 * g[3];
      P.headYaw = 0.12 * g[2];
      P.headRoll = sw * 0.10 * wave(t, 98, 0);
      P.lookX = 0.3 + g[0] - 0.4 * g[2]; P.lookY = -0.7 + g[1] - 0.4 * g[3];
      P.orbGlow = 0.95 + 0.2 * wave(t, 424, 0);
      turnBlink = g[4];
    } else if (state === "speaking") {
      // Holds the pebble and talks with its eyes and its head - in phrases:
      // a nod, both paws lifting a little off the pebble and opening, or a
      // tilt; at most one every two seconds, often none, never the same one
      // twice running, never just as its eyes move (see beat()). The paws
      // never leave the chest (holding the pebble up is what waiting on you
      // looks like). The mouth follows the words being heard
      // (critter-pose.js's mouthOf).
      const g = looks(t, S_GAZE, 1.8, 6, 0.65, 0.5, 0.18, 0, 0.06, 1.1, o);
      const b = beat(t, S_BEAT, S_GAZE, 1.8, 6, 0.65);
      const x = b[1];
      P.speak = 1;
      P.tilt = 0.16;
      P.headPitch = 0.05;
      P.headYaw = sw * 0.05 * wave(t, 111, 0) + 0.08 * g[2];
      P.headRoll = sw * 0.04 * wave(t, 93, 0.5);
      P.lookX = g[0] - 0.16 * g[2]; P.lookY = g[1] - 0.16 * g[3];
      P.orbGlow = 0.6 + 0.45 * amp;
      if (b[0] === 0) {
        P.headPitch -= hap * 0.06 * (bump(x / 0.7) - 0.3 * bump((x - 0.55) / 0.7));
      } else if (b[0] === 1) {
        const e = hap * envAHR(x, 0.4, 0.3, 0.6);
        P.pawLy += 0.06 * e; P.pawRy += 0.06 * e; P.pawLz -= 0.05 * e; P.pawRz += 0.05 * e;
        P.headPitch -= hap * 0.025 * bump(x / 0.9);
      } else if (b[0] === 2) {
        P.headRoll += hap * play * 0.07 * bump(x / 1.2);
      }
      turnBlink = g[4];
    } else if (state === "approval") {
      // Waiting on you, perhaps on something serious: no wave, nothing cute
      // (the owner's call, 2026-09-28). It lifts its head and holds its
      // pebble up a little off its chest in both paws, as if showing it to
      // you - looking at you, and keeping still, floating more quietly.
      // (Speaking keeps the pebble low on its chest, so the two stay easy to
      // tell apart. The paws stay together, forearms lying along the chest
      // rather than standing up from it: drawn in toward the chin, or held
      // higher, the forearm stood up and read as a raised hand.)
      const g = restingGaze(t, S_GAZE);
      P.tilt = 0.20;
      P.headPitch = 0.12;
      P.pawLx = P.pawRx = -0.08;
      P.pawLz = -0.07; P.pawRz = 0.07;
      P.pawLy = P.pawRy = 0.38;
      P.orbX = -0.08;
      P.orbY = PEBBLE[1] + 0.07;
      P.eyeL = P.eyeR = 1 + 0.1 * play;
      P.lookX = g[0]; P.lookY = g[1];
      P.orbGlow = 0.9;
      calm = 0.7; blinkSlow = 1.4;
    } else if (state === "standby") {
      // Asleep, drifting, paws over its eyes and its pebble resting on its
      // chest. The water still rocks it, but gently; once in a while a sigh.
      const e = happening(t, 16, 0.5, 5.5, S_EVENT, 0.35, 1);
      const sigh = e[0] === 0 ? bump(e[1] / 4.5) : 0;
      P.tilt = 0.04;
      P.headPitch = 0.10 - 0.03 * sigh;
      P.eyeL = P.eyeR = 0;
      P.orbGlow = 0.15;
      P.ripple = 0.005;
      deepBreath = sigh; calm = 0.4;
      // 171 cycles a loop: a breath every 6 seconds.
      breathK = 171; breathDepth = 1.8; blinks = false;
      paws = "eyes";
    } else if (state === "error") {
      // Something went wrong: a still, concerned look - head tipped a
      // little, eyes lowered, holding its pebble. Nothing comic (the pebble
      // used to slip and it scratched its head; the owner's call,
      // 2026-09-28). Only its breathing and the water move it, and its
      // eyes' tiny darts.
      const g = restingGaze(t, S_GAZE);
      P.headRoll = -0.15 * play;
      P.headPitch = 0.02;
      P.eyeL = P.eyeR = 0.8;
      P.lookX = g[0]; P.lookY = -0.25 + g[1];
      P.orbGlow = 0.35;
      calm = 0.8; blinkSlow = 1.4;
    } else if (state === "banked") {
      // Dozing on the water, half-lidded, blinking slowly, and now and then
      // nodding off - its head sinking back, until it catches itself.
      const e = happening(t, 16, 0.5, 5.5, S_EVENT, 0.55, 1);
      const x = e[1];
      const droop = e[0] === 0 ? (x < 3.2 ? smooth(clamp(x / 3.2, 0, 1)) : 1 - smooth(clamp((x - 3.2) / 0.8, 0, 1))) : 0;
      P.eyeL = P.eyeR = 0.35 * (1 - 0.7 * droop);
      P.headPitch = -0.10 - 0.12 * droop;
      P.orbGlow = 0.25;
      calm = 0.8;
      // 205 cycles a loop: a breath every 5 seconds.
      breathK = 205; blinkSlow = 2.5;
    } else {
      // idle: floats with the water, looks about - eyes first, head after -
      // and every 10 to 30 seconds does one small thing: most often rubs its
      // pebble, kicks its feet or rolls lazily to one side; now and then
      // washes its face.
      const g = looks(t, S_GAZE, 1.5, 6, 0.35, 0.8, 0.25, 0, 0.08, 1.1, o);
      const ev = happening(t, 16, 0.5, 5.5, S_EVENT, 0.7, EVENTS);
      const x = ev[1];
      let hx = g[2];
      P.tilt = 0.10 + sw * 0.011 * shift(t, S_ROLL);
      P.rock = sw * 0.01 * shift(t, S_LEAN);
      P.pawLy += sw * 0.008 * wave(t, 150, 0); P.pawRy += sw * 0.008 * wave(t, 150, 2.0);
      if (ev[0] === 0) {
        // Washes its face: paws to its cheeks, rubbing down, and back.
        wash = hap * envAHR(x, 0.6, 2.2, 0.8);
        P.headPitch += 0.1 * wash;
        eyeK = 1 - 0.6 * wash;
      } else if (ev[0] === 1 || ev[0] === 2) {
        // Rolls lazily to one side and looks that way, then back. (A small
        // roll: the look carries it.)
        const s = ev[0] === 1 ? -1 : 1, e = hap * envAHR(x, 1.4, 1.8, 1.8);
        P.rock += s * 0.02 * e;
        hx += (s * 0.6 - hx) * e;
      } else if (ev[0] === 3) {
        // Kicks its feet a few times.
        P.paddle = hap * envAHR(x, 0.4, 1.8, 0.8) * (0.5 + 0.5 * wave(t, 1024, 0));
      } else if (ev[0] === 4) {
        // Lifts its pebble a little and rubs it between its paws.
        const e = hap * envAHR(x, 0.5, 1.5, 0.8), r = 0.03 * wave(t, 1536, 0) * e;
        P.orbY += 0.03 * e; P.pawLy += 0.03 * e; P.pawRy += 0.03 * e;
        P.pawLx += r; P.pawRx -= r;
      }
      P.headYaw = 0.25 * hx;
      P.headPitch += 0.10 * g[3];
      P.headRoll = sw * 0.05 * wave(t, 67, 0);
      P.lookX = g[0] - 0.4 * hx; P.lookY = g[1] - 0.4 * g[3];
      turnBlink = g[4];
    }

    // Floating: the whole otter bobs and rocks with the water (179 and 130
    // cycles a loop: a swell every 5.7 seconds, a rock every 7.9) - gently,
    // and less again under the calm, serious and still options.
    const settle = (1 - 0.5 * o.calm) * (1 - 0.6 * o.serious) * (1 - o.still);
    const water = calm * settle;
    // The small waves and rings on the water (seaotter.sksl's waterSlope)
    // quieten with the options too - calm halves them, still stops them.
    // (Only the options: each state already sets its own ripple.)
    P.ripple *= settle;
    P.bob = 0.009 * water * wave(t, 179, 0);
    P.rock += 0.025 * water * wave(t, 130, 0.6);
    const b = wave(t, breathK, 0) * (1 + 0.6 * deepBreath);
    P.breath = 1 + 0.02 * breathDepth * b;

    const w = state === "standby" ? 0 : clamp(look.w || 0, 0, 1);
    if (w > 0) {
      const lx = clamp(look.x || 0, -1, 1), ly = clamp(look.y || 0, -1, 1);
      P.lookX += (lx - P.lookX) * w;
      P.lookY += (ly - P.lookY) * w;
      P.headYaw += m[1] * 0.2 * lx * w;
      P.headPitch += m[1] * 0.2 * ly * w;
    }

    // Paws that go to the head are placed after the head has turned. While
    // they are away the pebble rests on its chest, not in mid-air.
    if (paws === "eyes") {
      [P.pawLx, P.pawLy, P.pawLz] = onHead(P, [-0.10, 0.05, -0.25]);
      [P.pawRx, P.pawRy, P.pawRz] = onHead(P, [0.10, 0.05, -0.25]);
      P.orbY = PEBBLE_DOWN;
    }
    if (wash > 0) {
      // Both paws to the near side of its face - one on the cheek, one
      // under the jaw - rubbing up and down, held out in front of the face
      // where they can be seen. (Its far cheek is on the far side of its
      // head as it lies, and reaching it meant an arm across the face.)
      const r = 0.03 * wave(t, 1229, 0);
      const L = onHead(P, [0.22, -0.15 + r, -0.21]), R = onHead(P, [0.27, -0.04 + r, -0.15]);
      P.pawLx += (L[0] - P.pawLx) * wash; P.pawLy += (L[1] - P.pawLy) * wash; P.pawLz += (L[2] - P.pawLz) * wash;
      P.pawRx += (R[0] - P.pawRx) * wash; P.pawRy += (R[1] - P.pawRy) * wash; P.pawRz += (R[2] - P.pawRz) * wash;
      P.orbY += (PEBBLE_DOWN - P.orbY) * wash;
    }

    const q = 1 - o.quiet;
    const k = eyeK * (1 - q * Math.max(blinks ? blinkAt(t, S_BLINK, blinkSlow, 2, 10) : 0, turnBlink));
    P.eyeL *= k; P.eyeR *= k;
    return P;
  }

  /** A small stretch in the water, `s` 0..1: paws up and apart, chin up, toes out. */
  function stretch(P, s) {
    P.pawLy += 0.06 * s; P.pawRy += 0.06 * s; P.pawLz -= 0.06 * s; P.pawRz += 0.06 * s;
    P.headPitch += 0.10 * s; P.tilt += 0.04 * s; P.paddle += 0.5 * s;
  }
  /**
   * The otter's waking up and nodding off - see critter-pose.js's "Waking
   * up and falling asleep" and the panda's wakeSleep for what x, k, E and F
   * are.
   */
  function wakeSleep(P, state, x, k, E, t, F) {
    const e = E * k;
    if (state === "standby") {
      // Nodding off: a slow stretch in the water, then its paws come up
      // over its eyes (leaving the pebble on its chest) and it settles.
      const s = e * envAHR(x - 0.15, 0.5, 0.25, 0.5);
      const lids = (1 - 0.35 * ease((x - 0.2) / 0.8)) * (1 - 0.5 * E * envAHR(x - 0.15, 0.5, 0.25, 0.5))
        * (1 - ease((x - 1.4) / 0.8));
      const lid = k * toward(eyesClose(x), lids, E);
      P.eyeL = F.eyeL * lid; P.eyeR = F.eyeR * lid;
      // Its paws (and the pebble in them) stay where they were until 1.2 s,
      // then take 1.2 s to come up over its eyes; the stretch is over by 1.4 s.
      const hold = e * (1 - ease((x - 1.2) / 1.2));
      P.pawLx = toward(P.pawLx, F.pawLx, hold); P.pawLy = toward(P.pawLy, F.pawLy, hold); P.pawLz = toward(P.pawLz, F.pawLz, hold);
      P.pawRx = toward(P.pawRx, F.pawRx, hold); P.pawRy = toward(P.pawRy, F.pawRy, hold); P.pawRz = toward(P.pawRz, F.pawRz, hold);
      P.orbX = toward(P.orbX, F.orbX, hold); P.orbY = toward(P.orbY, F.orbY, hold);
      stretch(P, s);
      return;
    }
    // Waking: its paws stay over its eyes a moment, rub them (twice each,
    // lowered a little so the eyes show, squinting open), come away into a
    // small stretch, and go back to the pebble, picking it up.
    const s = e * envAHR(x - 1.0, 0.4, 0.3, 0.4);
    stretch(P, s);
    const face = e * (1 - ease((x - 1.0) / 1.0));
    if (face > 0) {
      const rub = envAHR(x - 0.3, 0.2, 0.45, 0.2), ph = TAU * 2 * (x - 0.3);
      const L = onHead(P, [-0.10, 0.05 - 0.05 * rub + 0.025 * rub * Math.sin(ph), -0.25]);
      const R = onHead(P, [0.10, 0.05 - 0.05 * rub - 0.025 * rub * Math.sin(ph), -0.25]);
      P.pawLx = toward(P.pawLx, L[0], face); P.pawLy = toward(P.pawLy, L[1], face); P.pawLz = toward(P.pawLz, L[2], face);
      P.pawRx = toward(P.pawRx, R[0], face); P.pawRy = toward(P.pawRy, R[1], face); P.pawRz = toward(P.pawRz, R[2], face);
    }
    P.orbY = toward(P.orbY, PEBBLE_DOWN, e * (1 - ease((x - 1.6) / 0.6)));
    const lids = 0.4 * ease((x - 0.45) / 0.4) + 0.6 * ease((x - 1.05) / 0.45);
    const f = 1 - k * (1 - toward(eyesOpen(x), lids, E));
    P.eyeL *= f; P.eyeR *= f;
  }

  const HALF = halfLives(
    ["eyeL", "eyeR", "lookX", "lookY"], ["speak"], ["headYaw", "headPitch", "headRoll"],
    ["pawLx", "pawLy", "pawLz", "pawRx", "pawRy", "pawRz", "orbX", "orbY", "orbZ"], ["paddle"]);
  const pose = makePose(stateTargets, KEYS, HALF, wakeSleep);

  const WATER_Y = -0.42;

  function uniforms(P, mouth) {
    const bodyPos = [0.02, WATER_Y + 0.02 + P.bob, 0];
    // Tilt lifts the head end; rock rolls the otter about its spine.
    const B = mul(rz(-P.tilt), rx(P.rock));
    const toWorld = (v) => add(bodyPos, apply(B, v));
    const H = mul(B, headTurn(P));
    return {
      uBodyPos: bodyPos,
      uBodyR0: invRow(B, 0), uBodyR1: invRow(B, 1), uBodyR2: invRow(B, 2),
      uBreath: [P.breath],
      uNeck: toWorld(NECK),
      uHeadR0: invRow(H, 0), uHeadR1: invRow(H, 1), uHeadR2: invRow(H, 2),
      uFace: [clamp(P.eyeL, 0, 1.2), clamp(P.eyeR, 0, 1.2), clamp(P.paddle, 0, 1)],
      uMouth: mouthOf(P, mouth),
      uLook: [clamp(P.lookX, -1, 1), clamp(P.lookY, -1, 1)],
      // Shoulders on top of the chest, so the short arms lie along it.
      uShL: toWorld([-0.34, 0.20, -0.13]),
      uShR: toWorld([-0.34, 0.20, 0.13]),
      uPawL: toWorld([P.pawLx, P.pawLy, P.pawLz]),
      uPawR: toWorld([P.pawRx, P.pawRy, P.pawRz]),
      uWater: [WATER_Y, P.wave, clamp(P.ripple, 0, 0.03), 0],
      uOrb: [...toWorld([P.orbX, P.orbY, P.orbZ]), P.orbR],
      uOrbGlow: [clamp(P.orbGlow, 0, 1.5)],
    };
  }

  // The otter's camera (seaotter.sksl): target x, y, z, distance, pitch.
  const CAM = [0, -0.30, 0, 3.30, 0.50];
  /** Where its sleeping Zs rise from - see critter-pose.js's overlay(). */
  function overlay(P, view) {
    const bodyPos = [0.02, WATER_Y + 0.02 + P.bob, 0];
    const B = mul(rz(-P.tilt), rx(P.rock));
    const at = add(bodyPos, apply(B, onHead(P, ZZ_AT)));
    return overlayAt(P, at, CAM, view);
  }
  const ZZ_AT = [-0.05, 0.36, 0.05];

  /** Whether one of its idle happenings is playing at clock t (critter-pose.js playing()). */
  function busy(state, t) {
    return state === "idle" && C.util.playing(happening(t, 16, 0.5, 5.5, S_EVENT, 0.7, EVENTS));
  }

  C.species.seaotter = { KEYS, stateTargets, pose, uniforms, mouth: mouthOf, overlay, busy };
})(typeof globalThis !== "undefined" ? globalThis : this);
