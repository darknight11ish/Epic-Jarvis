# Security and privacy - Jarvis notes bridge

This page is for anyone deciding whether to trust this plugin with a vault. It
says what the plugin can do, what it cannot do, where the token lives, and how
to check the important claims yourself - including the exact commands that
check the shipped file Obsidian loads.

Plain words first: **the plugin asks Jarvis to change a note, and Jarvis asks
you first.** The plugin holds no approval power and writes no note.

## What the plugin can do

- Read the **active note's metadata** from Obsidian's own cache: title, path,
  headings, outgoing/incoming/unresolved links, frontmatter keys.
- Read up to 12,000 characters of the active note, and up to 12,000 characters
  of the selected text, to send with a question.
- Ask Jarvis a question (`POST /api/chat`) and show the answer.
- Ask Jarvis to file text into today's daily note.
- Ask Jarvis to make one small, exact edit: insert under a heading, bold,
  italic, checklist, replace, set a tag, create a note from a template.
- Read the template **names** Jarvis knows, and the first ~600 characters of a
  template file in your vault, to preview it.
- Show a status item and a settings tab.

That is the whole list. Everything it sends goes to the one backend address you
configure.

## What it cannot do

| It cannot | Why not |
|---|---|
| Approve or deny a card | It never calls `/api/approve` or `/api/deny`, and it has no code that could. The card is raised on the PC and answered on the PC. |
| Write, create, delete or rename a note itself | Nothing calls `vault.modify`, and it does not create or delete notes either - creation goes through Jarvis, after a card. Changes are made by the backend, with the File Guardian copy and Undo. |
| Drive Obsidian through `obsidian://` links | It uses no `obsidian://` write action; the vault is not changed by asking Obsidian to change it. |
| Talk to any other computer | The only address in the bundle is the backend URL, default `127.0.0.1:4719`. No telemetry, no analytics, no crash reporting, no update check, no remote fonts or images. |
| Keep working when the token is wrong | The backend answers `401` and the plugin reports it. Nothing is raised, nothing is written. |
| Hide what it did from you | Every write is a card on your PC with Jarvis's own sentence, and the answer is the backend's own sentence - saved, denied, failed or conflict. |

## The token

The plugin needs the same token the phone uses: the Jarvis backend's **pairing
token**. On this PC it normally lives in **Windows Credential Manager** under
`Jarvis Backend/pairing token`, encrypted to your Windows account (DPAPI).

| Question | Answer |
|---|---|
| Where do I get it? | The Jarvis desktop app's **Settings -> "Your phone needs the same token" -> Show the token for my phone**. Or, in the backend folder, `py -3 jarvis_token_store.py show`. Both show it on purpose. |
| Where does the plugin keep it? | **Preferred:** it stores the **name** of a secret in Obsidian's secret storage and reads the value when it makes a request. **Fallback:** the value itself, in this plugin's `data.json`, inside the vault folder - plain text, warned about on the settings screen. |
| How does it travel? | As the `X-Jarvis-Token` header, on a request to the configured backend URL, and nowhere else. |
| Is it ever in a URL? | No. Query strings carry the note's vault-relative path, never the token. |
| Is it ever logged? | No. There is no console logging anywhere in the plugin's source, and the token never goes into a note. The one file it can reach is `data.json`, and only if you use the fallback field. |
| Is it ever printed? | Not in a message and not in an error. The fallback field holds it, masked, and that is the only place in the plugin it appears. |

**Wrong token, in order:** the backend answers `401` with the sentence *bad or
missing X-Jarvis-Token*; the status bar reads `Jarvis: token refused`; no card
is raised; nothing is written. Fix it by copying the token again in full from
the desktop app (the plugin trims surrounding spaces, so a stray space is not
the cause).

**A note on Obsidian's secret storage.** It is Obsidian's own vault-wide store,
not this plugin's private box. Another plugin in the same vault can ask for a
secret by its name. That is still better than plain text, because the value is
not sitting in a file you might sync or copy - but it is not a wall between
plugins. Treat every plugin in a vault as code you trust.

## The one-card rule, and why the plugin cannot approve

Every write in this project goes through the same door: Jarvis's approval card,
raised by the PC backend, answered on the PC. A note edit is no different. The
plugin sends the request and then **waits** - it polls the backend for the
outcome and shows you the backend's own sentence.

The plugin cannot approve because:

- approving is a different route (`/api/approve`), and the plugin never calls it;
- the only thing the plugin can send is a *request* for a change; the yes is a
  separate action on the PC;
- the card appears on the PC, not in Obsidian, so there is nothing in Obsidian
  to click that would count as a yes.

The safety nets are the backend's, and they are the same ones every other note
write uses: the **File Guardian** copies the old bytes before a write, and
**Undo** reverses it. If the note changed since the edit started, the write is
refused as a **conflict** instead of overwriting the newer version.

This is also the limit, said plainly: the card is the boundary, and the backend
trusts the token. A program already running on this PC that holds the token
could approve a card. That is exactly why the token is kept in Credential
Manager rather than in a file, and why a leaked token matters.

## The greps that prove it

Run these in the `obsidian-plugin` folder - against `main.js`, the file you
actually copy into your vault, not against the TypeScript source. Checking the
bundle checks what Obsidian runs.

**1. No approval, no denial, no direct vault write.** This must print nothing:

```powershell
Select-String -Path main.js -SimpleMatch -Pattern 'vault.modify','/api/approve','/api/deny'
```

Silence is the result you want. If a line appears, that line is a finding, not a
style note. The design also never creates, deletes or renames a note, so
`'vault.create','vault.delete','vault.trash','vault.rename'` are a fair addition
to that pattern list - they printed nothing when this page was written, and the
command is there so it stays that way.

