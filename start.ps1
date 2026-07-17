# =====================================================================
# One-command startup for the whole platform.
# Usage (from the project root):   .\start.ps1
#   - Starts the backend stack (Docker: postgres, redis, minio, chroma,
#     backend API, celery worker)
#   - Waits for the API to be healthy
#   - Starts the frontend dev server (this window shows its logs)
# Stop the frontend with Ctrl+C, then run .\stop.ps1 to stop Docker.
# =====================================================================

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$compose = "docker compose --env-file `"$root\.env`" -f `"$root\docker\docker-compose.yml`""

Write-Host "`n[1/3] Starting backend stack (Docker)..." -ForegroundColor Cyan
Invoke-Expression "$compose up -d"

Write-Host "`n[2/3] Waiting for the API to be healthy..." -ForegroundColor Cyan
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8000/api/v1/health" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}
if ($ready) {
    Write-Host "      Backend is up: http://localhost:8000/api/v1/docs" -ForegroundColor Green
} else {
    Write-Host "      API not healthy yet - check: docker compose ... ps" -ForegroundColor Yellow
}

Write-Host "`n[3/3] Starting frontend (http://localhost:3000)..." -ForegroundColor Cyan
Write-Host "      Open http://localhost:3000 in your browser." -ForegroundColor Green
Write-Host "      Press Ctrl+C here to stop the frontend, then run .\stop.ps1`n" -ForegroundColor Yellow

Set-Location "$root\frontend"
if (-not (Test-Path "node_modules")) {
    Write-Host "      Installing frontend dependencies (first run only)..." -ForegroundColor Cyan
    npm install
}
npm run dev
