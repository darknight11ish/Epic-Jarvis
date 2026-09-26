//! The HUD page's requests to Jarvis, made here in Rust, so the page never
//! holds the pairing token (apps security audit M2).
//!
//! `jarvis_hud.html` is vendored from the backend and was written to call the
//! backend itself, with the token in `window.JARVIS`. So any script running in
//! that page - a bug in it, or text it was tricked into running - could read
//! the token and call anything the API allows, including `POST /api/approve`,
//! skipping Windows Hello, the stale-stream check and `decide_approval`
//! altogether. Now `hud_bootstrap.js` configures the page with NO token and
//! routes its requests here:
//!
//! * [`hud_get`]: a read, and only one of the reads the page is known to make
//!   ([`allowed_get`]). Nothing else, whatever path a script asks for.
//! * [`hud_chat`]: `POST /api/chat`, with only the fields the page sends
//!   ([`chat_payload`]), streamed back over a channel.
//! * The right/wrong mark goes through the quickbar's own `mark_answer`.
//!
//! Approve and Deny are not here at all: they are answered in the Jarvis bar
//! or the widget, through `decide_approval`, with Windows Hello and the stale
//! check. Memory writes are not here either: they are the Brain's.

use std::time::Duration;

use serde::Serialize;
use tauri::ipc::Channel;
use tauri::{AppHandle, Manager};

use crate::commands::{jarvis_base, jarvis_client, jarvis_headers};
use crate::ChatState;

/// Every read the HUD page makes, exactly. `/api/retrieve` is the one with a
/// query, and it is checked on its own in [`allowed_get`].
pub const HUD_GET_PATHS: [&str; 5] = [
    "/api/status",
    "/api/graph",
    "/api/pending",
    "/api/initiative",
    "/api/memory/pending",
];

/// The retrieval trace: `/api/retrieve?q=<the question>`, and nothing else.
const RETRIEVE_PATH: &str = "/api/retrieve";

/// A question longer than this is not one the page sends (it sends the
/// user's own message, which the chat box keeps short).
const MAX_QUERY_BYTES: usize = 16 * 1024;

/// How long one read may take, start to finish.
const GET_TIMEOUT: Duration = Duration::from_secs(20);

/// The largest reply passed to the page. `/api/graph` is the big one.
const MAX_GET_BODY_BYTES: usize = 16 * 1024 * 1024;

/// The path (and query) the HUD may read, or `None`.
///
/// Exact matches only: no other route, no `..`, no fragment, no second query
/// parameter, nothing that is not plain printable ASCII. A path that is not
/// on the list is refused here, not sent and left to the backend to refuse.
pub fn allowed_get(path: &str) -> Option<String> {
    if path.is_empty()
        || path.len() > RETRIEVE_PATH.len() + 3 + MAX_QUERY_BYTES
        || !path.bytes().all(|b| (0x21..0x7f).contains(&b))
        || path.contains('#')
        || path.contains("..")
    {
        return None;
    }
    let (route, query) = match path.split_once('?') {
        Some((route, query)) => (route, Some(query)),
        None => (path, None),
    };
    if HUD_GET_PATHS.contains(&route) {
        return query.is_none().then(|| route.to_string());
    }
    if route == RETRIEVE_PATH {
        let q = query?.strip_prefix("q=")?;
        // One parameter: its value is percent-encoded by the page
        // (encodeURIComponent), so a literal `&` or `=` means a second one.
        if q.is_empty() || q.contains('&') || q.contains('=') || q.contains('?') {
            return None;
        }
        return Some(format!("{RETRIEVE_PATH}?q={q}"));
    }
    None
}

/// The body of `POST /api/chat` the HUD may send: only the fields the page
/// itself sends, each only in its own shape. Anything else is left out, so
/// a script in the page cannot use this to send fields the page never does.
pub fn chat_payload(body: &serde_json::Value) -> Result<serde_json::Value, String> {
    let body = body
        .as_object()
        .ok_or_else(|| "the chat request was not a JSON object".to_string())?;
    let messages = body
        .get("messages")
        .and_then(|m| m.as_array())
        .filter(|m| !m.is_empty() && m.iter().all(|x| x.is_object()))
        .ok_or_else(|| "the chat request had no messages".to_string())?;
    let mut out = serde_json::Map::new();
    out.insert(
        "messages".into(),
        serde_json::Value::Array(messages.clone()),
    );
    if let Some(auto) = body.get("auto").and_then(|v| v.as_bool()) {
        out.insert("auto".into(), serde_json::json!(auto));
    }
    match body.get("lane") {
        Some(serde_json::Value::String(lane)) if lane.len() <= 200 => {
            out.insert("lane".into(), serde_json::json!(lane));
        }
        Some(serde_json::Value::Null) => {
            out.insert("lane".into(), serde_json::Value::Null);
        }
        _ => {}
    }
    if let Some(stream) = body.get("stream").and_then(|v| v.as_bool()) {
        out.insert("stream".into(), serde_json::json!(stream));
    }
    if let Some(t) = body.get("temperature").and_then(|v| v.as_f64()) {
        if (0.0..=2.0).contains(&t) {
            out.insert("temperature".into(), serde_json::json!(t));
        }
    }
    // The same two history fields, checked the same way, as the quickbar's
    // (commands::chat_extras) - and `device` can only say "hud" from here.
    let conversation = body.get("conversation_id").and_then(|v| v.as_str());
    out.extend(crate::commands::chat_extras(conversation, Some("hud")));
    Ok(serde_json::Value::Object(out))
}

