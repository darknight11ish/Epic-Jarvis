package com.jarvis.client.data

import android.content.Context
import android.content.Intent
import android.provider.Settings
import com.jarvis.client.service.JarvisAccessibilityService
import androidx.core.content.edit

/**
 * The Android-backed half of [AppControl]: the option and the allow-list saved
 * in this phone's own app storage, and the two read-only facts only Android can
 * answer (Android's own accessibility switch, and the app list).
 *
 * Per-device, never synced to the PC or another phone - the same rule
 * [NotificationAllowListStore]'s list already follows, and for the same reason:
 * which apps are even installed here is a fact about this one phone.
 *
 * EMPTY BY DEFAULT: nothing is read or done until the owner adds an app. Adding
 * an app that is Jarvis itself, a password manager or a bank-looking app is
 * refused here in plain words ([ScreenNever.blocked]), before anything is saved.
 */
class AppControlStore(private val context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    /** The owner's option. OFF on a fresh install and when anything is unreadable. */
    fun optionOn(): Boolean = prefs.getBoolean(KEY_OPTION, false)

    /** The owner's own switch. Off is instant; on is explained on the screen and needs Android's too. */
    fun setOption(on: Boolean) {
        prefs.edit { putBoolean(KEY_OPTION, on) }
    }

    /** The owner's list, EMPTY by default; a missing or broken file reads as empty, never everything. */
    fun entries(): List<AppControl.AppEntry> = AppControl.parseStored(prefs.getString(KEY_APPS, null))

    fun isAllowed(packageName: String?): Boolean =
        packageName != null && entries().any { it.packageName == packageName }

    /**
     * Adds one app. Refused when [AppControl.add] refuses it, and refused first
     * when Android's own category says it is a bank/payment app, when it is a
     * known password manager, or when it is Jarvis itself.
     */
    fun add(packageName: String): AppControl.AddResult {
        val pkg = packageName.trim()
        val result = AppControl.add(entries(), pkg, labelOf(pkg), refusedApp(pkg))
        if (result.error == null) {
            prefs.edit { putString(KEY_APPS, AppControl.storeJson(result.entries)) }
        }
        return result
    }

    /** Taking one off is instant: it only ever lets Jarvis do less. */
    fun remove(packageName: String) {
        prefs.edit { putString(KEY_APPS, AppControl.storeJson(AppControl.remove(entries(), packageName))) }
    }

    /** The app's own display name, or the package name when Android will not say. */
    fun labelOf(packageName: String): String = runCatching {
        val pm = context.packageManager
        pm.getApplicationLabel(pm.getApplicationInfo(packageName, 0)).toString()
    }.getOrNull()?.takeIf { it.isNotBlank() } ?: packageName

    /** Android's declared Play Store category, or null when it declared none / on old versions. */
    private fun category(packageName: String): Int? = runCatching {
        context.packageManager.getApplicationInfo(packageName, 0).category
            .takeIf { it != -1 } // ApplicationInfo.CATEGORY_UNDEFINED
    }.getOrNull()

    private fun refusedApp(packageName: String): String? = when (
        ScreenNever.blocked(packageName, emptySet(), category(packageName))
    ) {
        ScreenNever.Why.JARVIS -> AppControl.REFUSE_JARVIS
        ScreenNever.Why.PASSWORD_MANAGER -> AppControl.REFUSE_PASSWORD_MANAGER
        ScreenNever.Why.BANKING -> AppControl.REFUSE_BANKING
        ScreenNever.Why.OWNER, ScreenNever.Why.UNKNOWN_APP, null -> null
    }

    /**
     * Android's own Accessibility switch, READ-ONLY: the one fact only Android
     * can answer. A refusal to read it is CANNOT_READ (the screen says so and
     * points at Android's settings); it is never guessed ON or OFF.
     */
    fun androidState(): AppControl.AndroidState {
        val raw = try {
            Settings.Secure.getString(
                context.contentResolver,
                Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
            )
        } catch (_: Exception) {
            null
        }
        return AppControl.androidState(raw, component())
    }

    /** The component name Android's list must contain: this app's own package and service. */
    fun component(): String = AppControl.component(
        context.packageName,
        JarvisAccessibilityService::class.java.name,
    )

    /** This phone's installed apps, for the picker - read off the main thread by the screen. */
    fun installedApps(): List<NotificationAllowListStore.InstalledApp> =
        NotificationAllowListStore(context).installedApps(skipNotificationList = false)

    /**
     * Opens Android's own Accessibility settings, where the owner must ALSO
     * turn Jarvis on. Nothing here turns that on: only Android can.
     */
    fun openAccessibilitySettings() {
        val intent = Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        runCatching { context.startActivity(intent) }
    }

    private companion object {
        const val PREFS = "jarvis_app_control"
        const val KEY_OPTION = "option_on"
        const val KEY_APPS = "apps"
    }
}
