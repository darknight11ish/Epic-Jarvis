/**
 * The monkey's body language, for each of Jarvis's eight states.
 *
 * Loaded after critter-pose.js, like the owl's and the otter's; adds the
 * monkey to CritterPose.species. The phone runs a line-for-line Kotlin copy
 * (MonkeyPose.kt), held to the same answers by tools/gen_critters.py's
 * fixture and CritterPoseTest.
 *
 * It hangs by one arm (the viewer's right) from a vine across the top of the
 * picture, and swings gently on it like a slow pendulum; the other hand holds
 * a banana, which is its orb. Asleep, it has climbed up and sits on the vine,
 * its tail curled round it, hugging its banana. The owner asked for it to be
 * "more energetic than the other animal models to a degree" - so it swings,
 * glances a little more often and does its small things a little more often
 * than the others, but with the same limits: every movement eased, nothing
 * big faster than a few times a second, looks held at least 0.6 s, and the
 * serious moments (waiting on you, something wrong, a crisis) still.
 *
 * Frames. World: x to the viewer's right, y up, the monkey faces -z. The
 * body's own frame has its origin in the middle of the torso. The body hangs
 * from the PIVOT, where its hand holds the vine: its middle sits `hang` from
 * the pivot, turned round it by the swing - so a swing turns the whole
 * monkey round its hand, as a pendulum does.
 */
