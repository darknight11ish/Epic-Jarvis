/**
 * features.js - "Everything Jarvis can do" (docs/FEATURES-LIST-DESIGN.md,
 * 2026-10-08).
 *
 * Reads `features.json` - the one list, checked in three times over and held
 * together by tools/check_feature_list.py - and draws it as nine groups of
 * extendable rows. Nothing here changes anything: there is no invoke(), no
 * fetch to the PC, and no model. The words are the file's, to the letter.
 *
 * WHY NO INLINE THEME GUARD. Every other window sets [data-theme] from a
 * synchronous inline script before first paint. tests/csp-inline.mjs pins the
 * number of inline script blocks per page and refuses to let it rise, so this
 * page has none and applies the same saved theme here instead. The stylesheet
 * is linked, and the page's own rules live in its <style>: a <style> element
 * or a style="..." attribute written by script is refused by the packaged CSP
 * (tests/csp.mjs - the 2026-10-07 giant-face incident), so nothing dynamic is
 * ever styled from here.
 *
 * WHY THE ORDER INSIDE A GROUP. The design note: each app shows its own
 * surface's features first, with the other app's marked "on your phone" /
 * "on your PC". The nine groups keep the file's fixed order (the completeness
 * test enforces it); within a group, this app's own come first.
 */

/** The theme values the settings window and every other window write. */
const THEMES = ["deep-space", "paper", "high-contrast"];

try {
  const saved = localStorage.getItem("jarvis.theme");
  if (THEMES.includes(saved)) document.documentElement.setAttribute("data-theme", saved);
} catch {
  /* private mode, cleared site data - the default theme is correct */
}

/** This surface, for "own features first" and the marker on the other's. */
const HERE = "desktop";
/**
 * The marker for a feature that belongs to the OTHER app, and only that one:
 * a feature of this app's own (or one both have) carries no marker at all - it
 * is the normal case, and labelling every row would say nothing.
 */
const OTHER_TAG = { phone: "on your phone" };

const list = document.getElementById("features-list");
const status = document.getElementById("features-status");
const sub = document.getElementById("features-sub");

/** One field of an opened row: a label and the sentence from the file. */
function field(label, value) {
  const row = document.createElement("div");
  row.className = "feat-field";
  const name = document.createElement("span");
  name.className = "feat-label";
  // textContent everywhere: this is a data file, and the CSP-safe, escape-free
  // way to put its words on the page is to never parse them as markup.
  name.textContent = label;
  const text = document.createElement("p");
  text.className = "feat-value";
  text.textContent = value;
  row.appendChild(name);
  row.appendChild(text);
  return row;
}

/** One feature: a <details> row that extends to the four fields. */
function row(entry) {
  const item = document.createElement("details");
  item.className = "feat-item";
  item.dataset.id = entry.id;

  const summary = document.createElement("summary");
  summary.className = "feat-title";
  summary.textContent = entry.title;
  const tag = OTHER_TAG[entry.surface] || "";
  if (tag) {
    const chip = document.createElement("span");
    chip.className = "feat-tag";
    chip.textContent = tag;
    summary.appendChild(chip);
  }
  item.appendChild(summary);

  const opened = document.createElement("div");
  opened.className = "feat-opened";
  opened.appendChild(field("What it does", entry.what));
  opened.appendChild(field("How to reach it", entry.where));
  opened.appendChild(field("Asks first", entry.asks));
  // A feature with no real limit draws no line at all, rather than an empty
  // one that reads as a missing answer (the design note's empty `limit`).
  if (entry.limit) opened.appendChild(field("One limit", entry.limit));
  item.appendChild(opened);
  return item;
}

/** The groups, in the file's order, each with this surface's features first. */
function grouped(entries) {
  const order = [];
  const buckets = new Map();
  for (const entry of entries) {
    if (!buckets.has(entry.group)) {
      buckets.set(entry.group, []);
      order.push(entry.group);
    }
    buckets.get(entry.group).push(entry);
  }
  for (const [name, rows] of buckets) {
    buckets.set(name, [
      ...rows.filter((e) => e.surface !== "phone"),
      ...rows.filter((e) => e.surface === "phone"),
    ]);
  }
  return order.map((name) => [name, buckets.get(name)]);
}

function draw(entries) {
  list.innerHTML = "";
  const groups = grouped(entries);
  for (const [name, rows] of groups) {
    const section = document.createElement("section");
    section.className = "card features-group";
    section.dataset.group = name;
    const heading = document.createElement("h2");
    heading.textContent = name;
    section.appendChild(heading);
    const count = document.createElement("p");
    count.className = "note";
    count.textContent = rows.length === 1 ? "1 feature" : `${rows.length} features`;
    section.appendChild(count);
    // The rows go in a plain div, not straight into the section: the summary
    // and the section's own box should not be siblings in a flex layout.
    const box = document.createElement("div");
    for (const entry of rows) box.appendChild(row(entry));
    section.appendChild(box);
    list.appendChild(section);
  }
  sub.textContent = `${entries.length} features, in ${groups.length} groups. Nothing on this page changes anything.`;
  const other = entries.filter((e) => e.surface === "phone").length;
  status.textContent = other
    ? `${other} of them ${other === 1 ? "is" : "are"} on your phone.`
    : "";
}

async function start() {
  try {
    const answer = await fetch("features.json", { cache: "no-store" });
    if (!answer.ok) throw new Error(`the list could not be read (${answer.status})`);
    const entries = await answer.json();
    if (!Array.isArray(entries) || entries.length === 0) {
      throw new Error("the list is empty");
    }
    draw(entries);
  } catch (error) {
    // Plain words, the same as every other failure in this app: the owner
    // should never be shown a raw error or a code.
    sub.textContent = "The feature list could not be read.";
    status.textContent =
      "Close this window and open it again from Settings. If it keeps happening, " +
      "run apply-patches.ps1 again, which puts the list back.";
    console.error("[features] could not read features.json:", error);
  }
}

start();
