package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import java.net.URLEncoder

/**
 * "Person dossier" on the phone: one person's read-only dossier, opened by
 * tapping their name in "People and things" ([Entities]) - the phone's half of
 * LM-4 and #540 (docs/JARVIS-API.md section 143; backend
 * `jarvis_people_crm.build_person_dossier()`).
 *
 * **A read only.** Nothing is written, nothing is kept on the phone, no model
 * sees it, and no card is raised. The words are the PC's own records' words;
 * the phone never summarises or ranks them.
 *
 * ## The privacy rule, and where it is enforced
 *
 * The whole "People and things" screen is already replaced by
 * [com.jarvis.client.ui.screens.HiddenSection] while "Hide memory lists and
 * chat history" is on (see [Entities]), so a name cannot be tapped while the
 * lists are hidden - and this dossier lives inside that same section, so it is
 * hidden with it. The PC's route is owner-only (`jarvis_owner_check.from_this_pc`)
 * and refuses another device before it reads anything. A withheld answer (the
 * PC can withhold one itself) is drawn as ONE sentence: [Read.Shown] keeps the
 * `body` and drops every other field, so a name or a fact can never be drawn
 * beside it.
 *
 * The answer shape is the module's own dict, passed back unchanged by
 * `/api/people/dossier`: `{ok, withheld, why, name, private, active_facts,
 * retired_facts, recent_chat, recent_email, commitments, next_event, states,
 * why, read, counts, text}`. This object reads only `withheld`, `why`, `name`
 * and `text`; the rest belongs to the desktop's richer card.
 */
object PeopleDossier {

    const val PATH = "/api/people/dossier"
    const val TITLE = "Person dossier"

    /** The section's own line while the dossier is being read. */
    const val READING = "Reading…"

    /** The PC withheld the whole dossier (its own rule, said in one sentence). */
    const val HIDDEN = "Hidden while App lock or \"Hide memory lists and chat history\" is on."

    /** A PC whose backend predates the route (404/501). */
    const val MISSING = "Your PC's Jarvis does not have the person dossier yet. " +
        "Run apply-patches.ps1 on the PC."

    /** The PC answered, but not in a shape this app can read. */
    const val UNREADABLE = "Jarvis answered, but not in a way this app can read. " +
        "Update the backend by running apply-patches.ps1."

    /** The PC was allowed to answer and has no saved facts at all. */
    const val NOTHING = "Jarvis has no saved facts about them."

    /** One person's read. */
    sealed class Read {
        /**
         * A dossier the PC was willing to show. [withheld] is true for the
         * PC's one-sentence hidden answer: then [body] is that sentence and
         * every other field is empty.
         */
        data class Shown(
            val name: String,
            val body: String,
            val withheld: Boolean = false,
        ) : Read()

        /** This PC has no such route yet (a 404 or a 501). */
        object Missing : Read()

        /** A read that failed, said in one plain sentence. */
        data class Failed(val why: String) : Read()
    }

    /** `GET /api/people/dossier?name=` for one person, %-encoded. */
    fun path(name: String): String = PATH + "?name=" + encode(name)

    /** One query value, encoded (the same rule the desktop's Rust uses). */
    fun encode(value: String): String = URLEncoder.encode(value, "UTF-8").replace("+", "%20")

    /** A read that failed because this PC has no such route: a 404 or a 501. */
    fun missing(error: ApiError): Boolean = MemoryUsed.missing(error)

    /**
     * The PC's answer -> [Read]. Null when the shape is not a dossier at all
     * (the caller then says [UNREADABLE]); a withheld answer is a Shown with
     * only its sentence - never a name, a fact or a count.
     */
    fun parse(body: JsonObject): Read? {
        val withheld = (body["withheld"] as? JsonPrimitive)?.booleanOrNull == true
        if (withheld) {
            val said = body.text("why") ?: body.text("text") ?: HIDDEN
            return Read.Shown(name = "", body = said, withheld = true)
        }
        val ok = (body["ok"] as? JsonPrimitive)?.booleanOrNull
        if (ok == false) {
            val said = body.text("why") ?: body.text("text") ?: UNREADABLE
            // A refusal still echoes no person's name: the module writes "".
            return Read.Shown(name = body.text("name").orEmpty(), body = said)
        }
        if (ok != true) return null
        val name = body.text("name").orEmpty()
        val words = body.text("text")?.takeIf { it.isNotBlank() } ?: NOTHING
        return Read.Shown(name = name, body = words)
    }

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
}
