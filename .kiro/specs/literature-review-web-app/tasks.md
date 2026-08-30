# Implementation Plan: Literature Review Web Application

## Overview

Convert the existing Jupyter notebook multi-agent system into a production-ready web application: a FastAPI backend with 10 Google ADK agents, a React SPA frontend, Redis caching, Docker containerization, and comprehensive testing. The implementation follows a foundational-first order: project scaffolding → data models → config → tools → agents → API layer → frontend → infrastructure → tests → documentation.

---

## Tasks

- [x] 1. Scaffold project structure and virtual environment
  - Create the full directory tree under `literature-review-web-app/` matching the design: `backend/agents/`, `backend/tools/`, `backend/models/`, `backend/services/`, `backend/config/`, `backend/utils/`, `backend/api/routes/`, `backend/tests/unit/`, `backend/tests/property/`, `backend/tests/integration/`, `frontend/src/components/`, `frontend/src/hooks/`, `frontend/src/api/`
  - Create all `__init__.py` files for every Python package directory
  - Create `backend/requirements.txt` with pinned versions for all dependencies: `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `google-adk`, `google-generativeai`, `arxiv>=2.1.0`, `semanticscholar`, `httpx`, `aioredis`, `redis`, `reportlab`, `scikit-learn`, `numpy`, `hypothesis`, `pytest`, `pytest-asyncio`, `pytest-httpx`, `pytest-cov`, `pytest-benchmark`
  - Create `frontend/package.json` with React 18, TypeScript, Vite, `@mui/material`, `axios`, `msw`
  - _Requirements: 1.1, 1.5, 7.4, 7.5, 8.1_

- [x] 2. Implement core data models
  - [x] 2.1 Implement domain models in `backend/models/paper.py`
    - Write frozen dataclasses: `Paper`, `Theme`, `ResearchGap`, `LiteratureReview` exactly as specified in design
    - Include all fields with correct types, defaults, and `field(default_factory=...)` for mutable defaults
    - Add full Python type hints throughout
    - _Requirements: 1.8, 1.10, 12.1, 12.3, 12.5_
  - [x] 2.2 Implement job state models in `backend/models/job.py`
    - Write `Stage` enum with all 14 values (`PENDING` through `CANCELLED`)
    - Write `STAGE_ORDER` list of 10 ordered stages
    - Write `Job` dataclass with all fields: `job_id`, `topic`, `config`, `status`, `created_at`, `updated_at`, `progress_pct`, `message`, `result`, `error`
    - _Requirements: 1.8, 6.2_
  - [x] 2.3 Implement API Pydantic models in `backend/models/api.py`
    - Write `ReviewConfig`, `CreateReviewRequest`, `CreateReviewResponse`, `JobStatusResponse`, `JobResultResponse`, `LiteratureReviewDTO`
    - Add field validators: topic min_length=5 max_length=500, max_papers ge=5 le=50
    - _Requirements: 2.2, 2.3, 2.4, 2.9, 5.2, 5.3_
  - [ ]* 2.4 Write unit tests for data model validation
    - Test `ReviewConfig` boundary values, `CreateReviewRequest` validation, `Job` state transitions
    - _Requirements: 15.1_

- [x] 3. Implement configuration and logging
  - [x] 3.1 Implement settings in `backend/config/settings.py`
    - Write `Settings` class using `pydantic-settings` reading from environment: `GOOGLE_API_KEY`, `IEEE_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY`, `SERPAPI_KEY`, `REDIS_URL`, `DATABASE_URL`, `LOG_LEVEL`, `CORS_ORIGINS`, `MAX_CONCURRENT_JOBS`
    - Add startup validation that fails fast if required keys are absent
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.8, 8.9, 8.10_
  - [x] 3.2 Implement structured logging in `backend/config/logging_config.py`
    - Configure Python `logging` with JSON formatter, log level from settings, handlers for console and optional file output
    - _Requirements: 9.1, 9.10_
  - [x] 3.3 Create `.env.example` at project root
    - Document every environment variable with name, description, example value, and whether required/optional
    - _Requirements: 8.6, 14.6_

- [x] 4. Implement utility modules
  - [x] 4.1 Implement retry decorator in `backend/utils/retry.py`
    - Write `@retry(max_attempts, initial_delay_seconds, backoff_factor, retryable_status_codes)` async decorator
    - Compute inter-attempt delays as `initial_delay * backoff_factor^attempt`
    - Raise the final exception if all attempts fail
    - _Requirements: 3.8, 9.8, 10.2_
  - [ ]* 4.2 Write property test for exponential backoff in `backend/tests/property/test_retry.py`
    - **Property 6: Exponential Backoff Correctness**
    - **Validates: Requirements 9.8, 3.8**
    - `# Feature: literature-review-web-app, Property 6: exponential backoff correctness`
    - `@settings(max_examples=100)` `@given(st.integers(min_value=0, max_value=5))`
    - Assert exactly N+1 total calls, each delay strictly greater than the previous, final result is the success value
    - _Requirements: 15.1_
  - [x] 4.3 Implement deduplication logic in `backend/utils/deduplication.py`
    - Write `deduplicate_papers(papers: list[Paper]) -> list[Paper]` that removes papers sharing the same non-null DOI and papers with identical normalized titles (lowercase, stripped punctuation)
    - _Requirements: 3.7_
  - [ ]* 4.4 Write property test for paper deduplication in `backend/tests/property/test_deduplication.py`
    - **Property 2: Paper Deduplication Completeness**
    - **Validates: Requirements 3.7**
    - `# Feature: literature-review-web-app, Property 2: paper deduplication completeness`
    - `@settings(max_examples=100)` `@given(paper_lists_with_duplicates())`
    - Assert no two output papers share a non-null DOI, and no two share a normalized title
    - _Requirements: 15.1_
  - [x] 4.5 Implement correlation ID middleware in `backend/utils/correlation.py`
    - Write FastAPI middleware that reads `X-Correlation-ID` request header or generates a UUID, attaches it to request state and all log records
    - _Requirements: 9.11_

