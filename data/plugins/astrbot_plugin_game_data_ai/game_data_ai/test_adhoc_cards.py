"""Unit tests for adhoc_table Feishu card rendering."""

from game_data_ai.cards import (
    _adhoc_table_element,
    _adhoc_table_markdown,
    _append_native_table_or_markdown,
    _section_header_md,
    _section_header_element,
    _wow_week_compare_table_element,
    build_adhoc_result_card_json,
    build_result_cards_json,
)


def test_adhoc_table_markdown_rich_keeps_font_and_br_without_truncation():
    """render_mode=markdown cells carry inline <font>/<br> (colored 变化量+变化率);
    rich rendering must keep the markup intact and must not truncate (>48 chars)."""
    long_delta = "404.81万元<br><font color='red'>−41.67万元 ↓10.3%</font>"
    md = _adhoc_table_markdown(
        {
            "columns": [
                {"key": "window", "label": "对比口径", "type": "string"},
                {"key": "revenue", "label": "游戏收入(充值)", "type": "string"},
            ],
            "rows": [{"window": "前一天（日环比）", "revenue": long_delta}],
            "row_count": 1,
            "render_mode": "markdown",
        },
        heading=None,
        rich=True,
    )
    assert "<font color='red'>" in md  # color preserved
    assert "<br>" in md  # second line preserved
    assert "↓10.3%" in md and "…" not in md  # not truncated


def test_force_markdown_table_does_not_consume_native_budget():
    elements: list[dict] = []
    table_seq = [1]
    native_budget = [0]  # no native slots left, but markdown still renders
    _append_native_table_or_markdown(
        elements,
        table={
            "columns": [{"key": "a", "label": "A", "type": "string"}],
            "rows": [{"a": "x<br><font color='green'>+1 ↑5%</font>"}],
            "row_count": 1,
            "render_mode": "markdown",
        },
        table_seq=table_seq,
        native_budget=native_budget,
    )
    joined = "".join(e.get("content", "") for e in elements if e.get("tag") == "markdown")
    assert "<font color='green'>" in joined
    assert table_seq[0] == 1  # native sequence untouched


def test_section_header_md_drops_stage_label_prefix():
    """Chapter label only drives color now; the visible title must not carry the
    redundant "流水构成 · " prefix (链路点3)."""
    md = _section_header_md({"stage_label": "流水构成", "title": "广告消耗(投放)"})
    assert md == "**广告消耗(投放)**"
    assert "流水构成 ·" not in md


def test_adhoc_table_markdown_renders_columns_and_rows():
    md = _adhoc_table_markdown(
        {
            "columns": [
                {"key": "channel", "label": "渠道", "type": "string"},
                {"key": "cnt", "label": "人数", "type": "number"},
            ],
            "rows": [
                {"channel": "ios", "cnt": 120},
                {"channel": "android", "cnt": 340},
            ],
            "row_count": 2,
        }
    )
    assert "渠道" in md and "ios" in md and "340" in md


def test_adhoc_table_markdown_sanitizes_newline_headers_and_drops_sql_caption():
    """Curated section tables use 2-line headers ("对比日\\n2026-06-01"); the
    Markdown fallback must flatten the newline (no phantom rows) and must NOT
    claim it is a raw SQL dump."""
    md = _adhoc_table_markdown(
        {
            "columns": [
                {"key": "product", "label": "充值商品", "type": "string"},
                {"key": "comp", "label": "对比日\n2026-06-01", "type": "string"},
                {"key": "main", "label": "分析日\n2026-06-08", "type": "string"},
            ],
            "rows": [{"product": "36500钻石", "comp": "21.59万元", "main": "8.69万元"}],
            "row_count": 1,
        },
        heading=None,
    )
    header_line = next(line for line in md.splitlines() if "充值商品" in line)
    # Header is a single Markdown row: date wrapped onto the same cell, no break.
    assert "对比日 2026-06-01" in header_line
    assert "分析日 2026-06-08" in header_line
    assert "原始行" not in md and "按需 SQL" not in md
    assert "查询结果" not in md  # heading=None → no redundant title line


