# Test Inventory Service API PowerShell Script

$baseUrl = "http://localhost:8001/api/inventory"

Write-Host "=== Testing Inventory Service API ===" -ForegroundColor Green

# 1. Test health check
Write-Host "`n1. Testing health check..." -ForegroundColor Yellow
try {
    $healthResponse = Invoke-RestMethod -Uri "http://localhost:8001/api/healthz" -Method GET
    Write-Host "[OK] Health check successful: $($healthResponse | ConvertTo-Json)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Health check failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 2. Create test product
Write-Host "`n2. Creating test product..." -ForegroundColor Yellow
$productData = @{
    sku = "TEST-001"
    name = "Test Product"
    price = 99.99
    safety_stock = 10
} | ConvertTo-Json

try {
    $createResponse = Invoke-RestMethod -Uri "$baseUrl/products" -Method POST -Body $productData -ContentType "application/json"
    $productId = $createResponse.id
    Write-Host "[OK] Product created successfully: ID=$productId" -ForegroundColor Green
    Write-Host "   Product info: $($createResponse | ConvertTo-Json)" -ForegroundColor Cyan
} catch {
    Write-Host "[FAIL] Product creation failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 3. Get product list
Write-Host "`n3. Getting product list..." -ForegroundColor Yellow
try {
    $listResponse = Invoke-RestMethod -Uri "$baseUrl/products" -Method GET
    Write-Host "[OK] Product list retrieved successfully: $($listResponse.Count) products" -ForegroundColor Green
    $listResponse | ForEach-Object { Write-Host "   - $($_.sku): $($_.name) (Stock: $($_.stock))" -ForegroundColor Cyan }
} catch {
    Write-Host "[FAIL] Product list retrieval failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 4. Get single product
Write-Host "`n4. Getting single product (ID: $productId)..." -ForegroundColor Yellow
try {
    $getResponse = Invoke-RestMethod -Uri "$baseUrl/products/$productId" -Method GET
    Write-Host "[OK] Single product retrieved successfully" -ForegroundColor Green
    Write-Host "   Product info: $($getResponse | ConvertTo-Json)" -ForegroundColor Cyan
} catch {
    Write-Host "[FAIL] Single product retrieval failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 5. Update product
Write-Host "`n5. Updating product..." -ForegroundColor Yellow
$updateData = @{
    name = "Updated Test Product"
    price = 149.99
    safety_stock = 15
} | ConvertTo-Json

try {
    $updateResponse = Invoke-RestMethod -Uri "$baseUrl/products/$productId" -Method PUT -Body $updateData -ContentType "application/json"
    Write-Host "[OK] Product updated successfully" -ForegroundColor Green
    Write-Host "   Updated info: $($updateResponse | ConvertTo-Json)" -ForegroundColor Cyan
} catch {
    Write-Host "[FAIL] Product update failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 6. Get stock information
Write-Host "`n6. Getting stock information..." -ForegroundColor Yellow
try {
    $stockInfo = Invoke-RestMethod -Uri "$baseUrl/stock/$productId" -Method GET
    Write-Host "[OK] Stock information retrieved successfully" -ForegroundColor Green
    Write-Host "   Stock info: $($stockInfo | ConvertTo-Json)" -ForegroundColor Cyan
} catch {
    Write-Host "[FAIL] Stock information retrieval failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 7. Adjust stock (increase)
Write-Host "`n7. Adjusting stock (increase)..." -ForegroundColor Yellow
$stockAdjustment = @{ adjustment = 50 } | ConvertTo-Json

try {
    $stockResponse = Invoke-RestMethod -Uri "$baseUrl/stock/$productId/adjust" -Method POST -Body $stockAdjustment -ContentType "application/json"
    Write-Host "[OK] Stock adjustment successful (increase)" -ForegroundColor Green
    Write-Host "   Stock info: $($stockResponse | ConvertTo-Json)" -ForegroundColor Cyan
} catch {
    Write-Host "[FAIL] Stock adjustment failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 8. Adjust stock (decrease to trigger low stock warning)
Write-Host "`n8. Adjusting stock (decrease to trigger low stock warning)..." -ForegroundColor Yellow
$stockAdjustment = @{ adjustment = -45 } | ConvertTo-Json

try {
    $stockResponse = Invoke-RestMethod -Uri "$baseUrl/stock/$productId/adjust" -Method POST -Body $stockAdjustment -ContentType "application/json"
    Write-Host "[OK] Stock adjustment successful (triggered low stock warning)" -ForegroundColor Green
    Write-Host "   Stock info: $($stockResponse | ConvertTo-Json)" -ForegroundColor Cyan
} catch {
    Write-Host "[FAIL] Stock adjustment failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 9. Get low stock products list
Write-Host "`n9. Getting low stock products list..." -ForegroundColor Yellow
try {
    $lowStockResponse = Invoke-RestMethod -Uri "$baseUrl/low-stock" -Method GET
    Write-Host "[OK] Low stock list retrieved successfully: $($lowStockResponse.Count) low stock products" -ForegroundColor Green
    $lowStockResponse | ForEach-Object { Write-Host "   - $($_.sku): $($_.name) (Current: $($_.current_stock), Safety: $($_.safety_stock))" -ForegroundColor Red }
} catch {
    Write-Host "[FAIL] Low stock list retrieval failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 10. Get all stock information
Write-Host "`n10. Getting all stock information..." -ForegroundColor Yellow
try {
    $allStockResponse = Invoke-RestMethod -Uri "$baseUrl/stock" -Method GET
    Write-Host "[OK] All stock information retrieved successfully: $($allStockResponse.Count) products" -ForegroundColor Green
    $allStockResponse | ForEach-Object { 
        $status = if ($_.is_low_stock) { "[LOW STOCK]" } else { "[NORMAL]" }
        Write-Host "   - $($_.sku): $($_.name) (Stock: $($_.current_stock)/$($_.safety_stock)) $status" -ForegroundColor Cyan 
    }
} catch {
    Write-Host "[FAIL] All stock information retrieval failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 11. Delete product
Write-Host "`n11. Deleting product..." -ForegroundColor Yellow
try {
    $deleteResponse = Invoke-RestMethod -Uri "$baseUrl/products/$productId" -Method DELETE
    Write-Host "[OK] Product deleted successfully: $($deleteResponse.message)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Product deletion failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=== Test Complete ===" -ForegroundColor Green
Write-Host "All Inventory Service API tests completed!" -ForegroundColor Green