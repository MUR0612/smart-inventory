# Smart Inventory System Complete Test Script
# Make sure all services are running: docker-compose up -d

Write-Host "=== Smart Inventory System Complete Test ===" -ForegroundColor Green
Write-Host "Test Time: $(Get-Date)" -ForegroundColor Cyan

# 1. Health Check
Write-Host "`n=== 1. Health Check ===" -ForegroundColor Yellow
try {
    $inventoryHealth = Invoke-RestMethod -Uri "http://localhost:8001/api/healthz" -Method GET
    Write-Host "[OK] Inventory Service: $($inventoryHealth.status)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Inventory Service Connection Failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

try {
    $orderHealth = Invoke-RestMethod -Uri "http://localhost:8002/api/healthz" -Method GET
    Write-Host "[OK] Order Service: $($orderHealth.status)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Order Service Connection Failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 2. Product Management Test
Write-Host "`n=== 2. Product Management Test ===" -ForegroundColor Yellow

# Get existing product list
Write-Host "Getting product list..." -ForegroundColor Cyan
$products = Invoke-RestMethod -Uri "http://localhost:8001/api/inventory/products" -Method GET
Write-Host "Existing product count: $($products.Count)" -ForegroundColor Cyan

# Create new product
Write-Host "Creating new product..." -ForegroundColor Cyan
$newProduct = @{
    sku = "TEST-PS-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    name = "PowerShell Test Product"
    price = 299.99
    safety_stock = 10
} | ConvertTo-Json

try {
    $createdProduct = Invoke-RestMethod -Uri "http://localhost:8001/api/inventory/products" -Method POST -Body $newProduct -ContentType "application/json"
    Write-Host "[OK] Product created successfully: ID=$($createdProduct.id), SKU=$($createdProduct.sku)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Product creation failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 3. Stock Management Test
Write-Host "`n=== 3. Stock Management Test ===" -ForegroundColor Yellow

# Adjust stock (increase)
Write-Host "Increasing stock..." -ForegroundColor Cyan
$stockAdjustment = @{ adjustment = 100 } | ConvertTo-Json
try {
    $stockResponse = Invoke-RestMethod -Uri "http://localhost:8001/api/inventory/stock/$($createdProduct.id)/adjust" -Method POST -Body $stockAdjustment -ContentType "application/json"
    Write-Host "[OK] Stock increased successfully: Current stock=$($stockResponse.current_stock)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Stock adjustment failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Adjust stock (reduce to low stock)
Write-Host "Reducing stock to low stock status..." -ForegroundColor Cyan
$stockAdjustment = @{ adjustment = -95 } | ConvertTo-Json
try {
    $stockResponse = Invoke-RestMethod -Uri "http://localhost:8001/api/inventory/stock/$($createdProduct.id)/adjust" -Method POST -Body $stockAdjustment -ContentType "application/json"
    Write-Host "[OK] Stock reduced successfully: Current stock=$($stockResponse.current_stock), Low stock=$($stockResponse.is_low_stock)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Stock adjustment failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Check low stock warning
Write-Host "Checking low stock warning..." -ForegroundColor Cyan
try {
    $lowStockResponse = Invoke-RestMethod -Uri "http://localhost:8001/api/inventory/low-stock" -Method GET
    Write-Host "[OK] Low stock product count: $($lowStockResponse.Count)" -ForegroundColor Green
    $lowStockResponse | ForEach-Object { Write-Host "  - $($_.sku): $($_.name) (Current: $($_.current_stock), Safety: $($_.safety_stock))" -ForegroundColor Red }
} catch {
    Write-Host "[FAIL] Low stock check failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 4. Order Management Test
Write-Host "`n=== 4. Order Management Test ===" -ForegroundColor Yellow

# Create order
Write-Host "Creating order..." -ForegroundColor Cyan
$orderData = @{
    items = @(
        @{
            product_id = $createdProduct.id
            qty = 3
        }
    )
    customer_name = "PowerShell Test Customer"
    customer_email = "test@powershell.com"
    shipping_address = "PowerShell Test Address 123"
    notes = "PowerShell Automated Test Order"
} | ConvertTo-Json -Depth 3

try {
    $createdOrder = Invoke-RestMethod -Uri "http://localhost:8002/api/orders/" -Method POST -Body $orderData -ContentType "application/json"
    Write-Host "[OK] Order created successfully: ID=$($createdOrder.id), Total=$$($createdOrder.total)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Order creation failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Get order list
Write-Host "Getting order list..." -ForegroundColor Cyan
try {
    $orders = Invoke-RestMethod -Uri "http://localhost:8002/api/orders/" -Method GET
    Write-Host "[OK] Order count: $($orders.Count)" -ForegroundColor Green
    $orders | Select-Object -First 3 | ForEach-Object { Write-Host "  - Order #$($_.id): $($_.customer_name) - $($_.status) - $$($_.total)" -ForegroundColor Cyan }
} catch {
    Write-Host "[FAIL] Order list retrieval failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 5. Order Status Update Test
Write-Host "`n=== 5. Order Status Update Test ===" -ForegroundColor Yellow

# Update order status to PAID
Write-Host "Updating order status to PAID..." -ForegroundColor Cyan
$statusUpdate = @{ status = "PAID"; notes = "PowerShell Test Payment Complete" } | ConvertTo-Json
try {
    $updatedOrder = Invoke-RestMethod -Uri "http://localhost:8002/api/orders/$($createdOrder.id)/status" -Method PATCH -Body $statusUpdate -ContentType "application/json"
    Write-Host "[OK] Order status updated to PAID successfully" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Order status update failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Update order status to SHIPPED
Write-Host "Updating order status to SHIPPED..." -ForegroundColor Cyan
$statusUpdate = @{ status = "SHIPPED"; notes = "PowerShell Test Shipping Complete" } | ConvertTo-Json
try {
    $updatedOrder = Invoke-RestMethod -Uri "http://localhost:8002/api/orders/$($createdOrder.id)/status" -Method PATCH -Body $statusUpdate -ContentType "application/json"
    Write-Host "[OK] Order status updated to SHIPPED successfully" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Order status update failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 6. Order Details and Workflow Test
Write-Host "`n=== 6. Order Details and Workflow Test ===" -ForegroundColor Yellow

# Get order details
Write-Host "Getting order details..." -ForegroundColor Cyan
try {
    $orderDetail = Invoke-RestMethod -Uri "http://localhost:8002/api/orders/$($createdOrder.id)" -Method GET
    Write-Host "[OK] Order details:" -ForegroundColor Green
    Write-Host "  Order ID: $($orderDetail.id)" -ForegroundColor Cyan
    Write-Host "  Customer: $($orderDetail.customer_name)" -ForegroundColor Cyan
    Write-Host "  Status: $($orderDetail.status)" -ForegroundColor Cyan
    Write-Host "  Total: $$($orderDetail.total)" -ForegroundColor Cyan
    Write-Host "  Item count: $($orderDetail.items.Count)" -ForegroundColor Cyan
    $orderDetail.items | ForEach-Object { Write-Host "    - $($_.product_sku): $($_.product_name) x $($_.qty) = $$($_.subtotal)" -ForegroundColor Cyan }
} catch {
    Write-Host "[FAIL] Order details retrieval failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Get workflow information
Write-Host "Getting workflow information..." -ForegroundColor Cyan
try {
    $workflowInfo = Invoke-RestMethod -Uri "http://localhost:8002/api/orders/$($createdOrder.id)/workflow" -Method GET
    Write-Host "[OK] Workflow information:" -ForegroundColor Green
    Write-Host "  Current status: $($workflowInfo.current_status)" -ForegroundColor Cyan
    Write-Host "  Valid transitions: $($workflowInfo.valid_transitions -join ', ')" -ForegroundColor Cyan
    Write-Host "  Created at: $($workflowInfo.timeline.created_at)" -ForegroundColor Cyan
    Write-Host "  Paid at: $($workflowInfo.timeline.paid_at)" -ForegroundColor Cyan
    Write-Host "  Shipped at: $($workflowInfo.timeline.shipped_at)" -ForegroundColor Cyan
} catch {
    Write-Host "[FAIL] Workflow information retrieval failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 7. Cleanup Test Data
Write-Host "`n=== 7. Cleanup Test Data ===" -ForegroundColor Yellow
Write-Host "Deleting test product..." -ForegroundColor Cyan
try {
    $deleteResponse = Invoke-RestMethod -Uri "http://localhost:8001/api/inventory/products/$($createdProduct.id)" -Method DELETE
    Write-Host "[OK] Test product deleted successfully: $($deleteResponse.message)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Test product deletion failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 8. Final Statistics
Write-Host "`n=== 8. Final Statistics ===" -ForegroundColor Yellow
try {
    $finalProducts = Invoke-RestMethod -Uri "http://localhost:8001/api/inventory/products" -Method GET
    $finalOrders = Invoke-RestMethod -Uri "http://localhost:8002/api/orders/" -Method GET
    $finalLowStock = Invoke-RestMethod -Uri "http://localhost:8001/api/inventory/low-stock" -Method GET
    
    Write-Host "[OK] System statistics:" -ForegroundColor Green
    Write-Host "  Total products: $($finalProducts.Count)" -ForegroundColor Cyan
    Write-Host "  Total orders: $($finalOrders.Count)" -ForegroundColor Cyan
    Write-Host "  Low stock products: $($finalLowStock.Count)" -ForegroundColor Cyan
} catch {
    Write-Host "[FAIL] Final statistics retrieval failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=== Test Complete ===" -ForegroundColor Green
Write-Host "Completion time: $(Get-Date)" -ForegroundColor Cyan
Write-Host "All functionality tests completed! System is running properly." -ForegroundColor Green