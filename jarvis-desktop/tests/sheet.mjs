/** Contact sheet: every state, one image, on a checkerboard so the window
 *  transparency is part of what is being judged. `node tests/sheet.mjs [theme]` */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as K from "./uikit.mjs";

const OUT = fileURLToPath(new URL("./shots", import.meta.url));
const theme = process.argv[2] || "default";
const dir = path.join(OUT, theme);
const files = fs.readdirSync(dir).filter((f) => f.endsWith(".png")).sort();
const cells = files.map((f) => ({
  label: f.replace(/\.png$/, "").replace(/^\d+-/, ""),
  data: "data:image/png;base64," + fs.readFileSync(path.join(dir, f)).toString("base64"),
}));

const browser = await K.launch();
const page = await browser.newPage({ viewport: { width: 1500, height: 400 } });
await page.setContent(`<style>
  body{margin:0;background:#15171c;font:12px "Segoe UI",system-ui,sans-serif;color:#cfd6e0}
  .g{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;padding:18px}
  figure{margin:0} figcaption{padding:0 0 6px;font-size:10px;letter-spacing:.06em;
    text-transform:uppercase;color:#7d8899}
  .plate{background-color:#fff;background-image:
      linear-gradient(45deg,#d8dde4 25%,transparent 25%,transparent 75%,#d8dde4 75%),
      linear-gradient(45deg,#d8dde4 25%,transparent 25%,transparent 75%,#d8dde4 75%);
    background-size:16px 16px;background-position:0 0,8px 8px;border-radius:8px;overflow:hidden}
  .plate img{display:block;width:100%}
</style><div class="g">${cells.map((c) =>
  `<figure><figcaption>${c.label}</figcaption><div class="plate"><img src="${c.data}"></div></figure>`
).join("")}</div>`);
await page.waitForTimeout(700);
const out = path.join(OUT, `sheet-${theme}.png`);
await page.screenshot({ path: out, fullPage: true });
await browser.close();
console.log(out);
