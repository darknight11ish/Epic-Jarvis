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
 * SNOOZE (2026-09-25): a timer, alarm or reminder carries one action,
 * "Snooze 10 minutes" ([com.jarvis.client.net.Schedule.SNOOZE]) - never
 * Approve, never "all". It goes to [EventService] (ACTION_SNOOZE), which
 * waits for the link like a notification's Deny and then sends ONE snooze,
 * held on a stale link ([com.jarvis.client.JarvisRuntime.scheduleAct]). A
 * snooze is not an approval: it only sets the same thing to go off once
 * more, later, on the PC, and needs no card. The locked screen's version
 * ([locked]) has no action at all.
 *
 * ONE notification id, 0x3100, told apart by a TAG - the job's key (its id,
 * or `id#match@...` for a "tell me when" match). Android keys a
 * notification by (tag, id), so each job has its own, the same after the
 * app process restarts: a new alarm never replaces one still showing, and a
 * Snooze or Stop pressed on a notification from before a restart still
 * finds its own (bug audit 2026-09-26, #3 - the numbers used to be handed
 * out in memory and started again from the first after a restart). Below
 * [ApprovalNotifier]'s range, whose restore() cancels anything of ours it
 * finds at or above 0x4B00, and below the two services' own. Each
 * notification's buttons carry the key as their intent's data, so two
 * notifications' PendingIntents are never taken for the same one.
 */
object ScheduleNotifier {
    private const val TAG = "ScheduleNotifier"

    /** The one id every schedule notification has; its tag tells them apart. */
    const val NOTIFICATION_ID = 0x3100

    /** The kinds that carry a Snooze (jarvis_schedule.SNOOZABLE). */
    private val SNOOZABLE = com.jarvis.client.net.Schedule.SNOOZABLE

    /** The job id a Snooze action carries. */
    const val EXTRA_JOB_ID = "com.jarvis.client.extra.JOB_ID"

    /** The notification's tag a Stop carries. */
    const val EXTRA_TAG = "com.jarvis.client.extra.NOTIFICATION_TAG"

    /**
     * Takes one job's "went off" notification away: after a Snooze went
     * through, and when the PC says the job changed - snoozed, deleted or
     * done somewhere else (bug audit #1). A ringing one stops with it.
     */
    fun cancel(context: Context, jobId: String) {
        runCatching { NotificationManagerCompat.from(context).cancel(jobId, NOTIFICATION_ID) }
    }

    /** Distinct per key, so no two notifications share a PendingIntent. */
    private fun keyData(key: String): Uri = Uri.fromParts("jarvis-schedule", key, null)

