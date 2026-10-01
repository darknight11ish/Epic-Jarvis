//! Topic controls (the owner's request of 2026-09-30, "adjust the brain of
//! Jarvis to include or exclude different topics"; JARVIS-API.md section 107;
//! `docs/TOPIC-CONTROLS-DESIGN.md`, "Slice contract (frozen)" C1-C10; backend
//! `jarvis_topics.py`).
//!
//! Every saved fact sits under one topic, and each topic has a mode: learn and
//! use, use but do not learn, learn but do not use, or off. The PC enforces
//! the modes; this file only carries the owner's taps there. Eight commands,
//! one per power, in the style of [`super::decks`]:
//!
//! * [`brain_topics`] - `GET /api/topics`: the topics, counts and modes. A read.
//! * [`brain_topics_edit`] - `POST /api/topics {"op": ...}`: add, rename,
//!   colour and icon, reorder, keywords, private on or off, delete with a
//!   destination for its facts. Never deletes a fact.
//! * [`brain_topics_mode`] - `POST /api/topics/mode {"id", "mode"}`.
//! * [`brain_topics_file`] - `POST /api/topics/file`: file the ticked facts
//!   under a topic, or confirm the guesses ("These are right").
//! * [`brain_topics_settings`] - `POST /api/topics/settings {"model_help"}`.
//! * [`brain_topics_preview`] - `GET /api/topics/preview?id=&mode=`: what a
//!   change would do, in numbers and one sentence from the PC. A read.
//! * [`brain_topics_review`] - `GET /api/topics/review`: the facts Jarvis
//!   sorted by guessing, ten at a time. A memory list.
//! * [`brain_topics_hidden`] - `GET /api/topics/hidden`: one topic's facts
//!   ("Show them" on an Off topic). A memory list.
//!
//! A write that raises an approval card comes back `202` with `waiting: true`;
//! that is handed on as it is (it is an `ok: true` answer), and the page reads
//! `GET /api/topics` until `waiting` is null. **This file never decides
//! whether a change needs a card**: the PC does (rule: stricter is at once,
//! looser on a private topic is a card). It never approves one either.
//!
//! Every write is held on a stale link (rule 4); the reads are not. The
//! PC's own refusals (`{"ok": false, "error": <code>, "message": ...}`) are
//! handed on unchanged, and the sentences the checks below make on their own
//! are the PC's (they are in the shared fixture, `tests/fixtures/
//! topics-cases.json`, and a test holds the two together).
//!
//! **Hiding.** Topic names and keywords are the owner's words, so while "Hide
//! memory lists and chat history" (lock.rs) is on (or App lock has locked) they are taken out of every
//! answer here, in Rust, so a page script cannot read round it: names become
//! empty (Unsorted keeps its fixed name), keywords go, the preview's sentence
//! (which names the topic) goes. Counts and modes stay: they say nothing
//! about the owner's words. The two fact lists (the check list and "Show
//! them") are not fetched at all while hidden.
//!
//! No token is logged or returned. The answer-reading and redacting functions
//! are plain functions of (status, body) so their tests run without a Tauri
//! app or a network.

use serde::Deserialize;
use tauri::AppHandle;

