/**
 * "Chatbot API keys" - the words, and how to read what get_chatbot_api_keys
 * sends (docs/ACCOUNT-KEYS-DESIGN.md steps 1-2, 2026-10-06).
 *
 * Six services, one box each. The key is typed here and goes straight into
 * Windows Credential Manager on this PC - the same shape as the Accounts
 * page's four secrets (account-secrets.js, src-tauri/src/account_secrets.rs,
 * token_store.rs), like the web search keys before it. It is never sent over
 * HTTP to the backend, never to the phone, and never shown again once saved
 * (rule 3).
 *
 * THE NAMES ARE NOT THIS FILE'S TO CHOOSE. The backend reads each key under
 * the Credential Manager name its own Python side builds
 * (`jarvis_chatbot_api.KEY_TARGETS`, from `PRESETS[pid].company`), and the
 * desktop writes under `token_store.rs`'s `CHATBOT_API_KEY_TARGETS`. Those
 * two are pinned against each other by a generated fixture
 * (`backend/tests/fixtures/chatbot-api-key-targets.json`,
 * `tools/gen_chatbot_key_targets.py`), with a test on each side:
 * `backend/test_chatbot_keys.py` and `token_store.rs`'s own
 * `the_six_chatbot_targets_are_the_python_sides_own`. Nothing here may
 * disagree with either.
 *
 * @module chatbot-api-keys
 */

export const TITLE = "Chatbot API keys";

/** The six services, in the order the Rust table lists them. */
export const SERVICES = Object.freeze([
  "openai",
  "deepseek",
  "mistral",
  "xai",
  "openrouter",
  "groq",
]);

/** The name the owner knows the service by. */
export const LABEL = Object.freeze({
  openai: "ChatGPT (OpenAI)",
  deepseek: "DeepSeek",
  mistral: "Mistral",
  xai: "Grok (xAI)",
  openrouter: "OpenRouter",
  groq: "Groq",
});

/** The company whose account the key belongs to - the words the backend
 *  itself uses (`PRESETS[pid].company`), so the page and the PC agree. */
export const COMPANY = Object.freeze({
  openai: "OpenAI",
  deepseek: "DeepSeek",
  mistral: "Mistral AI",
  xai: "xAI",
  openrouter: "OpenRouter",
  groq: "Groq",
});

/** Where the owner makes a key - each one's own page
 *  (`PRESETS[pid].key_where`, carried in the generated fixture). */
export const KEY_WHERE = Object.freeze({
  openai: "https://platform.openai.com/api-keys",
  deepseek: "https://platform.deepseek.com/api_keys",
  mistral: "https://console.mistral.ai/api-keys",
  xai: "https://console.x.ai",
  openrouter: "https://openrouter.ai/keys",
  groq: "https://console.groq.com/keys",
});

/** What the one line under the box says, per service. */
export const HELP = Object.freeze({
  openai:
    "Make a key at platform.openai.com → API keys. Each answer costs a little on your OpenAI account.",
  deepseek:
    "Make a key at platform.deepseek.com → API keys. DeepSeek's answers are counted from an estimate: its own cap on answer length could not be checked.",
  mistral:
    "Make a key at console.mistral.ai → API keys. Each answer costs a little on your Mistral account.",
  xai: "Make a key at console.x.ai. Each answer costs a little on your xAI account.",
  openrouter:
    "Make a key at openrouter.ai → Keys. OpenRouter passes each message on to the company that runs the model you chose, under that company's terms too - and it reports the real cost of each answer, which Jarvis counts instead of estimating.",
  groq: "Make a key at console.groq.com → API keys. Groq has a free tier, so this one may cost nothing.",
});

/** Every key is masked: none of these is ever shown as typed. */
export const MASKED = true;

export const SAVE_LABEL = "Save";
export const FORGET_LABEL = "Remove";
export const MISSING = "Could not read which chatbot keys are saved on this PC.";

/** Plain words for a service that is not one of the six - only ever shown
 *  for a name the PC sent that this page does not know. */
export function unknownService(service) {
  return `${service} is not one of the six chatbot services this page knows.`;
}

/**
 * get_chatbot_api_keys's answer, read into one row per service, always all
 * six in SERVICES's order - never depends on the PC sending them in any
 * particular order or sending all six.
 */
export function readChatbotApiKeys(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  const rows = Array.isArray(a.services) ? a.services : [];
  return SERVICES.map((service) => {
    const row = rows.find((r) => r && r.service === service) || {};
    return {
      service,
      label: LABEL[service],
      company: COMPANY[service],
      keyWhere: KEY_WHERE[service],
      // There is no environment variable for one of these (unlike the four
      // account secrets): the backend has never read one. Kept in the shape
      // so a page that shows both kinds of box reads one thing.
      envSet: row.env_set === true,
      saved: typeof row.saved === "boolean" ? row.saved : null,
    };
  });
}

