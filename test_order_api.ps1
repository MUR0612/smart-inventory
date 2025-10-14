# Order Service API Test Script

$baseUrl = "http://localhost:8002/api/orders"

Write-Host "=== Testing Order Service API ===" -ForegroundColor Green

# 1. Test health check
Write-Host "`n1. Testing health check..." -ForegroundColor Yellow
try {
    $healthResponse = Invoke-RestMethod -Uri "http://localhost:8002/api/healthz" -Method GET
    Write-Host "[OK] Health check successful" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Health check failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 2. Create test order
Write-Host "`n2. Creating test order..." -ForegroundColor Yellow
$orderData = @{
    items = @(
        @{
            product_id = 1
            qty = 2
        }
    )
    customer_name = "Test Customer"
    customer_email = "test@example.com"
    shipping_address = "Test Address 123"
    notes = "Test Order"
} | ConvertTo-Json -Depth 3

try {
    $createResponse = Invoke-RestMethod -Uri "$baseUrl/" -Method POST -Body $orderData -ContentType "application/json"
    $orderId = $createResponse.id
    Write-Host "[OK] Order created successfully: ID=$orderId" -ForegroundColor Green
    Write-Host "   Order info: $($createResponse | ConvertTo-Json)" -ForegroundColor Cyan
} catch {
    Write-Host "[FAIL] Order creation failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 3. Get order list
Write-Host "`n3. Getting order list..." -ForegroundColor Yellow
try {
    $listResponse = Invoke-RestMethod -Uri "$baseUrl/" -Method GET
    Write-Host "[OK] Order list retrieved successfully: $($listResponse.Count) orders" -ForegroundColor Green
    $listResponse | ForEach-Object { Write-Host "   - Order #$($_.id): $($_.customer_name) - $($_.status) - $$($_.total)" -ForegroundColor Cyan }
} catch {
    Write-Host "[FAIL] Order list retrieval failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 4. Get single order
Write-Host "`n4. Getting single order (ID: $orderId)..." -ForegroundColor Yellow
try {
    $getResponse = Invoke-RestMethod -Uri "$baseUrl/$orderId" -Method GET
    Write-Host "[OK] Single order retrieved successfully" -ForegroundColor Green
    Write-Host "   Order info: $($getResponse | ConvertTo-Json)" -ForegroundColor Cyan
} catch {
    Write-Host "[FAIL] Single order retrieval failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 5. Update order status to PAID
Write-Host "`n5. Updating order status to PAID..." -ForegroundColor Yellow
$statusUpdate = @{
    status = "PAID"
    notes = "Payment completed via test"
} | ConvertTo-Json

try {
    $updateResponse = Invoke-RestMethod -Uri "$baseUrl/$orderId/status" -Method PATCH -Body $statusUpdate -ContentType "application/json"
    Write-Host "[OK] Order status updated to PAID successfully" -ForegroundColor Green
    Write-Host "   Updated order: $($updateResponse | ConvertTo-Json)" -ForegroundColor Cyan
} catch {
    Write-Host "[FAIL] Order status update failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 6. Update order status to SHIPPED
Write-Host "`n6. Updating order status to SHIPPED..." -ForegroundColor Yellow
$statusUpdate = @{
    status = "SHIPPED"
    notes = "Order shipped via test"
} | ConvertTo-Json

try {
    $updateResponse = Invoke-RestMethod -Uri "$baseUrl/$orderId/status" -Method PATCH -Body $statusUpdate -ContentType "application/json"
    Write-Host "[OK] Order status updated to SHIPPED successfully" -ForegroundColor Green
    Write-Host "   Updated order: $($updateResponse | ConvertTo-Json)" -ForegroundColor Cyan
} catch {
    Write-Host "[FAIL] Order status update failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 7. Get order workflow information
Write-Host "`n7. Getting order workflow information..." -ForegroundColor Yellow
try {
    $workflowResponse = Invoke-RestMethod -Uri "$baseUrl/$orderId/workflow" -Method GET
    Write-Host "[OK] Order workflow information retrieved successfully" -ForegroundColor Green
    Write-Host "   Workflow info: $($workflowResponse | ConvertTo-Json)" -ForegroundColor Cyan
} catch {
    Write-Host "[FAIL] Order workflow information retrieval failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 8. Test order refund (since it's already SHIPPED)
Write-Host "`n8. Testing order refund..." -ForegroundColor Yellow
$refundData = @{
    status = "REFUNDED"
    notes = "Order refunded via test"
} | ConvertTo-Json

try {
    $refundResponse = Invoke-RestMethod -Uri "$baseUrl/$orderId/status" -Method PATCH -Body $refundData -ContentType "application/json"
    Write-Host "[OK] Order refunded successfully" -ForegroundColor Green
    Write-Host "   Refunded order: $($refundResponse | ConvertTo-Json)" -ForegroundColor Cyan
} catch {
    Write-Host "[FAIL] Order refund failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 9. Test invalid status transition
Write-Host "`n9. Testing invalid status transition..." -ForegroundColor Yellow
$invalidStatusUpdate = @{
    status = "SHIPPED"
    notes = "Trying to go back to SHIPPED from REFUNDED"
} | ConvertTo-Json

try {
    $invalidResponse = Invoke-RestMethod -Uri "$baseUrl/$orderId/status" -Method PATCH -Body $invalidStatusUpdate -ContentType "application/json"
    Write-Host "[WARN] Invalid status transition was allowed (unexpected)" -ForegroundColor Yellow
} catch {
    Write-Host "[OK] Invalid status transition properly rejected: $($_.Exception.Message)" -ForegroundColor Green
}

# 10. Get final order status
Write-Host "`n10. Getting final order status..." -ForegroundColor Yellow
try {
    $finalResponse = Invoke-RestMethod -Uri "$baseUrl/$orderId" -Method GET
    Write-Host "[OK] Final order status retrieved successfully" -ForegroundColor Green
    Write-Host "   Final order: $($finalResponse | ConvertTo-Json)" -ForegroundColor Cyan
} catch {
    Write-Host "[FAIL] Final order status retrieval failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=== Test Complete ===" -ForegroundColor Green
Write-Host "All Order Service API tests completed!" -ForegroundColor Green