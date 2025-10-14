#!/bin/bash

# 負載測試腳本 - Smart Inventory
echo "🚀 開始負載測試 Smart Inventory..."

# 設定變數
NAMESPACE="smart-inventory"
INGRESS_NAME="smart-inventory-ingress"
TEST_DURATION="300s"  # 5分鐘
CONCURRENT_USERS=10
REQUESTS_PER_SECOND=50

# 檢查必要的工具
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl 未安裝"
    exit 1
fi

# 獲取外部 IP
echo "🌐 獲取外部 IP..."
EXTERNAL_IP=$(kubectl get ingress $INGRESS_NAME -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

if [ -z "$EXTERNAL_IP" ]; then
    echo "❌ 無法獲取外部 IP，請檢查 Ingress 狀態"
    kubectl get ingress $INGRESS_NAME -n $NAMESPACE
    exit 1
fi

echo "📍 外部 IP: $EXTERNAL_IP"

# 測試基本連通性
echo "🔍 測試基本連通性..."
if curl -s --max-time 10 "http://$EXTERNAL_IP/api/inventory/healthz" > /dev/null; then
    echo "✅ 基本連通性測試通過"
else
    echo "❌ 基本連通性測試失敗"
    exit 1
fi

# 檢查 HPA 狀態
echo "📊 檢查 HPA 狀態..."
kubectl get hpa -n $NAMESPACE

# 開始負載測試
echo "🚀 開始負載測試..."
echo "   持續時間: $TEST_DURATION"
echo "   並發用戶: $CONCURRENT_USERS"
echo "   目標 RPS: $REQUESTS_PER_SECOND"

# 使用 hey 工具進行負載測試 (如果可用)
if command -v hey &> /dev/null; then
    echo "📈 使用 hey 進行負載測試..."
    hey -n 10000 -c $CONCURRENT_USERS -q $REQUESTS_PER_SECOND -z $TEST_DURATION \
        "http://$EXTERNAL_IP/api/inventory/healthz" &
    
    # 監控 HPA 和 Pod 狀態
    echo "📊 監控 HPA 和 Pod 狀態..."
    echo "按 Ctrl+C 停止監控"
    
    while true; do
        echo "=== $(date) ==="
        echo "HPA 狀態:"
        kubectl get hpa -n $NAMESPACE
        echo ""
        echo "Pod 狀態:"
        kubectl get pods -n $NAMESPACE
        echo ""
        echo "Pod 資源使用:"
        kubectl top pods -n $NAMESPACE 2>/dev/null || echo "Metrics server 未安裝"
        echo ""
        sleep 30
    done
else
    echo "⚠️  hey 工具未安裝，使用 curl 進行簡單測試..."
    echo "安裝 hey: go install github.com/rakyll/hey@latest"
    
    # 使用 curl 進行簡單的並發測試
    for i in {1..100}; do
        curl -s "http://$EXTERNAL_IP/api/inventory/healthz" &
        if [ $((i % 10)) -eq 0 ]; then
            echo "已發送 $i 個請求"
            sleep 1
        fi
    done
    wait
fi

echo "✅ 負載測試完成！"