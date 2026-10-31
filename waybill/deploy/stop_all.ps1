"""停止三个服务。"""

$ErrorActionPreference = 'Continue'

foreach ($name in @('.oa.pid', '.fin.pid', '.agent.pid')) {
    $file = Join-Path $PSScriptRoot $name
    if (-not (Test-Path $file)) { continue }
    $procId = [int](Get-Content $file -Raw).Trim()
    try {
        Stop-Process -Id $procId -Force -ErrorAction Stop
        Write-Host "已停止 PID $procId ($name)"
    } catch {
        Write-Host "PID $procId ($name) 已经不在运行"
    }
    Remove-Item $file -Force
}
