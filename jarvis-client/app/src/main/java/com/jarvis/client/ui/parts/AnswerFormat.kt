package com.jarvis.client.ui.parts

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.ClickableText
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import com.jarvis.client.ui.theme.JarvisType
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalRadii

/**
 * A small, hand-written formatter for Jarvis's answers - bold, italics,
 * inline code, fenced code blocks and simple lists, the shapes a model
 * actually emits (UI-AUDIT-2026-09-26.md item 5). No markdown library: the
 * desktop's own renderer (`jarvis-desktop/src/markdown.js`, tested by
 * `jarvis-desktop/scripts/markdown-test.mjs`) is the reference for what
 * "bold/italic/list/code" should cover, but this is a smaller subset on
 * purpose - headings, tables, block quotes and nested lists stay the
 * desktop's job. The phone only ever needs what fits one screen's width.
 *
 * SECURITY (`critic.md` D1): a markdown link's own words - `[label](url)` -
 * are written by whoever the answer is quoting. Once Jarvis has read an
 * email or a web page, that may not be the owner. So a link's label is
 * never the tappable text; the real address always is. `[Click
 * here](http://evil.example)` renders as a tappable `http://evil.example`,
 * never as "Click here" - the same reason the desktop's `open_external_url`
 * is handed the stashed URL and nothing rewrites it (markdown.js's own
 * comment on stashing URLs before the emphasis passes run).
 *
 * Parsing is plain [Regex] over one already-split paragraph's lines, so
 * every branch below either matches a fixed-width slice of the input or
 * advances the line cursor by at least one line - there is no way for this
 * to spin without consuming input, unlike the desktop's own index-based
 * scanner (which had exactly that bug once, `markdown-test.mjs`'s
 * `previouslyHung` cases).
 */

/** One rendered piece of an answer. */
internal sealed class AnswerBlock {
    /** Plain prose, already unwrapped to one line - `renderInline` applies. */
    data class Paragraph(val text: String) : AnswerBlock()

    /** One list line. `marker` is the raw bullet/number, e.g. "-" or "2.". */
    data class ListLine(val ordered: Boolean, val marker: String, val text: String) : AnswerBlock()

    /** A fenced code block. `language` is the fence's info word, or null. */
    data class Code(val text: String, val language: String?) : AnswerBlock()
}

private val FENCE = Regex("""^\s*(`{3,}|~{3,})\s*(\S*).*$""")
private val LIST_MARKER = Regex("""^(\s*)([-*+]|\d+[.)])\s+(.*)$""")

/**
 * Splits one paragraph chunk (as already split on blank lines by the
 * caller - see `HomeScreen.kt`'s `PARAGRAPH_BREAK`) into blocks: a run of
 * list-marker lines becomes a list, a fence becomes a code block (closed or
 * not - an unclosed fence is exactly what a live stream looks like before
 * the closing marker has arrived), and everything else is joined into one
 * paragraph the way the desktop's own paragraph branch does.
 */
internal fun parseAnswerBlocks(chunk: String): List<AnswerBlock> {
    val lines = chunk.replace("\r\n", "\n").split("\n")
    val blocks = mutableListOf<AnswerBlock>()
    val paragraph = mutableListOf<String>()
    fun flushParagraph() {
        if (paragraph.isNotEmpty()) {
            blocks += AnswerBlock.Paragraph(paragraph.joinToString(" "))
            paragraph.clear()
        }
    }

    var index = 0
    while (index < lines.size) {
        val line = lines[index]

        val fence = FENCE.matchEntire(line)
        if (fence != null) {
            flushParagraph()
            val markerChar = fence.groupValues[1][0]
            val markerLen = fence.groupValues[1].length
            val language = fence.groupValues[2].takeIf { it.isNotBlank() }
            val closer = Regex("^\\s*$markerChar{$markerLen,}\\s*$")
            val body = mutableListOf<String>()
            index += 1
            while (index < lines.size && !closer.matches(lines[index])) {
                body += lines[index]
                index += 1
            }
            index += 1 // the closing fence, if a stream has delivered one yet
            blocks += AnswerBlock.Code(body.joinToString("\n"), language)
            continue
        }

        if (line.isBlank()) {
            flushParagraph()
            index += 1
            continue
        }

        val item = LIST_MARKER.matchEntire(line)
        if (item != null) {
            flushParagraph()
            val marker = item.groupValues[2]
            blocks += AnswerBlock.ListLine(
                ordered = marker.any { it.isDigit() },
                marker = marker,
                text = item.groupValues[3],
            )
            index += 1
            continue
        }

        paragraph += line.trim()
        index += 1
    }
    flushParagraph()
    return blocks
}

/** The tag [AnnotatedString.getStringAnnotations] looks up a tapped link's real address under. */
private const val URL_TAG = "answer-url"

/**
 * Inline spans within one block's text: bold, italic, inline code and
 * links. Matches the desktop's `renderInline` (`markdown.js`) as closely as
 * a flat (non-nested) pass can: `***x***` before `**x**` before `__x__`
 * before `*x*`, `__` guarded against splitting an identifier
 * (`user__name__id`, the same case markdown.js's own test list carries),
 * and `*` guarded against ordinary arithmetic (`a * b`). Nesting - `**bold
 * *and italic* tail**` - is the one thing dropped from the desktop's
 * version, to keep this a single non-recursive pass; a model answer that
 * relies on nested emphasis shows its outer pair only.
 *
 * A markdown link's destination is shown and made tappable; its label is
 * read and discarded - see this file's header comment.
 */
