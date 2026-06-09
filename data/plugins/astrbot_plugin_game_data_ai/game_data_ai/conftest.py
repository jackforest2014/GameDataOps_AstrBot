"""Test-only shim: cards.py imports `from astrbot.api import logger`, but the
AstrBot runtime package is not installed in the unit-test environment. Provide a
minimal stub so cards.py (pure rendering helpers) can be imported standalone."""

import logging
import sys
import types


def _ensure_astrbot_stub() -> None:
    if "astrbot" in sys.modules:
        return
    try:
        # Prefer the real package when it is installed (full AstrBot test suite);
        # only fall back to a stub when it cannot be imported (standalone card tests).
        import importlib.util

        if importlib.util.find_spec("astrbot") is not None:
            return
    except Exception:  # noqa: BLE001 - find_spec may raise on broken namespaces
        pass
    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    api.logger = logging.getLogger("astrbot.test_stub")
    astrbot.api = api
    sys.modules["astrbot"] = astrbot
    sys.modules["astrbot.api"] = api


_ensure_astrbot_stub()
