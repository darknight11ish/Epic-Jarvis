# Work order, 2026-10-05

**The owner's decisions, recorded verbatim in intent.** Fourteen choices were
offered as tappable questions and every recommendation was taken, except the last
one, where the owner asked for a pull request. Nothing here needs asking again.

Started at 2026-10-05 08:50 PDT, after the fourteen-pass audit
([AUDIT-PASS-2026-10-05.md](AUDIT-PASS-2026-10-05.md)).

## Decided

| # | Decision | The owner chose |
|---|---|---|
| 1 | What to fix first | **All three critical bugs**: the widget that can approve the wrong card, the voice gate that fails open, and run the check for whether the model is spilling onto the processor |
| 2 | The five PC-only files | **Snapshot them and add the backend to backups.** Snapshot stays **outside the public repo** |
| 3 | The rest of the audit | **All of it** - dead features, the four guards, the tests that cannot fail, the false statements, log retention, the card measurement, the install path, the security pair, the UI batch, the dead weight |
| 4 | The 12 GB card | **Measure first**, then switch on what the numbers support |
| 5 | Meta's Glimmer | **Measure Qwen 3.5 9B first**, then try Glimmer across both cards |
| 6 | Install path | **Build it** - scripted backend install, an installer, and the signing key so CI can publish it |
| 7 | Security pair | **Both** - retire the shared pairing key, and stop alerts defaulting to a public service |
| 8 | The phone's menu row | **Show it by default**, keep "hide" as an option |
| 9 | Settings | **Merge 33 cards to about 20**, nothing deleted |
| 10 | The HUD's keyboard route | **Add a shortcut**, off until the owner picks one |
| 11 | Test honesty | **Fix both** - the 141 lines that print PASS without checking, and the patch tool that invents missing text instead of failing |
| 12 | Applying the fixes | **The Lead applies them** to the owner's PC, after verifying them in the repo, and confirms Jarvis still starts |
| 13 | GitHub | **Push the branch and open a pull request** (the owner merges) |
| 14 | Publishing the five files | Snapshot private; publishing them stays the owner's separate decision |

## The order of work

1. **Fix and prove in the repo** - the four workstreams already running (widget,
   voice gate, the four guards, the five-file rescue) plus the four started with
   this order (install path; the security pair and the two default changes;
   Settings merge and the wording pass; test honesty and the measurement kit).
2. **Verify** - review every diff, run each suite the change touches, run the four
   new guards over the whole tree, and confirm each new test fails when its fix is
   reverted.
3. **Commit** with a timestamped message, one commit per workstream so a revert is
   possible.
4. **Push the branch and open the pull request** for the owner to merge.
5. **Apply to the owner's PC** - `apply-patches.ps1`, then confirm the backend
   starts and the preflight passes. This is the step that makes any of it real.
6. **The measurements** - the owner runs the two card checks (the kit is written
   by workstream D), and the numbers go on a scoreboard page before anything is
   switched on.

## What only the owner can do

- **Run the two measurement commands** on the PC (the kit prints them and reads
  the output back in plain words). Nothing is switched on until the numbers are in.
- **Press Merge** on the pull request.
- **Decide later** whether the five PC-only files ever go public.

## What is deliberately not in this order

- `videos/` - the owner keeps every launch video; it is not dead weight.
- The 121 patches and `backend/patch-history/` - they are the shipping mechanism.
- Anything requiring a rendered window or a running phone: no Playwright and no
  Android SDK here, so those items stay verified by reading until the owner runs
  the apps.
