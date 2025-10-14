# --- smart-inventory quick script ---
Write-Host "==> docker compose up -d --build" -ForegroundColor Cyan
docker compose up -d --build

Write-Host "`n==> docker compose ps" -ForegroundColor Cyan
docker compose ps

Write-Host "`n==> tail logs (mysql, inventory, order, nginx) -- last 60 lines" -ForegroundColor Cyan
docker compose logs --tail=60 mysql inventory-service order-service nginx

Write-Host "`n==> waiting for services to start (10 seconds)..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

Write-Host "`n==> health checks via Nginx" -ForegroundColor Cyan
$urls = @(
  "http://localhost:8080/healthz",
  "http://localhost:8080/api/inventory/healthz",
  "http://localhost:8080/api/orders/healthz"
)
foreach ($u in $urls) {
  try {
    $r = Invoke-WebRequest -Uri $u -UseBasicParsing
    Write-Host ("{0} => {1}" -f $u, $r.StatusCode) -ForegroundColor Green
  } catch {
    Write-Host ("{0} => FAILED: {1}" -f $u, $_.Exception.Message) -ForegroundColor Red
  }
}

Write-Host "`n==> direct service health checks" -ForegroundColor Cyan
$directUrls = @(
  "http://localhost:8001/api/healthz",
  "http://localhost:8002/api/healthz"
)
foreach ($u in $directUrls) {
  try {
    $r = Invoke-WebRequest -Uri $u -UseBasicParsing
    Write-Host ("{0} => {1}" -f $u, $r.StatusCode) -ForegroundColor Green
  } catch {
    Write-Host ("{0} => FAILED: {1}" -f $u, $_.Exception.Message) -ForegroundColor Red
  }
}
