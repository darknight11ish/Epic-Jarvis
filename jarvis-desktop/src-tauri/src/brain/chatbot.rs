//! "Talk to a chatbot for me" (the owner's decisions of 2026-09-27 and
//! 2026-09-28; docs/CHATBOT-DRIVER-DESIGN.md; backend/chatbot-routes.patch,
//! `jarvis_chatbot_routes.py` over `jarvis_chatbot.py`; JARVIS-API.md
//! section 60).
//!
//! Jarvis asks an AI chatbot about something for the owner and writes its
//! own follow-ups on the PC, within limits approved on ONE card. The Brain's
//! Work tab is the only window with these commands:
//!
//! * [`chatbot_status`] - `GET /api/chatbot/status?id=`: the chatbots, which
//!   version runs, and the conversation with its transcript. A read. While
//!   the private lists are hidden the goal, the transcript and the summary
//!   are taken out here ([`hide_words`]), like a focus session's "on what".
//! * [`chatbot_start`] - `POST /api/chatbot/start`: raises ONE approval card
//!   on the PC; nothing is sent before a yes. Held on a stale link.
//! * [`chatbot_limits`] - `POST /api/chatbot/limits`: a NEW card. Held on a
//!   stale link.
//! * [`chatbot_stop`] - `POST /api/chatbot/stop`. Never held: it only makes
//!   Jarvis do less.
//! * [`chatbot_pause`] / [`chatbot_resume`] - the existing
//!   `/api/task/pause` and `/api/task/resume` (a conversation runs as a
//!   task). Pause is never held; Resume raises its own card and is held.
//!
//! * [`chatbot_compare_start`] - `POST /api/chatbot/compare/start` ("Ask
//!   several and compare", `jarvis_chatbot_compare.py`): two or more
//!   chatbots, ONE approval card listing every one. Held on a stale link.
//! * [`chatbot_compare_stop`] - `POST /api/chatbot/compare/stop`: the whole
//!   comparison. Never held.
//!
//! Stop everything (the hotkey) already stops a conversation and a
//! comparison: the backend's `jarvis_chatbot` and `jarvis_chatbot_compare`
//! register with `jarvis_stop_all`.

use tauri::AppHandle;