**2. The token is a header.** This prints the line where the header is set:

```powershell
Select-String -Path main.js -SimpleMatch -Pattern 'X-Jarvis-Token'
```

What you see is source code. No token value can appear, because the token is
never in the bundle - it is read at run time.

**3. Every web address in the bundle.** This lists each one it finds:

```powershell
Select-String -Path main.js -Pattern 'https?://[A-Za-z0-9._:/-]+' -AllMatches | ForEach-Object { $_.Matches.Value } | Sort-Object -Unique
```

Expected: `http://127.0.0.1:4719`, and the same address with a full stop after
it where a sentence in the code names it. Nothing else.

If another address appears, read it. A web address inside a comment is
harmless; a request to it would not be. The plugin's own claim is that there is
no other host at all.

**What these commands can and cannot prove.** They prove these three things
about this bundle as it is written: nothing calls an approve or deny route,
nothing writes the vault directly, and no other host is present. They are not a
mathematical proof - a determined author could hide a call another way. The
stronger check is reading `src/`, which is why it is in the same folder, in
small files.

## Localhost only

The default backend URL is `http://127.0.0.1:4719` - a loopback address, which
means the request never leaves this PC. The settings screen treats `127.0.0.1`,
`localhost` and `::1` as this PC.

If you type any other address, the plugin shows this warning right under the
field: *"This address is not on this PC. The Jarvis token would be sent to that
host - only do this if you mean it."* Do not ignore it. If this PC is ever
reached from other devices, it is over Tailscale or NordVPN Meshnet (private
device-to-device networks). **This project never opens a public tunnel** - no
ngrok, no Cloudflare Tunnel, no Tailscale Funnel - and nothing in this plugin
changes that.

## No telemetry, no network beyond the backend

There is no analytics, no phone-home, no crash uploader, no usage counter and
no update check. The plugin does not download anything. It makes one kind of
call: an HTTP request, using Obsidian's own `requestUrl`, to the backend URL in
its settings.

Obsidian's developer console may still contain Obsidian's own messages; that is
Obsidian, not this plugin.

## Known limits

Said plainly, because a security page that only lists strengths is marketing:

1. **A plugin runs inside Obsidian, with the same power as Obsidian.** It could,
   in principle, do anything the app can do. This page argues from the shipped
   bundle (the greps above), not from trust. Community plugins are trusted code
   by design, and "Trust author" is a real decision.
2. **The code is not signed.** There is no signature or published hash to compare
   against. You have the files because they came out of this repository's
   `obsidian-plugin` folder. Copy them from there and from nowhere else.
3. **It is not in Obsidian's community directory.** No community review, no
   publisher verification, no automatic update channel. Updates are a manual
   copy of three files.
4. **The fallback token is plain text** in `data.json` inside the vault folder.
   It is protected by your Windows account and nothing else. Use the secret
   picker when you can.
5. **Obsidian's secret storage is shared per vault.** Another plugin in that vault
   can read a secret by name.
6. **Another program running as you can read the token from Credential
   Manager.** The backend's own module says so: moving it out of a plain file
   stops it appearing in backups and file searches, not a program that asks the
   same Windows account. This is a limit of the PC, not of this plugin.
7. **One token is shared by every client** - the desktop app, the phone and this
   plugin. Changing it means pairing everything again.
8. **The plugin has no rate limit of its own.** It can ask often; every write
   still needs a card.
9. **Not tested against the live backend, in a real Obsidian, by a person.** The
   list is in [README.md](README.md#what-is-proven-and-what-is-not-tested). This
   page describes the design and the code, not a field test.
10. **A card can be approved by any program holding the token.** See the end of
    **The one-card rule**. The token is the real credential; the plugin just
    carries it.

## Revoke the token

Turn it off, then take the token away. Do as much as you need, in this order:

1. **Stop the plugin:** Obsidian **Settings -> Community plugins**, turn
   **Jarvis notes bridge** off.
2. **Delete its copy:** delete `<vault>\.obsidian\plugins\jarvis-notes-bridge\`.
   That removes `data.json`, and with it any fallback token.
3. **Remove the secret** in Obsidian's **Settings -> Secret storage**, if you made
   one for this plugin.
4. **Change the token itself** - only if you think it has leaked, because every
   Jarvis client must be paired again afterwards:
   - If you ever typed a token into the **Jarvis desktop app's Settings**, press
     its **Clear token** button first. `forget` below cannot remove that one, and
     the desktop passes it to the backend when it starts Jarvis.
   - In the backend folder, `py -3 jarvis_token_store.py forget` deletes the
     stored token. The next start makes a new one and every device must pair
     again. `py -3 jarvis_token_store.py where` says where it is kept, without
     printing it.
   - If `HUD_TOKEN` is set in your Windows environment, that value wins over the
     stored one. Remove it with
     `[Environment]::SetEnvironmentVariable('HUD_TOKEN', $null, 'User')` and
     open a new terminal window.
   - To see the entry yourself: **Control Panel -> Credential Manager ->
     Windows Credentials -> "Jarvis Backend/pairing token"**.
5. **Put the new token into the plugin** - step 5 of [INSTALL.md](INSTALL.md) -
   and re-pair the phone.

## If something looks wrong

Tell the owner. Do not paste the token, a screenshot of the settings screen
with **Show the token for my phone** open, or the contents of `data.json` into
an issue, a chat or a note. If you must show the settings screen, clear the
fallback field first - the secret picker shows a name, not a value.
