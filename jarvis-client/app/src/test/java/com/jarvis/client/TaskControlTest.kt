package com.jarvis.client

import com.jarvis.client.net.ApiError
import com.jarvis.client.net.TaskControl
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The words the phone shows for the task controls and the card note, held
 * to what the desktop's `backend/task-control.patch` actually does
 * (`backend/jarvis_task_control.py`, `handle_post`).
 */
class TaskControlTest {

    @Test
    fun resumeNeverClaimsToHaveResumed() {
        // The server raises an approval card and runs nothing until it is
        // approved. Anything saying "resumed" would be untrue.
        assertFalse(TaskControl.RESUME_ASKED.contains("resumed", ignoreCase = true))
        assertTrue(TaskControl.RESUME_ASKED.contains("card"))
        assertTrue(TaskControl.RESUME_ASKED.contains("Nothing has run yet"))
    }

    @Test
    fun aCardNoteSaysItDecidedNothing() {
        assertTrue(TaskControl.NOTE_KEPT.contains("Nothing was approved or denied"))
    }

    @Test
    fun resumeOnAStaleLinkPointsAtStop() {
        // Rule 4 holds Resume on a stale link; Stop is never held.
        assertTrue(TaskControl.RESUME_WHILE_STALE.contains("Stop still works"))
    }

    @Test
    fun aConflictOnTheTaskRoutesIsNotAlreadyHandledElsewhere() {
        // On approve/deny a 409 means "someone else answered it". On the task
        // routes it means "nothing to act on" - the server's own reasons.
        val words = TaskControl.failure(ApiError.AlreadyHandled)!!
        assertTrue(words.contains("nothing is running or paused"))
        assertFalse(words.contains("elsewhere"))
    }

    @Test
    fun aConflictOnACardNoteMeansTheCardIsGone() {
        val words = TaskControl.failure(ApiError.AlreadyHandled, amend = true)!!
        assertTrue(words.contains("no longer waiting"))
    }

    @Test
    fun aMissingRouteNamesThePatch() {
        assertTrue(TaskControl.failure(ApiError.NotFound)!!.contains("task-control"))
    }

    @Test
    fun everythingElseFallsBackToTheGenericWording() {
        assertNull(TaskControl.failure(ApiError.BadToken))
        assertNull(TaskControl.failure(ApiError.Server(500, "")))
        assertNull(TaskControl.failure(ApiError.Unreachable("x")))
    }
}
