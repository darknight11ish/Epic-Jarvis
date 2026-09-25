package com.jarvis.client.ui.screens

import android.content.Intent
import android.net.Uri
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
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
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import com.jarvis.client.BuildConfig
import com.jarvis.client.ui.Chevron
import com.jarvis.client.ui.parts.pressable
import com.jarvis.client.ui.theme.LocalAccent
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalMotion
import com.jarvis.client.ui.theme.LocalRadii

/**
 * A question this app's own owner has actually been asked, or would be.
 *
 * Answers specific to THIS app — the one on the phone. The desktop program has
 * its own FAQ, in its own Settings window, because the two run into different
 * problems: this one is a thin client (its only models are small sound
 * models - the wake word, the end of speech and "stop" - and none of them
 * makes words), reached over a private mesh network (Tailscale or Meshnet), gated by the phone's
 * fingerprint sensor rather than its keyboard. A phone owner asking "does this run anything on my phone" needs a different
 * answer than a desktop owner asking the same question about their graphics
 * card.
 */
private data class Faq(val q: String, val a: String)

private val FAQS = listOf(
    Faq(
        "Do I need Tailscale for this to work?",
        "You need a private mesh network between only the devices you own, " +
            "never the open internet — Tailscale is one, and NordVPN's Meshnet " +
            "is another, if you already have a NordVPN account. Jarvis's brain " +
            "runs on your desktop, and this phone only reaches it over that " +
            "mesh. When you pair, type the desktop's mesh name — Tailscale's " +
            "ends in .ts.net, Meshnet's ends in .nord — not its 100.x address " +
            "directly. This phone is only allowed to trust a small, named " +
            "list of hosts, and a name is on that list where a raw address " +
            "cannot be.",
    ),
    Faq(
        "Does this app run any AI on my phone?",
        // Used to answer "No." It was never true once the wake word came in:
        // three small sound models run here (voice/OrtWakeModels.kt,
        // SmartTurn.kt, StopWord.kt). None of them makes words.
        "Only small sound models. They listen for the \"hey Jarvis\" wake " +
            "word, for the end of your sentence, and for \"stop\" while Jarvis " +
            "is talking. They only listen for sounds: none of them turns " +
            "speech into words. Everything else runs on your PC: checking it " +
            "is your voice, writing down what you said, understanding it, " +
            "and deciding what to say back. That order matters - a phone " +
            "that wrote down your words itself would have done it before " +
            "your PC could check it was your voice.",
    ),
    Faq(
        "How do I use \"hey Jarvis\"?",
        "It is off until you turn it on, in two steps. First, on Platform " +
            "checks, tap Turn on \"hey Jarvis\" and approve the card that " +
            "appears - that lets your desktop accept it. Then tap Listen on " +
            "this phone. While that is on, the microphone stays open (Android " +
            "shows its microphone dot and a notification), a small model on " +
            "the phone listens for the phrase and nothing else, and nothing " +
            "leaves the phone until it hears it. Then what you say next goes " +
            "to your desktop, which checks it is your voice before it writes " +
            "down a word. Two exceptions, both only while you are talking " +
            "with Jarvis: with \"Interrupt Jarvis while it talks\" on, about " +
            "two seconds of anything said over Jarvis's answer go to your " +
            "desktop, which only checks whether it was you (it never writes " +
            "those down); and when Jarvis ends an answer with a question, " +
            "your reply goes without the phrase, checked the same way. It " +
            "stops when you stop it, restart the phone, or Android closes " +
            "Jarvis, and it uses some battery while on.",
    ),
    Faq(
        "How do I teach Jarvis my voice? Where is the talk button?",
        "Open Platform checks and tap Train my voice on the Your voice card. " +
            "Read the twelve short sentences, send them, then approve the card that " +
            "appears on your desktop or here - Jarvis learns your voice only " +
            "when you approve it, and the recordings are deleted either way. " +
            "The talk button on Home appears once your voice is trained and " +
            "the desktop can turn speech into text; the same card says which " +
            "of those is still missing.",
    ),
    Faq(
        "Why can't I approve everything waiting for me in one tap?",
        // Used to say the cards were in the Inbox and the buttons were
        // "Affirm" and "Refuse". The cards are on Home (Inbox only links to
        // them), and "Affirm"/"Refuse" are the names of the components in
        // the code, not the words on the buttons (screens-11).
        "On purpose, the same as on the desktop: there is no approve-all " +
            "anywhere in Jarvis. Each card waiting for you on Home is answered " +
            "on its own, by a swipe for the ones the desktop has already flagged " +
            "as safe to swipe, or by tapping Approve or Deny otherwise. " +
            "Nothing runs until you decide, one thing at a time.",
    ),
    Faq(
        "Why does approving something ask for my fingerprint, but denying doesn't?",
        // Kept in step with SecurityScreen.kt and data/Security.kt.
        "Out of the box, your fingerprint (or phone PIN) is asked only for " +
            "the risky ones: actions that leave your PC, cannot be undone, " +
            "were not labelled by Jarvis, or arrived flagged as rushed. A phone " +
            "is the device most likely to be picked up by someone who is not " +
            "you, so approving one of those checks that whoever is holding it " +
            "right now is really the owner. If you want it for every approval, " +
            "open Platform checks, then Lock and fingerprint settings, and " +
            "choose Every approval. Denying is always the safe direction, so it " +
            "is never gated behind anything — the cautious answer should never " +
            "be the slow one.",
    ),
    Faq(
        "Can I lock Jarvis itself, or hide what it remembers?",
        "Yes, in Platform checks, then Lock and fingerprint settings. Lock " +
            "Jarvis makes opening the app need your fingerprint or phone PIN, " +
            "and you choose how long it can be out of sight before it asks " +
            "again. Hide memory lists and chat history keeps Mind's memory lists, the wiki's " +
            "list of your notes and your chat history hidden until you tap " +
            "Show and confirm. Chat " +
            "answers are not hidden, because your PC does not say which ones " +
            "used your email, calendar, notes or memory. Fingerprint only " +
            "leaves out the PIN; only a fingerprint or face that Android rates " +
            "as strong counts, and many phones' face unlock does not. Turning " +
            "something on is instant; turning it off asks for your fingerprint " +
            "or PIN first. These settings stay on this phone and are never " +
            "sent to your PC.",
    ),
    Faq(
        "Are my chats kept anywhere?",
        "On your PC, encrypted, and nowhere else - including what you say by " +
            "voice. This phone keeps none of it. To read, delete or stop " +
            "keeping them, open Mind, then Chat history. Turning keeping back " +
            "on asks you first, with an approval card; turning it off is " +
            "instant, and what is already kept stays until you delete it. " +
            "Text you share into Jarvis from another app is sent, and kept, " +
            "marked as shared, so Jarvis never mistakes it for your own words.",
    ),
    Faq(
        "My phone has no screen lock. Does the fingerprint check still work?",
        "No, because there is nothing for Jarvis to check against. So risky " +
            "approvals - anything that leaves your PC, cannot be undone, or " +
            "that outside text tried to rush - are refused until the phone " +
            "has a screen lock, with a message and a button that opens " +
            "Android's screen-lock settings (Security, Screen lock). Other " +
            "approvals still work. If you turn any Jarvis lock on, approvals " +
            "that need the check are refused and the app lock and hidden " +
            "lists stay shut too; Jarvis will not let you turn a lock on while " +
            "the phone has no screen lock. The PC does the same without " +
            "Windows Hello.",
    ),
    Faq(
        "What does a Jarvis notification show on my lock screen?",
        "Only that Jarvis is waiting on a decision — never the actual " +
            "content of what it wants to do. The real details stay hidden " +
            "until you unlock the phone and open the app. The notification " +
            "can have a Deny button, when refusing without reading is safe, " +
            "but never an Approve button, on purpose: saying yes happens " +
            "inside the app, where the risky ones ask for your fingerprint, " +
            "and that is not a decision to make from a locked screen. The " +
            "home-screen widget follows the same rule.",
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
        "Check that your private network (Tailscale, or NordVPN's Meshnet) " +
            "is actually running on both the phone and the desktop first — " +
            "that is the most common cause by far. Open " +
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
        // Used to say "this is currently a debug build". It is not: the
        // workflow publishes the RELEASE build to the client-latest page
        // (build.gradle.kts, the long comment on `release`), and the risk
        // that is actually on record - the shared signing key - went
        // unmentioned (screens-11). Kept to what the build files show.
        "Not for a phone only you use, which is what this app is for. The " +
            "copy on your GitHub release page is a release build, the " +
            "finished and locked-down kind: developer tools on a computer " +
            "plugged into the phone cannot reach into this app's storage. " +
            "The one thing worth knowing: every build is signed with the same " +
            "key, which is what lets an update install over the old copy " +
            "without wiping your pairing. Anyone holding that key could build " +
            "an app your phone accepts as an update to this one, and that app " +
            "could read your pairing token. The key is kept as a hidden secret " +
            "in the project's GitHub settings, not in the code. So install " +
            "Jarvis updates only from your own release page, never from a " +
            "file someone sends you.",
    ),
    Faq(
        "How do I know when there is a newer version?",
        // net/UpdateCheck.kt.
        "Jarvis asks GitHub, at most every six hours, whether a newer build " +
            "is on the client-latest release page, and if there is one, a " +
            "quiet line near the top of Home offers to open that page. It " +
            "never downloads or installs anything: you install it yourself, " +
            "the same way as before. The question to GitHub carries nothing " +
            "about you or Jarvis. To stop it, open Platform checks and turn " +
            "off Check for new versions on the This app card; that card also " +
            "says if the last check failed.",
    ),
)

