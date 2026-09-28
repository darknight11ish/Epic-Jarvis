package com.jarvis.client.data

import android.app.role.RoleManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.edit

/**
 * The Android-backed half of [NotificationAllowList]: reads this phone's
 * installed apps and its own default-SMS-app answer, and persists the
 * list the owner has actually chosen. Per-device, never synced to the PC
 * or to another phone - the same rule [ClientSettings]'s other per-device
 * settings already follow, and for the same reason: which apps are even
 * installed here is a fact about this one phone.
 *
 * EMPTY BY DEFAULT (CLAUDE.md, 2026-09-26). Nothing is captured for any
 * app until the owner adds it here, and [PhoneNotificationListenerService]
 * reads this same list before it stores anything at all.
 */
class NotificationAllowListStore(private val context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    /** The package names the owner has added, empty on a fresh install. */
    fun packages(): Set<String> = prefs.getStringSet(KEY_PACKAGES, emptySet()).orEmpty().toSet()

    fun contains(packageName: String): Boolean = packageName in packages()

    /**
     * This phone's own default SMS/Messages app(s), from Android's own
     * `RoleManager.ROLE_SMS` (API 29+) - the strong signal
     * [NotificationAllowList.isSmsPackage] is built around. Empty, never a
     * guess, on an older phone or if the call fails for any reason; the
     * static fallback list in [NotificationAllowList] still applies either
     * way.
     */
    private fun smsRoleHolders(): Set<String> {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return emptySet()
        return runCatching {
            val rm = context.getSystemService(RoleManager::class.java) ?: return emptySet()
            if (!rm.isRoleAvailable(RoleManager.ROLE_SMS)) return emptySet()
            rm.getRoleHolders(RoleManager.ROLE_SMS).toSet()
        }.getOrDefault(emptySet())
    }

    /**
     * [packageName]'s declared Play Store category (`ApplicationInfo
     * .category`, API 26+), or null when it declared none, is not
     * installed, or the read fails for any reason - never a guess.
     */
    private fun category(packageName: String): Int? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return null
        return runCatching {
            val info = context.packageManager.getApplicationInfo(packageName, 0)
            info.category.takeIf { it != -1 } // ApplicationInfo.CATEGORY_UNDEFINED
        }.getOrNull()
    }

    /**
     * Adds [packageName], unless [NotificationAllowList.evaluateAdd]
     * refuses it (SMS or banking) - checked against THIS phone's own live
     * category and SMS-role answers, never a stale guess. Only
     * [NotificationAllowList.AddResult.Added] changes the saved list.
     */
    fun add(packageName: String): NotificationAllowList.AddResult {
        val result = NotificationAllowList.evaluateAdd(
            packageName,
            current = packages(),
            category = category(packageName),
            smsRoleHolders = smsRoleHolders(),
        )
        if (result is NotificationAllowList.AddResult.Added) {
            prefs.edit { putStringSet(KEY_PACKAGES, packages() + packageName) }
        }
        return result
    }

    /** Takes [packageName] off the list. Never a card, never held: this only
     * lets Jarvis see less, the same "remove is instant" rule every other
     * allow-list in this app already follows (folders, news feeds). */
    fun remove(packageName: String) {
        prefs.edit { putStringSet(KEY_PACKAGES, packages() - packageName) }
    }

    /**
     * Every app installed on this phone with an ordinary home-screen icon,
     * as (package name, the label the owner would recognise) - for the
     * "add an app" picker. Apps already on the list, and this app itself,
     * are left out; nothing here is a network call or a Play Store
     * lookup, only [PackageManager], already on the phone.
     *
     * NEEDS the `<queries>` element in `AndroidManifest.xml` (a launcher
     * `MAIN`/`LAUNCHER` intent filter): without it, Android 11+'s package
     * visibility rules would silently filter `getInstalledApplications`
     * down to almost nothing, and this picker would show few or none of
     * the apps actually on the phone - not a security gap, since the
     * owner would just see an empty-looking list rather than a wrong one,
     * but a real usability one, caught by re-reading Android's own
     * package-visibility documentation rather than assumed away.
     *
     * A REAL, SAID-PLAINLY LIMIT even with that element: an app with no
     * launcher icon at all (a pure background component) will not appear
     * here, so it cannot be added from this picker - rare in practice,
     * since an app posting a notification a person would want to read
     * almost always has an icon too.
     */
    fun installedApps(): List<InstalledApp> {
        val pm = context.packageManager
        val already = packages()
        return runCatching {
            pm.getInstalledApplications(PackageManager.GET_META_DATA)
        }.getOrDefault(emptyList())
            .asSequence()
            .filter { it.packageName != context.packageName }
            .filter { it.packageName !in already }
            .map { InstalledApp(it.packageName, pm.getApplicationLabel(it).toString()) }
            .sortedBy { it.label.lowercase() }
            .toList()
    }

    data class InstalledApp(val packageName: String, val label: String)

    private companion object {
        const val PREFS = "jarvis_phone_notifications"
        const val KEY_PACKAGES = "allowed_packages"
    }
}
