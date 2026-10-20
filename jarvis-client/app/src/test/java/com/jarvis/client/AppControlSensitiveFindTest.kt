package com.jarvis.client

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * 2026-10-20 audit, Part I catch 3: `find()` was the one accessibility path
 * still skipping only `node.isPassword`, while `snapshot()`, `tap()` and
 * `type()` already used the wider `sensitive(node)` helper (isPassword OR a
 * password input type OR isAccessibilityDataSensitive). A visible-password
 * field or a data-sensitive subtree could therefore be traversed by a tap by
 * label. This is a SOURCE test, like the other phone contract tests: there is
 * no Android SDK in this container, so CI's Gradle build is the first compile,
 * and nothing here claims the UI was driven on a phone.
 */
class AppControlSensitiveFindTest {

    private fun source(): String = listOf(
        File("src/main/java/com/jarvis/client/service/JarvisAccessibilityService.kt"),
        File("app/src/main/java/com/jarvis/client/service/JarvisAccessibilityService.kt"),
    ).first { it.isFile }.readText()

    @Test
    fun findSkipsEverySensitiveNodeNotOnlyPasswordOnes() {
        val text = source()
        val find = text.substringAfter("private fun find(")
            .substringBefore("private fun ", missingDelimiterValue = text.substringAfter("private fun find("))
        assertTrue(
            "find() must skip anything sensitive(node) calls sensitive",
            find.contains("if (sensitive(node)) continue"),
        )
        assertFalse(
            "find() must not fall back to the password flag alone",
            find.contains("if (node.isPassword) continue"),
        )
        assertTrue(
            "the shared helper must still cover the wider Android checks",
            text.contains("isAccessibilityDataSensitive") && text.contains("passwordInputType"),
        )
    }
}
