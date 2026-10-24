#!/usr/bin/env python3
"""jarvis_live_turn.py - one whole Live turn over the persistent stream (G2b).

WHAT THIS IS. G2 (`jarvis_live_stream.py`) carries the phone's audio frames and
hands one complete WAV to a speech sink. This module is that sink: it turns the
WAV into one answer and gives the answer back as 16 kHz mono PCM frames, so
`end_turn` -> words -> an answer -> speech happens on the PC while the phone
just plays what arrives.

THE PATH, step by step (all local, all on this PC):
  1. `jarvis_speech.hear(wav, source="live", mic="phone")` - the SAME one-shot
     check every Live clip goes through: session on for this device, cards,
     mute, the owner check, then words. A clip that fails the owner check
     never reaches the model and its words are discarded, exactly as there.
  2. The answer is asked for over the PC's own loopback `/api/chat` route -
     the same route both apps already use - with the chat message marked
     `"live": True`, which is how `jarvis_agent` knows to add the Live note and
     the side-talk rules. WHY A SELF-CALL: that answer chain is written inline
     in the HUD server's route body (base `jarvis_hud.py` + patches), not a
     reusable function, and re-implementing it here would be a second, less
     tested path. Reusing the route means no HUD base or patch edit, and the
     cost - one extra loopback hop per turn - is measured in the design's G4
     slice rather than assumed cheap.
  3. `jarvis_speech.say(answer)` - the same text-to-speech the apps call - and
     its WAV is split into the design's 64 ms PCM frames.

WHAT IT DOES NOT DO (honest limits, said here so no doc can overclaim):
  * The speech hand-off is whole-WAV: `say()` returns the complete answer and
    this module chunks it. FIRST-FRAGMENT TTS STREAMING IS A LATER PHASE; the
    owner hears nothing until the whole answer exists. That is the first
    honest slice, not the final latency.
  * No audio is written to a file, logged or kept: WAVs exist in RAM for the
    length of one turn.
  * The switch `[live] stream` must still be ON (it ships OFF) before anything
    in this file is reachable at all; and G4 measures the real phone before
    any of it is claimed as working.
"""

from __future__ import annotations

import http.client
import io
import json
import wave

#: The design's frame shape (same as jarvis_live_stream.py).
SAMPLE_RATE = 16000
FRAME_BYTES = 2048
#: One answer can take a while on the local model; the loopback wait is bounded.
CHAT_TIMEOUT_S = 900.0

#: Plain sentences the phone may show; the same shape as jarvis_live_stream.WORDS.
WORDS = {
    "no_voice": "Jarvis can't speak the answer yet - the voice engine is not "
                "installed here.",
    "chat_failed": "Jarvis could not finish that answer - try once more.",
    "no_link": "Jarvis lost the link to its own brain - press Live again.",
}

#: Hooks, injected by the suite so the whole path runs with no model, no voice
#: check and no TTS engine. `None` means "use the real one" at call time.
HEAR = None
CHAT = None
SAY = None


# ------------------------------------------------------------------ defaults ----

def _default_hear(wav: bytes):
    import jarvis_speech
    return jarvis_speech.hear(wav, source="live", mic="phone")


def _default_say(text: str):
    import jarvis_speech
    return jarvis_speech.say(text, mic="phone")


def _delta(chunk: dict) -> str:
    """The text a chat chunk adds, from the shapes the PC's route can send."""
    choices = chunk.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        for part in ("delta", "message"):
            box = first.get(part)
            if isinstance(box, dict) and isinstance(box.get("content"), str):
                return box["content"]
        if isinstance(first.get("text"), str):
            return first["text"]
    for name in ("content", "response", "text"):
        if isinstance(chunk.get(name), str):
            return chunk[name]
    return ""


def _terminal(chunk: dict) -> bool:
    if chunk.get("done") is True or chunk.get("finished") is True:
        return True
    choices = chunk.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        if choices[0].get("finish_reason"):
            return True
    return False


