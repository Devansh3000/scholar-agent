import { Container } from '@mui/material';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  cancelJob,
  getResult,
  submitReview,
  type CreateReviewRequest,
  type JobResultResponse,
  type ReviewConfig,
} from './api/client';
import { ErrorBanner } from './components/ErrorBanner';
import { ProgressTracker } from './components/ProgressTracker';
import { ResultsViewer } from './components/ResultsViewer';
import { TopicForm } from './components/TopicForm';
import { useJobPoller } from './hooks/useJobPoller';

type AppState = 'idle' | 'submitting' | 'polling' | 'failed' | 'complete' | 'error';

export default function App() {
  const [appState, setAppState] = useState<AppState>('idle');
  const [jobId, setJobId] = useState<string | null>(null);
  const [result, setResult] = useState<JobResultResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string>('');

  const pollerJobId = appState === 'polling' || appState === 'failed' ? jobId : null;
  const pollerData = useJobPoller(pollerJobId);
  const resultFetchedRef = useRef(false);

  useEffect(() => {
    if (appState !== 'polling') return;

    if (pollerData.status === 'completed' && !resultFetchedRef.current && jobId) {
      resultFetchedRef.current = true;
      getResult(jobId)
        .then((data) => {
          setResult(data);
          setAppState('complete');
        })
        .catch((err: unknown) => {
          const msg = err instanceof Error ? err.message : 'Failed to fetch result';
          setErrorMessage(msg);
          setAppState('error');
        });
    } else if (pollerData.status === 'failed') {
      // Show progress tracker with error detail instead of generic error banner
      setAppState('failed');
    } else if (pollerData.status === 'cancelled') {
      setErrorMessage('The review was cancelled.');
      setAppState('error');
    } else if (pollerData.error && pollerData.status === null) {
      setErrorMessage('Cannot reach backend. Make sure the server is running on port 8000.');
      setAppState('error');
    }
  }, [appState, jobId, pollerData.status, pollerData.error]);

  const handleSubmit = useCallback(async (topic: string, config: ReviewConfig) => {
    setAppState('submitting');
    setErrorMessage('');
    resultFetchedRef.current = false;

    const req: CreateReviewRequest = { topic, config };
    try {
      const response = await submitReview(req);
      setJobId(response.job_id);
      setAppState('polling');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to submit review request. Is the backend running on port 8000?';
      setErrorMessage(msg);
      setAppState('error');
    }
  }, []);

  const handleCancel = useCallback(async () => {
    if (!jobId) return;
    try {
      await cancelJob(jobId);
    } catch {
      // ignore
    }
  }, [jobId]);

  const handleRetry = useCallback(() => {
    setAppState('idle');
    setJobId(null);
    setResult(null);
    setErrorMessage('');
    resultFetchedRef.current = false;
  }, []);

  const progressStatus = jobId
    ? {
        job_id: jobId,
        status: pollerData.status ?? 'pending',
        stage: pollerData.stage ?? '',
        progress_pct: pollerData.progress_pct,
        message: pollerData.message ?? 'Starting…',
        elapsed_seconds: pollerData.elapsed_seconds,
        estimated_remaining_seconds: pollerData.estimated_remaining_seconds,
      }
    : null;

  const showProgress = (appState === 'polling' || appState === 'failed') && progressStatus;

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      {(appState === 'idle' || appState === 'submitting') && (
        <TopicForm onSubmit={handleSubmit} isLoading={appState === 'submitting'} />
      )}

      {showProgress && (
        <>
          <ProgressTracker
            status={progressStatus}
            onCancel={handleCancel}
            error={pollerData.error}
          />
          {appState === 'failed' && (
            <ErrorBanner
              message={pollerData.message || 'Pipeline failed. See details above.'}
              onRetry={handleRetry}
            />
          )}
        </>
      )}

      {appState === 'complete' && result && jobId && (
        <ResultsViewer result={result} jobId={jobId} />
      )}

      {appState === 'error' && (
        <ErrorBanner message={errorMessage} onRetry={handleRetry} />
      )}
    </Container>
  );
}
