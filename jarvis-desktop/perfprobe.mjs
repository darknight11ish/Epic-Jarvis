import * as K from "./tests/uikit.mjs";
const { base, close } = await K.serve();
const browser = await K.launch();

const page = await browser.newPage({ viewport:{width:1300,height:950}, deviceScaleFactor:1 });
page.on("pageerror", e=>console.log("PAGEERR", String(e).slice(0,150)));

// instrument BEFORE any script runs
await page.addInitScript(() => {
  window.__M = { grad:0, rgbaStr:0, gei:0, gbcr:0, gcs:0, txt:0, raf:0, ctx2d:0,
                 fillStyleSet:0, saveN:0, imgData:0, arcs:0 };
  const P = CanvasRenderingContext2D.prototype;
  const og = P.createRadialGradient; P.createRadialGradient = function(...a){ window.__M.grad++; return og.apply(this,a); };
  const ol = P.createLinearGradient; P.createLinearGradient = function(...a){ window.__M.grad++; return ol.apply(this,a); };
  const os = P.save; P.save = function(){ window.__M.saveN++; return os.call(this); };
  const oa = P.arc; P.arc = function(...a){ window.__M.arcs++; return oa.apply(this,a); };
  const ogid = P.getImageData; P.getImageData = function(...a){ window.__M.imgData++; return ogid.apply(this,a); };
  const fsd = Object.getOwnPropertyDescriptor(P, "fillStyle");
  Object.defineProperty(P, "fillStyle", { ...fsd, set(v){ window.__M.fillStyleSet++; fsd.set.call(this,v); } });

  const ogbcr = Element.prototype.getBoundingClientRect;
  Element.prototype.getBoundingClientRect = function(){ window.__M.gbcr++; return ogbcr.call(this); };
  const ogcs = window.getComputedStyle;
  window.getComputedStyle = function(...a){ window.__M.gcs++; return ogcs.apply(window,a); };
  const ogei = document.getElementById.bind(document);
  document.getElementById = function(id){ window.__M.gei++; return ogei(id); };
  const td = Object.getOwnPropertyDescriptor(Node.prototype, "textContent");
  Object.defineProperty(Node.prototype, "textContent", { ...td, set(v){ window.__M.txt++; td.set.call(this,v); } });
  const oraf = window.requestAnimationFrame;
  window.requestAnimationFrame = function(cb){ window.__M.raf++; return oraf.call(window, cb); };
});

await page.goto(`${base}/faces.html`);
await page.waitForTimeout(4000); // let boot probe + calibration settle

const sample = async (ms, label) => {
  await page.evaluate(()=>{ for(const k in window.__M) window.__M[k]=0; window.__t0=performance.now(); });
  await page.waitForTimeout(ms);
  return await page.evaluate((label)=>{
    const el = performance.now()-window.__t0;
    const m = {...window.__M};
    const per = {}; for(const k in m) per[k] = +(m[k]/(el/1000)).toFixed(0);
    return { label, seconds:+(el/1000).toFixed(2), total:m, perSecond:per,
             surfaces: (window.surfaces||[]).length,
             visible: (window.surfaces||[]).filter(s=>s.vis).length };
  }, label);
};

console.log("=== A. grid at top of page, default ===");
console.log(JSON.stringify(await sample(3000,"grid"), null, 1));

// heap growth
const cdp = await page.context().newCDPSession(page);
await cdp.send("HeapProfiler.enable");
await cdp.send("Performance.enable");
const perf = async () => Object.fromEntries((await cdp.send("Performance.getMetrics")).metrics.map(m=>[m.name,m.value]));
const p1 = await perf(); await page.waitForTimeout(6000); const p2 = await perf();
console.log("=== B. 6s CDP metrics delta ===");
for (const k of ["JSHeapUsedSize","JSHeapTotalSize","Nodes","JSEventListeners","LayoutCount","RecalcStyleCount","LayoutDuration","RecalcStyleDuration","ScriptDuration","TaskDuration","Frames"]) {
  console.log(` ${k}: ${p1[k]} -> ${p2[k]}  (delta ${ (p2[k]-p1[k]).toFixed ? (p2[k]-p1[k]).toFixed(3) : p2[k]-p1[k] })`);
}

console.log("=== C. reported internals ===");
console.log(JSON.stringify(await page.evaluate(()=>({
  perfText: document.getElementById("perf")?.textContent,
  clockText: document.getElementById("clock")?.textContent,
  stride: window.CLOCK?.stride, hz: window.CLOCK?.hz, budget: window.CLOCK?.budget,
  qname: typeof QNAME!=="undefined"?QNAME:null,
  canvasPx: [...document.querySelectorAll(".card canvas")].slice(0,4).map(c=>`${c.width}x${c.height} css=${Math.round(c.getBoundingClientRect().width)}`),
})), null, 1));

await page.close(); await browser.close(); close();
