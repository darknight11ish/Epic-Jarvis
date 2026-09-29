//! "Chat with customer support for me" (the owner's decisions of 2026-09-28;
//! docs/CHATBOT-DRIVER-DESIGN.md "Customer-support chats";
//! `jarvis_support.py` through `jarvis_chatbot_routes.py`; JARVIS-API.md
//! section 65).
//!
//! Jarvis chats with a company's customer support for the owner, in the
//! owner's name, in a browser window on the PC. ONE card lists every detail
//! it may give; EVERY offer gets its own card. The Brain's Work tab is the
//! only window with these commands:
//!
//! * [`support_status`] - `GET /api/chatbot/status?support=`: the companies,
//!   the version, and the chat (the latest going, or the one named). A read.
//!   While the private lists are hidden the goal, the details, the
//!   transcript, the offer's words, the question and the summary are taken
//!   out here ([`hide_words`]).
//! * [`support_start`] - `POST /api/chatbot/support/start`: ONE approval card
//!   on the PC; nothing is sent before a yes. Held on a stale link.
//! * [`support_stop`] - never held: it only makes Jarvis do less.
//! * [`support_takeover`] - never held: Jarvis stops sending; the owner
//!   types in the window.
//! * [`support_answer`] - the owner's choice about a waiting offer OTHER
//!   than accepting (accepting is only ever the offer's own card): Decline
//!   and "Say something else" send words, so they are held on a stale link;
//!   Take over is not.
//! * [`support_export`] - "Export transcript": the PC's plain text, saved to
//!   a file the owner picks in the Windows "Save as" dialog. Held while the
//!   private lists are hidden (it is the whole chat, with the details).
//!
//! Resume is `chatbot_resume` (the task's own card, like a chatbot
//! conversation's). Stop everything (the hotkey) already stops a support
//! chat: the backend's `jarvis_support` registers with `jarvis_stop_all`.

use tauri::AppHandle;

use super::{require_link_live, READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

/// A PC whose backend has no support chats. The phone says the same
/// (`Support.MISSING`).
pub(crate) const SUPPORT_MISSING: &str =
    "Your PC's Jarvis cannot chat with customer support yet - run apply-patches.ps1 on the PC.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// The PC's own limits (`jarvis_support.py`); the PC checks them again.
pub(crate) const MAX_GOAL_CHARS: usize = 1000;
pub(crate) const MAX_DETAILS: usize = 12;
pub(crate) const MAX_DETAIL_NAME: usize = 40;
pub(crate) const MAX_DETAIL_VALUE: usize = 200;
pub(crate) const MAX_SAY_CHARS: usize = 1200;
/// The most either version allows (the full version's); the PC checks the
/// caps of the version that runs.
const MOST_MESSAGES: u32 = 40;
const MOST_MINUTES: u32 = 60;
const MOST_QUEUE_MINUTES: u32 = 120;

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

/// A support chat's id (`jarvis_support._new_id`): `sup_` and 12 hex.
pub(crate) fn valid_id(id: &str) -> bool {
    id.len() == 16
        && id.starts_with("sup_")
        && id[4..]
            .chars()
            .all(|c| c.is_ascii_digit() || ('a'..='f').contains(&c))
}

/// [`support_status`]'s reading: an older PC (no `companies`) is "missing".
pub(crate) fn status_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        let v = parsed(body).ok_or_else(|| UNREADABLE.to_string())?;
        if v.get("companies").is_some_and(|c| c.is_array()) {
            return Ok(v);
        }
        if v.get("chatbots").is_some() {
            return Ok(serde_json::json!({ "available": false, "why": SUPPORT_MISSING }));
        }
        return Err(UNREADABLE.to_string());
    }
    if status == 404 || status == 501 {
        return Ok(serde_json::json!({ "available": false, "why": SUPPORT_MISSING }));
    }
    Err(commands::backend_refusal(status, body))
}

