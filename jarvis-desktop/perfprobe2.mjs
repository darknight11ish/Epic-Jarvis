import * as K from "./tests/uikit.mjs";
const { base, close } = await K.serve();
const browser = await K.launch();
const page = await browser.newPage({ viewport:{width:1300,height:950}, deviceScaleFactor:1 });

await page.addInitScript(() => {
  window.__S = { sortCalls:0, filterOnSamples:0 };
  const osort = Array.prototype.sort;
  Array.prototype.sort = function(...a){ if(this.length>50) window.__S.sortCalls++; return osort.apply(this,a); };
});
await page.goto(`${base}/faces.html`);
await page.waitForTimeout(3000);

const snap = () => page.evaluate(() => {
  // reach into CAL via its localStorage + reconstruct by probing global names
  const g = {};
  for (const n of ["CLOCK","CAL","surfaces","Q","QNAME","AUTO"]) g[n] = (n in window);
  return { globals:g, sortCalls: window.__S.sortCalls,
           clockSamples: (window.CLOCK&&window.CLOCK.samples.length) };
});
console.log("globals visible:", JSON.stringify(await snap()));

// Everything is in module-ish top-level scope of a classic script -> should be global.
const dig = async () => page.evaluate(() => {
  const out = { clock:{}, cal:null, surf:null };
  try { out.clock = { hz:CLOCK.hz, stride:CLOCK.stride, budget:+CLOCK.budget.toFixed(2),
                      samples:CLOCK.samples.length, achieved:CLOCK.achieved, probed:CLOCK.probed }; } catch(e){ out.clock=String(e); }
  try { out.cal = CAL.summary(); } catch(e){ out.cal=String(e); }
  try { out.surf = { n:surfaces.length, vis:surfaces.filter(s=>s.vis).length,
                     px:surfaces.map(s=>s.w).slice(0,6), ss:surfaces[0].ss }; } catch(e){ out.surf=String(e); }
  try { out.q = { QNAME, ss:Q.ss, detail:Q.detail }; } catch(e){ out.q=String(e); }
  out.sorts = window.__S.sortCalls;
  return out;
});
console.log("T+3s ", JSON.stringify(await dig()));
await page.waitForTimeout(10000);
console.log("T+13s", JSON.stringify(await dig()));

// Probe CAL internal arrays via the closure's localStorage + a re-entry:
// instead, measure array growth by patching push on the fly is impossible.
// Use heap snapshot counts of large number arrays instead:
const cdp = await page.context().newCDPSession(page);
await cdp.send("Runtime.enable");
const heapOf = async () => (await cdp.send("Runtime.evaluate",{expression:"1",returnByValue:true}), 0);

// measure raw frame cost breakdown by disabling the readout writes
console.log("=== cost with #perf/#fps text writes suppressed ===");
const before = await page.evaluate(async ()=>{
  await new Promise(r=>setTimeout(r,2500));
  return { costAvg: +document.getElementById("perf").textContent.split(" ")[0], achieved: CLOCK.achieved };
});
await page.evaluate(()=>{
  // neutralise the per-frame DOM writes
  const d = Object.getOwnPropertyDescriptor(Node.prototype,"textContent");
  Object.defineProperty(Node.prototype,"textContent",{...d,set(v){ /* swallow */ }});
  window.__suppressed = true;
});
await page.waitForTimeout(4000);
const after = await page.evaluate(()=>({ achieved: CLOCK.achieved }));
console.log("before:", JSON.stringify(before), " after suppressing text writes:", JSON.stringify(after));

await page.close(); await browser.close(); close();
