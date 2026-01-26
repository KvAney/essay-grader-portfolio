# Data Flow Diagrams - Essay Grader v2.0

## 1. Upload Flow (Stage 1: Ingestion)

```
User Action: Click "Upload" on Frontend
                       ↓
        ┌──────────────────────────┐
        │  Browser Sends File      │
        │  POST /upload/           │
        │  file=essay.txt          │
        └──────────┬───────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  API Gateway (main.py)           │
        │  ├─ Receive file                 │
        │  ├─ Validate (size, type)        │
        │  ├─ Rate limit check (50/min)    │
        │  └─ ✓ Pass                       │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  PostgreSQL                      │
        │  INSERT INTO submissions:        │
        │  {                               │
        │    id: 1,                        │
        │    filename: 'essay.txt',        │
        │    status: 'queued',             │
        │    created_at: now()             │
        │  }                               │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  Background Task (async)         │
        │  Produce to Kafka (don't wait)   │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  Kafka Topic: ocr-jobs           │
        │  {                               │
        │    submission_id: 1,             │
        │    filename: 'essay.txt',        │
        │    file_hex: "abc123...",        │
        │    timestamp: 1234567890         │
        │  }                               │
        │  Size: ~5MB                      │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  Return to Browser (202)         │
        │  {                               │
        │    "submission_id": 1,           │
        │    "status": "queued",           │
        │    "message": "Processing..."    │
        │  }                               │
        └──────────────────────────────────┘
        
Time: ~200ms (user sees instant response!)
```

---

## 2. OCR Processing Flow (Stage 2)

```
Kafka Consumer: ocr-group
Listens to: ocr-jobs topic
                   ↓
        ┌──────────────────────────────────┐
        │  OCR Worker receives message     │
        │  submission_id: 1                │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  Extract text from file_hex      │
        │  (Mock OCR - returns demo text)  │
        │  Result: "Democracy is a..."     │
        │  Length: ~5MB                    │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  MongoDB: Insert Document        │
        │  Collection: evaluations         │
        │  {                               │
        │    _id: ObjectId("abc..."),      │
        │    submission_id: 1,             │
        │    filename: 'essay.txt',        │
        │    text: "Democracy is a...",    │
        │    status: 'ocr_completed',      │
        │    ocr_time: 3.2,                │
        │    created_at: timestamp         │
        │  }                               │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  PostgreSQL: Update Status       │
        │  UPDATE submissions SET          │
        │  status = 'ocr_completed',       │
        │  mongo_id = 'ObjectId(...)'      │
        │  WHERE id = 1                    │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  Produce to Kafka (Claim Check)  │
        │  Topic: ai-processing            │
        │  {                               │
        │    submission_id: 1,             │
        │    mongo_id: "ObjectId(...)",    │ <-- Reference only!
        │    filename: 'essay.txt'         │     Size: <1KB
        │  }                               │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  Log completion                  │
        │  [ESSAY #1] ✓ OCR completed     │
        │  Queued for AI analysis          │
        └──────────────────────────────────┘

Time: ~2-5 seconds
MongoDB saves the heavy 5MB document
Kafka only carries the reference (< 1KB)
```

---

## 3. AI Orchestration Flow (Stage 3)

