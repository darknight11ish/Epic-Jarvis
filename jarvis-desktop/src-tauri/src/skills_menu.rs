//! Settings -> "Skills": the skills menu's PC doors (the owner's decision of
//! 2026-11-02, scope B of `.dsh-scratch/OWNER-QUEUE-2026-11-02/
//! HERMES-SKILLS-RESEARCH.md`; `backend/jarvis_skill_menu.py` and the drop-in
//! folder `plugins/ready/skill-menu/`; JARVIS-API.md section 178).
//!
//! ONE command, settings window only (permissions/surfaces.toml,
//! `settings-surface`). Every action is a pass-through: the PC decides, and
//! this window never decides anything.
//!
//! * `read`         - `GET /api/skills/menu`: every installed skill, every one
//!   turned off, the verdict each was installed with, and the owner's sentence
//!   about a `scripts/` folder staying inert. A read, never held.
//! * `pick_folder`  - the Windows "Select folder" dialog, and nothing else.
//! * `pick_zip`     - the Windows "Open" dialog for one `.zip`.
//! * `scan`         - `POST /api/skills/install {"dry_run": true}`: the
//!   scanner's verdict, its findings and the warning list, so the owner reads
//!   what they are about to be asked about. The PC raises no card for it.
//! * `install`      - `POST /api/skills/install`: the SAME scanner, then ONE
//!   `modify_own_code` card on the PC. Nothing is installed before a person
//!   answers, and a skill the scanner refuses never becomes a card at all.
//! * `import_scan`  - `POST /api/skills/import/scan`: a read-only scan of
//!   `%USERPROFILE%\.hermes\skills`. Installs nothing, raises no card.
//! * `enable`       - `POST /api/skills/state {"on": true}`: one card, then the
//!   skill is installed again from `skills-off\`.
//! * `disable`      - `POST /api/skills/state {"on": false}`: immediate, never
//!   held - it only takes an ability away, and nothing is deleted.
//! * `remove_off`   - `POST /api/skills/state {"remove": true}`: deletes ONE
//!   skill that is ALREADY turned off, i.e. the copy this menu parked in
//!   `skills-off\`. Immediate and never held: it is out of the load path
//!   already, so it only takes something away. It is the one door to that
//!   copy - `brain_remove_skill` cannot see `skills-off\`, because
//!   `jarvis_skills.uninstall` resolves a name only under the skills folder -
//!   and the PC refuses an installed name outright, so the two doors never
//!   reach the same folder.
//! * `edit`         - `POST /api/skills/edit`: the same scanner and the same
//!   ONE card, for a SKILL.md the owner changed here.
//! * `creator_read` - `GET /api/creator/incoming`: the ONE waiting folder and
//!   every skill or plug-in folder in it, each with the scanner's own verdict
//!   and findings. A READ-ONLY scan: it copies, moves and installs nothing and
//!   raises no card (2026-11-09, Wave 13; JARVIS-API section 209).
//! * `creator_install` - `POST /api/creator/install`: ONE staged item, by NAME.
//!   A skill goes through the pack manager's own scanner and its own ONE card,
//!   and lands TURNED OFF; a plug-in is refused before any card, in the pack
//!   manager's own words.
//!
//! The four actions that can raise a card (`install`, `enable`, `edit` and
//! `creator_install`) are held while the event stream is stale (rule 4: never
//! act when the stream is stale). `disable`, the reads and the two pickers are
//! never held.
//!
//! This window never gets a file system of its own: the pickers run here, and
//! only the path the owner chose is sent - to this PC's Jarvis, nowhere else.
//! There is no download, no marketplace and no auto-install anywhere in it.

use std::time::Duration;

use tauri::{AppHandle, Manager};

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

const MENU_PATH: &str = "/api/skills/menu";
const INSTALL_PATH: &str = "/api/skills/install";
const IMPORT_SCAN_PATH: &str = "/api/skills/import/scan";
const STATE_PATH: &str = "/api/skills/state";
const EDIT_PATH: &str = "/api/skills/edit";
/// Creator mode's two routes (2026-11-09, Wave 13; JARVIS-API section 209).
/// The waiting folder is on this PC, so both are answered here and by the PC
/// alone - `jarvis_creator` refuses any other device with its own words.
const CREATOR_INCOMING_PATH: &str = "/api/creator/incoming";
const CREATOR_INSTALL_PATH: &str = "/api/creator/install";

