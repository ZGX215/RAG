# 一键启动：Redis + FastAPI + Celery Worker
# 用法：powershell -ExecutionPolicy Bypass -File scripts\start_all.ps1

Write-Host "=== 启动 Redis ===" -ForegroundColor Green
$redisDir = "E:\trae\redis\Redis-8.10.1-Windows-x64-msys2-with-Service"
$redisExe = Join-Path $redisDir "redis-server.exe"
$redisConf = Join-Path $redisDir "redis.conf"

Start-Process -FilePath $redisExe -ArgumentList $redisConf -WindowStyle Hidden
Write-Host "Redis 已启动（后台运行）" -ForegroundColor Green
Start-Sleep -Seconds 2

# 验证 Redis 连接
python -c "import redis; r = redis.Redis(host='localhost', port=6379, socket_connect_timeout=3); print('Redis:', 'OK' if r.ping() else 'FAIL')"

Write-Host ""
Write-Host "=== 启动 FastAPI ===" -ForegroundColor Green
Set-Location "E:\trae\cede\mcu-rag-qa-v2"

# 启动 FastAPI（后台）
$fastapiProc = Start-Process -FilePath "python" -ArgumentList "main.py" -WindowStyle Hidden -PassThru
Write-Host "FastAPI PID: $($fastapiProc.Id)" -ForegroundColor Green
Start-Sleep -Seconds 15

# 验证 FastAPI
$health = Invoke-RestMethod -Uri http://localhost:8000/health -ErrorAction SilentlyContinue
if ($health) {
    Write-Host "FastAPI: OK (status=$($health.status))" -ForegroundColor Green
} else {
    Write-Host "FastAPI: 启动中..." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== 启动 Celery Worker ===" -ForegroundColor Green
$celeryProc = Start-Process -FilePath "celery" -ArgumentList "-A app.cross.celery_app:celery_app worker --loglevel=info" -WindowStyle Hidden -PassThru
Write-Host "Celery PID: $($celeryProc.Id)" -ForegroundColor Green

Write-Host ""
Write-Host "=== 所有服务已启动 ===" -ForegroundColor Green
Write-Host "  FastAPI:  http://localhost:8000"
Write-Host "  Health:   http://localhost:8000/health"
Write-Host "  Metrics:  http://localhost:8000/metrics"
Write-Host ""
Write-Host "停止所有服务:  Stop-Process -Name python -Force" -ForegroundColor Yellow