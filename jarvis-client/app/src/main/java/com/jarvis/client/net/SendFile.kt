package com.jarvis.client.net

import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.longOrNull
import java.io.File
import java.security.MessageDigest
import java.util.Locale
import kotlin.io.encoding.Base64
import kotlin.io.encoding.ExperimentalEncodingApi

/**
 * "Send one file from the PC to the phone" - the owner's ask of 2026-10-31,
 * verbatim: *"am i able to ask jarvis to search for a file for me and send it
 * to the jarvis android app to view and or download directly? this would be a
 * file on the desktop"*. The ceiling became **2 GiB in 1 MiB pieces** on
 * 2026-11-14 (the owner's "2 GB", design `SEND-TO-PHONE-2GB-DESIGN-2026-11-14`
 * items 1-5 and 7). The backend half is `backend/jarvis_send_file.py`
 * (docs/JARVIS-API.md section 172); this object is the whole phone-facing
 * contract.
 *
 * THREE routes, and none takes a filesystem path:
 *
 * - `GET /api/files/send` - the files the owner has already approved for this
 *   phone, waiting for it: `{id, name, folder, size_bytes, mime, expires_in}`
 *   each, plus the PC's `cap_bytes`, `chunk_bytes`, `ttl_seconds`, `single_use`
 *   and one `said` sentence. A file appears ONLY after a person approved its
 *   card.
 * - `GET /api/files/download?id=&offset=&length=` - ONE slice of ONE approved
 *   file, as base64 JSON `{offset, length, data, chunk_sha256, sha256,
 *   size_bytes, name, mime}`. `sha256` is the WHOLE file's hash and
 *   `chunk_sha256` is this slice's, so a corrupted piece is caught before it
 *   is written. A raw path is never accepted and the answer never carries one.
 * - `POST /api/files/ack` - the phone's receipt, `{"id": …}`, sent after the
 *   whole file's SHA-256 has been checked. A receipt that fails changes
 *   nothing the owner sees: the PC's own grace expires the id anyway
 *   ([readAck]).
 *
 * The PC's own rules, stated here and never reinterpreted: ONE file at a time,
 * at most [MAX_BYTES] (2 GiB), the link lasts [TTL_SECONDS] (ten minutes), and
 * the id is consumed only when the LAST slice is served - so a dropped link may
 * retry the same offset, and `single_use` means **one completed transfer**, not
 * "works once no matter what". [receive] is that retry loop, kept here, in
 * pure Kotlin, so `SendFileTest` can drive it with a fake PC.
 *
 * Two limits are this phone's own, and both are checked BEFORE a slice is
 * fetched: View is offered only at or under [VIEW_MAX_BYTES] (200 MiB; above
 * that the row says [VIEW_USE_SAVE]), and the safe two-step save needs
 * [bytesNeeded] free on the volume that holds the app cache, because the whole
 * file is cached AND then copied into Downloads (Q2/Q3, 2026-11-14).
 *
 * The phone never approves anything: the card was raised and answered on the
 * PC, and this side only lists, fetches and checks.
 *
 * Every sentence shown to the owner in the plate comes from the PC's answer
 * where the PC sent one; the fallbacks here are the app's own plain words for
 * a phone-side step (a piece that was not the one asked for, a file that
 * changed, a save that failed).
 *
 * Pure Kotlin (base64/charset/format/`java.io` only - no Android types), so
 * `SendFileTest` runs it on a plain JVM.
 */
object SendFile {
    /** The three routes, as `tools/check_parity.py` reads them. */
    const val LIST_PATH = "/api/files/send"
    const val DOWNLOAD_PATH = "/api/files/download"

    /** The phone's receipt for one finished file: `POST {"id": …}`. */
    const val ACK_PATH = "/api/files/ack"

    /**
     * The one number (design item 1): 2 GiB, written once. The PC's own
     * `cap_bytes` is read from its list answer, and a file is refused before a
     * single slice is asked for when it is over either this or that.
     */
    const val MAX_BYTES = 2L * 1024L * 1024L * 1024L

    /** The PC's slice size (design item 2): 1 MiB. `length` is never more. */
    const val CHUNK_BYTES = 1024 * 1024

    /**
     * The largest file View will hand to another app: **200 MiB** (Gemini's
     * Q3, 2026-11-14). Above it a big video would sit in this app's cache with
     * a viewer holding it open, so the row offers Save instead - a clean local
     * policy line, with no wire change.
     */
    const val VIEW_MAX_BYTES = 200L * 1024L * 1024L

