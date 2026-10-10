//! Which notifications this PC may post, and when it may not.
//!
//! Settings -> Notifications offers one switch per kind - alarms, reminders,
//! the morning briefing, and a website needing the owner - plus a quiet-hours
//! window. Until this module existed those choices were written by
//! `notifications-prefs.js` into the webview's `localStorage` and read by
//! NOTHING that posts a toast, so a kind switched off still notified: the
//! switches looked like they worked and did not. The webview could not fix it
//! from its side. Every toast this app posts is raised in Rust
//! (`brain/schedule.rs`, `brain/briefing.rs`, `stream.rs`), Rust cannot read
//! another window's `localStorage`, and no command carried the choices.
//!
//! So the choices live here now, and the wiring is:
//!
//! * the settings window PUSHES its copy in through
//!   [`set_notification_prefs`] - `notifications-prefs.js` is still the one
//!   place the page reads and writes them, and it is that file which calls
//!   this command, so there is one source of truth rather than two;
//! * the window also pushes once on LOAD, which is how choices the owner had
//!   already made in `localStorage` before this module existed are carried
//!   over instead of being silently reverted;
//! * every poster asks [`may_post`] before it raises anything.
//!
//! ## The store
//!
//! Deliberately the same shape as `windows.rs`'s `WidgetPrefs`: a small JSON
//! file in the app config dir, a `Default` that is what the app does with no
//! file at all, and a `Mutex` plus a dirty flag flushed by the telemetry tick.
//! A missing or corrupt file is NOT an error - it is the defaults, and the
//! defaults are EVERYTHING ON. "Nothing stored" must never be read as "nothing
//! may notify": going quiet by accident is the same bug from the other side.
//! A file written before a field existed is read the same way (`serde`
//! `default` per field, as `WidgetPrefs` does).
//!
//! ## The gate, and the asymmetry a later edit would flatten
//!
//! [`verdict`] is the whole policy, and it is a pure function so it can be
//! tested without a Tauri app:
//!
//! * **A per-kind switch is absolute.** Off means no toast of that kind, at
//!   any hour, ringing or not. There is no hour at which "off" quietly means
//!   "on again".
//! * **Quiet hours act on the three kinds that can wait** - a reminder, the
//!   briefing, and a handoff - **and on nothing else.** They never silence an
//!   ALARM, and they never silence an APPROVAL. An alarm the owner set must
//!   still ring at 03:00, which is the entire point of having set it; and an
//!   approval card must always reach him, or Jarvis sits waiting for a yes
//!   nobody was ever told about. This is exactly the rule a later edit
//!   flattens - "quiet hours: return false here" reads perfectly reasonable
//!   until it is an alarm - so it is stated twice: once in
//!   [`Kind::waits_for_quiet_hours`], which lists the three kinds by name,
//!   and once in this module's tests, which walk every minute of the day.

use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

/// The quiet-hours window's default ends, the same two `notifications-prefs.js`
/// puts in the page's inputs on first run.
pub const DEFAULT_QUIET_START: &str = "22:00";
pub const DEFAULT_QUIET_END: &str = "07:00";

/// The owner's notification choices, as the settings page sends them.
///
/// `camelCase` and `default` are load-bearing, not decoration: the page speaks
/// the keys the page's own `localStorage` uses (`quietEnabled`, `quietStart`,
/// `quietEnd`), and an older or hand-edited file that lacks a field must take
/// the field's default rather than fail to load at all - a file that will not
/// parse would read as "no choices", which is everything on, and the owner's
/// real "off" would be lost.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct NotificationPrefs {
    /// Alarms, and an urgent "tell me when" alert (the settings row is
    /// "Alarms and urgent alerts"). Off means neither rings.
    pub alarms: bool,
    /// Reminders, timers and to-do items coming due (the row is "Reminders,
    /// timers and to-dos").
    pub reminders: bool,
    /// The morning briefing is ready to read in the Brain.
    pub briefing: bool,
    /// A website or support chat has paused at a captcha or sign-in page and
    /// is waiting for the owner.
    pub handoff: bool,
    /// Quiet hours on or off.
    pub quiet_enabled: bool,
    /// The window's two ends, "HH:MM" on the owner's own wall clock.
    pub quiet_start: String,
    pub quiet_end: String,
}

impl Default for NotificationPrefs {
    /// Everything on, quiet hours off: exactly what this app did before the
    /// switches existed. See the module doc for why this is the empty store's
    /// meaning and not "everything off".
    fn default() -> Self {
        Self {
            alarms: true,
            reminders: true,
            briefing: true,
            handoff: true,
            quiet_enabled: false,
            quiet_start: DEFAULT_QUIET_START.to_string(),
            quiet_end: DEFAULT_QUIET_END.to_string(),
        }
    }
}

