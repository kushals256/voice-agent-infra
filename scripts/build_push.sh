#!/usr/bin/env bash
# Build the bot image and push to Artifact Registry.
# Default PLATFORM=linux/arm64 (native on Apple Silicon, supported by Cloud Run).
# Override with PLATFORM=linux/amd64 if needed.
#
# Requires: gcloud (authenticated), docker with buildx.
# Env:
#   PROJECT_ID  (required)  GCP project id
#   REGION      (default us-central1)
#   REPO_ID     (default bots)
#   IMAGE_TAG   (default latest)
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
REPO_ID="${REPO_ID:-bots}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
PLATFORM="${PLATFORM:-linux/arm64}"

IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_ID}/bot:${IMAGE_TAG}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Configuring docker auth for ${REGION}-docker.pkg.dev"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

echo "==> Building ${IMAGE} (${PLATFORM})"
docker buildx build \
  --platform "${PLATFORM}" \
  -t "${IMAGE}" \
  --push \
  "${HERE}/bot"

echo "==> Pushed ${IMAGE}"
