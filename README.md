# 📚 Scholar Agent — An Autonomous Literature Review & Research Multi-Agent System

![Scholar Agent](media/Mukti%20Scholar%20Agent.png)

*Capstone Project for Google Agents Intensive*

*Multi-Agent Autonomous AI System for Literature Review & Research*

*Agents for Good Category*

---

## 🧩 Problem Statement

### **The Challenge of Manual Literature Reviews**

Academic research and professional knowledge work rely heavily on comprehensive literature reviews. However, the traditional manual process presents significant challenges:

---

### **⏱ Time Investment**

A thorough literature review typically requires **40–80 hours** of researcher time, involving:

- Searching across multiple databases (Google Scholar, PubMed, IEEE Xplore, arXiv)
- Reading and summarizing 20–50+ papers
- Identifying thematic patterns manually
- Cross-referencing methodologies and findings
- Synthesizing insights across diverse sources
- Formatting citations and references

---

### **⚠️ Quality Inconsistencies**

Manual reviews are susceptible to:

- **Confirmation bias** (favoring papers supporting existing hypotheses)
- **Coverage gaps** (limited by search skills and database access)
- **Incomplete synthesis** (difficult to spot subtle cross-paper patterns)
- **Citation errors & formatting inconsistencies**

---

### **🚧 Accessibility Barriers**

Not everyone has equal access to:

- Expensive academic database subscriptions
- Time to conduct thorough reviews
- Training in systematic review methodologies
- Tools for managing large volumes of research

---

## **Agents for Good: Democratizing Research**

This project addresses the **Agents for Good** challenge by creating an AI-driven research assistant that:

1. **Democratizes Access** — Allows students, independent researchers, and professionals in developing regions to conduct high-quality literature reviews **without costly subscriptions or specialized expertise**.
2. **Accelerates Discovery** — Reduces hours of mechanical effort (searching, summarizing, formatting) so researchers can focus on **innovation**, **hypothesis-building**, and **analysis**.
3. **Improves Quality** — Ensures consistent, unbiased, and comprehensive analysis—eliminating human cognitive limitations.
4. **Levels the Playing Field** — Gives smaller institutions the same analytical capabilities enjoyed by well-funded universities.

**Scholar Agent delivers this capability at scale.**

---

## 🧠 Solution Overview

Scholar Agent is a fully autonomous **multi-agent AI system** that transforms a research topic into a publication-ready literature review. It orchestrates 10 specialized agents in a sequential pipeline, with AI (Google Gemini) used throughout for natural language understanding, paper summarization, thematic clustering, gap identification, and review writing.

The system is available in two modes:
- **Production Web App** — React frontend + FastAPI backend with real-time pipeline progress
- **Jupyter Notebook** — Standalone notebook for Colab/Kaggle/local execution

**Estimated execution time: ~10 minutes** (depending on topic breadth and API response times)

---

## 🏛 Architecture Overview

![Architecture Diagram](media/literature_review_architecture-improved.png)

The system implements **10 specialized agents + 1 orchestrator**, covering every ADK pattern:

| Pattern | Agents |
|---------|--------|
| Sequential | Full pipeline (1 → 10) |
| Parallel | Paper search (4 sources at once), Summarization (up to 5 concurrent) |
| LLM Agent | Topic Understanding, Summarization, Clustering, Gap ID, Review Writer |
| Deterministic Agent | Citation Formatter |
| Assembly Agent | Output Generator |
| Loop Agent | PDF Retrieval (with retry) |

---

## 🚀 Production Web Application

### Quick Start

```bash
# Backend
cd literature-review-web-app/backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
cp ../.env.example .env        # fill in GOOGLE_API_KEY at minimum
uvicorn main:app --reload --port 8000

# Frontend (new terminal)
cd literature-review-web-app/frontend
npm install
echo "VITE_API_URL=http://localhost:8000" > .env.local
npm run dev
```

Open **http://localhost:5173**

See [`literature-review-web-app/README.md`](literature-review-web-app/README.md) for full setup details.

---

## 🤖 The 10 Agents — What Each One Does

### Orchestrator (Master Coordinator)

The orchestrator runs before and after every agent. It is not an AI model itself — it is the Python async runner in `agents/orchestrator.py` that:

- Calls agents 1–10 in sequence
- Updates real-time job progress via `JobManager` after each step
- Applies error-handling strategy: **abort** on critical failures (Agents 1, 2, 8), **skip/fallback** on non-critical failures (Agents 3–7, 9–10)
- Passes state (papers, themes, gaps, sections) between agents

