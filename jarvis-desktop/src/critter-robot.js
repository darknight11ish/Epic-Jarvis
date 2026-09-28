/**
 * The robot's body language, for each of Jarvis's eight states.
 *
 * Loaded after critter-pose.js, like the animals' files; adds the robot to
 * CritterPose.species. The phone runs a line-for-line Kotlin copy
 * (RobotPose.kt), held to the same answers by tools/gen_critters.py's
 * fixture and CritterPoseTest.
 *
 * The owner's fifth face (2026-09-28), from their own picture: a small cute
 * robot that floats, with a big glossy visor on its helmet of a head. It has
 * NO MOUTH: its glowing eyes on the visor are its face. They carry the
 * state's colour (the shader's uHot - the colour the animals' orbs glow in)
 * and the expression: happy arcs at rest, wide round eyes listening,
 * narrowed eyes looking up and scanning while it thinks, bright eyes that
 * pulse with the real voice while it speaks, steady eyes waiting on you, a
 * small concerned slant at an error, heavy lids dozing, a sleeping line on
 * standby. Its ear fins and its mitten arms show the state too.
 *
 * Now and then at rest it ZIPS round inside its own space - a quick, eased
 * dash to another spot, a little loop, and back - and its two cute moments
 * take turns (critter-pose.js's cuteAt): a friendly wave, and polishing its
 * visor (a gleam crosses the glass when it is done). Never across the
 * screen, never under "Still", calm motion or a serious moment, and never
 * while waiting on you or at an error: those stay attentive and still.
 *
 * It does every new behaviour the animals do (critter-pose.js's "New
 * behaviours": variants, listening nods, phrase-end gestures, the fact-saved
 * nod and the long-answer glow - its eyes and fins, having no orb - petting,
 * the focus buddy, hello and goodbye), with the same options and timing.
 *
 * The same limits as the animals: every movement eased, nothing big faster
 * than a few times a second, looks held at least 0.6 s, gestures in phrases.
 *
 * Frames. World: x to the viewer's right, y up, the robot faces -z. The
 * body's own frame has its origin in the middle of its egg of a body; the
 * whole robot turns about it. The head turns on its own about the neck.
 */
