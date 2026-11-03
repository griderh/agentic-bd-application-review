#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
runner="$repo_root/.venv/bin/bd-packet"

if [[ ! -x "$runner" ]]; then
  printf '%s\n' "Missing $runner. Follow the local setup instructions in README.md first." >&2
  exit 1
fi

exec "$runner" broward-demo \
  --root "$repo_root" \
  --endpoint "${BD_FOUNDRY_ENDPOINT:-https://bd-application-builder-resource.openai.azure.com/openai/v1}" \
  --deployment "${BD_FOUNDRY_DEPLOYMENT:-gpt-6.1-sol}" \
  --request-timeout-seconds "${BD_REQUEST_TIMEOUT_SECONDS:-180}" \
  --allow-paid \
  "$@"
