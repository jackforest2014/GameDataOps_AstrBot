# AstrBot · v2 并行实例（对接 game_data_ai v2 栈）

与 Go 仓库 **同名分支**：`feat/conversational-analysis-refinement`。

完整端口表与 compose 说明见 Go 仓库：

`docs/deploy/03-v2-local-parallel-stack.md`

---

## 目的

本地 **legacy**（`:8080` + AstrBot WebUI `6185`）继续服务日常问数；**v2** 栈（`:8180` + WebUI `6285`）开发 analysisv2 / Neo4j 知识库，两实例互不抢占端口。

---

## 环境变量（插件 `astrbot_plugin_game_data_ai`）

| 变量 | Legacy 实例 | v2 实例 |
|------|-------------|---------|
| `GAME_DATA_AI_BASE_URL` | `http://127.0.0.1:8080` | **`http://127.0.0.1:8180`** |
| `GAME_DATA_AI_SERVICE_TOKEN` | 与 Go `.env` 一致 | 与 Go **`.env.v2`** 一致 |
| `GAME_DATA_AI_SHARED_SECRET` | 同上 | 同上 |

可在启动 AstrBot 前于 PowerShell 设置：

```powershell
$env:GAME_DATA_AI_BASE_URL = "http://127.0.0.1:8180"
python main.py
```

---

## WebUI 端口

Legacy 默认 **`6185`**（`data/cmd_config.json` → `webui.port`）。

v2 第二实例建议：

1. 复制 `data` → `data-v2`（或独立工作目录）；
2. 将 **`webui.port`** 改为 **`6285`**；
3. 在该目录启动 AstrBot，并设置上述 `GAME_DATA_AI_BASE_URL`。

---

## 飞书 OAuth

v2 Go 回调基址为 **`http://127.0.0.1:8180`**。飞书应用需登记：

`http://127.0.0.1:8180/api/v1/auth/feishu/callback`

与 legacy `8080` 回调可并存；同一时期若只跑一个实例，只启用对应回调即可。

---

## 验收

1. Go v2：`curl http://127.0.0.1:8180/healthz` → OK  
2. AstrBot v2 问数后，trace 中可见 v2 pipeline / analysisv2 相关 span  
3. Legacy `:8080` 与 v2 `:8180` 同时 `netstat` 监听
