#!/bin/bash

# GCP 清理腳本 - Smart Inventory
echo "🧹 開始清理 Smart Inventory GCP 資源..."

# 設定變數
CLUSTER_NAME="smart-inventory-cluster"
ZONE="asia-east1-a"

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

echo "⚠️  這將刪除以下資源："
echo "   - GKE 集群: $CLUSTER_NAME"
echo "   - 所有相關的 Pod、Service、Ingress"
echo "   - 靜態 IP (如果存在)"
echo ""

read -p "確定要繼續嗎？(y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ 取消清理操作"
    exit 1
fi

# 刪除 Kubernetes 資源
echo "🗑️ 刪除 Kubernetes 資源..."
kubectl delete namespace smart-inventory --ignore-not-found=true

# 刪除 GKE 集群
echo "🗑️ 刪除 GKE 集群..."
gcloud container clusters delete $CLUSTER_NAME --zone=$ZONE --quiet

# 刪除靜態 IP (如果存在)
echo "🗑️ 檢查並刪除靜態 IP..."
STATIC_IP_NAME="smart-inventory-ip"
if gcloud compute addresses describe $STATIC_IP_NAME --global --quiet 2>/dev/null; then
    gcloud compute addresses delete $STATIC_IP_NAME --global --quiet
    echo "✅ 已刪除靜態 IP: $STATIC_IP_NAME"
else
    echo "ℹ️  未找到靜態 IP: $STATIC_IP_NAME"
fi

echo "✅ 清理完成！"
echo ""
echo "💰 成本控制提醒："
echo "   - GKE 集群已刪除，不再產生計算費用"
echo "   - 靜態 IP 已釋放，不再產生網路費用"
echo "   - 請檢查 GCP Console 確認所有資源已清理"