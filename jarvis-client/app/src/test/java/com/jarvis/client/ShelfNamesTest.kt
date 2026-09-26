package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.JobRecord
import com.jarvis.client.net.UndoEntry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The undo shelf and the job list, in either app's field names.
 *
 * jarvis_undo.py and jarvis_jobs.py live only on the owner's PC, and the two
 * apps guessed different names for the same rows: the phone label / what /
 * reversible / capabilities / private, the desktop action / kind /
 * revertible / caps / tainted / handler. Whichever the server really sends,
 * one app was showing "(action)" and no Undo button. Both apps now read both;
 * the desktop's rows below are its own test fixture's (tests/uikit.mjs).
 */
class ShelfNamesTest {

    private fun undo(json: String) = JarvisJson.decodeFromString(UndoEntry.serializer(), json)
    private fun job(json: String) = JarvisJson.decodeFromString(JobRecord.serializer(), json)

    @Test
    fun anUndoRowInTheDesktopsNamesReads() {
        val e = undo("""{"id":"u1","action":"file_write","target":"C:\\notes.txt","revertible":true,"ts":1700000000}""")
        assertEquals("file_write", e.title)
        assertTrue(e.canRevert)
    }

    @Test
    fun anUndoRowInThePhonesNamesStillReads() {
        val e = undo("""{"id":"u2","label":"Deleted notes.txt","reversible":true,"at_ms":5}""")
        assertEquals("Deleted notes.txt", e.title)
        assertTrue(e.canRevert)
    }

    /** CONTROL: a final row stays final, whichever name says so. */
    @Test
    fun aFinalRowIsNotRevertibleByEitherName() {
        assertFalse(undo("""{"id":"u3","kind":"email_send","revertible":false}""").canRevert)
        assertFalse(undo("""{"id":"u4","label":"Sent","reversible":false}""").canRevert)
        assertEquals("email_send", undo("""{"id":"u3","kind":"email_send"}""").title)
    }

    @Test
    fun aJobInTheDesktopsNamesReads() {
        val j = job("""{"id":"j1","handler":"index","state":"running","caps":["fs.read","memory.write"],"tainted":true,"created":1700000000}""")
        assertEquals("index", j.title)
        assertEquals(listOf("fs.read", "memory.write"), j.frozen)
        assertTrue(j.tainted)
        // `tainted` is not `private`: a different promise, shown differently.
        assertFalse(j.private)
    }

    @Test
    fun aJobInThePhonesNamesStillReads() {
        val j = job("""{"id":"j2","label":"weekly digest","capabilities":["memory.read"],"private":true,"progress":0.5}""")
        assertEquals("weekly digest", j.title)
        assertEquals(listOf("memory.read"), j.frozen)
        assertTrue(j.private)
    }

    @Test
    fun aJobWithNoNameFallsBackToItsId() {
        assertEquals("j3", job("""{"id":"j3"}""").title)
    }
}
