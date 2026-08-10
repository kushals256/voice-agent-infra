# Report — Vocobase cold-start challenge

**Author:** Kushal
**Date:** 2026-08-09 (UTC)  
**Platform:** Google Cloud Run v2, `us-central1`  
**Harness:** [`harness/harness.py`](harness/harness.py)  
**Primary result artifact:** [`harness/results/burst-20260810-011231.json`](harness/results/burst-20260810-011231.json)

---

## 1. Test setup

The harness implements the section-5 burst test exactly:

1. Open **10 steady** WebSocket sessions and hold them open. With Cloud Run
   `concurrency=1`, each session occupies one instance — the fleet is at
   capacity.
2. Fire **10 burst** sessions back-to-back as fast as the client can issue
   connection requests.
3. For each burst session, measure wall time from the connection request to the
   **first binary audio frame** the bot sends.
4. Report all 10 values, median, and p95. Pass if **p95 < 5 seconds**.

The bot greets on connect (`LLMRunFrame` or `TTSSpeakFrame`), so the harness
never sends microphone audio. “First audio” is the first non-empty binary
WebSocket frame from the server.

**Deploy config for the primary run:**

| Parameter | Value |
| --- | --- |
| Service | `voicebot` on Cloud Run |
| Image | `bot:v7` (Artifact Registry) |
| `concurrency` | 1 |
| `min-instances` | 20 (10 busy + 10 warm spares) |
| `max-instances` | 20 |
| Instance size | 1 vCPU / 2 GiB |
| STT + TTS | Deepgram (Aura TTS) |
| LLM | NVIDIA NIM Llama 3.1 8B |
| `GREETING_MODE` | `llm` |

**Command:**

```bash
python harness/harness.py \
  wss://voicebot-txznokm34q-uc.a.run.app/ws-client \
  --steady 10 --burst 10 --target 5.0
```

---

## 2. Burst test results

All timings are **request → first audio** for burst sessions 11–20.

| Session | Latency (s) |
| --- | --- |
| 11 | 4.753 |
| 12 | 4.774 |
| 13 | 5.103 |
| 14 | 4.928 |
| 15 | 4.397 |
| 16 | 4.949 |
| 17 | 4.061 |
| 18 | 5.456 |
| 19 | 4.776 |
| 20 | 4.749 |
| **Median** | **4.775** |
| **p95** | **5.297** |

**Connected:** 10 / 10 burst sessions received audio.

**Pass condition: p95 < 5 seconds → FAIL (by 0.30 s)**

Min: 4.061 s · Max: 5.456 s

---

## 3. Where the seconds went

Cold-start timing is instrumented in [`bot/bot.py`](bot/bot.py) via greppable
`COLDSTART {...}` JSON logs at each phase:

```
process_start → imports_done → client_connected → first_audio
```

Pulled from Cloud Run logs:

```bash
gcloud run services logs read voicebot --region us-central1 --limit 200 \
  | grep COLDSTART
```

### Measured breakdown

| Phase | Time | What it is |
| --- | --- | --- |
| **Cold container import** | **~21 s** | Python + Silero VAD + Pipecat graph load at instance startup |
| **Warm: connect → first audio (TTS greeting)** | **~0.9–1.0 s** | Burst landed on a spare that already paid the import |
| **Warm: connect → first audio (LLM greeting, this run)** | **~4.8 s median, 5.3 s p95** | What the burst test measured |

### Interpretation

The burst sessions did **not** wait for a cold container boot (~21 s). All
10/10 connected to **warm spares** that had already completed import. The
5.3 s p95 is **provider pipeline latency on a warm instance**, not
infrastructure cold start.

Approximate warm-path budget for `GREETING_MODE=llm`:

```
WebSocket connect + Cloud Run routing     ~0.3–0.5 s
NVIDIA Llama 3.1 8B time-to-first-token   ~3.0–4.0 s
Deepgram Aura TTS first audio chunk       ~0.5–1.0 s
                                          ─────────
Total (matches observed ~4.8 s median)    ~4.5–5.5 s
```

### Control experiment

With `GREETING_MODE=tts` (direct TTS greeting, no LLM), warm instances
produced first audio at **p95 ~1.0 s** when all sessions connected. This
isolates infrastructure from provider latency: the warm pool works; the LLM
TTFB is what pushes the full-greeting path over 5 s.

Later TTS runs intermittently hit **Cloud Run HTTP 429** (“Rate exceeded”) at
the GCP **20-instance quota ceiling** when 20 WebSockets were already open
with zero headroom. Requesting quota > 20 would allow a clean TTS-mode pass.

---

## 4. Idle capacity cost at 10 concurrent steady state

### Design

At 10 steady conversations, the fleet holds **10 warm spares** to absorb a
burst of 10 inside one boot window (~21 s):

