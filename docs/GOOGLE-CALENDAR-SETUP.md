# Connect Google Calendar: the one-time setup, click by click

**Date:** 2026-10-28. **What this is:** the ten minutes of setup only you can do,
because it happens inside your own Google account. Jarvis cannot do it for you,
and nothing in it costs money.

There are two ways to connect your calendar, and you only need one:

| way | what it gives you | what you do |
|---|---|---|
| **Private link (read-only)** | Jarvis can read your calendar. It cannot add, change or delete anything. | Paste one secret address. No Google Cloud, no sign-in. |
| **Google sign-in (read/write)** | Jarvis can read your calendar **and** add, change or delete an event - each change on its own approval card. | The setup on this page, once. |

The private link needs no setup page at all: it is the box that already exists in
Settings → Accounts ("Calendar's private iCal address"). In Google Calendar, open
**Settings** (the gear), pick your calendar on the left, scroll to **Integrate
calendar**, and copy **Secret address in iCal format**. Paste it in that box.

Everything below is only for the read/write way.

---

## What you are actually making

Google will not let a program read your calendar unless that program has been
registered with Google first. Registering one is free and takes ten minutes. What
Google gives you at the end is two strings:

- a **client ID** - long, ends in `.apps.googleusercontent.com`. This one is
  public: it appears in the address your browser visits.
- a **client secret** - short, starts with `GOCSPX-`. This one is a password.

Jarvis keeps the secret in Windows Credential Manager (encrypted to your Windows
account, never a file), and the client ID in its settings file, which holds no
secret.

---

## Step 1 - a project (about 1 minute)

