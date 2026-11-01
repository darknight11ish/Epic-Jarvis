# Install the Jarvis notes bridge

This is the by-hand guide. It puts the plugin into a **test vault** first, where
nothing you do can hurt your real notes.

> **Test vault first. Every time.**
> Do **not** copy this plugin into your live vault until the Lead or the owner
> says so. Nothing in this work has been installed into the live vault, and the
> plugin's editing half is not on the live backend yet (see **What works
> today** below).

Read [README.md](README.md) for what the plugin is, and
[SECURITY.md](SECURITY.md) for what it can and cannot do.

## Before you start

| You need | How to tell |
|---|---|
| Obsidian `1.13.0` or newer | Obsidian's own **Settings -> About** shows the version. |
| The three plugin files | `manifest.json`, `main.js`, `styles.css`, in the `obsidian-plugin` folder of this repository. |
| Jarvis running on this PC | The Jarvis desktop app is open, or the backend is running. Default address: `http://127.0.0.1:4719`. |
| The Jarvis token | Step 5 says where to get it. Do not paste it into a note, a chat or a screenshot. |
| A second vault | Step 1. This is the throwaway one. |

If `main.js` is not in the `obsidian-plugin` folder, build it first - in that
folder, in a terminal:

```powershell
npm install; npm run build
```

## Step 1 - Make (or choose) a test vault

In Obsidian: **Create new vault** -> name it `Obsidian Test Vault` -> **Create**.

A vault is just a folder of notes with a hidden `.obsidian` folder inside it.
This second vault is your laboratory: it has its own settings, its own
plugins, and none of your real notes. If you delete it later, you lose only
test notes.

Note the folder path - Obsidian shows it under the vault's name on the vault
picker, for example `C:\Users\pcadmin\Documents\Obsidian Test Vault`.

## Step 2 - Copy three files into it

The plugin goes in a folder named after its id, inside the vault's plugins
folder:

```
<test vault>\.obsidian\plugins\jarvis-notes-bridge\
    manifest.json
    main.js
    styles.css
```

**By hand (File Explorer).** Open the repository's `obsidian-plugin` folder.
Select `manifest.json`, `main.js` and `styles.css`, and copy them. Then open
your test vault folder, open `.obsidian`, open `plugins`, and make a new folder
called `jarvis-notes-bridge`. Paste the three files into it. If `.obsidian` or
`plugins` is not visible, Windows is hiding folders whose name starts with a
dot: in File Explorer, **View -> Show -> Hidden items**.

**Or one line in PowerShell.** Set `$vault` to your test vault's path, then
paste the whole line. It makes the folders, copies the three files and ends by
telling you where they landed:

```powershell
$vault = "C:\Users\pcadmin\Documents\Obsidian Test Vault"; $src = "C:\Users\pcadmin\Documents\Jarvis github\Epic-Jarvis-main\obsidian-plugin"; New-Item -ItemType Directory -Force "$vault\.obsidian\plugins\jarvis-notes-bridge" | Out-Null; Copy-Item "$src\manifest.json","$src\main.js","$src\styles.css" -Destination "$vault\.obsidian\plugins\jarvis-notes-bridge\" -Force; "Files copied to $vault\.obsidian\plugins\jarvis-notes-bridge"
```

Change `$src` if your copy of this repository lives somewhere else. If
`styles.css` is not in the folder yet, copy `manifest.json` and `main.js` only
- the plugin still loads, it just looks plain.

The folder must contain `manifest.json` directly. A folder inside a folder
(`...\jarvis-notes-bridge\obsidian-plugin\manifest.json`) will not be seen.

## Step 3 - Turn the plugin on

In the test vault, open **Settings -> Community plugins**.

1. If Obsidian offers **Turn on community plugins**, press it first.
2. In the **Installed plugins** list, find **Jarvis notes bridge** and turn its
   switch on. Obsidian may ask you to confirm that you trust it - read the
   [SECURITY.md](SECURITY.md) page first if you like, that is exactly what it is
   for.

If the plugin is not in the list: press **Ctrl+R** to reload Obsidian, or close
and reopen it. A new plugin folder is only picked up when Obsidian looks again.

