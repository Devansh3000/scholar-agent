import { useEffect, useRef, useState } from 'react';
import { getStatus, type JobStatusResponse } from '../api/client';

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled']);
const POLL_INTERVAL_MS = 2000;

export interface UseJobPollerResult {
  status: string | null;
  stage: string | null;
  progress_pct: number;
  elapsed_seconds: number;
  estimated_remaining_seconds: number | null;
  message: string | null;
  error: string | null;
}

export function useJobPoller(jobId: string | null): UseJobPollerResult {
  const [state, setState] = useState<UseJobPollerResult>({
    status: null,
    stage: null,
    progress_pct: 0,
    elapsed_seconds: 0,
    estimated_remaining_seconds: null,
    message: null,
    error: null,
  });

  const statusRef = useRef<string | null>(null);
  statusRef.current = state.status;
  // Count consecutive network errors — only surface after 3 consecutive failures
  const errorCountRef = useRef(0);

  useEffect(() => {
    if (!jobId) {
      setState({
        status: null, stage: null, progress_pct: 0, elapsed_seconds: 0,
        estimated_remaining_seconds: null, message: null, error: null,
      });
      errorCountRef.current = 0;
      return;
    }

    let cancelled = false;

    const poll = async () => {
      if (cancelled) return;
      if (statusRef.current && TERMINAL_STATUSES.has(statusRef.current)) return;

      try {
        const data: JobStatusResponse = await getStatus(jobId);
        if (!cancelled) {
          errorCountRef.current = 0; // reset error count on success
          setState({
            status: data.status,
            stage: data.stage,
            progress_pct: data.progress_pct,
            elapsed_seconds: data.elapsed_seconds,
            estimated_remaining_seconds: data.estimated_remaining_seconds,
            message: data.message,
            error: null,
          });
        }
      } catch (err) {
        if (!cancelled) {
          errorCountRef.current += 1;
          // Only surface error after 3 consecutive failures (6 seconds)
          if (errorCountRef.current >= 3) {
            const message = err instanceof Error ? err.message : 'Failed to fetch status';
            setState((prev) => ({ ...prev, error: message }));
          }
        }
      }
    };

    void poll();
    const intervalId = setInterval(() => {
      if (statusRef.current && TERMINAL_STATUSES.has(statusRef.current)) {
        clearInterval(intervalId);
        return;
      }
      void poll();
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [jobId]);

  return state;
}
