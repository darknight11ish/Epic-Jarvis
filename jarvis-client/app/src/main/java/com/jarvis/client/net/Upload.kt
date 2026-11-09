package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put
import java.io.InputStream
import java.security.MessageDigest
import java.util.Base64
import java.util.Locale

/**
 * A document - or a Notion export `.zip` - sent from the phone INTO a folder
 * Jarvis already looks in, in three steps (the owner's ask of 2026-11-05; the
 * design is `.dsh-scratch/DOC-INTAKE-DESIGN-2026-11-05/DESIGN.md`, section
 * C0; the PC's half is `backend/jarvis_upload.py`, built by its own lane).
 *
 * WHY THIS FILE EXISTS AT ALL. The 2026-10-29 record said "an upload endpoint,
 * a resumable or chunked transfer ... not built, now or later"; the owner
 * asked for one on 2026-11-05, so the record is reversed for exactly those
 * words and the `decisions.d/` fragment belongs to the PC's lane. The phone's
 * job is the transport: read the file the owner picked, split it into 1 MiB
 * chunks, post them one at a time, and say in plain words what happened.
 *
 * THE THREE CALLS, and what the PC does with them:
 *  - `POST /api/upload/begin` - the name, size, type, the listed folder to go
 *    into and the purpose. For a document this is where the PC raises its ONE
 *    approval card, before a byte is written; a 202 with `waiting: true` means
 *    "nothing will move until the owner says yes".
 *  - `POST /api/upload/chunk` - one 1 MiB slice as base64. While the card is
 *    waiting the answer is 409 `{"waiting": true}`, so the phone pauses and
 *    tries the SAME slice again; it never skips ahead.
 *  - `POST /api/upload/finish` - the id alone. Only here does a document
 *    become a real file in `<the chosen folder>\From my phone\`, measured from
 *    the bytes that actually arrived.
 *
 * WHY 1 MiB. It keeps every request at about 1.4 MB of base64 + JSON, a third
 * of the PC's 4 MiB body ceiling (`AttachFile.BACKEND_MAX_BODY`), and it is
 * the same chunk size the PC's own history importer uses. The number is not
 * new to the project.
 *
 * TWO CAPS, THE OWNER'S DECISIONS: 50 MB for a document (exactly what the PC's
 * reader already handles, so nothing can be stored that Jarvis cannot open -
 * `jarvis_documents.MAX_DOC_BYTES`) and 4 GB for a Notion export (raised from
 * 250 MB on 2026-11-09, when the owner chose to send the same export from the
 * phone that the PC imports). The Notion one is the RAW ZIP BYTES that cross
 * his private network, not the PC's unpacked ceiling - that ceiling is 4 GB too,
 * but it answers a different question (what the archive expands to) and it is
 * checked on the PC. They are checked here before a byte leaves the phone, and
 * again by the PC.
 *
 * HONEST DEGRADATION. A PC without these routes answers 404 (an older backend,
 * or the upload module missing). Then the answer is [notHere] and NOTHING is
 * sent: [send] asks the PC first and only opens the file after `begin` said
 * yes. That is `net/Handsfree.kt`'s NOT_HERE shape, for the same reason - a
 * state with its own words instead of a feature that looks broken.
 *
 * NOTHING IS KEPT ON THE PHONE. The bytes are read from the provider straight
 * into the chunk being sent, and dropped. They are never written to this app's
 * storage, never in a Bundle, never logged, never in a preference - the same
 * promise [AttachFile] makes, restated for the durable path.
 *
 * PURE KOTLIN, no Android types: [measure], [send] and the four wire bodies
 * are plain functions over an [InputStream], so `UploadTest` runs the whole
 * state machine - chunk boundaries, the retry on 409, every refusal, and the
 * 404 that sends nothing - on a plain JVM.
 */
object Upload {

