package com.jarvis.assistant.service

import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.jarvis.assistant.JarvisRuntime
import com.jarvis.assistant.MainActivity
import com.jarvis.assistant.R
import com.jarvis.assistant.network.ConnectionState
import com.jarvis.assistant.notifications.ApprovalNotificationManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch

/**
 * Keeps the process alive so approval requests and voice replies still arrive
 * with the screen off.
 *
 * The service starts under the `specialUse` foreground type — holding the link
 * open is not itself microphone work — and promotes itself to `microphone` only
 * while capture is running. Declaring `microphone` up front would make
 * startForeground throw on Android 14+ whenever RECORD_AUDIO has not been
 * granted yet.
 */
class JarvisForegroundService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var watcher: Job? = null
    private var wakeLock: PowerManager.WakeLock? = null

    @Volatile private var lastState: ConnectionState = ConnectionState.RECONNECTING

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        JarvisRuntime.initialize(this)

        startInForeground(ConnectionState.RECONNECTING, micActive = false)
        acquireWakeLock()

        // Synchronous, so the runtime can promote the service to the `microphone`
        // type and learn whether the platform allowed it *before* AudioRecord is
        // opened. Driving this off the micActive flow instead is too late: the
        // collector is dispatched through a channel, so the promotion lands after
        // startRecording() has already been evaluated by the audio policy.
        JarvisRuntime.micForegroundPromoter = { wantsMic ->
            startInForeground(lastState, micActive = wantsMic)
        }

        watcher = scope.launch {
            combine(
                JarvisRuntime.socket.state,
                JarvisRuntime.micActive,
            ) { state, mic -> state to mic }
                .collect { (state, mic) ->
                    startInForeground(state, mic)
                }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        JarvisRuntime.connect()
        // Restarted by the system after a kill: the whole point is to come back.
        return START_STICKY
    }

    override fun onDestroy() {
        watcher?.cancel()
        watcher = null
        JarvisRuntime.micForegroundPromoter = null
        releaseWakeLock()
        super.onDestroy()
    }

    /**
     * @return true when the requested foreground type was actually applied. A false
     * here for a microphone request means the platform refused, and the caller must
     * not capture: see the catch block.
     */
    private fun startInForeground(state: ConnectionState, micActive: Boolean): Boolean {
        lastState = state
        val wantsMicType = micActive && JarvisRuntime.hasMicPermission()
        val type = if (wantsMicType) {
            ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
        } else {
            specialUseType()
        }

        val text = when (state) {
            ConnectionState.CONNECTED -> if (micActive) "Listening" else "Linked to desktop"
            ConnectionState.RECONNECTING -> "Reconnecting…"
            ConnectionState.OFFLINE -> "Offline"
        }

        val notification = NotificationCompat.Builder(this, ApprovalNotificationManager.CHANNEL_LINK)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(text)
            .setOngoing(true)
            .setShowWhen(false)
            .setSilent(true)
            .setPriority(NotificationCompat.PRIORITY_MIN)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .setContentIntent(contentIntent())
            .build()

        return try {
            ServiceCompat.startForeground(this, NOTIFICATION_ID, notification, type)
            true
        } catch (e: Exception) {
            // A denied permission must not take the whole link down, so the service
            // stays up under its uncapped specialUse type.
            Log.e(TAG, "startForeground(type=$type) rejected", e)
            if (wantsMicType) {
                // But capture must stop. `microphone` is a while-in-use type and the
                // platform throws when one is started from the background; silently
                // downgrading and carrying on left AudioRecord running under a
                // non-microphone service, which the platform mutes — an ongoing
                // notification reading "Listening" while the desktop received an
                // endless stream of silence, recorded only in logcat.
                runCatching {
                    ServiceCompat.startForeground(
                        this,
                        NOTIFICATION_ID,
                        notification,
                        specialUseType(),
                    )
                }
                if (JarvisRuntime.micActive.value) JarvisRuntime.stopMic()
            }
            false
        }
    }

    private fun specialUseType(): Int =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
        } else {
            0
        }

    private fun contentIntent(): PendingIntent =
        PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

    private fun acquireWakeLock() {
        if (wakeLock != null) return
        val pm = ContextCompat.getSystemService(this, PowerManager::class.java) ?: return
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, WAKE_LOCK_TAG).apply {
            setReferenceCounted(false)
            runCatching { acquire(WAKE_LOCK_TIMEOUT_MS) }
        }
    }

    private fun releaseWakeLock() {
        wakeLock?.let { lock -> runCatching { if (lock.isHeld) lock.release() } }
        wakeLock = null
    }

    companion object {
        private const val TAG = "JarvisFgs"
        private const val NOTIFICATION_ID = 0x4A56
        private const val WAKE_LOCK_TAG = "JarvisMobile::link"

        /**
         * Bounded so a crash on the desktop side cannot pin the CPU awake
         * indefinitely; the service re-acquires whenever it is restarted.
         */
        private const val WAKE_LOCK_TIMEOUT_MS = 6L * 60L * 60L * 1000L

        const val ACTION_STOP = "com.jarvis.assistant.STOP_LINK"

        fun start(context: Context) {
            val intent = Intent(context, JarvisForegroundService::class.java)
            runCatching { ContextCompat.startForegroundService(context, intent) }
                .onFailure { Log.e(TAG, "could not start foreground service", it) }
        }

        fun stop(context: Context) {
            val intent = Intent(context, JarvisForegroundService::class.java)
                .setAction(ACTION_STOP)
            runCatching { context.startService(intent) }
        }
    }
}
