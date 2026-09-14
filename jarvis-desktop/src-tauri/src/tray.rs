//! The Windows notification-area icon: what Jarvis is doing, without a window.
//!
//! DESKTOP-BUILD build-order step 2. The icon is drawn here rather than loaded
//! from a file because its colour is state, and the state comes off the event
//! stream:
//!
//! ```text
//! Jarvis — thinking                      (status, disabled)
//! Power: quiet · set by hand             (status, disabled)
//! Active · Quiet · Standby — no route    (status, disabled — see below)
//! 2 approvals waiting                    (opens the queue)
//! ─────────────────────────────
//! Show HUD Window
//! Toggle Spotlight              Alt+Space
//! Toggle Widget                 Alt+Shift+W
//! ─────────────────────────────
//! Reconnect event stream
//! Status Check
//! ─────────────────────────────
//! Quit
//! ```
//!
//! ## The power switch that is not here
//!
//! §6 asks for "a Quiet/Standby/Active switch" in the minimum menu. There is no
//! route to build it on. `jarvis_hud.py`'s `do_POST` serves `/api/shutdown`,
//! `/api/models/{install,switch,rollback}`, `/api/skills/decide`,
//! `/api/memory/decide`, `/api/approve`, `/api/deny` and `/api/chat` — and
//! nothing else. `jarvis_power` has `set_mode`, but the HTTP server does not
//! expose it, and `GET /api/version` reports the mode read-only inside
//! `capabilities.power`. Rather than invent an endpoint and ship a menu item
//! that 404s, the switch appears as a disabled row that says why. It becomes
//! three live items the day the server grows the route.
//!
//! ## Colour
//!
//! Every colour in this file comes out of [`crate::spec::resolve`], reading the
//! same `jarvis-visual-spec.json` the faces read. §6: "Resolve the colour, do
//! not choose it… A tray with constants in it is wrong the moment the user
//! changes anything." There is not one hex literal below.

use std::sync::Mutex;

use tauri::{
    image::Image,
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager,
};

use crate::spec::{self, Binding, Rgb};
use crate::stream::LinkState;
use crate::{commands, events, windows};

/// Identifier the tray icon is registered under, so it can be looked up later
/// with `AppHandle::tray_by_id`.
pub const TRAY_ID: &str = "jarvis-tray";

/// Icon edge, in pixels. Windows asks for 16×16 at 100% scaling and 32×32 at
/// 200%; drawing at 32 and letting the shell downscale is sharper than drawing
/// at 16 and letting it upscale.
const ICON_SIZE: u32 = 32;

/// How often an animated pattern is re-resolved.
///
/// §6 sanctions exactly this: "A pattern that animates (breathe, pulse,
/// rainbow) does not need to animate in the tray — resolve it at a low rate, or
/// take the pattern's base colour. A tray icon redrawing at 60fps is a real
/// battery cost." Taking the base colour is the cheaper option but it is wrong
/// for `rainbow`, whose t=0 is pure red — "thinking" would show as an error
/// colour. So: a low rate, and the redraw is skipped entirely unless the
/// resolved 8-bit colour actually changed, which for `breathe` is most ticks.
const ANIMATION_TICK: std::time::Duration = std::time::Duration::from_millis(500);

// Menu item ids. Kept as constants so the builder and the click handler cannot
// drift apart.
const ID_STATUS_ACTIVITY: &str = "status-activity";
const ID_STATUS_POWER: &str = "status-power";
const ID_STATUS_POWER_SWITCH: &str = "status-power-switch";
const ID_APPROVALS: &str = "approvals";
const ID_BACKEND: &str = "backend";
const ID_SHOW_HUD: &str = "show-hud";
const ID_TOGGLE_SPOTLIGHT: &str = "toggle-spotlight";
const ID_TOGGLE_WIDGET: &str = "toggle-widget";
const ID_RECONNECT: &str = "reconnect";
const ID_SETTINGS: &str = "settings";
const ID_STATUS_CHECK: &str = "status-check";
const ID_QUIT: &str = "quit";