    /** The PC's three routes (DESIGN.md C0.1). */
    const val BEGIN_PATH = "/api/upload/begin"
    const val CHUNK_PATH = "/api/upload/chunk"
    const val FINISH_PATH = "/api/upload/finish"

    /** Raw bytes per chunk: the PC's own number, and a third of its body cap. */
    const val CHUNK_BYTES = 1_048_576

    /** Most raw bytes one document may carry - the PC's `MAX_DOC_BYTES`. */
    const val DOCUMENT_MAX = 50L * 1024 * 1024

    /** Most raw bytes one Notion export may carry, as it is sent - the owner's 4 GB (was 250 MB; raised 2026-11-09). */
    const val NOTION_MAX = 4L * 1024 * 1024 * 1024

    /** What the phone is sending. The PC reads this word, and nothing about it is a path. */
    enum class Purpose(val wire: String) {
        DOCUMENT("document"),
        NOTION("notion"),
    }

    // ------------------------------------------------------------- words ---

    /** The Folders screen's own action, under the list (DESIGN.md C0.5). */
    const val TITLE = "Send a document"

    /** The sentence under the action, and the promise behind it. */
    const val DETAIL = "Pick a document and it goes into a folder Jarvis may look in, into a " +
        "new folder called From my phone. Your PC asks you once before anything lands."

    /** A PC without the upload routes: its own state, in its own words. */
    const val NOT_HERE = "Sending a document from your phone is not available on this PC yet."

    /** The same fact for the Notion door. */
    const val NOT_HERE_NOTION =
        "Bringing in a Notion export from your phone is not available on this PC yet."

    /** The PC is holding the transfer for its ONE approval card. */
    const val WAITING = "Waiting for your yes on the PC - approve the card there and the file will follow."

    /** Everything arrived, and the PC now wants its yes before it writes the file. */
    const val SENT_WAITING = "Sent to your PC - approve the card on your PC."

    /** The card was answered no; nothing was written. */
    const val DENIED = "You said no on the PC, so nothing was saved."

    /** The upload timed out on the PC; nothing was written. */
    const val EXPIRED = "That upload timed out on the PC, so nothing was saved. Pick it again to retry."

    /** The file was empty. */
    const val EMPTY = "That file is empty, so there is nothing to send."

    /** The provider could not give the bytes at all. */
    const val UNREADABLE = "That file could not be read."

    /** The file changed size between reading it and sending it. */
    const val CHANGED = "The file changed while it was being sent. Nothing was saved - try again."

    /** Nothing was sent because the PC answered something this app does not understand. */
    const val STOPPED = "The transfer stopped before the PC had the whole file. Nothing was saved."

    /** The PC refused without a sentence of its own. */
    const val REFUSED = "Your PC did not take that file, and did not say why."

    /** A file whose kind this door does not send. */
    fun wrongKind(name: String): String =
        "$name is not a kind this door sends. Send a PDF, Word, Excel, PowerPoint, text, " +
            "Markdown or CSV file - or bring a Notion export in with the row below."

    /** A Notion pick that is not a `.zip`. */
    const val WRONG_ZIP = "That is not a .zip. In Notion, choose Settings, Export all workspace " +
        "content, as Markdown & CSV, and pick the .zip it makes."

    /** Why a document is refused for its size: the number, the cap, and the one alternative. */
    fun tooBig(bytes: Long, purpose: Purpose): String =
        "That file is ${AttachFile.sizeWords(bytes)}. " +
            (if (purpose == Purpose.NOTION) "Notion exports" else "Documents") +
            " up to ${capWords(purpose)} can be sent from your phone."

    /** The same refusal when the size is not knowable - "bigger than" is then the honest word. */
    fun overCap(purpose: Purpose): String =
        "That file is bigger than ${capWords(purpose)}. " +
            (if (purpose == Purpose.NOTION) "Notion exports" else "Documents") +
            " up to ${capWords(purpose)} can be sent from your phone."

