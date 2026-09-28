//! "Widgets you describe" (the owner's choice of 2026-09-28, the SAFE
//! version; backend `jarvis_widgets.py`; JARVIS-API.md section 86).
//!
//! A widget is a small CHECKED DESCRIPTION the PC keeps - a heading, a
//! number, a list, a bar and up to four buttons from a fixed menu - never
//! code. The PC's AI model only turns the owner's words into that
//! description, and the PC checks it with plain code before anyone sees it.
//!
//! The Brain (Work tab, "Widgets") manages them:
//!
//! * [`brain_widgets`] - `GET /api/widgets`: the saved widgets, the previews
//!   waiting for Add, and the menu. A read. While "Windows Hello for memory
//!   lists and chat history" hides the private lists, the names, headings
//!   and sentences are taken out here, in Rust.
//! * [`brain_widgets_draft`] - `POST /api/widgets/draft {"words",
//!   "provenance"}`: a PREVIEW from the owner's own typed words. The page
//!   says whether the words were pasted into the box; pasted words are sent
//!   as `"pasted"`, which the PC refuses (only the owner's own typed or
//!   spoken words make a widget). Not held on a stale link: it adds nothing.
//! * [`brain_widgets_add`] - `POST /api/widgets/add {"draft"}`: keep a
//!   preview exactly as shown. No approval card (the PC's `no_card` says
//!   why). Held on a stale link, like every change.
//! * [`brain_widgets_discard`] - drop a preview. Not held: it only drops.
//! * [`brain_widgets_delete`] - `POST /api/widgets/delete {"id"}`: at once,
//!   no "are you sure?", ONE widget. Held on a stale link, like Coming up's
//!   Delete.
//!
//! The desktop widget window draws one of them in place of the face - the
//! same window, no new webview, and only two more commands for it:
//!
//! * [`widget_board`] - the saved widgets' names, and the chosen one filled
//!   in now (`GET /api/widgets/show?id=`). While App lock is on or the
//!   private lists are hidden, every private block loses its words HERE
//!   ([`redact_show`]): a desktop is as public as the phone's home screen.
//! * [`widget_board_action`] - ONE button: exactly the five safe actions of
//!   the phone's Quick Settings tiles ([`ACTIONS`]), matched on a closed
//!   list in Rust - never Approve or Deny, never a route or body from the
//!   page. Stop everything is never held; Brief me only opens the Brain
//!   (behind App lock); the timer, focus and play/pause are held on a stale
//!   link (rule 4).
//!
//! The answer-reading functions are plain functions so their tests run
//! without a Tauri app or a network.

use std::time::Duration;

use tauri::AppHandle;

