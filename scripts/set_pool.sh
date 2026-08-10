#!/usr/bin/env bash
# Set the warm spare pool (Cloud Run min-instances) without a full Terraform run.
# Handy to warm up right before the test and cool down right after.
#
#   scripts/set_pool.sh 20   # warm 20 spares for the burst test
#   scripts/set_pool.sh 0    # scale to zero (stop paying)
#
# Env: PROJECT_ID (required), REGION (default us-central1), SERVICE (default voicebot)
set -euo pipefail

MIN="${1:?usage: set_pool.sh <min-instances>}"
PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-voicebot}"

echo "==> Setting ${SERVICE} min-instances=${MIN} in ${REGION}"
gcloud run services update "${SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --min-instances "${MIN}" \
  --quiet

echo "==> Done. Current config:"
gcloud run services describe "${SERVICE}" \
  --project "${PROJECT_ID}" --region "${REGION}" \
  --format="value(spec.template.metadata.annotations['autoscaling.knative.dev/minScale'])" || true
