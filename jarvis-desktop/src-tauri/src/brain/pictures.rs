//! Ask for a picture, and keep it (the owner's decision of 2026-09-27:
//! *"12 GB card: longer conversations with picture understanding first, and
//! making pictures too (swapped in when asked, since both cannot sit on the
//! card at once)"*; JARVIS-API.md section 124; backend `jarvis_pictures.py`).
//!
//! Four commands, one per route, in Settings -> Pictures:
//!
//! * [`brain_pictures`] - `GET /api/pictures`. A read: the folder, how many
//!   pictures are in it, how big it is, the switch, the two drawing programs
//!   this PC supports, and every picture with its own prompt, seed and when it
//!   was made.
//! * [`brain_pictures_file`] - `GET /api/pictures/file?id=<id>`. A read: ONE
//!   picture as base64 PNG, which the page draws as a `data:` image (the
//!   packaged CSP already allows `img-src data:` - the form picture at
//!   JARVIS-API section 98 draws the same way).
//! * [`brain_pictures_make`] - `POST /api/pictures {"prompt": "..."}`. Draws
//!   one and keeps it. **NO APPROVAL CARD**, and this file is where that is
//!   decided: a picture is a new file in a folder on this PC, drawn by a
//!   program on this PC, from words the owner typed - the same shape as a
//!   timer or a note. It opens no way out of the PC and loosens no rule.
//!   Held on a stale link anyway (rule 4), because it does change something.
//! * [`brain_pictures_settings`] - `POST /api/pictures/settings`. The switch,
//!   the drawing program and the folder. ONE named change at a time, and the
//!   backend refuses all of it unless it came from this PC.
//!   [`choose_pictures_folder`] opens the same Windows "Select folder" dialog
//!   "Folders Jarvis may look in" uses and hands the path to that route.
//!
//! **A PROMPT IS THE OWNER'S OWN WORDS.** Nothing here reads a file, an email,
//! a page or a saved fact, and the picture is never handed to a model. Every
//! sentence comes from the PC; this file works none of them out.
//!
//! **HIDDEN WITH THE PRIVATE THINGS.** The prompts are the owner's own words,
//! so while "Hide memory lists and chat history" is on (or App lock is locked)
//! [`hide_private`] takes the whole gallery out - prompts, seeds, paths, the
//! folder and the picture bytes - and leaves one line saying so. The page
//! cannot read round it, and the bytes are never even fetched: the page is
//! given `hidden: true` and draws the line.
//!
//! A picture this app can open is never a picture it has to trust: `id` must
//! be a bare file stem before it is asked for, so a page cannot make the PC
//! read another path.
//!
//! Nothing is cached, written to disk or logged here. The token only ever
//! travels in the headers `commands::jarvis_headers` builds.
//!
//! The answer-reading functions are plain functions of (status, body), so
//! their tests run without a Tauri app or a network.

use tauri::AppHandle;

use super::{require_link_live, READ_TIMEOUT, WRITE_TIMEOUT};
use crate::commands;

/// A PC whose backend has no pictures feature yet. Plain words, the same shape
/// every other Brain surface uses for an older PC.
pub(crate) const PICTURES_MISSING: &str =
    "Your PC's Jarvis does not have pictures yet - run apply-patches.ps1 on the PC.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. \
     Update the backend by running apply-patches.ps1.";

/// The words the PC sends with a hidden answer; used only if it sent none.
const HIDDEN_WORDS: &str = "Hidden while memory lists and chat history are hidden.";

/// The longest prompt this app will send, matching the PC's own cap. Checked
/// here too so an over-long prompt is refused before anything is sent.
pub(crate) const MAX_PROMPT: usize = 2000;

/// The shortest and longest picture name this app will ask the PC for. A PC
/// name is `YYYY-MM-DD-HHMMSS-<slug>` - 20 characters at the very least - and
/// the bound above is here so a page cannot ask for anything long.
const MIN_ID: usize = 17;
const MAX_ID: usize = 96;

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

