/* Jarvis v3: the per-frame engine shared by the landscape film (index.html)
   and the upright cut (vertical.html).

   Every visible value is a pure function of t. One GSAP tween advances a clock
   and calls render(t); nothing else animates. That is what keeps a seek to any
   frame identical to playing up to it, which the capture engine relies on.
   Scenes and captions are keyed to window.TIMING.hits, the same table the score
   is written from. An element or a hit a film does not have is simply skipped. */
(function () {
  "use strict";
  var FPS = 30;

  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function lerp(a, b, k) { return a + (b - a) * k; }
  var E = {
    lin: function (k) { return k; },
    out2: function (k) { return 1 - (1 - k) * (1 - k); },
    out3: function (k) { return 1 - Math.pow(1 - k, 3); },
    in2: function (k) { return k * k; },
    io: function (k) { return k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2; },
    // A small settle: overshoots about 3% and comes back.
    settle: function (k) { var c = 1.4; return 1 + (c + 1) * Math.pow(k - 1, 3) + c * Math.pow(k - 1, 2); }
  };
  function prog(t, t0, d, e) { return (e || E.out3)(clamp((t - t0) / d, 0, 1)); }
  function $(id) { return document.getElementById(id); }
  function has(v) { return typeof v === "number" && !isNaN(v); }

  /* Fade in at t0 (rising dy px), optionally out at t1. Hard-hidden before t0. */
  function appear(el, t, t0, o) {
    if (!el || !has(t0)) return;
    o = o || {};
    var d = o.d || 0.5, dy = o.dy === undefined ? 24 : o.dy, dx = o.dx || 0;
    var kin = t < t0 ? 0 : prog(t, t0, d, o.e || E.out3);
    var kout = has(o.out) ? 1 - prog(t, o.out, o.outD || 0.3, E.in2) : 1;
    var k = kin * kout;
    el.style.opacity = t < t0 ? "0" : k.toFixed(3);
    var up = has(o.out) && t >= o.out ? -(o.outDy || 0) * prog(t, o.out, o.outD || 0.3, E.in2) : 0;
    el.style.transform = "translate(" + (dx * (1 - kin)).toFixed(1) + "px," + (dy * (1 - kin) + up).toFixed(1) + "px)" +
      (o.s0 ? " scale(" + lerp(o.s0, 1, kin).toFixed(4) + ")" : "");
  }

  function run(cfg) {
    var H = cfg.H, R = window.REACTOR, AD = window.AUDIO_DATA;
    gsap.defaults({ lazy: false });
    var tl = gsap.timeline({ paused: true });

    function audioLow(t) { var i = clamp(Math.floor(t * AD.fps), 0, AD.low.length - 1); return AD.low[i] || 0; }

    /* ---------- the big reactor ---------- */
    var heroWrap = $("hero-wrap"), heroCv = $("hero");
    var heroS = R.surface(heroCv, "arc");
    function heroSeg(t) { var k = 0; for (var i = 0; i < cfg.hero.length; i++) { if (t >= cfg.hero[i][0]) k = i; else break; } return k; }
    // Integrated spin, so a state change eases the speed rather than jumping the angle.
    // A "cut" segment (the owner said "stop") snaps instead: everything holds still.
    function heroPhase(t) {
      var ph = 0, sp = null, dt = 1 / 120;
      for (var x = 0; x < t; x += dt) {
        var s = cfg.hero[heroSeg(x)];
        var target = R.speedOf("arc", s[1]) * (s[2] === "cut" ? 0.35 : 1);
        if (sp === null || s[2] === "cut" && x - s[0] < dt) sp = target;
        sp += (target - sp) * Math.min(1, dt / 0.25);
        ph += sp * Math.min(dt, t - x);
      }
      return ph;
    }
    function micAmp(t) { return clamp(0.3 + 0.6 * Math.abs(Math.sin(t * 6.7)) * (0.55 + 0.45 * Math.sin(t * 2.3 + 1)), 0, 1); }
    function voiceAmp(t) { return clamp(0.25 + 0.6 * Math.pow(Math.abs(Math.sin(t * 8.9) * Math.sin(t * 3.1 + 0.4)), 0.7), 0, 1); }
    function ampFor(state, t) { return state === "listening" ? micAmp(t) : state === "speaking" ? voiceAmp(t) : 0.2; }
    // State colours crossfade over 0.3 s (never on a "cut").
    function heroColour(i, t) {
      var s = cfg.hero[i], c = R.colours(s[1], t, ampFor(s[1], t));
      if (i > 0 && s[2] !== "cut") {
        var k = (t - s[0]) / 0.3;
        if (k < 1) {
          var p = R.colours(cfg.hero[i - 1][1], t, ampFor(cfg.hero[i - 1][1], t)), e = k * k * (3 - 2 * k);
          c = { a: R.mix(p.a, c.a, e), b: R.mix(p.b, c.b, e) };
        }
      }
      return c;
    }
    function heroFrame(t) {
      for (var i = 0; i < cfg.frames.length; i++) {
        var f = cfg.frames[i];
        if (t >= f[0] && t < f[1]) return { f: f, k: E.io(clamp((t - f[0]) / (f[1] - f[0]), 0, 1)) };
      }
      return null;
    }
    function drawHero(t) {
      var fr = heroFrame(t);
      if (!fr) { heroWrap.style.opacity = "0"; return; }
      var f = fr.f, frozen = has(H.stop) && t >= H.stop && t < (H.outro || 1e9);
      var tt = frozen ? H.stop : t;                         // "stop": the picture holds
      var k = frozen ? E.io(clamp((H.stop - f[0]) / (f[1] - f[0]), 0, 1)) : fr.k;
      var sc = lerp(f[4], f[5], k);
      var ignite = f[0] === 0 ? E.out3(clamp(t / 0.6, 0, 1)) : 1;
      heroWrap.style.opacity = String(f[6]);
      heroWrap.style.transform = "translate(" + f[2] + "px," + f[3] + "px) scale(" + sc.toFixed(4) + ")";
      heroWrap.style.clipPath = ignite < 1 ? "circle(" + (8 + 67 * ignite).toFixed(2) + "% at 50% 50%)" : "none";
      var si = heroSeg(t), state = cfg.hero[si][1];
      var active = state !== "idle";
      g2(heroS);
      var swell = has(H.outro) && t >= H.outro ? 0.25 * E.out2(clamp((t - H.outro) / 2.5, 0, 1)) : 0;
      R.draw(heroS, { t: tt, phase: heroPhase(tt), state: state, amp: frozen ? 0.1 : ampFor(state, tt), beat: audioLow(t) * 0.6,
                      col: heroColour(si, t), glow: (active ? 0.3 : 0.2) + audioLow(t) * 0.35 + swell, clear: false, quality: 1.2 });
    }
    function g2(s) { s.g.setTransform(1, 0, 0, 1, 0, 0); s.g.clearRect(0, 0, s.canvas.width, s.canvas.height); }

    /* ---------- the phone's own small reactor ---------- */
    var phoneCv = $("phone-face"), phoneS = phoneCv ? R.surface(phoneCv, "arc") : null;
    function drawPhone(t) {
      if (!phoneS || !has(H.cards)) return;
      var ok = t >= H.approved;
      var st = ok ? "idle" : "approval";
      g2(phoneS);
      R.draw(phoneS, { t: t, phase: t * R.speedOf("arc", st), state: st, amp: 0.2, beat: audioLow(t) * 0.4, glow: 0.35, clear: false, fxAge: Math.max(0, t - H.cards) });
    }

    /* ---------- captions ---------- */
    var cap = $("cap"), capWho = $("cap-who"), capText = $("cap-text");
    var capPrev = $("cap-prev"), capPrevText = $("cap-prev-text");
    var lastTyped = "";
    function captions(t) {
      var c = null;
      for (var i = 0; i < cfg.caps.length; i++) if (t >= cfg.caps[i][0] && t < cfg.caps[i][1]) c = cfg.caps[i];
      // The line Jarvis was cut off in, kept (dimmed) above "Stop." so it reads muted.
      var typeCap = null;
      cfg.caps.forEach(function (x) { if (x[4] === "type") typeCap = x; });
      if (capPrev && typeCap && c && c[4] === "big") {
        capPrev.style.opacity = "1";
        capPrevText.textContent = typedAt(typeCap, typeCap[1]) + "—";
      } else if (capPrev) capPrev.style.opacity = "0";
      if (!c) { cap.style.opacity = "0"; return; }
      var who = c[2] === "you" ? "You:" : c[2] === "jarvis" ? "Jarvis:" : "";
      capWho.textContent = who; capWho.className = c[2]; capWho.style.display = who ? "" : "none";
      cap.classList.toggle("big", c[4] === "big");
      var text = c[3];
      if (c[4] === "words") {
        var words = text.split(" "), n = Math.ceil(clamp((t - c[0]) / c[5], 0, 1) * words.length);
        text = words.slice(0, Math.max(1, n)).join(" ");
      } else if (c[4] === "type") {
        text = typedAt(c, t);
        text += Math.floor(t * 4) % 2 ? "▌" : " ";
      }
      capText.textContent = text;
      // "Stop." cuts in on its frame; everything else fades in over 0.18 s.
      var k = c[4] === "big" ? 1 : prog(t, c[0], 0.18, E.out2);
      cap.style.opacity = k.toFixed(3);
    }
    function typedAt(c, t) { return c[3].slice(0, Math.floor(clamp((t - c[0]) / c[5], 0, 1) * c[3].length)); }

    /* ---------- camera ---------- */
    var stage = $("stage");
    function camera(t) {
      var sc = 1, origin = "50% 50%";
      for (var i = 0; i < cfg.drift.length; i++) {
        var d = cfg.drift[i];
        if (t >= d[0] && t < d[1]) sc = 1 + 0.018 * E.io((t - d[0]) / (d[1] - d[0]));
      }
      var p = cfg.push;
      if (p && t >= p.at && t < p.until) {
        sc = lerp(1, p.to, prog(t, p.at, p.len, E.io));
        if (has(p.back) && t >= p.back) sc = lerp(sc, 1, prog(t, p.back, 0.7, E.io));
        origin = p.origin;
      }
      if (has(H.stop) && t >= H.stop && t < (H.outro || 1e9)) {      // hold still on "stop"
        for (var j = 0; j < cfg.drift.length; j++) { var q = cfg.drift[j]; if (H.stop >= q[0] && H.stop <= q[1]) sc = 1 + 0.018 * E.io((H.stop - q[0]) / (q[1] - q[0])); }
      }
      stage.style.transformOrigin = origin;
      stage.style.transform = "scale(" + sc.toFixed(4) + ")";
    }

    /* ---------- scene 2-3: the approval, on the PC and the phone ---------- */
    // A press is shown on the button itself (a brief accent outline), never a grey dot.
    function press(el, t, at) {
      if (!el || !has(at)) return;
      var on = t >= at - 0.12 && t < at + 0.45;
      el.style.opacity = on ? (t < at ? prog(t, at - 0.12, 0.12, E.out2) : 1 - prog(t, at + 0.2, 0.25, E.in2)).toFixed(3) : "0";
    }
    var pOk = $("p-ok");
    var RING = 2 * Math.PI * 54;
    var fpRing = $("fp-ring"), fpPrint = $("fp-print");
    if (fpRing) fpRing.setAttribute("stroke-dasharray", RING.toFixed(2));
    function approval(t) {
      if (!has(H.cards)) return;
      // cardsLead: the upright cut starts with the cards already in place.
      var C = H.cards - (cfg.cardsLead || 0);
      appear($("desk"), t, C, { d: 0.55, dy: 60, e: E.settle });
      appear($("phone"), t, C - 0.25, { d: 0.6, dy: 120, e: E.out3, out: cfg.phoneOut, outD: 0.4, outDy: -80 });
      appear($("phone-where"), t, H.cards + 0.3, { d: 0.4, dy: 10 });
      appear($("pcard"), t, C + 2 / FPS, { d: 0.5, dy: 60, e: E.settle, out: H.approved, outD: 0.3, outDy: 30 });
      if (cfg.staticHead) appear($("h-ask1"), t, -1, { d: 0.01, dy: 0, out: H.browser, outD: 0.3 });
      else appear($("h-ask1"), t, H.ask, { d: 0.5, out: H.shout - 0.25, outD: 0.25 });
      appear($("h-ask2"), t, H.every, { d: 0.5, out: H.shout - 0.25, outD: 0.25 });
      appear($("h-shout1"), t, H.shout, { d: 0.5 });
      appear($("h-shout2"), t, H.checks, { d: 0.5 });
      appear($("task-note"), t, H.taskNote, { d: 0.5, dy: 10 });
      // countdown: EXPIRES IN 00:47, down once a second (ApprovalCard.kt clockCountdown)
      var left = 47 - Math.floor(clamp(t - H.cards, 0, 40));
      var n = $("exp-n"); if (n) n.textContent = "00:" + String(left).padStart(2, "0");
      var f = $("exp-fill"); if (f) f.style.transform = "scaleX(" + (left / 60).toFixed(3) + ")";
      // tap Approve, then Android's fingerprint sheet
      if (pOk) {
        var down = t >= H.tap && t < H.tap + 0.18;
        pOk.style.transform = "scale(" + (down ? 0.95 : 1) + ")";
        pOk.style.boxShadow = down ? "0 0 0 4px #0b1016, 0 0 0 7px var(--accent)" : "none";
      }
      var sheet = $("sheet");
      if (sheet) {
        var kin = prog(t, H.sheet, 0.35, E.out3), kout = prog(t, H.ok + 0.12, 0.28, E.in2);
        sheet.style.transform = "translateY(" + (100 * (1 - kin + kout)).toFixed(2) + "%)";
      }
      if (fpRing) {
        var fill = prog(t, H.touch, H.ok - H.touch, E.io);
        fpRing.setAttribute("stroke-dashoffset", (RING * (1 - fill)).toFixed(2));
        fpPrint.style.stroke = t >= H.ok ? "var(--verdant)" : "";
        Array.prototype.forEach.call(fpPrint.children, function (p) { p.style.stroke = t >= H.ok ? "#3ddc97" : ""; });
      }
      appear($("p-done"), t, H.approved + 0.25, { d: 0.35, dy: 0, s0: 0.8, e: E.settle });
      appear($("desk-card"), t, H.cards, { d: 0.01, dy: 0, out: H.clear, outD: 0.3, outDy: 24 });
      // The real PC card, then a slow zoom so its allowed site and steps can be read.
      var z = cfg.deskZoom, img = $("desk-img");
      if (z && img) {
        var kz = prog(t, z.at, z.len, E.io) * (1 - prog(t, z.out, 0.6, E.io));
        img.style.transformOrigin = z.origin;
        img.style.transform = "scale(" + lerp(1, z.to, kz).toFixed(4) + ")";
      }
      browser(t);
    }

    /* The visible browser: only the two approved steps, on the one allowed site. */
    var URL = "library.example.org/account";
    function browser(t) {
      if (!has(H.browser)) return;
      appear($("browser"), t, H.browser, { d: 0.55, dy: 50, e: E.settle });
      appear($("b-note"), t, H.browser + 0.6, { d: 0.5, dy: 10 });
      var u = $("b-url"); if (u) u.textContent = t < H.step1 ? "" : URL;
      var page = document.querySelector("#browser .bpage");
      if (page) page.style.opacity = "1";
      appear($("b-step"), t, H.step2, { d: 0.3, dy: 8, out: H.renewed + 0.4, outD: 0.3 });
      var btn = $("b-renew1"), due = $("b-due1");
      if (btn) {
        var on = t >= H.step2 && t < H.renewed;
        btn.classList.toggle("hot", on);
        btn.style.transform = "scale(" + (t >= H.click && t < H.click + 0.14 ? 0.93 : 1) + ")";
        btn.style.visibility = t >= H.renewed ? "hidden" : "visible";
      }
      if (due) {
        var done = t >= H.renewed;
        due.textContent = done ? "Renewed · due 5 Nov" : "Due Friday";
        due.classList.toggle("ok", done);
      }
    }

    /* ---------- scenes 4-6 ---------- */
    var pressKeep = $("press-keep");
    function memory(t) {
      appear($("h-private"), t, H.private, { d: 0.7, dy: 20 });
      if (has(H.memory)) { appear($("h-keep"), t, H.memory, { d: 0.01, dy: 0 }); }
      appear($("m-june"), t, H.june, { d: 0.6, dy: 30 });
      appear($("june-card"), t, H.juneCard, { d: 0.6, dy: 50 });
      appear($("m-sept"), t, H.sept, { d: 0.6, dy: 30 });
      appear($("ask-wrap"), t, H.askCard, { d: 0.55, dy: 60, e: E.settle, out: H.list - 0.25, outD: 0.3, outDy: 40 });
      appear($("h-keep"), t, H.keepLine, { d: 0.5 });
      press(pressKeep, t, H.keep);
      appear($("facts-wrap"), t, H.list, { d: 0.55, dy: 40 });
      appear($("retired-box"), t, H.retired, { d: 0.35, dy: 0 });
      appear($("retired-note"), t, H.retired + 0.2, { d: 0.4, dx: 16, dy: 0 });
    }

    /* ---------- the end ---------- */
    function outro(t) {
      if (!has(H.outro)) return;
      appear($("scrim"), t, H.outro, { d: 0.8, dy: 0 });
      appear($("o1"), t, H.o1, { d: 0.7, dy: 26 });
      appear($("o2"), t, H.pc, { d: 0.7, dy: 26 });
      appear($("o3"), t, H.rules, { d: 0.7, dy: 26 });
      appear($("small1"), t, H.small1, { d: 0.6, dy: 12 });
      appear($("small2"), t, H.small2, { d: 0.6, dy: 12 });
      appear($("wordmark"), t, H.logo, { d: 0.9, dy: 0, s0: 1.06 });
      var fade = $("fade"); fade.style.opacity = prog(t, cfg.dur - 0.7, 0.7, E.in2).toFixed(3);
    }

    function render(t) {
      drawHero(t);
      drawPhone(t);
      appear($("listen-note"), t, H.listenNote, { d: 0.6, dy: 10 });
      approval(t);
      memory(t);
      outro(t);
      captions(t);
      camera(t);
    }

    var clock = { t: 0 };
    tl.to(clock, { t: cfg.dur, duration: cfg.dur, ease: "none", onUpdate: function () { render(clock.t); } }, 0);
    render(0);
    window.__timelines = window.__timelines || {};
    window.__timelines[cfg.id] = tl;
  }

  window.FILM = { run: run };
})();
