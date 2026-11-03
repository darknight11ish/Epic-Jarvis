//! A second, third, any-number-of chat windows at once (the owner's ask of
//! 2026-11-03: "have multiple conversation windows open at once").
//!
//! One HUD window has always been the desktop's conversation surface. This
//! module adds more of the SAME surface - the same `jarvis_hud.html`, the same
//! injected bootstrap, the same dark theme and minimum size - each as its own
//! webview with its own conversation. Closing one never closes the others: they
//! are ordinary separate `WebviewWindow`s, and nothing here holds the main HUD
//! open or ties the extra ones to it.
//!
//! # Labels are a fixed set, not a counter
//!
//! [`CHAT_LABELS`] is the complete list - `chat-1` .. `chat-8` - and this
//! module only ever uses one of those. That is not cosmetic: `lock.rs`'s
//! capture-block sweep and `window_memory.rs`'s tracked list are `&'static str`
//! tables, so a fixed set is what lets an extra chat window be covered by App
//! lock and remembered for size/place at all. A generated label could not be
//! in either without widening both to owned strings.
//!
//! # Which conversation a window is on
//!
//! A window may be asked for a conversation id (the query string
//! `?conversation=<id>`, and the same id through the injected
//! `window.__jarvisConversation`, which is how the shell passes it before the
//! page's own scripts run). The bootstrap opens that kept chat in the new
//! window through the page's own History host, so only that window changes.
//! With no id the window starts on a fresh conversation, exactly as pressing
//! "New chat" in the HUD does. The page's own conversation id is per-window
//! memory (`hud-history.js` / `chat-history.js`), so two windows can never
//! append one transcript.
//!
//! # The same chat in two windows
//!
//! It cannot happen: [`open_for`] keeps a map of conversation id -> label and
//! FOCUSES the window already showing that conversation instead of building a
//! second one on the same transcript. That is the rule the owner asked for as
//! "open this conversation in a new window" - the window exists, so there is
//! nothing to duplicate. The map entry is dropped when the window is destroyed
//! (`WindowEvent::Destroyed`). The lookup itself is pure and tested without a
//! window ([`dedupe_label`]).
//!
//! Deliberately NOT done here: nothing is restored from a saved window list at
//! start-up. The main HUD is the window Jarvis always opens; extra chat windows
//! are something the owner asked for in this session, and silently reopening
//! five of them at login is not the same request.

use std::collections::HashMap;
use std::sync::Mutex;

use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

/// Label prefix of an extra chat window.
pub const CHAT_LABEL_PREFIX: &str = "chat-";

/// Every label an extra chat window can have. Fixed on purpose (see the module
/// doc): the App-lock capture sweep and the window-state table both hold
/// `&'static str`s.
pub const CHAT_LABELS: [&str; 8] = [
    "chat-1", "chat-2", "chat-3", "chat-4", "chat-5", "chat-6", "chat-7", "chat-8",
];

/// Every extra chat window label and the page it loads, in one table the shell's
/// window builder and `tools/check_invoke_grants.py` can both read.
///
/// The grant check maps a capability's `windows` list to the page each label
/// loads. These labels are chosen at RUNTIME from [`CHAT_LABELS`], so there is
/// no literal builder call to read - this table is what tells both the check
/// and a reader which page a `chat-*` window really is. A test holds it to
/// [`CHAT_LABELS`] so the two cannot drift.
pub const CHAT_WINDOW_PAGES: [(&str, &str); 8] = [
    ("chat-1", "jarvis_hud.html"),
    ("chat-2", "jarvis_hud.html"),
    ("chat-3", "jarvis_hud.html"),
    ("chat-4", "jarvis_hud.html"),
    ("chat-5", "jarvis_hud.html"),
    ("chat-6", "jarvis_hud.html"),
    ("chat-7", "jarvis_hud.html"),
    ("chat-8", "jarvis_hud.html"),
];

/// The most extra chat windows open at once. A guard, not a policy: each one
/// is a WebView2 process holding a chat, and a loop that asked for windows must
/// not take the machine down.
pub const MAX_CHAT_WINDOWS: usize = CHAT_LABELS.len();

/// The page every chat window loads - the same one the main HUD loads.
const CHAT_PAGE: &str = "jarvis_hud.html";

/// A chat window's title. The main HUD is "Jarvis"; an extra one says what it
/// is, so the taskbar does not show two identical windows.
const CHAT_TITLE: &str = "Jarvis — Chat";

