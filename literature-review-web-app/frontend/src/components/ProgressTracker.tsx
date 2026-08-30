import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  LinearProgress,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Paper,
  Typography,
} from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked';
import AutorenewIcon from '@mui/icons-material/Autorenew';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import type { JobStatusResponse } from '../api/client';

interface ProgressTrackerProps {
  status: JobStatusResponse;
  onCancel: () => void;
  error?: string | null;
}

// All 10 pipeline stages in order with descriptions
const PIPELINE_STAGES = [
  {
    id: 'topic_understood',
    label: 'Topic Understanding',
    description: 'Analyzing topic, extracting keywords & generating search queries',
    agent: 'Agent 1',
  },
  {
    id: 'papers_fetched',
    label: 'Paper Search',
    description: 'Searching arXiv, Semantic Scholar, IEEE Xplore & Google Scholar in parallel',
    agent: 'Agent 2',
  },
  {
    id: 'pdfs_retrieved',
    label: 'PDF Retrieval',
    description: 'Downloading full-text PDFs where available',
    agent: 'Agent 3',
  },
  {
    id: 'summaries_done',
    label: 'Paper Summarization',
    description: 'Generating structured summaries for each paper using Gemini',
    agent: 'Agent 4',
  },
  {
    id: 'themes_identified',
    label: 'Thematic Clustering',
    description: 'Creating embeddings and grouping papers into thematic clusters',
    agent: 'Agent 5',
  },
  {
    id: 'analysis_complete',
    label: 'Comparative Analysis',
    description: 'Comparing methodologies and findings across paper groups',
    agent: 'Agent 6',
  },
  {
    id: 'gaps_identified',
    label: 'Gap Identification',
    description: 'Identifying methodological, empirical & theoretical research gaps',
    agent: 'Agent 7',
  },
  {
    id: 'review_written',
    label: 'Review Writing',
    description: 'Drafting introduction, thematic analysis, gaps section & conclusion',
    agent: 'Agent 8',
  },
  {
    id: 'citations_formatted',
    label: 'Citation Formatting',
    description: 'Formatting bibliography in selected citation style',
    agent: 'Agent 9',
  },
  {
    id: 'output_generated',
    label: 'PDF Generation',
    description: 'Assembling final literature review document',
    agent: 'Agent 10',
  },
];

const STAGE_ORDER = PIPELINE_STAGES.map((s) => s.id);

function getStageIndex(stage: string): number {
  return STAGE_ORDER.indexOf(stage);
}

function formatSeconds(seconds: number): string {
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  const mins = Math.floor(s / 60);
  const secs = s % 60;
  return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
}

