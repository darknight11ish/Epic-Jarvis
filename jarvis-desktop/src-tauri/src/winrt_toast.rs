//! A Deny button on the Windows toast for a pending approval.
//!
//! `docs/ARCHITECTURE.md` records this as a known limitation: rule 2's own
//! words are "Deny may be a notification action. Approve may not... Approving
//! means opening the app" - and Windows had neither, because
//! `tauri-plugin-notification`'s desktop backend (`notify-rust`,
//! `win7_notifications` - checked in
//! `tauri-plugin-notification-2.4.0/src/desktop.rs`, not assumed) accepts
//! `action_type_id` on the builder and never reads it. Actions are a
//! mobile-only feature of that plugin. This module goes around it: real
//! WinRT toast XML, built and shown through `windows::UI::Notifications`
//! directly, the same OS surface the plugin itself sits on top of.
//!
//! ## What is verified here, and what is not
//!
//! Every line in this file compiles and passes `cargo clippy -D warnings`
//! against `x86_64-pc-windows-msvc` (this container's own way of checking
//! Rust without a GTK-shaped Linux dependency graph - see `CLAUDE.md`), so
//! the API surface used here is real and matches this exact `windows` crate
//! version. What that check CANNOT prove, and what a Windows host would
//! have to: that clicking "Deny" actually relaunches this exact process
//! with the toast's `arguments` string as its command line, which depends
//! on the Start Menu shortcut Tauri's own NSIS installer creates carrying
//! an `AppUserModelID` that matches what `set_explicit_aumid()` sets below.
//! The plain, buttonless toast this app already shows today (via the
//! plugin) already opens the app on click, which only works because that
//! association already exists - this reuses the *same* association rather
//! than inventing a new one, but has not been watched fire on a real
//! Windows machine. Said here rather than left quiet.
//!
//! ## Why `activationType="foreground"`, not a background COM activator
//!
//! A background-activated toast action (one that runs without bringing the
//! app to the foreground at all - the closest match to Android's own
//! `decideDetached`, which never opens the app) needs a registered COM
//! class: a `CLSID` in the registry pointing at this exe as a
//! `LocalServer32`, `INotificationActivationCallback` implemented and
//! `CoRegisterClassObject`'d, and the Start Menu shortcut's own
//! `ToastActivatorCLSID` property set to match. That is real, install-time
//! plumbing this session cannot add to the NSIS installer with any
//! confidence of getting right un-tested, and a wrong CLSID registration is
//! a worse failure mode than "no Deny button" - a stale or malformed
//! registry entry outlives the app that wrote it. Foreground activation
//! needs none of that: only the AUMID association the app already has.
//! The visible cost is that Deny still briefly activates this process (see
//! `deny_id_from_argv`/`decide_denied_detached` below for what happens when
//! it does) rather than never touching it - a real gap from Android's
//! shape, not hidden here.

use tauri::AppHandle;
use windows::core::HSTRING;
use windows::Data::Xml::Dom::XmlDocument;
use windows::Win32::UI::Shell::SetCurrentProcessExplicitAppUserModelID;
use windows::UI::Notifications::{ToastNotification, ToastNotificationManager};

/// Must match `identifier` in `tauri.conf.json` - the same string the
/// installer's own shortcut is built against, so the AUMID this process
/// claims for itself is the one the shortcut already carries.
const AUMID: &str = "com.jarvis.desktop";

/// The argv marker a Deny action's `arguments` carries. Chosen to look
/// nothing like a normal flag (`--deny=…`) or a file path, since this token
/// arrives as a bare, unparsed command-line argument on relaunch and must
/// not collide with anything a shell or a shortcut would ever pass on its
/// own.
const DENY_PREFIX: &str = "jarvis-deny:";

