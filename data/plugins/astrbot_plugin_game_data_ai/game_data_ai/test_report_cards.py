"""Unit tests for structured report (answer.report) Feishu card rendering."""

from game_data_ai.cards import (
    _clean_citation_snippet,
    _lineage_rag_block,
    _report_bullet_line,
    _report_elements,
    _report_header_element,
    _report_paragraph_md,
    _report_section_elements,
    build_report_card_json,
    build_result_cards_json,
    build_verification_cards_json,
)


def _sample_payload() -> dict:
    return {
        "trace_id": "tr_x",
        "session_id": "s1",
        "answer": {
            "title": "文档问答",
            "summary": "概述句。",
            "facts": ["发现：版本空窗期"],
            "report": {
                "sections": [
                    {
                        "level": 1,
                        "title": "结论概述",
                        "paragraphs": ["数据下滑由**版本空窗**导致。"],
                    },
                    {
                        "level": 1,
                        "title": "关键发现与假设检验",
                        "bullets": [
                            {"kind": "finding", "text": "发现：版本空窗期"},
                            {"kind": "forecast", "text": "预判：v3950 减缓下滑"},
                        ],
                    },
                ]
            },
        },
        "rendering": {"preferred": "table"},
    }


def test_header_element_is_full_width_colored_bar():
    el = _report_header_element("结论概述", 1)
    assert el["tag"] == "column_set"
    assert el["background_style"] == "blue"
    md = el["columns"][0]["elements"][0]["content"]
    assert "**结论概述**" in md and "white" in md


def test_paragraph_indents_and_strips_heading():
    out = _report_paragraph_md("### 结论概述 正文")
    assert out.startswith("\u3000\u3000")
    assert "#" not in out  # markdown heading must not survive (avoids big font)


def test_bullet_kind_colors():
    assert "blue" in _report_bullet_line({"kind": "finding", "text": "发现：x"})
    assert "purple" in _report_bullet_line({"kind": "forecast", "text": "预判：y"})
    assert _report_bullet_line({"kind": "plain", "text": "z"}) == "• z"


def test_report_elements_preserve_section_order_and_bold():
    els = _report_elements(_sample_payload()["answer"]["report"])
    # header, paragraph, header, bullets
    assert els[0]["tag"] == "column_set"
    assert "**版本空窗**" in els[1]["content"]
    assert els[2]["tag"] == "column_set"


def test_build_report_card_routes_and_has_no_giant_heading():
    payload = _sample_payload()
    cards = build_result_cards_json(payload)
    assert len(cards) == 1
    card = cards[0]
    assert card["header"]["title"]["content"] == "文档问答"
    # No markdown element should carry a heading prefix that enlarges the font.
    for el in card["body"]["elements"]:
        if el.get("tag") == "markdown":
            assert not el["content"].lstrip().startswith("#")


def test_build_report_card_direct_entry():
    card = build_report_card_json(_sample_payload())
    assert card["schema"] == "2.0"
    assert any(e["tag"] == "column_set" for e in card["body"]["elements"])


def test_bullet_source_doc_fact_keeps_kind_color_with_tag():
    line = _report_bullet_line(
        {"kind": "finding", "source": "doc_fact", "text": "发现：版本空窗"}
    )
    assert "[事实]" in line
    assert "blue" in line  # 事实保留 kind 配色


def test_bullet_source_inference_is_weakened_grey():
    line = _report_bullet_line(
        {"kind": "finding", "source": "inference", "text": "可能由空窗导致"}
    )
    assert "[推断]" in line
    # 推断弱化为灰字，且不得保留 finding 的蓝色
    assert "grey" in line and "blue" not in line


def test_bullet_source_model_prior_is_weakened_grey():
    line = _report_bullet_line(
        {"kind": "forecast", "source": "model_prior", "text": "通常会回升"}
    )
    assert "[经验]" in line
    assert "grey" in line and "purple" not in line


def test_bullet_no_source_falls_back_to_kind_color():
    # 未标注 source 时保持旧行为（与 test_bullet_kind_colors 一致）。
    assert "blue" in _report_bullet_line({"kind": "finding", "text": "x"})
    assert _report_bullet_line({"kind": "plain", "text": "z"}) == "• z"


