# Mirror-push all branches/tags to GitLab when worktree "git push" fails on Windows.
#
# Usage:
#   .\scripts\push-mirror-gitlab.ps1
#   .\scripts\push-mirror-gitlab.ps1 -GitLabUrl "git@y1.pookgitlab.com:aibot/astrbot.git"

param(
    [string]$GitLabUrl = "https://y1.pookgitlab.com/aibot/astrbot.git"
)

$ErrorActionPreference = "Stop"
Remove-Item Env:GIT_DIR, Env:GIT_WORK_TREE, Env:GIT_TRACE, Env:GIT_EDITOR -ErrorAction SilentlyContinue

$GitCmd = "C:\Program Files\Git\cmd\git.exe"
if (-not (Test-Path $GitCmd)) {
    throw "Git for Windows not found at $GitCmd"
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BareDir = Join-Path $env:TEMP "GameDataOps_AstrBot-mirror.git"

Write-Host "Source repo: $RepoRoot" -ForegroundColor Cyan
& $GitCmd -C $RepoRoot rev-parse --is-inside-work-tree | Out-Null

if (Test-Path $BareDir) {
    Remove-Item -Recurse -Force $BareDir
}

Write-Host "Creating bare mirror at $BareDir ..." -ForegroundColor Cyan
& $GitCmd -C $RepoRoot clone --bare . $BareDir

Write-Host "Pushing --mirror to $GitLabUrl ..." -ForegroundColor Cyan
& $GitCmd -C $BareDir push --mirror $GitLabUrl

Write-Host "Done. Branches on GitLab should include dev and master." -ForegroundColor Green
Write-Host "Optional: add GitLab as remote in working copy:" -ForegroundColor Green
Write-Host "  git remote add gitlab $GitLabUrl"
Write-Host "  git checkout dev"
Write-Host "  git push -u gitlab dev   # only if worktree git push works"