/// What a backend without `jarvis_skill_menu.py` is told. The same sentence the
/// Settings card shows, so the window and the page cannot drift.
pub(crate) const SKILLS_MENU_MISSING: &str =
    "Your PC's Jarvis cannot show the skills menu yet - run apply-patches.ps1 on the PC.";

/// What a PC without `jarvis_creator.py` is told, in the same words the card
/// shows. Creator mode is part of the same Settings card, so the answer names
/// the same one command.
pub(crate) const CREATOR_MISSING: &str =
    "Your PC's Jarvis cannot show Creator mode yet - run apply-patches.ps1 on the PC.";

const STALE: &str =
    "The connection to Jarvis is catching up, so nothing can be sent until it does.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

const READ_TIMEOUT: Duration = Duration::from_secs(20);
/// A `.zip` is unpacked on the PC and every file in it scanned before this
/// answers, so it gets longer than a plain read.
const SCAN_TIMEOUT: Duration = Duration::from_secs(120);
const WRITE_TIMEOUT: Duration = Duration::from_secs(30);
/// A card is answered by a person. The backend bounds its own wait at 900 s
/// (`jarvis_gate.APPROVAL_TIMEOUT`), so this waits for that plus a few seconds
/// for the answer to come back - the same bound `lock::rules` uses.
const CARD_WAIT: Duration = Duration::from_secs(905);

