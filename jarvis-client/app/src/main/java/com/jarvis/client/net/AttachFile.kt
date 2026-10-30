package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.util.Base64
import java.util.Locale

/**
 * A document sent in chat, and the numbers that keep it inside what the PC accepts.
 *
 * ONE FILE, ONE QUESTION, ONE TURN. The file the owner picks rides inside the
 * newest user message as one `attachment` object - `name`, `mime`, `size` and
 * the raw bytes as base64 - with `has_file: true` beside `has_image`
 * (docs/JARVIS-API.md, "A file in chat"; the design is
 * `.dsh-scratch/FILE-UPLOAD-FEASIBILITY-2026-10-29/REPORT.md` section 8).
 * Nothing is uploaded: there is no route for it, no temp folder, no lifetime.
 * It is read on the owner's PC, within the turn it was sent with, and nowhere
 * else.
 *
 * NOTHING HERE IS KEPT. The bytes are held in memory until the send returns,
 * then dropped. They are never written to this app's storage, never in a
 * Bundle, never in a preference, never logged, and never in the conversation
 * ([ChatHistory] keeps the WORDS only, so a later question cannot re-send the
 * file - the owner attaches it again if they want to ask something else).
 *
 * THE PC DOES THE READING. The phone does not extract text, render a page or
 * preview anything: the PC turns the bytes into at most 12,000 characters with
 * the same converter `my_files` already uses, and the answer says how much was
 * left out. A picture is NOT one of these - it keeps its own path
 * ([ChatPicture]), which covers secrets with black boxes before any model
 * sees it.
 *
 * THE CAP IS THE REASON THIS FILE EXISTS. Base64 grows the bytes by a third, so
 * 2,500,000 bytes becomes 3,333,336 characters of JSON; with the most
 * conversation this app sends (18,000 characters) that is about 3.35 MB,
 * comfortably under the PC's `MAX_BODY` of 4 MiB ([BACKEND_MAX_BODY], the same
 * number as [ChatPicture.BACKEND_MAX_BODY]). A bigger file is not an upload
 * problem - it is a "put it in a folder Jarvis may look in" problem, which the
 * PC already solves, so a refusal says exactly that.
 *
 * `picked` is pure and takes the bytes the caller read, so a JVM test can hold
 * every refusal and the exact wire shape still. The Android half - the system
 * file picker, `OpenableColumns.DISPLAY_NAME`, reading at most one byte over
 * the cap - is in `MainActivity`, the same way the custom-voice WAV picker is.
 */
object AttachFile {

    /** Most raw bytes one attachment may carry. */
    const val MAX_BYTES = 2_500_000

    /** The PC's `MAX_BODY`: the whole `/api/chat` request, in bytes. */
    const val BACKEND_MAX_BODY = ChatPicture.BACKEND_MAX_BODY

    /** One kind the PC already reads with `my_files`, named by its extension. */
    class Kind(val extension: String, val mime: String, val label: String)

    private const val DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    private const val XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    private const val PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

    /** The eight extensions - the seven `my_files` kinds, with `.md` written both ways. */
    val KINDS: List<Kind> = listOf(
        Kind("pdf", "application/pdf", "PDF"),
        Kind("docx", DOCX, "Word"),
        Kind("xlsx", XLSX, "Excel"),
        Kind("pptx", PPTX, "PowerPoint"),
        Kind("md", "text/markdown", "Markdown"),
        Kind("markdown", "text/markdown", "Markdown"),
        Kind("txt", "text/plain", "text"),
        Kind("csv", "text/csv", "CSV"),
    )

    /**
     * The system picker's own filter. Narrow on purpose: a picker offering
     * every type would let the owner choose a 400 MB video and learn the cap
     * from a refusal instead of from the list.
     */
    val MIME_TYPES: Array<String> = KINDS.map { it.mime }.distinct().toTypedArray()