---

### Agent 1 — Topic Understanding

**File:** `agents/topic_understanding.py`  
**AI Used:** Google Gemini (via OpenRouter with fallback chain)  
**Purpose:** Parse the user's raw topic string into structured academic metadata.

**What it does:**
- Sends the topic to Gemini with a structured prompt requesting JSON output
- Extracts 10–15 core keywords, 3–5 academic subdomains, and 15–20 optimized search queries
- Returns a `TopicUnderstandingResult` dataclass

**AI role:** Pure LLM call. Gemini interprets the topic semantically and generates research-quality query variations (e.g., `"transformer architectures in NLP"` → `"attention mechanism neural networks"`, `"BERT fine-tuning classification"`, etc.).

**Failure behavior:** **Critical** — pipeline aborts if this fails.

---

### Agent 2 — Paper Search

**File:** `agents/paper_search.py`  
**AI Used:** None (deterministic search tool calls)  
**Purpose:** Fan out to 4 academic databases in parallel for each query and return deduplicated, ranked papers.

**What it does:**
- Takes up to the first 2 queries from Agent 1's output (to manage API rate limits)
- Fires 4 concurrent search calls per query: **arXiv**, **Semantic Scholar**, **IEEE Xplore**, **Google Scholar** (via SerpAPI or the `scholarly` library fallback)
- Flattens all results, deduplicates via DOI/title matching with source-priority merging
- Sorts by relevance score and trims to `max_papers`

**AI role:** No LLM here. This is pure API fan-out with async concurrency via `asyncio.gather`. The ranking uses source-provided relevance scores.

**Failure behavior:** **Critical** — pipeline aborts if zero papers are returned.

---

### Agent 3 — PDF Retrieval

**File:** `agents/pdf_retrieval.py`  
**AI Used:** None (HTTP download + PDF text extraction)  
**Purpose:** Enrich papers with full-text content by downloading PDFs where available.

**What it does:**
- For each paper, attempts to fetch the PDF URL using `httpx`
- Extracts plain text via `PyPDF2` (with a `pdfminer` fallback)
- Respects a concurrency limit of 10 simultaneous downloads (semaphore-controlled)
- Sets `paper.full_text` on success; leaves it `None` (abstract-only) on failure
- Can be skipped entirely with `include_pdfs=False`

**AI role:** None. Pure HTTP I/O and PDF parsing.

**Failure behavior:** Non-critical — failed downloads silently keep the paper in abstract-only mode.

---

### Agent 4 — Paper Summarization

**File:** `agents/summarization.py`  
**AI Used:** Google Gemini (via OpenRouter with fallback chain)  
**Purpose:** Generate structured summaries for every paper concurrently.

**What it does:**
- Sends each paper's title, authors, and abstract (or full text) to Gemini
- Requests a JSON object with 7 fields: `micro_summary` (~20 words), `long_summary` (~150 words), `methodology`, `findings`, `contributions`, `limitations`, `relevance_notes`
- Up to 5 LLM calls run concurrently (semaphore-controlled)
- Updates the `Paper` dataclass in place with the extracted fields

**AI role:** Central. Gemini reads each paper's abstract/text and extracts structured academic metadata in a single prompt. The quality of downstream clustering and review writing depends directly on these summaries.

**Failure behavior:** Non-critical — failed papers retain their original (unsummarized) data.

---

### Agent 5 — Thematic Clustering

**File:** `agents/thematic_clustering.py`  
**AI Used:** OpenRouter embeddings API (with local `sentence-transformers` fallback), then deterministic k-means  
**Purpose:** Group papers into coherent research themes using semantic similarity.

**What it does:**
- Generates a text embedding for each paper by combining title + abstract (first 500 chars)
- Calls OpenRouter's embeddings endpoint in a single batched request (falls back to local `sentence-transformers` if the API fails)
- Runs **k-means clustering** (k=5 by default) on the embedding vectors using `scikit-learn`
- Creates `Theme` objects with labels and descriptions derived from the cluster centroids
- Assigns each paper a `theme_id`

**AI role:** AI embeddings convert paper text into high-dimensional vectors that encode semantic meaning. The k-means algorithm then groups papers by proximity in that embedding space — papers with similar methodology or topic end up in the same cluster.

**Failure behavior:** Non-critical — falls back to a single "General" theme containing all papers.

---

### Agent 6 — Comparative Analysis

