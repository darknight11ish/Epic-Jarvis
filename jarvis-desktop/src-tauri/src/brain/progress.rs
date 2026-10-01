//! Activity heatmap and balance chart (the owner's tick of 2026-09-30;
//! `docs/GOALS-PROGRESS-DESIGN.md` part C and its "Progress contract
//! (frozen)"; JARVIS-API.md section 105; backend `jarvis_progress.py`).
//!
//! Three commands, one per route, in Brain -> Projects:
//!
//! * [`brain_progress_activity`] - `GET /api/progress/activity?weeks=N`
//!   (4 to 26, 12 if left out). A read.
//! * [`brain_progress_balance`] - `GET /api/progress/balance`. A read.
//! * [`brain_progress_balance_save`] - `POST /api/progress/balance
//!   {"axes": [{"kind", "ref", "label"?}]}`: 3 to 8 areas replace the whole
//!   chart, an empty list clears it. No card (the owner's own display
//!   choice), held on a stale link (rule 4).
//!
//! Every number and sentence comes from the PC; this file never works a
//! shade, a column or a sentence out. It only hands the answer on.
//!
//! A day's count can include a private (health or money) number, and an area
//! can be one; the PC says so with `keep_on_screen: true`. While "Windows
//! Hello for memory lists and chat history" hides the private lists, or App
//! lock is locked, such an answer is replaced here, in Rust, so a page script
//! cannot read round it: the picture (days, areas, values, the summary, the
//! picker's names) is taken out and only `hidden_words` is left. A picker row
//! that is private while nothing else is hidden loses its name and cannot be
//! ticked.
//!
//! While the lists are hidden the chart cannot be changed either: every answer
//! then carries `lists_hidden: true` (the page draws no picker) and the save
//! command refuses with the hidden words, as the phone does.
//!
//! Nothing from this file is cached, written to disk or logged. The token is
//! only in the headers `commands::jarvis_headers` builds.
//!
//! The answer-reading functions are plain functions of (status, body), so
//! their tests run without a Tauri app or a network.

use tauri::AppHandle;

