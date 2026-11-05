package com.jarvis.client.net

import kotlin.math.roundToLong

/**
 * Attention-first sorting for the Work pane (2026-11-04, pattern 4 of the
 * owner-forwarded `gemini_rulings_1253_and_superagent_spec_2026_11_04.md`).
 *
 * The phone's half of the same idea as the desktop's `src/attention.js`, and
 * the ONE place on this platform where the question is answered. A jobs list
 * that treats every background job equally makes healthy work look like work
 * the owner must look at; so the screen is split in two:
 *
 *  * **"Needs you"** - a person has to decide, answer, retry or read a failure.
 *    Shown expanded, with the job's own action. When it is empty it is not
 *    drawn AT ALL, so it costs zero pixels (the screen does not reserve a box
 *    for an absence).
 *  * **"Quiet / healthy"** - everything else, folded into ONE line until the
 *    owner taps it.
 *
 * ## The contract
 *
 * [waitsForPerson] is TRUE only when a human decision, an answer or an
 * unacknowledged failure is what the job is waiting on:
 *
 *     state in ("waiting_approval", "blocked", "needs_input")
 *     or (state == "failed" and not dismissed_by_owner)
 *
 * The PC may send the answer itself in a per-job `waits_for_person` boolean
 * ([JobRecord.waitsForPerson]); when it does, that boolean WINS, because the
 * server knows things this file cannot see. When it is absent - every backend
 * shipped before 2026-11-04 - the derivation above is used, so the pane looks
 * right against an older PC rather than broken. A `null` field is not the same
 * fact as `false`, which is why the model keeps it nullable.
 *
 * ## What this file deliberately does not do
 *
 * It approves nothing, adds no action and starts no polling: it only groups a
 * list a read already returned and writes one sentence about it. The one
 * existing refresh path redraws the screen; nothing here schedules a tick.
 *
 * Pure Kotlin, so `AttentionFirstTest.kt` pins the truth table, the stable
 * order and the one-line summary on the JVM without a running app.
 */
object JobAttention {

    /** The section heading the owner reads. The desktop draws the same words. */
    const val NEEDS_HEAD = "Needs you"

    /** The collapsed bar's own name. The desktop draws the same words. */
    const val QUIET_HEAD = "Quiet / healthy"

    /** What the bar's trailing hint says, closed and open. */
    const val SHOW = "Show"
    const val HIDE = "Hide"

    /** The screen-reader state of the fold, the peer of the desktop's `aria-expanded`. */
    const val EXPANDED = "Expanded"
    const val COLLAPSED = "Collapsed"

    /** The states that ALWAYS wait for a person, by the spec's own list. */
    val NEEDS_PERSON_STATES: Set<String> = setOf("waiting_approval", "blocked", "needs_input")

    /**
     * True only when the job is waiting on a person. See the object note for
     * the contract and for why the server's own boolean, when present, wins.
     */
    fun waitsForPerson(job: JobRecord): Boolean {
        job.waitsForPerson?.let { return it }
        val state = job.state.trim()
        if (state in NEEDS_PERSON_STATES) return true
        // A failure the owner has already put aside is not still asking for
        // him. The model's `false` default is deliberate: a malformed payload
        // must never HIDE a failure.
        return state == "failed" && !job.dismissedByOwner
    }

    /** The two sections, in the payload's own order on both sides. */
    data class Split(
        val needs: List<JobRecord>,
        val quiet: List<JobRecord>,
    )

    /**
     * Stable partition: the jobs that wait for a person, then everything else.
     * Neither list is re-sorted, so a row never jumps position between two
     * reads of the same answer.
     */
    fun partition(jobs: List<JobRecord>): Split {
        val needs = ArrayList<JobRecord>()
        val quiet = ArrayList<JobRecord>()
        for (job in jobs) {
            (if (waitsForPerson(job)) needs else quiet).add(job)
        }
        return Split(needs = needs, quiet = quiet)
    }

    /** Whole words for an age, the same shape the desktop's `attention.js` uses. */
    fun agoWords(epochSeconds: Long, nowSeconds: Long): String {
        if (epochSeconds <= 0L) return ""
        val seconds = (nowSeconds - epochSeconds).coerceAtLeast(0L)
        return when {
            seconds < 45 -> "just now"
            seconds < 3600 -> "${(seconds / 60.0).roundToLong().coerceAtLeast(1)}m ago"
            seconds < 86400 -> "${(seconds / 3600.0).roundToLong()}h ago"
            else -> "${(seconds / 86400.0).roundToLong()}d ago"
        }
    }

    /**
     * The collapsed bar's ONE line, and only facts the payload supports:
     *
     *     Quiet / healthy · 3 background jobs — 1 still running, 2 finished · last finished 5m ago
     *
     * A count is printed only when it is non-zero, and "last finished" only
     * when a row really carries a finish time. Being in the quiet half is
     * defined by [waitsForPerson], never by a guess about health.
     */
    fun quietLine(jobs: List<JobRecord>, nowSeconds: Long): String {
        if (jobs.isEmpty()) return ""
        var running = 0
        var done = 0
        var failed = 0
        var cancelled = 0
        var last = 0.0
        for (job in jobs) {
            when (job.state.trim()) {
                "running", "queued" -> running += 1
                "done" -> done += 1
                "failed" -> failed += 1
                "cancelled" -> cancelled += 1
            }
            val finished = job.finished ?: 0.0
            if (finished.isFinite() && finished > last) last = finished
        }
        val bits = ArrayList<String>(4)
        if (running > 0) bits.add("$running still running")
        if (done > 0) bits.add("$done finished")
        if (failed > 0) bits.add("$failed failed")
        if (cancelled > 0) bits.add("$cancelled cancelled")
        val n = jobs.size
        val head = "$QUIET_HEAD · $n background job${if (n == 1) "" else "s"}"
        var line = head
        if (bits.isNotEmpty()) line += " — " + bits.joinToString(", ")
        if (last > 0.0) line += " · last finished " + agoWords(last.toLong(), nowSeconds)
        return line
    }
}
