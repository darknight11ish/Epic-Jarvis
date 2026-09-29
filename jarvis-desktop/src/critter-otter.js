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
          wave, bump, envAHR, happening, happeningV, noise, breathWave, NONE4, playingV, beat, shift, looks, restingGaze, optsOf, mods, blinkAt,
          overlayAt, ease, toward, eyesOpen, eyesClose, TAU, gaze, NONE, ZERO2, AWAKE, focusOf, petOf, cuteOf,
          switchE, listenNod, phraseBeat, ackNodOf, ackGlowOf, focusEndOf, variant, arrivalOf, cuteAt,
          cuteQuiet, cuteBusy, fullTurn, lidSet, lidNod, lidWake, HELLO_S, GOODBYE_S } = C.util;

  const KEYS = [
    "headYaw", "headPitch", "headRoll", "bob", "rock", "tilt", "breath",
    "eyeL", "eyeR", "paddle", "speak", "lookX", "lookY",
    "pawLx", "pawLy", "pawLz", "pawRx", "pawRy", "pawRz",
    "orbX", "orbY", "orbZ", "orbR", "orbGlow", "ripple", "wave", "asleep",
    "lid", "lidSlope",   // the painted eyelid (uLid)
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
  // ...and for the new behaviours (critter-pose.js's "New behaviours").
  const S_LISTEN = 216, S_THINK = 219, S_FOCUS = 222, S_NOD = 234, S_PHRASE = 235, S_CUTE = 236;
  // ...and the otter's own seeds for the slow wander (critter-pose.js noise()): its talking sway and its breathing.
  const N_YAW = 24, N_ROLL = 25, N_BREATH = 26;
  // How long each cute moment lasts: rolling over in the water, juggling
  // its pebble from paw to paw.
  const CUTE_LEN = [6.8, 6.5];
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
    o = optsOf(o, t);
    const m = mods(o);
    // Idle: a focus session, and a cute moment while it plays, take the
    // happenings away.
    const cu = state === "idle" ? cuteAt(t, since, S_CUTE, CUTE_LEN) : NONE;
    const cw = cu[0] >= 0 ? cuteOf(o) : 0;
    const fw = state === "idle" ? focusOf(o) : 0;
    const fp = fw * (1 - 0.6 * o.calm);   // the focus pose itself: smaller under calm (the happenings still go by fw)
    // (and so do the stretch as a focus session ends, and being stroked)
    const fe = state === "idle" ? focusEndOf(t, o) : 0, pw = AWAKE[state] ? petOf(o) : 0;
    // (The idle happening of this slot, its size and thinning: critter-pose.js happeningV.)
    const evI = state === "idle" ? happeningV(t, 16, 0.5, 5.5, S_EVENT, 0.7, EVENTS, o.attention) : NONE4;
    m[0] *= (1 - fw) * (1 - cw * (cu[0] >= 0 ? cuteQuiet(cu[1], CUTE_LEN[cu[0]]) : 0)) * (1 - fe) * (1 - pw) * evI[3];
    const hap = m[0], sw = m[2], play = m[3];
    const P = {
      headYaw: 0, headPitch: 0, headRoll: 0, bob: 0, rock: 0, tilt: 0.10, breath: 1,
      eyeL: 1, eyeR: 1, paddle: 0, speak: 0, lookX: 0, lookY: 0,
      pawLx: -0.14, pawLy: 0.33, pawLz: -0.09, pawRx: -0.14, pawRy: 0.33, pawRz: 0.09,
      orbX: PEBBLE[0], orbY: PEBBLE[1], orbZ: PEBBLE[2], orbR: PEBBLE[3], orbGlow: 0.55, ripple: 0.010,
      // Where the rings on the water have spread to: every state shares it.
      // (391 cycles a loop: 2.4 radians a second, kept small for the GPU.)
      wave: 6.283185307179586 * (((t - 1024 * Math.floor(t / 1024)) / 1024 * 391) % 1),
      asleep: state === "standby" ? 1 : 0,
      lid: 0, lidSlope: 0,
    };
    // 244 cycles a loop: a breath every 4.2 seconds.
    let breathK = 244, breathDepth = 1, blinkSlow = 1, blinks = true, turnBlink = 0, calm = 1;
    let eyeK = 1, deepBreath = 0, paws = null, wash = 0, ackK = 1;

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
      // Now and then (variety): it tilts its head the other way, lifts it a
      // little closer, or gives a small kick of its feet.
      const v = variant(t, o, S_LISTEN, 0.4);
      if (v[0] === 0) P.headRoll -= 0.42 * play * v[1];
      else if (v[0] === 1) { P.headPitch += 0.06 * v[1]; P.tilt += 0.03 * v[1]; }
      else if (v[0] === 2) P.paddle += 0.5 * v[1] * (0.5 + 0.5 * wave(t, 1024, 0));
      // A small nod in your pauses (the head end lifting for the ear flick).
      const nd = listenNod(t, o, S_NOD);
      P.headPitch += nd[0]; P.headRoll += play * nd[1]; eyeK *= 1 - nd[2]; P.tilt += 0.02 * nd[3];
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
      // Now and then (variety): it rolls the pebble between its paws, looks
      // up at the sky, thinking, or holds the pebble up nearer its eyes.
      const v = variant(t, o, S_THINK, 0.5);
      if (v[0] === 0) {
        const r = 0.03 * v[1] * wave(t, 1536, 0);
        P.pawLx += r; P.pawRx -= r;
      } else if (v[0] === 1) {
        P.headPitch += 0.25 * v[1]; P.lookY += 0.9 * v[1];
      } else if (v[0] === 2) {
        P.orbY += 0.05 * v[1]; P.pawLy += 0.05 * v[1]; P.pawRy += 0.05 * v[1]; P.headPitch -= 0.06 * v[1];
      }
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
      // (With the host's phrase ends, the gestures land on them instead.)
      const b = o.phraseN >= 0 ? phraseBeat(t, o, S_PHRASE, S_GAZE, 1.8, 6, 0.65) : beat(t, S_BEAT, S_GAZE, 1.8, 6, 0.65);
      const x = b[1];
      ackK = b[0] >= 0 ? 1 - bump(clamp(x / 1.6, 0, 1)) : 1;
      P.speak = 1;
      P.tilt = 0.16;
      P.headPitch = 0.05;
      P.headYaw = sw * 0.05 * noise(t, N_YAW, 4) + 0.08 * g[2];
      P.headRoll = sw * 0.04 * noise(t, N_ROLL, 4);
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
      // The small reaction as it arrives (variety), then still. (Lying on
      // its back, leaning in is lifting its head end.)
      const ar = arrivalOf(state, o, since);
      P.headPitch += ar[0]; P.headRoll += play * ar[1]; P.tilt += ar[2] + 0.03 * ar[4]; eyeK *= 1 - ar[3];
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
      const ar = arrivalOf(state, o, since);
      P.headPitch += ar[0]; P.headRoll += play * ar[1]; P.tilt += ar[2] + 0.03 * ar[4]; eyeK *= 1 - ar[3];
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
      const ev = evI;
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
      if (fw > 0) {
        // Working beside you (a focus session): it settles to look at the
        // pebble on its chest, and looks about far less.
        const f = gaze(t, S_FOCUS, 4, 12, 0.75, 0.3, 0.12, 0, 0.03, 1.6);
        P.headYaw += (0.2 * f[2] - P.headYaw) * fp;
        P.headPitch += (-0.22 + 0.1 * f[3] - P.headPitch) * fp;
        P.lookX += (0.3 + f[0] - 0.4 * f[2] - P.lookX) * fp;
        P.lookY += (-0.6 + f[1] - 0.4 * f[3] - P.lookY) * fp;
        turnBlink *= 1 - fp;
      }
      // The small stretch in the water as a focus session ends.
      if (fe > 0) { stretch(P, fe); eyeK *= 1 - 0.4 * fe; deepBreath = Math.max(deepBreath, fe); }
      if (cw > 0 && cu[0] === 0) {
        // Cute moment: it rolls right over in the water, pebble held to its
        // chest, eyes shut as its face goes under, and bobs up the right way
        // - the rings spreading. (Under calm, only a small roll to one side
        // and back: a whole turn cannot be made smaller - see fullTurn.)
        const x = cu[1];
        P.rock += fullTurn(x, 0.8, 4.8, CUTE_LEN[0], cw) + 0.25 * cw * (1 - smooth(clamp((cw - 0.8) / 0.2, 0, 1))) * bump((x - 0.8) / 4.8);
        eyeK *= 1 - cw * envAHR(x - 2.0, 0.5, 1.6, 0.6);
        P.ripple += 0.008 * cw * bump((x - 1.0) / 5.5);
        turnBlink *= 1 - cw * envAHR(x, 0.6, 5.4, 0.8);
      } else if (cw > 0 && cu[0] === 1) {
        // Cute moment: it juggles its pebble from paw to paw over its chest,
        // a little arc each way, its eyes following - and catches it.
        const x = cu[1], j = cw * envAHR(x, 0.8, 4.6, 1.0);
        const s = Math.sin(TAU * 0.55 * (x - 0.8)), c = 1 - s * s;
        P.orbZ += 0.10 * j * s; P.orbY += j * (0.03 + 0.09 * c);
        P.pawLz += (-0.13 - P.pawLz) * j; P.pawRz += (0.13 - P.pawRz) * j;
        P.pawLy += j * (0.03 + 0.05 * Math.max(0, -s)); P.pawRy += j * (0.03 + 0.05 * Math.max(0, s));
        P.lookY += (-0.3 - 0.4 * s - P.lookY) * j; P.lookX += (0.2 - P.lookX) * j;
        P.headPitch += (-0.12 - P.headPitch) * j;
        turnBlink *= 1 - j;
      }
    }

    // Stroked (petting): it rolls a little toward your hand and leans its
    // head into it, eyes half shut, its feet giving a happy little kick.
    if (pw > 0) {
      P.rock += 0.05 * pw * o.petX;
      P.headRoll += pw * play * (0.10 * o.petX + 0.03 * o.petDir);
      P.headPitch += 0.03 * pw;
      P.paddle += 0.3 * pw * (0.5 + 0.5 * wave(t, 700, 0));
      eyeK *= 1 - 0.5 * pw;
    }
    // A fact saved: one small nod, its head end lifting a touch. A long answer
    // ready: the pebble glows up once.
    const an = AWAKE[state] ? ackNodOf(t, o) : ZERO2;
    P.headPitch += ackK * an[0]; P.tilt += 0.02 * ackK * an[1];
    const gl = AWAKE[state] ? ackGlowOf(t, o) : 0;
    P.orbGlow += 0.4 * gl; P.orbR *= 1 + 0.12 * gl;

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
    const b = breathWave(t, breathK, N_BREATH) * (1 + 0.6 * deepBreath);
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
    farewell(P, state, o);
    lidSet(P, state);

    const q = 1 - o.quiet;
    const k = eyeK * (1 - q * Math.max(blinks ? blinkAt(t, S_BLINK, blinkSlow, 2, 10) : 0, turnBlink));
    P.eyeL *= k; P.eyeR *= k;
    return P;
  }

  /**
   * Hello and goodbye (critter-pose.js's farewell says how they work). The
   * otter's goodbye is a little wave of its paw, looking at you, then it
   * dives under the water; its hello, it pops back up with a splash of
   * rings, a small bob past the surface, and looks at you. Asleep or dozing:
   * no wave, no look. Waiting on you or at an error: none of it, the host's
   * cross-fade (switchE).
   */
  const DIVE = 0.6;   // how far under it goes: hidden by the water, not so deep it shows below the pool
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
      const wv = a * awake;
      P.pawRx -= 0.16 * wv; P.pawRy += 0.20 * wv; P.pawRz += 0.10 * wv + 0.05 * wv * Math.sin(TAU * 1.6 * g);
      const d = E * ease((g - 0.4) / 0.6);
      P.bob -= DIVE * d; P.tilt -= 0.2 * d;
      P.ripple += 0.01 * E * bump((g - 0.45) / 0.55);
    }
    if (h < 1) {
      const d = E * (1 - ease(h / 0.45));
      P.bob -= DIVE * d - E * 0.035 * bump((h - 0.3) / 0.45); P.tilt -= 0.2 * d;
      P.ripple += 0.012 * E * bump((h - 0.1) / 0.8);
      const at = E * awake * ease((h - 0.25) / 0.25) * (1 - ease((h - 0.8) / 0.2));
      P.lookX += (0 - P.lookX) * at; P.lookY += (0 - P.lookY) * at;
      P.headYaw += (0 - P.headYaw) * at;
    }
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
      // The painted lid comes down with the eyes' drooping, not with the squint of the stretch laid on it.
      const droop = (1 - 0.35 * ease((x - 0.2) / 0.8)) * (1 - ease((x - 1.4) / 0.8));
      lidNod(P, F, 1 - k * toward(eyesClose(x), droop, E));
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
    lidWake(P, x, k);   // ...and lifts a little after they open
  }

  // (rock is an angle: rolled right over, it settles the short way round.)
  const HALF = Object.assign(halfLives(
    ["eyeL", "eyeR", "lookX", "lookY"], ["speak"], ["headYaw", "headPitch", "headRoll"],
    ["pawLx", "pawLy", "pawLz", "pawRx", "pawRy", "pawRz", "orbX", "orbY", "orbZ"], ["paddle"]),
    { rock: [0.18, 0, Math.PI] });   // (0.18: HL_BODY, as before)
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
      uLid: [clamp(P.lid, 0, 1), clamp(P.lidSlope, -1, 1)],
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
  function busy(state, t, since, opts) {
    return state === "idle" && (playingV(happeningV(t, 16, 0.5, 5.5, S_EVENT, 0.7, EVENTS, opts ? optsOf(opts, t).attention : 1))
      || cuteBusy(t, since, opts, S_CUTE, CUTE_LEN));
  }

  /** Whether one of its own talking gestures is playing at clock t (critter-pose.js gesturing()). */
  function gesturing(t) {
    const b = beat(t, S_BEAT, S_GAZE, 1.8, 6, 0.65);
    return b[0] >= 0 && b[1] >= 0 && b[1] < C.util.GESTURE_S;
  }

  C.species.seaotter = { KEYS, stateTargets, pose, uniforms, mouth: mouthOf, overlay, busy, gesturing, HELLO_S, GOODBYE_S };
})(typeof globalThis !== "undefined" ? globalThis : this);
