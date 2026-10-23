//! The desktop HUD's saved layout (H1 of the editable-HUD design, Gemini
//! rulings 23-28, 2026-10-21; docs/ARCHITECTURE.md section 8).
//!
//! WHAT THIS IS. `jarvis-desktop/src/hud-layout.js` owns the card registry, the
//! seven presets and the closed-world normalizer. This module is the one place
//! that document is PERSISTED: the appearance-class settings store the theme
//! already uses (`jarvis-desktop.json`), no backend call, no approval card -
//! a layout holds card coordinates and visibility, nothing private, and it
//! loosens no security rule.
//!
//! WHY THE VALIDATION IS HERE TOO. The webview normalizes before it saves, but
//! the settings file can be hand-edited on disk. `sanitise` is therefore a
//! second, independent closed-world pass: known regions/shells/densities/
//! themes, bounded numbers, unknown keys and `x`/`y` dropped, all four
//! protected cards visible. A document that fails is NEVER written over the
//! last good one, and `choose` serves the last good copy so a hand-edit cannot
//! lock the owner out of the HUD picker.
//!
//! NO BACKEND, NO TOKEN. This is the desktop's own store, the same class as
//! `theme`, and the HUD page still holds no pairing token (`hud.json` grants
//! the read for the bootstrap, and since H2 of the editable-HUD design
//! (2026-10-22, owner-approved) EXACTLY ONE write - `set_hud_layout`, so the
//! page's own Edit mode can save its layout; the Settings picker writes the
//! same document, and no other write command is granted to that window).
//!
//! H2 also adds `open_hud_edit`, called by the Settings window's "Edit HUD in
//! the window" button: it shows the owner's HUD window and tells it to enter
//! edit mode. One navigation command - it changes no setting and approves
//! nothing.

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_store::StoreExt;

/// The store key the current layout is saved under.
pub const STORE_KEY: &str = "hud_layout";
/// The last layout that passed validation, kept so a bad hand-edit is not fatal.
pub const LAST_GOOD_KEY: &str = "hud_layout_last_good";
/// The version of the document shape this build reads and writes.
pub const LAYOUT_VERSION: u64 = 1;
/// The named regions a card can live in (ruling 23).
pub const REGIONS: &[&str] = &[
    "header",
    "left_rail",
    "stage_top",
    "stage_main",
    "right_rail",
];
/// The shells a preset may choose between.
pub const SHELL_TEMPLATES: &[&str] = &[
    "three-column",
    "split-stage",
    "center-core",
    "two-column-left",
    "two-column-right",
    "single-stage-bento",
];
/// The densities the renderer understands.
pub const DENSITIES: &[&str] = &["comfortable", "compact", "spacious"];
/// The stage tabs a layout can open on (H3: the page's own five plus Talk).
pub const STAGE_TABS: &[&str] = &[
    "talk",
    "galaxy",
    "today",
    "reminders",
    "memory",
    "telemetry",
];
/// The most owner-saved layouts one document may carry (H3, bounded here and
/// in `hud-layout.js`). A library is appearance data, not a dumping ground.
pub const MAX_USER_PRESETS: usize = 20;
/// The longest owner-typed layout name.
pub const MAX_USER_NAME: usize = 60;
/// The largest saved document this build accepts (H3): a layout library is a
/// few dozen tiny records, never a payload.
pub const MAX_DOCUMENT_BYTES: usize = 64 * 1024;
/// The built-in HUD layouts a saved layout may name as its base (H3). Keep in
/// step with `PRESETS` in `jarvis-desktop/src/hud-layout.js`; the coherence
/// slice renamed "focus" to "quiet", and the old id stays accepted as a silent
/// migration alias, exactly as the JS normalizer does.
pub const BUILT_IN_PRESETS: &[&str] = &[
    "cockpit",
    "studio",
    "ambient",
    "quiet",
    "telemetry",
    "second_brain",
    "minimal",
];
/// Old preset ids still accepted on the save road (JS maps them on load).
pub const PRESET_ALIASES: &[&str] = &["focus"];

