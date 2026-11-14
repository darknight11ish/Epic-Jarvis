package com.jarvis.client.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import com.jarvis.client.data.SettingsBackup
import com.jarvis.client.ui.parts.Gap
import com.jarvis.client.ui.parts.Plate
import com.jarvis.client.ui.parts.Primary
import com.jarvis.client.ui.parts.Quiet
import com.jarvis.client.ui.parts.Secondary
import com.jarvis.client.ui.parts.Section
import com.jarvis.client.ui.parts.TextInput
import com.jarvis.client.ui.theme.LocalChrome

/**
 * Settings -> "Phone settings backup" (2026-11-13, the copy-over wave; the
 * owner-approved spec in `COPY-OVER-SPEC-2026-11-13.md`, section A1).
 *
 * WHAT IT IS. A locked file holding THIS phone's settings - the face and
 * colours, the menus shown, the voice and display switches, which apps Jarvis
 * may open, and which apps may tell Jarvis about a notification - so a phone
 * that is wiped or replaced can be set up again without tapping through every
 * switch. The list is [SettingsBackup.FILES], and it is deliberately short.
 *
 * WHAT IT IS NOT. It is not the PC's backup (that lives one row above, on the
 * "Backups" card, and stays the PC's). It is not chat history, not saved
 * memories, not pictures, not logs, and above all **not the pairing token**:
 * the token lives behind the Android Keystore in its own preferences file,
 * which is on [SettingsBackup.EXCLUDED_FILES] with its reason. A restored
 * phone pairs again, exactly as it would after a reinstall - which is what
 * makes the file safe to put on a USB stick.
 *
 * WHY THE PASSWORD IS ASKED FOR HERE, NOT READ OFF THE FILE. The file is
 * encrypted (PBKDF2 -> AES-256-GCM, `data/EncryptedBackup.kt`, adapted from
 * Mobile-Harness under MIT). There is no recovery: a forgotten password means
 * the file cannot be opened, and the app says so before the owner picks a
 * place to save it. A wrong password or a damaged file is refused with plain
 * words ([SettingsBackup.WRONG_PASSWORD], [SettingsBackup.DAMAGED]) and
 * nothing on the phone is changed.
 *
 * The two file dialogs belong to `MainActivity` (Android's own document
 * picker), so this plate only collects the password and hands it over. The
 * password never leaves the dialog's own state and is cleared by the caller
 * after the file is written or read.
 */
@Composable
internal fun PhoneBackupSection(
    busy: Boolean,
    line: String?,
    lineIsWarning: Boolean,
    onSave: (CharArray) -> Unit,
    onRestore: (CharArray) -> Unit,
) {
    val chrome = LocalChrome.current
    var mode by remember { mutableStateOf<PasswordMode?>(null) }

    Section("Phone settings backup") {
        Plate {
            Text(
                "Save this phone's own settings into one file, locked with a password you choose. " +
                    "On a new or wiped phone, restore that file instead of setting everything up again.",
                style = MaterialTheme.typography.bodySmall,
                color = chrome.textMid,
            )
            Gap(6)
            Text(
                "What goes in: the face and colours, which menus are shown, the voice and display " +
                    "switches, which apps Jarvis may open, and which apps may tell Jarvis about a " +
                    "notification.",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
            Gap(2)
            // Said as loudly as the good part, because this is the promise the
            // whole feature rests on.
            Text(
                "What never goes in: your pairing token, chats, saved memories, pictures or logs. " +
                    "A restored phone pairs with your PC again.",
                style = MaterialTheme.typography.labelSmall,
                color = chrome.textLo,
            )
            Gap(10)
            Primary(
                text = if (busy) "Working…" else "Save a backup",
                modifier = Modifier.fillMaxWidth(),
                enabled = !busy,
                busy = busy,
                onClick = { mode = PasswordMode.SAVE },
            )
            Gap(6)
            Secondary(
                text = "Restore from a backup",
                modifier = Modifier.fillMaxWidth(),
                enabled = !busy,
                onClick = { mode = PasswordMode.RESTORE },
            )
            line?.let {
                Gap(8)
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (lineIsWarning) chrome.warnInk else chrome.textHi,
                )
            }
            if (!busy && line == null) {
                Gap(6)
                Text(
                    "Nothing is saved or changed until you pick a file. The PC's own backups are " +
                        "on the row above - this card is this phone's settings.",
                    style = MaterialTheme.typography.labelSmall,
                    color = chrome.textLo,
                )
            }
        }
    }

    mode?.let { chosen ->
        PasswordDialog(
            mode = chosen,
            busy = busy,
            onCancel = { mode = null },
            onConfirm = { password ->
                mode = null
                if (chosen == PasswordMode.SAVE) onSave(password) else onRestore(password)
            },
        )
    }
}

private enum class PasswordMode { SAVE, RESTORE }

/**
 * The one question: what password? For a SAVE it is asked twice, because a
 * typo here is a file nobody can open, and there is deliberately no recovery.
 */
@Composable
private fun PasswordDialog(
    mode: PasswordMode,
    busy: Boolean,
    onCancel: () -> Unit,
    onConfirm: (CharArray) -> Unit,
) {
    val chrome = LocalChrome.current
    var password by remember { mutableStateOf("") }
    var again by remember { mutableStateOf("") }
    val save = mode == PasswordMode.SAVE
    var problem by remember { mutableStateOf<String?>(null) }

    Dialog(onDismissRequest = { if (!busy) onCancel() }) {
        Plate {
            Column(modifier = Modifier.heightIn(max = 460.dp).verticalScroll(rememberScrollState())) {
                Text(
                    if (save) "Lock this backup" else "Open a backup",
                    style = MaterialTheme.typography.titleSmall,
                    color = chrome.textHi,
                )
                Gap(6)
                Text(
                    if (save) {
                        "Choose a password. It is the only thing that opens this file - there is " +
                            "no recovery, and Jarvis never stores it or sends it anywhere."
                    } else {
                        "Type the password this backup was saved with. Nothing on this phone is " +
                            "changed unless it opens."
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = chrome.textMid,
                )
                Gap(10)
                TextInput(
                    value = password,
                    onValueChange = {
                        password = it
                        problem = null
                    },
                    modifier = Modifier.fillMaxWidth(),
                    label = "Password",
                    password = true,
                )
                if (save) {
                    Gap(8)
                    TextInput(
                        value = again,
                        onValueChange = {
                            again = it
                            problem = null
                        },
                        modifier = Modifier.fillMaxWidth(),
                        label = "Type it again",
                        password = true,
                    )
                    Gap(6)
                    Text(
                        "At least ${SettingsBackup.MIN_PASSWORD} characters. A short phrase you " +
                            "will remember beats one you write down.",
                        style = MaterialTheme.typography.labelSmall,
                        color = chrome.textLo,
                    )
                }
                problem?.let {
                    Gap(8)
                    Text(it, style = MaterialTheme.typography.bodySmall, color = chrome.warnInk)
                }
                Gap(12)
                Primary(
                    text = if (save) "Choose where to save it" else "Open the backup",
                    modifier = Modifier.fillMaxWidth(),
                    enabled = password.isNotEmpty() && !busy,
                    busy = busy,
                    onClick = {
                        val first = SettingsBackup.passwordProblem(password.toCharArray())
                        val mismatch = save && again != password
                        when {
                            save && first != null -> problem = first
                            mismatch -> problem = "The two passwords are different. Type the same one twice."
                            else -> onConfirm(password.toCharArray())
                        }
                    },
                )
                Gap(6)
                Quiet(
                    "Cancel",
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !busy,
                    onClick = onCancel,
                )
            }
        }
    }
}
