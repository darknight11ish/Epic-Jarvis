//! Settings -> "Devices": pairing a phone by QR code, with a key per device
//! (docs/PAIRING-DESIGN.md, phase 1 - the owner's "build QR-code pairing
//! now", 2026-09-28). The routes are the design's section 6, frozen for the
//! three builders (backend, phone, this app); nothing here changes them.
//!
//! Seven commands, settings window only (permissions/surfaces.toml,
//! `settings-surface`):
//!
//! * [`pair_phone_address`] - the name the phone reaches this PC at, for the
//!   QR code: the one the owner typed last time, else this PC's Tailscale
//!   name from `tailscale status --json` (a local, read-only command with a
//!   2-second limit; nothing is sent anywhere), else nothing - typed once.
//! * [`pair_start`] - `POST /api/pair/start {"address", "port"?}` (PC only).
//!   The answer's `qr` text is turned into a picture HERE, with the
//!   `qrcodegen` crate, and thrown away: the page gets the SVG, the typed
//!   backup code, the countdown and the tries left - never the QR text,
//!   whose secret would otherwise sit in the page's scripts (design 8.2).
//!   Before the code is handed to the page the settings window is hidden
//!   from screen capture (design 7.1). Held on a stale link: it ends in an
//!   approval card.
//! * [`pair_session`] - `GET /api/pair/session`, read every 2 s while the
//!   panel is open: the state, the countdown, the phone's name and the four
//!   words once it has asked, and the PC's own sentence for the state. The
//!   capture guard comes off as soon as the session has ended.
//! * [`pair_cancel`] - `POST /api/pair/cancel {}`. Never held; it only takes
//!   something away. The capture guard comes off.
//! * [`devices_list`] - `GET /api/devices`. A read.
//! * [`devices_remove`] - `POST /api/devices/remove {"id"}`: ONE device,
//!   immediate, no card (it only takes access away, like Forget). Never held
//!   on a stale link (design 12, rule 4: only a loosening waits).
//! * [`devices_shared`] - `POST /api/devices/shared {"retired"}`: Retire is
//!   stricter, immediate and never held; Bring it back is looser - one card
//!   with Windows Hello on the PC - and held on a stale link.
//!
//! The approval itself - "Jarvis wants to connect a new device" - is an
//! ordinary card, answered in the Jarvis bar or the widget through
//! [`crate::commands::decide_approval`] like every other one, with Windows
//! Hello asked by the backend. Nothing here approves anything.
//!
//! The token goes out in `X-Jarvis-Token` through
//! [`crate::commands::jarvis_headers`], never logged. The QR text and the
//! typed code are never logged either: no `println!` below prints an answer.

use std::time::Duration;

use tauri::{AppHandle, Manager};

use crate::commands::{
    backend_refusal, backend_unreachable, jarvis_base, jarvis_client, jarvis_headers,
    own_network_host, SETTINGS_STORE,
};

pub(crate) const LIST_PATH: &str = "/api/devices";
const VERSION_PATH: &str = "/api/version";
const REMOVE_PATH: &str = "/api/devices/remove";
const LABEL_PATH: &str = "/api/devices/label";
const SHARED_PATH: &str = "/api/devices/shared";
const PAIR_START_PATH: &str = "/api/pair/start";
const PAIR_SESSION_PATH: &str = "/api/pair/session";
const PAIR_CANCEL_PATH: &str = "/api/pair/cancel";

/// Where the address typed for the QR code is remembered (design 4: it is
/// not a secret, so the ordinary settings store).
pub(crate) const ADDRESS_KEY: &str = "pair_phone_address";

/// What a PC whose backend has no `jarvis_devices.py` answers (a 404 - the
/// route is not there, design 6).
pub(crate) const PAIRING_MISSING: &str = "Your PC's Jarvis cannot pair phones by QR code yet - \
     run apply-patches.ps1 on this PC. Until then, your phone keeps using the old shared key \
     (Settings, Connection).";

const STALE: &str =
    "The connection to Jarvis is catching up, so nothing can be sent until it does.";

const UNREADABLE: &str = "Jarvis answered, but not in a way this app can read. Update the \
                          backend by running apply-patches.ps1.";

/// The QR text did not have the design's shape (8.4). The session is
/// cancelled rather than a picture drawn of something unexpected.
pub(crate) const NOT_A_CODE: &str = "That is not a Jarvis pairing code.";
pub(crate) const NEWER_CODE: &str = "This code is from a newer Jarvis - update the app.";

/// A device key refused because the owner removed it (design 5.3). The
/// design's sentence speaks to a phone; this app is a computer, so it says
/// the same thing in a computer's words. A desktop never gets a device key
/// by pairing (only phones pair), so this is a key typed into Settings by
/// hand.
pub(crate) const KEY_REMOVED: &str = "The key this app uses was removed on the PC running \
     Jarvis, so Jarvis no longer answers it. In Settings, Connection, clear the token to go \
     back to Jarvis's own.";

/// The old shared key, used from another computer after the owner retired
/// it (design 5.3). Only a Jarvis Desktop on a DIFFERENT computer can hit
/// this: from the PC itself the shared key always works (design 2.3).
pub(crate) const SHARED_RETIRED: &str = "This computer was using the old shared key, which \
     has been retired on the PC running Jarvis, so Jarvis no longer answers it from here. On \
     that PC, open Settings, Devices, and press Bring it back.";

/// The design's 409 `uses_it_yourself` sentence (6.4), for an answer that
/// carries only the reason.
const USES_IT_YOURSELF: &str = "This device is still using the old shared key. Pair it with \
     the QR code first, or it would cut itself off.";

const NO_SUCH_DEVICE: &str = "That device is not paired any more.";

const READ_TIMEOUT: Duration = Duration::from_secs(15);
/// `tailscale status` normally answers in well under a second (design 8.1:
/// "if the Tailscale command answers within 2 s").
const TAILSCALE_LIMIT: Duration = Duration::from_secs(2);

/// The session states in which a code or the four words are on screen, so
/// the window stays hidden from screen capture (design 3).
const ACTIVE: [&str; 3] = ["waiting_for_phone", "waiting_for_card", "approved"];

/// The fields of `GET /api/pair/session` the page gets - all of them in the
/// design (6.1). A whitelist, so if a backend ever put the code or the
/// secret into this answer by mistake, it would still not reach the page.
const SESSION_FIELDS: [&str; 7] = [
    "state",
    "expires_in",
    "tries_left",
    "device_name",
    "words",
    "wrong_tries_from",
    "message",
];

