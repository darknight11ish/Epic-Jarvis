package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * The crisis help line (the owner's decision, 2026-09-27; CLAUDE.md,
 * "Decided 2026-09-27, the owner's answers": "Crisis help line: United
 * States - 988 (Suicide & Crisis Lifeline) and 911." and "Crisis messages
 * are never learned from and never counted."). `backend/jarvis_wellbeing.py`,
 * docs/JARVIS-API.md section 38.
 *
 * The word check, the fixed help message, the note to the model, and never
 * learning from a crisis turn all run on the PC, inside
 * `jarvis_agent.run_local_turn` - already wired into `/api/chat`, so they
 * take effect with no change here at all. This file reads ONE cosmetic
 * flag off the SAME `X-Jarvis-Route` header [SecondCard.routeFromHeader]
 * and [Schedule.quickFromRouteHeader] already read, `wellbeing: "crisis"`
 * - present only on a turn that matched, absent on every other one - so
 * Home can draw the answer as a calm, plain panel instead of an ordinary
 * bubble. **Not confirmed sent by every backend**: `backend/wellbeing.patch`
 * was written with no real `jarvis_hud.py` to check it against (see its
 * own section in backend/README.md). Without the flag, the words still
 * arrive as an ordinary answer - this only changes how they are drawn.
 */
object Wellbeing {
    /** True only when this turn's `X-Jarvis-Route` carries `"wellbeing": "crisis"`. */
    fun crisisFromHeader(header: String?): Boolean {
        if (header.isNullOrBlank()) return false
        val obj = runCatching { JarvisJson.parseToJsonElement(header.trim()) as? JsonObject }
            .getOrNull() ?: return false
        return obj.str("wellbeing") == "crisis"
    }

    private fun JsonObject.str(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
}
