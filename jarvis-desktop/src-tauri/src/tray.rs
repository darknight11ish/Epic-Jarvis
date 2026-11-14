//! The Windows notification-area icon: what Atlas is doing, without a window.
//!
//! DESKTOP-BUILD build-order step 2. The icon is drawn here rather than loaded
//! from a file because its colour is state, and the state comes off the event
//! stream:
//!
//! ```text
//! Atlas — thinking                        (status, disabled)
//! Power: quiet · set by hand              (status, disabled)
//! Change power mode ▸ Active / Quiet / Standby
//! ─────────────────────────────
//! 2 approvals waiting                      (opens the queue)
//! Mute spoken interruptions until tomorrow
//! Stop everything
//! ─────────────────────────────
//! Start Atlas Live
//! ─────────────────────────────
//! Show or hide the Atlas bar              Alt+Space
//! Show the HUD window
//! Open the Brain
//! Settings and help…
//! More… ▸ Start Watch with me · Show or hide the widget · Show or hide the
//!         floating face · Floating face: bigger · Floating face: smaller ·
//!         Chat history… · Faces… · Everything Atlas can do…
//!         Backend: not supervised · Reconnect the event stream · Run a status
//!         check · Not checked yet · Update Atlas to <version>
//! ─────────────────────────────
//! Quit Atlas
//! ```
//!
//! ## Two update rows: one acts, one reports
//!
//! `ID_UPDATE` is the ACTION and it exists only while a newer version is known
//! (the owner, 2026-11-03 - see below). `ID_UPDATE_STATE` is the REPORT: a
//! disabled row that is always in the menu and says one of four things -
//! `Up to date · checked 14:32`, `Update available · checked 14:32`,
//! `Not checked yet`, `Cannot check · <why>` - from `update.rs`'s own
//! `Status::state` (Task-50, Wave 12). Before it, the absence of the action row
//! meant "nothing known", "nothing newer" and "the check failed" all at once,
//! so a menu could not tell the owner which one it was. The report row adds no
//! state of its own: `update_state_row` reads the cached answer and the OS's
//! local clock, and invents neither.
//!
//! Five groups and four separators, in the order the questions get asked: what
//! is Atlas, what wants me, Atlas Live, where do I look, and the one row that
//! ends the session. `ia.mjs` counts the separators, so a row added without
//! thinking about the groups is caught rather than silently making the menu
//! longer again.
//!
//! ## The update row exists only while there is an update
//!
//! The owner, 2026-11-03: *"when i right click the tray icon for jarvis I want
//! a menu option that appears if there is an update to jarvis"*. So the no-update
//! state is the row being **absent**, not greyed out. `update_row` is that whole
//! rule - `None` means it does not belong in the menu, `Some(label)` means it
//! does and names the version when the check gave one - and `on_update_status`
//! is the one place that adds it (`Submenu::append`) or takes it away
//! (`Submenu::remove`). Tauri 2.12's `MenuItem` has no `set_visible`, which is
//! why the menu itself is where absence lives.
//!
//! Pressing it **updates both halves**: `update::install_from_tray` runs the same
//! `update_both` the Settings Install press and an answered chat card run - the
//! backend is patched first, then Jarvis Desktop installs - after turning the
//! row into "Updating Atlas to <version>…" so a second press cannot start a
//! second run. Only where the backend half cannot run at all (the two folders
//! are not set, or the patch program is missing) does it fall back to the
//! desktop-only `install_update`, and then it says plainly that the BACKEND was
//! NOT updated and where to finish it. It is never automatic and there is no
//! second updater. **With App lock on it is behind the lock** (DEF-045): the row
//! patches the live backend, so the press asks Windows Hello first
//! (`lock::require_unlocked`, the same prompt the rows that open a window show)
//! and starts nothing unless it confirms - declining says plainly that nothing
//! was started. On Windows a successful install ends this process (the
//! installer restarts the app), so the next launch starts with the row absent
//! because the new version is the running one - the row cannot linger after an
//! install.
//!
//! Atlas Live keeps a group of its own: it sat right under "Stop everything",
//! and a click one row off started or ended it (the Live review, 2026-09-28).
//! Quit keeps the separator above it for the same kind of reason - it is the one
//! row that ends the session.
//!
//! ## The "More…" submenu
//!
//! The owner asked for this menu to be about half its length - "only put the
//! most important ones" - and chose to move the rest one click in rather than
//! delete them, so nothing became unreachable. The brief row, Watch with me,
//! the windows group's tail and the whole machinery group now live in one
//! submenu built in `create_tray`. Every one of them is the SAME `MenuItem` it
//! always was, still held by [`Rows`]: rebuilding one with the same id would
//! show the same words on screen and then silently stop updating as the state
//! changed.
//!
//! A hotkeyed row leads its group because a hotkey printed beside a row is the
//! only way most people ever learn it exists.
//!
//! ## The power switch
//!
//! §6 asks for "a Quiet/Standby/Active switch" in the minimum menu. For a long
//! time there was no route to build it on, and the `Power:` row said
//! `· read-only`. `backend/power-mode.patch` adds `POST /api/power`, so the
//! row is now followed by a "Change power mode" submenu with the three modes.
//! The server sends the change through its approval gate as `power_manage`
//! (the owner's toml says `auto`: the safe direction either way), and the
//! `Power:` row changes only when the server's own `power` event says so -
//! never on the click. Waking (Active) is held while the link is stale, like
//! any other action; going quieter is not. A backend without the patch
//! answers 404, and the tray says so in a notification.
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
    menu::{IsMenuItem, Menu, MenuItem, PredefinedMenuItem, Submenu},
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
const ID_STOP_EVERYTHING: &str = "stop-everything";
/// Atlas Live (live.rs): start or end the voice conversation on this PC.
const ID_LIVE: &str = "jarvis-live";
/// Watch with me (look.rs): start or stop the session on this PC.
const ID_WATCH: &str = "jarvis-watch";
const ID_POWER_ACTIVE: &str = "power-active";
const ID_POWER_QUIET: &str = "power-quiet";
const ID_POWER_STANDBY: &str = "power-standby";
const ID_BACKEND: &str = "backend";
const ID_SHOW_HUD: &str = "show-hud";
const ID_SHOW_BRAIN: &str = "show-brain";
/// "Chat history…" (the chat audit, 2026-09-28): the Brain, on History.
const ID_CHAT_HISTORY: &str = "chat-history";
/// A second (or third, or...) conversation window (2026-11-03, the owner's
/// ask: "have multiple conversation windows open at once").
const ID_NEW_CHAT_WINDOW: &str = "new-chat-window";
const ID_SHOW_FACES: &str = "show-faces";
/// "Everything Atlas can do" (docs/FEATURES-LIST-DESIGN.md, 2026-10-08): the
/// whole feature set, in plain words, read-only.
const ID_SHOW_FEATURES: &str = "show-features";
const ID_TOGGLE_SPOTLIGHT: &str = "toggle-spotlight";
const ID_TOGGLE_WIDGET: &str = "toggle-widget";
const ID_TOGGLE_FLOATING: &str = "toggle-floating";
/// The floating face's size cycle (2026-10-30): two rows rather than a new
/// Settings control, because every Settings toggle is generated from the
/// backend's settings registry (a cross-app contract); this is desktop-only
/// and lives where the face's own on/off row already lives.
const ID_FLOATING_BIGGER: &str = "floating-bigger";
const ID_FLOATING_SMALLER: &str = "floating-smaller";
const ID_RECONNECT: &str = "reconnect";
const ID_SETTINGS: &str = "settings";
const ID_UPDATE: &str = "update";
/// The update REPORT row (Task-50, Wave 12): "Up to date · checked 14:32",
/// "Update available · checked 14:32", "Not checked yet" or
/// "Cannot check · <why>". Always in the menu, always disabled - it reports
/// the four-state truth from `update.rs` and never acts.
const ID_UPDATE_STATE: &str = "update-state";
/// "Setup unfinished - 9 of 25" (Wave B, 2026-11-03): the "Personalize Atlas"
/// quiz is not finished. Like the update row it is ABSENT when there is
/// nothing to do, and it is driven by `setup_offer`'s state - never fetched
/// from here.
const ID_SETUP: &str = "setup-unfinished";
const ID_STATUS_CHECK: &str = "status-check";
const ID_QUIT: &str = "quit";

/// Handles to the menu rows whose text is state, so they can be re-labelled in
/// place. Rebuilding the whole menu on every event would close it under the
/// user's cursor.
///
/// A row's home in the menu is not recorded here, and does not need to be: a
/// `MenuItem` keeps working wherever it is parented. That is what makes the
/// "More…" submenu safe - `waiting`, `watch`, `backend` and `update` moved
/// into it and kept the SAME handle, so they still re-label themselves. A new
/// `MenuItem` built for the submenu would have looked identical and then
/// quietly stopped updating, with nothing to report it.
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
    /// "Start Atlas Live" / "End Atlas Live".
    live: MenuItem<tauri::Wry>,
    watch: MenuItem<tauri::Wry>,
    backend: MenuItem<tauri::Wry>,
    /// Parented only while a newer version is known to exist.
    update: MenuItem<tauri::Wry>,
    /// The always-present update REPORT row (Task-50): "Up to date · checked
    /// 14:32" / "Cannot check · …" / "Not checked yet". Disabled; it reports and
    /// never acts, and it is re-labelled in place as the cached answer moves.
    update_state: MenuItem<tauri::Wry>,
    /// "Setup unfinished - 9 of 25" (Wave B): parented only while the quiz is
    /// unfinished. Same change-of-parent rule as `update`.
    setup: MenuItem<tauri::Wry>,
    /// The "More…" submenu `update` is added to and removed from - change of
    /// parent is how the row becomes absent (Tauri 2.12 has no `set_visible`).
    more: Submenu<tauri::Wry>,
    // The rows that PRINT a hotkey. Kept so a rebind can re-label them:
    // `accel()` was only ever read while the menu was built, so a row went on
    // advertising the key the owner had just replaced - the exact thing the
    // `toggle_spotlight` comment below exists to prevent (click audit,
    // 2026-10-08: the tooltip, rebuilt live, showed the new key while the row
    // showed the old one).
    stop_everything: MenuItem<tauri::Wry>,
    toggle_spotlight: MenuItem<tauri::Wry>,
    toggle_widget: MenuItem<tauri::Wry>,
    toggle_floating: MenuItem<tauri::Wry>,
}

