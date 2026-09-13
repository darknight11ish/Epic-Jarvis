# Jarvis Mobile

Native Android companion for a self-hosted Jarvis desktop server reached over
Tailscale. Kotlin 2.0 / Compose / Material3, `compileSdk` 35, `minSdk` 28.

Build: `./gradlew assembleDebug` → `app/build/outputs/apk/debug/app-debug.apk`.
CI builds it on every push; download it from the run's Artifacts.

## Server endpoint

The app dials `ws://<host>:<port>/api/mobile/ws`. The address field accepts a
bare host, `host:port`, or a full `ws|wss|http|https` URL; a URL with no path
gets `/api/mobile/ws` appended.

OkHttp sends a ping every 45s and expects pongs. Reconnection backs off
1s → 2s → 4s … capped at 30s.

## Wire protocol

Text frames are JSON objects discriminated by `type`. Unknown types are logged
and dropped rather than killing the connection, so the desktop can add events
without breaking older builds.

### Desktop → phone

| `type` | Fields | Effect |
| --- | --- | --- |
| `approval_request` | `id`, `title`, `summary`, `tier`, `detail?`, `expires_at_ms?` | Heads-up notification with Approve/Reject |
| `approval_resolved` | `id`, `approved` | Cancels the notification (resolved elsewhere) |
| `audio_stream_start` | `stream_id`, `sample_rate`, `channels`, `encoding` | Opens AudioTrack. `encoding` is `pcm16` or `wav` |
| `audio_chunk` | `stream_id`, `data` (base64), `seq` | Queued for playback |
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
| `approval_decision` | `id`, `approved`, `device_id`, `decided_at_ms`, `signature` |
| `audio_input_start` | `stream_id`, `sample_rate` (16000), `channels`, `encoding` |
| `audio_input_end` | `stream_id` |
| `interrupt` | `reason` |
| `telemetry_snapshot` | `request_id`, `snapshot` |
| `device_command_result` | `id`, `ok`, `detail?` |

**Microphone audio is binary, not JSON.** After `audio_input_start`, raw
little-endian 16 kHz / 16-bit mono PCM arrives as binary WebSocket frames until
`audio_input_end`. Downlink audio uses base64 `audio_chunk` frames instead, so
the desktop can interleave it with control messages on one stream.

## Approval signing

`signature` is HMAC-SHA256, lowercase hex, over:

```
{id}|{approved}|{device_id}|{decided_at_ms}
```

where `approved` is the literal `true` or `false`. The key is the shared secret
stored on the phone. **The HUD has no field for it yet** — set it via
`JarvisSettings.sharedSecret` or seed the `shared_secret` key in the
`jarvis_settings` SharedPreferences file. With no secret the signature is an
empty string and the desktop should fall back to Tailnet-level trust.

Reject a decision whose `decided_at_ms` is far from the server clock, so a
captured payload cannot be replayed later.

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
- `usesCleartextTraffic` is enabled for plain `ws://` over the Tailnet. Use
  `wss://` if the link ever leaves it.
