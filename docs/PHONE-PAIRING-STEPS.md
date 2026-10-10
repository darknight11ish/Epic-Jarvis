# Pairing your phone, step by step, with the real labels

> **Where every word in this page comes from.** Written 2026-10-05. Every
> button name, screen title and error sentence below was read out of the code
> in this repository **at commit `acf3ffbdb0a703aa140aa41db7ffba2774db45a6`**
> (`origin/main`, "Merge pull request #49 from darknight11ish/next-tick-sweep"
> — the merge commit itself). Nothing here is remembered or guessed; each claim
> names the file and line it was read at.
>
> This page changes no product code. It is a description of what the code
> already does.

---

## Read this first: the one step most likely to go wrong

**Pairing does nothing at all unless Windows Hello (a PIN is enough) is set up
on this PC.** The approval card that lets a phone in is a "PC only, always
Windows Hello" card (`backend/jarvis_owner_check.py:126`, the
`PC_ONLY_ACTIONS` set). On a PC without Windows Hello the card is **refused**,
and the phone never gets a key. If you are not sure, set up a PIN first:
Windows Settings → **Accounts** → **Sign-in options** → **PIN (Windows
Hello)**.

Two other things bite before anything else can work, in this order:

1. **Tailscale (or NordVPN Meshnet) must be on, on both devices**, at home
   too. The phone cannot use your home Wi-Fi address (`docs/INSTALL.md:812-822`).
2. **A Windows Firewall rule must let the port through**, or the phone is
   blocked while everything looks right (`docs/INSTALL.md:892-917`). That is
   the `New-NetFirewallRule` line in step 3 below.

---

## 1. The APK: how it is built, what it is called, where it comes from

### There are two Android apps, and only one of them can talk to Jarvis

| Workflow file | Which app | Artifact name | Published? |
|---|---|---|---|
| `.github/workflows/android-apk.yml` | **`jarvis-android`** (the OLD app) | `jarvis-android-debug-apk` (line 170) | **No** — the file says so itself at lines 175-188: "This workflow no longer publishes a release" |
| `.github/workflows/jarvis-client.yml` | **`jarvis-client`** (the app that works) | `jarvis-client-release-apk` (line 342) | **Yes** — the `client-latest` release, main only |

`jarvis-android` "speaks a WebSocket protocol invented before
`JARVIS-API.md` existed, and none of its endpoints are implemented
server-side" (`android-apk.yml:177-182`, and `CLAUDE.md`'s project section).
**Do not install that one.** The reason the old one stopped publishing is
written in the workflow: two similar links where one silently cannot work "is
a trap rather than a choice".

### What triggers a build

- **`android-apk.yml`** (lines 14-29): `workflow_dispatch` (manual) **and**
  every push to **any** branch, but only when the push touches
  `jarvis-android/**`, `keystore/**` or that workflow file itself. Its own
  comment (lines 3-12) explains the path filter: a generic detector used to
  pick between the two Gradle roots by filesystem order, so the artifact's
  contents were decided by `readdir`.
- **`jarvis-client.yml`** (lines 3-19): `workflow_dispatch` (manual) **and**
  every push touching `jarvis-client/**`, `keystore/**`,
  `.github/workflows/jarvis-client.yml`, `backend/**`,
  `jarvis-desktop/src/**`, `jarvis-desktop/src-tauri/src/**`,
  `jarvis-desktop/tests/fixtures/**` or `VERSION`.

Both are also runnable by hand from the repository's **Actions** tab
(`workflow_dispatch`).

### Does it actually run on `main`?

**Yes.** `main`'s own copy of `jarvis-client.yml` is read here, at commit
`acf3ffbd`, and it does have the `client-latest` publish step (lines 1025-1094,
gated on `github.ref == 'refs/heads/main'`, line 1027). The most recent commits
to touch that file on `main` are `b8095be0`, `a313968a`, `ddfa664d` and
`4c401553` ("CI: publish the phone APK from main only") — all present in
`main`'s history, none of them disabling it.

**One honest gap, not established:** the restore step needs the repository
secret `DEBUG_KEYSTORE_B64` (line 54). If that secret is missing the job stops
on purpose with a loud error (lines 56-64). Whether the secret exists cannot
be checked from a checkout. If the run goes red at "Put the signing key back",
that is why.

**Another honest gap, not established:** whether the APK published at
`client-latest` right now was built from the current `main`. The release notes
say the branch and commit (line 1057), so read that line when you download.

### Where he downloads it

**The `client-latest` release page:**
`https://github.com/darknight11ish/Epic-Jarvis/releases/tag/client-latest`
(`docs/INSTALL.md:1001-1005`).

The file is named `jarvis-client-<short-commit>.apk`, for example
`jarvis-client-497563d.apk` (`jarvis-client.yml:1041`, and
`docs/INSTALL.md:1003-1005`). The release notes' first line is
"**Jarvis for Android $version** - from \`$branch\`, commit …" (line 1057).

