# Jarvis Mobile (legacy)

> **Legacy - kept for reference only. This app cannot talk to Jarvis.**
>
> It speaks an old connection method (a WebSocket at `/api/mobile/ws`) that
> the Jarvis backend never had, so it cannot connect to it at all. **The phone
> app to install is `jarvis-client`**, from the
> [`client-latest` release](https://github.com/darknight11ish/Epic-Jarvis/releases/tag/client-latest).
> This folder stays so its parts can be borrowed; its useful ones (the
> approval widget and a quick-link widget) are already in `jarvis-client`.
> It publishes no release; CI only builds it, so it does not rot.

Native Android companion for a self-hosted Jarvis desktop server reached over
Tailscale. Kotlin 2.0 / Compose / Material3, `compileSdk` 35, `minSdk` 28.

Build: `./gradlew assembleDebug` → `app/build/outputs/apk/debug/app-debug.apk`.
CI builds it on every push; download it from the run's Artifacts.

## Server endpoint

The app dials `ws://<host>:<port>/api/mobile/ws`. The address field accepts a
bare host, `host:port`, or a full `ws|wss|http|https` URL; a URL with no path
gets `/api/mobile/ws` appended.

OkHttp pings every 25s and expects pongs. Reconnection backs off 1s → 2s → 4s …
capped at 30s.

The ping interval sits under 30s deliberately: carrier CGNAT gateways commonly
reap idle mappings at that mark, and a longer interval leaves the phone believing
it is connected on a socket that is already dead.

If an auth token is configured the upgrade request carries
`Authorization: Bearer <token>`. Reject there — before the upgrade completes —
rather than after the client is registered.

The app refuses to dial plaintext `ws://` unless the host is inside
100.64.0.0/10, RFC1918, loopback, `.ts.net` or `.local`. Android's network
security config cannot express this (its rules take hostnames and IP literals,
not CIDR ranges), so the check lives in `JarvisSettings.isCleartextTargetPrivate`.

## Wire protocol

Text frames are JSON objects discriminated by `type`. Unknown types are logged
and dropped rather than killing the connection, so the desktop can add events
without breaking older builds.

### Desktop → phone

| `type` | Fields | Effect |
| --- | --- | --- |
| `approval_request` | `id`, `title`, `summary`, `tier`, `detail?`, `expires_at_ms?` | Heads-up notification with Approve/Reject |
| `approval_resolved` | `id`, `approved` | Cancels the notification (resolved elsewhere) |
| `audio_stream_start` | `stream_id`, `sample_rate`, `channels`, `encoding`, `binary_tag?` | Opens AudioTrack. `encoding` is `pcm16` or `wav` |
| `audio_chunk` | `stream_id`, `data` (base64), `seq` | Fallback path — prefer binary frames |
| `audio_stream_end` | `stream_id` | Drains and closes playback |
| `device_command` | `id`, `action`, `params` | See actions below |
| `telemetry_request` | `id` | Phone replies with `telemetry_snapshot` |
| `desktop_telemetry` | `cpu_percent?`, `gpu_temp_c?`, `gpu_percent?`, `vram_used_mb?`, `vram_total_mb?`, `ram_percent?` | Rendered on the HUD |
| `status` | `text` | Free-form status line on the HUD |

`device_command.action` accepts `torch_on`, `torch_off`, `torch_toggle`,
`set_volume` (`params.percent`, 0-100), `vibrate` (`params.pattern`: `tick`,
`confirm`, `alert`), `interrupt_audio`, and `telemetry`. Every command is
answered with `device_command_result`.

### Phone → desktop

| `type` | Fields |
| --- | --- |
| `hello` | `device_id`, `platform`, `app_version`, `protocol_version` |
| `approval_decision` | `id`, `approved`, `device_id`, `decided_at_ms`, `nonce`, `signature` |
| `audio_input_start` | `stream_id`, `sample_rate` (16000), `channels`, `encoding` |
| `audio_input_end` | `stream_id` |
| `interrupt` | `reason` |
| `telemetry_snapshot` | `request_id`, `snapshot` |
| `device_command_result` | `id`, `ok`, `detail?` |

### Audio framing

**Audio is binary in both directions.**

Uplink: after `audio_input_start`, raw little-endian 16 kHz / 16-bit mono PCM
arrives as binary WebSocket frames until `audio_input_end`.

Downlink: set `binary_tag` (0-255) on `audio_stream_start`, then send binary
frames shaped `[tag][pcm…]`. The tag lets the phone drop frames belonging to a
stream that has already ended. Base64 `audio_chunk` still works but costs a 33%
payload inflation plus a JSON parse per 20ms of speech, which shows up as GC
pressure during playback — use it only if binary frames are impractical.

Playback holds back 120ms before starting, as a jitter buffer. Cellular packet
arrival is bursty, and starting on the first byte means the track drains faster
than the network refills it.

## Approval signing

`signature` is HMAC-SHA256, lowercase hex, over:

```
{id}|{approved}|{device_id}|{decided_at_ms}|{nonce}
```

where `approved` is the literal `true` or `false`. The key is the signing secret,
entered in the HUD's Pairing section. It is write-only: a stored secret is never
read back into the UI.

**There is no unsigned path.** With no secret configured the app refuses to send
the decision at all and says so on the HUD, rather than emitting an empty
signature for the desktop to wave through. An empty-signature fallback would mean
a lost or misconfigured secret silently downgrades every approval to "trust
anything that can reach the port" — invisible exactly when it matters. The
desktop should mirror this and reject any decision without a valid HMAC.

Reject a decision whose `decided_at_ms` is far from the server clock, **and track
seen `nonce` values** — a timestamp window alone still lets an identical decision
be replayed until the window closes.

## Behaviour worth knowing

- Decisions taken while the socket is down are queued and replayed on reconnect.
- Starting the mic performs barge-in first: local playback is flushed and an
  `interrupt` is sent before the first uplink byte.
- Capture uses `VOICE_COMMUNICATION` so the platform applies echo cancellation;
  without it speaker output feeds back into the uplink during duplex playback.
- The foreground service runs as `specialUse` and promotes to `microphone` only
  while capturing — declaring `microphone` up front makes `startForeground`
  throw on Android 14+ before `RECORD_AUDIO` is granted.
- Wi-Fi SSID needs a location permission on API 29+ that this app does not
  request, so `wifi_ssid` is usually absent. Use `network_transport` instead.
- Cleartext is permitted at the manifest level for plain `ws://` over the
  Tailnet, but the app itself refuses public-host cleartext targets (see above).
  Use `wss://` if the link ever leaves the Tailnet.