/// One action's request, worked out before anything is sent - so what the page
/// may ask for is a short, checkable list rather than a path to anything.
#[derive(Debug, PartialEq)]
pub(crate) enum Plan {
    /// A read: no body, never held.
    Get(String, Duration),
    /// A picker, which reaches the PC's own dialogs and nothing else.
    PickFolder,
    PickZip,
    /// A write the PC answers with its own words (and, for `install`, `enable`
    /// and `edit`, exactly ONE approval card).
    Post(&'static str, serde_json::Value, Duration),
}

/// Is this action one that raises a card? Only those wait for a live stream.
pub(crate) fn held(action: &str) -> bool {
    matches!(action, "install" | "enable" | "edit" | "creator_install")
}

fn text(value: &Option<String>) -> String {
    value.as_deref().unwrap_or("").trim().to_string()
}

/// What `action` will do, or the words saying why it will not.
pub(crate) fn plan(
    action: &str,
    path: &Option<String>,
    hermes: &Option<String>,
    name: &Option<String>,
    body: &Option<String>,
    accept_warnings: bool,
) -> Result<Plan, String> {
    match action {
        "read" => {
            // A name turns the list read into ONE skill's row, with its own
            // SKILL.md text so the page can show what the owner is editing.
            // The name is `[a-z0-9-]` on the PC's side and the query is never
            // a path, so this cannot reach a file of its own.
            let skill = text(name);
            let route = if skill.is_empty() {
                MENU_PATH.to_string()
            } else {
                format!("{MENU_PATH}?name={skill}")
            };
            Ok(Plan::Get(route, READ_TIMEOUT))
        }
        "pick_folder" => Ok(Plan::PickFolder),
        "pick_zip" => Ok(Plan::PickZip),
        "import_scan" => Ok(Plan::Post(
            IMPORT_SCAN_PATH,
            serde_json::json!({}),
            SCAN_TIMEOUT,
        )),
        "scan" | "install" => {
            // "scan" IS the dry run: one action, no second flag to disagree
            // with it.
            let mut body_out = serde_json::json!({
                "accept_warnings": accept_warnings,
                "dry_run": action == "scan",
            });
            let folder = text(path);
            let rel = text(hermes);
            if !folder.is_empty() {
                body_out["path"] = serde_json::Value::String(folder);
            } else if !rel.is_empty() {
                // A folder the Hermes SCAN named. The page never sends a path
                // for this: the PC joins the name under its own Hermes root.
                body_out["hermes"] = serde_json::Value::String(rel);
            } else {
                return Err("Choose a folder or a .zip first.".to_string());
            }
            Ok(Plan::Post(
                INSTALL_PATH,
                body_out,
                if action == "scan" {
                    SCAN_TIMEOUT
                } else {
                    CARD_WAIT
                },
            ))
        }
        "enable" | "disable" => {
            let skill = text(name);
            if skill.is_empty() {
                return Err("Name a skill first.".to_string());
            }
            Ok(Plan::Post(
                STATE_PATH,
                serde_json::json!({
                    "name": skill,
                    "on": action == "enable",
                    "accept_warnings": accept_warnings,
                }),
                if action == "enable" {
                    CARD_WAIT
                } else {
                    WRITE_TIMEOUT
                },
            ))
        }
        "remove_off" => {
            // Deleting a skill this menu itself parked in `skills-off\`. That
            // copy is beyond `brain_remove_skill` (the PC resolves an uninstall
            // name only under the skills folder), so without this a skill the
            // owner switched off could be switched back on and never got rid
            // of. No card and never held: it is already out of the load path,
            // so this only takes a capability away, exactly like `disable`.
            let skill = text(name);
            if skill.is_empty() {
                return Err("Name a skill first.".to_string());
            }
            Ok(Plan::Post(
                STATE_PATH,
                serde_json::json!({ "name": skill, "remove": true }),
                WRITE_TIMEOUT,
            ))
        }
        "edit" => {
            let skill = text(name);
            if skill.is_empty() {
                return Err("Name a skill first.".to_string());
            }
            let words = body.clone().unwrap_or_default();
            if words.trim().is_empty() {
                return Err("There is nothing to save: the SKILL.md is empty.".to_string());
            }
            Ok(Plan::Post(
                EDIT_PATH,
                serde_json::json!({
                    "name": skill,
                    "text": words,
                    "accept_warnings": accept_warnings,
                }),
                CARD_WAIT,
            ))
        }
        "creator_read" => Ok(Plan::Get(CREATOR_INCOMING_PATH.to_string(), READ_TIMEOUT)),
        "creator_install" => {
            // ONE folder's NAME, never a path: the PC resolves it inside its
            // own waiting folder and refuses anything that is not a plain name.
            let item = text(name);
            if item.is_empty() {
                return Err("Name one folder from the waiting folder first.".to_string());
            }
            Ok(Plan::Post(
                CREATOR_INSTALL_PATH,
                serde_json::json!({
                    "name": item,
                    "accept_warnings": accept_warnings,
                }),
                CARD_WAIT,
            ))
        }
        other => Err(format!("There is no such skills action ({other}).")),
    }
}

/// A read's answer: the PC's own body on 2xx, [`SKILLS_MENU_MISSING`] from a PC
/// without the module, and the PC's own sentence otherwise.
pub(crate) fn menu_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("skills").is_some_and(|s| s.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 {
        return Ok(serde_json::json!({ "ok": false, "why": SKILLS_MENU_MISSING }));
    }
    Err(backend_refusal(status, body))
}

/// A write's answer: the PC's own body on 2xx (a refusal included - the
/// module answers 200 with `ok: false` when a skill was refused and
/// quarantined, and that is information, not an error), the PC's own sentence
/// on 4xx (the warnings to accept, a skill that is off, a bad name), and
/// [`SKILLS_MENU_MISSING`] when the route is not there at all.
pub(crate) fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    change_answer_for(status, body, SKILLS_MENU_MISSING)
}

/// A write's answer with its own "this PC has not got it yet" sentence. Creator
/// mode is a separate module from the skills menu, so a 404 there must not tell
/// the owner to re-run the installer for the wrong reason.
fn change_answer_for(status: u16, body: &str, missing: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.is_object())
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 {
        return Err(missing.to_string());
    }
    if let Some(said) = sentence(body) {
        return Err(said);
    }
    Err(backend_refusal(status, body))
}

/// Creator mode's one write: the same "the PC's own words" rule, with Creator
/// mode's own missing-module sentence when the route is not there at all.
pub(crate) fn creator_change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    change_answer_for(status, body, CREATOR_MISSING)
}

