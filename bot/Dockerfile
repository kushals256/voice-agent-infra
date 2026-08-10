# Self-contained linux/amd64 image for Cloud Run.
#
# We build our own slim base instead of dailyco/pipecat-base because that image
# is published arm64-only, while Cloud Run runs amd64. Our dependency set has no
# torch (Silero VAD uses onnxruntime), so a slim Python image + libgomp1 (OpenMP
# for onnxruntime) is enough. This also gives us a deliberately small image,
# which helps cold-start pull time.
FROM python:3.12-slim

# uv binary from its official (multi-arch) image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Runtime system lib: onnxruntime needs OpenMP.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON=python3.12

# Install locked deps into the project venv (reproducible).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

COPY raw_serializer.py bot.py ./

# Cloud Run injects PORT (defaults 8080). Run the plain WebSocket transport.
ENV PORT=8080
CMD ["sh", "-c", "uv run --no-sync python bot.py -t websocket --host 0.0.0.0 --port ${PORT:-8080}"]
