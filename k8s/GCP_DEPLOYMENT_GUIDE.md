# Smart Inventory - GCP 部署指南

## 📋 概述

本指南將協助您將 Smart Inventory 系統部署到 Google Cloud Platform (GCP) 的 Kubernetes Engine (GKE) 上。

## 🎯 第四階段目標

- ✅ 在 GCP 建立 K8s cluster (2 nodes e2-standard-2)
- ✅ 部署 YAML 並驗證外部存取
- ✅ 模擬負載驗證 HPA scaling
- ✅ 關閉 cluster 減少 credit 消耗

## 🏗️ 架構組件

### GCP 資源
- **GKE Cluster**: 2 nodes e2-standard-2
- **Container Registry**: 存放 Docker 映像檔
- **Load Balancer**: 外部訪問入口
- **Static IP**: 固定外部 IP

### Kubernetes 資源
- **Namespace**: `smart-inventory`
- **Deployments**: inventory-service, order-service
- **Services**: ClusterIP 服務
- **Ingress**: GCP Load Balancer
- **HPA**: 水平自動擴展

## 🚀 部署步驟

### 前置需求

1. **安裝 Google Cloud SDK**
   ```bash
   # Windows (使用 PowerShell)
   (New-Object Net.WebClient).DownloadFile("https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe", "$env:Temp\GoogleCloudSDKInstaller.exe")
   & "$env:Temp\GoogleCloudSDKInstaller.exe"
   ```

2. **初始化 gcloud**
   ```bash
   gcloud init
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```

3. **安裝必要工具**
   ```bash
   # 安裝 kubectl
   gcloud components install kubectl
   
   # 安裝 hey (負載測試工具)
   go install github.com/rakyll/hey@latest
   ```

### 部署流程

#### 1. 建構並推送 Docker 映像檔
```bash
cd k8s
chmod +x build-and-push-images.sh
./build-and-push-images.sh
```

#### 2. 部署到 GCP
```bash
chmod +x gcp-deploy.sh
./gcp-deploy.sh
```

#### 3. 驗證部署
```bash
# 檢查 Pod 狀態
kubectl get pods -n smart-inventory

# 檢查服務狀態
kubectl get services -n smart-inventory

# 檢查 Ingress 狀態
kubectl get ingress -n smart-inventory

# 獲取外部 IP
kubectl get ingress smart-inventory-ingress -n smart-inventory -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
```

#### 4. 測試 API
```bash
# 獲取外部 IP
EXTERNAL_IP=$(kubectl get ingress smart-inventory-ingress -n smart-inventory -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# 測試健康檢查
curl http://$EXTERNAL_IP/api/inventory/healthz
curl http://$EXTERNAL_IP/api/orders/healthz
```

## 🧪 負載測試

### 執行負載測試
```bash
chmod +x load-test.sh
./load-test.sh
```

### 監控 HPA
```bash
# 監控 HPA 狀態
kubectl get hpa -n smart-inventory -w

# 監控 Pod 擴展
kubectl get pods -n smart-inventory -w

# 查看資源使用情況
kubectl top pods -n smart-inventory
```

## 💰 成本控制

### 預估成本
- **GKE Cluster**: ~$0.10/小時 (2 nodes e2-standard-2)
- **Load Balancer**: ~$0.025/小時
- **Static IP**: ~$0.004/小時 (未使用時)
- **Container Registry**: 免費 (小於 500MB)

### 成本控制策略
1. **自動關閉**: 設定排程任務自動關閉集群
2. **監控使用量**: 使用 GCP Console 監控資源使用
3. **及時清理**: 測試完成後立即清理資源

### 清理資源
```bash
chmod +x gcp-cleanup.sh
./gcp-cleanup.sh
```

## 🔍 故障排除

### 常見問題

1. **映像檔拉取失敗**
   ```bash
   # 檢查映像檔是否存在
   gcloud container images list --repository=gcr.io/PROJECT_ID
   
   # 重新推送映像檔
   ./build-and-push-images.sh
   ```

2. **Ingress 無法獲取外部 IP**
   ```bash
   # 檢查 Ingress 狀態
   kubectl describe ingress smart-inventory-ingress -n smart-inventory
   
   # 檢查 Load Balancer 服務
   kubectl get services -n smart-inventory
   ```

3. **HPA 不工作**
   ```bash
   # 檢查 Metrics Server
   kubectl get deployment metrics-server -n kube-system
   
   # 安裝 Metrics Server
   kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
   ```

### 監控和日誌

```bash
# 查看 Pod 日誌
kubectl logs -f deployment/inventory-service -n smart-inventory
kubectl logs -f deployment/order-service -n smart-inventory

# 查看事件
kubectl get events -n smart-inventory --sort-by='.lastTimestamp'

# 查看資源使用情況
kubectl top nodes
kubectl top pods -n smart-inventory
```

## 📊 性能測試結果

### 預期結果
- **響應時間**: < 200ms (正常負載)
- **並發處理**: 100+ 並發請求
- **自動擴展**: CPU > 50% 時自動擴展
- **零停機更新**: Rolling update 成功

### 測試指令
```bash
# 基本功能測試
curl http://$EXTERNAL_IP/api/inventory/healthz
curl http://$EXTERNAL_IP/api/orders/healthz

# 負載測試
hey -n 1000 -c 10 http://$EXTERNAL_IP/api/inventory/healthz

# 監控擴展
kubectl get hpa -n smart-inventory -w
```

## 🎓 學習成果

完成此階段後，您將掌握：

1. **GCP 服務使用**: GKE, Container Registry, Load Balancer
2. **Kubernetes 部署**: 生產環境部署最佳實踐
3. **自動擴展**: HPA 配置和監控
4. **成本控制**: 雲端資源管理和優化
5. **負載測試**: 性能測試和監控

## 📝 注意事項

1. **專案 ID**: 請將所有 `PROJECT_ID` 替換為您的實際專案 ID
2. **區域設定**: 預設使用 `asia-east1-a`，可根據需要調整
3. **資源限制**: 確保 GCP 配額足夠
4. **安全設定**: 生產環境請加強安全配置
5. **備份策略**: 重要資料請設定備份

## 🔗 相關資源

- [GKE 官方文檔](https://cloud.google.com/kubernetes-engine/docs)
- [Kubernetes 官方文檔](https://kubernetes.io/docs/)
- [GCP 定價計算器](https://cloud.google.com/products/calculator)
- [hey 負載測試工具](https://github.com/rakyll/hey)
