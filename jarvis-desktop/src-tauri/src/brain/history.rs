//! Chat history on the PC - the Brain's History tab (JARVIS-API.md section
//! 18, "Chat history").
//!
//! The PC keeps each conversation, encrypted, when "Keep chat history on
//! this PC" is on (the default). This window lists them, opens one
//! read-only, searches what was said, deletes ONE at a time, and changes the
//! two settings. Five commands, each its own power, like the rest of
//! brain.rs:
//!
//! * [`brain_history_list`] - `GET /api/history`, a page at a time.
//! * [`brain_history_open`] - `GET /api/history/conversation?id=`.
//! * [`brain_history_search`] - `GET /api/history/search?q=` (section 71):
//!   the conversations whose words match, each with a snippet. A read,
//!   refused while the private lists are hidden, like opening one.
//! * [`brain_history_delete`] - `POST /api/history/delete`, one id. There is
//!   no "delete all" here or on the server: irreversible bulk actions stay
//!   off the API.
//! * [`brain_history_settings`] - `POST /api/history/settings`, ONE field
//!   per request. Turning history ON only raises an approval card (tier
//!   `ask`), and is held while the event stream is stale (rule 4), exactly
//!   like the learning switch ([`super::brain_memory_learning`]). OFF is
//!   never held: it only narrows what Jarvis does.
//! * [`brain_continue_chat`] - "Continue this chat" (the owner's decision,
//!   2026-09-28, "Chats, after the chat audit"): brings up the Jarvis bar
//!   and tells it which conversation to carry on. It sends no words: the
//!   bar reads the conversation itself with [`chat_continue_open`], the
//!   quickbar's one read of History - a conversation it may carry on, and
//!   nothing else.
//!
//! The list takes a `kind` (chat, live, support, chatbot, compare): "Live
//! only" and the other History filters (the chat audit, 2026-09-28).
//!
//! "Windows Hello for memory lists and chat history" (lock.rs) covers this list too: while
//! the Brain's private lists are hidden, the list comes back with its
//! conversations taken out (how many there were is kept), and a transcript
//! is not opened at all. Here, in Rust, so a page script cannot read round
//! it.
//!
//! The answer-reading functions are plain functions of (status, body) so
//! their tests run without a Tauri app or a network.

use tauri::AppHandle;

use super::{require_link_live, READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

/// What a backend without chat history (without `chat-history.patch`) is
/// told to do about it. The page shows this sentence as it is.
pub(crate) const HISTORY_UPDATE: &str = "This PC's Jarvis does not keep chat history yet. \
     Update the backend by running apply-patches.ps1, then open this again.";

/// The only "Delete conversations older than" choices the PC takes: never
/// (0, the default), 30 days, 90 days, a year.
pub(crate) const KEEP_DAYS: [u32; 4] = [0, 30, 90, 365];

/// What a transcript open is refused with while the private lists are
/// hidden.
pub(crate) const HISTORY_STILL_HIDDEN: &str = "Your chat history is hidden. Press Show on \
     the Brain's History tab and confirm it is you with Windows Hello first.";

/// The kinds of conversation History keeps (`jarvis_chat_log.KINDS`) - the
/// only `kind` a list may be narrowed to. Anything else is not sent.
pub(crate) const KINDS: [&str; 5] = ["chat", "live", "support", "chatbot", "compare"];

/// Chat tags (docs/CHAT-TAGS-DESIGN.md section 10, the frozen contract): a
/// tag is `{id, name, colour 0-7, icon, order}`, one per chat, at most 12,
/// names 1-24 characters (the PC holds the limit of 12). The owner's tag
/// names are their own words, so every tag command below asks [`crate::lock::private_hidden`] first.
pub(crate) const TAG_NAME_MAX: usize = 24;
pub(crate) const TAG_COLOURS: i64 = 8;
/// The shared icon list; each app draws them with its own icons.
pub(crate) const TAG_ICONS: [&str; 10] = [
    "briefcase",
    "book",
    "home",
    "folder",
    "lightbulb",
    "star",
    "flag",
    "wrench",
    "leaf",
    "music",
];
/// The `error` codes the PC's tag routes answer with. The page maps each to
/// one plain sentence; anything else is not passed on as a code.
pub(crate) const TAG_ERROR_CODES: [&str; 8] = [
    "bad_name",
    "name_taken",
    "too_many_tags",
    "bad_colour",
    "bad_icon",
    "tag_not_found",
    "not_found",
    "bad_request",
];

/// What a backend without chat tags is told to do about it.
pub(crate) const TAGS_UPDATE: &str = "This PC's Jarvis cannot sort chats under tags yet. \
     Update the backend by running apply-patches.ps1, then open this again.";

/// What a tag read or edit is refused with while the private lists are
/// hidden: tag names are the owner's words, like titles.
pub(crate) const TAGS_STILL_HIDDEN: &str = "Your chat history is hidden, and so are your tag \
     names. Press Show on the Brain's History tab and confirm it is you with Windows Hello first.";

/// The kinds "Continue this chat" may carry on (`jarvis_chat_log.CONTINUABLE`).
pub(crate) const CONTINUABLE: [&str; 2] = ["chat", "live"];

/// What the quickbar is told when it asks to carry on a chat it may not:
/// a support record, a chatbot conversation or a comparison. The Brain
/// shows the PC's own reason (`continue_why`) before it ever gets here.
pub(crate) const NOT_CONTINUABLE: &str = "That conversation can't be continued: it is a \
     record of a chat with someone other than Jarvis.";

/// The event the Jarvis bar hears "Continue this chat" by: the id alone.
pub(crate) const CONTINUE_EVENT: &str = "continue-chat";

/// A page of the list: 30 unless asked, never more than the server's 100.
const DEFAULT_LIMIT: u32 = 30;
const MAX_LIMIT: u32 = 100;

/// "Search what was said" (JARVIS-API.md section 71): the PC's own limits
/// (`jarvis_chat_log.SEARCH_MAX_CHARS`, `SEARCH_DEFAULT`, `SEARCH_MAX`).
/// Nothing longer is sent.
const SEARCH_MAX_CHARS: usize = 100;
const SEARCH_DEFAULT: u32 = 20;
const SEARCH_MAX: u32 = 50;

/// What a PC whose backend cannot search the words yet (no
/// `brain-reads.patch`) is told. The page then searches titles only, and
/// says so with this sentence. The phone says the same (`ChatLog.SEARCH_OLD`).
pub(crate) const SEARCH_UPDATE: &str = "This PC's Jarvis can only search titles. To search \
     what was said, update it by running apply-patches.ps1 on the PC.";

/// What a search is refused with while the private lists are hidden.
pub(crate) const SEARCH_STILL_HIDDEN: &str = "Your chat history is hidden. Press Show on \
     the Brain's History tab and confirm it is you with Windows Hello first.";

/// `GET /api/history/search`'s path for these words, or why not. The words
/// are tidied (runs of spaces become one) and every byte that is not a
/// plain letter, digit or `-._~` is percent-encoded, so nothing the owner
/// types can start a second parameter.
pub(crate) fn search_path(
    query: &str,
    limit: Option<u32>,
    kind: Option<&str>,
) -> Result<String, String> {
    let words = query.split_whitespace().collect::<Vec<_>>().join(" ");
    if words.chars().count() < 2 {
        return Err("Type at least two letters to search what was said.".to_string());
    }
    if words.chars().count() > SEARCH_MAX_CHARS {
        return Err(format!(
            "That search is too long. Use up to {SEARCH_MAX_CHARS} characters."
        ));
    }
    let limit = limit.unwrap_or(SEARCH_DEFAULT).clamp(1, SEARCH_MAX);
    let mut path = format!(
        "/api/history/search?q={}&limit={limit}",
        commands::encode_path_segment(&words)
    );
    // "Live only" and a typed search combine (the second chat audit,
    // 2026-09-28, finding 8): the same kinds the list may be narrowed to.
    match kind.filter(|k| !k.is_empty()) {
        None => {}
        Some(k) if KINDS.contains(&k) => path.push_str(&format!("&kind={k}")),
        Some(k) => return Err(format!("{k:?} is not a kind of conversation History keeps")),
    }
    Ok(path)
}

/// [`brain_history_search`]'s reading of the answer.
///
/// * 2xx with `query_ok` and a `conversations` list - passed on as it is.
/// * 404 or 501 - `{"available": false, "why": SEARCH_UPDATE}`: a backend
///   without the search, which the page answers by searching titles.
/// * anything else - the backend's own sentence, or a plain line.
pub(crate) fn search_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| {
                v.get("query_ok").is_some_and(|q| q.is_boolean())
                    && v.get("conversations").is_some_and(|c| c.is_array())
            })
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 || status == 501 {
        return Ok(serde_json::json!({ "available": false, "why": SEARCH_UPDATE }));
    }
    Err(commands::backend_refusal(status, body))
}