use super::{require_link_live, READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

/// A PC whose backend has no topic controls yet (`words.missing` in the
/// shared fixture; the phone says the same).
pub(crate) const TOPICS_MISSING: &str =
    "Your PC's Jarvis does not have topic controls yet - run apply-patches.ps1 on the PC.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// The four modes, in the order the picker lists them.
pub(crate) const MODES: [&str; 4] = ["both", "use_only", "learn_only", "off"];

/// The icons a topic may wear: the chat tags' ten plus `heart`, `coin`, `people`.
pub(crate) const ICONS: [&str; 13] = [
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
    "heart",
    "coin",
    "people",
];

const NAME_MAX: usize = 24;
const WORDS_MAX: usize = 20;
const WORD_LEN: (usize, usize) = (2, 30);
const COLOURS: i64 = 8;
/// Facts one `file` call may carry.
const FILE_MAX: usize = 200;
const REVIEW_LIMIT_MAX: u32 = 50;
const HIDDEN_LIMIT_MAX: u32 = 100;

/// The PC's sentence for each error code the checks here can make. The same
/// words are in the fixture's `errors`; a test holds them together.
pub(crate) const ERRORS: [(&str, &str); 15] = [
    ("bad_request", "Jarvis could not understand that request."),
    (
        "bad_name",
        "A topic needs a name of 1 to 24 letters or numbers.",
    ),
    ("name_taken", "You already have a topic with that name."),
    (
        "too_many_topics",
        "You can have up to 16 topics of your own. Delete one first.",
    ),
    (
        "bad_colour",
        "That colour is not one of the eight to pick from.",
    ),
    (
        "bad_icon",
        "That picture is not one of the ones to pick from.",
    ),
    (
        "bad_words",
        "Keywords are short words or phrases, up to 20 of them.",
    ),
    ("topic_not_found", "That topic is not there any more."),
    ("bad_mode", "That is not one of the four choices."),
    ("no_delete_unsorted", "Unsorted cannot be deleted."),
    ("no_rename_unsorted", "Unsorted cannot be renamed."),
    (
        "needs_destination",
        "Pick a topic for its facts to move to first.",
    ),
    (
        "bad_destination",
        "Pick a different topic for its facts to move to.",
    ),
    ("no_such_fact", "One of those facts is not there any more."),
    ("unavailable", "Topics are not available on this PC yet."),
];

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

/// A refusal made here, before anything is sent, in the PC's own sentence.
pub(crate) fn refusal(code: &str) -> serde_json::Value {
    let message = ERRORS
        .iter()
        .find(|(c, _)| *c == code)
        .map_or(ERRORS[0].1, |(_, m)| *m);
    serde_json::json!({ "ok": false, "error": code, "message": message })
}

/// A body the backend itself classified as a refusal. `None` for any other
/// shape, which is how a backend with no topics at all (a bare 404) is told
/// apart from the feature's own `topic_not_found`.
fn backend_refusal_body(body: &str) -> Option<serde_json::Value> {
    let v = parsed(body)?;
    if v.get("ok").and_then(|o| o.as_bool()) != Some(false) {
        return None;
    }
    v.get("error")
        .and_then(|e| e.as_str())
        .filter(|s| !s.is_empty())?;
    Some(v)
}

/// The reading of any answer. `need` is a field a success must carry and that
/// is not null (`None`: only `ok: true`). A `202` (a card was raised) is an
/// `ok: true` answer and passes. A refusal the PC classified comes back as
/// `Ok` with `ok: false` intact, so the page can show its `message`.
pub(crate) fn topics_answer(
    status: u16,
    body: &str,
    need: Option<&str>,
) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("ok").and_then(|o| o.as_bool()) == Some(true))
            .filter(|v| need.is_none_or(|k| v.get(k).is_some_and(|x| !x.is_null())))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if let Some(refusal) = backend_refusal_body(body) {
        return Ok(refusal);
    }
    if status == 404 || status == 501 {
        return Err(TOPICS_MISSING.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// Any answer of this file with the owner's words taken out, for while the
/// private lists are hidden. Counts, modes, flags and ids stay. A refusal has
/// nothing to hide and is left as it is.
pub(crate) fn redact_answer(mut answer: serde_json::Value) -> serde_json::Value {
    if answer.get("ok").and_then(|o| o.as_bool()) != Some(true) {
        return answer;
    }
    if let Some(obj) = answer.as_object_mut() {
        if let Some(serde_json::Value::Array(topics)) = obj.get_mut("topics") {
            for t in topics.iter_mut() {
                let Some(o) = t.as_object_mut() else { continue };
                let unsorted = o.get("system").and_then(|s| s.as_bool()) == Some(true);
                if !unsorted {
                    o.insert("name".into(), serde_json::json!(""));
                }
                if o.contains_key("words") {
                    o.insert("words".into(), serde_json::json!([]));
                }
            }
        }
        // The preview's sentence names the topic. The page builds its own
        // from the numbers.
        if obj.contains_key("line") {
            obj.insert("line".into(), serde_json::json!(""));
        }
        obj.insert("lists_hidden".into(), serde_json::json!(true));
    }
    answer
}

/// True while "Hide memory lists and chat history" is on and not shown, or App
/// lock has locked (the same rule brain/progress.rs and retirement.rs use).
fn words_hidden(app: &AppHandle) -> bool {
    crate::lock::private_hidden(app) || crate::lock::app_locked(app)
}

fn hide_if_private(app: &AppHandle, answer: serde_json::Value) -> serde_json::Value {
    if words_hidden(app) {
        redact_answer(answer)
    } else {
        answer
    }
}

/// What the two fact lists answer while the private lists are hidden: no call
/// was made, so nothing about a fact is known here.
pub(crate) fn lists_hidden_answer() -> serde_json::Value {
    serde_json::json!({ "ok": true, "lists_hidden": true, "facts": [], "next": null, "total": 0 })
}

// ---------------------------------------------------------------------------
// The rules the PC also checks (held to the fixture's name_cases / words_cases)
// ---------------------------------------------------------------------------

/// The topic name, tidied (spaces collapsed) - or `None` when not allowed.
pub(crate) fn clean_name(raw: &str) -> Option<String> {
    let s = raw.split_whitespace().collect::<Vec<_>>().join(" ");
    if s.is_empty() || s.chars().count() > NAME_MAX {
        return None;
    }
    let bad = |c: char| {
        (c as u32) < 32
            || matches!(
                c,
                '\u{200b}' | '\u{200c}' | '\u{200d}' | '\u{2060}' | '\u{feff}'
            )
    };
    if s.chars().any(bad) {
        return None;
    }
    Some(s)
}

fn word_ok(w: &str) -> bool {
    let chars: Vec<char> = w.chars().collect();
    let Some((first, rest)) = chars.split_first() else {
        return false;
    };
    let Some((last, middle)) = rest.split_last() else {
        return false;
    };
    let edge = |c: &char| c.is_alphanumeric() || *c == '_';
    edge(first)
        && edge(last)
        && middle
            .iter()
            .all(|c| edge(c) || matches!(c, '\'' | ' ' | '-'))
}

/// The owner's keywords, lower-cased, no duplicates - or `None`. Takes the
/// shapes the PC does: null, a string (split on commas and new lines), or a
/// list of strings.
pub(crate) fn clean_words(raw: &serde_json::Value) -> Option<Vec<String>> {
    let items: Vec<serde_json::Value> = match raw {
        serde_json::Value::Null => return Some(Vec::new()),
        serde_json::Value::String(s) => s
            .split(['\n', ','])
            .map(|p| serde_json::Value::String(p.to_string()))
            .collect(),
        serde_json::Value::Array(a) => a.clone(),
        _ => return None,
    };
    if items.len() > WORDS_MAX * 2 {
        return None;
    }
    let mut out: Vec<String> = Vec::new();
    for item in items {
        let w = item.as_str()?;
        let w = w
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ")
            .to_lowercase();
        if w.is_empty() {
            continue;
        }
        let n = w.chars().count();
        if n < WORD_LEN.0 || n > WORD_LEN.1 || !word_ok(&w) {
            return None;
        }
        if !out.contains(&w) {
            out.push(w);
        }
    }
    (out.len() <= WORDS_MAX).then_some(out)
}

/// A topic id: a whole number from 1.
fn valid_id(id: Option<i64>) -> Result<i64, &'static str> {
    match id {
        Some(n) if n >= 1 => Ok(n),
        _ => Err("topic_not_found"),
    }
}

// ---------------------------------------------------------------------------
// Bodies
// ---------------------------------------------------------------------------

/// What the page sends for one change to the topics list. Field names are the
/// page's (camelCase); the PC's are made in [`edit_body`].
#[derive(Debug, Default, Deserialize)]
#[serde(default, rename_all = "camelCase")]
pub struct TopicEdit {
    pub op: String,
    pub id: Option<i64>,
    pub name: Option<String>,
    pub colour: Option<i64>,
    pub icon: Option<String>,
    pub words: Option<Vec<String>>,
    pub private: Option<bool>,
    pub before: Option<i64>,
    pub move_to: Option<i64>,
}

fn colour_ok(c: Option<i64>) -> Result<Option<i64>, &'static str> {
    match c {
        None => Ok(None),
        Some(n) if (0..COLOURS).contains(&n) => Ok(Some(n)),
        Some(_) => Err("bad_colour"),
    }
}

