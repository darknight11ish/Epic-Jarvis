//! The one event-stream connection, owned by Rust and fanned out to every
//! surface.
//!
//! Three windows need the same news: the quickbar renders approval gates, the
//! widget renders them too, and the tray icon carries the colour. Before this
//! module each of those subscribed for itself, which is three sockets, three
//! reconnect timers, three copies of the resume point, and — the part that
//! actually bites — three places that can disagree about whether an approval
//! is still open, and so three chances at the same 409 race.
//!
//! So: one `GET /api/events`, held open here, and `app.emit` to everyone.
//! JARVIS-API §3 is the contract this implements:
//!
//! * resume with `Last-Event-ID` (persisted, so a restart resumes too);
//! * `hello.stale == true` means re-fetch everything, do not replay;
//! * `: keepalive` every ~20 s, and its *absence* means the socket is dead
//!   even when the OS has not noticed;
//! * an event is a doorbell, not a database — on `approval` this module
//!   re-fetches `/api/pending` once and hands the result to all three
//!   surfaces, rather than letting each of them fetch it.
//!
//! ## Why not the webview's own `EventSource`
//!
//! JARVIS-API §3 offers the choice and names the reason to take this one:
//! "If you'd rather stream in Rust (to update the tray icon without the window
//! open)". A tray icon that only knows what Jarvis is doing while a window
//! happens to be open is the tray icon not working. There are two more:
//! `EventSource` cannot set a request header, so a token has to ride in the
//! query string, and the server's stream ends by design after an hour —
//! reconnecting is not an error path here, it is the normal one.

use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

use crate::commands;
use crate::sse::{Event, Frame};

/// Backoff floor. The server tells us `retry: 3000`; this is what we use until
/// it has, and the value we return to after a clean connect.
const BASE_BACKOFF: Duration = Duration::from_millis(3_000);
/// Backoff ceiling. A backend that is simply not running must not be hammered.
const MAX_BACKOFF: Duration = Duration::from_secs(30);
/// A connection that lasted at least this long did its job, so the next
/// reconnect starts from the floor again.
const PRODUCTIVE_CONNECTION: Duration = Duration::from_secs(30);
/// How long a silent socket is given before it is treated as dead.
///
/// JARVIS-API §3: keepalives arrive every ~20 s and "their absence for much
/// longer than that means the connection is dead even if the socket hasn't
/// noticed". Three missed keepalives is that, with room for a stalled laptop.
const SILENCE_TIMEOUT: Duration = Duration::from_secs(70);
/// Connect timeout. Loopback either answers at once or is not there.
const CONNECT_TIMEOUT: Duration = Duration::from_secs(5);
/// Timeout for the small side-fetches this module makes (`/api/version`,
/// `/api/pending`). Never applied to the stream itself, which is meant to hang.
const FETCH_TIMEOUT: Duration = Duration::from_secs(10);
/// How often the resume point is allowed to reach disk. The bus only publishes
/// on change, so this is nearly always idle; it exists so that a burst cannot
/// turn into a write per event.
const RESUME_SAVE_INTERVAL: Duration = Duration::from_secs(5);
/// Largest line the stream may send before it is treated as broken. The bus
/// publishes small JSON objects; a megabyte without a newline is a fault.
const MAX_LINE_BYTES: usize = 1024 * 1024;
/// Store key holding the resume point across restarts.
const RESUME_KEY: &str = "events.last_id";

/// What every surface — and the tray — is told about the one stream.
///
/// `stale` is the field with teeth: DESKTOP-BUILD's checklist says "disable
/// approve/deny while the stream is stale", because answering a queue you
/// cannot confirm is live is how you approve something twice.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LinkState {
    /// The stream is connected and has said hello.
    pub connected: bool,
    /// Nothing on this machine can be trusted to be current. True before the
    /// first connect, and again from the moment a connection drops.
    pub stale: bool,
    /// The base the stream is pointed at, so a surface can say where.
    pub base: String,
    /// Last event id seen, which is also the resume point.
    pub last_id: u64,
    /// Power mode: `active`, `quiet` or `standby`. Whether Jarvis is available.
    pub power: String,
    /// What put Jarvis in that mode — `override` for a hand-set one, or
    /// `schedule` / `idle` / `auto`. JARVIS-API §4: "Talking to Jarvis does not
    /// cancel a Quiet the user set by hand", so the tray has to be able to say
    /// which kind of Quiet this is.
    pub power_set_by: Option<String>,
    /// Activity: `idle`, `listening`, `thinking`, `speaking`, `working`,
    /// `error`. What Jarvis is doing. The visual spec binds colour to this one.
    pub activity: String,
    /// How many approvals are waiting on a human. Not the digest count —
    /// see [`crate::attention::Attention::pending`] for that one.
    pub approvals: usize,
    /// The interruption budget, the digest count and the server's `banked`
    /// flag. Carried on the link rather than in a channel of its own so that
    /// the tray, the quickbar and the widget cannot disagree about how many
    /// things are waiting: one struct, one broadcast, one repaint.
    pub attention: crate::attention::Attention,
    /// Why the stream is down, when it is. `None` while connected.
    pub error: Option<String>,
}

