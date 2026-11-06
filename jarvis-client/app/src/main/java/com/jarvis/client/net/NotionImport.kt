package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.put
import java.util.Locale

/**
 * "Bring in a Notion export" - from the phone, into an Obsidian vault on the
 * PC (the owner's ask of 2026-11-05: "a download of my notion notes in
 * markdown towards the processed and put into OBsidian through jarvis
 * uploading it to the Android app"; DESIGN.md sections C1 and C1.1-C1.3).
 *
 * THE OWNER EXPORTS IT HIMSELF. No Notion login and no API token: in Notion,
 * Settings -> Export -> Markdown & CSV, then he picks the `.zip` that made.
 * The phone only carries the file; it never talks to Notion.
 *
 * THE TWO ROUTES ON THE PC, and the one rule they keep:
 *  - `GET /api/notion/vaults` - the vaults the PC already has, each validated
 *    by the PC as a real Obsidian vault. The phone picks one BY NAME and never
 *    types a path.
 *  - `POST /api/notion/phone-import` - `{upload, vault}` with no `digest` is
 *    the dry run: it plans and writes NOTHING. The same call with the plan's
 *    `digest` is the import: ONE `import_notion_export` card, then the write.
 *
 * The PC's own two path-taking routes (`/api/notion/preview` and
 * `/api/notion/import`) stay PC-only and unchanged: they take a path on the
 * PC, and a phone has none to name. The new routes take an upload id instead.
 *
 * ONE CARD AND UNDO, in the PC's own words (copied from `docs/JARVIS-API.md`
 * section 152, not invented here): the import writes the vault after one
 * person's yes; a denied, timed-out or refused card brings nothing in; one
 * reversible entry is recorded, so Undo takes the folder back off. The phone
 * says exactly that and adds no promise of its own.
 *
 * Pure Kotlin, no Android types: `NotionImportTest` holds the wire bodies, the
 * plan sentence, every refusal and the one-card words on a plain JVM.
 */
object NotionImport {

    const val VAULTS_PATH = "/api/notion/vaults"
    const val IMPORT_PATH = "/api/notion/phone-import"

    /** The PC's own title for this action (`jarvis_documents.NOTION_TITLE`). */
    const val TITLE = "Bring in a Notion export"

    /** What the phone says when it starts asking the PC which vaults it has. */
    const val CHECKING = "Asking your PC which vaults it has…"

    /** A PC without the phone routes: its own honest state. */
    const val NOT_HERE =
        "Bringing in a Notion export from your phone is not available on this PC yet."

    /** The PC has no Obsidian vault set up yet (the PC's own sentence). */
    const val NO_VAULT = "Choose your Obsidian vault on the PC first - Settings, Notes."

    /** How to make the export, copied from the PC's own `NOTION_DETAIL`. */
    const val HOW = "In Notion: Settings, Export all workspace content, as Markdown & CSV. " +
        "Then pick the .zip it made."

    /** The vault chooser's one line. */
    const val CHOOSE_VAULT = "Choose the vault to bring it into:"

    /** The plan's one button and its way out. */
    const val CONFIRM = "Bring it in"
    const val CANCEL = "Not now"

    // ---- The one-card + Undo words: docs/JARVIS-API.md section 152. --------

    /** "the import writes the vault after ONE person's yes". */
    const val ONE_YES = "The import writes the vault after one person's yes."

    /** "a denied, timed-out or refused card brings nothing in". */
    const val DENIED = "A denied, timed-out or refused card brings nothing in."

    /** "one reversible entry is recorded ... so Undo takes the folder back off". */
    const val UNDO = "One reversible entry is recorded, so Undo takes the folder back off."

    /** The whole promise, for the screen that asks. */
    fun promise(): String = "$ONE_YES $DENIED $UNDO"

    /** The sentence while the PC's card is being decided. */
    const val WAITING = "Waiting for your yes on the PC - approve the card there or in Approvals."

    /** Nothing was brought in, in the PC's words. */
    fun nothing(reason: String): String {
        val why = reason.trim()
        if (why.isEmpty()) return "Nothing was brought in."
        return "Nothing was brought in: " + DesktopWrite.asSentence(why)
    }

    // ------------------------------------------------------------- vaults ---

    /** One Obsidian vault the PC already has and has checked. [path] is the PC's, for display only. */
    data class Vault(val id: String, val name: String, val path: String)

    /** `GET /api/notion/vaults`. [ready] false means the PC has no vault yet. */
    data class Vaults(val ready: Boolean, val vaults: List<Vault>, val said: String)

    /** Null when the answer is not this route's shape at all. */
    fun parseVaults(body: JsonObject): Vaults? {
        if (body.flag("available") == false) return null
        val ok = body.flag("ok")
        val list = body["vaults"] as? JsonArray
        if (ok == false && list == null) {
            return Vaults(ready = false, vaults = emptyList(), said = reason(body) ?: NO_VAULT)
        }
        if (list == null && body.flag("ready") != true) return null
        val vaults = (list ?: JsonArray(emptyList())).mapNotNull { e ->
            val o = e as? JsonObject ?: return@mapNotNull null
            val id = o.text("id") ?: return@mapNotNull null
            val path = o.text("path").orEmpty()
            Vault(id = id, name = o.text("name") ?: vaultName(path), path = path)
        }
        return Vaults(
            ready = body.flag("ready") ?: vaults.isNotEmpty(),
            vaults = vaults,
            said = body.text("said").orEmpty(),
        )
    }

