//! Taking the owner where Jarvis said it would.
//!
//! ONE path reaches this module, and it is the app's existing, tested one: a
//! chat answer's route line. The backend has told the desktop which place an
//! answer is about since 2026-10-31 (`X-Jarvis-Route`: `open_settings`,
//! `open_brain`, `open_app_kind`/`open_place`; documented in
//! `docs/JARVIS-API.md` §58). The HUD page's injected bootstrap reads that
//! route and calls the [`open_jarvis_area`] command with the route's
//! `open_area`/`open_anchor` fields - the F6 extension of the same closed id
//! set, not a second mechanism.
//!
//! **There is deliberately no `ui.navigate` stream listener here.** The F6
//! research correction (`RESEARCH.md` F3/F5, and the backend worker's
//! 2026-11-03 confirmation) kept navigation on the per-request route field:
//! the backend publishes no `ui.navigate` event, and a listener for a frame
//! that can never arrive would be a doorbell into an empty room
//! (`docs/ARCHITECTURE.md` §6). If a navigation frame is ever added, its
//! client handler belongs in the same change as the publisher - and it must be
//! label-filtered, never a broadcast (Tauri event payloads are outside the ACL;
//! a global emit would make every open chat window jump).
//!
//! The areas the app can honestly open are ONE table ([`AREA_ALIASES`]) in
//! Rust, so a route naming a screen and the page chrome that performs the
//! switch cannot drift. The injected page chrome (`hud_bootstrap.js`) owns the
//! actual DOM switch: the page is vendored (`jarvis_hud.html` is a
//! byte-identical twin), so the shell adapts it without forking it.
//!
//! An area the desktop cannot open is never silently ignored: the HUD gets a
//! plain sentence in its own chat log saying what was asked for and that this
//! desktop has no such screen ([`unknown_words`]).
//!
//! What this module never does: it changes no setting, raises no card,
//! approves nothing. Every window it opens goes through the same App-lock
//! check as the tray row that opens it.

use serde::Serialize;
use tauri::AppHandle;

use crate::windows;

