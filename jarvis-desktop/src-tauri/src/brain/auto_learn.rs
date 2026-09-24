//! Automatic learning - the Brain's two switches and its "Saved
//! automatically" list (JARVIS-API.md section 19, "Automatic learning").
//!
//! The owner decided on 2026-09-24 that Jarvis learns automatically by
//! default: facts about the owner, from the owner's own words only, are
//! saved without a per-fact yes, and every one is listed with a one-tap
//! Forget. Four commands, each its own power, like the rest of brain.rs:
//!
//! * [`brain_memory_learning_status`] - `GET /api/memory/learning`: the
//!   learning switch, the two automatic-learning switches, and whether a
//!   card to turn either on is waiting. What the switches are drawn from.
//! * [`brain_memory_auto_list`] - `GET /api/memory/auto`, a page at a time,
//!   newest first. It carries the two switches' states too, which the page
//!   falls back to on a PC whose `GET /api/memory/learning` is missing.
//! * [`brain_memory_learning_auto`] - `POST /api/memory/learning/auto`,
//!   "Learn automatically".
//! * [`brain_memory_learning_sensitive`] - `POST
//!   /api/memory/learning/sensitive`, "Also remember sensitive topics
//!   automatically".
//!
//! Turning either switch ON only raises an approval card (tier `ask`) and is
//! held while the event stream is stale (rule 4), exactly like the learning
//! switch ([`super::brain_memory_learning`]). OFF is never held: it only
//! narrows what Jarvis does, and an off that refuses when the link is unwell
//! fails exactly when it is wanted.
//!
//! Forget on this list is the existing [`super::brain_memory_forget`] - one
//! fact per call, held on a stale link. There is no "forget all".
//!
//! "Windows Hello for memory lists and chat history" (lock.rs) covers this
//! list too: while the Brain's private lists are hidden it comes back with
//! its facts taken out (how many there were is kept). The two switches stay:
//! they say nothing about the owner. Here, in Rust, so a page script cannot
//! read round it.
//!
//! The answer-reading functions are plain functions of (status, body) so
//! their tests run without a Tauri app or a network.

use tauri::AppHandle;