# --- A2: 排版（小标签加粗、分组空行、概述首句+列表） ----------------------


def test_bullet_tag_is_bold_outside_font():
    """来源标签必须用 ** 加粗且位于 <font> 标签之外。
    飞书 markdown 不支持 ** 嵌套在 <font> 内（会渲染成字面量 ** 和裸 </font>）。
    """
    line = _report_bullet_line(
        {"kind": "finding", "source": "doc_fact", "text": "发现：版本空窗"}
    )
    assert "**[事实]**" in line  # 来源标签加粗
    # 有颜色包裹时，条目前缀不再加粗（** 在 <font> 内无效），剥除后才能正确渲染。
    assert "**发现：**" not in line
    # 不得出现 ** 嵌套在 <font> 标签内——飞书会把 </font> 渲染为字面量。
    assert "</font>**" not in line and "**</font>" not in line

def test_bullet_no_bold_inside_font():
    """LLM 生成的 ** 加粗也应被剥除，避免 <font> 内出现 ** 字面量。"""
    line = _report_bullet_line(
        {"kind": "finding", "source": "inference", "text": "可能由**空窗期**导致"}
    )
    assert "**空窗期**" not in line  # ** 被剥除
    assert "空窗期" in line          # 内容保留


def test_group_blank_line_between_finding_groups():
    section = {
        "title": "关键发现与假设检验",
        "level": 1,
        "bullets": [
            {"kind": "finding", "source": "doc_fact", "text": "发现：A"},
            {"kind": "hypothesis", "source": "inference", "text": "假设：B"},
            {"kind": "finding", "source": "doc_fact", "text": "发现：C"},
        ],
    }
    els = _report_section_elements(section)
    bullets_md = els[-1]["content"]
    # 第二个 finding 之前应有空行（\n\n），第一个 finding 与其假设之间无空行。
    assert "\n\n" in bullets_md
    assert bullets_md.count("\n\n") == 1


def test_group_blank_line_between_forecasts():
    section = {
        "title": "预判与展望",
        "level": 1,
        "bullets": [
            {"kind": "forecast", "text": "预判：X"},
            {"kind": "forecast", "text": "预判：Y"},
        ],
    }
    bullets_md = _report_section_elements(section)[-1]["content"]
    assert "\n\n" in bullets_md  # 两条预判之间有空行


def test_summary_section_leads_then_lists():
    section = {
        "title": "结论概述",
        "level": 1,
        "paragraphs": [
            "核心结论一句话。第二点原因。第三点佐证。第四点展望。",
        ],
    }
    content = _report_section_elements(section)[-1]["content"]
    # 概述应先有一两句话，再以列表（• ）罗列其余句子。
    assert "• " in content
    assert content.count("• ") >= 2


def test_summary_short_text_stays_paragraph():
    section = {"title": "结论概述", "level": 1, "paragraphs": ["只有一句话。"]}
    content = _report_section_elements(section)[-1]["content"]
    assert "• " not in content  # 短文本不强行列表


# --- A3: 引用 snippet 清洗 ---------------------------------------------------


def test_clean_citation_snippet_strips_table_markdown():
    raw = "# 所有appid\n| app_id | 描述 |\n| --- | --- |\n| 101725348225 | 每个user_id全局唯一 |"
    out = _clean_citation_snippet(raw)
    assert "---" not in out
    assert "所有appid" in out and "app_id" in out
    assert "\n" not in out  # 压成一行


def test_lineage_rag_block_uses_cleaned_snippet():
    md = _lineage_rag_block(
        [
            {
                "document_title": "仙魔业务文档",
                "project_id": "xianmo",
                "locator": "版本日期",
                "snippet": "| 版本号 | 起始日期 |\n| --- | --- |\n| 4000 | 2026-06-11 |",
            }
        ]
    )
    assert "| --- |" not in md
    assert "**[1]**" in md and "仙魔业务文档" in md


