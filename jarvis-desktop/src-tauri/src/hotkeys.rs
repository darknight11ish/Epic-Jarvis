//! The global accelerators, and where they are stored.
//!
//! These were five constants in `lib.rs`. That was fine until the first machine
//! this ran on refused `Alt+Space` — recent Windows 11 builds hand it to the
//! Copilot app, PowerToys Run claims it by default, and half a dozen launchers
//! compete for it. A refused binding was reported in a notification and then
//! nothing could be done about it, because the only way to change one was to
//! edit Rust and rebuild.
//!
//! ## Two rules the parser enforces
//!
//! **A global hotkey must carry a modifier.** `RegisterHotKey` will happily
//! take a bare `S`, and then every S typed anywhere on the machine goes to
//! Jarvis instead of to the document the person is writing. There is no undo
//! for that from inside the app, because the Settings window would not receive
//! its own keystrokes either. It is rejected before it can be saved.
//!
//! **No two actions may share a binding.** The plugin dispatches on the
//! shortcut that fired, so a duplicate would silently run whichever arm the
//! match hit first and the other action would look broken.
//!
//! ## Registration is reported, not assumed
//!
//! `register()` failing is the normal case on a busy machine, so every apply
//! returns a per-action verdict and the Settings window renders it. An
//! accelerator that saved but did not bind is the exact state the user needs to
//! see, and the old code could only say so in a toast at startup.

use std::collections::BTreeMap;
use std::str::FromStr;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut};
use tauri_plugin_store::StoreExt;

use crate::commands;

/// Key in the settings store.
const STORE_KEY: &str = "hotkeys";

/// One bindable action: what it is called, what it does, and what it was.
pub struct Action {
    /// Stable id. Persisted, so it must not change.
    pub id: &'static str,
    /// What the Settings window calls it.
    pub label: &'static str,
    /// The shipped binding, and what Reset returns to.
    pub default: &'static str,
    /// One line of why, shown under the label.
    pub hint: &'static str,
}

/// Every action that can be bound, in the order Settings lists them.
pub const ACTIONS: &[Action] = &[
    Action {
        id: "toggle_quickbar",
        label: "Show or hide the Jarvis bar",
        default: "Alt+Space",
        hint: "From anywhere, whatever program is in front.",
    },
    Action {
        id: "ingest_clipboard",
        label: "Attach the clipboard",
        default: "Super+Shift+J",
        hint: "Put whatever is on the clipboard into the bar as context.",
    },
    Action {
        id: "capture_screen",
        label: "Attach a screen capture",
        default: "Alt+Shift+S",
        // Worth keeping on screen: it is the first thing anyone tries to set
        // this to, and the failure is silent and confusing.
        hint: "Not Win+Shift+S — the Snipping Tool owns that at the shell level.",
    },
    Action {
        id: "quick_note",
        // Not "to Logseq": the quickbar arms Logseq only when this PC is set
        // up for it, and otherwise the first note app it is set up for
        // (main.js, "quick-note-summon").
        label: "Quick note",
        default: "Alt+Shift+N",
        hint: "Open the Jarvis bar ready to file a note - to Logseq, or else the first note app this PC is set up for.",
    },
    Action {
        id: "toggle_widget",
        label: "Show or hide the widget",
        default: "Alt+Shift+W",
        hint: "The desktop pane with the meters and the gates.",
    },
    Action {
        id: "stop_everything",
        label: "Stop everything",
        // With Jarvis's other Alt+Shift keys, and on no Windows shortcut:
        // Windows has no Alt+Shift+letter of its own, and the Escape
        // combinations are taken (Ctrl+Shift+Esc is Task Manager, Alt+Esc
        // switches windows). Word's "mark index entry" is the one program
        // shortcut it shadows. backend/README.md, "Stop everything".
        default: "Alt+Shift+X",
        hint: "Stops Jarvis talking and anything it is doing on the screen or the phone, at once. Asks nothing first; approves nothing.",
    },
];

