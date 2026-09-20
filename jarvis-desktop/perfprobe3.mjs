import * as K from "./tests/uikit.mjs";
const { base, close } = await K.serve();
const browser = await K.launch();
const page = await browser.newPage({ viewport:{width:1300,height:950}, deviceScaleFactor:1 });
await page.addInitScript(() => {
  window.__M={perfWrites:0,gei:0,rafTicks:0,drawCalls:0};
  const ogei=document.getElementById.bind(document);
  document.getElementById=function(id){ if(id==="perf")window.__M.gei++; return ogei(id); };
  const oraf=window.requestAnimationFrame;
  window.requestAnimationFrame=function(cb){ return oraf.call(window,(t)=>{window.__M.rafTicks++;return cb(t);}); };
  const P=CanvasRenderingContext2D.prototype, of=P.fill;
  P.fill=function(...a){window.__M.drawCalls++;return of.apply(this,a);};
});
await page.goto(`${base}/faces.html`);
await page.waitForTimeout(3000);

const cdp = await page.context().newCDPSession(page);
await cdp.send("Performance.enable");
const perf = async()=>Object.fromEntries((await cdp.send("Performance.getMetrics")).metrics.map(m=>[m.name,m.value]));

async function measure(label, secs=6){
  await page.evaluate(()=>{for(const k in window.__M)window.__M[k]=0;});
  const a=await perf(); await page.waitForTimeout(secs*1000); const b=await perf();
  const m=await page.evaluate(()=>({...window.__M}));
  const d=k=>+(b[k]-a[k]).toFixed(3);
  console.log(`${label.padEnd(34)} script=${d("ScriptDuration")}s (${(d("ScriptDuration")/secs*100).toFixed(0)}% core)`
    +` task=${d("TaskDuration")}s layouts=${d("LayoutCount")} recalc=${d("RecalcStyleCount")}`
    +` | rafTicks=${m.rafTicks} perfWrites=${m.gei} ctxFills=${m.drawCalls}`);
}

await measure("A. grid visible (top of page)");
await page.evaluate(()=>window.scrollTo(0,document.body.scrollHeight));
await page.waitForTimeout(1500);
await measure("B. scrolled to footer (0 canvas vis)");
await page.evaluate(()=>window.scrollTo(0,0));
await page.waitForTimeout(1500);
await measure("C. back at top");

// simulate the window being hidden (Tauri hides, does not close, these windows)
await page.evaluate(()=>{ Object.defineProperty(document,"visibilityState",{get:()=>"hidden",configurable:true});
                          Object.defineProperty(document,"hidden",{get:()=>true,configurable:true});
                          document.dispatchEvent(new Event("visibilitychange")); });
await page.waitForTimeout(1000);
await measure("D. document.hidden=true", 5);
console.log("visible surfaces while hidden:", await page.evaluate(()=>"x"));
await page.close(); await browser.close(); close();
