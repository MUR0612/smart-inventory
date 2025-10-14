# PowerShell Testing Guide

## 🚀 Quick Start

### 1. Environment Setup
Set environment variables in PowerShell (if no .env file exists):

```powershell
# Set environment variables
$env:MYSQL_ROOT_PASSWORD = "rootpassword123"
$env:MYSQL_DATABASE = "smart_inventory"
$env:MYSQL_USER = "inventory_user"
$env:MYSQL_PASSWORD = "inventory_pass123"
$env:DB_URL = "mysql+pymysql://inventory_user:inventory_pass123@mysql:3306/smart_inventory"
$env:REDIS_HOST = "redis"
$env:REDIS_PORT = "6379"
$env:INVENTORY_PORT = "8001"
$env:ORDER_PORT = "8002"
```

### 2. Start System
```powershell
# Method 1: Use existing script
.\scripts.ps1

# Method 2: Manual start
docker-compose up -d --build
```

### 3. Check Service Status
```powershell
# Check container status
docker-compose ps

# Check service logs
docker-compose logs --tail=20 inventory-service order-service
```

## 🧪 Test Scripts

### 1. Complete System Test (Recommended)

#### Method A: Use CMD Batch File (Avoids execution policy restrictions)

**Execute in PowerShell:**
```powershell
# Ensure you're in the correct directory
cd "C:\Users\user\Desktop\INFS3208\assignment individual project\smart-inventory"

# Execute CMD batch file
.\test_complete_system.cmd
```
**Features:**
- ✅ Health checks
- ✅ Product CRUD operations
- ✅ Inventory management and low stock warnings
- ✅ Order creation and workflow
- ✅ Order status updates (CREATED → PAID → SHIPPED)
- ✅ Automatic test data cleanup

#### Method B: Manual PowerShell Commands (Most secure)

**If you encounter Chinese encoding issues, use the following methods:**

```powershell
# Method 1: Use English version (recommended)
Get-Content .\test_simple_commands.ps1

# Method 2: Quick health check
Get-Content .\test_health_check.ps1
```

Then copy and paste the commands one by one into PowerShell.

#### Method C: PowerShell Script (Requires execution policy)
```powershell
# If execution policy allows
.\test_complete_system.ps1
```

### 2. Individual Service Tests

#### Inventory Service Test
```powershell
.\test_inventory_api.ps1
```
**Features:**
- Product management (create, read, update, delete)
- Stock adjustment and queries
- Low stock warning system
- Redis cache functionality

#### Order Service Test
```powershell
.\test_order_api.ps1
```
**Features:**
- Order creation and queries
- Order status management
- Workflow validation
- Order cancellation functionality

#### Simple API Test
```powershell
.\test_api_simple.ps1
```
**Features:**
- Basic health checks
- Simple product operations
- Stock adjustment tests

## 🔍 Manual Test Commands

### Quick Health Check (Recommended)
```powershell
# One-click health check (via Nginx)
try { Invoke-RestMethod -Uri "http://localhost:8080/healthz" -Method GET; Write-Host "Nginx: Healthy" -ForegroundColor Green } catch { Write-Host "Nginx: Failed" -ForegroundColor Red }
try { Invoke-RestMethod -Uri "http://localhost:8080/api/inventory/healthz" -Method GET; Write-Host "Inventory Service: Healthy" -ForegroundColor Green } catch { Write-Host "Inventory Service: Failed" -ForegroundColor Red }
try { Invoke-RestMethod -Uri "http://localhost:8080/api/orders/healthz" -Method GET; Write-Host "Order Service: Healthy" -ForegroundColor Green } catch { Write-Host "Order Service: Failed" -ForegroundColor Red }

# Or use health check script
Get-Content .\test_health_check.ps1
```

### Detailed Health Check
```powershell
# Via Nginx (recommended)
Invoke-RestMethod -Uri "http://localhost:8080/healthz"
Invoke-RestMethod -Uri "http://localhost:8080/api/inventory/healthz"
Invoke-RestMethod -Uri "http://localhost:8080/api/orders/healthz"

# Direct service access
Invoke-RestMethod -Uri "http://localhost:8001/api/healthz"
Invoke-RestMethod -Uri "http://localhost:8002/api/healthz"
```