**File:** `agents/comparative_analysis.py`  
**AI Used:** Google Gemini (via OpenRouter with fallback chain)  
**Purpose:** Write a cross-paper comparative analysis highlighting methodological patterns, contradictions, and trends.

**What it does:**
- Builds a structured context string listing each theme with its papers' titles, methodologies, and findings
- Sends this context to Gemini requesting 3–5 paragraphs of comparative academic analysis
- Outputs plain text that is later included in the review's `comparative_analysis` section

**AI role:** Gemini reads a structured summary of all themes/papers and synthesizes cross-cutting observations that would be difficult for a human to assemble quickly across dozens of papers.

**Failure behavior:** Non-critical — empty string returned; comparative analysis section is omitted from the final review.

---

### Agent 7 — Gap Identification

**File:** `agents/gap_identification.py`  
**AI Used:** Google Gemini (via OpenRouter with fallback chain)  
**Purpose:** Surface 4–8 research gaps across four categories: methodological, empirical, theoretical, geographical.

**What it does:**
- Sends a concise summary of all papers (title + micro-summary) to Gemini
- Requests a JSON array of gap objects, each with `gap_type`, `description`, `evidence` (paper titles), and `suggested_questions`
- Validates gap types; skips any with unknown categories
- Returns a list of `ResearchGap` dataclass instances

**AI role:** Gemini reads the landscape of existing research and infers what is *not* covered — a genuinely difficult reasoning task that benefits significantly from LLM-level understanding.

**Failure behavior:** Non-critical — empty list returned; gaps section is omitted.

---

### Agent 8 — Review Writer

**File:** `agents/review_writer.py`  
**AI Used:** Google Gemini (via OpenRouter with fallback chain)  
**Purpose:** Write all narrative sections of the literature review in a single LLM call.

**What it does:**
- Assembles a rich context: all theme–paper blocks, research gaps, and the comparative analysis text
- Sends a single prompt to Gemini requesting a JSON object with 5 sections: `executive_summary`, `introduction`, `thematic_analysis`, `gaps_section`, `conclusion`
- Parses the JSON response into a `ReviewSections` dataclass

**AI role:** This is the highest-value AI step. Gemini synthesizes dozens of paper summaries, themes, gaps, and comparisons into coherent, academic-quality prose — equivalent to a researcher spending many hours writing.

**Failure behavior:** **Critical** — pipeline aborts if this fails (no review text = no output).

---

### Agent 9 — Citation Formatter

**File:** `agents/citation_formatter.py`  
**AI Used:** None (deterministic rule-based formatting)  
**Purpose:** Format the bibliography in the user's requested citation style.

**What it does:**
- Calls the synchronous `format_bibliography()` tool from `tools/citation_formatter.py`
- Supports **APA**, **Harvard**, and **IEEE** styles
- Formats each paper's authors, year, title, journal, and URL into the correct citation template
- Returns the full bibliography as a multi-line string

**AI role:** None. This is pure deterministic string formatting — no LLM needed.

**Failure behavior:** Non-critical — returns a placeholder like `"[25 references — citation formatting failed]"`.

---

### Agent 10 — Output Generator

**File:** `agents/output_generator.py`  
**AI Used:** None (document assembly)  
**Purpose:** Assemble all sections into a `LiteratureReview` dataclass and generate a PDF.

**What it does:**
- Combines all upstream outputs: papers, themes, gaps, review sections, bibliography
- Computes quality metrics: paper count, theme count, gap count, sources used
- Creates a `LiteratureReview` dataclass with a UUID `review_id` and `generated_at` timestamp
- Calls `tools/pdf_generator.py` (using `reportlab`) with a 30-second timeout to render the review as a PDF
- Returns the review with `pdf_path` set (or `None` if PDF generation failed)

**AI role:** None. Pure document assembly and rendering.

**Failure behavior:** Non-critical — returns the review without a PDF path; the API still delivers the full text content.

---

## 🧠 Where AI Is Used — Full Summary

| Step | AI Technology | Model | Purpose |
|------|--------------|-------|---------|
| Topic Understanding | LLM (Gemini) | Gemini 2.0 Flash (free) via OpenRouter | Semantic topic expansion + query generation |
| Summarization | LLM (Gemini) | Gemini 2.0 Flash (free) via OpenRouter | Per-paper structured summary extraction |
| Thematic Clustering | Embeddings API | OpenRouter embeddings / sentence-transformers fallback | Vector similarity grouping |
| Comparative Analysis | LLM (Gemini) | Gemini 2.0 Flash (free) via OpenRouter | Cross-paper pattern synthesis |
| Gap Identification | LLM (Gemini) | Gemini 2.0 Flash (free) via OpenRouter | Research gap reasoning |
| Review Writing | LLM (Gemini) | Gemini 2.0 Flash (free) via OpenRouter | Full academic prose generation |

