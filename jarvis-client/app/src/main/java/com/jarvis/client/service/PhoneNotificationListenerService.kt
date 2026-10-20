package com.jarvis.client.service

import android.app.Notification
import android.provider.Telephony
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.data.CapturedNotification
import com.jarvis.client.data.CapturedNotifications
import com.jarvis.client.data.NotificationAllowListStore
import com.jarvis.client.data.NotificationGate

/**
 * The actual `NotificationListenerService` for "reading phone
 * notifications" (CLAUDE.md, 2026-09-26; docs/JARVIS-API.md §61). Bound by
 * the system, once the owner grants "Notification access" in Android's own
 * Settings (`Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS`) - a special,
 * OS-level access, NOT a runtime permission dialog, because it is unusually
 * broad: once granted, this class is offered EVERY notification posted on
 * the phone, by every app, whether or not Jarvis's own switch is on.
 *
 * SIX GATES, ALL CHECKED BEFORE A SINGLE BYTE IS STORED, in
 * `onNotificationPosted`'s own order (cheapest first, so an app that fails
 * an earlier one never has its text even read out of the notification):
 *   1. [JarvisRuntime.phoneNotificationsAllowed] - the PC-decided master
 *      switch (off by default; ON needs one approval card). OFF: nothing
 *      below this line ever runs for that notification.
 *   2. [NotificationGate.isSecret] - an Android "secret" notification
 *      (`VISIBILITY_SECRET`) is never read or kept, whatever app posted it
 *      (2026-10-20 audit, Area 10A).
 *   3. SMS/Messages - dropped outright even if [NotificationAllowListStore]
 *      somehow held the package (it refuses to add one in the first place
 *      - this is defence in depth, not the primary gate). CLAUDE.md:
 *      "Never text messages (SMS)... even if the owner tries to add the
 *      Messages app". MMS arrives through the same default-SMS app, so the
 *      same answer covers it.
 *   4. A banking/brokerage/payment package - refused whole even if it somehow
 *      reached the allow-list (2026-10-20 audit, Area 10A); adding one is
 *      already refused by [NotificationAllowListStore].
 *   5. [NotificationAllowListStore] - only an app the owner has explicitly
 *      added (empty by default) is kept at all; every other app's
 *      notification is dropped here, unread by anything past this line.
 *   6. [NotificationGate.capture] - the title and the text are redacted
 *      TOGETHER (a 4-8 digit code with a trigger word in either field is
 *      masked) as the very last step before [CapturedNotifications.add].
 *      This is on-device, BEFORE anything could ever be sent to the PC.
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
        val posted = notification.notification ?: return
        // Android itself marks a notification secret: never read, never kept.
        if (NotificationGate.isSecret(posted.visibility)) return
        val smsHolders = smsRoleHolders()
        val category = appCategory(pkg)
        when (NotificationGate.packageSkip(pkg, smsHolders, category)) {
            NotificationGate.Skip.SMS -> return
            NotificationGate.Skip.BANKING -> return
            NotificationGate.Skip.SECRET, null -> Unit
        }
        if (!allowList.contains(pkg)) return

        val extras = posted.extras ?: return
        val rawTitle = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
        val rawText = bestText(extras)
        if (rawTitle.isBlank() && rawText.isBlank()) return

        val (title, text) = when (val verdict = NotificationGate.capture(
            pkg, posted.visibility, rawTitle, rawText, smsHolders, category,
        )) {
            is NotificationGate.Verdict.SkipIt -> return
            is NotificationGate.Verdict.Capture -> verdict.title to verdict.text
        }
        val row = CapturedNotification(
            id = "${pkg}:${notification.key}:${notification.postTime}",
            packageName = pkg,
            appLabel = appLabel(pkg),
            title = title,
            text = text,
            postedAtMs = notification.postTime,
        )
        // Gate 1 again, against the PC itself this time (at most every few
        // seconds): switched off on the PC means nothing is stored, even if
        // this phone's cached copy had not heard yet.
        JarvisRuntime.storeIfPhoneNotificationsStillOn { store.add(row) }
    }

    /**
     * Android can bind this service in a process nothing else has started
     * yet; without this the cached switch reads as off there and nothing is
     * ever captured (audit A2). Starting the runtime connects nothing.
     */
    override fun onListenerConnected() {
        super.onListenerConnected()
        runCatching { JarvisRuntime.initialize(applicationContext) }
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

    /** The app's declared store category, or null when it cannot be read. */
    private fun appCategory(pkg: String): Int? = runCatching {
        packageManager.getApplicationInfo(pkg, 0).category
    }.getOrNull()

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
