# Day 12 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found in `01-localhost-vs-production/develop/app.py`
Trong file `develop/app.py`, có ít nhất 5 vấn đề (anti-patterns) sau:
1. **Hardcoded Secrets (Dòng 17, 18):** `OPENAI_API_KEY` và `DATABASE_URL` chứa credentials giả lập (`sk-hardcoded-...`, `password123`) được viết trực tiếp vào mã nguồn. Nếu mã nguồn này được đẩy lên kho lưu trữ công khai (GitHub), các thông tin nhạy cảm này sẽ lập tức bị lộ.
2. **Không có cấu hình tập trung (Dòng 21, 22):** Các biến cấu hình logic như `DEBUG = True`, `MAX_TOKENS = 500` định nghĩa cứng trực tiếp, không linh hoạt khi chuyển đổi giữa môi trường dev, staging và production.
3. **Log không chuẩn hóa và lộ thông tin nhạy cảm (Dòng 32-34):** Sử dụng hàm `print()` thay vì thư viện logging. Đồng thời ghi log trực tiếp biến nhạy cảm `OPENAI_API_KEY` ra stdout, tạo lỗ hổng bảo mật nghiêm trọng khi log bị thu thập.
4. **Không có Health Check Endpoint (Liveness/Readiness probes):** Không cung cấp endpoint `/health` hay `/ready`. Khi ứng dụng bị treo hoặc gặp lỗi kết nối cơ sở dữ liệu, các nền tảng tự động hóa (Railway, Render, Kubernetes) không thể phát hiện để tự động khởi động lại.
5. **Cấu hình mạng cứng (Dòng 51-53):** Gán cứng `host="localhost"` và `port=8000`. Cấu hình `host="localhost"` khiến container bên ngoài không thể kết nối tới dịch vụ. Cấu hình cứng `port=8000` làm ứng dụng không thể khởi chạy trên các môi trường cloud (Railway/Render) nơi cổng được chỉ định linh hoạt qua biến môi trường `PORT`. Đồng thời, bật chế độ `reload=True` gây lãng phí tài nguyên và rủi ro bảo mật trong production.

### Exercise 1.3: Comparison table

| Feature | Develop (Basic) | Production (Advanced) | Tại sao quan trọng? |
|---------|---------|------------|----------------|
| **Config** | Hardcode trực tiếp trong mã nguồn. | Sử dụng biến môi trường (Environment variables) qua file cấu hình `config.py` đọc từ `os.getenv` hoặc class Settings. | Cho phép chuyển đổi linh hoạt cấu hình giữa các môi trường mà không cần sửa đổi mã nguồn. Đảm bảo tuân thủ nguyên tắc 12-Factor App. |
| **Secrets** | Hardcode trực tiếp (`api_key = "sk-..."`). | Đọc từ môi trường qua biến hệ thống (chỉ cần cấu hình trên server/dashboard). | Tránh lộ lọt API keys, thông tin tài khoản cơ sở dữ liệu khi đẩy mã nguồn lên GitHub/GitLab. |
| **Port** | Cố định `8000`, host `localhost`. | Đọc động từ biến môi trường `PORT`, bind vào `0.0.0.0`. | Giúp các nền tảng dịch vụ Cloud tự động định tuyến cổng (port binding). Bind `0.0.0.0` để container có thể nhận yêu cầu từ bên ngoài máy host. |
| **Health check** | Không triển khai. | Triển khai 2 endpoints `/health` (Liveness) và `/ready` (Readiness). | Giúp điều phối viên dịch vụ (Orchestrator) kiểm tra trạng thái sống của dịch vụ để tự động khởi động lại khi crash, hoặc ngắt traffic khi ứng dụng quá tải/đang khởi động. |
| **Shutdown** | Tắt đột ngột (kill process). | Graceful shutdown xử lý tín hiệu `SIGTERM`, chờ xử lý xong các request in-flight rồi mới tắt ứng dụng. | Tránh ngắt quãng request của người dùng, đảm bảo tính toàn vẹn của dữ liệu và cải thiện trải nghiệm người dùng khi cập nhật phiên bản mới. |
| **Logging** | Dùng hàm `print()`. | Sử dụng structured logging định dạng JSON (`json.dumps`). | Giúp các hệ thống thu thập log trung tâm (Loki, Datadog, ELK) dễ dàng phân loại, lập chỉ mục và phân tích lỗi tự động mà không cần viết các parser regex phức tạp. |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions
1. **Base image là gì?:** Base image là `python:3.11`. Đây là phân phối Python đầy đủ, kích thước lớn vì chứa toàn bộ bộ biên dịch và các công cụ bổ trợ hệ thống.
2. **Working directory là gì?:** Working directory được thiết lập là `/app`. Tất cả các câu lệnh tiếp theo (`COPY`, `RUN`, `CMD`) sẽ được thực thi tại thư mục này trong container.
3. **Tại sao COPY requirements.txt trước?:** Nhằm tối ưu hóa cơ chế lưu bộ nhớ đệm theo lớp của Docker (layer caching). Quá trình cài đặt dependencies tốn nhiều thời gian nhất. Nếu `requirements.txt` không thay đổi, Docker sẽ bỏ qua việc chạy `pip install` ở các lần build sau và lấy luôn từ cache, giúp đẩy nhanh tiến độ build khi thay đổi code ứng dụng.
4. **CMD vs ENTRYPOINT khác nhau thế nào?:**
   - `CMD` thiết lập lệnh mặc định hoặc tham số mặc định cho container. Lệnh này có thể dễ dàng bị ghi đè hoàn toàn bằng cách truyền lệnh mới ở cuối câu lệnh `docker run`.
   - `ENTRYPOINT` quy định file thực thi chính luôn chạy khi container khởi động. Các tham số truyền vào từ `docker run` hoặc `CMD` sẽ được truyền làm tham số cho file thực thi này. Muốn ghi đè `ENTRYPOINT` phải sử dụng cờ `--entrypoint` chuyên dụng.

