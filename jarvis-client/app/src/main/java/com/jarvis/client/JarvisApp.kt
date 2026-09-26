package com.jarvis.client

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.media.AudioAttributes
import android.media.RingtoneManager
import androidx.core.content.ContextCompat
import com.jarvis.client.platform.CrashLog
import com.jarvis.client.platform.GpuProbe
import com.jarvis.client.service.ApprovalNotifier
import com.jarvis.client.service.EventService
import com.jarvis.client.service.ScheduleNotifier

class JarvisApp : Application() {
    override fun onCreate() {
        super.onCreate()

        // First, before anything that could fail. A startup crash in a
        // sideloaded app otherwise leaves nothing behind but "it closed".
        CrashLog.install(this) {
            runCatching {
                if (JarvisRuntime.isInitialized) JarvisRuntime.tokens.token() else null
            }.getOrNull()
        }

        // Asks the graphics driver what it is, on a background thread, so a
        // software renderer (an emulator) has the face at Low before it first
        // draws. Once per process; see GpuProbe.
        GpuProbe.start()

        val manager = ContextCompat.getSystemService(this, NotificationManager::class.java)
            ?: return

        manager.createNotificationChannel(
            NotificationChannel(
                EventService.CHANNEL_ID,
                getString(R.string.channel_link_name),
                // IMPORTANCE_LOW: the link notification is a status line, not an
                // alert. It is ongoing and permanent, so anything higher would
                // make the app a constant interruption about nothing.
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = getString(R.string.channel_link_desc)
                setShowBadge(false)
            },
        )

        // Separate channel, and separately importance-controlled, so the link
        // line can stay silent for ever while a decision still makes a sound.
        // One channel could not do both, which is how the app ended up
        // announcing nothing at all.
        manager.createNotificationChannel(
            NotificationChannel(
                ApprovalNotifier.CHANNEL_ID,
                getString(R.string.channel_approval_name),
                // HIGH, not MAX: it makes a sound and heads-up, it does not take
                // over the screen. Nothing Jarvis asks for is worth a full-screen
                // intent, and an item that claims to be urgent is exactly the one
                // that should not be able to demand the whole display.
                NotificationManager.IMPORTANCE_HIGH,
            ).apply {
                description = getString(R.string.channel_approval_desc)
                setShowBadge(true)
                enableVibration(true)
            },
        )

        // A second approval channel, because on Android 8 and later whether a
        // notification interrupts is a property of the CHANNEL, not of the
        // notification. `setPriority` is only a sorting hint inside a channel.
        // So "heavy interrupts, normal waits to be found" cannot be a flag on
        // the post; it has to be two channels, and the routing happens in
        // ApprovalNotifier via PendingItem.shouldInterrupt.
        //
        // LOW rather than DEFAULT: DEFAULT still makes a sound, and the whole
        // point of this channel is the approvals that should not. Nothing is
        // lost by being silent - the foreground service's own status line
        // already shows a running count of what is waiting, so a quiet
        // approval is visible in two places without having made a noise.
        //
        // A NEW id rather than lowering the existing channel, because an
        // app cannot lower a channel's importance once it has been created -
        // that belongs to the person, not the app - so a rename in place would
        // have silently kept HIGH for everyone who already has the app.
        manager.createNotificationChannel(
            NotificationChannel(
                ApprovalNotifier.QUIET_CHANNEL_ID,
                getString(R.string.channel_approval_quiet_name),
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = getString(R.string.channel_approval_quiet_desc)
                setShowBadge(true)
            },
        )

        // Alarms and urgent "tell me when"s (2026-09-25: "alarms that keep
        // ringing"; ScheduleNotifier.postRinging). Its own channel because the
        // sound belongs to the channel: the ALARM sound, with alarm usage, so
        // Do Not Disturb treats it as an alarm (let through when the phone
        // allows alarms - the default) rather than as a message. Nothing here
        // asks to override Do Not Disturb itself. Still no full-screen intent.
        manager.createNotificationChannel(
            NotificationChannel(
                ScheduleNotifier.ALARM_CHANNEL_ID,
                getString(R.string.channel_alarm_name),
                NotificationManager.IMPORTANCE_HIGH,
            ).apply {
                description = getString(R.string.channel_alarm_desc)
                setShowBadge(true)
                enableVibration(true)
                vibrationPattern = longArrayOf(0, 600, 400, 600)
                val sound = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
                    ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
                setSound(
                    sound,
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ALARM)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .build(),
                )
            },
        )
    }
}
