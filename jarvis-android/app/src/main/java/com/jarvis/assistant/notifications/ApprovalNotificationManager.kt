package com.jarvis.assistant.notifications

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.jarvis.assistant.JarvisRuntime
import com.jarvis.assistant.R
import com.jarvis.assistant.network.ApprovalRequestEvent
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * Signs approval decisions so the desktop can prove the tap came from the paired
 * handset rather than anything else that reached the WebSocket port.
 *
 * With no shared secret configured the signature is empty and the desktop is
 * expected to fall back to whatever transport-level trust the Tailnet gives it.
 */
object ApprovalSigner {

    fun sign(secret: String, id: String, approved: Boolean, deviceId: String, atMs: Long): String {
        if (secret.isEmpty()) return ""
        val payload = "$id|$approved|$deviceId|$atMs"
        return runCatching {
            val mac = Mac.getInstance("HmacSHA256")
            mac.init(SecretKeySpec(secret.toByteArray(Charsets.UTF_8), "HmacSHA256"))
            mac.doFinal(payload.toByteArray(Charsets.UTF_8))
                .joinToString("") { byte -> "%02x".format(byte) }
        }.getOrDefault("")
    }
}

/**
 * Posts the lock-screen approval gate and routes the button taps.
 *
 * The decision goes back over the existing WebSocket from a BroadcastReceiver,
 * so the desktop unblocks without the phone ever being unlocked or the app
 * being brought to the foreground.
 */
class ApprovalNotificationManager(context: Context) {

    private val appContext = context.applicationContext
    private val notifier = NotificationManagerCompat.from(appContext)

    init {
        createChannels()
    }

    private fun createChannels() {
        val manager = ContextCompat.getSystemService(appContext, NotificationManager::class.java)
            ?: return

        val approvals = NotificationChannel(
            CHANNEL_APPROVALS,
            appContext.getString(R.string.channel_approvals_name),
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = appContext.getString(R.string.channel_approvals_description)
            enableVibration(true)
            setShowBadge(true)
            lockscreenVisibility = NotificationCompat.VISIBILITY_PUBLIC
        }

        val link = NotificationChannel(
            CHANNEL_LINK,
            appContext.getString(R.string.channel_link_name),
            NotificationManager.IMPORTANCE_MIN,
        ).apply {
            description = appContext.getString(R.string.channel_link_description)
            setShowBadge(false)
        }

        manager.createNotificationChannel(approvals)
        manager.createNotificationChannel(link)
    }

    fun post(request: ApprovalRequestEvent) {
        val body = buildString {
            append(request.summary.ifBlank { "Waiting on your approval." })
            request.detail?.takeIf { it.isNotBlank() }?.let {
                append('\n')
                append(it)
            }
        }

        val notification = NotificationCompat.Builder(appContext, CHANNEL_APPROVALS)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(request.title)
            .setContentText(request.summary.ifBlank { "Waiting on your approval." })
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setSubText(request.tier)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setAutoCancel(false)
            .setOngoing(false)
            .setOnlyAlertOnce(true)
            .addAction(
                R.drawable.ic_notification,
                appContext.getString(R.string.action_approve),
                decisionIntent(request.id, approved = true),
            )
            .addAction(
                R.drawable.ic_notification,
                appContext.getString(R.string.action_reject),
                decisionIntent(request.id, approved = false),
            )
            .build()

        // POST_NOTIFICATIONS may still be denied; the desktop gate then falls back
        // to its own timeout rather than the phone silently swallowing the request.
        runCatching { notifier.notify(notificationId(request.id), notification) }
    }

    fun cancel(requestId: String) {
        notifier.cancel(notificationId(requestId))
    }

    private fun decisionIntent(requestId: String, approved: Boolean): PendingIntent {
        val intent = Intent(appContext, ApprovalActionReceiver::class.java).apply {
            action = if (approved) ACTION_APPROVE else ACTION_REJECT
            putExtra(EXTRA_REQUEST_ID, requestId)
        }
        return PendingIntent.getBroadcast(
            appContext,
            notificationId(requestId) + if (approved) 1 else 2,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    companion object {
        const val CHANNEL_APPROVALS = "jarvis_approvals"
        const val CHANNEL_LINK = "jarvis_link"
        const val ACTION_APPROVE = "com.jarvis.assistant.APPROVE"
        const val ACTION_REJECT = "com.jarvis.assistant.REJECT"
        const val EXTRA_REQUEST_ID = "request_id"

        fun notificationId(requestId: String): Int = requestId.hashCode() and 0x7fffffff
    }
}

/** Receives the lock-screen taps and hands the signed decision to the runtime. */
class ApprovalActionReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val requestId = intent.getStringExtra(ApprovalNotificationManager.EXTRA_REQUEST_ID)
            ?: return
        val approved = when (intent.action) {
            ApprovalNotificationManager.ACTION_APPROVE -> true
            ApprovalNotificationManager.ACTION_REJECT -> false
            else -> return
        }
        JarvisRuntime.initialize(context)
        JarvisRuntime.submitApprovalDecision(requestId, approved)
    }
}
