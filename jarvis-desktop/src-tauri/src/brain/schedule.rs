//! "Coming up" - timers, alarms, reminders, repeating jobs and the to-do list
//! (the owner's decisions of 2026-09-25; backend/schedule.patch,
//! `jarvis_schedule.py`; JARVIS-API.md section 21).
//!
//! Three commands, each its own power, like the rest of brain.rs:
//!
//! * [`brain_schedule`] - `GET /api/schedule`: the list. A read. While
//!   "Windows Hello for memory lists and chat history" (lock.rs) hides the
//!   Brain's private lists, the words of every reminder and to-do item are
//!   taken out here, in Rust, so a page script cannot read round it; the
//!   times, kinds and counts stay, so timers still count down.
//! * [`brain_schedule_act`] - `POST /api/schedule/act {"id", "do"}`: ONE job:
//!   pause, resume, delete, done, or add time to a timer. No card: it only
//!   ever makes things quieter. Held while the event stream is stale (rule
//!   4), like every change in this window. There is no list form and no
//!   "delete all".
//! * [`brain_schedule_add_todo`] - `POST /api/schedule/add {"kind": "todo",
//!   "text"}`: one to-do item, in the owner's own words. Held on a stale link.
//!   Timers and reminders are set by saying or typing them to Jarvis.
//! * [`brain_schedule_add_standby`] - `POST /api/schedule/add {"kind":
//!   "standby", "repeat": {"every": "day", "at", "until"}}`: the standby
//!   schedule (backend `jarvis_standby_schedule.py`) - Standby, the same one
//!   as the tray's Change power mode, on a timetable. Since 2026-09-26 (the
//!   owner's decision after the approvals audit) the PC sets it up at once,
//!   with no card, and says the next night. Held on a stale link. Turning it
//!   off is Delete on its row, like any job.
//! * [`brain_schedule_add_today`] - `POST /api/schedule/add {"kind":
//!   "today", "text", "repeat"}` (2026-09-28): one Today card, the owner's
//!   own words shown on the Work tab's Today card from a time on chosen days
//!   (backend `jarvis_today.py`). No card; held on a stale link. Its words
//!   are blanked by [`redact_list`] like every reminder's.
//!
//! * [`brain_schedule_clear_list`] - `POST /api/schedule/act {"do":
//!   "clear_list", "list", "count"}` (2026-09-25): every item on ONE named
//!   list ("shopping"), after the page's "are you sure?". `count` is how many
//!   items the page showed; the PC clears nothing if that is no longer right.
//!   Never the to-do list itself. Held on a stale link.
//!
//! Snooze (2026-09-25) is one more action of [`brain_schedule_act`]: a timer,
//! alarm or reminder that went off, again in ten minutes - a one-off copy on
//! the PC, no card. [`toast_fired`] puts a Snooze button on its toast
//! (winrt_toast.rs `notify_fired`), which lands in [`snooze_from_toast`].
//!
//! And one thing that is not a command: [`toast_fired`], which stream.rs
//! calls when a `schedule` event says a job went off. The event carries the
//! id and the kind only, never the words; this reads the words by id and
//! shows a Windows toast. While App lock is on, or the private lists are
//! hidden, the toast says only what KIND of thing is due ("Jarvis: a
//! reminder is due.") - the same lock-screen words the phone uses.
//!
//! Whether a toast is raised at all is the owner's own choice, made in
//! Settings (notifications.rs): a kind he switched off never reaches one, and
//! quiet hours hold back the three kinds that can wait. An alarm is never
//! held back, and every gate lives in [`show`] and [`show_quiet`] - the two
//! functions here that actually post.
//!
//! "Tell me when" (backend jarvis_tellme.py, 2026-09-25): a watch that
//! matched says `"state": "matched"`, and [`toast_matched`] shows the job's
//! `alert` ("An email from Alex arrived.") - built on the PC from the
//! owner's own words, never from the email. An ALARM, and a "tell me when"
//! marked urgent, keep ringing until dismissed ([`rings`]: an alarm toast
//! whose sound loops, winrt_toast.rs `notify_alarm`). The owner's decision:
//! "alarms that keep ringing"; a match only notifies.
//!
//! The answer-reading functions are plain functions of (status, body) so
//! their tests run without a Tauri app or a network.

use std::collections::HashSet;
use std::sync::Mutex;

use tauri::AppHandle;

use super::{require_link_live, READ_TIMEOUT, REPEAT_EDIT_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;
use crate::notifications::{self, Kind};

/// A PC whose backend has no scheduler yet. The phone says the same
/// (`Schedule.MISSING`).
pub(crate) const SCHEDULE_MISSING: &str =
    "Your PC's Jarvis does not have timers and reminders yet - run apply-patches.ps1 on the PC.";

/// A change refused because the PC has no such route. Nothing changed.
pub(crate) const SCHEDULE_TOO_OLD: &str =
    "Not changed: your PC's Jarvis does not have timers and reminders yet.";

/// The job is not on the list any more (a 404 that says so).
pub(crate) const NO_SUCH_JOB: &str = "That is not on the list any more.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// The only things one job can be asked to do. Never "all", never a list.
/// The last three are Phase 2 (2026-10-22): ONE edit, ONE move between the
/// to-do lists, ONE reorder - the PC's own `jarvis_schedule._act_phase2` is the
/// authority; these names only say what one job may be asked.
pub(crate) const ACTIONS: &[&str] = &[
    "pause", "resume", "delete", "done", "add_time", "snooze", "edit", "move", "reorder",
];

/// Snooze: how long the buttons set (jarvis_schedule.SNOOZE_DEFAULT), and
/// the shortest and longest the PC takes.
pub(crate) const SNOOZE_SECONDS: f64 = 600.0;
const SNOOZE_MIN: f64 = 60.0;
const SNOOZE_MAX: f64 = 24.0 * 3600.0;

/// The kinds a toast offers Snooze on (jarvis_schedule.SNOOZABLE).
#[cfg_attr(not(windows), allow(dead_code))]
pub(crate) const SNOOZABLE: &[&str] = &["timer", "alarm", "reminder"];

/// The button's words - both apps' (coming-up.js SNOOZE_LABEL).
#[cfg_attr(not(windows), allow(dead_code))]
pub(crate) const SNOOZE_LABEL: &str = "Snooze 10 minutes";

/// The longest named list's name the PC keeps (jarvis_schedule.MAX_LIST_NAME).
const MAX_LIST_NAME: usize = 30;

/// The longest to-do item the PC keeps (jarvis_schedule.MAX_TEXT).
pub(crate) const MAX_TEXT: usize = 300;

/// The longest a timer may run (jarvis_schedule.MAX_TIMER): a timer is for
/// today; later than 24 hours is a reminder.
pub(crate) const MAX_TIMER_SECONDS: f64 = 24.0 * 3600.0;

/// The highest rank a reorder may name. The PC renumbers a list 0..n-1, and a
/// list holds at most `jarvis_schedule.MAX_TODO` open items; a number past that
/// is not a position on any list.
const MAX_REORDER_RANK: i64 = 300;

/// The Phase 2 fields ONE edit, move or reorder may carry (2026-10-22, the
/// owner's Reminders request). Every field is optional; [`change_body`] refuses
/// an empty or nonsensical combination and never invents a value. Deserialised
/// from the page's own argument object with `deny_unknown_fields`, so a page
/// cannot smuggle a field the PC never takes through this command. `when` is
/// deliberately not here: this window reschedules with date+time, and a field
/// it never sends has no reason to exist (the PC still accepts `when` from
/// other callers).
#[derive(Debug, Default, serde::Deserialize)]
#[serde(deny_unknown_fields, rename_all = "snake_case")]
pub struct ScheduleChange {
    pub text: Option<String>,
    pub date: Option<String>,
    pub time: Option<String>,
    /// `at` is an EPOCH (seconds), the PC's own shape - not "HH:MM" (the
    /// HH:MM choice is `time`, beside `date`).
    pub at: Option<f64>,
    pub repeat: Option<serde_json::Value>,
    pub list: Option<String>,
    pub rank: Option<i64>,
    pub seconds: Option<f64>,
}

/// How long ONE change may take: a repeat edit waits for the owner's approval
/// card (the 202), everything else keeps the ordinary write budget.
pub(crate) fn change_timeout(action: &str, change: &ScheduleChange) -> std::time::Duration {
    if action == "edit" && change.repeat.is_some() {
        REPEAT_EDIT_TIMEOUT
    } else {
        WRITE_TIMEOUT
    }
}

/// A move target as the PC takes it: the literal `"todo"` for the to-do list
/// itself, else a named list's tidied name. `None` is never sent - the page
/// always names its target, so a missing one is refused before any request.
fn move_target(raw: &str) -> Result<String, String> {
    let t = raw.trim().to_ascii_lowercase();
    if t.is_empty() || t == "todo" || t == "to-do" {
        return Ok("todo".to_string());
    }
    list_name(raw).ok_or_else(|| "That is not one of your lists.".to_string())
}

/// The body of ONE Phase 2 change: `edit`, `move` or `reorder`, built only from
/// the fields the page gave and checked against the PC's own limits before any
/// request is made (the PC checks them again and is the authority).
///
/// THE VERB IS CHOSEN HERE (Lead, 2026-10-22): an `edit` whose ONLY field is a
/// list becomes the backend's `move` verb, exactly as a list-only change must;
/// a list riding with text/when/repeat stays inside the one `edit`.
pub(crate) fn change_body(
    id: &str,
    action: &str,
    change: &ScheduleChange,
) -> Result<serde_json::Value, String> {
    if !valid_id(id) {
        return Err("That is not one job.".to_string());
    }
    match action {
        "move" => {
            let raw = change
                .list
                .as_deref()
                .ok_or_else(|| "Choose which list.".to_string())?;
            Ok(serde_json::json!({ "id": id, "do": "move", "list": move_target(raw)? }))
        }
        "reorder" => {
            let rank = change.rank.ok_or_else(|| "Which position?".to_string())?;
            if !(0..=MAX_REORDER_RANK).contains(&rank) {
                return Err("That position is not on the list.".to_string());
            }
            Ok(serde_json::json!({ "id": id, "do": "reorder", "rank": rank }))
        }
        "edit" => {
            let mut body = serde_json::Map::new();
            body.insert("id".into(), serde_json::json!(id));
            body.insert("do".into(), serde_json::json!("edit"));
            let mut fields = 0usize;
            let mut has_list = false;
            let mut timed = Vec::new();
            if let Some(raw) = change.text.as_deref() {
                let t = raw.split_whitespace().collect::<Vec<_>>().join(" ");
                if t.is_empty() {
                    return Err("Type what to change it to first.".to_string());
                }
                if t.chars().count() > MAX_TEXT {
                    return Err(format!(
                        "That is longer than {MAX_TEXT} characters - say it more briefly."
                    ));
                }
                body.insert("text".into(), serde_json::json!(t));
                fields += 1;
            }
            let date = change
                .date
                .as_deref()
                .map(str::trim)
                .filter(|d| !d.is_empty());
            let time = change
                .time
                .as_deref()
                .map(str::trim)
                .filter(|t| !t.is_empty());
            if date.is_some() != time.is_some() {
                return Err("Give the date and time together.".to_string());
            }
            if let (Some(date), Some(time)) = (date, time) {
                if !date_shape(date) {
                    return Err("A date looks like 2030-09-15.".to_string());
                }
                let at =
                    hhmm(time).ok_or_else(|| "Write the time as HH:MM, like 18:00.".to_string())?;
                body.insert("date".into(), serde_json::json!(date));
                body.insert("time".into(), serde_json::json!(at));
                timed.push("date/time");
                fields += 1;
            }
            if let Some(at) = change.at {
                if !at.is_finite() || at <= 0.0 {
                    return Err("Give the time as the PC's own clock.".to_string());
                }
                body.insert("at".into(), serde_json::json!(at));
                timed.push("at");
                fields += 1;
            }
            if let Some(seconds) = change.seconds {
                if !seconds.is_finite() || seconds <= 0.0 {
                    return Err("A timer needs a positive number of seconds.".to_string());
                }
                if seconds > MAX_TIMER_SECONDS {
                    return Err("A timer is for today - at most 24 hours.".to_string());
                }
                body.insert("seconds".into(), serde_json::json!(seconds));
                timed.push("seconds");
                fields += 1;
            }
            if timed.len() > 1 {
                return Err("give one time: when, at, date+time or seconds".to_string());
            }
            if let Some(rule) = change.repeat.as_ref() {
                body.insert("repeat".into(), repeat_rule(rule)?);
                fields += 1;
            }
            if let Some(raw) = change.list.as_deref() {
                body.insert("list".into(), serde_json::json!(move_target(raw)?));
                has_list = true;
                fields += 1;
            }
            if fields == 0 {
                return Err("an edit needs at least one field to change".to_string());
            }
            if has_list && fields == 1 {
                // The ONLY change is the list: the backend's own `move` verb.
                let list = body.remove("list").unwrap_or(serde_json::json!("todo"));
                return Ok(serde_json::json!({ "id": id, "do": "move", "list": list }));
            }
            Ok(serde_json::Value::Object(body))
        }
        _ => Err(format!("\"{action}\" is not something a job can change.")),
    }
}

/// The HUD Reminders tab's own sentence for a value it cannot send.
pub(crate) const REMINDERS_FORM_HINT: &str =
    "The Reminders tab adds a reminder, a timer, an alarm or a to-do item.";

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

/// A job id as the PC makes them: "s" and ten hex digits.
pub(crate) fn valid_id(id: &str) -> bool {
    id.len() == 11
        && id.starts_with('s')
        && id[1..]
            .chars()
            .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
}

/// The Today board's own read (GTD-2, 2026-10-18; backend `jarvis_today.py`,
/// answered by the already-wrapped `jarvis_brain_reads.py`): due reminders,
/// the first open step of each active goal/project work list, and the
/// said-I'd-do proposals. It is ADDED to this list's answer under `cockpit`;
/// when the board has nothing to show the key is not added at all, and a
/// failed board read never fails the list itself.
const COCKPIT_PATH: &str = "/api/today/cockpit";

/// The board sections that are a list; each is copied only when it has
/// something in it.
const COCKPIT_KEYS: &[&str] = &["due_reminders", "active_next_steps", "proposals"];

/// [`brain_schedule`]'s reading of the answer.
pub(crate) fn list_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| {
                v.get("jobs").is_some_and(|j| j.is_array())
                    && v.get("todo").is_some_and(|t| t.is_array())
            })
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 || status == 501 {
        return Ok(serde_json::json!({ "available": false, "why": SCHEDULE_MISSING }));
    }
    Err(commands::backend_refusal(status, body))
}

