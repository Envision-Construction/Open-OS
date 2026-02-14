"""DLP Proxy — FastAPI service that inspects/redacts PII via GCP Sensitive Data Protection.

Sits between Open Web UI and OpenClaw Gateway. Inspects user prompts on the way in
and assistant responses on the way out. Redacts or blocks sensitive content.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from google.cloud import dlp_v2

# ─── Configuration ────────────────────────────────────────────────────────────
OPENCLAW_UPSTREAM = os.getenv("OPENCLAW_UPSTREAM", "http://openclaw:11434")
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "open-os-prod")
DLP_MIN_LIKELIHOOD = os.getenv("DLP_MIN_LIKELIHOOD", "LIKELY")
BLOCK_ON_FINDING = os.getenv("BLOCK_ON_FINDING", "false").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "dlp-proxy"}


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