    private fun allowed(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED

    /**
     * Shows one job that went off. [title] and [text] come from
     * [com.jarvis.client.net.Schedule.notification]; [lockScreen] is the
     * kind's lock-screen words, the only thing a locked phone shows.
     */
    fun post(
        context: Context,
        jobId: String,
        kind: String,
        title: String,
        text: String,
        lockScreen: String,
        /** A morning briefing: the tap opens Mind, where the briefing is. */
        openBriefing: Boolean = false,
        /**
         * Keep ringing until seen: an alarm, or an urgent "tell me when"
         * ([com.jarvis.client.net.Schedule.rings]). Then it goes on the alarm
         * channel ([ALARM_CHANNEL_ID]), its sound and vibration repeat
         * (`FLAG_INSISTENT`) until the notification is opened, pulled down,
         * tapped, stopped or swiped away. It is marked ongoing, which keeps it
         * from being swiped away on Android 13; Android 14 and later let any
         * such notification be swiped away (which also stops it).
         */
        ring: Boolean = false,
        /** Several notices for one job ("every time"): one each, not one replacing the last. */
        key: String = jobId,
        /**
         * Heard more than ten minutes after it went off (the owner's decision
         * of 2026-09-26): no sound, no ringing and no Snooze - a notice of
         * when it was missed ([com.jarvis.client.net.Schedule.missedWords]).
         */
        quiet: Boolean = false,
    ) {
        if (!allowed(context)) {
            Log.w(TAG, "POST_NOTIFICATIONS is not granted, so a $kind that went off is not shown")
            return
        }
        if (ring && !quiet) {
            postRinging(context, key, jobId, kind, title, text, lockScreen, openBriefing)
            return
        }
        val n = NotificationCompat.Builder(context, ApprovalNotifier.CHANNEL_ID)
            // Never copied to a paired watch or other device (Android bridges
            // notifications by default): what Jarvis says stays on this phone.
            .setLocalOnly(true)
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
            .setSilent(quiet)
            .setContentIntent(open(context, key, openBriefing))
            .apply {
                if (kind in SNOOZABLE && !openBriefing && !quiet) {
                    addAction(
                        R.drawable.ic_notification,
                        com.jarvis.client.net.Schedule.SNOOZE,
                        snoozeIntent(context, jobId, key),
                    )
                }
            }
            .build()
        runCatching { NotificationManagerCompat.from(context).notify(key, NOTIFICATION_ID, n) }
            .onFailure { Log.w(TAG, "could not post a $kind that went off", it) }
    }

    /**
     * The one that keeps ringing. Still never a full-screen intent, and still
     * the lock-screen rule: a locked phone shows only [lockScreen]. Its
     * button is Stop - it silences and removes this notification and does
     * nothing else - and, on an alarm going off, Snooze beside it (the same
     * one-off copy ten minutes later as on a quiet notification). Nothing
     * here can approve anything.
     *
     * Do Not Disturb: nothing here overrides it. The channel's sound is an
     * ALARM sound (`USAGE_ALARM`) and the notification is `CATEGORY_ALARM`,
     * and Android lets alarms through Do Not Disturb by default (Settings ->
     * Do Not Disturb -> Alarms), so it rings unless the owner turned that off.
     */
    private fun postRinging(
        context: Context,
        key: String,
        jobId: String,
        kind: String,
        title: String,
        text: String,
        lockScreen: String,
        openBriefing: Boolean,
    ) {
        val n = NotificationCompat.Builder(context, ALARM_CHANNEL_ID)
            // Never copied to a paired watch or other device (Android bridges
            // notifications by default): what Jarvis says stays on this phone.
            .setLocalOnly(true)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setPublicVersion(locked(context, lockScreen))
            .setOngoing(true)
            .setAutoCancel(true)
            .setContentIntent(open(context, key, openBriefing))
            .addAction(0, STOP, stopIntent(context, key))
            .apply {
                if (kind in SNOOZABLE && !openBriefing) {
                    addAction(
                        R.drawable.ic_notification,
                        com.jarvis.client.net.Schedule.SNOOZE,
                        snoozeIntent(context, jobId, key),
                    )
                }
            }
            .build()
        n.flags = n.flags or Notification.FLAG_INSISTENT
        runCatching { NotificationManagerCompat.from(context).notify(key, NOTIFICATION_ID, n) }
            .onFailure { Log.w(TAG, "could not post a ringing $kind", it) }
    }

    /** Stop: to [EventService], which cancels this one notification - nothing else. */
    private fun stopIntent(context: Context, key: String): PendingIntent =
        PendingIntent.getService(
            context,
            0,
            Intent(context, EventService::class.java)
                .setAction(EventService.ACTION_STOP_RINGING)
                .setData(keyData(key))
                .putExtra(EXTRA_TAG, key),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

    /** Stops one ringing notification (the Stop button): the one with this tag, nothing else. */
    fun stopRinging(context: Context, tag: String?) {
        if (tag.isNullOrEmpty()) return
        runCatching { NotificationManagerCompat.from(context).cancel(tag, NOTIFICATION_ID) }
    }

    /** The alarm channel (JarvisApp creates it): alarms and urgent "tell me when"s. */
    const val ALARM_CHANNEL_ID = "jarvis_alarm"
    const val STOP = "Stop"

    private fun locked(context: Context, lockScreen: String): Notification =
        NotificationCompat.Builder(context, ApprovalNotifier.CHANNEL_ID)
            // Never copied to a paired watch or other device (Android bridges
            // notifications by default): what Jarvis says stays on this phone.
            .setLocalOnly(true)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(context.getString(R.string.app_name))
            .setContentText(lockScreen)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .build()

    private fun snoozeIntent(context: Context, jobId: String, key: String): PendingIntent {
        val intent = Intent(context, EventService::class.java)
            .setAction(EventService.ACTION_SNOOZE)
            .setData(keyData(key))
            .putExtra(EXTRA_JOB_ID, jobId)
        return PendingIntent.getService(
            context,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    private fun open(context: Context, key: String, openBriefing: Boolean): PendingIntent {
        val intent = Intent(context, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        if (openBriefing) intent.action = MainActivity.ACTION_OPEN_BRIEFING
        return PendingIntent.getActivity(
            context,
            key.hashCode(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }
}
