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
//! ## A click on a toast's BODY (2026-11-13) - measured, and what it means
//!
//! The owner reported that clicking the body of an approval toast did nothing,
//! and expected the ordinary Windows behaviour: the click opens the app, and
//! for an approval it opens that card. It really did nothing, and this PC can
//! show why:
//!
//! * the toast was in Windows' own notification store - id 2566, group
//!   `jarvis-approval`, 2026-11-13 17:51:50, the owner's exact words and the
//!   one Deny button - carrying `activationType="foreground"
//!   launch="jarvis-open"`;
//! * 34 seconds later Windows logged "Some toast notifications have been
//!   cleared" (the toast left the store, which is what a click or a dismissal
//!   produces), and `jarvis-desktop.log` records NO second launch and no
//!   folded second instance at that time. Nothing was started: the click
//!   reached Windows and stopped there;
//! * the Start Menu shortcuts carry the AppUserModelID this module claims
//!   (`com.jarvis.desktop`) and **no `ToastActivatorCLSID`** - read back
//!   through the shell's own shortcut properties, not assumed.
//!
//! Microsoft's own table for an unpackaged Win32 app is the other half:
//! visuals and **actions** are supported without a COM activator, and
//! in-process ("ongoing") activation is not. A body click carries no
//! `arguments` for Windows to launch a process with, so with no activator it
//! has nowhere to go; an action's `arguments` ARE that payload, which is the
//! shape every `*_from_argv` reader below already depends on, and the one the
//! owner did not report as broken (the Deny button). Said plainly: that action
//! half rests on the table and on the owner's report, not on a click this
//! session watched - the same limit the Deny path has always carried.
//!
//! So this module does the two things that can be done from inside the app, and
//! says what neither of them can achieve on its own:
//!
//! * every toast's body carries a `launch` marker, and
//!   [`open_request_from_argv`] answers it on BOTH activation paths (a running
//!   app's single-instance callback and a cold start) - so a body click does
//!   the right thing the moment Windows delivers one, and an approval's marker
//!   names its card so that click opens that card;
//! * an approval toast offers **Open** as an action, which rides exactly the
//!   activation `Deny` rides, so the owner has one press that opens the card.
//!
//! WHAT IS NOT DONE, AND WHY. Making the body click itself arrive needs the
//! installer to put a `ToastActivatorCLSID` on the Start Menu shortcut (in the
//! "stub CLSID" form of Microsoft's table, enough for launch activation; the
//! COM-activator form additionally needs an `INotificationActivationCallback`
//! server and a registry entry). That is install-time plumbing this change
//! does not add: it cannot be watched firing from here, and a wrong CLSID left
//! on a shortcut or in the registry outlives the app that wrote it - the
//! failure mode this module's doc already refuses for the Deny button. When
//! that plumbing lands, the two functions above answer it and no toast XML has
//! to change.
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

/// The argv marker the Stop button on a ringing toast carries - a timer,
/// alarm or reminder that went off (the owner's report of 2026-10-11: "theres
/// not turn off alarm, only a snooze in the notifcation"). Pressing it takes
/// that one toast away and does nothing else: it is the same job-scoped
/// silence the phone's own Stop button does, and it never reaches the backend
/// (which still shows the job under "Just went off" in the Brain's Coming up,
/// so a stopped alarm is not a lost one).
const STOP_PREFIX: &str = "jarvis-stop:";

/// The words on that button, both apps' - the phone's `ScheduleNotifier.STOP`
/// is the same word, and the two read as one control rather than two.
pub(crate) const STOP_LABEL: &str = "Stop";

/// The argv marker the Open button carries on a reminder that opens something
/// (2026-10-27, the owner's request): the SAME job id only, never the address
/// or the path. The PC reads the target back from its own answer and checks it
/// again (`reminder_open.rs`), so a launch argument cannot choose what opens.
///
/// NOT the body-click marker below, though the two words are close: this one
/// leads `jarvis-openjob:` and names a schedule job, that one leads
/// `jarvis-open` and names nothing or an approval card. One argv, one meaning -
/// [`open_request_from_argv`] must never answer this one.
const OPEN_PREFIX: &str = "jarvis-openjob:";

/// The marker a click on the BODY of one of this module's toasts carries: the
/// `<toast>` element's own `launch` attribute. With an approval card's id after
/// a colon (`jarvis-open:<id>`) it also names the card to open.
///
/// This is the one activation Windows has nowhere to deliver without a toast
/// activator - see this module's doc, which measured that on this PC. It is
/// written all the same: it costs nothing, and it is the half that will already
/// be right when the installer starts carrying the activator.
const OPEN_TOAST_PREFIX: &str = "jarvis-open";

/// The word on that button. "Open", never "Continue" or "Go": it says what
/// happens before it happens, and it is the same word the HUD's own row uses.
///
/// The approval toast's own Open action (2026-11-13) uses this word too: one
/// word for "open this in Jarvis", whichever notification carries it.
pub(crate) const OPEN_LABEL: &str = "Open";

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

/// The line every approval toast carries under the card's own words: where
/// the other half of the decision is, and why it cannot be here.
///
/// The owner reported this as a missing button (2026-10-11): a toast with
/// only Deny offered half a decision and never said where the other half
/// was. Approve cannot go on a notification at all - it is answered by
/// Windows Hello over the window that asked (docs/ARCHITECTURE.md §3, rule
/// 2) - so the toast has to say so instead of looking broken.
///
/// This is the toast's own short sentence. `jarvis-link.js`'s
/// [`APPROVE_WHERE`] names the surfaces the card waits on ("in the Jarvis
/// bar, on the widget, or on your phone's Home screen"); a toast has no room
/// for that list, and both say the same thing about the bar, which is where
/// this app's own "Not denied" sentence already points the owner.
const APPROVE_WHERE_TOAST: &str =
    "Deny here, or open Jarvis to approve - approving needs your Windows Hello.";

/// How many lines the card's own words may take in the toast. A compact toast
/// shows only a few lines, so an unbounded paragraph pushes everything after it
/// off the bottom - which is how the where-to-approve line went missing even
/// though it was in the XML. Two lines is enough to recognise the card; the
/// full words are on the card itself.
const BODY_MAX_LINES: u8 = 2;

