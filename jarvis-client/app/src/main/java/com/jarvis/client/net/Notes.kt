package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.longOrNull

/**
 * The Notes editor, from the phone - the desktop's four routes
 * (`.dsh-scratch/NOTES-EDITOR-2026-10-31/CONTRACT.md`; the backend half is
 * `jarvis_notes_edit.py`):
 *
 * - `GET /api/notes/list?q=` - every `.md`/`.txt` note in the owner's Obsidian
 *   vault: path, title, size and mtime, newest first, at most 2,000 rows and
 *   `truncated: true` when there were more. Never note text.
 * - `GET /api/notes/read?path=` - one note's text, its sha256, size and mtime.
 * - `POST /api/notes/save` - the text, the path, and the sha256 the edit
 *   started from. The desktop raises ONE existing approval card
 *   (`edit_vault_note`, tier `ask`) and answers `waiting`; the write happens
 *   only after the owner approves it. A denied card writes nothing; a hash
 *   that no longer matches answers `conflict` and writes nothing.
 * - `GET /api/notes/save?id=` - how that save ended: `waiting`, `saved`,
 *   `denied` or `failed`, with the desktop's own plain sentence.
 *
 * The phone NEVER approves anything itself (`CLAUDE.md` rule 4): this object
 * only reads the desktop's answers and says them. Every sentence shown comes
 * from the PC's answer where the PC gave one; the fallbacks here follow the
 * shape note filing and the wiki builder already use ([Approvals.WHERE] for a
 * waiting card).
 *
 * Pure, no Android: `NotesContractTest`.
 */
object Notes {
    const val LIST_PATH = "/api/notes/list"
    const val READ_PATH = "/api/notes/read"
    const val SAVE_PATH = "/api/notes/save"

    /** Ask about a save every two seconds - the note-filing card's own rate. */
    const val POLL_MS = 2_000L

    /** A little over the PC gate's own 180-second approval timeout. */
    const val GIVE_UP_MS = 200_000L

    /** Over this a note is refused with 413, by the contract. */
    const val MAX_BYTES = 2L * 1024L * 1024L

    /** The most rows an answer may carry before it says `truncated`. */
    const val MAX_LISTED = 2_000

    /** The search text is bounded; longer than this is cut, not sent whole. */
    const val MAX_QUERY = 200

    /** Why Save is greyed while the link is stale (the same rule as [Wiki.STALE]). */
    const val STALE =
        "Not connected to the desktop, so saving waits until the link is back. " +
            "You can read what is already open; nothing is written."

    /** One row of the list. [mtime] is the PC's epoch seconds, as the contract sends it. */
    data class Note(val path: String, val title: String, val size: Long, val mtime: Double)

    /** `GET /api/notes/list`'s answer. */
    data class View(
        /** The vault folder, for display only - the phone never builds a path from it. */
        val root: String,
        val count: Int,
        val notes: List<Note>,
        val truncated: Boolean,
    )

    /** `GET /api/notes/read`'s answer. */
    data class Text(val path: String, val text: String, val sha256: String, val size: Long, val mtime: Double)

    /**
     * What to show for one save answer. [final] means no more polling; [saved]
     * is only true when the desktop said the note really was written;
     * [conflict] means nothing was written and the note changed under the edit.
     */
    data class Said(
        val text: String,
        val final: Boolean,
        val saved: Boolean,
        val conflict: Boolean = false,
        /** The note's sha256 after a save (or its current one after a conflict). */
        val sha256: String? = null,
    )

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.long(key: String): Long =
        (this[key] as? JsonPrimitive)?.longOrNull ?: (this[key] as? JsonPrimitive)?.doubleOrNull?.toLong() ?: 0L

    private fun JsonObject.double(key: String): Double =
        (this[key] as? JsonPrimitive)?.doubleOrNull ?: 0.0

    /** `/api/notes/list`, with the search text when there is one. */
    fun listPath(query: String): String {
        val q = query.trim().take(MAX_QUERY)
        if (q.isEmpty()) return LIST_PATH
        return LIST_PATH + "?q=" + java.net.URLEncoder.encode(q, "UTF-8")
    }

    /** `/api/notes/read` for one vault-relative path. */
    fun readPath(path: String): String =
        READ_PATH + "?path=" + java.net.URLEncoder.encode(path, "UTF-8")

    /** `/api/notes/save` for one job id - the same route, no body. */
    fun statusPath(id: String): String =
        SAVE_PATH + "?id=" + java.net.URLEncoder.encode(id, "UTF-8")

    /**
     * The save body: the path, the whole text, and the hash the edit started
     * from. Null only when no path was named - an EMPTY note is a real note
     * and must be savable, so an empty [text] is not refused here.
     */
    fun saveBody(path: String, text: String, expectedSha256: String): String? {
        val p = path.trim()
        if (p.isEmpty()) return null
        val pathJson = JarvisApi.quote(p)
        val textJson = JarvisApi.quote(text)
        val shaJson = JarvisApi.quote(expectedSha256.trim())
        return """{"path":$pathJson,"text":$textJson,"expected_sha256":$shaJson}"""
    }