fn known_preset(id: &str) -> bool {
    BUILT_IN_PRESETS.contains(&id) || PRESET_ALIASES.contains(&id)
}
/// The four cards no layout may hide (ruling 25).
pub const PROTECTED_IDS: &[&str] = &[
    "approvals",
    "emergency_stop",
    "voice_controls",
    "bar_launcher",
];

const MAX_TEXT: usize = 60;
const MAX_CARDS: usize = 64;

fn text_of(value: Option<&serde_json::Value>, max: usize) -> Option<String> {
    let text = value?.as_str()?.trim().replace(char::is_whitespace, " ");
    if text.is_empty() {
        None
    } else {
        Some(text.chars().take(max).collect())
    }
}

fn int_in(value: Option<&serde_json::Value>, lo: i64, hi: i64) -> Option<i64> {
    let number = value?.as_i64()?;
    (lo..=hi).contains(&number).then_some(number)
}

fn bool_of(value: Option<&serde_json::Value>) -> Option<bool> {
    value?.as_bool()
}

fn allowed(value: Option<&serde_json::Value>, allowed: &[&str]) -> Option<String> {
    let text = value?.as_str()?;
    allowed.contains(&text).then(|| text.to_string())
}

/// One card, in the closed-world shape; `None` when the row is not usable.
fn card(value: &serde_json::Value) -> Option<serde_json::Value> {
    let object = value.as_object()?;
    let id = object.get("id")?.as_str()?.trim();
    if id.is_empty() || id.len() > 40 || !id.chars().all(|c| c.is_ascii() && !c.is_control()) {
        return None;
    }
    let region = allowed(object.get("region"), REGIONS)?;
    let order = int_in(object.get("order"), 0, 50)?;
    // H3/Q5: the seven fixed cards carry no col_span/row_span in the contract
    // (the renderer ignores their spans), so a missing span is defaulted to
    // the full-width value instead of refusing the document. A PRESENT span is
    // still bounded; a hostile one is refused.
    let col_span = match object.get("col_span") {
        None => 12,
        Some(value) => int_in(Some(value), 1, 12)?,
    };
    let row_span = match object.get("row_span") {
        None => 1,
        Some(value) => int_in(Some(value), 1, 4)?,
    };
    let visible = bool_of(object.get("visible"))?;
    let collapsed = bool_of(object.get("collapsed"))?;
    if PROTECTED_IDS.contains(&id) && !visible {
        return None;
    }
    let mut options = serde_json::Map::new();
    if let Some(tab) = object
        .get("options")
        .and_then(|o| o.as_object())
        .and_then(|o| allowed(o.get("tab"), STAGE_TABS))
    {
        options.insert("tab".to_string(), serde_json::Value::String(tab));
    }
    Some(serde_json::json!({
        "id": id,
        "region": region,
        "order": order,
        "col_span": col_span,
        "row_span": row_span,
        "visible": visible,
        "collapsed": collapsed,
        "options": serde_json::Value::Object(options),
    }))
}