/// The same inner size and minimum the HUD builder declares (`lib.rs`
/// `build_hud_window`). A chat window is the same surface, so it opens at the
/// same size and may not be dragged below the same floor.
const CHAT_INNER: (f64, f64) = (1280.0, 820.0);
const CHAT_MIN: (f64, f64) = (960.0, 640.0);

/// The longest conversation id this app will put in a window: an id is a
/// database key, not a sentence. Longer than this is refused rather than
/// truncated, because a truncated id names a different (or no) conversation.
pub const MAX_CONVERSATION_ID: usize = 200;

/// Bookkeeping for the extra windows. Managed state (`.manage` in `lib.rs`).
#[derive(Default)]
pub struct ChatWindows {
    /// conversation id -> window label, for the windows that have one.
    open: Mutex<HashMap<String, String>>,
}

/// Whether a window label belongs to an extra chat window.
pub fn is_chat_window(label: &str) -> bool {
    CHAT_LABELS.contains(&label)
}

/// The first free label, or `None` when all [`MAX_CHAT_WINDOWS`] are open.
/// Pure: the caller hands in "does this window exist".
pub fn free_label<F>(exists: F) -> Option<&'static str>
where
    F: Fn(&str) -> bool,
{
    CHAT_LABELS.iter().copied().find(|label| !exists(label))
}

/// A conversation id as this module will accept it, or `None` for "no id".
///
/// Trimmed; an empty string means no id (a plain new chat window); control
/// characters are refused outright (a window label and an id are not places to
/// smuggle anything); the rest is capped at [`MAX_CONVERSATION_ID`] characters,
/// counted in chars so a multi-byte id is not cut mid-character.
pub fn clean_conversation(raw: &str) -> Option<String> {
    let trimmed = raw.trim();
    if trimmed.is_empty() || trimmed.chars().any(char::is_control) {
        return None;
    }
    Some(trimmed.chars().take(MAX_CONVERSATION_ID).collect())
}

/// Which label an `open` request should reuse, from the map and a "does this
/// window still exist" check. Pure: the map is handed in.
///
/// `None` means "build a new window". An entry whose window is gone is ignored
/// (the caller drops it); it must never be returned, or a request would try to
/// focus a window that does not exist.
pub fn dedupe_label<F>(
    open: &HashMap<String, String>,
    conversation: &str,
    exists: F,
) -> Option<String>
where
    F: Fn(&str) -> bool,
{
    open.get(conversation)
        .filter(|label| exists(label))
        .cloned()
}

/// The window title for a chat window. The page's own title is the
/// conversation's; this title is only the OS chrome above it, so it never
/// repeats an id.
pub fn chat_title(_conversation: Option<&str>) -> String {
    CHAT_TITLE.to_string()
}

// ---------------------------------------------------------------------------
// Opening
// ---------------------------------------------------------------------------

/// Brings an existing chat window forward.
fn focus(window: &WebviewWindow) -> Result<(), String> {
    window
        .show()
        .map_err(|e| format!("unable to show the chat window: {e}"))?;
    let _ = window.unminimize();
    window
        .set_focus()
        .map_err(|e| format!("unable to focus the chat window: {e}"))
}

fn label_exists(app: &AppHandle, label: &str) -> bool {
    app.get_webview_window(label).is_some()
}