**He does not need to build an APK.** GitHub builds it. The other run
artifact, `jarvis-client-release-apk`, is the same file but arrives as a zip
in a workflow run, which the GitHub phone app cannot download
(`jarvis-client.yml:1019-1024` says the plain `.apk` at a stable URL exists
precisely for that reason). Use the release page.

---

## 2. Installing it

Both ways are documented in `docs/INSTALL.md:1006-1016`.

**From the phone (the easier way),** `docs/INSTALL.md:1007-1010`:

> **On the phone:** open that page in the phone's browser and tap the
> `.apk`. The first time, Android asks to allow installing apps from that
> browser (Settings → Apps → *your browser* → **Install unknown apps** →
> Allow). Then tap Install.

**From the PC over USB,** the documented command, `docs/INSTALL.md:1011-1016`:

> turn on USB debugging on the phone (Settings → About phone → tap **Build
> number** seven times; then Settings → System → Developer options → **USB
> debugging**), plug it in, accept the prompt on the phone, and from the
> folder the APK is in:
> `adb install -r jarvis-client-<commit>.apk`. (`adb` comes with Google's
> "SDK Platform Tools", one line: `winget install --id Google.PlatformTools -e`.)

So the exact command, with the real filename pattern, is:

```powershell
adb install -r jarvis-client-<commit>.apk
```

`docs/INSTALL.md:1018-1030` also warns that from 2027 Google's developer
verification will add a one-time 24-hour flow for installing **by tapping the
file** on Google-certified phones, while **installing with `adb` stays
allowed**. That is a search summary of Google's announcement, not something
tried on a phone — the page says so itself.

If installing says `INSTALL_FAILED_UPDATE_INCOMPATIBLE`, the copy on the phone
was signed with a different key (`docs/INSTALL.md:1032-1034`,
`jarvis-client.yml:1067`). Uninstall once, install this one, and pair again.
**A first-time install cannot hit this.**

---

## 3. Pairing: the exact labels and the exact order of taps

### 3.1 On the PC, before anything else

**Tailscale (or NordVPN Meshnet) on the PC, signed in** — `docs/INSTALL.md:826-845`.

**Tell the backend to listen for the phone.** In Jarvis Desktop: tray icon →
**Settings and help…** → **Connection** → the field under
**Let my phone reach this** (`docs/INSTALL.md:854-860`). Type this PC's own
address on that network, which **looks like `100.x.x.x`** — the Tailscale or
NordVPN app shows it. Save.

> **The desktop box takes the `100.x` number; the phone takes the NAME**
> (`docs/INSTALL.md:869-872`). They are not the same field and not the same
> value. This is a real trap: the desktop refuses a name such as `mypc.nord`
> (`docs/INSTALL.md:880-883`) and the phone refuses a `100.x` number
> (`PhoneAddress.kt:56-60`).

**Restart the supervised Jarvis** so it reads the new bind address: same
Settings → **More options** → **Starting Jarvis for you** → **Stop**, then
**Start** (`docs/INSTALL.md:127-131`).

**Add the firewall rule.** In PowerShell **opened as administrator**
(right-click PowerShell → Run as administrator), one line
(`docs/INSTALL.md:901-903`, and the preflight checks the same line at
`backend/selftest.py:1850`):

```powershell
New-NetFirewallRule -DisplayName "Jarvis backend (private mesh only)" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 4719 -RemoteAddress 100.64.0.0/10 -Profile Any
```

If you answered **Cancel** or **Don't allow** to Windows' own prompt in the
past, it made a rule that *blocks* Python, and a block beats an allow —
`docs/INSTALL.md:907-917` gives the one line to list Python's rules and says
to delete the `Block` one.

**Windows Hello (a PIN is enough) must be set up** — see the top of this page.

### 3.2 On the PC: start the pairing

Jarvis Desktop → tray icon → **Settings and help…** → **Devices**.

There is a section headed **Devices** with this sentence
(`jarvis-desktop/src/settings.html:218-224`):

> Each phone gets its own key, and you can remove any one of them without
> touching the others. To add a phone, press **Pair a phone** and scan the
> code with the Jarvis app on that phone - over Tailscale or NordVPN Meshnet
> only.

Then, in order:

1. **First time only**, a field labelled **Your phone reaches this PC at**
   appears (`settings.html:230`). Its note says
   (`settings.html:234-238`): "This PC's Tailscale name (it ends in `.ts.net`)
   or its NordVPN Meshnet name (it ends in `.nord`). The Tailscale or NordVPN
   app shows it. You only type it once." **This is the phone's address, i.e.
   the NAME, not the `100.x` number** — the backend refuses a number here
   (`jarvis_devices.py:286-290`, `ADDRESS_NOT_A_NAME`).
