# Upstream reference (pipecat-quickstart)

Frozen copy of [pipecat-ai/pipecat-quickstart](https://github.com/pipecat-ai/pipecat-quickstart)
@ `main` (Aug 2026) for **diff comparison only**.

| File | Purpose |
| --- | --- |
| [`bot.py`](bot.py) | Original quickstart bot (Daily/WebRTC, Cartesia, OpenAI) |
| [`Dockerfile`](Dockerfile) | Original `dailyco/pipecat-base` image |
| [`pyproject.toml`](pyproject.toml) | Original dependency set |
| [`CHANGES.md`](CHANGES.md) | Summary of every modification in [`../bot/`](../bot/) |

**Compare:**

```bash
diff _reference/bot.py bot/bot.py
diff _reference/Dockerfile bot/Dockerfile
diff _reference/pyproject.toml bot/pyproject.toml
```

My working code lives in [`bot/`](../bot/). This folder is not executed — it
shows reviewers what I started from and what I changed.
