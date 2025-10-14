# 🚀 Smart Inventory - Kubernetes 部署檢查清單

## 📋 第三階段完成項目

### ✅ 1. 建立 Deployment & Service YAML
- [x] **MySQL Deployment** - 包含健康檢查和持久化存儲
- [x] **Redis Deployment** - 包含健康檢查
- [x] **Inventory Service Deployment** - 2個副本，包含資源限制
- [x] **Order Service Deployment** - 2個副本，包含資源限制
- [x] **所有服務的 ClusterIP Service** - 內部服務發現

### ✅ 2. Ingress + LoadBalancer
- [x] **Ingress 配置** - 替代 Nginx 反向代理
- [x] **路由規則** - `/api/inventory` → inventory-service, `/api/orders` → order-service
- [x] **健康檢查端點** - `/healthz` 全域健康檢查

### ✅ 3. HPA (Horizontal Pod Autoscaler)
- [x] **Inventory Service HPA** - CPU 50%, Memory 70% 閾值
- [x] **Order Service HPA** - CPU 50%, Memory 70% 閾值
- [x] **擴展範圍** - 最小 2 個副本，最大 10 個副本

### ✅ 4. Liveness/Readiness Probe
- [x] **MySQL Probes** - mysqladmin ping 檢查
- [x] **Redis Probes** - redis-cli ping 檢查
- [x] **微服務 Probes** - HTTP GET `/api/healthz` 檢查
- [x] **適當的延遲和間隔** - 避免啟動時誤報

### ✅ 5. Rolling Update / Rollback 測試
- [x] **Rolling Update 腳本** - `test-rolling-update.sh`
- [x] **Rollback 測試** - `kubectl rollout undo`
- [x] **零停機更新** - 確保服務持續可用

## 🎯 部署步驟

### 前置準備
1. **確保 Kubernetes 集群運行**
   ```bash
   kubectl cluster-info
   kubectl get nodes
   ```

2. **建立 Docker 映像檔**
   ```bash
   # 在專案根目錄
   docker build -t inventory-service:latest ./inventory-service
   docker build -t order-service:latest ./order-service
   ```

3. **載入映像檔到 Kubernetes**
   ```bash
   # 對於 minikube
   minikube image load inventory-service:latest
   minikube image load order-service:latest
   
   # 對於 kind
   kind load docker-image inventory-service:latest
   kind load docker-image order-service:latest
   ```

### 執行部署
```bash
cd k8s
chmod +x *.sh
./deploy.sh
```

### 驗證部署
```bash
./test-k8s.sh
```

### 測試功能
```bash
# 測試 Rolling Update
./test-rolling-update.sh

# 測試 HPA
./test-hpa.sh
```

## 🔍 驗證要點

### 1. 基本功能驗證
- [ ] 所有 Pod 狀態為 `Running`
- [ ] 所有服務正常運行
- [ ] Ingress 可以訪問
- [ ] 健康檢查端點回應正常

### 2. 微服務溝通驗證
- [ ] 庫存服務可以連接 MySQL
- [ ] 訂單服務可以連接 MySQL
- [ ] 訂單服務可以調用庫存服務
- [ ] Redis 快取正常工作

### 3. 自動擴展驗證
- [ ] HPA 監控 CPU 和 Memory
- [ ] 負載增加時 Pod 自動擴展
- [ ] 負載減少時 Pod 自動縮減

### 4. 零停機更新驗證
- [ ] Rolling Update 過程中服務不中斷
- [ ] 回滾功能正常工作
- [ ] 更新過程中健康檢查正常

## 🛠️ 故障排除

### 常見問題
1. **Pod 無法啟動** - 檢查映像檔是否載入
2. **服務無法連接** - 檢查 Service 和 Ingress 配置
3. **HPA 不工作** - 檢查 metrics-server 是否安裝
4. **健康檢查失敗** - 檢查 Probe 配置和應用程式端點

### 調試命令
```bash
# 檢查 Pod 詳細資訊
kubectl describe pod <pod-name> -n smart-inventory

# 查看 Pod 日誌
kubectl logs <pod-name> -n smart-inventory

# 檢查服務端點
kubectl get endpoints -n smart-inventory

# 檢查 HPA 詳細資訊
kubectl describe hpa <hpa-name> -n smart-inventory
```

## 📊 監控指標

### 關鍵指標
- **Pod 數量** - 確保 HPA 正常工作
- **CPU 使用率** - 監控自動擴展觸發
- **Memory 使用率** - 監控資源使用
- **健康檢查狀態** - 確保服務可用性

### 監控命令
```bash
# 實時監控 Pod
kubectl get pods -n smart-inventory -w

# 監控 HPA
kubectl get hpa -n smart-inventory -w

# 查看資源使用
kubectl top pods -n smart-inventory
```

## 🎉 完成標準

當您能夠成功執行以下操作時，第三階段就完成了：

1. ✅ **一鍵部署** - `./deploy.sh` 成功部署所有組件
2. ✅ **服務訪問** - 通過 Ingress 訪問所有 API 端點
3. ✅ **自動擴展** - HPA 根據負載自動調整 Pod 數量
4. ✅ **零停機更新** - Rolling Update 和 Rollback 正常工作
5. ✅ **健康檢查** - 所有 Liveness 和 Readiness Probes 正常

恭喜！您已經完成了 Smart Inventory 的 Kubernetes 編排階段！🎊
