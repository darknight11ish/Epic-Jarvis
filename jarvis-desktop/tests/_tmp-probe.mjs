import * as K from "./uikit.mjs";

const { base, close } = await K.serve();
const browser = await K.launch();
const page = await K.open(browser, base, "index.html", {});
await page.evaluate(() => {
  const core = window.__TAURI__.core;
  const invoke = core.invoke;
  window.__coachOn = false;
  core.invoke = async (cmd, args) => {
    if (cmd === "get_prompt_coach") {
      return { ok: true, on: true, why: "", label: "Prompt coach", heading: "Prompt coach",
        button: "Coach this", send_mine: "Send mine", send_suggestion: "Send the suggestion" };
    }
    if (cmd === "coach_prompt") {
      window.__body = { ...args };
      return { ok: true, coach: { score: 4, clear: false,
        issues: [{ what: "No output shape", why: "could be prose", fix: "say a table" }],
        missing: ["Which PC is this for?"],
        suggestion: "Compare them, as a table." } };
    }
    return invoke(cmd, args);
  };
});
await page.evaluate(() => window.dispatchEvent(new Event("focus")));
await page.waitForTimeout(300);

console.log("DOM:", await page.evaluate(() => {
  const button = document.getElementById("coach-this");
  const field = document.getElementById("prompt-field");
  const css = (el, p) => getComputedStyle(el).getPropertyValue(p);
  return {
    fieldChildren: [...field.children].map((e) => `${e.tagName}#${e.id}`),
    bodyChildren: [...field.parentElement.children].map((e) => `${e.tagName}#${e.id}`),
    buttonParent: button.parentElement.id,
    fieldTag: field.tagName,
    fieldDisplay: css(field, "display"),
    fieldDirection: css(field, "flex-direction"),
    buttonDisplay: css(button, "display"),
    buttonPosition: css(button, "position"),
    buttonRect: button.getBoundingClientRect().toJSON(),
    promptRect: document.getElementById("prompt").getBoundingClientRect().toJSON(),
    fieldRect: field.getBoundingClientRect().toJSON(),
    barDirection: css(document.getElementById("bar"), "flex-direction"),
  };
}));

await page.fill("#prompt", "compare the two models");
await page.click("#coach-this");
await page.waitForTimeout(400);
console.log("BODY:", JSON.stringify(await page.evaluate(() => window.__body)));
console.log("PANEL:", JSON.stringify(await page.evaluate(() => {
  const panel = document.getElementById("coach-panel");
  return { text: panel.innerText,
    missingHidden: document.querySelector(".coach-missing").hidden,
    lines: [...document.querySelectorAll(".coach-missing .coach-lines > *")].map((e) => e.textContent) };
})));

// Now two real turns, then look at state.thread via a fresh coach press.
await page.click(".coach-close");
await page.fill("#prompt", "what is on my calendar");
await page.press("#prompt", "Enter");
await page.waitForTimeout(300);
await page.fill("#prompt", "and tomorrow?");
await page.press("#prompt", "Enter");
await page.waitForTimeout(400);
console.log("TURNS:", await page.evaluate(() => (window.__calls || []).filter((c) => c[0] === "stream_chat").length));
await page.fill("#prompt", "compare the two models");
await page.click("#coach-this");
await page.waitForTimeout(400);
console.log("HISTORY:", JSON.stringify(await page.evaluate(() => (window.__body || {}).history)));
console.log("ERRORS:", JSON.stringify(page.__errors));
await browser.close();
close();
