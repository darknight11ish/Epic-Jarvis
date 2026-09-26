# Cutting-edge audit, round 3: the home, the PC itself and the physical world

Research only, 2026-09-26. Nothing here is built, and no rule changes without
the owner's yes. It builds on round 1 and 2 (`CUTTING-EDGE-2026-09-26-*.md`),
the creativity audit (`CREATIVITY-AUDIT-2026-09-25.md`,
`creativity-2026-09-25/`) and the competitor reports, and does not repeat
them. Where an idea extends an earlier one, it says so.

## In short (for the owner)

1. **Your PC is about to have two graphics cards, and Jarvis can only see one of them.** The desktop's heat reading shows the first card only. Fixing that is small and comes first.
2. **Jarvis can make the cards cooler and quieter while losing little speed** (a "power limit"). It measures first, then gives you one line to paste. Jarvis itself never gets administrator rights.
3. **"Wake my PC" from the phone works at home with no extra kit.** Away from home it needs something at home that is always on, such as Home Assistant.
4. **"Turn off the downstairs lights"** can become one approval card listing every light, worked out from Home Assistant's rooms and floors.
5. **"Room awareness" gets a concrete shape:** Jarvis knows which room a request came from. It speaks where you are, and it is more discreet when someone else is around. It never grants anything.
6. **Two corrections to earlier reports.** Home Assistant's MCP device list does not include device ids. And every Home Assistant idea here assumes you run Home Assistant, which no Jarvis test has reached yet.

## How far to trust this

- **Read myself** (raw files on GitHub): Home Assistant release notes 2026.4
  to 2026.9. HA core source: `api/__init__.py` (which REST routes need an
  admin), `websocket_api/commands.py`, `config/area_registry.py`,
  `config/floor_registry.py`, `config/entity_registry.py`,
  `components/homeassistant/llm.py` (the MCP "live context"),
  `mcp_server/server.py`, `camera/__init__.py`, `wake_on_lan/services.yaml`
  and `energy/websocket_api.py`. Licence files for Bermuda, LibreHardwareMonitor,
  NAPS2, matterjs-server, Frigate, tailscale-wakeonlan, UpSnap, evcc,
  Tesla vehicle-command and WeeWX. The READMEs of LibreHardwareMonitor and
  matterjs-server.
- **Search summaries only** (marked **(summary)**): nvidia-smi power limits
  on Windows GeForce (docs.nvidia.com was blocked), Frigate 0.16/0.17 face
  recognition, Wake-on-LAN over Tailscale, the Ecowitt local API, FanControl's
  licence, evcc's REST API, Tesla BLE on Windows, the HA MCP community server.
- **Not checked:** anything on the owner's real PC, cards, router or Home
  Assistant. Power-limit savings are **claims** from blogs. Whether the owner
  runs Home Assistant, Frigate, a scanner, a weather station or an EV is
  unknown. ARCHITECTURE §10 says "Nothing has reached a real Home Assistant."

## What changed out there (relevant to Jarvis)

| Where | What is new | What it means for Jarvis |
|---|---|---|
| HA 2026.4 | "Occupancy" cross-domain triggers. Matter locks: manage users and **PIN codes** from HA, with the same actions available to automations | Occupancy is a room-awareness input. The PIN actions are **not for Jarvis** (see below) |
| HA 2026.5 | "Entered home" and "left home" triggers **removed** from Person; zone triggers replace them in 2026.6 Labs | Jarvis's "tell me when I get home" polls the state (`jarvis_tellme._look_home`, line 704), so this change does not break it |
| HA 2026.6 | Energy: battery charge level and named sources. Z-Wave lock PINs. OpenThread Border Router 1.4 | Energy totals are readable (idea 10) |
| HA 2026.7 | Automations built **around areas** ("motion in the living room"). Activity timeline. **Matter server rewritten in matter.js** (python-matter-server archived) **(summary)** | Areas are now the HA way of thinking, so Jarvis should think in areas too (idea 4) |
| HA 2026.8 | **New HA OS installs no longer use `:8123`**. Existing installs keep their port. Entity ids can be renamed | The owner's `JARVIS_HOME_URL` should be exactly the address HA opens at. A renamed id breaks a "tell me when" watch that names it |
| HA MCP server | Tools now carry `readOnlyHint` / `destructiveHint` (`mcp_server/server.py:63-67`, read) | These are HA's own claims about its tools. They are never a reason for Jarvis to skip a card |