/// What was last painted: the two colours, the notch count, the state, and
/// whether Atlas Live's mark was on it.
type PaintKey = (Rgb, Rgb, u32, &'static str, bool, bool);

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
pub struct Painted(Mutex<Option<PaintKey>>);

/// The tray's flash-safety governor — one instance, because the tray draws
/// exactly one surface (the icon). See [`spec::FlashGovernor`] for why one of
/// these must never be shared across more than one surface, and
/// [`governed_resolve`] for the one place it is called from: calling it twice
/// per repaint (this module used to resolve once for the dedup key and again
/// inside `paint`) would show it the same logical frame as two frames.
///
/// Registered in `run()` alongside `Painted`, for the same reason `Painted`
/// is: a panic on first use, in a task with no supervisor, in a release
/// build with no stderr.
#[derive(Default)]
pub struct TrayFlashGovernor(Mutex<spec::FlashGovernor>);

/// What the update row says, or `None` when it must not be in the menu at all.
///
/// The owner asked for this exactly (2026-11-03): *"when i right click the tray
/// icon for jarvis I want a menu option that appears if there is an update to
/// jarvis"*. So **absence is the no-update state** - not a greyed-out row - and
/// the label is the plain instruction, naming the version when the check gave
/// one ("Update Atlas to 0.2.411"), because the row is also the only warning
/// the owner gets before pressing it.
///
/// Pure on purpose: this is the whole rule, and a rule this small is the part
/// that can be a test without a running app. `None` is "no row"; `Some` is the
/// text of the row that must be there.
fn update_row(available: Option<&str>) -> Option<String> {
    let version = available?.trim();
    // A check can know "something newer exists" without a version worth
    // printing; the row still appears, in plain words.
    if version.is_empty() {
        return Some("Update Atlas".to_string());
    }
    Some(format!("Update Atlas to {version}"))
}

/// The "checked ..." half of the update status row, or `None` when there is no
/// time to show.
///
/// `checked_at` is `update.rs`'s `"YYYY-MM-DD HH:MM"` local stamp. Today's
/// stamp is the bare time ("checked 14:32"); any older one keeps its date,
/// because "checked 14:32" on a check from last week would read as today.
/// `today` is the OS's own local date at drawing time - `None` when the clock
/// cannot be read, in which case the full stamp is printed rather than a
/// guessed "today".
fn checked_words(checked_at: &str, today: Option<&str>) -> Option<String> {
    let stamp = checked_at.trim();
    if stamp.is_empty() {
        return None;
    }
    let (day, time) = stamp.split_once(' ').unwrap_or(("", stamp));
    if !day.is_empty() && Some(day) == today {
        return Some(time.to_string());
    }
    Some(stamp.to_string())
}

/// Why a check could not answer, in a few words - the tray row is a glance, not
/// the card. The full sentence is Settings -> Updates' (`Status::error`), and
/// this never invents one: each arm names a failure `update.rs` really produces,
/// and the fallback still says it failed.
///
/// A build with no update key is checked FIRST, from the status itself: it never
/// asked anything, so its `error` may be empty and the reason is the build.
fn cannot_check_why(status: &crate::update::Status) -> &'static str {
    if !status.supported {
        return "this build has no update key";
    }
    let error = status.error.as_deref().unwrap_or("");
    let lower = error.to_lowercase();
    if lower.contains("no update key") {
        return "this build has no update key";
    }
    if lower.contains("no releases") || lower.contains("404") || lower.contains("not found") {
        return "no releases are published yet";
    }
    if lower.contains("could not reach")
        || lower.contains("connect")
        || lower.contains("dns")
        || lower.contains("timed out")
    {
        return "the release page could not be reached";
    }
    if lower.contains("signature") {
        return "a release failed its signature check";
    }
    if lower.contains("updater could not start") {
        return "the updater could not start";
    }
    "the check failed"
}

