# What I changed from pipecat-quickstart

Upstream snapshot is in this folder. Modified code is in [`../bot/`](../bot/).

## Summary

| Area | Upstream | My version |
| --- | --- | --- |
| Transport | Daily / WebRTC via `create_transport()` | **Plain WebSocket** (`-t websocket`) for Cloud Run |
| Hosting target | Pipecat Cloud / local browser | **Self-hosted Cloud Run**, `concurrency=1` |
| TTS | Cartesia | **Deepgram Aura TTS** (Cartesia free tier = 2 concurrent streams) |
| LLM | OpenAI only | **NVIDIA NIM Llama 3.1 8B** (OpenAI credits exhausted) + OpenAI fallback |
| Serializer | Default transport encoding | **`raw_serializer.py`** — raw PCM so harness times first binary frame |
| Observability | Loguru info lines | **`COLDSTART` JSON logs** — process_start → imports_done → first_audio |
| Dependencies | webrtc, daily, cartesia extras | **Slimmed** — silero, deepgram, openai, websocket only |
| Docker base | `dailyco/pipecat-base` (arm64) | **`python:3.12-slim` + uv** (amd64 for Cloud Run, smaller pull) |
| Greeting | LLM only | Configurable **`GREETING_MODE=llm|tts`** for latency experiments |

## New files (not in upstream)

| File | Why |
| --- | --- |
| [`../bot/raw_serializer.py`](../bot/raw_serializer.py) | Raw PCM WebSocket serializer for deterministic first-audio timing |
| [`../infra/`](../infra/) | Terraform — Cloud Run, Artifact Registry, Secret Manager |
| [`../harness/harness.py`](../harness/harness.py) | Burst latency test client |
| [`../scripts/`](../scripts/) | build, deploy, set warm pool, run test, teardown |

## `bot.py` — key modifications

1. **WebSocket transport** instead of Daily/WebRTC — Cloud Run speaks HTTP/WSS, not UDP.
2. **`RawAudioServerSerializer`** wired into `WebsocketServerTransport` params.
3. **`COLDSTART` timing** at module import, post-import, client connect, first audio.
4. **`NvidiaLLMService`** — OpenAI-compatible client pointed at NVIDIA NIM API.
5. **`_create_llm()`** — picks NVIDIA when `NVIDIA_API_KEY` is set, else OpenAI.
6. **`DeepgramTTSService`** replaces Cartesia.
7. **`GREETING_MODE`** env — `tts` queues `TTSSpeakFrame` (~1s warm); `llm` queues `LLMRunFrame` (~5s warm).
8. **Entry point** — `main()` runs websocket server on `$PORT` (Cloud Run injects 8080).

## `Dockerfile` — key modifications

1. **`python:3.12-slim`** instead of `dailyco/pipecat-base` — amd64 for Cloud Run, no arm64 mismatch.
2. **`libgomp1`** for onnxruntime (Silero VAD).
3. Copies **`raw_serializer.py`** alongside `bot.py`.
4. **CMD** starts WebSocket transport on `${PORT:-8080}`.

## `pyproject.toml` — key modifications

1. Renamed project to `warm-pool-voice-agent`.
2. Removed **`webrtc`, `daily`, `cartesia`** extras — fewer imports, faster cold start.
3. Added **`websocket`** extra for the plain WS transport.

## Everything else in the repo (not bot changes)

Net-new infrastructure and tooling beyond the quickstart:

- **Infrastructure:** warm spare pool via Cloud Run `min-instances`, Terraform IaC.
- **Harness:** 10 steady + 10 burst sessions, p95 on request → first audio.
- **Measurement:** proved ~21s cold import vs ~1s warm TTS vs ~5s warm LLM path.