/// A change's reading: the PC's own sentence, whether it went through or
/// was refused. A 404 WITH the route's own `{"ok": false, "error"}` is "no
/// such chat"; a 404 without it is an older PC.
pub(crate) fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body).ok_or_else(|| UNREADABLE.to_string());
    }
    let said = parsed(body).and_then(|v| {
        if v.get("ok").and_then(|o| o.as_bool()) == Some(false) {
            v.get("error").and_then(|e| e.as_str()).map(str::to_string)
        } else {
            None
        }
    });
    if let Some(error) = said.filter(|e| !e.trim().is_empty()) {
        if matches!(status, 400 | 404 | 409) {
            return Err(error);
        }
    }
    if status == 404 || status == 501 {
        return Err(SUPPORT_MISSING.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// One detail row as typed: a name and its exact value.
#[derive(serde::Deserialize, Clone, Debug, PartialEq)]
pub struct Detail {
    pub name: String,
    pub value: String,
}

fn limit(value: Option<u32>, most: u32, what: &str) -> Result<Option<u32>, String> {
    match value {
        Some(v) if v == 0 || v > most => Err(format!("{what}: 1 to {most}.")),
        other => Ok(other),
    }
}

/// The body for a start. The goal and every value go exactly as typed (only
/// the ends trimmed): the card shows them word for word. The PC refuses the
/// rows that can never be on a card (a password, a card number...).
#[allow(clippy::too_many_arguments)]
pub(crate) fn start_body(
    company: &str,
    address: Option<&str>,
    goal: &str,
    details: &[Detail],
    max_messages: Option<u32>,
    max_minutes: Option<u32>,
    max_queue_minutes: Option<u32>,
) -> Result<serde_json::Value, String> {
    let company = company.trim();
    if company.is_empty()
        || company.len() > 40
        || !company
            .chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
    {
        return Err("Choose a company.".to_string());
    }
    let goal = goal.trim();
    if goal.is_empty() {
        return Err("Say what Jarvis should get done.".to_string());
    }
    if goal.chars().count() > MAX_GOAL_CHARS {
        return Err(format!(
            "The goal is longer than {MAX_GOAL_CHARS} characters."
        ));
    }
    let mut rows = Vec::new();
    for d in details {
        let name = d.name.split_whitespace().collect::<Vec<_>>().join(" ");
        let value = d.value.trim().to_string();
        if name.is_empty() && value.is_empty() {
            continue;
        }
        if name.is_empty() {
            return Err("Every detail needs a name, like \"Order number\".".to_string());
        }
        if value.is_empty() {
            return Err(format!("The detail \"{name}\" has no value."));
        }
        if name.chars().count() > MAX_DETAIL_NAME || value.chars().count() > MAX_DETAIL_VALUE {
            return Err(format!("The detail \"{name}\" is too long."));
        }
        if value.contains('\n') {
            return Err(format!("The detail \"{name}\" has a line break in it."));
        }
        rows.push(serde_json::json!({ "name": name, "value": value }));
    }
    if rows.len() > MAX_DETAILS {
        return Err(format!("At most {MAX_DETAILS} details."));
    }
    let mut body = serde_json::json!({
        "company": company,
        "goal": goal,
        "details": rows,
    });
    if company == "other" {
        let a = address.unwrap_or("").trim();
        if !a.starts_with("https://") || a.len() > 500 {
            return Err("Type the company's help page, starting with https://".to_string());
        }
        body["address"] = serde_json::json!(a);
    }
    if let Some(m) = limit(max_messages, MOST_MESSAGES, "Most messages")? {
        body["max_messages"] = serde_json::json!(m);
    }
    if let Some(m) = limit(max_minutes, MOST_MINUTES, "Most minutes of chat")? {
        body["max_minutes"] = serde_json::json!(m);
    }
    if let Some(m) = limit(
        max_queue_minutes,
        MOST_QUEUE_MINUTES,
        "Most minutes in the queue",
    )? {
        body["max_queue_minutes"] = serde_json::json!(m);
    }
    Ok(body)
}

/// The body for an answer about the waiting offer: decline, say or takeover
/// - never "accept" (that is only ever the offer's own card).
pub(crate) fn answer_body(
    id: &str,
    offer: u32,
    choice: &str,
    text: Option<&str>,
) -> Result<serde_json::Value, String> {
    if !valid_id(id) {
        return Err("Say which support chat.".to_string());
    }
    let mut body = serde_json::json!({ "id": id, "offer": offer, "choice": choice });
    match choice {
        "decline" | "takeover" => {}
        "say" => {
            let t = text
                .unwrap_or("")
                .split_whitespace()
                .collect::<Vec<_>>()
                .join(" ");
            if t.is_empty() {
                return Err("Type what Jarvis should send.".to_string());
            }
            if t.chars().count() > MAX_SAY_CHARS {
                return Err(format!("At most {MAX_SAY_CHARS} characters."));
            }
            body["text"] = serde_json::json!(t);
        }
        _ => {
            return Err(
                "Choose Decline, Say something else or Take over - accepting is done on the \
                 approval card."
                    .to_string(),
            )
        }
    }
    Ok(body)
}

/// The status with the owner's words taken out - the goal, the details'
/// values, the transcript, the question, the offer's words and reply, the
/// summary, the reference and the end words - and `hidden` set. The
/// company, the counts, the state and the version stay.
pub(crate) fn hide_words(mut answer: serde_json::Value) -> serde_json::Value {
    if let Some(s) = answer.get_mut("support").and_then(|s| s.as_object_mut()) {
        s.insert("goal".into(), serde_json::json!(""));
        s.insert("details".into(), serde_json::json!([]));
        s.insert("transcript".into(), serde_json::json!([]));
        s.insert("question".into(), serde_json::json!(""));
        s.insert("summary".into(), serde_json::Value::Null);
        s.insert("reference".into(), serde_json::json!(""));
        s.insert("ended".into(), serde_json::json!(""));
        s.insert("paused".into(), serde_json::json!(""));
        if let Some(o) = s.get_mut("offer").and_then(|o| o.as_object_mut()) {
            o.insert("words".into(), serde_json::json!(""));
            o.insert("reply".into(), serde_json::json!(""));
            o.insert("said".into(), serde_json::json!(""));
        }
        s.insert("hidden".into(), serde_json::json!(true));
    }
    // The other features' parts of the same answer are hidden their own way.
    super::chatbot::hide_words(answer)
}

/// The companies, the version and one support chat (the one named, or the
/// latest going). A read.
#[tauri::command]
pub async fn support_status(
    app: AppHandle,
    id: Option<String>,
) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(&app);
    let id = id.filter(|i| valid_id(i)).unwrap_or_default();
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/chatbot/status"))
        .query(&[("support", id)])
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = status_answer(status, &body)?;
    Ok(if crate::lock::private_hidden(&app) {
        hide_words(answer)
    } else {
        answer
    })
}

/// Ask for a support chat: ONE approval card on the PC. Held on a stale link.
#[tauri::command]
#[allow(clippy::too_many_arguments)]
pub async fn support_start(
    app: AppHandle,
    company: String,
    address: Option<String>,
    goal: String,
    details: Vec<Detail>,
    max_messages: Option<u32>,
    max_minutes: Option<u32>,
    max_queue_minutes: Option<u32>,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let body = start_body(
        &company,
        address.as_deref(),
        &goal,
        &details,
        max_messages,
        max_minutes,
        max_queue_minutes,
    )?;
    post(&app, "/api/chatbot/support/start", body).await
}

/// Stop a support chat. Never held, never a card.
#[tauri::command]
pub async fn support_stop(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    if !valid_id(&id) {
        return Err("Say which support chat to stop.".to_string());
    }
    post(
        &app,
        "/api/chatbot/support/stop",
        serde_json::json!({ "id": id }),
    )
    .await
}

/// Take over: Jarvis stops sending. Never held, never a card.
#[tauri::command]
pub async fn support_takeover(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    if !valid_id(&id) {
        return Err("Say which support chat.".to_string());
    }
    post(
        &app,
        "/api/chatbot/support/takeover",
        serde_json::json!({ "id": id }),
    )
    .await
}

/// Decline, "Say something else" (both send words: held on a stale link) or
/// Take over (not held) about the waiting offer.
#[tauri::command]
pub async fn support_answer(
    app: AppHandle,
    id: String,
    offer: u32,
    choice: String,
    text: Option<String>,
) -> Result<serde_json::Value, String> {
    let body = answer_body(&id, offer, &choice, text.as_deref())?;
    if choice != "takeover" {
        require_link_live(&app)?;
    }
    post(&app, "/api/chatbot/support/answer", body).await
}

/// "Export transcript": the PC's plain text, saved where the owner picks.
/// Returns `{"saved": <path>}`, or `{"cancelled": true}`. The file is NOT
/// encrypted, and the button says so.
#[tauri::command]
pub async fn support_export(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    crate::lock::require_private_shown(&app)?;
    if !valid_id(&id) {
        return Err("Say which support chat.".to_string());
    }
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/chatbot/support/export"))
        .query(&[("id", id)])
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let got = change_answer(status, &body)?;
    let text = got
        .get("text")
        .and_then(|t| t.as_str())
        .ok_or_else(|| UNREADABLE.to_string())?
        .to_string();
    let name = export_name(got.get("filename").and_then(|f| f.as_str()).unwrap_or(""));
    let (tx, rx) = tokio::sync::oneshot::channel();
    // Its own thread: the dialog needs a single-threaded COM apartment.
    std::thread::spawn(move || {
        let _ = tx.send(super::save_dialog::pick_as(
            &name,
            &super::save_dialog::TEXT_FILE,
        ));
    });
    let picked = rx
        .await
        .map_err(|_| "the save dialog closed unexpectedly".to_string())??;
    let Some(path) = picked else {
        return Ok(serde_json::json!({ "cancelled": true }));
    };
    std::fs::write(&path, text).map_err(|e| format!("could not save {}: {e}", path.display()))?;
    Ok(serde_json::json!({ "saved": path.display().to_string() }))
}

/// The name the dialog suggests: the PC's, when it is a plain file name.
pub(crate) fn export_name(suggested: &str) -> String {
    let ok = !suggested.is_empty()
        && suggested.len() <= 80
        && suggested.ends_with(".txt")
        && suggested
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '.' || c == '_');
    if ok {
        suggested.to_string()
    } else {
        "jarvis-support-chat.txt".to_string()
    }
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

    fn row(n: &str, v: &str) -> Detail {
        Detail {
            name: n.into(),
            value: v.into(),
        }
    }

    #[test]
    fn ids_are_the_pcs_shape_only() {
        assert!(valid_id("sup_0123456789ab"));
        assert!(!valid_id("sup_0123456789AB"));
        assert!(!valid_id("chat_0123456789ab"));
        assert!(!valid_id("sup_../../etc/pa"));
    }

    #[test]
    fn an_older_pc_says_so() {
        let old = r#"{"routed": true, "chatbots": [], "tier": {}}"#;
        assert_eq!(status_answer(200, old).unwrap()["why"], SUPPORT_MISSING);
        assert_eq!(status_answer(404, "").unwrap()["available"], false);
        let new = r#"{"companies": [], "support_tier": {}, "support": null}"#;
        assert!(status_answer(200, new).unwrap()["companies"].is_array());
        assert!(status_answer(200, r#"{"ok": true}"#).is_err());
    }

    #[test]
    fn the_goal_and_values_go_as_typed_and_blank_rows_are_dropped() {
        let b = start_body(
            "groupon",
            None,
            "  Refund my voucher ",
            &[
                row("  Order   number ", " 4481902217 "),
                row("", ""),
                row("Email", "a@b.example"),
            ],
            Some(10),
            None,
            Some(60),
        )
        .unwrap();
        assert_eq!(b["goal"], "Refund my voucher");
        assert_eq!(
            b["details"],
            serde_json::json!([{"name": "Order number", "value": "4481902217"},
                               {"name": "Email", "value": "a@b.example"}])
        );
        assert_eq!(b["max_messages"], 10);
        assert_eq!(b["max_queue_minutes"], 60);
        assert!(b.get("address").is_none());
        assert!(start_body("groupon", None, " ", &[], None, None, None).is_err());
        assert!(start_body("../x", None, "g", &[], None, None, None).is_err());
        assert!(start_body("groupon", None, "g", &[row("", "x")], None, None, None).is_err());
        assert!(start_body("groupon", None, "g", &[row("x", "")], None, None, None).is_err());
        assert!(start_body("groupon", None, "g", &[], Some(41), None, None).is_err());
        let many = vec![row("a", "b"); 13];
        assert!(start_body("groupon", None, "g", &many, None, None, None).is_err());
        assert!(start_body(
            "other",
            Some("http://x.example"),
            "g",
            &[],
            None,
            None,
            None
        )
        .is_err());
        let o = start_body(
            "other",
            Some(" https://help.example.com "),
            "g",
            &[],
            None,
            None,
            None,
        )
        .unwrap();
        assert_eq!(o["address"], "https://help.example.com");
    }

    #[test]
    fn accepting_is_never_an_answer_here() {
        assert!(answer_body("sup_0123456789ab", 1, "accept", None).is_err());
        assert!(answer_body("sup_0123456789ab", 1, "say", Some("  ")).is_err());
        let b = answer_body(
            "sup_0123456789ab",
            2,
            "say",
            Some(" Is  there another option? "),
        )
        .unwrap();
        assert_eq!(b["text"], "Is there another option?");
        assert_eq!(b["offer"], 2);
        assert!(answer_body("sup_0123456789ab", 1, "decline", None).is_ok());
        assert!(answer_body("nope", 1, "decline", None).is_err());
    }

    #[test]
    fn the_owners_words_are_hidden_with_the_private_lists() {
        let out = hide_words(serde_json::json!({"session": null, "support": {
            "goal": "refund", "details": [{"name": "Email", "value": "a@b.example"}],
            "transcript": [{"who": "company", "text": "t"}], "question": "q",
            "offer": {"id": 1, "words": "w", "reply": "r"}, "summary": {"answer": "x"},
            "reference": "GRP1", "company_name": "Groupon", "messages_used": 3}}));
        let s = &out["support"];
        assert_eq!(s["goal"], "");
        assert_eq!(s["details"], serde_json::json!([]));
        assert_eq!(s["transcript"], serde_json::json!([]));
        assert_eq!(s["offer"]["words"], "");
        assert!(s["summary"].is_null());
        assert_eq!(s["hidden"], true);
        assert_eq!(s["company_name"], "Groupon");
        assert_eq!(s["messages_used"], 3);
    }

    #[test]
    fn the_export_name_is_a_plain_file_name() {
        assert_eq!(
            export_name("jarvis-support-groupon-2026-09-28.txt"),
            "jarvis-support-groupon-2026-09-28.txt"
        );
        assert_eq!(export_name("../evil.txt"), "jarvis-support-chat.txt");
        assert_eq!(export_name("x.exe"), "jarvis-support-chat.txt");
    }
}