fn icon_ok(i: &Option<String>) -> Result<Option<String>, &'static str> {
    match i {
        None => Ok(None),
        Some(s) if ICONS.contains(&s.as_str()) => Ok(Some(s.clone())),
        Some(_) => Err("bad_icon"),
    }
}

/// The body of one `POST /api/topics`, or the error code that refuses it.
pub(crate) fn edit_body(e: &TopicEdit) -> Result<serde_json::Value, &'static str> {
    let name = |n: &Option<String>| n.as_deref().and_then(clean_name).ok_or("bad_name");
    let words = |w: &Option<Vec<String>>| {
        clean_words(&serde_json::json!(w.clone().unwrap_or_default())).ok_or("bad_words")
    };
    match e.op.as_str() {
        "add" => {
            let mut b = serde_json::json!({ "op": "add", "name": name(&e.name)? });
            if let Some(c) = colour_ok(e.colour)? {
                b["colour"] = serde_json::json!(c);
            }
            if let Some(i) = icon_ok(&e.icon)? {
                b["icon"] = serde_json::json!(i);
            }
            if e.words.is_some() {
                b["words"] = serde_json::json!(words(&e.words)?);
            }
            if let Some(p) = e.private {
                b["private"] = serde_json::json!(p);
            }
            Ok(b)
        }
        "rename" => Ok(serde_json::json!({
            "op": "rename", "id": valid_id(e.id)?, "name": name(&e.name)?
        })),
        "style" => {
            let id = valid_id(e.id)?;
            let colour = colour_ok(e.colour)?;
            let icon = icon_ok(&e.icon)?;
            if colour.is_none() && icon.is_none() {
                return Err("bad_request");
            }
            let mut b = serde_json::json!({ "op": "style", "id": id });
            if let Some(c) = colour {
                b["colour"] = serde_json::json!(c);
            }
            if let Some(i) = icon {
                b["icon"] = serde_json::json!(i);
            }
            Ok(b)
        }
        "move" => {
            let before = match e.before {
                None => serde_json::Value::Null,
                Some(n) if n >= 1 => serde_json::json!(n),
                Some(_) => return Err("topic_not_found"),
            };
            Ok(serde_json::json!({ "op": "move", "id": valid_id(e.id)?, "before": before }))
        }
        "words" => {
            if e.words.is_none() {
                return Err("bad_words");
            }
            Ok(serde_json::json!({
                "op": "words", "id": valid_id(e.id)?, "words": words(&e.words)?
            }))
        }
        "private" => match e.private {
            Some(p) => Ok(serde_json::json!({
                "op": "private", "id": valid_id(e.id)?, "private": p
            })),
            None => Err("bad_request"),
        },
        "delete" => {
            let id = valid_id(e.id)?;
            let to = match e.move_to {
                None => return Err("needs_destination"),
                Some(n) if n >= 1 => n,
                Some(_) => return Err("bad_destination"),
            };
            if to == id {
                return Err("bad_destination");
            }
            Ok(serde_json::json!({ "op": "delete", "id": id, "move_to": to }))
        }
        _ => Err("bad_request"),
    }
}