/// "HH:MM" as minutes past midnight, or `None` for anything else - including
/// the empty string an untouched or cleared time input can send.
fn clock_minutes(text: &str) -> Option<u32> {
    let (hours, minutes) = text.trim().split_once(':')?;
    let hours: u32 = hours.parse().ok()?;
    let minutes: u32 = minutes.parse().ok()?;
    (hours < 24 && minutes < 60).then_some(hours * 60 + minutes)
}

impl NotificationPrefs {
    /// The quiet-hours window in minutes past midnight, or `None` when quiet
    /// hours are off or either end cannot be read.
    ///
    /// A window whose two ends are the same time is EMPTY, not all day.
    /// Nobody means "all day" by typing one time twice, and a stray "from
    /// 22:00 to 22:00" that swallowed the briefing and every reminder until
    /// someone noticed would be worse than ignoring it.
    pub fn quiet_window(&self) -> Option<(u32, u32)> {
        if !self.quiet_enabled {
            return None;
        }
        let start = clock_minutes(&self.quiet_start)?;
        let end = clock_minutes(&self.quiet_end)?;
        (start != end).then_some((start, end))
    }

    /// True at `minutes` past local midnight, while the quiet-hours window
    /// runs.
    ///
    /// The window normally wraps midnight (22:00 to 07:00 is the ordinary
    /// one), so "inside" is the union of two stretches, not one.
    pub fn quiet_now(&self, minutes: u32) -> bool {
        let Some((start, end)) = self.quiet_window() else {
            return false;
        };
        if start < end {
            minutes >= start && minutes < end
        } else {
            minutes >= start || minutes < end
        }
    }

    /// The same choices with anything unreadable replaced by the defaults.
    ///
    /// The page sends what its inputs hold, and a time input gives "HH:MM" -
    /// but a hand-edited `notifications.json`, or a page that sent nothing,
    /// must not leave a window the gate cannot judge.
    fn tidied(mut self) -> Self {
        if clock_minutes(&self.quiet_start).is_none() {
            self.quiet_start = DEFAULT_QUIET_START.to_string();
        }
        if clock_minutes(&self.quiet_end).is_none() {
            self.quiet_end = DEFAULT_QUIET_END.to_string();
        }
        self
    }
}

/// One kind of thing that can arrive as a Windows toast on this PC.
///
/// The four kinds Settings offers a switch for, plus two it does not. The
/// "plus two" are the point: a poster must be able to say what it is posting
/// without being handed a switch that does not exist for it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Kind {
    /// An alarm going off, and an urgent "tell me when" alert - the same
    /// ringing, break-through-Focus-Assist behaviour, and the same settings
    /// row ("Alarms and urgent alerts").
    Alarm,
    /// A reminder, a timer or a to-do item coming due.
    Reminder,
    /// The morning briefing is ready.
    Briefing,
    /// A website or support chat is waiting for the owner.
    Handoff,
    /// A toast with no switch of its own: a plain (non-urgent) "tell me
    /// when" match, a "tell me when" that cannot look, and the line a Snooze
    /// press is answered with. Nothing here turns it off, because Settings
    /// never offered to - inventing a silence for it is not this module's
    /// job - and quiet hours leave it alone for the same reason the module
    /// doc gives: only the three kinds that can wait are listed.
    Other,
    /// An approval card's own toast (`stream.rs` `refresh_pending`).
    ///
    /// It is in this enum so that "an approval is never silenced" is a POLICY
    /// this module states and its tests hold, rather than an absence someone
    /// would have to notice. Its poster asks [`may_post`] like every other
    /// one, and the answer is `Show` at every hour, with every switch off.
    Approval,
}

impl Kind {
    /// The kind an event names. `urgent` is a "tell me when"'s own flag: an
    /// urgent match rings until dismissed, exactly like an alarm, so it rides
    /// the alarms switch; a plain match has no switch at all.
    ///
    /// A kind this build does not know is [`Kind::Other`] - shown, as it was
    /// before these switches existed, rather than guessed at.
    pub fn for_event(kind: &str, urgent: bool) -> Self {
        match kind {
            "alarm" => Kind::Alarm,
            "tellme" if urgent => Kind::Alarm,
            "reminder" | "timer" | "todo" => Kind::Reminder,
            "briefing" => Kind::Briefing,
            "handoff" => Kind::Handoff,
            _ => Kind::Other,
        }
    }

    /// Whether quiet hours may hold this kind back.
    ///
    /// THREE kinds, named one by one on purpose - see the module doc. An
    /// alarm is not one of them (the owner set it to ring), and neither is an
    /// approval (`Kind::Approval`), which must always reach him. A single
    /// change here - adding `| Kind::Alarm`, say - is the edit the module's
    /// tests exist to catch.
    pub fn waits_for_quiet_hours(self) -> bool {
        matches!(self, Kind::Reminder | Kind::Briefing | Kind::Handoff)
    }
}

