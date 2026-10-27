
## 2026-10-27 — The "no standing grant" rule is changed by the owner: cloud escalation becomes a switch

The rule that this replaces, in `jarvis_router.choose()`'s own words, was the
owner's decision of 2026-09-24: cloud use is "per use, with permission ... and
asks. **No standing grant.**" Every gate below gate 6 still runs first and can
still only push a turn back to local; what changed is **who says yes**, and
there is now a third answer besides "the owner clicked for this one question"
and "nobody".

**What the owner asked for, 2026-10-27.** A checkbox in the Presets menu -
"escalate to the cloud when the work is too complex" - which, once on, lets
Jarvis send a hard question to the one cloud provider he has chosen without
asking him first. He also asked for the Cloud row itself to sit in that menu
beside General/Coding/Agentic+Vision/Fast, with the six connected API services
under it, and for the three lane names (`jarvis-escalate`, `jarvis-critic`,
`jarvis-bulk`) to become one.

**Why it is not simply a loosening nobody can see.** Four things bound it, and
each is proved rather than described:

  * **ONE card, at ON, and nothing before it.** `POST /api/work/cloud-escalate`
    raises one `change_own_config` card; a refused card writes nothing. Turning
    it OFF is a tightening and is instant - the same asymmetry every other
    switch in this program keeps.
  * **The PC's own file is the only source of the standing yes.** It is read by
    `jarvis_router.standing_escalation()` at gate 6 and from nowhere else - no
    request body, no header and no client flag. The HUD page's own `cloud_yes`
    counts only while that file says on, so a page that has not refreshed
    cannot defeat the switch. Another client's `cloud_yes` (the phone's "Try
    the cloud model") is the per-question tap it already was and is unchanged.
  * **"Escalate this" typed in the message is a yes for that turn only.**
    A fixed phrase list, evaluated at gate 6, after every privacy gate. Nothing
    is stored; the next message has to ask again.
  * **Every gate is untouched and still first.** Lockdown, a tainted
    conversation, a picture, the words off the screen, a private topic, a
    pasted secret, the monthly money limit: a turn refused by any of them stays
    local, and `backend/test_cloud_escalate_setting.py` drives each one with the
    switch ON and the phrase present.

**What this does NOT authorise, said plainly.** No new route reaches the
cloud. No key can be typed, pasted or sent from either app (rule 3): the
provider list carries the command line to run on the PC, and nothing else. The
phone reads the setting and never writes it - turning it on needs the card, and
the card lives on the PC (`docs/ARCHITECTURE.md` §8). One provider at a time.
The money limit still decides whether a message can be sent at all.

**One honest limitation, measured not assumed.** The questions that escalate
are the ones the cloud most often answers with its working-out instead of an
answer: four of four measured escalated turns came back
`finish_reason: "length"` with empty `content`
(`docs/FIELD-TEST-CLOUD-ESCALATION-2026-10-14.md`). On a turn the owner did not
click for, that working-out is **not** shown; the PC answers it instead, under
one line saying the cloud did not answer. That is a real change in what he
sees on those turns, and it is recorded here because the alternative - a page
of a model's private reasoning offered as an answer to a question nobody asked
to send anywhere - is worse than an honest sentence.

**What this replaces, and only that.** The 2026-09-24 "no standing grant" rule,
in the one place it governs cloud escalation. Nothing else moves: the
per-question yes both apps already had, the offer gate, the taint latch, the
private-topic backstop and the secret scan are all as they were, and
`docs/ARCHITECTURE.md` §11's cloud paragraph is amended to point here.