/// One reply, as the page's `fetch` shim rebuilds it into a `Response`.
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HudReply {
    pub status: u16,
    pub content_type: String,
    /// `X-Jarvis-Route`, as the backend sent it (the page reads the lane,
    /// the gate and the reason from it, as it always has).
    pub route: Option<String>,
    pub body: String,
}

fn reach_error(base: &str, e: &reqwest::Error) -> String {
    if e.is_connect() {
        format!("could not reach the Jarvis server at {base}")
    } else if e.is_timeout() {
        "the Jarvis server did not answer in time".to_string()
    } else {
        format!("the request failed: {e}")
    }
}

fn header(response: &reqwest::Response, name: &str) -> Option<String> {
    response
        .headers()
        .get(name)
        .and_then(|v| v.to_str().ok())
        .map(str::to_string)
}

/// One of the HUD page's reads ([`allowed_get`]), with the token added here.
#[tauri::command]
pub async fn hud_get(app: AppHandle, path: String) -> Result<HudReply, String> {
    let path = allowed_get(&path)
        .ok_or_else(|| "the HUD window cannot read that - nothing was sent".to_string())?;
    let base = jarvis_base(&app);
    let mut response = jarvis_client(Some(GET_TIMEOUT))?
        .get(format!("{base}{path}"))
        .headers(jarvis_headers(&app)?)
        .send()
        .await
        .map_err(|e| reach_error(&base, &e))?;
    let status = response.status().as_u16();
    let content_type = header(&response, "Content-Type").unwrap_or_default();
    let route = header(&response, "X-Jarvis-Route");
    let mut bytes: Vec<u8> = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|e| reach_error(&base, &e))? {
        bytes.extend_from_slice(&chunk);
        if bytes.len() > MAX_GET_BODY_BYTES {
            return Err("the Jarvis server sent a reply too large for the HUD".to_string());
        }
    }
    Ok(HudReply {
        status,
        content_type,
        route,
        body: String::from_utf8_lossy(&bytes).into_owned(),
    })
}

/// The HUD's chat stream in flight: its own slot, so the HUD and the Jarvis
/// bar never cancel each other's answer.
#[derive(Default)]
pub struct HudChatState(pub ChatState);

/// One message on a [`hud_chat`] channel, as JSON: in order, one `head`,
/// then the body in `data` pieces, then `end` once the body has ended. The
/// `end` rides the channel itself, so the page knows it has every piece
/// (the command's own reply travels a different way and can arrive first).
#[derive(Debug, Serialize)]
#[serde(tag = "kind", rename_all = "lowercase")]
enum ChatFrame {
    #[serde(rename_all = "camelCase")]
    Head {
        status: u16,
        content_type: String,
        route: Option<String>,
    },
    Data {
        text: String,
    },
    End,
}

fn send_frame(on_event: &Channel<String>, frame: &ChatFrame) -> Result<(), String> {
    let json = serde_json::to_string(frame).map_err(|e| e.to_string())?;
    on_event
        .send(json)
        .map_err(|e| format!("unable to reach the HUD page: {e}"))
}

/// The HUD's `POST /api/chat`, with the token added here.
///
/// `on_event` receives [`ChatFrame`]s: the status and headers, then the body
/// as it arrives, whole lines with each line's `\n` kept, so the page reads
/// exactly what it would have read from the server, then `end`. Resolves when
/// the body ends; rejects when the server could not be reached (the page's
/// `fetch` rejects then too) or the stream broke.
#[tauri::command]
pub async fn hud_chat(
    app: AppHandle,
    body: serde_json::Value,
    on_event: Channel<String>,
) -> Result<(), String> {
    let payload = chat_payload(&body)?;
    let cancel = app.state::<HudChatState>().0.begin();
    let base = jarvis_base(&app);
    let headers = jarvis_headers(&app)?;
    let outcome = tokio::select! {
        result = pump(base, headers, payload, &on_event) => result,
        _ = cancel.notified() => Ok(()),
    };
    app.state::<HudChatState>().0.finish(&cancel);
    outcome
}

/// Stops the HUD's chat stream in flight, if there is one (the page's Stop,
/// a new message, or its two-minute silence watchdog).
#[tauri::command]
pub fn hud_chat_cancel(app: AppHandle) {
    app.state::<HudChatState>().0.cancel();
}