/// Opens a chat window, or focuses the one already showing `conversation`.
///
/// `conversation` must already be [`clean_conversation`]'d; `None` always
/// builds a new window, because "new chat" really means a new one.
pub fn open_for(app: &AppHandle, conversation: Option<String>) -> Result<String, String> {
    // A conversation that is already on screen comes back as ITSELF. The app
    // lock covers the HUD and every chat window as one family (`Covered::Hud`),
    // so the decision here has to name the window: `may_open_window` carries
    // this label into the unlock, and a successful Windows Hello brings back
    // the clicked chat window instead of the main HUD (audit finding,
    // 2026-11-03; the main HUD stealing the unlock left the asked-for window
    // hidden).
    if let Some(conv) = conversation.as_deref() {
        let existing = {
            let state = app.state::<ChatWindows>();
            let lock = state
                .open
                .lock()
                .map_err(|_| "the chat window list is unavailable".to_string())?;
            dedupe_label(&lock, conv, |label| label_exists(app, label))
        };
        if let Some(label) = existing {
            if let Some(window) = app.get_webview_window(&label) {
                if !crate::lock::may_open_window(app, &label) {
                    return Ok(String::new());
                }
                focus(&window)?;
                return Ok(label);
            }
            // The window went away between the check and the focus: forget the
            // stale entry and build a new one below.
            if let Ok(mut open) = app.state::<ChatWindows>().open.lock() {
                open.remove(conv);
            }
        }
    }

    // Creating a NEW window: the app lock, on the same rule as every other way
    // into a HUD surface (`windows::show_hud`): an extra chat window is the
    // HUD's own page, with its approvals and its History list, so it is not put
    // on a locked PC. Without this the tray row, or a chat answer's own
    // `open_area` route arriving while the HUD is hidden, could put a HUD page
    // over a locked desktop - and a FOCUSED one holds the lock open (`lock.rs`
    // `covered_focused`), so it would not even be swept away again.
    // When Windows Hello confirms, lock.rs shows the main HUD (there is no new
    // window yet to show); the press is then repeated and this opens. An empty
    // label means "nothing was opened".
    if !crate::lock::may_open(app, crate::lock::Covered::Hud) {
        return Ok(String::new());
    }

    let Some(label) = free_label(|label| label_exists(app, label)) else {
        return Err(format!(
            "There are already {MAX_CHAT_WINDOWS} chat windows open - that is the limit. \
             Close one of them first. Nothing was opened."
        ));
    };

    let base = crate::commands::jarvis_base(app);
    let script = crate::hud_page_script(&base, conversation.as_deref());

    let window = WebviewWindowBuilder::new(
        app,
        label,
        // The page literal stays HERE, beside the builder: `tools/check_invoke_grants.py`
        // reads it to know which page this window loads, and the page is what
        // decides which commands the window may call.
        WebviewUrl::App(CHAT_PAGE.into()),
    )
    .title(chat_title(conversation.as_deref()))
    .inner_size(CHAT_INNER.0, CHAT_INNER.1)
    .min_inner_size(CHAT_MIN.0, CHAT_MIN.1)
    .center()
    .resizable(true)
    .decorations(true)
    .transparent(false)
    .skip_taskbar(false)
    .visible(false)
    .focused(false)
    .shadow(true)
    .theme(Some(tauri::Theme::Dark))
    .initialization_script(&script)
    .build()
    .map_err(|e| format!("unable to open a chat window: {e}"))?;

    // Its own size and place, restored as every other remembered window is
    // (`window_memory.rs` treats every label in this set like the HUD), then
    // shown. A window that stays hidden gets its size/place now and its
    // maximise later; this one is shown at once, so it takes the full restore.
    crate::window_memory::restore(&window, true);
    focus(&window)?;

    let handle = app.clone();
    let mine = label.to_string();
    window.on_window_event(move |event| {
        if matches!(event, tauri::WindowEvent::Destroyed) {
            if let Ok(mut open) = handle.state::<ChatWindows>().open.lock() {
                open.retain(|_conversation, owned| owned != &mine);
            }
        }
    });

    if let Some(conv) = conversation {
        if let Ok(mut open) = app.state::<ChatWindows>().open.lock() {
            open.insert(conv, label.to_string());
        }
    }
    Ok(label.to_string())
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

/// Opens a fresh chat window (no conversation).
#[tauri::command]
pub fn new_chat_window(app: AppHandle) -> Result<String, String> {
    open_for(&app, None)
}

/// Opens `conversation` in a new window, or brings the window already showing
/// it to the front. The id is the page's own conversation id; it is cleaned
/// here and nothing else is accepted.
#[tauri::command]
pub fn open_conversation_window(app: AppHandle, conversation: String) -> Result<String, String> {
    match clean_conversation(&conversation) {
        Some(conv) => open_for(&app, Some(conv)),
        None => Err("That is not a conversation id, so no window was opened.".to_string()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn there_are_eight_labels_and_they_are_the_only_ones_recognised() {
        assert_eq!(CHAT_LABELS.len(), 8);
        assert_eq!(MAX_CHAT_WINDOWS, 8);
        assert_eq!(CHAT_LABELS[0], "chat-1");
        assert_eq!(CHAT_LABELS[7], "chat-8");
        for label in [
            "hud", "chat-", "chat-x", "xchat-1", "chat-1-2", "chat-9", "settings",
        ] {
            assert!(!is_chat_window(label), "{label}");
        }
    }

    #[test]
    fn every_label_names_the_hud_page_in_the_table_the_grant_check_reads() {
        assert_eq!(CHAT_WINDOW_PAGES.len(), CHAT_LABELS.len());
        for (index, (label, page)) in CHAT_WINDOW_PAGES.iter().enumerate() {
            assert_eq!(*label, CHAT_LABELS[index], "the two label tables disagree");
            assert_eq!(*page, "jarvis_hud.html", "{label} loads a different page");
        }
    }

    #[test]
    fn the_first_free_label_is_chosen_and_all_eight_being_open_says_none() {
        assert_eq!(free_label(|_| false), Some("chat-1"));
        assert_eq!(free_label(|label| label == "chat-1"), Some("chat-2"));
        assert_eq!(free_label(|_| true), None);
    }

    /// The app lock is asked BEFORE this module can put a HUD page on screen.
    ///
    /// A source-text pin, the same pattern `lock.rs` uses for its own opt-out
    /// guard: the rule is an ORDER inside one function, and a unit test opens
    /// no window, so the file is read back rather than remembered. It exists
    /// because this hole was real once (2026-11-03): a chat window created
    /// while App lock was closed showed the whole HUD page - pending cards and
    /// chat titles - over a locked desktop, and the focused window then counted
    /// as "the owner is here", so the away-watch left it there.
    #[test]
    fn a_chat_window_cannot_be_opened_past_the_app_lock() {
        let src = include_str!("chat_windows.rs");
        let start = src.find("pub fn open_for(").expect("open_for is gone");
        let rest = &src[start..];
        let end = rest
            .find("/// Opens a fresh chat window")
            .expect("the open_for body lost its end marker");
        let body = &rest[..end];
        // Two gated paths, because a chat window can be brought up two ways and
        // a future edit could gate one and not the other:
        //  * an EXISTING conversation's window is shown again - gated by
        //    `may_open_window`, which carries that window's label so Windows
        //    Hello brings back the window the owner asked for (not the main
        //    HUD);
        //  * a NEW window - gated by `may_open(Covered::Hud)` before anything
        //    is built.
        let existing_gate = body
            .find("crate::lock::may_open_window(app, &label)")
            .expect("open_for no longer asks the app lock for an existing window");
        let existing_focus = body
            .find("focus(&window)?;")
            .expect("the existing-window focus path is gone");
        assert!(
            existing_gate < existing_focus,
            "a hidden chat window is shown before the app lock is asked"
        );
        let new_gate = body
            .find("crate::lock::may_open(app, crate::lock::Covered::Hud)")
            .expect("open_for no longer asks the app lock for a new window");
        let builder = body
            .find("WebviewWindowBuilder::new")
            .expect("the window builder is gone");
        assert!(
            new_gate < builder,
            "a window is built before the app lock is asked, so a locked PC could get a HUD page"
        );
        // The refusal is a quiet "nothing was opened", not an error toast: the
        // Windows Hello prompt `lock.rs` starts is the answer the owner sees.
        assert!(
            body.contains("return Ok(String::new());"),
            "a locked press must report that nothing was opened"
        );
    }

    #[test]
    fn a_conversation_id_is_trimmed_and_an_empty_one_means_no_id() {
        assert_eq!(clean_conversation("  abc  "), Some("abc".to_string()));
        assert_eq!(clean_conversation(""), None);
        assert_eq!(clean_conversation("   "), None);
    }

    #[test]
    fn a_control_character_is_refused_not_cleaned() {
        assert_eq!(clean_conversation("abc\nxyz"), None);
        assert_eq!(clean_conversation("abc\u{7f}"), None);
    }

    #[test]
    fn a_long_id_is_capped_by_characters_not_bytes() {
        let long = "é".repeat(MAX_CONVERSATION_ID + 10);
        let cleaned = clean_conversation(&long).expect("an id of letters is an id");
        assert_eq!(cleaned.chars().count(), MAX_CONVERSATION_ID);
    }

    #[test]
    fn a_conversation_already_open_is_found_and_reused() {
        let mut open = HashMap::new();
        open.insert("abc".to_string(), "chat-3".to_string());
        assert_eq!(
            dedupe_label(&open, "abc", |label| label == "chat-3"),
            Some("chat-3".to_string())
        );
        // A second conversation is not in the map: a new window is built.
        assert_eq!(dedupe_label(&open, "def", |_| true), None);
    }

    #[test]
    fn a_mapping_whose_window_is_gone_is_not_reused() {
        let mut open = HashMap::new();
        open.insert("abc".to_string(), "chat-3".to_string());
        assert_eq!(dedupe_label(&open, "abc", |_| false), None);
    }

    #[test]
    fn every_window_carries_the_same_title_and_never_the_raw_conversation() {
        assert_eq!(chat_title(None), "Jarvis — Chat");
        assert_eq!(chat_title(Some("secret-looking-id")), "Jarvis — Chat");
    }
}