/// The toast's XML. Open and Deny are the only actions, whatever the
/// arguments: Approve never goes on a notification (docs/ARCHITECTURE.md §3,
/// rule 2). An empty body (App lock: the title only) leaves out its line - and
/// the where-to-approve line with it, because that case says nothing else.
///
/// ORDER MATTERS, and the where-to-approve line goes SECOND (2026-10-13). It
/// used to be emitted after the card's own words, which meant a card with a
/// long body - most of them - consumed the toast's few visible lines and the
/// explanation was never seen. The owner saw exactly that: a body clipped
/// mid-word, one Deny button, and no sentence saying where the other half of
/// the decision was. Both defences are load-bearing: the line is second, and
/// the body is capped at [`BODY_MAX_LINES`].
///
/// OPEN CAME WITH THE BODY-CLICK REPORT (2026-11-13, see the module doc).
/// Windows does not deliver a click on the body of an unpackaged app's toast
/// without a toast activator, and this install has none, so the sentence
/// "open Jarvis to approve" described a gesture nothing could receive. Open is
/// that gesture as a real action - the activation Windows DOES route, the same
/// one Deny uses - and it carries the same marker the body does, so the two
/// cannot open different things. It is placed first because it is the decision
/// the sentence points at, and because the phone's own approval notification
/// puts Review before Deny. Deny's own XML is untouched.
fn approval_toast_xml(title: &str, body: &str, id: &str, silent: bool) -> String {
    // The where-to-approve line first, so it cannot be crowded out by a long
    // body; the body then takes what is left, bounded by BODY_MAX_LINES.
    let where_line = if body.trim().is_empty() {
        String::new()
    } else {
        format!("\n      <text>{APPROVE_WHERE_TOAST}</text>")
    };
    let body_line = if body.trim().is_empty() {
        String::new()
    } else {
        format!(
            "\n      <text hint-maxLines=\"{BODY_MAX_LINES}\">{}</text>",
            escape_xml(body)
        )
    };
    let audio = if silent {
        "\n  <audio silent=\"true\"/>"
    } else {
        ""
    };
    // ONE marker for the body click and for the Open action: the card's id
    // when this toast has one, so both open THAT card (and the Jarvis bar
    // fallback names it too - `commands::open_approval_in_quickbar`).
    let marker = escape_xml(&open_marker(id));
    format!(
        r#"<toast activationType="foreground" launch="{marker}">
  <visual>
    <binding template="ToastGeneric">
      <text>{title}</text>{where_line}{body_line}
    </binding>
  </visual>{audio}
  <actions>
    <action content="{open}" arguments="{marker}" activationType="foreground"/>
    <action content="Deny" arguments="{prefix}{id}" activationType="foreground"/>
  </actions>
</toast>"#,
        title = escape_xml(title),
        prefix = DENY_PREFIX,
        id = escape_xml(id),
        open = OPEN_LABEL,
    )
}

/// The `launch` marker a toast carries: the body-click marker on its own, or
/// with the approval card's id after a colon when the toast has one.
///
/// A card id that is not plain letters, digits, `-` or `_` still goes into the
/// XML (it is the PC's own id, and Deny carries it the same way) - but
/// [`open_request_from_argv`] will not read it back as a card. That click then
/// falls to the ordinary second-launch path: the window still comes up, and no
/// card this module could not name is opened by a launch argument.
fn open_marker(id: &str) -> String {
    if id.is_empty() {
        OPEN_TOAST_PREFIX.to_string()
    } else {
        format!("{OPEN_TOAST_PREFIX}:{id}")
    }
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
    // Tagged with the card's id so it can be taken away when the card leaves
    // the queue ([`remove_approval`]). A second toast for the same id replaces
    // the first instead of stacking.
    if !id.is_empty() {
        toast.SetTag(&HSTRING::from(id))?;
        toast.SetGroup(&HSTRING::from(APPROVAL_GROUP))?;
    }
    let notifier = ToastNotificationManager::CreateToastNotifierWithId(&HSTRING::from(AUMID))?;
    notifier.Show(&toast)
}

/// The group every approval toast is put in, tagged with the card's id.
const APPROVAL_GROUP: &str = "jarvis-approval";

/// Takes a card's toast away once the card is no longer waiting: decided on
/// this PC or the phone, timed out or cancelled (`stream.rs`, the same read
/// that tracks the pending queue). A toast left behind keeps a Deny button
/// that can only fail. Quiet when there is nothing to remove.
pub fn remove_approval(id: &str) {
    if is_uninstalled_build() || id.is_empty() {
        return;
    }
    let removed = ToastNotificationManager::History().and_then(|h| {
        h.RemoveGroupedTagWithId(
            &HSTRING::from(id),
            &HSTRING::from(APPROVAL_GROUP),
            &HSTRING::from(AUMID),
        )
    });
    if let Err(e) = removed {
        crate::logfile::log(&format!(
            "[jarvis] could not take the approval toast for {id} away: {e}"
        ));
    }
}

/// What a Deny click that did not go through means for the owner. Pure, so it
/// is tested.
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum DenyFailure {
    /// The card was already decided, expired or gone (the server's 409 from
    /// `/api/deny`): nothing is wrong, so nothing is shown but a quiet note.
    AlreadyDecided,
    /// Not sent; the owner is told the card is still waiting. `plain` is a
    /// sentence of this app's own, or empty - never the raw error text.
    NotSent { plain: String },
}

/// Sorts a `deny_from_notification` error. Raw system or server text (an
/// HTTP status and body, "unable to ...") is never passed on; this app's own
/// plain refusals (a stale stream) are.
pub(crate) fn classify_deny_failure(err: &str) -> DenyFailure {
    let e = err.trim();
    if e.contains("HTTP 409") {
        return DenyFailure::AlreadyDecided;
    }
    let raw = e.contains("HTTP ") || e.starts_with("unable to") || e.contains("os error");
    DenyFailure::NotSent {
        plain: if raw { String::new() } else { e.to_string() },
    }
}

/// The quiet words for a card that was already decided.
pub(crate) const ALREADY_DECIDED: &str = "Already decided.";

/// The XML of a toast that keeps ringing: an alarm, or an urgent "tell me
/// when" (backend jarvis_tellme.py; the owner's decision of 2026-09-25,
/// "alarms that keep ringing"). `scenario="alarm"` keeps it on screen
/// until it is dismissed, and its sound loops until then
/// (`Notification.Looping.Alarm`, `loop="true"`). Windows requires an
/// alarm toast to carry a button, and its own Dismiss
/// (`activationType="system"`) is kept LAST - it stops the sound and starts
/// nothing.
///
/// **Its label is written out (2026-10-11).** It used to be `content=""`,
/// on this file's own unverified claim that Windows renders its own word for
/// a system action. Nothing Windows stored agrees: Microsoft's own toasts in
/// the same store carry `arguments="dismiss" content="Dismiss"`, and every
/// "went off" toast this app had ever shown - 22 of them in the owner's own
/// store - carried no dismiss action at all. The owner, seeing exactly that,
/// reported "theres not turn off alarm, only a snooze in the notifcation".
/// So the button the owner presses is [`STOP_LABEL`], a labelled
/// `activationType="system"` action that removes this one toast and nothing
/// else; the ringing is unchanged (still `scenario="alarm"`, still the
/// looping alarm sound, still until dismissed or snoozed).
///
/// A timer, alarm or reminder going off also gets Snooze (`snooze`: the job
/// id and the button's words), the same button as [`notify_fired`]'s - it
/// carries the id only. There is no Approve here.
pub(crate) fn alarm_xml(title: &str, body: &str, snooze: Option<(&str, &str)>) -> String {
    // With no job id (an urgent "tell me when" carries one too, so this is
    // the belt-and-braces case) there is still a way out: the job-scoped Stop
    // falls back to Windows' own dismiss, which stops the sound.
    let stop = snooze
        .map(|(id, _)| {
            format!(
                r#"<action content="{label}" arguments="{prefix}{id}" activationType="system"/>
    "#,
                label = STOP_LABEL,
                prefix = STOP_PREFIX,
                id = escape_xml(id),
            )
        })
        .unwrap_or_default();
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
        r#"<toast scenario="alarm" activationType="foreground" launch="{marker}">
  <visual>
    <binding template="ToastGeneric">
      <text>{title}</text>
      <text>{body}</text>
    </binding>
  </visual>
  <audio src="ms-winsoundevent:Notification.Looping.Alarm" loop="true"/>
  <actions>
    {snooze}{stop}<action activationType="system" arguments="dismiss" content="Dismiss"/>
  </actions>
</toast>"#,
        title = escape_xml(title),
        body = escape_xml(body),
        marker = OPEN_TOAST_PREFIX,
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
    // Tagged with the job id when it has one (an alarm going off), so a
    // snooze or delete elsewhere stops it (`remove_fired`).
    if let Err(e) = try_show(&alarm_xml(title, body, snooze), snooze.map(|(id, _)| id)) {
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
        r#"<toast activationType="foreground" launch="{marker}">
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
        marker = OPEN_TOAST_PREFIX,
    )
}

