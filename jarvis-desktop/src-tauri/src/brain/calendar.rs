//! Jarvis's own local calendar (2026-10-29, the owner's desktop HUD request):
//! the request bodies the HUD's two commands are allowed to send, and the read
//! the HUD shows while App lock is on.
//!
//! The store and the routes are the backend's (`GET /api/calendar`,
//! `POST /api/calendar/add`, `POST /api/calendar/act` - one local SQLite file,
//! no network). This module is the DESKTOP half only:
//!
//! * [`add_body`] and [`act_body`] are the ONLY shapes that leave
//!   `hud_calendar.rs`. Every field the contract names is here with its cap,
//!   and nothing else is - so a script in the HUD page cannot turn "add one
//!   event" into any other write, and `act` has no list form and no delete-all
//!   (the same no-bulk rule `/api/schedule/act` has).
//! * [`redact_read`] is what `lock/rules.rs` applies to the read while App lock
//!   or "Hide memory lists" is on. An event's title, place and notes are the
//!   owner's own words - in the same class as a reminder's - while the dates,
//!   times, the all-day flag, the reminder minutes and the counts say nothing
//!   about him and stay, so the card can still say "3 events - hidden".
//!
//! A warning/reminder on an event is STORED, not fired in this slice: nothing
//! here starts a timer, a job or a notification. The whole module has no
//! network call of its own; the one write path is `brain::schedule::post`,
//! which adds the pairing token in Rust (the page holds none).

use serde::Deserialize;

/// The longest title the calendar reader itself accepts (`jarvis_calendar.py`),
/// so an event Jarvis writes can never be one its own reader would refuse.
const TITLE_MAX: usize = 300;
const PLACE_MAX: usize = 300;
const NOTES_MAX: usize = 2_000;
/// A reminder up to a week ahead. The backend stores the field; nothing rings
/// in this slice.
const REMIND_MAX: i64 = 10_080;
/// The recurrence words the page offers, and the only ones this builder lets
/// out. They are the BACKEND's own vocabulary, not the page's idea of it:
/// `jarvis_local_calendar.RECURRENCES` is `("none", "daily", "weekly",
/// "monthly")`, and its `_recurrence` refuses anything else with a 400 - so a
/// page sending "week" would have been refused by the store every time. No
/// repeat is the empty string on the wire (see [`put_recurrence`]), which the
/// store reads as "none". A closed set, never free text.
const RECURRENCE: [&str; 3] = ["daily", "weekly", "monthly"];
/// The event id's shape in the contract: "c" + 10 lowercase hex.
const ID_LEN: usize = 11;

/// One update's fields, all optional: only what the owner changed is sent.
///
/// `Some("")` is a CLEAR for `place`/`notes`/`time`/`end_time` (the page's own
/// empty input), while `None` means "leave it as it is". A field that is not
/// here cannot be sent by the HUD at all.
#[derive(Debug, Default, Clone, Deserialize)]
pub struct CalendarChange {
    pub title: Option<String>,
    pub date: Option<String>,
    #[serde(default)]
    pub time: Option<String>,
    #[serde(default)]
    pub end_date: Option<String>,
    #[serde(default)]
    pub end_time: Option<String>,
    #[serde(default)]
    pub all_day: Option<bool>,
    #[serde(default)]
    pub place: Option<String>,
    #[serde(default)]
    pub notes: Option<String>,
    #[serde(default)]
    pub remind_minutes: Option<i64>,
    #[serde(default)]
    pub recurrence: Option<String>,
}

impl CalendarChange {
    /// True when there is nothing to change: an `update` with no field would
    /// be a write that changes nothing, so it is refused instead of sent.
    pub fn is_empty(&self) -> bool {
        self.title.is_none()
            && self.date.is_none()
            && self.time.is_none()
            && self.end_date.is_none()
            && self.end_time.is_none()
            && self.all_day.is_none()
            && self.place.is_none()
            && self.notes.is_none()
            && self.remind_minutes.is_none()
            && self.recurrence.is_none()
    }
}

