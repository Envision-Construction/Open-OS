#!/usr/bin/env bash
# Recreate branding ConfigMaps from assets/ directory.
# Usage: ./scripts/update-branding.sh [--dry-run]

set -euo pipefail

NAMESPACE="open-os"
ASSETS_DIR="$(cd "$(dirname "$0")/../assets" && pwd)"
DRY_RUN=""

if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN="--dry-run=client"
  echo "[dry-run] Will show what would be applied without changing the cluster."
fi

echo "Updating branding ConfigMaps from: $ASSETS_DIR"

kubectl create configmap branding-logo \
  --from-file=logo.png="$ASSETS_DIR/logo.png" \
  -n "$NAMESPACE" $DRY_RUN -o yaml --dry-run=client | kubectl apply -f - $DRY_RUN

kubectl create configmap branding-favicon \
  --from-file=favicon.png="$ASSETS_DIR/favicon.png" \
  --from-file=favicon.ico="$ASSETS_DIR/favicon.ico" \
  --from-file=favicon-96x96.png="$ASSETS_DIR/favicon-96x96.png" \
  --from-file=apple-touch-icon.png="$ASSETS_DIR/apple-touch-icon.png" \
  -n "$NAMESPACE" $DRY_RUN -o yaml --dry-run=client | kubectl apply -f - $DRY_RUN

kubectl create configmap branding-background \
  --from-file=background.jpg="$ASSETS_DIR/background.jpg" \
  -n "$NAMESPACE" $DRY_RUN -o yaml --dry-run=client | kubectl apply -f - $DRY_RUN

kubectl create configmap branding-splash \
  --from-file=splash.png="$ASSETS_DIR/splash.png" \
  -n "$NAMESPACE" $DRY_RUN -o yaml --dry-run=client | kubectl apply -f - $DRY_RUN

kubectl create configmap branding-splash-dark \
  --from-file=splash-dark.png="$ASSETS_DIR/splash-dark.png" \
  -n "$NAMESPACE" $DRY_RUN -o yaml --dry-run=client | kubectl apply -f - $DRY_RUN

kubectl create configmap branding-css \
  --from-file=custom.css="$ASSETS_DIR/custom.css" \
  -n "$NAMESPACE" $DRY_RUN -o yaml --dry-run=client | kubectl apply -f - $DRY_RUN

kubectl create configmap branding-onboarding-js \
  --from-file=onboarding.js="$ASSETS_DIR/onboarding.js" \
  -n "$NAMESPACE" $DRY_RUN -o yaml --dry-run=client | kubectl apply -f - $DRY_RUN

echo "Done. Restart the open-webui pod to pick up changes:"
echo "  kubectl rollout restart deployment/open-webui -n $NAMESPACE"
