//! Where the desktop keeps the pairing token the owner typed into Settings:
//! **Windows Credential Manager**, not the settings file.
//!
//! ## Why
//!
//! `CLAUDE.md` rule 3 says a secret is "kept out of anything the app writes to
//! disk in plain text", and until this module the typed token sat in
//! `jarvis-desktop.json` as plain JSON next to the window positions. Windows
//! Credential Manager keeps it encrypted to the signed-in Windows user (DPAPI),
//! and it is where Windows itself keeps saved network passwords. The owner can
//! see and delete it in Control Panel → Credential Manager → Windows
//! Credentials, under the name in [`TARGET`].
//!
//! ## The three promises
//!
//! 1. **Never write the token as plain text.** A token Credential Manager
//!    refuses is not saved anywhere; Settings says so and why
//!    (`set_api_settings`). It used to fall back to the settings file.
//! 2. **Move an old value once, then remove it - never lose it.**
//!    [`plan_migration`] copies a token an older version left in the settings
//!    file into the credential store, reads it back, and only when the
//!    read-back matches deletes the plain-text copy. If it cannot, the old
//!    copy is left where it was (not rewritten) so the pairing survives.
//! 3. **Never log the token.** Errors carry the Windows error code, never the
//!    value.
//!
//! The backend keeps its OWN token here too, under [`BACKEND_TARGET`]; this
//! app only reads that one ([`read_backend`]).
//!
//! On anything but Windows there is no credential store here: every call
//! reports [`Unavailable`](StoreError::Unavailable). The product is a Windows
//! app; this only keeps the Linux/macOS build honest.

/// The name the token is filed under in Credential Manager.
pub const TARGET: &str = "Jarvis Desktop/pairing token";

/// The name the BACKEND files its own token under (`backend/jarvis_token_store.py`,
/// `TARGET` there - `test_token_store.py` checks the two are the same text).
/// Read-only from here: the backend makes it, moves its old plain-text file
/// into it, and is the only thing that writes it.
pub const BACKEND_TARGET: &str = "Jarvis Backend/pairing token";

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StoreError {
    /// No credential store on this platform.
    Unavailable,
    /// The store answered with an error. The code, never the value.
    Failed(String),
}

impl std::fmt::Display for StoreError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            StoreError::Unavailable => {
                write!(f, "there is no Windows Credential Manager on this system")
            }
            StoreError::Failed(why) => write!(f, "Windows Credential Manager refused: {why}"),
        }
    }
}

/// Where a token lives, and what to do with the old plain-text copy. Pure,
/// so the decision is testable without Windows.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Migration {
    /// No plain-text token: nothing to move.
    Nothing,
    /// Moved and verified: delete the plain-text copy.
    RemovePlain,
    /// Could not be moved or verified: keep the plain-text copy (never lose it).
    KeepPlain(String),
}

/// The migration decision, given what the settings file holds and three
/// operations on the credential store. Written against closures so the
/// "never lose it" rule is tested on every platform, not only Windows.
pub fn plan_migration(
    plain: Option<&str>,
    write: impl FnOnce(&str) -> Result<(), StoreError>,
    read_back: impl FnOnce() -> Result<Option<String>, StoreError>,
) -> Migration {
    let Some(plain) = plain.map(str::trim).filter(|t| !t.is_empty()) else {
        return Migration::Nothing;
    };
    if let Err(e) = write(plain) {
        return Migration::KeepPlain(e.to_string());
    }
    match read_back() {
        Ok(Some(back)) if back == plain => Migration::RemovePlain,
        Ok(_) => Migration::KeepPlain(
            "the token read back from Credential Manager did not match".to_string(),
        ),
        Err(e) => Migration::KeepPlain(e.to_string()),
    }
}

#[cfg(windows)]
mod imp {
    use super::StoreError;
    use windows_sys::Win32::Foundation::{GetLastError, ERROR_NOT_FOUND};
    use windows_sys::Win32::Security::Credentials::{
        CredDeleteW, CredFree, CredReadW, CredWriteW, CREDENTIALW, CRED_PERSIST_LOCAL_MACHINE,
        CRED_TYPE_GENERIC,
    };

