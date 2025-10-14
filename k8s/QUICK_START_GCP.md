# Smart Inventory - GCP 快速開始指南

## 🚀 快速部署到 GCP

### 前置需求檢查

1. **安裝 Google Cloud SDK**
   ```powershell
   # 下載並安裝 Google Cloud SDK
   (New-Object Net.WebClient).DownloadFile("https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe", "$env:Temp\GoogleCloudSDKInstaller.exe")
   & "$env:Temp\GoogleCloudSDKInstaller.exe"
   ```

2. **初始化 gcloud**
   ```powershell
   gcloud init
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```

3. **安裝必要工具**
   ```powershell
   # 安裝 kubectl
   gcloud components install kubectl
   
   # 安裝 hey (負載測試工具)
   go install github.com/rakyll/hey@latest
   ```

### 一鍵部署

```powershell
# 1. 建構並推送 Docker 映像檔
.\build-and-push-images.sh

# 2. 部署到 GCP
.\gcp-deploy.ps1

# 3. 測試 API
$EXTERNAL_IP = kubectl get ingress smart-inventory-ingress -n smart-inventory -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
curl http://$EXTERNAL_IP/api/inventory/healthz
```

### 負載測試

```powershell
# 執行負載測試
.\load-test.ps1

# 監控 HPA
kubectl get hpa -n smart-inventory -w
```

### 成本監控

```powershell
# 檢查成本
.\cost-monitor.ps1
```

### 清理資源

```powershell
# 清理所有資源
.\gcp-cleanup.ps1
```

## 📋 部署檢查清單

- [ ] Google Cloud SDK 已安裝
- [ ] 已登入 Google Cloud
- [ ] 專案 ID 已設定
- [ ] Docker 映像檔已推送到 GCR
- [ ] GKE 集群已建立
- [ ] 應用程式已部署
- [ ] Ingress 已配置
- [ ] 外部 IP 可訪問
- [ ] API 端點正常響應
- [ ] HPA 正常工作
- [ ] 負載測試通過

## 🔧 故障排除

### 常見問題

1. **映像檔拉取失敗**
   ```powershell
   # 重新推送映像檔
   .\build-and-push-images.sh
   ```

2. **Ingress 無法獲取外部 IP**
   ```powershell
   # 檢查 Ingress 狀態
   kubectl describe ingress smart-inventory-ingress -n smart-inventory
   ```

3. **HPA 不工作**
   ```powershell
   # 安裝 Metrics Server
   kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
   ```

## 📊 預期結果

- **響應時間**: < 200ms
- **並發處理**: 100+ 並發請求
- **自動擴展**: CPU > 50% 時自動擴展
- **零停機更新**: Rolling update 成功

## 💰 成本估算

- **GKE 集群**: ~$0.10/小時
- **Load Balancer**: ~$0.025/小時
- **靜態 IP**: ~$0.004/小時
- **總計**: ~$0.13/小時

## 🎯 學習目標

完成此階段後，您將掌握：

1. **GCP 服務使用**: GKE, Container Registry, Load Balancer
2. **Kubernetes 部署**: 生產環境部署最佳實踐
3. **自動擴展**: HPA 配置和監控
4. **成本控制**: 雲端資源管理和優化
5. **負載測試**: 性能測試和監控