/// `GET /api/history`'s path for one page. `before` is the `updated` of the
/// oldest conversation already shown; it is written as the plain number the
/// page was given (Rust never writes an `f64` in exponent form), so paging
/// neither repeats nor skips one.
#[cfg(test)]
pub(crate) fn list_path(
    limit: Option<u32>,
    before: Option<f64>,
    kind: Option<&str>,
) -> Result<String, String> {
    list_path_tagged(limit, before, kind, None)
}

/// A tag filter for the list: `none` (untagged) or a whole tag id. Anything
/// else is not sent, so nothing typed can start a second parameter.
pub(crate) fn tag_filter(tag: &str) -> Result<String, String> {
    if tag == "none" {
        return Ok("none".to_string());
    }
    match tag.parse::<u32>() {
        Ok(n) if n > 0 && tag == n.to_string() => Ok(n.to_string()),
        _ => Err(format!("{tag:?} is not a tag this PC keeps")),
    }
}

/// [`list_path`] narrowed to one tag (`tag=<id>` or `tag=none`).
pub(crate) fn list_path_tagged(
    limit: Option<u32>,
    before: Option<f64>,
    kind: Option<&str>,
    tag: Option<&str>,
) -> Result<String, String> {
    let limit = limit.unwrap_or(DEFAULT_LIMIT).clamp(1, MAX_LIMIT);
    let mut path = format!("/api/history?limit={limit}");
    if let Some(b) = before {
        if !b.is_finite() || b <= 0.0 {
            return Err(format!("{b} is not a moment in time"));
        }
        path.push_str(&format!("&before={b}"));
    }
    match kind.filter(|k| !k.is_empty()) {
        None => {}
        Some(k) if KINDS.contains(&k) => path.push_str(&format!("&kind={k}")),
        Some(k) => return Err(format!("{k:?} is not a kind of conversation History keeps")),
    }
    if let Some(t) = tag.filter(|t| !t.is_empty()) {
        path.push_str(&format!("&tag={}", tag_filter(t)?));
    }
    Ok(path)
}

/// [`chat_continue_open`]'s reading: the conversation, only when it is a
/// kind the bar may carry on. An older PC that sends no `kind` is an
/// ordinary chat (every conversation it kept was one, or a support record,
/// which it cannot tell apart - so it is let through only when no turn is
/// a support or chatbot row).
pub(crate) fn continue_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    let conv = conversation_answer(status, body)?;
    let kind = conv.get("kind").and_then(|k| k.as_str()).unwrap_or("chat");
    let others = conv
        .get("turns")
        .and_then(|t| t.as_array())
        .is_some_and(|turns| {
            turns.iter().any(|t| {
                matches!(
                    t.get("role").and_then(|r| r.as_str()),
                    Some("support") | Some("chatbot")
                )
            })
        });
    if !CONTINUABLE.contains(&kind) || others {
        return Err(NOT_CONTINUABLE.to_string());
    }
    // The PC's own "no" (a chat titled "A difficult moment" is kept but not
    // carried on - the second chat audit, 2026-09-28): its own plain reason.
    if conv.get("continuable").and_then(|c| c.as_bool()) == Some(false) {
        let why = conv
            .get("continue_why")
            .and_then(|w| w.as_str())
            .filter(|w| !w.trim().is_empty())
            .unwrap_or(NOT_CONTINUABLE);
        return Err(why.to_string());
    }
    Ok(conv)
}

