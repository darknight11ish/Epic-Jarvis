//! Brain -> History -> "Forget a time frame" (the owner's decision of
//! 2026-09-28; backend/jarvis_forget_range.py, forget-range.patch;
//! JARVIS-API.md section 64).
//!
//! The owner picks some days; the PC lists what Jarvis learned and the chats
//! from then, each ticked; the owner unticks any to keep and presses "Forget
//! these"; the PC raises ONE approval card listing every item, decided by a
//! tap (never by voice); approved, the facts are forgotten (as Forget does)
//! and the chats deleted, with 10 minutes to Undo.
//!
//! Two commands, Brain window only (permissions/surfaces.toml,
//! `brain-forget-range`):
//!
//! * [`forget_range_read`] - `GET /api/memory/forget_range` (the status:
//!   a card waiting, the Undo window, the days a spoken request filled in)
//!   or `.../preview` (the list). A read, never held. While "Windows Hello
//!   for memory lists and chat history" hides the Brain's private lists, or
//!   App lock has locked Jarvis, the list comes back here with every fact's
//!   words and every chat's title taken out - only the counts and the days
//!   stay (lock.rs) - exactly like the History list.
//! * [`forget_range_write`] - ONE of two things, named by an action from a
//!   fixed list (the page never names a URL): `forget` (the ids still
//!   ticked, to the PC, which raises the card) - refused while the lists are
//!   hidden (the owner must be able to read what goes) and held while the
//!   event stream is stale (rule 4: it acts on a list the window read); and
//!   `undo` - one tap, no card, never held: it only puts back what the owner
//!   had a few minutes ago, and holding it could let the ten minutes run out
//!   and lose the chats for good.
//!
//! The answer-reading functions are plain functions of (status, body), so
//! their tests run against the real answers (`tests/fixtures/
//! forget-range-cases.json`, made by tools/gen_forget_range_cases.py).

use tauri::{AppHandle, Manager};

