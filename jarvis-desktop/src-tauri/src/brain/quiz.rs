//! Quiz me on a text (the owner's "go ahead", 2026-09-30;
//! `docs/STUDY-FROM-TEXT-DESIGN.md` section 11; JARVIS-API.md section 98;
//! backend `jarvis_quiz.py`).
//!
//! The owner pastes some text, the PC's local model writes a few questions,
//! and the owner types an answer to each. Five commands, one per route, each
//! its own power, modelled on [`super::goals`]:
//!
//! * [`brain_quiz_start`] - `POST /api/quiz {"text", "count"?, "title"?}`;
//!   Spanish practice (JARVIS-API section 102.4) adds `mode`, `level`,
//!   `exercise` and `topic`, and its `text` is optional.
//! * [`brain_quiz_get`] - `GET /api/quiz/<id>`: a read, used to paint the
//!   quiz again after "Show" ends a hidden state.
//! * [`brain_quiz_answer`] - `POST /api/quiz/<id>/answer {"n", "answer"}`.
//! * [`brain_quiz_finish`] - `POST /api/quiz/<id>/finish`; with the optional
//!   `keep` body (JARVIS-API section 102.1) it keeps chosen questions in a
//!   deck first. The app sends only each card's `n` and `answer`.
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
                // PC's help words instead, and passes through as it is. So does
                // a finish that had a crisis phrase in a kept back (102.1).
                (matches!(need, Some("mark") | Some("summary")) && is_crisis(v))
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
        // The key word is the owner's text too (Spanish practice); a null stays
        // null so a mark with no key still reads as one.
        if m.get("expected").is_some_and(|e| e.is_string()) {
            m.insert("expected".into(), serde_json::json!(""));
        }
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

/// The six levels, and the four exercises, and the two modes, as the PC
/// names them (JARVIS-API section 102.4).
const LEVELS: [&str; 6] = ["A1", "A2", "B1", "B2", "C1", "C2"];
const EXERCISES: [&str; 4] = ["translate", "blank", "complete", "mixed"];
const TOPIC_MAX: usize = 60;

/// The body of `POST /api/quiz` for the owner's choices, or the plain reason
/// it cannot be sent. Text mode sends what it always sent; Spanish sends
/// `mode` and only the choices that were made, and `text` only if there is
/// some (blank means "the model writes the sentences").
pub(crate) fn start_body(
    text: Option<&str>,
    count: Option<i64>,
    title: Option<&str>,
    mode: Option<&str>,
    level: Option<&str>,
    exercise: Option<&str>,
    topic: Option<&str>,
) -> Result<serde_json::Value, String> {
    let spanish = match mode {
        None | Some("text") => false,
        Some("spanish") => true,
        Some(_) => return Err("That is not a quiz mode.".to_string()),
    };
    let mut body = serde_json::json!({});
    let text = text.filter(|t| !t.trim().is_empty());
    match (text, spanish) {
        (Some(t), _) => body["text"] = serde_json::json!(t),
        (None, false) => body["text"] = serde_json::json!(""),
        (None, true) => {}
    }
    if let Some(count) = count {
        body["count"] = serde_json::json!(count);
    }
    if let Some(title) = title.filter(|t| !t.trim().is_empty()) {
        body["title"] = serde_json::json!(title);
    }
    if spanish {
        body["mode"] = serde_json::json!("spanish");
        if let Some(level) = level.filter(|l| !l.is_empty()) {
            if !LEVELS.contains(&level) {
                return Err("That is not a level from A1 to C2.".to_string());
            }
            body["level"] = serde_json::json!(level);
        }
        if let Some(exercise) = exercise.filter(|e| !e.is_empty()) {
            if !EXERCISES.contains(&exercise) {
                return Err("That is not one of the exercises.".to_string());
            }
            body["exercise"] = serde_json::json!(exercise);
        }
        if let Some(topic) = topic.map(str::trim).filter(|t| !t.is_empty()) {
            if topic.chars().count() > TOPIC_MAX {
                return Err("Keep the topic to 60 characters or fewer.".to_string());
            }
            body["topic"] = serde_json::json!(topic);
        }
    }
    Ok(body)
}

