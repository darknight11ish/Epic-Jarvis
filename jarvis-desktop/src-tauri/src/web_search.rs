//! Settings -> "Web search" (the owner's decisions of 2026-09-25;
//! backend/web-search.patch, backend/jarvis_search.py; JARVIS-API.md
//! section 23).
//!
//! Five commands, settings window only (permissions/surfaces.toml,
//! `settings-surface`):
//!
//! * [`get_web_search`] - `GET /api/search`: which of the four providers is
//!   chosen (SearXNG on this PC by default), each one's "why use this one"
//!   line in the PC's own words, whether it is ready, the SearXNG address,
//!   "Ask before every web search", and Whoogle's reason for being left out.
//! * [`set_web_search`] - `POST /api/search/settings` with ONE change: the
//!   provider or the SearXNG address (at once), or "Ask before every web
//!   search" (on at once; off raises ONE approval card on the PC). Held
//!   while the event stream is stale, here and on the phone.
//! * [`test_web_search`] - `POST /api/search/test`: one search for a fixed
//!   harmless word through the chosen provider, and what happened in words
//!   ("works", "not running", "JSON not enabled", "key missing", "credits
//!   used up"). Held on a stale link too.
//! * [`save_search_key`] / [`forget_search_key`] - the Tavily or Brave
//!   Search key, written straight into Windows Credential Manager on THIS PC
//!   ([`crate::token_store::write_search_key`]) under the name the backend
//!   reads. The key never goes over HTTP - not to the backend, not to the
//!   phone - and is never returned to the page, logged or put in an error
//!   (CLAUDE.md rule 3). The phone has no way to enter one: sending a key
//!   over the link would send it somewhere other than its one service
//!   (ARCHITECTURE.md section 8, "One-sided on purpose").

use std::time::Duration;

use tauri::{AppHandle, Manager};

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};
use crate::token_store;

pub(crate) const SEARCH_PATH: &str = "/api/search";

/// The four providers, in the PC's order.
pub(crate) const PROVIDERS: [&str; 4] = ["searxng", "duckduckgo", "tavily", "brave"];

/// What a backend without `jarvis_search.py` is told to do about it. The
/// phone says the same (`WebSearch.MISSING`).
pub(crate) const SEARCH_MISSING: &str = "Your PC's Jarvis does not have web search yet - run \
     apply-patches.ps1 on the PC.";

const STALE: &str = "The connection to Jarvis is catching up, so nothing can be sent until \
                     it does.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);
const WRITE_TIMEOUT: Duration = Duration::from_secs(20);
/// A test search waits for the provider (up to 15 seconds on the PC).
const TEST_TIMEOUT: Duration = Duration::from_secs(40);

fn missing(code: u16, body: &str) -> bool {
    code == 404
        || (code == 503
            && serde_json::from_str::<serde_json::Value>(body)
                .ok()
                .and_then(|v| v.get("available").and_then(|a| a.as_bool()))
                == Some(false))
}

/// [`get_web_search`]'s reading of the answer, tested against
/// `tests/fixtures/web-search-cases.json` (the real `view()`).
pub(crate) fn search_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("providers").is_some_and(|p| p.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "why": SEARCH_MISSING }));
    }
    Err(backend_refusal(status, body))
}

/// A POST's answer: 200 and 202 are the PC's object as it is; a refusal is
/// the PC's own sentence.
pub(crate) fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.is_object())
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Err(SEARCH_MISSING.to_string());
    }
    Err(backend_refusal(status, body))
}

/// The body of ONE change. Exactly one of the three; a provider must be one
/// of the four; an address is text of a sane length (the PC decides whether
/// it is the owner's own network).
pub(crate) fn setting_body(
    provider: Option<&str>,
    searxng_url: Option<&str>,
    ask_every_time: Option<bool>,
) -> Result<serde_json::Value, String> {
    let given =
        provider.is_some() as u8 + searxng_url.is_some() as u8 + ask_every_time.is_some() as u8;
    if given != 1 {
        return Err("Change one setting at a time.".to_string());
    }
    if let Some(p) = provider {
        if !PROVIDERS.contains(&p) {
            return Err("That is not one of the four searches.".to_string());
        }
        return Ok(serde_json::json!({ "provider": p }));
    }
    if let Some(u) = searxng_url {
        let u = u.trim();
        if u.len() > 200 {
            return Err("That address is too long.".to_string());
        }
        return Ok(serde_json::json!({ "searxng_url": u }));
    }
    Ok(serde_json::json!({ "ask_every_time": ask_every_time.unwrap_or(true) }))
}

fn stale(app: &AppHandle) -> bool {
    app.state::<crate::stream::StreamState>().link().stale
}