/// `POST /api/calendar/add`'s body: ONE event, every field capped.
///
/// `all_day` drops `time`/`end_time` rather than refusing them (an all-day
/// event has no time of day, and the page's own all-day tick leaves the two
/// boxes alone), and an empty optional string is simply not sent.
#[allow(clippy::too_many_arguments)]
pub(crate) fn add_body(
    title: &str,
    date: &str,
    time: Option<&str>,
    end_date: Option<&str>,
    end_time: Option<&str>,
    all_day: bool,
    place: Option<&str>,
    notes: Option<&str>,
    remind_minutes: Option<i64>,
    recurrence: Option<&str>,
) -> Result<serde_json::Value, String> {
    let title = title.trim();
    if title.is_empty() {
        return Err("An event needs a title.".to_string());
    }
    if title.chars().count() > TITLE_MAX {
        return Err(format!("A title can be up to {TITLE_MAX} characters."));
    }
    let start = parse_day(date)
        .ok_or_else(|| "The date must be a real day written like 2026-11-03.".to_string())?;
    let mut body = serde_json::json!({ "title": title, "date": date, "all_day": all_day });
    let map = body.as_object_mut().expect("a JSON object");

    if all_day {
        let end = match end_date.map(str::trim).filter(|s| !s.is_empty()) {
            Some(day) => {
                let end = parse_day(day).ok_or_else(|| {
                    "The last day must be a real day written like 2026-11-03.".to_string()
                })?;
                if end < start {
                    return Err("An event cannot end before it starts.".to_string());
                }
                Some(day)
            }
            None => None,
        };
        if let Some(day) = end {
            if day != date {
                map.insert("end_date".into(), serde_json::json!(day));
            }
        }
    } else {
        let start_min = parse_time(time.unwrap_or(""))
            .ok_or_else(|| "A timed event needs a start time written like 14:30.".to_string())?;
        map.insert("time".into(), serde_json::json!(time.unwrap_or("").trim()));
        let end = match end_time.map(str::trim).filter(|s| !s.is_empty()) {
            Some(t) => Some(
                parse_time(t)
                    .ok_or_else(|| "The end time must be written like 15:15.".to_string())?,
            ),
            None => None,
        };
        let end_day = match end_date.map(str::trim).filter(|s| !s.is_empty()) {
            Some(day) => parse_day(day).ok_or_else(|| {
                "The last day must be a real day written like 2026-11-03.".to_string()
            })?,
            None => start,
        };
        if end_day < start {
            return Err("An event cannot end before it starts.".to_string());
        }
        if let Some(end_min) = end {
            let start_at = day_minutes(start) + start_min;
            let end_at = day_minutes(end_day) + end_min;
            if end_at <= start_at {
                return Err("The end must be after the start.".to_string());
            }
            map.insert(
                "end_time".into(),
                serde_json::json!(end_time.unwrap_or("").trim()),
            );
            if end_day != start {
                map.insert(
                    "end_date".into(),
                    serde_json::json!(end_date.unwrap_or("").trim()),
                );
            }
        }
    }
    put_words(&mut body, place, notes)?;
    put_reminder(&mut body, remind_minutes)?;
    put_recurrence(&mut body, recurrence)?;
    Ok(body)
}

