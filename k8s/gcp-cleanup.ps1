# GCP 清理腳本 - Smart Inventory (PowerShell)
Write-Host "🧹 開始清理 Smart Inventory GCP 資源..." -ForegroundColor Green

# 設定變數
$CLUSTER_NAME = "smart-inventory-cluster"
$ZONE = "asia-east1-a"

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

Write-Host "⚠️  這將刪除以下資源：" -ForegroundColor Yellow
Write-Host "   - GKE 集群: $CLUSTER_NAME" -ForegroundColor White
Write-Host "   - 所有相關的 Pod、Service、Ingress" -ForegroundColor White
Write-Host "   - 靜態 IP (如果存在)" -ForegroundColor White
Write-Host ""

$confirmation = Read-Host "確定要繼續嗎？(y/N)"
if ($confirmation -ne "y" -and $confirmation -ne "Y") {
    Write-Host "❌ 取消清理操作" -ForegroundColor Red
    exit 1
}

# 刪除 Kubernetes 資源
Write-Host "🗑️ 刪除 Kubernetes 資源..." -ForegroundColor Yellow
try {
    kubectl delete namespace smart-inventory --ignore-not-found=true
    Write-Host "✅ Kubernetes 資源已刪除" -ForegroundColor Green
} catch {
    Write-Host "⚠️  刪除 Kubernetes 資源時發生錯誤: $($_.Exception.Message)" -ForegroundColor Yellow
}

# 刪除 GKE 集群
Write-Host "🗑️ 刪除 GKE 集群..." -ForegroundColor Yellow
try {
    gcloud container clusters delete $CLUSTER_NAME --zone=$ZONE --quiet
    Write-Host "✅ GKE 集群已刪除" -ForegroundColor Green
} catch {
    Write-Host "❌ 刪除 GKE 集群失敗: $($_.Exception.Message)" -ForegroundColor Red
}

# 刪除靜態 IP (如果存在)
Write-Host "🗑️ 檢查並刪除靜態 IP..." -ForegroundColor Yellow
$STATIC_IP_NAME = "smart-inventory-ip"
try {
    $ipExists = gcloud compute addresses describe $STATIC_IP_NAME --global --quiet 2>$null
    if ($LASTEXITCODE -eq 0) {
        gcloud compute addresses delete $STATIC_IP_NAME --global --quiet
        Write-Host "✅ 已刪除靜態 IP: $STATIC_IP_NAME" -ForegroundColor Green
    } else {
        Write-Host "ℹ️  未找到靜態 IP: $STATIC_IP_NAME" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️  檢查靜態 IP 時發生錯誤: $($_.Exception.Message)" -ForegroundColor Yellow
}

# 檢查是否還有其他相關資源
Write-Host "`n🔍 檢查其他相關資源..." -ForegroundColor Yellow

# 檢查 Load Balancer
Write-Host "檢查 Load Balancer..." -ForegroundColor Yellow
$lbInfo = gcloud compute forwarding-rules list --format="value(name)" 2>$null
if ($lbInfo) {
    Write-Host "發現 Load Balancer: $lbInfo" -ForegroundColor Yellow
    Write-Host "請手動刪除: gcloud compute forwarding-rules delete $lbInfo" -ForegroundColor White
} else {
    Write-Host "✅ 未發現 Load Balancer" -ForegroundColor Green
}

# 檢查防火牆規則
Write-Host "檢查防火牆規則..." -ForegroundColor Yellow
$firewallRules = gcloud compute firewall-rules list --filter="name~$CLUSTER_NAME" --format="value(name)" 2>$null
if ($firewallRules) {
    Write-Host "發現防火牆規則: $firewallRules" -ForegroundColor Yellow
    Write-Host "請手動刪除: gcloud compute firewall-rules delete $firewallRules" -ForegroundColor White
} else {
    Write-Host "✅ 未發現相關防火牆規則" -ForegroundColor Green
}

Write-Host "`n✅ 清理完成！" -ForegroundColor Green
Write-Host ""
Write-Host "💰 成本控制提醒：" -ForegroundColor Cyan
Write-Host "   - GKE 集群已刪除，不再產生計算費用" -ForegroundColor White
Write-Host "   - 靜態 IP 已釋放，不再產生網路費用" -ForegroundColor White
Write-Host "   - 請檢查 GCP Console 確認所有資源已清理" -ForegroundColor White

Write-Host "`n🔗 相關連結：" -ForegroundColor Cyan
Write-Host "   - GCP Console: https://console.cloud.google.com/" -ForegroundColor White
Write-Host "   - 計費資訊: https://console.cloud.google.com/billing" -ForegroundColor White