    /// Credential Manager's own limit for a generic credential's secret.
    const MAX_BLOB: usize = 5 * 512;

    fn wide(s: &str) -> Vec<u16> {
        s.encode_utf16().chain(std::iter::once(0)).collect()
    }

    pub fn read(name: &str) -> Result<Option<String>, StoreError> {
        let target = wide(name);
        let mut cred: *mut CREDENTIALW = std::ptr::null_mut();
        // SAFETY: `target` is a NUL-terminated UTF-16 buffer that outlives the
        // call; `cred` is an out-pointer CredReadW fills on success and that
        // is released with CredFree below, on every path that got one.
        let ok = unsafe { CredReadW(target.as_ptr(), CRED_TYPE_GENERIC, 0, &mut cred) };
        if ok == 0 {
            // SAFETY: no preconditions.
            let code = unsafe { GetLastError() };
            return if code == ERROR_NOT_FOUND {
                Ok(None)
            } else {
                Err(StoreError::Failed(format!(
                    "reading failed (Windows error {code})"
                )))
            };
        }
        // SAFETY: CredReadW succeeded, so `cred` points at a valid CREDENTIALW
        // whose blob is `CredentialBlobSize` bytes long (possibly zero, with a
        // null pointer). The bytes are copied out before CredFree.
        let bytes = unsafe {
            let c = &*cred;
            let out = if c.CredentialBlob.is_null() || c.CredentialBlobSize == 0 {
                Vec::new()
            } else {
                std::slice::from_raw_parts(c.CredentialBlob, c.CredentialBlobSize as usize).to_vec()
            };
            CredFree(cred as *const core::ffi::c_void);
            out
        };
        let text = String::from_utf8(bytes)
            .map_err(|_| StoreError::Failed("the stored token is not valid text".to_string()))?;
        let text = text.trim().to_string();
        Ok(if text.is_empty() { None } else { Some(text) })
    }

    pub fn write(name: &str, token: &str) -> Result<(), StoreError> {
        let bytes = token.as_bytes();
        if bytes.len() > MAX_BLOB {
            return Err(StoreError::Failed(format!(
                "the token is longer than Credential Manager allows ({} bytes)",
                MAX_BLOB
            )));
        }
        let mut target = wide(name);
        let mut user = wide("jarvis");
        let mut blob = bytes.to_vec();
        // SAFETY: zeroed is a valid CREDENTIALW (all integers and null
        // pointers); every pointer set below points into a local buffer that
        // outlives the CredWriteW call, which copies what it needs.
        let ok = unsafe {
            let mut cred: CREDENTIALW = std::mem::zeroed();
            cred.Type = CRED_TYPE_GENERIC;
            cred.TargetName = target.as_mut_ptr();
            cred.UserName = user.as_mut_ptr();
            cred.CredentialBlobSize = blob.len() as u32;
            cred.CredentialBlob = blob.as_mut_ptr();
            cred.Persist = CRED_PERSIST_LOCAL_MACHINE;
            CredWriteW(&cred, 0)
        };
        // Do not leave the copy lying in freed memory longer than needed.
        blob.iter_mut().for_each(|b| *b = 0);
        if ok == 0 {
            // SAFETY: no preconditions.
            let code = unsafe { GetLastError() };
            return Err(StoreError::Failed(format!(
                "saving failed (Windows error {code})"
            )));
        }
        Ok(())
    }

    pub fn delete(name: &str) -> Result<(), StoreError> {
        let target = wide(name);
        // SAFETY: `target` is a NUL-terminated UTF-16 buffer that outlives
        // the call.
        let ok = unsafe { CredDeleteW(target.as_ptr(), CRED_TYPE_GENERIC, 0) };
        if ok == 0 {
            // SAFETY: no preconditions.
            let code = unsafe { GetLastError() };
            if code != ERROR_NOT_FOUND {
                return Err(StoreError::Failed(format!(
                    "deleting failed (Windows error {code})"
                )));
            }
        }
        Ok(())
    }
}

