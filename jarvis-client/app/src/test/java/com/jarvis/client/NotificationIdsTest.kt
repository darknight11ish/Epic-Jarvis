package com.jarvis.client

import com.jarvis.client.service.NotificationIds
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Two notifications with the same number replace each other and are cancelled
 * together (the chatbot line and "Hey Jarvis is off" once shared 0x3200; the
 * wake-word and screen-watch services shared 0x4A57). Every id lives in
 * [NotificationIds], and none may repeat.
 */
class NotificationIdsTest {

    @Test
    fun `no two notification ids are the same`() {
        val byId = NotificationIds.ALL.groupBy({ it.second }, { it.first })
        val clashes = byId.filterValues { it.size > 1 }
        assertTrue("ids used twice: $clashes", clashes.isEmpty())
    }

    @Test
    fun `every id constant is in the list`() {
        // The object's own constants, read by reflection, must all be in ALL.
        val declared = NotificationIds::class.java.declaredFields
            .filter { it.type == Int::class.javaPrimitiveType && java.lang.reflect.Modifier.isStatic(it.modifiers) }
            .map { it.name }
            .toSet()
        val listed = NotificationIds.ALL.map { it.first }.toSet()
        assertEquals("a constant is missing from ALL", declared, listed)
    }

    @Test
    fun `everything but the approval range sits below its first number`() {
        for ((name, id) in NotificationIds.ALL) {
            if (name == "APPROVAL_FIRST") continue
            assertTrue("$name ($id) must stay below the approval range", id < NotificationIds.APPROVAL_FIRST)
        }
    }
}