```
min-instances = 20   (10 productive + 10 idle spares)
concurrency     = 1   (one WebSocket = one container)
```

Only the **10 spares** are idle capacity. The 10 busy instances serving steady
calls are productive load, not idle insurance.

### Rates

Cloud Run **us-central1**, request-based billing, 1 vCPU / 2 GiB per instance
([pricing](https://cloud.google.com/run/pricing), Aug 2026):

| Resource | Active rate | Idle rate (min-instance) |
| --- | --- | --- |
| vCPU | $0.000024 / s | $0.0000025 / s |
| Memory | $0.0000025 / GiB-s | $0.0000025 / GiB-s |

### Per-instance hourly cost

**Idle spare** (min-instance, not serving a request):

```
vCPU:    1 × $0.0000025/s           = $0.0000025/s
memory:  2 GiB × $0.0000025/GiB-s  = $0.0000050/s
total:   $0.0000075/s × 3600       = $0.027 / hr
```

**Busy call** (actively serving a WebSocket):

```
vCPU:    1 × $0.000024/s            = $0.000024/s
memory:  2 GiB × $0.0000025/GiB-s  = $0.0000050/s
total:   $0.000029/s × 3600         = $0.104 / hr
```

### Idle capacity at 10 concurrent

```
10 spares × $0.027/hr = $0.27 / hr
                       ≈ $6.48 / day
                       ≈ $197 / month   (if held warm 24/7)
```

Productive steady load (not idle capacity):

```
10 busy × $0.104/hr = $1.04 / hr
```

**Actual test-run cost:** warm 20 instances ~15 min → run test → tear down:

```
20 instances × ~$0.05/hr blended × 0.25 hr ≈ $0.25
```

Comfortably inside GCP free tier / $300 trial credit → **~$0 out of pocket**.

Scale-to-zero (`min-instances=0` + `scripts/teardown.sh`) when not testing
eliminates idle cost entirely.

---

## 5. Same design at 100 concurrent

### Productive load

```
100 busy instances × $0.104/hr = $10.44 / hr
```

### Idle capacity — two sizing choices

**Fixed spare pool** (keep 10 spares regardless of steady load — survives a
burst of 10 only, same as the 10-concurrent design):

```
10 spares × $0.027/hr = $0.27 / hr
```

**Proportional spare pool** (100 spares for 100 steady — survives a burst of
100 inside one boot window):

```
100 spares × $0.027/hr = $2.70 / hr
                        ≈ $64.80 / day
                        ≈ $1,971 / month   (if held warm 24/7)
```

### Trade-off

| Pool size | Idle cost | Survives burst of |
| --- | --- | --- |
| 10 spares (fixed) | $0.27/hr | 10 (then cold ~21 s) |
| 100 spares (proportional) | $2.70/hr | 100 |

This is the assignment’s linear bet: every spare is paid around the clock to
serve nothing most of the time. Cloud Run’s **idle billing rate** (~4× cheaper
than active) and **scale-to-zero** make the bet affordable for bounded test
windows, but do not change the curve — proportional spares still cost
linearly.

---

## 6. Summary

| Item | Result |
| --- | --- |
| Burst connectivity | **10 / 10** |
| Median (burst) | **4.775 s** |
| p95 (burst) | **5.297 s** |
| Pass (p95 < 5 s) | **FAIL** (by 0.30 s) |
| Root cause of miss | LLM TTFB on warm instances, not container cold start |
| Idle capacity @ 10 concurrent | **$0.27/hr** (10 spares) |
| Idle capacity @ 100 concurrent | **$0.27/hr** fixed / **$2.70/hr** proportional |

The warm spare pool solved the burst cold-start problem: no burst caller waited
for the ~21 s import. The remaining gap to the 5 s target is provider pipeline
time (NVIDIA Llama first token). TTS-only greeting on warm instances achieved
~1 s p95, confirming the infrastructure design is sound.

---

## 7. Reproduce

```bash
# Deploy (see README §6 for full safe-deploy playbook)
gcloud run deploy voicebot \
  --image=us-central1-docker.pkg.dev/$PROJECT_ID/bots/bot:v7 \
  --region=us-central1 --min-instances=20 --max-instances=20 \
  --concurrency=1 --cpu-boost --no-cpu-throttling \
  --set-secrets=DEEPGRAM_API_KEY=deepgram-api-key:latest,NVIDIA_API_KEY=nvidia-api-key:latest \
  --set-env-vars=GREETING_MODE=llm,PIPECAT_WEBSOCKET_AUTH=none \
  --allow-unauthenticated

# Wait ~6 min for 20 spares to finish import, then:
python harness/harness.py wss://<host>/ws-client --steady 10 --burst 10 --target 5.0

# Tear down
PROJECT_ID=$PROJECT_ID scripts/teardown.sh
```
