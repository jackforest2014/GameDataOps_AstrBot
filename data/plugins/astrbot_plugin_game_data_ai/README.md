# astrbot_plugin_game_data_ai

飞书单聊问数入口（MVP 第三批 A01–A23）。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `GAME_DATA_AI_BASE_URL` | `http://127.0.0.1:8080` | 平台 API |
| `GAME_DATA_AI_SERVICE_TOKEN` | `dev-service-token` | `X-Service-Token` |
| `GAME_DATA_AI_SHARED_SECRET` | `dev-shared-secret` | IdentityAssertion HMAC |

## 安装

将本目录置于 `AstrBot/data/plugins/astrbot_plugin_game_data_ai`，在 WebUI 插件管理中启用并重载。

若启动日志出现 `No module named 'game_data_ai'`，请确认已拉取含 `main.py` 顶部 `sys.path` 修复的版本，并在 WebUI 中 **重载插件**。

若修改 `game_data_ai/*.py` 后重载仍报旧错误（如 `motion`），请 **再重载一次** 或 **重启 AstrBot**（子模块 Python 缓存问题，已在 `main.py` 重载时清理）。

## 触发方式

- 飞书单聊中包含数据类关键词（流水、活动、朱雀等）
- 命令：`/gd_query <问题>`

## 依赖

需先启动 `game_data_ai` 后端：`go run ./cmd/server`（默认 `:8080`）。
