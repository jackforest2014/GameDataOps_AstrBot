"""
game_data_ai 飞书问数插件（MVP batch 3 + v1.1 文档）

- p2p 消息 → POST /api/v1/chat/messages（+ GET /api/v1/events/stream）
- 带飞书文档链接 → 入库确认卡 + ingest-decision，最终答案走 SSE
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
from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent

from game_data_ai.cards import (
    build_denied_plain,
    build_p2p_only_plain,
    build_progress_plain,
    build_result_card_json,
    card_json_to_plain_fallback,
)
from game_data_ai.attachments import build_attachments
from game_data_ai.card_action import register_feedback_card_handler
from game_data_ai.client import GameDataAIClient
from game_data_ai.event_stream import DocumentSSEHub
from game_data_ai.auth_card import build_feishu_auth_card_json
from game_data_ai.ingest_card import build_ingest_confirm_card
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
        self.sse_hub = DocumentSSEHub(self.client)
        self.sse_hub.on_event(self._on_document_sse)
        self._cancel_candidates: dict[str, list[str]] = {}
        # chat_id -> unix time of last successful query (for date follow-ups)
        self._active_data_chats: dict[str, float] = {}
        # trace_id -> {chat_id, message_id, confirm_shown}
        self._doc_sessions: dict[str, dict] = {}
        self._user_active_trace: dict[str, str] = {}
        self._user_last_chat: dict[str, str] = {}
        self._ingest_cards_sent: dict[str, set[str]] = {}
        # feishu_user_id -> buffered confirm_required before HTTP returns trace_id
        self._buffered_ingest_confirms: dict[str, list[dict]] = {}
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
        await self.sse_hub.shutdown()
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

    async def _send_ingest_confirm_card(
        self,
        *,
        trace_id: str,
        chat_id: str,
        document_id: str,
        title: str,
    ) -> bool:
        if not trace_id or not chat_id or not document_id:
            return False
        shown = self._ingest_cards_sent.setdefault(trace_id, set())
        if document_id in shown:
            return False
        shown.add(document_id)
        card = build_ingest_confirm_card(
            document_id=document_id,
            title=title,
            trace_id=trace_id,
        )
        ok = await self._send_card_from_action(None, card, chat_id)
        if not ok:
            logger.warning(
                f"[game_data_ai] ingest.card_send_failed trace={trace_id} doc={document_id}"
            )
        return ok

    async def _flush_buffered_ingest_cards(
        self, feishu_user_id: str, trace_id: str, chat_id: str
    ) -> None:
        buffered = self._buffered_ingest_confirms.pop(feishu_user_id, [])
        for data in buffered:
            await self._send_ingest_confirm_card(
                trace_id=trace_id,
                chat_id=chat_id,
                document_id=str(data.get("document_id") or ""),
                title=str(data.get("title") or ""),
            )

    async def _on_document_sse(
        self,
        feishu_user_id: str,
        _ev_id: int,
        event_type: str,
        data: dict,
    ) -> None:
        if event_type == "document.ingest.confirm_required":
            trace_id = str(data.get("trace_id") or "") or self._user_active_trace.get(
                feishu_user_id, ""
            )
            if not trace_id:
                self._buffered_ingest_confirms.setdefault(feishu_user_id, []).append(
                    dict(data)
                )
                return
            chat_id = self._user_last_chat.get(feishu_user_id, feishu_user_id)
            sess = self._doc_sessions.get(trace_id)
            if sess:
                chat_id = sess["chat_id"]
            await self._send_ingest_confirm_card(
                trace_id=trace_id,
                chat_id=chat_id,
                document_id=str(data.get("document_id") or ""),
                title=str(data.get("title") or ""),
            )
            return

        if event_type == "document.kg.candidates":
            candidates = data.get("candidates") or []
            if not candidates:
                return
            trace_id = str(data.get("trace_id") or "")
            chat_id = self._user_last_chat.get(feishu_user_id, feishu_user_id)
            sess = self._doc_sessions.get(trace_id)
            if sess:
                chat_id = sess["chat_id"]
            from game_data_ai.kg_candidate_card import build_kg_candidate_card

            await self._send_card_from_action(None, build_kg_candidate_card(data), chat_id)
            return

        if event_type == "document.verification.result":
            cards = data.get("cards") or []
            if not cards:
                return
            trace_id = str(data.get("trace_id") or "")
            chat_id = self._user_last_chat.get(feishu_user_id, feishu_user_id)
            sess = self._doc_sessions.get(trace_id)
            if sess:
                chat_id = sess["chat_id"]
            from game_data_ai.cards import build_verification_cards_json

            card = build_verification_cards_json(data)
            await self._send_card_from_action(None, card, chat_id)
            return

        if event_type == "document.auth_required":
            auth_url = self.client.abs_url(str(data.get("auth_url") or ""))
            chat_id = self._user_last_chat.get(feishu_user_id, feishu_user_id)
            await self._send_card_from_action(
                None,
                build_feishu_auth_card_json(auth_url=auth_url),
                chat_id,
            )

        if event_type == "document.ingest.progress":
            pct = data.get("percent")
            logger.info(
                f"[game_data_ai] ingest.progress user={feishu_user_id[:16]} "
                f"doc={data.get('document_id')} {pct}% stage={data.get('stage')}"
            )

    def _payload_from_sse_answered(self, data: dict) -> dict:
        return {
            "trace_id": data.get("trace_id"),
            "session_id": data.get("session_id"),
            "status": data.get("status") or "answered",
            "answer": data.get("answer"),
            "error": data.get("error"),
            "rendering": data.get("rendering"),
        }

    async def _deliver_query_payload(
        self,
        event: AstrMessageEvent | None,
        chat_id: str,
        message_id: str,
        payload: dict,
    ) -> list:
        """Send result cards/plain; returns yielded plain fragments if any."""
        status = payload.get("status")
        if status == "failed":
            err = payload.get("error") or {}
            if err.get("code") == "audit_write_failed":
                return [
                    "分析结果暂未下发（审计写入失败），请稍后重试或联系管理员。"
                ]
            if err.get("code") == "document_auth_required":
                auth_url = self.client.abs_url(
                    f"/api/v1/auth/feishu/start?feishu_user_id="
                    f"{payload.get('feishu_user_id', '')}"
                )
                return [
                    "需要飞书文档授权后才能继续。\n"
                    f"请打开：{auth_url}\n授权后重新发送文档链接。"
                ]
            return [build_denied_plain(err) if err else str(err)]

        if status == "denied":
            err = payload.get("error") or {}
            out = [build_denied_plain(err)]
            if err.get("code") == "project_unresolved":
                out.append("请补充项目名后重试，例如：「仙魔项目活动流水怎么样？」")
            return out

        if status != "answered":
            err = payload.get("error") or {}
            return [
                build_denied_plain(err)
                if err
                else card_json_to_plain_fallback(payload)
            ]

        self._active_data_chats[chat_id] = time.time()
        from game_data_ai.cards import build_result_cards_json

        cards = build_result_cards_json(payload)
        logger.info(
            f"[game_data_ai] lark.send_cards chat={chat_id} "
            f"trace={payload.get('trace_id')} count={len(cards)}"
        )
        sent_card = False
        for i, card in enumerate(cards):
            ok = False
            if event is not None:
                # 直发到会话（receive_id），不用 areply 回复路径：进度卡已回复过同一条
                # 用户消息，再次 areply 同一消息会卡住约 30s 才超时（见 14:26 日志）。
                ok = await self._try_send_lark_card(event, card, chat_id, "")
            if not ok:
                ok = await self._send_card_from_action(None, card, chat_id)
            sent_card = sent_card or ok
            if i + 1 < len(cards):
                await asyncio.sleep(0.35)
        if sent_card:
            return []
        answer = payload.get("answer") or {}
        return [
            f"【{answer.get('title', '分析结果')}】\n"
            f"{answer.get('summary', '')}\n"
            + "\n".join(f"- {f}" for f in (answer.get("facts") or [])[:5])
            + f"\n\ntrace: {payload.get('trace_id', '')}"
        ]

    async def _handle_query(self, event: AstrMessageEvent, question: str):
        user_id, chat_id, message_id = _feishu_ids(event)
        if not user_id or not message_id:
            yield event.plain_result("无法识别飞书用户或消息 ID，请重试。")
            return

        self._user_last_chat[user_id] = chat_id
        self.sse_hub.ensure_connected(user_id)
        attachments = build_attachments(question)

        # 飞书原生流式进度卡：streaming_mode=True 配合定时刷新文字制造加载动画。
        # CardKit sequence 必须从 1 开始且严格递增，每次更新前自增。
        progress_card_id: str | None = None
        progress_seq = 0
        progress_ticker: asyncio.Task | None = None
        is_lark = isinstance(event, LarkMessageEvent)
        logger.info(f"[game_data_ai] streaming_card.check is_lark={is_lark} chat={chat_id}")

        # —— 蓝色科技感动画：原地旋转 spinner + 呼吸省略号 ——
        # 旋转类 spinner 不做空间位移，眼睛只感知图形内部形变，低帧率(~2.5fps)下仍流畅；
        # 而位移类（扫描条）会被眼睛追踪，低帧率必然掉帧感。
        _SPIN_PRESETS = {
            "ball": "⣾⣽⣻⢿⡿⣟⣯⣷",          # braille 实心球旋转（默认，最耐看）
            "dots": "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏",       # braille 经典点阵
            "arc": "◜◠◝◞◡◟",               # 弧线旋转
            "circle": "◐◓◑◒",              # 半圆旋转
            "moon": "🌑🌒🌓🌔🌕🌖🌗🌘",       # 月相（自带色彩）
        }
        _anim_spinner = _SPIN_PRESETS.get(
            os.getenv("GAME_DATA_AI_PROGRESS_SPINNER", "ball"), _SPIN_PRESETS["ball"]
        )
        _anim_dots = ["   ", "·  ", "·· ", "···"]  # 呼吸省略号（定宽，避免重绘抖动）

        def _anim_frame(t: int) -> str:
            spin = _anim_spinner[t % len(_anim_spinner)]
            dots = _anim_dots[t % len(_anim_dots)]
            return f"<font color='blue'>{spin} 正在分析中{dots}</font>"

        async def _progress_anim() -> None:
            """定时刷新进度卡文字，制造流畅的“分析中”动画。

            所有帧可见字符等宽（颜色标签不计入显示宽度），避免重绘抖动。
            刷新间隔受网络 RTT 约束，默认 0.4s，可用环境变量覆盖。
            """
            nonlocal progress_seq
            try:
                interval = float(os.getenv("GAME_DATA_AI_PROGRESS_ANIM_SEC", "0.4"))
            except ValueError:
                interval = 0.4
            interval = min(max(interval, 0.2), 2.0)

            i = 1
            # 上限保护：即使异常路径漏调用 _close_progress，也不会无限刷新。
            while i < 720:
                try:
                    await asyncio.sleep(interval)
                    progress_seq += 1
                    await event._update_streaming_text(
                        progress_card_id, _anim_frame(i), progress_seq
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as _exc:
                    logger.debug(f"[game_data_ai] 进度动画刷新失败: {_exc}")
                i += 1

        if is_lark:
            try:
                progress_card_id = await event._create_streaming_card()
                logger.info(f"[game_data_ai] streaming_card.created card_id={progress_card_id}")
                if progress_card_id:
                    sent = await event._send_card_message(
                        progress_card_id,
                        reply_message_id=message_id,
                        receive_id=chat_id,
                        receive_id_type="chat_id",
                    )
                    logger.info(f"[game_data_ai] streaming_card.sent ok={sent}")
                    if sent:
                        # 写入初始文字，触发 streaming_mode 打字动画（sequence 从 1 起）
                        progress_seq += 1
                        upd = await event._update_streaming_text(
                            progress_card_id, _anim_frame(0), progress_seq
                        )
                        logger.info(
                            f"[game_data_ai] streaming_card.text ok={upd} seq={progress_seq}"
                        )
                        # 启动后台动画刷新
                        progress_ticker = asyncio.create_task(_progress_anim())
                    else:
                        progress_card_id = None
            except Exception as _exc:
                logger.warning(f"[game_data_ai] 流式进度卡片失败，回退纯文本: {_exc}")
                progress_card_id = None

        if not progress_card_id:
            logger.info("[game_data_ai] streaming_card.fallback plain_result")
            yield event.plain_result(build_progress_plain())

        async def _close_progress(text: str) -> None:
            """停止动画、写入最终文字并关闭 streaming_mode；无卡片时静默返回。"""
            nonlocal progress_seq, progress_ticker
            if progress_ticker is not None:
                progress_ticker.cancel()
                try:
                    await progress_ticker
                except (asyncio.CancelledError, Exception):
                    pass
                progress_ticker = None
            if not progress_card_id or not isinstance(event, LarkMessageEvent):
                return
            try:
                progress_seq += 1
                await event._update_streaming_text(progress_card_id, text, progress_seq)
                progress_seq += 1
                await event._close_streaming_mode(progress_card_id, progress_seq)
            except Exception as _exc:
                logger.warning(f"[game_data_ai] 关闭流式进度卡片失败: {_exc}")

        try:
            payload = await self.client.chat_messages(
                feishu_user_id=user_id,
                feishu_chat_id=chat_id,
                feishu_message_id=message_id,
                question=question,
                chat_type="p2p",
                session_id=f"sess_{chat_id}",
                attachments=attachments or None,
            )
        except Exception as e:
            await _close_progress("❌ 平台暂时不可用，请稍后重试")
            logger.error(f"[game_data_ai] API 调用失败: {e}")
            yield event.plain_result(f"平台暂时不可用：{e}")
            return

        status = payload.get("status")
        trace_id = str(payload.get("trace_id") or "")

        if status == "failed":
            err = payload.get("error") or {}
            if err.get("code") == "document_auth_required":
                await _close_progress("🔐 需要飞书文档授权，请查看下方链接")
                auth_url = self.client.abs_url(
                    f"/api/v1/auth/feishu/start?feishu_user_id={user_id}"
                )
                yield event.plain_result(
                    "需要飞书文档授权。\n"
                    f"请打开：{auth_url}\n完成后重新发送文档链接。"
                )
                return
            await _close_progress("⚠️ 分析遇到问题，请查看下方详情")
            for line in await self._deliver_query_payload(
                event, chat_id, message_id, payload
            ):
                yield event.plain_result(line)
            return

        if trace_id:
            self._user_active_trace[user_id] = trace_id
            self._doc_sessions[trace_id] = {
                "chat_id": chat_id,
                "message_id": message_id,
            }

        ingest_offer = payload.get("ingest_offer") or {}
        if trace_id and ingest_offer:
            offer_trace = str(ingest_offer.get("trace_id") or trace_id)
            for doc in ingest_offer.get("documents") or []:
                await self._send_ingest_confirm_card(
                    trace_id=offer_trace,
                    chat_id=chat_id,
                    document_id=str(doc.get("document_id") or ""),
                    title=str(doc.get("title") or ""),
                )
            await self._flush_buffered_ingest_cards(user_id, offer_trace, chat_id)

        # Legacy: old backend may still return awaiting_ingest_decision without answer.
        if status == "awaiting_ingest_decision" and not payload.get("answer"):
            await _close_progress("📄 文档已解析，等待入库确认")
            for doc in payload.get("pending_documents") or []:
                await self._send_ingest_confirm_card(
                    trace_id=trace_id,
                    chat_id=chat_id,
                    document_id=str(doc.get("document_id") or ""),
                    title=str(doc.get("title") or ""),
                )
            yield event.plain_result(
                "文档已解析。若未看到入库卡片，请重载插件后重试；分析结果将随后返回。"
            )
            return

        await _close_progress("✅ 分析完成，结果见下方")
        for line in await self._deliver_query_payload(
            event, chat_id, message_id, payload
        ):
            yield event.plain_result(line)
