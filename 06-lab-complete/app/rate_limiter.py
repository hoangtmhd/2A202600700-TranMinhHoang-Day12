"""Rate Limiter module — Giới hạn lưu lượng request sử dụng Redis Sorted Set (Sliding Window)."""
import time
import logging
import redis
from fastapi import HTTPException
from app.config import settings

logger = logging.getLogger(__name__)

# Kết nối tới Redis cache
# Nếu redis_url trống, việc kết nối sẽ bị bỏ qua (hoặc dùng fallback in-memory)
r = None
if settings.redis_url:
    try:
        r = redis.from_url(settings.redis_url)
    except Exception as e:
        logger.error(f"Failed to connect to Redis at {settings.redis_url}: {e}")

def check_rate_limit(user_key: str):
    """
    Kiểm tra rate limit sử dụng thuật toán Sliding Window với Redis Sorted Set.
    Giới hạn số lượng request mỗi user trong 1 phút dựa trên settings.rate_limit_per_minute.
    """
    if r is None:
        # Fallback đơn giản nếu không có Redis (cho dev local không có Redis)
        logger.warning("Redis is not connected. Bypassing rate limiter check.")
        return

    now = time.time()
    key = f"rate_limit:{user_key}"
    clear_before = now - 60

    try:
        # Pipeline để thực hiện atomic operations giảm round-trips
        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, clear_before)
        pipe.zcard(key)
        pipe.zadd(key, {f"{now}-{user_key}": now})
        pipe.expire(key, 65)
        
        # Thực thi pipeline và lấy số lượng request trong window
        _, request_count, _, _ = pipe.execute()

        if request_count > settings.rate_limit_per_minute:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} req/min",
                headers={"Retry-After": "60"},
            )
    except redis.RedisError as e:
        logger.error(f"Redis rate limiter error: {e}")
        # Không chặn người dùng nếu Redis bị lỗi (Fail-open)
        return