/// [`brain_schedule_act`]'s and [`brain_schedule_add_todo`]'s reading.
pub(crate) fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body).ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 {
        let reason =
            parsed(body).and_then(|v| v.get("reason").and_then(|r| r.as_str()).map(str::to_string));
        return Err(if reason.as_deref() == Some("no_such_job") {
            NO_SUCH_JOB.to_string()
        } else {
            SCHEDULE_TOO_OLD.to_string()
        });
    }
    if status == 501 {
        return Err(SCHEDULE_TOO_OLD.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// The list with every reminder's and to-do item's words taken out, for
/// while the private lists are hidden (lock.rs). Kinds, times and counts
/// stay: they say nothing about the owner, and a timer should still count
/// down. A named list's name is the owner's words too ("presents for Sam"):
/// each becomes "hidden-1", "hidden-2"... here, the same on its items and in
/// `lists`, so the page can still group them and cannot read the names.
pub(crate) fn redact_list(mut list: serde_json::Value) -> serde_json::Value {
    let mut count = 0usize;
    let mut names: Vec<String> = Vec::new();
    let mut stand_in = |name: &str| -> String {
        let i = match names.iter().position(|n| n == name) {
            Some(i) => i,
            None => {
                names.push(name.to_string());
                names.len() - 1
            }
        };
        format!("hidden-{}", i + 1)
    };
    if let Some(obj) = list.as_object_mut() {
        if let Some(serde_json::Value::Array(lists)) = obj.get_mut("lists") {
            for l in lists.iter_mut() {
                if let Some(o) = l.as_object_mut() {
                    let name = o
                        .get("name")
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_string();
                    o.insert("name".into(), serde_json::json!(stand_in(&name)));
                    o.insert("title".into(), serde_json::json!(""));
                }
            }
        }
        for key in ["jobs", "todo", "went_off"] {
            if let Some(serde_json::Value::Array(items)) = obj.get_mut(key) {
                for item in items.iter_mut() {
                    if let Some(o) = item.as_object_mut() {
                        if o.get("text")
                            .and_then(|t| t.as_str())
                            .is_some_and(|t| !t.is_empty())
                        {
                            count += 1;
                        }
                        o.insert("text".into(), serde_json::json!(""));
                        // A "tell me when"'s notice names the sender or the
                        // device, from the same words.
                        if o.contains_key("alert") {
                            o.insert("alert".into(), serde_json::json!(""));
                        }
                        // ... and so does its "cannot look" notice (2026-09-28).
                        if o.contains_key("broken") {
                            o.insert("broken".into(), serde_json::json!(""));
                        }
                        // A reminder for next time's subject is the owner's
                        // words too (jarvis_next_time.py, 2026-09-28).
                        if o.contains_key("about") {
                            o.insert("about".into(), serde_json::json!(""));
                        }
                        // A reminder's ONE action (2026-10-27) is the owner's
                        // words a third time: the web address he meant to open,
                        // the file's path (which names a folder of his), or the
                        // note's own text - and the Open button is drawn from
                        // it. Every payload value is blanked and only the KIND
                        // stays (a fixed word from a closed list, which says
                        // nothing about him), so the page cannot draw a control
                        // that would open what it may not show.
                        if let Some(serde_json::Value::Object(action)) = o.get_mut("action") {
                            let kind = action
                                .get("kind")
                                .and_then(|v| v.as_str())
                                .unwrap_or("")
                                .to_string();
                            action.clear();
                            action.insert("kind".into(), serde_json::json!(kind));
                        }
                        o.insert("hidden".into(), serde_json::json!(true));
                        let named = o
                            .get("list")
                            .and_then(|v| v.as_str())
                            .filter(|s| !s.is_empty())
                            .map(str::to_string);
                        if let Some(name) = named {
                            o.insert("list".into(), serde_json::json!(stand_in(&name)));
                        }
                    }
                }
            }
        }
        // The Today board's words are the owner's own too (GTD-2): reminder
        // titles, goal and project steps, said-I'd-do proposals. Each list is
        // emptied and counted, exactly like the jobs above; the board's own
        // yes/no switch state stays (it says nothing about the owner).
        if let Some(serde_json::Value::Object(board)) = obj.get_mut("cockpit") {
            for key in COCKPIT_KEYS {
                if let Some(serde_json::Value::Array(items)) = board.get_mut(*key) {
                    count += items.len();
                    items.clear();
                }
            }
        }
        obj.insert("hidden".into(), serde_json::json!(true));
        obj.insert("hidden_count".into(), serde_json::json!(count));
    }
    list
}

/// The Today board added to this list's answer, with every existing field
/// untouched. Only the board's own sections are copied, and only when they
/// have something in them (`cockpit` is not added for a quiet day, and the
/// switch's own state and the honest empty `rollover_cards` ride along so the
/// page can draw its opt-in row). A missing board changes nothing.
pub(crate) fn merge_cockpit(
    mut list: serde_json::Value,
    cockpit: Option<serde_json::Value>,
) -> serde_json::Value {
    let Some(serde_json::Value::Object(board)) = cockpit else {
        return list;
    };
    let Some(out) = list.as_object_mut() else {
        return list;
    };
    let mut section = serde_json::Map::new();
    if board.get("available") == Some(&serde_json::Value::Bool(true)) {
        for key in ["unspoken_commitments_enabled", "rollover_cards"] {
            if let Some(value) = board.get(key) {
                section.insert((*key).to_string(), value.clone());
            }
        }
        for key in COCKPIT_KEYS {
            if let Some(items) = board.get(*key) {
                if items.as_array().is_some_and(|a| !a.is_empty()) {
                    section.insert((*key).to_string(), items.clone());
                }
            }
        }
    }
    if !section.is_empty() {
        out.insert("cockpit".to_string(), serde_json::Value::Object(section));
    }
    list
}

/// The body of one change: one id, one action, nothing else.
pub(crate) fn act_body(
    id: &str,
    action: &str,
    seconds: Option<f64>,
) -> Result<serde_json::Value, String> {
    if !valid_id(id) {
        return Err("That is not one job.".to_string());
    }
    if !ACTIONS.contains(&action) {
        return Err(format!("\"{action}\" is not something a job can do."));
    }
    if action == "add_time" {
        let s = seconds.filter(|s| s.is_finite() && *s != 0.0);
        return match s {
            Some(s) => Ok(serde_json::json!({ "id": id, "do": action, "seconds": s })),
            None => Err("How much time?".to_string()),
        };
    }
    if action == "snooze" {
        let s = seconds.unwrap_or(SNOOZE_SECONDS);
        if !s.is_finite() || !(SNOOZE_MIN..=SNOOZE_MAX).contains(&s) {
            return Err("A snooze is from 1 minute to 24 hours.".to_string());
        }
        return Ok(serde_json::json!({ "id": id, "do": action, "seconds": s }));
    }
    Ok(serde_json::json!({ "id": id, "do": action }))
}

/// A named list's name as the PC keeps it ("shopping"): lower case, one to
/// three plain words. None for anything else - the PC checks the same, and
/// says why in its own words.
pub(crate) fn list_name(v: &str) -> Option<String> {
    let t = v.split_whitespace().collect::<Vec<_>>().join(" ");
    let words: Vec<&str> = t.split(' ').collect();
    let plain = |w: &&str| {
        w.chars().next().is_some_and(|c| c.is_ascii_lowercase())
            && w.chars()
                .all(|c| c.is_ascii_lowercase() || c == '\'' || c == '-')
    };
    (!t.is_empty() && t.len() <= MAX_LIST_NAME && words.len() <= 3 && words.iter().all(plain))
        .then_some(t)
}

/// The body of one new to-do item - on a named list when `list` says one.
pub(crate) fn todo_body(text: &str, list: Option<&str>) -> Result<serde_json::Value, String> {
    let t = text.split_whitespace().collect::<Vec<_>>().join(" ");
    if t.is_empty() {
        return Err("Type what to add first.".to_string());
    }
    if t.chars().count() > MAX_TEXT {
        return Err(format!(
            "That is longer than {MAX_TEXT} characters - say it more briefly."
        ));
    }
    match list {
        None => Ok(serde_json::json!({ "kind": "todo", "text": t })),
        Some(l) => {
            let name = list_name(l).ok_or_else(|| "That is not one of your lists.".to_string())?;
            Ok(serde_json::json!({ "kind": "todo", "text": t, "list": name }))
        }
    }
}

/// The body that clears ONE named list: its name and how many items the
/// page showed. Never the to-do list (it has no name), never "all".
pub(crate) fn clear_list_body(list: &str, count: u32) -> Result<serde_json::Value, String> {
    let name = list_name(list).ok_or_else(|| "That is not one of your lists.".to_string())?;
    if count == 0 {
        return Err("There is nothing on that list.".to_string());
    }
    Ok(serde_json::json!({ "do": "clear_list", "list": name, "count": count }))
}

/// A time of day as the PC wants it: "HH:MM", 24-hour, tidied ("1:00" ->
/// "01:00"). None when it is not one.
fn hhmm(v: &str) -> Option<String> {
    let (h, m) = v.trim().split_once(':')?;
    if h.is_empty() || h.len() > 2 || m.len() != 2 {
        return None;
    }
    if !h.chars().all(|c| c.is_ascii_digit()) || !m.chars().all(|c| c.is_ascii_digit()) {
        return None;
    }
    let (h, m): (u32, u32) = (h.parse().ok()?, m.parse().ok()?);
    (h <= 23 && m <= 59).then(|| format!("{h:02}:{m:02}"))
}

/// Both apps' words for two times that cannot be a standby schedule.
pub(crate) const STANDBY_BAD_TIMES: &str =
    "Write each time as HH:MM, like 01:00, and pick two different times.";

/// The body of a new standby schedule: every day, from `start` to `end`.
/// The PC checks the same things and says so; this refuses early, in the
/// words both apps use.
pub(crate) fn standby_body(start: &str, end: &str) -> Result<serde_json::Value, String> {
    match (hhmm(start), hhmm(end)) {
        (Some(at), Some(until)) if at != until => Ok(serde_json::json!({
            "kind": "standby",
            "repeat": { "every": "day", "at": at, "until": until },
        })),
        _ => Err(STANDBY_BAD_TIMES.to_string()),
    }
}

/// The longest a Today card's words may be (jarvis_today.MAX_TEXT).
pub(crate) const TODAY_MAX_TEXT: usize = 80;

/// The body of a new Today card (backend jarvis_today.py, 2026-09-28): the
/// owner's words, shown from `at` ("HH:MM") on `days` (0 = Monday). All
/// seven days is "every day", Monday to Friday is "every weekday", anything
/// else "every week" on those days - the scheduler's own rules. The PC
/// checks the same things and says so; this refuses early, in the words
/// both apps use (today.js, net/Today.kt).
pub(crate) fn today_body(text: &str, at: &str, days: &[u8]) -> Result<serde_json::Value, String> {
    let t = text.split_whitespace().collect::<Vec<_>>().join(" ");
    if t.is_empty() {
        return Err("A Today card needs some words: what should it say?".to_string());
    }
    if t.chars().count() > TODAY_MAX_TEXT {
        return Err(format!(
            "A Today card is at most {TODAY_MAX_TEXT} characters - say it more briefly."
        ));
    }
    let at = hhmm(at).ok_or_else(|| "Write the time as HH:MM, like 07:00.".to_string())?;
    let mut d: Vec<u8> = days.iter().copied().filter(|x| *x <= 6).collect();
    d.sort_unstable();
    d.dedup();
    if d.is_empty() {
        return Err("Pick at least one day.".to_string());
    }
    let repeat = if d.len() == 7 {
        serde_json::json!({ "every": "day", "at": at })
    } else if d == [0, 1, 2, 3, 4] {
        serde_json::json!({ "every": "weekday", "at": at })
    } else {
        serde_json::json!({ "every": "week", "at": at, "days": d })
    };
    Ok(serde_json::json!({ "kind": "today", "text": t, "repeat": repeat }))
}

/// The ONE action a reminder may carry (2026-10-27), as the HUD's own form
/// sends it: a checked SHAPE only.
///
/// The backend owns the security rules - `https` only, the folder allow-list,
/// the extension list, the closed task list - and refuses anything it does not
/// accept with one plain sentence, which the page shows as it is. The shape is
/// checked here as well so a body this app cannot mean never leaves the app in
/// the first place: one kind from the four, exactly its one payload key, and one
/// non-empty string.
fn action_body(action: &serde_json::Value) -> Result<serde_json::Value, String> {
    let obj = action
        .as_object()
        .ok_or_else(|| "That is not one reminder action.".to_string())?;
    let kind = obj.get("kind").and_then(|v| v.as_str()).unwrap_or("");
    let key = match kind {
        "show-note" => "note",
        "open-webpage" => "url",
        "open-file" => "path",
        "run-task" => "task",
        _ => return Err("Pick what the reminder should do, or Nothing.".to_string()),
    };
    if obj.len() != 2 || !obj.contains_key(key) {
        return Err("A reminder has one action, and one thing it points at.".to_string());
    }
    let value = obj
        .get(key)
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    if value.is_empty() {
        return Err("Pick the thing to open first, or choose Nothing.".to_string());
    }
    Ok(serde_json::json!({ "kind": kind, key: value }))
}

/// The HUD Reminders tab's form -> the body of `POST /api/schedule/add`.
/// ONE item at a time, in the four plain kinds the form offers, and nothing
/// the backend does not already take for them. `notes` is not a field of its
/// own on the PC (a reminder has ONE free-text field), so it is carried as
/// the last sentence of the item's words, after " - ": the PR says so.
///
/// This is PHASE 1 of the owner's Reminders request: adding items and the
/// existing one-job actions. Editing an item's words/time/list and
/// reordering need backend actions and therefore a later deploy (Phase 2);
/// this builder deliberately has no body for them.
///
/// `action` (2026-10-27) is the owner's "then open / then do" choice, and only
/// a REMINDER may carry one - the same guard `jarvis_schedule.add_at` makes, so
/// the refusal reads the same from either side.
//
// One argument per form field (see `hud_schedule_add`): the tests assert the
// flat body each combination makes, and the fields are the page's own.
#[allow(clippy::too_many_arguments)]
pub(crate) fn hud_add_body(
    kind: &str,
    text: Option<&str>,
    notes: Option<&str>,
    seconds: Option<f64>,
    date: Option<&str>,
    time: Option<&str>,
    repeat: Option<&serde_json::Value>,
    list: Option<&str>,
    action: Option<&serde_json::Value>,
) -> Result<serde_json::Value, String> {
    let kind = kind.trim().to_ascii_lowercase();
    let words = joined_words(text, notes)?;
    if action.is_some() && kind != "reminder" {
        return Err("Only a reminder can carry an action.".to_string());
    }
    match kind.as_str() {
        "todo" => todo_body(&words, list),
        "timer" => {
            let seconds = seconds.ok_or_else(|| "A timer needs how long it runs.".to_string())?;
            if !seconds.is_finite() || seconds <= 0.0 {
                return Err("A timer needs a positive number of seconds.".to_string());
            }
            if seconds > MAX_TIMER_SECONDS {
                return Err("A timer is for today - at most 24 hours.".to_string());
            }
            let mut body = serde_json::json!({ "kind": "timer", "seconds": seconds });
            if !words.is_empty() {
                body["text"] = serde_json::json!(words);
            }
            Ok(body)
        }
        "alarm" | "reminder" => {
            let checked = match action {
                Some(raw) => Some(action_body(raw)?),
                None => None,
            };
            if let Some(rule) = repeat {
                let mut body = serde_json::json!({ "kind": kind, "repeat": repeat_rule(rule)? });
                if !words.is_empty() {
                    body["text"] = serde_json::json!(words);
                }
                if let Some(action) = checked {
                    body["action"] = action;
                }
                return Ok(body);
            }
            let date = date
                .map(str::trim)
                .filter(|d| !d.is_empty())
                .ok_or_else(|| "Pick a date, like 2030-09-15.".to_string())?;
            if !date_shape(date) {
                return Err("A date looks like 2030-09-15.".to_string());
            }
            let at = time
                .and_then(hhmm)
                .ok_or_else(|| "Write the time as HH:MM, like 18:00.".to_string())?;
            let mut body = serde_json::json!({ "kind": kind, "date": date, "time": at });
            if !words.is_empty() {
                body["text"] = serde_json::json!(words);
            }
            if let Some(action) = checked {
                body["action"] = action;
            }
            Ok(body)
        }
        _ => Err(REMINDERS_FORM_HINT.to_string()),
    }
}

/// The words an item is added with: its text, then its notes when there are
/// any (one field on the PC), tidied and kept to the PC's limit.
fn joined_words(text: Option<&str>, notes: Option<&str>) -> Result<String, String> {
    let tidy = |v: Option<&str>| {
        v.map(|s| s.split_whitespace().collect::<Vec<_>>().join(" "))
            .unwrap_or_default()
    };
    let mut out = tidy(text);
    let notes = tidy(notes);
    if !notes.is_empty() {
        if out.is_empty() {
            out = notes;
        } else {
            out = format!("{out} - {notes}");
        }
    }
    if out.chars().count() > MAX_TEXT {
        return Err(format!(
            "That is longer than {MAX_TEXT} characters - say it more briefly."
        ));
    }
    Ok(out)
}

/// A date as the PC writes one ("2030-09-15"), before the PC's own calendar
/// check. Only the shape is judged here - the backend owns "not a date".
fn date_shape(v: &str) -> bool {
    let b = v.as_bytes();
    b.len() == 10
        && b[4] == b'-'
        && b[7] == b'-'
        && b.iter()
            .enumerate()
            .all(|(i, c)| (i == 4 || i == 7) || c.is_ascii_digit())
}

/// The repeat rule the HUD form offers, tidied the way `jarvis_schedule`'s
/// `check_rule` does it: every day, every weekday, or every week on the
/// picked days. The PC checks it again; this refuses early in plain words.
fn repeat_rule(rule: &serde_json::Value) -> Result<serde_json::Value, String> {
    let rule = rule.as_object().ok_or_else(|| {
        "A repeat is every day, every weekday, or every week on some days.".to_string()
    })?;
    if rule.contains_key("until") {
        return Err("Only a standby schedule has an end time.".to_string());
    }
    let every = rule
        .get("every")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_ascii_lowercase();
    match every.as_str() {
        "day" | "weekday" => {
            let at = rule
                .get("at")
                .and_then(|v| v.as_str())
                .and_then(hhmm)
                .ok_or_else(|| "Write the time as HH:MM, like 07:30.".to_string())?;
            Ok(serde_json::json!({ "every": every, "at": at }))
        }
        "week" => {
            let at = rule
                .get("at")
                .and_then(|v| v.as_str())
                .and_then(hhmm)
                .ok_or_else(|| "Write the time as HH:MM, like 07:30.".to_string())?;
            let days = rule.get("days").and_then(|v| v.as_array()).ok_or_else(|| {
                "A weekly repeat needs its days, 0 (Monday) to 6 (Sunday).".to_string()
            })?;
            let mut out: Vec<u8> = Vec::new();
            for day in days {
                let n = day.as_u64().filter(|n| *n <= 6).ok_or_else(|| {
                    "A weekly repeat needs its days, 0 (Monday) to 6 (Sunday).".to_string()
                })?;
                out.push(n as u8);
            }
            out.sort_unstable();
            out.dedup();
            if out.is_empty() {
                return Err("Pick at least one day.".to_string());
            }
            Ok(serde_json::json!({ "every": "week", "at": at, "days": out }))
        }
        _ => Err("A repeat is every day, every weekday, or every week on some days.".to_string()),
    }
}

/// Whether a `schedule` event that went off should be shown at all. The PC
/// says `"notify": false` for a kind that tells nobody - the standby
/// schedule at 01:00 - and then there is no toast (the phone shows no
/// notification either).
pub(crate) fn wants_toast(data: &serde_json::Value) -> bool {
    data.get("notify").and_then(|v| v.as_bool()) != Some(false)
}

/// "Tell me when" - what a locked screen, and a toast while App lock or the
/// hidden lists are on, ever says about one (jarvis_tellme.LOCK_SCREEN; the
/// phone's `Schedule.TELLME_LOCK_SCREEN`).
pub(crate) const TELLME_LOCK_SCREEN: &str =
    "Jarvis: something you asked to be told about happened.";

/// A "tell me when" that cannot look (2026-09-28) - what a toast says about
/// it while App lock or the hidden lists are on (jarvis_tellme's
/// BROKEN_LOCK_SCREEN; the phone's `Schedule.TELLME_BROKEN_LOCK_SCREEN`).
pub(crate) const TELLME_BROKEN_LOCK_SCREEN: &str =
    "Jarvis: a \"tell me when\" cannot look right now.";

/// (title, body) for a "tell me when" that cannot look: the job's `broken`
/// sentence (made on the PC from the owner's own words and fixed words
/// about the problem), or only the generic words when `private` or when
/// there is none.
pub(crate) fn broken_words(job: Option<&serde_json::Value>, private: bool) -> (String, String) {
    let title = toast_title("tellme").to_string();
    let said = job
        .and_then(|j| j.get("broken"))
        .and_then(|v| v.as_str())
        .map(str::trim)
        .unwrap_or("");
    if private || said.is_empty() {
        return (title, TELLME_BROKEN_LOCK_SCREEN.to_string());
    }
    (title, said.to_string())
}

/// The toast's title for a kind - both apps' words.
pub(crate) fn toast_title(kind: &str) -> &'static str {
    match kind {
        "timer" => "Timer done",
        "alarm" => "Alarm",
        "reminder" => "Reminder",
        "todo" => "To-do",
        "briefing" => "Morning briefing",
        "tellme" => "Tell me when",
        _ => "Jarvis",
    }
}

/// Whether this keeps ringing until it is dismissed: an alarm going off,
/// and a "tell me when" the owner marked urgent. Everything else rings once.
pub(crate) fn rings(kind: &str, data: &serde_json::Value) -> bool {
    kind == "alarm"
        || (kind == "tellme" && data.get("urgent").and_then(|v| v.as_bool()) == Some(true))
}

/// What a locked screen may show for a kind, when the PC did not say. The
/// PC's own words are `lock_screen` on the job (jarvis_schedule.KINDS).
pub(crate) fn lock_screen_words(kind: &str) -> &'static str {
    match kind {
        "timer" => "Jarvis: your timer is done.",
        "alarm" => "Jarvis: alarm.",
        "reminder" => "Jarvis: a reminder is due.",
        "todo" => "Jarvis: a to-do item is due.",
        "briefing" => "Jarvis: your morning briefing is ready.",
        "tellme" => TELLME_LOCK_SCREEN,
        _ => "Jarvis: something is due.",
    }
}

