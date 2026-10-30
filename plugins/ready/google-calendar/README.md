# google-calendar

Your own Google Calendar, both ways, and you pick one:

- **Private link (read-only)** - the secret iCal address Google gives every
  calendar. One box in Settings, Accounts; Jarvis can read it and cannot
  change it.
- **Google sign-in (read/write)** - a real OAuth sign-in over a redirect that
  comes back to **this PC only** (127.0.0.1). Jarvis can then read the
  calendar and add, change or delete an event. Every change waits on its own
  approval card showing the exact event.

**Turning it on today is three commands in the backend folder** - there is no
Settings card for it yet, because every Settings card in this program is a Rust
command and `src-tauri/src/lib.rs` is where the parallel account-connect work
is:

```
py -3 jarvis_google_calendar.py client <client-id>    then paste the secret, hidden
py -3 jarvis_google_calendar.py mode google
py -3 jarvis_google_calendar.py connect
```

`status`, `where`, `mode ical`, `mode off` and `disconnect` are beside them.
`docs/GOOGLE-CALENDAR-SETUP.md` is the one-time Google Cloud setup, click by
click.

**Drop-in, and this one replaces NO patch.** Nothing about `jarvis_hud.py`
changes to add this: the feature was born as a folder. Copy this folder into
the backend's `jarvis_plugins\` folder and restart Jarvis.

    Copy-Item plugins\ready\google-calendar "$env:JARVIS_BACKEND\jarvis_plugins\" -Recurse

- Module the loader calls: `jarvis_google_calendar.install()` (takes the
  core's Handler)
- Routes: `GET /api/google-calendar/status`,
  `GET /api/google-calendar/events?days=7`, `POST /api/google-calendar/start`,
  `POST /api/google-calendar/cancel`, `POST /api/google-calendar/disconnect`,
  `POST /api/google-calendar/mode`, `POST /api/google-calendar/client`,
  `POST /api/google-calendar/events`, `POST /api/google-calendar/events/update`,
  `POST /api/google-calendar/events/delete`
- Position in the loader's order: 160, after `antislop` at 159, so its routes
  are checked in the order they were added rather than in the middle of
  somebody else's.
- The patch this replaces: none - this is a new feature, not one that used to
  be a patch.

## What leaves this PC, and what never does

- **The browser sign-in.** `POST /api/google-calendar/start` binds
  `HTTPServer(("127.0.0.1", 0))` - a random port on loopback - and hands the
  Google sign-in address to your own default browser. Google sends the answer
  back to `http://127.0.0.1:<that port>/callback`. There is no ngrok, no
  Cloudflare Tunnel, no Tailscale Funnel, and nothing to configure: Windows
  will not even accept a connection to that port from another machine.
- **PKCE and `state`.** The code verifier never leaves the process, the
  challenge goes to Google, and the callback is answered only when its `state`
  matches the one this flow started with. A wrong or missing state is refused
  and NOTHING is exchanged.
- **The refresh token** goes into Windows Credential Manager (DPAPI) under
  `Jarvis Backend/Google Calendar refresh token`, through the same
  `jarvis_token_store` helper the rest of the backend uses. Access tokens live
  in memory only. Neither is ever written to a file, a log line, a route
  answer, a card or a model prompt, and the phone never holds either.
- **The client secret** goes into Credential Manager under
  `Jarvis Backend/Google Calendar client secret`. The client ID is not a
  secret, so it sits in `google-calendar.json` beside `accounts.json`.

## Before it can work at all: one Google Cloud setup, once

About ten minutes, free, and only you can do it (it needs your Google
account). `docs/GOOGLE-CALENDAR-SETUP.md` walks through it click by click:
create a project, enable the Calendar API, fill in the OAuth consent screen,
add yourself as a test user, create a **Desktop app** OAuth client, and then
give the two strings to Jarvis with `jarvis_google_calendar.py client <id>`
in the backend folder (it asks for the secret with the typing hidden). There
is no Settings card for this yet, which is why the commands above are the way
in.

**Said plainly:** `calendar.events` is a *sensitive* scope. In "Testing" mode
with yourself as a test user it works, and only you can use it - but Google
deletes a Testing-mode refresh token after about 7 days, after which Jarvis
says "the saved Google permission has expired - connect again". Publishing the
app ("In production") with this scope means Google's verification review. That
is Google's rule, not Jarvis's.

## Adding it: the catalogue, or the folder by hand

This folder is in `plugins/registry.json` under `folders` (a drop-in that
replaces no patch), so the catalogue script knows it by name:

```
scripts\add-plugin.ps1 -Name google-calendar -BackendPath "D:\your\backend"
```

`add-plugin.ps1` reads its names from `plugins/registry.json` and copies this
folder into the backend's `jarvis_plugins\`, which is also what the
`Copy-Item` line above does if you would rather do it yourself. If a future
`tools/gen_plugin_catalogue.py` run ever leaves it out, run that generator -
never hand-edit the registry.