## Step 4 - Set the backend address

**Settings -> Jarvis notes bridge**.

The row is called **Jarvis backend URL**, and it is already
`http://127.0.0.1:4719`, which is the address of Jarvis on this PC. Leave it
alone unless you know it moved.

If you ever put an address that is not this PC in that field, the plugin shows
a warning right under it: "This address is not on this PC. The Jarvis token
would be sent to that host - only do this if you mean it." A loopback address
is `127.0.0.1`, `localhost` or `::1` - anything else is another computer, and
this project never opens a public tunnel.

## Step 5 - Give it the token

The plugin needs the same token the phone uses. It is the Jarvis backend's
"pairing token".

**Where it comes from - pick one:**

- **The Jarvis desktop app:** open its **Settings** and find the card that says
  **"Your phone needs the same token"**. Press **Show the token for my phone**
  and copy what appears. It is 43 characters.
- **A terminal, in the backend folder:**
  `py -3 jarvis_token_store.py show` prints it. This is the command that shows
  the token on purpose - do not run it while somebody can see your screen, and
  do not paste its output into a file.

Never type the token into a note, a chat message, a screenshot or an issue.

**Where it goes - pick one.** The plugin's settings show the secret picker and
the fallback field; the plain "secret's name" field appears only if your
Obsidian version cannot show the picker:

- **Token in SecretStorage (preferred).** This is the picker. It lists the
  names of secrets in Obsidian's own secret storage and can make a new one:
  give it a name you will recognise (for example `jarvis`) and paste the token
  as its value. The plugin then saves only the **name**. You can also make the
  secret centrally in Obsidian's own **Settings -> Secret storage** and pick it
  here afterwards.
- **Token in SecretStorage - the secret's name.** Only shown when the picker is
  not available. Type the name, never the token.
- **Fallback token (stored on this PC, not encrypted by Obsidian).** For a test
  vault, or when secret storage is not available. The row says plainly where the
  value goes: this plugin's `data.json`, in the vault's `.obsidian` folder, in
  plain text. It is masked on screen, and it is fine for a throwaway test vault.

If your Obsidian has no **Secret storage** section, check the version under
**Settings -> About**. Update Obsidian, or use the fallback field for now and
move to a secret once the update is in.

A good sanity check: the token is around 43 characters, no spaces. If you
pasted a whole sentence or a file path, copy it again.

## Step 6 - Press Test connection

**Settings -> Jarvis notes bridge -> Test connection.** It makes one cheap read
(`GET /api/notes/templates`), does not call the model, and answers in plain
words:

| Answer | What it means |
|---|---|
| **Connected. This Jarvis knows N template name(s).** | The address, the token and the backend all agree. |
| **Not connected: No Jarvis token yet...** | Step 5 has not been done, or the secret name does not match a secret. |
| **Not connected: Could not reach the local Jarvis...** | Nothing answered at that address. Is Jarvis running? See [When it fails](#when-it-fails). |
| **Not connected: Jarvis refused the token (HTTP 401)...** | The token is wrong or from an older install. Copy it again in full. |
| **Not connected: Jarvis does not have this route yet (HTTP 404)...** | Expected before the backend deploy - see below. Your token may be perfectly fine. |

## Step 7 - Open a note and try it

1. Open any note in the test vault.
2. Click the speech-bubble ribbon icon on Obsidian's left edge. Hovering it says
   **Open the Jarvis panel**. The panel opens on the right and shows that note's
   title, path, headings, links and frontmatter keys.
3. In the panel's ask box, type a question about the note and press **Ask**. The
   answer appears in the panel. The ask itself writes nothing; if Jarvis decides
   to do something, its own approval card appears on the PC, never here.
4. Run **Capture to today's note** from the command palette (**Ctrl+P**, then
   type `Jarvis`). Type a sentence, send it, and look at your PC: Jarvis raises
   its ordinary card there. Nothing is written until you answer that card on
   the PC.

## What works today, and what will not

