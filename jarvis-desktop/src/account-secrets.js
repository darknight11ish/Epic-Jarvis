/**
 * Accounts (ease-of-use audit row 15, "Security G3" - and the owner's
 * decision of 2026-10-06) - the words, and how to read what
 * get_account_secrets and get_account_addresses send.
 *
 * TWO SHAPES, and this page holds one of each:
 *
 *  - the four SECRETS (SECRETS below): the IMAP username and password, the
 *    private calendar link and the Home Assistant token. They used to be
 *    plain Windows user environment variables - which Windows itself stores
 *    as plain text. Each has its own box here, written straight into Windows
 *    Credential Manager on this PC (account-secrets-settings.js;
 *    src-tauri/src/account_secrets.rs, token_store.rs). Never over HTTP,
 *    never to the phone.
 *  - the eight ADDRESSES and one choice (ADDRESSES below): the mail server,
 *    its port and mailbox, the sending server, its port and how the email is
 *    encrypted, the Home Assistant address and the calendar's CalDAV
 *    address. An address is not a secret, so it takes the shape this project
 *    already proved for the SearXNG address: a backend route that keeps it in
 *    accounts.json in the config folder and hands it back
 *    (src-tauri/src/account_addresses.rs, backend/jarvis_accounts.py,
 *    backend/accounts.patch). Also desktop only - the phone has no such page
 *    (deep config editing stays off it, CLAUDE.md).
 *
 * The matching environment variable, if the owner already has one, keeps
 * winning on the backend either way - and for an address, that is said on the
 * row rather than pretended away.
 *
 * @module account-secrets
 */

export const TITLE = "Accounts";

export const SECRETS = Object.freeze([
  "imap_user",
  "imap_password",
  "calendar_ics_url",
  "home_token",
]);

export const LABEL = Object.freeze({
  imap_user: "IMAP username",
  imap_password: "IMAP password",
  calendar_ics_url: "Calendar iCal link",
  home_token: "Home Assistant token",
});

export const ENV_VAR = Object.freeze({
  imap_user: "JARVIS_IMAP_USER",
  imap_password: "JARVIS_IMAP_PASSWORD",
  calendar_ics_url: "JARVIS_CALENDAR_ICS_SECRET_URL",
  home_token: "JARVIS_HOME_TOKEN",
});

export const PLACEHOLDER = Object.freeze({
  imap_user: "you@example.com",
  imap_password: "Paste your mail password or app password",
  calendar_ics_url: "Paste the “Secret address in iCal format”",
  home_token: "Paste your Home Assistant long-lived access token",
});

export const HELP = Object.freeze({
  imap_user: "The email address (or account name) you sign in to your mail server with. Used for both reading and sending mail.",
  imap_password: "Your mail server's password - or an app password, if your provider (Gmail, for one) needs one instead.",
  calendar_ics_url: "Google Calendar → the gear icon → Settings → your calendar → Integrate calendar → “Secret address in iCal format”. Anyone with this link can read the calendar, so it is handled like a password.",
  home_token: "Home Assistant → your profile (bottom left) → Security → Long-Lived Access Tokens → Create Token.",
});

/** Text vs password input for the box: only the username is shown as typed. */
export const MASKED = Object.freeze({
  imap_user: false,
  imap_password: true,
  calendar_ics_url: true,
  home_token: true,
});

export const SAVE_LABEL = "Save";
export const FORGET_LABEL = "Remove";
export const MISSING =
  "Could not read which accounts are set up on this PC.";

/* ── The eight addresses and the one choice ─────────────────────────────── */

export const ADDRESSES_TITLE = "Server addresses";

export const ADDRESSES_NOTE =
  "Where each account lives. These are addresses, not secrets: they are kept in a plain settings file on this PC (accounts.json), and typed here rather than in a Windows environment variable. If you already set one of them as an environment variable, that still wins and the row says so.";

/**
 * The eight, in the same order the PC sends them
 * (jarvis_accounts.FIELDS, and every reader's own order).
 */
export const ADDRESSES = Object.freeze([
  "imap_host",
  "imap_port",
  "imap_mailbox",
  "smtp_host",
  "smtp_port",
  "smtp_tls",
  "home_url",
  "caldav_url",
]);

export const ADDRESS_LABEL = Object.freeze({
  imap_host: "Mail server (reading)",
  imap_port: "Mail server port",
  imap_mailbox: "Mailbox folder",
  smtp_host: "Sending server",
  smtp_port: "Sending server port",
  smtp_tls: "How email is encrypted on its way out",
  home_url: "Home Assistant address",
  caldav_url: "Calendar (CalDAV) address",
});

export const ADDRESS_ENV_VAR = Object.freeze({
  imap_host: "JARVIS_IMAP_HOST",
  imap_port: "JARVIS_IMAP_PORT",
  imap_mailbox: "JARVIS_IMAP_MAILBOX",
  smtp_host: "JARVIS_SMTP_HOST",
  smtp_port: "JARVIS_SMTP_PORT",
  smtp_tls: "JARVIS_SMTP_TLS",
  home_url: "JARVIS_HOME_URL",
  caldav_url: "JARVIS_CALDAV_URL",
});