async fn pump(
    base: String,
    headers: reqwest::header::HeaderMap,
    payload: serde_json::Value,
    on_event: &Channel<String>,
) -> Result<(), String> {
    let mut response = jarvis_client(None)?
        .post(format!("{base}/api/chat"))
        .headers(headers)
        .json(&payload)
        .send()
        .await
        .map_err(|e| reach_error(&base, &e))?;
    send_frame(
        on_event,
        &ChatFrame::Head {
            status: response.status().as_u16(),
            content_type: header(&response, "Content-Type").unwrap_or_default(),
            route: header(&response, "X-Jarvis-Route"),
        },
    )?;

    // Whole lines, cut from raw bytes so a character split across two
    // network chunks is never decoded half-way.
    let mut buffer: Vec<u8> = Vec::with_capacity(8 * 1024);
    while let Some(bytes) = response
        .chunk()
        .await
        .map_err(|e| format!("the stream broke: {e}"))?
    {
        buffer.extend_from_slice(&bytes);
        if let Some(last) = buffer.iter().rposition(|b| *b == b'\n') {
            let lines: Vec<u8> = buffer.drain(..=last).collect();
            send_frame(
                on_event,
                &ChatFrame::Data {
                    text: String::from_utf8_lossy(&lines).into_owned(),
                },
            )?;
        }
        // Bounded, as the Jarvis bar's stream is: a body with no line break
        // would otherwise grow this until the app runs out of memory.
        if buffer.len() > crate::commands::MAX_CHAT_LINE_BYTES {
            return Err("the chat stream sent a line too long to be real".to_string());
        }
    }
    if !buffer.is_empty() {
        send_frame(
            on_event,
            &ChatFrame::Data {
                text: String::from_utf8_lossy(&buffer).into_owned(),
            },
        )?;
    }
    send_frame(on_event, &ChatFrame::End)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_page_reads_are_allowed_exactly() {
        for path in HUD_GET_PATHS {
            assert_eq!(allowed_get(path).as_deref(), Some(path));
        }
        assert_eq!(
            allowed_get("/api/retrieve?q=what%20is%20on%20today").as_deref(),
            Some("/api/retrieve?q=what%20is%20on%20today")
        );
    }

    #[test]
    fn nothing_else_is_allowed() {
        for path in [
            "",
            "/api/approve",
            "/api/deny",
            "/api/memory/facts",
            "/api/memory/export",
            "/api/status?x=1",
            "/api/status/",
            "/api/status#a",
            "/api/../api/approve",
            "/api/graph/../memory/export",
            "api/status",
            "http://127.0.0.1:4719/api/status",
            "/api/retrieve",
            "/api/retrieve?q=",
            "/api/retrieve?q=a&limit=999",
            "/api/retrieve?x=a",
            "/api/retrieve?q=a=b",
            "/api/retrieve?q=has space",
            "/api/pending\n",
        ] {
            assert_eq!(allowed_get(path), None, "{path:?} was allowed");
        }
        let long = format!("/api/retrieve?q={}", "a".repeat(MAX_QUERY_BYTES + 1));
        assert_eq!(allowed_get(&long), None);
    }

    #[test]
    fn the_chat_body_keeps_only_the_pages_fields() {
        let body = serde_json::json!({
            "auto": true,
            "lane": null,
            "messages": [{"role": "user", "content": "hi", "provenance": "typed"}],
            "conversation_id": "abcdefgh12",
            "device": "desktop",
            "stream": true,
            "temperature": 0.7,
            "model": "someone-elses",
            "tools": [{"name": "send_email"}],
            "by": "hud",
        });
        let out = chat_payload(&body).unwrap();
        let keys: Vec<&String> = out.as_object().unwrap().keys().collect();
        for k in &keys {
            assert!(
                [
                    "messages",
                    "auto",
                    "lane",
                    "stream",
                    "temperature",
                    "conversation_id",
                    "device"
                ]
                .contains(&k.as_str()),
                "{k} was passed on"
            );
        }
        assert_eq!(out["device"], "hud", "the HUD can only say it is the HUD");
        assert_eq!(out["conversation_id"], "abcdefgh12");
        assert_eq!(out["messages"][0]["provenance"], "typed");
    }

    #[test]
    fn the_channel_frames_are_the_shape_hud_bootstrap_reads() {
        let head = serde_json::to_value(ChatFrame::Head {
            status: 200,
            content_type: "text/event-stream".into(),
            route: Some("{}".into()),
        })
        .unwrap();
        assert_eq!(
            head,
            serde_json::json!({"kind": "head", "status": 200,
                "contentType": "text/event-stream", "route": "{}"})
        );
        let data = serde_json::to_value(ChatFrame::Data {
            text: "data: x\n".into(),
        })
        .unwrap();
        assert_eq!(
            data,
            serde_json::json!({"kind": "data", "text": "data: x\n"})
        );
        assert_eq!(
            serde_json::to_value(ChatFrame::End).unwrap(),
            serde_json::json!({"kind": "end"})
        );
    }

    #[test]
    fn a_chat_body_without_messages_is_refused() {
        assert!(chat_payload(&serde_json::json!({"messages": []})).is_err());
        assert!(chat_payload(&serde_json::json!({"messages": ["hi"]})).is_err());
        assert!(chat_payload(&serde_json::json!("hi")).is_err());
    }
}
