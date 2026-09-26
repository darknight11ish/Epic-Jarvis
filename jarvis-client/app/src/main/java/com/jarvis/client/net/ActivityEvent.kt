package com.jarvis.client.net

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * The sentence an `activity` event carries - "Using calculator..." - for the
 * progress line under the face.
 *
 * The desktop's bus sends it as `{"key": "activity", "value": {"state": ...,
 * "detail": ...}}` (`backend/rebuilt/jarvis_events.py` `set_activity`, through
 * `BUS.note`). This app read `activity_detail` off the event, a field no
 * backend sends, so the line only ever showed what `/api/status` said on the
 * next refresh. Read from where the bus puts it now, with the two flatter
 * shapes still accepted. `ActivityEventTest` checks it against events captured
 * from the real bus (`chat-stream-cases.json`, `activity_events`).
 */
object ActivityEvent {

    /** The sentence, trimmed and capped at [max] characters, or null. */
    fun detail(data: JsonElement?, max: Int): String? {
        val obj = data as? JsonObject ?: return null
        val nested = (obj["value"] as? JsonObject)?.let { text(it["detail"]) }
        val said = nested ?: text(obj["detail"]) ?: text(obj["activity_detail"])
        return said?.trim()?.takeIf { it.isNotEmpty() }?.take(max)
    }

    private fun text(e: JsonElement?): String? =
        (e as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
}
