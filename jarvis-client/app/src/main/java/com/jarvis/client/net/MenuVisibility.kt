package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * "Hide the finance menu" by voice or chat (docs/JARVIS-API.md section 109.2): the change the
 * PC named in the answer's `X-Jarvis-Route` as `menu_visibility: {"action", "target"}`. The PC
 * cannot know which app asked, so it names the change and every app that hears it applies it
 * to its OWN list (`data/MenuPrefs.kt`). Nothing here reaches out: no request, no card, no
 * gate - hiding only tidies.
 *
 * [target] is a menu id, `group.<id>`, or `all` (for `reset`). An id this phone does not have,
 * a group it has no member of, and a never-hideable id are ignored by [MenuLogic] - so a
 * mistaken or hostile header can do no more than tidy.
 */
data class MenuRoute(val action: String, val target: String) {

    companion object {
        /** The header's change, or null when it named none or named a malformed one. */
        fun fromRoute(header: String?): MenuRoute? {
            if (header.isNullOrBlank()) return null
            val root = runCatching { JarvisJson.parseToJsonElement(header.trim()) as? JsonObject }
                .getOrNull() ?: return null
            val change = root["menu_visibility"] as? JsonObject ?: return null
            val action = change.text("action") ?: return null
            val target = change.text("target") ?: return null
            if (action !in MenuLogic.ACTIONS || target.isEmpty()) return null
            return MenuRoute(action, target)
        }

        private fun JsonObject.text(key: String): String? =
            (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content
    }
}
