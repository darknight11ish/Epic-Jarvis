package com.jarvis.client.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * "Playing on your PC" on Home (the owner's choice of 2026-09-28, the
 * research audit's idea 8): play, pause, next and previous for whatever is
 * playing on the PC, through the routes the PC already answers
 * (backend `jarvis_media.py`, media.patch; docs/JARVIS-API.md section 74):
 * `GET /api/media` ("what's playing", in the PC's own sentence) and
 * `POST /api/media/control {"action"}`.
 *
 * No card (the owner's decision of 2026-09-27: music and video control on
 * the PC needs none - a button pressed by the owner is their own words).
 * Every button is greyed while the link is stale (rule 4:
 * [com.jarvis.client.JarvisRuntime.pcMediaControl] refuses on a stale link
 * too). What is playing is the playing app's words, not the owner's - it is
 * only shown, never saved or sent anywhere.
 *
 * Desktop: none, on purpose - the PC already has its own media keys and
 * Windows' media controls right there (docs/ARCHITECTURE.md section 8).
 *
 * Pure Kotlin, no Android types, so `PcMediaTest` runs it on a plain JVM.
 */
object PcMedia {
    const val PATH = "/api/media"
    const val CONTROL_PATH = "/api/media/control"

    const val TITLE = "Playing on your PC"
    const val HINT =
        "Play, pause or skip whatever is playing on your PC. No approval card - it only " +
            "controls music and video there."
    const val READING = "Asking your PC…"

    /** The PC without jarvis_media.py - jarvis_quick.MEDIA_MISSING, word for word. */
    const val MISSING =
        "Your PC's Jarvis cannot control music or video yet - run apply-patches.ps1 on the PC."

    const val PREVIOUS = "previous"
    const val PLAY = "play"
    const val PAUSE = "pause"
    const val NEXT = "next"

    /** The buttons, in order. Never more than one action per tap. */
    val ACTIONS = listOf(PREVIOUS, PLAY, PAUSE, NEXT)

    fun label(action: String): String = when (action) {
        PREVIOUS -> "Previous"
        PLAY -> "Play"
        PAUSE -> "Pause"
        NEXT -> "Next"
        else -> action
    }

    /** The body of ONE button's request, or null for anything else. */
    fun body(action: String): String? =
        if (action in ACTIONS) "{\"action\":\"$action\"}" else null

    /** The PC's own sentence ("Paused.", "Nothing seems to be playing right now."). */
    fun said(o: JsonObject?): String? =
        (o?.get("said") as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()
            ?.takeIf { it.isNotEmpty() }

    /** A PC without the routes. */
    fun missing(e: ApiError): Boolean =
        e == ApiError.NotFound || (e is ApiError.Server && e.code == 404)
}