/// The body of one mode change.
pub(crate) fn mode_body(id: i64, mode: &str) -> Result<serde_json::Value, &'static str> {
    let id = valid_id(Some(id))?;
    if !MODES.contains(&mode) {
        return Err("bad_mode");
    }
    Ok(serde_json::json!({ "id": id, "mode": mode }))
}

/// The body of filing facts: under a topic (`topic_id`), or "These are right"
/// (`confirm`). One or the other, never both, never a bare list.
pub(crate) fn file_body(
    ids: &[i64],
    topic_id: Option<i64>,
    confirm: bool,
) -> Result<serde_json::Value, &'static str> {
    if ids.is_empty() || ids.len() > FILE_MAX || ids.iter().any(|n| *n < 1) {
        return Err("bad_request");
    }
    if confirm {
        if topic_id.is_some() {
            return Err("bad_request");
        }
        return Ok(serde_json::json!({ "ids": ids, "confirm": true }));
    }
    match topic_id {
        Some(t) if t >= 1 => Ok(serde_json::json!({ "ids": ids, "topic_id": t })),
        _ => Err("topic_not_found"),
    }
}

/// A review cursor is opaque but short and plain; anything else is refused
/// rather than sent.
fn cursor_ok(after: &str) -> bool {
    !after.is_empty()
        && after.len() <= 64
        && after
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-' | b'.' | b':'))
}