```
Kafka Consumer: ai-group
Listens to: ai-processing topic
                   ↓
        ┌──────────────────────────────────┐
        │  AI Worker receives message      │
        │  submission_id: 1                │
        │  mongo_id: "ObjectId(...)"       │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  PostgreSQL: Update Status       │
        │  UPDATE submissions SET          │
        │  status = 'ai_processing'        │
        │  WHERE id = 1                    │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  MongoDB: Fetch Document         │
        │  Find by _id = mongo_id          │
        │  Get: text = "Democracy is..."   │
        │  Length: 5MB                     │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────────────────────┐
        │        AI ORCHESTRATOR: Fan-Out Pattern          │
        │                                                  │
        │  Rate Limiter Check:                            │
        │  Current: 0/20 RPM → ✓ Proceed                 │
        │                                                  │
        │  Spawn 4 Parallel Tasks:                        │
        │                                                  │
        │  ┌─────────────┐ ┌─────────────┐               │
        │  │Grammar Task │ │Structure    │               │
        │  │  Groq Call  │ │Task Groq    │               │
        │  │  API #1     │ │Call API #2  │               │
        │  └─────────────┘ └─────────────┘               │
        │                                                  │
        │  ┌─────────────┐ ┌─────────────┐               │
        │  │Logic Task   │ │Content Task │               │
        │  │  Groq Call  │ │  Groq Call  │               │
        │  │  API #3     │ │  API #4     │               │
        │  └─────────────┘ └─────────────┘               │
        │                                                  │
        │  Awaits all 4 to complete (~3-5s each)        │
        │  But they run concurrently, not sequentially!  │
        │  Total time: ~5-10 seconds (not 15-20s)       │
        └──────────┬───────────────────────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  Aggregator: Combine Results     │
        │                                  │
        │  Result 1 (Grammar): 97/100      │
        │  Result 2 (Structure): 82/100    │
        │  Result 3 (Logic): 88/100        │
        │  Result 4 (Content): 79/100      │
        │                                  │
        │  Average: (97+82+88+79)/4 = 86.5 │
        │  Status: COMPLETED               │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  MongoDB: Update Document        │
        │  db.evaluations.update_one({     │
        │    _id: mongo_id                 │
        │  }, {                            │
        │    $set: {                       │
        │      status: 'completed',        │
        │      analysis_tasks: [...],      │
        │      aggregated_feedback: "...", │
        │      overall_score: 86.5,        │
        │      completion_time: 8.3        │
        │    }                             │
        │  })                              │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  PostgreSQL: Final Update        │
        │  UPDATE submissions SET          │
        │  status = 'completed'            │
        │  WHERE id = 1                    │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  Worker logs completion          │
        │  [ESSAY #1] ✓ ANALYSIS COMPLETE  │
        │  Score: 86.5/100                 │
        │  Ready for user query            │
        └──────────────────────────────────┘

Time: ~15-30 seconds (4 parallel tasks)
Rate Limit Used: 4/20 RPM
Remaining Capacity: 16/20 RPM (for next 4 tasks)
```

---

## 4. Status Check Flow

```
User Action: GET /status/1 from browser
                   ↓
        ┌──────────────────────────────────┐
        │  API Gateway checks request      │
        │  GET /status/1                   │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  PostgreSQL Query                │
        │  SELECT * FROM submissions       │
        │  WHERE id = 1                    │
        │                                  │
        │  Result:                         │
        │  {                               │
        │    id: 1,                        │
        │    filename: 'essay.txt',        │
        │    status: 'completed',          │
        │    mongo_id: 'ObjectId(...)'     │
        │  }                               │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  Check: status == 'completed'?   │
        │  ✓ Yes → Fetch full results      │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  MongoDB Query                   │
        │  db.evaluations.findOne({        │
        │    _id: ObjectId(mongo_id)       │
        │  })                              │
        │                                  │
        │  Returns: Complete analysis doc  │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────────────┐
        │  Format Response:                        │
        │  {                                       │
        │    "submission_id": 1,                   │
        │    "status": "completed",                │
        │    "analysis": [                         │
        │      {                                   │
        │        "task": "Grammar Analysis",       │
        │        "result": "97/100 - Excellent..." │
        │      },                                  │
        │      {                                   │
        │        "task": "Structure Analysis",     │
        │        "result": "82/100 - Good..."      │
        │      },                                  │
        │      ...                                 │
        │    ],                                    │
        │    "overall_score": 86.5,                │
        │    "aggregated_feedback": "..."          │
        │  }                                       │
        └──────────┬───────────────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  Return to Browser (200 OK)      │
        │  Display results to user         │
        └──────────────────────────────────┘

Time: ~100-200ms (just DB queries, no processing)
```

---

## 5. Rate Limiting Flow