/// (title, body) for a job that went off. `private`: App lock is on or the
/// private lists are hidden - then the body is the lock-screen words only,
/// never the job's own.
pub(crate) fn toast_words(
    kind: &str,
    job: Option<&serde_json::Value>,
    private: bool,
) -> (String, String) {
    let title = toast_title(kind).to_string();
    let fallback = job
        .and_then(|j| j.get("lock_screen"))
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| lock_screen_words(kind))
        .to_string();
    let Some(job) = job else {
        return (title, fallback);
    };
    if private {
        return (title, fallback);
    }
    // A "tell me when" says its `alert` - made on the PC from the owner's
    // own words - never its `text`, which is what is watched.
    let field = if kind == "tellme" { "alert" } else { "text" };
    let text = job.get(field).and_then(|v| v.as_str()).unwrap_or("").trim();
    let mut body = if !text.is_empty() {
        if kind == "timer" {
            format!("The {text} timer is done.")
        } else {
            text.to_string()
        }
    } else {
        fallback
    };
    if let Some(missed) = job.get("missed").and_then(|v| v.as_str()) {
        body.push_str(&format!(" ({missed} - the PC was off or asleep.)"));
    }
    (title, body)
}

/// How late (seconds after it went off) this app may still ring for a job
/// it hears about. Later than this - the app was restarted, or the PC's
/// event reached it late - it shows a quiet "missed at" notice instead of
/// ringing as if it were happening now (the owner's decision of
/// 2026-09-26; the phone's `Schedule.LATE_RING_LIMIT_S`).
pub(crate) const LATE_RING_LIMIT_S: i64 = 10 * 60;

