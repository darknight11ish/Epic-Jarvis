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
import android.widget.Toast
import com.jarvis.client.net.ApiResult
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.jarvis.client.Activity
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.LinkState
import com.jarvis.client.MainActivity
import com.jarvis.client.R
import com.jarvis.client.voice.VoiceSession
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.cancel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

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
            linkWanted = false
            JarvisRuntime.stopStream()
            stopSelf()
            return START_NOT_STICKY
        }
        if (intent?.action == ACTION_STOP_RINGING) {
            // Stop on a ringing alarm or urgent "tell me when": silence and
            // remove that one notification. Nothing is sent, nothing decided -
            // and the link is NOT started: Stop does not need it, and the
            // owner may have switched it off (bug audit 2026-09-26, #4). A
            // service woken only for this goes away again.
            ScheduleNotifier.stopRinging(this, intent.getStringExtra(ScheduleNotifier.EXTRA_TAG))
            if (!linkWanted) {
                stopSelf()
                return START_NOT_STICKY
            }
            return START_STICKY
        }
        // Every other start runs the link.
        linkWanted = true
        if (intent?.action == ACTION_DENY) {
            // The stream first, same as every other start. This branch used to
            // skip it, so a Deny tapped while the service was cold - after a
            // reboot, or after Android reclaimed the process overnight - was
            // decided against whatever `pending` last held, which is the
            // stale-queue case the decision blocker exists to refuse. Starting
            // the stream is idempotent when it is already up.
            JarvisRuntime.startStream()
            denyFromNotification(intent.getStringExtra(ApprovalNotifier.EXTRA_APPROVAL_ID))
            // START_STICKY, not START_NOT_STICKY: the sticky flag is the
            // system's restart policy going forward, not a per-call receipt,
            // and this branch does not call stopSelf() the way ACTION_STOP
            // above does. Returning NOT_STICKY here would leave the link
            // unable to auto-restart after some later, unrelated kill, purely
            // because the last onStartCommand happened to be a Deny tap.
            return START_STICKY
        }
        if (intent?.action == ACTION_SNOOZE) {
            // A notification's Snooze (ScheduleNotifier): the stream first,
            // like Deny, then ONE snooze once the link is live.
            JarvisRuntime.startStream()
            snoozeFromNotification(intent.getStringExtra(ScheduleNotifier.EXTRA_JOB_ID))
            return START_STICKY
        }
        JarvisRuntime.startStream()
        return START_STICKY
    }

    /**
     * The Snooze button on a timer's, alarm's or reminder's notification. It
     * waits for the link like [denyFromNotification] - a change is refused on
     * a stale link (rule 4), and a cold process starts stale - then sends ONE
     * snooze through the same call as Coming up's button
     * ([JarvisRuntime.scheduleAct], held on a stale link), and says how it
     * went in a toast: the app is very likely not on screen. The
     * notification goes only once the PC said yes.
     */
    private fun snoozeFromNotification(id: String?) {
        if (id == null || !com.jarvis.client.net.Schedule.validId(id)) return
        scope.launch {
            awaitLive()
            val (changed, said) = JarvisRuntime.scheduleAct(id, "snooze")
            runCatching { Toast.makeText(this@EventService, said, Toast.LENGTH_LONG).show() }
            if (changed) runCatching { ScheduleNotifier.cancel(this@EventService, id) }
        }
    }

    /**
     * The Deny button on an approval notification.
     *
     * The lookup below CAN miss, and used to miss FAR more often than the
     * comment that once sat here admitted. `startStream()` just above this
     * call is fire-and-forget - it launches its own connect-and-refresh
     * coroutine and returns immediately - so on a cold process (Android
     * reclaimed it overnight; the notification stayed in the drawer) the very
     * next line read `pending.value` before that refresh had any chance to
     * land. Not an edge case: on a genuine cold start this raced every single
     * time, and lost every single time, because nothing here ever waited.
     *
     * So this now asks once, directly, before deciding the item is really
     * gone - the same `refreshPending()` the watchdog now also calls directly
     * for the same reason (see `JarvisRuntime.startStream`'s watchdog
     * comment): a plain GET that does not depend on the SSE stream's own
     * timing, so it can resolve long before `startStream`'s asynchronous
     * refresh would have. Only if the item is STILL missing after that fresh
     * read is it treated as actually gone.
     *
     * No confirmation, no biometric: this is the same unguarded
     * `decide(item, approve = false)` InboxScreen's own Deny button already
     * sends, on the same "refusing something you have not read costs only a
     * retry" reasoning `notice.deny_ok` states server-side.
     *
     * Nothing on the normal path cancels the notification directly (the
     * still-missing case below is the exception, because there is no
     * decision to make and so nothing that will ever resync it). `decide`'s
     * own success path calls `refreshPending()`, which changes
     * `JarvisRuntime.pending` and runs this service's own watcher, which
     * resyncs the drawer - the same path that already removes a notification
     * approved or denied from the desktop instead. A failure leaves the
     * item, and the notification, right where they were: this queue never
     * shows "gone" before the desktop has actually said so, the same rule
     * the Brain screen's memory queue holds by staying busy rather than
     * optimistically hiding a row.
     */
    private fun denyFromNotification(id: String?) {
        if (id == null) return
        scope.launch {
            // Wait - briefly - for the link to be live before looking. On a
            // cold process the stream has only just been started, `stale` is
            // still true, and `decide()` rightly refuses to act on a stale
            // queue (rule 4). Deciding at once therefore always failed on a
            // cold start; the toast said so, but the denial never went out.
            // Waiting for the first successful re-read fixes that without
            // loosening the rule: `decide()` still checks for itself.
            val live = awaitLive()
            var item = JarvisRuntime.pending.value.firstOrNull { it.id == id }
            if (item == null) {
                JarvisRuntime.refreshPending()
                item = JarvisRuntime.pending.value.firstOrNull { it.id == id }
            }
            if (item == null) {
                // Say so, out loud, and take the dead notification away.
                //
                // Silence here was the worst possible answer: the user
                // believes they refused something, and either the desktop is
                // still waiting for a decision or it was resolved hours ago -
                // and the drawer looks identical in both cases. A toast
                // because the app is very likely not on screen when a
                // notification action is tapped, and the in-app notice as
                // well so the explanation is still there when they do open
                // it.
                //
                // The wording splits on whether the fresh read above actually
                // landed. Connected and still missing is real evidence the
                // item is gone - the desktop was just asked and said so. Not
                // connected means this proved nothing either way: the item
                // could easily still be sitting open on the desktop, and
                // saying "handled elsewhere" here would be exactly the false
                // closure this whole rewrite exists to stop.
                Log.w(TAG, "deny tapped for an approval that is not pending any more")
                val message = if (!live || JarvisRuntime.stale.value || JarvisRuntime.link.value != LinkState.CONNECTED) {
                    "Could not reach the desktop to check - this may still be waiting. " +
                        "Open the app once it reconnects."
                } else {
                    "That request is no longer waiting - it was handled elsewhere, " +
                        "or Jarvis restarted since the notification was posted."
                }
                runCatching { Toast.makeText(this@EventService, message, Toast.LENGTH_LONG).show() }
                runCatching { JarvisRuntime.setNotice(message) }
                runCatching { ApprovalNotifier.cancelFor(this@EventService, id) }
                return@launch
            }
            // The result was discarded here. `decide()` already sets a notice
            // on failure - unreachable, stale, already handled - but a notice
            // is a view on a screen, and the whole reason this action exists
            // is that the screen is very likely not open. Without a Toast the
            // owner walked away believing they had denied something that the
            // desktop never heard about.
            val result = JarvisRuntime.decide(item, approve = false)
            if (result is ApiResult.Failed) {
                val message = "Could not send the denial: " +
                    (JarvisRuntime.notice.value ?: "the desktop did not accept it.")
                runCatching { Toast.makeText(this@EventService, message, Toast.LENGTH_LONG).show() }
            }
        }
    }

    /**
     * True once the link is connected and not stale, false if that has not
     * happened within [LIVE_WAIT_MS]. Returns at once when it already is.
     */
    private suspend fun awaitLive(): Boolean =
        withTimeoutOrNull(LIVE_WAIT_MS) {
            combine(JarvisRuntime.stale, JarvisRuntime.link) { stale, link ->
                !stale && link == LinkState.CONNECTED
            }.first { it }
        } ?: false

    override fun onDestroy() {
        watcher?.cancel()
        watcher = null
        // Nothing is listening for these any more, and a decision request that
        // outlives the connection that could deliver the answer is a trap.
        //
        // EXCEPT when the service is dying because it could not start at all.
        // `clear` calls `restore` first, which deliberately adopts
        // notifications posted by PREVIOUS processes - so on the path the
        // manifest itself describes (the system reclaims the process
        // overnight, the sticky restart lands with the app in the background,
        // and a background foreground-service start is refused) the service's
        // dying act was to cancel last night's real approval. Morning: an
        // empty drawer, and a widget reading "Not checked yet". The request
        // was still open on the desktop and had become invisible on the phone.
        //
        // Those notifications are not a dead end either: their Deny action
        // targets this service with ACTION_DENY, which starts the stream
        // again before answering. Keeping them is strictly better than the
        // trap this guard was written for - that trap is a link the owner
        // deliberately stopped, which is the case still cleared below.
        if (lastStartFailure == null) {
            ApprovalNotifier.clear(this)
        } else {
            Log.w(
                TAG,
                "not clearing approval notifications: this service is stopping because " +
                    "startForeground was refused ($lastStartFailure), and they may be the " +
                    "only sign left that something is waiting",
            )
        }
        JarvisRuntime.stopStream()
        // The on-device text-to-speech engine, which nothing else releases.
        // Creating a TextToSpeech binds a service for the life of the process,
        // and Speaker.release() - written for exactly this - had no caller
        // anywhere in the app. This is the one place in the files this change
        // owns where a shutdown is unambiguously correct: the link is being
        // torn down, and the next speakOnDevice rebuilds the engine lazily.
        //
        // Only while nothing is being spoken. release() calls stop(), which
        // would cut a reply off mid-sentence if the user stopped the link from
        // the tile while Jarvis was talking.
        runCatching {
            if (JarvisRuntime.voice.phase.value == VoiceSession.Phase.OFF) {
                JarvisRuntime.voice.speaker.release()
            }
        }
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
            activity == Activity.PAUSED -> "Paused"
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
            // Cleared on the path that actually worked, which nothing used to
            // do. The field was write-once, so one refused start left the
            // readiness screen warning about a link that had since come back
            // and stayed there until the process died - and a warning that
            // never clears is a warning nobody reads.
            lastStartFailure = null
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
            // The collector too, not only the service. stopSelf() asks the
            // system to tear the service down, which is not immediate, and the
            // watcher kept collecting in the meantime: every link, activity or
            // pending change came straight back in here, was refused again, and
            // logged again. On a flapping connection that is a tight loop of
            // binder calls and stack traces on the exact path that is already
            // failing - and every one of them rewrote lastStartFailure.
            //
            // Cancelling from inside the collector is safe: the rest of this
            // emission runs to the end and the next one never arrives.
            watcher?.cancel()
            watcher = null
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
        const val ACTION_SNOOZE = "com.jarvis.client.SNOOZE_JOB"
        const val ACTION_STOP_RINGING = "com.jarvis.client.STOP_RINGING"

        /**
         * How long a Deny from outside the app waits for the link to come up
         * before answering "could not reach the desktop". Long enough for a
         * cold start over Tailscale; short enough that the toast still reads
         * as the answer to the tap.
         */
        private const val LIVE_WAIT_MS = 20_000L

        /**
         * Set when the platform refused to let the service go foreground. Read by
         * the readiness screen; null while nothing has gone wrong.
         */
        @JvmStatic
        @Volatile
        var lastStartFailure: String? = null

        /**
         * Whether the link should be running in this process: set by every
         * start but a ringing alarm's Stop, cleared when the owner switches
         * the link off. A Stop tapped after that must not switch it back on.
         */
        @Volatile
        private var linkWanted = false

        fun start(context: Context) {
            runCatching {
                ContextCompat.startForegroundService(
                    context,
                    Intent(context, EventService::class.java),
                )
            }.onFailure { Log.e(TAG, "could not start", it) }
        }

        /**
         * Denies one approval from outside the app - the home-screen widget.
         *
         * Goes through this service, the same as the notification's Deny, so
         * both get the same handling: the stream is started, the queue is
         * re-read once the link is live, and the answer is said out loud
         * either way. The widget used to decide on its own against whatever
         * `pending` held in memory - empty after the process had been killed
         * - so it said "handled elsewhere" about approvals still waiting.
         *
         * A tap on a widget is one of Android's allowed reasons to start a
         * foreground service from the background. False if the start was
         * refused anyway, so the caller can say so.
         */
        fun deny(context: Context, id: String): Boolean =
            runCatching {
                ContextCompat.startForegroundService(
                    context,
                    Intent(context, EventService::class.java)
                        .setAction(ACTION_DENY)
                        .putExtra(ApprovalNotifier.EXTRA_APPROVAL_ID, id),
                )
            }.onFailure { Log.e(TAG, "could not start to deny", it) }.isSuccess

        fun stop(context: Context) {
            runCatching {
                context.startService(
                    Intent(context, EventService::class.java).setAction(ACTION_STOP),
                )
            }
        }
    }
}