/// Handles to the menu rows whose text is state, so they can be re-labelled in
/// place. Rebuilding the whole menu on every event would close it under the
/// user's cursor.
#[derive(Default)]
pub struct TrayHandles {
    inner: Mutex<Option<Rows>>,
}

struct Rows {
    activity: MenuItem<tauri::Wry>,
    power: MenuItem<tauri::Wry>,
    approvals: MenuItem<tauri::Wry>,
    backend: MenuItem<tauri::Wry>,
}

/// The colour last pushed to the shell, so an unchanged frame costs nothing.
#[derive(Default)]
struct Painted(Mutex<Option<Rgb>>);

/// Builds the tray icon, its menu and the event handlers.
pub fn create_tray(app: &AppHandle) -> tauri::Result<()> {
    let link = app.state::<crate::stream::StreamState>().link();

    let activity = MenuItem::with_id(
        app,
        ID_STATUS_ACTIVITY,
        activity_label(&link),
        false,
        None::<&str>,
    )?;
    let power = MenuItem::with_id(
        app,
        ID_STATUS_POWER,
        power_label(&link),
        false,
        None::<&str>,
    )?;
    // Disabled on purpose, and worded so the reason is on screen rather than in
    // a commit message. See the module docs.
    let power_switch = MenuItem::with_id(
        app,
        ID_STATUS_POWER_SWITCH,
        "Active · Quiet · Standby — the server exposes no route yet",
        false,
        None::<&str>,
    )?;
    let approvals = MenuItem::with_id(
        app,
        ID_APPROVALS,
        approvals_label(&link),
        link.approvals > 0,
        None::<&str>,
    )?;

    // One row that is status and action at once: it says what the backend is
    // and, when there is something to do about it, does it.
    let backend_state = backend_row(app);
    let backend = MenuItem::with_id(
        app,
        ID_BACKEND,
        backend_state.0,
        backend_state.1,
        None::<&str>,
    )?;

    let show_hud = MenuItem::with_id(app, ID_SHOW_HUD, "Show HUD Window", true, None::<&str>)?;
    let toggle_spotlight = MenuItem::with_id(
        app,
        ID_TOGGLE_SPOTLIGHT,
        "Toggle Spotlight",
        true,
        Some("Alt+Space"),
    )?;
    let toggle_widget = MenuItem::with_id(
        app,
        ID_TOGGLE_WIDGET,
        "Toggle Widget",
        true,
        Some("Alt+Shift+W"),
    )?;
    let reconnect = MenuItem::with_id(
        app,
        ID_RECONNECT,
        "Reconnect event stream",
        true,
        None::<&str>,
    )?;
    let settings = MenuItem::with_id(app, ID_SETTINGS, "Settings…", true, None::<&str>)?;
    let status_check = MenuItem::with_id(app, ID_STATUS_CHECK, "Status Check", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, ID_QUIT, "Quit", true, None::<&str>)?;

    let menu = Menu::with_items(
        app,
        &[
            &activity,
            &power,
            &power_switch,
            &approvals,
            &backend,
            &PredefinedMenuItem::separator(app)?,
            &show_hud,
            &toggle_spotlight,
            &toggle_widget,
            &PredefinedMenuItem::separator(app)?,
            &settings,
            &reconnect,
            &status_check,
            &PredefinedMenuItem::separator(app)?,
            &quit,
        ],
    )?;

    app.state::<TrayHandles>()
        .inner
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .replace(Rows {
            activity,
            power,
            approvals,
            backend,
        });

    // Private to this module, so it is registered here rather than in `run`.
    app.manage(Painted::default());

    let mut builder = TrayIconBuilder::with_id(TRAY_ID)
        .tooltip(tooltip(&link))
        .menu(&menu)
        // Left click summons the spotlight; the menu belongs on right click.
        //
        // Linux caveat, documented as §6 asks: tray *icon* click events are not
        // emitted there at all. The icon shows and right-click still opens the
        // menu, so every action above is in the menu and this handler is a
        // bonus that simply does not exist on Linux.
        .show_menu_on_left_click(false)
        .on_menu_event(handle_menu_event)
        .on_tray_icon_event(handle_tray_icon_event);

    if let Some(icon) = render_icon(&link) {
        builder = builder.icon(icon);
    } else if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }

    builder.build(app)?;
    spawn_animation(app.clone());
    Ok(())
}