/// What the store says about one kind at one moment.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Verdict {
    /// Post it.
    Show,
    /// The owner switched this kind off. Absolute: at any hour.
    SwitchedOff,
    /// Quiet hours, and a kind that can wait.
    QuietHours,
}

impl Verdict {
    pub fn shows(self) -> bool {
        matches!(self, Verdict::Show)
    }
}

/// The whole policy, and the only place it is written down.
///
/// `minutes` is minutes past LOCAL midnight, or `None` when this platform
/// cannot say what the time is (see [`local_minutes`]) - an unreadable clock
/// must not silence anything, so it simply means quiet hours do not apply.
pub fn verdict(prefs: &NotificationPrefs, kind: Kind, minutes: Option<u32>) -> Verdict {
    let switched_on = match kind {
        Kind::Alarm => prefs.alarms,
        Kind::Reminder => prefs.reminders,
        Kind::Briefing => prefs.briefing,
        Kind::Handoff => prefs.handoff,
        // The two with no switch. `Other`: Settings never offered to turn it
        // off. `Approval`: it must always reach the owner - there is no hour
        // and no combination of switches at which this may become false.
        Kind::Other | Kind::Approval => true,
    };
    if !switched_on {
        // Absolute, and checked before quiet hours so an off switch stays
        // `SwitchedOff` rather than being re-explained as a quiet window:
        // off at noon is the same choice as off at midnight.
        return Verdict::SwitchedOff;
    }
    if kind.waits_for_quiet_hours() && minutes.is_some_and(|m| prefs.quiet_now(m)) {
        return Verdict::QuietHours;
    }
    Verdict::Show
}

/// Minutes past local midnight, or `None` on a platform this module cannot
/// ask.
///
/// Quiet hours are the owner's wall clock, so `SystemTime`'s UTC is not an
/// answer; on Windows this is the OS's own local time, which already knows
/// about the time zone and summer time. Anywhere else there is no answer, and
/// [`verdict`] treats that as "quiet hours cannot be judged" rather than
/// guessing - guessing would silence a reminder at the wrong hour.
#[cfg(windows)]
fn local_minutes() -> Option<u32> {
    use windows_sys::Win32::Foundation::SYSTEMTIME;
    use windows_sys::Win32::System::SystemInformation::GetLocalTime;

    // SAFETY: `SYSTEMTIME` is a plain struct of `u16`s, so all-zero is a
    // valid value, and `now` is a valid, writable pointer for the whole call
    // - which is the function's only requirement. `GetLocalTime` returns
    // nothing to fail on.
    let mut now: SYSTEMTIME = unsafe { std::mem::zeroed() };
    unsafe { GetLocalTime(&mut now) };
    Some(u32::from(now.wHour) * 60 + u32::from(now.wMinute))
}

#[cfg(not(windows))]
fn local_minutes() -> Option<u32> {
    None
}

/// In-memory copy of [`NotificationPrefs`], flushed to disk by the telemetry
/// tick - the same discipline `windows.rs`'s `WidgetState` uses, for the same
/// reason: the settings page can send a change while the window is closing,
/// and the write is not worth doing twice.
///
/// The command writes through at once as well (it is a deliberate choice by
/// the owner, not a mouse drag), so nothing here depends on the tick.
#[derive(Default)]
pub struct NotificationState {
    prefs: Mutex<NotificationPrefs>,
    dirty: AtomicBool,
}

impl NotificationState {
    pub fn snapshot(&self) -> NotificationPrefs {
        self.prefs
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .clone()
    }

    /// Applies `edit` to the stored prefs and marks them for the next flush.
    pub fn update(&self, edit: impl FnOnce(&mut NotificationPrefs)) {
        let mut prefs = self
            .prefs
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        edit(&mut prefs);
        self.dirty.store(true, Ordering::Relaxed);
    }

    /// Writes the prefs out if anything changed since the last flush.
    pub fn flush(&self, app: &AppHandle) {
        if !self.dirty.swap(false, Ordering::Relaxed) {
            return;
        }
        let prefs = self.snapshot();
        if let Err(err) = write_notification_prefs(app, &prefs) {
            eprintln!("[jarvis] unable to persist notification prefs: {err}");
        }
    }
}

fn notification_prefs_path(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app
        .path()
        .app_config_dir()
        .map_err(|e| format!("unable to resolve the app config dir: {e}"))?;
    Ok(dir.join("notifications.json"))
}

fn write_notification_prefs(app: &AppHandle, prefs: &NotificationPrefs) -> Result<(), String> {
    let path = notification_prefs_path(app)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("unable to create {}: {e}", parent.display()))?;
    }
    let json = serde_json::to_string_pretty(prefs)
        .map_err(|e| format!("unable to serialize notification prefs: {e}"))?;
    std::fs::write(&path, json).map_err(|e| format!("unable to write {}: {e}", path.display()))
}

