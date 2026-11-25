//! Settings -> Connection: "Show a QR code for my phone's browser".
//!
//! The owner's ask (2026-11-13): Atlas already serves its full web page on this
//! PC's own private-network address, and he wants to open it on his phone
//! without typing that address into the browser. The control is one button in
//! Settings -> Connection that shows a QR code; scanning it with a phone camera
//! opens Atlas's page at this PC's private address.
//!
//! **The picture carries the private address and nothing else.** No token, no
//! one-time key, no query string, and never a public tunnel (CLAUDE.md rule 2:
//! "no share my Jarvis"). That is not a simplification - it is the only honest
//! version: a browser cannot be handed a credential by a picture that the page
//! does not also show, and the address is already printed under the picture, so
//! a photo of the code reveals exactly what the owner is looking at and signs
//! nothing in.
//!
//! **The code opens the page; it does not sign the browser in.** When that
//! browser is not signed in, Atlas's own page says how to pair it: a browser's
//! pairing key (`jdk1...`) is minted on this PC at a terminal
//! (`jarvis_devices.py --add-device`) and exchanged for the `jarvis_token`
//! cookie by `POST /api/devices/web-session` (JARVIS-API section 90). There is
//! deliberately no route that mints one - a remote way to create credentials is
//! exactly what the `pair_device` card gates - so this feature adds no route,
//! sends nothing, and must not grow one to make the code "sign you in".
//!
//! The parts:
//!
//! * [`browser_url`] is the address the owner sees under the picture, and
//!   [`browser_link`] is the ONE place the text the picture carries is built.
//!   Today they are the same string, and a test pins that: the code can never
//!   carry more than the page shows.
//! * [`browser_bind`] refuses a blank, wildcard, loopback or home-network
//!   address, because a phone that scanned `127.0.0.1` would open itself.
//! * [`browser_port`] reads the port from this app's configured address, so the
//!   QR follows a port the owner changed.
//! * [`browser_answer`] draws it with [`crate::devices::qr_svg`], the same
//!   `qrcodegen` path phone pairing already uses.
//!
//! One command, callable from any window of this app (`settings-surface` and
//! the HUD's own `hud-browser-qr` in `permissions/surfaces.toml`), because the
//! HUD page will call it too. It takes no arguments on purpose: the bind address
//! is read HERE, from this app's own store, so a page cannot point the QR at an
//! address of its choosing.

use tauri::AppHandle;

use crate::commands::{configured_base, supervised_bind_address, validate_bind_address};
use crate::devices::qr_svg;

/// What the card shows when there is nothing for the phone to reach: the
/// "Let my phone reach this" address is blank, or it is not one a phone could
/// ever use.
///
/// One sentence for both, as the owner asked: it names the control to turn on
/// and the address to pick, and it invents no reason the owner cannot act on.
/// It carries no token, no key and no address.
pub(crate) const NO_PHONE_ADDRESS: &str =
    "Turn on Let my phone reach this first, and pick this PC's \
     own 100.x address. Until then there is nothing for the phone to reach.";

/// `JARVIS_HUD_PORT`'s default (`jarvis_hud.py`), and the desktop's own
/// [`crate::commands::DEFAULT_BASE`] port. Used when this app has no other
/// port configured.
pub(crate) const DEFAULT_PORT: u16 = 4719;

/// What the page gets: the finished picture, and the address it points at.
/// Never anything the picture carries that the page does not show.
#[derive(Debug, PartialEq, Eq)]
pub(crate) struct BrowserQr {
    pub svg: String,
    pub url: String,
}

/// The address the QR points at, as the owner is allowed to see it: scheme,
/// host, port and a bare `/`. No query, no fragment, no credentials.
pub(crate) fn browser_url(bind: &str, port: u16) -> String {
    format!("http://{bind}:{port}/")
}

/// The exact text the QR code carries - and the ONE place it is built.
///
/// It is the address and nothing else. This is the function a later edit would
/// reach for to add a sign-in part; it must not grow one (see the module
/// comment), and the test `the_picture_carries_the_address_and_nothing_else`
/// pins both the exact text and that [`browser_url`] is the same string.
pub(crate) fn browser_link(bind: &str, port: u16) -> String {
    browser_url(bind, port)
}