/// The reading of either read. `need` is the key a success must carry
/// (`pictures` for the gallery). A `404`/`501` is a PC without the feature:
/// `available: false`, and the page draws nothing at all for it.
pub(crate) fn pictures_answer(
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

/// The same reading for the picture bytes: `png` must be a base64 string.
pub(crate) fn file_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("ok").and_then(|o| o.as_bool()) != Some(false))
            .filter(|v| v.get("png").is_some_and(|x| x.is_string()))
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

/// A picture id as the PC makes it: `YYYY-MM-DD-HHMMSS-<slug>`, so letters,
/// digits, dashes, dots and underscores only - never a separator and never a
/// `..`. A page cannot make the PC read another path.
pub(crate) fn valid_id(id: &str) -> bool {
    let bytes = id.as_bytes();
    if bytes.len() < MIN_ID || bytes.len() > MAX_ID {
        return false;
    }
    if !id.starts_with(|c: char| c.is_ascii_digit()) {
        return false;
    }
    !id.contains("..")
        && id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.')
}

/// The prompt as the PC's own cap allows it, or the plain reason it cannot be
/// sent. Trimmed, because a prompt of spaces is no prompt at all.
pub(crate) fn prompt_body(prompt: &str) -> Result<serde_json::Value, String> {
    let text = prompt.trim();
    if text.is_empty() {
        return Err("Say what the picture should show, and Jarvis will draw it.".to_string());
    }
    if text.chars().count() > MAX_PROMPT {
        return Err(format!(
            "That is a very long request for a picture. Keep it under {MAX_PROMPT} characters."
        ));
    }
    Ok(serde_json::json!({ "prompt": text }))
}

/// The body of `POST /api/pictures/settings`, rebuilt from the page's request
/// so only what the contract lets an app send goes out: one named change.
pub(crate) fn settings_body(
    action: &str,
    on: Option<bool>,
    runtime: Option<&str>,
    address: Option<&str>,
    folder: Option<&str>,
) -> Result<serde_json::Value, String> {
    match action {
        "enabled" => match on {
            Some(value) => Ok(serde_json::json!({ "action": "enabled", "on": value })),
            None => Err("Say whether making pictures is on or off.".to_string()),
        },
        "runtime" => {
            let mut body = serde_json::json!({ "action": "runtime" });
            // `null` is a real choice here: "nothing chosen yet".
            body["runtime"] = match runtime {
                Some(name) if !name.is_empty() => serde_json::json!(name),
                _ => serde_json::Value::Null,
            };
            if let Some(text) = address.map(str::trim).filter(|a| !a.is_empty()) {
                body["address"] = serde_json::json!(text);
            }
            Ok(body)
        }
        "folder" => {
            let text = folder.unwrap_or("").trim();
            if text.is_empty() {
                return Err("Give the folder to keep the pictures in.".to_string());
            }
            Ok(serde_json::json!({ "action": "folder", "folder": text }))
        }
        _ => Err("Say what to change: enabled, runtime or folder.".to_string()),
    }
}

fn words_hidden(app: &AppHandle) -> bool {
    crate::lock::private_hidden(app) || crate::lock::app_locked(app)
}

/// The gallery with the owner's own words taken out: nothing but the PC's own
/// "hidden" sentence stays - and not one prompt, seed, path, picture id, count,
/// size, folder or program name. There is deliberately no `count`, `bytes`,
/// `folder` or `pictures` key at all, so a page cannot draw a number or a path
/// out of a hidden answer even by accident.
pub(crate) fn hidden_answer(answer: &serde_json::Value) -> serde_json::Value {
    let words = answer
        .get("words")
        .and_then(|w| w.as_str())
        .filter(|w| !w.is_empty())
        .unwrap_or(HIDDEN_WORDS);
    serde_json::json!({
        "ok": true,
        "available": true,
        "hidden": true,
        "keep_on_screen": true,
        "title": "Pictures",
        "hidden_words": words,
    })
}

