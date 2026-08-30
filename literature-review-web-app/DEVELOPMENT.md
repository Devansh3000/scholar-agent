# Development Guide

## Prerequisites

- Python 3.11 or 3.12 (Python 3.13 has a known incompatibility with `aioredis` — see [Common Issues](#common-issues))
- Node.js 20+
- Git
- Redis (optional — the app falls back to in-memory cache if Redis is unavailable)

---

## Environment Variables

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

The only **required** variable is `GOOGLE_API_KEY`. Everything else has a working default.

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_API_KEY` | Yes | — | Gemini API key for all LLM calls. Get one at [aistudio.google.com](https://aistudio.google.com/app/apikey). |
| `IEEE_API_KEY` | No | — | IEEE Xplore API key. If absent, IEEE is skipped as a search source. |
| `SEMANTIC_SCHOLAR_API_KEY` | No | — | Semantic Scholar key. Improves rate limits; falls back to unauthenticated tier. |
| `SERPAPI_KEY` | No | — | Reliable Google Scholar search. If absent, falls back to `scholarly` (may be blocked). |
| `REDIS_URL` | No | `redis://localhost:6379` | Redis connection URL. Falls back to in-memory cache if unreachable. |
| `DATABASE_URL` | No | — | PostgreSQL URL for persistent storage. Leave empty for in-memory only. |
| `LOG_LEVEL` | No | `INFO` | Log verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `CORS_ORIGINS` | No | `["http://localhost:3000","http://localhost:5173"]` | JSON array of allowed frontend origins. |
| `MAX_CONCURRENT_JOBS` | No | `10` | Max simultaneous pipeline jobs. |
| `ENVIRONMENT` | No | `development` | `development`, `staging`, or `production`. |

---

## Backend Setup

### Windows

```bat
cd literature-review-web-app\backend

REM Create and activate the virtual environment, then install dependencies
setup_venv.bat

REM Activate for subsequent sessions
venv\Scripts\activate.bat
```

### Linux / macOS

```bash
cd literature-review-web-app/backend

# Create and activate the virtual environment, then install dependencies
chmod +x setup_venv.sh
./setup_venv.sh

# Activate for subsequent sessions
source venv/bin/activate
```

### Manual setup (any platform)

```bash
cd literature-review-web-app/backend
python -m venv venv

# Windows
venv\Scripts\activate.bat

# Linux / macOS
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

---

## Running the Backend

From `literature-review-web-app/backend` with the venv activated:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API is available at `http://localhost:8000`. The interactive docs are at `http://localhost:8000/docs`.

To verify the server is running:

```bash
curl http://localhost:8000/api/health
# {"status": "ok", "version": "1.0.0"}
```

---

## Running Tests

From `literature-review-web-app/backend` with the venv activated:

```bash
# Run all tests with coverage report
pytest --cov=. --cov-report=term-missing

# Run only unit tests
pytest tests/unit/

# Run only property-based tests
pytest tests/property/

# Run only integration tests
pytest tests/integration/

# Run a specific test file
pytest tests/unit/test_retry.py -v
```

Example output:

```
========================= test session starts ==========================
platform win32 -- Python 3.11.9, pytest-8.3.3
collected 47 items

tests/unit/test_deduplication.py ....                             [  8%]
tests/unit/test_retry.py .......                                  [ 23%]
tests/unit/test_cache_service.py .....                            [ 34%]
tests/property/test_job_id_uniqueness.py .                        [ 36%]
tests/property/test_deduplication.py .                            [ 38%]
tests/property/test_progress.py .                                 [ 40%]
tests/integration/test_api.py ..............                      [ 70%]
...

---------- coverage: platform win32, python 3.11.9 ----------
TOTAL                                          1842    412    78%

========================= 47 passed in 12.34s ==========================
```

Coverage must stay at or above 70% (`pytest-cov` enforces this in CI).

---

## Running the Frontend

```bash
cd literature-review-web-app/frontend
npm install
npm run dev
```

The dev server starts at `http://localhost:5173` (Vite default). It proxies API requests to `http://localhost:8000`.

To run frontend tests:

```bash
npm test
```

To build for production:

```bash
npm run build
# Output goes to frontend/dist/
```

---

## Common Issues

### Missing `GOOGLE_API_KEY`

The backend will start but every pipeline job will fail at Agent 1 (Topic Understanding) with a Gemini authentication error. Set `GOOGLE_API_KEY` in your `.env` file before submitting any review jobs.

```
AuthenticationError: GOOGLE_API_KEY is not set or invalid
```

### `aioredis` incompatibility on Python 3.13

`aioredis==2.0.1` (in `requirements.txt`) does not support Python 3.13 due to the removal of `asyncio.coroutines.coroutine` in that release. Use Python 3.11 or 3.12, or replace `aioredis` with `redis[asyncio]`:

```bash
pip uninstall aioredis
pip install "redis[asyncio]==5.0.8"
```

Then update the import in `services/cache_service.py` from `import aioredis` to `from redis.asyncio import Redis`.

### `scholarly` rate limiting / Google blocking

The `scholarly` library scrapes Google Scholar and is frequently blocked by Google's bot detection, especially in CI or cloud environments. If you see repeated `MaxTriesExceedException` errors from `scholarly`, set a `SERPAPI_KEY` in your `.env` to use the SerpAPI backend instead. The paper search adapter will automatically prefer SerpAPI when the key is present.

### Redis connection refused

If Redis is not running, the cache service falls back to in-memory storage automatically — the app will still work. You will see a warning in the logs:

```
WARNING  cache_service: Redis unavailable, using in-memory cache
```

To start Redis locally (if installed):

```bash
# Linux / macOS
redis-server

# Windows (via WSL or Docker)
docker run -p 6379:6379 redis:7-alpine
```

### Port already in use

If port 8000 is taken, specify a different port:

```bash
uvicorn main:app --reload --port 8001
```

Update `CORS_ORIGINS` in `.env` if you also changed the frontend port.

---

## Troubleshooting

**Is the backend running?**

```bash
curl http://localhost:8000/api/health
```

A `200 {"status": "ok"}` response confirms the server is up. A connection refused error means uvicorn is not running or is on a different port.

**Check logs for a specific job:**

The backend logs include the `job_id` and `correlation_id` on every line related to a pipeline run. Filter by job ID:

```bash
# If running with default stdout logging
uvicorn main:app --reload 2>&1 | grep <job_id>
```

**Increase log verbosity:**

Set `LOG_LEVEL=DEBUG` in `.env` and restart the server. This emits per-agent timing, cache hit/miss events, and full exception tracebacks.