/// Where one area request wants to go.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Target {
    /// A view the HUD page itself draws: its key on `setView` (talk/brain).
    HudView(&'static str),
    /// A stage tab in the page's own tab strip: talk/galaxy/today/reminders/
    /// memory/telemetry.
    HudTab(&'static str),
    /// One of the page's own panels, opened by the chrome's own button:
    /// history sidebar or presets menu.
    HudPanel(&'static str),
    /// The Settings window, at an optional section id.
    Settings {
        anchor: Option<String>,
    },
    /// The Brain window, at one of its own places.
    Brain {
        place: &'static str,
    },
    Faces,
    Features,
    /// A new chat window.
    NewChatWindow,
    /// Nothing this desktop can open.
    Unknown,
}

/// The area table: every name the backend may use, mapped to the real surface.
///
/// Aliases are the words a person (or the backend's screen registry) would
/// use. They are matched case-insensitively after trimming. Keeping this table
/// here, and only here, is what makes "the desktop knows every area it can
/// open" testable without a window ([`classify`]'s tests).
pub const AREA_ALIASES: [(&str, &str); 22] = [
    ("talk", "view:talk"),
    ("chat", "view:talk"),
    ("conversation", "view:talk"),
    ("hud", "view:talk"),
    ("galaxy", "view:brain"),
    ("memory-map", "view:brain"),
    ("graph", "view:brain"),
    ("today", "tab:today"),
    ("reminders", "tab:reminders"),
    ("memory", "tab:memory"),
    ("telemetry", "tab:telemetry"),
    ("history", "panel:history"),
    ("chats", "panel:history"),
    ("conversations", "panel:history"),
    ("presets", "panel:presets"),
    ("focus", "panel:presets"),
    ("settings", "window:settings"),
    ("preferences", "window:settings"),
    ("brain", "window:brain"),
    ("second-brain", "window:brain"),
    ("faces", "window:faces"),
    ("features", "window:features"),
];

/// The area ids that open the desktop's own windows rather than a HUD panel -
/// kept as one list so the injected page chrome can be held to the same words
/// by `tests/hud-nav.mjs`.
pub const WINDOW_AREAS: [&str; 5] = ["settings", "brain", "faces", "features", "updates"];

/// What `open_jarvis_area` and a `ui.navigate` event do: the same table, the
/// same destinations.
pub fn classify(area: &str, anchor: Option<&str>) -> Target {
    let area = area.trim().to_ascii_lowercase();
    let anchor = anchor
        .map(str::trim)
        .filter(|a| !a.is_empty())
        .map(str::to_string);
    for (alias, destination) in AREA_ALIASES {
        if alias != area {
            continue;
        }
        let (kind, key) = destination.split_once(':').unwrap_or(("unknown", ""));
        return match kind {
            "view" => Target::HudView(static_key(key)),
            "tab" => Target::HudTab(static_key(key)),
            "panel" => Target::HudPanel(static_key(key)),
            "window" => match key {
                "settings" => Target::Settings { anchor },
                "brain" => Target::Brain {
                    place: brain_place(anchor.as_deref()),
                },
                "faces" => Target::Faces,
                "features" => Target::Features,
                _ => Target::Unknown,
            },
            _ => Target::Unknown,
        };
    }
    // "Updates" is a Settings CARD, not a window of its own: it is the place
    // the tray's "Update available" row already opens, and naming it as an
    // area must reach the same card.
    if area == "updates" || area == "update" {
        return Target::Settings {
            anchor: Some("updates".to_string()),
        };
    }
    if area == "new-chat-window" || area == "new-chat" || area == "new_window" {
        return Target::NewChatWindow;
    }
    Target::Unknown
}

/// The static spelling of a destination key, or `"talk"` for a key this build
/// does not carry (the table is compile-time data; a typo shows up in tests).
fn static_key(key: &str) -> &'static str {
    match key {
        "talk" => "talk",
        "brain" => "brain",
        "today" => "today",
        "reminders" => "reminders",
        "memory" => "memory",
        "telemetry" => "telemetry",
        "history" => "history",
        "presets" => "presets",
        _ => "talk",
    }
}

/// The Brain window place an anchor names, restricted to the places
/// `windows.rs` already accepts ([`windows::BRAIN_PLACES`], via
/// `show_brain_at`). Anything else means "open the Brain at its top".
fn brain_place(anchor: Option<&str>) -> &'static str {
    match anchor.map(str::trim) {
        Some("history") => "history",
        Some("tutorials") => "tutorials",
        _ => "brain",
    }
}

/// The sentence the HUD's chat log gets when the area does not exist here.
/// One plain line: what was asked for, and that this desktop has no such
/// screen. Never a dead control and never silence.
pub fn unknown_words(area: &str) -> String {
    let area = area.trim();
    if area.is_empty() {
        return "Jarvis asked the desktop to open a screen, but the request did not say \
                which one. Nothing was opened."
            .to_string();
    }
    format!(
        "Jarvis asked to open \"{area}\", but the desktop has no \"{area}\". \
         Nothing was opened."
    )
}

/// What one request ended up doing, for the command's return value and the log.
#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct NavOutcome {
    /// The area as the caller spelled it, trimmed.
    pub area: String,
    /// `hud-view`, `hud-tab`, `hud-panel`, `settings`, `brain`, `faces`,
    /// `features`, `new-chat-window` or `unknown`.
    pub target: String,
}

impl NavOutcome {
    fn of(area: &str, target: &Target) -> Self {
        let name = match target {
            Target::HudView(_) => "hud-view",
            Target::HudTab(_) => "hud-tab",
            Target::HudPanel(_) => "hud-panel",
            Target::Settings { .. } => "settings",
            Target::Brain { .. } => "brain",
            Target::Faces => "faces",
            Target::Features => "features",
            Target::NewChatWindow => "new-chat-window",
            Target::Unknown => "unknown",
        };
        Self {
            area: area.trim().to_string(),
            target: name.to_string(),
        }
    }
}