**Correction to round 1, idea 10** ("HA's exposed devices as Jarvis's list"):
the MCP live-context tool returns each device's names, domain, area, state
and a few attributes, but **not its entity id**. The code builds `info` with
`names`/`domain`/`state`/`areas` (`homeassistant/llm.py:143-165`) and returns
`exposed_entities.values()` without the keys (lines 322-326). So it cannot
feed `plan_service()` on its own. Ids need the entity registry (idea 4).

## Ranked list

"Rule risk" = how close it comes to the five rules and the dated decisions.

| # | Idea | Why it matters | Size | Rule risk |
|---|---|---|---|---|
| 1 | Health for BOTH cards: heat, power, "slowed down because hot" | Today only the first card is read. The 2060 is coming | S | None |
| 2 | Measured power limit per card, one line for the owner to paste | Cooler and quieter, and speed is claimed to barely drop | S-M | Low (Jarvis never elevated) |
| 3 | "Wake my PC" from the phone | Every competitor is always on; Jarvis sleeps with the PC | M | Low (never a port-forward) |
| 4 | Rooms and floors: "the downstairs lights" as ONE card that lists each light | Matches HA's own area model; the model stops guessing ids | M | Low; one owner question |
| 5 | Room awareness: which room, who else, where to speak | Discretion and "in here" without new sensors | M | Low (only ever stricter) |
| 6 | "Goes through the maker's cloud" line on home cards | Rule 1 honesty for cars, some plugs and cameras | S-M | None (a tightening) |
| 7 | Hardening: a non-admin HA user for Jarvis | Blocks HA's admin-only routes if the token leaks | S (docs) | None (a tightening) |
| 8 | "Tell me when someone is at the door" from HA/Frigate labels | A useful camera feature with no picture and no face | S | Low |
| 9 | Camera snapshot on request, shown in the app, never kept | "Show me the front door" | M | Medium: strict rules |
| 10 | "What did running Jarvis cost today?" and HA energy totals | Power data already exists on the PC | S / M | None |
| 11 | Welcome home, done safely | "While you were out" plus at most one card | S-M | Low |
| 12 | Scan to Obsidian | Paper into the vault, text searchable | M | Low (the existing note card) |
| 13 | Printer, weather station, EV: read-only through HA | Briefing lines ("toner low", "car at 80%") | S each | Low |
| 14 | Sleep the PC with a wake-up set for the next alarm | Alarms still ring after the PC sleeps | M | Low; unverified on Windows |

## Details

**1. Both cards' health.** *Found:* the desktop widget runs `nvidia-smi` and
parses only the first line (`commands.rs:2617`, `text.lines().next()`). With
the 2060 fitted, the widget shows one card, whichever `nvidia-smi` lists first.
The backend's card query (`rebuilt/jarvis_compute.py:139`, `FIELDS_FULL`)
asks for memory and ids but not heat or power. *Change:* add
`temperature.gpu`, `power.draw`, `power.limit`, `fan.speed` and
`clocks_event_reasons` (field names **(summary)**; check them with
`nvidia-smi --help-query-gpu`) to `query_cards`, and show one row per card in
`/api/hardware` (`jarvis_hardware.status`, both apps' Hardware screen) and in
the widget. A plain-words line such as "The 12 GB card is at 83 °C and slowing
itself down" can be answered without the model in `jarvis_quick.py`. Before
installing, MODEL-TOPOLOGY already says to check the power supply (750 W
comfortable); this makes the result visible. *Fit:* a read on this PC only,
no card, nothing leaves. The creativity audit cut "PC health (is the disk
full?)" as rarely wanted. This one differs because Jarvis's own work is what
heats the cards. **S.**