// ---------------------------------------------------------------------------
// State → the one spec state the icon resolves against
// ---------------------------------------------------------------------------

/// Maps what the stream reports onto one of the spec's seven states.
///
/// Two vocabularies meet here and they are not the same size, which is the only
/// judgement call in this file — so both mismatches are named rather than
/// papered over:
///
/// * **`working` has no binding.** `jarvis_events.ACTIVITY` is `idle,
///   listening, thinking, speaking, working, error`; the spec's states are
///   `idle, listening, thinking, speaking, approval, standby, error`. `working`
///   falls to `thinking`, the nearest bound state — Jarvis is busy and not
///   talking. Bind a `working` state in the spec and this line stops guessing.
/// * **`quiet` has no binding either.** The spec has `standby` but no `quiet`,
///   so a hand-set Quiet shows the `standby` colour, and only while nothing is
///   actually happening: if Jarvis is mid-turn the activity colour wins,
///   because that is the question the spec binds colour to.
///
/// Precedence, highest first: an error, then anything waiting on the human,
/// then what Jarvis is doing, then whether it is awake at all. Approvals sit
/// above activity deliberately — a tray icon exists to be glanced at, and the
/// only thing on this bus that needs the human is an approval.
fn spec_state(link: &LinkState) -> &'static str {
    if link.activity == "error" {
        return "error";
    }
    if link.approvals > 0 {
        return "approval";
    }
    match link.activity.as_str() {
        "listening" => "listening",
        "thinking" => "thinking",
        "speaking" => "speaking",
        "working" => "thinking",
        _ => match link.power.as_str() {
            "standby" | "quiet" => "standby",
            _ => "idle",
        },
    }
}

fn binding_for(link: &LinkState) -> Binding {
    let id = spec_state(link);
    spec::state_binding(id)
        .or_else(|| spec::state_binding("idle"))
        .unwrap_or_default()
}

/// Seconds since the process started, which is the `t` the pattern engine wants.
/// Its absolute value is irrelevant — every pattern is periodic in it.
fn clock() -> f64 {
    use std::sync::OnceLock;
    static START: OnceLock<std::time::Instant> = OnceLock::new();
    START
        .get_or_init(std::time::Instant::now)
        .elapsed()
        .as_secs_f64()
}

// ---------------------------------------------------------------------------
// Drawing
// ---------------------------------------------------------------------------

/// Renders the icon for a link state: a filled disc while the stream is up, a
/// ring while it is down.
///
/// Connectivity is carried by the *shape* and state by the colour, on purpose.
/// Giving "disconnected" a colour of its own would mean choosing one, and the
/// spec has no binding for it — a hollow icon says "nothing is coming through"
/// without claiming to know what Jarvis is doing.
fn render_icon(link: &LinkState) -> Option<Image<'static>> {
    let resolved = spec::resolve(&binding_for(link), clock(), 0.0, 0.0);
    Some(draw(resolved.a, resolved.b, link.connected))
}

