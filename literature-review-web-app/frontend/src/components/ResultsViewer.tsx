import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  Chip,
  Divider,
  Stack,
  Typography,
} from '@mui/material';
import { downloadPDF, type JobResultResponse } from '../api/client';

interface ResultsViewerProps {
  result: JobResultResponse;
  jobId: string;
}

export function ResultsViewer({ result, jobId }: ResultsViewerProps) {
  const { review } = result;

  // Group research gaps by gap_type
  const gapsByType = review.research_gaps.reduce<Record<string, typeof review.research_gaps>>(
    (acc, gap) => {
      (acc[gap.gap_type] ??= []).push(gap);
      return acc;
    },
    {},
  );

  return (
    <Box sx={{ maxWidth: 800, mx: 'auto', mt: 6, px: 2, pb: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 2 }}>
        <Box>
          <Typography variant="h4" component="h1">
            {review.topic}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {review.paper_count} papers · {review.citation_style} · Generated{' '}
            {new Date(review.generated_at).toLocaleString()}
          </Typography>
        </Box>
        <Button variant="contained" onClick={() => downloadPDF(jobId)}>
          Download PDF
        </Button>
      </Box>

      <Divider />

      {/* Executive summary */}
      <Box>
        <Typography variant="h5" gutterBottom>
          Executive Summary
        </Typography>
        <Typography variant="body1" sx={{ whiteSpace: 'pre-line' }}>
          {review.executive_summary}
        </Typography>
      </Box>

      <Divider />

      {/* Themes accordion */}
      <Box>
        <Typography variant="h5" gutterBottom>
          Themes ({review.themes.length})
        </Typography>
        {review.themes.length === 0 ? (
          <Typography color="text.secondary">No themes identified.</Typography>
        ) : (
          review.themes.map((theme) => (
            <Accordion key={theme.theme_id} disableGutters>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                  <Typography fontWeight={600}>{theme.label}</Typography>
                  <Chip
                    label={`${theme.paper_ids.length} paper${theme.paper_ids.length !== 1 ? 's' : ''}`}
                    size="small"
                    variant="outlined"
                  />
                </Box>
              </AccordionSummary>
              <AccordionDetails>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  {theme.description}
                </Typography>
                {theme.narrative_summary && (
                  <Typography variant="body2" sx={{ mt: 1, whiteSpace: 'pre-line' }}>
                    {theme.narrative_summary}
                  </Typography>
                )}
              </AccordionDetails>
            </Accordion>
          ))
        )}
      </Box>

      <Divider />

      {/* Research gaps */}
      <Box>
        <Typography variant="h5" gutterBottom>
          Research Gaps
        </Typography>
        {Object.keys(gapsByType).length === 0 ? (
          <Typography color="text.secondary">No research gaps identified.</Typography>
        ) : (
          Object.entries(gapsByType).map(([gapType, gaps]) => (
            <Box key={gapType} sx={{ mb: 3 }}>
              <Chip
                label={gapType.charAt(0).toUpperCase() + gapType.slice(1)}
                color="primary"
                sx={{ mb: 1 }}
              />
              {gaps.map((gap, idx) => (
                <Box key={idx} sx={{ ml: 1, mb: 1.5 }}>
                  <Typography variant="body2">{gap.description}</Typography>
                  {gap.suggested_questions.length > 0 && (
                    <Stack direction="row" flexWrap="wrap" spacing={1} sx={{ mt: 0.5 }}>
                      {gap.suggested_questions.map((q, qi) => (
                        <Chip key={qi} label={q} size="small" variant="outlined" />
                      ))}
                    </Stack>
                  )}
                </Box>
              ))}
            </Box>
          ))
        )}
      </Box>

      <Divider />

      {/* Quality metrics */}
      {Object.keys(review.quality_metrics).length > 0 && (
        <Box>
          <Typography variant="h6" gutterBottom>
            Quality Metrics
          </Typography>
          <Stack direction="row" flexWrap="wrap" spacing={1}>
            {Object.entries(review.quality_metrics).map(([key, value]) => (
              <Chip
                key={key}
                label={`${key}: ${String(value)}`}
                variant="outlined"
                size="small"
              />
            ))}
          </Stack>
        </Box>
      )}
    </Box>
  );
}