/// While the private lists are hidden, the gallery is replaced whole. An
/// answer from an older PC (`available: false`) passes through untouched, so
/// the page still knows the feature is simply not there.
pub(crate) fn hide_private(answer: serde_json::Value) -> serde_json::Value {
    if answer.get("available").and_then(|a| a.as_bool()) == Some(false) {
        return answer;
    }
    if answer.get("hidden").and_then(|h| h.as_bool()) == Some(true) {
        return answer;
    }
    hidden_answer(&answer)
}

fn shown(app: &AppHandle, answer: serde_json::Value) -> serde_json::Value {
    if words_hidden(app) {
        hide_private(answer)
    } else {
        answer
    }
}

/// The folder, its size, the switch and every picture with its own prompt.
/// A read.
#[tauri::command]
pub async fn brain_pictures(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/pictures"))
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    let answer = pictures_answer(status, &body, "pictures")?;
    Ok(shown(&app, answer))
}

/// ONE picture as base64 PNG. A read, and never fetched at all while the
/// private lists are hidden - there is nothing to hide a picture from if the
/// bytes never left the PC.
#[tauri::command]
pub async fn brain_pictures_file(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    if !valid_id(&id) {
        return Err("There is no picture with that name.".to_string());
    }
    if words_hidden(&app) {
        return Ok(hidden_answer(&serde_json::json!({})));
    }
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}/api/pictures/file"))
        .query(&[("id", &id)])
        .headers(commands::jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    file_answer(status, &body)
}