/// Loads persisted prefs, falling back to the defaults for a missing or
/// corrupt file - a bad `notifications.json` must never stop the app from
/// starting, and must never be read as "nothing may notify".
pub fn load_notification_prefs(app: &AppHandle) -> NotificationPrefs {
    notification_prefs_path(app)
        .ok()
        .and_then(|path| std::fs::read_to_string(path).ok())
        .and_then(|raw| serde_json::from_str::<NotificationPrefs>(&raw).ok())
        .unwrap_or_default()
        .tidied()
}

/// May a toast of this kind be posted right now?
///
/// The one call every poster makes, and the reason the policy above is
/// reachable at all. It reads the in-memory copy (never the file: a poster
/// runs on the event stream and must not touch the disk per toast) and the
/// OS's own local clock.
pub fn may_post(app: &AppHandle, kind: Kind) -> bool {
    let prefs = app.state::<NotificationState>().snapshot();
    verdict(&prefs, kind, local_minutes()).shows()
}

// ---------------------------------------------------------------------------
// A change made on the PHONE reaches these toasts
// ---------------------------------------------------------------------------

/// The PC's own copy of the notification choices: the `[notifications]` section
/// of `jarvis-framework.toml`, which the phone writes through the backend
/// (the owner's decision, 2026-10-09: "the PC's notification choices must be
/// changeable from the phone"). `GET /api/notifications` answers the same
/// section back in this app's own `camelCase` names.
///
/// THE GAP THIS CLOSES. Everything above reads `NotificationState`, which is
/// filled once at startup from `notifications.json` and changed from then on
/// only by [`set_notification_prefs`] - which only the desktop's Settings page
/// calls. So a choice made on the PHONE was written to the PC's settings file
/// and shown by both screens, while the toasts went on following the old values
/// until somebody happened to open Settings -> Notifications. An alarm switched
/// on from the phone did not ring; one switched off from the phone still rang.
pub(crate) const NOTIFICATIONS_PATH: &str = "/api/notifications";

/// How long one refresh may take. The loop this rides on wakes every three
/// seconds, so this is a ceiling on one attempt, not on the gap between them.
const SYNC_TIMEOUT: Duration = Duration::from_secs(10);

/// Every how many wake-ups the choices are re-read. ~30 s: a toast that arrives
/// in that window follows the previous choice, and the owner's own Settings page
/// still applies a change at once through [`set_notification_prefs`], so nothing
/// they do on this PC waits for it.
pub(crate) const SYNC_EVERY: u32 = 10;

/// [`NotificationState::sync_from_remote`]'s reading of the answer, tested in
/// this file. `None` means "keep what we have", and EVERY failure means that:
/// an older PC with no such route, a backend that is down, a hand-edited body,
/// a missing field, a wrong type.
///
/// FAILING TO "KEEP" RATHER THAN TO "ALL ON" is the point. This store's own rule
/// is that a missing file reads as everything on, because going quiet by
/// accident is the bug from the other side - but that rule is for a file this
/// app owns and wrote. A refresh that cannot read the PC's real choices has
/// learnt nothing, and the honest answer to "what did the phone choose?" is "we
/// do not know yet", not "everything on" and not "everything off".
pub(crate) fn notifications_answer(status: u16, body: &str) -> Option<NotificationPrefs> {
    if !(200..300).contains(&status) {
        return None;
    }
    let value: serde_json::Value = serde_json::from_str(body).ok()?;
    let node = value.get("notifications")?.as_object()?;
    let flag = |name: &str| node.get(name)?.as_bool();
    let clock = |name: &str| node.get(name)?.as_str().map(str::to_string);
    Some(
        NotificationPrefs {
            alarms: flag("alarms")?,
            reminders: flag("reminders")?,
            briefing: flag("briefing")?,
            handoff: flag("handoff")?,
            quiet_enabled: flag("quietEnabled")?,
            quiet_start: clock("quietStart")?,
            quiet_end: clock("quietEnd")?,
        }
        .tidied(),
    )
}

impl NotificationState {
    /// Copies the PC's own choices (the phone's change included) into the copy
    /// every toast reads. Answers whether the state actually moved.
    ///
    /// NOT written to `notifications.json` on purpose. That file is this app's
    /// private copy of what the owner chose HERE, and the PC's settings file is
    /// the one both apps change; keeping the two in step on disk is the
    /// settings page's business (`notifications-prefs.js`), not this loop's.
    /// Nothing is persisted, so a backend that answers nonsense cannot leave a
    /// wrong choice behind on disk.
    pub fn sync_from_remote(&self, remote: NotificationPrefs) -> bool {
        let mut prefs = self
            .prefs
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if *prefs == remote {
            return false;
        }
        *prefs = remote;
        // Deliberately NOT `self.dirty.store(true)`: `dirty` means "there is
        // something of this app's own to write out", and this is not.
        true
    }
}

