package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * Filing a note in Logseq, Joplin or Obsidian from the phone - the desktop's
 * `POST /api/notes/capture` (`backend/note-capture.patch`).
 *
 * Only the note apps the desktop says are set up are offered: `GET` on the
 * same path with no id answers `{"ok": true, "targets": [...]}`, names only
 * (see [targets]). If that cannot be read, none are offered, and the plate
 * says why.
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

    /** The three note apps, in the desktop's order. */
    val ALL: List<String> = listOf("logseq", "joplin", "obsidian")

    /** The desktop's name for a target. Anything unknown is the journal, as before. */
    fun normal(target: String): String = when (target.trim().lowercase()) {
        "joplin" -> "joplin"
        "obsidian" -> "obsidian"
        else -> "logseq"
    }

    /** The name people see. */
    fun name(target: String): String = when (normal(target)) {
        "joplin" -> "Joplin"
        "obsidian" -> "Obsidian"
        else -> "Logseq"
    }

    /** The request body, or null when there is nothing to file. */
    fun body(target: String, text: String): String? {
        val t = text.trim()
        if (t.isEmpty()) return null
        val where = normal(target)
        return """{"target":${JarvisApi.quote(where)},"text":${JarvisApi.quote(t)}}"""
    }

    /** Which note apps the desktop is set up for - or why that is not known. */
    sealed interface Targets {
        data class Known(val names: List<String>) : Targets
        data class Unknown(val why: String) : Targets
    }

    /** Reads the answer to `GET` [PATH] with no id. Only a real list counts. */
    fun targets(answer: JsonObject): Targets {
        val list = answer["targets"] as? JsonArray
            ?: return Targets.Unknown("the desktop's answer did not say which note apps are set up")
        val names = list.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }
        return Targets.Known(ALL.filter { it in names })
    }

    /** A failed request for the list. A 404 is a desktop from before the list existed. */
    fun targetsFailure(e: ApiError, generic: String): Targets.Unknown = Targets.Unknown(
        if (e == ApiError.NotFound) {
            "the desktop's Jarvis does not say which note apps are set up yet - copy the " +
                "new backend files in on the PC (run apply-patches.ps1)"
        } else {
            generic
        },
    )

    /** The one line shown instead of buttons - never all of them. */
    fun noTargetsLine(t: Targets): String = when (t) {
        is Targets.Unknown -> "Couldn't check which note apps are set up on your PC: ${t.why}"
        is Targets.Known -> "No note app is set up on your PC yet - see docs/INSTALL.md, Notes."
    }

    fun statusPath(id: String): String =
        PATH + "?id=" + java.net.URLEncoder.encode(id, "UTF-8")

    /** What to show for one answer. */
    data class Said(val text: String, val final: Boolean, val filed: Boolean)

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    fun jobId(job: JsonObject): String? = job.str("id")

    fun describe(job: JsonObject, target: String): Said {
        val place = name(target)
        val said = job.str("message")
        return when (job.str("state")) {
            "filed" -> Said(said ?: "Filed in $place.", final = true, filed = true)
            "waiting" -> Said("Waiting for your approval on the desktop to file this in $place.",
                final = false, filed = false)
            // `message` first; without one, the desktop's reason in `error` -
            // the same fallback the wiki reader uses. A refusal the desktop
            // explained only in `error` (a 429 "several notes are already
            // waiting", a note too long) used to show as a bare "Not filed".
            "not_filed", "failed" -> Said(
                said ?: job.str("error")?.let(::asSentence) ?: "Not filed in $place.",
                final = true,
                filed = false,
            )
            else -> Said("The desktop answered, but did not say whether the note was filed. Check $place.",
                final = true, filed = false)
        }
    }

    /** The desktop's `error` strings are lower-case fragments; shown as a sentence. */
    private fun asSentence(s: String): String =
        s.replaceFirstChar { it.uppercase() }.let { if (it.last() in ".!?") it else "$it." }

    /** Said when the desktop stopped answering while a card was still up. */
    const val GAVE_UP = "Still waiting for approval on the desktop. Nothing is filed until you answer the card."

    /** A failed request, in words. `null` means use the generic sentence. */
    fun failure(e: ApiError): String? = when (e) {
        ApiError.NotFound ->
            "This desktop cannot file notes yet - its backend needs the note-capture patch. Nothing was filed."
        else -> null
    }
}