/// Every card list, from the active document or from one saved user layout, is
/// validated by the same closed-world pass and sorted into the one canonical
/// order. Shared so the four protected cards can never be enforced differently
/// in the two places.
fn sanitise_cards(raw_cards: &[serde_json::Value]) -> Result<Vec<serde_json::Value>, String> {
    if raw_cards.is_empty() || raw_cards.len() > MAX_CARDS {
        return Err(format!(
            "the layout has {} cards; this build reads 1 to {MAX_CARDS}",
            raw_cards.len()
        ));
    }
    let mut cards = Vec::with_capacity(raw_cards.len());
    let mut seen = std::collections::BTreeSet::new();
    for row in raw_cards {
        let card = card(row).ok_or_else(|| "a card row is not readable".to_string())?;
        let card_id = card["id"].as_str().unwrap_or_default().to_string();
        if !seen.insert(card_id.clone()) {
            return Err(format!("the layout lists card `{card_id}` twice"));
        }
        cards.push(card);
    }
    for protected in PROTECTED_IDS {
        let row = cards
            .iter()
            .find(|card| card["id"].as_str() == Some(protected))
            .ok_or_else(|| format!("the layout omits the protected card `{protected}`"))?;
        if row["visible"].as_bool() != Some(true) {
            return Err(format!("the layout hides the protected card `{protected}`"));
        }
    }
    cards.sort_by(|a, b| {
        let a_region = a["region"].as_str().unwrap_or_default();
        let b_region = b["region"].as_str().unwrap_or_default();
        region_index(a_region)
            .cmp(&region_index(b_region))
            .then_with(|| {
                a["order"]
                    .as_i64()
                    .unwrap_or_default()
                    .cmp(&b["order"].as_i64().unwrap_or_default())
            })
            .then_with(|| {
                a["id"]
                    .as_str()
                    .unwrap_or_default()
                    .cmp(b["id"].as_str().unwrap_or_default())
            })
    });
    Ok(cards)
}

/// Whether an owner-saved layout id is in the one shape both sides write:
/// `custom-` plus lowercase letters/digits/hyphens (max 40 characters).
fn custom_id_ok(id: &str) -> bool {
    let Some(rest) = id.strip_prefix("custom-") else {
        return false;
    };
    !rest.is_empty()
        && id.len() <= 40
        && rest
            .chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-')
}

/// One owner-saved layout entry, in the closed-world shape.
fn sanitise_user_preset(entry: &serde_json::Value) -> Result<serde_json::Value, String> {
    let object = entry
        .as_object()
        .ok_or_else(|| "one saved layout is not a JSON object".to_string())?;
    let id = text_of(object.get("id"), 40).ok_or_else(|| "a saved layout has no id".to_string())?;
    if !custom_id_ok(&id) {
        return Err(format!(
            "the saved layout id `{id}` is not one this build writes"
        ));
    }
    let name = text_of(object.get("name"), MAX_USER_NAME)
        .ok_or_else(|| "a saved layout has no name".to_string())?;
    let base_preset = text_of(object.get("base_preset"), MAX_TEXT)
        .ok_or_else(|| "a saved layout names no base preset".to_string())?;
    // H3-3: the JS normalizer drops a saved layout whose base preset is not one
    // of the seven, so Rust must not store one either (otherwise the two
    // normalizers disagree and an entry can be saved-but-never-shown).
    if !known_preset(&base_preset) {
        return Err(format!(
            "a saved layout names an unknown base layout `{base_preset}`"
        ));
    }
    let shell_template = allowed(object.get("shell_template"), SHELL_TEMPLATES)
        .ok_or_else(|| "a saved layout names an unknown shell template".to_string())?;
    let density = allowed(object.get("density"), DENSITIES)
        .ok_or_else(|| "a saved layout names an unknown density".to_string())?;
    let default_stage_tab = allowed(object.get("default_stage_tab"), STAGE_TABS)
        .ok_or_else(|| "a saved layout names an unknown stage tab".to_string())?;
    let raw_cards = object
        .get("cards")
        .and_then(|cards| cards.as_array())
        .ok_or_else(|| "a saved layout has no card list".to_string())?;
    let cards = sanitise_cards(raw_cards)?;
    Ok(serde_json::json!({
        "id": id,
        "name": name,
        "base_preset": base_preset,
        "shell_template": shell_template,
        "density": density,
        "default_stage_tab": default_stage_tab,
        "cards": cards,
    }))
}

fn region_index(region: &str) -> i64 {
    REGIONS
        .iter()
        .position(|name| *name == region)
        .unwrap_or(99) as i64
}

