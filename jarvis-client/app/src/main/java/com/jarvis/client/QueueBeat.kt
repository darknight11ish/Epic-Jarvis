package com.jarvis.client

/**
 * When this phone re-reads the approval queue with no event to tell it to.
 *
 * WHY THIS EXISTS (the owner's report of 2026-10-29): *"when a decision/approval
 * card has already been addressed (approved or denied) on either the Android app
 * or the desktop program, make sure the Android widgets (and every other
 * surface that shows a card/notification) update to reflect that - no stale card
 * left showing, no dead Approve/Deny on a resolved card."*
 *
 * Every Android surface - the home-screen approval widget, the notification, the
 * Home card, the Inbox plate - reads ONE thing, [JarvisRuntime.pending], and that
 * one thing was only ever assigned after a re-read triggered by the `approval`
 * event (`JarvisRuntime.onEvent`). The event is a DOORBELL, and a doorbell can be
 * missed:
 *
 *  - the PC's pump publishes it from a poller that catches its own exceptions
 *    (`jarvis_events._poll_approvals`, `except Exception: return`), so one failed
 *    database read is one silent tick;
 *  - a `note()` publishes only on CHANGE, so the backend has to see the change
 *    before it can ring at all - with the pump not running (an unapplied patch, a
 *    backend started differently) there is nothing to ring;
 *  - the pump's own tick is the backend process's; a PC asleep, mid-restart, or
 *    with the events patch missing rings nothing at all.
 *
 * The desktop never had this as a hang: its HUD page has carried a 30-second
 * safety-net read beside the stream since long before this (`jarvis_hud.html`'s
 * `setInterval(() => apprPoll(), 30000)`), and its stream re-reads the queue on
 * every connect and every resume. The phone had no beat at all - so a missed
 * doorbell meant the card stayed on the home screen, with a Deny that could only
 * answer "no longer waiting", until the app was restarted or the link dropped.
 *
 * So this is the same safety net, with the same 30 seconds, on the phone.
 *
 * WHY IT IS NOT THE "SECOND POLLER" THE 2026-10-27 DECISION REFUSED. That
 * decision (`docs/DECISIONS.md`, "A home-screen widget ends in words") turned
 * down a *background* refresh that would wake a phone to fetch a queue nobody
 * was showing, and it was right: `widgetJob` already redraws every widget when
 * the queue changes, and a background poll would duplicate it. This beat is the
 * other case - the app is ALREADY running (the runtime is started, the stream is
 * up or trying), a card is ALREADY on screen, and the only question is whether
 * the queue still holds it. It reads nothing when no card is waiting, it starts
 * no service, it wakes no widget, and it cannot approve or deny anything: it is
 * one GET of the same route every surface already reads.
 *
 * WHY 30 SECONDS. A dead card is a wrong "waiting on you" on a lock screen; a
 * phone reading one small JSON document every 30 seconds while a card waits is
 * nothing beside the event stream's own 20-second keepalives. It is also the
 * number the desktop's own safety net uses, so the two apps answer "how stale
 * can a card be" with one number instead of two.
 *
 * Pure and Android-free, so `QueueBeatTest` can check the whole matrix on the
 * JVM: the runtime it feeds (a singleton built from a `Context`) cannot be
 * constructed off a device.
 */
object QueueBeat {

    /** How often the fallback read runs. See "WHY 30 SECONDS" above. */
    const val EVERY_MS = 30_000L

    /**
     * Whether this beat should re-read the queue now.
     *
     * Only when there is something on screen to be wrong about, and only when
     * the PC can actually be asked:
     *
     *  - `waiting == 0`: nothing is drawn from the queue, so there is nothing a
     *    stale read could hold open. A quiet phone makes no request at all -
     *    which is what keeps this from being a poll.
     *  - `connected == false`: the link is down or reconnecting, and that path
     *    has its own recovery (`startStream`'s watchdog, `EventStream`'s own
     *    reconnect). Asking anyway would only fail, and `refreshPending`'s
     *    failure arm sets `stale` and a notice - turning a phone with no signal
     *    into one that says "Could not re-read what is waiting" every 30
     *    seconds about a queue that is fine.
     *
     * @param waiting how many approvals [JarvisRuntime.pending] holds.
     * @param connected whether the event stream is CONNECTED right now.
     */
    fun due(waiting: Int, connected: Boolean): Boolean = waiting > 0 && connected
}