/// Whether a job that went off at `fired_at` (seconds; 0 = unknown) is heard
/// too late to ring at `now`. Unknown is not late: the job could not be read,
/// so it is shown as before.
pub(crate) fn heard_late(fired_at: i64, now: i64) -> bool {
    fired_at > 0 && now - fired_at > LATE_RING_LIMIT_S
}

/// Whether a job is late, using `age_s` sent directly by the PC first
/// to prevent clock skew and catch stale alarms when fired_at is 0.
pub(crate) fn is_late(fired_at: i64, now: i64, age_s: Option<f64>) -> bool {
    if let Some(age) = age_s {
        if age >= 0.0 && age > LATE_RING_LIMIT_S as f64 {
            return true;
        }
    }
    heard_late(fired_at, now)
}

/// The quiet notice's words: when it went off (the PC's own clock words,
/// `went_off_at`), then what it was - both apps' words.
pub(crate) fn missed_words(went_off_at: &str, body: &str) -> String {
    let at = went_off_at.trim();
    let head = if at.is_empty() {
        "Missed earlier.".to_string()
    } else {
        format!("Missed at {at}.")
    };
    let body = body.trim();
    if body.is_empty() {
        head
    } else {
        format!("{head} {body}")
    }
}

pub(crate) fn now_secs() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

/// The jobs already toasted, by id and the time they went off, so a replayed
/// event after a reconnect does not toast twice.
static TOASTED: Mutex<Option<HashSet<(String, i64)>>> = Mutex::new(None);

/// The "shown once" key's time part: when it went off, as read from the
/// job - or, when the job could not be read (`at` 0), this event's own id
/// (`_event`, put in by stream.rs), so two failed reads of a repeating job
/// on different days are not taken for the same firing and the later one
/// dropped. `None` (neither known): shown, without remembering it.
pub(crate) fn shown_key(at: i64, data: &serde_json::Value) -> Option<i64> {
    if at > 0 {
        return Some(at);
    }
    data.get("_event")
        .and_then(|v| v.as_u64())
        .and_then(|e| i64::try_from(e).ok())
        .map(|e| -e)
}

/// The event's own data, with its id as `_event` - for [`shown_key`]. Only
/// the copy handed to a toast; the frame the windows get is unchanged.
pub(crate) fn with_event_id(data: &serde_json::Value, id: Option<u64>) -> serde_json::Value {
    let mut data = data.clone();
    if let (Some(obj), Some(id)) = (data.as_object_mut(), id) {
        obj.insert("_event".to_string(), serde_json::json!(id));
    }
    data
}

pub(crate) fn first_time(id: &str, fired_at: i64) -> bool {
    let mut guard = TOASTED.lock().unwrap_or_else(|e| e.into_inner());
    let set = guard.get_or_insert_with(HashSet::new);
    if set.len() > 500 {
        set.clear();
    }
    set.insert((id.to_string(), fired_at))
}

/// A `schedule` event said a job went off: read its words by id and show a
/// toast. Called on its own task by stream.rs, so a slow read never holds
/// the event stream up. Nothing is shown for a job that went off more than a
/// day ago (the PC keeps them that long) or one already shown.
pub async fn toast_fired(app: AppHandle, base: String, data: serde_json::Value) {
    if !wants_toast(&data) {
        return;
    }
    let Some(id) = data.get("id").and_then(|v| v.as_str()).map(str::to_string) else {
        return;
    };
    if !valid_id(&id) {
        return;
    }
    let kind = data
        .get("kind")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    // A morning briefing is toasted when it is READY (briefing.rs
    // toast_ready), not when its time comes: it takes a moment to put
    // together, and the toast must not arrive before the briefing does.
    if kind == "briefing" {
        return;
    }
    // The owner's own switches, and quiet hours (notifications.rs). Asked
    // before the job is read: a kind he switched off costs no round trip, and
    // a reminder quiet hours hold back is never fetched only to be thrown
    // away. An ALARM is never held back by quiet hours - that module's doc
    // says why, and its tests walk every minute of the day.
    let toast_kind = Kind::for_event(&kind, false);
    if !notifications::may_post(&app, toast_kind) {
        return;
    }
    let job = read_job(&app, &base, &id).await;
    let fired_at = job
        .as_ref()
        .and_then(|j| j.get("fired_at"))
        .and_then(|v| v.as_f64())
        .unwrap_or(0.0) as i64;
    if let Some(key) = shown_key(fired_at, &data) {
        if !first_time(&id, key) {
            return;
        }
    }
    let security = crate::lock::current(&app);
    let private = security.app_lock || crate::lock::private_hidden(&app);
    let (title, mut body) = toast_words(&kind, job.as_ref(), private);
    // A reminder that opens something (2026-10-27): the notice names the target
    // IN FULL before anything opens, and the Open button carries the job id
    // only. Nothing opens by itself. While App lock or the private lists are
    // hidden there is no target to show, so there is no button either -
    // `redact_list` blanks the action for the HUD, and `private` is what stops
    // the toast drawing a control whose target the owner may not see.
    let opening = open_notice(job.as_ref(), private);
    if let Some((line, _)) = opening.as_ref() {
        body = format!("{body} {line}");
    }
    let age_s = job
        .as_ref()
        .and_then(|j| j.get("age_s"))
        .and_then(|v| v.as_f64())
        .or_else(|| data.get("age_s").and_then(|v| v.as_f64()));
    // Heard more than ten minutes after it went off (the app was closed,
    // or restarted and replayed the event): a quiet notice saying when,
    // never a ringing alarm as if it were happening now, and no Snooze.
    if is_late(fired_at, now_secs(), age_s) {
        let at = job
            .as_ref()
            .and_then(|j| j.get("went_off_at"))
            .and_then(|v| v.as_str())
            .unwrap_or("");
        show_quiet(&app, toast_kind, &title, &missed_words(at, &body));
        return;
    }
    // A timer, alarm or reminder gets a Snooze button (2026-09-25) - on
    // Windows, through winrt_toast.rs; anything else, or anywhere else, the
    // plain toast. The button carries the id only. An alarm also keeps
    // ringing until it is dismissed or snoozed.
    let snooze = SNOOZABLE
        .contains(&kind.as_str())
        .then_some((id.as_str(), SNOOZE_LABEL));
    show(
        &app,
        toast_kind,
        &title,
        &body,
        rings(&kind, &data),
        snooze,
        opening.as_ref().map(|(_, job)| job.as_str()),
    );
}

/// What ONE fired reminder's action opens, as the notice says it: the words to
/// put in the toast's body, and the job id its Open button carries.
///
/// `None` when there is nothing to open - no action, a note, a task - and while
/// the private lists are hidden: a button whose target cannot be shown must not
/// be drawn, because a control that opens something the owner cannot see is the
/// one thing this feature must never offer. The PC's own second check
/// (`action_problem`, `jarvis_schedule._action_problem`) is honoured here too,
/// so a file that has gone or a folder that was removed shows no button at all.
pub(crate) fn open_notice(
    job: Option<&serde_json::Value>,
    private: bool,
) -> Option<(String, String)> {
    if private {
        return None;
    }
    let job = job?;
    let action = job.get("action")?.as_object()?;
    let key = match action.get("kind")?.as_str()? {
        "open-webpage" => "url",
        "open-file" => "path",
        _ => return None,
    };
    if job
        .get("action_problem")
        .and_then(|v| v.as_str())
        .is_some_and(|p| !p.is_empty())
    {
        return None;
    }
    let target = action.get(key)?.as_str()?;
    if target.is_empty() {
        return None;
    }
    let id = job.get("id")?.as_str()?;
    if !valid_id(id) {
        return None;
    }
    Some((format!("This opens: {target}"), id.to_string()))
}

