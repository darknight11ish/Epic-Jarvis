//! Pillar 14B: the DESKTOP half of the opt-in, RAM-only clipboard time machine.
//!
//! ## What this is
//!
//! The owner copies things all day: a link to clean up, a small table to turn
//! into Markdown, a JSON blob to read, a sentence to keep for a minute. A
//! clipboard history is useful for exactly that. But a clipboard is also the
//! surface a password manager's "copy password" button writes to, where a
//! one-time code from a phone lands, and where a private key or a card number
//! can pass by on its way somewhere else. So this module is built the other way
//! round from an ordinary clipboard manager: it keeps NOTHING until it is
//! turned on, it would rather refuse something useful than keep one secret, and
//! it forgets the lot on the next lock.
//!
//! Slice 14A (`jarvis_clipboard.py`, the Python module and its suite) is another
//! session's slice and is NOT merged into this tree. This module is the desktop
//! wiring that module's own docstring names as slice 14B: a RAM-only ring that
//! mirrors its behaviour, its API shape and its privacy rules exactly, the
//! Windows capture that feeds it, a global hotkey, and the Quickbar transform
//! drawer. It adds no backend route, no Python file, no registration and no
//! model call; nothing here leaves this PC and nothing here touches the disk
//! with a copied word.
//!
//! ## What it is
//!
//! * THE RING. One in-memory `VecDeque`, [`DEFAULT_MAX_ITEMS`] (25) long and
//!   [`DEFAULT_MAX_ITEM_CHARS`] (32768) per item. The newest item is first in
//!   `state()`'s list. A text already in the ring is never stored twice:
//!   re-copying it moves that one entry to the top. Both numbers are
//!   N_placeholder, mirroring the Python slice - not measured on real use.
//! * offer() REFUSES, STORING NOTHING, with the reason in `reason`:
//!   `disabled`, `empty`, `too_large`, `excluded_app`, `secret_detected`,
//!   `secret_or_otp_detected`. The Python module also has `not_text` (its ring
//!   is called from Python, where anything can be passed) and
//!   `scrubber_unavailable` (its judge is an external module that can be
//!   missing); in this process every input is a Rust `&str` already and there
//!   is no external scrubber to be missing, so neither can occur here. That is
//!   said out loud rather than pretended away.
//! * THE JUDGE. Python asks the project's real `jarvis_scrub`; the desktop has
//!   no copy of it, so this module carries a NARROW, deterministic detector of
//!   its own - PEM header, one-time code with the wording that frames one, a
//!   lone generated-password-shaped token, a card number that passes the check
//!   digit, and a short list of labelled credential shapes (a line saying
//!   `password:` and then a value, an AWS access key id, a GitHub token, an
//!   `sk-` API key, a JWT). It CANNOT recognise every secret - a brand-new key
//!   format, a screenshot of a password, or a secret split across two copies
//!   can still get through. Privacy here comes from being OFF by default and
//!   from wiping on lock, not from a perfect classifier. That is the Python
//!   module's own honest sentence, and it is no less true here.
//! * THE TRANSFORMS. [`transform`] is a pure function - it keeps nothing - for
//!   exactly three kinds, and always returns the same four fields
//!   `{ok, kind, text, reason}`: `markdown_table` (CSV or TSV, a tab on the
//!   first non-empty line selects TSV, -> a pipe table with a `| --- |`
//!   separator row), `pretty_json`, and `strip_tracking_params` (every http(s)
//!   URL's tracking parameters removed, every other parameter kept in its
//!   order, trailing sentence punctuation untouched). The results are the
//!   Python module's results for every ordinary input the two are given: the
//!   pretty-JSON transform parses the text itself, so it keeps each object's
//!   key order and each integer's exact digits rather than going through a
//!   sorted map. The known differences are narrow refusals, never a
//!   half-transformed table: a lone-surrogate `\ud800` escape (a Rust `String`
//!   cannot hold one) and nesting deeper than [`JSON_MAX_DEPTH`] levels are
//!   refused, where Python's own decoder is bounded by its recursion limit.
//! * THE CAPTURE. A watcher started once at startup ticks every
//!   [`WATCH_EVERY`] (N_placeholder: not measured). It reads Windows' own
//!   clipboard sequence number first - a cheap call that does not open the
//!   clipboard - and only reads the text when the sequence changed. It never
//!   writes anything to disk, and it never logs a copied word.
//! * THE LOCK. App lock (`lock.rs`) and the Windows session lock (the same
//!   check `live.rs` already uses to end Jarvis Live) both wipe the ring AND
//!   turn capture off, on the first tick that sees either. The drawer is told
//!   with an event that carries no text, so an open drawer clears itself too.
//! * NOT PERSISTED. The switch starts OFF on every launch. Nothing about this
//!   feature is written to the settings store; there is no store in this file.
//!
//! ## Where it is reached from
//!
//! The global hotkey (`hotkeys::ACTIONS`, `Alt+Shift+C` by default and
//! rebindable in Settings) opens the drawer at the Jarvis bar. The drawer
//! itself is `src/clipboard-drawer.js`, mounted in `src/index.html`, drawn with
//! `style.css` - see its own doc comment. The six Tauri commands at the bottom
//! of this file are the whole IPC surface, each granted to the quickbar only
//! (`permissions/surfaces.toml`'s `clipboard-time-machine` set).
//!
//! ## What this module does NOT do, said plainly
//!
//! * It does not decide WHEN a copy is offered beyond "the clipboard changed":
//!   that is this watcher's own rule, and it is off until the owner turns it
//!   on in the drawer.
//! * It does not put an approval card in front of turning capture on. The
//!   owner's switch IS the approval here (one explicit press, off by default);
//!   the Python module's own note - that a future caller must put the backend's
//!   permission model in front of turning capture on - applies to a caller that
//!   would raise a `jarvis_gate` card, which is the other session's lane.
//! * It does not scrub what it stores. Anything it keeps was judged not to be a
//!   credential; it is kept verbatim so a transform can work on it.

use std::collections::VecDeque;
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{Mutex, MutexGuard};
use std::time::Duration;

use serde::Serialize;
use tauri::{AppHandle, Manager};

/// How many copies the ring keeps. N_placeholder, mirroring the Python slice.
pub const DEFAULT_MAX_ITEMS: usize = 25;

/// The longest single item kept, in characters: 32 KiB of plain text.
pub const DEFAULT_MAX_ITEM_CHARS: usize = 32_768;

/// A window title or process name holding any of these is refused: a password
/// manager's "copy password" and a credential dialog are the two cases the
/// ring exists to survive. Matched case-insensitively as a substring, because
/// a window's title reads "Sign in - Bitwarden" and not just "Bitwarden".
pub const EXCLUDED_APPS: &[&str] = &[
    "1password",
    "bitwarden",
    "keepass",
    "keepassxc",
    "dashlane",
    "lastpass",
    "proton pass",
    "windows security",
    "credential manager",
];

/// Query parameters that identify who clicked a link. A parameter that starts
/// with `utm_` is treated the same way. Everything else is kept.
pub const TRACKING_PARAMS: &[&str] = &[
    "fbclid", "gclid", "msclkid", "mc_eid", "igshid", "_hsenc", "vero_id", "mkt_tok",
];

/// The only three transforms there are. A caller asking for a fourth gets a
/// plain refusal, not a guess at what they meant.
pub const TRANSFORMS: &[&str] = &["markdown_table", "pretty_json", "strip_tracking_params"];

/// How often the watcher looks. N_placeholder: not measured on this PC, the
/// same honesty rule the Python slice states for its own numbers.
const WATCH_EVERY: Duration = Duration::from_millis(700);

/// The plain words the drawer shows when App lock would ask before anything
/// private here may be read or changed.
const LOCKED_WORDS: &str =
    "Jarvis is locked. Open the Jarvis bar and unlock it, then open clipboard history again.";

// ---------------------------------------------------------------------------
//   The ring
// ---------------------------------------------------------------------------

/// One kept copy: the words, and the window they were copied from.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Item {
    pub text: String,
    pub app: String,
    pub title: String,
}

/// What the drawer draws: the switch, the copies newest first, and the bounds.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct StateView {
    pub enabled: bool,
    /// True while App lock (or the Windows lock) would ask before the owner
    /// could look at this window's contents; the drawer closes on it.
    pub locked: bool,
    pub items: Vec<Item>,
    pub max_items: usize,
    pub max_item_chars: usize,
}

/// What one offer did, and why. Always exactly two fields, like the Python
/// ring's `{"kept", "reason"}`.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Offer {
    pub kept: bool,
    pub reason: String,
}

/// One transform's answer. Always exactly the four fields the Python module's
/// `_result` returns.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct TransformResult {
    pub ok: bool,
    pub kind: String,
    pub text: String,
    pub reason: String,
}

/// The opt-in, RAM-only ring buffer. See the module docstring for the lot.
pub struct Ring {
    enabled: bool,
    max_items: usize,
    max_item_chars: usize,
    excluded: Vec<String>,
    items: VecDeque<Item>,
}

impl Default for Ring {
    fn default() -> Self {
        Self::new()
    }
}