### Product Management
```powershell
# Create product
$product = @{
    sku = "TEST-001"
    name = "Test Product"
    price = 99.99
    safety_stock = 10
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8001/api/inventory/products" -Method POST -Body $product -ContentType "application/json"

# Get product list
Invoke-RestMethod -Uri "http://localhost:8001/api/inventory/products" -Method GET
```

### Order Management
```powershell
# Create order
$order = @{
    items = @(
        @{
            product_id = 1
            qty = 2
        }
    )
    customer_name = "Test Customer"
    customer_email = "test@example.com"
    shipping_address = "Test Address"
} | ConvertTo-Json -Depth 3

Invoke-RestMethod -Uri "http://localhost:8002/api/orders/" -Method POST -Body $order -ContentType "application/json"
```

## 🐛 Troubleshooting

### Common Issues

1. **PowerShell Execution Policy Error**
   ```
   Error: Cannot load file because script execution is disabled on this system
   ```
   **Solutions:**
   - Use CMD batch file: `.\test_complete_system.cmd`
   - Use manual commands: `Get-Content .\test_simple_commands.ps1`
   - Or modify execution policy (not recommended): `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

2. **Service Won't Start**
   ```powershell
   # Check logs
   docker-compose logs inventory-service
   docker-compose logs order-service
   
   # Rebuild
   docker-compose down
   docker-compose up -d --build
   ```

3. **Database Connection Failed**
   ```powershell
   # Check MySQL status
   docker-compose logs mysql
   
   # Check environment variables
   docker-compose config
   ```

4. **API Call Failed**
   ```powershell
   # Check if services are running
   docker-compose ps
   
   # Check if ports are correct
   netstat -an | findstr "8001\|8002\|8080"
   ```

5. **Kaspersky Antivirus Blocking**
   - Use CMD batch files instead of PowerShell scripts
   - Add project folder to antivirus whitelist
   - Use manual command approach for testing

### Reset System
```powershell
# Complete reset
docker-compose down -v
docker-compose up -d --build
```

## 📊 Test Results Verification

### Success Indicators
- ✅ All health checks pass
- ✅ Product CRUD operations work properly
- ✅ Stock adjustment and low stock warnings work properly
- ✅ Order workflow is complete (CREATED → PAID → SHIPPED)
- ✅ Inter-service communication works properly
- ✅ Redis cache functionality works properly

### Expected Output Example
```
=== Smart Inventory System Complete Test ===
[OK] Inventory Service: healthy
[OK] Order Service: healthy
[OK] Product created successfully: ID=1, SKU=TEST-PS-20241201-143022
[OK] Stock increased successfully: Current stock=100
[OK] Stock reduced successfully: Current stock=5, Low stock=True
[OK] Low stock product count: 1
[OK] Order created successfully: ID=1, Total=$599.98
[OK] Order status updated to PAID successfully
[OK] Order status updated to SHIPPED successfully
[OK] Test product deleted successfully
=== Test Complete ===
```

## 🎯 Recommended Testing Workflow

### 1. Quick Test (30 seconds)
```cmd
# Use CMD batch file for complete testing
.\test_complete_system.cmd
```

### 2. Manual Test (5 minutes)
```powershell
# View test commands
Get-Content .\test_simple_commands.ps1

# Execute quick health check
try { Invoke-RestMethod -Uri "http://localhost:8080/healthz" -Method GET; Write-Host "Nginx: Healthy" -ForegroundColor Green } catch { Write-Host "Nginx: Failed" -ForegroundColor Red }
try { Invoke-RestMethod -Uri "http://localhost:8080/api/inventory/healthz" -Method GET; Write-Host "Inventory Service: Healthy" -ForegroundColor Green } catch { Write-Host "Inventory Service: Failed" -ForegroundColor Red }
try { Invoke-RestMethod -Uri "http://localhost:8080/api/orders/healthz" -Method GET; Write-Host "Order Service: Healthy" -ForegroundColor Green } catch { Write-Host "Order Service: Failed" -ForegroundColor Red }
```

### 3. Next Steps
After completing local tests, you can:
1. Deploy to Kubernetes for scalability testing
2. Use load testing to verify HPA functionality
3. Deploy to GCP for cloud validation
4. Present to instructor for grading