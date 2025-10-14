# Smart Inventory System Simple Test Commands
# These commands can be copied and pasted directly into PowerShell without executing script files

Write-Host "=== Smart Inventory System Simple Test Commands ===" -ForegroundColor Green
Write-Host "Please copy the following commands one by one into PowerShell" -ForegroundColor Yellow

Write-Host "`n=== 1. Health Check ===" -ForegroundColor Cyan
Write-Host "# Check Inventory Service"
Write-Host "Invoke-RestMethod -Uri 'http://localhost:8001/api/healthz' -Method GET"
Write-Host ""
Write-Host "# Check Order Service"
Write-Host "Invoke-RestMethod -Uri 'http://localhost:8002/api/healthz' -Method GET"

Write-Host "`n=== 2. Product Management Test ===" -ForegroundColor Cyan
Write-Host "# Get Product List"
Write-Host "Invoke-RestMethod -Uri 'http://localhost:8001/api/inventory/products' -Method GET"
Write-Host ""
Write-Host "# Create New Product"
Write-Host "`$newProduct = @{"
Write-Host "    sku = 'TEST-MANUAL-$(Get-Date -Format 'yyyyMMdd-HHmmss')'"
Write-Host "    name = 'Manual Test Product'"
Write-Host "    price = 199.99"
Write-Host "    safety_stock = 5"
Write-Host "} | ConvertTo-Json"
Write-Host ""
Write-Host "Invoke-RestMethod -Uri 'http://localhost:8001/api/inventory/products' -Method POST -Body `$newProduct -ContentType 'application/json'"

Write-Host "`n=== 3. Stock Management Test ===" -ForegroundColor Cyan
Write-Host "# Adjust Stock (Increase)"
Write-Host "`$stockAdjustment = @{ adjustment = 50 } | ConvertTo-Json"
Write-Host "Invoke-RestMethod -Uri 'http://localhost:8001/api/inventory/stock/1/adjust' -Method POST -Body `$stockAdjustment -ContentType 'application/json'"
Write-Host ""
Write-Host "# Check Low Stock Warning"
Write-Host "Invoke-RestMethod -Uri 'http://localhost:8001/api/inventory/low-stock' -Method GET"

Write-Host "`n=== 4. Order Management Test ===" -ForegroundColor Cyan
Write-Host "# Create Order"
Write-Host "`$orderData = @{"
Write-Host "    items = @("
Write-Host "        @{"
Write-Host "            product_id = 1"
Write-Host "            qty = 2"
Write-Host "        }"
Write-Host "    )"
Write-Host "    customer_name = 'Manual Test Customer'"
Write-Host "    customer_email = 'test@manual.com'"
Write-Host "    shipping_address = 'Manual Test Address 456'"
Write-Host "    notes = 'Manual Test Order'"
Write-Host "} | ConvertTo-Json -Depth 3"
Write-Host ""
Write-Host "Invoke-RestMethod -Uri 'http://localhost:8002/api/orders/' -Method POST -Body `$orderData -ContentType 'application/json'"

Write-Host "`n=== 5. Order Status Update Test ===" -ForegroundColor Cyan
Write-Host "# Update Order Status to PAID"
Write-Host "`$statusUpdate = @{ status = 'PAID'; notes = 'Manual Test Payment Complete' } | ConvertTo-Json"
Write-Host "Invoke-RestMethod -Uri 'http://localhost:8002/api/orders/1/status' -Method PATCH -Body `$statusUpdate -ContentType 'application/json'"
Write-Host ""
Write-Host "# Update Order Status to SHIPPED"
Write-Host "`$statusUpdate = @{ status = 'SHIPPED'; notes = 'Manual Test Shipping Complete' } | ConvertTo-Json"
Write-Host "Invoke-RestMethod -Uri 'http://localhost:8002/api/orders/1/status' -Method PATCH -Body `$statusUpdate -ContentType 'application/json'"

Write-Host "`n=== 6. Order Details and Workflow Test ===" -ForegroundColor Cyan
Write-Host "# Get Order Details"
Write-Host "Invoke-RestMethod -Uri 'http://localhost:8002/api/orders/1' -Method GET"
Write-Host ""
Write-Host "# Get Workflow Information"
Write-Host "Invoke-RestMethod -Uri 'http://localhost:8002/api/orders/1/workflow' -Method GET"

Write-Host "`n=== 7. System Statistics ===" -ForegroundColor Cyan
Write-Host "# Get Final Statistics"
Write-Host "`$products = Invoke-RestMethod -Uri 'http://localhost:8001/api/inventory/products' -Method GET"
Write-Host "`$orders = Invoke-RestMethod -Uri 'http://localhost:8002/api/orders/' -Method GET"
Write-Host "`$lowStock = Invoke-RestMethod -Uri 'http://localhost:8001/api/inventory/low-stock' -Method GET"
Write-Host ""
Write-Host "Write-Host 'Total Products: ' `$products.Count"
Write-Host "Write-Host 'Total Orders: ' `$orders.Count"
Write-Host "Write-Host 'Low Stock Products: ' `$lowStock.Count"

Write-Host "`n=== Usage Instructions ===" -ForegroundColor Yellow
Write-Host "1. Ensure system is started: docker-compose up -d"
Write-Host "2. Copy the above commands one by one into PowerShell"
Write-Host "3. Observe the output of each command"
Write-Host "4. If errors occur, check if services are running properly"
Write-Host "5. Use 'docker-compose logs' to view service logs"

Write-Host "`n=== Quick Health Check ===" -ForegroundColor Green
Write-Host "Execute the following commands for quick health check:"
Write-Host "try { Invoke-RestMethod -Uri 'http://localhost:8001/api/healthz' -Method GET; Write-Host 'Inventory Service: Healthy' -ForegroundColor Green } catch { Write-Host 'Inventory Service: Failed' -ForegroundColor Red }"
Write-Host "try { Invoke-RestMethod -Uri 'http://localhost:8002/api/healthz' -Method GET; Write-Host 'Order Service: Healthy' -ForegroundColor Green } catch { Write-Host 'Order Service: Failed' -ForegroundColor Red }"