/// Draws the disc into an RGBA buffer.
///
/// Supersampled 3×3 per pixel: at 32 px a hard-edged circle downscaled by the
/// shell to 16 px reads as a ragged blob, and the notification area is the one
/// place where a few hundred float operations at 2 Hz is not worth optimising.
fn draw(a: Rgb, b: Rgb, filled: bool) -> Image<'static> {
    let size = ICON_SIZE as f64;
    let centre = size / 2.0;
    // Leave a pixel of margin so the disc is not clipped by the shell's own
    // rounding of the icon rectangle.
    let outer = centre - 1.5;
    let inner = if filled { 0.0 } else { outer - 4.5 };

    let mut pixels = Vec::with_capacity((ICON_SIZE * ICON_SIZE * 4) as usize);
    for y in 0..ICON_SIZE {
        for x in 0..ICON_SIZE {
            let mut covered = 0.0f64;
            let mut edge = 0.0f64;
            for sy in 0..3 {
                for sx in 0..3 {
                    let px = x as f64 + (sx as f64 + 0.5) / 3.0;
                    let py = y as f64 + (sy as f64 + 0.5) / 3.0;
                    let d = ((px - centre).powi(2) + (py - centre).powi(2)).sqrt();
                    if d <= outer && d >= inner {
                        covered += 1.0 / 9.0;
                        // The outer third of the radius takes the darker of the
                        // two resolved colours, which is what gives the icon a
                        // rim instead of a flat dot at 16 px.
                        if d > outer * 0.66 {
                            edge += 1.0 / 9.0;
                        }
                    }
                }
            }
            if covered <= 0.0 {
                pixels.extend_from_slice(&[0, 0, 0, 0]);
                continue;
            }
            let rim = (edge / covered).clamp(0.0, 1.0);
            let blend = |hot: u8, cool: u8| {
                (hot as f64 * (1.0 - rim) + cool as f64 * rim)
                    .round()
                    .clamp(0.0, 255.0) as u8
            };
            pixels.extend_from_slice(&[
                blend(a.r, b.r),
                blend(a.g, b.g),
                blend(a.b, b.b),
                (covered * 255.0).round().clamp(0.0, 255.0) as u8,
            ]);
        }
    }

    Image::new_owned(pixels, ICON_SIZE, ICON_SIZE)
}

/// Re-resolves an animated pattern at [`ANIMATION_TICK`] and repaints only when
/// the 8-bit colour has actually moved.
fn spawn_animation(app: AppHandle) {
    tauri::async_runtime::spawn(async move {
        loop {
            tokio::time::sleep(ANIMATION_TICK).await;
            let link = app.state::<crate::stream::StreamState>().link();
            if !spec::is_animated(&binding_for(&link)) {
                continue;
            }
            repaint(&app, &link);
        }
    });
}

/// Pushes a new icon and tooltip, skipping the shell call when nothing moved.
fn repaint(app: &AppHandle, link: &LinkState) {
    let Some(tray) = app.tray_by_id(TRAY_ID) else {
        return;
    };
    let resolved = spec::resolve(&binding_for(link), clock(), 0.0, 0.0);
    {
        let painted = app.state::<Painted>();
        let mut slot = painted
            .0
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if *slot == Some(resolved.a) {
            return;
        }
        *slot = Some(resolved.a);
    }
    if let Err(err) = tray.set_icon(Some(draw(resolved.a, resolved.b, link.connected))) {
        eprintln!("[jarvis] tray: unable to set the icon: {err}");
    }
    if let Err(err) = tray.set_tooltip(Some(tooltip(link))) {
        eprintln!("[jarvis] tray: unable to set the tooltip: {err}");
    }
}

// ---------------------------------------------------------------------------
// Labels
// ---------------------------------------------------------------------------

fn activity_label(link: &LinkState) -> String {
    if !link.connected {
        return match &link.error {
            Some(err) => format!("Jarvis — offline: {}", first_sentence(err)),
            None => "Jarvis — connecting…".to_string(),
        };
    }
    match link.activity.as_str() {
        "idle" => "Jarvis — idle".to_string(),
        other => format!("Jarvis — {other}"),
    }
}

fn power_label(link: &LinkState) -> String {
    // `set_by` is "override" when a human set the mode, and schedule / idle /
    // auto when the machine did. Saying which matters: JARVIS-API §4 warns that
    // talking to Jarvis clears the second kind of Quiet and not the first.
    let by = match link.power_set_by.as_deref() {
        Some("override") => " · set by hand",
        Some("schedule") => " · quiet hours",
        Some("idle") => " · idle timer",
        _ => "",
    };
    format!("Power: {}{by}", link.power)
}

fn approvals_label(link: &LinkState) -> String {
    match link.approvals {
        0 if link.stale => "Approvals: unknown while offline".to_string(),
        0 => "No approvals waiting".to_string(),
        1 => "1 approval waiting".to_string(),
        n => format!("{n} approvals waiting"),
    }
}

