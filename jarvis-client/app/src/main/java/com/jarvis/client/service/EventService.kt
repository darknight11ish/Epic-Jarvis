package com.jarvis.client.service

import android.app.Notification
import android.app.PendingIntent
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
import com.jarvis.client.Activity
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.LinkState
import com.jarvis.client.MainActivity
import com.jarvis.client.R
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.cancel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch

/**
 * Holds the SSE connection open.
 *
 * This is the single biggest thing the native app buys over a browser tab:
 * Android suspends a backgrounded WebView's connections within about a minute,
 * so approvals silently stop arriving. A foreground service does not get killed
 * for that.
 *
 * The type is specialUse rather than dataSync deliberately - see §3.1(2). The
 * six-hour dataSync budget on Android 15 is shared across every dataSync
 * service in the app and, when spent, produces a fatal RemoteServiceException
 * rather than a graceful stop. §11 makes "survives more than six hours without
 * the app being foregrounded" an acceptance criterion, which is precisely the
 * test dataSync fails.
 */
class EventService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var watcher: Job? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        JarvisRuntime.initialize(this)
        startInForeground(LinkState.RECONNECTING, Activity.IDLE, 0)

        // The notification carries live state rather than a fixed string. It is
        // the only surface visible while the phone is in a pocket, so "Linked"
        // versus "Reconnecting" versus "2 waiting" is the whole value of it.
        watcher = scope.launch {
            combine(
                JarvisRuntime.link,
                JarvisRuntime.activity,
                JarvisRuntime.pending,
            ) { link, activity, pending -> Triple(link, activity, pending.size) }
                .collect { (link, activity, count) ->
                    startInForeground(link, activity, count)
                    // The status line is not an alert — it is IMPORTANCE_LOW and
                    // silent by design. Anything actually waiting for a decision
                    // needs its own notification, on its own channel, or the
                    // whole reason this service holds the stream open in the
                    // background is wasted battery.
                    ApprovalNotifier.sync(this@EventService, JarvisRuntime.pending.value)
                }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            JarvisRuntime.stopStream()
            stopSelf()
            return START_NOT_STICKY
        }
        if (intent?.action == ACTION_DENY) {
            denyFromNotification(intent.getStringExtra(ApprovalNotifier.EXTRA_APPROVAL_ID))
            return START_NOT_STICKY
        }
        JarvisRuntime.startStream()
        return START_STICKY
    }

    /**
     * The Deny button on an approval notification.
     *
     * Reachable only because this service is already running the stream that
     * put the approval in `JarvisRuntime.pending` in the first place - the
     * notification cannot exist otherwise, so the lookup below is not a race
     * against something that might not have started yet.
     *
     * No confirmation, no biometric: this is the same unguarded
     * `decide(item, approve = false)` InboxScreen's own Deny button already
     * sends, on the same "refusing something you have not read costs only a
     * retry" reasoning `notice.deny_ok` states server-side.
     *
     * Nothing here cancels the notification directly. `decide`'s own success
     * path calls `refreshPending()`, which changes `JarvisRuntime.pending` and
     * runs this service's own watcher, which resyncs the drawer - the same
     * path that already removes a notification approved or denied from the
     * desktop instead. A failure leaves the item, and the notification, right
     * where they were: this queue never shows "gone" before the desktop has
     * actually said so, the same rule the Brain screen's memory queue holds
     * by staying busy rather than optimistically hiding a row.
     */
    private fun denyFromNotification(id: String?) {
        val item = id?.let { target -> JarvisRuntime.pending.value.firstOrNull { it.id == target } }
            ?: return
        scope.launch { JarvisRuntime.decide(item, approve = false) }
    }

    override fun onDestroy() {
        watcher?.cancel()
        watcher = null
        // Nothing is listening for these any more, and a decision request that
        // outlives the connection that could deliver the answer is a trap.
        ApprovalNotifier.clear(this)
        JarvisRuntime.stopStream()
        // The scope, not only the one child it tracked. onClick and
        // onStartCommand launch untracked work on it, so a service torn
        // down mid-call left a coroutine running on a live job, holding
        // the destroyed instance.
        scope.cancel()
        super.onDestroy()
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

    private fun startInForeground(link: LinkState, activity: Activity, pending: Int) {
        val text = when {
            link != LinkState.CONNECTED -> when (link) {
                LinkState.RECONNECTING -> "Reconnecting…"
                else -> "Offline"
            }
            pending > 0 -> if (pending == 1) "1 approval waiting" else "$pending approvals waiting"
            activity == Activity.LISTENING -> "Listening"
            activity == Activity.THINKING -> "Thinking"
            activity == Activity.SPEAKING -> "Speaking"
            activity == Activity.WORKING -> "Working"
            activity == Activity.ERROR -> "Something went wrong"
            else -> "Linked"
        }

        val notification: Notification =
            NotificationCompat.Builder(this, CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_notification)
                .setContentTitle(getString(R.string.app_name))
                .setContentText(text)
                .setOngoing(true)
                .setSilent(true)
                .setShowWhen(false)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
                .setContentIntent(contentIntent())
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

    private fun contentIntent(): PendingIntent =
        PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

    companion object {
        private const val TAG = "JarvisEventService"
        const val CHANNEL_ID = "jarvis_link"
        private const val NOTIFICATION_ID = 0x4A56
        const val ACTION_STOP = "com.jarvis.client.STOP_LINK"
        const val ACTION_DENY = "com.jarvis.client.DENY_APPROVAL"

        /**
         * Set when the platform refused to let the service go foreground. Read by
         * the readiness screen; null while nothing has gone wrong.
         */
        @JvmStatic
        @Volatile
        var lastStartFailure: String? = null

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
