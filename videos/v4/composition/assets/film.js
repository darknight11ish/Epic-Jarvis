/* Jarvis v4: the per-frame engine for both cuts (index.html, vertical.html).

   v2's look (slammed capitals, RGB-split glitch, camera punches on the beat,
   HUD brackets and readouts, scanlines, grain) on v3's engine: every visible
   value is a pure function of t. One GSAP tween advances a clock and calls
   render(t); nothing else animates, so a seek to any frame equals playing up
   to it. Everything is keyed to window.TIMING.hits, the table the score is
   written from. An element or a hit a film does not have is skipped. */
(function () {
  "use strict";
  var FPS = 30;

  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function lerp(a, b, k) { return a + (b - a) * k; }
  var E = {
    lin: function (k) { return k; },
    out2: function (k) { return 1 - (1 - k) * (1 - k); },
    out3: function (k) { return 1 - Math.pow(1 - k, 3); },
    expo: function (k) { return k >= 1 ? 1 : 1 - Math.pow(2, -10 * k); },
    in2: function (k) { return k * k; },
    io: function (k) { return k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2; },
    back: function (k) { var c = 1.8; return 1 + (c + 1) * Math.pow(k - 1, 3) + c * Math.pow(k - 1, 2); }
  };
  function prog(t, t0, d, e) { return (e || E.out3)(clamp((t - t0) / d, 0, 1)); }
  function $(id) { return document.getElementById(id); }
  function has(v) { return typeof v === "number" && !isNaN(v); }
  function hashi(n) { n = Math.imul(n ^ (n >>> 16), 0x45d9f3b); n = Math.imul(n ^ (n >>> 16), 0x45d9f3b); return (n ^ (n >>> 16)) >>> 0; }
  var GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#$%&*+?<>/";
  function scramble(text, t0, dur, t, seed) {
    if (t < t0) return "";
    var k = clamp((t - t0) / dur, 0, 1);
    if (k >= 1) return text;
    var lock = Math.floor(k * text.length), frame = Math.floor(t * FPS), out = "";
    for (var i = 0; i < text.length; i++) {
      var ch = text.charAt(i);
      out += (ch === " " || i < lock) ? ch : GLYPHS.charAt(hashi(seed * 977 + i * 131 + frame * 7919) % GLYPHS.length);
    }
    return out;
  }

  /* ---------- building blocks ---------- */
  // Rise in at t0 (from dx, dy), optionally out at o.out. Hidden before t0.
  function appear(el, t, t0, o) {
    if (!el || !has(t0)) return;
    o = o || {};
    var d = o.d || 0.4, dy = o.dy === undefined ? 30 : o.dy, dx = o.dx || 0;
    var kin = t < t0 ? 0 : prog(t, t0, d, o.e || E.out3);
    var kout = has(o.out) ? 1 - prog(t, o.out, o.outD || 0.25, E.in2) : 1;
    el.style.opacity = t < t0 ? "0" : (kin * kout).toFixed(3);
    el.style.transform = "translate(" + (dx * (1 - kin)).toFixed(1) + "px," + (dy * (1 - kin)).toFixed(1) + "px)" +
      (o.s0 ? " scale(" + lerp(o.s0, 1, kin).toFixed(4) + ")" : "");
  }
  // v2's headline slam: from big and blurred to sharp in about a third of a second.
  function slam(el, t, t0, o) {
    if (!el || !has(t0)) return;
    o = o || {};
    var k = t < t0 ? 0 : prog(t, t0, o.d || 0.32, E.expo);
    var kout = has(o.out) ? 1 - prog(t, o.out, 0.2, E.in2) : 1;
    el.style.opacity = t < t0 ? "0" : (Math.min(1, k * 1.4) * kout).toFixed(3);
    el.style.transform = "scale(" + lerp(o.from || 1.5, 1, k).toFixed(4) + ")";
    el.style.filter = k < 1 ? "blur(" + (18 * (1 - k)).toFixed(1) + "px)" : "none";
  }
  // RGB-split glitch on a .gt headline: the red and cyan copies jitter for 0.3 s.
  function glitch(el, t, at, reach) {
    if (!el || !has(at)) return;
    var d = t - at, off = 0;
    if (d >= 0 && d < 0.3) off = (Math.floor(d / 0.05) % 2 ? 1 : -1) * (reach || 12) * (1 - d / 0.3);
    el.style.setProperty("--gr", (-off).toFixed(1) + "px");
    el.style.setProperty("--gb", off.toFixed(1) + "px");
  }
  // A press on a button: an accent outline that flashes on.
  function press(el, t, at) {
    if (!el || !has(at)) return;
    var on = t >= at - 0.1 && t < at + 0.5;
    el.style.opacity = on ? (t < at ? prog(t, at - 0.1, 0.1, E.out2) : 1 - prog(t, at + 0.25, 0.25, E.in2)).toFixed(3) : "0";
  }

  function run(cfg) {
    var H = cfg.H, R = window.REACTOR, AD = window.AUDIO_DATA;
    gsap.defaults({ lazy: false });
    var tl = gsap.timeline({ paused: true });
    function audioLow(t) { var i = clamp(Math.floor(t * AD.fps), 0, AD.low.length - 1); return AD.low[i] || 0; }

    /* glitch-text copies (the rgb-glitch-text structure) */
    Array.prototype.forEach.call(document.querySelectorAll(".gt[data-text]"), function (el) {
      var s = el.getAttribute("data-text");
      ["gr", "gb", "gm"].forEach(function (c) { var sp = document.createElement("span"); sp.className = c; sp.textContent = s; el.appendChild(sp); });
      el.setAttribute("data-layout-allow-overlap", "");
      Array.prototype.forEach.call(el.children, function (c) { c.setAttribute("data-layout-allow-overlap", ""); });
    });

    /* ---------- the reactor ---------- */
    var heroWrap = $("hero-wrap"), heroS = R.surface($("hero"), "arc");
    function segAt(list, t) { var k = 0; for (var i = 0; i < list.length; i++) { if (t >= list[i][0]) k = i; else break; } return k; }
    function heroPhase(t) {
      var ph = 0, sp = null, dt = 1 / 120;
      for (var x = 0; x < t; x += dt) {
        var s = cfg.hero[segAt(cfg.hero, x)], target = R.speedOf("arc", s[1]);
        if (x < 1.5) target *= 1 + 5 * Math.exp(-x / 0.45);      // the ignite spin-up
        if (sp === null) sp = target;
        sp += (target - sp) * Math.min(1, dt / 0.22);
        ph += sp * Math.min(dt, t - x);
      }
      return ph;
    }
    function ampFor(state, t) {
      if (state === "listening") return clamp(0.3 + 0.6 * Math.abs(Math.sin(t * 6.7)) * (0.55 + 0.45 * Math.sin(t * 2.3 + 1)), 0, 1);
      if (state === "speaking") return clamp(0.25 + 0.6 * Math.pow(Math.abs(Math.sin(t * 8.9) * Math.sin(t * 3.1 + 0.4)), 0.7), 0, 1);
      return 0.2;
    }
    function heroColour(i, t) {
      var s = cfg.hero[i], c = R.colours(s[1], t, ampFor(s[1], t));
      if (i > 0) {
        var k = (t - s[0]) / 0.25;
        if (k < 1) { var p = R.colours(cfg.hero[i - 1][1], t, ampFor(cfg.hero[i - 1][1], t)), e = k * k * (3 - 2 * k); c = { a: R.mix(p.a, c.a, e), b: R.mix(p.b, c.b, e) }; }
      }
      return c;
    }
    function drawHero(t) {
      var f = null;
      for (var i = 0; i < cfg.frames.length; i++) if (t >= cfg.frames[i][0] && t < cfg.frames[i][1]) f = cfg.frames[i];
      if (!f) { heroWrap.style.opacity = "0"; return; }
      var k = E.io(clamp((t - f[0]) / (f[1] - f[0]), 0, 1));
      var frozen = has(H.stop) && t >= H.stop && t < H.stopEnd;
      heroWrap.style.opacity = String(f[6]);
      heroWrap.style.transform = "translate(" + f[2] + "px," + f[3] + "px) scale(" + lerp(f[4], f[5], k).toFixed(4) + ")";
      heroWrap.style.clipPath = t < 1.6 && f[0] === 0 ? "circle(" + (75 * E.expo(clamp((t - 0.05) / 1.4, 0, 1))).toFixed(2) + "% at 50% 50%)" : "none";
      var tt = frozen ? H.stop : t, si = segAt(cfg.hero, tt), st = cfg.hero[si][1];
      heroS.g.setTransform(1, 0, 0, 1, 0, 0); heroS.g.clearRect(0, 0, heroS.canvas.width, heroS.canvas.height);
      R.draw(heroS, { t: tt, phase: heroPhase(tt), state: st, amp: ampFor(st, tt), beat: audioLow(t) * 0.8,
                      col: heroColour(si, tt), glow: (st === "standby" ? 0.08 : st === "idle" ? 0.2 : 0.32) + audioLow(t) * 0.45, clear: false, quality: 1.2 });
    }

    /* ---------- captions: every spoken line, labelled ---------- */
    var cap = $("cap"), capWho = $("cap-who"), capText = $("cap-text");
    function captions(t) {
      var c = null;
      for (var i = 0; i < cfg.caps.length; i++) if (t >= cfg.caps[i][0] && t < cfg.caps[i][1]) c = cfg.caps[i];
      if (!c) { cap.style.opacity = "0"; return; }
      capWho.textContent = c[2] === "you" ? "YOU ▸" : "JARVIS ▸";
      capWho.className = c[2];
      var words = c[3].split(" "), n = Math.ceil(clamp((t - c[0]) / (c[4] || 0.6), 0, 1) * words.length);
      capText.textContent = words.slice(0, Math.max(1, n)).join(" ");
      cap.style.opacity = prog(t, c[0], 0.12, E.out2).toFixed(3);
    }

    /* ---------- HUD ---------- */
    var hudCtx = $("hud-ctx"), hudState = $("hud-state"), hudDot = $("hud-dot"), hudBeat = $("hud-beat"), hudTc = $("hud-tc");
    var STATE = { standby: "MODEL ASLEEP", idle: "IDLE", listening: "LISTENING", thinking: "THINKING", speaking: "SPEAKING" };
    function hud(t) {
      var c = cfg.context[segAt(cfg.context, t)];
      if (hudCtx) hudCtx.textContent = scramble(c[1], c[0], 0.35, t, 90 + Math.round(c[0] * 10));
      if (hudBeat) { var b = cfg.beats[segAt(cfg.beats, t)]; hudBeat.textContent = b[1]; }
      var s = cfg.hero[segAt(cfg.hero, t)][1];
      if (has(H.stop) && t >= H.stop && t < H.stopEnd) s = "idle";
      if (hudState) hudState.textContent = (has(H.stop) && t >= H.stop && t < H.stopEnd + 0.6) ? "STOPPED" : STATE[s];
      var dot = (has(H.stop) && t >= H.stop && t < H.stopEnd + 0.6) ? "#ff6878" : R.colours(s, t, 0.3).a;
      if (hudDot) { hudDot.style.background = dot; hudDot.style.boxShadow = "0 0 12px " + dot; }
      var fr = Math.floor(t * FPS + 1e-6);
      if (hudTc) hudTc.textContent = "00:00:" + String(Math.floor(fr / FPS)).padStart(2, "0") + ":" + String(fr % FPS).padStart(2, "0") + "  ·  120 BPM";
      Array.prototype.forEach.call(document.querySelectorAll(".br path"), function (p, i) {
        var len = 180; p.setAttribute("stroke-dasharray", len);
        p.setAttribute("stroke-dashoffset", (len * (1 - prog(t, 0.25 + i * 0.08, 0.7, E.io))).toFixed(1));
      });
      Array.prototype.forEach.call(document.querySelectorAll(".hud-t"), function (el, i) { el.style.opacity = prog(t, 0.5 + i * 0.06, 0.4, E.out2).toFixed(3); });
      var g = document.querySelector("#grain .tex"), gh = hashi(fr + 17);
      if (g) g.style.transform = "translate(" + ((gh % 31) - 15) + "%," + (((gh >>> 8) % 31) - 15) + "%)";
    }

    /* ---------- camera: punches, flash, RGB split, shake on the hits ---------- */
    var push = $("push"), punchEl = $("punch"), shakeEl = $("shake"), flashEl = $("flash"), camera = $("camera");
    var rgbR = $("rgb-r"), rgbB = $("rgb-b");
    function cam(t) {
      var pu = 1;
      for (var i = 0; i < cfg.drift.length; i++) { var d = cfg.drift[i]; if (t >= d[0] && t < d[1]) pu = 1 + 0.03 * E.io((t - d[0]) / (d[1] - d[0])); }
      push.style.transform = "scale(" + pu.toFixed(4) + ")";
      var punch = 1, flash = 0, split = 0, sx = 0, sy = 0;
      for (var h = 0; h < cfg.hits.length; h++) {
        var at = H[cfg.hits[h][0]], stn = cfg.hits[h][1], dd = t - at;
        if (!has(at) || dd < 0 || dd > 0.45) continue;
        punch = Math.max(punch, 1 + 0.05 * stn * (1 - E.expo(clamp(dd / 0.42, 0, 1))));
        flash = Math.max(flash, 0.22 * stn * (1 - E.out2(clamp(dd / 0.2, 0, 1))));
        split = Math.max(split, 20 * stn * (1 - E.out2(clamp(dd / 0.3, 0, 1))));
        if (stn >= 0.8) { var fi = Math.floor((dd - 0.02) * FPS); if (fi === 0) { sx = 14 * stn; sy = -8 * stn; } else if (fi === 1) { sx = -10 * stn; sy = 6 * stn; } }
      }
      punchEl.style.transform = "scale(" + punch.toFixed(4) + ")";
      shakeEl.style.transform = "translate(" + sx.toFixed(1) + "px," + sy.toFixed(1) + "px)";
      flashEl.style.opacity = flash.toFixed(3);
      camera.style.filter = split > 0.4 ? "url(#rgbsplit)" : "none";
      rgbR.setAttribute("dx", (-split).toFixed(2)); rgbB.setAttribute("dx", split.toFixed(2));
    }

    /* ---------- the scenes ---------- */
    function scenes(t) {
      // 0: CUTTING-EDGE.
      slam($("edge"), t, H.edge, { from: 1.7, d: 0.3 }); glitch($("edge"), t, H.edge + 0.03, 22);

      // 1: it lives on your PC
      appear($("local-shot"), t, H.local, { d: 0.45, dx: -60, dy: 0 });
      appear($("room"), t, H.local + 0.1, { d: 0.5, dy: 0, s0: 0.85 });
      ["tag-email", "tag-files", "tag-mem"].forEach(function (id, i) { appear($(id), t, H.local + 0.35 + i * 0.12, { d: 0.35, dy: 0, s0: 1.8, e: E.expo }); });
      appear($("room-label"), t, H.tagLocal, { d: 0.3, dy: 10 });
      appear($("tl-local"), t, H.tagLocal, { d: 0.3, dy: 10 });
      appear($("tl-net"), t, H.tagNet, { d: 0.3, dy: 10 });

      // 2: focus
      appear($("focus-run"), t, H.focusCard, { d: 0.45, dy: 60, e: E.back });
      // the real card, running on target, then off target the moment YouTube is in front
      appear($("focus-drift"), t, H.distract - 0.1, { d: 0.12, dy: 0 });
      slam($("focus-rep"), t, H.report, { from: 1.25, d: 0.35 });
      appear($("tl-focus"), t, H.focusCard + 0.4, { d: 0.3, dy: 10 });

      // 3: tell me when
      appear($("tell-card"), t, H.tellCard, { d: 0.45, dy: 60, e: E.back });
      appear($("tell-ok"), t, H.tellOk, { d: 0.3, dy: 0, s0: 0.7, e: E.back });
      appear($("phone-t"), t, H.ring - 0.35, { d: 0.45, dy: 120, e: E.out3 });
      appear($("notif-t"), t, H.ring, { d: 0.3, dy: -30, e: E.back });
      ["ring-a", "ring-b"].forEach(function (id, i) {
        var el = $(id); if (!el) return;
        var at = i ? H.ring2 : H.ring, d = t - at;
        el.style.opacity = d < 0 || d > 0.7 ? "0" : (1 - d / 0.7).toFixed(3);
        el.style.transform = "scale(" + (0.6 + 0.9 * clamp(d / 0.7, 0, 1)).toFixed(3) + ")";
      });
      var ph = $("phone-t");
      if (ph && t >= H.ring && t < H.stop) ph.style.transform += " rotate(" + (Math.sin(t * 90) * 1.6 * (Math.floor((t - H.ring) * 4) % 2 ? 1 : 0.3)).toFixed(2) + "deg)";
      appear($("tl-tell"), t, H.tellCard + 0.4, { d: 0.3, dy: 10 });

      // 4: stop everything
      ["key-alt", "key-shift", "key-x"].forEach(function (id, i) { slam($(id), t, H.stop + i * 0.05, { from: 1.9, d: 0.18 }); });
      appear($("toast"), t, H.toast, { d: 0.35, dx: 80, dy: 0 });
      appear($("phone-s"), t, H.phoneStop, { d: 0.4, dy: 100 });
      appear($("tl-stop"), t, H.toast, { d: 0.3, dy: 10 });

      // 5: and it still asks first
      slam($("asks"), t, H.asksLine, { from: 1.4 }); glitch($("asks"), t, H.asksLine + 0.04, 14);
      appear($("mail-card"), t, H.mailCard, { d: 0.45, dy: 60, e: E.back });
      appear($("ready-mail"), t, H.asksLine + 0.5, { d: 0.3, dy: 8 });
      appear($("hello"), t, H.hello, { d: 0.35, dy: 0, s0: 0.92, e: E.back });
      appear($("phone-f"), t, H.finger - 0.3, { d: 0.4, dy: 100 });
      var ring = $("fp-ring");
      if (ring) { var L = 2 * Math.PI * 54; ring.setAttribute("stroke-dasharray", L.toFixed(1)); ring.setAttribute("stroke-dashoffset", (L * (1 - prog(t, H.finger, H.ok - H.finger - 0.1, E.io))).toFixed(1)); }
      appear($("approved"), t, H.ok, { d: 0.3, dy: 0, s0: 0.7, e: E.back });
      appear($("tl-asks"), t, H.mailCard + 0.6, { d: 0.3, dy: 10 });

      // 6: instant answers, the model asleep
      appear($("timer-shot"), t, H.answer - 0.5, { d: 0.4, dx: 60, dy: 0 });
      appear($("tl-instant"), t, H.noModel, { d: 0.3, dy: 10 });
      appear($("asleep"), t, H.instant + 0.2, { d: 0.3, dy: 0 });

      // 7: it learns you
      appear($("mem-saved"), t, H.memory, { d: 0.45, dy: 60, e: E.back });
      press($("press-erase"), t, H.erase);
      appear($("mem-sens"), t, H.sensitive, { d: 0.45, dx: 80, dy: 0, e: E.back });
      appear($("tl-learn"), t, H.memory + 0.5, { d: 0.3, dy: 10 });

      // 8: your rules
      appear($("scrim"), t, H.outro, { d: 0.3, dy: 0 });
      [["o1", H.o1], ["o2", H.pc], ["o3", H.rules]].forEach(function (o) { slam($(o[0]), t, o[1], { from: 1.6, d: 0.4 }); glitch($(o[0]), t, o[1] + 0.03, 14); });
      appear($("tl-ready"), t, H.ready, { d: 0.4, dy: 10 });
      slam($("wordmark"), t, H.logo, { from: 1.35, d: 0.6 });
      $("fade").style.opacity = prog(t, cfg.dur - 0.7, 0.7, E.in2).toFixed(3);
    }

    function render(t) { drawHero(t); scenes(t); captions(t); hud(t); cam(t); }
    var clock = { t: 0 };
    tl.to(clock, { t: cfg.dur, duration: cfg.dur, ease: "none", onUpdate: function () { render(clock.t); } }, 0);
    render(0);
    window.__timelines = window.__timelines || {};
    window.__timelines[cfg.id] = tl;
  }

  window.FILM = { run: run };
})();