    /**
     * The cap in the owner's own words: 50 MB for a document, 4 GB for a
     * Notion export (the 250 MB of 2026-11-05 was raised on 2026-11-09). NOT
     * [AttachFile.sizeWords] of the byte count: 50 MiB measures 52.4 MB in
     * decimal units, and the owner decided a number he can read as fifty.
     */
    fun capWords(purpose: Purpose): String =
        if (purpose == Purpose.NOTION) "4 GB" else "50 MB"

    /** The one cap for a purpose. */
    fun cap(purpose: Purpose): Long =
        if (purpose == Purpose.NOTION) NOTION_MAX else DOCUMENT_MAX

    /** What the phone says when the folder list on the PC is empty: the PC's own line. */
    const val NO_FOLDERS = "Folders are added on the PC: Settings, Folders Jarvis may look in."

    /** The line under a disabled button on a stale or missing link (rule 4). */
    const val OFFLINE = "Not connected to the desktop, so nothing can be sent until the link is back."

    /** The progress chip: real chunks sent, never a timer. */
    fun progress(name: String, sent: Int, total: Int): String =
        "Sending $name - $sent of $total"

    /** The chip while the file is still being measured (its size and SHA-256 known). */
    fun preparing(name: String): String = "Getting $name ready…"

    /** The waiting chip. */
    fun waitingLine(name: String): String = "Waiting for your yes on the PC - $name is not sent yet."

    /**
     * What the screen says after the whole transfer. [said] is the PC's own
     * sentence whenever it sent one, shown verbatim; otherwise the sentence is
     * built from the folder the PC named.
     */
    fun savedText(name: String, folder: String, said: String): String {
        val pc = said.trim()
        if (pc.isNotEmpty()) return pc
        val where = if (folder.isBlank()) "your PC" else "\"$folder\""
        return "Saved in $where. Ask Jarvis about it whenever you like."
    }

    /** The outcome of a whole send, as one plain sentence. */
    fun outcomeText(outcome: Outcome): String = when (outcome) {
        is Outcome.Saved -> savedText(outcome.name, outcome.folder, outcome.said)
        is Outcome.Waiting -> SENT_WAITING
        is Outcome.Refused -> outcome.why
        Outcome.NotHere -> NOT_HERE
        is Outcome.Uploaded -> outcome.said.ifBlank { "Your PC has the file." }
    }

    /** Whether an error means "this PC has no upload routes at all". */
    fun missing(error: ApiError): Boolean = Folders.missing(error)

    // --------------------------------------------------------- wire bodies ---

    /** What one file is, before a byte is sent. */
    class Meta(
        /** The name shown to the owner and sent to the PC - never a path. */
        val name: String,
        /** Our own type for the extension, not whatever the provider claimed. */
        val mime: String,
        /** The size measured from the bytes, not the provider's claim. */
        val size: Long,
        /** SHA-256 of the whole file, lowercase hex. */
        val sha256: String,
        val purpose: Purpose,
    )

    /**
     * `POST /api/upload/begin`'s body, exactly: `name`, `size`, `mime`,
     * `sha256`, `purpose`, and `into` for a document.
     *
     * `into` is the chosen listed folder's path, EXACTLY as `GET /api/folders`
     * returned it - it is validated on the PC by equality against that list,
     * so the phone can only use a grant the owner already gave. A Notion
     * export sends no `into`: its destination is a vault, chosen after the
     * zip is on the PC.
     *
     * `sha256` is not in DESIGN.md's begin body. It is additive - the PC can
     * ignore a key it does not read - and it is what lets the PC prove the
     * bytes it assembled are the file the phone read before it moves anything
     * into place.
     */
    fun beginBody(meta: Meta, into: String?): String = buildJsonObject {
        put("name", meta.name)
        put("size", meta.size)
        put("mime", meta.mime)
        put("sha256", meta.sha256)
        put("purpose", meta.purpose.wire)
        into?.takeIf { it.isNotBlank() }?.let { put("into", it) }
    }.toString()