// ---------------------------------------------------------------------------
// The QR text (design 8.4) and its picture (8.2)
// ---------------------------------------------------------------------------

/// One QR text, read by the design's strict rule (8.4):
/// `jarvis-pair:1/<host>/<port>/<pair_id>/<secret>/<expires>`.
#[derive(Debug, PartialEq, Eq)]
pub(crate) struct PairQr<'a> {
    pub host: &'a str,
    pub port: u16,
    pub pair_id: &'a str,
    pub secret: &'a str,
    pub expires: u64,
}

/// Reads a QR text by the design's rule, or says why not. The same cases
/// the backend (Python) and the phone (Kotlin) check; one shape, no URL
/// library guessing at an odd string.
pub(crate) fn parse_pair_qr(text: &str) -> Result<PairQr<'_>, &'static str> {
    let rest = text.strip_prefix("jarvis-pair:").ok_or(NOT_A_CODE)?;
    let parts: Vec<&str> = rest.split('/').collect();
    let version = parts[0];
    if version != "1" {
        // A plain number other than 1 is a later format; anything else is
        // not a pairing code at all.
        let newer = !version.is_empty()
            && version.len() <= 4
            && version.bytes().all(|b| b.is_ascii_digit())
            && !version.starts_with('0');
        return Err(if newer { NEWER_CODE } else { NOT_A_CODE });
    }
    let [_, host, port, pair_id, secret, expires] = parts[..] else {
        return Err(NOT_A_CODE);
    };
    if !phone_host_ok(host) {
        return Err(NOT_A_CODE);
    }
    let port = plain_number(port, 5)
        .filter(|p| (1..=65535).contains(p))
        .ok_or(NOT_A_CODE)? as u16;
    let hex_id = pair_id.len() == 16
        && pair_id
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b));
    if !hex_id {
        return Err(NOT_A_CODE);
    }
    let secret_ok = secret.len() == 22
        && secret
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_');
    if !secret_ok {
        return Err(NOT_A_CODE);
    }
    if expires.len() != 10 {
        return Err(NOT_A_CODE);
    }
    let expires = plain_number(expires, 10).ok_or(NOT_A_CODE)?;
    Ok(PairQr {
        host,
        port,
        pair_id,
        secret,
        expires,
    })
}

/// Digits only, at most `max` of them, no leading zero (a `0` alone is
/// read as 0, which no field accepts).
fn plain_number(text: &str, max: usize) -> Option<u64> {
    if text.is_empty() || text.len() > max || !text.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    if text.len() > 1 && text.starts_with('0') {
        return None;
    }
    text.parse().ok()
}

/// The phone's own host rule (design 8.4): lower case `[a-z0-9.-]`, 1-253
/// characters, a Tailscale (`.ts.net`) or NordVPN Meshnet (`.nord`) name,
/// and on the owner's own networks by the shared rule.
pub(crate) fn phone_host_ok(host: &str) -> bool {
    (1..=253).contains(&host.len())
        && host
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'.' || b == b'-')
        && (host.ends_with(".ts.net") || host.ends_with(".nord"))
        && own_network_host(host)
}

/// The typed backup code as the backend gives it (design 8.5): 8
/// characters from Crockford's alphabet, shown as `K7QM-4TXD`. Anything
/// else is not shown - the backend is updated to match, not guessed at.
pub(crate) fn code_ok(code: &str) -> bool {
    let plain: String = code.chars().filter(|c| *c != '-').collect();
    plain.len() == 8
        && plain
            .bytes()
            .all(|b| b.is_ascii_digit() || (b.is_ascii_uppercase() && !b"ILOU".contains(&b)))
        && code.len() <= 9
}

/// The QR code as an SVG picture, and its QR version (its size class).
///
/// Error correction level M, as the design asks (the library may raise it
/// when that fits in the same size, which only makes it easier to read).
/// Black squares on white with the standard 4-square quiet border, whatever
/// the app's theme: a camera reads dark-on-light codes, not the other way.
pub(crate) fn qr_svg(text: &str) -> Result<(String, u8), String> {
    use qrcodegen::{QrCode, QrCodeEcc};
    use std::fmt::Write;

    let qr = QrCode::encode_text(text, QrCodeEcc::Medium)
        .map_err(|_| "The pairing code is too long to draw.".to_string())?;
    let border = 4;
    let size = qr.size();
    let dim = size + border * 2;
    let mut path = String::with_capacity((size * size) as usize * 6);
    for y in 0..size {
        for x in 0..size {
            if qr.get_module(x, y) {
                let _ = write!(path, "M{},{}h1v1h-1z", x + border, y + border);
            }
        }
    }
    let svg = format!(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 {dim} {dim}\" \
         shape-rendering=\"crispEdges\"><rect width=\"{dim}\" height=\"{dim}\" \
         fill=\"#ffffff\"/><path d=\"{path}\" fill=\"#000000\"/></svg>"
    );
    Ok((svg, qr.version().value()))
}

/// [`qr_svg`] as a `data:` address the page's `<img>` can show - the page
/// policy allows `img-src data:` (tauri.conf.json), and nothing is fetched.
pub(crate) fn qr_data_uri(text: &str) -> Result<String, String> {
    use base64::Engine;

    let (svg, _) = qr_svg(text)?;
    Ok(format!(
        "data:image/svg+xml;base64,{}",
        base64::engine::general_purpose::STANDARD.encode(svg)
    ))
}

// ---------------------------------------------------------------------------
// The address the phone reaches this PC at (design 8.1)
// ---------------------------------------------------------------------------

/// The owner's typing, made into `(host, port)`: a leading `http://` or
/// `https://` and a trailing `/` are dropped, a `:port` is split off, and
/// the name is lower-cased. Whether the name passes the phone's rule is the
/// backend's call (its 400 carries the phone's own sentence); this only
/// refuses what could not be a name at all.
pub(crate) fn split_address(typed: &str) -> Result<(String, Option<u16>), &'static str> {
    const TYPE_IT: &str = "Type the name your phone reaches this PC at - it ends in .ts.net \
                           (Tailscale) or .nord (NordVPN Meshnet).";
    let t = typed.trim();
    let t = t
        .strip_prefix("http://")
        .or_else(|| t.strip_prefix("https://"))
        .unwrap_or(t);
    let t = t.trim_end_matches('/');
    let (host, port) = match t.rsplit_once(':') {
        Some((host, port)) => {
            let port = plain_number(port, 5)
                .filter(|p| (1..=65535).contains(p))
                .ok_or(TYPE_IT)? as u16;
            (host, Some(port))
        }
        None => (t, None),
    };
    let host = host.trim_end_matches('.').to_lowercase();
    if host.is_empty()
        || host.len() > 253
        || host
            .chars()
            .any(|c| c.is_whitespace() || c.is_control() || "/@?#\\[]".contains(c))
    {
        return Err(TYPE_IT);
    }
    Ok((host, port))
}

