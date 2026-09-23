package com.jarvis.client

import com.jarvis.client.net.JarvisJson
import com.jarvis.client.net.UndoEntry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * A held message on the undo shelf, read the way the desktop's Brain window
 * reads it (`jarvis-desktop/src/brain.js`, renderUndo): `category: "hold"`
 * with `detail.handle`. Only such an entry gets a Stop sending button.
 */
class HoldEntryTest {

    private fun entry(json: String) = JarvisJson.decodeFromString(UndoEntry.serializer(), json)

    @Test
    fun aHoldWithAHandleIsStoppable() {
        val e = entry("""{"id":"u1","category":"hold","detail":{"handle":"h-42"},"reason":"sends in 20s"}""")
        assertEquals("h-42", e.holdHandle)
    }

    @Test
    fun anythingElseIsNot() {
        assertNull(entry("""{"id":"u2","category":"file","detail":{"handle":"h"}}""").holdHandle)
        assertNull(entry("""{"id":"u3","category":"hold"}""").holdHandle)
        assertNull(entry("""{"id":"u4","category":"hold","detail":{"handle":""}}""").holdHandle)
        assertNull(entry("""{"id":"u5","category":"hold","detail":{"handle":7}}""").holdHandle)
        assertNull(entry("""{"id":"u6","label":"old shape","reversible":true}""").holdHandle)
    }

    @Test
    fun theOldFieldsStillRead() {
        val e = entry("""{"id":"u7","label":"Deleted notes.txt","reversible":true,"at_ms":5}""")
        assertEquals("Deleted notes.txt", e.label)
        assertEquals(true, e.reversible)
    }
}
