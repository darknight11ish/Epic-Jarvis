//! Review decks (the owner's decision of 2026-09-30; JARVIS-API.md section
//! 102; `docs/QUIZ-DECKS-DESIGN.md`, "Slice contract (frozen)" C4; backend
//! `jarvis_decks.py`).
//!
//! Questions kept from a quiz live in a sealed store on the PC and are asked
//! again on a spaced schedule the PC works out. Eleven commands, one per
//! route, each its own power, modelled on [`super::quiz`] and
//! [`super::goals`]:
//!
//! * [`brain_decks`] - `GET /api/decks`: the deck list, the counts and the
//!   plain "N cards ready" line. A read.
//! * [`brain_decks_create`] - `POST /api/decks {"name"}`: an empty deck.
//! * [`brain_decks_settings`] - `POST /api/decks/settings {"new_per_day"}`.
//! * [`brain_decks_act`] - `POST /api/decks/<id>/act`: rename, pause, resume
//!   or delete one deck.
//! * [`brain_decks_cards`] - `GET /api/decks/<id>/cards`: one deck's cards.
//! * [`brain_decks_card_act`] - `POST /api/decks/<id>/cards/<cid>/act`: edit
//!   or delete one card.
//! * [`brain_review`], [`brain_review_reveal`], [`brain_review_rate`],
//!   [`brain_review_more`] - the review session.
//!
//! No card is raised anywhere: the owner's own tap saves the owner's own
//! words on the PC and nothing leaves it. Every write is held on a stale link
//! (rule 4). This app keeps nothing of a deck: no name, no front, no back.
//!
//! While "Windows Hello for memory lists and chat history" (lock.rs) hides
//! the private lists, deck names, fronts, backs and passages are taken out of
//! every answer here, in Rust, so a page script cannot read round it. The
//! counts, `line` and the next-ready day stay - they say nothing about the
//! owner's words. **Reviewing is unavailable while hidden**: the four review
//! commands do not ask the PC at all and answer `hidden: true`, so a card is
//! never even fetched.
//!
//! The backend's own refusals (`{"ok": false, "error": <code>, "message":
//! ...}`) are handed on unchanged so the page can show the PC's own message;
//! this file never rewords them and never invents a success.
//!
//! The answer-reading and redacting functions are plain functions of
//! (status, body) so their tests run without a Tauri app or a network.

use tauri::AppHandle;

use super::quiz::valid_id;
use super::{require_link_live, READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

/// A PC whose backend has no study decks yet.
pub(crate) const DECKS_MISSING: &str =
    "Your PC's Jarvis does not have study decks yet - run apply-patches.ps1 on the PC.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// The deck (or card) is not there any more.
pub(crate) const NO_SUCH_DECK: &str = "That deck is not there any more.";

/// What the four review commands answer while the private lists are hidden.
pub(crate) const REVIEW_HIDDEN: &str = "Turn off Hide memory lists to review";

/// The longest a deck name may be (JARVIS-API 102.2 `limits.name`).
const NAME_MAX: usize = 60;
/// The longest a card's front (500) or back (2,000) may be.
const FRONT_MAX: usize = 500;
const BACK_MAX: usize = 2000;
/// New cards a day: 0 to 20.
const NEW_PER_DAY_MAX: i64 = 20;

const RATINGS: [&str; 4] = ["again", "hard", "good", "easy"];

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

/// A body the backend itself classified as a refusal: `{"ok": false,
/// "error": "<code>", ...}`. `None` for any other shape, which is how a
/// backend with no decks at all (a bare 404) is told apart from the feature's
/// own `deck_not_found`.
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

/// The reading of any answer. `need` is a field a success must carry and
/// that is not null (`None`: only `ok: true`). A refusal the backend
/// classified comes back as `Ok` with `ok: false` intact.
pub(crate) fn decks_answer(
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
        return Err(DECKS_MISSING.to_string());
    }
    Err(commands::backend_refusal(status, body))
}

fn blank(obj: &mut serde_json::Map<String, serde_json::Value>, keys: &[&str]) {
    for key in keys {
        if obj.contains_key(*key) {
            obj.insert((*key).into(), serde_json::json!(""));
        }
    }
}

/// One deck with its name taken out. Counts, flags and `kind` stay.
fn redact_deck(deck: &mut serde_json::Value) {
    if let Some(o) = deck.as_object_mut() {
        blank(o, &["name"]);
    }
}

/// One card with its words taken out (front, back, passage, key label
/// stays: it is the PC's fixed sentence, not the owner's).
fn redact_card(card: &mut serde_json::Value) {
    if let Some(o) = card.as_object_mut() {
        blank(o, &["front", "back", "passage"]);
    }
}

