#!/usr/bin/env bash
# Tear down all billable infrastructure.
#
# Env: PROJECT_ID (required), REGION (default us-central1)
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-${HERE}/.env}"

if [[ -f "${ENV_FILE}" ]]; then set -a; source "${ENV_FILE}"; set +a; fi

export TF_VAR_project_id="${PROJECT_ID}"
export TF_VAR_region="${REGION}"
export TF_VAR_deepgram_api_key="${DEEPGRAM_API_KEY:-x}"
export TF_VAR_openai_api_key="${OPENAI_API_KEY:-x}"
export TF_VAR_cartesia_api_key="${CARTESIA_API_KEY:-x}"

terraform -chdir="${HERE}/infra" destroy -input=false -auto-approve
echo "==> All resources destroyed."