use super::{require_link_live, READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

/// What the page says for a backend without automatic learning - the
/// phone's words. A switch refused by such a backend says it as the error.
pub(crate) const AUTO_MISSING: &str = "Your PC's Jarvis does not have automatic learning yet.";

/// A page of the list: 30 unless asked, never more than 100.
const DEFAULT_LIMIT: u32 = 30;
const MAX_LIMIT: u32 = 100;

/// `GET /api/memory/auto`'s path for one page. `before` is the `saved_at` of
/// the oldest fact already shown; it is written as the plain number the page
/// was given (Rust never writes an `f64` in exponent form), so paging
/// neither repeats nor skips one.
pub(crate) fn list_path(limit: Option<u32>, before: Option<f64>) -> Result<String, String> {
    let limit = limit.unwrap_or(DEFAULT_LIMIT).clamp(1, MAX_LIMIT);
    let mut path = format!("/api/memory/auto?limit={limit}");
    if let Some(b) = before {
        if !b.is_finite() || b <= 0.0 {
            return Err(format!("{b} is not a moment in time"));
        }
        path.push_str(&format!("&before={b}"));
    }
    Ok(path)
}

/// Which switch: the route each one posts to.
pub(crate) fn switch_path(which: Switch) -> &'static str {
    match which {
        Switch::Auto => "/api/memory/learning/auto",
        Switch::Sensitive => "/api/memory/learning/sensitive",
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Switch {
    Auto,
    Sensitive,
}

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// [`brain_memory_auto_list`]'s reading of the answer.
///
/// * 2xx with a `facts` list - passed on as it is.
/// * 404 - `{"available": false, "why": AUTO_MISSING}`: an older backend,
///   which the page says plainly rather than as an error.
/// * anything else - the backend's own sentence, or a plain line.
pub(crate) fn list_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("facts").is_some_and(|f| f.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 {
        return Ok(serde_json::json!({ "available": false, "why": AUTO_MISSING }));
    }
    Err(commands::backend_refusal(status, body))
}

/// [`brain_memory_learning_status`]'s reading of the answer.
///
/// * 2xx with a boolean `auto` - passed on as it is.
/// * 404 - `{"available": false}`: a PC without this route; the page then
///   reads the switches from the list instead (and says [`AUTO_MISSING`]
///   when that is missing too).
/// * anything else - the backend's own sentence, or a plain line.
pub(crate) fn status_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("auto").is_some_and(|a| a.is_boolean()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 {
        return Ok(serde_json::json!({ "available": false }));
    }
    Err(commands::backend_refusal(status, body))
}

/// A switch's reading. 200 (off, or on already) and 202 (`{"waiting":
/// true}` - a card was raised, it is NOT on yet) are both answers to show as
/// they are; a 404 is an older backend; a 503 (the tier is not `ask`), a 400
/// and anything else is the backend's own sentence.
pub(crate) fn switch_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body).ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 {
        return Err(AUTO_MISSING.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// The list with its facts taken out, for while the private lists are
/// hidden (lock.rs). The two switches stay: they say nothing about the
/// owner.
pub(crate) fn redact_list(mut list: serde_json::Value) -> serde_json::Value {
    if let Some(obj) = list.as_object_mut() {
        if let Some(serde_json::Value::Array(items)) = obj.get_mut("facts") {
            let count = items.len();
            items.clear();
            obj.insert("hidden".into(), serde_json::json!(true));
            obj.insert("hidden_count".into(), serde_json::json!(count));
        }
    }
    list
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

async fn set(app: &AppHandle, which: Switch, enabled: bool) -> Result<serde_json::Value, String> {
    // ON only raises a card, but it is raised against a switch this window
    // read from a link that may have stopped updating: held (rule 4). OFF is
    // never held.
    if enabled {
        require_link_live(app)?;
    }
    let base = commands::jarvis_base(app);
    let response = commands::jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}{}", switch_path(which)))
        .headers(commands::jarvis_headers(app)?)
        .json(&serde_json::json!({ "enabled": enabled }))
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    switch_answer(status, &text)
}

/// The switches: background learning, "Learn automatically", "Also remember
/// sensitive topics automatically", and whether a card to turn either of the
/// last two on is waiting (and how the last one ended). A read, and not
/// hidden with the memory lists: it says nothing about the owner.
#[tauri::command]
pub async fn brain_memory_learning_status(app: AppHandle) -> Result<serde_json::Value, String> {
    let (status, body) = get(&app, "/api/memory/learning").await?;
    status_answer(status, &body)
}

/// One page of the facts saved automatically that are still current, newest
/// first, with the two switches. `before`: the `saved_at` of the oldest one
/// already shown, for "Load older". Reads only.
#[tauri::command]
pub async fn brain_memory_auto_list(
    app: AppHandle,
    before: Option<f64>,
    limit: Option<u32>,
) -> Result<serde_json::Value, String> {
    let path = list_path(limit, before)?;
    let (status, body) = get(&app, &path).await?;
    let answer = list_answer(status, &body)?;
    Ok(if crate::lock::private_hidden(&app) {
        redact_list(answer)
    } else {
        answer
    })
}

/// "Learn automatically". ON raises one approval card and is held on a
/// stale link; OFF is immediate and never held.
#[tauri::command]
pub async fn brain_memory_learning_auto(
    app: AppHandle,
    enabled: bool,
) -> Result<serde_json::Value, String> {
    set(&app, Switch::Auto, enabled).await
}

/// "Also remember sensitive topics automatically". ON raises one approval
/// card and is held on a stale link; OFF is immediate and never held.
#[tauri::command]
pub async fn brain_memory_learning_sensitive(
    app: AppHandle,
    enabled: bool,
) -> Result<serde_json::Value, String> {
    set(&app, Switch::Sensitive, enabled).await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_page_is_asked_for_within_limits() {
        assert_eq!(list_path(None, None).unwrap(), "/api/memory/auto?limit=30");
        assert_eq!(
            list_path(Some(0), None).unwrap(),
            "/api/memory/auto?limit=1"
        );
        assert_eq!(
            list_path(Some(500), None).unwrap(),
            "/api/memory/auto?limit=100"
        );
        assert_eq!(
            list_path(Some(30), Some(1_790_000_300.0)).unwrap(),
            "/api/memory/auto?limit=30&before=1790000300"
        );
        // A fractional `saved_at` goes back exactly as it came, never
        // rounded into the next second.
        assert_eq!(
            list_path(None, Some(1_790_000_300.25)).unwrap(),
            "/api/memory/auto?limit=30&before=1790000300.25"
        );
        for bad in [f64::NAN, f64::INFINITY, 0.0, -5.0] {
            assert!(list_path(None, Some(bad)).is_err(), "{bad}");
        }
    }

    #[test]
    fn each_switch_posts_to_its_own_route() {
        assert_eq!(switch_path(Switch::Auto), "/api/memory/learning/auto");
        assert_eq!(
            switch_path(Switch::Sensitive),
            "/api/memory/learning/sensitive"
        );
    }

    #[test]
    fn the_switches_are_passed_on_and_a_missing_route_is_not_an_error() {
        let body = r#"{"enabled": true, "auto": true, "auto_sensitive": false,
            "auto_waiting": false, "sensitive_waiting": true,
            "auto_last": null, "sensitive_last": null}"#;
        let got = status_answer(200, body).unwrap();
        assert_eq!(got["auto"], true);
        assert_eq!(got["sensitive_waiting"], true);
        assert_eq!(status_answer(404, "").unwrap()["available"], false);
        // No `auto` switch in it: not this route's answer.
        assert!(status_answer(200, r#"{"enabled": true}"#).is_err());
        assert!(status_answer(500, "").is_err());
    }

    #[test]
    fn the_list_is_passed_on_and_an_older_backend_says_so() {
        let body = r#"{"auto": true, "auto_sensitive": false,
            "facts": [{"id": 12, "text": "Works on Jarvis.", "saved_at": 1790000300.5,
                       "provenance": "typed", "device": "desktop"}]}"#;
        let got = list_answer(200, body).unwrap();
        assert_eq!(got["facts"][0]["id"], 12);
        assert_eq!(got["auto"], true);
        let old = list_answer(404, "").unwrap();
        assert_eq!(old["available"], false);
        assert_eq!(old["why"], AUTO_MISSING);
        assert!(list_answer(200, r#"{"ok": true}"#).is_err());
        assert!(list_answer(200, "not json").is_err());
        assert_eq!(
            list_answer(500, r#"{"error": "the memory store is locked"}"#).unwrap_err(),
            "The memory store is locked"
        );
    }

    #[test]
    fn on_waits_off_is_done_and_a_refusal_is_the_servers_own_sentence() {
        let waiting =
            switch_answer(202, r#"{"ok": true, "waiting": true, "auto": false}"#).unwrap();
        assert_eq!(waiting["waiting"], true);
        let off = switch_answer(200, r#"{"ok": true, "auto": false}"#).unwrap();
        assert_eq!(off["auto"], false);
        assert_eq!(
            switch_answer(
                503,
                r#"{"error": "learning_auto_enable is not set to ask in jarvis-framework.toml"}"#
            )
            .unwrap_err(),
            "Learning_auto_enable is not set to ask in jarvis-framework.toml"
        );
        assert_eq!(switch_answer(404, "").unwrap_err(), AUTO_MISSING);
        assert!(switch_answer(400, r#"{"error": "need {\"enabled\": true|false}"}"#).is_err());
    }

    #[test]
    fn hidden_lists_keep_the_count_and_the_switches_but_no_fact() {
        let list = serde_json::json!({
            "auto": true, "auto_sensitive": false,
            "facts": [{"id": 1, "text": "Sees Dr Patel on Tuesdays"}, {"id": 2, "text": "x"}]
        });
        let hidden = redact_list(list);
        assert_eq!(hidden["facts"], serde_json::json!([]));
        assert_eq!(hidden["hidden"], true);
        assert_eq!(hidden["hidden_count"], 2);
        assert_eq!(hidden["auto"], true);
        assert!(!hidden.to_string().contains("Patel"));
    }
}