2. Press **Pair a phone** (`settings.html:245`).
3. **What he should see** (`settings.html:250-266`, filled by
   `jarvis-desktop/src/devices.js:394-407`):
   - a **QR code picture**, with the alt text "The pairing code. Scan it with
     the Jarvis app on your phone." (`settings.html:252`);
   - under it: "Can't scan? Type this code on the phone: **K7QM-4TXD**"
     (`settings.html:253-256`);
   - "Works for 9:41 more" — a live countdown (`devices-words.js:61-67`);
   - a status line that starts as "Waiting for your phone…"
     (`jarvis_devices.py:231`).
   - a **Cancel** button.

The QR code and the code last **10 minutes**, work **once**, and die after
**3 wrong tries** (`jarvis_devices.py:152-153`, `SESSION_SECONDS = 600`,
`TRIES = 3`).

> **A safety note worth knowing:** while this panel is open, the settings
> window is hidden from screen capture — a screenshot, a screen recording or a
> meeting's screen share shows a black box instead of the code
> (`docs/PAIRING-DESIGN.md:599-606`). That is why a screenshot will not show
> the code.

### 3.3 On the phone

Open the Jarvis app. If nothing is paired yet, the pairing screen is what you
get. Its heading is **JARVIS**, with the line **Pair with your desktop** under
it (`PairingScreen.kt:195-200`). Above that, on a genuine first pairing only,
one picture and this sentence (`PairingScreen.kt:182-191`):

> This is Jarvis: an assistant that runs on your own PC, not someone else's
> server. Connect this phone to it below.

Then the two buttons, in this order (`PairByCode.kt:194-217`):

1. **Scan the code on your PC** — the filled button, the top one.
2. **Type the code instead** — the plain button under it.

Under both, a small line says: "On your PC: Settings, Devices, Pair a phone."
(`PairByCode.kt:213-217`).

**If he taps "Scan the code on your PC" for the first time**, Android asks for
the camera, after one sentence first (`Pairing.kt:81-82`,
`PairByCode.kt:223-234`):

> Jarvis uses the camera only to read the code on your PC. Nothing is
> recorded or sent.

The buttons on that explanation are **Continue** and **Type the code
instead**. Then: "Point the camera at the QR code on your PC."
(`PairByCode.kt:236-240`).

**Then, whether he scanned or typed, the same question**
(`PairByCode.kt:321-354`):

> **Connect to `<your-pc>.ts.net`?**
>
> Only if that is your PC. Your PC will show an approval card; nothing is
> handed over until you approve it there.

with a field **Name for this phone** (pre-filled with the phone's model, e.g.
"Pixel 9"; `PairByCode.kt:85` and `:340`) whose note reads "Shown on your PC's
card and in its list of devices." (`PairByCode.kt:341`). The buttons are
**Connect** and **Cancel**.

**If he typed instead** (`PairByCode.kt:270-320`), the two fields are:

- **Your PC's Tailscale or Meshnet name** — placeholder
  `your-pc.tailnet.ts.net  (or ….nord)`, with the note "The name the Tailscale
  or NordVPN app shows for your PC. Leave off :4719 and it is added for you."
- **Code (8 letters)** — placeholder `K7QM-4TXD`, with the note "Under the QR
  code on your PC. It works once, for 10 minutes."

and the buttons are **Next** and **Cancel**.

### 3.4 The four words, and the card

After **Connect**, the phone shows a block headed **Check the words**
(`PairByCode.kt:134-160`):

- the four words, large, centre, separated by ` · ` — for example
  `tulip · anchor · mellow · crane`;
- "**Approve the card on your PC if it shows these same words.**"
  (`Pairing.kt:80`, `APPROVE_IF_SAME`);
- "Waiting for the card on your PC. If the words are different, deny it
  there." (`PairByCode.kt:152-157`);
- a **Cancel** button.

The phone works the words out itself from the pairing secret and **refuses if
the PC's answer gives different ones** (`Pairing.kt:64-65`,
`WORDS_DIFFER` = "The PC answered with different words. Do not approve the
card on your PC."). It also refuses if the answer "did not come from the PC
that showed this code" (`Pairing.kt:66-67`). So the words are a real check,
not decoration.

---

## 4. What approves what: the card, word for word, and denying it

### The card's title

**"Jarvis wants to connect a new device"**

Read from the code, not the design: `backend/jarvis_devices.py:292`
(`CARD_TITLE = "Jarvis wants to connect a new device"`), produced by
`jarvis_card_words.title_for`, whose `TITLES` entry for the action is
`"pair_device": "connect a new device"` (`jarvis_card_words.py:160`) prefixed
with `LEAD = "Jarvis wants to "` (`jarvis_card_words.py:176`, `:232-239`).

### The card's body, word for word

`backend/jarvis_devices.py:1290-1299` (`def card_text`):