/// A "tell me when" matched (`{"id", "kind": "tellme", "state": "matched",
/// "urgent"}`): read its `alert` by id and show it - ringing until dismissed
/// when it is urgent. Only ever a notice: nothing here acts, and the toast's
/// only button is Windows' own Dismiss. Once per match, even when a
/// reconnect replays the event. A late urgent alert becomes a quiet "Missed"
/// notice (owner decision, 2026-09-30).
pub async fn toast_matched(app: AppHandle, base: String, data: serde_json::Value) {
    if !wants_toast(&data) {
        return;
    }
    let Some(id) = data.get("id").and_then(|v| v.as_str()).map(str::to_string) else {
        return;
    };
    if !valid_id(&id) || data.get("kind").and_then(|v| v.as_str()) != Some("tellme") {
        return;
    }
    // An urgent match rings until it is dismissed, exactly like an alarm, so
    // it rides the "Alarms and urgent alerts" switch; a plain match has no
    // switch of its own and is shown as before (notifications.rs).
    let urgent = data.get("urgent").and_then(|v| v.as_bool()) == Some(true);
    let toast_kind = Kind::for_event("tellme", urgent);
    if !notifications::may_post(&app, toast_kind) {
        return;
    }
    let job = read_job(&app, &base, &id).await;
    let at = job
        .as_ref()
        .and_then(|j| j.get("alert_at"))
        .and_then(|v| v.as_f64())
        .unwrap_or(0.0) as i64;
    if let Some(key) = shown_key(at, &data) {
        if !first_time(&format!("{id}#match"), key) {
            return;
        }
    }
    let security = crate::lock::current(&app);
    let private = security.app_lock || crate::lock::private_hidden(&app);
    let (title, body) = toast_words("tellme", job.as_ref(), private);
    let age_s = job
        .as_ref()
        .and_then(|j| j.get("age_s"))
        .and_then(|v| v.as_f64())
        .or_else(|| data.get("age_s").and_then(|v| v.as_f64()));
    if is_late(at, now_secs(), age_s) {
        let went_off = job
            .as_ref()
            .and_then(|j| j.get("went_off_at"))
            .and_then(|v| v.as_str())
            .unwrap_or("");
        show_quiet(&app, toast_kind, &title, &missed_words(went_off, &body));
        return;
    }
    show(
        &app,
        toast_kind,
        &title,
        &body,
        rings("tellme", &data),
        None,
        None,
    );
}

/// A "tell me when" cannot look (`{"id", "kind": "tellme", "state":
/// "broken"}`, 2026-09-28): read its `broken` sentence by id and show it.
/// The PC says this once per problem (repeats held back for hours, cleared
/// by itself at the next good look). An ordinary toast - it never rings, an
/// urgent watch included: only a real match rings. Once per telling, even
/// when a reconnect replays the event.
pub async fn toast_broken(app: AppHandle, base: String, data: serde_json::Value) {
    if !wants_toast(&data) {
        return;
    }
    let Some(id) = data.get("id").and_then(|v| v.as_str()).map(str::to_string) else {
        return;
    };
    if !valid_id(&id) || data.get("kind").and_then(|v| v.as_str()) != Some("tellme") {
        return;
    }
    let job = read_job(&app, &base, &id).await;
    let at = job
        .as_ref()
        .and_then(|j| j.get("broken_at"))
        .and_then(|v| v.as_f64())
        .unwrap_or(0.0) as i64;
    if let Some(key) = shown_key(at, &data) {
        if !first_time(&format!("{id}#broken"), key) {
            return;
        }
    }
    let security = crate::lock::current(&app);
    let private = security.app_lock || crate::lock::private_hidden(&app);
    let (title, body) = broken_words(job.as_ref(), private);
    // A "tell me when" that cannot look has no switch of its own and is not
    // one of the kinds quiet hours act on (notifications.rs), so this is
    // `Kind::Other` - shown, exactly as before the switches existed.
    show(
        &app,
        Kind::for_event("tellme", false),
        &title,
        &body,
        false,
        None,
        None,
    );
}

/// One toast: a ringing one (an alarm, an urgent "tell me when") through
/// WinRT, where its sound can loop until it is dismissed; one with Snooze
/// through WinRT too; any other through the plugin, as before.
///
/// The owner's notification switches and quiet hours are asked HERE, first
/// thing, because this function is where a Windows toast is actually raised
/// (notifications.rs). Every caller says what kind it is posting; a kind he
/// switched off, or (for the three kinds that can wait) the quiet-hours
/// window, ends the call before any toast exists.
fn show(
    app: &AppHandle,
    kind: Kind,
    title: &str,
    body: &str,
    ring: bool,
    snooze: Option<(&str, &str)>,
    open: Option<&str>,
) {
    if !notifications::may_post(app, kind) {
        return;
    }
    #[cfg(windows)]
    {
        if ring {
            crate::winrt_toast::notify_alarm(app, title, body, snooze);
            return;
        }
        if let Some((id, label)) = snooze {
            crate::winrt_toast::notify_fired(app, title, body, id, label, open);
            return;
        }
    }
    #[cfg(not(windows))]
    let _ = (ring, snooze, open);
    commands::notify(app, title, body);
}

/// The PC says a job changed (`{"id", "kind", "state": "changed"}`):
/// snoozed, deleted or done on the phone, by voice or in the Brain. Its
/// "went off" toast - a ringing alarm's included - goes. Never a "tell me
/// when": its job ends the moment it matched to tell only once.
pub(crate) fn on_changed(data: &serde_json::Value) {
    let Some(id) = data.get("id").and_then(|v| v.as_str()) else {
        return;
    };
    let kind = data.get("kind").and_then(|v| v.as_str()).unwrap_or("");
    if !removes_on_change(id, kind) {
        return;
    }
    #[cfg(windows)]
    crate::winrt_toast::remove_fired(id);
    #[cfg(not(windows))]
    let _ = id;
}

/// Whether a `changed` job's toast is taken away: one job id, of a kind
/// that has a "went off" toast with Snooze.
pub(crate) fn removes_on_change(id: &str, kind: &str) -> bool {
    valid_id(id) && SNOOZABLE.contains(&kind)
}

/// A toast without a sound: a job heard about too late to ring.
///
/// Gated exactly like [`show`] - a kind the owner switched off must not
/// notify even quietly, and a late reminder is still a reminder. A late ALARM
/// keeps its own exception: quiet hours never hold it back, only lateness
/// does, which is why this takes the kind rather than assuming one.
pub(crate) fn show_quiet(app: &AppHandle, kind: Kind, title: &str, body: &str) {
    if !notifications::may_post(app, kind) {
        return;
    }
    #[cfg(windows)]
    {
        crate::winrt_toast::notify_quiet(app, title, body);
    }
    #[cfg(not(windows))]
    commands::notify(app, title, body);
}

/// A Snooze pressed on a toast (winrt_toast.rs): the same change as the
/// button in Coming up - ten minutes, one job, held on a stale link - and a
/// toast saying how it went, since the window is very likely not open.
#[cfg_attr(not(windows), allow(dead_code))]
pub(crate) async fn snooze_from_toast(app: AppHandle, id: String) {
    let said = match require_link_live(&app) {
        Err(e) => format!("Not snoozed: {e}."),
        Ok(()) => match act_body(&id, "snooze", Some(SNOOZE_SECONDS)) {
            Err(e) => format!("Not snoozed: {e}"),
            Ok(body) => match post(&app, "/api/schedule/act", body).await {
                Ok(v) => v
                    .get("said")
                    .and_then(|s| s.as_str())
                    .unwrap_or("Snoozed.")
                    .to_string(),
                Err(e) => format!("Not snoozed: {e}"),
            },
        },
    };
    // The answer to the owner's own Snooze press - a job whose toast was
    // shown a moment ago, so there is no switch it could be failing to honour
    // (notifications.rs `Kind::Other`) - and deliberately not gated: "not
    // snoozed" is a refusal he must hear about.
    commands::notify(&app, "Jarvis", &said);
}

pub(crate) async fn read_job(app: &AppHandle, base: &str, id: &str) -> Option<serde_json::Value> {
    let headers = commands::jarvis_headers(app).ok()?;
    let response = commands::jarvis_client(Some(READ_TIMEOUT))
        .ok()?
        .get(format!("{base}/api/schedule"))
        .query(&[("id", id)])
        .headers(headers)
        .send()
        .await
        .ok()?;
    if !response.status().is_success() {
        return None;
    }
    let body = response.text().await.ok()?;
    parsed(&body).and_then(|v| v.get("job").cloned())
}

/// The timers, alarms, reminders, repeating jobs and the to-do list. A read.
#[tauri::command]
pub async fn brain_schedule(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/schedule"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = list_answer(status, &body)?;
    // The Today board rides on this same read (GTD-2): one more GET to the
    // PC, added under `cockpit`. A board that fails or is missing is not the
    // list's failure - the list is what Coming up and the phones need.
    let board = match commands::jarvis_client(Some(READ_TIMEOUT)) {
        Ok(client) => match commands::jarvis_headers(&app) {
            Ok(headers) => {
                match client
                    .get(format!("{base}{COCKPIT_PATH}"))
                    .headers(headers)
                    .send()
                    .await
                {
                    Ok(response) if response.status().is_success() => {
                        response.text().await.ok().and_then(|b| parsed(&b))
                    }
                    _ => None,
                }
            }
            Err(_) => None,
        },
        Err(_) => None,
    };
    let answer = merge_cockpit(answer, board);
    Ok(
        if crate::lock::private_hidden(&app) && answer.get("available") != Some(&false.into()) {
            redact_list(answer)
        } else {
            answer
        },
    )
}

/// ONE job: pause, resume, delete, done, add time (and, since Phase 2, edit,
/// move or reorder). Held on a stale link. `change` is only for the three
/// Phase 2 verbs; the six older ones keep their flat `seconds` body.
#[tauri::command]
pub async fn brain_schedule_act(
    app: AppHandle,
    id: String,
    action: String,
    seconds: Option<f64>,
    change: Option<ScheduleChange>,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    if let Some(change) = change {
        let body = change_body(&id, &action, &change)?;
        let timeout = change_timeout(&action, &change);
        return post_with_timeout(&app, "/api/schedule/act", body, timeout).await;
    }
    let body = act_body(&id, &action, seconds)?;
    post(&app, "/api/schedule/act", body).await
}

/// One new to-do item - on a named list when `list` says one. Held on a
/// stale link.
#[tauri::command]
pub async fn brain_schedule_add_todo(
    app: AppHandle,
    text: String,
    list: Option<String>,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let body = todo_body(&text, list.as_deref())?;
    post(&app, "/api/schedule/add", body).await
}

/// Every item on ONE named list, after the page's "are you sure?". `count`
/// is how many items the page showed: the PC clears nothing when the list
/// has changed since. Never the to-do list. Held on a stale link.
#[tauri::command]
pub async fn brain_schedule_clear_list(
    app: AppHandle,
    list: String,
    count: u32,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let body = clear_list_body(&list, count)?;
    post(&app, "/api/schedule/act", body).await
}

/// The standby schedule: every day from `start` to `end` ("HH:MM"). The PC
/// sets it up at once, with no card (2026-09-26). Held on a stale link.
#[tauri::command]
pub async fn brain_schedule_add_standby(
    app: AppHandle,
    start: String,
    end: String,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let body = standby_body(&start, &end)?;
    post(&app, "/api/schedule/add", body).await
}

