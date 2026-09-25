# Closing the approval gap: a design

> Written 2026-09-25. **Design only. Nothing about how approvals work has
> been changed.** Two questions for the owner are at the end; building waits
> for the answers. The gap itself is recorded in `ARCHITECTURE.md` §3, "A
> known limit: a program already on the PC".

## The short answer

- **Recommended: the backend asks Windows Hello itself** (Windows Hello is
  the PC's fingerprint, face or PIN check) before it accepts a risky approval
  sent from this PC. Today the desktop app asks, so a program that skips the
  desktop app skips the check. Phone approvals get their own proof later,
  when the planned "more devices" work adds per-device keys. The phone signs
  each risky approval with a key that only its fingerprint check can unlock.
- **It narrows the gap. It does not close it completely, and nothing can.**
  A harmful program running as you on your PC can, with enough effort,
  change Jarvis's own files or take over its running program. Windows does
  not protect one of your programs from another one of yours. What the fix
  does stop is the **cheap** attack, which is the one that matters most:
  read the pairing token (the password the apps use to talk to Jarvis) and
  send one web request. That attack takes a few lines of code and knows
  almost nothing about Jarvis. It is the kind of attack that hit Meta's Muse
  this month. It also stops the attack that concerns Jarvis most directly: a
  command you approved (say, a `pip install`) running someone else's script,
  which then quietly approves Jarvis's next cards.
- **Size:** step 1 (the PC) is **M**, about the size of the App lock work.
  Step 2 (the phone) is part of "more devices", which is **L** already.
- It starts with **a half-day test on your PC**. Three things it depends on
  cannot be checked from here (listed under "Assumed" below).

## 1. What the gap is, exactly

Checked in the code on 2026-09-25:

- The desktop's Windows Hello check runs inside the desktop app, in
  `commands.rs` `answer_approval` → `lock::check_approval`, and only then
  does it send `POST /api/approve`. The backend does not know a check
  happened. It sees the token and nothing else.
- Any program running as you can read that token from Credential Manager.
  `backend/jarvis_token_store.py` says so in its own header: "any program
  running as the same Windows user can still ask Credential Manager for it".

Two things make the gap **wider than `ARCHITECTURE.md` §3 said**. Both are
corrected there now:

1. **The phone uses the same token as the PC.** There is one pairing token.
   `jarvis_token_store.py show` prints it "to type into the phone", and
   `JARVIS-API.md` §1 says "the server cannot tell the laptop from the
   phone". So a program on the PC can approve by **pretending to be the
   phone**. The phone's fingerprint check (`BiometricGate.kt`,
   `SecurityRules.approvalNeedsCheck`) is also made inside the app, and the
   backend never sees it. The phone's copy of the token is safe from phone
   apps (it is locked with an Android Keystore key, `TokenStore.kt`). But
   the PC holds the same token.
2. **A program does not need `/api/approve` at all.** The approval gate waits
   for a row in `approvals.db` to say `state == "approved"`. You can see this
   in `gate-outcome.patch`'s context lines. `approvals.db` sits in
   `~/.openjarvis/`, according to `rebuilt/jarvis_framework.py`. That is a
   normal file in your user folder. A program running as you can write
   "approved" into it directly. So a check added only to `/api/approve` would
   be easy to walk around. The design below covers this.

Two things are **not** affected. A notification can never approve
(`answer_approval`, `AnsweredFrom::Notification`). The HUD page cannot
approve at all (`hud_proxy.rs`, `hud_bootstrap.js`).

## 2. What no fix can stop

Plainly: **if a program is written specifically to attack Jarvis and runs as
you, it wins in the end.** It can:

- edit the backend's Python files, which live in your user folder, so that
  the check does nothing, then wait for the next restart;
- take over the running backend or desktop app from inside, the way
  debuggers do. Windows allows this between programs of the same user;
- type and click as you, although it cannot pass a Windows Hello check for
  you.

Nothing Jarvis builds inside your Windows account changes this. The real
boundary would be running the backend as a **separate Windows account**,
with its files where your account cannot write. That is a big change, and it
fights with things Jarvis does as you: controlling your windows, your
microphone, your files. It is out of scope here. It is mentioned so the limit
is honest.

## 3. What a fix can stop

