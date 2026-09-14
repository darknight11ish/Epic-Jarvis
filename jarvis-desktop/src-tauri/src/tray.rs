//! The Windows notification-area icon: what Jarvis is doing, without a window.
//!
//! DESKTOP-BUILD build-order step 2. The icon is drawn here rather than loaded
//! from a file because its colour is state, and the state comes off the event
//! stream:
//!
//! ```text
//! Jarvis — thinking                        (status, disabled)
//! Power: quiet · set by hand · read-only   (status, disabled)
//! ─────────────────────────────
//! 2 approvals waiting                      (opens the queue)
//! 3 things waiting to be told · standby    (opens the brief)
//! Mute spoken interruptions until tomorrow
//! ─────────────────────────────
//! Show or hide Spotlight          Alt+Space
//! Show or hide the widget         Alt+Shift+W
//! Show the HUD window
//! Open the Brain
//! ─────────────────────────────
//! Backend: not supervised                  (status or action)
//! Reconnect the event stream
//! Run a status check
//! Settings…
//! ─────────────────────────────
//! Quit Jarvis
//! ```
//!
//! Four groups, in the order the questions get asked: what is Jarvis, what
//! wants me, where do I look, and what is under the hood. The two hotkeyed
//! rows lead their group because a hotkey printed beside a row is the only way
//! most people ever learn it exists.
//!
//! ## The power switch that is not here
//!
//! §6 asks for "a Quiet/Standby/Active switch" in the minimum menu. There is no
//! route to build it on. `jarvis_hud.py`'s `do_POST` serves `/api/shutdown`,
//! `/api/models/{install,switch,rollback}`, `/api/skills/decide`,
//! `/api/memory/decide`, `/api/approve`, `/api/deny` and `/api/chat` — and
//! nothing else. `jarvis_power` has `set_mode`, but the HTTP server does not
//! expose it, and `GET /api/version` reports the mode read-only inside
//! `capabilities.power`.
//!
//! This used to be a whole disabled row reading "Active · Quiet · Standby — the
//! server exposes no route yet". That is a true sentence and a bad menu item:
//! it spent a line, every single open, telling the owner about something that
//! does not exist. The same fact now rides on the `Power:` row as
//! `· read-only`, next to the value it qualifies. It becomes three live items
//! the day the server grows the route.
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
const ID_APPROVALS: &str = "approvals";
const ID_WAITING: &str = "waiting";
const ID_MUTE: &str = "mute";
const ID_BACKEND: &str = "backend";
const ID_SHOW_HUD: &str = "show-hud";
const ID_SHOW_BRAIN: &str = "show-brain";
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
    waiting: MenuItem<tauri::Wry>,
    mute: MenuItem<tauri::Wry>,
    backend: MenuItem<tauri::Wry>,
}

