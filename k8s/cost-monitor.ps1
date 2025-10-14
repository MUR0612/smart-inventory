# 成本監控腳本 - Smart Inventory (PowerShell)
Write-Host "💰 開始監控 Smart Inventory GCP 成本..." -ForegroundColor Green

# 設定變數
$PROJECT_ID = gcloud config get-value project 2>$null
$CLUSTER_NAME = "smart-inventory-cluster"
$ZONE = "asia-east1-a"

if (-not $PROJECT_ID) {
    Write-Host "❌ 未設定專案 ID。請執行: gcloud config set project YOUR_PROJECT_ID" -ForegroundColor Red
    exit 1
}

Write-Host "📋 專案 ID: $PROJECT_ID" -ForegroundColor Yellow

# 檢查 gcloud 是否已安裝並登入
try {
    $gcloudVersion = gcloud version 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud CLI 未安裝"
    }
} catch {
    Write-Host "❌ gcloud CLI 未安裝。請先安裝 Google Cloud SDK" -ForegroundColor Red
    exit 1
}

# 檢查是否已登入
$activeAccount = gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>$null
if (-not $activeAccount) {
    Write-Host "❌ 請先登入 Google Cloud: gcloud auth login" -ForegroundColor Red
    exit 1
}

Write-Host "🔍 檢查 GCP 資源使用情況..." -ForegroundColor Yellow

# 檢查 GKE 集群狀態
Write-Host "`n📊 GKE 集群狀態:" -ForegroundColor Cyan
$clusterInfo = gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="table(name,status,currentMasterVersion,currentNodeCount,currentNodeVersion)" 2>$null
if ($clusterInfo) {
    Write-Host $clusterInfo
} else {
    Write-Host "❌ 集群不存在或無法訪問" -ForegroundColor Red
}

# 檢查節點狀態
Write-Host "`n🖥️ 節點狀態:" -ForegroundColor Cyan
$nodeInfo = gcloud compute instances list --filter="name~$CLUSTER_NAME" --format="table(name,status,machineType,zone)" 2>$null
if ($nodeInfo) {
    Write-Host $nodeInfo
} else {
    Write-Host "❌ 無法獲取節點資訊" -ForegroundColor Red
}

# 檢查 Load Balancer
Write-Host "`n🌐 Load Balancer 狀態:" -ForegroundColor Cyan
$lbInfo = gcloud compute forwarding-rules list --format="table(name,region,IPAddress,target)" 2>$null
if ($lbInfo) {
    Write-Host $lbInfo
} else {
    Write-Host "ℹ️  未找到 Load Balancer" -ForegroundColor Yellow
}

# 檢查靜態 IP
Write-Host "`n🌍 靜態 IP 狀態:" -ForegroundColor Cyan
$ipInfo = gcloud compute addresses list --format="table(name,region,address,status)" 2>$null
if ($ipInfo) {
    Write-Host $ipInfo
} else {
    Write-Host "ℹ️  未找到靜態 IP" -ForegroundColor Yellow
}

# 檢查 Container Registry 使用情況
Write-Host "`n🐳 Container Registry 使用情況:" -ForegroundColor Cyan
$registryInfo = gcloud container images list --repository=gcr.io/$PROJECT_ID --format="table(name,digest,creationTime)" 2>$null
if ($registryInfo) {
    Write-Host $registryInfo
} else {
    Write-Host "ℹ️  未找到容器映像檔" -ForegroundColor Yellow
}

# 估算成本
Write-Host "`n💰 成本估算:" -ForegroundColor Cyan
Write-Host "基於 e2-standard-2 (2 vCPU, 8GB RAM) 2 個節點:" -ForegroundColor Yellow
Write-Host "  - GKE 集群: ~$0.10/小時" -ForegroundColor White
Write-Host "  - Load Balancer: ~$0.025/小時" -ForegroundColor White
Write-Host "  - 靜態 IP: ~$0.004/小時 (未使用時)" -ForegroundColor White
Write-Host "  - 總計: ~$0.13/小時" -ForegroundColor Green

# 檢查 Kubernetes 資源使用
Write-Host "`n📊 Kubernetes 資源使用:" -ForegroundColor Cyan
try {
    $podInfo = kubectl get pods -n smart-inventory --no-headers 2>$null
    if ($podInfo) {
        Write-Host "Pod 狀態:" -ForegroundColor Yellow
        kubectl get pods -n smart-inventory
        Write-Host ""
        
        Write-Host "資源使用情況:" -ForegroundColor Yellow
        try {
            kubectl top pods -n smart-inventory 2>$null
        } catch {
            Write-Host "Metrics server 未安裝，無法獲取資源使用情況" -ForegroundColor Yellow
        }
        
        Write-Host ""
        Write-Host "HPA 狀態:" -ForegroundColor Yellow
        kubectl get hpa -n smart-inventory 2>$null
    } else {
        Write-Host "❌ 無法獲取 Kubernetes 資源資訊" -ForegroundColor Red
    }
} catch {
    Write-Host "❌ 無法連接到 Kubernetes 集群" -ForegroundColor Red
}

# 提供成本控制建議
Write-Host "`n💡 成本控制建議:" -ForegroundColor Cyan
Write-Host "1. 設定自動關閉: 使用 Cloud Scheduler 在非工作時間關閉集群" -ForegroundColor White
Write-Host "2. 監控使用量: 定期檢查 GCP Console 中的計費資訊" -ForegroundColor White
Write-Host "3. 及時清理: 測試完成後立即執行清理腳本" -ForegroundColor White
Write-Host "4. 使用預留實例: 長期使用可考慮預留實例以降低成本" -ForegroundColor White

# 提供清理指令
Write-Host "`n🧹 清理指令:" -ForegroundColor Cyan
Write-Host "執行以下指令清理資源:" -ForegroundColor Yellow
Write-Host "  .\gcp-cleanup.ps1" -ForegroundColor White

Write-Host "`n✅ 成本監控完成！" -ForegroundColor Green