fn escape_xml(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

/// Claims this process's AUMID before any toast is shown. Idempotent and
/// safe to call every startup - `SetCurrentProcessExplicitAppUserModelID`
/// simply overwrites whatever this process claimed before, and a process
/// has exactly one.
///
/// Logged, not surfaced: failure here degrades to the same "toast shows
/// with a generic identity" state that existed before this file did, never
/// a crash.
pub fn set_explicit_aumid() {
    let result = unsafe { SetCurrentProcessExplicitAppUserModelID(&HSTRING::from(AUMID)) };
    if let Err(e) = result {
        crate::logfile::log(&format!(
            "[jarvis] could not set the explicit AppUserModelID: {e}"
        ));
    }
}

/// Shows an approval toast with a Deny button, or falls back to the plain
/// (buttonless) toast the plugin already knows how to show if anything here
/// fails - a WinRT call erroring must not mean the owner hears nothing at
/// all about a pending approval.
pub fn notify_approval(app: &AppHandle, title: &str, body: &str, id: &str) {
    if let Err(e) = try_notify_approval(title, body, id) {
        crate::logfile::log(&format!(
            "[jarvis] actionable toast failed, falling back to a plain one: {e}"
        ));
        crate::commands::notify(app, title, body);
    }
}

fn try_notify_approval(title: &str, body: &str, id: &str) -> windows::core::Result<()> {
    let xml = format!(
        r#"<toast activationType="foreground" launch="jarvis-open">
  <visual>
    <binding template="ToastGeneric">
      <text>{title}</text>
      <text>{body}</text>
    </binding>
  </visual>
  <actions>
    <action content="Deny" arguments="{prefix}{id}" activationType="foreground"/>
  </actions>
</toast>"#,
        title = escape_xml(title),
        body = escape_xml(body),
        prefix = DENY_PREFIX,
        id = escape_xml(id),
    );

    let doc = XmlDocument::new()?;
    doc.LoadXml(&HSTRING::from(xml))?;
    let toast = ToastNotification::CreateToastNotification(&doc)?;
    let notifier = ToastNotificationManager::CreateToastNotifierWithId(&HSTRING::from(AUMID))?;
    notifier.Show(&toast)
}

/// Reads a Deny action's id out of a relaunch's argv, if this relaunch is
/// one. `None` for every ordinary launch and every ordinary second-instance
/// activation - the ONLY thing that produces this prefix is a click on the
/// button this module's own toast XML built.
pub fn deny_id_from_argv(argv: &[String]) -> Option<&str> {
    argv.iter().find_map(|a| a.strip_prefix(DENY_PREFIX))
}

/// Answers a Deny reached this way with the same call the in-app card and
/// the quickbar use - `decide_approval`, not a second signing path. Runs on
/// its own task: the single-instance callback and the startup path that
/// call this are not `async` themselves, and a decision this shape must not
/// block whichever of those the app is currently inside.
pub fn decide_denied_detached(app: &AppHandle, id: &str) {
    let app = app.clone();
    let id = id.to_string();
    tauri::async_runtime::spawn(async move {
        if let Err(e) = crate::commands::decide_approval(app, id.clone(), false).await {
            crate::logfile::log(&format!(
                "[jarvis] notification Deny for {id} did not go through: {e}"
            ));
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn xml_special_characters_are_escaped() {
        assert_eq!(escape_xml("A & B"), "A &amp; B");
        assert_eq!(escape_xml("<script>"), "&lt;script&gt;");
        assert_eq!(escape_xml(r#"say "hi""#), "say &quot;hi&quot;");
    }

    #[test]
    fn an_ordinary_relaunch_carries_no_deny_id() {
        let argv = vec!["jarvis-desktop.exe".to_string()];
        assert_eq!(deny_id_from_argv(&argv), None);
    }

    #[test]
    fn a_deny_click_s_argv_yields_the_id() {
        let argv = vec![
            "jarvis-desktop.exe".to_string(),
            "jarvis-deny:appr_abc123".to_string(),
        ];
        assert_eq!(deny_id_from_argv(&argv), Some("appr_abc123"));
    }

    /// CONTROL: an id that merely CONTAINS the prefix mid-string, rather
    /// than starting with it, must not match - `strip_prefix`, not `find`.
    #[test]
    fn the_prefix_must_lead_the_argument() {
        let argv = vec!["not-jarvis-deny:appr_x".to_string()];
        assert_eq!(deny_id_from_argv(&argv), None);
    }

    #[test]
    fn aumid_matches_the_tauri_config_identifier() {
        let conf = include_str!("../tauri.conf.json");
        assert!(
            conf.contains(&format!("\"identifier\": \"{AUMID}\"")),
            "AUMID must track tauri.conf.json's own identifier, or the \
             shortcut this depends on will not match what this process claims"
        );
    }
}
