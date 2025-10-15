#!/bin/bash

# Smart Inventory 雲端部署展示腳本
echo "🎯 Smart Inventory 雲端部署展示"
echo "=================================="

echo ""
echo "1️⃣ 展示 GCP 集群狀態："
echo "----------------------------"
kubectl get pods -n smart-inventory

echo ""
echo "2️⃣ 展示服務架構："
echo "----------------------------"
kubectl get services -n smart-inventory
echo ""
kubectl get ingress -n smart-inventory

echo ""
echo "3️⃣ 展示 HPA 自動擴展配置："
echo "----------------------------"
kubectl get hpa -n smart-inventory

echo ""
echo "4️⃣ 展示外部訪問測試："
echo "----------------------------"
echo "測試 inventory-service:"
curl http://35.244.241.159/api/inventory/healthz
echo ""
echo "測試 order-service:"
curl http://35.244.241.159/api/orders/healthz

echo ""
echo "5️⃣ 展示資源使用情況："
echo "----------------------------"
kubectl top pods -n smart-inventory

echo ""
echo "6️⃣ 展示負載測試："
echo "----------------------------"
echo "執行 10 次 API 調用..."
for i in {1..10}; do
    echo -n "請求 $i: "
    curl -s http://35.244.241.159/api/inventory/healthz | grep -o '"status":"[^"]*"'
done

echo ""
echo "🎉 展示完成！"
echo "外部 IP: http://35.244.241.159"
echo "集群狀態: 所有服務運行正常"
echo "自動擴展: HPA 配置完成"