    /** A file ready to send, held in memory only. */
    class Ready(
        /** The name shown to the owner and sent to the PC - never a path. */
        val name: String,
        /** Our own type for the extension, not whatever the provider claimed. */
        val mime: String,
        /** The raw size in bytes. */
        val size: Int,
        /** The raw bytes, base64 - the wire field, with no `data:` prefix. */
        val base64: String,
    ) {
        /** Never the bytes: a data class's toString would print the whole file. */
        override fun toString(): String = "AttachFile.Ready($name, $size bytes)"
    }

    /** What one pick came to. */
    sealed interface Picked {
        class Ok(val file: Ready) : Picked
        class Refused(val why: String) : Picked
    }

    /** "Read on your PC." - the chip's own words, and the promise behind them. */
    const val READ_ON_PC = "Read on your PC."

    /**
     * The rest of the chip. The PC records a file as outside text, so a later
     * web search or note in the same chat still asks first - correct, and
     * surprising, so the chip says it.
     */
    const val OUTSIDE_TEXT =
        "The words count as outside text, so a web search in this chat will still ask first."

    /** The chip under the composer while a file is attached. */
    fun attachedLine(f: Ready): String = "${f.name} \u2014 ${sizeWords(f.size)}. $READ_ON_PC $OUTSIDE_TEXT"

    /** A sentence for a file the picker could not read at all. */
    const val UNREADABLE = "That file could not be read."

    /**
     * Why a file this big is refused: the number, the cap, and the one thing
     * that does work for a bigger file - a folder the PC may look in.
     */
    fun tooBig(bytes: Long): String =
        "That file is ${sizeWords(bytes)}. Files up to ${sizeWords(MAX_BYTES)} can be attached. " +
            FOLDER_ALTERNATIVE

    /**
     * The same refusal when the real size is not knowable - the provider did
     * not say it, and the cap was reached while reading. Saying "bigger than"
     * is honest; saying an exact number here would be invented.
     */
    fun overCap(): String =
        "That file is bigger than ${sizeWords(MAX_BYTES)}. Files up to ${sizeWords(MAX_BYTES)} " +
            "can be attached. " + FOLDER_ALTERNATIVE

    /** The one thing that works for a file too big for chat. */
    const val FOLDER_ALTERNATIVE = "For a bigger one, put it in a folder Jarvis may look in and ask about it there."

    /** Why this kind is refused: what IS read, and the same folder alternative. */
    fun wrongKind(name: String): String =
        "$name is not a kind Jarvis reads in chat. Attach a PDF, Word, Excel, PowerPoint, " +
            "text, Markdown or CSV file - or put it in a folder Jarvis may look in."

    /**
     * One pick, decided here rather than in the Activity: the size cap first
     * (a 40 MB file is refused before anything else is said about it), then
     * the kind, then the base64.
     *
     * [mime] is only a fallback for a file whose name has NO extension - a
     * document a provider named "taxes" and typed `application/pdf`. A name
     * that does have an extension is decided by that extension alone, so a
     * `.zip` a provider mislabels cannot be let in on the provider's word.
     * When the extension is one of ours, OUR type goes on the wire, because
     * the PC checks the bytes against the type they claim to be.
     */
    fun picked(bytes: ByteArray, name: String?, mime: String? = null): Picked {
        val shown = shownName(name)
        if (bytes.size > MAX_BYTES) return Picked.Refused(overCap())
        val kind = kindFor(name, mime) ?: return Picked.Refused(wrongKind(shown))
        if (bytes.isEmpty()) return Picked.Refused(UNREADABLE)
        return Picked.Ok(Ready(shown, kind.mime, bytes.size, base64(bytes)))
    }

    /**
     * The kind a pick really is: the name's extension first, and a provider's
     * MIME type only when the name has no extension at all.
     */
    fun kindFor(name: String?, mime: String?): Kind? =
        kindOf(name) ?: (if (hasNoExtension(name)) kindForMime(mime) else null)