/// One Today card: the owner's words, from `at` on `days`. The PC sets it
/// up at once, with no card (it only shows the owner's own words back to
/// them). Held on a stale link. Deleting it is Delete on its row, like any
/// job.
#[tauri::command]
pub async fn brain_schedule_add_today(
    app: AppHandle,
    text: String,
    at: String,
    days: Vec<u8>,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let body = today_body(&text, &at, &days)?;
    post(&app, "/api/schedule/add", body).await
}

/// The said-I'd-do switch (GTD-2, 2026-10-18; backend `jarvis_today.py`'s
/// `request_unspoken`: OFF by default, OFF immediate, ON is ONE approval card
/// at tier "ask"). Neither direction is held on a stale link: turning it OFF
/// only stops Jarvis reading the owner's words (the stricter direction), and
/// turning it ON changes nothing until the PC's own card is approved - the
/// same shape as the other privacy switches (`set_prompt_coach`).
#[tauri::command]
pub async fn brain_schedule_set_unspoken(
    app: AppHandle,
    enabled: bool,
) -> Result<serde_json::Value, String> {
    post(&app, COCKPIT_PATH, serde_json::json!({"enabled": enabled})).await
}

pub(crate) async fn post(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
) -> Result<serde_json::Value, String> {
    post_with_timeout(app, path, body, WRITE_TIMEOUT).await
}

