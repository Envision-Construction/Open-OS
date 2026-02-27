"""DLP Proxy — FastAPI service that inspects/redacts PII via GCP Sensitive Data Protection.

Sits between Open Web UI and OpenClaw Gateway. Inspects user prompts on the way in
and assistant responses on the way out. Redacts or blocks sensitive content.

Also serves as the OAuth 2.0 callback handler for Google integrations.
Users connect their Google account via /oauth/start → consent → /oauth/callback.
Tokens are stored per-user in /data/tokens/.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import secrets as secrets_mod
import stat
import time
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from google.cloud import dlp_v2

# ─── Configuration ────────────────────────────────────────────────────────────
OPENCLAW_UPSTREAM = os.getenv("OPENCLAW_UPSTREAM", "http://openclaw:11434")
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "open-os-prod")
DLP_MIN_LIKELIHOOD = os.getenv("DLP_MIN_LIKELIHOOD", "LIKELY")
BLOCK_ON_FINDING = os.getenv("BLOCK_ON_FINDING", "true").lower() != "false"
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "").strip()
REDACT_ASSISTANT_OUTPUT = (
    os.getenv("REDACT_ASSISTANT_OUTPUT", "false").lower() == "true"
)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# OAuth 2.0 config — Google
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
OAUTH_REDIRECT_URI = os.getenv(
    "OAUTH_REDIRECT_URI", "https://os.envsn.com/oauth/callback"
)
GOOGLE_SCOPES = "openid email profile https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/drive"

# OAuth 2.0 config — Slack (personal user token, not workspace bot)
SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID", "")
SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET", "")
SLACK_OAUTH_REDIRECT_URI = os.getenv("SLACK_OAUTH_REDIRECT_URI", OAUTH_REDIRECT_URI)
SLACK_USER_SCOPES = os.getenv(
    "SLACK_USER_SCOPES",
    "channels:read,channels:history,chat:write,users:read,files:read",
)

# WhatsApp — Evolution API
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://evolution-api:8080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")

TOKEN_STORE_DIR = Path(os.getenv("TOKEN_STORE_DIR", "/data/tokens"))
TOKEN_STORE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=getattr(logging, LOG_LEVEL))
logger = logging.getLogger("dlp-proxy")

app = FastAPI(title="DLP Proxy", version="1.0.0")
dlp_client = dlp_v2.DlpServiceClient()
http_client = httpx.AsyncClient(base_url=OPENCLAW_UPSTREAM, timeout=120.0)

# InfoTypes to scan for
INFO_TYPES = [
    {"name": "PERSON_NAME"},
    {"name": "EMAIL_ADDRESS"},
    {"name": "PHONE_NUMBER"},
    {"name": "CREDIT_CARD_NUMBER"},
    {"name": "US_SOCIAL_SECURITY_NUMBER"},
    {"name": "STREET_ADDRESS"},
    {"name": "DATE_OF_BIRTH"},
    {"name": "IP_ADDRESS"},
    {"name": "PASSPORT"},
    {"name": "US_DRIVERS_LICENSE_NUMBER"},
]

INSPECT_CONFIG = {
    "info_types": INFO_TYPES,
    "min_likelihood": getattr(
        dlp_v2.Likelihood, DLP_MIN_LIKELIHOOD, dlp_v2.Likelihood.LIKELY
    ),
    "include_quote": True,
    "limits": {"max_findings_per_request": 20},
}

# deidentify_content does not support limits.max_findings_per_request
INSPECT_CONFIG_DEIDENTIFY = {
    "info_types": INFO_TYPES,
    "min_likelihood": getattr(
        dlp_v2.Likelihood, DLP_MIN_LIKELIHOOD, dlp_v2.Likelihood.LIKELY
    ),
    "include_quote": True,
}

DEIDENTIFY_CONFIG = {
    "info_type_transformations": {
        "transformations": [
            {
                "primitive_transformation": {
                    "replace_config": {
                        "new_value": {"string_value": "[REDACTED]"},
                    },
                },
            },
        ],
    },
}


def inspect_content(text: str) -> list[dict[str, Any]]:
    """Inspect text for PII using DLP API. Returns list of findings."""
    if not text or not text.strip():
        return []

    parent = f"projects/{GCP_PROJECT_ID}/locations/global"
    item = {"value": text}

    try:
        response = dlp_client.inspect_content(
            request={
                "parent": parent,
                "inspect_config": INSPECT_CONFIG,
                "item": item,
            }
        )
        findings = []
        for finding in response.result.findings:
            findings.append(
                {
                    "info_type": finding.info_type.name,
                    "likelihood": dlp_v2.Likelihood(finding.likelihood).name,
                    "quote": finding.quote,
                }
            )
        return findings
    except Exception:
        logger.critical("DLP inspect_content FAILED — content passing through UNINSPECTED")
        return []


def redact_content(text: str) -> str:
    """Redact PII from text using DLP API."""
    if not text or not text.strip():
        return text

    parent = f"projects/{GCP_PROJECT_ID}/locations/global"
    item = {"value": text}

    try:
        response = dlp_client.deidentify_content(
            request={
                "parent": parent,
                "deidentify_config": DEIDENTIFY_CONFIG,
                "inspect_config": INSPECT_CONFIG_DEIDENTIFY,
                "item": item,
            }
        )
        return response.item.value
    except Exception:
        logger.critical("DLP redact_content FAILED — content passing through UNINSPECTED")
        return text


def _extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text", ""))
        return "\n".join(parts)
    return ""


def extract_latest_user_text(body: dict) -> str:
    """Extract only the latest user message text from an OpenAI-format request."""
    messages = body.get("messages", [])
    if not isinstance(messages, list):
        return ""
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "user":
            continue
        return _extract_text_from_content(msg.get("content", ""))
    return ""


def redact_latest_user_message(body: dict) -> None:
    """Redact only the latest user message in-place."""
    messages = body.get("messages", [])
    if not isinstance(messages, list):
        return
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            msg["content"] = redact_content(content)
            return
        if isinstance(content, list):
            new_parts = []
            for part in content:
                if (
                    isinstance(part, dict)
                    and part.get("type") == "text"
                    and isinstance(part.get("text"), str)
                ):
                    new_part = dict(part)
                    new_part["text"] = redact_content(part.get("text", ""))
                    new_parts.append(new_part)
                else:
                    new_parts.append(part)
            msg["content"] = new_parts
            return
        return


# ─── OAuth 2.0 Token Store Helpers ─────────────────────────────────────────────

ALLOWED_PROVIDERS = {"google", "slack", "whatsapp"}


def _token_path(user_id: str, provider: str = "google") -> Path:
    if provider not in ALLOWED_PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")
    safe_id = hashlib.sha256(user_id.encode()).hexdigest()[:16]
    if provider == "google":
        # Backward compat: google tokens use the original filename
        return TOKEN_STORE_DIR / f"{safe_id}.json"
    return TOKEN_STORE_DIR / f"{safe_id}_{provider}.json"


def load_user_tokens(user_id: str, provider: str = "google") -> dict | None:
    path = _token_path(user_id, provider)
    if path.exists():
        return json.loads(path.read_text())
    return None


def save_user_tokens(user_id: str, tokens: dict, provider: str = "google") -> None:
    tokens["updated_at"] = time.time()
    tokens["user_id"] = user_id
    tokens["provider"] = provider
    path = _token_path(user_id, provider)
    path.write_text(json.dumps(tokens, indent=2))
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600


def delete_user_tokens(user_id: str, provider: str = "google") -> bool:
    """Delete persisted OAuth tokens for a user/provider. Returns True if removed."""
    safe_id = hashlib.sha256(user_id.encode()).hexdigest()[:16]
    paths: list[Path] = [_token_path(user_id, provider)]
    if provider == "google":
        # Backward compatibility in case any older filename variant exists.
        paths.append(TOKEN_STORE_DIR / f"{safe_id}_google.json")

    removed = False
    for path in paths:
        if path.exists():
            path.unlink(missing_ok=True)
            removed = True
    return removed


# ─── OAuth 2.0 Routes ─────────────────────────────────────────────────────────


def _create_state(user_id: str, provider: str) -> str:
    state = hashlib.sha256(f"{user_id}:{provider}:{time.time()}".encode()).hexdigest()[:32]
    state_path = TOKEN_STORE_DIR / f"state_{state}.json"
    state_path.write_text(
        json.dumps({"user_id": user_id, "provider": provider, "created": time.time()})
    )
    return state


@app.get("/oauth/start")
async def oauth_start(user_id: str = "default", provider: str = "google"):
    # ── Slack OAuth (personal user token) ────────────────────────────
    if provider == "slack":
        if not SLACK_CLIENT_ID:
            raise HTTPException(status_code=500, detail="SLACK_CLIENT_ID not configured")
        state = _create_state(user_id, "slack")
        params = urllib.parse.urlencode(
            {
                "client_id": SLACK_CLIENT_ID,
                "redirect_uri": SLACK_OAUTH_REDIRECT_URI,
                "user_scope": SLACK_USER_SCOPES,
                "state": state,
            }
        )
        return RedirectResponse(f"https://slack.com/oauth/v2/authorize?{params}")

    # ── WhatsApp via Evolution API ────────────────────────────────────
    if provider == "whatsapp":
        return await _whatsapp_connect(user_id)

    # ── Google OAuth (default) ────────────────────────────────────────
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID not configured")
    state = _create_state(user_id, "google")
    params = urllib.parse.urlencode(
        {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope": GOOGLE_SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    )
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


_SUCCESS_HTML = """
<html>
<head><style>
    body {{ background: #1a1a2e; color: #e0e0e0; font-family: -apple-system, sans-serif;
           display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
    .card {{ text-align: center; padding: 3rem; border-radius: 16px;
            background: rgba(255,255,255,0.05); backdrop-filter: blur(10px); }}
    h2 {{ color: #4ade80; margin-bottom: 0.5rem; }}
    p {{ color: #9ca3af; }}
</style></head>
<body><div class="card">
    <h2>{title}</h2>
    <p>You can close this tab and return to your chat.</p>
    <p style="margin-top:2rem;font-size:0.85rem;color:#6b7280;">{detail}</p>
</div></body></html>
"""


@app.get("/oauth/callback")
async def oauth_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return HTMLResponse(
            f"<h2>Authorization failed</h2><p>{error}</p>", status_code=400
        )

    if not code or not state:
        return HTMLResponse("<h2>Missing code or state</h2>", status_code=400)

    state_path = TOKEN_STORE_DIR / f"state_{state}.json"
    if not state_path.exists():
        return HTMLResponse("<h2>Invalid or expired state</h2>", status_code=400)

    state_data = json.loads(state_path.read_text())
    state_path.unlink(missing_ok=True)

    MAX_STATE_AGE = 600  # 10 minutes
    if time.time() - state_data.get("created", 0) > MAX_STATE_AGE:
        return HTMLResponse("<h2>OAuth state expired. Please restart.</h2>", status_code=400)

    user_id = state_data.get("user_id", "default")
    provider = state_data.get("provider", "google")

    # ── Slack token exchange (personal user token) ─────────────────────
    if provider == "slack":
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://slack.com/api/oauth.v2.access",
                data={
                    "code": code,
                    "client_id": SLACK_CLIENT_ID,
                    "client_secret": SLACK_CLIENT_SECRET,
                    "redirect_uri": SLACK_OAUTH_REDIRECT_URI,
                },
            )

        if resp.status_code != 200:
            logger.error("Slack token exchange HTTP error: %s", resp.text)
            return HTMLResponse("<h2>Slack token exchange failed</h2>", status_code=500)

        data = resp.json()
        if not data.get("ok"):
            logger.error("Slack token exchange error: %s", data.get("error"))
            return HTMLResponse(
                f"<h2>Slack authorization failed</h2><p>{data.get('error')}</p>",
                status_code=400,
            )

        # Personal connection: user token is the primary token
        authed_user = data.get("authed_user", {})
        user_token = authed_user.get("access_token", "")
        save_user_tokens(
            user_id,
            {
                "access_token": user_token,
                "bot_token": user_token,
                "user_token": user_token,
                "team_id": data.get("team", {}).get("id", ""),
                "team_name": data.get("team", {}).get("name", ""),
                "scope": authed_user.get("scope", ""),
                "user_scope": authed_user.get("scope", ""),
            },
            provider="slack",
        )
        logger.info("Slack user token saved for user_id=%s", user_id)
        return HTMLResponse(
            _SUCCESS_HTML.format(
                title="Slack Connected",
                detail="Your personal Slack account is now linked.",
            )
        )

    # ── Google token exchange (default) ───────────────────────────────
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": OAUTH_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )

    if resp.status_code != 200:
        logger.error("Token exchange failed: %s", resp.text)
        return HTMLResponse("<h2>Token exchange failed. Please try again.</h2>", status_code=500)

    tokens = resp.json()
    save_user_tokens(
        user_id,
        {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "token_type": tokens.get("token_type"),
            "expires_in": tokens.get("expires_in"),
            "scope": tokens.get("scope"),
        },
    )

    logger.info("OAuth tokens saved for user_id=%s", user_id)
    return HTMLResponse(
        _SUCCESS_HTML.format(
            title="Google Account Connected",
            detail="Your Gmail, Calendar, and Drive tools are now active.",
        )
    )


@app.get("/oauth/tokens/{user_id}")
async def get_tokens(user_id: str, provider: str = "google", instance: str = "", x_internal_key: str = Header(default="")):
    if INTERNAL_API_KEY and not secrets_mod.compare_digest(x_internal_key, INTERNAL_API_KEY):
        raise HTTPException(status_code=403, detail="Forbidden")


    # ── WhatsApp: check Evolution API instance ────────────────────────
    if provider == "whatsapp":
        return await _whatsapp_check(user_id, instance=instance)

    tokens = load_user_tokens(user_id, provider)
    if not tokens:
        raise HTTPException(status_code=404, detail="No tokens for this user")
    return {
        "connected": True,
        "scope": tokens.get("scope", ""),
        "has_refresh_token": bool(tokens.get("refresh_token")),
    }


@app.get("/oauth/tokens/{user_id}/full")
async def get_full_tokens(user_id: str, provider: str = "google", x_internal_key: str = Header(default="")):
    """Return full token payload for tool use (called by Open WebUI tools)."""
    if INTERNAL_API_KEY and not secrets_mod.compare_digest(x_internal_key, INTERNAL_API_KEY):
        raise HTTPException(status_code=403, detail="Forbidden")

    if provider == "whatsapp":
        # Only expose runtime config when the instance is actually connected.
        await _whatsapp_check(user_id)
        # Return Evolution API config so the WhatsApp tool can call Evolution directly
        instance_name = _wa_instance_name(user_id)
        return {
            "connected": True,
            "provider": "whatsapp",
            "evolution_api_url": EVOLUTION_API_URL,
            "evolution_api_key": "***redacted***",
            "instance_name": instance_name,
        }

    tokens = load_user_tokens(user_id, provider)
    if not tokens:
        raise HTTPException(status_code=404, detail="No tokens for this user")
    # Strip internal metadata
    safe = {k: v for k, v in tokens.items() if k not in ("user_id", "updated_at")}
    safe["connected"] = True
    return safe


@app.delete("/oauth/tokens/{user_id}")
async def delete_tokens(user_id: str, provider: str = "google"):
    """Disconnect a provider for a user."""
    if provider == "whatsapp":
        return await _whatsapp_disconnect(user_id)

    if provider not in ("google", "slack"):
        raise HTTPException(status_code=400, detail="Unsupported provider")

    removed = delete_user_tokens(user_id, provider)
    return {
        "connected": False,
        "provider": provider,
        "disconnected": True,
        "deleted": removed,
    }


@app.get("/oauth/refresh/{user_id}")
async def refresh_token(user_id: str):
    tokens = load_user_tokens(user_id)
    if not tokens or not tokens.get("refresh_token"):
        raise HTTPException(status_code=404, detail="No refresh token")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_token": tokens["refresh_token"],
                "grant_type": "refresh_token",
            },
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Token refresh failed")

    new_tokens = resp.json()
    tokens["access_token"] = new_tokens.get("access_token")
    tokens["expires_in"] = new_tokens.get("expires_in")
    save_user_tokens(user_id, tokens)

    return {"access_token": tokens["access_token"], "expires_in": tokens["expires_in"]}


# ─── WhatsApp via Evolution API ───────────────────────────────────────────────


def _wa_user_hash(user_id: str) -> str:
    return hashlib.sha256(user_id.encode()).hexdigest()[:12]


def _wa_instance_base(user_id: str) -> str:
    return f"envision_{_wa_user_hash(user_id)}"


def _wa_meta_path(user_id: str) -> Path:
    safe_id = hashlib.sha256(user_id.encode()).hexdigest()[:16]
    return TOKEN_STORE_DIR / f"{safe_id}_whatsapp_meta.json"


def _wa_load_meta(user_id: str) -> dict:
    path = _wa_meta_path(user_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _wa_save_meta(user_id: str, data: dict) -> None:
    safe = data if isinstance(data, dict) else {}
    safe["updated_at"] = time.time()
    _wa_meta_path(user_id).write_text(json.dumps(safe, indent=2))


def _wa_clear_meta(user_id: str) -> None:
    try:
        _wa_meta_path(user_id).unlink(missing_ok=True)
    except Exception:
        pass


def _wa_set_instance_name(user_id: str, instance_name: str) -> None:
    if not instance_name:
        return
    _wa_save_meta(user_id, {"instance_name": instance_name})


def _wa_new_instance_name(user_id: str) -> str:
    return f"{_wa_instance_base(user_id)}_{secrets.token_hex(2)}"


def _wa_instance_name(user_id: str) -> str:
    meta = _wa_load_meta(user_id)
    name = str(meta.get("instance_name") or "").strip()
    if name:
        return name
    return _wa_instance_base(user_id)


async def _wa_delete_instance(
    client: httpx.AsyncClient, headers: dict[str, str], instance_name: str
) -> bool:
    if not instance_name:
        return False

    attempts = [
        ("DELETE", f"/instance/delete/{instance_name}"),
        ("POST", f"/instance/logout/{instance_name}"),
        ("DELETE", f"/instance/logout/{instance_name}"),
    ]

    deleted = False
    for method, path in attempts:
        try:
            resp = await client.request(method, path, headers=headers)
            if resp.status_code in (200, 201, 202, 204):
                deleted = True
                return deleted
            if resp.status_code == 404:
                return deleted
        except Exception:
            logger.exception(
                "Evolution instance cleanup failed method=%s path=%s", method, path
            )
    return deleted


def _extract_evolution_qr(payload: Any) -> tuple[str, str]:
    """Extract qr base64/code from varying Evolution API response shapes."""
    if not isinstance(payload, dict):
        return "", ""

    qr_base64 = ""
    qr_code = ""

    def pull_from(obj: Any) -> None:
        nonlocal qr_base64, qr_code
        if not isinstance(obj, dict):
            return
        qr_obj = obj.get("qrcode", {})
        if isinstance(qr_obj, dict):
            qr_base64 = qr_obj.get("base64", "") or qr_base64
            qr_code = qr_obj.get("code", "") or qr_code
        qr_base64 = obj.get("base64", "") or qr_base64
        qr_code = obj.get("code", "") or qr_code

    pull_from(payload)
    pull_from(payload.get("message", {}))
    pull_from(payload.get("data", {}))
    return qr_base64, qr_code


async def _whatsapp_connect(user_id: str):
    """Create or fetch a WhatsApp instance and show a QR code page."""
    if not EVOLUTION_API_KEY:
        raise HTTPException(status_code=500, detail="EVOLUTION_API_KEY not configured")

    current_instance_name = _wa_instance_name(user_id)
    base_instance_name = _wa_instance_base(user_id)
    instance_name = current_instance_name
    # Use a fresh instance token per connect attempt to avoid stale session reuse.
    instance_token = secrets.token_hex(12).upper()
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}

    qr_base64 = ""
    qr_code = ""
    create_status = 0
    create_body = ""
    connect_status = 0
    connect_body = ""

    # If already linked, do not start a new QR flow.
    try:
        status = await _whatsapp_check(user_id=user_id, instance=instance_name)
        if status and status.get("connected"):
            return HTMLResponse("""
            <html><body style="font-family:-apple-system,sans-serif;background:#111827;color:#e5e7eb;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
              <div style="text-align:center;max-width:420px;padding:2rem;">
                <h2 style="color:#4ade80;">WhatsApp Already Connected</h2>
                <p>You can close this tab and return to your chat.</p>
              </div>
              <script>setTimeout(function(){ window.close(); }, 1500);</script>
            </body></html>
            """)
    except HTTPException:
        pass

    try:
        async with httpx.AsyncClient(base_url=EVOLUTION_API_URL, timeout=8.0) as client:
            # New connect attempts get a fresh instance name to avoid reusing
            # corrupted/stuck auth states from previous failed scans.
            fresh_instance_name = _wa_new_instance_name(user_id)
            cleanup_names: list[str] = []
            if current_instance_name:
                cleanup_names.append(current_instance_name)
            if base_instance_name and base_instance_name != current_instance_name:
                cleanup_names.append(base_instance_name)
            for old_name in cleanup_names:
                await _wa_delete_instance(client, headers, old_name)

            instance_name = fresh_instance_name
            _wa_set_instance_name(user_id, instance_name)

            # Reuse connecting/open sessions; only reset clearly closed/broken ones.
            instance_exists = False
            existing_state = ""
            existing_row: dict[str, Any] = {}
            try:
                state_resp = await client.get(
                    f"/instance/connectionState/{instance_name}",
                    headers=headers,
                )
                if state_resp.status_code == 200:
                    instance_exists = True
                    state_data = state_resp.json() if state_resp.text else {}
                    existing_state = (
                        state_data.get("instance", {}).get("state", "") or ""
                    ).strip().lower()
                    try:
                        list_resp = await client.get("/instance/fetchInstances", headers=headers)
                        if list_resp.status_code == 200 and list_resp.text:
                            rows = list_resp.json()
                            if isinstance(rows, list):
                                for row in rows:
                                    if (
                                        isinstance(row, dict)
                                        and row.get("name") == instance_name
                                    ):
                                        existing_row = row
                                        break
                    except Exception:
                        logger.exception(
                            "Evolution fetchInstances failed during connect for %s",
                            instance_name,
                        )
            except Exception:
                logger.exception("Evolution state check failed for %s", instance_name)

            # Recover from stale connecting sessions that never complete.
            if instance_exists and existing_state == "connecting":
                owner_jid = (existing_row.get("ownerJid") or "").strip()
                updated_at = (existing_row.get("updatedAt") or "").strip()
                stale = False
                if not owner_jid and updated_at:
                    try:
                        updated_dt = datetime.fromisoformat(
                            updated_at.replace("Z", "+00:00")
                        )
                        age_s = (datetime.now(timezone.utc) - updated_dt).total_seconds()
                        if age_s > 120:
                            stale = True
                    except Exception:
                        stale = False
                if stale:
                    logger.warning(
                        "Evolution instance %s is stale connecting; forcing reset",
                        instance_name,
                    )
                    try:
                        await client.delete(
                            f"/instance/delete/{instance_name}", headers=headers
                        )
                    except Exception:
                        logger.exception(
                            "Evolution stale-connecting delete failed for %s",
                            instance_name,
                        )
                    await asyncio.sleep(1.0)
                    instance_exists = False
                    existing_state = ""

            # Recover from zombie "open" sessions that are not actually usable.
            # This prevents repeated invalid-link loops where Evolution stays open
            # with ownerJid but never syncs chats/messages.
            if instance_exists and existing_state == "open":
                owner_jid = (existing_row.get("ownerJid") or "").strip()
                reason_code = existing_row.get("disconnectionReasonCode")
                updated_at = (existing_row.get("updatedAt") or "").strip()

                age_s = 0.0
                if updated_at:
                    try:
                        updated_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                        age_s = (datetime.now(timezone.utc) - updated_dt).total_seconds()
                    except Exception:
                        age_s = 0.0

                should_reset_open = bool(reason_code) or (not owner_jid and age_s > 120)

                if should_reset_open:
                    logger.warning(
                        "Evolution instance %s is open-but-unusable; forcing reset",
                        instance_name,
                    )
                    try:
                        await client.delete(
                            f"/instance/delete/{instance_name}",
                            headers=headers,
                        )
                    except Exception:
                        logger.exception(
                            "Evolution zombie-open delete failed for %s",
                            instance_name,
                        )
                    await asyncio.sleep(1.0)
                    instance_exists = False
                    existing_state = ""

            # Closed/broken sessions are reset; active handshakes are reused.
            if instance_exists and existing_state not in ("connecting", "open"):
                try:
                    await client.delete(f"/instance/delete/{instance_name}", headers=headers)
                except Exception:
                    logger.exception("Evolution reset delete failed for %s", instance_name)
                await asyncio.sleep(1.0)
                instance_exists = False

            # If an instance is already active/connecting, request current QR first.
            if instance_exists and not qr_base64:
                for _ in range(3):
                    qr_resp = await client.get(
                        f"/instance/connect/{instance_name}",
                        headers=headers,
                    )
                    connect_status = qr_resp.status_code
                    connect_body = (qr_resp.text or "")[:600]
                    if qr_resp.status_code == 200:
                        qr_data = qr_resp.json() if qr_resp.text else {}
                        qr_from_connect, code_from_connect = _extract_evolution_qr(
                            qr_data
                        )
                        qr_base64 = qr_from_connect or qr_base64
                        qr_code = code_from_connect or qr_code
                    if qr_base64:
                        break
                    await asyncio.sleep(1.0)

            # Create only when instance does not exist (or connect path didn't return data).
            if not qr_base64 and not instance_exists:
                create_payload = {
                    "instanceName": instance_name,
                    "integration": "WHATSAPP-BAILEYS",
                    "token": instance_token,
                    "qrcode": True,
                    "settings": {
                        "syncFullHistory": True,
                        "readMessages": False,
                        "readStatus": False,
                    },
                }
                # Evolution API v2.2.x expects a token for Baileys instances and
                # returns QR reliably when qrcode=true is set.
                create_resp = await client.post(
                    "/instance/create",
                    json=create_payload,
                    headers=headers,
                )
                create_status = create_resp.status_code
                create_body = (create_resp.text or "")[:600]
                logger.info(
                    "Evolution create instance %s: %s",
                    instance_name,
                    create_resp.status_code,
                )

                # Handle stale reserved names by retrying after forced delete.
                if create_status == 403 and "already in use" in create_body.lower():
                    logger.warning(
                        "Evolution instance name already in use for %s; forcing delete+retry",
                        instance_name,
                    )
                    try:
                        await client.delete(
                            f"/instance/delete/{instance_name}", headers=headers
                        )
                    except Exception:
                        logger.exception(
                            "Evolution delete retry failed for %s", instance_name
                        )
                    await asyncio.sleep(1.2)
                    create_resp = await client.post(
                        "/instance/create",
                        json=create_payload,
                        headers=headers,
                    )
                    create_status = create_resp.status_code
                    create_body = (create_resp.text or "")[:600]
                    logger.info(
                        "Evolution create retry %s: %s",
                        instance_name,
                        create_resp.status_code,
                    )

                if create_resp.status_code in (200, 201):
                    create_data = create_resp.json() if create_resp.text else {}
                    qr_from_create, code_from_create = _extract_evolution_qr(create_data)
                    qr_base64 = qr_from_create or qr_base64
                    qr_code = code_from_create or qr_code

                # Fall back to connect endpoint if create didn't return a QR.
                if not qr_base64:
                    for _ in range(3):
                        qr_resp = await client.get(
                            f"/instance/connect/{instance_name}",
                            headers=headers,
                        )
                        connect_status = qr_resp.status_code
                        connect_body = (qr_resp.text or "")[:600]
                        if qr_resp.status_code == 200:
                            qr_data = qr_resp.json() if qr_resp.text else {}
                            qr_from_connect, code_from_connect = _extract_evolution_qr(
                                qr_data
                            )
                            qr_base64 = qr_from_connect or qr_base64
                            qr_code = code_from_connect or qr_code
                        if qr_base64:
                            break
                        await asyncio.sleep(1.0)
    except Exception as exc:
        logger.exception("Evolution API connect failed for %s", instance_name)
        return HTMLResponse(
            "<h2>WhatsApp unavailable right now</h2>"
            "<p>Could not reach the WhatsApp connector service.</p>"
            f"<p style='color:#6b7280;font-size:0.9rem'>Details: {str(exc)}</p>",
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )

    if qr_base64 and not qr_base64.startswith("data:image"):
        qr_base64 = f"data:image/png;base64,{qr_base64}"

    if not qr_base64:
        logger.error("Evolution QR not available for %s", instance_name)
        return HTMLResponse(
            "<h2>WhatsApp connection not ready</h2>"
            "<p>The connector did not return a QR code yet. Please close this tab and try Connect again in 10-20 seconds.</p>"
            f"<p style='color:#6b7280;font-size:0.9rem'>Create status: {create_status} | Connect status: {connect_status}</p>"
            f"<p style='color:#6b7280;font-size:0.8rem;word-break:break-word'>Create response: {create_body}</p>"
            f"<p style='color:#6b7280;font-size:0.8rem;word-break:break-word'>Connect response: {connect_body}</p>",
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )

    # Render a page with the QR code that auto-polls for connection
    return HTMLResponse(f"""
    <html>
    <head><style>
        body {{ background: #1a1a2e; color: #e0e0e0; font-family: -apple-system, sans-serif;
               display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
        .card {{ text-align: center; padding: 2.5rem; border-radius: 16px; max-width: 420px;
                background: rgba(255,255,255,0.05); backdrop-filter: blur(10px); }}
        h2 {{ color: #25D366; margin-bottom: 0.5rem; }}
        p {{ color: #9ca3af; font-size: 0.9rem; }}
        img {{ border-radius: 12px; margin: 1.5rem 0; }}
        .refresh-btn {{ margin-top: .2rem; border:1px solid rgba(255,255,255,.2); background:rgba(255,255,255,.06); color:#e5e7eb; border-radius:10px; padding:.45rem .8rem; font-size:.78rem; cursor:pointer; }}
        .refresh-btn:hover {{ background:rgba(255,255,255,.12); }}
        .connected {{ display: none; }}
        .connected.show {{ display: block; }}
        .qr-area.hide {{ display: none; }}
    </style></head>
    <body><div class="card">
        <div class="qr-area" id="qr">
            <h2>Connect WhatsApp</h2>
            <p>Scan this QR code with your phone's WhatsApp app</p>
            <img id="qr-img" src="{qr_base64}" width="260" height="260" alt="QR Code" />
            <button id="refresh-btn" class="refresh-btn" type="button">Refresh QR</button>
            <p id="status-note" style="font-size:0.8rem;color:#6b7280;">Open WhatsApp &gt; Settings &gt; Linked Devices &gt; Link a Device</p>
        </div>
        <div class="connected" id="done">
            <h2 style="color:#4ade80;">WhatsApp Connected</h2>
            <p>You can close this tab and return to your chat.</p>
            <p style="margin-top:1rem;font-size:0.85rem;color:#6b7280;">Your WhatsApp messaging is now active.</p>
        </div>
    </div>
    <script>
        function showConnected() {{
            document.getElementById('qr').classList.add('hide');
            document.getElementById('done').classList.add('show');
            setTimeout(function() {{ window.close(); }}, 2000);
        }}

        function refreshQr(force) {{
            var url = '/oauth/whatsapp/qr/{user_id}?_ts=' + Date.now();
            if (force) url += '&force=1';
            return fetch(url, {{ cache: 'no-store' }})
                .then(function(r) {{ return r.ok ? r.json() : null; }})
                .then(function(d) {{
                    if (!d) return;
                    if (d.connected) {{
                        var noteOk = document.getElementById('status-note');
                        if (noteOk) noteOk.textContent = 'Connection verified. Finalizing...';
                        return;
                    }}
                    if (d.pending) {{
                        var notePending = document.getElementById('status-note');
                        if (notePending) notePending.textContent = 'Waiting for WhatsApp confirmation... keep WhatsApp open on your phone.';
                        return;
                    }}
                    if (d.base64) {{
                        var img = document.getElementById('qr-img');
                        if (img) img.src = d.base64;
                        var note = document.getElementById('status-note');
                        if (note) note.textContent = 'QR refreshed. Scan from WhatsApp > Settings > Linked Devices > Link a Device';
                    }}
                }})
                .catch(function() {{}});
        }}

        var refreshBtn = document.getElementById('refresh-btn');
        if (refreshBtn) {{
            refreshBtn.addEventListener('click', function() {{
                refreshQr(true);
            }});
        }}

        var connectedStreak = 0;
        var poll = setInterval(function() {{
            fetch('/oauth/tokens/{user_id}?provider=whatsapp&instance={instance_name}')
                .then(function(r) {{ return r.ok ? r.json() : null; }})
                .then(function(d) {{
                    if (d && d.connected) {{
                        connectedStreak += 1;
                        var note = document.getElementById('status-note');
                        if (note && connectedStreak < 2) {{
                            note.textContent = 'Connection detected. Verifying stability...';
                        }}
                        if (connectedStreak >= 2) {{
                            clearInterval(poll);
                            showConnected();
                        }}
                        return;
                    }}
                    connectedStreak = 0;
                }})
                .catch(function() {{}});
        }}, 3000);

        // Do not auto-rotate QR while user is scanning.
        // Auto-refresh can invalidate a just-scanned code and cause link failures.
    </script>
    </body></html>
    """, headers={"Cache-Control": "no-store"})


async def _whatsapp_check(user_id: str, instance: str = ""):
    """Check whether a WhatsApp instance is connected."""
    if not EVOLUTION_API_KEY:
        raise HTTPException(status_code=404, detail="WhatsApp not configured")

    instance_name = instance or _wa_instance_name(user_id)
    headers = {"apikey": EVOLUTION_API_KEY}

    try:
        async with httpx.AsyncClient(base_url=EVOLUTION_API_URL, timeout=10.0) as client:
            state_resp = await client.get(
                f"/instance/connectionState/{instance_name}",
                headers=headers,
            )
            list_resp = await client.get("/instance/fetchInstances", headers=headers)
            state = ""
            if state_resp.status_code == 200:
                state_data = state_resp.json() if state_resp.text else {}
                state = state_data.get("instance", {}).get("state", "")

            instance_row = {}
            if list_resp.status_code == 200 and list_resp.text:
                rows = list_resp.json()
                if isinstance(rows, list):
                    for row in rows:
                        if isinstance(row, dict) and row.get("name") == instance_name:
                            instance_row = row
                            break

            conn_status = (instance_row.get("connectionStatus") or "").strip().lower()
            owner_jid = (instance_row.get("ownerJid") or "").strip()
            counts = instance_row.get("_count", {})
            chat_count = 0
            message_count = 0
            if isinstance(counts, dict):
                try:
                    chat_count = int(counts.get("Chat") or 0)
                except Exception:
                    chat_count = 0
                try:
                    message_count = int(counts.get("Message") or 0)
                except Exception:
                    message_count = 0

            if state == "open" and conn_status == "open" and owner_jid:
                # Consider linked as soon as transport is open and ownerJid exists.
                # Chat/message sync can lag after link; expose readiness separately.
                data_ready = chat_count > 0 or message_count > 0
                if not data_ready:
                    try:
                        chats_resp = await client.post(
                            f"/chat/findChats/{instance_name}",
                            headers=headers,
                            json={"page": 1, "limit": 1},
                        )
                        if chats_resp.status_code < 400:
                            chats_payload = chats_resp.json() if chats_resp.text else []
                            if isinstance(chats_payload, list) and len(chats_payload) > 0:
                                chat_count = max(chat_count, len(chats_payload))
                                data_ready = True
                    except Exception:
                        pass

                if not data_ready:
                    try:
                        msgs_resp = await client.post(
                            f"/chat/findMessages/{instance_name}",
                            headers=headers,
                            json={"page": 1, "limit": 1},
                        )
                        if msgs_resp.status_code < 400:
                            msgs_payload = msgs_resp.json() if msgs_resp.text else {}
                            records = []
                            if isinstance(msgs_payload, dict):
                                msgs_root = msgs_payload.get("messages")
                                if isinstance(msgs_root, dict):
                                    rec = msgs_root.get("records")
                                    if isinstance(rec, list):
                                        records = rec
                            if records:
                                message_count = max(message_count, len(records))
                                data_ready = True
                    except Exception:
                        pass

                return {
                    "connected": True,
                    "state": state,
                    "connection_status": conn_status,
                    "owner_jid": owner_jid,
                    "instance_name": instance_name,
                    "chat_count": chat_count,
                    "message_count": message_count,
                    "data_ready": data_ready,
                }

            reason_code = instance_row.get("disconnectionReasonCode")
            if reason_code:
                raise HTTPException(
                    status_code=404,
                    detail=f"WhatsApp not connected (reason code: {reason_code})",
                )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Evolution API check failed")

    raise HTTPException(status_code=404, detail="WhatsApp not connected")


@app.get("/oauth/whatsapp/qr/{user_id}")
async def whatsapp_qr(user_id: str, force: bool = False):
    """Return a fresh QR for a user's WhatsApp instance while still unlinked."""
    if not EVOLUTION_API_KEY:
        raise HTTPException(status_code=500, detail="EVOLUTION_API_KEY not configured")

    instance_name = _wa_instance_name(user_id)
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}

    # First, check using the strict connected criteria used by /oauth/tokens.
    try:
        status = await _whatsapp_check(user_id=user_id, instance=instance_name)
        if status and status.get("connected"):
            return {
                "connected": True,
                "state": status.get("state", "open"),
                "instance_name": instance_name,
                "owner_jid": status.get("owner_jid", ""),
            }
    except HTTPException:
        pass

    async with httpx.AsyncClient(base_url=EVOLUTION_API_URL, timeout=10.0) as client:
        state_resp = await client.get(
            f"/instance/connectionState/{instance_name}",
            headers=headers,
        )
        if state_resp.status_code == 200:
            state_data = state_resp.json() if state_resp.text else {}
            state = state_data.get("instance", {}).get("state", "")
            # During handshake, don't rotate QR automatically unless explicitly forced.
            if state == "connecting" and not force:
                return {
                    "connected": False,
                    "pending": True,
                    "state": state,
                    "instance_name": instance_name,
                }

        qr_resp = await client.get(
            f"/instance/connect/{instance_name}",
            headers=headers,
        )
        if qr_resp.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"QR fetch failed (HTTP {qr_resp.status_code})",
            )
        qr_data = qr_resp.json() if qr_resp.text else {}
        qr_base64, qr_code = _extract_evolution_qr(qr_data)
        if not qr_base64:
            raise HTTPException(status_code=503, detail="QR not available yet")
        if not qr_base64.startswith("data:image"):
            qr_base64 = f"data:image/png;base64,{qr_base64}"
        return {
            "connected": False,
            "instance_name": instance_name,
            "base64": qr_base64,
            "code": qr_code,
        }


def _extract_wa_records(payload: Any) -> list[dict]:
    def as_dict_list(value: Any) -> list[dict]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    if isinstance(payload, list):
        return as_dict_list(payload)
    if not isinstance(payload, dict):
        return []

    candidates = [
        payload.get("messages"),
        payload.get("records"),
        payload.get("data"),
        payload.get("response"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            nested = (
                candidate.get("records")
                or candidate.get("messages")
                or candidate.get("data")
            )
            records = as_dict_list(nested)
            if records:
                return records
        records = as_dict_list(candidate)
        if records:
            return records
    return []


def _extract_wa_chat_last_messages(payload: Any) -> list[dict]:
    chats = []
    if isinstance(payload, list):
        chats = payload
    elif isinstance(payload, dict):
        chats = payload.get("chats") or payload.get("data") or payload.get("records") or []
    if not isinstance(chats, list):
        return []

    out = []
    for chat in chats:
        if not isinstance(chat, dict):
            continue
        last_message = chat.get("lastMessage")
        if not isinstance(last_message, dict):
            last_message = {}

        key = last_message.get("key")
        if not isinstance(key, dict):
            key = {}

        remote = (
            key.get("remoteJid")
            or chat.get("id")
            or chat.get("jid")
            or chat.get("remoteJid")
            or ""
        )
        out.append(
            {
                "message": last_message.get("message")
                or chat.get("message")
                or last_message
                or chat,
                "messageTimestamp": last_message.get("messageTimestamp")
                or chat.get("conversationTimestamp")
                or chat.get("timestamp")
                or chat.get("updatedAt")
                or 0,
                "fromMe": bool(
                    last_message.get("fromMe")
                    or key.get("fromMe")
                    or chat.get("fromMe")
                ),
                "pushName": chat.get("name") or chat.get("pushName") or "",
                "sender": chat.get("name") or chat.get("pushName") or remote,
                "remoteJid": remote,
                "key": {
                    "remoteJid": remote,
                    "fromMe": bool(
                        last_message.get("fromMe")
                        or key.get("fromMe")
                        or chat.get("fromMe")
                    ),
                },
            }
        )
    return [item for item in out if isinstance(item, dict)]


async def _whatsapp_fetch_records(user_id: str, limit: int = 80) -> list[dict]:
    if not EVOLUTION_API_KEY:
        raise HTTPException(status_code=404, detail="WhatsApp not configured")

    instance_name = _wa_instance_name(user_id)
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    q_limit = max(20, min(limit, 150))

    async with httpx.AsyncClient(base_url=EVOLUTION_API_URL, timeout=12.0) as client:
        # Primary endpoint
        resp = await client.post(
            f"/chat/findMessages/{instance_name}",
            headers=headers,
            json={"page": 1, "limit": q_limit},
        )
        if resp.status_code < 400:
            data = resp.json() if resp.text else {}
            records = _extract_wa_records(data)
            if records:
                return records

        # Fallback endpoint
        chats_resp = await client.post(
            f"/chat/findChats/{instance_name}",
            headers=headers,
            json={"page": 1, "limit": max(20, min(q_limit, 100))},
        )
        if chats_resp.status_code < 400:
            chats_data = chats_resp.json() if chats_resp.text else {}
            return _extract_wa_chat_last_messages(chats_data)

        return []


@app.get("/oauth/whatsapp/messages/{user_id}")
async def whatsapp_messages(user_id: str, limit: int = 80):
    """Return recent WhatsApp message records for a connected user."""
    await _whatsapp_check(user_id)
    records = await _whatsapp_fetch_records(user_id=user_id, limit=limit)
    return {"connected": True, "provider": "whatsapp", "records": records}


async def _whatsapp_disconnect(user_id: str, instance: str = ""):
    """Best-effort disconnect of WhatsApp instance from Evolution API."""
    if not EVOLUTION_API_KEY:
        return {
            "connected": False,
            "provider": "whatsapp",
            "disconnected": True,
            "deleted": False,
            "note": "EVOLUTION_API_KEY not configured",
        }

    mapped_name = _wa_instance_name(user_id)
    base_name = _wa_instance_base(user_id)
    targets = [instance or mapped_name, mapped_name, base_name]
    seen: set[str] = set()
    unique_targets: list[str] = []
    for name in targets:
        if name and name not in seen:
            seen.add(name)
            unique_targets.append(name)

    headers = {"apikey": EVOLUTION_API_KEY}
    deleted_any = False
    async with httpx.AsyncClient(base_url=EVOLUTION_API_URL, timeout=10.0) as client:
        for target in unique_targets:
            deleted_any = (await _wa_delete_instance(client, headers, target)) or deleted_any

    _wa_clear_meta(user_id)
    return {
        "connected": False,
        "provider": "whatsapp",
        "disconnected": True,
        "deleted": deleted_any,
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "dlp-proxy",
        "oauth_configured": bool(GOOGLE_CLIENT_ID),
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """Proxy /v1/chat/completions with DLP inspection on input."""
    body = await request.json()

    # Inspect only the latest user input turn.
    user_text = extract_latest_user_text(body)
    findings = inspect_content(user_text)

    if findings:
        logger.warning(
            "DLP findings in user input: %s", json.dumps(findings, default=str)
        )

        if BLOCK_ON_FINDING:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "PII detected in input",
                    "findings": findings,
                    "message": "Please remove sensitive data before sending.",
                },
            )

        # Redact only the latest user turn; keep tool/assistant history intact.
        redact_latest_user_message(body)

    # Check if streaming is requested
    stream = body.get("stream", False)
    headers = {
        "Content-Type": "application/json",
        "Authorization": request.headers.get("Authorization", ""),
    }

    if stream:
        return await _proxy_stream(body, headers)
    else:
        return await _proxy_sync(body, headers)


async def _proxy_sync(body: dict, headers: dict) -> Response:
    """Forward non-streaming request and inspect response."""
    try:
        resp = await http_client.post(
            "/v1/chat/completions", json=body, headers=headers
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream error: {exc}") from exc

    if resp.status_code != 200:
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type="application/json",
        )

    resp_body = resp.json()

    # Inspect/redact assistant response only when explicitly enabled.
    if REDACT_ASSISTANT_OUTPUT:
        choices = resp_body.get("choices", [])
        for choice in choices:
            msg = choice.get("message", {})
            content = msg.get("content", "")
            if content:
                resp_findings = inspect_content(content)
                if resp_findings:
                    logger.warning(
                        "DLP findings in response: %s",
                        json.dumps(resp_findings, default=str),
                    )
                    msg["content"] = redact_content(content)

    return Response(
        content=json.dumps(resp_body),
        status_code=200,
        media_type="application/json",
    )


async def _proxy_stream(body: dict, headers: dict) -> StreamingResponse:
    """Forward streaming request. DLP inspection on chunks is best-effort."""

    async def stream_generator():
        try:
            async with http_client.stream(
                "POST", "/v1/chat/completions", json=body, headers=headers
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        chunk_str = line[6:]
                        if chunk_str.strip() == "[DONE]":
                            yield f"data: [DONE]\n\n"
                            break
                        try:
                            chunk = json.loads(chunk_str)
                            # Best-effort streaming redaction only if enabled.
                            if REDACT_ASSISTANT_OUTPUT:
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    findings = inspect_content(content)
                                    if findings:
                                        logger.warning(
                                            "DLP finding in stream chunk: %s", findings
                                        )
                                        delta["content"] = redact_content(content)
                                        chunk["choices"][0]["delta"] = delta
                            yield f"data: {json.dumps(chunk)}\n\n"
                        except json.JSONDecodeError:
                            yield f"{line}\n"
                    elif line.strip():
                        yield f"{line}\n"
        except httpx.RequestError as exc:
            logger.error("Stream proxy error: %s", exc)
            yield f'data: {{"error": "{exc}"}}\n\n'

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def catch_all(request: Request, path: str):
    """Pass-through for non-chat endpoints (models, etc.)."""
    body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)

    try:
        resp = await http_client.request(
            method=request.method,
            url=f"/{path}",
            content=body,
            headers=headers,
        )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type", "application/json"),
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream error: {exc}") from exc
