import * as K from "./tests/uikit.mjs";
const { base, close } = await K.serve();
const browser = await K.launch();

async function sample(page, label, secs=6){
  const cdp = page.__cdp;
  const m = async () => Object.fromEntries((await cdp.send("Performance.getMetrics")).metrics.map(x=>[x.name,x.value]));
  const a = await m(); await page.waitForTimeout(secs*1000); const b = await m();
  const d = k => +(b[k]-a[k]).toFixed(4);
  console.log(`${label.padEnd(52)} layouts/s=${(d("LayoutCount")/secs).toFixed(1)} recalc/s=${(d("RecalcStyleCount")/secs).toFixed(1)} layoutDur=${(d("LayoutDuration")/secs*100).toFixed(2)}%core task=${(d("TaskDuration")/secs*100).toFixed(1)}%core`);
}

const page = await K.open(browser, base, "index.html", {}, { width: 760, height: 620 });
page.__cdp = await page.context().newCDPSession(page);
await page.__cdp.send("Performance.enable");
await page.waitForTimeout(1500);

await sample(page, "state=idle (as loaded)");
await page.evaluate(()=>document.documentElement.dataset.state="streaming");
await sample(page, "state=streaming");
await page.evaluate(()=>{ document.querySelectorAll(".pulse").forEach(e=>e.style.animation="none"); });
await sample(page, "  streaming, .pulse animation off");
await page.evaluate(()=>{ document.querySelectorAll(".shell").forEach(e=>e.style.setProperty("--x","1")); 
  const s=document.createElement("style"); s.textContent=".shell::before{animation:none !important}"; document.head.appendChild(s); });
await sample(page, "  streaming, .shell::before scan off too");
await page.evaluate(()=>{ const s=document.createElement("style"); s.textContent=".cursor{animation:none !important}"; document.head.appendChild(s); });
await sample(page, "  streaming, .cursor blink off too");
await page.evaluate(()=>{ const s=document.createElement("style"); s.textContent=".reactor-halo,.reactor-ring-outer,.reactor-ring-mid,.reactor-core{animation:none !important}"; document.head.appendChild(s); });
await sample(page, "  streaming, reactor animations off too");
await page.evaluate(()=>{ document.getElementById("reactor").style.filter="none"; });
await sample(page, "  streaming, reactor drop-shadow off too");

// and the reverse: idle with only the reactor stopped
await page.evaluate(()=>document.documentElement.dataset.state="idle");
await sample(page, "state=idle, everything above still off");

await page.close(); await browser.close(); close();