1. Open <https://console.cloud.google.com> in your browser and sign in.
2. At the very top, click the project list (it says something like "My First
   Project" or "Select a project"), then **New project**.
3. Name it `Jarvis` and click **Create**. Wait a few seconds, then make sure the
   project list at the top says **Jarvis** - everything below happens inside the
   project you have selected.

## Step 2 - turn the Calendar API on (about 1 minute)

1. In the search box at the top, type `Google Calendar API` and open it.
2. Click **Enable**. When it finishes, the page says "API/Service enabled".

## Step 3 - the consent screen (about 4 minutes)

This is the screen Google shows when you sign in. It is also where you tell
Google who is allowed to use the app - only you, for now.

1. In the left menu: **APIs & Services** → **OAuth consent screen**.
2. Choose **External** and click **Create**. (External just means "not limited to
   one company's Google Workspace"; you will still be the only user.)
3. Fill in only what it insists on:
   - **App name**: `Jarvis`
   - **User support email**: your own address
   - **Developer contact information**: your own address
   Leave the logo and the links empty. Click **Save and continue**.
4. **Scopes**: click **Add or remove scopes**, tick
   `https://www.googleapis.com/auth/calendar.events`, and click **Update**, then
   **Save and continue**. (One scope, and it is the narrowest one that can list,
   create, change and delete events. Jarvis does not ask for access to your
   contacts, your email, your files or any other calendar.)
5. **Test users**: click **Add users**, type your own Google address, and click
   **Save and continue**. **This step matters**: while the app is in "Testing",
   only the addresses on this list can sign in.
6. Back on the summary, click **Back to dashboard**.

## Step 4 - the client (about 2 minutes)

1. Left menu: **APIs & Services** → **Credentials**.
2. Click **+ Create credentials** → **OAuth client ID**.
3. **Application type**: choose **Desktop app**. (This is the type that may
   redirect back to `http://127.0.0.1`, which is what Jarvis uses. If you pick
   "Web application" the sign-in will fail with `redirect_uri_mismatch`.)
4. Name it `Jarvis desktop` and click **Create**.
5. A box shows the client ID and the client secret. Keep it open, or click
   **Download JSON** - either way you need those two strings in the next step.

## Step 5 - give them to Jarvis (about 2 minutes)

**Where this happens today, said plainly:** there is no Settings card for this
yet. The Settings window has no door of its own to the backend (every Settings
card in this program is a Rust command, and that file is being edited by the
other account-connect work), so the setup is three lines in the backend folder,
the same shape `py -3 jarvis_token_store.py show` already uses. A Settings card
can be added later without changing any of this - the same routes are behind it.

Open a terminal in the backend folder (the folder holding `jarvis_hud.py`) and
run these three lines, one at a time:

```
py -3 jarvis_google_calendar.py client <paste the client ID here>
py -3 jarvis_google_calendar.py mode google
py -3 jarvis_google_calendar.py connect
```

1. The first line saves the client ID (which is public) and then **asks you for
   the client secret with the typing hidden**. Paste it and press Enter. It goes
   straight into Windows Credential Manager, is never shown again, and is never
   sent anywhere but Google's own token endpoint. Your shell's history never sees
   it.
2. The second line chooses the read/write way.
3. The third line opens your own browser at Google's sign-in page. Sign in,
   leave the permission boxes ticked, press **Allow**. The browser comes back to
   a page on this PC that says Jarvis is connected, and the terminal prints
   `Connected.`

If the browser did not open by itself, the same line prints the sign-in address -
paste it into your browser within ten minutes. After ten minutes it expires; run
`connect` again.

Other commands, for later:

```
py -3 jarvis_google_calendar.py status       what is connected, in words
py -3 jarvis_google_calendar.py where        where the token is kept (never the token)
py -3 jarvis_google_calendar.py disconnect   ask Google to forget it, and forget it here
py -3 jarvis_google_calendar.py mode off     stop using either way, KEEP the token
py -3 jarvis_google_calendar.py mode ical    use the private link instead
```

Was it really connected? `status` says `Connected: yes` and names the token's
Credential Manager entry. Nothing is guessed: a `yes` there means the sign-in
came back through this PC's own loopback listener and the refresh token was
written and read back.

---

## What "Testing" means, said plainly

Your app is in **Testing** mode, and that has two consequences Google imposes,
not Jarvis:

1. **Only the test users on your list can sign in.** That is you. Nobody else can
   use this client, even if they had the client ID.
2. **Google deletes a Testing-mode refresh token after about 7 days.** Jarvis
   will then say, in plain words, "the saved Google permission has expired -
   run `py -3 jarvis_google_calendar.py connect` in the backend folder again",
   and running that once more fixes it. Your calendar is not touched and
   nothing is lost.

To stop that expiring you would have to publish the app ("In production"), and
Google requires a **verification review** for the `calendar.events` scope - a
questionnaire and, for some scopes, a video of the app in use. That is Google's
rule, not Jarvis's, and this page will not pretend otherwise. For a personal
app used by one person, staying in Testing and re-connecting once a week is the
honest choice.

**Nothing here is a public tunnel.** The sign-in comes back to
`http://127.0.0.1:<a random port>/callback` - an address on this PC that only
this PC can reach. There is no ngrok, no Cloudflare Tunnel, no Tailscale Funnel,
and nothing to configure.

---

## If something goes wrong

| what you see | what it means | what to do |
|---|---|---|
| `redirect_uri_mismatch` at Google | the OAuth client is not a **Desktop app** | make a new client, type **Desktop app**, use its ID and secret |
| `access_denied` | you pressed Cancel, or the address you signed in with is not on the Test users list | add that address in step 3.5, try again |
| "the Google client secret has not been saved on this PC" | step 5's first line did not finish | run `client <id>` again and paste the secret |
| "the saved Google permission has expired" | Google deleted a Testing-mode token (about 7 days) | run `connect` again |
| "Google did not send a refresh token" | the consent boxes were unticked, or a second consent was skipped | run `connect` again and leave every box ticked |
| "That sign-in did not start here" | the callback did not match the sign-in Jarvis started (an old tab, or somebody else's link) | run `connect` again; Jarvis exchanged nothing the first time |

## Removing it

`py -3 jarvis_google_calendar.py disconnect` asks Google to forget the permission
and deletes the saved token from this PC. You can also see and remove the
permission yourself at <https://myaccount.google.com/permissions> - that is the
only reliable place if Google was unreachable when you disconnected.

Switching to **Off** (`mode off`) is different: it stops Jarvis using either way
and **keeps** the saved token, so you can switch back without signing in again.