def test_section_header_chapter_tint_by_stage_label():
    """章节用底色块区分；按底色深浅选字色：深底(blue/red/purple)白字、浅底(grey)默认深字，
    保证对比度（用户第三轮反馈：深底上深字看不清）。"""
    dark = {"涨跌榜": "purple", "异常": "red", "流水构成": "blue"}
    for stage, color in dark.items():
        el = _section_header_element({"stage_label": stage, "title": f"{stage} · 测试"})
        assert el["tag"] == "column_set"
        assert el["background_style"] == color, stage
        content = el["columns"][0]["elements"][0]["content"]
        assert "**" in content  # bold title
        assert "white" in content, stage  # 深底用白字保证对比度
    # 浅灰底（下钻子章节）仍用默认深字。
    grey = _section_header_element({"stage_label": "下钻", "title": "下钻 · 测试"})
    assert grey["background_style"] == "grey"
    grey_content = grey["columns"][0]["elements"][0]["content"]
    assert "**" in grey_content
    assert "white" not in grey_content


def test_section_header_plain_when_no_stage_tint():
    el = _section_header_element({"stage_label": "其他", "title": "普通段落"})
    assert el["tag"] == "markdown"


def test_adhoc_index_column_compact_text_not_decimal():
    el = _adhoc_table_element(
        {
            "columns": [
                {"key": "idx", "label": "#", "type": "string", "width": "80px"},
                {"key": "name", "label": "活动主名", "type": "string"},
            ],
            "rows": [{"idx": "1", "name": "世界杯活动"}, {"idx": "2", "name": "五一活动"}],
            "row_count": 2,
        },
        element_id="gdTblIdx",
    )
    assert el is not None
    idx_col = el["columns"][0]
    assert idx_col["data_type"] == "text"
    assert idx_col["width"] == "80px"
    assert idx_col["horizontal_align"] == "center"
    assert el["rows"][0]["idx"] == "1"
    assert el["rows"][1]["idx"] == "2"


def test_adhoc_table_element_native_text_and_freeze():
    el = _adhoc_table_element(
        {
            "columns": [
                {"key": "prop_name", "label": "计费点", "type": "string"},
                {"key": "change_amount", "label": "变化金额(元)", "type": "string"},
            ],
            "rows": [
                {
                    "prop_name": "198元灵武召唤礼包",
                    "change_amount": "+160,176",
                },
            ],
            "row_count": 1,
        },
        element_id="gdTbl0",
    )
    assert el is not None
    assert el["tag"] == "table"
    assert el["freeze_first_column"] is True
    assert el["columns"][0]["data_type"] == "text"
    assert el["rows"][0]["prop_name"] == "198元灵武召唤礼包"


def _collect_chart_element_ids(node) -> list[str]:
    """递归收集卡片里所有 tag=='chart' 元素的 element_id。"""
    found: list[str] = []
    if isinstance(node, dict):
        if node.get("tag") == "chart" and node.get("element_id"):
            found.append(node["element_id"])
        for v in node.values():
            found.extend(_collect_chart_element_ids(v))
    elif isinstance(node, list):
        for v in node:
            found.extend(_collect_chart_element_ids(v))
    return found


def _multidim_bar(col: str, label: str) -> dict:
    """模拟后端多维拆分图：chart_id 均为 multidim_*（归一化后同为「multid」）。"""
    return {
        "chart_id": f"multidim_{col}",
        "type": "bar",
        "direction": "horizontal",
        "title": f"{label}拆分 · 昨日流水(人民币元)",
        "labels": ["A", "B"],
        "datasets": [{"name": "流水(人民币元)", "values": [10.0, 20.0]}],
    }