    /** `POST /api/upload/chunk`'s body: `id`, `index`, and the slice as base64. */
    fun chunkBody(id: String, index: Int, data: ByteArray): String = buildJsonObject {
        put("id", id)
        put("index", index)
        put("data", Base64.getEncoder().encodeToString(data))
    }.toString()

    /** `POST /api/upload/finish`'s body: the id alone. */
    fun finishBody(id: String): String = buildJsonObject { put("id", id) }.toString()

    /** The base64 the wire carries, for a test or a caller that holds the bytes. */
    fun base64(data: ByteArray): String = Base64.getEncoder().encodeToString(data)

    // ------------------------------------------------------------- chunking ---

    /**
     * How many chunks a file of [size] bytes makes at [chunkBytes] each. The
     * size the PC answers in `begin` is honoured ([chunkBytes] defaults to its
     * own number), because a PC that wants smaller slices would refuse a 1 MiB
     * one with a 413.
     */
    fun chunks(size: Long, chunkBytes: Int = CHUNK_BYTES): Int {
        val step = chunkBytes.coerceIn(1, CHUNK_BYTES).toLong()
        return if (size <= 0L) 0 else ((size + step - 1) / step).toInt()
    }

    /** The raw length of chunk [index], for a file of [size] bytes. */
    fun chunkLength(size: Long, index: Int, chunkBytes: Int = CHUNK_BYTES): Int {
        if (size <= 0L || index < 0) return 0
        val step = chunkBytes.coerceIn(1, CHUNK_BYTES).toLong()
        val offset = index.toLong() * step
        if (offset >= size) return 0
        return minOf(step, size - offset).toInt()
    }

    // ------------------------------------------------------------- measure ---

    /** What one pass over the chosen file came to. */
    sealed interface Measured {
        /** [size] bytes and their SHA-256, lowercase hex. */
        data class Ok(val size: Long, val sha256: String) : Measured

        /** Nothing was read: the provider gave no stream. */
        data object Unreadable : Measured

        /** The file is empty. */
        data object Empty : Measured

        /** More than [limit] bytes; reading stopped as soon as that was certain. */
        data class TooBig(val limit: Long) : Measured
    }

    /**
     * One pass over the file: its real size and SHA-256, or the first refusal.
     * At most one byte over [limit] is read, so a 4 GB video is refused without
     * being read in full. Nothing is kept.
     */
    fun measure(input: InputStream, limit: Long): Measured {
        val digest = MessageDigest.getInstance("SHA-256")
        val buffer = ByteArray(64 * 1024)
        var total = 0L
        var first = true
        try {
            while (true) {
                val n = input.read(buffer)
                if (n < 0) break
                if (n == 0) continue
                first = false
                total += n
                if (total > limit) return Measured.TooBig(limit)
                digest.update(buffer, 0, n)
            }
        } catch (e: Exception) {
            return Measured.Unreadable
        }
        if (total == 0L) return Measured.Empty
        return Measured.Ok(total, hex(digest.digest()))
    }

    private fun hex(bytes: ByteArray): String {
        val out = StringBuilder(bytes.size * 2)
        for (b in bytes) {
            val v = b.toInt() and 0xff
            out.append(HEX[v ushr 4]).append(HEX[v and 0x0f])
        }
        return out.toString()
    }

    private const val HEX = "0123456789abcdef"

    // -------------------------------------------------------------- answers ---

    /** What the PC answered: the status and the JSON body. */
    data class Reply(val code: Int, val body: JsonObject?)

    /** What `begin` came to. */
    sealed interface Begin {
        data class Ok(
            val id: String,
            val waiting: Boolean,
            val chunkBytes: Int,
            val maxBytes: Long,
            val said: String,
        ) : Begin

        /** The PC's own refusal, in its own sentence. */
        data class Refused(val why: String) : Begin

