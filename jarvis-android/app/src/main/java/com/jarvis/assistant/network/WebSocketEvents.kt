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

/** An `ask` tier action on the desktop is gated until the phone answers. */
@Serializable
@SerialName("approval_request")
data class ApprovalRequestEvent(
    val id: String,
    val title: String = "Approval required",
    val summary: String = "",
    val tier: String = "ask",
    val detail: String? = null,
    @SerialName("expires_at_ms") val expiresAtMs: Long? = null,
) : InboundEvent

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