### Exercise 2.3: Image size comparison
- **Develop Image (Basic):** 1660 MB (1.66 GB)
- **Production Image (Advanced):** 236 MB
- **Chênh lệch kích thước (Difference):** 85.8% (Tiết kiệm khoảng 1.42 GB)
- **Giải thích tại sao Production Image nhỏ hơn:**
  - Sử dụng base image là `python:3.11-slim` thay vì `python:3.11` tiêu chuẩn (giảm lượng thư viện hệ thống dư thừa).
  - Áp dụng kỹ thuật **Multi-stage build**: Stage 1 (`builder`) cài đặt toàn bộ công cụ cần để biên dịch như `gcc`, `libpq-dev` và lưu cache cài đặt. Stage 2 (`runtime`) chỉ copy các file thư viện Python sạch đã cài đặt từ `/root/.local` của Stage 1 sang mà không cần copy các công cụ build nặng nề.
  - Loại bỏ cache cài đặt của pip thông qua cờ `--no-cache-dir`.

### Exercise 2.4: Docker Compose questions
- **Services nào được start?:** Có 4 services chính được start:
  1. `agent`: FastAPI AI agent (Triển khai ứng dụng FastAPI).
  2. `redis`: Dịch vụ cache in-memory phục vụ lưu session và rate limiting.
  3. `qdrant`: Vector database lưu trữ tri thức cho RAG.
  4. `nginx`: Đóng vai trò làm Load balancer phân tải và Reverse proxy đón nhận kết nối bên ngoài.
- **Chúng giao tiếp với nhau thế nào?:**
  - Các service cùng tham gia vào một mạng ảo nội bộ tên là `internal` sử dụng driver bridge.
  - Client bên ngoài chỉ giao tiếp với cổng `80` (HTTP) và `443` (HTTPS) của `nginx`.
  - `nginx` thực hiện phân tải các yêu cầu `/health`, `/ask` vào các container `agent` ở cổng nội bộ `8000`.
  - Container `agent` kết nối tới `redis` qua domain nội bộ `redis:6379` và kết nối tới `qdrant` qua `qdrant:6333` để truy xuất dữ liệu. `redis` và `qdrant` không expose port ra ngoài host để đảm bảo an toàn bảo mật.

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment
- **URL triển khai mẫu:** `https://day12-production-agent.up.railway.app`
- **Sự khác biệt giữa `render.yaml` và `railway.toml`:**
  - `railway.toml` định cấu hình cho một dịch vụ đơn lẻ, chỉ rõ cách build (ví dụ dùng Nixpacks) và cách chạy lệnh start cùng tham số healthcheckPath.
  - `render.yaml` đóng vai trò là Blueprint Infrastructure as Code (IaC), định nghĩa đồng thời nhiều tài nguyên trong cùng một file (cả dịch vụ Web của Agent và dịch vụ Redis độc lập), quản lý cả cấu hình tài nguyên (gói free, khu vực singapore), và cách sinh tự động các khóa bảo mật (`generateValue`).