- [x] 5. Checkpoint — Verify utilities and models
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement cache service
  - [x] 6.1 Implement `CacheService` in `backend/services/cache_service.py`
    - Write async `get`, `set`, `delete`, `exists` methods
    - Primary implementation uses `aioredis`; fall back to in-memory `dict` with TTL tracking when Redis is unavailable
    - Log cache hits and misses as metrics
    - _Requirements: 4.5, 10.3, 10.7, 10.8, 10.9, 10.10_
  - [ ]* 6.2 Write property test for cache round trip in `backend/tests/property/test_cache.py`
    - **Property 5: Cache Round Trip Correctness**
    - **Validates: Requirements 4.5, 4.6, 4.7, 10.3**
    - `# Feature: literature-review-web-app, Property 5: cache round trip correctness`
    - `@settings(max_examples=100)` `@given(st.text(), st.binary(), st.floats(min_value=0.1, max_value=86400.0))`
    - Assert retrieval before TTL returns stored value; retrieval after TTL returns None
    - _Requirements: 15.1_
  - [ ]* 6.3 Write unit tests for cache service in `backend/tests/unit/test_cache_service.py`
    - Test get/set/miss/TTL-expiry examples with in-memory backend
    - _Requirements: 15.1_

- [x] 7. Implement academic API search tools
  - [x] 7.1 Implement arXiv search tool in `backend/tools/arxiv_search.py`
    - Write `async def search_arxiv(query: str, max_results: int, cache: CacheService) -> list[Paper]` using the `arxiv` library
    - Map `arxiv.Result` fields to `Paper` dataclass, set `source="arxiv"`
    - Apply retry decorator; cache results with 24-hour TTL
    - _Requirements: 3.2, 3.5, 3.6, 3.9, 3.10, 4.5, 10.1, 10.3_
  - [x] 7.2 Implement Semantic Scholar search tool in `backend/tools/semantic_scholar_search.py`
    - Write `async def search_semantic_scholar(query: str, max_results: int, cache: CacheService) -> list[Paper]` using the `semanticscholar` library
    - Apply retry decorator with 1-req/sec rate limit awareness; cache results 24 h TTL
    - _Requirements: 3.4, 3.5, 3.6, 3.9, 3.10, 10.1, 10.3_
  - [x] 7.3 Implement IEEE Xplore search tool in `backend/tools/ieee_search.py`
    - Write `async def search_ieee(query: str, max_results: int, cache: CacheService) -> list[Paper]` using `httpx` async client with IEEE REST API and `IEEE_API_KEY`
    - Apply retry decorator; cache results 24 h TTL
    - _Requirements: 3.1, 3.5, 3.6, 3.9, 3.10, 10.1, 10.3_
  - [x] 7.4 Implement Google Scholar / SerpAPI search tool in `backend/tools/scholar_search.py`
    - Write adapter: use `scholarly` if `SERPAPI_KEY` is absent, SerpAPI if present
    - Apply retry decorator; cache results 24 h TTL
    - _Requirements: 3.3, 3.5, 3.6, 3.9, 3.10, 10.1, 10.3_
  - [ ]* 7.5 Write property test for API response parsing in `backend/tests/property/test_api_parsing.py`
    - **Property 3: API Response Parsing Round Trip**
    - **Validates: Requirements 3.9, 3.10**
    - `# Feature: literature-review-web-app, Property 3: API response parsing round trip`
    - `@settings(max_examples=100)` `@given(valid_api_responses())`
    - Assert every parsed `Paper` has non-empty title, authors, year, abstract, url, and source matches origin
    - _Requirements: 15.1_
  - [ ]* 7.6 Write unit tests for API parsers in `backend/tests/unit/test_api_parsers.py`
    - Test known arXiv / Scholar / IEEE response payloads → `Paper` conversion
    - _Requirements: 15.1_