impl Default for LinkState {
    fn default() -> Self {
        Self {
            connected: false,
            // Nothing has been heard yet, so nothing is known. Starting at
            // `false` would enable the approve buttons for the first second of
            // every launch, against a queue nobody has read.
            stale: true,
            base: String::new(),
            last_id: 0,
            power: "active".to_string(),
            power_set_by: None,
            activity: "idle".to_string(),
            approvals: 0,
            attention: crate::attention::Attention::default(),
            error: None,
        }
    }
}

/// Managed state: the link, plus the pending queue as this process last read
/// it. The queue lives here rather than in each window so that all three render
/// the same list from the same fetch.
#[derive(Default)]
pub struct StreamState {
    link: Mutex<LinkState>,
    pending: Mutex<Vec<serde_json::Value>>,
    /// False until the first successful read of `/api/pending`.
    ///
    /// The desktop toasts an arriving gate, and on the very first read every
    /// gate already in the queue would look like an arrival — five toasts at
    /// launch for five decisions the owner may have parked days ago. The first
    /// read establishes the baseline and says nothing.
    seeded: std::sync::atomic::AtomicBool,
    /// True only while the queue on screen came from a successful read of
    /// `/api/pending` made on THIS connection. Reset to false every time a
    /// connection opens, set by [`refresh_pending`] on each read.
    ///
    /// The `hello` branch needs it: the queue is read once just before the
    /// hello frame arrives, and a failure there used to be forgotten - a
    /// following `hello {stale: false}` then cleared `stale` and re-enabled
    /// Approve and Deny over the last run's queue.
    queue_read: std::sync::atomic::AtomicBool,
}

impl StreamState {
    pub fn link(&self) -> LinkState {
        self.lock_link().clone()
    }

    pub fn pending(&self) -> Vec<serde_json::Value> {
        self.pending
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .clone()
    }

    fn lock_link(&self) -> std::sync::MutexGuard<'_, LinkState> {
        self.link
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    /// Applies a change and reports whether anything actually moved, so a
    /// no-op does not cost an IPC broadcast to three windows and an icon
    /// redraw.
    fn update<F: FnOnce(&mut LinkState)>(&self, edit: F) -> Option<LinkState> {
        let mut guard = self.lock_link();
        let before = guard.clone();
        edit(&mut guard);
        if same_link(&before, &guard) {
            None
        } else {
            Some(guard.clone())
        }
    }
}

fn same_link(a: &LinkState, b: &LinkState) -> bool {
    a.connected == b.connected
        && a.stale == b.stale
        && a.base == b.base
        && a.last_id == b.last_id
        && a.power == b.power
        && a.power_set_by == b.power_set_by
        && a.activity == b.activity
        && a.approvals == b.approvals
        && a.attention == b.attention
        && a.error == b.error
}

// ---------------------------------------------------------------------------
// Commands the surfaces call instead of streaming for themselves
// ---------------------------------------------------------------------------

/// The current link state. A window calls this once when it loads, then lives
/// off the [`crate::events::JARVIS_LINK`] broadcasts.
#[tauri::command]
pub fn get_link_state(app: AppHandle) -> LinkState {
    app.state::<StreamState>().link()
}

/// The approval queue as this process last read it. Same contract: read once
/// on load, then follow [`crate::events::APPROVALS_CHANGED`].
#[tauri::command]
pub fn get_pending_approvals(app: AppHandle) -> serde_json::Value {
    let state = app.state::<StreamState>();
    let items = state.pending();
    serde_json::json!({
        "count": items.len(),
        "items": items,
        "stale": state.link().stale,
    })
}

/// Asks the stream to reconnect now instead of waiting out its backoff — what
/// the tray's "Reconnect" item and a settings change both want.
#[tauri::command]
pub fn refresh_link(app: AppHandle) {
    kick(&app);
}

// ---------------------------------------------------------------------------
// The connection
// ---------------------------------------------------------------------------

/// Signal used to cut a connection short: a settings change, or an explicit
/// reconnect. Held in [`StreamState`]'s task rather than in managed state
/// because only the loop and [`kick`] ever touch it.
static WAKE: std::sync::OnceLock<Arc<tokio::sync::Notify>> = std::sync::OnceLock::new();

fn wake() -> &'static Arc<tokio::sync::Notify> {
    WAKE.get_or_init(|| Arc::new(tokio::sync::Notify::new()))
}

/// Drops whatever connection is open and reconnects without serving out the
/// backoff.
///
/// `notify_one`, not `notify_waiters`. The latter is a no-op when nobody is
/// parked, and the loop is unparked for long stretches — the two side-fetches
/// after a connect are up to 10 s each, plus every `dispatch`, plus the tail of
/// the outer loop. A kick landing in one of those evaporated, so "Reconnect"
/// and the post-start nudge could silently do nothing and the user waited out
/// a 30 s backoff staring at "offline".
///
/// `notify_one` leaves a permit instead, so the kick is honoured at the next
/// wait. The cost is that a permit can cut one healthy connection short; that
/// costs a reconnect, which is exactly what was asked for anyway.
pub fn kick(app: &AppHandle) {
    let _ = app;
    wake().notify_one();
}

