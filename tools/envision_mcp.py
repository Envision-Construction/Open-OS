"""
title: Envision MCP Gateway
author: Avi Reddy
version: 0.1.0
license: MIT
description: Bridge to Envision Construction's MCP gateway — 390+ tools for Procore, Gmail, Slack, Drive, Calendar, Zoom, ClickUp, Rippling, Buildr CRM, document search, and more. Use ask_envision for natural language queries or call_tool for direct tool invocation.
required_pip_packages: aiohttp
"""

import json
import asyncio
import time
from typing import Any, Callable, Optional
from pydantic import BaseModel, Field


class Tools:
    """Bridge to the Envision MCP streamable HTTP server.

    Provides access to 390+ construction, communication, HR, and financial
    tools through the unified Envision-MCP gateway.
    """

    class Valves(BaseModel):
        mcp_server_url: str = Field(
            default="https://envision-mcp-845049957105.us-central1.run.app/mcp",
            description="Envision MCP streamable HTTP endpoint",
        )
        request_timeout: int = Field(
            default=120,
            description="Request timeout in seconds",
        )

    def __init__(self):
        self.valves = self.Valves()
        self._session_id: Optional[str] = None
        self._initialized: bool = False
        self._request_counter: int = 0
        self._init_lock = asyncio.Lock()
        self._init_failed_until: float = 0

    def _next_id(self) -> int:
        self._request_counter += 1
        return self._request_counter

    async def _mcp_request(self, method: str, params: Optional[dict] = None) -> dict:
        """Send a JSON-RPC 2.0 request to the MCP server."""
        import aiohttp

        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
        }
        if params:
            payload["params"] = params

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        timeout = aiohttp.ClientTimeout(total=self.valves.request_timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                self.valves.mcp_server_url,
                json=payload,
                headers=headers,
            ) as resp:
                # Capture session ID from response
                if "Mcp-Session-Id" in resp.headers:
                    self._session_id = resp.headers["Mcp-Session-Id"]

                content_type = resp.headers.get("Content-Type", "")

                if "text/event-stream" in content_type:
                    # SSE response — stream lines to avoid buffering entire body
                    result = None
                    async for line_bytes in resp.content:
                        line = line_bytes.decode("utf-8", errors="replace").rstrip("\n\r")
                        line = line.strip()
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            if data_str:
                                try:
                                    result = json.loads(data_str)
                                except json.JSONDecodeError:
                                    pass
                    return result or {"error": "No valid SSE data received"}
                else:
                    return await resp.json()

    async def _mcp_notify(self, method: str, params: dict = None) -> None:
        """Send a JSON-RPC notification (no id field, no response expected)."""
        import aiohttp

        payload = {"jsonrpc": "2.0", "method": method}
        if params:
            payload["params"] = params

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        timeout = aiohttp.ClientTimeout(total=self.valves.request_timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.post(
                    self.valves.mcp_server_url,
                    json=payload,
                    headers=headers,
                ) as resp:
                    if "Mcp-Session-Id" in resp.headers:
                        self._session_id = resp.headers["Mcp-Session-Id"]
            except Exception:
                pass  # notifications are fire-and-forget

    async def _ensure_initialized(self):
        """Initialize the MCP session if not already done."""
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            if time.time() < self._init_failed_until:
                return
            result = await self._mcp_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "open-webui-envision-bridge",
                        "version": "0.1.0",
                    },
                },
            )
            if result and "result" in result:
                self._initialized = True
                # Send as a notification — no id field, no response expected
                await self._mcp_notify("notifications/initialized")
            else:
                self._init_failed_until = time.time() + 10

    async def ask_envision(
        self,
        question: str,
        project_name: str = "",
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Ask Envision OS a natural language question about construction projects, budgets, RFIs, schedules, documents, meetings, emails, HR, or CRM data.

        Use this for broad questions like:
        - "What is the budget for Flow Aventura?"
        - "Show me open RFIs for the project"
        - "What was discussed in yesterday's meeting?"
        - "Who is on PTO this week?"

        :param question: Natural language question about any Envision-connected data
        :param project_name: Optional project name to scope the query (e.g., "flow-aventura")
        :return: Answer with citations and sources
        """
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {"description": "Querying Envision OS...", "done": False},
                }
            )

        try:
            await self._ensure_initialized()

            params = {"name": "ask_envision_os", "arguments": {"question": question}}
            if project_name:
                params["arguments"]["project_name"] = project_name

            result = await self._mcp_request("tools/call", params)

            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "Done", "done": True}}
                )

            return self._format_tool_result(result)

        except Exception as e:
            if __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {"description": f"Error: {e}", "done": True},
                    }
                )
            return f"Error querying Envision OS: {e}"

    async def search_documents(
        self,
        query: str,
        project_id: str = "",
        doc_type: str = "",
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Search construction documents (drawings, specs, RFIs, submittals) with AI-powered citations.

        :param query: Search query (e.g., "fire rating for Door 104", "structural steel specs")
        :param project_id: Optional Procore project ID to filter by
        :param doc_type: Optional document type filter: drawings, specs, rfis, submittals, building_code
        :return: Answer with document citations
        """
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {"description": "Searching documents...", "done": False},
                }
            )

        try:
            await self._ensure_initialized()

            args = {"query": query}
            if project_id:
                args["project_id"] = project_id
            if doc_type:
                args["doc_type"] = doc_type

            result = await self._mcp_request(
                "tools/call", {"name": "search_documents", "arguments": args}
            )

            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "Done", "done": True}}
                )

            return self._format_tool_result(result)

        except Exception as e:
            if __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {"description": f"Error: {e}", "done": True},
                    }
                )
            return f"Error searching documents: {e}"

    async def search_meetings(
        self,
        query: str,
        days_back: int = 30,
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Search meeting transcripts (Zoom, Google Meet) with AI summarization.

        :param query: What to search for in meeting discussions
        :param days_back: How many days back to search (default 30)
        :return: Answer with meeting citations
        """
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {"description": "Searching meetings...", "done": False},
                }
            )

        try:
            await self._ensure_initialized()

            result = await self._mcp_request(
                "tools/call",
                {
                    "name": "search_meetings",
                    "arguments": {"query": query, "days_back": days_back},
                },
            )

            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "Done", "done": True}}
                )

            return self._format_tool_result(result)

        except Exception as e:
            if __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {"description": f"Error: {e}", "done": True},
                    }
                )
            return f"Error searching meetings: {e}"

    async def discover_tools(
        self,
        search: str = "",
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Discover available tools on the Envision MCP gateway. Returns tool names and descriptions.

        Use this to find what tools are available before calling them with call_tool.

        :param search: Optional keyword to filter tools (e.g., "procore", "slack", "budget")
        :return: List of matching tools with descriptions
        """
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {"description": "Discovering tools...", "done": False},
                }
            )

        try:
            await self._ensure_initialized()

            # Use the built-in tool discovery if available
            if search:
                result = await self._mcp_request(
                    "tools/call",
                    {
                        "name": "discover_tools_for_query",
                        "arguments": {"query": search, "top_k": 10},
                    },
                )
                if __event_emitter__:
                    await __event_emitter__(
                        {
                            "type": "status",
                            "data": {"description": "Done", "done": True},
                        }
                    )
                return self._format_tool_result(result)

            # Fall back to listing all tools
            result = await self._mcp_request("tools/list")

            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "Done", "done": True}}
                )

            if result and "result" in result:
                tools = result["result"].get("tools", [])
                lines = [f"**{len(tools)} tools available**\n"]
                for t in tools[:50]:  # Cap display at 50
                    desc = (t.get("description") or "")[:80]
                    lines.append(f"- **{t['name']}**: {desc}")
                if len(tools) > 50:
                    lines.append(
                        f"\n... and {len(tools) - 50} more. Use `search` parameter to filter."
                    )
                return "\n".join(lines)

            return self._format_tool_result(result)

        except Exception as e:
            if __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {"description": f"Error: {e}", "done": True},
                    }
                )
            return f"Error discovering tools: {e}"

    async def call_tool(
        self,
        tool_name: str,
        arguments: str = "{}",
        __user__: dict = {},
        __event_emitter__: Callable[[Any], Any] = None,
    ) -> str:
        """Call any tool on the Envision MCP gateway by name. Use discover_tools first to find available tools.

        :param tool_name: Exact tool name (e.g., "procore_get_rfis", "slack_send_message", "gmail_search")
        :param arguments: JSON string of arguments (e.g., '{"query": "open RFIs", "project_id": "12345"}')
        :return: Tool execution result
        """
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {"description": f"Calling {tool_name}...", "done": False},
                }
            )

        try:
            await self._ensure_initialized()

            try:
                args = (
                    json.loads(arguments) if isinstance(arguments, str) else arguments
                )
            except json.JSONDecodeError:
                return f"Error: Invalid JSON in arguments: {arguments}"

            result = await self._mcp_request(
                "tools/call",
                {
                    "name": tool_name,
                    "arguments": args,
                },
            )

            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "Done", "done": True}}
                )

            return self._format_tool_result(result)

        except Exception as e:
            if __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {"description": f"Error: {e}", "done": True},
                    }
                )
            return f"Error calling {tool_name}: {e}"

    def _format_tool_result(self, result: dict) -> str:
        """Format MCP JSON-RPC result into a readable string."""
        if not result:
            return "No response received from MCP server."

        if "error" in result:
            err = result["error"]
            if isinstance(err, dict):
                return f"Error {err.get('code', '')}: {err.get('message', str(err))}"
            return f"Error: {err}"

        if "result" in result:
            content = result["result"]

            # tools/call returns {"content": [{"type": "text", "text": "..."}]}
            if isinstance(content, dict) and "content" in content:
                parts = []
                for item in content["content"]:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            parts.append(item.get("text", ""))
                        elif item.get("type") == "image":
                            parts.append(f"[Image: {item.get('mimeType', 'image')}]")
                        else:
                            parts.append(json.dumps(item, indent=2))
                    else:
                        parts.append(str(item))
                return "\n".join(parts) if parts else "Empty response."

            # Other results
            if isinstance(content, str):
                return content
            return json.dumps(content, indent=2, default=str)

        return json.dumps(result, indent=2, default=str)
