"""Cost Guard module — Giám sát và giới hạn chi phí LLM sử dụng Redis."""
import time
import logging
import redis
from fastapi import HTTPException
from app.config import settings

logger = logging.getLogger(__name__)

# Giá token tham khảo
PRICE_PER_1K_INPUT_TOKENS = 0.00015   # GPT-4o-mini: $0.15/1M input
PRICE_PER_1K_OUTPUT_TOKENS = 0.0006   # GPT-4o-mini: $0.60/1M output

r = None
if settings.redis_url:
    try:
        r = redis.from_url(settings.redis_url)
    except Exception as e:
        logger.error(f"Failed to connect to Redis at {settings.redis_url}: {e}")

def get_budget_key(user_key: str) -> str:
    """Trả về Redis key theo định dạng budget:{user_key}:{yyyy-mm-dd}."""
    today = time.strftime("%Y-%m-%d")
    return f"budget:{user_key}:{today}"

def check_budget(user_key: str):
    """
    Kiểm tra xem user có vượt quá daily budget không.
    Ném lỗi 402 Payment Required nếu vượt quá giới hạn.
    """
    if r is None:
        logger.warning("Redis is not connected. Bypassing cost guard check.")
        return

    key = get_budget_key(user_key)
    try:
        current_cost_str = r.get(key)
        current_cost = float(current_cost_str) if current_cost_str else 0.0
        
        if current_cost >= settings.daily_budget_usd:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "Daily budget exceeded",
                    "used_usd": round(current_cost, 6),
                    "budget_usd": settings.daily_budget_usd,
                    "resets_at": "midnight UTC",
                }
            )
    except redis.RedisError as e:
        logger.error(f"Redis cost guard check error: {e}")

def record_usage(user_key: str, input_tokens: int, output_tokens: int) -> float:
    """
    Tính toán chi phí cho request vừa thực hiện và cộng dồn vào Redis.
    Trả về tổng chi phí đã tiêu thụ trong ngày của user.
    """
    input_cost = (input_tokens / 1000) * PRICE_PER_1K_INPUT_TOKENS
    output_cost = (output_tokens / 1000) * PRICE_PER_1K_OUTPUT_TOKENS
    cost = input_cost + output_cost

    if r is None:
        return cost

    key = get_budget_key(user_key)
    try:
        pipe = r.pipeline()
        pipe.incrbyfloat(key, cost)
        pipe.expire(key, 32 * 24 * 3600)  # Lưu trữ trong 32 ngày để phục vụ thống kê/phân tích tháng
        results = pipe.execute()
        
        new_total_cost = float(results[0])
        logger.info(f"Recorded usage for user {user_key}: cost=${cost:.6f}, total_today=${new_total_cost:.6f}")
        return new_total_cost
    except redis.RedisError as e:
        logger.error(f"Failed to record usage in Redis: {e}")
        return cost
