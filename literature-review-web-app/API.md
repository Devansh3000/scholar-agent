# API Reference

Base URL: `http://localhost:8000`

FastAPI auto-generates interactive docs at **http://localhost:8000/docs** (Swagger UI) and **http://localhost:8000/redoc** (ReDoc).

---

## Endpoints

### 1. POST /api/literature-review

Submit a new literature review job. Returns immediately with a job ID; the pipeline runs in the background.

**Request body**

```json
{
  "topic": "transformer architectures in natural language processing",
  "config": {
    "max_papers": 20,
    "search_depth": "medium",
    "citation_style": "APA",
    "include_pdfs": true
  }
}
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| `topic` | string | yes | 5–500 characters |
| `config.max_papers` | integer | no | 5–50, default `20` |
| `config.search_depth` | string | no | `"shallow"` \| `"medium"` \| `"deep"`, default `"medium"` |
| `config.citation_style` | string | no | `"APA"` \| `"Harvard"` \| `"IEEE"`, default `"APA"` |
| `config.include_pdfs` | boolean | no | default `true` |

**Response — 202 Accepted**

```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "estimated_seconds": 120
}
```

**Error responses**

| Status | Condition |
|---|---|
| 422 | Validation error (e.g. `topic` too short, `max_papers` out of range) |
| 503 | Server at capacity — retry after `Retry-After` header value (seconds) |

503 body:
```json
{
  "error": "Server at capacity",
  "retry_after": 30
}
```

---

### 2. GET /api/literature-review/{job_id}/status

Poll the progress of a running or completed job.

**Path parameter:** `job_id` — UUID returned by the submit endpoint.

**Response — 200 OK**

```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "running",
  "stage": "papers_fetched",
  "progress_pct": 45.0,
  "message": "Fetched 18 papers, starting summarisation",
  "elapsed_seconds": 38.2,
  "estimated_remaining_seconds": 82.0
}
```

| Field | Description |
|---|---|
| `status` | `pending` \| `running` \| `completed` \| `failed` \| `cancelled` |
| `stage` | Current pipeline stage name (e.g. `papers_fetched`, `themes_clustered`) |
| `progress_pct` | `0.0` – `100.0` |
| `estimated_remaining_seconds` | `null` when unknown (job not started or already finished) |

**Error responses**

| Status | Condition |
|---|---|
| 404 | Job ID not found |

---

### 3. GET /api/literature-review/{job_id}/result

Fetch the completed review. Only available once `status` is `completed`.

**Path parameter:** `job_id` — UUID returned by the submit endpoint.

**Response — 200 OK**

```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "completed_at": "2024-11-15T14:32:10.123456Z",
  "review": {
    "review_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "topic": "transformer architectures in natural language processing",
    "generated_at": "2024-11-15T14:32:10.123456Z",
    "citation_style": "APA",
    "paper_count": 20,
    "papers": [
      {
        "paper_id": "2310.12345",
        "title": "Attention Is All You Need",
        "authors": ["Vaswani, A.", "Shazeer, N."],
        "year": 2017,
        "journal": "Advances in Neural Information Processing Systems",
        "url": "https://arxiv.org/abs/1706.03762",
        "source": "arxiv",
        "doi": "10.48550/arXiv.1706.03762",
        "micro_summary": "Introduces the Transformer model based solely on attention mechanisms.",
        "theme_id": 1
      }
    ],
    "themes": [
      {
        "theme_id": 1,
        "label": "Self-Attention Mechanisms",
        "description": "Papers exploring the design and variants of self-attention.",
        "paper_ids": ["2310.12345"],
        "narrative_summary": "This theme covers foundational work on self-attention..."
      }
    ],
    "research_gaps": [
      {
        "gap_type": "empirical",
        "description": "Limited evaluation of transformers on low-resource languages.",
        "evidence": ["Only 3 of 20 papers include non-English benchmarks."],
        "suggested_questions": ["How do transformer models generalise to low-resource languages?"]
      }
    ],
    "introduction": "This review examines...",
    "executive_summary": "Transformers have become the dominant architecture...",
    "thematic_analysis": "## Theme 1: Self-Attention Mechanisms\n...",
    "comparative_analysis": "Comparing the approaches across papers...",
    "gaps_section": "Several gaps were identified...",
    "conclusion": "In conclusion...",
    "bibliography": "Vaswani, A., et al. (2017). Attention is all you need...",
    "quality_metrics": {
      "source_diversity": 0.85,
      "coverage_score": 0.78
    }
  }
}
```

**Error responses**

| Status | Condition |
|---|---|
| 404 | Job ID not found, or job exists but result is not ready yet |

---

### 4. GET /api/literature-review/{job_id}/download

Stream the generated PDF for a completed review.

**Path parameter:** `job_id` — UUID returned by the submit endpoint.

**Response — 200 OK**

- Content-Type: `application/pdf`
- Content-Disposition: `attachment; filename="literature-review-{job_id[:8]}.pdf"`
- Body: PDF binary stream

**Error responses**

| Status | Condition |
|---|---|
| 404 | Job ID not found or result not yet available |
| 503 | Result exists but PDF generation is not available for this review |

---

### 5. POST /api/literature-review/{job_id}/cancel

Cancel a pending or running job.

**Path parameter:** `job_id` — UUID returned by the submit endpoint.

No request body required.

**Response — 200 OK**

```json
{
  "status": "cancelled",
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
}
```

**Error responses**

| Status | Condition |
|---|---|
| 404 | Job ID not found |

---

### 6. GET /api/health

Liveness check. Returns the service status and application version.

**Response — 200 OK**

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

No error responses under normal conditions. A non-200 response indicates the service is unhealthy.

---

## Standard Error Envelope

All 4xx/5xx responses (except the 503 capacity response on the submit endpoint) use a common structure:

```json
{
  "error": "Job not found",
  "correlation_id": "9f8e7d6c-5b4a-3210-fedc-ba9876543210",
  "status_code": 404
}
```

Include `correlation_id` in bug reports to trace the request in server logs.
