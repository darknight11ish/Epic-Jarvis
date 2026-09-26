/**
 * Web search (the owner's decisions of 2026-09-25; JARVIS-API.md section 23;
 * backend jarvis_search.py) - the words, and how to read what the PC sends.
 *
 * Five providers, SearXNG the default (a search program on this PC, in
 * Docker), then DuckDuckGo (the ddgs package), Exa, Tavily and Brave Search
 * (keys; Brave can cost money past its free credit). Whoogle is left out,
 * with its reason.
 * Each has a short "why use this one" line. The PC sends those lines with
 * every GET /api/search, and Settings shows the PC's words; the copies below
 * are the same words (backend/test_web_search.py checks them against the PC's
 * and the phone's net/WebSearch.kt), used only when an answer lacks them.
 *
 * Used by Settings, "Web search" (web-search-settings.js; src-tauri/src/
 * web_search.rs). The Exa, Tavily and Brave keys are typed here only - never on
 * the phone - and go straight into Credential Manager on this PC.
 *
 * @module web-search
 */

export const WHY = Object.freeze({
  searxng:
    "Free, no key and no account: a search program that runs on this PC in Docker and asks several search engines for you, without their cookies or trackers. Those engines still see your internet address, and it needs Docker plus one setting (JSON) switched on.",
  duckduckgo:
    "Free, no key, and only one Python package to install (ddgs). It reads DuckDuckGo's public pages because there is no official way in, so it can be slowed down or stop working when DuckDuckGo changes, and DuckDuckGo still sees your internet address.",
  exa:
    "Finds pages by meaning, not just matching words, and returns the useful passages of each page, with about $10 of free credit a month (roughly 1,400 searches) and no payment card. Needs a free account and a key, and Exa sees what you search, tied to your key.",
  tavily:
    "Made for AI assistants: short, clean results, with 1,000 free credits a month (a basic search uses one). Needs a free account and a key, and Tavily sees what you search, tied to your key.",
  brave:
    "Brave's own independent index, with about $5 of free credit each month (roughly 1,000 searches). Needs an account, a payment card that is charged if you go past the free credit, and a key, and Brave sees what you search, tied to your key.",
});
export const LABEL = Object.freeze({
  searxng: "SearXNG (on this PC)",
  duckduckgo: "DuckDuckGo",
  exa: "Exa",
  tavily: "Tavily",
  brave: "Brave Search",
});
export const WHOOGLE_WHY =
  "Not offered: its own README says it no longer returns results, since Google blocked searching without JavaScript in 2025.";
export const DEFAULT_WHY =
  "SearXNG is the default because it costs nothing, needs no key or account, and runs on this PC, so no single search company keeps a record of your searches.";
export const ASK_LABEL = "Ask before every web search";
export const ASK_DETAIL =
  "Off (the default): Jarvis asks first only when private things could slip into a search - after it has read your email, files, notes or other outside text, when the search words repeat something you told it, or when it used a sensitive saved fact - and shows you the exact search words. On: it asks before every search. Turning this on is immediate; turning it off asks you with an approval card.";
export const KEY_ENTRY =
  "Keys are entered on the PC only - in the desktop app's Settings, Web search, or with one line in PowerShell (backend/README.md). The phone never asks for one: sending a key to the PC would send it somewhere other than its own service.";
export const KEY_WHERE = Object.freeze({
  exa: "https://dashboard.exa.ai (sign up, then API Keys)",
  tavily: "https://app.tavily.com (sign in, then API Keys)",
  brave: "https://api-dashboard.search.brave.com (sign up, add a card, then API Keys)",
});

export const PROVIDERS = Object.freeze(["searxng", "duckduckgo", "exa", "tavily", "brave"]);
export const KEYED = Object.freeze(["exa", "tavily", "brave"]);
export const DEFAULT_ADDRESS = "http://127.0.0.1:8888";

export const TITLE = "Web search";
export const DETAIL =
  "Choose where Jarvis searches the web. Only the search words are sent, to the search you " +
  "choose, and never quietly to another one: if it is not working, Jarvis says so and offers " +
  "to switch.";