/// Starts the one connection. Called once from `setup`.
pub fn spawn(app: AppHandle) {
    // Resume where the last run left off, so a restart is not a re-read.
    let resume = load_resume(&app);
    if resume > 0 {
        app.state::<StreamState>().lock_link().last_id = resume;
        println!("[jarvis] event stream resuming from id {resume}");
    }

    tauri::async_runtime::spawn(async move {
        let mut backoff = BASE_BACKOFF;
        loop {
            let base = commands::jarvis_base(&app);
            publish_link(&app, |link| {
                link.base = base.clone();
            });

            let opened_at = Instant::now();
            let outcome = connect_once(&app, &base).await;

            let message = match outcome {
                Ok(reason) => {
                    // A clean end is the normal case, not a failure: the server
                    // closes the stream after an hour by design. Reconnecting
                    // promptly is correct, so the backoff is reset — but only
                    // if the connection actually did some work. A server that
                    // 200s the headers and immediately closes the body also
                    // arrives here, and resetting for that meant reconnecting
                    // every 3 s for ever with the tray flapping.
                    if opened_at.elapsed() >= PRODUCTIVE_CONNECTION {
                        backoff = BASE_BACKOFF;
                    }
                    reason
                }
                Err(err) => {
                    eprintln!("[jarvis] event stream: {err}");
                    err
                }
            };

            publish_link(&app, |link| {
                link.connected = false;
                link.stale = true;
                link.error = Some(message.clone());
            });
            save_resume(&app, true);

            // Grow the backoff BEFORE waiting, so the two resets below are not
            // undone one line later — which is what used to happen: a clean
            // hourly close reconnected at 5.4 s instead of 3 s, and a
            // user-requested reconnect climbed on every press.
            let wait = backoff;
            backoff = std::cmp::min(backoff.mul_f64(1.8), MAX_BACKOFF);

            // Wait out the backoff, unless something asks for a reconnect now.
            tokio::select! {
                _ = tokio::time::sleep(wait) => {}
                _ = wake().notified() => { backoff = BASE_BACKOFF; }
            }
        }
    });
}

/// Holds one connection open until it ends. `Ok` carries why it ended cleanly;
/// `Err` carries why it failed.
async fn connect_once(app: &AppHandle, base: &str) -> Result<String, String> {
    let client = reqwest::Client::builder()
        .connect_timeout(CONNECT_TIMEOUT)
        // Deliberately no total timeout: this request is *meant* to hang for
        // an hour. Silence is caught by SILENCE_TIMEOUT around each read
        // instead, which is the only thing that can tell a healthy idle stream
        // from a dead one.
        .no_proxy()
        .build()
        .map_err(|e| format!("unable to build the stream client: {e}"))?;

    let mut headers = commands::jarvis_headers(app)?;
    let resume = app.state::<StreamState>().link().last_id;
    if resume > 0 {
        // The header, not `?since=`. Both work — the server reads the query
        // string only when the header is absent — but the token also travels
        // as a header here, and putting either in a URL is how they end up in
        // a log.
        if let Ok(value) = reqwest::header::HeaderValue::from_str(&resume.to_string()) {
            headers.insert("Last-Event-ID", value);
        }
    }
    headers.insert(
        reqwest::header::ACCEPT,
        reqwest::header::HeaderValue::from_static("text/event-stream"),
    );

    let mut response = client
        .get(format!("{base}/api/events"))
        .headers(headers)
        .send()
        .await
        .map_err(|e| {
            // Plain words first, the technical part after: the tray and the
            // quickbar show only the first sentence (tray.rs first_sentence,
            // jarvis-link.js linkWords), and Settings shows the whole thing.
            if e.is_connect() {
                format!(
                    "Jarvis is not running at {base}. Start it, or check the \
                     address in Settings. Technical detail: could not reach the \
                     Jarvis server at {base}."
                )
            } else {
                format!(
                    "Could not connect to Jarvis. Technical detail: the event \
                     stream could not be opened: {e}"
                )
            }
        })?;

    let status = response.status();
    if !status.is_success() {
        let body = response.text().await.unwrap_or_default();
        let body = body.trim();
        return Err(match status.as_u16() {
            // The server's own words for these two, so the message names the
            // fix rather than the symptom.
            401 => "Jarvis refused this app's token. Open Settings, then \
                    Connection, and paste the token again. Technical detail: the \
                    server refused the event stream (HTTP 401, bad or missing token)."
                .to_string(),
            403 => "Jarvis refused this app. Technical detail: the server refused \
                    the event stream as cross-origin. The desktop client sends \
                    X-Jarvis-Client: hud, so this means JARVIS_HUD_ORIGINS does \
                    not cover this client."
                .to_string(),
            code if body.is_empty() => format!(
                "Jarvis answered with an error. Technical detail: the event \
                 stream answered HTTP {code}."
            ),
            code => format!(
                "Jarvis answered with an error. Technical detail: the event \
                 stream answered HTTP {code}: {body}"
            ),
        });
    }

    println!("[jarvis] event stream open against {base}");

    // The activity state is *pushed*, never polled, so a client that connects
    // mid-turn has no event to learn it from — and, despite what DESKTOP-BUILD
    // §6 says, the SSE `hello` frame does not carry it either: `jarvis_events
    // .stream()` builds that frame from `resumed_from / stale / latest /
    // retry_ms` alone. The `activity` field lives on `GET /api/version`'s
    // hello. So the tray asks for it here, once per connect.
    prime_from_version(app, base).await;
    // Same reasoning for the queue: `note()` only publishes on change, so a
    // client that connects while three approvals are already waiting hears
    // nothing at all until a fourth arrives.
    //
    // The result is recorded in `queue_read` rather than returned here,
    // because the decision it feeds is made later, when `hello` arrives. It
    // used to be thrown away (`let _ =`), with a comment saying there was no
    // `stale = false` to guard - but there was one, in the `hello` branch, and
    // a clean `hello {stale: false}` after a failed read here cleared `stale`
    // over the previous run's queue. The phone never had this gap: it clears
    // `stale` only after a successful re-read (JarvisRuntime.onOpen).
    app.state::<StreamState>()
        .queue_read
        .store(false, std::sync::atomic::Ordering::Relaxed);
    refresh_pending(app, base).await;

    let mut frame = Frame::default();
    // Lines are cut from raw bytes so a multi-byte character split across two
    // network chunks is never decoded half-way.
    let mut buffer: Vec<u8> = Vec::with_capacity(8 * 1024);

    loop {
        let chunk = tokio::select! {
            read = tokio::time::timeout(SILENCE_TIMEOUT, response.chunk()) => match read {
                Ok(Ok(Some(bytes))) => bytes,
                Ok(Ok(None)) => {
                    // The server ends the stream after an hour by design.
                    return Ok("the server closed the stream; reconnecting".to_string());
                }
                Ok(Err(e)) => {
                    return Err(format!(
                        "The connection to Jarvis dropped. Technical detail: the \
                         event stream broke: {e}"
                    ))
                }
                Err(_) => {
                    return Err(format!(
                        "Jarvis went quiet: nothing heard for {} seconds. \
                         Technical detail: no keepalive for {}s, so the event \
                         stream is treated as dead.",
                        SILENCE_TIMEOUT.as_secs(),
                        SILENCE_TIMEOUT.as_secs()
                    ))
                }
            },
            _ = wake().notified() => {
                return Ok("reconnecting at the client's request".to_string());
            }
        };

        buffer.extend_from_slice(&chunk);
        // A body that never sends a newline would otherwise grow this until the
        // process dies. No legitimate SSE frame is anywhere near this large.
        if buffer.len() > MAX_LINE_BYTES {
            return Err(format!(
                "the event stream sent {} bytes with no line break; treating it as broken",
                buffer.len()
            ));
        }
        while let Some(newline) = buffer.iter().position(|b| *b == b'\n') {
            let line: Vec<u8> = buffer.drain(..=newline).collect();
            let text = String::from_utf8_lossy(&line[..line.len() - 1])
                .trim_end_matches('\r')
                .to_string();
            if let Some(event) = frame.feed(&text) {
                dispatch(app, base, event).await;
            }
        }
    }
}

