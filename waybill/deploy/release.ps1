# 本地发版（Windows）：构建前端 → 打包 → 上传 → 重启服务
#
#   powershell -ExecutionPolicy Bypass -File deploy\release.ps1 -Server root@1.2.3.4
#
# 不上传：.env、*.db、logs、node_modules、.git
# 所以重复发版不会覆盖线上配置和数据。

param(
    [Parameter(Mandatory = $true)][string]$Server,
    [string]$AppDir = '/opt/waybill',
    # pnpm 不在 PATH 上时显式指定（例如 DSH 自带的运行时）
    [string]$Pnpm
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Fail([string]$message) {
    Write-Host $message -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------- 构建前端

Write-Host '== 1/4 构建控制台前端 ==' -ForegroundColor Cyan
$webDir = Join-Path $root 'agent\web'
if (-not (Test-Path (Join-Path $webDir 'node_modules'))) {
    Fail 'agent\web\node_modules 不存在，先在该目录执行 pnpm install'
}

if (-not $Pnpm) {
    $cmd = Get-Command pnpm -ErrorAction SilentlyContinue
    if ($cmd) { $Pnpm = $cmd.Source }
}

Push-Location $webDir
try {
    if ($Pnpm) {
        & $Pnpm build
    } else {
        # 没有独立 pnpm 时退回 corepack
        & corepack pnpm build
    }
    if ($LASTEXITCODE -ne 0) { Fail '前端构建失败' }
} finally {
    Pop-Location
}

# ---------------------------------------------------------------- 打包

Write-Host '== 2/4 打包 ==' -ForegroundColor Cyan
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$tarball = Join-Path $env:TEMP "waybill-$stamp.tgz"

& tar -czf $tarball -C $root `
    --exclude='.git' `
    --exclude='node_modules' `
    --exclude='__pycache__' `
    --exclude='*.pyc' `
    --exclude='*.db' `
    --exclude='*.db-wal' `
    --exclude='*.db-shm' `
    --exclude='agent/.env' `
    --exclude='systems/fin/.env' `
    --exclude='agent/logs' `
    --exclude='deploy/.oa.pid' `
    --exclude='deploy/.fin.pid' `
    --exclude='deploy/.agent.pid' `
    .
if ($LASTEXITCODE -ne 0) { Fail '打包失败' }
Write-Host ("包大小: {0:N1} MB" -f ((Get-Item $tarball).Length / 1MB))

# ---------------------------------------------------------------- 上传

Write-Host '== 3/4 上传 ==' -ForegroundColor Cyan
& scp $tarball "${Server}:/tmp/waybill-release.tgz"
if ($LASTEXITCODE -ne 0) { Fail '上传失败（检查 SSH 是否已配置免密）' }

# ---------------------------------------------------------------- 远端

Write-Host '== 4/4 解压并重启 ==' -ForegroundColor Cyan
$remote = @"
set -e
mkdir -p $AppDir
tar -xzf /tmp/waybill-release.tgz -C $AppDir
chown -R waybill:waybill $AppDir
# 依赖可能随代码变化：每次装一遍，已满足的会很快跳过
$AppDir/.venv/bin/pip install -q -r $AppDir/requirements.txt
systemctl restart waybill-oa waybill-fin waybill-agent
sleep 2
systemctl --no-pager --lines=0 is-active waybill-oa waybill-fin waybill-agent
curl -fsS http://127.0.0.1:8300/health >/dev/null && echo 'agent 健康检查通过'
"@

& ssh $Server $remote
if ($LASTEXITCODE -ne 0) { Fail '远端部署失败，登录服务器看 journalctl -u waybill-agent' }

Remove-Item $tarball -Force
Write-Host "完成：$stamp" -ForegroundColor Green