/// The id, checked before it goes into a URL or a body: 8-64 characters of
/// `[A-Za-z0-9_-]`, what the PC makes and accepts. Nothing else can reach
/// the query string.
fn checked_id(id: &str) -> Result<&str, String> {
    if commands::valid_conversation_id(id) {
        Ok(id)
    } else {
        Err("That is not a conversation this PC keeps.".to_string())
    }
}

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// [`brain_history_list`]'s reading of the answer.
///
/// * 2xx with `enabled` and a `conversations` list - passed on as it is.
/// * 404 - `{"available": false, "why": HISTORY_UPDATE}`: an older backend,
///   which the page says plainly rather than as an error.
/// * anything else - the backend's own sentence, or a plain line.
pub(crate) fn list_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| {
                v.get("enabled").is_some_and(|e| e.is_boolean())
                    && v.get("conversations").is_some_and(|c| c.is_array())
            })
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 {
        return Ok(serde_json::json!({ "available": false, "why": HISTORY_UPDATE }));
    }
    Err(commands::backend_refusal(status, body))
}

/// [`brain_history_open`]'s reading: the transcript, or why not. A 404 is
/// "no such conversation" - it was deleted (here, on the phone, or by the
/// keep setting) after the list was read.
pub(crate) fn conversation_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("turns").is_some_and(|t| t.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 {
        return Err(
            "That conversation is no longer kept on this PC. It was deleted, \
                    or it was older than the keep setting."
                .to_string(),
        );
    }
    Err(commands::backend_refusal(status, body))
}

/// [`brain_history_delete`]'s reading. A 404 means it is already gone -
/// which is what was asked for - so it is `{"ok": true, "gone": true}`, and
/// the page says it was already deleted rather than that deleting failed.
pub(crate) fn delete_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return Ok(parsed(body).unwrap_or_else(|| serde_json::json!({ "ok": true })));
    }
    if status == 404 {
        return Ok(serde_json::json!({ "ok": true, "gone": true }));
    }
    Err(commands::backend_refusal(status, body))
}

/// The body for `POST /api/history/settings`: exactly ONE of the two, as
/// the server takes them (anything else is a 400 there). `keep_days` only
/// from [`KEEP_DAYS`].
pub(crate) fn settings_body(
    enabled: Option<bool>,
    keep_days: Option<u32>,
) -> Result<serde_json::Value, String> {
    match (enabled, keep_days) {
        (Some(on), None) => Ok(serde_json::json!({ "enabled": on })),
        (None, Some(days)) if KEEP_DAYS.contains(&days) => {
            Ok(serde_json::json!({ "keep_days": days }))
        }
        (None, Some(days)) => Err(format!(
            "{days} days is not a choice; pick never, 30 days, 90 days or 1 year."
        )),
        _ => Err("Change one chat history setting at a time.".to_string()),
    }
}

