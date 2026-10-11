/**
 * Settings -> "Chatbot API keys" (docs/ACCOUNT-KEYS-DESIGN.md steps 1-5,
 * 2026-10-06; the owner's decision 1: "keys and limits together").
 *
 * Five Rust commands, Settings only:
 *  - get_chatbot_api_keys / save_chatbot_api_key / forget_chatbot_api_key
 *    (src-tauri/src/account_secrets.rs): one key into (or out of) Credential
 *    Manager on this PC. The box is emptied as soon as it is sent and the key
 *    is never shown again, exactly like the Accounts page's four secrets;
 *  - chatbot_limits / set_chatbot_limit (src-tauri/src/chatbot_money.rs): the
 *    monthly money limit and the price list of the same six services, read
 *    from the PC and set from here. A key with no limit leaves the service
 *    unusable, which is why the two halves are one card.
 *
 * NO APPROVAL CARD FOR A KEY, and that is a written decision: saving the
 * owner's own key for the owner's own account is the owner configuring their
 * own accounts (docs/JARVIS-API.md:8471-8475, the same rule the Accounts page
 * follows).
 *
 * A CARD FOR A RAISE, and NO CARD FOR ANYTHING ELSE. Raising a monthly limit
 * is a loosening, so the PC raises ONE approval card naming the service and
 * both amounts, asks Windows Hello for it, and refuses it from any other
 * device. Lowering one, removing one, correcting a price and resetting one
 * only tighten or correct. Which of the two a change is decided by the PC
 * from the amount against the limit it already holds; this page only uses the
 * owner's own number to say beforehand whether a card is coming, and shows
 * whichever the PC says actually happened.
 *
 * There is no such page on the phone: the owner is never asked for an account
 * secret there, and the PC refuses the money route to anything but itself.
 *
 * @module chatbot-api-keys-settings
 */

import { announce } from "./jarvis-link.js";
import {
  changeWords,
  estimatesLine,
  FORGET_LABEL,
  HELP,
  LABEL,
  limitActionFor,
  limitButtonWords,
  MISSING,
  moneyFor,
  raiseWords,
  readChatbotApiKeys,
  SAVE_LABEL,
  statusLine,
} from "./chatbot-api-keys.js";

const TAURI = globalThis.__TAURI__;
const IS_TAURI = Boolean(TAURI && TAURI.core && TAURI.core.invoke);
const $ = (id) => document.getElementById(id);

async function invoke(command, args = {}) {
  if (!IS_TAURI) throw new Error("no desktop backend");
  return TAURI.core.invoke(command, args);
}

const as = {
  section: $("chatbot-api-keys"),
  body: $("cak-body"),
  status: $("cak-status"),
  estimates: $("cak-estimates"),
  raiseWords: $("cak-raise-words"),
};

let busy = false;
/** The last money answer: what the PC said about every service. Never
 *  invented here, and never kept anywhere but in this page's memory. */
let money = null;

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

function say(text, tone) {
  if (!as.status) return;
  as.status.textContent = text;
  if (tone) as.status.dataset.tone = tone;
  else delete as.status.dataset.tone;
}