use super::{require_link_live, READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

/// A PC whose backend has no chatbot routes. The phone says the same
/// (`Chatbot.MISSING`).
pub(crate) const CHATBOT_MISSING: &str =
    "Your PC's Jarvis cannot talk to chatbots yet - run apply-patches.ps1 on the PC.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// The longest goal the PC takes (`jarvis_chatbot.MAX_GOAL_CHARS`).
pub(crate) const MAX_GOAL_CHARS: usize = 1000;
/// Never-send words: how many, and how long each (`MAX_NEVER_SEND`, `..._CHARS`).
pub(crate) const MAX_NEVER: usize = 50;
pub(crate) const MAX_NEVER_CHARS: usize = 60;
/// The most messages and minutes either version allows (the full version's).
/// The PC checks the real caps for the version that runs.
const MOST_MESSAGES: u32 = 20;
const MOST_MINUTES: u32 = 30;

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

fn valid_id(id: &str) -> bool {
    id.len() == 17
        && id.starts_with("chat_")
        && id[5..]
            .chars()
            .all(|c| c.is_ascii_digit() || ('a'..='f').contains(&c))
}

/// A comparison's id (`jarvis_chatbot_compare._new_id`): `cmp_` and 12 hex.
fn valid_compare_id(id: &str) -> bool {
    id.len() == 16
        && id.starts_with("cmp_")
        && id[4..]
            .chars()
            .all(|c| c.is_ascii_digit() || ('a'..='f').contains(&c))
}

/// The most chatbots one comparison may name (the two-card version's; the PC
/// checks the real cap for the version that runs).
const MOST_COMPARED: usize = 4;

/// [`chatbot_status`]'s reading of the answer.
pub(crate) fn status_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("chatbots").is_some_and(|c| c.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 || status == 501 {
        return Ok(serde_json::json!({ "available": false, "why": CHATBOT_MISSING }));
    }
    Err(commands::backend_refusal(status, body))
}

/// A change's reading: the PC's own sentence, whether it went through or
/// was refused. A 404 WITH the route's own `{"ok": false, "error"}` is "no
/// such conversation"; a 404 without it is an older PC.
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
        return Err(CHATBOT_MISSING.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// The never-send words, tidied: spaces collapsed, blanks and repeats
/// dropped. Too many, or one too long, is refused here with the PC's limits.
pub(crate) fn clean_never(words: &[String]) -> Result<Vec<String>, String> {
    let mut out: Vec<String> = Vec::new();
    for raw in words {
        let w = raw.split_whitespace().collect::<Vec<_>>().join(" ");
        if w.is_empty() {
            continue;
        }
        if w.chars().count() > MAX_NEVER_CHARS {
            return Err(format!(
                "A never-send word is longer than {MAX_NEVER_CHARS} characters."
            ));
        }
        if !out.iter().any(|o| o.to_lowercase() == w.to_lowercase()) {
            out.push(w);
        }
    }
    if out.len() > MAX_NEVER {
        return Err(format!("At most {MAX_NEVER} never-send words."));
    }
    Ok(out)
}

fn limit(value: Option<u32>, most: u32, what: &str) -> Result<Option<u32>, String> {
    match value {
        Some(v) if v == 0 || v > most => Err(format!("Most {what}: 1 to {most}.")),
        other => Ok(other),
    }
}

/// The body for a start. The goal goes exactly as typed (only the ends
/// trimmed): the card shows it word for word, and it is what is sent.
pub(crate) fn start_body(
    chatbot: &str,
    goal: &str,
    max_messages: Option<u32>,
    max_minutes: Option<u32>,
    never_send: &[String],
) -> Result<serde_json::Value, String> {
    let chatbot = chatbot.trim();
    if chatbot.is_empty()
        || chatbot.len() > 40
        || !chatbot
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_')
    {
        return Err("Choose a chatbot.".to_string());
    }
    let goal = goal.trim();
    if goal.is_empty() {
        return Err("Say what Jarvis should find out.".to_string());
    }
    if goal.chars().count() > MAX_GOAL_CHARS {
        return Err(format!(
            "The goal is longer than {MAX_GOAL_CHARS} characters."
        ));
    }
    let mut body = serde_json::json!({
        "chatbot": chatbot,
        "goal": goal,
        "never_send": clean_never(never_send)?,
    });
    if let Some(m) = limit(max_messages, MOST_MESSAGES, "messages")? {
        body["max_messages"] = serde_json::json!(m);
    }
    if let Some(m) = limit(max_minutes, MOST_MINUTES, "minutes")? {
        body["max_minutes"] = serde_json::json!(m);
    }
    Ok(body)
}

/// The body for "Ask several and compare": the same goal and limits as a
/// single conversation, and the chatbots as a list of ids, no repeats.
pub(crate) fn compare_body(
    chatbots: &[String],
    goal: &str,
    max_messages: Option<u32>,
    max_minutes: Option<u32>,
    never_send: &[String],
) -> Result<serde_json::Value, String> {
    let mut ids: Vec<String> = Vec::new();
    for raw in chatbots {
        let id = raw.trim();
        if id.is_empty()
            || id.len() > 40
            || !id.chars().all(|c| c.is_ascii_alphanumeric() || c == '_')
        {
            return Err("Choose the chatbots to ask.".to_string());
        }
        if !ids.iter().any(|x| x == id) {
            ids.push(id.to_string());
        }
    }
    if ids.len() < 2 {
        return Err("Pick at least 2 chatbots to compare.".to_string());
    }
    if ids.len() > MOST_COMPARED {
        return Err(format!(
            "Pick at most {MOST_COMPARED} chatbots in this version."
        ));
    }
    let mut body = start_body(&ids[0], goal, max_messages, max_minutes, never_send)?;
    if let Some(o) = body.as_object_mut() {
        o.remove("chatbot");
        o.insert("chatbots".into(), serde_json::json!(ids));
    }
    Ok(body)
}

/// The body for a limits change: only what was given.
pub(crate) fn limits_body(
    id: &str,
    max_messages: Option<u32>,
    max_minutes: Option<u32>,
    never_send: Option<&[String]>,
) -> Result<serde_json::Value, String> {
    if !valid_id(id) {
        return Err("Say which conversation's limits to change.".to_string());
    }
    let mut body = serde_json::json!({ "id": id });
    if let Some(m) = limit(max_messages, MOST_MESSAGES, "messages")? {
        body["max_messages"] = serde_json::json!(m);
    }
    if let Some(m) = limit(max_minutes, MOST_MINUTES, "minutes")? {
        body["max_minutes"] = serde_json::json!(m);
    }
    if let Some(words) = never_send {
        body["never_send"] = serde_json::json!(clean_never(words)?);
    }
    Ok(body)
}

/// The status with the owner's words taken out - the goal, the never-send
/// words, the transcript (its first message IS the goal), the summary, the
/// chatbot's question and the end words (a "goal met" reason can repeat the
/// conversation) - and `hidden` set. Counts, the state and the version stay.
pub(crate) fn hide_words(mut answer: serde_json::Value) -> serde_json::Value {
    if let Some(s) = answer.get_mut("session").and_then(|s| s.as_object_mut()) {
        hide_session(s);
    }
    // A comparison: its goal, summary and end words, and every conversation
    // in it, the same way. Its counts, state and chatbots' names stay.
    if let Some(c) = answer.get_mut("compare").and_then(|c| c.as_object_mut()) {
        c.insert("goal".into(), serde_json::json!(""));
        c.insert("never_send".into(), serde_json::json!([]));
        c.insert("summary".into(), serde_json::Value::Null);
        c.insert("ended".into(), serde_json::json!(""));
        c.insert("hidden".into(), serde_json::json!(true));
        if let Some(members) = c.get_mut("members").and_then(|m| m.as_array_mut()) {
            for m in members.iter_mut().filter_map(|m| m.as_object_mut()) {
                hide_session(m);
            }
        }
    }
    answer
}

fn hide_session(s: &mut serde_json::Map<String, serde_json::Value>) {
    s.insert("goal".into(), serde_json::json!(""));
    s.insert("never_send".into(), serde_json::json!([]));
    s.insert("transcript".into(), serde_json::json!([]));
    s.insert("summary".into(), serde_json::Value::Null);
    s.insert("question".into(), serde_json::json!(""));
    s.insert("ended".into(), serde_json::json!(""));
    s.insert("hidden".into(), serde_json::json!(true));
}

/// The chatbots, the version, one conversation (the one named, or the latest
/// one still going) and one comparison (likewise). A read.
#[tauri::command]
pub async fn chatbot_status(
    app: AppHandle,
    id: Option<String>,
    compare: Option<String>,
) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(&app);
    let id = id.filter(|i| valid_id(i)).unwrap_or_default();
    let compare = compare.filter(|c| valid_compare_id(c)).unwrap_or_default();
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/chatbot/status"))
        .query(&[("id", id), ("compare", compare)])
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

/// Ask for a conversation: ONE approval card on the PC. Held on a stale link.
#[tauri::command]
pub async fn chatbot_start(
    app: AppHandle,
    chatbot: String,
    goal: String,
    max_messages: Option<u32>,
    max_minutes: Option<u32>,
    never_send: Vec<String>,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let body = start_body(&chatbot, &goal, max_messages, max_minutes, &never_send)?;
    post(&app, "/api/chatbot/start", body).await
}

/// New limits for a running or paused conversation: a NEW card. Held on a
/// stale link.
#[tauri::command]
pub async fn chatbot_limits(
    app: AppHandle,
    id: String,
    max_messages: Option<u32>,
    max_minutes: Option<u32>,
    never_send: Option<Vec<String>>,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let body = limits_body(&id, max_messages, max_minutes, never_send.as_deref())?;
    post(&app, "/api/chatbot/limits", body).await
}

/// Stop one conversation. Never held, never a card.
#[tauri::command]
pub async fn chatbot_stop(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    if !valid_id(&id) {
        return Err("Say which conversation to stop.".to_string());
    }
    post(&app, "/api/chatbot/stop", serde_json::json!({ "id": id })).await
}

/// Pause the running conversation (it runs as a task). Never held.
#[tauri::command]
pub async fn chatbot_pause(app: AppHandle) -> Result<serde_json::Value, String> {
    post(&app, "/api/task/pause", serde_json::json!({})).await
}

/// Resume a paused one: the PC raises its own card first. Held on a stale
/// link, like the widget's Resume.
#[tauri::command]
pub async fn chatbot_resume(app: AppHandle) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    post(&app, "/api/task/resume", serde_json::json!({})).await
}

/// "Ask several and compare": ONE approval card on the PC listing every
/// chatbot; nothing is sent before a yes. Held on a stale link.
#[tauri::command]
pub async fn chatbot_compare_start(
    app: AppHandle,
    chatbots: Vec<String>,
    goal: String,
    max_messages: Option<u32>,
    max_minutes: Option<u32>,
    never_send: Vec<String>,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let body = compare_body(&chatbots, &goal, max_messages, max_minutes, &never_send)?;
    post(&app, "/api/chatbot/compare/start", body).await
}

/// Stop the whole comparison. Never held, never a card.
#[tauri::command]
pub async fn chatbot_compare_stop(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    if !valid_compare_id(&id) {
        return Err("Say which comparison to stop.".to_string());
    }
    post(
        &app,
        "/api/chatbot/compare/stop",
        serde_json::json!({ "id": id }),
    )
    .await
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
    fn ids_are_the_pcs_shape_only() {
        assert!(valid_id("chat_0123456789ab"));
        assert!(!valid_id("chat_0123456789AB"));
        assert!(!valid_id("chat_../../etc/pa"));
        assert!(!valid_id(""));
    }

    #[test]
    fn the_status_is_passed_on_and_an_older_backend_says_so() {
        let body = r#"{"routed": true, "chatbots": [], "tier": {}, "session": null}"#;
        assert_eq!(status_answer(200, body).unwrap()["routed"], true);
        for old in [404, 501] {
            let a = status_answer(old, "").unwrap();
            assert_eq!(a["available"], false);
            assert_eq!(a["why"], CHATBOT_MISSING);
        }
        assert!(status_answer(200, r#"{"ok": true}"#).is_err());
    }

    #[test]
    fn a_refusal_is_the_pcs_own_sentence() {
        let e = change_answer(
            400,
            r#"{"ok": false, "error": "Gemini through its website is not built yet."}"#,
        );
        assert_eq!(
            e.unwrap_err(),
            "Gemini through its website is not built yet."
        );
        let e = change_answer(404, r#"{"ok": false, "error": "No such conversation."}"#);
        assert_eq!(e.unwrap_err(), "No such conversation.");
        assert_eq!(change_answer(404, "").unwrap_err(), CHATBOT_MISSING);
        assert_eq!(
            change_answer(202, r#"{"ok": true, "asking": true}"#).unwrap()["asking"],
            true
        );
    }

    #[test]
    fn the_goal_goes_as_typed_and_the_limits_are_checked() {
        let b = start_body(
            "gemini_web",
            "  Find out  about ferns \n",
            Some(5),
            None,
            &[
                "  Project   Nimbus ".into(),
                "project nimbus".into(),
                "".into(),
            ],
        )
        .unwrap();
        assert_eq!(b["goal"], "Find out  about ferns");
        assert_eq!(b["never_send"], serde_json::json!(["Project Nimbus"]));
        assert_eq!(b["max_messages"], 5);
        assert!(b.get("max_minutes").is_none());
        assert!(start_body("gemini_web", "   ", None, None, &[]).is_err());
        assert!(start_body("../x", "goal", None, None, &[]).is_err());
        assert!(start_body("gemini_web", "goal", Some(0), None, &[]).is_err());
        assert!(start_body("gemini_web", "goal", None, Some(31), &[]).is_err());
        assert!(start_body("gemini_web", &"x".repeat(1001), None, None, &[]).is_err());
        assert!(start_body("gemini_web", "goal", None, None, &["y".repeat(61)]).is_err());
    }

    #[test]
    fn a_comparison_names_two_to_four_chatbots_and_the_goal_as_typed() {
        let ids = |v: &[&str]| v.iter().map(|s| s.to_string()).collect::<Vec<_>>();
        let b = compare_body(
            &ids(&["gemini_web", "chatgpt_web", "gemini_web"]),
            "  Ferns ",
            Some(3),
            None,
            &["Nimbus".into()],
        )
        .unwrap();
        assert_eq!(
            b["chatbots"],
            serde_json::json!(["gemini_web", "chatgpt_web"])
        );
        assert!(b.get("chatbot").is_none());
        assert_eq!(b["goal"], "Ferns");
        assert_eq!(b["max_messages"], 3);
        assert_eq!(b["never_send"], serde_json::json!(["Nimbus"]));
        assert_eq!(
            compare_body(&ids(&["gemini_web"]), "g", None, None, &[]).unwrap_err(),
            "Pick at least 2 chatbots to compare."
        );
        assert!(compare_body(&ids(&["a", "b", "c", "d", "e"]), "g", None, None, &[]).is_err());
        assert!(compare_body(&ids(&["a", "../b"]), "g", None, None, &[]).is_err());
        assert!(compare_body(&ids(&["a", "b"]), "  ", None, None, &[]).is_err());
        assert!(valid_compare_id("cmp_0123456789ab"));
        assert!(!valid_compare_id("chat_0123456789ab"));
        assert!(!valid_compare_id("cmp_../../etc/p"));
    }

    #[test]
    fn a_comparisons_words_are_hidden_too() {
        let out = hide_words(serde_json::json!({"session": null, "compare": {
            "goal": "the tax return", "summary": {"answer": "x"}, "ended": "e",
            "never_send": ["a"], "messages_used": 3, "members": [
                {"goal": "the tax return", "transcript": [{"who": "chatbot", "text": "t"}],
                 "question": "q", "name": "Gemini"}]}}));
        let c = &out["compare"];
        assert_eq!(c["goal"], "");
        assert!(c["summary"].is_null());
        assert_eq!(c["hidden"], true);
        assert_eq!(c["messages_used"], 3);
        assert_eq!(c["members"][0]["goal"], "");
        assert_eq!(c["members"][0]["transcript"], serde_json::json!([]));
        assert_eq!(c["members"][0]["question"], "");
        assert_eq!(c["members"][0]["name"], "Gemini");
    }

    #[test]
    fn a_limits_change_carries_only_what_changed() {
        let b = limits_body("chat_0123456789ab", Some(6), None, None).unwrap();
        assert_eq!(
            b,
            serde_json::json!({"id": "chat_0123456789ab", "max_messages": 6})
        );
        let words = vec!["Nimbus".to_string()];
        let b = limits_body("chat_0123456789ab", None, None, Some(&words)).unwrap();
        assert_eq!(b["never_send"], serde_json::json!(["Nimbus"]));
        assert!(limits_body("nope", Some(6), None, None).is_err());
    }

    #[test]
    fn the_owners_words_are_hidden_with_the_private_lists() {
        let out = hide_words(serde_json::json!({"session": {
            "goal": "the tax return", "transcript": [{"who": "jarvis", "text": "the tax return"}],
            "summary": {"answer": "x"}, "question": "q", "never_send": ["a"],
            "ended": "It stopped because the goal looked met: tax", "messages_used": 2}}));
        let s = &out["session"];
        assert_eq!(s["goal"], "");
        assert_eq!(s["transcript"], serde_json::json!([]));
        assert!(s["summary"].is_null());
        assert_eq!(s["ended"], "");
        assert_eq!(s["hidden"], true);
        assert_eq!(s["messages_used"], 2);
        assert!(hide_words(serde_json::json!({"session": null}))["session"].is_null());
    }
}
