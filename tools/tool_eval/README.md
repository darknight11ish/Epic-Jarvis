# Tool test: how well a local model picks and fills Jarvis's tools

`ollama_tool_eval.py` sends 65 made-up requests to a model in Ollama on this
PC, the same way Jarvis does, with Jarvis's real tool list (read from
`backend/jarvis_agent.py`; `jarvis_tools.json` is a saved copy used only if
that cannot be read). It scores whether the model picks the right tool,
fills it in correctly, and stays quiet when no tool fits. **Nothing is
run** - tool calls are only read and scored - and it only talks to Ollama
at 127.0.0.1.

Run it from the repository folder (one line; the first part downloads the
model to test, about 3.4 GB):

```
ollama pull qwen3.5:4b; py -3 tools\tool_eval\ollama_tool_eval.py --models jarvis-primary qwen3.5:4b --repair
```

The scores print in the window and are saved to
`tools\tool_eval\tool_eval_results.json`. Testing a model switches nothing:
Jarvis keeps using `jarvis-primary` until you change it.

Self-test without a model: `python3 tools/tool_eval/ollama_tool_eval.py --selftest`.

Written for the research in `docs/RESEARCH-2026-09-24.md` §6.
