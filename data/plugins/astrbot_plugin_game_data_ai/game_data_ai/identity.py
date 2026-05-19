"""IdentityAssertion v1 signing (docs/mvp/test/附录A-IdentityAssertion-v1.md)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid


def build_identity_headers(
    *,
    shared_secret: str,
    feishu_user_id: str,
    feishu_chat_id: str,
    feishu_message_id: str,
    method: str,
    path: str,
    raw_body: bytes,
    service_token: str,
    caller_service: str = "astrbot-game-data-ai",
) -> dict[str, str]:
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    assertion_id = f"ida_{uuid.uuid4().hex[:16]}"
    body_hash = hashlib.sha256(raw_body).hexdigest()
    canonical = "\n".join(
        [
            "v1",
            timestamp,
            nonce,
            assertion_id,
            feishu_user_id,
            feishu_chat_id,
            feishu_message_id,
            method.upper(),
            path,
            body_hash,
        ]
    )
    signature = hmac.new(
        shared_secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-Service-Token": service_token,
        "X-Caller-Service": caller_service,
        "X-Identity-Assertion": assertion_id,
        "X-Identity-Signature": signature,
        "X-Request-Timestamp": timestamp,
        "X-Request-Nonce": nonce,
    }
