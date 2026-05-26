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

## v1.1 文档问数（`feat/feishu-doc-v1.1`）

| 变量 | 默认 | 说明 |
|---|---|---|
| `GAME_DATA_AI_SSE_ENABLED` | `true` | 是否维持 `GET /api/v1/events/stream` |
| `GAME_DATA_AI_INGEST_WAIT_SEC` | `180` | 等待入库确认 + SSE 最终答案超时（秒） |

- 问数入口：`POST /api/v1/chat/messages`（消息中含飞书文档链接会自动带 `attachments`）
- 入库确认：SSE `document.ingest.confirm_required` → 卡片按钮 → `ingest-decision`
- 最终答案：SSE `document.chat.answered`（勿轮询 HTTP）

建议在独立 worktree 开发：`GameDataOps_AstrBot-feishu-doc`，与 Go 仓 `game_data_ai-feishu-doc` 联调。
