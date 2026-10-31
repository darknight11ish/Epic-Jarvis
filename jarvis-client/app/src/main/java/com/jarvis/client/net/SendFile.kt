package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.longOrNull
import java.security.MessageDigest
import kotlin.io.encoding.Base64
import kotlin.io.encoding.ExperimentalEncodingApi

/**
 * "Send one file from the PC to the phone" - the owner's ask of 2026-10-31,
 * verbatim: *"am i able to ask jarvis to search for a file for me and send it
 * to the jarvis android app to view and or download directly? this would be a
 * file on the desktop"*. Gemini ruled the bounded slice the same day (Q7).
 * The backend half is `backend/jarvis_send_file.py` (docs/JARVIS-API.md
 * section 172); this object is the whole phone-facing contract.
 *
 * TWO routes, and neither takes a filesystem path:
 *
 * - `GET /api/files/send` - the files the owner has already approved for this
 *   phone, waiting for it: `{id, name, folder, size_bytes, mime, expires_in}`
 *   each, plus the PC's `cap_bytes`, `ttl_seconds`, `single_use` and one `said`
 *   sentence. A file appears ONLY after a person approved its card.
 * - `GET /api/files/download?id=<id>` - the bytes of ONE approved file, as
 *   base64 JSON `{name, size_bytes, mime, sha256, data}`. A raw path is never
 *   accepted and the answer never carries one.
 *
 * The PC's own rules, stated here and never reinterpreted: ONE file at a time,
 * at most [MAX_BYTES] (10 MiB), the link lasts [TTL_SECONDS] (ten minutes) and
 * works ONCE - a second fetch is a plain 404 ("already downloaded or the
 * ten-minute window passed"). The phone never approves anything: the card was
 * raised and answered on the PC, and this side only lists and fetches.
 *
 * Every sentence shown to the owner in the plate comes from the PC's answer
 * where the PC sent one; the few fallbacks here are the app's own plain words
 * for a phone-side step (a phone with no app that can open the file, a save
 * that failed).
 *
 * Pure Kotlin (base64/charset/format only - no Android types), so
 * `SendFileTest` runs it on a plain JVM.
 */
object SendFile {
    /** The two routes, as `tools/check_parity.py` reads them. */
    const val LIST_PATH = "/api/files/send"
    const val DOWNLOAD_PATH = "/api/files/download"

    /** The PC's own named limits (docs/JARVIS-API.md section 172.3). */
    const val MAX_BYTES = 10L * 1024L * 1024L
    const val TTL_SECONDS = 10 * 60
    const val MAX_PENDING = 8

    /** The PC's id shape: `file_` and 16-64 URL-safe characters. */
    private val ID_SHAPE = Regex("^file_[A-Za-z0-9_-]{16,64}$")

    /** How often the plate re-reads the list while it is open (a file lives 10 min). */
    const val REFRESH_MS = 15_000L

    /** An older PC without the module (404/501 from the list route). */
    const val MISSING =
        "Your PC's Jarvis cannot send files to your phone yet - run apply-patches.ps1 on the PC."

    /**
     * The phone's own sentence while the private lists are hidden. This route
     * has no `?hidden=1` in the contract, so the phone simply does not ask: no
     * filename is ever fetched or drawn while the lists are hidden.
     */
    const val HIDDEN_NAMES =
        "A file's name is hidden while your memory lists and chat history are hidden. " +
            "Show them to see what is waiting."

    /** The PC's limits, in one line the owner can read. */
    const val LIMITS =
        "One file at a time, up to 10 MiB, and the link lasts ten minutes and works once."

    /** Nothing waiting, and no PC sentence to quote. */
    const val NOTHING_WAITING = "No file is waiting for your phone right now."

    /** The PC's answer could not be read as a file at all. */
    const val UNREADABLE = "The PC's answer did not carry the file. Nothing was saved."

    /** A file that arrived changed on the way (the PC's own sha256 disagrees). */
    const val NOT_WHAT_WAS_SENT =
        "The file that arrived did not match what your PC said it was sending, so it was " +
            "not kept. Ask Jarvis to send it again."

    /** Phone-side: no app on this phone will open the file. */
    const val NO_VIEWER =
        "This phone has no app that can open that kind of file. Save to Downloads keeps it, " +
            "and you can open it from there."

    /** Phone-side: writing into Downloads was refused. */
    const val SAVE_FAILED = "That file could not be saved to Downloads. Nothing was kept."

    /** One approved file waiting for the phone. */
    data class Waiting(
        val id: String,
        val name: String,
        val folder: String,
        val sizeBytes: Long,
        val mime: String,
        val expiresIn: Int,
    )

    /** `GET /api/files/send`, read. */
    sealed class ListReply {
        /** The PC listed its waiting files (possibly none). */
        data class Ready(
            val files: List<Waiting>,
            val capBytes: Long,
            val ttlSeconds: Int,
            val singleUse: Boolean,
            val said: String,
        ) : ListReply()

        /** An older PC without the module: not a failure, nothing to draw. */
        object Missing : ListReply()

        /** The read failed: the PC's own sentence, or a plain fallback. */
        data class Refused(val said: String) : ListReply()
    }

