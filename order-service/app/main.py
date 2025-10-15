import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from .db import engine
from .models import Base
from .routers import health, orders
from .services.redis_subscriber import redis_subscriber
import time
import asyncio

# 等資料庫就緒（最多 20 秒，每秒重試）
RETRIES = 20
for i in range(RETRIES):
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT 1"))
        break
    except Exception:
        if i == RETRIES - 1:
            raise
        time.sleep(1)

# 初始化資料表
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Order Service")

# 添加 CORS 中間件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允許所有來源
    allow_credentials=True,
    allow_methods=["*"],  # 允許所有方法
    allow_headers=["*"],  # 允許所有標頭
)

@app.on_event("startup")
async def startup_event():
    """應用啟動時啟動 Redis 訂閱者"""
    asyncio.create_task(redis_subscriber.subscribe_to_channels())

app.include_router(health.router)
app.include_router(orders.router)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8002)