/// The backend row's label and whether it is clickable.
///
/// Supervision is off by default and stays off unless the user turns it on, so
/// the common case is a row that explains rather than offers.
fn backend_row(app: &AppHandle) -> (String, bool) {
    let status = crate::sidecar::supervisor_status(app.clone());
    match (status.supervise, status.owned, status.configured) {
        (_, true, _) => (
            format!("Stop the backend (pid {})", status.pid.unwrap_or_default()),
            true,
        ),
        (true, false, true) => ("Start the backend".to_string(), true),
        (true, false, false) => (
            "Backend: supervision is on but nothing is configured".to_string(),
            false,
        ),
        (false, false, _) => ("Backend: not supervised".to_string(), false),
    }
}

fn tooltip(link: &LinkState) -> String {
    let mut parts = vec![activity_label(link)];
    if link.connected {
        parts.push(power_label(link));
        if link.approvals > 0 {
            parts.push(approvals_label(link));
        }
    }
    parts.push("Alt+Space".to_string());
    parts.join(" · ")
}

/// Trims a long error down to something a menu row can hold.
fn first_sentence(text: &str) -> String {
    let text = text.trim();
    let cut = text.find(['.', ';']).map(|i| i + 1).unwrap_or(text.len());
    let mut out = text[..cut].trim_end_matches(['.', ';']).to_string();
    if out.chars().count() > 60 {
        out = out.chars().take(57).collect::<String>() + "…";
    }
    out
}

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------

/// Called by the stream whenever the link state moves. Re-labels the rows and
/// repaints the icon.
pub fn on_link_changed(app: &AppHandle, link: &LinkState) {
    if let Some(rows) = app
        .state::<TrayHandles>()
        .inner
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .as_ref()
    {
        let _ = rows.activity.set_text(activity_label(link));
        let _ = rows.power.set_text(power_label(link));
        let _ = rows.approvals.set_text(approvals_label(link));
        // Nothing to open when the queue is empty, and a menu row that opens an
        // empty list is worse than one that is plainly unavailable.
        let _ = rows.approvals.set_enabled(link.approvals > 0);
        // The pid check is a `try_wait`, so this also notices a backend that
        // exited on its own between one event and the next.
        let (label, enabled) = backend_row(app);
        let _ = rows.backend.set_text(label);
        let _ = rows.backend.set_enabled(enabled);
    }
    // The state changed, so the previous colour is no longer what should be on
    // screen even if the pattern happens to resolve to it this instant.
    app.state::<Painted>()
        .0
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .take();
    repaint(app, link);
}

