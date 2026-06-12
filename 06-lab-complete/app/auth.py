"""Authentication module — Xác thực API Key từ request headers."""
from fastapi import Security, HTTPException
from fastapi.security.api_key import APIKeyHeader
from app.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Xác thực API Key.
    Nếu không hợp lệ, ném ra lỗi 401 Unauthorized.
    Nếu hợp lệ, trả về chính api_key (dùng làm identifier cho rate limit/cost guard).
    """
    if not api_key or api_key != settings.agent_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include header: X-API-Key: <key>",
        )
    return api_key
