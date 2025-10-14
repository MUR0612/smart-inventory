#!/bin/bash

# 部署 Smart Inventory 到 Kubernetes
echo "🚀 開始部署 Smart Inventory 到 Kubernetes..."

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
kubectl apply -f inventory-service.yaml
kubectl apply -f order-service.yaml

# 建立 Ingress
echo "🌐 建立 Ingress..."
kubectl apply -f ingress.yaml

# 建立 HPA
echo "📈 建立 HPA..."
kubectl apply -f hpa.yaml

echo "✅ 部署完成！"
echo "🔍 檢查 Pod 狀態："
kubectl get pods -n smart-inventory

echo "🌐 檢查服務狀態："
kubectl get services -n smart-inventory

echo "📊 檢查 HPA 狀態："
kubectl get hpa -n smart-inventory