use super::{require_link_live, READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

/// The model gets 40 seconds on the PC (`jarvis_widgets.MODEL_TIMEOUT`);
/// this waits a little longer so its own sentence arrives.
const DRAFT_TIMEOUT: Duration = Duration::from_secs(60);

/// A PC without the routes (the phone says the same, `JarvisWidgets.MISSING`).
pub(crate) const WIDGETS_MISSING: &str =
    "Your PC's Jarvis cannot make widgets yet - run apply-patches.ps1 on the PC.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// The longest description the PC takes (`jarvis_widgets.MAX_WORDS`).
pub(crate) const MAX_WORDS: usize = 300;

/// What a private block says while its words are hidden
/// (`jarvis_widgets.PRIVATE_HIDDEN`).
pub(crate) const PRIVATE_HIDDEN: &str = "Hidden - open Jarvis to see it.";

/// The five buttons: the phone's Quick Settings tile actions, the same wire
/// names and words. Nothing else can be pressed from a widget.
pub(crate) const ACTIONS: &[(&str, &str)] = &[
    ("focus", "Focus session"),
    ("timer", "10-min timer"),
    ("brief_me", "Brief me"),
    ("stop_everything", "Stop everything"),
    ("pc_play_pause", "Play/pause PC"),
];

/// The sources whose words are the owner's own (or another program's).
pub(crate) const PRIVATE_SOURCES: &[&str] =
    &["now_playing", "reminders", "timers", "today", "todo"];

/// The timer button's words - the phone's `QuickTiles.TIMER_SET`.
pub(crate) const TIMER_SET: &str = "10-minute timer set on your PC.";
/// The focus button's length - the Focus session's own default.
const FOCUS_MINUTES: u32 = 25;

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

/// A saved widget's id as the PC makes them: "w" and ten hex digits.
pub(crate) fn valid_id(id: &str) -> bool {
    valid_tagged(id, 'w')
}

/// A preview's id: "d" and ten hex digits.
pub(crate) fn valid_draft(id: &str) -> bool {
    valid_tagged(id, 'd')
}

fn valid_tagged(id: &str, tag: char) -> bool {
    id.len() == 11
        && id.starts_with(tag)
        && id[1..]
            .chars()
            .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
}

/// The list's reading.
pub(crate) fn list_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("widgets").is_some_and(|w| w.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 || status == 501 {
        return Ok(serde_json::json!({ "available": false, "why": WIDGETS_MISSING }));
    }
    Err(commands::backend_refusal(status, body))
}

/// A POST's reading: the PC's own answer, or its own sentence when it
/// refused (`{"ok": false, "error"}`), or "update the PC" for a PC without
/// the route.
pub(crate) fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    let got = parsed(body);
    if (200..300).contains(&status) {
        return got.ok_or_else(|| UNREADABLE.to_string());
    }
    if let Some(error) = got
        .as_ref()
        .filter(|v| v.get("ok") == Some(&serde_json::Value::Bool(false)))
        .and_then(|v| v.get("error"))
        .and_then(|e| e.as_str())
    {
        return Err(error.to_string());
    }
    if status == 404 || status == 501 {
        return Err(WIDGETS_MISSING.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// The draft's body. The page says only whether the words were pasted;
/// "typed" or "pasted" is decided here, never taken from the page.
pub(crate) fn draft_body(words: &str, pasted: bool) -> Result<serde_json::Value, String> {
    let words = words.split_whitespace().collect::<Vec<_>>().join(" ");
    if words.is_empty() {
        return Err(
            "Say what the widget should show - for example, your next 3 reminders and a \
             timer button."
                .to_string(),
        );
    }
    if words.chars().count() > MAX_WORDS {
        return Err(format!(
            "That is too long for a widget. Keep it under {MAX_WORDS} characters."
        ));
    }
    Ok(serde_json::json!({
        "words": words,
        "provenance": if pasted { "pasted" } else { "typed" },
    }))
}

/// The list with the owner's words taken out, for while the private lists
/// are hidden: names, headings, sentences and parts go; ids, kinds and the
/// menu stay, so Delete still works.
pub(crate) fn redact_list(mut list: serde_json::Value) -> serde_json::Value {
    if let Some(obj) = list.as_object_mut() {
        for key in ["widgets", "drafts"] {
            if let Some(serde_json::Value::Array(items)) = obj.get_mut(key) {
                for item in items.iter_mut() {
                    if let Some(o) = item.as_object_mut() {
                        o.insert("name".into(), serde_json::json!(""));
                        o.insert("said".into(), serde_json::json!(""));
                        o.insert("parts".into(), serde_json::json!([]));
                        o.insert("hidden".into(), serde_json::json!(true));
                        if let Some(serde_json::Value::Array(blocks)) = o.get_mut("blocks") {
                            blank_blocks(blocks);
                        }
                    }
                }
            }
        }
        obj.insert("hidden".into(), serde_json::json!(true));
    }
    list
}

fn blank_blocks(blocks: &mut [serde_json::Value]) {
    for b in blocks.iter_mut() {
        if let Some(o) = b.as_object_mut() {
            if o.contains_key("text") {
                o.insert("text".into(), serde_json::json!(""));
            }
            if o.contains_key("label") {
                o.insert("label".into(), serde_json::json!(""));
            }
        }
    }
}

/// Is this block's source private? The PC's flag, OR one of
/// [`PRIVATE_SOURCES`], OR a source this app does not know (a newer PC):
/// fails closed.
fn block_private(o: &serde_json::Map<String, serde_json::Value>) -> bool {
    let source = o.get("source").and_then(|s| s.as_str()).unwrap_or("");
    let known = PRIVATE_SOURCES.contains(&source)
        || [
            "disk_free",
            "email_count",
            "events_count",
            "focus",
            "reminders_count",
            "todo_count",
        ]
        .contains(&source);
    o.get("private") != Some(&serde_json::Value::Bool(false))
        || !known
        || PRIVATE_SOURCES.contains(&source)
}

/// One widget, filled in, with every private block's words taken out -
/// for while App lock is on or the private lists are hidden. A title keeps
/// its words only when nothing is hidden (it is the owner's own words too).
pub(crate) fn redact_show(mut shown: serde_json::Value) -> serde_json::Value {
    if let Some(obj) = shown.as_object_mut() {
        obj.insert("name".into(), serde_json::json!(""));
        if let Some(serde_json::Value::Array(blocks)) = obj.get_mut("blocks") {
            for b in blocks.iter_mut() {
                let Some(o) = b.as_object_mut() else { continue };
                let kind = o.get("type").and_then(|t| t.as_str()).unwrap_or("");
                match kind {
                    "title" => {
                        o.insert("text".into(), serde_json::json!(""));
                    }
                    "number" | "list" | "progress" if block_private(o) => {
                        o.insert("items".into(), serde_json::json!([]));
                        o.insert("more".into(), serde_json::json!(0));
                        o.insert("value".into(), serde_json::json!(""));
                        o.insert("fraction".into(), serde_json::json!(0.0));
                        o.insert("note".into(), serde_json::json!(PRIVATE_HIDDEN));
                        o.insert("private".into(), serde_json::json!(true));
                        o.insert("hidden".into(), serde_json::json!(true));
                    }
                    _ => {}
                }
            }
        }
        obj.insert("hidden".into(), serde_json::json!(true));
    }
    shown
}

/// The widget window's picker: only ids and names (names blanked while
/// hidden).
pub(crate) fn board_names(list: &serde_json::Value, hidden: bool) -> serde_json::Value {
    let items: Vec<serde_json::Value> = list
        .get("widgets")
        .and_then(|w| w.as_array())
        .map(|w| {
            w.iter()
                .filter_map(|x| {
                    let id = x.get("id").and_then(|i| i.as_str())?;
                    if !valid_id(id) {
                        return None;
                    }
                    let name = if hidden {
                        ""
                    } else {
                        x.get("name").and_then(|n| n.as_str()).unwrap_or("")
                    };
                    Some(serde_json::json!({ "id": id, "name": name }))
                })
                .collect()
        })
        .unwrap_or_default();
    serde_json::Value::Array(items)
}

/// Play when nothing is playing (or the PC could not say), pause when it
/// says "Playing: ..." - the phone's `QuickTiles.playPauseAction`.
pub(crate) fn play_pause_action(said: Option<&str>) -> &'static str {
    if said.is_some_and(|s| s.trim_start().starts_with("Playing:")) {
        "pause"
    } else {
        "play"
    }
}

/// One button, matched on the closed list. `None` for anything else.
pub(crate) fn action_of(action: &str) -> Option<&'static str> {
    ACTIONS
        .iter()
        .find(|(id, _)| *id == action)
        .map(|(id, _)| *id)
}

/// Whether a button waits for a live link (rule 4): everything but Stop
/// everything (it only stops) and Brief me (it only opens the Brain).
pub(crate) fn held_when_stale(action: &str) -> bool {
    !matches!(action, "stop_everything" | "brief_me")
}

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
    Ok((status, response.text().await.unwrap_or_default()))
}

