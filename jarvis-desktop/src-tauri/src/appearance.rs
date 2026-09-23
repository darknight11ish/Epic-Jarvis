//! Which face Jarvis wears, and how each state looks — stored where both
//! clients can reach it.
//!
//! ## Why this is not just a local setting
//!
//! The visual spec's own first sentence is that Android and the desktop cannot
//! share drawing code — one is Compose, one is a webview — so what they share
//! is DATA. A choice of face is exactly that data, and a choice that lives only
//! on the desktop is half a feature: the owner picks `orbit` on the laptop and
//! the phone carries on wearing `arc`.
//!
//! So the server is the truth when it is reachable, and the local store is a
//! cache and an offline fallback. Whichever client writes last wins, which is
//! the right rule for a single-owner machine and the wrong one for a team —
//! there is one owner here.
//!
//! ## The route exists once `appearance.patch` is applied
//!
//! `GET /api/appearance` and `POST /api/appearance` were first a proposal,
//! written up in `docs/APPEARANCE-API.md`. `backend/appearance.patch` now adds
//! both to `jarvis_hud.py` (tested by `backend/test_appearance.py`): the
//! document lives in `appearance.json` beside `config.toml`, a save publishes
//! an `appearance` event, and the write carries the same origin and token
//! checks as the other desktop-only routes. It needs no approval: it is
//! cosmetic, and `backend/README.md` says why it should stay that way.
//!
//! The backend lives on the owner's machine, not in this repo, so whether a
//! given backend has the patch is only known at run time. One without it
//! answers 404 or 501, and then every read falls back to the local store and
//! every write reports that it stayed local. That is deliberately visible in
//! the UI rather than silent: a picker that claims to have changed the phone
//! when it has not is worse than one that says it could not.
//!
//! `/api/config` was the obvious existing home and is not one — it is a read on
//! this side and a 501 on the server, so there is no write path to borrow.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_store::StoreExt;

use crate::commands;

/// Key in the settings store.
const STORE_KEY: &str = "appearance";

/// The route this module reads and writes (`backend/appearance.patch`).
const ROUTE: &str = "/api/appearance";

/// Short: this is read on the way into a window the user is already looking at,
/// and a stalled request would leave the editor blank.
const TIMEOUT: std::time::Duration = std::time::Duration::from_millis(2_500);

/// How one state should look: a pattern, a colour, and the pattern's own knobs.
///
/// Deliberately the same shape the kit's `BIND` already uses and the same shape
/// `resolve()` takes in both renderers, so nothing has to translate.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Binding {
    pub pattern: String,
    /// Absent for the patterns whose `kind` is `hue_sweep` — `rainbow` and
    /// `sweep` generate their own hues and ignore it, so storing a colour
    /// there would imply it does something.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub color: Option<String>,
    #[serde(default, skip_serializing_if = "serde_json::Map::is_empty")]
    pub params: serde_json::Map<String, serde_json::Value>,
}

/// The whole appearance document.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Appearance {
    /// The face id, or `None` to leave the client's own default alone.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub face: Option<String>,
    /// State id to binding. A state that is absent keeps the spec's default,
    /// so a client that has never been edited is not a client with no face.
    #[serde(default)]
    pub bindings: BTreeMap<String, Binding>,
    /// Unix seconds at the last write. The tie-break between two clients.
    #[serde(default)]
    pub updated: f64,
}

/// The appearance as the rest of the process sees it.
///
/// Cached in memory because the tray asks for a binding on every repaint —
/// twice a second while a pattern animates — and neither a disk read nor a
/// network round trip belongs on that path.
#[derive(Default)]
pub struct AppearanceState(std::sync::Mutex<Appearance>);

impl AppearanceState {
    fn put(&self, doc: &Appearance) {
        *self
            .0
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner()) = doc.clone();
    }

    /// A copy of the whole document, for the HUD window.
    ///
    /// That window cannot ask for it (`capabilities/hud.json` grants it one
    /// command, the mic button's, and no read), so `lib.rs` pushes this into
    /// it when its page loads.
    pub fn snapshot(&self) -> Appearance {
        self.0
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .clone()
    }

    /// The owner's binding for a state, if they have set one.
    ///
    /// Returns `None` for a state they have not touched, so the caller falls
    /// through to the spec's default — a document that binds `idle` and
    /// nothing else must not blank the other seven.
    pub fn binding(&self, state_id: &str) -> Option<crate::spec::Binding> {
        let doc = self
            .0
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let bound = doc.bindings.get(state_id)?;
        if bound.pattern.trim().is_empty() {
            return None;
        }
        Some(crate::spec::Binding {
            pattern: bound.pattern.clone(),
            color: bound.color.clone(),
            // `to`, `family` and `colors` are pattern-level slots the editor
            // does not expose. Leaving them None means `resolve` takes them
            // from the pattern, which is what an unedited binding does too.
            to: None,
            family: None,
            colors: None,
            params: bound.params.clone(),
        })
    }
}