    /** What the row says where View would be, above [VIEW_MAX_BYTES]. */
    const val VIEW_USE_SAVE = "Use Save for files over 200 MiB"

    /**
     * The room the safe two-step save needs, in tenths of the file's size:
     * **2.1x** (Gemini's Q2, 2026-11-14). Whole numbers, so [bytesNeeded]'s
     * ceiling is exact rather than a float that can round a byte short on a
     * 2 GiB file.
     */
    const val SPACE_TENTHS = 21L

    /** The PC's own named limits (docs/JARVIS-API.md section 172.3). */
    const val TTL_SECONDS = 10 * 60
    const val MAX_PENDING = 8

    /**
     * How many times ONE slice is asked for again after a dropped link. The PC
     * only consumes the id when the LAST slice is served, so the same offset
     * may be asked for again safely; [CHUNK_RETRY_MS] is the pause between
     * tries. Four tries rides out a Tailscale/Meshnet hiccup without turning a
     * dead PC into a two-minute wait.
     */
    const val CHUNK_TRIES = 4
    const val CHUNK_RETRY_MS = 1_000L

    /**
     * The app-private folder a download is assembled in, under `cacheDir`.
     * `res/xml/send_file_paths.xml` exposes exactly this folder to the app's
     * own `FileProvider` (`cache-path name="received" path="received/"`), so
     * View can hand the verified file to Android's viewer.
     */
    const val RECEIVED_DIR = "received"

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

    /**
     * The PC's limits, in one line the owner can read. The ceiling is the
     * single 2 GiB number above, and the old "works once" is wrong now: a
     * slice may be retried, and the receipt is sent after the whole file
     * verifies, so it is **one completed transfer**.
     */
    val LIMITS =
        "One file at a time, up to ${capWords(MAX_BYTES)}. The link lasts ten minutes, " +
            "and it is good for one completed transfer."

    /** Nothing waiting, and no PC sentence to quote. */
    const val NOTHING_WAITING = "No file is waiting for your phone right now."

    /** The PC's answer could not be read as a piece of the file at all. */
    const val UNREADABLE = "The PC's answer did not carry the file. Nothing was saved."

    /**
     * A 200 that is not a SLICE: the offset or the slice hash is missing. That
     * is the old whole-file answer (the old PC capped at 10 MiB) - an old phone
     * would save it as a broken file, so it is refused instead.
     */
    const val NOT_PIECES =
        "Your PC's Jarvis is still sending whole files rather than pieces, so nothing was " +
            "saved. Update Jarvis on the PC, then ask for the file again."

    /** A slice that is not the one this phone asked for (or the file changed under it). */
    const val WRONG_SLICE =
        "The PC sent a piece of the file this phone did not ask for, so nothing was saved. " +
            "Ask Jarvis to send it again."

    /** The whole file's sha256 disagrees, or its reported size keeps changing. */
    const val NOT_WHAT_WAS_SENT =
        "The file that arrived did not match what your PC said it was sending, so it was " +
            "not kept. Ask Jarvis to send it again."

