/**
 * model-resources.js - the Brain Model pane's "Loaded now / Resources" plate,
 * and the one COMPUTE panel words fix (2026-11-09).
 *
 * THE OWNER'S ASK, verbatim (2026-11-08, two Brain -> Model screenshots):
 * *"the model section should tell me whats currently loaded into jarvis, how
 * much memory is jarvis using of each gpu, how much other computer resources
 * jarvis is uses besides vram on the gpus, what the context size is, and any
 * other important info"* - and *"i have the coding preset loaded into jarvis
 * right now, and it still says this"* beside a COMPUTE panel reading "Runs on
 * graphics card 2" and three stale "free of" numbers while the Coding preset's
 * pooled three-card lane held the coder across all three cards.
 *
 * WHAT THIS MODULE IS. The reading and the words: it turns the backend's own
 * read-only answer (`GET /api/models/resources`, served by
 * `jarvis_model_resources.collect()`) into the plate's rows and into the
 * COMPUTE panel's corrected rows. It holds no DOM, no token, no network call
 * and no state; `brain.js` draws it, so every sentence here can be proved by a
 * node test with no browser and no GPU.
 *
 * WHAT IT MUST NEVER SAY. A number it was not given is "not reported" - never
 * 0. A per-card split of Jarvis's models is shown only when the driver reported
 * it (`gpu_share.known`); otherwise the loaded model's own total video memory
 * is shown and the missing split is said out loud. A lane that does not answer
 * is "not running", not a model with an empty memory figure. And the COMPUTE
 * panel names the cards the model is really ON (all three, for the pooled lane)
 * - never the plan's single `cuda:N` as if it were the loaded truth.
 */

/** The cards carrying a model, as the owner's words: all three, one, or two. */
export function cardsWords(indices) {
  const idx = [...new Set((indices || [])
    .map((value) => Number(value))
    .filter((value) => Number.isInteger(value) && value >= 0))].sort((a, b) => a - b);
  if (!idx.length) return "no graphics card (or the cards were not reported)";
  if (idx.length === 3 && idx[0] === 0 && idx[1] === 1 && idx[2] === 2) {
    return "all three graphics cards (0, 1, 2)";
  }
  if (idx.length === 1) return `graphics card ${idx[0]}`;
  if (idx.length === 2) return `graphics cards ${idx[0]} and ${idx[1]}`;
  return `graphics cards ${idx.slice(0, -1).join(", ")} and ${idx[idx.length - 1]}`;
}

/** A context size in words, or the honest "not reported". */
export function contextWords(tokens) {
  const value = Number(tokens);
  if (!Number.isInteger(value) || value <= 0) return "the context size was not reported";
  return `${value.toLocaleString("en-US")} tokens of context`;
}

/** A gigabyte figure (backend sends MB) with one decimal, or "". */
export function gbWords(mb) {
  if (mb === null || mb === undefined || mb === "") return "";
  const value = Number(mb);
  if (!Number.isFinite(value)) return "";
  return `${(value / 1024).toFixed(1)} GB`;
}

/** A gibibyte figure (backend sends bytes) with one decimal, or "". */
export function gibWords(bytes) {
  if (bytes === null || bytes === undefined || bytes === "") return "";
  const value = Number(bytes);
  if (!Number.isFinite(value)) return "";
  return `${(value / (1024 ** 3)).toFixed(1)} GiB`;
}

/** A time-of-day for the read, or "" when the answer carried none. */
export function readTimeWords(payload) {
  const words = payload && typeof payload.read_at_words === "string"
    ? payload.read_at_words.trim() : "";
  if (words) return words;
  const stamp = Number(payload && payload.read_at);
  if (!Number.isFinite(stamp) || stamp <= 0) return "";
  return new Date(stamp * 1000).toLocaleTimeString();
}

/** One loaded lane: the model, its context and the cards it is really on. */
export function loadedLaneWords(lane) {
  if (!lane || typeof lane !== "object") return "";
  if (lane.state === "unreachable") return "not running - nothing answers on that lane";
  if (!lane.loaded) return "nothing loaded";
  const bits = [String(lane.model || "a model"),
    contextWords(lane.context_length),
    cardsWords(lane.gpu_indices)];
  const percent = Number(lane.on_card_percent);
  if (lane.spill_bytes != null && Number(lane.spill_bytes) > 0) {
    const mib = Math.round(Number(lane.spill_bytes) / (1024 ** 2));
    bits.push(`${Number.isFinite(percent) ? `${percent}% on the cards` : "partly on the cards"}: `
      + `${mib.toLocaleString("en-US")} MiB spilled into system RAM`);
  } else if (Number.isFinite(percent) && percent >= 100) {
    bits.push("100% on the cards, nothing spilled into system RAM");
  } else if (lane.spill_bytes != null) {
    bits.push("nothing spilled into system RAM");
  }
  return bits.join("; ");
}

/** How much video memory Jarvis's own loaded models hold, and whether the
 *  per-card split was measured - said honestly either way. */
