import redis
import json
import asyncio
from typing import Dict, Any

class RedisSubscriber:
    """Redis 訂閱者服務"""
    
    def __init__(self):
        try:
            self.redis_client = redis.Redis(host='redis', port=6379, decode_responses=True, socket_connect_timeout=5, socket_timeout=5)
            self.running = False
        except Exception as e:
            print(f"Redis connection failed: {e}")
            self.redis_client = None
            self.running = False
    
    async def handle_low_stock_alert(self, data: Dict[str, Any]):
        """處理低庫存警告"""
        print(f"🚨 Low Stock Alert: {data['sku']} ({data['name']}) - "
              f"Current: {data['current_stock']}, Safety: {data['safety_stock']}")
        
        # 這裡可以添加更多處理邏輯，例如：
        # - 發送郵件通知
        # - 更新儀表板
        # - 記錄到日誌系統
        # - 觸發自動補貨流程
    
    async def handle_stock_change(self, data: Dict[str, Any]):
        """處理庫存變更通知"""
        print(f"📦 Stock Change: {data['sku']} ({data['name']}) - "
              f"Changed by {data['adjustment']} (from {data['old_stock']} to {data['new_stock']})")
        
        # 這裡可以添加更多處理邏輯，例如：
        # - 更新庫存統計
        # - 觸發重新計算安全庫存
        # - 更新儀表板數據
    
    async def handle_inventory_update(self, data: Dict[str, Any]):
        """處理庫存更新通知"""
        print(f"🔄 Inventory Update: {data}")
        
        # 這裡可以添加更多處理邏輯
    
    async def subscribe_to_channels(self):
        """訂閱所有相關頻道"""
        if not self.redis_client:
            print("❌ Redis client not available, skipping subscription")
            return
            
        try:
            pubsub = self.redis_client.pubsub()
            
            # 訂閱頻道
            pubsub.subscribe(
                'low_stock_alerts',
                'stock_changes', 
                'inventory_updates'
            )
            
            print("🔔 Subscribed to Redis channels: low_stock_alerts, stock_changes, inventory_updates")
            
            self.running = True
            for message in pubsub.listen():
                if not self.running:
                    break
                    
                if message['type'] == 'message':
                    channel = message['channel']
                    data = json.loads(message['data'])
                    
                    if channel == 'low_stock_alerts':
                        await self.handle_low_stock_alert(data)
                    elif channel == 'stock_changes':
                        await self.handle_stock_change(data)
                    elif channel == 'inventory_updates':
                        await self.handle_inventory_update(data)
                        
        except Exception as e:
            print(f"❌ Redis subscription error: {e}")
        finally:
            if 'pubsub' in locals():
                pubsub.close()
            print("🔕 Redis subscription closed")
    
    def stop(self):
        """停止訂閱"""
        self.running = False

# 全域實例
redis_subscriber = RedisSubscriber()
