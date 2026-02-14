#!/usr/bin/env bash
set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────
PROJECT_ID="open-os-prod"
REGION="us-central1"
CLUSTER_NAME="openclaw-cluster"
VPC_NAME="openclaw-vpc"
SUBNET_NAME="openclaw-subnet"
SUBNET_RANGE="10.10.0.0/24"
POD_RANGE="10.11.0.0/16"
SERVICE_RANGE="10.12.0.0/20"
SA_NAME="openclaw-sa"
KSA_NAME="openclaw-ksa"
NAMESPACE="openclaw"
NAT_ROUTER="openclaw-router"
NAT_NAME="openclaw-nat"

echo "=== OpenClaw GCP Infrastructure Setup ==="
echo "Project: $PROJECT_ID | Region: $REGION"
echo ""

# ─── Set project ─────────────────────────────────────────────────────────────
gcloud config set project "$PROJECT_ID"

# ─── Enable APIs ─────────────────────────────────────────────────────────────
echo ">>> Enabling GCP APIs..."
gcloud services enable \
  container.googleapis.com \
  dlp.googleapis.com \
  secretmanager.googleapis.com \
  iap.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  artifactregistry.googleapis.com \
  compute.googleapis.com

# ─── VPC & Subnet ────────────────────────────────────────────────────────────
echo ">>> Creating VPC and subnet..."
gcloud compute networks create "$VPC_NAME" \
  --subnet-mode=custom \
  --project="$PROJECT_ID" \
  2>/dev/null || echo "VPC already exists"

gcloud compute networks subnets create "$SUBNET_NAME" \
  --network="$VPC_NAME" \
  --region="$REGION" \
  --range="$SUBNET_RANGE" \
  --secondary-range="pods=$POD_RANGE,services=$SERVICE_RANGE" \
  --enable-private-ip-google-access \
  2>/dev/null || echo "Subnet already exists"

# ─── Cloud NAT (outbound-only internet) ─────────────────────────────────────
echo ">>> Creating Cloud NAT..."
gcloud compute routers create "$NAT_ROUTER" \
  --network="$VPC_NAME" \
  --region="$REGION" \
  2>/dev/null || echo "Router already exists"

gcloud compute routers nats create "$NAT_NAME" \
  --router="$NAT_ROUTER" \
  --region="$REGION" \
  --auto-allocate-nat-external-ips \
  --nat-all-subnet-ip-ranges \
  2>/dev/null || echo "NAT already exists"

# ─── GKE Autopilot Cluster ──────────────────────────────────────────────────
echo ">>> Creating GKE Autopilot cluster..."
gcloud container clusters create-auto "$CLUSTER_NAME" \
  --region="$REGION" \
  --network="$VPC_NAME" \
  --subnetwork="$SUBNET_NAME" \
  --cluster-secondary-range-name="pods" \
  --services-secondary-range-name="services" \
  --enable-private-nodes \
  --enable-master-authorized-networks \
  --master-authorized-networks="0.0.0.0/0" \
  --workload-pool="$PROJECT_ID.svc.id.goog" \
  --security-posture=standard \
  --workload-vulnerability-scanning=standard \
  2>/dev/null || echo "Cluster already exists"

# Get cluster credentials
gcloud container clusters get-credentials "$CLUSTER_NAME" \
  --region="$REGION" \
  --project="$PROJECT_ID"

# ─── GCP Service Account ────────────────────────────────────────────────────
echo ">>> Creating GCP service account..."
gcloud iam service-accounts create "$SA_NAME" \
  --display-name="OpenClaw Workload Identity SA" \
  2>/dev/null || echo "SA already exists"

SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

# Grant roles
declare -a ROLES=(
  "roles/dlp.user"
  "roles/secretmanager.secretAccessor"
  "roles/logging.logWriter"
  "roles/monitoring.metricWriter"
)

for role in "${ROLES[@]}"; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="$role" \
    --condition=None \
    --quiet
done

# ─── Workload Identity Binding ───────────────────────────────────────────────
echo ">>> Configuring Workload Identity..."
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:$PROJECT_ID.svc.id.goog[$NAMESPACE/$KSA_NAME]" \
  --quiet

# ─── Secret Manager Secrets ─────────────────────────────────────────────────
echo ">>> Creating Secret Manager secrets (empty — populate manually)..."
declare -a SECRETS=(
  "anthropic-api-key"
  "openclaw-gateway-token"
  "google-oauth-client-id"
  "google-oauth-client-secret"
  "google-oauth-refresh-tokens"
  "slack-bot-token"
  "slack-app-token"
  "open-webui-secret-key"
  "open-webui-oauth-client-secret"
)

for secret in "${SECRETS[@]}"; do
  gcloud secrets create "$secret" --replication-policy="automatic" \
    2>/dev/null || echo "Secret $secret already exists"
done

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Populate secrets:  gcloud secrets versions add <name> --data-file=<file>"
echo "  2. Deploy k8s:        kubectl apply -f k8s/"
echo "  3. Run OAuth setup:   ./scripts/setup-oauth.sh"
