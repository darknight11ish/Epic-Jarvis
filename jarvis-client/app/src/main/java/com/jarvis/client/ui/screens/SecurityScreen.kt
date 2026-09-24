package com.jarvis.client.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.jarvis.client.data.ApprovalCheck
import com.jarvis.client.data.CheckAvailability
import com.jarvis.client.data.CheckMethod
import com.jarvis.client.data.RelockAfter
import com.jarvis.client.data.Security
import com.jarvis.client.data.SecurityRules
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Notice
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.liveStatus
import com.jarvis.client.ui.theme.LocalChrome

/**
 * Security: the app lock and the fingerprint settings (`data/Security.kt`).
 *
 * Every control hands the WHOLE new settings record to [onChange], and the
 * caller decides: a loosening waits for a fingerprint or PIN check, a
 * tightening is saved at once (`SecurityRules.loosens`). This screen never
 * saves anything itself, so there is no path from a tap here to a looser
 * setting that skips the check.
 *
 * Saved on this phone only, never sent to the PC.
 */
@Composable
fun SecurityScreen(
    security: Security,
    /** What the phone says about [security]'s method right now. */
    availability: CheckAvailability,
    onChange: (Security) -> Unit,
    onBack: () -> Unit,
    /** True while a fingerprint or PIN check for a change is up. */
    busy: Boolean = false,
    notice: String? = null,
    onDismissNotice: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    Column(modifier.fillMaxSize().background(chrome.surface0).navigationBarsPadding()) {
        TopBar("Security", onBack, subtitle = "Lock and fingerprint, on this phone only")

        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            if (notice != null) {
                item(key = "notice") { Notice(notice, onDismissNotice) }
            }

            // The one warning that changes what the other settings do. Said
            // here rather than discovered at the next approval.
            if (security.anyLockOn && availability != CheckAvailability.READY &&
                availability != CheckAvailability.NOT_NOW
            ) {
                item(key = "no-check") {
                    // Not a Notice: that has a Dismiss, and this cannot be
                    // dismissed - it is true until the phone is set up.
                    Plate(tone = chrome.warnInk.copy(alpha = 0.10f), outline = chrome.warnInk.copy(alpha = 0.35f)) {
                        Text(
                            SecurityRules.noCheckSentence(
                                security.method,
                                "Approvals that need the check are refused for now, and the app " +
                                    "lock and hidden lists stay shut.",
                            ),
                            style = MaterialTheme.typography.bodyMedium,
                            color = chrome.warnInk,
                            modifier = Modifier.liveStatus(),
                        )
                    }
                }
            }

            item(key = "app-lock") {
                Section("App lock") {
                    Plate {
                        SwitchRow(
                            title = "Lock Jarvis",
                            detail = "Opening Jarvis needs your fingerprint or phone PIN.",
                            checked = security.appLock,
                            enabled = !busy,
                            onChange = { onChange(security.copy(appLock = it)) },
                        )
                        Gap(12)
                        Setting(
                            "Lock again after",
                            caption = "How long Jarvis can be out of sight before it asks again. " +
                                "It also decides when hidden memory lists hide again.",
                        ) {
                            Choices(
                                options = RelockAfter.entries,
                                isSelected = { it == security.relockAfter },
                                label = { it.label },
                                enabled = !busy,
                                onPick = { onChange(security.copy(relockAfter = it)) },
                            )
                        }
                    }
                }
            }

            item(key = "approvals") {
                Section("Fingerprint for approvals") {
                    Plate {
                        Choices(
                            options = ApprovalCheck.entries,
                            isSelected = { it == security.approvals },
                            label = { it.label },
                            enabled = !busy,
                            onPick = { onChange(security.copy(approvals = it)) },
                        )
                        Gap(6)
                        Text(
                            "Risky means it leaves your PC, cannot be undone, was not labelled " +
                                "by Jarvis, or something tried to rush you. Denying never asks.",
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textLo,
                        )
                    }
                }
            }

            item(key = "private") {
                Section("Fingerprint for private lists") {
                    Plate {
                        SwitchRow(
                            title = "Hide memory lists",
                            detail = "On Mind, what Jarvis wants to remember, what it believed on a " +
                                "date, the wiki's list of your notes and your chat history stay " +
                                "hidden until you tap Show and confirm it is you.",
                            checked = security.privateLists,
                            enabled = !busy,
                            onChange = { onChange(security.copy(privateLists = it)) },
                        )
                        Gap(6)
                        Text(
                            "Chat answers are not hidden. Your PC does not say which answers used " +
                                "your email, calendar, notes or memory, so this phone cannot tell " +
                                "them apart.",
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textLo,
                        )
                    }
                }
            }

            item(key = "method") {
                Section("What counts as you") {
                    Plate {
                        Choices(
                            options = CheckMethod.entries,
                            isSelected = { it == security.method },
                            label = { it.label },
                            enabled = !busy,
                            onPick = { onChange(security.copy(method = it)) },
                        )
                        Gap(6)
                        Text(
                            "Fingerprint only leaves out the phone's PIN. Only a fingerprint or " +
                                "face that Android rates as strong counts. Many phones' face " +
                                "unlock does not, so on those use your fingerprint.",
                            style = MaterialTheme.typography.bodySmall,
                            color = chrome.textLo,
                        )
                    }
                }
            }

            item(key = "rules") {
                Text(
                    "Saved on this phone only, never sent to your PC. Turning something on is " +
                        "instant. Turning something off, or making it looser, asks for your " +
                        "fingerprint or PIN first. The notification and the widget can deny, " +
                        "never approve.",
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
            }
        }
    }
}

/**
 * What the whole app shows while the app lock is shut. Nothing behind it
 * is composed, so nothing from Jarvis is on screen - or in the recent-apps
 * picture, which MainActivity also turns off while the lock is on.
 */
@Composable
fun LockedScreen(
    /** Why the last try did not open it, or null. */
    message: String?,
    busy: Boolean,
    onUnlock: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val chrome = LocalChrome.current
    Column(
        modifier.fillMaxSize().background(chrome.surface0).padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            "Jarvis is locked",
            style = MaterialTheme.typography.titleLarge,
            color = chrome.textHi,
            modifier = Modifier.semantics { heading() },
        )
        Gap(8)
        Text(
            "Use your fingerprint or phone PIN to open it.",
            style = MaterialTheme.typography.bodyMedium,
            color = chrome.textMid,
            textAlign = TextAlign.Center,
        )
        if (message != null) {
            Gap(12)
            Text(
                message,
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.warnInk,
                textAlign = TextAlign.Center,
            )
        }
        Gap(24)
        Primary("Unlock", modifier = Modifier.fillMaxWidth(), busy = busy, enabled = !busy, onClick = onUnlock)
    }
}

/**
 * A Mind section whose contents are hidden by "Hide memory lists". The
 * title stays, so the owner knows what is there; the contents are not
 * composed at all until Show is confirmed.
 */
@Composable
internal fun HiddenSection(title: String, busy: Boolean, onShow: () -> Unit) {
    val chrome = LocalChrome.current
    Section(title) {
        Plate {
            Text(
                "Hidden. Tap Show and confirm it is you.",
                style = MaterialTheme.typography.bodyMedium,
                color = chrome.textMid,
            )
            Gap(6)
            Quiet(if (busy) "Checking…" else "Show", enabled = !busy, onClick = onShow)
        }
    }
}