/// The saved widgets, the previews and the menu. A read.
#[tauri::command]
pub async fn brain_widgets(app: AppHandle) -> Result<serde_json::Value, String> {
    let (status, body) = get(&app, "/api/widgets").await?;
    let answer = list_answer(status, &body)?;
    Ok(
        if crate::lock::private_hidden(&app) && answer.get("available") != Some(&false.into()) {
            redact_list(answer)
        } else {
            answer
        },
    )
}

/// A preview from the owner's own typed words. Adds nothing.
#[tauri::command]
pub async fn brain_widgets_draft(
    app: AppHandle,
    words: String,
    pasted: bool,
) -> Result<serde_json::Value, String> {
    let body = draft_body(&words, pasted)?;
    let (status, text) = post(&app, "/api/widgets/draft", body, DRAFT_TIMEOUT).await?;
    change_answer(status, &text)
}

/// Keep ONE preview, exactly as shown. Held on a stale link.
#[tauri::command]
pub async fn brain_widgets_add(app: AppHandle, draft: String) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    if !valid_draft(&draft) {
        return Err("That preview has expired or was already used.".to_string());
    }
    let (status, text) = post(
        &app,
        "/api/widgets/add",
        serde_json::json!({ "draft": draft }),
        WRITE_TIMEOUT,
    )
    .await?;
    change_answer(status, &text)
}

