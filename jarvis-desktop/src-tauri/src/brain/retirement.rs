//! The retirement what-if (the owner's decision of 2026-09-30, queue item 5;
//! `docs/FINANCE-DESIGN.md` part B and its "Retirement contract (frozen)";
//! JARVIS-API.md section 103; backend `jarvis_retirement.py`).
//!
//! The owner types a few numbers about their own money; the PC plays out
//! 10,000 made-up futures and answers with ranges. Two commands, one per
//! route, each its own power:
//!
//! * [`brain_retirement_defaults`] - `GET /api/retirement/defaults`: the form
//!   (fields, limits, units, the made-up default figures, the words). A read.
//! * [`brain_retirement_run`] - `POST /api/retirement/run` with the typed
//!   numbers as one flat object.
//!
//! No approval card and no Windows Hello: it is a calculation on numbers the
//! owner typed, and nothing leaves the PC. The run is held on a stale link
//! (rule 4).
//!
//! **Private, screen only.** While "Hide memory lists and chat history" is on,
//! or App lock has locked Jarvis, the PC is NOT asked at all and the answer is
//! `{"ok": true, "hidden": true, "words": {"hidden": "Retirement what-if
//! hidden"}}`; the numbers the owner typed are not sent. This app keeps
//! nothing: no file, no cache, no log line ever carries the typed numbers, the
//! result or the pairing token, and an error text never repeats a typed value.
//!
//! The PC's own refusals (`400 {"ok": false, "error", "field", "message"}`,
//! `429 busy`, `503 too_slow`) are handed on as `Ok` with `ok: false` intact
//! so the page can put the message beside the field it names; this file never
//! rewords them and never invents a success. The answer-reading functions are
//! plain functions of (status, body), so their tests run without a Tauri app
//! or a network, against the real answers in `tests/fixtures/
//! retirement-cases.json`.

use std::time::Duration;

use tauri::AppHandle;

use super::{require_link_live, READ_TIMEOUT};
use crate::commands;

/// A PC without `jarvis_retirement.py` / `retirement.patch`.
pub(crate) const RETIREMENT_MISSING: &str =
    "Your PC's Jarvis cannot work out a retirement what-if yet - run apply-patches.ps1 on the PC.";

/// The words the contract fixes for the hidden state (`words.hidden`).
pub(crate) const HIDDEN: &str = "Retirement what-if hidden";

/// The backend's own answer to a busy or too-slow run, if it sent none.
const BUSY: &str = "Another what-if is still being worked out. Try again in a moment.";
const TOO_SLOW: &str = "That took too long to work out, so it was stopped. Try again.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// The PC stops a run at 30 seconds (contract R6); wait a little longer so its
/// own `too_slow` answer, not a timeout here, is what the owner reads.
const RUN_TIMEOUT: Duration = Duration::from_secs(40);

/// The eleven fields of the contract, in the order the form draws them. A run
/// carries these keys and no other.
pub(crate) const FIELD_KEYS: [&str; 11] = [
    "current_age",
    "retirement_age",
    "plan_to_age",
    "savings",
    "yearly_saving",
    "yearly_spending",
    "other_income",
    "other_income_start_age",
    "expected_return_percent",
    "volatility_percent",
    "inflation_percent",
];

/// The longest typed text a field may carry ("1,250,000.50", "-5.5%").
const TEXT_MAX: usize = 40;

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

/// The answer given while the numbers must not be shown or sent.
pub(crate) fn hidden_answer() -> serde_json::Value {
    serde_json::json!({ "ok": true, "hidden": true, "words": { "hidden": HIDDEN } })
}

/// True while the card must neither be read nor drawn: the private lists are
/// hidden, or App lock has locked Jarvis.
fn card_hidden(app: &AppHandle) -> bool {
    crate::lock::private_hidden(app) || crate::lock::app_locked(app)
}

/// A refusal the backend classified: `{"ok": false, "error": "<code>", ...}`,
/// rebuilt with exactly the four keys the page reads (`ok`, `error`, `field`,
/// `message`), so nothing else the PC might echo is handed on.
fn refusal_body(v: &serde_json::Value) -> Option<serde_json::Value> {
    let error = v
        .get("error")
        .and_then(|e| e.as_str())
        .filter(|s| !s.is_empty())?;
    let text = |key: &str| v.get(key).and_then(|m| m.as_str()).unwrap_or("");
    Some(serde_json::json!({
        "ok": false,
        "error": error,
        "field": text("field"),
        "message": text("message"),
    }))
}