| Action | Today |
|---|---|
| The panel, the note's shape, **Ask** | Works - these are read-only. |
| **Capture to today's note** | Works - and it raises a card on the PC that you answer there. |
| Test connection, status bar | Until the backend deploy they honestly report a missing route: **Not connected: Jarvis does not have this route yet (HTTP 404)...** in the settings, and **Jarvis: notes routes not deployed** in the status bar. Your token can be perfectly fine. |
| Bold, Italic, Checklist, Replace, Set tag | Wait for the deploy. Until then the plugin says the backend does not have the route yet. |
| Insert under heading, the template dropdown, creating a note | Wait for the deploy, for the same reason. |

The reason is written out in [README.md](README.md#known-limits): the editing
routes are built in this repository on PR #1049 and are not in the live backend
until that deploy happens.

The full honest lists are in
[README.md](README.md#what-is-proven-and-what-is-not-tested) (what has never
been tested) and [SECURITY.md](SECURITY.md#known-limits) (what the plugin can
and cannot protect you from).

## When it fails

Work down this list. Each line is something to check, in order.

| What you see | Check this |
|---|---|
| **Jarvis: unreachable**, or **Not connected: Could not reach the local Jarvis. Is the desktop Jarvis running on this PC?** | Is the Jarvis desktop app open? Jarvis has to be running on this PC. Then check the port: `Test-NetConnection 127.0.0.1 -Port 4719 -InformationLevel Quiet` - `True` means something is listening, `False` means nothing is. |
| **Jarvis: no token (Settings)**, or **Not connected: No Jarvis token yet...** | Step 5. If you used the secret picker, check the name you picked still exists in Obsidian's **Secret storage**. |
| **Jarvis: token refused**, or **Not connected: Jarvis refused the token (HTTP 401)...** | The token is wrong or from an older install. Copy it again in full from **Show the token for my phone**. |
| **Jarvis: notes routes not deployed**, or **Not connected: Jarvis does not have this route yet (HTTP 404)...** | Not a mistake you made before the deploy - see **What works today**. Ask and Capture still work. |
| The plugin is not in **Community plugins** | The files are in the wrong place. They must be at `<vault>\.obsidian\plugins\jarvis-notes-bridge\manifest.json`. Then **Ctrl+R**. |
| Turning it on shows an error | Press **Ctrl+Shift+I** (the developer console), open the **Console** tab, and read the red line that mentions `Jarvis notes bridge`. That line is the real error; the on-screen notice is only a summary. |
| The panel opens but is empty | Click into a note first. The panel describes the **active** note; with no note open there is nothing to describe. |
| Capture says a card is waiting, but no card appears | Look at the Jarvis desktop app - the card is raised there, never inside Obsidian. |
| **Could not ask Jarvis: ...** | Read the rest of that sentence - it is Jarvis's own reason (a route this backend does not have, a note that changed, or a note that is too big). Nothing was written. |

Two more things worth knowing when something looks broken:

- The status bar wording is the quickest diagnosis. The table in
  [README.md](README.md#the-status-bar) says what each one means.
- The plugin does not print the token in messages or errors; the only place it
  appears is the field or the secret you put it in. The desktop app's **Show
  the token for my phone** does show it, so close your screen share before you
  press that one.

## Uninstall

1. **Settings -> Community plugins**, turn **Jarvis notes bridge** off.
2. Delete the folder `<vault>\.obsidian\plugins\jarvis-notes-bridge\`. That
   also deletes `data.json`, which is where the fallback token was kept.
3. If you made an Obsidian secret just for this plugin, remove it in Obsidian's
   **Settings -> Secret storage** - secrets there belong to the whole vault, so
   other plugins could use the same name.
4. If you want to change the token itself, that is a backend job and it affects
   every Jarvis client, including the phone. [SECURITY.md](SECURITY.md#revoke-the-token)
   has the exact steps.

## The one rule for now

**Never point this at the live vault until the Lead or the owner says so.**

A test vault is a second, throwaway vault: same Obsidian, different folder,
none of your real notes. The plugin is built and checked in this repository and
has not run on any real notes yet. When the editing half is deployed and the
owner has said yes, the install is the same steps - with the live vault's path
in step 2.
