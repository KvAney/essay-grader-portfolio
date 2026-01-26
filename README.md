# Essay Grader Portfolio Project

A comprehensive essay grading system using Hybrid Architecture (PostgreSQL + MongoDB + Kafka) with AI-powered evaluation via Groq.

## Architecture Overview

```
Frontend (React) → Backend API (FastAPI) → Kafka Message Queue
                                            ├── OCR Worker → MongoDB
                                            └── AI Worker (Groq) → MongoDB
                        
PostgreSQL (Metadata)
```

## Features

- **File Upload**: Upload essays in PDF or text format
- **OCR Processing**: Extract text from documents using Tesseract
- **AI Grading**: Evaluate essays using Groq's LLaMA model
- **Real-time Status**: Track submission status in real-time
- **Scalable Architecture**: Kafka-based message queue for async processing

## Tech Stack

### Backend
- **Framework**: FastAPI
- **Databases**: PostgreSQL (relational), MongoDB (document store)
- **Message Broker**: Apache Kafka
- **AI API**: Groq (LLaMA 3 70B)
- **OCR**: Tesseract

### Frontend
- **Framework**: React 18
- **HTTP Client**: Axios

### Infrastructure
- **Containerization**: Docker & Docker Compose
- **Services**: Zookeeper, Kafka, PostgreSQL, MongoDB

## Project Structure

```
essay-grader-portfolio/
├── docker-compose.yml           # Infrastructure setup
├── backend/
│   ├── Dockerfile              # Backend container
│   ├── requirements.txt         # Python dependencies
│   ├── .env                     # Environment variables
│   └── app/
│       ├── __init__.py
│       ├── main.py              # FastAPI application
│       ├── core/
│       │   └── config.py         # Configuration
│       ├── db/
│       │   ├── postgres.py       # PostgreSQL connection
│       │   ├── mongo.py          # MongoDB connection
│       │   └── models.py         # Database models
│       ├── services/
│       │   ├── ocr.py            # OCR processing
│       │   └── ai_agents.py      # Groq AI integration
│       └── workers/
│           ├── ocr_worker.py     # Kafka consumer 1
│           └── ai_worker.py      # Kafka consumer 2
└── frontend/
    ├── package.json
    ├── public/
    │   └── index.html
    └── src/
        ├── App.jsx
        ├── App.css
        ├── index.js
        └── index.css
```

## Setup Instructions

### Prerequisites

- Docker & Docker Compose installed
- Node.js 14+ (for frontend development)
- Groq API key from [console.groq.com](https://console.groq.com)

### 1. Create .env file

Create `backend/.env`:

```env
GROQ_API_KEY=gsk_YOUR_API_KEY_HERE
DATABASE_URL=postgresql://postgres:ppt@postgres_db:5432/essay_eval_db
MONGO_URL=mongodb://mongo_db:27017
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
```

### 2. Start Services

```bash
cd essay-grader-portfolio
docker-compose up --build
```

This will start:
- PostgreSQL on port 5432
- MongoDB on port 27017
- Kafka on port 9092
- FastAPI backend on port 8000

### 3. Test the API

Open browser and go to: `http://localhost:8000/docs`

**Test Endpoints:**

1. **Upload Essay**
   - POST `/upload/`
   - Upload a text file or PDF
   - Response: `{"submission_id": 1, "status": "Queued for OCR"}`

2. **Check Status**
   - GET `/status/{submission_id}`
   - Response: `{"status": "completed", "result": "...AI evaluation..."}`

3. **List All Submissions**
   - GET `/submissions/`

### 4. Frontend (Optional)

```bash
cd frontend
npm install
npm start
```

Visit `http://localhost:3000`

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| POST | `/upload/` | Upload essay file |
| GET | `/status/{submission_id}` | Get submission status |
| GET | `/submissions/` | List all submissions |

## Kafka Topics

| Topic | Producer | Consumer | Purpose |
|-------|----------|----------|---------|
| `ocr-jobs` | API Gateway | OCR Worker | Initial processing queue |
| `ai-processing` | OCR Worker | AI Worker | AI evaluation queue |

## Database Schema

### PostgreSQL (submissions table)

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER (PK) | Submission ID |
| filename | STRING | Original filename |
| status | STRING | Current status |
| mongo_id | STRING | Link to MongoDB document |
| created_at | DATETIME | Timestamp |

### MongoDB (evaluations collection)

```json
{
  "_id": "ObjectId",
  "submission_id": 1,
  "text": "Extracted essay text...",
  "ai_result": "Grade and feedback...",
  "status": "completed",
  "created_at": "timestamp"
}
```

## Status Flow

1. **queued** → File uploaded, waiting for OCR
2. **ocr_completed** → Text extracted, waiting for AI analysis
3. **completed** → AI evaluation done, result available

## Environment Variables

- `GROQ_API_KEY`: Your Groq API key
- `DATABASE_URL`: PostgreSQL connection string
- `MONGO_URL`: MongoDB connection string
- `KAFKA_BOOTSTRAP_SERVERS`: Kafka broker address
- `OCR_TOPIC`: Kafka topic for OCR jobs
- `AI_TOPIC`: Kafka topic for AI processing

## Rate Limiting

Groq Free Tier: 20 requests per minute

To enable rate limiting in `ai_worker.py`, uncomment:
```python
time.sleep(3)  # Throttle to ~20 RPM
```

## Troubleshooting

### Kafka Connection Issues
- Ensure `KAFKA_BOOTSTRAP_SERVERS` is set correctly
- For Docker: use `kafka:9092` (internal)
- For local: use `localhost:9092`

### OCR Not Working
- Install Tesseract: `apt-get install tesseract-ocr`
- Currently using mock OCR for demo

### MongoDB Connection
- Check MongoDB is running: `docker ps | grep mongo`
- Verify connection string in `.env`

## Future Enhancements

- [ ] Real Tesseract OCR integration
- [ ] S3 file storage instead of inline hex
- [ ] Email notifications
- [ ] User authentication
- [ ] Advanced grading rubrics
- [ ] Multiple AI models support
- [ ] Result caching

## License

MIT

## Support

For issues, create a GitHub issue or contact the maintainer.