impl Ring {
    /// A ring that keeps nothing until it is turned on, with the shipped bounds.
    pub fn new() -> Self {
        Self::with_limits(DEFAULT_MAX_ITEMS, DEFAULT_MAX_ITEM_CHARS, &[])
    }

    /// A ring with the shipped shape and extra refused app names (Settings has
    /// no such list today; the argument exists because the Python ring has it,
    /// and its tests drive one).
    pub fn with_limits(max_items: usize, max_item_chars: usize, extra_excluded: &[&str]) -> Self {
        let mut excluded: Vec<String> = EXCLUDED_APPS.iter().map(|a| a.to_string()).collect();
        excluded.extend(
            extra_excluded
                .iter()
                .map(|a| a.trim().to_lowercase())
                .filter(|a| !a.is_empty()),
        );
        Self {
            enabled: false,
            max_items: max_items.max(1),
            max_item_chars: max_item_chars.max(1),
            excluded,
            items: VecDeque::new(),
        }
    }

    /// The ring, newest first, as copies: a caller cannot edit the ring.
    pub fn items(&self) -> Vec<Item> {
        self.items.iter().cloned().collect()
    }

    /// Is the switch on? Read by the watcher and the commands.
    pub fn enabled(&self) -> bool {
        self.enabled
    }

    /// The owner turned it on. Nothing is offered before this.
    pub fn enable(&mut self) {
        self.enabled = true;
    }

    /// The owner turned it off. The kept copies stay until cleared or locked.
    pub fn disable(&mut self) {
        self.enabled = false;
    }

    /// Offer one copied text to the ring; store it or refuse it plainly.
    ///
    /// A refusal stores nothing and leaves the ring exactly as it was. The
    /// order of the checks is the Python module's order, so the same input
    /// gives the same reason in both halves.
    pub fn offer(&mut self, text: &str, foreground_app: &str, foreground_title: &str) -> Offer {
        if !self.enabled {
            return refused("disabled");
        }
        if text.trim().is_empty() {
            return refused("empty");
        }
        if text.chars().count() > self.max_item_chars {
            return refused("too_large");
        }
        if self.excluded(foreground_app, foreground_title) {
            return refused("excluded_app");
        }
        if secret_reason(text).is_some() {
            return refused("secret_detected");
        }
        if text.to_uppercase().contains("-----BEGIN") {
            return refused("secret_or_otp_detected");
        }
        if one_time_code(text) {
            return refused("secret_or_otp_detected");
        }
        if password_like(text) {
            return refused("secret_or_otp_detected");
        }
        self.store(text, foreground_app, foreground_title);
        Offer {
            kept: true,
            reason: String::new(),
        }
    }

    /// The machine locked: wipe the ring at once and stop capturing.
    ///
    /// Turning capture back on is the owner's switch, not something a lock
    /// event may do by itself.
    pub fn lock(&mut self) {
        self.items.clear();
        self.enabled = false;
    }

    /// Wipe the ring at once, leaving the capture switch as it was.
    pub fn clear(&mut self) {
        self.items.clear();
    }

    fn excluded(&self, app: &str, title: &str) -> bool {
        let haystack = format!("{app}\n{title}").to_lowercase();
        if haystack.trim().is_empty() {
            return false;
        }
        self.excluded.iter().any(|name| haystack.contains(name))
    }

    fn store(&mut self, text: &str, app: &str, title: &str) {
        if let Some(index) = self.items.iter().position(|item| item.text == text) {
            self.items.remove(index);
        }
        self.items.push_front(Item {
            text: text.to_string(),
            app: app.to_string(),
            title: title.to_string(),
        });
        while self.items.len() > self.max_items {
            self.items.pop_back();
        }
    }
}

fn refused(reason: &str) -> Offer {
    Offer {
        kept: false,
        reason: reason.to_string(),
    }
}

// ---------------------------------------------------------------------------
//   The judge: a narrow, deterministic copy of the refusals
// ---------------------------------------------------------------------------

/// The words that signal a one-time code is about to appear (or has just
/// appeared). The 4-8 digit code must be within [`OTP_WINDOW`] characters of
/// one of them, so "the login page loaded" is not a code.
const OTP_WORDS: &[&str] = &[
    "code",
    "otp",
    "verification",
    "verify",
    "passcode",
    "2fa",
    "two-factor",
    "one-time",
    "login",
    "sign-in",
    "pin",
];

/// Two words that only count together, with whitespace between them.
const OTP_TWO_WORDS: &[(&str, &str)] = &[("security", "code")];

/// How close a 4-8 digit code must be to one of the words above.
const OTP_WINDOW: usize = 80;

/// A card number, written with or without spaces or dashes. The digits alone
/// are checked by the Luhn check digit. A run whose separators MIX (a copied
/// date and time, "2026-10-17 192216") is not read as a card: a card's groups
/// are separated one way, not two.
fn secret_reason(text: &str) -> Option<&'static str> {
    if card_number(text) {
        return Some("secret_detected");
    }
    if labelled_secret(text) {
        return Some("secret_detected");
    }
    if bare_key(text) {
        return Some("secret_detected");
    }
    None
}

/// A line that labels a credential and then gives it a value, e.g.
/// `password: hunter2`, `API_KEY=abc123`. This is the shape a log scrubber
/// catches; the desktop has no such scrubber, so here it is, deliberately
/// short and documented rather than clever.
fn labelled_secret(text: &str) -> bool {
    const LABELS: &[&str] = &[
        "password",
        "passwd",
        "passphrase",
        "api key",
        "api_key",
        "apikey",
        "secret key",
        "secret_key",
        "client secret",
        "access token",
        "auth token",
        "bearer ",
        "private key",
    ];
    for line in text.lines() {
        let lower = line.to_lowercase();
        for label in LABELS {
            let Some(at) = lower.find(label) else {
                continue;
            };
            let rest = lower[at + label.len()..].trim_start();
            let value = rest
                .strip_prefix(':')
                .or_else(|| rest.strip_prefix('='))
                .unwrap_or("");
            if value.trim().chars().count() >= 4 {
                return true;
            }
        }
    }
    false
}

/// One token shaped like a known kind of secret key: an AWS access key id, a
/// GitHub token, an `sk-` API key, a Slack token, a Google API key, or a JWT.
/// Tokens are compared without surrounding punctuation; a key written inside
/// an assignment (`AWS_ACCESS_KEY_ID=AKIA...`) is found by [`key_inside`].
/// Nothing here is a classifier, and this list is exactly as long as it says.
fn bare_key(text: &str) -> bool {
    if key_inside(text, "AKIA", 16) || key_inside(text, "ASIA", 16) {
        return true;
    }
    if key_inside(text, "AIza", 35) {
        return true;
    }
    for raw in text.split_whitespace() {
        let token = raw
            .trim_matches(|c: char| c.is_ascii_punctuation() && c != '-' && c != '_' && c != '.');
        if !token.is_ascii() {
            continue;
        }
        if ["ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_"]
            .iter()
            .any(|prefix| token.starts_with(prefix))
            && token.len() >= 30
        {
            return true;
        }
        if token.starts_with("sk-") && token.len() >= 20 {
            return true;
        }
        if (token.starts_with("xoxb-") || token.starts_with("xoxp-")) && token.len() >= 20 {
            return true;
        }
        if token.starts_with("eyJ") && token.matches('.').count() == 2 && token.len() >= 40 {
            return true;
        }
    }
    false
}

/// Whether `needle` appears in `text` with `body` further upper-case ASCII
/// letters or digits after it (an AWS access key id's shape), bounded by
/// non-key characters either side. `needle` is compared case-sensitively,
/// as the real scrubber's own key shapes are.
fn key_inside(text: &str, needle: &str, body: usize) -> bool {
    let mut from = 0;
    while let Some(found) = text[from..].find(needle) {
        let at = from + found;
        let after = at + needle.len();
        let before_ok = at == 0
            || !text[..at]
                .chars()
                .next_back()
                .is_some_and(|c| c.is_ascii_alphanumeric());
        let tail = &text[after..];
        let enough = tail.len() >= body;
        let shaped = enough
            && tail[..body]
                .chars()
                .all(|c| c.is_ascii_uppercase() || c.is_ascii_digit());
        let ends_ok = enough
            && !tail[body..]
                .chars()
                .next()
                .is_some_and(|c| c.is_ascii_uppercase() || c.is_ascii_digit());
        if before_ok && shaped && ends_ok {
            return true;
        }
        from = at + needle.len();
    }
    false
}

/// The Luhn check digit: 13 to 19 digits with a correct check digit.
fn luhn_ok(digits: &str) -> bool {
    if digits.is_empty() || !digits.chars().all(|c| c.is_ascii_digit()) {
        return false;
    }
    if !(13..=19).contains(&digits.len()) {
        return false;
    }
    let mut total = 0u32;
    for (index, ch) in digits.chars().rev().enumerate() {
        let mut value = ch.to_digit(10).unwrap_or(0);
        if index % 2 == 1 {
            value *= 2;
            if value > 9 {
                value -= 9;
            }
        }
        total += value;
    }
    total.is_multiple_of(10)
}

