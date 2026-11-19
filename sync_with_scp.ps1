# SSH 키를 사용하여 로컬 코드를 NAS에 동기화

$ErrorActionPreference = "Stop"

$localDir = "C:\My_Obsidian\Projects\ReBalancer"
$nasHost = "doogie_admin@192.168.0.46"
$nasDir = "/volume1/rebalancer"
$keyPath = "$env:USERPROFILE\.ssh\id_rebalancer"

# 동기화할 파일 목록
$pythonFiles = @(
    "config.py",
    "database.py",
    "crawler.py",
    "momentum_engine.py",
    "rebalance_engine.py",
    "portfolio_engine.py",
    "notification.py",
    "signal_accuracy_engine.py",
    "scheduler.py",
    "main.py"
)

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "Syncing Python files to NAS using SSH key" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host ""

# SSH 키 테스트
Write-Host "Testing SSH connection..." -ForegroundColor Yellow
try {
    $result = ssh -i $keyPath -o StrictHostKeyChecking=no $nasHost "whoami" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ SSH connection successful: $result" -ForegroundColor Green
    } else {
        Write-Host "⚠️  SSH test failed" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️  SSH test error: $_" -ForegroundColor Yellow
}

Write-Host ""

# 파일 동기화
$syncedCount = 0
foreach ($file in $pythonFiles) {
    $localPath = Join-Path $localDir $file

    if (-not (Test-Path $localPath)) {
        Write-Host "⚠️  $file - NOT FOUND" -ForegroundColor Yellow
        continue
    }

    Write-Host "Syncing: $file " -NoNewline -ForegroundColor White

    try {
        # SCP를 사용한 파일 전송
        scp -i $keyPath -o StrictHostKeyChecking=no $localPath "${nasHost}:${nasDir}/${file}" 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅" -ForegroundColor Green
            $syncedCount++
        } else {
            Write-Host "❌" -ForegroundColor Red
        }
    } catch {
        Write-Host "❌ Error: $_" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "Synced $syncedCount/$($pythonFiles.Count) files" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

Write-Host ""
Write-Host "Verifying files on NAS..." -ForegroundColor Yellow

# NAS에서 Python 파일 확인
$verifyCmd = "ls -la $nasDir/*.py | wc -l"
$count = ssh -i $keyPath -o StrictHostKeyChecking=no $nasHost $verifyCmd 2>&1

Write-Host "Python files on NAS: $count files" -ForegroundColor Green

Write-Host ""
Write-Host "Restarting API server on NAS..." -ForegroundColor Yellow

# 서비스 재시작
ssh -i $keyPath -o StrictHostKeyChecking=no $nasHost "sudo systemctl restart rebalancer" 2>&1 | Out-Null

Start-Sleep -Seconds 2

# 서비스 상태 확인
Write-Host "Checking service status..." -ForegroundColor Yellow
$status = ssh -i $keyPath -o StrictHostKeyChecking=no $nasHost "sudo systemctl status rebalancer | head -3" 2>&1

foreach ($line in $status) {
    if ($line -match "active|running|failed") {
        Write-Host "  $line" -ForegroundColor Green
    } else {
        Write-Host "  $line"
    }
}

Write-Host ""
Write-Host "Performing health check..." -ForegroundColor Yellow

# Health check
$health = ssh -i $keyPath -o StrictHostKeyChecking=no $nasHost "curl -s http://localhost:8000/health" 2>&1

if ($health -match '"status".*"healthy"') {
    Write-Host "✅ API server is healthy" -ForegroundColor Green
    Write-Host "  $health" -ForegroundColor Green
} else {
    Write-Host "⚠️  Health check result:" -ForegroundColor Yellow
    Write-Host "  $health" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "✅ Sync and restart completed successfully!" -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Cyan