/// Routes a context-menu click to the matching action.
fn handle_menu_event(app: &AppHandle, event: tauri::menu::MenuEvent) {
    match event.id().as_ref() {
        // The three status rows are disabled, so they cannot fire; listed
        // anyway so that enabling one later cannot fall through to the
        // "unhandled" branch unnoticed.
        ID_STATUS_ACTIVITY | ID_STATUS_POWER | ID_STATUS_POWER_SWITCH => {}

        // The queue lives in the HUD, which is the surface with room for the
        // risk copy that makes an approval a decision rather than a button.
        ID_APPROVALS => {
            if let Err(err) = windows::show_hud(app) {
                eprintln!("[jarvis] tray: HUD unavailable: {err}");
                commands::notify(app, "Jarvis", &format!("HUD unavailable: {err}"));
            }
        }

        ID_SHOW_HUD => {
            if let Err(err) = windows::show_hud(app) {
                eprintln!("[jarvis] tray: HUD unavailable: {err}");
                commands::notify(app, "Jarvis", &format!("HUD unavailable: {err}"));
            }
        }

        ID_TOGGLE_SPOTLIGHT => match windows::toggle_quickbar(app) {
            Ok(true) => crate::emit_quickbar(app, events::FOCUS_INPUT, ()),
            Ok(false) => {}
            Err(err) => eprintln!("[jarvis] tray: quickbar toggle failed: {err}"),
        },

        ID_TOGGLE_WIDGET => {
            if let Err(err) = windows::toggle_widget(app) {
                eprintln!("[jarvis] tray: widget toggle failed: {err}");
            }
        }

        ID_BACKEND => run_backend_action(app),

        ID_SETTINGS => {
            if let Err(err) = windows::show_settings(app) {
                eprintln!("[jarvis] tray: settings unavailable: {err}");
                commands::notify(app, "Jarvis", &format!("Settings unavailable: {err}"));
            }
        }

        ID_RECONNECT => crate::stream::kick(app),

        ID_STATUS_CHECK => run_status_check(app),

        ID_QUIT => {
            #[cfg(desktop)]
            {
                use tauri_plugin_global_shortcut::GlobalShortcutExt;
                let _ = app.global_shortcut().unregister_all();
            }
            if let Some(hud) = app.get_webview_window(crate::HUD_LABEL) {
                let _ = hud.destroy();
            }
            // §6: quit goes through §5's shutdown path. It does — `exit(0)`
            // raises `ExitRequested` with a code, and `run()` answers that by
            // asking the backend to stop, waiting, and killing the tree if it
            // is still there. Only a backend this app started is touched: one
            // the user launched from a terminal is attached to, never adopted,
            // so quitting the GUI leaves it running.
            app.exit(0);
        }

        other => eprintln!("[jarvis] tray: unhandled menu id `{other}`"),
    }
}

/// Left click on the icon summons the spotlight, matching what users expect
/// from a launcher that lives in the notification area. Not emitted on Linux.
fn handle_tray_icon_event(tray: &tauri::tray::TrayIcon, event: TrayIconEvent) {
    if let TrayIconEvent::Click {
        button: MouseButton::Left,
        button_state: MouseButtonState::Up,
        ..
    } = event
    {
        let app = tray.app_handle();
        match windows::show_quickbar(app) {
            Ok(()) => crate::emit_quickbar(app, events::FOCUS_INPUT, ()),
            Err(err) => eprintln!("[jarvis] tray: unable to summon the quickbar: {err}"),
        }
    }
}

/// Starts or stops the backend, whichever the row is currently offering.
fn run_backend_action(app: &AppHandle) {
    let handle = app.clone();
    let owned = crate::sidecar::supervisor_status(app.clone()).owned;

    tauri::async_runtime::spawn(async move {
        let outcome = if owned {
            crate::sidecar::stop_owned(&handle, "asked from the tray").await
        } else {
            match crate::sidecar::start_backend(handle.clone()).await {
                Ok(outcome) => outcome,
                Err(err) => err,
            }
        };
        println!("[jarvis] tray: {outcome}");
        commands::notify(&handle, "Jarvis — backend", &outcome);
        // The row's label is derived from state that just changed.
        let link = handle.state::<crate::stream::StreamState>().link();
        on_link_changed(&handle, &link);
        if !owned {
            crate::sidecar::watch_startup(handle);
        }
    });
}

