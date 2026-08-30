# Scholar Agent

Scholar Agent is a full-stack academic research tool that takes a research topic and automatically produces a structured literature review. You submit a topic through the React web interface; the FastAPI backend kicks off a 10-agent Google ADK pipeline that searches multiple academic databases, retrieves and summarizes papers, clusters them into themes, identifies research gaps, writes the review sections, formats citations, and delivers a finished document — all without manual intervention.

## Architecture

The application is a React SPA that talks to a FastAPI backend over a REST/polling API. The backend orchestrates a sequential 10-agent pipeline built on the Google Agent Development Kit (ADK), with each agent responsible for a single stage of the literature review workflow. Academic sources covered are arXiv, Semantic Scholar, IEEE Xplore, and Google Scholar (via SerpAPI or the `scholarly` fallback).

**The 10 pipeline agents:**

| # | Agent | Role |
|---|-------|------|
| 1 | Topic Understanding | Parses the user's topic and generates targeted search queries |
| 2 | Paper Search | Queries arXiv, Semantic Scholar, IEEE Xplore, and Google Scholar |
| 3 | PDF Retrieval | Downloads full-text PDFs where available; falls back to abstracts |
| 4 | Summarization | Generates per-paper micro-summaries using Gemini |
| 5 | Thematic Clustering | Groups papers into coherent research themes |
| 6 | Comparative Analysis | Analyses similarities and differences across papers |
| 7 | Gap Identification | Surfaces open research questions not addressed by the literature |
| 8 | Review Writer | Drafts all review sections (introduction, analysis, gaps, conclusion) |
| 9 | Citation Formatter | Formats bibliography in APA, MLA, Chicago, or IEEE style |
| 10 | Output Generator | Assembles the final structured review document |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- API keys (see [Required API Keys](#required-api-keys))

### Backend Setup

```bash
cd backend

# Create and activate a virtual environment
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt

cp ../.env.example .env
# Edit .env and fill in your API keys

uvicorn main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
echo "VITE_API_URL=http://localhost:8000" > .env.local
npm run dev
```

Open http://localhost:5173

## Required API Keys

| Key | Required | Where to Get |
|-----|----------|--------------|
| `GOOGLE_API_KEY` | Yes | https://aistudio.google.com/app/apikey |
| `IEEE_API_KEY` | No | https://developer.ieee.org |
| `SEMANTIC_SCHOLAR_API_KEY` | No | https://api.semanticscholar.org |
| `SERPAPI_KEY` | No | https://serpapi.com (fallback to `scholarly` if absent) |

Only `GOOGLE_API_KEY` is required. The pipeline degrades gracefully when optional keys are missing — it skips sources that need them and continues with what is available.

## Project Structure

```
literature-review-web-app/
├── backend/
│   ├── agents/          # 10 specialized agents + orchestrator
│   ├── tools/           # Search tools, PDF extractor, clustering, formatters
│   ├── models/          # Pydantic + dataclass models (api, job, paper)
│   ├── services/        # JobManager, PipelineRunner, CacheService
│   ├── config/          # Settings (pydantic-settings), logging config
│   ├── utils/           # Retry logic, deduplication, correlation ID
│   ├── api/             # FastAPI routes + middleware
│   │   └── routes/      # /reviews, /jobs, /health endpoints
│   ├── tests/
│   │   ├── unit/        # Per-module unit tests
│   │   ├── property/    # Hypothesis property-based tests
│   │   └── integration/ # End-to-end pipeline tests
│   ├── requirements.txt
│   └── main.py          # App entry point
└── frontend/
    └── src/
        ├── api/         # Typed axios client
        ├── components/  # TopicForm, ProgressTracker, ResultsViewer, ErrorBanner
        └── hooks/       # useJobPoller
```

## Running Tests

```bash
cd backend
pytest --cov=. --cov-report=term-missing
```

To run only unit or property tests:

```bash
pytest tests/unit/
pytest tests/property/
```

## API Documentation

Interactive Swagger UI is auto-generated and available at http://localhost:8000/docs once the backend is running.