| Attack | Today | After step 1 | After step 2 |
|---|---|---|---|
| A program reads the token and posts `/api/approve` from the PC | **Works** | Stopped: a Windows Hello prompt appears showing the card's title, and you did not ask for it | Stopped |
| The same, but pretending to be the phone (connecting through the PC's Tailscale address) | **Works** | Stopped (the backend sees the request came from this PC; see 5.2) | Stopped |
| A program writes "approved" into `approvals.db` | **Works** | Stopped (the gate only accepts approvals stamped by the backend's own running process; see 5.3) | Stopped |
| A program approves a card that is **not** risky (local, undoable, not rushed) through `/api/approve` | Works | **Still works**: the rule is "risky only", as on the phone | Still works |
| A command you approved (`pip install x`) runs a script that approves Jarvis's next cards | **Works** | Stopped (same as the first row) | Stopped |
| Someone at your unlocked PC who knows how to read the token | **Works** | Stopped (they cannot pass Windows Hello) | Stopped |
| Someone who stole the token uses it from **another** device on your Tailscale network | **Works** | **Still works** (the backend takes it for the phone) | Stopped (no phone key, no approval) |
| A program built to attack Jarvis edits its files or takes over its process | Works | Works | Works (section 2) |

## 4. The options

### (a) The backend asks Windows Hello itself, for risky approvals from this PC

- **Stops:** every row marked "Stopped" under step 1 in the table above, with the stamp
  in 5.3.
- **Does not stop:** another device on your network using a stolen token,
  until step 2; a Jarvis-specific attack (section 2).
- **Where the prompt appears:** on the PC, sent by the backend. The backend
  chooses the words, so they are the card's own title and "why", the way the
  desktop's prompt does it today (`lock/rules.rs` `approval_message`). This
  matters: if a program triggers the prompt, you see the name of a card you
  never pressed Approve on.
- **Phone approvals:** these never raise a prompt on the PC. The backend
  tells a phone request apart from a PC request by where the connection comes
  from (5.2). The phone keeps doing its own fingerprint check, as today.
- **Can Python do it without heavy extras?** Yes, probably. Microsoft's own
  Python bindings for Windows' built-in APIs exist on PyPI:
  `winrt-runtime` and `winrt-Windows.Security.Credentials.UI`, version
  3.2.1, with Windows wheels. I checked that they exist, not how they
  behave. Two other routes exist if they misbehave: a small helper program
  built from the Rust the desktop already has (`lock.rs` `hello::verify`),
  or a PowerShell call. The half-day test picks one.
- **The catch:** Microsoft's documentation says a desktop program should
  show this prompt "for a window" (`RequestVerificationForWindowAsync`), not
  without one. The backend has no window. So it needs a small window of its
  own, and the desktop app must let it come to the front
  (`AllowSetForegroundWindow`) just before it sends an approval. **Untested**
  (see "Assumed").
- **Size:** M.

### (b) Per-device keys that sign each risky approval

- **Phone: yes, this is the right tool.** The phone makes a key in the
  Android Keystore that **cannot be used without a fresh fingerprint or PIN
  for every single use**. The backend gives each card a random one-time
  number. The phone signs that number together with the card, and the
  backend checks the signature. A program on the PC cannot make that
  signature. This is built into Android (`setUserAuthenticationParameters(0,
  …)`, API 30; the app needs API 33 or newer). It closes the last "Still
  works" row of the table. It fits "more devices" exactly, since that work
  gives each device its own key anyway, confirmed on the PC by an approval
  card.
  - Android will only make such a key when the phone has a screen lock. On a
    phone with no screen lock, risky approvals would have to be refused.
    That is question 2.
- **PC: not worth it.** The PC's version would be a Windows Hello key
  (`KeyCredentialManager`). Three problems, from what I could read:
  - for a normal (not Store-packaged) desktop app like Jarvis, **any program
    of yours can open the same key by name**. It still cannot sign without
    your fingerprint or PIN;
  - the prompt has **no custom words**. It says roughly "Making sure it's
    you", so a program could trigger one that looks exactly like a real one;
  - reports say its prompt opens **behind** other windows in desktop apps,
    with no way to pass a window.

  Option (a) gives the same protection with better words on the prompt,
  because the backend is on the PC already. A key only helps when the thing
  checking it is somewhere else.
- **Size:** phone part M, inside "more devices" (L).

### (c) Risky approvals only from the phone

- **Stops:** nothing that (a) plus the phone half of (b) does not stop. It
  also needs (b), or a program on the PC would simply pretend to be the
  phone. The ceiling in section 2 is the same, because the backend itself is
  still on the PC.
- **Costs:** you would pick up the phone for every risky card. With the
  default "Risky only" rule, that is most tool cards (anything unclassified,
  outbound or not undoable). And nothing risky could be approved when the
  phone is flat or away.
- **Not recommended.**

### (d) Accept it and keep it written down

- **Costs nothing.** It is honest, given section 2.
- **But** it leaves the cheap attacks open, including the "approved script
  approves the next cards" one. That is an approve-all by the back door,
  which invariant 3 and rule 4 exist to prevent.
- You already chose against this. It is here because this design says the
  fix is partial, and you may want to weigh that.

## 5. The recommendation, in two steps

### Step 1: the PC (M, after the half-day test)

1. **The backend decides which approvals are risky, with the phone's rule.**
   Anything unclassified, outbound, not undoable, or rushed by outside text
   counts. The backend already holds that information: `approval-notice.patch`
   computes it from the gate's own risk table. The desktop's "Every approval"
   setting stays on the desktop, as an extra on top.
2. **It tells a PC request from a phone request by the connection itself.**
   The rule: a connection counts as "from this PC" when it comes from
   loopback (`127.0.0.1` or `::1`), **or** when it comes from one of the PC's
   own addresses (a connection from the PC to its own Tailscale address
   arrives from that same address). Anything that cannot be placed counts as
   the PC, so it asks. A program on the PC cannot make its request come from
   the phone's address. It would need another device to do that, which is
   what step 2 closes.
3. **An approval is stamped by the process that checked it.** When
   `/api/approve` passes, the backend writes a stamp into the approval row: a
   short code made with a secret that exists only in the running backend's
   memory, created fresh at every start and never written to disk. The gate
   accepts "approved" **only with a valid stamp**, for every card, risky or
   not, because stamping costs nothing. Before building, every legitimate
   way a row becomes "approved" has to be found and made to stamp too. One
   example is the gate's own terminal yes/no (`jarvis_gate.confirm`), if it
   writes the row. That is not checked: the file is not in this repo. A
   program that writes "approved" into `approvals.db` has no stamp, so the
   card stays refused. A card still waiting when the backend restarts is
   refused anyway today, so the fresh secret loses nothing.
   - **One thing to confirm first:** that the gate's wait runs in the same
     process as the web server. It appears to, because the chat tool loop
     calls the gate inside the backend. I have not seen `jarvis_hud.py`
     (it is not in this repo), so this is not verified.
4. **The desktop stops asking when the backend will ask**, so you are never
   asked twice. The backend says so in one field on `/api/status` (for
   example `owner_check: "backend"`). An old backend without the field keeps
   today's behaviour. For those approvals, the desktop's approval wait
   (`APPROVAL_TIMEOUT`, 10 seconds today) grows to the card's time left,
   because the request now stays open while the prompt is up.
5. **Everything else stays as it is.** Deny is never held up. A notification
   still cannot approve. The desktop still refuses on a stale link, and the
   backend adds its own version of that rule: a card that expired while the
   prompt was open is refused, not approved. One card, one prompt, one
   decision. No approve-all.
6. **When Windows Hello is not set up on the PC.** Today, with no lock
   turned on, the approval goes through without a check. That is the phone's
   rule (`lock/rules.rs` `approval_verdict`). Keeping that rule would leave
   the gap open on a PC without Windows Hello. That choice is question 2.
7. **Tests:** the risky rule is compared against the phone's and desktop's
   (the same shared cases), plus the address rule, the stamp (an unstamped
   "approved" row is refused), and "Deny is never held". Plus the usual audit
   for the feature (CLAUDE.md), and both apps' docs.

### Step 2: the phone (with "more devices")

When QR pairing gives the phone its own key, add a second key for approvals:
per-use, locked behind the fingerprint or PIN. Each card in `/api/pending`
carries a one-time number. The phone's approve body adds a signature over the
card id, that number and the card's text. The backend checks it with
`cryptography`, which it already uses for chat history. From then on, a risky
approval that is not from this PC must carry a valid phone signature.

## 6. How it fits the rules

- **Rule 4 (never auto-approve; a stale link blocks acting):** unchanged, and
  strengthened. The backend refuses a card that expired while the prompt was
  open.
- **Invariant 3 (no approve-all):** this is what it protects. Today, one
  approved command can approve every card after it.
- **The one permission model (§3):** still one gate and one card. This adds a
  check on who answers the card, not a second approval path.
- **Rule 3 (keys):** the stamp's secret never leaves the backend's memory.
  Step 2's phone key never leaves the phone.
- **Both apps:** step 1 changes the desktop only (the phone already asks on
  its own side). Step 2 is the phone's half. Until step 2 lands, this is
  written down in ARCHITECTURE §8, "One-sided on purpose".

## 7. What I verified, and what I assumed

**Verified (read in this repo, or in the original documentation):**

- Every code fact in section 1: `commands.rs`, `lock.rs`, `lock/rules.rs`,
  `jarvis_token_store.py`, `TokenStore.kt`, `BiometricGate.kt`,
  `Security.kt`, `gate-outcome.patch`, `approval-notice.patch`,
  `rebuilt/jarvis_framework.py`, `jarvis_agent.py` (`shell_exec`).
- Android: a per-use key needs a screen lock, and it is invalidated if the
  screen lock is removed. Timeout `0` means "user authentication must take
  place for every use of the key". Read in Android's own source,
  `KeyGenParameterSpec.java` (AOSP).
- Windows: a desktop app should use `RequestVerificationForWindowAsync` with
  a window, not the plain call. Windows Hello keys are TPM-backed when the PC
  has a TPM, and signing asks for the PIN or fingerprint. Read in
  Microsoft's documentation source on GitHub (`MicrosoftDocs/winrt-api`,
  `MicrosoftDocs/windows-dev-docs`), because learn.microsoft.com is blocked
  from here.
- The Python Windows packages exist on PyPI (`winrt-runtime`,
  `winrt-Windows.Security.Credentials.UI`, 3.2.1, Windows wheels).

**From search-result summaries only (I could not open the pages):**

- `KeyCredentialManager` keys are not separated per app for normal desktop
  programs: "another process under the same user account can open the same
  KeyCredential if the credential name is known" (a Microsoft Q&A page).
- Its prompt opens behind the app's window in desktop apps, with no way to
  pass a window (Bitwarden and WindowsAppSDK discussions).

**Assumed, and checked in the half-day test before any building:**

- The backend can show the prompt at the front, with its own small window
  and the desktop's `AllowSetForegroundWindow`.
- A connection from the PC to its own Tailscale or Meshnet address arrives
  from that same address.
- The gate's wait runs in the same process as `/api/approve`
  (`jarvis_hud.py` is not in this repo).

## 8. Questions for the owner

**1. This narrows the gap. It cannot close it.** A program written
specifically to attack Jarvis can still get around it. Simple programs and
approved scripts cannot. Still build it?

- **Yes: step 1 now (after a half-day test on your PC), the phone half with
  "more devices"** (recommended)
- **No: keep it written down as a known limit**

**2. A PC with no Windows Hello, or a phone with no screen lock.** Today a
risky approval goes through there without a check. Once the backend checks,
should it?

- **Refuse risky approvals until a PIN or screen lock is set up**
  (recommended, because otherwise the gap stays open on that device)
- **Let them through as today**

## Sources

- [Windows Hello for developers (MicrosoftDocs source)](https://github.com/MicrosoftDocs/windows-dev-docs/blob/docs/hub/apps/develop/security/windows-hello.md)
- [UserConsentVerifier (MicrosoftDocs/winrt-api source)](https://github.com/MicrosoftDocs/winrt-api/blob/docs/windows.security.credentials.ui/userconsentverifier.md)
- [KeyCredentialManager (MicrosoftDocs/winrt-api source)](https://github.com/MicrosoftDocs/winrt-api/blob/docs/windows.security.credentials/keycredentialmanager.md)
- [Microsoft Q&A: security boundary of KeyCredentialManager for desktop apps](https://learn.microsoft.com/en-us/answers/questions/5912130/what-is-the-security-boundary-of-windows-hello-key) (summary only)
- [WindowsAppSDK discussion #1265: Windows Hello from a Win32 app](https://github.com/microsoft/WindowsAppSDK/discussions/1265) (summary only)
- [Bitwarden PR #14953: Windows Hello prompt behind the window](https://github.com/bitwarden/clients/pull/14953) (summary only)
- [AOSP KeyGenParameterSpec.java](https://github.com/aosp-mirror/platform_frameworks_base/blob/master/keystore/java/android/security/keystore/KeyGenParameterSpec.java)
- [PyPI: winrt-Windows.Security.Credentials.UI](https://pypi.org/project/winrt-Windows.Security.Credentials.UI/)
