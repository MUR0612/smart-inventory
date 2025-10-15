#!/bin/bash

# GCP 部署腳本 - Smart Inventory (澳洲地區)
echo "🚀 開始部署 Smart Inventory 到 GCP Kubernetes (澳洲地區)..."

# 檢查 gcloud 是否已安裝並登入
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI 未安裝。請先安裝 Google Cloud SDK"
    exit 1
fi

# 檢查是否已登入
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ 請先登入 Google Cloud: gcloud auth login"
    exit 1
fi

# 設定變數 - 澳洲地區
PROJECT_ID=$(gcloud config get-value project)
CLUSTER_NAME="infs3208-cluster"
ZONE="australia-southeast1-b"
NODE_COUNT=2
MACHINE_TYPE="e2-standard-2"

echo "📋 部署配置："
echo "   Project ID: $PROJECT_ID"
echo "   Cluster Name: $CLUSTER_NAME"
echo "   Zone: $ZONE"
echo "   Node Count: $NODE_COUNT"
echo "   Machine Type: $MACHINE_TYPE"

# 建立 GKE 集群
echo "🏗️ 建立 GKE 集群..."
gcloud container clusters create $CLUSTER_NAME \
    --zone=$ZONE \
    --num-nodes=$NODE_COUNT \
    --machine-type=$MACHINE_TYPE \
    --enable-autoscaling \
    --min-nodes=1 \
    --max-nodes=5 \
    --enable-autorepair \
    --enable-autoupgrade \
    --disk-size=20GB \
    --disk-type=pd-standard

# 獲取集群憑證
echo "🔑 獲取集群憑證..."
gcloud container clusters get-credentials $CLUSTER_NAME --zone=$ZONE

# 建立 namespace
echo "📦 建立 namespace..."
kubectl apply -f namespace.yaml

# 建立 ConfigMap 和 Secret
echo "🔧 建立 ConfigMap 和 Secret..."
kubectl apply -f configmap.yaml

# 建立 MySQL 和 Redis
echo "🗄️ 部署 MySQL 和 Redis..."
kubectl apply -f mysql.yaml
kubectl apply -f redis.yaml

# 等待 MySQL 和 Redis 就緒
echo "⏳ 等待 MySQL 和 Redis 就緒..."
kubectl wait --for=condition=ready pod -l app=mysql -n smart-inventory --timeout=300s
kubectl wait --for=condition=ready pod -l app=redis -n smart-inventory --timeout=300s

# 建立微服務
echo "🚀 部署微服務..."
kubectl apply -f gcp-inventory-service.yaml
kubectl apply -f gcp-order-service.yaml

# 建立 GCP Ingress
echo "🌐 建立 GCP Ingress..."
kubectl apply -f gcp-ingress.yaml

# 建立 HPA
echo "📈 建立 HPA..."
kubectl apply -f hpa.yaml

# 等待 Ingress 就緒
echo "⏳ 等待 Ingress 就緒..."
kubectl wait --for=condition=ready ingress/smart-inventory-ingress -n smart-inventory --timeout=300s

echo "✅ 部署完成！"
echo ""
echo "🔍 檢查 Pod 狀態："
kubectl get pods -n smart-inventory

echo ""
echo "🌐 檢查服務狀態："
kubectl get services -n smart-inventory

echo ""
echo "📊 檢查 HPA 狀態："
kubectl get hpa -n smart-inventory

echo ""
echo "🌍 檢查 Ingress 狀態："
kubectl get ingress -n smart-inventory

echo ""
echo "🌐 獲取外部 IP："
kubectl get ingress smart-inventory-ingress -n smart-inventory -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
echo ""

echo "📝 測試指令："
echo "curl http://\$(kubectl get ingress smart-inventory-ingress -n smart-inventory -o jsonpath='{.status.loadBalancer.ingress[0].ip}')/api/inventory/healthz"
