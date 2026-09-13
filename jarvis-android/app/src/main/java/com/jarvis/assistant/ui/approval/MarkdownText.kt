package com.jarvis.assistant.ui.approval

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.assistant.ui.theme.JarvisCyan
import com.jarvis.assistant.ui.theme.JarvisOutline
import com.jarvis.assistant.ui.theme.JarvisSurface
import com.jarvis.assistant.ui.theme.JarvisTextMuted
import com.jarvis.assistant.ui.theme.JarvisTextPrimary

/** Renders the parsed Markdown subset. */
@Composable
fun MarkdownText(source: String, modifier: Modifier = Modifier) {
    val blocks = remember(source) { Markdown.parse(source) }

    Column(modifier) {
        blocks.forEachIndexed { index, block ->
            if (index > 0) Spacer(Modifier.height(6.dp))
            when (block) {
                is MdBlock.Heading -> Text(
                    text = block.spans.toAnnotated(),
                    style = MaterialTheme.typography.titleMedium.copy(
                        fontSize = when (block.level) {
                            1 -> 19.sp
                            2 -> 17.sp
                            else -> 15.sp
                        },
                        fontWeight = FontWeight.SemiBold,
                    ),
                    color = JarvisTextPrimary,
                )

                is MdBlock.Paragraph -> Text(
                    text = block.spans.toAnnotated(),
                    style = MaterialTheme.typography.bodyMedium,
                    color = JarvisTextPrimary,
                )

                is MdBlock.ListItem -> Row(
                    modifier = Modifier.padding(start = (block.indent * 14).dp),
                ) {
                    Text(
                        text = block.marker,
                        style = MaterialTheme.typography.bodyMedium,
                        color = JarvisCyan,
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        text = block.spans.toAnnotated(),
                        style = MaterialTheme.typography.bodyMedium,
                        color = JarvisTextPrimary,
                    )
                }

                is MdBlock.Quote -> Row {
                    Spacer(
                        Modifier
                            .width(3.dp)
                            .height(18.dp)
                            .background(JarvisCyan, RoundedCornerShape(2.dp)),
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        text = block.spans.toAnnotated(),
                        style = MaterialTheme.typography.bodyMedium,
                        color = JarvisTextMuted,
                    )
                }

                is MdBlock.CodeBlock -> Column(
                    Modifier
                        .fillMaxWidth()
                        .background(JarvisSurface, RoundedCornerShape(8.dp))
                        .padding(10.dp),
                ) {
                    block.language?.let {
                        Text(it, style = MaterialTheme.typography.labelSmall, color = JarvisTextMuted)
                        Spacer(Modifier.height(4.dp))
                    }
                    // Code must not reflow; a wrapped shell command reads as a
                    // different command.
                    Text(
                        text = block.code,
                        modifier = Modifier.horizontalScroll(rememberScrollState()),
                        style = MaterialTheme.typography.bodyMedium.copy(
                            fontFamily = FontFamily.Monospace,
                            fontSize = 12.sp,
                        ),
                        color = JarvisTextPrimary,
                        softWrap = false,
                    )
                }

                MdBlock.Divider -> HorizontalDivider(color = JarvisOutline)
            }
        }
    }
}

fun List<MdSpan>.toAnnotated(): AnnotatedString = buildAnnotatedString {
    this@toAnnotated.forEach { span ->
        val style = SpanStyle(
            fontWeight = if (span.bold) FontWeight.SemiBold else null,
            fontStyle = if (span.italic) FontStyle.Italic else null,
            fontFamily = if (span.code) FontFamily.Monospace else null,
            color = if (span.code || span.link != null) JarvisCyan else JarvisTextPrimary,
            textDecoration = when {
                span.strike -> TextDecoration.LineThrough
                span.link != null -> TextDecoration.Underline
                else -> null
            },
        )
        withStyle(style) { append(span.text) }
    }
}
