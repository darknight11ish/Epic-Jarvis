//! The morning briefing (the owner's decisions of 2026-09-25;
//! backend/briefing.patch, `jarvis_briefing.py`; JARVIS-API.md section 22).
//!
//! A short list of the day, put together on the PC WITHOUT the AI model:
//! today's calendar (only when it is set up), today's alarms, reminders and
//! timers, the to-do list, how many approval cards wait, and - only when
//! email is set up - how many unread emails (the number only). It is a kind
//! of job on the one scheduler, so it also shows in Coming up.
//!
//! Brain window (the Work tab):
//! * [`brain_briefing`] - `GET /api/briefing`: the latest briefing. A read.
//!   While "Windows Hello for memory lists and chat history" (lock.rs) hides
//!   the private lists, every line is taken out HERE, in Rust, so a page
//!   script cannot read round it; the counts stay.
//! * [`brain_briefing_now`] - `POST /api/briefing/now`: "Brief me now". It
//!   only READS, so like every read it is not held on a stale link. The same
//!   hiding applies to its answer.
//!
//! Settings window ("Morning briefing"):
//! * [`get_briefing_setup`] - the briefing jobs and what a briefing
//!   includes. The briefing itself is taken out: Settings never shows it.
//! * [`set_briefing`] - `POST /api/schedule/add {"kind": "briefing",
//!   "repeat": rule}`: it repeats, so the PC raises the scheduler's ONE
//!   approval card (schedule_repeat) listing the next three times, and
//!   nothing is set up before a yes. Held on a stale link.
//! * [`stop_briefing`] - `POST /api/schedule/act {"id", "do": "delete"}` for
//!   ONE briefing job, immediate, no card. Held on a stale link. The id must
//!   be one of the briefing jobs the PC lists right now: this window cannot
//!   delete any other job.
//! * [`set_briefing_senders`] - `POST /api/briefing/senders {"enabled"}`:
//!   "Show who new emails are from" (on by default, the owner's decision of
//!   2026-09-25). OFF is immediate and never held - it only shows less. ON
//!   raises ONE approval card on the PC and changes nothing until it is
//!   approved, so it is held on a stale link - the shape of every setting
//!   that shows more.
//!
//! And [`toast_ready`], which stream.rs calls when a `schedule` event says a
//! briefing is ready: a Windows toast that says ONLY "Jarvis: your morning
//! briefing is ready." - never a line of it, whatever the lock settings.
//! The scheduler's own "fired" toast is skipped for a briefing
//! (schedule.rs), so the toast never comes before the briefing does.

use tauri::AppHandle;

use super::schedule::{change_answer, first_time, read_job, valid_id};
use super::{require_link_live, READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

/// A PC without the briefing. The phone says the same (`Briefing.MISSING`).
pub(crate) const BRIEFING_MISSING: &str =
    "Your PC's Jarvis does not have the morning briefing yet - run apply-patches.ps1 on the PC.";

/// A PC whose briefing has no senders setting. The phone says the same
/// (`Briefing.SENDERS_MISSING`).
pub(crate) const SENDERS_MISSING: &str =
    "Your PC's Jarvis does not have this setting yet - run apply-patches.ps1 on the PC.";

/// All a toast ever says (jarvis_briefing.LOCK_SCREEN).
pub(crate) const LOCK_SCREEN: &str = "Jarvis: your morning briefing is ready.";

/// The toast's title - both apps' words.
pub(crate) const TOAST_TITLE: &str = "Morning briefing";

/// "Brief me now" can wait for a slow calendar or mail server: the PC gives
/// them 25 seconds together (jarvis_briefing.READ_DEADLINE).
const NOW_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(45);

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// The repeats a briefing can be set up with - the scheduler's own rules.
pub(crate) const EVERY: &[&str] = &["day", "weekday", "week"];

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

/// [`brain_briefing`]'s, [`brain_briefing_now`]'s and
/// [`get_briefing_setup`]'s reading of the answer.
pub(crate) fn briefing_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("briefing").is_some())
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 || status == 501 {
        return Ok(serde_json::json!({ "available": false, "why": BRIEFING_MISSING }));
    }
    Err(commands::backend_refusal(status, body))
}

