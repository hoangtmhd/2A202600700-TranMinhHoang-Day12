"""
Production AI Agent — Kết hợp tất cả Day 12 concepts

Checklist:
  ✅ Config từ environment (12-factor)
  ✅ Structured JSON logging
  ✅ API Key authentication
  ✅ Rate limiting (Redis-based)
  ✅ Cost guard (Redis-based)
  ✅ Input validation (Pydantic)
  ✅ Health check + Readiness probe (Redis check)
  ✅ Graceful shutdown
  ✅ Security headers
  ✅ CORS
  ✅ Error handling
"""
import os
import time
import signal
import logging
import json
import redis
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Security, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from app.config import settings
from app.auth import verify_api_key
from app.rate_limiter import check_rate_limit
from app.cost_guard import check_budget, record_usage, get_budget_key

# Mock LLM (thay bằng OpenAI/Anthropic khi có API key)
from utils.mock_llm import ask as llm_ask

# ─────────────────────────────────────────────────────────
# Logging — JSON structured
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_in_flight_requests = 0

# Khởi tạo kết nối Redis
r = None
if settings.redis_url:
    try:
        r = redis.from_url(settings.redis_url)
    except Exception as e:
        logger.error(f"Failed to connect to Redis at {settings.redis_url}: {e}")

# ─────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }))
    
    # Kiểm tra kết nối Redis lúc startup
    if r:
        try:
            r.ping()
            logger.info(json.dumps({"event": "redis_connected", "status": "ok"}))
        except Exception as e:
            logger.error(json.dumps({"event": "redis_connection_failed", "error": str(e)}))
            
    time.sleep(0.1)  # simulate init
    _is_ready = True
    logger.info(json.dumps({"event": "ready"}))

    yield

    _is_ready = False
    logger.info(json.dumps({"event": "shutdown_initiated"}))
    
    # Graceful shutdown: Chờ các request in-flight hoàn thành
    timeout = 30
    elapsed = 0
    while _in_flight_requests > 0 and elapsed < timeout:
        logger.info(json.dumps({
            "event": "waiting_in_flight",
            "count": _in_flight_requests,
            "elapsed_seconds": elapsed
        }))
        time.sleep(1)
        elapsed += 1
        
    logger.info(json.dumps({"event": "shutdown_complete"}))

# ─────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _in_flight_requests
    start = time.time()
    _in_flight_requests += 1
    try:
        response: Response = await call_next(request)
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if "server" in response.headers:
            del response.headers["server"]
        duration = round((time.time() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration,
        }))
        return response
    except Exception as e:
        logger.error(json.dumps({
            "event": "request_error",
            "method": request.method,
            "path": request.url.path,
            "error": str(e)
        }))
        raise
    finally:
        _in_flight_requests -= 1

# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000,
                          description="Your question for the agent")

class AskResponse(BaseModel):
    question: str
    answer: str
    model: str
    timestamp: str

# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────

@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {
            "ask": "POST /ask (requires X-API-Key)",
            "health": "GET /health",
            "ready": "GET /ready",
        },
    }

@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(
    body: AskRequest,
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """
    Send a question to the AI agent.

    **Authentication:** Include header `X-API-Key: <your-key>`
    """
    # Sử dụng 8 ký tự đầu của API Key để phân biệt các user bucket
    user_id = _key[:8]

    # 1. Rate limiting check (Redis-based)
    check_rate_limit(user_id)

    # 2. Budget check (Redis-based)
    check_budget(user_id)

    # Ước lượng tokens đầu vào
    input_tokens = len(body.question.split()) * 2

    logger.info(json.dumps({
        "event": "agent_call",
        "user_id": user_id,
        "q_len": len(body.question),
        "client": str(request.client.host) if request.client else "unknown",
    }))

    # 3. Lấy lịch sử hội thoại từ Redis (Stateless design)
    history_key = f"history:{user_id}"
    chat_history = []
    if r:
        try:
            # Lấy 10 tin nhắn gần nhất từ Redis list
            history_raw = r.lrange(history_key, -10, -1)
            for item in history_raw:
                chat_history.append(json.loads(item))
        except Exception as e:
            logger.error(json.dumps({"event": "get_history_failed", "error": str(e)}))

    # 4. Gọi LLM
    # Trong môi trường Lab, mock_llm chỉ nhận question. Tuy nhiên, chúng ta lưu trữ lịch sử
    # trò chuyện vào Redis để đảm bảo tính stateless đúng chuẩn.
    answer = llm_ask(body.question)

    # Ước lượng tokens đầu ra và ghi nhận chi phí
    output_tokens = len(answer.split()) * 2
    record_usage(user_id, input_tokens, output_tokens)

    # 5. Lưu lịch sử hội thoại mới vào Redis và đặt TTL là 1 giờ
    if r:
        try:
            chat_turn = {"q": body.question, "a": answer, "ts": datetime.now(timezone.utc).isoformat()}
            r.rpush(history_key, json.dumps(chat_turn))
            r.ltrim(history_key, -20, -1)  # Giữ tối đa 20 tin nhắn
            r.expire(history_key, 3600)    # Hết hạn sau 1 giờ không hoạt động
        except Exception as e:
            logger.error(json.dumps({"event": "save_history_failed", "error": str(e)}))

    return AskResponse(
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

@app.get("/health", tags=["Operations"])
def health():
    """Liveness probe. Platform restarts container if this fails."""
    status = "ok"
    checks = {"llm": "mock" if not settings.openai_api_key else "openai"}
    return {
        "status": status,
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/ready", tags=["Operations"])
def ready():
    """Readiness probe. Load balancer stops routing here if not ready."""
    if not _is_ready:
        raise HTTPException(503, "Not ready yet")
    
    # Kiểm tra kết nối Redis thực tế
    if r:
        try:
            r.ping()
        except Exception as e:
            logger.error(json.dumps({"event": "readiness_redis_failed", "error": str(e)}))
            raise HTTPException(503, f"Redis not available: {str(e)}")
            
    return {"ready": True}

@app.get("/metrics", tags=["Operations"])
def metrics(_key: str = Depends(verify_api_key)):
    """Basic metrics (protected)."""
    user_id = _key[:8]
    daily_cost = 0.0
    
    # Lấy thông tin chi phí thực tế từ Redis
    if r:
        try:
            cost_key = get_budget_key(user_id)
            cost_val = r.get(cost_key)
            if cost_val:
                daily_cost = float(cost_val)
        except Exception as e:
            logger.error(json.dumps({"event": "get_metrics_cost_failed", "error": str(e)}))

    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "daily_cost_usd": round(daily_cost, 6),
        "daily_budget_usd": settings.daily_budget_usd,
        "budget_used_pct": round(daily_cost / settings.daily_budget_usd * 100, 1) if settings.daily_budget_usd else 0.0,
    }

# ─────────────────────────────────────────────────────────
# Graceful Shutdown
# ─────────────────────────────────────────────────────────
def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal_received", "signum": signum}))
    # uvicorn tự xử lý tắt tiến trình qua lifespan, ở đây chỉ log nhận tín hiệu

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)

if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