/// `host` or `host:port`, as it is remembered and shown back.
fn address_text(host: &str, port: Option<u16>) -> String {
    match port {
        Some(p) => format!("{host}:{p}"),
        None => host.to_string(),
    }
}

/// This PC's Tailscale name from `tailscale status --json`'s
/// `Self.DNSName`, trailing dot removed - or `None` when it is missing or
/// is not a name the phone may use.
pub(crate) fn tailscale_name(json: &str) -> Option<String> {
    let v: serde_json::Value = serde_json::from_str(json).ok()?;
    let name = v.get("Self")?.get("DNSName")?.as_str()?;
    let name = name.trim().trim_end_matches('.').to_lowercase();
    (name.ends_with(".ts.net") && phone_host_ok(&name)).then_some(name)
}

/// Runs `tailscale status --json --peers=false` with a 2-second limit.
/// `--peers=false` keeps the answer small (only this PC); the output is
/// read on its own thread while the command runs, so a long answer can
/// never fill the pipe and stall it. **Unverified on Windows** (design 10,
/// the half-hour test): if the command is missing or answers differently,
/// this gives `None` and the owner types the name once.
fn ask_tailscale() -> Option<String> {
    let mut candidates = vec![std::path::PathBuf::from("tailscale")];
    if let Some(pf) = std::env::var_os("ProgramFiles") {
        candidates.push(
            std::path::Path::new(&pf)
                .join("Tailscale")
                .join("tailscale.exe"),
        );
    }
    for program in candidates {
        let mut command = std::process::Command::new(&program);
        command.args(["status", "--json", "--peers=false"]);
        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            command.creation_flags(CREATE_NO_WINDOW);
        }
        if let Some(out) = run_briefly(command, TAILSCALE_LIMIT) {
            return tailscale_name(&out);
        }
    }
    None
}

/// A command's standard output, or `None` when it could not start, failed,
/// or did not finish within `limit` (it is then killed).
fn run_briefly(mut command: std::process::Command, limit: Duration) -> Option<String> {
    use std::io::Read;
    use std::process::Stdio;

    command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    let mut child = command.spawn().ok()?;
    let mut pipe = child.stdout.take()?;
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        let mut out = Vec::new();
        let _ = pipe.by_ref().take(1 << 20).read_to_end(&mut out);
        let _ = tx.send(out);
    });
    let out = match rx.recv_timeout(limit) {
        Ok(out) => out,
        Err(_) => {
            let _ = child.kill();
            let _ = child.wait();
            return None;
        }
    };
    let status = child.wait().ok()?;
    status
        .success()
        .then(|| String::from_utf8_lossy(&out).into_owned())
}

fn remembered_address(app: &AppHandle) -> Option<String> {
    use tauri_plugin_store::StoreExt;

    app.store(SETTINGS_STORE)
        .ok()
        .and_then(|store| store.get(ADDRESS_KEY))
        .and_then(|v| v.as_str().map(str::to_string))
        .filter(|a| !a.trim().is_empty())
}

fn remember_address(app: &AppHandle, address: &str) {
    use tauri_plugin_store::StoreExt;

    if let Ok(store) = app.store(SETTINGS_STORE) {
        store.set(ADDRESS_KEY, serde_json::json!(address));
        if let Err(e) = store.save() {
            // Not remembered: the owner types it again next time. Nothing
            // else is lost. The address is not a secret, but it is not
            // printed either - the log needs only that it failed.
            eprintln!("[jarvis] the pairing address could not be remembered: {e}");
        }
    }
}

// ---------------------------------------------------------------------------
// Reading the answers (tested below without a network)
// ---------------------------------------------------------------------------

fn json_object(body: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()
        .filter(|v| v.is_object())
}

fn reason(body: &str) -> Option<String> {
    json_object(body)?
        .get("reason")?
        .as_str()
        .map(str::to_string)
}

/// The words for a key the backend refused with a reason (design 5.3), or
/// `None` for any other answer. Read wherever this app shows why Jarvis
/// refused it: the event stream's 401 and [`backend_refusal`].
pub(crate) fn refused_key_words(body: &str) -> Option<&'static str> {
    match json_object(body)?.get("key")?.as_str()? {
        "device_removed" => Some(KEY_REMOVED),
        "shared_retired" => Some(SHARED_RETIRED),
        _ => None,
    }
}

/// `GET /api/devices`: the PC's own answer, with any key or key hash taken
/// out defensively (the backend promises never to send one, design 6.4);
/// a PC without pairing is `{"available": false, "why": ...}`.
pub(crate) fn list_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if status == 404 {
        return Ok(serde_json::json!({ "available": false, "why": PAIRING_MISSING }));
    }
    if !(200..300).contains(&status) {
        return Err(backend_refusal(status, body));
    }
    let mut v = json_object(body)
        .filter(|v| v.get("devices").is_some_and(|d| d.is_array()))
        .ok_or_else(|| UNREADABLE.to_string())?;
    if let Some(rows) = v.get_mut("devices").and_then(|d| d.as_array_mut()) {
        for row in rows.iter_mut() {
            if let Some(row) = row.as_object_mut() {
                row.remove("token");
                row.remove("token_sha256");
            }
        }
    }
    v["available"] = serde_json::json!(true);
    Ok(v)
}

/// Whether `GET /api/version` says this backend has signed approvals
/// (`capabilities.pairing.signed_approvals` is `true`, docs/PAIRING-DESIGN.md
/// section 11). Anything else - an older backend, an unreadable answer, an
/// error status - is "no", so the page then shows nothing extra.
pub(crate) fn signed_approvals_in_version(status: u16, body: &str) -> bool {
    (200..300).contains(&status)
        && serde_json::from_str::<serde_json::Value>(body)
            .ok()
            .and_then(|v| v["capabilities"]["pairing"]["signed_approvals"].as_bool())
            .unwrap_or(false)
}

