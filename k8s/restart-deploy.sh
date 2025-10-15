#!/bin/bash

# 重新部署腳本 - Smart Inventory (澳洲地區)
echo "🔄 重新開始部署 Smart Inventory 到 GCP Kubernetes..."

# 檢查當前目錄
echo "📁 當前目錄："
pwd
ls -la

# 檢查專案設定
echo "🔍 檢查專案設定..."
PROJECT_ID=$(gcloud config get-value project)
echo "專案 ID: $PROJECT_ID"

if [ -z "$PROJECT_ID" ]; then
    echo "❌ 未設定專案 ID。請執行: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

# 設定澳洲地區
echo "🌏 設定澳洲地區..."
gcloud config set compute/zone australia-southeast1-b

# 啟用必要的 API
echo "🔧 啟用必要的 API..."
gcloud services enable container.googleapis.com
gcloud services enable containerregistry.googleapis.com

# 配置 Docker 認證
echo "🔑 配置 Docker 認證..."
gcloud auth configure-docker

# 建構並推送映像檔
echo "🐳 建構並推送 Docker 映像檔..."
chmod +x build-and-push-images.sh
./build-and-push-images.sh

# 執行部署
echo "🚀 開始部署..."
chmod +x gcp-deploy-australia.sh
./gcp-deploy-australia.sh

echo "✅ 重新部署完成！"
