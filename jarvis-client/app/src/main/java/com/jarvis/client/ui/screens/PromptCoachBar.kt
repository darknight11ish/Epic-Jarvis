package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.LinkState
import com.jarvis.client.net.ChatHistory
import com.jarvis.client.net.PromptCoach
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Rule
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/** The most room the rewritten question gets before it scrolls inside itself. */
private val SUGGESTION_MAX_HEIGHT = 220.dp

/**
 * "Coach this", and the advice panel it opens
 * (docs/PROMPT-COACH-DESIGN.md, docs/JARVIS-API.md section 119). It sits in the
 * chat bar on Home, in the one [Composer] the owner types in - above the
 * message box, so it is beside the thing it coaches.
 *
 * WHAT IT IS. The owner types a question, presses **Coach this**, and the model
 * on their own PC reads it (with the last few turns, so "it" and "that" have an
 * antecedent) and says what is missing: a score, up to four gaps - each with
 * what is missing, why it matters and the smallest fix - the questions it would
 * have to ask, and the same request rewritten.
 *
 * WHAT IT NEVER DOES. It sends nothing. The panel's two buttons are the only
 * way anything leaves it, and both go down the chat's own path: **Send mine**
 * sends the words the owner typed, unchanged; **Send the suggestion** puts the
 * rewrite in the box and sends that. The score is never a gate - a 1 out of 10
 * is still sendable, and the panel offers the same two buttons whatever it
 * says.
 *
 * OFF BY DEFAULT, AND NO BUTTON AT ALL WHEN OFF. The master switch is on Mind
 * ([PromptCoachSection], ui/screens/PromptCoachPlate.kt). Off, or not read yet,
 * nothing here is drawn. A PC with no route at all ([PromptCoach.missing]) gets
 * [PromptCoach.MISSING] above the box instead - the owner asked for a feature
 * their PC cannot serve, and a button that would 404 is worse than a sentence
 * saying why.
 *
 * A REFUSAL IS THE PC'S OWN SENTENCE. The module refuses in words - too short
 * to coach, the switch off on the PC, no model found, the model silent, the
 * address not this PC - and every one of those is shown as it arrived
 * ([PromptCoach.Read.Refused]). Only a transport failure (the link down, a bad
 * token) goes through [JarvisRuntime.coach]'s own plain-words plumbing, and
 * even that never leaves an empty panel: the panel is drawn only when there is
 * something in it.
 *
 * @param draft the words in the box, read as a lambda so a keystroke does not
 *   recompose this (the composer's own reason for taking it that way).
 * @param view what the PC last said about the coach, or null before it
 *   answered. Off, and unanswered, both draw nothing.
 * @param thread the conversation above the box, from [HomeState.thread] -
 *   memory only, and never kept by the coach.
 * @param link the link, so the button is offered only while the PC can be
 *   reached. NOT the stale guard: see [JarvisRuntime.coach].
 * @param shared whether text shared from another app is held for the next
 *   question. While it is, the coach stands down - "Send the suggestion"
 *   cannot clear that text the way the ordinary Send does, so a coached send
 *   would carry words the owner was not looking at.
 * @param sendMine sends what is in the box as it is - which, while the panel is
 *   drawn, is exactly the text that was coached (`current` above).
 * @param sendSuggestion puts this rewrite in the box and sends it.
 */
