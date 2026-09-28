/* Lip-sync for the faces: turns one spoken reply (a whole WAV, analysed
 * before it plays) into a "mouth track" - 100 frames a second of
 *   level  how loud (0..1, smoothed) - every face's sound level;
 *   open   how far the mouth is open (0 = closed: pauses, m/b/p);
 *   wide   lips spread (ee, i, s - teeth showing);
 *   round  lips rounded (oo, oh, w).
 * The faces then read the track at the audio's own playback clock (plus a
 * small lead, LEAD_S), so the mouth stays in step with what is heard.
 * Everything happens on this device; nothing is sent anywhere.
 *
 * The phone has a line-for-line copy (jarvis-client .../audio/LipSync.kt);
 * tools/gen_lipsync.py and LipSyncTest.kt keep the two giving the same
 * numbers. Change both together. How it works, and how it was measured:
 * docs/LIPSYNC.md.
 *
 * A classic script (no import/export): sets globalThis.JarvisLipSync, and
 * module.exports under node. */
(function () {
  "use strict";
  var FPS = 100;
  // How far ahead of the audio clock the mouth is read. Lips move slightly
  // before the sound they make, and viewers accept a mouth that is early far
  // more readily than one that is late (docs/LIPSYNC.md, "Why 50 ms").
  var LEAD_S = 0.05;

  function clamp01(x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
  function smooth01(a, b, x) { var t = clamp01((x - a) / (b - a)); return t * t * (3 - 2 * t); }

  // ---- Spectrum of a real frame -----------------------------------------
  // Power spectrum of N real samples via one complex FFT of N/2 points (the
  // usual even/odd packing), bins 0..N/2. Iterative radix-2, in place.
  function makeSpectrum(N) {
    var M = N >> 1, bits = 0, i, j;
    while ((1 << bits) < M) bits++;
    var cosM = new Float64Array(M >> 1), sinM = new Float64Array(M >> 1);
    for (i = 0; i < (M >> 1); i++) {
      cosM[i] = Math.cos(2 * Math.PI * i / M);
      sinM[i] = Math.sin(2 * Math.PI * i / M);
    }
    var cosN = new Float64Array(M + 1), sinN = new Float64Array(M + 1);
    for (i = 0; i <= M; i++) {
      cosN[i] = Math.cos(2 * Math.PI * i / N);
      sinN[i] = Math.sin(2 * Math.PI * i / N);
    }
    var rev = new Int32Array(M);
    for (i = 0; i < M; i++) {
      var r = 0;
      for (j = 0; j < bits; j++) r |= ((i >> j) & 1) << (bits - 1 - j);
      rev[i] = r;
    }
    var zr = new Float64Array(M), zi = new Float64Array(M);
    // x: Float64Array(N) real input; pw: Float64Array(M + 1) output power.
    return function (x, pw) {
      var i, j, k, t;
      for (i = 0; i < M; i++) { j = rev[i]; zr[j] = x[2 * i]; zi[j] = x[2 * i + 1]; }
      for (var size = 2; size <= M; size <<= 1) {
        var half = size >> 1, step = M / size;
        for (i = 0; i < M; i += size) {
          for (k = 0; k < half; k++) {
            var wr = cosM[k * step], wi = -sinM[k * step];
            var a = i + k, b = a + half;
            var xr = zr[b] * wr - zi[b] * wi, xi = zr[b] * wi + zi[b] * wr;
            zr[b] = zr[a] - xr; zi[b] = zi[a] - xi;
            zr[a] += xr; zi[a] += xi;
          }
        }
      }
      for (k = 0; k <= M; k++) {
        var ka = k === M ? 0 : k, m = k === 0 ? 0 : M - k;
        var er = (zr[ka] + zr[m]) * 0.5, ei = (zi[ka] - zi[m]) * 0.5;
        var or = (zi[ka] + zi[m]) * 0.5, oi = -(zr[ka] - zr[m]) * 0.5;
        var c = cosN[k], s = sinN[k];
        var Xr = er + c * or + s * oi, Xi = ei + c * oi - s * or;
        pw[k] = Xr * Xr + Xi * Xi;
      }
    };
  }

  function db(e) { return 10 * Math.log10(e + 1e-12); }

  // Quarter-octave bands from BAND_LO Hz: band j covers
  // BAND_LO * 2^(j/4) .. BAND_LO * 2^((j+1)/4).
  var BAND_LO = 75, NB = 29;
  function bandPos(hz) { return 4 * Math.log(hz / BAND_LO) / Math.LN2; }

  // Stage 1: per-frame broadband level (dB) and quarter-octave band powers
  // of the pre-emphasised, Hann-windowed frame (~25 ms, centred on the
  // frame's time). Frames far below everything else skip the FFT.
  function features(samples, sr) {
    var len = samples.length;
    var n = len > 0 ? Math.floor((len * FPS + sr - 1) / sr) : 0;
    var N = 128, target = 0.025 * sr;
    while (N < 2048 && N * 1.4142 < target) N *= 2;
    var half = N >> 1;
    var spectrum = makeSpectrum(N), fr = new Float64Array(N), P = new Float64Array(half + 1),
      w = new Float64Array(N), wsum = 0, k, i;
    for (k = 0; k < N; k++) { w[k] = 0.5 - 0.5 * Math.cos(2 * Math.PI * k / N); wsum += w[k] * w[k]; }
    var bandOf = new Int32Array(half + 1);
    for (k = 0; k <= half; k++) {
      var hz = k * sr / N;
      var j = hz >= BAND_LO ? Math.floor(bandPos(hz)) : -1;
      bandOf[k] = j >= 0 && j < NB ? j : -1;
    }
    var all = new Float64Array(n), bands = new Float64Array(n * NB);
    for (i = 0; i < n; i++) {
      var c = Math.floor(i * sr / FPS), start = c - half, e = 0;
      for (k = 0; k < N; k++) {
        var idx = start + k;
        var x = idx >= 0 && idx < len ? samples[idx] : 0;
        var p = idx >= 1 && idx <= len ? samples[idx - 1] : 0;
        var wx = w[k] * x;
        e += wx * wx;
        fr[k] = w[k] * (x - 0.97 * p);
      }
      all[i] = db(e / wsum);
      if (all[i] < -100) continue;
      spectrum(fr, P);
      var o = i * NB;
      for (k = 1; k <= half; k++) if (bandOf[k] >= 0) bands[o + bandOf[k]] += P[k] / wsum;
    }
    return { n: n, all: all, bands: bands };
  }

  // Power between band positions x0..x1 (fractional band indices).
  function bandSum(B, o, x0, x1) {
    var s = 0, j0 = Math.max(0, Math.floor(x0)), j1 = Math.min(NB - 1, Math.floor(x1));
    for (var j = j0; j <= j1; j++) {
      var a = x0 > j ? x0 : j, b = x1 < j + 1 ? x1 : j + 1;
      if (b > a) s += B[o + j] * (b - a);
    }
    return s;
  }
  function percentile(arr, count, q) {
    if (count <= 0) return 0;
    var a = Array.prototype.slice.call(arr, 0, count).sort(function (x, y) { return x - y; });
    return a[Math.floor(q * (count - 1))];
  }

  // Smoothing without delay: a one-pole filter run forward (coefficient af)
  // and then backward (ab). A smaller backward coefficient (slower) spreads
  // each change a little EARLIER in time - anticipation, as real lips do.
  function smoothFB(x, af, ab) {
    var n = x.length, i, y = x[0];
    for (i = 0; i < n; i++) { y += (x[i] - y) * af; x[i] = y; }
    y = n > 0 ? x[n - 1] : 0;
    for (i = n - 1; i >= 0; i--) { y += (x[i] - y) * ab; x[i] = y; }
  }
  function coef(ms) { return 1 - Math.exp(-1000 / FPS / ms); }

  // The tuning, measured on Jarvis's real voice (Kokoro) in its default and
  // three animal voices - docs/LIPSYNC.md has the numbers. Hz for band
  // edges, dB for levels and thresholds, ms for smoothing. The Kotlin copy
  // has the same table.
  var K = {
    lmA: 300, lmB: 700, lmC: 800, lmD: 1400, lmAdapt: 0.9, lmPrior: 4,
    fbA: 1400, fbB: 2100, fbC: 2100, fbD: 3300, fbAdapt: 0.8, fbPrior: 2, fbN0: 80,
    fricLo: 10, fricHi: 22, nasLo: 2, nasHi: 8, openRange: 30, lmOpen: 8,
    openMs: 25, dipLo: 7.5, dipHi: 12, dipMix: 0.3, wide0: 7, wide1: 7, round0: 1, round1: 3.5,
    round2: 6, lipFwdMs: 40, lipBackMs: 60, teeth: 0.45
  };

  function analyse(samples, sampleRate, debug) {
    if (!(sampleRate > 0) || !samples) samples = [];
    var F = features(samples, sampleRate), n = F.n, B = F.bands, i, j;
    var level = new Float32Array(n), open = new Float32Array(n),
      wide = new Float32Array(n), round = new Float32Array(n);
    var tr = { fps: FPS, n: n, level: level, open: open, wide: wide, round: round };
    if (n === 0) return tr;
    var tmp = new Float64Array(n), m = 0;
    for (i = 0; i < n; i++) if (F.all[i] > -80) tmp[m++] = F.all[i];
    if (m === 0) return tr;
    // Loudness reference (robust peak) and the gate below which is silence.
    var ref = percentile(tmp, m, 0.95);
    var floor = percentile(tmp, m, 0.10);
    var gate = Math.min(ref - 30, Math.max(ref - 50, floor + 8));

    // ---- level: loudness 0..1, fast attack, slower release -------------
    var att = coef(20), rel = coef(75), env = 0;
    for (i = 0; i < n; i++) {
      var x = clamp01((F.all[i] - gate) / (ref - gate));
      env += (x - env) * (x > env ? att : rel);
      level[i] = env;
    }

    // ---- per-frame acoustic cues ------------------------------------------
    // dO: "oral" energy 300-4000 Hz - what comes out of an open mouth (a
    //     nasal murmur or a closed-lip voice bar has little of it);
    // dH: 4-10 kHz (hiss: s, sh, f, th); dL: 80-1000 Hz (voicing);
    // lm: 300-700 vs 800-1400 Hz - high for close vowels (ee, oo), low for
    //     open ones (ah): a stand-in for the first formant, i.e. the jaw;
    // fb: 2100-3300 vs 1400-2100 Hz - high for front vowels (ee: second
    //     and third formants up there), low for back and rounded ones (oo,
    //     oh, ah): a stand-in for the second formant. Band ratios, not
    //     formant tracking: cheap, and no peak-picking to go wrong.
    var dO = new Float64Array(n), dH = new Float64Array(n), dL = new Float64Array(n),
      lm = new Float64Array(n), fb = new Float64Array(n);
    var x80 = bandPos(80), x300 = bandPos(300), x1000 = bandPos(1000),
      x4000 = bandPos(4000), x10k = bandPos(10000),
      xE = bandPos(K.lmA), xF = bandPos(K.lmB), xG = bandPos(K.lmC), xH = bandPos(K.lmD),
      xA = bandPos(K.fbA), xB = bandPos(K.fbB), xC = bandPos(K.fbC), xD = bandPos(K.fbD);
    for (i = 0; i < n; i++) {
      var o = i * NB;
      dO[i] = db(bandSum(B, o, x300, x4000));
      dH[i] = db(bandSum(B, o, x4000, x10k));
      dL[i] = db(bandSum(B, o, x80, x1000));
      lm[i] = db(bandSum(B, o, xE, xF)) - db(bandSum(B, o, xG, xH));
      fb[i] = db(bandSum(B, o, xC, xD)) - db(bandSum(B, o, xA, xB));
    }
    m = 0;
    for (i = 0; i < n; i++) if (F.all[i] > gate) tmp[m++] = dO[i];
    var refO = percentile(tmp, m, 0.95);

    // Soft frame classes (0..1): fric - hiss (s, sh, f); nas - a nasal
    // murmur (m, n) or a closed-lip voice bar (b), where the low band carries
    // on but the oral band has dropped; vow - a clear vowel, the only frames
    // the lip shape is read from.
    var fric = new Float64Array(n), nas = new Float64Array(n), vow = new Float64Array(n),
      speech = new Uint8Array(n), lo = new Float64Array(n);
    for (i = 0; i < n; i++) {
      speech[i] = F.all[i] > gate ? 1 : 0;
      lo[i] = dL[i] - dO[i];
    }
    for (i = 0; i < n; i++) {
      fric[i] = speech[i] ? smooth01(K.fricLo, K.fricHi, dH[i] - dO[i]) : 0;
      nas[i] = speech[i] ? smooth01(K.nasLo, K.nasHi, lo[i]) : 0;
      vow[i] = smooth01(refO - 22, refO - 10, dO[i]) * (1 - fric[i]) * (1 - nas[i]);
    }

    // The voice's own colour: some voices (the breathy owl, the darker
    // panda) are brighter or darker overall, which shifts both lip cues.
    // Centre them on this clip's median vowel - but only in proportion to
    // how many vowels there are (a short "Done." keeps the typical voice's
    // centre), and not all the way, so a sentence full of "ee"s still
    // reads as spread.
    m = 0;
    for (i = 0; i < n; i++) if (vow[i] > 0.5) tmp[m++] = fb[i];
    var fbOff = m > 0 ? K.fbAdapt * (percentile(tmp, m, 0.5) - K.fbPrior) * m / (m + K.fbN0) : 0;
    m = 0;
    for (i = 0; i < n; i++) if (vow[i] > 0.5) tmp[m++] = lm[i];
    var lmOff = m > 0 ? K.lmAdapt * (percentile(tmp, m, 0.5) - K.lmPrior) * m / (m + K.fbN0) : 0;

    // ---- open ---------------------------------------------------------------
    // Loudness of the oral band (vowels near the top, m/n/b well down),
    // opened wider for open vowels (the jaw: low lm), less for nasals and
    // hiss; then smoothed both ways so it neither lags nor jitters.
    var ot = new Float64Array(n);
    for (i = 0; i < n; i++) {
      if (!speech[i]) continue;
      var u = clamp01((dO[i] - refO + K.openRange) / K.openRange);
      var jaw = clamp01((K.lmOpen - lm[i] + lmOff) / 12);
      ot[i] = Math.pow(u, 1.4) * (0.55 + 0.45 * jaw) * (1 - 0.8 * nas[i]) * (1 - 0.6 * fric[i]);
    }
    smoothFB(ot, coef(K.openMs), coef(K.openMs));

    // Short dips (under ~140 ms) in the oral energy between two louder
    // stretches: the lips (or tongue) closing for m, b, p (and t, d, n).
    // The mouth closes for the dip; a longer gap is a pause, below.
    var cl = new Float64Array(n);
    for (i = 1; i < n - 1; i++) {
      if (!(dO[i] <= dO[i - 1] && dO[i] < dO[i + 1])) continue;
      var L = -1e9, R = -1e9;
      for (j = Math.max(0, i - 12); j <= i; j++) if (dO[j] > L) L = dO[j];
      for (j = i; j <= Math.min(n - 1, i + 12); j++) if (dO[j] > R) R = dO[j];
      if (L < refO - 15 || R < refO - 15) continue;
      var depth = Math.min(L, R) + K.dipMix * (Math.max(L, R) - Math.min(L, R)) - dO[i];
      var cs = smooth01(K.dipLo, K.dipHi, depth);
      if (cs <= 0) continue;
      var lim = dO[i] + 0.5 * depth, a = i, b = i;
      while (a > 0 && dO[a - 1] < lim) a--;
      while (b < n - 1 && dO[b + 1] < lim) b++;
      if (b - a + 1 > 14) continue;
      for (j = a; j <= b; j++) if (cs > cl[j]) cl[j] = cs;
    }
    // The same at the edge of a pause, where a dip has only one side: an
    // "m" or "b" that starts ("Maybe") or ends ("...them") a stretch of
    // speech - quieter than the vowel next to it and nasal-sounding.
    for (i = 0; i < n; i++) {
      if (!speech[i]) continue;
      var edgeL = i === 0 || !speech[i - 1], edgeR = i === n - 1 || !speech[i + 1];
      if (!edgeL && !edgeR) continue;
      var dir = edgeL ? 1 : -1, pk = -1e9;
      for (j = i; j >= 0 && j < n && Math.abs(j - i) <= 25; j += dir) if (dO[j] > pk) pk = dO[j];
      if (pk < refO - 15) continue;
      for (j = i; j >= 0 && j < n && Math.abs(j - i) < 15 && speech[j]; j += dir) {
        var ce = smooth01(K.dipLo, K.dipHi, pk - dO[j]) * smooth01(-2, 2, lo[j]);
        if (ce <= 0.05) break;
        if (ce > cl[j]) cl[j] = ce;
      }
    }
    smoothFB(cl, coef(8), coef(8));

    // Pauses: a silent stretch of 80 ms or more closes the mouth fully,
    // 40 ms into the silence; it starts opening 30 ms before speech resumes.
    var pm = new Float64Array(n);
    for (i = 0; i < n; i++) pm[i] = 1;
    i = 0;
    while (i < n) {
      if (speech[i]) { i++; continue; }
      j = i;
      while (j < n && !speech[j]) j++;
      if (j - i >= 8) {
        for (var k = i; k < j; k++) {
          var dl = i > 0 ? k - i + 1 : 99, dr = j < n ? j - k : 99;
          pm[k] = Math.max(clamp01(1 - dl / 4), clamp01(1 - dr / 4));
        }
      }
      i = j;
    }

    for (i = 0; i < n; i++) {
      var ov = ot[i] * (1 - cl[i]) * pm[i];
      open[i] = clamp01(1.15 * ov / (1 + 0.15 * ov));
    }

    // ---- wide / round -------------------------------------------------------
    // Targets from vowel frames only; consonants between them borrow their
    // neighbours' lip shape (normalised smoothing), and the backward pass is
    // slower, so lips shape up a little before the vowel (coarticulation).
    var nw = new Float64Array(n), nr = new Float64Array(n), den = new Float64Array(n),
      fr2 = new Float64Array(n);
    for (i = 0; i < n; i++) {
      var f2 = fb[i] - fbOff;
      var wt = clamp01((f2 - K.wide0) / K.wide1);
      var rt = clamp01((lm[i] - lmOff - K.round0) / K.round1) * clamp01((K.round2 - f2) / K.wide1);
      nw[i] = vow[i] * wt; nr[i] = vow[i] * rt; den[i] = vow[i]; fr2[i] = fric[i];
    }
    var lf = coef(K.lipFwdMs), lb = coef(K.lipBackMs);
    smoothFB(nw, lf, lb); smoothFB(nr, lf, lb); smoothFB(den, lf, lb); smoothFB(fr2, coef(20), coef(20));
    for (i = 0; i < n; i++) {
      var pres = clamp01(den[i] / 0.3) * pm[i];
      var wv = den[i] > 1e-6 ? nw[i] / den[i] : 0, rv = den[i] > 1e-6 ? nr[i] / den[i] : 0;
      wv = Math.max(wv * pres, K.teeth * fr2[i] * pm[i]);
      rv = rv * pres;
      wide[i] = clamp01(wv * (1 - rv));
      round[i] = clamp01(rv * (1 - wv));
    }

    if (debug) tr._debug = { all: F.all, dO: dO, dH: dH, dL: dL, lm: lm, fb: fb, ref: ref, refO: refO,
      gate: gate, fbOff: fbOff, lmOff: lmOff, fric: fric, nas: nas, vow: vow, cl: cl, pm: pm };
    return tr;
  }

  function sample(track, t, out) {
    if (!track) return null;
    out = out || { level: 0, open: 0, wide: 0, round: 0 };
    var f = (t + LEAD_S) * track.fps;
    if (!(f >= 0) || f > track.n - 1 || track.n === 0) {
      out.level = out.open = out.wide = out.round = 0;
      return out;
    }
    var i = Math.floor(f), u = f - i, j = Math.min(i + 1, track.n - 1);
    out.level = track.level[i] + (track.level[j] - track.level[i]) * u;
    out.open = track.open[i] + (track.open[j] - track.open[i]) * u;
    out.wide = track.wide[i] + (track.wide[j] - track.wide[i]) * u;
    out.round = track.round[i] + (track.round[j] - track.round[i]) * u;
    return out;
  }

  function fromWav(buf) {
    var u8 = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
    var dv = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);
    var p = 12, ch = 1, rate = 24000, bits = 16, data = null;
    while (p + 8 <= u8.length) {
      var id = String.fromCharCode(u8[p], u8[p + 1], u8[p + 2], u8[p + 3]);
      var size = dv.getUint32(p + 4, true);
      if (id === "fmt ") {
        ch = dv.getUint16(p + 10, true);
        rate = dv.getUint32(p + 12, true);
        bits = dv.getUint16(p + 22, true);
      } else if (id === "data") {
        data = [p + 8, Math.min(size, u8.length - p - 8)];
        break;
      }
      p += 8 + size + (size & 1);
    }
    if (!data || bits !== 16 || ch < 1) return { samples: new Float32Array(0), sampleRate: rate };
    var frames = Math.floor(data[1] / (2 * ch));
    var out = new Float32Array(frames);
    for (var i = 0; i < frames; i++) {
      var s = 0;
      for (var c = 0; c < ch; c++) s += dv.getInt16(data[0] + (i * ch + c) * 2, true);
      out[i] = s / ch / 32768;
    }
    return { samples: out, sampleRate: rate };
  }

  var B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  function pack(track) {
    var n = track.n, bytes = new Uint8Array(n * 4), i;
    for (i = 0; i < n; i++) {
      bytes[i * 4] = Math.round(clamp01(track.level[i]) * 255);
      bytes[i * 4 + 1] = Math.round(clamp01(track.open[i]) * 255);
      bytes[i * 4 + 2] = Math.round(clamp01(track.wide[i]) * 255);
      bytes[i * 4 + 3] = Math.round(clamp01(track.round[i]) * 255);
    }
    var s = "";
    for (i = 0; i < bytes.length; i += 3) {
      var b0 = bytes[i], b1 = i + 1 < bytes.length ? bytes[i + 1] : 0,
        b2 = i + 2 < bytes.length ? bytes[i + 2] : 0;
      s += B64[b0 >> 2] + B64[((b0 & 3) << 4) | (b1 >> 4)] +
        (i + 1 < bytes.length ? B64[((b1 & 15) << 2) | (b2 >> 6)] : "=") +
        (i + 2 < bytes.length ? B64[b2 & 63] : "=");
    }
    return track.fps + ":" + s;
  }
  function unpack(str) {
    var c = str.indexOf(":"), fps = parseInt(str.slice(0, c), 10), s = str.slice(c + 1);
    var len = Math.floor(s.length / 4) * 3;
    if (s.endsWith("==")) len -= 2; else if (s.endsWith("=")) len -= 1;
    var bytes = new Uint8Array(len), j = 0;
    for (var i = 0; i < s.length; i += 4) {
      var v = (B64.indexOf(s[i]) << 18) | (B64.indexOf(s[i + 1]) << 12) |
        ((s[i + 2] === "=" ? 0 : B64.indexOf(s[i + 2])) << 6) |
        (s[i + 3] === "=" ? 0 : B64.indexOf(s[i + 3]));
      if (j < len) bytes[j++] = (v >> 16) & 255;
      if (j < len) bytes[j++] = (v >> 8) & 255;
      if (j < len) bytes[j++] = v & 255;
    }
    var n = Math.floor(len / 4);
    var t = { fps: fps, n: n, level: new Float32Array(n), open: new Float32Array(n),
      wide: new Float32Array(n), round: new Float32Array(n) };
    for (var k = 0; k < n; k++) {
      t.level[k] = bytes[k * 4] / 255; t.open[k] = bytes[k * 4 + 1] / 255;
      t.wide[k] = bytes[k * 4 + 2] / 255; t.round[k] = bytes[k * 4 + 3] / 255;
    }
    return t;
  }

  var JarvisLipSync = { FPS: FPS, LEAD_S: LEAD_S, analyse: analyse, sample: sample,
    fromWav: fromWav, pack: pack, unpack: unpack };
  globalThis.JarvisLipSync = JarvisLipSync;
  if (typeof module !== "undefined") module.exports = JarvisLipSync;
})();
