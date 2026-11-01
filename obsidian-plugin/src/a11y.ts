/*
 * Small, pure accessibility helpers.
 *
 * No `obsidian` import and no DOM API beyond `setAttribute`, so the same calls
 * can be tested with plain node (tests/accessibility.test.mjs) and used by the
 * panel, the settings tab and the four dialogs.
 *
 * WHY these exist at all: the plugin creates most of its own controls inside a
 * sidebar ItemView. A visible paragraph above a text box is NOT a label for a
 * screen reader, and an answer that appears after a network call is silent
 * unless its container is a live region. The rule in this project is that a
 * thing must be true on the screen; these helpers are how the same thing is
 * true for somebody who cannot see the screen.
 */

/** The one DOM method these helpers use, so a plain object can stand in for an element in tests. */
export interface AttrTarget {
  setAttribute(name: string, value: string): void;
}

/** Give a control the name a screen reader announces. An empty name is a bug. */
export function accessibleName(el: AttrTarget, name: string): void {
  const clean = (name ?? "").trim();
  if (!clean) throw new Error("an accessible name must not be empty");
  el.setAttribute("aria-label", clean);
}

/**
 * Mark an element as a live region: a sentence that changes after an async
 * action (an answer, a write result, a connection test) is announced instead of
 * appearing silently. Polite waits for the screen reader to finish speaking;
 * assertive (role="alert") interrupts, so it is only for a real failure the
 * user must hear now.
 */
export function liveRegion(el: AttrTarget, politeness: "polite" | "assertive" = "polite"): void {
  // role and aria-live must agree: role="alert" is assertive, role="status" is
  // polite, and mixing them is contradictory (role wins in some screen readers).
  el.setAttribute("role", politeness === "assertive" ? "alert" : "status");
  el.setAttribute("aria-live", politeness);
  el.setAttribute("aria-atomic", "true");
}

/** Name a group of related controls (a row of buttons is one stop for a screen reader). */
export function group(el: AttrTarget, name: string): void {
  const clean = (name ?? "").trim();
  if (!clean) throw new Error("a group name must not be empty");
  el.setAttribute("role", "group");
  el.setAttribute("aria-label", clean);
}

/** Say an area is busy while a request runs, and clear it when the answer lands. */
export function busy(el: AttrTarget, isBusy: boolean): void {
  el.setAttribute("aria-busy", isBusy ? "true" : "false");
}

/**
 * Give a control a visible-text-compatible hint (used only where a disabled
 * button cannot carry its own reason: a disabled control cannot be focused, so
 * the reason must live in nearby text and in the tooltip).
 */
export function hint(el: AttrTarget, text: string): void {
  const clean = (text ?? "").trim();
  if (!clean) return;
  el.setAttribute("title", clean);
}
