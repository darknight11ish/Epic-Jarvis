//! Best-effort scrubbing for a line before it is written to a Jarvis log file.
//!
//! ## Why this exists
//!
//! README section 8 (honest limits; bullet 15) said the quiet part out loud:
//! `backend.log` is scrubbed, but **`jarvis-desktop.log` is not**, and the
//! updater's own log is not either. `logfile.rs` relied on discipline about
//! what may be printed to it. A panic message, a child program's output, a
//! URL copied out of an error - none of those obey that discipline.
//!
//! So every desktop log line now goes through [`scrub_log_line`] at the ONE
//! append path in `logfile.rs`, and the updater script keeps the same shapes
//! out of its log (its own `Scrub-LogLine`). The pure function lives here so
//! `cargo test` can feed it real secret strings without a log directory, an
//! app handle or a running backend.
//!
//! ## What it redacts
//!
//! * a pairing/device token: `jdk1.<anything in [A-Za-z0-9._-]>`;
//! * a `name: value` / `name=value` pair whose name looks like a secret
//!   (`X-Jarvis-Token`, `Authorization`, `token`, `key`, `password`,
//!   `secret`, `sig`), keeping the NAME so the line still says what failed;
//! * `Authorization: Bearer <token>` and a bare `Bearer <long token>`;
//! * the API key shapes `sk-...`, `gh[pousr]_...` and `AIza...`;
//! * a 32-or-more-character hex/base64 blob after one of those markers.
//!
//! Ordinary prose is returned byte-for-byte unchanged. There is deliberately
//! no "looks random" rule: `jarvis_scrub.py` documents why on the backend (a
//! bug report needs something left to read), and the same restraint applies
//! here.
//!
//! ## What this is NOT
//!
//! A guarantee. A pattern list never recognises everything, and this one is
//! deliberately small: it knows the shapes the README names, not every format
//! a future caller might invent. It is also only wired where the app writes
//! its own log - the Python child writes `backend.log` directly and obeys its
//! own scrubber there. The README says both halves out loud; so does the note
//! the Settings screen shows about the files.
//!
//! No regex crate, no new dependency: this is a small byte scanner, which also
//! keeps it obvious why a line was or was not changed.

/// A pairing / device token was here.
pub const PAIR_TOKEN: &str = "[REDACTED_PAIR_TOKEN]";
/// A known API key shape was here.
pub const API_KEY: &str = "[REDACTED_API_KEY]";
/// An assigned or header secret was here (the name is kept beside it).
pub const SECRET: &str = "[REDACTED]";

/// Key names (lower case) whose value is a secret when assigned or sent as a
/// header. Longest first so `x-jarvis-token` wins over `token` at the same spot.
const SECRET_KEYS: [&str; 7] = [
    "x-jarvis-token",
    "authorization",
    "password",
    "secret",
    "token",
    "sig",
    "key",
];

/// The characters a pairing token may continue with after `jdk1.`.
fn is_pair_char(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'.' || b == b'_' || b == b'-'
}

/// The characters an `sk-` key may continue with.
fn is_sk_char(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_' || b == b'-'
}

/// The characters a hex/base64-looking value or bearer token may continue with.
fn is_blob_char(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'+' || b == b'/' || b == b'=' || b == b'_' || b == b'-'
}

/// True at the start of a word: the byte before is not part of a name.
fn boundary_before(bytes: &[u8], i: usize) -> bool {
    i == 0
        || !(bytes[i - 1].is_ascii_alphanumeric() || bytes[i - 1] == b'_' || bytes[i - 1] == b'-')
}

fn skip_spaces(bytes: &[u8], mut j: usize) -> usize {
    while j < bytes.len() && (bytes[j] == b' ' || bytes[j] == b'\t') {
        j += 1;
    }
    j
}

/// What a redaction found: where the replaced span ends and what replaces it.
struct Hit {
    end: usize,
    replacement: String,
}

impl Hit {
    fn new(end: usize, replacement: impl Into<String>) -> Self {
        Self {
            end,
            replacement: replacement.into(),
        }
    }
}

/// One log line with the secret shapes above taken out.
pub fn scrub_log_line(line: &str) -> String {
    let mut out = String::with_capacity(line.len());
    let mut i = 0usize;
    while i < line.len() {
        if !line.is_char_boundary(i) {
            i += 1;
            continue;
        }
        match redact_at(line, i) {
            Some(hit) => {
                out.push_str(&hit.replacement);
                i = hit.end;
            }
            None => {
                let Some(ch) = line[i..].chars().next() else {
                    break;
                };
                out.push(ch);
                i += ch.len_utf8();
            }
        }
    }
    out
}

