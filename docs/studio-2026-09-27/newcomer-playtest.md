# Newcomer play test (condensed by main session; agent could not write files)
Ran check-backend.ps1, apply-patches.ps1, selftest --preflight on fake folders under pwsh 7.

Give-up points:
1. No backend download (INSTALL.md:85-97). apply-patches.ps1:908 says "needs the OpenJarvis backend folder" - OpenJarvis is unrelated (INSTALL :86-90, :1106). Wrong-download trap.
2. Desktop build from source: updater signing key empty (tauri.conf.json:118), no installer; README.md:112 desktop-latest link -> release does not exist.
3. Phone reach: 5 things must be right, nothing checks them together. `100.x:4719` -> "must not include a port ... JARVIS_HUD_PORT" (commands.rs:784). Loopback-only Jarvis shows as "Jarvis isn't running" on phone (setup audit F4). "Let my phone reach this" only works if desktop app starts Jarvis, INSTALL 1.8 starts by hand.

NEW BUG (VERIFIED by main session): desktop shows key grouped in fours with spaces (settings.js:284 groupInFours); nothing says to drop spaces; phone TokenStore.setToken only trims ends (TokenStore.kt ~72); MainActivity.kt:1155 passes token as typed. Fix: strip all whitespace on phone; "without the spaces" hint on PC.

Still open from earlier audits: ease #3 (phone menu row hidden by default AppearanceStore.kt:644; "Platform checks" name; no hint on empty Home), #9 signing key, QR pairing, jarvis-client/README.md missing, owner's folder path hard-coded (8 INSTALL commands + README + both scripts). Setup audit S6, S10/D1, D2 "Start here" card, D3/F2 crash status + auto-restart never resets, F4, F6-F8, I7 OLLAMA_NO_CLOUD.
Contradiction: CLAUDE.md "Phone: allow home-network addresses" + README.md:81-82 vs code: phone only Tailscale/Meshnet names (network_security_config.xml:59-64, INSTALL.md:628-638).
Other: apply-patches creates _jarvis-logs before "NOTHING HAS BEEN CHANGED"; "send the block above back" (1451,1839); "-Revert" w/o full command (1513,1530); voice section in 13,748-line README; INSTALL 3.2 reads as fix history; branch name claude/admiring-ritchie-5urg5h in desktop README + desktop-release.yml.
Time: 2-3 h, ~8 programs for owner; impossible for others.
Competitors: LM Studio/Jan one installer; Open WebUI one docker line + PWA; OpenClaw QR / short setup code at top of first phone screen.
15-min plan: tiny (strip spaces; fix OpenJarvis line; README 81-82 + CLAUDE.md wording w/ owner OK; accept :4719); small (Quick start at top of INSTALL; scripts auto-find backend; phone-reach preflight line; phone hint on "isn't running"); big (signing key -> installer; QR pairing; Start here card).
