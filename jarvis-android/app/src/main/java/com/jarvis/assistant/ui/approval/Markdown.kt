package com.jarvis.assistant.ui.approval

/**
 * A deliberately small Markdown subset: what note-taking apps actually emit.
 *
 * Pulling in a full CommonMark renderer would add a dependency and a lot of
 * surface for content that arrives as headings, emphasis, lists, links and
 * fenced code. Anything unrecognised falls through as literal text rather than
 * being dropped, so an unsupported construct is still readable.
 *
 * Parsing is pure Kotlin and produces no Compose types, keeping it unit testable.
 */

sealed interface MdBlock {
    data class Heading(val level: Int, val spans: List<MdSpan>) : MdBlock
    data class Paragraph(val spans: List<MdSpan>) : MdBlock
    data class ListItem(val indent: Int, val marker: String, val spans: List<MdSpan>) : MdBlock
    data class Quote(val spans: List<MdSpan>) : MdBlock
    data class CodeBlock(val language: String?, val code: String) : MdBlock
    data object Divider : MdBlock
}

/** An inline run of text with any combination of emphases applied. */
data class MdSpan(
    val text: String,
    val bold: Boolean = false,
    val italic: Boolean = false,
    val code: Boolean = false,
    val strike: Boolean = false,
    val link: String? = null,
)

object Markdown {

    private val HEADING = Regex("""^(#{1,6})\s+(.*)$""")
    private val BULLET = Regex("""^(\s*)[-*+]\s+(.*)$""")
    private val ORDERED = Regex("""^(\s*)(\d{1,3})[.)]\s+(.*)$""")
    private val QUOTE = Regex("""^\s*>\s?(.*)$""")
    private val DIVIDER = Regex("""^\s*([-*_])\s*(\1\s*){2,}$""")
    private val FENCE = Regex("""^\s*```\s*(\S+)?\s*$""")

    /** Logseq bullets carry `id::`/`collapsed::` metadata that is noise here. */
    private val LOGSEQ_PROPERTY = Regex("""^\s*[a-zA-Z][\w-]*::\s?.*$""")

    fun parse(source: String): List<MdBlock> {
        val blocks = mutableListOf<MdBlock>()
        val lines = source.replace("\r\n", "\n").split('\n')
        val paragraph = StringBuilder()

        fun flushParagraph() {
            if (paragraph.isNotEmpty()) {
                blocks += MdBlock.Paragraph(parseInline(paragraph.toString().trim()))
                paragraph.setLength(0)
            }
        }

        var index = 0
        while (index < lines.size) {
            val line = lines[index]

            val fence = FENCE.matchEntire(line)
            if (fence != null) {
                flushParagraph()
                val language = fence.groupValues[1].takeIf { it.isNotBlank() }
                val body = StringBuilder()
                index++
                while (index < lines.size && FENCE.matchEntire(lines[index]) == null) {
                    body.appendLine(lines[index])
                    index++
                }
                index++ // closing fence, or past the end for an unterminated block
                blocks += MdBlock.CodeBlock(language, body.toString().trimEnd('\n'))
                continue
            }

            when {
                line.isBlank() -> flushParagraph()

                LOGSEQ_PROPERTY.matches(line) -> Unit

                DIVIDER.matches(line) -> {
                    flushParagraph()
                    blocks += MdBlock.Divider
                }

                HEADING.matches(line) -> {
                    flushParagraph()
                    val (hashes, text) = HEADING.find(line)!!.destructured
                    blocks += MdBlock.Heading(hashes.length, parseInline(text.trim()))
                }

                QUOTE.matches(line) -> {
                    flushParagraph()
                    blocks += MdBlock.Quote(parseInline(QUOTE.find(line)!!.groupValues[1]))
                }

                BULLET.matches(line) -> {
                    flushParagraph()
                    val (indent, text) = BULLET.find(line)!!.destructured
                    blocks += MdBlock.ListItem(indent.length / 2, "•", parseInline(text))
                }

                ORDERED.matches(line) -> {
                    flushParagraph()
                    val (indent, number, text) = ORDERED.find(line)!!.destructured
                    blocks += MdBlock.ListItem(indent.length / 2, "$number.", parseInline(text))
                }

                else -> {
                    if (paragraph.isNotEmpty()) paragraph.append(' ')
                    paragraph.append(line.trim())
                }
            }
            index++
        }
        flushParagraph()
        return blocks
    }

    /**
     * Scans for `**bold**`, `*italic*`, `` `code` ``, `~~strike~~` and
     * `[text](url)`. An unmatched marker stays literal rather than swallowing
     * the rest of the line.
     */
    fun parseInline(source: String): List<MdSpan> {
        if (source.isEmpty()) return listOf(MdSpan(""))
        val spans = mutableListOf<MdSpan>()
        val literal = StringBuilder()
        var bold = false
        var italic = false
        var strike = false
        var i = 0

        fun flush() {
            if (literal.isNotEmpty()) {
                spans += MdSpan(literal.toString(), bold = bold, italic = italic, strike = strike)
                literal.setLength(0)
            }
        }

        while (i < source.length) {
            val rest = source.length - i
            val char = source[i]

            // Inline code wins over emphasis: markers inside it are literal.
            if (char == '`') {
                val close = source.indexOf('`', i + 1)
                if (close > i) {
                    flush()
                    spans += MdSpan(source.substring(i + 1, close), code = true)
                    i = close + 1
                    continue
                }
            }

            if (char == '[') {
                val closeText = source.indexOf(']', i + 1)
                if (closeText > i && closeText + 1 < source.length && source[closeText + 1] == '(') {
                    val closeUrl = source.indexOf(')', closeText + 2)
                    if (closeUrl > closeText) {
                        flush()
                        spans += MdSpan(
                            text = source.substring(i + 1, closeText),
                            bold = bold,
                            italic = italic,
                            link = source.substring(closeText + 2, closeUrl),
                        )
                        i = closeUrl + 1
                        continue
                    }
                }
            }

            if (rest >= 2 && source.startsWith("**", i)) {
                if (bold || source.indexOf("**", i + 2) > 0) {
                    flush(); bold = !bold; i += 2; continue
                }
            }
            if (rest >= 2 && source.startsWith("~~", i)) {
                if (strike || source.indexOf("~~", i + 2) > 0) {
                    flush(); strike = !strike; i += 2; continue
                }
            }
            if (char == '*' || char == '_') {
                val hasCloser = italic || source.indexOf(char, i + 1) > 0
                if (hasCloser) {
                    flush(); italic = !italic; i += 1; continue
                }
            }

            literal.append(char)
            i++
        }
        flush()
        return spans.ifEmpty { listOf(MdSpan(source)) }
    }

    /** Plain text, for notification bodies where styling is unavailable. */
    fun toPlainText(source: String): String = parse(source).joinToString("\n") { block ->
        when (block) {
            is MdBlock.Heading -> block.spans.joinToString("") { it.text }
            is MdBlock.Paragraph -> block.spans.joinToString("") { it.text }
            is MdBlock.ListItem -> "${block.marker} " + block.spans.joinToString("") { it.text }
            is MdBlock.Quote -> "> " + block.spans.joinToString("") { it.text }
            is MdBlock.CodeBlock -> block.code
            MdBlock.Divider -> "—"
        }
    }
}
