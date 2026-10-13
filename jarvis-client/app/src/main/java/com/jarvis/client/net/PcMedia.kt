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
    /**
     * The line that used to stand in for the read before it landed.
     *
     * No longer drawn by Home: the plate is hidden entirely unless the PC says
     * a track is really playing (the owner, 2026-10-13), so there is no such
     * thing as "the plate is up but there is nothing to say yet". Kept because
     * it is the plate's own description of itself and any future surface that
     * shows these controls while idle needs the same sentence.
     */
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

    /**
     * What the PC says a track is doing. `GET /api/media` answers only
     * `{"ok", "said"}` - `jarvis_media.handle_get` drops everything else,
     * including the playback flag - so the PC's own sentence is the only
     * signal the phone is given, and these are the two shapes that sentence
     * has when something is loaded (jarvis_media.now_playing):
     * `"Playing: “title” by artist."` and `"Paused: “title”."`.
     */
    enum class State { PLAYING, PAUSED, NONE }

    /** What the PC writes in front of a track that is playing. */
    const val PLAYING_PREFIX = "Playing:"

    /** What the PC writes in front of a track that is loaded but paused. */
    const val PAUSED_PREFIX = "Paused:"

    /**
     * Which state the PC's sentence describes.
     *
     * The plate is drawn while a track is PLAYING OR PAUSED (the owner's
     * answer of 2026-10-13, choosing "Also show it while paused" over hiding
     * on pause). [State.NONE] covers everything else and the plate hides for
     * all of it: the empty answer ("Nothing seems to be playing right now."),
     * a failed or unreachable read (null), an empty sentence, and any wording
     * this phone does not recognise. Hiding is the direction to be wrong in -
     * a control that may not mean anything must not be on screen.
     */
    fun state(said: String?): State {
        val text = said?.trim().orEmpty()
        return when {
            text.startsWith(PLAYING_PREFIX) -> State.PLAYING
            text.startsWith(PAUSED_PREFIX) -> State.PAUSED
            else -> State.NONE
        }
    }

    /** The states the plate is drawn in. Kept as a function so the rule has one home. */
    fun shown(state: State): Boolean = state == State.PLAYING || state == State.PAUSED

    /**
     * The buttons for a state - the transport, reflecting which it is. A
     * paused track offers [PLAY] and no [PAUSE]; a playing one offers [PAUSE]
     * and no [PLAY]. [PREVIOUS] and [NEXT] belong to both.
     */
    fun transport(state: State): List<String> = when (state) {
        State.PLAYING -> listOf(PREVIOUS, PAUSE, NEXT)
        State.PAUSED -> listOf(PREVIOUS, PLAY, NEXT)
        State.NONE -> emptyList()
    }

    /**
     * What the PC answers a BUTTON with - short acknowledgements that name no
     * track and carry no state (`jarvis_media._SAID`): "Playing.", "Paused.",
     * "Skipped to the next.", "Back to the previous.".
     *
     * The plate never reads a STATE out of one of these: only the descriptive
     * `GET` sentence is written as "Playing: …" or "Paused: …", and the
     * gate is built on that. After a button the plate reads the PC again for
     * the descriptive sentence and the new state, and shows the button's own
     * answer only when it is NOT one of these - a refusal or a notice, which
     * is the honest thing to put on screen.
     */
    val ACKS: Set<String> = setOf(
        "Playing.", "Paused.", "Skipped to the next.", "Back to the previous.",
    )

    /** Whether the PC's answer to a button is a plain acknowledgement. */
    fun ack(said: String?): Boolean = said?.trim() in ACKS

    /** The PC's own words for "nothing is playing" (`jarvis_media._REASON_WORDS["nothing"]`). */
    const val NOTHING = "Nothing seems to be playing right now."

    /**
     * How often Home re-reads what is playing.
     *
     * The plate is hidden whenever no track is loaded, and a hidden control
     * that never asked again could never appear when the owner starts a track
     * - so the read has to keep going while Home is on screen. The same shape
     * and the same order of cost as Home's other small reads
     * (`SkySettings.POLL_MS`, `InboxTidy.POLL_MS`): one small local request
     * every fifteen seconds, never while the link is down.
     */
    const val POLL_MS = 15_000L

    /** A PC without the routes. */
    fun missing(e: ApiError): Boolean =
        e == ApiError.NotFound || (e is ApiError.Server && e.code == 404)
}
