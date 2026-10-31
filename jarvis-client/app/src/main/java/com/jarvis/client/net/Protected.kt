package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull

/**
 * "Protected from Jarvis" on the phone - the PC's owner-editable list of what
 * Jarvis may NOT touch (`.dsh-scratch/PROTECTED-ITEMS-2026-10-31/CONTRACT.md`;
 * the PC's half is `jarvis_protection.py`).
 *
 * The owner's request, verbatim: *"add a list of file folders, and programs
 * that i can manually add to (or ask jarvis to exclude in chat and get a card)
 * that blocks jarvis from having any access (read or write) or the ability to
 * make certain files or folders or programs read only"*. Each entry is a
 * folder, a file or a program, with ONE of two modes:
 *
 * - **blocked** - no access at all. For a folder or file: no read, no search
 *   hit, no snippet, no document read, no write, no delete, no rename. For a
 *   program: no opening, closing or controlling it, and no screen reading of
 *   its windows.
 * - **readonly** - reads and search results are allowed; every write, delete,
 *   rename or restore is refused. For a program, the owner's own words: "see
 *   it, never act".
 *
 * THE PHONE'S HALF IS DELIBERATELY SMALL, and this file is the whole of it:
 * it may LIST the entries and ASK for one to be REMOVED. The pickers are on
 * the PC (the phone has no view of the PC's files or programs - the same
 * reason the folders allow-list is PC-added), and adding is either the owner
 * in the PC's Settings or a chat request that raises a card on the PC. There
 * is no phone file browser and no phone add path in this object, and a test
 * pins that.
 *
 * Removal is LOOSENING, so it always asks: `POST /api/protection/remove`
 * answers `waiting` with a job id, the PC raises ONE existing approval card,
 * and this phone never decides it. The entry stays until the owner approves.
 *
 * Pure, no Android: `ProtectedContractTest`.
 */
object Protected {
    const val PATH = "/api/protection"
    const val REMOVE_PATH = "/api/protection/remove"

    /** Ask the list again every two seconds while a removal is waiting. */
    const val POLL_MS = 2_000L

    /** How long the plate keeps watching for the entry to disappear. */
    const val GIVE_UP_MS = 200_000L

    /** The two modes the PC sends in `modes`, by wire value. */
    const val MODE_BLOCKED = "blocked"
    const val MODE_READONLY = "readonly"

    /**
     * The contract's own phone line: the pickers are on the PC, and a chat
     * request from here raises one card. Shown under the list, always.
     */
    const val PICKERS =
        "Add folders, files and programs on your PC - or ask Jarvis in chat from here and it " +
            "will raise a card. Removing one asks for one card too."

    /** Said when the link is down: Remove waits, and nothing is changed. */
    const val STALE =
        "Not connected to the desktop, so removing waits until the link is back. " +
            "Nothing is changed."

    /** The PC's sentence when the card is answered: the entry is gone. */
    const val REMOVED = "Removed. The entry is no longer protected."

    /** Still waiting (or denied) when the phone stops watching. */
    const val STILL_THERE =
        "It is still in the list - if you denied the card, nothing changed. Nothing is " +
            "removed until you approve the card on your PC or on this phone's Home screen."

    /** One entry of the list, as the PC stores it. */
    data class Item(
        val id: String,
        val kind: String,
        val target: String,
        val mode: String,
        val added: String,
        val addedBy: String,
    )

    /** `GET /api/protection`'s answer. */
    data class View(
        val count: Int,
        val items: List<Item>,
        /** The modes the PC says exist - shown instead of a hard-coded pair when sent. */
        val modes: List<String>,
        /** The PC's own sentence about how changes are asked for, or empty. */
        val changeCard: String,
    )

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    /** The kind, in the list's words. Unknown kinds are shown as the PC sent them, never invented. */
    fun kindWord(kind: String): String = when (kind.trim().lowercase()) {
        "folder" -> "Folder"
        "file" -> "File"
        "program" -> "Program"
        else -> kind.trim().ifEmpty { "Entry" }
    }

