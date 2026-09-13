# Jarvis Desktop

A native **Windows 11** client for the Jarvis stack: a Rust (Tauri v2) backend
driving a WebView2 frontend.

* **Quickbar** — a 750×80 frameless, transparent, always-on-top spotlight bar
  summoned with `Alt+Space`. Streams answers from the local Jarvis server into
  an expandable card that the native window grows to fit.
* **HUD** — a 1280×820 frameless window pointed at `http://127.0.0.1:4719`.
* **Widget** — a 320px glass pane that lives on the desktop: a 44px mini-pill
  that expands to a telemetry panel, pending approval gates and a one-shot
  capture field.
* **Tray** — Toggle Spotlight · Toggle HUD Window · Status Check · Quit.
* **Vibrancy** — Windows 11 Acrylic behind the quickbar, Mica behind the HUD
  (Acrylic fallback on Windows 10).

## Global hotkeys

| Shortcut | Action |
|----------|--------|
| `Alt` + `Space` | Toggle the quickbar. On show it is centred, focused, and the frontend receives `focus-input`. |
| `Win` + `Shift` + `J` | Read the clipboard and inject it into the quickbar as context. |
| `Alt` + `Shift` + `S` | Capture the primary display and attach it to the next prompt. |
| `Alt` + `Shift` + `N` | Summon the bar pre-armed for a Logseq journal note (`#log `). |
| `Alt` + `Shift` + `W` | Show or hide the desktop widget. |

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
│   ├── main.js               # streaming, markdown, events, window sizing
│   ├── widget.html           # desktop widget markup
│   ├── widget.css            # widget glass styling
│   └── widget.js             # widget state machine and event wiring
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
| `stream_chat` | Open a chat stream against the Jarvis server and push each response line down a Tauri channel. Returns the stream's generation number. |
| `cancel_chat` | Abort the stream in flight; drops the socket, so the workstation stops generating. |
| `decide_approval` | Answer a pending approval — `POST /api/approve` or `/api/deny` with `{id, by: "desktop_spotlight"}`. |
| `capture_screen` | Grab the primary display, return a base64 JPEG data URI. |
| `check_server_health` | Probe Jarvis (`:4719/api/status`), Ollama (`:11434/api/tags`) and LiteLLM (`:4000/health`) concurrently; returns a structured report. |
| `hide_quickbar` / `show_quickbar` | Dismiss or summon the spotlight. |
| `toggle_hud` | Show/hide the HUD window. |
| `resize_quickbar` | Grow the native window to fit the answer card. |
| `set_quickbar_pinned` / `is_quickbar_pinned` | Keep the bar open through focus loss. |
| `write_clipboard` / `read_clipboard` | Clipboard access. |
| `notify_user` | Raise a Windows toast. |
| `open_external_url` | Validate an http(s) URL and hand it to the OS shell. |
| `resize_desktop_widget` | Expand/collapse the widget, or match a measured content height. |
| `set_widget_always_on_top` | Float the widget, or let active windows cover it. |
| `toggle_widget` | Show or hide the widget. |
| `save_widget_position` / `get_widget_prefs` | Persist and read the widget's geometry and mode. |
| `prefill_quickbar` | Summon the spotlight with a note prefix armed. |
| `capture_note` | File a note without opening the spotlight (`stream: false`). |
| `announce_approval` / `set_route_lane` | Relay state between windows through the backend. |
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

External links in the answer card are opened by `open_external_url`, which
validates the URL and then spawns `rundll32 url.dll,FileProtocolHandler`. It
deliberately does **not** shell out through `cmd /C start`: `cmd.exe` re-parses
its command line, Rust's argument escaping targets the C runtime convention
rather than cmd's metacharacters, and link text here is written by a language
model — a URL containing `&` would become a second command.

## Dual-note quick capture

A prefix at the head of the prompt pre-routes the turn and shows a chip beside
the reactor:

| Prefix | Target | Chip |
|--------|--------|------|
| `#log`, `#logseq`, `#journal` | Logseq daily journal (`append_logseq_journal`) | cyan **Logseq Journal** |
| `#joplin`, `#vault` | Joplin personal vault (`create_joplin_note` / `search_joplin`) | violet **Joplin Vault** |

`Alt+Shift+N` summons the bar with `#log ` already typed and the caret after
it; anything already in the box is kept.

The prefix is stripped before sending. Routing is declared twice, so a server
reading either mechanism lands in the same place: a top-level `note_target`
field, and a system turn naming the tool. `note_target` is additive — a server
that does not know the field ignores it.

## Approval gates

When the server answers `409` or streams a chunk marked `"tier": "ask"`, the
spotlight renders an approval card instead of prose: the action name, a preview
of the change, and Approve / Deny. Nothing runs until the human decides.

* The gate pins the window, so clicking away to read the diff does not dismiss
  it.
* `Enter` approves and `Esc` denies — both keys are taken over for as long as
  the gate is open, so neither can be hit by muscle memory meaning something
  else.
* A `diff` preview is colour-coded by rebuilding the escaped text into tagged
  spans, so the escape-first guarantee still holds — no raw HTML is ever
  inserted.
