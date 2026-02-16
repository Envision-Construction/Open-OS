# Open-OS

Personal AI operating system powered by [OpenClaw](https://github.com/open-webui/open-webui) + [Open Web UI](https://github.com/open-webui/open-webui) on GCP.

## Architecture

```
Internet → Cloud LB + IAP → Open Web UI → DLP Proxy → OpenClaw Gateway → LLM APIs
                                                          ↕
                                                    Skills/Integrations
                                                    (Gmail, Calendar, Drive,
                                                     Slack, WhatsApp)
```

### Components

| Component | Role | Image |
|-----------|------|-------|
| **OpenClaw** | AI gateway — routes to LLM providers, manages tools/skills | StatefulSet + 20Gi PVC |
| **Open Web UI** | Chat UI — conversations, RAG, user management | Deployment + 5Gi PVC |
| **DLP Proxy** | PII inspection/redaction via GCP Sensitive Data Protection | Deployment (read-only FS) |

### Infrastructure

- **GKE Autopilot** in `us-central1` with private nodes
- **VPC** with Cloud NAT for egress
- **IAP** zero-trust access (Google identity required)
- **Secret Manager** + External Secrets Operator for credential management
- **Workload Identity** — no service account keys on cluster
- **Network Policies** — strict pod-to-pod firewall

### LLM Configuration

| Model | Use Case |
|-------|----------|
| Claude Sonnet 4.5 | Default — fast, capable |
| Claude Opus 4.6 | Complex reasoning tasks |
| OpenAI (optional) | Fallback / comparison |
| Google AI (optional) | Gemini models |

## Quick Start (Local Dev)

```bash
# 1. Clone
git clone https://github.com/avireddy0/Open-OS.git
cd Open-OS

# 2. Set environment
cp .env.example .env  # Edit with your API keys

# 3. Run
docker compose up -d

# 4. Open
open http://localhost:3000
```

## GCP Deployment

### Prerequisites

- GCP project (`open-os-prod`)
- `gcloud` CLI authenticated
- Domain with DNS access (for TLS + IAP)

### Setup

```bash
# 1. Provision infrastructure (VPC, GKE, secrets, IAM)
chmod +x scripts/setup-gcp.sh
./scripts/setup-gcp.sh

# 2. Configure OAuth for Google integrations
chmod +x scripts/setup-oauth.sh
./scripts/setup-oauth.sh

# 3. Connect to cluster
gcloud container clusters get-credentials openclaw-cluster \
  --region us-central1 --project open-os-prod

# 4. Install External Secrets Operator
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets \
  -n external-secrets --create-namespace

# 5. Bootstrap Docker Hub secrets (one-time)
DOCKERHUB_USERNAME='your-user' DOCKERHUB_TOKEN='your-token' \
  ./scripts/bootstrap-dockerhub-gcp-secrets.sh open-os-prod

# 6. Build once, then mirror to both Artifact Registry + Docker Hub
gcloud services enable cloudbuild.googleapis.com --project open-os-prod
gcloud builds submit --project open-os-prod --config cloudbuild.yaml .

# 7. Deploy to GKE
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/secrets-external.yaml
kubectl apply -f k8s/openclaw-statefulset.yaml
kubectl apply -f k8s/dlp-proxy-deployment.yaml
kubectl apply -f k8s/open-webui-deployment.yaml
kubectl apply -f k8s/services.yaml
kubectl apply -f k8s/network-policies.yaml

# 8. Set up ingress (after DNS is configured)
kubectl apply -f k8s/ingress.yaml
```

### Docker Hub Sync

- `cloudbuild.yaml` builds `dlp-proxy` once and pushes:
  - `us-central1-docker.pkg.dev/open-os-prod/openclaw-registry/dlp-proxy:{SHORT_SHA,latest}`
  - `docker.io/<dockerhub-username>/open-os-dlp-proxy:{SHORT_SHA,latest}`
- `.github/workflows/dockerhub-sync.yml` keeps Docker Hub updated on every push to `main`.
  - Configure GitHub repo secrets: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`.
- `k8s/dlp-proxy-deployment.yaml` pulls from Docker Hub (`docker.io/avireddy0/open-os-dlp-proxy:latest`).
- Verify sync wiring anytime:

```bash
./scripts/verify-dockerhub-gcp-sync.sh open-os-prod
```

### DNS Setup

1. Get the static IP: `gcloud compute addresses describe openclaw-ip --global --format='value(address)'`
2. Create an A record for your domain pointing to that IP
3. Wait for certificate provisioning (~15 min)

## Security

- **IAP**: All web traffic requires Google identity authentication
- **DLP**: User inputs and AI responses are scanned for PII (SSN, credit cards, emails, etc.)
- **Network Policies**: Strict pod-to-pod isolation — Open Web UI → DLP Proxy → OpenClaw only
- **Pod Security**: Restricted PSS, non-root containers, dropped capabilities
- **Secrets**: Stored in GCP Secret Manager, synced via Workload Identity (no keys on disk)
- **Private Nodes**: GKE nodes have no public IPs — egress via Cloud NAT only

## Integrations

| Integration | Protocol | Status |
|-------------|----------|--------|
| Gmail | OAuth 2.0 (gog skill) | Planned |
| Google Calendar | OAuth 2.0 (gog skill) | Planned |
| Google Drive | OAuth 2.0 (gog skill) | Planned |
| Slack | Socket Mode | Planned |
| WhatsApp | Baileys (unofficial) | Planned |

## Cost Estimate

| Component | Monthly Cost |
|-----------|-------------|
| GKE Autopilot (3 pods) | ~$30-40 |
| Cloud NAT | ~$5 |
| Persistent Disks (25 Gi) | ~$3 |
| Secret Manager | ~$1 |
| Load Balancer + IAP | ~$18 |
| DLP API (inspections) | ~$1-5 |
| **Total (excl. LLM API)** | **~$55-80** |

## File Structure

```
Open-OS/
├── dlp-proxy/
│   ├── main.py              # FastAPI DLP inspection proxy
│   └── Dockerfile
├── k8s/
│   ├── namespace.yaml        # Namespace + PSS labels
│   ├── openclaw-statefulset.yaml
│   ├── open-webui-deployment.yaml
│   ├── dlp-proxy-deployment.yaml
│   ├── services.yaml         # ClusterIP services
│   ├── ingress.yaml          # LB + IAP + TLS
│   ├── network-policies.yaml # Pod firewall rules
│   └── secrets-external.yaml # ExternalSecret CRDs
├── scripts/
│   ├── setup-gcp.sh          # Infrastructure provisioning
│   ├── setup-oauth.sh        # OAuth credential setup
│   ├── bootstrap-dockerhub-gcp-secrets.sh
│   └── verify-dockerhub-gcp-sync.sh
├── cloudbuild.yaml           # Build once -> push to AR + mirror to Docker Hub
├── docker-compose.yml        # Local development
└── README.md
```

## License

MIT