def test_adhoc_multidim_card_chart_element_ids_unique():
    """多维拆分卡片：顶层 charts（第 1 维）与各 section 图（后续维）chart_id 归一化后同名，
    必须共享去重集合，保证 ElementID 全局唯一，否则飞书 300301「Duplicate ID」整卡失败。"""
    payload = {
        "trace_id": "tr_multidim",
        "session_id": "sess_1",
        "answer": {
            "title": "HiggsDomino · 昨日 · 多维度流水拆分",
            "summary": "按 3 个维度拆分。",
            "query_mode": "adhoc_multidim",
            "adhoc_table": {
                "columns": [{"key": "name", "label": "支付渠道", "type": "string"}],
                "rows": [{"name": "A"}],
                "row_count": 1,
            },
            "charts": [_multidim_bar("infull_type", "支付渠道")],
            "sections": [
                {
                    "stage_index": 1,
                    "title": "发布渠道拆分",
                    "summary": "按发布渠道拆分。",
                    "adhoc_table": {
                        "columns": [{"key": "name", "label": "发布渠道", "type": "string"}],
                        "rows": [{"name": "X"}],
                        "row_count": 1,
                    },
                    "charts": [_multidim_bar("channel_type", "发布渠道")],
                },
                {
                    "stage_index": 2,
                    "title": "平台拆分",
                    "summary": "按平台拆分。",
                    "adhoc_table": {
                        "columns": [{"key": "name", "label": "平台", "type": "string"}],
                        "rows": [{"name": "iOS"}],
                        "row_count": 1,
                    },
                    "charts": [_multidim_bar("platform", "平台")],
                },
            ],
        },
    }
    card = build_adhoc_result_card_json(payload)
    ids = _collect_chart_element_ids(card)
    assert len(ids) == 3, f"应渲染 3 张图，实得 {len(ids)}：{ids}"
    assert len(ids) == len(set(ids)), f"图表 ElementID 必须唯一，实得重复：{ids}"


def test_build_adhoc_result_card_json_uses_native_table():
    card = build_adhoc_result_card_json(
        {
            "trace_id": "tr_adhoc",
            "session_id": "sess_1",
            "answer": {
                "title": "仙魔 · 按需查询",
                "summary": "返回 2 行。",
                "query_mode": "adhoc",
                "template_id": "catalog.adhoc",
                "adhoc_table": {
                    "columns": [{"key": "n", "label": "N", "type": "number"}],
                    "rows": [{"n": 1}],
                    "row_count": 1,
                },
                "methodology": "catalog.adhoc",
                "sql_digest": "abc123",
            },
        }
    )
    body = card["body"]["elements"]
    tables = [el for el in body if el.get("tag") == "table"]
    assert len(tables) == 1
    assert tables[0]["columns"][0]["data_type"] == "number"


def test_section_header_gain_loss_use_tinted_background():
    gain = _section_header_element(
        {
            "stage_label": "二",
            "title": "涨幅贡献 Top（按变化金额）",
            "summary": "流水增加的计费点 Top 10。",
        }
    )
    loss = _section_header_element(
        {
            "stage_label": "三",
            "title": "跌幅贡献 Top（按变化金额）",
            "summary": "流水减少的计费点 Top 10。",
        }
    )
    for el, color in ((gain, "green"), (loss, "red")):
        assert el["tag"] == "column_set"
        assert el["background_style"] == color
        content = el["columns"][0]["elements"][0]["content"]
        assert "Top" in content
        assert "white" in content  # 深底(green/red)用白字保证对比度


def test_build_adhoc_sections_use_native_tables():
    card = build_adhoc_result_card_json(
        {
            "trace_id": "tr_wow",
            "session_id": "sess_1",
            "answer": {
                "summary": "双周分析",
                "query_mode": "adhoc",
                "sections": [
                    {
                        "stage_label": "步骤 1",
                        "title": "概况",
                        "adhoc_table": {
                            "columns": [{"key": "a", "label": "A", "type": "string"}],
                            "rows": [{"a": "1"}],
                            "row_count": 1,
                        },
                    },
                    {
                        "stage_label": "步骤 3",
                        "title": "对比",
                        "compare_rows": [
                            {"metric": "流水", "p1": "1", "p2": "2", "delta": "+1"},
                        ],
                    },
                ],
            },
        }
    )
    tables = [el for el in card["body"]["elements"] if el.get("tag") == "table"]
    assert len(tables) == 2
    assert _wow_week_compare_table_element(
        [{"metric": "m", "p1": "1", "p2": "2", "delta": "0"}],
        element_id="t0",
    )["freeze_first_column"]