/// Applies one event: updates what the tray needs, re-fetches what the doorbell
/// rang for, and hands the raw event to every window.
async fn dispatch(app: &AppHandle, base: &str, event: Event) {
    if let Some(id) = event.id {
        publish_link(app, |link| {
            // Monotonic: a replayed backlog must not walk the resume point
            // backwards if the server ever renumbers.
            if id > link.last_id {
                link.last_id = id;
            }
        });
        save_resume(app, false);
    }

    match event.name.as_str() {
        "hello" => {
            let stale = event.data["stale"].as_bool().unwrap_or(false);
            // `latest` is the server's newest id. If it is BEHIND our resume
            // point, the bus has been renumbered — `jarvis_events.Bus` is in
            // memory and `_next` restarts at 1 on every backend restart. Its
            // `since()` then returns `stale = False` against an empty ring, so
            // we are told we are caught up while the monotonic guard below
            // silently discards every event for ever. Nothing else lowers the
            // resume point, so without this a routine restart killed the stream
            // permanently and only clearing the settings store brought it back.
            let latest = event.data["latest"].as_u64();
            let renumbered = matches!((latest, app.state::<StreamState>().link().last_id),
                                      (Some(latest), last) if last > 0 && latest < last);
            if renumbered {
                println!("[jarvis] the event bus restarted; resetting the resume point");
            }

            // `stale` is cleared only once the queue has actually been read
            // on this connection - see `hello_may_clear_stale`. It used to be
            // cleared here unconditionally, which enabled Approve and Deny for
            // two network round-trips against a queue that had just been
            // declared untrustworthy; and after that, on `!stale` alone, which
            // did the same whenever the read just before hello had failed.
            let queue_read = app
                .state::<StreamState>()
                .queue_read
                .load(std::sync::atomic::Ordering::Relaxed);
            let settled = hello_may_clear_stale(stale, renumbered, queue_read);
            publish_link(app, |link| {
                link.connected = true;
                link.error = None;
                if settled {
                    link.stale = false;
                }
                if renumbered {
                    link.last_id = latest.unwrap_or(0);
                }
            });
            if renumbered {
                save_resume(app, true);
            }

            if stale || renumbered {
                // Rule 2 of §3: we fell off the back of the 512-event ring.
                // Everything local is suspect — re-read it, do not replay.
                println!("[jarvis] resume point unusable; re-reading all state");
                prime_from_version(app, base).await;
                let reread = refresh_pending(app, base).await;
                crate::attention::refresh(app, base).await;
                // Only if the queue actually came back. This used to clear
                // `stale` unconditionally, one line after a call whose every
                // failure path sets `stale` and keeps the PREVIOUS queue -
                // so a backend that restarted and answered /api/pending with
                // a 503 while its gate module loaded left the windows
                // rendering pre-restart cards with live buttons, and
                // `decide_approval`'s own staleness gate passed. The owner
                // could approve an id the restarted backend had reassigned.
                //
                // The comment above this branch promised exactly this
                // behaviour ("cleared only once the re-read below has
                // landed") while the code did not do it, which is why it went
                // unnoticed.
                if reread {
                    publish_link(app, |link| link.stale = false);
                }
                crate::emit_all(app, crate::events::JARVIS_RESYNC, ());
            } else {
                // A clean hello, but the queue read just before it failed.
                // Try once more now; `stale` stays set unless it lands.
                if !settled && refresh_pending(app, base).await {
                    publish_link(app, |link| link.stale = false);
                }
                // A clean resume still needs one read. The `attention` event
                // only fires on a change, so a desktop that connects to a
                // quiet system would sit on `known: false` — and therefore on
                // "waiting: unknown" — until the budget happened to move.
                crate::attention::refresh(app, base).await;
            }
        }

        // The one event kind that carries its own state rather than ringing a
        // doorbell. §4 documents the payload and the update order says "use
        // the event, poll only on resume"; `_publish_state` sends it only when
        // one of the five fields actually moves, so applying it directly costs
        // nothing and re-fetching would cost a round trip per change.
        "attention" => {
            let data = event.data.clone();
            publish_link(app, |link| link.attention.apply_event(&data));
        }

        // The doorbell. §3 rule 1: the event says something changed, so read
        // the thing that changed — once, here, not once per window.
        // A failure has already set `stale`. A success while connected (that
        // is, after this connection's hello) is exactly what "the queue is
        // confirmed live" means, so it may clear a `stale` left by an earlier
        // failed read - the same rule the phone's watchdog follows. Without
        // this, one failed read left the buttons disabled until the stream
        // happened to reconnect.
        "approval" => {
            let read = refresh_pending(app, base).await;
            if read && app.state::<StreamState>().link().connected {
                publish_link(app, |link| link.stale = false);
            }
        }

        "activity" => {
            if let Some(state) = activity_state(&event.data) {
                let state = state.to_string();
                publish_link(app, |link| link.activity = state.clone());
            }
        }

        // `bus.note()` wraps a changed value as {key, value}; for power the
        // value is `jarvis_power.current()`, which is the mode string.
        "power" => {
            if let Some(mode) = event.data["value"].as_str() {
                let mode = mode.to_string();
                publish_link(app, |link| link.power = mode.clone());
                // The event carries the mode and nothing else, so who set it
                // has to come from /api/version. Cheap, and only on a change.
                prime_from_version(app, base).await;
            }
        }

        // finding | persona | model | voice — nothing here consumes them, and
        // nothing here should: they are fanned out below like everything else,
        // and the surface that renders one owns what it means.
        _ => {}
    }

    let frame = serde_json::json!({
        "kind": event.name,
        "id": event.id,
        "data": event.data,
    });
    crate::emit_all(app, crate::events::JARVIS_EVENT, frame.clone());
    // The HUD gets the same frame by a different road; see `push_to_hud`.
    crate::push_to_hud(app, "event", &frame);
}