export const MISSING = "Your PC's Jarvis does not have web search yet - run apply-patches.ps1 on the PC.";
export const LEFT_OUT_TITLE = "Left out";
export const ADDRESS_LABEL = "SearXNG address";
export const ADDRESS_NOTE =
  "This PC or your own network only (your home network, Tailscale or NordVPN Meshnet). Leave " +
  "it empty for this PC's http://127.0.0.1:8888.";
export const ADDRESS_SAVE = "Save address";
export const KEYS_TITLE = "Keys";
export const KEY_SAVE = "Save key";
export const KEY_FORGET = "Remove key";
export const KEY_SAVED = "A key is saved on this PC.";
export const KEY_NONE = "No key saved yet.";
export const KEY_UNKNOWN = "Could not check whether a key is saved.";
export const TEST_LABEL = "Test search";
export const TEST_BUSY = "Searching…";
export const TEST_NOTE =
  "Sends one search for the word \"wikipedia\" through the search you chose, and says what " +
  "happened. It is a real search: on Tavily it uses one credit.";
export const READY = "Ready.";
export const CHOSEN = "In use.";

/** One provider row, from the PC's answer (or these words for an older PC). */
function provider(p) {
  const id = String((p && p.id) || "");
  return {
    id,
    label: String((p && p.label) || LABEL[id] || id),
    why: String((p && p.why) || WHY[id] || ""),
    needsKey: Boolean(p && p.needs_key),
    keySaved: p && typeof p.key_saved === "boolean" ? p.key_saved : null,
    keyWhere: String((p && p.key_where) || KEY_WHERE[id] || ""),
    ready: Boolean(p && p.ready),
    state: String((p && p.state) || ""),
    said: String((p && p.said) || ""),
  };
}

/**
 * GET /api/search (through get_web_search), read. `available: false` with
 * `why` for a PC without it.
 */
export function readSearch(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  if (a.available === false) return { available: false, why: String(a.why || MISSING) };
  const providers = Array.isArray(a.providers)
    ? a.providers.filter((p) => p && PROVIDERS.includes(p.id)).map(provider)
    : [];
  if (!providers.length) return { available: false, why: MISSING };
  const leftOut = Array.isArray(a.left_out)
    ? a.left_out
        .filter((x) => x && x.label)
        .map((x) => ({ label: String(x.label), why: String(x.why || "") }))
    : [{ label: "Whoogle", why: WHOOGLE_WHY }];
  return {
    available: true,
    provider: PROVIDERS.includes(a.provider) ? a.provider : null,
    why: String(a.why || ""),
    defaultWhy: String(a.default_why || DEFAULT_WHY),
    providers,
    leftOut,
    address: String(a.searxng_url || DEFAULT_ADDRESS),
    askEveryTime: a.ask_every_time === true,
    askLabel: String(a.ask_every_time_label || ASK_LABEL),
    askDetail: String(a.ask_every_time_detail || ASK_DETAIL),
    keyEntry: String(a.key_entry || KEY_ENTRY),
    waiting: a.waiting === true,
    last: a.last && typeof a.last === "object" ? String(a.last.message || "") : "",
  };
}

/** The line under a provider: in use, ready, or what stands in the way. */
export function providerLine(p, chosen) {
  const now = p.id === chosen ? `${CHOSEN} ` : "";
  return (p.ready ? `${now}${READY}` : `${now}${p.said}`).trim();
}

/** The line under a key: saved, not, or unknown - never the key. */
export function keyLine(p) {
  if (p.keySaved === true) return KEY_SAVED;
  if (p.keySaved === false) return KEY_NONE;
  return KEY_UNKNOWN;
}

/** Test search's answer, as one line and a tone. */
export function testWords(out) {
  const o = out && typeof out === "object" ? out : {};
  const said = String(o.said || o.error || "It did not work.");
  const offer = o.ok ? "" : String(o.offer || "");
  return { text: offer ? `${said} ${offer}` : said, tone: o.ok ? "ok" : "bad" };
}