def test_dashboard_section_title_not_duplicated():
    """大盘 section 表：标题只应由 section header 渲染一次；表前不得再打印一遍同名标题
    （用户反馈「大部分表格的标题都重复了一遍」）。"""
    card = build_adhoc_result_card_json(
        {
            "trace_id": "tr_dash",
            "session_id": "sess_1",
            "answer": {
                "title": "公司大盘日报",
                "summary": "共 2 张表。",
                "query_mode": "dashboard",
                "adhoc_table": {
                    "columns": [{"key": "m", "label": "指标", "type": "string"}],
                    "rows": [{"m": "总流水"}],
                    "row_count": 1,
                    "render_mode": "markdown",
                },
                "sections": [
                    {
                        "title": "窗口汇总",
                        "adhoc_table": {
                            "columns": [{"key": "m", "label": "指标", "type": "string"}],
                            "rows": [{"m": "总流水"}],
                            "row_count": 1,
                            "render_mode": "markdown",
                        },
                    }
                ],
            },
        }
    )

    def _count(token: str) -> int:
        n = 0
        for el in card["body"]["elements"]:
            if el.get("tag") == "markdown" and token in (el.get("content") or ""):
                n += 1
        return n

    assert _count("窗口汇总") == 1, "section title must render exactly once"


def test_build_adhoc_result_card_json_uses_wathet_header():
    card = build_adhoc_result_card_json(
        {
            "trace_id": "tr_adhoc",
            "session_id": "sess_1",
            "answer": {
                "title": "仙魔 · 按需查询",
                "summary": "返回 2 行。",
                "query_mode": "adhoc",
                "template_id": "catalog.adhoc",
                "adhoc_table": {
                    "columns": [{"key": "n", "label": "N", "type": "number"}],
                    "rows": [{"n": 1}],
                    "row_count": 1,
                },
                "methodology": "catalog.adhoc",
                "sql_digest": "abc123",
            },
        }
    )
    assert card["header"]["template"] == "wathet"
    body = card["body"]["elements"]
    assert any(el.get("tag") == "table" for el in body)
    assert any(
        el.get("tag") == "markdown" and "查询结果" in el.get("content", "")
        for el in body
    )


def test_week_compare_change_chart_renders_chart_element():
    card = build_adhoc_result_card_json(
        {
            "trace_id": "tr_wc",
            "session_id": "sess_1",
            "answer": {
                "title": "仙魔 · 近一周付费对比",
                "summary": "本期 vs 上期，金额变化 -5.0%。",
                "query_mode": "adhoc",
                "template_id": "catalog.adhoc",
                "charts": [
                    {
                        "chart_id": "week_compare_delta",
                        "type": "bar",
                        "title": "两期核心指标环比变化（%）",
                        "labels": ["付费金额", "付费人数", "ARPPU"],
                        "datasets": [{"name": "环比%", "values": [-5.0, -2.9, -2.2]}],
                    }
                ],
                "sections": [
                    {
                        "stage_label": "一",
                        "title": "两期汇总对比",
                        "adhoc_table": {
                            "columns": [{"key": "metric", "label": "指标", "type": "string"}],
                            "rows": [{"metric": "付费金额"}],
                            "row_count": 1,
                        },
                    }
                ],
                "facts": ["上期付费金额 14,492,784，本期 13,765,204，变化 -5.0%。"],
                "methodology": "catalog.adhoc",
                "sql_digest": "abc",
            },
        }
    )
    body = card["body"]["elements"]
    # 图表先于"要点"文字出现，实现图文结合（#1）。
    assert any(el.get("tag") == "chart" for el in body)
    assert any(
        el.get("tag") == "markdown" and "要点" in el.get("content", "") for el in body
    )