    /** The last segment of a PC path - the only part of a vault path the phone ever shows. */
    fun vaultName(path: String): String {
        val cut = maxOf(path.lastIndexOf('/'), path.lastIndexOf('\\'))
        return path.substring(cut + 1).trim().takeIf { it.isNotEmpty() } ?: path.trim()
    }

    // --------------------------------------------------------------- plan ---

    /** The dry run's plan, as much as the phone shows. [vault] is a path on the PC. */
    data class Plan(
        val name: String,
        val vault: String,
        val notes: Int,
        val attachments: Int,
        val databases: Int,
        val rows: Int,
        val htmlPages: Int,
        val renamed: Int,
        val digest: String,
        val said: String,
    )

    /** Null when the answer carries no plan. */
    fun parsePlan(body: JsonObject): Plan? {
        val plan = body["plan"] as? JsonObject ?: return null
        return Plan(
            name = plan.text("name").orEmpty(),
            vault = plan.text("vault").orEmpty(),
            notes = plan.whole("notes") ?: 0,
            attachments = plan.whole("attachments") ?: 0,
            databases = plan.whole("databases") ?: 0,
            rows = plan.whole("rows") ?: 0,
            htmlPages = plan.whole("html_pages") ?: 0,
            renamed = plan.whole("renamed") ?: 0,
            digest = plan.text("digest").orEmpty(),
            said = body.text("said") ?: plan.text("said").orEmpty(),
        )
    }

    /** The PC's answer to the dry run, read: the plan, or the PC's own reason. */
    sealed interface Preview {
        data class Ready(val plan: Plan) : Preview
        data class Refused(val why: String) : Preview

        /** The PC does not have these routes. */
        data object NotHere : Preview
    }

    /** `phone-import`'s dry-run answer. */
    fun readPreview(reply: Upload.Reply): Preview {
        val body = reply.body
        if (reply.code == 404 || reply.code == 501 || reply.code == 503) return Preview.NotHere
        if (body?.flag("ok") == false) return Preview.Refused(reason(body) ?: "Nothing was brought in.")
        val plan = body?.let(::parsePlan) ?: return Preview.Refused(reason(body) ?: "Your PC sent no plan.")
        return Preview.Ready(plan)
    }

    /**
     * The phone's own sentence for the plan, in the words DESIGN.md C1.3
     * gives: "Your export has 312 notes, 44 attachments and 6 databases.
     * Bring it into "My Vault"?"
     */
    fun planSentence(p: Plan): String {
        val counts = listOf(
            count(p.notes, "note"),
            count(p.attachments, "attachment"),
            count(p.databases, "database"),
        )
        val vault = vaultName(p.vault).ifBlank { p.vault }
        val into = if (vault.isBlank()) "" else " Bring it into \"$vault\"?"
        return "Your export has ${joinAnd(counts)}." + into
    }

    private fun count(n: Int, one: String): String =
        if (n == 1) "1 $one" else String.format(Locale.ROOT, "%,d", n) + " ${one}s"

    /** "a, b and c" - the same plain list the design's sentence uses. */
    private fun joinAnd(items: List<String>): String = when (items.size) {
        0 -> ""
        1 -> items[0]
        else -> items.dropLast(1).joinToString(", ") + " and " + items.last()
    }

    // ------------------------------------------------------------- bodies ---

    /**
     * `POST /api/notion/phone-import`'s body: the upload id and the vault id,
     * plus the plan's `digest` only on the call that imports. No path, no
     * zip name, no source: the PC owns those.
     */
    fun body(upload: String, vault: String, digest: String? = null): String = buildJsonObject {
        put("upload", upload)
        put("vault", vault)
        digest?.takeIf { it.isNotBlank() }?.let { put("digest", it) }
    }.toString()

    /** The import's answer, read: the PC's own sentence, or one built from its numbers. */
    fun imported(body: JsonObject?, plan: Plan?): String {
        if (body == null) return "Your PC did not say what happened."
        val copy = body.text("said")
        if (!copy.isNullOrBlank()) return copy
        val notes = body.whole("notes") ?: plan?.notes ?: 0
        val folder = vaultName(body.text("folder").orEmpty()).ifBlank { plan?.name.orEmpty() }
        val landed = if (folder.isBlank()) "" else " into \"$folder\""
        return "Brought ${count(notes, "note")}$landed. $UNDO"
    }

    /** The import's answer, read as a refusal when it says `ok: false`. */
    fun refusal(body: JsonObject?): String? {
        if (body == null) return null
        if (body.flag("ok") != false) return null
        return reason(body) ?: "Nothing was brought in."
    }

    /** The PC's own reason from any of the fields its routes use for one. */
    fun reason(body: JsonObject?): String? =
        (body?.text("reason") ?: body?.text("error") ?: body?.text("said") ?: body?.text("message"))

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()
            ?.takeIf { it.isNotEmpty() }

    private fun JsonObject.flag(key: String): Boolean? =
        (this[key] as? JsonPrimitive)?.booleanOrNull

    private fun JsonObject.whole(key: String): Int? =
        (this[key] as? JsonPrimitive)?.intOrNull
}