/**
 * The line under one box: never claims to know a key, only whether one is
 * saved. Deliberately different words from the Accounts page's own
 * statusLine: there is no environment variable here that could take
 * precedence, so saying nothing about one is the honest line.
 */
export function statusLine(entry) {
  if (!entry) return "Could not check.";
  if (entry.saved === true) return "Saved in Windows Credential Manager on this PC.";
  if (entry.saved === false) return "Not set.";
  return "Could not check whether one is saved.";
}

/* ── The monthly money limit and the price list ───────────────────────────
 *
 * docs/ACCOUNT-KEYS-DESIGN.md steps 3-5, decisions 1, 3 and 4. A key with no
 * limit leaves the service unusable ("no limit, no conversation"), and a
 * limit with no way to raise it puts the owner back in PowerShell exactly
 * when the app should be enough - so the two are one card.
 *
 * THE ONE RULE: raising a limit is a loosening, so the PC raises ONE
 * approval card and asks Windows Hello for it; lowering one, removing one,
 * correcting a price and resetting one need no card at all. Which of the two
 * a change is decided by the PC, from the amount against the limit it holds -
 * never here. This file only picks the word ("raise" or "lower") from what
 * the owner typed, and shows whichever the PC says actually happened.
 */

/** How the page asks the PC for one change, from what the owner typed.
 *  `null` when there is nothing to ask: nothing typed, or something that is
 *  not a number at all. A FIRST limit (nothing set yet) is always a raise,
 *  because there was nothing to loosen before. */
export function limitActionFor(current, typed) {
  const raw = String(typed === null || typed === undefined ? "" : typed).trim();
  if (raw === "") return null;
  const amount = Number(raw);
  if (!Number.isFinite(amount) || amount < 0) return null;
  if (current === null || current === undefined) return "raise_limit";
  return amount > current ? "raise_limit" : "lower_limit";
}

/** The words on the button that sends a typed amount. */
export function limitButtonWords(current, typed) {
  const action = limitActionFor(current, typed);
  if (action === "raise_limit") return current === null || current === undefined
    ? "Set this limit" : "Raise it";
  if (action === "lower_limit") return "Lower it";
  return "Save the limit";
}

/** Whether sending this one will ask for an approval card - said before the
 *  tap, so a 300-second wait is never a surprise. False for a first limit set
 *  to nothing and for anything that only tightens. */
export function willAskForApproval(current, typed) {
  return limitActionFor(current, typed) === "raise_limit";
}

/** One service's money row, read from GET/POST /api/chatbot/money, or null
 *  when the PC answered without it. Every field the page shows comes from
 *  here; nothing is invented on this side. */
export function moneyFor(answer, service) {
  const rows = Array.isArray(answer && answer.services) ? answer.services : [];
  const row = rows.find((r) => r && r.service === service);
  if (!row) return null;
  const price = row.price && typeof row.price === "object" ? row.price : null;
  return {
    // Whether the PC will accept a change at all: false on a PC that answered
    // with `can_change: false` (a request from somewhere else), which the
    // page must not pretend otherwise about.
    canChange: row.can_change === true,
    limit: typeof row.limit === "number" ? row.limit : null,
    limitWords: String(row.limit_words || ""),
    spentWords: String(row.spent_words || ""),
    leftWords: String(row.left_words || ""),
    until: String(row.until || ""),
    reached: row.reached === true,
    // The PC's own sentence about this service's money. Shown as given.
    line: String(row.line || ""),
    // The PC's own sentence about how it keeps to the limit (the answer
    // length cap, and what hidden reasoning does to it).
    cap: String(row.cap || ""),
    price: price
      ? {
          model: String(price.model || ""),
          // "yours" or "default" - the whole point of decision 4.
          source: String(price.source || ""),
          verified: price.verified === true,
          set: String(price.set || ""),
          in: typeof price.in === "number" ? price.in : null,
          out: typeof price.out === "number" ? price.out : null,
          line: String(price.line || ""),
          pricePage: String(price.price_page || ""),
        }
      : null,
  };
}

/** The estimate warning the whole screen carries, from the PC's own answer. */
export function estimatesLine(answer) {
  const said = String((answer && answer.estimates) || "").trim();
  return said || "Every amount here is an estimate from a price list you can correct.";
}

/** The line that says which direction asks for an approval card, from the
 *  PC's own answer. */
export function raiseWords(answer) {
  const said = String((answer && answer.raise_words) || "").trim();
  return said || ("Raising a limit asks you on an approval card, and Windows Hello on this PC "
    + "confirms it is you. Lowering one, removing one and correcting a price change at once, "
    + "with no card.");
}

/** What the page says about a change that came back. The PC's own words are
 *  the sentence; `raised` is what actually happened, which is not always what
 *  was asked for (a "raise" to no more than the current amount is a
 *  lowering). */
export function changeWords(answer) {
  const said = String((answer && answer.said) || "").trim();
  if (said) return said;
  return answer && answer.raised === true
    ? "The limit was raised on your approval card."
    : "Saved.";
}

