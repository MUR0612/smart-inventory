#!/bin/bash

# Rolling Update 測試腳本
echo "🔄 開始 Rolling Update 測試..."

# 檢查當前部署狀態
echo "📊 檢查當前部署狀態..."
kubectl get deployments -n smart-inventory

# 檢查當前映像檔版本
echo "🐳 檢查當前映像檔版本..."
kubectl get deployment inventory-service -n smart-inventory -o jsonpath='{.spec.template.spec.containers[0].image}'
echo ""

# 模擬更新映像檔 (假設有新版本)
echo "🚀 執行 Rolling Update..."
kubectl set image deployment/inventory-service inventory-service=inventory-service:v2 -n smart-inventory

# 監控更新過程
echo "👀 監控更新過程..."
kubectl rollout status deployment/inventory-service -n smart-inventory --timeout=300s

# 檢查更新後的狀態
echo "📊 檢查更新後狀態..."
kubectl get deployments -n smart-inventory
kubectl get pods -n smart-inventory -l app=inventory-service

# 測試服務是否正常
echo "🧪 測試服務是否正常..."
kubectl get services -n smart-inventory
kubectl get ingress -n smart-inventory

# 等待一下讓服務穩定
sleep 10

# 測試健康檢查
INGRESS_IP=$(kubectl get ingress smart-inventory-ingress -n smart-inventory -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
if [ -z "$INGRESS_IP" ]; then
    INGRESS_IP="localhost"
fi

echo "🏥 測試更新後的健康檢查..."
curl -f http://$INGRESS_IP/api/inventory/healthz && echo "✅ 服務正常" || echo "❌ 服務異常"

# 回滾測試
echo "🔄 執行回滾測試..."
kubectl rollout undo deployment/inventory-service -n smart-inventory

# 監控回滾過程
echo "👀 監控回滾過程..."
kubectl rollout status deployment/inventory-service -n smart-inventory --timeout=300s

# 檢查回滾後狀態
echo "📊 檢查回滾後狀態..."
kubectl get deployments -n smart-inventory
kubectl get pods -n smart-inventory -l app=inventory-service

# 測試回滾後服務
echo "🏥 測試回滾後服務..."
curl -f http://$INGRESS_IP/api/inventory/healthz && echo "✅ 回滾成功，服務正常" || echo "❌ 回滾後服務異常"

echo "✅ Rolling Update 測試完成！"