@Composable
internal fun PromptCoachBar(
    draft: () -> String,
    view: PromptCoach.View?,
    thread: List<ChatHistory.Exchange>,
    link: LinkState,
    shared: Boolean,
    streaming: Boolean,
    sendMine: () -> Unit,
    sendSuggestion: (String) -> Unit,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()

    // The panel's own contents, and the words it was opened for. `coachedText`
    // is kept rather than re-read from `draft` so the panel can be dropped the
    // moment those words change (see `current` below).
    var coaching by remember { mutableStateOf(false) }
    var critique by remember { mutableStateOf<PromptCoach.Critique?>(null) }
    var refusal by remember { mutableStateOf<String?>(null) }
    var coachedText by remember { mutableStateOf("") }

    fun close() {
        critique = null
        refusal = null
        coachedText = ""
    }

    val v = view
    // Off, or not read yet: no button, no line, nothing at all. The switch's
    // own screen is where "off" is explained.
    if (v == null || v.on) return

    if (!v.routeKnown) {
        // The PC answered that it has no prompt coach at all. The owner asked
        // for it and it is not there, so say so rather than showing a button
        // that would 404 - and never an empty panel.
        Text(
            PromptCoach.MISSING,
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textMid,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 4.dp)
                .liveStatus(),
        )
        Gap(6)
        return
    }

    // The words in the box, read once here (the same single snapshot read the
    // composer makes), so the button knows whether there is anything to coach.
    val written = draft()
    // Advice read for words that are no longer in the box is advice about a
    // question the owner is not about to ask - and "Send mine" must never send
    // something other than what it coached. So the panel is shown ONLY while
    // the box still holds the words it was read for; typing closes it by
    // itself. Nothing is lost: the button is right there to press again.
    val current = critique != null && coachedText == written
    // A question shorter than the PC's own floor is not sent at all: the PC
    // would only refuse it, and refusing costs a round trip the owner can see.
    val enoughWords = written.trim().split(WHITESPACE).count { it.isNotEmpty() } >= PromptCoach.MIN_WORDS
    val canAsk = link == LinkState.CONNECTED && !streaming && !coaching && enoughWords && !shared

    Row(
        Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Quiet(
            v.button,
            enabled = canAsk,
            modifier = Modifier.semantics {
                contentDescription = if (canAsk) {
                    "Ask your PC what is missing from this question before you send it"
                } else {
                    "Coach this is not available just now"
                }
            },
            onClick = {
                val asked = draft()
                if (asked.isBlank()) return@Quiet
                close()
                coachedText = asked
                coaching = true
                scope.launch {
                    try {
                        when (val r = JarvisRuntime.coach(asked, PromptCoach.history(thread))) {
                            is PromptCoach.Read.Shown -> critique = r.critique
                            is PromptCoach.Read.Refused -> refusal = r.said
                            PromptCoach.Read.Malformed -> refusal = PromptCoach.MALFORMED
                            PromptCoach.Read.Missing -> refusal = PromptCoach.MISSING
                            is PromptCoach.Read.Failed -> refusal = r.why
                        }
                    } finally {
                        coaching = false
                    }
                }
            },
        )
        if (coaching) {
            Text(
                PromptCoach.READING,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
                modifier = Modifier.liveStatus(),
            )
        }
    }

    val c = critique
    val said = refusal
    when {
        c != null && current -> {
            Gap(6)
            PromptCoachAdvice(
                critique = c,
                view = v,
                canSend = link == LinkState.CONNECTED && !streaming && !shared,
                onSendMine = {
                    close()
                    sendMine()
                },
                onSendSuggestion = {
                    val pick = c.suggestion
                    close()
                    sendSuggestion(pick)
                },
                onDismiss = { close() },
            )
        }
        said != null -> {
            // The PC's own sentence, or the plain-words line for a link that
            // failed. Never a generic "something went wrong", and never an
            // empty panel.
            Gap(6)
            Plate {
                Text(
                    said,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (said == PromptCoach.MISSING) chrome.textMid else chrome.warnInk,
                    modifier = Modifier.liveStatus(),
                )
                Gap(4)
                Quiet(PromptCoach.DISMISS, onClick = { close() })
            }
        }
    }
}

/**
 * The advice itself, in the order the design fixed: the score out of 10; each
 * gap as what is missing, why it matters and the smallest fix; the questions;
 * and the rewrite in full.
 *
 * The rewrite is drawn in full and is never applied by being shown - only
 * "Send the suggestion" sends it, and even that puts it in the box first
 * ([PromptCoach.SEND_SUGGESTION]).
 */