(function (root) {
  "use strict";
  const C = root.CritterPose;
  const { makePose, halfLives, mouthOf, clamp, smooth, rx, ry, rz, mul, apply, add, invRow,
          wave, bump, envAHR, happening, beat, shift, looks, restingGaze, optsOf, mods, blinkAt,
          overlayAt, ease, toward, eyesOpen, eyesClose } = C.util;

  const KEYS = [
    "headYaw", "headPitch", "headRoll", "swing", "lean", "breath", "bob",
    "eyeL", "eyeR", "brow", "speak", "lookX", "lookY", "earL", "earR",
    "vineY", "vineZ", "hangX", "hangY", "hangZ", "dip", "dipX",
    "grip", "aHx", "aHy", "aHz", "aEx", "aEy", "aEz", "bEx", "bEy", "bEz", "bHx", "bHy", "bHz",
    "orbX", "orbY", "orbZ", "orbR", "orbGlow", "banYaw", "banRoll", "banPitch",
    "legLf", "legLo", "legLk", "legRf", "legRo", "legRk",
    "tailWrap", "tail1", "tail2", "tail3", "tail4", "tailCurl",
    "asleep",
  ];

  // Where the hand holds the vine (x), and the vine's height and depth there
  // while it hangs.
  const GRIP_X = 0.46, VINE_Y = 0.93;
  // The body's middle, from the pivot, hanging (and sitting on the vine).
  // (It hangs beside its hand, not under it, as in the owner's picture: its
  // arm goes up past the side of its head, outside the ear.)
  const HANG = [-0.60, -1.133, -0.11], SIT = [-0.46, 0.245, 0.0], VINE_SIT = -0.405;
  // The neck and the shoulders, in the body's frame.
  const NECK = [0, 0.185, -0.01], SH_A = [0.16, 0.12, 0.02], SH_B = [-0.15, 0.11, 0.0];
  // Arm B (the banana arm) hanging at its side, the banana in its hand.
  const ELB_B = [-0.25, -0.01, -0.03], HAND_B = [-0.31, -0.13, -0.09];
  // The banana, from the hand holding it (body frame): held near one end.
  const BAN_AT = [0.07, -0.025, -0.035];
  const THIGH = 0.16, SHIN = 0.16;
  // Arm A's upper arm and forearm (each); and which way its elbow bends while
  // it holds the vine: out to the side, a little down and back.
  const ARM = 0.62, POLE = [1, -0.25, 0.2], ELBOW_MAX = 0.3;
  // How much bigger the head is drawn than it is modelled (monkey.sksl's HEAD_S).
  const HEAD_S = 1.10;

  // The monkey's own dice (see critter-pose.js's note on salts).
  const S_GAZE = 224, S_EVENT = 240, S_ROLL = 248, S_LEAN = 216, S_BEAT = 232, S_BLINK = 212;
  // Its idle happenings, and how often each comes up: kicking its legs,
  // looking round and curling its tail most; looking at its banana and a
  // wider swing a little less; a scratch of its head (the biggest) least.
  const EVENTS = [10, 16, 20, 16, 20, 18];   // scratch, banana, kick, swing, look round, tail curl
  // A 16-second slot has one with a chance of 0.85 (the others: 0.7) - about
  // a fifth more often. (Slots must divide critter-pose.js's PERIOD.)
  const SLOT = 16, CHANCE = 0.85;

  // The head's own turn (without the body's).
  function headTurn(P) { return mul(ry(-P.headYaw), mul(rx(P.headPitch), rz(-P.headRoll))); }
  /** A point given in the head's frame, in the body's frame. */
  function onHead(P, v) { return add(NECK, apply(headTurn(P), [v[0] * HEAD_S, v[1] * HEAD_S, v[2] * HEAD_S])); }

  /**
   * How much each state lets it swing, and the swing at clock t: a slow
   * pendulum (293 cycles a loop: one swing every 3.5 seconds, 0.29 a second)
   * whose reach itself drifts slowly (41 cycles a loop), about 1.5 to 2.5
   * degrees each way - under 4 at its widest. Idle, now and then it swings a little wider for a few swings
   * (the happening "swing"). `m` is mods(). The tail and the legs ask for it
   * a moment earlier (follow-through).
   */
  const SWING = { idle: 1, listening: 0.45, thinking: 0.55, speaking: 0.6, approval: 0.15, standby: 0,
                  error: 0.1, banked: 0.4 };
  function swingAt(state, t, m) {
    const k = SWING[state] === undefined ? 1 : SWING[state];
    let a = 0.014 * (1 + 0.25 * wave(t, 41, 1.3));
    if (state === "idle") {
      const ev = happening(t, SLOT, 0.5, 5.5, S_EVENT, CHANCE, EVENTS);
      if (ev[0] === 3) a += m[0] * 0.007 * envAHR(ev[1], 1.5, 3.0, 2.0);
    }
    return k * m[2] * a * wave(t, 293, 0);
  }
  const TAIL_LAG = 0.14;

  function stateTargets(state, t, amp, look, since, o) {
    if (typeof since !== "number") since = 1e9;
    o = o || optsOf();
    const m = mods(o), hap = m[0], sw = m[2], play = m[3];
    const P = {
      headYaw: 0, headPitch: 0, headRoll: 0, swing: 0, lean: 0, breath: 1, bob: 0,
      eyeL: 1, eyeR: 1, brow: 0, speak: 0, lookX: 0, lookY: 0, earL: 0, earR: 0,
      vineY: VINE_Y, vineZ: 0.16, hangX: HANG[0], hangY: HANG[1], hangZ: HANG[2], dip: 0.035, dipX: GRIP_X,
      grip: 1, aHx: 0.20, aHy: 0.05, aHz: -0.12, aEx: 0.34, aEy: -0.02, aEz: -0.06,
      bEx: ELB_B[0], bEy: ELB_B[1], bEz: ELB_B[2], bHx: HAND_B[0], bHy: HAND_B[1], bHz: HAND_B[2],
      orbX: 0, orbY: 0, orbZ: 0, orbR: 0.09, orbGlow: 0.55, banYaw: 0.25, banRoll: 0.10, banPitch: 0,
      legLf: 0.18, legLo: 0.10, legLk: 0.45, legRf: 0.18, legRo: 0.10, legRk: 0.45,
      tailWrap: 0, tail1: 0, tail2: 0, tail3: 0, tail4: 0, tailCurl: 0,
      asleep: state === "standby" ? 1 : 0,
    };
    // 244 cycles a loop: a breath every 4.2 seconds.
    let breathK = 244, breathDepth = 1, blinkSlow = 1, blinks = true, turnBlink = 0;
    let eyeK = 1, deepBreath = 0, scratch = 0, peel = 0;

    if (state === "listening") {
      // Leans in, head tilted about 15 degrees, ears turned forward to you,
      // eyes on you with only small glances; its swing settles to half.
      // (Serious: no tilt, eyes their usual size.)
      const g = looks(t, S_GAZE, 1.8, 6, 0.8, 0.2, 0.1, 0, 0.05, 1.1, o);
      P.headRoll = play * 0.26 + sw * 0.025 * wave(t, 205, 0);
      P.headPitch = 0.06;
      P.headYaw = 0.1 * g[2];
      P.lean = 0.09;
      P.earL = P.earR = -0.22 - 0.06 * amp;
      P.eyeL = P.eyeR = 1 + 0.12 * play;
      P.brow = 0.3 + 0.4 * play;
      P.lookX = g[0] - 0.4 * g[2]; P.lookY = 0.1 + g[1] - 0.4 * g[3];
      P.orbGlow = 0.55 + 0.5 * amp;
      turnBlink = g[4];
    } else if (state === "thinking") {
      // Brings its banana up in front of its chest and looks into it - it
      // glows its brightest - tapping it against its chin in little bursts,
      // and glancing up and away now and then.
      const gate = smooth(clamp(0.5 + 1.5 * wave(t, 184, 0), 0, 1));
      const tap = sw * Math.pow(0.5 - 0.5 * wave(t, 1141, Math.PI / 2), 2) * gate;
      const g = looks(t, S_GAZE, 1.8, 6, 0.55, 0.6, 0.2, 0.75, 0.05, 1.1, o);
      P.bEx = -0.24; P.bEy = 0.02; P.bEz = -0.14;
      P.bHx = -0.10; P.bHy = 0.02 + 0.045 * tap; P.bHz = -0.27;
      P.banYaw = 0.1 + sw * 0.12 * wave(t, 97, 0); P.banRoll = 0.35; P.banPitch = -0.2;
      P.orbR = 0.11;
      P.headPitch = -0.30 + sw * 0.03 * wave(t, 147, 0) + 0.22 * g[3];
      P.headYaw = -0.08 + 0.15 * g[2];
      P.headRoll = sw * 0.08 * wave(t, 98, 0);
      P.lookX = -0.2 + g[0] - 0.4 * g[2];
      P.lookY = -0.7 + g[1] - 0.4 * g[3];
      P.brow = 0.25;
      P.lean = 0.05;
      P.orbGlow = 0.95 + 0.2 * wave(t, 424, 0);
      turnBlink = g[4];
    } else if (state === "speaking") {
      // Talks with its eyes, its head and its banana hand - in phrases: at
      // most one gesture every two seconds (a nod, the banana lifted a
      // little and lowered, a tilt), often none, never the same one twice
      // running, never just as its eyes move to look somewhere (beat()).
      // Its swing settles to a little over half. The mouth follows the
      // words being heard (critter-pose.js's mouthOf).
      const g = looks(t, S_GAZE, 1.6, 5.5, 0.65, 0.5, 0.18, 0, 0.06, 1.1, o);
      const b = beat(t, S_BEAT, S_GAZE, 1.6, 5.5, 0.65);
      const x = b[1];
      P.speak = 1;
      P.lean = 0.05;
      P.headPitch = 0.03;
      P.headYaw = sw * 0.05 * wave(t, 111, 0) + 0.09 * g[2];
      P.headRoll = sw * 0.04 * wave(t, 93, 0.5);
      P.lookX = g[0] - 0.16 * g[2]; P.lookY = g[1] - 0.16 * g[3];
      P.brow = 0.3 + 0.1 * amp;
      P.orbGlow = 0.6 + 0.45 * amp;
      if (b[0] === 0) {
        // A nod on the stressed word: down, and back a little past level.
        P.headPitch -= hap * 0.065 * (bump(x / 0.7) - 0.3 * bump((x - 0.55) / 0.7));
        P.brow += hap * 0.25 * bump(x / 0.7);
      } else if (b[0] === 1) {
        // The banana hand comes up and out a little, holds, and goes back.
        const e = hap * envAHR(x, 0.4, 0.3, 0.6);
        P.bHx += 0.05 * e; P.bHy += 0.12 * e; P.bHz -= 0.08 * e;
        P.bEy += 0.05 * e; P.bEz -= 0.03 * e;
        P.banRoll += 0.25 * e;
        P.headPitch -= hap * 0.025 * bump(x / 0.9);
      } else if (b[0] === 2) {
        P.headRoll += hap * play * 0.07 * bump(x / 1.2);
        P.brow += hap * 0.15 * bump(x / 1.2);
      }
      turnBlink = g[4];
    } else if (state === "approval") {
      // Waiting on you - perhaps on something serious, so no wave and
      // nothing cute (the owner's call, 2026-09-28): it hangs still, leans
      // in and looks straight at you, ears forward, holding its banana out
      // a little toward you. Only its breathing moves, slow blinks and its
      // eyes' tiny darts.
      const g = restingGaze(t, S_GAZE);
      P.lean = 0.07;
      P.headPitch = 0.04;
      P.eyeL = P.eyeR = 1 + 0.1 * play;
      P.brow = 0.4;
      P.earL = P.earR = -0.18;
      P.bEx = -0.26; P.bEy = 0.02; P.bEz = -0.10;
      P.bHx = -0.22; P.bHy = -0.02; P.bHz = -0.30;
      P.banYaw = 0.35; P.banRoll = 0.05;
      P.lookX = g[0]; P.lookY = g[1];
      P.orbGlow = 0.9;
      blinkSlow = 1.4;
    } else if (state === "standby") {
      // Asleep, sitting on the vine: it has climbed up onto it, its legs
      // hanging in front and its tail curled round it, hugging its banana
      // to its chest; head drooped, eyes shut, breathing slowly. Once in a
      // while a sigh. Nothing else moves.
      const e = happening(t, 16, 0.5, 5.5, S_EVENT, 0.35, 1);
      const sigh = e[0] === 0 ? bump(e[1] / 4.5) : 0;
      P.vineY = VINE_SIT; P.vineZ = 0; P.hangX = SIT[0]; P.hangY = SIT[1]; P.hangZ = SIT[2];
      P.dip = 0.02; P.dipX = 0;
      P.grip = 0; P.aHx = 0.07; P.aHy = -0.03; P.aHz = -0.20; P.aEx = 0.25; P.aEy = -0.07; P.aEz = -0.08;
      P.bEx = -0.17; P.bEy = -0.03; P.bEz = -0.10; P.bHx = -0.07; P.bHy = -0.04; P.bHz = -0.20;
      P.banYaw = 0; P.banRoll = 0; P.banPitch = 0;
      P.legLf = P.legRf = 1.30; P.legLo = P.legRo = 0.12; P.legLk = P.legRk = 1.30;
      P.tailWrap = 1;
      P.eyeL = P.eyeR = 0;
      P.headPitch = -0.34 - 0.035 * sigh;
      P.headRoll = 0.14 * play;
      P.lean = 0.04;
      P.earL = P.earR = 0.1;
      P.orbGlow = 0.15;
      deepBreath = sigh;
      // 171 cycles a loop: a breath every 6 seconds.
      breathK = 171; breathDepth = 1.8; blinks = false;
    } else if (state === "error") {
      // Something went wrong: a still, concerned look - head tipped a
      // little and lowered, eyes down, brows drawn, ears back a touch; it
      // hangs almost still. Nothing comic (the owner's call, 2026-09-28).
      const g = restingGaze(t, S_GAZE);
      P.headRoll = -0.12 * play;
      P.headPitch = -0.10;
      P.earL = P.earR = 0.15;
      P.eyeL = P.eyeR = 0.8;
      P.brow = -0.3;
      P.lookX = g[0]; P.lookY = -0.3 + g[1];
      P.orbGlow = 0.35;
      blinkSlow = 1.4;
    } else if (state === "banked") {
      // Keeping things for later: dozing where it hangs, half-lidded,
      // blinking slowly, swinging a little - and now and then its head sinks
      // over three seconds before it catches itself.
      const e = happening(t, 16, 0.5, 5.5, S_EVENT, 0.55, 1);
      const x = e[1];
      const droop = e[0] === 0 ? (x < 3.2 ? smooth(clamp(x / 3.2, 0, 1)) : 1 - smooth(clamp((x - 3.2) / 0.8, 0, 1))) : 0;
      P.eyeL = P.eyeR = 0.35 * (1 - 0.7 * droop);
      P.headPitch = -0.15 - 0.12 * droop;
      P.earL = P.earR = 0.1;
      P.lookY = -0.2;
      P.orbGlow = 0.25;
      // 205 cycles a loop: a breath every 5 seconds.
      breathK = 205; blinkSlow = 2.5;
    } else {
      // idle: hangs and swings gently, looking about - the eyes first, the
      // head after - with a curious tilt of the head now and then; its legs
      // and tail trail the swing. Every 10 to 25 seconds it does one small
      // thing: most often kicks its legs, looks round at something or curls
      // its tail; now and then looks at its banana or swings a little
      // wider; once in a while scratches its head.
      const g = looks(t, S_GAZE, 1.2, 5, 0.35, 0.8, 0.25, 0, 0.08, 1.1, o);
      const ev = happening(t, SLOT, 0.5, 5.5, S_EVENT, CHANCE, EVENTS);
      const x = ev[1];
      let ex = g[0], ey = g[1], hx = g[2], hy = g[3];
      if (ev[0] === 4) {
        // Something to one side catches its ear: that ear turns first, then
        // head and eyes turn that way together; it looks, and comes back.
        const s = sideOf(ev[2]) < 0.5 ? -1 : 1;
        const ear = hap * 0.35 * envAHR(x, 0.25, 2.2, 0.8);
        if (s < 0) P.earL -= ear; else P.earR -= ear;
        const wh = hap * envAHR(x - 0.4, 0.9, 1.3, 0.9);
        ex += (s * 0.9 - ex) * wh; ey += (0.15 - ey) * wh;
        hx += (s * 0.75 - hx) * wh; hy += (0.1 - hy) * wh;
      }
      P.lean = sw * 0.015 * shift(t, S_LEAN);
      P.headYaw = 0.25 * hx;
      P.headPitch = 0.10 * hy + sw * 0.02 * wave(t, 97, 1.1);
      // The curious tilt: slow, and now and then a little further.
      P.headRoll = sw * (0.03 * wave(t, 71, 0.2) + 0.025 * shift(t, S_ROLL));
      P.lookX = ex - 0.4 * hx; P.lookY = ey - 0.4 * hy;
      P.earL += sw * 0.04 * wave(t, 131, 0); P.earR += sw * 0.04 * wave(t, 131, 2.3);
      P.bHy += sw * 0.008 * wave(t, 113, 0);
      if (ev[0] === 0) {
        // A scratch at the top of its head with its banana hand (the banana
        // goes along), head tipped into it, eyes half shut.
        scratch = hap * envAHR(x, 0.6, 1.5, 0.7);
        P.headRoll += 0.05 * scratch;
        eyeK = 1 - 0.45 * scratch;
      } else if (ev[0] === 1) {
        // Looks at its banana: lifts it in front of its face, tips its head
        // to one side, turns it a little, and lowers it again.
        peel = hap * envAHR(x, 0.8, 1.8, 0.9);
        P.lookX += (-0.35 - P.lookX) * peel; P.lookY += (-0.35 - P.lookY) * peel;
        P.headYaw += (-0.06 - P.headYaw) * peel;
        P.headPitch += (-0.08 - P.headPitch) * peel;
        P.headRoll += 0.05 * peel;
      } else if (ev[0] === 2) {
        // Kicks its legs, one then the other, a few times.
        const e = hap * envAHR(x, 0.4, 1.6, 0.6);
        P.legLf += 0.28 * e * (0.5 + 0.5 * wave(t, 700, 0));
        P.legRf += 0.28 * e * (0.5 + 0.5 * wave(t, 700, Math.PI));
        P.legLk -= 0.2 * e; P.legRk -= 0.2 * e;
      } else if (ev[0] === 5) {
        // Curls its tail tip tighter, and lets it go.
        P.tailCurl += hap * 0.9 * envAHR(x, 0.7, 1.0, 1.0);
      }
      turnBlink = g[4];
    }

    // The swing, and what trails it: the tail swings as the body did a
    // moment ago, further back along it (follow-through), and the legs
    // trail it a little. The head stays more level than the body.
    P.swing = swingAt(state, t, m);
    const s1 = swingAt(state, t - TAIL_LAG, m), s2 = swingAt(state, t - 2 * TAIL_LAG, m);
    const s3 = swingAt(state, t - 3 * TAIL_LAG, m), s4 = swingAt(state, t - 4 * TAIL_LAG, m);
    P.tail1 = 0.9 * (s1 - P.swing); P.tail2 = 1.4 * (s2 - P.swing); P.tail3 = 1.9 * (s3 - P.swing);
    P.tail4 = 2.4 * (s4 - P.swing);
    const tw = sw * 0.06 * wave(t, 77, 0.9);
    P.tail2 += tw; P.tail3 += 1.6 * tw; P.tail4 += 2.0 * tw;
    P.tailCurl += sw * 0.12 * wave(t, 59, 0.3);
    const legLag = 1.5 * (s2 - P.swing);
    P.legLo -= legLag; P.legRo += legLag;
    P.headRoll -= 0.4 * P.swing;

    // Breathing: the chest swells and the body lifts a little.
    const b = wave(t, breathK, 0) * (1 + 0.6 * deepBreath);
    P.breath = 1 + 0.02 * breathDepth * b;
    P.bob = 0.006 * breathDepth * b;

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
      // The banana hand goes to the top of its head, wherever the head has
      // turned, and scratches back and forth twice a second; on the way it
      // swings out round the side of the head (an arc, not through it).
      const q = onHead(P, [-0.24, 0.66 + 0.025 * wave(t, 2048, 0), -0.05]);
      const arc = 4 * scratch * (1 - scratch);
      P.bHx += (q[0] - P.bHx) * scratch - 0.14 * arc;
      P.bHy += (q[1] - P.bHy) * scratch;
      P.bHz += (q[2] - P.bHz) * scratch - 0.06 * arc;
      P.bEx += (-0.34 - P.bEx) * scratch; P.bEy += (0.26 - P.bEy) * scratch; P.bEz += (-0.02 - P.bEz) * scratch;
      P.banRoll += 1.2 * scratch;
    }
    if (peel > 0) {
      // Up in front of its face, the banana turned to show its side.
      P.bEx += (-0.26 - P.bEx) * peel; P.bEy += (0.02 - P.bEy) * peel; P.bEz += (-0.14 - P.bEz) * peel;
      P.bHx += (-0.14 - P.bHx) * peel; P.bHy += (0.10 - P.bHy) * peel; P.bHz += (-0.30 - P.bHz) * peel;
      P.banYaw += 0.25 * peel * wave(t, 160, 0); P.banRoll += 0.45 * peel;
    }

    // The banana rides in the hand holding it.
    const ban = banFrame(P);
    const off = apply(ban, BAN_AT);
    P.orbX = P.bHx + off[0]; P.orbY = P.bHy + off[1]; P.orbZ = P.bHz + off[2];

    const qk = 1 - (o.quiet || 0);
    const k = eyeK * (1 - qk * Math.max(blinks ? blinkAt(t, S_BLINK, blinkSlow, 2, 9) : 0, turnBlink));
    P.eyeL *= k; P.eyeR *= k;
    return P;
  }

  // Which way a happening starting at clock `at` looks, 0..1: a hash of its
  // slot's number (taken round, like every slot here), exact in both apps.
  function sideOf(at) { return C.hash01((Math.floor(at / SLOT) & 255) * 256 + S_EVENT + 3); }

  /** The banana's turn in the body's frame (yaw, then roll, then pitch). */
  function banFrame(P) { return mul(ry(-P.banYaw), mul(rz(P.banRoll), rx(P.banPitch))); }

  /**
   * The monkey's waking up and nodding off - see critter-pose.js's "Waking
   * up and falling asleep" and the panda's wakeSleep for what x, k, E and F
   * are.
   *
   * It sleeps sitting ON the vine and hangs from it awake, so going to sleep
   * it climbs up, and waking it slides back down. That move is not an extra:
   * it is the difference between the two poses, and the ordinary settling
   * (makePose) makes it, under calm, still and serious too - on screen the
   * picture follows the monkey, so the vine is what moves. Two things are
   * added to it:
   *
   *  - Always: the vine goes BEHIND the monkey while it passes (its head,
   *    body and legs), and comes forward again only under its seat - the
   *    settling alone would draw it straight through them. `passing` works
   *    out how far the settling has got, from its own half-lives.
   *  - The extras, played at E times k as the other animals' are, each
   *    starting from nothing: nodding off, it looks up at the vine, keeps
   *    hold with its hand until the vine is down at its middle, and lifts
   *    its legs over, curls its tail round and hugs its banana only once it
   *    is up, before its head droops; waking, a small stretch as it hangs
   *    (legs out, a deeper breath) and its ears flick.
   */
  // How far a settling with half-life hl has got, x seconds in (critically
  // damped, as makePose's offset(); 0 to 1).
  function settled(x, hl) {
    const y = 2 * 0.6931471805599453 / hl;
    return 1 - (1 + y * x) * Math.exp(-y * x);
  }
  /** How far behind the vine is, for how far the monkey is from hanging (0) to sitting (1). */
  function behind(s) { return ease(s / 0.25) * (1 - ease((s - 0.75) / 0.25)); }
  const VINE_BACK = 0.42;
  function passing(P, s, cut) {
    const b = VINE_BACK * behind(s) * cut;
    P.vineZ += b; P.hangZ -= b;
  }
  // Holds the pose's numbers `keys` back toward F's by w.
  function hold(P, F, keys, w) { for (const key of keys) P[key] = toward(P[key], F[key], w); }
  const LEGS = ["legLf", "legLo", "legLk", "legRf", "legRo", "legRk"];
  const TAILK = ["tailWrap", "tail1", "tail2", "tail3", "tail4", "tailCurl"];
  const HUG = ["aHx", "aHy", "aHz", "aEx", "aEy", "aEz", "bEx", "bEy", "bEz", "bHx", "bHy", "bHz", "orbX", "orbY", "orbZ",
               "banYaw", "banRoll", "banPitch"];
  const HEAD = ["headYaw", "headPitch", "headRoll"];
  function wakeSleep(P, state, x, k, E, t, F) {
    const e = E * k;
    if (state === "standby") {
      // Nodding off (3 s). The settling (half-life 0.18 s, five times
      // slower nodding off) carries it up; the vine passes behind.
      passing(P, 1 - k * (1 - settled(x, 0.9)), 1 - ease((x - 2.2) / 0.8));
      const lids = (1 - 0.35 * ease((x - 0.1) / 0.6)) * (1 - ease((x - 1.9) / 0.9));
      const lid = k * toward(eyesClose(x), lids, E);
      P.eyeL = F.eyeL * lid; P.eyeR = F.eyeR * lid;
      // Its hand keeps hold till the vine is down at its middle; its legs,
      // tail and banana wait till it is up; its head droops last.
      P.grip += e * F.grip * settled(x, 0.75) * (1 - ease((x - 1.0) / 0.7));
      hold(P, F, LEGS, e * settled(x, 1.1) * (1 - ease((x - 1.0) / 1.4)));
      hold(P, F, TAILK, e * settled(x, 1.1) * (1 - ease((x - 1.4) / 1.4)));
      hold(P, F, HUG, e * settled(x, 0.75) * (1 - ease((x - 1.2) / 1.4)));
      hold(P, F, HEAD, e * settled(x, 0.65) * (1 - ease((x - 1.6) / 1.2)));
      // A look up at the vine as it starts.
      const up = e * envAHR(x, 0.4, 0.5, 0.6);
      P.headPitch += 0.25 * up; P.lookY += 0.6 * up;
      return;
    }
    // Waking (2.2 s): the settling (2.5 times slower waking) brings it down
    // to hang again; the vine passes behind; a small stretch as it hangs,
    // and its ears flick.
    passing(P, k * (1 - settled(x, 0.45)), 1 - ease((x - 1.6) / 0.6));
    const lids = eyesOpen(x) * (1 - E * bump((x - 0.75) / 0.45));
    const f = 1 - k * (1 - lids);
    P.eyeL *= f; P.eyeR *= f;
    const s = e * envAHR(x - 1.2, 0.35, 0.2, 0.45);
    P.legLf += 0.25 * s; P.legRf += 0.25 * s; P.legLk -= 0.2 * s; P.legRk -= 0.2 * s;
    P.breath += 0.012 * s; P.headPitch += 0.06 * s;
    const flick = e * (bump((x - 1.2) / 0.5) - 0.3 * bump((x - 1.6) / 0.5));
    P.earL -= 0.3 * flick; P.earR -= 0.3 * flick;
  }

  const HALF = halfLives(
    ["eyeL", "eyeR", "lookX", "lookY"], ["speak"], ["headYaw", "headPitch", "headRoll", "brow"],
    ["aHx", "aHy", "aHz", "aEx", "aEy", "aEz", "bEx", "bEy", "bEz", "bHx", "bHy", "bHz", "orbX", "orbY", "orbZ",
     "banYaw", "banRoll", "banPitch", "grip"],
    ["earL", "earR", "legLf", "legLo", "legLk", "legRf", "legRo", "legRk",
     "tail1", "tail2", "tail3", "tail4", "tailCurl", "tailWrap"]);
  const pose = makePose(stateTargets, KEYS, HALF, wakeSleep);

  // The tail hanging (body frame, the last number its thickness there): down
  // from between its legs, bending a little to one side, into a hook at the
  // end - and wrapped round the vine as it sits.
  const TAIL_HANG = [
    [0.00, -0.16, 0.11, 0.036], [0.02, -0.33, 0.10, 0.032], [0.02, -0.50, 0.06, 0.030],
    [0.09, -0.62, 0.02, 0.028], [0.14, -0.54, 0.01, 0.026],
  ];
  const TAIL_WRAP = [
    [0.00, -0.16, 0.11, 0.036], [0.12, -0.23, 0.12, 0.032], [0.18, -0.335, 0.02, 0.030],
    [0.21, -0.26, -0.08, 0.028], [0.23, -0.19, -0.02, 0.026],
  ];
  const HIP_X = 0.085, HIP_Y = -0.13;

  /** A leg's knee and foot (body frame): forward swing f, out o, knee bend k. */
  function leg(side, f, o, k) {
    const so = Math.sin(o), co = Math.cos(o), f2 = f - k;
    const kn = [side * HIP_X + THIGH * side * so * Math.cos(f), HIP_Y - THIGH * co * Math.cos(f), -THIGH * Math.sin(f)];
    const ft = [kn[0] + SHIN * side * so * Math.cos(f2), kn[1] - SHIN * co * Math.cos(f2), kn[2] - SHIN * Math.sin(f2)];
    return [kn, ft];
  }
  /** The vine's centre at x (the shader's partVine, without its thickness). */
  function vineAt(P, x) {
    const dx = x - P.dipX;
    return P.vineY - 0.035 * x * x - P.dip / (1 + 18 * dx * dx);
  }
  const mixV = (a, b, w) => [a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w, a[2] + (b[2] - a[2]) * w];
  /**
   * Where the elbow of an arm of two ARM-long pieces goes, from shoulder
   * `a` to hand `b`, bending toward `pole` (world): halfway along, then out
   * from the line by about as much as the arm's length leaves over.
   */
  function bend(a, b, pole) {
    const d = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
    // (Its direction eased where the hand passes close by the shoulder -
    // the climb - so the elbow never swings round there in a moment.)
    const len = Math.hypot(d[0], d[1], d[2]), ul = Math.sqrt(len * len + 0.09);
    const u = [d[0] / ul, d[1] / ul, d[2] / ul];
    const k = pole[0] * u[0] + pole[1] * u[1] + pole[2] * u[2];
    const q = [pole[0] - k * u[0], pole[1] - k * u[1], pole[2] - k * u[2]];
    // (Out along the pole's part square to the arm, near enough its full
    // length while that part is big; when the arm lines up with the pole it
    // shrinks smoothly, rather than turning round in a frame.)
    const ql = Math.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + 0.09);
    // How far out: grows with the slack left in the arm, smoothly (a hard
    // "straight" limit made the elbow change speed in one frame), and never
    // more than ELBOW_MAX.
    const slack = 2 * ARM - len, g = 0.5 * (slack + Math.sqrt(slack * slack + 0.004));
    const h = ELBOW_MAX * Math.tanh(0.9 * g / ELBOW_MAX);
    return [a[0] + d[0] / 2 + q[0] / ql * h, a[1] + d[1] / 2 + q[1] / ql * h, a[2] + d[2] / 2 + q[2] / ql * h];
  }
  /** The body's frame and where its middle is (world). */
  function bodyOf(P) {
    const S = rz(P.swing);
    const B = mul(S, rx(-P.lean));
    const h = apply(S, [P.hangX, P.hangY, P.hangZ]);
    return [B, [GRIP_X + h[0], P.vineY + h[1] + P.bob, P.vineZ + h[2]]];
  }

  function uniforms(P, mouth) {
    const bo = bodyOf(P), B = bo[0], bodyPos = bo[1];
    const toWorld = (v) => add(bodyPos, apply(B, v));
    const H = mul(B, headTurn(P));
    // Arm A's hand: on the vine (a little below its middle and in front, so
    // the fingers wrap it), or wherever the pose puts it.
    const grip = clamp(P.grip, 0, 1);
    const free = toWorld([P.aHx, P.aHy, P.aHz]);
    const onVine = [GRIP_X, vineAt(P, GRIP_X) - 0.012, P.vineZ - 0.03];
    const handA = [free[0] + (onVine[0] - free[0]) * grip, free[1] + (onVine[1] - free[1]) * grip,
                   free[2] + (onVine[2] - free[2]) * grip];
    // Its elbow: while it holds the vine, where an arm of two ARM-long
    // pieces from its shoulder to its hand bends to, out to the side (POLE);
    // otherwise wherever the pose puts it.
    const shA = toWorld(SH_A);
    const elbA = mixV(toWorld([P.aEx, P.aEy, P.aEz]), bend(shA, handA, apply(B, POLE)), grip);
    const L = leg(-1, P.legLf, P.legLo, P.legLk), R = leg(1, P.legRf, P.legRo, P.legRk);
    const ban = mul(B, banFrame(P));
    // The tail: each point of the hanging tail turned round the root by
    // how far behind the swing it is, the hook curled by tailCurl, then
    // blended toward the tail wrapped round the vine.
    const tail = {};
    const turns = [0, P.tail1, P.tail2, P.tail3, P.tail4];
    const wrap = clamp(P.tailWrap, 0, 1), base = TAIL_HANG[0];
    let px = base[0], py = base[1];
    for (let i = 0; i < 5; i++) {
      const a = TAIL_HANG[i], c = TAIL_WRAP[i];
      let x = a[0], y = a[1];
      if (i > 0) {
        // Each segment of the hanging tail keeps its length and turns by
        // its own lag; the hook's two segments curl in by tailCurl.
        const p0 = TAIL_HANG[i - 1];
        const ang = turns[i] + (i >= 3 ? 0.5 * P.tailCurl : 0);
        const dx = a[0] - p0[0], dy = a[1] - p0[1], ca = Math.cos(ang), sa = Math.sin(ang);
        x = px + dx * ca - dy * sa; y = py + dx * sa + dy * ca;
      }
      px = x; py = y;
      const v = [x + (c[0] - x) * wrap, y + (c[1] - y) * wrap, a[2] + (c[2] - a[2]) * wrap];
      // (The thickness handed over is the segment's that starts here: the
      // average of its two ends, ready-made for the shader.)
      tail["uTail" + i] = [...toWorld(v), i < 4 ? 0.5 * (a[3] + TAIL_HANG[i + 1][3]) : a[3]];
    }
    return Object.assign({
      uBodyPos: bodyPos,
      uBodyR0: invRow(B, 0), uBodyR1: invRow(B, 1), uBodyR2: invRow(B, 2),
      uBreath: [P.breath],
      uNeck: toWorld(NECK),
      uHeadR0: invRow(H, 0), uHeadR1: invRow(H, 1), uHeadR2: invRow(H, 2),
      uFace: [clamp(P.eyeL, 0, 1.2), clamp(P.eyeR, 0, 1.2), P.brow],
      uMouth: mouthOf(P, mouth),
      uLook: [clamp(P.lookX, -1, 1), clamp(P.lookY, -1, 1)],
      uEars: [clamp(P.earL, -0.6, 0.6), clamp(P.earR, -0.6, 0.6)],
      uShA: shA,
      uElbA: elbA,
      uHandA: handA,
      uShB: toWorld(SH_B),
      uElbB: toWorld([P.bEx, P.bEy, P.bEz]),
      uHandB: toWorld([P.bHx, P.bHy, P.bHz]),
      uKneeL: L[0], uKneeR: R[0], uFootL: L[1], uFootR: R[1],
      uVine: [P.vineY, P.vineZ, P.dipX, P.dip],
      uBan0: invRow(ban, 0), uBan1: invRow(ban, 1), uBan2: invRow(ban, 2),
      uOrb: [...toWorld([P.orbX, P.orbY, P.orbZ]), P.orbR],
      uOrbGlow: [clamp(P.orbGlow, 0, 1.5)],
    }, tail);
  }

  // The monkey's camera (monkey.sksl): target x, y, z, distance, pitch.
  const CAM = [-0.08, 0.055, 0, 3.31, 0];
  const ZZ_AT = [0.30, 0.80, 0.0];
  /** Where its sleeping Zs rise from - see critter-pose.js's overlay(). */
  function overlay(P, view) {
    const bo = bodyOf(P);
    const at = add(bo[1], apply(bo[0], onHead(P, ZZ_AT)));
    return overlayAt(P, at, CAM, view);
  }

  /** Whether one of its idle happenings is playing at clock t (critter-pose.js playing()). */
  function busy(state, t) {
    return state === "idle" && C.util.playing(happening(t, SLOT, 0.5, 5.5, S_EVENT, CHANCE, EVENTS));
  }

  C.species.monkey = { KEYS, stateTargets, pose, uniforms, mouth: mouthOf, overlay, busy };
})(typeof globalThis !== "undefined" ? globalThis : this);