/// Any answer of this file with the owner's words taken out, for while the
/// private lists are hidden. Counts, `line`, `next_ready_day` and every id
/// stay. A refusal has nothing to hide and is left as it is.
pub(crate) fn redact_answer(mut answer: serde_json::Value) -> serde_json::Value {
    if answer.get("ok").and_then(|o| o.as_bool()) != Some(true) {
        return answer;
    }
    if let Some(obj) = answer.as_object_mut() {
        if let Some(serde_json::Value::Array(decks)) = obj.get_mut("decks") {
            decks.iter_mut().for_each(redact_deck);
        }
        if let Some(deck) = obj.get_mut("deck") {
            redact_deck(deck);
        }
        if let Some(serde_json::Value::Array(cards)) = obj.get_mut("cards") {
            cards.iter_mut().for_each(redact_card);
        }
        if let Some(card) = obj.get_mut("card") {
            redact_card(card);
        }
        if let Some(next) = obj.get_mut("next") {
            redact_card(next);
        }
        if let Some(back) = obj.get_mut("back").and_then(|b| b.as_object_mut()) {
            blank(back, &["answer", "passage"]);
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

/// The answer of a review command while the private lists are hidden: no
/// call was made, so nothing about a card is known here.
pub(crate) fn review_hidden_answer() -> serde_json::Value {
    serde_json::json!({ "ok": true, "hidden": true, "message": REVIEW_HIDDEN })
}

fn bad_input(message: &str) -> Result<serde_json::Value, String> {
    Ok(serde_json::json!({ "ok": false, "error": "bad_request", "message": message }))
}

/// Characters, not bytes: the PC counts characters.
fn chars(s: &str) -> usize {
    s.chars().count()
}

async fn get(app: &AppHandle, path: &str, need: Option<&str>) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{path}"))
        .headers(commands::jarvis_headers(app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    decks_answer(status, &body, need)
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
    decks_answer(status, &text, need)
}

/// The deck list, the counts and the "N cards ready" line. A read.
#[tauri::command]
pub async fn brain_decks(app: AppHandle) -> Result<serde_json::Value, String> {
    let answer = get(&app, "/api/decks", Some("decks")).await?;
    Ok(hide_if_private(&app, answer))
}

/// A new, empty deck. No card. Held on a stale link.
#[tauri::command]
pub async fn brain_decks_create(app: AppHandle, name: String) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let trimmed = name.trim();
    if trimmed.is_empty() || chars(trimmed) > NAME_MAX {
        return bad_input("A deck name is 1 to 60 characters.");
    }
    let answer = post(
        &app,
        "/api/decks",
        serde_json::json!({ "name": trimmed }),
        Some("deck"),
    )
    .await?;
    Ok(hide_if_private(&app, answer))
}

/// New cards a day, 0 to 20. A setting; no card. Held on a stale link.
#[tauri::command]
pub async fn brain_decks_settings(
    app: AppHandle,
    new_per_day: i64,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    if !(0..=NEW_PER_DAY_MAX).contains(&new_per_day) {
        return bad_input("New cards a day is a whole number from 0 to 20.");
    }
    post(
        &app,
        "/api/decks/settings",
        serde_json::json!({ "new_per_day": new_per_day }),
        Some("new_per_day"),
    )
    .await
}

/// Rename, pause, resume or delete one deck. Delete is immediate once the
/// page has asked "are you sure?". Held on a stale link.
#[tauri::command]
pub async fn brain_decks_act(
    app: AppHandle,
    id: String,
    action: String,
    name: Option<String>,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    if !valid_id(&id) {
        return Err(NO_SUCH_DECK.to_string());
    }
    let body = match action.as_str() {
        "rename" => {
            let n = name.unwrap_or_default();
            let n = n.trim();
            if n.is_empty() || chars(n) > NAME_MAX {
                return bad_input("A deck name is 1 to 60 characters.");
            }
            serde_json::json!({ "do": "rename", "name": n })
        }
        "pause" | "resume" | "delete" => serde_json::json!({ "do": action }),
        _ => return bad_input("That is not something a deck can do."),
    };
    let answer = post(&app, &format!("/api/decks/{id}/act"), body, None).await?;
    Ok(hide_if_private(&app, answer))
}

/// One deck's cards. A read; the words are taken out while hidden.
#[tauri::command]
pub async fn brain_decks_cards(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    if !valid_id(&id) {
        return Err(NO_SUCH_DECK.to_string());
    }
    let answer = get(&app, &format!("/api/decks/{id}/cards"), Some("cards")).await?;
    Ok(hide_if_private(&app, answer))
}

/// Edit a card's front or back, or delete the card. Held on a stale link.
#[tauri::command]
pub async fn brain_decks_card_act(
    app: AppHandle,
    id: String,
    cid: String,
    action: String,
    front: Option<String>,
    back: Option<String>,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    if !valid_id(&id) || !valid_id(&cid) {
        return Err(NO_SUCH_DECK.to_string());
    }
    let body = match action.as_str() {
        "edit" => {
            let mut b = serde_json::json!({ "do": "edit" });
            if let Some(f) = &front {
                if f.trim().is_empty() || chars(f) > FRONT_MAX {
                    return bad_input("The front of a card is 1 to 500 characters.");
                }
                b["front"] = serde_json::json!(f);
            }
            if let Some(k) = &back {
                if chars(k) > BACK_MAX {
                    return bad_input("The back of a card is at most 2,000 characters.");
                }
                b["back"] = serde_json::json!(k);
            }
            if front.is_none() && back.is_none() {
                return bad_input("Change the front or the back first.");
            }
            b
        }
        "delete" => serde_json::json!({ "do": "delete" }),
        _ => return bad_input("That is not something a card can do."),
    };
    let answer = post(
        &app,
        &format!("/api/decks/{id}/cards/{cid}/act"),
        body,
        None,
    )
    .await?;
    Ok(hide_if_private(&app, answer))
}

/// The next card to review. A read. Not asked of the PC while hidden.
#[tauri::command]
pub async fn brain_review(
    app: AppHandle,
    deck: Option<String>,
) -> Result<serde_json::Value, String> {
    if crate::lock::private_hidden(&app) {
        return Ok(review_hidden_answer());
    }
    match deck.filter(|d| !d.is_empty()) {
        Some(d) if !valid_id(&d) => Err(NO_SUCH_DECK.to_string()),
        Some(d) => get(&app, &format!("/api/review?deck={d}"), Some("state")).await,
        None => get(&app, "/api/review", Some("state")).await,
    }
}

/// Shows a card's back. A card can be rated only after this. Held on a stale
/// link; not asked of the PC while hidden.
#[tauri::command]
pub async fn brain_review_reveal(
    app: AppHandle,
    card: String,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    if !valid_id(&card) {
        return Err(NO_SUCH_DECK.to_string());
    }
    if crate::lock::private_hidden(&app) {
        return Ok(review_hidden_answer());
    }
    post(
        &app,
        "/api/review/reveal",
        serde_json::json!({ "card": card }),
        Some("back"),
    )
    .await
}

/// The owner's own rating of a revealed card. Held on a stale link.
#[tauri::command]
pub async fn brain_review_rate(
    app: AppHandle,
    card: String,
    rating: String,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    if !valid_id(&card) {
        return Err(NO_SUCH_DECK.to_string());
    }
    if !RATINGS.contains(&rating.as_str()) {
        return bad_input("Choose how it went first.");
    }
    if crate::lock::private_hidden(&app) {
        return Ok(review_hidden_answer());
    }
    post(
        &app,
        "/api/review/rate",
        serde_json::json!({ "card": card, "rating": rating }),
        Some("state"),
    )
    .await
}

/// "Do 10 more": raises the run's limit by 10. Held on a stale link.
#[tauri::command]
pub async fn brain_review_more(
    app: AppHandle,
    deck: Option<String>,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let body = match deck.filter(|d| !d.is_empty()) {
        Some(d) if !valid_id(&d) => return Err(NO_SUCH_DECK.to_string()),
        Some(d) => serde_json::json!({ "deck": d }),
        None => serde_json::json!({}),
    };
    if crate::lock::private_hidden(&app) {
        return Ok(review_hidden_answer());
    }
    post(&app, "/api/review/more", body, Some("state")).await
}

#[cfg(test)]
mod tests {
    use super::*;

    const FIXTURE: &str = include_str!("../../../tests/fixtures/decks-words.json");

    fn sample(name: &str) -> String {
        let all: serde_json::Value = serde_json::from_str(FIXTURE).unwrap();
        all["samples"][name].to_string()
    }

    #[test]
    fn a_good_answer_is_passed_on_and_a_bad_shape_is_never_a_success() {
        let a = decks_answer(200, &sample("decks"), Some("decks")).unwrap();
        assert_eq!(a["decks"][0]["cards"], 8);
        assert_eq!(a["line"], "3 cards ready");
        assert!(decks_answer(200, r#"{"ok": true}"#, Some("decks")).is_err());
        assert!(decks_answer(200, r#"{"ok": true, "decks": null}"#, Some("decks")).is_err());
        assert!(decks_answer(200, "not json", Some("decks")).is_err());
        assert!(decks_answer(200, r#"{"ok": false}"#, None).is_err());
        assert!(decks_answer(200, r#"{"ok": true}"#, None).is_ok());
        // A review card that is null is fine; a review with no state is not.
        assert!(decks_answer(200, &sample("review_card"), Some("state")).is_ok());
        assert!(decks_answer(200, r#"{"ok": true, "card": null}"#, Some("state")).is_err());
    }

    #[test]
    fn the_backends_own_refusal_code_is_handed_on_unchanged() {
        for (status, code) in [
            (400, "bad_deck_name"),
            (404, "deck_not_found"),
            (404, "card_not_found"),
            (409, "not_revealed"),
            (409, "deck_paused"),
            (409, "too_many_decks"),
            (503, "deck_unavailable"),
        ] {
            let body = format!(r#"{{"ok": false, "error": "{code}", "message": "PC words."}}"#);
            let a = decks_answer(status, &body, Some("deck")).unwrap();
            assert_eq!(a["ok"], false, "{code}");
            assert_eq!(a["error"], code);
            assert_eq!(a["message"], "PC words.");
        }
    }

    #[test]
    fn a_backend_with_no_decks_says_so_and_never_succeeds() {
        for old in [404, 501] {
            for body in ["", "Not Found", "{}"] {
                assert_eq!(
                    decks_answer(old, body, None).unwrap_err(),
                    DECKS_MISSING,
                    "{old} {body:?}"
                );
            }
        }
    }

    #[test]
    fn hidden_decks_keep_counts_and_the_line_but_no_words() {
        let a = decks_answer(200, &sample("decks"), Some("decks")).unwrap();
        let hidden = redact_answer(a);
        let s = hidden.to_string();
        for word in ["Plants", "Verbos"] {
            assert!(!s.contains(word), "{word} leaked: {s}");
        }
        assert_eq!(hidden["hidden"], true);
        assert_eq!(hidden["decks"][0]["name"], "");
        assert_eq!(hidden["decks"][0]["cards"], 8);
        assert_eq!(hidden["decks"][0]["ready"], 3);
        assert_eq!(hidden["decks"][1]["paused"], true);
        assert_eq!(hidden["decks"][0]["id"], "d1a2b3c4d5e6");
        assert_eq!(hidden["line"], "3 cards ready");
        assert_eq!(hidden["next_ready_day"], "2026-10-03");
        assert_eq!(hidden["new_per_day"], 5);
    }

    #[test]
    fn hidden_cards_lose_front_back_and_passage_and_a_hidden_review_card_too() {
        let cards = redact_answer(decks_answer(200, &sample("cards"), Some("cards")).unwrap());
        let s = cards.to_string();
        for word in ["Plants", "sunlight", "Chlorophyll"] {
            assert!(!s.contains(word), "{word} leaked: {s}");
        }
        assert_eq!(cards["cards"][0]["id"], "c1a2b3c4d5e6");
        assert_eq!(cards["cards"][0]["kind"], "recall");
        let review =
            redact_answer(decks_answer(200, &sample("review_card"), Some("state")).unwrap());
        assert!(!review.to_string().contains("sunlight"));
        assert_eq!(review["ready"], 3);
        assert_eq!(review["line"], "3 cards ready");
        let rate = redact_answer(decks_answer(200, &sample("rate"), Some("state")).unwrap());
        assert!(!rate.to_string().contains("Second card"));
        assert_eq!(rate["comes_back"], "2026-10-03");
        let reveal = redact_answer(decks_answer(200, &sample("reveal"), Some("back")).unwrap());
        assert!(!reveal.to_string().contains("Chlorophyll"));
        // A refusal has nothing to hide and is left as it is.
        let refusal = serde_json::json!({"ok": false, "error": "deck_not_found", "message": "m"});
        assert_eq!(redact_answer(refusal.clone()), refusal);
    }

    #[test]
    fn an_unavailable_list_is_read_with_its_why_word_for_word() {
        let a = decks_answer(200, &sample("decks_unavailable"), Some("decks")).unwrap();
        assert_eq!(a["available"], false);
        assert_eq!(a["decks"].as_array().unwrap().len(), 0);
        assert_eq!(
            a["why"],
            "Decks are not set up on this PC: no key in Credential Manager."
        );
    }

    #[test]
    fn a_hidden_review_never_asks_the_pc() {
        let a = review_hidden_answer();
        assert_eq!(a["ok"], true);
        assert_eq!(a["hidden"], true);
        assert_eq!(a["message"], "Turn off Hide memory lists to review");
        assert!(a.get("card").is_none());
    }

    #[test]
    fn the_shared_words_agree_with_the_fixture() {
        let all: serde_json::Value = serde_json::from_str(FIXTURE).unwrap();
        assert_eq!(all["words"]["review_hidden"], REVIEW_HIDDEN);
        assert_eq!(all["ratings"], serde_json::json!(RATINGS));
    }

    #[test]
    fn the_input_limits_count_characters_like_the_pc() {
        assert_eq!(chars("ñandú"), 5);
        assert_eq!(chars(&"¿".repeat(60)), 60);
        const {
            assert!(
                NAME_MAX == 60 && FRONT_MAX == 500 && BACK_MAX == 2000 && NEW_PER_DAY_MAX == 20
            );
        }
    }
}