#[cfg(not(windows))]
mod imp {
    use super::StoreError;

    pub fn read(_name: &str) -> Result<Option<String>, StoreError> {
        Err(StoreError::Unavailable)
    }
    pub fn write(_name: &str, _token: &str) -> Result<(), StoreError> {
        Err(StoreError::Unavailable)
    }
    pub fn delete(_name: &str) -> Result<(), StoreError> {
        Err(StoreError::Unavailable)
    }
}

/// What Credential Manager last said, so every request does not ask it again.
/// `None` = not asked yet (or the last ask failed, so ask next time).
static CACHE: std::sync::Mutex<Option<Option<String>>> = std::sync::Mutex::new(None);

fn remember(value: Option<Option<String>>) {
    if let Ok(mut c) = CACHE.lock() {
        *c = value;
    }
}

/// The saved token, if Credential Manager holds one - asked once, then
/// remembered until this process writes or deletes it.
pub fn read() -> Result<Option<String>, StoreError> {
    if let Ok(c) = CACHE.lock() {
        if let Some(known) = c.as_ref() {
            return Ok(known.clone());
        }
    }
    let got = imp::read(TARGET)?;
    remember(Some(got.clone()));
    Ok(got)
}

/// Asks Credential Manager itself, past the cache - for checking that a
/// write really landed before the plain-text copy is deleted.
pub fn read_fresh() -> Result<Option<String>, StoreError> {
    let got = imp::read(TARGET)?;
    remember(Some(got.clone()));
    Ok(got)
}

/// Saves (or replaces) the token in Credential Manager.
pub fn write(token: &str) -> Result<(), StoreError> {
    remember(None);
    imp::write(TARGET, token)?;
    remember(Some(Some(token.to_string())));
    Ok(())
}

/// Removes the token from Credential Manager. Not an error when there was none.
pub fn delete() -> Result<(), StoreError> {
    remember(None);
    imp::delete(TARGET)?;
    remember(Some(None));
    Ok(())
}

/// Where the web search keys are kept for the backend (Settings -> "Web
/// search"; `backend/jarvis_search.py` `KEY_TARGETS` reads them under the same
/// names - `test_web_search.py` checks the text). The owner's decision of
/// 2026-09-25: keys are entered on the PC only, so this app writes them
/// straight into Credential Manager and they never cross the link to the
/// backend's API, nor reach the phone. Written, checked and deleted here;
/// never read back to a page - only whether one is saved.
pub const SEARCH_KEY_TARGETS: [(&str, &str); 3] = [
    ("exa", "Jarvis Backend/Exa key"),
    ("tavily", "Jarvis Backend/Tavily key"),
    ("brave", "Jarvis Backend/Brave Search key"),
];

/// The Credential Manager name for `provider`'s key, or `None` for a
/// provider that uses none.
pub fn search_key_target(provider: &str) -> Option<&'static str> {
    SEARCH_KEY_TARGETS
        .iter()
        .find(|(p, _)| *p == provider)
        .map(|(_, t)| *t)
}

/// Whether `key` can be a key: 8 to 200 plain characters, no spaces - the
/// backend's own rule (`jarvis_search.key_problem`). The reason never quotes it.
pub fn search_key_problem(key: &str) -> Option<&'static str> {
    let k = key.trim();
    if k.is_empty() {
        return Some("The key is empty.");
    }
    if k.len() < 8 || k.len() > 200 || !k.bytes().all(|b| (0x21..=0x7e).contains(&b)) {
        return Some(
            "The key must be 8 to 200 plain characters with no spaces - check that the \
             whole key was copied, and nothing else.",
        );
    }
    None
}