/// `POST /api/calendar/act`'s body: ONE event, `delete` or `update`.
///
/// There is no other verb, no list, no range and no "all": the same narrowness
/// `brain::schedule::act_body` has, and the same reason.
pub(crate) fn act_body(
    id: &str,
    action: &str,
    change: Option<&CalendarChange>,
) -> Result<serde_json::Value, String> {
    if !is_id(id) {
        return Err("That is not one of the calendar's events.".to_string());
    }
    match action {
        "delete" => {
            if change.is_some_and(|c| !c.is_empty()) {
                return Err("A delete takes no fields.".to_string());
            }
            Ok(serde_json::json!({ "id": id, "do": "delete" }))
        }
        "update" => {
            let change = change
                .filter(|c| !c.is_empty())
                .ok_or_else(|| "There is nothing to change.".to_string())?;
            let mut body = serde_json::json!({ "id": id, "do": "update" });
            if let Some(title) = &change.title {
                let title = title.trim();
                if title.is_empty() {
                    return Err("An event needs a title.".to_string());
                }
                if title.chars().count() > TITLE_MAX {
                    return Err(format!("A title can be up to {TITLE_MAX} characters."));
                }
                body["title"] = serde_json::json!(title);
            }
            let start = match &change.date {
                Some(day) => {
                    let start = parse_day(day).ok_or_else(|| {
                        "The date must be a real day written like 2026-11-03.".to_string()
                    })?;
                    body["date"] = serde_json::json!(day);
                    Some(start)
                }
                None => None,
            };
            let end_day = match &change.end_date {
                Some(day) => {
                    let day = day.trim();
                    if day.is_empty() {
                        body["end_date"] = serde_json::json!("");
                        None
                    } else {
                        let parsed = parse_day(day).ok_or_else(|| {
                            "The last day must be a real day written like 2026-11-03.".to_string()
                        })?;
                        body["end_date"] = serde_json::json!(day);
                        Some(parsed)
                    }
                }
                None => None,
            };
            if let (Some(start), Some(end)) = (start, end_day) {
                if end < start {
                    return Err("An event cannot end before it starts.".to_string());
                }
            }
            let all_day = change.all_day;
            if all_day == Some(true) {
                // An all-day event has no times of day: clear them rather than
                // leaving a stale 14:30 under a day-long event.
                if change.time.as_deref().is_some_and(|t| !t.trim().is_empty())
                    || change
                        .end_time
                        .as_deref()
                        .is_some_and(|t| !t.trim().is_empty())
                {
                    return Err("An all-day event has no times.".to_string());
                }
                body["time"] = serde_json::json!("");
                body["end_time"] = serde_json::json!("");
            } else {
                let start_min = put_time(
                    &mut body,
                    "time",
                    change.time.as_deref(),
                    "The start time must be written like 14:30.",
                )?;
                let end_min = put_time(
                    &mut body,
                    "end_time",
                    change.end_time.as_deref(),
                    "The end time must be written like 15:15.",
                )?;
                // Both ends known and on one day is the only pair an edit can
                // prove out of order; a single end is the store's own check.
                if let (Some(start), Some(end_min)) = (start, end_min) {
                    let same_day = end_day.is_none_or(|end| end == start);
                    if let Some(start_min) = start_min {
                        if same_day && end_min <= start_min {
                            return Err("The end must be after the start.".to_string());
                        }
                        if end_day.is_some_and(|end| {
                            day_minutes(end) + end_min <= day_minutes(start) + start_min
                        }) {
                            return Err("The end must be after the start.".to_string());
                        }
                    }
                }
            }
            if let Some(flag) = all_day {
                body["all_day"] = serde_json::json!(flag);
            }
            put_words(&mut body, change.place.as_deref(), change.notes.as_deref())?;
            put_reminder(&mut body, change.remind_minutes)?;
            put_recurrence(&mut body, change.recurrence.as_deref())?;
            // An empty repeat box on an edit means "stop repeating", which is
            // a clear rather than an omission; the add path treats empty as
            // "no repeat" for the same reason.
            if change
                .recurrence
                .as_deref()
                .is_some_and(|r| r.trim().is_empty())
            {
                body["recurrence"] = serde_json::json!("");
            }
            Ok(body)
        }
        _ => Err("The HUD can only delete or change one event.".to_string()),
    }
}

/// The place's and the notes' caps, and an empty box meaning "remove it".
fn put_words(
    body: &mut serde_json::Value,
    place: Option<&str>,
    notes: Option<&str>,
) -> Result<(), String> {
    if let Some(place) = place {
        let place = place.trim();
        if place.chars().count() > PLACE_MAX {
            return Err(format!("A place can be up to {PLACE_MAX} characters."));
        }
        body["place"] = serde_json::json!(place);
    }
    if let Some(notes) = notes {
        let notes = notes.trim();
        if notes.chars().count() > NOTES_MAX {
            return Err(format!("Notes can be up to {NOTES_MAX} characters."));
        }
        body["notes"] = serde_json::json!(notes);
    }
    Ok(())
}

/// One time field on an update: an empty box clears it, a real `HH:MM` is
/// sent, and anything else is refused. Returns its minutes when there was one.
fn put_time(
    body: &mut serde_json::Value,
    key: &str,
    time: Option<&str>,
    why: &str,
) -> Result<Option<i64>, String> {
    match time {
        None => Ok(None),
        Some(raw) => {
            let raw = raw.trim();
            if raw.is_empty() {
                body[key] = serde_json::json!("");
                return Ok(None);
            }
            let minutes = parse_time(raw).ok_or_else(|| why.to_string())?;
            body[key] = serde_json::json!(raw);
            Ok(Some(minutes))
        }
    }
}