async fn read(app: &AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{SEARCH_PATH}"))
        .headers(jarvis_headers(app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    search_answer(status, &body)
}

async fn post(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
    timeout: Duration,
) -> Result<serde_json::Value, String> {
    let base = jarvis_base(app);
    let response = jarvis_client(Some(timeout))?
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

/// The providers, their "why" lines and the settings: `GET /api/search`.
#[tauri::command]
pub async fn get_web_search(app: AppHandle) -> Result<serde_json::Value, String> {
    read(&app).await
}

/// ONE change. Turning "Ask before every web search" off raises an approval
/// card on the PC; nothing else asks. Held on a stale link.
#[tauri::command]
pub async fn set_web_search(
    app: AppHandle,
    provider: Option<String>,
    searxng_url: Option<String>,
    ask_every_time: Option<bool>,
) -> Result<serde_json::Value, String> {
    let body = setting_body(provider.as_deref(), searxng_url.as_deref(), ask_every_time)?;
    if stale(&app) {
        return Err(STALE.to_string());
    }
    post(&app, "/api/search/settings", body, WRITE_TIMEOUT).await
}

/// One test search for a fixed word. Held on a stale link.
#[tauri::command]
pub async fn test_web_search(app: AppHandle) -> Result<serde_json::Value, String> {
    if stale(&app) {
        return Err(STALE.to_string());
    }
    post(
        &app,
        "/api/search/test",
        serde_json::json!({}),
        TEST_TIMEOUT,
    )
    .await
}

fn provider_label(provider: &str) -> &'static str {
    match provider {
        "tavily" => "Tavily",
        _ => "Brave Search",
    }
}

/// Saves the Tavily or Brave Search key in Credential Manager on this PC.
/// Returns words only - never the key.
#[tauri::command]
pub async fn save_search_key(provider: String, key: String) -> Result<serde_json::Value, String> {
    if token_store::search_key_target(&provider).is_none() {
        return Err("Only Tavily and Brave Search use a key.".to_string());
    }
    if let Some(why) = token_store::search_key_problem(&key) {
        return Err(why.to_string());
    }
    token_store::write_search_key(&provider, &key).map_err(|e| format!("Not saved: {e}."))?;
    Ok(serde_json::json!({
        "ok": true,
        "said": format!(
            "Saved your {} key in Windows Credential Manager on this PC. It is sent only to {} itself.",
            provider_label(&provider),
            provider_label(&provider)
        ),
    }))
}

/// Removes the Tavily or Brave Search key from this PC.
#[tauri::command]
pub async fn forget_search_key(provider: String) -> Result<serde_json::Value, String> {
    if token_store::search_key_target(&provider).is_none() {
        return Err("Only Tavily and Brave Search use a key.".to_string());
    }
    token_store::delete_search_key(&provider).map_err(|e| format!("Not removed: {e}."))?;
    Ok(serde_json::json!({
        "ok": true,
        "said": format!("Removed your {} key from this PC.", provider_label(&provider)),
    }))
}

#[cfg(test)]
mod tests {
    use super::{change_answer, search_answer, setting_body, PROVIDERS, SEARCH_MISSING};

    /// The real answers, made by `tools/gen_web_search_cases.py`.
    const CASES: &str = include_str!("../../tests/fixtures/web-search-cases.json");

    fn cases() -> serde_json::Value {
        serde_json::from_str(CASES).expect("web-search-cases.json is JSON")
    }

    #[test]
    fn every_real_view_is_passed_on_unchanged() {
        let doc = cases();
        let all = doc["cases"].as_object().expect("cases");
        let mut n = 0;
        for (name, view) in all
            .iter()
            .filter(|(k, _)| !k.starts_with("post_") && !k.starts_with("test_"))
        {
            let got =
                search_answer(200, &view.to_string()).unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(&got, view, "{name}");
            n += 1;
        }
        assert!(n >= 4);
        let ids: Vec<&str> = doc["cases"]["default"]["providers"]
            .as_array()
            .unwrap()
            .iter()
            .map(|p| p["id"].as_str().unwrap())
            .collect();
        assert_eq!(ids, PROVIDERS);
    }

    #[test]
    fn a_pc_without_it_says_so_and_refusals_are_the_pcs_words() {
        for code in [404u16, 503] {
            let got = search_answer(code, r#"{"available": false}"#).unwrap();
            assert_eq!(got["why"], SEARCH_MISSING);
        }
        let doc = cases();
        let bad = &doc["cases"]["post_bad_address"];
        let err = change_answer(
            bad["status"].as_u64().unwrap() as u16,
            &bad["body"].to_string(),
        )
        .unwrap_err();
        assert!(
            err.starts_with("That SearXNG address cannot be used"),
            "{err}"
        );
        for name in [
            "post_provider",
            "post_ask_off",
            "test_works",
            "test_not_running",
        ] {
            let c = &doc["cases"][name];
            let got = change_answer(c["status"].as_u64().unwrap() as u16, &c["body"].to_string())
                .unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(&got, &c["body"], "{name}");
        }
    }

    #[test]
    fn exactly_one_change_per_request() {
        assert_eq!(
            setting_body(Some("brave"), None, None).unwrap(),
            serde_json::json!({"provider": "brave"})
        );
        assert_eq!(
            setting_body(None, Some(" http://127.0.0.1:8888 "), None).unwrap(),
            serde_json::json!({"searxng_url": "http://127.0.0.1:8888"})
        );
        assert_eq!(
            setting_body(None, None, Some(false)).unwrap(),
            serde_json::json!({"ask_every_time": false})
        );
        assert!(setting_body(None, None, None).is_err());
        assert!(setting_body(Some("brave"), None, Some(true)).is_err());
        assert!(setting_body(Some("whoogle"), None, None).is_err());
        assert!(setting_body(None, Some(&"x".repeat(201)), None).is_err());
    }
}