> "**Pixel 9**" is asking for its own key to talk to Jarvis.
> Check that phone shows these four words: **tulip · anchor · mellow · crane**
>
> Approve only if you are pairing that phone right now, on this PC. If you did
> not press "Pair a phone", deny this. You can remove the device any time in
> Settings, Devices.

(`{name}` is the phone's model or the name typed on the phone; the four words
are the live ones, joined with ` · `.)

### Where the card appears on the PC

In the usual card places — the Jarvis bar, the widget, or the phone's Home
screen (`jarvis-desktop/src/settings.html:322-324`). The Devices page states
plainly that it does **not** approve it there (`settings.html:214-216`: "The
approval itself is an ordinary card … never approved here").

It **always** asks Windows Hello and can **only** be approved on the PC
(`backend/jarvis_owner_check.py:126`; `docs/JARVIS-API.md:14716-14719`). On a
PC with no Windows Hello it is refused.

**The card lives 180 seconds** — the shipped `approval_timeout_seconds`
default (`backend/rebuilt/jarvis-framework.toml:79`). After that the phone
says "The card on your PC ran out of time. Start again on the PC."
(`Pairing.kt:69`).

The key is made **only after** the card is approved — never before, never held
in advance (`docs/PAIRING-DESIGN.md:518-519`, `jarvis_devices.py:1283-1287`).

### If he denies it

- The phone shows: "**You said no on your PC. Nothing changed on this
  phone.**" (`Pairing.kt:68`, `DENIED`).
- The PC's session state becomes `denied`; the desktop's line is "You said no
  on the card. Nothing changed." (`devices-words.js:20`), or the backend's own
  "You said no on the card, so Pixel 9 was not connected."
  (`jarvis_devices.py:235`).
- **No key is made.** The old shared key is untouched.

That is the whole of it: a denial costs nothing and can be repeated.

---

## 5. "Retire" — where it is, what it retires, and why the order matters

### The exact control and label

**On the desktop** (`jarvis-desktop/src/settings.html:273-284`): a section
headed **Old shared key**, with the note "Used by this PC, and by devices
paired before each one had its own key." The button's label is exactly:

> **Retire for other devices**

(`settings.html:281`). Beside it, hidden until it applies, is **Bring it
back** (`settings.html:282`).

**On the phone** the same button exists, spelled the same way
(`DevicesPlate.kt:242`: `Secondary("Retire for other devices", …)`), inside
Settings → Devices. Tapping it first shows the question, and only then a
**Retire** button and **Cancel** (`DevicesPlate.kt:247-268`). The phone only
offers it at all when this phone already holds a key of its own
(`DevicesPlate.kt:231`), because retiring from a phone that still uses the
shared key would cut that phone off.

**What it retires:** the one old shared key that every device used before
per-device keys existed. It does **not** delete anything and cannot be pressed
by accident into locking him out: after Retire the shared key **still works
from this PC**, only from this PC (`jarvis_devices.py:1181-1184`,
`docs/PAIRING-DESIGN.md:152-157`). The desktop's own apps and the backend keep
using it.

### Retiring is immediate, with no card

`jarvis_devices.py:1846` and `docs/JARVIS-API.md:14773`: `POST
/api/devices/shared {"retired": true}` is immediate, no card — it only takes
access away. Retiring in this state is the **stricter** direction, and
stricter is always immediate in this project. The desktop says "Retired. It
now works on this PC only." (`devices.js:282`).

There is one refusal: `409 uses_it_yourself` when the request itself used the
shared key from another device
(`jarvis_devices.py:250-251`):

> This phone is still using the old shared key. Pair it with the QR code
> first, or it would cut itself off.

### What breaks if he retires the shared key BEFORE the phone is paired

**Nothing is broken — and this is important to get right.** A phone that has
never been paired holds **no key at all**. Retiring the shared key removes a
key that phone does not have and has never used. The pairing he then does is
per-device pairing by QR code, which does not use the shared key at all
(`jarvis_devices.py:280-291` — the pairing routes are the only ones in Jarvis
that take no key). So:

- **A never-paired phone: retiring first changes nothing for it.** It can
  still pair by QR code afterwards.
- **A phone that HAS been paired with the old shared key by hand** (the
  older, pre-QR way — `docs/INSTALL.md:953-975`): retiring cuts it off with
  `401 {"key": "shared_retired"}`, and the phone shows, word for word
  (`jarvis_devices.py:219-220`):

  > This phone was using the old shared key, which has been retired on your
  > PC. Pair it with the QR code in Settings, Devices, on your PC.

So the order that is right anyway is: **pair by QR code first, then Retire.**
Retiring first does not break a never-paired phone, but it does break any
phone still on the old hand-typed key.

### Does the code warn him? Yes, in two places

1. **If he retires while another device used the key in the last 30 days**,
   the desktop asks first, naming the address (`devices-words.js:188-190`):

   > Retire the old shared key for other devices? The device (100.101.2.3)
   > that used it 2 hours ago will stop reaching Jarvis until it is paired
   > with the QR code. This PC keeps working.

   The phone asks its own version (`net/Devices.kt:193-202`): "Retire the old
   shared key for other devices? Any device still using it stops reaching
   Jarvis at once. This PC keeps using it."
2. After pairing, when signed approvals are on, both apps nudge him:
   "Your phone now signs risky approvals. Retire the old shared key now so
   unverified devices cannot approve risky actions."
   (`devices-words.js:129`; `net/Devices.kt:30`).

### A change he should know about (2026-10-05, before this page)

Since **2026-10-05** the shared key is a **first-pairing bootstrap**. Once
**any** device holds a key of its own, the shared key stops being a way in
from other devices **even if he never presses Retire**
(`jarvis_devices.py:41-67` and `:1185-1191`, `_first_pairing` at `:949-961`).
The refusal has its own sentence, on purpose not the word "retired", because
nobody retired it (`jarvis_devices.py:224-226`):

> This PC gives every device its own key now, so the old shared key works on
> this PC only. Pair this phone with the QR code in Settings, Devices, on
> your PC.

And in that state **both apps hide the Retire button**, because it would
change nothing (`devices-words.js:152-180`, `DevicesPlate.kt:231`). The row
then reads: "The first device has its own key, so the old shared key now works
on this PC only." (`devices-words.js:137`, `jarvis_devices.py:257-258`).

**Plain consequence for the owner:** pair the phone first. After that the old
key is already shut to other devices, and pressing **Retire for other
devices** (if it is still offered) is the tidy last step, not a risky one.
If the button is not there, that is the code telling him there is nothing left
to retire.

---

## 6. The typed-code fallback

**Yes, and it is a first-class path, not a hidden one.** Both places:

**On the phone**, next to the scan button (`PairByCode.kt:208`):

> **Type the code instead**

It opens two fields — **Your PC's Tailscale or Meshnet name** and
**Code (8 letters)** — and the code field's note says "Under the QR code on
your PC. It works once, for 10 minutes." (`PairByCode.kt:270-296`). The PC
shows the same eight characters under the QR picture, as "Can't scan? Type
this code on the phone: **K7QM-4TXD**" (`settings.html:253-256`).

It is also offered when the camera cannot be used, in three different
situations, each with its own sentence:

- the phone has no usable camera: "This phone has no camera Jarvis can use.
  Type the code instead." (`PairByCode.kt:202`);
- the camera permission is refused: "Jarvis can't use the camera, so it can't
  scan the code. Type the code instead, or allow the camera for Jarvis in
  Android's settings." (`Pairing.kt:83-85`, `CAMERA_REFUSED`);
- the camera will not start: "The camera could not be started. Type the code
  instead." (`PairByCode.kt:254`).

The typed code is 8 characters of Crockford's alphabet (`0-9` and `A-Z`
without `I L O U`), shown as `K7QM-4TXD`, and the phone normalises what he
types — upper case, spaces and `-` removed, `O`→`0`, `I`/`L`→`1`
(`docs/JARVIS-API.md:14655-14657`). A wrong one says "That code is not right.
2 tries left." (`Pairing.kt:91-95`). **Three wrong tries from anywhere burn
the session** — QR and typed alike (`jarvis_devices.py:153`) — and then:
"Three wrong tries - this code no longer works. Start again."
(`jarvis_devices.py:238`).