```
Multiple Users Upload Simultaneously
                   ↓
        ┌──────────────────────────────────┐
        │  User 1: Upload essay            │
        │  Rate Limiter: 1/50 ✓            │
        │  Process: Queue to Kafka         │
        └──────────────────────────────────┘
        
        ┌──────────────────────────────────┐
        │  User 2-5: Upload essays         │
        │  Rate Limiter: 2-5/50 ✓          │
        │  Process: Queue to Kafka         │
        └──────────────────────────────────┘
        
        ┌──────────────────────────────────┐
        │  User 6-50: Upload essays        │
        │  Rate Limiter: 6-50/50 ✓         │
        │  Process: Queue to Kafka         │
        └──────────────────────────────────┘
        
        ┌──────────────────────────────────┐
        │  User 51: Upload essay           │
        │  Rate Limiter: 51/50 ✗           │
        │  Action: WAIT 1.2 seconds        │
        │  Then: Process                   │
        └──────────────────────────────────┘

All users get 202 Accepted responses immediately!
Kafka buffers excess messages
OCR Worker processes one-by-one
                   ↓
        ┌──────────────────────────────────┐
        │  Each essay → MongoDB (save)     │
        │  Each essay → Kafka: ai-process  │
        └──────────────────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  AI Worker receives from Kafka   │
        │  Rate Limit: 20 RPM              │
        │                                  │
        │  Scenario A:                     │
        │  Messages queued: 50/min         │
        │  Groq capacity: 20/min           │
        │  Result: Queue persists until    │
        │  system catches up (~5 min)      │
        │                                  │
        │  Scenario B:                     │
        │  Messages queued: 5/min          │
        │  Groq capacity: 20/min           │
        │  Result: Process instantly ✓     │
        └──────────────────────────────────┘

Key: Kafka acts as elastic buffer
No messages lost, no API crashes
Just slower processing during load spikes
```

---

## 6. Error Scenario Flow

```
Scenario: Groq API returns 429 (Rate Limit Error)
                   ↓
        ┌──────────────────────────────────┐
        │  AI Worker makes Groq call       │
        │  ✗ Response: 429 Too Many Req    │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  Exception handler catches it    │
        │  Logs error: "429 from Groq"     │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  Set error result in MongoDB:    │
        │  {                               │
        │    status: 'error',              │
        │    error_message: '429 Rate...',│
        │    retry_after: 60 (seconds)     │
        │  }                               │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  PostgreSQL: Mark as error       │
        │  status = 'error'                │
        └──────────┬───────────────────────┘
                   ↓
        ┌──────────────────────────────────┐
        │  Next message from Kafka:        │
        │  Will have better rate limit     │
        │  Token refilled for new attempt  │
        └──────────────────────────────────┘

System gracefully handles rate limit errors!
```

---

## Summary: Data Journey

```
┌─────────────────────────────────────────────────────────┐
│                  User's Essay Journey                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ 1. Upload (200ms)                                       │
│    Browser → API Gateway                               │
│    ✓ File validated                                    │
│    ✓ Stored in PostgreSQL (metadata)                   │
│    ✓ Queued to Kafka: ocr-jobs                        │
│    → User sees: "Processing..." immediately            │
│                                                         │
│ 2. OCR Processing (2-5s)                               │
│    Kafka → OCR Worker                                  │
│    ✓ Extract text                                      │
│    ✓ Stored in MongoDB (heavy data - 5MB)             │
│    ✓ Queued to Kafka: ai-processing (reference only)  │
│    → PostgreSQL: status = "ocr_completed"              │
│                                                         │
│ 3. AI Analysis (15-30s)                                │
│    Kafka → AI Worker (Orchestrator)                    │
│    ✓ Rate limited (20 RPM safe)                       │
│    ✓ 4 parallel Groq calls                             │
│    ✓ Aggregate results                                 │
│    ✓ Stored in MongoDB (analysis results)             │
│    → PostgreSQL: status = "completed"                  │
│                                                         │
│ Total Time: 20-40s from upload to complete results    │
│                                                         │
│ Result Retrieval:                                      │
│    User queries /status/1                              │
│    ✓ Fetch from PostgreSQL (metadata) - fast          │
│    ✓ If complete, fetch from MongoDB (analysis) - fast │
│    ✓ Return full analysis to user                     │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Key Patterns

### ✅ Async Pattern
```
Don't wait for async operations
Queue work → Return immediately → Process in background
Result: Non-blocking API, 202 Accepted responses
```

### ✅ Claim Check Pattern
```
Don't pass heavy data through message queues
Store in database → Pass reference in queue → Fetch when needed
Result: Kafka stays fast, scales to any file size
```

### ✅ Fan-Out Pattern
```
Don't do tasks sequentially
Spawn parallel tasks → Wait for all → Aggregate results
Result: 3x faster with same rate limit budget
```

### ✅ Rate Limiting Pattern
```
Don't let users exhaust API quota
Token bucket → Smooth distribution → Graceful queuing
Result: Fair access, no 429 errors, sustainable load
```
