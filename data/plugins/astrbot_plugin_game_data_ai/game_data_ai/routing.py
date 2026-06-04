"""Message routing for query / schedule / cancel.

Production: AstrBot calls Go POST /api/v1/intent/route (LLM semantic).
detect_route() remains as offline fallback when API unavailable.
"""

from __future__ import annotations

import os
import re
import time

from .attachments import build_attachments

# 定时：用短语，避免「每天付费金额」里的「每天」误判
SCHEDULE_PHRASES = (
    "定时推送",
    "定时订阅",
    "定时任务",
    "定时发送",
    "每天推送",
    "每日推送",
    "每周推送",
    "订阅推送",
)
CANCEL_KEYWORDS = ("取消",)
DATA_KEYWORDS = (
    "流水", "付费", "活动", "收入", "营收", "arppu", "arpu", "数据", "分析", "复盘",
    "留存", "付费率", "复购率", "对比", "近一周", "近7日", "近七日", "上周", "前一周",
    "朱雀", "仙魔", "怎么样", "看下", "帮我看", "图形", "图表", "可视化", "图形式",
    "版本", "复购", "经营", "日活", "dau", "人数",
)

# 同会话追问：仅日期/展示方式，无「流水」等关键词时仍走问数 API
DATE_DOT_RE = re.compile(r"\d{1,2}\.\d{1,2}")
DATE_MD_RE = re.compile(r"\d{1,2}[-/月]\d{1,2}")
DATE_RANGE_HINTS = ("从", "到", "至", "~", "之间", "的呢", "那", "还", "呢")
DISPLAY_REFINEMENT = ("图形", "图表", "可视化", "表格", "图形式")

# 上一轮问数成功后，在此窗口内允许日期追问
DATA_CHAT_TTL_SEC = 30 * 60


def _is_schedule_intent(t: str) -> bool:
    if "我的" in t and "任务" in t:
        return True
    if any(p in t for p in SCHEDULE_PHRASES):
        return True
    if "定时" in t and any(x in t for x in ("推送", "订阅", "任务", "发送")):
        return True
    if ("每天" in t or "每日" in t) and any(
        x in t for x in ("推送", "订阅", "发我", "发送", "报告")
    ):
        return True
    return False


def _is_data_intent(t: str) -> bool:
    return any(k in t for k in DATA_KEYWORDS)


def detect_route(text: str) -> str:
    t = (text or "").strip().lower()
    if not t:
        return "ignore"
    if build_attachments(text or ""):
        return "query"
    if any(k in t for k in ("飞书文档", "wiki", "配置文档", "文档里", "文档中")):
        return "query"
    if any(k in t for k in CANCEL_KEYWORDS) and any(
        k in t for k in ("定时", "推送", "订阅")
    ):
        return "cancel"
    # 明确定时短语优先
    if any(p in t for p in SCHEDULE_PHRASES):
        if "我的" in t and "任务" in t:
            return "list_schedules"
        return "schedule"
    # 数据问数优先于弱定时信号，避免「每天付费」「付费留存」等误判
    if _is_data_intent(t):
        return "query"
    if _is_schedule_intent(t):
        if "我的" in t and "任务" in t:
            return "list_schedules"
        return "schedule"
    if is_date_follow_up(text):
        return "query"
    if _is_chitchat_intent(t):
        return "chitchat"
    return "ignore"


# 纯打招呼 / 问助手是谁能做什么（PRD §5.3.3 d）：后端拟人作答，前端发纯文本即可
GREETINGS = (
    "你好", "您好", "你好啊", "在吗", "在么", "嗨", "哈喽", "hi", "hello", "hey",
    "早上好", "下午好", "晚上好", "谢谢", "多谢", "辛苦了", "再见", "拜拜",
)
CHITCHAT_KEYWORDS = (
    "你是谁", "你叫什么", "你能做什么", "你会做什么", "你能干什么", "你是什么", "自我介绍",
)


def _is_chitchat_intent(t: str) -> bool:
    s = (t or "").strip()
    if s in GREETINGS:
        return True
    return any(k in s for k in CHITCHAT_KEYWORDS)


def is_date_follow_up(text: str) -> bool:
    """口语日期区间或追问（如「从5.1 到 5.10 的呢？」）。"""
    t = (text or "").strip()
    if not t:
        return False
    has_date = bool(DATE_DOT_RE.search(t) or DATE_MD_RE.search(t))
    if not has_date:
        return False
    if any(h in t for h in DATE_RANGE_HINTS):
        return True
    if "到" in t or "至" in t:
        return True
    return False


def is_display_refinement(text: str) -> bool:
    t = (text or "").strip()
    return any(k in t for k in DISPLAY_REFINEMENT)


def should_route_question(
    text: str,
    *,
    chat_id: str = "",
    active_data_chats: dict[str, float] | None = None,
) -> bool:
    if detect_route(text) != "ignore":
        return True
    if not chat_id or not active_data_chats:
        return False
    ts = active_data_chats.get(chat_id)
    if not ts or time.time() - ts > DATA_CHAT_TTL_SEC:
        return False
    if is_date_follow_up(text) or is_display_refinement(text):
        return True
    return False
