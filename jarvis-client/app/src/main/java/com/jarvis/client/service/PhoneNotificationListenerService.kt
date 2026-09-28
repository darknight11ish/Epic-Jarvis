package com.jarvis.client.service

import android.app.Notification
import android.provider.Telephony
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.data.CapturedNotification
import com.jarvis.client.data.CapturedNotifications
import com.jarvis.client.data.NotificationAllowList
import com.jarvis.client.data.NotificationAllowListStore
import com.jarvis.client.data.NotificationRedactor

/**
 * The actual `NotificationListenerService` for "reading phone
 * notifications" (CLAUDE.md, 2026-09-26; docs/JARVIS-API.md §61). Bound by
 * the system, once the owner grants "Notification access" in Android's own
 * Settings (`Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS`) - a special,
 * OS-level access, NOT a runtime permission dialog, because it is unusually
 * broad: once granted, this class is offered EVERY notification posted on
 * the phone, by every app, whether or not Jarvis's own switch is on.
 *
 * FOUR GATES, ALL CHECKED BEFORE A SINGLE BYTE IS STORED, in
 * `onNotificationPosted`'s own order (cheapest first, so an app that fails
 * an earlier one never has its text even read out of the notification):
 *   1. [JarvisRuntime.phoneNotificationsAllowed] - the PC-decided master
 *      switch (off by default; ON needs one approval card). OFF: nothing
 *      below this line ever runs for that notification.
 *   2. [isSmsLike] - dropped outright even if [NotificationAllowListStore]
 *      somehow held the package (it refuses to add one in the first place
 *      - this is defence in depth, not the primary gate). CLAUDE.md:
 *      "Never text messages (SMS)... even if the owner tries to add the
 *      Messages app".
 *   3. [NotificationAllowListStore] - only an app the owner has explicitly
 *      added (empty by default) is kept at all; every other app's
 *      notification is dropped here, unread by anything past this line.
 *   4. [NotificationRedactor] - always applied to the title and the text,
 *      the very last step before [CapturedNotifications.add], blanking
 *      anything that looks like a one-time code.
 *
 * NEVER REPLIES, DISMISSES, OR ACTS ON A NOTIFICATION. This class does not
 * override `onNotificationRemoved` for any write purpose, holds no
 * `RankingMap` state, and calls nothing on the system's own
 * `NotificationManager` - it only reads what was posted, and only stores a
 * redacted copy locally. Nothing here calls a Jarvis tool, saves a fact, or
 * reaches the PC on its own; the only door back to a chat is the owner's
 * own "Attach recent notifications" ([CapturedNotifications.sharedText]).
 */
class PhoneNotificationListenerService : NotificationListenerService() {

    private val allowList by lazy { NotificationAllowListStore(applicationContext) }
    private val store by lazy { CapturedNotifications(applicationContext) }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        val notification = sbn ?: return
        if (!JarvisRuntime.phoneNotificationsAllowed()) return
        val pkg = notification.packageName ?: return
        if (pkg == packageName) return // never Jarvis's own notifications
        if (isSmsLike(notification)) return
        if (!allowList.contains(pkg)) return

        val extras = notification.notification?.extras ?: return
        val rawTitle = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
        val rawText = bestText(extras)
        if (rawTitle.isBlank() && rawText.isBlank()) return

        val (title, text) = NotificationRedactor.redactBoth(rawTitle, rawText)
        store.add(
            CapturedNotification(
                id = "${pkg}:${notification.key}:${notification.postTime}",
                packageName = pkg,
                appLabel = appLabel(pkg),
                title = title,
                text = text,
                postedAtMs = notification.postTime,
            ),
        )
    }

    // No onNotificationRemoved override: removals are not read, kept or
    // acted on - there is nothing this service does with one.

    /**
     * The longest of the shapes a notification's text usually comes in -
     * `EXTRA_BIG_TEXT` (an expanded notification) falls back to
     * `EXTRA_TEXT`, then the lines of `EXTRA_TEXT_LINES` (an
     * `InboxStyle` notification) joined together. Never `EXTRA_SUB_TEXT`
     * or `EXTRA_SUMMARY_TEXT`, which are usually just the app's own name a
     * second time.
     */
    private fun bestText(extras: android.os.Bundle): String {
        extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString()?.let { if (it.isNotBlank()) return it }
        extras.getCharSequence(Notification.EXTRA_TEXT)?.toString()?.let { if (it.isNotBlank()) return it }
        val lines = extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES)
        return lines?.joinToString("\n") { it.toString() }.orEmpty()
    }

    private fun appLabel(pkg: String): String = runCatching {
        val pm = packageManager
        pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString()
    }.getOrDefault(pkg)

    /**
     * Defence in depth for CLAUDE.md's hard "never text messages (SMS)"
     * rule, on top of [NotificationAllowListStore] refusing to add an
     * SMS/Messages app in the first place: even a notification whose
     * PACKAGE the owner somehow got onto the list (a future Android
     * version, a bug, a role change after the app was added) is dropped
     * here if Android itself marks it as a message from the phone's own
     * default SMS app.
     */
    private fun isSmsLike(sbn: StatusBarNotification): Boolean {
        val pkg = sbn.packageName ?: return false
        val smsHolders = smsRoleHolders()
        return NotificationAllowList.isSmsPackage(pkg, smsHolders)
    }

    /** Same signal [NotificationAllowListStore] checks before adding a
     * package to the list in the first place - read again here so a
     * package that reached the list some other way (a future Android
     * version, a bug) still cannot store an SMS notification. See that
     * class's own doc comment for why this is `Telephony.Sms
     * .getDefaultSmsPackage`, not `RoleManager.getRoleHolders` (the
     * latter is hidden from the public SDK stub this app actually
     * compiles against). */
    private fun smsRoleHolders(): Set<String> = runCatching {
        Telephony.Sms.getDefaultSmsPackage(this)?.let { setOf(it) } ?: emptySet()
    }.getOrDefault(emptySet())
}