/// Scrub a whole piece of text line by line, keeping its line endings.
///
/// Used by the crash/sidecar paths that copy a block of log text rather than a
/// single line; `\n` and `\r\n` are preserved exactly.
pub fn scrub_io(text: String) -> String {
    let mut out = String::with_capacity(text.len());
    let mut start = 0usize;
    for (idx, ch) in text.char_indices() {
        if ch != '\n' {
            continue;
        }
        let line = &text[start..idx];
        let cr = line.ends_with('\r');
        let body = if cr { &line[..line.len() - 1] } else { line };
        out.push_str(&scrub_log_line(body));
        if cr {
            out.push('\r');
        }
        out.push('\n');
        start = idx + 1;
    }
    if start < text.len() {
        out.push_str(&scrub_log_line(&text[start..]));
    }
    out
}

/// Try every rule at byte index `i` (always a char boundary).
fn redact_at(line: &str, i: usize) -> Option<Hit> {
    let bytes = line.as_bytes();

    // 1. A pairing / device token. `jdk1.` plus at least one token character.
    if line[i..].starts_with("jdk1.") {
        let mut j = i + "jdk1.".len();
        let start = j;
        while j < bytes.len() && is_pair_char(bytes[j]) {
            j += 1;
        }
        if j > start {
            return Some(Hit::new(j, PAIR_TOKEN));
        }
    }

    // 2. Known API-key shapes.
    if line[i..].starts_with("sk-") {
        let mut j = i + 3;
        let start = j;
        while j < bytes.len() && is_sk_char(bytes[j]) {
            j += 1;
        }
        if j - start >= 16 {
            return Some(Hit::new(j, API_KEY));
        }
    }
    if i + 4 <= bytes.len()
        && &bytes[i..i + 2] == b"gh"
        && matches!(bytes[i + 2], b'p' | b'o' | b'u' | b's' | b'r')
        && bytes[i + 3] == b'_'
    {
        let mut j = i + 4;
        let start = j;
        while j < bytes.len() && bytes[j].is_ascii_alphanumeric() {
            j += 1;
        }
        if j - start >= 20 {
            return Some(Hit::new(j, API_KEY));
        }
    }
    if line[i..].starts_with("AIza") {
        let mut j = i + 4;
        let start = j;
        while j < bytes.len()
            && (bytes[j].is_ascii_alphanumeric() || bytes[j] == b'_' || bytes[j] == b'-')
        {
            j += 1;
        }
        if j - start >= 30 {
            return Some(Hit::new(j, API_KEY));
        }
    }

    // 3. A secret assigned or sent under a name that says it is a secret.
    if boundary_before(bytes, i) {
        for key in SECRET_KEYS {
            let Some(candidate) = line.get(i..i + key.len()) else {
                continue;
            };
            if !candidate.eq_ignore_ascii_case(key) {
                continue;
            }
            if let Some(hit) = scrub_assignment(line, i, key.len()) {
                return Some(hit);
            }
        }

        // 4. A bare `Bearer <long token>`, for a header copied out of context.
        //    Sixteen characters is deliberately conservative: "Bearer of good
        //    news" is prose and must survive.
        if line
            .get(i..i + 6)
            .map(|s| s.eq_ignore_ascii_case("bearer"))
            .unwrap_or(false)
        {
            let j = i + 6;
            if j < bytes.len() && (bytes[j] == b' ' || bytes[j] == b'\t') {
                let start = skip_spaces(bytes, j);
                let mut k = start;
                while k < bytes.len() && is_blob_char(bytes[k]) {
                    k += 1;
                }
                if k - start >= 16 {
                    return Some(Hit::new(k, "Bearer [REDACTED]"));
                }
            }
        }
    }

    None
}

