import axios from 'axios';

// ---------------------------------------------------------------------------
// TypeScript interfaces matching backend Pydantic models
// ---------------------------------------------------------------------------

export interface ReviewConfig {
  max_papers: number;       // 5–50, default 20
  search_depth: 'shallow' | 'medium' | 'deep';
  citation_style: 'APA' | 'Harvard' | 'IEEE';
  include_pdfs: boolean;
}

export interface CreateReviewRequest {
  topic: string;
  config?: ReviewConfig;
}

export interface CreateReviewResponse {
  job_id: string;
  estimated_seconds: number;
}

export interface JobStatusResponse {
  job_id: string;
  status: string;
  stage: string;
  progress_pct: number;
  message: string;
  elapsed_seconds: number;
  estimated_remaining_seconds: number | null;
}

export interface PaperDTO {
  paper_id: string;
  title: string;
  authors: string[];
  year: number;
  journal: string;
  url: string;
  source: string;
  doi?: string;
  micro_summary?: string;
  theme_id?: number;
}

export interface ThemeDTO {
  theme_id: number;
  label: string;
  description: string;
  paper_ids: string[];
  narrative_summary?: string;
}

export interface ResearchGapDTO {
  gap_type: string;
  description: string;
  evidence: string[];
  suggested_questions: string[];
}

export interface LiteratureReviewDTO {
  review_id: string;
  topic: string;
  generated_at: string;
  papers: PaperDTO[];
  themes: ThemeDTO[];
  research_gaps: ResearchGapDTO[];
  introduction: string;
  executive_summary: string;
  thematic_analysis: string;
  comparative_analysis: string;
  gaps_section: string;
  conclusion: string;
  bibliography: string;
  citation_style: string;
  paper_count: number;
  quality_metrics: Record<string, unknown>;
}

export interface JobResultResponse {
  job_id: string;
  review: LiteratureReviewDTO;
  completed_at: string;
}

// ---------------------------------------------------------------------------
// Axios instance
// ---------------------------------------------------------------------------

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 300000, // 5 minutes — result fetch needs time
});

// Timeout for submit — returns job_id quickly but allow time for cold starts
const submitApi = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
});

// Generous timeout for status polling
const pollApi = axios.create({
  baseURL: BASE_URL,
  timeout: 60000,
});

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export const submitReview = (req: CreateReviewRequest): Promise<CreateReviewResponse> =>
  submitApi.post<CreateReviewResponse>('/api/literature-review', req).then((r) => r.data);

export const getStatus = (jobId: string): Promise<JobStatusResponse> =>
  pollApi.get<JobStatusResponse>(`/api/literature-review/${jobId}/status`).then((r) => r.data);

export const getResult = (jobId: string): Promise<JobResultResponse> =>
  api.get<JobResultResponse>(`/api/literature-review/${jobId}/result`).then((r) => r.data);

export const downloadPDF = (jobId: string): void => {
  window.open(`${BASE_URL}/api/literature-review/${jobId}/download`, '_blank');
};

export const cancelJob = (jobId: string): Promise<void> =>
  api.post(`/api/literature-review/${jobId}/cancel`).then(() => undefined);
