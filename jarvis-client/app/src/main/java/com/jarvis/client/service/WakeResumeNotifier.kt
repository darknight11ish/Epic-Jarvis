package com.jarvis.client.service

import android.Manifest
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.MainActivity
import com.jarvis.client.R
import com.jarvis.client.data.WakeResume

/**
 * The ONE quiet "\"Hey Jarvis\" is off since the phone restarted - tap to turn
 * it back on" notification ([WakeResume], docs/JARVIS-API.md section 81.1).
 *
 * Posted by [BootReceiver] only. It starts nothing: its tap opens
 * [MainActivity] with [MainActivity.ACTION_RESUME_LISTENING], and the app -
 * in front, after App lock if that is on - starts "Listen on this phone"
 * the same way the Checks switch does, with the same checks (the desktop's
 * wake word on, the microphone and notification permissions held). That is
 * the only way Android lets an app open the microphone: from the owner's
 * own action, with the app visible.
 *
 * On the wake-word channel, which is already quiet (IMPORTANCE_LOW: no
 * sound, no pop-up). No action buttons: the only thing to do is the tap.
 * Taken away when listening starts or is switched off, and by the tap.
 */
object WakeResumeNotifier {
    private const val TAG = "JarvisWakeResume"

    /**
     * Its own id, distinct from every other ([NotificationIds] holds them all and
     * NotificationIdsTest checks none repeats). It used to share 0x3200 with the
     * chatbot line, so cancelling one removed the other.
     */
    private const val NOTIFICATION_ID = NotificationIds.WAKE_RESUME

    fun post(context: Context, action: String?) {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            Log.i(TAG, "notifications not allowed; no restart notice")
            return
        }
        WakeWordService.ensureChannel(context)
        val open = PendingIntent.getActivity(
            context,
            REQUEST_CODE,
            Intent(context, MainActivity::class.java)
                .setAction(MainActivity.ACTION_RESUME_LISTENING)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(context, WakeWordService.CHANNEL_ID)
            .setLocalOnly(!JarvisRuntime.watchNotificationsAllowed())
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(WakeResume.title(action))
            .setContentText(WakeResume.TEXT)
            .setStyle(NotificationCompat.BigTextStyle().bigText(WakeResume.TEXT))
            .setSilent(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setAutoCancel(true)
            .setContentIntent(open)
            .build()
        runCatching { NotificationManagerCompat.from(context).notify(NOTIFICATION_ID, notification) }
            .onFailure { Log.w(TAG, "could not post the restart notice", it) }
    }

    fun cancel(context: Context) {
        runCatching { NotificationManagerCompat.from(context).cancel(NOTIFICATION_ID) }
    }

    private const val REQUEST_CODE = 0x3201
}
