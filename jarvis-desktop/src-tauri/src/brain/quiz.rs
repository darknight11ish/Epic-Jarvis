//! Quiz me on a text (the owner's "go ahead", 2026-09-30;
//! `docs/STUDY-FROM-TEXT-DESIGN.md` section 11; JARVIS-API.md section 98;
//! backend `jarvis_quiz.py`).
//!
//! The owner pastes some text, the PC's local model writes a few questions,
//! and the owner types an answer to each. Five commands, one per route, each
//! its own power, modelled on [`super::goals`]:
//!
//! * [`brain_quiz_start`] - `POST /api/quiz {"text", "count"?, "title"?}`.
//! * [`brain_quiz_get`] - `GET /api/quiz/<id>`: a read, used to paint the
//!   quiz again after "Show" ends a hidden state.
//! * [`brain_quiz_answer`] - `POST /api/quiz/<id>/answer {"n", "answer"}`.
//! * [`brain_quiz_finish`] - `POST /api/quiz/<id>/finish`.
//! * [`brain_quiz_stop`] - `POST /api/quiz/<id>/stop`.
//!
//! No card is raised: the text is the owner's own, only the local model sees
//! it and nothing leaves the PC. Every write is held on a stale link
//! (rule 4). The quiz lives in the PC's memory only, and this app keeps
//! nothing of it: no text, no answers, no marks.
//!
//! While "Windows Hello for memory lists and chat history" (lock.rs) hides
//! the private lists, the questions, the source passages and the comments
//! are taken out of every answer here, in Rust, so a page script cannot read
//! round it - the same treatment as the "Used" list. The counts, levels and
//! question numbers stay: they say nothing about the owner's text.
//!
//! The backend's own refusals (`{"ok": false, "error": <code>, "message":
//! ...}`) are handed on unchanged so the page can put its plain words to each
//! code; this file never rewords them and never invents a success.
//!
//! The answer-reading functions are plain functions of (status, body) so
//! their tests run without a Tauri app or a network.

use tauri::AppHandle;

use super::{require_link_live, READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

/// A PC whose backend has no Quiz yet. The phone says the same words.
pub(crate) const QUIZ_MISSING: &str =
    "Your PC's Jarvis does not have Quiz yet - run apply-patches.ps1 on the PC.";

/// The backend's own answer, when there is no such route at all.
const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// The quiz is not open any more (finished, stopped, restarted or timed out).
pub(crate) const NO_SUCH_QUIZ: &str = "That quiz is not open any more.";

/// The longest id this app will put in a URL.
const ID_MAX: usize = 64;

/// A quiz id as the PC makes it: letters, digits, `-` and `_` only, so an id
/// can never carry a `/`, `?` or `..` into the route.
pub(crate) fn valid_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= ID_MAX
        && id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
}

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

/// A body the backend itself classified as a refusal: `{"ok": false,
/// "error": "<code>", ...}`. `None` for any other shape, which is how a
/// backend with no Quiz at all (a bare 404) is told apart from the feature's
/// own `not_found`.
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

/// A crisis answer: `{"ok": true, "crisis": true, "message": "<words>", ...}`.
fn is_crisis(v: &serde_json::Value) -> bool {
    v.get("crisis").and_then(|c| c.as_bool()) == Some(true)
        && v.get("message")
            .is_some_and(|m| m.as_str().is_some_and(|s| !s.is_empty()))
}

