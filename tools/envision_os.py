"""
title: Envision OS
author: Avi Reddy
version: 1.0.0
license: MIT
description: Personal AI OS — Gmail, Calendar, Drive, Slack, WhatsApp + 390 Envision construction tools with OAuth connection flow
required_pip_packages: google-auth google-auth-oauthlib google-api-python-client aiohttp slack_sdk
"""

from pydantic import BaseModel, Field
from typing import Any, Callable, Optional
import asyncio
import json
import os
import time


class Tools:
    class Valves(BaseModel):
        google_client_id: str = Field(
            default=os.getenv("GOOGLE_CLIENT_ID", ""),
            description="Google OAuth Client ID",
        )
        google_client_secret: str = Field(
            default=os.getenv("GOOGLE_CLIENT_SECRET", ""),
            description="Google OAuth Client Secret",
        )
        google_refresh_token: str = Field(
            default=os.getenv("GOOGLE_REFRESH_TOKEN", ""),
            description="Google OAuth Refresh Token",
        )
        google_oauth_redirect_uri: str = Field(
            default=os.getenv(
                "GOOGLE_OAUTH_REDIRECT_URI", "urn:ietf:wg:oauth:2.0:oob"
            ),
            description="OAuth Redirect URI",
        )
        oauth_proxy_url: str = Field(
            default=os.getenv("OAUTH_PROXY_URL", "http://dlp-proxy:8080"),
            description="Internal OAuth proxy base URL",
        )
        slack_bot_token: str = Field(
            default=os.getenv("SLACK_BOT_TOKEN", ""),
            description="Slack Bot Token (xoxb-...)",
        )
        slack_user_token: str = Field(
            default=os.getenv("SLACK_USER_TOKEN", ""),
            description="Slack User Token for search",
        )
        whatsapp_access_token: str = Field(
            default=os.getenv("WHATSAPP_ACCESS_TOKEN", ""),
            description="WhatsApp Cloud API Access Token",
        )
        whatsapp_phone_number_id: str = Field(
            default=os.getenv("WHATSAPP_PHONE_ID", ""),
            description="WhatsApp Phone Number ID",
        )
        whatsapp_business_account_id: str = Field(
            default=os.getenv("WHATSAPP_BUSINESS_ID", ""),
            description="WhatsApp Business Account ID",
        )
        envision_mcp_url: str = Field(
            default=os.getenv(
                "ENVISION_MCP_URL",
                "https://envision-mcp-845049957105.us-central1.run.app/mcp",
            ),
            description="Envision MCP Gateway URL",
        )

    def __init__(self) -> None:
        self.valves = self.Valves()
        self._mcp_session_id = None
        self._mcp_initialized = False
        self._mcp_request_id = 0
        self._http_session = None
        self._init_lock = asyncio.Lock()
        self._mcp_init_failed_until = 0
        self._google_creds = None
        self._google_creds_expiry = 0

    def _make_emitter(self, __event_emitter__: Callable[[Any], Any]) -> Callable:
        if __event_emitter__ is None:
            async def emit(_: Any) -> None:
                return None
            return emit
        return __event_emitter__

    async def connect_google_account(
        self,
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Start the Google OAuth flow. Generates a clickable authorization URL. After authorizing in your browser, copy the code and use complete_google_connection to finish setup."""
        emit = self._make_emitter(__event_emitter__)

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {"description": "🔐 Preparing Google OAuth...", "done": False},
            }
        )
        try:
            if not self.valves.google_client_id or not self.valves.google_client_secret:
                await emit(
                    {
                        "type": "status",
                        "data": {
                            "description": "❌ Missing Google OAuth credentials",
                            "done": True,
                        },
                    }
                )
                return (
                    "❌ **Error:** Google OAuth Client ID/Secret not configured.\n\n"
                    "Please add them in Tool Settings and try again."
                )

            from google_auth_oauthlib.flow import Flow

            scopes = [
                "openid",
                "email",
                "profile",
                "https://www.googleapis.com/auth/gmail.modify",
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/drive",
            ]

            client_config = {
                "web": {
                    "client_id": self.valves.google_client_id,
                    "client_secret": self.valves.google_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.valves.google_oauth_redirect_uri],
                }
            }

            flow = Flow.from_client_config(client_config, scopes=scopes)
            flow.redirect_uri = self.valves.google_oauth_redirect_uri
            auth_url, _ = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
            )

            await emit(
                {
                    "type": "status",
                    "data": {"description": "✅ OAuth link ready", "done": True},
                }
            )
            return (
                "## 🔗 Connect Your Google Account\n\n"
                "Click the link below to authorize Envision OS:\n\n"
                f"**[→ Authorize with Google]({auth_url})**\n\n"
                "After authorizing, you'll see a code on the callback page.\n"
                'Copy it and say: **"Complete connection with code `PASTE_CODE_HERE`"**'
            )
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return (
                f"❌ **Error:** {str(e)}\n\n"
                "Please check your connection settings in Tool Settings."
            )

    async def complete_google_connection(
        self,
        authorization_code: str,
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Complete the Google OAuth flow by exchanging an authorization code for access tokens. Provide the code from the OAuth callback page."""
        emit = self._make_emitter(__event_emitter__)

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {
                    "description": "🔐 Exchanging authorization code...",
                    "done": False,
                },
            }
        )
        try:
            if not self.valves.google_client_id or not self.valves.google_client_secret:
                await emit(
                    {
                        "type": "status",
                        "data": {
                            "description": "❌ Missing Google OAuth credentials",
                            "done": True,
                        },
                    }
                )
                return (
                    "❌ **Error:** Google OAuth Client ID/Secret not configured.\n\n"
                    "Please add them in Tool Settings and try again."
                )

            from google_auth_oauthlib.flow import Flow

            scopes = [
                "openid",
                "email",
                "profile",
                "https://www.googleapis.com/auth/gmail.modify",
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/drive",
            ]

            client_config = {
                "web": {
                    "client_id": self.valves.google_client_id,
                    "client_secret": self.valves.google_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.valves.google_oauth_redirect_uri],
                }
            }

            flow = Flow.from_client_config(client_config, scopes=scopes)
            flow.redirect_uri = self.valves.google_oauth_redirect_uri
            flow.fetch_token(code=authorization_code)

            creds = flow.credentials
            refresh_token = creds.refresh_token
            if not refresh_token:
                await emit(
                    {
                        "type": "status",
                        "data": {
                            "description": "❌ No refresh token returned",
                            "done": True,
                        },
                    }
                )
                return (
                    "❌ **Error:** No refresh token returned.\n\n"
                    "Please revoke access in Google Account settings and try again.\n"
                    "Make sure the consent screen shows **Continue** and **Allow**."
                )

            await emit(
                {
                    "type": "status",
                    "data": {"description": "✅ Google connected", "done": True},
                }
            )
            return (
                "## ✅ Google Connected\n\n"
                "**Services enabled:** Gmail, Calendar, Drive\n\n"
                "Copy this refresh token to your Tool settings:\n\n"
                f"`{refresh_token}`"
            )
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return (
                f"❌ **Error:** {str(e)}\n\n"
                "Please check your connection settings in Tool Settings."
            )

    async def check_connections(
        self,
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Check which services are currently connected and configured."""
        emit = self._make_emitter(__event_emitter__)

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {"description": "🔌 Checking connections...", "done": False},
            }
        )
        try:
            user_id = self._extract_user_id(__user__)

            google_connected = False
            slack_connected = False
            whatsapp_connected = False

            if user_id:
                google_connected = bool(
                    await self._get_oauth_status(user_id=user_id, provider="google")
                )
                slack_connected = bool(
                    await self._get_oauth_status(user_id=user_id, provider="slack")
                )
                whatsapp_connected = bool(
                    await self._get_oauth_status(user_id=user_id, provider="whatsapp")
                )

            if not google_connected:
                google_connected = bool(
                    self.valves.google_client_id
                    and self.valves.google_client_secret
                    and self.valves.google_refresh_token
                )
            if not slack_connected:
                slack_connected = bool(
                    self.valves.slack_bot_token or self.valves.slack_user_token
                )
            if not whatsapp_connected:
                whatsapp_connected = bool(
                    self.valves.whatsapp_access_token
                    and self.valves.whatsapp_phone_number_id
                )

            envision_connected = bool(self.valves.envision_mcp_url)
            google_account_email = ""
            slack_account_label = ""
            if google_connected and user_id:
                google_profile = await self._get_google_profile(user_id=user_id)
                if google_profile:
                    google_account_email = google_profile.get("email", "")
            if slack_connected and user_id:
                slack_profile = await self._get_slack_profile(user_id=user_id)
                if slack_profile:
                    slack_account_label = (
                        slack_profile.get("matched_email")
                        or slack_profile.get("matched_name")
                        or slack_profile.get("email")
                        or slack_profile.get("real_name")
                        or slack_profile.get("user")
                        or ""
                    )
                    if (
                        slack_profile.get("team")
                        and slack_account_label
                        and slack_profile.get("team")
                        not in slack_account_label
                    ):
                        slack_account_label = (
                            f"{slack_account_label} @ {slack_profile.get('team')}"
                        )

            def status_label(is_connected: bool) -> str:
                return "✅ Connected" if is_connected else "❌ Not configured"

            google_status = status_label(google_connected)
            if google_account_email:
                google_status = f"{google_status} ({google_account_email})"
            slack_status = status_label(slack_connected)
            if slack_account_label:
                slack_status = f"{slack_status} ({slack_account_label})"

            await emit(
                {
                    "type": "status",
                    "data": {"description": "✅ Connection status ready", "done": True},
                }
            )
            return (
                "## 🔌 Connection Status\n\n"
                "| Service | Status |\n"
                "|---------|--------|\n"
                f"| Google (Gmail, Calendar, Drive) | {google_status} |\n"
                f"| Slack | {slack_status} |\n"
                f"| WhatsApp | {status_label(whatsapp_connected)} |\n"
                f"| Envision MCP | {status_label(envision_connected)} |"
            )
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return (
                f"❌ **Error:** {str(e)}\n\n"
                "Please check your connection settings in Tool Settings."
            )

    async def get_connected_google_account(
        self,
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Return the Google account currently connected for this signed-in user. Use this when asked which Google account is connected."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {"description": "🔎 Checking connected Google account...", "done": False},
            }
        )
        try:
            user_id = self._extract_user_id(__user__)
            if not user_id:
                await emit(
                    {
                        "type": "status",
                        "data": {"description": "❌ Missing user context", "done": True},
                    }
                )
                return (
                    "❌ **Error:** Could not determine the current user context.\n\n"
                    "Please refresh and try again."
                )

            google_status = await self._get_oauth_status(
                user_id=user_id, provider="google"
            )
            if not google_status:
                await emit(
                    {
                        "type": "status",
                        "data": {"description": "❌ Google not connected", "done": True},
                    }
                )
                return (
                    "Google is not connected for this user.\n\n"
                    "Click **Connect** for Google Workspace first."
                )

            profile = await self._get_google_profile(user_id=user_id)
            if not profile:
                await emit(
                    {
                        "type": "status",
                        "data": {"description": "⚠️ Connected but profile unavailable", "done": True},
                    }
                )
                return (
                    "Google is connected, but I could not read the account profile right now.\n\n"
                    "Please try again in a few seconds."
                )

            email = profile.get("email", "(unknown)")
            verified = bool(profile.get("verified_email"))
            name = profile.get("name", "")

            await emit(
                {
                    "type": "status",
                    "data": {"description": "✅ Connected account found", "done": True},
                }
            )
            if name:
                return (
                    f"Connected Google account: **{email}**\n"
                    f"Name: **{name}**\n"
                    f"Verified: **{'Yes' if verified else 'No'}**"
                )
            return (
                f"Connected Google account: **{email}**\n"
                f"Verified: **{'Yes' if verified else 'No'}**"
            )
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return f"❌ **Error:** {str(e)}"

    async def get_connected_slack_account(
        self,
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Return the Slack account currently connected for this signed-in user."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {
                    "description": "🔎 Checking connected Slack account...",
                    "done": False,
                },
            }
        )
        try:
            user_id = self._extract_user_id(__user__)
            if not user_id:
                await emit(
                    {
                        "type": "status",
                        "data": {"description": "❌ Missing user context", "done": True},
                    }
                )
                return (
                    "❌ **Error:** Could not determine the current user context.\n\n"
                    "Please refresh and try again."
                )

            slack_status = await self._get_oauth_status(user_id=user_id, provider="slack")
            if not slack_status:
                await emit(
                    {
                        "type": "status",
                        "data": {"description": "❌ Slack not connected", "done": True},
                    }
                )
                return (
                    "Slack is not connected for this user.\n\n"
                    "Click **Connect** for Slack first."
                )

            app_user_name, app_user_email = self._extract_user_identity(__user__)
            if not app_user_email:
                google_profile = await self._get_google_profile(user_id=user_id)
                if google_profile:
                    app_user_email = (google_profile.get("email") or "").strip()
                    if not app_user_name:
                        app_user_name = (google_profile.get("name") or "").strip()

            slack_profile = await self._get_slack_profile(
                user_id=user_id, preferred_email=app_user_email
            )
            if not slack_profile:
                await emit(
                    {
                        "type": "status",
                        "data": {
                            "description": "⚠️ Connected but profile unavailable",
                            "done": True,
                        },
                    }
                )
                return (
                    "Slack is connected, but I could not read the account profile right now.\n\n"
                    "Please try again in a few seconds."
                )

            user_name = (
                slack_profile.get("email")
                or slack_profile.get("real_name")
                or slack_profile.get("user")
                or "(unknown)"
            )
            team_name = slack_profile.get("team", "")
            workspace_url = slack_profile.get("url", "")
            matched_email = slack_profile.get("matched_email", "")
            matched_name = slack_profile.get("matched_name", "")

            await emit(
                {
                    "type": "status",
                    "data": {"description": "✅ Connected Slack account found", "done": True},
                }
            )
            lines = []
            if matched_email or matched_name:
                who = matched_email or matched_name
                lines.append(f"Connected Slack account: **{who}**")
            elif app_user_email or app_user_name:
                who = app_user_email or app_user_name
                lines.append(f"Connected Slack account: **{who}**")
            else:
                lines.append(f"Connected Slack account: **{user_name}**")

            if team_name:
                lines.append(f"Workspace: **{team_name}**")
            if workspace_url:
                lines.append(f"URL: {workspace_url}")
            if app_user_name or app_user_email:
                who = app_user_name or app_user_email
                if app_user_name and app_user_email:
                    who = f"{app_user_name} ({app_user_email})"
                lines.append(f"Authorized app user: **{who}**")
            return "\n".join(lines)
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return f"❌ **Error:** {str(e)}"

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = "",
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Send an email via Gmail. Supports plain text and CC recipients (comma-separated)."""
        emit = self._make_emitter(__event_emitter__)

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {"description": "✉️ Sending email...", "done": False},
            }
        )
        try:
            user_id = self._extract_user_id(__user__)
            creds = await self._get_google_creds(user_id=user_id)
            if not creds:
                await emit(
                    {
                        "type": "status",
                        "data": {
                            "description": "❌ Google not connected",
                            "done": True,
                        },
                    }
                )
                return (
                    "❌ **Error:** Google is not connected.\n\n"
                    "Run **connect_google_account** first."
                )

            import base64
            from email.mime.text import MIMEText
            from googleapiclient.discovery import build

            service = build("gmail", "v1", credentials=creds)

            message = MIMEText(body, "plain", "utf-8")
            message["to"] = to
            if cc:
                message["cc"] = cc
            message["subject"] = subject

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            loop = asyncio.get_running_loop()
            request = service.users().messages().send(
                userId="me", body={"raw": raw_message}
            )
            await loop.run_in_executor(None, request.execute)

            await emit(
                {
                    "type": "status",
                    "data": {"description": "✅ Email sent", "done": True},
                }
            )
            return f"✅ **Email sent** to {to}\n**Subject:** {subject}"
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return (
                f"❌ **Error:** {str(e)}\n\n"
                "Please check your connection settings in Tool Settings."
            )

    async def search_emails(
        self,
        query: str,
        max_results: int = 10,
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Search Gmail emails. Use Gmail search syntax (from:, to:, subject:, has:attachment, after:, before:, is:unread). For project-wide latest communication questions, this automatically routes to a cross-source digest."""
        emit = self._make_emitter(__event_emitter__)

        __user__ = __user__ or {}
        if self._is_latest_project_communication_query(query or ""):
            project_hint = self._extract_project_hint_from_text(query or "")
            if project_hint:
                return await self.ask_envision(
                    question=f"What is the latest communication regarding {project_hint}?",
                    project_name=project_hint,
                    __user__=__user__,
                    __event_emitter__=emit,
                )

        await emit(
            {
                "type": "status",
                "data": {"description": "🔍 Searching emails...", "done": False},
            }
        )
        try:
            user_id = self._extract_user_id(__user__)
            creds = await self._get_google_creds(user_id=user_id)
            if not creds:
                await emit(
                    {
                        "type": "status",
                        "data": {
                            "description": "❌ Google not connected",
                            "done": True,
                        },
                    }
                )
                return (
                    "❌ **Error:** Google is not connected.\n\n"
                    "Run **connect_google_account** first."
                )

            from email.utils import parsedate_to_datetime
            from googleapiclient.discovery import build

            service = build("gmail", "v1", credentials=creds)

            loop = asyncio.get_running_loop()
            request = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
            )
            response = await loop.run_in_executor(None, request.execute)
            messages = response.get("messages", [])
            if not messages:
                await emit(
                    {
                        "type": "status",
                        "data": {"description": "✅ No emails found", "done": True},
                    }
                )
                return f"No emails found for query: {query}"

            rows = [
                "| # | From | Subject | Date | ID |",
                "|---|------|---------|------|----|",
            ]

            def get_header(headers: list[dict], name: str) -> str:
                for header in headers:
                    if header.get("name", "").lower() == name.lower():
                        return header.get("value", "")
                return ""

            for index, message in enumerate(messages, start=1):
                message_id = message.get("id", "")
                request = (
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=message_id,
                        format="metadata",
                        metadataHeaders=["Subject", "From", "Date"],
                    )
                )
                detail = await loop.run_in_executor(None, request.execute)
                headers = detail.get("payload", {}).get("headers", [])
                subject = get_header(headers, "Subject") or "(no subject)"
                sender = get_header(headers, "From") or "(unknown sender)"
                date_raw = get_header(headers, "Date")
                date_display = date_raw
                if date_raw:
                    try:
                        date_display = parsedate_to_datetime(date_raw).strftime("%b %d")
                    except Exception:
                        date_display = date_raw

                safe_subject = subject.replace("\n", " ").replace("|", "\\|")
                safe_sender = sender.replace("\n", " ").replace("|", "\\|")
                rows.append(
                    f"| {index} | {safe_sender} | {safe_subject} | {date_display} | `{message_id}` |"
                )

            await emit(
                {
                    "type": "status",
                    "data": {
                        "description": f"✅ Found {len(messages)} emails",
                        "done": True,
                    },
                }
            )
            return f'## 📧 Search Results: "{query}"\n\n' + "\n".join(rows)
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return (
                f"❌ **Error:** {str(e)}\n\n"
                "Please check your connection settings in Tool Settings."
            )

    async def read_email(
        self,
        message_id: str,
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Read the full content of a specific email by its message ID."""
        emit = self._make_emitter(__event_emitter__)

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {"description": "📨 Loading email...", "done": False},
            }
        )
        try:
            user_id = self._extract_user_id(__user__)
            creds = await self._get_google_creds(user_id=user_id)
            if not creds:
                await emit(
                    {
                        "type": "status",
                        "data": {
                            "description": "❌ Google not connected",
                            "done": True,
                        },
                    }
                )
                return (
                    "❌ **Error:** Google is not connected.\n\n"
                    "Run **connect_google_account** first."
                )

            import base64
            from email.utils import parsedate_to_datetime
            from googleapiclient.discovery import build

            service = build("gmail", "v1", credentials=creds)

            loop = asyncio.get_running_loop()
            request = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
            )
            message = await loop.run_in_executor(None, request.execute)
            payload = message.get("payload", {})
            headers = payload.get("headers", [])

            def get_header(name: str) -> str:
                for header in headers:
                    if header.get("name", "").lower() == name.lower():
                        return header.get("value", "")
                return ""

            def decode_body(data: Optional[str]) -> str:
                if not data:
                    return ""
                decoded_bytes = base64.urlsafe_b64decode(data.encode("utf-8"))
                try:
                    return decoded_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    return decoded_bytes.decode("latin-1", errors="replace")

            def extract_plain_text(payload_dict: dict) -> str:
                if not payload_dict:
                    return ""
                body_data = payload_dict.get("body", {}).get("data")
                if body_data:
                    return decode_body(body_data)

                parts = payload_dict.get("parts", []) or []
                for part in parts:
                    if part.get("mimeType") == "text/plain":
                        return decode_body(part.get("body", {}).get("data"))

                for part in parts:
                    for subpart in part.get("parts", []) or []:
                        if subpart.get("mimeType") == "text/plain":
                            return decode_body(subpart.get("body", {}).get("data"))

                return ""

            subject = get_header("Subject") or "(no subject)"
            sender = get_header("From") or "(unknown sender)"
            recipient = get_header("To") or "(unknown recipient)"
            date_raw = get_header("Date") or ""
            date_display = date_raw
            if date_raw:
                try:
                    date_display = parsedate_to_datetime(date_raw).strftime(
                        "%B %d, %Y %I:%M %p"
                    )
                except Exception:
                    date_display = date_raw

            body_text = extract_plain_text(payload) or message.get("snippet", "")

            await emit(
                {
                    "type": "status",
                    "data": {"description": "✅ Email loaded", "done": True},
                }
            )
            return (
                "## 📨 Email Details\n\n"
                f"**From:** {sender}\n"
                f"**To:** {recipient}\n"
                f"**Date:** {date_display}\n"
                f"**Subject:** {subject}\n\n"
                "---\n\n"
                f"{body_text}"
            )
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return (
                f"❌ **Error:** {str(e)}\n\n"
                "Please check your connection settings in Tool Settings."
            )

    async def list_events(
        self,
        days_ahead: int = 7,
        max_results: int = 20,
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """List upcoming Google Calendar events for the next N days."""
        emit = self._make_emitter(__event_emitter__)

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {"description": "📅 Loading calendar events...", "done": False},
            }
        )
        try:
            user_id = self._extract_user_id(__user__)
            creds = await self._get_google_creds(user_id=user_id)
            if not creds:
                await emit(
                    {
                        "type": "status",
                        "data": {
                            "description": "❌ Google not connected",
                            "done": True,
                        },
                    }
                )
                return (
                    "❌ **Error:** Google is not connected.\n\n"
                    "Run **connect_google_account** first."
                )

            from datetime import datetime, timedelta, timezone
            from googleapiclient.discovery import build

            service = build("calendar", "v3", credentials=creds)

            now = datetime.now(timezone.utc)
            time_min = now.isoformat()
            time_max = (now + timedelta(days=days_ahead)).isoformat()

            loop = asyncio.get_running_loop()
            request = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                )
            )
            response = await loop.run_in_executor(None, request.execute)
            events = response.get("items", [])
            if not events:
                await emit(
                    {
                        "type": "status",
                        "data": {"description": "✅ No upcoming events", "done": True},
                    }
                )
                return "No upcoming events found."

            def parse_iso(value: str) -> Optional[datetime]:
                if not value:
                    return None
                try:
                    if value.endswith("Z"):
                        return datetime.fromisoformat(value.replace("Z", "+00:00"))
                    return datetime.fromisoformat(value)
                except Exception:
                    return None

            rows = [
                "| # | When | Event | Location |",
                "|---|------|-------|----------|",
            ]

            for index, event in enumerate(events, start=1):
                start = event.get("start", {})
                end = event.get("end", {})
                summary = event.get("summary", "(no title)")
                location = event.get("location", "")

                when_display = "(time unavailable)"
                if "dateTime" in start:
                    start_dt = parse_iso(start.get("dateTime"))
                    end_dt = parse_iso(end.get("dateTime"))
                    if start_dt:
                        day = start_dt.strftime("%a, %b %d")
                        start_time = start_dt.strftime("%I:%M %p").lstrip("0")
                        end_time = ""
                        if end_dt:
                            end_time = end_dt.strftime("%I:%M %p").lstrip("0")
                        when_display = f"{day} · {start_time} – {end_time}".strip()
                elif "date" in start:
                    start_dt = parse_iso(start.get("date"))
                    if start_dt:
                        day = start_dt.strftime("%a, %b %d")
                        when_display = f"{day} · All day"

                safe_summary = summary.replace("\n", " ").replace("|", "\\|")
                safe_location = location.replace("\n", " ").replace("|", "\\|")
                rows.append(
                    f"| {index} | {when_display} | {safe_summary} | {safe_location} |"
                )

            await emit(
                {
                    "type": "status",
                    "data": {"description": "✅ Events loaded", "done": True},
                }
            )
            return f"## 📅 Upcoming Events (next {days_ahead} days)\n\n" + "\n".join(
                rows
            )
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return (
                f"❌ **Error:** {str(e)}\n\n"
                "Please check your connection settings in Tool Settings."
            )

    async def create_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        description: str = "",
        attendees: str = "",
        location: str = "",
        timezone: str = "America/Chicago",
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Create a Google Calendar event. Times in ISO 8601 format. Attendees as comma-separated emails."""
        emit = self._make_emitter(__event_emitter__)

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {"description": "📅 Creating event...", "done": False},
            }
        )
        try:
            user_id = self._extract_user_id(__user__)
            creds = await self._get_google_creds(user_id=user_id)
            if not creds:
                await emit(
                    {
                        "type": "status",
                        "data": {
                            "description": "❌ Google not connected",
                            "done": True,
                        },
                    }
                )
                return (
                    "❌ **Error:** Google is not connected.\n\n"
                    "Run **connect_google_account** first."
                )

            from datetime import datetime
            from googleapiclient.discovery import build

            service = build("calendar", "v3", credentials=creds)

            attendee_list = []
            for email in attendees.split(","):
                email = email.strip()
                if email:
                    attendee_list.append({"email": email})

            event = {
                "summary": title,
                "description": description,
                "location": location,
                "start": {"dateTime": start_time, "timeZone": timezone},
                "end": {"dateTime": end_time, "timeZone": timezone},
            }
            if attendee_list:
                event["attendees"] = attendee_list

            loop = asyncio.get_running_loop()
            request = service.events().insert(calendarId="primary", body=event)
            await loop.run_in_executor(None, request.execute)

            def parse_iso(value: str) -> Optional[datetime]:
                if not value:
                    return None
                try:
                    if value.endswith("Z"):
                        return datetime.fromisoformat(value.replace("Z", "+00:00"))
                    return datetime.fromisoformat(value)
                except Exception:
                    return None

            start_dt = parse_iso(start_time)
            end_dt = parse_iso(end_time)
            if start_dt and end_dt:
                day = start_dt.strftime("%a, %b %d")
                start_fmt = start_dt.strftime("%I:%M %p").lstrip("0")
                end_fmt = end_dt.strftime("%I:%M %p").lstrip("0")
                time_display = f"{day} · {start_fmt} – {end_fmt}"
            else:
                time_display = f"{start_time} → {end_time}"

            location_display = location or "(no location)"

            await emit(
                {
                    "type": "status",
                    "data": {"description": "✅ Event created", "done": True},
                }
            )
            return (
                f"✅ **Event created:** {title}\n"
                f"📅 {time_display}\n"
                f"📍 {location_display}"
            )
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return (
                f"❌ **Error:** {str(e)}\n\n"
                "Please check your connection settings in Tool Settings."
            )

    async def search_drive(
        self,
        query: str,
        max_results: int = 20,
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Search Google Drive for files by name or content."""
        emit = self._make_emitter(__event_emitter__)

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {"description": "📁 Searching Drive...", "done": False},
            }
        )
        try:
            user_id = self._extract_user_id(__user__)
            creds = await self._get_google_creds(user_id=user_id)
            if not creds:
                await emit(
                    {
                        "type": "status",
                        "data": {
                            "description": "❌ Google not connected",
                            "done": True,
                        },
                    }
                )
                return (
                    "❌ **Error:** Google is not connected.\n\n"
                    "Run **connect_google_account** first."
                )

            from datetime import datetime
            from googleapiclient.discovery import build

            service = build("drive", "v3", credentials=creds)

            safe_query = query.replace("'", "\\'")
            q = f"name contains '{safe_query}' or fullText contains '{safe_query}'"

            loop = asyncio.get_running_loop()
            request = (
                service.files()
                .list(
                    q=q,
                    pageSize=max_results,
                    fields="files(id, name, mimeType, modifiedTime, size)",
                )
            )
            response = await loop.run_in_executor(None, request.execute)
            files = response.get("files", [])
            if not files:
                await emit(
                    {
                        "type": "status",
                        "data": {"description": "✅ No files found", "done": True},
                    }
                )
                return f"No files found for query: {query}"

            def format_size(size_value: Optional[str]) -> str:
                if not size_value:
                    return "-"
                try:
                    size = int(size_value)
                except Exception:
                    return str(size_value)
                for unit in ["B", "KB", "MB", "GB", "TB"]:
                    if size < 1024:
                        return f"{size:.0f} {unit}"
                    size /= 1024
                return f"{size:.0f} PB"

            rows = [
                "| # | Name | Type | Modified | Size | ID |",
                "|---|------|------|----------|------|----|",
            ]

            for index, item in enumerate(files, start=1):
                name = item.get("name", "")
                mime_type = item.get("mimeType", "")
                modified_raw = item.get("modifiedTime", "")
                modified_display = modified_raw
                if modified_raw:
                    try:
                        if modified_raw.endswith("Z"):
                            dt = datetime.fromisoformat(
                                modified_raw.replace("Z", "+00:00")
                            )
                        else:
                            dt = datetime.fromisoformat(modified_raw)
                        modified_display = dt.strftime("%Y-%m-%d")
                    except Exception:
                        modified_display = modified_raw

                rows.append(
                    "| {index} | {name} | {mime} | {mod} | {size} | `{fid}` |".format(
                        index=index,
                        name=name.replace("|", "\\|"),
                        mime=mime_type.replace("|", "\\|"),
                        mod=modified_display,
                        size=format_size(item.get("size")),
                        fid=item.get("id", ""),
                    )
                )

            await emit(
                {
                    "type": "status",
                    "data": {
                        "description": f"✅ Found {len(files)} files",
                        "done": True,
                    },
                }
            )
            return f'## 📁 Drive Results: "{query}"\n\n' + "\n".join(rows)
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return (
                f"❌ **Error:** {str(e)}\n\n"
                "Please check your connection settings in Tool Settings."
            )

    async def read_drive_file(
        self,
        file_id: str,
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Read the text content of a Google Drive file. Automatically exports Google Docs/Sheets/Slides to text."""
        emit = self._make_emitter(__event_emitter__)

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {"description": "📄 Reading Drive file...", "done": False},
            }
        )
        try:
            user_id = self._extract_user_id(__user__)
            creds = await self._get_google_creds(user_id=user_id)
            if not creds:
                await emit(
                    {
                        "type": "status",
                        "data": {
                            "description": "❌ Google not connected",
                            "done": True,
                        },
                    }
                )
                return (
                    "❌ **Error:** Google is not connected.\n\n"
                    "Run **connect_google_account** first."
                )

            import io
            from datetime import datetime
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaIoBaseDownload

            service = build("drive", "v3", credentials=creds)

            loop = asyncio.get_running_loop()
            request = (
                service.files()
                .get(fileId=file_id, fields="id, name, mimeType, modifiedTime, size")
            )
            metadata = await loop.run_in_executor(None, request.execute)
            mime_type = metadata.get("mimeType", "")

            export_mime = None
            if mime_type == "application/vnd.google-apps.document":
                export_mime = "text/plain"
            elif mime_type == "application/vnd.google-apps.spreadsheet":
                export_mime = "text/csv"
            elif mime_type == "application/vnd.google-apps.presentation":
                export_mime = "text/plain"

            if export_mime:
                request = service.files().export(fileId=file_id, mimeType=export_mime)
            else:
                request = service.files().get_media(fileId=file_id)

            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)
            loop = asyncio.get_running_loop()
            def _download():
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            await loop.run_in_executor(None, _download)

            content_bytes = buffer.getvalue()
            try:
                content_text = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                content_text = content_bytes.decode("latin-1", errors="replace")

            if len(content_text) > 50000:
                content_text = content_text[:50000] + "\n\n...[truncated]"

            modified_raw = metadata.get("modifiedTime", "")
            modified_display = modified_raw
            if modified_raw:
                try:
                    if modified_raw.endswith("Z"):
                        dt = datetime.fromisoformat(modified_raw.replace("Z", "+00:00"))
                    else:
                        dt = datetime.fromisoformat(modified_raw)
                    modified_display = dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    modified_display = modified_raw

            await emit(
                {
                    "type": "status",
                    "data": {"description": "✅ File loaded", "done": True},
                }
            )
            return (
                "## 📄 Drive File\n\n"
                f"**Name:** {metadata.get('name', '')}\n"
                f"**ID:** {metadata.get('id', '')}\n"
                f"**Type:** {mime_type}\n"
                f"**Modified:** {modified_display}\n"
                f"**Size:** {metadata.get('size', '-')}\n\n"
                "---\n\n"
                "```text\n"
                f"{content_text or '(No text content)'}\n"
                "```"
            )
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return (
                f"❌ **Error:** {str(e)}\n\n"
                "Please check your connection settings in Tool Settings."
            )

    async def send_slack_message(
        self,
        channel: str,
        text: str,
        thread_ts: str = "",
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Send a Slack message to a channel or DM target. Supports channel name/ID, user ID, or Slack user profile URL."""
        emit = self._make_emitter(__event_emitter__)

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {"description": "💬 Sending Slack message...", "done": False},
            }
        )
        try:
            user_id = self._extract_user_id(__user__)
            token_payload = (
                await self._get_oauth_tokens(user_id=user_id, provider="slack")
                if user_id
                else None
            ) or {}
            slack_team_id = token_payload.get("team_id", "")
            slack_token = await self._get_slack_token(
                user_id=user_id, require_user_scope=True
            )
            if not slack_token:
                await emit(
                    {
                        "type": "status",
                        "data": {
                            "description": "❌ Slack not configured",
                            "done": True,
                        },
                    }
                )
                return (
                    "❌ **Error:** Slack is not connected.\n\n"
                    "Click **Connect** for Slack first."
                )

            import re
            from slack_sdk.web.async_client import AsyncWebClient

            client = AsyncWebClient(token=slack_token)

            def clean_target(value: str) -> str:
                return (value or "").strip()

            def clean_text(value: str) -> str:
                return (value or "").strip().strip('"').strip("'").strip()

            def split_target_and_message(target: str, body: str) -> tuple[str, str]:
                target_clean = clean_target(target)
                body_clean = clean_text(body)
                lower = target_clean.lower()

                # Allow natural-language inputs passed entirely via `channel`, e.g.
                # "to Sebastian Santander saying test in slack"
                if lower.startswith("to "):
                    target_clean = target_clean[3:].strip()
                    lower = target_clean.lower()
                if lower.startswith("dm "):
                    target_clean = target_clean[3:].strip()
                    lower = target_clean.lower()
                if lower.startswith("direct message to "):
                    target_clean = target_clean[len("direct message to ") :].strip()
                    lower = target_clean.lower()
                if lower.startswith("back to "):
                    target_clean = target_clean[len("back to ") :].strip()
                    lower = target_clean.lower()
                if lower.startswith("reply to "):
                    target_clean = target_clean[len("reply to ") :].strip()
                    lower = target_clean.lower()
                if lower.startswith("respond to "):
                    target_clean = target_clean[len("respond to ") :].strip()
                    lower = target_clean.lower()
                if lower.startswith("message back to "):
                    target_clean = target_clean[len("message back to ") :].strip()
                    lower = target_clean.lower()
                if lower.startswith("send to "):
                    target_clean = target_clean[len("send to ") :].strip()
                    lower = target_clean.lower()

                markers = [
                    " saying ",
                    " say ",
                    " with message ",
                    " message ",
                    " with text ",
                    " text ",
                ]
                for marker in markers:
                    idx = lower.find(marker)
                    if idx == -1:
                        continue
                    lhs = target_clean[:idx].strip(" ,:")
                    rhs = target_clean[idx + len(marker) :].strip()
                    if lhs:
                        target_clean = lhs
                    if rhs and not body_clean:
                        body_clean = rhs
                    break

                # Remove wrapping labels that LLM may include.
                for prefix in ("user ", "recipient ", "channel "):
                    if target_clean.lower().startswith(prefix):
                        target_clean = target_clean[len(prefix) :].strip()

                # Handle patterns like "back to Sebastian" after marker split.
                for prefix in ("back to ", "reply to ", "respond to "):
                    if target_clean.lower().startswith(prefix):
                        target_clean = target_clean[len(prefix) :].strip()

                return clean_target(target_clean), clean_text(body_clean)

            def normalize_name(value: str) -> str:
                return "".join(ch for ch in (value or "").lower() if ch.isalnum())

            def extract_slack_user_id(value: str) -> str:
                raw = clean_target(value)
                if raw.startswith("<@") and raw.endswith(">"):
                    raw = raw[2:-1]
                if raw.upper().startswith("U") and raw[1:].isalnum():
                    return raw.upper()
                match = re.search(r"/team/(U[A-Z0-9]+)", raw, flags=re.IGNORECASE)
                if match:
                    return match.group(1).upper()
                return ""

            async def resolve_user_target(target: str) -> tuple[str | None, str | None]:
                raw = clean_target(target)
                user_id_direct = extract_slack_user_id(raw)
                if user_id_direct:
                    try:
                        user_data = await client.users_info(user=user_id_direct)
                        user_obj = user_data.get("user", {}) if user_data else {}
                        profile_obj = user_obj.get("profile", {}) if user_obj else {}
                        display = (
                            profile_obj.get("real_name")
                            or user_obj.get("real_name")
                            or profile_obj.get("display_name")
                            or user_obj.get("name")
                            or user_id_direct
                        )
                        return user_id_direct, display
                    except Exception:
                        return user_id_direct, user_id_direct

                if "@" in raw and "/" not in raw:
                    try:
                        lookup = await client.users_lookupByEmail(email=raw)
                        user_obj = lookup.get("user", {}) if lookup else {}
                        if user_obj and user_obj.get("id"):
                            profile_obj = user_obj.get("profile", {}) if user_obj else {}
                            display = (
                                profile_obj.get("real_name")
                                or user_obj.get("real_name")
                                or profile_obj.get("display_name")
                                or user_obj.get("name")
                                or raw
                            )
                            return user_obj.get("id"), display
                    except Exception:
                        pass

                needle = normalize_name(raw.lstrip("@"))
                if not needle:
                    return None, None

                best_id = None
                best_name = None
                cursor = None
                for _ in range(12):
                    kwargs = {"limit": 200, "cursor": cursor}
                    if slack_team_id:
                        kwargs["team_id"] = slack_team_id
                    resp = await client.users_list(**kwargs)
                    for member in resp.get("members", []) or []:
                        if member.get("deleted") or member.get("is_bot"):
                            continue
                        profile_obj = member.get("profile", {}) if member else {}
                        candidates = [
                            profile_obj.get("real_name", ""),
                            profile_obj.get("display_name", ""),
                            member.get("real_name", ""),
                            member.get("name", ""),
                            profile_obj.get("email", ""),
                        ]
                        exact = False
                        for item in candidates:
                            norm = normalize_name(item)
                            if not norm:
                                continue
                            if norm == needle:
                                exact = True
                                break
                            if needle in norm or norm in needle:
                                if not best_id:
                                    best_id = member.get("id")
                                    best_name = item
                        if exact:
                            resolved_id = member.get("id")
                            resolved_name = (
                                profile_obj.get("real_name")
                                or profile_obj.get("display_name")
                                or member.get("real_name")
                                or member.get("name")
                                or resolved_id
                            )
                            return resolved_id, resolved_name
                    cursor = (resp.get("response_metadata", {}) or {}).get("next_cursor")
                    if not cursor:
                        break
                if best_id:
                    return best_id, (best_name or best_id)
                return None, None

            async def open_dm_channel(user_slack_id: str, display_name: str = "") -> tuple[str | None, str | None]:
                if not user_slack_id:
                    return None, None
                open_kwargs = {"users": user_slack_id}
                if slack_team_id:
                    open_kwargs["team_id"] = slack_team_id
                try:
                    opened = await client.conversations_open(**open_kwargs)
                    channel_obj = opened.get("channel", {}) if opened else {}
                    dm_id = channel_obj.get("id")
                    if dm_id:
                        label = display_name or user_slack_id
                        return dm_id, f"DM:{label}"
                except Exception:
                    pass
                # Fallback: Slack may accept user-id as channel in some contexts.
                label = display_name or user_slack_id
                return user_slack_id, f"DM:{label}"

            async def resolve_channel_id(target: str) -> tuple[str | None, str | None]:
                target = clean_target(target)
                if target.startswith(("C", "D", "G")):
                    return target, None
                if target.upper().startswith("U") and target[1:].isalnum():
                    return await open_dm_channel(target.upper(), target.upper())
                extracted_user = extract_slack_user_id(target)
                if extracted_user:
                    return await open_dm_channel(extracted_user, extracted_user)
                channel_name = target.lstrip("#")
                cursor = None
                for _ in range(12):
                    list_kwargs = {
                        "exclude_archived": True,
                        "limit": 200,
                        "cursor": cursor,
                        "types": "public_channel,private_channel,mpim,im",
                    }
                    if slack_team_id:
                        list_kwargs["team_id"] = slack_team_id
                    response = await client.conversations_list(
                        **list_kwargs
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
                user_match_id, user_match_name = await resolve_user_target(target)
                if user_match_id:
                    return await open_dm_channel(user_match_id, user_match_name or target)
                return None, None

            channel, text = split_target_and_message(channel, text)
            if not text:
                await emit(
                    {
                        "type": "status",
                        "data": {
                            "description": "❌ Missing message text",
                            "done": True,
                        },
                    }
                )
                return "❌ **Error:** Missing message text."

            if not slack_team_id:
                try:
                    auth_data = await client.auth_test()
                    slack_team_id = auth_data.get("team_id", "") or slack_team_id
                except Exception:
                    pass

            channel_id, channel_name = await resolve_channel_id(channel)
            if not channel_id:
                await emit(
                    {
                        "type": "status",
                        "data": {"description": "❌ Channel not found", "done": True},
                    }
                )
                return f"❌ **Error:** Channel not found: {channel}"

            response = await client.chat_postMessage(
                channel=channel_id,
                text=text,
                thread_ts=thread_ts or None,
            )

            permalink = ""
            try:
                ts = response.get("ts")
                if ts:
                    link = await client.chat_getPermalink(
                        channel=channel_id,
                        message_ts=ts,
                    )
                    permalink = link.get("permalink", "")
            except Exception:
                permalink = ""

            display_channel = channel_name or channel
            await emit(
                {
                    "type": "status",
                    "data": {"description": "✅ Slack message sent", "done": True},
                }
            )
            if permalink:
                return f"✅ **Slack message sent** to {display_channel}\n{permalink}"
            return f"✅ **Slack message sent** to {display_channel}"
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return (
                f"❌ **Error:** {str(e)}\n\n"
                "Please check your connection settings in Tool Settings."
            )

    async def search_slack(
        self,
        query: str,
        max_results: int = 10,
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Search Slack messages. Uses search.messages when available, with fallback to conversations history."""
        emit = self._make_emitter(__event_emitter__)

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {"description": "🔍 Searching Slack...", "done": False},
            }
        )
        try:
            user_id = self._extract_user_id(__user__)
            user_tz_name = self._extract_user_timezone(__user__)
            query_lower = (query or "").lower()
            if (
                ("last" in query_lower or "latest" in query_lower or "recent" in query_lower)
                and ("message" in query_lower or "dm" in query_lower or "direct" in query_lower)
            ):
                return await self.get_latest_slack_messages(
                    max_results=max(1, min(max_results, 10)),
                    __user__=__user__,
                    __event_emitter__=emit,
                )

            token_payload = (
                await self._get_oauth_tokens(user_id=user_id, provider="slack")
                if user_id
                else None
            ) or {}
            slack_team_id = token_payload.get("team_id", "")
            slack_token = await self._get_slack_token(
                user_id=user_id, require_user_scope=True
            )
            if not slack_token:
                await emit(
                    {
                        "type": "status",
                        "data": {
                            "description": "❌ Slack not configured",
                            "done": True,
                        },
                    }
                )
                return (
                    "❌ **Error:** Slack is not connected.\n\n"
                    "Click **Connect** for Slack first."
                )

            from datetime import datetime, timezone
            from zoneinfo import ZoneInfo
            from slack_sdk.errors import SlackApiError
            from slack_sdk.web.async_client import AsyncWebClient

            try:
                local_tz = ZoneInfo(user_tz_name)
            except Exception:
                local_tz = timezone.utc

            client = AsyncWebClient(token=slack_token)
            matches = []
            used_fallback = False
            sender_cache = {}

            try:
                search_kwargs = {"query": query, "count": max_results}
                if slack_team_id:
                    search_kwargs["team_id"] = slack_team_id
                response = await client.search_messages(**search_kwargs)
                matches = response.get("messages", {}).get("matches", [])
            except SlackApiError as slack_err:
                err_code = (
                    (slack_err.response.data or {}).get("error", "")
                    if getattr(slack_err, "response", None)
                    else ""
                )
                # Bot-style token types cannot use search.messages. Fall back to
                # conversations.history scanning with local text filtering.
                if err_code in ("not_allowed_token_type", "missing_scope"):
                    used_fallback = True
                    needle = (query or "").strip().lower()

                    channel_cursor = None
                    channels = []
                    for _ in range(30):
                        list_kwargs = {
                            "exclude_archived": True,
                            "limit": 200,
                            "cursor": channel_cursor,
                            "types": "public_channel,private_channel,mpim,im",
                        }
                        if slack_team_id:
                            list_kwargs["team_id"] = slack_team_id
                        channel_resp = await client.conversations_list(**list_kwargs)
                        channels.extend(channel_resp.get("channels", []) or [])
                        channel_cursor = (
                            channel_resp.get("response_metadata", {}) or {}
                        ).get("next_cursor")
                        if not channel_cursor:
                            break

                    collected = []
                    for channel in channels:
                        channel_id = channel.get("id", "")
                        if not channel_id:
                            continue
                        try:
                            hist = await client.conversations_history(
                                channel=channel_id, limit=50
                            )
                        except SlackApiError:
                            continue
                        for message in hist.get("messages", []) or []:
                            text = (message.get("text") or "").strip()
                            if needle and needle not in text.lower():
                                continue
                            sender_id = message.get("user", "")
                            sender_name = await self._resolve_slack_user_display(
                                client, sender_id, sender_cache, team_id=slack_team_id
                            )
                            collected.append(
                                {
                                    "ts": message.get("ts", ""),
                                    "username": sender_name,
                                    "text": text,
                                    "channel": {
                                        "name": channel.get("name")
                                        or channel.get("id")
                                        or "unknown"
                                    },
                                }
                            )
                            if len(collected) >= max_results:
                                break
                        if len(collected) >= max_results:
                            break

                    matches = collected
                else:
                    raise

            if not matches:
                await emit(
                    {
                        "type": "status",
                        "data": {"description": "✅ No results", "done": True},
                    }
                )
                return "No Slack messages found."

            def format_ts(ts: str) -> str:
                try:
                    value = float(ts)
                    return datetime.fromtimestamp(value, tz=timezone.utc).astimezone(
                        local_tz
                    ).strftime(
                        "%Y-%m-%d %I:%M %p"
                    )
                except Exception:
                    return ts

            rows = [
                "| # | When | Channel | Sender | Text |",
                "|---|------|---------|--------|------|",
            ]

            for index, match in enumerate(matches[:max_results], start=1):
                channel_info = match.get("channel", {})
                channel_name = channel_info.get("name", "unknown")
                sender = match.get("username") or ""
                if not sender:
                    sender = await self._resolve_slack_user_display(
                        client,
                        match.get("user", ""),
                        sender_cache,
                        team_id=slack_team_id,
                    )
                text = await self._replace_slack_user_mentions(
                    match.get("text", ""),
                    client,
                    sender_cache,
                    team_id=slack_team_id,
                )
                text = text.replace("\n", " ")
                text = text.replace("|", "\\|")
                rows.append(
                    f"| {index} | {format_ts(match.get('ts', ''))} | #{channel_name} | {sender} | {text} |"
                )

            await emit(
                {
                    "type": "status",
                    "data": {"description": "✅ Slack search complete", "done": True},
                }
            )
            heading = f'## 💬 Slack Search Results: "{query}"'
            if used_fallback:
                heading += "\n\n_Using conversations history fallback (search API unavailable for this token type)._"
            heading += f"\n\n_All times shown in {user_tz_name}._"
            return heading + "\n\n" + "\n".join(rows)
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return (
                f"❌ **Error:** {str(e)}\n\n"
                "Please check your connection settings in Tool Settings."
            )

    async def get_latest_slack_messages(
        self,
        max_results: int = 5,
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Get the latest received Slack messages with sender names and channels."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {"description": "📥 Loading latest Slack messages...", "done": False},
            }
        )
        try:
            user_id = self._extract_user_id(__user__)
            app_user_name, app_user_email = self._extract_user_identity(__user__)
            user_tz_name = self._extract_user_timezone(__user__)
            if not app_user_email:
                google_profile = await self._get_google_profile(user_id=user_id)
                if google_profile:
                    app_user_email = (google_profile.get("email") or "").strip()
                    if not app_user_name:
                        app_user_name = (google_profile.get("name") or "").strip()
            token_payload = (
                await self._get_oauth_tokens(user_id=user_id, provider="slack")
                if user_id
                else None
            ) or {}
            slack_team_id = token_payload.get("team_id", "")
            slack_token = await self._get_slack_token(
                user_id=user_id, require_user_scope=True
            )
            if not slack_token:
                await emit(
                    {
                        "type": "status",
                        "data": {"description": "❌ Slack not configured", "done": True},
                    }
                )
                return (
                    "❌ **Error:** Slack is not connected.\n\n"
                    "Click **Connect** for Slack first."
                )

            from datetime import datetime, timezone
            from zoneinfo import ZoneInfo
            from slack_sdk.errors import SlackApiError
            from slack_sdk.web.async_client import AsyncWebClient

            client = AsyncWebClient(token=slack_token)
            try:
                local_tz = ZoneInfo(user_tz_name)
            except Exception:
                local_tz = timezone.utc
            slack_profile = await self._get_slack_profile(
                user_id=user_id, preferred_email=app_user_email
            )
            self_user_id = (
                (slack_profile or {}).get("matched_user_id")
                or (slack_profile or {}).get("user_id")
                or ""
            )
            if not self_user_id:
                try:
                    auth = await client.auth_test()
                    self_user_id = auth.get("user_id", "") or self_user_id
                except Exception:
                    pass

            sender_cache = {}
            dm_partner_cache = {}
            entries = []

            def normalize_name(value: str) -> str:
                return "".join(ch for ch in (value or "").lower() if ch.isalnum())

            async def resolve_dm_partner(channel_obj: dict) -> str:
                channel_id = (channel_obj or {}).get("id", "")
                if not channel_id:
                    return ""
                if channel_id in dm_partner_cache:
                    return dm_partner_cache[channel_id]

                dm_user_id = (channel_obj or {}).get("user", "")
                if not dm_user_id:
                    try:
                        info_kwargs = {"channel": channel_id}
                        if slack_team_id:
                            info_kwargs["team_id"] = slack_team_id
                        info = await client.conversations_info(**info_kwargs)
                        channel_info = (info or {}).get("channel", {}) or {}
                        dm_user_id = channel_info.get("user", "")
                    except Exception:
                        dm_user_id = ""

                name = ""
                if dm_user_id:
                    name = await self._resolve_slack_user_display(
                        client, dm_user_id, sender_cache, team_id=slack_team_id
                    )
                dm_partner_cache[channel_id] = name or ""
                return dm_partner_cache[channel_id]

            # Fast path: Slack search API sorted by timestamp (includes DMs/channels).
            # This avoids scanning every conversation on every request.
            try:
                search_kwargs = {
                    "query": "*",
                    "count": max(20, min(100, max_results * 6)),
                    "sort": "timestamp",
                    "sort_dir": "desc",
                }
                if slack_team_id:
                    search_kwargs["team_id"] = slack_team_id
                search_resp = await client.search_messages(**search_kwargs)
                for match in (search_resp.get("messages", {}) or {}).get("matches", []) or []:
                    sender_id = match.get("user", "")
                    text = (match.get("text") or "").strip()
                    if not text:
                        continue
                    ts = match.get("ts", "")
                    if not ts:
                        continue
                    sender = ""
                    if sender_id:
                        sender = await self._resolve_slack_user_display(
                            client, sender_id, sender_cache, team_id=slack_team_id
                        )
                    if not sender or sender == "unknown":
                        sender = (
                            (match.get("username") or "").strip()
                            or (match.get("user_profile", {}) or {}).get("real_name", "")
                            or ""
                        )
                    channel_obj = match.get("channel", {}) or {}
                    channel_name = channel_obj.get("name") or channel_obj.get("id") or "unknown"
                    dm_partner = ""
                    if channel_obj.get("is_im"):
                        dm_partner = await resolve_dm_partner(channel_obj)
                        if (not sender or sender == "unknown") and dm_partner:
                            sender = dm_partner
                        channel_name = f"DM:{dm_partner or sender}" if (dm_partner or sender) else "DM"
                    is_self_by_id = bool(sender_id and self_user_id and sender_id == self_user_id)
                    is_self_dm = bool(
                        channel_obj.get("is_im")
                        and dm_partner
                        and sender
                        and normalize_name(sender) != normalize_name(dm_partner)
                    )
                    if is_self_by_id or is_self_dm:
                        continue
                    if not sender:
                        sender = "unknown"
                    entries.append(
                        {
                            "ts": ts,
                            "sender": sender,
                            "channel": channel_name,
                            "text": await self._replace_slack_user_mentions(
                                text, client, sender_cache, team_id=slack_team_id
                            ),
                        }
                    )
                    if len(entries) >= max(1, min(max_results, 20)):
                        break
            except SlackApiError as slack_err:
                err_code = (
                    (slack_err.response.data or {}).get("error", "")
                    if getattr(slack_err, "response", None)
                    else ""
                )
                # If search is unavailable for token/scope, fall back to channel scanning.
                if err_code not in ("not_allowed_token_type", "missing_scope"):
                    raise

            if not entries:
                channel_cursor = None
                channels = []
                for _ in range(8):
                    list_kwargs = {
                        "exclude_archived": True,
                        "limit": 200,
                        "cursor": channel_cursor,
                        "types": "im,mpim,public_channel,private_channel",
                    }
                    if slack_team_id:
                        list_kwargs["team_id"] = slack_team_id
                    channel_resp = await client.conversations_list(**list_kwargs)
                    channels.extend(channel_resp.get("channels", []) or [])
                    channel_cursor = (channel_resp.get("response_metadata", {}) or {}).get(
                        "next_cursor"
                    )
                    if not channel_cursor:
                        break

                sem = asyncio.Semaphore(10)

                async def newest_received_entry(channel_obj: dict) -> Optional[dict]:
                    channel_id = channel_obj.get("id", "")
                    if not channel_id:
                        return None
                    try:
                        async with sem:
                            hist_kwargs = {"channel": channel_id, "limit": 10}
                            if slack_team_id:
                                hist_kwargs["team_id"] = slack_team_id
                            hist = await client.conversations_history(**hist_kwargs)
                    except SlackApiError:
                        return None

                    for message in (hist.get("messages", []) or []):
                        subtype = (message.get("subtype") or "").strip()
                        if subtype in ("bot_message", "channel_join", "channel_leave"):
                            continue
                        sender_id = message.get("user", "")
                        text = (message.get("text") or "").strip()
                        ts = message.get("ts", "")
                        if not text or not ts:
                            continue
                        sender = await self._resolve_slack_user_display(
                            client, sender_id, sender_cache, team_id=slack_team_id
                        )
                        channel_name = (
                            channel_obj.get("name") or channel_obj.get("id") or "unknown"
                        )
                        dm_partner = ""
                        if channel_obj.get("is_im"):
                            dm_partner = await resolve_dm_partner(channel_obj)
                            if (not sender or sender == "unknown") and dm_partner:
                                sender = dm_partner
                            channel_name = f"DM:{dm_partner or sender}" if (dm_partner or sender) else "DM"
                        is_self_by_id = bool(sender_id and self_user_id and sender_id == self_user_id)
                        is_self_dm = bool(
                            channel_obj.get("is_im")
                            and dm_partner
                            and sender
                            and normalize_name(sender) != normalize_name(dm_partner)
                        )
                        if is_self_by_id or is_self_dm:
                            continue
                        if not sender:
                            sender = "unknown"
                        return {
                            "ts": ts,
                            "sender": sender,
                            "channel": channel_name,
                            "text": await self._replace_slack_user_mentions(
                                text, client, sender_cache, team_id=slack_team_id
                            ),
                        }
                    return None

                scanned = await asyncio.gather(
                    *(newest_received_entry(ch) for ch in channels),
                    return_exceptions=True,
                )
                for item in scanned:
                    if isinstance(item, Exception) or not item:
                        continue
                    entries.append(item)

            def ts_value(ts: str) -> float:
                try:
                    return float(ts)
                except Exception:
                    return 0.0

            entries.sort(key=lambda item: ts_value(item.get("ts", "")), reverse=True)
            entries = entries[: max(1, min(max_results, 20))]

            if not entries:
                await emit(
                    {
                        "type": "status",
                        "data": {"description": "✅ No results", "done": True},
                    }
                )
                return "No recent received Slack messages found."

            def format_ts(ts: str) -> str:
                try:
                    value = float(ts)
                    return datetime.fromtimestamp(value, tz=timezone.utc).astimezone(
                        local_tz
                    ).strftime(
                        "%Y-%m-%d %I:%M %p"
                    )
                except Exception:
                    return ts

            lines = [
                "## 📥 Latest Slack Messages",
                f"_All times shown in {user_tz_name}._",
                "",
                "| # | When | Channel | Sender | Message |",
                "|---|------|---------|--------|---------|",
            ]
            for index, entry in enumerate(entries, start=1):
                safe_text = entry["text"].replace("\n", " ").replace("|", "\\|")
                lines.append(
                    f"| {index} | {format_ts(entry['ts'])} | {entry['channel']} | {entry['sender']} | {safe_text} |"
                )

            latest = entries[0]
            latest_dm = next(
                (entry for entry in entries if entry.get("channel", "").startswith("DM:")),
                None,
            )
            lines.extend(
                [
                    "",
                    f"Last message sender: **{latest['sender']}**",
                    f"Last message channel: **{latest['channel']}**",
                ]
            )
            if latest_dm:
                lines.extend(
                    [
                        f"Latest DM sender: **{latest_dm['sender']}**",
                        f"Latest DM channel: **{latest_dm['channel']}**",
                    ]
                )

            await emit(
                {
                    "type": "status",
                    "data": {"description": "✅ Latest Slack messages loaded", "done": True},
                }
            )
            return "\n".join(lines)
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return (
                f"❌ **Error:** {str(e)}\n\n"
                "Please check your connection settings in Tool Settings."
            )

    async def get_last_slack_sent_and_received(
        self,
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Return the latest Slack message you sent and the latest Slack message you received, including sender names and channels."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {"description": "📥📤 Loading latest Slack activity...", "done": False},
            }
        )
        try:
            user_id = self._extract_user_id(__user__)
            app_user_name, app_user_email = self._extract_user_identity(__user__)
            user_tz_name = self._extract_user_timezone(__user__)
            if not app_user_email:
                google_profile = await self._get_google_profile(user_id=user_id)
                if google_profile:
                    app_user_email = (google_profile.get("email") or "").strip()
                    if not app_user_name:
                        app_user_name = (google_profile.get("name") or "").strip()

            token_payload = (
                await self._get_oauth_tokens(user_id=user_id, provider="slack")
                if user_id
                else None
            ) or {}
            slack_team_id = token_payload.get("team_id", "")
            slack_token = await self._get_slack_token(
                user_id=user_id, require_user_scope=True
            )
            if not slack_token:
                await emit(
                    {
                        "type": "status",
                        "data": {"description": "❌ Slack not configured", "done": True},
                    }
                )
                return (
                    "❌ **Error:** Slack is not connected.\n\n"
                    "Click **Connect** for Slack first."
                )

            from datetime import datetime, timezone
            from zoneinfo import ZoneInfo
            from slack_sdk.web.async_client import AsyncWebClient

            client = AsyncWebClient(token=slack_token)
            try:
                local_tz = ZoneInfo(user_tz_name)
            except Exception:
                local_tz = timezone.utc

            slack_profile = await self._get_slack_profile(
                user_id=user_id, preferred_email=app_user_email
            )
            self_user_id = (
                (slack_profile or {}).get("matched_user_id")
                or (slack_profile or {}).get("user_id")
                or ""
            )
            self_name = (
                (slack_profile or {}).get("matched_name")
                or (slack_profile or {}).get("real_name")
                or app_user_name
                or "You"
            )
            if not self_user_id:
                try:
                    auth = await client.auth_test()
                    self_user_id = auth.get("user_id", "") or self_user_id
                    if self_name == "You":
                        self_name = auth.get("user", "") or self_name
                except Exception:
                    pass

            sender_cache = {}
            dm_partner_cache = {}

            def normalize_name(value: str) -> str:
                return "".join(ch for ch in (value or "").lower() if ch.isalnum())

            async def resolve_dm_partner(channel_obj: dict) -> str:
                channel_id = (channel_obj or {}).get("id", "")
                if not channel_id:
                    return ""
                if channel_id in dm_partner_cache:
                    return dm_partner_cache[channel_id]
                dm_user_id = (channel_obj or {}).get("user", "")
                if not dm_user_id:
                    try:
                        info_kwargs = {"channel": channel_id}
                        if slack_team_id:
                            info_kwargs["team_id"] = slack_team_id
                        info = await client.conversations_info(**info_kwargs)
                        channel_info = (info or {}).get("channel", {}) or {}
                        dm_user_id = channel_info.get("user", "")
                    except Exception:
                        dm_user_id = ""
                name = ""
                if dm_user_id:
                    name = await self._resolve_slack_user_display(
                        client, dm_user_id, sender_cache, team_id=slack_team_id
                    )
                dm_partner_cache[channel_id] = name or ""
                return dm_partner_cache[channel_id]

            def ts_value(ts: str) -> float:
                try:
                    return float(ts)
                except Exception:
                    return 0.0

            def format_ts(ts: str) -> str:
                try:
                    return datetime.fromtimestamp(float(ts), tz=timezone.utc).astimezone(
                        local_tz
                    ).strftime("%Y-%m-%d %I:%M %p")
                except Exception:
                    return ts

            last_sent = None
            last_received = None
            search_kwargs = {
                "query": "*",
                "count": 120,
                "sort": "timestamp",
                "sort_dir": "desc",
            }
            if slack_team_id:
                search_kwargs["team_id"] = slack_team_id
            response = await client.search_messages(**search_kwargs)
            for match in (response.get("messages", {}) or {}).get("matches", []) or []:
                text = (match.get("text") or "").strip()
                ts = match.get("ts", "")
                if not text or not ts:
                    continue
                sender_id = match.get("user", "")
                sender_name = ""
                if sender_id:
                    sender_name = await self._resolve_slack_user_display(
                        client, sender_id, sender_cache, team_id=slack_team_id
                    )
                if not sender_name or sender_name == "unknown":
                    sender_name = (
                        (match.get("username") or "").strip()
                        or (match.get("user_profile", {}) or {}).get("real_name", "")
                        or ""
                    )

                channel_obj = match.get("channel", {}) or {}
                channel_name = channel_obj.get("name") or channel_obj.get("id") or "unknown"
                recipient_name = ""
                if channel_obj.get("is_im"):
                    dm_partner = await resolve_dm_partner(channel_obj)
                    channel_name = f"DM:{dm_partner}" if dm_partner else "DM"
                    recipient_name = dm_partner

                is_self_by_id = bool(self_user_id and sender_id and sender_id == self_user_id)
                is_self_dm = bool(
                    channel_obj.get("is_im")
                    and recipient_name
                    and sender_name
                    and normalize_name(sender_name) != normalize_name(recipient_name)
                )
                is_self = is_self_by_id or is_self_dm
                item = {
                    "ts": ts,
                    "when": format_ts(ts),
                    "channel": channel_name,
                    "sender": sender_name or ("You" if is_self else "unknown"),
                    "recipient": recipient_name,
                    "text": await self._replace_slack_user_mentions(
                        text, client, sender_cache, team_id=slack_team_id
                    ),
                }

                if is_self and last_sent is None:
                    if not item["sender"]:
                        item["sender"] = self_name or "You"
                    last_sent = item
                if (not is_self) and last_received is None:
                    last_received = item
                if last_sent and last_received:
                    break

            if not last_sent and not last_received:
                await emit(
                    {
                        "type": "status",
                        "data": {"description": "✅ No results", "done": True},
                    }
                )
                return "No recent Slack sent/received messages found."

            lines = [
                "## 📥📤 Latest Slack Activity",
                f"_All times shown in {user_tz_name}._",
                "",
            ]
            if last_received:
                lines.extend(
                    [
                        f"Last received sender: **{last_received['sender']}**",
                        f"Last received channel: **{last_received['channel']}**",
                        f"Last received time: **{last_received['when']}**",
                        f'Last received message: "{last_received["text"]}"',
                        "",
                    ]
                )
            if last_sent:
                recipient_text = (
                    f" to **{last_sent['recipient']}**"
                    if last_sent.get("recipient")
                    else ""
                )
                sent_lines = [
                    f"Last sent sender: **{last_sent['sender'] or self_name}**",
                    f"Last sent channel: **{last_sent['channel']}**",
                    f"Last sent time: **{last_sent['when']}**",
                    f'Last sent message{recipient_text}: "{last_sent["text"]}"',
                ]
                if last_sent.get("recipient"):
                    sent_lines.insert(
                        1, f"Last sent recipient: **{last_sent['recipient']}**"
                    )
                lines.extend(sent_lines)

            await emit(
                {
                    "type": "status",
                    "data": {"description": "✅ Latest Slack activity loaded", "done": True},
                }
            )
            return "\n".join(lines)
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return (
                f"❌ **Error:** {str(e)}\n\n"
                "Please check your connection settings in Tool Settings."
            )

    async def send_whatsapp(
        self,
        to: str,
        message: str,
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Send a WhatsApp message. Phone number in international format (+15551234567)."""
        emit = self._make_emitter(__event_emitter__)

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {
                    "description": "📲 Sending WhatsApp message...",
                    "done": False,
                },
            }
        )
        try:
            if (
                not self.valves.whatsapp_access_token
                or not self.valves.whatsapp_phone_number_id
            ):
                await emit(
                    {
                        "type": "status",
                        "data": {
                            "description": "❌ WhatsApp not configured",
                            "done": True,
                        },
                    }
                )
                return "❌ **Error:** WhatsApp credentials are not configured."

            cleaned = "".join(ch for ch in to if ch.isdigit() or ch == "+")
            whatsapp_to = cleaned[1:] if cleaned.startswith("+") else cleaned

            url = f"https://graph.facebook.com/v21.0/{self.valves.whatsapp_phone_number_id}/messages"
            payload = {
                "messaging_product": "whatsapp",
                "to": whatsapp_to,
                "type": "text",
                "text": {"body": message},
            }
            headers = {
                "Authorization": f"Bearer {self.valves.whatsapp_access_token}",
                "Content-Type": "application/json",
            }

            session = await self._get_session()
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status >= 400:
                    error_text = await resp.text()
                    raise Exception(
                        f"WhatsApp API error {resp.status}: {error_text}"
                    )

            await emit(
                {
                    "type": "status",
                    "data": {"description": "✅ WhatsApp sent", "done": True},
                }
            )
            return f"✅ **WhatsApp message sent** to {to}"
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return (
                f"❌ **Error:** {str(e)}\n\n"
                "Please check your connection settings in Tool Settings."
            )

    async def get_last_whatsapp_sent_and_received(
        self,
        max_results: int = 80,
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Return your latest sent and received WhatsApp messages from your connected personal WhatsApp account."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {"description": "📲 Loading WhatsApp activity...", "done": False},
            }
        )
        try:
            user_id = self._extract_user_id(__user__)
            if not user_id:
                await emit(
                    {
                        "type": "status",
                        "data": {"description": "❌ Missing user context", "done": True},
                    }
                )
                return "❌ **Error:** Missing signed-in user context."

            status = await self._get_oauth_status(user_id=user_id, provider="whatsapp")
            if not status or not status.get("connected"):
                await emit(
                    {
                        "type": "status",
                        "data": {"description": "❌ WhatsApp not connected", "done": True},
                    }
                )
                return "❌ **Error:** WhatsApp is not connected."

            def extract_text(blob: Any) -> str:
                if isinstance(blob, str):
                    return blob.strip()
                if isinstance(blob, dict):
                    for key in ("conversation", "text", "body", "caption"):
                        value = blob.get(key)
                        if isinstance(value, str) and value.strip():
                            return value.strip()
                    for value in blob.values():
                        found = extract_text(value)
                        if found:
                            return found
                if isinstance(blob, list):
                    for item in blob:
                        found = extract_text(item)
                        if found:
                            return found
                return ""
            try:
                records = await self._get_whatsapp_records(
                    user_id=user_id, limit=max_results
                )
            except Exception as exc:
                await emit(
                    {
                        "type": "status",
                        "data": {"description": "❌ WhatsApp query failed", "done": True},
                    }
                )
                return f"❌ **Error:** WhatsApp query failed ({str(exc)})."

            if not records:
                await emit(
                    {
                        "type": "status",
                        "data": {"description": "✅ No WhatsApp messages found", "done": True},
                    }
                )
                return "No WhatsApp messages found yet."

            from datetime import datetime, timezone
            from zoneinfo import ZoneInfo

            def msg_ts(item: dict) -> float:
                raw = (
                    item.get("messageTimestamp")
                    or item.get("timestamp")
                    or item.get("createdAt")
                    or item.get("key", {}).get("messageTimestamp")
                    or 0
                )
                try:
                    if isinstance(raw, str) and "-" in raw:
                        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
                    return float(raw)
                except Exception:
                    return 0.0

            def format_ts(raw_ts: float) -> str:
                if not raw_ts:
                    return "unknown time"
                try:
                    tz_name = self._extract_user_timezone(__user__)
                    local_tz = ZoneInfo(tz_name)
                except Exception:
                    local_tz = timezone.utc
                return datetime.fromtimestamp(raw_ts, tz=timezone.utc).astimezone(local_tz).strftime("%Y-%m-%d %I:%M %p")

            sorted_records = sorted(records, key=msg_ts, reverse=True)
            last_sent = None
            last_received = None
            for item in sorted_records:
                key = item.get("key", {}) if isinstance(item.get("key"), dict) else {}
                from_me = bool(item.get("fromMe") or key.get("fromMe"))
                text = extract_text(item.get("message", item)) or "[media/other]"
                remote = key.get("remoteJid") or item.get("remoteJid") or ""
                sender = item.get("pushName") or item.get("sender") or item.get("participant") or remote or "unknown"
                entry = {
                    "when": format_ts(msg_ts(item)),
                    "text": self._clip_text(text, 260),
                    "remote": remote,
                    "sender": sender,
                }
                if from_me and last_sent is None:
                    last_sent = entry
                if (not from_me) and last_received is None:
                    last_received = entry
                if last_sent and last_received:
                    break

            lines = ["## 📲 Latest WhatsApp Activity", ""]
            if last_received:
                lines.extend(
                    [
                        f"Last received from: **{last_received['sender']}**",
                        f"Last received time: **{last_received['when']}**",
                        f"Last received message: \"{last_received['text']}\"",
                        "",
                    ]
                )
            if last_sent:
                lines.extend(
                    [
                        f"Last sent to: **{last_sent['remote'] or 'contact'}**",
                        f"Last sent time: **{last_sent['when']}**",
                        f"Last sent message: \"{last_sent['text']}\"",
                    ]
                )
            if not last_sent and not last_received:
                lines.append("No readable WhatsApp messages found.")

            await emit(
                {
                    "type": "status",
                    "data": {"description": "✅ WhatsApp activity loaded", "done": True},
                }
            )
            return "\n".join(lines)
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return (
                f"❌ **Error:** {str(e)}\n\n"
                "Please check your connection settings in Tool Settings."
            )

    async def get_last_whatsapp_message_sent(
        self,
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Return only the last WhatsApp message you sent."""
        data = await self.get_last_whatsapp_sent_and_received(
            max_results=80, __user__=__user__, __event_emitter__=__event_emitter__
        )
        if data.startswith("## 📲 Latest WhatsApp Activity"):
            lines = data.splitlines()
            keep = []
            for line in lines:
                if line.startswith("Last sent ") or line.startswith("##"):
                    keep.append(line)
            if keep:
                return "\n".join(keep)
        return data

    async def ask_envision(
        self,
        question: str,
        project_name: str = "",
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Ask Envision OS a question about your construction projects. Access 390+ tools including Procore, Sage, Buildr, ClickUp, Rippling."""
        emit = self._make_emitter(__event_emitter__)

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {"description": "🏗️ Querying Envision OS...", "done": False},
            }
        )
        try:
            def looks_like_upstream_failure(text: str) -> bool:
                if not text:
                    return True
                t = text.lower()
                markers = [
                    "unified agent is unavailable",
                    "unable to retrieve",
                    "authorization error",
                    "access denied",
                    "denied",
                    "error when trying to query analytics",
                    "procore and sage intacct",
                    "connection issue with procore",
                    "couldn't complete this request",
                ]
                return any(marker in t for marker in markers)

            args = {"question": question}
            if project_name:
                args["project_name"] = project_name
            extractor = getattr(self, "_extract_mcp_user_id", None)
            if callable(extractor):
                mcp_user_id = extractor(__user__)
            else:
                mcp_user_id = self._extract_user_id(__user__)
            if mcp_user_id:
                args["user_id"] = mcp_user_id

            result = await self._mcp_request(
                "tools/call",
                {"name": "ask_envision_os", "arguments": args},
            )

            def format_result(data: dict) -> str:
                if not data:
                    return "No response received from Envision MCP."
                if "error" in data:
                    err = data["error"]
                    if isinstance(err, dict):
                        return f"❌ **Error:** {err.get('message', str(err))}"
                    return f"❌ **Error:** {err}"
                if "result" in data:
                    content = data["result"]
                    if isinstance(content, dict) and "content" in content:
                        parts = []
                        for item in content["content"]:
                            if isinstance(item, dict):
                                if item.get("type") == "text":
                                    parts.append(item.get("text", ""))
                                elif item.get("type") == "image":
                                    parts.append(
                                        f"[Image: {item.get('mimeType', 'image')}]"
                                    )
                                else:
                                    parts.append(json.dumps(item, indent=2))
                            else:
                                parts.append(str(item))
                        return "\n".join(parts).strip() or "No content returned."
                    if isinstance(content, str):
                        return content
                    return json.dumps(content, indent=2, default=str)
                return json.dumps(data, indent=2, default=str)

            await emit(
                {
                    "type": "status",
                    "data": {"description": "✅ Envision response ready", "done": True},
                }
            )
            output = format_result(result)

            final_output = output
            # Project-scoped calls can intermittently fail upstream; retry once
            # without hard project scoping to recover freshest available context.
            if project_name and looks_like_upstream_failure(output):
                retry_args = {"question": question}
                if mcp_user_id:
                    retry_args["user_id"] = mcp_user_id
                retry = await self._mcp_request(
                    "tools/call",
                    {"name": "ask_envision_os", "arguments": retry_args},
                )
                retry_output = format_result(retry)
                if retry_output and not looks_like_upstream_failure(retry_output):
                    final_output = retry_output

            if self._is_latest_project_communication_query(question or ""):
                project_hint = (project_name or self._extract_project_hint_from_text(question or "")).strip()
                if project_hint:
                    return await self._build_project_communications_digest(
                        project_hint=project_hint,
                        __user__=__user__,
                        mcp_output=final_output,
                    )
            return final_output
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return (
                f"❌ **Error:** {str(e)}\n\n"
                "Please check your connection settings in Tool Settings."
            )

    async def search_construction_docs(
        self,
        query: str,
        project_id: str = "",
        doc_type: str = "",
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Search construction documents (drawings, specs, RFIs, submittals) with AI-powered citations."""
        emit = self._make_emitter(__event_emitter__)

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {
                    "description": "📄 Searching construction docs...",
                    "done": False,
                },
            }
        )
        try:
            args = {"query": query}
            if project_id:
                args["project_id"] = project_id
            if doc_type:
                args["doc_type"] = doc_type
            extractor = getattr(self, "_extract_mcp_user_id", None)
            if callable(extractor):
                mcp_user_id = extractor(__user__)
            else:
                mcp_user_id = self._extract_user_id(__user__)
            if mcp_user_id:
                args["user_id"] = mcp_user_id

            result = await self._mcp_request(
                "tools/call",
                {"name": "search_documents", "arguments": args},
            )

            def format_result(data: dict) -> str:
                if not data:
                    return "No response received from Envision MCP."
                if "error" in data:
                    err = data["error"]
                    if isinstance(err, dict):
                        return f"❌ **Error:** {err.get('message', str(err))}"
                    return f"❌ **Error:** {err}"
                if "result" in data:
                    content = data["result"]
                    if isinstance(content, dict) and "content" in content:
                        parts = []
                        for item in content["content"]:
                            if isinstance(item, dict):
                                if item.get("type") == "text":
                                    parts.append(item.get("text", ""))
                                elif item.get("type") == "image":
                                    parts.append(
                                        f"[Image: {item.get('mimeType', 'image')}]"
                                    )
                                else:
                                    parts.append(json.dumps(item, indent=2))
                            else:
                                parts.append(str(item))
                        return "\n".join(parts).strip() or "No content returned."
                    if isinstance(content, str):
                        return content
                    return json.dumps(content, indent=2, default=str)
                return json.dumps(data, indent=2, default=str)

            await emit(
                {
                    "type": "status",
                    "data": {"description": "✅ Docs search complete", "done": True},
                }
            )
            return format_result(result)
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return (
                f"❌ **Error:** {str(e)}\n\n"
                "Please check your connection settings in Tool Settings."
            )

    async def envision_tool(
        self,
        tool_name: str,
        arguments: str = "{}",
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Call any Envision MCP tool by name. Use discover_envision_tools to find available tools. Arguments as JSON string."""
        emit = self._make_emitter(__event_emitter__)

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {"description": f"⚙️ Calling {tool_name}...", "done": False},
            }
        )
        try:
            try:
                args = (
                    json.loads(arguments) if isinstance(arguments, str) else arguments
                )
            except json.JSONDecodeError:
                await emit(
                    {
                        "type": "status",
                        "data": {"description": "❌ Invalid JSON", "done": True},
                    }
                )
                return "❌ **Error:** Invalid JSON in arguments."

            result = await self._mcp_request(
                "tools/call",
                {"name": tool_name, "arguments": args},
            )

            def format_result(data: dict) -> str:
                if not data:
                    return "No response received from Envision MCP."
                if "error" in data:
                    err = data["error"]
                    if isinstance(err, dict):
                        return f"❌ **Error:** {err.get('message', str(err))}"
                    return f"❌ **Error:** {err}"
                if "result" in data:
                    content = data["result"]
                    if isinstance(content, dict) and "content" in content:
                        parts = []
                        for item in content["content"]:
                            if isinstance(item, dict):
                                if item.get("type") == "text":
                                    parts.append(item.get("text", ""))
                                elif item.get("type") == "image":
                                    parts.append(
                                        f"[Image: {item.get('mimeType', 'image')}]"
                                    )
                                else:
                                    parts.append(json.dumps(item, indent=2))
                            else:
                                parts.append(str(item))
                        return "\n".join(parts).strip() or "No content returned."
                    if isinstance(content, str):
                        return content
                    return json.dumps(content, indent=2, default=str)
                return json.dumps(data, indent=2, default=str)

            await emit(
                {
                    "type": "status",
                    "data": {"description": "✅ Tool response ready", "done": True},
                }
            )
            return format_result(result)
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return (
                f"❌ **Error:** {str(e)}\n\n"
                "Please check your connection settings in Tool Settings."
            )

    async def discover_envision_tools(
        self,
        search: str = "",
        __user__: dict = None,
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """List available Envision MCP tools. Optionally filter by search keyword. There are 390+ tools across Procore, Sage, Slack, Gmail, Drive, Zoom, ClickUp, Rippling, Buildr, and more."""
        emit = self._make_emitter(__event_emitter__)

        __user__ = __user__ or {}
        await emit(
            {
                "type": "status",
                "data": {
                    "description": "🔎 Loading Envision tool list...",
                    "done": False,
                },
            }
        )
        try:
            result = await self._mcp_request("tools/list")
            if not result or "result" not in result:
                await emit(
                    {
                        "type": "status",
                        "data": {
                            "description": "❌ Tool list unavailable",
                            "done": True,
                        },
                    }
                )
                return "❌ **Error:** Unable to fetch tool list."

            tools = result["result"].get("tools", [])
            if search:
                search_lower = search.lower()
                tools = [
                    tool
                    for tool in tools
                    if search_lower in tool.get("name", "").lower()
                    or search_lower in (tool.get("description") or "").lower()
                ]

            rows = [
                "| # | Tool | Description |",
                "|---|------|-------------|",
            ]
            for index, tool in enumerate(tools, start=1):
                name = tool.get("name", "")
                desc = (tool.get("description") or "").replace("\n", " ")
                pipe_escaped = desc.replace("|", "\\|")
                rows.append(f"| {index} | `{name}` | {pipe_escaped} |")

            await emit(
                {
                    "type": "status",
                    "data": {
                        "description": f"✅ {len(tools)} tools listed",
                        "done": True,
                    },
                }
            )
            heading = "## 🧰 Envision MCP Tools"
            if search:
                heading = f'## 🧰 Envision MCP Tools (filtered: "{search}")'
            return heading + "\n\n" + "\n".join(rows)
        except Exception as e:
            await emit(
                {
                    "type": "status",
                    "data": {"description": "❌ Error", "done": True},
                }
            )
            return (
                f"❌ **Error:** {str(e)}\n\n"
                "Please check your connection settings in Tool Settings."
            )

    def _is_latest_project_communication_query(self, text: str) -> bool:
        t = (text or "").strip().lower()
        if not t:
            return False
        has_latest = any(
            phrase in t
            for phrase in (
                "latest",
                "most recent",
                "newest",
                "last update",
                "latest on",
            )
        )
        has_comm_context = any(
            phrase in t
            for phrase in (
                "communication",
                "status",
                "update",
                "regarding",
                "about",
                "project",
            )
        )
        return has_latest and has_comm_context

    def _extract_project_hint_from_text(self, text: str) -> str:
        import re

        source = (text or "").strip()
        if not source:
            return ""

        lower = source.lower()
        patterns = [
            r"(?:regarding|about|on|for)\s+([a-z0-9&\-\s]{2,80})$",
            r"latest(?:\s+communication|\s+update|\s+status|\s+on)?\s+(?:for|on|about|regarding)?\s*([a-z0-9&\-\s]{2,80})$",
            r"([a-z0-9&\-\s]{2,80})\s+project$",
        ]
        for pattern in patterns:
            match = re.search(pattern, lower)
            if not match:
                continue
            candidate = match.group(1).strip()
            candidate = re.sub(r"\b(the|project|regarding|about|status|latest|communication|update)\b", " ", candidate)
            candidate = re.sub(r"\s+", " ", candidate).strip(" -_.,")
            if candidate:
                return candidate

        tokens = re.findall(r"[A-Za-z0-9&\-]+", source)
        stop = {
            "what",
            "whats",
            "what's",
            "the",
            "latest",
            "communication",
            "regarding",
            "about",
            "project",
            "status",
            "update",
            "on",
            "for",
            "is",
            "of",
        }
        candidate_tokens = [tok for tok in tokens if tok.lower() not in stop]
        return " ".join(candidate_tokens[:4]).strip()

    def _clip_text(self, text: str, limit: int = 520) -> str:
        compact = " ".join((text or "").split())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 1] + "…"

    async def _latest_email_for_project(
        self,
        project_hint: str,
        user_id: str,
        lookback_days: int = 90,
        max_results: int = 5,
    ) -> str:
        if not user_id:
            return "Email: not available (missing signed-in user)."
        creds = await self._get_google_creds(user_id=user_id)
        if not creds:
            return "Email: not connected."
        try:
            from datetime import datetime, timezone
            from email.utils import parsedate_to_datetime
            from googleapiclient.discovery import build

            service = build("gmail", "v1", credentials=creds)
            query = f'"{project_hint}" newer_than:{lookback_days}d'
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute(),
            )
            messages = (resp or {}).get("messages", []) or []
            if not messages:
                return f"Email: no recent messages found for \"{project_hint}\"."

            def header_value(headers: list[dict], name: str) -> str:
                for header in headers:
                    if header.get("name", "").lower() == name.lower():
                        return header.get("value", "")
                return ""

            best = None
            best_ts = 0.0
            for message in messages:
                message_id = message.get("id", "")
                detail = await loop.run_in_executor(
                    None,
                    lambda mid=message_id: service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=mid,
                        format="metadata",
                        metadataHeaders=["Subject", "From", "Date"],
                    )
                    .execute(),
                )
                headers = (detail or {}).get("payload", {}).get("headers", []) or []
                date_raw = header_value(headers, "Date")
                ts = 0.0
                if date_raw:
                    try:
                        ts = parsedate_to_datetime(date_raw).timestamp()
                    except Exception:
                        ts = 0.0
                if ts <= 0:
                    try:
                        ts = int((detail or {}).get("internalDate", "0")) / 1000.0
                    except Exception:
                        ts = 0.0
                if ts >= best_ts:
                    best_ts = ts
                    best = {
                        "subject": header_value(headers, "Subject") or "(no subject)",
                        "from": header_value(headers, "From") or "(unknown sender)",
                        "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %I:%M %p %Z")
                        if ts
                        else (date_raw or "unknown"),
                    }
            if not best:
                return f"Email: no readable message metadata found for \"{project_hint}\"."
            return (
                f'Email latest: {best["date"]} from {best["from"]} '
                f'— "{self._clip_text(best["subject"], 180)}"'
            )
        except Exception as exc:
            msg = str(exc)
            if "invalid_request" in msg and "client ID" in msg:
                return "Email: token refresh failed (reconnect Google Workspace)."
            return f"Email: unavailable ({msg})"

    async def _latest_slack_for_project(self, project_hint: str, __user__: Optional[dict]) -> str:
        try:
            raw = await self.search_slack(
                query=project_hint,
                max_results=5,
                __user__=__user__ or {},
                __event_emitter__=None,
            )
        except Exception as exc:
            return f"Slack: unavailable ({str(exc)})"

        if not raw:
            return "Slack: unavailable."
        if raw.startswith("❌"):
            return f"Slack: {self._clip_text(raw, 160)}"
        if "No Slack messages found" in raw:
            return f'Slack: no recent messages found for "{project_hint}".'

        import re

        row = None
        for line in raw.splitlines():
            if re.match(r"^\|\s*1\s*\|", line.strip()):
                row = line.strip()
                break
        if not row:
            return "Slack: search completed, but no parsable top result."
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        if len(cells) < 5:
            return "Slack: search completed, but no parsable top result."
        when = cells[1]
        channel = cells[2].lstrip("#")
        sender = cells[3] or "unknown"
        message = self._clip_text(cells[4].replace("\\|", "|"), 220)
        return f'Slack latest: {when} in {channel} from {sender} — "{message}"'

    async def _latest_whatsapp_for_project(self, project_hint: str, user_id: str) -> str:
        if not user_id:
            return "WhatsApp: not available (missing signed-in user)."
        try:
            connected = await self._get_oauth_status(user_id=user_id, provider="whatsapp")
            if not connected:
                return "WhatsApp: not connected."
        except Exception:
            return "WhatsApp: not connected."

        def extract_text(blob: Any) -> str:
            if isinstance(blob, str):
                return blob
            if isinstance(blob, dict):
                for key in ("conversation", "text", "body", "message"):
                    value = blob.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
                for value in blob.values():
                    value_text = extract_text(value)
                    if value_text:
                        return value_text
            if isinstance(blob, list):
                for item in blob:
                    value_text = extract_text(item)
                    if value_text:
                        return value_text
            return ""

        try:
            records = await self._get_whatsapp_records(user_id=user_id, limit=40)
            if not records:
                return f'WhatsApp: no recent messages found for "{project_hint}".'

            needle = (project_hint or "").strip().lower()
            best = None
            for record in records:
                text = extract_text(record)
                if not text:
                    continue
                if needle and needle not in text.lower():
                    continue
                best = record
                break
            if not best:
                best = records[0]

            text = self._clip_text(extract_text(best), 220) or "(no text)"
            sender = (
                best.get("pushName")
                or best.get("sender")
                or best.get("participant")
                or best.get("key", {}).get("remoteJid")
                or "unknown"
            )
            when = (
                best.get("messageTimestamp")
                or best.get("timestamp")
                or best.get("createdAt")
                or "unknown time"
            )
            return f'WhatsApp latest: {when} from {sender} — "{text}"'
        except Exception as exc:
            return f"WhatsApp: unavailable ({str(exc)})"

    async def _build_project_communications_digest(
        self,
        project_hint: str,
        __user__: Optional[dict],
        mcp_output: str,
    ) -> str:
        user = __user__ or {}
        user_id = self._extract_user_id(user)
        email_summary, slack_summary, whatsapp_summary = await asyncio.gather(
            self._latest_email_for_project(project_hint=project_hint, user_id=user_id),
            self._latest_slack_for_project(project_hint=project_hint, __user__=user),
            self._latest_whatsapp_for_project(project_hint=project_hint, user_id=user_id),
            return_exceptions=False,
        )
        lines = [
            f"## Latest Communications: {project_hint}",
            "",
            "Tried sources: Envision MCP, Slack, Email, WhatsApp.",
            "",
            f"- Envision MCP: {self._clip_text(mcp_output or 'No response.', 700)}",
            f"- {slack_summary}",
            f"- {email_summary}",
            f"- {whatsapp_summary}",
        ]
        return "\n".join(lines)

    async def _get_google_creds(self, user_id: str = "") -> Any:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        if self._google_creds and not self._google_creds.expired:
            return self._google_creds

        scopes = [
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/drive",
        ]

        access_token = None
        refresh_token = None
        using_proxy_oauth = False

        if user_id:
            token_payload = await self._get_oauth_tokens(user_id=user_id, provider="google")
            if token_payload:
                using_proxy_oauth = True
                access_token = token_payload.get("access_token")
                refresh_token = token_payload.get("refresh_token")
            if not access_token:
                access_token = await self._refresh_google_access_token(user_id=user_id)
                if access_token:
                    using_proxy_oauth = True

        # Fallback for legacy static-token deployments.
        if not refresh_token:
            refresh_token = self.valves.google_refresh_token
        if not access_token:
            access_token = None

        if not refresh_token and not access_token:
            return None
        # Only require local client credentials when using legacy local refresh tokens.
        if (not using_proxy_oauth) and refresh_token and (
            not self.valves.google_client_id or not self.valves.google_client_secret
        ):
            return None

        # Primary path: refresh-token credentials.
        # Fallback path: short-lived access-token-only credentials from /oauth/refresh.
        if refresh_token:
            creds = Credentials(
                token=access_token,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.valves.google_client_id,
                client_secret=self.valves.google_client_secret,
                scopes=scopes,
            )
        else:
            creds = Credentials(token=access_token, scopes=scopes)

        if (not creds.valid or not creds.token) and creds.refresh_token:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: creds.refresh(Request()))
        self._google_creds = creds
        return creds

    def _extract_user_id(self, __user__: Optional[dict]) -> str:
        user = __user__ or {}
        for key in ("id", "user_id", "sub"):
            value = user.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _extract_user_identity(self, __user__: Optional[dict]) -> tuple[str, str]:
        user = __user__ or {}
        name = user.get("name", "") if isinstance(user.get("name"), str) else ""
        email = user.get("email", "") if isinstance(user.get("email"), str) else ""
        return name.strip(), email.strip()

    def _extract_mcp_user_id(self, __user__: Optional[dict]) -> str:
        user = __user__ or {}
        email = user.get("email", "") if isinstance(user.get("email"), str) else ""
        if email.strip():
            return email.strip()
        return self._extract_user_id(user)

    def _extract_user_timezone(self, __user__: Optional[dict]) -> str:
        user = __user__ or {}
        timezone = user.get("timezone", "") if isinstance(user.get("timezone"), str) else ""
        if timezone and timezone.strip():
            return timezone.strip()
        settings = user.get("settings", {})
        if isinstance(settings, dict):
            tz = settings.get("timezone", "")
            if isinstance(tz, str) and tz.strip():
                return tz.strip()
        return "America/New_York"

    async def _get_oauth_status(self, user_id: str, provider: str) -> Optional[dict]:
        if not user_id:
            return None
        import aiohttp

        session = await self._get_session()
        base_url = self.valves.oauth_proxy_url.rstrip("/")
        url = f"{base_url}/oauth/tokens/{user_id}?provider={provider}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 404:
                return None
            if resp.status >= 400:
                return None
            return await resp.json()

    async def _get_oauth_tokens(self, user_id: str, provider: str) -> Optional[dict]:
        if not user_id:
            return None
        import aiohttp

        session = await self._get_session()
        base_url = self.valves.oauth_proxy_url.rstrip("/")
        url = f"{base_url}/oauth/tokens/{user_id}/full?provider={provider}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 404:
                return None
            if resp.status >= 400:
                return None
            return await resp.json()

    async def _refresh_google_access_token(self, user_id: str) -> Optional[str]:
        if not user_id:
            return None
        import aiohttp

        session = await self._get_session()
        base_url = self.valves.oauth_proxy_url.rstrip("/")
        url = f"{base_url}/oauth/refresh/{user_id}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status >= 400:
                return None
            data = await resp.json()
            return data.get("access_token")

    async def _get_whatsapp_records(self, user_id: str, limit: int = 80) -> list[dict]:
        if not user_id:
            return []
        import aiohttp

        session = await self._get_session()
        base_url = self.valves.oauth_proxy_url.rstrip("/")
        safe_limit = max(20, min(limit, 150))
        url = f"{base_url}/oauth/whatsapp/messages/{user_id}?limit={safe_limit}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=25)) as resp:
            if resp.status == 404:
                detail = ""
                try:
                    payload = await resp.json(content_type=None)
                    if isinstance(payload, dict):
                        detail = (
                            payload.get("detail")
                            or payload.get("message")
                            or payload.get("error")
                            or ""
                        )
                except Exception:
                    detail = (await resp.text())[:200]
                # 404 from this endpoint means disconnected/missing session, not empty inbox.
                raise RuntimeError(
                    "WhatsApp not connected"
                    + (f": {detail}" if detail else "")
                )
            if resp.status >= 400:
                detail = ""
                try:
                    payload = await resp.json(content_type=None)
                    if isinstance(payload, dict):
                        detail = (
                            payload.get("detail")
                            or payload.get("message")
                            or payload.get("error")
                            or ""
                        )
                except Exception:
                    detail = (await resp.text())[:200]
                raise RuntimeError(
                    f"WhatsApp query failed (HTTP {resp.status})"
                    + (f": {detail}" if detail else "")
                )
            payload = await resp.json(content_type=None)
            if not isinstance(payload, dict):
                return []
            records = payload.get("records", [])
            if not isinstance(records, list):
                return []
            return [item for item in records if isinstance(item, dict)]

    async def _get_google_profile(self, user_id: str) -> Optional[dict]:
        if not user_id:
            return None
        import aiohttp

        google_status = await self._get_oauth_status(user_id=user_id, provider="google")
        if not google_status:
            return None

        access_token = await self._refresh_google_access_token(user_id=user_id)
        if not access_token:
            return None

        session = await self._get_session()
        headers = {"Authorization": f"Bearer {access_token}"}
        profile_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        async with session.get(
            profile_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status == 401 and google_status.get("has_refresh_token"):
                refreshed = await self._refresh_google_access_token(user_id=user_id)
                if not refreshed:
                    return None
                headers = {"Authorization": f"Bearer {refreshed}"}
                async with session.get(
                    profile_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as retry_resp:
                    if retry_resp.status >= 400:
                        return None
                    return await retry_resp.json()
            if resp.status >= 400:
                return None
            return await resp.json()

    async def _get_slack_token(
        self, user_id: str = "", require_user_scope: bool = False
    ) -> Optional[str]:
        token_payload = None
        if user_id:
            token_payload = await self._get_oauth_tokens(
                user_id=user_id, provider="slack"
            )

        if token_payload:
            if require_user_scope:
                for key in ("user_token", "access_token"):
                    value = token_payload.get(key)
                    if value:
                        return value
            else:
                for key in ("user_token", "access_token", "bot_token"):
                    value = token_payload.get(key)
                    if value:
                        return value

        # Legacy static-token fallback
        if require_user_scope:
            return self.valves.slack_user_token or None
        return self.valves.slack_bot_token or self.valves.slack_user_token or None

    async def _get_slack_profile(
        self, user_id: str, preferred_email: str = ""
    ) -> Optional[dict]:
        if not user_id:
            return None
        if not preferred_email:
            google_profile = await self._get_google_profile(user_id=user_id)
            if google_profile:
                preferred_email = (google_profile.get("email") or "").strip()
        token_payload = await self._get_oauth_tokens(user_id=user_id, provider="slack")
        token_payload = token_payload or {}
        slack_team_id = token_payload.get("team_id", "")
        token = await self._get_slack_token(user_id=user_id, require_user_scope=False)
        if not token:
            return None

        from slack_sdk.errors import SlackApiError
        from slack_sdk.web.async_client import AsyncWebClient

        client = AsyncWebClient(token=token)
        auth_data = await client.auth_test()

        profile = {
            "user": auth_data.get("user", ""),
            "user_id": auth_data.get("user_id", ""),
            "team": auth_data.get("team", ""),
            "team_id": auth_data.get("team_id", ""),
            "url": auth_data.get("url", ""),
        }

        if preferred_email:
            try:
                lookup = await client.users_lookupByEmail(email=preferred_email)
                matched_user = lookup.get("user", {}) if lookup else {}
                matched_profile = matched_user.get("profile", {}) if matched_user else {}
                profile["matched_user_id"] = matched_user.get("id", "")
                profile["matched_name"] = (
                    matched_user.get("real_name") or matched_user.get("name", "")
                )
                profile["matched_email"] = matched_profile.get("email", "")
                if profile["matched_name"]:
                    profile["real_name"] = profile["matched_name"]
                if profile["matched_email"]:
                    profile["email"] = profile["matched_email"]
            except Exception:
                pass

        slack_user_id = profile.get("user_id")
        if slack_user_id:
            try:
                user_data = await client.users_info(user=slack_user_id)
            except SlackApiError as slack_err:
                err_code = (
                    (slack_err.response.data or {}).get("error", "")
                    if getattr(slack_err, "response", None)
                    else ""
                )
                if err_code == "missing_argument" and slack_team_id:
                    user_data = await client.users_info(
                        user=slack_user_id, team_id=slack_team_id
                    )
                else:
                    user_data = None
            try:
                slack_user = user_data.get("user", {}) if user_data else {}
                slack_user_profile = slack_user.get("profile", {}) if slack_user else {}
                profile["real_name"] = slack_user.get("real_name", "") or slack_user.get(
                    "name", ""
                )
                profile["email"] = slack_user_profile.get("email", "")
            except Exception:
                # users:read / users:read.email might not be granted; auth_test is enough
                pass

        return profile

    async def _resolve_slack_user_display(
        self, client: Any, sender_id: str, cache: dict, team_id: str = ""
    ) -> str:
        if not sender_id:
            return "unknown"
        if sender_id in cache:
            return cache[sender_id]

        from slack_sdk.errors import SlackApiError

        label = sender_id
        try:
            user_data = await client.users_info(user=sender_id)
        except SlackApiError as slack_err:
            err_code = (
                (slack_err.response.data or {}).get("error", "")
                if getattr(slack_err, "response", None)
                else ""
            )
            if err_code == "missing_argument" and team_id:
                user_data = await client.users_info(user=sender_id, team_id=team_id)
            else:
                user_data = None
        try:
            slack_user = user_data.get("user", {}) if user_data else {}
            slack_user_profile = slack_user.get("profile", {}) if slack_user else {}
            label = (
                slack_user_profile.get("real_name")
                or slack_user.get("real_name")
                or slack_user_profile.get("display_name")
                or slack_user.get("name")
                or sender_id
            )
        except Exception:
            label = sender_id

        cache[sender_id] = label
        return label

    async def _replace_slack_user_mentions(
        self, text: str, client: Any, cache: dict, team_id: str = ""
    ) -> str:
        if not text:
            return text
        import re

        user_ids = set(re.findall(r"<@([A-Z0-9]+)>", text))
        out = text
        for uid in user_ids:
            name = await self._resolve_slack_user_display(
                client, uid, cache, team_id=team_id
            )
            out = out.replace(f"<@{uid}>", f"@{name}")
        return out

    async def _get_session(self):
        if self._http_session is None or self._http_session.closed:
            import aiohttp

            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def _mcp_request(self, method: str, params: dict = None) -> dict:
        import aiohttp

        def next_id() -> int:
            self._mcp_request_id += 1
            return self._mcp_request_id

        async def send(payload: dict) -> dict:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            if self._mcp_session_id:
                headers["Mcp-Session-Id"] = self._mcp_session_id

            timeout = aiohttp.ClientTimeout(total=120)
            session = await self._get_session()
            async with session.post(
                self.valves.envision_mcp_url,
                json=payload,
                headers=headers,
                timeout=timeout,
            ) as resp:
                if "Mcp-Session-Id" in resp.headers:
                    self._mcp_session_id = resp.headers["Mcp-Session-Id"]

                content_type = resp.headers.get("Content-Type", "")
                if resp.status >= 400:
                    return {"error": f"HTTP {resp.status}: {await resp.text()}"}

                if "text/event-stream" in content_type:
                    result = None
                    raw = await resp.text()
                    for raw_line in raw.splitlines():
                        line = raw_line.strip()
                        if not line or line.startswith(":"):
                            continue
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            if not data_str or data_str == "[DONE]":
                                continue
                            try:
                                result = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue
                        else:
                            try:
                                result = json.loads(line)
                            except json.JSONDecodeError:
                                continue

                    if result is None:
                        return {"error": "No valid response from MCP server"}
                    return result

                try:
                    return await resp.json()
                except Exception:
                    return {"error": "Invalid JSON response from MCP"}

        if not self._mcp_initialized and method not in (
            "initialize",
            "notifications/initialized",
        ):
            async with self._init_lock:
                if self._mcp_initialized:
                    pass  # another coroutine beat us to it
                elif time.time() < self._mcp_init_failed_until:
                    return {"error": "MCP initialization failed recently, backing off"}
                else:
                    init_payload = {
                        "jsonrpc": "2.0",
                        "id": next_id(),
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {
                                "name": "open-webui-envision-os",
                                "version": "1.0.0",
                            },
                        },
                    }
                    init_result = await send(init_payload)
                    if init_result and "result" in init_result:
                        self._mcp_initialized = True
                        # Send as a notification — no id field, no response expected
                        await send(
                            {
                                "jsonrpc": "2.0",
                                "method": "notifications/initialized",
                            }
                        )
                    else:
                        self._mcp_init_failed_until = time.time() + 10
                        return init_result

        payload = {
            "jsonrpc": "2.0",
            "id": next_id(),
            "method": method,
        }
        if params:
            payload["params"] = params
        return await send(payload)
