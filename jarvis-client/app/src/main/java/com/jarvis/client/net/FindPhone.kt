package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlin.math.abs

/**
 * "Ring my phone" (backend `jarvis_find_phone.py`, the owner's choice of
 * 2026-09-28; docs/JARVIS-API.md section 74): said or typed to Jarvis on the
 * PC, answered there without the AI model, and heard here as ONE
 * `ring_phone` event - `{"id", "state": "ring"|"stop", "at", "until",
 * "seconds"}`, no words at all. This phone then rings on the alarm channel
 * ([com.jarvis.client.service.ScheduleNotifier.ALARM_CHANNEL_ID] - an alarm
 * sound, so it rings even on silent), with a Stop button, and stops by
 * itself after [MAX_SECONDS] at the most. No card: it only rings the
 * owner's own phone, from the owner's own words.
 *
 * NEVER FOR A STALE OR REPLAYED EVENT. A reconnect replays recent events,
 * and a phone that was out of reach hears them late. It rings only when:
 *  - the event is fresh - this phone's clock within [FRESH_SECONDS] of the
 *    PC's `at` (far stricter than the 10-minute rule for alarms: a ring that
 *    comes late is only a surprise, never useful), and
 *  - this `id` has not rung here before (the runtime keeps the ids, like
 *    the ids of alarms already shown).
 * A late one is dropped silently: there is nothing to tell the owner.
 *
 * The desktop has no part in this: it is the PC being asked, not rung
 * (docs/ARCHITECTURE.md section 8).
 *
 * Pure Kotlin, no Android types, so `FindPhoneTest` runs it on a plain JVM.
 * The idea is KDE Connect's "Find my phone" (GPL) - the idea only, no code.
 */
object FindPhone {
    const val EVENT = "ring_phone"

    /** How far this phone's clock may be from the PC's `at` for it to ring. */
    const val FRESH_SECONDS = 120.0

    /** The longest it rings, whatever the event says. */
    const val MAX_SECONDS = 120

    /** The shortest - an event that says less rings this long. */
    const val MIN_SECONDS = 10

    const val TITLE = "Jarvis is ringing this phone"
    const val TEXT = "You asked Jarvis to find your phone. Press Stop to stop the ringing."
    const val LOCK_SCREEN = "Jarvis: you asked to find this phone."

    data class Ring(val id: String, val stop: Boolean, val at: Double, val seconds: Int)

    private val ID = Regex("r[0-9a-f]{12}")

    /** The event's data, read - or null when it is not a ring the PC makes. */
    fun parse(data: JsonObject?): Ring? {
        if (data == null) return null
        val id = data.text("id") ?: return null
        if (!ID.matches(id)) return null
        val stop = when (data.text("state")) {
            "ring" -> false
            "stop" -> true
            else -> return null
        }
        val at = data.num("at") ?: return null
        val seconds = (data.num("seconds") ?: 60.0).toInt().coerceIn(MIN_SECONDS, MAX_SECONDS)
        return Ring(id, stop, at, seconds)
    }

    /** Fresh enough to ring now, by this phone's clock (epoch seconds). */
    fun fresh(r: Ring, nowSeconds: Double): Boolean = abs(nowSeconds - r.at) <= FRESH_SECONDS

    /** Ring for this event now? Never a stop, never a stale one. */
    fun shouldRing(r: Ring, nowSeconds: Double): Boolean = !r.stop && fresh(r, nowSeconds)

    /** How long the notification rings before it goes by itself, in ms. */
    fun ringMillis(r: Ring): Long = r.seconds.coerceIn(MIN_SECONDS, MAX_SECONDS) * 1000L

    /** The notification's tag: one per ring. */
    fun tag(id: String): String = "find-phone:$id"

    private fun JsonObject.text(key: String): String? =
        (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.num(key: String): Double? =
        (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull
}
