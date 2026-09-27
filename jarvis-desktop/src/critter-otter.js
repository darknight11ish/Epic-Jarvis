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
  const { makePose, clamp, rx, ry, rz, mul, apply, add, invRow } = C.util;
  const TAU = Math.PI * 2;

  const KEYS = [
    "headYaw", "headPitch", "headRoll", "bob", "rock", "tilt", "breath",
    "eyeL", "eyeR", "paddle", "mouth", "lookX", "lookY",
    "pawLx", "pawLy", "pawLz", "pawRx", "pawRy", "pawRz",
    "orbX", "orbY", "orbZ", "orbR", "orbGlow", "ripple", "wave",
  ];

  const NECK = [-0.60, 0.14, 0.0];
  // The head at rest is turned up toward the camera and a little toward the
  // middle of the picture; the state's own turn adds to this.
  const HEAD_BASE_YAW = 0.30, HEAD_BASE_PITCH = 0.62;
  // The pebble on its chest, and the paws that hold it (body frame).
  const PEBBLE = [-0.12, 0.34, 0.0, 0.075];

  // The head's own turn, as a matrix (without the body's).
  function headTurn(P) {
    return mul(ry(-(HEAD_BASE_YAW + P.headYaw)), mul(rx(HEAD_BASE_PITCH + P.headPitch), rz(-P.headRoll)));
  }
  // A point given in the head's frame, in the body's frame: so a paw can be
  // sent to a cheek or over an eye wherever the head happens to be.
  function onHead(P, v) { return add(NECK, apply(headTurn(P), v)); }

  function stateTargets(state, t, amp, look) {
    const P = {
      headYaw: 0, headPitch: 0, headRoll: 0, bob: 0, rock: 0, tilt: 0.10, breath: 1,
      eyeL: 1, eyeR: 1, paddle: 0, mouth: 0, lookX: 0, lookY: 0,
      pawLx: -0.14, pawLy: 0.33, pawLz: -0.09, pawRx: -0.14, pawRy: 0.33, pawRz: 0.09,
      orbX: PEBBLE[0], orbY: PEBBLE[1], orbZ: PEBBLE[2], orbR: PEBBLE[3], orbGlow: 0.55, ripple: 0.010,
      // Where the rings on the water have spread to: every state shares it.
      wave: t * 2.4,
    };
    let breathPeriod = 4.2, breathDepth = 1, blinks = true, paws = null;

    if (state === "listening") {
      // Head up and tilted, paws to its cheeks.
      P.tilt = 0.24;
      P.headPitch = 0.12;
      P.headRoll = 0.28 + 0.03 * Math.sin(t * 1.3);
      P.eyeL = P.eyeR = 1.12;
      P.orbY = 0.30;
      P.orbGlow = 0.55 + 0.5 * amp;
      paws = "cheeks";
    } else if (state === "thinking") {
      // Taps the pebble on its belly, watching it.
      const tap = Math.pow(Math.max(0, Math.sin(t * 7.0)), 3);
      P.orbY = PEBBLE[1] + 0.07 * tap;
      P.pawLy = P.pawRy = 0.33 + 0.07 * tap;
      P.headPitch = -0.30;
      P.headRoll = 0.10 * Math.sin(t * 0.6);
      P.lookY = -0.7; P.lookX = 0.3;
      P.orbGlow = 0.95 + 0.2 * Math.sin(t * 2.6);
    } else if (state === "speaking") {
      P.mouth = clamp(amp * 1.35, 0, 1);
      P.headPitch = 0.04 + 0.08 * amp;
      P.headYaw = 0.08 * Math.sin(t * 0.7);
      P.headRoll = 0.06 * Math.sin(t * 0.9);
      P.pawRx = -0.22; P.pawRy = 0.42 + 0.08 * amp; P.pawRz = 0.14;
      P.orbGlow = 0.6 + 0.45 * amp;
    } else if (state === "approval") {
      // Waiting on you: looks at you and waves a paw in the air.
      P.pawRx = -0.32 + 0.07 * Math.sin(t * 5.0); P.pawRy = 0.52 + 0.03 * Math.sin(t * 10.0); P.pawRz = 0.10;
      P.eyeL = P.eyeR = 1.1;
      P.headPitch = 0.10;
      P.orbGlow = 0.9;
    } else if (state === "standby") {
      // Asleep, drifting, paws over its eyes.
      P.tilt = 0.04;
      P.headPitch = 0.10;
      P.eyeL = P.eyeR = 0;
      P.orbGlow = 0.15;
      P.ripple = 0.005;
      breathPeriod = 6.0; breathDepth = 1.8; blinks = false;
      paws = "eyes";
    } else if (state === "error") {
      // Puzzled: the pebble has slipped to one side, one paw scratches its
      // head, and it squints.
      P.headRoll = -0.30;
      P.headPitch = 0.10;
      P.eyeL = 0.55; P.eyeR = 0.9;
      P.lookY = 0.3;
      P.orbX = 0.12; P.orbY = 0.26; P.orbZ = 0.20;
      P.orbGlow = 0.35;
      paws = "scratch";
    } else if (state === "banked") {
      P.eyeL = P.eyeR = 0.35;
      P.headPitch = -0.10;
      P.orbGlow = 0.25;
      breathPeriod = 5.0;
    } else {
      // idle: rocks on the water, looks about, and paddles now and then.
      P.lookX = 0.55 * Math.sin(t * 0.31) + 0.25 * Math.sin(t * 0.83 + 1.3);
      P.lookY = 0.15 * Math.sin(t * 0.47);
      P.headYaw = 0.25 * P.lookX;
      P.headPitch = 0.08 * P.lookY;
      P.headRoll = 0.06 * Math.sin(t * 0.4);
      P.paddle = Math.pow(Math.max(0, Math.sin(t * 0.7)), 4) * (0.5 + 0.5 * Math.sin(t * 6.0));
    }

    // Floating: the whole otter bobs and rocks with the water.
    const swell = Math.sin(t * 1.1);
    P.bob = 0.018 * swell;
    P.rock += 0.05 * Math.sin(t * 0.8 + 0.6);
    const b = Math.sin((t * TAU) / breathPeriod);
    P.breath = 1 + 0.02 * breathDepth * b;

    const w = state === "standby" ? 0 : clamp(look.w || 0, 0, 1);
    if (w > 0) {
      const lx = clamp(look.x || 0, -1, 1), ly = clamp(look.y || 0, -1, 1);
      P.lookX += (lx - P.lookX) * w;
      P.lookY += (ly - P.lookY) * w;
      P.headYaw += 0.35 * lx * w;
      P.headPitch += 0.2 * ly * w;
    }

    // Paws that go to the head are placed after the head has turned.
    if (paws === "cheeks") {
      [P.pawLx, P.pawLy, P.pawLz] = onHead(P, [-0.24, -0.08, -0.10]);
      [P.pawRx, P.pawRy, P.pawRz] = onHead(P, [0.24, -0.08, -0.10]);
    } else if (paws === "eyes") {
      [P.pawLx, P.pawLy, P.pawLz] = onHead(P, [-0.10, 0.05, -0.25]);
      [P.pawRx, P.pawRy, P.pawRz] = onHead(P, [0.10, 0.05, -0.25]);
    } else if (paws === "scratch") {
      const s = 0.02 * Math.sin(t * 9.0);
      [P.pawLx, P.pawLy, P.pawLz] = onHead(P, [-0.25 + s, 0.14, 0.02]);
    }

    if (blinks) {
      const k = 1 - C.blink(t);
      P.eyeL *= k; P.eyeR *= k;
    }
    return P;
  }

  const pose = makePose(stateTargets, KEYS);

  const WATER_Y = -0.42;

  function uniforms(P) {
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
      uFace: [clamp(P.eyeL, 0, 1.2), clamp(P.eyeR, 0, 1.2), clamp(P.paddle, 0, 1), clamp(P.mouth, 0, 1)],
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

  C.species.seaotter = { KEYS, stateTargets, pose, uniforms };
})(typeof globalThis !== "undefined" ? globalThis : this);