/// The reading of the form's answer: the fields list must be there.
pub(crate) fn defaults_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("ok").and_then(|o| o.as_bool()) == Some(true))
            .filter(|v| {
                v.get("fields")
                    .and_then(|f| f.as_array())
                    .is_some_and(|f| !f.is_empty())
            })
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 || status == 501 {
        return Err(RETIREMENT_MISSING.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// The reading of a run's answer. A success must carry a `result` object of
/// kind `retirement` with a `state`. Every refusal the PC classified (400, and
/// the two plain ones, 429 busy and 503 too_slow) comes back as `Ok` with
/// `ok: false`; the page maps the code to the field or the line.
pub(crate) fn run_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("ok").and_then(|o| o.as_bool()) == Some(true))
            .filter(|v| {
                v.get("result").is_some_and(|r| {
                    r.is_object()
                        && r.get("kind").and_then(|k| k.as_str()) == Some("retirement")
                        && r.get("state").and_then(|s| s.as_str()).is_some()
                })
            })
            .map(|v| serde_json::json!({ "ok": true, "result": v["result"] }))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    let refusal = parsed(body).as_ref().and_then(refusal_body);
    match status {
        429 => {
            let mut out = refusal.unwrap_or_else(|| {
                serde_json::json!({ "ok": false, "error": "busy", "field": "", "message": BUSY })
            });
            out["error"] = serde_json::json!("busy");
            if out["message"].as_str().is_none_or(str::is_empty) {
                out["message"] = serde_json::json!(BUSY);
            }
            Ok(out)
        }
        503 => {
            let mut out = refusal.unwrap_or_else(|| {
                serde_json::json!({ "ok": false, "error": "too_slow", "field": "", "message": TOO_SLOW })
            });
            out["error"] = serde_json::json!("too_slow");
            if out["message"].as_str().is_none_or(str::is_empty) {
                out["message"] = serde_json::json!(TOO_SLOW);
            }
            Ok(out)
        }
        400 | 422 => refusal.ok_or_else(|| UNREADABLE.to_string()),
        404 | 501 => Err(RETIREMENT_MISSING.to_string()),
        _ => Err(commands::backend_refusal(status, body)),
    }
}

/// The body of `POST /api/retirement/run` for what the page holds: a flat
/// object with only the contract's keys, each a finite number or a short
/// text. An empty box is left out (the PC takes the default, or says which
/// required box is missing). The errors are plain words and never repeat a
/// typed value.
pub(crate) fn run_body(values: &serde_json::Value) -> Result<serde_json::Value, String> {
    let object = values
        .as_object()
        .ok_or_else(|| "Send the numbers as a set of named fields.".to_string())?;
    let mut out = serde_json::Map::new();
    for (key, value) in object {
        if !FIELD_KEYS.contains(&key.as_str()) {
            return Err("That is not one of the what-if's fields.".to_string());
        }
        match value {
            serde_json::Value::Null => {}
            serde_json::Value::String(text) => {
                let text = text.trim();
                if text.is_empty() {
                    continue;
                }
                if text.chars().count() > TEXT_MAX {
                    return Err("That entry is too long to be a number.".to_string());
                }
                out.insert(key.clone(), serde_json::json!(text));
            }
            serde_json::Value::Number(n) if n.as_f64().is_some_and(f64::is_finite) => {
                out.insert(key.clone(), value.clone());
            }
            _ => return Err("Type each entry as a number.".to_string()),
        }
    }
    Ok(serde_json::Value::Object(out))
}

/// The what-if's form, read from the PC. A read, never held on a stale link.
/// While the card must be hidden the PC is not asked.
#[tauri::command]
pub async fn brain_retirement_defaults(app: AppHandle) -> Result<serde_json::Value, String> {
    if card_hidden(&app) {
        return Ok(hidden_answer());
    }
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/retirement/defaults"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    defaults_answer(status, &body)
}