/** An error in words, never a bridge error or JSON. */
function problemWords(error) {
  const said = String((error && error.message) || error || "").trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 400) {
    return "Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}

function setBusy(v) {
  busy = v;
  if (!as.body) return;
  for (const el of as.body.querySelectorAll("button")) el.disabled = v;
}

/** The one-line "where to make a key" address, as a real link - it is a page
 *  the owner opens in their own browser, not something this app fetches. */
function whereLine(entry) {
  const p = node("p", "note");
  p.append(document.createTextNode("Make a key here: "));
  const a = document.createElement("a");
  a.href = entry.keyWhere;
  a.target = "_blank";
  a.rel = "noreferrer";
  a.textContent = entry.keyWhere;
  p.append(a);
  return p;
}

/** The money half of one service's row: the limit, what is spent, and the
 *  price with where it came from. Everything shown is the PC's own. */
function moneyRow(entry, m) {
  const box = node("div", "cak-money");
  box.dataset.money = entry.service;
  if (!m) {
    box.append(node("p", "sc-line", "The monthly money limit for this service could not be "
      + "read from this PC."));
    return box;
  }
  box.append(node("p", "sc-line", m.line));
  box.append(node("p", "note",
    `Spent this month: ${m.spentWords}. Left: ${m.leftWords}. The count starts again on ${m.until}.`));

  // The limit itself. A disabled row with the PC's own reason beats a control
  // that would be refused.
  if (m.canChange) {
    const line = node("div", "row sc-command");
    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.step = "0.01";
    input.id = `cak-limit-${entry.service}`;
    input.placeholder = m.limit === null ? "no limit set" : String(m.limit);
    input.value = m.limit === null ? "" : String(m.limit);
    input.setAttribute("aria-label", `${LABEL[entry.service]} monthly money limit in dollars`);
    const save = node("button", "btn small", "");
    save.type = "button";
    const paintButton = () => {
      const action = limitActionFor(m.limit, input.value);
      save.textContent = limitButtonWords(m.limit, input.value);
      save.disabled = action === null;
      // Said BEFORE the tap: a raise waits on an approval card and on Windows
      // Hello, and that can take minutes.
      save.title = action === "raise_limit"
        ? "This one asks you on an approval card, with Windows Hello on this PC."
        : action === "lower_limit"
          ? "This one only spends less, so it changes at once, with no card."
          : "";
    };
    paintButton();
    input.addEventListener("input", paintButton);
    save.addEventListener("click", () => change(entry, "limit", input));
    const remove = node("button", "btn ghost small", "Remove the limit");
    remove.type = "button";
    remove.hidden = m.limit === null;
    remove.addEventListener("click", () => change(entry, "remove_limit"));
    line.append(input, save, remove);
    box.append(line);
    const hint = node("p", "note", "");
    const paintHint = () => {
      const typed = input.value;
      hint.textContent = limitActionFor(m.limit, typed) === "raise_limit"
        ? (m.limit === null
            ? "Setting a limit lets Jarvis use this service at all. Nothing is used without one."
            : "This raises the limit, so it asks you on an approval card first, and Windows "
              + "Hello on this PC confirms it is you.")
        : limitActionFor(m.limit, typed) === "lower_limit"
          ? "This lowers the limit, so it changes at once - no card."
          : "";
    };
    paintHint();
    input.addEventListener("input", paintHint);
    box.append(hint);
  } else {
    box.append(node("p", "sc-line",
      "The monthly money limit is set on this PC only."));
  }

  // The price, with its own source and date (decision 4).
  if (m.price) {
    const p = node("div", "cak-price");
    p.dataset.price = entry.service;
    p.append(node("p", "sc-line", m.price.line));
    if (m.canChange) {
      const line = node("div", "row sc-command");
      const pin = document.createElement("input");
      pin.type = "number";
      pin.min = "0";
      pin.step = "0.01";
      pin.id = `cak-price-in-${entry.service}`;
      pin.placeholder = "in";
      pin.value = m.price.in === null ? "" : String(m.price.in);
      pin.setAttribute("aria-label", `${LABEL[entry.service]} price per million word-pieces in`);
      const pout = document.createElement("input");
      pout.type = "number";
      pout.min = "0";
      pout.step = "0.01";
      pout.id = `cak-price-out-${entry.service}`;
      pout.placeholder = "out";
      pout.value = m.price.out === null ? "" : String(m.price.out);
      pout.setAttribute("aria-label", `${LABEL[entry.service]} price per million word-pieces out`);
      const save = node("button", "btn small", "Correct this price");
      save.type = "button";
      save.addEventListener("click", () => change(entry, "set_price", null, pin, pout));
      const reset = node("button", "btn ghost small", "Back to the default");
      reset.type = "button";
      reset.hidden = m.price.source !== "yours";
      reset.addEventListener("click", () => change(entry, "reset_price"));
      line.append(pin, pout, save, reset);
      p.append(line);
      p.append(node("p", "note",
        `This is the price for model ${m.price.model}, in dollars per million word-pieces `
        + `(tokens). Correcting it is not a loosening, so it changes at once with no card - `
        + `and every amount spent is only ever an estimate from it.`));
    }
    if (m.price.pricePage) {
      const page = node("p", "note");
      page.append(document.createTextNode("Check the real price here: "));
      const a = document.createElement("a");
      a.href = m.price.pricePage;
      a.target = "_blank";
      a.rel = "noreferrer";
      a.textContent = m.price.pricePage;
      page.append(a);
      p.append(page);
    }
    box.append(p);
  }

  if (m.cap) box.append(node("p", "note", m.cap));
  return box;
}

function row(entry) {
  const box = node("div", "sc-switch");
  box.dataset.service = entry.service;
  const id = `cak-${entry.service}`;
  const label = node("label", "label", LABEL[entry.service]);
  label.htmlFor = id;
  const line = node("div", "row sc-command");
  const input = document.createElement("input");
  input.type = "password";
  input.id = id;
  input.autocomplete = "off";
  input.spellcheck = false;
  input.placeholder = `Paste your ${LABEL[entry.service]} API key`;
  input.disabled = entry.envSet;
  const save = node("button", "btn small", SAVE_LABEL);
  save.type = "button";
  save.disabled = entry.envSet;
  save.addEventListener("click", () => save_(entry, input));
  const forget = node("button", "btn ghost small", FORGET_LABEL);
  forget.type = "button";
  forget.hidden = entry.saved !== true;
  forget.disabled = entry.envSet;
  forget.addEventListener("click", () => forget_(entry));
  line.append(input, save, forget);
  box.append(label, line);
  box.append(node("p", "sc-line", statusLine(entry)));
  box.append(whereLine(entry));
  box.append(node("p", "note", HELP[entry.service]));
  box.append(moneyRow(entry, moneyFor(money, entry.service)));
  return box;
}

function paint(entries) {
  if (!as.body) return;
  as.body.replaceChildren(...entries.map(row));
}

function paintWords() {
  if (as.estimates) as.estimates.textContent = estimatesLine(money);
  if (as.raiseWords) as.raiseWords.textContent = raiseWords(money);
}

async function load() {
  if (!as.section || !IS_TAURI) return;
  try {
    const entries = readChatbotApiKeys(await invoke("get_chatbot_api_keys"));
    // The money half is its own read: a PC that cannot answer it still shows
    // the six key boxes, with the money row saying so, rather than nothing.
    try {
      const answer = await invoke("chatbot_money");
      money = answer && answer.available === false ? null : answer;
      if (money === null) say(String((answer && answer.why) || MISSING), "bad");
    } catch (error) {
      money = null;
      say(problemWords(error), "bad");
    }
    paintWords();
    paint(entries);
  } catch (error) {
    say(problemWords(error) || MISSING, "bad");
  }
}

async function save_(entry, input) {
  if (busy) return;
  const value = input.value;
  // Emptied at once: the key is not kept in the page a moment longer than
  // the one call that saves it.
  input.value = "";
  if (!value.trim()) {
    say(`Paste a ${LABEL[entry.service]} API key first.`, "bad");
    return;
  }
  setBusy(true);
  try {
    const out = await invoke("save_chatbot_api_key", { service: entry.service, value });
    say(String((out && out.said) || "Saved."), "ok");
    announce(as.status.textContent);
  } catch (error) {
    say(problemWords(error), "bad");
  } finally {
    setBusy(false);
  }
  await load();
}

async function forget_(entry) {
  if (busy) return;
  setBusy(true);
  try {
    const out = await invoke("forget_chatbot_api_key", { service: entry.service });
    say(String((out && out.said) || "Removed."), "ok");
  } catch (error) {
    say(problemWords(error), "bad");
  } finally {
    setBusy(false);
  }
  await load();
}

/**
 * ONE money change. `kind` is "limit", "remove_limit", "set_price" or
 * "reset_price". Which of the two directions a "limit" is, and therefore
 * whether a card is raised, is the PC's decision from the amount against the
 * limit it holds - this only passes the owner's own number.
 *
 * A raise can wait minutes (the card sits until it is answered, and Windows
 * Hello is asked while it does), so the buttons stay disabled and the line
 * says what is being waited for.
 */
async function change(entry, kind, limitInput, priceIn, priceOut) {
  if (busy) return;
  const args = { service: entry.service };
  if (kind === "limit") {
    const typed = Number(limitInput && limitInput.value);
    const action = limitActionFor(moneyFor(money, entry.service)?.limit ?? null, typed);
    if (action === null) {
      say(`Type how many dollars a month for ${LABEL[entry.service]} first.`, "bad");
      return;
    }
    args.action = action;
    args.dollars = typed;
    setBusy(true);
    if (action === "raise_limit") {
      say(`Waiting for your approval card, and Windows Hello, for ${LABEL[entry.service]}...`);
    } else {
      say(`Lowering the limit for ${LABEL[entry.service]}...`);
    }
  } else if (kind === "remove_limit") {
    args.action = "remove_limit";
    setBusy(true);
    say(`Removing the limit for ${LABEL[entry.service]}...`);
  } else if (kind === "set_price") {
    const pin = Number(priceIn && priceIn.value);
    const pout = Number(priceOut && priceOut.value);
    if (!Number.isFinite(pin) || !Number.isFinite(pout) || pin < 0 || pout < 0) {
      say(`Type both prices for ${LABEL[entry.service]}: dollars per million in, then out.`, "bad");
      return;
    }
    args.action = "set_price";
    args.priceIn = pin;
    args.priceOut = pout;
    setBusy(true);
  } else {
    args.action = "reset_price";
    setBusy(true);
  }
  try {
    const answer = await invoke("set_chatbot_money", args);
    // The whole new view comes back with the answer, so the page repaints
    // from the PC's own numbers rather than from what was typed.
    money = answer && answer.available === false ? null : answer;
    say(changeWords(answer), "ok");
    announce(as.status.textContent);
  } catch (error) {
    // A refusal is the PC's own sentence: "You said no, so the limit was not
    // raised", "This is set on the PC only...", or the catching-up line.
    say(problemWords(error), "bad");
  } finally {
    setBusy(false);
  }
  await load();
}

if (as.section) {
  load();
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) load();
  });
}
