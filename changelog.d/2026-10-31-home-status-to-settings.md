- **Home's status wording moves into Settings:** the top of Home carried the
  PC's own paragraph "Jarvis is not starting the local model by itself:
  automatic restarting is off." and its "Restart it automatically again" button
  all the time (the owner's screenshot: "it's there all the time and unnecessary.
  it should be in settings"). The sentence, its switch and the press's own
  refusal now live in a Settings card, **The local model** (`ModelLaneSection.kt`),
  findable by its own Settings-search row and jump entry; the switch calls the
  same `JarvisRuntime.setLaneAuto` as before and still asks the PC rather than
  claiming the change. Home keeps its compact link indicator (the dot and
  "Connected"), its one-tap History link, and the Start button - which appears
  only while the lane is really down. The feature is moved, not removed.
