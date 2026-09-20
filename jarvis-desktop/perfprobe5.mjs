import * as K from "./tests/uikit.mjs";
const { base, close } = await K.serve();
const browser = await K.launch();
const page = await K.open(browser, base, "index.html", {}, { width: 760, height: 620 });

// Real SSE stream, 30s worth of tokens at ~40 tok/s -> a long markdown answer.
await page.evaluate(() => {
  window.__paints = 0; window.__paintMs = 0; window.__sizes = [];
  const oih = Object.getOwnPropertyDescriptor(Element.prototype, "innerHTML");
  Object.defineProperty(Element.prototype, "innerHTML", { ...oih, set(v){
    if (this.id === "answer") { window.__paints++; window.__sizes.push(v.length); }
    oih.set.call(this, v);
  }});
  const of = window.fetch;
  window.fetch = async (url, opt) => {
    if (!/chat|completion/i.test(String(url)) && !(opt && opt.method === "POST")) return of(url, opt);
    const enc = new TextEncoder();
    const para = "Jarvis weighed the request against the arbiter's current budget and replied in ordinary prose, with **bold** emphasis, a `code span`, and a [link](https://example.invalid/x) so the inline renderer has work to do. ";
    let n = 0;
    const body = new ReadableStream({
      pull(c) {
        if (n >= 1200) { c.enqueue(enc.encode("data: [DONE]\n\n")); c.close(); return; }
        const chunk = (n % 18 === 17) ? "\n\n" : para.split(" ")[n % 30] + " ";
        c.enqueue(enc.encode(`data: ${JSON.stringify({choices:[{delta:{content:chunk}}]})}\n\n`));
        n++;
        return new Promise(r => setTimeout(r, 25)); // ~40 tok/s
      }
    });
    return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
  };
});

const cdp = await page.context().newCDPSession(page);
await cdp.send("Performance.enable");
const m = async () => Object.fromEntries((await cdp.send("Performance.getMetrics")).metrics.map(x=>[x.name,x.value]));

await page.fill("#prompt", "write me something long");
const a = await m();
await page.keyboard.press("Enter");
await page.waitForTimeout(32000);
const b = await m();
const d = k => +(b[k]-a[k]).toFixed(3);

const r = await page.evaluate(() => ({
  paints: window.__paints,
  finalHtmlKB: +(window.__sizes[window.__sizes.length-1]/1024).toFixed(1),
  totalHtmlGeneratedKB: +(window.__sizes.reduce((s,x)=>s+x,0)/1024).toFixed(0),
  bufferKB: "n/a",
  blocks: document.getElementById("answer").childElementCount,
}));
console.log("--- 30s streaming reply, real paint() path ---");
console.log(JSON.stringify(r, null, 1));
console.log(`ScriptDuration=${d("ScriptDuration")}s  TaskDuration=${d("TaskDuration")}s  LayoutCount=${d("LayoutCount")}  RecalcStyleCount=${d("RecalcStyleCount")}  LayoutDuration=${d("LayoutDuration")}s  heap +${((b.JSHeapUsedSize-a.JSHeapUsedSize)/1024/1024).toFixed(2)}MB  Nodes ${a.Nodes}->${b.Nodes}`);
console.log(`=> ${(d("ScriptDuration")/32*100).toFixed(1)}% of one core for 32s, ${r.paints} full subtree rebuilds, ${r.totalHtmlGeneratedKB}KB of HTML strings built and thrown away`);
await page.close(); await browser.close(); close();