def test_build_result_cards_json_routes_adhoc():
    cards = build_result_cards_json(
        {
            "trace_id": "tr_x",
            "session_id": "sess_x",
            "answer": {
                "query_mode": "adhoc",
                "summary": "未能完成。",
                "template_id": "catalog.adhoc",
                "notices": [
                    {
                        "level": "warning",
                        "code": "llm_unavailable",
                        "title": "无法生成",
                        "body": "stub",
                    }
                ],
            },
        }
    )
    assert len(cards) == 1
    assert cards[0]["header"]["template"] == "wathet"


# --- B4: illustrated_facts 内嵌图表 -------------------------------------------


def test_illustrated_facts_renders_chart_and_text_per_fact():
    """每个 illustrated_fact 应先渲染小图再渲染文字，且不产生顶层图表块。"""
    payload = {
        "trace_id": "tr_test",
        "answer": {
            "title": "仙魔 · 近一周付费对比",
            "summary": "本期付费略降。",
            "query_mode": "adhoc",
            "template_id": "catalog.adhoc",
            "illustrated_facts": [
                {
                    "text": "上期付费金额 14,303,059，本期 13,936,305，变化 -2.6%。",
                    "chart": {
                        "chart_id": "cmp_pay_amount",
                        "type": "bar",
                        "title": "付费金额（元）",
                        "labels": ["上期\n05/17~05/23", "本期\n05/24~05/30"],
                        "datasets": [{"name": "付费金额（元）", "values": [14303059, 13936305]}],
                        "direction": "vertical",
                    },
                },
                {
                    "text": "上期付费人数 57,178，本期 55,984，变化 -2.1%。",
                    "chart": {
                        "chart_id": "cmp_pay_users",
                        "type": "bar",
                        "title": "付费人数",
                        "labels": ["上期\n05/17~05/23", "本期\n05/24~05/30"],
                        "datasets": [{"name": "付费人数", "values": [57178, 55984]}],
                        "direction": "vertical",
                    },
                },
                {
                    "text": "上期付费率 0.84 %，本期 0.78 %（-0.06 个百分点）。",
                },
            ],
        },
        "rendering": {"preferred": "table"},
    }
    card = build_adhoc_result_card_json(payload)
    elements = card["body"]["elements"]
    tags = [e.get("tag") for e in elements]

    # 应存在 chart_image 元素（两个指标带图）
    chart_elements = [e for e in elements if e.get("tag") == "chart"]
    assert len(chart_elements) >= 2, f"want >= 2 chart elements, got {len(chart_elements)}"

    # 应有「要点」标题
    md_contents = [e.get("content", "") for e in elements if e.get("tag") == "markdown"]
    assert any("要点" in c for c in md_contents)

    # 三个 illustrated_fact 的文字都应出现在卡片中
    all_text = " ".join(md_contents)
    assert "14,303,059" in all_text
    assert "57,178" in all_text or "57178" in all_text
    assert "付费率" in all_text


def test_illustrated_facts_no_top_level_chart_block():
    """有 illustrated_facts 时，不应再有顶层「图表」大标题。"""
    payload = {
        "trace_id": "tr_x",
        "answer": {
            "title": "t",
            "summary": "s",
            "query_mode": "adhoc",
            "charts": [],  # 空顶层图表
            "illustrated_facts": [
                {
                    "text": "上期 100，本期 90，变化 -10%。",
                    "chart": {
                        "chart_id": "c1",
                        "type": "bar",
                        "title": "值",
                        "labels": ["上期", "本期"],
                        "datasets": [{"name": "值", "values": [100, 90]}],
                        "direction": "vertical",
                    },
                }
            ],
        },
        "rendering": {"preferred": "table"},
    }
    card = build_adhoc_result_card_json(payload)
    md_contents = [e.get("content", "") for e in card["body"]["elements"] if e.get("tag") == "markdown"]
    all_text = " ".join(md_contents)
    # 不应有「图表」这个大标题
    assert "**图表**" not in all_text