(function (root) {
  "use strict";
  const C = root.CritterPose;
  const { makePose, halfLives, mouthOf, clamp, ease, rx, ry, rz, mul, apply, add, invRow,
          wave, bump, envAHR, happening, chain, shift, gaze, looks, restingGaze, optsOf, mods, blinkAt,
          overlayAt, toward, eyesClose, TAU, NONE, ZERO2, AWAKE, focusOf, petOf, cuteOf, varOf, switchE,
          listenNod, phraseBeat, ackNodOf, ackGlowOf, focusEndOf, variant, cuteAt, cuteQuiet, cuteBusy,
          HELLO_S, GOODBYE_S } = C.util;
  const hash01 = C.hash01;

  const KEYS = [
    "posX", "posY", "posZ", "yaw", "roll", "pitch",
    "headYaw", "headPitch", "headRoll",
    "eyeL", "eyeR", "happy", "size", "squint", "slant", "lookX", "lookY", "glow", "speak",
    "finL", "finR", "finGlow", "gleam",
    "lHx", "lHy", "lHz", "rHx", "rHy", "rHz",
    "asleep",
  ];

  // Where the middle of its body floats at rest (world y).
  const REST_Y = -0.37;
  // In the body's frame: where the head turns, and the head's middle above
  // that (robot.sksl's HC); the shoulders; the mittens at rest, a little out
  // to the sides as in the picture.
  const NECK = [0, 0.285, 0], HC_Y = 0.335;
  const SH_L = [-0.29, 0.17, 0], SH_R = [0.29, 0.17, 0];
  const HAND_L = [-0.47, -0.17, -0.06], HAND_R = [0.47, -0.17, -0.06];
  // The right mitten up in a wave, as in the owner's picture.
  const WAVE_R = [0.60, 0.40, -0.22];

  // The robot's own dice (see critter-pose.js's note on salts). The numbers
  // under 256 are nearly all taken by the four animals, so the robot's bases
  // sit in the gaps: none is another face's base (a base for the same
  // purpose is what would make two faces glance or blink together).
  const S_GAZE = 77, S_EVENT = 157, S_BEAT = 237, S_BLINK = 244, S_LEAN = 135, S_ZIP = 158, S_SIDE = 254,
        S_LISTEN = 78, S_THINK = 79, S_FOCUS = 239, S_NOD = 252, S_PHRASE = 253, S_CUTE = 251, S_BAG = 243;
  // How long each cute moment lasts: the wave, polishing its visor.
  const CUTE_LEN = [3.3, 3.2];

  /* ------------------------------------------------------------------ *
   * What it does at rest, and when.
   *
   * Idle time is cut into 16-second slots, sixteen to a 256-second window
   * (so everything repeats with critter-pose.js's PERIOD): a ZIP round its
   * space in slots 0, 6 and 13, each with a chance of 0.75 - about one every
   * two minutes (measured over the whole 4096 s the dice repeat in: 27 an
   * hour, so 1 to 3 minutes apart); in the other slots, with a chance of 0.7, one
   * small thing (below), never the same kind twice running. A zip plays only
   * once it has rested REST_S seconds in idle, and never over a cute moment
   * (judged at the zip's start, so one never pops in part way).
   * ------------------------------------------------------------------ */
  const SLOT = 16, REST_S = 10;
  // fin flick, curious look, hover dip, look at its mitten, happy squint
  const SMALL = [22, 20, 18, 18, 22];
  const K_ZIP = 5;
  function idleEvent(t) {
    const n = Math.floor(t / SLOT), m = n & 255, pos = m & 15;
    if ((pos === 0 || pos === 6 || pos === 13) && hash01(m * 256 + S_ZIP) < 0.75) {
      // (happening()'s own start: the same hash, so every kind starts alike.)
      const off = 0.5 + 5.5 * hash01(m * 256 + S_EVENT + 2);
      return [K_ZIP, t - n * SLOT - off, n * SLOT + off];
    }
    return happening(t, SLOT, 0.5, 5.5, S_EVENT, 0.7, SMALL);
  }
  /** Which way a happening starting at clock `at` goes, -1 or 1. */
  function sideOf(at) { return hash01((Math.floor(at / SLOT) & 255) * 256 + S_SIDE) < 0.5 ? -1 : 1; }

  /**
   * The zip: where it is, `x` seconds in, from its resting place ([x, y, z]
   * world offset). A quick eased dash out to a spot inside its space, a
   * little loop there, and a dash back, each easing in and out and
   * overlapping a little so it flows: about 2.6 seconds in all. The spot
   * and the loop's way round come from the slot's hash; the spot is always
   * inside the picture (up to 0.22 to either side, a little up, and 0.45
   * to 0.85 back, which makes it smaller as it goes).
   */
  const ZIP_S = 2.6;
  function zipAt(x, at) {
    if (x <= 0 || x >= ZIP_S) return [0, 0, 0];
    const m = Math.floor(at / SLOT) & 255;
    const tx = 0.22 * (2 * hash01(m * 256 + S_ZIP + 1) - 1);
    const ty = 0.03 + 0.10 * hash01(m * 256 + S_ZIP + 2);
    const tz = 0.45 + 0.40 * hash01(m * 256 + S_ZIP + 3);
    const dir = hash01(m * 256 + S_ZIP + 4) < 0.5 ? -1 : 1;
    const go = ease(x / 0.7) - ease((x - 1.75) / 0.85);
    const th = TAU * ease((x - 0.55) / 1.3);
    const r = 0.10;
    return [tx * go + dir * r * Math.sin(th), ty * go + r * (1 - Math.cos(th)), tz * go];
  }
  /**
   * Whether a zip starting `x` seconds ago may play: it has rested REST_S
   * seconds in idle, and no cute moment plays at its start, middle or end
   * (`since` is how long it has been idle).
   */
  function zipClear(t, since, x) {
    const s0 = since - x;
    if (s0 < REST_S) return 0;
    for (const d of [0, 0.5 * ZIP_S, ZIP_S]) {
      if (cuteAt(t - x + d, s0 + d, S_CUTE, CUTE_LEN)[0] >= 0) return 0;
    }
    return 1;
  }

  /**
   * A talking gesture when the host gives no phrase ends: critter-pose.js's
   * beat() with the robot's five kinds - a nod, the right mitten opening
   * out, the left, both, a tilt with a fin flick - at most one every two
   * seconds, often none, never the same twice running, never within 1.5 s
   * of a look that moves its eyes.
   */
  const BEAT = [3, 2, 2, 2, 2];
  function beat(t) {
    const b = happening(t, 2, 0, 0.6, S_BEAT, 0.45, BEAT);
    if (b[0] < 0) return b;
    const atYou = (id) => hash01(id * 256 + S_GAZE + 5) < 0.65;
    const moves = (c) => !(atYou(c[0]) && atYou(c[2]));
    const c = chain(b[2], 32, S_GAZE, 1.6, 5.5, 1.3);
    if (c[1] < 1.5 && moves(c)) return NONE;
    const n = chain(b[2] + 1.5, 32, S_GAZE, 1.6, 5.5, 1.3);
    if (n[0] !== c[0] && moves(n)) return NONE;
    return b;
  }
  /**
   * The same five kinds from a gesture landing on one of Jarvis's phrase
   * ends (phraseBeat's three kinds: a nod; one mitten - which one from the
   * phrase's own number; both mittens, or a tilt with a fin flick).
   */
  function phraseKind(k, n) {
    if (k === 0) return 0;
    if (k === 1) return hash01((n & 4095) * 256 + S_BAG) < 0.5 ? 1 : 2;
    return hash01((n & 4095) * 256 + S_BAG + 1) < 0.5 ? 3 : 4;
  }

  /** v, held softly inside -k..k (a smooth limit: no corner where it starts to hold). */
  function soft(v, k) { return k * Math.tanh(v / k); }

  // The head's own turn (without the body's).
  function headTurn(P) { return mul(ry(-P.headYaw), mul(rx(P.headPitch), rz(-P.headRoll))); }
  /** A point given in the head's frame, in the body's frame. */
  function onHead(P, v) { return add(NECK, apply(headTurn(P), v)); }
  /** Moves the left (or right) mitten toward `v` (body frame) by w. */
  function handL(P, v, w) { P.lHx += (v[0] - P.lHx) * w; P.lHy += (v[1] - P.lHy) * w; P.lHz += (v[2] - P.lHz) * w; }
  function handR(P, v, w) { P.rHx += (v[0] - P.rHx) * w; P.rHy += (v[1] - P.rHy) * w; P.rHz += (v[2] - P.rHz) * w; }

  /**
   * The small reaction as waiting on you or something going wrong arrives,
   * `x` seconds in, variant `k` (critter-pose.js's arriveKind, o.arrive), at
   * weight w (varOf), then still:
   *  - waiting on you: [0] it straightens up a touch, fins perking; [1] a
   *    quick blink, and its eyes widen a little; [2] it leans in a little
   *    closer.
   *  - something wrong: [0] a small start back, eyes squeezing; [1] its fins
   *    sag a little further, and a slow blink; [2] a glance down, its head
   *    dipping.
   * Returns how far the eyes shut (0..1).
   */
  const ARRIVE_S = 1.3;
  function react(P, state, x, k, w) {
    if (k < 0 || w <= 0 || x <= 0 || x >= ARRIVE_S) return 0;
    if (state === "approval") {
      if (k === 0) {
        const b = w * bump(x / 1.0);
        P.posY += 0.022 * b; P.finL -= 0.18 * b; P.finR -= 0.18 * b;
        return 0;
      }
      if (k === 1) {
        P.size += 0.07 * w * bump((x - 0.2) / 0.8);
        return w * bump(x / 0.3);
      }
      const b = w * bump(x / 1.1);
      P.pitch += 0.05 * b; P.posZ -= 0.03 * b; P.headPitch += 0.03 * b;
      return 0;
    }
    if (k === 0) {
      const b = w * bump(x / 0.9);
      P.posZ += 0.035 * b;
      return 0.35 * b;
    }
    if (k === 1) {
      const b = w * bump(x / 1.2);
      P.finL += 0.2 * b; P.finR += 0.2 * b;
      return w * bump((x - 0.1) / 0.6);
    }
    const b = w * bump(x / 1.2);
    P.lookY -= 0.35 * b; P.headPitch -= 0.05 * b;
    return 0;
  }

  function stateTargets(state, t, amp, look, since, o) {
    if (typeof since !== "number") since = 1e9;
    o = optsOf(o, t);
    const m = mods(o);
    // Idle: a focus session, and a cute moment while it plays, take the
    // happenings away (critter-pose.js's rules).
    const cu = state === "idle" ? cuteAt(t, since, S_CUTE, CUTE_LEN) : NONE;
    const cw = cu[0] >= 0 ? cuteOf(o) : 0;
    const fw = state === "idle" ? focusOf(o) : 0;
    const fp = fw * (1 - 0.6 * o.calm);   // the focus pose itself: smaller under calm (the happenings still go by fw)
    m[0] *= (1 - fw) * (1 - cw * (cu[0] >= 0 ? cuteQuiet(cu[1], CUTE_LEN[cu[0]]) : 0));
    const hap = m[0], sw = m[2], play = m[3];
    // The zip: gone under calm, Still, serious, a wake-up and a focus session
    // - and while it is being petted: it comes back to the hand.
    const zipW = (1 - o.still) * (1 - o.calm) * (1 - o.serious) * (1 - o.quiet) * (1 - fw) *
                 (1 - (AWAKE[state] ? petOf(o) : 0));
    const P = {
      posX: 0, posY: 0, posZ: 0, yaw: 0, roll: 0, pitch: 0, headYaw: 0, headPitch: 0, headRoll: 0,
      eyeL: 1, eyeR: 1, happy: 0, size: 1, squint: 0, slant: 0, lookX: 0, lookY: 0, glow: 1, speak: 0,
      finL: 0.12, finR: 0.12, finGlow: 0.5, gleam: -1,
      lHx: HAND_L[0], lHy: HAND_L[1], lHz: HAND_L[2], rHx: HAND_R[0], rHy: HAND_R[1], rHz: HAND_R[2],
      asleep: state === "standby" ? 1 : 0,
    };
    // Its hover - its breathing: a slow float up and down (300 cycles a
    // loop: once every 3.4 seconds).
    let bobK = 300, bobA = 0.018, blinkSlow = 1, blinks = true, turnBlink = 0, lid = 1, ackK = 1;
    // What moves a mitten relative to the head, worked out once the head
    // has turned (below).
    let chin = 0, polish = 0, rub = 0, waveUp = 0, waving = 0;
    let zip = null;

    if (state === "listening") {
      // Wide, round, attentive eyes on you, its head tilted about 14
      // degrees, its fins leaning in and its mittens up and open, as if to
      // say "go on". Your voice makes its eyes and fins glow brighter.
      // (Serious: no tilt, eyes their usual size.)
      const g = looks(t, S_GAZE, 1.8, 6, 0.85, 0.2, 0.1, 0, 0.04, 1.1, o);
      P.headRoll = play * 0.24 + sw * 0.02 * wave(t, 205, 0);
      P.headYaw = 0.1 * g[2];
      P.headPitch = 0.03;
      P.pitch = 0.06;
      P.finL = P.finR = -0.14;
      P.eyeL = P.eyeR = 1.05 + 0.1 * play;
      P.size = 1.06 + 0.06 * play;
      P.lookX = g[0] - 0.4 * g[2]; P.lookY = 0.05 + g[1] - 0.4 * g[3];
      P.glow = 1.05 + 0.35 * amp;
      P.finGlow = 0.6 + 0.4 * amp;
      P.lHx = -0.40; P.lHy = -0.03; P.lHz = -0.20; P.rHx = 0.40; P.rHy = -0.03; P.rHz = -0.20;
      // Now and then (variety): it tilts its head the other way, leans in a
      // little closer with both fins forward, or turns one fin to you.
      const v = variant(t, o, S_LISTEN, 0.4);
      if (v[0] === 0) P.headRoll -= 0.40 * play * v[1];
      else if (v[0] === 1) { P.pitch += 0.04 * v[1]; P.posZ -= 0.03 * v[1]; P.finL -= 0.08 * v[1]; P.finR -= 0.08 * v[1]; }
      else if (v[0] === 2) P.finR -= 0.25 * v[1];
      // A small nod in your pauses, its fins flicking.
      const nd = listenNod(t, o, S_NOD);
      P.headPitch += nd[0]; P.headRoll += play * nd[1]; lid *= 1 - nd[2];
      P.finL -= 0.25 * nd[3]; P.finR -= 0.25 * nd[3];
      turnBlink = g[4];
    } else if (state === "thinking") {
      // Narrowed eyes looking up, scanning slowly from side to side, their
      // glow swelling and ebbing; a mitten to its "chin".
      const g = looks(t, S_GAZE, 1.8, 6, 0.3, 0.5, 0.15, 0.5, 0.04, 1.1, o);
      P.squint = 0.6; P.size = 0.96;
      P.lookX = sw * 0.45 * wave(t, 150, 0) + 0.3 * g[0] - 0.3 * g[2];
      P.lookY = 0.75 + 0.15 * g[1] - 0.3 * g[3];
      P.headPitch = 0.07 + 0.1 * g[3] + sw * 0.02 * wave(t, 147, 0);
      P.headYaw = 0.12 * g[2] + sw * 0.05 * wave(t, 150, 0.4);
      P.headRoll = play * 0.06 + sw * 0.03 * wave(t, 98, 0);
      P.glow = 0.95 + 0.15 * wave(t, 300, 0);
      P.finGlow = 0.8;
      chin = 1;
      // Now and then (variety): both mittens tap together at its chest, its
      // head tilts with one fin twitching, or it looks down, thinking.
      const v = variant(t, o, S_THINK, 0.5);
      if (v[0] === 0) {
        const gate = ease(0.5 + 1.5 * wave(t, 184, 0));
        const taps = sw * Math.pow(0.5 - 0.5 * wave(t, 1141, Math.PI / 2), 2) * gate;
        chin = 1 - v[1];
        handL(P, [-0.11, -0.10 + 0.02 * taps, -0.31], v[1]);
        handR(P, [0.11, -0.10 + 0.02 * taps, -0.31], v[1]);
      } else if (v[0] === 1) {
        P.headRoll += 0.10 * play * v[1];
        P.finR += sw * 0.12 * v[1] * wave(t, 400, 0);
      } else if (v[0] === 2) {
        P.lookY += (-0.4 - P.lookY) * v[1]; P.headPitch -= 0.12 * v[1];
      }
      turnBlink = g[4];
    } else if (state === "speaking") {
      // Bright eyes, a little happy - they pulse with the voice (uniforms()
      // takes that from the words being heard, and only from them). It talks
      // with its head and its mittens, in phrases.
      const g = looks(t, S_GAZE, 1.6, 5.5, 0.65, 0.5, 0.18, 0, 0.06, 1.1, o);
      // (With the host's phrase ends, the gestures land on them instead.)
      let b = beat(t);
      if (o.phraseN >= 0) {
        const pb = phraseBeat(t, o, S_PHRASE, S_GAZE, 1.6, 5.5, 0.65);
        b = pb[0] < 0 ? pb : [phraseKind(pb[0], Math.max(0, o.phraseN)), pb[1], pb[2]];
      }
      const x = b[1];
      // A fact's nod waits while a gesture plays, so two never stack up.
      ackK = b[0] >= 0 ? 1 - bump(clamp(x / 1.6, 0, 1)) : 1;
      P.speak = 1;
      P.happy = 0.55; P.size = 1.02; P.glow = 1.1; P.finGlow = 0.7;
      P.pitch = 0.03;
      P.headYaw = sw * 0.05 * wave(t, 111, 0) + 0.09 * g[2];
      P.headRoll = sw * 0.04 * wave(t, 93, 0.5);
      P.lookX = g[0] - 0.16 * g[2]; P.lookY = g[1] - 0.16 * g[3];
      P.lHx = -0.47; P.lHy = -0.12; P.lHz = -0.12; P.rHx = 0.47; P.rHy = -0.12; P.rHz = -0.12;
      if (b[0] === 0) {
        // A nod on the stressed word, eyes smiling a little more.
        P.headPitch -= hap * 0.07 * (bump(x / 0.7) - 0.3 * bump((x - 0.55) / 0.7));
        P.happy += hap * 0.3 * bump(x / 0.7);
      } else if (b[0] === 1 || b[0] === 2) {
        // One mitten opens out, palm up, and goes back.
        const e = hap * envAHR(x, 0.4, 0.35, 0.6);
        if (b[0] === 1) { P.rHx += 0.06 * e; P.rHy += 0.14 * e; P.rHz -= 0.10 * e; P.finR -= 0.12 * e; }
        else { P.lHx -= 0.06 * e; P.lHy += 0.14 * e; P.lHz -= 0.10 * e; P.finL -= 0.12 * e; }
      } else if (b[0] === 3) {
        // Both mittens open a little, eyes a touch wider.
        const e = hap * envAHR(x, 0.45, 0.3, 0.6);
        P.lHx -= 0.05 * e; P.lHy += 0.10 * e; P.lHz -= 0.08 * e;
        P.rHx += 0.05 * e; P.rHy += 0.10 * e; P.rHz -= 0.08 * e;
        P.size += 0.04 * e;
      } else if (b[0] === 4) {
        // A tilt of the head, and a fin flicks.
        P.headRoll += hap * play * 0.08 * bump(x / 1.2);
        P.finL -= hap * 0.2 * bump((x - 0.2) / 0.6);
      }
      turnBlink = g[4];
    } else if (state === "approval") {
      // Waiting on you - perhaps on something serious, so NO WAVE and
      // nothing cute (the owner's call, 2026-09-28): steady round eyes
      // straight at you, fins up, its mittens a little forward, leaning
      // in a little, hovering almost still. Only its hover, slow blinks and
      // its eyes' tiny darts move - after one small reaction as it arrives.
      const g = restingGaze(t, S_GAZE);
      P.eyeL = P.eyeR = 1.06;
      P.size = 1.04 + 0.03 * play;
      P.glow = 1.1; P.finGlow = 0.7; P.finL = P.finR = -0.06;
      P.pitch = 0.05; P.headPitch = 0.03;
      P.lHx = -0.41; P.lHy = -0.11; P.lHz = -0.18; P.rHx = 0.41; P.rHy = -0.11; P.rHz = -0.18;
      P.lookX = g[0]; P.lookY = g[1];
      blinkSlow = 1.4; bobA = 0.006;
      lid *= 1 - react(P, state, since, o.arrive, varOf(o));
    } else if (state === "standby") {
      // Asleep, powered down: its eyes a dim line, its head bowed, its fins
      // drooping, its mittens slack; it floats a little lower and slower.
      // Once in a while a sigh. Nothing else moves.
      const e = happening(t, 16, 0.5, 5.5, S_EVENT, 0.35, 1);
      const sigh = e[0] === 0 ? bump(e[1] / 4.5) : 0;
      P.eyeL = P.eyeR = 0;
      P.glow = 0.4; P.finGlow = 0.12; P.finL = P.finR = 0.50;
      P.headPitch = -0.16 - 0.03 * sigh; P.headRoll = 0.08 * play; P.pitch = 0.04;
      P.posY = -0.08 - 0.01 * sigh;
      P.lHx = -0.40; P.lHy = -0.26; P.lHz = -0.02; P.rHx = 0.40; P.rHy = -0.26; P.rHz = -0.02;
      // 171 cycles a loop: once every 6 seconds.
      bobK = 171; bobA = 0.008 * (1 + 0.6 * sigh); blinks = false;
    } else if (state === "error") {
      // Something went wrong: a still, concerned look - its eyes a little
      // smaller and slanted, looking down, head tipped, fins drooping,
      // mittens lowered. Nothing comic (the owner's call, 2026-09-28).
      const g = restingGaze(t, S_GAZE);
      P.slant = 0.30; P.squint = 0.45; P.size = 0.92; P.eyeL = P.eyeR = 0.85; P.glow = 0.85;
      P.headRoll = -0.10 * play; P.headPitch = -0.07;
      P.lookX = g[0]; P.lookY = -0.3 + g[1];
      P.finL = P.finR = 0.40; P.finGlow = 0.3;
      P.lHx = -0.42; P.lHy = -0.24; P.lHz = -0.04; P.rHx = 0.42; P.rHy = -0.24; P.rHz = -0.04;
      P.posY = -0.02;
      blinkSlow = 1.4; bobA = 0.006;
      lid *= 1 - react(P, state, since, o.arrive, varOf(o));
    } else if (state === "banked") {
      // Keeping things for later: dozing where it floats, lids heavy,
      // blinking slowly - and now and then its head sinks over three
      // seconds before it catches itself.
      const e = happening(t, 16, 0.5, 5.5, S_EVENT, 0.55, 1);
      const x = e[1];
      const droop = e[0] === 0 ? (x < 3.2 ? ease(x / 3.2) : 1 - ease((x - 3.2) / 0.8)) : 0;
      P.eyeL = P.eyeR = 0.35 * (1 - 0.7 * droop);
      P.squint = 0.3; P.glow = 0.6; P.finGlow = 0.3; P.finL = P.finR = 0.3;
      P.headPitch = -0.12 - 0.12 * droop;
      P.lookY = -0.2;
      P.posY = -0.03;
      // 205 cycles a loop: once every 5 seconds.
      bobK = 205; bobA = 0.012; blinkSlow = 2.5;
    } else {
      // idle: happy arcs for eyes, looking about - the eyes first, the head
      // after; it bobs gently where it floats and its fins sway a little.
      // Now and then one small thing, a zip, or a cute moment.
      const g = looks(t, S_GAZE, 1.4, 5.5, 0.4, 0.8, 0.3, 0.05, 0.07, 1.1, o);
      const ev = idleEvent(t), x = ev[1];
      P.happy = 0.85;
      P.headYaw = 0.22 * g[2];
      P.headPitch = 0.08 * g[3] + sw * 0.015 * wave(t, 97, 1.1);
      P.headRoll = sw * 0.03 * wave(t, 71, 0.2);
      P.roll = sw * 0.02 * shift(t, S_LEAN);
      P.posX = sw * 0.01 * wave(t, 131, 0.4);
      P.lookX = g[0] - 0.4 * g[2]; P.lookY = g[1] - 0.4 * g[3];
      P.finL += sw * 0.05 * wave(t, 173, 0); P.finR += sw * 0.05 * wave(t, 173, 1.9);
      P.lHy += sw * 0.008 * wave(t, 113, 0); P.rHy += sw * 0.008 * wave(t, 113, 1.5);
      if (ev[0] === 0) {
        // A fin flicks, then the other, a little less.
        const s = sideOf(ev[2]);
        const a = hap * 0.35 * bump(x / 0.5), b = hap * 0.22 * bump((x - 0.35) / 0.5);
        if (s < 0) { P.finL += a; P.finR += b; } else { P.finR += a; P.finL += b; }
      } else if (ev[0] === 1) {
        // Something to one side: its head turns to it, a little tilted, its
        // eyes round and curious; it looks, and comes back.
        const s = sideOf(ev[2]), e = hap * envAHR(x, 0.5, 1.6, 0.7);
        P.headYaw += (s * 0.28 - P.headYaw) * e;
        P.headRoll += s * 0.10 * play * e;
        P.happy += (0.15 - P.happy) * e; P.size += 0.08 * e;
        P.lookX += (s * 0.7 - P.lookX) * e; P.lookY += (0.1 - P.lookY) * e;
      } else if (ev[0] === 2) {
        // It dips a little where it floats, blinks, and rises back.
        const d = hap * bump(x / 1.6);
        P.posY -= 0.035 * d;
        P.finL += 0.08 * d; P.finR += 0.08 * d;
        lid = 1 - hap * bump((x - 0.55) / 0.35);
      } else if (ev[0] === 3) {
        // It lifts its left mitten, looks at it, wiggles it, and lowers it.
        const e = hap * envAHR(x, 0.6, 1.4, 0.7);
        handL(P, [-0.30, 0.02, -0.30], e);
        P.lHx += 0.02 * e * wave(t, 900, 0);
        P.headPitch -= 0.14 * e; P.headYaw -= 0.10 * e;
        P.lookX += (-0.35 - P.lookX) * e; P.lookY += (-0.6 - P.lookY) * e;
        P.happy += (0.3 - P.happy) * e;
      } else if (ev[0] === 4) {
        // A happy squint: its eyes smile right up, and a small tilt.
        const e = hap * envAHR(x, 0.4, 1.4, 0.6);
        P.happy += (1 - P.happy) * e; P.size += 0.05 * e;
        lid = 1 - 0.3 * e;
        P.headRoll += sideOf(ev[2]) * 0.08 * play * e;
      } else if (ev[0] === K_ZIP) {
        zip = [x, ev[2], zipW * zipClear(t, since, x)];
      }
      turnBlink = g[4];
      if (fw > 0) {
        // Working beside you (a focus session): its mittens together in
        // front of it, tinkering a little, its eyes on them, looking up now
        // and then - far fewer looks, no happenings and no zips.
        const f = gaze(t, S_FOCUS, 4, 12, 0.75, 0.3, 0.12, 0, 0.03, 1.6);
        P.lookX += (f[0] - 0.4 * f[2] - P.lookX) * fp;
        P.lookY += (-0.6 + f[1] - 0.4 * f[3] - P.lookY) * fp;
        P.headYaw += (0.2 * f[2] - P.headYaw) * fp;
        P.headPitch += (-0.14 + 0.1 * f[3] - P.headPitch) * fp;
        handL(P, [-0.14, -0.14 + 0.01 * sw * wave(t, 260, 0), -0.30], fp);
        handR(P, [0.14, -0.14 + 0.01 * sw * wave(t, 260, 2.1), -0.30], fp);
        P.happy += (0.5 - P.happy) * fp;
        turnBlink *= 1 - fp;
      }
      // The small stretch as a focus session ends: mittens up and out, fins
      // flicking, eyes smiling shut.
      const fe = focusEndOf(t, o);
      if (fe > 0) {
        handL(P, [-0.55, 0.22, -0.08], 0.8 * fe); handR(P, [0.55, 0.22, -0.08], 0.8 * fe);
        P.headPitch += 0.08 * fe; P.finL -= 0.25 * fe; P.finR -= 0.25 * fe;
        P.happy += (1 - P.happy) * fe; lid *= 1 - 0.5 * fe;
      }
      if (cw > 0 && cu[0] === 0) {
        // Cute moment: a friendly wave, as in the owner's picture - its right
        // mitten up, waving side to side a few times, eyes smiling, head
        // tipped.
        const xc = cu[1];
        waveUp = cw * envAHR(xc, 0.6, 1.9, 0.7);
        waving = cw * envAHR(xc - 0.5, 0.3, 1.5, 0.4);
        P.happy += (1 - P.happy) * waveUp; P.size += 0.04 * waveUp;
        P.headRoll += 0.10 * play * waveUp; P.headYaw += 0.06 * waveUp;
        P.roll -= 0.03 * waveUp;
        P.finR -= 0.15 * waveUp;
        P.lookX += (0 - P.lookX) * waveUp; P.lookY += (0 - P.lookY) * waveUp;
        turnBlink *= 1 - waveUp;
      } else if (cw > 0 && cu[0] === 1) {
        // Cute moment: it polishes its visor - its right mitten comes up and
        // rubs two small circles on the glass, eyes squeezed happily shut;
        // then a gleam crosses the visor and its fins flick.
        const xc = cu[1];
        polish = cw * envAHR(xc, 0.7, 1.6, 0.7);
        rub = envAHR(xc - 0.6, 0.3, 1.3, 0.4);
        P.happy += (1 - P.happy) * polish;
        lid *= 1 - 0.45 * polish * rub;
        P.headPitch -= 0.10 * polish; P.headRoll -= 0.08 * play * polish;
        P.lookX += (0 - P.lookX) * polish; P.lookY += (0 - P.lookY) * polish;
        if (xc > 2.4 && xc < 3.15) P.gleam = (xc - 2.4) / 0.75;
        const fl = cw * bump((xc - 2.4) / 0.6);
        P.finL -= 0.25 * fl; P.finR -= 0.25 * fl;
        turnBlink *= 1 - polish;
      }
    }

    // Stroked (petting): it leans its head into your hand, eyes smiling
    // and half shut, fins back happily - and follows the stroke a little.
    const pw = AWAKE[state] ? petOf(o) : 0;
    if (pw > 0) {
      P.headRoll += pw * play * (0.10 * o.petX + 0.03 * o.petDir);
      P.headPitch += 0.04 * pw;
      P.roll -= 0.02 * pw * o.petX;
      P.finL += 0.2 * pw; P.finR += 0.2 * pw;
      P.happy += (1 - P.happy) * pw;
      lid *= 1 - 0.45 * pw;
    }
    // A fact saved: one small nod, fins flicking. A long answer ready: its
    // eyes and fins glow up once (it has no orb).
    const an = AWAKE[state] ? ackNodOf(t, o) : ZERO2;
    P.headPitch += ackK * an[0]; P.finL -= 0.3 * ackK * an[1]; P.finR -= 0.3 * ackK * an[1];
    const gl = AWAKE[state] ? ackGlowOf(t, o) : 0;
    P.glow += 0.4 * gl; P.finGlow += 0.6 * gl;

    // The hover.
    const hb = wave(t, bobK, 0);
    P.posY += bobA * (1 - 0.4 * o.calm) * hb;
    // Its fins trail the hover a moment behind (follow-through).
    const trail = 0.25 * bobA * (1 - 0.4 * o.calm) * wave(t - 0.35, bobK, 0) / 0.018;
    P.finL += 0.04 * trail; P.finR += 0.04 * trail;

    // Following the pointer: mostly with the eyes. Asleep, it does not.
    const lw = state === "standby" ? 0 : clamp(look.w || 0, 0, 1);
    if (lw > 0) {
      const lx = clamp(look.x || 0, -1, 1), ly = clamp(look.y || 0, -1, 1);
      P.lookX += (lx - P.lookX) * lw;
      P.lookY += (ly - P.lookY) * lw;
      P.headYaw += m[1] * 0.2 * lx * lw;
      P.headPitch += m[1] * 0.2 * ly * lw;
    }

    // What the mittens do to the head, now that it has turned.
    if (chin > 0) handR(P, onHead(P, [0.21, 0.01, -0.30]), chin);
    if (polish > 0) {
      const q = onHead(P, [0.14 + 0.05 * rub * wave(t, 1280, Math.PI / 2), HC_Y - 0.10 + 0.045 * rub * wave(t, 1280, 0), -0.52]);
      handR(P, q, polish);
    }
    if (waveUp > 0) {
      handR(P, WAVE_R, waveUp);
      P.rHx += 0.06 * waving * wave(t, 1741, 0);
      P.rHz -= 0.02 * waving * wave(t, 1741, Math.PI / 2);
    }
    if (zip && zip[2] > 0) {
      // The dash itself, with its bank into each turn and its eyes looking
      // where it is going; the mittens and fins trail a little.
      const k = zip[2], p = zipAt(zip[0], zip[1]);
      const h = 1 / 30, a = zipAt(zip[0] + h, zip[1]), b = zipAt(zip[0] - h, zip[1]);
      const vx = k * (a[0] - b[0]) / (2 * h), vy = k * (a[1] - b[1]) / (2 * h), vz = k * (a[2] - b[2]) / (2 * h);
      // (Every limit here is a soft one - soft() - so nothing changes speed
      // in a frame as the dash reaches it.)
      const v2 = vx * vx + vy * vy + vz * vz, sp = v2 / (v2 + 0.5);
      P.posX += k * p[0]; P.posY += k * p[1]; P.posZ += k * p[2];
      P.roll -= 0.22 * soft(vx, 1.4);
      P.pitch += 0.10 * soft(-vz, 1.4) + 0.05 * soft(vy, 1.4);
      P.happy += (1 - P.happy) * sp;
      P.lookX += 0.35 * soft(vx, 1.0); P.lookY += 0.25 * soft(vy, 1.0);
      P.lHx -= 0.03 * vx; P.lHy -= 0.03 * vy; P.rHx -= 0.03 * vx; P.rHy -= 0.03 * vy;
      P.finL += 0.10 * sp; P.finR += 0.10 * sp;
    }
    lid *= farewell(P, state, o);

    const qk = 1 - o.quiet;
    const k = lid * (1 - qk * Math.max(blinks ? blinkAt(t, S_BLINK, blinkSlow, 2, 9) : 0, turnBlink));
    P.eyeL *= k; P.eyeR *= k;
    return P;
  }

  /**
   * Hello and goodbye, when the owner switches faces (critter-pose.js's
   * farewell says how the host plays them: o.hello and o.goodbye, 0..1).
   *  - Goodbye: a quick wave, eyes smiling, looking at you (not asleep or
   *    dozing), then it zips up and out of the top of the picture.
   *  - Hello: it drops in from above, settles with a small bounce, its eyes
   *    boot up, blink, and look at you; its fins flick (not asleep or
   *    dozing).
   * Under still, calm or a serious moment, and while waiting on you or at
   * an error (E, critter-pose.js's switchE), the pose plays none of it and
   * the host cross-fades the faces (critter-pose.js's switchAlpha), as for
   * every face. Returns how open the eyes are (0..1) for the caller to lay
   * on the lids.
   */
  const UP = 2.3, DOWN = 2.1;   // how far up it goes to be out of view, leaving and arriving
  function farewell(P, state, o) {
    const g = o.goodbye, h = o.hello;
    if (g <= 0 && h >= 1) return 1;
    const E = switchE(o, state);
    const awake = AWAKE[state] ? 1 : 0;
    let lid = 1;
    if (g > 0) {
      const a = E * bump(clamp(g / 0.6, 0, 1));
      const at = E * awake * ease(g / 0.2);
      P.lookX += (0 - P.lookX) * at; P.lookY += (0 - P.lookY) * at;
      P.headYaw += (0 - P.headYaw) * at;
      const wv = a * awake;
      handR(P, WAVE_R, wv);
      P.rHx += 0.06 * wv * Math.sin(TAU * 1.6 * g);
      P.happy += (1 - P.happy) * wv;
      const go = E * ease((g - 0.45) / 0.55);
      P.posY += UP * go; P.posZ += 0.2 * go;
      P.finL += 0.2 * go; P.finR += 0.2 * go;
    }
    if (h < 1) {
      lid *= toward(1, ease((h - 0.35) / 0.3) * (1 - bump((h - 0.72) / 0.18)), E);
      P.posY += E * (DOWN * (1 - ease(h / 0.55)) - 0.045 * bump((h - 0.52) / 0.33));
      const f = E * awake * bump((h - 0.6) / 0.3);
      P.finL -= 0.25 * f; P.finR -= 0.25 * f;
      const at = E * awake * ease((h - 0.4) / 0.2) * (1 - ease((h - 0.85) / 0.15));
      P.lookX += (0 - P.lookX) * at; P.lookY += (0 - P.lookY) * at;
      P.headYaw += (0 - P.headYaw) * at;
      P.happy += (1 - P.happy) * E * awake * bump((h - 0.6) / 0.4);
    }
    return lid;
  }

  /**
   * Its powering down and booting up - see critter-pose.js's "Waking up and
   * falling asleep" and the panda's wakeSleep for what x, k, E and F are.
   *
   *  - Powering down (3 s): its eyes keep their shape as they narrow to a
   *    line and their glow dims; it sinks a little as its hover slows (the
   *    settling does that); its fins, mittens and head hold a moment and
   *    then droop.
   *  - Booting up (2.2 s): the dim line of its eyes brightens first (the
   *    settling of its glow), then they open, blink once, and its fins
   *    flick up; a small lift as it powers up.
   * Waking into waiting on you, an error or a doze, or under calm, Still or
   * a serious moment: only the eyes.
   */
  const FINS = ["finL", "finR"];
  const HANDS = ["lHx", "lHy", "lHz", "rHx", "rHy", "rHz"];
  const HEAD = ["headYaw", "headPitch", "headRoll"];
  function hold(P, F, keys, w) { for (const key of keys) P[key] = toward(P[key], F[key], w); }
  function wakeSleep(P, state, x, k, E, t, F) {
    const e = E * k;
    if (state === "standby") {
      const lids = (1 - 0.3 * ease((x - 0.3) / 0.7)) * (1 - ease((x - 1.6) / 1.0));
      const lid = k * toward(eyesClose(x), lids, E);
      P.eyeL = F.eyeL * lid; P.eyeR = F.eyeR * lid;
      // The eyes keep their shape as they close (happy arcs close as arcs).
      const shape = k * (1 - ease((x - 2.2) / 0.8));
      P.happy = toward(P.happy, F.happy, shape); P.size = toward(P.size, F.size, shape);
      P.squint = toward(P.squint, F.squint, shape); P.slant = toward(P.slant, F.slant, shape);
      P.glow = toward(P.glow, F.glow, k * (1 - ease((x - 1.2) / 1.6)));
      hold(P, F, FINS, e * (1 - ease((x - 1.0) / 1.6)));
      hold(P, F, HANDS, e * (1 - ease((x - 0.8) / 1.8)));
      hold(P, F, HEAD, e * (1 - ease((x - 1.4) / 1.4)));
      return;
    }
    const lids = ease((x - 0.45) / 0.5) * (1 - E * bump((x - 1.15) / 0.35));
    const f = 1 - k * (1 - lids);
    P.eyeL *= f; P.eyeR *= f;
    P.finL -= 0.25 * e * bump((x - 1.3) / 0.6); P.finR -= 0.25 * e * bump((x - 1.4) / 0.6);
    P.posY += 0.02 * e * bump((x - 0.9) / 0.9);
  }

  // (The eyes' SHAPE - happy, size, lids, slant - and their glow settle with
  // the body, not as fast as the eyelids: a quicker change of expression
  // made a sudden change of speed at the start of it. Opening and closing,
  // and where they look, stay quick.)
  const HALF = halfLives(
    ["eyeL", "eyeR", "lookX", "lookY", "gleam"], ["speak"],
    ["headYaw", "headPitch", "headRoll"],
    ["lHx", "lHy", "lHz", "rHx", "rHy", "rHz", "finGlow"],
    ["finL", "finR"]);
  const pose = makePose(stateTargets, KEYS, HALF, wakeSleep);

  /** The whole robot's turn: its spin (yaw), its bank (roll), its lean (pitch). */
  function frameOf(P) { return mul(ry(-P.yaw), mul(rz(P.roll), rx(-P.pitch))); }
  function bodyAt(P) { return [P.posX, REST_Y + P.posY, P.posZ]; }

  /**
   * The shader's uniforms. `mouth` is the words being heard (as for the
   * animals' mouths): the robot has no mouth, so it makes its eyes PULSE -
   * brighter, a touch bigger, a small hop - with the voice's opening, and
   * only while it is speaking. No real voice (a typed answer, Quiet): no
   * pulse, exactly as a mouth stays shut.
   */
  function uniforms(P, mouth) {
    const B = frameOf(P), bodyPos = bodyAt(P);
    const toWorld = (v) => add(bodyPos, apply(B, v));
    const H = mul(B, headTurn(P));
    const neck = toWorld(NECK);
    const M = mouthOf(P, mouth);
    const pulse = clamp(M[0] + 0.3 * M[1], 0, 1);
    // The "orb" is only a light: a point (no halo) just behind the visor's
    // glass - there it throws no glint on the glass - whose glow reaches
    // its chest, mittens and fins in the eyes' colour.
    const light = add(neck, apply(H, [0, HC_Y - 0.08, -0.36]));
    return {
      uBodyPos: bodyPos,
      uBodyR0: invRow(B, 0), uBodyR1: invRow(B, 1), uBodyR2: invRow(B, 2),
      uNeck: neck,
      uHeadR0: invRow(H, 0), uHeadR1: invRow(H, 1), uHeadR2: invRow(H, 2),
      uEyes: [clamp(P.eyeL, 0, 1.3), clamp(P.eyeR, 0, 1.3), clamp(P.happy, 0, 1), clamp(P.size, 0.6, 1.4)],
      uEyes2: [clamp(P.squint, 0, 1), P.slant, clamp(P.glow, 0, 1.6), pulse],
      uLook: [clamp(P.lookX, -1, 1), clamp(P.lookY, -1, 1)],
      uFins: [P.finL, P.finR, clamp(P.finGlow, 0, 1.5), P.gleam],
      uShL: toWorld(SH_L), uHandL: toWorld([P.lHx, P.lHy, P.lHz]),
      uShR: toWorld(SH_R), uHandR: toWorld([P.rHx, P.rHy, P.rHz]),
      uOrb: [light[0], light[1], light[2], 0],
      uOrbGlow: [clamp(0.5 * P.glow, 0, 1)],
    };
  }

  // The robot's camera (robot.sksl): target x, y, z, distance, pitch.
  const CAM = [0, -0.05, 0, 3.25, 0.10];
  const ZZ_AT = [0.36, HC_Y + 0.40, 0];
  /** Where its sleeping Zs rise from - see critter-pose.js's overlay(). */
  function overlay(P, view) {
    const at = add(bodyAt(P), apply(frameOf(P), onHead(P, ZZ_AT)));
    return overlayAt(P, at, CAM, view);
  }

  /** Whether one of its idle moments is playing at clock t (critter-pose.js playing(), cuteBusy()). */
  function busy(state, t, since, opts) {
    return state === "idle" && (C.util.playing(idleEvent(t)) || cuteBusy(t, since, opts, S_CUTE, CUTE_LEN));
  }

  /** Whether one of its own talking gestures is playing at clock t (critter-pose.js gesturing()). */
  function gesturing(t) {
    const b = beat(t);
    return b[0] >= 0 && b[1] >= 0 && b[1] < C.util.GESTURE_S;
  }

  C.species.robot = { KEYS, stateTargets, pose, uniforms, mouth: mouthOf, overlay, busy, gesturing, HELLO_S, GOODBYE_S };
})(typeof globalThis !== "undefined" ? globalThis : this);