/// The state out of an `activity` event. Two shapes: the state at the top
/// level, or the rebuilt bus's `note()` shape, `{key, value: {state,
/// detail}}` (backend/rebuilt/jarvis_events.py `set_activity`). Reading only
/// the first left the tray on "idle" through every turn on the second.
fn activity_state(data: &serde_json::Value) -> Option<&str> {
    data["state"]
        .as_str()
        .or_else(|| data["value"]["state"].as_str())
}

/// Reads `GET /api/version` for the activity state, which nothing else carries.
async fn prime_from_version(app: &AppHandle, base: &str) {
    let Ok(client) = reqwest::Client::builder()
        .connect_timeout(CONNECT_TIMEOUT)
        .timeout(FETCH_TIMEOUT)
        .no_proxy()
        .build()
    else {
        return;
    };
    let Ok(headers) = commands::jarvis_headers(app) else {
        return;
    };
    let body: serde_json::Value = match client
        .get(format!("{base}/api/version"))
        .headers(headers)
        .send()
        .await
    {
        Ok(response) => {
            let status = response.status();
            if !status.is_success() {
                // A 401 body parses fine and would have left the tray sitting
                // on the idle colour through an entire conversation.
                eprintln!("[jarvis] /api/version answered HTTP {}", status.as_u16());
                return;
            }
            match response.json().await {
                Ok(body) => body,
                Err(err) => {
                    eprintln!("[jarvis] /api/version returned something unreadable: {err}");
                    return;
                }
            }
        }
        Err(err) => {
            eprintln!("[jarvis] /api/version unavailable: {err}");
            return;
        }
    };

    let activity = body["activity"].as_str().unwrap_or("idle").to_string();
    // The power mode rides in the capabilities block rather than at the top
    // level: `capabilities.power` is `jarvis_power.status()`, and `false` when
    // the module is not installed at all.
    let power = body["capabilities"]["power"]["mode"]
        .as_str()
        .map(str::to_string);
    let set_by = body["capabilities"]["power"]["set_by"]
        .as_str()
        .map(str::to_string);
    publish_link(app, |link| {
        link.activity = activity;
        if let Some(power) = power {
            link.power = power;
            link.power_set_by = set_by.clone();
        }
    });
}