/// The colour last pushed to the shell, so an unchanged frame costs nothing.
///
/// Registered on the builder in `run()` alongside every other managed type,
/// not here. It used to be registered inside `create_tray`, after eight
/// fallible calls — and `run()` treats a `create_tray` failure as non-fatal, so
/// a menu-item error left the stream's very first event panicking on
/// `state::<Painted>()` in a task with no supervisor. Release builds set
/// `windows_subsystem = "windows"`, so that panic went to a stderr that does
/// not exist: no tray, no stream, no approvals, and nothing on screen to say so.
#[derive(Default)]
pub struct Painted(Mutex<Option<(Rgb, u32, &'static str)>>);

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
    let approvals = MenuItem::with_id(
        app,
        ID_APPROVALS,
        approvals_label(&link),
        link.approvals > 0,
        None::<&str>,
    )?;

    // The digest count. Separate from the approvals row because the two count
    // different things: an approval is waiting on a decision right now, a
    // digest item is waiting to be *told* to you. Folding them into one number
    // would make "3 waiting" mean neither.
    // Enabled whenever the arbiter has answered at all, NOT only when something
    // is pending. Gating it on `pending > 0` made the brief unreachable at the
    // exact moment the owner most wants it — "did I miss anything?" is a
    // question you ask when the count is zero — and took the interruption
    // budget and the mute control down with it, since the panel carries both.
    let waiting = MenuItem::with_id(
        app,
        ID_WAITING,
        waiting_label(&link),
        link.attention.known,
        None::<&str>,
    )?;
    let mute = MenuItem::with_id(app, ID_MUTE, mute_label(&link), true, None::<&str>)?;

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

    let show_hud = MenuItem::with_id(app, ID_SHOW_HUD, "Show the HUD window", true, None::<&str>)?;
    let show_brain = MenuItem::with_id(app, ID_SHOW_BRAIN, "Open the Brain", true, None::<&str>)?;
    let toggle_spotlight = MenuItem::with_id(
        app,
        ID_TOGGLE_SPOTLIGHT,
        "Show or hide Spotlight",
        true,
        Some("Alt+Space"),
    )?;
    let toggle_widget = MenuItem::with_id(
        app,
        ID_TOGGLE_WIDGET,
        "Show or hide the widget",
        true,
        Some("Alt+Shift+W"),
    )?;
    let reconnect = MenuItem::with_id(
        app,
        ID_RECONNECT,
        "Reconnect the event stream",
        true,
        None::<&str>,
    )?;
    let settings = MenuItem::with_id(app, ID_SETTINGS, "Settings…", true, None::<&str>)?;
    let status_check = MenuItem::with_id(
        app,
        ID_STATUS_CHECK,
        "Run a status check",
        true,
        None::<&str>,
    )?;
    let quit = MenuItem::with_id(app, ID_QUIT, "Quit Jarvis", true, None::<&str>)?;

    let menu = Menu::with_items(
        app,
        &[
            // What Jarvis is. Both rows are disabled: they report, they do
            // not offer.
            &activity,
            &power,
            &PredefinedMenuItem::separator(app)?,
            // What is waiting on you, and your control over being interrupted.
            // `mute` belongs here rather than among the machinery: it is the
            // answer to the two rows above it.
            &approvals,
            &waiting,
            &mute,
            &PredefinedMenuItem::separator(app)?,
            // Windows, everyday ones first — the two with hotkeys are the two
            // reached most often, and a hotkey printed beside a row is how the
            // owner learns it exists.
            &toggle_spotlight,
            &toggle_widget,
            &show_hud,
            &show_brain,
            &PredefinedMenuItem::separator(app)?,
            // The machinery. `backend` and `reconnect` were three groups apart
            // while being the same subject: is the thing on the other end of
            // the socket alive, and can I do something about it.
            &backend,
            &reconnect,
            &status_check,
            &settings,
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
            waiting,
            mute,
            backend,
        });

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

    // The activity states are composed by `attention::face_state`, which is
    // `jarvis_arbiter.face_state` line for line: it is the only place that
    // decides whether a resting face becomes `banked`, and it takes the
    // server's own `banked` flag rather than recomputing it.
    let composed = crate::attention::face_state(&link.activity, link.attention.banked);
    if composed != "idle" {
        return composed;
    }

    // Resting. Power decides between standby and idle — except that `banked`
    // has already claimed the resting face above, which is the right order:
    // "things are waiting silently" is more worth a glance than "asleep", and
    // the two never contradict each other because a banked system with budget
    // to spend is not a state the arbiter can produce.
    match link.power.as_str() {
        "standby" | "quiet" => "standby",
        _ => "idle",
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
    Some(paint(link))
}

/// Resolves the state and draws it, dim and notches included.
///
/// One function so the animation tick, the first paint and `repaint` cannot
/// disagree about what the icon should look like.
fn paint(link: &LinkState) -> Image<'static> {
    let state = spec_state(link);
    let resolved = spec::resolve(&binding_for(link), clock(), 0.0, 0.0);
    let dim = spec::state_dim(state);
    // `notches` is the overlay the spec puts on `banked`, and its source is
    // named there: "the number of items waiting in the digest
    // (jarvis_arbiter.pending_count)" — which is `attention.pending`, not the
    // approval queue.
    let notches = spec::notch_overlay(state)
        // The undimmed hot colour marks the ring: see `draw`.
        .map(|max| (link.attention.pending as usize, max, resolved.a));
    draw(
        shade(resolved.a, dim),
        shade(resolved.b, dim),
        link.connected,
        notches,
    )
}

/// Applies a state transform's `dim`. A plain multiply on the linearised value
/// would be more correct and less legible: these are small icons and the spec's
/// dims are chosen against what the faces look like on screen, which is sRGB.
fn shade(c: Rgb, dim: f64) -> Rgb {
    if dim >= 1.0 {
        return c;
    }
    let f = |v: u8| (f64::from(v) * dim).round().clamp(0.0, 255.0) as u8;
    Rgb {
        r: f(c.r),
        g: f(c.g),
        b: f(c.b),
    }
}

/// The outline drawn around the disc, and why there are two of them.
///
/// The notification area is the one surface whose backdrop the app does not
/// choose and cannot read: Windows 11 ships a light taskbar and a dark one, an
/// accent-coloured one, and whatever wallpaper shows through the acrylic. A
/// bare coloured disc is therefore always at risk — `standby` on a light
/// taskbar, and `banked`, which the spec dims to 0.45 and which measured
/// 1.72:1 against near-white.
///
/// One outline cannot solve this. Whatever colour it is, some taskbar matches
/// it: an edge chosen to oppose the FILL was the first attempt here, and it
/// measured 1.03:1 the moment a dim blue disc got a near-white ring and the
/// taskbar was white.
///
/// Two do solve it. The band is split: dark on the outside, light just inside
/// it. On a light taskbar the dark ring draws the silhouette; on a dark one the
/// dark ring disappears and the light ring draws it, 0.8 px in — 0.4 px after
/// the shell's downscale, which nobody can see. Whichever way the taskbar goes,
/// one of the two rings has contrast against it.
///
/// The dim stays. It is what `banked` MEANS, and a dimmed disc inside a legible
/// outline still reads as dimmed.
const INK_DARK: Rgb = Rgb {
    r: 12,
    g: 14,
    b: 18,
};
/// Not pure white: that flares on an OLED taskbar and reads as a halo rather
/// than an edge.
const INK_LIGHT: Rgb = Rgb {
    r: 236,
    g: 240,
    b: 245,
};

/// Draws the disc into an RGBA buffer.
///
/// Supersampled 3×3 per pixel: at 32 px a hard-edged circle downscaled by the
/// shell to 16 px reads as a ragged blob, and the notification area is the one
/// place where a few hundred float operations at 2 Hz is not worth optimising.
fn draw(a: Rgb, b: Rgb, filled: bool, notches: Option<(usize, usize, Rgb)>) -> Image<'static> {
    Image::new_owned(draw_pixels(a, b, filled, notches), ICON_SIZE, ICON_SIZE)
}

