# Jarvis notes bridge

An Obsidian plugin that puts Jarvis in Obsidian's right-hand sidebar.

You can ask about the note you are reading, and make small, exact edits to it.
Every edit goes through Jarvis's own approval card, and that card is raised on
your PC and answered on your PC. The plugin never approves anything and never
writes a note itself.

This is a first-party Epic-Jarvis component - part of this project, not a
third-party plugin. It is a **client** for the Jarvis backend on the same
Windows PC.

| | |
|---|---|
| Plugin id | `jarvis-notes-bridge` |
| Display name | Jarvis notes bridge |
| Version | `0.1.2` |
| Needs Obsidian | `1.13.0` or newer |
| Runs on | Desktop only |
| Talks to | the Jarvis backend on this PC, default `http://127.0.0.1:4719` |
| Installed by | copying three files into a vault - it is **not** in Obsidian's community plugin directory |
| State | field test: built in this repository, **never installed in the owner's live vault** |

- **Putting it in place:** [INSTALL.md](INSTALL.md) - step by step, into a
  **test vault**.
- **Checking the safety claims:** [SECURITY.md](SECURITY.md) - what the plugin
  can and cannot do, where the token lives, and the commands that prove it.

## What it does, in two waves

### Wave 1 - read, ask, capture

Ask and Capture work with the backend as it is today. The status bar and
**Test connection** use the template-list route as their cheap health check, so
before the deploy they will honestly say the notes routes are not deployed yet
(see **Known limits**).