/// Re-reads the approval queue and hands the same list to all three surfaces.
///
/// This is the single place the desktop learns what is pending. Before the
/// fan-out the quickbar and the widget each fetched it on their own timers,
/// which meant two lists, two moments, and two chances to offer a decision on
/// something the other had already answered.
/// Re-reads `/api/pending`.
///
/// @return true only when the queue was actually re-read. The caller needs
/// that: every failure path below leaves the PREVIOUS queue in place and sets
/// `stale`, and a caller that then cleared `stale` unconditionally - which is
/// what `dispatch`'s `hello` branch did - re-enabled Approve and Deny over a
/// queue the code had just declared untrustworthy. Returning `()` is what made
/// that mistake invisible.
async fn refresh_pending(app: &AppHandle, base: &str) -> bool {
    let Ok(client) = reqwest::Client::builder()
        .connect_timeout(CONNECT_TIMEOUT)
        .timeout(FETCH_TIMEOUT)
        .no_proxy()
        .build()
    else {
        return false;
    };
    let Ok(headers) = commands::jarvis_headers(app) else {
        return false;
    };

    // The status is checked before the body is trusted. It used to go straight
    // to `.json()`, and a 401/403/500 error body parses perfectly well — the
    // `or_else` chain below then yielded an empty list, so a refused request
    // silently WIPED the approval queue on all three surfaces while `stale`
    // stayed false and the approve buttons stayed live. A queued shell command
    // simply vanished.
    let body: serde_json::Value = match client
        .get(format!("{base}/api/pending"))
        .headers(headers)
        .send()
        .await
    {
        Ok(response) => {
            let status = response.status();
            if !status.is_success() {
                eprintln!(
                    "[jarvis] /api/pending answered HTTP {}; keeping the last known queue",
                    status.as_u16()
                );
                // Not knowing is not the same as knowing there is nothing.
                mark_queue_unread(app);
                return false;
            }
            match response.json().await {
                Ok(body) => body,
                Err(err) => {
                    eprintln!("[jarvis] /api/pending returned something unreadable: {err}");
                    mark_queue_unread(app);
                    return false;
                }
            }
        }
        Err(err) => {
            eprintln!("[jarvis] /api/pending unavailable: {err}");
            mark_queue_unread(app);
            return false;
        }
    };

    // The server has answered `{"pending": [...]}` and a bare array at
    // different points in its life; accept either rather than show an empty
    // queue when there is one.
    // `{"available": false, "pending": []}` means the gate module is not
    // installed — which is not the same as an empty queue, and the API spec
    // says a false capability means hide the UI, not show an empty one.
    let available = body["available"].as_bool().unwrap_or(true);
    let mut items: Vec<serde_json::Value> = body["pending"]
        .as_array()
        .or_else(|| body["items"].as_array())
        .or_else(|| body.as_array())
        .cloned()
        .unwrap_or_default();
    // Turn `expires_in` (seconds left, approval-expiry.patch) into a deadline
    // NOW, at the moment of the read. The windows may render this list much
    // later (a window opening reads the cached queue), and "150 s left" read
    // then would be wrong by however long it sat here.
    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0);
    for item in items.iter_mut() {
        stamp_expiry(item, now_ms);
    }

    let state = app.state::<StreamState>();
    let seeded = state
        .seeded
        .swap(true, std::sync::atomic::Ordering::Relaxed);
    let arrived: Vec<serde_json::Value> = {
        let mut slot = state
            .pending
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let known: std::collections::HashSet<String> =
            slot.iter().filter_map(approval_id).collect();
        let fresh = items
            .iter()
            .filter(|item| approval_id(item).is_some_and(|id| !known.contains(&id)))
            .cloned()
            .collect();
        *slot = items.clone();
        fresh
    };
    publish_link(app, |link| link.approvals = items.len());
    state
        .queue_read
        .store(true, std::sync::atomic::Ordering::Relaxed);

    // The ping. A gate that arrives while the owner is in another window
    // produced nothing they could perceive without looking: the tray icon went
    // amber, and that was the whole signal. A screen reader heard it only if
    // the spotlight happened to be the focused window, because the live region
    // is in the page.
    //
    // One toast per gate, and only for ids this process has not already seen —
    // `/api/pending` is re-read on connect, on resume and on every `approval`
    // event, and a re-read is not an arrival. `seeded` suppresses the first
    // read entirely: a queue that was already waiting when the app started is
    // not five things arriving at once.
    //
    // The toast says what wants a decision and never offers one. There is no
    // action on it, because an action on a notification is a decision made
    // without the risk line, the `raised` block or the source in front of you.
    for item in arrived.iter().filter(|_| seeded) {
        // `notice` is built server-side by jarvis_gate.notice_for, from the
        // action name and the risk table — it never reads `detail`, `prompt`
        // or the contents of `raised`, so it is safe to display anywhere. One
        // source of wording, so this and the phone cannot describe the same
        // waiting decision two different ways.
        let notice = &item["notice"];

        // "weight: 'heavy' interrupts; 'normal' waits to be found" -
        // docs/ARCHITECTURE.md's own rule 1 for any client reading this
        // contract. This used to toast for every arrival regardless of
        // weight, with a comment claiming "the weight is still honoured: a
        // heavy item gets the tray's attention state" - which was true of
        // EVERY pending item, heavy or not (tray.rs escalates on
        // `link.approvals > 0`, not on weight), so the one field that exists
        // to let a person tell "needs you now" from "can wait" was computed
        // server-side and read nowhere. Missing `weight` (an older backend)
        // defaults to interrupting, same as the missing-notice fallback
        // below already assumes the more attention-worthy case rather than
        // the quieter one.
        if notice["weight"].as_str() == Some("normal") {
            continue;
        }

        let (title, body) = match (notice["title"].as_str(), notice["body"].as_str()) {
            (Some(t), Some(b)) => (t.to_string(), b.to_string()),
            // A backend without approval-notice.patch. The old wording, which
            // is worse but not wrong — better than a toast that says nothing
            // because a field it wanted was missing.
            _ => {
                let what = item["action"].as_str().unwrap_or("an action");
                (
                    "Jarvis is waiting on you".to_string(),
                    format!("{what} — nothing runs until you decide."),
                )
            }
        };

        // `action_type_id` is accepted by tauri-plugin-notification's builder
        // but the DESKTOP implementation (notify_rust, win7_notifications)
        // never reads it — actions are a mobile-only feature of that plugin.
        // Checked in tauri-plugin-notification-2.4.0/src/desktop.rs rather
        // than assumed. winrt_toast.rs goes around it with a real WinRT
        // toast on Windows; see that module's own doc for exactly what is
        // and is not verified about it. `deny_ok` is "always true" per
        // docs/ARCHITECTURE.md's own contract table, so no per-item check is
        // needed before offering the button.
        //
        // The tray's attention state is unconditional on any pending item,
        // heavy or not - that is the "waits to be found" half of the same
        // rule, a passive, glanceable signal rather than an interruption,
        // and it is correct for it to stay unconditional.
        #[cfg(windows)]
        {
            let id = approval_id(item).unwrap_or_default();
            crate::winrt_toast::notify_approval(app, &title, &body, &id);
        }
        #[cfg(not(windows))]
        crate::commands::notify(app, &title, &body);
    }

    crate::emit_all(
        app,
        crate::events::APPROVALS_CHANGED,
        serde_json::json!({ "count": items.len(), "items": items, "available": available }),
    );
    true
}

