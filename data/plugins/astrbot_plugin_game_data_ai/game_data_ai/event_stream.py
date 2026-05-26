"""SSE client for GET /api/v1/events/stream (v1.1 document notifications)."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp
from astrbot.api import logger

from .client import GameDataAIClient

EventHandler = Callable[[str, int, str, dict[str, Any]], Awaitable[None]]


class DocumentSSEHub:
    """One background reader per feishu_user_id; dispatches platform SSE events."""

    def __init__(self, client: GameDataAIClient) -> None:
        self._client = client
        self._tasks: dict[str, asyncio.Task] = {}
        self._last_event_id: dict[str, int] = {}
        self._handlers: list[EventHandler] = []
        self._answered_waiters: dict[str, asyncio.Future] = {}
        self._stop = asyncio.Event()

    def on_event(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    def ensure_connected(self, feishu_user_id: str) -> None:
        if not feishu_user_id:
            return
        if os.getenv("GAME_DATA_AI_SSE_ENABLED", "true").lower() in ("0", "false", "no"):
            return
        task = self._tasks.get(feishu_user_id)
        if task is not None and not task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._tasks[feishu_user_id] = loop.create_task(
            self._run_stream(feishu_user_id),
            name=f"game_data_ai_sse_{feishu_user_id[:12]}",
        )

    async def shutdown(self) -> None:
        self._stop.set()
        for task in list(self._tasks.values()):
            task.cancel()
        for fut in self._answered_waiters.values():
            if not fut.done():
                fut.cancel()
        self._answered_waiters.clear()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    def wait_answered(self, trace_id: str) -> asyncio.Future:
        fut = asyncio.get_running_loop().create_future()
        self._answered_waiters[trace_id] = fut
        return fut

    def cancel_wait(self, trace_id: str) -> None:
        fut = self._answered_waiters.pop(trace_id, None)
        if fut is not None and not fut.done():
            fut.cancel()

    async def _run_stream(self, feishu_user_id: str) -> None:
        backoff = 2.0
        while not self._stop.is_set():
            try:
                await self._read_once(feishu_user_id)
                backoff = 2.0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(
                    f"[game_data_ai] sse.disconnected user={feishu_user_id[:16]} err={e}"
                )
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                return
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 1.5, 30.0)

    async def _read_once(self, feishu_user_id: str) -> None:
        last_id = self._last_event_id.get(feishu_user_id, 0)
        url, headers = self._client.sse_stream_request(feishu_user_id, last_id)
        timeout = aiohttp.ClientTimeout(total=None, sock_read=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise RuntimeError(f"SSE HTTP {resp.status}: {text[:200]}")
                event_name: str | None = None
                data_buf: list[str] = []
                ev_id = last_id
                while not self._stop.is_set():
                    line_b = await resp.content.readline()
                    if not line_b:
                        break
                    line = line_b.decode("utf-8", errors="replace").rstrip("\r\n")
                    if line.startswith("id:"):
                        try:
                            ev_id = int(line[3:].strip())
                        except ValueError:
                            pass
                    elif line.startswith("event:"):
                        event_name = line[6:].strip()
                    elif line.startswith("data:"):
                        data_buf.append(line[5:].strip())
                    elif line == "" and event_name:
                        payload: dict[str, Any] = {}
                        if data_buf:
                            try:
                                payload = json.loads("\n".join(data_buf))
                            except json.JSONDecodeError:
                                payload = {"raw": "\n".join(data_buf)}
                        self._last_event_id[feishu_user_id] = ev_id
                        await self._dispatch(feishu_user_id, ev_id, event_name, payload)
                        event_name = None
                        data_buf = []

    async def _dispatch(
        self,
        feishu_user_id: str,
        ev_id: int,
        event_name: str,
        payload: dict[str, Any],
    ) -> None:
        trace_id = str(payload.get("trace_id") or "")
        if event_name == "document.chat.answered" and trace_id:
            fut = self._answered_waiters.pop(trace_id, None)
            if fut is not None and not fut.done():
                fut.set_result(payload)
        for handler in self._handlers:
            try:
                await handler(feishu_user_id, ev_id, event_name, payload)
            except Exception as e:
                logger.warning(f"[game_data_ai] sse.handler error: {e}")
