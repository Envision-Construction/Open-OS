"""
title: Slack
author: Avi Reddy
version: 0.1.0
license: MIT
description: Send, search, and read Slack messages using Bot Token
required_pip_packages: slack_sdk aiohttp
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel


class Tools:
    class Valves(BaseModel):
        slack_bot_token: str = ""  # xoxb-... token
        slack_user_token: str = ""
        dlp_proxy_url: str = "http://dlp-proxy:8080"

    def __init__(self) -> None:
        self.valves = self.Valves()
        self._user_cache: dict[str, str] = {}

    async def _ensure_tokens(self, __user__: dict | None = None) -> str | None:
        """Load Slack tokens from DLP proxy if valves are empty."""
        if self.valves.slack_bot_token:
            return None

        if not __user__:
            return "Slack bot token is not configured."

        user_id = __user__.get("id") or __user__.get("sub") or ""
        if not user_id:
            return "Cannot determine user ID for Slack config lookup."

        import aiohttp

        try:
            url = f"{self.valves.dlp_proxy_url}/oauth/tokens/{user_id}/full?provider=slack"
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return "Slack not connected. Use the Connect panel to link your Slack workspace."
                    data = await resp.json()
                    self.valves.slack_bot_token = data.get("bot_token") or data.get("access_token", "")
                    self.valves.slack_user_token = data.get("user_token", "")
        except Exception:
            return "Could not reach DLP proxy to load Slack tokens."

        if not self.valves.slack_bot_token:
            return "Slack not connected. Use the Connect panel to link your Slack workspace."
        return None

    async def send_message(
        self,
        channel: str,
        text: str,
        thread_ts: str = "",
        __user__: dict | None = None,
        __event_emitter__=None,
    ) -> str:
        err = await self._ensure_tokens(__user__)
        if err:
            return err

        await self._emit_status(
            __event_emitter__,
            "in_progress",
            f"Sending message to {channel}...",
        )

        from slack_sdk.web.async_client import AsyncWebClient
        from slack_sdk.errors import SlackApiError

        client = AsyncWebClient(token=self.valves.slack_bot_token)

        try:
            channel_id, channel_name = await self._resolve_channel_id(client, channel)
            if not channel_id:
                await self._emit_status(
                    __event_emitter__,
                    "error",
                    f"Channel not found: {channel}",
                )
                return f"Channel not found: {channel}"

            response = await client.chat_postMessage(
                channel=channel_id,
                text=text,
                thread_ts=thread_ts or None,
            )
            message = response.get("message", {})
            sender = await self._resolve_sender_name(client, message)
            timestamp = self._format_ts(message.get("ts") or response.get("ts"))
            display_channel = channel_name or channel
            formatted = f"{timestamp} — {sender} in {display_channel}: {message.get('text', text)}"

            await self._emit_status(
                __event_emitter__,
                "complete",
                "Message sent.",
            )
            return formatted
        except Exception as exc:
            error = exc.response.get("error", "unknown_error")
            await self._emit_status(
                __event_emitter__,
                "error",
                f"Slack API error: {error}",
            )
            return f"Slack API error: {error}"

    async def search_messages(
        self,
        query: str,
        max_results: int = 10,
        __user__: dict | None = None,
        __event_emitter__=None,
    ) -> str:
        await self._ensure_tokens(__user__)
        if not self.valves.slack_user_token:
            return "Slack user token is required for search (search:read). Re-connect Slack with user scopes."

        await self._emit_status(
            __event_emitter__,
            "in_progress",
            f"Searching Slack for: {query}",
        )

        from slack_sdk.web.async_client import AsyncWebClient

        client = AsyncWebClient(token=self.valves.slack_user_token)

        try:
            response = await client.search_messages(query=query, count=max_results)
            matches = response.get("messages", {}).get("matches", [])

            if not matches:
                await self._emit_status(
                    __event_emitter__,
                    "complete",
                    "No results found.",
                )
                return "No results found."

            lines: list[str] = []
            for match in matches[:max_results]:
                timestamp = self._format_ts(match.get("ts"))
                channel_info = match.get("channel", {})
                channel_name = channel_info.get("name", "unknown")
                sender = await self._resolve_sender_name(client, match)
                text = match.get("text", "")
                lines.append(f"{timestamp} — {sender} in #{channel_name}: {text}")

            await self._emit_status(
                __event_emitter__,
                "complete",
                f"Found {len(lines)} messages.",
            )
            return "\n".join(lines)
        except Exception as exc:
            error = exc.response.get("error", "unknown_error")
            await self._emit_status(
                __event_emitter__,
                "error",
                f"Slack API error: {error}",
            )
            return f"Slack API error: {error}"

    async def read_channel_history(
        self,
        channel: str,
        limit: int = 20,
        __user__: dict | None = None,
        __event_emitter__=None,
    ) -> str:
        err = await self._ensure_tokens(__user__)
        if err:
            return err

        await self._emit_status(
            __event_emitter__,
            "in_progress",
            f"Reading messages from {channel}...",
        )

        from slack_sdk.web.async_client import AsyncWebClient

        client = AsyncWebClient(token=self.valves.slack_bot_token)

        try:
            channel_id, channel_name = await self._resolve_channel_id(client, channel)
            if not channel_id:
                await self._emit_status(
                    __event_emitter__,
                    "error",
                    f"Channel not found: {channel}",
                )
                return f"Channel not found: {channel}"

            response = await client.conversations_history(
                channel=channel_id, limit=limit
            )
            messages = response.get("messages", [])
            if not messages:
                await self._emit_status(
                    __event_emitter__,
                    "complete",
                    "No messages found.",
                )
                return "No messages found."

            lines: list[str] = []
            display_channel = channel_name or channel
            for message in messages:
                sender = await self._resolve_sender_name(client, message)
                timestamp = self._format_ts(message.get("ts"))
                text = message.get("text", "")
                lines.append(f"{timestamp} — {sender} in {display_channel}: {text}")

            await self._emit_status(
                __event_emitter__,
                "complete",
                f"Loaded {len(lines)} messages.",
            )
            return "\n".join(lines)
        except Exception as exc:
            error = str(exc)
            await self._emit_status(
                __event_emitter__,
                "error",
                f"Slack API error: {error}",
            )
            return f"Slack API error: {error}"

    async def list_channels(
        self,
        __user__: dict | None = None,
        __event_emitter__=None,
    ) -> str:
        err = await self._ensure_tokens(__user__)
        if err:
            return err

        await self._emit_status(
            __event_emitter__,
            "in_progress",
            "Listing channels...",
        )

        from slack_sdk.web.async_client import AsyncWebClient

        client = AsyncWebClient(token=self.valves.slack_bot_token)

        try:
            channels: list[dict[str, Any]] = []
            cursor = None
            while True:
                response = await client.conversations_list(
                    exclude_archived=True,
                    limit=200,
                    cursor=cursor,
                    types="public_channel,private_channel,mpim,im",
                )
                for item in response.get("channels", []):
                    if (
                        item.get("is_member")
                        or item.get("is_im")
                        or item.get("is_mpim")
                    ):
                        channels.append(item)
                cursor = response.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break

            if not channels:
                await self._emit_status(
                    __event_emitter__,
                    "complete",
                    "No channels found.",
                )
                return "No channels found."

            lines = []
            for channel in channels:
                name = channel.get("name") or channel.get("user") or "unknown"
                channel_id = channel.get("id", "unknown")
                is_private = channel.get("is_private", False)
                prefix = (
                    "#" if channel.get("is_channel") or channel.get("is_group") else ""
                )
                privacy = "private" if is_private else "public"
                lines.append(f"{prefix}{name} ({channel_id}) — {privacy}")

            await self._emit_status(
                __event_emitter__,
                "complete",
                f"Found {len(lines)} channels.",
            )
            return "\n".join(lines)
        except Exception as exc:
            error = exc.response.get("error", "unknown_error")
            await self._emit_status(
                __event_emitter__,
                "error",
                f"Slack API error: {error}",
            )
            return f"Slack API error: {error}"

    async def _resolve_channel_id(
        self,
        client: Any,
        channel: str,
    ) -> tuple[str | None, str | None]:
        if channel.startswith(("C", "D", "G")):
            return channel, None

        channel_name = channel.lstrip("#")
        cursor = None
        while True:
            response = await client.conversations_list(
                exclude_archived=True,
                limit=200,
                cursor=cursor,
                types="public_channel,private_channel",
            )
            for item in response.get("channels", []):
                if (
                    item.get("name") == channel_name
                    or item.get("name_normalized") == channel_name
                ):
                    return item.get("id"), item.get("name")
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        return None, None

    async def _resolve_sender_name(self, client: Any, message: dict[str, Any]) -> str:
        if message.get("user"):
            return await self._get_user_name(client, message["user"])

        if message.get("username"):
            return str(message.get("username"))

        bot_profile = message.get("bot_profile") or {}
        if bot_profile.get("name"):
            return str(bot_profile.get("name"))

        if message.get("bot_id"):
            return f"bot:{message['bot_id']}"

        return "unknown"

    async def _get_user_name(self, client: Any, user_id: str) -> str:
        if user_id in self._user_cache:
            return self._user_cache[user_id]

        response = await client.users_info(user=user_id)
        user = response.get("user", {})
        profile = user.get("profile", {})
        name = (
            profile.get("display_name")
            or profile.get("real_name")
            or user.get("name")
            or user_id
        )
        self._user_cache[user_id] = name
        return name

    def _format_ts(self, ts: str | None) -> str:
        if not ts:
            return "unknown_time"

        try:
            timestamp = float(ts)
        except (TypeError, ValueError):
            return str(ts)

        return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S %Z"
        )

    async def _emit_status(
        self, __event_emitter__, status: str, description: str
    ) -> None:
        if __event_emitter__ is None:
            return

        await __event_emitter__(
            {
                "type": "status",
                "data": {
                    "status": status,
                    "description": description,
                },
            }
        )
