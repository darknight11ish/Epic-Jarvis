package com.jarvis.client.service

import android.Manifest
import android.app.Notification
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.MainActivity
import com.jarvis.client.R
import com.jarvis.client.net.Chatbot
import com.jarvis.client.net.Support

/**
 * The ongoing notification while Jarvis talks to a chatbot for the owner
 * ("Talking to Gemini, 3 of 5", with Stop) - [com.jarvis.client.net.Chatbot],
 * kept in step by [JarvisRuntime.watchChatbot].
 *
 * Quiet: the link's own low-importance channel, no sound, no heads-up - it
 * is a status line, not an alert (the approval card itself arrives the usual
 * way, through [ApprovalNotifier]). It carries only the chatbot's name and
 * the counts, never the goal or a word of the conversation, and a locked
 * phone shows only [Chatbot.NOTIFY_LOCKED].
 *
 * Its one button is Stop - it goes to [EventService] (ACTION_CHATBOT_STOP),
 * which sends ONE stop for this conversation. Stopping is never held on a
 * stale link and never a card: it only makes Jarvis do less. Nothing here
 * can approve, resume or start anything.
 *
 * Its own id (NotificationIds.CHATBOT, 0x3200): below [ApprovalNotifier]'s range (whose restore()
 * cancels anything of ours at or above 0x4B00), apart from
 * [ScheduleNotifier]'s 0x3100 and the services' own.
 */
object ChatbotNotifier {
    private const val TAG = "ChatbotNotifier"
    const val NOTIFICATION_ID = NotificationIds.CHATBOT

    /** A customer-support chat's own line, beside a chatbot conversation's. */
    const val SUPPORT_NOTIFICATION_ID = NotificationIds.SUPPORT_CHAT

    /** The conversation (or comparison) id a Stop carries. */
    const val EXTRA_SESSION_ID = "com.jarvis.client.extra.CHATBOT_SESSION"

    private fun allowed(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED

    /** Shows (or updates) the line for [s]; takes it away once [s] has ended. */
    fun post(context: Context, s: Chatbot.Session) = show(context, Chatbot.talkingLine(s), s.id)

    /**
     * The same line for "Ask several and compare" ("Comparing 3 chatbots:
     * asking ChatGPT, 2 of 3"). Its Stop carries the comparison's id, so it
     * stops the whole comparison.
     */
    fun postCompare(context: Context, c: Chatbot.Compare) =
        show(context, Chatbot.compareTalkingLine(c), c.id)

    /**
     * A customer-support chat ("Chat with Groupon: offer waiting"). Its Stop
     * carries the support chat's id. The line never carries the goal, a
     * detail or a word of the chat; a locked phone shows [Support.NOTIFY_LOCKED].
     */
    fun postSupport(context: Context, c: Support.Chat) =
        show(context, Support.talkingLine(c), c.id, SUPPORT_NOTIFICATION_ID, Support.TITLE,
            Support.NOTIFY_LOCKED)

    fun cancelSupport(context: Context) {
        runCatching { NotificationManagerCompat.from(context).cancel(SUPPORT_NOTIFICATION_ID) }
    }

    private fun show(
        context: Context,
        line: String,
        stopId: String,
        id: Int = NOTIFICATION_ID,
        title: String = Chatbot.TITLE,
        lockedWords: String = Chatbot.NOTIFY_LOCKED,
    ) {
        if (line.isEmpty()) {
            runCatching { NotificationManagerCompat.from(context).cancel(id) }
            return
        }
        if (!allowed(context)) return
        val n = NotificationCompat.Builder(context, EventService.CHANNEL_ID)
            // Stays on this phone unless the owner turned on "Show
            // notifications on a compatible watch" (Brain, off by default).
            .setLocalOnly(!JarvisRuntime.watchNotificationsAllowed())
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(line)
            .setContentText(title)
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setPublicVersion(locked(context, lockedWords))
            .setContentIntent(open(context))
            .addAction(0, Chatbot.STOP, stopIntent(context, stopId))
            .build()
        runCatching { NotificationManagerCompat.from(context).notify(id, n) }
            .onFailure { Log.w(TAG, "could not post the chatbot line", it) }
    }

    fun cancel(context: Context) {
        runCatching { NotificationManagerCompat.from(context).cancel(NOTIFICATION_ID) }
    }

    private fun locked(context: Context, words: String): Notification =
        NotificationCompat.Builder(context, EventService.CHANNEL_ID)
            .setLocalOnly(!JarvisRuntime.watchNotificationsAllowed())
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(context.getString(R.string.app_name))
            .setContentText(words)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .build()

    /** Stop: to [EventService], which sends ONE stop for this conversation - nothing else. */
    private fun stopIntent(context: Context, id: String): PendingIntent =
        PendingIntent.getService(
            context,
            0,
            Intent(context, EventService::class.java)
                .setAction(EventService.ACTION_CHATBOT_STOP)
                .setData(Uri.fromParts("jarvis-chatbot", id, null))
                .putExtra(EXTRA_SESSION_ID, id),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

    private fun open(context: Context): PendingIntent =
        PendingIntent.getActivity(
            context,
            NOTIFICATION_ID,
            Intent(context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
}
