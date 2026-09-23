package com.jarvis.client.service

import android.Manifest
import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
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
     * Whether [restore] has already read the drawer back in this process.
     *
     * Once per process, not once per sync: `getActiveNotifications` is a binder
     * call to SystemUI and this object is synced on every state emission, which
     * is often. After the first pass [assigned] is authoritative again.
     */
    private var restored = false

    /**
     * How many pending approvals could not be announced because
     * POST_NOTIFICATIONS is not granted, and a one-shot latch so the log says
     * so once rather than on every emission.
     *
     * This exists because the failure is invisible from the outside. The
     * foreground service keeps running, the link keeps reading CONNECTED, the
     * ongoing status notification is hidden too - so nothing on the phone looks
     * broken while the one thing this file exists to do is not happening.
     *
     * Read by the Checks screen's "Notifications" item, which reports the
     * number back. MainActivity now also asks for the permission the moment
     * the app is paired, so the old hole - never opening Checks meant never
     * being asked, and never being asked meant every approval went unheard -
     * is closed at the source. This counter stays because the permission can
     * still be refused, or revoked later in Android Settings.
     */
    @Volatile
    var silenced = 0
        private set

    private var warnedSilenced = false

    /**
     * Reads the drawer back after the process was killed and restarted.
     *
     * [assigned] is in memory only. Android reclaims the process overnight, the
     * service restarts sticky, and `sync` then runs with an empty map: its
     * cancel loop has nothing to cancel, so approvals the desktop resolved
     * hours ago sit in the drawer for ever and their Deny buttons point at
     * approvals this process has never heard of.
     *
     * The approval id is stamped into the notification's own extras by [build],
     * so the map can be rebuilt from what is actually on screen rather than
     * guessed at. Anything in this object's id range that cannot be matched -
     * posted by an older build, or corrupted - is cancelled, because a
     * notification nothing can ever map back to an approval is one the user can
     * never get an answer out of.
     */
    private fun restore(context: Context) {
        if (restored) return
        restored = true
        val manager = ContextCompat.getSystemService(context, NotificationManager::class.java)
            ?: return
        val active = runCatching { manager.activeNotifications }
            .onFailure { Log.w(TAG, "could not read the drawer back", it) }
            .getOrNull() ?: return
        for (posted in active) {
            // Ours only, and only the per-approval range. The link's own ongoing
            // notification and the group summary both sit below FIRST_ID, and
            // cancelling either of those here would kill the foreground
            // service's own notification.
            if (posted == null || posted.id < FIRST_ID) continue
            val approvalId = runCatching { posted.notification?.extras?.getString(EXTRA_APPROVAL_ID) }
                .getOrNull()
            if (approvalId.isNullOrEmpty()) {
                runCatching { manager.cancel(posted.id) }
                continue
            }
            assigned[approvalId] = posted.id
            // Past anything already on screen, or the next approval would
            // overwrite a live one - the collision this whole map exists to
            // prevent, reintroduced by the restart.
            if (posted.id >= nextId) nextId = posted.id + 1
        }
    }

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
        // Before anything is posted or cancelled: after a sticky restart the map
        // is empty and the drawer is not, and a cancel loop over an empty map
        // cancels nothing.
        restore(context)
        if (!allowed(context)) {
            // Denied POST_NOTIFICATIONS. Nothing to do but keep the bookkeeping
            // straight, so that granting it later posts a correct set rather
            // than a backlog.
            assigned.keys.retainAll(pending.map { it.id }.toSet())
            silenced = pending.size
            if (pending.isNotEmpty() && !warnedSilenced) {
                // Once per denied run, not once per emission: this is called on
                // every state change and a log line per frame is its own bug.
                warnedSilenced = true
                Log.w(
                    TAG,
                    "POST_NOTIFICATIONS is not granted, so ${pending.size} approval(s) " +
                        "will not be announced. Nothing else looks broken - the service is " +
                        "still running - so this is the only sign. Grant notifications for " +
                        "Jarvis in Android Settings, or open the Checks screen.",
                )
            }
            return
        }
        silenced = 0
        warnedSilenced = false

        val live = pending.associateBy { it.id }

        for ((id, notificationId) in assigned.entries.toList()) {
            if (id !in live) {
                manager.cancel(notificationId)
                assigned.remove(id)
            }
        }

        for (item in pending) {
            val notificationId = assigned.getOrPut(item.id) { nextId++ }
            runCatching { manager.notify(notificationId, build(context, item, notificationId)) }
                .onFailure { Log.w(TAG, "could not post approval ${item.id}", it) }
        }

        if (pending.size > 1) {
            // The summary alerts on ITS channel, not on its children's, and the
            // default group behaviour is for the summary to alert at all. So a
            // summary hardcoded to the loud channel would make a sound over a
            // drawer of approvals that were every one of them meant to be
            // quiet - undoing the whole routing one line above.
            val loud = pending.any { it.shouldInterrupt }
            runCatching { manager.notify(SUMMARY_ID, summary(context, pending.size, loud)) }
        } else {
            manager.cancel(SUMMARY_ID)
        }
    }

    /** Clears everything this object posted. Used when the link goes down. */
    fun clear(context: Context) {
        val manager = NotificationManagerCompat.from(context)
        // Including anything a previous process posted: without this, "clear"
        // cleared only what this process happened to remember, and the drawer
        // kept approvals from before the restart that nothing would ever remove.
        restore(context)
        assigned.values.forEach { manager.cancel(it) }
        assigned.clear()
        manager.cancel(SUMMARY_ID)
    }

    /**
     * Removes the notification for one approval that is no longer live.
     *
     * Used by the Deny action when the approval it names is not in `pending`
     * any more - the stale-notification case a restarted process produces. The
     * normal path does not need this: `decide` refreshes `pending` and the
     * watcher resyncs the drawer.
     */
    fun cancelFor(context: Context, approvalId: String) {
        val manager = NotificationManagerCompat.from(context)
        restore(context)
        assigned.remove(approvalId)?.let { manager.cancel(it) }
        // Same rule sync() uses: a summary over fewer than two children is just
        // a duplicate of the child.
        if (assigned.size < 2) manager.cancel(SUMMARY_ID)
    }

    private fun allowed(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED

    /**
     * The text this notification is allowed to show.
     *
     * `notice` when the desktop sent one, and NOTHING assembled here on top of
     * it. That is the whole contract: the desktop generates `notice` from the
     * action name and its own risk table, reading no `detail`, no `prompt` and
     * nothing inside `raised`, so it is safe by construction rather than safe
     * because a reviewer remembered to redact something.
     *
     * What this used to do is the hole: it composed a body from `item.summary`
     * and `item.risk.why`. Both are row prose, and row prose can carry text
     * somebody else wrote. It was mitigated - the lock screen has always shown
     * the redacted public version below, not this - but composing it here at
     * all is the mistake, and it is the same mistake in three other places in
     * this project's history.
     *
     * The fallback, used only when `notice` is absent (a desktop older than
     * the contract), is the title - built by decodePendingRows from the action
     * name alone, never from `prompt` or `detail` - and `risk.why`. It no
     * longer includes `item.summary`: that now carries the readable part of
     * `detail` (so the in-app card says what Jarvis wants), which is exactly
     * the payload a notification must not show. Posting nothing would be
     * worse: an approval nobody is told about is the failure this whole file
     * exists to prevent.
     */
    private fun textFor(item: PendingItem): Pair<String, String> {
        val notice = item.notice
        if (notice != null && notice.title.isNotBlank()) {
            return notice.title to notice.body.ifBlank { "Nothing has happened yet." }
        }
        val body = buildString {
            if (item.risk.why.isNotBlank()) appendLine(item.risk.why)
            if (item.raised != null) {
                // Named, never quoted. See the importance note below.
                appendLine("Marked urgent by the message itself.")
            }
        }.trim().ifEmpty { "Jarvis is waiting for a decision." }
        return item.title to body
    }

    private fun build(context: Context, item: PendingItem, notificationId: Int): Notification {
        val (title, body) = textFor(item)

        // Which channel, not which priority. On Android 8 and later the
        // decision to interrupt belongs to the channel; `setPriority` below is
        // kept only because it still orders notifications within one.
        val channel = if (item.shouldInterrupt) CHANNEL_ID else QUIET_CHANNEL_ID

        return NotificationCompat.Builder(context, channel)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
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
            // The approval id rides inside the notification so that a process
            // which has been killed and restarted can read [assigned] back off
            // the drawer in [restore]. Without it a restart loses every mapping
            // and the notifications it posted become uncancellable.
            .addExtras(Bundle().apply { putString(EXTRA_APPROVAL_ID, item.id) })
            .setGroup(GROUP)
            .setContentIntent(openCard(context, item.id, notificationId))
            // Deny only, never Approve - and Deny only when the desktop's own
            // notice says refusing without reading is safe.
            //
            // Approve is not offered on any account, and would be ignored by
            // EventService if it somehow arrived: approving from a
            // notification is refused on this side's own terms, not on the
            // server's say-so. Both gates that make an approval safe live
            // inside the app - the staleness check, which refuses to send a
            // decision the phone cannot confirm is still live, and the
            // fingerprint on anything outbound or irreversible - and a
            // notification action from the lock screen routes around both.
            //
            // Deny carries neither gate even inside the app - see
            // MainActivity.onDeny, which sends `decide(item, approve = false)`
            // with no biometric prompt - so offering it here moves the same
            // unguarded call to a second surface rather than weakening
            // anything. This was declined once before on the reasoning that
            // the extra tap is cheap and a notification is the surface where
            // a mistaken tap is least recoverable; asked again, the answer
            // was to add it.
            .apply {
                if (item.notice?.denyOk != false) {
                    addAction(
                        R.drawable.ic_notification,
                        context.getString(R.string.approval_deny_action),
                        denyIntent(context, item, notificationId),
                    )
                }
            }
            .build()
    }

    private fun redacted(context: Context): Notification =
        NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(context.getString(R.string.app_name))
            .setContentText(context.getString(R.string.approval_locked))
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .build()

    private fun summary(context: Context, count: Int, loud: Boolean): Notification =
        NotificationCompat.Builder(context, if (loud) CHANNEL_ID else QUIET_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(context.getString(R.string.app_name))
            .setContentText(context.getString(R.string.approvals_waiting, count))
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setGroup(GROUP)
            .setGroupSummary(true)
            .setContentIntent(openCard(context, null, SUMMARY_ID))
            .build()

    /**
     * Routes to [EventService], not a standalone receiver: the service is
     * already running and already holds the live `JarvisRuntime.pending` this
     * approval came from - the notification cannot exist otherwise - so there
     * is no cold-start case where the app has to be spun up just to read it.
     */
    private fun denyIntent(context: Context, item: PendingItem, notificationId: Int): PendingIntent {
        val intent = Intent(context, EventService::class.java)
            .setAction(EventService.ACTION_DENY)
            .putExtra(EXTRA_APPROVAL_ID, item.id)
        return PendingIntent.getService(
            context,
            // notificationId, not item.id.hashCode(): it comes from [assigned],
            // the same collision-free counter that already exists to keep two
            // live approvals from colliding on a notification id, so reusing it
            // here keeps two live approvals from colliding on a Deny action
            // too.
            //
            // This used to add that the code stays "distinct from openCard()'s
            // request code range (FIRST_ID and up vs. a raw hashCode)". That
            // stopped being true when openCard was given the same
            // notificationId to fix its own collision, and the sentence was
            // left behind describing a version that no longer exists. Nothing
            // breaks - getService and getActivity are different PendingIntent
            // kinds and do not collide on request code alone - but the stated
            // safety argument was void, so it is gone rather than left to be
            // trusted by whoever changes openCard next.
            notificationId,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    private fun openCard(context: Context, approvalId: String?, requestCode: Int): PendingIntent {
        val intent = Intent(context, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            .setAction(ACTION_OPEN_APPROVAL)
        if (approvalId != null) intent.putExtra(EXTRA_APPROVAL_ID, approvalId)
        return PendingIntent.getActivity(
            context,
            // The same collision-free id [denyIntent] uses, not
            // `approvalId?.hashCode()`: a hash collision between two live
            // approvals would rewrite the earlier one's intent extras to
            // the newer id under FLAG_UPDATE_CURRENT, and its notification
            // would open the wrong card. The summary passes its own fixed
            // SUMMARY_ID, which sits just below the per-item range and so
            // can never collide with one.
            requestCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    private const val TAG = "ApprovalNotifier"
    const val CHANNEL_ID = "jarvis_approval"

    /**
     * Approvals that post without a sound: see [PendingItem.shouldInterrupt].
     * A separate channel because importance is a channel property on Android 8
     * and later, and a separate ID because an app cannot lower the importance
     * of a channel it already created.
     */
    const val QUIET_CHANNEL_ID = "jarvis_approval_quiet"
    const val ACTION_OPEN_APPROVAL = "com.jarvis.client.OPEN_APPROVAL"
    const val EXTRA_APPROVAL_ID = "approval_id"
    private const val GROUP = "jarvis_approvals"
    private const val FIRST_ID = 0x4B00
    private const val SUMMARY_ID = 0x4AFF
}