fn bad(code: &str) -> Result<serde_json::Value, String> {
    Ok(refusal(code))
}

// ---------------------------------------------------------------------------
// Talking to the PC
// ---------------------------------------------------------------------------

async fn get(
    app: &AppHandle,
    path: &str,
    query: &[(&str, String)],
    need: Option<&str>,
) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{path}"))
        .query(query)
        .headers(commands::jarvis_headers(app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    topics_answer(status, &body, need)
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
    topics_answer(status, &text, None)
}

/// The topics, their counts and modes. A read; names are taken out while the
/// private lists are hidden.
#[tauri::command]
pub async fn brain_topics(app: AppHandle) -> Result<serde_json::Value, String> {
    let answer = get(&app, "/api/topics", &[], Some("topics")).await?;
    Ok(hide_if_private(&app, answer))
}

/// One change to the topics list (add, rename, colour and icon, reorder,
/// keywords, private, delete with a home for its facts). Held on a stale
/// link. A `202` is handed on: a card is waiting on the PC.
#[tauri::command]
pub async fn brain_topics_edit(
    app: AppHandle,
    edit: TopicEdit,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let body = match edit_body(&edit) {
        Ok(b) => b,
        Err(code) => return bad(code),
    };
    let answer = post(&app, "/api/topics", body).await?;
    Ok(hide_if_private(&app, answer))
}

/// One topic's mode. Held on a stale link. `200` or `202` (a card).
#[tauri::command]
pub async fn brain_topics_mode(
    app: AppHandle,
    id: i64,
    mode: String,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let body = match mode_body(id, &mode) {
        Ok(b) => b,
        Err(code) => return bad(code),
    };
    let answer = post(&app, "/api/topics/mode", body).await?;
    Ok(hide_if_private(&app, answer))
}

/// File the ticked facts under a topic, or confirm the guesses. Held on a
/// stale link.
#[tauri::command]
pub async fn brain_topics_file(
    app: AppHandle,
    ids: Vec<i64>,
    topic_id: Option<i64>,
    confirm: Option<bool>,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    // The check list is not shown while hidden, so neither is anything filed
    // from it.
    if words_hidden(&app) {
        return Err(crate::lock::PRIVATE_STILL_HIDDEN.to_string());
    }
    let body = match file_body(&ids, topic_id, confirm == Some(true)) {
        Ok(b) => b,
        Err(code) => return bad(code),
    };
    let answer = post(&app, "/api/topics/file", body).await?;
    Ok(hide_if_private(&app, answer))
}

/// The "Let Jarvis's local model help sort" switch. No card. Held on a stale
/// link.
#[tauri::command]
pub async fn brain_topics_settings(
    app: AppHandle,
    model_help: bool,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let answer = post(
        &app,
        "/api/topics/settings",
        serde_json::json!({ "model_help": model_help }),
    )
    .await?;
    Ok(hide_if_private(&app, answer))
}

/// What one mode change would do, in numbers and one sentence. A read.
#[tauri::command]
pub async fn brain_topics_preview(
    app: AppHandle,
    id: i64,
    mode: String,
) -> Result<serde_json::Value, String> {
    if let Err(code) = mode_body(id, &mode) {
        return bad(code);
    }
    let answer = get(
        &app,
        "/api/topics/preview",
        &[("id", id.to_string()), ("mode", mode)],
        Some("mode"),
    )
    .await?;
    Ok(hide_if_private(&app, answer))
}

/// The facts Jarvis sorted by guessing, ten at a time. A memory list: not
/// fetched at all while the private lists are hidden.
#[tauri::command]
pub async fn brain_topics_review(
    app: AppHandle,
    after: Option<String>,
    limit: Option<u32>,
) -> Result<serde_json::Value, String> {
    if words_hidden(&app) {
        return Ok(lists_hidden_answer());
    }
    let mut query: Vec<(&str, String)> = Vec::new();
    if let Some(a) = after.filter(|a| !a.is_empty()) {
        if !cursor_ok(&a) {
            return bad("bad_request");
        }
        query.push(("after", a));
    }
    let limit = limit.unwrap_or(10).clamp(1, REVIEW_LIMIT_MAX);
    query.push(("limit", limit.to_string()));
    get(&app, "/api/topics/review", &query, Some("facts")).await
}

/// One topic's facts ("Show them" on an Off topic). A memory list: not fetched
/// at all while the private lists are hidden.
#[tauri::command]
pub async fn brain_topics_hidden(
    app: AppHandle,
    id: i64,
    after: Option<i64>,
    limit: Option<u32>,
) -> Result<serde_json::Value, String> {
    if valid_id(Some(id)).is_err() {
        return bad("topic_not_found");
    }
    if words_hidden(&app) {
        return Ok(lists_hidden_answer());
    }
    let mut query: Vec<(&str, String)> = vec![("id", id.to_string())];
    if let Some(a) = after.filter(|a| *a >= 1) {
        query.push(("after", a.to_string()));
    }
    let limit = limit.unwrap_or(100).clamp(1, HIDDEN_LIMIT_MAX);
    query.push(("limit", limit.to_string()));
    get(&app, "/api/topics/hidden", &query, Some("facts")).await
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Made by `tools/gen_topics_cases.py`; the phone reads a byte-identical copy.
    const CASES: &str = include_str!("../../../tests/fixtures/topics-cases.json");

    fn cases() -> serde_json::Value {
        serde_json::from_str(CASES).expect("topics-cases.json is JSON")
    }

    fn edit(op: &str) -> TopicEdit {
        TopicEdit {
            op: op.into(),
            ..TopicEdit::default()
        }
    }

    #[test]
    fn the_words_and_lists_here_are_the_fixtures() {
        let doc = cases();
        assert_eq!(doc["words"]["missing"], TOPICS_MISSING);
        let modes: Vec<&str> = doc["modes"]
            .as_array()
            .unwrap()
            .iter()
            .map(|m| m["id"].as_str().unwrap())
            .collect();
        assert_eq!(modes, MODES);
        let icons: Vec<&str> = doc["icons"]
            .as_array()
            .unwrap()
            .iter()
            .map(|i| i.as_str().unwrap())
            .collect();
        assert_eq!(icons, ICONS);
        assert_eq!(doc["limits"]["name_max"], NAME_MAX);
        assert_eq!(doc["limits"]["words_max"], WORDS_MAX);
        assert_eq!(doc["limits"]["colours"], COLOURS);
        let errors = doc["errors"].as_object().unwrap();
        assert_eq!(errors.len(), ERRORS.len());
        for (code, sentence) in ERRORS {
            assert_eq!(errors[code], sentence, "{code}");
            assert_eq!(refusal(code)["message"], sentence, "{code}");
            assert_eq!(refusal(code)["ok"], false);
        }
    }

    #[test]
    fn a_name_is_tidied_like_the_pc_tidies_it() {
        for case in cases()["name_cases"].as_array().unwrap() {
            let raw = case["raw"].as_str().unwrap();
            let want = case["clean"].as_str().map(str::to_string);
            assert_eq!(clean_name(raw), want, "{raw:?}");
        }
        assert_eq!(clean_name("a\u{200b}b"), None);
    }

    #[test]
    fn keywords_are_cleaned_like_the_pc_cleans_them() {
        for case in cases()["words_cases"].as_array().unwrap() {
            let want = case["clean"].as_array().map(|a| {
                a.iter()
                    .map(|w| w.as_str().unwrap().to_string())
                    .collect::<Vec<_>>()
            });
            assert_eq!(clean_words(&case["raw"]), want, "{}", case["raw"]);
        }
        let many: Vec<String> = (0..21).map(|n| format!("word{n}")).collect();
        assert_eq!(clean_words(&serde_json::json!(many)), None);
    }

    #[test]
    fn every_edit_is_one_small_body_or_a_refusal() {
        let mut add = edit("add");
        add.name = Some("  Garden   plans ".into());
        add.colour = Some(3);
        add.icon = Some("leaf".into());
        add.words = Some(vec!["Boiler".into(), "boiler".into()]);
        assert_eq!(
            edit_body(&add).unwrap(),
            serde_json::json!({"op": "add", "name": "Garden plans", "colour": 3,
                               "icon": "leaf", "words": ["boiler"]})
        );
        add.colour = Some(8);
        assert_eq!(edit_body(&add), Err("bad_colour"));
        add.colour = None;
        add.icon = Some("skull".into());
        assert_eq!(edit_body(&add), Err("bad_icon"));
        add.icon = None;
        add.name = Some(String::new());
        assert_eq!(edit_body(&add), Err("bad_name"));

        let mut rename = edit("rename");
        rename.id = Some(4);
        rename.name = Some("Home".into());
        assert_eq!(
            edit_body(&rename).unwrap(),
            serde_json::json!({"op": "rename", "id": 4, "name": "Home"})
        );
        rename.id = Some(0);
        assert_eq!(edit_body(&rename), Err("topic_not_found"));

        let mut style = edit("style");
        style.id = Some(4);
        assert_eq!(edit_body(&style), Err("bad_request"));
        style.icon = Some("heart".into());
        assert_eq!(
            edit_body(&style).unwrap(),
            serde_json::json!({"op": "style", "id": 4, "icon": "heart"})
        );

        let mut mv = edit("move");
        mv.id = Some(4);
        assert_eq!(
            edit_body(&mv).unwrap(),
            serde_json::json!({"op": "move", "id": 4, "before": null})
        );
        mv.before = Some(2);
        assert_eq!(edit_body(&mv).unwrap()["before"], 2);

        let mut priv_ = edit("private");
        priv_.id = Some(4);
        assert_eq!(edit_body(&priv_), Err("bad_request"));
        priv_.private = Some(false);
        assert_eq!(edit_body(&priv_).unwrap()["private"], false);

        let mut words = edit("words");
        words.id = Some(4);
        assert_eq!(edit_body(&words), Err("bad_words"));
        words.words = Some(vec![]);
        assert_eq!(edit_body(&words).unwrap()["words"], serde_json::json!([]));

        assert_eq!(edit_body(&edit("nuke")), Err("bad_request"));
        assert_eq!(edit_body(&edit("")), Err("bad_request"));
    }

    #[test]
    fn a_delete_always_says_where_the_facts_go() {
        let mut del = edit("delete");
        del.id = Some(4);
        assert_eq!(edit_body(&del), Err("needs_destination"));
        del.move_to = Some(4);
        assert_eq!(edit_body(&del), Err("bad_destination"));
        del.move_to = Some(1);
        assert_eq!(
            edit_body(&del).unwrap(),
            serde_json::json!({"op": "delete", "id": 4, "move_to": 1})
        );
    }

    #[test]
    fn a_mode_is_one_of_the_four_and_nothing_else() {
        for m in MODES {
            assert_eq!(
                mode_body(3, m).unwrap(),
                serde_json::json!({"id": 3, "mode": m})
            );
        }
        assert_eq!(mode_body(3, "Off"), Err("bad_mode"));
        assert_eq!(mode_body(3, ""), Err("bad_mode"));
        assert_eq!(mode_body(0, "off"), Err("topic_not_found"));
    }

    #[test]
    fn filing_is_a_named_topic_or_a_confirm_never_a_bare_list() {
        assert_eq!(
            file_body(&[5, 6], Some(2), false).unwrap(),
            serde_json::json!({"ids": [5, 6], "topic_id": 2})
        );
        assert_eq!(
            file_body(&[5], None, true).unwrap(),
            serde_json::json!({"ids": [5], "confirm": true})
        );
        assert_eq!(file_body(&[5], Some(2), true), Err("bad_request"));
        assert_eq!(file_body(&[5], None, false), Err("topic_not_found"));
        assert_eq!(file_body(&[], Some(2), false), Err("bad_request"));
        assert_eq!(file_body(&[0], Some(2), false), Err("bad_request"));
        let many: Vec<i64> = (1..=201).collect();
        assert_eq!(file_body(&many, Some(2), false), Err("bad_request"));
        let just: Vec<i64> = (1..=200).collect();
        assert!(file_body(&just, Some(2), false).is_ok());
    }

    #[test]
    fn a_review_cursor_is_plain_or_refused() {
        assert!(cursor_ok("3:41"));
        assert!(cursor_ok("abc_DEF-1.2"));
        for odd in ["", "a b", "../x", "a&b=1", "é", &"x".repeat(65)] {
            assert!(!cursor_ok(odd), "{odd:?}");
        }
    }

    #[test]
    fn a_card_waiting_is_an_answer_and_a_refusal_keeps_the_pcs_sentence() {
        let waiting = r#"{"ok": true, "waiting": true, "id": 3, "kind": "mode",
                          "message": "Waiting for your approval."}"#;
        let got = topics_answer(202, waiting, None).unwrap();
        assert_eq!(got["waiting"], true);
        assert_eq!(got["id"], 3);

        let view = r#"{"ok": true, "topics": [], "waiting": null, "last": null}"#;
        assert!(topics_answer(200, view, Some("topics")).is_ok());
        assert!(topics_answer(200, r#"{"ok": true}"#, Some("topics")).is_err());
        assert!(topics_answer(200, "not json", None).is_err());

        let refused = r#"{"ok": false, "error": "name_taken",
                          "message": "You already have a topic with that name."}"#;
        let got = topics_answer(409, refused, None).unwrap();
        assert_eq!(got["ok"], false);
        assert_eq!(got["error"], "name_taken");
        assert_eq!(got["message"], "You already have a topic with that name.");

        let unavailable = r#"{"ok": false, "error": "unavailable", "message": "x"}"#;
        assert_eq!(
            topics_answer(503, unavailable, None).unwrap()["error"],
            "unavailable"
        );

        // A bare 404 is a PC with no such route, never a success.
        for old in [(404, r#"{"error": "not found"}"#), (404, ""), (501, "{}")] {
            assert_eq!(
                topics_answer(old.0, old.1, None).unwrap_err(),
                TOPICS_MISSING
            );
        }
        assert!(topics_answer(500, "boom", None).is_err());
    }

    #[test]
    fn hidden_lists_keep_counts_and_modes_but_no_name_or_keyword() {
        let view = serde_json::json!({
            "ok": true, "id": 2, "facts": 230, "unchecked": 3,
            "topics": [
                {"id": 1, "system": true, "name": "Unsorted", "mode": "both", "facts": 5,
                 "words": [], "private": false},
                {"id": 2, "system": false, "name": "Work", "mode": "use_only", "facts": 41,
                 "words": ["standup", "boiler"], "private": false},
                {"id": 3, "system": false, "name": "Health", "mode": "off", "facts": 9,
                 "words": [], "private": true},
            ],
            "waiting": {"topic": 3, "kind": "mode"}, "last": null,
            "line": "12 things Jarvis knows about Work will be left out of answers.",
        });
        let hidden = redact_answer(view);
        let text = hidden.to_string();
        assert!(!text.contains("Work"), "{text}");
        assert!(!text.contains("Health"), "{text}");
        assert!(!text.contains("standup"), "{text}");
        assert_eq!(hidden["topics"][0]["name"], "Unsorted");
        assert_eq!(hidden["topics"][1]["name"], "");
        assert_eq!(hidden["topics"][1]["facts"], 41);
        assert_eq!(hidden["topics"][1]["mode"], "use_only");
        assert_eq!(hidden["topics"][2]["private"], true);
        assert_eq!(hidden["waiting"]["topic"], 3);
        assert_eq!(hidden["lists_hidden"], true);
        assert_eq!(hidden["line"], "");
        // A refusal has nothing to hide.
        let refusal = refusal("bad_name");
        assert_eq!(redact_answer(refusal.clone()), refusal);
    }

    #[test]
    fn the_two_fact_lists_answer_empty_when_hidden() {
        let a = lists_hidden_answer();
        assert_eq!(a["lists_hidden"], true);
        assert_eq!(a["facts"], serde_json::json!([]));
        assert_eq!(a["next"], serde_json::Value::Null);
    }
}
