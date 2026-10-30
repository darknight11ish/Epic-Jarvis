package com.jarvis.client

/**
 * Orders overlapping reads of the approval queue, so an old answer cannot
 * overwrite a newer one.
 *
 * WHY THIS EXISTS. `JarvisRuntime.refreshPending` is the one place the queue
 * every Android surface draws from is assigned, and it can be called from
 * several places at once: the 30-second `QueueBeat`, the `approval` event, a
 * screen resuming, and - the one that matters here - the decision path
 * immediately after `/api/approve` or `/api/deny` returns. They do not queue
 * up behind each other: the runtime's `scope` is `Dispatchers.Default`, so two
 * reads can be in flight together.
 *
 * The race, concretely: the beat's GET is issued while a card is still
 * waiting. The owner denies that card, the POST lands, and the decision's own
 * refresh reads an empty queue and clears the screen. THEN the beat's older
 * GET answers with the pre-decision list and puts the card back - and
 * `ApprovalNotifier.sync` re-posts its notification from that list, so the
 * resolved card is back on the lock screen for up to another 30 seconds. That
 * is the same "dead card" the beat exists to remove, arriving through the beat
 * itself.
 *
 * THE RULE. Every read takes a number from [begin] BEFORE it goes out. A
 * response is applied only if no newer read has started since; a superseded
 * response is dropped whole, success or failure. Dropping a superseded
 * FAILURE is the same safe direction: the newer read owns the state, and if
 * that one fails it sets `stale` and the old queue stays as it was - never a
 * queue the app pretends is fresh.
 *
 * The check and the write happen inside one lock, so a newer request cannot
 * start between "you are still the newest" and the assignment it guards. The
 * guarded work must be a plain state update with no suspension; the callers'
 * suspending follow-ups run after it.
 *
 * Pure and Android-free, so `PendingRefreshOrderTest` can prove the ordering
 * on the JVM: the runtime is a singleton built from a `Context` and cannot be
 * constructed off a device.
 */
class PendingRefreshOrder {

    private val lock = Any()
    private var latest = 0L

    /** Takes the next generation number. Call once per read, before the request. */
    fun begin(): Long = synchronized(lock) { ++latest }

    /**
     * Runs [apply] only if [token] is still the newest generation.
     *
     * @return true when it ran, false when a newer read has started and this
     *   response must be dropped.
     */
    fun applyIfLatest(token: Long, apply: () -> Unit): Boolean =
        synchronized(lock) {
            if (token != latest) {
                false
            } else {
                apply()
                true
            }
        }
}
