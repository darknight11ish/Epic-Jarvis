//! "Spending summaries" (the owner's decision of 2026-09-30, queue item 2;
//! `docs/FINANCE-DESIGN.md` part A and its frozen slice contract;
//! JARVIS-API.md section 100; backend `jarvis_spending.py`, spending.patch).
//!
//! Two kinds of command, each in its own permission set
//! (`permissions/surfaces.toml`):
//!
//! **The chat table** (`spending-table`, the Jarvis bar only):
//!
//! * [`chat_table`] - `GET /api/chat/table?id=<32 hex>`. The chat stream said
//!   `: jarvis-table <id>` right before the answer's sentence; the bar asks
//!   for the table here. A read, never held on a stale link. While "Hide
//!   memory lists and chat history" is on, or App lock has locked Jarvis, the
//!   PC is NOT asked at all and the answer is `{"hidden": true}` (the id
//!   stays good for two hours on the PC; the bar asks again when it is
//!   unlocked). The table is handed to the page and kept nowhere here: no
//!   file, no log, no cache.
//!
//! **The Settings box** (`spending-settings`, Settings only; every write is
//! PC-only on the backend - a request from any other device gets 403
//! `pc_only`, and the words the PC sends are shown as they are):
//!
//! * [`get_spending`] - `GET /api/spending`: layouts, categories, waiting
//!   files. A read.
//! * [`spending_profile_read`] - `GET /api/spending/profile?file=`: the
//!   proposal for a waiting file, or the saved layout it already has.
//! * [`spending_profile_save`] - `POST /api/spending/profile` with
//!   `confirm: true` (added here, always).
//! * [`spending_profile_delete`] - `POST /api/spending/profile/delete`.
//! * [`spending_categories_save`] / [`spending_categories_reset`] -
//!   `POST /api/spending/categories`.
//! * [`spending_suggest`] - `POST /api/spending/suggest`: proposals only;
//!   nothing is saved until the owner taps "Add these rules".
//!
//! No approval card is raised by any of them (the owner's own tap on their
//! own file). The writes are held on a stale link (rule 4). The token is
//! never logged or returned; a bank file's rows are never handled here (the
//! PC hides them; only its preview reaches the page).
//!
//! The answer-reading functions are plain functions of (status, body) so
//! their tests run against the real answers in `tests/fixtures/
//! spending-cases.json` (made by `tools/gen_spending_cases.py`).

use std::time::Duration;

use tauri::{AppHandle, Manager};

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
};

const TABLE_PATH: &str = "/api/chat/table";
pub(crate) const SPENDING_PATH: &str = "/api/spending";
const PROFILE_PATH: &str = "/api/spending/profile";
const PROFILE_DELETE_PATH: &str = "/api/spending/profile/delete";
const CATEGORIES_PATH: &str = "/api/spending/categories";
const SUGGEST_PATH: &str = "/api/spending/suggest";

/// The words the contract fixes (`words.TABLE_HIDDEN`, `words.TABLE_GONE`).
pub(crate) const TABLE_HIDDEN: &str = "Spending table hidden";
pub(crate) const TABLE_GONE: &str = "This table is no longer kept. Ask again to see it.";

/// A PC without `jarvis_spending.py` / `spending.patch`. Desktop wording (the
/// contract has none for this case); same shape as the other "run
/// apply-patches.ps1" lines.
pub(crate) const SPENDING_MISSING: &str =
    "Your PC's Jarvis cannot add up spending yet - run apply-patches.ps1 on the PC.";

const STALE: &str =
    "The connection to Jarvis is catching up, so nothing can be sent until it does.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);
/// Reading a big bank file (hiding account numbers first) takes a while.
const FILE_TIMEOUT: Duration = Duration::from_secs(120);

/// The longest file path the page may put in a request.
const PATH_MAX: usize = 1024;

/// A table id as the PC makes it: 32 lowercase hex characters, so an id can
/// never carry a `&`, `/`, `?` or `..` into the route.
pub(crate) fn valid_table_id(id: &str) -> bool {
    id.len() == 32 && id.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
}

fn valid_file(file: &str) -> bool {
    !file.trim().is_empty() && file.len() <= PATH_MAX && !file.contains('\0')
}