/// The answer with every line of the briefing taken out, for while the
/// private lists are hidden. The section titles and summaries stay - they
/// are counts and states ("2 events today."), never a calendar title, a
/// reminder's words or a to-do item.
pub(crate) fn redact(mut answer: serde_json::Value) -> serde_json::Value {
    let mut count = 0usize;
    if let Some(b) = answer.get_mut("briefing").and_then(|b| b.as_object_mut()) {
        b.insert("text".into(), serde_json::json!(""));
        if let Some(serde_json::Value::Array(sections)) = b.get_mut("sections") {
            for s in sections.iter_mut() {
                if let Some(o) = s.as_object_mut() {
                    count += o
                        .get("items")
                        .and_then(|i| i.as_array())
                        .map_or(0, |i| i.len());
                    o.insert("items".into(), serde_json::json!([]));
                }
            }
        }
        b.insert("hidden".into(), serde_json::json!(true));
        b.insert("hidden_count".into(), serde_json::json!(count));
    }
    if let Some(o) = answer.as_object_mut() {
        o.insert("hidden".into(), serde_json::json!(true));
    }
    answer
}

/// Settings shows the setup, never the briefing itself.
pub(crate) fn setup_view(mut answer: serde_json::Value) -> serde_json::Value {
    if let Some(o) = answer.as_object_mut() {
        if o.contains_key("briefing") {
            o.insert("briefing".into(), serde_json::Value::Null);
        }
    }
    answer
}

/// "HH:MM", 00:00 to 23:59, tidied to two digits each.
fn clock(at: &str) -> Option<String> {
    let (h, m) = at.trim().split_once(':')?;
    let h: u8 = h.parse().ok()?;
    let m: u8 = m.parse().ok()?;
    (h <= 23 && m <= 59 && at.trim().len() <= 5).then(|| format!("{h:02}:{m:02}"))
}

/// The body of one briefing that repeats: every day, every weekday, or
/// every week on some days (0 = Monday). Nothing else.
pub(crate) fn repeat_body(every: &str, at: &str, days: &[u8]) -> Result<serde_json::Value, String> {
    if !EVERY.contains(&every) {
        return Err("A briefing repeats every day, every weekday, or on chosen days.".into());
    }
    let at = clock(at).ok_or_else(|| "Pick a time, like 07:00.".to_string())?;
    let mut rule = serde_json::json!({ "every": every, "at": at });
    if every == "week" {
        if days.iter().any(|x| *x > 6) {
            return Err("Days are 0 (Monday) to 6 (Sunday).".into());
        }
        let mut d: Vec<u8> = days.to_vec();
        d.sort_unstable();
        d.dedup();
        if d.is_empty() {
            return Err("Pick at least one day.".into());
        }
        rule["days"] = serde_json::json!(d);
    }
    Ok(serde_json::json!({ "kind": "briefing", "repeat": rule }))
}