/// Asks the PC what the notification choices are now, and puts them where
/// [`may_post`] will see them. Called from the telemetry loop every
/// [`SYNC_EVERY`] wake-ups.
///
/// SILENT ON EVERY FAILURE, by design: an older PC (404), a backend that is
/// down, a token this app cannot read - each leaves the current choices in
/// force, which is exactly what happened before this function existed. It is
/// also never fatal: a failed refresh must not stop the telemetry loop.
pub(crate) async fn refresh_notification_prefs(app: AppHandle) {
    let base = crate::commands::jarvis_base(&app);
    let client = match crate::commands::jarvis_client(Some(SYNC_TIMEOUT)) {
        Ok(client) => client,
        Err(err) => {
            eprintln!("[jarvis] notification choices not re-read: {err}");
            return;
        }
    };
    let headers = match crate::commands::jarvis_headers(&app) {
        Ok(headers) => headers,
        Err(err) => {
            eprintln!("[jarvis] notification choices not re-read: {err}");
            return;
        }
    };
    let response = match client
        .get(format!("{base}{NOTIFICATIONS_PATH}"))
        .headers(headers)
        .send()
        .await
    {
        Ok(response) => response,
        Err(err) => {
            // Said on stderr and nowhere else: the event stream already shows
            // the owner that this PC cannot reach its own Jarvis, and a toast
            // about it would be a toast about notifications.
            eprintln!("[jarvis] notification choices not re-read: {err}");
            return;
        }
    };
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    if let Some(remote) = notifications_answer(status, &body) {
        app.state::<NotificationState>().sync_from_remote(remote);
    }
}