* The card is fed by whatever the server sends. It recognises the id under
  `id`, `request_id` or `approval_id`; the action under `action`, `tool` or
  `name`; and a preview from `diff`, `command`, `preview`, `content`, `body`,
  `text`, `summary`, or an `arguments` object rendered as JSON. Anything nested
  under `approval`, `pending_approval` or `approval_request` is unwrapped
  first.

## Chat protocol

Chat requests are made **from Rust**, not from the WebView. `stream_chat` posts
to `http://127.0.0.1:4719/api/chat` with `reqwest` and pushes each line of the
response down a `tauri::ipc::Channel`:

```jsonc
{
  "messages": [
    { "role": "system", "content": "Route this turn to the Logseq daily journal…" },
    { "role": "system", "content": "Context:\n…clipboard…" },
    { "role": "user",   "content": "…" }
  ],
  "has_image": true,
  "images": ["data:image/jpeg;base64,…"],
  "stream": true,
  "auto": true,
  "note_target": "logseq"   // only when a prefix pre-routed the turn
}
```

Headers: `X-Jarvis-Client: hud`, plus `X-Jarvis-Token` when `JARVIS_TOKEN` or
`HUD_TOKEN` is set in the app process's environment.

Going through Rust rather than `fetch` buys four things:

* **No CORS, no preflight.** A native client should not negotiate with a
  browser sandbox to reach its own loopback service. `fetch` from
  `http://tauri.localhost` needs an `OPTIONS` round trip on every request even
  though the server allows that origin.
* **The token stays out of the WebView.** It is read from the environment in
  `commands.rs` and never enters JavaScript memory, so a script injected into
  the HUD cannot read it.
* **Cancelling drops the socket.** `cancel_chat` aborts the Tokio task; no
  abandoned fetch keeps draining a response.
* **One stream at a time.** Starting a stream bumps a generation counter and
  aborts the previous task, so a superseded stream cannot deliver late chunks.

The channel carries raw response lines and the promise carries the terminal
state: `stream_chat` resolves when the body ends and rejects with the failure
text otherwise, so the frontend never infers "the stream ended" from silence.
A `409` is not a failure — the body is forwarded down the channel so the
approval card renders through the normal parsing path. Lines are assembled from
raw bytes in Rust, so a multi-byte character split across two network chunks is
never decoded half-way.

The frontend parses each line itself, accepting Server-Sent Events
(`data: {…}`, `[DONE]`), newline-delimited JSON and plain text, and reading
token deltas from any of `choices[0].delta.content`,
`choices[0].message.content`, `message.content`, `response`, `delta`, `token`,
`content` or `text`. A `route`, `tier`, `provider` or `model` field anywhere in
a chunk flips the badge between **Local / qwen3:8b** and
**Cloud / jarvis-escalate**.

Opening `index.html` in a plain browser (no Tauri) falls back to a streaming
`fetch`, purely so the UI can be iterated on outside the app. That path is
subject to CORS and sends no token.

## Desktop widget

A separate `widget` window, 320px wide, transparent and frameless, with Acrylic
behind it. It starts visible and is remembered between runs.

**Collapsed (44px).** Connection dot, GPU temperature, the active route pill,
`#log` / `#jop` quick-capture buttons, a pin toggle and the expand chevron. The
whole bar is a `data-tauri-drag-region`, so it drags from anywhere.

**Expanded.** Three meters (VRAM, CPU, GPU), any pending approval gate, and a
one-line capture field with a target switch. The window is sized from the
measured content rather than a fixed number, coalesced to one resize per 60ms
for the same DWM reason the spotlight throttles.

### Meter semantics

VRAM warns at 80% and turns red at 92% — running out is a real failure. CPU and
GPU *utilisation* are never coloured as warnings: a GPU at 95% during inference
is the machine working. The GPU bar's **length** is load, but its **colour** is
temperature (amber at 78°C, red at 87°C), which is the GPU number actually
worth reacting to.

### Telemetry

Sampled in Rust every 3 seconds and pushed to the widget alone, and only while
it is visible. CPU and RAM come from `sysinfo`; GPU temperature, utilisation and
VRAM come from `nvidia-smi --query-gpu=… --format=csv`, spawned with
`CREATE_NO_WINDOW` — without that flag a console flashes on every sample. The
first failed spawn disables the GPU probe permanently, so a machine without an
NVIDIA card pays nothing, and those meters render as `n/a` rather than zero.

### Pinning

The pin toggle switches between always-on-top and letting active windows cover
the widget. That second mode is not true desktop parenting: re-parenting to the
shell's `WorkerW` needs raw Win32 and breaks Acrylic on several builds, so the
widget still surfaces if you click it or Alt+Tab past it.

### Position persistence

Geometry, expanded state, pin mode and visibility live in `widget.json` beside
`config.json` in the app config dir — four scalars written from Rust, so a store
plugin would add a dependency and a capability grant to buy nothing. Dragging
emits a `Moved` event per mouse move, so position is held in memory and flushed
by the telemetry tick; a restored position that lands on a monitor that is no
longer attached is discarded rather than parking the widget off-screen.

### Approvals in two places

The spotlight finds gates in its own stream and relays them through
`announce_approval`, which the backend broadcasts to every window — the widget
has no stream to find them in. `decide_approval` broadcasts `approval-resolved`
after a successful decision, so answering in one window closes the card in the
other.