/// Validate and rewrite one layout document into its canonical, closed-world
/// form. Unknown keys and `x`/`y` are dropped, never copied; a document that
/// would hide or omit a protected card is refused outright.
pub fn sanitise(value: &serde_json::Value) -> Result<serde_json::Value, String> {
    let object = value
        .as_object()
        .ok_or_else(|| "the layout is not a JSON object".to_string())?;
    if object.get("version").and_then(|v| v.as_u64()) != Some(LAYOUT_VERSION) {
        return Err(format!(
            "the layout is version {:?}, but this build reads version {LAYOUT_VERSION}",
            object.get("version")
        ));
    }
    let base_preset = text_of(object.get("base_preset"), MAX_TEXT)
        .ok_or_else(|| "the layout names no base preset".to_string())?;
    let id =
        text_of(object.get("id"), MAX_TEXT).ok_or_else(|| "the layout has no id".to_string())?;
    let name = text_of(object.get("name"), MAX_TEXT)
        .ok_or_else(|| "the layout has no name".to_string())?;
    let shell_template = allowed(object.get("shell_template"), SHELL_TEMPLATES)
        .ok_or_else(|| "the layout names an unknown shell template".to_string())?;
    let density = allowed(object.get("density"), DENSITIES)
        .ok_or_else(|| "the layout names an unknown density".to_string())?;
    let default_stage_tab = allowed(object.get("default_stage_tab"), STAGE_TABS)
        .ok_or_else(|| "the layout names an unknown stage tab".to_string())?;
    let updated_at = int_in(object.get("updated_at"), 0, i64::MAX / 2)
        .ok_or_else(|| "the layout has no sane updated_at".to_string())?;
    let raw_cards = object
        .get("cards")
        .and_then(|cards| cards.as_array())
        .ok_or_else(|| "the layout has no card list".to_string())?;
    let cards = sanitise_cards(raw_cards)?;
    // The owner-saved layouts travel with the active document (H3). They are
    // validated by the SAME card pass; the library is bounded; and a document
    // whose active id is a saved layout must actually carry that entry.
    let empty = Vec::new();
    let raw_users = object
        .get("user_presets")
        .and_then(|value| value.as_array())
        .unwrap_or(&empty);
    if raw_users.len() > MAX_USER_PRESETS {
        return Err(format!(
            "the layout carries {} saved layouts; this build keeps up to {MAX_USER_PRESETS}",
            raw_users.len()
        ));
    }
    let mut users = Vec::with_capacity(raw_users.len());
    let mut user_ids = std::collections::BTreeSet::new();
    for entry in raw_users {
        let clean = sanitise_user_preset(entry)?;
        let entry_id = clean["id"].as_str().unwrap_or_default().to_string();
        if !user_ids.insert(entry_id.clone()) {
            return Err(format!("the saved layout `{entry_id}` is listed twice"));
        }
        users.push(clean);
    }
    if custom_id_ok(&id) && !user_ids.contains(&id) {
        return Err(format!(
            "the active layout `{id}` is not in the saved-layout list"
        ));
    }
    let clean = serde_json::json!({
        "version": LAYOUT_VERSION,
        "id": id,
        "name": name,
        "base_preset": base_preset,
        "shell_template": shell_template,
        "density": density,
        "default_stage_tab": default_stage_tab,
        "cards": cards,
        "user_presets": users,
        "updated_at": updated_at,
    });
    if serde_json::to_vec(&clean)
        .map(|bytes| bytes.len())
        .unwrap_or(0)
        > MAX_DOCUMENT_BYTES
    {
        return Err("the saved layouts are larger than this build allows".to_string());
    }
    Ok(clean)
}

/// What the picker/HUD gets back, and where it came from.
#[derive(Debug, Clone, Serialize)]
pub struct LayoutAnswer {
    /// The validated layout, or None when nothing has ever been saved.
    pub layout: Option<serde_json::Value>,
    /// "saved", "last_good" (the saved copy was unusable) or "none".
    pub source: String,
}