/// Shows [`quiet_xml`], or the plugin's plain toast - which makes its one
/// usual sound - on an uninstalled build or if anything here fails.
pub fn notify_quiet(app: &AppHandle, title: &str, body: &str) {
    if is_uninstalled_build() {
        crate::commands::notify(app, title, body);
        return;
    }
    if let Err(e) = try_show(&quiet_xml(title, body), None) {
        crate::logfile::log(&format!(
            "[jarvis] quiet toast failed, falling back to a plain one: {e}"
        ));
        crate::commands::notify(app, title, body);
    }
}

fn try_show(xml: &str, job: Option<&str>) -> windows::core::Result<()> {
    let doc = XmlDocument::new()?;
    doc.LoadXml(&HSTRING::from(xml))?;
    let toast = ToastNotification::CreateToastNotification(&doc)?;
    if let Some(id) = job {
        tag_as_job(&toast, id)?;
    }
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
            crate::commands::notify(&app, "Atlas", &deny_not_sent_words(LINK_NEVER_CAME));
            return;
        }
        // No option: a toast Deny names no plan, and denying never needs to -
        // refusing all of them is one answer however many there are.
        if let Err(e) = crate::commands::deny_from_notification(app.clone(), id.clone()).await {
            crate::logfile::log(&format!(
                "[jarvis] notification Deny for {id} did not go through: {}",
                crate::crash_notes::scrub(&e)
            ));
            match classify_deny_failure(&e) {
                // Decided somewhere else first: no error toast, and the old
                // toast goes. A quiet note says why the click did nothing.
                DenyFailure::AlreadyDecided => {
                    remove_approval(&id);
                    if !crate::commands::toast_privacy_on(&app) {
                        notify_quiet(&app, "Atlas", ALREADY_DECIDED);
                    }
                }
                DenyFailure::NotSent { plain } => {
                    crate::commands::notify_guarded(
                        &app,
                        "Atlas",
                        &deny_not_sent_words(&plain),
                        None,
                    );
                }
            }
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
/// button and, since 2026-10-11, a "Stop" one (`brain/schedule.rs`
/// `toast_fired`; both in [`fired_xml`]). The same foreground activation as
/// Deny. Anything failing here - or an uninstalled build, which has no
/// shortcut for the AUMID - falls back to the plain toast without a button,
/// the one shown before this existed; Snooze is then in the Brain's Coming
/// up, under "Just went off".
///
/// A snooze is not an approval: it only sets the same thing to go off once
/// more, later, and needs no card (the owner's rule for a one-off). A stop is
/// not one either: it answers nothing and changes nothing, taking this one
/// notification away. Both buttons carry the job id only, never the words.
pub fn notify_fired(
    app: &AppHandle,
    title: &str,
    body: &str,
    id: &str,
    label: &str,
    open: Option<&str>,
) {
    if is_uninstalled_build() {
        crate::commands::notify(app, title, body);
        return;
    }
    if let Err(e) = try_notify_fired(title, body, id, label, open) {
        crate::logfile::log(&format!(
            "[jarvis] snooze toast failed, falling back to a plain one: {e}"
        ));
        crate::commands::notify(app, title, body);
    }
}

/// The XML of a toast that rang once and is over: a timer, alarm or reminder
/// that went off (`brain/schedule.rs` `toast_fired`), with the two buttons
/// the phone's own timer offers - Snooze ([`SNOOZE_PREFIX`]) and Stop
/// ([`STOP_PREFIX`]). Both carry the job id only, never the owner's words.
///
/// Stop is the owner's report of 2026-10-11: with Snooze alone, a timer that
/// had gone off could only be snoozed or clicked through into the app, and
/// **22 of the 22 "went off" toasts in the owner's own Windows store carried
/// Snooze and no other action** - no dismiss, nothing to take it away.
fn fired_xml(title: &str, body: &str, id: &str, label: &str, open: Option<&str>) -> String {
    // A reminder that opens something (2026-10-27) gets ONE more button, before
    // Snooze and Stop: it carries the job id only, and pressing it opens what
    // the notice names - never anything else. It is drawn only when the PC's own
    // answer says the target is still good (`brain/schedule.rs` `open_notice`),
    // so a button that cannot work is never offered.
    let open_action = match open {
        Some(job) => format!(
            r#"
    <action content="{label}" arguments="{prefix}{id}" activationType="foreground"/>"#,
            label = OPEN_LABEL,
            prefix = OPEN_PREFIX,
            id = escape_xml(job),
        ),
        None => String::new(),
    };
    format!(
        r#"<toast activationType="foreground" launch="{marker}">
  <visual>
    <binding template="ToastGeneric">
      <text>{title}</text>
      <text>{body}</text>
    </binding>
  </visual>
  <actions>{open_action}
    <action content="{label}" arguments="{prefix}{id}" activationType="foreground"/>
    <action content="{stop_label}" arguments="{stop_prefix}{id}" activationType="foreground"/>
  </actions>
</toast>"#,
        title = escape_xml(title),
        body = escape_xml(body),
        label = escape_xml(label),
        prefix = SNOOZE_PREFIX,
        id = escape_xml(id),
        stop_label = STOP_LABEL,
        stop_prefix = STOP_PREFIX,
        open_action = open_action,
        marker = OPEN_TOAST_PREFIX,
    )
}

fn try_notify_fired(
    title: &str,
    body: &str,
    id: &str,
    label: &str,
    open: Option<&str>,
) -> windows::core::Result<()> {
    let xml = fired_xml(title, body, id, label, open);
    let doc = XmlDocument::new()?;
    doc.LoadXml(&HSTRING::from(xml))?;
    let toast = ToastNotification::CreateToastNotification(&doc)?;
    tag_as_job(&toast, id)?;
    let notifier = ToastNotificationManager::CreateToastNotifierWithId(&HSTRING::from(AUMID))?;
    notifier.Show(&toast)
}

/// The group every "went off" toast is put in, tagged with its job id, so
/// [`remove_fired`] can take exactly that one away.
const SCHEDULE_GROUP: &str = "jarvis-schedule";

fn tag_as_job(toast: &ToastNotification, id: &str) -> windows::core::Result<()> {
    toast.SetTag(&HSTRING::from(id))?;
    toast.SetGroup(&HSTRING::from(SCHEDULE_GROUP))
}

/// Takes a job's "went off" toast away - a ringing alarm stops with it -
/// when the PC says the job changed: snoozed, deleted or done on the phone,
/// by voice or in the Brain (the phone does the same with its notification;
/// bug audit 2026-09-26, phone #1, mirrored here). A plain toast shown by
/// the plugin has no tag and stays; it does not ring.
pub fn remove_fired(id: &str) {
    if is_uninstalled_build() {
        return;
    }
    let removed = ToastNotificationManager::History().and_then(|h| {
        h.RemoveGroupedTagWithId(
            &HSTRING::from(id),
            &HSTRING::from(SCHEDULE_GROUP),
            &HSTRING::from(AUMID),
        )
    });
    if let Err(e) = removed {
        crate::logfile::log(&format!(
            "[jarvis] could not take the toast for {id} away: {e}"
        ));
    }
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
    // An Open click arrives on the same launch path and must be answered FIRST:
    // it acts (it opens a page or a file), where Snooze only sets a time.
    if let Some(id) = open_id_from_argv(&argv) {
        crate::logfile::log(&format!("[jarvis] Open reached from a cold start: {id}"));
        open_detached(app, id);
        return;
    }
    let Some(id) = snooze_id_from_argv(&argv) else {
        return;
    };
    crate::logfile::log(&format!("[jarvis] Snooze reached from a cold start: {id}"));
    snooze_detached(app, id);
}

/// An Open click's job id out of a launch's argv - `None` for every other
/// launch. The same `s`-and-ten-hex-digits id the other two take, and the same
/// "the prefix must lead the argument" rule.
pub fn open_id_from_argv(argv: &[String]) -> Option<&str> {
    argv.iter()
        .find_map(|a| a.strip_prefix(OPEN_PREFIX))
        .filter(|id| crate::brain::schedule::valid_id(id))
}

/// Sends the open on its own task: the window is very likely not open when a
/// toast button is pressed. It goes through the SAME command the HUD's Open
/// button uses ([`crate::reminder_open::open_reminder_target`]), so both doors
/// re-read the job and re-check the target in exactly one place - and both are
/// held on a stale link, because opening is acting.
pub fn open_detached(app: &AppHandle, id: &str) {
    let app = app.clone();
    let id = id.to_string();
    tauri::async_runtime::spawn(async move {
        let _ = link_came_up(&app).await;
        if let Err(e) = crate::reminder_open::open_reminder_target(app.clone(), id).await {
            // One sentence, in a toast: a click that did nothing would read as
            // a broken button ("a silent failure looks like a broken feature",
            // open_app.rs). The same words the HUD shows.
            //
            // P-5 of the 2026-10-27 privacy audit: `e` is the PC's own
            // `action_problem` sentence, so these are SERVER words - and a
            // toast is the one surface that can be read over a shoulder while
            // App lock or "Hide memory lists and chat history" is on. Today it
            // names no path or file; the first time it does, this is the leak.
            // So the toast goes through the guarded door: the same sentence
            // while the lock is off, and a fixed line - plus the log, scrubbed
            // - while it is on.
            crate::logfile::log(&format!(
                "[jarvis] a reminder could not be opened: {}",
                crate::crash_notes::scrub(e.trim())
            ));
            let locked_body = format!(
                "That reminder could not be opened. {}",
                crate::commands::DETAILS_IN_LOG
            );
            crate::commands::notify_guarded(&app, "Atlas", &e, Some(&locked_body));
        }
    });
}

/// A Stop click's job id out of a launch's argv - `None` for every other
/// launch. The same `s`-and-ten-hex-digits id [`snooze_id_from_argv`] takes,
/// and the same "the prefix must lead the argument" rule.
pub fn stop_id_from_argv(argv: &[String]) -> Option<&str> {
    argv.iter()
        .find_map(|a| a.strip_prefix(STOP_PREFIX))
        .filter(|id| crate::brain::schedule::valid_id(id))
}

/// Stops ONE ringing "went off" toast: the toast with this job id goes, and
/// nothing else happens - no route, no card, no state change, exactly what
/// the phone's own Stop button does ([`ScheduleNotifier.stopRinging`]). This
/// is why it can run without waiting for the event stream: it answers
/// nothing, so a stale link cannot make it silently do the wrong thing.
pub fn stop_detached(id: &str) {
    remove_fired(id);
    crate::logfile::log(&format!("[jarvis] Stop pressed on {id}'s toast"));
}

/// A Stop clicked on a toast while Jarvis was CLOSED. The single-instance
/// callback above only fires with a process already running, so a cold start
/// is the only place this launch can be seen - and, like Snooze, it must not
/// leave a window up for a click that asks for nothing.
pub fn stop_at_startup(app: &AppHandle) {
    let argv: Vec<String> = std::env::args().collect();
    let Some(id) = stop_id_from_argv(&argv) else {
        return;
    };
    let _ = app;
    stop_detached(id);
}

// ---------------------------------------------------------------------------
// A click on a toast's BODY, and the Open action beside Deny (2026-11-13)
// ---------------------------------------------------------------------------

/// What a click on the BODY of one of this module's toasts asks for: the
/// `<toast>`'s own `launch` attribute. See this module's doc for what Windows
/// does and does not deliver here on this PC, and why the Open action exists.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum ToastOpen {
    /// No card named - a timer, an alarm, a "heard late" notice, or an
    /// approval whose toast had no id. Bring Jarvis forward.
    Window,
    /// An approval's card id. Bring Jarvis forward AND open that card, through
    /// the same command Settings' "Open the card" button calls.
    Card(String),
}

