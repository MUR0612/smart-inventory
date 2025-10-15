#!/bin/bash

# Google Cloud Shell 部署腳本 - Smart Inventory
echo "🚀 在 Google Cloud Shell 中部署 Smart Inventory..."

# 檢查是否在 Cloud Shell 中
if [ -z "$CLOUD_SHELL" ]; then
    echo "⚠️  警告：這不是 Google Cloud Shell 環境"
fi

# 設定變數
PROJECT_ID=$(gcloud config get-value project)
CLUSTER_NAME="infs3208-cluster-$(date +%s)"
ZONE="asia-east1-a"
NODE_COUNT=2
MACHINE_TYPE="e2-standard-2"

echo "📋 部署配置："
echo "   Project ID: $PROJECT_ID"
echo "   Cluster Name: $CLUSTER_NAME"
echo "   Zone: $ZONE"
echo "   Node Count: $NODE_COUNT"
echo "   Machine Type: $MACHINE_TYPE"

# 啟用必要的 API
echo "🔧 啟用必要的 API..."
gcloud services enable container.googleapis.com
gcloud services enable containerregistry.googleapis.com

# 建構並推送 Docker 映像檔
echo "🐳 建構並推送 Docker 映像檔..."
cd k8s
chmod +x build-and-push-images.sh
./build-and-push-images.sh

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

# 部署應用程式
echo "🚀 部署應用程式..."
chmod +x gcp-deploy.sh
./gcp-deploy.sh

echo "✅ 部署完成！"
echo ""
echo "🌐 獲取外部 IP："
kubectl get ingress smart-inventory-ingress -n smart-inventory -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
echo ""

echo "📝 測試指令："
echo "curl http://\$(kubectl get ingress smart-inventory-ingress -n smart-inventory -o jsonpath='{.status.loadBalancer.ingress[0].ip}')/api/inventory/healthz"
echo "curl http://\$(kubectl get ingress smart-inventory-ingress -n smart-inventory -o jsonpath='{.status.loadBalancer.ingress[0].ip}')/api/orders/healthz"