- [x] 8. Implement additional backend tools
  - [x] 8.1 Implement PDF extractor tool in `backend/tools/pdf_extractor.py`
    - Write `async def extract_pdf_text(url: str, cache: CacheService) -> str | None` using `httpx` for download and text extraction
    - Apply retry decorator; return `None` on persistent failure so the paper is marked abstract-only
    - _Requirements: 11.7_
  - [x] 8.2 Implement thematic clustering tool in `backend/tools/clustering.py`
    - Write `def cluster_papers(papers: list[Paper], n_clusters: int) -> list[Theme]` using scikit-learn k-means on paper embeddings
    - Each paper must be assigned to exactly one theme; generate `Theme` with label, description, `paper_ids` frozenset
    - _Requirements: 11.9, 12.3_
  - [ ]* 8.3 Write property test for theme coverage in `backend/tests/property/test_clustering.py`
    - **Property 7: Theme Coverage — Every Paper Assigned to Exactly One Theme**
    - **Validates: Requirements 12.3**
    - `# Feature: literature-review-web-app, Property 7: theme coverage partition`
    - `@settings(max_examples=100)` `@given(paper_sets(min_size=3, max_size=30))`
    - Assert union of all `theme.paper_ids` == set of all input paper IDs, no paper appears in two themes, every theme has non-empty label and description
    - _Requirements: 15.1_
  - [x] 8.4 Implement citation formatter tool in `backend/tools/citation_formatter.py`
    - Write `def format_citation(paper: Paper, style: Literal["APA","Harvard","IEEE"]) -> str` returning a correctly formatted citation string
    - _Requirements: 11.13, 12.6, 12.9, 12.10_
  - [ ]* 8.5 Write unit tests for citation formatter in `backend/tests/unit/test_citation_formatter.py`
    - Test APA, Harvard, IEEE formatting with known paper fixtures
    - _Requirements: 15.1_
  - [x] 8.6 Implement PDF generator tool in `backend/tools/pdf_generator.py`
    - Write `def generate_pdf(review: LiteratureReview, output_path: str) -> str` using `reportlab`
    - Include table of contents, headers, page numbers, bibliography section, and theme cluster summary
    - _Requirements: 12.7, 12.8, 12.9_