fn put_reminder(body: &mut serde_json::Value, minutes: Option<i64>) -> Result<(), String> {
    if let Some(minutes) = minutes {
        if !(0..=REMIND_MAX).contains(&minutes) {
            return Err("A reminder can be from 0 to 10080 minutes before.".to_string());
        }
        body["remind_minutes"] = serde_json::json!(minutes);
    }
    Ok(())
}

fn put_recurrence(body: &mut serde_json::Value, recurrence: Option<&str>) -> Result<(), String> {
    if let Some(recurrence) = recurrence.map(str::trim).filter(|s| !s.is_empty()) {
        if !RECURRENCE.contains(&recurrence) {
            return Err("That repeat is not one the calendar offers.".to_string());
        }
        body["recurrence"] = serde_json::json!(recurrence);
    }
    Ok(())
}

fn is_id(id: &str) -> bool {
    id.len() == ID_LEN
        && id.starts_with('c')
        && id[1..]
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

/// A day written `YYYY-MM-DD`, as a real calendar date.
fn parse_day(day: &str) -> Option<(i32, u32, u32)> {
    let b = day.as_bytes();
    if b.len() != 10 || b[4] != b'-' || b[7] != b'-' {
        return None;
    }
    if !b
        .iter()
        .enumerate()
        .all(|(i, c)| i == 4 || i == 7 || c.is_ascii_digit())
    {
        return None;
    }
    let year: i32 = day[0..4].parse().ok()?;
    let month: u32 = day[5..7].parse().ok()?;
    let date: u32 = day[8..10].parse().ok()?;
    if !(1..=12).contains(&month) || date == 0 || date > days_in_month(year, month) {
        return None;
    }
    Some((year, month, date))
}

fn is_leap(year: i32) -> bool {
    (year % 4 == 0 && year % 100 != 0) || year % 400 == 0
}

fn days_in_month(year: i32, month: u32) -> u32 {
    match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if is_leap(year) => 29,
        2 => 28,
        _ => 0,
    }
}

/// Days since 1970-01-01 (Howard Hinnant's civil-from-days, inverted), so two
/// days can be compared without a date crate - this crate has none.
fn day_minutes((year, month, date): (i32, u32, u32)) -> i64 {
    let y = if month <= 2 { year - 1 } else { year } as i64;
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = y - era * 400;
    let m = month as i64;
    let doy = (153 * (if m > 2 { m - 3 } else { m + 9 }) + 2) / 5 + date as i64 - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    (era * 146_097 + doe - 719_468) * 1_440
}

/// Minutes into the day for `HH:MM`, 00:00..=23:59.
fn parse_time(time: &str) -> Option<i64> {
    let b = time.as_bytes();
    if b.len() != 5 || b[2] != b':' {
        return None;
    }
    if !b
        .iter()
        .enumerate()
        .all(|(i, c)| i == 2 || c.is_ascii_digit())
    {
        return None;
    }
    let hours: i64 = time[0..2].parse().ok()?;
    let minutes: i64 = time[3..5].parse().ok()?;
    if hours > 23 || minutes > 59 {
        return None;
    }
    Some(hours * 60 + minutes)
}