        /** This PC has no upload routes. Nothing has been sent. */
        data object NotHere : Begin
    }

    /** What one chunk came to. */
    sealed interface Chunk {
        data class Sent(val received: Long) : Chunk

        /** The PC's card is still waiting: pause and send this SAME chunk again. */
        data class Waiting(val said: String) : Chunk

        /** The card was answered no. Nothing will be written. */
        data class Denied(val said: String) : Chunk

        /** The upload id expired. */
        data class Expired(val said: String) : Chunk

        /** A refusal: the PC's own sentence, or this app's. */
        data class Refused(val why: String) : Chunk
    }

    /** What `finish` came to. */
    sealed interface Finish {
        /** A document is now a real file, [name] in [folder]. */
        data class Saved(val name: String, val folder: String, val said: String) : Finish

        /** The staging copy is complete, and the next step is the caller's. */
        data class Staged(val said: String) : Finish

        /** The PC still wants its yes before it writes. */
        data class Waiting(val said: String) : Finish

        data class Refused(val why: String) : Finish

        data object NotHere : Finish
    }

    /** What a whole [send] came to. */
    sealed interface Outcome {
        data class Saved(val name: String, val folder: String, val said: String) : Outcome

        /** Every byte is on the PC, and its card is still waiting. */
        data class Waiting(val said: String) : Outcome

        /** A Notion export is staged on the PC under [id]; the import is the next call. */
        data class Uploaded(val id: String, val said: String) : Outcome

        data class Refused(val why: String) : Outcome

        /** This PC has no upload routes. Nothing was read and nothing was sent. */
        data object NotHere : Outcome
    }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()
            ?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.booleanOrNull

    private fun JsonObject.whole(key: String): Long? =
        (this[key] as? JsonPrimitive)?.longOrNull

    private fun JsonObject.wholeInt(key: String): Int? =
        (this[key] as? JsonPrimitive)?.intOrNull

    /** The PC's reason, from the fields its routes use for one. */
    private fun reason(body: JsonObject?): String? =
        (body?.text("said") ?: body?.text("reason") ?: body?.text("error") ?: body?.text("message"))

    /**
     * `begin` read. 404 (and 501/503, the same "no such route / not running"
     * family [Folders.missing] uses) is [Begin.NotHere]; any other answered
     * status with a sentence is the PC's own refusal, shown as sent.
     */
    fun readBegin(reply: Reply): Begin {
        val body = reply.body
        if (reply.code == 404 || reply.code == 501 || reply.code == 503) return Begin.NotHere
        if (reply.code in 200..299) {
            val id = body?.text("id") ?: return Begin.Refused(reason(body) ?: REFUSED)
            return Begin.Ok(
                id = id,
                waiting = body.flag("waiting") ?: (reply.code == 202),
                chunkBytes = body.wholeInt("chunk_bytes")?.takeIf { it in 1..CHUNK_BYTES }
                    ?: CHUNK_BYTES,
                maxBytes = body.whole("max_bytes") ?: 0L,
                said = reason(body).orEmpty(),
            )
        }
        return Begin.Refused(reason(body) ?: if (reply.code == 403) DENIED else REFUSED)
    }