/// Writes the questions for a pasted text (or, in Spanish practice, for a
/// level, an exercise and an optional topic). The text goes to the PC's
/// local model only. No card. Held on a stale link.
#[tauri::command]
#[allow(clippy::too_many_arguments)]
pub async fn brain_quiz_start(
    app: AppHandle,
    text: Option<String>,
    count: Option<i64>,
    title: Option<String>,
    mode: Option<String>,
    level: Option<String>,
    exercise: Option<String>,
    topic: Option<String>,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let body = start_body(
        text.as_deref(),
        count,
        title.as_deref(),
        mode.as_deref(),
        level.as_deref(),
        exercise.as_deref(),
        topic.as_deref(),
    )?;
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

/// The longest a kept back may be (JARVIS-API 102.1).
const KEEP_ANSWER_MAX: usize = 2000;
/// The longest a new deck's name may be.
const KEEP_NAME_MAX: usize = 60;

/// The `keep` body for finish, rebuilt from the page's request so that only
/// what the contract lets an app send goes out: the deck (an id, or null with
/// a `new_deck` name) and, per card, only `n` and `answer`. The PC takes each
/// front and passage from its own open quiz. Errors are plain words.
pub(crate) fn keep_body(keep: &serde_json::Value) -> Result<serde_json::Value, String> {
    let deck = keep.get("deck").cloned().unwrap_or(serde_json::Value::Null);
    let mut out = serde_json::json!({});
    match &deck {
        serde_json::Value::Null => {
            let name = keep
                .get("new_deck")
                .and_then(|n| n.as_str())
                .map(str::trim)
                .unwrap_or("");
            if name.is_empty() || name.chars().count() > KEEP_NAME_MAX {
                return Err("A deck name is 1 to 60 characters.".to_string());
            }
            out["deck"] = serde_json::Value::Null;
            out["new_deck"] = serde_json::json!(name);
        }
        serde_json::Value::String(id) if valid_id(id) => out["deck"] = deck.clone(),
        _ => return Err("Choose a deck or name a new one.".to_string()),
    }
    let cards = keep
        .get("cards")
        .and_then(|c| c.as_array())
        .ok_or_else(|| "Tick at least one question to keep.".to_string())?;
    if cards.is_empty() {
        return Err("Tick at least one question to keep.".to_string());
    }
    let mut sent = Vec::with_capacity(cards.len());
    for card in cards {
        let n = card
            .get("n")
            .and_then(|n| n.as_i64())
            .filter(|n| *n >= 1)
            .ok_or_else(|| "That is not one of this quiz's questions.".to_string())?;
        let answer = card.get("answer").and_then(|a| a.as_str()).unwrap_or("");
        if answer.chars().count() > KEEP_ANSWER_MAX {
            return Err(
                "That answer is too long. Keep it to 2,000 characters or fewer.".to_string(),
            );
        }
        sent.push(serde_json::json!({ "n": n, "answer": answer }));
    }
    out["cards"] = serde_json::Value::Array(sent);
    Ok(out)
}

/// Ends the quiz and asks for the short summary; the PC forgets the quiz.
/// With `keep`, the chosen questions go into a deck first (all or nothing;
/// on a failure the quiz stays open). Held on a stale link.
#[tauri::command]
pub async fn brain_quiz_finish(
    app: AppHandle,
    id: String,
    keep: Option<serde_json::Value>,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    if !valid_id(&id) {
        return Err(NO_SUCH_QUIZ.to_string());
    }
    let mut body = serde_json::json!({});
    if let Some(keep) = keep.filter(|k| !k.is_null()) {
        if crate::lock::private_hidden(&app) {
            return Err("Turn off Hide memory lists to keep questions".to_string());
        }
        body["keep"] = keep_body(&keep)?;
    }
    let answer = post(
        &app,
        &format!("/api/quiz/{id}/finish"),
        body,
        Some("summary"),
    )
    .await?;
    Ok(hide_if_private(&app, answer))
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
        // The crisis pass-through applies to the answer and finish routes
        // (a crisis phrase in a kept back), not to start.
        assert!(quiz_answer(200, body, Some("summary")).is_ok());
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

    #[test]
    fn text_mode_sends_what_it_always_sent() {
        let b = start_body(Some("some text"), None, None, None, None, None, None).unwrap();
        assert_eq!(b, serde_json::json!({"text": "some text"}));
        let b = start_body(
            Some("t"),
            Some(5),
            Some("Bread"),
            Some("text"),
            Some("B1"),
            Some("blank"),
            Some("x"),
        )
        .unwrap();
        assert_eq!(
            b,
            serde_json::json!({"text": "t", "count": 5, "title": "Bread"})
        );
        // No text in Text mode is still sent (the PC refuses it in words).
        assert_eq!(
            start_body(None, None, None, None, None, None, None).unwrap()["text"],
            ""
        );
    }

    #[test]
    fn spanish_mode_sends_its_choices_and_text_only_if_there_is_some() {
        let b = start_body(
            None,
            None,
            None,
            Some("spanish"),
            Some("B1"),
            Some("blank"),
            Some("  food  "),
        )
        .unwrap();
        assert_eq!(
            b,
            serde_json::json!({"mode": "spanish", "level": "B1", "exercise": "blank", "topic": "food"})
        );
        let b = start_body(Some("   "), None, None, Some("spanish"), None, None, None).unwrap();
        assert_eq!(b, serde_json::json!({"mode": "spanish"}));
        let b = start_body(Some("Hola"), None, None, Some("spanish"), None, None, None).unwrap();
        assert_eq!(b["text"], "Hola");
        for level in ["A1", "A2", "B1", "B2", "C1", "C2"] {
            assert!(start_body(None, None, None, Some("spanish"), Some(level), None, None).is_ok());
        }
        for exercise in ["translate", "blank", "complete", "mixed"] {
            assert!(start_body(
                None,
                None,
                None,
                Some("spanish"),
                None,
                Some(exercise),
                None
            )
            .is_ok());
        }
    }

    #[test]
    fn spanish_choices_are_checked_before_anything_is_sent() {
        for bad in [
            start_body(None, None, None, Some("french"), None, None, None),
            start_body(None, None, None, Some("spanish"), Some("D1"), None, None),
            start_body(None, None, None, Some("spanish"), None, Some("speak"), None),
            start_body(
                None,
                None,
                None,
                Some("spanish"),
                None,
                None,
                Some(&"ñ".repeat(61)),
            ),
        ] {
            assert!(bad.is_err());
        }
        // 60 characters is fine even when the bytes are more.
        assert!(start_body(
            None,
            None,
            None,
            Some("spanish"),
            None,
            None,
            Some(&"ñ".repeat(60))
        )
        .is_ok());
    }

    #[test]
    fn keep_sends_only_the_number_and_the_back_of_each_card() {
        let keep = serde_json::json!({"deck": "d1a2b3c4d5e6", "junk": 1, "cards": [
            {"n": 2, "answer": "mi respuesta", "front": "forged", "passage": "forged"},
            {"n": 3, "answer": ""}]});
        let b = keep_body(&keep).unwrap();
        assert_eq!(
            b,
            serde_json::json!({"deck": "d1a2b3c4d5e6", "cards": [
                {"n": 2, "answer": "mi respuesta"}, {"n": 3, "answer": ""}]})
        );
        assert!(!b.to_string().contains("forged"));
        let new = serde_json::json!({"deck": null, "new_deck": "  Plantas  ", "cards": [{"n": 1, "answer": "x"}]});
        let b = keep_body(&new).unwrap();
        assert_eq!(b["deck"], serde_json::Value::Null);
        assert_eq!(b["new_deck"], "Plantas");
    }

    #[test]
    fn keep_refuses_a_bad_request_in_plain_words() {
        let card = serde_json::json!([{"n": 1, "answer": "x"}]);
        for keep in [
            serde_json::json!({"deck": null, "new_deck": "", "cards": card}),
            serde_json::json!({"deck": null, "new_deck": "x".repeat(61), "cards": card}),
            serde_json::json!({"deck": "../x", "cards": card}),
            serde_json::json!({"deck": 5, "cards": card}),
            serde_json::json!({"deck": "d1a2b3c4d5e6", "cards": []}),
            serde_json::json!({"deck": "d1a2b3c4d5e6"}),
            serde_json::json!({"deck": "d1a2b3c4d5e6", "cards": [{"n": 0, "answer": "x"}]}),
            serde_json::json!({"deck": "d1a2b3c4d5e6", "cards": [{"answer": "x"}]}),
            serde_json::json!({"deck": "d1a2b3c4d5e6", "cards": [{"n": 1, "answer": "x".repeat(2001)}]}),
        ] {
            assert!(keep_body(&keep).is_err(), "{keep}");
        }
        assert!(keep_body(&serde_json::json!({"deck": "d1a2b3c4d5e6", "cards": [{"n": 1, "answer": "ñ".repeat(2000)}]})).is_ok());
    }

    #[test]
    fn a_hidden_spanish_mark_loses_its_key_word_but_keeps_the_fixed_label() {
        let fixture: serde_json::Value =
            serde_json::from_str(include_str!("../../../tests/fixtures/decks-cases.json")).unwrap();
        let a = quiz_answer(
            200,
            &fixture["samples"]["spanish_quiz"].to_string(),
            Some("quiz"),
        )
        .unwrap();
        assert_eq!(a["quiz"]["mode"], "spanish");
        let hidden = redact_answer(a);
        let s = hidden.to_string();
        for word in ["está", "Plantas", "libro", "cat"] {
            assert!(!s.contains(word), "{word} leaked: {s}");
        }
        assert_eq!(hidden["quiz"]["questions"][0]["mark"]["expected"], "");
        assert_eq!(hidden["quiz"]["questions"][0]["mark"]["marked_by"], "code");
        assert_eq!(hidden["quiz"]["mode"], "spanish");
        assert!(hidden["quiz"]["notice"].as_str().unwrap().contains("988"));
    }

    #[test]
    fn a_finish_that_kept_questions_is_read_with_its_count_and_a_crisis_one_passes() {
        let fixture: serde_json::Value =
            serde_json::from_str(include_str!("../../../tests/fixtures/decks-cases.json")).unwrap();
        let ok = quiz_answer(
            200,
            &fixture["samples"]["keep_ok"].to_string(),
            Some("summary"),
        )
        .unwrap();
        assert_eq!(ok["kept"], 3);
        let crisis = quiz_answer(
            200,
            &fixture["samples"]["keep_crisis"].to_string(),
            Some("summary"),
        )
        .unwrap();
        assert_eq!(crisis["crisis"], true);
        let dup = r#"{"ok": false, "error": "duplicate_card", "message": "Question 2 is already in that deck."}"#;
        let a = quiz_answer(409, dup, Some("summary")).unwrap();
        assert_eq!(a["error"], "duplicate_card");
    }
}