fn action(id: &str) -> Option<&'static Action> {
    ACTIONS.iter().find(|a| a.id == id)
}

/// What happened when one binding was offered to the OS.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Bound {
    pub id: String,
    pub label: String,
    pub hint: String,
    pub accelerator: String,
    pub default: String,
    /// True when the OS accepted it. False means another application owns it.
    pub registered: bool,
    /// Why not, in the OS's words, when it did not bind.
    pub error: Option<String>,
}

/// The live bindings, and the verdict on each from the last apply.
#[derive(Default)]
pub struct HotkeyState(std::sync::Mutex<Vec<Bound>>);

impl HotkeyState {
    pub fn snapshot(&self) -> Vec<Bound> {
        self.0
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .clone()
    }

    fn replace(&self, next: Vec<Bound>) {
        *self
            .0
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner()) = next;
    }
}

/// Parses an accelerator, refusing the two shapes that cannot be undone.
///
/// The modifier rule is the important one. Everything else here is the
/// plugin's own parser; this only adds the constraint it does not have.
pub fn parse(accelerator: &str) -> Result<Shortcut, String> {
    let text = accelerator.trim();
    if text.is_empty() {
        return Err("no keys".to_string());
    }
    let shortcut = Shortcut::from_str(text)
        .map_err(|_| format!("`{text}` is not a combination this build understands"))?;
    if shortcut.mods.is_empty() {
        return Err(format!(
            "`{text}` has no modifier. A global hotkey without one swallows that \
             key everywhere on the machine, including in the box you would use \
             to change it back."
        ));
    }
    Ok(shortcut)
}

/// The bindings as configured: the store's values where present, defaults
/// where not, and defaults again for anything the store holds that no longer
/// parses.
pub fn configured(app: &AppHandle) -> BTreeMap<String, String> {
    let stored = app
        .store(commands::SETTINGS_STORE)
        .ok()
        .and_then(|store| store.get(STORE_KEY));

    let mut out = BTreeMap::new();
    for spec in ACTIONS {
        let saved = stored
            .as_ref()
            .and_then(|v| v.get(spec.id))
            .and_then(|v| v.as_str())
            .map(str::to_owned);
        // A saved value that no longer parses falls back rather than leaving
        // the action unbindable — a build that drops a key name should not
        // strand someone with a dead shortcut and no way to see why.
        let accel = match saved {
            Some(text) if parse(&text).is_ok() => text,
            _ => spec.default.to_string(),
        };
        out.insert(spec.id.to_string(), accel);
    }
    out
}

/// Writes the bindings, having already checked they are sane.
fn persist(app: &AppHandle, bindings: &BTreeMap<String, String>) -> Result<(), String> {
    let store = app
        .store(commands::SETTINGS_STORE)
        .map_err(|e| format!("settings store unavailable: {e}"))?;
    store.set(
        STORE_KEY,
        serde_json::to_value(bindings).map_err(|e| e.to_string())?,
    );
    store
        .save()
        .map_err(|e| format!("could not write the settings store: {e}"))
}

/// Rejects a set that cannot be bound, before anything is written or
/// unregistered.
///
/// Validating the whole set first matters: `apply` starts by dropping every
/// existing binding, so a failure discovered halfway through would leave the
/// user with fewer working hotkeys than they had.
fn validate(bindings: &BTreeMap<String, String>) -> Result<(), String> {
    let mut seen: BTreeMap<String, &str> = BTreeMap::new();
    for (id, accel) in bindings {
        parse(accel)
            .map_err(|e| format!("{}: {e}", action(id).map_or(id.as_str(), |a| a.label)))?;
        // Compare the parsed form, so `Alt+Space` and `alt+space` collide as
        // they will in the OS rather than passing as two different strings.
        let key = format!("{:?}", parse(accel).unwrap());
        if let Some(other) = seen.insert(key, id) {
            let (a, b) = (
                action(other).map_or(other, |a| a.label),
                action(id).map_or(id.as_str(), |a| a.label),
            );
            return Err(format!(
                "`{accel}` is on both {a} and {b}. One combination cannot run two actions."
            ));
        }
    }
    Ok(())
}

