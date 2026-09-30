/**
 * The picture of a filled-in web form, on the "Jarvis wants to submit this
 * form" card (docs/FORM-REVIEW-DESIGN.md, 2026-09-30; src-tauri/src/brain/
 * form_review.rs).
 *
 * Jarvis fills a form in a visible browser, stops before the last click and
 * takes one picture of the page. The card for that click carries the
 * picture's id in `detail.picture`. While that card is showing in the Jarvis
 * bar, this shows the picture on it: small at first, bigger on a click.
 *
 * What must hold (tests/form-review.mjs):
 *  - the picture is asked for only when the row says it has one, and only
 *    while its card is showing; it is held in memory only (no storage, no
 *    cache, no console) and dropped when the card goes;
 *  - while App lock is on Rust answers `locked` and nothing is shown; while
 *    "Hide memory lists and chat history" is on it answers `hidden`, nothing is
 *    fetched, and one line says why (owner, 2026-09-30);
 *  - if it cannot be loaded the card says so in one plain sentence and the
 *    written details below it are what the owner reads - Approve and Deny
 *    keep every rule they already have (nothing here touches them);
 *  - the widget, toasts and the HUD page never load this file.
 *
 * @module form-review
 */

export const WORDS = Object.freeze({
  alt: "The form as Jarvis filled it in",
  enlarge: "Enlarge the picture of the form",
  close: "Close",
  heading: "The form as Jarvis filled it in",
  hint: "Click the picture to see it bigger.",
  gone: "The picture of the form is gone. The card may have timed out. Read the details below before you approve.",
  loading: "Loading the picture of the form...",
  failed:
    "Jarvis could not load the picture of the form. Read the details below before you approve.",
  hidden:
    'The picture shows your name, phone and email, so it is hidden while "Hide memory lists and chat history" is on. ' +
    "Turn that off in Settings, under Security, to see it, or read the details below before you approve.",
});

const ID = /^[A-Za-z0-9_-]{1,64}$/;
const BASE64 = /^[A-Za-z0-9+/]+={0,2}$/;

/**
 * The picture id a card row carries, or null. `detail` may be an object, JSON
 * text, or text cut short by the gate (so it no longer parses).
 */
export function pictureId(approval) {
  let detail = approval && approval.detail;
  if (typeof detail === "string") {
    try {
      detail = JSON.parse(detail);
    } catch {
      const m = /"picture"\s*:\s*"([A-Za-z0-9_-]{1,64})"/.exec(detail);
      return m ? m[1] : null;
    }
  }
  if (!detail || typeof detail !== "object") return null;
  const id = detail.picture;
  return typeof id === "string" && ID.test(id) ? id : null;
}

/**
 * @param {HTMLElement} box the (initially hidden) holder on the card
 * @param {object} opts
 * @param {(command: string, args?: object) => Promise<any>} opts.invoke
 * @param {() => void} [opts.onChange] the card's size changed
 * @param {(text: string) => void} [opts.announce]
 * @param {Document} [opts.doc] the page (for the overlay's Escape key)
 */
export function mountFormReview(box, { invoke, onChange = () => {}, announce = () => {}, doc } = {}) {
  const page = doc || (typeof document !== "undefined" ? document : null);
  let key = null; // `${approval id}|${picture id}` already asked for
  let seq = 0; // bumps on every clear, so a late answer is dropped
  let overlay = null;
  let onKey = null;

  function closeOverlay() {
    if (onKey && page && page.removeEventListener) {
      page.removeEventListener("keydown", onKey, true);
    }
    onKey = null;
    if (overlay) {
      const big = overlay.children && overlay.children[0];
      if (big && big.removeAttribute) big.removeAttribute("src");
      if (overlay.remove) overlay.remove();
    }
    overlay = null;
  }

  function openOverlay(src) {
    closeOverlay();
    overlay = document.createElement("div");
    overlay.className = "form-review-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", WORDS.alt);
    const big = document.createElement("img");
    big.className = "form-review-big";
    big.alt = WORDS.alt;
    big.src = src;
    const close = document.createElement("button");
    close.type = "button";
    close.className = "text-button form-review-close";
    close.textContent = WORDS.close;
    overlay.append(big, close);
    overlay.addEventListener("click", closeOverlay);
    if (page && page.addEventListener) {
      // Escape closes the picture - and only the picture: on the card it
      // would put the whole approval aside.
      onKey = (event) => {
        if (event.key !== "Escape") return;
        event.preventDefault();
        event.stopPropagation();
        closeOverlay();
      };
      page.addEventListener("keydown", onKey, true);
    }
    box.append(overlay);
  }

  function say(text) {
    const line = document.createElement("p");
    line.className = "form-review-note";
    line.setAttribute("role", "status");
    line.textContent = text;
    box.replaceChildren(line);
  }

  function clear() {
    seq += 1;
    key = null;
    closeOverlay();
    box.replaceChildren();
    if (!box.hidden) {
      box.hidden = true;
      onChange();
    }
  }

  function paint(jpeg) {
    const src = `data:image/jpeg;base64,${jpeg}`;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "form-review-thumb";
    button.setAttribute("aria-label", WORDS.enlarge);
    const img = document.createElement("img");
    img.className = "form-review-img";
    img.alt = WORDS.alt;
    img.src = src;
    button.append(img);
    button.addEventListener("click", () => openOverlay(src));
    const heading = document.createElement("p");
    heading.className = "form-review-heading";
    heading.textContent = WORDS.heading;
    const hint = document.createElement("p");
    hint.className = "form-review-note";
    hint.textContent = WORDS.hint;
    box.replaceChildren(heading, button, hint);
    onChange();
  }

  /**
   * Show the picture for this card, if it has one. Safe to call again for
   * the same card (a resync): it asks once per card and picture.
   */
  async function show(approval) {
    const id = pictureId(approval);
    if (!id) {
      clear();
      return;
    }
    const want = `${approval.id}|${id}`;
    if (key === want) return;
    clear();
    key = want;
    const mine = seq;
    box.hidden = false;
    say(WORDS.loading);
    onChange();
    let answer = null;
    try {
      answer = await invoke("form_review_picture", { id });
    } catch {
      answer = null;
    }
    if (mine !== seq) return; // the card went (or changed) meanwhile
    if (answer && answer.locked === true) {
      // App lock: show nothing, and ask again when the card is painted
      // again after the unlock.
      box.replaceChildren();
      box.hidden = true;
      key = null;
      onChange();
      return;
    }
    if (answer && answer.hidden === true) {
      // "Hide memory lists and chat history": no picture, and one line why.
      // Asked again when the card is painted again after the switch is off.
      key = null;
      say(WORDS.hidden);
      announce(WORDS.hidden);
      onChange();
      return;
    }
    if (answer && answer.ok === false && !answer.error) {
      // A plain "no" from the PC: the picture is gone (the card was decided or
      // timed out). Anything that threw, or carried an error, is "could not load".
      say(WORDS.gone);
      announce(WORDS.gone);
      onChange();
      return;
    }
    const jpeg = answer && answer.ok === true && typeof answer.jpeg === "string" ? answer.jpeg : "";
    if (!jpeg || !BASE64.test(jpeg)) {
      say(WORDS.failed);
      announce(WORDS.failed);
      onChange();
      return;
    }
    paint(jpeg);
  }

  return { show, clear, shownKey: () => key };
}
