"""
title: Google Drive
author: Avi Reddy
version: 0.1.0
license: MIT
description: Search, read, and list Google Drive files using OAuth 2.0
required_pip_packages: google-auth google-auth-oauthlib google-api-python-client
"""

from __future__ import annotations

import asyncio
import io
from typing import Any, Callable

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from pydantic import BaseModel

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
TOKEN_URI = "https://oauth2.googleapis.com/token"
MAX_TEXT_LENGTH = 50000


class Tools:
    class Valves(BaseModel):
        google_client_id: str = ""
        google_client_secret: str = ""
        google_refresh_token: str = ""

    def __init__(self) -> None:
        self.valves = self.Valves()

    async def search_files(
        self,
        query: str,
        max_results: int = 20,
        __user__: dict | None = None,
        __event_emitter__: Callable[[dict[str, Any]], Any] | None = None,
    ) -> str:
        await self._emit_status(
            __event_emitter__, f"Searching Drive for: {query}", "in_progress"
        )
        try:
            service = await self._build_service()
            query_str = self._build_search_query(query)
            response = await asyncio.to_thread(
                service.files()
                .list(
                    q=query_str,
                    pageSize=max_results,
                    fields="files(id, name, mimeType, modifiedTime, size)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute
            )
            files = response.get("files", [])
            if not files:
                await self._emit_status(
                    __event_emitter__, "No files found", "complete", True
                )
                return "No files found."

            lines = [f"Results ({len(files)}):"]
            for item in files:
                lines.append(self._format_file_summary(item))

            await self._emit_status(
                __event_emitter__, "Search completed", "complete", True
            )
            return "\n".join(lines)
        except Exception as exc:  # noqa: BLE001
            await self._emit_status(
                __event_emitter__, f"Search failed: {exc}", "error", True
            )
            return f"Error searching files: {exc}"

    async def read_file(
        self,
        file_id: str,
        __user__: dict | None = None,
        __event_emitter__: Callable[[dict[str, Any]], Any] | None = None,
    ) -> str:
        await self._emit_status(
            __event_emitter__, "Fetching file metadata", "in_progress"
        )
        try:
            service = await self._build_service()
            metadata = await asyncio.to_thread(
                service.files()
                .get(
                    fileId=file_id,
                    fields="id, name, mimeType",
                    supportsAllDrives=True,
                )
                .execute
            )
            name = metadata.get("name", "")
            mime_type = metadata.get("mimeType", "")
            request = self._build_download_request(service, file_id, mime_type)

            await self._emit_status(
                __event_emitter__, "Downloading file content", "in_progress"
            )
            content = await asyncio.to_thread(self._download_as_text, request)
            content = self._truncate_text(content)

            await self._emit_status(
                __event_emitter__, "Read completed", "complete", True
            )
            return f"File: {name} ({mime_type})\n\n{content}"
        except Exception as exc:  # noqa: BLE001
            await self._emit_status(
                __event_emitter__, f"Read failed: {exc}", "error", True
            )
            return f"Error reading file: {exc}"

    async def list_files(
        self,
        folder_id: str = "root",
        max_results: int = 30,
        __user__: dict | None = None,
        __event_emitter__: Callable[[dict[str, Any]], Any] | None = None,
    ) -> str:
        await self._emit_status(
            __event_emitter__, f"Listing folder: {folder_id}", "in_progress"
        )
        try:
            service = await self._build_service()
            response = await asyncio.to_thread(
                service.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    pageSize=max_results,
                    fields="files(id, name, mimeType, modifiedTime, size)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute
            )
            files = response.get("files", [])
            if not files:
                await self._emit_status(
                    __event_emitter__, "No files found", "complete", True
                )
                return "No files found in folder."

            lines = [f"Files in folder ({len(files)}):"]
            for item in files:
                lines.append(self._format_file_summary(item))

            await self._emit_status(
                __event_emitter__, "List completed", "complete", True
            )
            return "\n".join(lines)
        except Exception as exc:  # noqa: BLE001
            await self._emit_status(
                __event_emitter__, f"List failed: {exc}", "error", True
            )
            return f"Error listing files: {exc}"

    async def get_file_info(
        self,
        file_id: str,
        __user__: dict | None = None,
        __event_emitter__: Callable[[dict[str, Any]], Any] | None = None,
    ) -> str:
        await self._emit_status(
            __event_emitter__, f"Fetching info for: {file_id}", "in_progress"
        )
        try:
            service = await self._build_service()
            info = await asyncio.to_thread(
                service.files()
                .get(
                    fileId=file_id,
                    fields="id, name, mimeType, size, modifiedTime, owners",
                    supportsAllDrives=True,
                )
                .execute
            )
            owner = ""
            owners = info.get("owners", [])
            if owners:
                owner = owners[0].get("displayName", "")
            lines = [
                "File Info:",
                f"Name: {info.get('name', '')}",
                f"ID: {info.get('id', '')}",
                f"MIME Type: {info.get('mimeType', '')}",
                f"Size: {info.get('size', '')}",
                f"Modified: {info.get('modifiedTime', '')}",
            ]
            if owner:
                lines.append(f"Owner: {owner}")

            await self._emit_status(__event_emitter__, "Info fetched", "complete", True)
            return "\n".join(lines)
        except Exception as exc:  # noqa: BLE001
            await self._emit_status(
                __event_emitter__, f"Info failed: {exc}", "error", True
            )
            return f"Error getting file info: {exc}"

    async def _build_credentials(self) -> Credentials:
        if not self.valves.google_client_id:
            raise ValueError("Missing google_client_id")
        if not self.valves.google_client_secret:
            raise ValueError("Missing google_client_secret")
        if not self.valves.google_refresh_token:
            raise ValueError("Missing google_refresh_token")

        credentials = Credentials(
            token=None,
            refresh_token=self.valves.google_refresh_token,
            token_uri=TOKEN_URI,
            client_id=self.valves.google_client_id,
            client_secret=self.valves.google_client_secret,
            scopes=SCOPES,
        )
        try:
            await asyncio.to_thread(credentials.refresh, Request())
        except Exception as e:
            raise RuntimeError(f"Google credential refresh failed: {e}") from e
        return credentials

    async def _build_service(self):
        credentials = await self._build_credentials()
        return await asyncio.to_thread(
            build, "drive", "v3", credentials=credentials, cache_discovery=False
        )

    def _build_search_query(self, query: str) -> str:
        safe_query = query.replace("\\", "\\\\").replace("'", "\\'")
        return f"(name contains '{safe_query}' or fullText contains '{safe_query}')"

    def _build_download_request(self, service, file_id: str, mime_type: str):
        if mime_type.startswith("application/vnd.google-apps"):
            export_mime = self._export_mime_type(mime_type)
            if not export_mime:
                raise ValueError("Unsupported Google Workspace file type for export")
            return service.files().export_media(fileId=file_id, mimeType=export_mime)
        return service.files().get_media(fileId=file_id)

    def _export_mime_type(self, mime_type: str) -> str | None:
        export_map = {
            "application/vnd.google-apps.document": "text/plain",
            "application/vnd.google-apps.spreadsheet": "text/csv",
            "application/vnd.google-apps.presentation": "text/plain",
        }
        return export_map.get(mime_type)

    def _download_as_text(self, request) -> str:
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue().decode("utf-8", errors="replace")

    def _truncate_text(self, text: str) -> str:
        if len(text) <= MAX_TEXT_LENGTH:
            return text
        return f"{text[:MAX_TEXT_LENGTH]}\n\n[Truncated to {MAX_TEXT_LENGTH} chars]"

    def _format_file_summary(self, item: dict[str, Any]) -> str:
        size = item.get("size", "")
        modified = item.get("modifiedTime", "")
        return (
            "- "
            f"{item.get('name', '')}"
            f" (id: {item.get('id', '')}, "
            f"mime: {item.get('mimeType', '')}, "
            f"modified: {modified}, size: {size})"
        )

    async def _emit_status(
        self,
        __event_emitter__: Callable[[dict[str, Any]], Any] | None,
        description: str,
        status: str,
        done: bool = False,
    ) -> None:
        if __event_emitter__ is None:
            return
        payload = {
            "type": "status",
            "data": {
                "description": description,
                "status": status,
                "done": done,
            },
        }
        try:
            await __event_emitter__(payload)
        except Exception:  # noqa: BLE001
            return