/// An approval row's id, as text. The gate's ids are strings today, but a
/// number is accepted too: reading only strings meant a numeric id was never
/// "seen", so it was never toasted and never counted as known - every
/// re-read looked like nothing had arrived. `jarvis-link.js` already turns a
/// number into a string (`String(row.id)`), so this is the same id the
/// windows answer with.
fn approval_id(item: &serde_json::Value) -> Option<String> {
    match &item["id"] {
        serde_json::Value::String(s) if !s.trim().is_empty() => Some(s.trim().to_string()),
        serde_json::Value::Number(n) => Some(n.to_string()),
        _ => None,
    }
}

/// Longest `expires_in` read as a real countdown. The shipped gate waits 180
/// seconds; anything over a day is a wrong unit or a bug, and showing no
/// countdown beats showing a wrong one.
const MAX_EXPIRES_IN_SECS: f64 = 24.0 * 3600.0;

/// Adds `expires_at_ms` (this machine's clock) to a row that carries
/// `expires_in` and no deadline of its own. Leaves every other row alone.
fn stamp_expiry(item: &mut serde_json::Value, now_ms: u64) {
    if item.get("expires_at_ms").is_some_and(|v| v.is_number()) {
        return;
    }
    let Some(secs) = item.get("expires_in").and_then(|v| v.as_f64()) else {
        return;
    };
    if !secs.is_finite() || !(0.0..=MAX_EXPIRES_IN_SECS).contains(&secs) {
        return;
    }
    if let Some(obj) = item.as_object_mut() {
        obj.insert(
            "expires_at_ms".to_string(),
            serde_json::json!(now_ms + (secs * 1000.0) as u64),
        );
    }
}

/// A read of `/api/pending` failed: the queue on screen is the last one we
/// knew, not the current one. Every failure path goes through here so none of
/// them can set `stale` and forget `queue_read`, or the other way round.
fn mark_queue_unread(app: &AppHandle) {
    app.state::<StreamState>()
        .queue_read
        .store(false, std::sync::atomic::Ordering::Relaxed);
    publish_link(app, |link| link.stale = true);
}

/// Whether a `hello` frame may clear `stale` on its own.
///
/// Only when the server says we are caught up (`hello_stale` false), the bus
/// has not been renumbered by a backend restart, AND the approval queue was
/// actually read on this connection. The last condition is the one that was
/// missing: `hello {stale: false}` says the EVENT ring is intact, not that we
/// hold the current queue.
fn hello_may_clear_stale(hello_stale: bool, renumbered: bool, queue_read: bool) -> bool {
    !(hello_stale || renumbered) && queue_read
}

