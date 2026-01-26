# Quickstart Guide

## One-Command Setup

```bash
# 1. Navigate to project
cd essay-grader-portfolio

# 2. Set your Groq API key (Windows PowerShell)
$env:GROQ_API_KEY="gsk_YOUR_KEY_HERE"

# 3. Start all services
docker-compose up --build
```

## Verify It's Working

### Terminal 1: Check services
```bash
docker-compose ps
```

### Terminal 2: Test API
```bash
# Health check
curl http://localhost:8000/

# Upload test file
curl -X POST http://localhost:8000/upload/ \
  -F "file=@test.txt"

# Check status (replace 1 with returned submission_id)
curl http://localhost:8000/status/1
```

## Expected Output Timeline

1. **Immediate**: Returns `submission_id: 1`
2. **5 seconds**: Status changes to `ocr_completed`
3. **10 seconds**: Status changes to `completed` with AI result

## Web UI

Open: http://localhost:8000/docs (Swagger UI)

## Logs

```bash
# View all logs
docker-compose logs -f

# View specific service
docker-compose logs -f backend
docker-compose logs -f kafka
```

## Stop Services

```bash
docker-compose down
# With cleanup
docker-compose down -v
```

## Common Issues & Fixes

**Issue**: Kafka not starting
- Fix: `docker-compose down -v && docker-compose up --build`

**Issue**: Port already in use (8000, 5432, etc)
- Fix: Edit `docker-compose.yml` and change ports, or stop other services

**Issue**: Groq API errors
- Fix: Verify API key in `.env` file

**Issue**: MongoDB connection refused
- Fix: Wait 10 seconds for MongoDB to start, then retry
