"""Tests for Feishu URL extraction."""

from game_data_ai.attachments import build_attachments, extract_feishu_doc_urls


def test_extract_wiki_url():
    text = "请看 https://example.feishu.cn/wiki/wikcnXXXX 里的配置"
    urls = extract_feishu_doc_urls(text)
    assert len(urls) == 1
    assert "feishu.cn/wiki" in urls[0]


def test_build_attachments_dedup():
    text = (
        "https://a.feishu.cn/wiki/x "
        "https://a.feishu.cn/wiki/x "
        "https://b.larkoffice.com/docx/abc"
    )
    atts = build_attachments(text)
    assert len(atts) == 2
    assert atts[0]["type"] == "feishu_doc_link"