/// Whether the text holds a card number that passes the check digit.
fn card_number(text: &str) -> bool {
    let chars: Vec<char> = text.chars().collect();
    let mut index = 0;
    while index < chars.len() {
        let starts_here = chars[index].is_ascii_digit()
            && (index == 0 || !(chars[index - 1].is_ascii_digit() || chars[index - 1] == '-'));
        if !starts_here {
            index += 1;
            continue;
        }
        // (digit [space|-]?) ... digit, the shape the Python regex describes.
        let mut digits = String::new();
        let mut separators: Vec<char> = Vec::new();
        let mut cursor = index;
        while cursor < chars.len() {
            if !chars[cursor].is_ascii_digit() {
                break;
            }
            digits.push(chars[cursor]);
            cursor += 1;
            if cursor + 1 < chars.len()
                && (chars[cursor] == ' ' || chars[cursor] == '-')
                && chars[cursor + 1].is_ascii_digit()
            {
                separators.push(chars[cursor]);
                cursor += 1;
            }
        }
        let ends_clean =
            cursor >= chars.len() || !(chars[cursor].is_ascii_digit() || chars[cursor] == '-');
        let one_kind = separators
            .first()
            .is_none_or(|first| separators.iter().all(|s| s == first));
        if ends_clean && one_kind && luhn_ok(&digits) {
            return true;
        }
        index = cursor.max(index + 1);
    }
    false
}

/// Word characters, in the sense the Python patterns' `\b` uses. Close enough
/// to Unicode's `\w` for window titles and copied text: letters, digits and
/// the underscore; a hyphen is a boundary, which is what makes "sign-in" one
/// word in the Python pattern and "sign in" two.
fn word_char(c: char) -> bool {
    c.is_alphanumeric() || c == '_'
}

/// Every maximal run of ASCII digits: `(start, end)` in char indices.
fn digit_runs(chars: &[char]) -> Vec<(usize, usize)> {
    let mut runs = Vec::new();
    let mut at = 0;
    while at < chars.len() {
        if chars[at].is_ascii_digit() {
            let start = at;
            while at < chars.len() && chars[at].is_ascii_digit() {
                at += 1;
            }
            runs.push((start, at));
        } else {
            at += 1;
        }
    }
    runs
}

/// The text's characters, each lower-cased, for the case-insensitive word
/// searches. One character per character (a rare expanding lower-case such as
/// 'İ' is approximated by its first character), so positions in this list are
/// positions in the original text too.
fn lower_chars(text: &str) -> Vec<char> {
    text.chars()
        .map(|c| c.to_lowercase().next().unwrap_or(c))
        .collect()
}

/// Whether `phrase` appears in `chars` starting at `at`, with a word boundary
/// before and after it. `chars` is already lower-cased.
fn phrase_at(chars: &[char], at: usize, phrase: &str) -> bool {
    if at > 0 && word_char(chars[at - 1]) {
        return false;
    }
    let mut cursor = at;
    for want in phrase.chars() {
        let Some(have) = chars.get(cursor) else {
            return false;
        };
        if *have != want {
            return false;
        }
        cursor += 1;
    }
    cursor >= chars.len() || !word_char(chars[cursor])
}

/// Every place `phrase` appears with word boundaries around it.
fn phrase_starts(chars: &[char], phrase: &str) -> Vec<usize> {
    let needle: Vec<char> = phrase.chars().collect();
    let mut starts = Vec::new();
    if needle.is_empty() || chars.len() < needle.len() {
        return starts;
    }
    for at in 0..=chars.len() - needle.len() {
        if chars[at..at + needle.len()] == needle[..] && phrase_at(chars, at, phrase) {
            starts.push(at);
        }
    }
    starts
}

/// Whether the text holds a one-time code with the wording that frames one.
fn one_time_code(text: &str) -> bool {
    let chars: Vec<char> = text.chars().collect();
    let lower = lower_chars(text);
    let runs = digit_runs(&chars);

    let code_near = |from: usize, to: usize| {
        runs.iter().any(|(start, end)| {
            let len = end - start;
            (4..=8).contains(&len) && *start < to && *end > from
        })
    };

    for word in OTP_WORDS {
        for at in phrase_starts(&lower, word) {
            let window_start = at.saturating_sub(OTP_WINDOW);
            let window_end = (at + word.chars().count() + OTP_WINDOW).min(chars.len());
            if code_near(window_start, window_end) {
                return true;
            }
        }
    }

    for (first, second) in OTP_TWO_WORDS {
        for at in phrase_starts(&lower, first) {
            let after = at + first.chars().count();
            let mut at2 = after;
            while at2 < chars.len() && chars[at2].is_whitespace() {
                at2 += 1;
            }
            // The two words must be touching, separated only by whitespace.
            if at2 == after || !phrase_at(&lower, at2, second) {
                continue;
            }
            let window_start = at.saturating_sub(OTP_WINDOW);
            let window_end = (at2 + second.chars().count() + OTP_WINDOW).min(chars.len());
            if code_near(window_start, window_end) {
                return true;
            }
        }
    }

    authenticator_code(&chars)
}

/// A "G-123456" authenticator-style code, with word boundaries either side.
fn authenticator_code(chars: &[char]) -> bool {
    let mut at = 0;
    while at + 7 < chars.len() {
        let matches = (chars[at] == 'G' || chars[at] == 'g')
            && chars[at + 1] == '-'
            && (at == 0 || !word_char(chars[at - 1]));
        if matches {
            let digits: String = chars[at + 2..at + 8].iter().collect();
            let after = at + 8;
            if digits.len() == 6
                && digits.chars().all(|c| c.is_ascii_digit())
                && (after >= chars.len() || !word_char(chars[after]))
            {
                return true;
            }
        }
        at += 1;
    }
    false
}

/// Whether the text is ONE token shaped like a generated password: "one word,
/// 12-128 characters, mixing at least three of lower case, upper case, digits
/// and symbols". A lone http(s) link mixes those classes too and is a link, not
/// a password: it is what the tracking transform is for.
fn password_like(text: &str) -> bool {
    let mut words = text.split_whitespace();
    let Some(token) = words.next() else {
        return false;
    };
    if words.next().is_some() {
        return false;
    }
    let len = token.chars().count();
    if !(12..=128).contains(&len) {
        return false;
    }
    if token.contains("://") {
        return false;
    }
    let classes = [
        token.chars().any(|c| c.is_lowercase()),
        token.chars().any(|c| c.is_uppercase()),
        token.chars().any(|c| c.is_ascii_digit()),
        token.chars().any(|c| !c.is_alphanumeric()),
    ];
    classes.iter().filter(|seen| **seen).count() >= 3
}

// ---------------------------------------------------------------------------
//   The transforms (pure functions, keeping nothing)
// ---------------------------------------------------------------------------

fn result(ok: bool, kind: &str, text: String, reason: &str) -> TransformResult {
    TransformResult {
        ok,
        kind: kind.to_string(),
        text,
        reason: reason.to_string(),
    }
}

/// One of the three deterministic transforms, or a plain refusal.
///
/// Always returns exactly `{ok, kind, text, reason}`. `reason` is "" on
/// success and a short plain-English sentence on refusal; nothing is ever
/// half-transformed. The function keeps nothing and touches no other state.
pub fn transform(text: &str, kind: &str) -> TransformResult {
    match kind {
        "markdown_table" => markdown_table(text),
        "pretty_json" => pretty_json(text),
        "strip_tracking_params" => strip_tracking(text),
        other => result(
            false,
            other,
            String::new(),
            "that is not a transform I know",
        ),
    }
}

/// One table cell: no raw pipe (it would end the cell) and no newline.
fn cell(value: &str) -> String {
    value
        .trim()
        .replace("\r\n", "\n")
        .replace('\n', " ")
        .replace('|', "\\|")
}

/// CSV or TSV -> a pipe table with a `| --- |` separator row.
fn markdown_table(text: &str) -> TransformResult {
    let first = text
        .split('\n')
        .map(|line| line.trim_end_matches('\r'))
        .find(|line| !line.trim().is_empty())
        .unwrap_or("");
    let delimiter = if first.contains('\t') { '\t' } else { ',' };
    let parsed = parse_delimited(text, delimiter);
    let rows: Vec<Vec<String>> = parsed
        .into_iter()
        .filter(|row| row.iter().any(|cell| !cell.trim().is_empty()))
        .collect();
    if rows.len() < 2 {
        return result(
            false,
            "markdown_table",
            String::new(),
            "a table needs at least 2 rows",
        );
    }
    let columns = rows[0].len();
    if columns < 2 {
        return result(
            false,
            "markdown_table",
            String::new(),
            "a table needs at least 2 columns",
        );
    }
    if rows.iter().any(|row| row.len() != columns) {
        return result(
            false,
            "markdown_table",
            String::new(),
            "every row needs the same number of columns",
        );
    }
    let mut lines: Vec<String> = Vec::with_capacity(rows.len() + 1);
    lines.push(format!(
        "| {} |",
        rows[0]
            .iter()
            .map(|value| cell(value))
            .collect::<Vec<_>>()
            .join(" | ")
    ));
    lines.push(format!(
        "| {} |",
        std::iter::repeat_n("---", columns)
            .collect::<Vec<_>>()
            .join(" | ")
    ));
    for row in &rows[1..] {
        lines.push(format!(
            "| {} |",
            row.iter()
                .map(|value| cell(value))
                .collect::<Vec<_>>()
                .join(" | ")
        ));
    }
    result(true, "markdown_table", lines.join("\n") + "\n", "")
}

