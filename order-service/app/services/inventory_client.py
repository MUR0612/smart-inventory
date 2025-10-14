import httpx
import os
from typing import Dict, List, Optional
from fastapi import HTTPException

class InventoryClient:
    """庫存服務客戶端"""
    
    def __init__(self):
        self.base_url = os.getenv("INVENTORY_BASE_URL", "http://inventory-service:8001")
        self.timeout = 30.0
    
    async def check_stock(self, product_id: int, required_qty: int) -> Dict:
        """檢查產品庫存是否足夠"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/api/inventory/stock/{product_id}")
                response.raise_for_status()
                
                stock_info = response.json()
                if stock_info["current_stock"] < required_qty:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Insufficient stock for product {product_id}. "
                               f"Required: {required_qty}, Available: {stock_info['current_stock']}"
                    )
                
                return stock_info
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Inventory service unavailable: {str(e)}")
    
    async def reserve_stock(self, product_id: int, qty: int) -> Dict:
        """預留庫存（減少庫存）"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                adjustment_data = {"adjustment": -qty}
                response = await client.post(
                    f"{self.base_url}/api/inventory/stock/{product_id}/adjust",
                    json=adjustment_data
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
            elif e.response.status_code == 400:
                raise HTTPException(status_code=409, detail="Insufficient stock")
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Inventory service unavailable: {str(e)}")
    
    async def release_stock(self, product_id: int, qty: int) -> Dict:
        """釋放庫存（增加庫存）"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                adjustment_data = {"adjustment": qty}
                response = await client.post(
                    f"{self.base_url}/api/inventory/stock/{product_id}/adjust",
                    json=adjustment_data
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Inventory service unavailable: {str(e)}")
    
    async def get_product_info(self, product_id: int) -> Dict:
        """取得產品資訊"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/api/inventory/products/{product_id}")
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Inventory service unavailable: {str(e)}")

# 全域實例
inventory_client = InventoryClient()


