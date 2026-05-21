"""
game_data_ai 飞书问数插件（MVP batch 3: A01–A23）

- p2p 消息 → POST /api/v1/query/metric
- 群聊 → p2p_only 提示
- 结果 → 飞书交互卡片（lark Json）或纯文本降级
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

# AstrBot 以模块方式加载 main.py，需把插件根目录加入 path 才能 import 子包 game_data_ai
_PLUGIN_ROOT = Path(__file__).resolve().parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

# WebUI「重载插件」会重新执行 main，但 game_data_ai.* 可能仍留在 sys.modules（旧 cards.py）
for _mod in list(sys.modules):
    if _mod == "game_data_ai" or _mod.startswith("game_data_ai."):
        del sys.modules[_mod]

from astrbot.api import logger, star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.platform import MessageType

from game_data_ai.cards import (
    build_denied_plain,
    build_p2p_only_plain,
    build_progress_plain,
    build_result_card_json,
    card_json_to_plain_fallback,
)
from game_data_ai.card_action import register_feedback_card_handler
from game_data_ai.client import GameDataAIClient
from game_data_ai.routing import detect_route
from game_data_ai.routing_resolve import resolve_route
from game_data_ai.schedule_cancel_card import (
    build_cancel_preview_card,
    build_schedule_created_card,
)
from game_data_ai.session_notice import build_session_closed_card_json


def _feishu_ids(event: AstrMessageEvent) -> tuple[str, str, str]:
    msg = event.message_obj
    user_id = msg.sender.user_id if msg.sender else ""
    message_id = msg.message_id or ""
    raw = msg.raw_message
    chat_id = getattr(raw, "chat_id", None) if raw is not None else None
    if not chat_id:
        chat_id = msg.session_id or user_id
    return user_id, str(chat_id), message_id


@star.register(
    "astrbot_plugin_game_data_ai",
    "game_data_ai",
    "飞书单聊问数 · game_data_ai 平台",
    "0.1.0",
    "https://github.com/jackforest2014/game_data_ai",
)
class GameDataAIPlugin(star.Star):
    def __init__(self, context: star.Context) -> None:
        super().__init__(context)
        self.client = GameDataAIClient()
        self._cancel_candidates: dict[str, list[str]] = {}
        # chat_id -> unix time of last successful query (for date follow-ups)
        self._active_data_chats: dict[str, float] = {}
        register_feedback_card_handler(
            self.client,
            self._send_card_from_action,
            cancel_candidates=self._cancel_candidates,
        )
        self._notify_stop = asyncio.Event()
        self._notify_task: asyncio.Task | None = None
        self._delivery_task: asyncio.Task | None = None
        try:
            loop = asyncio.get_running_loop()
            self._notify_task = loop.create_task(self._session_notify_loop())
            self._delivery_task = loop.create_task(self._delivery_poll_loop())
        except RuntimeError:
            pass
        logger.info("[game_data_ai] 已注册飞书卡片按钮回调 card.action.trigger")

    async def _send_card_from_action(self, _event, card_json: dict, chat_id: str) -> None:
        """从 card.action.trigger 异步下发追问卡片（不依赖 LarkMessageEvent）。"""
        try:
            from astrbot.core.platform.sources.lark.lark_adapter import (
                LarkPlatformAdapter,
            )
            from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent
        except ImportError:
            return False
        adapter = None
        for inst in self.context.platform_manager.get_insts():
            if isinstance(inst, LarkPlatformAdapter):
                adapter = inst
                break
        if adapter is None:
            logger.warning("[game_data_ai] 未找到 Lark 适配器，追问卡片未发送")
            return False
        lark_api = getattr(adapter, "lark_api", None)
        if lark_api is None:
            logger.warning("[game_data_ai] Lark API 客户端不可用")
            return False
        try:
            ok = await LarkMessageEvent._send_interactive_card(
                card_json,
                lark_client=lark_api,
                reply_message_id=None,
                receive_id=chat_id,
                receive_id_type="chat_id",
            )
            if ok:
                logger.info(f"[game_data_ai] lark.correction_card_sent chat={chat_id}")
            else:
                logger.warning("[game_data_ai] lark.correction_card_sent failed")
            return ok
        except Exception as e:
            logger.warning(f"[game_data_ai] 追问卡片发送失败: {e}")
            return False

    async def terminate(self) -> None:
        self._notify_stop.set()
        for task in (self._notify_task, self._delivery_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def _session_notify_loop(self) -> None:
        interval = float(os.getenv("GAME_DATA_AI_NOTIFY_POLL_SEC", "5"))
        if interval < 2:
            interval = 2
        logger.info(f"[game_data_ai] session.notify_poll started interval={interval}s")
        while not self._notify_stop.is_set():
            try:
                payload = await self.client.poll_session_notifications(limit=20)
                for item in payload.get("notifications") or []:
                    chat_id = item.get("feishu_chat_id") or ""
                    message = item.get("message") or ""
                    idle_min = int(item.get("idle_minutes") or 1)
                    if not chat_id or not message:
                        continue
                    card = build_session_closed_card_json(
                        message=message,
                        idle_minutes=idle_min,
                    )
                    ok = await self._send_card_from_action(None, card, chat_id)
                    if ok:
                        logger.info(
                            f"[game_data_ai] lark.session_closed_notice chat={chat_id} "
                            f"idle_min={idle_min}"
                        )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"[game_data_ai] session.notify_poll error: {e}")
            try:
                await asyncio.wait_for(self._notify_stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    async def _try_send_lark_card(
        self,
        event: AstrMessageEvent,
        card_json: dict,
        chat_id: str,
        reply_message_id: str,
    ) -> bool:
        try:
            from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent
        except ImportError:
            return False
        if not isinstance(event, LarkMessageEvent) or event.bot is None:
            return False
        try:
            return await LarkMessageEvent._send_interactive_card(
                card_json,
                lark_client=event.bot,
                reply_message_id=reply_message_id or None,
                receive_id=chat_id,
                receive_id_type="chat_id",
            )
        except Exception as e:
            logger.warning(f"[game_data_ai] 飞书卡片发送失败，将降级文本: {e}")
            return False

    @filter.command("gd_query")
    async def gd_query_cmd(self, event: AstrMessageEvent) -> None:
        """显式触发问数：/gd_query 朱雀活动流水怎么样"""
        text = event.message_str.removeprefix("/gd_query").strip()
        if not text:
            yield event.plain_result("用法：/gd_query <自然语言问题>")
            return
        async for result in self._handle_query(event, text):
            yield result

    @filter.platform_adapter_type(filter.PlatformAdapterType.LARK)
    @filter.event_message_type(filter.EventMessageType.ALL, priority=5)
    async def on_lark_message(self, event: AstrMessageEvent) -> None:
        """飞书消息：群聊拒绝；单聊数据类问题走平台 API。"""
        msg_type = event.message_obj.type
        text = (event.message_str or "").strip()

        user_id, chat_id, message_id = _feishu_ids(event)

        if msg_type == MessageType.GROUP_MESSAGE:
            route = await resolve_route(
                self.client,
                text,
                user_id=user_id,
                chat_id=chat_id,
                message_id=message_id,
                active_data_chats=self._active_data_chats,
            )
            if route not in ("ignore", ""):
                yield event.plain_result(build_p2p_only_plain())
                event.stop_event()
            return

        if msg_type != MessageType.FRIEND_MESSAGE:
            return

        route = await resolve_route(
            self.client,
            text,
            user_id=user_id,
            chat_id=chat_id,
            message_id=message_id,
            active_data_chats=self._active_data_chats,
        )
        if route in ("ignore", ""):
            return
        if route == "cancel":
            async for result in self._handle_cancel(event, text):
                yield result
        elif route == "schedule":
            async for result in self._handle_schedule(event, text):
                yield result
        else:
            async for result in self._handle_query(event, text):
                yield result
        event.stop_event()

    async def _delivery_poll_loop(self) -> None:
        interval = float(os.getenv("GAME_DATA_AI_DELIVERY_POLL_SEC", "30"))
        if interval < 10:
            interval = 10
        logger.info(f"[game_data_ai] delivery.poll started interval={interval}s")
        while not self._notify_stop.is_set():
            try:
                payload = await self.client.poll_schedule_deliveries(pending=True)
                for item in payload.get("deliveries") or []:
                    chat_id = item.get("feishu_chat_id") or ""
                    qpayload = item.get("payload") or {}
                    if not chat_id or not qpayload:
                        continue
                    card = build_result_card_json(qpayload)
                    header = card.get("header") or {}
                    title = header.get("title") or {}
                    title["content"] = "【定时洞察】" + (title.get("content") or "分析结果")
                    header["template"] = "wathet"
                    ok = await self._send_card_from_action(None, card, chat_id)
                    if ok:
                        await self.client.ack_delivery(int(item.get("id") or 0))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"[game_data_ai] delivery.poll error: {e}")
            try:
                await asyncio.wait_for(self._notify_stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    async def _handle_schedule(self, event: AstrMessageEvent, question: str):
        user_id, chat_id, message_id = _feishu_ids(event)
        yield event.plain_result("正在创建定时推送…")
        try:
            resp = await self.client.create_schedule(
                feishu_user_id=user_id,
                feishu_chat_id=chat_id,
                feishu_message_id=message_id,
                question=question,
            )
        except Exception as e:
            yield event.plain_result(f"创建定时任务失败：{e}")
            return
        if resp.get("error"):
            yield event.plain_result(str(resp.get("error")))
            return
        card = build_schedule_created_card(resp)
        sent = await self._try_send_lark_card(event, card, chat_id, message_id)
        if not sent:
            yield event.plain_result(
                f"已创建定时推送：{resp.get('label', '')}，下次 {resp.get('next_run_at', '')}"
            )

    async def _handle_cancel(self, event: AstrMessageEvent, question: str):
        user_id, chat_id, message_id = _feishu_ids(event)
        yield event.plain_result("正在加载可取消的定时任务…")
        try:
            preview = await self.client.cancel_preview(
                feishu_user_id=user_id,
                feishu_chat_id=chat_id,
                feishu_message_id=message_id,
                question=question,
            )
        except Exception as e:
            yield event.plain_result(f"取消预览失败：{e}")
            return
        token = preview.get("action_token", "")
        if token:
            self._cancel_candidates[token] = [
                it.get("schedule_id", "") for it in preview.get("items") or []
            ]
        card = build_cancel_preview_card(preview)
        sent = await self._try_send_lark_card(event, card, chat_id, message_id)
        if not sent:
            items = preview.get("items") or []
            lines = "\n".join(f"- {it.get('label', '')}" for it in items[:10])
            yield event.plain_result(f"请选择要取消的任务（请在卡片中操作）：\n{lines}")

    async def _handle_query(self, event: AstrMessageEvent, question: str):
        user_id, chat_id, message_id = _feishu_ids(event)
        if not user_id or not message_id:
            yield event.plain_result("无法识别飞书用户或消息 ID，请重试。")
            return

        yield event.plain_result(build_progress_plain())

        try:
            payload = await self.client.query_metric(
                feishu_user_id=user_id,
                feishu_chat_id=chat_id,
                feishu_message_id=message_id,
                question=question,
                chat_type="p2p",
                session_id=f"sess_{chat_id}",
            )
        except Exception as e:
            logger.error(f"[game_data_ai] API 调用失败: {e}")
            yield event.plain_result(f"平台暂时不可用：{e}")
            return

        status = payload.get("status")
        if status == "failed":
            err = payload.get("error") or {}
            if err.get("code") == "audit_write_failed":
                yield event.plain_result(
                    "分析结果暂未下发（审计写入失败），请稍后重试或联系管理员。"
                )
                return

        if status == "answered":
            self._active_data_chats[chat_id] = time.time()
            from game_data_ai.cards import build_result_cards_json

            cards = build_result_cards_json(payload)
            logger.info(
                f"[game_data_ai] lark.send_cards chat={chat_id} "
                f"trace={payload.get('trace_id')} "
                f"count={len(cards)} "
                f"mode={(payload.get('rendering') or {}).get('preferred')}"
            )
            sent_card = False
            for i, card in enumerate(cards):
                ok = await self._try_send_lark_card(event, card, chat_id, message_id)
                sent_card = sent_card or ok
                if ok:
                    logger.info(
                        f"[game_data_ai] lark.card_sent ok {i + 1}/{len(cards)}"
                    )
                else:
                    logger.warning(
                        f"[game_data_ai] lark.card_sent failed {i + 1}/{len(cards)}"
                    )
                if i + 1 < len(cards):
                    await asyncio.sleep(0.35)
            if sent_card and len(cards) > 1:
                logger.info(f"[game_data_ai] lark.cards_all_sent n={len(cards)}")
            elif not sent_card:
                logger.warning("[game_data_ai] lark.card_sent failed, fallback text")
            answer = payload.get("answer") or {}
            if not sent_card:
                yield event.plain_result(
                    f"【{answer.get('title', '分析结果')}】\n"
                    f"{answer.get('summary', '')}\n"
                    + "\n".join(f"- {f}" for f in (answer.get("facts") or [])[:5])
                    + f"\n\ntrace: {payload.get('trace_id', '')}\n"
                    f"模板: {answer.get('template_id', '')}\n"
                    f"口径: {answer.get('methodology', '')}"
                )
            return

        if status == "denied":
            err = payload.get("error") or {}
            yield event.plain_result(build_denied_plain(err))
            if err.get("code") == "project_unresolved":
                yield event.plain_result("请补充项目名后重试，例如：「仙魔项目活动流水怎么样？」")
            return

        err = payload.get("error") or {}
        yield event.plain_result(
            build_denied_plain(err)
            if err
            else card_json_to_plain_fallback(payload)
        )
