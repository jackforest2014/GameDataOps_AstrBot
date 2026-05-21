"""Routing tests — schedule vs data query."""

from game_data_ai.routing import detect_route


def test_weekly_payment_metrics_is_query_not_schedule():
    q = (
        "请帮我看一下近一周的付费情况（包含每天付费金额、人数、付费率、arppu、arpu、"
        "当日复购率、付费留存（当日付费且次日也付费）），与前一周做对比"
    )
    assert detect_route(q) == "query"


def test_daily_push_phrase_is_schedule():
    assert detect_route("每天早上定时推送日报") == "schedule"


def test_cancel_schedule():
    assert detect_route("取消定时推送") == "cancel"