/// `GET /api/pair/session`, cut down to the design's fields.
pub(crate) fn session_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if status == 404 {
        return Ok(serde_json::json!({ "state": "none", "available": false,
                                      "why": PAIRING_MISSING }));
    }
    if !(200..300).contains(&status) {
        return Err(backend_refusal(status, body));
    }
    let v = json_object(body)
        .filter(|v| v.get("state").is_some_and(|s| s.is_string()))
        .ok_or_else(|| UNREADABLE.to_string())?;
    let mut out = serde_json::Map::new();
    for field in SESSION_FIELDS {
        if let Some(value) = v.get(field) {
            out.insert(field.to_string(), value.clone());
        }
    }
    Ok(serde_json::Value::Object(out))
}

/// Whether a session in `state` still shows a code or the words.
pub(crate) fn session_active(state: &str) -> bool {
    ACTIVE.contains(&state)
}

/// What [`pair_start`] keeps from the PC's answer: the QR text (drawn, then
/// dropped), the typed code, and the two numbers.
#[derive(Debug)]
pub(crate) struct Started {
    pub qr: String,
    pub code: String,
    pub expires_in: u64,
    pub tries_left: u64,
}

/// `POST /api/pair/start`'s answer. A 200 whose QR text or code does not
/// have the design's shape is refused (the caller then cancels the
/// session), rather than drawn or shown.
pub(crate) fn start_answer(status: u16, body: &str) -> Result<Started, String> {
    if status == 404 {
        return Err(PAIRING_MISSING.to_string());
    }
    if !(200..300).contains(&status) {
        return Err(backend_refusal(status, body));
    }
    let v = json_object(body).ok_or_else(|| UNREADABLE.to_string())?;
    let qr = v.get("qr").and_then(|q| q.as_str()).unwrap_or("");
    let code = v.get("code").and_then(|c| c.as_str()).unwrap_or("");
    if v.get("ok").and_then(|o| o.as_bool()) != Some(true) {
        return Err(UNREADABLE.to_string());
    }
    parse_pair_qr(qr).map_err(str::to_string)?;
    if !code_ok(code) {
        return Err(UNREADABLE.to_string());
    }
    Ok(Started {
        qr: qr.to_string(),
        code: code.to_string(),
        expires_in: v.get("expires_in").and_then(|e| e.as_u64()).unwrap_or(600),
        tries_left: v.get("tries_left").and_then(|t| t.as_u64()).unwrap_or(3),
    })
}