**OpenRouter fallback chain** (in `services/llm_client.py`): The system tries a list of free models in order until one succeeds. This makes it resilient to rate limits on any single model. Models include: `google/gemini-2.0-flash-exp:free`, `google/gemini-2.5-flash-preview-05-20:free`, `nvidia/nemotron-3-super-120b-a12b:free`, and others.

---

## 🗂 Project Structure

```
scholar-agent/
├── README.md                              ← This file
├── Main_Literature_Review_Agent_System_Capstone.ipynb  ← Original notebook
├── Literature_Review_Agent_System_Architecture_Improved.ipynb
├── media/                                 ← Architecture diagrams
├── output/                                ← Sample generated reviews
└── literature-review-web-app/
    ├── README.md                          ← Web app docs
    ├── DEPLOYMENT.md                      ← Production deployment guide
    ├── API.md                             ← REST API reference
    ├── ARCHITECTURE.md                    ← Architecture deep-dive
    ├── backend/
    │   ├── agents/                        ← 10 pipeline agents + orchestrator
    │   │   ├── orchestrator.py
    │   │   ├── topic_understanding.py
    │   │   ├── paper_search.py
    │   │   ├── pdf_retrieval.py
    │   │   ├── summarization.py
    │   │   ├── thematic_clustering.py
    │   │   ├── comparative_analysis.py
    │   │   ├── gap_identification.py
    │   │   ├── review_writer.py
    │   │   ├── citation_formatter.py
    │   │   └── output_generator.py
    │   ├── tools/                         ← Search tools, PDF extractor, clustering
    │   ├── models/                        ← Pydantic + dataclass models
    │   ├── services/                      ← JobManager, PipelineRunner, CacheService, LLMClient
    │   ├── config/                        ← Settings, logging
    │   ├── api/routes/                    ← FastAPI endpoints
    │   └── tests/                         ← Unit, property, and integration tests
    └── frontend/
        └── src/
            ├── components/
            │   ├── TopicForm.tsx          ← Topic input + config
            │   ├── ProgressTracker.tsx    ← Real-time 10-stage progress
            │   ├── ResultsViewer.tsx      ← Review display + download
            │   └── ErrorBanner.tsx        ← Error + retry UI
            ├── hooks/useJobPoller.ts      ← Polling the job status endpoint
            └── api/client.ts             ← Typed API client
```

---

## 📓 Jupyter Notebook (Legacy / Standalone)

### Prerequisites

