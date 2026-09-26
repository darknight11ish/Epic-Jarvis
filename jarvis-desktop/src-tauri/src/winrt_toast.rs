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
//!
//! ## The two ways a Deny click arrives
//!
//! Both end in `commands::deny_from_notification` - the same sending path
//! `decide_approval` uses, with no way to approve - and both are needed:
//!
//! - **Jarvis already running** - `tauri-plugin-single-instance`'s callback
//!   in `lib.rs` gets the relaunch's argv and answers there.
//! - **Jarvis closed** - the click starts the app, so no second instance
//!   exists and that callback never fires. [`decide_denied_at_startup`]
//!   reads this process's own argv instead. Without it a Deny on a closed
//!   app opened the window and answered nothing at all.

use tauri::{AppHandle, Manager};
use windows::core::HSTRING;
use windows::Data::Xml::Dom::XmlDocument;
use windows::Win32::UI::Shell::SetCurrentProcessExplicitAppUserModelID;
use windows::UI::Notifications::{ToastNotification, ToastNotificationManager};

/// Must match `identifier` in `tauri.conf.json` - the same string the
/// installer's own shortcut is built against, so the AUMID this process
/// claims for itself is the one the shortcut already carries.
const AUMID: &str = "com.jarvis.desktop";

/// The argv marker a Snooze action's `arguments` carries (2026-09-25): a
/// timer, alarm or reminder that went off, snoozed from its own toast. The
/// same foreground-activation path as Deny - see [`notify_fired`].
const SNOOZE_PREFIX: &str = "jarvis-snooze:";

/// The argv marker a Deny action's `arguments` carries. Chosen to look
/// nothing like a normal flag (`--deny=…`) or a file path, since this token
/// arrives as a bare, unparsed command-line argument on relaunch and must
/// not collide with anything a shell or a shortcut would ever pass on its
/// own.
const DENY_PREFIX: &str = "jarvis-deny:";