/// Drop ONE preview. Not held: it only drops.
#[tauri::command]
pub async fn brain_widgets_discard(
    app: AppHandle,
    draft: String,
) -> Result<serde_json::Value, String> {
    if !valid_draft(&draft) {
        return Ok(serde_json::json!({ "ok": true }));
    }
    let (status, text) = post(
        &app,
        "/api/widgets/discard",
        serde_json::json!({ "draft": draft }),
        WRITE_TIMEOUT,
    )
    .await?;
    change_answer(status, &text)
}

/// Delete ONE widget, at once. Held on a stale link.
#[tauri::command]
pub async fn brain_widgets_delete(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    if !valid_id(&id) {
        return Err("That widget is not there any more.".to_string());
    }
    let (status, text) = post(
        &app,
        "/api/widgets/delete",
        serde_json::json!({ "id": id }),
        WRITE_TIMEOUT,
    )
    .await?;
    change_answer(status, &text)
}

/// The widget window: the saved widgets' names, and the chosen one filled
/// in now. A read. Private words are taken out while App lock is on or the
/// private lists are hidden.
#[tauri::command]
pub async fn widget_board(app: AppHandle, id: Option<String>) -> Result<serde_json::Value, String> {
    let hidden = crate::lock::current(&app).app_lock || crate::lock::private_hidden(&app);
    let (status, body) = get(&app, "/api/widgets").await?;
    let list = list_answer(status, &body)?;
    if list.get("available") == Some(&false.into()) {
        return Ok(list);
    }
    let names = board_names(&list, hidden);
    let chosen = id.filter(|i| valid_id(i));
    let shown = match chosen {
        Some(wid) => {
            let (status, body) = get(&app, &format!("/api/widgets/show?id={wid}")).await?;
            if (200..300).contains(&status) {
                let v = parsed(&body).ok_or_else(|| UNREADABLE.to_string())?;
                if hidden {
                    redact_show(v)
                } else {
                    v
                }
            } else {
                // Deleted since, most likely: the window goes back to the face.
                serde_json::Value::Null
            }
        }
        None => serde_json::Value::Null,
    };
    Ok(serde_json::json!({
        "available": true,
        "widgets": names,
        "shown": shown,
        "hidden": hidden,
    }))
}

