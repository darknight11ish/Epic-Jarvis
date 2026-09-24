package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull

/**
 * The wiki builder, from the phone - the desktop's `GET /api/wiki` and
 * `POST /api/wiki/ingest` (`backend/wiki.patch`, `backend/jarvis_wiki.py`).
 *
 * Documents the owner puts in their Obsidian vault's `Jarvis Wiki/Sources`
 * folder are turned into linked pages by the model on the desktop's second
 * graphics card. The phone lists those documents with their state and offers
 * "Add to wiki" for a new or changed one. It does not browse files or read
 * pages: the vault already reaches the phone through Syncthing.
 *
 * "Add to wiki" only asks. The desktop's model reads the document, then ONE
 * approval card is raised; nothing is written until it is answered. The job
 * the desktop answers with has a `state`:
 *
 * - `reading` - the model is reading it; no card yet.
 * - `waiting` - the card is up (Home, and the desktop).
 * - `writing` - approved; writing the pages.
 * - `done` - written. Only then does the phone say it was added.
 * - `refused` / `failed` - with the desktop's own reason in `message`.
 *
 * A refusal the desktop explained before any job started (already in the
 * wiki, too big, the second card is off) comes back as `state: "refused"`
 * with the reason in `error`, and is shown the same way.
 */
object Wiki {
    const val PATH = "/api/wiki"
    const val INGEST_PATH = "/api/wiki/ingest"
    const val POLL_MS = 3_000L

    /** Reading a long document on the second card, then the card's own wait. */
    const val GIVE_UP_MS = 30L * 60L * 1000L

    data class Source(val name: String, val state: String, val why: String) {
        /** New or changed: the only two states "Add to wiki" is offered for. */
        val addable: Boolean get() = state == "new" || state == "changed"
    }

    data class View(
        val available: Boolean,
        val why: String,
        val folderOk: Boolean,
        val folderWhy: String,
        val pages: Int,
        val recent: List<String>,
        val sources: List<Source>,
        /** The document the desktop is working on now, from any device, or null. */
        val runningSource: String?,
    ) {
        fun canAdd(s: Source): Boolean = available && folderOk && runningSource == null && s.addable
    }

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    /** Reads `GET` [PATH]'s answer. Unknown states are shown, never offered for adding. */
    fun read(answer: JsonObject): View {
        val sources = (answer["sources"] as? JsonArray).orEmpty().mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val name = o.str("name") ?: return@mapNotNull null
            Source(name, o.str("state").orEmpty(), o.str("why").orEmpty())
        }
        val recent = (answer["recent"] as? JsonArray).orEmpty()
            .mapNotNull { (it as? JsonPrimitive)?.contentOrNull }
        return View(
            available = (answer["available"] as? JsonPrimitive)?.booleanOrNull == true,
            why = answer.str("why").orEmpty(),
            folderOk = (answer["vault_folder_ok"] as? JsonPrimitive)?.booleanOrNull == true,
            folderWhy = answer.str("folder_why").orEmpty(),
            pages = (answer["pages"] as? JsonPrimitive)?.intOrNull ?: 0,
            recent = recent,
            sources = sources,
            runningSource = (answer["running"] as? JsonObject)?.str("source"),
        )
    }

    /** A source state, in words. */
    fun label(state: String): String = when (state) {
        "new" -> "New"
        "changed" -> "Changed"
        "in_wiki" -> "In the wiki"
        "too_big" -> "Too big"
        "unreadable" -> "Can't read"
        else -> state
    }

    /** One log line without its Markdown heading marks. */
    fun logLine(line: String): String = line.removePrefix("## ").trim()

    /** The request body, or null when no document is named. */
    fun body(source: String): String? {
        val s = source.trim()
        if (s.isEmpty()) return null
        return """{"source":${JarvisApi.quote(s)}}"""
    }

    fun statusPath(id: String): String =
        INGEST_PATH + "?id=" + java.net.URLEncoder.encode(id, "UTF-8")

    fun jobId(job: JsonObject): String? = job.str("id")

    /** What to show for one answer about a job. */
    data class Said(val text: String, val final: Boolean, val done: Boolean)

    fun describe(job: JsonObject): Said {
        val said = job.str("message")
        return when (job.str("state")) {
            "reading" -> Said(said ?: "The model on the second card is reading it. No card yet.",
                final = false, done = false)
            "waiting" -> Said(said ?: "Waiting for your approval. Nothing is written until you answer.",
                final = false, done = false)
            "writing" -> Said(said ?: "Writing the pages.", final = false, done = false)
            "done" -> Said(said ?: "Added to the wiki.", final = true, done = true)
            "refused", "failed" -> Said(said ?: job.str("error") ?: "Not added. Nothing was written.",
                final = true, done = false)
            else -> Said("The desktop answered, but did not say how it went. Look in the wiki folder.",
                final = true, done = false)
        }
    }

    /** Said when the phone stopped following a job that was still going. */
    const val GAVE_UP = "Still going on the desktop. Nothing is written until you approve its card."

    /** A failed request, in words. `null` means use the generic sentence. */
    fun failure(e: ApiError): String? = when (e) {
        ApiError.NotFound ->
            "This desktop has no wiki builder yet - its backend needs wiki.patch " +
                "(run apply-patches.ps1 on the PC). Nothing was added."
        else -> null
    }
}
