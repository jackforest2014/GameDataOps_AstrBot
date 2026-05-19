"""
game_data_ai 飞书问数插件（MVP batch 3: A01–A23）

- p2p 消息 → POST /api/v1/query/metric
- 群聊 → p2p_only 提示
- 结果 → 飞书交互卡片（lark Json）或纯文本降级
"""

from __future__ import annotations

import sys
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

DATA_KEYWORDS = (
    "流水",
    "付费",
    "活动",
    "收入",
    "营收",
    "arppu",
    "数据",
    "分析",
    "复盘",
    "朱雀",
    "仙魔",
    "怎么样",
    "看下",
    "图形",
    "图表",
    "可视化",
    "图形式",
)


def _should_route_question(text: str) -> bool:
    t = (text or "").strip()
    if not t or t.startswith("/"):
        return False
    return any(k in t for k in DATA_KEYWORDS)


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
        register_feedback_card_handler(self.client, self._send_card_from_action)
        logger.info("[game_data_ai] 已注册飞书卡片按钮回调 card.action.trigger")

    async def _send_card_from_action(self, _event, card_json: dict, chat_id: str) -> None:
        """从 card.action.trigger 异步下发追问卡片（不依赖 LarkMessageEvent）。"""
        try:
            from astrbot.core.platform.sources.lark.lark_adapter import (
                LarkPlatformAdapter,
            )
            from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent
        except ImportError:
            return
        adapter = None
        for inst in self.context.platform_manager.get_insts():
            if isinstance(inst, LarkPlatformAdapter):
                adapter = inst
                break
        if adapter is None:
            logger.warning("[game_data_ai] 未找到 Lark 适配器，追问卡片未发送")
            return
        lark_api = getattr(adapter, "lark_api", None)
        if lark_api is None:
            logger.warning("[game_data_ai] Lark API 客户端不可用")
            return
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
        except Exception as e:
            logger.warning(f"[game_data_ai] 追问卡片发送失败: {e}")

    async def terminate(self) -> None:
        pass

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

        if msg_type == MessageType.GROUP_MESSAGE:
            if _should_route_question(text):
                yield event.plain_result(build_p2p_only_plain())
                event.stop_event()
            return

        if msg_type != MessageType.FRIEND_MESSAGE:
            return

        if not _should_route_question(text):
            return

        async for result in self._handle_query(event, text):
            yield result
        event.stop_event()

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
            card = build_result_card_json(payload)
            logger.info(
                f"[game_data_ai] lark.send_card chat={chat_id} "
                f"trace={payload.get('trace_id')} "
                f"mode={(payload.get('rendering') or {}).get('preferred')}"
            )
            sent_card = await self._try_send_lark_card(event, card, chat_id, message_id)
            if sent_card:
                logger.info("[game_data_ai] lark.card_sent ok")
            else:
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
