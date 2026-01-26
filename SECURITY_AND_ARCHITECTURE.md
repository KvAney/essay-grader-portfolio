# Security & Architecture - Essay Grader v2.0

## Critical Security Fixes

### 1. **Security Issue Fixed: Direct Kafka Exposure**

**Problem (v1.0):**
```
Frontend (Browser) → Kafka (Port 9092 public)
```
- Kafka ports exposed to internet
- Write credentials leaked to browser
- Anyone with port access could inject malicious messages

**Solution (v2.0):**
```
Frontend (Browser) → API Gateway (Port 8000) → Kafka (Internal only)
```
- API Gateway acts as a secure intermediary
- Kafka ports NOT exposed to public internet
- All credentials stay server-side
- Rate limiting on ingestion API prevents abuse

### 2. **Rate Limiting Architecture**

Groq Free Tier Constraint: **20 requests/minute**

**Problem:** If 10 users upload simultaneously and each essay runs 4 AI analysis tasks (Grammar, Structure, Logic, Content), you get 40 requests instantly → **429 Too Many Requests** error.

**Solution (Token Bucket + Sliding Window):**

```
┌─────────────────────────────────────────────────────────────┐
│  Ingestion API (50 uploads/min)                             │
│  Rate Limiter: TokenBucket                                  │
└─────────────────────────────────────────────────────────────┘
                        ↓
                   Kafka: ocr-jobs
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  OCR Worker (processes sequentially)                        │
│  Saves to MongoDB (heavy data)                              │
└─────────────────────────────────────────────────────────────┘
                        ↓
                   Kafka: ai-processing
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  AI Orchestrator (20 requests/min)                          │
│  Rate Limiter: SlidingWindow (Groq protection)              │
│  Parallel Execution: 4 async tasks per essay               │
│  Capacity: ~5 essays/min (20 RPM ÷ 4 tasks)               │
└─────────────────────────────────────────────────────────────┘
```

If 100 messages arrive, Kafka queues them. AI Worker processes ~1 every 12 seconds. Safe!

## Architecture Layers

### Layer 1: Ingestion (API Gateway) - `main.py`
```
POST /upload/ → Validate → Save to Postgres → Queue to Kafka (non-blocking) → Return 202
```
- **202 Accepted**: Returns immediately, doesn't wait for processing
- **Rate Limit**: 50 uploads/min (default, configurable)
- **CORS**: Only from localhost:3000 and localhost:8000
- **File Validation**: Max 50MB, check MIME type
- **Background Task**: Kafka send happens async

### Layer 2: Processing (OCR Worker) - `ocr_worker.py`
```
Kafka: ocr-jobs → Extract Text (OCR) → Save to MongoDB → Queue to Kafka: ai-processing
```
- **Claim Check Pattern**: Only store IDs in Kafka, heavy data in MongoDB
- **Async Processing**: One essay at a time, non-blocking
- **Error Handling**: Retry logic, logging per essay
- **Status Update**: Postgres marked as "ocr_completed"

### Layer 3: Analysis (AI Orchestrator) - `ai_worker.py` + `ai_orchestrator.py`
```
Kafka: ai-processing → Fetch from MongoDB → Fan-out 4 parallel AI tasks → Aggregate → Save to MongoDB
```

**Fan-Out Pattern: 4 Concurrent AI Tasks**
```
                    ┌─────────────────────┐
                    │   AI Orchestrator   │
                    │  (Rate Limited)     │
                    └────────────┬────────┘
                                 │
                ┌────────────────┼────────────────┐
                ↓                ↓                ↓                ↓
         ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
         │   Grammar    │ │  Structure   │ │    Logic     │ │   Content    │
         │  Analysis    │ │  Analysis    │ │   Analysis   │ │  Analysis    │
         │  (Groq)      │ │  (Groq)      │ │  (Groq)      │ │  (Groq)      │
         └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
                │                │                │                │
                └────────────────┼────────────────┘
                                 │
                        ┌────────▼────────┐
                        │  Aggregator     │
                        │  Combine results│
                        └────────┬────────┘
                                 │
                        ┌────────▼────────┐
                        │ Save to MongoDB │
                        │ Update Postgres │
                        └─────────────────┘
```

**Why Parallel Execution?**
- Groq allows 20 requests/min
- 4 tasks × 5 essays = 20 requests ✓ (safe)
- Parallel execution: 4 calls run at same time (~3-5 seconds each)
- Sequential execution: 4 × 3-5 seconds = 12-20 seconds per essay
- **Parallel = 3x faster** with same rate limit!

### Data Flow: Claim Check Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│  Kafka (Small Messages Only)                                    │
├─────────────────────────────────────────────────────────────────┤
│  Topic: ocr-jobs                                                │
│  {submission_id: 1, filename: essay.pdf, file_hex: "abc123..."}│  <-- 5MB
│                                                                 │
│  PROBLEM: Can't pass 5MB essays through Kafka!                │
│  - Kafka default max = 1MB                                     │
│  - Network bloat                                               │
│  - Serialization overhead                                      │
└─────────────────────────────────────────────────────────────────┘
                            ↓
                    Solution: Claim Check
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  MongoDB (Heavy Data Storage)                                   │
├─────────────────────────────────────────────────────────────────┤
│  Collection: evaluations                                        │
│  {                                                              │
│    _id: ObjectId("..."),                                       │
│    submission_id: 1,                                           │
│    text: "Long essay text...",  <-- 5MB stored here           │
│    status: "ocr_completed",                                    │
│    analysis_tasks: [],                                         │
│    aggregated_feedback: null                                   │
│  }                                                              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Kafka (Lightweight Reference)                                  │
├─────────────────────────────────────────────────────────────────┤
│  Topic: ai-processing                                           │
│  {submission_id: 1, mongo_id: "ObjectId(...)", filename: "..."} │  <-- <1KB
│                                                                 │
│  SOLUTION: Only pass reference IDs!                            │
│  - Worker fetches essay from MongoDB using mongo_id            │
│  - Kafka stays lean and fast                                   │
│  - Scales to 100,000+ essays                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Status Flow

