package com.jarvis.client.platform

import android.app.KeyguardManager
import android.content.Context

/**
 * Two different questions about this phone's lock screen, kept together
 * because both must fail in the SAFE direction and the safe direction
 * differs:
 *
 *  - [isSecure]: is the lock screen secure (a PIN, pattern, password or
 *    biometric - Android's `KeyguardManager.isDeviceSecure`)? Notification
 *    content may only be shown in the clear when this is true: Android's
 *    `VISIBILITY_PRIVATE` hides a notification's body on a SECURE lock
 *    screen, but shows it on a swipe-only one. When this is false, every
 *    notifier uses its redacted public words instead (M12,
 *    `data/Security.kt` `SecurityRules.notificationsLocked`). Any failure
 *    reads as false: "cannot prove the phone is locked" is treated as
 *    "someone else may be looking", the safe direction.
 *
 *  - [isLocked]: is the phone locked RIGHT NOW? Read once, at the moment the
 *    owner presses the mic, for the owner's setting of 2026-11-05 ("read an
 *    answer that uses what Jarvis remembers aloud on my unlocked phone").
 *    Any failure reads as TRUE there, because that answer would SPEAK: see
 *    the method's own comment.
 */
object DeviceSecure {
    fun isSecure(context: Context): Boolean = runCatching {
        (context.applicationContext.getSystemService(Context.KEYGUARD_SERVICE) as? KeyguardManager)
            ?.isDeviceSecure == true
    }.getOrDefault(false)

    /**
     * Is the phone locked NOW - the keyguard is up and needs the PIN, pattern,
     * password or biometric to get past (`KeyguardManager.isDeviceLocked`)?
     *
     * This is the ONE fact the owner's setting of 2026-11-05 needs, and it is
     * read at the MOMENT HE PRESSES THE MIC, then carried with that question:
     * "the phone was unlocked when I asked". It is never re-read later, so an
     * answer that arrives after the phone locks still counts as asked on an
     * unlocked phone - his own instruction.
     *
     * Any failure reads as **locked**, the opposite direction from [isSecure]
     * and for the opposite reason: there a wrong answer redacts more, here a
     * wrong answer SPEAKS more. "Cannot prove the phone is unlocked" is not
     * "unlocked".
     */
    fun isLocked(context: Context): Boolean = runCatching {
        val keyguard = context.applicationContext
            .getSystemService(Context.KEYGUARD_SERVICE) as? KeyguardManager
        // No KeyguardManager at all: this build cannot say, so it counts as
        // locked (see the doc comment above).
        keyguard?.isDeviceLocked ?: true
    }.getOrDefault(true)
}