/// What the always-present update status row says, from `update.rs`'s
/// four-state truth. Pure, so the whole rule is a test without an app.
///
/// `None` is the fresh-launch case: the tray is built before the startup check
/// answers, and "Not checked yet" is the only thing true then. It is also what
/// an unrecognised future state draws, because a state this build does not know
/// is not a licence to say "up to date".
fn update_state_row(status: Option<&crate::update::Status>, today: Option<&str>) -> String {
    let Some(status) = status else {
        return "Not checked yet".to_string();
    };
    let at = status
        .checked_at
        .as_deref()
        .and_then(|stamp| checked_words(stamp, today));
    let checked = |base: &str| match &at {
        Some(at) => format!("{base} · checked {at}"),
        None => base.to_string(),
    };
    match status.state.as_str() {
        "update_available" => checked("Update available"),
        "up_to_date" => checked("Up to date"),
        "cannot_check" => {
            let why = cannot_check_why(status);
            match &at {
                Some(at) => format!("Cannot check · {why} · checked {at}"),
                None => format!("Cannot check · {why}"),
            }
        }
        _ => "Not checked yet".to_string(),
    }
}

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
    // backend/power-mode.patch. One item per mode; the server decides, and
    // the Power row above follows its event, not these clicks.
    let power_modes = Submenu::with_items(
        app,
        "Change power mode",
        true,
        &[
            &MenuItem::with_id(
                app,
                ID_POWER_ACTIVE,
                "Active — answers, and may speak first",
                true,
                None::<&str>,
            )?,
            &MenuItem::with_id(
                app,
                ID_POWER_QUIET,
                "Quiet — answers, starts nothing itself",
                true,
                None::<&str>,
            )?,
            &MenuItem::with_id(
                app,
                ID_POWER_STANDBY,
                "Standby — frees the graphics card",
                true,
                None::<&str>,
            )?,
        ],
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
    // "Stop everything" (continuity audit 2026-09-26): the same as the
    // hotkey (`commands::stop_everything_now`), for a mouse, or when another
    // program holds the key. Never greyed: not by a stale link, App lock or
    // a waiting card - it only makes Atlas stop.
    let stop_everything = MenuItem::with_id(
        app,
        ID_STOP_EVERYTHING,
        "Stop everything",
        true,
        accel(app, "stop_everything").as_deref(),
    )?;

    // Atlas Live: never greyed - starting is refused with a reason (a stale
    // link, App lock, no voice print), and ending always works. Both rows print
    // their hotkey when the owner has set one: the tray is where most people
    // learn a key exists (see the shield icon's own note), and these two shipped
    // unbound, so the row said nothing at all about them.
    let live = MenuItem::with_id(
        app,
        ID_LIVE,
        live_label(),
        true,
        accel(app, "toggle_live").as_deref(),
    )?;
    let watch = MenuItem::with_id(
        app,
        ID_WATCH,
        watch_label(),
        true,
        accel(app, "toggle_watch").as_deref(),
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

    let show_hud = MenuItem::with_id(app, ID_SHOW_HUD, "Show the HUD window", true, None::<&str>)?;
    let show_brain = MenuItem::with_id(app, ID_SHOW_BRAIN, "Open the Brain", true, None::<&str>)?;
    let chat_history =
        MenuItem::with_id(app, ID_CHAT_HISTORY, "Chat history…", true, None::<&str>)?;
    let new_chat_window = MenuItem::with_id(
        app,
        ID_NEW_CHAT_WINDOW,
        "New chat window",
        true,
        None::<&str>,
    )?;
    let show_faces = MenuItem::with_id(app, ID_SHOW_FACES, "Faces…", true, None::<&str>)?;
    // The whole feature set in one window (2026-10-08). It used to sit in the
    // windows group beside Faces, needing no separator of its own; the tray
    // trim moved it into the "More…" submenu, which is why `ia.mjs` now counts
    // four separators for the five top-level groups rather than five for six.
    let show_features = MenuItem::with_id(
        app,
        ID_SHOW_FEATURES,
        "Everything Atlas can do…",
        true,
        None::<&str>,
    )?;
    let toggle_spotlight = MenuItem::with_id(
        app,
        ID_TOGGLE_SPOTLIGHT,
        "Show or hide the Atlas bar",
        true,
        // Read, not hardcoded. The tray is the fallback surface for exactly
        // the case where a hotkey was refused or rebound, so a tray that
        // advertises "Alt+Space" after PowerToys took it is pointing the owner
        // at the one key that cannot work.
        accel(app, "toggle_quickbar").as_deref(),
    )?;
    let toggle_widget = MenuItem::with_id(
        app,
        ID_TOGGLE_WIDGET,
        "Show or hide the widget",
        true,
        accel(app, "toggle_widget").as_deref(),
    )?;
    let toggle_floating = MenuItem::with_id(
        app,
        ID_TOGGLE_FLOATING,
        "Show or hide the floating face",
        true,
        accel(app, "toggle_floating").as_deref(),
    )?;
    // The face's size cycle, next to its on/off row (2026-10-30). Plain rows,
    // not a submenu and not a Settings toggle: a Settings toggle means a new
    // row in backend/jarvis_settings_registry.py and both contract fixtures,
    // and this is a desktop-only cosmetic choice the owner asked to be able to
    // feel. Each click resizes the face at once (and the choice is remembered).
    let floating_bigger = MenuItem::with_id(
        app,
        ID_FLOATING_BIGGER,
        "Floating face: bigger",
        true,
        None::<&str>,
    )?;
    let floating_smaller = MenuItem::with_id(
        app,
        ID_FLOATING_SMALLER,
        "Floating face: smaller",
        true,
        None::<&str>,
    )?;
    let reconnect = MenuItem::with_id(
        app,
        ID_RECONNECT,
        "Reconnect the event stream",
        true,
        None::<&str>,
    )?;
    // The update row (owner, 2026-11-03): it is BUILT like any other row but
    // only parented into "More…" when a check has already found something - the
    // fresh launch has no answer yet, so it starts absent and a later check puts
    // it in. `on_update_status` is the one place that adds and removes it, and
    // it must be THIS handle: a second `MenuItem` with the same id would look
    // right on screen and then never re-label.
    let available = crate::update::available_version(app);
    let update_label = update_row(available.as_deref());
    let update = MenuItem::with_id(
        app,
        ID_UPDATE,
        // Never shown when there is no update; this is only the handle's
        // starting text.
        update_label
            .clone()
            .unwrap_or_else(|| "Update Atlas".to_string()),
        true,
        None::<&str>,
    )?;
    // The update REPORT row (Task-50, Wave 12). Built disabled on purpose: it
    // reports, it does not act (`tray-rows.mjs` holds it to that). Its text is
    // the four-state truth from the cache `update.rs` already keeps; at this
    // point no check has run, so it says "Not checked yet" and the startup
    // check re-labels it when it answers.
    let update_state = MenuItem::with_id(
        app,
        ID_UPDATE_STATE,
        update_state_row(
            Some(&crate::update::last_status(app)),
            crate::update::local_day().as_deref(),
        ),
        false,
        None::<&str>,
    )?;
    // The "Personalize Atlas" row (Wave B, 2026-11-03). Built like any other
    // row and parented into "More…" only while the quiz is unfinished - at a
    // fresh launch the state has not been read yet, so it starts absent and
    // `on_setup_state` puts it in when a read says so. The same handle is
    // re-labelled in place as the count moves.
    let setup_state = app
        .state::<crate::setup_offer::SetupOfferState>()
        .snapshot();
    let setup_label = setup_state.tray_label();
    let setup = MenuItem::with_id(
        app,
        ID_SETUP,
        // Never shown when the quiz is finished; this is only the handle's
        // starting text.
        setup_label
            .clone()
            .unwrap_or_else(|| "Setup unfinished".to_string()),
        true,
        None::<&str>,
    )?;
    let settings = MenuItem::with_id(app, ID_SETTINGS, "Settings and help…", true, None::<&str>)?;
    let status_check = MenuItem::with_id(
        app,
        ID_STATUS_CHECK,
        "Run a status check",
        true,
        None::<&str>,
    )?;
    let quit = MenuItem::with_id(app, ID_QUIT, "Quit Atlas", true, None::<&str>)?;

    // The one submenu the tray trim added (the owner: the menu had "way too
    // many options ... only put the most important ones, it should be half this
    // size at most"). Everything still reachable but not wanted every day moved
    // one click in here, so nothing became unreachable.
    //
    // These are the SAME `MenuItem`s built above, moved - never rebuilt. Each
    // one is still held by `Rows` and still re-labelled in place as the state
    // moves (`waiting`'s count and enabled state, `watch`'s Start/Stop wording,
    // `backend`'s pid and supervision line, `update`'s version, and the hotkey
    // rebinds for `toggle_widget`/`toggle_floating`/`watch`). A second item
    // with the same id would look right on screen and then go stale, and no
    // test could see it. `rows.*` is the only other reference to them, so
    // moving a row into here costs nothing.
    //
    // `update` is LAST on purpose: `on_update_status` puts it back with
    // `append` after a check finds a new version again, and a last row needs no
    // index that a later addition would silently shift.
    let mut more_items: Vec<&dyn IsMenuItem<tauri::Wry>> = vec![
        &waiting,
        &watch,
        &toggle_widget,
        &toggle_floating,
        &floating_bigger,
        &floating_smaller,
        // 2aa9c6492 (F6 desktop): a second conversation window, first among
        // the destinations because it is the everyday one.
        &new_chat_window,
        &chat_history,
        &show_faces,
        &show_features,
        &backend,
        &reconnect,
        &status_check,
        // The update REPORT row sits beside the status check, before the rows
        // that appear and disappear: it is always there, and what it says is
        // the four-state truth about updates (Task-50).
        &update_state,
    ];
    // The quiz row sits after the status check and before the update row: both
    // are "state moved, so the row appeared" rows that `on_*` appends when it
    // has something to say, and a last row needs no index that a later addition
    // would silently shift.
    if setup_label.is_some() {
        more_items.push(&setup);
    }
    if update_label.is_some() {
        more_items.push(&update);
    }
    let more = Submenu::with_items(app, "More…", true, &more_items)?;

    // Five groups, four separators. `ia.mjs` counts the separators in this
    // slice and would fail if a row were added back at the top level, so the
    // menu cannot quietly grow past the owner's "half this size" without a
    // deliberate edit to the test's own expectation.
    let menu = Menu::with_items(
        app,
        &[
            // What Atlas is. Both rows are disabled: they report, they do
            // not offer.
            &activity,
            &power,
            &power_modes,
            &PredefinedMenuItem::separator(app)?,
            // What is waiting on you, and your control over being interrupted.
            // `mute` belongs here rather than among the machinery: it is the
            // answer to the two rows above it.
            &approvals,
            &mute,
            &stop_everything,
            &PredefinedMenuItem::separator(app)?,
            // Atlas Live on its own line, away from "Stop everything" (the
            // review of 2026-09-28: a click one row off started or ended it).
            &live,
            &PredefinedMenuItem::separator(app)?,
            // Windows and the two ways on from them, everyday ones first - the
            // row with a hotkey is the one reached most often, and a hotkey
            // printed beside a row is how the owner learns it exists. Settings
            // ends the block, and "More…" is the submenu holding every
            // destination and every under-the-hood row that is not wanted
            // every day.
            &toggle_spotlight,
            &show_hud,
            &show_brain,
            &settings,
            &more,
            &PredefinedMenuItem::separator(app)?,
            // Quit last, on its own, as it always was: it is the one row that
            // ends the session, so it stays visibly apart from its neighbours.
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
            live,
            watch,
            backend,
            update,
            update_state,
            setup,
            more,
            stop_everything,
            toggle_spotlight,
            toggle_widget,
            toggle_floating,
        });

    let mut builder = TrayIconBuilder::with_id(TRAY_ID)
        .tooltip(tooltip(app, &link))
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

    if let Some(icon) = render_icon(app, &link) {
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
///   falls to `thinking`, the nearest bound state — Atlas is busy and not
///   talking. Bind a `working` state in the spec and this line stops guessing.
/// * **`quiet` has no binding either.** The spec has `standby` but no `quiet`,
///   so a hand-set Quiet shows the `standby` colour, and only while nothing is
///   actually happening: if Atlas is mid-turn the activity colour wins,
///   because that is the question the spec binds colour to.
///
/// Precedence, highest first: an error, then anything waiting on the human,
/// then what Atlas is doing, then whether it is awake at all. Approvals sit
/// above activity deliberately — a tray icon exists to be glanced at, and the
/// only thing on this bus that needs the human is an approval.
fn spec_state(link: &LinkState) -> &'static str {
    // Not connected: asleep, whatever the last activity was - the icon is
    // hollow as well (`draw`), which is what says "not connected". The
    // owner's rule (2026-09-28) for every face surface, and the faces'
    // own (jarvis-link.js surfaceState): the stream keeps the last activity
    // it heard when it drops, so without this the hollow icon could stay in
    // the colour of "speaking" or "waiting on you" for as long as Atlas
    // was gone.
    if !link.connected {
        return "standby";
    }
    if link.activity == "error" {
        return "error";
    }
    // Never the approval colour while acting is blocked (rule 4): while the
    // link is stale nobody can approve from this PC (jarvis-link.js
    // `decide` refuses), so an icon asking for a decision would be a promise
    // the buttons break. The faces follow the same rule.
    if link.approvals > 0 && !link.stale {
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
    //
    // One exception (owner, 2026-09-29): a focus session puts Atlas on Quiet,
    // and the animal then shows its focus buddy, awake and working beside the
    // owner - so the icon reads "idle", the same as the faces
    // (jarvis-link.js surfaceState). Only that Quiet: a Quiet the owner set by
    // hand, and standby of any kind, still read as asleep.
    match link.power.as_str() {
        "quiet" if link.power_set_by.as_deref() == Some("focus") => "idle",
        "standby" | "quiet" => "standby",
        _ => "idle",
    }
}

/// The state the icon shows: [`spec_state`], except that while talk-to-type
/// holds the microphone (talk_type.rs) it shows `listening` - the one sign,
/// always on screen, that this PC is recording. It is a local fact the
/// server's stream cannot know, so it wins over everything the stream says.
fn shown_state(link: &LinkState) -> &'static str {
    if crate::talk_type::listening() {
        "listening"
    } else {
        spec_state(link)
    }
}

/// Repaints now, from the current link (talk-to-type started or stopped).
pub fn refresh(app: &AppHandle) {
    let link = app.state::<crate::stream::StreamState>().link();
    repaint(app, &link);
}

fn binding_for(app: &AppHandle, link: &LinkState) -> Binding {
    let id = shown_state(link);
    // The owner's choice first, the spec's default second. This used to read
    // the spec alone, which meant the Faces window edited a document the tray
    // never looked at: you could rebind `idle`, press save, be told it was
    // saved, and watch the icon carry on exactly as before.
    app.state::<crate::appearance::AppearanceState>()
        .binding(id)
        .or_else(|| spec::state_binding(id))
        .or_else(|| spec::state_binding("idle"))
        .unwrap_or_default()
}

/// Repaints after the appearance document changes.
///
/// The colour cache in [`Painted`] is keyed on the resolved colour, so a
/// rebind that happens to resolve to the same 8-bit value is correctly a
/// no-op; anything else redraws on the next call.
pub fn on_appearance_changed(app: &AppHandle) {
    // Drop the cached colour first. The key cannot see a binding change that
    // resolves to the same colour *right now* but animates differently, and
    // `repaint` would take the early return.
    let painted = app.state::<Painted>();
    painted
        .0
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .take();
    let link = app.state::<crate::stream::StreamState>().link();
    repaint(app, &link);
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
/// without claiming to know what Atlas is doing.
fn render_icon(app: &AppHandle, link: &LinkState) -> Option<Image<'static>> {
    let resolved = governed_resolve(app, link);
    Some(paint(link, resolved))
}

/// Resolves through this module's one [`TrayFlashGovernor`]. The only path to
/// a colour here, the same way `resolve()` is the spec's only path to one —
/// so nothing in this file can bypass the flash governor by calling
/// `spec::resolve` directly.
fn governed_resolve(app: &AppHandle, link: &LinkState) -> spec::Resolved {
    let binding = binding_for(app, link);
    // The same value twice, on purpose: `clock()` here is real elapsed time
    // and nothing scales it, so the tray's animation clock and the governor's
    // one-second window are the same clock. See FlashGovernor::resolve's doc
    // for why they are separate parameters at all.
    let t = clock();
    app.state::<TrayFlashGovernor>()
        .0
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .resolve(&binding, t, 0.0, 0.0, t)
}

/// Draws the already-resolved colour, dim and notches included.
///
/// Takes `resolved` rather than resolving itself so the governor sees each
/// repaint exactly once — see [`governed_resolve`].
fn paint(link: &LinkState, resolved: spec::Resolved) -> Image<'static> {
    let state = shown_state(link);
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
    let mut pixels = draw_pixels(a, b, filled, notches);
    if crate::live::on_here() {
        mark_live(&mut pixels);
    }
    if crate::look::on_here() {
        mark_watching(&mut pixels);
    }
    Image::new_owned(pixels, ICON_SIZE, ICON_SIZE)
}

/// Atlas Live's colour on the icon: the sign's red dot (theme.css `--bad`
/// in the default theme), with a white ring so it reads on a dark taskbar
/// and a light one alike.
const LIVE_DOT: Rgb = Rgb {
    r: 0xE5,
    g: 0x48,
    b: 0x4D,
};

/// Paints Atlas Live's mark - a small red dot with a light ring - over the
/// lower-right of the icon, while Live is on on this PC. Over whatever the
/// disc drew there: the mark is what says the microphone is open.
fn mark_live(pixels: &mut [u8]) {
    let size = ICON_SIZE as f64;
    let (cx, cy) = (size - 7.0, size - 7.0);
    let dot = 5.0f64;
    let ring = 6.6f64;
    for y in 0..ICON_SIZE {
        for x in 0..ICON_SIZE {
            let mut in_dot = 0.0f64;
            let mut in_ring = 0.0f64;
            for sy in 0..3 {
                for sx in 0..3 {
                    let px = x as f64 + (sx as f64 + 0.5) / 3.0;
                    let py = y as f64 + (sy as f64 + 0.5) / 3.0;
                    let d = ((px - cx).powi(2) + (py - cy).powi(2)).sqrt();
                    if d <= dot {
                        in_dot += 1.0 / 9.0;
                    } else if d <= ring {
                        in_ring += 1.0 / 9.0;
                    }
                }
            }
            if in_dot <= 0.0 && in_ring <= 0.0 {
                continue;
            }
            let at = ((y * ICON_SIZE + x) * 4) as usize;
            let cover = (in_dot + in_ring).clamp(0.0, 1.0);
            let mix = |old: u8, dot_c: u8| {
                let ring_c = 255.0;
                let want = if in_dot + in_ring > 0.0 {
                    (f64::from(dot_c) * in_dot + ring_c * in_ring) / (in_dot + in_ring)
                } else {
                    f64::from(old)
                };
                (f64::from(old) * (1.0 - cover) + want * cover)
                    .round()
                    .clamp(0.0, 255.0) as u8
            };
            pixels[at] = mix(pixels[at], LIVE_DOT.r);
            pixels[at + 1] = mix(pixels[at + 1], LIVE_DOT.g);
            pixels[at + 2] = mix(pixels[at + 2], LIVE_DOT.b);
            let alpha = f64::from(pixels[at + 3]);
            pixels[at + 3] = (alpha + (255.0 - alpha) * cover).round().clamp(0.0, 255.0) as u8;
        }
    }
}

/// Watch with me's mark on the icon: a small light "eye" (a ring with a dark
/// pupil) in the upper right - "the eye on the tray icon" of the design - so
/// the sign that Atlas is watching is there whatever window is in front.
fn mark_watching(pixels: &mut [u8]) {
    let size = ICON_SIZE as f64;
    let (cx, cy) = (size - 7.0, 7.0);
    let ring = 6.4f64;
    let pupil = 2.4f64;
    for y in 0..ICON_SIZE {
        for x in 0..ICON_SIZE {
            let mut white = 0.0f64;
            let mut dark = 0.0f64;
            for sy in 0..3 {
                for sx in 0..3 {
                    let px = x as f64 + (sx as f64 + 0.5) / 3.0;
                    let py = y as f64 + (sy as f64 + 0.5) / 3.0;
                    let d = ((px - cx).powi(2) + (py - cy).powi(2)).sqrt();
                    if d <= pupil {
                        dark += 1.0 / 9.0;
                    } else if d <= ring {
                        white += 1.0 / 9.0;
                    }
                }
            }
            let cover = (white + dark).clamp(0.0, 1.0);
            if cover <= 0.0 {
                continue;
            }
            let at = ((y * ICON_SIZE + x) * 4) as usize;
            let mix = |old: u8, light: f64, ink: f64| {
                let want = (light * white + ink * dark) / (white + dark);
                (f64::from(old) * (1.0 - cover) + want * cover)
                    .round()
                    .clamp(0.0, 255.0) as u8
            };
            pixels[at] = mix(pixels[at], 236.0, f64::from(INK_DARK.r));
            pixels[at + 1] = mix(pixels[at + 1], 240.0, f64::from(INK_DARK.g));
            pixels[at + 2] = mix(pixels[at + 2], 245.0, f64::from(INK_DARK.b));
            let alpha = f64::from(pixels[at + 3]);
            pixels[at + 3] = (alpha + (255.0 - alpha) * cover).round().clamp(0.0, 255.0) as u8;
        }
    }
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
            if !spec::is_animated(&binding_for(&app, &link)) {
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
    let state = shown_state(link);
    let resolved = governed_resolve(app, link);
    {
        let painted = app.state::<Painted>();
        let mut slot = painted
            .0
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        // The notch count is part of the key. Keying on the colour alone meant
        // a fourth item arriving while banked — same still colour, one more
        // notch — was skipped as an unchanged frame, so the ring never grew.
        // `resolved.b` is in the key because `draw` uses it for the rim: a
        // rebind that lands on the same primary but a different secondary
        // repainted nothing and kept the old edge.
        // Atlas Live on this PC adds its mark (the design's "a Live mark on
        // the tray icon", missing until the review of 2026-09-28).
        let key = (
            resolved.a,
            resolved.b,
            link.attention.pending,
            state,
            crate::live::on_here(),
            crate::look::on_here(),
        );
        if *slot == Some(key) {
            return;
        }
        *slot = Some(key);
    }
    if let Err(err) = tray.set_icon(Some(paint(link, resolved))) {
        eprintln!("[jarvis] tray: unable to set the icon: {err}");
    }
    if let Err(err) = tray.set_tooltip(Some(tooltip(app, link))) {
        eprintln!("[jarvis] tray: unable to set the tooltip: {err}");
    }
}

// ---------------------------------------------------------------------------
// Labels
// ---------------------------------------------------------------------------

fn activity_label(link: &LinkState) -> String {
    if !link.connected {
        return match &link.error {
            Some(err) => format!("Atlas — offline: {}", first_sentence(err)),
            None => "Atlas — connecting…".to_string(),
        };
    }
    // Connected but stale: the stream is up and `/api/pending` could not be
    // read, so the activity below is last known, not current. The phone says
    // "Stale — reconnecting" in amber for exactly this; the tray used to say
    // "idle" as though nothing were wrong.
    if link.stale {
        return "Atlas — stale, reconnecting".to_string();
    }
    match link.activity.as_str() {
        "idle" => "Atlas — idle".to_string(),
        other => format!("Atlas — {other}"),
    }
}

fn power_label(link: &LinkState) -> String {
    // `set_by` is "override" when a human set the mode, and schedule / idle /
    // auto when the machine did. Saying which matters: JARVIS-API §4 warns that
    // talking to Atlas clears the second kind of Quiet and not the first.
    let by = match link.power_set_by.as_deref() {
        Some("override") => " · set by hand",
        Some("schedule") => " · quiet hours",
        Some("idle") => " · idle timer",
        Some("standby_schedule") => " · standby schedule",
        Some("focus") => " · focus session",
        _ => "",
    };
    // The "· read-only" that used to end this row is gone: the submenu
    // below it sets the mode now (backend/power-mode.patch).
    format!("Power: {}{by}", link.power)
}

fn approvals_label(link: &LinkState) -> String {
    match link.approvals {
        0 if link.stale && !link.connected => "Approvals: unknown while offline".to_string(),
        // "offline" was the wrong word here: the stream is connected, it is
        // the queue that could not be confirmed.
        0 if link.stale => "Approvals: unknown until the link catches up".to_string(),
        1 if link.stale => "1 approval waiting (last known)".to_string(),
        n if link.stale => format!("{n} approvals waiting (last known)"),
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
    let body = match link.attention.blocked_by.as_deref() {
        Some(reason) if link.attention.pending > 0 => format!("{head} · {reason}"),
        _ if link.attention.pending > 0 => format!(
            "{head} · {} of {} interruptions left",
            link.attention.remaining, link.attention.limit
        ),
        _ => head,
    };
    // `digest_due` was read off `/api/attention` into `Attention` and never
    // looked at again anywhere in this client - the field computed
    // server-side specifically to say "it is time for the daily brief" had
    // no effect on anything the owner could see. This does not invent a new
    // proactive notification for it (this struct is only refreshed on
    // connect, resume and after a mute - "poll only on resume" is this
    // module's own stated design, and a timely alert would need an actual
    // periodic check, which is a bigger decision than this one line). What
    // it does is stop the flag being silently dropped on every occasion the
    // client already happens to be looking: if there is something to tell
    // AND the server says it is due, the row says so.
    if link.attention.digest_due && link.attention.pending > 0 {
        format!("{body} · today's brief is ready")
    } else {
        body
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

/// The Live row's words: what clicking it does.
fn live_label() -> &'static str {
    if crate::live::on_here() {
        "End Atlas Live"
    } else {
        "Start Atlas Live"
    }
}

/// The Watch with me row's words: what clicking it does.
fn watch_label() -> &'static str {
    if crate::look::on_here() {
        "Stop Watch with me"
    } else {
        "Start Watch with me"
    }
}

/// Watch with me started or ended here: the row, the tooltip and the icon's
/// eye follow.
pub fn watch_changed(app: &AppHandle) {
    if let Some(rows) = app
        .state::<TrayHandles>()
        .inner
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .as_ref()
    {
        let _ = rows.watch.set_text(watch_label());
    }
    if let Some(tray) = app.tray_by_id(TRAY_ID) {
        let link = app.state::<crate::stream::StreamState>().link();
        let _ = tray.set_tooltip(Some(tooltip(app, &link)));
        repaint(app, &link);
    }
}

/// Atlas Live started or ended here: the row, the tooltip and the icon's
/// Live mark follow.
pub fn live_changed(app: &AppHandle) {
    if let Some(rows) = app
        .state::<TrayHandles>()
        .inner
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .as_ref()
    {
        let _ = rows.live.set_text(live_label());
    }
    if let Some(tray) = app.tray_by_id(TRAY_ID) {
        let link = app.state::<crate::stream::StreamState>().link();
        let _ = tray.set_tooltip(Some(tooltip(app, &link)));
        repaint(app, &link);
    }
}

fn tooltip(app: &AppHandle, link: &LinkState) -> String {
    let mut parts = vec![if crate::talk_type::listening() {
        crate::talk_type::TRAY_LISTENING.to_string()
    } else {
        activity_label(link)
    }];
    if crate::live::on_here() {
        parts.push("Atlas Live is on".to_string());
    }
    if crate::look::on_here() {
        parts.push("Atlas is watching your screen".to_string());
    }
    // Not while stale: power, approvals and the brief would be last-known
    // facts presented as current ones - the phone drops the same extras.
    if link.connected && !link.stale {
        parts.push(power_label(link));
        let locked = crate::lock::locked_now(app) || crate::lock::app_locked(app);
        if !locked {
            if link.approvals > 0 {
                parts.push(approvals_label(link));
            }
            if link.attention.pending > 0 {
                parts.push(waiting_label(link));
            }
        }
    }
    if let Some(a) = accel(app, "toggle_quickbar") {
        parts.push(a);
    }
    parts.join(" · ")
}

/// Trims a long error down to something a menu row can hold.
/// The accelerator actually bound to an action, or None if the OS refused it.
///
/// None is the honest answer: a menu row with no accelerator beside it is
/// correct when there is no key that triggers it, and better than a row
/// promising one that does nothing.
fn accel(app: &AppHandle, id: &str) -> Option<String> {
    let bound = crate::hotkeys::configured(app);
    bound.get(id).cloned().filter(|s| !s.trim().is_empty())
}

/// Re-labels every tray row that prints a hotkey, after one is set or reset.
/// The menu is built ONCE, so without this a row kept showing the key the owner
/// had just replaced for the rest of the session - while the hover tooltip,
/// which IS rebuilt live (`tooltip()`, called from `repaint()`), showed the new
/// one. The comment on `toggle_spotlight` says why that row exists at all: a
/// tray advertising "Alt+Space" after PowerToys took it points the owner at the
/// one key that cannot work.
///
/// Called from the two hotkey commands, deferred to the event loop
/// (`hotkeys::relabel_tray`) - NOT from `apply()`, which also runs during setup
/// where touching the native menu hangs the main thread. A missing tray is
/// simply left alone; at startup the rows are built with their keys already.
pub fn hotkeys_changed(app: &AppHandle) {
    let handles = app.state::<TrayHandles>();
    let guard = handles
        .inner
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    let Some(rows) = guard.as_ref() else {
        return; // no tray was built (startup, or create_tray failed)
    };
    // What the OS actually ACCEPTED, from the state `apply()` has just written:
    // a row must never print a key that was refused, or it points the owner at
    // the one key that cannot work. That is not hypothetical - this PC's
    // Alt+Space is held by another program, and the Atlas bar's row said
    // "Alt+Space" while the key was refused (2026-10-08).
    let applied = app.state::<crate::hotkeys::HotkeyState>().snapshot();
    let registered = |id: &str| applied.iter().find(|b| b.id == id).map(|b| b.registered);
    for (id, item) in [
        ("stop_everything", &rows.stop_everything),
        ("toggle_quickbar", &rows.toggle_spotlight),
        ("toggle_widget", &rows.toggle_widget),
        ("toggle_floating", &rows.toggle_floating),
        ("toggle_live", &rows.live),
        ("toggle_watch", &rows.watch),
    ] {
        let key = match registered(id) {
            Some(false) => None, // refused by the OS: print nothing at all
            _ => accel(app, id),
        };
        if let Err(err) = item.set_accelerator(key.as_deref()) {
            eprintln!("[jarvis] tray: could not re-label the row for {id}: {err}");
        }
    }
}

fn first_sentence(text: &str) -> String {
    let text = text.trim();
    // A full stop only ends a sentence when whitespace or the end follows it.
    // Without that test the first offline message the owner ever sees - "could
    // not reach the Jarvis server at http://127.0.0.1:4719. Is it running?" -
    // was cut at the dot inside the address, and the tray read, literally,
    // "Jarvis - offline: could not reach the Jarvis server at http://127".
    // The 403 message lost the half that names JARVIS_HUD_ORIGINS, which is
    // the actual fix, for the same reason.
    let bytes = text.as_bytes();
    let ends_here = |i: usize| -> bool {
        match bytes.get(i + 1) {
            None => true,
            Some(b) => b.is_ascii_whitespace(),
        }
    };
    let cut = text
        .char_indices()
        .find(|(i, c)| (*c == '.' || *c == ';') && ends_here(*i))
        .map(|(i, _)| i + 1)
        .unwrap_or(text.len());
    let mut out = text[..cut].trim_end_matches(['.', ';']).to_string();
    if out.chars().count() > 60 {
        out = out.chars().take(57).collect::<String>() + "…";
    }
    out
}

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------

/// Re-labels the update REPORT row and adds, re-labels or removes the update
/// ACTION row. Called by `update.rs` when a check answers, and by nothing else.
///
/// Two rows, two jobs:
///
/// * `ID_UPDATE_STATE` is the REPORT (Task-50, Wave 12). It is always in the
///   menu and always disabled, and it says one of four things from
///   `update.rs`'s own `Status::state` - [`update_state_row`] is that whole
///   rule. It is re-labelled on every answer, so the time beside "up to date"
///   is the check's own.
/// * `ID_UPDATE` is the ACTION, and its rule is [`update_row`]: no update means
///   the row is not in the menu at all. It is added to "More…" (`append`,
///   because it is that submenu's last row) and removed from it rather than
///   disabled, because a greyed row saying "Jarvis Desktop 0.2.0" is the shape
///   the owner asked to be rid of (2026-11-03).
///
/// Pressing the action row starts the SAME both-halves update the Settings
/// Install press starts (`update::install_from_tray`); this function only
/// decides whether the row exists and what both rows say.
pub fn on_update_status(app: &AppHandle, status: &crate::update::Status) {
    let label = update_row(status.available.as_deref());
    let state_label = update_state_row(Some(status), crate::update::local_day().as_deref());
    if let Some(rows) = app
        .state::<TrayHandles>()
        .inner
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .as_ref()
    {
        // The report row is always there, so it is only ever re-labelled - a
        // failure here is said and nothing else changes.
        if let Err(err) = rows.update_state.set_text(state_label) {
            eprintln!("[jarvis] tray: could not re-label the update status row: {err}");
        }
        match label {
            Some(label) => {
                // Re-label even when the row is already there: the version moves
                // from one release to the next, and the label names it.
                if let Err(err) = rows.update.set_text(label) {
                    eprintln!("[jarvis] tray: could not re-label the update row: {err}");
                }
                // And ENABLE it: a failed press left the row disabled on
                // "Updating…", and the re-check that follows a failure finds the
                // release still there. Without this the owner could never press
                // it again.
                let _ = rows.update.set_enabled(true);
                if rows.more.get(ID_UPDATE).is_none() {
                    if let Err(err) = rows.more.append(&rows.update) {
                        eprintln!("[jarvis] tray: could not show the update row: {err}");
                    }
                }
            }
            None => {
                if rows.more.get(ID_UPDATE).is_some() {
                    if let Err(err) = rows.more.remove(&rows.update) {
                        eprintln!("[jarvis] tray: could not remove the update row: {err}");
                    }
                }
            }
        }
    }
}

/// One press is under way: the row stays - the update is still there - but says
/// what it is doing and cannot start a second download while the first runs.
pub fn update_started(app: &AppHandle, version: &str) {
    if let Some(rows) = app
        .state::<TrayHandles>()
        .inner
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .as_ref()
    {
        let _ = rows
            .update
            .set_text(format!("Updating Atlas to {version}…"));
        let _ = rows.update.set_enabled(false);
    }
}

/// Adds, re-labels or removes the "Setup unfinished" row (Wave B, 2026-11-03).
///
/// Called by `setup_offer::refresh_setup_state` when a read of the PC's own
/// questionnaire state really moved, and by nothing else. The rule is
/// [`crate::setup_offer::SetupState::tray_label`]: no unfinished quiz means the
/// row is not in the menu at all - a greyed row saying "Setup unfinished" is a
/// nag with no door. The row lives in "More…" (`append`, because it is that
/// submenu's last-but-one row) and is removed from it rather than disabled.
///
/// Pressing it opens Settings at the quiz card (`handle_menu_event`); this
/// function only decides whether the row exists and what it says. It changes no
/// setting and answers no question.
pub fn on_setup_state(app: &AppHandle) {
    let label = app
        .state::<crate::setup_offer::SetupOfferState>()
        .snapshot()
        .tray_label();
    if let Some(rows) = app
        .state::<TrayHandles>()
        .inner
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .as_ref()
    {
        match label {
            Some(label) => {
                if let Err(err) = rows.setup.set_text(label) {
                    eprintln!("[jarvis] tray: could not re-label the setup row: {err}");
                }
                // The count moves as questions are answered, so the row is
                // always enabled while it exists - there is always a door.
                let _ = rows.setup.set_enabled(true);
                if rows.more.get(ID_SETUP).is_none() {
                    if let Err(err) = rows.more.append(&rows.setup) {
                        eprintln!("[jarvis] tray: could not show the setup row: {err}");
                    }
                }
            }
            None => {
                if rows.more.get(ID_SETUP).is_some() {
                    if let Err(err) = rows.more.remove(&rows.setup) {
                        eprintln!("[jarvis] tray: could not remove the setup row: {err}");
                    }
                }
            }
        }
    }
}

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
        // `known`, NOT `pending > 0`. Both lines were here — the second
        // overwrote the first on every event, so the fix that made the brief
        // reachable at zero pending was reverted one line after it, and the
        // test caught nothing because it asserted the label and the mere
        // presence of a `set_enabled` call rather than the value.
        let _ = rows.waiting.set_enabled(link.attention.known);
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
                commands::notify_failed(
                    app,
                    "Atlas",
                    "The Atlas bar could not open.",
                    &err.to_string(),
                    commands::Details::Log,
                );
                return;
            }
            crate::emit_quickbar(app, events::SHOW_APPROVAL, ());
        }

        // Speech first, then the PC; a notification says what was stopped.
        ID_STOP_EVERYTHING => commands::stop_everything_now(app),

        // Start or end Atlas Live on this PC (live.rs).
        ID_LIVE => crate::live::toggle_from_tray(app),
        // Start or stop Watch with me on this PC (look.rs).
        ID_WATCH => crate::look::toggle_from_tray(app),

        ID_SHOW_HUD => {
            if let Err(err) = windows::show_hud(app) {
                eprintln!("[jarvis] tray: HUD unavailable: {err}");
                commands::notify_failed(
                    app,
                    "Atlas",
                    "The HUD could not open.",
                    &err.to_string(),
                    commands::Details::Log,
                );
            }
        }

        ID_SHOW_FACES => {
            if let Err(err) = windows::show_faces(app) {
                eprintln!("[jarvis] faces unavailable: {err}");
                commands::notify_failed(
                    app,
                    "Atlas",
                    "The faces window could not open.",
                    &err.to_string(),
                    commands::Details::Log,
                );
            }
        }

        ID_SHOW_FEATURES => {
            if let Err(err) = windows::show_features(app) {
                eprintln!("[jarvis] feature list unavailable: {err}");
                commands::notify_failed(
                    app,
                    "Atlas",
                    "The list of what Atlas can do could not open.",
                    &err.to_string(),
                    commands::Details::Log,
                );
            }
        }

        ID_SHOW_BRAIN => {
            if let Err(err) = windows::show_brain(app) {
                eprintln!("[jarvis] tray: the Brain would not open: {err}");
                commands::notify_failed(
                    app,
                    "Atlas",
                    "The Brain could not open.",
                    &err.to_string(),
                    commands::Details::Log,
                );
            }
        }

        ID_NEW_CHAT_WINDOW => {
            // A second conversation window (2026-11-03). Each one is its own
            // window and its own conversation; closing it never closes the
            // others. The window list, the per-conversation dedupe and the
            // label set live in chat_windows.rs.
            if let Err(err) = crate::chat_windows::open_for(app, None) {
                eprintln!("[jarvis] tray: a new chat window would not open: {err}");
                commands::notify_failed(
                    app,
                    "Atlas",
                    "A new chat window could not open.",
                    &err,
                    commands::Details::Log,
                );
            }
        }

        ID_CHAT_HISTORY => {
            if let Err(err) = windows::show_brain_at(app, "history") {
                eprintln!("[jarvis] tray: chat history would not open: {err}");
                commands::notify_failed(
                    app,
                    "Atlas",
                    "Chat history could not open.",
                    &err.to_string(),
                    commands::Details::Log,
                );
            }
        }

        // The menu row and the icon's own left click are the same toggle now,
        // and `toggle_quickbar` places the caret itself - no second
        // `emit_quickbar` here (2026-10-10).
        ID_TOGGLE_SPOTLIGHT => {
            if let Err(err) = windows::toggle_quickbar(app) {
                eprintln!("[jarvis] tray: quickbar toggle failed: {err}");
            }
        }

        ID_TOGGLE_WIDGET => {
            if let Err(err) = windows::toggle_widget(app) {
                eprintln!("[jarvis] tray: widget toggle failed: {err}");
            }
        }

        ID_TOGGLE_FLOATING => {
            if let Err(err) = windows::toggle_floating(app) {
                eprintln!("[jarvis] tray: floating face toggle failed: {err}");
            }
        }

        // The face's size cycle. Cosmetic, so it applies at once with no
        // approval card; if the face is closed the choice is still remembered
        // and shows the next time it opens.
        ID_FLOATING_BIGGER => {
            if let Err(err) = windows::step_floating_size(app, true) {
                eprintln!("[jarvis] tray: floating face could not grow: {err}");
            }
        }

        ID_FLOATING_SMALLER => {
            if let Err(err) = windows::step_floating_size(app, false) {
                eprintln!("[jarvis] tray: floating face could not shrink: {err}");
            }
        }

        // The brief is a list with consequence ranking and disclosures, not a
        // menu, so the row opens the surface that can render one. That is the
        // quickbar rather than the HUD: the HUD window loads the backend's own
        // `jarvis_hud.html`, which is not ours to add sections to.
        ID_WAITING => {
            if let Err(err) = windows::show_quickbar(app) {
                eprintln!("[jarvis] tray: quickbar unavailable: {err}");
                commands::notify_failed(
                    app,
                    "Atlas",
                    "The Atlas bar could not open.",
                    &err.to_string(),
                    commands::Details::Log,
                );
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
                    commands::notify_failed(
                        &app,
                        "Atlas",
                        "Mute could not be changed.",
                        &err,
                        commands::Details::Log,
                    );
                }
            });
        }

        ID_POWER_ACTIVE | ID_POWER_QUIET | ID_POWER_STANDBY => {
            let mode = match event.id().as_ref() {
                ID_POWER_ACTIVE => "active",
                ID_POWER_QUIET => "quiet",
                _ => "standby",
            };
            let app = app.clone();
            tauri::async_runtime::spawn(async move {
                match commands::set_power_mode(&app, mode).await {
                    Ok(message) => commands::notify(&app, "Atlas", &first_sentence(&message)),
                    Err(err) => {
                        eprintln!("[jarvis] tray: power mode failed: {err}");
                        commands::notify_failed(
                            &app,
                            "Atlas",
                            "The power mode could not be changed.",
                            &err,
                            commands::Details::Log,
                        );
                    }
                }
            });
        }

        ID_BACKEND => run_backend_action(app),

        // The row exists only while a newer version is known (`on_update_status`
        // adds it, `update_row` is the rule), and pressing it updates BOTH
        // halves - the backend first, then Jarvis Desktop - through the same
        // runner the Settings Install press and an answered chat card use. The
        // desktop-only `install_update` is reached only where the backend half
        // cannot run at all, and then the toast says the BACKEND was NOT
        // updated. Never a second updater and never anything automatic.
        //
        // Spawned, not awaited: this handler already runs on the main thread,
        // and the press re-labels the row - menu work is POSTED to the main
        // thread, so doing it inline here would deadlock on itself.
        ID_UPDATE => run_update_from_tray(app),

        // "Settings and help…" stays plain Settings. The Updates card is still
        // reachable from it (and from Settings search and every other surface
        // that names it); the tray's own row no longer goes there, because it
        // now does the install the owner asked it to do.
        ID_SETTINGS => {
            if let Err(err) = windows::show_settings(app) {
                eprintln!("[jarvis] tray: settings unavailable: {err}");
                commands::notify_failed(
                    app,
                    "Atlas",
                    "Settings could not open.",
                    &err.to_string(),
                    commands::Details::Log,
                );
            }
        }

        ID_RECONNECT => crate::stream::kick(app),

        // "Setup unfinished - 9 of 25" (Wave B, 2026-11-03): Settings, at the
        // "Personalize Atlas" card. Navigation only - the card's own Apply is
        // still the one write, and this row answers no question.
        ID_SETUP => {
            if let Err(err) = windows::show_settings_at(app, "personalize-jarvis") {
                eprintln!("[jarvis] tray: the Personalize Atlas card could not open: {err}");
                commands::notify_failed(
                    app,
                    crate::setup_offer::TITLE,
                    "Settings could not open.",
                    &err.to_string(),
                    commands::Details::Log,
                );
            }
        }

        ID_STATUS_CHECK => run_status_check(app),

        ID_QUIT => {
            #[cfg(desktop)]
            {
                use tauri_plugin_global_shortcut::GlobalShortcutExt;
                let _ = app.global_shortcut().unregister_all();
            }
            // Sizes and places first: the window-state plugin's own save runs
            // at exit, when the HUD below is already gone (window_memory.rs).
            crate::window_memory::save_now(app);
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

/// Left click on the icon SUMMONS the spotlight, and a second left click sends
/// it away again - matching what users expect from a launcher that lives in
/// the notification area.
///
/// This used to call `windows::show_quickbar` unconditionally, so clicking the
/// icon while the bar was already up did nothing visible: the owner's own
/// request of 2026-10-10, "open jarvis bar ... should also hide it if it is
/// clicked again after it pops up". It now goes through the one toggle every
/// other route uses (the `Alt+Space` hotkey, "open the Atlas bar" said out
/// loud, and the tray menu's own Show/Hide row), so all four agree. The caret
/// is placed by `toggle_quickbar` itself, which is why there is no
/// `emit_quickbar` here any more. Not emitted on Linux.
fn handle_tray_icon_event(tray: &tauri::tray::TrayIcon, event: TrayIconEvent) {
    if let TrayIconEvent::Click {
        button: MouseButton::Left,
        button_state: MouseButtonState::Up,
        ..
    } = event
    {
        let app = tray.app_handle();
        // App lock may ask Windows Hello first; `Ok(false)` is "not on screen
        // yet", which is not a failure and is not reported as one.
        if let Err(err) = windows::toggle_quickbar(app) {
            eprintln!("[jarvis] tray: unable to toggle the quickbar: {err}");
        }
    }
}

/// The tray's "Update Atlas to <version>" row: the same both-halves update the
/// Settings Install press runs, from the context menu. Where the backend half
/// cannot run on this PC, `install_from_tray` still says so and runs the desktop
/// half alone rather than pretending.
///
/// Off the main thread on purpose. The press must turn the row into "Updating
/// Atlas to <version>…" (so a second press cannot start a second run), and
/// Tauri posts every menu call to the main thread and waits for it - so doing
/// that from inside a menu handler would wait on the thread that is running it.
fn run_update_from_tray(app: &AppHandle) {
    let handle = app.clone();
    tauri::async_runtime::spawn(async move {
        crate::update::install_from_tray(handle).await;
    });
}

/// Starts or stops the backend, whichever the row is currently offering.
fn run_backend_action(app: &AppHandle) {
    let handle = app.clone();
    let owned = crate::sidecar::supervisor_status(app.clone()).owned;

    tauri::async_runtime::spawn(async move {
        let mut failed = None;
        let outcome = if owned {
            crate::sidecar::stop_owned(&handle, "asked from the tray").await
        } else {
            match crate::sidecar::start_backend(handle.clone()).await {
                Ok(outcome) => outcome,
                Err(err) => {
                    failed = Some(err.clone());
                    err
                }
            }
        };
        println!("[jarvis] tray: {outcome}");
        match failed {
            // A failed start is raw error text: plain words in the toast, the
            // text itself in the log and the crash notes.
            Some(raw) => {
                crate::crash_notes::record("backend", "start", &raw);
                commands::notify_failed(
                    &handle,
                    "Atlas — backend",
                    "The backend could not be started.",
                    &raw,
                    commands::Details::CrashNotes,
                );
            }
            None => commands::notify(&handle, "Atlas — backend", &outcome),
        }
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
                commands::notify(&handle, "Atlas — Status Check", &report.summary);
                crate::emit_all(&handle, events::HEALTH_REPORT, report);
            }
            Err(err) => {
                eprintln!("[jarvis] tray: status check failed: {err}");
                commands::notify_failed(
                    &handle,
                    "Atlas — Status Check",
                    "The status check could not finish.",
                    &err,
                    commands::Details::Log,
                );
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_live_mark_is_a_red_dot_at_the_lower_right() {
        let mut px = vec![0u8; (ICON_SIZE * ICON_SIZE * 4) as usize];
        mark_live(&mut px);
        let at = |x: u32, y: u32| ((y * ICON_SIZE + x) * 4) as usize;
        let c = at(ICON_SIZE - 7, ICON_SIZE - 7);
        assert!(
            px[c] > 200 && px[c + 1] < 120 && px[c + 3] == 255,
            "red, opaque"
        );
        let ring = at(ICON_SIZE - 7 + 6, ICON_SIZE - 7);
        assert!(px[ring + 1] > 150, "a light ring round it");
        assert_eq!(px[at(4, 4) + 3], 0, "the rest of the icon untouched");
    }

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
        // activity, and a Quiet Atlas mid-answer is still answering.
        l.activity = "speaking".into();
        assert_eq!(spec_state(&l), "speaking");

        // Something waiting on the human outranks that.
        l.approvals = 2;
        assert_eq!(spec_state(&l), "approval");

        // An error outranks everything.
        l.activity = "error".into();
        assert_eq!(spec_state(&l), "error");
    }

    /// A focus session's Quiet is not asleep (owner, 2026-09-29): the faces
    /// show the focus buddy, so the icon reads idle. A Quiet set by hand, or
    /// any standby, still reads as asleep. CONTROL: without the `focus` arm in
    /// `spec_state` the first assertion says "standby".
    #[test]
    fn a_focus_sessions_quiet_is_awake_and_a_hand_set_one_is_asleep() {
        let mut l = link();
        l.power = "quiet".into();
        l.power_set_by = Some("focus".into());
        assert_eq!(spec_state(&l), "idle", "focus Quiet shows the buddy");
        assert_eq!(power_label(&l), "Power: quiet · focus session");
        l.power_set_by = Some("override".into());
        assert_eq!(spec_state(&l), "standby", "a hand-set Quiet stays asleep");
        l.power_set_by = None;
        assert_eq!(spec_state(&l), "standby");
        l.power = "standby".into();
        l.power_set_by = Some("focus".into());
        assert_eq!(
            spec_state(&l),
            "standby",
            "only Quiet is the focus session's"
        );
        l.power = "quiet".into();
        l.power_set_by = Some("focus".into());
        l.connected = false;
        assert_eq!(spec_state(&l), "standby", "not connected is asleep");
    }

    /// Never the approval colour while acting is blocked, and not connected
    /// is asleep (the owner's rule, 2026-09-28) - with the hollow icon.
    #[test]
    fn no_approval_while_blocked_and_asleep_when_disconnected() {
        let mut l = link();
        l.approvals = 2;
        l.activity = "speaking".into();
        assert_eq!(spec_state(&l), "approval");
        l.stale = true;
        assert_eq!(
            spec_state(&l),
            "speaking",
            "a stale link asked for a decision"
        );
        l.connected = false;
        assert_eq!(
            spec_state(&l),
            "standby",
            "a dropped link kept its last activity"
        );
        l.activity = "error".into();
        assert_eq!(spec_state(&l), "standby");
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

        // Foreground wins: the budget governs what Atlas starts, not what it
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
        assert_eq!(activity_label(&cold), "Atlas — connecting…");
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
        assert!(activity_label(&down).starts_with("Atlas — offline: could not reach"));
        assert!(activity_label(&down).chars().count() < 90);

        // Connected, but the queue could not be confirmed: not "idle", and
        // not "offline" either, and any count is marked as last known.
        let mut stale = link();
        stale.stale = true;
        assert_eq!(activity_label(&stale), "Atlas — stale, reconnecting");
        assert_eq!(
            approvals_label(&stale),
            "Approvals: unknown until the link catches up"
        );
        stale.approvals = 2;
        assert_eq!(approvals_label(&stale), "2 approvals waiting (last known)");

        let mut quiet = link();
        quiet.power = "quiet".into();
        quiet.power_set_by = Some("override".into());
        // No `· read-only` any more: the "Change power mode" submenu sets it
        // (backend/power-mode.patch). Who set it is still said.
        assert_eq!(power_label(&quiet), "Power: quiet · set by hand");
        quiet.power = "standby".into();
        quiet.power_set_by = Some("standby_schedule".into());
        assert_eq!(power_label(&quiet), "Power: standby · standby schedule");

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

        // Zero pending had no coverage, and it is the case that changed: the
        // row used to be disabled here, which made the brief unreachable at
        // exactly the moment someone asks "did I miss anything?". It is a way
        // in now, so it has to read like one rather than like a status.
        budgeted.attention.pending = 0;
        assert_eq!(
            waiting_label(&budgeted),
            "Nothing waiting — the brief and the budget"
        );
        assert!(
            budgeted.attention.known,
            "the row is enabled on `known`, so a label test that left it false \
             would be asserting the disabled case by accident"
        );

        // digest_due was read off the wire into Attention and then never
        // looked at by anything - the field computed server-side
        // specifically to say "it is time for the daily brief" had no
        // effect anywhere. The row now says so when there is something to
        // tell and the server says it is due.
        budgeted.attention.pending = 3;
        budgeted.attention.limit = 6;
        budgeted.attention.remaining = 2;
        budgeted.attention.digest_due = true;
        assert_eq!(
            waiting_label(&budgeted),
            "3 things waiting to be told · 2 of 6 interruptions left · \
             today's brief is ready"
        );
        // But not when there is nothing to tell - "the brief is ready" over
        // an empty digest would be the same false confidence the zero-
        // pending case above was fixed to avoid.
        budgeted.attention.pending = 0;
        assert_eq!(
            waiting_label(&budgeted),
            "Nothing waiting — the brief and the budget"
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

    /// The "not connected" icon is the hollow ring (`filled == false`), and
    /// its edge must stand out on both taskbars too (owner, 2026-09-29: the
    /// faces' not-connected ring was 1.65:1 against the ground and was raised
    /// to about 4:1; the tray icon did not need it, and this is the proof).
    /// The ring is the thick body of the icon, and the two-tone outline round
    /// it (dark outside, light just inside) has contrast against whichever
    /// taskbar it sits on, whatever the fill colour - standby's grey at
    /// its dimmest included.
    #[test]
    fn the_hollow_not_connected_icon_has_an_edge_against_both_taskbars() {
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
        let standby = shade(
            Rgb {
                r: 107,
                g: 125,
                b: 148,
            },
            0.6,
        );
        let buf = draw_pixels(standby, standby, false, None);
        // The middle of the icon is EMPTY (hollow), not a disc.
        let mid = ((ICON_SIZE / 2) * ICON_SIZE + ICON_SIZE / 2) as usize * 4;
        assert_eq!(
            buf[mid + 3],
            0,
            "the middle of the not-connected icon is filled"
        );
        for (bg, label) in [(WHITE, "a light taskbar"), (BLACK, "a dark one")] {
            let mut best = 1.0f64;
            for i in (0..buf.len()).step_by(4) {
                let px = &buf[i..i + 4];
                if px[3] == 0 {
                    continue;
                }
                best = best.max(ratio(over(px, bg), bg));
            }
            assert!(
                best >= 3.0,
                "the hollow icon on {label}: the strongest edge measures {best:.2}:1, under 3:1"
            );
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

    /// The owner, 2026-11-03: the row appears only when an update exists, and it
    /// names the version the check found. **Absence, not greyed out**, is the
    /// no-update state - which is why the rule answers `Option` rather than a
    /// label plus a flag. Pure, so no menu and no app are needed.
    #[test]
    fn the_update_row_is_absent_with_no_update_and_present_with_one() {
        assert_eq!(update_row(None), None, "a row with no update to offer");
        assert_eq!(
            update_row(Some("0.2.411")).as_deref(),
            Some("Update Atlas to 0.2.411"),
            "the row must name the version the owner is about to install"
        );
        // A check can answer "something newer exists" without a label worth
        // printing; the row still belongs in the menu, in plain words.
        assert_eq!(update_row(Some("")).as_deref(), Some("Update Atlas"));
        assert_eq!(update_row(Some("   ")).as_deref(), Some("Update Atlas"));
    }

    /// Task-50 (Wave 12): the report row's status, built the way `update.rs`
    /// hands it over. Only the fields `update_state_row` reads are set.
    fn update_status(state: &str, error: Option<&str>, at: Option<&str>) -> crate::update::Status {
        crate::update::Status {
            current: "0.2.320".to_string(),
            state: state.to_string(),
            error: error.map(str::to_string),
            checked_at: at.map(str::to_string),
            supported: true,
            ..crate::update::Status::default()
        }
    }

    /// The four states, in the owner's words: up to date, update available,
    /// unknown and cannot check. Before this row there was ONE signal (the
    /// action row appearing) and its absence meant three different things.
    #[test]
    fn the_update_status_row_is_the_four_state_truth() {
        assert_eq!(
            update_state_row(None, Some("2026-11-09")),
            "Not checked yet",
            "a fresh launch has no answer, so it must not look like one"
        );
        assert_eq!(
            update_state_row(
                Some(&update_status("unknown", None, None)),
                Some("2026-11-09")
            ),
            "Not checked yet"
        );
        assert_eq!(
            update_state_row(
                Some(&update_status("up_to_date", None, Some("2026-11-09 14:32"))),
                Some("2026-11-09")
            ),
            "Up to date · checked 14:32"
        );
        assert_eq!(
            update_state_row(
                Some(&update_status(
                    "update_available",
                    None,
                    Some("2026-11-09 14:32")
                )),
                Some("2026-11-09")
            ),
            "Update available · checked 14:32"
        );
    }

    /// The one rule this row exists to keep: no invented "up to date". A state
    /// this build does not know, or one with no check behind it, is drawn as
    /// unknown - never as the good state.
    #[test]
    fn the_update_status_row_never_claims_up_to_date_without_a_check() {
        let unknown = update_status("unknown", None, None);
        assert_eq!(update_state_row(Some(&unknown), None), "Not checked yet");
        let empty = update_status("", None, None);
        assert_eq!(update_state_row(Some(&empty), None), "Not checked yet");
        let future = update_status("half_checked", None, None);
        assert_eq!(update_state_row(Some(&future), None), "Not checked yet");
    }

    /// "Cannot check" carries WHY, in a few words, and the time if a check was
    /// really attempted. Each reason is one `update.rs` really produces.
    #[test]
    fn a_cannot_check_row_says_why() {
        let unreachable = update_status(
            "cannot_check",
            Some("Could not reach the release endpoint: connection refused"),
            Some("2026-11-09 14:32"),
        );
        assert_eq!(
            update_state_row(Some(&unreachable), Some("2026-11-09")),
            "Cannot check · the release page could not be reached · checked 14:32"
        );
        let no_key = update_status(
            "cannot_check",
            Some("This build has no update key, so it cannot verify a download and will not try."),
            None,
        );
        assert_eq!(
            update_state_row(Some(&no_key), None),
            "Cannot check · this build has no update key",
            "a build that never asked must not carry a time either"
        );
        let no_releases = update_status(
            "cannot_check",
            Some("No releases published yet, so there is nothing to compare against."),
            Some("2026-11-09 14:32"),
        );
        assert_eq!(
            update_state_row(Some(&no_releases), Some("2026-11-09")),
            "Cannot check · no releases are published yet · checked 14:32"
        );
    }

    /// A build with no update key never asks anything, so its row must say that
    /// at launch - "Not checked yet" would invite a Check the Settings card
    /// disables. This is the fresh-launch shape `update::last_status` hands the
    /// tray when no check has answered.
    #[test]
    fn a_build_that_cannot_check_says_so_at_launch() {
        let keyless = crate::update::Status {
            state: "cannot_check".to_string(),
            supported: false,
            ..crate::update::Status::default()
        };
        assert_eq!(
            update_state_row(Some(&keyless), None),
            "Cannot check · this build has no update key"
        );
    }

    /// A check from an earlier day keeps its date: "checked 09:05" on a stale
    /// answer would read as this morning, which is a made-up fact.
    #[test]
    fn an_old_check_keeps_its_date() {
        let old = update_status("up_to_date", None, Some("2026-11-08 09:05"));
        assert_eq!(
            update_state_row(Some(&old), Some("2026-11-08")),
            "Up to date · checked 09:05"
        );
        assert_eq!(
            update_state_row(Some(&old), Some("2026-11-09")),
            "Up to date · checked 2026-11-08 09:05"
        );
        assert_eq!(
            update_state_row(Some(&old), None),
            "Up to date · checked 2026-11-08 09:05",
            "an unreadable clock must not be guessed into 'today'"
        );
    }

    /// A blank stamp is no stamp. It must not leave a dangling "checked".
    #[test]
    fn a_blank_time_is_not_a_check_time() {
        let blank = update_status("up_to_date", None, Some("   "));
        assert_eq!(update_state_row(Some(&blank), None), "Up to date");
        assert_eq!(checked_words("", None), None);
        assert_eq!(checked_words("   ", Some("2026-11-09")), None);
    }

    /// Wave B (2026-11-03): the same absence rule for "Setup unfinished - 9 of
    /// 25". The state is `setup_offer`'s own, and this test is what holds the
    /// tray to it: no unfinished quiz, no row; and the count the owner sees is
    /// the count the state carries, not a number the tray typed.
    #[test]
    fn the_setup_row_is_absent_when_the_quiz_is_done_or_unread() {
        use crate::setup_offer::SetupState;

        // Not read yet: no row. An absent answer is not "unfinished".
        assert_eq!(SetupState::default().tray_label(), None);

        // Finished: no row.
        let done = SetupState {
            known: true,
            version: 2,
            completed_version: 2,
            answered: 25,
            total: 25,
            dismissed_at: None,
        };
        assert_eq!(done.tray_label(), None);

        // Unfinished: the row, with the state's own two numbers.
        let behind = SetupState {
            completed_version: 1,
            answered: 9,
            ..done
        };
        assert_eq!(
            behind.tray_label().as_deref(),
            Some("Setup unfinished \u{2014} 9 of 25")
        );
    }
}
