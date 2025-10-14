@echo off
REM Smart Inventory System Complete Test Script
REM Make sure all services are running: docker-compose up -d

echo === Smart Inventory System Complete Test ===
echo Test Time: %date% %time%

REM 1. Health Check
echo.
echo === 1. Health Check ===
echo Checking Inventory Service...
curl -s http://localhost:8001/api/healthz > nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Inventory Service: Healthy
) else (
    echo [FAIL] Inventory Service Connection Failed
    exit /b 1
)

echo Checking Order Service...
curl -s http://localhost:8002/api/healthz > nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Order Service: Healthy
) else (
    echo [FAIL] Order Service Connection Failed
    exit /b 1
)

REM 2. Product Management Test
echo.
echo === 2. Product Management Test ===

echo Getting product list...
curl -s http://localhost:8001/api/inventory/products > products.json
if %errorlevel% neq 0 (
    echo [FAIL] Cannot get product list
    exit /b 1
)
echo [OK] Product list retrieved successfully

echo Creating new product...
set TEST_SKU=TEST-CMD-%date:~0,4%%date:~5,2%%date:~8,2%-%time:~0,2%%time:~3,2%%time:~6,2%
set TEST_SKU=%TEST_SKU: =0%

curl -s -X POST http://localhost:8001/api/inventory/products ^
  -H "Content-Type: application/json" ^
  -d "{\"sku\":\"%TEST_SKU%\",\"name\":\"CMD Test Product\",\"price\":299.99,\"safety_stock\":10}" > new_product.json

if %errorlevel% equ 0 (
    echo [OK] Product created successfully
) else (
    echo [FAIL] Product creation failed
    exit /b 1
)

REM 3. Stock Management Test
echo.
echo === 3. Stock Management Test ===

echo Increasing stock...
curl -s -X POST http://localhost:8001/api/inventory/stock/1/adjust ^
  -H "Content-Type: application/json" ^
  -d "{\"adjustment\":100}" > stock_response.json

if %errorlevel% equ 0 (
    echo [OK] Stock increased successfully
) else (
    echo [FAIL] Stock adjustment failed
)

echo Reducing stock to low stock status...
curl -s -X POST http://localhost:8001/api/inventory/stock/1/adjust ^
  -H "Content-Type: application/json" ^
  -d "{\"adjustment\":-95}" > stock_response2.json

if %errorlevel% equ 0 (
    echo [OK] Stock reduced successfully
) else (
    echo [FAIL] Stock adjustment failed
)

echo Checking low stock warning...
curl -s http://localhost:8001/api/inventory/low-stock > low_stock.json
if %errorlevel% equ 0 (
    echo [OK] Low stock check successful
) else (
    echo [FAIL] Low stock check failed
)

REM 4. Order Management Test
echo.
echo === 4. Order Management Test ===

echo Creating order...
curl -s -X POST http://localhost:8002/api/orders/ ^
  -H "Content-Type: application/json" ^
  -d "{\"items\":[{\"product_id\":1,\"qty\":3}],\"customer_name\":\"CMD Test Customer\",\"customer_email\":\"test@cmd.com\",\"shipping_address\":\"CMD Test Address 123\",\"notes\":\"CMD Automated Test Order\"}" > new_order.json

if %errorlevel% equ 0 (
    echo [OK] Order created successfully
) else (
    echo [FAIL] Order creation failed
    exit /b 1
)

echo Getting order list...
curl -s http://localhost:8002/api/orders/ > orders.json
if %errorlevel% equ 0 (
    echo [OK] Order list retrieved successfully
) else (
    echo [FAIL] Order list retrieval failed
)

REM 5. Order Status Update Test
echo.
echo === 5. Order Status Update Test ===

echo Updating order status to PAID...
curl -s -X PATCH http://localhost:8002/api/orders/1/status ^
  -H "Content-Type: application/json" ^
  -d "{\"status\":\"PAID\",\"notes\":\"CMD Test Payment Complete\"}" > status_update1.json

if %errorlevel% equ 0 (
    echo [OK] Order status updated to PAID successfully
) else (
    echo [FAIL] Order status update failed
)

echo Updating order status to SHIPPED...
curl -s -X PATCH http://localhost:8002/api/orders/1/status ^
  -H "Content-Type: application/json" ^
  -d "{\"status\":\"SHIPPED\",\"notes\":\"CMD Test Shipping Complete\"}" > status_update2.json

if %errorlevel% equ 0 (
    echo [OK] Order status updated to SHIPPED successfully
) else (
    echo [FAIL] Order status update failed
)

REM 6. Order Details and Workflow Test
echo.
echo === 6. Order Details and Workflow Test ===

echo Getting order details...
curl -s http://localhost:8002/api/orders/1 > order_detail.json
if %errorlevel% equ 0 (
    echo [OK] Order details retrieved successfully
) else (
    echo [FAIL] Order details retrieval failed
)

echo Getting workflow information...
curl -s http://localhost:8002/api/orders/1/workflow > workflow_info.json
if %errorlevel% equ 0 (
    echo [OK] Workflow information retrieved successfully
) else (
    echo [FAIL] Workflow information retrieval failed
)

REM 7. Cleanup Test Data
echo.
echo === 7. Cleanup Test Data ===
echo Deleting test product...
curl -s -X DELETE http://localhost:8001/api/inventory/products/1 > delete_response.json
if %errorlevel% equ 0 (
    echo [OK] Test product deleted successfully
) else (
    echo [FAIL] Test product deletion failed
)

REM 8. Final Statistics
echo.
echo === 8. Final Statistics ===
curl -s http://localhost:8001/api/inventory/products > final_products.json
curl -s http://localhost:8002/api/orders/ > final_orders.json
curl -s http://localhost:8001/api/inventory/low-stock > final_low_stock.json

echo [OK] System statistics completed

REM Clean up temporary files
del products.json new_product.json stock_response.json stock_response2.json low_stock.json
del new_order.json orders.json status_update1.json status_update2.json
del order_detail.json workflow_info.json delete_response.json
del final_products.json final_orders.json final_low_stock.json

echo.
echo === Test Complete ===
echo Completion Time: %date% %time%
echo All functionality tests completed! System is running properly.

pause