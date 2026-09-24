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
            "waiting" -> Said("Waiting for your approval to file this in $place. ${Approvals.WHERE}",
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
    const val GAVE_UP =
        "Still waiting for your approval. " + Approvals.WHERE + " Nothing is filed until you do."

    /** A failed request, in words. `null` means use the generic sentence. */
    fun failure(e: ApiError): String? = when (e) {
        ApiError.NotFound ->
            "This desktop cannot file notes yet - its backend needs the note-capture patch. Nothing was filed."
        else -> null
    }

    // ------------------------------------------------ chat-line prefixes ----

    /**
     * A chat line that starts with one of these files the rest as a note
     * instead of asking Jarvis anything - the desktop's quickbar prefixes,
     * word for word (`jarvis-desktop/src/main.js`, `NOTE_PREFIXES`). `#vault`
     * means Obsidian since 2026-09-24, on the desktop and in the backend
     * (`jarvis_note_capture._ALIASES`) alike.
     */
    val PREFIXES: Map<String, String> = linkedMapOf(
        "#log" to "logseq",
        "#logseq" to "logseq",
        "#journal" to "logseq",
        "#joplin" to "joplin",
        "#jop" to "joplin",
        "#vault" to "obsidian",
        "#obs" to "obsidian",
        "#obsidian" to "obsidian",
        "#daily" to "obsidian",
    )

    /** The desktop's `parseNotePrefix` pattern: `#` and letters, then a space or the end. */
    private val PREFIX = Regex("""^\s*(#[a-z]+)(\s+|$)""", RegexOption.IGNORE_CASE)

    /** A chat line that starts with a note prefix: which app, and the words after the prefix. */
    data class Prefixed(val target: String, val body: String)

    /** The prefix and the words after it, or null for an ordinary question. */
    fun prefixed(line: String): Prefixed? {
        val m = PREFIX.find(line) ?: return null
        val target = PREFIXES[m.groupValues[1].lowercase()] ?: return null
        return Prefixed(target, line.substring(m.range.last + 1))
    }

    /** The desktop's chip label for each app (`NOTE_PREFIXES`' `label`). */
    fun label(target: String): String = when (normal(target)) {
        "joplin" -> "Joplin Note"
        "obsidian" -> "Obsidian Daily Note"
        else -> "Logseq Journal"
    }

    /** What to set up on the PC, word for word from the desktop (`note-capture.js`, `TARGETS`). */
    fun setUp(target: String): String = when (normal(target)) {
        "joplin" -> "Put Joplin's Web Clipper token in JARVIS_JOPLIN_TOKEN (docs/INSTALL.md, Notes)."
        "obsidian" -> "Set [notes.obsidian] vault_directory in jarvis-framework.toml (docs/INSTALL.md, Notes)."
        else -> "Set [notes.logseq] graph_directory in jarvis-framework.toml (docs/INSTALL.md, Notes)."
    }

    /** Said when the PC said, for certain, that this app is not set up - the desktop's `notSetUp`. */
    fun notSetUp(target: String): String =
        "${name(target)} isn't set up on your PC, so nothing was filed. ${setUp(target)}"

    /** The desktop's words for a prefix with nothing after it. */
    const val NOTHING_TO_FILE = "Nothing to file - type the note after the prefix."

    /** What a prefixed chat line comes to. */
    sealed interface ChatNote {
        /** File [text] in [target] through [com.jarvis.client.JarvisRuntime.fileNote]. */
        data class File(val target: String, val text: String) : ChatNote

        /** Send nothing, and show [why]. */
        data class NotFiled(val why: String) : ChatNote
    }

    /**
     * The desktop's `fileFromBar` decision, in its order: an app the PC said
     * is NOT set up is refused here, with nothing sent; an empty note is
     * refused; anything else is sent. When the PC could not be asked
     * ([Targets.Unknown]) the note is sent anyway, and the PC's own answer -
     * it refuses an app that is not set up, saying why - is what is shown.
     */
    fun chatNote(p: Prefixed, targets: Targets): ChatNote {
        if (targets is Targets.Known && p.target !in targets.names) {
            return ChatNote.NotFiled(notSetUp(p.target))
        }
        val text = p.body.trim()
        if (text.isEmpty()) return ChatNote.NotFiled(NOTHING_TO_FILE)
        return ChatNote.File(p.target, text)
    }

    /**
     * The line under the chat box while a prefix is typed - the desktop's
     * chip beside its prompt - or null for an ordinary question. Says "not
     * set up" only when the PC said so; while the list is unknown it says
     * where the note will go, as the desktop does.
     */
    fun chip(draft: String, targets: Targets?): String? {
        val p = prefixed(draft) ?: return null
        if (targets is Targets.Known && p.target !in targets.names) {
            return "${label(p.target)} - not set up on your PC, so this would not be filed."
        }
        return "${label(p.target)}: this is filed as a note, not asked as a question."
    }

    /**
     * The prefix shown for each app the PC is set up for, with what it does
     * - the desktop's help list (`index.html`, the `data-note-target` rows),
     * which shows a prefix only for a note app that is set up. None when the
     * list is unknown or empty.
     */
    fun primer(targets: Targets?): List<Pair<String, String>> {
        val ready = (targets as? Targets.Known)?.names.orEmpty()
        return ready.map { t ->
            when (t) {
                "joplin" -> "#joplin" to "File what you type as a new Joplin note"
                "obsidian" -> "#obs" to "File what you type in today's Obsidian daily note"
                else -> "#log" to "File what you type in today's Logseq journal"
            }
        }
    }
}