---

## 7. What the phone needs to reach the PC, and the exact errors

### The allowed addresses

The phone applies **two** checks, and both must pass
(`PhoneAddress.kt:36-68`; `docs/ARCHITECTURE.md:87-105`):

1. the owner's own networks — this PC, the home network, Tailscale, NordVPN
   Meshnet, never the open internet (`OwnNetwork.kt:44-50`);
2. Android's own list of names this app may send plain `http://` to
   (`PhoneAddress.kt:44-49`):

```kotlin
"ts.net" to true,
"nord" to true,
"localhost" to true,
"127.0.0.1" to false,
```

**So the phone can, in practice, use only a name ending `.ts.net` or
`.nord` (plus `localhost`/`127.0.0.1`).** A home-network address such as
`192.168.1.20`, a name ending `.local`, or the PC's own `100.x` number passes
check (1) but fails check (2), and is **refused** — even though it is on his
own network, and even at home (`docs/INSTALL.md:812-822`). The owner decided
this on 2026-09-28: "the phone connects through Tailscale or NordVPN Meshnet
only", because at home the pairing key would otherwise travel unscrambled
(`CLAUDE.md`).

The desktop's **Let my phone reach this** box is the mirror image: it takes
the `100.x` number and refuses a name (`docs/INSTALL.md:874-883`).

### The exact errors he will see

