"""Message routing for query / schedule / cancel."""

from __future__ import annotations


SCHEDULE_KEYWORDS = ("定时", "每天", "订阅", "推送")
CANCEL_KEYWORDS = ("取消",)
DATA_KEYWORDS = (
    "流水", "付费", "活动", "收入", "营收", "arppu", "数据", "分析", "复盘",
    "朱雀", "仙魔", "怎么样", "看下", "图形", "图表", "可视化", "图形式",
    "版本", "复购", "经营", "日活", "dau",
)


def detect_route(text: str) -> str:
    t = (text or "").strip().lower()
    if not t:
        return "ignore"
    if any(k in t for k in CANCEL_KEYWORDS) and any(
        k in t for k in ("定时", "推送", "订阅")
    ):
        return "cancel"
    if any(k in t for k in SCHEDULE_KEYWORDS):
        if "我的" in t and "任务" in t:
            return "list_schedules"
        return "schedule"
    if any(k in t for k in DATA_KEYWORDS):
        return "query"
    return "ignore"


def should_route_question(text: str) -> bool:
    return detect_route(text) != "ignore"
