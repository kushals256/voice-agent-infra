#!/usr/bin/env bash
# Deploy (or update) the Cloud Run service via Terraform.
#
# Reads API keys from a .env file at the repo root (KEY=VALUE lines) and passes
# them to Terraform as TF_VAR_* so nothing is committed.
#
# Env:
#   PROJECT_ID     (required)
#   REGION         (default us-central1)
#   MIN_INSTANCES  (default 0)   warm spare pool floor
#   MAX_INSTANCES  (default 25)
#   IMAGE_TAG      (default latest)
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
MIN_INSTANCES="${MIN_INSTANCES:-0}"
MAX_INSTANCES="${MAX_INSTANCES:-25}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-${HERE}/.env}"

if [[ -f "${ENV_FILE}" ]]; then
  echo "==> Loading API keys from ${ENV_FILE}"
  set -a; source "${ENV_FILE}"; set +a
fi

: "${DEEPGRAM_API_KEY:?missing DEEPGRAM_API_KEY (put it in .env)}"

export TF_VAR_project_id="${PROJECT_ID}"
export TF_VAR_region="${REGION}"
export TF_VAR_min_instances="${MIN_INSTANCES}"
export TF_VAR_max_instances="${MAX_INSTANCES}"
export TF_VAR_image_tag="${IMAGE_TAG}"
export TF_VAR_deepgram_api_key="${DEEPGRAM_API_KEY}"
export TF_VAR_openai_api_key="${OPENAI_API_KEY:-unused}"
export TF_VAR_groq_api_key="${GROQ_API_KEY:-}"
export TF_VAR_nvidia_api_key="${NVIDIA_API_KEY:-}"

terraform -chdir="${HERE}/infra" init -input=false
terraform -chdir="${HERE}/infra" apply -input=false -auto-approve

echo
echo "==> WebSocket URL for the harness:"
terraform -chdir="${HERE}/infra" output -raw ws_client_url
echo
