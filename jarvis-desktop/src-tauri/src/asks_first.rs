//! Settings -> "What asks first" (the owner's decisions of 2026-09-26, after
//! the approvals audit; backend/asks-first.patch, jarvis_asks_first.py;
//! JARVIS-API.md section 32).
//!
//! Three commands, settings window only (permissions/surfaces.toml,
//! `settings-surface`):
//!
//! * [`get_asks_first`] - `GET /api/asks_first`: every action Jarvis can take
//!   and whether it asks first, in the PC's own words, grouped; which ones
//!   the apps may switch; whether this request may loosen (the PC decides:
//!   only a request from the PC itself); a waiting card; the lights setting.
//!   A read, never held.
//! * [`set_asks_first`] - `POST /api/asks_first/tier {"action", "ask"}` for
//!   ONE action on the short safe list ([`SWITCHABLE`]). `ask: true` makes
//!   it stricter - at once, never a card, and never held on a stale link: it
//!   only makes Jarvis ask more. `ask: false` loosens it - the PC raises ONE
//!   approval card that needs Windows Hello on the PC - so it is held on a
//!   stale link (rule 4). An action off the list is refused HERE too, before
//!   anything is sent; the PC refuses it as well.
//! * [`set_lights_without_card`] - `POST /api/asks_first/lights
//!   {"enabled"}`: "Lights, plugs and fans without a card". OFF at once,
//!   never held; ON raises ONE approval card on the PC, so it is held on a
//!   stale link - the shape of every setting that trusts more.
//! * [`set_tool_enabled`] - `POST /api/asks_first/tools {"tool", "enabled"}`
//!   (the owner's answer of 2026-09-27): whether the AI model is offered
//!   ONE of the four reading tools ([`TOOLS_SWITCHABLE`]) AT ALL - a
//!   DIFFERENT thing from [`set_asks_first`], which is whether an offered
//!   tool asks first. `enabled: true` is the PC only, one approval card
//!   that needs Windows Hello, so it is held on a stale link; `enabled:
//!   false` is at once, never held, from either app. A tool off the list is
//!   refused HERE too, before anything is sent; the PC refuses it as well.
//!   Desktop only (CLAUDE.md: no deep config editing on the phone).

use std::time::Duration;

use tauri::{AppHandle, Manager};

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

pub(crate) const ASKS_FIRST_PATH: &str = "/api/asks_first";
const TIER_PATH: &str = "/api/asks_first/tier";
const LIGHTS_PATH: &str = "/api/asks_first/lights";
const TOOLS_PATH: &str = "/api/asks_first/tools";

/// The actions the apps may switch - `jarvis_asks_first.SWITCHABLE`, word for
/// word (tests/fixtures/asks-first-cases.json checks it).
pub(crate) const SWITCHABLE: [&str; 7] = [
    "calendar_read",
    "email_read",
    "notes_search",
    "home_read",
    "append_obsidian_daily",
    "append_logseq_journal",
    "create_joplin_note",
];

/// The four reading tools that may be OFFERED to the AI model at all from
/// this app - `jarvis_asks_first.TOOLS_SWITCHABLE`, word for word. A
/// DIFFERENT list from [`SWITCHABLE`], and desktop only.
pub(crate) const TOOLS_SWITCHABLE: [&str; 4] =
    ["calendar_read", "email_read", "notes_search", "home_read"];

/// What a backend without `jarvis_asks_first.py` is told. The phone says
/// the same (`AsksFirst.MISSING`), and so does the PC.
pub(crate) const ASKS_FIRST_MISSING: &str = "Your PC's Jarvis cannot show what asks first yet - \
     run apply-patches.ps1 on the PC.";

/// An action off the list - `jarvis_asks_first.NOT_ON_LIST`, word for word.
pub(crate) const NOT_ON_LIST: &str = "Only reading your calendar, email, notes and home \
     status, and adding to your notes, can be changed from an app. Everything else changes \
     only in your settings file (jarvis-framework.toml), and some things always ask.";

