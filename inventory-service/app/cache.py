import os, redis

_redis = None

def get_redis():
    global _redis
    if _redis is None:
        host = os.getenv("REDIS_HOST", "redis")
        port = int(os.getenv("REDIS_PORT", "6379"))
        _redis = redis.Redis(host=host, port=port, decode_responses=True)
    return _redis