/// Probes the local services off the UI thread, then reports the result both as
/// a Windows toast and as an event the windows can render.
fn run_status_check(app: &AppHandle) {
    let handle = app.clone();

    tauri::async_runtime::spawn(async move {
        match commands::check_server_health(handle.clone()).await {
            Ok(report) => {
                commands::notify(&handle, "Jarvis — Status Check", &report.summary);
                crate::emit_all(&handle, events::HEALTH_REPORT, report);
            }
            Err(err) => {
                eprintln!("[jarvis] tray: status check failed: {err}");
                commands::notify(&handle, "Jarvis — Status Check", &format!("Failed: {err}"));
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    fn link() -> LinkState {
        LinkState {
            connected: true,
            stale: false,
            ..LinkState::default()
        }
    }

    /// The precedence order, which is the whole of the mapping's behaviour.
    #[test]
    fn state_precedence() {
        let mut l = link();
        assert_eq!(spec_state(&l), "idle");

        l.power = "standby".into();
        assert_eq!(spec_state(&l), "standby");
        l.power = "quiet".into();
        assert_eq!(spec_state(&l), "standby", "quiet borrows standby's binding");

        // Something happening outranks being quiet: the spec binds colour to
        // activity, and a Quiet Jarvis mid-answer is still answering.
        l.activity = "speaking".into();
        assert_eq!(spec_state(&l), "speaking");

        // Something waiting on the human outranks that.
        l.approvals = 2;
        assert_eq!(spec_state(&l), "approval");

        // An error outranks everything.
        l.activity = "error".into();
        assert_eq!(spec_state(&l), "error");
    }

    /// `working` is an activity with no state bound to it. This test is the
    /// alarm: if the spec ever grows a `working` state, it should stop passing
    /// and this mapping should stop guessing.
    #[test]
    fn working_falls_back_to_thinking() {
        let mut l = link();
        l.activity = "working".into();
        assert!(
            !spec::has_state("working"),
            "the spec now binds `working` — map it directly instead of to thinking"
        );
        assert_eq!(spec_state(&l), "thinking");
    }

    /// Every id the mapping can return must exist in the spec, or the icon
    /// silently falls back to idle's colour and the tray lies.
    #[test]
    fn every_mapped_state_is_bound() {
        for id in [
            "idle",
            "listening",
            "thinking",
            "speaking",
            "approval",
            "standby",
            "error",
        ] {
            assert!(spec::has_state(id), "`{id}` is not a spec state");
        }
    }

    /// The icon is the right size, has transparent corners and an opaque middle
    /// — the three things a wrong buffer layout would break.
    #[test]
    fn icon_is_a_disc_on_transparency() {
        let image = draw(Rgb { r: 255, g: 0, b: 0 }, Rgb { r: 0, g: 0, b: 128 }, true);
        assert_eq!(image.width(), ICON_SIZE);
        assert_eq!(image.height(), ICON_SIZE);
        let rgba = image.rgba();
        assert_eq!(rgba.len(), (ICON_SIZE * ICON_SIZE * 4) as usize);

        let at = |x: u32, y: u32| {
            let i = ((y * ICON_SIZE + x) * 4) as usize;
            (rgba[i], rgba[i + 1], rgba[i + 2], rgba[i + 3])
        };
        assert_eq!(at(0, 0).3, 0, "the corner must be transparent");
        let (_, _, _, alpha) = at(ICON_SIZE / 2, ICON_SIZE / 2);
        assert_eq!(alpha, 255, "the middle must be opaque");
        let (r, _, b, _) = at(ICON_SIZE / 2, ICON_SIZE / 2);
        assert!(r > b, "the middle takes the hot colour");
    }

    /// A disconnected icon is hollow, which is how the shape carries
    /// connectivity while the colour carries state.
    #[test]
    fn disconnected_icon_is_hollow() {
        let hollow = draw(
            Rgb { r: 255, g: 0, b: 0 },
            Rgb { r: 0, g: 0, b: 128 },
            false,
        );
        let rgba = hollow.rgba();
        let mid = (((ICON_SIZE / 2) * ICON_SIZE + ICON_SIZE / 2) * 4) as usize;
        assert_eq!(rgba[mid + 3], 0, "the middle of a ring is transparent");
    }

    /// Labels have to survive every state the stream can be in, including the
    /// one before it has ever connected.
    #[test]
    fn labels_cover_the_offline_case() {
        let cold = LinkState::default();
        assert_eq!(activity_label(&cold), "Jarvis — connecting…");
        assert_eq!(approvals_label(&cold), "Approvals: unknown while offline");

        let down = LinkState {
            error: Some(
                "could not reach the Jarvis server at http://127.0.0.1:4719. Is it running?".into(),
            ),
            ..LinkState::default()
        };
        assert!(activity_label(&down).starts_with("Jarvis — offline: could not reach"));
        assert!(activity_label(&down).chars().count() < 90);

        let mut quiet = link();
        quiet.power = "quiet".into();
        quiet.power_set_by = Some("override".into());
        assert_eq!(power_label(&quiet), "Power: quiet · set by hand");
    }
}