/// Where the document that is being shown came from, so the UI can say.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Loaded {
    #[serde(flatten)]
    pub appearance: Appearance,
    /// `"server"`, `"local"`, or `"default"` when nothing has ever been saved.
    pub source: String,
    /// True when the server holds this, so the phone sees it too.
    pub shared: bool,
    /// Why it is not shared, when it is not.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub note: Option<String>,
}

/// Puts a document into the cache and repaints whatever renders from it.
///
/// Without this the Faces window edited a document nothing else read: the tray
/// carried on drawing the spec defaults while the editor said "saved". Every
/// path that learns a new document calls this.
fn adopt(app: &AppHandle, doc: &Appearance) {
    app.state::<AppearanceState>().put(doc);
    crate::tray::on_appearance_changed(app);
    let _ = app.emit(crate::events::APPEARANCE_CHANGED, ());
    // The HUD cannot hear that event - its page's own CSP refuses Tauri's
    // IPC - so its reactor, which wears this same face, is handed the
    // document directly. See `push_to_hud`.
    crate::push_to_hud(app, "appearance", doc);
}

/// Loads the stored document at startup so the tray wears it immediately.
///
/// Local only, and deliberately: this runs during `setup`, and a network read
/// there would hold the tray's first paint behind a socket timeout.
pub fn adopt_at_startup(app: &AppHandle) {
    if let Some(doc) = local(app) {
        adopt(app, &doc);
    }
}

fn now() -> f64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or_default()
}

fn client() -> Option<reqwest::Client> {
    reqwest::Client::builder()
        .connect_timeout(TIMEOUT)
        .timeout(TIMEOUT)
        .no_proxy()
        .build()
        .ok()
}

fn local(app: &AppHandle) -> Option<Appearance> {
    app.store(commands::SETTINGS_STORE)
        .ok()
        .and_then(|store| store.get(STORE_KEY))
        .and_then(|v| serde_json::from_value(v).ok())
}

fn save_local(app: &AppHandle, doc: &Appearance) -> Result<(), String> {
    let store = app
        .store(commands::SETTINGS_STORE)
        .map_err(|e| format!("settings store unavailable: {e}"))?;
    store.set(
        STORE_KEY,
        serde_json::to_value(doc).map_err(|e| e.to_string())?,
    );
    store
        .save()
        .map_err(|e| format!("could not write the settings store: {e}"))
}