/// The saved "Let my phone reach this" address, or the card's plain refusal.
///
/// A blank value is the default and safe state, so it is refused here rather
/// than drawn as a QR nothing can reach. `validate_bind_address` already
/// refuses the wildcard and every address off the owner's own networks; this
/// adds the one thing only a PHONE's browser cares about: the address must be
/// a mesh address (`100.64.0.0/10`), because `127.0.0.1` is this PC itself and
/// a phone that scanned it would open its own loopback. The sentence the owner
/// sees says to pick the 100.x address, which is the fix in both cases.
pub(crate) fn browser_bind(raw: Option<&str>) -> Result<String, String> {
    let bind = raw.unwrap_or_default().trim();
    if bind.is_empty() {
        return Err(NO_PHONE_ADDRESS.to_string());
    }
    validate_bind_address(bind).map_err(|_| NO_PHONE_ADDRESS.to_string())?;
    let ip: std::net::Ipv4Addr = bind.parse().map_err(|_| NO_PHONE_ADDRESS.to_string())?;
    let [a, b, _, _] = ip.octets();
    if a != 100 || !(64..=127).contains(&b) {
        return Err(NO_PHONE_ADDRESS.to_string());
    }
    Ok(bind.to_string())
}

/// The port in the configured Jarvis address (`http://127.0.0.1:5005`), else
/// [`DEFAULT_PORT`].
///
/// The bind address is a bare host - the port is the backend's own
/// `JARVIS_HUD_PORT`, and the desktop's copy of it is the port in the address
/// it was configured with. A base this cannot read a port from (or one
/// `validate_base` refused, so nothing is sent to it) falls back to the
/// default rather than guessing.
pub(crate) fn browser_port(base: Option<&str>) -> u16 {
    base.and_then(|base| {
        let rest = base.trim().trim_end_matches('/');
        let authority = rest
            .strip_prefix("http://")
            .or_else(|| rest.strip_prefix("https://"))
            .unwrap_or(rest);
        let authority = authority.split('/').next().unwrap_or(authority);
        let (_, port) = authority.rsplit_once(':')?;
        port.parse::<u16>().ok().filter(|port| *port > 0)
    })
    .unwrap_or(DEFAULT_PORT)
}

/// The picture and the address, from the two values that decide them. Pure, so
/// a test can draw a QR without a window.
pub(crate) fn browser_answer(bind: &str, port: u16) -> Result<BrowserQr, String> {
    let (svg, _) = qr_svg(&browser_link(bind, port))
        .map_err(|_| "The QR code is too long to draw.".to_string())?;
    Ok(BrowserQr {
        svg,
        url: browser_url(bind, port),
    })
}