**2. Measured power limit.** GPU power limits are set with
`nvidia-smi -pl <watts> -i <card>`. It needs an administrator prompt, and the
limit resets at every restart. The usual Windows fix is a Task Scheduler task
at logon **(summary)**. Blogs claim local AI keeps about 97% of its speed with
roughly 100 W less **(claim)**. Word generation is limited mostly by memory
speed, so a small loss is plausible, but it must be measured. *Plugs in:*
`jarvis_hardware.request_measure` (line 1507) already times each model
(`_speed_measure`, line 1502). Add "measure at 100%, 85% and 70% of the
limit", and show the result ("at 190 W: 41 words/s instead of 43, 9 °C
cooler"). Then give **one PowerShell line** that the owner pastes into an
administrator window, the same pattern as "what Ollama reads at start-up is
one PowerShell line the owner runs" (ARCHITECTURE §10). The line sets the
limit and registers the logon task. *Fit:* the backend never runs elevated
and never changes a hardware setting itself, so no new card is needed. For
the 2060, wait until it is installed and measured (CLAUDE.md). **S-M.**

**3. Wake my PC.** Wake-on-LAN (WOL) is a "magic packet" that switches a
sleeping PC on over the home network. Tailscale cannot carry it, because WOL
works one layer below Tailscale. So something on the home network must send
it (Tailscale's own blog, **(summary)**). *At home:* the phone sends the
packet itself, as a local broadcast. That needs no key and no server, only
the INTERNET permission the app already has (`AndroidManifest.xml:5`). The
PC's network card address (MAC) is handed over at pairing. It is not a
secret. *Away:* three options, and the owner picks one:
(a) a Home Assistant button that calls `wake_on_lan.send_magic_packet`
(`services.yaml`, read; the owner presses it in HA's own app, because the
phone holds no HA token);
(b) `tailscale-wakeonlan` (MIT) on an always-on box;
(c) UpSnap (MIT).
*PC side:* a one-line PowerShell check that WOL is enabled on the network
card and that Windows "fast startup" is off. *Fit:* waking asks for nothing
and changes no data. Like Active, it is the safe direction, and the phone
shows "PC asleep" instead of a plain "offline". **Never** forward the WOL
port on the router, because that is an opening to the internet (rule 2).
**M.**

**4. Rooms and floors.** HA's area and floor lists come from its WebSocket
API: `config/area_registry/list`, `config/floor_registry/list` and
`config/entity_registry/list_for_display`. None of them is admin-only
(read). Python's standard library has no WebSocket client. So either add
`websocket-client` (Apache-2.0) or write a small RFC 6455 client. The first
keeps the "`urllib` only" reason in `jarvis_home.py:7-12` honest by saying
what was added. *Plugs in:* a read-only `areas()` in `jarvis_home.py`, cached
on the PC, that turns "downstairs lights" into an id list. That list goes to
the existing `plan_services` (line 401), capped at `MAX_GROUP` = 10 (line
136) and never cut. Locks, doors, alarms and covers
(`_HEAVY_DOMAINS`/`_ALONE_DOMAINS`, lines 117/130) are left out of the group
and each gets its own card, as decided on 2026-09-25. *Fit:* one card, every
device listed, the same as "kitchen, hall and bedroom". *Owner's call:* the
lights setting runs only for "devices the owner's own newest words named"
(ARCHITECTURE §2). Whether a room name counts is question 1 below. **M.**

**5. Room awareness (developing creativity idea 8).** Three signals Jarvis
already has, plus one optional one:
- *Where the request came from.* The backend knows whether a request came
  from this PC (`jarvis_owner_check.from_this_pc`, line 211). A setting in
  each app says "This device is in: Office", picked from HA's areas (idea 4),
  so "turn off the light in here" means that area's lights, on one card.
- *Whether someone else spoke.* The voice check already scores other voices
  (`jarvis_voice_enroll.calibrate`, line 1173). "Someone else was heard in
  the last few minutes" keeps private answers on screen (`private-speech.js`,
  `PrivateAloud.kt`). No recording or voice print of the other person is
  kept.
