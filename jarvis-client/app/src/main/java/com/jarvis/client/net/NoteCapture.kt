package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * Filing a note in Logseq or Joplin from the phone - the desktop's
 * `POST /api/notes/capture` (`backend/note-capture.patch`).
 *
 * The owner's own words go to the desktop with no model involved. The
 * desktop writes them through its approval gate, under the owner's own
 * rules for `append_logseq_journal` / `create_joplin_note`, and answers with
 * a job whose `state` is:
 *
 * - `filed` - written, and read back. Only then does the phone say "Filed".
 * - `waiting` - an approval card is up; ask again with [statusPath].
 * - `not_filed` / `failed` - with the desktop's own reason in `message`.
 *
 * Every sentence shown comes from that answer. The phone never decides on
 * its own that a note landed - the widget this replaces on the desktop could
 * only ever say "Sent", and this is the fix for that on both devices.
 */
object NoteCapture {
    const val PATH = "/api/notes/capture"
    const val POLL_MS = 2_000L

    /** A little over the desktop gate's own 180-second approval timeout. */
    const val GIVE_UP_MS = 200_000L

    /** The request body, or null when there is nothing to file. */
    fun body(target: String, text: String): String? {
        val t = text.trim()
        if (t.isEmpty()) return null
        val where = if (target.trim().lowercase() == "joplin") "joplin" else "logseq"
        return """{"target":${JarvisApi.quote(where)},"text":${JarvisApi.quote(t)}}"""
    }

    fun statusPath(id: String): String =
        PATH + "?id=" + java.net.URLEncoder.encode(id, "UTF-8")

    /** What to show for one answer. */
    data class Said(val text: String, val final: Boolean, val filed: Boolean)

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    fun jobId(job: JsonObject): String? = job.str("id")

    fun describe(job: JsonObject, target: String): Said {
        val place = if (target.trim().lowercase() == "joplin") "Joplin" else "Logseq"
        val said = job.str("message")
        return when (job.str("state")) {
            "filed" -> Said(said ?: "Filed in $place.", final = true, filed = true)
            "waiting" -> Said("Waiting for your approval on the desktop to file this in $place.",
                final = false, filed = false)
            "not_filed", "failed" -> Said(said ?: "Not filed in $place.", final = true, filed = false)
            else -> Said("The desktop answered, but did not say whether the note was filed. Check $place.",
                final = true, filed = false)
        }
    }

    /** Said when the desktop stopped answering while a card was still up. */
    const val GAVE_UP = "Still waiting for approval on the desktop. Nothing is filed until you answer the card."

    /** A failed request, in words. `null` means use the generic sentence. */
    fun failure(e: ApiError): String? = when (e) {
        ApiError.NotFound ->
            "This desktop cannot file notes yet - its backend needs the note-capture patch. Nothing was filed."
        else -> null
    }
}