/// [`brain_history_settings`]'s reading. 200 (off, keep days) and 202
/// (`{"waiting": true}` - a card was raised, history is NOT on yet) are both
/// answers to show as they are; a 503 (the tier is not `ask`) and anything
/// else is the backend's own sentence.
pub(crate) fn settings_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body).ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 {
        return Err(HISTORY_UPDATE.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// The list with its conversations taken out, for while the private lists
/// are hidden (lock.rs). The switch, the keep setting and `why_not` stay:
/// they say nothing about what was said.
pub(crate) fn redact_list(mut list: serde_json::Value) -> serde_json::Value {
    if let Some(obj) = list.as_object_mut() {
        if let Some(serde_json::Value::Array(items)) = obj.get_mut("conversations") {
            let count = items.len();
            items.clear();
            obj.insert("hidden".into(), serde_json::json!(true));
            obj.insert("hidden_count".into(), serde_json::json!(count));
        }
    }
    list
}

// ---------------------------------------------------------------------------
// Chat tags (docs/CHAT-TAGS-DESIGN.md section 10)
// ---------------------------------------------------------------------------

/// A tag name as the PC takes it: trimmed, 1-24 characters.
fn checked_tag_name(name: &str) -> Result<String, String> {
    let name = name.trim();
    let n = name.chars().count();
    if n == 0 || n > TAG_NAME_MAX || name.chars().any(|c| c.is_control()) {
        return Err("A tag name needs 1 to 24 letters or numbers.".to_string());
    }
    Ok(name.to_string())
}

fn checked_tag_colour(colour: i64) -> Result<i64, String> {
    if (0..TAG_COLOURS).contains(&colour) {
        Ok(colour)
    } else {
        Err("That colour is not one of the eight.".to_string())
    }
}

fn checked_tag_icon(icon: &str) -> Result<&str, String> {
    if TAG_ICONS.contains(&icon) {
        Ok(icon)
    } else {
        Err("That icon is not on the list.".to_string())
    }
}

fn checked_tag_id(id: Option<i64>) -> Result<i64, String> {
    match id {
        Some(n) if n > 0 => Ok(n),
        _ => Err("That is not a tag this PC keeps.".to_string()),
    }
}

/// The body for `POST /api/history/tags`: one `op` with exactly its own
/// fields, checked here so nothing else can ride along. `before` matters
/// only for `move` (`null` puts the tag last).
pub(crate) fn tags_body(
    op: &str,
    id: Option<i64>,
    name: Option<&str>,
    colour: Option<i64>,
    icon: Option<&str>,
    before: Option<i64>,
) -> Result<serde_json::Value, String> {
    let mut body = serde_json::Map::new();
    body.insert("op".into(), serde_json::json!(op));
    match op {
        "add" => {
            body.insert(
                "name".into(),
                serde_json::json!(checked_tag_name(name.unwrap_or(""))?),
            );
            if let Some(c) = colour {
                body.insert("colour".into(), serde_json::json!(checked_tag_colour(c)?));
            }
            if let Some(i) = icon {
                body.insert("icon".into(), serde_json::json!(checked_tag_icon(i)?));
            }
        }
        "rename" => {
            body.insert("id".into(), serde_json::json!(checked_tag_id(id)?));
            body.insert(
                "name".into(),
                serde_json::json!(checked_tag_name(name.unwrap_or(""))?),
            );
        }
        "style" => {
            body.insert("id".into(), serde_json::json!(checked_tag_id(id)?));
            if colour.is_none() && icon.is_none() {
                return Err("Pick a colour or an icon to change.".to_string());
            }
            if let Some(c) = colour {
                body.insert("colour".into(), serde_json::json!(checked_tag_colour(c)?));
            }
            if let Some(i) = icon {
                body.insert("icon".into(), serde_json::json!(checked_tag_icon(i)?));
            }
        }
        "move" => {
            body.insert("id".into(), serde_json::json!(checked_tag_id(id)?));
            body.insert(
                "before".into(),
                match before {
                    None => serde_json::Value::Null,
                    Some(b) => serde_json::json!(checked_tag_id(Some(b))?),
                },
            );
        }
        "delete" => {
            body.insert("id".into(), serde_json::json!(checked_tag_id(id)?));
        }
        other => return Err(format!("{other:?} is not something tags can do")),
    }
    Ok(serde_json::Value::Object(body))
}

/// The body for `POST /api/history/tag`: file one chat under a tag, or
/// (`None`) take its tag off.
pub(crate) fn tag_chat_body(id: &str, tag_id: Option<i64>) -> Result<serde_json::Value, String> {
    let id = checked_id(id)?;
    let tag_id = match tag_id {
        None => serde_json::Value::Null,
        Some(n) => serde_json::json!(checked_tag_id(Some(n))?),
    };
    Ok(serde_json::json!({ "id": id, "tag_id": tag_id }))
}

/// A refusal the PC classified: `{"ok": false, "error": <one of the known
/// codes>, ...}`. Passed on intact so the page can say one plain sentence
/// per code; an `error` that is not a known code is not treated as one.
fn tag_refusal(body: &str) -> Option<serde_json::Value> {
    let v = parsed(body)?;
    if v.get("ok").and_then(|o| o.as_bool()) != Some(false) {
        return None;
    }
    let code = v.get("error").and_then(|e| e.as_str())?;
    TAG_ERROR_CODES.contains(&code).then_some(v)
}

/// [`brain_history_tags`]'s reading of `GET /api/history/tags`: the PC's
/// `{"ok": true, "tags": [...], "untagged": n}`. A backend without the route
/// (404, 501) is `{"available": false, "why": TAGS_UPDATE}`, not an error.
pub(crate) fn tags_read_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("tags").is_some_and(|t| t.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 || status == 501 {
        return Ok(serde_json::json!({ "available": false, "why": TAGS_UPDATE }));
    }
    Err(commands::backend_refusal(status, body))
}

/// The reading of a tag write (`POST /api/history/tags` or `/tag`). A 2xx
/// with `ok: true` is passed on; a refusal the PC classified comes back as
/// `Ok` with `ok: false` intact; a backend with no route is [`TAGS_UPDATE`].
pub(crate) fn tag_write_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("ok").and_then(|o| o.as_bool()) == Some(true))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if let Some(v) = tag_refusal(body) {
        return Ok(v);
    }
    if status == 404 || status == 501 {
        return Err(TAGS_UPDATE.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// The tag read with the names taken out, for while the private lists are
/// hidden: only each tag's id, place and how many chats it holds stay
/// (counts only). Colour and icon go too, so a tag is nothing but a number.
pub(crate) fn redact_tags(mut v: serde_json::Value) -> serde_json::Value {
    if let Some(obj) = v.as_object_mut() {
        if let Some(serde_json::Value::Array(tags)) = obj.get_mut("tags") {
            for t in tags.iter_mut() {
                let kept = serde_json::json!({
                    "id": t.get("id").cloned().unwrap_or(serde_json::Value::Null),
                    "order": t.get("order").cloned().unwrap_or(serde_json::Value::Null),
                    "count": t.get("count").cloned().unwrap_or(serde_json::json!(0)),
                });
                *t = kept;
            }
        }
        obj.insert("hidden".into(), serde_json::json!(true));
    }
    v
}

// ---------------------------------------------------------------------------
// The commands
// ---------------------------------------------------------------------------

async fn get(app: &AppHandle, path: &str) -> Result<(u16, String), String> {
    let base = commands::jarvis_base(app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{path}"))
        .headers(commands::jarvis_headers(app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    Ok((status, response.text().await.unwrap_or_default()))
}

async fn post(
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
    Ok((status, response.text().await.unwrap_or_default()))
}

/// One page of conversations, newest first. `before`: the `updated` of the
/// oldest one already shown, for "Load older". Reads only.
#[tauri::command]
pub async fn brain_history_list(
    app: AppHandle,
    before: Option<f64>,
    limit: Option<u32>,
    kind: Option<String>,
    tag: Option<String>,
) -> Result<serde_json::Value, String> {
    let path = list_path_tagged(limit, before, kind.as_deref(), tag.as_deref())?;
    let (status, body) = get(&app, &path).await?;
    let answer = list_answer(status, &body)?;
    Ok(if crate::lock::private_hidden(&app) {
        redact_list(answer)
    } else {
        answer
    })
}

/// One conversation's transcript, read-only. Refused while the private
/// lists are hidden.
#[tauri::command]
pub async fn brain_history_open(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    let id = checked_id(&id)?;
    if crate::lock::private_hidden(&app) {
        return Err(HISTORY_STILL_HIDDEN.to_string());
    }
    let (status, body) = get(&app, &format!("/api/history/conversation?id={id}")).await?;
    conversation_answer(status, &body)
}

/// "Continue this chat", from the Brain's History (the owner's decision,
/// 2026-09-28): brings up the Jarvis bar and tells it which conversation to
/// carry on - the id only, never a word. The bar reads it itself
/// ([`chat_continue_open`]). Refused while the private lists are hidden,
/// like opening one. Not held on a stale link: it changes nothing on the
/// PC; the next question is held there as any question is.
#[tauri::command]
pub async fn brain_continue_chat(app: AppHandle, id: String) -> Result<(), String> {
    let id = checked_id(&id)?.to_string();
    if crate::lock::private_hidden(&app) {
        return Err(HISTORY_STILL_HIDDEN.to_string());
    }
    crate::windows::show_quickbar(&app)?;
    crate::emit_quickbar(&app, CONTINUE_EVENT, Some(id));
    Ok(())
}

/// The Jarvis bar's one read of History: a conversation it may carry on
/// ("Continue this chat", or "Move it here" in Jarvis Live) - a chat or a
/// Live session, never a support, chatbot or comparison record. Refused
/// while the private lists are hidden, like opening one in the Brain.
#[tauri::command]
pub async fn chat_continue_open(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    let id = checked_id(&id)?;
    if crate::lock::private_hidden(&app) {
        return Err(HISTORY_STILL_HIDDEN.to_string());
    }
    let (status, body) = get(&app, &format!("/api/history/conversation?id={id}")).await?;
    continue_answer(status, &body)
}

/// Are the private lists hidden right now ("Hide memory lists and chat
/// history")? The Jarvis bar asks before it draws the folded thread of
/// earlier answers (the owner's decision, 2026-09-28, after the second chat
/// audit: the thread hides with the rest of the chat history; the answer on
/// screen, being asked about right now, does not). Nothing is read from the
/// PC and nothing is returned but yes or no.
#[tauri::command]
pub async fn chat_thread_hidden(app: AppHandle) -> bool {
    crate::lock::private_hidden(&app)
}

/// [`brain_fact_chat`]'s reading: the PC's `{"id", "conversation": null |
/// {...}}`, or - from a PC without the route (404, 501) - `{"available":
/// false}`, and "Erase the words" then asks as it did before, without
/// naming a chat.
pub(crate) fn fact_chat_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("conversation").is_some())
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 && body.contains("no fact") {
        return Err("That fact is no longer on this PC.".to_string());
    }
    if status == 404 || status == 501 {
        return Ok(serde_json::json!({ "available": false }));
    }
    Err(commands::backend_refusal(status, body))
}

/// While the private lists are hidden, the chat's title is taken out (that
/// there is one stays, so the question still says a chat will go too).
pub(crate) fn redact_fact_chat(mut v: serde_json::Value) -> serde_json::Value {
    if let Some(conv) = v.get_mut("conversation").and_then(|c| c.as_object_mut()) {
        conv.remove("title");
        conv.insert("hidden".into(), serde_json::json!(true));
    }
    v
}

/// "Which chat did this fact come from?" (the chat audit, 2026-09-28): for
/// "Erase the words"'s "Also delete the chat it came from", which names that
/// chat before asking. A read (`GET /api/memory/fact-chat?id=`); it deletes
/// nothing.
#[tauri::command]
pub async fn brain_fact_chat(app: AppHandle, id: i64) -> Result<serde_json::Value, String> {
    if id <= 0 {
        return Err("That is not a fact this PC keeps.".to_string());
    }
    let (status, body) = get(&app, &format!("/api/memory/fact-chat?id={id}")).await?;
    let out = fact_chat_answer(status, &body)?;
    Ok(if crate::lock::private_hidden(&app) {
        redact_fact_chat(out)
    } else {
        out
    })
}

/// "Search what was said" (JARVIS-API.md section 71): the kept
/// conversations whose words hold every search word, each with a short
/// snippet. A read. The PC opens each kept turn in memory for this one
/// search and keeps no index and no record of the words; this command
/// keeps none either, and nothing here reaches the AI model.
///
/// Refused while the private lists are hidden, like opening a transcript:
/// a snippet is what was said.
#[tauri::command]
pub async fn brain_history_search(
    app: AppHandle,
    query: String,
    limit: Option<u32>,
    kind: Option<String>,
) -> Result<serde_json::Value, String> {
    let path = search_path(&query, limit, kind.as_deref())?;
    if crate::lock::private_hidden(&app) {
        return Err(SEARCH_STILL_HIDDEN.to_string());
    }
    let (status, body) = get(&app, &path).await?;
    search_answer(status, &body)
}

/// The owner's tags with how many chats each holds (`GET /api/history/tags`).
/// A read. While the private lists are hidden the names are taken out here,
/// in Rust, and only the counts come back.
#[tauri::command]
pub async fn brain_history_tags(app: AppHandle) -> Result<serde_json::Value, String> {
    let (status, body) = get(&app, "/api/history/tags").await?;
    let answer = tags_read_answer(status, &body)?;
    Ok(if crate::lock::private_hidden(&app) {
        redact_tags(answer)
    } else {
        answer
    })
}

/// Adds, renames, restyles, moves or deletes ONE tag (`POST
/// /api/history/tags`). No approval card: it is the owner's own tidying and
/// nothing leaves the PC. Refused while the private lists are hidden (the
/// names are the owner's words) and held while the event stream is stale
/// (rule 4). Deleting makes the tag's chats untagged; the page asks first.
#[tauri::command]
pub async fn brain_history_tags_edit(
    app: AppHandle,
    op: String,
    id: Option<i64>,
    name: Option<String>,
    colour: Option<i64>,
    icon: Option<String>,
    before: Option<i64>,
) -> Result<serde_json::Value, String> {
    let body = tags_body(&op, id, name.as_deref(), colour, icon.as_deref(), before)?;
    if crate::lock::private_hidden(&app) {
        return Err(TAGS_STILL_HIDDEN.to_string());
    }
    require_link_live(&app)?;
    let (status, text) = post(&app, "/api/history/tags", body).await?;
    tag_write_answer(status, &text)
}

/// Files ONE chat under a tag, or (`tag_id` empty) takes its tag off
/// (`POST /api/history/tag`). No card. Refused while the private lists are
/// hidden and held while the event stream is stale.
#[tauri::command]
pub async fn brain_history_tag(
    app: AppHandle,
    id: String,
    tag_id: Option<i64>,
) -> Result<serde_json::Value, String> {
    let body = tag_chat_body(&id, tag_id)?;
    if crate::lock::private_hidden(&app) {
        return Err(TAGS_STILL_HIDDEN.to_string());
    }
    require_link_live(&app)?;
    let (status, text) = post(&app, "/api/history/tag", body).await?;
    tag_write_answer(status, &text)
}

/// Deletes ONE conversation. It cannot be undone, and the page asks first.
/// Held while the event stream is stale, like forgetting a fact
/// ([`super::brain_memory_forget`]): it acts on a list read from a link
/// that cannot be confirmed live.
#[tauri::command]
pub async fn brain_history_delete(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let id = checked_id(&id)?;
    let (status, body) = post(&app, "/api/history/delete", serde_json::json!({ "id": id })).await?;
    delete_answer(status, &body)
}

/// Changes ONE chat history setting: `enabled` (the switch) or `keep_days`.
///
/// Turning history ON raises an approval card and is held on a stale link;
/// OFF is immediate and never held. A `keep_days` shorter than before
/// deletes older conversations at once, and it was chosen from a setting
/// this window read, so every keep change is held on a stale link too (the
/// page greys the choice then, the same rule).
#[tauri::command]
pub async fn brain_history_settings(
    app: AppHandle,
    enabled: Option<bool>,
    keep_days: Option<u32>,
) -> Result<serde_json::Value, String> {
    let body = settings_body(enabled, keep_days)?;
    if enabled == Some(true) || keep_days.is_some() {
        require_link_live(&app)?;
    }
    let (status, text) = post(&app, "/api/history/settings", body).await?;
    settings_answer(status, &text)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_page_is_asked_for_within_the_servers_limits() {
        assert_eq!(
            list_path(None, None, None).unwrap(),
            "/api/history?limit=30"
        );
        assert_eq!(
            list_path(Some(0), None, None).unwrap(),
            "/api/history?limit=1"
        );
        assert_eq!(
            list_path(Some(500), None, None).unwrap(),
            "/api/history?limit=100"
        );
        assert_eq!(
            list_path(Some(30), Some(1_790_000_300.0), None).unwrap(),
            "/api/history?limit=30&before=1790000300"
        );
        // A fractional `updated` goes back exactly as it came, never rounded
        // into the next second.
        assert_eq!(
            list_path(None, Some(1_790_000_300.25), None).unwrap(),
            "/api/history?limit=30&before=1790000300.25"
        );
        for bad in [f64::NAN, f64::INFINITY, 0.0, -5.0] {
            assert!(list_path(None, Some(bad), None).is_err(), "{bad}");
        }
    }

    #[test]
    fn a_kind_is_one_of_the_five_or_nothing() {
        assert_eq!(
            list_path(None, None, Some("live")).unwrap(),
            "/api/history?limit=30&kind=live"
        );
        assert_eq!(
            list_path(None, None, Some("")).unwrap(),
            "/api/history?limit=30"
        );
        assert!(list_path(None, None, Some("live&limit=100")).is_err());
        assert!(list_path(None, None, Some("imported")).is_err());
    }

    #[test]
    fn a_tag_filter_is_a_whole_id_or_none() {
        assert_eq!(
            list_path_tagged(None, None, None, Some("3")).unwrap(),
            "/api/history?limit=30&tag=3"
        );
        assert_eq!(
            list_path_tagged(None, None, Some("live"), Some("none")).unwrap(),
            "/api/history?limit=30&kind=live&tag=none"
        );
        assert_eq!(
            list_path_tagged(None, None, None, Some("")).unwrap(),
            "/api/history?limit=30"
        );
        for bad in ["3&limit=100", "-1", "0", "03", "all", "1.5", "None"] {
            assert!(
                list_path_tagged(None, None, None, Some(bad)).is_err(),
                "{bad}"
            );
        }
    }

    #[test]
    fn a_tag_edit_sends_only_its_own_fields() {
        let add = tags_body(
            "add",
            None,
            Some("  Garage "),
            Some(7),
            Some("wrench"),
            None,
        )
        .unwrap();
        assert_eq!(
            add,
            serde_json::json!({"op": "add", "name": "Garage", "colour": 7, "icon": "wrench"})
        );
        let bare = tags_body("add", Some(9), Some("Garage"), None, None, Some(4)).unwrap();
        assert_eq!(bare, serde_json::json!({"op": "add", "name": "Garage"}));
        let rename = tags_body("rename", Some(2), Some("Study"), Some(1), None, None).unwrap();
        assert_eq!(
            rename,
            serde_json::json!({"op": "rename", "id": 2, "name": "Study"})
        );
        let style = tags_body("style", Some(2), None, Some(5), None, None).unwrap();
        assert_eq!(
            style,
            serde_json::json!({"op": "style", "id": 2, "colour": 5})
        );
        let last = tags_body("move", Some(2), None, None, None, None).unwrap();
        assert_eq!(
            last,
            serde_json::json!({"op": "move", "id": 2, "before": null})
        );
        let before = tags_body("move", Some(2), None, None, None, Some(4)).unwrap();
        assert_eq!(
            before,
            serde_json::json!({"op": "move", "id": 2, "before": 4})
        );
        let del = tags_body("delete", Some(5), Some("x"), None, None, None).unwrap();
        assert_eq!(del, serde_json::json!({"op": "delete", "id": 5}));
    }

    #[test]
    fn a_bad_tag_edit_is_refused_before_it_is_sent() {
        let long = "x".repeat(TAG_NAME_MAX + 1);
        for (op, id, name, colour, icon) in [
            ("add", None, Some(""), None, None),
            ("add", None, Some("   "), None, None),
            ("add", None, None, None, None),
            ("add", None, Some(long.as_str()), None, None),
            ("add", None, Some("a\nb"), None, None),
            ("add", None, Some("ok"), Some(8), None),
            ("add", None, Some("ok"), Some(-1), None),
            ("add", None, Some("ok"), None, Some("smiley")),
            ("rename", None, Some("ok"), None, None),
            ("rename", Some(0), Some("ok"), None, None),
            ("style", Some(1), None, None, None),
            ("move", Some(-3), None, None, None),
            ("delete", None, None, None, None),
            ("erase-everything", Some(1), None, None, None),
        ] {
            assert!(
                tags_body(op, id, name, colour, icon, None).is_err(),
                "{op} {id:?} {name:?} {colour:?} {icon:?}"
            );
        }
        // 24 characters exactly is fine.
        let edge = "x".repeat(TAG_NAME_MAX);
        assert!(tags_body("add", None, Some(&edge), None, None, None).is_ok());
        // Every icon in the shared list is accepted, and colours 0-7.
        for icon in TAG_ICONS {
            assert!(tags_body("add", None, Some("a"), None, Some(icon), None).is_ok());
        }
        for c in 0..8 {
            assert!(tags_body("add", None, Some("a"), Some(c), None, None).is_ok());
        }
    }

    #[test]
    fn filing_a_chat_names_a_real_chat_and_a_real_tag() {
        assert_eq!(
            tag_chat_body("conv-0001-abcd", Some(2)).unwrap(),
            serde_json::json!({"id": "conv-0001-abcd", "tag_id": 2})
        );
        assert_eq!(
            tag_chat_body("conv-0001-abcd", None).unwrap(),
            serde_json::json!({"id": "conv-0001-abcd", "tag_id": null})
        );
        assert!(tag_chat_body("../etc", Some(2)).is_err());
        assert!(tag_chat_body("conv-0001-abcd", Some(0)).is_err());
    }

    #[test]
    fn the_tag_answers_are_read_as_the_contract_says() {
        let read = tags_read_answer(
            200,
            r#"{"ok":true,"tags":[{"id":1,"name":"Work","colour":0,"icon":"briefcase","order":0,"count":3}],"untagged":4}"#,
        )
        .unwrap();
        assert_eq!(read["untagged"], 4);
        assert!(tags_read_answer(200, r#"{"ok":true}"#).is_err());
        assert_eq!(tags_read_answer(404, "").unwrap()["why"], TAGS_UPDATE);
        // A write: success passes on, a classified refusal keeps its code,
        // a made-up code does not count as one.
        assert_eq!(
            tag_write_answer(200, r#"{"ok":true,"id":"c","tag_id":2}"#).unwrap()["tag_id"],
            2
        );
        let taken = tag_write_answer(
            409,
            r#"{"ok":false,"error":"name_taken","message":"already"}"#,
        )
        .unwrap();
        assert_eq!(taken["ok"], false);
        assert_eq!(taken["error"], "name_taken");
        let gone = tag_write_answer(404, r#"{"ok":false,"error":"not_found"}"#).unwrap();
        assert_eq!(gone["error"], "not_found");
        assert!(tag_write_answer(400, r#"{"ok":false,"error":"made_up"}"#).is_err());
        assert_eq!(tag_write_answer(404, "Not Found").unwrap_err(), TAGS_UPDATE);
        assert!(tag_write_answer(200, "<html>").is_err());
        assert!(tag_write_answer(200, r#"{"ok":false}"#).is_err());
    }

    #[test]
    fn hidden_tags_keep_counts_and_nothing_else() {
        let hidden = redact_tags(serde_json::json!({
            "ok": true, "untagged": 4,
            "tags": [
                {"id": 1, "name": "Health worries", "colour": 3, "icon": "star", "order": 0, "count": 3},
                {"id": 2, "name": "Boiler", "colour": 1, "icon": "home", "order": 1, "count": 1},
            ],
        }));
        assert_eq!(hidden["hidden"], true);
        assert_eq!(hidden["untagged"], 4);
        let text = hidden.to_string();
        assert!(
            !text.contains("Health") && !text.contains("Boiler"),
            "{text}"
        );
        let first = &hidden["tags"][0];
        assert_eq!(first["count"], 3);
        assert!(first.get("name").is_none() && first.get("icon").is_none());
    }

    #[test]
    fn every_tag_command_asks_the_lock_and_the_link() {
        // Source check: the three commands share one shape.
        let src = include_str!("history.rs");
        for name in [
            "pub async fn brain_history_tags(",
            "pub async fn brain_history_tags_edit(",
            "pub async fn brain_history_tag(",
        ] {
            let at = src.find(name).expect(name);
            let body = &src[at..at + 900.min(src.len() - at)];
            assert!(body.contains("private_hidden"), "{name} ignores the lock");
        }
        for name in [
            "pub async fn brain_history_tags_edit(",
            "pub async fn brain_history_tag(",
        ] {
            let at = src.find(name).unwrap();
            let body = &src[at..at + 900.min(src.len() - at)];
            let live = body.find("require_link_live").expect(name);
            assert!(
                live < body.find("post(").unwrap(),
                "{name} posts before rule 4"
            );
        }
    }

    #[test]
    fn which_chat_a_fact_came_from() {
        let got = fact_chat_answer(
            200,
            r#"{"id":3,"conversation":{"id":"conv-1","title":"t","updated":5,"kind":"chat"}}"#,
        )
        .unwrap();
        assert_eq!(got["conversation"]["title"], "t");
        let hidden = redact_fact_chat(got);
        assert!(hidden["conversation"].get("title").is_none());
        assert_eq!(hidden["conversation"]["hidden"], true);
        let none = fact_chat_answer(200, r#"{"id":3,"conversation":null}"#).unwrap();
        assert!(none["conversation"].is_null());
        assert_eq!(
            fact_chat_answer(404, "not found").unwrap()["available"],
            false
        );
        assert!(fact_chat_answer(404, r#"{"error":"no fact with that id"}"#).is_err());
    }

    #[test]
    fn only_a_chat_or_a_live_session_is_carried_on() {
        let chat = r#"{"id":"c1","kind":"chat","turns":[{"role":"user","text":"hi"}]}"#;
        assert!(continue_answer(200, chat).is_ok());
        let live = r#"{"id":"c1","kind":"live","turns":[]}"#;
        assert!(continue_answer(200, live).is_ok());
        let old = r#"{"id":"c1","turns":[{"role":"user","text":"hi"}]}"#;
        assert!(continue_answer(200, old).is_ok(), "an older PC's chat");
        for kind in ["support", "chatbot", "compare", "nonsense"] {
            let body = format!(r#"{{"id":"c1","kind":"{kind}","turns":[]}}"#);
            assert_eq!(
                continue_answer(200, &body).unwrap_err(),
                NOT_CONTINUABLE,
                "{kind}"
            );
        }
        let old_support = r#"{"id":"c1","turns":[{"role":"support","text":"x"}]}"#;
        assert!(
            continue_answer(200, old_support).is_err(),
            "an older PC's support record"
        );
        assert!(continue_answer(404, "").is_err());
    }

    #[test]
    fn only_a_well_formed_id_reaches_a_url() {
        assert!(checked_id("3f2c9a1e-7b4d-4c1a-9e2f-0a1b2c3d4e5f").is_ok());
        for bad in [
            "short",
            "a&limit=100000",
            "a b c d e f g",
            "../../etc/passwd",
        ] {
            assert!(checked_id(bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn the_list_is_passed_on_and_an_older_backend_says_update() {
        let body = r#"{"enabled": true, "recording": true, "why_not": "", "waiting": false,
            "keep_days": 0, "encrypted": true, "conversations": [{"id": "abcdefgh"}]}"#;
        let got = list_answer(200, body).unwrap();
        assert_eq!(got["conversations"][0]["id"], "abcdefgh");
        let old = list_answer(404, "").unwrap();
        assert_eq!(old["available"], false);
        assert!(old["why"].as_str().unwrap().contains("apply-patches.ps1"));
        assert!(list_answer(200, r#"{"ok": true}"#).is_err());
        assert_eq!(
            list_answer(500, r#"{"error": "the history store is locked"}"#).unwrap_err(),
            "The history store is locked"
        );
    }

    #[test]
    fn a_transcript_or_why_not() {
        let got = conversation_answer(200, r#"{"id": "abcdefgh", "turns": []}"#).unwrap();
        assert_eq!(got["id"], "abcdefgh");
        assert!(conversation_answer(404, "")
            .unwrap_err()
            .contains("no longer kept"));
        assert!(conversation_answer(200, "{}").is_err());
    }

    #[test]
    fn deleting_one_already_gone_is_not_a_failure() {
        assert_eq!(delete_answer(200, r#"{"ok": true}"#).unwrap()["ok"], true);
        let gone = delete_answer(404, "").unwrap();
        assert_eq!(gone["gone"], true);
        assert!(delete_answer(500, "").is_err());
    }

    #[test]
    fn one_setting_per_request_and_only_the_four_keep_choices() {
        assert_eq!(
            settings_body(Some(false), None).unwrap(),
            serde_json::json!({ "enabled": false })
        );
        for days in KEEP_DAYS {
            assert_eq!(
                settings_body(None, Some(days)).unwrap(),
                serde_json::json!({ "keep_days": days })
            );
        }
        assert!(settings_body(None, Some(7)).is_err());
        assert!(settings_body(Some(true), Some(30)).is_err());
        assert!(settings_body(None, None).is_err());
    }

    #[test]
    fn on_waits_and_a_refusal_is_the_servers_own_sentence() {
        let waiting = settings_answer(202, r#"{"waiting": true, "enabled": false}"#).unwrap();
        assert_eq!(waiting["waiting"], true);
        assert_eq!(
            settings_answer(
                503,
                r#"{"error": "history_enable is not set to ask in jarvis-framework.toml"}"#
            )
            .unwrap_err(),
            "History_enable is not set to ask in jarvis-framework.toml"
        );
        assert_eq!(settings_answer(404, "").unwrap_err(), HISTORY_UPDATE);
    }

    #[test]
    fn a_search_is_sent_only_within_the_pcs_limits_and_cannot_add_a_parameter() {
        assert_eq!(
            search_path("dentist", None, None).unwrap(),
            "/api/history/search?q=dentist&limit=20"
        );
        assert_eq!(
            search_path("  mill   road ", Some(500), None).unwrap(),
            "/api/history/search?q=mill%20road&limit=50"
        );
        // Nothing the owner types can start a second parameter or become a space.
        let odd = search_path("a&limit=100000#x+y=z", Some(3), None).unwrap();
        assert_eq!(
            odd,
            "/api/history/search?q=a%26limit%3D100000%23x%2By%3Dz&limit=3"
        );
        assert!(search_path("café ☕", None, None)
            .unwrap()
            .contains("caf%C3%A9%20%E2%98%95"));
        assert!(search_path("a", None, None).is_err());
        assert!(search_path("   ", None, None).is_err());
        assert!(search_path(&"x".repeat(101), None, None).is_err());
        assert!(
            search_path(&"é".repeat(100), None, None).is_ok(),
            "characters, not bytes"
        );
    }

    #[test]
    fn a_search_can_be_narrowed_to_one_kind_and_only_a_real_one() {
        assert_eq!(
            search_path("dentist", None, Some("live")).unwrap(),
            "/api/history/search?q=dentist&limit=20&kind=live"
        );
        assert_eq!(
            search_path("dentist", None, Some("")).unwrap(),
            "/api/history/search?q=dentist&limit=20"
        );
        assert!(search_path("dentist", None, Some("live&limit=100")).is_err());
        assert!(search_path("dentist", None, Some("imported")).is_err());
    }

    #[test]
    fn a_search_answer_or_title_only_on_an_older_backend() {
        let body = r#"{"query_ok": true, "conversations": [{"id": "abcdefgh",
            "snippet": {"parts": [{"text": "dentist", "hit": true}]}}], "more": false}"#;
        let got = search_answer(200, body).unwrap();
        assert_eq!(got["conversations"][0]["id"], "abcdefgh");
        for status in [404, 501] {
            let old = search_answer(status, "").unwrap();
            assert_eq!(old["available"], false);
            assert_eq!(old["why"], SEARCH_UPDATE);
        }
        assert!(search_answer(200, r#"{"conversations": []}"#).is_err());
        assert_eq!(
            search_answer(500, r#"{"error": "the history store is locked"}"#).unwrap_err(),
            "The history store is locked"
        );
        assert!(SEARCH_STILL_HIDDEN.contains("Windows Hello"));
    }

    #[test]
    fn hidden_lists_keep_the_count_and_the_settings_but_no_conversation() {
        let list = serde_json::json!({
            "enabled": true, "recording": true, "keep_days": 30,
            "conversations": [{"id": "abcdefgh", "title": "Dentist"}, {"id": "ijklmnop"}]
        });
        let hidden = redact_list(list);
        assert_eq!(hidden["conversations"], serde_json::json!([]));
        assert_eq!(hidden["hidden"], true);
        assert_eq!(hidden["hidden_count"], 2);
        assert_eq!(hidden["keep_days"], 30);
        assert!(!hidden.to_string().contains("Dentist"));
    }
}
