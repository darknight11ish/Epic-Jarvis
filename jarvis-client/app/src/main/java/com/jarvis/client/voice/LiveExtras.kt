package com.jarvis.client.voice

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.intOrNull

/**
 * The Jarvis Live extras on this phone (the owner's decisions of 2026-09-28,
 * CLAUDE.md "Jarvis Live extras, all yes"), their rules in one place, with no
 * Android in this file so LiveExtrasTest runs them:
 *
 *  - the Quick Settings tile ([tile]): start or end Live, and the minutes
 *    left while it is on here (service/LiveTileService.kt);
 *  - the headset button ([HeadsetKeys]): a press stops Jarvis talking, a
 *    long press turns the microphone off or on. It never approves anything
 *    - cards are decided by tapping only (service/LiveService.kt's media
 *    session calls nothing else);
 *  - "Live ended - Resume" ([resumeFor]): after Live ended here by itself
 *    in a way it can be resumed, a notification offers Resume for the rest
 *    of the PC's 10 minutes;
 *  - the microphone ([pickHeadset], [micWords]): a Bluetooth headset's
 *    microphone is preferred while one is connected, the phone's own
 *    otherwise, and the Live screen says which.
 */
object LiveExtras {

    // ---- the tile ------------------------------------------------------

    /** What the tile shows: on (Live on this phone) or off, and its second line. */
    data class Tile(val on: Boolean, val subtitle: String)

    const val TILE_LABEL = "Jarvis Live"

    fun tile(status: JsonObject?, connected: Boolean, me: String = LiveRules.ME): Tile {
        if (LiveRules.onHere(status, me)) {
            val minutes = (status?.get("minutes_left") as? JsonPrimitive)?.takeIf { !it.isString }?.intOrNull
            return Tile(true, if (minutes != null) "$minutes min left" else "On")
        }
        if (!connected) return Tile(false, "Offline")
        val device = (status?.get("device") as? JsonPrimitive)?.takeIf { it.isString }?.content
        val on = (status?.get("on") as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull == true
        if (on && device != null && device != me) return Tile(false, "On your ${LiveRules.deviceWords(device)}")
        return Tile(false, "Off")
    }

    // ---- the headset button -------------------------------------------

    /** What one headset-button event does. Nothing here can approve anything. */
    enum class Press { NONE, STOP_TALKING, MIC_TOGGLE }

    /** Held this long, a press is a long press. */
    const val LONG_PRESS_MS = 600L

    /**
     * Android's key codes a headset's one button sends (KeyEvent):
     * HEADSETHOOK 79, MEDIA_PLAY_PAUSE 85, MEDIA_PLAY 126, MEDIA_PAUSE 127.
     */
    val BUTTON_KEYS: Set<Int> = setOf(79, 85, 126, 127)

    /** KeyEvent.ACTION_DOWN and ACTION_UP. */
    const val DOWN = 0
    const val UP = 1

    /**
     * Turns the button's down and up events into one [Press]: a short press
     * on release, a long press as soon as it has been held [LONG_PRESS_MS]
     * (from the key's repeats), and nothing more until it is let go.
     */
    class HeadsetKeys {
        private var downAt: Long? = null
        private var longDone = false

        fun onKey(action: Int, keyCode: Int, repeat: Int, downTime: Long, eventTime: Long): Press {
            if (keyCode !in BUTTON_KEYS) return Press.NONE
            when (action) {
                DOWN -> {
                    if (repeat == 0 || downAt == null) {
                        downAt = downTime
                        longDone = false
                    }
                    val held = eventTime - (downAt ?: eventTime)
                    if (!longDone && repeat > 0 && held >= LONG_PRESS_MS) {
                        longDone = true
                        return Press.MIC_TOGGLE
                    }
                    return Press.NONE
                }
                UP -> {
                    val start = downAt ?: return Press.NONE
                    downAt = null
                    if (longDone) {
                        longDone = false
                        return Press.NONE
                    }
                    return if (eventTime - start >= LONG_PRESS_MS) Press.MIC_TOGGLE else Press.STOP_TALKING
                }
            }
            return Press.NONE
        }
    }

    // ---- "Live ended - Resume" ------------------------------------------

    const val RESUME_TITLE = "Jarvis Live ended"
    const val RESUME_BUTTON = "Resume Live"

    /**
     * How long "Live ended - Resume" should stay up, in milliseconds - or null
     * when there is nothing to resume here: Live ended on THIS phone, the PC
     * says it can be resumed, and the PC's own window (`limits.resume_s`,
     * 10 minutes) has not run out.
     */
    fun resumeFor(status: JsonObject?, me: String = LiveRules.ME): Long? {
        val o = status ?: return null
        val state = (o["state"] as? JsonPrimitive)?.takeIf { it.isString }?.content
        val device = (o["ended_device"] as? JsonPrimitive)?.takeIf { it.isString }?.content
        val resumable = (o["resumable"] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull == true
        if (state != "ended" || device != me || !resumable) return null
        val ago = (o["ended_ago_s"] as? JsonPrimitive)?.intOrNull ?: 0
        val window = ((o["limits"] as? JsonObject)?.get("resume_s") as? JsonPrimitive)?.intOrNull
            ?: LiveRules.RESUME_S
        val left = window - ago
        return if (left > 0) left * 1000L else null
    }

    // ---- the microphone ---------------------------------------------------

    /** One microphone Android offers: its type (AudioDeviceInfo.TYPE_*) and name. */
    data class Mic(val type: Int, val name: String)

    /**
     * The Bluetooth headset types, most preferred first: a Bluetooth LE
     * Audio headset (AudioDeviceInfo.TYPE_BLE_HEADSET, 26), then a classic
     * hands-free one (TYPE_BLUETOOTH_SCO, 7).
     */
    val HEADSET_TYPES: List<Int> = listOf(26, 7)

    /** The Bluetooth headset to prefer among [devices], or null to use the phone's own. */
    fun pickHeadset(devices: List<Mic>): Mic? =
        HEADSET_TYPES.firstNotNullOfOrNull { t -> devices.firstOrNull { it.type == t } }

    const val MIC_PHONE = "Microphone: this phone's"
    const val MIC_HEADSET = "Microphone: your Bluetooth headset"
    const val MIC_FELL_BACK = "Microphone: this phone's - the Bluetooth headset's could not be used"

    /** What the Live screen says about the microphone in use. */
    fun micWords(headset: Mic?, fellBack: Boolean = false): String = when {
        fellBack -> MIC_FELL_BACK
        headset == null -> MIC_PHONE
        headset.name.isBlank() -> MIC_HEADSET
        else -> "$MIC_HEADSET (${headset.name.take(40)})"
    }

    /** Said under the headset line on the Live screen: what the button does, and its limit. */
    const val HEADSET_HINT = "Headset button: press to stop Jarvis talking, hold to turn the " +
        "microphone off or on. It never approves anything. On some phones holding it opens " +
        "the phone's assistant instead - Mic off is here and in the notification too."
}