/// Draw one picture and keep it. NO CARD (see this file's own doc), but held
/// on a stale link: it writes a file, so it is a change and rule 4 applies.
#[tauri::command]
pub async fn brain_pictures_make(
    app: AppHandle,
    prompt: String,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let body = prompt_body(&prompt)?;
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}/api/pictures"))
        .headers(commands::jarvis_headers(&app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    if status == 404 || status == 501 {
        return Err(PICTURES_MISSING.to_string());
    }
    // A drawing takes far longer than a read's budget: the PC waits for the
    // program itself, and the answer is what it finally says.
    pictures_answer(status, &text, "name")
}

/// The switch, the drawing program and the folder. ONE named change at a
/// time; the PC refuses all of it unless the request came from this PC.
#[tauri::command]
#[allow(clippy::too_many_arguments)]
pub async fn brain_pictures_settings(
    app: AppHandle,
    action: String,
    on: Option<bool>,
    runtime: Option<String>,
    address: Option<String>,
    folder: Option<String>,
) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let body = settings_body(
        &action,
        on,
        runtime.as_deref(),
        address.as_deref(),
        folder.as_deref(),
    )?;
    let base = commands::jarvis_base(&app);
    let response = commands::jarvis_client(Some(WRITE_TIMEOUT))?
        .post(format!("{base}/api/pictures/settings"))
        .headers(commands::jarvis_headers(&app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| commands::backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let text = response.text().await.unwrap_or_default();
    if status == 404 || status == 501 {
        return Err(PICTURES_MISSING.to_string());
    }
    pictures_answer(status, &text, "pictures")
}

/// Choose the folder pictures are kept in: the SAME Windows "Select folder"
/// dialog "Folders Jarvis may look in" and "Choose a folder for backups" use,
/// then one settings change. No card, and the PC accepts the path only from
/// this PC.
#[tauri::command]
pub async fn choose_pictures_folder(app: AppHandle) -> Result<serde_json::Value, String> {
    require_link_live(&app)?;
    let Some(path) = crate::folders::pick(crate::folders::picker::What::Folder).await? else {
        return Ok(serde_json::json!({ "cancelled": true }));
    };
    brain_pictures_settings(
        app,
        "folder".to_string(),
        None,
        None,
        None,
        Some(path),
    )
    .await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn an_id_is_a_bare_file_stem_and_never_a_path() {
        for good in [
            "2026-10-11-140509-a-red-panda",
            "2026-10-11-140509-a-red-panda-2",
            "2026-01-02-030405-x",
        ] {
            assert!(valid_id(good), "{good}");
        }
        for bad in [
            "",
            "..",
            "../pictures.json",
            "/etc/passwd",
            "C:\\Windows\\win.ini",
            "2026-10-11-140509-a/b",
            "2026-10-11-140509-a\\b",
            "2026-10-11-140509-..",
            "2026-10-11-140509-a b",
            "not-a-date-at-all",
            &"9".repeat(MAX_ID + 1),
        ] {
            assert!(!valid_id(bad), "{bad:?}");
        }
        assert!(valid_id(&format!("2026-10-11-140509-{}", "a".repeat(MAX_ID - 20))));
    }

    #[test]
    fn a_prompt_is_trimmed_and_bounded() {
        assert_eq!(
            prompt_body("  a red panda  ").unwrap(),
            serde_json::json!({ "prompt": "a red panda" })
        );
        assert_eq!(
            prompt_body("   ").unwrap_err(),
            "Say what the picture should show, and Jarvis will draw it."
        );
        assert!(prompt_body(&"x".repeat(MAX_PROMPT)).is_ok());
        let too_long = prompt_body(&"x".repeat(MAX_PROMPT + 1)).unwrap_err();
        assert!(too_long.contains("very long request"), "{too_long}");
        // Counted in characters, not bytes: a prompt of non-Latin words that
        // fits under the cap must not be refused for being long in bytes.
        assert!(prompt_body(&"日".repeat(MAX_PROMPT)).is_ok());
    }

    #[test]
    fn the_settings_body_carries_one_named_change() {
        assert_eq!(
            settings_body("enabled", Some(true), None, None, None).unwrap(),
            serde_json::json!({ "action": "enabled", "on": true })
        );
        assert!(settings_body("enabled", None, None, None, None).is_err());
        assert_eq!(
            settings_body("runtime", None, Some("comfyui"), None, None).unwrap(),
            serde_json::json!({ "action": "runtime", "runtime": "comfyui" })
        );
        assert_eq!(
            settings_body("runtime", None, None, None, None).unwrap(),
            serde_json::json!({ "action": "runtime", "runtime": null })
        );
        assert_eq!(
            settings_body(
                "runtime",
                None,
                Some("sd_cpp"),
                Some(" http://127.0.0.1:9999 "),
                None
            )
            .unwrap(),
            serde_json::json!({
                "action": "runtime",
                "runtime": "sd_cpp",
                "address": "http://127.0.0.1:9999"
            })
        );
        assert_eq!(
            settings_body("folder", None, None, None, Some(" D:\\Jarvis pics ")).unwrap(),
            serde_json::json!({ "action": "folder", "folder": "D:\\Jarvis pics" })
        );
        assert!(settings_body("folder", None, None, None, Some("  ")).is_err());
        assert!(settings_body("shoes", None, None, None, None).is_err());
    }

    #[test]
    fn every_real_answer_reads_and_an_old_pc_draws_nothing() {
        let good = serde_json::json!({
            "ok": true,
            "available": true,
            "enabled": true,
            "pictures": [],
        })
        .to_string();
        let got = pictures_answer(200, &good, "pictures").unwrap();
        assert_eq!(got["enabled"], true);
        assert!(pictures_answer(200, "not json", "pictures").is_err());
        assert!(pictures_answer(200, r#"{"ok": true}"#, "pictures").is_err());
        assert!(pictures_answer(200, r#"{"ok": true, "pictures": null}"#, "pictures").is_err());
        let old = pictures_answer(404, "Not Found", "pictures").unwrap();
        assert_eq!(old["available"], false);
        assert_eq!(pictures_answer(501, "", "pictures").unwrap()["available"], false);
        assert!(pictures_answer(500, "boom", "pictures").is_err());
        // The bytes.
        let bytes = serde_json::json!({ "ok": true, "png": "AAAA" }).to_string();
        assert_eq!(file_answer(200, &bytes).unwrap()["png"], "AAAA");
        assert!(file_answer(200, r#"{"ok": true, "png": ""}"#, ).is_ok());
        assert!(file_answer(200, r#"{"ok": true, "png": 7}"#).is_err());
    }

    #[test]
    fn a_refusal_is_the_pcs_sentence_as_sent() {
        let body = serde_json::json!({
            "ok": false,
            "error": "Jarvis has no picture-making program set up yet, so it cannot draw one."
        })
        .to_string();
        assert_eq!(
            pictures_answer(503, &body, "pictures").unwrap_err(),
            "Jarvis has no picture-making program set up yet, so it cannot draw one."
        );
        // The switch being off is a sentence too, never a red error.
        let off = serde_json::json!({
            "ok": false,
            "off": true,
            "error": "Making pictures is switched off."
        })
        .to_string();
        assert_eq!(pictures_answer(503, &off, "pictures").unwrap_err(), "Making pictures is switched off.");
    }

    #[test]
    fn while_the_lists_are_hidden_not_one_prompt_survives() {
        let answer = serde_json::json!({
            "ok": true,
            "available": true,
            "enabled": true,
            "folder": "C:\\Users\\owner\\Pictures\\Jarvis",
            "count": 2,
            "bytes": 900000,
            "size_words": "900 KB",
            "words": "2 pictures, 900 KB on disk.",
            "pictures": [
                { "name": "a.png", "prompt": "a red panda in a library", "seed": 7 },
                { "name": "b.png", "prompt": "my sister's wedding", "seed": 8 }
            ]
        });
        let out = hide_private(answer);
        assert_eq!(out["hidden"], true);
        assert_eq!(out["keep_on_screen"], true);
        assert_eq!(out["hidden_words"], "2 pictures, 900 KB on disk.");
        for gone in [
            "pictures",
            "folder",
            "count",
            "bytes",
            "size_words",
            "enabled",
            "runtime",
            "runtimes",
            "words",
            "keep",
        ] {
            assert!(out.get(gone).is_none(), "{gone} survived");
        }
        let text = out.to_string().to_lowercase();
        for secret in ["red panda", "library", "sister", "wedding", "pictures\\jarvis"] {
            assert!(!text.contains(secret), "{secret} survived");
        }
        // An older PC's answer, and one already hidden, pass through.
        let old = serde_json::json!({ "available": false });
        assert_eq!(hide_private(old.clone()), old);
        let already = hide_private(out.clone());
        assert_eq!(already, out);
        // A hidden answer with no words of its own still says something.
        let bare = hidden_answer(&serde_json::json!({}));
        assert_eq!(bare["hidden_words"], HIDDEN_WORDS);
    }

    #[test]
    fn the_routes_are_literal_and_every_write_is_gated() {
        let src = include_str!("pictures.rs");
        // Everything below the `#[cfg(test)]` line is this test itself; the
        // scan is of the MODULE, not of the words used to check it. Without
        // this the assertions find their own literals and the whole test
        // proves nothing.
        let code = src.split("#[cfg(test)]").next().unwrap_or(src);
        for route in [
            "/api/pictures\"",
            "/api/pictures/file",
            "/api/pictures/settings",
        ] {
            assert!(code.contains(route), "{route}");
        }
        // Three writes wait for a live link - the drawing, the settings change
        // and the folder picker - and the two reads do not (they change
        // nothing). The literals are built so this test cannot find itself.
        let gate = ["require_link_live", "(&app)?;"].concat();
        assert_eq!(code.matches(&gate).count(), 3, "{gate}");
        assert!(code.contains("crate::lock::private_hidden(app)"));
        assert!(code.contains("crate::lock::app_locked(app)"));
        // The prompt is the owner's own words: nothing here reads a file, a
        // fact or a page.
        for forbidden in [
            ["std", "::fs"].concat(),
            ["jarvis", "_memory"].concat(),
            ["brain", "_history"].concat(),
            ["reqwest", "::get("].concat(),
        ] {
            assert!(!code.contains(&forbidden), "{forbidden} in pictures.rs");
        }
        // No card is raised from this app: the gate is only ever the PC's.
        for forbidden in [
            ["/api/", "approve"].concat(),
            ["/api/", "deny"].concat(),
            ["owner", "_check"].concat(),
        ] {
            assert!(!code.contains(&forbidden), "{forbidden} in pictures.rs");
        }
    }
}