/// A device's id as the design gives it (5.1): `d` and 8 lowercase hex
/// characters. `"pc"` is not removable and is refused here too.
pub(crate) fn device_id_ok(id: &str) -> bool {
    id.len() == 9
        && id.starts_with('d')
        && id[1..]
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

/// What the owner reads when a label could not be accepted (the PC's own
/// sentence, word for word: `jarvis_devices.DEVICES_WORDS["bad_label"]`).
/// Kept here so a label is refused before it makes a round trip, and checked
/// against the backend's copy by `backend/test_devices.py`.
pub(crate) const LABEL_BAD: &str = concat!(
    "Use a shorter label, with letters, numbers, spaces and - _ . ' ( ) only. ",
    "Leave it empty to go back to the name the device gave itself."
);

/// The owner's own label for a device: 0-40 characters, letters and digits of
/// any script, space, and `- _ . ' ( )`. The same rule the PC applies and the
/// same rule a paired device's name is held to (`jarvis_devices.name_ok`) -
/// a label is shown in both apps' device lists and inside a pairing card, so
/// it must not be able to fake a card's words. An empty label is valid: it
/// clears the label and the device goes back to the name it gave itself.
pub(crate) fn label_ok(label: &str) -> bool {
    if label.is_empty() {
        return true;
    }
    if label.chars().count() > 40 {
        return false;
    }
    label
        .chars()
        .all(|c| c.is_alphanumeric() || matches!(c, ' ' | '-' | '_' | '.' | '\'' | '(' | ')'))
}

/// A change's answer (remove, retire, bring back, cancel).
pub(crate) fn change_answer(status: u16, body: &str) -> Result<serde_json::Value, String> {
    if (200..300).contains(&status) {
        let mut v = json_object(body).ok_or_else(|| UNREADABLE.to_string())?;
        v["http"] = serde_json::json!(status);
        return Ok(v);
    }
    let why = reason(body);
    if status == 404 {
        return Err(match why.as_deref() {
            Some("no_such_device") => NO_SUCH_DEVICE.to_string(),
            _ => PAIRING_MISSING.to_string(),
        });
    }
    let said = json_object(body)
        .and_then(|v| v.get("error").and_then(|e| e.as_str()).map(str::to_string))
        .filter(|e| !e.trim().is_empty());
    if said.is_none() && why.as_deref() == Some("uses_it_yourself") {
        return Err(USES_IT_YOURSELF.to_string());
    }
    Err(backend_refusal(status, body))
}

// ---------------------------------------------------------------------------
// The settings window's screen-capture guard (design 7.1)
// ---------------------------------------------------------------------------
//
// ON while a pairing code or the four words are on screen, OFF once the session
// ends or the panel closes - the design's own shape ("put back when the panel
// closes").
//
// Why this is not Tauri's `set_content_protected`, which is the obvious call:
// on Windows that reaches `SetWindowDisplayAffinity`, and tao applies it by
// RECREATING the window. Pressing "Pair a phone" therefore closed the Settings
// window exactly as the pairing succeeded - the code never appeared and nothing
// was logged, because the window was rebuilt rather than crashed. The owner's
// report, 2026-10-07: "when i go to devices in the settings to pair a phone and
// click pair it closes the settings on desktop".
//
// The first fix removed the toggle and set the guard once at window creation.
// The owner asked for the toggle back the same day, on condition that it cannot
// close the window - so the Win32 call is made directly, on the window this app
// already owns. `SetWindowDisplayAffinity` changes an attribute of an existing
// window; it does not touch how the window was created, so nothing is rebuilt
// and Settings stays open. `WDA_EXCLUDEFROMCAPTURE` needs Windows 10 2004 or
// newer; where it is refused the code is still shown, which is the same failure
// the old helper had (a cheap guard against the easiest copy, not a wall -
// ARCHITECTURE section 3).

/// Hides the settings window from screenshots, screen recordings and screen
/// sharing (`on`), or puts it back. No window, or a refusal, is logged and
/// otherwise ignored: the code is still shown.
fn guard_capture(app: &AppHandle, on: bool) {
    let Some(window) = app.get_webview_window(crate::windows::SETTINGS_LABEL) else {
        return;
    };
    #[cfg(windows)]
    {
        use windows_sys::Win32::UI::WindowsAndMessaging::{
            SetWindowDisplayAffinity, WDA_EXCLUDEFROMCAPTURE, WDA_NONE,
        };
        let Ok(handle) = window.hwnd() else {
            eprintln!("[jarvis] could not read the settings window's handle for the capture guard");
            return;
        };
        // SAFETY: `handle` is this app's own settings-window handle, read back
        // from Tauri. SetWindowDisplayAffinity only sets an attribute on it -
        // unlike set_content_protected, it cannot rebuild the window.
        let ok = unsafe {
            SetWindowDisplayAffinity(
                handle.0 as _,
                if on { WDA_EXCLUDEFROMCAPTURE } else { WDA_NONE },
            )
        };
        if ok == 0 {
            eprintln!(
                "[jarvis] could not {} the settings window's capture guard: {}",
                if on { "set" } else { "clear" },
                std::io::Error::last_os_error()
            );
        }
    }
    #[cfg(not(windows))]
    {
        let _ = (window, on);
    }
}

// ---------------------------------------------------------------------------
// The commands
// ---------------------------------------------------------------------------

fn stale(app: &AppHandle) -> bool {
    app.state::<crate::stream::StreamState>().link().stale
}

async fn get_raw(app: &AppHandle, path: &str) -> Result<(u16, String), String> {
    let base = jarvis_base(app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .get(format!("{base}{path}"))
        .headers(jarvis_headers(app)?)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    Ok((status, response.text().await.unwrap_or_default()))
}

async fn post_raw(
    app: &AppHandle,
    path: &str,
    body: serde_json::Value,
) -> Result<(u16, String), String> {
    let base = jarvis_base(app);
    let response = jarvis_client(Some(READ_TIMEOUT))?
        .post(format!("{base}{path}"))
        .headers(jarvis_headers(app)?)
        .json(&body)
        .send()
        .await
        .map_err(|e| backend_unreachable(&e, &base))?;
    let status = response.status().as_u16();
    Ok((status, response.text().await.unwrap_or_default()))
}

/// The name to put in the QR code: `{"address", "source"}`, source
/// `"remembered"`, `"tailscale"` or `null` (nothing found - typed once).
#[tauri::command]
pub async fn pair_phone_address(app: AppHandle) -> serde_json::Value {
    if let Some(address) = remembered_address(&app) {
        return serde_json::json!({ "address": address, "source": "remembered" });
    }
    let found = tauri::async_runtime::spawn_blocking(ask_tailscale)
        .await
        .ok()
        .flatten();
    match found {
        Some(name) => serde_json::json!({ "address": name, "source": "tailscale" }),
        None => serde_json::json!({ "address": null, "source": null }),
    }
}

/// Starts a pairing session: `{"ok", "qr_svg", "code", "expires_in",
/// "tries_left"}`. The QR text itself never leaves this function.
#[tauri::command]
pub async fn pair_start(app: AppHandle, address: String) -> Result<serde_json::Value, String> {
    if stale(&app) {
        return Err(STALE.to_string());
    }
    let (host, port) = split_address(&address).map_err(str::to_string)?;
    let mut body = serde_json::json!({ "address": host });
    if let Some(port) = port {
        body["port"] = serde_json::json!(port);
    }
    let (status, text) = post_raw(&app, PAIR_START_PATH, body).await?;
    let started = match start_answer(status, &text) {
        Ok(started) => started,
        Err(problem) => {
            if (200..300).contains(&status) {
                // The PC made a session this app cannot show: end it, so no
                // code is left working that nobody can see.
                let _ = post_raw(&app, PAIR_CANCEL_PATH, serde_json::json!({})).await;
            }
            return Err(problem);
        }
    };
    let picture = match qr_data_uri(&started.qr) {
        Ok(picture) => picture,
        Err(problem) => {
            let _ = post_raw(&app, PAIR_CANCEL_PATH, serde_json::json!({})).await;
            return Err(problem);
        }
    };
    remember_address(&app, &address_text(&host, port));
    // Before the code reaches the page, never after (design 7.1).
    guard_capture(&app, true);
    Ok(serde_json::json!({
        "ok": true,
        "qr_svg": picture,
        "code": started.code,
        "expires_in": started.expires_in,
        "tries_left": started.tries_left,
    }))
}

/// The pairing session's state, for the panel's status line. The capture
/// guard comes off once the session has ended.
#[tauri::command]
pub async fn pair_session(app: AppHandle) -> Result<serde_json::Value, String> {
    let (status, text) = get_raw(&app, PAIR_SESSION_PATH).await?;
    let view = session_answer(status, &text)?;
    let state = view.get("state").and_then(|s| s.as_str()).unwrap_or("none");
    if !session_active(state) {
        guard_capture(&app, false);
    }
    Ok(view)
}

/// Ends the pairing session (and withdraws its card, if one waits). The
/// capture guard comes off whatever the PC answers.
#[tauri::command]
pub async fn pair_cancel(app: AppHandle) -> Result<serde_json::Value, String> {
    guard_capture(&app, false);
    let (status, text) = post_raw(&app, PAIR_CANCEL_PATH, serde_json::json!({})).await?;
    change_answer(status, &text)
}

/// The paired devices and the old shared key's state. A read.
#[tauri::command]
pub async fn devices_list(app: AppHandle) -> Result<serde_json::Value, String> {
    let (status, text) = get_raw(&app, LIST_PATH).await?;
    let mut out = list_answer(status, &text)?;
    // Whether the rows' `approval_key` means anything: asked of the version
    // page, best effort. A failed read is "no", never an error.
    let signed = match get_raw(&app, VERSION_PATH).await {
        Ok((code, body)) => signed_approvals_in_version(code, &body),
        Err(_) => false,
    };
    out["signed_approvals"] = serde_json::json!(signed);
    Ok(out)
}

/// Removes ONE device (never a list - there is no "remove all"). Immediate,
/// no card, not held on a stale link: it only takes access away.
#[tauri::command]
pub async fn devices_remove(app: AppHandle, id: String) -> Result<serde_json::Value, String> {
    if !device_id_ok(&id) {
        return Err("That is not a device this app can remove.".to_string());
    }
    let (status, text) = post_raw(&app, REMOVE_PATH, serde_json::json!({ "id": id })).await?;
    change_answer(status, &text)
}

/// The owner's own name for a device (docs/MULTI-DEVICE-DESIGN.md, the first
/// slice, 2026-10-09). Immediate, no card and never held on a stale link: a
/// label grants nothing and revokes nothing - it is what the list calls a
/// device the owner already paired. An empty `label` clears it, and the
/// device goes back to the name it gave itself at pairing.
#[tauri::command]
pub async fn devices_label(
    app: AppHandle,
    id: String,
    label: String,
) -> Result<serde_json::Value, String> {
    if !device_id_ok(&id) {
        return Err("That is not a device this app can label.".to_string());
    }
    let label = label.trim().to_string();
    if !label_ok(&label) {
        // Refused here as well as on the PC: the PC's own sentence is the one
        // the owner reads, but a label that could never be accepted should
        // not make a round trip first.
        return Err(LABEL_BAD.to_string());
    }
    let (status, text) = post_raw(
        &app,
        LABEL_PATH,
        serde_json::json!({ "id": id, "label": label }),
    )
    .await?;
    change_answer(status, &text)
}

/// Retires the old shared key for other devices (`retired: true`,
/// immediate), or brings it back (`false`: one card with Windows Hello on
/// the PC, held on a stale link).
#[tauri::command]
pub async fn devices_shared(app: AppHandle, retired: bool) -> Result<serde_json::Value, String> {
    if !retired && stale(&app) {
        return Err(STALE.to_string());
    }
    let (status, text) =
        post_raw(&app, SHARED_PATH, serde_json::json!({ "retired": retired })).await?;
    change_answer(status, &text)
}

#[cfg(test)]
mod tests {
    use super::*;

    const EXAMPLE: &str = "jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/00112233445566ff/\
                           AAECAwQFBgcICQoLDA0ODw/1790000600";

    #[test]
    fn the_designs_example_reads() {
        let qr = parse_pair_qr(EXAMPLE).unwrap();
        assert_eq!(
            qr,
            PairQr {
                host: "jarvis-pc.tail1234.ts.net",
                port: 4719,
                pair_id: "00112233445566ff",
                secret: "AAECAwQFBgcICQoLDA0ODw",
                expires: 1_790_000_600,
            }
        );
        assert!(parse_pair_qr(
            "jarvis-pair:1/my-pc.nord/1/00112233445566ff/AAECAwQFBgcICQoLDA0ODw/1790000600"
        )
        .is_ok());
    }

    #[test]
    fn anything_off_the_shape_is_refused() {
        let bad = [
            "",
            "jarvis-pair:",
            "JARVIS-PAIR:1/jarvis-pc.tail1234.ts.net/4719/00112233445566ff/AAECAwQFBgcICQoLDA0ODw/1790000600",
            // Six parts exactly - one more, one fewer.
            "jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/00112233445566ff/AAECAwQFBgcICQoLDA0ODw/1790000600/x",
            "jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/00112233445566ff/AAECAwQFBgcICQoLDA0ODw",
            // Something before or after, or a space.
            " jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/00112233445566ff/AAECAwQFBgcICQoLDA0ODw/1790000600",
            "jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/00112233445566ff/AAECAwQFBgcICQoLDA0ODw/1790000600 ",
            // Host: upper case, not a mesh name, a number, the open internet.
            "jarvis-pair:1/Jarvis-PC.tail1234.ts.net/4719/00112233445566ff/AAECAwQFBgcICQoLDA0ODw/1790000600",
            "jarvis-pair:1/example.com/4719/00112233445566ff/AAECAwQFBgcICQoLDA0ODw/1790000600",
            "jarvis-pair:1/100.101.2.3/4719/00112233445566ff/AAECAwQFBgcICQoLDA0ODw/1790000600",
            "jarvis-pair:1/pc.local/4719/00112233445566ff/AAECAwQFBgcICQoLDA0ODw/1790000600",
            "jarvis-pair:1/evil.ts.net.example.com/4719/00112233445566ff/AAECAwQFBgcICQoLDA0ODw/1790000600",
            // Port: zero, leading zero, too big, not a number.
            "jarvis-pair:1/jarvis-pc.tail1234.ts.net/0/00112233445566ff/AAECAwQFBgcICQoLDA0ODw/1790000600",
            "jarvis-pair:1/jarvis-pc.tail1234.ts.net/04719/00112233445566ff/AAECAwQFBgcICQoLDA0ODw/1790000600",
            "jarvis-pair:1/jarvis-pc.tail1234.ts.net/65536/00112233445566ff/AAECAwQFBgcICQoLDA0ODw/1790000600",
            "jarvis-pair:1/jarvis-pc.tail1234.ts.net/+4719/00112233445566ff/AAECAwQFBgcICQoLDA0ODw/1790000600",
            // pair_id: upper-case hex, too short.
            "jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/00112233445566FF/AAECAwQFBgcICQoLDA0ODw/1790000600",
            "jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/00112233445566f/AAECAwQFBgcICQoLDA0ODw/1790000600",
            // Secret: 21 characters, padding, a plus.
            "jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/00112233445566ff/AAECAwQFBgcICQoLDA0OD/1790000600",
            "jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/00112233445566ff/AAECAwQFBgcICQoLDA0OD=/1790000600",
            "jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/00112233445566ff/AAECAwQFBgcICQoLDA0OD+/1790000600",
            // Expires: 9 or 11 digits.
            "jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/00112233445566ff/AAECAwQFBgcICQoLDA0ODw/179000060",
            "jarvis-pair:1/jarvis-pc.tail1234.ts.net/4719/00112233445566ff/AAECAwQFBgcICQoLDA0ODw/17900006000",
        ];
        for text in bad {
            assert_eq!(parse_pair_qr(text), Err(NOT_A_CODE), "{text:?}");
        }
        let newer = "jarvis-pair:2/jarvis-pc.tail1234.ts.net/4719/00112233445566ff/\
                     AAECAwQFBgcICQoLDA0ODw/1790000600";
        assert_eq!(parse_pair_qr(newer), Err(NEWER_CODE));
        assert_eq!(parse_pair_qr("jarvis-pair:x/a"), Err(NOT_A_CODE));
    }

    #[test]
    fn the_typed_code_is_eight_crockford_characters() {
        assert!(code_ok("K7QM-4TXD"));
        assert!(code_ok("K7QM4TXD"));
        for bad in [
            "K7QM-4TX",
            "K7QM-4TXDD",
            "K7QM-4TXI",
            "k7qm-4txd",
            "K7QM 4TXD",
            "",
            "K7-QM-4T-XD",
        ] {
            assert!(!code_ok(bad), "{bad}");
        }
    }

    /// Reads the SVG back into a grid of dark squares, so the tests check
    /// the picture itself, not only that some text came out.
    fn modules(svg: &str) -> (i32, std::collections::HashSet<(i32, i32)>) {
        let dim: i32 = svg
            .split("viewBox=\"0 0 ")
            .nth(1)
            .and_then(|s| s.split(' ').next())
            .and_then(|s| s.parse().ok())
            .expect("viewBox");
        let d = svg
            .split(" d=\"")
            .nth(1)
            .unwrap()
            .split('"')
            .next()
            .unwrap();
        let mut dark = std::collections::HashSet::new();
        for cmd in d.split('M').filter(|c| !c.is_empty()) {
            let xy = cmd
                .strip_suffix("h1v1h-1z")
                .expect("one square per command");
            let (x, y) = xy.split_once(',').unwrap();
            dark.insert((x.parse().unwrap(), y.parse().unwrap()));
        }
        (dim, dark)
    }

    #[test]
    fn the_picture_is_well_formed_and_holds_the_code() {
        let (svg, version) = qr_svg(EXAMPLE).unwrap();
        assert!(svg.starts_with("<svg xmlns=\"http://www.w3.org/2000/svg\""));
        assert!(svg.ends_with("</svg>"));
        assert_eq!(
            svg.matches('<').count(),
            4,
            "svg, rect, path and the closing tag"
        );
        // Nothing in the picture but squares: the text itself is not in it.
        assert!(!svg.contains("jarvis-pair"));
        assert!(!svg.contains("AAECAwQFBgcICQoLDA0ODw"));
        assert!((1..=7).contains(&version), "version {version}");

        let qr = qrcodegen::QrCode::encode_text(EXAMPLE, qrcodegen::QrCodeEcc::Medium).unwrap();
        let (dim, dark) = modules(&svg);
        assert_eq!(dim, qr.size() + 8, "a 4-square quiet border on each side");
        for y in 0..qr.size() {
            for x in 0..qr.size() {
                assert_eq!(qr.get_module(x, y), dark.contains(&(x + 4, y + 4)));
            }
        }
        // The top-left finder pattern: a dark 7x7 ring.
        for i in 0..7 {
            assert!(dark.contains(&(4 + i, 4)) && dark.contains(&(4, 4 + i)));
        }
        let uri = qr_data_uri(EXAMPLE).unwrap();
        assert!(uri.starts_with("data:image/svg+xml;base64,"));
    }

    #[test]
    fn the_longest_valid_text_still_draws() {
        // A 253-character host is the longest the rule allows. The design
        // (section 10) hoped for "version 10 or less" even then, but at
        // level M a version-10 code holds only 213 bytes and this text is
        // 324 - so the check here is that it draws, at a size a phone
        // camera still reads. An ordinary Tailscale name stays at 7 or
        // under (the test above).
        let label = "a".repeat(63);
        let host = format!("{label}.{label}.{label}.{}.ts.net", "b".repeat(54));
        assert_eq!(host.len(), 253);
        let text = format!(
            "jarvis-pair:1/{host}/65535/00112233445566ff/AAECAwQFBgcICQoLDA0ODw/1790000600"
        );
        assert!(parse_pair_qr(&text).is_ok());
        let (_, version) = qr_svg(&text).unwrap();
        assert!(version <= 14, "version {version}");
    }

    #[test]
    fn the_typed_address_is_made_into_a_name_and_a_port() {
        assert_eq!(
            split_address(" Jarvis-PC.tail1234.ts.net ").unwrap(),
            ("jarvis-pc.tail1234.ts.net".to_string(), None)
        );
        assert_eq!(
            split_address("http://jarvis-pc.tail1234.ts.net:4719/").unwrap(),
            ("jarvis-pc.tail1234.ts.net".to_string(), Some(4719))
        );
        assert_eq!(
            split_address("my-pc.nord.").unwrap(),
            ("my-pc.nord".to_string(), None)
        );
        for bad in [
            "",
            "   ",
            "my pc.ts.net",
            "me@pc.ts.net",
            "pc.ts.net:0",
            "pc.ts.net:x",
            "a/b",
        ] {
            assert!(split_address(bad).is_err(), "{bad:?}");
        }
        assert_eq!(address_text("pc.ts.net", Some(80)), "pc.ts.net:80");
    }

    #[test]
    fn the_tailscale_name_is_read_from_self() {
        let out = r#"{"Version":"1.80.0","Self":{"DNSName":"Jarvis-PC.tail1234.ts.net.","TailscaleIPs":["100.101.2.3"]}}"#;
        assert_eq!(
            tailscale_name(out).as_deref(),
            Some("jarvis-pc.tail1234.ts.net")
        );
        assert_eq!(tailscale_name(r#"{"Self":{"DNSName":""}}"#), None);
        assert_eq!(
            tailscale_name(r#"{"Self":{"DNSName":"pc.example.com."}}"#),
            None
        );
        assert_eq!(tailscale_name(r#"{"BackendState":"Stopped"}"#), None);
        assert_eq!(tailscale_name("not json"), None);
    }

    #[test]
    fn a_refused_key_is_explained() {
        let removed = r#"{"error": "bad or missing X-Jarvis-Token", "key": "device_removed"}"#;
        let retired = r#"{"error": "bad or missing X-Jarvis-Token", "key": "shared_retired"}"#;
        assert_eq!(refused_key_words(removed), Some(KEY_REMOVED));
        assert_eq!(refused_key_words(retired), Some(SHARED_RETIRED));
        assert_eq!(
            refused_key_words(r#"{"error": "bad or missing X-Jarvis-Token"}"#),
            None
        );
        assert_eq!(refused_key_words(r#"{"key": "something_new"}"#), None);
        assert_eq!(refused_key_words(""), None);
    }

    #[test]
    fn the_device_list_never_passes_a_key_on() {
        let body = r#"{"you": "pc", "devices": [
            {"id": "pc", "name": "This PC", "kind": "pc", "removable": false},
            {"id": "d3f9a1c2e", "name": "Pixel 9", "kind": "phone", "created": 1790000000,
             "last_seen": 1790003600, "removable": true, "approval_key": false,
             "token": "jdk1.oops", "token_sha256": "c26f"}],
            "shared": {"retired": false, "retired_at": null, "last_other_seen": null,
                       "last_other_address": null, "can_bring_back_here": true},
            "pairing": {"available": true, "why_not": null}}"#;
        let v = list_answer(200, body).unwrap();
        assert_eq!(v["available"], true);
        assert_eq!(v["devices"][1]["name"], "Pixel 9");
        assert!(v["devices"][1].get("token").is_none());
        assert!(v["devices"][1].get("token_sha256").is_none());
        let missing = list_answer(404, "").unwrap();
        assert_eq!(missing["available"], false);
        assert_eq!(missing["why"], PAIRING_MISSING);
        assert!(list_answer(200, "{}").is_err());
        assert!(list_answer(500, r#"{"error": "boom"}"#).is_err());
    }

    #[test]
    fn signed_approvals_are_read_from_the_version_only_when_true() {
        let yes = r#"{"capabilities": {"pairing": {"signed_approvals": true}}}"#;
        assert!(signed_approvals_in_version(200, yes));
        for body in [
            r#"{"capabilities": {"pairing": {"signed_approvals": false}}}"#,
            r#"{"capabilities": {"pairing": {"signed_approvals": "true"}}}"#,
            r#"{"capabilities": {"pairing": {}}}"#,
            r#"{"capabilities": {"pairing": true}}"#,
            r#"{"capabilities": {}}"#,
            "not json",
        ] {
            assert!(!signed_approvals_in_version(200, body), "{body}");
        }
        assert!(!signed_approvals_in_version(500, yes));
    }

    #[test]
    fn the_approval_key_state_reaches_the_page_untouched() {
        let body = r#"{"devices": [
            {"id": "a", "name": "A", "kind": "phone", "approval_key": true},
            {"id": "b", "name": "B", "kind": "phone", "approval_key": "waiting"},
            {"id": "c", "name": "C", "kind": "phone", "approval_key": false},
            {"id": "d", "name": "D", "kind": "phone"}]}"#;
        let v = list_answer(200, body).unwrap();
        assert_eq!(v["devices"][0]["approval_key"], true);
        assert_eq!(v["devices"][1]["approval_key"], "waiting");
        assert_eq!(v["devices"][2]["approval_key"], false);
        assert!(v["devices"][3].get("approval_key").is_none());
    }

    #[test]
    fn the_session_is_cut_down_to_the_designs_fields() {
        let body = r#"{"state": "waiting_for_card", "expires_in": 512, "tries_left": 3,
            "device_name": "Pixel 9", "words": ["tulip", "anchor", "mellow", "crane"],
            "wrong_tries_from": [], "message": "Your phone asked.",
            "code": "K7QM-4TXD", "qr": "jarvis-pair:1/x", "secret": "AAEC"}"#;
        let v = session_answer(200, body).unwrap();
        assert_eq!(v["words"][3], "crane");
        assert_eq!(v["message"], "Your phone asked.");
        for leak in ["code", "qr", "secret"] {
            assert!(v.get(leak).is_none(), "{leak}");
        }
        assert_eq!(
            session_answer(200, r#"{"state": "none"}"#).unwrap()["state"],
            "none"
        );
        assert_eq!(session_answer(404, "").unwrap()["state"], "none");
        assert!(session_answer(200, "[]").is_err());
        assert!(session_active("waiting_for_phone"));
        assert!(session_active("waiting_for_card"));
        assert!(session_active("approved"));
        for ended in [
            "none",
            "done",
            "denied",
            "timed_out",
            "expired",
            "burnt",
            "cancelled",
            "refused",
        ] {
            assert!(!session_active(ended), "{ended}");
        }
    }

    #[test]
    fn a_start_answer_is_only_used_when_it_has_the_designs_shape() {
        let good = format!(
            r#"{{"ok": true, "pair_id": "00112233445566ff", "qr": "{EXAMPLE}",
                 "code": "K7QM-4TXD", "expires_in": 600, "tries_left": 3}}"#
        );
        let s = start_answer(200, &good).unwrap();
        assert_eq!(s.code, "K7QM-4TXD");
        assert_eq!((s.expires_in, s.tries_left), (600, 3));
        assert_eq!(s.qr, EXAMPLE);
        let bad_qr = good.replace("jarvis-pair:1/", "jarvis-pair:1/example.com/");
        assert!(start_answer(200, &bad_qr).is_err());
        let bad_code = good.replace("K7QM-4TXD", "K7QM-4TXI");
        assert!(start_answer(200, &bad_code).is_err());
        assert_eq!(start_answer(404, "").unwrap_err(), PAIRING_MISSING);
        let pc_only =
            r#"{"ok": false, "pc_only": true, "error": "This can only be done on the PC itself."}"#;
        assert_eq!(
            start_answer(403, pc_only).unwrap_err(),
            "This can only be done on the PC itself."
        );
    }

    #[test]
    fn only_one_real_device_id_can_be_removed() {
        assert!(device_id_ok("d3f9a1c2e"));
        for bad in [
            "pc",
            "",
            "d3f9a1c2",
            "d3f9a1c2e0",
            "D3f9a1c2e",
            "d3F9a1c2e",
            "x3f9a1c2e",
            "d3f9a1c2g",
        ] {
            assert!(!device_id_ok(bad), "{bad}");
        }
    }

    #[test]
    fn only_a_label_the_pc_would_take_is_sent() {
        // docs/MULTI-DEVICE-DESIGN.md, the first slice: the same rule the PC
        // applies (jarvis_devices.label_ok), refused here first so a label
        // that could never be accepted does not make a round trip. The empty
        // label IS valid: it is how a label is cleared, and the device goes
        // back to the name it gave itself at pairing.
        assert!(label_ok(""));
        assert!(label_ok("Garden phone"));
        assert!(label_ok("Sam's (old) phone"));
        assert!(label_ok("Zoë's tablet"));
        assert!(label_ok(&"A".repeat(40)));
        for bad in [
            &"A".repeat(41),
            "Phone\nsecond line",
            "Phone | Fake card",
            "<b>Phone</b>",
            "Phone\u{202e}gnihs",
            "Phone\ttab",
        ] {
            assert!(!label_ok(bad), "{bad:?}");
        }
    }

    #[test]
    fn a_change_says_what_happened_in_words() {
        let ok =
            change_answer(200, r#"{"ok": true, "id": "d3f9a1c2e", "name": "Pixel 9"}"#).unwrap();
        assert_eq!(ok["http"], 200);
        assert_eq!(
            change_answer(202, r#"{"waiting": true}"#).unwrap()["waiting"],
            true
        );
        assert_eq!(
            change_answer(404, r#"{"reason": "no_such_device"}"#).unwrap_err(),
            NO_SUCH_DEVICE
        );
        assert_eq!(change_answer(404, "").unwrap_err(), PAIRING_MISSING);
        assert_eq!(
            change_answer(409, r#"{"reason": "uses_it_yourself"}"#).unwrap_err(),
            USES_IT_YOURSELF
        );
        assert_eq!(
            change_answer(
                409,
                r#"{"reason": "uses_it_yourself", "error": "Pair it first."}"#
            )
            .unwrap_err(),
            "Pair it first."
        );
    }
}
