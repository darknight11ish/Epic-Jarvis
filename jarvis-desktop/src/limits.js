/**
 * Settings -> "Limits and frequency": the reading half (2026-10-08).
 *
 * The PC owns this list (`backend/jarvis_limits.py`, one table for every limit;
 * `GET /api/limits` answers it through `limits-read.patch`). Everything here is
 * pure: it turns the answer into the rows the page draws, and turns a click
 * into the JSON value the backend expects. The module that talks to Rust is
 * `limits-settings.js`, so this half can be tested without a window - the same
 * split `reach.js` / `reach-settings.js` uses.
 *
 * WHAT THE PAGE MUST NOT DECIDE. Which way a change goes is the backend's: it
 * compares the value with the number already in force, and turning one UP that
 * lets Jarvis do more is a loosening it puts to the owner on an approval card
 * before writing anything. So this file never sends "raise"/"lower" - only a
 * key and a value - and never says a change happened until the PC says so.
 *
 * @module limits
 */

/** The shape a card draws, from whatever the PC answered. */
export function normaliseLimits(body) {
  const raw = body && typeof body === "object" ? body : {};
  if (raw.available === false) {
    return { available: false, why: String(raw.why || ""), rows: [] };
  }
  const rows = Array.isArray(raw.limits) ? raw.limits : [];
  return {
    available: true,
    why: "",
    rows: rows
      .filter((r) => r && typeof r === "object" && r.key)
      // This page IS the PC, so it offers the limits the PC may change. A row
      // marked `phone` belongs to the phone's own settings and is left out -
      // the PC's card must not offer a control the phone owns. The route sends
      // every row with its own `app`, so this is the page filtering on what
      // each row says, not a guess: the same route serves the phone, which
      // keeps the rows marked `phone` and `both`.
      .filter((r) => r.app !== "phone")
      .map((r) => ({
        key: String(r.key),
        title: String(r.title || r.key),
        kind: r.kind === "bool" ? "bool" : "int",
        value: r.kind === "bool" ? r.value === true : Number(r.value),
        words: String(r.words || ""),
        choices: Array.isArray(r.choices) ? r.choices.map(Number) : [],
        low: Number(r.low ?? 0),
        high: Number(r.high ?? 0),
        unit: String(r.unit || ""),
        note: String(r.note || ""),
        loosenUp: r.loosen_up === true,
        pcOnly: r.pc_only === true,
      })),
  };
}

/**
 * The value one step from `value`, in `direction` (-1 or +1), or null when
 * there is nowhere to go. With choices, a step is the next choice (so a limit
 * stored as 7 and offered as 1/24/168 steps to 24 rather than to 8, which the
 * backend would refuse); without them it is one whole number inside low..high.
 */
export function stepped(limit, direction) {
  if (!limit || limit.kind === "bool") return null;
  const dir = direction < 0 ? -1 : 1;
  if (limit.choices.length) {
    const sorted = [...limit.choices].sort((a, b) => a - b);
    const next = dir > 0 ? sorted.find((c) => c > limit.value)
                         : [...sorted].reverse().find((c) => c < limit.value);
    return next === undefined ? null : next;
  }
  const next = limit.value + dir;
  if (next < limit.low || next > limit.high) return null;
  return next;
}

/** The JSON value a control sends for `value` on `limit`. */
export function valueFor(limit, value) {
  return limit && limit.kind === "bool" ? value === true : Number(value);
}

/** What a row says about the number it holds now. */
export function rowWords(limit) {
  if (!limit) return "";
  if (limit.words) return limit.words;
  if (limit.kind === "bool") return limit.value ? "on" : "off";
  return `${limit.value}${limit.unit ? " " + limit.unit : ""}`;
}

/** An error in words, never a bridge error or JSON. */
export function problemWords(error) {
  // `error.message` may be an empty string, and `"" || error` then falls
  // through to the error ITSELF - which is how a blank bridge failure used to
  // put the bare word "Error" on the page. Read the message when there is one,
  // whatever it says, and only then fall back.
  const raw = error && error.message !== undefined ? error.message : error;
  const said = String(raw === null || raw === undefined ? "" : raw).trim();
  if (!said || /[{}<>]|::|not allowed|undefined|null/i.test(said) || said.length > 400) {
    return "Could not change that. Try again in a moment, or restart Jarvis Desktop.";
  }
  return said;
}
