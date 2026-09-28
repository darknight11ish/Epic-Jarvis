package com.jarvis.client.data

/**
 * "\"Hey Jarvis\" is off since the phone restarted - tap to turn it back on."
 * (the owner's choice of 2026-09-28, "Phone conveniences"; docs/JARVIS-API.md
 * section 81.1). The idea is Dicio's (GPL - the idea only, no code).
 *
 * WHY. "Listen on this phone" ([com.jarvis.client.service.WakeWordService])
 * is never started at boot, on purpose: Android does not let an app open the
 * microphone from the background, and Jarvis would not want to anyway - the
 * microphone opens only from the owner's own tap. So after a restart (or an
 * app update, which also ends it) it was silently off, and nothing said so.
 *
 * WHAT. At boot, if the owner had it on, ONE quiet notification. Tapping it
 * opens Jarvis, which starts listening straight away - from the owner's tap,
 * with the app in front, the only way Android allows. With App lock on, the
 * fingerprint comes first and listening starts only after it. Nothing is
 * started by the notification itself, and nothing at all if it is ignored.
 *
 * Pure Kotlin, so `WakeResumeTest` holds the decision on a plain JVM.
 */
object WakeResume {
    const val BOOT = "android.intent.action.BOOT_COMPLETED"
    const val UPDATED = "android.intent.action.MY_PACKAGE_REPLACED"

    const val TITLE_BOOT = "\"Hey Jarvis\" is off since the phone restarted"
    const val TITLE_UPDATED = "\"Hey Jarvis\" is off since Jarvis was updated"
    const val TEXT = "Tap to turn it back on. Jarvis never opens the microphone by itself."

    /** Said on Home once listening is back on from the notification. */
    const val BACK_ON = "Listening for \"hey Jarvis\" on this phone again."

    /**
     * Whether to post the notice after [action]. Only for a restart or an
     * update, only on a paired phone, and only if the owner had "Listen on
     * this phone" on when it ended ([wanted]: set when the owner starts it,
     * cleared when anyone stops it on purpose).
     */
    fun offer(action: String?, paired: Boolean, wanted: Boolean): Boolean =
        (action == BOOT || action == UPDATED) && paired && wanted

    fun title(action: String?): String = if (action == UPDATED) TITLE_UPDATED else TITLE_BOOT
}
