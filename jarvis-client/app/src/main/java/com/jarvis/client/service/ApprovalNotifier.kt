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
import com.jarvis.client.net.PendingItem

/**
 * Puts a pending approval in front of you when the app is not.
 *
 * This is the reason the foreground service exists. Holding the stream open in
 * the background is only worth the battery if something *happens* when a
 * decision arrives, and until now nothing did: the only channel was the link's
 * own status line, at IMPORTANCE_LOW with setSilent(true). An approval could
 * arrive, sit in the queue, and expire with the phone face-down on a table
 * having made no sound and shown nothing.
 */
object ApprovalNotifier {

    /**
     * Notification ids, assigned per approval id and remembered so the same
     * request updates its own notification rather than stacking a second one.
     *
     * A map rather than `id.hashCode()`: a hash collision between two live
     * approvals would silently replace one decision request with another, which
     * is the one failure mode this whole surface exists to prevent.
     */
    private val assigned = LinkedHashMap<String, Int>()
    private var nextId = FIRST_ID

    /**
     * Brings the drawer in line with [pending]: posts what is new, refreshes
     * what changed, and cancels what has been decided elsewhere.
     *
     * Cancelling matters as much as posting. Approve something on the desktop
     * and the phone's notification must go, or the next person to pick it up is
     * looking at a decision that no longer exists.
     */
    fun sync(context: Context, pending: List<PendingItem>) {
        val manager = NotificationManagerCompat.from(context)
        if (!allowed(context)) {
            // Denied POST_NOTIFICATIONS. Nothing to do but keep the bookkeeping
            // straight, so that granting it later posts a correct set rather
            // than a backlog.
            assigned.keys.retainAll(pending.map { it.id }.toSet())
            return
        }

        val live = pending.associateBy { it.id }

        for ((id, notificationId) in assigned.entries.toList()) {
            if (id !in live) {
                manager.cancel(notificationId)
                assigned.remove(id)
            }
        }

        for (item in pending) {
            val notificationId = assigned.getOrPut(item.id) { nextId++ }
            runCatching { manager.notify(notificationId, build(context, item)) }
                .onFailure { Log.w(TAG, "could not post approval ${item.id}", it) }
        }

        if (pending.size > 1) {
            runCatching { manager.notify(SUMMARY_ID, summary(context, pending.size)) }
        } else {
            manager.cancel(SUMMARY_ID)
        }
    }

    /** Clears everything this object posted. Used when the link goes down. */
    fun clear(context: Context) {
        val manager = NotificationManagerCompat.from(context)
        assigned.values.forEach { manager.cancel(it) }
        assigned.clear()
        manager.cancel(SUMMARY_ID)
    }

    private fun allowed(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED

    private fun build(context: Context, item: PendingItem): Notification {
        val body = buildString {
            if (item.summary.isNotBlank()) appendLine(item.summary)
            if (item.risk.why.isNotBlank()) appendLine(item.risk.why)
            if (item.raised != null) {
                // Named, never amplified. See the importance note below.
                appendLine("Marked urgent by the message itself.")
            }
        }.trim().ifEmpty { "Jarvis is waiting for a decision." }

        return NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(item.title)
            .setContentText(body.lineSequence().first())
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            // Never PRIORITY_MAX and never a full-screen intent, whatever the
            // item claims about itself. `raised` is a *quoted assertion from
            // whoever wrote the message* — the exact thing a phishing attempt
            // sets. Letting it raise the alarm level would hand an attacker the
            // volume control, so it changes the wording and nothing else.
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            // The summary can quote an email. The lock screen gets the redacted
            // version below; the real text needs the phone unlocked.
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setPublicVersion(redacted(context))
            .setAutoCancel(true)
            .setOnlyAlertOnce(true)
            .setGroup(GROUP)
            .setContentIntent(openCard(context, item.id))
            // Deliberately no Approve/Deny actions.
            //
            // Both gates that make a decision safe live inside the app: the
            // staleness check, which refuses to send a decision the phone
            // cannot confirm is still live, and the fingerprint on anything
            // outbound or irreversible. A notification action would route
            // around both from the lock screen. Tapping opens the card, which
            // is one extra tap and the entire safety model.
            .build()
    }

    private fun redacted(context: Context): Notification =
        NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(context.getString(R.string.app_name))
            .setContentText(context.getString(R.string.approval_locked))
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .build()

    private fun summary(context: Context, count: Int): Notification =
        NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(context.getString(R.string.app_name))
            .setContentText(context.getString(R.string.approvals_waiting, count))
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setGroup(GROUP)
            .setGroupSummary(true)
            .setContentIntent(openCard(context, null))
            .build()

    private fun openCard(context: Context, approvalId: String?): PendingIntent {
        val intent = Intent(context, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            .setAction(ACTION_OPEN_APPROVAL)
        if (approvalId != null) intent.putExtra(EXTRA_APPROVAL_ID, approvalId)
        return PendingIntent.getActivity(
            context,
            // A distinct request code per approval, or FLAG_UPDATE_CURRENT
            // would rewrite every earlier intent's extras to the newest id and
            // every notification in the drawer would open the same card.
            approvalId?.hashCode() ?: 0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    private const val TAG = "ApprovalNotifier"
    const val CHANNEL_ID = "jarvis_approval"
    const val ACTION_OPEN_APPROVAL = "com.jarvis.client.OPEN_APPROVAL"
    const val EXTRA_APPROVAL_ID = "approval_id"
    private const val GROUP = "jarvis_approvals"
    private const val FIRST_ID = 0x4B00
    private const val SUMMARY_ID = 0x4AFF
}
