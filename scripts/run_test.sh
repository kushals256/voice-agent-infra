#!/usr/bin/env bash
# Run the burst latency test against the deployed service.
#
# Env: STEADY (default 10), BURST (default 10), TARGET (default 5.0)
#      WS_URL (optional; otherwise read from terraform output)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STEADY="${STEADY:-10}"
BURST="${BURST:-10}"
TARGET="${TARGET:-5.0}"

WS_URL="${WS_URL:-$(terraform -chdir="${HERE}/infra" output -raw ws_client_url)}"
echo "==> Testing ${WS_URL} (steady=${STEADY}, burst=${BURST}, target=${TARGET}s)"

cd "${HERE}/harness"
python3 harness.py "${WS_URL}" --steady "${STEADY}" --burst "${BURST}" --target "${TARGET}"
