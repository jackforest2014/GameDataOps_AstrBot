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
        logger.info(
            f"[game_data_ai] api.request POST {path} "
            f"user={feishu_user_id} msg={feishu_message_id} "
            f"session={session_id or ''} question={question[:80]}"
        )
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, data=raw_body, headers=headers) as resp:
                text = await resp.text()
                try:
                    payload = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    payload = {"status": "failed", "error": {"code": "invalid_json", "message": text}}
                if resp.status >= 400 and "status" not in payload:
                    payload = {
                        "status": "failed",
                        "error": {"code": f"http_{resp.status}", "message": text},
                    }
                answer = payload.get("answer") or {}
                rendering = payload.get("rendering") or {}
                logger.info(
                    f"[game_data_ai] api.response status={payload.get('status')} "
                    f"http={resp.status} trace={payload.get('trace_id')} "
                    f"rendering={rendering.get('preferred')} "
                    f"title={answer.get('title', '')} "
                    f"metrics={len(answer.get('metrics') or [])} "
                    f"chart_series={answer.get('chart_series') or []}"
                )
                if payload.get("error"):
                    err = payload["error"]
                    logger.warning(
                        f"[game_data_ai] api.error code={err.get('code')} msg={err.get('message')}"
                    )
                return payload

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
        path = "/api/v1/feedback"
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
        raw_body = json.dumps(body_obj, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            **build_identity_headers(
                shared_secret=self.shared_secret,
                feishu_user_id=feishu_user_id,
                feishu_chat_id=feishu_chat_id,
                feishu_message_id=client_action_id,
                method="POST",
                path=path,
                raw_body=raw_body,
                service_token=self.service_token,
            ),
        }
        url = f"{self.base_url}{path}"
        logger.info(
            f"[game_data_ai] api.request POST {path} trace={trace_id} "
            f"type={feedback_type} action_id={client_action_id}"
        )
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, data=raw_body, headers=headers) as resp:
                text = await resp.text()
                try:
                    payload = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    payload = {
                        "status": "failed",
                        "error": {"code": "invalid_json", "message": text},
                    }
                logger.info(
                    f"[game_data_ai] api.response feedback status={payload.get('status')} "
                    f"http={resp.status} feedback_id={payload.get('feedback_id')}"
                )
                return payload
