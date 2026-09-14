package com.jarvis.assistant

import com.jarvis.assistant.ui.approval.DiffKind
import com.jarvis.assistant.ui.approval.Markdown
import com.jarvis.assistant.ui.approval.MdBlock
import com.jarvis.assistant.ui.approval.NoteDiff
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class NoteDiffTest {

    @Test
    fun `identical documents produce no changes`() {
        val lines = NoteDiff.between("a\nb\nc", "a\nb\nc")
        assertTrue(NoteDiff.summarize(lines).isEmpty)
    }

    @Test
    fun `a single edited line is one addition and one removal`() {
        val lines = NoteDiff.between("one\ntwo\nthree", "one\nTWO\nthree")
        val summary = NoteDiff.summarize(lines)
        assertEquals(1, summary.added)
        assertEquals(1, summary.removed)
        assertTrue(lines.any { it.kind == DiffKind.ADDED && it.text == "TWO" })
        assertTrue(lines.any { it.kind == DiffKind.REMOVED && it.text == "two" })
    }

    @Test
    fun `appended lines are additions only`() {
        val lines = NoteDiff.between("a", "a\nb\nc")
        val summary = NoteDiff.summarize(lines)
        assertEquals(2, summary.added)
        assertEquals(0, summary.removed)
    }

    /** A one-line change in a long note must not render the whole note. */
    @Test
    fun `long unchanged runs collapse into a gap marker`() {
        val before = (1..80).joinToString("\n") { "line $it" }
        val after = before.replace("line 40", "line forty")
        val lines = NoteDiff.between(before, after)

        assertTrue(lines.any { it.kind == DiffKind.GAP })
        assertTrue("rendered ${lines.size} rows for an 80-line note", lines.size < 20)
    }

    @Test
    fun `oversized documents degrade to a whole-body replacement`() {
        val before = (1..NoteDiff.MAX_LINES + 5).joinToString("\n") { "a$it" }
        val after = (1..NoteDiff.MAX_LINES + 5).joinToString("\n") { "b$it" }
        val lines = NoteDiff.between(before, after)
        assertTrue(lines.none { it.kind == DiffKind.CONTEXT })
    }

    @Test
    fun `unified diff from the desktop is parsed`() {
        val lines = NoteDiff.fromUnified(
            """
            --- a/note.md
            +++ b/note.md
            @@ -1,3 +1,3 @@
             keep
            -gone
            +added
            """.trimIndent(),
        )
        val summary = NoteDiff.summarize(lines)
        assertEquals(1, summary.added)
        assertEquals(1, summary.removed)
        assertTrue(lines.none { it.text.startsWith("+++") || it.text.startsWith("---") })
    }

    @Test
    fun `a desktop-supplied diff wins over reconstructing one`() {
        val chosen = NoteDiff.forPayload(
            diff = "@@\n+from desktop",
            before = "x",
            after = "y",
        )
        assertTrue(chosen!!.any { it.text == "from desktop" })
    }

    @Test
    fun `markdown parses the constructs notes actually use`() {
        val blocks = Markdown.parse(
            """
            # Heading
            Some **bold** and `code`.

            - first
            - second

            ```kotlin
            val x = 1
            ```
            """.trimIndent(),
        )
        assertTrue(blocks.any { it is MdBlock.Heading && it.level == 1 })
        assertTrue(blocks.any { it is MdBlock.CodeBlock && it.language == "kotlin" })
        assertEquals(2, blocks.count { it is MdBlock.ListItem })

        val paragraph = blocks.filterIsInstance<MdBlock.Paragraph>().first()
        assertTrue(paragraph.spans.any { it.bold && it.text == "bold" })
        assertTrue(paragraph.spans.any { it.code && it.text == "code" })
    }

    /** An unmatched marker must stay literal, not swallow the rest of the line. */
    @Test
    fun `unbalanced emphasis does not eat the line`() {
        val spans = Markdown.parseInline("2 * 3 is six")
        assertEquals("2 * 3 is six", spans.joinToString("") { it.text })
    }

    @Test
    fun `logseq block properties are dropped`() {
        val blocks = Markdown.parse("- a task\n  id:: 66f1-2b\n  collapsed:: true")
        assertEquals(1, blocks.size)
    }
}
