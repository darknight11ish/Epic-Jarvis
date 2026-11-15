package com.jarvis.client.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.MainActivity
import com.jarvis.client.R
import com.jarvis.client.voice.LiveRules

/**
 * Keeps a read-aloud going while the app is not in front of the owner.
 *
 * THE OWNER'S ASK (2026-11-15): *"when i move out of the jarvis android app on
 * my phone (whether thats just putting it in picture in picture mode or moving
 * to a different app or homescreen, it should continue the read outloud if
 * thats what i selected on the jarvis app. right now it stops it"* - and, asked
 * what should happen when the screen locks, he chose **"keep going even when
 * locked"**.
 *
 * WHY A SERVICE. Android freezes a backgrounded app's process once it is
 * cached, which stops audio mid-sentence; a foreground service with the
 * `mediaPlayback` type is Android's own way of saying "this app is playing
 * something", and it is what keeps the voice going through HOME, another app
 * and the lock screen. The type is `mediaPlayback` rather than `specialUse`
 * because the app really is playing audio - mislabelling it would be a lie to
 * the operating system.
 *
 * WHAT IT IS NOT. It plays nothing itself: [JarvisRuntime] owns the audio and
 * the sentences. This service holds the process awake for as long as that read
 * lasts, and carries the one notification that says so, with Stop.
 *
 * THE STOP CONTROL IS THE POINT. A read that carries on out of sight must be
 * stoppable without finding the app again: this notification's Stop, the app's
 * own Stop talking button, "stop" said to Jarvis, and Stop everything all end
 * it through the same door ([JarvisRuntime.stopReadingAloud]).
 *
 * STARTED ONLY BY A READ. `START_NOT_STICKY`, never at boot, and it stops
 * itself the moment the read ends - there is no state in which this service
 * runs with nothing to play.
 */
class ReadAloudService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            // The same door as the app's own Stop button: one place ends a read.
            JarvisRuntime.stopReadingAloud()
            stopSelf()
            return START_NOT_STICKY
        }
        post()
        return START_NOT_STICKY
    }

    /** Foreground, or nothing: a service that failed to go foreground is stopped. */
    private fun post() {
        ensureChannel(this)
        val open = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val stop = PendingIntent.getService(
            this,
            1,
            Intent(this, ReadAloudService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(getString(R.string.read_aloud_reading))
            .setContentText(getString(R.string.read_aloud_notice))
            .setContentIntent(open)
            .addAction(0, LiveRules.STOP_TALKING, stop)
            .setOngoing(true)
            .setSilent(true)
            // Nothing about this line leaves the phone: it is the shade's own
            // notice, and the test that watches every builder demands this be
            // said in so many words.
            .setLocalOnly(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_TRANSPORT)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .build()
        try {
            ServiceCompat.startForeground(
                this,
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK,
            )
        } catch (e: Exception) {
            // Android may refuse a foreground service (a restricted background
            // start, or the owner switched this channel off). The read still
            // plays while the process lives; it is simply not protected after
            // that, so say so and stop rather than pretend otherwise.
            Log.w(TAG, "startForeground refused; the read is not kept alive", e)
            stopSelf()
        }
    }

    companion object {
        private const val TAG = "ReadAloudService"
        const val CHANNEL_ID = "jarvis_read_aloud"
        private const val NOTIFICATION_ID = NotificationIds.READ_ALOUD
        const val ACTION_STOP = "com.jarvis.client.READ_ALOUD_STOP"

        /** Start keeping a read alive. Never throws: audio is not worth a crash. */
        fun start(context: Context?) {
            val app = context?.applicationContext ?: return
            runCatching {
                ContextCompat.startForegroundService(app, Intent(app, ReadAloudService::class.java))
            }
        }

        /** Stop keeping it alive. Called when the read ends, stops, or fails. */
        fun stop(context: Context?) {
            val app = context?.applicationContext ?: return
            runCatching { app.stopService(Intent(app, ReadAloudService::class.java)) }
        }

        fun ensureChannel(context: Context) {
            val manager = context.getSystemService(NotificationManager::class.java) ?: return
            if (manager.getNotificationChannel(CHANNEL_ID) != null) return
            val channel = NotificationChannel(
                CHANNEL_ID,
                context.getString(R.string.read_aloud_channel),
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = context.getString(R.string.read_aloud_channel_why)
                setSound(null, null)
                enableVibration(false)
                setShowBadge(false)
            }
            manager.createNotificationChannel(channel)
        }
    }
}
