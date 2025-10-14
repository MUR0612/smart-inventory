#!/bin/bash

# Kubernetes 部署測試腳本
echo "🧪 開始測試 Kubernetes 部署..."

# 檢查 namespace
echo "📦 檢查 namespace..."
kubectl get namespace smart-inventory

# 檢查所有 Pod 狀態
echo "🔍 檢查 Pod 狀態..."
kubectl get pods -n smart-inventory

# 檢查服務狀態
echo "🌐 檢查服務狀態..."
kubectl get services -n smart-inventory

# 檢查 HPA 狀態
echo "📈 檢查 HPA 狀態..."
kubectl get hpa -n smart-inventory

# 檢查 Ingress 狀態
echo "🚪 檢查 Ingress 狀態..."
kubectl get ingress -n smart-inventory

# 等待所有 Pod 就緒
echo "⏳ 等待所有 Pod 就緒..."
kubectl wait --for=condition=ready pod -l app=mysql -n smart-inventory --timeout=300s
kubectl wait --for=condition=ready pod -l app=redis -n smart-inventory --timeout=300s
kubectl wait --for=condition=ready pod -l app=inventory-service -n smart-inventory --timeout=300s
kubectl wait --for=condition=ready pod -l app=order-service -n smart-inventory --timeout=300s

# 測試健康檢查端點
echo "🏥 測試健康檢查端點..."

# 獲取 Ingress 地址
INGRESS_IP=$(kubectl get ingress smart-inventory-ingress -n smart-inventory -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
if [ -z "$INGRESS_IP" ]; then
    INGRESS_IP="localhost"
fi

echo "🌐 Ingress IP: $INGRESS_IP"

# 測試庫存服務健康檢查
echo "📦 測試庫存服務健康檢查..."
curl -f http://$INGRESS_IP/api/inventory/healthz || echo "❌ 庫存服務健康檢查失敗"

# 測試訂單服務健康檢查
echo "📋 測試訂單服務健康檢查..."
curl -f http://$INGRESS_IP/api/orders/healthz || echo "❌ 訂單服務健康檢查失敗"

# 測試全域健康檢查
echo "🌍 測試全域健康檢查..."
curl -f http://$INGRESS_IP/healthz || echo "❌ 全域健康檢查失敗"

echo "✅ 測試完成！"
