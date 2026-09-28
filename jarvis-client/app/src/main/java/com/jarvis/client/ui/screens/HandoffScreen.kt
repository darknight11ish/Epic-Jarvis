package com.jarvis.client.ui.screens

import android.graphics.BitmapFactory
import android.util.Base64
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.Handoff
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.theme.LocalChrome
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * "Solve it here" (the owner's decision of 2026-09-28; [Handoff]): a live
 * picture of the ONE browser window on the PC that is paused at a captcha, a
 * sign-in page or an "unusual activity" page, and the owner's own taps,
 * typing, a few keys and scrolls passed back to it.
 *
 * - The picture is asked for about once a second ([Handoff.FRAME_EVERY_MS])
 *   only while this screen is on screen and the app is in front
 *   (`repeatOnLifecycle(RESUMED)`), and never behind App lock (the lock
 *   screen replaces this one, so nothing here runs). It is held in memory
 *   for this screen only - never written anywhere - and screenshots of
 *   Jarvis are blocked while this screen shows (MainActivity,
 *   SecurityRules.blockScreenCapture).
 * - A tap on the picture goes as fractions of it ([Handoff.fractions]); a
 *   tap on the empty margin goes nowhere. Typing goes as typed (masked for a
 *   sign-in page); Enter, Backspace, Tab and Space are buttons.
 * - Input is held on a stale link, and says so ([Handoff.HELD_STALE]). End
 *   and "Solve it on the PC instead" are never held.
 * - It says plainly that some captchas refuse taps passed on this way.
 * - Jarvis never solves it: nothing here taps or types by itself.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun HandoffScreen(
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    val scope = rememberCoroutineScope()
    val offer by JarvisRuntime.handoffOffer.collectAsState()
    val stale by JarvisRuntime.stale.collectAsState()
    var hid by remember { mutableStateOf(JarvisRuntime.handoffActive) }
    var picture by remember { mutableStateOf<ImageBitmap?>(null) }
    var picSize by remember { mutableStateOf(0 to 0) }
    var said by remember { mutableStateOf<String?>(null) }
    var ended by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    // Not rememberSaveable: what is typed into the page (a sign-in page's
    // password among it) is never saved in the app's state.
    var typed by remember { mutableStateOf("") }
    val lifecycle = LocalLifecycleOwner.current.lifecycle

    // Read what is waiting now: opened from the alert after Android closed
    // the app, nothing has been read yet. A read - never held.
    var checked by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        JarvisRuntime.chatbotStatus(null)
        checked = true
    }

    // Start once, when there is a page waiting and no hand-off yet - and not
    // on a stale link (it starts when the link is back).
    LaunchedEffect(offer?.key, hid, stale) {
        val o = offer ?: return@LaunchedEffect
        if (hid != null || ended != null || stale) return@LaunchedEffect
        busy = true
        val (h, why) = JarvisRuntime.handoffStart(o)
        busy = false
        if (h != null) hid = h else said = why
    }

    // The picture, about once a second, only while this screen is in front.
    LaunchedEffect(hid) {
        val h = hid ?: return@LaunchedEffect
        lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
            while (true) {
                when (val a = JarvisRuntime.handoffFrame(h)) {
                    is Handoff.Answer.Picture -> {
                        val bytes = runCatching { Base64.decode(a.jpeg, Base64.DEFAULT) }.getOrNull()
                        val bmp = bytes?.let { runCatching { BitmapFactory.decodeByteArray(it, 0, it.size) }.getOrNull() }
                        if (bmp != null) {
                            picture = bmp.asImageBitmap()
                            picSize = a.width to a.height
                        }
                        delay(Handoff.FRAME_EVERY_MS)
                    }
                    is Handoff.Answer.TooSoon -> delay(a.retryMs)
                    is Handoff.Answer.Ended -> {
                        ended = a.words
                        picture = null
                        hid = null
                        return@repeatOnLifecycle
                    }
                    is Handoff.Answer.Failed -> {
                        if (a.words.isNotEmpty()) said = a.words
                        delay(Handoff.FRAME_EVERY_MS * 2)
                    }
                }
            }
        }
    }

    // Leaving the screen does not end the hand-off at once (a rotation must
    // not), but nothing more is asked for; the PC ends it after 45 seconds
    // unlooked-at. The picture goes with the screen.
    DisposableEffect(Unit) { onDispose { picture = null } }

    fun send(body: String?) {
        scope.launch {
            val a = JarvisRuntime.handoffInput(body)
            said = when (a) {
                null -> null
                is Handoff.Answer.Ended -> {
                    ended = a.words
                    hid = null
                    null
                }
                is Handoff.Answer.Failed -> a.words.ifEmpty { null }
                is Handoff.Answer.TooSoon -> "Slow down a little."
                is Handoff.Answer.Picture -> null
            }
        }
    }

    val site = offer?.site ?: ""
    val subtitle = offer?.let { "${it.site}: ${Handoff.reasonWords(it.reason)}" }

    Column(modifier.fillMaxSize().background(chrome.surface0).navigationBarsPadding().imePadding()) {
        TopBar(Handoff.TITLE, onBack = onBack, subtitle = subtitle)
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (ended != null || (checked && offer == null && hid == null)) {
                Plate {
                    Text(
                        ended ?: "Nothing is waiting for you on a website right now.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = chrome.textHi,
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
                    )
                    Gap(8)
                    Secondary("Back", onClick = onBack)
                }
                Gap(24)
            } else {
                Text(Handoff.DETAIL, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                // Said plainly, always on screen (the owner's decision).
                Text(Handoff.MAY_REFUSE, style = MaterialTheme.typography.bodySmall, color = chrome.textHi)

                // The picture. A tap on it goes to the same place on the page.
                val bmp = picture
                Box(
                    Modifier
                        .fillMaxWidth()
                        .heightIn(min = 240.dp, max = 560.dp)
                        .background(chrome.surface1)
                        .pointerInput(bmp, hid, stale) {
                            detectTapGestures { at ->
                                val h = hid ?: return@detectTapGestures
                                val (w, hh) = picSize
                                val f = Handoff.fractions(at.x, at.y, this.size.width.toFloat(),
                                    this.size.height.toFloat(), w, hh) ?: return@detectTapGestures
                                send(Handoff.tapBody(h, f.first, f.second))
                            }
                        },
                    contentAlignment = Alignment.Center,
                ) {
                    if (bmp != null) {
                        Image(
                            bitmap = bmp,
                            contentDescription = "The page on your PC: $site. Tap where you would click.",
                            contentScale = ContentScale.Fit,
                            modifier = Modifier.fillMaxWidth().heightIn(min = 240.dp, max = 560.dp),
                        )
                    } else {
                        Text(
                            if (busy || hid != null || !checked) Handoff.WAITING else said.orEmpty(),
                            style = MaterialTheme.typography.bodyMedium,
                            color = chrome.textMid,
                        )
                    }
                }

                if (stale) {
                    Text(
                        Handoff.HELD_STALE,
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.warnInk,
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
                    )
                }
                said?.let {
                    Text(
                        it,
                        style = MaterialTheme.typography.bodySmall,
                        color = chrome.textHi,
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
                    )
                }

                val h = hid
                Plate {
                    TextInput(
                        value = typed,
                        onValueChange = { typed = it.take(Handoff.TEXT_MOST) },
                        modifier = Modifier.fillMaxWidth(),
                        label = Handoff.TYPE_LABEL,
                        // A sign-in page: what is typed is masked on this screen.
                        password = offer?.reason == "login",
                    )
                    Gap(6)
                    Secondary(Handoff.TYPE_SEND, enabled = h != null && typed.isNotEmpty() && !stale, onClick = {
                        val body = h?.let { Handoff.textBody(it, typed) }
                        typed = ""
                        send(body)
                    })
                    Gap(8)
                    Text(Handoff.KEYS_LABEL, style = MaterialTheme.typography.labelMedium, color = chrome.textMid)
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Handoff.SHOWN_KEYS.forEach { key ->
                            Secondary(key, enabled = h != null && !stale, onClick = {
                                send(h?.let { Handoff.keyBody(it, key) })
                            })
                        }
                        Secondary(Handoff.SCROLL_UP, enabled = h != null && !stale, onClick = {
                            send(h?.let { Handoff.scrollBody(it, -Handoff.SCROLL_STEP) })
                        })
                        Secondary(Handoff.SCROLL_DOWN, enabled = h != null && !stale, onClick = {
                            send(h?.let { Handoff.scrollBody(it, Handoff.SCROLL_STEP) })
                        })
                    }
                }

                Text(Handoff.THEN_RESUME, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                Text(Handoff.NEW_WINDOW, style = MaterialTheme.typography.bodySmall, color = chrome.textMid)
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    // Never held: ending only makes Jarvis do less.
                    Primary(Handoff.PC_BUTTON, onClick = {
                        h?.let { JarvisRuntime.handoffEnd(it) }
                        onBack()
                    })
                    Quiet(Handoff.END, onClick = {
                        h?.let { JarvisRuntime.handoffEnd(it) }
                        hid = null
                        ended = com.jarvis.client.net.Handoff.ENDED.getValue("owner")
                    })
                }
                Gap(24)
            }
        }
    }
}
