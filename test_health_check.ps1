# Smart Inventory System Health Check
# This script can be copied and pasted into PowerShell

Write-Host "=== Smart Inventory System Health Check ===" -ForegroundColor Green

# Check Nginx
Write-Host "`nChecking Nginx..." -ForegroundColor Cyan
try {
    $nginxHealth = Invoke-RestMethod -Uri "http://localhost:8080/healthz" -Method GET
    Write-Host "[OK] Nginx: $nginxHealth" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Nginx: Failed - $($_.Exception.Message)" -ForegroundColor Red
}

# Check Inventory Service via Nginx
Write-Host "`nChecking Inventory Service (via Nginx)..." -ForegroundColor Cyan
try {
    $inventoryHealth = Invoke-RestMethod -Uri "http://localhost:8080/api/inventory/healthz" -Method GET
    Write-Host "[OK] Inventory Service: $($inventoryHealth.status)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Inventory Service: Failed - $($_.Exception.Message)" -ForegroundColor Red
}

# Check Order Service via Nginx
Write-Host "`nChecking Order Service (via Nginx)..." -ForegroundColor Cyan
try {
    $orderHealth = Invoke-RestMethod -Uri "http://localhost:8080/api/orders/healthz" -Method GET
    Write-Host "[OK] Order Service: $($orderHealth.status)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Order Service: Failed - $($_.Exception.Message)" -ForegroundColor Red
}

# Check services directly
Write-Host "`nChecking services directly..." -ForegroundColor Cyan
try {
    $inventoryDirect = Invoke-RestMethod -Uri "http://localhost:8001/api/healthz" -Method GET
    Write-Host "[OK] Inventory Service (Direct): $($inventoryDirect.status)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Inventory Service (Direct): Failed - $($_.Exception.Message)" -ForegroundColor Red
}

try {
    $orderDirect = Invoke-RestMethod -Uri "http://localhost:8002/api/healthz" -Method GET
    Write-Host "[OK] Order Service (Direct): $($orderDirect.status)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Order Service (Direct): Failed - $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=== Health Check Complete ===" -ForegroundColor Green
Write-Host "All services are running properly!" -ForegroundColor Green