@Composable
fun FaqScreen(
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    Column(modifier.fillMaxSize().background(chrome.surface0)) {
        // Titled with the word on the button that opened it. Home's nav says
        // "Help", and a beginner who taps "Help" and lands on "Frequently
        // asked questions" has to work out that they are the same place
        // (screens-15). The old title moves into the subtitle.
        TopBar(
            "Help",
            onBack,
            subtitle = "Frequently asked questions, for this phone. The desktop has its own.",
        )

        LazyColumn(
            verticalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.weight(1f).fillMaxWidth().padding(horizontal = 18.dp),
        ) {
            item(key = "top-space") { Spacer(Modifier.height(6.dp)) }
            items(FAQS, key = { it.q }) { FaqCard(it) }
            // Identity, not behaviour - the FAQ above already answers "how does
            // this behave"; this answers "what is this, and where did it come
            // from." Sits at the end of this list rather than its own screen or
            // status-bar chip, mirroring the desktop's own About Jarvis section,
            // which lives at the end of its Settings/FAQ page for the same
            // reason.
            item(key = "about") { AboutCard() }
            item(key = "bottom-space") { Spacer(Modifier.height(4.dp)) }
        }
    }
}

/**
 * One question. Closed by default, so the list is scannable rather than a wall of text.
 *
 * The open/closed mark is a drawn chevron that turns over, not a typed "+"
 * and "−" (screens-14): those were whatever the phone's font made of them,
 * and a bare "+" reads as "add". The chevron is decoration only. A screen
 * reader is told the state in words instead - "Expanded" or "Collapsed" -
 * which it had no way to know before (a11y-8), because "+" was read out as
 * "plus".
 *
 * The answer is bodyMedium (15sp), not bodySmall (13sp): these are
 * paragraphs meant to be read, and 13sp is the size for captions.
 */