/// Saves a web search key, then reads it back to be sure it landed.
pub fn write_search_key(provider: &str, key: &str) -> Result<(), StoreError> {
    let target = search_key_target(provider)
        .ok_or_else(|| StoreError::Failed("only Exa, Tavily and Brave Search use a key".into()))?;
    let key = key.trim();
    imp::write(target, key)?;
    match imp::read(target)? {
        Some(back) if back == key => Ok(()),
        _ => Err(StoreError::Failed(
            "the key read back from Credential Manager did not match".into(),
        )),
    }
}

/// Removes a web search key. Not an error when there was none.
pub fn delete_search_key(provider: &str) -> Result<(), StoreError> {
    let target = search_key_target(provider)
        .ok_or_else(|| StoreError::Failed("only Exa, Tavily and Brave Search use a key".into()))?;
    imp::delete(target)
}

/// The four account secrets email, calendar and Home Assistant used to keep
/// as plain Windows user environment variables (ease-of-use audit row 15,
/// "Security G3"; `settings.html` "Accounts"; `account_secrets.rs`).
///
/// (short id, the environment variable the backend still reads FIRST if the
/// owner already set one - `backend/jarvis_token_store.resolve_secret`'s
/// own rule 2, "someone who set it meant it" - and the Credential Manager
/// name for the fallback). `test_account_secrets.py` checks the backend
/// reads under these exact four names.
pub const ACCOUNT_SECRET_TARGETS: [(&str, &str, &str); 4] = [
    (
        "imap_user",
        "JARVIS_IMAP_USER",
        "Jarvis Backend/IMAP username",
    ),
    (
        "imap_password",
        "JARVIS_IMAP_PASSWORD",
        "Jarvis Backend/IMAP password",
    ),
    (
        "calendar_ics_url",
        "JARVIS_CALENDAR_ICS_SECRET_URL",
        "Jarvis Backend/Calendar iCal link",
    ),
    (
        "home_token",
        "JARVIS_HOME_TOKEN",
        "Jarvis Backend/Home Assistant token",
    ),
];

/// The Credential Manager name for `name`'s secret, or `None` for a name
/// that is not one of the four.
pub fn account_secret_target(name: &str) -> Option<&'static str> {
    ACCOUNT_SECRET_TARGETS
        .iter()
        .find(|(n, _, _)| *n == name)
        .map(|(_, _, t)| *t)
}

/// The environment variable name for `name`'s secret - the one the backend
/// still reads first, if it is set. Never returns the value.
pub fn account_secret_env(name: &str) -> Option<&'static str> {
    ACCOUNT_SECRET_TARGETS
        .iter()
        .find(|(n, _, _)| *n == name)
        .map(|(_, e, _)| *e)
}

/// Whether `name`'s environment variable is set to a non-blank value on
/// THIS PC, right now - checked fresh (a value set after Jarvis Desktop
/// started needs a restart to be seen here, same as every other setting in
/// this file). Never the value, only whether one is there. `None` for a
/// name that is not one of the four.
pub fn account_secret_env_set(name: &str) -> Option<bool> {
    account_secret_env(name).map(|env_name| {
        std::env::var(env_name)
            .map(|v| !v.trim().is_empty())
            .unwrap_or(false)
    })
}

/// Whether `value` can be one of the four secrets, or why not. Deliberately
/// more permissive than `search_key_problem`: an IMAP password or a Home
/// Assistant token can hold a space or punctuation a search key never does,
/// and the calendar link is a whole URL. The reason never quotes it.
pub fn account_secret_problem(name: &str, value: &str) -> Option<&'static str> {
    let v = value.trim();
    if v.is_empty() {
        return Some("That is empty.");
    }
    if v.chars().any(|c| c.is_control()) {
        return Some("That has a character it should not - copy it again.");
    }
    if name == "calendar_ics_url" {
        if v.len() > 2048 {
            return Some("That address is too long.");
        }
        if !v.starts_with("https://") {
            return Some(
                "That does not start with https:// - copy the \"Secret address in iCal \
                 format\" again.",
            );
        }
        return None;
    }
    if v.len() > 1024 {
        return Some("That is too long.");
    }
    None
}

