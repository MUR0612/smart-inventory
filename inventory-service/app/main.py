import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from .db import engine
from .models import Base
from .routers import health, products, stock
import time

# 開機時重試 DB，避免剛啟動連不上
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

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Inventory Service")

# 添加 CORS 中間件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允許所有來源
    allow_credentials=True,
    allow_methods=["*"],  # 允許所有方法
    allow_headers=["*"],  # 允許所有標頭
)

app.include_router(health.router)
app.include_router(products.router)
app.include_router(stock.router)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001)
