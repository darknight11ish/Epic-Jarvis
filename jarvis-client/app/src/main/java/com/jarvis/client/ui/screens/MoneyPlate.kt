package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.ApiResult
import com.jarvis.client.net.Money
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Rule
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.theme.LocalChrome

/**
 * "Chatbot money limits" on the phone ([Money]; `GET /api/chatbot/money`,
 * `backend/jarvis_chatbot_limits.py`'s `view()`, docs/JARVIS-API.md section
 * 122). Brain's own plate, under "Money and time", beside Spending and the
 * retirement what-if - the desktop's Settings -> Chatbot API keys page, read
 * from the phone.
 *
 * THE PLATE PRINTS THE PC'S OWN WORDS. Every sentence drawn here came out of
 * the answer: the service's one-line summary, its model, its price line with
 * where that price came from and when it was set, and the answer-length cap
 * the PC asks the service for. Nothing is added up, rounded, re-worded or
 * hidden, and nothing is read aloud or kept: the amounts live in this
 * composable's memory for as long as the plate is on screen (plain
 * `remember`, never `rememberSaveable`).
 *
 * READ ONLY, and it says so. There is no Raise button, no price box and no
 * body sent to this route: the write half is a separate piece of work that
 * ships with its own `WRITE_PATHS` entry and its own caller. [Money.READ_ONLY]
 * is on the plate so the PC's `pc_only` sentence - true of the backend and of
 * the desktop - is not read as a promise about this phone.
 *
 * THE ONE ANSWER THAT MUST NOT DRAW A BLANK. When the PC's money file is
 * there but unreadable it answers 503 `money_unreadable` with its own
 * `message`, rather than reporting nothing spent. [Money.readFailure] keeps
 * that sentence and [Money.Read.Refused] draws it exactly as it came - the
 * same treatment a 404 on a PC without the page gets.
 *
 * Under "Hide memory lists and chat history" only the hidden line is drawn,
 * with the Show button; no fetch is made and no amounts are held. The money
 * figures are the owner's own, the same rule Spending and the retirement
 * what-if keep.
 */
@Composable
internal fun ChatbotMoneySection(
    privateHidden: Boolean,
    showPrivateBusy: Boolean,
    onShowPrivate: () -> Unit,
) {
    val chrome = LocalChrome.current

    if (Money.hiddenNow(hideLists = privateHidden, locked = false)) {
        // No fetch and nothing held: this branch composes no state, so amounts
        // already read are dropped the moment the lists hide.
        Section(Money.TITLE) {
            Plate {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        Money.HIDDEN,
                        style = MaterialTheme.typography.bodyMedium,
                        color = chrome.textMid,
                        modifier = Modifier.weight(1f),
                    )
                    Quiet(
                        if (showPrivateBusy) "Checking…" else "Show",
                        enabled = !showPrivateBusy,
                        onClick = onShowPrivate,
                    )
                }
            }
        }
        return
    }

    var reads by remember { mutableIntStateOf(0) }
    var read by remember { mutableStateOf<Money.Read?>(null) }
    // The PC's own title, once it has sent one; the app's until then.
    var title by remember { mutableStateOf(Money.TITLE) }

    LaunchedEffect(reads) {
        when (val r = JarvisRuntime.chatbotMoney()) {
            is ApiResult.Ok -> {
                val got = Money.readBody(r.value)
                read = got
                if (got is Money.Read.Shown) title = got.view.title
            }
            is ApiResult.Failed ->
                read = Money.readFailure(r.error) ?: Money.Read.Failed(JarvisRuntime.noticeFor(r.error))
        }
    }

    Section(title, trailing = { Quiet("Refresh", onClick = { reads += 1 }) }) {
        Plate {
            when (val r = read) {
                null -> Text(
                    Money.READING,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textLo,
                )
                // The PC's own sentence: a 503 money_unreadable above all. Drawn
                // as it came - a blank here is the defect this plate exists for.
                is Money.Read.Refused -> Text(
                    r.message,
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
                is Money.Read.Failed -> Text(
                    "Couldn't read the chatbot money limits: ${r.why}",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.warnInk,
                )
                is Money.Read.Shown -> MoneyBody(r.view)
            }
        }
    }
}

/** The view itself: the PC's sentences, in the PC's own order. */
@Composable
private fun MoneyBody(view: Money.View) {
    val chrome = LocalChrome.current
    if (view.about.isNotEmpty()) {
        Text(view.about, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    }
    Gap(8)
    if (view.services.isEmpty()) {
        Text(Money.NO_SERVICES, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
    } else {
        view.services.forEachIndexed { index, service ->
            if (index > 0) {
                Gap(10)
                Rule()
                Gap(10)
            }
            MoneyServiceBlock(service)
        }
    }
    if (view.estimates.isNotEmpty()) {
        Gap(10)
        Text(view.estimates, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    }
    if (view.pcOnly.isNotEmpty()) {
        Gap(6)
        Text(view.pcOnly, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
    }
    Gap(6)
    Text(Money.READ_ONLY, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
}

/**
 * One API service: the PC's own line for it, the three figures it sent, its
 * model, its price line and the cap. Every string below is the PC's - except
 * [Money.figuresLine]'s framing sentence, which is the desktop's own, word for
 * word. Nothing is added up, rounded or re-worded.
 */
@Composable
private fun MoneyServiceBlock(service: Money.Service) {
    val chrome = LocalChrome.current
    val heading = service.company.ifEmpty { service.name }
    Column(Modifier.fillMaxWidth()) {
        if (heading.isNotEmpty()) {
            Text(heading, style = MaterialTheme.typography.titleSmall, color = chrome.textHi)
            Gap(2)
        }
        if (service.line.isNotEmpty()) {
            Text(service.line, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
        }
        Money.figuresLine(service).takeIf { it.isNotEmpty() }?.let {
            Gap(2)
            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        }
        service.modelProblem?.let {
            Gap(2)
            Text(it, style = MaterialTheme.typography.labelSmall, color = chrome.warnInk)
        }
        if (service.model.isNotEmpty()) {
            Gap(4)
            Text(service.model, style = MaterialTheme.typography.labelSmall, color = chrome.textMid)
        }
        service.price?.line?.takeIf { it.isNotEmpty() }?.let { priceLine ->
            Gap(2)
            // A default price the PC marks UNVERIFIED is drawn in the warning
            // ink: the sentence itself already says so, and the colour is what
            // makes it findable down a long plate.
            Text(
                priceLine,
                style = MaterialTheme.typography.labelSmall,
                color = if (service.price.unverified) chrome.warnInk else chrome.textMid,
            )
        }
        if (service.cap.isNotEmpty()) {
            Gap(2)
            Text(service.cap, style = MaterialTheme.typography.labelSmall, color = chrome.textLo)
        }
    }
}