/// Split delimited text into rows and cells the way the Python `csv` module
/// does for the shapes a clipboard actually holds: quoted fields with doubled
/// quotes, delimiters and newlines inside quotes, and CRLF line ends.
fn parse_delimited(text: &str, delimiter: char) -> Vec<Vec<String>> {
    let mut rows: Vec<Vec<String>> = Vec::new();
    let mut row: Vec<String> = Vec::new();
    let mut field = String::new();
    let mut quoted = false;
    let mut chars = text.chars().peekable();
    while let Some(ch) = chars.next() {
        if quoted {
            if ch == '"' {
                if chars.peek() == Some(&'"') {
                    field.push('"');
                    chars.next();
                } else {
                    quoted = false;
                }
            } else {
                field.push(ch);
            }
            continue;
        }
        if ch == '"' && field.is_empty() {
            quoted = true;
        } else if ch == delimiter {
            row.push(std::mem::take(&mut field));
        } else if ch == '\r' || ch == '\n' {
            if ch == '\r' && chars.peek() == Some(&'\n') {
                chars.next();
            }
            row.push(std::mem::take(&mut field));
            rows.push(std::mem::take(&mut row));
        } else {
            field.push(ch);
        }
    }
    if !field.is_empty() || !row.is_empty() {
        row.push(field);
        rows.push(row);
    }
    rows
}

/// Valid JSON -> the same value indented two spaces; invalid -> refusal.
///
/// It is a small parser of this module's own, not `serde_json::Value`, because
/// Python's `json` keeps an object's keys in the order they were written and
/// `serde_json`'s default map sorts them - so a pretty-printed clipboard blob
/// would come back with its keys shuffled, which is a visible difference from
/// the module this one mirrors, not a formatting detail. Keeping the original
/// integer lexeme also keeps Python's arbitrary-precision integers exact.
///
/// The remaining known differences from Python's `json.dumps(indent=2,
/// ensure_ascii=False)` are deliberate and narrow: a lone-surrogate `\ud800`
/// escape is refused rather than carried (a Rust `String` cannot hold one),
/// and nesting is capped at [`JSON_MAX_DEPTH`] instead of Python's recursion
/// limit. Both are refusals of text no ordinary clipboard holds.
fn pretty_json(text: &str) -> TransformResult {
    match parse_json(text) {
        Some(value) => result(true, "pretty_json", pretty_json_value(&value), ""),
        None => result(
            false,
            "pretty_json",
            String::new(),
            "that is not valid JSON",
        ),
    }
}

/// How deep a clipboard blob may nest before the transform refuses it.
///
/// Python's decoder is bounded by its own recursion limit (about 1000); this
/// is the same idea, kept comfortably below what a stack here can take - a
/// copied JSON document is a handful of levels, and a crafted one must not be
/// able to overflow the thread that drew the bar.
const JSON_MAX_DEPTH: usize = 128;

/// One parsed JSON value, keeping an object's key order and an integer's own
/// digits (see [`pretty_json`] for why).
enum Json {
    Null,
    Bool(bool),
    /// The digits exactly as written, minus a `-0` normalised to `0` (Python's
    /// `json` turns `-0` into the integer 0 and prints it that way).
    Int(String),
    Float(f64),
    Str(String),
    Arr(Vec<Json>),
    Obj(Vec<(String, Json)>),
}

fn parse_json(text: &str) -> Option<Json> {
    let mut parser = JsonParser {
        chars: text.chars().peekable(),
        depth: 0,
    };
    parser.whitespace();
    let value = parser.value()?;
    parser.whitespace();
    if parser.chars.next().is_some() {
        return None;
    }
    Some(value)
}

struct JsonParser<'a> {
    chars: std::iter::Peekable<std::str::Chars<'a>>,
    depth: usize,
}

impl JsonParser<'_> {
    fn whitespace(&mut self) {
        while self
            .chars
            .peek()
            .is_some_and(|c| matches!(c, ' ' | '\t' | '\n' | '\r'))
        {
            self.chars.next();
        }
    }

    fn eat(&mut self, want: char) -> bool {
        if self.chars.peek() == Some(&want) {
            self.chars.next();
            true
        } else {
            false
        }
    }

    fn value(&mut self) -> Option<Json> {
        self.whitespace();
        match self.chars.peek().copied()? {
            '{' => self.object(),
            '[' => self.array(),
            '"' => self.string().map(Json::Str),
            't' => self.literal("true", Json::Bool(true)),
            'f' => self.literal("false", Json::Bool(false)),
            'n' => self.literal("null", Json::Null),
            // Python's json accepts these three by default, and refuses
            // anything else with an error; so does this.
            'N' => self.literal("NaN", Json::Float(f64::NAN)),
            'I' => self.literal("Infinity", Json::Float(f64::INFINITY)),
            '-' if self.starts_with("-Infinity") => {
                self.literal("-Infinity", Json::Float(f64::NEG_INFINITY))
            }
            '-' | '0'..='9' => self.number(),
            _ => None,
        }
    }

    fn starts_with(&self, text: &str) -> bool {
        let mut rest = self.chars.clone();
        for want in text.chars() {
            if rest.next() != Some(want) {
                return false;
            }
        }
        true
    }

    fn literal(&mut self, word: &str, value: Json) -> Option<Json> {
        if !self.starts_with(word) {
            return None;
        }
        for _ in word.chars() {
            self.chars.next();
        }
        Some(value)
    }

    fn enter(&mut self) -> Option<()> {
        self.depth += 1;
        if self.depth > JSON_MAX_DEPTH {
            return None;
        }
        Some(())
    }

    fn object(&mut self) -> Option<Json> {
        self.enter()?;
        if !self.eat('{') {
            return None;
        }
        let mut entries: Vec<(String, Json)> = Vec::new();
        self.whitespace();
        if !self.eat('}') {
            loop {
                self.whitespace();
                let key = self.string()?;
                self.whitespace();
                if !self.eat(':') {
                    return None;
                }
                let value = self.value()?;
                // A repeated key is the LAST value, in the place the key was
                // first written - exactly what Python's dict does.
                match entries.iter_mut().find(|(name, _)| *name == key) {
                    Some(entry) => entry.1 = value,
                    None => entries.push((key, value)),
                }
                self.whitespace();
                if self.eat('}') {
                    break;
                }
                if !self.eat(',') {
                    return None;
                }
            }
        }
        self.depth -= 1;
        Some(Json::Obj(entries))
    }

    fn array(&mut self) -> Option<Json> {
        self.enter()?;
        if !self.eat('[') {
            return None;
        }
        let mut items = Vec::new();
        self.whitespace();
        if !self.eat(']') {
            loop {
                items.push(self.value()?);
                self.whitespace();
                if self.eat(']') {
                    break;
                }
                if !self.eat(',') {
                    return None;
                }
            }
        }
        self.depth -= 1;
        Some(Json::Arr(items))
    }

    fn string(&mut self) -> Option<String> {
        if !self.eat('"') {
            return None;
        }
        let mut out = String::new();
        loop {
            match self.chars.next()? {
                '"' => return Some(out),
                '\\' => match self.chars.next()? {
                    '"' => out.push('"'),
                    '\\' => out.push('\\'),
                    '/' => out.push('/'),
                    'b' => out.push('\u{8}'),
                    'f' => out.push('\u{c}'),
                    'n' => out.push('\n'),
                    'r' => out.push('\r'),
                    't' => out.push('\t'),
                    'u' => out.push(self.unicode_escape()?),
                    _ => return None,
                },
                // An unescaped control character is invalid JSON (Python's
                // decoder is strict about this by default too).
                c if (c as u32) < 0x20 => return None,
                c => out.push(c),
            }
        }
    }

    fn unicode_escape(&mut self) -> Option<char> {
        let high = self.hex4()?;
        if (0xD800..0xDC00).contains(&high) {
            // A surrogate pair: the second half must follow immediately.
            if !self.eat('\\') || !self.eat('u') {
                return None;
            }
            let low = self.hex4()?;
            if !(0xDC00..0xE000).contains(&low) {
                return None;
            }
            let code = 0x10000 + ((high - 0xD800) << 10) + (low - 0xDC00);
            char::from_u32(code)
        } else if (0xDC00..0xE000).contains(&high) {
            // A lone low surrogate: JSON's text can hold one, Rust's cannot.
            None
        } else {
            char::from_u32(high)
        }
    }

    fn hex4(&mut self) -> Option<u32> {
        let mut value = 0u32;
        for _ in 0..4 {
            let digit = self.chars.next()?.to_digit(16)?;
            value = value * 16 + digit;
        }
        Some(value)
    }

    fn number(&mut self) -> Option<Json> {
        let mut lexeme = String::new();
        if self.eat('-') {
            lexeme.push('-');
        }
        // Integer part: `0` alone, or a non-zero digit then any digits.
        match self.chars.peek().copied()? {
            '0' => {
                lexeme.push('0');
                self.chars.next();
            }
            '1'..='9' => {
                while let Some(c) = self.chars.peek().copied().filter(char::is_ascii_digit) {
                    lexeme.push(c);
                    self.chars.next();
                }
            }
            _ => return None,
        }
        let mut float = false;
        if self.eat('.') {
            float = true;
            lexeme.push('.');
            let mut digits = 0;
            while let Some(c) = self.chars.peek().copied().filter(char::is_ascii_digit) {
                lexeme.push(c);
                self.chars.next();
                digits += 1;
            }
            if digits == 0 {
                return None;
            }
        }
        if self.chars.peek().is_some_and(|c| *c == 'e' || *c == 'E') {
            float = true;
            let mark = self.chars.next()?;
            lexeme.push(mark);
            if let Some(sign) = self
                .chars
                .peek()
                .copied()
                .filter(|c| *c == '+' || *c == '-')
            {
                lexeme.push(sign);
                self.chars.next();
            }
            let mut digits = 0;
            while let Some(c) = self.chars.peek().copied().filter(|c| c.is_ascii_digit()) {
                lexeme.push(c);
                self.chars.next();
                digits += 1;
            }
            if digits == 0 {
                return None;
            }
        }
        if !float {
            return Some(Json::Int(if lexeme == "-0" { "0".into() } else { lexeme }));
        }
        let parsed: f64 = lexeme.parse().ok()?;
        Some(Json::Float(parsed))
    }
}

