package com.jarvis.client

import com.jarvis.client.net.MemoryCards
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Wave-10 Q2.3 (2026-11-08): EVERY fetch of the memory review queue must ask
 * for the "stop using this fact?" cards, or the backend hides them and the
 * phone can never show the Forget card the owner just asked for.
 *
 * The URL with both flags lives in ONE constant, [MemoryCards.PENDING_PATH],
 * and every call site reads it. This guard is on the SOURCE, not one call: a
 * new screen that types the path itself (or a bare `/api/memory/pending`)
 * fails here instead of silently losing `retire_cards=1` - which is exactly
 * how the card would disappear without a word.
 */
class MemoryPendingFlagTest {

    private val client: File = requireNotNull(
        repoFile("jarvis-client/app/src/main/java/com/jarvis/client/net/Learning.kt")
            .parentFile?.parentFile,
    ) { "the client sources were not found above the test's working directory" }

    private fun ktFiles(): List<File> =
        client.walkTopDown().filter { it.isFile && it.extension == "kt" }.toList()

    @Test
    fun `the one queue URL asks for retire cards and the overnight-tidy card`() {
        assertEquals(
            "/api/memory/pending?retire_cards=1&sleep_offer=1",
            MemoryCards.PENDING_PATH,
        )
    }

    @Test
    fun `no call site can fetch the queue without the flags`() {
        // The bare URL may be TYPED as code in one place only: the constant
        // itself. Comments that mention the route (the screens' docs) are not
        // call sites and are ignored here.
        val typedInCode = ktFiles().flatMap { file ->
            file.readLines()
                .map { it.trim() }
                .filter { line ->
                    line.contains("\"/api/memory/pending") &&
                        !line.startsWith("//") && !line.startsWith("*")
                }
                .map { file.name }
        }.distinct().sorted()
        assertEquals(
            "a new raw /api/memory/pending call site appeared - it must use " +
                "MemoryCards.PENDING_PATH so retire_cards=1 is never lost",
            listOf("Learning.kt"),
            typedInCode,
        )

        // REAL fetches go through a probe of the constant. (A screen may also
        // mention the constant in its docs; that is not a call site.)
        val fetches = ktFiles().filter {
            Regex("""probe\(\s*MemoryCards\.PENDING_PATH\s*\)""").containsMatchIn(it.readText())
        }
        assertTrue(
            "no fetch of the review queue uses MemoryCards.PENDING_PATH - how does the queue load?",
            fetches.isNotEmpty(),
        )
        // And no fetch may build the URL itself: that is the line that would
        // silently drop the flags.
        for (file in ktFiles()) {
            assertTrue(
                "${file.name} builds the queue URL itself, which can drop the flags",
                !Regex("""probe\(\s*"/api/memory/pending""").containsMatchIn(file.readText()),
            )
        }
    }
}