- [x] 9. Checkpoint — Verify tools compile and unit tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement agents 1–5
  - [x] 10.1 Implement Topic Understanding Agent in `backend/agents/topic_understanding.py`
    - Write `async def run(input: AgentInput, context: AgentContext) -> AgentOutput` that calls Gemini 2.5 Flash to extract keywords and generate search queries from the research topic
    - Use Google ADK agent pattern; abort pipeline if this agent fails
    - _Requirements: 11.5_
  - [x] 10.2 Implement Paper Search Agent in `backend/agents/paper_search.py`
    - Write `async def run(input, context)` that fans out to all four search tools concurrently using `asyncio.gather`
    - Continue if ≥1 source succeeds; log failed sources; deduplicate results using `deduplication.py`
    - _Requirements: 3.6, 4.3, 11.6_
  - [x] 10.3 Implement PDF Retrieval Agent in `backend/agents/pdf_retrieval.py`
    - Write loop agent that calls `extract_pdf_text` for each paper; marks papers as abstract-only on persistent failure
    - _Requirements: 11.7_
  - [x] 10.4 Implement Summarization Agent in `backend/agents/summarization.py`
    - Write parallel agent that calls Gemini 2.5 Flash concurrently for each paper to generate micro-summary, long-summary, methodology, findings, contributions, limitations
    - Skip papers where summarization fails
    - _Requirements: 4.4, 11.8_
  - [x] 10.5 Implement Thematic Clustering Agent in `backend/agents/thematic_clustering.py`
    - Write agent that calls Gemini for embeddings then uses `clustering.py` tool; fall back to single-theme grouping on failure
    - _Requirements: 11.9_

- [x] 11. Implement agents 6–10 and orchestrator
  - [x] 11.1 Implement Comparative Analysis Agent in `backend/agents/comparative_analysis.py`
    - Write `async def run(input, context)` that calls Gemini to generate per-theme comparison matrices and methodological pattern analysis; omit section on failure
    - _Requirements: 11.10, 12.4_
  - [x] 11.2 Implement Gap Identification Agent in `backend/agents/gap_identification.py`
    - Write `async def run(input, context)` that calls Gemini to identify methodological, empirical, theoretical, and geographical research gaps; omit section on failure
    - _Requirements: 11.11, 12.5_
  - [x] 11.3 Implement Review Writer Agent in `backend/agents/review_writer.py`
    - Write `async def run(input, context)` that calls Gemini to produce: introduction, thematic_analysis, comparative_analysis, gaps_section, conclusion, executive_summary; abort pipeline if this agent fails
    - _Requirements: 11.12, 12.1, 12.2_
  - [x] 11.4 Implement Citation Formatter Agent in `backend/agents/citation_formatter.py`
    - Write `async def run(input, context)` that calls `citation_formatter.py` tool for each paper in the selected style; use placeholder citations on failure
    - _Requirements: 11.13, 12.6, 12.9, 12.10_
  - [ ]* 11.5 Write property test for citation completeness in `backend/tests/property/test_citations.py`
    - **Property 8: Citation Completeness**
    - **Validates: Requirements 12.6, 12.9**
    - `# Feature: literature-review-web-app, Property 8: citation completeness`
    - `@settings(max_examples=100)` `@given(review_with_referenced_papers())`
    - Assert bibliography contains a citation for every referenced paper, and every bibliography entry references a paper in the collection
    - _Requirements: 15.1_
  - [x] 11.6 Implement Output Generator Agent in `backend/agents/output_generator.py`
    - Write `async def run(input, context)` that assembles `LiteratureReview` dataclass and calls `generate_pdf`; return Markdown text without PDF on generator failure
    - _Requirements: 11.14, 12.7, 12.11_
  - [x] 11.7 Implement Orchestrator in `backend/agents/orchestrator.py`
    - Wire agents 1→2→3→4→5→6→7→8→9→10 sequentially using Google ADK `SequentialAgent`; apply the error-handling decision tree from the design (abort / skip / continue per agent)
    - Update job status via `JobManager.update_status` after each stage with correct `Stage` enum value
    - _Requirements: 1.3, 4.2, 11.2, 11.15, 11.16_

