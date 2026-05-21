"""HTTP client for game_data_ai platform API."""

from __future__ import annotations

import json
import os
from typing import Any

import aiohttp
from astrbot.api import logger

from .identity import build_identity_headers


class GameDataAIClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("GAME_DATA_AI_BASE_URL", "http://127.0.0.1:8080").rstrip(
            "/"
        )
        self.service_token = os.getenv("GAME_DATA_AI_SERVICE_TOKEN", "dev-service-token")
        self.shared_secret = os.getenv("GAME_DATA_AI_SHARED_SECRET", "dev-shared-secret")

    async def _post_json(
        self,
        path: str,
        body_obj: dict[str, Any],
        *,
        feishu_user_id: str,
        feishu_chat_id: str,
        feishu_message_id: str,
        timeout_sec: float = 30,
    ) -> dict[str, Any]:
        raw_body = json.dumps(body_obj, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            **build_identity_headers(
                shared_secret=self.shared_secret,
                feishu_user_id=feishu_user_id,
                feishu_chat_id=feishu_chat_id,
                feishu_message_id=feishu_message_id,
                method="POST",
                path=path,
                raw_body=raw_body,
                service_token=self.service_token,
            ),
        }
        url = f"{self.base_url}{path}"
        timeout = aiohttp.ClientTimeout(total=timeout_sec)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, data=raw_body, headers=headers) as resp:
                text = await resp.text()
                try:
                    payload = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    payload = {"error": {"code": "invalid_json", "message": text}}
                if resp.status >= 400 and "error" not in payload:
                    payload = {"error": {"code": f"http_{resp.status}", "message": text}}
                return payload

    async def classify_route(
        self,
        *,
        feishu_user_id: str,
        feishu_chat_id: str,
        feishu_message_id: str,
        question: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        path = "/api/v1/intent/route"
        body_obj: dict[str, Any] = {"question": question}
        if session_id:
            body_obj["session_id"] = session_id
        timeout = float(os.getenv("GAME_DATA_AI_ROUTE_TIMEOUT_SEC", "20"))
        payload = await self._post_json(
            path,
            body_obj,
            feishu_user_id=feishu_user_id,
            feishu_chat_id=feishu_chat_id,
            feishu_message_id=feishu_message_id,
            timeout_sec=timeout,
        )
        logger.info(
            f"[game_data_ai] route.classify route={payload.get('route')} "
            f"source={payload.get('source')} reason={(payload.get('reason') or '')[:60]}"
        )
        return payload

    async def query_metric(
        self,
        *,
        feishu_user_id: str,
        feishu_chat_id: str,
        feishu_message_id: str,
        question: str,
        chat_type: str = "p2p",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        path = "/api/v1/query/metric"
        body_obj: dict[str, Any] = {
            "feishu_user_id": feishu_user_id,
            "feishu_chat_id": feishu_chat_id,
            "feishu_message_id": feishu_message_id,
            "question": question,
            "chat_type": chat_type,
        }
        if session_id:
            body_obj["session_id"] = session_id
        logger.info(
            f"[game_data_ai] api.request POST {path} "
            f"user={feishu_user_id} msg={feishu_message_id} question={question[:80]}"
        )
        timeout = float(os.getenv("GAME_DATA_AI_QUERY_TIMEOUT_SEC", "90"))
        payload = await self._post_json(
            path,
            body_obj,
            feishu_user_id=feishu_user_id,
            feishu_chat_id=feishu_chat_id,
            feishu_message_id=feishu_message_id,
            timeout_sec=timeout,
        )
        answer = payload.get("answer") or {}
        rendering = payload.get("rendering") or {}
        logger.info(
            f"[game_data_ai] api.response status={payload.get('status')} "
            f"trace={payload.get('trace_id')} rendering={rendering.get('preferred')} "
            f"charts={len(answer.get('charts') or [])}"
        )
        return payload

    async def create_schedule(
        self,
        *,
        feishu_user_id: str,
        feishu_chat_id: str,
        feishu_message_id: str,
        question: str,
    ) -> dict[str, Any]:
        return await self._post_json(
            "/api/v1/schedules",
            {
                "feishu_user_id": feishu_user_id,
                "feishu_chat_id": feishu_chat_id,
                "question": question,
            },
            feishu_user_id=feishu_user_id,
            feishu_chat_id=feishu_chat_id,
            feishu_message_id=feishu_message_id,
        )

    async def cancel_preview(
        self,
        *,
        feishu_user_id: str,
        feishu_chat_id: str,
        feishu_message_id: str,
        question: str = "",
        mode: str = "",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "feishu_user_id": feishu_user_id,
            "feishu_chat_id": feishu_chat_id,
        }
        if question:
            body["question"] = question
        if mode:
            body["mode"] = mode
        return await self._post_json(
            "/api/v1/schedules/cancel-preview",
            body,
            feishu_user_id=feishu_user_id,
            feishu_chat_id=feishu_chat_id,
            feishu_message_id=feishu_message_id,
        )

    async def cancel_confirm(
        self,
        *,
        feishu_user_id: str,
        feishu_chat_id: str,
        feishu_message_id: str,
        action_token: str,
        schedule_ids: list[str],
    ) -> dict[str, Any]:
        return await self._post_json(
            "/api/v1/schedules/cancel-confirm",
            {
                "feishu_user_id": feishu_user_id,
                "action_token": action_token,
                "schedule_ids": schedule_ids,
            },
            feishu_user_id=feishu_user_id,
            feishu_chat_id=feishu_chat_id,
            feishu_message_id=feishu_message_id,
        )

    async def poll_schedule_deliveries(self, *, pending: bool = True) -> dict[str, Any]:
        path = "/api/v1/schedules/deliveries"
        query = "?pending=1" if pending else ""
        headers = {
            **build_identity_headers(
                shared_secret=self.shared_secret,
                feishu_user_id="_delivery_poll",
                feishu_chat_id="_delivery_poll",
                feishu_message_id="poll_deliveries",
                method="GET",
                path=path,
                raw_body=b"",
                service_token=self.service_token,
            ),
        }
        url = f"{self.base_url}{path}{query}"
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                text = await resp.text()
                try:
                    return json.loads(text) if text else {"deliveries": []}
                except json.JSONDecodeError:
                    return {"deliveries": []}

    async def ack_delivery(self, delivery_id: int) -> None:
        await self._post_json(
            f"/api/v1/schedules/deliveries/{delivery_id}/ack",
            {},
            feishu_user_id="_delivery_ack",
            feishu_chat_id="_delivery_ack",
            feishu_message_id=f"ack_{delivery_id}",
            timeout_sec=10,
        )

    async def submit_feedback(
        self,
        *,
        trace_id: str,
        session_id: str,
        feishu_user_id: str,
        feishu_chat_id: str,
        feedback_type: str,
        template_id: str,
        client_action_id: str,
        problem_type: str = "",
        comment: str = "",
    ) -> dict[str, Any]:
        body_obj: dict[str, Any] = {
            "trace_id": trace_id,
            "session_id": session_id,
            "feishu_user_id": feishu_user_id,
            "feishu_chat_id": feishu_chat_id,
            "feedback_type": feedback_type,
            "template_id": template_id,
            "client_action_id": client_action_id,
            "source": "feishu_card",
        }
        if problem_type:
            body_obj["problem_type"] = problem_type
        if comment:
            body_obj["comment"] = comment
        return await self._post_json(
            "/api/v1/feedback",
            body_obj,
            feishu_user_id=feishu_user_id,
            feishu_chat_id=feishu_chat_id,
            feishu_message_id=client_action_id,
            timeout_sec=5,
        )

    async def poll_session_notifications(self, *, limit: int = 20) -> dict[str, Any]:
        path = "/api/v1/session/notifications"
        query = f"?limit={limit}"
        headers = {
            **build_identity_headers(
                shared_secret=self.shared_secret,
                feishu_user_id="_notify_poll",
                feishu_chat_id="_notify_poll",
                feishu_message_id=f"poll_{limit}",
                method="GET",
                path=path,
                raw_body=b"",
                service_token=self.service_token,
            ),
        }
        url = f"{self.base_url}{path}{query}"
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                text = await resp.text()
                try:
                    payload = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    payload = {"notifications": []}
                if resp.status >= 400:
                    return {"notifications": []}
                return payload