/// A tool off [`TOOLS_SWITCHABLE`] - `jarvis_asks_first.TOOLS_NOT_ON_LIST`,
/// word for word.
pub(crate) const TOOLS_NOT_ON_LIST: &str = "Only reading your calendar, email, notes and home \
     status can be offered to the AI model from an app. Every other tool changes only in your \
     settings file (jarvis-framework.toml, [tools].enabled).";

const STALE: &str =
    "The connection to Jarvis is catching up, so nothing can be sent until it does.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);
const WRITE_TIMEOUT: Duration = Duration::from_secs(20);

fn missing(code: u16, body: &str) -> bool {
    code == 404
        || (code == 503
            && serde_json::from_str::<serde_json::Value>(body)
                .ok()
                .and_then(|v| v.get("available").and_then(|a| a.as_bool()))
                == Some(false))
}

/// [`get_asks_first`]'s reading of the answer, tested against the contract
/// file (the real `view()`).
pub(crate) fn asks_first_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("groups").is_some_and(|g| g.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "why": ASKS_FIRST_MISSING }));
    }
    Err(backend_refusal(status, body))
}

/// The body of one switch, or why not: only an action on [`SWITCHABLE`].
pub(crate) fn tier_body(action: &str, ask: bool) -> Result<serde_json::Value, String> {
    if !SWITCHABLE.contains(&action) {
        return Err(NOT_ON_LIST.to_string());
    }
    Ok(serde_json::json!({ "action": action, "ask": ask }))
}

/// The body of one "offer this to the AI model" switch, or why not: only a
/// tool on [`TOOLS_SWITCHABLE`].
pub(crate) fn tool_body(tool: &str, enabled: bool) -> Result<serde_json::Value, String> {
    if !TOOLS_SWITCHABLE.contains(&tool) {
        return Err(TOOLS_NOT_ON_LIST.to_string());
    }
    Ok(serde_json::json!({ "tool": tool, "enabled": enabled }))
}

/// Whether a change is held while the event stream is stale: loosening
/// (a card) and turning the lights setting on (a card) are; making
/// something stricter, and turning the lights setting off, never are.
pub(crate) fn held_on_stale(loosens: bool) -> bool {
    loosens
}

/// A change's answer: the PC's own body on a 2xx (200 done, 202 a card is
/// up), [`ASKS_FIRST_MISSING`] from a PC without the route, and the PC's
/// own sentence otherwise (403 "the PC only", 409, 503).
pub(crate) fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.is_object())
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Err(ASKS_FIRST_MISSING.to_string());
    }
    Err(backend_refusal(status, body))
}