- [x] 12. Implement Job Manager and Pipeline Runner
  - [x] 12.1 Implement `JobManager` in `backend/services/job_manager.py`
    - Implement all interface methods: `create_job`, `get_status`, `get_result`, `update_status`, `complete_job`, `fail_job`, `cancel_job`
    - Store jobs in Redis (with in-memory fallback) using `job:{job_id}` keys
    - `create_job` generates UUID v4 job IDs
    - _Requirements: 2.3, 6.1, 6.3, 13.2, 13.3_
  - [ ]* 12.2 Write property test for job ID uniqueness in `backend/tests/property/test_job_id_uniqueness.py`
    - **Property 1: Job ID Uniqueness**
    - **Validates: Requirements 2.3**
    - `# Feature: literature-review-web-app, Property 1: job ID uniqueness`
    - `@settings(max_examples=200)` `@given(st.lists(valid_review_requests(), min_size=2, max_size=50))`
    - Assert all job IDs are distinct across a batch of requests
    - _Requirements: 15.1_
  - [ ]* 12.3 Write property test for progress percentage monotonicity in `backend/tests/property/test_progress.py`
    - **Property 4: Progress Percentage Monotonicity and Accuracy**
    - **Validates: Requirements 6.3**
    - `# Feature: literature-review-web-app, Property 4: progress percentage monotonicity`
    - `@settings(max_examples=100)` `@given(stage_subsets())`
    - Assert `progress_pct == (len(completed_stages) / 10) * 100` and that adding more stages never decreases progress
    - _Requirements: 15.1_
  - [ ]* 12.4 Write unit tests for progress tracking in `backend/tests/unit/test_progress.py`
    - Test progress percentage with 0, 5, 10 stages complete
    - _Requirements: 15.1_
  - [x] 12.5 Implement `PipelineRunner` in `backend/services/pipeline_runner.py`
    - Write `async def run_pipeline(job_id: str, topic: str, config: ReviewConfig) -> None`
    - Creates `AgentContext`, invokes orchestrator, handles top-level exceptions by calling `job_manager.fail_job`
    - _Requirements: 4.10, 11.2_

- [x] 13. Checkpoint — Verify agent pipeline with mock external services
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Implement FastAPI application and REST API
  - [x] 14.1 Implement literature review routes in `backend/api/routes/literature_review.py`
    - POST `/api/literature-review` → validates `CreateReviewRequest`, creates job, schedules `PipelineRunner` as `BackgroundTask`, returns 202 `CreateReviewResponse`
    - GET `/api/literature-review/{job_id}/status` → returns `JobStatusResponse` including `elapsed_seconds` and `estimated_remaining_seconds`
    - GET `/api/literature-review/{job_id}/result` → returns 200 `JobResultResponse` or 404
    - GET `/api/literature-review/{job_id}/download` → streams PDF as `application/pdf` or 404
    - POST `/api/literature-review/{job_id}/cancel` → calls `cancel_job`, returns 200
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.8, 5.4, 5.6, 5.9, 5.11_
  - [x] 14.2 Implement health route in `backend/api/routes/health.py`
    - GET `/api/health` → returns `{status: "ok", version: "..."}` 200
    - _Requirements: 2.7_
  - [x] 14.3 Implement middleware in `backend/api/middleware.py`
    - Register CORS middleware allowing `CORS_ORIGINS` from settings
    - Register correlation ID middleware from `utils/correlation.py`
    - Register request logging middleware (method, path, status, duration)
    - Register global exception handler returning standardized `{error, correlation_id, status_code}` JSON
    - Return 503 with `Retry-After` header when max concurrent jobs exceeded
    - _Requirements: 2.11, 2.12, 9.2, 9.6, 9.7, 9.11, 13.6_
  - [x] 14.4 Implement FastAPI app factory in `backend/main.py`
    - Create `app = FastAPI(...)`, include all routers, register middleware, initialise settings/logging/cache on startup
    - _Requirements: 2.1, 8.8_

