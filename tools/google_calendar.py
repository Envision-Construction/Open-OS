"""
title: Google Calendar
author: Avi Reddy
version: 0.1.0
license: MIT
description: List, create, and update Google Calendar events using OAuth 2.0
required_pip_packages: google-auth google-auth-oauthlib google-api-python-client
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from pydantic import BaseModel

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_URI = "https://oauth2.googleapis.com/token"
CALENDAR_ID = "primary"


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _format_event_time(value: str) -> str:
    if "T" not in value:
        return value

    parsed = _parse_iso_datetime(value)
    if not parsed:
        return value

    tz_label = parsed.strftime("%Z").strip()
    if not tz_label:
        tz_label = parsed.strftime("%z").strip()

    label = f" {tz_label}" if tz_label else ""
    return parsed.strftime("%Y-%m-%d %I:%M %p") + label


def _format_attendees(attendees: List[Dict[str, Any]]) -> str:
    emails = [attendee.get("email") for attendee in attendees if attendee.get("email")]
    return ", ".join(emails) if emails else "None"


class Tools:
    class Valves(BaseModel):
        google_client_id: str = ""
        google_client_secret: str = ""
        google_refresh_token: str = ""

    def __init__(self) -> None:
        self.valves = self.Valves()

    async def _emit_status(
        self, __event_emitter__, description: str, done: bool = False
    ) -> None:
        if not __event_emitter__:
            return

        await __event_emitter__(
            {
                "type": "status",
                "data": {
                    "description": description,
                    "done": done,
                },
            }
        )

    async def _build_credentials(self) -> Credentials:
        if not self.valves.google_client_id:
            raise ValueError("Missing Google client ID in valves.")
        if not self.valves.google_client_secret:
            raise ValueError("Missing Google client secret in valves.")
        if not self.valves.google_refresh_token:
            raise ValueError("Missing Google refresh token in valves.")

        credentials = Credentials(
            token=None,
            refresh_token=self.valves.google_refresh_token,
            token_uri=TOKEN_URI,
            client_id=self.valves.google_client_id,
            client_secret=self.valves.google_client_secret,
            scopes=SCOPES,
        )

        await asyncio.to_thread(credentials.refresh, Request())
        return credentials

    async def _get_service(self):
        credentials = await self._build_credentials()
        return await asyncio.to_thread(
            build,
            "calendar",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )

    async def list_events(
        self,
        days_ahead: int = 7,
        max_results: int = 20,
        *,
        __user__: dict,
        __event_emitter__,
    ) -> str:
        """List upcoming Google Calendar events within a time range."""
        await self._emit_status(
            __event_emitter__, "Authenticating with Google Calendar..."
        )

        try:
            service = await self._get_service()
            now = datetime.now(timezone.utc)
            time_min = now.isoformat()
            time_max = (now + timedelta(days=days_ahead)).isoformat()

            await self._emit_status(__event_emitter__, "Fetching upcoming events...")

            request = service.events().list(
                calendarId=CALENDAR_ID,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            response = await asyncio.to_thread(request.execute)
            events = response.get("items", [])

            if not events:
                await self._emit_status(
                    __event_emitter__, "No upcoming events found.", done=True
                )
                return f"No upcoming events in the next {days_ahead} days."

            lines = [f"Upcoming events (next {days_ahead} days):"]
            for index, event in enumerate(events, start=1):
                summary = event.get("summary", "(No title)")
                start_raw = event.get("start", {}).get("dateTime") or event.get(
                    "start", {}
                ).get("date", "")
                end_raw = event.get("end", {}).get("dateTime") or event.get(
                    "end", {}
                ).get("date", "")
                start = _format_event_time(start_raw) if start_raw else "Unknown"
                end = _format_event_time(end_raw) if end_raw else "Unknown"
                location = event.get("location", "N/A")
                attendees = _format_attendees(event.get("attendees", []))
                event_id = event.get("id", "N/A")
                link = event.get("htmlLink", "N/A")

                lines.append(f"{index}. {summary}")
                lines.append(f"   When: {start} - {end}")
                lines.append(f"   Location: {location}")
                lines.append(f"   Attendees: {attendees}")
                lines.append(f"   Event ID: {event_id}")
                lines.append(f"   Link: {link}")

            await self._emit_status(__event_emitter__, "Events retrieved.", done=True)
            return "\n".join(lines)
        except Exception as exc:
            await self._emit_status(
                __event_emitter__, f"Failed to list events: {exc}", done=True
            )
            return f"Error listing events: {exc}"

    async def create_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        description: str = "",
        location: str = "",
        attendees: str = "",
        *,
        __user__: dict,
        __event_emitter__,
    ) -> str:
        """Create a new Google Calendar event."""
        await self._emit_status(
            __event_emitter__, "Authenticating with Google Calendar..."
        )

        try:
            service = await self._get_service()
            event_body: Dict[str, Any] = {
                "summary": title,
                "start": {"dateTime": start_time},
                "end": {"dateTime": end_time},
            }
            if description:
                event_body["description"] = description
            if location:
                event_body["location"] = location

            if attendees:
                attendee_list = [
                    {"email": email.strip()}
                    for email in attendees.split(",")
                    if email.strip()
                ]
                if attendee_list:
                    event_body["attendees"] = attendee_list

            await self._emit_status(__event_emitter__, "Creating event...")

            request = service.events().insert(calendarId=CALENDAR_ID, body=event_body)
            created = await asyncio.to_thread(request.execute)

            created_start = created.get("start", {}).get("dateTime") or created.get(
                "start", {}
            ).get("date", "")
            created_end = created.get("end", {}).get("dateTime") or created.get(
                "end", {}
            ).get("date", "")
            start_display = (
                _format_event_time(created_start) if created_start else "Unknown"
            )
            end_display = _format_event_time(created_end) if created_end else "Unknown"

            await self._emit_status(__event_emitter__, "Event created.", done=True)

            return "\n".join(
                [
                    "Event created successfully:",
                    f"Title: {created.get('summary', title)}",
                    f"When: {start_display} - {end_display}",
                    f"Location: {created.get('location', location) or 'N/A'}",
                    f"Event ID: {created.get('id', 'N/A')}",
                    f"Link: {created.get('htmlLink', 'N/A')}",
                ]
            )
        except Exception as exc:
            await self._emit_status(
                __event_emitter__, f"Failed to create event: {exc}", done=True
            )
            return f"Error creating event: {exc}"

    async def update_event(
        self,
        event_id: str,
        title: str = "",
        start_time: str = "",
        end_time: str = "",
        description: str = "",
        *,
        __user__: dict,
        __event_emitter__,
    ) -> str:
        """Update an existing Google Calendar event by ID."""
        await self._emit_status(
            __event_emitter__, "Authenticating with Google Calendar..."
        )

        try:
            if not any([title, start_time, end_time, description]):
                await self._emit_status(
                    __event_emitter__,
                    "No update fields provided. Nothing to change.",
                    done=True,
                )
                return "No update fields provided."

            service = await self._get_service()
            await self._emit_status(__event_emitter__, "Fetching existing event...")

            get_request = service.events().get(calendarId=CALENDAR_ID, eventId=event_id)
            event = await asyncio.to_thread(get_request.execute)

            if title:
                event["summary"] = title
            if description:
                event["description"] = description
            if start_time:
                event.setdefault("start", {})
                event["start"]["dateTime"] = start_time
                event["start"].pop("date", None)
            if end_time:
                event.setdefault("end", {})
                event["end"]["dateTime"] = end_time
                event["end"].pop("date", None)

            await self._emit_status(__event_emitter__, "Updating event...")

            update_request = service.events().update(
                calendarId=CALENDAR_ID,
                eventId=event_id,
                body=event,
            )
            updated = await asyncio.to_thread(update_request.execute)

            updated_start = updated.get("start", {}).get("dateTime") or updated.get(
                "start", {}
            ).get("date", "")
            updated_end = updated.get("end", {}).get("dateTime") or updated.get(
                "end", {}
            ).get("date", "")
            start_display = (
                _format_event_time(updated_start) if updated_start else "Unknown"
            )
            end_display = _format_event_time(updated_end) if updated_end else "Unknown"

            await self._emit_status(__event_emitter__, "Event updated.", done=True)

            return "\n".join(
                [
                    "Event updated successfully:",
                    f"Title: {updated.get('summary', title) or '(No title)'}",
                    f"When: {start_display} - {end_display}",
                    f"Description: {updated.get('description', description) or 'N/A'}",
                    f"Event ID: {updated.get('id', event_id)}",
                    f"Link: {updated.get('htmlLink', 'N/A')}",
                ]
            )
        except Exception as exc:
            await self._emit_status(
                __event_emitter__, f"Failed to update event: {exc}", done=True
            )
            return f"Error updating event: {exc}"