/// The value, indented two spaces, the way Python's `json.dumps(indent=2,
/// ensure_ascii=False)` writes it.
fn pretty_json_value(value: &Json) -> String {
    let mut out = String::new();
    write_json(&mut out, value, 0);
    out
}

fn write_json(out: &mut String, value: &Json, indent: usize) {
    match value {
        Json::Null => out.push_str("null"),
        Json::Bool(true) => out.push_str("true"),
        Json::Bool(false) => out.push_str("false"),
        Json::Int(digits) => out.push_str(digits),
        Json::Float(number) => out.push_str(&python_float_repr(*number)),
        Json::Str(text) => write_json_string(out, text),
        Json::Arr(items) => {
            if items.is_empty() {
                out.push_str("[]");
                return;
            }
            out.push_str("[\n");
            for (index, item) in items.iter().enumerate() {
                if index > 0 {
                    out.push_str(",\n");
                }
                write_indent(out, indent + 1);
                write_json(out, item, indent + 1);
            }
            out.push('\n');
            write_indent(out, indent);
            out.push(']');
        }
        Json::Obj(entries) => {
            if entries.is_empty() {
                out.push_str("{}");
                return;
            }
            out.push_str("{\n");
            for (index, (key, item)) in entries.iter().enumerate() {
                if index > 0 {
                    out.push_str(",\n");
                }
                write_indent(out, indent + 1);
                write_json_string(out, key);
                out.push_str(": ");
                write_json(out, item, indent + 1);
            }
            out.push('\n');
            write_indent(out, indent);
            out.push('}');
        }
    }
}

fn write_indent(out: &mut String, indent: usize) {
    for _ in 0..indent {
        out.push_str("  ");
    }
}

/// One JSON string, quotes included: `"`, `\` and control characters escaped,
/// non-ASCII left as text (`ensure_ascii=False`).
fn write_json_string(out: &mut String, text: &str) {
    out.push('"');
    for c in text.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\u{8}' => out.push_str("\\b"),
            '\u{c}' => out.push_str("\\f"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
}

/// One float, in Python `repr`'s shape: always a decimal point (or NaN /
/// Infinity), scientific notation only outside `1e-4 .. 1e16`, and an exponent
/// with its sign and at least two digits - so `1.0` is "1.0" and `1e-5` is
/// "1e-05", not "1" and "0.00001".
fn python_float_repr(number: f64) -> String {
    if number.is_nan() {
        return "NaN".to_string();
    }
    if number.is_infinite() {
        return if number > 0.0 {
            "Infinity"
        } else {
            "-Infinity"
        }
        .to_string();
    }
    let scientific = format!("{number:e}");
    let (mantissa, exponent_text) = scientific.split_once('e').unwrap_or((&scientific, "0"));
    let exponent: i32 = exponent_text.parse().unwrap_or(0);
    if (-4..16).contains(&exponent) {
        let mut plain = format!("{number}");
        if !plain.contains('.') && !plain.contains('e') {
            plain.push_str(".0");
        }
        return plain;
    }
    format!(
        "{}e{}{:02}",
        mantissa,
        if exponent < 0 { '-' } else { '+' },
        exponent.abs()
    )
}

/// Whether one query parameter name is a click identifier.
fn is_tracking(name: &str) -> bool {
    let lowered = name.to_lowercase();
    lowered.starts_with("utm_") || TRACKING_PARAMS.contains(&lowered.as_str())
}

/// Percent-decode one query component, `+` as a space, invalid UTF-8 replaced
/// - the same leniency `urllib.parse.unquote` has.
fn decode_component(raw: &str) -> String {
    let bytes = raw.as_bytes();
    let mut out: Vec<u8> = Vec::with_capacity(bytes.len());
    let mut at = 0;
    while at < bytes.len() {
        match bytes[at] {
            b'+' => {
                out.push(b' ');
                at += 1;
            }
            b'%' if at + 2 < bytes.len() => {
                let hex = std::str::from_utf8(&bytes[at + 1..at + 3]).ok();
                match hex.and_then(|h| u8::from_str_radix(h, 16).ok()) {
                    Some(byte) => {
                        out.push(byte);
                        at += 3;
                    }
                    None => {
                        out.push(b'%');
                        at += 1;
                    }
                }
            }
            byte => {
                out.push(byte);
                at += 1;
            }
        }
    }
    String::from_utf8_lossy(&out).into_owned()
}

/// Percent-encode one query component the way `urllib.parse.urlencode` does:
/// letters, digits and `_.-~` kept, a space as `+`, everything else `%XX`.
fn encode_component(raw: &str) -> String {
    let mut out = String::with_capacity(raw.len());
    for byte in raw.bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'_' | b'.' | b'-' | b'~' => {
                out.push(byte as char);
            }
            b' ' => out.push('+'),
            other => out.push_str(&format!("%{other:02X}")),
        }
    }
    out
}

/// One URL with its tracking parameters removed and nothing else moved.
fn clean_url(raw: &str) -> String {
    let mut tail = String::new();
    let mut body = raw;
    while let Some(last) = body.chars().last() {
        if ".,;:!?".contains(last) {
            tail.insert(0, last);
            body = &body[..body.len() - last.len_utf8()];
        } else {
            break;
        }
    }
    let Some((scheme, rest)) = body.split_once("://") else {
        return raw.to_string();
    };
    // What `urlsplit` calls netloc, path, query and fragment.
    let netloc_end = rest.find(['/', '?', '#']).unwrap_or(rest.len());
    let netloc = &rest[..netloc_end];
    let after = &rest[netloc_end..];
    let (path, query_and_fragment) = match after.find(['?', '#']) {
        Some(at) => (&after[..at], &after[at..]),
        None => (after, ""),
    };
    let (query, fragment) = match query_and_fragment.strip_prefix('?') {
        Some(rest) => match rest.find('#') {
            Some(at) => (&rest[..at], &rest[at..]),
            None => (rest, ""),
        },
        None => ("", query_and_fragment),
    };
    // `urlsplit` treats a trailing bare "#" as no fragment at all, and
    // `urlunsplit` therefore drops it. So does this.
    let fragment = if fragment == "#" { "" } else { fragment };
    let mut kept: Vec<(String, String)> = Vec::new();
    for piece in query.split('&') {
        if piece.is_empty() {
            continue;
        }
        let (name, value) = match piece.split_once('=') {
            Some((name, value)) => (decode_component(name), decode_component(value)),
            None => (decode_component(piece), String::new()),
        };
        if !is_tracking(&name) {
            kept.push((name, value));
        }
    }
    let rebuilt_query = kept
        .iter()
        .map(|(name, value)| format!("{}={}", encode_component(name), encode_component(value)))
        .collect::<Vec<_>>()
        .join("&");
    let mut out = format!("{}://{}{}", scheme.to_lowercase(), netloc, path);
    if !rebuilt_query.is_empty() {
        out.push('?');
        out.push_str(&rebuilt_query);
    }
    out.push_str(fragment);
    out.push_str(&tail);
    out
}

/// Every http(s) URL's tracking parameters gone; all other text untouched.
fn strip_tracking(text: &str) -> TransformResult {
    let mut out = String::with_capacity(text.len());
    let mut at = 0;
    while at < text.len() {
        let rest = &text[at..];
        let lowered = rest.to_ascii_lowercase();
        let found = lowered.find("http://").or_else(|| lowered.find("https://"));
        let Some(found) = found else {
            out.push_str(rest);
            break;
        };
        // The Python pattern starts at a word boundary: `xhttps://` is not a
        // link, a bracket or the start of the text is.
        let before_ok = text[..at + found]
            .chars()
            .next_back()
            .is_none_or(|c| !word_char(c));
        if !before_ok {
            out.push_str(&text[at..at + found + 1]);
            at += found + 1;
            continue;
        }
        out.push_str(&rest[..found]);
        let url_start = at + found;
        let mut url_end = url_start;
        for ch in text[url_start..].chars() {
            if ch.is_whitespace() || matches!(ch, '<' | '>' | '"' | '\'') {
                break;
            }
            url_end += ch.len_utf8();
        }
        out.push_str(&clean_url(&text[url_start..url_end]));
        at = url_end;
    }
    result(true, "strip_tracking_params", out, "")
}

