//! Settings -> "What Jarvis can reach" (the Muse audit, 2026-09-25;
//! backend/reach.patch, backend/jarvis_reach.py; JARVIS-API.md section 24).
//!
//! One command, settings window only (permissions/surfaces.toml,
//! `settings-surface`):
//!
//! * [`get_reach`] - `GET /api/reach`: every way Jarvis can reach something
//!   outside itself, whether each is on, where it goes (a host name only),
//!   whether it asks first, one plain line each, and the tools the AI model
//!   is offered. The PC writes every word of it from its own settings - the
//!   model never does - and this passes the answer on as it is.
//!
//! Read only. It changes nothing, so it is not held while the event stream
//! is stale. No password, key, private link or ntfy topic is in the answer
//! (the PC leaves them out; backend/test_reach.py checks it).

use std::time::Duration;

use tauri::AppHandle;

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

pub(crate) const REACH_PATH: &str = "/api/reach";

/// What a backend without `jarvis_reach.py` is told to do about it. The
/// phone says the same (`Reach.MISSING`), and so does the PC.
pub(crate) const REACH_MISSING: &str = "Your PC's Jarvis cannot list what it can reach yet - \
     run apply-patches.ps1 on the PC.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);

fn missing(code: u16, body: &str) -> bool {
    code == 404
        || (code == 503
            && serde_json::from_str::<serde_json::Value>(body)
                .ok()
                .and_then(|v| v.get("available").and_then(|a| a.as_bool()))
                == Some(false))
}

/// [`get_reach`]'s reading of the answer, tested against
/// `tests/fixtures/reach-cases.json` (the real `view()`).
pub(crate) fn reach_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("rows").is_some_and(|r| r.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if missing(status, body) {
        return Ok(serde_json::json!({ "available": false, "why": REACH_MISSING }));
    }
    Err(backend_refusal(status, body))
}

/// Every way Jarvis can reach something outside itself: `GET /api/reach`.
#[tauri::command]
pub async fn get_reach(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{REACH_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    reach_answer(status, &body)
}

#[cfg(test)]
mod tests {
    use super::{reach_answer, REACH_MISSING};

    /// The real answers, made by `tools/gen_reach_cases.py`.
    const CASES: &str = include_str!("../../tests/fixtures/reach-cases.json");

    #[test]
    fn every_real_view_is_passed_on_unchanged() {
        let doc: serde_json::Value = serde_json::from_str(CASES).expect("reach-cases.json");
        let all = doc["cases"].as_object().expect("cases");
        assert!(all.len() >= 4);
        for (name, view) in all {
            let got =
                reach_answer(200, &view.to_string()).unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(&got, view, "{name}");
            let ids: Vec<&str> = view["rows"]
                .as_array()
                .unwrap()
                .iter()
                .map(|r| r["id"].as_str().unwrap())
                .collect();
            let want: Vec<&str> = doc["ids"]
                .as_array()
                .unwrap()
                .iter()
                .map(|x| x.as_str().unwrap())
                .collect();
            assert_eq!(ids, want, "{name}");
        }
        assert_eq!(doc["missing"].as_str().unwrap(), REACH_MISSING);
    }

    #[test]
    fn an_older_pc_says_so_and_nonsense_is_refused() {
        for code in [404u16, 503] {
            let got = reach_answer(code, r#"{"available": false}"#).unwrap();
            assert_eq!(got["why"], REACH_MISSING);
        }
        assert!(reach_answer(200, "not json").is_err());
        assert!(reach_answer(200, r#"{"rows": "nope"}"#).is_err());
        assert!(reach_answer(401, r#"{"error": "bad or missing X-Jarvis-Token"}"#).is_err());
    }
}