export const ADDRESS_PLACEHOLDER = Object.freeze({
  imap_host: "imap.gmail.com",
  imap_port: "993",
  imap_mailbox: "INBOX",
  smtp_host: "Leave empty to work it out from the mail server",
  smtp_port: "465",
  smtp_tls: "",
  home_url: "http://homeassistant.local:8123",
  caldav_url: "https://caldav.example.com/dav/",
});

export const ADDRESS_HELP = Object.freeze({
  imap_host: "The server Jarvis reads your inbox from. Your email provider's help page calls it the IMAP server.",
  imap_port: "993 is the usual port for a mail server you read securely. Leave empty to use 993.",
  imap_mailbox: "Which folder to read. Leave empty for INBOX.",
  smtp_host: "The server Jarvis sends mail through. Leave empty and Jarvis works it out from the mail server above when it starts with “imap.” (imap.gmail.com → smtp.gmail.com).",
  smtp_port: "465 keeps the usual default (encrypted from the first byte). 587 is the other common one.",
  smtp_tls: "Encrypted before logging in (STARTTLS) is the safe choice on any port but 465. “Not encrypted” is allowed only to a server on this PC or your own networks - a local mail bridge - never across the internet.",
  home_url: "Home Assistant's own address, e.g. http://homeassistant.local:8123 or the address you open it at. Plain http:// is allowed only on this PC or your own networks (home network, Tailscale, NordNet Meshnet); use https:// for anything else.",
  caldav_url: "A CalDAV calendar's address, if you use one that is not Google. Google Calendar is read through the private iCal link above instead.",
});

/** A field that is a choice rather than free text, and its options. The empty
 *  choice is "not set here", which lets the default apply. */
export const ADDRESS_CHOICES = Object.freeze({
  smtp_tls: Object.freeze([
    Object.freeze({ value: "", label: "Not set here (use the usual default)" }),
    Object.freeze({ value: "ssl", label: "ssl - encrypted from the first byte (the default on port 465)" }),
    Object.freeze({ value: "starttls", label: "starttls - the server must encrypt before logging in" }),
    Object.freeze({ value: "off", label: "off - NOT encrypted (a server on this PC or your own network only)" }),
  ]),
});

export const ADDRESS_SAVE_LABEL = "Save";
export const ADDRESSES_MISSING =
  "Could not read the account addresses from this PC.";
export const ADDRESSES_LOADING = "Checking the server addresses…";

/**
 * get_account_addresses's answer, read into one row per address, always all
 * eight in ADDRESSES's order - never depends on the PC sending them in any
 * particular order or sending all eight. `value` is the address saved on this
 * PC ("" when none is); an environment variable's own value is never in the
 * answer, only whether one is set.
 */
export function readAccountAddresses(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  const rows = Array.isArray(a.fields) ? a.fields : [];
  return ADDRESSES.map((name) => {
    const row = rows.find((r) => r && r.name === name) || {};
    return {
      name,
      label: ADDRESS_LABEL[name],
      envVar: ADDRESS_ENV_VAR[name],
      envSet: row.env_set === true,
      value: typeof row.value === "string" ? row.value : "",
      choices: ADDRESS_CHOICES[name] || null,
      why: typeof a.why === "string" ? a.why : "",
    };
  });
}

/** The line under one box: where the address in force comes from, and never
 *  a value this page was not given. */
export function addressStatusLine(entry) {
  if (!entry) return "Could not check.";
  if (entry.envSet) {
    return `Already set as ${entry.envVar} on this PC - that is what Jarvis uses, so what is typed here is ignored until it is removed there.`;
  }
  if (entry.value) return "Saved on this PC.";
  return "Not set.";
}

/**
 * get_account_secrets's answer, read into one row per secret, always all
 * four in SECRETS's order - never depends on the PC sending them in any
 * particular order or sending all four.
 */
export function readAccountSecrets(answer) {
  const a = answer && typeof answer === "object" ? answer : {};
  const rows = Array.isArray(a.secrets) ? a.secrets : [];
  return SECRETS.map((name) => {
    const row = rows.find((r) => r && r.name === name) || {};
    return {
      name,
      label: LABEL[name],
      envVar: ENV_VAR[name],
      envSet: row.env_set === true,
      saved: typeof row.saved === "boolean" ? row.saved : null,
    };
  });
}

/** The line under one box: never claims to know a value, only whether one is
 *  set, and where it is coming from. */
export function statusLine(entry) {
  if (!entry) return "Could not check.";
  if (entry.envSet) {
    return `Already set as ${entry.envVar} on this PC - that is used, so nothing typed here takes effect until it is removed there.`;
  }
  if (entry.saved === true) return "Saved in Windows Credential Manager on this PC.";
  if (entry.saved === false) return "Not set.";
  return "Could not check whether one is saved.";
}