    /**
     * One chunk read. A 409 whose body says `waiting` (or says nothing else) is
     * the card, not a failure: the caller retries the same slice. A 403 that
     * says `denied` is the owner's no; a 403 without it is a refusal like any
     * other (the pairing token is checked a layer above, by `JarvisApi`).
     */
    fun readChunk(reply: Reply): Chunk {
        val body = reply.body
        if (reply.code == 404) return Chunk.Expired(reason(body) ?: EXPIRED)
        if (reply.code in 200..299) {
            if (body?.flag("ok") == false) {
                if (body.flag("waiting") == true) return Chunk.Waiting(reason(body) ?: WAITING)
                return Chunk.Refused(reason(body) ?: REFUSED)
            }
            if (body?.flag("waiting") == true) return Chunk.Waiting(reason(body) ?: WAITING)
            return Chunk.Sent(body?.whole("received") ?: 0L)
        }
        return when (reply.code) {
            403 -> if (body?.flag("denied") == true) {
                Chunk.Denied(reason(body) ?: DENIED)
            } else {
                Chunk.Refused(reason(body) ?: REFUSED)
            }
            409 -> if (body?.flag("waiting") == false) {
                Chunk.Refused(reason(body) ?: STOPPED)
            } else {
                Chunk.Waiting(reason(body) ?: WAITING)
            }
            410 -> Chunk.Expired(reason(body) ?: EXPIRED)
            413 -> Chunk.Refused(reason(body) ?: "That file is bigger than this PC takes.")
            else -> Chunk.Refused(reason(body) ?: REFUSED)
        }
    }

    /** `finish` read: a saved file, a staged export, a waiting card, or the PC's refusal. */
    fun readFinish(reply: Reply): Finish {
        val body = reply.body
        if (reply.code == 404) return Finish.NotHere
        val ok = body?.flag("ok")
        if (reply.code in 200..299 && ok != false) {
            if (body?.flag("waiting") == true) return Finish.Waiting(reason(body) ?: WAITING)
            if (body?.flag("saved") == true) {
                return Finish.Saved(
                    name = body.text("name").orEmpty(),
                    folder = body.text("folder").orEmpty(),
                    said = reason(body).orEmpty(),
                )
            }
            return Finish.Staged(reason(body).orEmpty())
        }
        if (reply.code == 403 && body?.flag("denied") == true) {
            return Finish.Refused(reason(body) ?: DENIED)
        }
        if (reply.code == 409) return Finish.Waiting(reason(body) ?: WAITING)
        if (reply.code == 410) return Finish.Refused(reason(body) ?: EXPIRED)
        if (reply.code == 413) return Finish.Refused(reason(body) ?: "That file is bigger than this PC takes.")
        return Finish.Refused(reason(body) ?: REFUSED)
    }

    // ------------------------------------------------------------ the send ---

    /**
     * How many times one chunk is re-tried while the PC's card waits, by
     * default. The PC's own approval window is 900 s; the runtime's pause
     * backs off to 30 s, so 450 is far more than the ~33 retries that window
     * really takes, and the PC's own expiry answers 403/410 first when the
     * owner never answers.
     */
    const val WAITS = 450