use super::{require_link_live, READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

/// A PC whose backend has no Progress pictures. The phone says the same
/// words; the page shows nothing at all for it.
pub(crate) const PROGRESS_MISSING: &str =
    "Your PC's Jarvis does not have the Progress pictures yet - run apply-patches.ps1 on the PC.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// The words the PC sends with a hidden answer; used only if it sent none.
const HIDDEN_WORDS: &str = "Hidden while memory lists and chat history are hidden.";

const WEEKS_MIN: i64 = 4;
const WEEKS_MAX: i64 = 26;
const AXES_MIN: usize = 3;
const AXES_MAX: usize = 8;
const LABEL_MAX: usize = 24;
const REF_MAX: usize = 64;

/// The PC's own sentence for a wrong number of areas.
pub(crate) const LIMIT_WORDS: &str = "Pick 3 to 8 areas, or none to clear the chart.";
const LONG_NAME_WORDS: &str = "A name on the chart is at most 24 characters.";
const BAD_AREA_WORDS: &str = "One of those numbers is gone.";

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

/// `{"ok": false, "error": "<sentence>"}` -> the sentence, as sent.
fn backend_error(body: &str) -> Option<String> {
    let v = parsed(body)?;
    if v.get("ok").and_then(|o| o.as_bool()) != Some(false) {
        return None;
    }
    v.get("error")
        .and_then(|e| e.as_str())
        .map(str::to_string)
        .filter(|s| !s.is_empty())
}

/// `weeks`, or the plain reason it cannot be sent. `None` is "12" on the PC.
pub(crate) fn weeks_value(weeks: Option<i64>) -> Result<Option<i64>, String> {
    match weeks {
        None => Ok(None),
        Some(w) if (WEEKS_MIN..=WEEKS_MAX).contains(&w) => Ok(Some(w)),
        Some(_) => Err("Show 4 to 26 weeks.".to_string()),
    }
}

/// An id as the PC makes it (32 hex for a number, `g` + digits for a goal):
/// letters, digits, `-` and `_` only.
pub(crate) fn valid_ref(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= REF_MAX
        && id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
}

/// The body of `POST /api/progress/balance`, rebuilt from the page's request
/// so only what the contract lets an app send goes out: per area a `kind`,
/// a `ref` and (only if typed) a `label`. Errors are plain words.
pub(crate) fn axes_body(axes: &serde_json::Value) -> Result<serde_json::Value, String> {
    let list = axes.as_array().ok_or_else(|| LIMIT_WORDS.to_string())?;
    if !list.is_empty() && !(AXES_MIN..=AXES_MAX).contains(&list.len()) {
        return Err(LIMIT_WORDS.to_string());
    }
    let mut sent = Vec::with_capacity(list.len());
    for axis in list {
        let kind = axis.get("kind").and_then(|k| k.as_str()).unwrap_or("");
        if kind != "bench" && kind != "goal" {
            return Err(BAD_AREA_WORDS.to_string());
        }
        let id = axis.get("ref").and_then(|r| r.as_str()).unwrap_or("");
        if !valid_ref(id) {
            return Err(BAD_AREA_WORDS.to_string());
        }
        let mut one = serde_json::json!({ "kind": kind, "ref": id });
        if let Some(label) = axis.get("label").and_then(|l| l.as_str()) {
            let label = label.trim();
            if label.chars().count() > LABEL_MAX {
                return Err(LONG_NAME_WORDS.to_string());
            }
            if !label.is_empty() {
                one["label"] = serde_json::json!(label);
            }
        }
        sent.push(one);
    }
    Ok(serde_json::json!({ "axes": sent }))
}

/// The reading of any of the three answers. `need` is the key a success must
/// carry (`days` for activity, `axes` for balance). A `404`/`501` is a PC
/// without the feature: `available: false`, and the page draws nothing.
pub(crate) fn progress_answer(
    status: u16,
    body: &str,
    need: &str,
) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("ok").and_then(|o| o.as_bool()) != Some(false))
            .filter(|v| v.get(need).is_some_and(|x| x.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if let Some(sentence) = backend_error(body) {
        return Err(sentence);
    }
    if status == 404 || status == 501 {
        return Ok(serde_json::json!({ "available": false }));
    }
    Err(commands::backend_refusal(status, body))
}

/// True when this answer holds something the owner marked or the PC judged
/// health or money: the whole answer, or any one area.
fn is_private(answer: &serde_json::Value) -> bool {
    if answer.get("keep_on_screen").and_then(|k| k.as_bool()) == Some(true) {
        return true;
    }
    answer
        .get("axes")
        .and_then(|a| a.as_array())
        .is_some_and(|axes| {
            axes.iter()
                .any(|a| a.get("keep_on_screen").and_then(|k| k.as_bool()) == Some(true))
        })
}

/// The answer with the picture taken out: nothing but the PC's own
/// "hidden" sentence stays (and the title, so the section can say what is
/// hidden). No days, areas, values, summary or picker names.
pub(crate) fn hidden_answer(answer: &serde_json::Value) -> serde_json::Value {
    let words = answer
        .get("hidden_words")
        .and_then(|w| w.as_str())
        .filter(|w| !w.is_empty())
        .unwrap_or(HIDDEN_WORDS);
    serde_json::json!({
        "ok": true,
        "available": true,
        "title": answer.get("title").cloned().unwrap_or_else(|| serde_json::json!("")),
        "hidden": true,
        "keep_on_screen": true,
        "hidden_words": words,
    })
}

/// While the private lists are hidden: an answer with a private item in it is
/// replaced by [`hidden_answer`]. In an answer that stays, a picker row that is
/// private loses its name and is flagged `hidden`, so the page cannot tick it.
pub(crate) fn hide_private(answer: serde_json::Value) -> serde_json::Value {
    if answer.get("available").and_then(|a| a.as_bool()) == Some(false) {
        return answer;
    }
    if is_private(&answer) {
        return hidden_answer(&answer);
    }
    let mut answer = answer;
    if let Some(serde_json::Value::Array(choices)) = answer.get_mut("choices") {
        for c in choices.iter_mut() {
            let private = c.get("keep_on_screen").and_then(|k| k.as_bool()) == Some(true);
            if let (true, Some(o)) = (private, c.as_object_mut()) {
                o.insert("name".into(), serde_json::json!(""));
                o.insert("project_name".into(), serde_json::json!(""));
                o.insert("hidden".into(), serde_json::json!(true));
            }
        }
    }
    answer
}

fn words_hidden(app: &AppHandle) -> bool {
    crate::lock::private_hidden(app) || crate::lock::app_locked(app)
}

/// Says on the answer that the private lists are hidden right now (Windows
/// Hello for memory lists, or App lock locked), whether or not this answer had
/// anything private in it. The page uses it to offer no picker, the same rule
/// as the phone: while the lists are hidden nothing on this section changes.
pub(crate) fn mark_lists_hidden(mut answer: serde_json::Value) -> serde_json::Value {
    if answer.get("available").and_then(|a| a.as_bool()) == Some(false) {
        return answer;
    }
    if let Some(o) = answer.as_object_mut() {
        o.insert("lists_hidden".into(), serde_json::json!(true));
    }
    answer
}

fn shown(app: &AppHandle, answer: serde_json::Value) -> serde_json::Value {
    if words_hidden(app) {
        mark_lists_hidden(hide_private(answer))
    } else {
        answer
    }
}

/// The last `weeks` weeks of days, each with a count and a shade level. A
/// read. `weeks` is 4 to 26; left out, the PC uses 12.
#[tauri::command]
pub async fn brain_progress_activity(
    app: AppHandle,
    weeks: Option<i64>,
) -> Result<serde_json::Value, String> {
    let weeks = weeks_value(weeks)?;
    let base = commands::jarvis_base(&app);
    let url = match weeks {
        Some(w) => format!("{base}/api/progress/activity?weeks={w}"),
        None => format!("{base}/api/progress/activity"),
    };
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(url)
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = progress_answer(status, &body, "days")?;
    Ok(shown(&app, answer))
}

/// The areas the owner picked, drawn as a balance chart, and what can be
/// picked. A read.
#[tauri::command]
pub async fn brain_progress_balance(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/progress/balance"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = progress_answer(status, &body, "axes")?;
    Ok(shown(&app, answer))
}

/// Replaces the whole chart with 3 to 8 areas, or clears it (an empty list).
/// No card. Held on a stale link. A refusal from the PC comes back as an
/// error carrying its sentence, as sent; nothing was stored.
#[tauri::command]
pub async fn brain_progress_balance_save(
    app: AppHandle,
    axes: serde_json::Value,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    // The one rule on both apps: while the private lists are hidden (or App
    // lock is locked) the chart cannot be changed - its names are not shown.
    if words_hidden(&app) {
        return Err(HIDDEN_WORDS.to_string());
    }
    let body = axes_body(&axes)?;
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}/api/progress/balance"))
        .headers(commands::jarvis_headers(&app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    if status == 404 || status == 501 {
        return Err(PROGRESS_MISSING.to_string());
    }
    let answer = progress_answer(status, &text, "axes")?;
    Ok(shown(&app, answer))
}

#[cfg(test)]
mod tests {
    use super::*;

    const CASES: &str = include_str!("../../../tests/fixtures/progress-cases.json");

    fn cases() -> serde_json::Value {
        serde_json::from_str(CASES).expect("progress-cases.json is JSON")
    }

    #[test]
    fn weeks_are_four_to_twenty_six() {
        assert_eq!(weeks_value(None), Ok(None));
        assert_eq!(weeks_value(Some(4)), Ok(Some(4)));
        assert_eq!(weeks_value(Some(26)), Ok(Some(26)));
        for bad in [-1, 0, 3, 27, 1000] {
            assert!(weeks_value(Some(bad)).is_err(), "{bad}");
        }
        let limits = &cases()["limits"];
        assert_eq!(limits["weeks_min"], WEEKS_MIN);
        assert_eq!(limits["weeks_max"], WEEKS_MAX);
        assert_eq!(limits["axes_min"], AXES_MIN as i64);
        assert_eq!(limits["axes_max"], AXES_MAX as i64);
        assert_eq!(limits["label_max"], LABEL_MAX as i64);
    }

    #[test]
    fn a_ref_is_letters_digits_dash_and_underscore_only() {
        for good in ["00000000000000000000000000000003", "g0000000000", "a-b_c"] {
            assert!(valid_ref(good), "{good}");
        }
        for bad in ["", "../x", "a/b", "a?b", "a b", &"a".repeat(65)] {
            assert!(!valid_ref(bad), "{bad:?}");
        }
    }

    fn axis(kind: &str, id: &str, label: Option<&str>) -> serde_json::Value {
        let mut a = serde_json::json!({ "kind": kind, "ref": id });
        if let Some(l) = label {
            a["label"] = serde_json::json!(l);
        }
        a
    }

    #[test]
    fn the_save_body_is_three_to_eight_areas_or_none() {
        let mk = |n: usize| {
            serde_json::Value::Array(
                (0..n)
                    .map(|i| axis("bench", &format!("b{i}"), None))
                    .collect(),
            )
        };
        let refusal = &cases()["refusals"]["two_areas"]["error"];
        assert_eq!(LIMIT_WORDS, refusal.as_str().unwrap());
        assert_eq!(
            LIMIT_WORDS,
            cases()["refusals"]["nine_areas"]["error"].as_str().unwrap()
        );
        for n in [1, 2, 9, 10] {
            assert_eq!(axes_body(&mk(n)), Err(LIMIT_WORDS.to_string()), "{n}");
        }
        for n in [0, 3, 8] {
            let body = axes_body(&mk(n)).unwrap();
            assert_eq!(body["axes"].as_array().unwrap().len(), n);
        }
        assert!(axes_body(&serde_json::json!({})).is_err());
    }

    #[test]
    fn the_save_body_carries_only_kind_ref_and_a_typed_label() {
        let body = axes_body(&serde_json::json!([
            { "kind": "bench", "ref": "abc", "label": "  Fitness ", "project": "p", "name": "x" },
            { "kind": "goal", "ref": "g1", "label": "   " },
            { "kind": "goal", "ref": "g2" },
        ]))
        .unwrap();
        assert_eq!(
            body,
            serde_json::json!({ "axes": [
                { "kind": "bench", "ref": "abc", "label": "Fitness" },
                { "kind": "goal", "ref": "g1" },
                { "kind": "goal", "ref": "g2" },
            ]})
        );
    }

    #[test]
    fn a_long_name_or_a_bad_area_is_refused_before_anything_is_sent() {
        let long = "x".repeat(25);
        let ok = "x".repeat(24);
        let mk = |label: &str| {
            serde_json::json!([
                axis("bench", "a", Some(label)),
                axis("bench", "b", None),
                axis("goal", "c", None)
            ])
        };
        assert_eq!(
            axes_body(&mk(&long)),
            Err(cases()["refusals"]["long_name"]["error"]
                .as_str()
                .unwrap()
                .to_string())
        );
        assert!(axes_body(&mk(&ok)).is_ok());
        for bad in [
            serde_json::json!([
                axis("shoe", "a", None),
                axis("bench", "b", None),
                axis("bench", "c", None)
            ]),
            serde_json::json!([
                axis("bench", "../a", None),
                axis("bench", "b", None),
                axis("bench", "c", None)
            ]),
            serde_json::json!([
                axis("bench", "", None),
                axis("bench", "b", None),
                axis("bench", "c", None)
            ]),
        ] {
            assert!(axes_body(&bad).is_err());
        }
    }

    #[test]
    fn every_real_answer_reads() {
        let c = cases();
        for key in [
            "empty",
            "one_day",
            "mixed_levels",
            "dst_weekend",
            "private_number",
        ] {
            let body = c["heat"][key].to_string();
            let got = progress_answer(200, &body, "days").unwrap();
            assert_eq!(got["words"], c["heat"][key]["words"], "{key}");
        }
        for key in [
            "nothing_picked",
            "three_areas",
            "five_areas_mixed",
            "target_reached_private",
            "after_a_benchmark_is_deleted",
            "after_a_goal_is_stopped",
        ] {
            let body = c["balance"][key].to_string();
            let got = progress_answer(200, &body, "axes").unwrap();
            assert_eq!(got["summary"], c["balance"][key]["summary"], "{key}");
        }
    }

    #[test]
    fn a_bad_shape_is_never_a_success() {
        assert!(progress_answer(200, "not json", "days").is_err());
        assert!(progress_answer(200, r#"{"ok": true}"#, "days").is_err());
        assert!(progress_answer(200, r#"{"ok": true, "days": null}"#, "days").is_err());
        assert!(progress_answer(200, r#"{"ok": false, "days": []}"#, "days").is_err());
        assert!(progress_answer(200, r#"{"ok": true, "days": []}"#, "days").is_ok());
    }

    #[test]
    fn a_refusal_is_the_pcs_sentence_as_sent_and_an_old_pc_draws_nothing() {
        let c = cases();
        for (name, r) in c["refusals"].as_object().unwrap() {
            let body = serde_json::json!({ "ok": false, "error": r["error"] }).to_string();
            let status = r["status"].as_u64().unwrap() as u16;
            assert_eq!(
                progress_answer(status, &body, "axes"),
                Err(r["error"].as_str().unwrap().to_string()),
                "{name}"
            );
        }
        let old = progress_answer(404, "Not Found", "axes").unwrap();
        assert_eq!(old["available"], false);
        assert_eq!(
            progress_answer(501, "", "days").unwrap()["available"],
            false
        );
        assert!(progress_answer(500, "boom", "days").is_err());
    }

    #[test]
    fn a_private_answer_is_taken_out_whole_and_only_the_pcs_words_stay() {
        let c = cases();
        let words = c["words"]["hidden"].as_str().unwrap();
        for answer in [
            c["heat"]["private_number"].clone(),
            c["balance"]["three_areas"].clone(),
            c["balance"]["target_reached_private"].clone(),
        ] {
            assert_eq!(answer["keep_on_screen"], true);
            let out = hide_private(answer.clone());
            assert_eq!(out["hidden"], true);
            assert_eq!(out["hidden_words"], words);
            for gone in [
                "days",
                "axes",
                "summary",
                "choices",
                "columns",
                "words",
                "radar",
                "total",
                "days_active",
                "note",
                "levels",
            ] {
                assert!(out.get(gone).is_none(), "{gone} survived");
            }
            let text = out.to_string();
            for name in ["Emergency fund", "Body weight", "Weekly distance", "Life"] {
                assert!(!text.contains(name), "{name} survived");
            }
        }
    }

    #[test]
    fn an_answer_with_nothing_private_stays_but_a_private_pick_is_hidden() {
        // A balance answer with no private area picked, but a private row to pick.
        let mut answer = cases()["balance"]["three_areas"].clone();
        answer["keep_on_screen"] = serde_json::json!(false);
        for a in answer["axes"].as_array_mut().unwrap() {
            a["keep_on_screen"] = serde_json::json!(false);
        }
        let out = hide_private(answer);
        assert!(out.get("hidden").is_none());
        assert!(out["axes"].is_array());
        let rows = out["choices"].as_array().unwrap();
        let private: Vec<_> = rows.iter().filter(|r| r["hidden"] == true).collect();
        assert_eq!(
            private.len(),
            3,
            "Body weight, Emergency fund, Sleep target"
        );
        for r in &private {
            assert_eq!(r["name"], "");
            assert_eq!(r["project_name"], "");
            assert_eq!(r["keep_on_screen"], true);
        }
        for r in rows.iter().filter(|r| r["keep_on_screen"] == false) {
            assert!(r.get("hidden").is_none());
            assert!(!r["name"].as_str().unwrap().is_empty());
        }
        // The heatmap with no private item is left alone.
        let heat = cases()["heat"]["mixed_levels"].clone();
        assert_eq!(heat["keep_on_screen"], false);
        assert_eq!(hide_private(heat.clone()), heat);
        // An old PC's answer passes through.
        let old = serde_json::json!({ "available": false });
        assert_eq!(hide_private(old.clone()), old);
    }

    #[test]
    fn hidden_lists_are_marked_on_every_answer_so_the_page_offers_no_picker() {
        let plain = cases()["balance"]["nothing_picked"].clone();
        let out = mark_lists_hidden(hide_private(plain));
        assert_eq!(out["lists_hidden"], true);
        assert!(out["axes"].is_array(), "nothing private: the answer stays");
        let private = mark_lists_hidden(hide_private(cases()["heat"]["private_number"].clone()));
        assert_eq!(private["lists_hidden"], true);
        assert_eq!(private["hidden"], true);
        let old = serde_json::json!({ "available": false });
        assert_eq!(mark_lists_hidden(old.clone()), old);
    }

    #[test]
    fn a_hidden_answer_with_no_words_of_its_own_gets_the_shared_ones() {
        let out = hidden_answer(&serde_json::json!({ "keep_on_screen": true }));
        assert_eq!(out["hidden_words"], cases()["words"]["hidden"]);
    }

    #[test]
    fn the_routes_are_literal_and_the_three_commands_are_reads_and_one_gated_write() {
        let src = include_str!("progress.rs");
        for route in ["\"{base}/api/progress/balance\"", "/api/progress/activity"] {
            assert!(src.contains(route), "{route}");
        }
        assert!(src.contains("require_link_live(&app)?;"));
        assert!(
            src.contains("if words_hidden(&app) {\n        return Err(HIDDEN_WORDS.to_string());"),
            "a save is refused while the lists are hidden"
        );
        assert!(src.contains("private_hidden"));
        assert!(src.contains("app_locked"));
    }
}
