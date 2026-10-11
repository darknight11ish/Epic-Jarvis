/**
 * pictures-settings.js — the PC's own setup for "Ask for a picture, and keep
 * it" (the owner's decision of 2026-09-27; `docs/JARVIS-API.md` section 124;
 * backend `jarvis_pictures.py`, `brain/pictures.rs`).
 *
 * THREE THINGS, AND ALL THREE ARE THE PC'S:
 *
 *   "Making pictures"        the switch, OFF to start
 *   the program that draws   ComfyUI or stable-diffusion.cpp, by name
 *   where pictures are kept  a folder on this PC, chosen with the same
 *                            Windows "Select folder" dialog "Folders Jarvis
 *                            may look in" uses
 *
 * The backend refuses all three from anywhere but this PC (`403 pc_only`), so
 * the phone has no control for any of them and this card is the only place
 * they change.
 *
 * NO APPROVAL CARD, and this is where that is written down on this side: a
 * picture is a new file in a folder on THIS PC, drawn by a program on THIS PC,
 * from words the owner typed. It opens no way out of the PC (nothing is ever
 * uploaded, emailed or shared), changes no account and loosens no rule - the
 * same shape as a timer or a note. Every change here does write, so every one
 * is held on a stale link (rule 4).
 *
 * THE GALLERY IS ELSEWHERE, ON PURPOSE. Asking for one and seeing the ones you
 * kept is Brain -> Projects -> Pictures (`pictures-panel.js`); this card says
 * so rather than drawing a second gallery. One place per thing.
 *
 * EVERY SENTENCE IS THE PC'S. The state line, the size, "kept until you delete
 * them yourself" and the one plain sentence naming what to install all come
 * from `jarvis_pictures.py`. This file works none of them out.
 *
 * @module pictures-settings
 */

const els = {};
for (const id of ["pc-title", "pc-subtitle", "pc-state", "pc-body", "pc-detail",
  "pc-switch", "pc-switch-label", "pc-runtime", "pc-install", "pc-folder",
  "pc-choose", "pc-size", "pc-keep", "pc-gallery-note", "pc-status"]) {
  els[id] = document.getElementById(id);
}

/** Pinned wording this page draws; every other sentence is the PC's. */
const NOTE =
  "Asking for one, and seeing the ones you kept, is in the Brain, under Projects, Pictures. " +
  "A picture is never sent anywhere by Jarvis.";
const NOTHING = "Nothing chosen yet";

let state = null;
let busy = false;

async function invoke(command, args = {}) {
  const core = globalThis.__TAURI__ && globalThis.__TAURI__.core;
  if (!core || !core.invoke) throw new Error("This window cannot reach Jarvis.");
  return core.invoke(command, args);
}

function say(message) {
  if (els["pc-status"]) els["pc-status"].textContent = String(message || "");
}

function filling(on) {
  if (els["pc-state"]) els["pc-state"].hidden = on;
  if (els["pc-body"]) els["pc-body"].hidden = !on;
}

/** One plain sentence for a failure, never a code. */
function errorText(error) {
  return String((error && error.message) || error || "That did not work.");
}

function draw(data) {
  state = data;
  if (!data || data.available === false) {
    // A PC without the feature: say what to run, and hide the controls.
    filling(false);
    if (els["pc-state"]) {
      els["pc-state"].textContent =
        "Your PC's Jarvis does not have pictures yet - run apply-patches.ps1 on the PC.";
    }
    return;
  }
  filling(true);
  if (els["pc-switch"]) els["pc-switch"].checked = data.enabled === true;
  if (els["pc-switch-label"]) {
    els["pc-switch-label"].textContent = "Making pictures";
  }
  // The program picker: "nothing chosen yet", then the two the PC supports,
  // each with the address it uses, and what to install written under it.
  if (els["pc-runtime"]) {
    els["pc-runtime"].replaceChildren();
    const none = document.createElement("option");
    none.value = "";
    none.textContent = NOTHING;
    els["pc-runtime"].append(none);
    for (const r of data.runtimes || []) {
      const option = document.createElement("option");
      option.value = r.id;
      option.textContent = `${r.plain} — ${r.address}`;
      els["pc-runtime"].append(option);
    }
    els["pc-runtime"].value = data.runtime || "";
    const chosen = (data.runtimes || []).find((r) => r.id === (data.runtime || ""));
    if (els["pc-install"]) {
      els["pc-install"].textContent = chosen
        ? `To install: ${chosen.install}`
        : "Install ComfyUI or stable-diffusion.cpp's server on this PC, then choose it here.";
    }
  }
  if (els["pc-folder"]) els["pc-folder"].value = data.folder || "";
  if (els["pc-size"]) {
    els["pc-size"].textContent = [
      `${data.count} ${data.count === 1 ? "picture" : "pictures"}`,
      data.size_words,
      data.folder,
    ].filter(Boolean).join(" · ");
  }
  if (els["pc-keep"]) els["pc-keep"].textContent = data.keep || "";
  if (els["pc-gallery-note"]) els["pc-gallery-note"].textContent = NOTE;
  // The PC's own one plain sentence while nothing is set up, or while the
  // switch is off: read word for word.
  if (els["pc-detail"]) els["pc-detail"].textContent = data.words || "";
}

async function read() {
  try {
    const data = await invoke("brain_pictures", {});
    if (data && data.hidden) {
      // The private lists are hidden: this card's own words are the owner's
      // words too (the folder and the prompts). Draw the PC's line only.
      filling(false);
      if (els["pc-state"]) {
        els["pc-state"].textContent = data.hidden_words || "Hidden while memory lists and chat history are hidden.";
      }
      return;
    }
    draw(data);
    say("");
  } catch (error) {
    filling(false);
    if (els["pc-state"]) els["pc-state"].textContent = errorText(error);
  }
}

async function change(args) {
  if (busy) return;
  busy = true;
  say("Saving…");
  try {
    const out = await invoke("brain_pictures_settings", args);
    if (out && out.available === false) {
      say("Your PC's Jarvis does not have pictures yet - run apply-patches.ps1 on the PC.");
    } else {
      say("");
    }
    await read();
  } catch (error) {
    // The PC's own sentence as sent - "the folder cannot be used", "pick one
    // of these two" and so on.
    say(errorText(error));
    await read();
  } finally {
    busy = false;
  }
}

if (els["pc-switch"]) {
  els["pc-switch"].addEventListener("change", () => {
    change({ action: "enabled", on: els["pc-switch"].checked === true });
  });
}

if (els["pc-runtime"]) {
  els["pc-runtime"].addEventListener("change", () => {
    const value = els["pc-runtime"].value;
    change({ action: "runtime", runtime: value || null });
  });
}

if (els["pc-choose"]) {
  els["pc-choose"].addEventListener("click", async () => {
    if (busy) return;
    busy = true;
    say("Asking Windows for a folder…");
    try {
      const out = await invoke("choose_pictures_folder", {});
      if (out && out.cancelled) say("");
      else say("");
      await read();
    } catch (error) {
      say(errorText(error));
    } finally {
      busy = false;
    }
  });
}

// Read once when the window opens, and again whenever the link comes back:
// nothing is written, so there is nothing to keep on this side.
read();
