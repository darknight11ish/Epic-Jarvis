# Custom plugins for Jarvis and DeepSeek Harness: one server, two hosts (design, 2026-10-04)

Status: **designed, not built.** The owner asked (2026-10-04) whether DeepSeek
Harness (DSH), which can build its own plug-ins, could be used to give Jarvis a
specific new tool or ability - either by taking an existing GitHub plug-in and
adapting it, or by writing a custom one when nothing suitable exists. The owner
then chose **"Both hosts, design doc only"**: design the shared-server approach so
one plug-in can serve both Jarvis and DSH, change nothing yet, and bring it back
before building. This is that design.

It will be **JARVIS-API section 115** (114 is the highest written; 111 is reserved
but unwritten by `docs/GITHUB-TOOLS-DESIGN.md`; check the queue table for a newer
free number when building).

Read first: `docs/ARCHITECTURE.md` section 3 (one permission model) and section 4
(the ways out of the PC), `backend/jarvis_mcp.py` (the bridge that already
exists), `docs/designs/mcp-draft-2026-09-23/DESIGN.md` (the full protocol and
Windows process handling), `docs/GITHUB-TOOLS-DESIGN.md` (adding outside code to
Jarvis, with cards and tests - the closest existing design).

Checked by reading only. **Nothing was run.** No plug-in was installed, no
`plugin_manager` call was made, no market install was performed, and no child
process of either host was started. The DSH behaviours named below (profile
composition, `install_bundle`, the market's install order) are read from the
installed DSH build and its shipped documentation, and must be confirmed by the
builder against the running host before the slice that depends on them.

## 1. The short version

- **The answer is yes, and most of it already exists.** Jarvis already speaks MCP
  (`backend/jarvis_mcp.py`, a shipped client), and DSH already builds and installs
  plug-ins (a Cordis plug-in framework, a `plugin_manager` tool, and a working
  plug-in market in your own profile). The two meet at **one program on the PC**.
- **Do not build a second plug-in system inside Jarvis.** Build the plug-in once;
  point both hosts at the same installed server.
- **One server, two hosts:**

  ```
  a GitHub repo or your own code
            |
            v
   installed ONCE on the PC (your action, one card in Jarvis)
            |
            v
   an MCP server, spoken over standard input/output (stdio)
            |
     +------+------+
     |             |
     v             v
  JARVIS        DEEPSEEK HARNESS
  jarvis_mcp.py   an MCP bundle
  every call       mcp__<server>__<tool>
  asks you first
  ```

- **Jarvis keeps rule 4 untouched.** Every call is still its own gate action under
  its own name (`mcp__<server>__<tool>`), still needs a person's yes, and a stale
  event stream still blocks it. A plug-in never gains a way to approve itself.
- **The install step is yours, not Jarvis's.** `jarvis_mcp.py` refuses any command
  that downloads code when it starts (`npx`, `uvx`, `pipx`, `npm exec`) and requires
  a full path to an installed program. So "Jarvis finds a plug-in and installs it
  alone" is **not** the current behaviour and is not proposed here.
- **Three shapes**, described in section 5: both hosts share one server
  (recommended), DSH-only, or Jarvis-only.
- **What is missing is thin** (section 4): a small adapter that writes the
  host-appropriate entry for a server, and a way to start the authoring step from
  Jarvis instead of you driving the DSH window.

## 2. Rules it keeps

- **Rule 1.** A plug-in that reads email, files, credentials or stored memory stays
  on the local model. Nothing private is put into a plug-in's request, a market
  search, or a model prompt for this feature. Only the plug-in's own public text
  (README, licence, file names) may leave the PC, and only when a card lists it.
- **Rule 2.** No tunnel. Nothing here opens a public address, and Jarvis's bridge
  refuses every transport except a program on this PC over standard input/output.
- **Rule 3.** A plug-in that needs a key gets it the way the bridge already does:
  never logged, sent only to the one program it is for, and never written to disk
  in plain text (a plain value or `credman:<entry>` from Windows Credential
  Manager, read at the moment the program starts). A key is never copied into
  conversation text or into a DSH bundle file - DSH's own guidance says to
  reference an existing credential with `!!js` rather than paste it.
- **Rule 4.** Nothing approves itself. Cards are decided by a person's tap, never
  by the model, never by the plug-in, never by voice, and never in bulk. A stale
  event stream blocks every button here (`Send X-Jarvis-Client: hud` on every
  request). `jarvis_mcp.py`'s floor is always "ask" in version 1, and it refuses
  any verdict that is not a person's approval.
- **Rule 5.** A non-commercial licence is **not** a reason to refuse a plug-in.
  Credit still goes in `THIRD-PARTY-NOTICES.txt`; share-alike still applies; a
  plug-in is never redistributed against its terms.
- **Outside text.** Everything a plug-in sends back is outside text: cleaned,
  capped and labelled untrusted, never learned as a fact, never read aloud by
  itself, and never a change to a verdict. It marks the turn, so note-writing and
  the web-search card ask afterwards.
- **Owner's taps only.** No model-callable tool installs a plug-in and no voice
  command does. Adding a plug-in is a tap in an app, like every other change of
  this size.
- **The model never decides a tier.** The gate decides, from the action name; an
  action nobody listed gets the unknown-action tier, "ask".

## 3. Threat model

Each line is: what could go wrong, then what stops it. "Known limit" means it is
true and written down rather than fixed.

| What could go wrong | What stops it |
|---|---|
| A plug-in server runs as you and can read files or use the internet | **Known limit, and the code says so in its own words:** `jarvis_mcp.py` "controls WHAT JARVIS ASKS IT TO DO and WHAT COMES BACK INTO THE CONVERSATION; it does not sandbox the program." That is exactly why adding one asks, and why the card says so |
| A plug-in is swapped for different code after you approved it | A card on add, and again whenever the program's bytes or version change. What you approved is remembered as a fingerprint (command, arguments, folder, setting names, and the bytes of the program file) plus the version it reported. A start with the same fingerprint and version needs no card and is written to the audit log; anything different asks again, and the card says what changed |
| Starting a plug-in fetches code from the internet each time | Refused: a download-on-start command (`npx`, `uvx`, `pipx`, `npm exec`) is rejected, and the command must be a full path (PATH is never searched) |
| A plug-in offers a tool that changes something while claiming to read | Read-only first: a tool is offered only when nothing in its name says it changes something, the program does not say otherwise, and either the program says it only reads or you wrote `read_only = true` for it after checking. `below_ask_ok` is refused in version 1, so no tool can sit below "ask" |
| A remote server is reached instead of a local program | Refused: programs on this PC over standard input/output only. No web addresses, no HTTP servers, no remote servers. **Home Assistant's MCP server is never used** - its tools act without a card, and `jarvis_home.py` does that job safely |
| A plug-in gets Jarvis's own secrets | The child's environment is an allow-list: it never receives the pairing token (`HUD_TOKEN`, `JARVIS_TOKEN`) or any `*_KEY` / `*_TOKEN` / `*_PASSWORD` of Jarvis's. A secret-looking name is never given as a plain value |
| A plug-in passes you instructions in its output | Its output is untrusted outside text, cleaned and capped, and the content-risk check is told where it came from (`mcp:<server>/<tool>`) |
| A plug-in starts a helper that outlives it | Processes are killed as a tree: on Windows each server is created suspended, put in a Job Object with kill-on-close, then resumed; on POSIX a new process group, then terminate, then kill. If Jarvis itself dies, Windows kills the whole tree |
| A half-written or misread `[mcp]` section silently widens access | It refuses rather than guesses (`ConfigError`), and the reach list reports it as off and says why |
| A DSH plug-in is installed by hand-writing the profile's files | DSH's own rule: do not write the profile's `package.json` or `cordis.patch.yml`; `install_bundle` performs those steps, and each hand-made write outside the workspace needs its own approval |
| Installing a DSH plugin cannot be undone | The market writes `disabled: true` rows into the official patch layer, so a plugin can be switched off without a restart, and a malformed patch file is never made worse |
| One broken plug-in stops DSH starting at all | **Known limit of DSH:** its boot is all-or-nothing. The market has a recovery prompt that lets you choose what is enabled at the next start. Worth knowing before installing anything experimental |

## 4. What exists today, and what is missing

**Exists and is installed (checked by reading):**

- Jarvis's MCP client: `backend/jarvis_mcp.py`, shipped and tested
  (`backend/test_mcp.py` against a real child process, `backend/test_mcp_wiring.py`
  inside the agent's real tool loop). Configured under `[mcp]`, which ships
  `enabled = false`.
- Jarvis reaches these tools **only** by asking for `more_tools("plugins")` - never
  from the core tool list.
- DSH runs on a plug-in framework (Cordis) and ships a plug-in-building skill with
  references for host plug-ins, UI plug-ins, and **MCP bundles**.
- Your `desktop` profile at `C:\Users\pcadmin\.dsh\profiles\desktop` already runs
  four community plug-ins from npm, and includes a working **plug-in market**
  (`dshmarket`) whose install order is: repo-verified npm packages, then
  author-supplied prebuilt GitHub Release tarballs, then full-repo GitHub source.
  So "take an existing plug-in and adapt it" is already a built path in the DSH
  window.
- DSH exposes plug-in management to its own agent as `plugin_manager`
  (`install_bundle` with an absolute package directory), and every call needs
  approval.

**Missing (the actual work):**

1. **A host-appropriate entry writer.** Given one installed server, write
   `[mcp.servers.<name>]` for Jarvis and an MCP bundle for DSH, from one place, so
   the two cannot drift apart.
2. **A way to start from Jarvis.** Today the authoring step is driven by hand in
   the DSH window. Starting it from Jarvis means a tap-only card, and the coding
   step waits for the second graphics card (the standing limit that Jarvis writes
   no code until the 12 GB card is installed and measured).
3. **A plain-language "what is this and what will it see" note** on the add card,
   including the un-sandboxed-program warning in words a beginner reads once and
   understands.

**Deliberately not proposed:**

- A second plug-in system inside Jarvis. It would duplicate the bridge, split the
  permission model in two, and break the "one permission model" promise.
- Letting Jarvis install from the internet by itself. It contradicts the bridge's
  own design and rule 4's "nothing approves itself".
- Home Assistant's MCP server. Refused for a stated reason; not reconsidered here.

## 5. The three shapes

- **(A) Both hosts, one server - recommended.** One MCP server on the PC, launched
  by Jarvis through the bridge and by DSH through an MCP bundle. The plug-in is
  built once and both hosts gain the tool. Jarvis keeps its card per call; DSH
  keeps its own approval model. This is what section 4's missing pieces serve.
- **(B) DSH-only.** Skip Jarvis entirely. You get the tool in the DSH window
  through the market or a custom bundle. Least work, but Jarvis never gains the
  ability, and the tool cannot be used by voice or from the phone.
- **(C) Jarvis-only.** A plain MCP server configured under `[mcp]`, never attached
  to DSH. Simplest to reason about; the authoring help in the DSH window would
  still be what writes it, so it buys little over (A).

## 6. How a plug-in is added - the shape of the flow

This is the intended sequence. Every card is a tap, and nothing here runs on a
model's say-so.

1. **Find.** Either you paste a GitHub repository address, or you search the DSH
   plug-in market in the DSH window. A market search leaves the PC (it asks the
   catalog site); a pasted address is a named way out of the PC carrying nothing
   private.
2. **Look before installing.** Plain code (not the model) reads the repository's
   licence, how recently it changed, whether it runs on Windows, and whether it
   ships an MCP interface. It says "this one has no MCP interface, so Jarvis cannot
   use it" plainly rather than installing it and failing later. The model may write
   a short "what is this?" note from the repository's own public text.
3. **Install once - your action, one card.** The card names the exact command,
   where it installs, the version, and - in plain words - that this is a program
   that will run as you and can do what you can. Jarvis does not fetch code at
   start, so this step is a real install event, not a runtime convenience.
4. **Inspect the tools.** `py -3 jarvis_mcp.py inspect jarvis-framework.toml <name>`
   prints the tools the program offers and the pin lines to copy in. Every tool is
   read-only unless you write `read_only = true` after checking it.
5. **Point both hosts at it.** Write the `[mcp.servers.<name>]` entry and the DSH
   MCP bundle from one place (section 4, missing piece 1).
6. **First start asks.** Adding a server asks once; a later start at the same
   fingerprint and version does not. Every call asks under its own action name.

## 7. Questions for the owner

Recommended answers are first. Nothing here is built until the owner answers.

- **Q1. Which shape?** (A) Both hosts, one server (recommended) - the plug-in is
  built once and serves Jarvis and DSH. (B) DSH-only. (C) Jarvis-only.
- **Q2. Who runs the install step?** (a) You run it, in a terminal, and Jarvis only
  ever points at an already-installed program (recommended - it is what the bridge
  already enforces, and it keeps the download visible to you). (b) A card-driven
  helper installs it for you, still one card per install, still a visible command.
- **Q3. When the plug-in is started:** (a) a card when it is added and again when
  its bytes or version change, as built today (recommended). (b) A card every time
  it starts (`CARD_EVERY_START = True`, one line).
- **Q4. Where may a plug-in come from?** (a) Any GitHub repository and the DSH
  market, with the licence and maintenance check above (recommended; rule 5 means a
  non-commercial licence is no reason to refuse). (b) Only repositories you have
  already checked yourself, added to a short list first.

## 8. What the builder must confirm before writing code

- The exact `plugin_manager` action names and their approval requirements on this
  DSH build, and the shape of a working MCP bundle in the `desktop` profile
  (compare with a profile-installed bundle, not a shipped one).
- Whether the DSH MCP client can launch a **stdio** server with a full path, the
  way `jarvis_mcp.py` insists on, or whether a small stdio wrapper is needed for a
  plug-in that only offers a web-address transport.
- Whether one MCP server process can serve two hosts at once or must be started
  once per host. If it must be separate, the design says so on the card rather than
  leaving two copies running by accident.
- That a plug-in's tool names are accepted by Jarvis's pinning
  (`[mcp.servers.<name>.tools."<tool>"]` with a `sha256:` pin), including any name
  the DSH side rewrites.
- The licence of anything installed, recorded in `THIRD-PARTY-NOTICES.txt` in the
  same change (rule 5).

## 9. Verification this design does not yet have

Nothing in this document was executed. Specifically **not** done: no plug-in
installed, no `plugin_manager` call, no market search or install, no `[mcp]`
section enabled, no child process started, and no DSH bundle written. The claims
about DSH come from reading its shipped skill, its reference files, your profile's
`package.json` and `cordis.patch.yml`, and the installed market's README. The
claims about Jarvis come from reading `backend/jarvis_mcp.py` and its tests. Both
sets must be confirmed against the running systems by the builder before any slice
that depends on them.