    /**
     * The whole transfer, in the only order that is honest: ASK THE PC FIRST
     * ([begin]), then read the file and send its chunks, then [finish].
     *
     * [open] is called only after `begin` answered - so a 404 or a refusal
     * means the file was never opened. That is the "nothing is sent" state
     * this class promises, and `UploadTest` holds it with a counter.
     *
     * A 409 while the card waits does NOT fail the transfer: [pause] runs and
     * the same slice is posted again, up to [waits] times. When the budget is
     * spent the outcome is [Outcome.Waiting] and the screen says so; the PC
     * deletes its staging copy when its id expires.
     */
    suspend fun send(
        meta: Meta,
        into: String?,
        open: () -> InputStream?,
        begin: suspend (String) -> Reply,
        chunk: suspend (String) -> Reply,
        finish: suspend (String) -> Reply,
        onProgress: (sent: Int, total: Int) -> Unit = { _, _ -> },
        onWaiting: (String) -> Unit = {},
        waits: Int = WAITS,
        pause: suspend () -> Unit = {},
    ): Outcome {
        // 1. The PC first. A PC without the routes never sees the file.
        val began = readBegin(begin(beginBody(meta, into)))
        val start = when (began) {
            Begin.NotHere -> return Outcome.NotHere
            is Begin.Refused -> return Outcome.Refused(began.why)
            is Begin.Ok -> began
        }
        if (start.waiting) onWaiting(start.said.ifBlank { WAITING })

        // 2. The bytes, one chunk at a time, from a stream that is never kept.
        val input = try {
            open()
        } catch (e: Exception) {
            null
        } ?: return Outcome.Refused(UNREADABLE)

        val total = chunks(meta.size, start.chunkBytes)
        onProgress(0, total)
        input.use { stream ->
            var index = 0
            var waitingSpent = 0
            var read = 0L
            val buffer = ByteArray(start.chunkBytes)
            while (index < total) {
                val want = chunkLength(meta.size, index, start.chunkBytes)
                val data = try {
                    readExactly(stream, buffer, want)
                } catch (e: Exception) {
                    null
                } ?: return Outcome.Refused(if (read == 0L) UNREADABLE else CHANGED)
                read += want
                while (true) {
                    val reply = chunk(chunkBody(start.id, index, data))
                    when (val answer = readChunk(reply)) {
                        is Chunk.Sent -> {
                            index += 1
                            onProgress(index, total)
                            break
                        }
                        is Chunk.Waiting -> {
                            onWaiting(answer.said.ifBlank { WAITING })
                            if (waitingSpent >= waits) return Outcome.Waiting(answer.said.ifBlank { WAITING })
                            waitingSpent += 1
                            pause()
                        }
                        is Chunk.Denied -> return Outcome.Refused(answer.said)
                        is Chunk.Expired -> return Outcome.Refused(answer.said)
                        is Chunk.Refused -> return Outcome.Refused(answer.why)
                    }
                }
            }
            // No extra byte may be waiting: that would mean the file grew.
            val extra = try {
                stream.read()
            } catch (e: Exception) {
                -1
            }
            if (extra != -1) return Outcome.Refused(CHANGED)
        }

        // 3. Only now does the PC make it real (or answer the Notion plan).
        return when (val end = readFinish(finish(finishBody(start.id)))) {
            is Finish.Saved -> {
                // A missing name/folder in the answer is not a failure: the PC's
                // sentence is the outcome, and the screen shows it as sent.
                if (meta.purpose == Purpose.NOTION) {
                    Outcome.Uploaded(start.id, end.said)
                } else {
                    Outcome.Saved(
                        name = end.name.ifBlank { meta.name },
                        folder = end.folder,
                        said = end.said,
                    )
                }
            }
            is Finish.Staged -> Outcome.Uploaded(start.id, end.said)
            is Finish.Waiting -> Outcome.Waiting(end.said)
            is Finish.Refused -> Outcome.Refused(end.why)
            Finish.NotHere -> Outcome.NotHere
        }
    }

    /** Exactly [want] bytes, or null when the stream ended first. */
    private fun readExactly(input: InputStream, buffer: ByteArray, want: Int): ByteArray? {
        val out = ByteArray(want)
        var got = 0
        while (got < want) {
            val n = input.read(buffer, 0, minOf(buffer.size, want - got))
            if (n < 0) return null
            if (n == 0) continue
            System.arraycopy(buffer, 0, out, got, n)
            got += n
        }
        return out
    }

    /**
     * The first refusal for a pick, said before a byte is read, or null when
     * the pick is worth measuring. The name's extension decides the kind - a
     * provider's MIME type is only a fallback for a name with none, the same
     * rule [AttachFile.kindFor] uses, so a `.zip` a provider mislabels can
     * never be let through the document door.
     */
    fun refusal(name: String?, mime: String?, stated: Long, purpose: Purpose): String? {
        val shown = AttachFile.shownName(name)
        if (stated > cap(purpose)) return tooBig(stated, purpose)
        if (purpose == Purpose.NOTION) {
            val ext = shown.substringAfterLast('.', "").lowercase(Locale.ROOT)
            if (ext != "zip") return WRONG_ZIP
            return null
        }
        if (AttachFile.kindFor(name, mime) == null) return wrongKind(shown)
        return null
    }
}
