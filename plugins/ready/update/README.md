# update

**Ask Jarvis to update itself from the phone, and let ONE card decide** (the
owner's ask of 2026-11-18: *"the desktop program can update itself, but only at
the PC, and only after Windows Hello there. I want the phone to be able to ask
for that same update, with the phone's own fingerprint."*).

**Drop-in.** Nothing about `jarvis_hud.py` changes to add this. Copy this folder
into the backend's `jarvis_plugins\` folder (or run
`scripts\add-plugin.ps1 -Name update`) and restart Jarvis. The module it names
ships with this repository (`backend/jarvis_update.py`), copied into the backend
by `scripts/apply-patches.ps1` - it is on the `SHIPPED` list in
`backend/_where.py` and on the script's own `$SHIPPED`. There is **no patch**
for it, and there is no `phone-update.patch`: this folder is the whole of its
wiring, the same way `plugins/ready/send-file` and `plugins/ready/notes-edit`
work.

## The two routes

```
GET  /api/update/status     what is installed, what is published, and the phase
                            of any update in flight or just finished - read-only
POST /api/update/request    raise the ONE card and return; nothing else
```

Both go through the core's own origin + token checks (`X-Jarvis-Token`, a paired
phone's own key), exactly like `/api/protection` and `/api/files/send`: the
module adds no second key and no keyless route. A phone that is not paired gets
the same 401/403 every other route gives it.

`/status` answers `can_request` and `why_not` from the **same** function that
refuses a request, so a greyed-out button names the same reason the tap would
have given: nothing newer published, a version that cannot be read, the backend
folder or the updater not found, the action's tier not "ask", a card already
waiting, or an update already running.

`/request` takes no argument that changes anything: there is no field for a
command, a path or a version, and the body is read for nothing.

## The one card

The card is the one that already exists: action **`desktop_update`**, tier
**"ask"**, raised through `jarvis_gate.check` like every other change. It is not
a second name for the ability - `jarvis_quick.UPDATE_ACTION` is the same
string - and its words are the ones written for it in `jarvis_card_words`
("Jarvis wants to update Jarvis itself - the backend first, then this app").

Nothing is downloaded, installed or changed before that card is approved. The
owner can answer it in two places, and both are a person:

- **on the PC**, with Windows Hello - the action has no `_RISK` row, so the gate
  gives it its worst case (permanent, outbound) and the PC still asks;
- **on the phone**, with that phone's own fingerprint or PIN: a fresh signature
  over a one-use challenge. A phone with no approval key is refused with the
  existing "Turn on signed approvals for this phone first." sentence so it can
  offer to turn signing on. This is the same pair of rules the owner chose for
  raising a spending limit on 2026-10-11, and `desktop_update` was taken out of
  `jarvis_owner_check.PC_ONLY_ACTIONS` on 2026-11-18 for exactly this.

Neither answer is a bulk approval, a switch or a standing rule: it decides this
one card, and a "no" proposes nothing.

## What runs after the yes

On the PC, the desktop's own Approve runs its own updater (`update_both`), and
that path is unchanged. A phone's approval never reaches that command, so the
thing that runs after a phone's yes is **`scripts/update-jarvis.ps1`**: the
repository's own both-halves updater, the same one the owner runs by hand, which
applies the patcher and installs the same signed desktop release. It is started
in a **detached helper** (the updater closes the backend it was asked from, so
the worker has to outlive it), with fixed arguments this module owns - no
`-SkipTests`, no `-SkipDesktop`, no `-NoCheck` - and progress is written to
`update-state.json` so the phone reads the phase back across the restart the
update itself causes.

**One update at a time.** The helper holds `update-in-progress.lock`, the same
lock the desktop's "update both halves" writes and reads (a live pid, a
heartbeat under 30 minutes, a start under 3 hours), and it refuses to take a
lock somebody else holds. So a PC approval and a phone approval cannot patch the
machine at the same moment: one runs, the other says plainly that an update is
already running and changes nothing.

## The named limits

- one card at a time; a second request answers 409 and names the waiting card;
- a state file in flight with a live pid is "running", and a request answers 409
  with the phase in plain words;
- the status route writes nothing and fetches no installer - the only read it
  makes is the public release manifest the desktop's own Settings card already
  reads, so the two can never disagree about which release is newest;
- an update that dies leaves `failed` in the state file with the script's own
  last lines, and is never reported as finished.

The phone's own screen for this (a button on the Updates card, `jarvis-client`)
is a later piece of work, recorded in `docs/ARCHITECTURE.md` section 8 under
"One-sided on purpose": the backend half - both routes, the card, the
fingerprint approval and the runner - is complete and tested here.