/// The longest card id a launch argument may name - the same cap
/// `commands::open_approval_in_quickbar` puts on an id a page sends.
const MAX_CARD_ID: usize = 200;

/// Whether `id` is a card id a launch argument may name: non-empty, short, and
/// letters, digits, `-` or `_` only.
///
/// The id is only ever handed to `open_approval_in_quickbar`, which decides
/// nothing and opens no window of its own - but a launch argument is written by
/// whoever launched the process, so it is not given a free shape to carry.
fn card_id_ok(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= MAX_CARD_ID
        && id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
}

/// Reads a body click's request out of a launch's argv. `None` for every
/// ordinary launch, and for every OTHER toast button's launch: `jarvis-deny:`,
/// `jarvis-snooze:`, `jarvis-stop:` and `jarvis-openjob:` each have their own
/// reader above, and one argv must have exactly one meaning.
pub(crate) fn open_request_from_argv(argv: &[String]) -> Option<ToastOpen> {
    argv.iter().find_map(|arg| {
        let rest = arg.strip_prefix(OPEN_TOAST_PREFIX)?;
        if rest.is_empty() {
            // The marker on its own: a toast that names no card.
            return Some(ToastOpen::Window);
        }
        let id = rest.strip_prefix(':')?;
        // `jarvis-openjob:` lands here with "job:..." and is refused by the
        // colon check - the reminder's Open button is not a body click.
        card_id_ok(id).then(|| ToastOpen::Card(id.to_string()))
    })
}