fn parsed(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

/// A 404 that jarvis_spending itself sent carries `"ok": false`; a PC without
/// the routes at all does not.
fn own_404(body: &str) -> bool {
    parsed(body).and_then(|v| v.get("ok").and_then(|o| o.as_bool())) == Some(false)
}

/// The PC's own words for a refusal: its `message` (403 `pc_only`, 400 with
/// the reason a file or a choice was refused) as given; else the shared
/// reading of `{"error": ...}`.
pub(crate) fn refusal(status: u16, body: &str) -> String {
    if let Some(message) = parsed(body)
        .and_then(|v| {
            v.get("message")
                .and_then(|m| m.as_str().map(str::to_string))
        })
        .filter(|m| !m.trim().is_empty())
    {
        return message;
    }
    backend_refusal(status, body)
}

/// [`chat_table`]'s reading of the answer: `{"table": {...}}` on 200,
/// `{"gone": true, "message": <the PC's words>}` on the PC's own 404 (or a
/// PC that has no such route: nothing was ever announced there).
pub(crate) fn table_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        let table = parsed(body)
            .and_then(|v| v.get("table").cloned())
            .filter(|t| t.is_object() && t.get("kind").and_then(|k| k.as_str()) == Some("spending"))
            .ok_or_else(|| UNREADABLE.to_string())?;
        return Ok(serde_json::json!({ "table": table }));
    }
    if status == 404 {
        let message = parsed(body)
            .filter(|_| own_404(body))
            .and_then(|v| {
                v.get("message")
                    .and_then(|m| m.as_str().map(str::to_string))
            })
            .filter(|m| !m.trim().is_empty())
            .unwrap_or_else(|| TABLE_GONE.to_string());
        return Ok(serde_json::json!({ "gone": true, "message": message }));
    }
    Err(refusal(status, body))
}

/// [`get_spending`]'s reading: the PC's own body on a 2xx;
/// `{"available": false, "why": SPENDING_MISSING}` from a PC without the
/// routes; the PC's own sentence otherwise.
pub(crate) fn view_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body)
            .filter(|v| v.get("categories").is_some_and(|c| c.is_array()))
            .ok_or_else(|| UNREADABLE.to_string());
    }
    if (status == 404 && !own_404(body)) || status == 501 {
        return Ok(serde_json::json!({ "available": false, "why": SPENDING_MISSING }));
    }
    Err(refusal(status, body))
}

/// A read or a change's answer: the PC's own body on a 2xx, the PC's own
/// words on 400 / 403 / 404 (a file it refused, `pc_only`), the missing line
/// from a PC without the routes.
pub(crate) fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        return parsed(body).ok_or_else(|| UNREADABLE.to_string());
    }
    if (status == 404 && !own_404(body)) || status == 501 {
        return Err(SPENDING_MISSING.to_string());
    }
    Err(refusal(status, body))
}

fn stale(app: &AppHandle) -> bool {
    app.state::<crate::stream::StreamState>().link().stale
}

/// True while a spending table must not be fetched or drawn.
fn table_hidden(app: &AppHandle) -> bool {
    crate::lock::private_hidden(app) || crate::lock::app_locked(app)
}

/// The table a chat answer announced. See the module note.
#[tauri::command]
pub async fn chat_table(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    if !valid_table_id(&id) {
        return Err("that table id is not one Jarvis made".to_string());
    }
    if table_hidden(&app) {
        return Ok(serde_json::json!({ "hidden": true, "words": TABLE_HIDDEN }));
    }
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{TABLE_PATH}?id={id}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    // Asked again after the wait: it could have been hidden meanwhile.
    if table_hidden(&app) {
        return Ok(serde_json::json!({ "hidden": true, "words": TABLE_HIDDEN }));
    }
    table_answer(status, &body)
}

/// Settings -> Spending: `GET /api/spending`. A read.
#[tauri::command]
pub async fn get_spending(app: AppHandle) -> Result<serde_json::Value, String> {
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{SPENDING_PATH}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    view_answer(status, &body)
}

/// The proposal for a waiting file (or its saved layout): `GET
/// /api/spending/profile?file=`. PC only on the backend.
#[tauri::command]
pub async fn spending_profile_read(
    app: AppHandle,
    file: String,
) -> Result<serde_json::Value, String> {
    if !valid_file(&file) {
        return Err("choose a bank file first".to_string());
    }
    let base = jarvis_base(&app);
    let response = jarvis_client(Some(FILE_TIMEOUT))?
        .get(format!("{base}{PROFILE_PATH}"))
        .query(&[("file", file.as_str())])
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    change_answer(status, &body)
}

