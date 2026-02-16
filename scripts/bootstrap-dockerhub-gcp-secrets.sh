#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${1:-open-os-prod}"

if [[ -z "${DOCKERHUB_USERNAME:-}" || -z "${DOCKERHUB_TOKEN:-}" ]]; then
  echo "Set DOCKERHUB_USERNAME and DOCKERHUB_TOKEN before running." >&2
  echo "Example:" >&2
  echo "  DOCKERHUB_USERNAME=your-user DOCKERHUB_TOKEN=your-token \\" >&2
  echo "    ./scripts/bootstrap-dockerhub-gcp-secrets.sh open-os-prod" >&2
  exit 1
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI is required." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker CLI is required." >&2
  exit 1
fi

tmp_docker_cfg="$(mktemp -d)"
trap 'rm -rf "$tmp_docker_cfg"' EXIT
if ! printf "%s" "$DOCKERHUB_TOKEN" | DOCKER_CONFIG="$tmp_docker_cfg" docker login --username "$DOCKERHUB_USERNAME" --password-stdin >/dev/null 2>&1; then
  echo "Docker Hub credentials are invalid." >&2
  exit 1
fi
DOCKER_CONFIG="$tmp_docker_cfg" docker logout >/dev/null 2>&1 || true

ensure_secret() {
  local secret="$1"
  if ! gcloud secrets describe "$secret" --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud secrets create "$secret" --replication-policy=automatic --project "$PROJECT_ID" >/dev/null
    echo "created secret: $secret"
  fi
}

ensure_secret "dockerhub-username"
ensure_secret "dockerhub-token"

printf "%s" "$DOCKERHUB_USERNAME" | gcloud secrets versions add dockerhub-username --project "$PROJECT_ID" --data-file=- >/dev/null
printf "%s" "$DOCKERHUB_TOKEN" | gcloud secrets versions add dockerhub-token --project "$PROJECT_ID" --data-file=- >/dev/null

project_number="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
cloudbuild_sa="${project_number}@cloudbuild.gserviceaccount.com"
compute_sa="${project_number}-compute@developer.gserviceaccount.com"

for secret in dockerhub-username dockerhub-token; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --project "$PROJECT_ID" \
    --member "serviceAccount:${cloudbuild_sa}" \
    --role "roles/secretmanager.secretAccessor" >/dev/null 2>&1 || true
  gcloud secrets add-iam-policy-binding "$secret" \
    --project "$PROJECT_ID" \
    --member "serviceAccount:${compute_sa}" \
    --role "roles/secretmanager.secretAccessor" >/dev/null 2>&1 || true
done

echo "Docker Hub secrets updated in ${PROJECT_ID}."
