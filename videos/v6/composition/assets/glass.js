/* Jarvis v6, "Your AI": the per-frame engine for both cuts.

   "Glass & Light": a graphite dark where the reactor (the app's own face,
   assets/reactor.js) is the only light. Real app screens sit on glass slabs
   rim-lit in the reactor's state colour. Effects live on the cuts and the
   edges, never on words someone is reading:
     - the iris: the next scene opens out of the reactor's core (8 frames),
       with a thin colour fringe on its edge only;
     - particles: the ignition at frame 0 and the settle at the end;
     - the tracing beam: a light that runs once round the one line that
       matters, then rests as a soft highlight;
     - the touch ring: where a finger taps the drawn phone;
     - focus-resolve: headlines arrive from a blur in 6 frames, then hold.

   Same contract as v3 to v5: one paused GSAP tween drives a clock, and
   render(t) sets every visible value as a pure function of t, so a seek to
   any frame equals playing up to it. Everything keys off window.TIMING.hits,
   the table the score is written from. */
(function () {
  "use strict";
  var FPS = 30;

  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function lerp(a, b, k) { return a + (b - a) * k; }
  var E = {
    lin: function (k) { return k; },
    out2: function (k) { return 1 - (1 - k) * (1 - k); },
    out3: function (k) { return 1 - Math.pow(1 - k, 3); },
    out5: function (k) { return 1 - Math.pow(1 - k, 5); },
    in2: function (k) { return k * k; },
    io: function (k) { return k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2; },
    soft: function (k) { return k * k * (3 - 2 * k); }
  };
  function prog(t, t0, d, e) { return (e || E.out3)(clamp((t - t0) / d, 0, 1)); }
  function $(id) { return document.getElementById(id); }
  function has(v) { return typeof v === "number" && !isNaN(v); }
  // Deterministic noise (no Math.random anywhere).
  function hash(n) { n = Math.imul(n ^ (n >>> 16), 0x45d9f3b); n = Math.imul(n ^ (n >>> 16), 0x45d9f3b); return ((n ^ (n >>> 16)) >>> 0) / 4294967296; }

  /* ---------- building blocks ---------- */
  // A scene layer: shown from a to b; opens with the iris when o.iris.
  function within(t, a, b) { return t >= a && t < b; }
  // Headline focus-resolve: from a 12 px blur and 104 % to sharp in 0.2 s, then still.
  function resolve(el, t, t0, o) {
    if (!el || !has(t0)) return;
    o = o || {};
    var k = t < t0 ? 0 : prog(t, t0, o.d || 0.2, E.out3);
    var kout = has(o.out) ? 1 - prog(t, o.out, o.outD || 0.15, E.in2) : 1;
    el.style.opacity = (t < t0 ? 0 : k * kout).toFixed(3);
    el.style.filter = k < 1 ? "blur(" + (12 * (1 - k)).toFixed(1) + "px)" : "none";
    el.style.transform = "translate(" + ((o.dx || 0) * (1 - k)).toFixed(1) + "px," + ((o.dy || 0) * (1 - k)).toFixed(1) + "px) scale(" + lerp(1.04, 1, k).toFixed(4) + ")";
  }
  // Plain fade-and-rise, for chips and tags.
  function appear(el, t, t0, o) {
    if (!el || !has(t0)) return;
    o = o || {};
    var k = t < t0 ? 0 : prog(t, t0, o.d || 0.25, E.out3);
    var kout = has(o.out) ? 1 - prog(t, o.out, o.outD || 0.15, E.in2) : 1;
    el.style.opacity = (t < t0 ? 0 : k * kout).toFixed(3);
    el.style.transform = "translate(" + ((o.dx || 0) * (1 - k)).toFixed(1) + "px," + ((o.dy === undefined ? 14 : o.dy) * (1 - k)).toFixed(1) + "px)";
  }
  // A glass slab arrives: a small turn in depth and a blur, then flat and still.
  function slab(el, t, t0, o) {
    if (!el || !has(t0)) return;
    o = o || {};
    var k = t < t0 ? 0 : prog(t, t0, o.d || 0.35, E.out5);
    var kout = has(o.out) ? 1 - prog(t, o.out, 0.15, E.in2) : 1;
    var bump = 0;
    (o.bumps || []).forEach(function (b) { var d = t - b; if (d >= 0 && d < 0.25) bump = Math.max(bump, 0.014 * (1 - E.out2(d / 0.25))); });
    el.style.opacity = (t < t0 ? 0 : Math.min(1, k * 1.6) * kout).toFixed(3);
    el.style.transform = "perspective(1800px) translateX(" + (70 * (1 - k)).toFixed(1) + "px) rotateY(" + (-11 * (1 - k)).toFixed(2) + "deg) scale(" + (1 + bump).toFixed(4) + ")";
    el.style.filter = k < 1 ? "blur(" + (8 * (1 - k)).toFixed(1) + "px)" : "none";
    var sh = el.querySelector(".sheen");
    if (sh) { var s = clamp((t - t0) / 0.5, 0, 1); sh.style.opacity = s > 0 && s < 1 ? (Math.sin(s * Math.PI) * 0.5).toFixed(3) : "0"; sh.style.transform = "translateX(" + lerp(-60, 160, s).toFixed(1) + "%) skewX(-18deg)"; }
  }
  // Show one of a stack of images: list of [time, id]; the latest reached shows (hard cut, on the beat).
  function pick(t, list) {
    var cur = -1;
    for (var i = 0; i < list.length; i++) if (t >= list[i][0]) cur = i;
    for (var j = 0; j < list.length; j++) { var el = $(list[j][1]); if (el) el.style.opacity = j === cur ? "1" : "0"; }
  }
  // The tracing beam: a light runs once round a box, then rests as a soft highlight.
  function beam(el, t, t0, box, host) {
    if (!el || !has(t0)) return;
    if (t < t0) { el.style.opacity = "0"; return; }
    var w = host.offsetWidth, h = host.offsetHeight, pad = 10;
    var x = box.x * w - pad, y = box.y * h - pad, bw = box.w * w + 2 * pad, bh = box.h * h + 2 * pad;
    el.style.opacity = "1";
    el.setAttribute("viewBox", "0 0 " + w + " " + h);
    var r = el.querySelector(".trace"), f = el.querySelector(".rest");
    [r, f].forEach(function (n) { n.setAttribute("x", x.toFixed(1)); n.setAttribute("y", y.toFixed(1)); n.setAttribute("width", bw.toFixed(1)); n.setAttribute("height", bh.toFixed(1)); });
    var L = 2 * (bw + bh), k = prog(t, t0, 0.45, E.io);
    r.setAttribute("stroke-dasharray", (L * 0.22).toFixed(1) + " " + L.toFixed(1));
    r.setAttribute("stroke-dashoffset", (-L * k).toFixed(1));
    r.style.opacity = (1 - prog(t, t0 + 0.4, 0.2, E.in2)).toFixed(3);
    f.style.opacity = (prog(t, t0 + 0.3, 0.25, E.out2)).toFixed(3);
  }
  // A finger's tap on the drawn phone.
  function tap(el, t, at) {
    if (!el || !has(at)) return;
    var d = t - at;
    if (d < -0.12 || d > 0.5) { el.style.opacity = "0"; return; }
    var k = clamp(d / 0.5, 0, 1);
    el.style.opacity = (d < 0 ? prog(t, at - 0.12, 0.12, E.out2) : 1 - k).toFixed(3);
    el.style.transform = "translate(-50%,-50%) scale(" + (d < 0 ? 0.8 : lerp(0.8, 1.6, E.out3(k))).toFixed(3) + ")";
  }

  function run(cfg) {
    var H = cfg.H, R = window.REACTOR, AD = window.AUDIO_DATA || { fps: 30, low: [0], rms: [0] };
    gsap.defaults({ lazy: false });
    var tl = gsap.timeline({ paused: true });
    var W = cfg.w, HH = cfg.h;
    function env(name, t) { var a = AD[name] || [0]; return a[clamp(Math.floor(t * (AD.fps || 30)), 0, a.length - 1)] || 0; }

    /* ---------- the reactor: the only light ---------- */
    var coreWrap = $("core-wrap"), coreS = R.surface($("core"), "arc"), glow = $("backlight");
    function segAt(list, t) { var k = 0; for (var i = 0; i < list.length; i++) { if (t >= list[i][0]) k = i; else break; } return k; }
    function frozen(t) { return has(H.stop) && t >= H.stop && t < H.silenceEnd; }
    function phaseAt(t) {
      var ph = 0, sp = null, dt = 1 / 120;
      for (var x = 0; x < t; x += dt) {
        if (frozen(x)) continue;
        var target = R.speedOf("arc", cfg.hero[segAt(cfg.hero, x)][1]);
        if (x < 1.2) target *= 1 + 4 * Math.exp(-x / 0.3);          // the ignition spin
        if (sp === null) sp = target;
        sp += (target - sp) * Math.min(1, dt / 0.2);
        ph += sp * Math.min(dt, t - x);
      }
      return ph;
    }
    function ampFor(state, t) {
      if (state === "listening") return clamp(0.3 + 0.6 * Math.abs(Math.sin(t * 6.7)) * (0.55 + 0.45 * Math.sin(t * 2.3 + 1)), 0, 1);
      if (state === "speaking") return clamp(0.25 + 0.6 * Math.pow(Math.abs(Math.sin(t * 8.9) * Math.sin(t * 3.1 + 0.4)), 0.7), 0, 1);
      return 0.2;
    }
    function colourAt(i, t) {
      var s = cfg.hero[i], c = R.colours(s[1], t, ampFor(s[1], t));
      if (i > 0) {
        var k = (t - s[0]) / 0.2;
        if (k < 1) { var p = R.colours(cfg.hero[i - 1][1], t, ampFor(cfg.hero[i - 1][1], t)), e = E.soft(k); c = { a: R.mix(p.a, c.a, e), b: R.mix(p.b, c.b, e) }; }
      }
      return c;
    }
    function drawCore(t) {
      var tt = frozen(t) ? H.stop : t, si = segAt(cfg.hero, tt), st = cfg.hero[si][1], col = colourAt(si, tt);
      var p = cfg.corePath(t);
      coreS.g.setTransform(1, 0, 0, 1, 0, 0); coreS.g.clearRect(0, 0, coreS.canvas.width, coreS.canvas.height);
      R.draw(coreS, { t: tt, phase: phaseAt(tt), state: st, amp: ampFor(st, tt), beat: env("low", t) * 0.5, col: col,
                      glow: 0.28 + env("low", t) * 0.25, clear: false, quality: 1.2 });
      coreWrap.style.transform = "translate(" + p.x.toFixed(1) + "px," + p.y.toFixed(1) + "px) scale(" + p.s.toFixed(4) + ")";
      coreWrap.style.opacity = p.a.toFixed(3);
      coreWrap.style.filter = p.blur ? "blur(" + p.blur.toFixed(1) + "px)" : "none";
      // The backlight: the reactor's colour, spilling into the dark behind the glass.
      var dim = frozen(t) ? 0.35 : 1;
      glow.style.transform = "translate(" + p.x.toFixed(1) + "px," + p.y.toFixed(1) + "px) scale(" + (p.s * (p.halo || 1)).toFixed(4) + ")";
      glow.style.background = "radial-gradient(circle, " + col.a + " 0%, rgba(0,0,0,0) 58%)";
      glow.style.opacity = (0.55 * (p.glow === undefined ? 0.5 : p.glow) * dim * (0.85 + env("low", t) * 0.3)).toFixed(3);
      document.documentElement.style.setProperty("--rim", col.a);
      return { col: col, p: p };
    }

    /* ---------- particles: the ignition and the settle ---------- */
    var pc = $("particles"), pg = pc.getContext("2d"), N = cfg.particles || 700;
    var P = [];
    for (var i = 0; i < N; i++) P.push({ a: hash(i * 3 + 1) * Math.PI * 2, r: 0.25 + 0.75 * Math.pow(hash(i * 3 + 2), 0.6), z: hash(i * 3 + 3), s: 1.4 + 3.2 * hash(i * 7 + 5) });
    function particles(t, core) {
      pg.setTransform(1, 0, 0, 1, 0, 0); pg.clearRect(0, 0, W, HH);
      var cx = cfg.coreHome.x + core.p.x, cy = cfg.coreHome.y + core.p.y, far = Math.hypot(W, HH) * 0.62;
      var bursts = [];
      // Ignition: outward from the core at frame 0.
      if (t < 1.4) bursts.push({ k: E.out3(clamp(t / 1.3, 0, 1)), out: true, fade: 1 - prog(t, 0.5, 0.9, E.in2) });
      // The settle: inward to the core at the end.
      if (has(H.end) && t >= H.end && t < H.end + 1.4) bursts.push({ k: E.out3(clamp((t - H.end) / 1.2, 0, 1)), out: false, fade: 1 - prog(t, H.end + 0.8, 0.6, E.in2) });
      if (!bursts.length) return;
      pg.globalCompositeOperation = "lighter";
      bursts.forEach(function (b) {
        for (var j = 0; j < N; j++) {
          var q = P[j], d = b.out ? lerp(30, far * q.r, b.k) : lerp(far * q.r, 40 + 30 * q.z, b.k);
          var a = q.a + (b.out ? 0.35 : -0.35) * b.k * (1 - q.r);
          var x = cx + Math.cos(a) * d, y = cy + Math.sin(a) * d * 0.9;
          var al = b.fade * (0.45 + 0.55 * q.z);
          if (al <= 0.01) continue;
          pg.fillStyle = q.z > 0.7 ? "rgba(238,243,247," + al.toFixed(3) + ")" : core.col.a;
          pg.globalAlpha = q.z > 0.7 ? 1 : al;
          pg.fillRect(x, y, q.s, q.s);
        }
      });
      pg.globalAlpha = 1;
      pg.globalCompositeOperation = "source-over";
    }

    /* ---------- dust: slow depth in the dark, never near the words ---------- */
    var dc = $("dust"), dg = dc.getContext("2d");
    function dust(t) {
      dg.setTransform(1, 0, 0, 1, 0, 0); dg.clearRect(0, 0, W, HH);
      for (var k = 0; k < 70; k++) {
        var z = 0.3 + 0.7 * hash(k * 11 + 3), x = (hash(k * 11 + 1) * W + t * 14 * z) % W, y = (hash(k * 11 + 2) * HH - t * 6 * z + HH) % HH;
        dg.fillStyle = "rgba(200,215,230," + (0.05 + 0.12 * z).toFixed(3) + ")";
        dg.fillRect(x, y, 1 + z * 1.6, 1 + z * 1.6);
      }
    }

    /* ---------- the iris: the next scene opens out of the reactor's core ---------- */
    function iris(t) {
      var ring = $("iris-ring"), active = null;
      (cfg.irises || []).forEach(function (ir) { if (t >= ir.at && t < ir.at + 8 / FPS + 0.001) active = ir; });
      cfg.scenes.forEach(function (sc) {
        var el = $(sc.id); if (!el) return;
        var on = within(t, sc.a, sc.b);
        el.style.visibility = on ? "visible" : "hidden";
        if (!on) return;
        var ir = (cfg.irises || []).filter(function (x) { return x.scene === sc.id; })[0];
        if (ir && t < ir.at + 8 / FPS) {
          var k = E.in2(clamp((t - ir.at) / (8 / FPS), 0, 1)), r = lerp(0, Math.hypot(W, HH), k);
          el.style.clipPath = "circle(" + r.toFixed(1) + "px at " + ir.x + "px " + ir.y + "px)";
        } else el.style.clipPath = "none";
      });
      if (!active) { ring.style.opacity = "0"; return; }
      var k2 = E.in2(clamp((t - active.at) / (8 / FPS), 0, 1)), r2 = lerp(0, Math.hypot(W, HH), k2);
      ring.style.opacity = (1 - k2 * 0.6).toFixed(3);
      ring.style.left = active.x + "px"; ring.style.top = active.y + "px";
      ring.style.width = ring.style.height = (2 * r2).toFixed(1) + "px";
    }

    /* ---------- the stop: freeze and a light dip ---------- */
    function stopHit(t) {
      var dip = $("dip");
      if (!has(H.stop)) { dip.style.opacity = "0"; return; }
      var d = t - H.stop;
      dip.style.opacity = d < 0 ? "0" : d < 0.07 ? (d / 0.07 * 0.55).toFixed(3) : (0.55 * (1 - prog(t, H.stop + 0.07, (H.silenceEnd - H.stop) + 0.2, E.out2))).toFixed(3);
    }

    function render(t) {
      dust(t);
      var core = drawCore(t);
      particles(t, core);
      iris(t);
      stopHit(t);
      cfg.scene(t, { resolve: resolve, appear: appear, slab: slab, pick: pick, beam: beam, tap: tap, prog: prog, E: E, $: $, H: H, clamp: clamp, lerp: lerp });
      $("fade").style.opacity = prog(t, cfg.dur - 0.35, 0.35, E.in2).toFixed(3);
    }
    var clock = { t: 0 };
    tl.to(clock, { t: cfg.dur, duration: cfg.dur, ease: "none", onUpdate: function () { render(clock.t); } }, 0);
    render(0);
    window.__timelines = window.__timelines || {};
    window.__timelines[cfg.id] = tl;
  }

  window.GLASS = { run: run, E: E, prog: prog };
})();
