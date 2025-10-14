# Smart Inventory - Kubernetes 部署指南

## 📋 概述

這個目錄包含了將 Smart Inventory 系統部署到 Kubernetes 集群所需的所有配置文件。

## 🏗️ 架構組件

### 核心服務
- **MySQL**: 資料庫服務
- **Redis**: 快取服務
- **Inventory Service**: 庫存管理微服務
- **Order Service**: 訂單管理微服務

### Kubernetes 資源
- **Namespace**: `smart-inventory`
- **Deployments**: 每個服務的部署配置
- **Services**: 內部服務發現
- **Ingress**: 外部訪問入口
- **HPA**: 水平自動擴展
- **ConfigMaps & Secrets**: 配置管理

## 🚀 快速部署

### 前置需求
1. Kubernetes 集群 (minikube, kind, 或雲端集群)
2. kubectl 命令行工具
3. Docker 映像檔已建立

### 部署步驟

1. **建立 Docker 映像檔** (如果尚未建立):
```bash
# 在專案根目錄
docker build -t inventory-service:latest ./inventory-service
docker build -t order-service:latest ./order-service
```

2. **載入映像檔到 Kubernetes** (如果是本地集群):
```bash
# 對於 minikube
minikube image load inventory-service:latest
minikube image load order-service:latest

# 對於 kind
kind load docker-image inventory-service:latest
kind load docker-image order-service:latest
```

3. **執行部署腳本**:
```bash
chmod +x deploy.sh
./deploy.sh
```

4. **手動部署** (可選):
```bash
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
kubectl apply -f mysql.yaml
kubectl apply -f redis.yaml
kubectl apply -f inventory-service.yaml
kubectl apply -f order-service.yaml
kubectl apply -f ingress.yaml
kubectl apply -f hpa.yaml
```

## 🔍 驗證部署

### 檢查 Pod 狀態
```bash
kubectl get pods -n smart-inventory
```

### 檢查服務狀態
```bash
kubectl get services -n smart-inventory
```

### 檢查 HPA 狀態
```bash
kubectl get hpa -n smart-inventory
```

### 檢查 Ingress
```bash
kubectl get ingress -n smart-inventory
```

## 🧪 測試功能

### 1. Rolling Update 測試
```bash
# 更新映像檔
kubectl set image deployment/inventory-service inventory-service=inventory-service:v2 -n smart-inventory

# 監控更新過程
kubectl rollout status deployment/inventory-service -n smart-inventory

# 回滾
kubectl rollout undo deployment/inventory-service -n smart-inventory
```

### 2. 自動擴展測試
```bash
# 產生負載 (需要安裝 hey 工具)
hey -n 1000 -c 10 http://localhost/api/inventory/healthz

# 監控 HPA
kubectl get hpa -n smart-inventory -w
```

### 3. 健康檢查測試
```bash
# 檢查 Pod 健康狀態
kubectl describe pod <pod-name> -n smart-inventory

# 檢查服務端點
kubectl get endpoints -n smart-inventory
```

## 🛠️ 故障排除

### 常見問題

1. **Pod 無法啟動**
   ```bash
   kubectl describe pod <pod-name> -n smart-inventory
   kubectl logs <pod-name> -n smart-inventory
   ```

2. **服務無法連接**
   ```bash
   kubectl get services -n smart-inventory
   kubectl describe service <service-name> -n smart-inventory
   ```

3. **HPA 不工作**
   ```bash
   kubectl describe hpa <hpa-name> -n smart-inventory
   kubectl top pods -n smart-inventory
   ```

### 清理資源
```bash
kubectl delete namespace smart-inventory
```

## 📊 監控和日誌

### 查看日誌
```bash
# 查看特定服務日誌
kubectl logs -f deployment/inventory-service -n smart-inventory
kubectl logs -f deployment/order-service -n smart-inventory

# 查看所有 Pod 日誌
kubectl logs -f -l app=inventory-service -n smart-inventory
```

### 資源使用情況
```bash
kubectl top pods -n smart-inventory
kubectl top nodes
```

## 🔧 配置說明

### 環境變數
- `DB_URL`: 資料庫連接字串
- `REDIS_HOST`: Redis 主機地址
- `REDIS_PORT`: Redis 端口
- `INVENTORY_BASE_URL`: 庫存服務 URL

### 資源限制
- **CPU**: 100m-200m
- **Memory**: 128Mi-256Mi
- **Storage**: 1Gi (MySQL)

### 健康檢查
- **Liveness Probe**: 30秒後開始，每10秒檢查
- **Readiness Probe**: 5秒後開始，每5秒檢查