    /**
     * The mode, in the owner's words. These are the contract's own words, so a
     * row on the phone says the same thing the PC's Settings says: "Blocked -
     * no access" / "Read-only". Unknown modes are shown as sent.
     */
    fun modeWord(mode: String): String = when (mode.trim().lowercase()) {
        MODE_BLOCKED -> "Blocked — no access"
        MODE_READONLY -> "Read-only"
        else -> mode.trim().ifEmpty { "Unknown" }
    }

    /** What the mode means for the kind, in one short line (the section's own explanation). */
    fun modeMeaning(kind: String, mode: String): String = when (mode.trim().lowercase()) {
        MODE_BLOCKED -> "Jarvis may not read it, write it or open it."
        MODE_READONLY -> if (kind.trim().lowercase() == "program") {
            "Jarvis may see it, never act on it."
        } else {
            "Jarvis may read it, but may never write, delete or rename it."
        }
        else -> ""
    }

    /** The list answer. An entry without an id or a target is skipped, never invented. */
    fun view(answer: JsonObject): View {
        val items = (answer["items"] as? JsonArray).orEmpty().mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val id = o.str("id") ?: return@mapNotNull null
            val target = o.str("target") ?: return@mapNotNull null
            Item(
                id = id,
                kind = o.str("kind").orEmpty(),
                target = target,
                mode = o.str("mode").orEmpty(),
                added = o.str("added").orEmpty(),
                addedBy = o.str("added_by").orEmpty(),
            )
        }
        val modes = (answer["modes"] as? JsonArray).orEmpty()
            .mapNotNull { (it as? JsonPrimitive)?.contentOrNull }
        return View(
            count = (answer["count"] as? JsonPrimitive)?.intOrNull ?: items.size,
            items = items,
            modes = modes,
            changeCard = answer.str("change_card").orEmpty(),
        )
    }

    /** The remove body: just the id. Null when no entry was named (nothing is sent). */
    fun removeBody(id: String): String? {
        val clean = id.trim()
        if (clean.isEmpty()) return null
        return """{"id":${JarvisApi.quote(clean)}}"""
    }

    fun jobId(answer: JsonObject): String? =
        (answer["id"] as? JsonPrimitive)?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    /**
     * What to show for the answer to a Remove tap. `removing` means the card is
     * up and the phone should watch the list; only the PC can say an entry is
     * gone, which is why [Removed] is said from the LIST after the card, never
     * from a status code here.
     */
    data class Said(val text: String, val removing: Boolean)

    fun describe(answer: JsonObject): Said {
        val said = answer["message"]?.let { (it as? JsonPrimitive)?.contentOrNull }
            ?.trim()?.takeIf { it.isNotEmpty() }
        val error = answer["error"]?.let { (it as? JsonPrimitive)?.contentOrNull }
            ?.trim()?.takeIf { it.isNotEmpty() }
        val state = (answer["state"] as? JsonPrimitive)?.contentOrNull?.trim()
        return when {
            state == "waiting" -> Said(
                said ?: "Waiting for your approval to remove it. It stays protected until you " +
                    "approve. ${Approvals.WHERE}",
                removing = true,
            )
            // A refusal answered before any card (unknown id, bad body) or a
            // state this build does not know: never taken as "removed".
            error != null -> Said(error.replaceFirstChar { it.uppercase() }, removing = false)
            else -> Said(
                "The desktop answered, but did not say whether the entry was removed. Check " +
                    "the list on your PC.",
                removing = false,
            )
        }
    }

    /** A failed request, in words. `null` means use the generic sentence. */
    fun failure(e: ApiError): String? = when (e) {
        ApiError.NotFound ->
            "This desktop has no protection list yet - its backend needs the protected-items " +
                "plugin (run apply-patches.ps1 on the PC). Nothing was changed."
        else -> null
    }
}