// ---------------------------------------------------------------------------
//   The live state: one ring, one switch, one clipboard sequence
// ---------------------------------------------------------------------------

/// The ring and the last clipboard sequence number the watcher acted on.
pub struct TimeMachineState {
    ring: Mutex<Ring>,
    last_sequence: AtomicU32,
}

impl Default for TimeMachineState {
    fn default() -> Self {
        Self {
            ring: Mutex::new(Ring::new()),
            // 0 means "nothing seen yet": the watcher and `enable()` replace
            // it with the clipboard's own number before the next read, so
            // whatever was already on the clipboard is never captured.
            last_sequence: AtomicU32::new(0),
        }
    }
}

fn guard(state: &TimeMachineState) -> MutexGuard<'_, Ring> {
    state
        .ring
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

fn with_ring<T>(app: &AppHandle, act: impl FnOnce(&mut Ring) -> T) -> T {
    let state = app.state::<TimeMachineState>();
    let mut ring = guard(&state);
    act(&mut ring)
}

/// App lock, or Windows' own lock screen. Asks nothing; both answers are
/// the existing app's own tests (`lock::app_locked`, `live::windows_locked`),
/// so this feature cannot disagree with the rest of the app about "locked".
fn machine_is_locked(app: &AppHandle) -> bool {
    if crate::lock::app_locked(app) {
        return true;
    }
    matches!(crate::live::windows_locked(), Some(true))
}

fn view(app: &AppHandle) -> StateView {
    let locked = machine_is_locked(app);
    let (enabled, items, max_items, max_item_chars) = with_ring(app, |ring| {
        if locked {
            ring.lock();
        }
        (
            ring.enabled(),
            ring.items(),
            ring.max_items,
            ring.max_item_chars,
        )
    });
    StateView {
        enabled,
        locked,
        items,
        max_items,
        max_item_chars,
    }
}

/// Reads the clipboard's text, or nothing when it holds something else.
fn read_clipboard_text(app: &AppHandle) -> Option<String> {
    use tauri_plugin_clipboard_manager::ClipboardExt;
    app.clipboard().read_text().ok()
}

/// The window in front: its program's file name and its title. Empty when
/// Windows will not tell us (a normal outcome, e.g. for a protected window):
/// an empty pair is not excluded, which is exactly the Python ring's rule.
#[cfg(windows)]
fn foreground_window() -> (String, String) {
    use windows_sys::Win32::Foundation::CloseHandle;
    use windows_sys::Win32::System::Threading::{
        OpenProcess, QueryFullProcessImageNameW, PROCESS_QUERY_LIMITED_INFORMATION,
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        GetForegroundWindow, GetWindowTextW, GetWindowThreadProcessId,
    };

    // SAFETY: every pointer is to a stack buffer sized beside it; the process
    // handle this opens is closed once, on every path. No pointer outlives the
    // call that fills it.
    unsafe {
        let window = GetForegroundWindow();
        if window.is_null() {
            return (String::new(), String::new());
        }
        let mut title = [0u16; 512];
        let title_len = GetWindowTextW(window, title.as_mut_ptr(), title.len() as i32);
        let title = if title_len > 0 {
            String::from_utf16_lossy(&title[..title_len as usize])
        } else {
            String::new()
        };
        let mut process_id = 0u32;
        GetWindowThreadProcessId(window, &mut process_id);
        if process_id == 0 {
            return (String::new(), title);
        }
        let handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, process_id);
        if handle.is_null() {
            return (String::new(), title);
        }
        let mut path = [0u16; 1024];
        let mut size = path.len() as u32;
        let ok = QueryFullProcessImageNameW(handle, 0, path.as_mut_ptr(), &mut size);
        CloseHandle(handle);
        if ok == 0 {
            return (String::new(), title);
        }
        let full = String::from_utf16_lossy(&path[..size as usize]);
        let app = full.rsplit(['\\', '/']).next().unwrap_or("").to_string();
        (app, title)
    }
}

#[cfg(not(windows))]
fn foreground_window() -> (String, String) {
    (String::new(), String::new())
}

/// The clipboard's sequence number: changes every time its contents change,
/// and cheap to read - it does not open the clipboard.
#[cfg(windows)]
fn clipboard_sequence() -> u32 {
    // SAFETY: a plain Win32 call with no arguments and no pointers.
    unsafe { windows_sys::Win32::System::DataExchange::GetClipboardSequenceNumber() }
}

#[cfg(not(windows))]
fn clipboard_sequence() -> u32 {
    0
}

/// The clipboard changed: offer its text to the ring, with the window it came
/// from. Returns whether the owner now has one more kept copy (for the drawer).
fn capture_once(app: &AppHandle) -> bool {
    let Some(text) = read_clipboard_text(app) else {
        return false;
    };
    let (foreground_app, foreground_title) = foreground_window();
    with_ring(app, |ring| {
        ring.offer(&text, &foreground_app, &foreground_title).kept
    })
}

/// Starts the one watcher: capture, and the lock wipe. Called once from setup.
///
/// It runs whether the switch is off or on, because the lock half must work
/// before the owner has ever turned capture on (a switch-off ring is already
/// empty, and `Ring::lock` is then just "off"). While the switch is off it
/// reads no clipboard text, only the sequence number and the lock state.
pub fn spawn_watch(app: AppHandle) {
    tauri::async_runtime::spawn(async move {
        // Whatever is already on the clipboard when Jarvis starts is not
        // something the owner copied after turning the feature on.
        {
            let state = app.state::<TimeMachineState>();
            state
                .last_sequence
                .store(clipboard_sequence(), Ordering::SeqCst);
        }
        let mut lock_announced = false;
        loop {
            tokio::time::sleep(WATCH_EVERY).await;
            if machine_is_locked(&app) {
                let was_on = with_ring(&app, |ring| {
                    let was_on = ring.enabled() || !ring.items().is_empty();
                    ring.lock();
                    was_on
                });
                if was_on || !lock_announced {
                    // No text, ever, in an event: the payload is unit and the
                    // drawer re-reads the (now empty) ring through a command.
                    crate::emit_quickbar(&app, crate::events::CLIPBOARD_TM_CHANGED, ());
                }
                lock_announced = true;
                continue;
            }
            lock_announced = false;

            let enabled = with_ring(&app, |ring| ring.enabled());
            if !enabled {
                continue;
            }
            let sequence = clipboard_sequence();
            if sequence == 0 {
                continue; // Windows would not tell us; do not guess
            }
            {
                let state = app.state::<TimeMachineState>();
                if state.last_sequence.swap(sequence, Ordering::SeqCst) == sequence {
                    continue;
                }
            }
            if capture_once(&app) {
                crate::emit_quickbar(&app, crate::events::CLIPBOARD_TM_CHANGED, ());
            }
        }
    });
}

/// The hotkey's whole job: open the drawer at the Jarvis bar.
///
/// Through the app lock like every other way in (`windows::show_quickbar`
/// asks Windows Hello first when it would ask). While the machine is locked
/// nothing is shown and the ring is wiped; the drawer's own commands re-check
/// the lock as well, so a page that kept running cannot read a copy either.
pub fn open_from_hotkey(app: &AppHandle) {
    if machine_is_locked(app) {
        with_ring(app, |ring| ring.lock());
        return;
    }
    if let Err(err) = crate::windows::show_quickbar(app) {
        eprintln!("[jarvis] clipboard history: the bar would not open: {err}");
        return;
    }
    // `show_quickbar` returns Ok when App lock answered "ask first", without
    // showing anything. Opening the drawer into a window the owner cannot see
    // would only leave private words lying in a hidden page, so it waits for
    // the next press, after unlocking.
    if !crate::windows::is_quickbar_visible(app) {
        return;
    }
    crate::emit_quickbar(app, crate::events::CLIPBOARD_TM_OPEN, ());
}

// ---------------------------------------------------------------------------
//   The command surface (the drawer's whole IPC, and only the quickbar's)
// ---------------------------------------------------------------------------

/// The drawer's read: the switch, the copies newest first, and the bounds.
///
/// Fails closed: while App lock (or the Windows lock screen) is up, the ring
/// is wiped before the answer is built, so a page that kept running while the
/// owner was away cannot read a copied word.
#[tauri::command]
pub fn clipboard_tm_state(app: AppHandle) -> StateView {
    view(&app)
}

/// Turns capture ON. The owner's explicit press is the permission: the feature
/// ships off, this command is the drawer's own switch, and nothing is kept
/// from before this moment (`last_sequence` is re-read, so what was already on
/// the clipboard is not captured).
#[tauri::command]
pub fn clipboard_tm_enable(app: AppHandle) -> Result<StateView, String> {
    if machine_is_locked(&app) {
        return Err(LOCKED_WORDS.to_string());
    }
    let state = app.state::<TimeMachineState>();
    state
        .last_sequence
        .store(clipboard_sequence(), Ordering::SeqCst);
    with_ring(&app, |ring| ring.enable());
    Ok(view(&app))
}