/// Applies a link change and, if anything moved, tells every window and repaints
/// the tray. One function so a caller cannot update the state and forget one of
/// the two consumers.
pub(crate) fn publish_link<F: FnOnce(&mut LinkState)>(app: &AppHandle, edit: F) {
    let Some(next) = app.state::<StreamState>().update(edit) else {
        return;
    };
    crate::emit_all(app, crate::events::JARVIS_LINK, next.clone());
    crate::push_to_hud(app, "link", &next);
    // A first launch built the HUD before the backend wrote its token; the
    // link changing is when that token certainly exists. No-op if unchanged.
    crate::configure_hud(app);
    crate::tray::on_link_changed(app, &next);
}

// ---------------------------------------------------------------------------
// Resume point
// ---------------------------------------------------------------------------

fn load_resume(app: &AppHandle) -> u64 {
    use tauri_plugin_store::StoreExt;
    app.store(commands::SETTINGS_STORE)
        .ok()
        .and_then(|store| store.get(RESUME_KEY))
        .and_then(|value| value.as_u64())
        .unwrap_or(0)
}

/// Writes the resume point, at most every [`RESUME_SAVE_INTERVAL`] unless
/// `force` (which the disconnect path passes, because the next thing that
/// happens may be the process going away).
fn save_resume(app: &AppHandle, force: bool) {
    use tauri_plugin_store::StoreExt;
    static LAST: Mutex<Option<Instant>> = Mutex::new(None);

    let id = app.state::<StreamState>().link().last_id;
    if id == 0 {
        return;
    }
    {
        let mut last = LAST.lock().unwrap_or_else(|p| p.into_inner());
        let due = last.is_none_or(|at| at.elapsed() >= RESUME_SAVE_INTERVAL);
        if !force && !due {
            return;
        }
        *last = Some(Instant::now());
    }
    if let Ok(store) = app.store(commands::SETTINGS_STORE) {
        store.set(RESUME_KEY, serde_json::json!(id));
        if let Err(err) = store.save() {
            eprintln!("[jarvis] unable to persist the event resume point: {err}");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The default must be stale: before the first hello nothing is known, and
    /// a UI that enables approve/deny on launch would be answering a queue it
    /// has not read.
    #[test]
    fn activity_state_reads_both_shapes() {
        let flat = serde_json::json!({"state": "thinking"});
        let noted = serde_json::json!({"key": "activity",
            "value": {"state": "working", "detail": "Using calculator..."}});
        assert_eq!(activity_state(&flat), Some("thinking"));
        assert_eq!(activity_state(&noted), Some("working"));
        assert_eq!(activity_state(&serde_json::json!({})), None);
    }

    /// The reconnect case from the audit: the queue read made just before the
    /// hello frame failed (backend restarting, 503), then `hello {stale:
    /// false}` arrived. Approve and Deny must stay disabled.
    #[test]
    fn a_clean_hello_after_a_failed_queue_read_stays_stale() {
        assert!(!hello_may_clear_stale(false, false, false));
    }

    #[test]
    fn a_clean_hello_after_a_good_queue_read_clears_stale() {
        assert!(hello_may_clear_stale(false, false, true));
    }

    #[test]
    fn a_stale_or_renumbered_hello_never_clears_stale_by_itself() {
        // Those two re-read everything first and clear `stale` only if the
        // re-read lands; the hello alone never does.
        assert!(!hello_may_clear_stale(true, false, true));
        assert!(!hello_may_clear_stale(false, true, true));
        assert!(!hello_may_clear_stale(true, true, false));
    }

    #[test]
    fn a_fresh_state_has_not_read_the_queue() {
        let state = StreamState::default();
        assert!(!state.queue_read.load(std::sync::atomic::Ordering::Relaxed));
    }

    #[test]
    fn an_approval_id_may_be_a_string_or_a_number() {
        assert_eq!(
            approval_id(&serde_json::json!({"id": "a1"})),
            Some("a1".to_string())
        );
        assert_eq!(
            approval_id(&serde_json::json!({"id": 12})),
            Some("12".to_string())
        );
        assert_eq!(approval_id(&serde_json::json!({"id": ""})), None);
        assert_eq!(approval_id(&serde_json::json!({"id": null})), None);
        assert_eq!(approval_id(&serde_json::json!({})), None);
    }

    #[test]
    fn expires_in_becomes_a_deadline_at_read_time() {
        let mut row = serde_json::json!({"id": "a1", "expires_in": 150});
        stamp_expiry(&mut row, 1_000_000);
        assert_eq!(row["expires_at_ms"], serde_json::json!(1_150_000u64));

        // A deadline the server already sent is kept.
        let mut kept = serde_json::json!({"expires_at_ms": 5, "expires_in": 150});
        stamp_expiry(&mut kept, 1_000_000);
        assert_eq!(kept["expires_at_ms"], serde_json::json!(5));

        // Absent, negative, or absurd: no countdown rather than a wrong one.
        for bad in [
            serde_json::json!({}),
            serde_json::json!({"expires_in": -1}),
            serde_json::json!({"expires_in": "150"}),
            serde_json::json!({"expires_in": 90_000_000}),
        ] {
            let mut row = bad.clone();
            stamp_expiry(&mut row, 1_000_000);
            assert!(row.get("expires_at_ms").is_none(), "{bad}");
        }
    }

    #[test]
    fn starts_stale() {
        let link = LinkState::default();
        assert!(link.stale);
        assert!(!link.connected);
        assert_eq!(link.approvals, 0);
    }
}