function formatStageName(stage: string): string {
  return stage.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

export function ProgressTracker({ status, onCancel, error }: ProgressTrackerProps) {
  const currentStageIdx = getStageIndex(status.stage);
  const isFailed = status.status === 'failed';
  const isCancelled = status.status === 'cancelled';
  const isRunning = status.status === 'running' || status.status === 'pending';

  // Compute real progress: count completed stages
  const completedCount = currentStageIdx >= 0 ? currentStageIdx : 0;
  const progressPct = isFailed || isCancelled
    ? status.progress_pct
    : Math.max(status.progress_pct, (completedCount / 10) * 100);

  return (
    <Box sx={{ maxWidth: 700, mx: 'auto', mt: 4, px: 2 }}>
      {/* Header */}
      <Typography variant="h5" fontWeight={600} gutterBottom>
        Generating Literature Review
      </Typography>

      {/* Error/failure banner */}
      {(isFailed || error) && (
        <Alert severity="error" sx={{ mb: 2 }}>
          <Typography fontWeight={600}>Pipeline Failed</Typography>
          <Typography variant="body2" sx={{ mt: 0.5, fontFamily: 'monospace', fontSize: '0.8rem' }}>
            {status.message || error || 'An unknown error occurred.'}
          </Typography>
          {error && (
            <Typography variant="body2" sx={{ mt: 0.5, color: 'error.dark' }}>
              {error}
            </Typography>
          )}
        </Alert>
      )}

      {isCancelled && (
        <Alert severity="warning" sx={{ mb: 2 }}>Review was cancelled.</Alert>
      )}

      {/* Overall progress bar */}
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
          <Typography variant="body2" fontWeight={600}>
            {isFailed ? 'Failed' : isCancelled ? 'Cancelled' : `${Math.round(progressPct)}% complete`}
          </Typography>
          <Box sx={{ display: 'flex', gap: 2 }}>
            <Typography variant="body2" color="text.secondary">
              Elapsed: {formatSeconds(status.elapsed_seconds)}
            </Typography>
            {status.estimated_remaining_seconds != null && isRunning && (
              <Typography variant="body2" color="text.secondary">
                ~{formatSeconds(status.estimated_remaining_seconds)} remaining
              </Typography>
            )}
          </Box>
        </Box>

        <LinearProgress
          variant="determinate"
          value={Math.min(Math.max(progressPct, 0), 100)}
          color={isFailed ? 'error' : isCancelled ? 'warning' : 'primary'}
          sx={{ height: 12, borderRadius: 6, mb: 1 }}
        />

        {/* Current stage chip */}
        {status.stage && !isFailed && !isCancelled && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1 }}>
            <AutorenewIcon fontSize="small" color="primary" sx={{ animation: isRunning ? 'spin 1s linear infinite' : 'none', '@keyframes spin': { '0%': { transform: 'rotate(0deg)' }, '100%': { transform: 'rotate(360deg)' } } }} />
            <Typography variant="body2" color="primary" fontWeight={500}>
              {formatStageName(status.stage)}: {status.message || 'Working…'}
            </Typography>
          </Box>
        )}
      </Paper>

      {/* Per-agent stage list */}
      <Paper variant="outlined" sx={{ mb: 2 }}>
        <Typography variant="subtitle2" sx={{ px: 2, pt: 1.5, pb: 0.5, color: 'text.secondary' }}>
          Pipeline Stages
        </Typography>
        <Divider />
        <List dense disablePadding>
          {PIPELINE_STAGES.map((stage, idx) => {
            const isCompleted = currentStageIdx > idx || status.status === 'completed';
            const isActive = currentStageIdx === idx && isRunning;
            const isFailedHere = isFailed && currentStageIdx === idx;

            return (
              <ListItem
                key={stage.id}
                sx={{
                  py: 0.75,
                  bgcolor: isActive ? 'primary.50' : isFailedHere ? 'error.50' : 'transparent',
                  borderLeft: isActive ? '3px solid' : '3px solid transparent',
                  borderColor: isActive ? 'primary.main' : 'transparent',
                }}
              >
                <ListItemIcon sx={{ minWidth: 36 }}>
                  {isFailedHere ? (
                    <ErrorOutlineIcon fontSize="small" color="error" />
                  ) : isCompleted ? (
                    <CheckCircleIcon fontSize="small" color="success" />
                  ) : isActive ? (
                    <AutorenewIcon fontSize="small" color="primary" sx={{ animation: 'spin 1.2s linear infinite', '@keyframes spin': { '0%': { transform: 'rotate(0deg)' }, '100%': { transform: 'rotate(360deg)' } } }} />
                  ) : (
                    <RadioButtonUncheckedIcon fontSize="small" sx={{ color: 'text.disabled' }} />
                  )}
                </ListItemIcon>
                <ListItemText
                  primary={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Typography
                        variant="body2"
                        fontWeight={isActive ? 600 : isCompleted ? 500 : 400}
                        color={isFailedHere ? 'error.main' : isActive ? 'primary.main' : isCompleted ? 'text.primary' : 'text.disabled'}
                      >
                        {stage.label}
                      </Typography>
                      <Chip
                        label={stage.agent}
                        size="small"
                        sx={{ height: 16, fontSize: '0.65rem', opacity: isCompleted || isActive ? 1 : 0.4 }}
                        color={isCompleted ? 'success' : isActive ? 'primary' : 'default'}
                        variant={isCompleted || isActive ? 'filled' : 'outlined'}
                      />
                    </Box>
                  }
                  secondary={
                    <Typography variant="caption" color={isActive ? 'primary.main' : 'text.secondary'} sx={{ opacity: isActive || isCompleted ? 1 : 0.5 }}>
                      {isActive && status.message ? status.message : stage.description}
                    </Typography>
                  }
                />
              </ListItem>
            );
          })}
        </List>
      </Paper>

      {/* Cancel button */}
      {isRunning && (
        <Button variant="outlined" color="error" size="small" onClick={onCancel}>
          Cancel Review
        </Button>
      )}
    </Box>
  );
}
