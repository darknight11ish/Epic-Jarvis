/* Jarvis v5, "A day with Jarvis": the per-frame engine for both cuts.

   One continuous shot. The camera glides along a single strip of the day,
   station by station, and never cuts. A ribbon of hours runs along the strip
   with the reactor riding it as the playhead, and the sky, the ink and the
   reactor's glow all follow the hour under the playhead: dawn, day, dusk,
   night. index.html runs the strip left to right; vertical.html runs it top
   to bottom.

   Same contract as v3 and v4: one paused GSAP tween advances a clock and
   calls render(t); every visible value is a pure function of t, so a seek to
   any frame equals playing up to it. Scenes key off window.TIMING.hits, the
   table the score is written from. */
(function () {
  "use strict";

  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function lerp(a, b, k) { return a + (b - a) * k; }
  var E = {
    lin: function (k) { return k; },
    out2: function (k) { return 1 - (1 - k) * (1 - k); },
    out3: function (k) { return 1 - Math.pow(1 - k, 3); },
    in2: function (k) { return k * k; },
    io: function (k) { return k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2; },
    soft: function (k) { return k * k * (3 - 2 * k); },
    back: function (k) { var c = 1.4; return 1 + (c + 1) * Math.pow(k - 1, 3) + c * Math.pow(k - 1, 2); }
  };
  function prog(t, t0, d, e) { return (e || E.out3)(clamp((t - t0) / d, 0, 1)); }
  function $(id) { return document.getElementById(id); }
  function has(v) { return typeof v === "number" && !isNaN(v); }

  /* ---------- colour ---------- */
  function hex(c) { return [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)]; }
  function mixHex(a, b, k) {
    var A = hex(a), B = hex(b);
    return "rgb(" + Math.round(lerp(A[0], B[0], k)) + "," + Math.round(lerp(A[1], B[1], k)) + "," + Math.round(lerp(A[2], B[2], k)) + ")";
  }
  // The sky by the hour: [hour, top, horizon, sun glow].
  var SKY = [
    [5.5, "#2b3252", "#c98f86", "#ffb27a"],
    [6.5, "#8fa6c9", "#f4c7a1", "#ffc58a"],
    [8.0, "#b6d0e8", "#f6e7d3", "#fff0c8"],
    [12.0, "#a9cbe8", "#f4efe6", "#fff6d8"],
    [15.5, "#b9cde0", "#f4e2c4", "#ffe3a8"],
    [18.0, "#6f73a6", "#d0917f", "#ffb07a"],
    [19.5, "#2a2e5c", "#5e4263", "#ff9aa0"],
    [21.0, "#161c3a", "#2e3163", "#9fb8ff"],
    [24.0, "#0a0e1f", "#171a36", "#8aa6ff"]
  ];
  function skyAt(h) {
    var i = 0;
    while (i < SKY.length - 2 && h >= SKY[i + 1][0]) i++;
    var a = SKY[i], b = SKY[i + 1], k = E.soft(clamp((h - a[0]) / (b[0] - a[0]), 0, 1));
    return { top: mixHex(a[1], b[1], k), low: mixHex(a[2], b[2], k), sun: mixHex(a[3], b[3], k) };
  }

  /* ---------- building blocks ---------- */
  // Rise in at t0 (from dx, dy), optionally out at o.out. Hidden before t0.
  function appear(el, t, t0, o) {
    if (!el || !has(t0)) return;
    o = o || {};
    var d = o.d || 0.5, dy = o.dy === undefined ? 24 : o.dy, dx = o.dx || 0;
    var kin = t < t0 ? 0 : prog(t, t0, d, o.e || E.out3);
    var kout = has(o.out) ? 1 - prog(t, o.out, o.outD || 0.3, E.in2) : 1;
    el.style.opacity = t < t0 ? "0" : (kin * kout).toFixed(3);
    el.style.transform = "translate(" + (dx * (1 - kin)).toFixed(1) + "px," + (dy * (1 - kin)).toFixed(1) + "px)" +
      (o.s0 ? " scale(" + lerp(o.s0, 1, kin).toFixed(4) + ")" : "");
    el.style.filter = o.blur && kin < 1 ? "blur(" + (o.blur * (1 - kin)).toFixed(1) + "px)" : "none";
  }
  // Type a line in, word by word, over d seconds.
  function words(el, t, t0, d) {
    if (!el || !has(t0)) return;
    var full = el.getAttribute("data-text");
    if (full === null) { full = el.textContent; el.setAttribute("data-text", full); }
    var w = full.split(" "), n = t < t0 ? 0 : Math.ceil(clamp((t - t0) / (d || 0.6), 0, 1) * w.length);
    el.style.opacity = t < t0 ? "0" : "1";
    // Unshown words keep their space (visibility), so the line never reflows.
    el.innerHTML = w.map(function (x, i) { return i < n ? x : '<span class="ghost">' + x + "</span>"; }).join(" ");
  }
  // A press on a button: a soft ring that blooms and fades.
  function press(el, t, at) {
    if (!el || !has(at)) return;
    var d = t - at;
    if (d < -0.15 || d > 0.7) { el.style.opacity = "0"; return; }
    el.style.opacity = (d < 0 ? prog(t, at - 0.15, 0.15, E.out2) : 1 - prog(t, at + 0.3, 0.4, E.in2)).toFixed(3);
    el.style.transform = "scale(" + (1 + 0.06 * clamp(d / 0.4, 0, 1)).toFixed(4) + ")";
  }
  // Cross-fade a stack of images: list of [time, id]; the last one reached shows.
  function swap(t, list, d) {
    var cur = -1;
    for (var i = 0; i < list.length; i++) if (t >= list[i][0]) cur = i;
    for (var j = 0; j < list.length; j++) {
      var el = $(list[j][1]); if (!el) continue;
      var on = j === cur ? prog(t, list[j][0], d || 0.25, E.out2) : (j === cur - 1 ? 1 : 0);
      if (j < cur - 1) on = 0;
      el.style.opacity = on.toFixed(3);
    }
  }

  function run(cfg) {
    var H = cfg.H, R = window.REACTOR, AD = window.AUDIO_DATA || { fps: 30, low: [0] };
    var X = cfg.axis === "y" ? 1 : 0, STRIDE = cfg.stride, ST = cfg.stations;
    gsap.defaults({ lazy: false });
    var tl = gsap.timeline({ paused: true });
    function audioLow(t) { var i = clamp(Math.floor(t * AD.fps), 0, AD.low.length - 1); return AD.low[i] || 0; }

    /* ---------- the camera: dwell with a slow drift, glide between stations ---------- */
    var DRIFT = cfg.drift || 22;
    var keys = [];
    ST.forEach(function (s, i) {
      keys.push([s.at[0], i * STRIDE - DRIFT, i === 0 ? E.lin : E.soft]);
      keys.push([s.at[1], i * STRIDE + DRIFT, E.lin]);
    });
    function camAt(t) {
      if (t <= keys[0][0]) return keys[0][1];
      for (var i = 1; i < keys.length; i++) {
        if (t <= keys[i][0]) {
          var a = keys[i - 1], b = keys[i];
          return lerp(a[1], b[1], b[2](clamp((t - a[0]) / (b[0] - a[0]), 0, 1)));
        }
      }
      return keys[keys.length - 1][1];
    }
    // Where each hour sits on the strip: piecewise-linear through the stations.
    function posOfHour(h) {
      if (h <= ST[0].hour) return (h - ST[0].hour) * STRIDE / 1.5;
      for (var i = 1; i < ST.length; i++) {
        if (h <= ST[i].hour) return lerp((i - 1) * STRIDE, i * STRIDE, (h - ST[i - 1].hour) / (ST[i].hour - ST[i - 1].hour));
      }
      return (ST.length - 1) * STRIDE + (h - ST[ST.length - 1].hour) * STRIDE / 1.5;
    }
    function hourAt(p) {
      if (p <= 0) return ST[0].hour + p * 1.5 / STRIDE;
      var i = Math.floor(p / STRIDE);
      if (i >= ST.length - 1) return ST[ST.length - 1].hour + (p - (ST.length - 1) * STRIDE) * 1.5 / STRIDE;
      return lerp(ST[i].hour, ST[i + 1].hour, (p - i * STRIDE) / STRIDE);
    }

    /* ---------- the ribbon of hours ---------- */
    var ribbon = $("ribbon"), labels = [];
    (function buildRibbon() {
      var h0 = Math.floor(ST[0].hour - 1), h1 = Math.ceil(ST[ST.length - 1].hour + 1);
      for (var h = h0; h <= h1 * 2; h++) {
        var hh = h / 2; if (hh < h0 || hh > h1) continue;
        var tick = document.createElement("div");
        tick.className = "tick" + (hh % 1 ? " half" : "");
        tick.style[X ? "top" : "left"] = posOfHour(hh).toFixed(1) + "px";
        if (!(hh % 1)) { var lab = document.createElement("span"); lab.textContent = (hh % 24) + ":00"; tick.appendChild(lab); labels.push([posOfHour(hh), lab]); }
        ribbon.appendChild(tick);
      }
    })();

    /* ---------- the reactor, riding the ribbon ---------- */
    var sunS = R.surface($("sun"), "arc");
    function segAt(list, t) { var k = 0; for (var i = 0; i < list.length; i++) { if (t >= list[i][0]) k = i; else break; } return k; }
    function sunPhase(t) {
      var ph = 0, sp = null, dt = 1 / 120;
      for (var x = 0; x < t; x += dt) {
        var target = R.speedOf("arc", cfg.hero[segAt(cfg.hero, x)][1]);
        if (sp === null) sp = target;
        sp += (target - sp) * Math.min(1, dt / 0.35);
        ph += sp * Math.min(dt, t - x);
      }
      return ph;
    }
    function ampFor(state, t) {
      if (state === "listening") return clamp(0.3 + 0.6 * Math.abs(Math.sin(t * 6.7)) * (0.55 + 0.45 * Math.sin(t * 2.3 + 1)), 0, 1);
      if (state === "speaking") return clamp(0.25 + 0.6 * Math.pow(Math.abs(Math.sin(t * 8.9) * Math.sin(t * 3.1 + 0.4)), 0.7), 0, 1);
      return 0.2;
    }
    function sunColour(i, t) {
      var s = cfg.hero[i], c = R.colours(s[1], t, ampFor(s[1], t));
      if (i > 0) {
        var k = (t - s[0]) / 0.35;
        if (k < 1) { var p = R.colours(cfg.hero[i - 1][1], t, ampFor(cfg.hero[i - 1][1], t)), e = E.soft(k); c = { a: R.mix(p.a, c.a, e), b: R.mix(p.b, c.b, e) }; }
      }
      return c;
    }
    var sunWrap = $("sun-wrap"), halo = $("halo");
    function drawSun(t, sky) {
      var si = segAt(cfg.hero, t), st = cfg.hero[si][1];
      var sleep = st === "standby";
      sunS.g.setTransform(1, 0, 0, 1, 0, 0); sunS.g.clearRect(0, 0, sunS.canvas.width, sunS.canvas.height);
      R.draw(sunS, { t: t, phase: sunPhase(t), state: st, amp: ampFor(st, t), beat: audioLow(t) * 0.6,
                     col: sunColour(si, t), glow: (sleep ? 0.06 : st === "idle" ? 0.2 : 0.3) + audioLow(t) * 0.3, clear: false, quality: 1.2 });
      // The ending: the playhead leaves the ribbon and settles in the middle, bigger.
      var o = cfg.sunPath(t);
      sunWrap.style.transform = "translate(" + o.x.toFixed(1) + "px," + o.y.toFixed(1) + "px) scale(" + o.s.toFixed(4) + ")";
      sunWrap.style.opacity = o.a.toFixed(3);
      halo.style.transform = "translate(" + o.x.toFixed(1) + "px," + o.y.toFixed(1) + "px)";
      halo.style.background = "radial-gradient(circle, " + sky.sun + " 0%, rgba(255,255,255,0) 68%)";
      halo.style.opacity = (sleep ? 0.25 : 0.75).toFixed(2);
    }

    /* ---------- sky, ink, world ---------- */
    var sky = $("sky"), world = $("world"), root = document.documentElement;
    var NIGHT = cfg.nightFrom || [18.9, 19.9];
    function place(t) {
      var p = camAt(t), h = hourAt(p);
      var s = skyAt(h);
      sky.style.background = "linear-gradient(" + (X ? "180deg" : "180deg") + ", " + s.top + " 0%, " + s.low + " 100%)";
      var n = E.soft(clamp((h - NIGHT[0]) / (NIGHT[1] - NIGHT[0]), 0, 1));
      root.style.setProperty("--ink", mixHex("#1d1a17", "#f4ecdf", n));
      root.style.setProperty("--ink2", mixHex("#5a524a", "#b9b3c9", n));
      root.style.setProperty("--warm", mixHex("#a4561f", "#f2a66b", n));
      root.style.setProperty("--rule", n > 0.5 ? "rgba(244,236,223,.35)" : "rgba(29,26,23,.28)");
      world.style.transform = X ? "translate3d(0," + (-p).toFixed(1) + "px,0)" : "translate3d(" + (-p).toFixed(1) + "px,0,0)";
      // An hour label gives way as it passes under the reactor.
      labels.forEach(function (l) { l[1].style.opacity = clamp((Math.abs(l[0] - p) - 70) / 90, 0, 1).toFixed(3); });
      ribbon.style.transform = X ? "translate3d(0," + (-p).toFixed(1) + "px,0)" : "translate3d(" + (-p).toFixed(1) + "px,0,0)";
      return { p: p, h: h, sky: s, night: n };
    }

    /* ---------- captions: every spoken line, labelled ---------- */
    var cap = $("cap"), capWho = $("cap-who"), capText = $("cap-text");
    function captions(t) {
      if (!cap) return;
      var c = null;
      for (var i = 0; i < cfg.caps.length; i++) if (t >= cfg.caps[i][0] && t < cfg.caps[i][1]) c = cfg.caps[i];
      if (!c) { cap.style.opacity = "0"; return; }
      capWho.textContent = c[2] === "you" ? "You" : "Jarvis";
      cap.className = c[2];
      if (capText.getAttribute("data-text") !== c[3]) { capText.setAttribute("data-text", c[3]); }
      words(capText, t, c[0], c[4] || 0.6);
      cap.style.opacity = (prog(t, c[0], 0.15, E.out2) * (1 - prog(t, c[1] - 0.15, 0.15, E.in2))).toFixed(3);
    }

    function render(t) {
      var v = place(t);
      drawSun(t, v.sky);
      cfg.scenes(t, { appear: appear, words: words, press: press, swap: swap, prog: prog, E: E, $: $, H: H, view: v, clamp: clamp, lerp: lerp });
      captions(t);
      $("fade").style.opacity = Math.max(1 - prog(t, 0, 0.5, E.out2), prog(t, cfg.dur - 0.6, 0.6, E.in2)).toFixed(3);
    }
    var clock = { t: 0 };
    tl.to(clock, { t: cfg.dur, duration: cfg.dur, ease: "none", onUpdate: function () { render(clock.t); } }, 0);
    render(0);
    window.__timelines = window.__timelines || {};
    window.__timelines[cfg.id] = tl;
  }

  window.DAY = { run: run, E: E, prog: prog };
})();