/// True when this exe is sitting in a cargo output directory rather than
/// where an installer put it - `…\target\debug\jarvis-desktop.exe` or
/// `…\target\release\…`.
///
/// This matters because everything below hangs off an AUMID that only
/// resolves for an INSTALLED app: the association is created by the NSIS
/// installer's Start Menu shortcut, and an uninstalled build has no
/// shortcut, so the AUMID names nothing. `tauri-plugin-notification` makes
/// exactly this check for exactly this reason before setting `app_id`
/// (`tauri-plugin-notification-2.4.0/src/desktop.rs:197-205`, read, not
/// assumed) - and it is skipped here, so the two agree and a test build does
/// not get a worse notification path than a shipped one.
///
/// Conservative on failure: if `current_exe()` cannot be read at all, this
/// says "installed", because the shipped configuration is the one that must
/// keep working.
fn is_uninstalled_build() -> bool {
    let Ok(exe) = std::env::current_exe() else {
        return false;
    };
    let Some(dir) = exe.parent() else {
        return false;
    };
    let sep = std::path::MAIN_SEPARATOR;
    let dir = dir.display().to_string();
    dir.ends_with(&format!("{sep}target{sep}debug"))
        || dir.ends_with(&format!("{sep}target{sep}release"))
}

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
/// **Skipped for an uninstalled build**, and that is not a nicety. This call
/// is process-wide: it changes the identity the plugin's own plain toasts
/// are shown under too, not only this module's. Claiming an AUMID that
/// resolves to no installed shortcut is how a toast ends up silently not
/// appearing at all - which would have hit exactly the `cargo run` builds
/// used for testing, and would have taken the buttonless fallback down with
/// it. See [`is_uninstalled_build`].
///
/// Logged, not surfaced: failure here degrades to the same "toast shows
/// with a generic identity" state that existed before this file did, never
/// a crash.
pub fn set_explicit_aumid() {
    if is_uninstalled_build() {
        crate::logfile::log(
            "[jarvis] uninstalled build - leaving the AppUserModelID alone, \
             so notifications keep the identity they already had",
        );
        return;
    }
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
///
/// `silent`: a "normal" card (the notice's weight: it can be undone and it
/// stays on this PC) shows without a sound - it waits to be found rather
/// than interrupting - where a "heavy" one plays the usual sound. Every card
/// gets a toast either way (the creativity audit, 2026-09-25: a normal card
/// used to get none, and expired unseen). The plain fallback cannot be made
/// silent through the plugin, so it keeps its sound.
pub fn notify_approval(app: &AppHandle, title: &str, body: &str, id: &str, silent: bool) {
    // An uninstalled build has no shortcut carrying this AUMID, so
    // `CreateToastNotifierWithId` is resolving a name that points at
    // nothing. Straight to the plain toast rather than through a WinRT call
    // whose failure mode there is "nothing appears and nothing errors" -
    // a Deny button that is never seen is worth less than a notification
    // that is. See `is_uninstalled_build`.
    if is_uninstalled_build() {
        crate::commands::notify(app, title, body);
        return;
    }
    if let Err(e) = try_notify_approval(title, body, id, silent) {
        crate::logfile::log(&format!(
            "[jarvis] actionable toast failed, falling back to a plain one: {e}"
        ));
        crate::commands::notify(app, title, body);
    }
}

/// The toast's XML. Deny is the ONLY action, whatever the arguments: Approve
/// never goes on a notification (docs/ARCHITECTURE.md §3, rule 2). An empty
/// body (App lock: the title only) leaves out its line.
fn approval_toast_xml(title: &str, body: &str, id: &str, silent: bool) -> String {
    let body_line = if body.trim().is_empty() {
        String::new()
    } else {
        format!("\n      <text>{}</text>", escape_xml(body))
    };
    let audio = if silent {
        "\n  <audio silent=\"true\"/>"
    } else {
        ""
    };
    format!(
        r#"<toast activationType="foreground" launch="jarvis-open">
  <visual>
    <binding template="ToastGeneric">
      <text>{title}</text>{body_line}
    </binding>
  </visual>{audio}
  <actions>
    <action content="Deny" arguments="{prefix}{id}" activationType="foreground"/>
  </actions>
</toast>"#,
        title = escape_xml(title),
        prefix = DENY_PREFIX,
        id = escape_xml(id),
    )
}

fn try_notify_approval(
    title: &str,
    body: &str,
    id: &str,
    silent: bool,
) -> windows::core::Result<()> {
    let xml = approval_toast_xml(title, body, id, silent);

    let doc = XmlDocument::new()?;
    doc.LoadXml(&HSTRING::from(xml))?;
    let toast = ToastNotification::CreateToastNotification(&doc)?;
    let notifier = ToastNotificationManager::CreateToastNotifierWithId(&HSTRING::from(AUMID))?;
    notifier.Show(&toast)
}

/// The XML of a toast that keeps ringing: an alarm, or an urgent "tell me
/// when" (backend jarvis_tellme.py; the owner's decision of 2026-09-25,
/// "alarms that keep ringing"). `scenario="alarm"` keeps it on screen
/// until it is dismissed, and its sound loops until then
/// (`Notification.Looping.Alarm`, `loop="true"`). Windows requires an
/// alarm toast to carry a button; its last button is Windows' own Dismiss
/// (`activationType="system"`), which stops the sound and starts nothing.
/// A timer, alarm or reminder going off also gets Snooze (`snooze`: the job
/// id and the button's words), the same button as [`notify_fired`]'s - it
/// carries the id only. There is no Approve here.
pub(crate) fn alarm_xml(title: &str, body: &str, snooze: Option<(&str, &str)>) -> String {
    let snooze = snooze
        .map(|(id, label)| {
            format!(
                r#"<action content="{label}" arguments="{prefix}{id}" activationType="foreground"/>
    "#,
                label = escape_xml(label),
                prefix = SNOOZE_PREFIX,
                id = escape_xml(id),
            )
        })
        .unwrap_or_default();
    format!(
        r#"<toast scenario="alarm" activationType="foreground" launch="jarvis-open">
  <visual>
    <binding template="ToastGeneric">
      <text>{title}</text>
      <text>{body}</text>
    </binding>
  </visual>
  <audio src="ms-winsoundevent:Notification.Looping.Alarm" loop="true"/>
  <actions>
    {snooze}<action activationType="system" arguments="dismiss" content=""/>
  </actions>
</toast>"#,
        title = escape_xml(title),
        body = escape_xml(body),
    )
}

/// Shows a toast that keeps ringing until it is dismissed ([`alarm_xml`]),
/// or - on an uninstalled build, or if anything here fails - the plain toast
/// the plugin shows, which rings ONCE. Said, not hidden: the looping sound
/// needs the installed app's identity, like the Deny button above.
pub fn notify_alarm(app: &AppHandle, title: &str, body: &str, snooze: Option<(&str, &str)>) {
    if is_uninstalled_build() {
        crate::commands::notify(app, title, body);
        return;
    }
    if let Err(e) = try_show(&alarm_xml(title, body, snooze)) {
        crate::logfile::log(&format!(
            "[jarvis] ringing toast failed, falling back to a plain one: {e}"
        ));
        crate::commands::notify(app, title, body);
    }
}

/// The XML of a toast without a sound and without buttons: an alarm or
/// reminder heard about more than ten minutes after it went off
/// (`brain/schedule.rs` `heard_late`, the owner's decision of 2026-09-26).
pub(crate) fn quiet_xml(title: &str, body: &str) -> String {
    format!(
        r#"<toast activationType="foreground" launch="jarvis-open">
  <visual>
    <binding template="ToastGeneric">
      <text>{title}</text>
      <text>{body}</text>
    </binding>
  </visual>
  <audio silent="true"/>
</toast>"#,
        title = escape_xml(title),
        body = escape_xml(body),
    )
}

/// Shows [`quiet_xml`], or the plugin's plain toast - which makes its one
/// usual sound - on an uninstalled build or if anything here fails.
pub fn notify_quiet(app: &AppHandle, title: &str, body: &str) {
    if is_uninstalled_build() {
        crate::commands::notify(app, title, body);
        return;
    }
    if let Err(e) = try_show(&quiet_xml(title, body)) {
        crate::logfile::log(&format!(
            "[jarvis] quiet toast failed, falling back to a plain one: {e}"
        ));
        crate::commands::notify(app, title, body);
    }
}

fn try_show(xml: &str) -> windows::core::Result<()> {
    let doc = XmlDocument::new()?;
    doc.LoadXml(&HSTRING::from(xml))?;
    let toast = ToastNotification::CreateToastNotification(&doc)?;
    let notifier = ToastNotificationManager::CreateToastNotifierWithId(&HSTRING::from(AUMID))?;
    notifier.Show(&toast)
}

/// Reads a Deny action's id out of a launch's argv, if this launch is one.
/// `None` for every ordinary launch and every ordinary second-instance
/// activation - the ONLY thing that produces this prefix is a click on the
/// button this module's own toast XML built.
///
/// An EMPTY id is `None`, not `Some("")`. `stream.rs` fills the toast's
/// `arguments` from `item["id"].as_str().unwrap_or_default()`, so a queue
/// row with no id at all produces the bare prefix `jarvis-deny:`. Returning
/// `Some("")` for that made the single-instance handler answer an approval
/// that does not exist and then return early - swallowing a real second
/// launch, whose only visible effect is that the window does not come up.
pub fn deny_id_from_argv(argv: &[String]) -> Option<&str> {
    argv.iter()
        .find_map(|a| a.strip_prefix(DENY_PREFIX))
        .filter(|id| !id.is_empty())
}

/// Answers a Deny reached this way through the same sending path the in-app
/// card and the quickbar use (`commands::deny_from_notification`, which ends
/// in the same function as `decide_approval`), not a second signing path -
/// and one that cannot approve, whatever it is handed. Runs on
/// its own task: the single-instance callback and [`decide_denied_at_startup`]
/// that call this are not `async` themselves, and a decision this shape must
/// not block whichever of those the app is currently inside.
pub fn decide_denied_detached(app: &AppHandle, id: &str) {
    let app = app.clone();
    let id = id.to_string();
    tauri::async_runtime::spawn(async move {
        // The same wait as a cold start (bug audit 2026-09-26, #2): a Deny
        // clicked while the link is reconnecting - after the PC wakes, or
        // the backend restarts, exactly when an old toast is likely to be
        // clicked - used to be refused and only logged. The toast has gone
        // by then, so the owner believed the card was denied.
        if !link_came_up(&app).await {
            crate::logfile::log(&format!(
                "[jarvis] notification Deny for {id} not sent: the event stream stayed stale"
            ));
            crate::commands::notify(&app, "Jarvis", &deny_not_sent_words(LINK_NEVER_CAME));
            return;
        }
        // No option: a toast Deny names no plan, and denying never needs to -
        // refusing all of them is one answer however many there are.
        if let Err(e) = crate::commands::deny_from_notification(app.clone(), id.clone()).await {
            crate::logfile::log(&format!(
                "[jarvis] notification Deny for {id} did not go through: {e}"
            ));
            crate::commands::notify(&app, "Jarvis", &deny_not_sent_words(&e));
        }
    });
}

/// Why a toast's button did nothing when the link never came back.
const LINK_NEVER_CAME: &str = "Jarvis's live link did not come back within 45 seconds";

/// What the toast says when a notification Deny could not be sent: that it
/// was NOT denied, why, and where the card still is. The reason is this
/// app's own sentence (`answer_approval`'s refusals, or the link wait above),
/// never the card's words.
pub fn deny_not_sent_words(why: &str) -> String {
    let why = why.trim().trim_end_matches('.');
    if why.is_empty() {
        return "Not denied. The card is still waiting in the Jarvis bar.".to_string();
    }
    format!("Not denied: {why}. The card is still waiting in the Jarvis bar.")
}

/// Waits for the event stream to be live, up to [`STARTUP_DENY_WAIT`]:
/// every decision or change is refused while it is stale (rule 4), and a
/// toast button is most often pressed right after a wake or a restart,
/// while the link is still coming back. `true` once it is live.
async fn link_came_up(app: &AppHandle) -> bool {
    let deadline = std::time::Instant::now() + STARTUP_DENY_WAIT;
    loop {
        if !app.state::<crate::stream::StreamState>().link().stale {
            return true;
        }
        if std::time::Instant::now() >= deadline {
            return false;
        }
        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
    }
}

/// How long a cold-start Deny waits for the event stream before giving up.
/// Long enough for the sidecar to come up and the stream to say hello on a
/// slow machine, short enough that a genuinely unreachable backend does not
/// leave a task sitting there for the life of the process.
const STARTUP_DENY_WAIT: std::time::Duration = std::time::Duration::from_secs(45);

/// A Deny clicked on a toast while Jarvis was NOT running.
///
/// This is the other half of the single-instance handler, and it did not
/// exist: `deny_id_from_argv` had exactly one caller, inside the
/// single-instance callback, which by design only fires when a process is
/// already up. So a Deny clicked on a toast after Jarvis had been closed
/// launched the app and answered nothing - silently paying the cost
/// `docs/ARCHITECTURE.md`'s rule 2 reserves for Approve ("Approving means
/// opening the app") while delivering the one thing rule 2 says a
/// notification IS allowed to do. This module's own doc claimed a startup
/// path for a while before one was here; now the claim is true.
///
/// It waits, rather than deciding immediately, because
/// the decision path (`commands::deny_from_notification`, like
/// `decide_approval`) refuses outright while the event stream is
/// stale - which it is on every cold start until the stream connects. Firing
/// straight away would have swapped a silent no-op for a logged one.
///
/// Answering is the whole job, and the window stays down while it happens -
/// but NOT because of anything in this function. `lib.rs`'s
/// `build_hud_window` is what decides that, and it needed a change to do it:
/// it built the HUD `.visible(true).focused(true)` for every launch that was
/// not a login start, so this one opened the full window and rule 2's "Deny
/// may be a notification action. Approve may not" was broken by the fix
/// meant to honour it. `launched_by_deny()` over there now reads the same
/// argv this does and hides the window exactly as a login start does.
///
/// Said explicitly because the first version of this comment claimed the
/// window was not raised while the code three files away was raising it.
pub fn decide_denied_at_startup(app: &AppHandle) {
    let argv: Vec<String> = std::env::args().collect();
    let Some(id) = deny_id_from_argv(&argv) else {
        return;
    };
    crate::logfile::log(&format!("[jarvis] Deny reached from a cold start: {id}"));
    // Waits for the link itself, and says so in a toast if it never comes.
    decide_denied_detached(app, id);
}

/// A timer, alarm or reminder that went off, with a "Snooze 10 minutes"
/// button (2026-09-25; `brain/schedule.rs` `toast_fired`). The same
/// foreground activation as Deny, so the same caveat: the button's relaunch
/// has not been watched on a real Windows PC. Anything failing here - or an
/// uninstalled build, which has no shortcut for the AUMID - falls back to
/// the plain toast without a button, the one shown before this existed;
/// Snooze is then in the Brain's Coming up, under "Just went off".
///
/// A snooze is not an approval: it only sets the same thing to go off once
/// more, later, and needs no card (the owner's rule for a one-off). The
/// button carries the job id only, never the words.
pub fn notify_fired(app: &AppHandle, title: &str, body: &str, id: &str, label: &str) {
    if is_uninstalled_build() {
        crate::commands::notify(app, title, body);
        return;
    }
    if let Err(e) = try_notify_fired(title, body, id, label) {
        crate::logfile::log(&format!(
            "[jarvis] snooze toast failed, falling back to a plain one: {e}"
        ));
        crate::commands::notify(app, title, body);
    }
}

fn try_notify_fired(title: &str, body: &str, id: &str, label: &str) -> windows::core::Result<()> {
    let xml = format!(
        r#"<toast activationType="foreground" launch="jarvis-open">
  <visual>
    <binding template="ToastGeneric">
      <text>{title}</text>
      <text>{body}</text>
    </binding>
  </visual>
  <actions>
    <action content="{label}" arguments="{prefix}{id}" activationType="foreground"/>
  </actions>
</toast>"#,
        title = escape_xml(title),
        body = escape_xml(body),
        label = escape_xml(label),
        prefix = SNOOZE_PREFIX,
        id = escape_xml(id),
    );
    let doc = XmlDocument::new()?;
    doc.LoadXml(&HSTRING::from(xml))?;
    let toast = ToastNotification::CreateToastNotification(&doc)?;
    let notifier = ToastNotificationManager::CreateToastNotifierWithId(&HSTRING::from(AUMID))?;
    notifier.Show(&toast)
}

/// A Snooze click's job id out of a launch's argv - `None` for every other
/// launch. Only a job id the PC makes ("s" and ten hex digits) counts.
pub fn snooze_id_from_argv(argv: &[String]) -> Option<&str> {
    argv.iter()
        .find_map(|a| a.strip_prefix(SNOOZE_PREFIX))
        .filter(|id| crate::brain::schedule::valid_id(id))
}

/// Sends the snooze on its own task, and says how it went in a toast - the
/// window is very likely not open when a toast button is pressed. Held on a
/// stale link like every change (`brain/schedule.rs` `snooze_from_toast`).
pub fn snooze_detached(app: &AppHandle, id: &str) {
    let app = app.clone();
    let id = id.to_string();
    tauri::async_runtime::spawn(async move {
        // The same wait as Deny. On a link that never comes back,
        // `snooze_from_toast` still refuses, and its toast says so.
        let _ = link_came_up(&app).await;
        crate::brain::schedule::snooze_from_toast(app, id).await;
    });
}

/// A Snooze clicked on a toast while Jarvis was CLOSED: the same wait for
/// the event stream as a cold-start Deny ([`decide_denied_at_startup`]),
/// because a change is refused while the link is stale.
pub fn snooze_at_startup(app: &AppHandle) {
    let argv: Vec<String> = std::env::args().collect();
    let Some(id) = snooze_id_from_argv(&argv) else {
        return;
    };
    crate::logfile::log(&format!("[jarvis] Snooze reached from a cold start: {id}"));
    snooze_detached(app, id);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_missed_alarm_is_shown_without_a_sound_or_a_button() {
        let xml = quiet_xml("Alarm", "Missed at 07:00. Wake <up>");
        assert!(xml.contains(r#"<audio silent="true"/>"#));
        assert!(!xml.contains("<action"));
        assert!(!xml.contains("Looping"));
        assert!(xml.contains("Wake &lt;up&gt;"));
    }

    #[test]
    fn a_deny_that_did_not_go_out_says_so_and_where_the_card_is() {
        let said = deny_not_sent_words("the event stream is stale.");
        assert_eq!(
            said,
            "Not denied: the event stream is stale. The card is still waiting in the Jarvis bar."
        );
        assert!(deny_not_sent_words("  ").starts_with("Not denied."));
        assert!(deny_not_sent_words(LINK_NEVER_CAME).contains("45 seconds."));
    }

    #[test]
    fn a_snooze_click_yields_one_job_id_and_nothing_else_does() {
        let argv = vec![
            "jarvis-desktop.exe".to_string(),
            "jarvis-snooze:s0123456789".to_string(),
        ];
        assert_eq!(snooze_id_from_argv(&argv), Some("s0123456789"));
        for bad in [
            "jarvis-snooze:",
            "jarvis-snooze:all",
            "jarvis-snooze:s0123",
            "jarvis-deny:s0123456789",
            "x-jarvis-snooze:s0123456789",
        ] {
            assert_eq!(snooze_id_from_argv(&[bad.to_string()]), None, "{bad}");
        }
        assert_eq!(deny_id_from_argv(&argv), None);
    }

    #[test]
    fn xml_special_characters_are_escaped() {
        assert_eq!(escape_xml("A & B"), "A &amp; B");
        assert_eq!(escape_xml("<script>"), "&lt;script&gt;");
        assert_eq!(escape_xml(r#"say "hi""#), "say &quot;hi&quot;");
    }

    #[test]
    fn a_ringing_toast_loops_until_dismissed_and_cannot_act() {
        let xml = alarm_xml("Tell me when", "An email from <Alex> & co arrived.", None);
        assert!(xml.contains(r#"scenario="alarm""#));
        assert!(xml
            .contains(r#"<audio src="ms-winsoundevent:Notification.Looping.Alarm" loop="true"/>"#));
        assert!(xml.contains(r#"activationType="system" arguments="dismiss""#));
        assert!(xml.contains("An email from &lt;Alex&gt; &amp; co arrived."));
        assert!(!xml.contains(DENY_PREFIX) && !xml.to_lowercase().contains("approve"));
        assert_eq!(xml.matches("<action ").count(), 1);
    }

    #[test]
    fn a_ringing_alarm_also_offers_snooze_with_its_id_only() {
        let xml = alarm_xml("Alarm", "Wake up", Some(("s0123456789", "Snooze")));
        assert!(xml.contains(r#"scenario="alarm""#));
        assert!(xml.contains(&format!(r#"arguments="{SNOOZE_PREFIX}s0123456789""#)));
        assert!(xml.contains(r#"activationType="system" arguments="dismiss""#));
        assert_eq!(xml.matches("<action ").count(), 2);
        assert!(!xml.contains(DENY_PREFIX) && !xml.to_lowercase().contains("approve"));
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

    /// The bare prefix with nothing after it. `stream.rs` builds the toast's
    /// `arguments` from `unwrap_or_default()`, so a queue row with no id
    /// produces exactly this - and answering "" is not a decision. It must
    /// read as "not a Deny relaunch" so the single-instance handler falls
    /// through and raises the window like any other second launch.
    #[test]
    fn an_empty_id_is_not_a_deny() {
        let argv = vec!["jarvis-desktop.exe".to_string(), "jarvis-deny:".to_string()];
        assert_eq!(deny_id_from_argv(&argv), None);
    }

    #[test]
    fn the_toast_offers_deny_and_never_approve() {
        for silent in [false, true] {
            let xml = approval_toast_xml("Jarvis wants to search the web", "Why.", "a1", silent);
            assert!(xml.contains(r#"<action content="Deny""#));
            assert!(!xml.to_lowercase().contains("approve"));
            assert_eq!(xml.matches("<action ").count(), 1);
            assert_eq!(xml.contains(r#"<audio silent="true"/>"#), silent);
        }
    }

    #[test]
    fn app_lock_s_title_only_toast_has_one_line() {
        let xml = approval_toast_xml("Jarvis wants to send an email", "", "a1", false);
        assert_eq!(xml.matches("<text>").count(), 1);
        assert!(xml.contains("<text>Jarvis wants to send an email</text>"));
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