/// The calendar read with the owner's words taken out, for `lock/rules.rs`.
///
/// The same shape `brain::schedule::redact_list` produces: every event keeps
/// its id, date, time, end, all-day flag, reminder minutes, recurrence, time
/// zone and source (none of which are words), while the title, the place and
/// the notes become `""`; `hidden` and `hidden_count` say how many titles were
/// blanked. The window, `sources` and the `on`/`available` flags are numbers,
/// fixed words and booleans, so they stay and the card can still say "3 events
/// - hidden".
pub(crate) fn redact_read(mut read: serde_json::Value) -> serde_json::Value {
    let mut count = 0usize;
    if let Some(object) = read.as_object_mut() {
        if let Some(serde_json::Value::Array(events)) = object.get_mut("events") {
            for event in events.iter_mut() {
                if let Some(fields) = event.as_object_mut() {
                    if fields
                        .get("title")
                        .and_then(|t| t.as_str())
                        .is_some_and(|t| !t.is_empty())
                    {
                        count += 1;
                    }
                    for key in ["title", "place", "notes"] {
                        if fields.contains_key(key) {
                            fields.insert(key.into(), serde_json::json!(""));
                        }
                    }
                }
            }
        }
        object.insert("hidden".into(), serde_json::Value::Bool(true));
        object.insert("hidden_count".into(), serde_json::json!(count));
        read
    } else {
        serde_json::json!({ "available": false, "hidden": true })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn one_timed_event_sends_exactly_the_contract_fields() {
        let body = add_body(
            "  Dentist  ",
            "2026-11-03",
            Some("14:30"),
            Some("2026-11-03"),
            Some("15:15"),
            false,
            Some("High Street"),
            Some("Bring the form"),
            Some(30),
            Some("weekly"),
        )
        .unwrap();
        assert_eq!(
            body,
            json!({
                "title": "Dentist",
                "date": "2026-11-03",
                "all_day": false,
                "time": "14:30",
                "end_time": "15:15",
                "place": "High Street",
                "notes": "Bring the form",
                "remind_minutes": 30,
                "recurrence": "weekly",
            }),
            "a same-day event must not send an end_date the store did not ask for"
        );
    }

    #[test]
    fn a_spanning_all_day_event_keeps_its_days_and_drops_its_times() {
        let body = add_body(
            "Trip",
            "2026-11-03",
            Some("09:00"),
            Some("2026-11-05"),
            Some("18:00"),
            true,
            None,
            None,
            None,
            None,
        )
        .unwrap();
        assert_eq!(body["all_day"], true);
        assert_eq!(body["end_date"], "2026-11-05");
        assert!(
            body.get("time").is_none(),
            "an all-day event kept a time: {body}"
        );
        assert!(body.get("end_time").is_none(), "{body}");
        assert!(
            body.get("place").is_none(),
            "an empty box is not sent: {body}"
        );
    }

    #[test]
    fn a_timed_event_that_spans_days_sends_both_ends() {
        let body = add_body(
            "Night shift",
            "2026-11-03",
            Some("22:00"),
            Some("2026-11-04"),
            Some("06:00"),
            false,
            None,
            None,
            None,
            None,
        )
        .unwrap();
        assert_eq!(body["date"], "2026-11-03");
        assert_eq!(body["time"], "22:00");
        assert_eq!(body["end_date"], "2026-11-04");
        assert_eq!(body["end_time"], "06:00");
    }

    #[test]
    fn a_bad_event_is_refused_in_words_before_anything_is_sent() {
        let ok = |body: Result<serde_json::Value, String>| {
            assert!(body.is_err(), "this should have been refused: {body:?}");
        };
        // No title, and a title longer than the reader's own cap.
        ok(add_body(
            "",
            "2026-11-03",
            Some("09:00"),
            None,
            None,
            false,
            None,
            None,
            None,
            None,
        ));
        ok(add_body(
            "   ",
            "2026-11-03",
            Some("09:00"),
            None,
            None,
            false,
            None,
            None,
            None,
            None,
        ));
        ok(add_body(
            &"x".repeat(TITLE_MAX + 1),
            "2026-11-03",
            Some("09:00"),
            None,
            None,
            false,
            None,
            None,
            None,
            None,
        ));
        // A day that is not a day: 30 February, month 13, the wrong shape.
        for day in [
            "2026-02-30",
            "2026-13-01",
            "2026-1-01",
            "03/11/2026",
            "2026-11-00",
        ] {
            ok(add_body(
                "x",
                day,
                Some("09:00"),
                None,
                None,
                false,
                None,
                None,
                None,
                None,
            ));
        }
        // A timed event with no time, or a time that is not one.
        ok(add_body(
            "x",
            "2026-11-03",
            None,
            None,
            None,
            false,
            None,
            None,
            None,
            None,
        ));
        ok(add_body(
            "x",
            "2026-11-03",
            Some("24:00"),
            None,
            None,
            false,
            None,
            None,
            None,
            None,
        ));
        ok(add_body(
            "x",
            "2026-11-03",
            Some("9:00"),
            None,
            None,
            false,
            None,
            None,
            None,
            None,
        ));
        // Ends before it starts, on one day and across days.
        ok(add_body(
            "x",
            "2026-11-03",
            Some("15:00"),
            None,
            Some("14:00"),
            false,
            None,
            None,
            None,
            None,
        ));
        ok(add_body(
            "x",
            "2026-11-03",
            Some("15:00"),
            None,
            Some("15:00"),
            false,
            None,
            None,
            None,
            None,
        ));
        ok(add_body(
            "Trip",
            "2026-11-03",
            None,
            Some("2026-11-02"),
            None,
            true,
            None,
            None,
            None,
            None,
        ));
        // Caps, a reminder out of range, and a repeat word that is not offered.
        ok(add_body(
            "x",
            "2026-11-03",
            Some("09:00"),
            None,
            None,
            false,
            Some(&"p".repeat(PLACE_MAX + 1)),
            None,
            None,
            None,
        ));
        ok(add_body(
            "x",
            "2026-11-03",
            Some("09:00"),
            None,
            None,
            false,
            None,
            Some(&"n".repeat(NOTES_MAX + 1)),
            None,
            None,
        ));
        ok(add_body(
            "x",
            "2026-11-03",
            Some("09:00"),
            None,
            None,
            false,
            None,
            None,
            Some(REMIND_MAX + 1),
            None,
        ));
        ok(add_body(
            "x",
            "2026-11-03",
            Some("09:00"),
            None,
            None,
            false,
            None,
            None,
            Some(-1),
            None,
        ));
        ok(add_body(
            "x",
            "2026-11-03",
            Some("09:00"),
            None,
            None,
            false,
            None,
            None,
            None,
            Some("hourly"),
        ));
    }

    #[test]
    fn a_heightened_repeat_is_the_pages_five_words_and_nothing_else() {
        for word in RECURRENCE {
            let body = add_body(
                "x",
                "2026-11-03",
                Some("09:00"),
                None,
                None,
                false,
                None,
                None,
                None,
                Some(word),
            )
            .unwrap();
            assert_eq!(body["recurrence"], word);
        }
        // The empty box means "does not repeat": no key at all.
        let body = add_body(
            "x",
            "2026-11-03",
            Some("09:00"),
            None,
            None,
            false,
            None,
            None,
            None,
            Some("  "),
        )
        .unwrap();
        assert!(body.get("recurrence").is_none(), "{body}");
    }

    #[test]
    fn one_delete_takes_an_id_and_nothing_else() {
        let id = "c0123456789";
        assert_eq!(
            act_body(id, "delete", None).unwrap(),
            json!({"id": id, "do": "delete"})
        );
        // Another verb, another shape of id, and a delete carrying fields are
        // all refused: no list form, no delete-all, no guessed id.
        for action in ["add", "delete_all", "clear", "move", "snooze", ""] {
            assert!(act_body(id, action, None).is_err(), "{action} was allowed");
        }
        for bad in [
            "",
            "c012345678",
            "c01234567890",
            "s0123456789",
            "C0123456789",
            "c012345678g",
            "c0123456789 ",
        ] {
            assert!(act_body(bad, "delete", None).is_err(), "{bad} was allowed");
        }
        let change = CalendarChange {
            title: Some("x".into()),
            ..Default::default()
        };
        assert!(act_body(id, "delete", Some(&change)).is_err());
    }

    #[test]
    fn one_update_sends_only_the_fields_the_owner_changed() {
        let id = "c0123456789";
        let change = CalendarChange {
            title: Some("  Lunch  ".into()),
            place: Some("".into()),
            ..Default::default()
        };
        assert_eq!(
            act_body(id, "update", Some(&change)).unwrap(),
            json!({"id": id, "do": "update", "title": "Lunch", "place": ""})
        );
        // Nothing to change is not a write.
        assert!(act_body(id, "update", None).is_err());
        assert!(act_body(id, "update", Some(&CalendarChange::default())).is_err());
        // The same caps and shapes apply on an update.
        let too_long = CalendarChange {
            notes: Some("n".repeat(NOTES_MAX + 1)),
            ..Default::default()
        };
        assert!(act_body(id, "update", Some(&too_long)).is_err());
        let bad_day = CalendarChange {
            date: Some("2026-02-30".into()),
            ..Default::default()
        };
        assert!(act_body(id, "update", Some(&bad_day)).is_err());
        let bad_repeat = CalendarChange {
            recurrence: Some("fortnight".into()),
            ..Default::default()
        };
        assert!(act_body(id, "update", Some(&bad_repeat)).is_err());
        // Emptying the repeat box is a CLEAR, not an omission.
        let clear = CalendarChange {
            recurrence: Some("  ".into()),
            ..Default::default()
        };
        assert_eq!(
            act_body(id, "update", Some(&clear)).unwrap()["recurrence"],
            ""
        );
    }

    #[test]
    fn an_all_day_tick_clears_the_times_and_refuses_new_ones() {
        let id = "c0123456789";
        let tick = CalendarChange {
            all_day: Some(true),
            ..Default::default()
        };
        assert_eq!(
            act_body(id, "update", Some(&tick)).unwrap(),
            json!({"id": id, "do": "update", "all_day": true,
                   "time": "", "end_time": ""})
        );
        let mixed = CalendarChange {
            all_day: Some(true),
            time: Some("14:30".into()),
            ..Default::default()
        };
        assert!(act_body(id, "update", Some(&mixed)).is_err());
        let untick = CalendarChange {
            all_day: Some(false),
            ..Default::default()
        };
        assert_eq!(
            act_body(id, "update", Some(&untick)).unwrap()["all_day"],
            false
        );
    }

    #[test]
    fn the_locked_read_keeps_the_shape_and_loses_every_word() {
        let read = json!({
            "available": true,
            "on": true,
            "days": 90,
            "window": {"start": "2026-10-29", "end": "2027-01-26"},
            "sources": {"local": {"state": "on", "count": 2}, "google": {"state": "not_on_a_screen"}},
            "events": [
                {"id": "c0123456789", "title": "Dentist", "date": "2026-11-03",
                 "time": "14:30", "all_day": false, "place": "High Street",
                 "notes": "Bring Priya's form", "remind_minutes": 30,
                 "recurrence": "weekly", "tz": "America/Los_Angeles", "source": "local"},
                {"id": "c012345678a", "title": "", "date": "2026-11-04",
                 "all_day": true, "place": "", "notes": "", "source": "local"}
            ]
        });
        let out = redact_read(read);
        let text = out.to_string();
        for word in ["Dentist", "High Street", "Priya", "form"] {
            assert!(!text.contains(word), "{word} survived the lock: {text}");
        }
        assert_eq!(out["events"][0]["title"], "");
        assert_eq!(out["events"][0]["place"], "");
        assert_eq!(out["events"][0]["notes"], "");
        // The facts that are not words stay, so the card can still be drawn.
        assert_eq!(out["events"][0]["id"], "c0123456789");
        assert_eq!(out["events"][0]["date"], "2026-11-03");
        assert_eq!(out["events"][0]["time"], "14:30");
        assert_eq!(out["events"][0]["all_day"], false);
        assert_eq!(out["events"][0]["remind_minutes"], 30);
        assert_eq!(out["events"][0]["tz"], "America/Los_Angeles");
        assert_eq!(out["events"][0]["source"], "local");
        assert_eq!(out["events"][1]["all_day"], true);
        assert_eq!(out["available"], true);
        assert_eq!(out["on"], true);
        assert_eq!(out["days"], 90);
        assert_eq!(out["window"]["start"], "2026-10-29");
        assert_eq!(out["sources"]["local"]["count"], 2);
        assert_eq!(out["hidden"], true);
        assert_eq!(out["hidden_count"], 1, "one event had a title: {out}");
        // A body that is not JSON becomes the honest hidden reply, never the
        // unreadable original.
        assert_eq!(
            redact_read(serde_json::Value::Null),
            json!({"available": false, "hidden": true})
        );
    }

    #[test]
    fn this_module_has_no_network_of_its_own() {
        // The project proves the no-egress claims by grepping the source
        // (docs/CLAIMS.tsv's `grep:` kind), and the same check belongs beside
        // the code it is about: the only write path is schedule::post.
        let source = include_str!("calendar.rs");
        let head = source.split("mod tests").next().unwrap_or(source);
        for word in ["reqwest", "socket", "TcpStream", "urllib"] {
            assert!(!head.contains(word), "the calendar builder grew a {word}");
        }
    }
}