| What | Details |
|---|---|
| Ribbon icon and panel | Click the ribbon icon (a speech bubble on Obsidian's left ribbon) and a **Jarvis** panel opens on the right. |
| The note's shape | The panel shows the active note's title and path, its headings, outgoing links, inbound links, unresolved links and frontmatter keys. It reads all of that from Obsidian's own metadata cache - the index Obsidian already keeps. Obsidian's in-memory copy of the note's text is read read-only whenever the panel refreshes and when you ask; it only leaves this PC (to the local Jarvis) when you ask. |
| Bounds | The panel displays the first 30 headings and links per list, and the ask context carries up to 80 headings, 80 links and 60 frontmatter keys. A note with more is cut at those fixed bounds - not a setting. |
| Ask | Type a question in the panel's box and the answer appears in the panel, under "Read-only: Jarvis answers here." The ask writes nothing by itself, but it is an ordinary Jarvis turn: if Jarvis decides to do something, its own card appears on the PC, never here. Up to 12,000 characters of the note, and up to 12,000 characters of any selected text, go with the question; it does not send the whole vault. |
| Selection ask | With text selected, the panel's question carries the selection too. The command **Ask Jarvis about the selection** does the same from the editor. |
| Capture | The command **Capture to today's note** opens a small box, prefilled with your selection. What you type is filed into today's daily note by the same route the desktop `#obs` capture uses. The panel has a **Capture selection** button for the same thing. |
| Capture's answer | The box shows Jarvis's own sentence back, and says plainly: "This plugin cannot approve cards. If a card appears, answer it in the Jarvis window on the PC - nothing is written before you do." |
| Status bar | On desktop, a small item at the bottom right of the window says what the connection is doing (table below). |

### Wave 2 - small, structured edits

This is the half that needs the deploy described under **Known limits**. Every
one of these is one card on the PC.

| What | Details |
|---|---|
| Selection actions | **Bold**, **Italic**, **Checklist** and **Replace...** act on the text you have selected. **Set tag...** works on the whole note. |
| Insert under heading | Pick one of the note's own headings from a dropdown, type the text, and insert one line under that heading. The heading list comes from Obsidian's metadata cache, so it is the note's real headings. |
| Templates | A dropdown of template names: Jarvis's list (names only) and the `.md` files in the vault's Templates folder, merged, with the source shown in brackets. Choosing one previews its first 600 characters - read-only - and creates a note through Jarvis. A name that only Jarvis knows is shown but cannot be used: no route sends template text back, so the plugin will not invent a body. The new note goes to the vault root unless you type another vault-relative path, and a name that already exists is refused by the backend. |
| What a write looks like | The plugin shows the PC's own card sentence, then "A card is waiting on the PC. This plugin cannot approve cards: answer it in the Jarvis window on the PC." It asks the backend every few seconds for up to 10 minutes. If the card is still unanswered then, it says it stopped checking and how to see the outcome later; once the card is answered it shows the backend's own final sentence: **saved**, **denied**, **failed** or **conflict**. It never says "saved" before the backend says saved. |

## The safety model

Three rules. They are properties of the code, not promises - [SECURITY.md](SECURITY.md)
has the commands that check them against the file Obsidian actually loads.

1. **One card, and the PC owns it.** A write is a request to Jarvis. Jarvis
   raises its ordinary approval card on the PC, the owner answers it on the
   PC, and only then does anything touch a note. The plugin never calls
   `/api/approve` or `/api/deny`; it has no code to do so.
2. **The plugin never writes the vault.** It calls `vault.modify` nowhere,
   never replaces text in your editor itself, creates no file and uses no
   `obsidian://` write action. The bytes are changed by the backend, after the
   card, through the same File Guardian copy and Undo every other Jarvis note
   write uses.
3. **The token stays here.** It is sent in one header, to the one backend URL
   you configured, and nowhere else. It is never logged, never put in a URL,
   never written into a note, and never printed in a message or an error.

The two safety nets you may already know are unchanged and stay in the backend,
not in the plugin: the **File Guardian** (the old bytes are copied before a
write, so a bad edit is recoverable) and **Undo**.

## Why Obsidian only

The desktop app and the phone have their own notes screen in this repository -
browse the vault, open a note, edit it, save it through the same one-card routes
this plugin calls. They do not need a second one, and they could not draw one
inside Obsidian's window anyway.

This plugin exists for the one job the other two cannot do: be the Obsidian
side, inside Obsidian, next to the note that is already open.

It is marked `isDesktopOnly` in its manifest, so Obsidian's mobile app will not
load it. That is on purpose, and the reason is concrete rather than a matter of
taste: the backend address it calls is this PC's own loopback (`127.0.0.1`), and
on a phone `127.0.0.1` would be the phone, not this PC.

That reason belongs in `docs/ARCHITECTURE.md` section 8 ("One-sided on
purpose"), where the project records deliberate one-sided features. It is
written here instead because this change does not edit that file.

## The routes it calls

These and no others. Every request carries the same headers:

| Header | Value |
|---|---|
| `Content-Type` | `application/json` |
| `X-Jarvis-Token` | The token, read at request time (see [SECURITY.md](SECURITY.md)) |
| `X-Jarvis-Client` | `hud` |
| `X-Jarvis-Surface` | `desktop` |

**Read-only**

| Route | What it is for |
|---|---|
| `GET /api/notes/templates` | The template names Jarvis knows. Names only - never template text. It is also the cheap health check behind the status bar and the **Test connection** button. |
| `GET /api/notes/read?path=<vault-relative path>` | Reads one note's bytes hash (`sha256`), so an edit can carry the hash of the version it started from. The text that comes back is never used to write anything. |
| `POST /api/chat` with `"stream": false` | Asks Jarvis a read-only question about the note or the selection. |

**Writes - each one goes through Jarvis's own one-card route**

| Route | Body | What it does |
|---|---|---|
| `POST /api/notes/capture` | `{"target":"obsidian","text":"..."}` | Files text into today's daily note. The same route the desktop `#obs` capture uses. |
| `GET /api/notes/capture?id=<job id>` | - | How that capture ended (polled). |
| `POST /api/notes/insert` | `{"path","text","mode":"under_heading","target","expected_sha256"}` | Adds one line under the chosen heading. |
| `POST /api/notes/format` | `{"path","target","style":"bold"\|"italic","action":"add","expected_sha256"}` | Wraps the selected text. |
| `POST /api/notes/replace` | `{"path","old","new","expected_sha256"}` | Replaces the selected text - one exact, whole-word occurrence. |
| `POST /api/notes/customize` | `{"path","action":"line","line_action":"checklist","target":<the whole line>,"expected_sha256"}` | Turns the selection's line into a checklist item. |
| `POST /api/notes/tag` | `{"path","tag","action":"add","where":"auto","expected_sha256"}` | Sets one tag on the note. |
| `POST /api/notes/create` | `{"path","text"}` | Creates one new note from a template. The template text is read read-only from the vault's Templates folder. |
| `GET /api/notes/change?id=<job id>` | - | How one write ended: `waiting`, `saved`, `denied` or `failed` (polled). |

**It never calls** `/api/approve` or `/api/deny`. It never writes the vault
itself. It never uses an `obsidian://` write action. It sends the token to the
configured backend URL and to no other address.

`expected_sha256` is the note's hash from when the edit started. If the note
changed in between, the backend refuses the write instead of overwriting
somebody else's edit, and that is the **conflict** the panel reports.

## Settings

**Obsidian Settings -> Jarvis notes bridge**

| Setting | Default | What it means |
|---|---|---|
| **Jarvis backend URL** | `http://127.0.0.1:4719` | Where Jarvis is listening on this PC. Loopback means `127.0.0.1`, `localhost` or `::1`. Anything else shows a warning on the same screen: "This address is not on this PC. The Jarvis token would be sent to that host - only do this if you mean it." |
| **Token in SecretStorage (preferred)** | none chosen | The picker for a secret in Obsidian's own secret storage. The plugin stores the **name**; the value is read when a request is made. |
| **Token in SecretStorage - the secret's name** | empty | Only shown when this Obsidian version cannot show the picker: the same setting as a plain field. The field holds the name only, never the token. |
| **Fallback token (stored on this PC, not encrypted by Obsidian)** | empty | For a test vault, or when secret storage is not available. Masked on screen, and saved in this plugin's `data.json` inside the vault folder, in plain text. |
| **Templates folder** | `Templates` | The vault folder the template list and preview read `.md` file names from. Read-only. |
| **Test connection** | button | Makes one cheap read (`GET /api/notes/templates`) and says what came back: "Connected. This Jarvis knows N template name(s)." or "Not connected: ..." It never calls the model. |

## Commands

Open the command palette with **Ctrl+P**, then type `Jarvis`. No command has a
default hotkey; you can assign one in Obsidian's **Settings -> Hotkeys**.

| Command | What it does |
|---|---|
| **Open the Jarvis panel** | Same as clicking the ribbon icon. |
| **Ask Jarvis about this note** | Opens a read-only ask dialog about the active note. |
| **Ask Jarvis about the selection** | Asks about the selected text. It only appears in the list while an editor is open. |
| **Capture to today's note** | Opens the capture box, prefilled with the selection. |
| **Through Jarvis: make the selection bold** | Wave 2. One card. |
| **Through Jarvis: make the selection italic** | Wave 2. One card. |
| **Through Jarvis: turn the selection's line into a checklist item** | Wave 2. One card. |
| **Through Jarvis: replace the selection...** | Wave 2. One card. |
| **Through Jarvis: tag this note...** | Wave 2. One card. |
| **Copy an Obsidian link to this note (read-only)** | Copies an `obsidian://open?vault=...&file=...` link to the clipboard, so it can be pasted where a note can be opened. It builds an open link only - never a URI write action. |

## Links back to Obsidian (the read-only direction)

The other half of "fully integrated" is the way **back** to the note. This
plugin does its half without writing anything: **Copy an Obsidian link to this
note** puts one link on the clipboard, in the shape Obsidian's own URI
documentation defines:

```
obsidian://open?vault=<vault name>&file=<vault-relative path>
```

The vault name is the name Obsidian shows; the path uses `/` and is
URL-encoded. A `#Heading` can be added after the file to jump to a section
(`%23Heading` once encoded) - the helper supports it even though the command
copies the whole note.

**Only `open` is ever built.** Obsidian's URI scheme also has actions that
change a note at once (`new` with `prepend`/`append`, `daily`, `unique`). This
plugin builds none of them, and a test pins that: a link is a way to *look* at
a note, never a way to change it. Every change in this project goes through
Jarvis's one card, the File Guardian copy and Undo, and an instant URI write
would bypass all three. The Jarvis desktop and chat lanes can use the same
`obsidian://open` shape to send the owner back to a note; that direction
belongs to those lanes, not this plugin.

## The status bar

On desktop, the item at the bottom right of the Obsidian window says
`Jarvis:` and then one of these. It checks when Obsidian starts, when you switch
notes, and once a minute after that; **Test connection** repaints it too.

| Reads | Means | What to do |
|---|---|---|
| `Jarvis: checking…` | The first check has not finished. | Wait a second. |
| `Jarvis: connected` | The token was accepted and the backend answered. | Nothing. |
| `Jarvis: no token (Settings)` | No token is set. | Do step 5 of [INSTALL.md](INSTALL.md). |
| `Jarvis: unreachable` | Nothing answered at that address. | Is Jarvis running? Is the port right? See [INSTALL.md](INSTALL.md#when-it-fails). |
| `Jarvis: token refused` | The backend answered and said no. | The token is wrong or belongs to an older install. Copy it again. |
| `Jarvis: notes routes not deployed` | The backend answered `404` to the cheap template-list health check. | Expected before the notes-routes deploy - see **Known limits**. Your token may be perfectly fine. |
| `Jarvis: HTTP 404` (or another number) | The backend answered with a status this plugin has no friendlier sentence for. | Read the Test connection row in Settings for the backend's own words. |

If the check fails in some other way, the item shows `Jarvis:` and the first 60
characters of the reason.

## What is proven, and what is not tested

**Checks this folder offers.** Run them yourself; a green run is the proof, not
this table.

| Command | What it checks |
|---|---|
| `npm run typecheck` | The TypeScript source type-checks. |
| `npm run build` | `esbuild.config.mjs` bundles `src/` into the `main.js` Obsidian loads. |
| `npm test` | The node tests in `tests/` (`protocol`, `templates`, `safety`). Needs Node 22.18 or newer, because they read the TypeScript source directly. |
| `npm run test:sandbox` | The same tests in one process, for a locked-down environment that refuses the child processes `node --test` starts (it fails there with `spawn EPERM`; that is the environment, not a test). |
| `npm run check` | Type-check, build, then `npm test`, in order. |
| the greps in [SECURITY.md](SECURITY.md) | The shipped `main.js` contains no approve, no deny and no direct vault write. |

**Not tested.** Said plainly, so nobody reads this document as a field report:

- loading in Obsidian;
- the SecretStorage / SecretComponent UI;
- the right-side panel rendering;
- `requestUrl` from Obsidian's Electron process against the live backend;
- real card flows (capture / insert / format / replace / customize / tag / create);
- polling `/api/notes/change`;
- the status bar;
- vaults larger than the context bounds.

## Known limits

**The editing routes are not on the live backend yet.** `insert`, `format`,
`replace`, `customize`, `tag`, `create`, `templates` and `change` are built in
this repository on PR #1049 and are **not** in the owner's live backend until
that deploy happens. Before it, those buttons answer honestly that this
backend does not have the route yet. **Only Ask and Capture work live.**

**An edit's first step needs a notes route too.** Every edit to an existing
note starts by reading that note's current hash (`GET /api/notes/read`) - a new
note from a template does not, because there is no note to read yet. That read
belongs to the same not-yet-deployed notes work, so the edit buttons have two
reasons to be unavailable until the deploy, and the plugin names the missing
route rather than guessing a hash.

**This work has never been installed into the owner's live vault.** A test
vault only. [INSTALL.md](INSTALL.md) says so at the top, on purpose.

**Not in the community directory.** There is no community review, no signature
and no update channel. You copy these files by hand, and you update them by
hand.

**The plugin runs inside Obsidian.** Anything a plugin can do, this plugin
could do; [SECURITY.md](SECURITY.md) argues from the shipped bundle rather than
from trust.

## Build it, package it, install it

The runtime files - the three you copy into a vault - are:

| File | What it is |
|---|---|
| `manifest.json` | The plugin's identity: id, name, version, minimum Obsidian, desktop-only. |
| `main.js` | The bundle Obsidian loads. Built from `src/`, not edited by hand. |
| `styles.css` | The panel's styling. |

`versions.json` is release metadata, not a runtime file.

From this folder:

```powershell
npm install; npm run build
```

`main.js` is written next to `manifest.json`. If `main.js` is already in the
folder, the folder is ready to copy without building.

Then follow [INSTALL.md](INSTALL.md). Do not copy it into the live vault until
the Lead or the owner says so.

### Where the source lives

`main.ts` used to be one file. It is split now, and `esbuild.config.mjs` bundles
the pieces back into the single `main.js` Obsidian loads.

| File | What it is |
|---|---|
| `src/main.ts` | The plugin: ribbon icon, commands, status bar, start-up. |
| `src/client.ts` | The requests to Jarvis: URLs, headers, and waiting for an answer. |
| `src/panel.ts` | The right-side panel. |
| `src/settings.ts` | The settings tab. |
| `src/modals.ts` | The ask, capture, replace and tag dialogs. |
| `src/protocol.ts` | The shapes of what goes to Jarvis and what comes back. |
| `src/templates.ts` | Template names and the read-only preview. |
| `src/types.ts` | Shared TypeScript types. |
| `tests/` | The node tests behind `npm test`. |

## What changed in the repository

This plugin is additive. **This folder is the only tree change.** No existing
shipped file was modified - no source, no document, no workflow. The one other
change that belongs to this work is the release note,
`changelog.d/2026-10-31-obsidian-plugin.md`, which is how this project records a
user-visible change.

The reason Obsidian-only is written in this README rather than in
`docs/ARCHITECTURE.md` section 8 is the same: this change does not edit that
file.