- *Whether the owner is at the PC.* Windows' time since the last key or
  mouse input (`GetLastInputInfo`, read by the desktop app, not stored). A
  timer or reminder speaks at the PC when the owner is there, and otherwise
  rings the phone. Today `jarvis_power.touch()` (line 122) counts only
  talking to Jarvis.
- *Optional:* HA occupancy for that area (HA 2026.4 triggers), read through
  `home_read`. It says "someone is in the room", never who.

*Fit:* room awareness only ever makes Jarvis quieter or narrower, never
grants anything. Turning it off is immediate, and turning it on is a card,
like the other voice settings that change what is spoken. Wording: "fewer
surprises", never "Jarvis knows who is in the room". **M.**

**6. "Goes through the maker's cloud" on the card.** Every HA integration
declares how it talks to its device (`iot_class`: `local_push`,
`cloud_polling`, ...). The `manifest/get` WebSocket command is not
admin-only (`commands.py:699`, read), and the entity registry names each
entity's integration. The card for a car, a cloud plug or a cloud camera can
then say "Home Assistant sends this through Tesla's servers." *Fit:* the same
honesty as "What Jarvis can reach" (`jarvis_reach.py`). It changes no tier.
Needs idea 4's WebSocket client. **S-M.**

**7. A non-admin HA user for Jarvis.** Read in HA's source: `/api/template`,
`/api/stream` (every event in the house), `POST /api/events` and the error
log are **admin-only** (`api/__init__.py:135, 339, 503, 532`). A token made
by a separate non-admin "Jarvis" user in HA cannot use them. Jarvis never
calls them, but a leaked token could. Non-admin users in HA can still
control every device, so this narrows the damage; it does not remove it.
*Trade-off:* HA's exposed-devices list over WebSocket needs admin (round 1,
`exposed_entities.py`), and the area/floor/registry lists in idea 4 do not.
*Change:* the setup guide says so, and the preflight
(`selftest.py --preflight`) can warn "this token is an admin's", which HA
reports in `auth/current_user`. Also: tell the owner to copy HA's exact
address, because new installs have no `:8123` (HA 2026.8). **S.**

**8. "Tell me when someone is at the door."** Frigate (MIT, local camera AI)
publishes per-camera "person / car / package detected" sensors to Home
Assistant **(from memory; not re-read this session)**. HA's own camera
integrations often do the same. `jarvis_tellme` already watches ONE HA entity
every minute and notifies in the owner's words (`HOME_MINUTES`, line 133;
the fast path, `jarvis_quick.py:1225`). This only needs words for "person
detected" in `STATE_WORDS`. *Fit:* one card to set up, labels only, no
picture, no face, nothing leaves the PC. **S.**

**9. Camera snapshot on request.** HA serves one still image at
`/api/camera_proxy/<camera id>` (`camera/__init__.py:878`, read). What could
be allowed:
- only on the owner's own typed or said request, or a tap;
- the picture shown in the app over the existing link and kept in memory,
  never written to disk;
- the AI model sees it only when asked ("what's in it?"), and then only the
  local picture model on the second card (ARCHITECTURE §10), as a picture
  turn counted as outside text;
- never a cloud lane, never continuous, never face recognition, never
  "who is it";
- new gate action `home_camera_look`, tier `ask` as shipped, and a camera
  stands alone like today (`_ALONE_DOMAINS`).
On a phone under App lock or "Hide memory lists", no picture is shown. **M.**

**10. Energy.** *PC only:* sample `power.draw` (idea 1) once a minute, and
"Jarvis used about 0.9 kWh today" becomes a briefing line or a fast-path
answer. *With HA:* totals from HA's recorder statistics over WebSocket (the
`energy/get_prefs` command exists, `energy/websocket_api.py:104`, read; I did
not check the statistics command's admin rule). When the owner is home shows
up in energy data, so it stays on the PC like every other home read. **S /
M.**

