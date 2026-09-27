package com.jarvis.client

import com.jarvis.client.data.FloatingAvatarMode
import com.jarvis.client.data.floatingAvatarShowsContent
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** "Floating Jarvis" (data/FloatingAvatar.kt): the three-state setting and
 *  what App lock does to what the avatar may show. */
class FloatingAvatarTest {

    @Test
    fun `off is the default`() {
        assertEquals(FloatingAvatarMode.OFF, FloatingAvatarMode.fromWire(null))
        assertEquals(FloatingAvatarMode.OFF, FloatingAvatarMode.fromWire("nonsense"))
    }

    @Test
    fun `every mode round-trips through its wire value`() {
        for (mode in FloatingAvatarMode.entries) {
            assertEquals(mode, FloatingAvatarMode.fromWire(mode.wire))
        }
    }

    @Test
    fun `wire values are stable and distinct`() {
        val wires = FloatingAvatarMode.entries.map { it.wire }
        assertEquals(wires.toSet().size, wires.size)
        assertEquals(setOf("off", "bubble", "overlay"), wires.toSet())
    }

    @Test
    fun `app lock does not change what the avatar shows (owner's decision, 2026-09-27)`() {
        // Cross-cutting audit finding #7: matches the desktop's own
        // floating face, which keeps showing link/approval/error state
        // regardless of App lock.
        assertTrue(floatingAvatarShowsContent(appLockOn = true))
        assertTrue(floatingAvatarShowsContent(appLockOn = false))
    }
}