/// The document the caller should render: the saved one when it validates,
/// otherwise the last good one, otherwise nothing (the caller then migrates the
/// old three-way value or falls back to Cockpit, exactly like a fresh install).
pub fn choose(
    saved: Option<&serde_json::Value>,
    last_good: Option<&serde_json::Value>,
) -> LayoutAnswer {
    if let Some(saved) = saved {
        if let Ok(layout) = sanitise(saved) {
            return LayoutAnswer {
                layout: Some(layout),
                source: "saved".to_string(),
            };
        }
    }
    if let Some(last_good) = last_good {
        if let Ok(layout) = sanitise(last_good) {
            return LayoutAnswer {
                layout: Some(layout),
                source: "last_good".to_string(),
            };
        }
    }
    LayoutAnswer {
        layout: None,
        source: "none".to_string(),
    }
}

/// Read the saved layout (appearance-class: no card, no backend, no token).
#[tauri::command]
pub fn get_hud_layout(app: AppHandle) -> LayoutAnswer {
    let Ok(store) = app.store(crate::commands::SETTINGS_STORE) else {
        return LayoutAnswer {
            layout: None,
            source: "none".to_string(),
        };
    };
    let saved = store.get(STORE_KEY);
    let last_good = store.get(LAST_GOOD_KEY);
    choose(saved.as_ref(), last_good.as_ref())
}

/// Save a validated layout. A document that fails validation is REFUSED and
/// the last good copy is left untouched (so a hand-edited settings file can
/// never destroy the owner's layout).
#[tauri::command]
pub fn set_hud_layout(app: AppHandle, layout: serde_json::Value) -> Result<LayoutAnswer, String> {
    let clean = sanitise(&layout)?;
    let store = app
        .store(crate::commands::SETTINGS_STORE)
        .map_err(|e| format!("settings store unavailable: {e}"))?;
    store.set(LAST_GOOD_KEY, clean.clone());
    store.set(STORE_KEY, clean.clone());
    store
        .save()
        .map_err(|e| format!("could not save the HUD layout: {e}"))?;
    Ok(LayoutAnswer {
        layout: Some(clean),
        source: "saved".to_string(),
    })
}

