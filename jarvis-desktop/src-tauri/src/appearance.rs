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
//! ## The route does not exist yet
//!
//! `GET /api/appearance` and `POST /api/appearance` are a proposal, written up
//! in `docs/APPEARANCE-API.md`. Today the backend answers neither, so every
//! read falls back to the local store and every write reports that it stayed
//! local. That is deliberately visible in the UI rather than silent: a picker
//! that claims to have changed the phone when it has not is worse than one that
//! says it could not.
//!
//! `/api/config` was the obvious existing home and is not one — it is a read on
//! this side and a 501 on the server, so there is no write path to borrow.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use tauri::AppHandle;
use tauri_plugin_store::StoreExt;

use crate::commands;

/// Key in the settings store.
const STORE_KEY: &str = "appearance";

/// The routes this module would use, once they exist.
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
            Loaded {
                appearance,
                source: "server".into(),
                shared: true,
                note: None,
            }
        }
        Err(why) => match local(&app) {
            Some(appearance) => Loaded {
                appearance,
                source: "local".into(),
                shared: false,
                note: Some(why),
            },
            None => Loaded {
                appearance: Appearance::default(),
                source: "default".into(),
                shared: false,
                note: Some(why),
            },
        },
    }
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
