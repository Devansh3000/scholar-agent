# Deployment Guide

## Manual Deployment (Without Docker)

### Backend (Production)

```bash
cd backend

python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate.bat

pip install -r requirements.txt
```

Set all environment variables directly — do not use a `.env` file in production:

```bash
export GOOGLE_API_KEY=your-key
export IEEE_API_KEY=your-key
export SEMANTIC_SCHOLAR_API_KEY=your-key
export SERPAPI_KEY=your-key
export REDIS_URL=redis://your-redis-host:6379
export ENVIRONMENT=production
export LOG_LEVEL=WARNING
export MAX_CONCURRENT_JOBS=20
export CORS_ORIGINS='["https://your-frontend-domain.com"]'
```

Run with multiple workers (recommended: 1 worker per CPU core):

```bash
# Option A: uvicorn directly
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

# Option B: gunicorn + uvicorn worker class
pip install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Frontend (Production)

Set the production API URL before building:

```bash
cd frontend
echo "VITE_API_URL=https://your-backend-domain.com" > .env.production
npm install
npm run build
# Output: frontend/dist/
```

Serve `frontend/dist/` with any static file server. Example nginx config:

```nginx
server {
    listen 80;
    server_name your-frontend-domain.com;
    root /var/www/scholar-agent/dist;
    index index.html;

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

---

## Cloud Deployment

### Google Cloud Run (Backend)

Cloud Run supports deploying directly from source using a `Procfile` or `Dockerfile`. Without Docker, use the source-based deploy:

```bash
# From the backend/ directory
gcloud run deploy scholar-agent-backend \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8000 \
  --memory 2Gi \
  --set-env-vars GOOGLE_API_KEY=...,ENVIRONMENT=production,LOG_LEVEL=WARNING
```

Set remaining secrets via Secret Manager:

```bash
gcloud secrets create ieee-api-key --data-file=- <<< "your-ieee-key"
gcloud run services update scholar-agent-backend \
  --update-secrets IEEE_API_KEY=ieee-api-key:latest
```

### Frontend (Static Hosting)

Build locally with the Cloud Run URL as the API base:

```bash
VITE_API_URL=https://scholar-agent-backend-xxx.run.app npm run build
```

Deploy to **Firebase Hosting**:
```bash
npm install -g firebase-tools
firebase init hosting   # set public dir to frontend/dist, SPA rewrite yes
firebase deploy
```

Or deploy to **Vercel** (auto-detects Vite):
```bash
npx vercel --cwd frontend
```

Or deploy to **Netlify**:
```bash
npx netlify-cli deploy --dir frontend/dist --prod
```

### Vertex AI Agent Engine

The Google ADK agents are compatible with Vertex AI Agent Engine. To deploy:

1. Set `GOOGLE_GENAI_USE_VERTEXAI=TRUE` in environment variables.
2. Configure a Google Cloud project with Vertex AI API enabled.
3. Follow the [Vertex AI Agent Engine deployment guide](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/deploy).

---

## Redis (Production)

Do not use the in-memory fallback in production — it does not persist across restarts.

| Provider | Notes |
|---|---|
| Google Cloud Memorystore | Fully managed Redis in GCP |
| AWS ElastiCache | Managed Redis on AWS |
| Redis Cloud | Managed Redis, any cloud |
| Self-hosted | `redis-server` on a VM or container |

Set `REDIS_URL` to the connection string, e.g.:

```
REDIS_URL=redis://:password@your-redis-host:6379/0
```

---

## PDF Output Storage

The default PDF output directory is `/tmp/reviews`. This is **ephemeral** in serverless environments (Cloud Run, Lambda) and in-memory in Docker unless a volume is mounted.

For persistent PDF storage, either:

- Mount a persistent volume at `/tmp/reviews`
- Override the output directory: set `OUTPUT_DIR` env var and update `agents/output_generator.py` accordingly
- Deliver PDFs directly to Cloud Storage / S3 and return a signed URL

---

## Resource Recommendations

| Component | Minimum | Recommended |
|---|---|---|
| Backend RAM per worker | 1 GB | 2 GB |
| Backend CPU per worker | 1 vCPU | 2 vCPU |
| Workers | 1 | 1 per CPU core |
| Redis memory | 256 MB | 1 GB |

The clustering/embedding steps (Agent 5) are the most memory-intensive. If using `max_papers=50`, allocate at least 2 GB RAM per worker.
