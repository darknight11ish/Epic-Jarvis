package com.jarvis.client.voice

/**
 * Which microphone Jarvis Live records from, and what the phone's audio system
 * must be told *before* the recorder is opened.
 *
 * WHY THIS FILE EXISTS. The owner, 2026-11-02: *"when I am using jarvis live in
 * my car and my phone is connected to Bluetooth it acts like it is in a call
 * but jarvis cannot hear me. the mic doesn't seem to be working properly at
 * all."* A car's Bluetooth is a **hands-free** device (HFP/SCO): its microphone
 * only exists while the phone is in a CALL. Android brings the SCO link up and
 * routes the microphone from the car only for the *communication* path - a
 * recorder opened on `VOICE_COMMUNICATION` with the audio mode at
 * `MODE_IN_COMMUNICATION`, or with the car as the communication device.
 *
 * The old code did half of that: it made the car the "communication device"
 * and then recorded with `VOICE_RECOGNITION` while the audio mode stayed
 * `MODE_NORMAL`, so Android never brought the link up. The car's head unit
 * showed a call; the recorder got silence.
 *
 * WHY IT IS A SEPARATE, PURE FILE. That failure only happens in a car, and a
 * JVM test cannot sit in one. So every decision is made here, from plain
 * values - the connected devices, whether Jarvis is talking, the owner's
 * microphone choice - and `service/LiveService.kt` only does the Android calls
 * this file asks for. Nothing here imports `android.*`, the same rule as
 * [LiveRules] and [LiveExtras], so `LiveAudioRouteTest` runs on the JVM. The
 * platform numbers below are named here for that reason, and pinned against
 * the real ones in that test.
 */
object LiveAudioRoute {

    // ---- the platform values, named here so this file has no Android in it ----
    //
    // AudioManager.MODE_*: NORMAL 0, RINGTONE 1, IN_CALL 2, IN_COMMUNICATION 3.
    const val MODE_NORMAL = 0
    const val MODE_IN_CALL = 2
    const val MODE_IN_COMMUNICATION = 3

    // MediaRecorder.AudioSource.*: MIC 1, VOICE_RECOGNITION 6, VOICE_COMMUNICATION 7.
    const val SRC_VOICE_RECOGNITION = 6
    const val SRC_VOICE_COMMUNICATION = 7

    // AudioDeviceInfo.TYPE_*: BUILTIN_SPEAKER 2, WIRED_HEADSET 3, BLUETOOTH_SCO 7,
    // BLUETOOTH_A2DP 8, BUILTIN_MIC 15, USB_HEADSET 22, BLE_HEADSET 26,
    // BLE_SPEAKER 27. The two headset types are [LiveExtras.HEADSET_TYPES]
    // (26, 7) - the order the app already prefers.
    const val TYPE_BUILTIN_SPEAKER = 2
    const val TYPE_WIRED_HEADSET = 3
    const val TYPE_BLUETOOTH_SCO = 7
    const val TYPE_BLUETOOTH_A2DP = 8
    const val TYPE_BUILTIN_MIC = 15
    const val TYPE_USB_HEADSET = 22
    const val TYPE_BLE_HEADSET = 26
    const val TYPE_BLE_SPEAKER = 27

    // ---- the owner's microphone choice -------------------------------------

    /**
     * "Microphone when a car is connected" - nothing else on this phone changes
     * it, and AUTO is the default. It is here rather than in the service so the
     * decision can be tested for every value; PHONE is the escape hatch if a
     * particular car's microphone still cannot be heard, and needs no new
     * decision when a row for it is added.
     */
    enum class MicChoice(val id: String) {
        /** The car's (or headset's) microphone when Bluetooth offers one, the phone's own otherwise. */
        AUTO("auto"),

        /** Always this phone's own microphone, even with a car connected. */
        PHONE("phone"),

        /** Only a Bluetooth microphone; the phone's own if none is connected. */
        HEADSET("headset"),
    }

    /** The saved choice, or [MicChoice.AUTO] for anything unknown - a bad value must never wedge the microphone. */
    fun choiceOf(saved: String?): MicChoice = MicChoice.entries.firstOrNull { it.id == saved } ?: MicChoice.AUTO

    // ---- what the service can see ------------------------------------------

    /**
     * The phone's audio state, as plain values (no Android types):
     *
     * @param inputTypes `AudioManager.getDevices(GET_DEVICES_INPUTS)` types.
     * @param outputTypes `AudioManager.getDevices(GET_DEVICES_OUTPUTS)` types.
     * @param communication `AudioManager.availableCommunicationDevices`, names
     *   included because the Live screen says which microphone it is using.
     * @param speaking Jarvis is talking: the reply is a voice call so the echo
     *   canceller can take Jarvis's own voice out of what the microphone hears.
     * @param choice the owner's microphone choice ([MicChoice]).
     */
    data class Inputs(
        val inputTypes: List<Int> = emptyList(),
        val outputTypes: List<Int> = emptyList(),
        val communication: List<LiveExtras.Mic> = emptyList(),
        val speaking: Boolean = false,
        val choice: MicChoice = MicChoice.AUTO,
    )

