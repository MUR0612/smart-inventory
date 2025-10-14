# 負載測試腳本 - Smart Inventory (PowerShell)
Write-Host "🚀 開始負載測試 Smart Inventory..." -ForegroundColor Green

# 設定變數
$NAMESPACE = "smart-inventory"
$INGRESS_NAME = "smart-inventory-ingress"
$TEST_DURATION = "300s"  # 5分鐘
$CONCURRENT_USERS = 10
$REQUESTS_PER_SECOND = 50

# 檢查必要的工具
try {
    $kubectlVersion = kubectl version --client 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "kubectl 未安裝"
    }
} catch {
    Write-Host "❌ kubectl 未安裝" -ForegroundColor Red
    exit 1
}

# 獲取外部 IP
Write-Host "🌐 獲取外部 IP..." -ForegroundColor Yellow
$EXTERNAL_IP = kubectl get ingress $INGRESS_NAME -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

if (-not $EXTERNAL_IP) {
    Write-Host "❌ 無法獲取外部 IP，請檢查 Ingress 狀態" -ForegroundColor Red
    kubectl get ingress $INGRESS_NAME -n $NAMESPACE
    exit 1
}

Write-Host "📍 外部 IP: $EXTERNAL_IP" -ForegroundColor Green

# 測試基本連通性
Write-Host "🔍 測試基本連通性..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://$EXTERNAL_IP/api/inventory/healthz" -TimeoutSec 10 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host "✅ 基本連通性測試通過" -ForegroundColor Green
    } else {
        Write-Host "❌ 基本連通性測試失敗 (狀態碼: $($response.StatusCode))" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "❌ 基本連通性測試失敗: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 檢查 HPA 狀態
Write-Host "📊 檢查 HPA 狀態..." -ForegroundColor Yellow
kubectl get hpa -n $NAMESPACE

# 開始負載測試
Write-Host "🚀 開始負載測試..." -ForegroundColor Green
Write-Host "   持續時間: $TEST_DURATION"
Write-Host "   並發用戶: $CONCURRENT_USERS"
Write-Host "   目標 RPS: $REQUESTS_PER_SECOND"

# 檢查是否有 hey 工具
try {
    $heyVersion = hey -version 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "📈 使用 hey 進行負載測試..." -ForegroundColor Yellow
        
        # 啟動 hey 負載測試
        $heyProcess = Start-Process -FilePath "hey" -ArgumentList "-n", "10000", "-c", $CONCURRENT_USERS, "-q", $REQUESTS_PER_SECOND, "-z", $TEST_DURATION, "http://$EXTERNAL_IP/api/inventory/healthz" -PassThru -NoNewWindow
        
        # 監控 HPA 和 Pod 狀態
        Write-Host "📊 監控 HPA 和 Pod 狀態..." -ForegroundColor Yellow
        Write-Host "按 Ctrl+C 停止監控" -ForegroundColor Yellow
        
        while (-not $heyProcess.HasExited) {
            Write-Host "=== $(Get-Date) ===" -ForegroundColor Cyan
            Write-Host "HPA 狀態:" -ForegroundColor Yellow
            kubectl get hpa -n $NAMESPACE
            Write-Host ""
            Write-Host "Pod 狀態:" -ForegroundColor Yellow
            kubectl get pods -n $NAMESPACE
            Write-Host ""
            Write-Host "Pod 資源使用:" -ForegroundColor Yellow
            try {
                kubectl top pods -n $NAMESPACE 2>$null
            } catch {
                Write-Host "Metrics server 未安裝" -ForegroundColor Yellow
            }
            Write-Host ""
            Start-Sleep -Seconds 30
        }
        
        # 等待 hey 完成
        $heyProcess.WaitForExit()
        
    } else {
        throw "hey 工具未安裝"
    }
} catch {
    Write-Host "⚠️  hey 工具未安裝，使用 PowerShell 進行簡單測試..." -ForegroundColor Yellow
    Write-Host "安裝 hey: go install github.com/rakyll/hey@latest" -ForegroundColor Yellow
    
    # 使用 PowerShell 進行簡單的並發測試
    Write-Host "🔄 開始簡單負載測試..." -ForegroundColor Yellow
    
    $jobs = @()
    for ($i = 1; $i -le 100; $i++) {
        $job = Start-Job -ScriptBlock {
            param($url)
            try {
                $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10
                return $response.StatusCode
            } catch {
                return "Error: $($_.Exception.Message)"
            }
        } -ArgumentList "http://$EXTERNAL_IP/api/inventory/healthz"
        
        $jobs += $job
        
        if ($i % 10 -eq 0) {
            Write-Host "已發送 $i 個請求" -ForegroundColor Yellow
            Start-Sleep -Seconds 1
        }
    }
    
    # 等待所有作業完成
    $jobs | Wait-Job | Out-Null
    
    # 收集結果
    $results = $jobs | Receive-Job
    $successCount = ($results | Where-Object { $_ -eq 200 }).Count
    $errorCount = ($results | Where-Object { $_ -ne 200 }).Count
    
    Write-Host "✅ 負載測試完成！" -ForegroundColor Green
    Write-Host "   成功請求: $successCount" -ForegroundColor Green
    Write-Host "   失敗請求: $errorCount" -ForegroundColor Red
    
    # 清理作業
    $jobs | Remove-Job
}

Write-Host "✅ 負載測試完成！" -ForegroundColor Green