    /** The raw bytes as the wire's `data` field: base64, no `data:` prefix. */
    fun base64(bytes: ByteArray): String = Base64.getEncoder().encodeToString(bytes)

    /**
     * The `attachment` object, exactly: `name`, `mime`, `size`, `data`. No
     * `type`, no `data:` prefix, no nesting - the PC reads these four keys.
     */
    fun part(f: Ready): JsonObject = buildJsonObject {
        put("name", f.name)
        put("mime", f.mime)
        put("size", f.size)
        put("data", f.base64)
    }

    /** The kind a file's extension names, or null when the list does not read it. */
    fun kindOf(name: String?): Kind? {
        val base = baseName(name) ?: return null
        val dot = base.lastIndexOf('.')
        if (dot <= 0 || dot == base.length - 1) return null
        val ext = base.substring(dot + 1).lowercase(Locale.ROOT)
        return KINDS.firstOrNull { it.extension == ext }
    }

    /** The kind a provider's MIME type names, for a file with no usable extension. */
    fun kindForMime(mime: String?): Kind? {
        val m = mime?.trim()?.lowercase(Locale.ROOT)?.substringBefore(';') ?: return null
        if (m.isEmpty()) return null
        return KINDS.firstOrNull { it.mime == m }
    }

    /**
     * Whether a name has no extension at all, which is the ONLY case where a
     * provider's MIME type is trusted ([picked]). `.env` and `taxes.zip` both
     * have a dot, so neither gets the fallback.
     */
    fun hasNoExtension(name: String?): Boolean {
        val base = baseName(name) ?: return true
        return !base.contains('.')
    }

    /**
     * The name to show and to send: the file's own basename, with any folder
     * taken off (a `DISPLAY_NAME` from a provider can be a full path), every
     * control character removed, and a sane length - keeping the extension
     * when it has to cut, because the PC decides what a file IS from its name.
     * Never blank.
     */
    fun shownName(raw: String?): String {
        val base = baseName(raw) ?: return NO_NAME
        val cleaned = base.filter { it.code >= 0x20 && it.code != 0x7f }.trim()
        val capped = if (cleaned.length <= NAME_MAX) {
            cleaned
        } else {
            val dot = cleaned.lastIndexOf('.')
            val ext = if (dot > 0 && cleaned.length - dot <= MAX_EXTENSION) cleaned.substring(dot) else ""
            cleaned.substring(0, NAME_MAX - ext.length) + ext
        }
        return capped.ifBlank { NO_NAME }
    }

    /** Longest extension kept when a name has to be cut. */
    const val MAX_EXTENSION = 12

    /** What a file with no usable name is called on screen and on the wire. */
    const val NO_NAME = "file"

    /** Longest name kept. Long enough for a real document, short enough for a chip. */
    const val NAME_MAX = 120

    private fun baseName(raw: String?): String? {
        val s = raw?.trim()?.takeIf { it.isNotEmpty() } ?: return null
        val cut = maxOf(s.lastIndexOf('/'), s.lastIndexOf('\\'))
        return s.substring(cut + 1).takeIf { it.isNotEmpty() }
    }

    /**
     * A size in the words the owner reads: decimal units, so 2,500,000 bytes
     * is "2.5 MB" - the same number the cap says.
     */
    fun sizeWords(bytes: Long): String {
        val n = bytes.coerceAtLeast(0)
        if (n >= 1_000_000) {
            val tenths = (n + 50_000L) / 100_000L
            return if (tenths % 10L == 0L) "${tenths / 10} MB" else "${tenths / 10}.${tenths % 10} MB"
        }
        if (n >= 1_000) return "${(n + 500L) / 1_000L} KB"
        return "$n bytes"
    }

    /** The same, for the byte counts this app holds as an `Int`. */
    fun sizeWords(bytes: Int): String = sizeWords(bytes.toLong())
}