use super::{READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

pub(crate) const STATUS_PATH: &str = "/api/memory/forget_range";
pub(crate) const PREVIEW_PATH: &str = "/api/memory/forget_range/preview";
pub(crate) const UNDO_PATH: &str = "/api/memory/forget_range/undo";

/// A PC without `jarvis_forget_range.py` / `forget-range.patch`. The phone
/// and forget-range.js say the same - all from the contract's `words.missing`.
pub(crate) const FORGET_RANGE_MISSING: &str =
    "Your PC's Jarvis cannot forget a time frame yet - run apply-patches.ps1 on the PC.";

const STALE: &str =
    "The connection to Jarvis is catching up, so nothing can be sent until it does.";

/// Forget these, while the list's words are hidden: the owner must be able
/// to read what goes before a card is raised for it.
pub(crate) const STILL_HIDDEN: &str = "Your memory lists and chat history are hidden. Press \
     Show and confirm it is you with Windows Hello, then read the list before you forget it.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

/// The quick choices the PC offers (jarvis_forget_range.PRESETS). Nothing
/// else reaches the query string.
pub(crate) const PRESETS: &[&str] = &[
    "today",
    "yesterday",
    "this_week",
    "last_week",
    "last_7_days",
    "this_month",
    "last_month",
];

/// A date the PC reads: "2026-09-01", or with a time, "2026-09-28T09:30".
pub(crate) fn is_when(s: &str) -> bool {
    let b = s.as_bytes();
    let digits = |r: std::ops::Range<usize>| r.into_iter().all(|i| b[i].is_ascii_digit());
    match b.len() {
        10 => digits(0..4) && b[4] == b'-' && digits(5..7) && b[7] == b'-' && digits(8..10),
        16 => {
            digits(0..4)
                && b[4] == b'-'
                && digits(5..7)
                && b[7] == b'-'
                && digits(8..10)
                && b[10] == b'T'
                && digits(11..13)
                && b[13] == b':'
                && digits(14..16)
        }
        _ => false,
    }
}

/// `kinds` for the query: "facts", "chats" or both, nothing else.
fn kinds_query(kinds: Option<&[String]>) -> Result<String, String> {
    let Some(kinds) = kinds else {
        return Ok("facts,chats".to_string());
    };
    let mut out = Vec::new();
    for k in ["facts", "chats"] {
        if kinds.iter().any(|x| x == k) {
            out.push(k);
        }
    }
    if out.is_empty() || kinds.iter().any(|x| x != "facts" && x != "chats") {
        return Err("Choose what Jarvis learned, chats, or both.".to_string());
    }
    Ok(out.join(","))
}

/// The GET path: the status (no preview asked for), or the list for a
/// quick choice or two dates.
pub(crate) fn read_path(
    preview: bool,
    preset: Option<&str>,
    from: Option<&str>,
    to: Option<&str>,
    kinds: Option<&[String]>,
) -> Result<String, String> {
    if !preview {
        return Ok(STATUS_PATH.to_string());
    }
    let kinds = kinds_query(kinds)?;
    if let Some(p) = preset {
        if !PRESETS.contains(&p) {
            return Err("Pick one of the choices, or type two dates.".to_string());
        }
        return Ok(format!("{PREVIEW_PATH}?preset={p}&kinds={kinds}"));
    }
    match (from, to) {
        (Some(a), Some(b)) if is_when(a) && is_when(b) => {
            Ok(format!("{PREVIEW_PATH}?from={a}&to={b}&kinds={kinds}"))
        }
        _ => Err("Type the dates like 2026-09-01.".to_string()),
    }
}

/// The body of "Forget these", checked: the two dates as the PC wrote
/// them, fact ids (whole numbers) and chat ids, at least one, at most 200.
pub(crate) fn forget_body(body: Option<serde_json::Value>) -> Result<serde_json::Value, String> {
    let body = body.unwrap_or_else(|| serde_json::json!({}));
    let obj = body
        .as_object()
        .ok_or_else(|| "send the list to forget".to_string())?;
    let when = |k: &str| {
        obj.get(k)
            .and_then(|v| v.as_str())
            .filter(|s| is_when(s))
            .map(str::to_string)
            .ok_or_else(|| "Type the dates like 2026-09-01.".to_string())
    };
    let (from, to) = (when("from")?, when("to")?);
    let facts: Vec<u64> = match obj.get("facts") {
        None | Some(serde_json::Value::Null) => Vec::new(),
        Some(serde_json::Value::Array(a)) => a
            .iter()
            .map(|v| v.as_u64().filter(|n| *n > 0))
            .collect::<Option<Vec<_>>>()
            .ok_or_else(|| "facts are whole-number ids".to_string())?,
        Some(_) => return Err("facts are whole-number ids".to_string()),
    };
    let chats: Vec<String> = match obj.get("chats") {
        None | Some(serde_json::Value::Null) => Vec::new(),
        Some(serde_json::Value::Array(a)) => a
            .iter()
            .map(|v| {
                v.as_str()
                    .filter(|s| commands::valid_conversation_id(s))
                    .map(str::to_string)
            })
            .collect::<Option<Vec<_>>>()
            .ok_or_else(|| "chats are conversation ids".to_string())?,
        Some(_) => return Err("chats are conversation ids".to_string()),
    };
    if facts.is_empty() && chats.is_empty() {
        return Err("Tick at least one thing to forget.".to_string());
    }
    if facts.len() + chats.len() > 200 {
        return Err("At most 200 at once. Choose fewer days.".to_string());
    }
    Ok(serde_json::json!({ "from": from, "to": to, "facts": facts, "chats": chats }))
}

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

/// A 404 that jarvis_forget_range itself sent carries `"ok": false`; a PC
/// without the routes at all does not.
fn own_404(body: &str) -> bool {
    parsed(body).and_then(|v| v.get("ok").and_then(|o| o.as_bool())) == Some(false)
}

/// [`forget_range_read`]'s reading: the PC's own body on a 2xx;
/// `{"available": false, "why": FORGET_RANGE_MISSING}` from a PC without
/// the routes; the PC's own sentence otherwise (a bad date, 400).
pub(crate) fn read_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body).ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 && !own_404(body) {
        return Ok(serde_json::json!({ "available": false, "why": FORGET_RANGE_MISSING }));
    }
    Err(commands::backend_refusal(status, body))
}