/// ONE write with its own budget (the repeat edit's card wait; `change_timeout`
/// picks it). Everything here is otherwise exactly `post`.
pub(crate) async fn post_with_timeout(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
    timeout: std::time::Duration,
) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(app);
    let response = commands::jarvis_client(Some(timeout))?
        .post(format!("{base}{path}"))
        .headers(commands::jarvis_headers(app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    change_answer(status, &text)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Phase 2 (2026-10-22): the three verbs' bodies, the owner's caps, and the
    /// verb choice the Lead settled - a list-only edit becomes `move`.
    #[test]
    fn one_change_keeps_the_phase2_bodies_and_the_owners_caps() {
        let none = ScheduleChange::default();
        let body =
            |id: &str, action: &str, change: &ScheduleChange| change_body(id, action, change);
        assert!(body("s0123456789", "edit", &none).is_err());
        assert!(body("not-an-id", "edit", &none).is_err());
        assert!(body("s0123456789", "explode", &none).is_err());

        let text = ScheduleChange {
            text: Some("  call mum  ".into()),
            ..Default::default()
        };
        assert_eq!(
            body("s0123456789", "edit", &text).unwrap(),
            serde_json::json!({"id": "s0123456789", "do": "edit", "text": "call mum"})
        );
        let long = ScheduleChange {
            text: Some("x".repeat(MAX_TEXT + 1)),
            ..Default::default()
        };
        assert!(body("s0123456789", "edit", &long).is_err());

        let when = ScheduleChange {
            date: Some("2030-09-15".into()),
            time: Some("7:5".into()),
            ..Default::default()
        };
        assert!(body("s0123456789", "edit", &when).is_err());
        let when = ScheduleChange {
            date: Some("2030-09-15".into()),
            time: Some("18:00".into()),
            ..Default::default()
        };
        assert_eq!(
            body("s0123456789", "edit", &when).unwrap(),
            serde_json::json!({"id": "s0123456789", "do": "edit",
                                     "date": "2030-09-15", "time": "18:00"})
        );

        let timer = ScheduleChange {
            seconds: Some(600.0),
            ..Default::default()
        };
        assert_eq!(
            body("s0123456789", "edit", &timer).unwrap(),
            serde_json::json!({"id": "s0123456789", "do": "edit", "seconds": 600.0})
        );
        for bad in [0.0, -5.0, MAX_TIMER_SECONDS + 1.0, f64::NAN] {
            let s = ScheduleChange {
                seconds: Some(bad),
                ..Default::default()
            };
            assert!(
                body("s0123456789", "edit", &s).is_err(),
                "seconds {bad} was accepted"
            );
        }

        let rule = ScheduleChange {
            repeat: Some(serde_json::json!({"every": "weekday", "at": "07:00"})),
            ..Default::default()
        };
        assert_eq!(
            body("s0123456789", "edit", &rule).unwrap(),
            serde_json::json!({"id": "s0123456789", "do": "edit",
                                     "repeat": {"every": "weekday", "at": "07:00"}})
        );
        let bad_rule = ScheduleChange {
            repeat: Some(serde_json::json!({"every": "decade"})),
            ..Default::default()
        };
        assert!(body("s0123456789", "edit", &bad_rule).is_err());

        // A list alone is the backend's `move` verb (Lead, 2026-10-22).
        let move_only = ScheduleChange {
            list: Some("shopping".into()),
            ..Default::default()
        };
        assert_eq!(
            body("s0123456789", "edit", &move_only).unwrap(),
            serde_json::json!({"id": "s0123456789", "do": "move", "list": "shopping"})
        );
        let todo = ScheduleChange {
            list: Some("to-do".into()),
            ..Default::default()
        };
        assert_eq!(
            body("s0123456789", "move", &todo).unwrap(),
            serde_json::json!({"id": "s0123456789", "do": "move", "list": "todo"})
        );
        // A list riding with words stays inside the one edit.
        let both = ScheduleChange {
            text: Some("milk".into()),
            list: Some("shopping".into()),
            ..Default::default()
        };
        assert_eq!(
            body("s0123456789", "edit", &both).unwrap(),
            serde_json::json!({"id": "s0123456789", "do": "edit", "text": "milk",
                                     "list": "shopping"})
        );
        assert!(body(
            "s0123456789",
            "edit",
            &ScheduleChange {
                list: Some("Not A List".into()),
                ..Default::default()
            }
        )
        .is_err());

        let rank = ScheduleChange {
            rank: Some(2),
            ..Default::default()
        };
        assert_eq!(
            body("s0123456789", "reorder", &rank).unwrap(),
            serde_json::json!({"id": "s0123456789", "do": "reorder", "rank": 2})
        );
        for bad in [-1, MAX_REORDER_RANK + 1] {
            assert!(body(
                "s0123456789",
                "reorder",
                &ScheduleChange {
                    rank: Some(bad),
                    ..Default::default()
                }
            )
            .is_err());
        }
        assert!(body("s0123456789", "reorder", &none).is_err());
        // `at` is the PC's own epoch shape, never "HH:MM" (review 737 #6): a
        // string is refused when the command's arguments are deserialised.
        let at = ScheduleChange {
            at: Some(1_893_456_000.0),
            ..Default::default()
        };
        assert_eq!(
            body("s0123456789", "edit", &at).unwrap(),
            serde_json::json!({"id": "s0123456789", "do": "edit",
                                     "at": 1_893_456_000.0})
        );
        assert!(
            serde_json::from_value::<ScheduleChange>(serde_json::json!({"at": "18:00"})).is_err(),
            "an epoch field accepted an HH:MM string"
        );
        let bad_at = ScheduleChange {
            at: Some(0.0),
            ..Default::default()
        };
        assert!(body("s0123456789", "edit", &bad_at).is_err());
        // The repeat edit is the ONE card-gated path, so it alone gets the long budget.
        assert_eq!(change_timeout("edit", &rule), REPEAT_EDIT_TIMEOUT);
        assert_eq!(change_timeout("edit", &text), WRITE_TIMEOUT);
        assert_eq!(change_timeout("move", &move_only), WRITE_TIMEOUT);
        assert_eq!(change_timeout("reorder", &rank), WRITE_TIMEOUT);
        assert_eq!(change_timeout("pause", &none), WRITE_TIMEOUT);
    }

    /// GTD-2: the Today board is ADDED under `cockpit`; every field of the
    /// list's own answer is untouched, a quiet board adds nothing, and a
    /// missing or failed board changes nothing at all.
    #[test]
    fn the_today_board_is_added_without_changing_the_list() {
        let list =
            serde_json::json!({"available": true, "jobs": [{"id": "s0123456789"}], "todo": []});
        let quiet = merge_cockpit(
            list.clone(),
            Some(
                serde_json::json!({"available": true, "unspoken_commitments_enabled": false,
                                    "rollover_cards": []}),
            ),
        );
        assert_eq!(quiet["jobs"], list["jobs"]);
        assert_eq!(quiet["todo"], list["todo"]);
        assert_eq!(quiet["cockpit"]["unspoken_commitments_enabled"], false);
        assert_eq!(quiet["cockpit"]["rollover_cards"], serde_json::json!([]));
        assert!(quiet["cockpit"].get("due_reminders").is_none());
        let full = merge_cockpit(
            list.clone(),
            Some(serde_json::json!({"available": true, "due_reminders": [
                {"id": "s0123456789", "text": "Call the vet"}], "proposals": []})),
        );
        assert_eq!(full["jobs"], list["jobs"]);
        assert_eq!(full["cockpit"]["due_reminders"][0]["text"], "Call the vet");
        assert!(full["cockpit"].get("proposals").is_none());
        assert_eq!(merge_cockpit(list.clone(), None), list);
        assert_eq!(
            merge_cockpit(list.clone(), Some(serde_json::json!({"available": false}))),
            list
        );
    }

    /// GTD-2: while the private lists are hidden, the board's words go too -
    /// and only the words; the board's own yes/no switch state stays.
    #[test]
    fn hidden_private_lists_blank_the_today_board_words() {
        let list = serde_json::json!({
            "available": true, "jobs": [], "todo": [],
            "cockpit": {
                "unspoken_commitments_enabled": true,
                "rollover_cards": [],
                "due_reminders": [
                    {"id": "s0123456789", "text": "Call the vet", "suggested_prompt": "Draft it"}],
                "active_next_steps": [{"kind": "goal", "step": "Call two installers"}],
                "proposals": [{"text": "send the report"}]
            }
        });
        let hidden = redact_list(list);
        assert_eq!(hidden["hidden"], true);
        assert_eq!(hidden["hidden_count"], 3);
        for key in ["due_reminders", "active_next_steps", "proposals"] {
            assert_eq!(hidden["cockpit"][key], serde_json::json!([]), "{key}");
        }
        let text = hidden.to_string();
        for words in [
            "Call the vet",
            "Call two installers",
            "send the report",
            "Draft it",
        ] {
            assert!(!text.contains(words), "{words} leaked: {text}");
        }
        assert_eq!(hidden["cockpit"]["unspoken_commitments_enabled"], true);
    }

    #[test]
    fn a_job_changed_elsewhere_takes_its_toast_away_but_never_a_tell_me_when() {
        assert!(removes_on_change("s0123456789", "alarm"));
        assert!(removes_on_change("s0123456789", "reminder"));
        assert!(!removes_on_change("s0123456789", "tellme"));
        assert!(!removes_on_change("all", "alarm"));
    }

    #[test]
    fn a_job_that_could_not_be_read_is_told_apart_by_its_event() {
        let data = with_event_id(&serde_json::json!({"id": "s0123456789"}), Some(41));
        assert_eq!(shown_key(1_700_000_000, &data), Some(1_700_000_000));
        assert_eq!(shown_key(0, &data), Some(-41));
        let other = with_event_id(&serde_json::json!({"id": "s0123456789"}), Some(97));
        assert_ne!(shown_key(0, &data), shown_key(0, &other));
        assert_eq!(shown_key(0, &serde_json::json!({})), None);
    }

    #[test]
    fn a_job_heard_more_than_ten_minutes_late_does_not_ring() {
        let went = 1_000_000;
        assert!(
            !heard_late(went, went + 600),
            "ten minutes exactly still rings"
        );
        assert!(heard_late(went, went + 601));
        assert!(
            !heard_late(0, went),
            "a job that could not be read is shown as before"
        );
        assert!(
            !heard_late(went, went - 5),
            "a clock a little behind is not late"
        );
        assert_eq!(missed_words("07:00", "Wake up"), "Missed at 07:00. Wake up");
        assert_eq!(
            missed_words("", "Jarvis: alarm."),
            "Missed earlier. Jarvis: alarm."
        );
        assert_eq!(missed_words("07:00", " "), "Missed at 07:00.");
        // age_s tests
        assert!(!is_late(went, went + 600, Some(600.0)));
        assert!(is_late(went, went, Some(601.0)));
        assert!(!is_late(0, went, Some(100.0)));
        assert!(is_late(0, went, Some(601.0)));
    }

    #[test]
    fn the_list_is_passed_on_and_an_older_backend_says_so() {
        let body = r#"{"available": true, "jobs": [{"id": "s0123456789", "kind": "timer",
            "text": "", "state": "active", "left": 60}], "todo": []}"#;
        assert_eq!(
            list_answer(200, body).unwrap()["jobs"][0]["id"],
            "s0123456789"
        );
        for old in [404, 501] {
            let a = list_answer(old, "{}").unwrap();
            assert_eq!(a["available"], false);
            assert_eq!(a["why"], SCHEDULE_MISSING);
        }
        assert!(list_answer(200, r#"{"ok": true}"#).is_err());
        assert!(list_answer(200, "not json").is_err());
    }

    #[test]
    fn hidden_lists_keep_the_times_but_no_words() {
        let list = serde_json::json!({
            "jobs": [{"id": "s0123456789", "kind": "reminder", "text": "see Dr Patel", "due": 1.0},
                     {"id": "s0123456780", "kind": "timer", "text": "", "left": 30}],
            "todo": [{"id": "s0123456781", "kind": "todo", "text": "renew prescription"}]
        });
        let hidden = redact_list(list);
        let s = hidden.to_string();
        assert!(!s.contains("Patel") && !s.contains("prescription"));
        assert_eq!(hidden["hidden"], true);
        assert_eq!(hidden["hidden_count"], 2);
        assert_eq!(hidden["jobs"][0]["due"], 1.0);
        assert_eq!(hidden["jobs"][1]["left"], 30);
    }

    #[test]
    fn one_job_one_action_and_never_all() {
        assert_eq!(
            act_body("s0123456789", "delete", None).unwrap(),
            serde_json::json!({ "id": "s0123456789", "do": "delete" })
        );
        assert_eq!(
            act_body("s0123456789", "add_time", Some(60.0)).unwrap()["seconds"],
            60.0
        );
        assert!(act_body("s0123456789", "add_time", None).is_err());
        for bad in [
            "*",
            "all",
            "",
            "s012345678",
            "s0123456789,s0123456780",
            "S0123456789",
        ] {
            assert!(act_body(bad, "delete", None).is_err(), "{bad}");
        }
        for bad in ["delete_all", "clear", "approve", ""] {
            assert!(act_body("s0123456789", bad, None).is_err(), "{bad}");
        }
    }

    #[test]
    fn a_today_card_is_the_owners_words_at_a_time_on_days() {
        assert_eq!(
            today_body("  Gym   bag ", "7:00", &[2, 0, 0]).unwrap(),
            serde_json::json!({ "kind": "today", "text": "Gym bag",
                "repeat": { "every": "week", "at": "07:00", "days": [0, 2] } })
        );
        assert_eq!(
            today_body("Bins", "18:30", &[0, 1, 2, 3, 4, 5, 6]).unwrap()["repeat"],
            serde_json::json!({ "every": "day", "at": "18:30" })
        );
        assert_eq!(
            today_body("Pills", "08:00", &[4, 3, 2, 1, 0]).unwrap()["repeat"],
            serde_json::json!({ "every": "weekday", "at": "08:00" })
        );
        assert!(today_body("   ", "07:00", &[0]).is_err());
        assert!(today_body(&"x".repeat(TODAY_MAX_TEXT + 1), "07:00", &[0]).is_err());
        assert!(today_body(&"x".repeat(TODAY_MAX_TEXT), "07:00", &[0]).is_ok());
        assert!(today_body("Gym", "25:00", &[0]).is_err());
        assert!(today_body("Gym", "07:00", &[]).is_err());
        assert!(today_body("Gym", "07:00", &[7, 9]).is_err());
    }

    #[test]
    fn hidden_lists_blank_a_today_cards_words_too() {
        let list = serde_json::json!({ "available": true,
            "jobs": [{ "id": "s0123456789", "kind": "today", "text": "Gym bag",
                       "today": "showing", "shows_at": "07:00" }],
            "todo": [] });
        let hidden = redact_list(list);
        assert!(!hidden.to_string().contains("Gym"));
        assert_eq!(hidden["jobs"][0]["today"], "showing");
        assert_eq!(hidden["jobs"][0]["shows_at"], "07:00");
    }

    #[test]
    fn a_todo_is_the_owners_words_tidied_and_capped() {
        assert_eq!(
            todo_body("  buy   milk ", None).unwrap(),
            serde_json::json!({ "kind": "todo", "text": "buy milk" })
        );
        assert!(todo_body("   ", None).is_err());
        assert!(todo_body(&"x".repeat(MAX_TEXT + 1), None).is_err());
        assert!(todo_body(&"x".repeat(MAX_TEXT), None).is_ok());
        assert_eq!(
            todo_body("milk", Some("shopping")).unwrap(),
            serde_json::json!({ "kind": "todo", "text": "milk", "list": "shopping" })
        );
        for bad in ["", "Shopping", "a b c d", "shop;ping", "hidden 1"] {
            assert!(todo_body("milk", Some(bad)).is_err(), "{bad}");
        }
    }

    #[test]
    fn snooze_is_one_job_ten_minutes_by_default_and_within_limits() {
        assert_eq!(
            act_body("s0123456789", "snooze", None).unwrap(),
            serde_json::json!({ "id": "s0123456789", "do": "snooze", "seconds": 600.0 })
        );
        assert_eq!(
            act_body("s0123456789", "snooze", Some(300.0)).unwrap()["seconds"],
            300.0
        );
        for bad in [0.0, 59.0, 86401.0, f64::NAN] {
            assert!(
                act_body("s0123456789", "snooze", Some(bad)).is_err(),
                "{bad}"
            );
        }
        assert!(act_body("all", "snooze", None).is_err());
    }

    #[test]
    fn clearing_names_one_named_list_and_the_count_the_page_showed() {
        assert_eq!(
            clear_list_body("shopping", 3).unwrap(),
            serde_json::json!({ "do": "clear_list", "list": "shopping", "count": 3 })
        );
        assert!(clear_list_body("shopping", 0).is_err());
        for bad in ["", "*", "To-do", "a b c d", "shop,ping"] {
            assert!(clear_list_body(bad, 1).is_err(), "{bad}");
        }
        // "all" is a plain word, so it reaches the PC - which refuses it as
        // a list's name (jarvis_schedule.list_key): there is no clear-all.
        assert_eq!(clear_list_body("all", 1).unwrap()["list"], "all");
    }

    #[test]
    fn hidden_lists_hide_the_list_names_too_but_keep_the_grouping() {
        let list = serde_json::json!({
            "jobs": [],
            "todo": [{"id": "s0123456781", "kind": "todo", "text": "ring", "list": "presents for sam"},
                     {"id": "s0123456782", "kind": "todo", "text": "card", "list": "presents for sam"},
                     {"id": "s0123456783", "kind": "todo", "text": "milk", "list": ""}],
            "lists": [{"name": "presents for sam", "title": "Presents for sam list", "open": 2}],
            "went_off": [{"id": "s0123456784", "kind": "reminder", "text": "call Dr Patel"}]
        });
        let hidden = redact_list(list);
        let s = hidden.to_string();
        assert!(
            !s.contains("sam") && !s.contains("ring") && !s.contains("Patel"),
            "{s}"
        );
        assert_eq!(hidden["lists"][0]["name"], "hidden-1");
        assert_eq!(hidden["todo"][0]["list"], "hidden-1");
        assert_eq!(hidden["todo"][1]["list"], "hidden-1");
        assert_eq!(hidden["todo"][2]["list"], "");
    }

    #[test]
    fn hidden_lists_hide_a_reminder_for_next_times_subject_too() {
        // jarvis_next_time.py (2026-09-28): the subject is the owner's words.
        let list = serde_json::json!({
            "jobs": [{"id": "s0123456785", "kind": "nexttime", "text": "ask about the bill",
                      "about": "the dentist", "when": "until Sunday 27 December",
                      "note": "Waits for you to talk about it."}],
            "todo": []
        });
        let hidden = redact_list(list);
        let s = hidden.to_string();
        assert!(!s.contains("dentist") && !s.contains("bill"), "{s}");
        assert_eq!(hidden["jobs"][0]["about"], "");
        assert_eq!(hidden["jobs"][0]["when"], "until Sunday 27 December");
        assert_eq!(hidden["jobs"][0]["hidden"], true);
    }

    #[test]
    fn a_refused_change_says_why_and_a_missing_route_is_never_a_success() {
        assert_eq!(
            change_answer(404, r#"{"ok": false, "reason": "no_such_job"}"#).unwrap_err(),
            NO_SUCH_JOB
        );
        assert_eq!(change_answer(404, "").unwrap_err(), SCHEDULE_TOO_OLD);
        assert_eq!(change_answer(501, "{}").unwrap_err(), SCHEDULE_TOO_OLD);
        assert!(change_answer(200, r#"{"ok": true, "said": "Paused."}"#).is_ok());
    }

    #[test]
    fn a_toast_shows_the_words_only_when_nothing_is_locked() {
        let job = serde_json::json!({"id": "s0123456789", "kind": "reminder",
            "text": "call Mum", "lock_screen": "Jarvis: a reminder is due.",
            "missed": "missed at 07:00"});
        let (t, b) = toast_words("reminder", Some(&job), false);
        assert_eq!(t, "Reminder");
        assert_eq!(b, "call Mum (missed at 07:00 - the PC was off or asleep.)");
        let (_, b) = toast_words("reminder", Some(&job), true);
        assert_eq!(b, "Jarvis: a reminder is due.");
        assert!(!b.contains("Mum"));
        let (t, b) = toast_words("timer", None, false);
        assert_eq!(
            (t.as_str(), b.as_str()),
            ("Timer done", "Jarvis: your timer is done.")
        );
        let timer = serde_json::json!({"kind": "timer", "text": "pasta"});
        assert_eq!(
            toast_words("timer", Some(&timer), false).1,
            "The pasta timer is done."
        );
    }

    #[test]
    fn a_standby_schedule_is_two_times_and_nothing_else() {
        assert_eq!(
            standby_body("1:00", "07:00").unwrap(),
            serde_json::json!({"kind": "standby",
                               "repeat": {"every": "day", "at": "01:00", "until": "07:00"}})
        );
        assert_eq!(
            standby_body(" 23:30 ", "06:05").unwrap()["repeat"]["at"],
            "23:30"
        );
        for (a, b) in [
            ("01:00", "01:00"),
            ("24:00", "07:00"),
            ("01:60", "07:00"),
            ("1", "07:00"),
            ("", ""),
            ("01:00", "7:0"),
            ("-1:00", "07:00"),
        ] {
            assert_eq!(
                standby_body(a, b).unwrap_err(),
                STANDBY_BAD_TIMES,
                "{a} {b}"
            );
        }
    }

    #[test]
    fn a_tell_me_when_says_its_alert_and_only_the_generic_words_when_locked() {
        let job = serde_json::json!({"id": "s0123456789", "kind": "tellme",
            "text": "an email from Alex arrives", "alert": "An email from Alex arrived.",
            "lock_screen": TELLME_LOCK_SCREEN});
        assert_eq!(
            toast_words("tellme", Some(&job), false),
            (
                "Tell me when".to_string(),
                "An email from Alex arrived.".to_string()
            )
        );
        let (_, b) = toast_words("tellme", Some(&job), true);
        assert_eq!(b, TELLME_LOCK_SCREEN);
        assert!(!b.contains("Alex"));
        assert_eq!(toast_words("tellme", None, false).1, TELLME_LOCK_SCREEN);
        let hidden = redact_list(serde_json::json!({"jobs": [job], "todo": []}));
        assert!(!hidden.to_string().contains("Alex"));
    }

    #[test]
    fn a_tell_me_when_that_cannot_look_says_so_and_only_the_generic_words_when_locked() {
        let job = serde_json::json!({"id": "s0123456789", "kind": "tellme",
            "text": "CI fails on o/r",
            "broken": "Your \"tell me when\" (CI fails on o/r) cannot look right now. GitHub did not answer.",
            "broken_at": 1_790_000_000.0});
        let (t, b) = broken_words(Some(&job), false);
        assert_eq!(t, "Tell me when");
        assert!(b.starts_with("Your \"tell me when\" (CI fails on o/r)"));
        let (_, b) = broken_words(Some(&job), true);
        assert_eq!(b, TELLME_BROKEN_LOCK_SCREEN);
        assert!(!b.contains("o/r"));
        assert_eq!(broken_words(None, false).1, TELLME_BROKEN_LOCK_SCREEN);
        let hidden = redact_list(serde_json::json!({"jobs": [job], "todo": []}));
        assert!(!hidden.to_string().contains("o/r"));
    }

    /// A reminder's own action is the owner's words a third time (2026-10-27):
    /// the address he meant to open, the path that names a folder of his, or the
    /// note's text. `redact_list` is the ONE place the private lists are blanked
    /// (App lock and "Hide memory lists"), and a field it does not know is a
    /// leak - so every payload value goes, only the KIND stays, and the page
    /// then draws no Open button (its target is gone).
    #[test]
    fn a_reminder_s_action_is_blanked_with_its_words_and_keeps_only_the_kind() {
        for action in [
            serde_json::json!({"kind": "open-webpage", "url": "https://example.com/invoice-42"}),
            serde_json::json!({"kind": "open-file",
                "path": "C:\\Users\\pcadmin\\Pictures\\taxes.png"}),
            serde_json::json!({"kind": "show-note", "note": "Take the blue folder"}),
            serde_json::json!({"kind": "run-task", "task": "briefing"}),
        ] {
            let job = serde_json::json!({"id": "s0123456789", "kind": "reminder",
                "text": "", "action": action, "fired_at": 1_793_000_000.0});
            let hidden = redact_list(serde_json::json!({"jobs": [job], "todo": []}));
            let text = hidden.to_string();
            for word in [
                "example.com",
                "invoice-42",
                "taxes.png",
                "pcadmin",
                "blue folder",
                "briefing",
            ] {
                assert!(!text.contains(word), "{word} survived redaction: {text}");
            }
            assert!(
                text.contains("open-webpage")
                    || text.contains("open-file")
                    || text.contains("show-note")
                    || text.contains("run-task"),
                "the kind is a fixed word and stays: {text}"
            );
            let row = &hidden["jobs"][0];
            assert_eq!(row["hidden"], serde_json::json!(true));
            assert!(row["action"]["kind"].as_str().is_some());
            // Only the kind: the one payload key is gone altogether, so a button
            // built from this row has no target to open.
            let keys = row["action"].as_object().unwrap().len();
            assert_eq!(
                keys, 1,
                "the action kept more than its kind: {}",
                row["action"]
            );
        }
    }

    /// The Open button is drawn only when there IS something to open, the PC did
    /// not refuse it, and the words are not hidden - and the notice names the
    /// target in full before anything opens.
    #[test]
    fn the_notice_names_the_target_and_offers_open_only_when_it_can_work() {
        let page = serde_json::json!({"id": "s0123456789", "kind": "reminder",
            "fired_at": 1_793_000_000.0,
            "action": {"kind": "open-webpage", "url": "https://example.com/invoice-42"}});
        assert_eq!(
            open_notice(Some(&page), false),
            Some((
                "This opens: https://example.com/invoice-42".to_string(),
                "s0123456789".to_string()
            ))
        );
        // Hidden words: no target to show, so no button.
        assert_eq!(open_notice(Some(&page), true), None);
        // The PC says it cannot work any more (the file has gone): no button.
        let mut gone = page.clone();
        gone["action_problem"] = serde_json::json!("That file is not there any more.");
        assert_eq!(open_notice(Some(&gone), false), None);
        // A note and a task open nothing; neither gets a button.
        for action in [
            serde_json::json!({"kind": "show-note", "note": "Take the blue folder"}),
            serde_json::json!({"kind": "run-task", "task": "briefing"}),
        ] {
            let mut job = page.clone();
            job["action"] = action;
            assert_eq!(open_notice(Some(&job), false), None);
        }
        assert_eq!(open_notice(None, false), None);
    }

    #[test]
    fn alarms_and_urgent_tell_me_whens_ring_until_dismissed() {
        let fired = serde_json::json!({"id": "s0123456789", "state": "fired"});
        assert!(rings("alarm", &fired));
        assert!(!rings("timer", &fired) && !rings("reminder", &fired));
        assert!(rings("tellme", &serde_json::json!({"urgent": true})));
        assert!(!rings("tellme", &serde_json::json!({"urgent": false})));
        assert!(!rings("tellme", &serde_json::json!({})));
    }

    #[test]
    fn a_kind_that_notifies_nobody_gets_no_toast() {
        assert!(!wants_toast(&serde_json::json!(
            {"id": "s0123456789", "kind": "standby", "state": "fired", "notify": false}
        )));
        assert!(wants_toast(&serde_json::json!(
            {"id": "s0123456789", "kind": "timer", "state": "fired"}
        )));
    }

    #[test]
    fn the_same_job_going_off_is_toasted_once() {
        assert!(first_time("s00000000aa", 100));
        assert!(!first_time("s00000000aa", 100));
        assert!(first_time("s00000000aa", 200));
    }

    // ---- the HUD Reminders tab's add form (2026-10-21) ------------------

    /// The form's fields -> the exact bodies `POST /api/schedule/add`
    /// already takes; nothing invented, no field the backend does not know.
    #[test]
    fn the_hud_add_form_makes_the_body_the_backend_takes() {
        let todo = hud_add_body(
            "todo",
            Some("Buy milk"),
            None,
            None,
            None,
            None,
            None,
            Some("shopping"),
            None,
        )
        .unwrap();
        assert_eq!(
            todo,
            serde_json::json!(
            {"kind": "todo", "text": "Buy milk", "list": "shopping"})
        );

        // The notes are carried in the item's ONE free-text field, on the end.
        let noted = hud_add_body(
            "reminder",
            Some("  Call Mum  "),
            Some("about the trip"),
            None,
            Some("2030-09-15"),
            Some("7:30"),
            None,
            None,
            None,
        )
        .unwrap();
        assert_eq!(
            noted,
            serde_json::json!({
            "kind": "reminder", "date": "2030-09-15", "time": "07:30",
            "text": "Call Mum - about the trip"})
        );

        let timer = hud_add_body(
            "timer",
            None,
            None,
            Some(600.0),
            None,
            None,
            None,
            None,
            None,
        )
        .unwrap();
        assert_eq!(
            timer,
            serde_json::json!({"kind": "timer", "seconds": 600.0})
        );

        let daily = hud_add_body(
            "reminder",
            Some("Stretch"),
            None,
            None,
            None,
            None,
            Some(&serde_json::json!({"every": "weekday", "at": "8:05"})),
            None,
            None,
        )
        .unwrap();
        assert_eq!(
            daily,
            serde_json::json!({
            "kind": "reminder", "repeat": {"every": "weekday", "at": "08:05"},
            "text": "Stretch"})
        );

        let weekly = hud_add_body(
            "alarm",
            None,
            None,
            None,
            None,
            None,
            Some(&serde_json::json!(
                                      {"every": "week", "at": "06:00", "days": [5, 0, 5]})),
            None,
            None,
        )
        .unwrap();
        assert_eq!(
            weekly,
            serde_json::json!({
            "kind": "alarm", "repeat": {"every": "week", "at": "06:00", "days": [0, 5]}})
        );
    }

    /// Every refusal is a plain sentence, and no bad shape reaches the PC.
    #[test]
    fn the_hud_add_form_refuses_bad_shapes_in_plain_words() {
        let err = |b: Result<serde_json::Value, String>| b.unwrap_err();
        assert_eq!(
            err(hud_add_body(
                "todo", None, None, None, None, None, None, None, None,
            )),
            "Type what to add first."
        );
        assert_eq!(
            err(hud_add_body(
                "reminder",
                Some("x"),
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )),
            "Pick a date, like 2030-09-15."
        );
        assert_eq!(
            err(hud_add_body(
                "reminder",
                Some("x"),
                None,
                None,
                Some("2030-9-15"),
                Some("07:30"),
                None,
                None,
                None,
            )),
            "A date looks like 2030-09-15."
        );
        assert_eq!(
            err(hud_add_body(
                "alarm",
                Some("x"),
                None,
                None,
                Some("2030-09-15"),
                Some("25:00"),
                None,
                None,
                None,
            )),
            "Write the time as HH:MM, like 18:00."
        );
        assert_eq!(
            err(hud_add_body(
                "timer",
                None,
                None,
                Some(0.0),
                None,
                None,
                None,
                None,
                None,
            )),
            "A timer needs a positive number of seconds."
        );
        assert_eq!(
            err(hud_add_body(
                "timer",
                None,
                None,
                Some(MAX_TIMER_SECONDS + 1.0),
                None,
                None,
                None,
                None,
                None,
            )),
            "A timer is for today - at most 24 hours."
        );
        assert_eq!(
            err(hud_add_body(
                "briefing",
                Some("x"),
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )),
            REMINDERS_FORM_HINT
        );
        assert_eq!(
            err(hud_add_body(
                "reminder",
                Some("x"),
                None,
                None,
                None,
                None,
                Some(&serde_json::json!({"every": "week", "at": "07:00",
                                                             "days": []})),
                None,
                None,
            )),
            "Pick at least one day."
        );
        assert_eq!(
            err(hud_add_body(
                "reminder",
                Some("x"),
                None,
                None,
                None,
                None,
                Some(&serde_json::json!({"every": "week", "at": "07:00",
                                                             "days": [9]})),
                None,
                None,
            )),
            "A weekly repeat needs its days, 0 (Monday) to 6 (Sunday)."
        );
        assert_eq!(
            err(hud_add_body(
                "reminder",
                Some("x"),
                None,
                None,
                None,
                None,
                Some(&serde_json::json!({"every": "day", "at": "07:00",
                                                             "until": "08:00"})),
                None,
                None,
            )),
            "Only a standby schedule has an end time."
        );
        assert_eq!(
            err(hud_add_body(
                "reminder",
                Some("x"),
                None,
                None,
                None,
                None,
                Some(&serde_json::json!({"every": "minutes"})),
                None,
                None,
            )),
            "A repeat is every day, every weekday, or every week on some days."
        );
        let too_long = "a".repeat(MAX_TEXT + 1);
        assert_eq!(
            err(hud_add_body(
                "todo",
                Some(&too_long),
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )),
            format!("That is longer than {MAX_TEXT} characters - say it more briefly.")
        );
    }
}
