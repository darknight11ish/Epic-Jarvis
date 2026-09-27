/**
 * The pygmy owl's body language, for each of Jarvis's eight states.
 *
 * Loaded after critter-pose.js, which holds what every animal shares (the
 * blink, the melt from one state to the next, the rotation sums); this adds
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
  const { makePose, clamp, rx, ry, rz, mul, apply, add, invRow } = C.util;
  const TAU = Math.PI * 2;

  const KEYS = [
    "headYaw", "headPitch", "headRoll", "neckDrop", "bob", "breath", "fluff",
    "eyeL", "eyeR", "brow", "beak", "lookX", "lookY", "wingL", "wingR",
    "orbX", "orbY", "orbZ", "orbR", "orbGlow",
  ];

  // Where the orb hovers when nothing in particular is happening: low, to
  // the owl's left (the viewer's right), in the body's frame.
  const ORB_REST = [0.50, 0.30, -0.30, 0.09];

  function stateTargets(state, t, amp, look) {
    const P = {
      headYaw: 0, headPitch: 0, headRoll: 0, neckDrop: 0, bob: 0, breath: 1, fluff: 1,
      eyeL: 1, eyeR: 1, brow: 0, beak: 0, lookX: 0, lookY: 0, wingL: 0, wingR: 0,
      orbX: ORB_REST[0], orbY: ORB_REST[1] + 0.03 * Math.sin(t * 1.4), orbZ: ORB_REST[2],
      orbR: ORB_REST[3], orbGlow: 0.55,
    };
    let breathPeriod = 3.6, breathDepth = 1, blinks = true;

    if (state === "listening") {
      // The listening tilt, eyes wide, leaning in.
      P.headRoll = 0.34 + 0.03 * Math.sin(t * 1.2);
      P.headPitch = 0.05;
      P.eyeL = P.eyeR = 1.12;
      P.brow = 0.8;
      P.fluff = 1.02;
      P.lookY = 0.1;
      P.headYaw = 0.12 * amp * Math.sin(t * 9.0);
      P.orbX = 0.42; P.orbY = 0.45; P.orbZ = -0.40;
      P.orbGlow = 0.55 + 0.5 * amp;
    } else if (state === "thinking") {
      // The orb circles slowly in front, and the owl tips its head right over
      // to follow it - the owl's own "thinking face".
      // It passes behind the head and round again, and the head follows it.
      const a = t * 0.9;
      P.orbX = 0.78 * Math.cos(a); P.orbY = 1.02 + 0.08 * Math.sin(a * 2.0);
      P.orbZ = -0.05 - 0.70 * Math.sin(a);
      P.orbR = 0.10;
      P.headRoll = 0.55 * Math.sin(t * 0.55);
      P.headYaw = 0.45 * Math.cos(a) * Math.max(0, Math.sin(a));
      P.headPitch = 0.12;
      P.lookX = 0.9 * Math.cos(a); P.lookY = 0.35;
      P.brow = 0.3;
      P.orbGlow = 0.95 + 0.2 * Math.sin(t * 2.6);
    } else if (state === "speaking") {
      // The beak rides Jarvis's voice, with a nod.
      P.beak = clamp(amp * 1.4, 0, 1);
      P.headPitch = 0.04 + 0.08 * amp;
      P.headYaw = 0.10 * Math.sin(t * 0.7);
      P.headRoll = 0.05 * Math.sin(t * 0.9);
      P.brow = 0.3 + 0.3 * amp;
      P.orbGlow = 0.6 + 0.45 * amp;
    } else if (state === "approval") {
      // Waiting on you: looks straight at you and waves a wing.
      P.wingR = 1.25 + 0.30 * Math.sin(t * 6.0);
      P.eyeL = P.eyeR = 1.1;
      P.brow = 0.9;
      P.headRoll = -0.10;
      P.orbGlow = 0.9;
    } else if (state === "standby") {
      // Asleep: fluffed up round, head sunk in, eyes shut to slits.
      P.eyeL = P.eyeR = 0;
      P.fluff = 1.10;
      P.neckDrop = 0.08;
      P.headPitch = -0.18;
      P.headRoll = 0.10;
      P.orbX = 0.62; P.orbY = -0.02; P.orbZ = -0.12;
      P.orbGlow = 0.15;
      breathPeriod = 5.5; breathDepth = 1.8; blinks = false;
    } else if (state === "error") {
      // Puzzled: a hard head tilt, one eye squinting, wings half out.
      P.headRoll = -0.45;
      P.headPitch = 0.10;
      P.eyeL = 0.45; P.eyeR = 1.05;
      P.brow = -0.4;
      P.lookY = 0.3;
      P.wingL = 0.35; P.wingR = 0.35;
      P.fluff = 1.04 + 0.01 * Math.sin(t * 11.0);
      P.orbGlow = 0.35;
    } else if (state === "banked") {
      P.eyeL = P.eyeR = 0.35;
      P.headPitch = -0.12;
      P.fluff = 1.05;
      P.lookY = -0.2;
      P.orbGlow = 0.25;
      breathPeriod = 5.0;
    } else {
      // idle: an owl's slow survey of the room, with the odd quick look over
      // its shoulder.
      P.lookX = 0.55 * Math.sin(t * 0.29) + 0.25 * Math.sin(t * 0.77 + 1.3);
      P.lookY = 0.15 * Math.sin(t * 0.43);
      const glance = Math.max(0, Math.sin(t * 0.21 - 1.0));
      P.headYaw = 0.45 * P.lookX + 0.55 * Math.pow(glance, 8);
      P.headPitch = 0.08 * P.lookY;
      P.headRoll = 0.05 * Math.sin(t * 0.37);
    }

    const b = Math.sin((t * TAU) / breathPeriod);
    P.breath = 1 + 0.016 * breathDepth * b;
    P.bob = 0.008 * breathDepth * b;

    const w = state === "standby" ? 0 : clamp(look.w || 0, 0, 1);
    if (w > 0) {
      // An owl follows with its whole head, so the pointer turns it further
      // than it turns the panda.
      const lx = clamp(look.x || 0, -1, 1), ly = clamp(look.y || 0, -1, 1);
      P.lookX += (lx - P.lookX) * w;
      P.lookY += (ly - P.lookY) * w;
      P.headYaw += 0.7 * lx * w;
      P.headPitch += 0.25 * ly * w;
    }

    if (blinks) {
      const k = 1 - C.blink(t);
      P.eyeL *= k; P.eyeR *= k;
    }
    return P;
  }

  const pose = makePose(stateTargets, KEYS);

  const SEAT_Y = -0.93;

  function uniforms(P) {
    const bodyPos = [0, SEAT_Y + P.bob, 0];
    const B = rx(0);
    const toWorld = (v) => add(bodyPos, apply(B, v));
    const neck = toWorld([0, 0.70 - P.neckDrop, -0.02]);
    const H = mul(B, mul(ry(-P.headYaw), mul(rx(P.headPitch), rz(-P.headRoll))));
    // A wing lifts out and up from its shoulder, round the axis pointing
    // back along the body.
    const wing = (lift, side) => rz(side * clamp(lift, 0, 1.6));
    const WL = wing(P.wingL, -1), WR = wing(P.wingR, 1);
    return {
      uBodyPos: bodyPos,
      uBodyR0: invRow(B, 0), uBodyR1: invRow(B, 1), uBodyR2: invRow(B, 2),
      uBreath: [P.breath, P.fluff],
      uNeck: neck,
      uHeadR0: invRow(H, 0), uHeadR1: invRow(H, 1), uHeadR2: invRow(H, 2),
      uWingL0: invRow(WL, 0), uWingL1: invRow(WL, 1), uWingL2: invRow(WL, 2),
      uWingR0: invRow(WR, 0), uWingR1: invRow(WR, 1), uWingR2: invRow(WR, 2),
      uFace: [clamp(P.eyeL, 0, 1.2), clamp(P.eyeR, 0, 1.2), P.brow, clamp(P.beak, 0, 1)],
      uLook: [clamp(P.lookX, -1, 1), clamp(P.lookY, -1, 1)],
      uOrb: [...toWorld([P.orbX, P.orbY, P.orbZ]), P.orbR],
      uOrbGlow: [clamp(P.orbGlow, 0, 1.5)],
    };
  }

  C.species.pygmyowl = { KEYS, stateTargets, pose, uniforms };
})(typeof globalThis !== "undefined" ? globalThis : this);
