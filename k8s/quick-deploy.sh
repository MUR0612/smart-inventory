#!/bin/bash

# 快速部署腳本 - 適用於 Google Cloud Shell
echo "🚀 快速部署 Smart Inventory 到 GCP..."

# 設定變數
PROJECT_ID=$(gcloud config get-value project)
CLUSTER_NAME="infs3208-cluster"
ZONE="asia-east1-a"

echo "📋 專案 ID: $PROJECT_ID"
echo "📋 集群名稱: $CLUSTER_NAME"

# 啟用 API
echo "🔧 啟用必要的 API..."
gcloud services enable container.googleapis.com
gcloud services enable containerregistry.googleapis.com

# 配置 Docker 認證
echo "🔑 配置 Docker 認證..."
gcloud auth configure-docker

# 建構並推送映像檔
echo "🐳 建構並推送 Docker 映像檔..."

# 建構 inventory-service
echo "📦 建構 inventory-service..."
cd ../inventory-service
docker build -t gcr.io/$PROJECT_ID/inventory-service:latest .
docker push gcr.io/$PROJECT_ID/inventory-service:latest

# 建構 order-service
echo "📦 建構 order-service..."
cd ../order-service
docker build -t gcr.io/$PROJECT_ID/order-service:latest .
docker push gcr.io/$PROJECT_ID/order-service:latest

# 回到 k8s 目錄
cd ../k8s

# 更新 YAML 文件中的專案 ID
echo "📝 更新 Kubernetes 配置文件..."
sed -i "s/PROJECT_ID/$PROJECT_ID/g" gcp-inventory-service.yaml
sed -i "s/PROJECT_ID/$PROJECT_ID/g" gcp-order-service.yaml

# 建立 GKE 集群
echo "🏗️ 建立 GKE 集群..."
gcloud container clusters create $CLUSTER_NAME \
    --zone=$ZONE \
    --num-nodes=2 \
    --machine-type=e2-standard-2 \
    --enable-autoscaling \
    --min-nodes=1 \
    --max-nodes=5

# 獲取集群憑證
echo "🔑 獲取集群憑證..."
gcloud container clusters get-credentials $CLUSTER_NAME --zone=$ZONE

# 部署應用程式
echo "🚀 部署應用程式..."

# 建立 namespace
kubectl apply -f namespace.yaml

# 建立 ConfigMap
kubectl apply -f configmap.yaml

# 部署 MySQL 和 Redis
kubectl apply -f mysql.yaml
kubectl apply -f redis.yaml

# 等待資料庫就緒
echo "⏳ 等待資料庫就緒..."
kubectl wait --for=condition=ready pod -l app=mysql -n smart-inventory --timeout=300s
kubectl wait --for=condition=ready pod -l app=redis -n smart-inventory --timeout=300s

# 部署微服務
kubectl apply -f gcp-inventory-service.yaml
kubectl apply -f gcp-order-service.yaml

# 建立 Ingress
kubectl apply -f gcp-ingress.yaml

# 建立 HPA
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
echo "🌐 外部 IP："
EXTERNAL_IP=$(kubectl get ingress smart-inventory-ingress -n smart-inventory -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "http://$EXTERNAL_IP"

echo ""
echo "📝 測試指令："
echo "curl http://$EXTERNAL_IP/api/inventory/healthz"
echo "curl http://$EXTERNAL_IP/api/orders/healthz"
