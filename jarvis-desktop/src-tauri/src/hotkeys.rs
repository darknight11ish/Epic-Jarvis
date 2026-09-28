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
    /// The shipped binding, and what Reset returns to. Empty: OFF until the
    /// owner picks a key (the Jarvis Live key, the owner's decision of
    /// 2026-09-28) - Reset turns it off again.
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
    Action {
        id: "toggle_floating",
        label: "Show or hide the floating face",
        // Same family as the rest ("Windows has no Alt+Shift+letter of its
        // own", above) - F for "floating", and free: nothing else here
        // uses it.
        default: "Alt+Shift+F",
        hint: "The small always-on-top window with just Jarvis's face - no chat box. Off by default.",
    },
    Action {
        // talk_type.rs: the one action that also reads key-up (lib.rs).
        id: "talk_to_type",
        label: "Talk-to-type",
        // T for "type", in the same Alt+Shift family as the rest. Word, for
        // one, uses Alt+Shift+T to insert the time; rebind it if that
        // matters more.
        default: "Alt+Shift+T",
        hint: "Hold it and speak, then let go: Jarvis types what you said into the program in front. A quick tap keeps it listening until you press it again. Works once talk-to-type is on (Settings, Voice).",
    },
    Action {
        id: "toggle_live",
        label: "Start or end Jarvis Live",
        // OFF until the owner picks a key (the owner's decision of
        // 2026-09-28, the Jarvis Live extras). Alt+Shift+L is suggested in
        // the hint: the same family as the others, and nothing here uses L.
        default: "",
        hint: "Off until you pick a key - Alt+Shift+L is free for it. Starting is held while the connection is catching up or App lock would ask; ending never is.",
    },
];

/// The key the Live hotkey's hint suggests. Checked below to be free of every
/// other action's shipped key.
pub const LIVE_SUGGESTED: &str = "Alt+Shift+L";

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
///
/// When a build ships a NEW action whose default lands on a key the owner
/// already saved, by hand, for something else, that something else keeps the
/// key: this new, never-chosen action comes back empty (unbound) instead.
/// The owner made a real choice for the old action; nobody chose the new
/// default yet, so it is not the new action's place to fight for it. Without
/// this, `set_hotkeys` (which starts from this map) would see the same
/// collision on every save and refuse ALL of them - not just the one that
/// actually clashes - until the owner noticed and moved one by hand (bug
/// audit 2026-09-27, desktop-rust finding #7). A default never fights another
/// default, though: two untouched defaults landing on the same key is a build
/// mistake, and stays a loud `validate` error like any other duplicate.
pub fn configured(app: &AppHandle) -> BTreeMap<String, String> {
    let stored = app
        .store(commands::SETTINGS_STORE)
        .ok()
        .and_then(|store| store.get(STORE_KEY));

    let mut out = BTreeMap::new();
    let mut on_default: std::collections::BTreeSet<String> = std::collections::BTreeSet::new();
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
            _ => {
                on_default.insert(spec.id.to_string());
                spec.default.to_string()
            }
        };
        out.insert(spec.id.to_string(), accel);
    }

    resolve_default_clashes(&mut out, &on_default);
    out
}