/// Drops every binding and puts the configured set back, recording the verdict
/// on each.
///
/// Returns the verdicts rather than an error: a refused accelerator is a normal
/// outcome on a machine with a launcher installed, and the caller's job is to
/// show which ones took rather than to fail.
pub fn apply(app: &AppHandle) -> Vec<Bound> {
    let bindings = configured(app);
    let manager = app.global_shortcut();
    // Unregister everything first. Re-registering an accelerator that is
    // already held by this process is itself an error, so a partial update
    // would report a conflict against ourselves.
    let _ = manager.unregister_all();

    let mut out = Vec::with_capacity(ACTIONS.len());
    for spec in ACTIONS {
        let accel = bindings
            .get(spec.id)
            .cloned()
            .unwrap_or_else(|| spec.default.to_string());
        let (registered, error) = match parse(&accel) {
            Ok(shortcut) => match manager.register(shortcut) {
                Ok(()) => {
                    println!("[jarvis] hotkey {} = {accel} registered", spec.id);
                    (true, None)
                }
                Err(err) => {
                    eprintln!("[jarvis] hotkey {} = {accel} refused: {err}", spec.id);
                    (false, Some(err.to_string()))
                }
            },
            Err(err) => (false, Some(err)),
        };
        out.push(Bound {
            id: spec.id.to_string(),
            label: spec.label.to_string(),
            hint: spec.hint.to_string(),
            accelerator: accel,
            default: spec.default.to_string(),
            registered,
            error,
        });
    }

    app.state::<HotkeyState>().replace(out.clone());
    out
}

/// Which action a fired shortcut belongs to, or `None` if it is not ours.
///
/// Resolved against the LIVE bindings rather than a startup snapshot, which is
/// the whole reason this is a lookup and not five comparisons against captured
/// values: those would keep firing the old actions after a rebind.
pub fn action_for(app: &AppHandle, fired: &Shortcut) -> Option<&'static str> {
    for bound in app.state::<HotkeyState>().snapshot() {
        if parse(&bound.accelerator).is_ok_and(|s| &s == fired) {
            return action(&bound.id).map(|a| a.id);
        }
    }
    None
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

/// The bindings and their current verdicts, for the Settings window.
#[tauri::command]
pub fn get_hotkeys(app: AppHandle) -> Vec<Bound> {
    let live = app.state::<HotkeyState>().snapshot();
    if live.is_empty() {
        // Nothing has been applied yet: describe the configuration without
        // claiming anything about whether it bound.
        return configured(&app)
            .into_iter()
            .filter_map(|(id, accelerator)| {
                action(&id).map(|spec| Bound {
                    id,
                    label: spec.label.to_string(),
                    hint: spec.hint.to_string(),
                    accelerator,
                    default: spec.default.to_string(),
                    registered: false,
                    error: Some("not applied yet".to_string()),
                })
            })
            .collect();
    }
    live
}

/// Saves a new set and re-registers immediately.
///
/// Validation happens before anything is written OR unregistered, so a rejected
/// set leaves the machine exactly as it was.
#[tauri::command]
pub fn set_hotkeys(
    app: AppHandle,
    bindings: BTreeMap<String, String>,
) -> Result<Vec<Bound>, String> {
    // Ignore ids this build does not have, and fill in any it was not sent, so
    // an older Settings page cannot silently drop an action.
    let mut next = configured(&app);
    for (id, accel) in bindings {
        if action(&id).is_some() {
            next.insert(id, accel.trim().to_string());
        }
    }
    validate(&next)?;
    persist(&app, &next)?;
    Ok(apply(&app))
}

