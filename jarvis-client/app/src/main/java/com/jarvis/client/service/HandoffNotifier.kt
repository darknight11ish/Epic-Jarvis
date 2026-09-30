package com.jarvis.client.service

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.jarvis.client.MainActivity
import com.jarvis.client.R
import com.jarvis.client.net.Handoff

/**
 * "Gemini needs you" - a chatbot website or a support chat paused at a
 * captcha, a sign-in page or an "unusual activity" page (the owner's
 * decision of 2026-09-28; [Handoff]).
 *
 * An ALERT, not a status line: its own channel at high importance, because
 * the conversation waits for the owner. What it says:
 *  - the site and the reason only ("Gemini needs you" / "Jarvis paused: a
 *    captcha..."), never a word from the page and never the goal;
 *  - while App lock or "Hide memory lists and chat history" is on, not even
 *    that: "A website Jarvis is using needs you" ([Handoff.alert]), and the
 *    lock-screen version is the same generic line.
 * It ALWAYS stays on this phone (`setLocalOnly(true)`): a hand-off is only
 * ever solved here or on the PC, never on a watch.
 *
 * Its one button is "Solve it here": it opens the app on the Solve it here
 * screen (behind the app lock, as ever). Nothing here starts the hand-off,
 * takes a picture or passes on a tap - the screen does, once the owner is
 * looking at it.
 *
 * Its own id, 0x3202: next to [ChatbotNotifier]'s 0x3200 and 0x3201, below
 * [ApprovalNotifier]'s range.
 */
object HandoffNotifier {
    private const val TAG = "HandoffNotifier"
    const val NOTIFICATION_ID = NotificationIds.HANDOFF
    const val CHANNEL_ID = "jarvis_needs_you"

    private fun allowed(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED

    private fun ensureChannel(context: Context) {
        val manager = ContextCompat.getSystemService(context, NotificationManager::class.java) ?: return
        runCatching {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "A website needs you", NotificationManager.IMPORTANCE_HIGH)
                    .apply {
                        description = "When a chatbot or support website Jarvis is using shows a captcha " +
                            "or a sign-in page, and Jarvis waits for you."
                        setShowBadge(true)
                    },
            )
        }
    }

    fun post(context: Context, o: Handoff.Offer, locked: Boolean) {
        if (!allowed(context)) return
        ensureChannel(context)
        val (title, text) = Handoff.alert(o, locked)
        val open = PendingIntent.getActivity(
            context,
            NOTIFICATION_ID,
            Intent(context, MainActivity::class.java)
                .setAction(MainActivity.ACTION_OPEN_HANDOFF)
                .putExtra(
                    com.jarvis.client.InternalLaunch.EXTRA_PROOF,
                    com.jarvis.client.InternalLaunch.token(context),
                )
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val n = NotificationCompat.Builder(context, CHANNEL_ID)
            // Always on this phone only: a captcha is solved here or on the PC.
            .setLocalOnly(true)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setOnlyAlertOnce(true)
            .setAutoCancel(true)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setPublicVersion(publicVersion(context))
            .setContentIntent(open)
            .addAction(0, Handoff.HERE_BUTTON, open)
            .build()
        runCatching { NotificationManagerCompat.from(context).notify(NOTIFICATION_ID, n) }
            .onFailure { Log.w(TAG, "could not post the alert", it) }
    }

    fun cancel(context: Context) {
        runCatching { NotificationManagerCompat.from(context).cancel(NOTIFICATION_ID) }
    }

    /** What a locked phone shows: nothing about the site. */
    private fun publicVersion(context: Context): Notification =
        NotificationCompat.Builder(context, CHANNEL_ID)
            .setLocalOnly(true)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(context.getString(R.string.app_name))
            .setContentText(Handoff.ALERT_LOCKED)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .build()
}
