# Jarvis Android — full source bundle

Commit `48967179f24900dcea5e3eec1dd12d3d688c547d` on `claude/android-apk-build-q435fi`, generated 2026-09-14.

This is the state **after** the audit fixes, and it is the state CI built:
both modules compile, both test suites run, both debug APKs assemble.

Every source file in the repository, in one document. Build outputs, the two
Gradle wrapper JARs and the documents under `docs/` are excluded.

## Contents
- `README.md`
- `jarvis-android/README.md`
- `server/README.md`
- `github/workflows/android-apk.yml`
- `github/workflows/jarvis-client.yml`
- `github/workflows/verify-toolchain.yml`
- `jarvis-android/app/build.gradle.kts`
- `jarvis-android/build.gradle.kts`
- `jarvis-android/settings.gradle.kts`
- `jarvis-client/app/build.gradle.kts`
- `jarvis-client/build.gradle.kts`
- `jarvis-client/settings.gradle.kts`
- `jarvis-android/gradle.properties`
- `jarvis-android/gradle/wrapper/gradle-wrapper.properties`
- `jarvis-client/gradle.properties`
- `jarvis-client/gradle/wrapper/gradle-wrapper.properties`
- `jarvis-android/app/src/main/AndroidManifest.xml`
- `jarvis-android/app/src/main/res/drawable/ic_launcher_foreground.xml`
- `jarvis-android/app/src/main/res/drawable/ic_notification.xml`
- `jarvis-android/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml`
- `jarvis-android/app/src/main/res/mipmap-anydpi-v26/ic_launcher_round.xml`
- `jarvis-android/app/src/main/res/values/colors.xml`
- `jarvis-android/app/src/main/res/values/strings.xml`
- `jarvis-android/app/src/main/res/values/themes.xml`
- `jarvis-android/app/src/main/res/xml/recognition_service.xml`
- `jarvis-android/app/src/main/res/xml/voice_interaction_service.xml`
- `jarvis-android/app/src/main/res/xml/widget_approval_info.xml`
- `jarvis-android/app/src/main/res/xml/widget_launcher_info.xml`
- `jarvis-android/app/src/main/res/xml/widget_telemetry_info.xml`
- `jarvis-client/app/src/main/AndroidManifest.xml`
- `jarvis-client/app/src/main/res/drawable/ic_launcher_foreground.xml`
- `jarvis-client/app/src/main/res/drawable/ic_notification.xml`
- `jarvis-client/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml`
- `jarvis-client/app/src/main/res/mipmap-anydpi-v26/ic_launcher_round.xml`
- `jarvis-client/app/src/main/res/values/colors.xml`
- `jarvis-client/app/src/main/res/values/strings.xml`
- `jarvis-client/app/src/main/res/values/themes.xml`
- `jarvis-client/app/src/main/res/xml/network_security_config.xml`
- `jarvis-android/app/proguard-rules.pro`
- `jarvis-client/app/proguard-rules.pro`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/JarvisApplication.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/MainActivity.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/audio/AudioPlayer.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/audio/AudioStreamer.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/data/JarvisSettings.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/data/PendingDecisionStore.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/data/PendingNoteStore.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/data/repository/WidgetDataRepository.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/network/JarvisWebSocketManager.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/network/WebSocketEvents.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/notifications/ApprovalNotificationManager.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/service/BootReceiver.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/service/JarvisForegroundService.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/service/JarvisInteractionSession.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/service/JarvisRecognitionService.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/service/JarvisVoiceService.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/service/QuickCaptureTileService.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/telemetry/DeviceTelemetryProvider.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/ui/approval/ApprovalDialog.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/ui/approval/Markdown.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/ui/approval/MarkdownText.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/ui/approval/NoteDiff.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/ui/capture/QuickCaptureSheet.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/ui/screens/HudScreen.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/ui/theme/Theme.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/widget/WidgetUi.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/widget/approval/ApprovalActionCallback.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/widget/approval/ApprovalWidget.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/widget/approval/ApprovalWidgetReceiver.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/widget/launcher/QuickLauncherReceiver.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/widget/launcher/QuickLauncherWidget.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/widget/telemetry/TelemetryReceiver.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/widget/telemetry/TelemetryWidget.kt`
- `jarvis-android/app/src/main/java/com/jarvis/assistant/widget/theme/JarvisGlanceTheme.kt`
- `jarvis-android/app/src/test/java/com/jarvis/assistant/ApprovalSignerTest.kt`
- `jarvis-android/app/src/test/java/com/jarvis/assistant/CleartextTargetTest.kt`
- `jarvis-android/app/src/test/java/com/jarvis/assistant/NoteDiffTest.kt`
- `jarvis-android/app/src/test/java/com/jarvis/assistant/QuickNoteSerializationTest.kt`
- `jarvis-android/app/src/test/java/com/jarvis/assistant/TelemetryProtocolTest.kt`
- `jarvis-client/app/src/main/java/com/jarvis/client/JarvisApp.kt`
- `jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt`
- `jarvis-client/app/src/main/java/com/jarvis/client/platform/PlatformReadiness.kt`
- `jarvis-client/app/src/main/java/com/jarvis/client/service/BootReceiver.kt`
- `jarvis-client/app/src/main/java/com/jarvis/client/service/EventService.kt`
- `jarvis-client/app/src/test/java/com/jarvis/client/PlatformReadinessTest.kt`
- `server/jarvis_mobile_ws.py`
- `server/test_jarvis_mobile_ws.py`

---

## `README.md`

```markdown
# Epic-Jarvis
Epic Javis based on openjarvis  and greatly enhanced . 

## Building the Android APK

APKs are built in CI, since the Android SDK is not vendored in this repo.

Two apps live here, and each has its own workflow and its own Gradle root:

| App | Workflow | Artifact |
| --- | --- | --- |
| `jarvis-android/` — the full companion (approvals, duplex audio, widgets, assistant role) | **Build Android APK** | `jarvis-android-debug-apk` |
| `jarvis-client/` — the rewrite against `ANDROID-BUILD.md`, currently step 0 | **Jarvis client** | `jarvis-client-debug-apk` |

Go to **Actions**, pick the workflow, and run it — or just push; each is scoped
to its own directory. Download the APK from the run's **Artifacts** section and
install it with `adb install -r <file>.apk`.

Unit tests gate both builds, and the workflows assert that the test task
actually matched sources: Gradle reports `NO-SOURCE` and exits 0 for a module
with no tests, so a green check is otherwise compatible with nothing having run.

**Debug builds only, and deliberately.** The app is sideloaded over adb and is
never listed on Play, so there is no channel a release build would serve. CI
used to decode a keystore and export four `SIGNING_*` variables into a build
that contained no `signingConfig` to read them — the result was an unsigned APK
that cannot be installed, uploaded under a name that called it signed. That
plumbing is gone rather than completed.
```

## `jarvis-android/README.md`

````markdown
# Jarvis Mobile

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
````

## `server/README.md`

````markdown
# Desktop endpoint for Jarvis Mobile

`jarvis_mobile_ws.py` is a stdlib-only WebSocket endpoint for the Android
client. Drop it next to your desktop server and import it — there is nothing to
install.

## Why it hand-rolls the framing

`BaseHTTPRequestHandler` cannot speak WebSocket. The alternatives were to move
the server to `aiohttp` or to open a second listener on another port, and both
change more than this needs to. Instead the module hijacks the connection after
writing the 101 response and implements RFC 6455 framing directly, so the
endpoint stays on port 4719 where the phone already dials it.

## Wiring it in

```python
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from jarvis_mobile_ws import ApprovalVerifier, MobileEndpoint

PENDING = {}          # request_id -> your gate object

ENDPOINT = MobileEndpoint(
    verifier=ApprovalVerifier(
        secret=os.environ["JARVIS_SHARED_SECRET"],
        allowed_device_ids=[os.environ["JARVIS_DEVICE_ID"]],   # optional but advised
    ),
    auth_token=os.environ.get("JARVIS_AUTH_TOKEN"),
    on_approval=lambda request_id, approved, client: PENDING.pop(request_id).resolve(approved),
    on_audio=lambda pcm, client: transcriber.feed(pcm),        # 16kHz 16-bit mono
    is_pending=lambda request_id: request_id in PENDING,
)

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path == MobileEndpoint.PATH:
            ENDPOINT.serve(self)      # blocks for the life of the socket
            return
        ...   # your existing routes

ThreadingHTTPServer(("0.0.0.0", 4719), Handler).serve_forever()
```

`ThreadingHTTPServer` is required: `serve()` blocks its thread until the phone
disconnects.

## Pushing to the phone

```python
ENDPOINT.broadcast(lambda c: c.send_approval_request(
    "req-1", "Delete 12 files", "rm -rf ~/scratch", tier="ask",
))
ENDPOINT.broadcast(lambda c: c.send_desktop_telemetry(
    cpu_percent=41.2, gpu_temp_c=68.0, vram_used_mb=9100, vram_total_mb=24576,
))
ENDPOINT.broadcast(lambda c: c.send_audio_stream("tts-1", pcm_chunks, sample_rate=22050))
```

`send_audio_stream` uses tagged binary frames rather than base64, avoiding a 33%
payload inflation and a JSON parse per 20ms of speech.

## Generating the pairing secret

```python
from jarvis_mobile_ws import generate_shared_secret
print(generate_shared_secret())
```

Paste the value into the phone's **Pairing → Signing secret** field and export
the same value as `JARVIS_SHARED_SECRET`. Without it the phone refuses to send
decisions and `ApprovalVerifier` refuses to construct — both ends fail closed.

## What the verifier enforces

Signature first, so unauthenticated input never reaches the replay cache:

1. Field types, including `approved` as a real JSON boolean — a `"true"` string
   is rejected rather than coerced.
2. `device_id` against the allowlist, when one is configured.
3. HMAC-SHA256 over `{id}|{approved}|{device_id}|{decided_at_ms}|{nonce}`,
   compared in constant time.
4. `decided_at_ms` within the skew window (60s default).
5. The request is still pending, via your `is_pending` callback.
6. The nonce is unseen, claimed atomically under a lock. The cache prunes on the
   same path that fills it, so it cannot grow without bound.

## Tests

```
python3 server/test_jarvis_mobile_ws.py
```

Covers the verifier and drives a real handshake, masked client frames,
ping/pong, 64-bit length frames, replay and forgery rejection, and the
server-to-phone senders over a raw socket.
````

## `jarvis-android/app/build.gradle.kts`

```kotlin
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

android {
    namespace = "com.jarvis.assistant"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.jarvis.assistant"
        minSdk = 28
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
            applicationIdSuffix = ""
        }
        release {
            // Shrinking is on, so proguard-rules.pro is actually exercised. It was
            // listed here while isMinifyEnabled was false, which meant the
            // kotlinx-serialization keeps and the OkHttp -dontwarns in it had never
            // once been applied — the release block advertised a shrink it did not
            // do, and the rules would have been validated for the first time on the
            // day someone turned it on.
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.10.01"))

    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")

    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.animation:animation")
    implementation("androidx.compose.material3:material3")
    // Declared, not inherited. LazyColumn, background and KeyboardOptions are used
    // directly throughout the UI and arrive only as an `api` transitive of
    // material3; that compiles today and stops compiling silently if material3
    // ever narrows what it exposes.
    implementation("androidx.compose.foundation:foundation")

    implementation("androidx.glance:glance:1.1.1")
    implementation("androidx.glance:glance-appwidget:1.1.1")
    implementation("androidx.glance:glance-material3:1.1.1")

    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    // Same reasoning: JarvisWebSocketManager imports okio.ByteString directly.
    implementation("com.squareup.okio:okio:3.6.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")

    debugImplementation("androidx.compose.ui:ui-tooling")

    testImplementation("junit:junit:4.13.2")
}
```

## `jarvis-android/build.gradle.kts`

```kotlin
plugins {
    id("com.android.application") version "8.7.3" apply false
    id("org.jetbrains.kotlin.android") version "2.0.21" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.21" apply false
    id("org.jetbrains.kotlin.plugin.serialization") version "2.0.21" apply false
}
```

## `jarvis-android/settings.gradle.kts`

```kotlin
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "JarvisMobile"
include(":app")
```

## `jarvis-client/app/build.gradle.kts`

```kotlin
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

android {
    namespace = "com.jarvis.client"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.jarvis.client"
        // 33, not 30: RuntimeShader/AGSL for the Nucleus face needs 33, and
        // taking 30 would mean a GLES fallback branch carried forever.
        minSdk = 33
        targetSdk = 36
        versionCode = 1
        versionName = "0.1-step0"
    }

    buildTypes {
        debug { isMinifyEnabled = false }
        release {
            // Minify off and proguardFiles listed anyway advertises a shrink that
            // does not happen. This module has no serialization runtime and no
            // reflective entry points yet, so the rules file is genuinely empty of
            // anything load-bearing; when step 2 adds the SSE client and its models,
            // turn this on rather than adding keeps that nothing verifies.
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        resources { excludes += "/META-INF/{AL2.0,LGPL2.1}" }
    }
}

dependencies {
    // NOT the 2026.08.00 the brief pins. That BOM resolves Compose 1.12.0,
    // whose every artifact declares minCompileSdk 37, and CheckAarMetadata
    // enforces that as a hard error. §3 also forbids compiling against 37
    // because it is Beta, so the two requirements cannot both be met.
    //
    // Surveying the BOMs by the minCompileSdk in their own AAR metadata:
    // 1.12.x needs 37, everything from 1.11.3 back to 1.9.1 needs 35. Compose
    // never required 36, so 2026.06.00 is the newest BOM usable here.
    //
    // The brief gives a reason for compileSdk 36 and none for this particular
    // BOM, so the BOM is the constraint that yields.
    implementation(platform("androidx.compose:compose-bom:2026.06.00"))

    implementation("androidx.core:core-ktx:1.15.0")
    // 1.12.4, not 1.9.3. androidx.activity is not managed by the Compose BOM, so
    // that pin was real rather than decorative: resolving the graph in CI shows
    // core-ktx and lifecycle floating up to 1.16.0 and 2.9.4 on their own, while
    // activity stayed at a November 2024 release hosting a 2026 Compose runtime
    // under targetSdk 36 — where edge-to-edge enforcement changed and
    // MainActivity calls enableEdgeToEdge(). 1.12.4 is the last patch of the
    // generation contemporaneous with Compose 1.11.3; 1.13.0 is stable but newer
    // than the BOM, and 1.14.x is alpha.
    implementation("androidx.activity:activity-compose:1.12.4")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")

    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.material3:material3")
    // Used directly (LazyColumn, background, KeyboardOptions) rather than relied on
    // as a material3 transitive.
    implementation("androidx.compose.foundation:foundation")

    // The serialization compiler plugin is applied in build.gradle.kts but no
    // runtime was declared, so the first @Serializable anyone wrote would have
    // failed to resolve rather than working. Step 2's event models need it.
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")

    testImplementation("junit:junit:4.13.2")
}
```

## `jarvis-client/build.gradle.kts`

```kotlin
// Versions verified against the registries on 13 Sep 2026, not inferred:
//   AGP 9.4.0            gradle-9.4.0.pom -> 200 on Google Maven
//   Kotlin               supplied BY AGP 9. The org.jetbrains.kotlin.android
//                        plugin is not applied: since AGP 9.0 it is built in,
//                        and applying it alongside is a hard error.
//   Compose BOM 2026.08.00  exists; pins androidx.compose.foundation 1.12.0
plugins {
    id("com.android.application") version "9.4.0" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.4.20" apply false
    id("org.jetbrains.kotlin.plugin.serialization") version "2.4.20" apply false
}
```

## `jarvis-client/settings.gradle.kts`

```kotlin
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "JarvisClient"
include(":app")
```

## `jarvis-android/gradle.properties`

```properties
org.gradle.jvmargs=-Xmx3072m -Dfile.encoding=UTF-8
org.gradle.parallel=true
org.gradle.caching=true

android.useAndroidX=true
android.nonTransitiveRClass=true

kotlin.code.style=official
```

## `jarvis-android/gradle/wrapper/gradle-wrapper.properties`

```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.11.1-bin.zip
# Verified against services.gradle.org, which this dev container cannot reach;
# read from a CI runner by .github/workflows/verify-toolchain.yml.
# validateDistributionUrl only checks the URL is well formed and reachable.
# Without this line every build downloads ~130 MB and executes it unverified.
distributionSha256Sum=f397b287023acdba1e9f6fc5ea72d22dd63669d59ed4a289a29b1a76eee151c6
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```

## `jarvis-client/gradle.properties`

```properties
org.gradle.jvmargs=-Xmx3072m -Dfile.encoding=UTF-8
org.gradle.parallel=true
org.gradle.caching=true
org.gradle.configuration-cache=true

android.useAndroidX=true
android.nonTransitiveRClass=true

kotlin.code.style=official
```

## `jarvis-client/gradle/wrapper/gradle-wrapper.properties`

```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-9.6.0-bin.zip
# Verified against services.gradle.org, which this dev container cannot reach;
# read from a CI runner by .github/workflows/verify-toolchain.yml.
# validateDistributionUrl only checks the URL is well formed and reachable.
# Without this line every build downloads ~130 MB and executes it unverified.
distributionSha256Sum=bbaeb2fef8710818cf0e261201dab964c572f92b942812df0c3620d62a529a01
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```

## `jarvis-android/app/src/main/AndroidManifest.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:tools="http://schemas.android.com/tools">

    <!-- Network: reaching the desktop server over Tailscale. -->
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />

    <!-- Audio: duplex voice pipeline. -->
    <uses-permission android:name="android.permission.RECORD_AUDIO" />
    <uses-permission android:name="android.permission.MODIFY_AUDIO_SETTINGS" />

    <!-- Power: stay reachable while the screen is off. -->
    <uses-permission android:name="android.permission.WAKE_LOCK" />
    <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />
    <uses-permission android:name="android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_MICROPHONE" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_SPECIAL_USE" />

    <!-- Device control. -->
    <!-- Torch uses CameraManager.setTorchMode, which requires no permission.
         CAMERA was declared and requested here and never used: it appeared in
         the same runtime batch as RECORD_AUDIO, so declining "Jarvis wants
         camera access" cost the user the microphone. android.permission.FLASHLIGHT
         is not a platform permission and was silently ignored. -->
    <uses-permission android:name="android.permission.VIBRATE" />
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />

    <uses-feature
        android:name="android.hardware.camera.flash"
        android:required="false" />
    <uses-feature
        android:name="android.hardware.camera"
        android:required="false" />
    <uses-feature
        android:name="android.hardware.microphone"
        android:required="false" />

    <application
        android:name=".JarvisApplication"
        android:allowBackup="false"
        android:icon="@mipmap/ic_launcher"
        android:label="@string/app_name"
        android:roundIcon="@mipmap/ic_launcher_round"
        android:supportsRtl="true"
        android:theme="@style/Theme.JarvisMobile"
        android:usesCleartextTraffic="true"
        tools:targetApi="35">

        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:launchMode="singleTask"
            android:showWhenLocked="true"
            android:turnScreenOn="true"
            android:theme="@style/Theme.JarvisMobile">

            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>

            <!-- Long-press power / corner swipe launches Jarvis. -->
            <intent-filter>
                <action android:name="android.intent.action.ASSIST" />
                <category android:name="android.intent.category.DEFAULT" />
            </intent-filter>

            <intent-filter>
                <action android:name="android.intent.action.VOICE_COMMAND" />
                <category android:name="android.intent.category.DEFAULT" />
            </intent-filter>

            <!-- Share sheet: send selected text straight into a note. -->
            <intent-filter>
                <action android:name="android.intent.action.SEND" />
                <category android:name="android.intent.category.DEFAULT" />
                <data android:mimeType="text/plain" />
            </intent-filter>
        </activity>

        <!-- One-tap capture from the notification shade. -->
        <service
            android:name=".service.QuickCaptureTileService"
            android:exported="true"
            android:icon="@drawable/ic_notification"
            android:label="@string/tile_quick_capture"
            android:permission="android.permission.BIND_QUICK_SETTINGS_TILE">
            <intent-filter>
                <action android:name="android.service.quicksettings.action.QS_TILE" />
            </intent-filter>
            <meta-data
                android:name="android.service.quicksettings.ACTIVE_TILE"
                android:value="false" />
        </service>

        <!-- System assistant hook. -->
        <service
            android:name=".service.JarvisVoiceService"
            android:exported="true"
            android:permission="android.permission.BIND_VOICE_INTERACTION"
            android:label="@string/app_name">
            <meta-data
                android:name="android.voice_interaction"
                android:resource="@xml/voice_interaction_service" />
            <intent-filter>
                <action android:name="android.service.voice.VoiceInteractionService" />
            </intent-filter>
        </service>

        <service
            android:name=".service.JarvisInteractionSessionService"
            android:exported="true"
            android:permission="android.permission.BIND_VOICE_INTERACTION" />

        <!-- No android:permission. BIND_VOICE_INTERACTION is signature-level and
             exists so only the system can bind a VoiceInteractionService; requiring
             it on a RecognitionService means every third-party SpeechRecognizer
             client is refused with ERROR_CLIENT and no callbacks, which made the
             advertised recognizer role unusable. RecognitionService documents no
             bind permission, and BIND_SPEECH_RECOGNIZER is not in the public SDK. -->
        <service
            android:name=".service.JarvisRecognitionService"
            android:exported="true">
            <intent-filter>
                <action android:name="android.speech.RecognitionService" />
            </intent-filter>
            <meta-data
                android:name="android.speech"
                android:resource="@xml/recognition_service" />
        </service>

        <receiver
            android:name=".service.BootReceiver"
            android:enabled="true"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.BOOT_COMPLETED" />
                <action android:name="android.intent.action.MY_PACKAGE_REPLACED" />
            </intent-filter>
        </receiver>

        <!-- Keeps the WebSocket and the duplex audio pipeline alive in the background. -->
        <service
            android:name=".service.JarvisForegroundService"
            android:exported="false"
            android:foregroundServiceType="microphone|specialUse">
            <property
                android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE"
                android:value="@string/fgs_special_use_reason" />
        </service>

        <!-- Home screen widgets. updatePeriodMillis=0 throughout: these are
             redrawn by state changes, never by a polling clock. -->
        <receiver
            android:name=".widget.approval.ApprovalWidgetReceiver"
            android:exported="true"
            android:label="@string/widget_approval_name">
            <intent-filter>
                <action android:name="android.appwidget.action.APPWIDGET_UPDATE" />
            </intent-filter>
            <meta-data
                android:name="android.appwidget.provider"
                android:resource="@xml/widget_approval_info" />
        </receiver>

        <receiver
            android:name=".widget.launcher.QuickLauncherReceiver"
            android:exported="true"
            android:label="@string/widget_launcher_name">
            <intent-filter>
                <action android:name="android.appwidget.action.APPWIDGET_UPDATE" />
            </intent-filter>
            <meta-data
                android:name="android.appwidget.provider"
                android:resource="@xml/widget_launcher_info" />
        </receiver>

        <receiver
            android:name=".widget.telemetry.TelemetryReceiver"
            android:exported="true"
            android:label="@string/widget_telemetry_name">
            <intent-filter>
                <action android:name="android.appwidget.action.APPWIDGET_UPDATE" />
            </intent-filter>
            <meta-data
                android:name="android.appwidget.provider"
                android:resource="@xml/widget_telemetry_info" />
        </receiver>

        <!-- Lock-screen Approve / Reject taps land here. -->
        <receiver
            android:name=".notifications.ApprovalActionReceiver"
            android:exported="false" />

    </application>
</manifest>
```

## `jarvis-android/app/src/main/res/drawable/ic_launcher_foreground.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp"
    android:height="108dp"
    android:viewportWidth="108"
    android:viewportHeight="108">
    <path
        android:fillColor="#FF22D3EE"
        android:fillType="evenOdd"
        android:pathData="M26,54 a28,28 0 1,0 56,0 a28,28 0 1,0 -56,0 Z M34,54 a20,20 0 1,0 40,0 a20,20 0 1,0 -40,0 Z" />
    <path
        android:fillColor="#FF22D3EE"
        android:pathData="M45,54 a9,9 0 1,0 18,0 a9,9 0 1,0 -18,0 Z" />
</vector>
```

## `jarvis-android/app/src/main/res/drawable/ic_notification.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp"
    android:height="24dp"
    android:viewportWidth="24"
    android:viewportHeight="24"
    android:tint="#FFFFFFFF">
    <path
        android:fillColor="#FFFFFFFF"
        android:fillType="evenOdd"
        android:pathData="M2,12 a10,10 0 1,0 20,0 a10,10 0 1,0 -20,0 Z M5,12 a7,7 0 1,0 14,0 a7,7 0 1,0 -14,0 Z" />
    <path
        android:fillColor="#FFFFFFFF"
        android:pathData="M8.5,12 a3.5,3.5 0 1,0 7,0 a3.5,3.5 0 1,0 -7,0 Z" />
</vector>
```

## `jarvis-android/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background" />
    <foreground android:drawable="@drawable/ic_launcher_foreground" />
    <monochrome android:drawable="@drawable/ic_launcher_foreground" />
</adaptive-icon>
```

## `jarvis-android/app/src/main/res/mipmap-anydpi-v26/ic_launcher_round.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background" />
    <foreground android:drawable="@drawable/ic_launcher_foreground" />
    <monochrome android:drawable="@drawable/ic_launcher_foreground" />
</adaptive-icon>
```

## `jarvis-android/app/src/main/res/values/colors.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <!-- Pure black so AMOLED pixels stay unlit. -->
    <color name="jarvis_black">#FF000000</color>
    <color name="jarvis_cyan">#FF22D3EE</color>
    <color name="ic_launcher_background">#FF000000</color>
</resources>
```

## `jarvis-android/app/src/main/res/values/strings.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">Jarvis Mobile</string>
    <string name="assist_label">Jarvis</string>

    <string name="fgs_special_use_reason">Maintains the persistent link to the user\'s own self-hosted Jarvis server so approval requests and voice replies arrive while the device is locked.</string>

    <string name="channel_approvals_name">Jarvis Approvals</string>
    <string name="channel_approvals_description">Interactive approval requests from the Jarvis desktop server.</string>
    <string name="channel_link_name">Jarvis Link</string>
    <string name="channel_link_description">Ongoing status of the connection to the Jarvis desktop server.</string>

    <string name="tile_quick_capture">Jarvis Capture</string>
    <string name="tile_subtitle_linked">Linked</string>
    <string name="tile_subtitle_reconnecting">Reconnecting</string>
    <string name="tile_subtitle_offline">Offline — will queue</string>

    <string name="widget_approval_name">Jarvis Approvals</string>
    <string name="widget_approval_desc">Review and approve pending autonomy requests.</string>
    <string name="widget_launcher_name">Jarvis Quick Launch</string>
    <string name="widget_launcher_desc">Status indicator and one-tap voice or note capture.</string>
    <string name="widget_telemetry_name">Jarvis Workstation Telemetry</string>
    <string name="widget_telemetry_desc">Desktop GPU, VRAM, and CPU telemetry.</string>

    <string name="action_approve">Approve</string>
    <string name="action_reject">Reject</string>
</resources>
```

## `jarvis-android/app/src/main/res/values/themes.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="Theme.JarvisMobile" parent="android:Theme.Material.NoActionBar">
        <item name="android:windowBackground">@color/jarvis_black</item>
        <item name="android:statusBarColor">@color/jarvis_black</item>
        <item name="android:navigationBarColor">@color/jarvis_black</item>
        <item name="android:windowLightStatusBar">false</item>
    </style>
</resources>
```

## `jarvis-android/app/src/main/res/xml/recognition_service.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<recognition-service
    xmlns:android="http://schemas.android.com/apk/res/android"
    android:settingsActivity="com.jarvis.assistant.MainActivity" />
```

## `jarvis-android/app/src/main/res/xml/voice_interaction_service.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<voice-interaction-service
    xmlns:android="http://schemas.android.com/apk/res/android"
    android:sessionService="com.jarvis.assistant.service.JarvisInteractionSessionService"
    android:recognitionService="com.jarvis.assistant.service.JarvisRecognitionService"
    android:supportsAssist="true"
    android:supportsLaunchVoiceAssistFromKeyguard="true"
    android:supportsLocalInteraction="true" />
```

## `jarvis-android/app/src/main/res/xml/widget_approval_info.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<!-- initialLayout is required: without it AppWidgetHostView cannot inflate
     anything before the first Glance update lands, and the launcher shows
     "Problem loading widget". aapt does not enforce it. -->
<appwidget-provider xmlns:android="http://schemas.android.com/apk/res/android"
    android:initialLayout="@layout/glance_default_loading_layout"
    android:description="@string/widget_approval_desc"
    android:minWidth="260dp"
    android:minHeight="110dp"
    android:targetCellWidth="4"
    android:targetCellHeight="2"
    android:maxResizeWidth="500dp"
    android:maxResizeHeight="300dp"
    android:resizeMode="horizontal|vertical"
    android:updatePeriodMillis="0"
    android:widgetCategory="home_screen" />
```

## `jarvis-android/app/src/main/res/xml/widget_launcher_info.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<!-- initialLayout is required: without it AppWidgetHostView cannot inflate
     anything before the first Glance update lands, and the launcher shows
     "Problem loading widget". aapt does not enforce it. -->
<appwidget-provider xmlns:android="http://schemas.android.com/apk/res/android"
    android:initialLayout="@layout/glance_default_loading_layout"
    android:description="@string/widget_launcher_desc"
    android:minWidth="260dp"
    android:minHeight="40dp"
    android:targetCellWidth="4"
    android:targetCellHeight="1"
    android:resizeMode="horizontal"
    android:updatePeriodMillis="0"
    android:widgetCategory="home_screen" />
```

## `jarvis-android/app/src/main/res/xml/widget_telemetry_info.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<!-- initialLayout is required: without it AppWidgetHostView cannot inflate
     anything before the first Glance update lands, and the launcher shows
     "Problem loading widget". aapt does not enforce it. -->
<appwidget-provider xmlns:android="http://schemas.android.com/apk/res/android"
    android:initialLayout="@layout/glance_default_loading_layout"
    android:description="@string/widget_telemetry_desc"
    android:minWidth="130dp"
    android:minHeight="110dp"
    android:targetCellWidth="2"
    android:targetCellHeight="2"
    android:resizeMode="horizontal|vertical"
    android:updatePeriodMillis="0"
    android:widgetCategory="home_screen" />
```

## `jarvis-client/app/src/main/AndroidManifest.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:tools="http://schemas.android.com/tools">

    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />

    <!-- §3.1(2). specialUse is uncapped; dataSync is not. See strings.xml. -->
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_SPECIAL_USE" />

    <!-- §3.1(3). Runtime grant since API 33. Denied, the service still runs but
         its ongoing notification is hidden from the drawer, which is exactly
         the state step 8's live-state notification depends on. -->
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />

    <!-- The service returns START_STICKY, and a sticky restart happens with the app
         in the background - which is not on the FGS background-start exemption list,
         so startForeground throws and the link ends permanently. A battery-optimisation
         exemption is the exemption that covers it. Requested from the readiness
         screen, never silently. -->
    <uses-permission android:name="android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS" />

    <!-- So the link comes back after a reboot rather than waiting for the user to
         open the app. BOOT_COMPLETED is itself an explicit FGS start exemption. -->
    <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />

    <application
        android:name=".JarvisApp"
        android:allowBackup="false"
        android:icon="@mipmap/ic_launcher"
        android:roundIcon="@mipmap/ic_launcher_round"
        android:label="@string/app_name"
        android:networkSecurityConfig="@xml/network_security_config"
        android:supportsRtl="true"
        android:theme="@style/Theme.Jarvis"
        tools:targetApi="36">

        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:launchMode="singleTask">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>

        <receiver
            android:name=".service.BootReceiver"
            android:enabled="true"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.BOOT_COMPLETED" />
                <action android:name="android.intent.action.MY_PACKAGE_REPLACED" />
            </intent-filter>
        </receiver>

        <service
            android:name=".service.EventService"
            android:exported="false"
            android:foregroundServiceType="specialUse">
            <property
                android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE"
                android:value="@string/fgs_special_use_reason" />
        </service>
    </application>