    /**
     * The whole answer: how to open the recorder, what the phone's audio mode
     * must be while it records, and which device must be asked for.
     *
     * @param source the `MediaRecorder.AudioSource` to open the recorder with.
     * @param holdMode the `AudioManager` mode the app must hold while recording,
     *   or null to leave the mode alone ([com.jarvis.client.audio.Speaker]
     *   owns it while Jarvis talks).
     * @param communicationType the `AudioDeviceInfo` type to make the
     *   communication device, or null for none.
     * @param needsScoLink true when the SCO/HFP call link itself has to come up
     *   for this microphone to exist (Android 12+ does that through
     *   `setCommunicationDevice`; `startBluetoothSco` is the old way and the
     *   service falls back to it only if the modern call is refused).
     * @param expectedInputType the input device type to prefer on the recorder,
     *   or null to leave the choice to Android.
     * @param callMode true for the call configuration - the car's (or a
     *   headset's) hands-free microphone - which is what the Live screen and
     *   the call detector must know about.
     * @param mediaOnly true when Bluetooth audio is connected but offers no
     *   microphone at all (A2DP media only, or a BLE speaker). The route is
     *   unchanged then, but the Live screen says why the car cannot be heard.
     * @param mic the Bluetooth microphone in use, for the Live screen's words.
     * @param fellBack true when a microphone was wanted and could not be used.
     */
    data class Route(
        val source: Int,
        val holdMode: Int?,
        val communicationType: Int?,
        val needsScoLink: Boolean,
        val expectedInputType: Int?,
        val callMode: Boolean,
        val mediaOnly: Boolean = false,
        val mic: LiveExtras.Mic? = null,
        val fellBack: Boolean = false,
    ) {
        /** What the Live screen says about the microphone in use. */
        val words: String
            get() = LiveExtras.micWords(mic, fellBack = fellBack, mediaOnly = mediaOnly)
    }

    // ---- the decision ------------------------------------------------------

    /**
     * The route for [i], pure: the same inputs always give the same answer.
     *
     * THE RULES, in order:
     *
     * 1. **The owner said this phone's** ([MicChoice.PHONE]): the phone's own
     *    microphone, exactly as if no Bluetooth were connected.
     * 2. **Bluetooth offers a hands-free microphone** (a car, a headset, earbuds
     *    - `TYPE_BLUETOOTH_SCO` or `TYPE_BLE_HEADSET` in the communication
     *    devices): the call configuration. `VOICE_COMMUNICATION` is the only
     *    source that receives audio from that microphone, the mode must be
     *    `MODE_IN_COMMUNICATION` for the link to exist, and the car must be the
     *    communication device. It is the SAME configuration whether Jarvis is
     *    talking or listening, so the recorder is not torn down at every reply.
     * 3. **Anything else**: unchanged - `VOICE_RECOGNITION` while listening
     *    (the un-beautified path the voice print was trained on), plus
     *    `VOICE_COMMUNICATION` while Jarvis talks so the echo canceller works.
     *    A wired or USB headset needs no help: Android already records from it.
     *    Bluetooth that offers no microphone (A2DP only) cannot be a microphone
     *    at all, and the screen says so - that is the difference between "the
     *    car has no microphone" and "Jarvis is broken".
     */
    fun decide(i: Inputs): Route {
        val wanted = if (i.choice == MicChoice.PHONE) null else handsFree(i.communication)
        if (wanted != null) {
            return Route(
                source = SRC_VOICE_COMMUNICATION,
                holdMode = MODE_IN_COMMUNICATION,
                communicationType = wanted.type,
                needsScoLink = true,
                expectedInputType = wanted.type,
                callMode = true,
                mic = wanted,
            )
        }
        return Route(
            source = if (i.speaking) SRC_VOICE_COMMUNICATION else SRC_VOICE_RECOGNITION,
            holdMode = null,
            communicationType = null,
            needsScoLink = false,
            expectedInputType = null,
            callMode = false,
            mediaOnly = i.choice != MicChoice.PHONE && mediaOnly(i),
            fellBack = i.choice == MicChoice.HEADSET,
        )
    }

    /**
     * The same decision with the Bluetooth microphone refused by Android (the
     * communication device could not be made, so the call link never came up):
     * the phone's own microphone, and the Live screen says the Bluetooth one
     * could not be used. Recording from a route Android refused would be
     * silence - which is the bug this file exists to stop.
     */
    fun fallback(i: Inputs): Route = decide(i.copy(choice = MicChoice.PHONE)).copy(
        mic = handsFree(i.communication),
        fellBack = true,
    )

    // ---- putting the phone back --------------------------------------------

    /**
     * What has to be put back when Live stops (or its route changes):
     * `mode` is the audio mode to restore, or null when the app never changed
     * it; `clearCommunicationDevice` says the app's own communication device
     * must be let go.
     */
    data class Undo(val mode: Int?, val clearCommunicationDevice: Boolean)

    /**
     * The undo for [applied], given the mode the phone was in before the app
     * changed it. Only a mode the app actually held is restored - the phone
     * route never touches the mode (the Speaker owns it while Jarvis talks), so
     * stopping Live must not reset a mode somebody else is using.
     */
    fun undo(applied: Route, beforeMode: Int): Undo = Undo(
        mode = if (applied.holdMode != null) beforeMode else null,
        clearCommunicationDevice = applied.communicationType != null,
    )

    // ---- helpers -----------------------------------------------------------

    /** The hands-free (microphone-capable) Bluetooth device among [devices], in the app's existing order. */
    private fun handsFree(devices: List<LiveExtras.Mic>): LiveExtras.Mic? = LiveExtras.pickHeadset(devices)

    /** Bluetooth is connected, but only for sound out: no hands-free device offers a microphone. */
    private fun mediaOnly(i: Inputs): Boolean {
        val media = i.outputTypes.any { it == TYPE_BLUETOOTH_A2DP || it == TYPE_BLE_SPEAKER }
        val microphone = handsFree(i.communication) != null || i.inputTypes.any { it in LiveExtras.HEADSET_TYPES }
        return media && !microphone
    }
}
