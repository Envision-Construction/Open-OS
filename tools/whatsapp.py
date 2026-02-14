"""
title: WhatsApp
author: Avi Reddy
version: 0.1.0
license: MIT
description: Send and read WhatsApp messages using the WhatsApp Cloud API
required_pip_packages: aiohttp
"""

from __future__ import annotations

import re
from pydantic import BaseModel


class Tools:
    API_BASE = "https://graph.facebook.com/v21.0"

    class Valves(BaseModel):
        whatsapp_access_token: str = ""
        whatsapp_phone_number_id: str = ""
        whatsapp_business_account_id: str = ""

    def __init__(self) -> None:
        self.valves = self.Valves()

    async def send_message(
        self,
        to: str,
        message: str,
        __user__: dict,
        __event_emitter__,
    ) -> str:
        user_label = self._user_label(__user__)
        await self._emit_status(
            __event_emitter__,
            f"Sending WhatsApp message{user_label}...",
            status="in_progress",
        )

        missing = self._missing_config(
            ["whatsapp_access_token", "whatsapp_phone_number_id"]
        )
        if missing:
            error_message = f"Missing configuration: {', '.join(missing)}"
            await self._emit_status(__event_emitter__, error_message, status="error")
            return error_message

        cleaned_to = self._normalize_phone_number(to)
        if not cleaned_to:
            error_message = "Invalid phone number. Provide an international format like +15551234567."
            await self._emit_status(__event_emitter__, error_message, status="error")
            return error_message

        url = f"{self.API_BASE}/{self.valves.whatsapp_phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": cleaned_to,
            "type": "text",
            "text": {"body": message},
        }

        status_code, data = await self._request("POST", url, payload)
        if status_code is None:
            error_message = "WhatsApp API request failed. Please try again later."
            await self._emit_status(__event_emitter__, error_message, status="error")
            return error_message

        if status_code >= 400:
            error_message = self._format_error(status_code, data)
            await self._emit_status(__event_emitter__, error_message, status="error")
            return error_message

        message_id = self._extract_message_id(data)
        await self._emit_status(
            __event_emitter__, "WhatsApp message sent.", status="complete"
        )
        if message_id:
            return f"WhatsApp message sent successfully. Message ID: {message_id}"
        return "WhatsApp message sent successfully."

    async def send_template_message(
        self,
        to: str,
        template_name: str,
        language_code: str = "en_US",
        __user__: dict = None,
        __event_emitter__=None,
    ) -> str:
        user_label = self._user_label(__user__ or {})
        await self._emit_status(
            __event_emitter__,
            f"Sending WhatsApp template{user_label}...",
            status="in_progress",
        )

        missing = self._missing_config(
            ["whatsapp_access_token", "whatsapp_phone_number_id"]
        )
        if missing:
            error_message = f"Missing configuration: {', '.join(missing)}"
            await self._emit_status(__event_emitter__, error_message, status="error")
            return error_message

        cleaned_to = self._normalize_phone_number(to)
        if not cleaned_to:
            error_message = "Invalid phone number. Provide an international format like +15551234567."
            await self._emit_status(__event_emitter__, error_message, status="error")
            return error_message

        url = f"{self.API_BASE}/{self.valves.whatsapp_phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": cleaned_to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }

        status_code, data = await self._request("POST", url, payload)
        if status_code is None:
            error_message = "WhatsApp API request failed. Please try again later."
            await self._emit_status(__event_emitter__, error_message, status="error")
            return error_message

        if status_code >= 400:
            error_message = self._format_error(status_code, data)
            await self._emit_status(__event_emitter__, error_message, status="error")
            return error_message

        message_id = self._extract_message_id(data)
        await self._emit_status(
            __event_emitter__, "WhatsApp template sent.", status="complete"
        )
        if message_id:
            return f"WhatsApp template sent successfully. Message ID: {message_id}"
        return "WhatsApp template sent successfully."

    async def get_message_templates(
        self,
        __user__: dict,
        __event_emitter__,
    ) -> str:
        user_label = self._user_label(__user__)
        await self._emit_status(
            __event_emitter__,
            f"Fetching WhatsApp templates{user_label}...",
            status="in_progress",
        )

        missing = self._missing_config(
            ["whatsapp_access_token", "whatsapp_business_account_id"]
        )
        if missing:
            error_message = f"Missing configuration: {', '.join(missing)}"
            await self._emit_status(__event_emitter__, error_message, status="error")
            return error_message

        url = (
            f"{self.API_BASE}/{self.valves.whatsapp_business_account_id}"
            "/message_templates"
        )

        status_code, data = await self._request("GET", url, None)
        if status_code is None:
            error_message = "WhatsApp API request failed. Please try again later."
            await self._emit_status(__event_emitter__, error_message, status="error")
            return error_message

        if status_code >= 400:
            error_message = self._format_error(status_code, data)
            await self._emit_status(__event_emitter__, error_message, status="error")
            return error_message

        templates = data.get("data", []) if isinstance(data, dict) else []
        if not templates:
            await self._emit_status(
                __event_emitter__, "No WhatsApp templates found.", status="complete"
            )
            return "No WhatsApp templates found."

        lines = ["Available WhatsApp templates:"]
        for template in templates:
            name = template.get("name", "unknown")
            language = template.get("language", "unknown")
            category = template.get("category", "unknown")
            status = template.get("status", "unknown")
            lines.append(f"- {name} ({language}) | {category} | {status}")

        await self._emit_status(
            __event_emitter__, "WhatsApp templates retrieved.", status="complete"
        )
        return "\n".join(lines)

    async def _request(
        self, method: str, url: str, payload: dict | None
    ) -> tuple[int | None, dict | None]:
        headers = {
            "Authorization": f"Bearer {self.valves.whatsapp_access_token}",
            "Content-Type": "application/json",
        }
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=30)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    method, url, json=payload, headers=headers
                ) as response:
                    data = await self._read_json(response)
                    return response.status, data
        except aiohttp.ClientError:
            return None, None

    async def _read_json(self, response) -> dict | None:
        try:
            return await response.json(content_type=None)
        except (ValueError, Exception):
            text = await response.text()
            return {"raw": text}

    def _format_error(self, status_code: int, data: dict | None) -> str:
        if not isinstance(data, dict):
            return f"WhatsApp API error (HTTP {status_code})."

        error = data.get("error") if isinstance(data.get("error"), dict) else {}
        message = error.get("message") or data.get("message") or "Unknown error"
        error_type = error.get("type")
        code = error.get("code")
        subcode = error.get("error_subcode")
        trace_id = error.get("fbtrace_id")

        parts = [f"WhatsApp API error (HTTP {status_code})", message]
        if error_type:
            parts.append(f"type={error_type}")
        if code:
            parts.append(f"code={code}")
        if subcode:
            parts.append(f"subcode={subcode}")
        if trace_id:
            parts.append(f"trace={trace_id}")
        return " | ".join(parts)

    def _normalize_phone_number(self, to: str) -> str:
        cleaned = re.sub(r"[\s\-()]", "", to or "").strip()
        if cleaned.startswith("00"):
            cleaned = f"+{cleaned[2:]}"
        elif cleaned and not cleaned.startswith("+"):
            cleaned = f"+{cleaned}"

        digits = cleaned[1:] if cleaned.startswith("+") else cleaned
        if not digits.isdigit():
            return ""
        return cleaned

    def _missing_config(self, fields: list[str]) -> list[str]:
        missing = []
        for field in fields:
            if not getattr(self.valves, field, None):
                missing.append(field)
        return missing

    def _extract_message_id(self, data: dict | None) -> str | None:
        if not isinstance(data, dict):
            return None
        messages = data.get("messages")
        if isinstance(messages, list) and messages:
            message_id = messages[0].get("id")
            if isinstance(message_id, str):
                return message_id
        return None

    def _user_label(self, user: dict) -> str:
        name = (user or {}).get("name") or (user or {}).get("username")
        if not name:
            return ""
        return f" for {name}"

    async def _emit_status(
        self, event_emitter, description: str, status: str = "in_progress"
    ) -> None:
        if not event_emitter:
            return
        await event_emitter(
            {
                "type": "status",
                "data": {
                    "description": description,
                    "status": status,
                },
            }
        )
