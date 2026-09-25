package com.jarvis.client.service

import android.Manifest
import android.app.Notification
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

/**
 * A timer, an alarm or a reminder that went off on the PC, shown on the phone
 * (the owner's decisions of 2026-09-25; docs/JARVIS-API.md section 21).
 *
 * THE PC IS THE CLOCK. This is called when the `schedule` event says a job
 * went off - so only while the phone is connected to the PC
 * ([com.jarvis.client.JarvisRuntime.onScheduleEvent]). Nothing here sets an
 * alarm on the phone, and no exact-alarm permission is asked for.
 *
 * On the existing approval channel (the one that makes a sound), with the
 * same lock-screen rule an approval has: the locked screen shows only what
 * KIND of thing is due ("Jarvis: a reminder is due."), never its words; the
 * words need the phone unlocked. While App lock or "Hide memory lists and
 * chat history" is on, the notification itself says only the kind, too -
 * the caller decides that ([com.jarvis.client.net.Schedule.notification]).
 *
 * Ids from 0x3100 to 0x31FF, round and round: below [ApprovalNotifier]'s
 * range, whose restore() cancels anything of ours it finds at or above
 * 0x4B00, and below the two services' own.
 */
object ScheduleNotifier {
    private const val TAG = "ScheduleNotifier"
    private const val FIRST_ID = 0x3100
    private const val SLOTS = 0x100

    private val assigned = LinkedHashMap<String, Int>()
    private var next = 0

    @Synchronized
    private fun idFor(jobId: String): Int {
        assigned[jobId]?.let { return it }
        val id = FIRST_ID + (next++ % SLOTS)
        assigned[jobId] = id
        if (assigned.size > SLOTS) assigned.remove(assigned.keys.first())
        return id
    }

    private fun allowed(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED

    /**
     * Shows one job that went off. [title] and [text] come from
     * [com.jarvis.client.net.Schedule.notification]; [lockScreen] is the
     * kind's lock-screen words, the only thing a locked phone shows.
     */
    fun post(context: Context, jobId: String, kind: String, title: String, text: String, lockScreen: String) {
        if (!allowed(context)) {
            Log.w(TAG, "POST_NOTIFICATIONS is not granted, so a $kind that went off is not shown")
            return
        }
        val notificationId = idFor(jobId)
        val n = NotificationCompat.Builder(context, ApprovalNotifier.CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setCategory(if (kind == "alarm") NotificationCompat.CATEGORY_ALARM else NotificationCompat.CATEGORY_REMINDER)
            // Never a full-screen intent: this is a notification, not the
            // phone's own alarm clock.
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setPublicVersion(locked(context, lockScreen))
            .setAutoCancel(true)
            .setContentIntent(open(context, notificationId))
            .build()
        runCatching { NotificationManagerCompat.from(context).notify(notificationId, n) }
            .onFailure { Log.w(TAG, "could not post a $kind that went off", it) }
    }

    private fun locked(context: Context, lockScreen: String): Notification =
        NotificationCompat.Builder(context, ApprovalNotifier.CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(context.getString(R.string.app_name))
            .setContentText(lockScreen)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .build()

    private fun open(context: Context, requestCode: Int): PendingIntent {
        val intent = Intent(context, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        return PendingIntent.getActivity(
            context,
            requestCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }
}