/// The pixel loop, split out from [`draw`] so it can be tested.
///
/// `Image` is a Tauri type and a test that wanted one would need an app handle;
/// a buffer of RGBA bytes needs nothing, and it is the part with the geometry
/// in it.
fn draw_pixels(a: Rgb, b: Rgb, filled: bool, notches: Option<(usize, usize, Rgb)>) -> Vec<u8> {
    let size = ICON_SIZE as f64;
    let centre = size / 2.0;
    // Leave a pixel of margin so the disc is not clipped by the shell's own
    // rounding of the icon rectangle.
    let outer = centre - 1.5;
    let inner = if filled { 0.0 } else { outer - 4.5 };
    // 1.6 px at 32, which the shell downscales to 0.8 px at 16 — a visible
    // edge rather than a border, which is all this needs to be.
    let stroke = 1.6f64;
    let edge_from = outer - stroke;
    // Where the dark half hands over to the light one.
    let ink_split = outer - stroke / 2.0;

    // The notch ring. `state_transforms.states.banked.overlay_spec` puts it
    // between 0.86 and 0.99 of the face radius, starting at twelve o'clock and
    // running clockwise, one notch per waiting item, up to `max_notches` with
    // an overflow mark beyond that.
    //
    // Positions sit on the fixed `max` grid rather than being spread evenly
    // across however many there are, so the ring reads as a gauge filling up:
    // three notches always occupy the same three o'clock positions, and a
    // fourth arriving adds one rather than shifting all of them.
    //
    // At 32 px — downscaled by the shell to 16 or 20 — twelve of these read as
    // a textured rim rather than a countable set. That is the honest limit of
    // the medium and it is the right signal anyway: the icon says *things are
    // banked and roughly how many*, and the exact number is one hover away in
    // the tooltip and one click away in the menu.
    let ring = notches.and_then(|(count, max, colour)| {
        let max = max.max(1);
        (count > 0).then(|| {
            let overflow = count > max;
            (count.min(max), max, overflow, colour)
        })
    });
    let notch_from = outer * 0.86;
    let notch_to = outer * 0.99;
    // Half the angular width of one tick, chosen so the mark is about 1.6 px
    // wide at the ring's radius: narrow enough to leave a clear gap on a 30°
    // pitch, wide enough to survive the downscale.
    let notch_half = 0.12f64;

    let mut pixels = Vec::with_capacity((ICON_SIZE * ICON_SIZE * 4) as usize);
    for y in 0..ICON_SIZE {
        for x in 0..ICON_SIZE {
            let mut covered = 0.0f64;
            let mut edge = 0.0f64;
            let mut notch = 0.0f64;
            let mut outline = 0.0f64;
            let mut outline_dark = 0.0f64;
            for sy in 0..3 {
                for sx in 0..3 {
                    let px = x as f64 + (sx as f64 + 0.5) / 3.0;
                    let py = y as f64 + (sy as f64 + 0.5) / 3.0;
                    let d = ((px - centre).powi(2) + (py - centre).powi(2)).sqrt();
                    if d <= outer && d >= edge_from {
                        outline += 1.0 / 9.0;
                        if d >= ink_split {
                            outline_dark += 1.0 / 9.0;
                        }
                    }
                    if d <= outer && d >= inner {
                        covered += 1.0 / 9.0;
                        // The outer third of the radius takes the darker of the
                        // two resolved colours, which is what gives the icon a
                        // rim instead of a flat dot at 16 px.
                        if d > outer * 0.66 {
                            edge += 1.0 / 9.0;
                        }
                    }
                    if let Some((count, max, overflow, _)) = ring {
                        if d >= notch_from && d <= notch_to {
                            // atan2 measured clockwise from twelve o'clock, so
                            // notch 0 is straight up and the count runs the way
                            // a clock does.
                            let angle = (px - centre).atan2(centre - py);
                            let pitch = std::f64::consts::TAU / max as f64;
                            for i in 0..count {
                                // The last tick doubles in width when there are
                                // more items than the ring can show: an extra
                                // mark somewhere else on the ring would read as
                                // one more item, which is the opposite of what
                                // an overflow means.
                                let half = if overflow && i + 1 == count {
                                    notch_half * 2.0
                                } else {
                                    notch_half
                                };
                                let mut delta = angle - i as f64 * pitch;
                                // Wrap into (-π, π] so the tick at twelve
                                // o'clock is not split across the seam.
                                delta = delta.rem_euclid(std::f64::consts::TAU);
                                if delta > std::f64::consts::PI {
                                    delta -= std::f64::consts::TAU;
                                }
                                if delta.abs() <= half {
                                    notch += 1.0 / 9.0;
                                    break;
                                }
                            }
                        }
                    }
                }
            }
            if covered <= 0.0 && notch <= 0.0 && outline <= 0.0 {
                pixels.extend_from_slice(&[0, 0, 0, 0]);
                continue;
            }
            let rim = if covered > 0.0 {
                (edge / covered).clamp(0.0, 1.0)
            } else {
                1.0
            };
            let blend = |hot: u8, cool: u8| {
                (hot as f64 * (1.0 - rim) + cool as f64 * rim)
                    .round()
                    .clamp(0.0, 255.0) as u8
            };
            // A notch is drawn in the state's UNDIMMED colour, over whatever
            // the disc put there. `banked` is dimmed to 0.45, so the ring needs
            // to escape that dim to be legible — and using the same hue at full
            // strength keeps it inside the palette the spec bound, rather than
            // introducing a colour of its own.
            let lit = notch.clamp(0.0, 1.0);
            let mark = ring.map(|(_, _, _, colour)| colour).unwrap_or(a);
            // Order matters: disc, then the outline over it, then the notch
            // ring over both. The notches sit at 0.86-0.99 of the radius, which
            // is inside the outline band — and they are the one mark that must
            // never be swallowed, because they are the count.
            let rim_ink = outline.clamp(0.0, 1.0);
            // Which of the two rings this pixel mostly belongs to. A pixel
            // straddling the split takes the majority rather than a blend of
            // the two, because a mid-grey between them contrasts with neither
            // taskbar, which is the whole failure being fixed.
            let ink = if outline > 0.0 && outline_dark / outline >= 0.5 {
                INK_DARK
            } else {
                INK_LIGHT
            };
            let out = |hot: u8, cool: u8, tick: u8, pen: u8| {
                let base = blend(hot, cool) as f64;
                let edged = base * (1.0 - rim_ink) + f64::from(pen) * rim_ink;
                (edged * (1.0 - lit) + f64::from(tick) * lit)
                    .round()
                    .clamp(0.0, 255.0) as u8
            };
            pixels.extend_from_slice(&[
                out(a.r, b.r, mark.r, ink.r),
                out(a.g, b.g, mark.g, ink.g),
                out(a.b, b.b, mark.b, ink.b),
                (covered.max(notch).max(outline) * 255.0)
                    .round()
                    .clamp(0.0, 255.0) as u8,
            ]);
        }
    }

    pixels
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
    let state = spec_state(link);
    let resolved = spec::resolve(&binding_for(link), clock(), 0.0, 0.0);
    {
        let painted = app.state::<Painted>();
        let mut slot = painted
            .0
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        // The notch count is part of the key. Keying on the colour alone meant
        // a fourth item arriving while banked — same still colour, one more
        // notch — was skipped as an unchanged frame, so the ring never grew.
        let key = (resolved.a, link.attention.pending, state);
        if *slot == Some(key) {
            return;
        }
        *slot = Some(key);
    }
    if let Err(err) = tray.set_icon(Some(paint(link))) {
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
    // "read-only" replaces what used to be a whole disabled row beneath this
    // one, naming three modes the server has no route to set. Saying it here
    // costs no line in a menu the owner opens dozens of times a day, and it
    // disappears the moment the row becomes settable.
    format!("Power: {}{by} · read-only", link.power)
}

fn approvals_label(link: &LinkState) -> String {
    match link.approvals {
        0 if link.stale => "Approvals: unknown while offline".to_string(),
        0 => "No approvals waiting".to_string(),
        1 => "1 approval waiting".to_string(),
        n => format!("{n} approvals waiting"),
    }
}

/// How many things are banked, and — when nothing can be said out loud — why.
///
/// This is `attention.pending`, the digest count, which is also the notch count
/// on the reactor's rim. `blocked_by` is what makes the row worth reading: "3
/// waiting" and "3 waiting · standby" are different situations, and the second
/// one explains why the machine has gone quiet.
fn waiting_label(link: &LinkState) -> String {
    if !link.attention.known {
        return "Waiting: unknown".to_string();
    }
    let head = match link.attention.pending {
        0 => "Nothing waiting — the brief and the budget".to_string(),
        1 => "1 thing waiting to be told".to_string(),
        n => format!("{n} things waiting to be told"),
    };
    match link.attention.blocked_by.as_deref() {
        Some(reason) if link.attention.pending > 0 => format!("{head} · {reason}"),
        _ if link.attention.pending > 0 => format!(
            "{head} · {} of {} interruptions left",
            link.attention.remaining, link.attention.limit
        ),
        _ => head,
    }
}

/// The mute row. Worded with its end date every time, because the API has no
/// mute without one and a row that just said "Mute" would imply otherwise.
fn mute_label(link: &LinkState) -> String {
    if link.attention.muted {
        "Unmute spoken interruptions".to_string()
    } else {
        "Mute spoken interruptions until tomorrow".to_string()
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
        if link.attention.pending > 0 {
            parts.push(waiting_label(link));
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
        let _ = rows.waiting.set_text(waiting_label(link));
        let _ = rows.waiting.set_enabled(link.attention.known);
        let _ = rows.waiting.set_enabled(link.attention.pending > 0);
        let _ = rows.mute.set_text(mute_label(link));
        // Muting is a write, and a write against a backend that has not been
        // read yet is a guess about which direction to write in.
        let _ = rows
            .mute
            .set_enabled(link.attention.known && link.connected);
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
        ID_STATUS_ACTIVITY | ID_STATUS_POWER => {}

        // The queue lives in the quickbar now, and the old comment here — "the
        // HUD is the surface with room for the risk copy" — stopped being true
        // when the gate grew its risk line, its `raised` chip with the
        // attacker's quote, the named source, the tier move and the context
        // disclosure. The HUD window loads the backend's own page, which is not
        // ours to add any of that to.
        ID_APPROVALS => {
            if let Err(err) = windows::show_quickbar(app) {
                eprintln!("[jarvis] tray: quickbar unavailable: {err}");
                commands::notify(app, "Jarvis", &format!("Quickbar unavailable: {err}"));
                return;
            }
            crate::emit_quickbar(app, events::SHOW_APPROVAL, ());
        }

        ID_SHOW_HUD => {
            if let Err(err) = windows::show_hud(app) {
                eprintln!("[jarvis] tray: HUD unavailable: {err}");
                commands::notify(app, "Jarvis", &format!("HUD unavailable: {err}"));
            }
        }

        ID_SHOW_BRAIN => {
            if let Err(err) = windows::show_brain(app) {
                eprintln!("[jarvis] tray: the Brain would not open: {err}");
                commands::notify(app, "Jarvis", &format!("Brain unavailable: {err}"));
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

        // The brief is a list with consequence ranking and disclosures, not a
        // menu, so the row opens the surface that can render one. That is the
        // quickbar rather than the HUD: the HUD window loads the backend's own
        // `jarvis_hud.html`, which is not ours to add sections to.
        ID_WAITING => {
            if let Err(err) = windows::show_quickbar(app) {
                eprintln!("[jarvis] tray: quickbar unavailable: {err}");
                commands::notify(app, "Jarvis", &format!("Quickbar unavailable: {err}"));
                return;
            }
            crate::emit_quickbar(app, events::SHOW_DIGEST, ());
        }

        // Mute is a toggle against the server, and its direction comes from
        // what the server last said rather than from a local flag — two windows
        // and a tray sharing one budget must not each keep their own idea of
        // whether it is muted.
        ID_MUTE => {
            let app = app.clone();
            tauri::async_runtime::spawn(async move {
                let muted = app
                    .state::<crate::stream::StreamState>()
                    .link()
                    .attention
                    .muted;
                if let Err(err) = crate::attention::set_attention_muted(app.clone(), !muted).await {
                    eprintln!("[jarvis] tray: mute failed: {err}");
                    commands::notify(&app, "Jarvis", &first_sentence(&err));
                }
            });
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

    /// Relative luminance, WCAG's definition, 0..1.
    ///
    /// Used to choose an outline that survives whichever taskbar the owner runs.
    fn luma(c: Rgb) -> f64 {
        let ch = |v: u8| {
            let s = f64::from(v) / 255.0;
            if s <= 0.03928 {
                s / 12.92
            } else {
                ((s + 0.055) / 1.055).powf(2.4)
            }
        };
        0.2126 * ch(c.r) + 0.7152 * ch(c.g) + 0.0722 * ch(c.b)
    }

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

    /// `banked` replaces a resting face and nothing else — the server's own
    /// rule, and the reason it is composed in one place rather than per
    /// surface.
    #[test]
    fn banked_takes_the_resting_face_only() {
        let mut l = link();
        l.attention.known = true;
        l.attention.banked = true;
        l.attention.pending = 3;
        assert_eq!(spec_state(&l), "banked");

        // Foreground wins: the budget governs what Jarvis starts, not what it
        // is in the middle of.
        l.activity = "speaking".into();
        assert_eq!(spec_state(&l), "speaking");
        l.activity = "idle".into();

        // So does something waiting on a decision, and so does an error.
        l.approvals = 1;
        assert_eq!(spec_state(&l), "approval");
        l.approvals = 0;
        l.activity = "error".into();
        assert_eq!(spec_state(&l), "error");
        l.activity = "idle".into();

        // Standby is the resting face when nothing is banked, and banked wins
        // over it when something is: "things are waiting silently" is worth
        // more of a glance than "asleep".
        l.power = "standby".into();
        assert_eq!(spec_state(&l), "banked");
        l.attention.banked = false;
        assert_eq!(spec_state(&l), "standby");
    }

    /// The dim is a shell transform the spec asks every client to apply once.
    /// Banked at full brightness is just idle in a different hue.
    #[test]
    fn banked_is_dimmed_and_notched() {
        assert_eq!(spec::state_dim("banked"), 0.45);
        assert_eq!(spec::state_dim("standby"), 0.6);
        assert_eq!(spec::state_dim("idle"), 1.0, "idle carries no transform");
        assert_eq!(spec::notch_overlay("banked"), Some(12));
        assert_eq!(spec::notch_overlay("idle"), None);
        assert_eq!(
            spec::notch_overlay("approval"),
            None,
            "approval pings, not notches"
        );
    }

    /// The notch ring has to actually change the pixels, and it has to change
    /// them *more* as items arrive — the bug this guards is a cached frame that
    /// skips the repaint because the colour did not move.
    #[test]
    fn notches_grow_with_the_count() {
        let hot = Rgb {
            r: 255,
            g: 220,
            b: 180,
        };
        let cool = Rgb {
            r: 40,
            g: 30,
            b: 20,
        };
        let lit = |count: usize| {
            draw(
                shade(hot, 0.45),
                shade(cool, 0.45),
                true,
                (count > 0).then_some((count, 12, hot)),
            )
            .rgba()
            .chunks(4)
            // A notch is BRIGHTER than the dimmed disc and WARMER than the
            // outline. Brightness alone was the old test, and it was right
            // until the two-tone outline existed: `INK_LIGHT` is bright by
            // design, so a dimmed disc with no notches at all counted 68 ring
            // pixels. The hue is what separates them — the notch is drawn in
            // the state's own undimmed colour, and these two rings are
            // deliberately neutral.
            .filter(|px| {
                px[3] > 0
                    && px[0] as u16 > (255.0 * 0.45) as u16 + 20
                    && px[0] as i16 - px[2] as i16 > 40
            })
            .count()
        };
        let none = lit(0);
        let one = lit(1);
        let four = lit(4);
        assert_eq!(
            none, 0,
            "a dimmed disc with no notches drew ring pixels anyway"
        );
        assert!(one > 0, "one waiting item must draw one notch");
        assert!(
            four > one * 2,
            "four notches ({four} px) should be well clear of one ({one} px)"
        );

        // Over the maximum the ring stops counting and marks the overflow
        // rather than wrapping around and reading as a smaller number.
        let twelve = lit(12);
        let fifty = lit(50);
        assert!(
            fifty > twelve,
            "the overflow mark must be visible: 50 drew {fifty} px, 12 drew {twelve}"
        );
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
            "banked",
        ] {
            assert!(spec::has_state(id), "`{id}` is not a spec state");
        }
    }

    /// The icon is the right size, has transparent corners and an opaque middle
    /// — the three things a wrong buffer layout would break.
    #[test]
    fn icon_is_a_disc_on_transparency() {
        let image = draw(
            Rgb { r: 255, g: 0, b: 0 },
            Rgb { r: 0, g: 0, b: 128 },
            true,
            None,
        );
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
            None,
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
        // Nothing has been read, so the row says so rather than "nothing
        // waiting" over a digest that was never fetched.
        assert_eq!(waiting_label(&cold), "Waiting: unknown");

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
        // `· read-only` replaced a whole disabled row that said the same
        // thing. It is part of the label now, not decoration.
        assert_eq!(
            power_label(&quiet),
            "Power: quiet · set by hand · read-only"
        );

        // The mute row names its end date in both directions, because the API
        // has no mute without one.
        let mut budgeted = link();
        budgeted.attention.known = true;
        assert!(mute_label(&budgeted).contains("until tomorrow"));
        budgeted.attention.muted = true;
        assert_eq!(mute_label(&budgeted), "Unmute spoken interruptions");

        // A blocked budget explains itself on the row rather than leaving the
        // user to wonder why nothing is being said.
        budgeted.attention.pending = 3;
        budgeted.attention.blocked_by = Some("muted until tomorrow".into());
        assert_eq!(
            waiting_label(&budgeted),
            "3 things waiting to be told · muted until tomorrow"
        );
        budgeted.attention.blocked_by = None;
        budgeted.attention.limit = 6;
        budgeted.attention.remaining = 2;
        assert_eq!(
            waiting_label(&budgeted),
            "3 things waiting to be told · 2 of 6 interruptions left"
        );
    }
    /// Contrast ratio between two opaque colours, WCAG's formula.
    fn ratio(x: Rgb, y: Rgb) -> f64 {
        let (a, b) = (luma(x), luma(y));
        let (hi, lo) = if a > b { (a, b) } else { (b, a) };
        (hi + 0.05) / (lo + 0.05)
    }

    /// Composites a pixel of the icon over a taskbar of a known colour.
    fn over(px: &[u8], bg: Rgb) -> Rgb {
        let alpha = f64::from(px[3]) / 255.0;
        let mix = |fg: u8, back: u8| {
            (f64::from(fg) * alpha + f64::from(back) * (1.0 - alpha)).round() as u8
        };
        Rgb {
            r: mix(px[0], bg.r),
            g: mix(px[1], bg.g),
            b: mix(px[2], bg.b),
        }
    }

    fn pixel(buf: &[u8], x: u32, y: u32) -> &[u8] {
        let i = ((y * ICON_SIZE + x) * 4) as usize;
        &buf[i..i + 4]
    }

    /// Two rings, opposed, so neither taskbar can hide both.
    #[test]
    fn the_two_rings_oppose_each_other() {
        assert!(luma(INK_LIGHT) > 0.8, "the inner ring is not light");
        assert!(luma(INK_DARK) < 0.02, "the outer ring is not dark");
    }

    /// The finding this exists for: `banked` is dimmed to 0.45 by the spec and
    /// measured 1.72:1 against a light taskbar. The disc may stay dim — that is
    /// what banked means — but the icon must still have a silhouette.
    ///
    /// Measured the way the eye does it: the strongest edge anywhere on the
    /// icon, against each of the two taskbars Windows ships. A fixed probe
    /// coordinate was the first attempt and it measured the antialiasing at
    /// the outer edge rather than the ring, reporting 1.03:1 for a design that
    /// actually holds at 14:1.
    #[test]
    fn the_icon_has_an_edge_against_both_taskbars() {
        const WHITE: Rgb = Rgb {
            r: 243,
            g: 243,
            b: 243,
        };
        const BLACK: Rgb = Rgb {
            r: 32,
            g: 32,
            b: 32,
        };

        /// The strongest contrast any pixel of the icon reaches against `bg`.
        ///
        /// Walked by index rather than with `chunks_exact(4)`: clippy from
        /// 1.98 pushes a constant chunk size onto `as_chunks::<4>()`, which is
        /// newer than the toolchain some of this is built with. Stepping is
        /// the version-independent spelling.
        fn strongest(buf: &[u8], bg: Rgb) -> f64 {
            let mut best = 1.0f64;
            for i in (0..buf.len()).step_by(4) {
                let px = &buf[i..i + 4];
                if px[3] == 0 {
                    continue;
                }
                best = best.max(ratio(over(px, bg), bg));
            }
            best
        }

        // Every state's resolved colour, dimmed as `paint` dims it. The two
        // extremes are what matter: the dimmest (banked, 0.45) and a pale one.
        for (name, fill) in [
            (
                "banked",
                shade(
                    Rgb {
                        r: 108,
                        g: 211,
                        b: 249,
                    },
                    0.45,
                ),
            ),
            (
                "standby",
                shade(
                    Rgb {
                        r: 107,
                        g: 125,
                        b: 148,
                    },
                    0.6,
                ),
            ),
            (
                "speaking",
                Rgb {
                    r: 214,
                    g: 242,
                    b: 255,
                },
            ),
            (
                "error",
                Rgb {
                    r: 247,
                    g: 59,
                    b: 59,
                },
            ),
        ] {
            let buf = draw_pixels(fill, fill, true, None);
            for (bg, label) in [(WHITE, "a light taskbar"), (BLACK, "a dark one")] {
                let r = strongest(&buf, bg);
                assert!(
                    r >= 3.0,
                    "{name} on {label}: the strongest edge measures {r:.2}:1, under 3:1"
                );
            }
        }
    }

    /// The notch ring is the count. It must not be swallowed by the outline it
    /// now overlaps — notches sit at 0.86-0.99 of the radius, the outline at
    /// 0.89-1.0 of it.
    #[test]
    fn a_notch_still_reads_over_the_outline() {
        let dim = shade(
            Rgb {
                r: 108,
                g: 211,
                b: 249,
            },
            0.45,
        );
        let hot = Rgb {
            r: 108,
            g: 211,
            b: 249,
        };
        let buf = draw_pixels(dim, dim, true, Some((1, 12, hot)));
        // Notch 0 is straight up, at the top of the ring.
        let top = pixel(&buf, ICON_SIZE / 2, 2);
        let side = pixel(&buf, ICON_SIZE / 2 + 14, ICON_SIZE / 2);
        assert!(
            ratio(
                over(
                    top,
                    Rgb {
                        r: 32,
                        g: 32,
                        b: 32
                    }
                ),
                over(
                    side,
                    Rgb {
                        r: 32,
                        g: 32,
                        b: 32
                    }
                )
            ) > 1.6,
            "the notch is indistinguishable from the outline beside it"
        );
    }
}
