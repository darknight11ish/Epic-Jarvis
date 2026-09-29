package com.jarvis.client.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * The phone's own last successful `GET /api/models` read, held only so
 * Brain -> Model has something to show, clearly marked as old, when a live
 * read fails - `docs/OFFLINE-MODELS-DESIGN-2026-09-27.md`.
 *
 * This is never a live disk read (the phone has no access to the PC's disk
 * at all) and never a browsable catalogue (CLAUDE.md: "do not build the
 * model catalogue... on the phone") - it is a plain read-only replay of
 * data the phone already had permission to see, from the last time it was
 * actually talking to the PC.
 *
 * Deliberately narrower than [ModelsInfo]: [ModelsInfo.offload] and
 * [ModelsInfo.speed] are facts about what Ollama's PROCESS is doing right
 * now, not facts about a file it already has (the design doc's section 5
 * table), so this class has no field for either one - there is nothing
 * here for a later reader to show stale by mistake, because it was never
 * carried into the cache in the first place. [currentRef] and [previous]
 * ARE cached, but only ever as "the model in use as of [asOfMs]", never as
 * "now" - see how `ModelsPlate` on `BrainScreen.kt` words it.
 */
data class CachedModels(
    val currentRef: String?,
    val previous: String?,
    val entries: List<ModelEntry>,
    /** Wall-clock millis when the read that produced this succeeded. */
    val asOfMs: Long,
) {
    /** The shape written to disk by `ModelsCacheStore`. Small and single-purpose on purpose. */
    fun toJson(): JsonObject = buildJsonObject {
        put("as_of_ms", asOfMs)
        currentRef?.let { put("current", it) }
        previous?.let { put("previous", it) }
        put(
            "installed",
            buildJsonArray {
                entries.forEach { e ->
                    add(
                        buildJsonObject {
                            put("ref", e.ref)
                            e.sizeBytes?.let { put("size", it) }
                            e.family?.let { put("family", it) }
                        },
                    )
                }
            },
        )
    }

    companion object {
        /**
         * The offline-safe subset of a live read, stamped with when that read
         * succeeded. Called only from the success path of a live
         * `GET /api/models` ([com.jarvis.client.JarvisRuntime.refreshModels]) -
         * never fetched specially, per the design doc's section 4.
         */
        fun from(models: ModelsInfo, asOfMs: Long): CachedModels = CachedModels(
            currentRef = models.currentRef,
            previous = models.previous,
            entries = models.entries,
            asOfMs = asOfMs,
        )

        /**
         * Anything unreadable - a corrupt preference, a shape from a future
         * version - is null, never a guess. [ModelsCacheStore.load] treats
         * null the same as "nothing was ever cached".
         */
        fun fromJson(json: JsonObject): CachedModels? {
            val asOf = json.long("as_of_ms") ?: return null
            val installed = (json["installed"] as? JsonArray).orEmpty()
            val entries = installed.mapNotNull { el ->
                val o = el as? JsonObject ?: return@mapNotNull null
                val ref = o.str("ref") ?: return@mapNotNull null
                ModelEntry(ref = ref, sizeBytes = o.long("size"), family = o.str("family"))
            }
            return CachedModels(
                currentRef = json.str("current"),
                previous = json.str("previous"),
                entries = entries,
                asOfMs = asOf,
            )
        }

        private fun JsonObject.str(key: String): String? =
            (this[key] as? JsonPrimitive)?.content?.takeIf { it.isNotBlank() }

        private fun JsonObject.long(key: String): Long? =
            (this[key] as? JsonPrimitive)?.content?.toLongOrNull()
    }
}

/**
 * What Brain -> Model has to show, exactly one of three shapes - never a
 * live disk read and never a browsable catalogue, for the reasons
 * [CachedModels]'s own doc comment gives.
 */
sealed interface ModelsView {
    /** The most recent live read succeeded. Every field on [info] is current. */
    data class Live(val info: ModelsInfo) : ModelsView

    /**
     * The most recent live read failed, or none has been tried yet this
     * run, and there is an earlier successful read to replay. [cached]
     * carries nothing about what is loaded in Ollama's memory right now,
     * so there is nothing for the screen to show stale by mistake - see
     * [CachedModels].
     */
    data class Stale(val cached: CachedModels) : ModelsView

    /** No live read has ever succeeded on this phone. Nothing to replay. */
    data object NeverConnected : ModelsView
}

/**
 * Decides what to show, given the most recent attempt and whatever is on
 * disk.
 *
 * [live] must be non-null ONLY when the MOST RECENT read succeeded - never
 * an older value kept around after a failure. [com.jarvis.client.JarvisRuntime.models]
 * follows exactly this rule as of the 2026-09-28 cache addition: it clears
 * to null on a failed read rather than leaving the previous answer sitting
 * there unlabelled, specifically so this function's two branches stay
 * mutually exclusive by construction - a failed read can never draw as
 * though it had just worked.
 */
fun modelsView(live: ModelsInfo?, cached: CachedModels?): ModelsView = when {
    live != null -> ModelsView.Live(live)
    cached != null -> ModelsView.Stale(cached)
    else -> ModelsView.NeverConnected
}
