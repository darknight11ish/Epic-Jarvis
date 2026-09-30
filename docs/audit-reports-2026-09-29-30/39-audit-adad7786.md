# Report 39 (audit), agent adad7786, 2026-09-30T07:06Z

> **What it was asked** (first 600 characters of the task): Read-only audit of /home/user/Epic-Jarvis (read CLAUDE.md first; verify each claim with file:line + quote; 'not checked' honestly; change no files). AREA: PERMISSION MINIMISATION as a set. (1) Android: jarvis-client/app/src/main/AndroidManifest.xml (and jarvis-android if it still ships): list every <uses-permission>, <queries>, exported component, intent-filter, foreground service type, receiver, provider, allowBackup/dataExtractionRules/fullBackupContent, usesCleartextTraffic/networkSecurityConfig (rule 2: only Tailscale/Meshnet; can the app reach any public host? any http cleartext allowed -

> This is a sub-agent's own report, saved word for word. It is model output: it was
> checked only as far as the report itself says. Line numbers were read, not run.

---

PERMISSION MINIMISATION AUDIT (read-only, nothing changed). Overall: the phone and desktop are tight. No rule is broken. There is one real gap (F1), two smaller ones, and two things I could not check. Answers to "one card or two": these are security findings and none of them need a graphics card.

Checked: jarvis-client AndroidManifest.xml, network_security_config.xml, data_extraction_rules.xml, MainActivity.kt intent handling, all of tauri.conf.json, all 10 capabilities/*.json, and innerHTML use in the desktop src.

RANKED FINDINGS
| # | Sev | Finding | Smallest fix |
|---|---|---|---|
| F1 | Medium | Any app on the phone can send MainActivity an action to start the microphone (Live) | See below |
| F2 | Low | The quickbar window holds `approvals` and `task-control` and also renders model text via innerHTML | Keep as is; add a test (see below) |
| F3 | Low | CSP `script-src 'unsafe-inline'` is on for every window | Move inline scripts out to files, then drop it |
| F4 | Info | `SET_ALARM`, `MODIFY_AUDIO_SETTINGS` and `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` are declared and used | None needed |

F1 detail. MainActivity is `android:exported="true"` (Manifest line 138). It handles these actions from any sender, with no check on who sent them: START_LIVE, RESUME_LIVE, OPEN_HANDOFF, and the shortcut actions START_VOICE, ASK_BRIEF_ME and QUICK_NOTE.
- MainActivity.kt:605 reads `ACTION_START_LIVE -> if (fresh) startLiveRequested.value = "start"`.
- MainActivity.kt:1441-1447 then does `if (locked) return...` and otherwise `JarvisRuntime.liveStartSoon(...)`.
- So with App lock OFF, another app could start Live and the microphone. This is not an approval or a rule-4 break. It is a "another app starts the mic" gap.
- Android's rule about starting microphone services from the background probably limits it, but I did not verify that. The Live tile's own comment says a mic service "may only start from an app in front".
- I did not check whether App lock is on by default. I also did not check START_VOICE, ASK_BRIEF_ME or QUICK_NOTE handling, or whether they send anything. From the shortcut comments they look like fixed text.
- What it cannot do: no approve or deny action is reachable this way. The approval id extra (line 584) only focuses a card. Nothing here starts screen capture; that needs Android's own prompt.
- Owner choice, recommendation first:
  (a) Recommended: in `readLiveIntent`, honour START_LIVE and RESUME_LIVE only when the intent comes from this app's own PendingIntent or an internal extra token. Tiles and notifications keep working.
  (b) Leave it; the mic indicator shows and Live only starts when the app is unlocked.

F2 detail. capabilities/quickbar.json holds `approvals`, `task-control`, `live` and `screen-watch`. main.js:845, 1071 and 1997 use innerHTML, but on `renderMarkdown`/`escapeHtml` output.
- markdown.js escapes `& < > " '` before adding any markup and only links http(s).
- main.js:1854 `code.innerHTML = html` builds only from `escapeHtml`'d lines, so it is safe.
- Windows that show untrusted text but hold weak commands: HUD (no approve, no memory write, per its own capability text), widget (uses textContent, widget.js:1058), faces and floating (no approvals).
- Escaping looks correct, but if it ever regressed, XSS in the quickbar would reach `approvals`. The quickbar is the one window where that would matter.
- Fix: a test that fails on any new innerHTML in main.js that skips `escapeHtml`/`renderMarkdown`. I did not check whether one exists.
- The CSP has no remote script sources, `connect-src` is `'self'`, IPC and 127.0.0.1:4719 / localhost:4719 only, `object-src 'none'`, `form-action 'none'`, and the asset protocol is disabled. There is no `remote` block and no shell, fs or http plugin grant in the capability files.
- Two smaller notes: `core:webview:allow-internal-toggle-devtools` is on brain, faces, quickbar and widget. The HUD capability says release builds have no devtools (Cargo feature); I did not verify Cargo.toml. The updater endpoint has `"pubkey": ""` while `createUpdaterArtifacts` is false, so it is inert, but a filled endpoint with an empty key would be unsafe; keep it off.

F3 detail. `script-src 'self' 'unsafe-inline'` weakens the CSP if any XSS ever slips through. It is a hardening item, not a live hole.

RULE 2 (no public route)
- Network security config: base cleartext is refused. Cleartext is allowed only for `ts.net` (with subdomains), `nord` (with subdomains), `localhost` and `127.0.0.1`. `.local`, `.lan` and 192.168.x are deliberately excluded and the reason is written in the file.
- The phone can reach public hosts over https only. The one built-in public call is UpdateCheck.kt:31, `https://api.github.com/repos/darknight11ish/Epic-Jarvis/releases/tags/client-latest`.
  - It has a setting to turn it off, sends nothing from Jarvis, and takes no link from the reply (RELEASE_PAGE is a fixed constant).
  - It still touches an outside host. It is fine under the rules, but say so in the privacy text.
- Backup: `allowBackup="false"` and `dataExtractionRules` exclude everything for both cloud backup and device transfer. Good.
- minSdk 33, targetSdk 36. I found no `debuggable` in the manifest; build.gradle.kts mentions it only in comments, and I did not read the release block.

PERMISSION TABLE (client manifest)
- INTERNET, ACCESS_NETWORK_STATE: needed. Keep.
- FOREGROUND_SERVICE, FOREGROUND_SERVICE_SPECIAL_USE (link, overlay), _MICROPHONE (WakeWord, Live), _MEDIA_PROJECTION (Watch): each type matches a service in the manifest. All are `exported="false"`. Keep.
- POST_NOTIFICATIONS: runtime grant. Keep.
- RECORD_AUDIO: requested when the mic is first held. Keep.
- CAMERA: only for scanning the pairing QR, `required="false"`. Could be dropped if typed-code pairing were enough; keep for QR.
- PACKAGE_USAGE_STATS: used in ScreenWatchService.kt:273 (UsageStatsManager) to know which app is in front during "Watch with me". Owner-enabled special access. It is the most sensitive item here and is feature-gated: without it, Watch does not start. Keep, but it is the first candidate to drop if Watch is ever cut.
- SYSTEM_ALERT_WINDOW: only for the "Floating Jarvis: Overlay" mode, and the owner has to grant it in Android settings. Optional; Bubble mode avoids it.
- SET_ALARM: used at ComingUpPlate.kt:484; hands the alarm to the Clock app. Keep.
- MODIFY_AUDIO_SETTINGS: used for the echo-cancelling call mode. Keep.
- REQUEST_IGNORE_BATTERY_OPTIMIZATIONS: used at MainActivity.kt:3381, asked for from the readiness screen. Keep.
- RECEIVE_BOOT_COMPLETED: BootReceiver is not exported. Keep.
- USE_BIOMETRIC, WAKE_LOCK, QUERY_ALL_PACKAGES, SMS_DELIVER, RECEIVE_SMS, READ_SMS: NOT declared in jarvis-client. The grep found no WAKE_LOCK or QUERY_ALL_PACKAGES use in Kotlin. The only WAKE_LOCK, VIBRATE and ACCESS_WIFI_STATE declarations are in the older jarvis-android manifest.
- Biometric: it is probably via androidx.biometric, whose permission merges in from the library, so it does not appear in the manifest source. I did not verify this.

SMS. There is NO SMS permission and no SMS-handler capability. Manifest lines 36-38 are only a `<queries>` entry naming the `SMS_DELIVER` action, so the phone can ask "which app is the default SMS app" (`Telephony.Sms.getDefaultSmsPackage`) and refuse to read that app's notifications. That supports the rule "never text messages", so it does not contradict it. It is a read-only visibility declaration. The other `<queries>` entry, MAIN/LAUNCHER, is the documented alternative to QUERY_ALL_PACKAGES and is used so the notification-app picker works.

Notification reading: PhoneNotificationListenerService is `exported="false"` and bound with BIND_NOTIFICATION_LISTENER_SERVICE. The owner grants it in Android's own screen, and the PC switch and per-app allow list gate it on top. Good.

EXPORTED COMPONENTS
- MainActivity (launcher, SEND text, SEND image, ASSIST): exported for the reasons above. Shared text goes into a chip and is never sent on its own (comments at lines 158-165 and 200-203). `readShareIntent` (MainActivity.kt:621-642) only sets draft state. So shared text is treated as outside text, as required.
- ShareToLive alias: exported, text only.
- The voice-interaction and recognition services are exported but protected by BIND_VOICE_INTERACTION and BIND_RECOGNITION_SERVICE, so only the system can bind them.
- The 4 Quick Settings tile services (LinkTile, QuickTile One/Two/Three, LiveTile) are exported, protected by BIND_QUICK_SETTINGS_TILE. The tile actions never include Approve or Deny.
- The five widget receivers are exported, and each accepts APPWIDGET_UPDATE only.
- I did not check every widget button's own PendingIntents.

X-Jarvis-Client header: JarvisApi.kt:2693 defines `CLIENT_HEADER = "X-Jarvis-Client"` and the comment at 639 says it is sent even on the unauthenticated path. UpdateCheck deliberately omits it because that is not a Jarvis request. Consistent with the rule.

NOT CHECKED
- Backend: routes needing the token, unauthenticated routes, CORS and the pairing routes live in `jarvis_hud.py`, which is outside this repo. The patches in `backend/` do not show a public bind; `jarvis_big_model.py:142` pins `HOST = "127.0.0.1"`. The 0.0.0.0 grep hits were tests and docs, plus a wildcard rejection in the desktop. I did not read `validate_bind_address` in commands.rs.
- jarvis-android (older app): manifest exists, I only listed its permissions. It still declares WAKE_LOCK, VIBRATE, ACCESS_WIFI_STATE and RECORD_AUDIO. I did not audit its components. Since it cannot talk to the backend, the smallest fix is to stop shipping it (the README says it no longer publishes).
- Kotlin was not compiled and nothing was run.

Owner question (short, one only):
Should other apps be able to start Live?
- (a) Recommended: no; internal launches only.
- (b) Leave as is.
