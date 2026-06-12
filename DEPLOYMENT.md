# Deployment Information

## Public URL
- **Agent API URL:** `https://day12-production-agent.up.railway.app`
- **Health Check URL:** `https://day12-production-agent.up.railway.app/health`

## Platform
- **Hosting Platform:** Railway
- **Database/Cache:** Railway Redis Add-on

## Test Commands

### 1. Health Check (Liveness Probe)
```bash
curl https://day12-production-agent.up.railway.app/health
```
**Expected Response:**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "production",
  "uptime_seconds": 154.2,
  "checks": {
    "llm": "mock"
  },
  "timestamp": "2026-06-12T07:50:00.123456Z"
}
```

### 2. Readiness Check (Readiness Probe)
```bash
curl https://day12-production-agent.up.railway.app/ready
```
**Expected Response:**
```json
{
  "ready": true
}
```

### 3. API Test (Without Authentication)
```bash
curl -i -X POST https://day12-production-agent.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Docker?"}'
```
**Expected Response:**
```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{"detail":"Invalid or missing API key. Include header: X-API-Key: <key>"}
```

### 4. API Test (With Authentication)
```bash
curl -i -X POST https://day12-production-agent.up.railway.app/ask \
  -H "X-API-Key: prod-agent-secure-key" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Docker?"}'
```
**Expected Response:**
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "question": "What is Docker?",
  "answer": "Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere! (mock response)",
  "model": "gpt-4o-mini",
  "timestamp": "2026-06-12T07:51:10.654321Z"
}
```

### 5. Rate Limiting Test (Send 15 requests consecutively within 1 minute)
```bash
for i in {1..15}; do 
  curl -H "X-API-Key: prod-agent-secure-key" \
       -H "Content-Type: application/json" \
       -d '{"question": "Test limit '$i'"}' \
       https://day12-production-agent.up.railway.app/ask
  echo ""
done
```
**Expected Response on 11th request:**
```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
Content-Type: application/json

{"detail":"Rate limit exceeded: 10 req/min"}
```

## Environment Variables Set
- `PORT`: `8000` (định tuyến tự động bởi Railway)
- `ENVIRONMENT`: `production`
- `AGENT_API_KEY`: `prod-agent-secure-key`
- `REDIS_URL`: `redis://default:password@redis-service-host:6379/0` (liên kết từ Redis Add-on)
- `LLM_MODEL`: `gpt-4o-mini`

## Screenshots
Các ảnh chụp màn hình minh chứng được đặt tại thư mục `screenshots/`:
- `screenshots/dashboard.png` (Trang quản trị Railway Dashboard)
- `screenshots/running.png` (Logs hiển thị dịch vụ đang chạy)
- `screenshots/test.png` (Kết quả kiểm thử gọi API qua curl thành công)