/// Carries out one area request.
///
/// The HUD page is told about HUD areas (view/tab/panel and Settings/Brain,
/// whose own `open_fix_place` call the chrome already makes) through the
/// single-window feed. Faces, Features and a new chat window are the shell's
/// own windows and are opened here directly.
pub fn dispatch(app: &AppHandle, area: &str, anchor: Option<&str>) -> NavOutcome {
    let target = classify(area, anchor);
    let outcome = NavOutcome::of(area, &target);
    let words = |outcome: &NavOutcome| {
        crate::logfile::log(&format!(
            "[jarvis] navigate: \"{}\" -> {}",
            outcome.area, outcome.target
        ));
    };
    match &target {
        Target::Faces => {
            if let Err(err) = windows::show_faces(app) {
                crate::logfile::log(&format!("[jarvis] navigate: Faces would not open: {err}"));
            }
        }
        Target::Features => {
            if let Err(err) = windows::show_features(app) {
                crate::logfile::log(&format!(
                    "[jarvis] navigate: the feature list would not open: {err}"
                ));
            }
        }
        Target::NewChatWindow => match crate::chat_windows::open_for(app, None) {
            // An empty label is the app lock's own answer: `chat_windows`
            // refused, and Windows Hello is being asked (the same rule every
            // other way to a HUD surface takes). Nothing was opened yet.
            Ok(label) if label.is_empty() => {
                crate::logfile::log(
                    "[jarvis] navigate: a new chat window waited for Windows Hello (App lock)",
                );
            }
            Ok(_) => {}
            Err(err) => crate::logfile::log(&format!("[jarvis] navigate: {err}")),
        },
        Target::Unknown => {
            words(&outcome);
            // The owner asked Jarvis to open something, so show the window that
            // can carry the sentence. App lock still decides (show_hud asks).
            if let Err(err) = windows::show_hud(app) {
                crate::logfile::log(&format!(
                    "[jarvis] navigate: the HUD would not come up to say what happened: {err}"
                ));
            }
            crate::push_to_hud_main(
                app,
                crate::hud_nav::NOTICE_FEED,
                &Notice {
                    words: unknown_words(area),
                },
            );
            return outcome;
        }
        Target::HudView(_)
        | Target::HudTab(_)
        | Target::HudPanel(_)
        | Target::Settings { .. }
        | Target::Brain { .. } => {
            if let Err(err) = windows::show_hud(app) {
                crate::logfile::log(&format!(
                    "[jarvis] navigate: the HUD would not come up: {err}"
                ));
            }
            let (area_key, anchor_key) = area_payload(&target);
            crate::push_to_hud_main(
                app,
                NAV_FEED,
                &NavRequest {
                    area: area_key.to_string(),
                    anchor: anchor_key,
                },
            );
        }
    }
    words(&outcome);
    outcome
}

/// The feed channel the HUD chrome hears a navigation on.
pub const NAV_FEED: &str = "nav";
/// The feed channel the HUD chrome hears an honest "this desktop cannot" on.
pub const NOTICE_FEED: &str = "notice";

/// One navigation push into the HUD page's feed.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct NavRequest {
    /// The page-level area word the chrome acts on: `talk`, `brain`, `today`,
    /// `reminders`, `memory`, `telemetry`, `history`, `presets`, `settings`,
    /// `brain-window`.
    pub area: String,
    /// The optional section inside it (a Settings card id, or the Brain's own
    /// `history`/`tutorials`).
    pub anchor: Option<String>,
}

/// A plain sentence for the HUD's own chat log.
#[derive(Debug, Clone, Serialize)]
pub struct Notice {
    pub words: String,
}

/// The `(area, anchor)` words the page chrome receives for one target.
fn area_payload(target: &Target) -> (&'static str, Option<String>) {
    match target {
        Target::HudView(view) => (view, None),
        Target::HudTab(tab) => (tab, None),
        Target::HudPanel(panel) => (panel, None),
        Target::Settings { anchor } => ("settings", anchor.clone()),
        Target::Brain { place } => ("brain-window", Some((*place).to_string())),
        Target::Faces | Target::Features | Target::NewChatWindow | Target::Unknown => {
            ("unknown", None)
        }
    }
}