def _verification_payload() -> dict:
    return {
        "trace_id": "tr_v",
        "cards": [
            {
                "question": "活动期 ARPPU 是否低于空窗期？",
                "verdict": "confirmed",
                "evidence": "P1 ARPPU 312 < P2 358（-12.8%）",
                "caliber": "高付费用户按计费点聚合",
                "sql_digest": "abc123",
            },
            {
                "question": "复购率是否按计费点下滑？",
                "verdict": "unverifiable",
                "need_fields": ["billing_point_id"],
            },
            {
                "question": "付费人数是否减少？",
                "verdict": "listed",
            },
        ],
    }


def test_verification_card_renders_each_verdict_badge():
    card = build_verification_cards_json(_verification_payload())
    assert card["schema"] == "2.0"
    body = "\n".join(
        e.get("content", "")
        for e in card["body"]["elements"]
        if e.get("tag") == "markdown"
    )
    assert "已证实" in body and "green" in body
    assert "暂无法验证" in body and "billing_point_id" in body
    assert "待验证" in body
    assert "trace `tr_v`" in body


def test_verification_card_leads_with_hypothesis_and_query():
    payload = {
        "trace_id": "tr_h",
        "cards": [
            {
                "hypothesis": "5 月下旬付费下滑由龙祖付费点疲劳导致",
                "question": "对比两期龙祖礼包收入贡献变化",
                "verdict": "inconclusive",
                "evidence": "本期 9,766,102 vs 上期 9,123,455（+7.0%）",
                "caliber": "按计费点聚合两期收入",
                "sql_digest": "abc",
            }
        ],
    }
    body = "\n".join(
        e.get("content", "")
        for e in build_verification_cards_json(payload)["body"]["elements"]
        if e.get("tag") == "markdown"
    )
    assert "**验证假设：**5 月下旬付费下滑由龙祖付费点疲劳导致" in body
    assert "验证做法：对比两期龙祖礼包收入贡献变化" in body
    assert "证据数据：本期 9,766,102" in body
    assert "建议核对的数据" in body  # 引导语与上文呼应


def test_verification_card_empty_cards_still_valid():
    card = build_verification_cards_json({"trace_id": "t0", "cards": []})
    assert card["schema"] == "2.0"
    assert card["header"]["title"]["content"] == "结论自验证"


# --- 飞书 markdown 视觉契约（Rendering contract） ----------------------------
# 飞书 markdown 不允许 ** 嵌套在 <font> 标签内，否则 </font> 会作为字面量出现，
# ** 也不加粗。以下测试通过检查典型输出来保证生成代码不违反此约束。


import re as _re

_FONT_TAG_RE = _re.compile(r"<font[^>]*>(.*?)</font>", _re.DOTALL)


def _has_bold_inside_font(text: str) -> bool:
    """检查 <font> 标签内是否存在 ** 加粗标记——如存在则飞书渲染会出错。"""
    for m in _FONT_TAG_RE.finditer(text):
        if "**" in m.group(1):
            return True
    return False


def test_no_bold_inside_font_for_typical_bullets():
    """关键渲染契约：任何 bullet 输出都不能在 <font> 内出现 ** 号。"""
    cases = [
        {"kind": "finding", "source": "doc_fact", "text": "发现：**版本空窗期**是主因"},
        {"kind": "hypothesis", "source": "inference", "text": "假设：**付费率**下滑"},
        {"kind": "forecast", "source": "model_prior", "text": "预判：**下月**回升"},
        {"kind": "finding", "text": "发现：无来源标注"},
        {"kind": "plain", "text": "普通说明"},
    ]
    for c in cases:
        line = _report_bullet_line(c)
        assert not _has_bold_inside_font(line), (
            f"bullet 输出在 <font> 内含 **（飞书渲染会出错）:\n  input={c}\n  output={line!r}"
        )


def test_no_literal_closing_font_tag_in_source_prefix():
    """来源标签前缀（[事实]/[推断]）不得出现 </font> 字面量。"""
    for source, _ in [("doc_fact", "finding"), ("inference", "hypothesis")]:
        line = _report_bullet_line({"kind": "finding", "source": source, "text": "x"})
        # 合法：<font color='grey'>[事实]</font> 或 **[事实]**（两种都行）
        # 非法：出现裸 </font> 在 ** 旁边（如 **[事实]**</font>）
        assert "**</font>" not in line and "</font>**" not in line, (
            f"来源前缀含非法 </font>: {line!r}"
        )