/// `name: value` / `name=value` / `"name": "value"` for one key at `i`.
fn scrub_assignment(line: &str, i: usize, key_len: usize) -> Option<Hit> {
    let bytes = line.as_bytes();
    let name_end = i + key_len;
    let mut j = skip_spaces(bytes, name_end);

    // A JSON-style log line quotes the key: `{"token": "..."}`.
    if j < bytes.len() && bytes[j] == b'"' {
        j += 1;
        j = skip_spaces(bytes, j);
    }
    if j >= bytes.len() || (bytes[j] != b':' && bytes[j] != b'=') {
        // No separator character (`token deadbeef...`): only a long hex/base64
        // blob is treated as a secret, so ordinary prose after "token" survives.
        let after_name = skip_spaces(bytes, name_end);
        if after_name > name_end {
            let mut k = after_name;
            while k < bytes.len() && is_blob_char(bytes[k]) {
                k += 1;
            }
            if k - after_name >= 32 {
                return Some(Hit::new(k, format!("{}={SECRET}", &line[i..name_end])));
            }
        }
        return None;
    }
    j += 1;
    j = skip_spaces(bytes, j);
    // An optional opening quote around the VALUE is consumed; the closing one
    // is left in place because it belongs to the surrounding text.
    if j < bytes.len() && bytes[j] == b'"' {
        j += 1;
    }

    // `Authorization: Bearer <token>` - the value is two words; the token is
    // the second one, so the Bearer word alone must not stop the redaction.
    if line
        .get(j..)
        .and_then(|rest| rest.get(..6))
        .map(|word| word.eq_ignore_ascii_case("bearer"))
        .unwrap_or(false)
    {
        let after = j + 6;
        if after < bytes.len() && (bytes[after] == b' ' || bytes[after] == b'\t') {
            let start = skip_spaces(bytes, after);
            let mut k = start;
            while k < bytes.len() && is_blob_char(bytes[k]) {
                k += 1;
            }
            // Any value after an explicit secret header's `Bearer` is a
            // credential, however short it is; "Bearer of..." is prose and is
            // not reached here because it has no `name:` in front of it.
            if k > start {
                return Some(Hit::new(k, format!("{}={SECRET}", &line[i..name_end])));
            }
        }
    }

    let start = j;
    let mut end = start;
    while end < bytes.len() {
        let b = bytes[end];
        if b == b' '
            || b == b'\t'
            || b == b'"'
            || b == b'\''
            || b == b'&'
            || b == b'\r'
            || b == b'\n'
        {
            break;
        }
        end += 1;
    }
    if end > start {
        return Some(Hit::new(end, format!("{}={SECRET}", &line[i..name_end])));
    }

    None
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Every one of the work order's named shapes, in one line, must be gone.
    #[test]
    fn pairing_tokens_headers_and_key_shapes_are_taken_out() {
        let line = "sync failed: jdk1.d12345678.secret_token_value \
                    X-Jarvis-Token: my-secret \
                    Authorization: Bearer abcdefghijklmnopqrstuvwxyz \
                    sk-proj-1234567890abcdefghij ghp_ABCDEFGHIJKLMNOPQRSTUVWX \
                    AIzaSyA1234567890abcdefghijklmnopqrstu";
        let out = scrub_log_line(line);
        for raw in [
            "jdk1.d12345678.secret_token_value",
            "my-secret",
            "abcdefghijklmnopqrstuvwxyz",
            "sk-proj-1234567890abcdefghij",
            "ghp_ABCDEFGHIJKLMNOPQRSTUVWX",
            "AIzaSyA1234567890abcdefghijklmnopqrstu",
        ] {
            assert!(!out.contains(raw), "raw secret survived: {raw}\n{out}");
        }
        assert!(out.contains(PAIR_TOKEN), "{out}");
        assert!(out.contains("X-Jarvis-Token=[REDACTED]"), "{out}");
        assert!(out.contains("Authorization=[REDACTED]"), "{out}");
        // The words that say WHAT failed are still there for the bug report.
        assert!(out.starts_with("sync failed: "), "{out}");
    }

    /// A 64-character hex value after `token=`.
    #[test]
    fn a_long_hex_value_after_token_is_taken_out() {
        let hex = "0123456789abcdef".repeat(4);
        let out = scrub_log_line(&format!("GET /v1/thing?token={hex}&x=1 failed"));
        assert!(!out.contains(&hex), "{out}");
        assert!(out.contains("token=[REDACTED]"), "{out}");
        assert!(
            out.contains("&x=1"),
            "the rest of the query was eaten: {out}"
        );
    }

    /// Pairing token in a URL query, the most likely real leak.
    #[test]
    fn a_pairing_token_inside_a_url_is_taken_out() {
        let out =
            scrub_log_line("open http://127.0.0.1:4719/x?pairing_token=jdk1.abc.def-123 failed");
        assert!(!out.contains("jdk1.abc.def-123"), "{out}");
        assert!(out.contains(PAIR_TOKEN), "{out}");
        assert!(
            out.contains("open http://127.0.0.1:4719/x?pairing_token="),
            "{out}"
        );
    }

    /// Ordinary prose is byte-for-byte unchanged - including words that
    /// merely contain "key", "token" or "Bearer".
    #[test]
    fn ordinary_prose_is_unchanged() {
        for line in [
            "The build took 12.5 seconds and wrote 4 files.",
            "The key to the shed is under the mat.",
            "A token of appreciation and a bearer of good news.",
            "jarvis-desktop.log rotated at 4 MiB; backend.log is 812 bytes.",
            "window 'Jarvis' opened at 1920x1080 on the RTX 2080 SUPER",
            "",
            "   leading and trailing spaces stay   ",
        ] {
            assert_eq!(scrub_log_line(line), line, "prose was changed: {line:?}");
        }
    }

    /// Lower-case and mixed-case header names are secret names too.
    #[test]
    fn header_names_are_matched_without_regard_to_case() {
        for line in [
            "x-jarvis-token: hunter2",
            "X-JARVIS-TOKEN=hunter2",
            "token: hunter2",
            "password=hunter2",
            "secret: hunter2",
            "sig=hunter2",
            "Authorization: Bearer ab",
        ] {
            let out = scrub_log_line(line);
            assert!(!out.contains("hunter2"), "not redacted: {line} -> {out}");
            assert!(out.contains("[REDACTED]"), "{line} -> {out}");
        }
    }

    /// A JSON-style line keeps its key and loses its value.
    #[test]
    fn a_quoted_json_pair_is_taken_out() {
        let out = scrub_log_line(r#"{"token": "my-secret", "retry": 2}"#);
        assert!(!out.contains("my-secret"), "{out}");
        assert!(out.contains("token=[REDACTED]"), "{out}");
        assert!(out.contains("retry"), "{out}");
    }

    /// A short word after `token` is prose, not a blob; a long blob is not.
    #[test]
    fn only_a_long_blob_after_a_bare_marker_is_redacted() {
        let prose = "the token distribution looked fine";
        assert_eq!(scrub_log_line(prose), prose);
        let blob = "token deadbeefdeadbeefdeadbeefdeadbeef";
        let out = scrub_log_line(blob);
        assert!(!out.contains("deadbeefdeadbeefdeadbeefdeadbeef"), "{out}");
    }

    /// The whole reader is idempotent: scrubbing its own output changes nothing.
    #[test]
    fn scrubbing_twice_is_the_same_as_scrubbing_once() {
        let line = "X-Jarvis-Token: my-secret jdk1.a.b sk-proj-1234567890abcdefghij";
        let once = scrub_log_line(line);
        let twice = scrub_log_line(&once);
        assert_eq!(once, twice);
    }

    /// `scrub_io` walks every line and keeps CRLF exactly.
    #[test]
    fn a_block_of_text_is_scrubbed_line_by_line_and_keeps_its_endings() {
        let text = "one: X-Jarvis-Token: aaa\r\ntwo is fine\r\nthree: token=bbb\n";
        let out = scrub_io(text.to_string());
        assert!(!out.contains("aaa"), "{out}");
        assert!(!out.contains("bbb"), "{out}");
        assert!(out.contains("one: X-Jarvis-Token=[REDACTED]\r\n"), "{out}");
        assert!(out.contains("two is fine\r\n"), "{out}");
        assert!(out.ends_with("three: token=[REDACTED]\n"), "{out}");
    }

    /// No input can panic the scanner: empty strings, lone markers, unusual
    /// Unicode and partial shapes.
    #[test]
    fn no_input_can_panic() {
        for line in [
            "",
            "jdk1.",
            "jdk1.x",
            "sk-",
            "sk-1234567890abcdef",
            "ghp_",
            "ghp_01234567890123456789",
            "AIza",
            "token=",
            "token:",
            "Bearer",
            "Bearer ",
            "\u{1F600} token=abc \u{00e9}",
            "   \t\r\n",
            "x-jarvis-token",
        ] {
            let _ = scrub_log_line(line);
        }
    }
}