    /** ONE approved file's bytes, or the PC's refusal in words. */
    sealed class Fetched {
        data class Got(
            val name: String,
            val sizeBytes: Long,
            val mime: String,
            val sha256: String,
            val bytes: ByteArray,
        ) : Fetched()

        data class Refused(val said: String) : Fetched()
    }

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.contentOrNull?.takeIf { it.isNotBlank() }

    private fun JsonObject.num(key: String): Long? =
        (this[key] as? JsonPrimitive)?.longOrNull ?: (this[key] as? JsonPrimitive)?.intOrNull?.toLong()

    /** The PC's refusal sentence in one body, or null when it sent none. */
    fun sentence(body: JsonObject?): String? = body?.str("error") ?: body?.str("said")

    /** `GET /api/files/send` for the plate. */
    fun readList(status: Int, body: JsonObject?): ListReply {
        if (status in 200..299) {
            val files = (body?.get("files") as? JsonArray).orEmpty().mapNotNull { el ->
                val o = el as? JsonObject ?: return@mapNotNull null
                val id = o.str("id") ?: return@mapNotNull null
                val name = o.str("name") ?: return@mapNotNull null
                Waiting(
                    id = id,
                    name = name,
                    folder = o.str("folder").orEmpty(),
                    sizeBytes = o.num("size_bytes") ?: 0L,
                    mime = o.str("mime").orEmpty(),
                    expiresIn = (o.num("expires_in") ?: 0L).toInt(),
                )
            }
            return ListReply.Ready(
                files = files,
                capBytes = body?.num("cap_bytes") ?: MAX_BYTES,
                ttlSeconds = (body?.num("ttl_seconds") ?: TTL_SECONDS.toLong()).toInt(),
                singleUse = (body?.get("single_use") as? JsonPrimitive)?.booleanOrNull ?: true,
                said = body?.str("said").orEmpty(),
            )
        }
        if (status == 404 || status == 501) return ListReply.Missing
        return ListReply.Refused(
            sentence(body) ?: "The files your PC has for your phone could not be read just now.",
        )
    }

    /** `?id=` for one of those files, or null when the id is not one of the PC's. */
    fun downloadPath(id: String): String? {
        val clean = id.trim()
        if (!ID_SHAPE.matches(clean)) return null
        return DOWNLOAD_PATH + "?id=" + java.net.URLEncoder.encode(clean, "UTF-8")
    }

    /** `GET /api/files/download?id=`, read - the bytes, or the PC's sentence. */
    @OptIn(ExperimentalEncodingApi::class)
    fun readDownload(status: Int, body: JsonObject?): Fetched {
        if (status !in 200..299) {
            return Fetched.Refused(
                sentence(body) ?: "That file could not be fetched just now, so nothing was kept.",
            )
        }
        val name = body?.str("name") ?: return Fetched.Refused(UNREADABLE)
        val text = body.str("data") ?: return Fetched.Refused(UNREADABLE)
        val bytes = runCatching { Base64.decode(text) }.getOrNull()
            ?: return Fetched.Refused(UNREADABLE)
        if (bytes.isEmpty()) return Fetched.Refused(UNREADABLE)
        val sha = body.str("sha256").orEmpty()
        if (sha.isNotEmpty() && !sha.equals(sha256(bytes), ignoreCase = true)) {
            return Fetched.Refused(NOT_WHAT_WAS_SENT)
        }
        return Fetched.Got(
            name = name,
            sizeBytes = body.num("size_bytes") ?: bytes.size.toLong(),
            mime = body.str("mime").orEmpty(),
            sha256 = sha,
            bytes = bytes,
        )
    }

    /** The SHA-256 of the bytes just arrived, lower-case hex - as the PC spells it. */
    fun sha256(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    /** The mime type an app opens the file with; the PC's own, or a safe generic. */
    fun mimeOr(mime: String): String = mime.trim().ifEmpty { "application/octet-stream" }

    /**
     * A filename that is safe to write on this phone: the PC already sends a
     * NAME (never a path), and this is the second belt - no separators, no
     * control characters, nothing that could leave the folder it is written to.
     */
    fun nameForDisk(name: String): String {
        val base = name.substringAfterLast('/').substringAfterLast('\\')
            .filter { it.code >= 32 && it !in "<>:\"|?*" }
            .trim().trim('.')
        return base.ifEmpty { "file" }.take(120)
    }

    /** "1,482,331 bytes (1.4 MB large)" - the PC's own card style, from its numbers. */
    fun sizeWords(bytes: Long): String {
        val n = if (bytes < 0) 0L else bytes
        val exact = n.toString().reversed().chunked(3).joinToString(",").reversed()
        val human = when {
            n < 1024 -> ""
            n < 1024 * 1024 -> " (${n / 1024} KB large)"
            else -> " (${"%.1f".format(n / (1024.0 * 1024.0))} MB large)"
        }
        return "$exact bytes$human"
    }

    /** "expires in 9 min" / "expires in under a minute" / "expired" - from the PC's `expires_in`. */
    fun expiryWords(expiresIn: Int): String = when {
        expiresIn <= 0 -> "expired"
        expiresIn < 60 -> "expires in under a minute"
        else -> "expires in ${(expiresIn + 59) / 60} min"
    }
}