</manifest>
```

## `jarvis-client/app/src/main/res/drawable/ic_launcher_foreground.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<!-- Vector rather than a raster set: one file covers every density, and the
     monochrome layer below needs a path anyway. -->
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp"
    android:height="108dp"
    android:viewportWidth="108"
    android:viewportHeight="108">
    <path
        android:fillColor="#FF22D3EE"
        android:fillType="evenOdd"
        android:pathData="M26,54 a28,28 0 1,0 56,0 a28,28 0 1,0 -56,0 Z M34,54 a20,20 0 1,0 40,0 a20,20 0 1,0 -40,0 Z" />
    <path
        android:fillColor="#FF22D3EE"
        android:pathData="M45,54 a9,9 0 1,0 18,0 a9,9 0 1,0 -18,0 Z" />
</vector>
```

## `jarvis-client/app/src/main/res/drawable/ic_notification.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<!-- Status bar icons are drawn as a single-colour mask, so this is a solid
     silhouette. The platform tints it; the fillColor here is only a placeholder. -->
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp"
    android:height="24dp"
    android:viewportWidth="24"
    android:viewportHeight="24"
    android:tint="#FFFFFFFF">
    <path
        android:fillColor="#FFFFFFFF"
        android:fillType="evenOdd"
        android:pathData="M4,12 a8,8 0 1,0 16,0 a8,8 0 1,0 -16,0 Z M6.5,12 a5.5,5.5 0 1,0 11,0 a5.5,5.5 0 1,0 -11,0 Z" />
    <path
        android:fillColor="#FFFFFFFF"
        android:pathData="M10,12 a2,2 0 1,0 4,0 a2,2 0 1,0 -4,0 Z" />
</vector>
```

## `jarvis-client/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background" />
    <foreground android:drawable="@drawable/ic_launcher_foreground" />
    <monochrome android:drawable="@drawable/ic_launcher_foreground" />
</adaptive-icon>
```

## `jarvis-client/app/src/main/res/mipmap-anydpi-v26/ic_launcher_round.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background" />
    <foreground android:drawable="@drawable/ic_launcher_foreground" />
    <monochrome android:drawable="@drawable/ic_launcher_foreground" />
</adaptive-icon>
```

## `jarvis-client/app/src/main/res/values/colors.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="ic_launcher_background">#FF000000</color>
</resources>
```

## `jarvis-client/app/src/main/res/values/strings.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">Jarvis</string>

    <!--
      §3.1(2). specialUse, not dataSync. dataSync is capped at six hours per
      rolling 24h on Android 15; when the budget runs out the system calls
      onTimeout() and then throws a fatal RemoteServiceException. For an
      assistant meant to be there when you speak to it that is a crash on a
      timer, not a limitation.

      The usual cost of specialUse is a Play Console justification review. This
      APK is sideloaded, never listed and non-commercial, so that cost does not
      apply here.
    -->
    <string name="fgs_special_use_reason">Holds the live event connection to the
        user\'s own Jarvis backend, running on their own machine, so approval
        requests arrive while the screen is off.</string>

    <string name="channel_link_name">Jarvis link</string>
    <string name="channel_link_desc">Ongoing connection to your Jarvis backend.</string>
</resources>
```

## `jarvis-client/app/src/main/res/values/themes.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="Theme.Jarvis" parent="android:Theme.Material.NoActionBar">
        <item name="android:windowBackground">@android:color/black</item>
        <item name="android:statusBarColor">@android:color/transparent</item>
        <item name="android:navigationBarColor">@android:color/transparent</item>
    </style>
</resources>
```

## `jarvis-client/app/src/main/res/xml/network_security_config.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<!--
  §3.1(1). Cleartext is off by default for targetSdk 28+, and this app speaks
  plain HTTP to a backend on the tailnet. With no config the connection fails
  looking like a network error, not a policy one.

  The config wins over android:usesCleartextTraffic on API 24+, so the manifest
  flag is omitted entirely rather than set and silently ignored.

  Hostname route, per the brief's own preference. `ts.net` with subdomains
  covers every Tailscale MagicDNS name without the build needing to know which
  one, which is what makes this work for a host the user types at run time.

  What this deliberately does NOT cover: a bare 100.x.y.z or a 192.168.x.y
  typed as digits. A network security config matches hostname strings and
  cannot express a CIDR range, so covering the CGNAT block would mean listing
  four million literals. Pair by MagicDNS name instead - which also survives
  the address changing. The app says so when the host it is given cannot be
  reached in cleartext.
-->
<network-security-config>
    <base-config cleartextTrafficPermitted="false" />

    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="true">ts.net</domain>
        <domain includeSubdomains="true">localhost</domain>
        <domain includeSubdomains="false">127.0.0.1</domain>
    </domain-config>
</network-security-config>
```

## `jarvis-android/app/proguard-rules.pro`

```text
# Kotlinx Serialization keeps its generated serializers via companion objects.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
-keepclassmembers class com.jarvis.assistant.network.** {
    *** Companion;
}
-keepclasseswithmembers class com.jarvis.assistant.network.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# OkHttp ships optional Conscrypt/Bouncy Castle hooks that are absent at runtime.
-dontwarn okhttp3.internal.platform.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**
```

## `jarvis-client/app/proguard-rules.pro`

```text
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/JarvisApplication.kt`

```kotlin
package com.jarvis.assistant

import android.app.Application
import android.content.Context
import android.util.Base64
import android.util.Log
import com.jarvis.assistant.audio.AudioPlayer
import com.jarvis.assistant.audio.AudioStreamer
import com.jarvis.assistant.data.JarvisSettings
import com.jarvis.assistant.data.PendingDecisionStore
import com.jarvis.assistant.data.PendingNoteStore
import com.jarvis.assistant.data.repository.WidgetDataRepository
import com.jarvis.assistant.network.ApprovalDecisionMessage
import com.jarvis.assistant.network.ApprovalRequestEvent
import com.jarvis.assistant.network.ApprovalResolvedEvent
import com.jarvis.assistant.network.AudioChunkEvent
import com.jarvis.assistant.network.AudioInputEndMessage
import com.jarvis.assistant.network.AudioInputStartMessage
import com.jarvis.assistant.network.AudioStreamEndEvent
import com.jarvis.assistant.network.AudioStreamStartEvent
import com.jarvis.assistant.network.ConnectionState
import com.jarvis.assistant.network.DesktopTelemetryEvent
import com.jarvis.assistant.network.DeviceCommandEvent
import com.jarvis.assistant.network.DeviceCommandResultMessage
import com.jarvis.assistant.network.HelloMessage
import com.jarvis.assistant.network.InterruptMessage
import com.jarvis.assistant.network.JarvisWebSocketManager
import com.jarvis.assistant.network.OutboundMessage
import com.jarvis.assistant.network.PingMessage
import com.jarvis.assistant.network.PongEvent
import com.jarvis.assistant.network.QuickNoteMessage
import com.jarvis.assistant.network.SocketSignal
import com.jarvis.assistant.network.StatusEvent
import com.jarvis.assistant.network.TelemetryRequestEvent
import com.jarvis.assistant.network.TelemetrySnapshotMessage
import com.jarvis.assistant.notifications.ApprovalNotificationManager
import com.jarvis.assistant.notifications.ApprovalSigner
import com.jarvis.assistant.telemetry.CommandOutcome
import com.jarvis.assistant.telemetry.DeviceTelemetryProvider
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.jsonPrimitive
import java.util.UUID
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicBoolean

class JarvisApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        JarvisRuntime.initialize(this)
    }
}

/**
 * Process-wide hub shared by the HUD, the foreground service, the assistant
 * session and the lock-screen BroadcastReceiver.
 *
 * A singleton rather than injected graph because every one of those entry points
 * can be the one that cold-starts the process, and they all need the same live
 * socket rather than four of them.
 */
object JarvisRuntime {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    @Volatile private var started = false

    lateinit var settings: JarvisSettings
        private set
    lateinit var telemetry: DeviceTelemetryProvider
        private set
    lateinit var approvals: ApprovalNotificationManager
        private set
    lateinit var player: AudioPlayer
        private set
    lateinit var pendingNotes: PendingNoteStore
        private set
    lateinit var pendingDecisions: PendingDecisionStore
        private set

    private lateinit var appContext: Context
    private lateinit var streamer: AudioStreamer

    val socket: JarvisWebSocketManager = JarvisWebSocketManager.get()

    private val _pendingApprovals = MutableStateFlow<List<ApprovalRequestEvent>>(emptyList())
    val pendingApprovals: StateFlow<List<ApprovalRequestEvent>> = _pendingApprovals.asStateFlow()

    private val _desktopTelemetry = MutableStateFlow<DesktopTelemetryEvent?>(null)
    val desktopTelemetry: StateFlow<DesktopTelemetryEvent?> = _desktopTelemetry.asStateFlow()

    private val _statusText = MutableStateFlow<String?>(null)
    val statusText: StateFlow<String?> = _statusText.asStateFlow()

    private val _micActive = MutableStateFlow(false)
    val micActive: StateFlow<Boolean> = _micActive.asStateFlow()

    /** Non-null when a decision could not be signed or the target was refused. */
    private val _blockingError = MutableStateFlow<String?>(null)
    val blockingError: StateFlow<String?> = _blockingError.asStateFlow()

    /** Last measured round trip to the desktop, or null before the first pong. */
    private val _latencyMs = MutableStateFlow<Long?>(null)
    val latencyMs: StateFlow<Long?> = _latencyMs.asStateFlow()

    /** Lets widgets read state without booting the socket from a cold process. */
    val isInitialized: Boolean get() = started

    /**
     * Messages that could not go out immediately, replayed on reconnect.
     *
     * Bounded, and audio control messages are dropped rather than queued: replaying
     * `audio_input_start`/`audio_input_end` pairs for streams that ended minutes ago
     * tells the desktop about microphone sessions that no longer exist, and there is
     * no PCM to go with them. Approval decisions do not live here at all — they are
     * persisted, because this queue dies with the process.
     */
    private val outbox = ConcurrentLinkedQueue<OutboundMessage>()

    /**
     * Guards the mic start/stop transition. `_micActive` alone is check-then-act:
     * the assistant flow on the main thread and a bound SpeechRecognizer on a binder
     * thread can both read false, both mint a stream id and both send an
     * `audio_input_start`, and only one of them is ever ended.
     */
    private val micTransition = AtomicBoolean(false)

    /**
     * Set by the foreground service. Promotes the service to the `microphone`
     * foreground type and reports whether the platform allowed it.
     *
     * The promotion has to happen *before* AudioRecord.startRecording(): the audio
     * policy decides mic eligibility at that call, so opening the mic first and
     * promoting afterwards yields zeroed frames. And a refusal has to stop the
     * capture rather than be logged — otherwise the notification reads "Listening"
     * while the desktop receives silence.
     */
    @Volatile var micForegroundPromoter: ((Boolean) -> Boolean)? = null

    @Volatile private var micStreamId: String? = null
    @Volatile private var expectingWavHeader = false
    @Volatile private var downlinkTag: Int? = null

    @Synchronized
    fun initialize(context: Context) {
        if (started) return
        appContext = context.applicationContext
        settings = JarvisSettings(appContext)
        telemetry = DeviceTelemetryProvider(appContext)
        approvals = ApprovalNotificationManager(appContext)
        pendingNotes = PendingNoteStore(appContext)
        pendingDecisions = PendingDecisionStore(appContext)
        player = AudioPlayer()
        streamer = AudioStreamer(appContext) { buffer, length ->
            socket.sendAudio(buffer, length)
        }
        started = true

        // One ordered collector over both transports. Text and binary used to be
        // collected independently, which loses the ordering between a stream's PCM
        // frames and its own start/end events.
        scope.launch {
            socket.incoming.collect { signal ->
                when (signal) {
                    is SocketSignal.Event -> handleEvent(signal.event)
                    is SocketSignal.Binary -> handleBinaryAudio(signal.frame)
                }
            }
        }
        scope.launch {
            socket.state.collect { state ->
                if (state == ConnectionState.CONNECTED) onConnected()
            }
        }

        WidgetDataRepository.observe(appContext, scope)

        connect()
    }

    /**
     * Refuses to dial an unencrypted target outside the Tailnet or a private LAN,
     * so a mistyped address cannot put approvals and voice on the open internet.
     */
    fun connect() {
        val url = settings.resolveWebSocketUrl()
        if (!JarvisSettings.isCleartextTargetPrivate(url)) {
            _blockingError.value =
                "Refusing plaintext ws:// to a public host. Use a Tailscale address or wss://."
            socket.disconnect()
            return
        }
        if (_blockingError.value?.startsWith("Refusing plaintext") == true) {
            _blockingError.value = null
        }
        socket.connect(url, settings.authToken)
    }

    fun updateServerAddress(address: String) {
        settings.setServerAddress(address)
        connect()
    }

    fun updateSharedSecret(secret: String) {
        settings.sharedSecret = secret
        if (secret.isNotEmpty()) _blockingError.value = null
    }

    fun updateAuthToken(token: String) {
        settings.authToken = token
        reconnectNow()
    }

    /** User-driven "try again now", bypassing the remaining backoff delay. */
    fun reconnectNow() {
        if (::settings.isInitialized) {
            connect()
            socket.reconnectNow()
        }
    }

    private fun onConnected() {
        socket.send(
            HelloMessage(
                deviceId = settings.deviceId,
                appVersion = BuildConfig.VERSION_NAME,
            ),
        )
        while (true) {
            val queued = outbox.peek() ?: break
            if (!socket.send(queued)) break
            outbox.poll()
        }

        flushPendingDecisions()
        flushPendingNotes()
        measureLatency()
    }

    /**
     * Replays decisions that were signed but never reached the desktop. Each row is
     * removed only once the socket has taken it, and the signature already covers
     * the nonce and timestamp, so a replay cannot alter what was agreed to.
     */
    private fun flushPendingDecisions() {
        for (decision in pendingDecisions.snapshot()) {
            if (!socket.send(decision)) return
            pendingDecisions.remove(decision)
        }
    }

    /** Fire-and-forget probe; the reply updates [latencyMs] when it lands. */
    fun measureLatency() {
        if (!started) return
        socket.send(PingMessage(System.currentTimeMillis()))
    }

    /**
     * Replays notes captured while offline, oldest first so the journal keeps
     * the order they were written in. Each is removed only once the socket has
     * actually taken it.
     */
    private fun flushPendingNotes() {
        for (note in pendingNotes.snapshot()) {
            if (!socket.send(note)) return
            pendingNotes.remove(note)
        }
    }

    /**
     * Capture never fails in front of the user: an unsendable note goes to disk
     * and is replayed on reconnect.
     *
     * @return true when it went straight out over the socket.
     */
    fun sendQuickNote(target: String, content: String, mode: String? = null): Boolean {
        val trimmed = content.trim()
        if (trimmed.isEmpty()) return false

        val note = QuickNoteMessage(
            target = target,
            // A journal is a running log, a vault note is a document.
            mode = mode ?: if (target == QuickNoteMessage.TARGET_LOGSEQ) {
                QuickNoteMessage.MODE_APPEND
            } else {
                QuickNoteMessage.MODE_CREATE
            },
            content = trimmed,
            timestampMs = System.currentTimeMillis(),
        )

        if (socket.send(note)) {
            telemetry.vibrate("confirm")
            return true
        }
        pendingNotes.add(note)
        telemetry.vibrate("tick")
        connect()
        return false
    }

    // --------------------------------------------------------- inbound ----

    private fun handleEvent(event: com.jarvis.assistant.network.InboundEvent) {
        when (event) {
            is ApprovalRequestEvent -> {
                _pendingApprovals.value = _pendingApprovals.value
                    .filterNot { it.id == event.id } + event
                approvals.post(event)
                telemetry.vibrate("alert")
            }

            is ApprovalResolvedEvent -> clearApproval(event.id)

            is AudioStreamStartEvent -> {
                expectingWavHeader = event.encoding.equals("wav", ignoreCase = true)
                downlinkTag = event.binaryTag
                player.start(event.sampleRate, event.channels)
            }

            is AudioChunkEvent -> {
                val decoded = runCatching { Base64.decode(event.data, Base64.DEFAULT) }.getOrNull()
                if (decoded == null) {
                    Log.w(TAG, "undecodable audio chunk seq=${event.seq}")
                    return
                }
                player.enqueue(stripWavHeaderIfPresent(decoded))
            }

            is AudioStreamEndEvent -> {
                expectingWavHeader = false
                downlinkTag = null
                player.finish()
            }

            is DeviceCommandEvent -> executeDeviceCommand(event)

            // Off the collector: collectTelemetrySnapshot does three binder round
            // trips and enumerates cameras. Doing it inline stalls the one consumer
            // of the socket for long enough to matter during a reply.
            is TelemetryRequestEvent -> scope.launch {
                sendOrQueue(
                    TelemetrySnapshotMessage(event.id, telemetry.collectTelemetrySnapshot()),
                )
            }

            is DesktopTelemetryEvent -> _desktopTelemetry.value = event

            is StatusEvent -> _statusText.value = event.text

            is PongEvent -> {
                val rtt = System.currentTimeMillis() - event.sentAtMs
                // A negative or absurd value means the clocks disagree, not that
                // the link is fast; showing it would be worse than showing none.
                _latencyMs.value = rtt.takeIf { it in 0..60_000 }
            }
        }
    }

    /**
     * Binary downlink: `[tag][pcm…]`, where the tag was announced by the
     * audio_stream_start that opened the stream. Frames for any other tag belong
     * to a stream that has already ended and are dropped.
     */
    private fun handleBinaryAudio(frame: ByteArray) {
        val expected = downlinkTag ?: return
        if (frame.isEmpty()) return
        if ((frame[0].toInt() and 0xFF) != expected) return
        if (frame.size <= 1) return
        player.enqueue(stripWavHeaderIfPresent(frame.copyOfRange(1, frame.size)))
    }

    /** WAV downlinks carry a 44-byte RIFF header the AudioTrack must not play. */
    private fun stripWavHeaderIfPresent(chunk: ByteArray): ByteArray {
        if (!expectingWavHeader) return chunk
        expectingWavHeader = false
        val isRiff = chunk.size > WAV_HEADER_BYTES &&
            chunk[0] == 'R'.code.toByte() && chunk[1] == 'I'.code.toByte() &&
            chunk[2] == 'F'.code.toByte() && chunk[3] == 'F'.code.toByte()
        return if (isRiff) chunk.copyOfRange(WAV_HEADER_BYTES, chunk.size) else chunk
    }

    private fun executeDeviceCommand(event: DeviceCommandEvent) {
        fun param(name: String): String? =
            runCatching { event.params[name]?.jsonPrimitive?.content }.getOrNull()

        val outcome: CommandOutcome = when (event.action) {
            "torch_on" -> telemetry.setTorch(true)
            "torch_off" -> telemetry.setTorch(false)
            "torch_toggle" -> telemetry.toggleTorch()
            "set_volume" -> {
                val percent = param("percent")?.toIntOrNull()
                if (percent == null) {
                    CommandOutcome(false, "set_volume requires a numeric 'percent'")
                } else {
                    telemetry.setMediaVolumePercent(percent)
                }
            }
            "vibrate" -> telemetry.vibrate(param("pattern") ?: "tick")
            "interrupt_audio" -> {
                player.flushNow()
                CommandOutcome(true, "playback flushed")
            }
            "telemetry" -> {
                scope.launch {
                    sendOrQueue(
                        TelemetrySnapshotMessage(event.id, telemetry.collectTelemetrySnapshot()),
                    )
                }
                CommandOutcome(true, "snapshot sent")
            }
            else -> {
                DeviceTelemetryProvider.logUnsupported(event.action)
                CommandOutcome(false, "unknown action '${event.action}'")
            }
        }

        sendOrQueue(DeviceCommandResultMessage(event.id, outcome.ok, outcome.detail))
    }

    // -------------------------------------------------------- outbound ----

    private fun sendOrQueue(message: OutboundMessage) {
        if (socket.send(message)) return
        when (message) {
            // Bracketing messages for a capture session that is already over. Sending
            // them minutes later describes a stream the desktop never saw any audio
            // for, so drop them instead.
            is AudioInputStartMessage, is AudioInputEndMessage, is InterruptMessage -> {
                Log.i(TAG, "dropping stale ${message::class.simpleName} rather than queueing it")
            }
            else -> {
                while (outbox.size >= OUTBOX_CAPACITY) outbox.poll()
                outbox.add(message)
            }
        }
        connect()
    }

    /**
     * Whether [requestId] can still be decided right now.
     *
     * Three gates, and all three exist because of the rule that the app never
     * auto-approves anything and refuses to act on a stale event stream:
     *
     *  - the request must be one the desktop actually sent and has not resolved.
     *    Without this the method signs whatever id it is handed, and it is reachable
     *    from a widget action whose parameters are not under the app's control — a
     *    signing oracle for decisions the user never saw;
     *  - it must not have expired. `expires_at_ms` was parsed and never read, so an
     *    expired card stayed tappable and re-signed with a fresh `decided_at_ms`
     *    that sails through the desktop's clock-skew window;
     *  - the link must be up. Accepting a decision offline clears the card and
     *    buzzes "confirm" while nothing has been sent, which is exactly the
     *    false confirmation the stale-stream rule exists to prevent.
     */
    fun approvalBlocker(requestId: String, nowMs: Long = System.currentTimeMillis()): String? {
        val request = _pendingApprovals.value.firstOrNull { it.id == requestId }
            ?: return "That request is no longer pending — it was resolved or withdrawn."
        val expiry = request.expiresAtMs
        if (expiry != null && nowMs >= expiry) {
            return "That request expired. Ask the desktop to raise it again."
        }
        if (socket.state.value != ConnectionState.CONNECTED) {
            return "Not connected to the desktop, so this decision cannot be delivered yet."
        }
        if (!settings.hasSharedSecret.value) {
            return "No pairing secret set, so this decision cannot be signed. Set one below."
        }
        return null
    }

    /** True when the HUD and the widgets should offer Approve/Deny at all. */
    fun canDecide(requestId: String): Boolean = approvalBlocker(requestId) == null

    /**
     * An unsigned decision is never sent, and neither is one that fails any gate in
     * [approvalBlocker]. The request stays in the pending list and the HUD says why,
     * rather than the desktop acting on an approval this handset cannot prove it
     * authorised — or the user believing they answered something that never left.
     */
    fun submitApprovalDecision(requestId: String, approved: Boolean) {
        val blocker = approvalBlocker(requestId)
        if (blocker != null) {
            _blockingError.value = blocker
            telemetry.vibrate("alert")
            return
        }

        val now = System.currentTimeMillis()
        val nonce = UUID.randomUUID().toString()
        val signature = ApprovalSigner.sign(
            secret = settings.sharedSecret,
            id = requestId,
            approved = approved,
            deviceId = settings.deviceId,
            atMs = now,
            nonce = nonce,
        )

        if (signature == null) {
            _blockingError.value =
                "No pairing secret set, so this decision cannot be signed. Set one below."
            telemetry.vibrate("alert")
            return
        }

        val decision = ApprovalDecisionMessage(
            id = requestId,
            approved = approved,
            deviceId = settings.deviceId,
            decidedAtMs = now,
            nonce = nonce,
            signature = signature,
        )

        // Persisted before the send is attempted, not after it fails. The caller may
        // be a BroadcastReceiver on a cold process whose importance boost lapses the
        // moment onReceive returns, and the send is asynchronous.
        pendingDecisions.add(decision)
        if (socket.send(decision)) pendingDecisions.remove(decision) else connect()

        clearApproval(requestId)
        telemetry.vibrate(if (approved) "confirm" else "tick")
    }

    private fun clearApproval(requestId: String) {
        _pendingApprovals.value = _pendingApprovals.value.filterNot { it.id == requestId }
        approvals.cancel(requestId)
    }

    // ------------------------------------------------------------- mic ----

    fun hasMicPermission(): Boolean = streamer.hasPermission()

    /**
     * Barge-in is part of starting the mic: whatever the desktop is currently
     * speaking is cut locally and remotely before the first uplink byte.
     */
    fun startMic(): Boolean {
        // Single-flight rather than check-then-act: this is called from the main
        // thread by the HUD and the assistant, and from a binder thread by a bound
        // SpeechRecognizer.
        if (!micTransition.compareAndSet(false, true)) return _micActive.value
        try {
            if (_micActive.value) return true
            bargeIn()

            // Promote the foreground service before the mic is opened, and abort if
            // the platform refuses — a `microphone` foreground service cannot be
            // started from the background, and capturing anyway yields silence under
            // a notification that claims to be listening.
            val promoter = micForegroundPromoter
            if (promoter != null && !promoter(true)) {
                _blockingError.value =
                    "Android would not allow microphone capture from the background. " +
                        "Open Jarvis and try again."
                return false
            }

            val streamId = UUID.randomUUID().toString()
            micStreamId = streamId
            sendOrQueue(
                AudioInputStartMessage(
                    streamId = streamId,
                    sampleRate = AudioStreamer.SAMPLE_RATE,
                ),
            )
            val ok = streamer.start()
            if (!ok) {
                micStreamId = null
                sendOrQueue(AudioInputEndMessage(streamId))
                promoter?.invoke(false)
                return false
            }
            _micActive.value = true
            return true
        } finally {
            micTransition.set(false)
        }
    }

    fun stopMic() {
        if (!micTransition.compareAndSet(false, true)) return
        try {
            if (!_micActive.value) return
            streamer.stop()
            _micActive.value = false
            micStreamId?.let { sendOrQueue(AudioInputEndMessage(it)) }
            micStreamId = null
            micForegroundPromoter?.invoke(false)
        } finally {
            micTransition.set(false)
        }
    }

    fun toggleMic(): Boolean = if (_micActive.value) {
        stopMic()
        false
    } else {
        startMic()
    }

    fun bargeIn() {
        player.flushNow()
        socket.send(InterruptMessage())
    }

    fun shutdown() {
        stopMic()
        player.release()
        socket.disconnect()
    }

    private const val TAG = "JarvisRuntime"
    private const val WAV_HEADER_BYTES = 44

    /** Small: this queue only holds things worth replaying, and it is never drained
     *  by anything but a successful reconnect. */
    private const val OUTBOX_CAPACITY = 64
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/MainActivity.kt`

```kotlin
package com.jarvis.assistant

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.systemBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.jarvis.assistant.network.ConnectionState
import com.jarvis.assistant.service.JarvisForegroundService
import com.jarvis.assistant.ui.capture.CaptureTarget
import com.jarvis.assistant.ui.capture.QuickCaptureSheet
import com.jarvis.assistant.ui.screens.HudActions
import com.jarvis.assistant.ui.screens.HudScreen
import com.jarvis.assistant.ui.screens.HudState
import com.jarvis.assistant.ui.theme.JarvisBlack
import com.jarvis.assistant.ui.theme.JarvisTheme

class MainActivity : ComponentActivity() {

    /** Bumped on every resume so permission-dependent UI re-reads its state. */
    private val resumeTick = mutableIntStateOf(0)
    private var startListeningOnResume = false