/// Open the HUD window in edit mode (Settings -> "The big HUD window" ->
/// "Edit HUD in the window", H2 2026-10-22). It shows and focuses the owner's
/// own HUD window and emits `jarvis:hud-edit-request`, which the injected
/// bootstrap forwards to the page as a DOM event; the page then enters its
/// edit mode. It writes no setting, raises no card and approves nothing.
#[tauri::command]
pub fn open_hud_edit(app: AppHandle) -> Result<(), String> {
    let Some(hud) = app.get_webview_window("hud") else {
        return Err("the HUD window is not open".to_string());
    };
    hud.show()
        .map_err(|e| format!("could not show the HUD window: {e}"))?;
    hud.set_focus()
        .map_err(|e| format!("could not focus the HUD window: {e}"))?;
    hud.emit("jarvis:hud-edit-request", ())
        .map_err(|e| format!("could not ask the HUD window to edit: {e}"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn base() -> serde_json::Value {
        let protected = |id: &str, region: &str| {
            serde_json::json!({
                "id": id,
                "region": region,
                "order": 0,
                "col_span": 12,
                "row_span": 1,
                "visible": true,
                "collapsed": false,
                "options": {},
            })
        };
        serde_json::json!({
            "version": 1,
            "id": "cockpit",
            "name": "Cockpit",
            "base_preset": "cockpit",
            "shell_template": "three-column",
            "density": "comfortable",
            "default_stage_tab": "talk",
            "cards": [
                protected("emergency_stop", "header"),
                protected("bar_launcher", "left_rail"),
                { "id": "nav", "region": "left_rail", "order": 0, "col_span": 12,
                  "row_span": 2, "visible": true, "collapsed": false, "options": {} },
                protected("approvals", "stage_top"),
                protected("voice_controls", "stage_top"),
            ],
            "user_presets": [],
            "updated_at": 0,
        })
    }

    #[test]
    fn a_valid_layout_round_trips_unchanged() {
        let doc = base();
        assert_eq!(sanitise(&doc).unwrap(), doc);
        let clean = sanitise(&doc).unwrap();
        assert_eq!(sanitise(&clean).unwrap(), clean);
    }

    #[test]
    fn the_wrong_version_is_refused_rather_than_guessed() {
        let mut doc = base();
        doc["version"] = serde_json::json!(2);
        assert!(sanitise(&doc).is_err());
        doc["version"] = serde_json::json!("1");
        assert!(sanitise(&doc).is_err());
        doc.as_object_mut().unwrap().remove("version");
        assert!(sanitise(&doc).is_err());
    }

    #[test]
    fn unknown_keys_and_x_y_are_dropped_never_copied() {
        let mut doc = base();
        doc["evil"] = serde_json::json!("<script>");
        doc["cards"][0]["x"] = serde_json::json!(3);
        doc["cards"][0]["y"] = serde_json::json!(9);
        doc["cards"][0]["evil"] = serde_json::json!(true);
        let clean = sanitise(&doc).unwrap();
        assert!(clean.get("evil").is_none());
        assert!(clean["cards"][0].get("x").is_none());
        assert!(clean["cards"][0].get("y").is_none());
        assert!(clean["cards"][0].get("evil").is_none());
    }

    #[test]
    fn out_of_range_numbers_and_enums_are_refused() {
        for (path, bad) in [
            ("region", serde_json::json!("nowhere")),
            ("order", serde_json::json!(51)),
            ("col_span", serde_json::json!(0)),
            ("row_span", serde_json::json!(9)),
        ] {
            let mut doc = base();
            doc["cards"][2][path] = bad.clone();
            assert!(sanitise(&doc).is_err(), "{path}={bad} was accepted");
        }
        for path in ["shell_template", "density", "default_stage_tab"] {
            let mut doc = base();
            doc[path] = serde_json::json!("neon");
            assert!(sanitise(&doc).is_err(), "{path} accepted an unknown token");
        }
    }

    #[test]
    fn a_hidden_or_missing_protected_card_is_refused() {
        for id in PROTECTED_IDS {
            let mut doc = base();
            let at = doc["cards"]
                .as_array()
                .unwrap()
                .iter()
                .position(|card| card["id"].as_str() == Some(id))
                .unwrap();
            doc["cards"][at]["visible"] = serde_json::json!(false);
            assert!(sanitise(&doc).is_err(), "{id} could be hidden");
            let mut doc = base();
            doc["cards"]
                .as_array_mut()
                .unwrap()
                .retain(|card| card["id"].as_str() != Some(id));
            assert!(sanitise(&doc).is_err(), "{id} could be omitted");
        }
    }

    #[test]
    fn duplicate_cards_are_refused() {
        let mut doc = base();
        let nav = doc["cards"][2].clone();
        doc["cards"].as_array_mut().unwrap().push(nav);
        assert!(sanitise(&doc).is_err());
    }

    #[test]
    fn cards_are_sorted_into_the_one_canonical_order() {
        let mut doc = base();
        doc["cards"].as_array_mut().unwrap().reverse();
        let clean = sanitise(&doc).unwrap();
        let regions: Vec<String> = clean["cards"]
            .as_array()
            .unwrap()
            .iter()
            .map(|card| card["region"].as_str().unwrap().to_string())
            .collect();
        let mut sorted = regions.clone();
        sorted.sort_by_key(|region| region_index(region));
        assert_eq!(regions, sorted);
    }

    #[test]
    fn choose_prefers_a_valid_saved_copy_then_the_last_good_one_then_none() {
        let good = base();
        let mut bad = base();
        bad["version"] = serde_json::json!(9);
        assert_eq!(choose(Some(&good), None).source, "saved");
        assert_eq!(choose(Some(&bad), None).source, "none");
        assert_eq!(choose(Some(&bad), Some(&good)).source, "last_good");
        assert_eq!(choose(None, Some(&good)).source, "last_good");
        assert_eq!(choose(None, None).source, "none");
        assert!(choose(None, None).layout.is_none());
    }

    #[test]
    fn a_saved_focus_layout_is_still_accepted_after_the_quiet_rename() {
        // F7 (2026-10-22): the JS normalizer maps "focus" to "quiet" silently.
        // This side only has to keep STORING such a document (the store's
        // closed-world validator must not reject an owner's saved layout just
        // because the label changed); the page bootstrap already accepts the
        // old id, and H2 normalizes it on load.
        let mut doc = base();
        doc["id"] = serde_json::json!("focus");
        doc["name"] = serde_json::json!("Focus");
        doc["base_preset"] = serde_json::json!("focus");
        doc["shell_template"] = serde_json::json!("two-column-left");
        let clean = sanitise(&doc).expect("a saved focus layout must stay storable");
        assert_eq!(clean["base_preset"], "focus");
        assert_eq!(clean["id"], "focus");
    }

    #[test]
    fn the_contract_mirror_has_the_seven_presets_and_they_all_validate() {
        let text = include_str!("../../../contract/hud-presets.json");
        let doc: serde_json::Value = serde_json::from_str(text).unwrap();
        let presets = doc["presets"].as_array().unwrap();
        assert_eq!(presets.len(), 7);
        let ids: Vec<&str> = presets
            .iter()
            .map(|preset| preset["id"].as_str().unwrap())
            .collect();
        // Focus was renamed Quiet on 2026-10-22 (coherence slice F7). The
        // contract carries the new id; the JS normalizer keeps "focus" as a
        // silent migration alias for a saved document.
        assert_eq!(
            ids,
            [
                "cockpit",
                "studio",
                "ambient",
                "quiet",
                "telemetry",
                "second_brain",
                "minimal"
            ]
        );
        for preset in presets {
            sanitise(preset).unwrap_or_else(|e| panic!("{}: {e}", preset["id"]));
            assert!(
                preset.get("theme").is_none(),
                "the contract still carries theme"
            );
            for card in preset["cards"].as_array().unwrap() {
                let id = card["id"].as_str().unwrap();
                let fixed = [
                    "emergency_stop",
                    "voice_controls",
                    "conversation",
                    "composer",
                    "galaxy",
                    "reminders",
                    "memory",
                ];
                if fixed.contains(&id) {
                    assert!(
                        card.get("col_span").is_none(),
                        "the contract still carries an inert span for {id}"
                    );
                    assert!(
                        card.get("row_span").is_none(),
                        "the contract still carries an inert span for {id}"
                    );
                }
            }
        }
    }

    fn card_row(id: &str, region: &str) -> serde_json::Value {
        serde_json::json!({
            "id": id, "region": region, "order": 0, "col_span": 12,
            "row_span": 1, "visible": true, "collapsed": false, "options": {},
        })
    }

    fn user_layout(id: &str, name: &str) -> serde_json::Value {
        serde_json::json!({
            "id": id,
            "name": name,
            "base_preset": "cockpit",
            "shell_template": "three-column",
            "density": "comfortable",
            "default_stage_tab": "talk",
            "cards": [
                card_row("emergency_stop", "header"),
                card_row("bar_launcher", "left_rail"),
                card_row("nav", "left_rail"),
                card_row("approvals", "stage_top"),
                card_row("voice_controls", "stage_top"),
            ],
        })
    }

    #[test]
    fn a_saved_layout_library_round_trips_and_is_bounded() {
        let mut doc = base();
        let layout = user_layout("custom-cockpit-1", "Evening");
        doc["id"] = serde_json::json!("custom-cockpit-1");
        doc["name"] = serde_json::json!("Evening");
        doc["user_presets"] = serde_json::json!([layout]);
        let clean = sanitise(&doc).unwrap();
        assert_eq!(clean["id"], "custom-cockpit-1");
        assert_eq!(clean["user_presets"].as_array().unwrap().len(), 1);
        assert_eq!(sanitise(&clean).unwrap(), clean);
    }

    #[test]
    fn hostile_or_unbounded_saved_layouts_are_refused() {
        // 21 layouts.
        let mut doc = base();
        let many: Vec<serde_json::Value> = (1..=21)
            .map(|n| user_layout(&format!("custom-cockpit-{n}"), "Mine"))
            .collect();
        doc["user_presets"] = serde_json::json!(many);
        assert!(sanitise(&doc).is_err(), "21 saved layouts were accepted");

        // A custom active id with no entry.
        let mut doc = base();
        doc["id"] = serde_json::json!("custom-missing-1");
        assert!(sanitise(&doc).is_err(), "an orphan active id was accepted");

        // A bad id shape and a duplicate id.
        for id in ["mine-1", "custom-", "custom-UPPER"] {
            let mut doc = base();
            doc["user_presets"] = serde_json::json!([user_layout(id, "Mine")]);
            assert!(sanitise(&doc).is_err(), "{id} was accepted as a saved id");
        }
        let mut doc = base();
        let one = user_layout("custom-cockpit-1", "Mine");
        doc["user_presets"] = serde_json::json!([one.clone(), one]);
        assert!(
            sanitise(&doc).is_err(),
            "a duplicate saved layout was accepted"
        );

        // A saved layout that hides a protected card.
        let mut doc = base();
        let mut bad = user_layout("custom-cockpit-1", "Mine");
        bad["cards"][3]["visible"] = serde_json::json!(false);
        doc["user_presets"] = serde_json::json!([bad]);
        assert!(
            sanitise(&doc).is_err(),
            "a saved layout could hide approvals"
        );

        // An empty name.
        let mut doc = base();
        doc["user_presets"] = serde_json::json!([user_layout("custom-cockpit-1", "   ")]);
        assert!(
            sanitise(&doc).is_err(),
            "an empty saved-layout name was accepted"
        );

        // H3-3: an unknown base preset is refused here too, so Rust can never
        // store an entry the page's normalizer would silently drop.
        let mut doc = base();
        let mut stranger = user_layout("custom-cockpit-1", "Mine");
        stranger["base_preset"] = serde_json::json!("holodeck");
        doc["user_presets"] = serde_json::json!([stranger]);
        assert!(
            sanitise(&doc).is_err(),
            "an unknown base preset was accepted"
        );
    }

    #[test]
    fn the_old_focus_name_is_still_an_accepted_base_preset() {
        // F7: the JS normalizer migrates "focus" to "quiet"; the save road must
        // not refuse an owner's H2-era saved layout because the label changed.
        let mut doc = base();
        let mut old = user_layout("custom-focus-1", "Evening");
        old["base_preset"] = serde_json::json!("focus");
        doc["user_presets"] = serde_json::json!([old]);
        let clean = sanitise(&doc).expect("an old focus-saved layout must stay storable");
        assert_eq!(clean["user_presets"][0]["base_preset"], "focus");
    }

    #[test]
    fn a_layouts_theme_is_dropped_not_required() {
        // H3/Q5: colour theme belongs to Appearance; an old saved document that
        // still carries one must keep loading, with the key dropped.
        let mut doc = base();
        doc["theme"] = serde_json::json!("paper");
        let clean = sanitise(&doc).unwrap();
        assert!(clean.get("theme").is_none(), "theme was copied through");
    }
}