## 2026-10-27 — F-01: a lane you pick by hand runs the same privacy gates

  * **What was wrong, and how it was found.** Two independent reviews on
    2026-10-27 found the same bypass, and it was re-verified against the
    published base before anything changed. `POST /api/chat` picks a lane in
    `jarvis_hud.py`'s `do_POST`, and it had two paths. The automatic one called
    `jarvis_router.choose()`, which runs every gate in a fixed order. The manual
    one - `"auto": false` with a `"lane"` - called
    `_manual_decision(chosen, local_model)`, which built a `Decision` with
    `gate: "manual"` and ran no gate at all. Any client with the pairing token
    could therefore send `{"lane": "<cloud lane>", "auto": false}` and have that
    turn answered on a cloud model with private memory text, a tainted
    conversation, a picture, or the owner's screen attached. Neither shipping
    client sends `lane` today, which is why it was latent rather than seen - not
    why it was safe.
  * **The rule, decided before the change was written.** A manual pick of the
    local model is exactly what it was. A manual pick of any other lane is used
    ONLY when the decision the automatic path would have made for that same turn
    landed on a cloud lane; the pick stands in for the owner's own yes for that
    one question and answers gate 6, nothing else. A refused pick stays on the
    local model and says why. Nothing may leave this PC "just because the owner
    picked the lane".
  * **How it is built, and why that shape.** There is now ONE
    `jarvis_router.choose(...)` call and both paths reach it
    (`if ROUTING:` plus `manual_pick = not body.get("auto", True)`), so a gate
    added to it can never reach one path only - the drift was the defect. The
    rule itself lives in a pure function, `_manual_lane(decide, chosen,
    local_model, lanes)`, so it can be proved by calling it rather than by
    driving a running HUD; `_manual_decision()` turns its answer into the
    `Decision` the rest of the turn reads, and with no router at all a cloud
    pick fails closed to the local model.
  * **What a refused pick looks like, and what it deliberately does not add.**
    No wire field. `X-Jarvis-Route` carries the router's own `gate`
    ("taint", "image", "screen", "private", "secret", "budget", "complexity",
    "lockdown", "unavailable", "cloud_model"), `where` is "local", `lane` is
    the local model, and `reason` is one plain sentence - the same shape a
    refused automatic decision already has, which both apps already draw as
    local. A lane this PC does not offer and a PC with no `jarvis_router.py`
    also stay local. A local pick is untouched: same lane, same reason, same
    gate, memory riding along as before.
  * **The one place the rule is stricter than the brief's examples, said
    plainly.** The brief listed the privacy and availability refusals. The
    implemented rule also refuses a pick on gate 4 (the complexity threshold)
    and gate 5 (the cloud budget), because "the same decision would have
    permitted a cloud lane" is the only reading that cannot be argued with, and
    the safe direction is to refuse. The product consequence, stated rather than
    discovered later: a cloud lane picked by hand answers a SHORT question on
    the local model, with the reason shown. If the owner would rather a manual
    pick outrank the complexity heuristic, that is a one-line change in
    `_manual_lane()` and a decision to record here - never a quiet edit.
  * **Cost, recorded because a reviewer should see it.** Three of the patch's
    four hunks read the owner's own HUD text: the manual path exists nowhere
    else, and `_manual_decision()` is the function whose gates were missing, so
    none of the three can anchor on text an earlier patch writes. `_stack.py`'s
    `jarvis_hud.py` RATCHET moves 58 -> 61 and
    `tools/check_patch_original_text.py` pins
    `f01-manual-lane-gate.patch` at 3 hunks / 37 lines, both with the reason
    written down. The fourth hunk anchors on the line `cloud-say-yes.patch`
    writes and costs nothing. No install block, no gate tier, no app file.
  * **Proven by:** `backend/test_hud_manual_lane_gate.py` - the patch applies to
    the published base and reverses out of it byte for byte; one
    `jarvis_router.choose()` call is counted as an ast node; `_manual_lane` is
    driven with REAL router decisions for a tainted conversation, a picture,
    the owner's screen, a private question, a pasted secret, Lockdown, a spent
    budget, an Ollama cloud model as the everyday model, a lane this PC does not
    offer, and no router at all; the local pick is shown unchanged; and the
    CONTROL lifts the OLD `_manual_decision()` out of the patch's own removed
    lines and shows it returning the cloud lane for the same tainted turn,
    which is what fails on today's code. **Not proven here:** a real HUD process
    answering a crafted `{"lane": ..., "auto": false}` request - this suite
    drives the functions out of the patched file, not the server, and that
    end-to-end run is a field test, never a pass.