    /** The file was edited on the PC while it was coming down. */
    const val CHANGED =
        "The file changed on your PC while it was coming down, so nothing was kept. " +
            "Ask Jarvis to send it again."

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
            val chunkBytes: Int,
            val ttlSeconds: Int,
            val singleUse: Boolean,
            val said: String,
        ) : ListReply()

        /** An older PC without the module: not a failure, nothing to draw. */
        object Missing : ListReply()

        /** The read failed: the PC's own sentence, or a plain fallback. */
        data class Refused(val said: String) : ListReply()
    }

    /**
     * ONE slice, as `GET /api/files/download` answers it.
     *
     * [Got] is a usable slice. [Broken] is something worth asking for again: a
     * 200 whose body is not a slice (a corrupt piece, the old whole-file shape,
     * a wrong size), or a 5xx - the PC saying "not right now" about a read that
     * failed for the moment. [Refused] is the PC's own final no (404 expired,
     * 409 changed, 416 at the end, 400 bad numbers): the same offset will not
     * get a different answer.
     */
    sealed class Chunk {
        data class Got(
            val offset: Long,
            val length: Int,
            val data: ByteArray,
            val sha256: String,
            val chunkSha256: String,
            val sizeBytes: Long,
            val name: String,
            val mime: String,
        ) : Chunk()

        data class Broken(val said: String) : Chunk()

        data class Refused(val said: String) : Chunk()
    }

    /**
     * What `POST /api/files/ack` came to. [Accepted] is the PC's 2xx: the id
     * is consumed now and the PC knows the file arrived whole. [Ignored] is
     * everything else, and is never shown to the owner - a 404 is a PC older
     * than the route, a 409 a receipt sent before the last piece, a 5xx or a
     * dropped link a moment's trouble. The PC's own grace expires the id
     * anyway, and the verified file stays on this phone either way.
     */
    sealed class Ack {
        data class Accepted(val said: String) : Ack()

        data class Ignored(val status: Int) : Ack()
    }

    /** What [receive] came to: the whole file arrived, or it did not. */
    sealed class Outcome {
        /** Every slice arrived and was written in order. The PC's whole-file [sha256]. */
        data class Done(
            val name: String,
            val mime: String,
            val sizeBytes: Long,
            val sha256: String,
        ) : Outcome()

        /** The PC refused (its own words), or a slice never became usable. */
        data class Refused(val said: String) : Outcome()

        /** The link failed through the whole retry budget; the app says it plainly. */
        data class Failed(val error: ApiError) : Outcome()
    }

    /**
     * ONE approved file's verified copy on this phone - the cache file is the
     * whole file and its sha256 has already been checked by the runtime. The
     * plate either opens it (View) or moves it into Downloads (Save), and only
     * then may it disappear from the cache.
     */
    sealed class Fetched {
        data class Got(
            val name: String,
            val sizeBytes: Long,
            val mime: String,
            val sha256: String,
            val file: File,
        ) : Fetched()

        data class Refused(val said: String) : Fetched()
    }

    /** How far a download has got: bytes written and the PC's whole size. */
    data class Progress(val received: Long, val total: Long)

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
            val cap = body?.num("cap_bytes") ?: MAX_BYTES
            return ListReply.Ready(
                files = files,
                capBytes = if (cap > 0) cap else MAX_BYTES,
                // A PC older than the chunking change sends no `chunk_bytes`.
                // Asking for 1 MiB is what the contract's own default is, and
                // the PC clamps rather than truncates.
                chunkBytes = ((body?.num("chunk_bytes") ?: CHUNK_BYTES.toLong()).toInt())
                    .coerceIn(1, CHUNK_BYTES),
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

    /**
     * `?id=&offset=&length=` for one slice, or null when any of them is not a
     * number this phone may put on the wire. The id must be one of the PC's
     * own shapes, so a filename or a path can never be asked for.
     */
    fun downloadPath(id: String, offset: Long, length: Int): String? {
        val clean = id.trim()
        if (!ID_SHAPE.matches(clean)) return null
        if (offset < 0L || length !in 1..CHUNK_BYTES) return null
        return DOWNLOAD_PATH + "?id=" + java.net.URLEncoder.encode(clean, "UTF-8") +
            "&offset=" + offset + "&length=" + length
    }

    /**
     * The receipt's body for one finished file - `{"id":"file_…"}` - or null
     * when [id] is not one of the PC's own id shapes, in which case no request
     * is made at all. A valid id is URL-safe characters only, so it is quoted
     * directly; no JSON library is needed to build four fields of nothing.
     */
    fun ackBody(id: String): String? {
        val clean = id.trim()
        if (!ID_SHAPE.matches(clean)) return null
        return "{\"id\":\"$clean\"}"
    }

    /**
     * `POST /api/files/ack` for ONE finished file, read. A 2xx is the PC's
     * receipt (its own `said` kept when it sent one); anything else - a 404
     * from an older PC, a 409, a 5xx, a 401/403 the caller already names - is
     * [Ack.Ignored] and the runtime says nothing about it. The id expires on
     * the PC's own grace when no receipt arrives, so a lost receipt costs the
     * owner nothing but 60 seconds of the PC's keeping the id.
     */
    fun readAck(status: Int, body: JsonObject?): Ack =
        if (status in 200..299) Ack.Accepted(sentence(body).orEmpty()) else Ack.Ignored(status)

    /**
     * `GET /api/files/download` for ONE slice, read.
     *
     * A 404/409/416/400 is the PC's own sentence and final; a 5xx is handed
     * back as retryable, because the PC is saying "not right now". A 200 is
     * checked here for the one thing this side can check by itself - the
     * slice's own sha256 - and anything else missing or self-contradictory is
     * [Chunk.Broken], which [receive] may ask for again. The WHOLE-file sha is
     * checked by the runtime after the last slice, never here.
     */
    @OptIn(ExperimentalEncodingApi::class)
    fun readChunk(status: Int, body: JsonObject?): Chunk {
        if (status !in 200..299) {
            val said = sentence(body)
                ?: "That piece of the file could not be fetched, so nothing was kept."
            // A 4xx is the PC's final word (expired, changed, past the end,
            // bad numbers). A 5xx is "not right now" on the PC - a read that
            // failed for the moment - so it gets the same retry as a dropped
            // link instead of throwing away a 2 GiB transfer.
            return if (status >= 500) Chunk.Broken(said) else Chunk.Refused(said)
        }
        val json = body ?: return Chunk.Broken(UNREADABLE)
        val text = json.str("data") ?: return Chunk.Broken(UNREADABLE)
        val bytes = runCatching { Base64.decode(text) }.getOrNull()
            ?: return Chunk.Broken(UNREADABLE)
        if (bytes.isEmpty()) return Chunk.Broken(UNREADABLE)
        // A whole-file answer from an older PC has data but no offset: refuse
        // it rather than save a file at the wrong place in the stream.
        val offset = json.num("offset") ?: return Chunk.Broken(NOT_PIECES)
        val length = json.num("length") ?: return Chunk.Broken(NOT_PIECES)
        val chunkSha = json.str("chunk_sha256") ?: return Chunk.Broken(NOT_PIECES)
        val sha = json.str("sha256") ?: return Chunk.Broken(UNREADABLE)
        val size = json.num("size_bytes") ?: return Chunk.Broken(UNREADABLE)
        if (length != bytes.size.toLong() || length > CHUNK_BYTES || offset < 0L || size <= 0L) {
            return Chunk.Broken(WRONG_SLICE)
        }
        if (!chunkSha.equals(sha256(bytes), ignoreCase = true)) {
            return Chunk.Broken(NOT_WHAT_WAS_SENT)
        }
        return Chunk.Got(
            offset = offset,
            length = length.toInt(),
            data = bytes,
            sha256 = sha,
            chunkSha256 = chunkSha,
            sizeBytes = size,
            name = json.str("name").orEmpty(),
            mime = json.str("mime").orEmpty(),
        )
    }

    /**
     * The whole download, in the only order that is honest: ask for slice 0,
     * then the next, until the PC's own `size_bytes` is reached. Nothing is
     * kept by this function; [write] is handed each slice at its own [Long]
     * offset, so a retried slice overwrites exactly the bytes it failed to
     * leave behind - which is why retrying the SAME offset is safe.
     *
     * A dropped link ([ApiResult.Failed]) is retried up to [tries]; so is a
     * [Chunk.Broken] piece. A [Chunk.Refused] is the PC's answer and stops at
     * once. The loop checks for cancellation on every slice, so a screen that
     * goes away stops asking the PC.
     *
     * [onProgress] is called after each slice is written and never says the
     * whole file arrived unless it did. The runtime then reads the written file
     * back for its sha256; this loop is pure Kotlin so a fake PC can drive it.
     */
    suspend fun receive(
        fetch: suspend (offset: Long, length: Int) -> ApiResult<Chunk>,
        write: (offset: Long, bytes: ByteArray) -> Unit,
        chunkBytes: Int = CHUNK_BYTES,
        tries: Int = CHUNK_TRIES,
        onProgress: (Progress) -> Unit = {},
        pause: suspend () -> Unit = { delay(CHUNK_RETRY_MS) },
    ): Outcome {
        val step = chunkBytes.coerceIn(1, CHUNK_BYTES)
        val budget = tries.coerceAtLeast(1)
        var offset = 0L
        var total = 0L
        var name = ""
        var mime = ""
        var sha = ""
        var attempts = 0
        while (true) {
            // A cancelled download must stop asking the PC, not just stop drawing.
            currentCoroutineContext().ensureActive()
            val want = if (total > 0L) minOf(step.toLong(), total - offset).toInt() else step
            when (val answer = fetch(offset, want)) {
                is ApiResult.Failed -> {
                    attempts += 1
                    if (attempts >= budget) return Outcome.Failed(answer.error)
                    pause()
                }
                is ApiResult.Ok -> when (val piece = answer.value) {
                    is Chunk.Refused -> return Outcome.Refused(piece.said)
                    is Chunk.Broken -> {
                        attempts += 1
                        if (attempts >= budget) return Outcome.Refused(piece.said)
                        pause()
                    }
                    is Chunk.Got -> {
                        val problem = sliceProblem(piece, offset, want, total, sha)
                        if (problem != null) {
                            attempts += 1
                            if (attempts >= budget) return Outcome.Refused(problem)
                            pause()
                        } else {
                            if (total <= 0L) {
                                total = piece.sizeBytes
                                if (total > MAX_BYTES) {
                                    return Outcome.Refused(overCapWords(total, MAX_BYTES))
                                }
                                name = piece.name
                                mime = piece.mime
                                sha = piece.sha256
                            }
                            write(offset, piece.data)
                            offset += piece.data.size
                            attempts = 0
                            onProgress(Progress(offset, total))
                            if (offset >= total) return Outcome.Done(name, mime, total, sha)
                        }
                    }
                }
            }
        }
    }

    /**
     * Why one [Chunk.Got] is not the slice that was asked for, in the app's
     * plain words, or null when it is. Pure, so the rule is tested directly:
     * the offset must be the one requested, the bytes must be exactly the
     * `length` the PC declared and no more than was asked for, the whole size
     * must be the same on every slice, and the whole-file sha must not change
     * mid-download.
     */
    fun sliceProblem(
        got: Chunk.Got,
        offset: Long,
        want: Int,
        total: Long,
        sha: String,
    ): String? = when {
        got.offset != offset -> WRONG_SLICE
        got.data.isEmpty() -> WRONG_SLICE
        got.data.size != got.length -> WRONG_SLICE
        got.data.size > want -> WRONG_SLICE
        got.sizeBytes <= 0L -> WRONG_SLICE
        offset + got.data.size > got.sizeBytes -> WRONG_SLICE
        total > 0L && got.sizeBytes != total -> CHANGED
        sha.isNotEmpty() && !got.sha256.equals(sha, ignoreCase = true) -> CHANGED
        else -> null
    }

    /** The SHA-256 of the bytes just arrived, lower-case hex - as the PC spells it. */
    fun sha256(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    /**
     * The SHA-256 of a whole file on this phone, read back from disk after the
     * last slice - the one check that proves the assembled file is the file the
     * PC named. Streams in 64 KiB pieces, so a 2 GiB file is never held in
     * memory.
     */
    fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val n = input.read(buffer)
                if (n < 0) break
                if (n > 0) digest.update(buffer, 0, n)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    /** "12,582,912 bytes received of 2,147,483,648 (0.6%)" - the download line. */
    fun progressWords(received: Long, total: Long): String {
        val got = if (received < 0) 0L else received
        if (total <= 0L) return "${grouped(got)} bytes received"
        val done = got.coerceAtMost(total)
        val percent = String.format(Locale.US, "%.1f", done * 100.0 / total)
        return "${grouped(done)} bytes received of ${grouped(total)} ($percent%)"
    }

    /** "1,482,331 bytes (1.4 MB large)" - the PC's own card style, from its numbers. */
    fun sizeWords(bytes: Long): String {
        val n = if (bytes < 0) 0L else bytes
        val human = when {
            n < 1024 -> ""
            n < 1024 * 1024 -> " (${n / 1024} KB large)"
            n < 1024L * 1024L * 1024L -> " (${"%.1f".format(n / (1024.0 * 1024.0))} MB large)"
            else -> " (${"%.1f".format(n / (1024.0 * 1024.0 * 1024.0))} GB large)"
        }
        return "${grouped(n)} bytes$human"
    }

    /**
     * A cap in the PC's own units: "2 GiB", "10 MiB" - never a bare number, and
     * never rounded to something the PC did not say. Falls back to exact bytes
     * for a cap that is not a whole unit.
     */
    fun capWords(capBytes: Long): String {
        val n = if (capBytes < 0) 0L else capBytes
        val mib = 1024L * 1024L
        val gib = mib * 1024L
        return when {
            n >= gib && n % gib == 0L -> "${n / gib} GiB"
            n >= mib && n % mib == 0L -> "${n / mib} MiB"
            n >= 1024L && n % 1024L == 0L -> "${n / 1024L} KiB"
            else -> "$n bytes"
        }
    }

    /** The phone's own pre-check, before one slice is asked for. */
    fun fitsCap(sizeBytes: Long, capBytes: Long): Boolean {
        val cap = if (capBytes > 0L) minOf(capBytes, MAX_BYTES) else MAX_BYTES
        return sizeBytes > 0L && sizeBytes <= cap
    }

    /** Why a file is not fetched at all, using both the PC's cap and the phone's. */
    fun overCapWords(sizeBytes: Long, capBytes: Long): String {
        val cap = if (capBytes > 0L) minOf(capBytes, MAX_BYTES) else MAX_BYTES
        return "That file is ${sizeWords(sizeBytes)}, bigger than the ${capWords(cap)} this phone " +
            "will fetch in one go. Nothing was fetched."
    }

    /**
     * May View open this file? At or under [VIEW_MAX_BYTES] (200 MiB), and
     * never above it (Q3). The plate asks with the list's size to decide
     * whether to draw the button at all; the plate's open step asks again with
     * the size the whole-file SHA-256 verified.
     */
    fun canView(sizeBytes: Long): Boolean = sizeBytes > 0L && sizeBytes <= VIEW_MAX_BYTES

    /**
     * How much free space the safe two-step save needs for [sizeBytes]:
     * **ceil(size x 2.1)**, because the whole file is held in the app cache
     * while it is checked and then a second copy streams into Downloads. Whole
     * numbers in tenths, so the ceiling is exact for a 2 GiB file rather than
     * a float that can land a byte short.
     */
    fun bytesNeeded(sizeBytes: Long): Long {
        val size = if (sizeBytes <= 0L) 0L else sizeBytes
        if (size > Long.MAX_VALUE / SPACE_TENTHS) return Long.MAX_VALUE
        val product = size * SPACE_TENTHS
        return product / 10L + if (product % 10L == 0L) 0L else 1L
    }

    /**
     * Is there room for this file's safe two-step save in [availableBytes]?
     * The comparison is `>=`, so exactly the needed amount is allowed and one
     * byte less is refused.
     */
    fun hasRoomFor(sizeBytes: Long, availableBytes: Long): Boolean =
        availableBytes >= bytesNeeded(sizeBytes)

    /**
     * The plain sentence for a phone without the room to keep the file: what
     * the file is, what the save needs and why, what is free, and that
     * nothing was fetched - shown BEFORE the first slice is asked for, so a
     * tight phone fails cleanly instead of filling `/data` halfway through a
     * 2 GiB file.
     */
    fun spaceWords(sizeBytes: Long, availableBytes: Long): String {
        val free = if (availableBytes < 0L) 0L else availableBytes
        return "There is not enough free space on this phone to keep that file. " +
            "It is ${sizeWords(sizeBytes)}, and saving it safely needs about " +
            "${sizeWords(bytesNeeded(sizeBytes))} free - one copy is kept while it is " +
            "checked, and then one goes to Downloads. Only ${sizeWords(free)} of free " +
            "space is left, so nothing was fetched. Free some space, then ask Jarvis to " +
            "send it again."
    }

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

    /** "expires in 9 min" / "expires in under a minute" / "expired" - from the PC's `expires_in`. */
    fun expiryWords(expiresIn: Int): String = when {
        expiresIn <= 0 -> "expired"
        expiresIn < 60 -> "expires in under a minute"
        else -> "expires in ${(expiresIn + 59) / 60} min"
    }

    /**
     * Deletes the received copies in [dir] the viewer is not using (Q3: "clean
     * up cache copies promptly") and returns how many it deleted. [keep] holds
     * the absolute paths handed to another app's viewer - a file the owner may
     * still be watching must never be pulled out from under it - and anything
     * that is not a plain file is left alone.
     */
    fun sweepReceived(dir: File, keep: Set<String>): Int {
        val files = dir.listFiles() ?: return 0
        var deleted = 0
        for (f in files) {
            if (!f.isFile || f.absolutePath in keep) continue
            if (f.delete()) deleted += 1
        }
        return deleted
    }

    /** "2,147,483,648" - the same grouping [sizeWords] uses. */
    private fun grouped(n: Long): String =
        n.toString().reversed().chunked(3).joinToString(",").reversed()
}
