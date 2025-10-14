#!/bin/bash

# HPA 測試腳本
echo "📈 開始 HPA 測試..."

# 檢查 HPA 狀態
echo "📊 檢查 HPA 狀態..."
kubectl get hpa -n smart-inventory

# 檢查當前 Pod 數量
echo "🔍 檢查當前 Pod 數量..."
kubectl get pods -n smart-inventory -l app=inventory-service
kubectl get pods -n smart-inventory -l app=order-service

# 檢查資源使用情況
echo "💻 檢查資源使用情況..."
kubectl top pods -n smart-inventory

# 產生負載測試 (需要安裝 hey 工具)
echo "🚀 開始負載測試..."

# 獲取 Ingress 地址
INGRESS_IP=$(kubectl get ingress smart-inventory-ingress -n smart-inventory -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
if [ -z "$INGRESS_IP" ]; then
    INGRESS_IP="localhost"
fi

echo "🌐 使用 Ingress IP: $INGRESS_IP"

# 檢查是否有 hey 工具
if command -v hey &> /dev/null; then
    echo "📊 使用 hey 工具進行負載測試..."
    hey -n 1000 -c 10 -m GET http://$INGRESS_IP/api/inventory/healthz &
    HEY_PID=$!
    
    # 監控 HPA 變化
    echo "👀 監控 HPA 變化 (30秒)..."
    timeout 30s kubectl get hpa -n smart-inventory -w &
    HPA_PID=$!
    
    # 等待負載測試完成
    wait $HEY_PID
    
    # 停止 HPA 監控
    kill $HPA_PID 2>/dev/null
else
    echo "⚠️ 未安裝 hey 工具，使用 curl 進行簡單測試..."
    for i in {1..50}; do
        curl -s http://$INGRESS_IP/api/inventory/healthz > /dev/null &
    done
    wait
fi

# 等待 HPA 響應
echo "⏳ 等待 HPA 響應 (30秒)..."
sleep 30

# 檢查 HPA 狀態
echo "📊 檢查 HPA 狀態..."
kubectl get hpa -n smart-inventory

# 檢查 Pod 數量變化
echo "🔍 檢查 Pod 數量變化..."
kubectl get pods -n smart-inventory -l app=inventory-service
kubectl get pods -n smart-inventory -l app=order-service

# 檢查資源使用情況
echo "💻 檢查資源使用情況..."
kubectl top pods -n smart-inventory

# 檢查 HPA 事件
echo "📝 檢查 HPA 事件..."
kubectl describe hpa inventory-service-hpa -n smart-inventory | grep -A 10 "Events:"
kubectl describe hpa order-service-hpa -n smart-inventory | grep -A 10 "Events:"

echo "✅ HPA 測試完成！"
