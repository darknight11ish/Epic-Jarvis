- **2026-11-14 — The measured card list counts every card nvidia-smi reports:**
  `jarvis_model_recommendations.measured_gpus()` now lists a card because it is
  in the PC and its size was read, not because the running Ollama's log happens
  to name it. `jarvis_hardware.detect()` already reported all three cards
  (measured on the owner's PC 2026-11-14: a 12 GB RTX 2060 and two 8 GB RTX 2080
  SUPERs, driver 617.42, 28,672 MiB) and the parser was never the problem; the
  bug was this module's own `used is False` filter, which turned "this Ollama
  does not use it" into "not a measured card" and sized every catalogue
  candidate for one 8 GB card. The `used` flag keeps its meaning everywhere else
  - the Hardware page and preset planning still say which cards Ollama uses -
  and `measured_gpus` keeps `jarvis_hardware.detect()` as its one nvidia-smi
  source (through `jarvis_compute`), so no second parser and no second
  nvidia-smi process were added; `jarvis_bench.read_cards()` was not needed for
  this. A card Ollama dropped that nvidia-smi never saw is still excluded, and
  an empty list still reaches `/api/models/check`'s existing plain 503 sentence,
  so a PC whose cards cannot be read is said in words rather than guessed at.
