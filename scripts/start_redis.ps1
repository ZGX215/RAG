<#
.SYNOPSIS
    启动 WSL 中的 Redis 服务，确保 Windows 端能正常连接。
    建议每次重启电脑后运行此脚本。

.DESCRIPTION
    1. 检查 WSL 中 Redis 是否已启动
    2. 未启动则自动启动
    3. 获取 WSL IP 并更新 .env 文件
    4. 验证 Windows 端能否连接 Redis
#>

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot ".env"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  WSL Redis 启动助手" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. 检查 WSL 是否可用
Write-Host "[1/4] 检查 WSL 状态..." -ForegroundColor Yellow
try {
    $wslVersion = wsl --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "WSL 不可用" }
    Write-Host "  WSL 正常: $($wslVersion.Split("`n")[0])" -ForegroundColor Green
} catch {
    Write-Host "  WSL 不可用，请先安装 WSL" -ForegroundColor Red
    exit 1
}

# 2. 检查 Redis 是否已启动
Write-Host "[2/4] 检查 Redis 状态..." -ForegroundColor Yellow
$redisPing = wsl redis-cli ping 2>&1
if ($redisPing -eq "PONG") {
    Write-Host "  Redis 已在运行 ✅" -ForegroundColor Green
} else {
    Write-Host "  Redis 未启动，正在启动..." -ForegroundColor Yellow
    $startResult = wsl -u root redis-server --daemonize yes --bind 0.0.0.0 --protected-mode no 2>&1
    Start-Sleep 2
    
    # 再次检查
    $retryPing = wsl redis-cli ping 2>&1
    if ($retryPing -eq "PONG") {
        Write-Host "  Redis 已启动 ✅" -ForegroundColor Green
    } else {
        Write-Host "  Redis 启动失败，请手动执行: wsl -u root redis-server --daemonize yes" -ForegroundColor Red
        exit 1
    }
}

# 3. 获取 WSL IP 并更新 .env
Write-Host "[3/4] 更新连接地址..." -ForegroundColor Yellow
$wslIp = (wsl hostname -I 2>&1).Trim()
if (-not $wslIp) {
    Write-Host "  获取 WSL IP 失败" -ForegroundColor Red
    exit 1
}
Write-Host "  WSL IP: $wslIp" -ForegroundColor Green

# 读取 .env，更新 Redis 地址
if (Test-Path $envFile) {
    $envContent = Get-Content $envFile -Raw
    
    # 替换或追加 Celery 配置
    $lines = $envContent -split "`n"
    $newLines = @()
    $found = @{ broker = $false; backend = $false; cache = $false }
    foreach ($line in $lines) {
        if ($line -match "^CELERY_BROKER_URL=") {
            $newLines += "CELERY_BROKER_URL=redis://${wslIp}:6379/0"
            $found.broker = $true
        } elseif ($line -match "^CELERY_RESULT_BACKEND=") {
            $newLines += "CELERY_RESULT_BACKEND=redis://${wslIp}:6379/1"
            $found.backend = $true
        } elseif ($line -match "^CACHE_REDIS_URL=") {
            $newLines += "CACHE_REDIS_URL=redis://${wslIp}:6379/2"
            $found.cache = $true
        } else {
            $newLines += $line
        }
    }
    # 如果没有找到，追加
    if (-not $found.broker) { $newLines += "CELERY_BROKER_URL=redis://${wslIp}:6379/0" }
    if (-not $found.backend) { $newLines += "CELERY_RESULT_BACKEND=redis://${wslIp}:6379/1" }
    if (-not $found.cache) { $newLines += "CACHE_REDIS_URL=redis://${wslIp}:6379/2" }
    
    Set-Content -Path $envFile -Value ($newLines -join "`n") -Encoding UTF8
    Write-Host "  .env 文件已更新 ✅" -ForegroundColor Green
} else {
    Write-Host "  .env 文件不存在，跳过更新" -ForegroundColor Yellow
}

# 4. 验证连接
Write-Host "[4/4] 验证连接..." -ForegroundColor Yellow
$testPing = wsl redis-cli ping 2>&1
if ($testPing -eq "PONG") {
    Write-Host "  WSL 端连接正常 ✅" -ForegroundColor Green
} else {
    Write-Host "  WSL 端连接异常 ❌" -ForegroundColor Red
}

# 尝试从 Python 验证
try {
    $pythonCheck = python -c "import redis; r = redis.Redis('${wslIp}', 6379); r.ping(); print('OK')" 2>&1
    if ($pythonCheck -eq "OK") {
        Write-Host "  Windows → Redis 连接正常 ✅" -ForegroundColor Green
    }
} catch {
    Write-Host "  Windows → Redis 连接异常，请检查防火墙" -ForegroundColor Yellow
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Redis 就绪，可以启动项目服务了" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan