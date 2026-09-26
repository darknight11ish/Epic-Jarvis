package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.put

/**
 * "Folders Jarvis may look in" (the owner's decisions of 2026-09-26: asking
 * about PDFs and Word files, and bringing in a Notion export; docs/JARVIS-API.md
 * section 35; backend `jarvis_documents.py`, `documents.patch`).
 *
 * ONE list of folders on the PC that Jarvis may find, search and read files
 * in, empty by default. On the phone:
 *  - the list, in the PC's own words (`GET /api/folders`);
 *  - Remove on each folder - at once, never held on a stale link: it only
 *    lets Jarvis see less (`POST /api/folders/remove`);
 *  - NO Add and no Notion import: adding a folder is the PC's alone (the PC
 *    refuses it from any other device), so the phone shows the PC's line
 *    saying where (ARCHITECTURE section 8, "One-sided on purpose").
 * Asking Jarvis about the files works from the phone like any question: the
 * PC reads them, with the model on the PC.
 *
 * Pure Kotlin, no Android types, so `FoldersTest` runs it on a plain JVM
 * against `contract/folders-cases.json` - the PC's real answers.
 */
object Folders {
    const val PATH = "/api/folders"
    const val REMOVE_PATH = "/api/folders/remove"

    // The desktop's words (folders.js), and the PC's.
    const val TITLE = "Folders Jarvis may look in"
    const val MISSING = "Your PC's Jarvis cannot look in folders yet - run apply-patches.ps1 on the PC."
    const val REMOVE = "Remove"
    const val NOT_HERE = "Not found on this PC any more."

    data class Folder(val path: String, val name: String, val exists: Boolean)

    data class View(
        val title: String,
        val detail: String,
        val empty: String,
        val why: String,
        val folders: List<Folder>,
        val phoneAdd: String,
        val waiting: String,
        val waitingWords: String,
        val documentsSaid: String,
        val documentsReady: Boolean,
        val removeLabel: String,
    )

    /** `GET /api/folders`. Null when the answer is not the list. */
    fun parse(body: JsonObject): View? {
        if (body.flag("available") == false) return null
        val list = body["folders"] as? JsonArray ?: return null
        val folders = list.mapNotNull { e ->
            val o = e as? JsonObject ?: return@mapNotNull null
            val path = o.text("path") ?: return@mapNotNull null
            Folder(path = path, name = o.text("name") ?: path, exists = o.flag("exists") != false)
        }
        val docs = body["documents"] as? JsonObject
        val waiting = (body["waiting"] as? JsonObject)?.text("path") ?: ""
        return View(
            title = body.text("title") ?: TITLE,
            detail = body.text("detail") ?: "",
            empty = body.text("empty") ?: "",
            why = body.text("why") ?: "",
            folders = folders,
            phoneAdd = body.text("phone_add") ?: "",
            waiting = waiting,
            waitingWords = body.text("waiting_words") ?: "",
            documentsSaid = docs?.text("said") ?: "",
            documentsReady = docs?.flag("ready") == true,
            removeLabel = body.text("remove_label") ?: REMOVE,
        )
    }

    /** The lines under a folder's name, as the desktop shows them. */
    fun lines(f: Folder): List<String> = if (f.exists) listOf(f.path) else listOf(f.path, NOT_HERE)

    /** `POST /api/folders/remove`'s body for ONE folder. */
    fun removeBody(path: String): String = buildJsonObject { put("path", path) }.toString()

    /** What to say after a remove. */
    fun said(outcome: DesktopWrite.Outcome): String = when (outcome) {
        is DesktopWrite.Outcome.Done -> outcome.said ?: "Removed."
        is DesktopWrite.Outcome.Waiting -> outcome.said ?: "Removed."
        is DesktopWrite.Outcome.Refused -> "Not changed. " + outcome.why
    }

    /** A PC without the route: an older backend, or the module missing (503). */
    fun missing(error: ApiError): Boolean =
        error == ApiError.NotFound || error == ApiError.NotAvailable ||
            (error is ApiError.Server && (error.code == 501 || error.code == 503))

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.takeIf { it !is JsonNull && !it.isString }?.booleanOrNull
}