/// Puts every binding back to what the app shipped with.
#[tauri::command]
pub fn reset_hotkeys(app: AppHandle) -> Result<Vec<Bound>, String> {
    let defaults: BTreeMap<String, String> = ACTIONS
        .iter()
        .map(|a| (a.id.to_string(), a.default.to_string()))
        .collect();
    persist(&app, &defaults)?;
    Ok(apply(&app))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_modifier_is_required() {
        // The rule that cannot be walked back from inside the app: a bare key
        // as a global hotkey swallows that key everywhere, including in the
        // field you would use to change it.
        assert!(parse("S").is_err());
        assert!(parse("F5").is_err());
        assert!(parse("Space").is_err());
        assert!(parse("Alt+Space").is_ok());
        assert!(parse("Super+Shift+J").is_ok());
    }

    #[test]
    fn nonsense_is_refused_without_panicking() {
        assert!(parse("").is_err());
        assert!(parse("   ").is_err());
        assert!(parse("Alt+").is_err());
        assert!(parse("Ctrl+Banana").is_err());
    }

    #[test]
    fn every_shipped_default_parses_and_carries_a_modifier() {
        // A default that does not parse would be unbindable on a fresh install
        // and nothing else in the build would notice.
        for spec in ACTIONS {
            parse(spec.default)
                .unwrap_or_else(|e| panic!("default for {} does not parse: {e}", spec.id));
        }
    }

    #[test]
    fn the_defaults_do_not_collide() {
        let defaults: BTreeMap<String, String> = ACTIONS
            .iter()
            .map(|a| (a.id.to_string(), a.default.to_string()))
            .collect();
        validate(&defaults).expect("the shipped defaults conflict with each other");
    }

    #[test]
    fn a_duplicate_is_named_rather_than_silently_taken() {
        let mut set: BTreeMap<String, String> = ACTIONS
            .iter()
            .map(|a| (a.id.to_string(), a.default.to_string()))
            .collect();
        set.insert("quick_note".into(), "Alt+Space".into());
        let err = validate(&set).expect_err("two actions on one combination were accepted");
        assert!(err.contains("Show or hide the Jarvis bar"), "{err}");
        assert!(err.contains("Quick note"), "{err}");
    }

    #[test]
    fn case_does_not_hide_a_duplicate() {
        // The OS compares the parsed combination, not the string, so these
        // collide there. Catching it here is the difference between a clear
        // message and one action silently never firing.
        let mut set: BTreeMap<String, String> = ACTIONS
            .iter()
            .map(|a| (a.id.to_string(), a.default.to_string()))
            .collect();
        set.insert("quick_note".into(), "alt+space".into());
        assert!(validate(&set).is_err());
    }

    #[test]
    fn stop_everything_ships_on_a_key_of_its_own() {
        let spec = action("stop_everything").expect("the Stop everything hotkey exists");
        assert_eq!(spec.default, "Alt+Shift+X");
        let ours = parse(spec.default).expect("parses");
        // Windows' own combinations: a stop key that opened Task Manager or
        // switched windows instead would fail at the one moment it matters.
        for reserved in [
            "Ctrl+Shift+Escape",
            "Alt+Escape",
            "Alt+Tab",
            "Alt+Shift+Tab",
            "Alt+F4",
            "Super+L",
            "Super+D",
        ] {
            if let Ok(theirs) = Shortcut::from_str(reserved) {
                assert_ne!(ours, theirs, "Stop everything collides with {reserved}");
            }
        }
    }

    #[test]
    fn ids_are_unique_and_stable_looking() {
        // They are persisted, so a duplicate id would make one action
        // permanently unsettable.
        let mut seen = std::collections::BTreeSet::new();
        for spec in ACTIONS {
            assert!(seen.insert(spec.id), "duplicate action id {}", spec.id);
            assert!(!spec.label.is_empty());
            assert!(!spec.hint.is_empty());
        }
    }
}
