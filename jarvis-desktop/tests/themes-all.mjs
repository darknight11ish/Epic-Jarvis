/**
 * Does a theme actually reach every window?
 *
 * Renders each surface under two themes through the SHIPPED path — the page's
 * own <link> and its inline bootstrap, with no stylesheet injected by the test
 * — and asserts the painted surface actually differs. Until this existed,
 * `themecheck.mjs` injected theme.css itself, so it measured a page
 * configuration that did not ship: three of the four windows never loaded the
 * contract at all and the theme picker changed one of them.
 */
import * as K from "./uikit.mjs";

const { base, close } = await K.serve();
const browser = await K.launch();

// The element that actually carries the window's background. The two overlay
// windows paint a shell inside a transparent body.
const PAGES = [
  ["index.html", "#shell", 750, 400],
  ["widget.html", "#widget-shell", 340, 320],
  ["settings.html", "body", 680, 700],
  ["brain.html", "body", 1000, 600],
];

let fails = 0;
for (const [page, selector, width, height] of PAGES) {
  const seen = {};
  for (const theme of ["deep-space", "paper"]) {
    const p = await K.open(browser, base, page,
      { pending: [], prefs: { expanded: true }, theme }, { width, height });
    await p.waitForTimeout(500);
    seen[theme] = await p.evaluate((sel) => ({
      bg: getComputedStyle(document.querySelector(sel)).backgroundColor,
      text: getComputedStyle(document.querySelector(sel)).color,
      attr: document.documentElement.getAttribute("data-theme"),
    }), selector);
    await p.close();
  }
  const ok = seen["deep-space"].bg !== seen.paper.bg;
  if (!ok) fails++;
  console.log(
    `${ok ? "ok  " : "FAIL"} ${page.padEnd(15)} ` +
    `dark[${seen["deep-space"].attr}]=${seen["deep-space"].bg}  ` +
    `light[${seen.paper.attr}]=${seen.paper.bg}`
  );
}
await browser.close();
close();
console.log(fails ? `\n${fails} window(s) ignore the theme` : "\nevery window follows the theme");
process.exit(fails ? 1 : 0);
