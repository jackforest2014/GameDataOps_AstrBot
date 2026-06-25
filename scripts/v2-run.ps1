# Start AstrBot v2 instance (WebUI :6285 → Go :8180).
# Legacy instance: GameDataOps_AstrBot on dev branch, WebUI :6185 → Go :8080.
param(
    [ValidateSet("run", "status")]
    [string]$Action = "run"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

$env:GAME_DATA_AI_BASE_URL = "http://127.0.0.1:8180"
$env:GAME_DATA_AI_SERVICE_TOKEN = if ($env:GAME_DATA_AI_SERVICE_TOKEN) { $env:GAME_DATA_AI_SERVICE_TOKEN } else { "dev-service-token" }
$env:GAME_DATA_AI_SHARED_SECRET = if ($env:GAME_DATA_AI_SHARED_SECRET) { $env:GAME_DATA_AI_SHARED_SECRET } else { "dev-shared-secret" }

switch ($Action) {
    "status" {
        Write-Host "AstrBot v2 worktree: $Root"
        Write-Host "  WebUI target port: 6285 (data/cmd_config.json dashboard.port)"
        Write-Host "  Go API: $env:GAME_DATA_AI_BASE_URL"
        try {
            Invoke-RestMethod "http://127.0.0.1:6285" -TimeoutSec 3 | Out-Null
            Write-Host "  WebUI: listening"
        } catch {
            Write-Host "  WebUI: not listening ($($_.Exception.Message))"
        }
        try {
            Invoke-RestMethod "http://127.0.0.1:8180/healthz" -TimeoutSec 3 | Out-Null
            Write-Host "  Go v2 healthz: ok"
        } catch {
            Write-Host "  Go v2 healthz: not ready ($($_.Exception.Message))"
        }
    }
    "run" {
        Push-Location $Root
        try {
            Write-Host "AstrBot v2: GAME_DATA_AI_BASE_URL=$env:GAME_DATA_AI_BASE_URL WebUI=:6285"
            Write-Host "Go v2 should be running (game_data_ai worktree HTTP_ADDR=:8180)"
            python main.py
        } finally {
            Pop-Location
        }
    }
}