**11. Welcome home, done safely.** "Tell me when I get home" is already
folded into `tellme` (usefulness.md). The new part is what happens on
arrival: Jarvis only **reads and offers**. It gives a "while you were out"
summary (the existing "What did I miss?" builder) at the PC when the owner
sits down (idea 5), and at most ONE card, such as "Turn on the hall and
kitchen lights?", through the back-off (`jarvis_backoff.may_offer`). Lights
switching themselves on arrival belong in HA's own automations. The lights
setting cannot do it, because nobody's own words named the devices. Only the
owner's own `person.*` is ever watched. **S-M.**

**12. Scan to Obsidian.** Scan on the PC with NAPS2's console program
(`NAPS2.Console.exe`, GPL-2.0, run as a separate program, **(summary)**) or
Windows' built-in scanning (WIA). Read the text locally with the OCR that
round 2 chose (voice-vision report) and save the PDF plus the text into the
vault. *Fit:* scanned paper is outside text, so the note write gets the
2026-09-24 card ("note-writing waits for a yes after outside text"). Nothing
is auto-learned from it (learning is from the owner's own words only). A
network scanner over plain `http://` is fine inside the owner's own networks
(`jarvis_local_http`). **M.**

**13. Printer, weather station, car.** All read-only, through HA entities
Jarvis already reads with `home_read`: printer ink or toner (HA's IPP
integration), a local weather station (Ecowitt gateways GW1200/2000/3000
answer `/get_livedata_info` on the LAN, undocumented **(summary)**; best
through HA, with round 1 idea 1), and an EV's charge level (evcc, MIT, local
REST, **(summary)**). Car *commands* go through HA like any device. A car
lock, a charge-port cover and a boot are heavy: each gets its own card. **S
each.**

**14. Sleep the PC, wake for the alarm.** A scheduled Windows task with
"Wake the computer to run this task" can wake a sleeping PC before the next
alarm, if "allow wake timers" is on. Whether that works without an
administrator prompt is **not verified**. It plugs in to the one scheduler
(`jarvis_schedule.py`). Putting the PC to sleep would be an owner's command
that ends the link, so rule 4 holds: nothing acts while the phone is stale.
**M.**

## Not for Jarvis

| Idea | Why not |
|---|---|
| Using HA's Assist (`/api/conversation/process`) or its MCP action tools to control devices | They act with no card (invariant 3). Round 1 said the same for MCP. Read-only use only |
| Jarvis as its own Matter controller (matterjs-server, Apache-2.0) | It would duplicate HA: pairing needs Bluetooth and a Thread border router. It is also security-critical (locks). L, for nothing HA does not already do |
| Matter or Z-Wave lock **PIN codes** (HA 2026.4/2026.6 actions) | Passwords and PINs always wait for the owner (2026-09-24), and locks are heavy. Jarvis must never set, read or say a lock code |
| Face recognition (built into Frigate 0.16+ **(summary)**), reading Frigate's face names, "who is at the door" | Faces of other people are private details about other people. Labels only (idea 8) |
| A camera Jarvis watches continuously, or storing clips | A standing sensor with no single approval (round 2's camera rule) |
| Cloud cameras and doorbells (Ring, Nest) directly | A new way out of the PC for private images (rule 1) |
| Tracking other household members' locations | Private details about other people; only the owner's own `person.*` |
| Reaching HA through Nabu Casa or a public URL; forwarding the WOL port | Public tunnel or public opening (rule 2) |
| Jarvis running as administrator to set power limits, or controlling fan curves | One elevated process is one bug away from harming the hardware. Fan tools (FanControl) are freeware with closed source **(summary)**. Read only |
| Car control through a maker's cloud API held by Jarvis (for example Tesla's Fleet API) | A new egress lane and a key for little gain. Tesla's local Bluetooth tool does not run on Windows **(summary)** |
| Arrival or motion switching devices without a card | The lights setting needs the owner's own words. Timed home routines belong in HA's automations |
| Printing text from outside text without a card | A planted instruction could waste paper or print private text where others see it |

## Questions for the owner

1. "Turn off the downstairs lights" names a floor, not the lights. With "Lights, plugs and fans without a card" switched on, should that still need a card?
   - **Yes, a room or floor always gets one card listing every light** (recommended)
   - **No, treat a room like named lights**
