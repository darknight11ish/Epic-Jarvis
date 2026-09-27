package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * "A cloud model could give this one a second look." — the offer gate
 * (`jarvis_router.choose()`, docs/JARVIS-API.md "`offer` in
 * `X-Jarvis-Route`", docs/ARCHITECTURE.md §11 "Cloud / API keys").
 *
 * The router never escalates a turn to the cloud on its own. When a
 * question is complex enough that a cloud lane could help, and nothing
 * privacy-sensitive kept it local, it still answers locally - but names
 * that lane in `offer` with `gate: "offer"`, so an app can ask the owner
 * "want a second opinion from the cloud?" for that ONE question. A turn
 * a privacy gate kept local outright carries no `offer` at all - `offer`
 * is `""` on every gate but this one - so reading `gate` first, not just
 * a non-blank `offer`, matters: nothing else on the header means "the
 * cloud could have answered but didn't".
 *
 * Read the same way as [Wellbeing.crisisFromHeader] and
 * [SecondCard.routeFromHeader] read the same `X-Jarvis-Route` header: a
 * small, single-purpose reader, not a shared parser.
 *
 * Saying yes for that one question is a new request field, `cloud_yes`
 * (`ChatHistory.requestBody`, [ChatSession.tryCloudForLast]) - the real
 * field name `backend/cloud-say-yes.patch` reads and threads into
 * `jarvis_router.choose()`'s own `owner_said_yes`, verified against the
 * owner's real `jarvis_hud.py` (2026-09-27; see that patch's own comment
 * for why it could not be checked the way every other patch in this
 * repository is). This file itself only reads the OTHER half of the
 * contract - the flag that says the offer exists in the first place -
 * and changes nothing about what is sent.
 */
object CloudOffer {

    /**
     * Exact wording (this project's rule: fixed UI strings match
     * word-for-word between the desktop and the phone app). No
     * exclamation marks, no film-quote phrases - the manner rules in
     * CLAUDE.md and docs/JARVIS-API.md.
     */
    const val LABEL = "A cloud model could give this one a second look."
    const val BUTTON = "Try the cloud model"
    const val MICRO = "Sends only this question - nothing else from this conversation."

    /**
     * The cloud lane named in `offer`, only when `gate` is exactly
     * `"offer"` too - null on every other gate (including one that also
     * happens to carry a non-blank `offer` some future backend adds for
     * a different reason), on a blank `offer`, on a header that is not
     * this JSON, and on no header at all.
     */
    fun laneFromHeader(header: String?): String? {
        if (header.isNullOrBlank()) return null
        val obj = runCatching { JarvisJson.parseToJsonElement(header.trim()) as? JsonObject }
            .getOrNull() ?: return null
        if (obj.str("gate") != "offer") return null
        return obj.str("offer")?.takeIf { it.isNotBlank() }?.take(80)
    }

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
}