/// Plays out the what-if for the typed numbers. Held on a stale link. The
/// numbers go to the PC only, and are kept nowhere here. While the card must
/// be hidden nothing is sent.
#[tauri::command]
pub async fn brain_retirement_run(
    app: AppHandle,
    values: serde_json::Value,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    if card_hidden(&app) {
        return Ok(hidden_answer());
    }
    let body = run_body(&values)?;
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(RUN_TIMEOUT))?
        .post(format!("{base}/api/retirement/run"))
        .headers(commands::jarvis_headers(&app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    run_answer(status, &text)
}

#[cfg(test)]
mod tests {
    use super::*;

    const CASES: &str = include_str!("../../../tests/fixtures/retirement-cases.json");

    fn case(name: &str) -> (u16, String) {
        let all: serde_json::Value = serde_json::from_str(CASES).unwrap();
        let c = &all[name];
        (c["status"].as_u64().unwrap() as u16, c["body"].to_string())
    }

    fn error_case(name: &str) -> (u16, String) {
        let all: serde_json::Value = serde_json::from_str(CASES).unwrap();
        let c = &all["errors"][name];
        (c["status"].as_u64().unwrap() as u16, c["body"].to_string())
    }

    #[test]
    fn the_form_is_read_with_all_eleven_fields_in_the_contracts_order() {
        let (s, b) = case("defaults");
        let a = defaults_answer(s, &b).unwrap();
        let keys: Vec<&str> = a["fields"]
            .as_array()
            .unwrap()
            .iter()
            .map(|f| f["key"].as_str().unwrap())
            .collect();
        assert_eq!(keys, FIELD_KEYS.to_vec());
        assert_eq!(a["words"]["hidden"], HIDDEN);
        assert_eq!(a["read_aloud"], false);
        assert_eq!(a["remember"], false);
    }

    #[test]
    fn a_form_with_no_fields_or_a_bad_shape_is_never_a_success() {
        assert!(defaults_answer(200, r#"{"ok": true, "fields": []}"#).is_err());
        assert!(defaults_answer(200, r#"{"ok": true}"#).is_err());
        assert!(defaults_answer(200, "not json").is_err());
        assert!(defaults_answer(200, r#"{"ok": false, "fields": [{}]}"#).is_err());
        assert_eq!(
            defaults_answer(404, r#"{"error": "not_found"}"#).unwrap_err(),
            RETIREMENT_MISSING
        );
        assert_eq!(defaults_answer(501, "").unwrap_err(), RETIREMENT_MISSING);
    }

    #[test]
    fn each_of_the_four_states_is_passed_on_as_the_pc_sent_it() {
        for state in [
            "mixed",
            "never_runs_out",
            "always_runs_out",
            "not_enough_to_say",
        ] {
            let (s, b) = case(state);
            let a = run_answer(s, &b).unwrap();
            assert_eq!(a["ok"], true, "{state}");
            assert_eq!(a["result"]["state"], state);
            assert_eq!(
                a["result"]["disclaimer"],
                "This is a simplified what-if, not financial advice."
            );
            assert_eq!(a["result"]["read_aloud"], false);
        }
        let (s, b) = case("mixed");
        let a = run_answer(s, &b).unwrap();
        assert_eq!(a["result"]["share"]["label"], "about 71 of 100");
        assert_eq!(a["result"]["runs_out_between"], serde_json::json!([81, 89]));
        assert_eq!(a["result"]["end_balance"]["text"]["p50"], "560,000");
    }

    #[test]
    fn a_success_without_a_real_result_is_never_a_success() {
        assert!(run_answer(200, r#"{"ok": true}"#).is_err());
        assert!(run_answer(200, r#"{"ok": true, "result": null}"#).is_err());
        assert!(run_answer(
            200,
            r#"{"ok": true, "result": {"kind": "other", "state": "mixed"}}"#
        )
        .is_err());
        assert!(run_answer(200, r#"{"ok": true, "result": {"kind": "retirement"}}"#).is_err());
        assert!(run_answer(
            200,
            r#"{"ok": false, "result": {"kind": "retirement", "state": "mixed"}}"#
        )
        .is_err());
        assert!(run_answer(200, "nope").is_err());
    }

    #[test]
    fn every_error_of_the_contract_keeps_its_code_field_and_message() {
        for code in [
            "missing",
            "bad_number",
            "negative",
            "out_of_range",
            "plan_not_after",
            "too_many_years",
            "unknown_field",
        ] {
            let (s, b) = error_case(code);
            assert_eq!(s, 400);
            let a = run_answer(s, &b).unwrap();
            let sent: serde_json::Value = serde_json::from_str(&b).unwrap();
            assert_eq!(a["ok"], false, "{code}");
            assert_eq!(a["error"], code);
            assert_eq!(a["field"], sent["field"]);
            assert_eq!(a["message"], sent["message"]);
            assert!(!a["message"].as_str().unwrap().is_empty());
        }
    }

    #[test]
    fn busy_and_too_slow_are_refusals_the_page_can_retry_or_show() {
        let (s, b) = case("busy");
        assert_eq!(s, 429);
        let a = run_answer(s, &b).unwrap();
        assert_eq!(
            (a["ok"].clone(), a["error"].clone()),
            (false.into(), "busy".into())
        );
        assert_eq!(a["message"], BUSY);
        let (s, b) = case("too_slow");
        assert_eq!(s, 503);
        let a = run_answer(s, &b).unwrap();
        assert_eq!(a["error"], "too_slow");
        assert_eq!(a["message"], TOO_SLOW);
        // Bodies with no words still get the fixed ones.
        assert_eq!(run_answer(429, "{}").unwrap()["message"], BUSY);
        assert_eq!(run_answer(503, "").unwrap()["message"], TOO_SLOW);
    }

    #[test]
    fn a_pc_without_the_route_says_so_and_other_failures_are_errors() {
        assert_eq!(run_answer(404, "").unwrap_err(), RETIREMENT_MISSING);
        assert_eq!(run_answer(501, "").unwrap_err(), RETIREMENT_MISSING);
        assert!(run_answer(500, "boom").is_err());
        assert!(run_answer(400, "not json").is_err());
    }

    #[test]
    fn a_refusal_hands_on_only_its_four_keys() {
        let a = run_answer(
            400,
            r#"{"ok": false, "error": "bad_number", "field": "savings", "message": "m", "echo": 123456}"#,
        )
        .unwrap();
        assert_eq!(a.as_object().unwrap().len(), 4);
        assert!(a.get("echo").is_none());
    }

    #[test]
    fn the_run_body_keeps_only_the_contracts_keys_and_plain_numbers() {
        let b = run_body(&serde_json::json!({
            "current_age": 40, "savings": "1,250,000", "expected_return_percent": "6.5%",
            "other_income": "", "other_income_start_age": null, "plan_to_age": "  "
        }))
        .unwrap();
        assert_eq!(
            b,
            serde_json::json!({
                "current_age": 40, "savings": "1,250,000", "expected_return_percent": "6.5%"
            })
        );
        assert_eq!(
            run_body(&serde_json::json!({})).unwrap(),
            serde_json::json!({})
        );
    }

    #[test]
    fn a_bad_body_is_refused_in_words_that_never_repeat_what_was_typed() {
        let unknown = run_body(&serde_json::json!({ "hunter2": 1 })).unwrap_err();
        assert!(!unknown.contains("hunter2"));
        let long = run_body(&serde_json::json!({ "savings": "9".repeat(41) })).unwrap_err();
        assert!(!long.contains("999"));
        for bad in [
            serde_json::json!({ "savings": true }),
            serde_json::json!({ "savings": [1] }),
            serde_json::json!({ "savings": { "a": 1 } }),
        ] {
            assert!(run_body(&bad).is_err(), "{bad}");
        }
        assert!(run_body(&serde_json::json!([1, 2])).is_err());
        assert!(run_body(&serde_json::json!("x")).is_err());
    }

    #[test]
    fn the_hidden_answer_carries_the_fixed_words_and_no_form() {
        let a = hidden_answer();
        assert_eq!(a["hidden"], true);
        assert_eq!(a["words"]["hidden"], "Retirement what-if hidden");
        assert!(a.get("fields").is_none());
        assert!(a.get("result").is_none());
    }
}
