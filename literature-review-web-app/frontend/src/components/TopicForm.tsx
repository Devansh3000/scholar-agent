import {
  Box,
  Button,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Slider,
  TextField,
  Typography,
} from '@mui/material';
import { useState } from 'react';
import type { ReviewConfig } from '../api/client';

interface TopicFormProps {
  onSubmit: (topic: string, config: ReviewConfig) => void;
  isLoading: boolean;
}

const DEFAULT_CONFIG: ReviewConfig = {
  max_papers: 20,
  search_depth: 'medium',
  citation_style: 'APA',
  include_pdfs: true,
};

export function TopicForm({ onSubmit, isLoading }: TopicFormProps) {
  const [topic, setTopic] = useState('');
  const [config, setConfig] = useState<ReviewConfig>(DEFAULT_CONFIG);
  const [topicError, setTopicError] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (topic.trim().length < 5) {
      setTopicError('Topic must be at least 5 characters.');
      return;
    }
    if (topic.trim().length > 500) {
      setTopicError('Topic must be at most 500 characters.');
      return;
    }

    setTopicError('');
    onSubmit(topic.trim(), config);
  };

  return (
    <Box component="form" onSubmit={handleSubmit} sx={{ display: 'flex', flexDirection: 'column', gap: 3, maxWidth: 600, mx: 'auto', mt: 6, px: 2 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        Literature Review Generator
      </Typography>

      {/* Topic input */}
      <TextField
        label="Research Topic"
        placeholder="e.g. Deep learning for medical image segmentation"
        value={topic}
        onChange={(e) => setTopic(e.target.value)}
        error={!!topicError}
        helperText={topicError || `${topic.length}/500 characters`}
        multiline
        minRows={2}
        required
        disabled={isLoading}
        inputProps={{ minLength: 5, maxLength: 500 }}
      />

      {/* Max papers slider */}
      <Box>
        <Typography gutterBottom>
          Max papers: <strong>{config.max_papers}</strong>
        </Typography>
        <Slider
          value={config.max_papers}
          onChange={(_, value) => setConfig((c) => ({ ...c, max_papers: value as number }))}
          min={5}
          max={50}
          step={5}
          marks
          valueLabelDisplay="auto"
          disabled={isLoading}
          aria-label="Maximum number of papers"
        />
      </Box>

      {/* Search depth */}
      <FormControl disabled={isLoading}>
        <InputLabel id="search-depth-label">Search Depth</InputLabel>
        <Select
          labelId="search-depth-label"
          label="Search Depth"
          value={config.search_depth}
          onChange={(e) =>
            setConfig((c) => ({ ...c, search_depth: e.target.value as ReviewConfig['search_depth'] }))
          }
        >
          <MenuItem value="shallow">Shallow</MenuItem>
          <MenuItem value="medium">Medium</MenuItem>
          <MenuItem value="deep">Deep</MenuItem>
        </Select>
      </FormControl>

      {/* Citation style */}
      <FormControl disabled={isLoading}>
        <InputLabel id="citation-style-label">Citation Style</InputLabel>
        <Select
          labelId="citation-style-label"
          label="Citation Style"
          value={config.citation_style}
          onChange={(e) =>
            setConfig((c) => ({ ...c, citation_style: e.target.value as ReviewConfig['citation_style'] }))
          }
        >
          <MenuItem value="APA">APA</MenuItem>
          <MenuItem value="Harvard">Harvard</MenuItem>
          <MenuItem value="IEEE">IEEE</MenuItem>
        </Select>
      </FormControl>

      <Button
        type="submit"
        variant="contained"
        size="large"
        disabled={isLoading}
      >
        {isLoading ? 'Generating…' : 'Generate Review'}
      </Button>
    </Box>
  );
}
