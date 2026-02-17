"""DLP Proxy — FastAPI service that inspects/redacts PII via GCP Sensitive Data Protection.

Sits between Open Web UI and OpenClaw Gateway. Inspects user prompts on the way in
and assistant responses on the way out. Redacts or blocks sensitive content.

Also serves as the OAuth 2.0 callback handler for Google integrations.
Users connect their Google account via /oauth/start → consent → /oauth/callback.
Tokens are stored per-user in /data/tokens/.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.parse
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from google.cloud import dlp_v2

# ─── Configuration ────────────────────────────────────────────────────────────
OPENCLAW_UPSTREAM = os.getenv("OPENCLAW_UPSTREAM", "http://openclaw:11434")
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "open-os-prod")
DLP_MIN_LIKELIHOOD = os.getenv("DLP_MIN_LIKELIHOOD", "LIKELY")
BLOCK_ON_FINDING = os.getenv("BLOCK_ON_FINDING", "false").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# OAuth 2.0 config — Google
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
OAUTH_REDIRECT_URI = os.getenv(
    "OAUTH_REDIRECT_URI", "https://os.envsn.com/oauth/callback"
)
GOOGLE_SCOPES = "openid email https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/drive.readonly"

# OAuth 2.0 config — Slack (personal user token, not workspace bot)
SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID", "")
SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET", "")
SLACK_USER_SCOPES = os.getenv(
    "SLACK_USER_SCOPES",
    "channels:read,channels:history,chat:write,users:read,files:read,search:read",
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
        logger.exception("DLP inspect_content failed")
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
                "inspect_config": INSPECT_CONFIG,
                "item": item,
            }
        )
        return response.item.value
    except Exception:
        logger.exception("DLP deidentify_content failed")
        return text


def extract_messages_text(body: dict) -> str:
    """Extract concatenated message text from OpenAI-format request body."""
    messages = body.get("messages", [])
    parts = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(part.get("text", ""))
    return "\n".join(parts)


# ─── OAuth 2.0 Token Store Helpers ─────────────────────────────────────────────


def _token_path(user_id: str, provider: str = "google") -> Path:
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
    _token_path(user_id, provider).write_text(json.dumps(tokens, indent=2))


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
        return HTMLResponse(
            f"<h2>Token exchange failed</h2><pre>{resp.text}</pre>", status_code=500
        )

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
async def get_tokens(user_id: str, provider: str = "google"):
    # ── WhatsApp: check Evolution API instance ────────────────────────
    if provider == "whatsapp":
        return await _whatsapp_check(user_id)

    tokens = load_user_tokens(user_id, provider)
    if not tokens:
        raise HTTPException(status_code=404, detail="No tokens for this user")
    return {
        "connected": True,
        "scope": tokens.get("scope", ""),
        "has_refresh_token": bool(tokens.get("refresh_token")),
    }


@app.get("/oauth/tokens/{user_id}/full")
async def get_full_tokens(user_id: str, provider: str = "google"):
    """Return full token payload for tool use (called by Open WebUI tools)."""
    if provider == "whatsapp":
        # Return Evolution API config so the WhatsApp tool can call Evolution directly
        instance_name = _wa_instance_name(user_id)
        return {
            "connected": True,
            "provider": "whatsapp",
            "evolution_api_url": EVOLUTION_API_URL,
            "evolution_api_key": EVOLUTION_API_KEY,
            "instance_name": instance_name,
        }

    tokens = load_user_tokens(user_id, provider)
    if not tokens:
        raise HTTPException(status_code=404, detail="No tokens for this user")
    # Strip internal metadata
    safe = {k: v for k, v in tokens.items() if k not in ("user_id", "updated_at")}
    safe["connected"] = True
    return safe


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


def _wa_instance_name(user_id: str) -> str:
    return f"envision_{hashlib.sha256(user_id.encode()).hexdigest()[:12]}"


async def _whatsapp_connect(user_id: str):
    """Create or fetch a WhatsApp instance and show a QR code page."""
    if not EVOLUTION_API_KEY:
        raise HTTPException(status_code=500, detail="EVOLUTION_API_KEY not configured")

    instance_name = _wa_instance_name(user_id)
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}

    qr_base64 = ""
    qr_code = ""

    async with httpx.AsyncClient(base_url=EVOLUTION_API_URL, timeout=30.0) as client:
        # Try to create instance — returns QR in response if qrcode=True
        create_resp = await client.post(
            "/instance/create",
            json={
                "instanceName": instance_name,
                "integration": "WHATSAPP-BAILEYS",
                "qrcode": True,
            },
            headers=headers,
        )
        logger.info("Evolution create instance %s: %s", instance_name, create_resp.status_code)

        if create_resp.status_code in (200, 201):
            create_data = create_resp.json()
            # QR comes nested under qrcode.base64 in create response
            qr_obj = create_data.get("qrcode", {})
            if isinstance(qr_obj, dict):
                qr_base64 = qr_obj.get("base64", "")
                qr_code = qr_obj.get("code", "")

        # Fall back to connect endpoint if create didn't return a QR
        if not qr_base64:
            qr_resp = await client.get(
                f"/instance/connect/{instance_name}",
                headers=headers,
            )
            if qr_resp.status_code == 200:
                qr_data = qr_resp.json()
                qr_base64 = qr_data.get("base64", "")
                qr_code = qr_data.get("code", "")

    if not qr_base64:
        logger.error("Evolution QR not available for %s", instance_name)
        return HTMLResponse(
            "<h2>WhatsApp connection failed</h2><p>Could not generate QR code. Try again.</p>",
            status_code=500,
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
        .connected {{ display: none; }}
        .connected.show {{ display: block; }}
        .qr-area.hide {{ display: none; }}
    </style></head>
    <body><div class="card">
        <div class="qr-area" id="qr">
            <h2>Connect WhatsApp</h2>
            <p>Scan this QR code with your phone's WhatsApp app</p>
            <img src="{qr_base64}" width="260" height="260" alt="QR Code" />
            <p style="font-size:0.8rem;color:#6b7280;">Open WhatsApp &gt; Settings &gt; Linked Devices &gt; Link a Device</p>
        </div>
        <div class="connected" id="done">
            <h2 style="color:#4ade80;">WhatsApp Connected</h2>
            <p>You can close this tab and return to your chat.</p>
            <p style="margin-top:1rem;font-size:0.85rem;color:#6b7280;">Your WhatsApp messaging is now active.</p>
        </div>
    </div>
    <script>
        var poll = setInterval(function() {{
            fetch('/oauth/tokens/{qr_code or "check"}?provider=whatsapp&instance={instance_name}')
                .then(function(r) {{ return r.ok ? r.json() : null; }})
                .then(function(d) {{
                    if (d && d.connected) {{
                        clearInterval(poll);
                        document.getElementById('qr').classList.add('hide');
                        document.getElementById('done').classList.add('show');
                        // Auto-close after 2s so onboarding popup detects closure
                        setTimeout(function() {{ window.close(); }}, 2000);
                    }}
                }})
                .catch(function() {{}});
        }}, 3000);
    </script>
    </body></html>
    """)


async def _whatsapp_check(user_id: str, instance: str = ""):
    """Check whether a WhatsApp instance is connected."""
    if not EVOLUTION_API_KEY:
        raise HTTPException(status_code=404, detail="WhatsApp not configured")

    instance_name = instance or _wa_instance_name(user_id)
    headers = {"apikey": EVOLUTION_API_KEY}

    try:
        async with httpx.AsyncClient(
            base_url=EVOLUTION_API_URL, timeout=10.0
        ) as client:
            resp = await client.get(
                f"/instance/connectionState/{instance_name}",
                headers=headers,
            )
        if resp.status_code == 200:
            data = resp.json()
            state = data.get("instance", {}).get("state", "")
            if state == "open":
                return {"connected": True, "state": state}
    except Exception:
        logger.exception("Evolution API check failed")

    raise HTTPException(status_code=404, detail="WhatsApp not connected")


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

    # Inspect user input
    user_text = extract_messages_text(body)
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

        # Redact and replace messages
        for msg in body.get("messages", []):
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                msg["content"] = redact_content(content)

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

    # Inspect assistant response
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
                            # Best-effort: log but don't block streaming
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content and len(content) > 20:
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