/// Blanks a DEFAULTED id's entry when it collides with another id's own
/// explicitly-saved entry. Two ids that are both defaulted are left to
/// collide loudly if they do - that is a build mistake, not this to paper
/// over, and `validate` already reports it. Pulled out of [`configured`] so
/// the resolution itself can be tested without an `AppHandle`.
fn resolve_default_clashes(
    bindings: &mut BTreeMap<String, String>,
    on_default: &std::collections::BTreeSet<String>,
) {
    for id in on_default {
        let Some(Ok(shortcut)) = bindings.get(id).map(|a| parse(a)) else {
            continue;
        };
        let clash = bindings.iter().any(|(other_id, accel)| {
            other_id != id
                && !on_default.contains(other_id)
                && parse(accel).is_ok_and(|s| s == shortcut)
        });
        if clash {
            bindings.insert(id.clone(), String::new());
        }
    }
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
        // Blank means `configured` already left this one unbound because its
        // default lost to another action's own saved key (finding #7) - not
        // a real gap to reject. Nothing else in this build can produce a
        // blank entry: the recording UI only ever writes a real combination.
        if accel.is_empty() {
            continue;
        }
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

        // `configured` already left this one blank because its default lost
        // to another action's own saved key. Registering it anyway would
        // just be refused by the OS, and the notification in lib.rs would
        // wrongly blame "another application" for a fight Jarvis itself
        // caused (finding #7) - so this never reaches `manager.register`.
        // Off by default and the owner has not picked a key: nothing to
        // register, and nothing is wrong (no error to show).
        if accel.is_empty() && spec.default.is_empty() {
            out.push(Bound {
                id: spec.id.to_string(),
                label: spec.label.to_string(),
                hint: spec.hint.to_string(),
                accelerator: String::new(),
                default: String::new(),
                registered: false,
                error: None,
            });
            continue;
        }
        if accel.is_empty() {
            let holder = ACTIONS.iter().find(|other| {
                other.id != spec.id
                    && bindings
                        .get(other.id)
                        .and_then(|a| parse(a).ok())
                        .zip(parse(spec.default).ok())
                        .is_some_and(|(a, b)| a == b)
            });
            let reason = match holder {
                Some(other) => format!(
                    "`{}` is already {}'s own key. Give this one a different one in Settings.",
                    spec.default, other.label
                ),
                None => format!("`{}` is already used elsewhere.", spec.default),
            };
            out.push(Bound {
                id: spec.id.to_string(),
                label: spec.label.to_string(),
                hint: spec.hint.to_string(),
                accelerator: String::new(),
                default: spec.default.to_string(),
                registered: false,
                error: Some(reason),
            });
            continue;
        }

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
        // and nothing else in the build would notice. An empty default is an
        // action that is OFF until the owner picks a key (Jarvis Live).
        for spec in ACTIONS.iter().filter(|a| !a.default.is_empty()) {
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

    /// Bug audit 2026-09-27, finding #7: a build-shipped default must not
    /// fight a key the owner already saved for something else, and must
    /// not stop EVERY other save while it does.
    #[test]
    fn a_new_default_loses_to_an_old_saved_key() {
        let mut bindings: BTreeMap<String, String> = ACTIONS
            .iter()
            .map(|a| (a.id.to_string(), a.default.to_string()))
            .collect();
        // The owner long ago moved "Quick note" onto what is now
        // "toggle_floating"'s shipped default.
        bindings.insert("quick_note".into(), "Alt+Shift+F".into());
        let on_default: std::collections::BTreeSet<String> =
            ["toggle_floating".to_string()].into_iter().collect();

        resolve_default_clashes(&mut bindings, &on_default);

        assert_eq!(bindings["toggle_floating"], "");
        assert_eq!(bindings["quick_note"], "Alt+Shift+F");
        // The clash is gone, so the whole set - not just these two ids -
        // validates: every other action's own save is no longer refused.
        validate(&bindings).expect("a resolved clash must not block other saves");
    }

    #[test]
    fn two_untouched_defaults_still_collide_loudly() {
        // Neither side was ever chosen by the owner, so there is no "keep
        // the owner's real choice" case to apply - this is just a build
        // mistake, and it must still be reported, not silently resolved.
        let mut bindings: BTreeMap<String, String> = ACTIONS
            .iter()
            .map(|a| (a.id.to_string(), a.default.to_string()))
            .collect();
        bindings.insert("quick_note".into(), "Alt+Shift+F".into());
        let on_default: std::collections::BTreeSet<String> =
            ["toggle_floating".to_string(), "quick_note".to_string()]
                .into_iter()
                .collect();

        resolve_default_clashes(&mut bindings, &on_default);

        assert_eq!(bindings["toggle_floating"], "Alt+Shift+F");
        assert_eq!(bindings["quick_note"], "Alt+Shift+F");
        assert!(validate(&bindings).is_err());
    }

    #[test]
    fn validate_accepts_a_blank_entry_as_left_unbound_on_purpose() {
        let mut bindings: BTreeMap<String, String> = ACTIONS
            .iter()
            .map(|a| (a.id.to_string(), a.default.to_string()))
            .collect();
        bindings.insert("toggle_floating".into(), String::new());
        validate(&bindings).expect("a blank, resolved entry must not read as \"no keys\"");
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

    /// The owner's decision of 2026-09-28: a PC hotkey to start or end Jarvis
    /// Live, OFF until the owner picks one, Alt+Shift+L suggested.
    #[test]
    fn the_live_key_is_off_until_picked_and_its_suggestion_is_free() {
        let spec = action("toggle_live").expect("the Jarvis Live hotkey exists");
        assert_eq!(spec.default, "", "the Live key must ship OFF");
        assert!(spec.hint.contains(LIVE_SUGGESTED));
        let suggested = parse(LIVE_SUGGESTED).expect("the suggestion parses");
        for other in ACTIONS.iter().filter(|a| !a.default.is_empty()) {
            assert_ne!(
                parse(other.default).unwrap(),
                suggested,
                "the suggested Live key is {}'s shipped key",
                other.label
            );
        }
        // Off, it validates (nothing bound) - and a picked key validates too.
        let mut set: BTreeMap<String, String> = ACTIONS
            .iter()
            .map(|a| (a.id.to_string(), a.default.to_string()))
            .collect();
        validate(&set).expect("the Live key left off must not read as no keys");
        set.insert("toggle_live".into(), LIVE_SUGGESTED.into());
        validate(&set).expect("picking the suggested key is accepted");
        // Picking a key another action already has is refused, by name.
        set.insert("toggle_live".into(), "Alt+Shift+X".into());
        let err = validate(&set).expect_err("a clash with Stop everything was accepted");
        assert!(err.contains("Stop everything"), "{err}");
    }

    #[test]
    fn talk_to_type_ships_on_its_own_key() {
        let spec = action(crate::talk_type::ACTION_ID).expect("the talk-to-type hotkey exists");
        assert_eq!(spec.default, "Alt+Shift+T");
        let ours = parse(spec.default).expect("parses");
        for other in ACTIONS.iter().filter(|a| a.id != spec.id) {
            assert_ne!(
                ours,
                parse(other.default).unwrap(),
                "clashes with {}",
                other.id
            );
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