/// The surface an approval's Open asks for. `"hud"` is the value
/// [`crate::commands::card_open_target`] maps to the full HUD window - the
/// surface that shows the whole card with its own Approve and Deny, and the
/// one `card-link.js` already asks for.
const CARD_TARGET: &str = "hud";

/// Answers a body click, or the Open action, on one of this module's toasts.
///
/// Deliberately NOT a new way to focus a window. A click that names no card
/// goes through [`crate::windows::show_hud`] - the one door the tray, the
/// hotkey and an ordinary second launch already use, so the window is
/// un-minimised and focused exactly as those do it. An approval goes through
/// [`crate::commands::open_approval_in_quickbar`], the SAME command
/// `card-link.js`'s "Open the card" button calls with the same `"hud"` target,
/// so the two cannot open different surfaces.
///
/// Decides nothing: the card still needs its own Approve and its Windows
/// Hello, and the App-lock rule still applies inside both doors.
pub(crate) fn open_from_toast(app: &AppHandle, request: &ToastOpen) {
    let opened = match request {
        ToastOpen::Window => crate::windows::show_hud(app),
        ToastOpen::Card(id) => crate::commands::open_approval_in_quickbar(
            app.clone(),
            Some(id.clone()),
            Some(CARD_TARGET.to_string()),
        ),
    };
    if let Err(e) = opened {
        // Logged, not toasted: a toast about a toast that could not open is
        // noise, and the owner is already looking at the notification.
        crate::logfile::log(&format!(
            "[jarvis] a notification click could not open Jarvis: {e}"
        ));
    }
}

/// A body click (or Open) that STARTED this process.
///
/// The single-instance callback only fires when a process is already running -
/// the same gap the Deny button had, and the reason `decide_denied_at_startup`
/// exists. Without this, a click on a toast that started Jarvis opened the
/// window and then did nothing about what was clicked, including an approval's
/// card.
pub fn open_at_startup(app: &AppHandle) {
    let argv: Vec<String> = std::env::args().collect();
    let Some(request) = open_request_from_argv(&argv) else {
        return;
    };
    crate::logfile::log("[jarvis] a notification click started Jarvis");
    open_from_toast(app, &request);
}

#[cfg(test)]
mod tests {
    use super::*;

