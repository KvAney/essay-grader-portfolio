# Installation & Deployment Guide - v2.0

## Prerequisites

- Docker & Docker Compose (v1.29+)
- Groq API Key (free at [console.groq.com](https://console.groq.com))
- Git (optional, for cloning)
- 4GB RAM minimum, 8GB recommended

## Quick Start (3 Steps)

### Step 1: Get Your Groq API Key

1. Visit [console.groq.com](https://console.groq.com)
2. Sign up / Log in
3. Create new API key
4. Copy the key (starts with `gsk_`)

### Step 2: Configure Environment

```bash
cd essay-grader-portfolio/backend
# Edit .env file with your key
GROQ_API_KEY=gsk_YOUR_KEY_HERE
```

### Step 3: Start All Services

```bash
cd essay-grader-portfolio
docker-compose up --build
```

Wait for all services to be healthy (~30 seconds):
```
✓ backend        - Ready at http://localhost:8000
✓ postgres_db    - Ready on port 5432
✓ mongo_db       - Ready on port 27017
✓ kafka          - Ready on port 9092
✓ ocr_worker     - Ready (consuming ocr-jobs)
✓ ai_worker      - Ready (consuming ai-processing)
```

## Testing the System

### Method 1: Swagger UI (Easiest)

1. Open browser: http://localhost:8000/docs
2. Click "Try it out" on `/upload/` endpoint
3. Choose a text file (or create one)
4. Click "Execute"
5. Copy the `submission_id` from response
6. Go to `/status/{submission_id}` endpoint
7. Click "Try it out" → paste submission_id → Execute
8. Refresh every 5 seconds until status is "completed"

### Method 2: cURL

```bash
# 1. Upload file
curl -X POST http://localhost:8000/upload/ \
  -F "file=@essay.txt"

# Response:
# {
#   "submission_id": 1,
#   "status": "queued",
#   "message": "Essay queued for processing..."
# }

# 2. Check status (replace 1 with your submission_id)
curl http://localhost:8000/status/1

# 3. List all submissions
curl http://localhost:8000/submissions/

# 4. Health check
curl http://localhost:8000/health
```

### Method 3: Frontend (React)

```bash
cd frontend
npm install
npm start
```

Visit http://localhost:3000

## Monitoring & Debugging

### View Service Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f ai_worker
docker-compose logs -f ocr_worker

# Follow logs from all workers
docker-compose logs -f ocr_worker ai_worker
```

### Check Service Health

```bash
# List running services
docker-compose ps

# Verify API is working
curl http://localhost:8000/health

# Check database connections
docker-compose exec postgres_db psql -U user -d essay_eval_db -c "SELECT * FROM submissions;"

# Check MongoDB
docker-compose exec mongo_db mongo essay_eval_db --eval "db.evaluations.find().limit(1);"
```

### Kafka Diagnostics

```bash
# List topics
docker-compose exec kafka kafka-topics \
  --list \
  --bootstrap-server kafka:9092

# Create topics manually (if needed)
docker-compose exec kafka kafka-topics \
  --create \
  --topic ocr-jobs \
  --partitions 1 \
  --replication-factor 1 \
  --bootstrap-server kafka:9092

# Monitor topic messages
docker-compose exec kafka kafka-console-consumer \
  --bootstrap-server kafka:9092 \
  --topic ocr-jobs \
  --from-beginning
```

## Performance Tuning

### Increase Processing Speed

Edit `docker-compose.yml` and add environment variables:

```yaml
ai_worker:
  environment:
    - GROQ_RATE_LIMIT=25  # Increase from 20 if Groq allows
    - AI_TIMEOUT=600      # Timeout for AI tasks (seconds)
```

### Increase Ingestion Capacity

Edit `backend/app/main.py`:

```python
# Current: 50 uploads/min
ingestion_rate_limiter = TokenBucketRateLimiter(rate=50, per=60)

# Change to (example):
ingestion_rate_limiter = TokenBucketRateLimiter(rate=100, per=60)  # 100/min
```

### Database Performance

```bash
# Create indexes for faster queries
docker-compose exec postgres_db psql -U user -d essay_eval_db -c "
CREATE INDEX idx_submissions_status ON submissions(status);
CREATE INDEX idx_submissions_created_at ON submissions(created_at DESC);
"
```

## Troubleshooting

### Issue: "Kafka Connection Refused"

**Symptoms:** 
- OCR/AI workers won't start
- Error: `Cannot connect to kafka:9092`

**Solution:**
```bash
# Wait for Kafka to fully start (takes ~15 seconds)
docker-compose restart ocr_worker ai_worker

# Or, check Kafka logs
docker-compose logs kafka
```

### Issue: "Groq API Error 429 (Too Many Requests)"

**Symptoms:**
- AI analysis fails with `RateLimitError`

**Solution:**
- Your `GROQ_API_KEY` may be on free tier with 20 RPM limit
- Current system is tuned for 20 RPM
- If you upgrade to paid, increase in `.env`:
  ```
  GROQ_RATE_LIMIT=100  # or higher
  ```

### Issue: "Port Already in Use"

**Symptoms:**
- Error: `Port 8000 already in use`

**Solution:**
```bash
# Find process using port
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# Stop using that port
docker-compose down

# Or change port in docker-compose.yml
# Change "8000:8000" to "8001:8000" etc.
```

### Issue: "MongoDB Connection Timeout"

**Symptoms:**
- Error: `connection refused` to mongo_db:27017

**Solution:**
```bash
# Restart MongoDB
docker-compose restart mongo_db

# Wait 10 seconds, then check
docker-compose logs mongo_db

# Verify it's running
docker-compose exec mongo_db mongo --eval "db.adminCommand('ping')"
```

### Issue: "Postgres Connection Failed"

**Symptoms:**
- Error: `psycopg2.OperationalError`

**Solution:**
```bash
# Check if Postgres is running
docker-compose exec postgres_db pg_isready

# Restart Postgres
docker-compose restart postgres_db

# Check logs
docker-compose logs postgres_db

# Verify credentials match in .env
```

### Issue: "Workers Not Processing Messages"

**Symptoms:**
- Messages stuck in Kafka
- Workers not progressing

**Solution:**
```bash
# Check worker logs
docker-compose logs -f ocr_worker

# Restart workers
docker-compose restart ocr_worker ai_worker

# Check Kafka consumer groups
docker-compose exec kafka kafka-consumer-groups \
  --bootstrap-server kafka:9092 \
  --list
```

## Production Deployment

### Before Going Live

1. **Update .env**
   ```env
   GROQ_API_KEY=gsk_YOUR_PRODUCTION_KEY  # Use production key
   INGESTION_RATE_LIMIT=100              # Adjust based on load
   ```

2. **Database Backups**
   ```bash
   # Export Postgres
   docker-compose exec postgres_db pg_dump -U user essay_eval_db > backup.sql
   
   # Export MongoDB
   docker-compose exec mongo_db mongodump --out /backup
   ```

3. **CORS Configuration**
   Update in `docker-compose.yml`:
   ```yaml
   CORS_ORIGINS=https://yourdomain.com,https://api.yourdomain.com
   ```

4. **Set Resource Limits**
   ```yaml
   services:
     backend:
       deploy:
         resources:
           limits:
             cpus: '2'
             memory: 2G
     ai_worker:
       deploy:
         resources:
           limits:
             cpus: '2'
             memory: 2G
   ```

### Scale Horizontally

Run multiple AI workers:

```bash
# Scale to 3 AI workers
docker-compose up --scale ai_worker=3

# They share the same consumer group
# Messages distributed automatically
```

### Monitoring

Install monitoring stack (optional):

```bash
# Add to docker-compose.yml
prometheus:
  image: prom/prometheus
  ports:
    - "9090:9090"

grafana:
  image: grafana/grafana
  ports:
    - "3000:3000"
```

## Maintenance

### Clean Up

```bash
# Stop all services
docker-compose down

# Remove volumes (WARNING: Deletes all data)
docker-compose down -v

# Remove unused images
docker image prune -a
```

### Update Code

```bash
# Pull latest
git pull origin main

# Rebuild containers
docker-compose up --build

# Apply migrations (if any)
docker-compose exec backend alembic upgrade head
```

### Backup Strategy

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="./backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p $BACKUP_DIR

# Postgres
docker-compose exec -T postgres_db pg_dump -U user essay_eval_db \
  > $BACKUP_DIR/postgres.sql

# MongoDB
docker-compose exec -T mongo_db mongodump \
  --out $BACKUP_DIR/mongo

echo "Backup saved to: $BACKUP_DIR"
```

## Support & Documentation

- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health
- **Groq Docs**: https://console.groq.com/docs
- **Architecture Guide**: [SECURITY_AND_ARCHITECTURE.md](SECURITY_AND_ARCHITECTURE.md)
- **Project README**: [README.md](README.md)