- [ ] 15. Write integration tests for API endpoints
  - [ ]* 15.1 Write integration tests in `backend/tests/integration/test_api.py`
    - Test all six API endpoints with `TestClient`
    - Use `pytest-httpx` to mock external academic API HTTP calls
    - Cover happy path, 400 invalid input, 404 unknown job, 503 overload scenarios
    - _Requirements: 15.3, 15.4, 15.5_
  - [ ]* 15.2 Write full pipeline integration test in `backend/tests/integration/test_pipeline.py`
    - Run entire 10-agent pipeline with all external services mocked; assert final `LiteratureReview` contains all required sections
    - _Requirements: 15.4, 15.5, 15.8_

- [x] 16. Implement React frontend
  - [x] 16.1 Implement typed API client in `frontend/src/api/client.ts`
    - Write `axios`-based client with typed request/response interfaces matching backend Pydantic models
    - Export: `submitReview`, `getStatus`, `getResult`, `downloadPDF`, `cancelJob`
    - _Requirements: 5.4, 5.6, 5.9, 5.11_
  - [x] 16.2 Implement `useJobPoller` hook in `frontend/src/hooks/useJobPoller.ts`
    - Poll `getStatus` every 2 seconds while job is `pending` or `running`; stop on `completed`, `failed`, or `cancelled`
    - Return `{status, stage, progress_pct, elapsed_seconds, estimated_remaining_seconds, message}`
    - _Requirements: 5.6, 5.7, 6.5, 6.6, 6.7_
  - [x] 16.3 Implement `TopicForm` component in `frontend/src/components/TopicForm.tsx`
    - Render text input (min 5, max 500 chars), `max_papers` slider (5–50), `search_depth` select, `citation_style` select, submit button
    - Call `submitReview` on submit; disable form while job is in progress
    - _Requirements: 5.2, 5.3, 5.4_
  - [x] 16.4 Implement `ProgressTracker` component in `frontend/src/components/ProgressTracker.tsx`
    - Render MUI `LinearProgress` bar with `progress_pct`, current stage name, status message, elapsed time, estimated remaining time, and a cancel button
    - _Requirements: 5.5, 5.7, 6.5, 6.6, 6.7, 5.11_
  - [x] 16.5 Implement `ResultsViewer` component in `frontend/src/components/ResultsViewer.tsx`
    - Display themes with paper lists, research gaps by category, executive summary, and a PDF download button triggering `downloadPDF`
    - _Requirements: 5.8, 5.9_
  - [x] 16.6 Implement `ErrorBanner` component in `frontend/src/components/ErrorBanner.tsx`
    - Display error message with retry option; shown when job fails or API call returns error
    - _Requirements: 5.10, 6.9_
  - [x] 16.7 Implement `App.tsx` and `main.tsx`
    - Wire components: render `TopicForm` → on submit show `ProgressTracker` → on complete show `ResultsViewer` → on error show `ErrorBanner`
    - _Requirements: 5.1, 5.12_

- [ ] 17. Write frontend tests
  - [ ]* 17.1 Write component tests in `frontend/src/__tests__/`
    - Use React Testing Library and `msw` to test `TopicForm`, `ProgressTracker`, `ResultsViewer`, `ErrorBanner`
    - Test `useJobPoller` hook: starts polling, stops on completion, stops on cancellation
    - _Requirements: 15.7_

- [x] 18. Checkpoint — Verify frontend and API integration
  - Ensure all tests pass, ask the user if questions arise.

- [x] 19. Docker containerization and infrastructure — SKIPPED (not required)
  - [x] 19.1 SKIPPED
  - [x] 19.2 SKIPPED
  - [x] 19.3 SKIPPED

- [ ] 20. Write performance and load tests
  - [ ]* 20.1 Write benchmark tests in `backend/tests/unit/test_performance.py`
    - Use `pytest-benchmark` to measure individual tool and agent execution time with mock APIs
    - _Requirements: 15.9_
  - [ ]* 20.2 Write end-to-end timing test in `backend/tests/integration/test_e2e_timing.py`
    - Assert full pipeline completes in < 120 seconds using all-mock external APIs
    - _Requirements: 4.1, 15.8, 15.9_
  - [ ]* 20.3 Write load test script in `backend/tests/load/locustfile.py`
    - Define `LiteratureReviewUser` with tasks: submit job, poll until complete
    - Target: 10 concurrent jobs
    - _Requirements: 15.10_

