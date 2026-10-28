"""启动两个仿真系统（Windows）。

    powershell -ExecutionPolicy Bypass -File deploy\start_all.ps1

两个服务都在独立进程里跑，脚本退出后仍然存活。停止用 stop_all.ps1。
"""

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot

# 依赖装在解释器里（requirements.txt），不再需要 PYTHONPATH。
# 优先用 py 启动器：Windows 商店的 python.exe 是占位程序，直接调会弹商店。
$launcher = $null
$launcherArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    $launcher = 'py'
    $launcherArgs = @('-3')
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $launcher = 'python'
} else {
    Write-Host '找不到 Python，先装一个。' -ForegroundColor Red
    exit 1
}

function Start-System([string]$name, [string]$script, [string]$port, [string]$pidFile) {
    $launchArgs = $launcherArgs + @($script, '--port', $port)
    $proc = Start-Process -FilePath $launcher -ArgumentList $launchArgs -PassThru -WindowStyle Hidden
    $proc.Id | Set-Content $pidFile
    Write-Host "$name  http://127.0.0.1:$port   (PID $($proc.Id))" -ForegroundColor Green
    return $proc
}

$oa = Start-System 'OA  ' (Join-Path $root 'systems\oa\run.py') '8100' (Join-Path $PSScriptRoot '.oa.pid')
$fin = Start-System '财务' (Join-Path $root 'systems\fin\run.py') '8200' (Join-Path $PSScriptRoot '.fin.pid')

Start-Sleep -Seconds 3

Write-Host ''
Write-Host '健康检查：'
try { Invoke-RestMethod 'http://127.0.0.1:8100/health' | ConvertTo-Json -Compress } catch { "OA 未就绪：$($_.Exception.Message)" }
try { Invoke-RestMethod 'http://127.0.0.1:8200/health' | ConvertTo-Json -Compress } catch { "财务未就绪：$($_.Exception.Message)" }