/// Turns capture OFF. The kept copies stay until cleared or locked.
#[tauri::command]
pub fn clipboard_tm_disable(app: AppHandle) -> StateView {
    with_ring(&app, |ring| ring.disable());
    view(&app)
}

/// Wipes the kept copies, leaving the switch as it was.
#[tauri::command]
pub fn clipboard_tm_clear(app: AppHandle) -> StateView {
    with_ring(&app, |ring| ring.clear());
    view(&app)
}

/// Wipes the kept copies AND turns capture off - the lock's own action,
/// offered as a button so the owner can do at once what a lock would do.
/// Allowed while locked: it only forgets.
#[tauri::command]
pub fn clipboard_tm_lock(app: AppHandle) -> StateView {
    with_ring(&app, |ring| ring.lock());
    view(&app)
}

/// Transforms one kept copy. `index` is its place in `clipboard_tm_state`'s
/// list (0 is the newest). Reading a copy is refused while App lock is up.
#[tauri::command]
pub fn clipboard_tm_transform(
    app: AppHandle,
    index: usize,
    kind: String,
) -> Result<TransformResult, String> {
    if machine_is_locked(&app) {
        return Err(LOCKED_WORDS.to_string());
    }
    let text = with_ring(&app, |ring| {
        ring.items().into_iter().nth(index).map(|item| item.text)
    })
    .ok_or_else(|| "that copy is no longer in the list".to_string())?;
    Ok(transform(&text, &kind))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A ring that is on, for the tests that are not about the switch.
    fn on() -> Ring {
        let mut ring = Ring::new();
        ring.enable();
        ring
    }

    #[test]
    fn a_new_ring_is_off_and_keeps_nothing() {
        let mut ring = Ring::new();
        let answer = ring.offer("something copied", "Code", "notes.py");
        assert_eq!(
            answer,
            Offer {
                kept: false,
                reason: "disabled".to_string()
            }
        );
        assert!(ring.items().is_empty());
    }

    #[test]
    fn newest_first_and_a_second_copy_moves_to_the_top() {
        let mut ring = on();
        assert!(ring.offer("first", "", "").kept);
        assert!(ring.offer("second", "", "").kept);
        let texts: Vec<String> = ring.items().into_iter().map(|item| item.text).collect();
        assert_eq!(texts, vec!["second", "first"]);
        // The same words again are not stored twice; the one entry moves up.
        assert!(ring.offer("first", "", "").kept);
        let texts: Vec<String> = ring.items().into_iter().map(|item| item.text).collect();
        assert_eq!(texts, vec!["first", "second"]);
    }

    #[test]
    fn the_ring_is_capped_and_drops_the_oldest() {
        let mut ring = Ring::with_limits(3, DEFAULT_MAX_ITEM_CHARS, &[]);
        ring.enable();
        for text in ["a", "b", "c", "d"] {
            assert!(ring.offer(text, "", "").kept);
        }
        let texts: Vec<String> = ring.items().into_iter().map(|item| item.text).collect();
        assert_eq!(texts, vec!["d", "c", "b"]);
    }

    #[test]
    fn a_copy_that_was_already_kept_can_still_be_read_back() {
        // The drawer draws copies; returning the ring itself would let a
        // caller edit it.
        let mut ring = on();
        ring.offer("kept words", "Code", "notes.py");
        let mut items = ring.items();
        items[0].text = "changed".to_string();
        assert_eq!(ring.items()[0].text, "kept words");
        assert_eq!(ring.items()[0].app, "Code");
        assert_eq!(ring.items()[0].title, "notes.py");
    }

    #[test]
    fn empty_and_whitespace_only_copies_are_refused() {
        let mut ring = on();
        for text in ["", "   ", "\n\t "] {
            assert_eq!(ring.offer(text, "", "").reason, "empty");
        }
        assert!(ring.items().is_empty());
    }

    #[test]
    fn a_copy_over_the_size_limit_is_refused_and_the_ring_is_untouched() {
        let mut ring = Ring::with_limits(DEFAULT_MAX_ITEMS, 10, &[]);
        ring.enable();
        assert!(ring.offer("short", "", "").kept);
        let answer = ring.offer("this is longer than ten", "", "");
        assert_eq!(
            answer,
            Offer {
                kept: false,
                reason: "too_large".to_string()
            }
        );
        assert_eq!(ring.items().len(), 1);
        // Exactly the limit is kept (the Python module refuses only LONGER).
        assert!(ring.offer("0123456789", "", "").kept);
    }

    #[test]
    fn a_password_manager_window_is_refused_by_title_or_process_name() {
        let mut ring = on();
        for (app, title) in [
            ("Bitwarden.exe", "Jarvis"),
            ("chrome.exe", "Sign in - Bitwarden"),
            ("1Password.exe", ""),
            ("Keeper", "Windows Security"),
            ("unknown.exe", "Credential Manager"),
        ] {
            let answer = ring.offer("the words", app, title);
            assert_eq!(answer.reason, "excluded_app", "app={app} title={title}");
        }
        assert!(ring.items().is_empty());
        // An ordinary editor is not excluded.
        assert!(ring.offer("the words", "Code.exe", "notes.py").kept);
    }

    #[test]
    fn a_window_title_with_no_name_in_it_is_still_captured() {
        let mut ring = on();
        assert!(ring.offer("the words", "", "Untitled - Notepad").kept);
    }

    #[test]
    fn a_pem_block_is_refused() {
        let mut ring = on();
        let answer = ring.offer(
            "-----BEGIN RSA PRIVATE KEY-----\nMIIEow...\n-----END RSA PRIVATE KEY-----",
            "Code.exe",
            "id_rsa",
        );
        assert_eq!(answer.reason, "secret_or_otp_detected");
        assert!(ring.items().is_empty());
        // The check is on the BEGIN marker, so a mention in prose is refused
        // too - the Python module's own rule ("-----BEGIN" in text.upper()).
        assert_eq!(
            ring.offer("a ------begin block follows", "", "").reason,
            "secret_or_otp_detected"
        );
    }

    #[test]
    fn a_one_time_code_with_its_wording_is_refused() {
        let mut ring = on();
        for text in [
            "Your verification code is 482913",
            "482913 is your code",
            "Use passcode 0412 to sign in",
            "2FA: 998123",
            "PIN 4471",
            "G-123456 is your authenticator code",
        ] {
            let answer = ring.offer(text, "", "");
            assert_eq!(
                answer.reason, "secret_or_otp_detected",
                "refused nothing for: {text}"
            );
        }
        // Wording without a code is ordinary words, not a secret.
        assert!(ring.offer("the login page loaded", "", "").kept);
        // A code with no wording near it is a number, not a one-time code.
        assert!(ring.offer("room 482913", "", "").kept);
    }

    #[test]
    fn a_lone_generated_password_is_refused() {
        let mut ring = on();
        assert_eq!(
            ring.offer("Xk9#mQ2!vL7@pR4$", "", "").reason,
            "secret_or_otp_detected"
        );
        // A link mixes the classes too and is a link, not a password.
        assert!(
            ring.offer("https://example.com/some/fairly/long/path?x=1", "", "")
                .kept
        );
        // Two words are prose, not one generated token.
        assert!(ring.offer("MixedCase word123! here", "", "").kept);
    }

    #[test]
    fn a_card_number_that_passes_the_check_digit_is_refused() {
        let mut ring = on();
        for text in [
            "4111 1111 1111 1111",
            "4111-1111-1111-1111",
            "card: 4012888888881881",
        ] {
            assert_eq!(
                ring.offer(text, "", "").reason,
                "secret_detected",
                "kept a card number: {text}"
            );
        }
        // Fails the check digit: not a card number.
        assert!(ring.offer("4111 1111 1111 1112", "", "").kept);
        // A copied date and time has MIXED separators: a card's groups are
        // separated one way, not two.
        assert!(ring.offer("2026-10-17 192216", "", "").kept);
    }

    #[test]
    fn a_labelled_credential_is_refused() {
        let mut ring = on();
        for text in [
            "password: hunter2",
            "api_key = abcdef123456",
            "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE",
            "token: ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        ] {
            assert_eq!(
                ring.offer(text, "", "").reason,
                "secret_detected",
                "kept a credential: {text}"
            );
        }
        // A line that only mentions the word is not a value.
        assert!(
            ring.offer("the password field is on that page", "", "")
                .kept
        );
    }

    #[test]
    fn clear_wipes_but_leaves_the_switch_as_it_was() {
        let mut ring = on();
        ring.offer("kept words", "", "");
        ring.clear();
        assert!(ring.items().is_empty());
        assert!(ring.enabled(), "clear must not turn capture off");
    }

    #[test]
    fn lock_wipes_and_turns_capture_off() {
        let mut ring = on();
        ring.offer("kept words", "", "");
        ring.lock();
        assert!(ring.items().is_empty());
        assert!(!ring.enabled(), "lock must stop capturing as well as wipe");
        // A lock cannot be undone by another lock; only the owner's switch on.
        ring.lock();
        assert!(!ring.enabled());
    }

    #[test]
    fn every_transform_answer_has_the_same_four_fields() {
        for kind in TRANSFORMS {
            let answer = transform("a,b\n1,2", kind);
            assert_eq!(answer.kind, *kind);
            assert!(answer.reason.is_empty() == answer.ok);
        }
        let unknown = transform("anything", "make_it_pretty");
        assert!(!unknown.ok);
        assert_eq!(unknown.reason, "that is not a transform I know");
    }

    #[test]
    fn csv_becomes_a_pipe_table() {
        let answer = transform("name,city\nAda,London\nGrace,New York", "markdown_table");
        assert!(answer.ok, "{}", answer.reason);
        assert_eq!(
            answer.text,
            "| name | city |\n| --- | --- |\n| Ada | London |\n| Grace | New York |\n"
        );
    }

    #[test]
    fn tsv_is_selected_by_a_tab_on_the_first_non_empty_line() {
        let answer = transform("\n\na\tb\n1\t2\n", "markdown_table");
        assert!(answer.ok, "{}", answer.reason);
        assert_eq!(answer.text, "| a | b |\n| --- | --- |\n| 1 | 2 |\n");
    }

    #[test]
    fn quoted_cells_keep_commas_and_escape_pipes_and_newlines() {
        let answer = transform("\"a, b\",c\n\"x|y\",\"two\nlines\"", "markdown_table");
        assert!(answer.ok, "{}", answer.reason);
        assert_eq!(
            answer.text,
            "| a, b | c |\n| --- | --- |\n| x\\|y | two lines |\n"
        );
    }

    #[test]
    fn a_table_with_too_few_rows_columns_or_ragged_rows_is_refused() {
        let one_row = transform("a,b", "markdown_table");
        assert!(!one_row.ok);
        assert_eq!(one_row.reason, "a table needs at least 2 rows");
        assert_eq!(one_row.text, "");

        let one_column = transform("a\nb", "markdown_table");
        assert!(!one_column.ok);
        assert_eq!(one_column.reason, "a table needs at least 2 columns");

        let ragged = transform("a,b\n1,2,3", "markdown_table");
        assert!(!ragged.ok);
        assert_eq!(ragged.reason, "every row needs the same number of columns");
    }

    #[test]
    fn valid_json_is_pretty_printed() {
        let answer = transform("{\"b\":2,\"a\":[1,true,null]}", "pretty_json");
        assert!(answer.ok, "{}", answer.reason);
        assert_eq!(
            answer.text,
            "{\n  \"b\": 2,\n  \"a\": [\n    1,\n    true,\n    null\n  ]\n}"
        );
        // Non-ASCII is kept as text, never escaped.
        let unicode = transform("{\"city\":\"Zürich\"}", "pretty_json");
        assert_eq!(unicode.text, "{\n  \"city\": \"Zürich\"\n}");
    }

    #[test]
    fn json_keeps_its_key_order_and_its_own_number_shapes() {
        // Python's json preserves the order the keys were written in, so this
        // must too - a sorted pretty-print is a different document.
        let answer = transform("{\"z\":1,\"a\":2,\"m\":3}", "pretty_json");
        assert_eq!(answer.text, "{\n  \"z\": 1,\n  \"a\": 2,\n  \"m\": 3\n}");
        // Python integers are arbitrary precision, and are printed exactly.
        let big = transform("{\"n\":123456789012345678901234567890}", "pretty_json");
        assert_eq!(big.text, "{\n  \"n\": 123456789012345678901234567890\n}");
        // Floats keep Python repr's shape: a decimal point, and scientific
        // notation only outside 1e-4 .. 1e16.
        assert_eq!(transform("1.0", "pretty_json").text, "1.0");
        assert_eq!(transform("1e3", "pretty_json").text, "1000.0");
        assert_eq!(transform("1e-5", "pretty_json").text, "1e-05");
        assert_eq!(transform("1e20", "pretty_json").text, "1e+20");
        assert_eq!(transform("-0.0", "pretty_json").text, "-0.0");
        // `-0` is the integer 0 in Python, and is printed that way.
        assert_eq!(transform("-0", "pretty_json").text, "0");
        // NaN/Infinity are accepted by Python's json by default; so here.
        assert_eq!(transform("NaN", "pretty_json").text, "NaN");
        assert_eq!(transform("-Infinity", "pretty_json").text, "-Infinity");
        // A repeated key is the last value, in the first key's place.
        assert_eq!(
            transform("{\"a\":1,\"b\":2,\"a\":3}", "pretty_json").text,
            "{\n  \"a\": 3,\n  \"b\": 2\n}"
        );
        // Escapes come back the way Python writes them.
        assert_eq!(
            transform("\"tab\\tquote\\\"slash\\\\\"", "pretty_json").text,
            "\"tab\\tquote\\\"slash\\\\\""
        );
        // An empty object and array stay on one line.
        assert_eq!(
            transform("{\"a\":{},\"b\":[]}", "pretty_json").text,
            "{\n  \"a\": {},\n  \"b\": []\n}"
        );
    }

    #[test]
    fn invalid_json_is_refused_never_half_printed() {
        // Nesting deeper than JSON_MAX_DEPTH is refused, not overflowed.
        let deep = format!(
            "{}{}",
            "[".repeat(JSON_MAX_DEPTH + 1),
            "]".repeat(JSON_MAX_DEPTH + 1)
        );
        for text in [
            "not json",
            "{\"a\": 1,}",
            "",
            "[1,2",
            "{\"a\" 1}",
            "01",
            "\"unterminated",
            // A lone surrogate cannot be held in a Rust String; refusing is
            // the only honest answer (see pretty_json's own note).
            "\"\\ud800\"",
            deep.as_str(),
        ] {
            let answer = transform(text, "pretty_json");
            assert!(!answer.ok, "accepted invalid JSON: {text}");
            assert_eq!(answer.reason, "that is not valid JSON");
            assert_eq!(answer.text, "");
        }
    }

    #[test]
    fn tracking_parameters_are_removed_and_the_others_kept_in_order() {
        let answer = transform(
            "See https://example.com/page?id=42&utm_source=news&page=2&fbclid=abc#top.",
            "strip_tracking_params",
        );
        assert!(answer.ok);
        assert_eq!(
            answer.text,
            "See https://example.com/page?id=42&page=2#top."
        );
    }

    #[test]
    fn every_documented_tracking_name_goes_and_utm_is_case_insensitive() {
        let answer = transform(
            "https://example.com/?gclid=1&msclkid=2&mc_eid=3&igshid=4&_hsenc=5&vero_id=6&mkt_tok=7&UTM_Campaign=8&keep=9",
            "strip_tracking_params",
        );
        assert_eq!(answer.text, "https://example.com/?keep=9");
    }

    #[test]
    fn text_that_is_not_a_url_is_returned_exactly_as_it_was() {
        let plain = "just some words, with punctuation; and a comma.";
        let answer = transform(plain, "strip_tracking_params");
        assert!(answer.ok);
        assert_eq!(answer.text, plain);
    }

    #[test]
    fn several_urls_are_each_cleaned_and_the_words_between_them_are_not() {
        let answer = transform(
            "one https://a.example/x?utm_source=1 keep two https://b.example/y?id=2&gclid=3",
            "strip_tracking_params",
        );
        assert_eq!(
            answer.text,
            "one https://a.example/x keep two https://b.example/y?id=2"
        );
    }

    #[test]
    fn a_word_touching_a_url_is_not_part_of_the_link() {
        let answer = transform(
            "xhttps://example.com/?utm_source=1",
            "strip_tracking_params",
        );
        assert_eq!(answer.text, "xhttps://example.com/?utm_source=1");
    }

    #[test]
    fn a_url_with_nothing_left_after_the_clean_drops_the_question_mark() {
        let answer = transform(
            "https://example.com/?utm_source=news",
            "strip_tracking_params",
        );
        assert_eq!(answer.text, "https://example.com/");
        // A bare host with only tracking parameters loses its "?" too.
        let bare = transform(
            "https://example.com?utm_source=news",
            "strip_tracking_params",
        );
        assert_eq!(bare.text, "https://example.com");
    }

    #[test]
    fn the_shipped_defaults_mirror_the_python_slice() {
        assert_eq!(DEFAULT_MAX_ITEMS, 25);
        assert_eq!(DEFAULT_MAX_ITEM_CHARS, 32_768);
        let python_excluded = [
            "1password",
            "bitwarden",
            "keepass",
            "keepassxc",
            "dashlane",
            "lastpass",
            "proton pass",
            "windows security",
            "credential manager",
        ];
        assert_eq!(EXCLUDED_APPS.len(), python_excluded.len());
        for (ours, theirs) in EXCLUDED_APPS.iter().zip(python_excluded.iter()) {
            assert_eq!(ours, theirs);
        }
        let python_transforms = ["markdown_table", "pretty_json", "strip_tracking_params"];
        assert_eq!(TRANSFORMS.len(), python_transforms.len());
        for (ours, theirs) in TRANSFORMS.iter().zip(python_transforms.iter()) {
            assert_eq!(ours, theirs);
        }
    }
}
