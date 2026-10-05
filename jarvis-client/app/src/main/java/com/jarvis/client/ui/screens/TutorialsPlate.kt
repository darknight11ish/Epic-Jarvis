package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.Tutorials
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Kicker
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Rule
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.launch

/**
 * "Tutorials" and the FAQ on the Brain screen (docs/JARVIS-API.md section 114,
 * docs/TUTORIALS-DESIGN.md): one catalogue for the phone and the PC, with the
 * owner's reading progress kept on the PC, so finishing a tutorial here marks it
 * there and the other way round.
 *
 * NO CARD, EVER, and it works on a stale link too - reading a tutorial and
 * marking where you got to act on nothing. The catalogue is the PC's own; this
 * screen holds it and drops it when it closes.
 *
 * SKIPPABLE, AND RESUMABLE. Every step writes where the owner has read to, so
 * leaving mid-way and coming back offers "Continue at step N". "Show this one
 * again" clears the record, and a tutorial whose steps changed comes back on its
 * own (due). The words are [Tutorials]'s, which are the desktop's.
 */
@Composable
internal fun TutorialsSection() {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    var read by remember { mutableStateOf<Tutorials.Read>(Tutorials.Read.NotAsked) }
    var open by remember { mutableStateOf<String?>(null) }
    var at by remember { mutableStateOf(0) }

    LaunchedEffect(Unit) {
        read = Tutorials.Read.Loading
        read = JarvisRuntime.tutorials()
    }

    Section(Tutorials.HEADING) {
        Plate {
            val loaded = read as? Tutorials.Read.Loaded
            if (loaded == null) {
                Text(
                    Tutorials.INTRO_OFFER,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
            } else {
                // The two sections the owner asked for: this app's own, and the
                // shared ones, which appear in both apps.
                for ((id, title) in Tutorials.SECTIONS) {
                    val mine = loaded.catalogue.forSection(id)
                    if (mine.isEmpty()) continue
                    Kicker(title, Modifier.semantics { heading() })
                    Gap(4)
                    for (tutorial in mine) {
                        Gap(2)
                        Text(
                            tutorial.title,
                            style = MaterialTheme.typography.bodyMedium,
                            color = chrome.textHi,
                        )
                        Text(
                            tutorial.stateWords,
                            style = MaterialTheme.typography.labelSmall,
                            color = if (tutorial.due && !tutorial.done) chrome.warnInk
                            else chrome.textMid,
                        )
                        if (tutorial.showsAgain) {
                            Gap(2)
                            Secondary(
                                text = Tutorials.AGAIN,
                                enabled = true,
                                modifier = Modifier.fillMaxWidth(),
                                onClick = { scope.launch { JarvisRuntime.markTutorial(tutorial.id, 0, "not_started") } },
                            )
                        } else {
                            Gap(2)
                            Secondary(
                                text = if (open == tutorial.id) Tutorials.QUIT else Tutorials.RESTART,
                                enabled = true,
                                modifier = Modifier.fillMaxWidth(),
                                onClick = {
                                    if (open == tutorial.id) {
                                        open = null
                                    } else {
                                        open = tutorial.id
                                        at = tutorial.startIndex
                                        scope.launch { JarvisRuntime.markTutorial(tutorial.id, at) }
                                    }
                                },
                            )
                        }
                    }
                    Gap(8)
                    Rule()
                    Gap(8)
                }

                // The open tutorial's step card.
                val shown = open?.let { id -> loaded.catalogue.tutorials.firstOrNull { it.id == id } }
                if (shown != null) {
                    val step = shown.steps.getOrNull(at) ?: shown.steps.firstOrNull()
                    Kicker(shown.stepWords, Modifier.semantics { heading() })
                    Gap(2)
                    step?.let {
                        Text(it.title, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
                        Gap(2)
                        Text(it.body, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
                        if (it.where.isNotEmpty()) {
                            Gap(4)
                            Text(it.where, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
                        }
                    }
                    Gap(6)
                    Secondary(
                        text = Tutorials.BACK,
                        enabled = shown.backIndex(at) != null,
                        modifier = Modifier.fillMaxWidth(),
                        onClick = {
                            shown.backIndex(at)?.let { back ->
                                at = back
                                scope.launch { JarvisRuntime.markTutorial(shown.id, back) }
                            }
                        },
                    )
                    Gap(4)
                    Secondary(
                        text = if (shown.nextIndex(at) == null) Tutorials.DONE else Tutorials.NEXT,
                        enabled = true,
                        modifier = Modifier.fillMaxWidth(),
                        onClick = {
                            val next = shown.nextIndex(at)
                            if (next == null) {
                                open = null
                                scope.launch { JarvisRuntime.markTutorial(shown.id, at, "done") }
                            } else {
                                at = next
                                scope.launch { JarvisRuntime.markTutorial(shown.id, next) }
                            }
                        },
                    )
                    Gap(4)
                    Secondary(
                        text = Tutorials.SKIP,
                        enabled = true,
                        modifier = Modifier.fillMaxWidth(),
                        onClick = {
                            open = null
                            scope.launch { JarvisRuntime.markTutorial(shown.id, at, "skipped") }
                        },
                    )
                }
            }

            Tutorials.readLine(read)?.let {
                Gap(8)
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (read is Tutorials.Read.Loading) chrome.textMid else chrome.warnInk,
                    modifier = Modifier.liveStatus(),
                )
            }

            FaqList()
        }
    }
}

/** The questions and answers, in the PC's own order. Read when first shown. */
@Composable
private fun FaqList() {
    val chrome = LocalChrome.current
    var questions by remember { mutableStateOf<List<Tutorials.Question>?>(null) }

    LaunchedEffect(Unit) { questions = JarvisRuntime.faq() }

    val list = questions ?: return
    if (list.isEmpty()) return
    Gap(10)
    Rule()
    Gap(8)
    Kicker(Tutorials.FAQ_HEADING, Modifier.semantics { heading() })
    for (item in list) {
        Gap(8)
        Text(item.q, style = MaterialTheme.typography.bodyMedium, color = chrome.textHi)
        Gap(2)
        Text(item.a, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
        if (item.where.isNotEmpty()) {
            Gap(2)
            Text(item.where, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        }
    }
}
