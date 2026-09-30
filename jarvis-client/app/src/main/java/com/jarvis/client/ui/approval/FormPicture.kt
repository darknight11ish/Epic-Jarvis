package com.jarvis.client.ui.approval

import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.window.SecureFlagPolicy
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import com.jarvis.client.JarvisRuntime
import com.jarvis.client.net.FormReview
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.theme.LocalChrome
import com.jarvis.client.ui.theme.LocalRadii
import kotlinx.coroutines.awaitCancellation

/**
 * The picture of a web form Jarvis filled in, on its "submit this form"
 * approval card (the owner's decision of 2026-09-30, [FormReview]).
 *
 * - Asked for only while this card is on screen AND the app is in front
 *   (`repeatOnLifecycle(RESUMED)`); the lock screen replaces the whole app
 *   under App lock, so nothing here runs while it is locked. Leaving the app
 *   drops the picture; coming back asks again.
 * - Held as a bitmap with plain `remember` - never `rememberSaveable`, never
 *   written anywhere, never given to a notification or a widget.
 * - Screenshots of Jarvis are blocked while it shows: [FormReview.enterView]
 *   is raised BEFORE the first request, and a short wait lets MainActivity
 *   set the window flag before any pixels of the form arrive.
 * - If it cannot be loaded the card says so in one sentence. Nothing here
 *   approves, denies or changes how the card is decided.
 */
@Composable
fun FormPicture(pictureId: String, modifier: Modifier = Modifier) {
    val chrome = LocalChrome.current
    val shape = LocalRadii.current.cardShape
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var picture by remember(pictureId) { mutableStateOf<ImageBitmap?>(null) }
    var said by remember(pictureId) { mutableStateOf<String?>(null) }
    var big by remember(pictureId) { mutableStateOf(false) }

    // Screenshots are blocked for as long as this is composed.
    DisposableEffect(pictureId) {
        FormReview.enterView()
        onDispose {
            FormReview.leaveView()
            picture = null
        }
    }

    LaunchedEffect(pictureId) {
        lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
            try {
                // Let the window's screenshot block take effect first.
                kotlinx.coroutines.delay(SECURE_WAIT_MS)
                when (val a = JarvisRuntime.formPicture(pictureId)) {
                    is FormReview.Answer.Picture -> {
                        val bytes = FormReview.decodeBytes(a.jpeg)
                        val bmp = bytes?.let {
                            runCatching { BitmapFactory.decodeByteArray(it, 0, it.size) }.getOrNull()
                        }
                        if (bmp != null) {
                            picture = bmp.asImageBitmap()
                            said = null
                        } else {
                            picture = null
                            said = FormReview.COULD_NOT_LOAD
                        }
                    }
                    is FormReview.Answer.Gone -> {
                        picture = null
                        said = FormReview.GONE
                    }
                    is FormReview.Answer.Failed -> {
                        picture = null
                        said = a.words
                    }
                }
                awaitCancellation()
            } finally {
                // The app went to the background (or the card went): drop it.
                picture = null
            }
        }
    }

    Column(modifier.fillMaxWidth()) {
        Text(
            FormReview.PICTURE_HEADING,
            style = MaterialTheme.typography.labelMedium,
            color = chrome.textHi,
        )
        Spacer(Modifier.height(6.dp))
        val bmp = picture
        if (bmp != null) {
            Image(
                bitmap = bmp,
                contentDescription = FormReview.PICTURE_DESCRIPTION,
                contentScale = ContentScale.Fit,
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 220.dp)
                    .clip(shape)
                    .background(chrome.surface1)
                    .clickable { big = true },
            )
            Spacer(Modifier.height(4.dp))
            Text(
                FormReview.TAP_TO_ENLARGE,
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
        } else {
            Text(
                said ?: FormReview.LOADING,
                style = MaterialTheme.typography.bodySmall,
                color = if (said != null) chrome.textHi else chrome.textMid,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
            )
        }
    }

    val shown = picture
    if (big && shown != null) {
        Dialog(
            onDismissRequest = { big = false },
            properties = DialogProperties(
                usePlatformDefaultWidth = false,
                securePolicy = SecureFlagPolicy.SecureOn,
            ),
        ) {
            Box(Modifier.fillMaxSize().background(Color.Black)) {
                Image(
                    bitmap = shown,
                    contentDescription = FormReview.PICTURE_DESCRIPTION,
                    contentScale = ContentScale.Fit,
                    modifier = Modifier.fillMaxSize().clickable { big = false },
                )
                Secondary(
                    FormReview.CLOSE,
                    modifier = Modifier.align(Alignment.BottomCenter).padding(16.dp),
                    onClick = { big = false },
                )
            }
        }
    }
}

/** Long enough for MainActivity's screenshot block to be set; short enough not to be noticed. */
private const val SECURE_WAIT_MS = 300L
