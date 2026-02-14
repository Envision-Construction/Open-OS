#!/usr/bin/env bash
set -euo pipefail

# ─── Google OAuth Setup Helper ───────────────────────────────────────────────
# Creates OAuth 2.0 credentials for the `gog` skill (Gmail, Calendar, Drive)
# and stores them in Secret Manager.
#
# Prerequisites:
#   - GCP project with APIs enabled (run setup-gcp.sh first)
#   - OAuth consent screen configured in GCP Console
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ID="open-os-prod"
SCOPES="https://www.googleapis.com/auth/gmail.modify,https://www.googleapis.com/auth/calendar.events,https://www.googleapis.com/auth/drive.readonly,https://www.googleapis.com/auth/contacts.readonly"

echo "=== Google OAuth Setup for OpenClaw gog Skill ==="
echo ""
echo "This script helps configure OAuth 2.0 for Gmail, Calendar, Drive access."
echo ""

# ─── Step 1: Check for existing credentials ─────────────────────────────────
echo "Step 1: Checking for existing OAuth credentials..."
CLIENT_ID=$(gcloud secrets versions access latest --secret="google-oauth-client-id" --project="$PROJECT_ID" 2>/dev/null || echo "")
if [ -n "$CLIENT_ID" ]; then
  echo "  Found existing client ID: ${CLIENT_ID:0:20}..."
  read -rp "  Overwrite? (y/N): " overwrite
  if [[ "$overwrite" != "y" && "$overwrite" != "Y" ]]; then
    echo "  Keeping existing credentials."
    CLIENT_ID_SET=true
  else
    CLIENT_ID_SET=false
  fi
else
  CLIENT_ID_SET=false
fi

# ─── Step 2: Set OAuth client credentials ────────────────────────────────────
if [ "$CLIENT_ID_SET" = false ]; then
  echo ""
  echo "Step 2: Enter OAuth 2.0 credentials"
  echo "  Create at: https://console.cloud.google.com/apis/credentials?project=$PROJECT_ID"
  echo "  Type: Web application"
  echo "  Authorized redirect URI: http://localhost:8080/callback"
  echo ""

  read -rp "  Client ID: " NEW_CLIENT_ID
  read -rsp "  Client Secret: " NEW_CLIENT_SECRET
  echo ""

  echo -n "$NEW_CLIENT_ID" | gcloud secrets versions add google-oauth-client-id --data-file=- --project="$PROJECT_ID"
  echo -n "$NEW_CLIENT_SECRET" | gcloud secrets versions add google-oauth-client-secret --data-file=- --project="$PROJECT_ID"
  echo "  Stored in Secret Manager."
fi

# ─── Step 3: Generate refresh token ─────────────────────────────────────────
echo ""
echo "Step 3: Generate refresh token"
echo "  Required scopes:"
echo "    - gmail.modify"
echo "    - calendar.events"
echo "    - drive.readonly"
echo "    - contacts.readonly"
echo ""

FETCHED_CLIENT_ID=$(gcloud secrets versions access latest --secret="google-oauth-client-id" --project="$PROJECT_ID")
FETCHED_CLIENT_SECRET=$(gcloud secrets versions access latest --secret="google-oauth-client-secret" --project="$PROJECT_ID")

AUTH_URL="https://accounts.google.com/o/oauth2/v2/auth?client_id=${FETCHED_CLIENT_ID}&redirect_uri=http://localhost:8080/callback&response_type=code&scope=${SCOPES}&access_type=offline&prompt=consent"

echo "  Open this URL in your browser:"
echo ""
echo "  $AUTH_URL"
echo ""
read -rp "  Paste the authorization code: " AUTH_CODE

# Exchange code for tokens
echo "  Exchanging code for tokens..."
RESPONSE=$(curl -s -X POST "https://oauth2.googleapis.com/token" \
  -d "code=$AUTH_CODE" \
  -d "client_id=$FETCHED_CLIENT_ID" \
  -d "client_secret=$FETCHED_CLIENT_SECRET" \
  -d "redirect_uri=http://localhost:8080/callback" \
  -d "grant_type=authorization_code")

REFRESH_TOKEN=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('refresh_token',''))")

if [ -z "$REFRESH_TOKEN" ]; then
  echo "  ERROR: Failed to get refresh token. Response:"
  echo "  $RESPONSE"
  exit 1
fi

echo -n "$REFRESH_TOKEN" | gcloud secrets versions add google-oauth-refresh-tokens --data-file=- --project="$PROJECT_ID"
echo "  Refresh token stored in Secret Manager."

# ─── Step 4: Verify ─────────────────────────────────────────────────────────
echo ""
echo "Step 4: Verifying token..."
ACCESS_TOKEN=$(curl -s -X POST "https://oauth2.googleapis.com/token" \
  -d "refresh_token=$REFRESH_TOKEN" \
  -d "client_id=$FETCHED_CLIENT_ID" \
  -d "client_secret=$FETCHED_CLIENT_SECRET" \
  -d "grant_type=refresh_token" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

if [ -n "$ACCESS_TOKEN" ]; then
  USERINFO=$(curl -s -H "Authorization: Bearer $ACCESS_TOKEN" "https://www.googleapis.com/oauth2/v2/userinfo")
  EMAIL=$(echo "$USERINFO" | python3 -c "import sys,json; print(json.load(sys.stdin).get('email','unknown'))")
  echo "  Authenticated as: $EMAIL"
else
  echo "  WARNING: Could not verify token."
fi

echo ""
echo "=== OAuth setup complete ==="
echo "  Restart the OpenClaw pod to pick up new credentials."