export function shareWords(payload) {
  const share = (payload && payload.gpu_share) || {};
  const lines = [];
  if (!share.known) {
    if (Number(share.loaded_vram_gib) > 0) {
      lines.push(`Jarvis's loaded model holds ${share.loaded_vram_gib} GiB of video `
        + "memory in total across " + cardsWords(share.cards) + ".");
    }
    lines.push("This PC's graphics driver does not report how much of each card "
      + "belongs to which program, so Jarvis's share of each card is not shown "
      + "as a number.");
    return lines;
  }
  for (const gpu of payload.gpus || []) {
    const jarvis = gbWords(gpu.jarvis_mb);
    if (!jarvis) continue;
    lines.push(`Card ${gpu.index}: Jarvis's models use ${jarvis} of the `
      + `${gbWords(gpu.used_mb)} other programs are not using on it.`);
  }
  return lines;
}

/** Per-card free/total and Jarvis's share, as strings (never a 0 for unknown). */
export function gpuLines(payload) {
  const lines = [];
  for (const gpu of (payload && payload.gpus) || []) {
    const free = gbWords(gpu.free_mb);
    const total = gbWords(gpu.total_mb);
    if (!total) continue;
    let line = `Card ${gpu.index} - ${gpu.name || "graphics card"}: `
      + `${free || "free memory not reported"} free of ${total}`;
    const jarvis = gbWords(gpu.jarvis_mb);
    if (jarvis) line += `; Jarvis's models use ${jarvis}`;
    lines.push(line);
  }
  return lines;
}

/** Jarvis's own resident memory and processor use, in the OS's numbers. */
export function jarvisWords(jarvis) {
  if (!jarvis || jarvis.available === false) {
    return "Jarvis's own memory and processor use could not be read on this PC.";
  }
  const bits = [];
  if (Number.isFinite(Number(jarvis.rss_mb))) bits.push(`${Math.round(Number(jarvis.rss_mb))} MiB of RAM`);
  if (Number.isFinite(Number(jarvis.cpu_percent))) {
    bits.push(`${Number(jarvis.cpu_percent).toFixed(1)}% of the processor on average since it started`);
  }
  let said = bits.length ? `Jarvis itself is using ${bits.join(" and ")}.`
    : "Jarvis's own memory use was not reported on this PC.";
  if (Number.isFinite(Number(jarvis.model_servers_rss_mb))) {
    said += ` The Ollama model servers it runs are using ${Math.round(Number(jarvis.model_servers_rss_mb))} MiB more.`;
  }
  return said;
}

/** The whole plate, as plain data `brain.js` draws without inventing a word. */
export function plateModel(payload) {
  if (!payload || payload.available === false) {
    return {
      available: false,
      why: String((payload && payload.why) || "this backend does not report loaded models"),
      readAt: "",
      lanes: [],
      gpus: [],
      share: [],
      jarvis: "",
      warnings: [],
    };
  }
  const lanes = (payload.lanes || []).map((lane) => ({
    key: lane.key,
    title: lane.label || lane.key || "lane",
    state: lane.state || (lane.loaded ? "loaded" : "unknown"),
    loaded: Boolean(lane.loaded),
    model: String(lane.model || ""),
    words: loadedLaneWords(lane),
  }));
  return {
    available: true,
    why: "",
    readAt: readTimeWords(payload),
    lanes,
    gpus: gpuLines(payload),
    share: shareWords(payload),
    jarvis: jarvisWords(payload.jarvis),
    warnings: (payload.warnings || []).map(String),
  };
}

/** The COMPUTE panel's rows, corrected to what is really loaded. When the
 *  backend's resources answer is absent, the plan's rows are kept and labelled
 *  as a plan - never dressed up as the loaded truth. */
export function computeModel(payload) {
  const plan = payload || {};
  if (!plan.available) {
    return { available: false, readAt: "", loaded: [], rows: [], share: [], jarvis: "" };
  }
  const loaded = [];
  for (const lane of plan.lanes || []) {
    if (!lane.loaded) continue;
    loaded.push({
      lane: lane.label || lane.key,
      model: String(lane.model || ""),
      context: contextWords(lane.context_length),
      cards: cardsWords(lane.gpu_indices),
      percent: Number.isFinite(Number(lane.on_card_percent))
        ? Number(lane.on_card_percent) : null,
      spill: lane.spill_bytes == null ? null : Number(lane.spill_bytes),
    });
  }
  const rows = [];
  for (const lane of plan.lanes || []) {
    if (!lane.loaded && lane.state !== "unreachable") continue;
    rows.push({ key: `lane ${lane.label || lane.key}`, value: loadedLaneWords(lane) });
  }
  return {
    available: true,
    readAt: readTimeWords(plan),
    loaded,
    rows,
    share: shareWords(plan),
    jarvis: jarvisWords(plan.jarvis),
    gpus: gpuLines(plan),
    warnings: (plan.warnings || []).map(String),
  };
}