**If the address is on his own network but is not a `.ts.net`/`.nord` name**
— the one he is most likely to hit (`PhoneAddress.kt:56-60`, word for word):

> Jarvis's address 192.168.1.20 is on your own network, but this phone can
> only reach your PC by its Tailscale name (ending in .ts.net) or its NordVPN
> Meshnet name (ending in .nord), not by a number or a home-network name:
> type the name the Tailscale or NordVPN app shows for your PC.

**If the address is off his own networks entirely** (`OwnNetwork.kt:44-47`):

> Jarvis's address 8.8.8.8 is not on your own networks, so this app will not
> send your pairing key there: on this phone, use your PC's Tailscale name
> (ending in .ts.net) or its NordVPN Meshnet name (ending in .nord).

**The four connection errors, word for word** (`net/PlainErrors.kt:49-69`):

| What he sees | What it means | Fix line from the code |
|---|---|---|
| **"Your PC isn't answering."** | Nothing answered at all. PC asleep or off, or Tailscale/Meshnet off at one end, or the firewall. | "It may be asleep or switched off, or Tailscale or NordVPN Meshnet may be off at one end. Wake the PC, check the private network on both, then try again." |
| **"Jarvis isn't running on your PC."** | The PC answered but nothing listened for the phone — Jarvis not started, or started on `127.0.0.1` only. | "The PC is on, but Jarvis is not started. On the PC, open Jarvis Desktop's Settings, then More options, and press Start under \"Starting Jarvis for you\" (it needs \"Let Jarvis Desktop start and stop Jarvis\" on). Or start it in PowerShell, the way you set it up. Then try again." |
| **"This device can't find your PC by its name."** | The name is wrong, or the VPN is off on the phone. | "Check that Tailscale or NordVPN Meshnet is on here, and that the PC's name in the connection settings is right." |
| **"Tailscale (or Meshnet) is off on this phone"** | No VPN running at all on the phone. Under the link on Home and on Checks (`LinkWords.kt:83`). | Switch it on in the Tailscale or NordVPN app; the phone reconnects by itself. |

**And if the key is the problem** (`PlainErrors.kt:85-90`):

> **"Your PC didn't accept this app's pairing key."** — "Enter the key again
> in the connection settings. The PC's desktop app shows it: Settings, \"Show
> the token for my phone\"."

`docs/INSTALL.md:1067-1072` adds the trap worth knowing: a server whose banner
says `token NONE` accepts only callers **on the PC itself**, so the phone is
refused **as if the key were wrong** when in fact there is no key at all.

Every one of these has a **Details** line under it for a bug report, with keys
and passwords taken out (`docs/INSTALL.md:1074-1075`).

### The PC's own half, in one command

`docs/INSTALL.md:1063-1066` and `:1079-1082` — with Jarvis running, in the
repository folder:

```powershell
$env:JARVIS_BACKEND = "C:\Users\pcadmin\Documents\Claude\Open jarvis files\Desktop program"; $env:PYTHONIOENCODING = "utf-8"; py -3 backend\selftest.py --preflight | Tee-Object -FilePath "$env:USERPROFILE\Desktop\preflight.txt"; Write-Host "Saved to $env:USERPROFILE\Desktop\preflight.txt"
```

Its **"Can your phone reach Jarvis?"** lines check the phone address, Tailscale
on the PC, Jarvis listening for the phone, and the firewall rule, and each one
says what to do (`docs/INSTALL.md:146-150`).

---

### Two shortcuts that cannot work, and why (read 2026-10-10)

Both were tried while testing this page against the live system, and both fail for
structural reasons rather than for want of configuration. They are written down so
the next person does not spend the same afternoon on them. **Neither is a defect:
both are the rules the owner chose.**

**1. `adb reverse` cannot carry pairing — and neither can the PC's own mesh
address.** The phone's half (`POST /api/pair/claim`) is refused unless `mesh_peer()`
answers `"mesh"` (`backend/jarvis_devices.py:1612`), and `mesh_peer()`
(`backend/jarvis_devices.py:838`) asks `from_this_pc()` **first**
(`backend/jarvis_owner_check.py:246`). That rule counts three things as this PC:
loopback; a connection whose peer address equals the address it arrived at; and any
of this PC's own addresses, Tailscale and Meshnet included. So a phone reaching
`127.0.0.1:4719` through `adb reverse` arrives *from loopback* and is judged this
PC; a request sent to the PC's own `100.x` mesh address arrives *from that same
address* and is judged this PC too. Both answer:

```
403 {"reason": "not_mesh",
     "error": "Pairing is for another device - this PC already has its own key."}
```

**Only a real second device, with its own mesh address, can claim a pairing
session.** Testing pairing therefore needs the phone on Tailscale or Meshnet — which
is what `docs/ANDROID-PAIRED-AUDIT-2026-10-10.md` §1 did, and it worked.

