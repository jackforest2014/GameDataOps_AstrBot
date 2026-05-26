"""Extract Feishu document links from user messages for chat/messages attachments."""

from __future__ import annotations

import re
from typing import Any

# feishu.cn / larksuite.com / larkoffice.com wiki, docx, sheets, bitable links
_FEISHU_DOC_URL = re.compile(
    r"https?://[^\s<>\"']+?(?:feishu\.cn|larksuite\.com|larkoffice\.com)[^\s<>\"']*",
    re.IGNORECASE,
)


def extract_feishu_doc_urls(text: str) -> list[str]:
    """Return unique document URLs in message order."""
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in _FEISHU_DOC_URL.finditer(text):
        url = m.group(0).rstrip(".,;:)】）")
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def build_attachments(text: str) -> list[dict[str, str]]:
    urls = extract_feishu_doc_urls(text)
    return [{"type": "feishu_doc_link", "url": u} for u in urls]
