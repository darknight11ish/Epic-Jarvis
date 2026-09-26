package com.jarvis.client.net

/**
 * Following a job the desktop is still running - a note waiting for its
 * approval card ([NoteCapture]), a wiki document being read ([Wiki]) - by
 * asking about it every few seconds.
 *
 * The follow used to end for good at the FIRST failed poll, with "Lost track
 * of it". On a phone that is a normal event, not a verdict: one request
 * timing out in a lift, or the private network re-connecting after the
 * screen went off, and the owner was told to go and check the desktop for a
 * job that was fine. Now:
 *
 * - while the link to the desktop is down, polls are skipped and the follow
 *   carries on ([shouldPoll]); nothing is asked of a desktop that cannot be
 *   reached, and nothing is concluded from not reaching it;
 * - a failed poll is only the end after [TOLERATED_FAILURES] in a row
 *   ([failed]); any answer in between resets the count ([answered]).
 *
 * The overall time limit each job already has (`GIVE_UP_MS`) still applies,
 * so a desktop that never comes back does not keep this going for ever.
 * One instance per job; not shared between threads.
 */
class JobFollow(private val tolerate: Int = TOLERATED_FAILURES) {

    private var failuresInARow = 0

    /** Whether to ask this time round. False while the link is down: skip, keep following. */
    fun shouldPoll(linkUp: Boolean): Boolean = linkUp

    /** A poll came back with an answer. */
    fun answered() {
        failuresInARow = 0
    }

    /** A poll failed. True when that was one too many in a row, and the follow ends. */
    fun failed(): Boolean {
        failuresInARow++
        return failuresInARow >= tolerate
    }

    companion object {
        /** Failed polls in a row before the follow gives up. */
        const val TOLERATED_FAILURES = 3
    }
}
