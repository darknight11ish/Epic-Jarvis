/**
 * The pygmy owl's body language, for each of Jarvis's eight states.
 *
 * Loaded after critter-pose.js, which holds what every animal shares (the
 * blink, the settling from one state to the next, the rotation sums); this adds
 * the owl to CritterPose.species. The phone runs a line-for-line Kotlin copy
 * (OwlPose.kt), held to the same answers by tools/gen_critters.py's fixture
 * and CritterPoseTest, exactly as the red panda's is.
 *
 * Owls have no hands, so the orb floats beside the owl rather than being
 * held, and it is the head that does the talking: owls turn their heads
 * much further than we do, and this one does.
 *
 * Coordinates: x to the viewer's right, y up, the owl faces -z.
 */
(function (root) {
  "use strict";
  const C = root.CritterPose;
  const { makePose, halfLives, mouthOf, clamp, smooth, rx, ry, rz, mul, apply, add, invRow,
          wave, bump, envAHR, happening, beat, shift, looks, restingGaze, optsOf, mods, blinkAt,
          overlayAt } = C.util;

  const KEYS = [
    "headYaw", "headPitch", "headRoll", "neckDrop", "bob", "breath", "fluff",
    "eyeL", "eyeR", "brow", "speak", "lookX", "lookY", "wingL", "wingR",
    "orbA", "orbY", "orbD", "orbR", "orbGlow",
    "lean", "bodyRoll", "asleep",
  ];

  // The orb floats free, and is placed round the owl rather than across it:
  // orbA is its angle round the head's upright axis (0 at the owl's left -
  // the viewer's right - a quarter turn in front of its face), orbD how far
  // out from that axis it is, orbY its height (body frame). Settling from
  // one state's place to another's then goes ROUND the head, never through
  // it or across the face. ORB_AXIS_Z is where the axis stands.
  const ORB_AXIS_Z = -0.05;
  // Settling round the head, the orb never crosses this angle: a little to
  // the viewer's left of straight in front of the face. From anywhere on
  // the far side it goes round the back instead.
  const ORB_CUT = Math.PI / 2 + 0.3;
  // Where the orb hovers when nothing in particular is happening: low, to
  // the owl's left (the viewer's right) - x 0.50, z -0.30 - and its radius.
  const ORB_REST = [0.4636476, 0.30, 0.559017, 0.09];
  // Listening (x 0.42, z -0.40), and asleep (x 0.62, z -0.12).
  const ORB_LISTEN = [0.6947382, 0.45, 0.5467175];
  const ORB_SLEEP = [0.1122027, -0.02, 0.6239391];

  // The owl's own dice (see critter-pose.js's note on salts).
  const S_GAZE = 80, S_EVENT = 96, S_ROLL = 104, S_LEAN = 112, S_BEAT = 120, S_BLINK = 128;
  // Its idle happenings, and how often each comes up: the head tilts and the
  // slow blink most; the bigger ones (a ruffle, a wing lifted) less.
  const EVENTS = [14, 12, 12, 20, 20, 22];   // ruffle, wing left, wing right, tilt left, tilt right, slow blink

  /*
   * Thinking: the orb circles the head - one turn every 7 seconds (147
   * cycles a loop), round the right side, over the brow, round the left and
   * behind - and the owl tips its head a little and turns it to follow.
   * The orb rides high as it passes in front, so it crosses the brow, never
   * the eyes.
   *
   * It does not jump onto that circle wherever the clock happens to have it:
   * it comes up the owl's right-hand side (the side it rests on) and eases
   * into the circle over a few seconds, catching up the difference the short
   * way round - so arriving at "thinking" never sends the orb across the
   * face. (Leaving is looked after by how the orb settles: round the head,
   * never through the front of the face, and round faster than it sinks -
   * see ORB_CUT and HALF.)
   */
  const ORBIT_K = 147, ORBIT_R = 0.6, ORB_SIDE = -0.3, ORB_RISE_S = 0.8, ORB_JOIN_S = 4.0;
  const ORBIT_W = C.util.TAU * ORBIT_K / C.util.LOOP;   // radians a second
  // Where on the circle the orb is at clock t, `since` seconds into
  // thinking: [angle, height, radius, cos, sin]. `u` (0..1) is how much of
  // the full circle there is: less, under the calm, serious and still
  // options, when it circles in a small ring above the head instead.
  function orbit(t, since, u) {
    const s = Math.max(0, since), tc = t - s;
    // How far round the circle is from the side at the change, taken so that
    // halfway through joining it is the short way round (it may go back a
    // little to meet the circle rather than race ahead to catch it).
    const half = ORBIT_W * ORB_JOIN_S / 2;
    let d = C.util.phaseOf(tc, ORBIT_K) - ORB_SIDE + half;
    d = d - C.util.TAU * Math.round(d / C.util.TAU) - half;
    // It waits at the side while it rises, then eases round to meet the
    // circle. (Once it has, the circle itself: `s` can be huge - "long
    // settled" - and ORBIT_W * s is then no use to a 32-bit float.)
    const f = s >= ORB_JOIN_S ? C.util.phaseOf(t, ORBIT_K)
      : ORB_SIDE + (d + ORBIT_W * s) * C.util.ease(s / ORB_JOIN_S);
    const ca = Math.cos(f), sa = Math.sin(f);
    const r = 0.25 + (ORBIT_R - 0.25) * u;
    const y = 1.60 + (1.20 - 1.60) * u + (0.03 + 0.13 * u) * sa;
    const rise = C.util.ease(since / ORB_RISE_S);
    return [f, 0.55 + (y - 0.55) * rise, r, ca, sa];
  }

  function stateTargets(state, t, amp, look, since, o) {
    if (typeof since !== "number") since = 1e9;
    o = o || optsOf();
    const m = mods(o), hap = m[0], sw = m[2], play = m[3];
    const P = {
      headYaw: 0, headPitch: 0, headRoll: 0, neckDrop: 0, bob: 0, breath: 1, fluff: 1,
      eyeL: 1, eyeR: 1, brow: 0, speak: 0, lookX: 0, lookY: 0, wingL: 0, wingR: 0,
      orbA: ORB_REST[0], orbY: ORB_REST[1] + sw * 0.03 * wave(t, 228, 0), orbD: ORB_REST[2],
      orbR: ORB_REST[3], orbGlow: 0.55,
      lean: 0, bodyRoll: 0, asleep: state === "standby" ? 1 : 0,
    };
    // 284 cycles a loop: a breath every 3.6 seconds.
    let breathK = 284, breathDepth = 1, blinkSlow = 1.2, blinks = true, turnBlink = 0;
    let eyeK = 1, deepBreath = 0;

    if (state === "listening") {
      // The listening tilt, eyes wide, leaning in, the orb close. The eyes
      // stay on you. Its brows stay level: pygmyowl.sksl draws them as a V
      // that grows STEEPER - sterner - as `brow` rises, so a raised brow here
      // read as a glare, not as interest.
      const g = looks(t, S_GAZE, 2, 7, 0.8, 0.2, 0.1, 0, 0.04, 0.6, o);
      P.headRoll = play * 0.34 + sw * 0.025 * wave(t, 188, 0);
      P.headPitch = 0.05;
      P.headYaw = 0.15 * g[2];
      P.lean = 0.04;
      P.eyeL = P.eyeR = 1 + 0.12 * play;
      P.brow = 0.1;
      P.fluff = 1.02;
      P.lookX = g[0] - 0.7 * g[2]; P.lookY = 0.1 + g[1];
      P.orbA = ORB_LISTEN[0]; P.orbY = ORB_LISTEN[1]; P.orbD = ORB_LISTEN[2];
      P.orbGlow = 0.55 + 0.5 * amp;
      turnBlink = g[4];
    } else if (state === "thinking") {
      // The orb circles its head (orbit(), above), and the owl follows it -
      // a small tilt, and a turn of the head as it passes in front.
      const q = orbit(t, since, sw), ca = q[3], sa = q[4];
      P.orbA = q[0]; P.orbY = q[1]; P.orbD = q[2];
      P.orbR = 0.10;
      P.headRoll = sw * 0.26 * wave(t, 90, 0);
      // (Eased in as the orb comes round, so the head never starts turning
      // with a jolt.)
      P.headYaw = m[1] * 0.45 * ca * Math.max(0, sa) * smooth(clamp(sa / 0.3, 0, 1));
      P.headPitch = 0.14;
      P.lookX = (0.35 + 0.55 * sw) * ca; P.lookY = 0.45 - 0.1 * sw;
      P.brow = 0.1;
      P.orbGlow = 0.95 + 0.2 * wave(t, 424, 0);
    } else if (state === "speaking") {
      // Leans in; its eyes lead each look and its head follows only a
      // little. It talks in phrases - a nod, a small lift of a wing, a tilt,
      // at most one every two seconds, often none, never the same one twice
      // running and never just as its eyes move (see beat()). The beak
      // follows the mouth track of the words being heard (see
      // critter-pose.js's mouthOf); `speak` says how much of it to show.
      const g = looks(t, S_GAZE, 1.8, 6, 0.65, 0.5, 0.18, 0, 0.04, 0.6, o);
      const b = beat(t, S_BEAT, S_GAZE, 1.8, 6, 0.65);
      const x = b[1];
      P.speak = 1;
      P.lean = 0.04;
      P.headPitch = 0.03;
      P.headYaw = sw * 0.06 * wave(t, 111, 0) + 0.12 * g[2];
      P.headRoll = sw * 0.035 * wave(t, 93, 0.5);
      P.lookX = g[0] - 0.28 * g[2]; P.lookY = g[1] - 0.28 * g[3];
      P.brow = 0.1 + 0.1 * amp;
      P.orbGlow = 0.6 + 0.45 * amp;
      if (b[0] === 0) {
        P.headPitch -= hap * 0.07 * (bump(x / 0.7) - 0.3 * bump((x - 0.55) / 0.7));
        P.brow += hap * 0.15 * bump(x / 0.7);
      } else if (b[0] === 1) {
        // A wing lifts a little from its side, as a hand would.
        P.wingR += hap * 0.22 * envAHR(x, 0.4, 0.3, 0.6);
        P.headPitch -= hap * 0.025 * bump(x / 0.9);
      } else if (b[0] === 2) {
        P.headRoll += hap * play * 0.08 * bump(x / 1.2);
      }
      turnBlink = g[4];
    } else if (state === "approval") {
      // Waiting on you, perhaps on something serious: no wave, nothing cute
      // (the owner's call, 2026-09-28). It draws itself up - sleek
      // feathers, head a little higher - leans in and looks straight at
      // you, eyes a little wide and brows level (see listening), still. Only
      // its breathing moves, a slow blink, and its eyes' tiny darts.
      const g = restingGaze(t, S_GAZE);
      P.neckDrop = -0.02;
      P.fluff = 0.98;
      P.lean = 0.04;
      P.headPitch = 0.04;
      P.eyeL = P.eyeR = 1 + 0.05 * play;
      P.brow = 0.1;
      P.lookX = g[0]; P.lookY = g[1];
      P.orbGlow = 0.9;
      blinkSlow = 1.6;
    } else if (state === "standby") {
      // Asleep: fluffed up round, head sunk in, eyes shut to slits. Now and
      // then a sigh - one deeper breath, the head settling a little lower.
      // The orb rests low beside it, still.
      const e = happening(t, 16, 0.5, 5.5, S_EVENT, 0.35, 1);
      const sigh = e[0] === 0 ? bump(e[1] / 4.5) : 0;
      P.eyeL = P.eyeR = 0;
      P.fluff = 1.10;
      P.neckDrop = 0.08 + 0.015 * sigh;
      P.headPitch = -0.18 - 0.03 * sigh;
      P.headRoll = 0.10 * play;
      P.orbA = ORB_SLEEP[0]; P.orbY = ORB_SLEEP[1]; P.orbD = ORB_SLEEP[2];
      P.orbGlow = 0.15;
      deepBreath = sigh;
      breathK = 186; breathDepth = 1.8; blinks = false;
    } else if (state === "error") {
      // Something went wrong: a still, concerned look - head tipped a
      // little and lowered, eyes down, its brows' V flattened (a negative
      // `brow` lowers the V's outer ends more than its inner ones, which
      // reads as worried, not stern). Nothing comic (it used to squint one
      // eye and ruffle; the owner's call, 2026-09-28). Only its breathing
      // moves, and its eyes' tiny darts.
      const g = restingGaze(t, S_GAZE);
      P.headRoll = -0.15 * play;
      P.headPitch = -0.08;
      P.eyeL = P.eyeR = 0.8;
      P.brow = -1.5;
      P.lookX = g[0]; P.lookY = -0.25 + g[1];
      P.fluff = 1.03;
      P.orbGlow = 0.35;
      blinkSlow = 1.6;
    } else if (state === "banked") {
      // Fluffed and half-lidded, blinking slowly, and now and then nodding
      // off - the head sinks, and it catches itself.
      const e = happening(t, 16, 0.5, 5.5, S_EVENT, 0.55, 1);
      const x = e[1];
      const droop = e[0] === 0 ? (x < 3.2 ? smooth(clamp(x / 3.2, 0, 1)) : 1 - smooth(clamp((x - 3.2) / 0.8, 0, 1))) : 0;
      P.eyeL = P.eyeR = 0.35 * (1 - 0.7 * droop);
      P.headPitch = -0.12 - 0.12 * droop;
      P.neckDrop = 0.03 * droop;
      P.fluff = 1.05;
      P.lookY = -0.2;
      P.orbGlow = 0.25;
      breathK = 205; blinkSlow = 3;
    } else {
      // idle: an owl's survey of the room. Its eyes barely move in its head,
      // so the HEAD does the looking: it turns quickly to something new and
      // holds there, still, the way owls do. Its weight shifts on the
      // branch now and then. Every 10 to 30 seconds one small thing: most
      // often a curious tilt of the head or a long slow blink; now and then
      // a ruffle of its feathers or a wing lifted and resettled.
      const g = looks(t, S_GAZE, 1.5, 6, 0.35, 0.7, 0.25, 0, 0.04, 0.8, o);
      const ev = happening(t, 16, 0.5, 5.5, S_EVENT, 0.7, EVENTS);
      const x = ev[1];
      const roll = sw * 0.011 * shift(t, S_ROLL);
      P.bodyRoll = roll;
      P.lean = sw * 0.011 * shift(t, S_LEAN);
      P.headYaw = 0.40 * g[2];
      P.headPitch = 0.12 * g[3];
      P.headRoll = -0.5 * roll + sw * 0.04 * wave(t, 77, 0.3);
      P.lookX = g[0] - 0.8 * g[2]; P.lookY = g[1] - 0.8 * g[3];
      P.fluff = 1 + sw * 0.008 * wave(t, 61, 0);
      if (ev[0] === 0) {
        // A ruffle: it puffs up, gives a small shiver, and smooths down.
        const e = hap * envAHR(x, 0.45, 0.9, 1.25);
        P.fluff += 0.07 * e + hap * 0.012 * wave(t, 2048, 0) * bump((x - 0.4) / 1.0);
        P.neckDrop = 0.012 * e; P.headPitch -= 0.05 * e;
        eyeK = 1 - 0.3 * e;
      } else if (ev[0] === 1 || ev[0] === 2) {
        // A wing lifted a little and folded back, a touch past and settling.
        const s = ev[0] === 1 ? -1 : 1;
        const lift = hap * 0.42 * (bump(x / 1.1) + 0.25 * bump((x - 0.8) / 0.8));
        if (s < 0) P.wingL += lift; else P.wingR += lift;
        P.bodyRoll += hap * s * 0.008 * bump(x / 1.6);
      } else if (ev[0] === 3 || ev[0] === 4) {
        // A curious tilt of the head, held, and back.
        const s = ev[0] === 3 ? -1 : 1;
        P.headRoll += hap * s * 0.25 * envAHR(x, 0.5, 1.6, 0.9);
      } else if (ev[0] === 5) {
        // A long slow blink (a blink, so the options leave it be).
        eyeK = 1 - 0.85 * envAHR(x, 0.45, 0.35, 0.6);
      }
      turnBlink = g[4];
    }

    const b = wave(t, breathK, 0) * (1 + 0.6 * deepBreath);
    P.breath = 1 + 0.016 * breathDepth * b;
    P.bob = 0.006 * breathDepth * b;

    const w = state === "standby" ? 0 : clamp(look.w || 0, 0, 1);
    if (w > 0) {
      // An owl follows with its whole head - but mostly with its eyes here,
      // so a pointer moving about does not swing the head to and fro.
      const lx = clamp(look.x || 0, -1, 1), ly = clamp(look.y || 0, -1, 1);
      P.lookX += (lx - P.lookX) * w;
      P.lookY += (ly - P.lookY) * w;
      P.headYaw += m[1] * 0.3 * lx * w;
      P.headPitch += m[1] * 0.25 * ly * w;
    }

    // Owls blink slowly, and on their own clock (their own salt).
    const k = eyeK * (1 - Math.max(blinks ? blinkAt(t, S_BLINK, blinkSlow, 3, 12) : 0, turnBlink));
    P.eyeL *= k; P.eyeR *= k;
    return P;
  }

  // The orb floats: it drifts to a new place more slowly than anything else
  // - round the head (orbA is an angle, settling the short way round), and
  // round faster than it sinks, so leaving "thinking" it moves out past the
  // side of the head before it drops, rather than down across the face.
  const HALF = Object.assign(halfLives(
    ["eyeL", "eyeR", "lookX", "lookY"], ["speak"], ["headYaw", "headPitch", "headRoll", "neckDrop", "brow"],
    [], ["wingL", "wingR", "fluff"]), { orbA: [0.16, 0, ORB_CUT, 1], orbY: [0.55, 0, null, 1], orbD: [0.16, 0, null, 1] });
  const settle = makePose(stateTargets, KEYS, HALF);
  /**
   * The pose, with the orb's place also given across and in depth (orbX,
   * orbZ, body frame) for a drawing that reads it that way - the flat
   * picture drawn without a GPU.
   */
  function pose(state, prevState, since, t, amp, look, hist, opts) {
    const P = settle(state, prevState, since, t, amp, look, hist, opts);
    P.orbX = P.orbD * Math.cos(P.orbA);
    P.orbZ = ORB_AXIS_Z - P.orbD * Math.sin(P.orbA);
    return P;
  }

  const SEAT_Y = -0.93;

  // The head as a keep-out egg, in the head's frame: a little bigger than
  // pygmyowl.sksl's skull (0.48, 0.41, 0.41 round (0, 0.30, 0.02)) so it
  // takes in the eyes and the beak too.
  const KEEP_C = [0, 0.30, 0.0], KEEP_R = [0.49, 0.42, 0.46], KEEP_GAP = 0.03, KEEP_SOFT = 0.03;
  /**
   * The orb, pushed out if it would sink into the head. The orb floats free
   * (the owl's weight shifts do not carry it), and while it circles the
   * head in "thinking" the head is tipping and turning too - and in the
   * Faces window the pointer turns it further, which let the orb sink
   * about 4 cm into the head. Worked out on the final pose, so it holds
   * mid-change as well. The push eases in (it grows with the square of the
   * overlap at first), so the orb is nudged, never knocked.
   */
  function clearOfHead(orb, r, neck, H) {
    const rel = [orb[0] - neck[0], orb[1] - neck[1], orb[2] - neck[2]];
    const h = [0, 1, 2].map((i) => {
      const row = invRow(H, i);
      return row[0] * rel[0] + row[1] * rel[1] + row[2] * rel[2] - KEEP_C[i];
    });
    const q0 = [h[0] / KEEP_R[0], h[1] / KEEP_R[1], h[2] / KEEP_R[2]];
    const q1 = [q0[0] / KEEP_R[0], q0[1] / KEEP_R[1], q0[2] / KEEP_R[2]];
    const k0 = Math.hypot(q0[0], q0[1], q0[2]), k1 = Math.hypot(q1[0], q1[1], q1[2]);
    if (k1 < 1e-6) return orb;
    const gap = k0 * (k0 - 1) / k1 - r;
    const short = KEEP_GAP + KEEP_SOFT - gap;
    if (short <= 0) return orb;
    const push = short < 2 * KEEP_SOFT ? short * short / (4 * KEEP_SOFT) : short - KEEP_SOFT;
    // Outward from the head: the egg's own normal, turned back into the world.
    const n = apply(H, [q1[0] / k1, q1[1] / k1, q1[2] / k1]);
    return [orb[0] + n[0] * push, orb[1] + n[1] * push, orb[2] + n[2] * push];
  }

  function uniforms(P, mouth) {
    const bodyPos = [0, SEAT_Y + P.bob, 0];
    // Its weight shifts on the branch: a lean forward, a roll to the side,
    // both about its feet.
    const B = mul(rz(-P.bodyRoll), rx(-P.lean));
    const toWorld = (v) => add(bodyPos, apply(B, v));
    const neck = toWorld([0, 0.70 - P.neckDrop, -0.02]);
    const H = mul(B, mul(ry(-P.headYaw), mul(rx(P.headPitch), rz(-P.headRoll))));
    // A wing lifts out and up from its shoulder, round the axis pointing
    // back along the body.
    const wing = (lift, side) => rz(side * clamp(lift, 0, 1.6));
    const WL = wing(P.wingL, -1), WR = wing(P.wingR, 1);
    return {
      uOrb: [...clearOfHead(add(bodyPos, [P.orbD * Math.cos(P.orbA), P.orbY, ORB_AXIS_Z - P.orbD * Math.sin(P.orbA)]),
                            P.orbR, neck, H), P.orbR],
      uBodyPos: bodyPos,
      uBodyR0: invRow(B, 0), uBodyR1: invRow(B, 1), uBodyR2: invRow(B, 2),
      uBreath: [P.breath, P.fluff],
      uNeck: neck,
      uHeadR0: invRow(H, 0), uHeadR1: invRow(H, 1), uHeadR2: invRow(H, 2),
      uWingL0: invRow(WL, 0), uWingL1: invRow(WL, 1), uWingL2: invRow(WL, 2),
      uWingR0: invRow(WR, 0), uWingR1: invRow(WR, 1), uWingR2: invRow(WR, 2),
      uFace: [clamp(P.eyeL, 0, 1.2), clamp(P.eyeR, 0, 1.2), P.brow],
      uMouth: mouthOf(P, mouth),
      uLook: [clamp(P.lookX, -1, 1), clamp(P.lookY, -1, 1)],
      uOrbGlow: [clamp(P.orbGlow, 0, 1.5)],
    };
  }

  // The owl's camera (pygmyowl.sksl): target x, y, z, distance, pitch.
  const CAM = [0, -0.12, 0, 3.35, 0];
  /** Where its sleeping Zs rise from - see critter-pose.js's overlay(). */
  function overlay(P, view) {
    const bodyPos = [0, SEAT_Y + P.bob, 0];
    const B = mul(rz(-P.bodyRoll), rx(-P.lean));
    const neck = add(bodyPos, apply(B, [0, 0.70 - P.neckDrop, -0.02]));
    const H = mul(B, mul(ry(-P.headYaw), mul(rx(P.headPitch), rz(-P.headRoll))));
    return overlayAt(P, add(neck, apply(H, [0.30, 0.80, 0.02])), CAM, view);
  }

  C.species.pygmyowl = { KEYS, stateTargets, pose, uniforms, mouth: mouthOf, overlay };
})(typeof globalThis !== "undefined" ? globalThis : this);
