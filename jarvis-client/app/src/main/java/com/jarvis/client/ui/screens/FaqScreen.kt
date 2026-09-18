package com.jarvis.client.ui.screens

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import com.jarvis.client.ui.parts.pressable
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalRadii

/**
 * A question this app's own owner has actually been asked, or would be.
 *
 * Answers specific to THIS app — the one on the phone. The desktop program has
 * its own FAQ, in its own Settings window, because the two run into different
 * problems: this one is a thin client with no model of its own, reached over
 * Tailscale, gated by the phone's fingerprint sensor rather than its keyboard.
 * A phone owner asking "does this run anything on my phone" needs a different
 * answer than a desktop owner asking the same question about their graphics
 * card.
 */
private data class Faq(val q: String, val a: String)

private val FAQS = listOf(
    Faq(
        "Do I need Tailscale for this to work?",
        "Yes. Jarvis's brain runs on your desktop, and this phone only reaches " +
            "it over Tailscale — a private network between only the devices you " +
            "own, never the open internet. When you pair, type the desktop's " +
            "Tailscale name (it ends in .ts.net), not its 100.x address " +
            "directly — this phone is only allowed to trust a small, named " +
            "list of hosts, and a name is on that list where a raw address " +
            "cannot be.",
    ),
    Faq(
        "Does this app run any AI on my phone?",
        "No. This app is a thin client: it shows you what the desktop says, " +
            "and it sends the desktop what you type or say. Recognising your " +
            "voice, understanding it, and deciding what to say back all " +
            "happen on the desktop, never here — a phone that transcribed " +
            "your voice itself would have already turned it into text before " +
            "the desktop's owner-voice check ever saw it, and there would be " +
            "nothing left for that check to examine.",
    ),
    Faq(
        "Why doesn't saying \"hey Jarvis\" wake anything on my phone?",
        "This phone never listens for a wake phrase — no wake-word model is " +
            "bundled in the app at all, so its microphone only opens while " +
            "you are holding the talk button down. A wake word can run on " +
            "the desktop instead; Platform checks shows whether the desktop " +
            "currently has one turned on, and lets you turn it off from " +
            "here, but turning it on is a desktop-side choice, on purpose.",
    ),
    Faq(
        "Why can't I approve everything waiting for me in one tap?",
        "On purpose, the same as on the desktop: there is no approve-all " +
            "anywhere in Jarvis. Each card in your Inbox is answered on its " +
            "own, by a swipe for the ones the desktop has already flagged as " +
            "safe to swipe, or by tapping Affirm or Refuse otherwise. " +
            "Nothing runs until you decide, one thing at a time.",
    ),
    Faq(
        "Why does approving something ask for my fingerprint, but denying doesn't?",
        "Your fingerprint is asked only for the actions where it matters most " +
            "— ones that leave this machine, cannot be undone, or arrived " +
            "flagged as rushed. A phone is the device most likely to be " +
            "picked up by someone who is not you, so approving one of those " +
            "actions checks that whoever is holding it right now is really " +
            "the owner. Denying is always the safe direction, so it is never " +
            "gated behind anything — the cautious answer should never be the " +
            "slow one.",
    ),
    Faq(
        "What does a Jarvis notification show on my lock screen?",
        "Only that Jarvis is waiting on a decision — never the actual " +
            "content of what it wants to do. The real details stay hidden " +
            "until you unlock the phone and open the app, and there is no " +
            "Approve or Deny button on the notification itself, on purpose: " +
            "a decision this app cares about enough to gate behind a " +
            "fingerprint is not one to make from a locked screen either.",
    ),
    Faq(
        "Does Jarvis's spoken voice ever get sent to a company like Google?",
        "Not any more. An earlier version of this app could fall back to " +
            "whatever speech engine Android had installed if the desktop's " +
            "own voice reply failed to arrive — on most phones, that is a " +
            "networked engine that sends the text away to be spoken. That " +
            "path is closed now: this app only ever speaks with a voice that " +
            "stays entirely on the phone, and if none is available, it shows " +
            "the reply as text instead of speaking it, rather than quietly " +
            "using one that phones home.",
    ),
    Faq(
        "It says \"Cannot reach the desktop.\" Now what?",
        "Check that Tailscale is actually running on both the phone and the " +
            "desktop first — that is the most common cause by far. Open " +
            "Platform checks from Home to see exactly what this phone thinks " +
            "is wrong. One known rough edge worth knowing about: a desktop " +
            "that is simply asleep or has its lid closed currently looks " +
            "identical to a real error on this screen, rather than a calmer " +
            "\"it's just asleep\" message — so before assuming something " +
            "broke, check whether the desktop itself is actually awake.",
    ),
    Faq(
        "Why does Jarvis want an exception from battery optimisation?",
        "So Android does not quietly close the connection to your desktop " +
            "while the app is in the background. Without it, the link this " +
            "app holds open can be killed within about a minute of you " +
            "switching to another app, and approvals simply stop arriving " +
            "with no warning. \"Keep link alive,\" on Platform checks, opens " +
            "Android's own exception screen — it is never granted silently, " +
            "and Platform checks keeps reporting the real state either way.",
    ),
    Faq(
        "Is my pairing token safe on this phone?",
        "It is stored using the phone's own hardware security chip (the " +
            "Android Keystore), not as plain text the way a file on a " +
            "desktop can be read by anyone with access to that computer. " +
            "Once you type it in to pair, it is never shown back to you " +
            "again, on this screen or anywhere else in the app.",
    ),
    Faq(
        "Is it a problem that I installed this from a file instead of the Play Store?",
        "Not for a phone only you use, which is what this build is for. " +
            "Worth knowing plainly rather than not mentioning: this is " +
            "currently a debug build, which is slightly less locked down " +
            "than a store release — specifically, a computer connected to " +
            "the phone with developer tools can still reach into this app's " +
            "own storage. Fine for a phone that stays in your own hands; " +
            "worth remembering if that phone is ever going to be someone " +
            "else's.",
    ),
)

@Composable
fun FaqScreen(
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    Column(modifier.fillMaxSize().background(chrome.surface0)) {
        TopBar(
            "Frequently asked questions",
            onBack,
            subtitle = "Answers specific to this phone. The desktop has its own.",
        )

        LazyColumn(
            verticalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.weight(1f).fillMaxWidth().padding(horizontal = 18.dp),
        ) {
            item(key = "top-space") { Spacer(Modifier.height(6.dp)) }
            items(FAQS, key = { it.q }) { FaqCard(it) }
            item(key = "bottom-space") { Spacer(Modifier.height(4.dp)) }
        }
    }
}

/** One question. Closed by default, so the list is scannable rather than a wall of text. */
@Composable
private fun FaqCard(faq: Faq) {
    val chrome = LocalChrome.current
    var open by rememberSaveable { mutableStateOf(false) }
    Column(
        Modifier
            .fillMaxWidth()
            .animateContentSize()
            .clip(LocalRadii.current.cardShape)
            .background(chrome.surface1)
            .pressable(onClick = { open = !open })
            .padding(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                faq.q,
                style = MaterialTheme.typography.titleSmall,
                color = chrome.textHi,
                modifier = Modifier.weight(1f),
            )
            Text(
                if (open) "−" else "+",
                style = MaterialTheme.typography.titleSmall,
                color = chrome.textMid,
            )
        }
        if (open) {
            Spacer(Modifier.height(8.dp))
            Text(faq.a, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
        }
    }
}