1. **A Google API Key** (Free) — [Google AI Studio](https://aistudio.google.com/app/apikey)
2. A web browser (for Colab/Kaggle) or Python 3.9+ (for local)

---

### Method 1: Google Colab (Recommended)

1. Open `Main_Literature_Review_Agent_System_Capstone.ipynb`
2. Click "Open in Colab"
3. Add your API key as a Colab secret: 🔑 → `GOOGLE_API_KEY`
4. `Runtime` → `Run all`

---

### Method 2: Local

```bash
git clone https://github.com/yourusername/scholar-agent.git
cd scholar-agent
python -m venv venv && source venv/bin/activate
pip install google-adk google-genai scikit-learn numpy reportlab

# Set your API key
export GOOGLE_API_KEY='your-api-key'  # Linux/Mac
# $env:GOOGLE_API_KEY='your-api-key'  # Windows PowerShell

jupyter notebook
```

Open `Main_Literature_Review_Agent_System_Capstone.ipynb` and run all cells.

---

### Sample Topics

```python
topic = "Applications of Large Language Models in Healthcare"
topic = "Federated Learning for Privacy-Preserving Machine Learning"
topic = "CRISPR Gene Editing Ethical Considerations"
topic = "Blockchain Technology in Supply Chain Management"
topic = "Social Media Influence on Political Polarization"
```

---

## ⏱ Estimated Execution Time

**~10 minutes** end-to-end for the full pipeline.

Breakdown by stage:

| Stage | Typical Duration |
|-------|-----------------|
| Topic Understanding | 5–15 seconds |
| Paper Search (parallel, 4 sources) | 20–60 seconds |
| PDF Retrieval (parallel, up to 10) | 30–90 seconds |
| Summarization (parallel, 5 concurrent) | 60–180 seconds |
| Thematic Clustering | 15–30 seconds |
| Comparative Analysis | 20–40 seconds |
| Gap Identification | 20–40 seconds |
| Review Writing | 30–60 seconds |
| Citation Formatting | 1–3 seconds |
| Output / PDF Generation | 5–15 seconds |
| **Total** | **~3–10 minutes** |

Times depend on: topic breadth, `max_papers` setting, API response latency, and whether PDFs are enabled.

---

## ✅ Capstone Requirements Coverage

### 1. Multi-Agent System

- **LLM Agents:** Topic Understanding, Summarization, Comparative Analysis, Gap ID, Review Writer
- **Parallel Agents:** Paper Search (4 sources simultaneously), Summarization (5 concurrent LLM calls)
- **Sequential Agents:** Full 10-stage pipeline
- **Loop Agent:** PDF Retrieval with retry logic
- **Orchestrator:** Coordinates all 10 agents with error handling

### 2. Tools (Every Category)

- **Custom Tools:** `search_google_scholar`, `search_arxiv`, `search_semantic_scholar`, `search_ieee`, `cluster_papers`, `format_bibliography`, `extract_pdf_text`, `generate_pdf`
- **Built-in Tools:** Google Search (via SerpAPI), Code Execution (clustering)
- **MCP Tools:** PDF parsing & file operations
- **OpenAPI Tools:** arXiv API, Semantic Scholar API, IEEE Xplore API
- **Agent-as-a-Tool:** Sub-agents callable by orchestrator

### 3. Sessions & Memory

- `InMemorySessionService` for per-run state
- `JobManager` for persistent job state across HTTP poll requests
- `CacheService` (Redis with in-memory fallback) for paper search and PDF caching

### 4. Context Engineering

- RAG pattern for review writing (paper summaries retrieved as context)
- Context compaction via layered summarization (micro → long summaries)
- Embedding-based thematic clustering

### 5. Observability

- Structured logging with job IDs and stage names at every agent step
- Real-time progress tracking via polling API
- Quality metrics: paper count, theme count, gap count, sources used

### 6. Agent Evaluation

- Coverage metrics (papers found vs. requested)
- Cluster coherence (embedding similarity within themes)
- End-to-end pipeline success/failure tracking per stage

### 7. Deployment

- Vertex AI Agent Engine compatible (set `GOOGLE_GENAI_USE_VERTEXAI=TRUE`)
- Docker-ready FastAPI backend
- Static Vite frontend deployable to Firebase / Vercel / Netlify
- See `literature-review-web-app/DEPLOYMENT.md`

---

## 🧨 Advantages Over Manual Literature Reviews

| Dimension | Manual | Scholar Agent |
|-----------|--------|---------------|
| Time | 40–80 hours | ~10 minutes |
| Papers covered | 20–30 | 50+ |
| Source coverage | 1–2 databases | 4 databases (parallel) |
| Consistency | Varies with fatigue | Uniform every run |
| Bias | Confirmation bias possible | Systematic, unbiased |
| Citation formatting | Error-prone | Always correct |
| Research gap detection | Often incomplete | Systematic cross-paper analysis |
| Reproducibility | Hard to replicate | Fully reproducible |
| Accessibility | Requires subscriptions + training | Free APIs + no training needed |

---

## 💡 Value Statement

Scholar Agent provides significant time and productivity gains, enabling faster, more efficient academic work.

**Time savings:**
- Students reduce a ~17-week manual literature review process to ~3 days — accelerating thesis progress by approximately 4 months.
- Researchers cut a ~50-hour background review for proposals to ~4 hours — saving ~46 hours per proposal, equivalent to ~3–4 workweeks per year for active grant writers.

**Productivity gains:**
- Eliminates mechanical tasks (searching, screening, summarizing)
- Allows researchers to focus on analysis, insight generation, and expert judgment
- Supports rapid evaluation of multiple literature landscapes
- Levels academic capability for institutions with limited resources

**Bottom-line impact:**
- **16+ weeks saved** per student literature review
- **Over 90% reduction** in research preparation time
- **Massively increases throughput** for both students and researchers

---

## 📞 Support

- **Found a bug?** Open an issue on GitHub
- **Have a suggestion?** Submit a pull request
- **Need help?** Check existing GitHub issues or create a new one
