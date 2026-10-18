//! Brain -> "People and things" -> "Person dossier" (LM-4): one click on a
//! person opens the read-only dossier `jarvis_people_crm.build_person_dossier()`
//! already builds (Pillar 16 / #540; JARVIS-API section 143).
//!
//! THE ONE READ
//!
//! [`people_dossier`] asks `GET /api/people/dossier?name=`, the owner-only
//! route added to `jarvis_brain_reads.py`'s existing install (no new module,
//! no patch, no registration). The name comes from PAGE INPUT - the name of a
//! person the PC itself already listed - so it is %-encoded here and never
//! glued into a URL raw. A read: nothing waits on a stale link, nothing is
//! written, no card is raised, no model sees it.
//!
//! THE HIDING RULE, IN RUST
//!
//! A dossier's every section is the owner's own records, so while App lock is
//! locked OR "Hide memory lists and chat history" is on the command asks the PC
//! for NOTHING and answers with one plain sentence ([`withheld_answer`]). The
//! same gate runs again AFTER the answer arrives, because the lock can turn on
//! while the read is out. The withheld answer carries no name, no fact, no
//! count and no mail - so a page script cannot read round it.
//!
//! Owner-only is the backend's rule (`jarvis_owner_check.from_this_pc`, before
//! the module is imported or the name is read). This window only ever talks to
//! `127.0.0.1`.

use tauri::AppHandle;

use super::guardian::encode;
use super::READ_TIMEOUT;
use crate::commands;

/// The one route, literal, so a page cannot build it.
pub(crate) const DOSSIER_PATH: &str = "/api/people/dossier";

/// While App lock or the hidden lists are on, this is the only sentence the
/// card gets. It names no person, no fact, no count and no file.
pub(crate) const HIDDEN_WORDS: &str =
    "Hidden while App lock or \"Hide memory lists and chat history\" is on.";

/// A PC whose backend predates the route.
pub(crate) const MISSING: &str = "Your PC's Jarvis does not have the person dossier \
     yet. Run apply-patches.ps1 on the PC.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

/// The two flags that hide the dossier: App lock, and "Hide memory lists and
/// chat history". Pure so the pair can be tested without a window.
pub(crate) fn hidden_flags(app_lock: bool, hide_lists: bool) -> bool {
    app_lock || hide_lists
}

/// Is the dossier hidden right now? Both flags from the same store the rest of
/// the app uses; never a cached copy.
pub(crate) fn words_hidden(app: &AppHandle) -> bool {
    hidden_flags(
        crate::lock::app_locked(app),
        crate::lock::private_hidden(app),
    )
}

/// The one hidden answer the card draws: a sentence and nothing else - no
/// name, no fact, no count, no mail.
pub(crate) fn withheld_answer(words: &str) -> serde_json::Value {
    serde_json::json!({
        "ok": false,
        "withheld": true,
        "why": words,
        "text": words,
        "name": "",
        "private": true,
        "made": 0.0,
        "states": {},
        "read": [],
    })
}

/// The refusal shape for a PC that cannot answer yet: the same dossier shape,
/// so the card can always use one renderer.
pub(crate) fn missing_answer() -> serde_json::Value {
    serde_json::json!({
        "ok": false,
        "withheld": false,
        "why": MISSING,
        "text": MISSING,
        "name": "",
        "private": true,
        "made": 0.0,
        "states": {},
        "read": [],
    })
}

/// The request line, built only from the encoded name.
pub(crate) fn dossier_path(name: &str) -> String {
    format!("{DOSSIER_PATH}?name={}", encode(name))
}

/// One person's read-only dossier. While hidden, the PC is not asked at all.
#[tauri::command]
pub async fn people_dossier(app: AppHandle, name: String) -> Result<serde_json::Value, String> {
    if words_hidden(&app) {
        return Ok(withheld_answer(HIDDEN_WORDS));
    }
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{}", dossier_path(&name)))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    // An older PC keeps saying what its other Brain modules say: update it.
    if status == 404 || status == 501 {
        return Ok(missing_answer());
    }
    let answer =
        serde_json::from_str::<serde_json::Value>(&text).map_err(|_| UNREADABLE.to_string())?;
    // The lock or the hidden lists can turn on while the read is out: never
    // hand the dossier over after that happened (the same rule the file
    // history drawer's answers keep).
    if words_hidden(&app) {
        return Ok(withheld_answer(HIDDEN_WORDS));
    }
    Ok(answer)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn either_switch_hides_the_dossier() {
        assert!(!hidden_flags(false, false));
        assert!(hidden_flags(true, false), "App lock must hide it");
        assert!(hidden_flags(false, true), "the hidden lists must hide it");
        assert!(hidden_flags(true, true));
    }

    #[test]
    fn the_withheld_answer_names_nothing() {
        let value = withheld_answer(HIDDEN_WORDS);
        assert_eq!(value["withheld"], true);
        assert_eq!(value["ok"], false);
        assert_eq!(value["name"], "");
        assert_eq!(value["why"], HIDDEN_WORDS);
        // No dossier section in it at all.
        assert!(value.get("active_facts").is_none());
        assert!(value.get("recent_email").is_none());
        assert!(value.get("recent_chat").is_none());
        assert!(value.get("commitments").is_none());
        assert!(value.get("next_event").is_none());
    }

    #[test]
    fn the_path_encodes_the_name() {
        assert_eq!(dossier_path("Priya"), "/api/people/dossier?name=Priya");
        assert_eq!(
            dossier_path("Ana Mara"),
            "/api/people/dossier?name=Ana%20Mara"
        );
        // A name can never add a parameter of its own.
        assert_eq!(
            dossier_path("x&hidden=1"),
            "/api/people/dossier?name=x%26hidden%3D1"
        );
        assert_eq!(dossier_path("Zoë"), "/api/people/dossier?name=Zo%C3%AB");
    }

    #[test]
    fn a_missing_pc_answers_in_the_same_shape() {
        let value = missing_answer();
        assert_eq!(value["ok"], false);
        assert_eq!(value["withheld"], false);
        assert_eq!(value["name"], "");
        assert!(value["why"]
            .as_str()
            .unwrap_or("")
            .contains("apply-patches.ps1"));
    }

    #[test]
    fn a_real_answer_that_arrives_after_the_lock_is_replaced_whole() {
        // The pure half of the command's post-read gate: the replacement keeps
        // nothing from the answer it replaces.
        let real = serde_json::json!({
            "ok": true, "withheld": false, "name": "Priya",
            "active_facts": [{"id": 1, "text": "Sister, lives in Lisbon"}],
            "text": "Priya - person dossier.\n- Sister, lives in Lisbon"
        });
        let hidden = withheld_answer(HIDDEN_WORDS);
        let json = serde_json::to_string(&hidden).unwrap();
        assert!(!json.contains("Priya"));
        assert!(!json.contains("Lisbon"));
        assert!(!json.contains("Sister"));
        assert_eq!(hidden["name"], "");
        // And the real answer really did hold those words, so this is not a
        // test that passes against nothing.
        assert!(serde_json::to_string(&real).unwrap().contains("Lisbon"));
    }
}