/// Reads the server's copy, or `Err` with a reason worth showing.
async fn from_server(app: &AppHandle) -> Result<Appearance, String> {
    let base = commands::jarvis_base(app);
    let client = client().ok_or("could not build an HTTP client")?;
    let headers = commands::jarvis_headers(app)?;
    let response = client
        .get(format!("{base}{ROUTE}"))
        .headers(headers)
        .send()
        .await
        .map_err(|e| {
            if e.is_connect() {
                format!("Jarvis is not answering at {base}")
            } else {
                format!("{ROUTE}: {e}")
            }
        })?;

    let status = response.status();
    if status.as_u16() == 404 || status.as_u16() == 501 {
        // The expected answer today, and not an error worth alarming about.
        return Err(format!(
            "This backend has no {ROUTE} yet, so the choice stays on this machine."
        ));
    }
    if !status.is_success() {
        return Err(format!("{ROUTE} answered HTTP {}", status.as_u16()));
    }
    let body: serde_json::Value = response
        .json()
        .await
        .map_err(|e| format!("{ROUTE} returned something unreadable: {e}"))?;
    // `{"available": false}` is the API's way of saying a capability is absent,
    // and §7 says hide the feature rather than show an empty one.
    if body.get("available").and_then(|v| v.as_bool()) == Some(false) {
        return Err(format!("{ROUTE} reports the capability is not installed."));
    }
    serde_json::from_value(body).map_err(|e| format!("{ROUTE} returned an unexpected shape: {e}"))
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

/// The appearance to show, and an honest account of where it came from.
///
/// Server first. It is the only copy the phone can also see, so a disagreement
/// between the two is resolved in favour of the one that is shared — otherwise
/// opening the editor on the desktop would quietly overwrite the phone's choice
/// with a stale local cache the next time anything was saved.
#[tauri::command]
pub async fn get_appearance(app: AppHandle) -> Loaded {
    match from_server(&app).await {
        Ok(appearance) => {
            // Mirror it locally so the next cold start has something to show
            // before the network answers.
            let _ = save_local(&app, &appearance);
            adopt(&app, &appearance);
            Loaded {
                appearance,
                source: "server".into(),
                shared: true,
                note: None,
            }
        }
        Err(why) => match local(&app) {
            Some(appearance) => {
                adopt(&app, &appearance);
                Loaded {
                    appearance,
                    source: "local".into(),
                    shared: false,
                    note: Some(why),
                }
            }
            None => Loaded {
                appearance: Appearance::default(),
                source: "default".into(),
                shared: false,
                note: Some(why),
            },
        },
    }
}

/// The appearance document this process is already wearing, from memory.
///
/// For a window that only needs to DRAW the owner's face - the Widget's live
/// face - rather than show where it came from. Unlike [`get_appearance`] it
/// makes no network call and broadcasts nothing, so a window may call it
/// from its own `appearance-changed` listener without starting a loop (that
/// command re-broadcasts the event every time it is called).
#[tauri::command]
pub fn appearance_snapshot(app: AppHandle) -> Appearance {
    app.state::<AppearanceState>().snapshot()
}

/// One state's colour for the window chrome - see [`appearance_colours`].
#[derive(Debug, Clone, Serialize)]
pub struct ChromeColour {
    /// `#rrggbb`.
    pub hex: String,
    /// The colour's palette family, deep to mist, when it has one.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ramp: Option<Vec<String>>,
    /// This colour's index in `ramp`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub step: Option<usize>,
}

/// The owner's state colours, as fixed values the window chrome can use: the
/// Brain's state dots and the accent (jarvis-link.js `followAppearance`).
///
/// Only the states the owner has bound. An unbound state keeps the colour
/// theme.css tuned for it, because those were measured against every theme's
/// surfaces and a spec default re-derived here would undo that. From memory,
/// like [`appearance_snapshot`]: no network, no broadcast.
#[tauri::command]
pub fn appearance_colours(app: AppHandle) -> BTreeMap<String, ChromeColour> {
    let state = app.state::<AppearanceState>();
    let mut out = BTreeMap::new();
    for id in [
        "idle",
        "listening",
        "thinking",
        "speaking",
        "approval",
        "standby",
        "error",
        "banked",
    ] {
        let Some(bind) = state.binding(id) else {
            continue;
        };
        let rgb = crate::spec::static_colour(&bind);
        let (ramp, step) = match crate::spec::family_ramp_of(rgb) {
            Some((ramp, i)) => (
                Some(ramp.into_iter().map(crate::spec::rgb_hex).collect()),
                Some(i),
            ),
            None => (None, None),
        };
        out.insert(
            id.to_string(),
            ChromeColour {
                hex: crate::spec::rgb_hex(rgb),
                ramp,
                step,
            },
        );
    }
    out
}

/// Saves. Always locally; to the server too when there is one.
///
/// The local write happens FIRST and unconditionally. A save that only
/// succeeded when the backend was up would lose the owner's work every time
/// they edited with Jarvis stopped, which is exactly when someone sits down to
/// fiddle with how it looks.
#[tauri::command]
pub async fn set_appearance(app: AppHandle, appearance: Appearance) -> Result<Loaded, String> {
    let mut doc = appearance;
    doc.updated = now();
    save_local(&app, &doc)?;
    // Before the network, not after: the desktop must obey a save even when
    // the backend is unreachable, and the editor's own window is the last
    // place that should be the only one that changed.
    adopt(&app, &doc);

    let base = commands::jarvis_base(&app);
    let Some(client) = client() else {
        return Ok(Loaded {
            appearance: doc,
            source: "local".into(),
            shared: false,
            note: Some("could not build an HTTP client".into()),
        });
    };
    let headers = match commands::jarvis_headers(&app) {
        Ok(headers) => headers,
        Err(err) => {
            return Ok(Loaded {
                appearance: doc,
                source: "local".into(),
                shared: false,
                note: Some(err),
            })
        }
    };

    let sent = client
        .post(format!("{base}{ROUTE}"))
        .headers(headers)
        .json(&doc)
        .send()
        .await;

    let note = match sent {
        Ok(response) if response.status().is_success() => None,
        Ok(response) => Some(match response.status().as_u16() {
            404 | 501 => format!(
                "Saved on this machine. This backend has no {ROUTE}, so the phone \
                 will not see it."
            ),
            code => format!("Saved on this machine. {ROUTE} answered HTTP {code}."),
        }),
        Err(err) if err.is_connect() => Some(format!(
            "Saved on this machine. Jarvis is not answering at {base}, so the phone \
             will not see it yet."
        )),
        Err(err) => Some(format!("Saved on this machine. {ROUTE}: {err}")),
    };

    Ok(Loaded {
        appearance: doc,
        shared: note.is_none(),
        source: if note.is_none() {
            "server".into()
        } else {
            "local".into()
        },
        note,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A document that binds one state must not blank the other seven.
    ///
    /// This is the bug the cache exists to make impossible in the other
    /// direction, and the one it could easily introduce in this one: a lookup
    /// that returned `Some(default)` for an unbound state would override the
    /// spec with an empty pattern everywhere.
    #[test]
    fn an_unbound_state_falls_through_to_the_spec() {
        let state = AppearanceState::default();
        state.put(&Appearance {
            face: None,
            bindings: [(
                "idle".to_string(),
                Binding {
                    pattern: "pulse".into(),
                    color: Some("violet-4".into()),
                    params: Default::default(),
                },
            )]
            .into_iter()
            .collect(),
            updated: 1.0,
        });
        assert!(state.binding("idle").is_some(), "the bound state was lost");
        assert!(
            state.binding("thinking").is_none(),
            "an unbound state overrode the spec instead of falling through"
        );
        assert!(state.binding("banked").is_none());
    }

    /// An empty pattern is not a binding. It would resolve to the fallback
    /// colour on every surface, which looks like the icon breaking.
    #[test]
    fn a_blank_pattern_is_not_treated_as_a_choice() {
        let state = AppearanceState::default();
        state.put(&Appearance {
            face: None,
            bindings: [(
                "idle".to_string(),
                Binding {
                    pattern: "   ".into(),
                    color: None,
                    params: Default::default(),
                },
            )]
            .into_iter()
            .collect(),
            updated: 1.0,
        });
        assert!(state.binding("idle").is_none());
    }

    /// The editor's per-binding params are where three of the eight states
    /// actually live — `thinking` is `sweep` narrowed to a 58° band. Dropping
    /// them renders the pattern's generic default instead.
    #[test]
    fn params_survive_the_conversion() {
        let state = AppearanceState::default();
        let mut params = serde_json::Map::new();
        params.insert("span_deg".into(), serde_json::json!(58));
        state.put(&Appearance {
            face: None,
            bindings: [(
                "thinking".to_string(),
                Binding {
                    pattern: "sweep".into(),
                    color: None,
                    params,
                },
            )]
            .into_iter()
            .collect(),
            updated: 1.0,
        });
        let bound = state.binding("thinking").expect("binding lost");
        assert_eq!(bound.params.get("span_deg"), Some(&serde_json::json!(58)));
    }

    #[test]
    fn the_hud_snapshot_is_the_whole_document() {
        // The HUD's reactor picks its face from `face` and its colours from
        // `bindings`, so the push has to carry both, as the page will read
        // them: the same field names the Faces window saves.
        let state = AppearanceState::default();
        let mut doc = Appearance {
            face: Some("orbit".into()),
            ..Default::default()
        };
        doc.bindings.insert(
            "thinking".into(),
            Binding {
                pattern: "breathe".into(),
                color: Some("amber-4".into()),
                params: serde_json::Map::new(),
            },
        );
        state.put(&doc);
        let pushed = serde_json::to_value(state.snapshot()).unwrap();
        assert_eq!(pushed["face"], "orbit");
        assert_eq!(pushed["bindings"]["thinking"]["pattern"], "breathe");
        assert_eq!(pushed["bindings"]["thinking"]["color"], "amber-4");
    }

    #[test]
    fn a_binding_round_trips() {
        let json = r#"{"pattern":"breathe","color":"ice-3"}"#;
        let b: Binding = serde_json::from_str(json).unwrap();
        assert_eq!(b.pattern, "breathe");
        assert_eq!(b.color.as_deref(), Some("ice-3"));
        // `params` is absent rather than an empty object, so the document the
        // phone receives is the document the desktop meant.
        assert_eq!(serde_json::to_string(&b).unwrap(), json);
    }

    #[test]
    fn a_hue_generating_pattern_stores_no_colour() {
        // `rainbow` and `sweep` are `hue_sweep`: they generate their own hues
        // and ignore the colour. Writing one anyway would imply it does
        // something.
        let b: Binding = serde_json::from_str(r#"{"pattern":"rainbow"}"#).unwrap();
        assert!(b.color.is_none());
        assert_eq!(
            serde_json::to_string(&b).unwrap(),
            r#"{"pattern":"rainbow"}"#
        );
    }

    #[test]
    fn an_empty_document_is_not_a_document_with_no_face() {
        // A state that is absent keeps the spec's default. A client that has
        // never been edited must not render as unbound.
        let a: Appearance = serde_json::from_str("{}").unwrap();
        assert!(a.face.is_none());
        assert!(a.bindings.is_empty());
    }

    #[test]
    fn unknown_fields_from_a_newer_client_do_not_break_the_read() {
        // The phone may write a field this build has never heard of. Refusing
        // the whole document over it would make the older client unusable.
        let json = r#"{"face":"orbit","bindings":{},"updated":1.0,"mood":"calm"}"#;
        let a: Appearance = serde_json::from_str(json).unwrap();
        assert_eq!(a.face.as_deref(), Some("orbit"));
    }
}
