"""
title: Gmail
author: Avi Reddy
version: 0.1.0
license: MIT
description: Send, search, and read Gmail emails using Google OAuth 2.0
required_pip_packages: google-auth google-auth-oauthlib google-api-python-client
"""

import base64
from email.mime.text import MIMEText
from typing import Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from pydantic import BaseModel

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class Tools:
    class Valves(BaseModel):
        google_client_id: str = ""
        google_client_secret: str = ""
        google_refresh_token: str = ""

    def __init__(self) -> None:
        self.valves = self.Valves()

    def _build_credentials(self) -> Credentials:
        creds = Credentials(
            token=None,
            refresh_token=self.valves.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.valves.google_client_id,
            client_secret=self.valves.google_client_secret,
            scopes=SCOPES,
        )
        if not creds.valid and creds.refresh_token:
            creds.refresh(Request())
        return creds

    def _get_header(self, headers: List[Dict[str, str]], name: str) -> str:
        for header in headers:
            if header.get("name", "").lower() == name.lower():
                return header.get("value", "")
        return ""

    def _decode_body(self, data: Optional[str]) -> str:
        if not data:
            return ""
        decoded_bytes = base64.urlsafe_b64decode(data.encode("utf-8"))
        try:
            return decoded_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return decoded_bytes.decode("latin-1", errors="replace")

    def _extract_plain_text(self, payload: Dict) -> str:
        if not payload:
            return ""
        body_data = payload.get("body", {}).get("data")
        if body_data:
            return self._decode_body(body_data)

        parts = payload.get("parts", []) or []
        for part in parts:
            if part.get("mimeType") == "text/plain":
                return self._decode_body(part.get("body", {}).get("data"))

        for part in parts:
            for subpart in part.get("parts", []) or []:
                if subpart.get("mimeType") == "text/plain":
                    return self._decode_body(subpart.get("body", {}).get("data"))

        return ""

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        __user__: dict,
        __event_emitter__,
    ) -> str:
        """Send an email via Gmail using OAuth 2.0 credentials."""
        _ = __user__
        await __event_emitter__(
            {"type": "status", "data": {"description": "Searching...", "done": False}}
        )
        try:
            creds = self._build_credentials()
            service = build("gmail", "v1", credentials=creds)

            message = MIMEText(body, "plain", "utf-8")
            message["to"] = to
            message["subject"] = subject

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            result = (
                service.users()
                .messages()
                .send(userId="me", body={"raw": raw_message})
                .execute()
            )
            message_id = result.get("id", "unknown")
            thread_id = result.get("threadId", "unknown")
            return (
                f"Email sent to {to}. Message ID: {message_id}. "
                f"Thread ID: {thread_id}."
            )
        except Exception as exc:
            return f"Error sending email: {exc}"
        finally:
            await __event_emitter__(
                {"type": "status", "data": {"description": "Done", "done": True}}
            )

    async def search_emails(
        self,
        query: str,
        max_results: int = 10,
        *,
        __user__: dict,
        __event_emitter__,
    ) -> str:
        """Search Gmail messages using a Gmail query string."""
        _ = __user__
        await __event_emitter__(
            {"type": "status", "data": {"description": "Searching...", "done": False}}
        )
        try:
            creds = self._build_credentials()
            service = build("gmail", "v1", credentials=creds)

            response = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )
            messages = response.get("messages", [])
            if not messages:
                return f"No emails found for query: {query}"

            lines: List[str] = []
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
                subject = self._get_header(headers, "Subject") or "(no subject)"
                sender = self._get_header(headers, "From") or "(unknown sender)"
                date = self._get_header(headers, "Date") or "(unknown date)"
                lines.append(
                    f"{index}. {subject} | {sender} | {date} | ID: {message_id}"
                )

            return "Search results:\n" + "\n".join(lines)
        except Exception as exc:
            return f"Error searching emails: {exc}"
        finally:
            await __event_emitter__(
                {"type": "status", "data": {"description": "Done", "done": True}}
            )

    async def read_email(
        self,
        message_id: str,
        __user__: dict,
        __event_emitter__,
    ) -> str:
        """Read a full Gmail message by message ID."""
        _ = __user__
        await __event_emitter__(
            {"type": "status", "data": {"description": "Searching...", "done": False}}
        )
        try:
            creds = self._build_credentials()
            service = build("gmail", "v1", credentials=creds)

            message = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
            payload = message.get("payload", {})
            headers = payload.get("headers", [])

            subject = self._get_header(headers, "Subject") or "(no subject)"
            sender = self._get_header(headers, "From") or "(unknown sender)"
            recipient = self._get_header(headers, "To") or "(unknown recipient)"
            date = self._get_header(headers, "Date") or "(unknown date)"
            snippet = message.get("snippet", "")
            body_text = self._extract_plain_text(payload) or snippet

            return (
                "Subject: {subject}\n"
                "From: {sender}\n"
                "To: {recipient}\n"
                "Date: {date}\n\n"
                "Body:\n{body_text}"
            ).format(
                subject=subject,
                sender=sender,
                recipient=recipient,
                date=date,
                body_text=body_text,
            )
        except Exception as exc:
            return f"Error reading email: {exc}"
        finally:
            await __event_emitter__(
                {"type": "status", "data": {"description": "Done", "done": True}}
            )
