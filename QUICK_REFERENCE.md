# Quick Reference - Essay Grader v2.0

## 🚀 Quick Start (Copy-Paste)

```bash
# 1. Navigate to project
cd essay-grader-portfolio

# 2. Edit backend/.env and add your Groq API key
# GROQ_API_KEY=gsk_YOUR_KEY_HERE

# 3. Start all services
docker-compose up --build

# 4. Open in browser
# API Docs: http://localhost:8000/docs
# Frontend: http://localhost:3000
```

---

## 📊 Architecture at a Glance

```
┌─────────────┐      ┌──────────┐      ┌─────────────┐      ┌────────────┐
│  Frontend   │─────→│   API    │─────→│  Kafka      │─────→│ Databases  │
│  (React)    │      │ Gateway  │      │ (Messages)  │      │ (PG, Mongo)│
└─────────────┘      └──────────┘      └─────────────┘      └────────────┘
                                              ↓
                                    ┌──────────────────────┐
                                    │  OCR Worker          │
                                    │  AI Orchestrator     │
                                    │  (with Groq API)     │
                                    └──────────────────────┘
```

---

## 🔑 Key Features

| Feature | Details |
|---------|---------|
| **Security** | Kafka internal only, credentials server-side |
| **Rate Limiting** | 20 RPM Groq, 50 uploads/min ingestion |
| **Scalability** | Handles 20+ concurrent users, queues excess |
| **Analysis** | 4 parallel AI tasks (Grammar, Structure, Logic, Content) |
| **Storage** | PostgreSQL (metadata) + MongoDB (essays) |
| **Performance** | ~5 essays/min, 15-40s per essay total |

---

## 📡 API Endpoints

### Upload Essay
```bash
POST /upload/
Content-Type: multipart/form-data

Response: 202 Accepted
{
  "submission_id": 1,
  "status": "queued"
}
```

### Check Status
```bash
GET /status/{submission_id}

Response: 200 OK
{
  "submission_id": 1,
  "status": "completed",
  "analysis": [...],
  "overall_score": 85,
  "aggregated_feedback": "..."
}
```

### List Submissions
```bash
GET /submissions/

Response: 200 OK
{
  "total": 10,
  "submissions": [...]
}
```

### Health Check
```bash
GET /health

Response: 200 OK
{
  "api": "healthy",
  "postgres": "healthy",
  "mongodb": "healthy",
  "kafka": "assumed healthy"
}
```

---

## 📝 Processing Stages

```
Stage 1: INGESTION (API Gateway)
  File Upload → Validation → Store in Postgres → Queue to Kafka
  Time: ~200ms
  Status: "queued"

Stage 2: OCR PROCESSING (OCR Worker)
  Fetch from Kafka → Extract text → Store in MongoDB → Queue next
  Time: ~2-5s
  Status: "ocr_completed"

Stage 3: AI ORCHESTRATION (AI Worker)
  Fetch from Kafka → Spawn 4 parallel AI tasks
  ├─ Grammar Analysis (Groq call)
  ├─ Structure Analysis (Groq call)
  ├─ Logic Analysis (Groq call)
  └─ Content Analysis (Groq call)
  Time: ~15-30s (parallel, not sequential)
  Status: "ai_processing" → "completed"
```

---

## 🛠️ Common Commands

### Start Services
```bash
docker-compose up --build
```

### Stop Services
```bash
docker-compose down
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

### Clean Everything
```bash
docker-compose down -v  # -v removes volumes (WARNING: deletes data)
```

### Rebuild Specific Service
```bash
docker-compose up --build backend
```

### Access Database
```bash
# PostgreSQL
docker-compose exec postgres_db psql -U user -d essay_eval_db

# MongoDB
docker-compose exec mongo_db mongo essay_eval_db
```

---

## 🔍 Monitoring

### Check Service Health
```bash
curl http://localhost:8000/health
```

### Check Kafka Topics
```bash
docker-compose exec kafka kafka-topics \
  --list --bootstrap-server kafka:9092
```

### Monitor Kafka Messages
```bash
docker-compose exec kafka kafka-console-consumer \
  --bootstrap-server kafka:9092 \
  --topic ocr-jobs \
  --from-beginning
```

### View Database Contents
```bash
# Submissions
docker-compose exec postgres_db psql -U user -d essay_eval_db \
  -c "SELECT * FROM submissions;"

# Evaluations
docker-compose exec mongo_db mongo essay_eval_db \
  --eval "db.evaluations.find().pretty();"
```

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| Port already in use | Change port in docker-compose.yml |
| Kafka won't start | Wait 15s, restart: `docker-compose restart kafka` |
| "429 Too Many Requests" | Groq rate limit hit, wait 30s, system auto-throttles |
| Workers not processing | Check logs: `docker-compose logs -f` |
| Database connection error | `docker-compose restart postgres_db` or `mongo_db` |
| CORS errors | Check CORS_ORIGINS in .env |

---

## 📊 Performance Expectations

| Metric | Value | Notes |
|--------|-------|-------|
| API Response | <200ms | Returns 202 immediately |
| OCR Processing | 2-5s | Per essay |
| AI Analysis | 15-30s | 4 parallel Groq calls |
| **Total Time** | 20-40s | End-to-end |
| **Throughput** | ~5 essays/min | Limited by 20 RPM Groq |
| **Max Concurrent Users** | 20+ | Excess queued in Kafka |

---

## 🎯 Rate Limiting

```python
# Ingestion (uploads)
Max: 50/min

# Groq API (AI calls)
Max: 20/min (free tier)
Each essay = 4 calls (Grammar, Structure, Logic, Content)
Capacity = 20 ÷ 4 = 5 essays/min

# System Behavior
- If <5 essays/min: Instant processing
- If >5 essays/min: Queued in Kafka, processed sequentially
- If messages arrive faster: Rate limiter blocks until capacity available
```

---

## 🔐 Security

✅ **What's Protected:**
- Kafka ports (internal only)
- API credentials (server-side)
- File uploads (validated)
- Database connections (credentials in .env)
- CORS (whitelist only)

❌ **What to Avoid:**
- Don't expose Kafka ports to internet
- Don't commit .env with real API keys
- Don't skip file size validation
- Don't run without CORS configuration

---

## 📚 Documentation Files

| File | Purpose |
|------|---------|
| [README.md](README.md) | Project overview |
| [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md) | Setup & deployment |
| [SECURITY_AND_ARCHITECTURE.md](SECURITY_AND_ARCHITECTURE.md) | Technical deep-dive |
| [IMPROVEMENTS_SUMMARY.md](IMPROVEMENTS_SUMMARY.md) | What changed v1→v2 |

---

## 🚀 Next Steps

1. Start services: `docker-compose up --build`
2. Test API: http://localhost:8000/docs
3. Upload sample essay
4. Check status endpoint
5. View results in `/status/{submission_id}`
6. Scale if needed or deploy to production

---

## 📞 Support

- 📖 Read docs first (90% of issues covered)
- 🔍 Check logs: `docker-compose logs -f`
- 🔗 Verify connectivity: `curl http://localhost:8000/health`
- 🛠️ Restart service: `docker-compose restart SERVICE_NAME`
- 💾 Backup before making changes

---

## 🎓 Learning Resources

- Async Python: https://docs.python.org/3/library/asyncio.html
- FastAPI: https://fastapi.tiangolo.com/
- Kafka: https://kafka.apache.org/
- Groq API: https://console.groq.com/docs
- Docker: https://docs.docker.com/

---

**Version:** 2.0 (Production Ready)
**Last Updated:** 2026-01-25
**Status:** ✅ All systems operational
