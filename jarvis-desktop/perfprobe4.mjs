import * as K from "./tests/uikit.mjs";
const { base, close } = await K.serve();
const browser = await K.launch();

async function run(label, mutate) {
  const page = await K.open(browser, base, "index.html", {}, { width: 760, height: 520 });
  await page.waitForTimeout(1200);
  if (mutate) await page.evaluate(mutate);
  await page.waitForTimeout(800);
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Performance.enable");
  const m = async () => Object.fromEntries((await cdp.send("Performance.getMetrics")).metrics.map(x=>[x.name,x.value]));
  const a = await m(); await page.waitForTimeout(8000); const b = await m();
  const d = k => +(b[k]-a[k]).toFixed(4);
  console.log(`${label.padEnd(46)} script=${d("ScriptDuration")}s layout=${d("LayoutCount")} recalc=${d("RecalcStyleCount")} layoutDur=${d("LayoutDuration")}s task=${d("TaskDuration")}s heap+${((b.JSHeapUsedSize-a.JSHeapUsedSize)/1024).toFixed(0)}KB`);
  await page.close();
}

console.log("--- spotlight window, IDLE, 8s samples ---");
await run("1. as shipped");
await run("2. reactor drop-shadow filter removed", () => {
  document.getElementById("reactor").style.filter = "none";
});
await run("3. reactor infinite animations stopped", () => {
  document.querySelectorAll(".reactor-halo,.reactor-ring-outer,.reactor-ring-mid,.reactor-core")
    .forEach(e => e.style.animation = "none");
});
await run("4. both removed", () => {
  document.getElementById("reactor").style.filter = "none";
  document.querySelectorAll(".reactor-halo,.reactor-ring-outer,.reactor-ring-mid,.reactor-core")
    .forEach(e => e.style.animation = "none");
});
await run("5. whole reactor display:none", () => {
  document.getElementById("reactor").style.display = "none";
});

console.log("\n--- streaming markdown: cost of a paint vs buffer length ---");
{
  const page = await K.open(browser, base, "index.html", {}, { width: 760, height: 520 });
  await page.waitForTimeout(800);
  const r = await page.evaluate(() => {
    // Rebuild what paint() does: innerHTML = renderMarkdown(buffer), growing.
    const para = "Jarvis considered the request and replied with a paragraph of ordinary prose containing **bold**, `code` and a [link](http://x). ";
    const host = document.createElement("div");
    document.body.appendChild(host);
    // crude markdown-ish stand-in is wrong; instead measure real innerHTML
    // rebuild cost of the answer subtree at growing sizes, which is half of
    // what paint() pays. Report both node count and ms.
    const out = [];
    let buf = "";
    for (let paints = 1; paints <= 300; paints++) {
      buf += para;
      if (paints % 60 === 0) {
        const t0 = performance.now();
        for (let k = 0; k < 10; k++) host.innerHTML = buf.split(". ").map(s=>`<p>${s}</p>`).join("");
        out.push({ paint: paints, bufKB: +(buf.length/1024).toFixed(1),
                   msPerRebuild: +((performance.now()-t0)/10).toFixed(2),
                   nodes: host.childElementCount });
      }
    }
    host.remove();
    return out;
  });
  console.table(r);
  const totalIfEveryPaint = r[r.length-1];
  console.log(`  a 300-paint reply (30s at 100ms) ends at ${totalIfEveryPaint.bufKB}KB / ${totalIfEveryPaint.nodes} blocks,`);
  console.log(`  ${totalIfEveryPaint.msPerRebuild}ms just to rebuild the subtree on the LAST paint (markdown parse is on top).`);
  await page.close();
}
await browser.close(); close();