/// [`forget_range_write`]'s reading: the PC's own body on a 2xx (202: the
/// card is up) with the status as `http`; the PC's own sentence otherwise
/// (409: a card already waiting, the list changed, an Undo still open).
pub(crate) fn write_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        let mut v = parsed(body).ok_or_else(|| UNREADABLE.to_string())?;
        if let Some(o) = v.as_object_mut() {
            o.insert("http".into(), serde_json::json!(status));
        }
        return Ok(v);
    }
    if status == 404 && !own_404(body) {
        return Err(FORGET_RANGE_MISSING.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// The list with every fact's words and every chat's title taken out, for
/// while the private lists are hidden or Jarvis is locked. The days, the
/// counts and the summary (numbers and dates only) stay.
pub(crate) fn redact(mut answer: serde_json::Value) -> serde_json::Value {
    if let Some(obj) = answer.as_object_mut() {
        if obj.contains_key("facts") || obj.contains_key("chats") {
            for key in ["facts", "chats"] {
                obj.insert(key.into(), serde_json::json!([]));
            }
            obj.insert("hidden".into(), serde_json::json!(true));
        }
    }
    answer
}

fn stale(app: &AppHandle) -> bool {
    app.state::<crate::stream::StreamState>().link().stale
}

fn words_hidden(app: &AppHandle) -> bool {
    crate::lock::private_hidden(app) || crate::lock::app_locked(app)
}

/// The status, or the list for some days. A read.
#[tauri::command]
pub async fn forget_range_read(
    app: AppHandle,
    preview: Option<bool>,
    preset: Option<String>,
    from: Option<String>,
    to: Option<String>,
    kinds: Option<Vec<String>>,
) -> Result<serde_json::Value, String> {
    let path = read_path(
        preview.unwrap_or(false),
        preset.as_deref(),
        from.as_deref(),
        to.as_deref(),
        kinds.as_deref(),
    )?;
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{path}"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    let answer = read_answer(status, &text)?;
    Ok(if words_hidden(&app) {
        redact(answer)
    } else {
        answer
    })
}

/// "Forget these" (the PC raises ONE card) or "Undo" (no card). See the
/// module note for what is held and why.
#[tauri::command]
pub async fn forget_range_write(
    app: AppHandle,
    action: String,
    body: Option<serde_json::Value>,
) -> Result<serde_json::Value, String> {
    let (path, body) = match action.as_str() {
        "forget" => {
            let body = forget_body(body)?;
            if words_hidden(&app) {
                return Err(STILL_HIDDEN.to_string());
            }
            if stale(&app) {
                return Err(STALE.to_string());
            }
            (STATUS_PATH, body)
        }
        "undo" => (UNDO_PATH, serde_json::json!({})),
        other => return Err(format!("not a forget-a-time-frame action: {other}")),
    };
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}{path}"))
        .headers(commands::jarvis_headers(&app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    write_answer(status, &text)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The real answers, made by `tools/gen_forget_range_cases.py`.
    const CASES: &str = include_str!("../../../tests/fixtures/forget-range-cases.json");

    fn cases() -> serde_json::Value {
        serde_json::from_str(CASES).expect("forget-range-cases.json is JSON")
    }

    #[test]
    fn every_real_answer_reads_the_way_the_page_expects() {
        let doc = cases();
        let all = doc["cases"].as_object().expect("cases");
        assert!(all.len() >= 15);
        for (name, case) in all {
            let (Some(status), Some(body)) = (case["status"].as_u64(), case.get("body")) else {
                continue;
            };
            let status = status as u16;
            let text = body.to_string();
            if (200..300).contains(&status) {
                assert_eq!(&read_answer(status, &text).unwrap(), body, "{name}");
                assert_eq!(
                    write_answer(status, &text).unwrap()["http"],
                    status,
                    "{name}"
                );
            } else {
                let said = body["error"].as_str().unwrap();
                let e = write_answer(status, &text).expect_err(name);
                assert!(e.starts_with(&said[..1].to_uppercase()), "{name}: {e}");
            }
        }
        let waiting =
            write_answer(202, &doc["cases"]["forget_waiting"]["body"].to_string()).unwrap();
        assert_eq!(waiting["waiting"], true);
    }

    #[test]
    fn a_pc_without_it_says_so() {
        let doc = cases();
        let missing = doc["missing"]["body"].to_string();
        let got = read_answer(404, &missing).unwrap();
        assert_eq!(got["why"], FORGET_RANGE_MISSING);
        assert_eq!(doc["words"]["missing"], FORGET_RANGE_MISSING);
        assert_eq!(write_answer(404, "").unwrap_err(), FORGET_RANGE_MISSING);
    }

    #[test]
    fn only_a_choice_or_two_real_dates_reach_the_query() {
        assert_eq!(
            read_path(false, None, None, None, None).unwrap(),
            STATUS_PATH
        );
        assert_eq!(
            read_path(true, Some("last_week"), None, None, None).unwrap(),
            "/api/memory/forget_range/preview?preset=last_week&kinds=facts,chats"
        );
        let chats = vec!["chats".to_string()];
        assert_eq!(
            read_path(
                true,
                None,
                Some("2026-09-01"),
                Some("2026-09-28T11:59"),
                Some(&chats)
            )
            .unwrap(),
            "/api/memory/forget_range/preview?from=2026-09-01&to=2026-09-28T11:59&kinds=chats"
        );
        for bad in [
            "2026-9-1",
            "2026-09-01&x=1",
            "1 Sept",
            "2026-09-01T9:30",
            "",
        ] {
            assert!(
                read_path(true, None, Some(bad), Some("2026-09-02"), None).is_err(),
                "{bad}"
            );
        }
        assert!(read_path(true, Some("forever"), None, None, None).is_err());
        let emails = vec!["emails".to_string()];
        assert!(read_path(true, Some("today"), None, None, Some(&emails)).is_err());
        let doc = cases();
        let presets: Vec<&str> = doc["presets"]
            .as_array()
            .unwrap()
            .iter()
            .map(|p| p["id"].as_str().unwrap())
            .collect();
        assert_eq!(presets, PRESETS, "the PC's choices and this list differ");
    }

    #[test]
    fn forget_sends_only_checked_ids() {
        let ok = forget_body(Some(serde_json::json!({
            "from": "2026-09-01", "to": "2026-09-15", "facts": [3, 4],
            "chats": ["conv-trip-00001"], "extra": "dropped"
        })))
        .unwrap();
        assert_eq!(
            ok,
            serde_json::json!({ "from": "2026-09-01", "to": "2026-09-15",
                                "facts": [3, 4], "chats": ["conv-trip-00001"] })
        );
        for bad in [
            serde_json::json!({ "from": "2026-09-01", "to": "2026-09-15" }),
            serde_json::json!({ "from": "x", "to": "2026-09-15", "facts": [1] }),
            serde_json::json!({ "from": "2026-09-01", "to": "2026-09-15", "facts": ["1"] }),
            serde_json::json!({ "from": "2026-09-01", "to": "2026-09-15", "facts": [0] }),
            serde_json::json!({ "from": "2026-09-01", "to": "2026-09-15", "chats": ["../x"] }),
            serde_json::json!([1]),
        ] {
            assert!(forget_body(Some(bad.clone())).is_err(), "{bad}");
        }
        let many: Vec<u64> = (1..=201).collect();
        assert!(forget_body(Some(
            serde_json::json!({ "from": "2026-09-01", "to": "2026-09-15", "facts": many })
        ))
        .is_err());
    }

    #[test]
    fn hidden_lists_keep_the_days_and_counts_but_no_words() {
        let doc = cases();
        let hidden = redact(doc["cases"]["preview"]["body"].clone());
        assert_eq!(hidden["hidden"], true);
        assert_eq!(hidden["facts"], serde_json::json!([]));
        assert_eq!(hidden["counts"]["facts"], 2);
        assert_eq!(hidden["frame"]["said"], "1 to 15 September 2026");
        let s = hidden.to_string();
        assert!(!s.contains("Leeds") && !s.contains("Rome") && !s.contains("poem"));
        let status = doc["cases"]["status_undo"]["body"].clone();
        assert_eq!(
            redact(status.clone()),
            status,
            "the status carries no words"
        );
    }
}
