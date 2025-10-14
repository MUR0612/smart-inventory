# GCP 部署腳本 - Smart Inventory (PowerShell)
Write-Host "🚀 開始部署 Smart Inventory 到 GCP Kubernetes..." -ForegroundColor Green

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

# 設定變數
$PROJECT_ID = gcloud config get-value project 2>$null
$CLUSTER_NAME = "infs3208-cluster-1"
$ZONE = "asia-east1-a"

if (-not $PROJECT_ID) {
    Write-Host "❌ 未設定專案 ID。請執行: gcloud config set project YOUR_PROJECT_ID" -ForegroundColor Red
    exit 1
}

Write-Host "📋 部署配置：" -ForegroundColor Yellow
Write-Host "   Project ID: $PROJECT_ID"
Write-Host "   Cluster Name: $CLUSTER_NAME"
Write-Host "   Zone: $ZONE"

# 檢查集群是否存在
Write-Host "🔍 檢查集群是否存在..." -ForegroundColor Green
$clusterExists = gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(name)" 2>$null

if (-not $clusterExists) {
    Write-Host "❌ 集群 $CLUSTER_NAME 不存在於區域 $ZONE" -ForegroundColor Red
    Write-Host "請確認集群名稱和區域是否正確" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ 找到集群: $CLUSTER_NAME" -ForegroundColor Green

# 獲取集群憑證
Write-Host "🔑 獲取集群憑證..." -ForegroundColor Green
gcloud container clusters get-credentials $CLUSTER_NAME --zone=$ZONE

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ 獲取憑證失敗" -ForegroundColor Red
    exit 1
}

# 建立 namespace
Write-Host "📦 建立 namespace..." -ForegroundColor Green
kubectl apply -f namespace.yaml

# 建立 ConfigMap 和 Secret
Write-Host "🔧 建立 ConfigMap 和 Secret..." -ForegroundColor Green
kubectl apply -f configmap.yaml

# 建立 MySQL 和 Redis
Write-Host "🗄️ 部署 MySQL 和 Redis..." -ForegroundColor Green
kubectl apply -f mysql.yaml
kubectl apply -f redis.yaml

# 等待 MySQL 和 Redis 就緒
Write-Host "⏳ 等待 MySQL 和 Redis 就緒..." -ForegroundColor Yellow
kubectl wait --for=condition=ready pod -l app=mysql -n smart-inventory --timeout=300s
kubectl wait --for=condition=ready pod -l app=redis -n smart-inventory --timeout=300s

# 建立微服務
Write-Host "🚀 部署微服務..." -ForegroundColor Green
kubectl apply -f gcp-inventory-service.yaml
kubectl apply -f gcp-order-service.yaml

# 建立 GCP Ingress
Write-Host "🌐 建立 GCP Ingress..." -ForegroundColor Green
kubectl apply -f gcp-ingress.yaml

# 建立 HPA
Write-Host "📈 建立 HPA..." -ForegroundColor Green
kubectl apply -f hpa.yaml

# 等待 Ingress 就緒
Write-Host "⏳ 等待 Ingress 就緒..." -ForegroundColor Yellow
kubectl wait --for=condition=ready ingress/smart-inventory-ingress -n smart-inventory --timeout=300s

Write-Host "✅ 部署完成！" -ForegroundColor Green
Write-Host ""
Write-Host "🔍 檢查 Pod 狀態：" -ForegroundColor Yellow
kubectl get pods -n smart-inventory

Write-Host ""
Write-Host "🌐 檢查服務狀態：" -ForegroundColor Yellow
kubectl get services -n smart-inventory

Write-Host ""
Write-Host "📊 檢查 HPA 狀態：" -ForegroundColor Yellow
kubectl get hpa -n smart-inventory

Write-Host ""
Write-Host "🌍 檢查 Ingress 狀態：" -ForegroundColor Yellow
kubectl get ingress -n smart-inventory

Write-Host ""
Write-Host "🌐 獲取外部 IP：" -ForegroundColor Yellow
$EXTERNAL_IP = kubectl get ingress smart-inventory-ingress -n smart-inventory -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
Write-Host $EXTERNAL_IP

Write-Host ""
Write-Host "📝 測試指令：" -ForegroundColor Yellow
Write-Host "curl http://$EXTERNAL_IP/api/inventory/healthz"
Write-Host "curl http://$EXTERNAL_IP/api/orders/healthz"