/// Saves one of the four account secrets, then reads it back to be sure it
/// landed - the same check `write_search_key` makes.
pub fn write_account_secret(name: &str, value: &str) -> Result<(), StoreError> {
    let target = account_secret_target(name)
        .ok_or_else(|| StoreError::Failed("not one of the four account secrets".into()))?;
    let value = value.trim();
    imp::write(target, value)?;
    match imp::read(target)? {
        Some(back) if back == value => Ok(()),
        _ => Err(StoreError::Failed(
            "the value read back from Credential Manager did not match".into(),
        )),
    }
}

/// Removes one of the four account secrets. Not an error when there was none.
pub fn delete_account_secret(name: &str) -> Result<(), StoreError> {
    let target = account_secret_target(name)
        .ok_or_else(|| StoreError::Failed("not one of the four account secrets".into()))?;
    imp::delete(target)
}

/// Whether Credential Manager holds a value for `name` - never the value
/// itself. `Ok(None)` when `name` is not one of the four.
pub fn account_secret_saved(name: &str) -> Result<Option<bool>, StoreError> {
    let Some(target) = account_secret_target(name) else {
        return Ok(None);
    };
    Ok(Some(imp::read(target)?.is_some()))
}

/// The token the backend made for itself, if Credential Manager holds one.
///
/// Asked every time, not cached: on a first run the backend makes it moments
/// after this app starts, and `jarvis_token_store.py forget` removes it while
/// the app is open - a remembered answer would be wrong in both cases.
/// Reading a credential is a local call, cheap next to the request it is for.
pub fn read_backend() -> Result<Option<String>, StoreError> {
    imp::read(BACKEND_TARGET)
}

#[cfg(test)]
mod tests {
    use super::{plan_migration, Migration, StoreError};

    #[test]
    fn nothing_to_move_when_the_settings_file_has_no_token() {
        assert_eq!(
            plan_migration(None, |_| panic!(), || panic!()),
            Migration::Nothing
        );
        assert_eq!(
            plan_migration(Some("  "), |_| panic!(), || panic!()),
            Migration::Nothing
        );
    }

    #[test]
    fn a_verified_copy_lets_the_plain_text_go() {
        let got = plan_migration(Some("abc"), |_| Ok(()), || Ok(Some("abc".to_string())));
        assert_eq!(got, Migration::RemovePlain);
    }

    /// The rule this module exists to keep: a failure never loses the pairing.
    #[test]
    fn any_failure_keeps_the_plain_text_copy() {
        let unavailable = plan_migration(
            Some("abc"),
            |_| Err(StoreError::Unavailable),
            || panic!("no read-back after a failed write"),
        );
        assert!(matches!(unavailable, Migration::KeepPlain(_)));
        let unreadable = plan_migration(
            Some("abc"),
            |_| Ok(()),
            || Err(StoreError::Failed("x".into())),
        );
        assert!(matches!(unreadable, Migration::KeepPlain(_)));
        let mismatched = plan_migration(Some("abc"), |_| Ok(()), || Ok(Some("abd".to_string())));
        assert!(matches!(mismatched, Migration::KeepPlain(_)));
        let missing = plan_migration(Some("abc"), |_| Ok(()), || Ok(None));
        assert!(matches!(missing, Migration::KeepPlain(_)));
    }

    /// Web search keys: two names, the backend's; a key is checked the
    /// backend's way; the reason never quotes it.
    #[test]
    fn search_keys_have_the_backends_names_and_rule() {
        use super::{search_key_problem, search_key_target};
        assert_eq!(
            search_key_target("tavily"),
            Some("Jarvis Backend/Tavily key")
        );
        assert_eq!(search_key_target("exa"), Some("Jarvis Backend/Exa key"));
        assert_eq!(
            search_key_target("brave"),
            Some("Jarvis Backend/Brave Search key")
        );
        assert_eq!(search_key_target("searxng"), None);
        assert_eq!(search_key_target("duckduckgo"), None);
        let fake = format!("{}{}", "tvly-", "fake0123456789");
        assert!(search_key_problem(&fake).is_none());
        assert!(search_key_problem(&format!("  {fake}\n")).is_none());
        for bad in ["", "short", "has a space in it", "tab\tin\tthe\tmiddle"] {
            let why = search_key_problem(bad).expect(bad);
            assert!(bad.len() < 5 || !why.contains(bad));
        }
        assert!(search_key_problem(&"x".repeat(201)).is_some());
    }

