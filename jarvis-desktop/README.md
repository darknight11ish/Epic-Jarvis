# Jarvis Desktop

A native **Windows 11** client for the Jarvis stack: a Rust (Tauri v2) backend
driving a WebView2 frontend.

* **Quickbar** — a 750×80 frameless, transparent, always-on-top spotlight bar
  summoned with `Alt+Space`. Streams answers from the local Jarvis server into
  an expandable card that the native window grows to fit.
* **HUD** — a 1280×820 frameless window pointed at `http://127.0.0.1:4719`.
* **Tray** — Toggle Spotlight · Toggle HUD Window · Status Check · Quit.
* **Vibrancy** — Windows 11 Acrylic behind the quickbar, Mica behind the HUD
  (Acrylic fallback on Windows 10).

## Global hotkeys

| Shortcut | Action |
|----------|--------|
| `Alt` + `Space` | Toggle the quickbar. On show it is centred, focused, and the frontend receives `focus-input`. |
| `Win` + `Shift` + `J` | Read the clipboard and inject it into the quickbar as context. |
| `Alt` + `Shift` + `S` | Capture the primary display and attach it to the next prompt. |

Capture is **not** bound to `Win+Shift+S`: the shell owns that for the Snipping
Tool, so `RegisterHotKey` returns ERROR_HOTKEY_ALREADY_REGISTERED (1409) and the
user gets the Snipping Tool instead. Any registration failure is logged and
non-fatal — the tray still drives everything.

## Layout

```text
jarvis-desktop/
├── package.json              # dev/build scripts (@tauri-apps/cli)
├── tauri.conf.json           # Tauri v2 config — source of truth
├── src/                      # WebView2 frontend (no bundler, no framework)
│   ├── index.html            # spotlight markup
│   ├── style.css             # AMOLED dark theme
│   └── main.js               # streaming, markdown, events, window sizing
└── src-tauri/
    ├── Cargo.toml
    ├── build.rs
    ├── capabilities/default.json
    ├── icons/                # generated reactor icon set
    └── src/
        ├── main.rs           # shim over the library
        ├── lib.rs            # plugins, hotkeys, tray + window setup
        ├── commands.rs       # capture, health checks, window/clipboard IPC
        ├── tray.rs           # notification-area icon and menu
        └── windows.rs        # vibrancy, spotlight placement, auto-hide
```

### A note on `tauri.conf.json`

The config lives at the **project root**. The Tauri CLI and
`tauri::generate_context!()` both read `src-tauri/tauri.conf.json`, so the npm
scripts copy it into place first:

```jsonc
"dev":   "npm run sync:config && tauri dev",
"build": "npm run sync:config && tauri build",
```

The copy is git-ignored — edit the root file only. If you invoke `cargo` or
`tauri` directly, run `npm run sync:config` once beforehand.

## Building

Prerequisites: Rust (MSVC toolchain), Node 18+, and the WebView2 runtime
(present on Windows 11; the installer bundles a bootstrapper otherwise).

```bash
npm install
npm run dev            # hot-reloading dev build
npm run build          # release build + MSI and NSIS installers
npm run bundle:msi     # MSI only
npm run lint           # cargo clippy -D warnings
```

The backend is verified to compile and pass clippy for
`x86_64-pc-windows-msvc`.

## IPC surface

Commands exposed to the frontend (`invoke("<name>", …)`):

| Command | Purpose |
|---------|---------|
| `capture_screen` | Grab the primary display, return a base64 JPEG data URI. |
| `check_server_health` | Probe Jarvis (`:4719/api/status`), Ollama (`:11434/api/tags`) and LiteLLM (`:4000/health`) concurrently; returns a structured report. |
| `hide_quickbar` / `show_quickbar` | Dismiss or summon the spotlight. |
| `toggle_hud` | Show/hide the HUD window. |
| `resize_quickbar` | Grow the native window to fit the answer card. |
| `set_quickbar_pinned` / `is_quickbar_pinned` | Keep the bar open through focus loss. |
| `write_clipboard` / `read_clipboard` | Clipboard access. |
| `notify_user` | Raise a Windows toast. |
| `quit_app` | Release the hotkeys and exit. |

Events emitted to the frontend: `focus-input`, `clipboard-inject`,
`screen-captured`, `capture-failed`, `health-report`, `pin-changed`.

## Security posture

`capabilities/default.json` grants only `core:default`, window drag and the
devtools toggle. Everything privileged — capture, health probes, clipboard,
notifications, window control — is an app-defined command in `commands.rs`,
and app commands are not permission-gated, so the clipboard, notification and
global-shortcut *plugin* permissions are simply not granted.

There is deliberately no `remote` block. The HUD loads
`http://127.0.0.1:4719` over plain HTTP; without a remote grant that origin
gets no IPC at all, so an XSS in the HUD web app cannot reach the clipboard,
the global shortcuts, or the window list. If the HUD ever needs IPC, add a
*separate* capability file scoped to that one window and that one command —
do not widen this one.

## Chat protocol

The quickbar posts to `POST http://127.0.0.1:4719/api/chat`:

```json
{
  "messages": [
    { "role": "system", "content": "Context:\n…clipboard…" },
    { "role": "user", "content": "…" }
  ],
  "has_image": true,
  "images": ["data:image/jpeg;base64,…"],
  "stream": true,
  "auto": true,
  "client": "jarvis-desktop"
}
```

Headers: `Content-Type: application/json`, `Accept: text/event-stream` and
`X-Jarvis-Client: hud`. The last one matters — a Tauri WebView's origin is
`http://tauri.localhost`, which will not be in the server's `ALLOWED_ORIGINS`,
and the client header is the documented fallback. Set `JARVIS_TOKEN` at the top
of `main.js` to also send `X-Jarvis-Token`.

**The server must still answer CORS.** `Content-Type: application/json` plus a
custom header makes this a preflighted request, so the WebView sends
`OPTIONS /api/chat` first and drops the response unless the server replies with
`Access-Control-Allow-Origin: http://tauri.localhost` (or `*`),
`Access-Control-Allow-Headers: content-type, x-jarvis-client, x-jarvis-token`
and `Access-Control-Allow-Methods: POST, OPTIONS`. A server-side origin check
passing is not sufficient; the browser enforces its own. If adding that to the
server is not an option, move the request into Rust (`reqwest` is already a
dependency) — same-process HTTP has no CORS.

The response reader accepts Server-Sent Events (`data: {…}`, terminated by
`[DONE]`), newline-delimited JSON, and plain text. Token deltas are read from
any of `choices[0].delta.content`, `choices[0].message.content`,
`message.content`, `response`, `delta`, `token`, `content` or `text`, so
Jarvis-native, Ollama and OpenAI-compatible shapes all render. A `route`,
`tier`, `provider` or `model` field anywhere in a chunk updates the badge
between **Local / qwen3:8b** and **Cloud / jarvis-escalate**.