private val INLINE_TOKEN = Regex(
    """\*\*\*(.+?)\*\*\*""" +
        """|\*\*(.+?)\*\*""" +
        """|(?<!\w)__(.+?)__(?!\w)""" +
        """|(?<![*\w])\*(?!\s)([^*\n]+?)\*""" +
        """|`([^`\n]+)`""" +
        """|\[([^\]]*)\]\((https?://[^\s)]+)\)""" +
        """|(?<![\w/])(https?://[^\s)]+)"""
)

internal fun formatInline(raw: String, textColor: Color, codeBackground: Color): AnnotatedString =
    buildAnnotatedString {
        var last = 0
        for (match in INLINE_TOKEN.findAll(raw)) {
            append(raw, last, match.range.first)
            val groups = match.groups
            when {
                groups[1] != null -> withStyle(
                    SpanStyle(fontWeight = FontWeight.Bold, fontStyle = FontStyle.Italic),
                ) { append(groups[1]!!.value) }
                groups[2] != null -> withStyle(SpanStyle(fontWeight = FontWeight.Bold)) {
                    append(groups[2]!!.value)
                }
                groups[3] != null -> withStyle(SpanStyle(fontWeight = FontWeight.Bold)) {
                    append(groups[3]!!.value)
                }
                groups[4] != null -> withStyle(SpanStyle(fontStyle = FontStyle.Italic)) {
                    append(groups[4]!!.value)
                }
                groups[5] != null -> withStyle(
                    SpanStyle(fontFamily = FontFamily.Monospace, background = codeBackground),
                ) { append(groups[5]!!.value) }
                // A markdown link: group 6 is the label and is never shown -
                // only group 7, the real destination, both as the visible
                // text and as the tappable annotation.
                groups[7] != null -> {
                    val url = groups[7]!!.value
                    pushStringAnnotation(URL_TAG, url)
                    withStyle(SpanStyle(textDecoration = TextDecoration.Underline)) { append(url) }
                    pop()
                }
                groups[8] != null -> {
                    val url = groups[8]!!.value
                    pushStringAnnotation(URL_TAG, url)
                    withStyle(SpanStyle(textDecoration = TextDecoration.Underline)) { append(url) }
                    pop()
                }
                else -> append(match.value)
            }
            last = match.range.last + 1
        }
        append(raw, last, raw.length)
        // The whole thing is one colour by default - only the spans above
        // override it - so a caller's base text colour still applies.
        addStyle(SpanStyle(color = textColor), 0, length)
    }

/**
 * Renders one already-split answer chunk with real formatting, in place of
 * the plain `Text` this replaces in `HomeScreen.kt`. `style`/`color` are the
 * same ones the plain `Text` used, so wrapping an existing call site changes
 * only what is inside it.
 */
@Composable
fun FormattedAnswer(
    text: String,
    modifier: Modifier = Modifier,
    style: TextStyle = MaterialTheme.typography.bodyLarge,
    color: Color = LocalChrome.current.textHi,
) {
    val chrome = LocalChrome.current
    val uriHandler = LocalUriHandler.current
    val radii = LocalRadii.current
    val blocks = remember(text) { parseAnswerBlocks(text) }
    val onLinkTap: (AnnotatedString, Int) -> Unit = { annotated, offset ->
        annotated.getStringAnnotations(URL_TAG, offset, offset).firstOrNull()?.let {
            uriHandler.openUri(it.item)
        }
    }
    Column(modifier) {
        blocks.forEachIndexed { index, block ->
            if (index > 0) Spacer(Modifier.height(6.dp))
            when (block) {
                is AnswerBlock.Paragraph -> {
                    val annotated = remember(block.text, color) {
                        formatInline(block.text, color, chrome.surface2)
                    }
                    ClickableText(
                        text = annotated,
                        style = style.copy(color = color),
                        onClick = { onLinkTap(annotated, it) },
                    )
                }
                is AnswerBlock.ListLine -> {
                    Row(Modifier.fillMaxWidth()) {
                        Text(
                            if (block.ordered) block.marker.trimEnd('.', ')') + "." else "•",
                            style = style.copy(color = color),
                            modifier = Modifier.width(22.dp),
                        )
                        val annotated = remember(block.text, color) {
                            formatInline(block.text, color, chrome.surface2)
                        }
                        ClickableText(
                            text = annotated,
                            style = style.copy(color = color),
                            modifier = Modifier.weight(1f),
                            onClick = { onLinkTap(annotated, it) },
                        )
                    }
                }
                is AnswerBlock.Code -> {
                    Box(
                        Modifier
                            .fillMaxWidth()
                            .clip(radii.controlShape)
                            .background(chrome.surface2)
                            .padding(10.dp),
                    ) {
                        Text(block.text, style = JarvisType.machine, color = color)
                    }
                }
            }
        }
    }
}
