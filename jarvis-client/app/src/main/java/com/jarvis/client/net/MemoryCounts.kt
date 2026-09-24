package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull

/**
 * How much Jarvis remembers, and whether it is learning - the numbers the
 * desktop's Brain window shows on its Memory pane (`jarvis-desktop/src/brain.js`,
 * `renderMemory` and `renderLearning`), in the same words.
 *
 * - `GET /api/memory/status` - `MemoryStore.status()` plus the route's own
 *   `sleep_time` (docs/JARVIS-API.md: `{available, db, facts, current,
 *   retired, embedder, semantic, vector_search, unembedded, sleep_time}`).
 *   `facts` counts retired ones too, so it is not shown; `current` is what
 *   is in use. `db` is a file path on the PC and is not shown on the phone.
 * - `learning` rides on `GET /api/memory/facts` (`memory-pane.patch`); asked
 *   with `?limit=1` so the phone is not sent every fact to learn one switch.
 *
 * READ-ONLY on purpose. The owner decided that turning learning ON must ask
 * first, with an approval card. The PC's `POST /api/memory/learning` switches
 * it on at once, with no card (`extraction-wiring.patch`, `set_learning`),
 * so the phone has no switch until the PC asks. [learningLine] says so.
 */
object MemoryCounts {
    const val STATUS_PATH = "/api/memory/status"
    const val LEARNING_PATH = "/api/memory/facts?limit=1"

    private fun JsonObject.prim(key: String): JsonPrimitive? = this[key] as? JsonPrimitive

    /** A number as the desktop's `num()` shows it: only a real number, else nothing. */
    private fun JsonObject.num(key: String): String? {
        val p = prim(key)?.takeIf { !it.isString } ?: return null
        val d = p.doubleOrNull ?: return null
        return if (d == Math.floor(d) && !d.isInfinite()) d.toLong().toString() else d.toString()
    }

    /** The label/value rows, in the desktop's order. Empty when the store said nothing. */
    fun fields(status: JsonObject): List<Pair<String, String>> {
        if (status.prim("available")?.booleanOrNull == false) return emptyList()
        val out = mutableListOf<Pair<String, String>>()
        status.num("current")?.let { out += "Facts in use" to it }
        status.num("retired")?.let { out += "No longer used" to it }
        status.prim("embedder")?.takeIf { it.isString }?.contentOrNull?.takeIf { it.isNotBlank() }?.let { e ->
            out += "Embedding" to if (status.prim("semantic")?.booleanOrNull == false) {
                "$e (matches words only until the real embedding model has downloaded)"
            } else {
                e
            }
        }
        if (status.prim("vector_search")?.booleanOrNull == false) {
            out += "Search by meaning" to "off - facts are found by keyword"
        }
        status.num("unembedded")?.takeIf { (it.toDoubleOrNull() ?: 0.0) > 0 }?.let {
            out += "Waiting to be indexed" to it
        }
        (status["sleep_time"] as? JsonObject)?.let { st ->
            out += "Overnight tidying" to if (st.prim("enabled")?.booleanOrNull == true) {
                "switched on, but not built yet - nothing runs"
            } else {
                "off (not built yet)"
            }
        }
        return out
    }

    /** `learning` off `/api/memory/facts`: true, false, or null when it is not there. */
    fun learning(facts: JsonObject): Boolean? = facts.prim("learning")?.booleanOrNull

    /** The learning line, and why the switch is on the PC for now. */
    fun learningLine(on: Boolean?): String = when (on) {
        true -> "Learning is on: Jarvis reads your conversations for facts, and each one still " +
            "needs your yes."
        false -> "Learning is off: nothing new is proposed. A message that starts " +
            "\"Remember:\" still makes a card."
        null -> "Couldn't tell whether learning is on."
    } + " The switch is on your PC for now (Brain window, Memory tab): turning learning on " +
        "should ask you first, and your PC does not ask yet."
}