def ask_pc(text: str, *, token: str, port: int, timeout: float = CHAT_TIMEOUT_S) -> dict:
    """Ask the PC's own `/api/chat` for one answer -> {"ok", "text"|"why"}.

    It sends the same token the phone's stream arrived with (never logged),
    marks the message `live: true` so the Live note applies, and reads the
    OpenAI-style SSE chunks the route already produces. It talks to 127.0.0.1
    only - the same listener that is serving this stream.
    """
    body = json.dumps({"messages": [{"role": "user", "content": text,
                                     "live": True}],
                       "stream": True}).encode("utf-8")
    conn = http.client.HTTPConnection("127.0.0.1", int(port), timeout=timeout)
    try:
        conn.request("POST", "/api/chat", body=body, headers={
            "Content-Type": "application/json",
            "X-Jarvis-Token": token,
            "X-Jarvis-Client": "hud",
        })
        resp = conn.getresponse()
        if resp.status != 200:
            return {"ok": False, "why": WORDS["chat_failed"]}
        words = []
        while True:
            line = resp.readline()
            if not line:
                break
            line = line.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except Exception:
                continue
            if not isinstance(chunk, dict):
                continue
            if chunk.get("error"):
                if isinstance(chunk["error"], dict):
                    chunk["error"] = chunk["error"].get("message") or str(chunk["error"])
                return {"ok": False, "why": WORDS["chat_failed"]}
            words.append(_delta(chunk))
            if _terminal(chunk):
                break
        answer = "".join(words).strip()
        if not answer:
            return {"ok": False, "why": WORDS["chat_failed"]}
        return {"ok": True, "text": answer}
    except Exception:
        return {"ok": False, "why": WORDS["chat_failed"]}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def pcm_from_wav(wav: bytes) -> bytes:
    """The WAV's samples, header stripped; empty when it is not mono 16-bit.

    `say()` promises a WAV; anything else is refused rather than guessed at,
    except that raw PCM is passed through untouched (a shorter path with the
    same frame shape is a legitimate future optimisation).
    """
    if not wav:
        return b""
    if not (wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"):
        return b"" if wav[:4] == b"RIFF" else bytes(wav)
    try:
        with wave.open(io.BytesIO(bytes(wav)), "rb") as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2:
                return b""
            return w.readframes(w.getnframes())
    except Exception:
        return b""
    finally:
        pass


def speech_frames(pcm: bytes, size: int = FRAME_BYTES) -> list:
    """One answer's PCM as the design's frames (the last one may be shorter)."""
    return [bytes(pcm[i:i + size]) for i in range(0, len(pcm), size) if pcm[i:i + size]]


# --------------------------------------------------------------------- turn ----

def turn(wav: bytes, ctx: dict | None = None) -> dict:
    """One WAV in, one answer out: {"ok", "text"?, "speech", "not_owner"?}.

    `ctx` carries what `jarvis_live_stream.serve` knows about the request:
    `token` (the phone's own token, for the loopback call), `port` (this
    server's listener) and `device`. A failed step returns `ok: False` and a
    plain sentence in `why`; nothing is ever half-answered.
    """
    ctx = ctx or {}
    heard = (HEAR or _default_hear)(wav)
    facts = heard.as_dict() if hasattr(heard, "as_dict") else heard
    if not isinstance(facts, dict):
        return {"ok": False, "why": WORDS["chat_failed"], "speech": []}
    # A voice that is not the owner is a normal, silent outcome: no words are
    # made of it and the PC says so in fixed words (never anything heard).
    if facts.get("is_owner") is False or facts.get("owner") is False:
        return {"ok": True, "not_owner": True, "speech": []}
    text = str(facts.get("text") or "").strip()
    if not text:
        return {"ok": True, "text": "", "speech": []}
    token = str(ctx.get("token") or "")
    port = int(ctx.get("port") or 0)
    if not token or port <= 0:
        return {"ok": False, "why": WORDS["no_link"], "speech": []}
    asked = (CHAT or ask_pc)(text, token=token, port=port)
    if not asked.get("ok"):
        return {"ok": False, "why": asked.get("why") or WORDS["chat_failed"],
                "speech": []}
    answer = str(asked.get("text") or "").strip()
    if not answer:
        return {"ok": False, "why": WORDS["chat_failed"], "speech": []}
    try:
        raw = (SAY or _default_say)(answer)
    except Exception:
        raw = None
    if not raw:
        return {"ok": False, "why": WORDS["no_voice"], "speech": []}
    pcm = pcm_from_wav(raw)
    if not pcm:
        return {"ok": False, "why": WORDS["no_voice"], "speech": []}
    return {"ok": True, "text": answer, "speech": speech_frames(pcm)}
