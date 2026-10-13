package com.jarvis.client

/**
 * Why the talk button cannot start a clip, in words, said where the button is.
 *
 * The owner, 2026-10-13: "the mic button in the bottom right hand corner of
 * the android app doesnt work if i tap it or hold it down". Its tap and hold
 * gestures are fine - [com.jarvis.client.ui.parts.VoiceButton] calls
 * `onBegin`/`onRelease` on both, and its whole `pointerInput` returns at once
 * when `enabled` is false, so a disabled microphone does exactly nothing. The
 * button is disabled whenever `state.link != LinkState.CONNECTED ||
 * state.streaming`, and the app never said which. That is the defect this file
 * fixes, and the project had already written it down
 * (`docs/ease-audit-2026-09-27/everyday.md:65`: "The reason ... is shown only
 * on the Checks screen, never on Home").
 *
 * This is the same shape as [LinkWords.composerHeldLine], which was added on
 * 2026-10-10 for the identical fault on Send: a greyed control that never
 * reaches the runtime's own blocker, so the runtime's sentence is never shown.
 * Every reason a tap can do nothing is named here, in the order a tap meets
 * them, and the words are pure so a JVM test can hold them still.
 *
 * What this file deliberately does NOT do: re-enable the button. The link gate
 * is correct behaviour (rule 4 - nothing acts on a link that cannot be
 * trusted), and the voice-not-offered gate is the PC's own answer. Naming the
 * reason is the fix; loosening a gate is not.
 */
object MicWords {

    /**
     * An answer is on its way in or out. The button is greyed for exactly the
     * same span as the composer's Send becomes Stop, so the fix is the other
     * button's, named rather than implied.
     */
    const val ANSWERING =
        "Jarvis is answering. Tap Stop, or wait for it to finish, then hold the microphone."

    /**
     * The microphone permission is not held.
     *
     * A tap in this state launches Android's own dialog (`MainActivity`'s
     * `beginVoice` -> `micPermission.launch(RECORD_AUDIO)`), and the capture
     * starts by itself if the owner allows it - so on a first tap the dialog
     * IS the answer, and this line explains the tap that appeared to do
     * nothing. After a denial - and after a permanent denial, where Android
     * shows no dialog at all and the callback simply reports `granted =
     * false` - every later tap does nothing whatsoever and says nothing. That
     * second case is the silent one, and it is why this line exists.
     */
    const val NO_PERMISSION =
        "This phone has not allowed the microphone. Allow it in Android's app settings, then hold " +
            "the microphone again."

    /**
     * The PC has not offered the talk button: `canPushToTalk` is false, which
     * is the voice check not being trained there yet (or no speech-to-text
     * engine). The PC's own words for it are on Checks, then "Train my voice";
     * this line is the door to them, not a second explanation.
     */
    const val NOT_OFFERED =
        "Your PC has not offered the microphone yet - that needs your voice trained. Open " +
            "Checks, then Train my voice."

    /**
     * The reason the talk button cannot start a clip right now, or null when
     * it can. The order is the order a tap meets the reasons:
     *
     *  1. the link is not up - the words could not be checked or sent anyway,
     *     and this is the same sentence the rest of Home already shows under a
     *     control it has greyed for the link;
     *  2. the microphone is not allowed on this phone;
     *  3. an answer is already streaming;
     *  4. the PC has not offered push-to-talk.
     *
     * @param voiceOffered `VoiceStatus.canPushToTalk` - false on a PC whose
     *   voice check is not trained, and on one with no transcription engine.
     */
    fun heldLine(
        link: LinkState,
        streaming: Boolean,
        micAllowed: Boolean,
        voiceOffered: Boolean,
    ): String? = when {
        link != LinkState.CONNECTED -> LinkWords.composerHeldLine(link)
        !micAllowed -> NO_PERMISSION
        streaming -> ANSWERING
        !voiceOffered -> NOT_OFFERED
        else -> null
    }
}
