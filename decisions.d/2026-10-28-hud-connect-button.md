- **2026-10-28 — The HUD window gets the lane's one action, and the reason it
  was kept off it no longer applies:** Every other surface that draws the
  standing "the local model isn't running" line - the Jarvis bar, the widget and
  the phone's Home - has offered "Start the local model" since 2026-10-13, and
  the HUD deliberately did not, because its reads were a fixed list in
  `hud_proxy.rs` and widening an allow-list for a route that starts a program on
  the PC was its own decision with its own review. The owner has now asked for
  the button in his own words ("when jarvis gets opened on the desktop from
  scratch, there should be a connect button next to these notifications saying
  its offline"), and the review that decision was waiting for is this one: the
  action was never a page fetch, it is a Tauri command that adds the token in
  Rust, so the grant is one narrow permission set (`hud-lane`: the bar's
  `read_model_lane` and `start_model_lane`) and `hud_proxy.rs` is untouched. The
  new decision does not widen what a script in that page can reach beyond what
  the bar's own button does: it starts the lane this PC's chat is pointed at -
  looked up on that PC by the owner's own task, never a command line built in the
  page - raises no card (his logon already runs that task unattended), and
  cannot start the other lane or switch the automatic restart on
  (`allow-set-model-lane-auto` is deliberately not in the set). What it replaces
  is the 2026-10-13 ruling that the HUD keeps the line and offers no button;
  nothing else about the lane's permission model changes. What it deliberately
  does not do: add a route, add a command, change `hud_proxy.rs`'s allow-list,
  or touch the automatic-restart switch's owners.
