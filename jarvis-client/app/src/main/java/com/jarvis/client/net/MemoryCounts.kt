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
 * The learning switch (`POST /api/memory/learning`). The owner decided that
 * turning learning ON must ask first: since `learning-asks.patch` the PC
 * raises an approval card under the action [LEARNING_ACTION] and answers 202
 * `{"waiting": true, "enabled": false}` - so ON is "waiting", never "on",
 * until that card is approved. OFF is immediate on the PC and is never held
 * here. The runtime holds ON on a stale link.
 */
object MemoryCounts {
    const val STATUS_PATH = "/api/memory/status"
    const val LEARNING_PATH = "/api/memory/facts?limit=1"
    const val LEARNING_WRITE_PATH = "/api/memory/learning"

    /** The gate action the PC raises the ON card under (jarvis_learning_switch.py). */
    const val LEARNING_ACTION = "learning_enable"

    fun learningBody(on: Boolean): String = "{\"enabled\":$on}"

    /** Is the ON card still in the approval queue? */
    fun learningCardWaiting(actions: List<String?>): Boolean = actions.any { it == LEARNING_ACTION }

    /** What to say after the switch was pressed, from the PC's answer. */
    fun learningSaid(on: Boolean, outcome: DesktopWrite.Outcome): String = when (outcome) {
        is DesktopWrite.Outcome.Waiting -> waitingLine()
        is DesktopWrite.Outcome.Refused -> "Not changed. ${outcome.why}"
        is DesktopWrite.Outcome.Done -> outcome.said?.let { DesktopWrite.asSentence(it) }
            ?: if (on) "Background learning is on." else "Background learning is off. Nothing new will be proposed."
    }

    /** While the ON card waits. "Background learning", as everywhere this switch is named. */
    fun waitingLine(): String = "Waiting for your approval to turn background learning on. ${Approvals.WHERE}"

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

    /**
     * The learning line. Since automatic learning (docs/JARVIS-API.md section
     * 19) not every fact needs a yes any more, so this no longer says so: the
     * "Learn automatically" switch under it says which way that is. This
     * switch is "background learning" everywhere it is named (fit audit,
     * 2026-09-24), so it is never mistaken for "Learn automatically".
     */
    fun learningLine(on: Boolean?): String = when (on) {
        true -> "Background learning is on: Jarvis reads your conversations for facts. " +
            "\"Learn automatically\", below, says whether it saves them without asking."
        false -> "Background learning is off: nothing new is proposed. A message that starts " +
            "\"Remember:\" still makes a card. Turning it on asks you first, with an approval card."
        null -> "Couldn't tell whether background learning is on."
    }
}