@Composable
private fun PromptCoachAdvice(
    critique: PromptCoach.Critique,
    view: PromptCoach.View,
    canSend: Boolean,
    onSendMine: () -> Unit,
    onSendSuggestion: () -> Unit,
    onDismiss: () -> Unit,
) {
    val chrome = LocalChrome.current
    val accent = LocalAccent.current
    Plate {
        Row(
            Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Kicker(PromptCoach.HEADING)
            Quiet(
                PromptCoach.DISMISS,
                color = chrome.textLo,
                modifier = Modifier.semantics {
                    contentDescription = "Close the prompt coach's advice"
                },
                onClick = onDismiss,
            )
        }
        // Read out by TalkBack as it arrives, so the score is heard and not
        // only seen.
        Text(
            PromptCoach.scoreLine(critique.score),
            style = MaterialTheme.typography.titleMedium,
            color = chrome.textHi,
            modifier = Modifier.liveStatus(),
        )
        if (critique.clear && critique.issues.isEmpty()) {
            Gap(6)
            // "This is clear, send it" is a valid, expected answer, and it
            // reads in words as well as in the score's own colour.
            Text(
                PromptCoach.CLEAR_LINE,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.okInk,
            )
        }

        critique.issues.forEachIndexed { i, issue ->
            if (i > 0) {
                Gap(10)
                Rule()
            }
            Gap(10)
            PromptCoachPart(PromptCoach.ISSUE_WHAT, issue.what, chrome.textHi)
            if (issue.why.isNotEmpty()) {
                Gap(6)
                PromptCoachPart(PromptCoach.ISSUE_WHY, issue.why, chrome.textMid)
            }
            if (issue.fix.isNotEmpty()) {
                Gap(6)
                PromptCoachPart(PromptCoach.ISSUE_FIX, issue.fix, accent)
            }
        }

        if (critique.missing.isNotEmpty()) {
            Gap(10)
            Rule()
            Gap(10)
            Kicker(PromptCoach.MISSING_TITLE)
            Gap(4)
            critique.missing.forEach { q ->
                Text("• $q", style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
            }
        }

        if (critique.suggestion.isNotEmpty()) {
            Gap(10)
            Rule()
            Gap(10)
            Kicker(PromptCoach.SUGGESTION_TITLE)
            Gap(4)
            // Scrolling inside itself: a rewrite of a long question must not
            // push the two buttons off the screen, because they are the only
            // way anything here is ever sent.
            Text(
                critique.suggestion,
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.textHi,
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = SUGGESTION_MAX_HEIGHT)
                    .verticalScroll(rememberScrollState()),
            )
        }

        Gap(12)
        Row(Modifier.fillMaxWidth()) {
            // "Send mine" first and quieter: the owner's own words are the
            // default and always work, whatever the score says.
            Secondary(
                view.sendMine,
                enabled = canSend,
                modifier = Modifier
                    .weight(1f)
                    .semantics { contentDescription = "Send your own words, unchanged" },
                onClick = onSendMine,
            )
            Spacer(Modifier.width(8.dp))
            Primary(
                view.sendSuggestion,
                enabled = canSend && critique.suggestion.isNotEmpty(),
                modifier = Modifier
                    .weight(1f)
                    .semantics {
                        contentDescription = "Put the rewritten question in the box and send that"
                    },
                onClick = onSendSuggestion,
            )
        }
        if (!canSend) {
            Gap(4)
            Text(
                PromptCoach.NOT_NOW,
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
                modifier = Modifier.liveStatus(),
            )
        }
    }
}

/** One labelled part of a gap: a kicker and its words. */
@Composable
private fun PromptCoachPart(label: String, words: String, ink: Color) {
    Kicker(label)
    Gap(2)
    Text(words, style = MaterialTheme.typography.bodySmall, color = ink)
}

/** One or more spaces, a tab or a newline: what separates words in the box. */
private val WHITESPACE = Regex("\\s+")