/// [`set_briefing_senders`]'s reading of the answer: the PC's own body on a
/// 2xx (200 done, 202 a card is up), [`SENDERS_MISSING`] from a PC without
/// the route, and the PC's refusal otherwise.
pub(crate) fn senders_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body).ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 || status == 501 {
        return Err(SENDERS_MISSING.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// Whether `id` is one of the briefing jobs in a `GET /api/briefing` answer.
pub(crate) fn is_setup(answer: &serde_json::Value, id: &str) -> bool {
    answer
        .get("setups")
        .and_then(|s| s.as_array())
        .is_some_and(|s| {
            s.iter().any(|j| {
                j.get("id").and_then(|v| v.as_str()) == Some(id)
                    && j.get("kind").and_then(|v| v.as_str()) == Some("briefing")
            })
        })
}

async fn read(app: &AppHandle) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/briefing"))
        .headers(commands::jarvis_headers(app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    briefing_answer(status, &body)
}

fn hide_if_needed(app: &AppHandle, answer: serde_json::Value) -> serde_json::Value {
    if crate::lock::private_hidden(app) && answer.get("available") != Some(&false.into()) {
        redact(answer)
    } else {
        answer
    }
}

/// The latest briefing. A read.
#[tauri::command]
pub async fn brain_briefing(app: AppHandle) -> Result<serde_json::Value, String> {
    let answer = read(&app).await?;
    Ok(hide_if_needed(&app, answer))
}

/// "Brief me now": one put together now. It only reads, so it is not held
/// on a stale link - like every read.
#[tauri::command]
pub async fn brain_briefing_now(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(NOW_TIMEOUT))?
        .post(format!("{base}/api/briefing/now"))
        .headers(commands::jarvis_headers(&app)?)
        .json(&serde_json::json!({}))
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = briefing_answer(status, &body)?;
    Ok(hide_if_needed(&app, answer))
}

/// Settings: the briefing jobs and what a briefing includes. A read.
#[tauri::command]
pub async fn get_briefing_setup(app: AppHandle) -> Result<serde_json::Value, String> {
    Ok(setup_view(read(&app).await?))
}

/// Settings: set one up that repeats. The PC raises ONE approval card;
/// nothing is set up before a yes. Held on a stale link.
#[tauri::command]
pub async fn set_briefing(
    app: AppHandle,
    every: String,
    at: String,
    days: Option<Vec<u8>>,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let body = repeat_body(&every, &at, days.as_deref().unwrap_or(&[]))?;
    post(&app, "/api/schedule/add", body).await
}

/// Settings: stop ONE briefing job, at once. Held on a stale link, and only
/// for a job the PC lists as a briefing right now.
#[tauri::command]
pub async fn stop_briefing(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    if !valid_id(&id) {
        return Err("That is not one briefing.".into());
    }
    if !is_setup(&read(&app).await?, &id) {
        return Err("That is not a briefing on the list any more.".into());
    }
    post(
        &app,
        "/api/schedule/act",
        serde_json::json!({ "id": id, "do": "delete" }),
    )
    .await
}

/// Settings: "Show who new emails are from". OFF at once, never held; ON
/// raises ONE approval card on the PC, so it is held on a stale link.
#[tauri::command]
pub async fn set_briefing_senders(
    app: AppHandle,
    enabled: bool,
) -> Result<serde_json::Value, String> {
    if enabled {
        require_link_live(&app)?;
    }
    let (status, text) = post_raw(
        &app,
        "/api/briefing/senders",
        serde_json::json!({ "enabled": enabled }),
    )
    .await?;
    senders_answer(status, &text)
}

async fn post(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let (status, text) = post_raw(app, path, body).await?;
    change_answer(status, &text)
}

async fn post_raw(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
) -> Result<(u16, String), String> {
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
    Ok((status, text))
}

/// A `schedule` event said a briefing is ready: a toast with the fixed
/// words only - never a line of the briefing, locked or not. Once per run
/// (a replayed event after a reconnect does not toast twice).
pub async fn toast_ready(app: AppHandle, base: String, data: serde_json::Value) {
    if data.get("kind").and_then(|v| v.as_str()) != Some("briefing") {
        return;
    }
    let Some(id) = data.get("id").and_then(|v| v.as_str()).map(str::to_string) else {
        return;
    };
    if !valid_id(&id) {
        return;
    }
    let fired_at = read_job(&app, &base, &id)
        .await
        .as_ref()
        .and_then(|j| j.get("fired_at"))
        .and_then(|v| v.as_f64())
        .unwrap_or(0.0) as i64;
    // The same set the "fired" toasts use, keyed apart from them.
    if !first_time(&format!("{id}:ready"), fired_at) {
        return;
    }
    commands::notify(&app, TOAST_TITLE, LOCK_SCREEN);
}

#[cfg(test)]
mod tests {
    use super::*;

    const ANSWER: &str = r#"{"available": true, "building": false, "setups": [
        {"id": "s0123456789", "kind": "briefing", "repeat": "every weekday (Monday to Friday) at 07:00"}],
        "briefing": {"id": "b0123456789", "text": "Calendar: 1 event today.\n- 09:30 Dentist",
          "sections": [{"key": "calendar", "title": "Calendar", "summary": "1 event today.",
                        "items": ["09:30 Dentist"]},
                       {"key": "todo", "title": "To-do list", "summary": "2 open items.",
                        "items": ["renew prescription", "post the letter"]}]}}"#;

    #[test]
    fn the_answer_is_passed_on_and_an_older_backend_says_so() {
        let a = briefing_answer(200, ANSWER).unwrap();
        assert_eq!(a["briefing"]["id"], "b0123456789");
        assert!(briefing_answer(200, r#"{"available": true, "briefing": null}"#).is_ok());
        for old in [404, 501] {
            let a = briefing_answer(old, "{}").unwrap();
            assert_eq!(a["available"], false);
            assert_eq!(a["why"], BRIEFING_MISSING);
        }
        assert!(briefing_answer(200, r#"{"ok": true}"#).is_err());
        assert!(briefing_answer(200, "not json").is_err());
    }

    #[test]
    fn hidden_lists_keep_the_counts_but_no_line() {
        let hidden = redact(briefing_answer(200, ANSWER).unwrap());
        let s = hidden.to_string();
        assert!(!s.contains("Dentist") && !s.contains("prescription") && !s.contains("letter"));
        assert_eq!(hidden["briefing"]["hidden"], true);
        assert_eq!(hidden["briefing"]["hidden_count"], 3);
        assert_eq!(
            hidden["briefing"]["sections"][0]["summary"],
            "1 event today."
        );
        assert_eq!(hidden["hidden"], true);
    }

    #[test]
    fn settings_never_sees_the_briefing() {
        let v = setup_view(briefing_answer(200, ANSWER).unwrap());
        assert!(v["briefing"].is_null());
        assert!(!v.to_string().contains("Dentist"));
        assert_eq!(v["setups"][0]["id"], "s0123456789");
    }

    #[test]
    fn a_repeat_is_one_of_the_schedulers_rules_and_nothing_else() {
        assert_eq!(
            repeat_body("weekday", "7:00", &[]).unwrap(),
            serde_json::json!({"kind": "briefing", "repeat": {"every": "weekday", "at": "07:00"}})
        );
        assert_eq!(
            repeat_body("week", "08:30", &[4, 0, 4]).unwrap()["repeat"]["days"],
            serde_json::json!([0, 4])
        );
        assert_eq!(
            repeat_body("week", "08:30", &[]).unwrap_err(),
            "Pick at least one day."
        );
        assert!(repeat_body("week", "08:30", &[]).is_err());
        assert!(repeat_body("week", "08:30", &[7]).is_err());
        for bad in ["hours", "all", "", "month"] {
            assert!(repeat_body(bad, "07:00", &[]).is_err(), "{bad}");
        }
        for bad in ["24:00", "7", "07:60", "", "07:00:00", "x:y"] {
            assert!(repeat_body("day", bad, &[]).is_err(), "{bad}");
        }
    }

    #[test]
    fn the_senders_answer_is_the_pcs_own_and_an_older_pc_says_so() {
        let on = senders_answer(
            202,
            r#"{"ok": true, "waiting": true, "message": "Waiting for your approval."}"#,
        )
        .unwrap();
        assert_eq!(on["waiting"], true);
        let off = senders_answer(200, r#"{"ok": true, "senders": {"on": false}}"#).unwrap();
        assert_eq!(off["senders"]["on"], false);
        for old in [404, 501] {
            assert_eq!(senders_answer(old, "{}").unwrap_err(), SENDERS_MISSING);
        }
        assert!(senders_answer(200, "not json").is_err());
        assert!(senders_answer(503, r#"{"ok": false, "error": "tier"}"#).is_err());
    }

    #[test]
    fn only_a_listed_briefing_can_be_stopped() {
        let a = briefing_answer(200, ANSWER).unwrap();
        assert!(is_setup(&a, "s0123456789"));
        assert!(!is_setup(&a, "s0000000000"));
        let reminder = serde_json::json!({"setups": [{"id": "s0123456789", "kind": "reminder"}]});
        assert!(!is_setup(&reminder, "s0123456789"));
    }
}