/// Creator mode's read: the waiting folder and its scanned items. `items` must
/// be a list, because a page that cannot find one would quietly show an empty
/// folder - and "nothing waiting" is not the same answer as "I could not ask".
pub(crate) fn creator_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .filter(|v| v.get("items").is_some_and(|i| i.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if status == 404 {
        return Ok(serde_json::json!({
            "ok": false, "available": false, "why": CREATOR_MISSING, "items": []
        }));
    }
    Err(backend_refusal(status, body))
}

/// The PC's own sentence out of a refusal body, whichever key it used.
///
/// `backend_refusal` reads `error` and nothing else. This module answers a
/// refusal with `reason` - and so do the `jarvis_skills.install()` results it
/// passes straight back - so without this the page would show "Jarvis refused
/// the request (HTTP 409)" for a skill that is merely waiting for the owner to
/// accept its warnings. Both keys are the PC's words; the first letter is
/// raised here exactly as `backend_refusal` does it.
fn sentence(body: &str) -> Option<String> {
    let value = serde_json::from_str::<serde_json::Value>(body).ok()?;
    for key in ["error", "reason"] {
        if let Some(words) = value.get(key).and_then(|w| w.as_str()) {
            let said = words.trim();
            if !said.is_empty() {
                let mut s = said.to_string();
                if let Some(first) = s.get(0..1) {
                    let upper = first.to_uppercase();
                    s.replace_range(0..1, &upper);
                }
                return Some(s);
            }
        }
    }
    None
}

fn stale(app: &AppHandle) -> bool {
    app.state::<crate::stream::StreamState>().link().stale
}

/// The skills menu and Creator mode: one command, twelve actions, all of them
/// the PC's.
#[tauri::command]
pub async fn skills_menu(
    app: AppHandle,
    action: String,
    path: Option<String>,
    hermes: Option<String>,
    name: Option<String>,
    text: Option<String>,
    accept_warnings: Option<bool>,
) -> Result<serde_json::Value, String> {
    let step = plan(
        &action,
        &path,
        &hermes,
        &name,
        &text,
        accept_warnings.unwrap_or(false),
    )?;
    if held(&action) && stale(&app) {
        return Err(STALE.to_string());
    }
    match step {
        Plan::PickFolder => {
            let Some(chosen) =
                crate::folders::pick(crate::folders::picker::What::SkillFolder).await?
            else {
                return Ok(serde_json::json!({ "cancelled": true }));
            };
            Ok(serde_json::json!({ "cancelled": false, "path": chosen }))
        }
        Plan::PickZip => {
            let Some(chosen) = crate::folders::pick(crate::folders::picker::What::SkillZip).await?
            else {
                return Ok(serde_json::json!({ "cancelled": true }));
            };
            Ok(serde_json::json!({ "cancelled": false, "path": chosen }))
        }
        Plan::Get(route, timeout) => {
            let base = jarvis_base(&app);
            let response = jarvis_client(Some(timeout))?
                .get(format!("{base}{route}"))
                .headers(jarvis_headers(&app)?)
                .send()
                .await
                .map_err(|e| backend_unreachable(&e, &base))?;
            let status = response.status().as_u16();
            let body = response.text().await.unwrap_or_default();
            if action.starts_with("creator_") {
                creator_answer(status, &body)
            } else {
                menu_answer(status, &body)
            }
        }
        Plan::Post(route, body, timeout) => {
            let base = jarvis_base(&app);
            let response = jarvis_client(Some(timeout))?
                .post(format!("{base}{route}"))
                .headers(jarvis_headers(&app)?)
                .json(&body)
                .send()
                .await
                .map_err(|e| backend_unreachable(&e, &base))?;
            let status = response.status().as_u16();
            let said = response.text().await.unwrap_or_default();
            if action.starts_with("creator_") {
                creator_change_answer(status, &said)
            } else {
                change_answer(status, &said)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{
        change_answer, creator_answer, creator_change_answer, held, menu_answer, plan, Plan,
        CREATOR_MISSING, SKILLS_MENU_MISSING,
    };

    fn none() -> Option<String> {
        None
    }

    #[test]
    fn every_action_the_page_uses_is_planned_and_nothing_else_is() {
        for action in [
            "read",
            "pick_folder",
            "pick_zip",
            "scan",
            "install",
            "import_scan",
            "enable",
            "disable",
            "remove_off",
            "edit",
            "creator_read",
            "creator_install",
        ] {
            assert!(
                plan(
                    action,
                    &Some("C:\\s\\a".into()),
                    &none(),
                    &Some("x".into()),
                    &Some("body".into()),
                    false
                )
                .is_ok(),
                "{action} should be planned"
            );
        }
        assert!(plan("rm -rf", &none(), &none(), &none(), &none(), false).is_err());
        assert!(plan("", &none(), &none(), &none(), &none(), false).is_err());
    }

    #[test]
    fn only_the_three_doors_that_raise_a_card_wait_for_a_live_stream() {
        for action in [
            "read",
            "pick_folder",
            "pick_zip",
            "scan",
            "import_scan",
            "disable",
            "remove_off",
            "creator_read",
        ] {
            assert!(!held(action), "{action} must not be held");
        }
        for action in ["install", "enable", "edit", "creator_install"] {
            assert!(held(action), "{action} raises a card and must be held");
        }
    }

    #[test]
    fn creator_mode_reads_its_folder_and_installs_one_named_item() {
        // A read: no body, never held, and its own route.
        match plan("creator_read", &none(), &none(), &none(), &none(), false) {
            Ok(Plan::Get(route, _)) => assert_eq!(route, "/api/creator/incoming"),
            other => panic!("{other:?}"),
        }
        // An install: ONE name, never a path, and the warnings flag carried.
        match plan(
            "creator_install",
            &Some("C:\\a\\path\\the-page-must-not-send".into()),
            &none(),
            &Some("tidy-desk".into()),
            &none(),
            true,
        ) {
            Ok(Plan::Post(route, body, _)) => {
                assert_eq!(route, "/api/creator/install");
                assert_eq!(body["name"], serde_json::json!("tidy-desk"));
                assert_eq!(body["accept_warnings"], serde_json::json!(true));
                assert!(
                    body.get("path").is_none(),
                    "Creator mode takes a NAME in the waiting folder, never a path"
                );
            }
            other => panic!("{other:?}"),
        }
        assert!(plan(
            "creator_install",
            &none(),
            &none(),
            &Some("   ".into()),
            &none(),
            false
        )
        .unwrap_err()
        .contains("waiting folder"));
    }

    #[test]
    fn creator_answers_say_their_own_missing_module_and_keep_the_pc_s_words() {
        let missing = creator_answer(404, "").unwrap();
        assert_eq!(missing["why"], CREATOR_MISSING);
        assert_eq!(missing["items"], serde_json::json!([]));
        assert!(creator_change_answer(404, "")
            .unwrap_err()
            .contains("Creator mode"));
        // The waiting folder's answer: `items` is a list or it is not an answer
        // the page can honestly show.
        let view = creator_answer(
            200,
            r#"{"ok": true, "folder": "C:\\c\\creator-incoming", "items": []}"#,
        )
        .unwrap();
        assert_eq!(view["items"], serde_json::json!([]));
        assert!(creator_answer(200, r#"{"ok": true, "folder": "x"}"#).is_err());
        // A refusal keeps the PC's own sentence, whichever key it used.
        let said = creator_change_answer(
            200,
            r#"{"ok": false, "refused": true, "reason": "that folder is not a skill"}"#,
        )
        .unwrap();
        assert_eq!(said["refused"], serde_json::json!(true));
        let err = creator_change_answer(
            409,
            r#"{"ok": false, "reason": "this one has warnings to read first"}"#,
        )
        .unwrap_err();
        assert!(err.to_lowercase().contains("warnings"), "{err}");
    }

    #[test]
    fn a_turned_off_skill_is_deleted_on_the_state_route_and_nowhere_else() {
        // The off list's Remove. It must be the SAME route that parked the
        // folder (the PC's own state door), with `remove` and no `on`, so there
        // are two questions on one route rather than a second removal path for
        // an installed skill - that one is still `brain_remove_skill`.
        match plan(
            "remove_off",
            &none(),
            &none(),
            &Some("a-skill".into()),
            &none(),
            false,
        ) {
            Ok(Plan::Post(route, body, _)) => {
                assert_eq!(route, "/api/skills/state");
                assert_eq!(body["name"], serde_json::json!("a-skill"));
                assert_eq!(body["remove"], serde_json::json!(true));
                assert!(
                    body.get("on").is_none(),
                    "remove and on are opposite questions; never both"
                );
            }
            other => panic!("{other:?}"),
        }
        assert!(plan(
            "remove_off",
            &none(),
            &none(),
            &Some("  ".into()),
            &none(),
            false
        )
        .unwrap_err()
        .contains("Name a skill"));
    }

    #[test]
    fn a_scan_never_asks_for_a_card_and_an_install_names_its_source() {
        match plan(
            "scan",
            &Some("C:\\s\\a".into()),
            &none(),
            &none(),
            &none(),
            false,
        ) {
            Ok(Plan::Post(route, body, _)) => {
                assert_eq!(route, "/api/skills/install");
                assert_eq!(body["dry_run"], serde_json::json!(true));
                assert_eq!(body["path"], serde_json::json!("C:\\s\\a"));
            }
            other => panic!("{other:?}"),
        }
        match plan(
            "install",
            &none(),
            &Some("mlops/axolotl".into()),
            &none(),
            &none(),
            true,
        ) {
            Ok(Plan::Post(_route, body, _)) => {
                assert_eq!(body["hermes"], serde_json::json!("mlops/axolotl"));
                assert_eq!(body["accept_warnings"], serde_json::json!(true));
                assert_eq!(body["dry_run"], serde_json::json!(false));
                assert!(
                    body.get("path").is_none(),
                    "a Hermes install never sends a path"
                );
            }
            other => panic!("{other:?}"),
        }
        assert!(plan("install", &none(), &none(), &none(), &none(), false)
            .unwrap_err()
            .contains("folder"));
    }

    #[test]
    fn on_and_off_are_one_route_with_one_flag() {
        match plan(
            "enable",
            &none(),
            &none(),
            &Some("a-skill".into()),
            &none(),
            false,
        ) {
            Ok(Plan::Post(route, body, _)) => {
                assert_eq!(route, "/api/skills/state");
                assert_eq!(body["on"], serde_json::json!(true));
            }
            other => panic!("{other:?}"),
        }
        match plan(
            "disable",
            &none(),
            &none(),
            &Some("a-skill".into()),
            &none(),
            false,
        ) {
            Ok(Plan::Post(route, body, _)) => {
                assert_eq!(route, "/api/skills/state");
                assert_eq!(body["on"], serde_json::json!(false));
            }
            other => panic!("{other:?}"),
        }
        assert!(plan(
            "disable",
            &none(),
            &none(),
            &Some("  ".into()),
            &none(),
            false
        )
        .is_err());
    }

    #[test]
    fn an_edit_carries_the_text_and_refuses_an_empty_one() {
        match plan(
            "edit",
            &none(),
            &none(),
            &Some("a".into()),
            &Some("new text".into()),
            false,
        ) {
            Ok(Plan::Post(route, body, _)) => {
                assert_eq!(route, "/api/skills/edit");
                assert_eq!(body["text"], serde_json::json!("new text"));
            }
            other => panic!("{other:?}"),
        }
        assert!(plan(
            "edit",
            &none(),
            &none(),
            &Some("a".into()),
            &Some("   ".into()),
            false
        )
        .is_err());
    }

    #[test]
    fn the_pc_s_words_come_back_and_a_missing_route_says_so() {
        let missing = menu_answer(404, "").unwrap();
        assert_eq!(missing["why"], SKILLS_MENU_MISSING);
        let said = change_answer(
            409,
            r#"{"ok": false, "reason": "read it before you say yes"}"#,
        )
        .unwrap_err();
        assert!(said.to_lowercase().contains("read it"), "{said}");
        let refused = change_answer(
            200,
            r#"{"ok": false, "verdict": "refuse", "quarantined": true, "asked": false}"#,
        )
        .unwrap();
        assert_eq!(refused["asked"], serde_json::json!(false));
        assert!(change_answer(404, "")
            .unwrap_err()
            .contains("apply-patches"));
        assert!(change_answer(200, "not json").is_err());
        let menu = menu_answer(200, r#"{"ok": true, "skills": [], "off": []}"#).unwrap();
        assert_eq!(menu["skills"], serde_json::json!([]));
        assert!(menu_answer(200, r#"{"ok": true}"#).is_err());
    }
}
