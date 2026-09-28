//! "Photo to reminder" (the owner's choice, 2026-09-28; backend
//! `jarvis_photo_remind.py`, photo-reminder.patch; JARVIS-API.md section 83).
//!
//! Two commands, for the Jarvis bar (a screen capture, Alt+Shift+S) and the
//! Brain's Coming up (a picture file the owner chooses):
//!
//! * [`photo_scan`] - `POST /api/photo/scan {"image": "data:image/...;base64,"}`:
//!   the PC reads the words in the picture with Windows' own text
//!   recognition and finds a date, a time and a title with plain code. It
//!   PROPOSES; it sets nothing up. The words are outside text (the answer
//!   says `"outside": true`) and are held on the page only until it is
//!   closed - never saved by this app.
//! * [`photo_add_reminder`] - `POST /api/schedule/add {"kind": "reminder",
//!   "date", "time", "text"}`: the owner's tap on "Add a Jarvis reminder",
//!   with the words and times as the owner left them. The PC reads the date
//!   and time on its own clock. No card, like any one-off reminder the
//!   owner sets; held while the event stream is stale (rule 4), like every
//!   change.
//!
//! The answer-reading functions are plain functions of (status, body) so
//! their tests run without a Tauri app or a network.

use std::time::Duration;

use tauri::AppHandle;

use super::{require_link_live, WRITE_TIMEOUT};
use crate::commands;

/// Windows gets 30 seconds to read one picture (`jarvis_ocr.TIMEOUT_S`);
/// this waits a little longer so its own sentence arrives.
const SCAN_TIMEOUT: Duration = Duration::from_secs(45);

/// The biggest picture sent: the PC refuses any request over 4 MiB.
const MAX_IMAGE_CHARS: usize = 4 * 1024 * 1024 - 1024;

/// A PC without the route (the phone says the same, `PhotoReminder.MISSING`).
pub(crate) const PHOTO_MISSING: &str =
    "Your PC's Jarvis cannot read dates in pictures yet - run apply-patches.ps1 on the PC.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

/// Only a picture as a `data:image/...;base64,` address is sent - never a
/// web address, never a file path - and never one over the PC's limit.
pub(crate) fn scan_body(image: &str) -> Result<serde_json::Value, String> {
    let image = image.trim();
    let head: String = image
        .chars()
        .take(48)
        .collect::<String>()
        .to_ascii_lowercase();
    if !head.starts_with("data:image/") || !head.contains(";base64,") {
        return Err("That is not a picture Jarvis can read.".to_string());
    }
    if image.len() > MAX_IMAGE_CHARS {
        return Err("The picture is too big. Try a smaller screenshot or photo.".to_string());
    }
    Ok(serde_json::json!({ "image": image }))
}

/// [`photo_scan`]'s reading: 2xx with a `found` list, or the PC's own
/// sentence (a 503 from Windows' text recognition says why in `error`).
pub(crate) fn scan_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("found").is_some_and(|f| f.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 || status == 501 {
        return Err(PHOTO_MISSING.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// The one reminder the owner's tap adds. The date and time are checked in
/// shape here and read on the PC's clock there.
pub(crate) fn reminder_body(
    date: &str,
    time: &str,
    text: &str,
) -> Result<serde_json::Value, String> {
    let date = date.trim();
    let time = time.trim();
    let text = text.trim();
    let date_ok = date.len() == 10
        && date.char_indices().all(|(i, c)| {
            if i == 4 || i == 7 {
                c == '-'
            } else {
                c.is_ascii_digit()
            }
        });
    if !date_ok {
        return Err("A date looks like 2026-10-12.".to_string());
    }
    let t: Vec<&str> = time.split(':').collect();
    let time_ok = t.len() == 2
        && (1..=2).contains(&t[0].len())
        && t[1].len() == 2
        && t.iter().all(|p| p.chars().all(|c| c.is_ascii_digit()))
        && t[0].parse::<u32>().is_ok_and(|h| h < 24)
        && t[1].parse::<u32>().is_ok_and(|m| m < 60);
    if !time_ok {
        return Err("A time looks like 14:00.".to_string());
    }
    if text.is_empty() {
        return Err("A reminder needs some words: what should Jarvis remind you of?".to_string());
    }
    Ok(serde_json::json!({ "kind": "reminder", "date": date, "time": time, "text": text }))
}

async fn post(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
    timeout: Duration,
) -> Result<(u16, String), String> {
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
    Ok((status, text))
}

/// Reads the dates in one picture and PROPOSES a reminder. Sets nothing up.
#[tauri::command]
pub async fn photo_scan(app: AppHandle, image: String) -> Result<serde_json::Value, String> {
    let body = scan_body(&image)?;
    drop(image);
    let (status, text) = post(&app, "/api/photo/scan", body, SCAN_TIMEOUT).await?;
    scan_answer(status, &text)
}

/// The owner's tap: one reminder, no card. Held on a stale link.
#[tauri::command]
pub async fn photo_add_reminder(
    app: AppHandle,
    date: String,
    time: String,
    text: String,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let body = reminder_body(&date, &time, &text)?;
    let (status, answer) = post(&app, "/api/schedule/add", body, WRITE_TIMEOUT).await?;
    super::schedule::change_answer(status, &answer)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_a_picture_as_a_data_address_is_sent() {
        assert!(scan_body("data:image/jpeg;base64,AAAA").is_ok());
        assert!(scan_body("data:image/png;base64,AAAA").is_ok());
        assert!(scan_body("https://example.com/flyer.png").is_err());
        assert!(scan_body("C:\\Users\\me\\flyer.png").is_err());
        assert!(scan_body("data:text/html;base64,PGgxPg==").is_err());
        let big = format!("data:image/jpeg;base64,{}", "A".repeat(MAX_IMAGE_CHARS));
        assert!(scan_body(&big).is_err());
    }

    #[test]
    fn a_scan_answer_is_read_or_said_plainly() {
        let ok = scan_answer(200, r#"{"ok":true,"outside":true,"found":[]}"#).unwrap();
        assert_eq!(ok["outside"], true);
        assert!(scan_answer(200, r#"{"ok":true}"#).is_err());
        assert_eq!(scan_answer(404, "").unwrap_err(), PHOTO_MISSING);
        let why = scan_answer(
            503,
            r#"{"ok":false,"error":"Windows could not read the words in the picture."}"#,
        )
        .unwrap_err();
        assert!(!why.is_empty());
    }

    #[test]
    fn the_tap_sends_one_reminder_in_the_owners_words() {
        let b = reminder_body("2026-10-12", "14:00", " Summer fair ").unwrap();
        assert_eq!(b["kind"], "reminder");
        assert_eq!(b["date"], "2026-10-12");
        assert_eq!(b["time"], "14:00");
        assert_eq!(b["text"], "Summer fair");
        assert!(b.get("repeat").is_none());
        assert!(reminder_body("12/10/2026", "14:00", "x").is_err());
        assert!(reminder_body("2026-10-12", "2pm", "x").is_err());
        assert!(reminder_body("2026-10-12", "24:00", "x").is_err());
        assert!(reminder_body("2026-10-12", "14:00", "  ").is_err());
    }
}
