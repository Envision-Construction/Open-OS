#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${1:-open-os-prod}"
status=0

ok() {
  echo "OK: $*"
}

warn() {
  echo "WARN: $*" >&2
  status=1
}

if gcloud services list --enabled --project "$PROJECT_ID" --format='value(config.name)' | rg -q '^cloudbuild\.googleapis\.com$'; then
  ok "cloudbuild.googleapis.com enabled in ${PROJECT_ID}"
else
  warn "cloudbuild.googleapis.com is not enabled in ${PROJECT_ID}"
fi

for secret in dockerhub-username dockerhub-token; do
  if gcloud secrets describe "$secret" --project "$PROJECT_ID" >/dev/null 2>&1; then
    ok "${secret} exists in ${PROJECT_ID}"
  else
    warn "${secret} missing in ${PROJECT_ID}"
  fi
done

if rg -q "mirror-to-dockerhub" /Users/avireddy/GitHub/Open-OS/cloudbuild.yaml; then
  ok "cloudbuild.yaml contains Docker Hub mirror step"
else
  warn "cloudbuild.yaml missing Docker Hub mirror step"
fi

if rg -q "docker.io/avireddy0/open-os-dlp-proxy:latest" /Users/avireddy/GitHub/Open-OS/k8s/dlp-proxy-deployment.yaml; then
  ok "k8s dlp-proxy image points to Docker Hub"
else
  warn "k8s dlp-proxy image does not point to Docker Hub"
fi

if [[ -f /Users/avireddy/GitHub/Open-OS/.github/workflows/dockerhub-sync.yml ]]; then
  ok "GitHub Actions Docker Hub sync workflow exists"
else
  warn "GitHub Actions Docker Hub sync workflow is missing"
fi

exit "$status"