/// The reading of any of the five answers. `need` is the field a success
/// must carry (`quiz`, or `summary` for finish, or none for stop). A refusal
/// the backend classified comes back as `Ok` with `ok: false` intact; the
/// page maps its `error` code to plain words.
pub(crate) fn quiz_answer(
    status: u16,
    body: &str,
    need: Option<&str>,
) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("ok").and_then(|o| o.as_bool()) == Some(true))
            .filter(|v| {
                // A crisis answer (JARVIS-API 98.4) has no mark: it carries the
                // PC's help words instead, and passes through as it is.
                (need == Some("mark") && is_crisis(v))
                    || need.is_none_or(|k| v.get(k).is_some_and(|x| !x.is_null()))
            })
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if let Some(refusal) = backend_refusal_body(body) {
        return Ok(refusal);
    }
    if status == 404 || status == 501 {
        return Err(QUIZ_MISSING.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

/// The quiz's own words taken out, for while the private lists are hidden:
/// every question's prompt, and every mark's comment and source passage.
/// Numbers, kinds, levels, the count answered and `grader_verified` stay.
pub(crate) fn redact_quiz(quiz: &mut serde_json::Value) {
    let Some(obj) = quiz.as_object_mut() else {
        return;
    };
    obj.insert("title".into(), serde_json::json!(""));
    if let Some(serde_json::Value::Array(questions)) = obj.get_mut("questions") {
        for q in questions.iter_mut() {
            if let Some(o) = q.as_object_mut() {
                o.insert("prompt".into(), serde_json::json!(""));
                if let Some(mark) = o.get_mut("mark") {
                    redact_mark(mark);
                }
            }
        }
    }
    obj.insert("hidden".into(), serde_json::json!(true));
}

/// One mark with its comment and passage taken out.
pub(crate) fn redact_mark(mark: &mut serde_json::Value) {
    if let Some(m) = mark.as_object_mut() {
        m.insert("comment".into(), serde_json::json!(""));
        m.insert("passage".into(), serde_json::json!(""));
    }
}

/// Applies [`redact_quiz`] / [`redact_mark`] to an answer that carries them.
pub(crate) fn redact_answer(mut answer: serde_json::Value) -> serde_json::Value {
    if answer.get("ok").and_then(|o| o.as_bool()) != Some(true) {
        return answer;
    }
    if let Some(obj) = answer.as_object_mut() {
        if let Some(q) = obj.get_mut("quiz") {
            redact_quiz(q);
        }
        if let Some(m) = obj.get_mut("mark") {
            redact_mark(m);
        }
        obj.insert("hidden".into(), serde_json::json!(true));
    }
    answer
}

fn hide_if_private(app: &AppHandle, answer: serde_json::Value) -> serde_json::Value {
    if crate::lock::private_hidden(app) {
        redact_answer(answer)
    } else {
        answer
    }
}

/// Writes the questions for a pasted text. The text goes to the PC's local
/// model only. No card. Held on a stale link.
#[tauri::command]
pub async fn brain_quiz_start(
    app: AppHandle,
    text: String,
    count: Option<i64>,
    title: Option<String>,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let mut body = serde_json::json!({ "text": text });
    if let Some(count) = count {
        body["count"] = serde_json::json!(count);
    }
    if let Some(title) = title.filter(|t| !t.trim().is_empty()) {
        body["title"] = serde_json::json!(title);
    }
    let answer = post(&app, "/api/quiz", body, Some("quiz")).await?;
    Ok(hide_if_private(&app, answer))
}

/// One open quiz, read again. A read.
#[tauri::command]
pub async fn brain_quiz_get(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    if !valid_id(&id) {
        return Err(NO_SUCH_QUIZ.to_string());
    }
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/quiz/{id}"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = quiz_answer(status, &body, Some("quiz"))?;
    Ok(hide_if_private(&app, answer))
}

/// The owner's typed answer to question `n`, marked by the local model
/// against the source passage. No card. Held on a stale link.
#[tauri::command]
pub async fn brain_quiz_answer(
    app: AppHandle,
    id: String,
    n: i64,
    answer: String,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    if !valid_id(&id) {
        return Err(NO_SUCH_QUIZ.to_string());
    }
    let out = post(
        &app,
        &format!("/api/quiz/{id}/answer"),
        serde_json::json!({ "n": n, "answer": answer }),
        Some("mark"),
    )
    .await?;
    Ok(hide_if_private(&app, out))
}

/// Ends the quiz and asks for the short summary; the PC forgets the quiz.
/// Held on a stale link.
#[tauri::command]
pub async fn brain_quiz_finish(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    if !valid_id(&id) {
        return Err(NO_SUCH_QUIZ.to_string());
    }
    post(
        &app,
        &format!("/api/quiz/{id}/finish"),
        serde_json::json!({}),
        Some("summary"),
    )
    .await
}

/// Stops the quiz and makes the PC forget it. Held on a stale link.
#[tauri::command]
pub async fn brain_quiz_stop(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    if !valid_id(&id) {
        return Err(NO_SUCH_QUIZ.to_string());
    }
    post(
        &app,
        &format!("/api/quiz/{id}/stop"),
        serde_json::json!({}),
        None,
    )
    .await
}

async fn post(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
    need: Option<&str>,
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
    quiz_answer(status, &text, need)
}

#[cfg(test)]
mod tests {
    use super::*;

    const QUIZ: &str = r#"{"ok": true, "quiz": {"id": "q0123abcd", "title": "Bread",
        "grader_verified": false, "answered": 1, "questions": [
        {"n": 1, "kind": "recall", "prompt": "What does yeast eat?",
         "mark": {"level": "got_it", "comment": "Right, sugar.", "passage": "Yeast eats sugar."}},
        {"n": 2, "kind": "explain", "prompt": "Why does dough rise?", "mark": null}]}}"#;

    #[test]
    fn an_id_is_letters_digits_dash_and_underscore_only() {
        for good in ["q0123abcd", "a-b_c", "Q1"] {
            assert!(valid_id(good), "{good}");
        }
        for bad in ["", "../x", "a/b", "a?b", "a b", "q\n", &"a".repeat(65)] {
            assert!(!valid_id(bad), "{bad:?}");
        }
    }

    #[test]
    fn a_good_answer_is_passed_on_and_a_bad_shape_is_never_a_success() {
        let a = quiz_answer(200, QUIZ, Some("quiz")).unwrap();
        assert_eq!(a["quiz"]["questions"][1]["n"], 2);
        assert!(quiz_answer(200, r#"{"ok": true}"#, Some("quiz")).is_err());
        assert!(quiz_answer(200, r#"{"ok": true, "quiz": null}"#, Some("quiz")).is_err());
        assert!(quiz_answer(200, "not json", Some("quiz")).is_err());
        assert!(quiz_answer(200, r#"{"ok": false}"#, None).is_err());
        assert!(quiz_answer(200, r#"{"ok": true}"#, None).is_ok());
        assert!(quiz_answer(
            200,
            r#"{"ok": true, "summary": {"counts": {}, "again": []}}"#,
            Some("summary")
        )
        .is_ok());
    }

    #[test]
    fn the_backends_own_refusal_code_is_handed_on_unchanged() {
        let body = r#"{"ok": false, "error": "text_too_short", "message": "Too short."}"#;
        let a = quiz_answer(400, body, Some("quiz")).unwrap();
        assert_eq!(a["ok"], false);
        assert_eq!(a["error"], "text_too_short");
        assert_eq!(a["message"], "Too short.");
        // The feature's own 404 is a refusal, not a missing feature.
        let nf = quiz_answer(
            404,
            r#"{"ok": false, "error": "not_found", "message": "x"}"#,
            None,
        )
        .unwrap();
        assert_eq!(nf["error"], "not_found");
        let down = quiz_answer(
            503,
            r#"{"ok": false, "error": "model_unavailable", "message": "x"}"#,
            Some("quiz"),
        )
        .unwrap();
        assert_eq!(down["error"], "model_unavailable");
    }

    #[test]
    fn a_backend_with_no_quiz_says_so_and_never_succeeds() {
        for old in [404, 501] {
            for body in ["", "Not Found", "{}"] {
                assert_eq!(quiz_answer(old, body, None).unwrap_err(), QUIZ_MISSING);
            }
        }
    }

    #[test]
    fn hidden_quiz_keeps_numbers_and_levels_but_no_words() {
        let a = quiz_answer(200, QUIZ, Some("quiz")).unwrap();
        let hidden = redact_answer(a);
        let s = hidden.to_string();
        for word in ["yeast", "Yeast", "sugar", "Bread", "dough"] {
            assert!(!s.contains(word), "{word} leaked: {s}");
        }
        assert_eq!(hidden["hidden"], true);
        assert_eq!(hidden["quiz"]["hidden"], true);
        assert_eq!(hidden["quiz"]["grader_verified"], false);
        assert_eq!(hidden["quiz"]["answered"], 1);
        assert_eq!(hidden["quiz"]["questions"][0]["mark"]["level"], "got_it");
        assert_eq!(hidden["quiz"]["questions"][1]["n"], 2);
        assert!(hidden["quiz"]["questions"][1]["mark"].is_null());
    }

    #[test]
    fn a_crisis_answer_passes_through_and_its_help_words_are_never_hidden() {
        let body = r#"{"ok": true, "crisis": true, "message": "Call **988** any time.",
            "quiz": {"id": "abc", "title": "Bread", "grader_verified": false, "answered": 0,
            "questions": [{"n": 1, "kind": "recall", "prompt": "What is yeast?", "mark": null}]}}"#;
        let a = quiz_answer(200, body, Some("mark")).unwrap();
        assert_eq!(a["crisis"], true);
        let hidden = redact_answer(a);
        assert_eq!(hidden["message"], "Call **988** any time.");
        assert_eq!(hidden["crisis"], true);
        assert_eq!(hidden["quiz"]["questions"][0]["prompt"], "");
        assert!(hidden["quiz"]["questions"][0]["mark"].is_null());
        // A crisis flag with no words is not readable; an ordinary answer with
        // no mark still is not either.
        let bare = r#"{"ok": true, "crisis": true, "quiz": {}}"#;
        assert_eq!(
            quiz_answer(200, bare, Some("mark")).unwrap_err(),
            UNREADABLE
        );
        let plain = r#"{"ok": true, "quiz": {}}"#;
        assert_eq!(
            quiz_answer(200, plain, Some("mark")).unwrap_err(),
            UNREADABLE
        );
        // The crisis pass-through applies to the answer route only.
        assert_eq!(
            quiz_answer(200, body, Some("summary")).unwrap_err(),
            UNREADABLE
        );
    }

    #[test]
    fn a_hidden_mark_loses_its_comment_and_passage() {
        let mut a = serde_json::json!({"ok": true, "mark": {"level": "partly",
            "comment": "Nearly.", "passage": "the source"}, "quiz": {"questions": []}});
        a = redact_answer(a);
        assert_eq!(a["mark"]["level"], "partly");
        assert_eq!(a["mark"]["comment"], "");
        assert_eq!(a["mark"]["passage"], "");
        // A refusal has nothing to hide and is left as it is.
        let refusal = serde_json::json!({"ok": false, "error": "not_found", "message": "m"});
        assert_eq!(redact_answer(refusal.clone()), refusal);
    }
}
