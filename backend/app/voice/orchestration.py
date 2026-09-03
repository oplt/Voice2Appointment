"""Local LLM/tool orchestration used by the hybrid voice pipeline."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from app.calendars.tool_schemas import AGENT_SYSTEM_PROMPT, VOICE_TOOL_DEFINITIONS
from app.calendars.tools import FUNCTION_MAP
from app.core.config import settings
from app.voice.dates import get_current_date_context


class OpenAICompatibleOrchestrator:
    """Keep conversation state and execute only the existing appointment tools."""

    def __init__(self, *, timezone_name: str) -> None:
        prompt = AGENT_SYSTEM_PROMPT.format(
            current_date_context=get_current_date_context(
                timezone_name=timezone_name
            )
        )
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": prompt}]

    async def respond(self, transcript: str) -> str:
        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY is required for VOICE_PIPELINE=hybrid")
        self.messages.append({"role": "user", "content": transcript})
        for _attempt in range(4):
            message = await self._completion()
            self.messages.append(message)
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                content = str(message.get("content") or "").strip()
                if not content:
                    raise RuntimeError("LLM returned an empty response")
                return content
            for tool_call in tool_calls:
                function = tool_call.get("function") or {}
                name = str(function.get("name") or "")
                if name not in FUNCTION_MAP:
                    result = {"error": f"Unknown function: {name}"}
                else:
                    try:
                        arguments = json.loads(function.get("arguments") or "{}")
                        result = await asyncio.to_thread(FUNCTION_MAP[name], **arguments)
                    except (TypeError, ValueError, json.JSONDecodeError) as exc:
                        result = {"error": f"Invalid tool arguments: {exc}"}
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id"),
                        "content": json.dumps(result),
                    }
                )
        raise RuntimeError("LLM exceeded the tool-call limit")

    async def _completion(self) -> dict[str, Any]:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": definition["name"],
                    "description": definition["description"],
                    "parameters": definition["parameters"],
                },
            }
            for definition in VOICE_TOOL_DEFINITIONS
        ]
        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{settings.llm_base_url}/chat/completions",
                headers=headers,
                json={
                    "model": settings.llm_model,
                    "messages": self.messages,
                    "tools": tools,
                    "tool_choice": "auto",
                    "temperature": 0.2,
                },
            )
            response.raise_for_status()
        payload = response.json()
        try:
            message = payload["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("LLM returned an invalid response") from exc
        if not isinstance(message, dict):
            raise RuntimeError("LLM returned an invalid message")
        return message

