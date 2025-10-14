# Simple Inventory Service API Test Script

$baseUrl = "http://localhost:8001/api/inventory"

Write-Host "=== Testing Inventory Service API ===" -ForegroundColor Green

# 1. Test health check
Write-Host "`n1. Testing health check..." -ForegroundColor Yellow
try {
    $healthResponse = Invoke-RestMethod -Uri "http://localhost:8001/api/healthz" -Method GET
    Write-Host "[OK] Health check successful" -ForegroundColor Green
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
} catch {
    Write-Host "[FAIL] Product creation failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 3. Get product list
Write-Host "`n3. Getting product list..." -ForegroundColor Yellow
try {
    $listResponse = Invoke-RestMethod -Uri "$baseUrl/products" -Method GET
    Write-Host "[OK] Product list retrieved successfully: $($listResponse.Count) products" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Product list retrieval failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 4. Adjust stock
Write-Host "`n4. Adjusting stock..." -ForegroundColor Yellow
$stockAdjustment = @{ adjustment = 50 } | ConvertTo-Json

try {
    $stockResponse = Invoke-RestMethod -Uri "$baseUrl/stock/$productId/adjust" -Method POST -Body $stockAdjustment -ContentType "application/json"
    Write-Host "[OK] Stock adjustment successful: Current stock = $($stockResponse.current_stock)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Stock adjustment failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 5. Check low stock
Write-Host "`n5. Checking low stock..." -ForegroundColor Yellow
try {
    $lowStockResponse = Invoke-RestMethod -Uri "$baseUrl/low-stock" -Method GET
    Write-Host "[OK] Low stock check successful: $($lowStockResponse.Count) low stock products" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Low stock check failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 6. Delete product
Write-Host "`n6. Deleting product..." -ForegroundColor Yellow
try {
    $deleteResponse = Invoke-RestMethod -Uri "$baseUrl/products/$productId" -Method DELETE
    Write-Host "[OK] Product deleted successfully" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Product deletion failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=== Test Complete ===" -ForegroundColor Green
Write-Host "Simple API test completed!" -ForegroundColor Green