    /// One function's body, from its signature to the first line that closes
    /// it, so a pin can hold a CALL rather than the whole file (the shape
    /// `notifications.rs` uses for the same job).
    fn body<'a>(src: &'a str, name: &str) -> &'a str {
        let at = src
            .find(name)
            .unwrap_or_else(|| panic!("{name} is gone from this file"));
        let rest = &src[at..];
        let end = rest
            .find("\n}\n")
            .expect("that function has no closing line");
        &rest[..end]
    }

    #[test]
    fn a_missed_alarm_is_shown_without_a_sound_or_a_button() {
        let xml = quiet_xml("Alarm", "Missed at 07:00. Wake <up>");
        assert!(xml.contains(r#"<audio silent="true"/>"#));
        assert!(!xml.contains("<action"));
        assert!(!xml.contains("Looping"));
        assert!(xml.contains("Wake &lt;up&gt;"));
    }

    #[test]
    fn a_deny_on_a_card_already_decided_is_not_an_error() {
        assert_eq!(
            classify_deny_failure("the server answered HTTP 409 to /deny: {\"error\":\"gone\"}"),
            DenyFailure::AlreadyDecided
        );
        // Any other raw failure is "not sent" with no raw text passed on.
        assert_eq!(
            classify_deny_failure("the server answered HTTP 500 to /deny: Traceback in C:/x.py"),
            DenyFailure::NotSent {
                plain: String::new()
            }
        );
        assert_eq!(
            classify_deny_failure("unable to deny `a`: connection reset (os error 10054)"),
            DenyFailure::NotSent {
                plain: String::new()
            }
        );
        // This app's own plain sentence is kept.
        assert_eq!(
            classify_deny_failure("the event stream is stale, so nothing can be answered"),
            DenyFailure::NotSent {
                plain: "the event stream is stale, so nothing can be answered".to_string()
            }
        );
        assert!(!ALREADY_DECIDED.to_lowercase().contains("error"));
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
        // Windows' own dismiss, and nothing else: an id-less ring has no job
        // to stop, and a labelled Stop with no id would stop the wrong thing.
        assert_eq!(xml.matches("<action ").count(), 1);
        assert!(!xml.contains(STOP_PREFIX));
    }

    /// The owner's report of 2026-10-11, as a test: the toast that keeps
    /// ringing must carry a button whose word a person can read. It used to
    /// carry `content=""`, which is a button with no label at all.
    #[test]
    fn a_ringing_alarm_s_way_out_is_a_labelled_stop_and_windows_dismiss() {
        let xml = alarm_xml(
            "Alarm",
            "Wake up",
            Some(("s0123456789", "Snooze 10 minutes")),
        );
        assert!(xml.contains(r#"scenario="alarm""#));
        assert!(xml.contains(r#"<action content="Stop" arguments="jarvis-stop:s0123456789" activationType="system"/>"#));
        assert!(xml.contains(
            r#"<action activationType="system" arguments="dismiss" content="Dismiss"/>"#
        ));
        assert_eq!(xml.matches("<action ").count(), 3);
        // The old shape, exactly: no action may be left without a word.
        assert!(
            !xml.contains(r#"content="""#),
            "an action still has no label:\n{xml}"
        );
        assert!(!xml.contains(DENY_PREFIX) && !xml.to_lowercase().contains("approve"));
    }

    #[test]
    fn a_ringing_alarm_also_offers_snooze_with_its_id_only() {
        let xml = alarm_xml("Alarm", "Wake up", Some(("s0123456789", "Snooze")));
        assert!(xml.contains(r#"scenario="alarm""#));
        assert!(xml.contains(&format!(r#"arguments="{SNOOZE_PREFIX}s0123456789""#)));
        assert!(xml.contains(r#"activationType="system" arguments="dismiss""#));
        // Snooze, Stop and Windows' dismiss.
        assert_eq!(xml.matches("<action ").count(), 3);
        assert!(!xml.contains(DENY_PREFIX) && !xml.to_lowercase().contains("approve"));
    }

    /// CONTROL: a one-off timer's toast offers BOTH things a person needs -
    /// Snooze to be reminded again, Stop to be rid of it - and neither can
    /// ever approve anything.
    #[test]
    fn a_timer_that_went_off_offers_snooze_and_stop() {
        let xml = fired_xml(
            "Timer done",
            "Jarvis: your timer is done.",
            "s0123456789",
            "Snooze 10 minutes",
            None,
        );
        assert!(xml.contains(r#"<action content="Snooze 10 minutes" arguments="jarvis-snooze:s0123456789" activationType="foreground"/>"#));
        assert!(xml.contains(r#"<action content="Stop" arguments="jarvis-stop:s0123456789" activationType="foreground"/>"#));
        assert_eq!(xml.matches("<action ").count(), 2);
        assert!(!xml.contains(r#"content="""#));
        assert!(!xml.contains(DENY_PREFIX) && !xml.to_lowercase().contains("approve"));
        // Still no sound of its own and no alarm scenario: this one has
        // already rung once and must not start ringing now.
        assert!(!xml.contains("scenario="));
        assert!(!xml.contains("Looping"));
    }

    /// A reminder that opens something (2026-10-27): ONE more button, carrying
    /// the job id only - never the address or the path - and it can approve
    /// nothing. The target is named in the notice, so the owner reads what will
    /// open BEFORE pressing it.
    #[test]
    fn a_reminder_that_opens_something_offers_an_open_button_with_the_id_only() {
        let xml = fired_xml(
            "Reminder",
            "Open this invoice. This opens: https://example.com/invoice-42",
            "s0123456789",
            "Snooze 10 minutes",
            Some("s0123456789"),
        );
        assert!(xml.contains(&format!(
            r#"<action content="{OPEN_LABEL}" arguments="{OPEN_PREFIX}s0123456789" activationType="foreground"/>"#
        )));
        assert!(xml.contains("https://example.com/invoice-42"));
        // Open, Snooze and Stop - and no fourth thing.
        assert_eq!(xml.matches("<action ").count(), 3);
        assert!(!xml.contains(r#"content="""#));
        assert!(!xml.contains(DENY_PREFIX) && !xml.to_lowercase().contains("approve"));
        // No open id, no Open button: the timer and alarm toasts are unchanged.
        let plain = fired_xml("Timer done", "Done.", "s0123456789", "Snooze", None);
        assert!(!plain.contains(OPEN_PREFIX));
        assert_eq!(plain.matches("<action ").count(), 2);
    }

    #[test]
    fn an_open_click_yields_one_job_id_and_nothing_else_does() {
        let argv = vec![
            "jarvis-desktop.exe".to_string(),
            "jarvis-openjob:s0123456789".to_string(),
        ];
        assert_eq!(open_id_from_argv(&argv), Some("s0123456789"));
        // Never a made-up id, and never one the prefix does not lead.
        for bad in [
            "jarvis-openjob:not-an-id",
            "xjarvis-openjob:s0123456789",
            "jarvis-openjob:",
            "jarvis-snooze:s0123456789",
            "https://example.com",
            "C:\\Users\\pcadmin\\Pictures\\taxes.png",
        ] {
            let argv = vec!["jarvis-desktop.exe".to_string(), bad.to_string()];
            assert_eq!(open_id_from_argv(&argv), None, "{bad}");
        }
    }

    #[test]
    fn a_stop_click_yields_one_job_id_and_nothing_else_does() {
        let argv = vec![
            "jarvis-desktop.exe".to_string(),
            "jarvis-stop:s0123456789".to_string(),
        ];
        assert_eq!(stop_id_from_argv(&argv), Some("s0123456789"));
        for bad in [
            "jarvis-stop:",
            "jarvis-stop:all",
            "jarvis-stop:s0123",
            "jarvis-deny:s0123456789",
            "jarvis-snooze:s0123456789",
            "x-jarvis-stop:s0123456789",
        ] {
            assert_eq!(stop_id_from_argv(&[bad.to_string()]), None, "{bad}");
        }
        // The two other buttons' readers must not answer a Stop, and this one
        // must not answer theirs - one argv, exactly one meaning.
        assert_eq!(snooze_id_from_argv(&argv), None);
        assert_eq!(deny_id_from_argv(&argv), None);
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
    fn the_toast_offers_open_and_deny_and_never_approve() {
        // Two actions since 2026-11-13: Open (which opens the card in Jarvis,
        // the gesture the body click cannot carry - see the module doc) and
        // Deny. Neither approves anything.
        for silent in [false, true] {
            let xml = approval_toast_xml("Jarvis wants to search the web", "Why.", "a1", silent);
            assert!(xml.contains(r#"<action content="Deny""#));
            assert!(xml.contains(&format!(r#"<action content="{OPEN_LABEL}""#)));
            assert_eq!(xml.matches("<action ").count(), 2);
            assert_eq!(xml.contains(r#"<audio silent="true"/>"#), silent);
        }
    }

    #[test]
    fn every_approval_toast_says_where_to_approve_and_never_offers_it() {
        // BOTH HALVES, and the second is the one that matters most.
        //
        // The first is the owner's report of 2026-10-11: a toast with only
        // Deny looked like a missing button, because nothing on it said where
        // the other half of the decision was.
        //
        // The second is the rule the fix has to leave standing: a notification
        // never approves anything (docs/ARCHITECTURE.md §3, rule 2).
        // Approving is answered by Windows Hello over the window that asked,
        // and a toast cannot ask for it. A later reader who sees "there is no
        // Approve button" as a bug and reaches for one has to get past this
        // test, so it says why they must not.
        for silent in [false, true] {
            let xml = approval_toast_xml(
                "Jarvis wants to raise a chatbot's monthly spending limit",
                "Why.",
                "a1",
                silent,
            );
            assert!(
                xml.contains(APPROVE_WHERE_TOAST),
                "the toast must say where the card can be approved:\n{xml}"
            );
            assert_eq!(
                xml.matches("<action ").count(),
                2,
                "a notification carries Open and Deny, and nothing else:\n{xml}"
            );
            let actions = xml.split("<actions>").nth(1).unwrap_or_default();
            assert!(
                !actions.to_lowercase().contains("approve"),
                "a notification must never carry an approving action - Windows \
                 Hello cannot be asked for from a toast:\n{xml}"
            );
            // And Open is not an approving action: it opens the card, where
            // the card's own Approve and Windows Hello still are.
            assert!(
                actions.contains(&format!(r#"content="{OPEN_LABEL}""#)),
                "the Open action is gone, so the toast's own sentence points at \
                 a gesture Windows cannot deliver:\n{xml}"
            );
        }
    }

    #[test]
    fn app_lock_s_title_only_toast_has_one_line() {
        // App lock's toast is the title only: no card words, and no
        // where-to-approve line either, because that case deliberately says
        // nothing else.
        let xml = approval_toast_xml("Jarvis wants to send an email", "", "a1", false);
        assert_eq!(xml.matches("<text>").count(), 1);
        assert!(xml.contains("<text>Jarvis wants to send an email</text>"));
        assert!(!xml.contains(APPROVE_WHERE_TOAST));
    }

    #[test]
    fn a_long_body_cannot_crowd_the_where_to_approve_line_out_of_the_toast() {
        // THE TEST THAT WAS MISSING, and the reason the 2026-10-11 fix shipped
        // broken. `every_approval_toast_says_where_to_approve_and_never_offers_it`
        // only asserts the sentence is IN the XML - which stays true while the
        // sentence is invisible, because a compact toast shows only its first
        // few lines. That is exactly what the owner's screenshot showed: a body
        // clipped mid-word, one Deny button, and no explanation.
        //
        // So this one asserts the two things that decide whether the sentence is
        // SEEN, not whether it is present:
        //   1. the explanation is emitted before the card's own words, so the
        //      body is the element that gets clipped; and
        //   2. the body's lines are capped, so it cannot take the whole toast
        //      even when the ordering is right.
        // Break either one and this test goes red - see the PR body for the
        // deliberately-broken run.
        let long_body = "Jarvis wants to turn on automatic learning. This changes \
                         how Jarvis remembers things across every conversation, and \
                         it takes effect immediately. Nothing has happened yet: your \
                         approval is what makes it happen.";
        let xml = approval_toast_xml(
            "Jarvis wants to turn on automatic learning",
            long_body,
            "a1",
            false,
        );

        assert!(
            xml.contains(APPROVE_WHERE_TOAST),
            "the toast must carry the where-to-approve sentence:\n{xml}"
        );
        let where_at = xml
            .find(APPROVE_WHERE_TOAST)
            .expect("the sentence is asserted present just above");
        let body_at = xml
            .find(long_body)
            .expect("the card's own words must be in the toast");
        assert!(
            where_at < body_at,
            "the where-to-approve sentence must come BEFORE the card's own words, or a \
             long body pushes it out of the visible lines - which is the bug this test \
             exists for:\n{xml}"
        );
        assert!(
            xml.contains(&format!("hint-maxLines=\"{BODY_MAX_LINES}\"")),
            "the card's own words must be bounded to {BODY_MAX_LINES} lines so they cannot \
             take the whole toast:\n{xml}"
        );
        assert!(
            xml.contains(&format!(
                "hint-maxLines=\"{BODY_MAX_LINES}\">{long_body}</text>"
            )),
            "the bound must be on the card's words themselves:\n{xml}"
        );
        // ...and the rule this module exists to keep still holds.
        assert_eq!(xml.matches("<action ").count(), 2, "{xml}");
        assert!(!xml
            .split("<actions>")
            .nth(1)
            .unwrap_or_default()
            .to_lowercase()
            .contains("approve"));
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

    #[test]
    fn a_server_worded_failure_toast_goes_through_the_guarded_door() {
        // P-5 of the 2026-10-27 privacy audit. An Open click's failure toast
        // carries the PC's own `action_problem` sentence: SERVER words, on the
        // one surface a person standing behind the owner can read without
        // touching anything. Today it names no path or file; the pattern is
        // what this pins, so the day the PC's sentence grows a file name it
        // cannot reach a toast while App lock or the hidden lists is on.
        let src = include_str!("winrt_toast.rs");
        let start = src
            .find("pub fn open_detached")
            .expect("the Open click's own task");
        let rest = &src[start..];
        let end = rest.find("\n}\n").expect("the end of that function");
        let body = &rest[..end];
        assert!(
            body.contains("notify_guarded("),
            "the Open failure toast no longer goes through the guarded door, so the PC's \
             own sentence reaches a toast whatever the lock says:\n{body}"
        );
        assert!(
            !body.contains("commands::notify("),
            "the Open failure toast calls the unguarded notify again:\n{body}"
        );
        // The raw sentence is not lost: it goes to the log, scrubbed.
        assert!(
            body.contains("crash_notes::scrub"),
            "the PC's own sentence is neither shown safely nor logged scrubbed:\n{body}"
        );
    }

    // -----------------------------------------------------------------------
    // A click on the BODY, and the Open action (2026-11-13)
    // -----------------------------------------------------------------------

    /// The owner's report of 2026-11-13, as a test. "Deny here, or open Jarvis
    /// to approve" described a gesture Windows cannot deliver to this app (the
    /// module doc measures it), so the toast now carries the gesture as an
    /// action - and the action and the body click name the SAME marker, so the
    /// two can never open different things.
    #[test]
    fn the_approval_toast_s_open_action_opens_the_card_and_never_approves() {
        let id = "07653f169571";
        let xml = approval_toast_xml(
            "Jarvis wants to forget what it learned and delete chats from the days you chose",
            "forgets the facts and deletes the chats listed on the card.",
            id,
            false,
        );
        // Deny is untouched: the same words, the same arguments, the same
        // activation type it has always had.
        assert!(
            xml.contains(&format!(
                r#"<action content="Deny" arguments="{DENY_PREFIX}{id}" activationType="foreground"/>"#
            )),
            "the Deny button changed shape:\n{xml}"
        );
        // The one new press: Open, with the same marker a body click carries.
        assert!(
            xml.contains(&format!(
                r#"<action content="{OPEN_LABEL}" arguments="{OPEN_TOAST_PREFIX}:{id}" activationType="foreground"/>"#
            )),
            "the Open action is not on the toast, so the sentence points at a \
             gesture Windows cannot deliver:\n{xml}"
        );
        // ...and the body click's own marker names the same card.
        assert!(
            xml.contains(&format!(
                r#"<toast activationType="foreground" launch="{OPEN_TOAST_PREFIX}:{id}">"#
            )),
            "the body click's marker does not name the card:\n{xml}"
        );
        // Exactly those two, and neither approves anything.
        assert_eq!(xml.matches("<action ").count(), 2, "{xml}");
        let actions = xml
            .split("<actions>")
            .nth(1)
            .unwrap_or_default()
            .to_lowercase();
        assert!(!actions.contains("approve"), "{xml}");
        assert!(!actions.contains(SNOOZE_PREFIX), "{xml}");
        assert!(!actions.contains(STOP_PREFIX), "{xml}");
    }

    /// A queue row with no id still gets a working Open and a body marker -
    /// the bare marker, never a colon with nothing after it (`jarvis-open:` is
    /// not a request this module can read back).
    #[test]
    fn an_id_less_approval_still_gets_a_working_open_and_a_body_marker() {
        let xml = approval_toast_xml("Jarvis wants to restart", "", "", false);
        assert!(
            xml.contains(&format!(
                r#"<toast activationType="foreground" launch="{OPEN_TOAST_PREFIX}">"#
            )),
            "{xml}"
        );
        assert!(
            xml.contains(&format!(
                r#"<action content="{OPEN_LABEL}" arguments="{OPEN_TOAST_PREFIX}" activationType="foreground"/>"#
            )),
            "{xml}"
        );
        assert!(!xml.contains(&format!("{OPEN_TOAST_PREFIX}:")), "{xml}");
        assert_eq!(xml.matches("<action ").count(), 2, "{xml}");
    }

    /// One argv, exactly one meaning. A body click names either the window or
    /// ONE card; every other button's marker - and anything a launcher could
    /// invent - reads as "not a body click", so the single-instance handler
    /// falls through to the ordinary second-launch path.
    #[test]
    fn a_body_click_names_a_window_or_one_card_and_nothing_else() {
        assert_eq!(
            open_request_from_argv(&["jarvis-desktop.exe".to_string()]),
            None
        );
        assert_eq!(
            open_request_from_argv(&[
                "jarvis-desktop.exe".to_string(),
                OPEN_TOAST_PREFIX.to_string()
            ]),
            Some(ToastOpen::Window)
        );
        assert_eq!(
            open_request_from_argv(&[
                "jarvis-desktop.exe".to_string(),
                format!("{OPEN_TOAST_PREFIX}:07653f169571"),
            ]),
            Some(ToastOpen::Card("07653f169571".to_string()))
        );
        // An id with a hyphen or an underscore is still one card: the gate's
        // ids are strings, and a test fixture already looks like `appr_abc123`.
        for id in ["appr_abc123", "07653f169571", "a-b_c"] {
            assert_eq!(
                open_request_from_argv(&[format!("{OPEN_TOAST_PREFIX}:{id}")]),
                Some(ToastOpen::Card(id.to_string())),
                "{id}"
            );
        }
        // The OTHER buttons' markers are not body clicks, and neither is a
        // marker that does not lead the argument.
        for other in [
            "jarvis-deny:07653f169571".to_string(),
            "jarvis-snooze:s0123456789".to_string(),
            "jarvis-stop:s0123456789".to_string(),
            "jarvis-openjob:s0123456789".to_string(),
            format!("x{OPEN_TOAST_PREFIX}:07653f169571"),
        ] {
            assert_eq!(
                open_request_from_argv(std::slice::from_ref(&other)),
                None,
                "{other}"
            );
        }
        // A card id this module would not hand the command is not a card.
        for bad in [
            format!("{OPEN_TOAST_PREFIX}:"),
            format!("{OPEN_TOAST_PREFIX}:../x"),
            format!("{OPEN_TOAST_PREFIX}:a b"),
            format!("{OPEN_TOAST_PREFIX}:a:b"),
            format!("{OPEN_TOAST_PREFIX}:a/b"),
        ] {
            assert_eq!(
                open_request_from_argv(std::slice::from_ref(&bad)),
                None,
                "{bad}"
            );
        }
        assert_eq!(
            open_request_from_argv(&[format!(
                "{OPEN_TOAST_PREFIX}:{}",
                "a".repeat(MAX_CARD_ID + 1)
            )]),
            None,
            "an over-long id is not a card this app will name"
        );
    }

    /// The marker WRITTEN into every toast is the marker the reader looks for -
    /// a round trip, so a rename on one side cannot leave the other silent.
    #[test]
    fn the_marker_in_every_toast_is_the_one_the_reader_looks_for() {
        let launch_of = |xml: &str| -> String {
            xml.split("launch=\"")
                .nth(1)
                .expect("every toast carries a launch marker")
                .split('"')
                .next()
                .expect("the attribute value ends")
                .to_string()
        };
        // An approval names its card...
        let approval = approval_toast_xml("Jarvis wants to restart", "Why.", "07653f169571", false);
        let marker = launch_of(&approval);
        assert_eq!(
            open_request_from_argv(std::slice::from_ref(&marker)),
            Some(ToastOpen::Card("07653f169571".to_string())),
            "{marker}"
        );
        // ...and the toasts that name no card ask for the window.
        for xml in [
            quiet_xml("Alarm", "Missed at 07:00."),
            alarm_xml("Alarm", "Wake up", Some(("s0123456789", "Snooze"))),
            fired_xml("Timer done", "Done.", "s0123456789", "Snooze", None),
            approval_toast_xml("Jarvis wants to restart", "", "", false),
        ] {
            let marker = launch_of(&xml);
            assert_eq!(
                open_request_from_argv(std::slice::from_ref(&marker)),
                Some(ToastOpen::Window),
                "{marker}\n{xml}"
            );
        }
    }

    /// A body click goes through the app's EXISTING doors - never a new
    /// window, a new tray icon or a second focus path. A plain click uses the
    /// one `show_hud` every other "show me Jarvis" press uses; an approval
    /// uses the `open_approval_in_quickbar` command `card-link.js`'s "Open the
    /// card" already calls, with the same surface.
    #[test]
    fn a_body_click_opens_the_window_through_the_one_door_that_already_exists() {
        let src = include_str!("winrt_toast.rs");
        let opened = body(src, "pub(crate) fn open_from_toast(");
        assert!(
            opened.contains("crate::windows::show_hud(app)"),
            "a body click no longer goes through the one show-the-HUD door:\n{opened}"
        );
        assert!(
            opened.contains("crate::commands::open_approval_in_quickbar("),
            "an approval's click no longer uses the app's own open-the-card \
             command:\n{opened}"
        );
        assert!(
            opened.contains("CARD_TARGET"),
            "the open-the-card command is called with a surface this module \
             picked itself:\n{opened}"
        );
        // Nothing here creates a window or a tray icon.
        for forbidden in [
            "WebviewWindowBuilder",
            "TrayIconBuilder",
            "set_focus()",
            "set_focus(",
        ] {
            assert!(
                !opened.contains(forbidden),
                "open_from_toast is building its own focus path ({forbidden}):\n{opened}"
            );
        }
        // The surface is the one `commands::card_open_target` maps to the HUD.
        assert_eq!(CARD_TARGET, "hud");
    }

    /// A click that arrives while Jarvis is running (the single-instance
    /// callback) AND one that starts it (a cold start) must both answer a body
    /// click. Handling only one is the exact half-fix the Deny button had to
    /// learn, and it looks identical from the owner's chair.
    #[test]
    fn both_launch_paths_answer_a_body_click() {
        let lib = include_str!("lib.rs");
        // The running case: the marker must be read BEFORE the ordinary
        // "second launch folded" fallback, or the window comes up and the card
        // is never opened.
        let start = lib
            .find("tauri_plugin_single_instance::init(")
            .expect("the single-instance callback is gone");
        let fallback = lib[start..]
            .find("second launch folded into the running instance")
            .expect("the ordinary second-launch fallback is gone");
        let callback = &lib[start..start + fallback];
        assert!(
            callback.contains("winrt_toast::open_request_from_argv(&_argv)"),
            "a body click that reaches a running Jarvis is folded into an \
             ordinary second launch:\n{callback}"
        );
        assert!(
            callback.contains("winrt_toast::open_from_toast(app, &request)"),
            "the single-instance callback reads the body click and does \
             nothing with it:\n{callback}"
        );
        // The cold-start case: a click that started the app.
        assert!(
            lib.contains("winrt_toast::open_at_startup(&handle)"),
            "a body click that STARTS Jarvis opens the window and does nothing \
             about what was clicked"
        );
        // ...and `open_at_startup` really does the work rather than logging.
        let startup = body(src_of_self(), "pub fn open_at_startup(");
        assert!(startup.contains("open_request_from_argv"), "{startup}");
        assert!(startup.contains("open_from_toast"), "{startup}");
    }

    /// This file's own text, for the pin above.
    fn src_of_self() -> &'static str {
        include_str!("winrt_toast.rs")
    }
}