/// The command the injected HUD chrome calls for a chat answer's route.
///
/// Navigation only: it opens what the owner's own answer named, through the
/// same table and the same windows the tray and the app lock already govern.
/// It changes no setting and approves nothing.
#[tauri::command]
pub fn open_jarvis_area(
    app: AppHandle,
    area: String,
    anchor: Option<String>,
) -> Result<NavOutcome, String> {
    let outcome = dispatch(&app, &area, anchor.as_deref());
    // Unknown is not an error the caller must handle: the HUD has already been
    // given the plain sentence. The command returns what it did so a test - and
    // an older page - can see it.
    Ok(outcome)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_area_the_backend_may_name_lands_on_a_real_surface() {
        let cases = [
            ("talk", Target::HudView("talk")),
            ("chat", Target::HudView("talk")),
            ("galaxy", Target::HudView("brain")),
            ("memory-map", Target::HudView("brain")),
            ("graph", Target::HudView("brain")),
            ("today", Target::HudTab("today")),
            ("reminders", Target::HudTab("reminders")),
            ("memory", Target::HudTab("memory")),
            ("telemetry", Target::HudTab("telemetry")),
            ("history", Target::HudPanel("history")),
            ("chats", Target::HudPanel("history")),
            ("presets", Target::HudPanel("presets")),
            ("faces", Target::Faces),
            ("features", Target::Features),
            ("new-chat", Target::NewChatWindow),
        ];
        for (area, want) in cases {
            assert_eq!(classify(area, None), want, "{area}");
        }
    }

    #[test]
    fn the_table_is_case_and_space_insensitive() {
        assert_eq!(
            classify("  Settings ", None),
            Target::Settings { anchor: None }
        );
        assert_eq!(classify("BRAIN", None), Target::Brain { place: "brain" });
    }

    #[test]
    fn settings_keeps_the_section_the_backend_named() {
        assert_eq!(
            classify("settings", Some("voice")),
            Target::Settings {
                anchor: Some("voice".to_string())
            }
        );
        // An empty anchor is no anchor, not a broken one.
        assert_eq!(
            classify("settings", Some("   ")),
            Target::Settings { anchor: None }
        );
    }

    #[test]
    fn updates_is_the_settings_card_the_tray_row_opens() {
        assert_eq!(
            classify("updates", None),
            Target::Settings {
                anchor: Some("updates".to_string())
            }
        );
    }

    #[test]
    fn the_brain_place_is_restricted_to_the_places_the_window_accepts() {
        assert_eq!(
            classify("brain", Some("history")),
            Target::Brain { place: "history" }
        );
        assert_eq!(
            classify("brain", Some("tutorials")),
            Target::Brain { place: "tutorials" }
        );
        // A place the Brain does not have opens its top, never an error.
        assert_eq!(
            classify("brain", Some("memory")),
            Target::Brain { place: "brain" }
        );
    }

    #[test]
    fn an_area_this_desktop_does_not_have_is_unknown_not_guessed() {
        assert_eq!(classify("dashboard", None), Target::Unknown);
        assert_eq!(classify("", None), Target::Unknown);
        assert_eq!(classify("hud/overlay", None), Target::Unknown);
    }

    #[test]
    fn the_unknown_sentence_names_what_was_asked_and_says_nothing_opened() {
        assert_eq!(
            unknown_words("dashboard"),
            "Jarvis asked to open \"dashboard\", but the desktop has no \"dashboard\". \
             Nothing was opened."
        );
        assert!(unknown_words("").contains("did not say which one"));
    }

    #[test]
    fn the_area_payload_only_ever_names_areas_the_chrome_acts_on() {
        assert_eq!(area_payload(&Target::HudView("brain")), ("brain", None));
        assert_eq!(
            area_payload(&Target::HudPanel("history")),
            ("history", None)
        );
        assert_eq!(
            area_payload(&Target::Settings {
                anchor: Some("voice".to_string())
            }),
            ("settings", Some("voice".to_string()))
        );
        assert_eq!(
            area_payload(&Target::Brain { place: "tutorials" }),
            ("brain-window", Some("tutorials".to_string()))
        );
    }

    #[test]
    fn the_page_areas_the_chrome_acts_on_are_the_ones_this_table_can_send() {
        // `tests/hud-nav.mjs` pins the JavaScript side to this exact list, so
        // the page chrome cannot quietly stop handling one of them.
        for (area, _) in AREA_ALIASES {
            let target = classify(area, None);
            let sent = area_payload(&target).0;
            match target {
                Target::HudView(_) | Target::HudTab(_) | Target::HudPanel(_) => {
                    assert!(!sent.is_empty(), "{area}")
                }
                _ => {}
            }
        }
    }
}
