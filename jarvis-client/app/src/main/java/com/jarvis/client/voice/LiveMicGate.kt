package com.jarvis.client.voice

/**
 * The microphone check BEFORE Jarvis Live starts on this phone (LM-3A; the
 * Pixel 9 failure of 2026-10-18: `RECORD_AUDIO: granted=false`, Live died
 * instantly and said nothing, because the owner was away from adb).
 *
 * PURE, so `LiveMicGateTest` holds every branch on the JVM without a device.
 * The caller reads [android.content.ContextCompat.checkSelfPermission] at
 * EVERY start and again on resume, so a permission Android 17 AUTO-REVOKED
 * while the app sat unused reaches exactly this decision - the same as one
 * never granted. Nothing here can claim a permission is held: [Decision.start]
 * is only ever true when the platform said so at that moment, and a missing
 * one NEVER starts Live on a promise (the owner's Start tap is the start).
 *
 * The two buttons have different jobs, and both are always honest:
 *  - [ALLOW] launches Android's own runtime request, which is only offered
 *    when the system will still show it (a rationale is owed, or this process
 *    has not asked yet);
 *  - [OPEN_SETTINGS] opens THIS app's Android page, the only route when the
 *    owner answered "don't ask again" (`USER_SET` - the system will not
 *    re-prompt).
 */
object LiveMicGate {
    /** One plain sentence on the Live card: what is missing, not a diagnosis. */
    const val NEED = "Jarvis Live needs Microphone permission on this phone."

    /** The first button, when Android will still show its own dialog. */
    const val ALLOW = "Allow microphone"

    /** Always offered: the one route when Android will not re-prompt. */
    const val OPEN_SETTINGS = "Open app permission settings"

    /**
     * What the Live card must do now.
     *
     * `start` is true only with the permission held. Otherwise `banner` is the
     * sentence to draw and the two flags say which buttons work: `offerAllow`
     * when the runtime dialog is still appropriate, `offerSettings` always
     * (Settings is the fallback that cannot be refused by the platform).
     */
    data class Decision(
        val start: Boolean,
        val banner: String = "",
        val offerAllow: Boolean = false,
        val offerSettings: Boolean = false,
    )

    /**
     * @param granted the platform's answer RIGHT NOW, never a remembered one
     *   (Android 17's auto-revoke is exactly why).
     * @param rationale `shouldShowRequestPermissionRationale`'s answer - true
     *   when the system would still show the dialog with an explanation.
     * @param askedBefore true when this process already launched the runtime
     *   request once; before the first ask `rationale` is false too, which is
     *   why both inputs are needed to tell "never asked" from "don't ask again".
     */
    fun decide(granted: Boolean, rationale: Boolean, askedBefore: Boolean): Decision {
        if (granted) return Decision(start = true)
        // Askable when the platform owes a rationale, or when this process has
        // not asked yet. After a "don't ask again" neither is true, so only
        // Settings is offered - pressing Allow there would be a silent no-op.
        val canAsk = rationale || !askedBefore
        return Decision(start = false, banner = NEED, offerAllow = canAsk, offerSettings = true)
    }
}