---

## Part 4: API Security

### Exercise 4.1-4.3: Test results
- **API Key Auth test (Ex 4.1):**
  - Không truyền API Key: Trả về lỗi `401 Unauthorized` với detail `"Missing API key."`.
  - Truyền sai API Key: Trả về lỗi `403 Forbidden` với detail `"Invalid API key."`.
  - Truyền đúng API Key (`X-API-Key: secret-key`): Trả về `200 OK` cùng nội dung phản hồi từ Agent.
- **Rate limiting test (Ex 4.3):**
  - Với tài khoản `student` (User thường - 10 req/min): Khi gửi request thứ 11 trong vòng 1 phút, server trả về lỗi `429 Too Many Requests` với header `Retry-After`.
  - Với tài khoản `teacher` (Admin - 100 req/min): Bypass giới hạn thường, áp dụng mức trần cao hơn (100 req/min).

### Exercise 4.4: Cost guard implementation
- **Cách tiếp cận:**
  - Sử dụng Redis làm hệ thống lưu trữ tập trung thay vì in-memory để đảm bảo tính stateless khi scale ứng dụng lên nhiều replicas.
  - Cấu trúc key trong Redis: `budget:{user_id}:{current_date}` (ví dụ `budget:user123:2026-06-12`).
  - Khi có request gửi đến, lấy số tiền đã tiêu dùng bằng lệnh `GET`. So sánh tổng số tiền hiện tại + số tiền ước tính cho request mới. Nếu vượt quá budget ($10/tháng hoặc $1/ngày theo cấu hình), ném ra ngoại lệ `HTTPException` mã `402 Payment Required`.
  - Nếu nằm trong budget, gọi LLM xong sẽ thực hiện cộng dồn chi phí mới bằng lệnh `INCRBYFLOAT` trên Redis và đặt thời hạn tự động hết hạn cho key là 32 ngày (`EXPIRE`) để giải phóng bộ nhớ.

---

## Part 5: Scaling & Reliability

### Exercise 5.1-5.5: Implementation notes
- **Liveness & Readiness probe (Ex 5.1):**
  - Liveness probe (`/health`): Trả về trạng thái `status: ok` khi tiến trình FastAPI đang hoạt động.
  - Readiness probe (`/ready`): Trả về `status: ready` (200) khi các kết nối tới database (Redis, SQL, Vector DB) đã sẵn sàng. Trả về `503 Service Unavailable` khi các kết nối này bị lỗi hoặc khi ứng dụng đang thực hiện Graceful Shutdown.
- **Graceful shutdown (Ex 5.2):**
  - Khi nhận tín hiệu `SIGTERM` (khi scale down hoặc deploy phiên bản mới), Agent sẽ lập tức chuyển trạng thái `_is_ready = False` (để Readiness probe trả về 503, khiến Load Balancer không hướng thêm traffic mới vào container này).
  - Agent tiếp tục chờ để xử lý nốt các request đang xử lý (in-flight) được ghi nhận thông qua biến đếm đòn bẩy Middleware cho đến khi biến đếm về 0 (hoặc hết thời gian timeout 30 giây), sau đó đóng các kết nối và dừng tiến trình một cách an toàn.
- **Stateless design (Ex 5.3):**
  - Để hỗ trợ scale ngang (phân phối request ngẫu nhiên qua các replicas bởi Load Balancer), toàn bộ lịch sử hội thoại được lưu trữ trên Redis với key `history:{user_id}` thay vì lưu tại bộ nhớ RAM của từng container. Nhờ đó, người dùng gửi request tới bất kỳ replica nào cũng đều truy xuất được đầy đủ lịch sử hội thoại trước đó.
- **Load Balancing (Ex 5.4 - 5.5):**
  - Chạy `docker compose up --scale agent=3` sẽ khởi động 3 instance của agent song song. Nginx đón nhận traffic ở cổng 80 và dùng thuật toán Round-Robin để điều phối request đều cho cả 3 container. Khi có 1 container bị chết đột ngột, Nginx tự động phát hiện qua cơ chế failover và chuyển hướng traffic sang các container còn lại mà không gây lỗi cho người dùng.
