package com.jarvis.client.platform

import android.app.KeyguardManager
import android.content.Context

/**
 * Is the phone's own lock screen secure (a PIN, pattern, password or
 * biometric - Android's `KeyguardManager.isDeviceSecure`)?
 *
 * Notification content may only be shown in the clear when this is true:
 * Android's `VISIBILITY_PRIVATE` hides a notification's body on a SECURE lock
 * screen, but shows it on a swipe-only one. When this is false, every notifier
 * uses its redacted public words instead (M12,
 * `data/Security.kt` `SecurityRules.notificationsLocked`).
 *
 * Any failure reads as false: "cannot prove the phone is locked" is treated as
 * "someone else may be looking", the safe direction.
 */
object DeviceSecure {
    fun isSecure(context: Context): Boolean = runCatching {
        (context.applicationContext.getSystemService(Context.KEYGUARD_SERVICE) as? KeyguardManager)
            ?.isDeviceSecure == true
    }.getOrDefault(false)
}