    /** Reads the list answer. A note without a path is skipped, never invented. */
    fun view(answer: JsonObject): View {
        val notes = (answer["notes"] as? JsonArray).orEmpty().mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val path = o.str("path") ?: return@mapNotNull null
            Note(
                path = path,
                title = o.str("title") ?: titleOf(path),
                size = o.long("size"),
                mtime = o.double("mtime"),
            )
        }
        return View(
            root = answer.str("root").orEmpty(),
            // `count` is the number the answer carries; the array is what is
            // drawn, so a missing count falls back to the rows really sent.
            count = (answer["count"] as? JsonPrimitive)?.intOrNull ?: notes.size,
            notes = notes,
            truncated = (answer["truncated"] as? JsonPrimitive)?.booleanOrNull == true,
        )
    }

    /** Reads one note's answer, or null when it did not carry the three things a note needs. */
    fun readNote(answer: JsonObject): Text? {
        val path = answer.str("path") ?: return null
        val text = (answer["text"] as? JsonPrimitive)?.contentOrNull ?: return null
        val sha = answer.str("sha256") ?: return null
        return Text(
            path = path,
            text = text,
            sha256 = sha,
            size = answer.long("size"),
            mtime = answer.double("mtime"),
        )
    }

    /** A path's name, extension dropped, as the last-resort title. */
    fun titleOf(path: String): String =
        path.substringAfterLast('/').substringAfterLast('\\').removeSuffix(".md").removeSuffix(".txt")

    /** "812 B" / "12 KB" for a list row; never a false precision. */
    fun sizeLabel(bytes: Long): String = when {
        bytes < 0 -> ""
        bytes < 1024 -> "$bytes B"
        bytes < 1024 * 1024 -> "${bytes / 1024} KB"
        else -> "${bytes / (1024 * 1024)} MB"
    }

    /** The desktop's `error` strings are lower-case fragments; shown as a sentence. */
    private fun asSentence(s: String): String =
        s.replaceFirstChar { it.uppercase() }.let { if (it.last() in ".!?") it else "$it." }

    fun jobId(answer: JsonObject): String? = answer.str("id")

    /**
     * What to show for one save answer - the POST's first answer, or any
     * `GET /api/notes/save?id=` poll. The PC's own `message` wins; without one
     * its `error` fragment is shown as a sentence; only then a fixed line.
     *
     * The `waiting` fallback says the card is on the PC or Home, exactly where
     * the phone raises every other card ([Approvals.WHERE]); the design's
     * minute-level countdown lives on that card's own UI, not in this line.
     */
    fun describe(answer: JsonObject): Said {
        val said = answer.str("message")
        val error = answer.str("error")?.let(::asSentence)
        val sha = answer.str("sha256") ?: answer.str("current_sha256")
        return when (answer.str("state")) {
            "waiting" -> Said(
                said ?: "Waiting for your approval to save this note. ${Approvals.WHERE} Nothing is written until you do.",
                final = false,
                saved = false,
            )
            "saved" -> Said(said ?: "Saved.", final = true, saved = true, sha256 = sha)
            "denied" -> Said(
                said ?: "The card was denied, so this note was not saved. It is unchanged.",
                final = true,
                saved = false,
            )
            "failed" -> Said(
                said ?: error ?: "Not saved. The note is unchanged.",
                final = true,
                saved = false,
            )
            "conflict" -> Said(
                said ?: "This note changed on your PC since you opened it, so nothing was written. " +
                    "Reload it to get the newer version.",
                final = true,
                saved = false,
                conflict = true,
                sha256 = sha,
            )
            null -> {
                // A refusal answered before any job started (`{"ok": false,
                // "error": ...}`) has no state - shown as its sentence, final.
                if (error != null) {
                    Said(error, final = true, saved = false)
                } else {
                    Said(
                        "The desktop answered, but did not say whether the note was saved. Check it on your PC.",
                        final = true,
                        saved = false,
                    )
                }
            }
            else -> Said(
                error ?: said ?: "The desktop answered, but did not say whether the note was saved. Check it on your PC.",
                final = true,
                saved = false,
            )
        }
    }

    /**
     * Said when the phone stopped following a save that was still waiting. It
     * is not a failure: the card can still be approved on the PC, and the
     * note's own text decides nothing.
     */
    const val GAVE_UP =
        "Still waiting for your approval to save this note. " + Approvals.WHERE + " Nothing is written until you do."

    /** A failed request, in words. `null` means use the generic sentence. */
    fun failure(e: ApiError): String? = when (e) {
        ApiError.NotFound ->
            "This desktop has no notes editor yet - its backend needs the notes-edit plugin " +
                "(run apply-patches.ps1 on the PC). Nothing was changed."
        ApiError.NotAvailable ->
            "Your PC has no Obsidian vault set up yet, so the notes editor has nothing to show. " +
                "Set [notes.obsidian] vault_directory in jarvis-framework.toml (docs/INSTALL.md, Notes)."
        else -> null
    }
}