/// `{"svg", "url"}` for Settings' "Show a QR code for my phone's browser".
///
/// The page gets the picture and the address it points at, and nothing else:
/// nothing here reads the token, nothing is logged, and the refusal is thrown
/// rather than returned as an empty picture, so a blank or invalid address can
/// never look like a code that works.
#[tauri::command]
pub fn browser_qr(app: AppHandle) -> Result<serde_json::Value, String> {
    let bind = browser_bind(supervised_bind_address(&app).as_deref())?;
    let port = browser_port(configured_base(&app).as_deref());
    let answer = browser_answer(&bind, port)?;
    Ok(serde_json::json!({
        "svg": answer.svg,
        "url": answer.url,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The lead's own string: the link the finished feature encodes is the
    /// private address, with no sign-in part.
    #[test]
    fn the_picture_carries_the_address_and_nothing_else() {
        assert_eq!(browser_link("100.64.0.5", 4719), "http://100.64.0.5:4719/");
        let link = browser_link("100.64.0.5", 4719);
        // No query, no fragment, no key/value pair: a credential would need one
        // of these, and the page's own copy says the code carries none.
        assert!(!link.contains('?'), "{link}");
        assert!(!link.contains('#'), "{link}");
        assert!(!link.contains('='), "{link}");
        assert!(!link.contains("token"), "{link}");
        assert!(!link.contains("jdk1"), "{link}");
        // The code and the words under it are the same string, by construction.
        assert_eq!(link, browser_url("100.64.0.5", 4719));
    }

    /// What the page is shown: the address, and a picture that does not spell
    /// it out as text. The address is under the picture, so the code reveals
    /// nothing the owner cannot already read - and nothing else.
    #[test]
    fn the_page_gets_the_address_and_a_drawn_picture() {
        let answer = browser_answer("100.64.0.5", 4719).unwrap();
        assert_eq!(answer.url, "http://100.64.0.5:4719/");
        assert_eq!(answer.url, browser_link("100.64.0.5", 4719));
        assert!(answer.svg.starts_with("<svg"), "not an SVG");
        // The address lives in the modules, not in the SVG text.
        assert!(
            !answer.svg.contains(&answer.url),
            "the SVG spells the address"
        );
        assert!(!answer.svg.contains("token"));
    }

    /// A blank or wildcard address is the card's plain sentence, never a
    /// picture of an address nothing can reach.
    #[test]
    fn a_blank_or_wildcard_address_is_refused() {
        for raw in [None, Some(""), Some("   "), Some("0.0.0.0"), Some("::")] {
            assert_eq!(
                browser_bind(raw),
                Err(NO_PHONE_ADDRESS.to_string()),
                "{raw:?} was accepted"
            );
        }
        assert_eq!(
            browser_bind(Some(" 100.64.0.5 ")),
            Ok("100.64.0.5".to_string())
        );
    }

    /// Only a mesh address is useful in a phone's browser: loopback is the
    /// phone itself, and a home or public address is one the validator already
    /// refuses.
    #[test]
    fn an_address_a_phone_cannot_reach_is_refused_too() {
        for raw in [
            Some("127.0.0.1"),
            Some("localhost"),
            Some("192.168.1.20"),
            Some("8.8.8.8"),
            Some("100.63.0.1"),
            Some("100.128.0.1"),
        ] {
            assert_eq!(
                browser_bind(raw),
                Err(NO_PHONE_ADDRESS.to_string()),
                "{raw:?} was accepted"
            );
        }
        assert_eq!(
            browser_bind(Some("100.64.0.5")),
            Ok("100.64.0.5".to_string())
        );
        assert_eq!(
            browser_bind(Some("100.127.255.254")),
            Ok("100.127.255.254".to_string())
        );
    }

    /// The port is the one this app was configured with, and 4719 otherwise.
    #[test]
    fn the_port_comes_from_the_configured_address() {
        assert_eq!(browser_port(Some("http://127.0.0.1:5005")), 5005);
        assert_eq!(browser_port(Some("http://127.0.0.1:4719/")), 4719);
        assert_eq!(browser_port(Some("https://100.64.0.5:8443")), 8443);
        for none in [
            None,
            Some(""),
            Some("127.0.0.1"),
            Some("not an address"),
            Some("http://h:0"),
        ] {
            assert_eq!(
                browser_port(none),
                DEFAULT_PORT,
                "{none:?} did not fall back"
            );
        }
    }

    /// The picture is a function of the address: same address, same picture;
    /// a different address, a different picture. A QR of a constant would pass
    /// every other test here, and would open the wrong door.
    #[test]
    fn the_picture_follows_the_address() {
        let a = browser_answer("100.64.0.5", 4719).unwrap();
        let same = browser_answer("100.64.0.5", 4719).unwrap();
        let other_host = browser_answer("100.64.0.6", 4719).unwrap();
        let other_port = browser_answer("100.64.0.5", 5005).unwrap();
        assert_eq!(a.svg, same.svg);
        assert_ne!(
            a.svg, other_host.svg,
            "a different address drew the same code"
        );
        assert_ne!(a.svg, other_port.svg, "a different port drew the same code");
        assert_ne!(a.url, other_host.url);
    }

    /// The rule the feature exists for: nothing this command returns, and no
    /// refusal it can show, ever names the token or a browser key. A later
    /// edit that puts one in the URL or an error string fails here.
    #[test]
    fn nothing_the_command_or_its_refusals_name_a_credential() {
        const TOKEN: &str = "pairing-token-0123456789abcdef";
        const KEY: &str = "jdk1.d0123abcd.0123456789012345678901234567890123456789abc";
        let answer = browser_answer("100.64.0.5", 4719).unwrap();
        assert!(!answer.url.contains(TOKEN));
        assert!(!answer.url.contains(KEY));
        assert!(!answer.svg.contains(TOKEN));
        assert!(!answer.svg.contains(KEY));
        for raw in [None, Some(""), Some("0.0.0.0"), Some("127.0.0.1")] {
            let refused = browser_bind(raw).unwrap_err();
            assert!(
                !refused.contains(TOKEN),
                "a refusal names the token: {refused}"
            );
        }
        assert!(!NO_PHONE_ADDRESS.contains(TOKEN));
        assert!(!NO_PHONE_ADDRESS.contains(KEY));
    }
}
