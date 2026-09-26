/**
 * Accounts (ease-of-use audit row 15, "Security G3") - the words, and how to
 * read what get_account_secrets sends.
 *
 * The IMAP username and password, the private calendar link, and the Home
 * Assistant token used to be set only as plain Windows user environment
 * variables - which Windows itself stores as plain text. Each now has its
 * own box here, written straight into Windows Credential Manager on this
 * PC (account-secrets-settings.js; src-tauri/src/account_secrets.rs,
 * token_store.rs) - the phone has no such box (deep config editing stays
 * off it, CLAUDE.md). The matching environment variable, if the owner
 * already has one, keeps winning on the backend either way.
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
