"""
title: WhatsApp
author: Avi Reddy
version: 0.2.0
license: MIT
description: Send and read WhatsApp messages via Evolution API (personal WhatsApp)
required_pip_packages: aiohttp
"""

from __future__ import annotations

from pydantic import BaseModel


class Tools:
    class Valves(BaseModel):
        evolution_api_url: str = "http://evolution-api:8080"
        evolution_api_key: str = ""
        evolution_instance: str = ""
        dlp_proxy_url: str = "http://dlp-proxy:8080"

    def __init__(self) -> None:
        self.valves = self.Valves()

    def _headers(self) -> dict:
        return {
            "apikey": self.valves.evolution_api_key,
            "Content-Type": "application/json",
        }

    def _instance(self) -> str:
        return self.valves.evolution_instance

    async def _ensure_config(self, __user__: dict = None) -> str | None:
        """Try to load config from DLP proxy token store if valves are empty."""
        if self.valves.evolution_api_key and self.valves.evolution_instance:
            return None

        if not __user__:
            return "WhatsApp not configured. Set evolution_api_key and evolution_instance in tool settings."

        user_id = __user__.get("id") or __user__.get("sub") or ""
        if not user_id:
            return "Cannot determine user ID for WhatsApp config lookup."

        import aiohttp

        try:
            url = f"{self.valves.dlp_proxy_url}/oauth/tokens/{user_id}/full?provider=whatsapp"
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return "WhatsApp not connected. Use the Connect panel to link your WhatsApp."
                    data = await resp.json()
                    self.valves.evolution_api_url = data.get("evolution_api_url", self.valves.evolution_api_url)
                    self.valves.evolution_api_key = data.get("evolution_api_key", "")
                    self.valves.evolution_instance = data.get("instance_name", "")
        except Exception:
            return "Could not reach DLP proxy to load WhatsApp config."

        if not self.valves.evolution_api_key or not self.valves.evolution_instance:
            return "WhatsApp not connected. Use the Connect panel to link your WhatsApp."
        return None

    async def send_message(
        self,
        to: str,
        message: str,
        __user__: dict = None,
        __event_emitter__=None,
    ) -> str:
        """Send a WhatsApp message to a phone number. Use international format like 15551234567."""
        await self._emit(
            __event_emitter__, f"Sending WhatsApp message to {to}...", "in_progress"
        )

        err = await self._ensure_config(__user__)
        if err:
            await self._emit(__event_emitter__, err, "error")
            return err

        import aiohttp

        url = f"{self.valves.evolution_api_url}/message/sendText/{self._instance()}"
        # Strip + prefix — Evolution API expects bare number with country code
        number = to.strip().lstrip("+")
        payload = {
            "number": number,
            "text": message,
        }

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(url, json=payload, headers=self._headers()) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status >= 400:
                        error_msg = data.get("message", [data]) if isinstance(data, dict) else str(data)
                        msg = f"Evolution API error ({resp.status}): {error_msg}"
                        await self._emit(__event_emitter__, msg, "error")
                        return msg
                    msg_key = data.get("key", {}).get("id", "") if isinstance(data, dict) else ""

            await self._emit(__event_emitter__, "WhatsApp message sent.", "complete")
            if msg_key:
                return f"WhatsApp message sent. ID: {msg_key}"
            return "WhatsApp message sent successfully."
        except Exception as exc:
            msg = f"Failed to send WhatsApp message: {exc}"
            await self._emit(__event_emitter__, msg, "error")
            return msg

    async def get_contacts(
        self,
        __user__: dict = None,
        __event_emitter__=None,
    ) -> str:
        """List all WhatsApp contacts."""
        await self._emit(__event_emitter__, "Fetching WhatsApp contacts...", "in_progress")

        err = await self._ensure_config(__user__)
        if err:
            await self._emit(__event_emitter__, err, "error")
            return err

        import aiohttp

        url = f"{self.valves.evolution_api_url}/chat/contacts/{self._instance()}"

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(url, headers=self._headers()) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status >= 400:
                        msg = f"Evolution API error ({resp.status}): {data}"
                        await self._emit(__event_emitter__, msg, "error")
                        return msg

            if not data or not isinstance(data, list):
                await self._emit(__event_emitter__, "No contacts found.", "complete")
                return "No contacts found."

            lines = [f"WhatsApp contacts ({len(data)}):"]
            for contact in data[:100]:  # Cap at 100 for readability
                name = contact.get("pushName") or contact.get("name") or "Unknown"
                jid = contact.get("id") or contact.get("jid") or ""
                # Extract phone number from JID (format: 15551234567@s.whatsapp.net)
                number = jid.split("@")[0] if "@" in jid else jid
                lines.append(f"- {name}: +{number}")

            await self._emit(
                __event_emitter__, f"Found {len(data)} contacts.", "complete"
            )
            return "\n".join(lines)
        except Exception as exc:
            msg = f"Failed to fetch contacts: {exc}"
            await self._emit(__event_emitter__, msg, "error")
            return msg

    async def get_chat_history(
        self,
        contact_number: str,
        count: int = 20,
        __user__: dict = None,
        __event_emitter__=None,
    ) -> str:
        """Get message history with a WhatsApp contact. Provide phone number in international format (e.g. 15551234567)."""
        await self._emit(
            __event_emitter__,
            f"Fetching chat history with {contact_number}...",
            "in_progress",
        )

        err = await self._ensure_config(__user__)
        if err:
            await self._emit(__event_emitter__, err, "error")
            return err

        import aiohttp

        number = contact_number.strip().lstrip("+")
        jid = f"{number}@s.whatsapp.net"
        url = f"{self.valves.evolution_api_url}/chat/findMessages/{self._instance()}"
        payload = {
            "where": {"key": {"remoteJid": jid}},
            "limit": count,
        }

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(url, json=payload, headers=self._headers()) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status >= 400:
                        msg = f"Evolution API error ({resp.status}): {data}"
                        await self._emit(__event_emitter__, msg, "error")
                        return msg
                    messages = data if isinstance(data, list) else data.get("messages", data.get("data", []))
            if not messages:
                await self._emit(__event_emitter__, "No messages found.", "complete")
                return "No messages found."

            lines = [f"Chat history with +{number} ({len(messages)} messages):"]
            for msg in messages:
                key = msg.get("key", {})
                from_me = key.get("fromMe", False)
                sender = "You" if from_me else f"+{number}"
                text = (msg.get("message", {}) or {}).get("conversation") or \
                       (msg.get("message", {}) or {}).get("extendedTextMessage", {}).get("text") or \
                       "[media/other]"
                ts = msg.get("messageTimestamp", "")
                lines.append(f"[{ts}] {sender}: {text}")

            await self._emit(
                __event_emitter__,
                f"Loaded {len(messages)} messages.",
                "complete",
            )
            return "\n".join(lines)
        except Exception as exc:
            msg = f"Failed to fetch chat history: {exc}"
            await self._emit(__event_emitter__, msg, "error")
            return msg

    async def list_chats(
        self,
        __user__: dict = None,
        __event_emitter__=None,
    ) -> str:
        """List all WhatsApp chats (recent conversations)."""
        await self._emit(__event_emitter__, "Fetching WhatsApp chats...", "in_progress")

        err = await self._ensure_config(__user__)
        if err:
            await self._emit(__event_emitter__, err, "error")
            return err

        import aiohttp

        url = f"{self.valves.evolution_api_url}/chat/findChats/{self._instance()}"

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(url, headers=self._headers()) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status >= 400:
                        msg = f"Evolution API error ({resp.status}): {data}"
                        await self._emit(__event_emitter__, msg, "error")
                        return msg

            if not data or not isinstance(data, list):
                await self._emit(__event_emitter__, "No chats found.", "complete")
                return "No chats found."

            lines = [f"WhatsApp chats ({len(data)}):"]
            for chat in data[:50]:
                jid = chat.get("id") or chat.get("jid") or ""
                name = chat.get("name") or chat.get("pushName") or ""
                number = jid.split("@")[0] if "@" in jid else jid
                unread = chat.get("unreadCount", 0)
                label = name if name else f"+{number}"
                suffix = f" ({unread} unread)" if unread else ""
                lines.append(f"- {label}: +{number}{suffix}")

            await self._emit(
                __event_emitter__, f"Found {len(data)} chats.", "complete"
            )
            return "\n".join(lines)
        except Exception as exc:
            msg = f"Failed to fetch chats: {exc}"
            await self._emit(__event_emitter__, msg, "error")
            return msg

    async def _emit(self, emitter, description: str, status: str) -> None:
        if not emitter:
            return
        await emitter(
            {"type": "status", "data": {"description": description, "status": status}}
        )
