// node states.mjs <face> <outdir> <px,px,...> [states,comma] [t] [yaw] [pitch]
// Env: PATCH=<json of [[from,to],...]> patches critters-gen.js on the fly; EXTRA=<json opts merged into pose opts>
import { mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { join } from "node:path";
import * as K from "/home/user/Epic-Jarvis/.claude/worktrees/agent-abd7d5ab573657428/jarvis-desktop/tests/uikit.mjs";
const [face, out, pxs] = process.argv.slice(2);
const ALL = ["idle","listening","thinking","speaking","approval","standby","error","banked"];
const STATES = (process.argv[5] && process.argv[5] !== "all") ? process.argv[5].split(",") : ALL;
const T = +(process.argv[6] || 31.3), YAW = +(process.argv[7] || 0), PIT = +(process.argv[8] || 0);
const EXTRA = process.env.EXTRA ? JSON.parse(process.env.EXTRA) : {};
const LIDS = process.env.LIDS ? JSON.parse(process.env.LIDS) : {};
const sizes = pxs.split(",").map(Number);
mkdirSync(out, { recursive: true });
const { base, close } = await K.serve();
const browser = await K.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 1200 }, deviceScaleFactor: 1 });
if (process.env.REPLACE) {
  await page.route(/critters-gen\.js/, async (route) => {
    await route.fulfill({ status: 200, contentType: "application/javascript", body: readFileSync(process.env.REPLACE, "utf8") });
  });
}
if (process.env.PATCH) {
  const reps = JSON.parse(readFileSync(process.env.PATCH, "utf8"));
  await page.route(/critters-gen\.js/, async (route) => {
    const resp = await route.fetch(); let body = await resp.text();
    for (const [a, b] of reps) { if (!body.includes(a)) throw new Error("patch miss " + a); body = body.split(a).join(b); }
    await route.fulfill({ response: resp, body });
  });
}
await page.goto(`${base}/faces.html?mode=display&feed=parent&face=${face}`, { timeout: 90000 });
await page.waitForFunction(() => typeof drawSurface === "function" && typeof CritterPose !== "undefined", null, { timeout: 90000 });
await page.waitForTimeout(800);
await page.evaluate(({ face }) => {
  window.requestAnimationFrame = () => 0;
  let fake = 1e6; performance.now = () => fake; window.__adv = (ms) => { fake += ms; };
  gpuJudge = () => {}; gpuTrip = () => {};
  document.body.innerHTML = ""; document.body.style.background = "#04070c";
  const sp = CritterPose.species[face], orig = sp.pose;
  const ou = sp.uniforms; sp.uniforms = (P, mouth) => { const U = ou(P, mouth); if (window.__LID) U.uLid = window.__LID; return U; };
  sp.pose = (st, prev, since, t, amp, look, hist, opts) => {
    const F = window.__F;
    if (!F) return orig(st, prev, since, t, amp, look, hist, opts);
    return orig(F.state, F.state, F.since, F.t, F.amp == null ? amp : F.amp, look, {}, Object.assign({}, opts, F.extra || {}));
  };
}, { face });
for (const PX of sizes) {
  await page.evaluate(({ face, PX, yaw, pit }) => {
    document.body.innerHTML = "";
    const cv = document.createElement("canvas");
    cv.style.width = PX + "px"; cv.style.height = PX + "px";
    document.body.appendChild(cv);
    const s = makeSurface(THEME[face], cv, null); s.seed = 7; s.ss = 1; sizeSurface(s); window.__s = s;
    VIEW.yaw = yaw; VIEW.pitch = pit;
  }, { face, PX, yaw: YAW, pit: PIT });
  for (const st of STATES) {
    let url;
    for (let k = 0; k < 40; k++) {
      url = await page.evaluate(({ st, T, k, EXTRA, LIDS }) => {
        __adv(50);
        window.__LID = LIDS[st] || [0, 0];
        window.__F = { state: st, since: 30, t: T, amp: st === "speaking" ? 0.5 : (st === "listening" ? 0.4 : 0), extra: EXTRA };
        if (st === "speaking") { LIP.mouth = { open: 0.55, wide: 0.3, round: 0.1 }; } else LIP.mouth = null;
        drawSurface(__s, 0.05, st);
        return k === 39 ? __s.canvas.toDataURL("image/png") : null;
      }, { st, T, k, EXTRA, LIDS });
    }
    writeFileSync(join(out, `${face}-${st}-${PX}.png`), Buffer.from(url.split(",")[1], "base64"));
  }
}
console.log("done", face);
await browser.close(); close();