async fn post(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
    timeout: Duration,
) -> Result<serde_json::Value, String> {
    if stale(app) {
        return Err(STALE.to_string());
    }
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

/// The keys a confirmed layout may carry; `confirm` is added here, always.
const PROFILE_KEYS: [&str; 8] = [
    "file",
    "header_row",
    "columns",
    "sign",
    "date_order",
    "decimal",
    "currency",
    "label",
];

/// The body of `POST /api/spending/profile`: only the known keys of what the
/// page sent, plus `confirm: true`. `Err` when it names no file.
pub(crate) fn profile_body(choices: &serde_json::Value) -> Result<serde_json::Value, String> {
    let Some(obj) = choices.as_object() else {
        return Err("the column choices were not readable".to_string());
    };
    let file = obj.get("file").and_then(|f| f.as_str()).unwrap_or("");
    if !valid_file(file) {
        return Err("choose a bank file first".to_string());
    }
    let mut out = serde_json::Map::new();
    for key in PROFILE_KEYS {
        if let Some(v) = obj.get(key) {
            out.insert(key.to_string(), v.clone());
        }
    }
    out.insert("confirm".to_string(), serde_json::Value::Bool(true));
    Ok(serde_json::Value::Object(out))
}

/// Save the columns the owner confirmed. No card. Held on a stale link.
#[tauri::command]
pub async fn spending_profile_save(
    app: AppHandle,
    choices: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let body = profile_body(&choices)?;
    post(&app, PROFILE_PATH, body, FILE_TIMEOUT).await
}

/// Forget a saved layout. Held on a stale link.
#[tauri::command]
pub async fn spending_profile_delete(
    app: AppHandle,
    id: String,
) -> Result<serde_json::Value, String> {
    if id.trim().is_empty() || id.len() > 64 {
        return Err("choose a saved layout first".to_string());
    }
    post(
        &app,
        PROFILE_DELETE_PATH,
        serde_json::json!({ "id": id }),
        READ_TIMEOUT,
    )
    .await
}

/// Only what the PC's category list holds: a name and its words.
pub(crate) fn categories_body(list: &serde_json::Value) -> Result<serde_json::Value, String> {
    let Some(items) = list.as_array() else {
        return Err("the categories were not readable".to_string());
    };
    let mut out = Vec::with_capacity(items.len());
    for item in items {
        let name = item.get("category").and_then(|c| c.as_str());
        let words = item.get("words").and_then(|w| w.as_array());
        let (Some(name), Some(words)) = (name, words) else {
            return Err("the categories were not readable".to_string());
        };
        let words: Vec<serde_json::Value> = words
            .iter()
            .filter_map(|w| w.as_str().map(|s| serde_json::json!(s)))
            .collect();
        out.push(serde_json::json!({ "category": name, "words": words }));
    }
    Ok(serde_json::json!({ "categories": out }))
}

/// Save the whole category list. No card. Held on a stale link.
#[tauri::command]
pub async fn spending_categories_save(
    app: AppHandle,
    categories: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let body = categories_body(&categories)?;
    post(&app, CATEGORIES_PATH, body, READ_TIMEOUT).await
}

/// Put the starter categories back. The page asks "are you sure?" first.
#[tauri::command]
pub async fn spending_categories_reset(app: AppHandle) -> Result<serde_json::Value, String> {
    post(
        &app,
        CATEGORIES_PATH,
        serde_json::json!({ "reset": true }),
        READ_TIMEOUT,
    )
    .await
}

/// Proposals for shop names no rule catches. Saves nothing.
#[tauri::command]
pub async fn spending_suggest(app: AppHandle, file: String) -> Result<serde_json::Value, String> {
    if !valid_file(&file) {
        return Err("choose a bank file first".to_string());
    }
    post(
        &app,
        SUGGEST_PATH,
        serde_json::json!({ "file": file }),
        FILE_TIMEOUT,
    )
    .await
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The real answers, made by `tools/gen_spending_cases.py`.
    const CASES: &str = include_str!("../../tests/fixtures/spending-cases.json");

    fn cases() -> serde_json::Value {
        serde_json::from_str(CASES).expect("spending-cases.json is JSON")
    }

    #[test]
    fn the_words_here_are_the_contracts() {
        let doc = cases();
        assert_eq!(doc["words"]["TABLE_HIDDEN"], TABLE_HIDDEN);
        assert_eq!(doc["words"]["TABLE_GONE"], TABLE_GONE);
        assert_eq!(
            doc["tables"]["by_category"]["words"]["hidden"],
            TABLE_HIDDEN
        );
    }

    #[test]
    fn a_table_id_is_32_lowercase_hex_and_nothing_else() {
        assert!(valid_table_id("3f9c0a5e1d7b4c2a8e6f01b2c3d4e5f6"));
        assert!(!valid_table_id(""));
        assert!(!valid_table_id("3F9C0A5E1D7B4C2A8E6F01B2C3D4E5F6"));
        assert!(!valid_table_id("3f9c0a5e1d7b4c2a8e6f01b2c3d4e5f"));
        assert!(!valid_table_id("3f9c0a5e1d7b4c2a8e6f01b2c3d4e5f6a"));
        assert!(!valid_table_id("3f9c0a5e1d7b4c2a8e6f01b2c3d4&5f6"));
        assert!(!valid_table_id("../../api/approve/aaaaaaaaaaaaaaaaaa"));
    }

    #[test]
    fn every_real_table_is_passed_on_unchanged() {
        let doc = cases();
        let tables = doc["tables"].as_object().expect("tables");
        assert!(tables.len() >= 6);
        for (name, table) in tables {
            let body = serde_json::json!({ "ok": true, "table": table }).to_string();
            let got = table_answer(200, &body).unwrap();
            assert_eq!(&got["table"], table, "{name}");
        }
    }

    #[test]
    fn a_table_that_is_gone_says_the_pcs_words() {
        let doc = cases();
        let body = serde_json::json!({
            "ok": false, "error": "gone", "message": doc["words"]["TABLE_GONE"]
        })
        .to_string();
        let got = table_answer(404, &body).unwrap();
        assert_eq!(got["gone"], true);
        assert_eq!(got["message"], doc["words"]["TABLE_GONE"]);
        // A PC with no such route at all: the same line, from here.
        let got = table_answer(404, r#"{"error": "not found"}"#).unwrap();
        assert_eq!(got["message"], TABLE_GONE);
        assert!(table_answer(500, "{}").is_err());
        assert!(table_answer(200, r#"{"ok": true, "table": {"kind": "other"}}"#).is_err());
        assert!(table_answer(200, "<html>").is_err());
    }

    #[test]
    fn every_real_view_reads_and_a_pc_without_it_says_so() {
        let doc = cases();
        for name in [
            "view_pc_nothing_saved",
            "view_phone_nothing_saved",
            "view_pc_file_waiting",
            "view_pc_one_layout",
        ] {
            let got = view_answer(200, &doc[name].to_string()).unwrap();
            assert_eq!(got, doc[name], "{name}");
        }
        let got = view_answer(404, r#"{"error": "not found"}"#).unwrap();
        assert_eq!(got["available"], false);
        assert_eq!(got["why"], SPENDING_MISSING);
        assert!(view_answer(200, "{nope").is_err());
    }

    #[test]
    fn the_pcs_own_message_wins_over_its_error_code() {
        let doc = cases();
        let pc_only = serde_json::json!({
            "ok": false, "error": "pc_only", "pc_only": true,
            "message": doc["errors"]["pc_only"]
        })
        .to_string();
        assert_eq!(
            change_answer(403, &pc_only).unwrap_err(),
            doc["errors"]["pc_only"].as_str().unwrap()
        );
        let big = serde_json::json!({
            "ok": false, "error": "too_big", "message": doc["errors"]["too_big"]
        })
        .to_string();
        assert_eq!(
            change_answer(400, &big).unwrap_err(),
            doc["errors"]["too_big"].as_str().unwrap()
        );
        // The PC's own "no such thing" is a refusal, not "missing".
        assert_ne!(
            change_answer(404, r#"{"ok": false, "error": "not_found"}"#).unwrap_err(),
            SPENDING_MISSING
        );
        assert_eq!(change_answer(404, "").unwrap_err(), SPENDING_MISSING);
    }

    #[test]
    fn a_real_proposal_reads_through_unchanged() {
        let doc = cases();
        for name in ["proposal_signed_amount", "proposal_date_order_unsettled"] {
            let got = change_answer(200, &doc[name].to_string()).unwrap();
            assert_eq!(got, doc[name], "{name}");
        }
    }

    #[test]
    fn a_confirmed_layout_carries_only_known_keys_and_confirm() {
        let sent = serde_json::json!({
            "file": "C:\\bank\\a.csv", "header_row": 0,
            "columns": {"date": 0, "description": 1, "amount": 2},
            "sign": "negative_out", "date_order": "ymd", "decimal": ".",
            "currency": "GBP", "label": "a.csv",
            "confirm": false, "path": "C:\\elsewhere", "token": "x"
        });
        let body = profile_body(&sent).unwrap();
        let obj = body.as_object().unwrap();
        assert_eq!(obj["confirm"], true);
        assert!(!obj.contains_key("path") && !obj.contains_key("token"));
        assert_eq!(obj["sign"], "negative_out");
        assert_eq!(obj.len(), 9);
        assert!(profile_body(&serde_json::json!({ "sign": "drcr" })).is_err());
        assert!(profile_body(&serde_json::json!("x")).is_err());
    }

    #[test]
    fn categories_are_sent_as_names_and_words_only() {
        let doc = cases();
        let list = doc["view_pc_nothing_saved"]["categories"].clone();
        let body = categories_body(&list).unwrap();
        assert_eq!(body["categories"], list);
        let dirty = serde_json::json!([{"category": "Food", "words": ["tesco", 5], "x": 1}]);
        assert_eq!(
            categories_body(&dirty).unwrap()["categories"][0],
            serde_json::json!({"category": "Food", "words": ["tesco"]})
        );
        assert!(categories_body(&serde_json::json!({})).is_err());
        assert!(categories_body(&serde_json::json!([{"category": "x"}])).is_err());
    }
}