**2. The desktop's Settings window cannot be revealed from outside the app.** It is
built with `.visible(false)` and shown only by the app's own
`window_memory::restore()` (`jarvis-desktop/src-tauri/src/windows.rs:462-472`, the
same pattern as `lib.rs:673-703`, so it does not flash up centred and then jump). A
driver that calls `ShowWindow`/`MoveWindow` on the window changes nothing: the window
exists, is enumerated at its size and title, and stays hidden. To press **Pair a
phone**, use the app's own command palette — the Jarvis bar → `/` → the row
**Devices** — and the owner's own click. That is also the only way the card can be
approved, since `pair_device` is PC-only and needs Windows Hello.

---

## The steps, in order, in plain words

What he clicks, and what he should see after each.

| # | Where | What he does | What he should see |
|---|---|---|---|
| 0 | PC, Windows Settings | Accounts → Sign-in options → set up a **PIN (Windows Hello)** if there is none | The card later needs this. Without it, pairing is refused |
| 1 | PC | Install Tailscale (`winget install --id Tailscale.Tailscale -e`), open it, sign in | Tailscale in the tray, signed in |
| 2 | Phone | Install **Tailscale** from the Play Store, open, sign in with the **same** account, switch it on | Tailscale on, showing the phone |
| 3 | PC, Tailscale admin | Check **MagicDNS** is on; note the PC's name, ending `.ts.net` | A name like `desktop.tail1234.ts.net` |
| 4 | PC, Jarvis Desktop | Tray icon → **Settings and help…** → **Connection** → **Let my phone reach this**: type this PC's `100.x.x.x` address, **Save** | The field holds the `100.x` number |
| 5 | PC, Jarvis Desktop | Same Settings → **More options** → **Starting Jarvis for you** → **Stop**, then **Start** | Jarvis restarts and binds to the mesh address |
| 6 | PC, PowerShell **as administrator** | The `New-NetFirewallRule` line above | One rule named "Jarvis backend (private mesh only)" |
| 7 | PC, Jarvis Desktop | Tray icon → **Settings and help…** → **Devices** | The **Devices** section, with **Pair a phone** |
| 8 | PC, same page | If asked, type the PC's **name** in **Your phone reaches this PC at**; press **Pair a phone** | A QR code, "Can't scan? Type this code on the phone: **K7QM-4TXD**", "Works for 9:41 more", "Waiting for your phone…" |
| 9 | Phone | Install the APK from the `client-latest` release (tap the file, or `adb install -r jarvis-client-<commit>.apk`) | Jarvis installed; opening it shows **JARVIS** / **Pair with your desktop** |
| 10 | Phone | Tap **Scan the code on your PC** (or **Type the code instead**) | Camera screen ("Point the camera at the QR code on your PC.") or the two typing fields |
| 11 | Phone | Let it read the code, or type the name and the 8 letters, then **Next** | **Connect to `<your-pc>.ts.net`?** with **Name for this phone** filled in |
| 12 | Phone | Press **Connect** | **Check the words** — four words large, and "Approve the card on your PC if it shows these same words." |
| 13 | PC | **Look at the card** in the Jarvis bar / widget. Title: "Jarvis wants to connect a new device". Check the four words match the phone | Windows Hello asks for the PIN |
| 14 | PC | Approve it (PIN/fingerprint) | The desktop's Devices panel says "**Pixel 9** is connected." |
| 15 | Phone | Wait a second or two | "Approved on your PC. Connecting with this phone's new key…" then the app's Home screen |
| 16 | PC, Jarvis Desktop → Devices | Look at **Paired devices** | **Pixel 9** listed, with "Phone · paired 5 Oct · last used just now" and a **Remove…** button |
| 17 | PC, Jarvis Desktop → Devices | **Then** press **Retire for other devices** under **Old shared key**, if it is still offered | "Retired. It now works on this PC only." — or the row already says "The first device has its own key, so the old shared key now works on this PC only." and the button is hidden, which means there is nothing left to do |

**After step 15, the phone is paired.** Steps 16-17 are tidying.

---

## What could not be established

Said plainly, because he is going to follow this literally.

1. **Whether the repository secret `DEBUG_KEYSTORE_B64` exists.** The APK jobs
   stop on purpose without it (`jarvis-client.yml:56-64`), and the workflow
   would not be green. A checkout cannot read repository secrets.
2. **Whether the APK currently on `client-latest` was built from this `main`.**
   The release notes name the branch and commit (`jarvis-client.yml:1057`) —
   read that line. Nothing in the repository proves which build is current.
3. **Whether `face-shots` (the last job in `jarvis-client.yml`) passes.** It is
   `continue-on-error: true` (line 1125), so it cannot block the publish, but
   it can leave the run red while the APK still published.
