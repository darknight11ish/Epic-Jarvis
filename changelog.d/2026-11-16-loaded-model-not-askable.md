- **The loaded model cannot be asked for** — the answer to "what model are you
  using" names the model Jarvis is *set* to use, and it says that is the model it
  answers with; nothing in chat can say what is actually resident, because "what
  models are loaded", "how many models are installed", "which model is loaded"
  and "what model is loaded right now" all fall through to the model's own guess.
  Measured on the deployed install on 2026-11-16, where the configured model was
  `qwen3.5:9b` and neither Ollama lane held it: the everyday lane held
  `jarvis-primary:latest` (a rename of `qwen3:8b`) and the other held
  `gemma4:12b-it-qat`. Recorded as **DEF-079**, with the two readers a fix needs
  already in the backend and unused by any answer — `jarvis_models.offload_status()`
  returns the loaded names straight from `/api/ps`, and `jarvis_models.installed()`
  returns the 23 installed ones.
