import redis
import json
import asyncio
from typing import Callable, Dict, Any
from ..cache import get_redis

class RedisPubSubService:
    """Redis Pub/Sub 服務"""
    
    def __init__(self):
        self.redis_client = get_redis()
        self.subscribers = {}
    
    def publish_low_stock_alert(self, alert_data: Dict[str, Any]):
        """發布低庫存警告"""
        try:
            self.redis_client.publish("low_stock_alerts", json.dumps(alert_data))
            print(f"Published low stock alert: {alert_data}")
        except Exception as e:
            print(f"Failed to publish low stock alert: {e}")
    
    def publish_stock_change(self, change_data: Dict[str, Any]):
        """發布庫存變更通知"""
        try:
            self.redis_client.publish("stock_changes", json.dumps(change_data))
            print(f"Published stock change: {change_data}")
        except Exception as e:
            print(f"Failed to publish stock change: {e}")
    
    def publish_inventory_update(self, update_data: Dict[str, Any]):
        """發布庫存更新通知"""
        try:
            self.redis_client.publish("inventory_updates", json.dumps(update_data))
            print(f"Published inventory update: {update_data}")
        except Exception as e:
            print(f"Failed to publish inventory update: {e}")
    
    async def subscribe_to_channel(self, channel: str, callback: Callable):
        """訂閱頻道"""
        try:
            pubsub = self.redis_client.pubsub()
            pubsub.subscribe(channel)
            
            print(f"Subscribed to channel: {channel}")
            
            for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        await callback(data)
                    except Exception as e:
                        print(f"Error processing message: {e}")
                        
        except Exception as e:
            print(f"Failed to subscribe to {channel}: {e}")
    
    def register_subscriber(self, channel: str, callback: Callable):
        """註冊訂閱者"""
        self.subscribers[channel] = callback
    
    async def start_subscribers(self):
        """啟動所有訂閱者"""
        tasks = []
        for channel, callback in self.subscribers.items():
            task = asyncio.create_task(self.subscribe_to_channel(channel, callback))
            tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks)

# 全域實例
redis_pubsub = RedisPubSubService()