/// Every action and whether it asks first: `GET /api/asks_first`. A read.
#[tauri::command]
pub async fn get_asks_first(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{ASKS_FIRST_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    asks_first_answer(status, &body)
}

async fn post(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let base = jarvis_base(app);
    let response = jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}{path}"))
        .headers(jarvis_headers(app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    change_answer(status, &text)
}

fn stale(app: &AppHandle) -> bool {
    app.state::<crate::stream::StreamState>().link().stale
}

/// "Ask me first" on ONE action of the short safe list. Stricter at once and
/// never held; looser raises one card (Windows Hello on the PC) and is held
/// on a stale link.
#[tauri::command]
pub async fn set_asks_first(
    app: AppHandle,
    action: String,
    ask: bool,
) -> Result<serde_json::Value, String> {
    let body = tier_body(&action, ask)?;
    if held_on_stale(!ask) && stale(&app) {
        return Err(STALE.to_string());
    }
    post(&app, TIER_PATH, body).await
}

/// "Lights, plugs and fans without a card": OFF at once, never held; ON
/// raises ONE approval card on the PC, so it is held on a stale link.
#[tauri::command]
pub async fn set_lights_without_card(
    app: AppHandle,
    enabled: bool,
) -> Result<serde_json::Value, String> {
    if held_on_stale(enabled) && stale(&app) {
        return Err(STALE.to_string());
    }
    post(&app, LIGHTS_PATH, serde_json::json!({ "enabled": enabled })).await
}

/// Offer ONE reading tool to the AI model at all, or stop offering it - a
/// DIFFERENT thing from [`set_asks_first`] (whether the AI model is offered
/// the tool at all, not whether it asks first once offered). `enabled: true`
/// raises ONE approval card that needs Windows Hello on the PC, so it is
/// held on a stale link; `enabled: false` is at once, never held.
#[tauri::command]
pub async fn set_tool_enabled(
    app: AppHandle,
    tool: String,
    enabled: bool,
) -> Result<serde_json::Value, String> {
    let body = tool_body(&tool, enabled)?;
    if held_on_stale(enabled) && stale(&app) {
        return Err(STALE.to_string());
    }
    post(&app, TOOLS_PATH, body).await
}

#[cfg(test)]
mod tests {
    use super::{
        asks_first_answer, change_answer, held_on_stale, tier_body, tool_body, ASKS_FIRST_MISSING,
        NOT_ON_LIST, SWITCHABLE, TOOLS_NOT_ON_LIST, TOOLS_SWITCHABLE,
    };

    /// The real answers, made by `tools/gen_asks_first_cases.py`.
    const CASES: &str = include_str!("../../tests/fixtures/asks-first-cases.json");

    #[test]
    fn every_real_view_is_passed_on_unchanged_and_the_words_match() {
        let doc: serde_json::Value = serde_json::from_str(CASES).expect("asks-first-cases.json");
        for (name, view) in doc["cases"].as_object().expect("cases") {
            let got =
                asks_first_answer(200, &view.to_string()).unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(&got, view, "{name}");
        }
        let list: Vec<&str> = doc["switchable"]
            .as_array()
            .unwrap()
            .iter()
            .map(|x| x.as_str().unwrap())
            .collect();
        assert_eq!(list, SWITCHABLE.to_vec());
        let tools_list: Vec<&str> = doc["tools_switchable"]
            .as_array()
            .unwrap()
            .iter()
            .map(|x| x.as_str().unwrap())
            .collect();
        assert_eq!(tools_list, TOOLS_SWITCHABLE.to_vec());
        assert_eq!(
            doc["words"]["missing"].as_str().unwrap(),
            ASKS_FIRST_MISSING
        );
        assert_eq!(doc["words"]["not_on_list"].as_str().unwrap(), NOT_ON_LIST);
        assert_eq!(
            doc["words"]["tools_not_on_list"].as_str().unwrap(),
            TOOLS_NOT_ON_LIST
        );
    }

    #[test]
    fn only_the_four_reading_tools_can_be_offered_and_only_on_is_held() {
        for t in TOOLS_SWITCHABLE {
            assert!(tool_body(t, false).is_ok());
            assert!(tool_body(t, true).is_ok());
        }
        for t in ["send_email", "home_control", "browser_control", ""] {
            assert_eq!(tool_body(t, false).unwrap_err(), TOOLS_NOT_ON_LIST);
        }
        assert!(held_on_stale(true));
        assert!(!held_on_stale(false));
    }

    #[test]
    fn only_the_short_list_is_sent_and_only_loosening_is_held() {
        for a in SWITCHABLE {
            assert!(tier_body(a, false).is_ok());
            assert!(tier_body(a, true).is_ok());
        }
        for a in [
            "send_email",
            "home_control",
            "wiki_update",
            "loosen_what_asks_first",
            "",
        ] {
            assert_eq!(tier_body(a, false).unwrap_err(), NOT_ON_LIST);
        }
        assert!(held_on_stale(true));
        assert!(!held_on_stale(false));
    }

    #[test]
    fn an_older_pc_says_so_and_a_refusal_is_the_pcs_own_sentence() {
        for code in [404u16, 503] {
            let got = asks_first_answer(code, r#"{"available": false}"#).unwrap();
            assert_eq!(got["why"], ASKS_FIRST_MISSING);
            assert_eq!(
                change_answer(code, r#"{"available": false}"#).unwrap_err(),
                ASKS_FIRST_MISSING
            );
        }
        assert!(asks_first_answer(200, "not json").is_err());
        let refused = change_answer(403, r#"{"ok": false, "error": "The PC only."}"#);
        assert_eq!(refused.unwrap_err(), "The PC only.");
        let up = change_answer(202, r#"{"ok": true, "waiting": true}"#).unwrap();
        assert_eq!(up["waiting"], true);
    }
}