    /// The reason given never contains the token itself.
    #[test]
    fn the_reason_never_quotes_the_token() {
        let got = plan_migration(
            Some("s3cret-token"),
            |_| Ok(()),
            || Ok(Some("other".to_string())),
        );
        match got {
            Migration::KeepPlain(why) => assert!(!why.contains("s3cret")),
            other => panic!("expected KeepPlain, got {other:?}"),
        }
    }

    /// The four account secrets: named the way the backend's
    /// `jarvis_token_store.resolve_secret` callers expect, and the same
    /// permissive-but-sane rule for all four (`test_account_secrets.py`
    /// checks the backend's own targets against this table).
    #[test]
    fn account_secrets_have_the_backends_four_names() {
        use super::{account_secret_env, account_secret_problem, account_secret_target};
        assert_eq!(
            account_secret_target("imap_user"),
            Some("Jarvis Backend/IMAP username")
        );
        assert_eq!(
            account_secret_target("imap_password"),
            Some("Jarvis Backend/IMAP password")
        );
        assert_eq!(
            account_secret_target("calendar_ics_url"),
            Some("Jarvis Backend/Calendar iCal link")
        );
        assert_eq!(
            account_secret_target("home_token"),
            Some("Jarvis Backend/Home Assistant token")
        );
        assert_eq!(account_secret_target("not_one_of_them"), None);
        assert_eq!(account_secret_env("imap_user"), Some("JARVIS_IMAP_USER"));
        assert_eq!(
            account_secret_env("imap_password"),
            Some("JARVIS_IMAP_PASSWORD")
        );
        assert_eq!(
            account_secret_env("calendar_ics_url"),
            Some("JARVIS_CALENDAR_ICS_SECRET_URL")
        );
        assert_eq!(account_secret_env("home_token"), Some("JARVIS_HOME_TOKEN"));

        assert!(account_secret_problem("imap_user", "owner@example.com").is_none());
        assert!(account_secret_problem("home_token", "a token with no spaces").is_none());
        for name in [
            "imap_user",
            "imap_password",
            "calendar_ics_url",
            "home_token",
        ] {
            let why = account_secret_problem(name, "").expect(name);
            assert_eq!(why, "That is empty.");
            let why = account_secret_problem(name, "   ").expect(name);
            assert_eq!(why, "That is empty.");
        }
        // Only the calendar link must be https:// - a password or token is
        // free text otherwise, unlike a search key (no "no spaces" rule).
        assert!(account_secret_problem("imap_password", "correct horse battery staple").is_none());
        assert!(
            account_secret_problem("calendar_ics_url", "https://calendar.google.com/x").is_none()
        );
        let why = account_secret_problem("calendar_ics_url", "http://calendar.google.com/x")
            .expect("http rejected");
        assert!(why.contains("https://"));
        let why = account_secret_problem("calendar_ics_url", "webcal://calendar.google.com/x")
            .expect("webcal rejected");
        assert!(why.contains("https://"));
        assert!(account_secret_problem("imap_user", &"x".repeat(1025)).is_some());
        assert!(account_secret_problem(
            "calendar_ics_url",
            &format!("https://{}", "x".repeat(2048))
        )
        .is_some());
        let secret = "s3cret-value-nobody-should-see";
        let why = account_secret_problem("home_token", &format!("bad\ttab{secret}")).unwrap();
        assert!(!why.contains(secret), "the reason quoted the value: {why}");
    }
}
