package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.put

/**
 * Installed skills on Mind, and removing one - the desktop's Brain window,
 * Faculties, Skills (`jarvis-desktop/src/brain.js`, the skills list;
 * `src-tauri/src/brain.rs`, `brain_remove_skill`).
 *
 * `GET /api/skills` is read the way the desktop reads it: a `skills` list
 * (or a bare list, which the phone's `probe` hands over as `items`), each
 * with a name, a scan verdict, a description, a path, and Jarvis's own notes
 * about the skill (`skill-notes.patch`) - shown, because they go into the
 * model's context every time the skill is used.
 *
 * `POST /api/skills/decide` with `{"name": ..., "remove": true}` removes one.
 * Removal only: there is deliberately no route that installs a skill, because
 * installing runs the scanner and the approval gate on the PC. The desktop
 * asks "are you sure" first and raises no card of its own; whether the PC
 * raises one is the PC's business (its handler is in the owner's
 * `jarvis_hud.py`, not in this repository), and the phone shows it if it does
 * ([DesktopWrite]).
 */
object Skills {
    const val PATH = "/api/skills"
    const val DECIDE_PATH = "/api/skills/decide"

    data class Skill(
        /** Shown. "(unnamed)" when the PC sent neither a name nor an id. */
        val title: String,
        /** What to post to remove it - null when there is no name to post. */
        val name: String?,
        val verdict: String,
        /** The verdict reads as clean ("clean", "ok", "pass"). */
        val clean: Boolean,
        /** The lines under it: description, path, then each of Jarvis's notes. */
        val lines: List<String>,
    )

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    /**
     * The skills, or null when the answer holds no list at all - the screen
     * then shows the answer's own keys, as it did before this existed.
     */
    fun read(answer: JsonObject): List<Skill>? {
        val list = (answer["skills"] as? JsonArray) ?: (answer["items"] as? JsonArray) ?: return null
        return list.mapNotNull { el ->
            val o = el as? JsonObject ?: return@mapNotNull null
            val name = o.text("name") ?: o.text("id")
            val verdict = o.text("verdict") ?: o.text("scan")
                ?: if ((o["ok"] as? JsonPrimitive)?.booleanOrNull == false) "flagged" else "clean"
            val notes = (o["notes"] as? JsonArray).orEmpty().mapNotNull { n ->
                when (n) {
                    is JsonPrimitive -> n.takeIf { it.isString }?.contentOrNull
                    is JsonObject -> n.text("note") ?: n.text("text")
                    else -> null
                }?.trim()?.takeIf { it.isNotEmpty() }
            }
            Skill(
                title = name ?: "(unnamed)",
                name = name,
                verdict = verdict,
                clean = Regex("clean|ok|pass", RegexOption.IGNORE_CASE).containsMatchIn(verdict),
                lines = listOfNotNull(o.text("description") ?: o.text("summary"), o.text("path")) +
                    notes.map { "Jarvis's note: “$it”" },
            )
        }
    }

    fun removeBody(name: String): String = buildJsonObject {
        put("name", name)
        put("remove", true)
    }.toString()

    /** Shown before Remove - the desktop's warning, in plainer words. */
    fun removeWarning(name: String): String =
        "Remove the skill \"$name\"? This cannot be undone from the phone. No app can install " +
            "a skill - installing runs Jarvis's safety scanner and approval rules on the PC - so " +
            "putting it back means putting its file back on the PC."

    /** What to say after asking the PC to remove [name]. */
    fun removeSaid(name: String, o: DesktopWrite.Outcome): String = when (o) {
        is DesktopWrite.Outcome.Done -> o.said ?: "Removed $name."
        is DesktopWrite.Outcome.Waiting ->
            "Waiting for your approval to remove $name. ${Approvals.WHERE} Nothing is removed until you do."
        is DesktopWrite.Outcome.Refused -> "Not removed. ${o.why}"
    }

    /** A failed request, in words. Null means use the generic sentence. */
    fun failure(e: ApiError): String? = when (e) {
        ApiError.NotFound, ApiError.NotAvailable ->
            "Your PC's Jarvis cannot remove skills (no /api/skills/decide there)."
        else -> null
    }
}