2. Waking the PC while you are away needs a device at home that is always on.
   - **Use Home Assistant's own button, if you run it** (recommended)
   - **Only wake it when my phone is on home Wi-Fi**

## Sources

Read (raw files):
- HA release notes 2026.4-2026.9: https://github.com/home-assistant/home-assistant.io/tree/current/source/_posts (`2026-04-01-release-20264` ... `2026-09-02-release-20269`)
- HA core (Apache-2.0), https://github.com/home-assistant/core/tree/dev/homeassistant: `components/api/__init__.py`, `components/websocket_api/commands.py`, `components/config/area_registry.py`, `floor_registry.py`, `entity_registry.py`, `components/homeassistant/llm.py`, `components/mcp_server/server.py`, `components/camera/__init__.py`, `components/wake_on_lan/services.yaml`, `components/energy/websocket_api.py`
- matterjs-server README and LICENSE (Apache-2.0): https://github.com/matter-js/matterjs-server
- LibreHardwareMonitor README (MPL-2.0; needs admin for some sensors): https://github.com/LibreHardwareMonitor/LibreHardwareMonitor
- Licences: Bermuda (MIT) https://github.com/agittins/bermuda · NAPS2 (GPL-2.0+) https://github.com/cyanfish/naps2 · Frigate (MIT) https://github.com/blakeblackshear/frigate · tailscale-wakeonlan (MIT) https://github.com/andygrundman/tailscale-wakeonlan · UpSnap (MIT) https://github.com/seriousm4x/UpSnap · evcc (MIT, sponsor-only parts excluded) https://github.com/evcc-io/evcc · vehicle-command (Apache-2.0) https://github.com/teslamotors/vehicle-command · WeeWX (GPL-3.0) https://github.com/weewx/weewx

Search summaries only:
- WOL and Tailscale: https://tailscale.com/blog/wake-on-lan-tailscale-upsnap
- nvidia-smi: https://docs.nvidia.com/deploy/nvidia-smi/ (blocked) · power limits at boot: https://pierretempel.com/p/set-nvidia-gpu-power-limits-at-boot · savings claim: https://runaihome.com/blog/gpu-power-limit-local-ai-tokens-per-second-2026/
- HA Matter server rewrite: https://www.home-assistant.io/blog/2026/06/23/the-matter-upgrade-youve-been-waiting-for/ · https://github.com/matter-js/python-matter-server
- Frigate 0.16 face recognition: https://idtechwire.com/frigate-0-16-adds-facial-and-license-plate-recognition-to-open-source-nvr/ · releases https://github.com/blakeblackshear/frigate/releases
- Bermuda room presence: https://www.homeautomationguy.io/blog/room-location-detection-with-bermuda-and-home-assistant-8f94b
- Ecowitt local API: https://github.com/alexlenk/ecowitt_local · https://blog.meteodrenthe.nl/2023/02/03/how-to-use-the-ecowitt-gateway-gw1000-gw1100-local-api/
- evcc REST API: https://docs.evcc.io/integrations/rest-api/
- FanControl: https://github.com/Rem0o/FanControl.Releases
- NAPS2 command line: https://www.naps2.com/doc/command-line
- HA MCP (community server, annotations): https://github.com/homeassistant-ai/ha-mcp
- Tesla BLE: https://github.com/teslamotors/vehicle-command

Repo files checked: CLAUDE.md; ARCHITECTURE.md §2-4, §10; MODEL-TOPOLOGY.md; `backend/jarvis_home.py`, `jarvis_tellme.py`, `jarvis_standby_schedule.py`, `jarvis_power_switch.py`, `jarvis_hardware.py`, `jarvis_asks_first.py`, `jarvis_local_http.py`, `jarvis_owner_check.py`, `jarvis_focus.py`, `jarvis_quick.py`, `jarvis_agent.py`, `rebuilt/jarvis_compute.py`, `rebuilt/jarvis_power.py`; `commands.rs` (`sample_gpu`); the `jarvis-client` manifest; the round 1-2 and creativity reports.
