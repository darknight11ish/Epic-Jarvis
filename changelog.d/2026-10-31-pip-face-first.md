- **Picture-in-picture: the model first, icons for Live:** the owner's two
  screenshots showed the small window squeezing the face beside "Standing by"
  and a cut-off answer sentence, and Live's "End Live" / "Mic off" as text
  links. Mode 1 now draws the face filling the window and **no wording at all**;
  mode 3's no-session fallback keeps the face filling the window with its one
  short fixed line; and Live draws the face filling most of the window with the
  small status line still at the bottom and the two buttons replaced by **icons**
  (a stop icon for End Live, a mic-on/mic-off icon for the toggle), each with its
  old words as the accessibility description and calling the exact same
  `JarvisRuntime.liveEndNow("owner")` / `JarvisRuntime.liveMute(...)` doors. The
  hidden/App-lock layout is untouched (dimmed face + LOCKED sentence), nothing
  approves or sends, and the window's only system action is still Expand. Two
  new vector drawables, no new icon dependency; phone-only (`PipTest` pins the
  branches, the drawables and the unchanged calls).
