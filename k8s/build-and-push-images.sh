#!/bin/bash

# 建構並推送 Docker 映像檔到 GCP Container Registry
echo "🐳 開始建構並推送 Docker 映像檔到 GCP..."

# 檢查 gcloud 是否已安裝並登入
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI 未安裝。請先安裝 Google Cloud SDK"
    exit 1
fi

# 檢查是否已登入
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ 請先登入 Google Cloud: gcloud auth login"
    exit 1
fi

# 獲取專案 ID
PROJECT_ID=$(gcloud config get-value project)
if [ -z "$PROJECT_ID" ]; then
    echo "❌ 未設定專案 ID。請執行: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

echo "📋 專案 ID: $PROJECT_ID"

# 啟用 Container Registry API
echo "🔧 啟用 Container Registry API..."
gcloud services enable containerregistry.googleapis.com

# 配置 Docker 認證
echo "🔑 配置 Docker 認證..."
gcloud auth configure-docker

# 建立簡單的 Dockerfile 和應用程式
echo "📝 建立 inventory-service..."
mkdir -p ../inventory-service
cat > ../inventory-service/Dockerfile << 'EOF'
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8001

CMD ["python", "main.py"]
EOF

cat > ../inventory-service/requirements.txt << 'EOF'
fastapi==0.104.1
uvicorn==0.24.0
pymysql==1.1.0
redis==5.0.1
pydantic==2.5.0
sqlalchemy==2.0.23
EOF

cat > ../inventory-service/main.py << 'EOF'
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/api/healthz")
async def health_check():
    return {"status": "healthy", "service": "inventory-service"}

@app.get("/api/inventory/healthz")
async def inventory_health():
    return {"status": "healthy", "service": "inventory-service"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
EOF

# 建立 order-service
echo "📝 建立 order-service..."
mkdir -p ../order-service
cat > ../order-service/Dockerfile << 'EOF'
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8002

CMD ["python", "main.py"]
EOF

cat > ../order-service/requirements.txt << 'EOF'
fastapi==0.104.1
uvicorn==0.24.0
pymysql==1.1.0
redis==5.0.1
pydantic==2.5.0
sqlalchemy==2.0.23
requests==2.31.0
EOF

cat > ../order-service/main.py << 'EOF'
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/api/healthz")
async def health_check():
    return {"status": "healthy", "service": "order-service"}

@app.get("/api/orders/healthz")
async def orders_health():
    return {"status": "healthy", "service": "order-service"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
EOF

# 建構並推送 inventory-service
echo "🏗️ 建構 inventory-service..."
cd ../inventory-service
docker build -t gcr.io/$PROJECT_ID/inventory-service:latest .
docker push gcr.io/$PROJECT_ID/inventory-service:latest
cd ../k8s

# 建構並推送 order-service
echo "🏗️ 建構 order-service..."
cd ../order-service
docker build -t gcr.io/$PROJECT_ID/order-service:latest .
docker push gcr.io/$PROJECT_ID/order-service:latest
cd ../k8s

# 更新 Kubernetes 配置文件中的專案 ID
echo "📝 更新 Kubernetes 配置文件..."
sed -i "s/PROJECT_ID/$PROJECT_ID/g" inventory-service.yaml
sed -i "s/PROJECT_ID/$PROJECT_ID/g" order-service.yaml

echo "✅ 映像檔建構和推送完成！"
echo ""
echo "📋 已推送的映像檔："
echo "   - gcr.io/$PROJECT_ID/inventory-service:latest"
echo "   - gcr.io/$PROJECT_ID/order-service:latest"
echo ""
echo "🚀 現在可以執行 ./gcp-deploy.sh 進行部署"