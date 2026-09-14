package com.jarvis.client.service

import android.app.Notification
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.jarvis.client.R

/**
 * Holds the SSE connection open. Step 0 only proves the service type is right;
 * the stream itself arrives in step 2.
 *
 * The type is specialUse rather than dataSync deliberately - see §3.1(2). The
 * six-hour dataSync budget on Android 15 is shared across every dataSync
 * service in the app and, when spent, produces a fatal RemoteServiceException
 * rather than a graceful stop. §11 makes "survives more than six hours without
 * the app being foregrounded" an acceptance criterion, which is precisely the
 * test dataSync fails.
 */
class EventService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        startInForeground()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        return START_STICKY
    }

    /**
     * Android 14+ requires onTimeout to be handled for timed foreground service
     * types. specialUse is not one of them, so neither of these should ever fire -
     * they are here so that if the type is ever changed back to a capped one, the
     * app stops itself instead of being killed with a RemoteServiceException.
     *
     * Both overloads, because they are not interchangeable: the one-argument form
     * is dispatched only for shortService, and the dataSync/mediaProcessing budget
     * on Android 15+ calls the two-argument one (API 35). With only the former
     * overridden, the safety net this comment describes was not armed on any device
     * this app runs on - the whole range is API 33-36.
     */
    override fun onTimeout(startId: Int) {
        Log.w(TAG, "foreground service timed out; the service type is capped after all")
        stopSelf()
    }

    override fun onTimeout(startId: Int, fgsType: Int) {
        if (Build.VERSION.SDK_INT >= 35) {
            Log.w(TAG, "foreground service type $fgsType timed out")
        }
        stopSelf()
    }

    private fun startInForeground() {
        val notification: Notification =
            NotificationCompat.Builder(this, CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_notification)
                .setContentTitle(getString(R.string.app_name))
                .setContentText("Not connected yet")
                .setOngoing(true)
                .setSilent(true)
                .setShowWhen(false)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
                .build()

        try {
            ServiceCompat.startForeground(
                this,
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE,
            )
        } catch (e: Exception) {
            // POST_NOTIFICATIONS denied does not stop the service, but other
            // failures do.
            //
            // The common case here is a sticky restart: the system reclaimed the
            // process, restarted the service with the app in the background, and a
            // background foreground-service start is not on the exemption list. That
            // used to end the link permanently with one logcat line. Record it where
            // the readiness screen can show it, so the phone can say the link is
            // down and why rather than appearing to work.
            Log.e(TAG, "startForeground refused", e)
            lastStartFailure = e.javaClass.simpleName
            stopSelf()
        }
    }

    companion object {
        private const val TAG = "JarvisEventService"

        /**
         * Set when the platform refused to let the service go foreground. Read by
         * the readiness screen; null while nothing has gone wrong.
         */
        @Volatile
        @JvmStatic
        var lastStartFailure: String? = null
        const val CHANNEL_ID = "jarvis_link"
        private const val NOTIFICATION_ID = 0x4A56
        const val ACTION_STOP = "com.jarvis.client.STOP_LINK"

        fun start(context: Context) {
            runCatching {
                ContextCompat.startForegroundService(
                    context,
                    Intent(context, EventService::class.java),
                )
            }.onFailure { Log.e(TAG, "could not start", it) }
        }

        fun stop(context: Context) {
            runCatching {
                context.startService(
                    Intent(context, EventService::class.java).setAction(ACTION_STOP),
                )
            }
        }
    }
}