    private val captureOpen = mutableStateOf(false)
    private val captureSeed = mutableStateOf("")
    private val captureTarget = mutableStateOf(CaptureTarget.LOGSEQ)

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { _ ->
        resumeTick.intValue += 1
        JarvisForegroundService.start(this)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        JarvisRuntime.initialize(this)

        requestRuntimePermissions()
        JarvisForegroundService.start(this)
        handleIntent(intent)

        setContent {
            JarvisTheme {
                val connection by JarvisRuntime.socket.state.collectAsStateWithLifecycle()
                val lastError by JarvisRuntime.socket.lastError.collectAsStateWithLifecycle()
                val serverAddress by JarvisRuntime.settings.serverAddress.collectAsStateWithLifecycle()
                val micActive by JarvisRuntime.micActive.collectAsStateWithLifecycle()
                val desktop by JarvisRuntime.desktopTelemetry.collectAsStateWithLifecycle()
                val approvals by JarvisRuntime.pendingApprovals.collectAsStateWithLifecycle()
                val statusText by JarvisRuntime.statusText.collectAsStateWithLifecycle()
                val blockingError by JarvisRuntime.blockingError.collectAsStateWithLifecycle()
                val hasSecret by JarvisRuntime.settings.hasSharedSecret.collectAsStateWithLifecycle()
                val hasToken by JarvisRuntime.settings.hasAuthToken.collectAsStateWithLifecycle()

                val tick = resumeTick.intValue
                var micGranted by remember { mutableStateOf(JarvisRuntime.hasMicPermission()) }
                var batteryExempt by remember {
                    mutableStateOf(JarvisRuntime.telemetry.isIgnoringBatteryOptimizations())
                }
                LaunchedEffect(tick) {
                    micGranted = JarvisRuntime.hasMicPermission()
                    batteryExempt = JarvisRuntime.telemetry.isIgnoringBatteryOptimizations()
                    if (startListeningOnResume && micGranted) {
                        startListeningOnResume = false
                        JarvisRuntime.startMic()
                    }
                }

                if (captureOpen.value) {
                    val queued by JarvisRuntime.pendingNotes.pendingCount
                        .collectAsStateWithLifecycle()
                    QuickCaptureSheet(
                        connected = connection == ConnectionState.CONNECTED,
                        initialText = captureSeed.value,
                        initialTarget = captureTarget.value,
                        micActive = micActive,
                        micPermissionGranted = micGranted,
                        queuedCount = queued,
                        onSend = { target, body ->
                            JarvisRuntime.sendQuickNote(target.wire, body)
                        },
                        onToggleMic = {
                            if (JarvisRuntime.hasMicPermission()) {
                                JarvisRuntime.toggleMic()
                            } else {
                                requestRuntimePermissions()
                            }
                        },
                        onDismiss = {
                            captureOpen.value = false
                            captureSeed.value = ""
                        },
                    )
                }

                // Remembered: HudActions is a parameter of every card on the screen,
                // and rebuilding it inside setContent handed each of them a new
                // identity on every recomposition, so nothing could skip. The
                // lambdas close over JarvisRuntime and this Activity, both of which
                // outlive the composition.
                val hudActions = remember {
                    HudActions(
                        onServerAddressChange = JarvisRuntime::updateServerAddress,
                        onReconnect = JarvisRuntime::reconnectNow,
                        onToggleMic = {
                            if (JarvisRuntime.hasMicPermission()) {
                                JarvisRuntime.toggleMic()
                            } else {
                                requestRuntimePermissions()
                            }
                        },
                        onApprove = { id -> JarvisRuntime.submitApprovalDecision(id, true) },
                        onReject = { id -> JarvisRuntime.submitApprovalDecision(id, false) },
                        onRequestBatteryExemption = ::requestBatteryExemption,
                        onSharedSecretChange = JarvisRuntime::updateSharedSecret,
                        onAuthTokenChange = JarvisRuntime::updateAuthToken,
                    )
                }

                HudScreen(
                    state = HudState(
                        connection = connection,
                        serverAddress = serverAddress,
                        micActive = micActive,
                        micPermissionGranted = micGranted,
                        desktop = desktop,
                        approvals = approvals,
                        statusText = statusText,
                        lastError = lastError,
                        batteryExempt = batteryExempt,
                        blockingError = blockingError,
                        hasSharedSecret = hasSecret,
                        hasAuthToken = hasToken,
                    ),
                    actions = hudActions,
                    modifier = Modifier
                        .fillMaxSize()
                        .background(JarvisBlack)
                        .windowInsetsPadding(WindowInsets.systemBars),
                )
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIntent(intent)
    }

    override fun onResume() {
        super.onResume()
        resumeTick.intValue += 1
        JarvisRuntime.connect()
    }

    /**
     * ASSIST arrives from the power-button long-press, which means the user wants
     * to talk immediately rather than look at the HUD.
     */
    private fun handleIntent(intent: Intent?) {
        if (intent?.action == ACTION_QUICK_CAPTURE) {
            captureTarget.value = when (intent.getStringExtra(EXTRA_CAPTURE_TARGET)) {
                CaptureTarget.JOPLIN.wire -> CaptureTarget.JOPLIN
                else -> CaptureTarget.LOGSEQ
            }
            captureOpen.value = true
            return
        }
        // Share sheet: seed capture with whatever was shared.
        if (intent?.action == Intent.ACTION_SEND && intent.type == "text/plain") {
            captureSeed.value = intent.getStringExtra(Intent.EXTRA_TEXT).orEmpty()
            captureOpen.value = true
            return
        }

        val wantsMic = intent?.action == Intent.ACTION_ASSIST ||
            intent?.action == ACTION_START_LISTENING ||
            intent?.action == ACTION_START_VOICE ||
            intent?.action == "android.intent.action.VOICE_COMMAND"
        if (!wantsMic) return

        if (JarvisRuntime.hasMicPermission()) {
            JarvisRuntime.startMic()
        } else {
            startListeningOnResume = true
            requestRuntimePermissions()
        }
    }

    private fun requestRuntimePermissions() {
        val wanted = buildList {
            add(Manifest.permission.RECORD_AUDIO)
            // No CAMERA. The only camera-adjacent feature is the torch, and
            // CameraManager.setTorchMode needs no permission — so this prompt bought
            // nothing and shared a batch with RECORD_AUDIO, where declining it cost
            // the user the microphone.
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
        permissionLauncher.launch(wanted.toTypedArray())
    }

    private fun requestBatteryExemption() {
        // The direct request dialog is the good path; some OEM builds block the
        // intent entirely, so fall back to the settings list.
        val direct = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
            .setData(Uri.parse("package:$packageName"))
        val fallback = Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)

        runCatching { startActivity(direct) }
            .recoverCatching { startActivity(fallback) }
    }

    companion object {
        const val ACTION_START_LISTENING = "com.jarvis.assistant.START_LISTENING"
        const val ACTION_QUICK_CAPTURE = "com.jarvis.assistant.QUICK_CAPTURE"
        const val ACTION_START_VOICE = "com.jarvis.assistant.START_VOICE"
        const val EXTRA_CAPTURE_TARGET = "capture_target"
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/audio/AudioPlayer.kt`

```kotlin
package com.jarvis.assistant.audio

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Low-latency playback of PCM streamed down from the desktop.
 *
 * Chunks land on a bounded channel and are drained by a single writer coroutine,
 * so a burst from the server cannot block the WebSocket reader thread.
 *
 * Playback does not begin on the first byte. [PREROLL_MS] of audio is written
 * into the track first, giving the stream a jitter buffer: over cellular, packet
 * arrival is bursty, and starting immediately means the track drains faster than
 * the network refills it and the speech breaks up. The cost is a fixed startup
 * delay, which is invisible next to network and synthesis latency.
 */
class AudioPlayer {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val playing = AtomicBoolean(false)

    private var track: AudioTrack? = null
    private var writer: Job? = null
    private var queue: Channel<ByteArray>? = null
    private var currentSampleRate = DEFAULT_SAMPLE_RATE

    /**
     * Identifies the stream currently being played. [finish] captures it and its
     * joiner only tears down if it is still current, so a reply that starts while
     * the previous one is still draining is not killed by the previous one's
     * teardown.
     */
    private var streamToken = 0

    val isPlaying: Boolean get() = playing.get()

    @Synchronized
    fun start(sampleRate: Int = DEFAULT_SAMPLE_RATE, channels: Int = 1) {
        // Always begins a new stream. The old early-return for a matching sample
        // rate meant that a reply arriving while the previous one was still draining
        // was dropped in full: start() did nothing, the still-open `queue` field
        // pointed at a closed channel, and every chunk of the new reply was logged
        // as "playback queue full". Cutting the tail of the previous reply short is
        // the lesser loss, and the desktop has already moved on by then anyway.
        stopInternal(flush = true)

        val channelCount = if (channels >= 2) 2 else 1
        val channelMask =
            if (channelCount == 2) AudioFormat.CHANNEL_OUT_STEREO else AudioFormat.CHANNEL_OUT_MONO
        val minBuffer = AudioTrack.getMinBufferSize(sampleRate, channelMask, ENCODING)
        if (minBuffer <= 0) {
            Log.e(TAG, "unsupported playback configuration ${sampleRate}Hz")
            return
        }

        val prerollBytes = sampleRate * channelCount * BYTES_PER_SAMPLE * PREROLL_MS / 1000
        // The track must hold the whole preroll plus headroom, otherwise the
        // writer blocks on a full buffer before playback has been allowed to start.
        val bufferSize = maxOf(minBuffer * 4, prerollBytes * 2)

        val newTrack = try {
            AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ASSISTANT)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build(),
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(ENCODING)
                        .setSampleRate(sampleRate)
                        .setChannelMask(channelMask)
                        .build(),
                )
                .setBufferSizeInBytes(bufferSize)
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build()
        } catch (e: Exception) {
            Log.e(TAG, "AudioTrack construction failed", e)
            return
        }

        if (newTrack.state != AudioTrack.STATE_INITIALIZED) {
            Log.e(TAG, "AudioTrack failed to initialise")
            newTrack.release()
            return
        }

        val channel = Channel<ByteArray>(capacity = QUEUE_CAPACITY)
        currentSampleRate = sampleRate
        track = newTrack
        queue = channel
        playing.set(true)
        streamToken += 1

        writer = scope.launch {
            var buffered = 0
            var started = false

            try {
                for (chunk in channel) {
                    if (!playing.get()) break
                    var offset = 0
                    while (offset < chunk.size && playing.get()) {
                        // Guarded: the caller can pause and flush this track from
                        // another thread to silence a barge-in immediately, and a
                        // write that lands after that must not escape the coroutine.
                        // Nothing here holds a CoroutineExceptionHandler, so an
                        // escaping throw would reach the default handler.
                        val written = runCatching {
                            newTrack.write(chunk, offset, chunk.size - offset)
                        }.getOrDefault(-1)
                        if (written <= 0) break
                        offset += written
                        buffered += written
                        if (!started && buffered >= prerollBytes) {
                            started = true
                            runCatching { newTrack.play() }
                        }
                    }
                }

                // A reply shorter than the preroll still has to be heard.
                if (!started && playing.get() && buffered > 0) {
                    runCatching { newTrack.play() }
                }
            } finally {
                // This coroutine owns the track for its whole life and is the only
                // thing that releases it. Releasing from the caller while a blocking
                // write was in flight was a use-after-release on a native object:
                // survivable on today's platform, because write() returns
                // ERROR_INVALID_OPERATION rather than throwing, but it is not a
                // property worth depending on.
                runCatching { newTrack.stop() }
                runCatching { newTrack.release() }
            }
        }
    }

    fun enqueue(pcm: ByteArray) {
        if (!playing.get()) start(currentSampleRate)
        val channel = queue ?: return
        if (channel.trySend(pcm).isFailure) {
            Log.w(TAG, "playback queue full, dropping ${pcm.size} bytes")
        }
    }

    /** Lets whatever is already buffered finish, then tears down. */
    @Synchronized
    fun finish() {
        queue?.close()
        // Stop accepting: a chunk arriving after the end event belongs to a stream
        // that is over, and resurrecting the closed channel here is what used to
        // swallow the following reply.
        queue = null
        val pending = writer
        val token = streamToken
        scope.launch {
            pending?.join()
            synchronized(this@AudioPlayer) {
                // Only tear down if no new stream has started in the meantime.
                if (token == streamToken && playing.get()) stopInternal(flush = false)
            }
        }
    }

    /** Barge-in: drop everything queued and silence the speaker immediately. */
    @Synchronized
    fun flushNow() {
        stopInternal(flush = true)
    }

    @Synchronized
    fun release() {
        stopInternal(flush = true)
    }

    private fun stopInternal(flush: Boolean) {
        playing.set(false)
        streamToken += 1
        queue?.close()
        queue = null
        writer?.cancel()
        writer = null
        // Pause and flush here so a barge-in silences the speaker now rather than
        // after the track's remaining buffer has drained. Both are safe to call
        // while the writer is mid-write; stop() and release() are not, so they stay
        // with the writer coroutine, which exits as soon as its write returns.
        track?.let { t ->
            runCatching {
                if (t.playState != AudioTrack.PLAYSTATE_STOPPED) t.pause()
                if (flush) t.flush()
            }
        }
        track = null
    }

    companion object {
        private const val TAG = "JarvisPlayer"
        const val DEFAULT_SAMPLE_RATE = 22_050
        private const val ENCODING = AudioFormat.ENCODING_PCM_16BIT
        private const val BYTES_PER_SAMPLE = 2
        private const val QUEUE_CAPACITY = 256

        /** Jitter budget before playback starts. */
        private const val PREROLL_MS = 120
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/audio/AudioStreamer.kt`

```kotlin
package com.jarvis.assistant.audio

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Microphone capture at 16 kHz / 16-bit / mono, pushed to the desktop as raw PCM.
 *
 * Uses VOICE_COMMUNICATION so the platform applies echo cancellation and noise
 * suppression — without it the handset's own speaker output feeds straight back
 * into the uplink during duplex playback.
 */
class AudioStreamer(
    private val context: Context,
    private val onChunk: (ByteArray, Int) -> Unit,
) {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val running = AtomicBoolean(false)
    private var job: Job? = null
    private var record: AudioRecord? = null

    val isRecording: Boolean get() = running.get()

    fun hasPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED

    /** @return true when capture actually started. */
    @SuppressLint("MissingPermission")
    fun start(): Boolean {
        if (running.get()) return true
        if (!hasPermission()) {
            Log.w(TAG, "RECORD_AUDIO not granted")
            return false
        }

        val minBuffer = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL, ENCODING)
        if (minBuffer <= 0) {
            Log.e(TAG, "unsupported capture configuration")
            return false
        }
        val bufferSize = maxOf(minBuffer * 2, CHUNK_BYTES * 2)

        val recorder = try {
            AudioRecord(
                MediaRecorder.AudioSource.VOICE_COMMUNICATION,
                SAMPLE_RATE,
                CHANNEL,
                ENCODING,
                bufferSize,
            )
        } catch (e: Exception) {
            Log.e(TAG, "AudioRecord construction failed", e)
            return false
        }

        if (recorder.state != AudioRecord.STATE_INITIALIZED) {
            Log.e(TAG, "AudioRecord failed to initialise")
            recorder.release()
            return false
        }

        // Inside the try, and before `running` is set: startRecording throws when
        // the microphone is held exclusively elsewhere (an in-progress call, a
        // concurrent-capture denial). Outside it, that throw propagated out of a
        // Compose click handler or a binder callback and left the native mic handle
        // open with isRecording still reporting true.
        try {
            recorder.startRecording()
        } catch (e: Exception) {
            Log.e(TAG, "startRecording rejected", e)
            runCatching { recorder.release() }
            return false
        }
        if (recorder.recordingState != AudioRecord.RECORDSTATE_RECORDING) {
            Log.e(TAG, "AudioRecord did not enter the recording state")
            runCatching { recorder.release() }
            return false
        }

        record = recorder
        running.set(true)

        job = scope.launch {
            val buffer = ByteArray(CHUNK_BYTES)
            try {
                while (running.get()) {
                    // Guarded for the same reason as the playback write: stop() can
                    // land while this is blocked in the native call, and nothing in
                    // this scope would catch an escaping throw.
                    val read = runCatching { recorder.read(buffer, 0, buffer.size) }
                        .getOrDefault(-1)
                    if (read > 0) {
                        onChunk(buffer, read)
                    } else if (read < 0) {
                        Log.e(TAG, "AudioRecord.read error $read")
                        break
                    }
                }
            } finally {
                // This coroutine owns the recorder and is the only thing that
                // releases it, so a release can never land under an in-flight read.
                runCatching { recorder.release() }
            }
        }
        return true
    }

    fun stop() {
        if (!running.compareAndSet(true, false)) return
        // stop() is safe to call while the reader is blocked in read() and is what
        // unblocks it; release() is left to the reader's own finally.
        record?.let { recorder ->
            runCatching {
                if (recorder.recordingState == AudioRecord.RECORDSTATE_RECORDING) recorder.stop()
            }
        }
        job?.cancel()
        job = null
        record = null
    }

    companion object {
        private const val TAG = "JarvisMic"
        const val SAMPLE_RATE = 16_000
        private const val CHANNEL = AudioFormat.CHANNEL_IN_MONO
        private const val ENCODING = AudioFormat.ENCODING_PCM_16BIT

        /** 20 ms of audio: small enough that barge-in feels instant. */
        private const val CHUNK_BYTES = SAMPLE_RATE / 50 * 2
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/data/JarvisSettings.kt`

```kotlin
package com.jarvis.assistant.data

import android.content.Context
import android.content.SharedPreferences
import androidx.core.content.edit
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.net.URI
import java.util.UUID

/**
 * Single-user configuration: which desktop to talk to and the shared secret used
 * to sign approval decisions. Backed by plain SharedPreferences — the secret is
 * only meaningful to the paired desktop and never leaves the Tailnet.
 */
class JarvisSettings(context: Context) {

    private val prefs: SharedPreferences =
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private val _serverAddress = MutableStateFlow(
        prefs.getString(KEY_SERVER, DEFAULT_SERVER) ?: DEFAULT_SERVER,
    )
    val serverAddress: StateFlow<String> = _serverAddress.asStateFlow()

    private val _handsFree = MutableStateFlow(prefs.getBoolean(KEY_HANDS_FREE, false))
    val handsFree: StateFlow<Boolean> = _handsFree.asStateFlow()

    private val deviceIdLock = Any()

    /**
     * Stable per-install identifier the desktop pairs against.
     *
     * Minted under a lock and committed synchronously. A plain get-or-create races
     * on first run: the connect coroutine and an approval tap can both find nothing
     * stored and mint different UUIDs, and a decision then carries a `device_id`
     * that does not match the one in `hello` — the desktop rejects the HMAC and the
     * cause is invisible from the phone.
     */
    val deviceId: String
        get() = synchronized(deviceIdLock) {
            prefs.getString(KEY_DEVICE_ID, null) ?: UUID.randomUUID().toString().also {
                prefs.edit(commit = true) { putString(KEY_DEVICE_ID, it) }
            }
        }

    private val _hasSecret = MutableStateFlow(!prefs.getString(KEY_SECRET, "").isNullOrEmpty())

    /** Whether a signing key exists, without exposing the key itself to the UI. */
    val hasSharedSecret: StateFlow<Boolean> = _hasSecret.asStateFlow()

    var sharedSecret: String
        get() = prefs.getString(KEY_SECRET, "") ?: ""
        set(value) {
            prefs.edit { putString(KEY_SECRET, value) }
            _hasSecret.value = value.isNotEmpty()
        }

    private val _hasAuthToken = MutableStateFlow(!prefs.getString(KEY_TOKEN, "").isNullOrEmpty())
    val hasAuthToken: StateFlow<Boolean> = _hasAuthToken.asStateFlow()

    /** Sent as `Authorization: Bearer` on the upgrade request, before the socket opens. */
    var authToken: String
        get() = prefs.getString(KEY_TOKEN, "") ?: ""
        set(value) {
            prefs.edit { putString(KEY_TOKEN, value) }
            _hasAuthToken.value = value.isNotEmpty()
        }

    fun setServerAddress(value: String) {
        val trimmed = value.trim()
        prefs.edit { putString(KEY_SERVER, trimmed) }
        _serverAddress.value = trimmed
    }

    fun setHandsFree(value: Boolean) {
        prefs.edit { putBoolean(KEY_HANDS_FREE, value) }
        _handsFree.value = value
    }

    /**
     * Accepts a bare host, `host:port`, or a full ws/wss/http/https URL and
     * normalises it to the WebSocket endpoint the desktop server exposes.
     */
    fun resolveWebSocketUrl(): String = normalizeToWebSocketUrl(_serverAddress.value)

    companion object {
        private const val PREFS = "jarvis_settings"
        private const val KEY_SERVER = "server_address"
        private const val KEY_SECRET = "shared_secret"
        private const val KEY_TOKEN = "auth_token"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_HANDS_FREE = "hands_free"

        /** Tailscale CGNAT range; replace with your own desktop's Tailscale IP. */
        const val DEFAULT_SERVER = "100.64.0.1:4719"
        const val WS_PATH = "/api/mobile/ws"

        /**
         * Whether an unencrypted `ws://` target is somewhere the traffic cannot
         * leave the private network.
         *
         * Android's network security config cannot express this: its domain rules
         * take hostnames and IP literals, not CIDR ranges, so a 100.64.0.0/10 rule
         * is not writable there and the check has to live in code.
         */
        fun isCleartextTargetPrivate(url: String): Boolean {
            if (!url.startsWith("ws://", ignoreCase = true)) return true
            val host = hostOf(url)?.lowercase() ?: return false

            if (host == "localhost" || host == "::1" || host.startsWith("127.")) return true
            if (host.endsWith(".ts.net") || host.endsWith(".local")) return true

            val octets = host.split('.')
            if (octets.size != 4) return false
            val parts = octets.map { it.toIntOrNull() ?: return false }
            if (parts.any { it !in 0..255 }) return false

            return when {
                // Tailscale CGNAT range.
                parts[0] == 100 && parts[1] in 64..127 -> true
                parts[0] == 10 -> true
                parts[0] == 192 && parts[1] == 168 -> true
                parts[0] == 172 && parts[1] in 16..31 -> true
                else -> false
            }
        }

        /**
         * The host of [url], or null when it cannot be determined unambiguously.
         *
         * Parsed with [URI] rather than by hand. Splitting the authority on ':'
         * looks equivalent and is not: it reads the userinfo of
         * `ws://100.64.0.1:8080@evil.com/` as the host, so a public target passes
         * [isCleartextTargetPrivate] while OkHttp — which parses correctly — dials
         * evil.com in the clear carrying the bearer token, every approval and the
         * microphone uplink.
         *
         * Anything [URI] cannot resolve to a server-based host returns null, which
         * every caller treats as "refuse".
         */
        fun hostOf(url: String): String? {
            val host = runCatching { URI(url).host }.getOrNull() ?: return null
            return host.trim('[', ']').takeUnless { it.isEmpty() }
        }

        fun normalizeToWebSocketUrl(raw: String): String {
            val input = raw.trim().ifEmpty { DEFAULT_SERVER }
            val withScheme = when {
                input.startsWith("ws://") || input.startsWith("wss://") -> input
                input.startsWith("http://") -> "ws://" + input.removePrefix("http://")
                input.startsWith("https://") -> "wss://" + input.removePrefix("https://")
                else -> "ws://$input"
            }
            val schemeEnd = withScheme.indexOf("://") + 3
            val hasPath = withScheme.indexOf('/', schemeEnd) >= 0
            return if (hasPath) withScheme else withScheme.trimEnd('/') + WS_PATH
        }
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/data/PendingDecisionStore.kt`

```kotlin
package com.jarvis.assistant.data

import android.content.Context
import androidx.core.content.edit
import com.jarvis.assistant.network.ApprovalDecisionMessage
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json

/**
 * Signed approval decisions that have not reached the desktop yet.
 *
 * This exists for one sequence: the process is not running, the user taps Approve
 * on the lock screen, the receiver initialises the runtime and submits — but the
 * dial is asynchronous, so the send fails, and once `onReceive` returns the
 * receiver's importance boost lapses and the process can be reaped before the
 * handshake completes. An in-memory queue loses the decision there with no trace,
 * which is the worst possible failure for the one interaction the whole app exists
 * to serve: the user believes they approved something and the desktop is still
 * waiting.
 *
 * A decision is already signed when it lands here, and the signature covers the
 * nonce and `decided_at_ms`, so replaying it later cannot change what was agreed
 * to — and the desktop's replay cache means sending it twice is harmless.
 *
 * Rows are written with `commit` rather than `apply`: `apply` is asynchronous and
 * the whole point of this class is the case where the process does not survive
 * long enough for an asynchronous write to land.
 */
class PendingDecisionStore(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    private val serializer = ListSerializer(ApprovalDecisionMessage.serializer())

    private var pending: List<ApprovalDecisionMessage> = load()

    @Synchronized
    fun add(decision: ApprovalDecisionMessage) {
        // Keyed on id: a second decision for the same request supersedes the first
        // rather than queueing both, so a double tap cannot send approve and deny.
        val next = (pending.filterNot { it.id == decision.id } + decision).takeLast(CAPACITY)
        persist(next)
    }

    @Synchronized
    fun snapshot(): List<ApprovalDecisionMessage> = pending

    @Synchronized
    fun remove(decision: ApprovalDecisionMessage) {
        persist(pending.filterNot { it.id == decision.id && it.nonce == decision.nonce })
    }

    @Synchronized
    fun contains(requestId: String): Boolean = pending.any { it.id == requestId }

    private fun persist(decisions: List<ApprovalDecisionMessage>) {
        pending = decisions
        prefs.edit(commit = true) {
            putString(KEY_QUEUE, json.encodeToString(serializer, decisions))
        }
    }

    private fun load(): List<ApprovalDecisionMessage> {
        val raw = prefs.getString(KEY_QUEUE, null) ?: return emptyList()
        return runCatching { json.decodeFromString(serializer, raw) }.getOrDefault(emptyList())
    }

    companion object {
        private const val PREFS = "jarvis_pending_decisions"
        private const val KEY_QUEUE = "queue"

        /** Far more than a human can generate; a bound only so nothing grows forever. */
        const val CAPACITY = 50
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/data/PendingNoteStore.kt`

```kotlin
package com.jarvis.assistant.data

import android.content.Context
import androidx.core.content.edit
import com.jarvis.assistant.network.QuickNoteMessage
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json

/**
 * Notes captured while the socket was down, replayed on reconnect.
 *
 * Backed by SharedPreferences rather than Room or DataStore: the payload is a
 * handful of short strings, and the app already keeps its settings here. Room
 * would add KSP codegen and a schema directory to the build for a queue that is
 * almost always empty and never exceeds [CAPACITY] rows.
 *
 * The in-memory outbox in JarvisRuntime is not enough on its own — it dies with
 * the process, and a note captured from the Quick Settings tile with no desktop
 * reachable is exactly the case where the process is short-lived.
 */
class PendingNoteStore(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    private val serializer = ListSerializer(QuickNoteMessage.serializer())

    private val _pending = MutableStateFlow(load())

    private val _pendingCount = MutableStateFlow(_pending.value.size)

    /** Count only: the HUD shows a backlog badge, not the note contents. */
    val pendingCount: StateFlow<Int> = _pendingCount.asStateFlow()

    @Synchronized
    fun add(note: QuickNoteMessage) {
        // Drop the oldest rather than the newest: a note the user just wrote is
        // the one they still remember and would notice losing.
        val next = (_pending.value + note).takeLast(CAPACITY)
        persist(next)
    }

    @Synchronized
    fun snapshot(): List<QuickNoteMessage> = _pending.value

    @Synchronized
    fun remove(note: QuickNoteMessage) {
        val next = _pending.value.toMutableList()
        next.remove(note)
        persist(next)
    }

    @Synchronized
    fun clear() = persist(emptyList())

    private fun persist(notes: List<QuickNoteMessage>) {
        _pending.value = notes
        _pendingCount.value = notes.size
        prefs.edit { putString(KEY_QUEUE, json.encodeToString(serializer, notes)) }
    }

    private fun load(): List<QuickNoteMessage> {
        val raw = prefs.getString(KEY_QUEUE, null) ?: return emptyList()
        return runCatching { json.decodeFromString(serializer, raw) }.getOrDefault(emptyList())
    }

    companion object {
        private const val PREFS = "jarvis_pending_notes"
        private const val KEY_QUEUE = "queue"
        const val CAPACITY = 200
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/data/repository/WidgetDataRepository.kt`

```kotlin
package com.jarvis.assistant.data.repository

import android.content.Context
import androidx.glance.appwidget.updateAll
import com.jarvis.assistant.JarvisRuntime
import com.jarvis.assistant.network.ApprovalRequestEvent
import com.jarvis.assistant.network.ConnectionState
import com.jarvis.assistant.widget.approval.ApprovalWidget
import com.jarvis.assistant.widget.launcher.QuickLauncherWidget
import com.jarvis.assistant.widget.telemetry.TelemetryWidget
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch

/**
 * Bridges live app state onto the home screen.
 *
 * Deliberately holds no state of its own. An earlier design kept its own
 * approval list and telemetry snapshot, which is a second source of truth that
 * drifts from [JarvisRuntime] the moment an approval resolves anywhere else —
 * from the lock-screen notification, say. This reads the runtime's flows and
 * pushes a redraw when they change, so widgets cannot disagree with the app.
 *
 * Nothing polls. Redraws happen only when an event actually moves the state.
 */
object WidgetDataRepository {

    data class ApprovalItem(
        val id: String,
        val action: String,
        val tier: String,
        val detail: String,
        val target: String? = null,
    )

    data class TelemetrySnapshot(
        val gpuTempC: Int? = null,
        val gpuPercent: Int? = null,
        val vramUsedMb: Int? = null,
        val vramTotalMb: Int? = null,
        val cpuPercent: Int? = null,
        val routeLane: String? = null,
        val model: String? = null,
        val isOnline: Boolean = false,
    ) {
        val hasData: Boolean
            get() = gpuTempC != null || cpuPercent != null || vramUsedMb != null
    }

    data class LinkStatus(val online: Boolean, val latencyMs: Long?)

    /** GPU designs throttle around here, so it is the point worth flagging. */
    const val GPU_WARN_C = 75

    const val CPU_WARN_PERCENT = 85

    /**
     * VRAM pressure is a fraction of the card, not an absolute. A fixed 7.2 GB
     * mark would sit at 90% of an 8 GB card and 30% of a 24 GB one, warning
     * constantly on the larger card while it is barely loaded.
     */
    const val VRAM_WARN_FRACTION = 0.90

    fun getPendingApprovals(): List<ApprovalItem> {
        if (!JarvisRuntime.isInitialized) return emptyList()
        return JarvisRuntime.pendingApprovals.value.map(::toItem)
    }

    fun getTelemetry(): TelemetrySnapshot {
        if (!JarvisRuntime.isInitialized) return TelemetrySnapshot()
        val desktop = JarvisRuntime.desktopTelemetry.value
        val online = JarvisRuntime.socket.state.value == ConnectionState.CONNECTED
        return TelemetrySnapshot(
            gpuTempC = desktop?.gpuTempC?.toInt(),
            gpuPercent = desktop?.gpuPercent?.toInt(),
            vramUsedMb = desktop?.vramUsedMb?.toInt(),
            vramTotalMb = desktop?.vramTotalMb?.toInt(),
            cpuPercent = desktop?.cpuPercent?.toInt(),
            routeLane = desktop?.routeLane,
            model = desktop?.model,
            isOnline = online,
        )
    }

    fun getConnectionStatus(): LinkStatus {
        if (!JarvisRuntime.isInitialized) return LinkStatus(online = false, latencyMs = null)
        val online = JarvisRuntime.socket.state.value == ConnectionState.CONNECTED
        return LinkStatus(online, JarvisRuntime.latencyMs.value.takeIf { online })
    }

    /** True when signing is impossible, so the widget can say so instead of failing silently. */
    fun isUnpaired(): Boolean =
        JarvisRuntime.isInitialized && JarvisRuntime.settings.sharedSecret.isEmpty()

    /**
     * Whether a decision tapped on the home screen could actually be delivered.
     *
     * The runtime refuses to sign one when the link is down, so offering the buttons
     * anyway means a tap that buzzes and does nothing. The widget says "offline"
     * instead.
     */
    fun canDecideNow(): Boolean =
        JarvisRuntime.isInitialized &&
            JarvisRuntime.socket.state.value == ConnectionState.CONNECTED &&
            !isUnpaired()

    private fun toItem(event: ApprovalRequestEvent) = ApprovalItem(
        id = event.id,
        action = event.title,
        tier = event.tier,
        detail = event.summary.ifBlank {
            event.note?.markdown ?: event.note?.after ?: event.detail.orEmpty()
        },
        target = event.note?.let { if (it.isJoplin) "JOPLIN" else "LOGSEQ" },
    )

    /**
     * Starts pushing redraws. Called once from the runtime; each widget family
     * is woken only by the state it actually renders.
     */
    fun observe(context: Context, scope: CoroutineScope) {
        val app = context.applicationContext

        scope.launch {
            // Distinct on the rendered content, not on the ids. The runtime replaces
            // an approval that reuses an id, so an id-only comparison reported "no
            // change" for a revised request and the widget kept offering Approve and
            // Deny against text the user was no longer looking at.
            JarvisRuntime.pendingApprovals
                .map { list -> list.map { ApprovalFingerprint(it) } }
                .distinctUntilChanged()
                .collect { ApprovalWidget().updateAll(app) }
        }

        scope.launch {
            // No distinctUntilChanged: a StateFlow already conflates equal values,
            // and kotlinx deprecates the operator on StateFlow at ERROR level.
            JarvisRuntime.desktopTelemetry
                .collect { TelemetryWidget().updateAll(app) }
        }

        scope.launch {
            // Connection state only. Folding latency in here meant every pong
            // redrew both widgets, and with the launcher widget probing on redraw
            // that closed a loop that never settled.
            JarvisRuntime.socket.state
                .collect {
                    QuickLauncherWidget().updateAll(app)
                    // Connectivity gates the telemetry card's live/stale styling.
                    TelemetryWidget().updateAll(app)
                }
        }
    }

    /**
     * What the approval widget actually renders, so equality means "nothing on the
     * widget would look different" rather than "the same request ids are pending".
     */
    private data class ApprovalFingerprint(
        val id: String,
        val title: String,
        val summary: String,
        val tier: String,
        val action: String?,
        val expiresAtMs: Long?,
    ) {
        constructor(event: ApprovalRequestEvent) : this(
            id = event.id,
            title = event.title,
            summary = event.summary,
            tier = event.tier,
            action = event.action,
            expiresAtMs = event.expiresAtMs,
        )
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/network/JarvisWebSocketManager.kt`

```kotlin
package com.jarvis.assistant.network

import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.min

enum class ConnectionState { OFFLINE, RECONNECTING, CONNECTED }

/**
 * One frame off the wire, in arrival order.
 *
 * Text and binary share a single stream deliberately. Carrying them on two flows
 * loses the ordering between them, and that ordering is load-bearing: the tail of
 * a reply is binary PCM followed by a text `audio_stream_end`, so an independently
 * collected end event clears the stream tag while frames are still queued and the
 * last of every reply is discarded. The head has the mirror problem.
 */
sealed interface SocketSignal {
    class Event(val event: InboundEvent) : SocketSignal
    class Binary(val frame: ByteArray) : SocketSignal
}

/**
 * Persistent link to the desktop server.
 *
 * Reconnects with exponential backoff (1s, 2s, 4s … capped at 30s) and pings on
 * a 25-second interval to keep the Tailscale path warm while the handset dozes.
 * Without traffic the NAT mapping is reclaimed and inbound approval requests
 * stall until the next radio wake; carrier CGNAT gateways commonly reap idle
 * mappings at 30 seconds, so the interval has to sit comfortably under that.
 *
 * The whole dial/backoff/teardown state machine runs under [lock]. It is touched
 * from the main thread, from OkHttp's reader thread and from binder threads, and
 * every field in it is a read-modify-write.
 */
class JarvisWebSocketManager private constructor() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val lock = Any()

    private val client: OkHttpClient = OkHttpClient.Builder()
        .pingInterval(PING_SECONDS, TimeUnit.SECONDS)
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .writeTimeout(15, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build()

    private val _state = MutableStateFlow(ConnectionState.OFFLINE)
    val state: StateFlow<ConnectionState> = _state.asStateFlow()

    private val _lastError = MutableStateFlow<String?>(null)
    val lastError: StateFlow<String?> = _lastError.asStateFlow()

    /**
     * Bounded, and the producer blocks rather than discarding when it fills.
     *
     * The previous buffer dropped on overflow with a log line, which meant a burst
     * of base64 audio chunks could push an `approval_request` out of the buffer: the
     * user never saw the prompt and the desktop waited on a gate nobody could answer.
     * Blocking the reader thread instead closes the TCP window and makes the desktop
     * slow down, which is the correct place for the pressure to land.
     */
    private val signals = Channel<SocketSignal>(capacity = SIGNAL_BUFFER)
    val incoming: Flow<SocketSignal> = signals.receiveAsFlow()

    @Volatile private var socket: WebSocket? = null
    @Volatile private var url: String? = null
    @Volatile private var authToken: String? = null
    @Volatile private var shutdown = true
    private var attempt = 0
    private var reconnectJob: Job? = null

    /**
     * Monotonic dial counter. Every [Listener] remembers the generation it was
     * created for and ignores its own callbacks once superseded, so cancelling a
     * socket to re-dial elsewhere cannot trigger a reconnect back to the old URL.
     *
     * Bumped by every path that invalidates the current socket — including
     * [openSocket] and [disconnect], both of which used to leave it alone. Leaving
     * it alone let a late `onFailure` from the previous generation schedule a second
     * dial at the *current* generation, so two sockets were live and both listeners
     * believed they were current: duplicated approvals and doubled audio.
     */
    private val generation = AtomicInteger(0)

    /** Idempotent: re-dials only when the target URL or token actually changed. */
    fun connect(wsUrl: String, token: String? = null) {
        synchronized(lock) {
            val normalizedToken = token?.takeIf { it.isNotBlank() }
            val sameTarget = url == wsUrl && authToken == normalizedToken
            // A reconnect already armed for this same target is progress, not a reason
            // to start over. Re-dialling here reset `attempt` on every caller, so the
            // backoff never grew past its first step for as long as anything polled
            // connect() — which onResume and every queued send do.
            if (!shutdown && sameTarget && (socket != null || reconnectJob?.isActive == true)) return
            url = wsUrl
            authToken = normalizedToken
            shutdown = false
            attempt = 0
            redial()
        }
    }

    fun disconnect() {
        synchronized(lock) {
            shutdown = true
            generation.incrementAndGet()
            reconnectJob?.cancel()
            reconnectJob = null
            socket?.cancel()
            socket = null
            _state.value = ConnectionState.OFFLINE
        }
    }

    /** Forces a fresh dial, e.g. after the user edits the server address. */
    fun reconnectNow() {
        synchronized(lock) {
            if (url == null) return
            shutdown = false
            attempt = 0
            redial()
        }
    }

    private fun redial() {
        reconnectJob?.cancel()
        reconnectJob = null
        openSocket()
    }

    fun send(message: OutboundMessage): Boolean {
        val ws = socket ?: return false
        return try {
            ws.send(JarvisJson.encodeToString(OutboundMessage.serializer(), message))
        } catch (e: Exception) {
            Log.w(TAG, "send failed", e)
            false
        }
    }

    /** Raw microphone PCM. Bracketed by audio_input_start / audio_input_end. */
    fun sendAudio(pcm: ByteArray, length: Int = pcm.size): Boolean {
        val ws = socket ?: return false
        return try {
            ws.send(pcm.toByteString(0, length))
        } catch (e: Exception) {
            Log.w(TAG, "audio send failed", e)
            false
        }
    }

    /** Caller must hold [lock]. */
    private fun openSocket() {
        val target = url ?: return
        if (shutdown) return
        val gen = generation.incrementAndGet()
        val stale = socket
        socket = null
        stale?.cancel()

        _state.value = ConnectionState.RECONNECTING
        val request = Request.Builder()
            .url(target)
            .apply { authToken?.let { header("Authorization", "Bearer $it") } }
            .build()
        val ws = client.newWebSocket(request, Listener(gen))
        // Re-check under the same lock: disconnect() may have bumped the generation
        // while newWebSocket was dialling, and an orphan socket here is exactly how
        // the plaintext refusal used to end up with a live link behind it.
        if (gen == generation.get() && !shutdown) socket = ws else ws.cancel()
    }

    private fun scheduleReconnect() {
        synchronized(lock) {
            if (shutdown) return
            if (reconnectJob?.isActive == true) return
            val backoff = min(BASE_BACKOFF_MS shl min(attempt, 5), MAX_BACKOFF_MS)
            attempt += 1
            _state.value = ConnectionState.RECONNECTING
            reconnectJob = scope.launch {
                delay(backoff)
                synchronized(lock) { if (!shutdown) openSocket() }
            }
        }
    }

    /**
     * Hands a frame to the consumer, blocking this reader thread if the consumer is
     * behind. Dropping is not an option here — see [signals].
     */
    private fun dispatch(signal: SocketSignal) {
        if (signals.trySend(signal).isSuccess) return
        runBlocking { signals.send(signal) }
    }

    private inner class Listener(private val gen: Int) : WebSocketListener() {

        private val current: Boolean get() = gen == generation.get()

        override fun onOpen(webSocket: WebSocket, response: Response) {
            if (!current) {
                webSocket.cancel()
                return
            }
            synchronized(lock) {
                if (gen != generation.get()) {
                    webSocket.cancel()
                    return
                }
                socket = webSocket
                attempt = 0
                _lastError.value = null
                _state.value = ConnectionState.CONNECTED
            }
            Log.i(TAG, "connected to ${webSocket.request().url}")
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            if (!current) return
            val event = try {
                JarvisJson.decodeFromString(InboundEvent.serializer(), text)
            } catch (e: Exception) {
                // An unrecognised `type` is not fatal; the desktop may be newer.
                Log.w(TAG, "dropping unparseable frame: ${e.message}")
                return
            }
            dispatch(SocketSignal.Event(event))
        }

        override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
            if (!current) return
            if (bytes.size < 2) return
            dispatch(SocketSignal.Binary(bytes.toByteArray()))
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            webSocket.close(NORMAL_CLOSURE, null)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            if (!current) return
            synchronized(lock) { if (socket === webSocket) socket = null }
            if (shutdown) _state.value = ConnectionState.OFFLINE else scheduleReconnect()
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            if (!current) return
            synchronized(lock) { if (socket === webSocket) socket = null }
            _lastError.value = t.message ?: t::class.java.simpleName
            Log.w(TAG, "socket failure: ${_lastError.value}")
            if (shutdown) _state.value = ConnectionState.OFFLINE else scheduleReconnect()
        }
    }

    companion object {
        private const val TAG = "JarvisWS"
        private const val PING_SECONDS = 25L
        private const val BASE_BACKOFF_MS = 1_000L
        private const val MAX_BACKOFF_MS = 30_000L
        private const val NORMAL_CLOSURE = 1000

        /** ~5s of 20ms audio frames, so an ordinary reply never touches the producer. */
        private const val SIGNAL_BUFFER = 256

        @Volatile private var instance: JarvisWebSocketManager? = null

        fun get(): JarvisWebSocketManager =
            instance ?: synchronized(this) {
                instance ?: JarvisWebSocketManager().also { instance = it }
            }
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/network/WebSocketEvents.kt`

```kotlin
package com.jarvis.assistant.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject

/**
 * Wire protocol between the phone and the self-hosted desktop server.
 *
 * Control traffic is JSON text frames discriminated by a `type` field. Audio in
 * both directions is raw binary: uplink frames are bracketed by
 * [AudioInputStartMessage] / [AudioInputEndMessage], downlink frames carry a
 * one-byte stream tag matching the [AudioStreamStartEvent] that opened them.
 */
val JarvisJson: Json = Json {
    classDiscriminator = "type"
    ignoreUnknownKeys = true
    encodeDefaults = true
    explicitNulls = false
}

// ---------------------------------------------------------------- inbound ----

@Serializable
sealed interface InboundEvent

/**
 * A proposed edit to a Joplin note or a Logseq page.
 *
 * The desktop may send whichever it has: [markdown] alone for a new note,
 * [before] and [after] for a rewrite, or a pre-computed unified [diff]. When both
 * before/after and a diff arrive, the diff wins — the desktop's own diff is
 * authoritative over one reconstructed here.
 */
@Serializable
data class NoteEditPayload(
    /** `joplin` or `logseq`. */
    val target: String,
    val title: String? = null,
    /** Notebook, folder or journal page the edit lands in. */
    val location: String? = null,
    /** Full proposed content, for a create or a whole-body replace. */
    val markdown: String? = null,
    val before: String? = null,
    val after: String? = null,
    /** Unified diff, if the desktop computed one. */
    val diff: String? = null,
) {
    val isJoplin: Boolean get() = target.equals("joplin", ignoreCase = true)
}

/** An `ask` tier action on the desktop is gated until the phone answers. */
@Serializable
@SerialName("approval_request")
data class ApprovalRequestEvent(
    val id: String,
    val title: String = "Approval required",
    val summary: String = "",
    val tier: String = "ask",
    val detail: String? = null,
    /** e.g. `edit_joplin_note`, `edit_logseq_page`, `shell`, `send_email`. */
    val action: String? = null,
    val note: NoteEditPayload? = null,
    @SerialName("expires_at_ms") val expiresAtMs: Long? = null,
) : InboundEvent {

    val isNoteEdit: Boolean
        get() = note != null || (action != null && action in NOTE_ACTIONS)

    companion object {
        val NOTE_ACTIONS = setOf("edit_joplin_note", "edit_logseq_page")
    }
}

/** The gate was resolved elsewhere (timeout, desktop UI); drop the notification. */
@Serializable
@SerialName("approval_resolved")
data class ApprovalResolvedEvent(
    val id: String,
    val approved: Boolean = false,
) : InboundEvent

@Serializable
@SerialName("audio_stream_start")
data class AudioStreamStartEvent(
    @SerialName("stream_id") val streamId: String,
    @SerialName("sample_rate") val sampleRate: Int = 22_050,
    val channels: Int = 1,
    /** `pcm16` (raw little-endian) or `wav` (RIFF header on the first chunk). */
    val encoding: String = "pcm16",
    /**
     * First byte of every binary frame belonging to this stream (0-255). Omit to
     * fall back to base64 [AudioChunkEvent] frames, which cost a 33% payload
     * inflation plus a JSON parse per 20ms of speech.
     */
    @SerialName("binary_tag") val binaryTag: Int? = null,
) : InboundEvent

@Serializable
@SerialName("audio_chunk")
data class AudioChunkEvent(
    @SerialName("stream_id") val streamId: String,
    /** Base64 payload. */
    val data: String,
    val seq: Long = 0,
) : InboundEvent

@Serializable
@SerialName("audio_stream_end")
data class AudioStreamEndEvent(
    @SerialName("stream_id") val streamId: String,
) : InboundEvent

/** Hardware action requested by the desktop, e.g. `torch_on`, `set_volume`. */
@Serializable
@SerialName("device_command")
data class DeviceCommandEvent(
    val id: String,
    val action: String,
    val params: JsonObject = JsonObject(emptyMap()),
) : InboundEvent

/** The desktop is asking for a fresh phone telemetry snapshot. */
@Serializable
@SerialName("telemetry_request")
data class TelemetryRequestEvent(
    val id: String,
) : InboundEvent

/** Desktop-side vitals rendered on the HUD. */
@Serializable
@SerialName("desktop_telemetry")
data class DesktopTelemetryEvent(
    @SerialName("cpu_percent") val cpuPercent: Double? = null,
    @SerialName("gpu_temp_c") val gpuTempC: Double? = null,
    @SerialName("gpu_percent") val gpuPercent: Double? = null,
    @SerialName("vram_used_mb") val vramUsedMb: Double? = null,
    @SerialName("vram_total_mb") val vramTotalMb: Double? = null,
    @SerialName("ram_percent") val ramPercent: Double? = null,
    /** `local` or `cloud`. */
    @SerialName("route_lane") val routeLane: String? = null,
    /** Model actually serving, e.g. `qwen3:8b` or `jarvis-escalate`. */
    val model: String? = null,
) : InboundEvent {
    val isCloudRoute: Boolean get() = routeLane.equals("cloud", ignoreCase = true)
}

/**
 * Round-trip probe.
 *
 * OkHttp's protocol-level ping keeps the NAT mapping warm but never exposes its
 * timing, so measuring the link needs a frame the app can see both ends of.
 * Sent on connect and on widget refresh rather than on a timer — a background
 * heartbeat purely to decorate a widget is not worth the radio wake.
 */
@Serializable
@SerialName("pong")
data class PongEvent(
    @SerialName("sent_at_ms") val sentAtMs: Long,
) : InboundEvent

/** Free-form transcript / status line for the HUD. */
@Serializable
@SerialName("status")
data class StatusEvent(
    val text: String,
) : InboundEvent

// --------------------------------------------------------------- outbound ----

@Serializable
sealed interface OutboundMessage

@Serializable
@SerialName("hello")
data class HelloMessage(
    @SerialName("device_id") val deviceId: String,
    val platform: String = "android",
    @SerialName("app_version") val appVersion: String,
    @SerialName("protocol_version") val protocolVersion: Int = 1,
) : OutboundMessage

/**
 * HMAC-signed so the desktop can prove the tap came from this paired handset.
 *
 * The [nonce] is inside the signed payload: a timestamp window alone still lets
 * an identical decision be replayed until the window closes, so the desktop must
 * reject a nonce it has already seen.
 */
@Serializable
@SerialName("approval_decision")
data class ApprovalDecisionMessage(
    val id: String,
    val approved: Boolean,
    @SerialName("device_id") val deviceId: String,
    @SerialName("decided_at_ms") val decidedAtMs: Long,
    val nonce: String,
    val signature: String,
) : OutboundMessage

@Serializable
@SerialName("audio_input_start")
data class AudioInputStartMessage(
    @SerialName("stream_id") val streamId: String,
    @SerialName("sample_rate") val sampleRate: Int,
    val channels: Int = 1,
    val encoding: String = "pcm16",
) : OutboundMessage

@Serializable
@SerialName("audio_input_end")
data class AudioInputEndMessage(
    @SerialName("stream_id") val streamId: String,
) : OutboundMessage

/** Barge-in: stop desktop synthesis immediately. */
@Serializable
@SerialName("interrupt")
data class InterruptMessage(
    val reason: String = "barge_in",
) : OutboundMessage

@Serializable
@SerialName("telemetry_snapshot")
data class TelemetrySnapshotMessage(
    @SerialName("request_id") val requestId: String?,
    val snapshot: JsonObject,
) : OutboundMessage

@Serializable
@SerialName("device_command_result")
data class DeviceCommandResultMessage(
    val id: String,
    val ok: Boolean,
    val detail: String? = null,
) : OutboundMessage

/**
 * A note captured on the phone and pushed to the desktop's note stores.
 *
 * [timestampMs] is when the user hit send, not when the frame reached the
 * desktop: a note queued offline and replayed an hour later still belongs in the
 * journal entry for the moment it was written.
 */
@Serializable
@SerialName("ping")
data class PingMessage(
    @SerialName("sent_at_ms") val sentAtMs: Long,
) : OutboundMessage

@Serializable
@SerialName("quick_note")
data class QuickNoteMessage(
    /** `logseq` or `joplin`. */
    val target: String,
    /** `append` or `create`. */
    val mode: String,
    val content: String,
    @SerialName("timestamp_ms") val timestampMs: Long,
) : OutboundMessage {

    companion object {
        const val TARGET_LOGSEQ = "logseq"
        const val TARGET_JOPLIN = "joplin"
        const val MODE_APPEND = "append"
        const val MODE_CREATE = "create"
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/notifications/ApprovalNotificationManager.kt`

```kotlin
package com.jarvis.assistant.notifications

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.jarvis.assistant.JarvisRuntime
import com.jarvis.assistant.R
import com.jarvis.assistant.network.ApprovalRequestEvent
import com.jarvis.assistant.ui.approval.Markdown
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * Signs approval decisions so the desktop can prove the tap came from the paired
 * handset rather than anything else that reached the WebSocket port.
 *
 * There is deliberately no unsigned path. An empty-signature fallback would mean
 * that losing or never setting the secret silently downgrades every approval to
 * "trust anything that can reach the port" — the failure would be invisible
 * precisely when it matters. Without a secret, signing fails and the decision is
 * not sent at all.
 */
object ApprovalSigner {

    fun sign(
        secret: String,
        id: String,
        approved: Boolean,
        deviceId: String,
        atMs: Long,
        nonce: String,
    ): String? {
        if (secret.isEmpty()) return null
        val payload = "$id|$approved|$deviceId|$atMs|$nonce"
        return runCatching {
            val mac = Mac.getInstance("HmacSHA256")
            mac.init(SecretKeySpec(secret.toByteArray(Charsets.UTF_8), "HmacSHA256"))
            mac.doFinal(payload.toByteArray(Charsets.UTF_8))
                .joinToString("") { byte -> "%02x".format(byte) }
        }.getOrNull()
    }
}

/**
 * Posts the lock-screen approval gate and routes the button taps.
 *
 * The decision goes back over the existing WebSocket from a BroadcastReceiver,
 * so the desktop unblocks without the phone ever being unlocked or the app
 * being brought to the foreground.
 */
class ApprovalNotificationManager(context: Context) {

    private val appContext = context.applicationContext
    private val notifier = NotificationManagerCompat.from(appContext)

    init {
        createChannels()
    }

    private fun createChannels() {
        val manager = ContextCompat.getSystemService(appContext, NotificationManager::class.java)
            ?: return

        val approvals = NotificationChannel(
            CHANNEL_APPROVALS,
            appContext.getString(R.string.channel_approvals_name),
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = appContext.getString(R.string.channel_approvals_description)
            enableVibration(true)
            setShowBadge(true)
            lockscreenVisibility = NotificationCompat.VISIBILITY_PUBLIC
        }

        val link = NotificationChannel(
            CHANNEL_LINK,
            appContext.getString(R.string.channel_link_name),
            NotificationManager.IMPORTANCE_MIN,
        ).apply {
            description = appContext.getString(R.string.channel_link_description)
            setShowBadge(false)
        }

        manager.createNotificationChannel(approvals)
        manager.createNotificationChannel(link)
    }

    fun post(request: ApprovalRequestEvent) {
        val note = request.note
        // Markdown reads as noise in a notification, which has no styling to
        // carry it: flatten to text rather than showing raw syntax.
        val proposed = note?.markdown ?: note?.after ?: request.detail
        val body = buildString {
            append(request.summary.ifBlank { "Waiting on your approval." })
            proposed?.takeIf { it.isNotBlank() }?.let {
                append('\n')
                append(Markdown.toPlainText(it).take(NOTIFICATION_BODY_LIMIT))
            }
        }

        val subText = when {
            note != null -> if (note.isJoplin) "Joplin" else "Logseq"
            else -> request.tier
        }

        val notification = NotificationCompat.Builder(appContext, CHANNEL_APPROVALS)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(request.title)
            .setContentText(request.summary.ifBlank { "Waiting on your approval." })
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setSubText(subText)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            // NotificationCompat has no CATEGORY_WORK; REMINDER is the closest
            // documented category for a pending action awaiting a decision.
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setAutoCancel(false)
            .setOngoing(false)
            .setOnlyAlertOnce(true)
            .addAction(
                R.drawable.ic_notification,
                appContext.getString(R.string.action_approve),
                decisionIntent(request.id, approved = true),
            )
            .addAction(
                R.drawable.ic_notification,
                appContext.getString(R.string.action_reject),
                decisionIntent(request.id, approved = false),
            )
            .build()

        // POST_NOTIFICATIONS may still be denied; the desktop gate then falls back
        // to its own timeout rather than the phone silently swallowing the request.
        runCatching { notifier.notify(notificationId(request.id), notification) }
    }

    fun cancel(requestId: String) {
        notifier.cancel(notificationId(requestId))
    }

    private fun decisionIntent(requestId: String, approved: Boolean): PendingIntent {
        val intent = Intent(appContext, ApprovalActionReceiver::class.java).apply {
            action = if (approved) ACTION_APPROVE else ACTION_REJECT
            putExtra(EXTRA_REQUEST_ID, requestId)
        }
        return PendingIntent.getBroadcast(
            appContext,
            notificationId(requestId) + if (approved) 1 else 2,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    companion object {
        const val CHANNEL_APPROVALS = "jarvis_approvals"
        const val CHANNEL_LINK = "jarvis_link"
        const val ACTION_APPROVE = "com.jarvis.assistant.APPROVE"
        const val ACTION_REJECT = "com.jarvis.assistant.REJECT"
        const val EXTRA_REQUEST_ID = "request_id"

        /** A shade notification truncates anyway; sending less keeps it legible. */
        private const val NOTIFICATION_BODY_LIMIT = 600

        fun notificationId(requestId: String): Int = requestId.hashCode() and 0x7fffffff
    }
}

/** Receives the lock-screen taps and hands the signed decision to the runtime. */
class ApprovalActionReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val requestId = intent.getStringExtra(ApprovalNotificationManager.EXTRA_REQUEST_ID)
            ?: return
        val approved = when (intent.action) {
            ApprovalNotificationManager.ACTION_APPROVE -> true
            ApprovalNotificationManager.ACTION_REJECT -> false
            else -> return
        }
        JarvisRuntime.initialize(context)
        JarvisRuntime.submitApprovalDecision(requestId, approved)
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/service/BootReceiver.kt`

```kotlin
package com.jarvis.assistant.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Brings the link back after a reboot.
 *
 * Without this the foreground service only ever started from the HUD or the
 * assistant session, so a phone rebooted overnight had no socket open in the
 * morning and approval requests simply stopped arriving — with nothing on the
 * device to say so, because the HUD is the only surface that would have said it.
 *
 * `BOOT_COMPLETED` is one of the documented exemptions to the background
 * foreground-service start restriction, so starting the service from here is
 * allowed where a sticky restart would not be.
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED,
            Intent.ACTION_MY_PACKAGE_REPLACED,
            -> {
                Log.i(TAG, "restarting link after ${intent.action}")
                JarvisForegroundService.start(context)
            }
        }
    }

    private companion object {
        const val TAG = "JarvisBoot"
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/service/JarvisForegroundService.kt`

```kotlin
package com.jarvis.assistant.service

import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.jarvis.assistant.JarvisRuntime
import com.jarvis.assistant.MainActivity
import com.jarvis.assistant.R
import com.jarvis.assistant.network.ConnectionState
import com.jarvis.assistant.notifications.ApprovalNotificationManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch

/**
 * Keeps the process alive so approval requests and voice replies still arrive
 * with the screen off.
 *
 * The service starts under the `specialUse` foreground type — holding the link
 * open is not itself microphone work — and promotes itself to `microphone` only
 * while capture is running. Declaring `microphone` up front would make
 * startForeground throw on Android 14+ whenever RECORD_AUDIO has not been
 * granted yet.
 */
class JarvisForegroundService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var watcher: Job? = null
    private var wakeLock: PowerManager.WakeLock? = null

    @Volatile private var lastState: ConnectionState = ConnectionState.RECONNECTING

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        JarvisRuntime.initialize(this)

        startInForeground(ConnectionState.RECONNECTING, micActive = false)
        acquireWakeLock()

        // Synchronous, so the runtime can promote the service to the `microphone`
        // type and learn whether the platform allowed it *before* AudioRecord is
        // opened. Driving this off the micActive flow instead is too late: the
        // collector is dispatched through a channel, so the promotion lands after
        // startRecording() has already been evaluated by the audio policy.
        JarvisRuntime.micForegroundPromoter = { wantsMic ->
            startInForeground(lastState, micActive = wantsMic)
        }

        watcher = scope.launch {
            combine(
                JarvisRuntime.socket.state,
                JarvisRuntime.micActive,
            ) { state, mic -> state to mic }
                .collect { (state, mic) ->
                    startInForeground(state, mic)
                }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        JarvisRuntime.connect()
        // Restarted by the system after a kill: the whole point is to come back.
        return START_STICKY
    }

    override fun onDestroy() {
        watcher?.cancel()
        watcher = null
        JarvisRuntime.micForegroundPromoter = null
        releaseWakeLock()
        super.onDestroy()
    }

    /**
     * @return true when the requested foreground type was actually applied. A false
     * here for a microphone request means the platform refused, and the caller must
     * not capture: see the catch block.
     */
    private fun startInForeground(state: ConnectionState, micActive: Boolean): Boolean {
        lastState = state
        val wantsMicType = micActive && JarvisRuntime.hasMicPermission()
        val type = if (wantsMicType) {
            ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
        } else {
            specialUseType()
        }

        val text = when (state) {
            ConnectionState.CONNECTED -> if (micActive) "Listening" else "Linked to desktop"
            ConnectionState.RECONNECTING -> "Reconnecting…"
            ConnectionState.OFFLINE -> "Offline"
        }

        val notification = NotificationCompat.Builder(this, ApprovalNotificationManager.CHANNEL_LINK)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(text)
            .setOngoing(true)
            .setShowWhen(false)
            .setSilent(true)
            .setPriority(NotificationCompat.PRIORITY_MIN)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .setContentIntent(contentIntent())
            .build()

        return try {
            ServiceCompat.startForeground(this, NOTIFICATION_ID, notification, type)
            true
        } catch (e: Exception) {
            // A denied permission must not take the whole link down, so the service
            // stays up under its uncapped specialUse type.
            Log.e(TAG, "startForeground(type=$type) rejected", e)
            if (wantsMicType) {
                // But capture must stop. `microphone` is a while-in-use type and the
                // platform throws when one is started from the background; silently
                // downgrading and carrying on left AudioRecord running under a
                // non-microphone service, which the platform mutes — an ongoing
                // notification reading "Listening" while the desktop received an
                // endless stream of silence, recorded only in logcat.
                runCatching {
                    ServiceCompat.startForeground(
                        this,
                        NOTIFICATION_ID,
                        notification,
                        specialUseType(),
                    )
                }
                if (JarvisRuntime.micActive.value) JarvisRuntime.stopMic()
            }
            false
        }
    }

    private fun specialUseType(): Int =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
        } else {
            0
        }

    private fun contentIntent(): PendingIntent =
        PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

    private fun acquireWakeLock() {
        if (wakeLock != null) return
        val pm = ContextCompat.getSystemService(this, PowerManager::class.java) ?: return
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, WAKE_LOCK_TAG).apply {
            setReferenceCounted(false)
            runCatching { acquire(WAKE_LOCK_TIMEOUT_MS) }
        }
    }

    private fun releaseWakeLock() {
        wakeLock?.let { lock -> runCatching { if (lock.isHeld) lock.release() } }
        wakeLock = null
    }

    companion object {
        private const val TAG = "JarvisFgs"
        private const val NOTIFICATION_ID = 0x4A56
        private const val WAKE_LOCK_TAG = "JarvisMobile::link"

        /**
         * Bounded so a crash on the desktop side cannot pin the CPU awake
         * indefinitely; the service re-acquires whenever it is restarted.
         */
        private const val WAKE_LOCK_TIMEOUT_MS = 6L * 60L * 60L * 1000L

        const val ACTION_STOP = "com.jarvis.assistant.STOP_LINK"

        fun start(context: Context) {
            val intent = Intent(context, JarvisForegroundService::class.java)
            runCatching { ContextCompat.startForegroundService(context, intent) }
                .onFailure { Log.e(TAG, "could not start foreground service", it) }
        }

        fun stop(context: Context) {
            val intent = Intent(context, JarvisForegroundService::class.java)
                .setAction(ACTION_STOP)
            runCatching { context.startService(intent) }
        }
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/service/JarvisInteractionSession.kt`

```kotlin
package com.jarvis.assistant.service

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.service.voice.VoiceInteractionSession
import android.service.voice.VoiceInteractionSessionService
import android.util.Log
import com.jarvis.assistant.JarvisRuntime
import com.jarvis.assistant.MainActivity

/** Factory the platform calls to spin up an assistant session. */
class JarvisInteractionSessionService : VoiceInteractionSessionService() {
    override fun onNewSession(args: Bundle?): VoiceInteractionSession =
        JarvisInteractionSession(this)
}

/**
 * The assistant session itself.
 *
 * Rather than draw a system overlay, this hands straight off to the HUD with the
 * microphone already live — the useful thing on a power-button press is to be
 * talking to the desktop, not to look at a translucent panel.
 */
class JarvisInteractionSession(context: Context) : VoiceInteractionSession(context) {

    private val appContext = context.applicationContext

    override fun onCreate() {
        super.onCreate()
        JarvisRuntime.initialize(appContext)
    }

    override fun onShow(args: Bundle?, showFlags: Int) {
        super.onShow(args, showFlags)
        Log.i(TAG, "assistant session shown (flags=$showFlags)")

        JarvisRuntime.connect()
        JarvisForegroundService.start(appContext)

        val intent = Intent(appContext, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            action = MainActivity.ACTION_START_LISTENING
        }
        runCatching { startAssistantActivity(intent) }
            .onFailure { appContext.startActivity(intent) }

        hide()
    }

    override fun onHide() {
        super.onHide()
        Log.i(TAG, "assistant session hidden")
    }

    companion object {
        private const val TAG = "JarvisSession"
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/service/JarvisRecognitionService.kt`

```kotlin
package com.jarvis.assistant.service

import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionService
import android.speech.SpeechRecognizer
import com.jarvis.assistant.JarvisRuntime

/**
 * A VoiceInteractionService is only accepted by the platform when it also
 * declares a recognition service, so this exists to satisfy that contract.
 *
 * Recognition itself happens on the desktop: audio is streamed there and the
 * transcript comes back over the WebSocket, so there is no on-device result to
 * report. Callers that bind here are told the operation is unsupported rather
 * than being left waiting on a callback that will never fire.
 */
class JarvisRecognitionService : RecognitionService() {

    override fun onCreate() {
        super.onCreate()
        JarvisRuntime.initialize(this)
    }

    override fun onStartListening(recognizerIntent: Intent?, listener: Callback?) {
        // Route the audio to the desktop, then close the client out cleanly.
        JarvisRuntime.startMic()
        listener?.let {
            runCatching { it.readyForSpeech(Bundle.EMPTY) }
            runCatching { it.error(SpeechRecognizer.ERROR_CLIENT) }
        }
    }

    override fun onStopListening(listener: Callback?) {
        JarvisRuntime.stopMic()
    }

    override fun onCancel(listener: Callback?) {
        JarvisRuntime.stopMic()
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/service/JarvisVoiceService.kt`

```kotlin
package com.jarvis.assistant.service

import android.content.Intent
import android.os.Bundle
import android.service.voice.VoiceInteractionService
import android.util.Log
import com.jarvis.assistant.JarvisRuntime

/**
 * Registers Jarvis as the system digital assistant.
 *
 * Selecting this app under Settings > Apps > Default apps > Digital assistant
 * routes the power-button long-press and the corner swipe here, which is what
 * makes the assistant reachable without unlocking or finding the launcher icon.
 */
class JarvisVoiceService : VoiceInteractionService() {

    override fun onCreate() {
        super.onCreate()
        JarvisRuntime.initialize(this)
        Log.i(TAG, "voice interaction service created")
    }

    override fun onReady() {
        super.onReady()
        // The link should already be warm by the time the user speaks.
        JarvisRuntime.connect()
    }

    override fun onLaunchVoiceAssistFromKeyguard() {
        super.onLaunchVoiceAssistFromKeyguard()
        showSession(Bundle.EMPTY, 0)
    }

    override fun onShutdown() {
        Log.i(TAG, "voice interaction service shutting down")
        super.onShutdown()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        return START_STICKY
    }

    companion object {
        private const val TAG = "JarvisVoice"
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/service/QuickCaptureTileService.kt`

```kotlin
package com.jarvis.assistant.service

import android.app.PendingIntent
import android.content.Intent
import android.os.Build
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import com.jarvis.assistant.JarvisRuntime
import com.jarvis.assistant.MainActivity
import com.jarvis.assistant.R
import com.jarvis.assistant.network.ConnectionState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * One-tap note capture from the notification shade.
 *
 * The tile doubles as a link indicator: active means the desktop is reachable,
 * so a glance at the shade answers "will this send or queue?" without opening
 * anything.
 */
class QuickCaptureTileService : TileService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var watcher: Job? = null

    override fun onStartListening() {
        super.onStartListening()
        // SystemUI can re-bind or re-request listening without an intervening
        // onStopListening, which left two collectors racing on the same Tile.
        watcher?.cancel()
        JarvisRuntime.initialize(this)
        // The tile is only visible while listening, so the collector lives
        // exactly as long as anyone can see the result.
        watcher = scope.launch {
            JarvisRuntime.socket.state.collect(::render)
        }
    }

    override fun onStopListening() {
        watcher?.cancel()
        watcher = null
        super.onStopListening()
    }

    override fun onDestroy() {
        watcher?.cancel()
        watcher = null
        super.onDestroy()
    }

    override fun onClick() {
        super.onClick()
        val intent = Intent(this, MainActivity::class.java).apply {
            action = MainActivity.ACTION_QUICK_CAPTURE
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        }

        if (isLocked) {
            // Capture needs the keyboard, which the keyguard will not give us.
            unlockAndRun { launch(intent) }
        } else {
            launch(intent)
        }
    }

    private fun launch(intent: Intent) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            // API 34 replaced the Intent overload; the older one throws here.
            val pending = PendingIntent.getActivity(
                this,
                0,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            startActivityAndCollapse(pending)
        } else {
            @Suppress("DEPRECATION")
            startActivityAndCollapse(intent)
        }
    }

    private fun render(state: ConnectionState) {
        val tile = qsTile ?: return
        tile.state = if (state == ConnectionState.CONNECTED) {
            Tile.STATE_ACTIVE
        } else {
            Tile.STATE_INACTIVE
        }
        tile.label = getString(R.string.tile_quick_capture)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            tile.subtitle = when (state) {
                ConnectionState.CONNECTED -> getString(R.string.tile_subtitle_linked)
                ConnectionState.RECONNECTING -> getString(R.string.tile_subtitle_reconnecting)
                ConnectionState.OFFLINE -> getString(R.string.tile_subtitle_offline)
            }
        }
        tile.updateTile()
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/telemetry/DeviceTelemetryProvider.kt`

```kotlin
package com.jarvis.assistant.telemetry

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.media.AudioManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.wifi.WifiManager
import android.os.BatteryManager
import android.os.Build
import android.os.PowerManager
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.util.Log
import androidx.core.content.ContextCompat
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Result of a hardware action requested by the desktop. */
data class CommandOutcome(val ok: Boolean, val detail: String)

/**
 * Reads phone vitals and performs the hardware actions the desktop can invoke.
 *
 * Every accessor degrades to a null/failed result rather than throwing: the
 * desktop polls this on a timer and one missing sensor must not break the frame.
 */
class DeviceTelemetryProvider(context: Context) {

    private val appContext = context.applicationContext

    private val audioManager: AudioManager? =
        ContextCompat.getSystemService(appContext, AudioManager::class.java)
    private val cameraManager: CameraManager? =
        ContextCompat.getSystemService(appContext, CameraManager::class.java)
    private val connectivityManager: ConnectivityManager? =
        ContextCompat.getSystemService(appContext, ConnectivityManager::class.java)
    private val powerManager: PowerManager? =
        ContextCompat.getSystemService(appContext, PowerManager::class.java)

    @Volatile private var torchOn = false

    // ------------------------------------------------------------- battery ----

    private fun batteryIntent(): Intent? =
        appContext.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))

    fun batteryPercent(): Int? {
        val intent = batteryIntent() ?: return null
        val level = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
        val scale = intent.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
        if (level < 0 || scale <= 0) return null
        return (level * 100f / scale).toInt()
    }

    /** One of: ac, usb, wireless, dock, unplugged. */
    fun chargingSource(): String {
        val intent = batteryIntent() ?: return "unknown"
        return when (intent.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0)) {
            BatteryManager.BATTERY_PLUGGED_AC -> "ac"
            BatteryManager.BATTERY_PLUGGED_USB -> "usb"
            BatteryManager.BATTERY_PLUGGED_WIRELESS -> "wireless"
            else -> "unplugged"
        }
    }

    fun isCharging(): Boolean {
        val status = batteryIntent()?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: return false
        return status == BatteryManager.BATTERY_STATUS_CHARGING ||
            status == BatteryManager.BATTERY_STATUS_FULL
    }

    // ------------------------------------------------------------- network ----

    /** wifi, cellular, ethernet, vpn or none. */
    fun activeTransport(): String {
        val cm = connectivityManager ?: return "unknown"
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return "none"
        return when {
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "cellular"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "ethernet"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN) -> "vpn"
            else -> "other"
        }
    }

    /**
     * The SSID is only readable with a location permission on API 29+. This app
     * does not request one, so expect null off Wi-Fi or on modern releases —
     * the transport type above is the reliable signal.
     */
    @Suppress("DEPRECATION")
    fun wifiSsid(): String? {
        if (activeTransport() != "wifi") return null
        val hasLocation = ContextCompat.checkSelfPermission(
            appContext,
            Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && !hasLocation) return null

        val wifi = appContext.applicationContext
            .getSystemService(Context.WIFI_SERVICE) as? WifiManager ?: return null
        val ssid = runCatching { wifi.connectionInfo?.ssid }.getOrNull() ?: return null
        val cleaned = ssid.trim('"')
        return cleaned.takeUnless { it.isEmpty() || it == "<unknown ssid>" }
    }

    // ------------------------------------------------------------- actions ----

    private fun torchCameraId(): String? {
        val cm = cameraManager ?: return null
        return runCatching {
            cm.cameraIdList.firstOrNull { id ->
                cm.getCameraCharacteristics(id)
                    .get(CameraCharacteristics.FLASH_INFO_AVAILABLE) == true
            }
        }.getOrNull()
    }

    fun setTorch(enabled: Boolean): CommandOutcome {
        val cm = cameraManager ?: return CommandOutcome(false, "no camera service")
        val id = torchCameraId() ?: return CommandOutcome(false, "no flash unit")
        return runCatching {
            cm.setTorchMode(id, enabled)
            torchOn = enabled
            CommandOutcome(true, "torch ${if (enabled) "on" else "off"}")
        }.getOrElse { CommandOutcome(false, it.message ?: "setTorchMode failed") }
    }

    fun toggleTorch(): CommandOutcome = setTorch(!torchOn)

    fun mediaVolume(): Int =
        audioManager?.getStreamVolume(AudioManager.STREAM_MUSIC) ?: 0

    fun maxMediaVolume(): Int =
        audioManager?.getStreamMaxVolume(AudioManager.STREAM_MUSIC) ?: 0

    /** @param percent 0-100, clamped. */
    fun setMediaVolumePercent(percent: Int): CommandOutcome {
        val am = audioManager ?: return CommandOutcome(false, "no audio service")
        val max = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
        if (max <= 0) return CommandOutcome(false, "no media stream")
        val target = (percent.coerceIn(0, 100) * max + 50) / 100
        return runCatching {
            am.setStreamVolume(AudioManager.STREAM_MUSIC, target, 0)
            CommandOutcome(true, "volume $target/$max")
        }.getOrElse { CommandOutcome(false, it.message ?: "setStreamVolume failed") }
    }

    private fun vibrator(): Vibrator? =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            ContextCompat.getSystemService(appContext, VibratorManager::class.java)?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            ContextCompat.getSystemService(appContext, Vibrator::class.java)
        }

    /** `tick`, `confirm`, `alert` — distinct patterns so taps are identifiable blind. */
    fun vibrate(pattern: String = "tick"): CommandOutcome {
        val v = vibrator() ?: return CommandOutcome(false, "no vibrator")
        if (!v.hasVibrator()) return CommandOutcome(false, "no vibrator")
        val timings = when (pattern) {
            "confirm" -> longArrayOf(0, 40, 80, 40)
            "alert" -> longArrayOf(0, 120, 90, 120, 90, 220)
            else -> longArrayOf(0, 25)
        }
        val amplitudes = IntArray(timings.size) { index ->
            if (index % 2 == 0) 0 else VibrationEffect.DEFAULT_AMPLITUDE
        }
        return runCatching {
            v.vibrate(VibrationEffect.createWaveform(timings, amplitudes, -1))
            CommandOutcome(true, "vibrated $pattern")
        }.getOrElse { CommandOutcome(false, it.message ?: "vibrate failed") }
    }

    fun isIgnoringBatteryOptimizations(): Boolean =
        powerManager?.isIgnoringBatteryOptimizations(appContext.packageName) ?: false

    fun isInteractive(): Boolean = powerManager?.isInteractive ?: false

    // ------------------------------------------------------------ snapshot ----

    fun collectTelemetrySnapshot(): JsonObject = buildJsonObject {
        put("device_model", "${Build.MANUFACTURER} ${Build.MODEL}")
        put("android_release", Build.VERSION.RELEASE)
        put("sdk_int", Build.VERSION.SDK_INT)
        put("captured_at_ms", System.currentTimeMillis())

        batteryPercent()?.let { put("battery_percent", it) }
        put("battery_charging", isCharging())
        put("battery_source", chargingSource())

        put("network_transport", activeTransport())
        wifiSsid()?.let { put("wifi_ssid", it) }

        put("media_volume", mediaVolume())
        put("media_volume_max", maxMediaVolume())
        put("torch_on", torchOn)
        put("screen_on", isInteractive())
        put("battery_optimizations_ignored", isIgnoringBatteryOptimizations())
    }

    companion object {
        private const val TAG = "JarvisTelemetry"

        fun logUnsupported(action: String) {
            Log.w(TAG, "unsupported device action: $action")
        }
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/ui/approval/ApprovalDialog.kt`

```kotlin
package com.jarvis.assistant.ui.approval

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.assistant.network.ApprovalRequestEvent
import com.jarvis.assistant.ui.theme.JarvisAmber
import com.jarvis.assistant.ui.theme.JarvisCyan
import com.jarvis.assistant.ui.theme.JarvisGreen
import com.jarvis.assistant.ui.theme.JarvisOutline
import com.jarvis.assistant.ui.theme.JarvisRed
import com.jarvis.assistant.ui.theme.JarvisSurface
import com.jarvis.assistant.ui.theme.JarvisTextMuted
import com.jarvis.assistant.ui.theme.JarvisTextPrimary
import kotlinx.coroutines.delay

/**
 * The approval card, in plain and note-edit forms.
 *
 * A note edit gets the Markdown rendered and, where the desktop supplied enough
 * to build one, a diff — approving a note rewrite from an escaped JSON blob is
 * approving something you have not read.
 */
@Composable
fun ApprovalCard(
    request: ApprovalRequestEvent,
    onApprove: () -> Unit,
    onReject: () -> Unit,
    modifier: Modifier = Modifier,
    /** False when the link is down or unpaired, so a decision cannot be delivered. */
    linkReady: Boolean = true,
) {
    // Keyed on the whole request, not on its id. The runtime replaces an approval
    // that reuses an id, and the LazyColumn key is the id too, so keying the parsed
    // diff on the id alone left the card rendering the superseded diff while Approve
    // submitted a decision on the revised request — approving something unread.
    val diff = remember(request) {
        request.note?.let { NoteDiff.forPayload(it.diff, it.before, it.after) }
    }
    val summary = remember(diff) { diff?.let { NoteDiff.summarize(it) } }

    // `expires_at_ms` was parsed and never read, so an expired card stayed tappable
    // and re-signed with a fresh decided_at_ms that passed the desktop's skew check.
    val expiresAt = request.expiresAtMs
    var now by remember(request.id) { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(request.id, expiresAt) {
        if (expiresAt == null) return@LaunchedEffect
        while (System.currentTimeMillis() < expiresAt) {
            now = System.currentTimeMillis()
            delay(1_000)
        }
        now = System.currentTimeMillis()
    }
    val expired = expiresAt != null && now >= expiresAt
    val canDecide = linkReady && !expired

    // Default to showing the diff when there is one: it is the thing being
    // approved, so it should not need a tap to reveal.
    var showDiff by rememberSaveable(request.id) { mutableStateOf(true) }

    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(JarvisSurface, RoundedCornerShape(12.dp))
            .border(1.dp, JarvisAmber.copy(alpha = 0.4f), RoundedCornerShape(12.dp))
            .padding(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = request.title,
                style = MaterialTheme.typography.titleMedium,
                color = JarvisAmber,
                modifier = Modifier.weight(1f),
            )
            request.note?.let { note ->
                TargetBadge(if (note.isJoplin) "JOPLIN" else "LOGSEQ")
            }
        }

        request.note?.let { note ->
            val where = listOfNotNull(note.title, note.location).joinToString(" · ")
            if (where.isNotBlank()) {
                Spacer(Modifier.height(2.dp))
                Text(where, style = MaterialTheme.typography.labelSmall, color = JarvisTextMuted)
            }
        }

        if (request.summary.isNotBlank()) {
            Spacer(Modifier.height(8.dp))
            Text(
                text = request.summary,
                style = MaterialTheme.typography.bodyMedium,
                color = JarvisTextPrimary,
            )
        }

        if (request.isNoteEdit) {
            NoteBody(
                request = request,
                diff = diff,
                added = summary?.added ?: 0,
                removed = summary?.removed ?: 0,
                expanded = showDiff,
                onToggle = { showDiff = !showDiff },
            )
        } else {
            request.detail?.takeIf { it.isNotBlank() }?.let { detail ->
                Spacer(Modifier.height(6.dp))
                Text(
                    text = detail,
                    style = MaterialTheme.typography.bodyMedium.copy(fontFamily = FontFamily.Monospace),
                    color = JarvisTextMuted,
                )
            }
        }

        val blocked = when {
            expired -> "Expired — ask the desktop to raise this again."
            !linkReady -> "Not connected. A decision taken now would not reach the desktop."
            else -> null
        }
        if (blocked != null) {
            Spacer(Modifier.height(8.dp))
            Text(
                text = blocked,
                style = MaterialTheme.typography.labelMedium,
                color = JarvisRed,
            )
        } else if (expiresAt != null) {
            Spacer(Modifier.height(8.dp))
            val secondsLeft = ((expiresAt - now) / 1000).coerceAtLeast(0)
            Text(
                text = "Expires in ${secondsLeft / 60}m ${secondsLeft % 60}s",
                style = MaterialTheme.typography.labelSmall,
                color = JarvisTextMuted,
            )
        }

        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = onApprove,
                enabled = canDecide,
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(10.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = JarvisGreen.copy(alpha = 0.16f),
                    contentColor = JarvisGreen,
                ),
            ) { Text("Approve") }

            Button(
                onClick = onReject,
                enabled = canDecide,
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(10.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = JarvisRed.copy(alpha = 0.16f),
                    contentColor = JarvisRed,
                ),
            ) { Text("Reject") }
        }
    }
}

@Composable
private fun NoteBody(
    request: ApprovalRequestEvent,
    diff: List<DiffLine>?,
    added: Int,
    removed: Int,
    expanded: Boolean,
    onToggle: () -> Unit,
) {
    val markdown = request.note?.markdown
        ?: request.note?.after
        ?: request.detail

    if (diff != null) {
        Spacer(Modifier.height(10.dp))
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clickable(onClick = onToggle)
                .padding(vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = if (expanded) "▾ Changes" else "▸ Changes",
                style = MaterialTheme.typography.labelSmall,
                color = JarvisTextMuted,
            )
            Spacer(Modifier.width(10.dp))
            if (added > 0) {
                Text("+$added", style = MaterialTheme.typography.labelSmall, color = JarvisGreen)
                Spacer(Modifier.width(6.dp))
            }
            if (removed > 0) {
                Text("−$removed", style = MaterialTheme.typography.labelSmall, color = JarvisRed)
            }
        }
        AnimatedVisibility(visible = expanded) {
            DiffView(diff)
        }
    } else if (!markdown.isNullOrBlank()) {
        Spacer(Modifier.height(10.dp))
        Text("PROPOSED", style = MaterialTheme.typography.labelSmall, color = JarvisTextMuted)
        Spacer(Modifier.height(6.dp))
        Column(
            Modifier
                .fillMaxWidth()
                .heightIn(max = 320.dp)
                .verticalScroll(rememberScrollState()),
        ) {
            MarkdownText(markdown)
        }
    }
}

@Composable
private fun DiffView(lines: List<DiffLine>, modifier: Modifier = Modifier) {
    val horizontal = rememberScrollState()

    // Lazy rather than a scrolling Column: a whole-document rewrite can be a
    // thousand lines, and composing every one of them to show thirty froze the HUD
    // the moment the approval arrived. Clipped before the background so an added or
    // removed first/last line does not square off the card's rounded corners.
    LazyColumn(
        modifier = modifier
            .fillMaxWidth()
            .heightIn(max = 340.dp)
            .clip(RoundedCornerShape(8.dp))
            .background(Color.Black)
            .border(1.dp, JarvisOutline, RoundedCornerShape(8.dp))
            .padding(vertical = 6.dp),
    ) {
        items(lines.size) { index ->
            val line = lines[index]
            val (tint, prefix, background) = when (line.kind) {
                DiffKind.ADDED -> Triple(JarvisGreen, "+", JarvisGreen.copy(alpha = 0.10f))
                DiffKind.REMOVED -> Triple(JarvisRed, "−", JarvisRed.copy(alpha = 0.10f))
                DiffKind.GAP -> Triple(JarvisTextMuted, " ", Color.Transparent)
                DiffKind.CONTEXT -> Triple(JarvisTextMuted, " ", Color.Transparent)
            }
            Row(
                Modifier
                    .fillMaxWidth()
                    .background(background)
                    .horizontalScroll(horizontal)
                    .padding(horizontal = 10.dp, vertical = 1.dp),
            ) {
                Text(
                    text = "$prefix ${line.text}",
                    style = MaterialTheme.typography.bodyMedium.copy(
                        fontFamily = FontFamily.Monospace,
                        fontSize = 12.sp,
                    ),
                    color = tint,
                    softWrap = false,
                )
            }
        }
    }
}

@Composable
private fun TargetBadge(label: String) {
    Text(
        text = label,
        style = MaterialTheme.typography.labelSmall,
        color = JarvisCyan,
        modifier = Modifier
            .background(JarvisCyan.copy(alpha = 0.12f), RoundedCornerShape(6.dp))
            .padding(horizontal = 8.dp, vertical = 3.dp),
    )
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/ui/approval/Markdown.kt`

````kotlin
package com.jarvis.assistant.ui.approval

/**
 * A deliberately small Markdown subset: what note-taking apps actually emit.
 *
 * Pulling in a full CommonMark renderer would add a dependency and a lot of
 * surface for content that arrives as headings, emphasis, lists, links and
 * fenced code. Anything unrecognised falls through as literal text rather than
 * being dropped, so an unsupported construct is still readable.
 *
 * Parsing is pure Kotlin and produces no Compose types, keeping it unit testable.
 */

sealed interface MdBlock {
    data class Heading(val level: Int, val spans: List<MdSpan>) : MdBlock
    data class Paragraph(val spans: List<MdSpan>) : MdBlock
    data class ListItem(val indent: Int, val marker: String, val spans: List<MdSpan>) : MdBlock
    data class Quote(val spans: List<MdSpan>) : MdBlock
    data class CodeBlock(val language: String?, val code: String) : MdBlock
    data object Divider : MdBlock
}

/** An inline run of text with any combination of emphases applied. */
data class MdSpan(
    val text: String,
    val bold: Boolean = false,
    val italic: Boolean = false,
    val code: Boolean = false,
    val strike: Boolean = false,
    val link: String? = null,
)

object Markdown {

    private val HEADING = Regex("""^(#{1,6})\s+(.*)$""")
    private val BULLET = Regex("""^(\s*)[-*+]\s+(.*)$""")
    private val ORDERED = Regex("""^(\s*)(\d{1,3})[.)]\s+(.*)$""")
    private val QUOTE = Regex("""^\s*>\s?(.*)$""")
    private val DIVIDER = Regex("""^\s*([-*_])\s*(\1\s*){2,}$""")
    private val FENCE = Regex("""^\s*```\s*(\S+)?\s*$""")

    /** Logseq bullets carry `id::`/`collapsed::` metadata that is noise here. */
    private val LOGSEQ_PROPERTY = Regex("""^\s*[a-zA-Z][\w-]*::\s?.*$""")

    fun parse(source: String): List<MdBlock> {
        val blocks = mutableListOf<MdBlock>()
        val lines = source.replace("\r\n", "\n").split('\n')
        val paragraph = StringBuilder()

        fun flushParagraph() {
            if (paragraph.isNotEmpty()) {
                blocks += MdBlock.Paragraph(parseInline(paragraph.toString().trim()))
                paragraph.setLength(0)
            }
        }

        var index = 0
        while (index < lines.size) {
            val line = lines[index]

            val fence = FENCE.matchEntire(line)
            if (fence != null) {
                flushParagraph()
                val language = fence.groupValues[1].takeIf { it.isNotBlank() }
                val body = StringBuilder()
                index++
                while (index < lines.size && FENCE.matchEntire(lines[index]) == null) {
                    body.appendLine(lines[index])
                    index++
                }
                index++ // closing fence, or past the end for an unterminated block
                blocks += MdBlock.CodeBlock(language, body.toString().trimEnd('\n'))
                continue
            }

            when {
                line.isBlank() -> flushParagraph()

                LOGSEQ_PROPERTY.matches(line) -> Unit

                DIVIDER.matches(line) -> {
                    flushParagraph()
                    blocks += MdBlock.Divider
                }

                HEADING.matches(line) -> {
                    flushParagraph()
                    val (hashes, text) = HEADING.find(line)!!.destructured
                    blocks += MdBlock.Heading(hashes.length, parseInline(text.trim()))
                }

                QUOTE.matches(line) -> {
                    flushParagraph()
                    blocks += MdBlock.Quote(parseInline(QUOTE.find(line)!!.groupValues[1]))
                }

                BULLET.matches(line) -> {
                    flushParagraph()
                    val (indent, text) = BULLET.find(line)!!.destructured
                    blocks += MdBlock.ListItem(indent.length / 2, "•", parseInline(text))
                }

                ORDERED.matches(line) -> {
                    flushParagraph()
                    val (indent, number, text) = ORDERED.find(line)!!.destructured
                    blocks += MdBlock.ListItem(indent.length / 2, "$number.", parseInline(text))
                }

                else -> {
                    if (paragraph.isNotEmpty()) paragraph.append(' ')
                    paragraph.append(line.trim())
                }
            }
            index++
        }
        flushParagraph()
        return blocks
    }

    /**
     * Scans for `**bold**`, `*italic*`, `` `code` ``, `~~strike~~` and
     * `[text](url)`. An unmatched marker stays literal rather than swallowing
     * the rest of the line.
     */
    fun parseInline(source: String): List<MdSpan> {
        if (source.isEmpty()) return listOf(MdSpan(""))
        val spans = mutableListOf<MdSpan>()
        val literal = StringBuilder()
        var bold = false
        var italic = false
        var strike = false
        var i = 0

        fun flush() {
            if (literal.isNotEmpty()) {
                spans += MdSpan(literal.toString(), bold = bold, italic = italic, strike = strike)
                literal.setLength(0)
            }
        }

        while (i < source.length) {
            val rest = source.length - i
            val char = source[i]

            // Inline code wins over emphasis: markers inside it are literal.
            if (char == '`') {
                val close = source.indexOf('`', i + 1)
                if (close > i) {
                    flush()
                    spans += MdSpan(source.substring(i + 1, close), code = true)
                    i = close + 1
                    continue
                }
            }

            if (char == '[') {
                val closeText = source.indexOf(']', i + 1)
                if (closeText > i && closeText + 1 < source.length && source[closeText + 1] == '(') {
                    val closeUrl = source.indexOf(')', closeText + 2)
                    if (closeUrl > closeText) {
                        flush()
                        spans += MdSpan(
                            text = source.substring(i + 1, closeText),
                            bold = bold,
                            italic = italic,
                            link = source.substring(closeText + 2, closeUrl),
                        )
                        i = closeUrl + 1
                        continue
                    }
                }
            }

            if (rest >= 2 && source.startsWith("**", i)) {
                if (bold || source.indexOf("**", i + 2) > 0) {
                    flush(); bold = !bold; i += 2; continue
                }
            }
            if (rest >= 2 && source.startsWith("~~", i)) {
                if (strike || source.indexOf("~~", i + 2) > 0) {
                    flush(); strike = !strike; i += 2; continue
                }
            }
            if (char == '*' || char == '_') {
                val hasCloser = italic || source.indexOf(char, i + 1) > 0
                if (hasCloser) {
                    flush(); italic = !italic; i += 1; continue
                }
            }

            literal.append(char)
            i++
        }
        flush()
        return spans.ifEmpty { listOf(MdSpan(source)) }
    }

    /** Plain text, for notification bodies where styling is unavailable. */
    fun toPlainText(source: String): String = parse(source).joinToString("\n") { block ->
        when (block) {
            is MdBlock.Heading -> block.spans.joinToString("") { it.text }
            is MdBlock.Paragraph -> block.spans.joinToString("") { it.text }
            is MdBlock.ListItem -> "${block.marker} " + block.spans.joinToString("") { it.text }
            is MdBlock.Quote -> "> " + block.spans.joinToString("") { it.text }
            is MdBlock.CodeBlock -> block.code
            MdBlock.Divider -> "—"
        }
    }
}
````

## `jarvis-android/app/src/main/java/com/jarvis/assistant/ui/approval/MarkdownText.kt`

```kotlin
package com.jarvis.assistant.ui.approval

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.assistant.ui.theme.JarvisCyan
import com.jarvis.assistant.ui.theme.JarvisOutline
import com.jarvis.assistant.ui.theme.JarvisSurface
import com.jarvis.assistant.ui.theme.JarvisTextMuted
import com.jarvis.assistant.ui.theme.JarvisTextPrimary

/** Renders the parsed Markdown subset. */
@Composable
fun MarkdownText(source: String, modifier: Modifier = Modifier) {
    val blocks = remember(source) { Markdown.parse(source) }

    Column(modifier) {
        blocks.forEachIndexed { index, block ->
            if (index > 0) Spacer(Modifier.height(6.dp))
            when (block) {
                is MdBlock.Heading -> Text(
                    text = block.spans.toAnnotated(),
                    style = MaterialTheme.typography.titleMedium.copy(
                        fontSize = when (block.level) {
                            1 -> 19.sp
                            2 -> 17.sp
                            else -> 15.sp
                        },
                        fontWeight = FontWeight.SemiBold,
                    ),
                    color = JarvisTextPrimary,
                )

                is MdBlock.Paragraph -> Text(
                    text = block.spans.toAnnotated(),
                    style = MaterialTheme.typography.bodyMedium,
                    color = JarvisTextPrimary,
                )

                is MdBlock.ListItem -> Row(
                    modifier = Modifier.padding(start = (block.indent * 14).dp),
                ) {
                    Text(
                        text = block.marker,
                        style = MaterialTheme.typography.bodyMedium,
                        color = JarvisCyan,
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        text = block.spans.toAnnotated(),
                        style = MaterialTheme.typography.bodyMedium,
                        color = JarvisTextPrimary,
                    )
                }

                is MdBlock.Quote -> Row {
                    Spacer(
                        Modifier
                            .width(3.dp)
                            .height(18.dp)
                            .background(JarvisCyan, RoundedCornerShape(2.dp)),
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        text = block.spans.toAnnotated(),
                        style = MaterialTheme.typography.bodyMedium,
                        color = JarvisTextMuted,
                    )
                }

                is MdBlock.CodeBlock -> Column(
                    Modifier
                        .fillMaxWidth()
                        .background(JarvisSurface, RoundedCornerShape(8.dp))
                        .padding(10.dp),
                ) {
                    block.language?.let {
                        Text(it, style = MaterialTheme.typography.labelSmall, color = JarvisTextMuted)
                        Spacer(Modifier.height(4.dp))
                    }
                    // Code must not reflow; a wrapped shell command reads as a
                    // different command.
                    Text(
                        text = block.code,
                        modifier = Modifier.horizontalScroll(rememberScrollState()),
                        style = MaterialTheme.typography.bodyMedium.copy(
                            fontFamily = FontFamily.Monospace,
                            fontSize = 12.sp,
                        ),
                        color = JarvisTextPrimary,
                        softWrap = false,
                    )
                }

                MdBlock.Divider -> HorizontalDivider(color = JarvisOutline)
            }
        }
    }
}

fun List<MdSpan>.toAnnotated(): AnnotatedString = buildAnnotatedString {
    this@toAnnotated.forEach { span ->
        val style = SpanStyle(
            fontWeight = if (span.bold) FontWeight.SemiBold else null,
            fontStyle = if (span.italic) FontStyle.Italic else null,
            fontFamily = if (span.code) FontFamily.Monospace else null,
            color = if (span.code || span.link != null) JarvisCyan else JarvisTextPrimary,
            textDecoration = when {
                span.strike -> TextDecoration.LineThrough
                span.link != null -> TextDecoration.Underline
                else -> null
            },
        )
        withStyle(style) { append(span.text) }
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/ui/approval/NoteDiff.kt`

```kotlin
package com.jarvis.assistant.ui.approval

/** How a line changed between the current note and the proposed one. */
enum class DiffKind { CONTEXT, ADDED, REMOVED, GAP }

data class DiffLine(val kind: DiffKind, val text: String)

data class DiffSummary(val added: Int, val removed: Int) {
    val isEmpty: Boolean get() = added == 0 && removed == 0
}

/**
 * Line-level diffing for note edits.
 *
 * Deliberately pure Kotlin with no Android or Compose types, so the logic is
 * exercised by ordinary JVM unit tests rather than an instrumented run.
 */
object NoteDiff {

    /**
     * Above this, the quadratic LCS table costs more memory than the result is
     * worth on a handset, and nobody approves a 2000-line diff from a lock
     * screen anyway. Larger inputs degrade to a whole-body replacement.
     */
    const val MAX_LINES = 600

    /**
     * Hard ceiling on lines handed to the renderer, whoever produced them. Above
     * this a diff is not something a person reads on a handset; it is something
     * they scroll past before tapping Approve.
     */
    const val MAX_RENDERED_LINES = 1_200

    private val TRUNCATION_MARKER =
        DiffLine(DiffKind.GAP, "@@ diff truncated at $MAX_RENDERED_LINES lines @@")

    /** Unchanged lines kept either side of a change, so edits have context. */
    private const val CONTEXT_LINES = 3

    fun summarize(lines: List<DiffLine>): DiffSummary = DiffSummary(
        added = lines.count { it.kind == DiffKind.ADDED },
        removed = lines.count { it.kind == DiffKind.REMOVED },
    )

    /** Parses a unified diff the desktop already computed. */
    /**
     * A desktop-supplied unified diff, capped.
     *
     * `between` has always bounded its own output; this path had no cap at all, so a
     * whole-document rewrite arrived as however many lines the desktop felt like
     * sending and every one of them was rendered.
     */
    fun fromUnified(diff: String): List<DiffLine> = diff
        .split('\n')
        .asSequence()
        .filterNot { it.startsWith("diff ") || it.startsWith("index ") }
        .filterNot { it.startsWith("--- ") || it.startsWith("+++ ") }
        .map { line ->
            when {
                line.startsWith("@@") -> DiffLine(DiffKind.GAP, line)
                line.startsWith("+") -> DiffLine(DiffKind.ADDED, line.substring(1))
                line.startsWith("-") -> DiffLine(DiffKind.REMOVED, line.substring(1))
                line.startsWith(" ") -> DiffLine(DiffKind.CONTEXT, line.substring(1))
                line.isEmpty() -> DiffLine(DiffKind.CONTEXT, "")
                else -> DiffLine(DiffKind.CONTEXT, line)
            }
        }
        .take(MAX_RENDERED_LINES)
        .toList()
        .let { if (it.size < MAX_RENDERED_LINES) it else it + TRUNCATION_MARKER }

    /** Computes a diff between two whole documents. */
    fun between(before: String, after: String): List<DiffLine> {
        val old = before.split('\n')
        val new = after.split('\n')

        if (old.size > MAX_LINES || new.size > MAX_LINES) {
            return old.map { DiffLine(DiffKind.REMOVED, it) } +
                new.map { DiffLine(DiffKind.ADDED, it) }
        }

        return collapse(walk(old, new))
    }

    /** Classic LCS backtrack, emitting removals before additions at each edit. */
    private fun walk(old: List<String>, new: List<String>): List<DiffLine> {
        val rows = old.size
        val cols = new.size
        // (rows+1) x (cols+1) lengths table, flattened.
        val table = IntArray((rows + 1) * (cols + 1))
        fun at(r: Int, c: Int) = table[r * (cols + 1) + c]

        for (r in rows - 1 downTo 0) {
            for (c in cols - 1 downTo 0) {
                table[r * (cols + 1) + c] = if (old[r] == new[c]) {
                    at(r + 1, c + 1) + 1
                } else {
                    maxOf(at(r + 1, c), at(r, c + 1))
                }
            }
        }

        val out = ArrayList<DiffLine>(rows + cols)
        var r = 0
        var c = 0
        while (r < rows && c < cols) {
            when {
                old[r] == new[c] -> {
                    out += DiffLine(DiffKind.CONTEXT, old[r]); r++; c++
                }
                at(r + 1, c) >= at(r, c + 1) -> {
                    out += DiffLine(DiffKind.REMOVED, old[r]); r++
                }
                else -> {
                    out += DiffLine(DiffKind.ADDED, new[c]); c++
                }
            }
        }
        while (r < rows) out += DiffLine(DiffKind.REMOVED, old[r++])
        while (c < cols) out += DiffLine(DiffKind.ADDED, new[c++])
        return out
    }

    /**
     * Replaces long unchanged stretches with a single [DiffKind.GAP] marker.
     * A one-word change in a long note should not require scrolling past the
     * whole note to find it.
     */
    private fun collapse(lines: List<DiffLine>): List<DiffLine> {
        val keep = BooleanArray(lines.size)
        lines.forEachIndexed { index, line ->
            if (line.kind != DiffKind.CONTEXT) {
                val from = maxOf(0, index - CONTEXT_LINES)
                val to = minOf(lines.lastIndex, index + CONTEXT_LINES)
                for (i in from..to) keep[i] = true
            }
        }
        if (keep.all { it }) return lines

        val out = ArrayList<DiffLine>(lines.size)
        var skipped = 0
        lines.forEachIndexed { index, line ->
            if (keep[index]) {
                if (skipped > 0) {
                    out += DiffLine(DiffKind.GAP, "@@ $skipped unchanged line${if (skipped == 1) "" else "s"} @@")
                    skipped = 0
                }
                out += line
            } else {
                skipped++
            }
        }
        if (skipped > 0) {
            out += DiffLine(DiffKind.GAP, "@@ $skipped unchanged line${if (skipped == 1) "" else "s"} @@")
        }
        return out
    }

    /** Picks the best available representation from what the desktop sent. */
    fun forPayload(diff: String?, before: String?, after: String?): List<DiffLine>? = when {
        !diff.isNullOrBlank() -> fromUnified(diff)
        before != null && after != null -> between(before, after)
        else -> null
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/ui/capture/QuickCaptureSheet.kt`

```kotlin
package com.jarvis.assistant.ui.capture

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import com.jarvis.assistant.network.QuickNoteMessage
import com.jarvis.assistant.ui.theme.JarvisAmber
import com.jarvis.assistant.ui.theme.JarvisBlack
import com.jarvis.assistant.ui.theme.JarvisCyan
import com.jarvis.assistant.ui.theme.JarvisGreen
import com.jarvis.assistant.ui.theme.JarvisOutline
import com.jarvis.assistant.ui.theme.JarvisSurface
import com.jarvis.assistant.ui.theme.JarvisTextMuted

enum class CaptureTarget(val wire: String, val label: String) {
    LOGSEQ(QuickNoteMessage.TARGET_LOGSEQ, "Logseq Journal"),
    JOPLIN(QuickNoteMessage.TARGET_JOPLIN, "Joplin Vault"),
}

/**
 * Frictionless capture: open, type, send.
 *
 * The point is to outrun the thought, so the keyboard is up on arrival and the
 * send path never blocks on the network — an offline note is queued and
 * acknowledged rather than refused.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun QuickCaptureSheet(
    connected: Boolean,
    initialText: String = "",
    initialTarget: CaptureTarget = CaptureTarget.LOGSEQ,
    micActive: Boolean,
    micPermissionGranted: Boolean,
    queuedCount: Int,
    onSend: (CaptureTarget, String) -> Unit,
    onToggleMic: () -> Unit,
    onDismiss: () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val focusRequester = remember { FocusRequester() }

    var target by rememberSaveable(initialTarget) { mutableStateOf(initialTarget) }
    // Keyed on the seed so a fresh share replaces the field rather than
    // appending to whatever the last capture left behind.
    var text by rememberSaveable(initialText) { mutableStateOf(initialText) }

    LaunchedEffect(Unit) {
        // The sheet has to be laid out before the field can take focus.
        runCatching { focusRequester.requestFocus() }
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = JarvisBlack,
        scrimColor = JarvisBlack.copy(alpha = 0.7f),
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp)
                .navigationBarsPadding()
                .imePadding(),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = "QUICK CAPTURE",
                    style = MaterialTheme.typography.labelSmall,
                    color = JarvisTextMuted,
                    modifier = Modifier.weight(1f),
                )
                if (!connected) {
                    Text(
                        text = if (queuedCount > 0) "OFFLINE · $queuedCount QUEUED" else "OFFLINE",
                        style = MaterialTheme.typography.labelSmall,
                        color = JarvisAmber,
                    )
                }
            }

            Spacer(Modifier.height(10.dp))

            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                CaptureTarget.entries.forEachIndexed { index, option ->
                    SegmentedButton(
                        selected = target == option,
                        onClick = { target = option },
                        shape = SegmentedButtonDefaults.itemShape(
                            index = index,
                            count = CaptureTarget.entries.size,
                        ),
                        colors = SegmentedButtonDefaults.colors(
                            activeContainerColor = JarvisCyan.copy(alpha = 0.16f),
                            activeContentColor = JarvisCyan,
                            activeBorderColor = JarvisCyan,
                            inactiveContainerColor = JarvisSurface,
                            inactiveContentColor = JarvisTextMuted,
                            inactiveBorderColor = JarvisOutline,
                        ),
                    ) {
                        Text(option.label, style = MaterialTheme.typography.labelSmall)
                    }
                }
            }

            Spacer(Modifier.height(12.dp))

            OutlinedTextField(
                value = text,
                onValueChange = { text = it },
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 120.dp)
                    .focusRequester(focusRequester),
                placeholder = {
                    Text(
                        text = if (target == CaptureTarget.LOGSEQ) {
                            "Appends to today's journal"
                        } else {
                            "Creates a note in your vault"
                        },
                        style = MaterialTheme.typography.bodyMedium,
                    )
                },
                textStyle = MaterialTheme.typography.bodyMedium,
                keyboardOptions = KeyboardOptions(
                    capitalization = KeyboardCapitalization.Sentences,
                    imeAction = ImeAction.Default,
                ),
                shape = RoundedCornerShape(12.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = JarvisCyan,
                    unfocusedBorderColor = JarvisOutline,
                    focusedContainerColor = JarvisSurface,
                    unfocusedContainerColor = JarvisSurface,
                ),
            )

            Spacer(Modifier.height(12.dp))

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = onToggleMic,
                    enabled = micPermissionGranted,
                    modifier = Modifier.height(52.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (micActive) JarvisCyan else JarvisSurface,
                        contentColor = if (micActive) JarvisBlack else JarvisCyan,
                        disabledContainerColor = JarvisSurface,
                        disabledContentColor = JarvisTextMuted,
                    ),
                ) {
                    Text(
                        text = if (micActive) "STOP" else "TALK",
                        style = MaterialTheme.typography.labelSmall,
                    )
                }

                Spacer(Modifier.width(0.dp))

                Button(
                    onClick = {
                        onSend(target, text.trim())
                        text = ""
                        onDismiss()
                    },
                    enabled = text.isNotBlank(),
                    modifier = Modifier
                        .weight(1f)
                        .height(52.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = JarvisGreen.copy(alpha = 0.18f),
                        contentColor = JarvisGreen,
                        disabledContainerColor = JarvisSurface,
                        disabledContentColor = JarvisTextMuted,
                    ),
                ) {
                    Text(
                        text = if (connected) "Send to Jarvis" else "Queue for Jarvis",
                        style = MaterialTheme.typography.titleMedium,
                    )
                }
            }

            Spacer(Modifier.height(20.dp))
        }
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/ui/screens/HudScreen.kt`

```kotlin
package com.jarvis.assistant.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.minimumInteractiveComponentSize
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.jarvis.assistant.network.ApprovalRequestEvent
import com.jarvis.assistant.network.ConnectionState
import com.jarvis.assistant.network.DesktopTelemetryEvent
import com.jarvis.assistant.ui.approval.ApprovalCard
import com.jarvis.assistant.ui.theme.JarvisAmber
import com.jarvis.assistant.ui.theme.JarvisBlack
import com.jarvis.assistant.ui.theme.JarvisCyan
import com.jarvis.assistant.ui.theme.JarvisGreen
import com.jarvis.assistant.ui.theme.JarvisOutline
import com.jarvis.assistant.ui.theme.JarvisRed
import com.jarvis.assistant.ui.theme.JarvisSurface
import com.jarvis.assistant.ui.theme.JarvisTextMuted
import kotlin.math.roundToInt

/**
 * Everything the screen needs, hoisted into one immutable snapshot.
 *
 * [Immutable] is load-bearing and not decoration. `approvals` is a `List`, which
 * Compose treats as unstable because the interface carries no immutability
 * guarantee, and one unstable parameter makes the whole class unstable — under
 * strong skipping that means identity comparison, and this is rebuilt on every
 * recomposition, so nothing downstream could ever skip. Every telemetry frame
 * recomposed every visible approval card and its diff. The annotation is honest
 * here: the list is only ever replaced wholesale by the runtime, never mutated.
 */
@Immutable
data class HudState(
    val connection: ConnectionState,
    val serverAddress: String,
    val micActive: Boolean,
    val micPermissionGranted: Boolean,
    val desktop: DesktopTelemetryEvent?,
    val approvals: List<ApprovalRequestEvent>,
    val statusText: String?,
    val lastError: String?,
    /** True once Android has been told to stop dozing this app. */
    val batteryExempt: Boolean,
    /** Set when signing or the target address blocks an action outright. */
    val blockingError: String?,
    val hasSharedSecret: Boolean,
    val hasAuthToken: Boolean,
)

/** Stable so the callbacks do not invalidate every card that captures them. */
@Immutable
data class HudActions(
    val onServerAddressChange: (String) -> Unit,
    val onReconnect: () -> Unit,
    val onToggleMic: () -> Unit,
    val onApprove: (String) -> Unit,
    val onReject: (String) -> Unit,
    val onRequestBatteryExemption: () -> Unit,
    val onSharedSecretChange: (String) -> Unit,
    val onAuthTokenChange: (String) -> Unit,
)

@Composable
fun HudScreen(state: HudState, actions: HudActions, modifier: Modifier = Modifier) {
    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .background(JarvisBlack)
            .padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item(key = "header") {
            Spacer(Modifier.height(20.dp))
            ConnectionHeader(state.connection, state.lastError)
        }

        item(key = "server") {
            ServerAddressField(
                address = state.serverAddress,
                onCommit = actions.onServerAddressChange,
                onReconnect = actions.onReconnect,
            )
        }

        state.blockingError?.let { message ->
            item(key = "blocking-error") {
                WarningCard(text = message, actionLabel = null, onAction = null)
            }
        }

        item(key = "pairing") {
            SectionLabel("PAIRING")
            SecretField(
                label = "Signing secret",
                isSet = state.hasSharedSecret,
                onCommit = actions.onSharedSecretChange,
            )
            Spacer(Modifier.height(8.dp))
            SecretField(
                label = "Auth token (optional)",
                isSet = state.hasAuthToken,
                onCommit = actions.onAuthTokenChange,
            )
        }

        if (!state.batteryExempt) {
            item(key = "battery") {
                WarningCard(
                    text = "Android may sleep the link while locked. Allow unrestricted background battery usage.",
                    actionLabel = "Fix",
                    onAction = actions.onRequestBatteryExemption,
                )
            }
        }

        if (!state.micPermissionGranted) {
            item(key = "mic-permission") {
                WarningCard(
                    text = "Microphone access is denied, so voice input is unavailable.",
                    actionLabel = null,
                    onAction = null,
                )
            }
        }

        item(key = "desktop") {
            SectionLabel("DESKTOP")
            DesktopTelemetryRow(state.desktop)
        }

        if (state.approvals.isNotEmpty()) {
            item(key = "approvals-label") { SectionLabel("PENDING APPROVALS") }
            items(state.approvals, key = { it.id }) { request ->
                ApprovalCard(
                    request = request,
                    onApprove = { actions.onApprove(request.id) },
                    onReject = { actions.onReject(request.id) },
                    // A decision taken with the link down clears the card and buzzes
                    // "confirm" while nothing has been sent. Say so instead.
                    linkReady = state.connection == ConnectionState.CONNECTED &&
                        state.hasSharedSecret,
                )
            }
        }

        state.statusText?.let { status ->
            item(key = "status") {
                SectionLabel("STATUS")
                Text(
                    text = status,
                    style = MaterialTheme.typography.bodyMedium,
                    color = JarvisTextMuted,
                )
            }
        }

        item(key = "mic") {
            Spacer(Modifier.height(8.dp))
            MicButton(
                active = state.micActive,
                enabled = state.micPermissionGranted,
                onToggle = actions.onToggleMic,
            )
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun ConnectionHeader(state: ConnectionState, lastError: String?) {
    val (label, tint) = when (state) {
        ConnectionState.CONNECTED -> "CONNECTED" to JarvisGreen
        ConnectionState.RECONNECTING -> "RECONNECTING" to JarvisAmber
        ConnectionState.OFFLINE -> "OFFLINE" to JarvisRed
    }

    Column {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(10.dp)
                    .background(tint, CircleShape),
            )
            Spacer(Modifier.width(10.dp))
            Text(
                text = "JARVIS",
                style = MaterialTheme.typography.titleLarge,
                color = JarvisCyan,
            )
            Spacer(Modifier.width(10.dp))
            Text(
                text = label,
                style = MaterialTheme.typography.labelSmall,
                color = tint,
            )
        }
        if (state != ConnectionState.CONNECTED && !lastError.isNullOrBlank()) {
            Spacer(Modifier.height(4.dp))
            Text(
                text = lastError,
                style = MaterialTheme.typography.labelSmall,
                color = JarvisTextMuted,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun ServerAddressField(
    address: String,
    onCommit: (String) -> Unit,
    onReconnect: () -> Unit,
) {
    var draft by rememberSaveable(address) { mutableStateOf(address) }
    val keyboard = LocalSoftwareKeyboardController.current

    Row(verticalAlignment = Alignment.CenterVertically) {
        OutlinedTextField(
            value = draft,
            onValueChange = { draft = it },
            modifier = Modifier.weight(1f),
            singleLine = true,
            label = { Text("Desktop address", style = MaterialTheme.typography.labelSmall) },
            textStyle = MaterialTheme.typography.bodyMedium.copy(fontFamily = FontFamily.Monospace),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(
                onDone = {
                    keyboard?.hide()
                    onCommit(draft)
                },
            ),
            shape = RoundedCornerShape(10.dp),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = JarvisCyan,
                unfocusedBorderColor = JarvisOutline,
                focusedContainerColor = JarvisSurface,
                unfocusedContainerColor = JarvisSurface,
            ),
        )
        Spacer(Modifier.width(8.dp))
        Button(
            onClick = {
                keyboard?.hide()
                if (draft.trim() != address) onCommit(draft) else onReconnect()
            },
            shape = RoundedCornerShape(10.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = JarvisSurface,
                contentColor = JarvisCyan,
            ),
        ) {
            Text("Link", style = MaterialTheme.typography.labelSmall)
        }
    }
}

/**
 * Write-only: a stored secret is never read back into the UI, so a shoulder-surfer
 * or a screenshot cannot recover it. The field reports only whether one is set.
 */
@Composable
private fun SecretField(label: String, isSet: Boolean, onCommit: (String) -> Unit) {
    var draft by rememberSaveable { mutableStateOf("") }
    val keyboard = LocalSoftwareKeyboardController.current

    Row(verticalAlignment = Alignment.CenterVertically) {
        OutlinedTextField(
            value = draft,
            onValueChange = { draft = it },
            modifier = Modifier.weight(1f),
            singleLine = true,
            label = {
                Text(
                    text = if (isSet) "$label — set" else label,
                    style = MaterialTheme.typography.labelSmall,
                )
            },
            placeholder = {
                Text(
                    text = if (isSet) "Enter a new value to replace" else "Not set",
                    style = MaterialTheme.typography.labelSmall,
                )
            },
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Password,
                imeAction = ImeAction.Done,
            ),
            keyboardActions = KeyboardActions(
                onDone = {
                    keyboard?.hide()
                    onCommit(draft)
                    draft = ""
                },
            ),
            shape = RoundedCornerShape(10.dp),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = JarvisCyan,
                unfocusedBorderColor = if (isSet) JarvisGreen.copy(alpha = 0.5f) else JarvisAmber,
                focusedContainerColor = JarvisSurface,
                unfocusedContainerColor = JarvisSurface,
            ),
        )
        Spacer(Modifier.width(8.dp))
        Button(
            onClick = {
                keyboard?.hide()
                onCommit(draft)
                draft = ""
            },
            enabled = draft.isNotEmpty(),
            shape = RoundedCornerShape(10.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = JarvisSurface,
                contentColor = JarvisCyan,
                disabledContainerColor = JarvisSurface,
                disabledContentColor = JarvisTextMuted,
            ),
        ) {
            Text("Save", style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
private fun DesktopTelemetryRow(telemetry: DesktopTelemetryEvent?) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        StatTile("CPU", telemetry?.cpuPercent?.let { "${it.roundToInt()}%" }, Modifier.weight(1f))
        StatTile("GPU", telemetry?.gpuTempC?.let { "${it.roundToInt()}°C" }, Modifier.weight(1f))
        StatTile("VRAM", formatVram(telemetry), Modifier.weight(1f))
    }
}

private fun formatVram(telemetry: DesktopTelemetryEvent?): String? {
    val used = telemetry?.vramUsedMb ?: return null
    val total = telemetry.vramTotalMb
    return if (total != null && total > 0) {
        "${(used / 1024).roundToInt()}/${(total / 1024).roundToInt()}G"
    } else {
        "${used.roundToInt()}M"
    }
}

@Composable
private fun StatTile(label: String, value: String?, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .background(JarvisSurface, RoundedCornerShape(12.dp))
            .border(1.dp, JarvisOutline, RoundedCornerShape(12.dp))
            .padding(horizontal = 12.dp, vertical = 10.dp),
    ) {
        Text(label, style = MaterialTheme.typography.labelSmall, color = JarvisTextMuted)
        Spacer(Modifier.height(4.dp))
        Text(
            text = value ?: "—",
            style = MaterialTheme.typography.titleMedium,
            color = if (value == null) JarvisTextMuted else JarvisCyan,
            maxLines = 1,
        )
    }
}

@Composable
private fun WarningCard(text: String, actionLabel: String?, onAction: (() -> Unit)?) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(JarvisSurface, RoundedCornerShape(12.dp))
            .border(1.dp, JarvisAmber.copy(alpha = 0.3f), RoundedCornerShape(12.dp))
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.bodyMedium,
            color = JarvisTextMuted,
            modifier = Modifier.weight(1f),
        )
        if (actionLabel != null && onAction != null) {
            Spacer(Modifier.width(8.dp))
            Text(
                text = actionLabel,
                style = MaterialTheme.typography.labelSmall,
                color = JarvisAmber,
                modifier = Modifier
                    // A bare clickable Text is announced by TalkBack as static
                    // text, and at labelSmall the target is about 27dp tall. This
                    // is the only in-app route to the battery-exemption dialog.
                    .clickable(onClick = onAction, role = Role.Button)
                    .minimumInteractiveComponentSize()
                    .padding(horizontal = 10.dp, vertical = 6.dp),
            )
        }
    }
}

@Composable
private fun SectionLabel(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.labelSmall,
        color = JarvisTextMuted,
        modifier = Modifier.padding(top = 4.dp, bottom = 2.dp),
    )
}

@Composable
private fun MicButton(active: Boolean, enabled: Boolean, onToggle: () -> Unit) {
    val container: Color = if (active) JarvisCyan else JarvisSurface
    val content: Color = if (active) JarvisBlack else JarvisCyan

    Button(
        onClick = onToggle,
        enabled = enabled,
        modifier = Modifier
            .fillMaxWidth()
            .height(64.dp),
        shape = RoundedCornerShape(16.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = container,
            contentColor = content,
            disabledContainerColor = JarvisSurface,
            disabledContentColor = JarvisTextMuted,
        ),
    ) {
        Text(
            text = if (active) "LISTENING — TAP TO STOP" else "TAP TO TALK",
            style = MaterialTheme.typography.titleMedium,
        )
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/ui/theme/Theme.kt`

```kotlin
package com.jarvis.assistant.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/** True black: on AMOLED these pixels draw no current at all. */
val JarvisBlack = Color(0xFF000000)
val JarvisSurface = Color(0xFF0B0B0D)
val JarvisOutline = Color(0xFF1F2124)
val JarvisCyan = Color(0xFF22D3EE)
val JarvisAmber = Color(0xFFFBBF24)
val JarvisRed = Color(0xFFF87171)
val JarvisGreen = Color(0xFF34D399)
val JarvisTextPrimary = Color(0xFFE7E9EA)
val JarvisTextMuted = Color(0xFF8A9096)

private val JarvisColors = darkColorScheme(
    primary = JarvisCyan,
    onPrimary = JarvisBlack,
    secondary = JarvisCyan,
    onSecondary = JarvisBlack,
    background = JarvisBlack,
    onBackground = JarvisTextPrimary,
    surface = JarvisBlack,
    onSurface = JarvisTextPrimary,
    surfaceVariant = JarvisSurface,
    onSurfaceVariant = JarvisTextMuted,
    outline = JarvisOutline,
    error = JarvisRed,
    onError = JarvisBlack,
)

private val JarvisTypography = Typography(
    titleLarge = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 22.sp,
        letterSpacing = 0.4.sp,
    ),
    titleMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Medium,
        fontSize = 16.sp,
    ),
    bodyMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 14.sp,
        lineHeight = 20.sp,
    ),
    labelSmall = TextStyle(
        fontFamily = FontFamily.Monospace,
        fontSize = 11.sp,
        letterSpacing = 1.sp,
    ),
)

/**
 * Always dark. The HUD is meant to be readable at 3am without lighting the room,
 * so the system light theme is deliberately ignored.
 */
@Composable
fun JarvisTheme(
    @Suppress("UNUSED_PARAMETER") darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = JarvisColors,
        typography = JarvisTypography,
        content = content,
    )
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/widget/WidgetUi.kt`

```kotlin
package com.jarvis.assistant.widget

import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceModifier
import androidx.glance.action.Action
import androidx.glance.action.clickable
import androidx.glance.appwidget.cornerRadius
import androidx.glance.background
import androidx.glance.layout.Alignment
import androidx.glance.layout.Box
import androidx.glance.layout.padding
import androidx.glance.layout.size
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider
import com.jarvis.assistant.widget.theme.JarvisGlanceTheme

/**
 * Shared widget primitives.
 *
 * Glance's own Button renders through the platform's RemoteViews button, which
 * carries a light-theme background that fights an AMOLED card. A clickable Box
 * gives full control of the surface.
 *
 * Note that `cornerRadius` is a no-op below API 31; on 28-30 these render square,
 * which is cosmetic rather than broken.
 */
@Composable
fun PillButton(
    label: String,
    tint: ColorProvider,
    background: ColorProvider,
    onClick: Action,
    modifier: GlanceModifier = GlanceModifier,
) {
    Box(
        modifier = modifier
            .background(background)
            .cornerRadius(10.dp)
            .clickable(onClick)
            .padding(horizontal = 10.dp, vertical = 8.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text = label, style = TextStyle(color = tint, fontSize = 12.sp))
    }
}

@Composable
fun StatusDot(online: Boolean, size: Int = 10) {
    Box(
        modifier = GlanceModifier
            .size(size.dp)
            .background(if (online) JarvisGlanceTheme.StatusOk else JarvisGlanceTheme.StatusBad)
            .cornerRadius((size / 2).dp),
        contentAlignment = Alignment.Center,
    ) {}
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/widget/approval/ApprovalActionCallback.kt`

```kotlin
package com.jarvis.assistant.widget.approval

import android.content.Context
import androidx.glance.GlanceId
import androidx.glance.action.ActionParameters
import androidx.glance.appwidget.action.ActionCallback
import androidx.glance.appwidget.updateAll
import com.jarvis.assistant.JarvisRuntime

/**
 * Home-screen decisions go through the same signing path as every other surface.
 *
 * This deliberately does not build its own HMAC. A second signing implementation
 * is a second thing to keep in step with the desktop's verifier, and the one in
 * [JarvisRuntime.submitApprovalDecision] is already fail-closed, nonce-bearing,
 * queued when offline, and pinned by unit tests.
 */
class ApprovalActionCallback : ActionCallback {

    override suspend fun onAction(
        context: Context,
        glanceId: GlanceId,
        parameters: ActionParameters,
    ) {
        val id = parameters[PARAM_ID] ?: return
        val approved = parameters[PARAM_DECISION] ?: return

        // The callback is already suspending and the system holds a wakelock for
        // its duration. Detaching onto a bare CoroutineScope here would let the
        // process be reaped mid-send, losing the decision.
        JarvisRuntime.initialize(context)
        JarvisRuntime.submitApprovalDecision(id, approved)

        // submitApprovalDecision leaves the request pending when it cannot sign,
        // so redraw either way: the widget shows the next item, or the reason.
        ApprovalWidget().updateAll(context)
    }

    companion object {
        val PARAM_ID = ActionParameters.Key<String>("approval_id")
        val PARAM_DECISION = ActionParameters.Key<Boolean>("approval_decision")
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/widget/approval/ApprovalWidget.kt`

```kotlin
package com.jarvis.assistant.widget.approval

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.action.actionParametersOf
import androidx.glance.action.actionStartActivity
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.action.actionRunCallback
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.layout.Alignment
import androidx.glance.layout.Box
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.layout.width
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import com.jarvis.assistant.MainActivity
import com.jarvis.assistant.data.repository.WidgetDataRepository
import com.jarvis.assistant.widget.PillButton
import com.jarvis.assistant.widget.StatusDot
import com.jarvis.assistant.widget.theme.JarvisGlanceTheme

/** The oldest unresolved `ask` request, with the decision buttons attached. */
class ApprovalWidget : GlanceAppWidget() {

    override val sizeMode: SizeMode = SizeMode.Exact

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val pending = WidgetDataRepository.getPendingApprovals()
        val unpaired = WidgetDataRepository.isUnpaired()
        val deliverable = WidgetDataRepository.canDecideNow()
        val extra = (pending.size - 1).coerceAtLeast(0)

        provideContent {
            Box(
                modifier = GlanceModifier
                    .fillMaxSize()
                    .background(JarvisGlanceTheme.Background)
                    .cornerRadius(16.dp)
                    .padding(12.dp),
            ) {
                when {
                    pending.isEmpty() -> EmptyState()
                    unpaired -> UnpairedState()
                    // The runtime refuses to sign a decision it cannot deliver, so
                    // buttons here would buzz and do nothing.
                    !deliverable -> OfflineState()
                    else -> ActiveApproval(pending.first(), extra)
                }
            }
        }
    }

    @Composable
    private fun EmptyState() {
        Row(
            modifier = GlanceModifier.fillMaxSize(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            StatusDot(online = true, size = 8)
            Spacer(GlanceModifier.width(8.dp))
            Text(
                text = "Systems nominal · No pending approvals",
                style = TextStyle(
                    color = JarvisGlanceTheme.TextMuted,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                ),
            )
        }
    }

    /**
     * Signing is impossible without a secret, so the widget says so rather than
     * showing buttons that would silently refuse.
     */
    @Composable
    private fun UnpairedState() {
        Column(
            modifier = GlanceModifier
                .fillMaxSize()
                .clickable(actionStartActivity<MainActivity>()),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "Approvals need a pairing secret",
                style = TextStyle(
                    color = JarvisGlanceTheme.StatusBad,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                ),
            )
            Spacer(GlanceModifier.height(2.dp))
            Text("Tap to set one in the HUD", style = JarvisGlanceTheme.Label)
        }
    }

    /**
     * Pending approvals exist but the link is down.
     *
     * Showing Approve and Deny here would be a tap that appears to answer and does
     * not: the decision cannot be signed and delivered while the event stream is
     * stale, so the widget names the reason and opens the HUD instead.
     */
    @Composable
    private fun OfflineState() {
        Column(
            modifier = GlanceModifier
                .fillMaxSize()
                .clickable(actionStartActivity<MainActivity>()),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "Approvals pending — desktop unreachable",
                style = TextStyle(
                    color = JarvisGlanceTheme.StatusBad,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                ),
            )
            Spacer(GlanceModifier.height(2.dp))
            Text("Tap to open the HUD and reconnect", style = JarvisGlanceTheme.Label)
        }
    }

    @Composable
    private fun ActiveApproval(item: WidgetDataRepository.ApprovalItem, extra: Int) {
        Column(modifier = GlanceModifier.fillMaxSize()) {
            Row(
                modifier = GlanceModifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "Jarvis wants to:",
                    style = TextStyle(
                        color = JarvisGlanceTheme.Primary,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                    ),
                )
                Spacer(GlanceModifier.defaultWeight())
                item.target?.let {
                    Badge(it, JarvisGlanceTheme.Primary)
                    Spacer(GlanceModifier.width(4.dp))
                }
                Badge(item.tier.uppercase(), JarvisGlanceTheme.AccentGold)
            }

            Spacer(GlanceModifier.height(4.dp))

            Text(text = item.action, maxLines = 1, style = JarvisGlanceTheme.Title)

            Text(
                text = item.detail,
                maxLines = 2,
                modifier = GlanceModifier.defaultWeight(),
                style = TextStyle(color = JarvisGlanceTheme.TextMuted, fontSize = 11.sp),
            )

            if (extra > 0) {
                Text(
                    text = "+$extra more waiting",
                    style = TextStyle(color = JarvisGlanceTheme.AccentGold, fontSize = 10.sp),
                )
                Spacer(GlanceModifier.height(4.dp))
            }

            Row(modifier = GlanceModifier.fillMaxWidth()) {
                PillButton(
                    label = "Approve",
                    tint = JarvisGlanceTheme.StatusOk,
                    background = JarvisGlanceTheme.SurfaceRaised,
                    onClick = actionRunCallback<ApprovalActionCallback>(
                        actionParametersOf(
                            ApprovalActionCallback.PARAM_ID to item.id,
                            ApprovalActionCallback.PARAM_DECISION to true,
                        ),
                    ),
                    modifier = GlanceModifier.defaultWeight(),
                )
                Spacer(GlanceModifier.width(8.dp))
                PillButton(
                    label = "Deny",
                    tint = JarvisGlanceTheme.StatusBad,
                    background = JarvisGlanceTheme.SurfaceRaised,
                    onClick = actionRunCallback<ApprovalActionCallback>(
                        actionParametersOf(
                            ApprovalActionCallback.PARAM_ID to item.id,
                            ApprovalActionCallback.PARAM_DECISION to false,
                        ),
                    ),
                    modifier = GlanceModifier.defaultWeight(),
                )
            }
        }
    }

    @Composable
    private fun Badge(label: String, tint: androidx.glance.unit.ColorProvider) {
        Box(
            modifier = GlanceModifier
                .background(JarvisGlanceTheme.SurfaceRaised)
                .cornerRadius(4.dp)
                .padding(horizontal = 6.dp, vertical = 2.dp),
        ) {
            Text(
                text = label,
                style = TextStyle(color = tint, fontSize = 10.sp, fontWeight = FontWeight.Bold),
            )
        }
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/widget/approval/ApprovalWidgetReceiver.kt`

```kotlin
package com.jarvis.assistant.widget.approval

import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver

class ApprovalWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = ApprovalWidget()
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/widget/launcher/QuickLauncherReceiver.kt`

```kotlin
package com.jarvis.assistant.widget.launcher

import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver

class QuickLauncherReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = QuickLauncherWidget()
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/widget/launcher/QuickLauncherWidget.kt`

```kotlin
package com.jarvis.assistant.widget.launcher

import android.content.Context
import android.content.Intent
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.action.Action
import androidx.glance.action.actionStartActivity
import androidx.glance.appwidget.action.actionStartActivity as actionStartActivityIntent
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.layout.Alignment
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.padding
import androidx.glance.layout.width
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import com.jarvis.assistant.MainActivity
import com.jarvis.assistant.data.repository.WidgetDataRepository
import com.jarvis.assistant.widget.PillButton
import com.jarvis.assistant.widget.StatusDot
import com.jarvis.assistant.widget.theme.JarvisGlanceTheme

/** Link status plus the four things worth reaching without opening the app. */
class QuickLauncherWidget : GlanceAppWidget() {

    override val sizeMode: SizeMode = SizeMode.Exact

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        // Deliberately does not probe latency here. Doing so was a feedback loop:
        // the pong wrote a new round-trip time, the repository observed it and
        // called updateAll, which re-ran this function, which probed again. Round
        // trips jitter by a millisecond nearly every time, so nothing upstream
        // conflated it away. The value shown is whatever the last connect or the
        // last real traffic measured.
        val status = WidgetDataRepository.getConnectionStatus()

        provideContent {
            Row(
                modifier = GlanceModifier
                    .fillMaxSize()
                    .background(JarvisGlanceTheme.Background)
                    .cornerRadius(24.dp)
                    .padding(horizontal = 14.dp, vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                StatusDot(online = status.online)
                Spacer(GlanceModifier.width(8.dp))
                Text(
                    text = when {
                        !status.online -> "Offline"
                        status.latencyMs != null -> "${status.latencyMs}ms"
                        else -> "Linked"
                    },
                    style = TextStyle(
                        color = JarvisGlanceTheme.TextMuted,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Medium,
                    ),
                )

                Spacer(GlanceModifier.defaultWeight())

                ActionPill("Mic", JarvisGlanceTheme.Primary, route(context, MainActivity.ACTION_START_VOICE))
                Spacer(GlanceModifier.width(6.dp))
                ActionPill("#log", JarvisGlanceTheme.TextPrimary, capture(context, "logseq"))
                Spacer(GlanceModifier.width(6.dp))
                ActionPill("#joplin", JarvisGlanceTheme.TextPrimary, capture(context, "joplin"))
                Spacer(GlanceModifier.width(6.dp))
                ActionPill("HUD", JarvisGlanceTheme.TextMuted, actionStartActivity<MainActivity>())
            }
        }
    }

    @Composable
    private fun ActionPill(label: String, tint: androidx.glance.unit.ColorProvider, onClick: Action) {
        PillButton(
            label = label,
            tint = tint,
            background = JarvisGlanceTheme.SurfaceRaised,
            onClick = onClick,
        )
    }

    private fun route(context: Context, action: String): Action =
        actionStartActivityIntent(
            Intent(context, MainActivity::class.java)
                .setAction(action)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
        )

    private fun capture(context: Context, target: String): Action =
        actionStartActivityIntent(
            Intent(context, MainActivity::class.java)
                .setAction(MainActivity.ACTION_QUICK_CAPTURE)
                .putExtra(MainActivity.EXTRA_CAPTURE_TARGET, target)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
        )
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/widget/telemetry/TelemetryReceiver.kt`

```kotlin
package com.jarvis.assistant.widget.telemetry

import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver

class TelemetryReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = TelemetryWidget()
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/widget/telemetry/TelemetryWidget.kt`

```kotlin
package com.jarvis.assistant.widget.telemetry

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.action.actionStartActivity
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.layout.Alignment
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.layout.width
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider
import com.jarvis.assistant.MainActivity
import com.jarvis.assistant.data.repository.WidgetDataRepository
import com.jarvis.assistant.widget.theme.JarvisGlanceTheme
import kotlin.math.roundToInt

/** Desktop vitals from `desktop_telemetry` frames. */
class TelemetryWidget : GlanceAppWidget() {

    override val sizeMode: SizeMode = SizeMode.Exact

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val snapshot = WidgetDataRepository.getTelemetry()

        provideContent {
            Column(
                modifier = GlanceModifier
                    .fillMaxSize()
                    .background(JarvisGlanceTheme.Background)
                    .cornerRadius(16.dp)
                    .clickable(actionStartActivity<MainActivity>())
                    .padding(12.dp),
            ) {
                Row(
                    modifier = GlanceModifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text("WORKSTATION", style = JarvisGlanceTheme.Label)
                    Spacer(GlanceModifier.defaultWeight())
                    Text(
                        text = if (snapshot.isOnline) "LIVE" else "OFFLINE",
                        style = TextStyle(
                            color = if (snapshot.isOnline) {
                                JarvisGlanceTheme.StatusOk
                            } else {
                                JarvisGlanceTheme.StatusBad
                            },
                            fontSize = 9.sp,
                            fontWeight = FontWeight.Bold,
                        ),
                    )
                }

                Spacer(GlanceModifier.height(8.dp))

                if (!snapshot.hasData) {
                    Text(
                        text = if (snapshot.isOnline) "Awaiting telemetry" else "Desktop offline",
                        style = TextStyle(color = JarvisGlanceTheme.TextMuted, fontSize = 12.sp),
                    )
                    return@Column
                }

                val hot = (snapshot.gpuTempC ?: 0) >= WidgetDataRepository.GPU_WARN_C
                Metric(
                    label = "GPU",
                    value = snapshot.gpuTempC?.let { "$it°C" } ?: "—",
                    tint = if (hot) JarvisGlanceTheme.StatusBad else JarvisGlanceTheme.Primary,
                    // Stale numbers styled as live numbers is the failure mode
                    // worth avoiding on an always-visible surface.
                    stale = !snapshot.isOnline,
                )
                Spacer(GlanceModifier.height(6.dp))
                val vramTight = isVramTight(snapshot.vramUsedMb, snapshot.vramTotalMb)
                Metric(
                    label = "VRAM",
                    value = formatVram(snapshot.vramUsedMb, snapshot.vramTotalMb),
                    tint = if (vramTight) {
                        JarvisGlanceTheme.StatusBad
                    } else {
                        JarvisGlanceTheme.TextPrimary
                    },
                    stale = !snapshot.isOnline,
                )
                Spacer(GlanceModifier.height(6.dp))
                val cpuBusy = (snapshot.cpuPercent ?: 0) >= WidgetDataRepository.CPU_WARN_PERCENT
                Metric(
                    label = "CPU",
                    value = snapshot.cpuPercent?.let { "$it%" } ?: "—",
                    tint = if (cpuBusy) {
                        JarvisGlanceTheme.StatusBad
                    } else {
                        JarvisGlanceTheme.TextPrimary
                    },
                    stale = !snapshot.isOnline,
                )

                Spacer(GlanceModifier.defaultWeight())

                val cloud = snapshot.routeLane.equals("cloud", ignoreCase = true)
                Text(
                    text = buildString {
                        append(if (cloud) "Cloud" else "Local")
                        snapshot.model?.let { append(": ").append(it) }
                    },
                    maxLines = 1,
                    style = TextStyle(
                        color = if (cloud) JarvisGlanceTheme.AccentGold else JarvisGlanceTheme.StatusOk,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Medium,
                    ),
                )
            }
        }
    }

    @Composable
    private fun Metric(label: String, value: String, tint: ColorProvider, stale: Boolean) {
        Row(
            modifier = GlanceModifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(label, style = JarvisGlanceTheme.Label)
            Spacer(GlanceModifier.defaultWeight())
            Text(
                text = value,
                maxLines = 1,
                style = TextStyle(
                    color = if (stale) JarvisGlanceTheme.TextMuted else tint,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold,
                ),
            )
        }
    }

    private fun isVramTight(usedMb: Int?, totalMb: Int?): Boolean {
        if (usedMb == null || totalMb == null || totalMb <= 0) return false
        return usedMb.toDouble() / totalMb >= WidgetDataRepository.VRAM_WARN_FRACTION
    }

    private fun formatVram(usedMb: Int?, totalMb: Int?): String {
        if (usedMb == null) return "—"
        val used = (usedMb / 1024.0 * 10).roundToInt() / 10.0
        if (totalMb == null || totalMb <= 0) return "$used GB"
        val total = (totalMb / 1024.0 * 10).roundToInt() / 10.0
        return "$used / $total GB"
    }
}
```

## `jarvis-android/app/src/main/java/com/jarvis/assistant/widget/theme/JarvisGlanceTheme.kt`

```kotlin
package com.jarvis.assistant.widget.theme

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceModifier
import androidx.glance.background
import androidx.glance.unit.ColorProvider
import androidx.glance.text.FontWeight
import androidx.glance.text.TextStyle

/**
 * Widget palette.
 *
 * Home screens sit on the user's own wallpaper, so widgets use a near-black
 * surface rather than the HUD's true black: a pure #000000 card reads as a hole
 * punched in the wallpaper, while the app's own full-screen background does not.
 */
object JarvisGlanceTheme {
    val Background = ColorProvider(Color(0xFF04070C))
    val Surface = ColorProvider(Color(0xFF0A1119))
    val SurfaceRaised = ColorProvider(Color(0xFF121A24))
    val Line = ColorProvider(Color(0xFF172836))
    val Primary = ColorProvider(Color(0xFF6FE3FF))
    val AccentGold = ColorProvider(Color(0xFFFFB648))
    val StatusOk = ColorProvider(Color(0xFF3DDC97))
    val StatusWarn = ColorProvider(Color(0xFFFFB648))
    val StatusBad = ColorProvider(Color(0xFFFF6B7A))
    val TextPrimary = ColorProvider(Color(0xFFCFE4EE))
    val TextMuted = ColorProvider(Color(0xFF6B8496))

    val Label = TextStyle(color = TextMuted, fontSize = 10.sp, fontWeight = FontWeight.Medium)
    val Body = TextStyle(color = TextPrimary, fontSize = 12.sp)
    val Title = TextStyle(color = TextPrimary, fontSize = 13.sp, fontWeight = FontWeight.Bold)
    val Metric = TextStyle(color = Primary, fontSize = 17.sp, fontWeight = FontWeight.Bold)
}

fun GlanceModifier.appWidgetBackground(): GlanceModifier =
    this.background(JarvisGlanceTheme.Background)
```

## `jarvis-android/app/src/test/java/com/jarvis/assistant/ApprovalSignerTest.kt`

```kotlin
package com.jarvis.assistant

import com.jarvis.assistant.notifications.ApprovalSigner
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Test
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

class ApprovalSignerTest {

    private val secret = "pairing-secret"

    private fun reference(payload: String): String {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(secret.toByteArray(Charsets.UTF_8), "HmacSHA256"))
        return mac.doFinal(payload.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
    }

    @Test
    fun `signs the documented canonical payload`() {
        val signature = ApprovalSigner.sign(
            secret = secret,
            id = "req-1",
            approved = true,
            deviceId = "device-9",
            atMs = 1_726_200_000_000,
            nonce = "nonce-abc",
        )
        assertEquals(reference("req-1|true|device-9|1726200000000|nonce-abc"), signature)
    }

    /** Pinned so a refactor cannot silently change what the desktop must verify. */
    @Test
    fun `signature is stable lowercase hex of the expected length`() {
        val signature = ApprovalSigner.sign(secret, "r", false, "d", 1, "n")
        assertEquals(64, signature!!.length)
        assertEquals(signature.lowercase(), signature)
    }

    @Test
    fun `approved flag is part of the signature`() {
        val yes = ApprovalSigner.sign(secret, "r", true, "d", 1, "n")
        val no = ApprovalSigner.sign(secret, "r", false, "d", 1, "n")
        assertNotEquals(yes, no)
    }

    @Test
    fun `nonce is part of the signature`() {
        val first = ApprovalSigner.sign(secret, "r", true, "d", 1, "n1")
        val second = ApprovalSigner.sign(secret, "r", true, "d", 1, "n2")
        assertNotEquals(first, second)
    }

    /** The fail-closed contract: no secret means no signature, not an empty one. */
    @Test
    fun `returns null rather than an empty signature when unpaired`() {
        assertNull(ApprovalSigner.sign("", "r", true, "d", 1, "n"))
    }
}
```

## `jarvis-android/app/src/test/java/com/jarvis/assistant/CleartextTargetTest.kt`

```kotlin
package com.jarvis.assistant

import com.jarvis.assistant.data.JarvisSettings
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Pins the plaintext-target guard.
 *
 * Android's network security config cannot express 100.64.0.0/10, so this check
 * is the only thing standing between a mistyped address and the bearer token,
 * every approval and the microphone uplink going to a public host in the clear.
 * It is worth testing adversarially rather than only for the happy path.
 */
class CleartextTargetTest {

    @Test
    fun `userinfo cannot masquerade as the host`() {
        // The authority is 100.64.0.1:8080@evil.com. Splitting on ':' before '@'
        // reads the userinfo as the host and waves a public target through, while
        // OkHttp dials evil.com.
        assertEquals("evil.com", JarvisSettings.hostOf("ws://100.64.0.1:8080@evil.com/api/mobile/ws"))
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://100.64.0.1:8080@evil.com/api/mobile/ws"))
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://desktop.ts.net@evil.com/api/mobile/ws"))
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://10.0.0.1@evil.com/"))
    }

    @Test
    fun `private targets are still permitted`() {
        assertTrue(JarvisSettings.isCleartextTargetPrivate("ws://100.64.0.1:4719/api/mobile/ws"))
        assertTrue(JarvisSettings.isCleartextTargetPrivate("ws://100.127.255.254/"))
        assertTrue(JarvisSettings.isCleartextTargetPrivate("ws://10.0.0.5:4719/"))
        assertTrue(JarvisSettings.isCleartextTargetPrivate("ws://192.168.1.20:4719/"))
        assertTrue(JarvisSettings.isCleartextTargetPrivate("ws://172.16.0.1/"))
        assertTrue(JarvisSettings.isCleartextTargetPrivate("ws://127.0.0.1:4719/"))
        assertTrue(JarvisSettings.isCleartextTargetPrivate("ws://localhost:4719/"))
        assertTrue(JarvisSettings.isCleartextTargetPrivate("ws://desktop.tail1234.ts.net/api/mobile/ws"))
        assertTrue(JarvisSettings.isCleartextTargetPrivate("ws://desktop.local/"))
    }

    @Test
    fun `public and near-miss targets are refused`() {
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://example.com/"))
        // Suffix matching without the dot: these are registrable public domains.
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://notmyts.net/"))
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://ts.net/"))
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://evil-local/"))
        // Outside the CGNAT block, which is 100.64/10 and not all of 100/8.
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://100.128.0.1/"))
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://100.63.255.255/"))
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://172.32.0.1/"))
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://11.0.0.1/"))
    }

    @Test
    fun `tls targets are always permitted`() {
        assertTrue(JarvisSettings.isCleartextTargetPrivate("wss://example.com/api/mobile/ws"))
    }

    @Test
    fun `an unparseable target fails closed`() {
        assertNull(JarvisSettings.hostOf("not a url"))
        assertNull(JarvisSettings.hostOf("ws://"))
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws://"))
        assertFalse(JarvisSettings.isCleartextTargetPrivate("ws:// spaces /"))
    }

    @Test
    fun `ipv6 literals keep their brackets out of the host`() {
        assertEquals("::1", JarvisSettings.hostOf("ws://[::1]:4719/api/mobile/ws"))
        assertTrue(JarvisSettings.isCleartextTargetPrivate("ws://[::1]:4719/api/mobile/ws"))
    }

    @Test
    fun `normalization appends the endpoint path only when absent`() {
        assertEquals(
            "ws://100.64.0.1:4719/api/mobile/ws",
            JarvisSettings.normalizeToWebSocketUrl("100.64.0.1:4719"),
        )
        assertEquals(
            "wss://desk.ts.net/api/mobile/ws",
            JarvisSettings.normalizeToWebSocketUrl("https://desk.ts.net"),
        )
        assertEquals(
            "ws://desk.ts.net/custom",
            JarvisSettings.normalizeToWebSocketUrl("ws://desk.ts.net/custom"),
        )
    }
}
```

## `jarvis-android/app/src/test/java/com/jarvis/assistant/NoteDiffTest.kt`

````kotlin
package com.jarvis.assistant

import com.jarvis.assistant.ui.approval.DiffKind
import com.jarvis.assistant.ui.approval.Markdown
import com.jarvis.assistant.ui.approval.MdBlock
import com.jarvis.assistant.ui.approval.NoteDiff
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class NoteDiffTest {

    @Test
    fun `identical documents produce no changes`() {
        val lines = NoteDiff.between("a\nb\nc", "a\nb\nc")
        assertTrue(NoteDiff.summarize(lines).isEmpty)
    }

    @Test
    fun `a single edited line is one addition and one removal`() {
        val lines = NoteDiff.between("one\ntwo\nthree", "one\nTWO\nthree")
        val summary = NoteDiff.summarize(lines)
        assertEquals(1, summary.added)
        assertEquals(1, summary.removed)
        assertTrue(lines.any { it.kind == DiffKind.ADDED && it.text == "TWO" })
        assertTrue(lines.any { it.kind == DiffKind.REMOVED && it.text == "two" })
    }

    @Test
    fun `appended lines are additions only`() {
        val lines = NoteDiff.between("a", "a\nb\nc")
        val summary = NoteDiff.summarize(lines)
        assertEquals(2, summary.added)
        assertEquals(0, summary.removed)
    }

    /** A one-line change in a long note must not render the whole note. */
    @Test
    fun `long unchanged runs collapse into a gap marker`() {
        val before = (1..80).joinToString("\n") { "line $it" }
        val after = before.replace("line 40", "line forty")
        val lines = NoteDiff.between(before, after)

        assertTrue(lines.any { it.kind == DiffKind.GAP })
        assertTrue("rendered ${lines.size} rows for an 80-line note", lines.size < 20)
    }

    @Test
    fun `oversized documents degrade to a whole-body replacement`() {
        val before = (1..NoteDiff.MAX_LINES + 5).joinToString("\n") { "a$it" }
        val after = (1..NoteDiff.MAX_LINES + 5).joinToString("\n") { "b$it" }
        val lines = NoteDiff.between(before, after)
        assertTrue(lines.none { it.kind == DiffKind.CONTEXT })
    }

    @Test
    fun `unified diff from the desktop is parsed`() {
        val lines = NoteDiff.fromUnified(
            """
            --- a/note.md
            +++ b/note.md
            @@ -1,3 +1,3 @@
             keep
            -gone
            +added
            """.trimIndent(),
        )
        val summary = NoteDiff.summarize(lines)
        assertEquals(1, summary.added)
        assertEquals(1, summary.removed)
        assertTrue(lines.none { it.text.startsWith("+++") || it.text.startsWith("---") })
    }

    @Test
    fun `a desktop-supplied diff wins over reconstructing one`() {
        val chosen = NoteDiff.forPayload(
            diff = "@@\n+from desktop",
            before = "x",
            after = "y",
        )
        assertTrue(chosen!!.any { it.text == "from desktop" })
    }

    @Test
    fun `markdown parses the constructs notes actually use`() {
        val blocks = Markdown.parse(
            """
            # Heading
            Some **bold** and `code`.

            - first
            - second

            ```kotlin
            val x = 1
            ```
            """.trimIndent(),
        )
        assertTrue(blocks.any { it is MdBlock.Heading && it.level == 1 })
        assertTrue(blocks.any { it is MdBlock.CodeBlock && it.language == "kotlin" })
        assertEquals(2, blocks.count { it is MdBlock.ListItem })

        val paragraph = blocks.filterIsInstance<MdBlock.Paragraph>().first()
        assertTrue(paragraph.spans.any { it.bold && it.text == "bold" })
        assertTrue(paragraph.spans.any { it.code && it.text == "code" })
    }

    /** An unmatched marker must stay literal, not swallow the rest of the line. */
    @Test
    fun `unbalanced emphasis does not eat the line`() {
        val spans = Markdown.parseInline("2 * 3 is six")
        assertEquals("2 * 3 is six", spans.joinToString("") { it.text })
    }

    @Test
    fun `logseq block properties are dropped`() {
        val blocks = Markdown.parse("- a task\n  id:: 66f1-2b\n  collapsed:: true")
        assertEquals(1, blocks.size)
    }
}
````

## `jarvis-android/app/src/test/java/com/jarvis/assistant/QuickNoteSerializationTest.kt`

```kotlin
package com.jarvis.assistant

import com.jarvis.assistant.network.ApprovalRequestEvent
import com.jarvis.assistant.network.InboundEvent
import com.jarvis.assistant.network.JarvisJson
import com.jarvis.assistant.network.OutboundMessage
import com.jarvis.assistant.network.QuickNoteMessage
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class QuickNoteSerializationTest {

    @Test
    fun `quick_note serializes to the documented wire frame`() {
        val json = JarvisJson.encodeToString(
            OutboundMessage.serializer(),
            QuickNoteMessage(
                target = "logseq",
                mode = "append",
                content = "Captured text...",
                timestampMs = 1_726_200_000_000,
            ),
        )
        assertTrue(json, json.contains("\"type\":\"quick_note\""))
        assertTrue(json, json.contains("\"target\":\"logseq\""))
        assertTrue(json, json.contains("\"mode\":\"append\""))
        assertTrue(json, json.contains("\"content\":\"Captured text...\""))
        assertTrue(json, json.contains("\"timestamp_ms\":1726200000000"))
    }

    @Test
    fun `quick_note round-trips`() {
        val original = QuickNoteMessage("joplin", "create", "Body\nwith newline", 42L)
        val encoded = JarvisJson.encodeToString(OutboundMessage.serializer(), original)
        val decoded = JarvisJson.decodeFromString(OutboundMessage.serializer(), encoded)
        assertEquals(original, decoded)
    }

    @Test
    fun `note approval_request deserializes with its payload`() {
        val frame = """
            {"type":"approval_request","id":"a1","title":"Edit note",
             "action":"edit_joplin_note",
             "note":{"target":"joplin","title":"Ideas","before":"one\ntwo","after":"one\nthree"}}
        """.trimIndent()

        val event = JarvisJson.decodeFromString(InboundEvent.serializer(), frame)
        assertTrue(event is ApprovalRequestEvent)
        event as ApprovalRequestEvent

        assertTrue(event.isNoteEdit)
        assertEquals("joplin", event.note?.target)
        assertTrue(event.note!!.isJoplin)
        assertEquals("Ideas", event.note?.title)
    }

    @Test
    fun `logseq page action counts as a note edit without a payload`() {
        val frame = """{"type":"approval_request","id":"a2","action":"edit_logseq_page"}"""
        val event = JarvisJson.decodeFromString(InboundEvent.serializer(), frame)
            as ApprovalRequestEvent
        assertTrue(event.isNoteEdit)
        assertNull(event.note)
    }

    @Test
    fun `a shell approval is not treated as a note edit`() {
        val frame = """{"type":"approval_request","id":"a3","action":"shell"}"""
        val event = JarvisJson.decodeFromString(InboundEvent.serializer(), frame)
            as ApprovalRequestEvent
        assertTrue(!event.isNoteEdit)
    }
}
```

## `jarvis-android/app/src/test/java/com/jarvis/assistant/TelemetryProtocolTest.kt`

```kotlin
package com.jarvis.assistant

import com.jarvis.assistant.network.DesktopTelemetryEvent
import com.jarvis.assistant.network.InboundEvent
import com.jarvis.assistant.network.JarvisJson
import com.jarvis.assistant.network.OutboundMessage
import com.jarvis.assistant.network.PingMessage
import com.jarvis.assistant.network.PongEvent
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TelemetryProtocolTest {

    @Test
    fun `desktop_telemetry carries the model route`() {
        val frame = """
            {"type":"desktop_telemetry","cpu_percent":41.7,"gpu_temp_c":78.0,
             "vram_used_mb":5939.2,"vram_total_mb":8192.0,
             "route_lane":"cloud","model":"jarvis-escalate"}
        """.trimIndent()

        val event = JarvisJson.decodeFromString(InboundEvent.serializer(), frame)
            as DesktopTelemetryEvent

        assertEquals("jarvis-escalate", event.model)
        assertTrue(event.isCloudRoute)
        assertEquals(78, event.gpuTempC!!.toInt())
    }

    @Test
    fun `a telemetry frame without a route still decodes`() {
        val frame = """{"type":"desktop_telemetry","cpu_percent":12.0}"""
        val event = JarvisJson.decodeFromString(InboundEvent.serializer(), frame)
            as DesktopTelemetryEvent
        assertNull(event.model)
        assertFalse(event.isCloudRoute)
    }

    @Test
    fun `ping serializes with the timestamp the pong must echo`() {
        val json = JarvisJson.encodeToString(OutboundMessage.serializer(), PingMessage(1234L))
        assertTrue(json, json.contains("\"type\":\"ping\""))
        assertTrue(json, json.contains("\"sent_at_ms\":1234"))
    }

    @Test
    fun `pong round-trips the timestamp`() {
        val event = JarvisJson.decodeFromString(
            InboundEvent.serializer(),
            """{"type":"pong","sent_at_ms":98765}""",
        ) as PongEvent
        assertEquals(98765L, event.sentAtMs)
    }
}
```

## `jarvis-client/app/src/main/java/com/jarvis/client/JarvisApp.kt`

```kotlin
package com.jarvis.client

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import androidx.core.content.ContextCompat
import com.jarvis.client.service.EventService

class JarvisApp : Application() {
    override fun onCreate() {
        super.onCreate()
        val manager = ContextCompat.getSystemService(this, NotificationManager::class.java)
        manager?.createNotificationChannel(
            NotificationChannel(
                EventService.CHANNEL_ID,
                getString(R.string.channel_link_name),
                // IMPORTANCE_LOW: the link notification is a status line, not an
                // alert. Approvals get their own channel when step 4 lands.
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = getString(R.string.channel_link_desc)
                setShowBadge(false)
            },
        )
    }
}
```

## `jarvis-client/app/src/main/java/com/jarvis/client/MainActivity.kt`

```kotlin
package com.jarvis.client

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBars
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.client.platform.PlatformReadiness
import com.jarvis.client.platform.ReadinessItem
import com.jarvis.client.service.EventService

private val Void = Color(0xFF05070B)
private val Plate = Color(0xFF0A1119)
private val Line = Color(0xFF17293A)
private val Ink = Color(0xFFDBE7F2)
private val Dim = Color(0xFF8FA3B8)
private val Pick = Color(0xFF6FE3FF)
private val Ok = Color(0xFF5FE0A8)
private val Warn = Color(0xFFFFB648)

/**
 * Step 0 only. Nothing here talks to the network - the whole point of §3.1 is
 * that three of its four items fail silently and look like a network problem,
 * so they are made visible before any request is ever sent.
 */
class MainActivity : ComponentActivity() {

    private val permissionTick = mutableIntStateOf(0)

    private val notificationPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { permissionTick.intValue += 1 }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        setContent {
            val tick = permissionTick.intValue
            // rememberSaveable: a rotation, or process death behind the permission
            // dialog, wiped the typed host and snapped the readiness list back to
            // "No host set yet" — on the one screen whose job is capturing it.
            var host by rememberSaveable { mutableStateOf("") }
            val items = remember(tick, host) { PlatformReadiness.report(this, host) }

            Column(
                Modifier
                    .fillMaxSize()
                    .background(Void)
                    .windowInsetsPadding(WindowInsets.systemBars)
                    .padding(horizontal = 18.dp),
            ) {
                Spacer(Modifier.height(22.dp))
                Text(
                    "JARVIS",
                    style = MaterialTheme.typography.titleLarge,
                    color = Pick,
                )
                Text(
                    "Step 0 — platform configuration",
                    style = MaterialTheme.typography.labelSmall,
                    color = Dim,
                )

                Spacer(Modifier.height(16.dp))

                OutlinedTextField(
                    value = host,
                    onValueChange = { host = it },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    label = { Text("Desktop host", color = Dim) },
                    placeholder = { Text("your-desktop.tailnet.ts.net", color = Dim) },
                    textStyle = MaterialTheme.typography.bodyMedium
                        .copy(fontFamily = FontFamily.Monospace, color = Ink),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                    shape = RoundedCornerShape(10.dp),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = Pick,
                        unfocusedBorderColor = Line,
                        focusedContainerColor = Plate,
                        unfocusedContainerColor = Plate,
                    ),
                )

                Spacer(Modifier.height(14.dp))

                LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                    modifier = Modifier.weight(1f),
                ) {
                    items(items, key = { it.title }) { ReadinessCard(it) }
                }

                Spacer(Modifier.height(12.dp))

                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    // Derived from the already-remembered list rather than re-read
                    // from PackageManager in composition: a bare system read has no
                    // snapshot subscription and only refreshed here because `tick`
                    // happened to be read in the same restart scope.
                    val notificationsItem = items.firstOrNull { it.title == "Notifications" }
                    if (notificationsItem?.state == ReadinessItem.State.WARN) {
                        Button(
                            onClick = {
                                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                                    notificationPermission.launch(
                                        Manifest.permission.POST_NOTIFICATIONS,
                                    )
                                }
                            },
                            modifier = Modifier.weight(1f),
                            shape = RoundedCornerShape(10.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = Plate,
                                contentColor = Warn,
                            ),
                        ) { Text("Allow notifications") }
                    }

                    val batteryItem = items.firstOrNull { it.title == "Background restart" }
                    if (batteryItem?.state == ReadinessItem.State.WARN) {
                        Button(
                            onClick = { requestBatteryExemption() },
                            modifier = Modifier.weight(1f),
                            shape = RoundedCornerShape(10.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = Plate,
                                contentColor = Warn,
                            ),
                        ) { Text("Keep link alive") }
                    }

                    Button(
                        onClick = { EventService.start(this@MainActivity) },
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(10.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = Plate,
                            contentColor = Pick,
                        ),
                    ) { Text("Start link service") }
                }

                Spacer(Modifier.height(18.dp))
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // Notification permission and the battery exemption can both be changed in
        // Settings while we are away.
        permissionTick.intValue += 1
    }

    /**
     * Opens the platform's own exemption dialog. Never granted silently, and the
     * screen keeps reporting the real state either way.
     */
    private fun requestBatteryExemption() {
        val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
            .setData(Uri.parse("package:$packageName"))
        runCatching { startActivity(intent) }.onFailure {
            // Some builds hide the per-app dialog; fall back to the list.
            runCatching { startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)) }
        }
    }
}

@Composable
private fun ReadinessCard(item: ReadinessItem) {
    val tint = when (item.state) {
        ReadinessItem.State.OK -> Ok
        ReadinessItem.State.WARN -> Warn
        ReadinessItem.State.INFO -> Dim
    }
    Column(
        Modifier
            .fillMaxWidth()
            .background(Plate, RoundedCornerShape(12.dp))
            .padding(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Spacer(
                Modifier
                    .size(8.dp)
                    .background(tint, CircleShape),
            )
            Spacer(Modifier.width(10.dp))
            Text(
                item.title,
                style = MaterialTheme.typography.titleMedium.copy(fontSize = 14.sp),
                color = Ink,
            )
        }
        Spacer(Modifier.height(6.dp))
        Text(
            item.detail,
            style = MaterialTheme.typography.bodyMedium.copy(fontSize = 13.sp),
            color = Dim,
        )
    }
}
```

## `jarvis-client/app/src/main/java/com/jarvis/client/platform/PlatformReadiness.kt`

```kotlin
package com.jarvis.client.platform

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.PowerManager
import androidx.core.content.ContextCompat
import com.jarvis.client.service.EventService

/**
 * The four items in ANDROID-BUILD.md §3.1, reported rather than assumed.
 *
 * Three of them fail silently and look like something else: cleartext looks
 * like a network outage, a denied notification looks like the service not
 * running, and Doze looks like the backend going away. Step 0 exists so those
 * are visible on the device before anything talks to the network.
 */
data class ReadinessItem(
    val title: String,
    val detail: String,
    val state: State,
) {
    enum class State { OK, WARN, INFO }
}

object PlatformReadiness {

    /**
     * Hosts the network security config permits in cleartext. Kept in step with
     * res/xml/network_security_config.xml by hand: there is no API to read the
     * parsed config back, so a mismatch here is a lie on the readiness screen
     * rather than a runtime failure.
     */
    private val CLEARTEXT_EXACT = setOf("ts.net", "localhost", "127.0.0.1")
    private val CLEARTEXT_SUFFIXES = listOf(".ts.net")

    /**
     * Mirrors what `<domain includeSubdomains="true">ts.net</domain>` actually
     * matches: the domain itself and labels beneath it, and nothing else.
     *
     * The previous predicate held a bare `"ts.net"` and tested it with `endsWith`,
     * so `notmyts.net` and `evilts.net` — registrable public domains that have
     * nothing to do with Tailscale — reported "permitted" on the one screen whose
     * whole job is to make this policy legible. It failed in the safe direction,
     * because the platform would still refuse the connection, but the same shape of
     * bug in the other app sent a bearer token to a public host in the clear.
     */
    fun cleartextPermitted(host: String): Boolean {
        val h = host.trim().lowercase().substringBefore(':').trim('/')
        if (h.isEmpty()) return false
        if (h in CLEARTEXT_EXACT) return true
        return CLEARTEXT_SUFFIXES.any { h.endsWith(it) }
    }

    /**
     * Whether the app is exempt from battery optimisation.
     *
     * This is the exemption that lets the service go foreground from the background,
     * which is what a sticky restart after the system reclaims the process needs.
     * Without it, one reclaim ends the link permanently.
     */
    fun batteryExempt(context: Context): Boolean {
        val pm = ContextCompat.getSystemService(context, PowerManager::class.java) ?: return false
        return runCatching { pm.isIgnoringBatteryOptimizations(context.packageName) }
            .getOrDefault(false)
    }

    fun notificationsGranted(context: Context): Boolean =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
                PackageManager.PERMISSION_GRANTED
        } else {
            true
        }

    fun report(context: Context, host: String): List<ReadinessItem> = listOf(
        ReadinessItem(
            title = "Cleartext HTTP",
            detail = if (host.isBlank()) {
                "No host set yet. A MagicDNS name ending .ts.net is permitted; a bare IP is not."
            } else if (cleartextPermitted(host)) {
                "Permitted for $host by the network security config."
            } else {
                "$host is NOT permitted in cleartext. Use the desktop's MagicDNS " +
                    "name (….ts.net) rather than its IP address."
            },
            state = if (host.isNotBlank() && cleartextPermitted(host)) {
                ReadinessItem.State.OK
            } else {
                ReadinessItem.State.WARN
            },
        ),
        ReadinessItem(
            title = "Foreground service type",
            detail = "specialUse. dataSync would be capped at six hours a day on " +
                "Android 15 and the service would be killed when the budget ran out.",
            state = ReadinessItem.State.OK,
        ),
        ReadinessItem(
            title = "Notifications",
            detail = if (notificationsGranted(context)) {
                "Granted. The ongoing service notification will be visible."
            } else {
                "Denied. The service will still run, but its notification is hidden " +
                    "from the drawer and only appears in the Task Manager."
            },
            state = if (notificationsGranted(context)) {
                ReadinessItem.State.OK
            } else {
                ReadinessItem.State.WARN
            },
        ),
        ReadinessItem(
            title = "Background restart",
            detail = if (batteryExempt(context)) {
                "Exempt from battery optimisation, so the service can be restarted " +
                    "by the system after the process is reclaimed."
            } else {
                "Not exempt. If Android reclaims the process, the sticky restart " +
                    "happens in the background, startForeground is refused, and the " +
                    "link stops for good until you reopen the app."
            },
            state = if (batteryExempt(context)) {
                ReadinessItem.State.OK
            } else {
                ReadinessItem.State.WARN
            },
        ),
        ReadinessItem(
            title = "Link service",
            detail = EventService.lastStartFailure?.let {
                "The service was refused by the platform ($it) and stopped itself. " +
                    "Grant the battery-optimisation exemption above and start it again."
            } ?: "No start failures recorded.",
            state = if (EventService.lastStartFailure == null) {
                ReadinessItem.State.INFO
            } else {
                ReadinessItem.State.WARN
            },
        ),
        ReadinessItem(
            title = "Doze",
            detail = "A persistent socket is a deliberate departure from the " +
                "platform's documented direction, which is FCM. FCM routes through " +
                "Google and this app talks only to your backend, so the socket " +
                "stands and the stale indicator is the mitigation.",
            state = ReadinessItem.State.INFO,
        ),
    )
}
```

## `jarvis-client/app/src/main/java/com/jarvis/client/service/BootReceiver.kt`

```kotlin
package com.jarvis.client.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Restarts the link after a reboot or an app update.
 *
 * The service is otherwise only ever started by the button on the readiness
 * screen, so a phone rebooted overnight had no connection in the morning and
 * nothing on the device said so.
 *
 * `BOOT_COMPLETED` is a documented exemption to the background
 * foreground-service start restriction, which is why this works where the sticky
 * restart the system performs on its own does not.
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED,
            Intent.ACTION_MY_PACKAGE_REPLACED,
            -> {
                Log.i(TAG, "restarting link after ${intent.action}")
                EventService.start(context)
            }
        }
    }

    private companion object {
        const val TAG = "JarvisClientBoot"
    }
}
```

## `jarvis-client/app/src/main/java/com/jarvis/client/service/EventService.kt`

```kotlin
package com.jarvis.client.service

import android.app.Notification
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.jarvis.client.R

/**
 * Holds the SSE connection open. Step 0 only proves the service type is right;
 * the stream itself arrives in step 2.
 *
 * The type is specialUse rather than dataSync deliberately - see §3.1(2). The
 * six-hour dataSync budget on Android 15 is shared across every dataSync
 * service in the app and, when spent, produces a fatal RemoteServiceException
 * rather than a graceful stop. §11 makes "survives more than six hours without
 * the app being foregrounded" an acceptance criterion, which is precisely the
 * test dataSync fails.
 */
class EventService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        startInForeground()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        return START_STICKY
    }

    /**
     * Android 14+ requires onTimeout to be handled for timed foreground service
     * types. specialUse is not one of them, so neither of these should ever fire -
     * they are here so that if the type is ever changed back to a capped one, the
     * app stops itself instead of being killed with a RemoteServiceException.
     *
     * Both overloads, because they are not interchangeable: the one-argument form
     * is dispatched only for shortService, and the dataSync/mediaProcessing budget
     * on Android 15+ calls the two-argument one (API 35). With only the former
     * overridden, the safety net this comment describes was not armed on any device
     * this app runs on - the whole range is API 33-36.
     */
    override fun onTimeout(startId: Int) {
        Log.w(TAG, "foreground service timed out; the service type is capped after all")
        stopSelf()
    }

    override fun onTimeout(startId: Int, fgsType: Int) {
        if (Build.VERSION.SDK_INT >= 35) {
            Log.w(TAG, "foreground service type $fgsType timed out")
        }
        stopSelf()
    }

    private fun startInForeground() {
        val notification: Notification =
            NotificationCompat.Builder(this, CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_notification)
                .setContentTitle(getString(R.string.app_name))
                .setContentText("Not connected yet")
                .setOngoing(true)
                .setSilent(true)
                .setShowWhen(false)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
                .build()

        try {
            ServiceCompat.startForeground(
                this,
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE,
            )
        } catch (e: Exception) {
            // POST_NOTIFICATIONS denied does not stop the service, but other
            // failures do.
            //
            // The common case here is a sticky restart: the system reclaimed the
            // process, restarted the service with the app in the background, and a
            // background foreground-service start is not on the exemption list. That
            // used to end the link permanently with one logcat line. Record it where
            // the readiness screen can show it, so the phone can say the link is
            // down and why rather than appearing to work.
            Log.e(TAG, "startForeground refused", e)
            lastStartFailure = e.javaClass.simpleName
            stopSelf()
        }
    }

    companion object {
        private const val TAG = "JarvisEventService"

        /**
         * Set when the platform refused to let the service go foreground. Read by
         * the readiness screen; null while nothing has gone wrong.
         */
        @Volatile
        @JvmStatic
        var lastStartFailure: String? = null
        const val CHANNEL_ID = "jarvis_link"
        private const val NOTIFICATION_ID = 0x4A56
        const val ACTION_STOP = "com.jarvis.client.STOP_LINK"

        fun start(context: Context) {
            runCatching {
                ContextCompat.startForegroundService(
                    context,
                    Intent(context, EventService::class.java),
                )
            }.onFailure { Log.e(TAG, "could not start", it) }
        }

        fun stop(context: Context) {
            runCatching {
                context.startService(
                    Intent(context, EventService::class.java).setAction(ACTION_STOP),
                )
            }
        }
    }
}
```

## `jarvis-client/app/src/test/java/com/jarvis/client/PlatformReadinessTest.kt`

```kotlin
package com.jarvis.client

import com.jarvis.client.platform.PlatformReadiness
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Pins the cleartext predicate against the network security config it claims to
 * mirror.
 *
 * `<domain includeSubdomains="true">ts.net</domain>` matches `ts.net` and labels
 * beneath it, and nothing else. The screen this feeds exists to make that policy
 * legible, so a predicate that disagrees with it is worse than no screen at all.
 */
class PlatformReadinessTest {

    @Test
    fun `tailscale magicdns names are permitted`() {
        assertTrue(PlatformReadiness.cleartextPermitted("desktop.tail1234.ts.net"))
        assertTrue(PlatformReadiness.cleartextPermitted("desk.ts.net"))
        assertTrue(PlatformReadiness.cleartextPermitted("ts.net"))
        assertTrue(PlatformReadiness.cleartextPermitted("localhost"))
        assertTrue(PlatformReadiness.cleartextPermitted("127.0.0.1"))
    }

    @Test
    fun `a suffix that is not a subdomain is refused`() {
        // These are registrable public domains. A bare "ts.net" entry tested with
        // endsWith reported them permitted.
        assertFalse(PlatformReadiness.cleartextPermitted("notmyts.net"))
        assertFalse(PlatformReadiness.cleartextPermitted("evilts.net"))
        assertFalse(PlatformReadiness.cleartextPermitted("mylocalhost"))
        assertFalse(PlatformReadiness.cleartextPermitted("not127.0.0.1"))
    }

    @Test
    fun `bare tailscale addresses are refused, because the config cannot express a CIDR range`() {
        assertFalse(PlatformReadiness.cleartextPermitted("100.64.0.1"))
        assertFalse(PlatformReadiness.cleartextPermitted("100.101.102.103"))
    }

    @Test
    fun `ports and stray slashes do not change the verdict`() {
        assertTrue(PlatformReadiness.cleartextPermitted("desk.ts.net:8080"))
        assertTrue(PlatformReadiness.cleartextPermitted("/desk.ts.net/"))
        assertTrue(PlatformReadiness.cleartextPermitted("  DESK.TS.NET  "))
        assertFalse(PlatformReadiness.cleartextPermitted(""))
        assertFalse(PlatformReadiness.cleartextPermitted("   "))
    }

    @Test
    fun `public hosts are refused`() {
        assertFalse(PlatformReadiness.cleartextPermitted("example.com"))
        assertFalse(PlatformReadiness.cleartextPermitted("jarvis.example.com"))
    }
}
```

## `server/jarvis_mobile_ws.py`

```python
"""WebSocket endpoint for the Jarvis Mobile Android client.

Drop-in for a desktop server already built on ``http.server``. No third-party
dependencies: ``BaseHTTPRequestHandler`` cannot speak WebSocket, so this hijacks
the connection after the 101 response and implements RFC 6455 framing directly.
That keeps the endpoint on the same port the phone already dials rather than
forcing a migration to aiohttp or a second listener.

Wire up in your handler's ``do_GET``::

    from jarvis_mobile_ws import MobileEndpoint, ApprovalVerifier

    ENDPOINT = MobileEndpoint(
        verifier=ApprovalVerifier(secret=os.environ["JARVIS_SHARED_SECRET"]),
        auth_token=os.environ.get("JARVIS_AUTH_TOKEN"),
    )

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            if self.path == MobileEndpoint.PATH:
                ENDPOINT.serve(self)      # blocks for the life of the socket
                return
            ...

Serve it from ``ThreadingHTTPServer``; each phone occupies one thread.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import socket
import struct
import threading
import time
from typing import Any, Callable, Iterable, Iterator

log = logging.getLogger("jarvis.mobile")

_WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONT = 0x0
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

# The phone sends 20ms PCM chunks; anything approaching this is malformed.
MAX_FRAME_BYTES = 1 << 20

# The client pings every 25s. Three missed intervals means the peer is gone.
READ_TIMEOUT_SECONDS = 90.0


# --------------------------------------------------------------- approvals ----


class ApprovalVerifier:
    """Verifies the signed approval envelope the phone returns.

    Signed payload::

        {id}|{approved}|{device_id}|{decided_at_ms}|{nonce}

    Checks run signature-first so unauthenticated input never reaches the
    replay cache, and the nonce is claimed atomically: two threads racing the
    same replayed decision must not both win.
    """

    def __init__(
        self,
        secret: str,
        *,
        allowed_device_ids: Iterable[str] | None = None,
        max_clock_skew_ms: int = 60_000,
        nonce_ttl_seconds: int = 300,
    ) -> None:
        if not secret:
            # Fail closed at construction. A server that starts without a key
            # would otherwise accept whatever the phone refuses to sign.
            raise ValueError("ApprovalVerifier requires a non-empty shared secret")
        self._secret = secret.encode("utf-8")
        self._allowed = set(allowed_device_ids) if allowed_device_ids else None
        self._max_skew_ms = max_clock_skew_ms
        self._ttl = nonce_ttl_seconds
        self._nonces: dict[str, float] = {}
        self._lock = threading.Lock()

    def verify(
        self,
        payload: dict[str, Any],
        *,
        is_pending: Callable[[str], bool] | None = None,
    ) -> tuple[bool, str]:
        """Returns ``(ok, reason)``. Consumes the nonce only on success."""
        request_id = payload.get("id")
        approved = payload.get("approved")
        device_id = payload.get("device_id")
        decided_at = payload.get("decided_at_ms")
        nonce = payload.get("nonce")
        signature = payload.get("signature")

        if not isinstance(request_id, str) or not request_id:
            return False, "missing id"
        # Explicit bool test: a JSON string "true" must not coerce into a
        # decision, and `approved is True` alone would silently read it as
        # a rejection rather than rejecting the payload.
        if not isinstance(approved, bool):
            return False, "approved must be a JSON boolean"
        if not isinstance(device_id, str) or not device_id:
            return False, "missing device_id"
        if not isinstance(decided_at, int):
            return False, "missing decided_at_ms"
        if not isinstance(nonce, str) or not nonce:
            return False, "missing nonce"
        if not isinstance(signature, str) or not signature:
            return False, "missing signature"

        if self._allowed is not None and device_id not in self._allowed:
            return False, "unknown device_id"

        canonical = f"{request_id}|{'true' if approved else 'false'}|{device_id}|{decided_at}|{nonce}"
        expected = hmac.new(
            self._secret, canonical.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False, "invalid signature"

        now_ms = int(time.time() * 1000)
        if abs(now_ms - decided_at) > self._max_skew_ms:
            return False, "timestamp outside skew window"

        if is_pending is not None and not is_pending(request_id):
            return False, "no such pending approval"

        if not self._claim_nonce(nonce):
            return False, "replayed nonce"

        return True, "verified"

    def _claim_nonce(self, nonce: str) -> bool:
        now = time.monotonic()
        with self._lock:
            # Prune here rather than on a timer: the cache only grows on the
            # same code path that cleans it.
            if self._nonces:
                cutoff = now - self._ttl
                stale = [k for k, seen in self._nonces.items() if seen < cutoff]
                for key in stale:
                    del self._nonces[key]
            if nonce in self._nonces:
                return False
            self._nonces[nonce] = now
            return True

    @property
    def tracked_nonces(self) -> int:
        with self._lock:
            return len(self._nonces)


# -------------------------------------------------------------- ws framing ----


class WebSocketClosed(Exception):
    pass


class MobileSocket:
    """One connected handset. Send methods are safe from any thread."""

    def __init__(self, connection: socket.socket, rfile, wfile) -> None:
        self._conn = connection
        self._rfile = rfile
        self._wfile = wfile
        self._write_lock = threading.Lock()
        self._closed = False

    # -- reading ---------------------------------------------------------

    def read_message(self) -> tuple[int, bytes] | None:
        """Blocks for one complete data message. ``None`` once the peer goes."""
        fragments: list[bytes] = []
        message_op: int | None = None

        while True:
            frame = self._read_frame()
            if frame is None:
                return None
            fin, opcode, payload = frame

            if opcode == OP_CLOSE:
                self._safe_send(OP_CLOSE, payload[:2])
                self._closed = True
                return None
            if opcode == OP_PING:
                # Mandatory: OkHttp fails the connection if its ping goes
                # unanswered within the ping interval.
                self._safe_send(OP_PONG, payload)
                continue
            if opcode == OP_PONG:
                continue

            if opcode == OP_CONT:
                if message_op is None:
                    raise WebSocketClosed("continuation without a start frame")
                fragments.append(payload)
            elif opcode in (OP_TEXT, OP_BINARY):
                message_op = opcode
                fragments = [payload]
            else:
                raise WebSocketClosed(f"reserved opcode {opcode:#x}")

            if fin:
                assert message_op is not None
                return message_op, b"".join(fragments)

    def _read_frame(self) -> tuple[bool, int, bytes] | None:
        header = self._read_exact(2)
        if header is None:
            return None
        b0, b1 = header[0], header[1]
        fin = bool(b0 & 0x80)
        opcode = b0 & 0x0F
        masked = bool(b1 & 0x80)
        length = b1 & 0x7F

        if length == 126:
            raw = self._read_exact(2)
            if raw is None:
                return None
            length = struct.unpack("!H", raw)[0]
        elif length == 127:
            raw = self._read_exact(8)
            if raw is None:
                return None
            length = struct.unpack("!Q", raw)[0]

        if length > MAX_FRAME_BYTES:
            raise WebSocketClosed(f"frame of {length} bytes exceeds cap")
        if not masked:
            # RFC 6455 §5.1: every client frame must be masked.
            raise WebSocketClosed("unmasked frame from client")

        mask = self._read_exact(4)
        if mask is None:
            return None
        payload = self._read_exact(length) if length else b""
        if payload is None:
            return None

        return fin, opcode, _apply_mask(payload, mask)

    def _read_exact(self, count: int) -> bytes | None:
        chunks: list[bytes] = []
        remaining = count
        while remaining > 0:
            try:
                chunk = self._rfile.read(remaining)
            except (socket.timeout, TimeoutError):
                raise WebSocketClosed("read timed out; peer is gone")
            except OSError as exc:
                raise WebSocketClosed(f"read failed: {exc}")
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    # -- writing ---------------------------------------------------------

    def send_text(self, text: str) -> None:
        self._send(OP_TEXT, text.encode("utf-8"))

    def send_json(self, payload: dict[str, Any]) -> None:
        self.send_text(json.dumps(payload, separators=(",", ":")))

    def send_binary(self, data: bytes) -> None:
        self._send(OP_BINARY, data)

    def close(self, code: int = 1000) -> None:
        self._safe_send(OP_CLOSE, struct.pack("!H", code))
        self._closed = True

    def _send(self, opcode: int, payload: bytes) -> None:
        if self._closed:
            raise WebSocketClosed("socket already closed")
        header = bytearray()
        header.append(0x80 | opcode)
        size = len(payload)
        if size < 126:
            header.append(size)
        elif size < 65_536:
            header.append(126)
            header += struct.pack("!H", size)
        else:
            header.append(127)
            header += struct.pack("!Q", size)

        with self._write_lock:
            try:
                self._wfile.write(bytes(header) + payload)
                self._wfile.flush()
            except OSError as exc:
                self._closed = True
                raise WebSocketClosed(f"write failed: {exc}")

    def _safe_send(self, opcode: int, payload: bytes) -> None:
        try:
            self._send(opcode, payload)
        except WebSocketClosed:
            pass

    # -- protocol helpers ------------------------------------------------

    def send_approval_request(
        self,
        request_id: str,
        title: str,
        summary: str = "",
        tier: str = "ask",
        detail: str | None = None,
        expires_at_ms: int | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "type": "approval_request",
            "id": request_id,
            "title": title,
            "summary": summary,
            "tier": tier,
        }
        if detail is not None:
            payload["detail"] = detail
        if expires_at_ms is not None:
            payload["expires_at_ms"] = expires_at_ms
        self.send_json(payload)

    def send_approval_resolved(self, request_id: str, approved: bool) -> None:
        self.send_json(
            {"type": "approval_resolved", "id": request_id, "approved": approved}
        )

    def send_status(self, text: str) -> None:
        self.send_json({"type": "status", "text": text})

    def send_desktop_telemetry(self, **fields: float | None) -> None:
        payload: dict[str, Any] = {"type": "desktop_telemetry"}
        payload.update({k: v for k, v in fields.items() if v is not None})
        self.send_json(payload)

    def send_device_command(
        self, command_id: str, action: str, params: dict[str, Any] | None = None
    ) -> None:
        self.send_json(
            {
                "type": "device_command",
                "id": command_id,
                "action": action,
                "params": params or {},
            }
        )

    def send_audio_stream(
        self,
        stream_id: str,
        chunks: Iterator[bytes],
        sample_rate: int = 22_050,
        channels: int = 1,
        binary_tag: int = 1,
    ) -> None:
        """Streams PCM as tagged binary frames, avoiding base64 inflation."""
        if not 0 <= binary_tag <= 255:
            raise ValueError("binary_tag must fit in one byte")
        prefix = bytes([binary_tag])
        self.send_json(
            {
                "type": "audio_stream_start",
                "stream_id": stream_id,
                "sample_rate": sample_rate,
                "channels": channels,
                "encoding": "pcm16",
                "binary_tag": binary_tag,
            }
        )
        try:
            for chunk in chunks:
                if chunk:
                    self.send_binary(prefix + chunk)
        finally:
            self.send_json({"type": "audio_stream_end", "stream_id": stream_id})


def _apply_mask(payload: bytes, mask: bytes) -> bytes:
    if not payload:
        return payload
    # Big-integer XOR beats a per-byte Python loop by a wide margin, which
    # matters at 32 KB/s of continuous uplink PCM.
    size = len(payload)
    repeats, remainder = divmod(size, 4)
    full_mask = mask * repeats + mask[:remainder]
    return (
        int.from_bytes(payload, "big") ^ int.from_bytes(full_mask, "big")
    ).to_bytes(size, "big")


def compute_accept(key: str) -> str:
    digest = hashlib.sha1(key.encode("ascii") + _WS_GUID).digest()
    return base64.b64encode(digest).decode("ascii")


# ---------------------------------------------------------------- endpoint ----


class MobileEndpoint:
    """Handles the upgrade and the message loop for one connected phone."""

    PATH = "/api/mobile/ws"

    def __init__(
        self,
        verifier: ApprovalVerifier,
        *,
        auth_token: str | None = None,
        on_approval: Callable[[str, bool, MobileSocket], None] | None = None,
        on_audio: Callable[[bytes, MobileSocket], None] | None = None,
        on_event: Callable[[dict[str, Any], MobileSocket], None] | None = None,
        is_pending: Callable[[str], bool] | None = None,
    ) -> None:
        self._verifier = verifier
        self._auth_token = auth_token or None
        self._on_approval = on_approval
        self._on_audio = on_audio
        self._on_event = on_event
        self._is_pending = is_pending
        self._clients: set[MobileSocket] = set()
        self._clients_lock = threading.Lock()

    @property
    def clients(self) -> list[MobileSocket]:
        with self._clients_lock:
            return list(self._clients)

    def broadcast(self, send: Callable[[MobileSocket], None]) -> int:
        """Applies ``send`` to every live client; returns how many succeeded."""
        delivered = 0
        for client in self.clients:
            try:
                send(client)
                delivered += 1
            except WebSocketClosed:
                self._drop(client)
        return delivered

    def serve(self, handler) -> None:
        """Upgrades and runs the read loop. Blocks until the phone disconnects."""
        if not self._handshake(handler):
            return

        handler.close_connection = True
        try:
            handler.connection.settimeout(READ_TIMEOUT_SECONDS)
        except OSError:
            pass

        client = MobileSocket(handler.connection, handler.rfile, handler.wfile)
        with self._clients_lock:
            self._clients.add(client)

        try:
            self._pump(client)
        except WebSocketClosed as exc:
            log.info("mobile client closed: %s", exc)
        except Exception:
            log.exception("mobile client failed")
        finally:
            self._drop(client)

    def _pump(self, client: MobileSocket) -> None:
        while True:
            message = client.read_message()
            if message is None:
                return
            opcode, payload = message

            if opcode == OP_BINARY:
                if self._on_audio is not None:
                    self._on_audio(payload, client)
                continue

            try:
                event = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                log.warning("dropping unparseable text frame")
                continue
            if not isinstance(event, dict):
                continue

            if event.get("type") == "ping":
                # Echo the phone's own clock reading back untouched: it measures
                # the round trip itself, so the two clocks need not agree.
                sent_at = event.get("sent_at_ms")
                if isinstance(sent_at, int):
                    try:
                        client.send_json({"type": "pong", "sent_at_ms": sent_at})
                    except WebSocketClosed:
                        return
                continue

            if event.get("type") == "approval_decision":
                ok, reason = self._verifier.verify(event, is_pending=self._is_pending)
                if not ok:
                    log.warning(
                        "rejected approval %s: %s", event.get("id"), reason
                    )
                    continue
                if self._on_approval is not None:
                    self._on_approval(event["id"], event["approved"], client)
                continue

            if self._on_event is not None:
                self._on_event(event, client)

    def _handshake(self, handler) -> bool:
        headers = handler.headers

        if (headers.get("Upgrade") or "").lower() != "websocket":
            self._refuse(handler, 400, "expected a websocket upgrade")
            return False
        if "upgrade" not in (headers.get("Connection") or "").lower():
            self._refuse(handler, 400, "missing Connection: Upgrade")
            return False
        if (headers.get("Sec-WebSocket-Version") or "").strip() != "13":
            self._refuse(handler, 426, "unsupported websocket version")
            return False

        key = (headers.get("Sec-WebSocket-Key") or "").strip()
        if not key:
            self._refuse(handler, 400, "missing Sec-WebSocket-Key")
            return False

        # Rejecting here drops the TCP stream before any WebSocket state is
        # allocated, which a token carried in the first frame cannot do.
        if self._auth_token is not None:
            presented = (headers.get("Authorization") or "").strip()
            expected = f"Bearer {self._auth_token}"
            if not hmac.compare_digest(presented, expected):
                self._refuse(handler, 401, "bad or missing bearer token")
                return False

        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {compute_accept(key)}\r\n"
            "\r\n"
        )
        handler.wfile.write(response.encode("ascii"))
        handler.wfile.flush()
        return True

    @staticmethod
    def _refuse(handler, status: int, reason: str) -> None:
        body = reason.encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "text/plain; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Connection", "close")
        handler.end_headers()
        handler.wfile.write(body)
        handler.close_connection = True

    def _drop(self, client: MobileSocket) -> None:
        with self._clients_lock:
            self._clients.discard(client)
        try:
            client.close()
        except WebSocketClosed:
            pass


def generate_shared_secret() -> str:
    """A 256-bit key, hex encoded, to paste into the phone's Pairing field."""
    return os.urandom(32).hex()
```

## `server/test_jarvis_mobile_ws.py`

```python
"""Tests for the mobile WebSocket endpoint.

Run with::

    python3 server/test_jarvis_mobile_ws.py

Stdlib-only, including the client. The point is to prove the RFC 6455 framing
against a socket that masks its frames the way OkHttp does, rather than against
a library that would share this module's own assumptions.
"""

import base64
import hashlib
import hmac
import json
import os
import socket
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jarvis_mobile_ws import ApprovalVerifier, MobileEndpoint, compute_accept

failures = []


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(name)


SECRET = "test-secret-key"


print("Verifier:")
v = ApprovalVerifier(SECRET, max_clock_skew_ms=60_000, nonce_ttl_seconds=1)

def sign(rid, approved, dev, ts, nonce, secret=SECRET):
    canon = f"{rid}|{'true' if approved else 'false'}|{dev}|{ts}|{nonce}"
    return hmac.new(secret.encode(), canon.encode(), hashlib.sha256).hexdigest()

now = int(time.time()*1000)
good = {"type":"approval_decision","id":"r1","approved":True,"device_id":"d1",
        "decided_at_ms":now,"nonce":"n1","signature":sign("r1",True,"d1",now,"n1")}
check("valid decision accepted", v.verify(dict(good))[0])
check("replayed nonce rejected", v.verify(dict(good)) == (False, "replayed nonce"))

bad = dict(good); bad["nonce"]="n2"; bad["signature"]="deadbeef"
check("bad signature rejected", v.verify(bad) == (False, "invalid signature"))

stale_ts = now - 600_000
st = {"type":"approval_decision","id":"r2","approved":False,"device_id":"d1",
      "decided_at_ms":stale_ts,"nonce":"n3","signature":sign("r2",False,"d1",stale_ts,"n3")}
check("clock skew rejected", v.verify(st) == (False, "timestamp outside skew window"))

coerce = dict(good); coerce["approved"]="true"; coerce["nonce"]="n4"
check("string 'true' rejected (not coerced)", v.verify(coerce) == (False,"approved must be a JSON boolean"))

try:
    ApprovalVerifier("")
    _empty_ok = False
except ValueError:
    _empty_ok = True
check("empty secret refused at construction", _empty_ok)

# device pinning
vp = ApprovalVerifier(SECRET, allowed_device_ids=["known"])
check("unknown device rejected", vp.verify(dict(good)) == (False,"unknown device_id"))

# TTL pruning actually happens
v2 = ApprovalVerifier(SECRET, nonce_ttl_seconds=0)
for i in range(50):
    ts = int(time.time()*1000); n=f"p{i}"
    v2.verify({"id":"r","approved":True,"device_id":"d","decided_at_ms":ts,
               "nonce":n,"signature":sign("r",True,"d",ts,n)})
check(f"nonce cache pruned (holds {v2.tracked_nonces}, not 50)", v2.tracked_nonces <= 1)


SECRET, TOKEN = "s3cr3t", "tok-123"
approvals, audio = [], []

ENDPOINT = MobileEndpoint(
    verifier=ApprovalVerifier(SECRET),
    auth_token=TOKEN,
    on_approval=lambda rid, ok, c: approvals.append((rid, ok)),
    on_audio=lambda data, c: audio.append(data),
)

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path == MobileEndpoint.PATH:
            ENDPOINT.serve(self); return
        self.send_response(404); self.send_header("Content-Length","0"); self.end_headers()

srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

def frame(opcode, payload, mask=True):
    out = bytearray([0x80 | opcode])
    n = len(payload)
    m = 0x80 if mask else 0
    if n < 126: out.append(m | n)
    elif n < 65536: out.append(m | 126); out += struct.pack("!H", n)
    else: out.append(m | 127); out += struct.pack("!Q", n)
    if mask:
        k = os.urandom(4); out += k
        out += bytes(b ^ k[i % 4] for i, b in enumerate(payload))
    else:
        out += payload
    return bytes(out)

def read_frame(sock):
    def rd(n):
        buf = b""
        while len(buf) < n:
            c = sock.recv(n - len(buf))
            if not c: raise EOFError
            buf += c
        return buf
    b0, b1 = rd(2)
    op, ln = b0 & 0x0F, b1 & 0x7F
    if ln == 126: ln = struct.unpack("!H", rd(2))[0]
    elif ln == 127: ln = struct.unpack("!Q", rd(8))[0]
    return op, (rd(ln) if ln else b"")

def connect(token=TOKEN):
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    key = base64.b64encode(os.urandom(16)).decode()
    req = (f"GET {MobileEndpoint.PATH} HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\n"
           f"Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {key}\r\n")
    if token is not None: req += f"Authorization: Bearer {token}\r\n"
    s.sendall((req + "\r\n").encode())
    hdr = b""
    while b"\r\n\r\n" not in hdr: hdr += s.recv(4096)
    return s, hdr.decode(errors="replace"), key

print("Handshake:")
s, hdr, key = connect()
check("101 Switching Protocols", "101 Switching Protocols" in hdr)
check("Sec-WebSocket-Accept correct", f"Sec-WebSocket-Accept: {compute_accept(key)}" in hdr)

print("Auth:")
s2, hdr2, _ = connect(token="wrong")
check("bad bearer token -> 401", "401" in hdr2.split("\r\n")[0]); s2.close()
s3, hdr3, _ = connect(token=None)
check("missing bearer token -> 401", "401" in hdr3.split("\r\n")[0]); s3.close()

print("Framing:")
s.sendall(frame(0x9, b"ping-payload"))          # client ping
op, pl = read_frame(s)
check("ping answered with pong", op == 0xA and pl == b"ping-payload")

s.sendall(frame(0x2, bytes([7]) + b"\x01\x02" * 500))   # binary uplink
time.sleep(0.3)
check(f"binary frame received ({len(audio[0]) if audio else 0} bytes)",
      audio and len(audio[0]) == 1001 and audio[0][0] == 7)

big = os.urandom(70000)                          # forces 64-bit length path
s.sendall(frame(0x2, big)); time.sleep(0.4)
check("extended-length frame unmasked correctly", len(audio) > 1 and audio[1] == big)

print("Approval path:")
now = int(time.time()*1000)
def sign(rid, ap, dev, ts, n):
    return hmac.new(SECRET.encode(), f"{rid}|{'true' if ap else 'false'}|{dev}|{ts}|{n}".encode(),
                    hashlib.sha256).hexdigest()
dec = {"type":"approval_decision","id":"req-9","approved":True,"device_id":"phone",
       "decided_at_ms":now,"nonce":"nn1","signature":sign("req-9",True,"phone",now,"nn1")}
s.sendall(frame(0x1, json.dumps(dec).encode())); time.sleep(0.3)
check("signed approval delivered", approvals == [("req-9", True)])

s.sendall(frame(0x1, json.dumps(dec).encode())); time.sleep(0.3)   # replay
check("replay not delivered twice", approvals == [("req-9", True)])

forged = dict(dec); forged["nonce"]="nn2"; forged["signature"]="00"*32
s.sendall(frame(0x1, json.dumps(forged).encode())); time.sleep(0.3)
check("forged signature not delivered", approvals == [("req-9", True)])

print("Server -> phone:")
ENDPOINT.broadcast(lambda c: c.send_approval_request("req-10","Delete file","rm -rf /tmp/x"))
op, pl = read_frame(s)
ev = json.loads(pl)
check("approval_request framed correctly", op == 0x1 and ev["type"]=="approval_request" and ev["id"]=="req-10")

sent = ENDPOINT.broadcast(lambda c: c.send_audio_stream("st1", iter([b"\x11"*640, b"\x22"*640]), binary_tag=3))
op1, start = read_frame(s); op2, a1 = read_frame(s); op3, a2 = read_frame(s); op4, end = read_frame(s)
check("audio_stream_start carries binary_tag", json.loads(start)["binary_tag"] == 3)
check("audio frames tagged + binary", op2 == 0x2 and a1[0] == 3 and len(a1) == 641)
check("audio_stream_end sent", json.loads(end)["type"] == "audio_stream_end")

s.close(); srv.shutdown()
print(f"\n{'ALL PASS' if not failures else 'FAILURES: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
```