- [x] 21. Documentation
  - [x] 21.1 Update `README.md` with quick-start guide
    - Add project overview, architecture summary, prerequisites, `docker-compose up` quick-start, link to other docs
    - _Requirements: 14.1_
  - [x] 21.2 Create `DEPLOYMENT.md`
    - Document Docker build and run steps, environment variable setup, production considerations, cloud deployment notes
    - _Requirements: 14.2_
  - [x] 21.3 Create `API.md`
    - Document all six API endpoints with request/response JSON examples and error codes
    - Note: FastAPI also auto-generates OpenAPI docs at `/docs`
    - _Requirements: 14.3, 14.11_
  - [x] 21.4 Create `ARCHITECTURE.md`
    - Include Mermaid architecture diagram (from design doc), agent sequence diagram, component descriptions
    - _Requirements: 14.4, 14.8, 14.9_
  - [x] 21.5 Create `DEVELOPMENT.md`
    - Document local venv setup, `pip install -r requirements.txt`, running with `uvicorn`, running tests with `pytest --cov`
    - Include troubleshooting guide for common issues
    - _Requirements: 14.5, 14.10_

- [ ] 22. Final checkpoint — Full test suite and coverage check
  - Run `pytest --cov=backend --cov-report=term-missing` and verify ≥ 70% line coverage
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 15.6, 15.11_

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP build
- All 15 requirements are covered: Req 1 (tasks 1,2,4), Req 2 (task 14), Req 3 (task 7), Req 4 (tasks 6,7,10,11,12), Req 5 (task 16), Req 6 (tasks 12,16), Req 7 (task 19), Req 8 (task 3), Req 9 (tasks 4,14), Req 10 (tasks 4,6,7), Req 11 (tasks 10,11,12), Req 12 (tasks 8,11), Req 13 (tasks 12,14,19), Req 14 (task 21), Req 15 (tasks 4,6,7,8,11,12,15,17,20)
- All 8 correctness properties from the design are covered by dedicated property-based test sub-tasks (tasks 4.2, 4.4, 7.5, 8.3, 11.5, 12.2, 12.3, 6.2)
- Checkpoint tasks ensure incremental validation at natural breakpoints
- The `.env.example` and Docker files are included as first-class tasks (tasks 3.3, 19.1, 19.2, 19.3)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1", "2.2", "2.3", "3.1", "3.2", "3.3"] },
    { "id": 1, "tasks": ["2.4", "4.1", "4.3", "4.5"] },
    { "id": 2, "tasks": ["4.2", "4.4", "6.1"] },
    { "id": 3, "tasks": ["6.2", "6.3", "7.1", "7.2", "7.3", "7.4"] },
    { "id": 4, "tasks": ["7.5", "7.6", "8.1", "8.2", "8.4", "8.6"] },
    { "id": 5, "tasks": ["8.3", "8.5", "10.1", "10.2", "10.3", "10.4", "10.5"] },
    { "id": 6, "tasks": ["11.1", "11.2", "11.3", "11.4", "11.6"] },
    { "id": 7, "tasks": ["11.5", "11.7", "12.1"] },
    { "id": 8, "tasks": ["12.2", "12.3", "12.4", "12.5"] },
    { "id": 9, "tasks": ["14.1", "14.2", "14.3", "14.4", "16.1"] },
    { "id": 10, "tasks": ["15.1", "15.2", "16.2", "16.3"] },
    { "id": 11, "tasks": ["16.4", "16.5", "16.6", "16.7"] },
    { "id": 12, "tasks": ["17.1", "19.1", "19.2"] },
    { "id": 13, "tasks": ["19.3", "20.1", "20.2"] },
    { "id": 14, "tasks": ["20.3", "21.1", "21.2", "21.3", "21.4", "21.5"] }
  ]
}
```