4. **The exact Windows Hello prompt wording.** The design says the prompt shows
   the card's title (`docs/PAIRING-DESIGN.md:532-533`), but the prompt itself
   is Windows' own and is not in this repository.
5. **The look of the card on screen** — fonts, sizes, where it lands on the
   desktop. The words and the behaviour are read from the code; the pixels are
   not.
6. **Whether his installed desktop build already contains this pairing code.**
   Both apps show pairing and Devices only when `GET /api/version` reports
   `capabilities.pairing` (`docs/JARVIS-API.md:14606-14611`). If his Settings
   has no **Devices** section, his backend or desktop is older and step 1.5 of
   `docs/INSTALL.md` needs running again.

---

## Where each claim above was read

| Claim | File and line, at `acf3ffbd` |
|---|---|
| Two workflows, which app each builds | `.github/workflows/android-apk.yml:14-41`, `.github/workflows/jarvis-client.yml:3-19` |
| Old APK workflow publishes nothing | `.github/workflows/android-apk.yml:175-188` |
| Old artifact name | `.github/workflows/android-apk.yml:170` |
| Real artifact name | `.github/workflows/jarvis-client.yml:342` |
| Publish only from `main` | `.github/workflows/jarvis-client.yml:1025-1027` |
| APK file name in the release | `.github/workflows/jarvis-client.yml:1041`, `docs/INSTALL.md:1003-1005` |
| `adb install` command | `docs/INSTALL.md:1011-1016` |
| Install by tapping the file | `docs/INSTALL.md:1007-1010` |
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | `docs/INSTALL.md:1032-1034`, `jarvis-client.yml:1067` |
| Devices section and its words | `jarvis-desktop/src/settings.html:217-290` |
| **Pair a phone** button | `settings.html:245` |
| "Can't scan? Type this code on the phone" | `settings.html:253-256` |
| Retire button label | `settings.html:281`, `DevicesPlate.kt:242` |
| Bring it back | `settings.html:282` |
| Retire's confirm question | `devices-words.js:188-190` |
| Retire is immediate, no card | `docs/JARVIS-API.md:14773`, `jarvis_devices.py:1846` |
| `uses_it_yourself` sentence | `jarvis_devices.py:250-251` |
| Retire keeps the PC working | `jarvis_devices.py:1181-1184` |
| Shared key is a bootstrap now | `jarvis_devices.py:41-67`, `:949-961`, `:1185-1191` |
| `shared_first_pair_only` sentence | `jarvis_devices.py:224-226` |
| `shared_retired` sentence | `jarvis_devices.py:219-220` |
| Row sentence, both apps | `devices-words.js:137`, `jarvis_devices.py:257-258` |
| Both apps hide Retire then | `devices-words.js:152-180`, `DevicesPlate.kt:231` |
| Pairing screen heading | `PairingScreen.kt:195-200` |
| Scan / Type buttons | `PairByCode.kt:194-217` |
| Camera sentence | `Pairing.kt:81-82`, `PairByCode.kt:223-234` |
| "Connect to <host>?" | `PairByCode.kt:327-334` |
| Name for this phone | `PairByCode.kt:336-344` |
| Typed-code fields | `PairByCode.kt:270-296` |
| The four words block | `PairByCode.kt:134-160` |
| "Approve the card … these same words." | `Pairing.kt:80` |
| Words mismatch refusal | `Pairing.kt:64-67` |
| Denied sentence on the phone | `Pairing.kt:68` |
| Card title | `jarvis_devices.py:292`, `jarvis_card_words.py:160`, `:176`, `:232-239` |
| **Card body, word for word** | `jarvis_devices.py:1290-1299` |
| Card is PC-only + Windows Hello | `jarvis_owner_check.py:126`, `docs/JARVIS-API.md:14716-14719` |
| Card timeout 180 s | `backend/rebuilt/jarvis-framework.toml:79` |
| Key made only after approval | `jarvis_devices.py:1283-1287`, `docs/PAIRING-DESIGN.md:518-519` |
| 10 minutes, 3 tries | `jarvis_devices.py:152-153` |
| Session sentences | `jarvis_devices.py:230-242`, `devices-words.js:15-27` |
| Phone's connection errors | `net/PlainErrors.kt:49-90` |
| Phone's address rule and sentence | `PhoneAddress.kt:44-60`, `OwnNetwork.kt:44-50` |
| Allowed cleartext names | `PhoneAddress.kt:44-49` |
| Desktop's bind box rule | `docs/INSTALL.md:869-883` |
| Firewall line | `docs/INSTALL.md:901-903`, `backend/selftest.py:1850` |
| Preflight line and its checks | `docs/INSTALL.md:1079-1082`, `:1063-1066`, `:146-150` |
| VPN-off line | `LinkWords.kt:83` |
| Pairing routes take no key | `jarvis_devices.py:280-291`, `docs/JARVIS-API.md:14661-14662` |
