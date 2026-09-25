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
//!   as the tray's Change power mode, on a timetable. It repeats, so the PC
//!   raises ONE approval card (`schedule_repeat`) and sets nothing up until
//!   it is approved. Held on a stale link. Turning it off is Delete on its
//!   row, like any job.
//!
//! And one thing that is not a command: [`toast_fired`], which stream.rs
//! calls when a `schedule` event says a job went off. The event carries the
//! id and the kind only, never the words; this reads the words by id and
//! shows a Windows toast. While App lock is on, or the private lists are
//! hidden, the toast says only what KIND of thing is due ("Jarvis: a
//! reminder is due.") - the same lock-screen words the phone uses.
//!
//! The answer-reading functions are plain functions of (status, body) so
//! their tests run without a Tauri app or a network.

use std::collections::HashSet;
use std::sync::Mutex;

use tauri::AppHandle;

use super::{require_link_live, READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

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
pub(crate) const ACTIONS: &[&str] = &["pause", "resume", "delete", "done", "add_time"];

/// The longest to-do item the PC keeps (jarvis_schedule.MAX_TEXT).
pub(crate) const MAX_TEXT: usize = 300;

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
/// down.
pub(crate) fn redact_list(mut list: serde_json::Value) -> serde_json::Value {
    let mut count = 0usize;
    if let Some(obj) = list.as_object_mut() {
        for key in ["jobs", "todo"] {
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
                        o.insert("hidden".into(), serde_json::json!(true));
                    }
                }
            }
        }
        obj.insert("hidden".into(), serde_json::json!(true));
        obj.insert("hidden_count".into(), serde_json::json!(count));
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
    Ok(serde_json::json!({ "id": id, "do": action }))
}

/// The body of one new to-do item.
pub(crate) fn todo_body(text: &str) -> Result<serde_json::Value, String> {
    let t = text.split_whitespace().collect::<Vec<_>>().join(" ");
    if t.is_empty() {
        return Err("Type what to add first.".to_string());
    }
    if t.chars().count() > MAX_TEXT {
        return Err(format!(
            "That is longer than {MAX_TEXT} characters - say it more briefly."
        ));
    }
    Ok(serde_json::json!({ "kind": "todo", "text": t }))
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

/// Whether a `schedule` event that went off should be shown at all. The PC
/// says `"notify": false` for a kind that tells nobody - the standby
/// schedule at 01:00 - and then there is no toast (the phone shows no
/// notification either).
pub(crate) fn wants_toast(data: &serde_json::Value) -> bool {
    data.get("notify").and_then(|v| v.as_bool()) != Some(false)
}

/// The toast's title for a kind - both apps' words.
pub(crate) fn toast_title(kind: &str) -> &'static str {
    match kind {
        "timer" => "Timer done",
        "alarm" => "Alarm",
        "reminder" => "Reminder",
        "todo" => "To-do",
        "briefing" => "Morning briefing",
        _ => "Jarvis",
    }
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
    let text = job
        .get("text")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim();
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

/// The jobs already toasted, by id and the time they went off, so a replayed
/// event after a reconnect does not toast twice.
static TOASTED: Mutex<Option<HashSet<(String, i64)>>> = Mutex::new(None);

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
    let job = read_job(&app, &base, &id).await;
    let fired_at = job
        .as_ref()
        .and_then(|j| j.get("fired_at"))
        .and_then(|v| v.as_f64())
        .unwrap_or(0.0) as i64;
    if !first_time(&id, fired_at) {
        return;
    }
    let security = crate::lock::current(&app);
    let private = security.app_lock || crate::lock::private_hidden(&app);
    let (title, body) = toast_words(&kind, job.as_ref(), private);
    commands::notify(&app, &title, &body);
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
    Ok(
        if crate::lock::private_hidden(&app) && answer.get("available") != Some(&false.into()) {
            redact_list(answer)
        } else {
            answer
        },
    )
}

/// ONE job: pause, resume, delete, done, or add time. Held on a stale link.
#[tauri::command]
pub async fn brain_schedule_act(
    app: AppHandle,
    id: String,
    action: String,
    seconds: Option<f64>,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let body = act_body(&id, &action, seconds)?;
    post(&app, "/api/schedule/act", body).await
}

/// One new to-do item. Held on a stale link.
#[tauri::command]
pub async fn brain_schedule_add_todo(
    app: AppHandle,
    text: String,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let body = todo_body(&text)?;
    post(&app, "/api/schedule/add", body).await
}

/// The standby schedule: every day from `start` to `end` ("HH:MM"). The PC
/// raises one approval card; nothing is set up until it is approved. Held
/// on a stale link.
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

async fn post(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(app);
    let response = commands::jarvis_client(Some(WRITE_TIMEOUT))?
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
    fn a_todo_is_the_owners_words_tidied_and_capped() {
        assert_eq!(
            todo_body("  buy   milk ").unwrap(),
            serde_json::json!({ "kind": "todo", "text": "buy milk" })
        );
        assert!(todo_body("   ").is_err());
        assert!(todo_body(&"x".repeat(MAX_TEXT + 1)).is_err());
        assert!(todo_body(&"x".repeat(MAX_TEXT)).is_ok());
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
}