```
START
  ↓
[API] → /upload/ (202 Accepted)
  ↓
Postgres: status = "queued"
  ↓
Kafka: ocr-jobs (file_hex)
  ↓
[OCR Worker] → Extract text
  ↓
MongoDB: Insert essay text
  ↓
Postgres: status = "ocr_completed"
  ↓
Kafka: ai-processing (mongo_id)
  ↓
[AI Worker] → Spawn 4 parallel tasks
  ↓
Groq API: 4 concurrent calls (Grammar, Structure, Logic, Content)
  ↓
MongoDB: Update with analysis results
  ↓
Postgres: status = "completed"
  ↓
[UI] → /status/1 → Returns full analysis
  ↓
END
```

## Rate Limiting Implementation

### TokenBucketRateLimiter
Used by: **Groq API** (AI Worker)
```python
limiter = TokenBucketRateLimiter(rate=20, per=60)

# If you make 20 calls instantly:
#   → First 20 calls: allowed
#   → Call 21: WAIT 3 seconds (refill rate = 1 token/sec)
#   → Call 22: WAIT 6 seconds
#   → Etc.

# Smooth distribution prevents bursts
```

### SlidingWindowRateLimiter
Used by: **Ingestion API** (Backend)
```python
limiter = SlidingWindowRateLimiter(rate=50, window=60)

# Tracks exact timestamp of each request
# Window: last 60 seconds
# If 50 requests in last 60s:
#   → Request 51: WAIT until oldest request expires
```

### AdaptiveRateLimiter
For future: **Auto-scale based on 429 errors**
```python
if groq_error_429:
    await limiter.on_rate_limit_hit()  # Reduce rate to 80%
    
if success:
    await limiter.on_success()  # Increase rate by 1/min
```

## Deployment Topology

### Docker Compose Services

```
┌─────────────────────────────────────────────────────┐
│                     Network: essaynet               │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │
│  │   Backend    │  │ OCR Worker   │  │ AI Worker│ │
│  │  (API)       │  │              │  │ (Groq)   │ │
│  │  :8000       │  │              │  │          │ │
│  └──────────────┘  └──────────────┘  └──────────┘ │
│         ↓                ↓                ↓        │
│  ┌────────────────────────────────────────────┐   │
│  │     Kafka Broker (Message Queue)           │   │
│  │     Topics: ocr-jobs, ai-processing        │   │
│  │     :9092 (INTERNAL ONLY)                  │   │
│  └────────────────────────────────────────────┘   │
│         ↓                ↓                ↓        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │
│  │  PostgreSQL  │  │   MongoDB    │  │Zookeeper │ │
│  │  :5432       │  │  :27017      │  │ :2181    │ │
│  └──────────────┘  └──────────────┘  └──────────┘ │
│                                                     │
└─────────────────────────────────────────────────────┘
        ↓ (ONLY exposed)
    Port 8000 (API)
```

## Security Checklist

- ✅ **Kafka not exposed**: Internal network only
- ✅ **Credentials not in browser**: Stored server-side
- ✅ **Rate limiting implemented**: Protects Groq API
- ✅ **File validation**: Size limits, content checks
- ✅ **Async pattern**: Non-blocking, scalable
- ✅ **Error handling**: Logging, retries, graceful failures
- ✅ **Health checks**: All services monitored
- ✅ **Data persistence**: Volumes for DB and Kafka
- ✅ **CORS configured**: Only safe origins
- ✅ **Background tasks**: Non-blocking Kafka sends

## Monitoring & Debugging

### Check API Health
```bash
curl http://localhost:8000/health
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f ai_worker
docker-compose logs -f ocr_worker
docker-compose logs -f backend
```

### Monitor Kafka Topics
```bash
# List topics
docker-compose exec kafka kafka-topics --list --bootstrap-server localhost:9092

# Check topic messages
docker-compose exec kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic ocr-jobs --from-beginning
```

## Performance Metrics

| Metric | Value | Notes |
|--------|-------|-------|
| Ingestion Rate | 50/min | API level (configurable) |
| OCR Throughput | 1-2/min | Depends on file size |
| AI Processing | 5/min | 20 RPM Groq limit ÷ 4 tasks |
| Response Time (API) | 200ms | 202 Accepted |
| OCR Duration | 2-5s | Per essay |
| AI Analysis Duration | 15-30s | 4 parallel calls |
| **End-to-end** | 20-40s | OCR + AI combined |

## Future Enhancements

- [ ] WebSocket for real-time status updates
- [ ] Vector DB (Chroma) for fact-checking
- [ ] Multi-model support (Claude, GPT)
- [ ] Redis cache for frequent queries
- [ ] S3 file storage instead of file_hex
- [ ] Email notifications on completion
- [ ] Dashboard with metrics
- [ ] User authentication & API keys
