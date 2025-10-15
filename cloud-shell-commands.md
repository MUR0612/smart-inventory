# Google Cloud Shell 部署命令

## 第一步：檢查項目結構
```bash
cd k8s
ls -la
```

## 第二步：檢查當前專案設定
```bash
gcloud config get-value project
```

## 第三步：如果沒有設定專案，請設定
```bash
# 替換 YOUR_PROJECT_ID 為你的實際專案 ID
gcloud config set project YOUR_PROJECT_ID
```

## 第四步：啟用必要的 API
```bash
gcloud services enable container.googleapis.com
gcloud services enable containerregistry.googleapis.com
```

## 第五步：配置 Docker 認證
```bash
gcloud auth configure-docker
```

## 第六步：建構並推送 Docker 映像檔
```bash
# 建構 inventory-service
cd ../inventory-service
docker build -t gcr.io/$(gcloud config get-value project)/inventory-service:latest .
docker push gcr.io/$(gcloud config get-value project)/inventory-service:latest

# 建構 order-service
cd ../order-service
docker build -t gcr.io/$(gcloud config get-value project)/order-service:latest .
docker push gcr.io/$(gcloud config get-value project)/order-service:latest

# 回到 k8s 目錄
cd ../k8s
```

## 第七步：更新 Kubernetes 配置文件
```bash
# 更新 YAML 文件中的專案 ID
PROJECT_ID=$(gcloud config get-value project)
sed -i "s/PROJECT_ID/$PROJECT_ID/g" gcp-inventory-service.yaml
sed -i "s/PROJECT_ID/$PROJECT_ID/g" gcp-order-service.yaml
```

## 第八步：建立 GKE 集群
```bash
gcloud container clusters create infs3208-cluster \
    --zone=asia-east1-a \
    --num-nodes=2 \
    --machine-type=e2-standard-2 \
    --enable-autoscaling \
    --min-nodes=1 \
    --max-nodes=5 \
    --enable-autorepair \
    --enable-autoupgrade \
    --disk-size=20GB \
    --disk-type=pd-standard
```

## 第九步：獲取集群憑證
```bash
gcloud container clusters get-credentials infs3208-cluster --zone=asia-east1-a
```

## 第十步：部署應用程式
```bash
# 建立 namespace
kubectl apply -f namespace.yaml

# 建立 ConfigMap
kubectl apply -f configmap.yaml

# 部署 MySQL 和 Redis
kubectl apply -f mysql.yaml
kubectl apply -f redis.yaml

# 等待資料庫就緒
echo "⏳ 等待資料庫就緒..."
kubectl wait --for=condition=ready pod -l app=mysql -n smart-inventory --timeout=300s
kubectl wait --for=condition=ready pod -l app=redis -n smart-inventory --timeout=300s

# 部署微服務
kubectl apply -f gcp-inventory-service.yaml
kubectl apply -f gcp-order-service.yaml

# 建立 Ingress
kubectl apply -f gcp-ingress.yaml

# 建立 HPA
kubectl apply -f hpa.yaml
```

## 第十一步：檢查部署狀態
```bash
# 檢查 Pod 狀態
kubectl get pods -n smart-inventory

# 檢查服務狀態
kubectl get services -n smart-inventory

# 檢查 Ingress 狀態
kubectl get ingress -n smart-inventory

# 檢查 HPA 狀態
kubectl get hpa -n smart-inventory
```

## 第十二步：獲取外部 IP 並測試
```bash
# 獲取外部 IP
EXTERNAL_IP=$(kubectl get ingress smart-inventory-ingress -n smart-inventory -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "外部 IP: $EXTERNAL_IP"

# 測試 API
curl http://$EXTERNAL_IP/api/inventory/healthz
curl http://$EXTERNAL_IP/api/orders/healthz
```

## 故障排除命令
```bash
# 如果 Ingress 沒有外部 IP，檢查狀態
kubectl describe ingress smart-inventory-ingress -n smart-inventory

# 檢查 Pod 日誌
kubectl logs -f deployment/inventory-service -n smart-inventory
kubectl logs -f deployment/order-service -n smart-inventory

# 檢查事件
kubectl get events -n smart-inventory --sort-by='.lastTimestamp'
```
