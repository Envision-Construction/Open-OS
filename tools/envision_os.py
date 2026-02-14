"""
title: Envision OS
author: Avi Reddy
version: 1.0.0
license: MIT
description: Personal AI OS — Gmail, Calendar, Drive, Slack, WhatsApp + 390 Envision construction tools with OAuth connection flow
required_pip_packages: google-auth google-auth-oauthlib google-api-python-client aiohttp
"""

from pydantic import BaseModel, Field
from typing import Any, Callable, Optional
import json


class Tools:
    class Valves(BaseModel):
        # Google OAuth
        google_client_id: str = Field(
            default="",
            description="Google OAuth Client ID (Web Application type)",
        )
        google_client_secret: str = Field(
            default="",
            description="Google OAuth Client Secret",
        )
        google_refresh_token: str = Field(
            default="",
            description="Auto-filled after OAuth flow — do not edit manually",
        )
        google_oauth_redirect_uri: str = Field(
            default="https://storage.googleapis.com/open-os-oauth-callback/callback.html",
            description="OAuth callback URL",
        )
        # Slack
        slack_bot_token: str = Field(
            default="",
            description="Slack Bot Token (xoxb-...)",
        )
        slack_user_token: str = Field(
            default="",
            description="Slack User Token for search (xoxp-...)",
        )
        # WhatsApp
        whatsapp_access_token: str = Field(
            default="",
            description="WhatsApp Cloud API Access Token",
        )
        whatsapp_phone_number_id: str = Field(
            default="",
            description="WhatsApp Phone Number ID",
        )
        whatsapp_business_account_id: str = Field(
            default="",
            description="WhatsApp Business Account ID",
        )
        # Envision MCP
        envision_mcp_url: str = Field(
            default="https://envision-mcp-845049957105.us-central1.run.app/mcp",
            description="Envision MCP Gateway URL",
        )

    def __init__(self) -> None:
        self.valves = self.Valves()
        self._mcp_session_id = None
        self._mcp_initialized = False
        self._mcp_request_id = 0

    async def connect_google_account(
        self,
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Start the Google OAuth flow. Generates a clickable authorization URL. After authorizing in your browser, copy the code and use complete_google_connection to finish setup."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        _ = __user__
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
                "https://www.googleapis.com/auth/gmail.modify",
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/drive.readonly",
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
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Complete the Google OAuth flow by exchanging an authorization code for access tokens. Provide the code from the OAuth callback page."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        _ = __user__
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
                "https://www.googleapis.com/auth/gmail.modify",
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/drive.readonly",
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
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Check which services are currently connected and configured."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        _ = __user__
        await emit(
            {
                "type": "status",
                "data": {"description": "🔌 Checking connections...", "done": False},
            }
        )
        try:
            google_connected = bool(
                self.valves.google_client_id
                and self.valves.google_client_secret
                and self.valves.google_refresh_token
            )
            slack_connected = bool(
                self.valves.slack_bot_token or self.valves.slack_user_token
            )
            whatsapp_connected = bool(
                self.valves.whatsapp_access_token
                and self.valves.whatsapp_phone_number_id
            )
            envision_connected = bool(self.valves.envision_mcp_url)

            def status_label(is_connected: bool) -> str:
                return "✅ Connected" if is_connected else "❌ Not configured"

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
                f"| Google (Gmail, Calendar, Drive) | {status_label(google_connected)} |\n"
                f"| Slack | {status_label(slack_connected)} |\n"
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

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = "",
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Send an email via Gmail. Supports plain text and CC recipients (comma-separated)."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        _ = __user__
        await emit(
            {
                "type": "status",
                "data": {"description": "✉️ Sending email...", "done": False},
            }
        )
        try:
            if not self.valves.google_refresh_token:
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

            creds = self._get_google_creds()
            service = build("gmail", "v1", credentials=creds)

            message = MIMEText(body, "plain", "utf-8")
            message["to"] = to
            if cc:
                message["cc"] = cc
            message["subject"] = subject

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            service.users().messages().send(
                userId="me", body={"raw": raw_message}
            ).execute()

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
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Search Gmail emails. Use Gmail search syntax (from:, to:, subject:, has:attachment, after:, before:, is:unread)."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        _ = __user__
        await emit(
            {
                "type": "status",
                "data": {"description": "🔍 Searching emails...", "done": False},
            }
        )
        try:
            if not self.valves.google_refresh_token:
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

            creds = self._get_google_creds()
            service = build("gmail", "v1", credentials=creds)

            response = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )
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
                detail = (
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=message_id,
                        format="metadata",
                        metadataHeaders=["Subject", "From", "Date"],
                    )
                    .execute()
                )
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
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Read the full content of a specific email by its message ID."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        _ = __user__
        await emit(
            {
                "type": "status",
                "data": {"description": "📨 Loading email...", "done": False},
            }
        )
        try:
            if not self.valves.google_refresh_token:
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

            creds = self._get_google_creds()
            service = build("gmail", "v1", credentials=creds)

            message = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
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
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """List upcoming Google Calendar events for the next N days."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        _ = __user__
        await emit(
            {
                "type": "status",
                "data": {"description": "📅 Loading calendar events...", "done": False},
            }
        )
        try:
            if not self.valves.google_refresh_token:
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

            creds = self._get_google_creds()
            service = build("calendar", "v3", credentials=creds)

            now = datetime.now(timezone.utc)
            time_min = now.isoformat()
            time_max = (now + timedelta(days=days_ahead)).isoformat()

            response = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
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
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Create a Google Calendar event. Times in ISO 8601 format. Attendees as comma-separated emails."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        _ = __user__
        await emit(
            {
                "type": "status",
                "data": {"description": "📅 Creating event...", "done": False},
            }
        )
        try:
            if not self.valves.google_refresh_token:
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

            creds = self._get_google_creds()
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
                "start": {"dateTime": start_time},
                "end": {"dateTime": end_time},
            }
            if attendee_list:
                event["attendees"] = attendee_list

            service.events().insert(calendarId="primary", body=event).execute()

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
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Search Google Drive for files by name or content."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        _ = __user__
        await emit(
            {
                "type": "status",
                "data": {"description": "📁 Searching Drive...", "done": False},
            }
        )
        try:
            if not self.valves.google_refresh_token:
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

            creds = self._get_google_creds()
            service = build("drive", "v3", credentials=creds)

            safe_query = query.replace("'", "\\'")
            q = f"name contains '{safe_query}' or fullText contains '{safe_query}'"

            response = (
                service.files()
                .list(
                    q=q,
                    pageSize=max_results,
                    fields="files(id, name, mimeType, modifiedTime, size)",
                )
                .execute()
            )
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
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Read the text content of a Google Drive file. Automatically exports Google Docs/Sheets/Slides to text."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        _ = __user__
        await emit(
            {
                "type": "status",
                "data": {"description": "📄 Reading Drive file...", "done": False},
            }
        )
        try:
            if not self.valves.google_refresh_token:
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

            creds = self._get_google_creds()
            service = build("drive", "v3", credentials=creds)

            metadata = (
                service.files()
                .get(fileId=file_id, fields="id, name, mimeType, modifiedTime, size")
                .execute()
            )
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
            done = False
            while not done:
                _, done = downloader.next_chunk()

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
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Send a message to a Slack channel. Channel can be a name (#general) or ID."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        _ = __user__
        await emit(
            {
                "type": "status",
                "data": {"description": "💬 Sending Slack message...", "done": False},
            }
        )
        try:
            if not self.valves.slack_bot_token:
                await emit(
                    {
                        "type": "status",
                        "data": {
                            "description": "❌ Slack not configured",
                            "done": True,
                        },
                    }
                )
                return "❌ **Error:** Slack bot token is not configured."

            from slack_sdk.web.async_client import AsyncWebClient

            client = AsyncWebClient(token=self.valves.slack_bot_token)

            async def resolve_channel_id(target: str) -> tuple[str | None, str | None]:
                if target.startswith(("C", "D", "G")):
                    return target, None
                channel_name = target.lstrip("#")
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
                            item.get("name") == channel_name
                            or item.get("name_normalized") == channel_name
                        ):
                            return item.get("id"), item.get("name")
                    cursor = response.get("response_metadata", {}).get("next_cursor")
                    if not cursor:
                        break
                return None, None

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
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Search Slack messages. Requires user token (search:read scope)."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        _ = __user__
        await emit(
            {
                "type": "status",
                "data": {"description": "🔍 Searching Slack...", "done": False},
            }
        )
        try:
            if not self.valves.slack_user_token:
                await emit(
                    {
                        "type": "status",
                        "data": {
                            "description": "❌ Slack not configured",
                            "done": True,
                        },
                    }
                )
                return "❌ **Error:** Slack user token is required for search."

            from datetime import datetime, timezone
            from slack_sdk.web.async_client import AsyncWebClient

            client = AsyncWebClient(token=self.valves.slack_user_token)
            response = await client.search_messages(query=query, count=max_results)
            matches = response.get("messages", {}).get("matches", [])

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
                    return datetime.fromtimestamp(value, tz=timezone.utc).strftime(
                        "%Y-%m-%d %H:%M UTC"
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
                sender = match.get("username") or match.get("user") or "unknown"
                text = match.get("text", "").replace("\n", " ")
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
            return f'## 💬 Slack Search Results: "{query}"\n\n' + "\n".join(rows)
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
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Send a WhatsApp message. Phone number in international format (+15551234567)."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        _ = __user__
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

            import aiohttp

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

            async with aiohttp.ClientSession() as session:
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

    async def ask_envision(
        self,
        question: str,
        project_name: str = "",
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Ask Envision OS a question about your construction projects. Access 390+ tools including Procore, Sage, Buildr, ClickUp, Rippling."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        _ = __user__
        await emit(
            {
                "type": "status",
                "data": {"description": "🏗️ Querying Envision OS...", "done": False},
            }
        )
        try:
            args = {"question": question}
            if project_name:
                args["project_name"] = project_name

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

    async def search_construction_docs(
        self,
        query: str,
        project_id: str = "",
        doc_type: str = "",
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Search construction documents (drawings, specs, RFIs, submittals) with AI-powered citations."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        _ = __user__
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
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Call any Envision MCP tool by name. Use discover_envision_tools to find available tools. Arguments as JSON string."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        _ = __user__
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
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """List available Envision MCP tools. Optionally filter by search keyword. There are 390+ tools across Procore, Sage, Slack, Gmail, Drive, Zoom, ClickUp, Rippling, Buildr, and more."""
        emit = __event_emitter__ or (lambda x: None)
        if __event_emitter__ is None:

            async def emit(_: Any) -> None:
                return None

        _ = __user__
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

    def _get_google_creds(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        scopes = [
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/drive.readonly",
        ]

        creds = Credentials(
            token=None,
            refresh_token=self.valves.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.valves.google_client_id,
            client_secret=self.valves.google_client_secret,
            scopes=scopes,
        )

        if not creds.valid and creds.refresh_token:
            creds.refresh(Request())
        return creds

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
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.valves.envision_mcp_url,
                    json=payload,
                    headers=headers,
                ) as resp:
                    if "Mcp-Session-Id" in resp.headers:
                        self._mcp_session_id = resp.headers["Mcp-Session-Id"]

                    content_type = resp.headers.get("Content-Type", "")
                    if resp.status >= 400:
                        return {"error": f"HTTP {resp.status}: {await resp.text()}"}

                    if "text/event-stream" in content_type:
                        body = await resp.text()
                        result = None
                        for line in body.split("\n"):
                            line = line.strip()
                            if line.startswith("data:"):
                                data_str = line[5:].strip()
                                if not data_str:
                                    continue
                                try:
                                    result = json.loads(data_str)
                                except json.JSONDecodeError:
                                    continue
                        return result or {"error": "No valid SSE data received"}

                    try:
                        return await resp.json()
                    except Exception:
                        return {"error": "Invalid JSON response from MCP"}

        if not self._mcp_initialized and method not in (
            "initialize",
            "notifications/initialized",
        ):
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
                await send(
                    {
                        "jsonrpc": "2.0",
                        "id": next_id(),
                        "method": "notifications/initialized",
                    }
                )
            else:
                return init_result

        payload = {
            "jsonrpc": "2.0",
            "id": next_id(),
            "method": method,
        }
        if params:
            payload["params"] = params
        return await send(payload)
