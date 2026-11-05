package com.jarvis.client.net

import com.jarvis.client.call.CallRecordRules
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put
import java.time.ZoneId
import java.util.Base64

/**
 * The phone's half of the call-recording wire, exactly as the PC declared it
 * (the frozen contract of 2026-11-04; the PC's own section in
 * docs/JARVIS-API.md is written by the PC half and is the same table):
 *
 * ```
 * POST /api/call/recording/start
 *   {"started_at": "<iso8601>", "sample_rate": 16000, "channels": 1,
 *    "format": "s16le", "device": "phone"}
 *   -> 200 {"ok": true, "session": "<id>"}
 *
 * POST /api/call/recording/chunk
 *   {"session": "<id>", "seq": <int>, "data_b64": "<base64 PCM>"}
 *   -> 200 {"ok": true, "bytes": <n>}          (retry the SAME seq on failure)
 *
 * POST /api/call/recording/finish
 *   {"session": "<id>", "duration_sec": <n>, "title": "<optional>",
 *    "consent_notice": "on"}
 *   -> 200 {"ok": true, "note": "<path or pending>", "receipt": "..."}
 * ```
 *
 * All three carry the pairing token, `X-Jarvis-Client: hud` and
 * `X-Jarvis-Surface: phone`, because they go through
 * [JarvisApi.postObject] like every other request this app makes. Nothing
 * here logs the token, and nothing here is sent anywhere but the owner's own
 * PC (the address the app is already paired to).
 *
 * WHAT THE PHONE NEVER SENDS: no words, no transcript, no speaker labels, no
 * note path, no vault. Speech-to-text is the PC's job (a client must not do
 * it), the note is the PC's to name and write, and the vault is a folder this
 * phone cannot see. The three bodies above are the whole of it.
 *
 * Pure Kotlin (kotlinx.serialization + java.util.Base64), so
 * `CallRecordWireTest` holds every key, the base64 and the directive parser
 * on a plain JVM - the wire is where a typo is invisible until a real call.
 */
object CallRecordWire {

    /** The three routes, named once (in [CallRecordRules]) so a test can hold them to the contract. */
    val PATHS = listOf(
        CallRecordRules.START_PATH,
        CallRecordRules.CHUNK_PATH,
        CallRecordRules.FINISH_PATH,
    )

    /** A whole sentence for the one failure the owner can act on. */
    const val NO_ROUTE =
        "This PC's Jarvis has no call recording yet. Update it by running apply-patches.ps1 on the PC."

    // ----------------------------------------------------------- requests ---

    /**
     * `POST .../start`: the date the call began (with the phone's own offset,
     * so the PC dates the call as the owner lived it), and the exact shape of
     * the audio it is about to receive. `device` is the contract's word for
     * "the phone made this", not the phone's model.
     */
    fun startBody(startedAtMs: Long, zone: ZoneId = ZoneId.systemDefault()): String = buildJsonObject {
        put("started_at", CallRecordRules.startedAt(startedAtMs, zone))
        put("sample_rate", CallRecordRules.SAMPLE_RATE)
        put("channels", CallRecordRules.CHANNELS)
        put("format", CallRecordRules.FORMAT)
        put("device", CallRecordRules.DEVICE)
    }.toString()

    /**
     * `POST .../chunk`: one piece of PCM as base64, with the sequence number
     * the PC appends by. [`seq`] is 1 for the first piece of a recording and
     * goes up by one; a failed send is retried with the SAME number, because
     * the PC's file is the order it receives them in.
     */
    fun chunkBody(session: String, seq: Int, pcm: ByteArray): String = buildJsonObject {
        put("session", session)
        put("seq", seq)
        put("data_b64", Base64.getEncoder().encodeToString(pcm))
    }.toString()

    /**
     * `POST .../finish`: how long the recording is, an optional title, and the
     * consent notice's own flag ("on" - the notification showed
     * "Recording - tell the other person" for the whole call, and the PC
     * records that it did).
     */
    fun finishBody(session: String, durationSec: Long, title: String? = null): String = buildJsonObject {
        put("session", session)
        put("duration_sec", durationSec.coerceAtLeast(0L))
        title?.trim()?.takeIf { it.isNotEmpty() }?.let { put("title", it) }
        put("consent_notice", CallRecordRules.CONSENT_NOTICE)
    }.toString()

    // ------------------------------------------------------------ answers ---

    /**
     * Did the PC accept this request? Its answers are `{"ok": true, ...}`; an
     * `ok: false` is a refusal even inside a 200, and a body that does not say
     * `ok` at all is read as accepted because the contract only adds it to
     * say "no".
     */
    fun ok(body: JsonObject?): Boolean = body != null && body.flag("ok") != false

    /** What `start` answered: the PC's own session id, or null when it refused. */
    fun started(body: JsonObject?): String? {
        if (!ok(body)) return null
        return body?.str("session")?.takeIf { it.isNotBlank() }
    }

    /**
     * What `chunk` answered: the number of bytes the PC says it has for this
     * recording. The phone does not depend on the number - it trusts its own
     * file and its own `sent.txt` - but it is worth reading back, because a
     * PC that answers `bytes: 0` to every chunk is not appending anything.
     */
    fun ackedBytes(body: JsonObject?): Long? {
        if (!ok(body)) return null
        return body?.whole("bytes")
    }

    /** What `finish` came to: the note the PC wrote (or `pending`), and its receipt. */
    data class Finished(val note: String?, val receipt: String?) {
        /** Said in words: what the PC did with the audio. */
        fun said(): String = when {
            note.isNullOrBlank() || note == "pending" -> CallRecordRules.SENT_TEXT
            else -> "Kept in your notes: $note"
        }
    }

    fun finished(body: JsonObject?): Finished? {
        if (!ok(body)) return null
        return Finished(note = body?.str("note"), receipt = body?.str("receipt"))
    }

    // ---------------------------------------------------------- directive ---

    /**
     * The chat directive, read from the answer's `X-Jarvis-Route` header - the
     * app's one machine-directive channel, the same place `open_brain`,
     * `file_under`, `note_job` and `face_tuning` ride. The frozen contract
     * names the shape exactly:
     *
     * ```json
     * {"call_record": {"action": "arm"}}
     * ```
     *
     * ("stop" is the other action.) Returns the event it names, or null when
     * there is no header, no `call_record`, an action this app does not know,
     * or JSON that does not parse: an unknown directive is SILENCE, never a
     * guess - arming a microphone because of a malformed header would be the
     * worst possible reading of "I could not understand this".
     */
    fun directive(routeHeader: String?): CallRecordRules.Event? {
        val action = actionIn(routeHeader) ?: return null
        return CallRecordRules.eventOf(action)
    }

    /** The bare action word (`arm` / `stop`) from the same header, or null. */
    fun actionIn(routeHeader: String?): String? {
        if (routeHeader.isNullOrBlank()) return null
        val obj = runCatching { JarvisJson.parseToJsonElement(routeHeader.trim()) as? JsonObject }
            .getOrNull() ?: return null
        val field = obj[CallRecordRules.DIRECTIVE_KEY] as? JsonObject ?: return null
        val action = (field["action"] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
        return CallRecordRules.actionOf(action)
    }

    // -------------------------------------------------------------- reading ---

    private fun JsonObject.prim(key: String): JsonPrimitive? = this[key] as? JsonPrimitive

    private fun JsonObject.str(key: String): String? =
        prim(key)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.whole(key: String): Long? = prim(key)?.takeIf { !it.isString }?.longOrNull

    private fun JsonObject.flag(key: String): Boolean? = prim(key)?.takeIf { !it.isString }?.booleanOrNull
}