/// ONE button from the widget window, on the closed list. Answers the
/// sentence to show.
#[tauri::command]
pub async fn widget_board_action(app: AppHandle, action: String) -> Result<String, String> {
    let Some(action) = action_of(&action) else {
        return Err("A widget can only use its own small buttons.".to_string());
    };
    if held_when_stale(action) {
        require_link_live(&app)?;
    }
    match action {
        "stop_everything" => {
            commands::stop_everything_now(&app);
            Ok("Stop everything sent.".to_string())
        }
        "brief_me" => {
            crate::windows::show_brain(&app)?;
            Ok("Opening the Brain - your briefing is on the Work tab.".to_string())
        }
        "timer" => {
            let (status, text) = post(
                &app,
                "/api/schedule/add",
                serde_json::json!({ "kind": "timer", "seconds": 600 }),
                WRITE_TIMEOUT,
            )
            .await?;
            super::schedule::change_answer(status, &text)?;
            Ok(TIMER_SET.to_string())
        }
        "focus" => {
            let body = super::focus::start_body(FOCUS_MINUTES, "")?;
            let (status, text) = post(&app, "/api/focus/start", body, WRITE_TIMEOUT).await?;
            let v = super::focus::change_answer(status, &text)?;
            Ok(v.get("said")
                .and_then(|s| s.as_str())
                .unwrap_or("Focus session started.")
                .to_string())
        }
        "pc_play_pause" => {
            let (status, text) = get(&app, "/api/media").await?;
            let said = parsed(&text)
                .filter(|_| (200..300).contains(&status))
                .and_then(|v| v.get("said").and_then(|s| s.as_str()).map(str::to_string));
            let next = play_pause_action(said.as_deref());
            let (status, text) = post(
                &app,
                "/api/media/control",
                serde_json::json!({ "action": next }),
                WRITE_TIMEOUT,
            )
            .await?;
            if status == 404 || status == 501 {
                return Err(
                    "Your PC's Jarvis cannot control music yet - run apply-patches.ps1 on the PC."
                        .to_string(),
                );
            }
            // The PC answers its own sentence on a 200 and on a 503
            // ("Nothing seems to be playing right now.").
            Ok(parsed(&text)
                .and_then(|v| v.get("said").and_then(|s| s.as_str()).map(str::to_string))
                .unwrap_or_else(|| "Done.".to_string()))
        }
        _ => Err("A widget can only use its own small buttons.".to_string()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_the_five_tile_actions() {
        for a in [
            "focus",
            "timer",
            "brief_me",
            "stop_everything",
            "pc_play_pause",
        ] {
            assert_eq!(action_of(a), Some(a));
        }
        for bad in [
            "approve",
            "deny",
            "approve_all",
            "clear_latch",
            "",
            "Timer",
            " timer",
        ] {
            assert_eq!(action_of(bad), None);
        }
        assert!(!held_when_stale("stop_everything"));
        assert!(!held_when_stale("brief_me"));
        assert!(held_when_stale("timer") && held_when_stale("focus"));
        assert!(held_when_stale("pc_play_pause"));
    }

    #[test]
    fn ids_are_checked() {
        assert!(valid_id("w0123456789"));
        assert!(!valid_id("d0123456789"));
        assert!(!valid_id("w012345678Z"));
        assert!(!valid_id("../../x"));
        assert!(valid_draft("dabcdef0123"));
        assert!(!valid_draft("wabcdef0123"));
    }

    #[test]
    fn the_draft_body_decides_provenance_here() {
        let b = draft_body("  my   next reminders ", false).unwrap();
        assert_eq!(b["words"], "my next reminders");
        assert_eq!(b["provenance"], "typed");
        assert_eq!(draft_body("x", true).unwrap()["provenance"], "pasted");
        assert!(draft_body("   ", false).is_err());
        assert!(draft_body(&"x".repeat(MAX_WORDS + 1), false).is_err());
    }

    #[test]
    fn private_words_are_taken_out() {
        let shown = serde_json::json!({"ok": true, "name": "Morning", "blocks": [
            {"type": "title", "text": "Hi"},
            {"type": "list", "source": "reminders", "private": true,
             "items": [{"text": "call mum", "when": "12:00"}]},
            {"type": "number", "source": "todo_count", "private": false, "value": "3"},
            {"type": "number", "source": "brand_new", "private": false, "value": "9"},
            {"type": "button", "action": "timer", "label": "10-min timer"}]});
        let r = redact_show(shown);
        let text = r.to_string();
        assert!(
            !text.contains("call mum") && !text.contains("Morning") && !text.contains("\"Hi\"")
        );
        assert_eq!(r["blocks"][2]["value"], "3");
        assert_eq!(r["blocks"][3]["value"], "");
        assert_eq!(r["blocks"][1]["note"], PRIVATE_HIDDEN);
        assert_eq!(r["blocks"][4]["label"], "10-min timer");
    }

    #[test]
    fn the_list_hides_names_but_keeps_ids() {
        let list = serde_json::json!({"widgets": [
            {"id": "w0123456789", "name": "Morning", "said": "A widget", "parts": ["Heading: Hi"],
             "blocks": [{"type": "title", "text": "Hi"}]}], "drafts": []});
        let r = redact_list(list.clone());
        assert!(!r.to_string().contains("Morning") && !r.to_string().contains("Hi"));
        assert_eq!(r["widgets"][0]["id"], "w0123456789");
        assert_eq!(board_names(&list, true)[0]["name"], "");
        assert_eq!(board_names(&list, false)[0]["name"], "Morning");
    }

    #[test]
    fn answers_are_read_in_the_pcs_own_words() {
        assert_eq!(
            change_answer(
                409,
                r#"{"ok": false, "error": "You already have 12 widgets."}"#
            ),
            Err("You already have 12 widgets.".to_string())
        );
        assert_eq!(change_answer(404, "{}"), Err(WIDGETS_MISSING.to_string()));
        assert_eq!(
            list_answer(404, "").unwrap().get("available"),
            Some(&false.into())
        );
        assert_eq!(play_pause_action(Some("Playing: “x”.")), "pause");
        assert_eq!(play_pause_action(Some("Paused: “x”.")), "play");
        assert_eq!(play_pause_action(None), "play");
    }
}