@Composable
private fun FaqCard(faq: Faq) {
    val chrome = LocalChrome.current
    var open by rememberSaveable { mutableStateOf(false) }
    val turn by animateFloatAsState(
        targetValue = if (open) 180f else 0f,
        animationSpec = LocalMotion.current.micro(),
        label = "faq-chevron",
    )
    Column(
        Modifier
            .fillMaxWidth()
            .animateContentSize()
            .clip(LocalRadii.current.cardShape)
            .background(chrome.surface1)
            .semantics { stateDescription = if (open) "Expanded" else "Collapsed" }
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
            Spacer(Modifier.width(8.dp))
            // Turned in the draw phase, so the 120ms turn redraws one small
            // box and recomposes nothing.
            Chevron(
                tint = chrome.textMid,
                modifier = Modifier.graphicsLayer { rotationZ = turn },
            )
        }
        if (open) {
            Spacer(Modifier.height(8.dp))
            Text(faq.a, style = MaterialTheme.typography.bodyMedium, color = chrome.textMid)
        }
    }
}

/**
 * What this app IS, not how it behaves - the identity card, same job the
 * desktop's own About Jarvis section does at the end of its Settings page.
 *
 * The version comes from `BuildConfig.VERSION_NAME` - the real value Gradle
 * stamped into this exact build, never a hand-typed string that could go
 * stale the next time `versionName` changes in build.gradle.kts and nobody
 * remembers to update a second copy of it here.
 */
@Composable
private fun AboutCard() {
    val chrome = LocalChrome.current
    val context = LocalContext.current
    Column(
        Modifier
            .fillMaxWidth()
            .clip(LocalRadii.current.cardShape)
            .background(chrome.surface1)
            .padding(14.dp),
    ) {
        Text(
            "About Jarvis",
            style = MaterialTheme.typography.titleSmall,
            color = chrome.textHi,
        )
        Spacer(Modifier.height(8.dp))
        Text(
            "A thin client to the Jarvis brain running on your own desktop, " +
                "reached only over a private network between only the devices " +
                "you own (Tailscale, or NordVPN's Meshnet), never the open " +
                "internet. Only small sound models run on this phone, and " +
                "none of them turns speech into words; there is no " +
                "approve-all anywhere in this app, and " +
                "every action still stops and asks first, one at a time.",
            style = MaterialTheme.typography.bodySmall,
            color = chrome.textMid,
        )
        Spacer(Modifier.height(12.dp))
        AboutFact("Version", BuildConfig.VERSION_NAME)
        AboutFact("License", "MIT — see LICENSE in the source")
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "Source",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textMid,
                modifier = Modifier.width(64.dp),
            )
            Text(
                "github.com/darknight11ish/Epic-Jarvis",
                style = MaterialTheme.typography.bodySmall,
                color = LocalAccent.current,
                modifier = Modifier.pressable(onClick = {
                    // The real OS browser, same as any other outbound link -
                    // this app has no WebView to accidentally navigate away
                    // inside of, but it is still not this screen's job to
                    // render a web page.
                    val intent = Intent(
                        Intent.ACTION_VIEW,
                        Uri.parse("https://github.com/darknight11ish/Epic-Jarvis"),
                    )
                    context.startActivity(intent)
                }),
            )
        }
    }
}

@Composable
private fun AboutFact(label: String, value: String) {
    val chrome = LocalChrome.current
    Row(Modifier.padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(
            label,
            style = MaterialTheme.typography.labelSmall,
            color = chrome.textMid,
            modifier = Modifier.width(64.dp),
        )
        Text(value, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)
    }
}