/// The settings window's "Notifications" choices: the four switches and the
/// quiet-hours window, pushed here by `notifications-prefs.js` - the same file
/// that keeps the page's copy, so there is one place a change is made and two
/// copies that are written together.
///
/// Deliberately NOT held on a stale event stream, and no approval card: it
/// decides nothing outside this PC and only changes what this PC shows its
/// owner. It is written to disk AT ONCE rather than waiting for the telemetry
/// tick - a switch is a deliberate tap and the owner may close the window or
/// quit the app a second later, which is the same loss bug audit 2026-09-27
/// (desktop-rust finding #6) fixed for the widget's own prefs.
///
/// Answers with what was actually stored, so a page that sent an unreadable
/// time can see what it became instead of believing it was kept.
#[tauri::command]
pub fn set_notification_prefs(
    app: AppHandle,
    prefs: NotificationPrefs,
) -> Result<NotificationPrefs, String> {
    let stored = prefs.tidied();
    let state = app.state::<NotificationState>();
    state.update(|current| *current = stored.clone());
    state.flush(&app);
    Ok(stored)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The prefs every switch on, quiet hours off - the empty store.
    fn all_on() -> NotificationPrefs {
        NotificationPrefs::default()
    }

    /// The same, with quiet hours running 22:00 to 07:00.
    fn quiet() -> NotificationPrefs {
        NotificationPrefs {
            quiet_enabled: true,
            ..NotificationPrefs::default()
        }
    }

    /// Every minute of a day, for the sweeps below.
    fn every_minute() -> impl Iterator<Item = u32> {
        0u32..24 * 60
    }

    /// One function's own text, from its definition to the next one.
    ///
    /// The same source check `brain/history.rs` uses for "every one of these
    /// commands asks the lock and the link": a gate that is written here and
    /// never CALLED changes nothing, and deleting the call is exactly the
    /// edit this whole fix exists to prevent.
    fn function<'a>(src: &'a str, name: &str) -> &'a str {
        let at = src
            .find(name)
            .unwrap_or_else(|| panic!("{name} is gone from this file"));
        let rest = &src[at..];
        let mut end = rest.len();
        for next in [
            "\nfn ",
            "\npub fn ",
            "\npub(crate) fn ",
            "\nasync fn ",
            "\npub async fn ",
            "\npub(crate) async fn ",
            "\n#[cfg(test)]",
        ] {
            if let Some(i) = rest[1..].find(next) {
                end = end.min(i + 1);
            }
        }
        &rest[..end]
    }

    #[test]
    fn an_empty_store_is_everything_on_and_quiet_hours_off() {
        let prefs = all_on();
        assert!(prefs.alarms && prefs.reminders && prefs.briefing && prefs.handoff);
        assert!(!prefs.quiet_enabled);
        assert_eq!(prefs.quiet_start, DEFAULT_QUIET_START);
        assert_eq!(prefs.quiet_end, DEFAULT_QUIET_END);
        assert_eq!(prefs.quiet_window(), None);
        for kind in [
            Kind::Alarm,
            Kind::Reminder,
            Kind::Briefing,
            Kind::Handoff,
            Kind::Other,
            Kind::Approval,
        ] {
            for minutes in every_minute() {
                assert_eq!(
                    verdict(&prefs, kind, Some(minutes)),
                    Verdict::Show,
                    "{kind:?} at {minutes} must show with nothing stored"
                );
            }
        }
    }

    #[test]
    fn a_half_written_file_leaves_the_rest_on() {
        // A file from before a field existed, or hand-edited: the missing
        // switches keep the app's own default rather than reading as false.
        let half: NotificationPrefs = serde_json::from_str(r#"{"reminders": false}"#).unwrap();
        assert!(!half.reminders);
        assert!(half.alarms && half.briefing && half.handoff);
        assert!(!half.quiet_enabled);
        assert_eq!(
            half,
            NotificationPrefs {
                reminders: false,
                ..all_on()
            }
        );
        // Empty object, and a whole file that will not parse: the load path
        // falls back to the same defaults.
        assert_eq!(
            serde_json::from_str::<NotificationPrefs>("{}").unwrap(),
            all_on()
        );
        assert_eq!(
            serde_json::from_str::<NotificationPrefs>("not json")
                .unwrap_or_default()
                .tidied(),
            all_on()
        );
    }

    #[test]
    fn a_switch_that_is_off_is_off_at_every_hour() {
        // Absolute: the off switch is not re-read as "on again outside quiet
        // hours", and quiet hours do not turn an off switch into a different
        // reason.
        for (kind, off) in [
            (
                Kind::Alarm,
                NotificationPrefs {
                    alarms: false,
                    ..all_on()
                },
            ),
            (
                Kind::Reminder,
                NotificationPrefs {
                    reminders: false,
                    ..all_on()
                },
            ),
            (
                Kind::Briefing,
                NotificationPrefs {
                    briefing: false,
                    ..all_on()
                },
            ),
            (
                Kind::Handoff,
                NotificationPrefs {
                    handoff: false,
                    ..all_on()
                },
            ),
        ] {
            for prefs in [
                off.clone(),
                NotificationPrefs {
                    quiet_enabled: true,
                    ..off.clone()
                },
            ] {
                for minutes in every_minute() {
                    assert_eq!(
                        verdict(&prefs, kind, Some(minutes)),
                        Verdict::SwitchedOff,
                        "{kind:?} at {minutes} with its switch off"
                    );
                }
            }
        }
        // And the same switch read with no clock at all (a platform this
        // module cannot ask): off is still off.
        assert_eq!(
            verdict(
                &NotificationPrefs {
                    alarms: false,
                    ..all_on()
                },
                Kind::Alarm,
                None
            ),
            Verdict::SwitchedOff
        );
    }

    #[test]
    fn quiet_hours_hold_back_the_three_that_can_wait_and_nothing_else() {
        let prefs = quiet();
        for minutes in every_minute() {
            let inside = !(7 * 60..22 * 60).contains(&minutes);
            for kind in [Kind::Reminder, Kind::Briefing, Kind::Handoff] {
                let want = if inside {
                    Verdict::QuietHours
                } else {
                    Verdict::Show
                };
                assert_eq!(
                    verdict(&prefs, kind, Some(minutes)),
                    want,
                    "{kind:?} at {minutes}"
                );
            }
            // The kinds quiet hours must never touch: an alarm (its own
            // tests below), a toast with no switch of its own, and an
            // approval.
            for kind in [Kind::Other, Kind::Approval] {
                assert_eq!(
                    verdict(&prefs, kind, Some(minutes)),
                    Verdict::Show,
                    "{kind:?} at {minutes} must not be held back by quiet hours"
                );
            }
        }
        // The window's two ends: 22:00 is inside, 07:00 is not (the owner is
        // awake at 07:00, and "to 07:00" means quiet until then).
        assert_eq!(
            verdict(&prefs, Kind::Reminder, Some(21 * 60 + 59)),
            Verdict::Show
        );
        assert_eq!(
            verdict(&prefs, Kind::Reminder, Some(22 * 60)),
            Verdict::QuietHours
        );
        assert_eq!(
            verdict(&prefs, Kind::Reminder, Some(6 * 60 + 59)),
            Verdict::QuietHours
        );
        assert_eq!(verdict(&prefs, Kind::Reminder, Some(7 * 60)), Verdict::Show);
        // A window whose ends are the same time is empty, not all day.
        let same = NotificationPrefs {
            quiet_enabled: true,
            quiet_start: "22:00".into(),
            quiet_end: "22:00".into(),
            ..all_on()
        };
        assert_eq!(same.quiet_window(), None);
        // An unreadable time cannot be judged, so it cannot silence anything.
        let broken = NotificationPrefs {
            quiet_enabled: true,
            quiet_start: "tonight".into(),
            ..all_on()
        };
        assert_eq!(broken.quiet_window(), None);
        for minutes in every_minute() {
            assert_eq!(
                verdict(&broken, Kind::Briefing, Some(minutes)),
                Verdict::Show
            );
        }
        // And a clock this module cannot read is not midnight.
        assert_eq!(verdict(&prefs, Kind::Briefing, None), Verdict::Show);
    }

    #[test]
    fn quiet_hours_never_swallow_an_alarm_or_an_approval() {
        // THE line. Anyone flattening the gate by making quiet hours mean
        // "post nothing" fails here first.
        let prefs = quiet();
        for minutes in every_minute() {
            assert_eq!(
                verdict(&prefs, Kind::Alarm, Some(minutes)),
                Verdict::Show,
                "an alarm the owner set must still ring at {minutes}"
            );
            assert_eq!(
                verdict(&prefs, Kind::Approval, Some(minutes)),
                Verdict::Show,
                "an approval card must always reach him, at {minutes}"
            );
        }
        // Even with every switch off, an approval still shows: there is no
        // combination of the owner's choices that quietly drops a card.
        let everything_off = NotificationPrefs {
            alarms: false,
            reminders: false,
            briefing: false,
            handoff: false,
            quiet_enabled: true,
            ..all_on()
        };
        for minutes in every_minute() {
            assert_eq!(
                verdict(&everything_off, Kind::Approval, Some(minutes)),
                Verdict::Show
            );
        }
        // CONTROL: the same sweep does catch a kind that may be silenced.
        assert_eq!(
            verdict(&everything_off, Kind::Reminder, Some(23 * 60)),
            Verdict::SwitchedOff
        );
    }

    #[test]
    fn the_alarms_switch_covers_an_urgent_tell_me_when() {
        // The settings row is "Alarms and urgent alerts", and an urgent
        // match rings until dismissed exactly like an alarm - so it is the
        // same switch, and the same "quiet hours never touch it".
        assert_eq!(Kind::for_event("alarm", false), Kind::Alarm);
        assert_eq!(Kind::for_event("tellme", true), Kind::Alarm);
        assert_eq!(Kind::for_event("reminder", false), Kind::Reminder);
        assert_eq!(Kind::for_event("timer", false), Kind::Reminder);
        assert_eq!(Kind::for_event("todo", false), Kind::Reminder);
        assert_eq!(Kind::for_event("briefing", false), Kind::Briefing);
        assert_eq!(Kind::for_event("handoff", false), Kind::Handoff);
        // A plain match, a broken watch, and a kind this build does not know:
        // no switch of its own, so it is shown as it was before.
        assert_eq!(Kind::for_event("tellme", false), Kind::Other);
        for unknown in ["", "nexttime", "next_time", "standby"] {
            assert_eq!(Kind::for_event(unknown, false), Kind::Other, "{unknown}");
        }
    }

    #[test]
    fn every_poster_asks_this_module_first() {
        // Source check - see `function` above. Each of these call sites is a
        // toast that used to go out regardless of the switches.
        let schedule = include_str!("brain/schedule.rs");
        for name in ["fn show(", "pub(crate) fn show_quiet("] {
            assert!(
                function(schedule, name).contains("notifications::may_post"),
                "{name} posts without asking the notification store"
            );
        }
        let briefing = include_str!("brain/briefing.rs");
        assert!(
            function(briefing, "pub async fn toast_ready(")
                .contains("notifications::may_post(&app, crate::notifications::Kind::Briefing)"),
            "the briefing toast posts without asking the notification store"
        );
        let stream = include_str!("stream.rs");
        assert!(
            function(stream, "async fn toast_handoff(")
                .contains("notifications::may_post(&app, crate::notifications::Kind::Handoff)"),
            "the handoff toast posts without asking the notification store"
        );
        // The approval ping asks too, and its answer must stay yes: this is
        // the wiring half of `quiet_hours_never_swallow_an_alarm_or_an_approval`.
        assert!(
            function(stream, "async fn refresh_pending(")
                .contains("notifications::may_post(app, crate::notifications::Kind::Approval)"),
            "the approval toast no longer asks the store - a switch or quiet hours \
             could silence a card"
        );
    }

    // -----------------------------------------------------------------------
    // A choice made on the phone, and the toasts that follow it
    // -----------------------------------------------------------------------

    /// The backend's real answer for the owner's own settings, as
    /// `GET /api/notifications` serves it. Every switch on and quiet hours off
    /// is what the shipped `jarvis-framework.toml` says.
    fn backend(body: &str) -> Option<NotificationPrefs> {
        notifications_answer(200, body)
    }

    #[test]
    fn a_change_made_on_the_phone_is_read_from_the_pc() {
        // The owner's decision of 2026-10-09: the PC's notification choices are
        // changeable from the phone. The phone writes the settings file through
        // the backend; this is the desktop reading it back.
        let quiet_off_on_the_phone = backend(
            r#"{"ok": true, "notifications": {"alarms": false, "reminders": true,
                "briefing": true, "handoff": true, "quietEnabled": true,
                "quietStart": "22:00", "quietEnd": "07:00"}}"#,
        )
        .expect("the PC's own answer");
        assert!(!quiet_off_on_the_phone.alarms);
        assert!(quiet_off_on_the_phone.quiet_enabled);
        assert_eq!(
            quiet_off_on_the_phone.quiet_window(),
            Some((22 * 60, 7 * 60))
        );
        // And the thing the whole fix is for: an alarm switched OFF on the phone
        // stops the alarm toast, with nobody having opened Settings.
        assert_eq!(
            verdict(&quiet_off_on_the_phone, Kind::Alarm, Some(3 * 60)),
            Verdict::SwitchedOff
        );
        assert!(!verdict(&quiet_off_on_the_phone, Kind::Alarm, Some(3 * 60)).shows());
        // ...while a row that is still on keeps its own behaviour at the same
        // minute: the reminder is held by quiet hours, which the phone turned
        // ON, and an approval card is never swallowed by either.
        assert_eq!(
            verdict(&quiet_off_on_the_phone, Kind::Reminder, Some(3 * 60)),
            Verdict::QuietHours
        );
        assert_eq!(
            verdict(&quiet_off_on_the_phone, Kind::Approval, Some(3 * 60)),
            Verdict::Show,
            "quiet hours must never swallow an approval card"
        );
    }

    #[test]
    fn a_refresh_that_cannot_be_read_changes_nothing() {
        // EVERY failure is "keep what we have". An older PC (404), a backend
        // that is down, a body that is not JSON, a missing field, a field of the
        // wrong type - none of them may be read as a choice, because the store's
        // own rule (a missing file is everything ON) is for a file this app
        // wrote, not for a refresh that learnt nothing.
        assert_eq!(
            notifications_answer(404, r#"{"error": "no such route"}"#),
            None
        );
        assert_eq!(notifications_answer(401, r#"{"error": "bad token"}"#), None);
        assert_eq!(notifications_answer(500, "{}"), None);
        assert_eq!(notifications_answer(200, "not json"), None);
        assert_eq!(notifications_answer(200, "{}"), None);
        assert_eq!(notifications_answer(200, r#"{"notifications": {}}"#), None);
        assert_eq!(
            notifications_answer(
                200,
                r#"{"notifications": {"alarms": "yes", "reminders": true, "briefing": true,
                    "handoff": true, "quietEnabled": false, "quietStart": "22:00",
                    "quietEnd": "07:00"}}"#
            ),
            None,
            "a flag that is not a bool is not a choice"
        );
        assert_eq!(
            notifications_answer(
                200,
                r#"{"notifications": {"alarms": true, "reminders": true, "briefing": true,
                    "handoff": true, "quietEnabled": false}}"#
            ),
            None,
            "a missing clock is not a choice"
        );
    }

    #[test]
    fn a_refresh_cannot_leave_a_wrong_choice_on_disk() {
        // `dirty` means "there is something of THIS app's own to write out".
        // A refresh is not, so it must not arm the flush - a backend that
        // answered nonsense would otherwise be able to leave a wrong choice in
        // `notifications.json`, which is read at the next start-up.
        let state = NotificationState::default();
        let moved = state.sync_from_remote(NotificationPrefs {
            alarms: false,
            ..NotificationPrefs::default()
        });
        assert!(moved, "a different choice must move the state");
        assert!(!state.dirty.load(Ordering::Relaxed));
        assert!(!state.snapshot().alarms, "and the state really moved");
        // The same choice twice is not a change, so nothing is reported.
        assert!(!state.sync_from_remote(state.snapshot()));
    }

    #[test]
    fn the_telemetry_loop_actually_re_reads_the_choices() {
        // Source check - see `function` above. A refresh written here and never
        // CALLED is the exact defect this fixes, one layer up: the toasts would
        // go on following `notifications.json` for ever while a correct,
        // tested, unused function sat beside them.
        let lib = include_str!("lib.rs");
        let loop_body = function(lib, "fn spawn_telemetry_loop(");
        assert!(
            loop_body.contains("notifications::refresh_notification_prefs"),
            "the telemetry loop no longer re-reads the notification choices, so a \
             change made on the phone reaches the toasts only when Settings is opened"
        );
        assert!(
            loop_body.contains("notifications::SYNC_EVERY"),
            "the refresh is not spaced out by SYNC_EVERY, so it now runs on every \
             telemetry tick - three seconds apart"
        );
        // ...and the refresh really is a read of the PC's own route, and really
        // puts what it read where a toast will see it.
        let refresh = function(
            include_str!("notifications.rs"),
            "pub(crate) async fn refresh_notification_prefs(",
        );
        assert!(
            refresh.contains("NOTIFICATIONS_PATH") && refresh.contains(".get("),
            "the refresh no longer asks the PC's own /api/notifications route"
        );
        assert!(
            refresh.contains("sync_from_remote"),
            "the refresh reads the route and then throws the answer away"
        );
    }
}
