# =====================================================================
# Stop the backend stack.  Usage:   .\stop.ps1
# (The frontend is stopped with Ctrl+C in its own window.)
# Data volumes are KEPT, so your meetings/users survive a restart.
# =====================================================================

$root = $PSScriptRoot
Write-Host "`nStopping backend stack (Docker)..." -ForegroundColor Cyan
docker compose --env-file "$root\.env" -f "$root\docker\docker-compose.yml" down
Write-Host "Done. Data is preserved. Run .\start.ps1 to bring it back up.`n" -ForegroundColor Green
